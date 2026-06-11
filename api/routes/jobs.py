import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.job import Job
from models.site import Site
from models.step import Step
from services.brief_builder import (
    build_brief_for_comparison,
    build_brief_for_hero,
    build_brief_for_product,
    get_site_config,
)
from services.coverage import compute_slot_key, find_slot_conflict, record_coverage
from services.pipeline import pipeline_service
from services.pricerunner_client import fetch_product_from_url


router = APIRouter(prefix="/jobs", tags=["jobs"])

# Article type → (min_urls, max_urls). Validated at the unified endpoint
# before fetching from PriceRunner so bad payloads fail fast.
ARTICLE_TYPE_URL_COUNTS: dict[str, tuple[int, int]] = {
    "single-product-review": (1, 1),
    "comparison":             (2, 4),
    "hero":                   (5, 10),
}


class CreateJobRequest(BaseModel):
    site_id: str
    context: dict          # article_type, target_keyword, reasoning, product info, etc.
    reasoning: str | None = None


class JobResponse(BaseModel):
    job_id: str
    status: str
    site_id: str
    context: dict


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    request: CreateJobRequest,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Orchestrator (or human) creates a new article job.
    System creates all pipeline steps automatically based on config.
    """
    # Verify site exists
    site_result = await db.execute(
        select(Site).where(Site.id == uuid.UUID(request.site_id), Site.is_active.is_(True))
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    job = Job(
        site_id=uuid.UUID(request.site_id),
        status="queued",
        context=request.context,
        reasoning=request.reasoning,
    )
    db.add(job)
    await db.flush()  # get job.id before creating steps

    await pipeline_service.create_steps_for_job(job, db)

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        site_id=str(job.site_id),
        context=job.context,
    )


class CreateJobFromProductsRequest(BaseModel):
    site_key: str            # e.g. "hus" - must match a key in brief_builder.SITE_CONFIGS
    article_type: str        # single-product-review | comparison | hero
    product_urls: list[str]  # 1 for single, 2-4 for comparison, 5-10 for hero
    editorial_note: str | None = None  # optional in-band guidance threaded to the generator
    reasoning: str | None = None       # optional audit metadata, not seen by the generator
    force: bool = False                # bypass duplicate check


@router.post("/from-products", response_model=JobResponse, status_code=201)
async def create_job_from_products(
    request: CreateJobFromProductsRequest,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Create an article job from a list of PriceRunner product URLs.

    Single entry point for all article types. The article_type field discriminates:
      - single-product-review: 1 URL → review one product
      - comparison: 2-4 URLs → head-to-head article
      - hero: 5-10 URLs → category roundup with buying guide

    Flow:
      1. Validate article_type + URL count
      2. Resolve site config
      3. Fetch all products from PriceRunner in parallel
      4. Build ContentBrief via the type-specific brief builder
      5. Validate category mapping is known
      6. Check for duplicate jobs (same article_type + overlapping products)
      7. Create Job with brief + optional editorial_note in context
      8. Queue pipeline steps (write_draft → optimize_seo → qa_review → score)

    editorial_note: free-text guidance threaded into the generator's prompt context
    as `context.editorial_note`. Use to steer angle, framing, or constraints that
    aren't derivable from product specs. Example: "Lead with battery life - that
    matters most to this audience."
    """
    if request.article_type not in ARTICLE_TYPE_URL_COUNTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown article_type '{request.article_type}'. "
                f"Supported: {sorted(ARTICLE_TYPE_URL_COUNTS)}"
            ),
        )

    min_n, max_n = ARTICLE_TYPE_URL_COUNTS[request.article_type]
    n_urls = len(request.product_urls)
    if not (min_n <= n_urls <= max_n):
        raise HTTPException(
            status_code=422,
            detail=(
                f"article_type '{request.article_type}' requires {min_n}-{max_n} URLs; "
                f"got {n_urls}."
            ),
        )

    try:
        site_cfg = get_site_config(request.site_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Parallel fetch - same path for 1 URL or 10
    results = await asyncio.gather(
        *[fetch_product_from_url(url, country=site_cfg.pricerunner_country)
          for url in request.product_urls],
        return_exceptions=True,
    )
    products = []
    for url, result in zip(request.product_urls, results):
        if isinstance(result, Exception) or result is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Could not fetch product from URL: {url}. "
                    "Check that it is a valid PriceRunner product listing URL."
                ),
            )
        products.append(result)

    # Dispatch to the right brief builder
    try:
        if request.article_type == "single-product-review":
            brief = build_brief_for_product(products[0], request.site_key)
        elif request.article_type == "comparison":
            brief = build_brief_for_comparison(products, request.site_key)
        else:  # hero
            brief = build_brief_for_hero(products, request.site_key)
    except ValueError as e:
        # Hero raises on cross-category mixes; surface as 422.
        raise HTTPException(status_code=422, detail=str(e))

    if brief.category.isdigit():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown PriceRunner category ID '{brief.category}'. "
                "Add it to _CATEGORY_SLUG in api/services/pricerunner_client.py and restart the API."
            ),
        )

    site_result = await db.execute(
        select(Site).where(Site.domain == site_cfg.domain, Site.is_active.is_(True))
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(
            status_code=404,
            detail=f"No active site found for domain '{site_cfg.domain}'. Create it via POST /api/v1/sites first.",
        )

    # De-dup on slot identity (category + format + subject) via the coverage
    # ledger - not the old positional, same-type name match. A slot_key collision
    # means "this is the same article". See services/dedup.py + services/coverage.py.
    brief_dict = brief.model_dump()
    slot = compute_slot_key(brief.article_type, brief_dict)

    if not request.force:
        conflict = await find_slot_conflict(db, site.id, slot)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_slot",
                    "message": (
                        f"A {brief.article_type} for this slot already exists "
                        f"(status: {conflict['existing_status']}). "
                        "Add \"force\": true to create a new job anyway."
                    ),
                    "existing_job_id": conflict["existing_job_id"],
                    "existing_status": conflict["existing_status"],
                    "slot_key": slot,
                },
            )

    context: dict = {
        "product_urls": request.product_urls,
        "brief": brief_dict,
        "article_type": brief.article_type,
        "site_key": request.site_key,
        "slot_key": slot,
    }
    if request.editorial_note and request.editorial_note.strip():
        context["editorial_note"] = request.editorial_note.strip()

    job = Job(
        site_id=site.id,
        status="queued",
        context=context,
        reasoning=request.reasoning,
    )
    db.add(job)
    await db.flush()

    # Record coverage before create_steps_for_job (which commits) so the ledger
    # rows land in the same transaction as the job + its steps.
    await record_coverage(db, job, brief_dict, brief.article_type, slot)
    await pipeline_service.create_steps_for_job(job, db)

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        site_id=str(job.site_id),
        context=job.context,
    )


