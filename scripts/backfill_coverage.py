"""
backfill_coverage.py - populate the coverage ledger from existing jobs.

The job_products / job_coverage tables were added after jobs already existed.
This script walks every job, derives its slot + product keys from job.context,
and writes the missing ledger rows. Idempotent: jobs that already have a
coverage row are skipped, so it is safe to re-run.

Usage (from repo root):
    .venv\\Scripts\\python.exe scripts\\backfill_coverage.py            # dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_coverage.py --execute  # write rows
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from sqlalchemy import select  # noqa: E402

from database import AsyncSessionLocal, Base, engine  # noqa: E402
from models.coverage import JobCoverage  # noqa: E402
from models.job import Job  # noqa: E402
from services.coverage import compute_slot_key, record_coverage  # noqa: E402


async def backfill(execute: bool) -> None:
    # Ensure the coverage tables exist (no-op if already created).
    import models  # noqa: F401 - register all tables on Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        jobs = (await db.execute(select(Job))).scalars().all()
        covered = set((await db.execute(select(JobCoverage.job_id))).scalars().all())

        done = skipped = 0
        for job in jobs:
            if job.id in covered:
                continue
            ctx = job.context or {}
            brief = ctx.get("brief") or {}
            article_type = ctx.get("article_type") or brief.get("article_type")
            if not brief or not article_type:
                skipped += 1
                continue
            slot = compute_slot_key(article_type, brief)
            if execute:
                await record_coverage(db, job, brief, article_type, slot)
            done += 1

        if execute:
            await db.commit()

        verb = "Backfilled" if execute else "Would backfill"
        print(f"{verb} {done} job(s). Already covered: {len(covered)}. Skipped (no brief): {skipped}.")
        if not execute:
            print("Dry-run - pass --execute to write the rows.")


if __name__ == "__main__":
    asyncio.run(backfill(execute="--execute" in sys.argv))
