"""
PriceRunner API client — fetches live product data for article generation.

WHY THIS EXISTS
  The article generator needs real product data (price, specs, images, merchant count)
  to write factual, trustworthy Danish affiliate articles. PriceRunner's public web API
  (no auth required) is our source. This is a direct Python port of the TypeScript
  reference implementation in archive/src/scraper/pricerunner-client.ts.

WHY NO OFFICIAL API
  The formal PriceRunner publisher API (via Rune) is still pending. This client hits the
  same endpoints the browser hits, with browser-like headers. It covers everything we need
  for product data and is already proven in the TS implementation.

WHY ASYNC
  The FastAPI app is async throughout. Using httpx.AsyncClient keeps everything on the
  same event loop — no thread pool overhead and no sync blocking.

KEY DECISIONS
  - Rate limit: 1 req/sec minimum. PriceRunner blocks faster bursts.
  - Backoff: exponential on 429/5xx, max 4 retries. Fail fast on client errors.
  - Cache: 24hr in-memory per category. Category data doesn't change intraday.
  - User-Agent rotation: reduces risk of UA-based blocks on repeated requests.
  - Product IDs prefixed with "pr_" to distinguish from other future data sources.
  - Fetching by URL: extract category_id + product_id from URL, fetch category,
    filter to the specific product. No confirmed direct-product endpoint exists in the
    public API (see archive/docs/pricerunner-api-reference.md). Size=100 covers nearly
    all cases since the user is linking to a specific product they know about.
"""

import asyncio
import logging
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─── User-Agent rotation ───────────────────────────────────────────────────────
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


# ─── Rate limiting (1 req/sec minimum) ────────────────────────────────────────
_last_request_at: float = 0.0
_rate_limit_lock = asyncio.Lock()


async def _rate_limit() -> None:
    global _last_request_at
    async with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_request_at
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _last_request_at = time.monotonic()


