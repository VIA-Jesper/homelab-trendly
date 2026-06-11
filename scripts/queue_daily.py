"""
queue_daily.py — Plan and queue article jobs from the candidate pool.

Dry-run by default. Pass --execute to actually POST to the API.

Selection logic:
  Pass 0: pick up to 1 comparison if any category has 2+ existing singles AND
          a fresh product pair is available. Strengthens content clusters.
  Pass 1: fill remaining slots with the highest-score single-product-review
          candidates, max one per category per run (variety).
  Never picks two jobs from the same category in one run.

Hero is no longer auto-queued — see brain/inbox/2026-06-10-trendly-scaling-plan.md.
Use the API directly or queue-remote.json if a hero roundup is wanted manually.

Usage:
  python queue_daily.py                             # dry-run, 2 jobs
  python queue_daily.py --count 3                   # dry-run, 3 jobs
  python queue_daily.py --execute                   # queue 2 jobs for real
  python queue_daily.py --count 3 --execute
  python queue_daily.py --api-url http://host:8000 --api-key mykey --execute
  python queue_daily.py --no-comparisons            # singles only (skip Pass 0)
"""

import argparse
import sys
from pathlib import Path

import httpx

# Import shared logic from suggest_articles (same scripts/ dir)
sys.path.insert(0, str(Path(__file__).parent))
from suggest_articles import get_candidates, get_comparison_candidates

JSONL    = Path(__file__).parent.parent / "data" / "hot-products.jsonl"
SITE_KEY = "hus"


def _enc(s: str) -> str:
    return s.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)


def build_plan(count: int, include_comparisons: bool = True) -> list[dict]:
    """
    Return up to `count` job dicts:
      {"article_type": str, "product_urls": [str, ...], "reasoning": str, "category": str, "label": str}
    """
    plan: list[dict] = []
    used_categories: set[str] = set()

    # Pass 0: at most one comparison per run, pulled from categories with 2+ singles.
    if include_comparisons and count > 0:
        for cand in get_comparison_candidates():
            cat = cand["category"]
            if cat in used_categories:
                continue
            names = cand["names"]
            label = f"COMPARE {cat:<23}  {names[0]}  vs  {names[1]}"
            reasoning = (
                f"Comparison opportunity: '{cat}' has 2+ existing singles. "
                f"Pair score {cand['score']:.1f}."
            )
            plan.append({
                "article_type": "comparison",
                "product_urls": cand["product_urls"],
                "reasoning": reasoning,
                "category": cat,
                "label": label,
                "names": names,
            })
            used_categories.add(cat)
            break

    candidates = get_candidates(show_all=False, min_score=0.0)
    if not candidates and len(plan) == 0:
        return []

    # Pass 1: fill remaining slots with top single-product-review (one per category)
    for score, product, delta, is_new, exists in candidates:
        if len(plan) >= count:
            break
        if exists:
            continue
        cat = (product.get("category_name") or "").lower()
        if cat in used_categories:
            continue

        url   = product.get("product_url", "")
        name  = product.get("name", "")
        price = product.get("price_dkk")
        watch = product.get("watchers") or "-"
        rank  = product.get("rank") or "?"
        cat_display = product.get("category_name", cat)
        price_str = f"{price:,.0f} kr" if price else "?"

        label = f"SINGLE  {cat_display:<23}  {watch:<7}  rank {rank}  {price_str:>10}  {name}"
        reasoning = f"Score {score:.1f} — rank {rank}, {watch} watchers, {price_str}"

        plan.append({
            "article_type": "single-product-review",
            "product_urls": [url],
            "reasoning": reasoning,
            "category": cat,
            "label": label,
            "names": [name],
        })
        used_categories.add(cat)

    return plan


def print_plan(plan: list[dict]):
    print("\n=== Daily Queue Plan ===\n")
    if not plan:
        print("No candidates found. Run fetch_hot_products.py --popular first.")
        return
    for i, job in enumerate(plan, 1):
        print(_enc(f"  {i}. {job['label']}"))
        for url in job["product_urls"]:
            print(_enc(f"       {url}"))
    print()


def execute_plan(plan: list[dict], api_url: str, api_key: str):
    base = api_url.rstrip("/")
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}

    for job in plan:
        payload = {
            "site_key": SITE_KEY,
            "article_type": job["article_type"],
            "product_urls": job["product_urls"],
            "reasoning": job["reasoning"],
        }
        print(_enc(f"  Queuing: {job['label']}"))
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
    parser = argparse.ArgumentParser(description="Plan and queue daily article jobs")
    parser.add_argument("--count",          type=int, default=2,                  help="Number of jobs to queue (default: 2)")
    parser.add_argument("--execute",        action="store_true",                   help="Actually create jobs (default: dry-run)")
    parser.add_argument("--api-url",        default="http://localhost:8000",       help="Trendly API base URL")
    parser.add_argument("--api-key",        default="changeme",                    help="API key")
    parser.add_argument("--no-comparisons", action="store_true",                   help="Skip Pass 0 (singles only)")
    args = parser.parse_args()

    if not JSONL.exists():
        print("No product data. Run: python fetch_hot_products.py --popular")
        sys.exit(1)

    plan = build_plan(args.count, include_comparisons=not args.no_comparisons)
    print_plan(plan)

    if not plan:
        sys.exit(0)

    if args.execute:
        print("Executing plan...\n")
        execute_plan(plan, args.api_url, args.api_key)
        print("Done.")
    else:
        print("Dry-run. Pass --execute to queue these jobs.")
        print(f"  python queue_daily.py --count {args.count} --execute --api-url {args.api_url} --api-key {args.api_key}")


if __name__ == "__main__":
    main()
