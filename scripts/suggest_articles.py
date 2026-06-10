"""
suggest_articles.py — Surface article candidates from hot-products.jsonl.

Reads the latest snapshot per product, scores on rank + watchers, filters out
products already in the DB, and prints ranked candidates with recommended
article type.

Composite score:
  rank_score    = max(0, 11 - rank)   → rank 1 = 10pts, rank 10 = 1pt
  watcher_score → 1000+ = 4, 500+ = 3, 200+ = 2, 100+ = 1.5, 50+ = 1, none = 0
  composite     = rank_score + watcher_score

Article type recommendation:
  hero              — category has 0 existing articles AND 5+ unwritten candidates
  single-product-review — everything else

Usage:
  python suggest_articles.py                   # top 20 new candidates
  python suggest_articles.py --limit 10
  python suggest_articles.py --min-score 5
  python suggest_articles.py --show-all        # include already-written products
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).parent.parent
JSONL   = ROOT / "data" / "hot-products.jsonl"
DB_PATH = ROOT / "trendly_local.db"

WATCHER_SCORES = {"1000": 4.0, "500": 3.0, "200": 2.0, "100": 1.5, "50": 1.0}

# Minimum products per category before a hero is suggested instead of singles.
HERO_MIN_CANDIDATES = 5
HERO_MAX_PRODUCTS   = 7   # bundle size passed to the API


def _watcher_score(watchers: str) -> float:
    val = (watchers or "").replace("+", "").strip()
    return WATCHER_SCORES.get(val, 0.0)


def _rank_score(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return max(0.0, 11.0 - rank)


def composite_score(product: dict) -> float:
    return _rank_score(product.get("rank")) + _watcher_score(product.get("watchers", ""))


def load_snapshots() -> tuple[dict[str, dict], dict[str, dict]]:
    """Returns (latest, previous) snapshot dicts keyed by product ID."""
    history: dict[str, list[dict]] = defaultdict(list)
    with JSONL.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            fetched_for = p.get("fetched_for", "UNKNOWN")
            if fetched_for is None:
                continue
            pid = p.get("id")
            if pid:
                history[pid].append(p)

    latest, previous = {}, {}
    for pid, entries in history.items():
        entries.sort(key=lambda x: x.get("fetched_at", ""))
        latest[pid] = entries[-1]
        if len(entries) >= 2:
            previous[pid] = entries[-2]

    return latest, previous


def load_known_products() -> tuple[set[str], set[str]]:
    """Returns (known_ids, known_names) from existing jobs in the DB."""
    known_ids: set[str] = set()
    known_names: set[str] = set()
    if not DB_PATH.exists():
        return known_ids, known_names

    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT context FROM jobs")
        for (ctx_raw,) in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                url = ctx.get("product_url", "")
                m = re.search(r'/pl/\d+-(\d+)', url)
                if m:
                    known_ids.add(m.group(1))
                name = (ctx.get("brief") or {}).get("product_name", "")
                if name:
                    known_names.add(name.strip().lower())
                # Also check products list inside brief (hero/comparison jobs)
                for prod in ((ctx.get("brief") or {}).get("products") or []):
                    pname = prod.get("name", "")
                    if pname:
                        known_names.add(pname.strip().lower())
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return known_ids, known_names


def load_category_article_counts() -> dict[str, int]:
    """Returns {category_slug: job_count} for non-archived jobs, keyed by brief.category."""
    counts: dict[str, int] = {}
    if not DB_PATH.exists():
        return counts

    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT context FROM jobs WHERE status NOT IN ('archived')")
        for (ctx_raw,) in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                cat = ((ctx.get("brief") or {}).get("category") or "").strip().lower()
                if cat:
                    counts[cat] = counts.get(cat, 0) + 1
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return counts


def is_known(product: dict, known_ids: set[str], known_names: set[str]) -> bool:
    if product.get("id") in known_ids:
        return True
    return (product.get("name") or "").strip().lower() in known_names


def rising_delta(pid: str, latest: dict, previous: dict) -> int | None:
    prev = previous.get(pid)
    if not prev:
        return None
    r_now  = latest[pid].get("rank")
    r_prev = prev.get("rank")
    if r_now is None or r_prev is None:
        return None
    return r_prev - r_now


def recommend_article_type(
    category_name: str,
    unwritten_in_category: int,
    existing_in_category: int,
) -> str:
    """
    hero               — 0 existing articles for this category AND 5+ unwritten candidates
    single-product-review — everything else
    """
    cat = category_name.lower()
    if existing_in_category == 0 and unwritten_in_category >= HERO_MIN_CANDIDATES:
        return "hero"
    return "single-product-review"


def get_candidates(
    show_all: bool = False,
    min_score: float = 0.0,
) -> list[tuple[float, dict, int | None, bool, bool]]:
    """
    Return sorted candidate list: [(score, product, delta, is_new, exists), ...]
    Callers (queue_daily.py) import this directly.
    """
    if not JSONL.exists():
        return []

    latest, previous = load_snapshots()
    known_ids, known_names = load_known_products()

    candidates = []
    for pid, product in latest.items():
        exists = is_known(product, known_ids, known_names)
        if exists and not show_all:
            continue
        score = composite_score(product)
        if score < min_score:
            continue
        delta    = rising_delta(pid, latest, previous)
        is_new   = pid not in previous
        candidates.append((score, product, delta, is_new, exists))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates


def _fmt_delta(delta: int | None, is_new: bool) -> str:
    if is_new:
        return "NEW"
    if delta is None:
        return "-"
    if delta > 0:
        return f"+{delta}"
    if delta < 0:
        return f"{delta}"
    return "="


def _print_row(i: int, product: dict, score: float, delta: int | None, is_new: bool, exists: bool, rec_type: str | None):
    name     = (product.get("name") or "")
    cat      = (product.get("category_name") or "")[:20]
    watchers = product.get("watchers") or "-"
    rank     = product.get("rank") or "?"
    price    = product.get("price_dkk")
    price_str = f"{price:,.0f} kr" if price else "?"
    delta_str = _fmt_delta(delta, is_new)
    exists_tag = " [EXISTS]" if exists else ""
    type_tag   = f"  [{rec_type}]" if rec_type else ""

    line = (
        f"{i:>3}  {score:>5.1f}  {delta_str:>5}  {watchers:<7} {str(rank):>4}  "
        f"{cat:<20}  {price_str:>10}  {name}{exists_tag}{type_tag}"
    )
    url_line = f"     {product.get('product_url', '')}"
    print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))
    print(url_line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))


def main():
    parser = argparse.ArgumentParser(
        description="Surface article candidates ranked by composite hot-product score"
    )
    parser.add_argument("--limit",          type=int,   default=20)
    parser.add_argument("--min-score",      type=float, default=0.0)
    parser.add_argument("--show-all",       action="store_true")
    parser.add_argument("--recommend-type", action="store_true",
                        help="Show article type recommendation per candidate")
    args = parser.parse_args()

    if not JSONL.exists():
        print(f"No data at {JSONL}. Run fetch_hot_products.py --site-only first.")
        sys.exit(1)

    candidates = get_candidates(show_all=args.show_all, min_score=args.min_score)
    skipped    = len(load_snapshots()[0]) - len(candidates) if not args.show_all else 0

    # Build per-category counts for type recommendation
    cat_article_counts: dict[str, int] = {}
    cat_candidate_counts: dict[str, int] = defaultdict(int)
    rec_types: dict[str, str] = {}

    if args.recommend_type:
        cat_article_counts = load_category_article_counts()
        for _, product, _, _, exists in candidates:
            if not exists:
                cat_name = (product.get("category_name") or "").lower()
                cat_candidate_counts[cat_name] += 1
        for _, product, _, _, exists in candidates:
            cat_name = (product.get("category_name") or "").lower()
            pid = product.get("id", "")
            rec_types[pid] = recommend_article_type(
                cat_name,
                unwritten_in_category=cat_candidate_counts.get(cat_name, 0),
                existing_in_category=cat_article_counts.get(cat_name, 0),
            )

    print(f"\n=== Trendly Article Candidates ===")
    total_in_snapshot = len(load_snapshots()[0])
    print(f"Snapshot products: {total_in_snapshot}  |  Already in DB: {skipped}  |  Candidates: {len(candidates)}")
    print(f"\n{'#':>3}  {'Score':>5}  {'Rise':>5}  {'Watch':<7} {'Rank':>4}  {'Category':<20}  {'Price':>10}  Name")
    print("-" * 115)

    for i, (score, product, delta, is_new, exists) in enumerate(candidates[:args.limit], 1):
        pid      = product.get("id", "")
        rec_type = rec_types.get(pid) if args.recommend_type else None
        _print_row(i, product, score, delta, is_new, exists, rec_type)

    if not candidates:
        print("\nNo candidates. Try --show-all or run fetch_hot_products.py --site-only first.")


if __name__ == "__main__":
    main()