# ─── Exponential backoff ───────────────────────────────────────────────────────
async def _with_backoff(fn, max_retries: int = 4):
    """Retry fn() on 429/5xx with exponential backoff. Raises on client errors."""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            retryable = status == 429 or status == 503 or status >= 500
            if not retryable or attempt == max_retries:
                raise
            delay = min(1.0 * (2 ** attempt) + random.random() * 0.5, 30.0)
            logger.warning(
                "PriceRunner HTTP %s — retry %d/%d in %.1fs",
                status, attempt + 1, max_retries, delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


# ─── 24-hour in-memory cache ───────────────────────────────────────────────────
_CACHE_TTL = 24 * 60 * 60  # seconds

@dataclass
class _CacheEntry:
    data: object
    expires_at: float


_cache: dict[str, _CacheEntry] = {}


def _cache_get(key: str):
    entry = _cache.get(key)
    if entry is None or time.monotonic() > entry.expires_at:
        _cache.pop(key, None)
        return None
    return entry.data


def _cache_set(key: str, data: object) -> None:
    _cache[key] = _CacheEntry(data=data, expires_at=time.monotonic() + _CACHE_TTL)


# ─── Base URL per country ──────────────────────────────────────────────────────
_PR_BASE: dict[str, str] = {
    "DK": "https://www.pricerunner.dk",
    "SE": "https://www.pricerunner.se",
    "GB": "https://www.pricerunner.com",
}


def _base(country: str) -> str:
    return _PR_BASE.get(country.upper(), "https://www.pricerunner.dk")


# ─── Internal product model ────────────────────────────────────────────────────
@dataclass
class RawProduct:
    """
    Normalised product data ready for the brief builder.
    Mirrors the TypeScript RawProduct type in archive/src/services/product-store.ts.
    All fields are required — brief builder will reject incomplete products.
    """
    id: str             # "pr_{pricerunner_id}", e.g. "pr_3332774746"
    name: str
    category: str       # internal slug, e.g. "kaffemaskiner"
    price_kr: float
    retailer: str       # cheapest merchant name
    affiliate_url: str  # full pricerunner.dk product URL
    image_url: str
    popularity_score: float
    out_of_stock: bool
    specs: dict[str, str] = field(default_factory=dict)
    # specs may contain: brand, rating, watchedLabel, priceDrop, popularityRank, merchantCount


# ─── Category ID → internal slug map ──────────────────────────────────────────
# Matches CATEGORY_ID_MAP in archive/src/scraper/pricerunner-client.ts
_CATEGORY_SLUG: dict[str, str] = {
    "81":   "frituregryder-airfryere",
    "82":   "kaffemaskiner",
    "250":  "ismaskiner",
    "14":   "vaskemaskiner",
    "1613": "robotstoevsugere",
    "1595": "robotplaeneklippere",
    "335":  "grill",
    "120":  "havemaskiner",
    "638":  "hojtryks-hedvandsrensere",
    "345":  "elvaerktoej",
    "1258": "bore-skruemaskiner",
    "1260": "elsave",
}


# ─── Popularity scoring ────────────────────────────────────────────────────────
def _compute_popularity_score(p: dict) -> float:
    """
    Score a product by demand signals. Higher = more popular.
    Mirrors computePopularityScore() in archive/src/scraper/pricerunner-client.ts.

    Scoring:
      watchers  → 200+ = 40pts, 100+ = 30pts, 50+ = 20pts, any WATCHED = 10pts
      rank      → 1=30pts, 2=25pts, 3=20pts, top10=10pts
      rating    → ≥4.5 × ln(reviews+1), max 20pts
      merchants → >20=5pts, >10=3pts, >5=1pt
    """
    score = 0.0

    ribbon = p.get("ribbon") or {}
    ribbon_val = ribbon.get("value", "")
    try:
        watch_num = int(ribbon_val)
        if watch_num >= 200:
            score += 40
        elif watch_num >= 100:
            score += 30
        elif watch_num >= 50:
            score += 20
        else:
            score += 10
    except (ValueError, TypeError):
        if ribbon.get("type") == "WATCHED":
            score += 10

    rank_data = p.get("rank") or {}
    rank = rank_data.get("rank")
    if rank is not None:
        if rank == 1:
            score += 30
        elif rank == 2:
            score += 25
        elif rank == 3:
            score += 20
        elif rank <= 10:
            score += 10

    rating = p.get("rating") or {}
    avg = rating.get("average") or 0
    cnt = rating.get("count") or 0
    if avg >= 4.5 and cnt > 0:
        score += min(20, round(avg * math.log(cnt + 1)))

    merchants = (p.get("previewMerchants") or {}).get("count") or 0
    if merchants > 20:
        score += 5
    elif merchants > 10:
        score += 3
    elif merchants > 5:
        score += 1

    return score


# ─── V4 API response → RawProduct ─────────────────────────────────────────────
def _map_v4_product(p: dict, base_url: str, category_id: str) -> RawProduct:
    """Map a raw PriceRunner v4 API product dict to our internal RawProduct model."""
    def absolute(url: Optional[str]) -> str:
        if not url:
            return base_url
        return url if url.startswith("http") else f"{base_url}{url}"

    price_raw = (p.get("lowestPrice") or {}).get("amount")
    price_kr = (
        float(price_raw)
        if price_raw is not None
        else float((p.get("cheapestOffer") or {}).get("price", {}).get("amount", 0) or 0)
    )

    retailer = (
        (p.get("cheapestOffer") or {}).get("merchant", {}).get("name")
        or ((p.get("topOffers") or [{}])[0]).get("merchant", {}).get("name")
        or "PriceRunner"
    )

    image_data = p.get("image") or {}
    image_url = absolute(image_data.get("url") or image_data.get("path"))
    affiliate_url = absolute(p.get("url"))

    internal_category = _CATEGORY_SLUG.get(category_id, category_id)

    specs: dict[str, str] = {}
    brand = (p.get("brand") or {}).get("name")
    if brand:
        specs["brand"] = brand
    desc = p.get("description")
    if desc:
        specs["description"] = desc
    rating = p.get("rating") or {}
    if rating.get("average") is not None:
        specs["rating"] = f"{rating['average']} ({rating.get('count', 0)} reviews)"
    ribbon = p.get("ribbon") or {}
    if ribbon.get("type"):
        specs["ribbon"] = ribbon["type"]
    if ribbon.get("type") == "WATCHED" and ribbon.get("value"):
        num = abs(float(ribbon["value"]))
        specs["watchedLabel"] = f"{round(num)}+"
    price_drop = p.get("priceDrop") or {}
    if price_drop.get("percent") is not None:
        specs["priceDrop"] = f"{price_drop['percent']}%"
    rank_data = p.get("rank") or {}
    if rank_data.get("rank") is not None:
        specs["popularityRank"] = str(rank_data["rank"])
    merchants = (p.get("previewMerchants") or {}).get("count")
    if merchants is not None:
        specs["merchantCount"] = str(merchants)

    popularity = _compute_popularity_score(p)

    return RawProduct(
        id=f"pr_{p['id']}",
        name=p.get("name", ""),
        category=internal_category,
        price_kr=price_kr,
        retailer=retailer,
        affiliate_url=affiliate_url,
        image_url=image_url,
        popularity_score=popularity,
        out_of_stock=p.get("outOfStock", False),
        specs=specs,
    )


# ─── Public API ────────────────────────────────────────────────────────────────

def extract_product_info_from_url(url: str) -> Optional[tuple[str, str]]:
    """
    Extract (category_id, product_id) from a PriceRunner product listing URL.

    PriceRunner URL format: /pl/{categoryId}-{productId}/...
    Example: https://www.pricerunner.dk/pl/82-3332774746/Kaffemaskiner/Ninja-...
      → category_id="82", product_id="3332774746"

    Returns None if the URL doesn't match the expected pattern.
    """
    match = re.search(r"/pl/(\d+)-(\d+)", url)
    if not match:
        logger.warning("Could not extract product info from URL: %s", url)
        return None
    return match.group(1), match.group(2)


async def fetch_products_by_category(
    category_id: str,
    country: str = "DK",
    size: int = 30,
) -> list[RawProduct]:
    """
    Fetch products for a PriceRunner category, sorted by popularity.

    Uses the v4 category browse endpoint documented in
    archive/docs/pricerunner-api-reference.md. Results are cached for 24 hours
    since category data doesn't change intraday.
    """
    cache_key = f"category:{category_id}:{country}:{size}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    await _rate_limit()
    base = _base(country)
    country_upper = country.upper()
    country_lower = country.lower()

    async def _fetch():
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{base}/{country_lower}/api/search-edge-rest/public/search/category/v4/{country_upper}/{category_id}",
                params={"size": size, "sorting": "POPULARITY", "device": "desktop"},
                headers={"User-Agent": _random_ua(), "Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("products") or data.get("results") or []

    raw_products = await _with_backoff(_fetch)
    products = [_map_v4_product(p, base, category_id) for p in raw_products]
    _cache_set(cache_key, products)
    return products


async def fetch_product_from_url(url: str, country: str = "DK") -> Optional[RawProduct]:
    """
    Fetch a single product given its PriceRunner listing URL.

    Strategy:
      1. Extract category_id and product_id from the URL path
      2. Fetch up to 100 products from that category (sorted by popularity)
      3. Filter to the specific product by ID

    Why category fetch instead of a direct product endpoint:
      The public API only has a confirmed category browse endpoint. A size=100 fetch
      covers virtually all products a user would link to — if they're linking it,
      it's likely notable enough to appear in the top 100. If it doesn't appear
      (e.g. very niche or newly listed), we log a warning and return None.
    """
    info = extract_product_info_from_url(url)
    if not info:
        return None

    category_id, product_id = info
    target_id = f"pr_{product_id}"

    # Fetch up to 100 to maximise chance of finding the specific product
    products = await fetch_products_by_category(category_id, country=country, size=100)

    found = next((p for p in products if p.id == target_id), None)
    if not found:
        logger.warning(
            "Product %s not found in top 100 of category %s. "
            "It may be outside the popularity window.",
            product_id, category_id,
        )
    return found
