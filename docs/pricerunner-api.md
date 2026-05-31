# PriceRunner API — Discovered Endpoints

Unofficial endpoints reverse-engineered from the PriceRunner DK frontend.
No auth required. All return JSON.

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

### husforbegyndere.dk category IDs

| Category ID | Name               |
|-------------|--------------------|
| cl82        | Kaffemaskiner      |
| cl120       | Havemaskiner       |
| cl335       | Grill              |
| cl638       | Højtryksrensere    |
| cl1595      | Robotplæneklippere |
| cl1613      | Robotstøvsugere    |

Script: `scripts/fetch_hot_products.py`
