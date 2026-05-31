from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

_REPO_ROOT = Path(__file__).parent.parent


def _resolve_db_url(url: str) -> str:
    # Anchor relative SQLite paths to the repo root so CWD never matters.
    # e.g. sqlite+aiosqlite:///./trendly_local.db → absolute path
    prefix = "sqlite+aiosqlite:///"
    if url.startswith(prefix):
        path_part = url[len(prefix):]
        resolved = (_REPO_ROOT / path_part).resolve()
        return f"{prefix}{resolved}"
    return url


engine = create_async_engine(_resolve_db_url(settings.database_url), echo=(settings.log_level == "DEBUG"))

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
