# Brief - Delta Spec

## MODIFIED Requirements

### Requirement: Product Selection
The brief generator SHALL select up to 5 products matching the requested category,
filtered against the content registry to exclude products already published on the given site.
Phase 1: products from data/products.json (seeded via `npm run seed`).
Phase 2: products from PriceRunner Category Browse v4 API via live category traversal.

If category is not specified, the system SHALL select the leaf category with the most
unwritten products across all categories configured for the site.

#### Scenario: Category match with registry filtering
- **WHEN** brief generator receives category "laptops" for site "techblog"
- **THEN** returns up to 5 products where product.category === "laptops" AND product.id
  is NOT in the content registry for "techblog"

#### Scenario: Null category - system selects
- **WHEN** brief generator receives no category for site "techblog"
- **THEN** system picks the leaf category with the most unwritten products for that site

#### Scenario: No fresh products
- **WHEN** fewer than 3 unwritten products remain in the requested category for the site
- **THEN** brief generator returns error `{ error: "category_exhausted" }` instead of a brief

---

## ADDED Requirements

### Requirement: Content registry
The system SHALL maintain a per-site content registry tracking which product IDs have been
used in published articles. Registry is stored at `data/content-registry.json` as:
`{ [siteKey: string]: string[] }` - flat array of product IDs per site.

The registry SHALL be updated only when `status: "publish"` - draft articles SHALL NOT
register their products (drafts do not lock products from future briefs).

Writes SHALL be atomic: write to temp file, then rename, to prevent corruption on crash.

#### Scenario: Registry updated on publish
- **WHEN** publish_article is called with status="publish" and job completes successfully
- **THEN** all product IDs from the brief are appended to the site's registry array

#### Scenario: Registry not updated on draft
- **WHEN** publish_article is called with status="draft"
- **THEN** content registry is unchanged

#### Scenario: Registry file missing on startup
- **WHEN** data/content-registry.json does not exist
- **THEN** system treats all products as fresh (empty registry) and creates the file on first publish

---

### Requirement: PriceRunner Category Browse v4
Phase 2: the system SHALL fetch products using the Category Browse v4 API:
`GET {baseUrl}/{country}/api/search-edge-rest/public/search/category/v4/{COUNTRY}/{categoryId}
?size=30&sorting=POPULARITY&device=desktop`

Headers per request SHALL be cleared and set to only `User-Agent` (rotated) and
`Accept: application/json`. A minimum 1000ms interval SHALL be enforced between requests.
Results SHALL be cached in memory with a 24-hour TTL keyed by `pricerunner-category:{id}:{country}`.

`lowestPrice.amount` SHALL be parsed as a float (API returns it as a string).
Price fallback: `lowestPrice` first, then `cheapestOffer.price`.
Image URL fallback: `image.url` first, then `image.path`. Relative URLs prepend base URL.

Additional fields available from v4 to enrich brief: `brand.name`, `rating.average`,
`rating.count`, `ribbon.type` (TRENDING_CATEGORY, PRICE_DROP_ABSOLUTE), `priceDrop.percent`.

#### Scenario: Category products fetched live
- **WHEN** Phase 2 is active and get_brief is called with category="laptops"
- **THEN** system calls Category Browse v4 API and returns up to 5 products sorted by POPULARITY

#### Scenario: Rate limit respected
- **WHEN** two consecutive PriceRunner API calls are made
- **THEN** system enforces minimum 1000ms delay between them
