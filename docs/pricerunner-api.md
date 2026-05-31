# PriceRunner API — Discovered Endpoints

Unofficial endpoints reverse-engineered from the PriceRunner DK frontend.
No auth required. All return JSON.

Reference: https://github.com/Daniel6702/OpenPriceRunnerAPI (reverse-engineered wrapper, MIT)
May be worth forking — contains retry logic, price history, reviews, offers, and keyword endpoints
we haven't explored yet. License is permissive.

## Known base URLs

| Base URL | Used for |
|----------|----------|
| `https://www.pricerunner.dk/dk/api/search-compare-gateway/public` | Product data, reviews, price history, offers, hot products (OpenPriceRunnerAPI base) |
| `https://www.pricerunner.dk/dk/api/search-edge-rest/public` | Hot products (confirmed working) |
| `https://www.pricerunner.dk/dk/api/seo-edge-rest/public` | Navigation / category tree |

All endpoints below should be prefixed with the appropriate base URL.

---

## Navigation / Category discovery

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/navigation/menu/DK
```
Returns full category tree — all top-level groups (t/ prefix) and subcategories (cl/ prefix).

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/navigation/menu/DK/hierarchy/{id}
```
Returns subcategory list for a specific top-level group. Use `t{id}` format (e.g. `t14`, `t1424`).

### How to find a category ID

1. Browse to the category on pricerunner.dk — note the URL: `/cl/345/Elvaerktoej` → ID is `cl345`
2. Or fetch the full tree: `GET .../navigation/menu/DK` → search the JSON for the category name
3. Or fetch a top-level group: `GET .../navigation/menu/DK/hierarchy/t14` → lists all subcategory IDs and names under that group
4. Verify the ID works: `GET .../hot/products/v2/DK/cl345?size=3` — empty means wrong ID

**Top-level groups relevant to husforbegyndere.dk:**

| ID    | Name                  |
|-------|-----------------------|
| t14   | Køkkenapparater       |
| t3    | Hvidevarer            |
| t1424 | Have & Udemiljø       |
| t1426 | Hus                   |
| t1550 | Komfur & Ovne         |
| t1500 | Køleskabe & Fryseskabe|

---

## Product detail (used by pipeline)

```
GET https://www.pricerunner.dk/dk/api/search-edge-rest/public/pl/v5/DK/{productId}?currency=DKK
```

Returns full product data: name, specs, prices, images, affiliate URL.
Used by `brief_builder.py` to build a ContentBrief from a PriceRunner product URL.

---

## Hot products (trending)

```
GET https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK?size=N
```

Returns the top N trending products across all categories.
Ranked by watcher count / purchase intent signals.

### Filter by category

```
GET https://www.pricerunner.dk/dk/api/search-edge-rest/public/hot/products/v2/DK/{categoryId}?size=N
```

`categoryId` uses the `cl{id}` format from the product response (e.g. `cl1595` for Robotplæneklippere).

**Top-level category groups** (broader buckets, use `t{id}` format):
| ID   | Contents                                      |
|------|-----------------------------------------------|
| t2   | Electronics (tablets, laptops, PC components) |
| t3   | Vacuums & robot vacuums                       |
| t4   | Mobile phones                                 |
| t9   | PC components (GPUs, CPUs, RAM)               |
| t10  | Beauty & personal care                        |
| t11  | Automotive & EV chargers                      |
| t14  | Kitchen appliances                            |

### Key response fields

```json
{
  "id": "3292855103",
  "name": "Segway Navimow i105E",
  "url": "/pl/1595-3292855103/...",
  "lowestPrice": {"amount": "5749.00", "currency": "DKK"},
  "category": {"id": "cl1595", "name": "Robotplæneklippere"},
  "image": {"path": "/product/{imageId}/{slug}.jpg"},
  "rank": {"rank": 4, "trend": "MISSING"},
  "ribbon": {"type": "WATCHED", "value": "1000+"},
  "rating": {"averageRating": "4.80", "numberOfRatings": 51},
  "outOfStock": false
}
```

Image full URL: `https://www.pricerunner.dk{image.path}`

### Product discovery use case

Fetch hot products per category daily → log to `data/hot-products.jsonl` →
spot products with high watcher counts in site-relevant categories →
use product URL to trigger a new article job via `POST /api/v1/jobs/from-url`.

Future: track `rank` and `watchers` over time to detect rising trends before
they peak — articles written early rank better than articles written after the spike.

### husforbegyndere.dk category IDs (verified)

