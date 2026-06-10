"""
queue_daily.py — Plan and queue article jobs from the candidate pool.

Dry-run by default. Pass --execute to actually POST to the API.

Selection logic:
  1. Group all unwritten candidates by category.
  2. For each category with 0 existing articles AND 5+ candidates → recommend hero
     (bundles the top 7 by score into one roundup job).
  3. Remaining slots filled with the highest-score single-product-review candidates,
     max one per category per run (variety).
  4. Never picks two jobs from the same category in one run.

Usage:
  python queue_daily.py                             # dry-run, 2 jobs
  python queue_daily.py --count 3                   # dry-run, 3 jobs
  python queue_daily.py --execute                   # queue 2 jobs for real
  python queue_daily.py --count 3 --execute
  python queue_daily.py --api-url http://host:8000 --api-key mykey --execute
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx

# Import shared logic from suggest_articles (same scripts/ dir)
sys.path.insert(0, str(Path(__file__).parent))
from suggest_articles import (
    HERO_MAX_PRODUCTS,
    HERO_MIN_CANDIDATES,
    get_candidates,
    load_category_article_counts,
    recommend_article_type,
)

JSONL    = Path(__file__).parent.parent / "data" / "hot-products.jsonl"
SITE_KEY = "hus"


def _enc(s: str) -> str:
    return s.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)


def build_plan(count: int) -> list[dict]:
    """
    Return up to `count` job dicts:
      {"article_type": str, "product_urls": [str, ...], "reasoning": str, "category": str, "label": str}
    """
    candidates = get_candidates(show_all=False, min_score=0.0)
    if not candidates:
        return []

    cat_article_counts  = load_category_article_counts()

    # Group unwritten candidates by category name (lowercase)
    by_category: dict[str, list[tuple]] = defaultdict(list)
    for score, product, delta, is_new, exists in candidates:
        if exists:
            continue
        cat = (product.get("category_name") or "").lower()
        by_category[cat].append((score, product))

    # Pre-sort each category bucket by score desc (already sorted globally, but re-sort per bucket)
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x[0], reverse=True)

    plan: list[dict] = []
    used_categories: set[str] = set()

    # Pass 1: hero opportunities — categories with no existing articles and 5+ candidates
    for cat, bucket in sorted(by_category.items(), key=lambda kv: kv[1][0][0], reverse=True):
        if len(plan) >= count:
            break
        if cat in used_categories:
            continue
        existing = cat_article_counts.get(cat, 0)
        rec = recommend_article_type(cat, len(bucket), existing)
        if rec != "hero":
            continue

        top = bucket[:HERO_MAX_PRODUCTS]
        urls = [p.get("product_url", "") for _, p in top]
        names = [p.get("name", "") for _, p in top]
        label = f"HERO  {top[0][1].get('category_name', cat):<25}  {len(top)} products"
        reasoning = (
            f"Hero opportunity: {len(bucket)} unwritten candidates in '{cat}', "
            f"0 existing articles. Top products: {', '.join(names[:3])}..."
        )
        plan.append({
            "article_type": "hero",
            "product_urls": urls,
            "reasoning": reasoning,
            "category": cat,
            "label": label,
            "names": names,
        })
        used_categories.add(cat)

    # Pass 2: fill remaining slots with top single-product-review (one per category)
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
        if job["article_type"] == "hero":
            for j, (name, url) in enumerate(zip(job["names"], job["product_urls"]), 1):
                print(_enc(f"       {j}. {name}"))
                print(_enc(f"          {url}"))
        else:
            print(_enc(f"       {job['product_urls'][0]}"))
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
    parser.add_argument("--count",   type=int, default=2,                      help="Number of jobs to queue (default: 2)")
    parser.add_argument("--execute", action="store_true",                       help="Actually create jobs (default: dry-run)")
    parser.add_argument("--api-url", default="http://localhost:8000",           help="Trendly API base URL")
    parser.add_argument("--api-key", default="changeme",                        help="API key")
    args = parser.parse_args()

    if not JSONL.exists():
        print("No product data. Run: python fetch_hot_products.py --popular")
        sys.exit(1)

    plan = build_plan(args.count)
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
