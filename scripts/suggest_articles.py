"""
suggest_articles.py — Surface article candidates from hot-products.jsonl.

Reads the latest snapshot per product, scores each on a composite signal
(PriceRunner rank + watcher ribbon), filters out products already in the DB,
and prints a ranked candidate list with product URLs ready to queue.

Composite score:
  rank_score    = max(0, 11 - rank)   → rank 1 = 10pts, rank 10 = 1pt, rank 11+ = 0
  watcher_score → 1000+ = 4, 500+ = 3, 200+ = 2, 100+ = 1.5, 50+ = 1, none = 0
  composite     = rank_score + watcher_score

  rank 1 + 1000 watchers = 14 (max signal)
  rank 1 alone            = 10
  rank 5 + 500 watchers   = 9

Rising signal: compares latest snapshot to the previous fetch.
  ↑3 = climbed 3 positions since last run — strong intent signal even at lower scores.

Duplicate detection checks against existing jobs in the DB by:
  - PriceRunner product ID (extracted from URL)
  - Product name (lowercase match)

Usage:
  python suggest_articles.py                   # top 20 new candidates
  python suggest_articles.py --limit 10        # top 10
  python suggest_articles.py --min-score 5     # only score >= 5 (rank 5 or better)
  python suggest_articles.py --show-all        # include already-written products (marked [EXISTS])
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
JSONL = ROOT / "data" / "hot-products.jsonl"
DB_PATH = ROOT / "trendly_local.db"

WATCHER_SCORES = {"1000": 4.0, "500": 3.0, "200": 2.0, "100": 1.5, "50": 1.0}


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
            # Skip global (non-site-only) entries — fetched_for is None for those.
            # Old entries pre-dating this field are kept if they have a known category_id.
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
            except (json.JSONDecodeError, AttributeError, TypeError):
                pass
    finally:
        con.close()

    return known_ids, known_names


def is_known(product: dict, known_ids: set[str], known_names: set[str]) -> bool:
    if product.get("id") in known_ids:
        return True
    return (product.get("name") or "").strip().lower() in known_names


def rising_delta(pid: str, latest: dict, previous: dict) -> int | None:
    """Positive = rank improved (rank number decreased = product rose)."""
    prev = previous.get(pid)
    if not prev:
        return None
    r_now = latest[pid].get("rank")
    r_prev = prev.get("rank")
    if r_now is None or r_prev is None:
        return None
    return r_prev - r_now


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


def _print_row(i: int, product: dict, score: float, delta: int | None, is_new: bool, exists: bool):
    name = (product.get("name") or "")
    cat = (product.get("category_name") or "")[:20]
    watchers = product.get("watchers") or "-"
    rank = product.get("rank") or "?"
    price = product.get("price_dkk")
    price_str = f"{price:,.0f} kr" if price else "?"
    delta_str = _fmt_delta(delta, is_new)
    exists_tag = " [EXISTS]" if exists else ""

    line = (
        f"{i:>3}  {score:>5.1f}  {delta_str:>5}  {watchers:<7} {str(rank):>4}  "
        f"{cat:<20}  {price_str:>10}  {name}{exists_tag}"
    )
    url_line = f"     {product.get('product_url', '')}"
    print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))
    print(url_line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))


def main():
    parser = argparse.ArgumentParser(
        description="Surface article candidates ranked by composite hot-product score"
    )
    parser.add_argument("--limit", type=int, default=20, help="Max candidates to show (default: 20)")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum composite score filter")
    parser.add_argument("--show-all", action="store_true", help="Include products already in the DB")
    args = parser.parse_args()

    if not JSONL.exists():
        print(f"No data at {JSONL}. Run fetch_hot_products.py --site-only first.")
        sys.exit(1)

    latest, previous = load_snapshots()
    known_ids, known_names = load_known_products()

    candidates = []
    skipped = 0

    for pid, product in latest.items():
        exists = is_known(product, known_ids, known_names)
        if exists and not args.show_all:
            skipped += 1
            continue
        score = composite_score(product)
        if score < args.min_score:
            continue
        delta = rising_delta(pid, latest, previous)
        is_new_product = pid not in previous
        candidates.append((score, product, delta, is_new_product, exists))

    candidates.sort(key=lambda x: x[0], reverse=True)

    print(f"\n=== Trendly Article Candidates ===")
    print(f"Snapshot products: {len(latest)}  |  Already in DB: {skipped}  |  Candidates: {len(candidates)}")
    print(f"\n{'#':>3}  {'Score':>5}  {'Rise':>5}  {'Watch':<7} {'Rank':>4}  {'Category':<20}  {'Price':>10}  Name")
    print("-" * 115)

    for i, (score, product, delta, is_new, exists) in enumerate(candidates[:args.limit], 1):
        _print_row(i, product, score, delta, is_new, exists)

    if not candidates:
        print("\nNo candidates. Try --show-all or run fetch_hot_products.py --site-only first.")


if __name__ == "__main__":
    main()