@router.get("/{job_id}", response_model=dict)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Inspect job state and all step records."""
    result = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job.id),
        "site_id": str(job.site_id),
        "status": job.status,
        "context": job.context,
        "reasoning": job.reasoning,
        "created_at": job.created_at.isoformat(),
        "steps": [
            {
                "step_id": str(s.id),
                "step_name": s.step_name,
                "step_order": s.step_order,
                "status": s.status,
                "attempt": s.attempt,
                "has_output": s.output is not None,
            }
            for s in job.steps
        ],
    }


class ResetJobRequest(BaseModel):
    from_step: str | None = None  # step name to reset from; None = full reset


@router.post("/{job_id}/reset", response_model=dict)
async def reset_job(
    job_id: str,
    request: ResetJobRequest = ResetJobRequest(),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reset a job back to queued.

    from_step=None (default): full reset - drop all steps, recreate from scratch.
    from_step="optimize_seo": keep completed steps before that step, drop and
      recreate everything from that step onward. Useful for re-running SEO/QA
      without discarding the draft.
    """
    result = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from_step = request.from_step

    from config import settings as _settings

    if from_step:
        # Resolve the order of the named step from config (not DB, since it may be deleted)
        step_cfgs = _settings.pipeline_steps
        from_order = next(
            (i for i, s in enumerate(step_cfgs) if s["name"] == from_step), None
        )
        if from_order is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown step '{from_step}'. Known steps: {[s['name'] for s in step_cfgs]}",
            )
        # Delete steps at or after from_order, keep earlier ones intact
        await db.execute(
            delete(Step).where(Step.job_id == job.id, Step.step_order >= from_order)
        )
        await db.flush()
        # Recreate only the deleted steps
        for order, step_cfg in enumerate(step_cfgs):
            if order < from_order:
                continue
            prompt = await pipeline_service._get_active_prompt(step_cfg["prompt_name"], db)
            db.add(Step(
                job_id=job.id,
                step_name=step_cfg["name"],
                step_order=order,
                prompt_id=prompt.id if prompt else None,
                status="pending",
                attempt=1,
            ))
        message = f"Job reset from '{from_step}' - earlier steps preserved."
    else:
        await db.execute(delete(Step).where(Step.job_id == job.id))
        job.context = {k: v for k, v in job.context.items() if k != "qa_corrected"}
        await db.flush()
        await pipeline_service.create_steps_for_job(job, db)
        message = "Job reset - fresh steps created."

    job.status = "queued"
    await db.commit()

    return {"job_id": job_id, "status": "queued", "message": message}
