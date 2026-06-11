# Brief - Content Brief Generation Rules

## Requirements

### REQ-BRIEF-001 - Product Selection
The brief generator SHALL select up to 5 fresh products for the requested category.
Products already published for the given site (per content registry) are excluded.
If fewer than 3 fresh products remain, the generator SHALL return a structured error
instead of a brief.

### REQ-BRIEF-002 - Brief Structure
Every brief SHALL contain: brief_id, category, products (max 5), images,
writing_rules, compliance, articleType, articleHook.

### REQ-BRIEF-003 - Writing Rules
Defaults: tone=neutral, min_words=600, max_words=1200,
include_pros_cons=true, include_verdict=true.
Site config overrides defaults per site key.

### REQ-BRIEF-004 - Image Rules
Each image reference SHALL include: url, alt (product name + brand),
caption (product + retailer + price in DKK).

### REQ-BRIEF-005 - Product Data Sources (priority order)
1. Live PriceRunner v4 API - primary source, called on every request.
   - Category traversal resolves configured root categories to leaf categories automatically.
   - Results are cached in memory for 24 hours per category ID + country.
   - Rate limited to minimum 1000ms between requests.
2. Direct category ID fetch - used when agent provides a specific PR category ID
   (e.g. from dynamic category discovery).
3. Local product store (data/products.json) - fallback only, used when live API is
   unavailable or the category is not found via traversal.

### REQ-BRIEF-006 - Article Classification
After product selection the brief generator SHALL call the article classifier to determine
the article type (hero, deal, brand-vs-brand, budget-tiers, roundup) and generate a
Danish article hook. Both SHALL be included in the returned brief.

### REQ-BRIEF-007 - Category Auto-Selection
When no category is specified, the generator SHALL call the category discoverer to find
the leaf category with the most unwritten (fresh) products for the given site. If all
categories are exhausted, it returns { error: "all_categories_exhausted" }.

## Scenarios

### Scenario: Category provided, fresh products available
GIVEN the brief generator receives category "laptops" and site "techblog"
WHEN it fetches from PriceRunner and filters by content registry
THEN it returns a brief with up to 5 fresh products, articleType, and articleHook

### Scenario: Category exhausted
GIVEN category "laptops" has fewer than 3 fresh products for site "techblog"
WHEN the generator checks after filtering
THEN it returns { error: "category_exhausted", category: "laptops" }

### Scenario: Auto-selection when no category given
GIVEN no category is specified
WHEN the generator calls the category discoverer
THEN it selects the leaf category with the most unwritten products

### Scenario: Live API unavailable
GIVEN the PriceRunner API is unreachable
WHEN the generator attempts a live fetch
THEN it falls back to the local product store (data/products.json)
