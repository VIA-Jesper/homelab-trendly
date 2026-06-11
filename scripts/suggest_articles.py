"""
suggest_articles.py - Surface article candidates from hot-products.jsonl.

Reads the latest snapshot per product, scores on rank + watchers, filters out
products already in the DB, and prints ranked candidates with recommended
article type.

Composite score:
  rank_score    = max(0, 11 - rank)   → rank 1 = 10pts, rank 10 = 1pt
  watcher_score → 1000+ = 4, 500+ = 3, 200+ = 2, 100+ = 1.5, 50+ = 1, none = 0
  composite     = rank_score + watcher_score

Article type recommendation (single-product candidates):
  single-product-review - every unwritten product. Hero auto-recommendation retired
                          2026-06-10 (see brain/inbox/2026-06-10-trendly-scaling-plan.md).

Comparison opportunities (separate pool from single candidates):
  get_comparison_candidates() returns (category, product pair) tuples for
  categories that already have 2+ singles published. Used by queue_daily.py to
  build a comparison Pass 0.

Usage:
  python suggest_articles.py                   # top 20 new candidates
  python suggest_articles.py --limit 10
  python suggest_articles.py --min-score 5
  python suggest_articles.py --show-all        # include already-written products
  python suggest_articles.py --comparisons     # list eligible comparison pairs
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

# Shared canonical de-dup key (pure module; imported by file path to avoid the
# api `services` package __init__, which pulls in config/DB).
sys.path.insert(0, str(ROOT / "api" / "services"))
from dedup import canonical_product_key  # noqa: E402

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


def load_known_keys() -> set[str]:
    """
    Returns canonical product keys (see api/services/dedup.py) for every product
    already referenced by a job in the DB. Using the same key the API gate uses
    means planning agrees with creation - and catches name variants the old
    exact-string match missed.
    """
    keys: set[str] = set()
    if not DB_PATH.exists():
        return keys

    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT context FROM jobs")
        for (ctx_raw,) in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                for prod in ((ctx.get("brief") or {}).get("products") or []):
                    keys.add(canonical_product_key(
                        prod.get("name", ""),
                        pid=prod.get("id"),
                        url=prod.get("affiliate_url") or prod.get("product_url"),
                    ))
                top_url = ctx.get("product_url")
                if top_url:
                    keys.add(canonical_product_key("", url=top_url))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return keys


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


def load_written_singles_by_category() -> dict[str, list[dict]]:
    """
    Returns {category_slug: [{"id": pid, "name": str, "url": str}, ...]} for
    products that have a single-product-review job in the DB (any non-archived status,
    including in-flight). Used to discover comparison opportunities.

    Product name is read from brief.products[0].name (the brief stores singles
    with a single-item products list).
    """
    by_cat: dict[str, list[dict]] = defaultdict(list)
    if not DB_PATH.exists():
        return by_cat

    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT context FROM jobs WHERE status NOT IN ('archived', 'failed')")
        for (ctx_raw,) in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                if ctx.get("article_type") != "single-product-review":
                    continue
                brief = ctx.get("brief") or {}
                cat = (brief.get("category") or "").strip().lower()
                url = ctx.get("product_url", "") or ""
                m = re.search(r'/pl/\d+-(\d+)', url)
                pid = m.group(1) if m else None
                products = brief.get("products") or []
                name = products[0].get("name", "") if products else ""
                if cat and pid and name and url:
                    by_cat[cat].append({"id": pid, "name": name, "url": url})
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return by_cat


def load_comparison_pairs_written() -> set[frozenset]:
    """
    Returns a set of frozensets of product IDs that already appear together in a
    non-archived comparison job. Used to dedupe pair candidates.
    """
    pairs: set[frozenset] = set()
    if not DB_PATH.exists():
        return pairs

    con = sqlite3.connect(str(DB_PATH))
    try:
        cur = con.cursor()
        cur.execute("SELECT context FROM jobs WHERE status NOT IN ('archived')")
        for (ctx_raw,) in cur.fetchall():
            try:
                ctx = json.loads(ctx_raw) if isinstance(ctx_raw, str) else ctx_raw
                if ctx.get("article_type") != "comparison":
                    continue
                prods = (ctx.get("brief") or {}).get("products") or []
                pids: set[str] = set()
                for p in prods:
                    src = p.get("affiliate_url") or p.get("product_url") or ""
                    m = re.search(r'/pl/\d+-(\d+)', src)
                    if m:
                        pids.add(m.group(1))
                if len(pids) >= 2:
                    pairs.add(frozenset(pids))
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return pairs


def get_comparison_candidates() -> list[dict]:
    """
    Enumerate eligible comparison pairs.

    Trigger: a category has 2+ products written as singles, and the pair has
    not yet been covered by a comparison.

    Returns a list of candidate dicts sorted by combined score, highest first:
      {"category": str, "product_urls": [str, str],
       "names": [str, str], "ids": [str, str], "score": float}

    Score is the sum of each product's composite_score() from the latest snapshot,
    falling back to 0 when no snapshot is available.
    """
    written_by_cat = load_written_singles_by_category()
    pairs_written  = load_comparison_pairs_written()
    latest, _      = load_snapshots() if JSONL.exists() else ({}, {})

    candidates: list[dict] = []
    for cat, products in written_by_cat.items():
        if len(products) < 2:
            continue
        for i in range(len(products)):
            for j in range(i + 1, len(products)):
                a, b = products[i], products[j]
                pair_key = frozenset({a["id"], b["id"]})
                if pair_key in pairs_written:
                    continue
                score = composite_score(latest.get(a["id"], {})) + composite_score(latest.get(b["id"], {}))
                candidates.append({
                    "category":     cat,
                    "product_urls": [a["url"], b["url"]],
                    "names":        [a["name"], b["name"]],
                    "ids":          [a["id"], b["id"]],
                    "score":        score,
                })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def is_known(product: dict, known_keys: set[str]) -> bool:
    return canonical_product_key(
        product.get("name", ""),
        pid=product.get("id"),
        url=product.get("product_url"),
    ) in known_keys


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
    Always returns "single-product-review" for individual-product candidates.
    Hero auto-recommendation was retired 2026-06-10. Comparison opportunities
    live in get_comparison_candidates() - they're scored per pair, not per product,
    so they don't fit this function's signature.
    """
    _ = (category_name, unwritten_in_category, existing_in_category)  # kept for signature stability
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
    known_keys = load_known_keys()

    candidates = []
    for pid, product in latest.items():
        exists = is_known(product, known_keys)
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
    parser.add_argument("--comparisons",    action="store_true",
                        help="List eligible comparison pairs (categories with 2+ singles)")
    args = parser.parse_args()

    if args.comparisons:
        pairs = get_comparison_candidates()
        print(f"\n=== Eligible comparison pairs ===")
        print(f"Categories with 2+ singles + unwritten pair combinations: {len(pairs)}\n")
        if not pairs:
            print("No eligible pairs. Need at least 2 single-product-review jobs in the same category.")
            return
        for i, c in enumerate(pairs[:args.limit], 1):
            line = f"{i:>3}  {c['score']:>5.1f}  {c['category']:<25}  {c['names'][0]}  ×  {c['names'][1]}"
            print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))
        return

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
