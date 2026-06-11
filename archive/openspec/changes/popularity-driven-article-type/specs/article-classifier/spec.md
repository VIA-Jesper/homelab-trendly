## ADDED Requirements

### Requirement: Classify product list into article type
The classifier SHALL accept a non-empty array of `RawProduct` objects (sorted by `popularityScore` descending) and return an `ArticleClassification` object containing `articleType` and `articleHook`.

Classification SHALL follow these rules in priority order:

1. **hero** - top product `popularityScore` ≥ 2× second product score (or only one product), AND `specs.popularityRank === "1"` is present or `specs.watchedLabel` is present.
2. **deal** - top product `specs.priceDrop` is present AND numeric value ≥ 10, AND `specs.watchedLabel` is present.
3. **brand-vs-brand** - top two products have different `specs.brand` values AND their `popularityScore` values are within 20% of each other.
4. **budget-tiers** - at least three products are present AND the highest `priceKr` is ≥ 2× the lowest `priceKr`.
5. **roundup** - default when no other pattern matches.

#### Scenario: Single dominant product → hero
- **WHEN** the top product has popularityScore ≥ 2× the second product AND has watchers or rank 1
- **THEN** articleType is `"hero"` and articleHook references the product name and watcher signal

#### Scenario: High-watch product with recent price drop → deal
- **WHEN** the top product has priceDrop ≥ 10% and a watchedLabel
- **THEN** articleType is `"deal"` and articleHook references the price drop percentage

#### Scenario: Two close brands → brand-vs-brand
- **WHEN** top two products are from different brands and their scores are within 20%
- **THEN** articleType is `"brand-vs-brand"` and articleHook names both brands

#### Scenario: Wide price spread → budget-tiers
- **WHEN** at least 3 products present and max price ≥ 2× min price
- **THEN** articleType is `"budget-tiers"` and articleHook references the price range

#### Scenario: No strong pattern → roundup
- **WHEN** none of the above conditions are met
- **THEN** articleType is `"roundup"` and articleHook is a generic category roundup title

#### Scenario: Empty product list → roundup default
- **WHEN** an empty array is passed
- **THEN** articleType is `"roundup"` and articleHook is a safe generic fallback

### Requirement: Article hook is a Danish-language sentence
The `articleHook` SHALL be a single Danish-language sentence suitable as an article lead or title suggestion. It SHALL reference specific product names, brands, or signals from the data rather than using generic placeholder text.

#### Scenario: Hero hook includes product name
- **WHEN** articleType is `hero`
- **THEN** articleHook contains the top product's name

#### Scenario: Deal hook includes price drop percentage
- **WHEN** articleType is `deal` and priceDrop data is available
- **THEN** articleHook contains the price drop percentage

### Requirement: Classifier is a pure function with no side effects
The classifier SHALL NOT perform any I/O, network calls, or mutations to its inputs. It SHALL be deterministic - the same input SHALL always produce the same output.

#### Scenario: Repeated calls return identical output
- **WHEN** classifyProducts is called twice with the same product array
- **THEN** both calls return identical articleType and articleHook values
