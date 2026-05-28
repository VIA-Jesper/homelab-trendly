"""
SQLite state database for the TestFlow pipeline.
Tracks pipeline runs, review attempts, and published articles.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("testflow_state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          TEXT PRIMARY KEY,
    site_name       TEXT NOT NULL,
    topic           TEXT NOT NULL,
    keyword         TEXT NOT NULL,
    category_id     INTEGER NOT NULL,
    article_type    TEXT NOT NULL,
    status          TEXT NOT NULL,
    post_id         INTEGER,
    post_url        TEXT,
    duration_sec    REAL,
    total_phases    INTEGER,
    estimated_cost  REAL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    phase       TEXT NOT NULL,
    attempt     INTEGER NOT NULL,
    passed      INTEGER NOT NULL,
    score       REAL,
    feedback    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS published_articles (
    post_id      INTEGER PRIMARY KEY,
    site_name    TEXT NOT NULL,
    run_id       TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    title        TEXT NOT NULL,
    slug         TEXT NOT NULL,
    keyword      TEXT NOT NULL,
    category_id  INTEGER NOT NULL,
    article_type TEXT NOT NULL,
    published_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def record_run(
    run_id: str, site_name: str, topic: str, keyword: str,
    category_id: int, article_type: str, status: str,
    post_id: int | None = None, post_url: str | None = None,
    duration_sec: float | None = None,
) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO pipeline_runs
               (run_id, site_name, topic, keyword, category_id, article_type, status, post_id, post_url, duration_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run_id, site_name, topic, keyword, category_id, article_type, status, post_id, post_url, duration_sec),
        )


def record_review_attempt(
    run_id: str, phase: str, attempt: int, passed: bool, score: float | None, feedback: str | None
) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO review_attempts (run_id, phase, attempt, passed, score, feedback)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, phase, attempt, int(passed), score, feedback),
        )


def record_published_article(
    post_id: int, site_name: str, run_id: str, title: str,
    slug: str, keyword: str, category_id: int, article_type: str,
) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO published_articles
               (post_id, site_name, run_id, title, slug, keyword, category_id, article_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (post_id, site_name, run_id, title, slug, keyword, category_id, article_type),
        )


def get_published_titles(site_name: str, limit: int = 50) -> list[str]:
    """Return titles of published articles for internal linking context."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT title FROM published_articles WHERE site_name = ? ORDER BY published_at DESC LIMIT ?",
            (site_name, limit),
        ).fetchall()
    return [row["title"] for row in rows]


def get_published_count(site_name: str, since_days: int = 7) -> int:
    """Return number of articles published in the last N days."""
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM published_articles
               WHERE site_name = ? AND published_at >= datetime('now', ?)""",
            (site_name, f"-{since_days} days"),
        ).fetchone()
    return row["cnt"] if row else 0
