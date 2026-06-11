"""
plan_slots.py - deterministic slot planner (Phase 1).

Enumerates the article slots for a category from the format registry
(affiliate-pipeline/formats_v1.json) + segment config
(affiliate-pipeline/segments/<category>_v1.json), subtracts what the coverage
ledger already covers, ranks the unfilled slots by product popularity, and emits
the top N as jobs. Dry-run by default.

No LLM: the slot matrix (category x format x segment/product) defines every valid
article; this script just fills the unfilled slots. Slot identity is computed by
api/services/dedup.slot_key so the planner and the API gate agree exactly. See
docs/dedup-scaling-plan.md.

Usage (from repo root):
  .venv\\Scripts\\python.exe scripts\\plan_slots.py --category robotstoevsugere
  .venv\\Scripts\\python.exe scripts\\plan_slots.py --category robotstoevsugere --count 5
  .venv\\Scripts\\python.exe scripts\\plan_slots.py --category robotstoevsugere --execute --api-key changeme
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "trendly_local.db"
FORMATS_FILE = ROOT / "affiliate-pipeline" / "formats_v1.json"
SEGMENTS_DIR = ROOT / "affiliate-pipeline" / "segments"
SITE_KEY = "hus"
YEAR = datetime.now().year

# Pure modules from api/services (stdlib-only; imported by adding the dir to the
# path so the api `services` package __init__ - which needs config/DB - is skipped).
sys.path.insert(0, str(ROOT / "api" / "services"))
import dedup  # noqa: E402
import pricerunner_client as prc  # noqa: E402

# Reuse the pool loader + scorer from suggest_articles (same scripts/ dir).
sys.path.insert(0, str(ROOT / "scripts"))
from suggest_articles import composite_score, load_snapshots  # noqa: E402


def _enc(s: str) -> str:
    return s.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)


def load_formats() -> list[dict]:
    return json.loads(FORMATS_FILE.read_text(encoding="utf-8"))["formats"]


def load_segments(category_slug: str) -> list[dict]:
    f = SEGMENTS_DIR / f"{category_slug}_v1.json"
    return json.loads(f.read_text(encoding="utf-8"))["segments"] if f.exists() else []


def covered_slots() -> set[str]:
    """slot_keys owned by a live (non-archived/failed) job."""
    if not DB_PATH.exists():
        return set()
    con = sqlite3.connect(str(DB_PATH))
    try:
        rows = con.execute(
            "SELECT jc.slot_key FROM job_coverage jc JOIN jobs j ON j.id = jc.job_id "
            "WHERE j.status NOT IN ('archived', 'failed')"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


def _slug_of(p: dict) -> str | None:
    """Map a pool product to a category slug. The hot-products feed prefixes
    category ids ('cl1595'); _CATEGORY_SLUG keys are bare digits ('1595')."""
    digits = "".join(ch for ch in str(p.get("category_id") or "") if ch.isdigit())
    return prc._CATEGORY_SLUG.get(digits)


def category_pool(category_slug: str) -> list[tuple[float, dict]]:
    """Latest snapshot per product in this category, sorted by composite score desc."""
    latest, _ = load_snapshots()
    pool = [(composite_score(p), p) for p in latest.values() if _slug_of(p) == category_slug]
    pool.sort(key=lambda x: x[0], reverse=True)
    return pool


def _pkey(p: dict) -> str:
    return dedup.canonical_product_key(p.get("name", ""), pid=p.get("id"), url=p.get("product_url"))


def _price_matches(price: float | None, m: dict) -> bool:
    if price is None:
        return False
    if "price_min" in m and price < m["price_min"]:
        return False
    if "price_max" in m and price >= m["price_max"]:
        return False
    return True


def enumerate_slots(category_slug: str) -> list[dict]:
    """All candidate slots for the category (before subtracting covered ones)."""
    by_fmt = {f["key"]: f for f in load_formats()}
    segments = load_segments(category_slug)
    pool = category_pool(category_slug)
    display = prc.get_category_display(category_slug)
    slots: list[dict] = []

    def mk(slot_key, fmt, article_type, picks, segment, keyword, score):
        slots.append({
            "slot_key": slot_key, "format": fmt, "article_type": article_type,
            "product_urls": [p.get("product_url") for _, p in picks],
            "names": [p.get("name", "") for _, p in picks],
            "segment": segment, "keyword": keyword, "score": round(score, 2),
        })

    # single_review: one slot per product
    f = by_fmt.get("single_review")
    if f:
        for score, p in pool:
            if not p.get("product_url"):
                continue
            sk = dedup.slot_key("single-product-review", category_slug, [_pkey(p)])
            kw = f["keyword_template"].format(product=p.get("name", ""), category=display)
            mk(sk, "single_review", "single-product-review", [(score, p)], None, kw, score)

    # segment_roundup: one slot per segment with enough matching products
    f = by_fmt.get("segment_roundup")
    if f:
        for seg in segments:
            matched = [(s, p) for s, p in pool if _price_matches(p.get("price_dkk"), seg["match"])]
            if len(matched) < f["min_products"]:
                continue
            picks = matched[:f["max_products"]]
            sk = dedup.slot_key("hero", category_slug, [_pkey(p) for _, p in picks], segment=seg["segment_key"])
            kw = f["keyword_template"].format(category=display, segment=seg["segment_phrase"])
            mk(sk, "segment_roundup", "hero", picks, seg["segment_key"], kw,
               sum(s for s, _ in picks) / len(picks))

    # best_of: singleton (one per year), top products overall
    f = by_fmt.get("best_of")
    if f and len(pool) >= f["min_products"]:
        picks = pool[:f["max_products"]]
        sk = dedup.slot_key("hero", category_slug, [_pkey(p) for _, p in picks], segment=str(YEAR))
        kw = f["keyword_template"].format(category=display, year=YEAR)
        # Slight boost so the flagship roundup ranks above individual reviews.
        mk(sk, "best_of", "hero", picks, str(YEAR), kw, sum(s for s, _ in picks) / len(picks) + 1)

    return slots


def build_plan(category_slug: str, count: int) -> tuple[list[dict], int, int]:
    covered = covered_slots()
    allslots = enumerate_slots(category_slug)
    unfilled = [s for s in allslots if s["slot_key"] not in covered]
    unfilled.sort(key=lambda s: s["score"], reverse=True)
    return unfilled[:count], len(allslots), len(allslots) - len(unfilled)


def print_plan(plan: list[dict], total: int, filled: int, category_slug: str):
    print(f"\n=== Slot plan: {category_slug} ===")
    print(f"slots enumerated: {total}  |  already covered: {filled}  |  proposing: {len(plan)}\n")
    if not plan:
        print("No unfilled slots. (Pool empty for this category, or everything is covered.)")
        return
    for i, s in enumerate(plan, 1):
        seg = f" [{s['segment']}]" if s["segment"] else ""
        print(_enc(f"  {i}. {s['score']:>5.1f}  {s['format']:<16} {s['article_type']:<22} "
                   f"{len(s['product_urls'])}p{seg}  \"{s['keyword']}\""))
        print(_enc(f"       slot: {s['slot_key']}"))
    print()


def execute_plan(plan: list[dict], api_url: str, api_key: str):
    base = api_url.rstrip("/")
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    for s in plan:
        payload = {
            "site_key": SITE_KEY,
            "article_type": s["article_type"],
            "product_urls": s["product_urls"],
            "reasoning": f"planner slot {s['slot_key']} ({s['format']}): {s['keyword']}",
        }
        if s["segment"]:
            payload["segment"] = s["segment"]
        print(_enc(f"  queuing {s['format']}: \"{s['keyword']}\""))
        try:
            r = httpx.post(f"{base}/api/v1/jobs/from-products", json=payload, headers=headers, timeout=120)
            if r.status_code in (200, 201):
                print(f"    -> job {r.json().get('job_id')}")
            elif r.status_code == 409:
                print("    -> SKIP (already covered)")
            else:
                print(f"    -> ERROR {r.status_code}: {r.text[:200]}")
        except httpx.RequestError as e:
            print(f"    -> REQUEST ERROR: {e}")
    print()


def main():
    ap = argparse.ArgumentParser(description="Deterministic slot planner: fill unfilled article slots")
    ap.add_argument("--category", default="robotstoevsugere", help="category slug (see _CATEGORY_SLUG)")
    ap.add_argument("--count", type=int, default=5, help="max slots to propose (default: 5)")
    ap.add_argument("--execute", action="store_true", help="actually create jobs (default: dry-run)")
    ap.add_argument("--api-url", default="http://localhost:8000")
    ap.add_argument("--api-key", default="changeme")
    args = ap.parse_args()

    plan, total, filled = build_plan(args.category, args.count)
    print_plan(plan, total, filled, args.category)
    if not plan:
        return
    if args.execute:
        print("Executing plan...\n")
        execute_plan(plan, args.api_url, args.api_key)
        print("Done.")
    else:
        print("Dry-run. Pass --execute to queue these slots.")


if __name__ == "__main__":
    main()
