## 1. Types

- [x] 1.1 Add `ArticleType` enum and `ArticleClassification` type to `src/types/index.ts`
- [x] 1.2 Add `articleType` (optional string enum) and `articleHook` (optional string) to `ContentBriefSchema` in `src/types/index.ts`

## 2. Classifier

- [x] 2.1 Create `src/services/article-classifier.ts` with exported `classifyProducts(products: RawProduct[]): ArticleClassification`
- [x] 2.2 Implement `hero` detection: top score ≥ 2× second score AND (watchers present OR rank 1)
- [x] 2.3 Implement `deal` detection: top product priceDrop ≥ 10% AND watchedLabel present
- [x] 2.4 Implement `brand-vs-brand` detection: top two products different brands, scores within 20%
- [x] 2.5 Implement `budget-tiers` detection: 3+ products, max price ≥ 2× min price
- [x] 2.6 Implement `roundup` as default fallback
- [x] 2.7 Implement Danish hook generation for each article type using product name, brand, and signal data
- [x] 2.8 Handle edge cases: empty array, single product, missing specs fields

## 3. Brief Generator Integration

- [x] 3.1 Import `classifyProducts` in `src/services/brief-generator.ts`
- [x] 3.2 Call `classifyProducts(rawProducts)` after product selection, before building return value
- [x] 3.3 Include `articleType` and `articleHook` in the returned `ContentBrief`
- [x] 3.4 Ensure internal fields (`imageUrl`, `popularityScore`, `outOfStock`) are still stripped from `ProductBrief` in the brief output

## 4. Tests

- [x] 4.1 Create `tests/unit/article-classifier.test.ts` covering all five article types
- [x] 4.2 Add scenarios: empty array, single product, missing specs fields, ties in score
- [x] 4.3 Update `tests/unit/brief-generator.test.ts` to assert `articleType` and `articleHook` are present in returned brief
- [x] 4.4 Run `npm test` — all tests pass
