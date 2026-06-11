"""
backfill_scores.py - Add score_article step to existing complete jobs.

Finds all complete jobs that don't have a score_article step, injects the step,
and sets the job back to in_progress so the worker picks it up.

Usage (from repo root):
    .venv/Scripts/python.exe scripts/backfill_scores.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from sqlalchemy import select
from database import AsyncSessionLocal
import models  # noqa: F401 - registers ORM classes
from models.job import Job
from models.prompt import Prompt
from models.step import Step


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Get the score_article prompt
        prompt_result = await db.execute(
            select(Prompt).where(Prompt.name == "score_article", Prompt.is_active.is_(True))
        )
        prompt = prompt_result.scalar_one_or_none()
        if not prompt:
            print("ERROR: score_article prompt not found. Run load_prompts.py first.")
            return

        # Find complete jobs
        jobs_result = await db.execute(
            select(Job).where(Job.status == "complete")
        )
        jobs = jobs_result.scalars().all()

        backfilled = 0
        for job in jobs:
            # Check if score step already exists
            existing = await db.execute(
                select(Step).where(Step.job_id == job.id, Step.step_name == "score_article")
            )
            if existing.scalar_one_or_none():
                continue

            # Find the highest step_order for this job
            orders_result = await db.execute(
                select(Step.step_order).where(Step.job_id == job.id)
            )
            orders = [r for r in orders_result.scalars().all()]
            next_order = max(orders) + 1 if orders else 3

            db.add(Step(
                job_id=job.id,
                step_name="score_article",
                step_order=next_order,
                prompt_id=prompt.id,
                status="pending",
                attempt=1,
            ))
            job.status = "in_progress"
            backfilled += 1
            print(f"  Queued score_article for job {str(job.id)[:8]}…")

        await db.commit()
        print(f"\nDone. {backfilled} job(s) queued for scoring.")


if __name__ == "__main__":
    asyncio.run(main())
