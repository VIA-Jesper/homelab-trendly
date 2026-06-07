import asyncio
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
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
from services.pipeline import pipeline_service
from services.pricerunner_client import fetch_product_from_url


def _extract_product_id(url: str) -> str | None:
    m = re.search(r'/pl/\d+-(\d+)', url)
    return m.group(1) if m else None

router = APIRouter(prefix="/jobs", tags=["jobs"])


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


class CreateJobFromUrlRequest(BaseModel):
    site_key: str       # e.g. "hus" — must match a key in brief_builder.SITE_CONFIGS
    product_url: str    # full PriceRunner listing URL
    reasoning: str | None = None
    force: bool = False  # bypass duplicate check


@router.post("/from-url", response_model=JobResponse, status_code=201)
async def create_job_from_url(
    request: CreateJobFromUrlRequest,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Create an article job from a PriceRunner product URL.

    This is the primary entry point for single-product-review generation.
    The brief is built synchronously at job creation so the worker only ever
    handles agent steps — no fetch_brief step in the queue.

    Flow:
      1. Validate site_key → resolve site config
      2. Fetch product data from PriceRunner (live, ~1s)
      3. Build ContentBrief
      4. Create Job with brief in context
      5. Queue write_draft → optimize_seo → qa_review steps
    """
    # Validate site key before hitting the network
    try:
        site_cfg = get_site_config(request.site_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fetch product from PriceRunner — this is a live HTTP call
    product = await fetch_product_from_url(request.product_url, country=site_cfg.pricerunner_country)
    if product is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Could not fetch product from URL: {request.product_url}. "
                "Check that it is a valid PriceRunner product listing URL."
            ),
        )

    brief = build_brief_for_product(product, request.site_key)

    SUPPORTED_ARTICLE_TYPES = {"single-product-review", "comparison", "hero"}
    if brief.article_type not in SUPPORTED_ARTICLE_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Article type '{brief.article_type}' is not implemented yet. Supported: {sorted(SUPPORTED_ARTICLE_TYPES)}",
        )

    if brief.category.isdigit():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown PriceRunner category ID '{brief.category}'. "
                "Add it to _CATEGORY_SLUG in api/services/pricerunner_client.py and restart the API."
            ),
        )

    # Verify a matching site row exists in the DB (sites table is the source of truth
    # for WP category IDs and other DB-level config beyond what SITE_CONFIGS holds)
    site_result = await db.execute(
        select(Site).where(Site.domain == site_cfg.domain, Site.is_active.is_(True))
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(
            status_code=404,
            detail=f"No active site found for domain '{site_cfg.domain}'. Create it via POST /api/v1/sites first.",
        )

    if not request.force:
        product_id = _extract_product_id(request.product_url)
        dup_filters = []
        if product_id:
            dup_filters.append(
                func.json_extract(Job.context, "$.product_url").like(f"%{product_id}%")
            )
        if brief.products:
            dup_filters.append(
                func.json_extract(Job.context, "$.brief.products[0].name") == brief.products[0].name
            )
        dup_result = await db.execute(
            select(Job).where(Job.site_id == site.id, or_(*dup_filters))
        )
        duplicate = dup_result.scalar_one_or_none()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_product",
                    "message": f"A job for '{brief.products[0].name if brief.products else 'this product'}' already exists (status: {duplicate.status}). Add \"force\": true to the request body to create a new job anyway.",
                    "existing_job_id": str(duplicate.id),
                    "existing_status": duplicate.status,
                },
            )

    job = Job(
        site_id=site.id,
        status="queued",
        context={
            "product_url": request.product_url,
            "brief": brief.model_dump(),
            "article_type": brief.article_type,
            "site_key": request.site_key,
        },
        reasoning=request.reasoning,
    )
    db.add(job)
    await db.flush()

    await pipeline_service.create_steps_for_job(job, db)

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        site_id=str(job.site_id),
        context=job.context,
    )


class CreateComparisonJobRequest(BaseModel):
    site_key: str
    product_urls: list[str]   # 2-4 PriceRunner product URLs
    reasoning: str | None = None
    force: bool = False


@router.post("/from-urls", response_model=JobResponse, status_code=201)
async def create_comparison_job(
    request: CreateComparisonJobRequest,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Create a comparison article job from 2-4 PriceRunner product URLs.

    All products are fetched in parallel and assembled into a single ContentBrief
    with article_type="comparison". The same pipeline steps run as for single-product
    jobs — the type-specific generate prompt is selected automatically.
    """
    if not (2 <= len(request.product_urls) <= 4):
        raise HTTPException(status_code=422, detail="product_urls must contain 2-4 URLs")

    try:
        site_cfg = get_site_config(request.site_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fetch all products in parallel
    results = await asyncio.gather(
        *[fetch_product_from_url(url, country=site_cfg.pricerunner_country) for url in request.product_urls],
        return_exceptions=True,
    )
    products = []
    for url, result in zip(request.product_urls, results):
        if isinstance(result, Exception) or result is None:
            raise HTTPException(
                status_code=422,
                detail=f"Could not fetch product from URL: {url}. Check that it is a valid PriceRunner product listing URL.",
            )
        products.append(result)

    brief = build_brief_for_comparison(products, request.site_key)

    if brief.category.isdigit():
        raise HTTPException(
            status_code=422,
            detail=f"Unknown PriceRunner category ID '{brief.category}'. Add it to _CATEGORY_SLUG in api/services/pricerunner_client.py.",
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

    if not request.force:
        # Duplicate: any existing job that shares 2+ of the same products
        product_names = [p.name for p in brief.products]
        dup_filters = [
            func.json_extract(Job.context, f"$.brief.products[{i}].name") == name
            for i, name in enumerate(product_names)
        ]
        dup_result = await db.execute(
            select(Job).where(Job.site_id == site.id, or_(*dup_filters))
        )
        duplicate = dup_result.scalar_one_or_none()
        if duplicate:
            names_str = " vs ".join(product_names[:2])
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_comparison",
                    "message": f"A job comparing '{names_str}' already exists (status: {duplicate.status}). Add \"force\": true to create a new job anyway.",
                    "existing_job_id": str(duplicate.id),
                    "existing_status": duplicate.status,
                },
            )

    job = Job(
        site_id=site.id,
        status="queued",
        context={
            "product_urls": request.product_urls,
            "brief": brief.model_dump(),
            "article_type": brief.article_type,
            "site_key": request.site_key,
        },
        reasoning=request.reasoning,
    )
    db.add(job)
    await db.flush()

    await pipeline_service.create_steps_for_job(job, db)

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        site_id=str(job.site_id),
        context=job.context,
    )


