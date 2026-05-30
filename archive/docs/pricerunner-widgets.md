# PriceRunner Publisher Widgets

Reference for all available PriceRunner JS embed widgets.
Partner IDs are site-specific — see `.env` / `brief_builder.SITE_CONFIGS`.

Widget IDs must be unique per page. Convention: `pr-{scriptname}-widget-{8-char-hex}`.
Generate with `uuid4()[:8]` in Python or `randomUUID().slice(0,8)` in TS.

All widgets share the same disclosure attribution block:
```html
<div style="display: inline-block">
  <a href="https://www.pricerunner.dk/..." rel="nofollow">
    <p style="font: 14px 'Klarna Text', Helvetica, sans-serif; font-style: italic;
              color: var(--grayscale100); text-decoration: underline;">
      Annonce i samarbejde med <span style="font-weight:bold">PriceRunner</span>
    </p>
  </a>
</div>
```
The `href` should point to the product/category page (not the widget script URL).

---

## 1. product.js — Price comparison (recommended for single-product-review)

Shows 1–5 stores with their prices. Filters: in-stock only, Danish stores only.
Best used as the main CTA block in a single-product review.

```html
<div id="pr-product-widget-{id}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/product.js?onlyInStock=true&offerOrigin=NATIONAL&offerLimit=3&productId={numericProductId}&partnerId={partnerId}&widgetId=pr-product-widget-{id}"
  async></script>
```

**Query params:**
| Param | Value | Notes |
|-------|-------|-------|
| `productId` | numeric PR product ID | strip `pr_` prefix |
| `partnerId` | `adrunner_dk_husforbegyndere` | URL-encode |
| `widgetId` | matches the `div` id | must be unique per page |
| `onlyInStock` | `true` | omit to show out-of-stock |
| `offerOrigin` | `NATIONAL` | omit to include international stores |
| `offerLimit` | `1`–`5` | number of stores to show |

---

## 2. singleproduct.js — Lowest price only

Shows only the single lowest price. Simpler, good for inline mentions or tight layouts.

```html
<div id="pr-singleproduct-widget-{id}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/singleproduct.js?productId={numericProductId}&partnerId={partnerId}&widgetId=pr-singleproduct-widget-{id}"
  async></script>
```

**Query params:** `productId`, `partnerId`, `widgetId` — no filters.

---

## 3. bestprice.js — Text only (not recommended)

Renders just the product name and price as text. Minimal visual impact.
Not suitable for affiliate articles where conversion matters.

```html
<div id="pr-bestprice-widget-{id}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/bestprice.js?productId={numericProductId}&partnerId={partnerId}&widgetId=pr-bestprice-widget-{id}"
  async></script>
```

---

## 4. products.js — Multiple products (recommended for roundups/comparisons)

Shows multiple products side-by-side, each with lowest price. Takes a comma-separated
list of product IDs. Good for `roundup`, `brand-vs-brand`, `budget-tiers` article types.

```html
<div id="pr-products-widget-{id}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/products.js?productIds={id1}%2C{id2}%2C{id3}&onlyInStock=true&partnerId={partnerId}&widgetId=pr-products-widget-{id}"
  async></script>
```

**Query params:**
| Param | Value | Notes |
|-------|-------|-------|
| `productIds` | comma-separated numeric IDs | URL-encode the commas: `%2C` |
| `partnerId` | site partner ID | |
| `onlyInStock` | `true` | optional |

Attribution `href` points to `https://www.pricerunner.dk` (no specific product).

---

## 5. category.js — Category feed (good for category/hero articles)

Shows N products from a category. Can filter to only show products currently on sale
within a price-drop range. Good for category overview articles or "other options" sections.

```html
<div id="pr-category-widget-{id}" style="display: block; width: 100%"></div>
<script type="text/javascript"
  src="https://api.pricerunner.com/publisher-widgets/dk/category.js?productLimit=3&categoryId={categoryId}&partnerId={partnerId}&priceDropRange=-60_-10&widgetId=pr-category-widget-{id}"
  async></script>
```

**Query params:**
| Param | Value | Notes |
|-------|-------|-------|
| `categoryId` | numeric PR category ID | e.g. `1595` = robotplæneklippere |
| `productLimit` | integer | number of products to show |
| `partnerId` | site partner ID | |
| `priceDropRange` | e.g. `-60_-10` | optional; `-60_-10` = 10%–60% price drop |
| `onlyInStock` | `true` | optional |

Attribution `href` points to the category page:
`https://www.pricerunner.dk/cl/{categoryId}/{CategorySlug}`

---

## Widget → article type mapping

| Article type | Primary widget | Notes |
|---|---|---|
| `single-product-review` | `product.js` | 3 stores, in-stock, national |
| `roundup` | `products.js` | all reviewed products |
| `brand-vs-brand` | `products.js` | both brand products |
| `budget-tiers` | `products.js` | one per tier |
| `hero` / `deal` | `singleproduct.js` | single strong CTA |
| Category sidebar | `category.js` | use category ID from brief |

## Pipeline integration notes

- Numeric product ID: strip `pr_` prefix from `brief.products[].id`
- Category ID: extract from `_CATEGORY_SLUG` reverse map or pass through brief
- Widget inserter renders these blocks and splices them at placement anchors
- `product.js` and `products.js` are implemented in `archive/src/services/widget-inserter.ts`
  (`renderWidget()` with `singleproduct` / `product` variants)
- `category.js` and `products.js` (multi) are not yet in the Python pipeline
