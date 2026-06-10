"""
export_jobs.py — Export queued/published jobs from this instance's DB.

Run on the REMOTE instance, commit the output, and push. The primary instance
reads remote-jobs.json when regenerating queue-remote.json to avoid duplicates.

Usage:
  python scripts/export_jobs.py
  # → writes remote-jobs.json to repo root

  python scripts/export_jobs.py --out path/to/file.json
"""

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT    = Path(__file__).parent.parent
DB_PATH = ROOT / "trendly_local.db"
DEFAULT_OUT = ROOT / "remote-jobs.json"


def main():
    parser = argparse.ArgumentParser(description="Export this instance's job list for sync back to primary")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output path (default: remote-jobs.json)")
    args = parser.parse_args()

    out = Path(args.out)

    if not DB_PATH.exists():
        print(f"No DB at {DB_PATH} — nothing to export.")
        return

    jobs = []
    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT id, status, context, created_at FROM jobs WHERE status NOT IN ('archived')")
        for job_id, status, ctx_raw, created_at in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                brief = ctx.get("brief") or {}
                category = brief.get("category", "")

                # Collect product URLs and names from context
                product_urls: list[str] = []
                product_names: list[str] = []

                # Single product
                url = ctx.get("product_url") or brief.get("affiliate_url", "")
                name = brief.get("product_name", "")
                if url:
                    product_urls.append(url)
                if name:
                    product_names.append(name)

                # Hero / comparison — list of products in brief.products
                for p in (brief.get("products") or []):
                    purl = p.get("affiliate_url", "")
                    pname = p.get("name", "")
                    if purl and purl not in product_urls:
                        product_urls.append(purl)
                    if pname and pname not in product_names:
                        product_names.append(pname)

                # Also extract IDs from URLs for robust dedup
                product_ids = []
                for u in product_urls:
                    m = re.search(r'/pl/\d+-(\d+)', u)
                    if m:
                        product_ids.append(m.group(1))

                if not product_urls and not product_names:
                    continue

                jobs.append({
                    "job_id":        job_id,
                    "status":        status,
                    "category":      category,
                    "product_urls":  product_urls,
                    "product_names": product_names,
                    "product_ids":   product_ids,
                    "created_at":    created_at,
                })
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    output = {
        "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "instance":    "remote",
        "job_count":   len(jobs),
        "jobs":        jobs,
    }

    out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Exported {len(jobs)} jobs to {out}")
    print()
    cats = {}
    for j in jobs:
        cats[j["category"]] = cats.get(j["category"], 0) + 1
    for cat, count in sorted(cats.items()):
        print(f"  {cat:<40} {count} job(s)")
