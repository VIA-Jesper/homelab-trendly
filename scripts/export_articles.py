"""
export_articles.py - Export generated article CONTENT for import into another system.

Unlike export_jobs.py (which exports only queue metadata for dedup sync), this pulls
the finished article body + SEO + product/affiliate data + score + QA verdict for each
job, so the output is portable content you can import elsewhere.

For each job it takes the best available content: the QA-corrected article if the
qa_review retry produced one, else the optimize_seo output, else the write_draft output
(same precedence the publish route uses).

Usage (from repo root):
  .venv\\Scripts\\python.exe scripts\\export_articles.py
  # -> writes exports/articles-<timestamp>.json AND exports/md/<slug>.md per article

  .venv\\Scripts\\python.exe scripts\\export_articles.py --status complete   # only finished jobs
  .venv\\Scripts\\python.exe scripts\\export_articles.py --out exports/mybatch.json
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "trendly_local.db"
EXPORT_DIR = ROOT / "exports"


def _slugify(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_ " else "" for c in (s or "").lower())
    return "-".join(keep.split()) or "article"


def _parse_json(raw: str | None) -> dict | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        raw = "\n".join(lines[1:end]).strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def _best_content(ctx: dict, steps: dict) -> tuple[dict | None, str]:
    """Return (content_dict, source) using publish-route precedence."""
    qa_corrected = ctx.get("qa_corrected")
    if qa_corrected and qa_corrected.get("article"):
        return qa_corrected, "qa_corrected"
    for name in ("optimize_seo", "write_draft"):
        d = _parse_json(steps.get(name))
        if d and d.get("article"):
            return d, name
    return None, "none"


def main():
    ap = argparse.ArgumentParser(description="Export generated article content for external import")
    ap.add_argument("--status", default=None, help="Only export jobs with this status (e.g. complete)")
    ap.add_argument("--out", default=None, help="JSON output path (default: exports/articles-<ts>.json)")
    ap.add_argument("--no-md", action="store_true", help="Skip writing per-article markdown files")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"No DB at {DB_PATH}")
        return

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    EXPORT_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else EXPORT_DIR / f"articles-{ts}.json"

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    articles = []
    try:
        if args.status:
            job_rows = con.execute(
                "SELECT id, status, context, created_at FROM jobs WHERE status = ?", (args.status,)
            ).fetchall()
        else:
            job_rows = con.execute(
                "SELECT id, status, context, created_at FROM jobs WHERE status != 'archived'"
            ).fetchall()

        for j in job_rows:
            ctx = json.loads(j["context"]) if isinstance(j["context"], str) else (j["context"] or {})
            brief = ctx.get("brief") or {}
            steps = {
                r["step_name"]: r["output"]
                for r in con.execute(
                    "SELECT step_name, output FROM steps WHERE job_id = ? AND status = 'complete'", (j["id"],)
                ).fetchall()
            }
            content, source = _best_content(ctx, steps)
            if not content:
                continue

            seo = content.get("seo", {}) or {}
            body = content.get("article", "")
            score = _parse_json(steps.get("score_article"))
            qa_raw = (steps.get("qa_review") or "")
            products = [
                {"name": p.get("name"), "affiliate_url": p.get("affiliate_url"),
                 "price_kr": p.get("price_kr"), "id": p.get("id")}
                for p in (brief.get("products") or [])
            ]
            articles.append({
                "job_id": j["id"],
                "status": j["status"],
                "article_type": brief.get("article_type") or ctx.get("article_type"),
                "category": brief.get("category", ""),
                "title": seo.get("title", ""),
                "slug": seo.get("slug", ""),
                "meta_description": seo.get("description", ""),
                "focus_keyword": seo.get("focus_keyword", ""),
                "body_markdown": body,
                "word_count": len(body.split()),
                "products": products,
                "placements": content.get("placements", []),
                "score": score,
                "qa_passed": "PASS" in qa_raw.upper(),
                "content_source": source,
                "created_at": j["created_at"],
            })
    finally:
        con.close()

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": articles,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(articles)} article(s) -> {out_path}")

    if not args.no_md and articles:
        md_dir = EXPORT_DIR / "md"
        md_dir.mkdir(parents=True, exist_ok=True)
        for a in articles:
            fm = {
                "title": a["title"], "slug": a["slug"],
                "description": a["meta_description"], "focus_keyword": a["focus_keyword"],
                "category": a["category"], "article_type": a["article_type"],
                "qa_passed": a["qa_passed"], "word_count": a["word_count"],
                "products": [p["name"] for p in a["products"]],
            }
            front = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items())
            fname = f"{_slugify(a['slug'] or a['title'])}.md"
            (md_dir / fname).write_text(f"---\n{front}\n---\n\n{a['body_markdown']}\n", encoding="utf-8")
        print(f"Wrote {len(articles)} markdown file(s) -> {md_dir}")


if __name__ == "__main__":
    main()