All IDs verified via `/navigation/menu/DK` and `/navigation/menu/DK/hierarchy/{id}`.

**Garden & outdoor (t1424):**
| Category ID | Name                        | Notes |
|-------------|-----------------------------|-------|
| cl1595      | Robotplæneklippere          |       |
| cl119       | Plæneklippere               |       |
| cl1611      | Havetraktorer               |       |
| cl120       | Havemaskiner                |       |
| cl335       | Grill                       |       |
| cl638       | Højtryks- & Hedvandsrensere |       |
| cl1290      | Trampoliner                 |       |
| cl541       | Pools                       |       |
| cl1388      | Spabade & Vildmarksbade     |       |
| cl348       | Haveredskaber               | Uncertain — may be need-based, not review intent |
| cl499       | Havemøbler                  |       |

**Power tools:**
| Category ID | Name                | Notes |
|-------------|---------------------|-------|
| cl345       | Elværktøj           |       |
| cl1258      | Bore-Skruemaskiner  |       |
| cl1260      | Elsave              |       |

**Hvidevarer (t3):**
| Category ID | Name              | Notes |
|-------------|-------------------|-------|
| cl1613      | Robotstøvsugere   |       |
| cl19        | Støvsugere        |       |
| cl13        | Opvaskemaskiner   |       |
| cl14        | Vaskemaskiner     |       |
| cl17        | Tørretumblere     |       |
| cl101       | Komfurer          |       |
| cl105       | Ovne              |       |
| cl106       | Kogeplader        |       |
| cl3         | Mikrobølgeovne    |       |

**Kitchen appliances — use t14 to fetch all at once:**
| Category ID | Name                        |
|-------------|-----------------------------|
| t14         | Køkkenapparater (alle)      |
| cl82        | Kaffemaskiner               |
| cl81        | Frituregryder & Airfryere   |
| cl250       | Ismaskiner                  |
| cl84        | Blendere                    |
| cl1244      | Røremaskiner & Foodprocessorer |

Script: `scripts/fetch_hot_products.py`

---

## Additional endpoints (from OpenPriceRunnerAPI — base: search-compare-gateway/public)

These are documented in the reference repo but not yet tested in our pipeline.

### Product endpoints

| Endpoint | Description | Params |
|----------|-------------|--------|
| `/productlistings/pl/initial/{subcategoryId}-{productId}/DK` | Full product listing data | — |
| `/productlistings/rank/DK/{productId}` | Product rank | — |
| `/keyword/product/DK/{subcategoryId}-{productId}` | SEO keywords for a product | — |
| `/product-detail/v0/offers/DK/{productId}` | Merchant offers/prices | `af_ORIGIN`, `af_ITEM_CONDITION`, `sortByPreset`, `af_MERCHANT` |
| `/pricehistory/product/{productId}/DK/DAY` | Price history | `merchantId`, `selectedInterval` (e.g. `THREE_MONTHS`), `filter` |
| `/reviews/products/overview/DK/{productId}` | User reviews | `count` |
| `/listings/products/DK` | Batch product listings | `productIds` (comma-separated) |
| `/productinfo/DK` | Batch product info | `productIds`, `withShipping`, `onlyPayingMerchants`, `onlyCertifiedMerchants` |
| `/hot/products/v2/DK` | Hot/trending products | `size` |

### Category endpoints

| Endpoint | Description | Params |
|----------|-------------|--------|
| `/navigation/menu/DK/items` | Top-level categories | — |
| `/navigation/menu/DK` | Full category tree | — |
| `/navigation/menu/DK/hierarchy/{categoryId}` | Subcategories for a group | — |
| `/navigation/breadcrumbs/DK/{categoryId}` | Breadcrumb trail | — |
| `/keyword/tree/DK/{categoryId}` | SEO keywords for a category | — |
| `/keyword/category/DK/{subcategoryId}` | SEO keywords for subcategory | — |
| `/popularproducts/v2/DK/{categoryId}` | Popular products (all-time vs hot=trending) | — |
| `/search/category/v3/DK/{subcategoryId}` | Products in category with filters | `size`, dynamic filter pairs |
| `/search/guidingcontent/v2/DK/{subcategoryId}` | Buying guides for a category | `size` |
| `/search/board/DK/{subcategoryId}` | Category boards/featured | `size` |

### HTTP client notes (from repo)

- Default headers: `User-Agent: Chrome`, `Accept: application/json`
- Retry logic: exponential backoff on failure; 60s pause on 429/403
- No auth required
