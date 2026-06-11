# PriceRunner API Reference

> Discovered endpoints and data shapes for the Danish affiliate pipeline.
> Last updated: 2026-05-22

## Endpoints

### 1. Category Browse (products by category ID)

```
GET https://www.pricerunner.dk/dk/api/search-edge-rest/public/search/category/v4/DK/{categoryId}
Params: ?size=30&sorting=POPULARITY&device=desktop
Headers: User-Agent (browser), Accept: application/json
```

**Returns:** Products with prices, ratings, popularity ribbons, merchant counts.
**Use case:** Fetching products for article generation. Already used by `PriceRunnerClient`.
**Key field:** `category.path` shows parent hierarchy (e.g. 34 → 3 → 1613).

---

### 2. Navigation Menu (category tree discovery) ⭐

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/navigation/menu/DK/hierarchy/{topicId}
Headers: User-Agent (browser), Accept: application/json
```

**Returns:** Full category tree under a topic.
**Use case:** Discover all leaf categories under a broad topic like "Hjem & Husholdning" (t34).
**Key fields:**
- `categories[].id` - topic or leaf category ID
- `categories[].children[]` - leaf categories (cl-prefixed) or sub-topics
- `categories[].children[].id` - leaf category IDs like `cl82`, `cl250`

**Notes:**
- Some children IDs are compound (e.g. `100003649-100015017`) - these are filter combinations, skip them.
- Topics have `id` like `t34`, `t1424`. Leaf categories have `id` like `cl82` (the numeric part is the API category ID).
- The tree is essentially static. Scrape once, cache indefinitely. Refresh only if PriceRunner reorganizes.

---

### 3. Breadcrumbs

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/navigation/breadcrumbs/DK/{topicId}
```

**Returns:** Array of `{id, name, url}` representing the path to the topic.
**Use case:** Minimal. Shows topic ancestry. Less useful than `menu` endpoint.

---

### 4. Popular Products (cross-category trending)

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/popularproducts/v3/DK/{topicId}
```

**Returns:** ~15 trending products across ALL subcategories of a topic.
**Use case:** Identify breakout products across categories. Could inform which categories deserve new articles.
**Note:** Products have `categoryName: null` - you can't tell which subcategory they belong to without parsing the product URL.

---

### 5. Keyword Tree (search trends)

```
GET https://www.pricerunner.dk/dk/api/seo-edge-rest/public/keyword/tree/DK/{topicId}
```

**Returns:** ~50 popular search keywords with their landing page URLs.
**Use case:** SEO/content planning. Shows what users are actively searching for.

---

## Category ID Conventions

| Prefix | Meaning | Example |
|--------|---------|---------|
| `t` | Topic (has children) | `t34` = Hjem & Husholdning |
| `cl` | Leaf category (products) | `cl82` = Kaffemaskiner |
| `{n}-{n}` | Filter combination | `100003649-100015017` = skip these |

**API category ID** for `fetchProductsByCategoryId` is the numeric part after `cl`. So `cl82` → use `82`.

## Verified Topic Trees

### t34 - Hjem & Husholdning

**t14: Køkkenapparater**
- cl1617: Andre køkkenapparater
- cl90: Bagemaskiner
- cl84: Blendere
- cl69: Brødristere
- cl10025: Dehydratorer
- cl81: Frituregryder & Airfryere
- cl10027: Gasbrændere
- cl104: Håndmixere
- cl250: Ismaskiner
- cl479: Isterningmaskiner
- cl83: Juicere
- cl621: Kaffekværne
- cl82: Kaffemaskiner
- cl10023: Kødhakkere
- cl248: Køkkenvægte
- cl249: Madkogere
- cl10024: Minihakkere & Spiralizere
- cl10022: Pastamaskiner
- cl10020: Popcornmaskiner
- cl10026: Pålægsmaskiner
- cl1244: Røremaskiner & Foodprocessorer
- cl88: Sandwichgrill
- cl1312: Sodavandsmaskiner
- cl85: Stavblendere
- cl333: Vaffeljern
- cl10021: Vakuumpakkere
- cl68: Vandkedel

**t3: Hvidevarer**
- cl21: Emhætter
- t1550: Komfur & Ovne (sub-topic)
- t1500: Køleskabe & Fryseskabe (sub-topic)
- cl3: Mikrobølgeovne
- cl13: Opvaskemaskiner
- cl1613: Robotstøvsugere
- cl19: Støvsugere
- cl212: Støvsugertilbehør
- cl715: Tilbehør til hvidevarer
- cl740: Tørreskab
- cl17: Tørretumblere
- cl14: Vaskemaskiner

**t1426: Hus**
- cl516: Alarmer & Sikkerhed
- cl528: Batterier & Opladere
- cl453: Indeklima
- cl456: Kæledyr
- cl1274: Lommelygter
- cl589: Overvågningskameraer
- cl628: Rengøringsudstyr & -Midler
- cl80: Strygejern & Steamere
- cl550: Symaskiner
- cl590: Termometre & Vejrstationer
- cl357: Tøjpleje
- cl401: Ventilatorer
- cl1404: Vækkeure

**t1424: Have & Udemiljø**
- cl1595: Robotplæneklippere
- cl335: Grill
- cl659: Grilltilbehør
- cl120: Havemaskiner
- cl519: Krukker, Planter & Dyrkning
- cl119: Plæneklippere
- cl347: Haver & Udemiljøer
- cl638: Højtryks- & Hedvandsrensere
- cl348: Haveredskaber
- cl499: Havemøbler
- cl1467: Tilbehør til havemaskiner
- cl504: Drivhuse
- cl1611: Havetraktorer
- cl541: Pools
- cl1388: Spabade & Vildmarksbade
- cl10018: Udekøkkener
- cl1593: Sneslynger

## Verified Leaf Categories (husforbegyndere.dk)

| ID | Name | Verified |
|----|------|----------|
| 1595 | Robotplæneklippere | ✅ |
| 335 | Grill | ✅ |
| 120 | Havemaskiner | ✅ |
| 638 | Højtryks- & Hedvandsrensere | ✅ |
| 345 | Elværktøj | ✅ |
| 1260 | Elsave | ✅ |
| 1258 | Bore- & Skruemaskiner | ✅ |
| 250 | Ismaskiner | ✅ |
| 81 | Frituregryder & Airfryere | ✅ |
| 82 | Kaffemaskiner | ✅ |
| 14 | Vaskemaskiner | ✅ |
| 1613 | Robotstøvsugere | ✅ |

## Rate Limiting

- Minimum 1000ms between requests (already enforced by `PriceRunnerClient`)
- Use browser User-Agent rotation
- Cache results for 24 hours

## Future Work

- Build `discoverCategories(topicId)` function that recursively walks the tree and returns all leaf category IDs
- Cache tree results to disk (they're essentially static)
- Use `popularproducts` to identify trending categories that might need new articles
