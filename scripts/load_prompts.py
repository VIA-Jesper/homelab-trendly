"""
load_prompts.py - Create tables and load prompt files into the database.

Works with both SQLite (local) and Postgres (production).
Run this once before starting the pipeline for the first time,
and again whenever you update a prompt file.

Usage (from repo root):
    cd api && python ../scripts/load_prompts.py
"""

import asyncio
import sys
from pathlib import Path

# Add api/ to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, Base, engine


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Non-generate prompts: loaded as-is
PROMPT_FILES = {
    "optimize_seo":  PROMPTS_DIR / "optimize_v1.txt",
    "qa_review":     PROMPTS_DIR / "qa_v1.txt",
    "score_article": PROMPTS_DIR / "score_v1.txt",
}

# Generate prompts are assembled from base + per-type module.
# DB entry name: "generate_post_{article_type}" (hyphens → underscores).
# Legacy "generate_post" is kept pointing to single-product-review for backwards compat.
GENERATE_BASE = PROMPTS_DIR / "generate_base.txt"
GENERATE_TYPES = {
    "single_product_review": PROMPTS_DIR / "types" / "single-product-review.txt",
    "comparison":            PROMPTS_DIR / "types" / "comparison.txt",
    "hero":                  PROMPTS_DIR / "types" / "hero.txt",
}


def _assemble_generate_prompt(type_file: Path) -> str:
    base = GENERATE_BASE.read_text(encoding="utf-8")
    module = type_file.read_text(encoding="utf-8")
    return base + "\n\n" + module


async def create_tables() -> None:
    """Create all tables if they don't exist yet."""
    # Import models so Base knows about them
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables ready.")


async def _upsert_prompt(db: "AsyncSession", name: str, content: str) -> None:
    from models.prompt import Prompt
    result = await db.execute(
        select(Prompt).where(Prompt.name == name, Prompt.is_active.is_(True))
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.content = content
        print(f"  UPDATE  {name} (id: {existing.id})")
    else:
        db.add(Prompt(name=name, version="v1", content=content, is_active=True))
        print(f"  INSERT  {name}")


async def load_prompts() -> None:
    async with AsyncSessionLocal() as db:
        # Non-generate prompts
        for name, path in PROMPT_FILES.items():
            if not path.exists():
                print(f"  SKIP  {name} - file not found: {path}")
                continue
            await _upsert_prompt(db, name, path.read_text(encoding="utf-8"))

        # Generate prompts: base + type module assembled per type
        if not GENERATE_BASE.exists():
            print(f"  SKIP  generate prompts - base file not found: {GENERATE_BASE}")
        else:
            for type_key, type_file in GENERATE_TYPES.items():
                if not type_file.exists():
                    print(f"  SKIP  generate_post_{type_key} - type file not found: {type_file}")
                    continue
                content = _assemble_generate_prompt(type_file)
                await _upsert_prompt(db, f"generate_post_{type_key}", content)

            # Legacy alias: generate_post → single_product_review
            spr_file = GENERATE_TYPES.get("single_product_review")
            if spr_file and spr_file.exists():
                content = _assemble_generate_prompt(spr_file)
                await _upsert_prompt(db, "generate_post", content)

        await db.commit()
        print("Prompts loaded.")


async def main() -> None:
    print("Creating tables...")
    await create_tables()

    print("Loading prompts...")
    await load_prompts()

    print("\nDone. You can now start the API and create jobs.")


if __name__ == "__main__":
    asyncio.run(main())
