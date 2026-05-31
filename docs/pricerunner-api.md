# PriceRunner API — Discovered Endpoints

Unofficial endpoints reverse-engineered from the PriceRunner DK frontend.
No auth required. All return JSON.

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
