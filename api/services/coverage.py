"""
coverage.py - the de-dup ledger: read/write helpers over job_products + job_coverage.

The API gate calls find_slot_conflict() before creating a job and record_coverage()
after. The planner (Phase 1) reads the same tables to find unfilled slots. All the
canonical-key logic lives in services.dedup; this module is only the DB layer.

Functions take an AsyncSession so they are unit-testable against an in-memory DB.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.coverage import JobCoverage, JobProduct
from models.job import Job
from services.dedup import canonical_product_key, normalize_category, slot_key

# Jobs in these states no longer "own" their slot, so they don't block new jobs.
_DEAD_STATES = ("archived", "failed")


def product_entries(brief: dict) -> list[tuple[str, str]]:
    """[(product_key, name), ...] for every product in a brief."""
    out: list[tuple[str, str]] = []
    for p in (brief.get("products") or []):
        key = canonical_product_key(
            p.get("name", ""),
            pid=p.get("id"),
            url=p.get("affiliate_url") or p.get("product_url"),
        )
        out.append((key, p.get("name", "")))
    return out


def compute_slot_key(article_type: str, brief: dict, segment: str | None = None) -> str:
    """Canonical slot identity for a brief (delegates to services.dedup.slot_key)."""
    keys = [k for k, _ in product_entries(brief)]
    return slot_key(article_type, brief.get("category", ""), keys, segment=segment)


async def find_slot_conflict(db: AsyncSession, site_id: uuid.UUID, slot: str) -> dict | None:
    """Return info on a live job already owning this slot on this site, else None."""
    q = (
        select(JobCoverage.job_id, Job.status)
        .join(Job, Job.id == JobCoverage.job_id)
        .where(
            JobCoverage.site_id == site_id,
            JobCoverage.slot_key == slot,
            Job.status.notin_(_DEAD_STATES),
        )
        .limit(1)
    )
    row = (await db.execute(q)).first()
    if row is None:
        return None
    return {"existing_job_id": str(row[0]), "existing_status": row[1], "slot_key": slot}


async def record_coverage(
    db: AsyncSession,
    job: Job,
    brief: dict,
    article_type: str,
    slot: str,
    primary_keyword: str | None = None,
) -> None:
    """Write the coverage row + one product row per product. Caller commits."""
    db.add(JobCoverage(
        job_id=job.id,
        site_id=job.site_id,
        slot_key=slot,
        category_slug=normalize_category(brief.get("category", "")),
        article_type=article_type,
        primary_keyword=primary_keyword,
    ))
    for key, name in product_entries(brief):
        db.add(JobProduct(
            job_id=job.id,
            site_id=job.site_id,
            product_key=key,
            name=name,
            article_type=article_type,
        ))


async def set_coverage_slug(db: AsyncSession, job_id: uuid.UUID, slug: str | None) -> None:
    """Record the final published slug on the job's coverage row (best-effort)."""
    if not slug:
        return
    row = (
        await db.execute(select(JobCoverage).where(JobCoverage.job_id == job_id))
    ).scalar_one_or_none()
    if row:
        row.slug = slug
