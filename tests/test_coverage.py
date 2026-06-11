"""
Integration test for the coverage ledger (api/services/coverage.py) against a
real in-memory SQLite DB - no HTTP, no PriceRunner.

Each test runs an async scenario via asyncio.run(), so only plain `pytest` is
needed (no pytest-asyncio). The repo .env supplies DATABASE_URL/API_KEY that the
services package import requires.
Run: python -m pytest tests/test_coverage.py
"""

import asyncio
import pathlib
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "api"))

from database import Base  # noqa: E402
from models.job import Job  # noqa: E402
from models.site import Site  # noqa: E402
from services.coverage import (  # noqa: E402
    compute_slot_key,
    find_slot_conflict,
    record_coverage,
)

_HUS = "robotstøvsugere"


def _brief(pid: str, name: str) -> dict:
    return {
        "category": _HUS,
        "products": [{
            "id": pid,
            "name": name,
            "affiliate_url": f"https://www.pricerunner.dk/pl/19-{pid.split('_')[-1]}/x",
        }],
    }


async def _new_db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    import models  # noqa: F401 - register all tables on Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _seed_job(db, site, brief, article_type):
    slot = compute_slot_key(article_type, brief)
    job = Job(site_id=site.id, status="queued", context={"brief": brief, "article_type": article_type})
    db.add(job)
    await db.flush()
    await record_coverage(db, job, brief, article_type, slot)
    await db.commit()
    return job, slot


async def _scenario():
    engine, Session = await _new_db()
    async with Session() as db:
        site = Site(name="hus", domain="husforbegyndere.dk")
        db.add(site)
        await db.flush()

        brief = _brief("pr_111", "Roborock S8 Pro Ultra")
        job, slot = await _seed_job(db, site, brief, "single-product-review")

        # 1. Same product → slot conflict, points at the existing job.
        conflict = await find_slot_conflict(db, site.id, slot)
        assert conflict is not None
        assert conflict["existing_job_id"] == str(job.id)

        # 2. A name variant of the SAME product id → still the same slot (the bug
        #    the old exact-name check missed).
        variant = _brief("pr_111", "Roborock S8 Pro Ultra (hvid)")
        assert compute_slot_key("single-product-review", variant) == slot

        # 3. A different product → free slot.
        other = _brief("pr_222", "Eufy X10")
        assert await find_slot_conflict(db, site.id, compute_slot_key("single-product-review", other)) is None

        # 4. Same products, but a roundup → different slot (single != roundup).
        assert await find_slot_conflict(db, site.id, compute_slot_key("hero", brief)) is None

        # 5. Archiving the owner frees the slot.
        job.status = "archived"
        await db.commit()
        assert await find_slot_conflict(db, site.id, slot) is None
    await engine.dispose()


def test_coverage_slot_lifecycle():
    asyncio.run(_scenario())
