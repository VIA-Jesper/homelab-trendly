import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.job import Job
from models.site import Site
from services.brief_builder import build_brief_for_product, get_site_config
from services.pipeline import pipeline_service
from services.pricerunner_client import fetch_product_from_url

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
