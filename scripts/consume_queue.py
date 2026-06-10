"""
consume_queue.py — Seed a remote Trendly instance from queue-remote.json.

Reads the curated job list from queue-remote.json (repo root) and POSTs
each job to the remote API. Skip jobs that already exist in the remote DB
by checking against already-queued product names.

Usage:
  # Dry-run (default) — show what would be queued
  python scripts/consume_queue.py

  # Execute — actually create the jobs
  python scripts/consume_queue.py --execute

  # Limit to first N jobs (default: all)
  python scripts/consume_queue.py --limit 5 --execute

  # Point at a non-default API
  python scripts/consume_queue.py --api-url http://my-remote:8000 --api-key mykey --execute
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

QUEUE_FILE = Path(__file__).parent.parent / "queue-remote.json"
SITE_KEY   = "hus"


def _enc(s: str) -> str:
    return s.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)


def load_queue(limit: int | None = None) -> list[dict]:
    if not QUEUE_FILE.exists():
        print(f"Queue file not found: {QUEUE_FILE}")
        sys.exit(1)
    data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    print(f"Queue: {len(jobs)} jobs (generated {data.get('generated_at', '?')})")
    return jobs[:limit] if limit else jobs


def print_plan(jobs: list[dict]):
    print()
    for j in jobs:
        atype  = "HERO  " if j["article_type"] == "hero" else "SINGLE"
        names  = ", ".join(j["product_names"][:2])
        if len(j["product_names"]) > 2:
            names += f" +{len(j['product_names'])-2}"
        print(_enc(f"  {j['priority']:>2}. {atype}  {j['category']:<35} {names[:50]}"))
    print()


def execute(jobs: list[dict], api_url: str, api_key: str):
    base    = api_url.rstrip("/")
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    for j in jobs:
        payload = {
            "site_key":    SITE_KEY,
            "article_type": j["article_type"],
            "product_urls": j["product_urls"],
            "reasoning":   j["reasoning"],
        }
        print(_enc(f"  Queuing {j['priority']:>2}: {j['category']} ({j['article_type']})"))
        try:
            r = httpx.post(
                f"{base}/api/v1/jobs/from-products",
                json=payload,
                headers=headers,
                timeout=30,
            )
            if r.status_code in (200, 201):
                data = r.json()
                print(f"    → job_id: {data.get('job_id')}  status: {data.get('status')}")
            else:
                print(f"    → ERROR {r.status_code}: {r.text[:200]}")
        except httpx.RequestError as e:
            print(f"    → REQUEST ERROR: {e}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Seed a remote Trendly instance from queue-remote.json")
    parser.add_argument("--execute",  action="store_true",                     help="Actually create the jobs (default: dry-run)")
    parser.add_argument("--limit",    type=int, default=None,                  help="Only process first N jobs")
    parser.add_argument("--api-url",  default="http://localhost:8000",         help="Trendly API base URL")
    parser.add_argument("--api-key",  default="changeme",                      help="API key")
    args = parser.parse_args()

    jobs = load_queue(args.limit)
    print_plan(jobs)

    if args.execute:
        print("Executing...\n")
        execute(jobs, args.api_url, args.api_key)
        print("Done.")
    else:
        print(f"Dry-run. Pass --execute to queue these {len(jobs)} jobs.")
        print(f"  python scripts/consume_queue.py --execute --api-url {args.api_url} --api-key {args.api_key}")


if __name__ == "__main__":
    main()
