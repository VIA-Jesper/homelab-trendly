"""
fetch_hot_products.py — Append PriceRunner hot products to data/hot-products.jsonl.

Pure data dump. Run on a schedule (daily/weekly) to build a trend history.
Each run appends one line per product — the JSONL grows over time so you can
detect rising products (rank improving across fetches) in suggest_articles.py.

API used:
  https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK/{categoryId}?size=N

Each line written:
  {"fetched_at": "2026-06-01T12:00:00Z", "rank": 1, "id": "3292855103",
   "name": "Segway Navimow i105E", "category_id": "cl1595", "category_name": "...",
   "price_dkk": 6340.0, "watchers": "1000+", "image_url": "...", "product_url": "...",
   "out_of_stock": false}

Usage:
  python fetch_hot_products.py              # top 25 across all categories (global)
  python fetch_hot_products.py --site-only  # per-category for husforbegyndere.dk (recommended)

After running, use suggest_articles.py to surface ranked candidates from the log.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK"
LOG_FILE = Path(__file__).parent.parent / "data" / "hot-products.jsonl"

# Categories relevant to husforbegyndere.dk
# Prefix cl = specific category, t = top-level category group (broader)
HUSFORBEGYNDERE_CATEGORIES = {
    # Garden & outdoor (t1424) — verified
    "cl1595": "Robotplæneklippere",
    "cl119":  "Plæneklippere",
    "cl1611": "Havetraktorer",
    "cl120":  "Havemaskiner",
    "cl335":  "Grill",
    "cl638":  "Højtryks- & Hedvandsrensere",
    "cl1290": "Trampoliner",
    "cl541":  "Pools",
    "cl1388": "Spabade & Vildmarksbade",
    "cl499":  "Havemøbler",
    "cl348":  "Haveredskaber",  # uncertain — may be need-based, not review intent
    # Power tools — verified
    "cl345":  "Elværktøj",
    "cl1258": "Bore-Skruemaskiner",
    "cl1260": "Elsave",
    # Hvidevarer (t3) — verified
    "cl1613": "Robotstøvsugere",
    "cl19":   "Støvsugere",
    "cl13":   "Opvaskemaskiner",
    "cl14":   "Vaskemaskiner",
    "cl17":   "Tørretumblere",
    "cl101":  "Komfurer",
    "cl105":  "Ovne",
    "cl106":  "Kogeplader",
    # Kitchen — t14 covers all subcategories (ismaskiner, airfryere, kaffemaskiner, etc.)
    "t14":    "Køkkenapparater",
}


def fetch(category_id: str | None = None, size: int = 10) -> list[dict]:
    url = f"{BASE_URL}/{category_id}" if category_id else BASE_URL
    r = httpx.get(url, params={"size": size}, timeout=15)
    r.raise_for_status()
    return r.json().get("products", [])


def normalise(product: dict, fetched_at: str, fetched_for: str | None = None) -> dict:
    img = product.get("image") or {}
    img_path = img.get("path", "")
    cat = product.get("category") or {}
    price = (product.get("lowestPrice") or {}).get("amount")
    ribbon = (product.get("ribbon") or {}).get("value", "")
    return {
        "fetched_at": fetched_at,
        "fetched_for": fetched_for,  # category key queried (e.g. "cl1595", "t14") or None for global
        "rank": (product.get("rank") or {}).get("rank"),
        "id": product.get("id"),
        "name": product.get("name"),
        "category_id": cat.get("id"),
        "category_name": cat.get("name"),
        "price_dkk": float(price) if price else None,
        "watchers": ribbon,
        "image_url": f"https://www.pricerunner.dk{img_path}" if img_path else None,
        "product_url": f"https://www.pricerunner.dk{product.get('url', '')}",
        "out_of_stock": product.get("outOfStock", False),
    }


def watcher_sort_key(r: dict) -> int:
    """Parse ribbon value like '1000+', '500+', '100+' into an int for sorting."""
    val = (r.get("watchers") or "").replace("+", "").strip()
    try:
        return int(val)
    except ValueError:
        return 0


def print_row(r: dict):
    line = f"{(r['watchers'] or ''):10} {(r['category_name'] or ''):<25} {str(r['price_dkk'] or '?'):>8}  {r['name']}"
    print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))


def main():
    site_only = "--site-only" in sys.argv
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_rows: list[dict] = []

    if site_only:
        for cat_id, cat_name in HUSFORBEGYNDERE_CATEGORIES.items():
            print(f"Fetching {cat_name} ({cat_id})...")
            products = fetch(category_id=cat_id, size=50)
            all_rows.extend(normalise(p, fetched_at, fetched_for=cat_id) for p in products)
    else:
        print("Fetching top 25 hot products (all categories)...")
        products = fetch(size=25)
        all_rows = [normalise(p, fetched_at, fetched_for=None) for p in products]

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    sorted_rows = sorted(all_rows, key=watcher_sort_key, reverse=True)

    print(f"\nLogged {len(all_rows)} products to {LOG_FILE}\n")
    print(f"{'Watchers':<10} {'Category':<25} {'Price':>8}  Name")
    print("-" * 80)
    for r in sorted_rows:
        if watcher_sort_key(r) > 0:
            print_row(r)


if __name__ == "__main__":
    main()
