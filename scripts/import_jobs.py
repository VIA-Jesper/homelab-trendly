"""
import_jobs.py — Import exported jobs from a worker instance into the authority DB.

Run this on the AUTHORITY machine after copying remote-jobs.json from a worker.
Creates minimal job records (status=complete) so the authority's suggest_articles.py
correctly excludes those products from future suggestions.

Does NOT re-run the pipeline — this is purely for dedup tracking.

Usage:
  # Import all jobs from remote-jobs.json
  python scripts/import_jobs.py

  # Specify a different export file
  python scripts/import_jobs.py --input my-worker-jobs.json

  # Dry-run — show what would be imported without writing
  python scripts/import_jobs.py --dry-run
"""

import argparse
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT       = Path(__file__).parent.parent
DB_PATH    = ROOT / "trendly_local.db"
INPUT_FILE = ROOT / "remote-jobs.json"
SITE_KEY   = "hus"


def get_site_id(con: sqlite3.Connection) -> str:
    cur = con.cursor()
    cur.execute("SELECT id FROM sites WHERE key = ? OR name LIKE ?", (SITE_KEY, "%Hus%"))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"Site '{SITE_KEY}' not found in DB. "
            "Make sure the authority DB is initialised (docker-compose up ran at least once)."
        )
    return row[0]


def already_known(con: sqlite3.Connection, product_ids: set[str], product_names: set[str]) -> bool:
    """Return True if any of the given product IDs or names are already in the DB."""
    cur = con.cursor()
    cur.execute("SELECT context FROM jobs")
    for (ctx_raw,) in cur.fetchall():
        try:
            ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else (ctx_raw or {})
            brief = ctx.get("brief") or {}

            # Check single product URL
            url = ctx.get("product_url") or brief.get("affiliate_url", "")
            m = re.search(r'/pl/\d+-(\d+)', url)
            if m and m.group(1) in product_ids:
                return True

            name = (brief.get("product_name") or "").strip().lower()
            if name and name in product_names:
                return True

            # Check hero/comparison products list
            for p in (brief.get("products") or []):
                purl = p.get("affiliate_url", "")
                m2 = re.search(r'/pl/\d+-(\d+)', purl)
                if m2 and m2.group(1) in product_ids:
                    return True
                pname = (p.get("name") or "").strip().lower()
                if pname and pname in product_names:
                    return True
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    return False


def build_context(job: dict) -> dict:
    """Build a minimal context blob that suggest_articles.py can read for dedup."""
    names = job.get("product_names", [])
    urls  = job.get("product_urls", [])

    if job.get("article_type") == "hero" or len(urls) > 1:
        # Hero / comparison — store as products list in brief
        return {
            "article_type": job.get("article_type", "hero"),
            "brief": {
                "category": job.get("category", ""),
                "products": [
                    {"name": n, "affiliate_url": u}
                    for n, u in zip(names, urls)
                ],
            },
        }
    else:
        return {
            "article_type": job.get("article_type", "single-product-review"),
            "product_url": urls[0] if urls else "",
            "brief": {
                "category": job.get("category", ""),
                "product_name": names[0] if names else "",
            },
        }


def main():
    parser = argparse.ArgumentParser(description="Import worker jobs into the authority DB")
    parser.add_argument("--input",   default=str(INPUT_FILE), help="Path to exported JSON (default: remote-jobs.json)")
    parser.add_argument("--dry-run", action="store_true",     help="Show what would be imported, don't write")
    args = parser.parse_args()

    src = Path(args.input)
    if not src.exists():
        print(f"Input file not found: {src}")
        print("Run export_jobs.py on the worker first.")
        return

    if not DB_PATH.exists():
        print(f"No DB at {DB_PATH}. Make sure the authority API has been started at least once.")
        return

    data = json.loads(src.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    print(f"Input: {len(jobs)} jobs from {src.name} (exported {data.get('exported_at', '?')})")

    if args.dry_run:
        print("\nDry-run — nothing will be written.\n")

    con = sqlite3.connect(str(DB_PATH))
    try:
        site_id = get_site_id(con)

        imported = 0
        skipped  = 0

        for j in jobs:
            pids   = set(j.get("product_ids", []))
            pnames = {n.strip().lower() for n in j.get("product_names", [])}

            # Add IDs extracted from URLs (belt-and-suspenders)
            for u in j.get("product_urls", []):
                m = re.search(r'/pl/\d+-(\d+)', u)
                if m:
                    pids.add(m.group(1))

            if already_known(con, pids, pnames):
                print(f"  SKIP (already in DB): {j.get('category')} — {', '.join(j.get('product_names', [])[:2])}")
                skipped += 1
                continue

            ctx     = build_context(j)
            job_id  = str(uuid.uuid4()).replace("-", "")
            now     = datetime.now(timezone.utc).isoformat()
            reason  = j.get("reasoning", f"Imported from {src.name}")

            names_preview = ", ".join(j.get("product_names", [])[:2])
            if len(j.get("product_names", [])) > 2:
                names_preview += f" +{len(j['product_names'])-2}"

            print(f"  IMPORT: {j.get('category'):<35} {names_preview}")

            if not args.dry_run:
                con.execute(
                    "INSERT INTO jobs (id, site_id, status, context, reasoning, created_at, updated_at) "
                    "VALUES (?, ?, 'complete', ?, ?, ?, ?)",
                    (job_id, site_id, json.dumps(ctx, ensure_ascii=False), reason, now, now),
                )
                con.commit()

            imported += 1

    finally:
        con.close()

    print()
    if args.dry_run:
        print(f"Dry-run: would import {imported}, skip {skipped}.")
    else:
        print(f"Done: imported {imported}, skipped {skipped} (already in DB).")
