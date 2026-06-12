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
    related_articles,
    set_coverage_slug,
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


async def _related_scenario():
    engine, Session = await _new_db()
    async with Session() as db:
        site = Site(name="hus", domain="husforbegyndere.dk")
        db.add(site)
        await db.flush()

        # two same-category articles, both published (slug set)
        j1, slot1 = await _seed_job(db, site, _brief("pr_1", "Dreame X50"), "single-product-review")
        await set_coverage_slug(db, j1.id, "dreame-x50-test")
        j2, _ = await _seed_job(db, site, _brief("pr_2", "Roborock Q7"), "single-product-review")
        await set_coverage_slug(db, j2.id, "roborock-q7-test")
        # one not yet published (no slug) - must be excluded
        await _seed_job(db, site, _brief("pr_3", "Eufy X10"), "single-product-review")
        await db.commit()

        category_slug = slot1.split(":")[0]  # the true category prefix of the slot_key

        rel = await related_articles(db, site.id, category_slug, exclude_job_id=j1.id)
        slugs = {r["slug"] for r in rel}
        assert "roborock-q7-test" in slugs       # other published article in category
        assert "dreame-x50-test" not in slugs    # excluded (it is the current job)
        assert all(r["slug"] for r in rel)        # no unpublished (null-slug) rows
        assert len(rel) == 1
    await engine.dispose()


def test_related_articles_cluster():
    asyncio.run(_related_scenario())
