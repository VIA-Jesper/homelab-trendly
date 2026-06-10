"""
fetch_hot_products.py — Append PriceRunner products to data/hot-products.jsonl.

Two modes:
  --site-only  Trending (hot) products per category. Fast, ~50/category.
               Good for daily runs — surfaces products with purchase intent right now.
  --popular    All-time popular products per category via pagination.
               Fetches up to 200/category (2 pages × 100). Larger pool, slower.
               Run weekly or on first bootstrap to fill the candidate queue.

Usage:
  python fetch_hot_products.py              # top 25 trending across all categories
  python fetch_hot_products.py --site-only  # trending per category (recommended daily)
  python fetch_hot_products.py --popular    # all-time popular per category (weekly)

After running, use suggest_articles.py to surface ranked candidates.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HOT_BASE_URL    = "https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK"
POPULAR_BASE_URL = "https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK"
LOG_FILE = Path(__file__).parent.parent / "data" / "hot-products.jsonl"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Categories for --site-only / --popular (husforbegyndere.dk scope)
# cl prefix = specific subcategory, t prefix = top-level group (hot endpoint only)
HOT_CATEGORIES: dict[str, str] = {
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
    "cl348":  "Haveredskaber",
    "cl345":  "Elværktøj",
    "cl1258": "Bore-Skruemaskiner",
    "cl1260": "Elsave",
    "cl1613": "Robotstøvsugere",
    "cl19":   "Støvsugere",
    "cl13":   "Opvaskemaskiner",
    "cl14":   "Vaskemaskiner",
    "cl17":   "Tørretumblere",
    "cl101":  "Komfurer",
    "cl105":  "Ovne",
    "cl106":  "Kogeplader",
    "t14":    "Køkkenapparater",
}

# --popular uses the v4 search endpoint which requires bare numeric IDs (no cl/t prefix).
# t14 is expanded into specific kitchen subcategories since the v4 endpoint
# only accepts specific category IDs, not top-level group IDs.
POPULAR_CATEGORIES: dict[str, str] = {
    "1595": "Robotplæneklippere",
    "119":  "Plæneklippere",
    "1611": "Havetraktorer",
    "120":  "Havemaskiner",
    "335":  "Grill",
    "638":  "Højtryks- & Hedvandsrensere",
    "1290": "Trampoliner",
    "541":  "Pools",
    "1388": "Spabade & Vildmarksbade",
    "499":  "Havemøbler",
    "348":  "Haveredskaber",
    "345":  "Elværktøj",
    "1258": "Bore-Skruemaskiner",
    "1260": "Elsave",
    "1613": "Robotstøvsugere",
    "19":   "Støvsugere",
    "13":   "Opvaskemaskiner",
    "14":   "Vaskemaskiner",
    "17":   "Tørretumblere",
    "101":  "Komfurer",
    "105":  "Ovne",
    "106":  "Kogeplader",
    # t14 expanded into specific kitchen subcategories
    "82":   "Kaffemaskiner",
    "81":   "Frituregryder & Airfryere",
    "250":  "Ismaskiner",
    "84":   "Blendere",
    "1244": "Røremaskiner & Foodprocessorer",
}


# ── Hot endpoint (trending) ───────────────────────────────────────────────────

def fetch_hot(category_id: str | None = None, size: int = 50) -> list[dict]:
    url = f"{HOT_BASE_URL}/{category_id}" if category_id else HOT_BASE_URL
    r = httpx.get(url, params={"size": size}, headers={"User-Agent": _UA}, timeout=15)
    r.raise_for_status()
    return r.json().get("products", [])


def normalise_hot(product: dict, fetched_at: str, fetched_for: str | None = None) -> dict:
    img = product.get("image") or {}
    img_path = img.get("path", "")
    cat = product.get("category") or {}
    price = (product.get("lowestPrice") or {}).get("amount")
    ribbon = (product.get("ribbon") or {}).get("value", "")
    return {
        "fetched_at": fetched_at,
        "fetched_for": fetched_for,
        "source": "hot",
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


# ── Popular endpoint (all-time, paginated) ────────────────────────────────────

def fetch_popular_page(category_id: str, size: int = 100, offset: int = 0) -> tuple[list[dict], int]:
    """Returns (products, total_count). Hard cap: size=100. API rejects offset=0 — omit for first page."""
    params: dict = {"size": size, "sorting": "POPULARITY", "device": "desktop"}
    if offset > 0:
        params["offset"] = offset
    r = httpx.get(
        f"{POPULAR_BASE_URL}/{category_id}",
        params=params,
        headers={"User-Agent": _UA},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    products = data.get("products") or data.get("results") or []
    total = data.get("totalProductHits", 0)
    return products, total


def normalise_popular(product: dict, fetched_at: str, fetched_for: str, cat_id: str, cat_name: str) -> dict:
    """
    The v4 endpoint doesn't include category in individual product objects, so we
    inject category_id / category_name from the fetch context.
    The ribbon here can be PRICE_DROP_ABSOLUTE (not a watcher count) — only store
    watcher ribbons; everything else becomes empty string.
    """
    img = product.get("image") or {}
    img_url = img.get("url") or img.get("path", "")
    if img_url and not img_url.startswith("http"):
        img_url = f"https://www.pricerunner.dk{img_url}"
    price = (product.get("lowestPrice") or {}).get("amount")
    ribbon = product.get("ribbon") or {}
    watchers = ribbon.get("value", "") if ribbon.get("type") == "WATCHED" else ""
    return {
        "fetched_at": fetched_at,
        "fetched_for": fetched_for,
        "source": "popular",
        "rank": (product.get("rank") or {}).get("rank"),
        "id": product.get("id"),
        "name": product.get("name"),
        "category_id": f"cl{cat_id}",
        "category_name": cat_name,
        "price_dkk": float(price) if price else None,
        "watchers": watchers,
        "image_url": img_url or None,
        "product_url": f"https://www.pricerunner.dk{product.get('url', '')}",
        "out_of_stock": product.get("outOfStock", False),
    }


def fetch_popular_category(cat_id: str, cat_name: str, fetched_at: str, pages: int = 2) -> list[dict]:
    """Fetch up to pages*100 products for a category, respecting the 100/request cap."""
    rows: list[dict] = []
    for page in range(pages):
        offset = page * 100
        try:
            products, total = fetch_popular_page(cat_id, size=100, offset=offset)
        except httpx.HTTPStatusError as e:
            print(f"  [{cat_name}] page {page+1} failed: HTTP {e.response.status_code} — skipping")
            break
        if not products:
            break
        rows.extend(
            normalise_popular(p, fetched_at, fetched_for=f"cl{cat_id}", cat_id=cat_id, cat_name=cat_name)
            for p in products
        )
        print(f"  [{cat_name}] page {page+1}: {len(products)} products (total in catalog: {total})")
        if offset + 100 >= total:
            break  # fetched everything available
        time.sleep(0.5)   # 500ms between pages — stay well under rate limit
    return rows


# ── Shared helpers ────────────────────────────────────────────────────────────

def watcher_sort_key(r: dict) -> int:
    val = (r.get("watchers") or "").replace("+", "").strip()
    try:
        return int(val)
    except ValueError:
        return 0


def print_row(r: dict):
    line = f"{(r['watchers'] or ''):10} {(r['category_name'] or ''):<25} {str(r['price_dkk'] or '?'):>8}  {r['name']}"
    print(line.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    site_only = "--site-only" in sys.argv
    popular   = "--popular"   in sys.argv
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    all_rows: list[dict] = []

    if popular:
        print(f"Fetching all-time popular products per category ({len(POPULAR_CATEGORIES)} categories, up to 200 each)...\n")
        for cat_id, cat_name in POPULAR_CATEGORIES.items():
            print(f"Fetching {cat_name} ({cat_id})...")
            rows = fetch_popular_category(cat_id, cat_name, fetched_at, pages=2)
            all_rows.extend(rows)

    elif site_only:
        for cat_id, cat_name in HOT_CATEGORIES.items():
            print(f"Fetching {cat_name} ({cat_id}) [trending]...")
            products = fetch_hot(category_id=cat_id, size=50)
            all_rows.extend(normalise_hot(p, fetched_at, fetched_for=cat_id) for p in products)

    else:
        print("Fetching top 25 trending products (all categories)...")
        products = fetch_hot(size=25)
        all_rows = [normalise_hot(p, fetched_at, fetched_for=None) for p in products]

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
