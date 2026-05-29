import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.job import Job
from models.site import Site
from services.pipeline import pipeline_service

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
