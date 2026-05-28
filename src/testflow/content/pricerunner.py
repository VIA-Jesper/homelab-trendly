"""
PriceRunner API client.

Uses PriceRunner's unofficial internal API (discovered via DevTools).
Implements UA rotation, rate limiting with jitter, exponential backoff on 429/503,
and 24h disk cache for products (30d for category trees).
"""
import time
import json
import random
import httpx
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from testflow.models import PRProduct

CACHE_DIR = Path("cache/pricerunner")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


def _is_retryable(exc: Exception) -> bool:
    return (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {429, 503}
    ) or isinstance(exc, httpx.TimeoutException)


class PriceRunnerClient:
    BASE_SEARCH = "https://www.pricerunner.dk/dk/api/search-edge-rest"
    BASE_SEO = "https://www.pricerunner.dk/dk/api/seo-edge-rest"
    RATE_LIMIT_SEC = 1.5
    JITTER_MAX = 0.8

    def __init__(self, cache_dir: Path | None = None):
        self._last_request = 0.0
        self._session = httpx.Client(timeout=15)
        self._cache_dir = cache_dir or CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(UA_POOL),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.pricerunner.dk/",
            "Origin": "https://www.pricerunner.dk",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=2, min=3, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> dict:
        elapsed = time.time() - self._last_request
        wait = self.RATE_LIMIT_SEC + random.uniform(0.0, self.JITTER_MAX)
        if elapsed < wait:
            time.sleep(wait - elapsed)
        resp = self._session.get(url, params=params, headers=self._get_headers())
        self._last_request = time.time()
        resp.raise_for_status()
        return resp.json()

    def fetch_products_by_category(
        self, category_id: int, limit: int = 10, sorting: str = "POPULARITY"
    ) -> list[PRProduct]:
        cache_path = self._cache_dir / f"products-{category_id}.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 86400:
            raw = json.loads(cache_path.read_text())
        else:
            url = f"{self.BASE_SEARCH}/public/search/category/v4/DK/{category_id}"
            raw = self._get(url, {"size": limit, "sorting": sorting, "device": "desktop"})
            cache_path.write_text(json.dumps(raw))
        return self._parse_products(raw, category_id)

    def fetch_category_tree(self, topic_id: str) -> dict:
        cache_path = self._cache_dir / f"tree-{topic_id}.json"
        if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < 2_592_000:
            return json.loads(cache_path.read_text())
        url = f"{self.BASE_SEO}/public/navigation/menu/DK/hierarchy/{topic_id}"
        data = self._get(url)
        cache_path.write_text(json.dumps(data))
        return data

    def discover_categories(self, query: str) -> list[dict]:
        """Search PriceRunner's category tree for categories matching a query."""
        url = f"{self.BASE_SEO}/public/navigation/menu/DK/hierarchy/1"
        data = self._get(url)
        query_lower = query.lower()
        matches: list[dict] = []

        def walk(node: dict, parent_name: str = "") -> None:
            name = node.get("name", "")
            node_id = node.get("id", "")
            numeric_id = node_id.lstrip("clt").split("-")[0]
            if query_lower in name.lower() and numeric_id.isdigit():
                matches.append({
                    "name": name,
                    "id": int(numeric_id),
                    "parent": parent_name,
                    "raw_id": node_id,
                })
            for child in node.get("children", []):
                walk(child, parent_name=name)

        for top_node in data.get("children", []):
            walk(top_node)

        return sorted(matches, key=lambda m: len(m["name"]))

    def _parse_products(self, raw: dict, category_id: int | None) -> list[PRProduct]:
        """Parse API response into PRProduct list."""
        results = []
        for item in raw.get("products", raw.get("items", [])):
            try:
                # Handle nested price objects or flat fields
                price_obj = item.get("price", {})
                price_min = (
                    price_obj.get("min") if isinstance(price_obj, dict)
                    else item.get("minPrice", {}).get("amount", 0) if isinstance(item.get("minPrice"), dict)
                    else item.get("minPrice", 0)
                )
                price_max = (
                    price_obj.get("max") if isinstance(price_obj, dict)
                    else item.get("maxPrice", {}).get("amount", 0) if isinstance(item.get("maxPrice"), dict)
                    else item.get("maxPrice", 0)
                )
                # Handle nested rating object
                rating_raw = item.get("rating")
                if isinstance(rating_raw, dict):
                    rating = rating_raw.get("score")
                    review_count = rating_raw.get("count")
                else:
                    rating = rating_raw
                    review_count = item.get("reviewCount")
                # Handle nested image object
                image_raw = item.get("image", {})
                image_url = (
                    image_raw.get("url") if isinstance(image_raw, dict)
                    else item.get("imageUrl", "")
                )
                product_url = "https://www.pricerunner.dk" + item.get("url", "")
                # Handle nested category
                cat_raw = item.get("category", {})
                cat_name = (
                    cat_raw.get("name", "") if isinstance(cat_raw, dict)
                    else item.get("categoryName", "")
                )
                results.append(PRProduct(
                    id=str(item["id"]),
                    name=item["name"],
                    price_min=float(price_min or 0),
                    price_max=float(price_max or 0),
                    url=product_url,
                    image_url=image_url or "",
                    rating=float(rating) if rating is not None else None,
                    review_count=int(review_count) if review_count is not None else None,
                    merchant_count=item.get("merchantCount", 0),
                    category_id=category_id or 0,
                    category_name=cat_name,
                ))
            except Exception:
                pass
        return results


def filter_by_explicit(products: list[PRProduct], explicit: list[str]) -> list[PRProduct]:
    """Case-insensitive substring match. Returns products matching any explicit name."""
    if not explicit:
        return products
    matched = []
    for product in products:
        if any(ep.lower() in product.name.lower() for ep in explicit):
            matched.append(product)
    return matched