class CreateHeroJobRequest(BaseModel):
    site_key: str
    product_urls: list[str]   # 5-10 PriceRunner product URLs
    category_name: str        # human-readable category, e.g. "robotplæneklipper"
    reasoning: str | None = None
    force: bool = False


@router.post("/from-hero", response_model=JobResponse, status_code=201)
async def create_hero_job(
    request: CreateHeroJobRequest,
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Create a hero (category roundup) article job from 5-10 PriceRunner product URLs.

    Hero articles target high-volume "bedste [category]" head terms. They include
    a mandatory buying guide section so the article can rank on informational queries.
    All products are fetched in parallel and assembled into a single ContentBrief
    with article_type="hero". The same pipeline steps run as for other types — the
    type-specific generate prompt is selected automatically.
    """
    if not (5 <= len(request.product_urls) <= 10):
        raise HTTPException(status_code=422, detail="product_urls must contain 5-10 URLs")

    if not request.category_name.strip():
        raise HTTPException(status_code=422, detail="category_name is required for hero articles")

    try:
        site_cfg = get_site_config(request.site_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fetch all products in parallel
    results = await asyncio.gather(
        *[fetch_product_from_url(url, country=site_cfg.pricerunner_country) for url in request.product_urls],
        return_exceptions=True,
    )
    products = []
    for url, result in zip(request.product_urls, results):
        if isinstance(result, Exception) or result is None:
            raise HTTPException(
                status_code=422,
                detail=f"Could not fetch product from URL: {url}. Check that it is a valid PriceRunner product listing URL.",
            )
        products.append(result)

    brief = build_brief_for_hero(products, request.category_name, request.site_key)

    site_result = await db.execute(
        select(Site).where(Site.domain == site_cfg.domain, Site.is_active.is_(True))
    )
    site = site_result.scalar_one_or_none()
    if not site:
        raise HTTPException(
            status_code=404,
            detail=f"No active site found for domain '{site_cfg.domain}'. Create it via POST /api/v1/sites first.",
        )

    if not request.force:
        # Duplicate: any existing hero job that shares 3+ of the same products
        product_names = [p.name for p in brief.products]
        dup_filters = [
            func.json_extract(Job.context, f"$.brief.products[{i}].name") == name
            for i, name in enumerate(product_names)
        ]
        dup_result = await db.execute(
            select(Job).where(
                Job.site_id == site.id,
                func.json_extract(Job.context, "$.article_type") == "hero",
                or_(*dup_filters),
            )
        )
        # Heuristic: surface the most recent matching hero job. Strict 3+ overlap
        # would require post-fetch comparison; use first hit as a close-enough signal.
        duplicate = dup_result.scalars().first()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_hero",
                    "message": f"A hero job for '{request.category_name}' or overlapping products already exists (status: {duplicate.status}). Add \"force\": true to create a new job anyway.",
                    "existing_job_id": str(duplicate.id),
                    "existing_status": duplicate.status,
                },
            )

    job = Job(
        site_id=site.id,
        status="queued",
        context={
            "product_urls": request.product_urls,
            "category_name": request.category_name,
            "brief": brief.model_dump(),
            "article_type": brief.article_type,
            "site_key": request.site_key,
        },
        reasoning=request.reasoning,
    )
    db.add(job)
    await db.flush()

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

    from_step=None (default): full reset — drop all steps, recreate from scratch.
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
        message = f"Job reset from '{from_step}' — earlier steps preserved."
    else:
        await db.execute(delete(Step).where(Step.job_id == job.id))
        job.context = {k: v for k, v in job.context.items() if k != "qa_corrected"}
        await db.flush()
        await pipeline_service.create_steps_for_job(job, db)
        message = "Job reset — fresh steps created."

    job.status = "queued"
    await db.commit()

    return {"job_id": job_id, "status": "queued", "message": message}
