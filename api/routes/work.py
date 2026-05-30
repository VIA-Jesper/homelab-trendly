import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.job import Job
from models.step import Step
from services.pipeline import pipeline_service

router = APIRouter(prefix="/work", tags=["work"])


class WorkResponse(BaseModel):
    status: str           # "task" or "empty"
    task_id: str | None = None
    prompt: str | None = None
    content: dict | None = None


class WorkResult(BaseModel):
    output: str


class WorkFailure(BaseModel):
    error: str


@router.get("", response_model=WorkResponse)
async def get_work(db: AsyncSession = Depends(get_db)) -> WorkResponse:
    """
    Worker polls this endpoint. Returns next pending task or {"status": "empty"}.
    Worker script loops until status == "empty", then exits.

    Each poll also expires stale in_progress steps (worker died mid-task). Expired
    steps are reset to pending and count against max_attempts, so a broken step
    can't burn tokens indefinitely.
    """
    # Reclaim any steps whose worker lease expired before looking for new work
    await pipeline_service.expire_stale_steps(db)

    # Find oldest queued/in_progress job with a pending step
    result = await db.execute(
        select(Job)
        .where(Job.status.in_(["queued", "in_progress"]))
        .order_by(Job.created_at)
        .limit(1)
    )
    job = result.scalar_one_or_none()

    if not job:
        return WorkResponse(status="empty")

    step = await pipeline_service.get_next_step(job, db)
    if not step:
        return WorkResponse(status="empty")

    # Claim: mark in_progress and record lease timestamp
    step.status = "in_progress"
    step.claimed_at = datetime.now(timezone.utc)
    job.status = "in_progress"
    await db.commit()

    step_input = await pipeline_service.build_step_input(step, job, db)

    return WorkResponse(
        status="task",
        task_id=str(step.id),
        prompt=step_input["prompt"],
        content=step_input,
    )


@router.post("/{task_id}", response_model=dict)
async def submit_work(
    task_id: str,
    result: WorkResult,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Worker submits completed task output. System advances pipeline state.
    """
    step_result = await db.execute(
        select(Step).where(Step.id == uuid.UUID(task_id))
    )
    step = step_result.scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Task not found")

    job_result = await db.execute(select(Job).where(Job.id == step.job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    status = await pipeline_service.handle_step_result(step, result.output, job, db)
    return status


@router.post("/{task_id}/fail", response_model=dict)
async def fail_work(
    task_id: str,
    body: WorkFailure,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Worker calls this when the agent errors out (instead of dying silently).
    Marks the step failed and creates a new pending attempt if retries remain,
    otherwise marks the job failed. Prevents steps from getting stuck in_progress.
    """
    step_result = await db.execute(select(Step).where(Step.id == uuid.UUID(task_id)))
    step = step_result.scalar_one_or_none()
    if not step:
        raise HTTPException(status_code=404, detail="Task not found")

    job_result = await db.execute(select(Job).where(Job.id == step.job_id))
    job = job_result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return await pipeline_service.fail_step(step, body.error, job, db)
