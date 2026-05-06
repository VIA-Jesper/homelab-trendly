# Brief — Content Brief Generation Rules

## Requirements

### REQ-BRIEF-001 — Product Selection
The brief generator SHALL select up to 5 products matching the requested category.
Phase 1: products from data/products.json (real PriceRunner data seeded via `npm run seed`).
Phase 2: products from PriceRunner API or scraped product pages.

### REQ-BRIEF-002 — Brief Structure
Every brief SHALL contain: brief_id, category, products (max 5), images,
writing_rules, compliance.

### REQ-BRIEF-003 — Writing Rules
Defaults: tone=neutral, min_words=600, max_words=1200,
include_pros_cons=true, include_verdict=true.
Site config overrides defaults.

### REQ-BRIEF-004 — Image Rules
Each image reference SHALL include: url, alt (product name + key spec),
caption (product + retailer + price).

### REQ-BRIEF-005 — Phase Boundary
Phase 1: read from data/products.json (real PriceRunner data, seeded via `npm run seed`).
  - The seed script calls PriceRunner with backoff + UA rotation and writes results to disk.
  - The server reads from this snapshot at startup — no live calls during Phase 1 runtime.
Phase 2: brief-generator.ts calls pricerunner-client.ts directly on every request (live calls).

## Scenarios

### Scenario: Category match
GIVEN the brief generator receives category "laptops"
WHEN it queries the product store
THEN it returns up to 5 products where product.category === "laptops"

### Scenario: No products found
GIVEN category "unicycles"
WHEN it queries the product store
THEN it returns an empty products array (no error thrown)
