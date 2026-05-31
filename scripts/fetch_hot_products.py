"""
Fetches PriceRunner's hot products endpoint and appends results to a JSONL log.

Each run appends one line per product to data/hot-products.jsonl:
  {"fetched_at": "2026-05-31T12:00:00Z", "rank": 1, "id": "...", "name": "...", ...}

Run manually or via cron. No DB dependency.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

HOT_PRODUCTS_URL = (
    "https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK"
)
LOG_FILE = Path(__file__).parent.parent / "data" / "hot-products.jsonl"

# Category IDs relevant to husforbegyndere.dk — filter to these if --site-only flag passed
HUSFORBEGYNDERE_CATEGORY_IDS = {
    "cl82",    # Kaffemaskiner
    "cl1613",  # Robotstøvsugere
    "cl120",   # Havemaskiner
    "cl335",   # Grill
    "cl638",   # Højtryksrensere
    "cl1595",  # Robotplæneklippere
}


def fetch(size: int = 50) -> list[dict]:
    r = httpx.get(HOT_PRODUCTS_URL, params={"size": size}, timeout=15)
    r.raise_for_status()
    return r.json().get("products", [])


def normalise(product: dict, fetched_at: str) -> dict:
    img = product.get("image") or {}
    img_path = img.get("path", "")
    cat = product.get("category") or {}
    price = (product.get("lowestPrice") or {}).get("amount")
    ribbon = (product.get("ribbon") or {}).get("value", "")
    return {
        "fetched_at": fetched_at,
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


def main():
    site_only = "--site-only" in sys.argv
    size = 50

    print(f"Fetching top {size} hot products from PriceRunner...")
    products = fetch(size)
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if site_only:
        products = [p for p in products if (p.get("category") or {}).get("id") in HUSFORBEGYNDERE_CATEGORY_IDS]
        print(f"Filtered to {len(products)} products in husforbegyndere.dk categories")

    rows = [normalise(p, fetched_at) for p in products]

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Logged {len(rows)} products to {LOG_FILE}")
    print()
    print(f"{'Rank':<5} {'Category':<25} {'Price':>8}  {'Watchers':<8}  Name")
    print("-" * 80)
    for r in rows:
        line = f"{str(r['rank']):<5} {(r['category_name'] or ''):<25} {str(r['price_dkk'] or '?'):>8}  {(r['watchers'] or ''):8}  {r['name']}"
        print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))


if __name__ == "__main__":
    main()
