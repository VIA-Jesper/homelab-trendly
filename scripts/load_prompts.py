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

PROMPT_FILES = {
    "generate_post": PROMPTS_DIR / "generate_v1.txt",
    "optimize_seo":  PROMPTS_DIR / "optimize_v1.txt",
    "qa_review":     PROMPTS_DIR / "qa_v1.txt",
}


async def create_tables() -> None:
    """Create all tables if they don't exist yet."""
    # Import models so Base knows about them
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables ready.")


async def load_prompts() -> None:
    from models.prompt import Prompt

    async with AsyncSessionLocal() as db:
        for name, path in PROMPT_FILES.items():
            if not path.exists():
                print(f"  SKIP  {name} - file not found: {path}")
                continue

            content = path.read_text(encoding="utf-8")

            # Check if active prompt already exists
            result = await db.execute(
                select(Prompt).where(
                    Prompt.name == name,
                    Prompt.is_active.is_(True),
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.content = content
                print(f"  UPDATE  {name} (id: {existing.id})")
            else:
                prompt = Prompt(name=name, version="v1", content=content, is_active=True)
                db.add(prompt)
                print(f"  INSERT  {name}")

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
