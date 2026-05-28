## MODIFIED Requirements

### Requirement: Brief Structure
Every brief SHALL contain: brief_id, category, products (max 5), images,
writing_rules, compliance, articleType, articleHook.

`articleType` SHALL be one of: `"hero"`, `"deal"`, `"brand-vs-brand"`, `"budget-tiers"`, `"roundup"`.
`articleHook` SHALL be a non-empty Danish-language string.

Both fields are optional in the schema for backward compatibility but SHALL always be populated by the brief generator.

#### Scenario: Brief includes article type and hook
- **WHEN** the brief generator completes product selection
- **THEN** the returned brief contains a non-empty articleType and articleHook

#### Scenario: Brief with no products defaults to roundup
- **WHEN** no products are found for the requested category
- **THEN** articleType is `"roundup"` and articleHook is a safe generic fallback

## MODIFIED Requirements

### Requirement: Product Selection
The brief generator SHALL select up to 5 products matching the requested category.
Products SHALL be filtered to exclude out-of-stock items.
Products SHALL be sorted by `popularityScore` descending before selection.
After selection, the brief generator SHALL call the article classifier to determine `articleType` and `articleHook`.

Phase 1: products from data/products.json (real PriceRunner data seeded via `npm run seed`).
Phase 2: products from PriceRunner API or scraped product pages.

#### Scenario: Category match with popularity sort
- **WHEN** the brief generator receives category "laptops" and products exist with varying popularityScore
- **THEN** it returns up to 5 products ordered by popularityScore descending

#### Scenario: Out-of-stock products excluded
- **WHEN** some products in the category have outOfStock = true
- **THEN** those products are not included in the brief

#### Scenario: No products found
- **GIVEN** category "unicycles"
- **WHEN** it queries the product store
- **THEN** it returns an empty products array and articleType "roundup" (no error thrown)
