## Context

The brief generator currently selects up to 5 products by popularity score and returns them in a `ContentBrief`. The AI writing agent receives this brief but has no instruction about what article format to use. With multiple products at similar popularity levels the AI gravitates towards a comparison structure by default — even when one product clearly dominates or when the data calls for a deal/urgency angle.

The popularity signals are already captured on every `RawProduct`: `popularityScore`, `specs.popularityRank`, `specs.watchedLabel`, and `specs.priceDrop`. The classifier has everything it needs without any additional API calls.

## Goals / Non-Goals

**Goals:**
- Classify the selected product list into one of five article types based on signal patterns
- Generate a Danish-language hook sentence the AI can use as a lead-in
- Add `articleType` and `articleHook` to `ContentBrief` so the AI receives a clear single instruction
- Keep the classifier as a pure function with no side effects or I/O

**Non-Goals:**
- Changing how the AI prompt is constructed (out of scope — prompt engineering is separate)
- Fetching additional data from PriceRunner at classification time
- Supporting more than five article types in this iteration
- Translating hooks to other languages

## Decisions

### D1 — Pure function classifier, not a service

**Decision:** Implement as a single exported function `classifyProducts(products: RawProduct[]): ArticleClassification`.

**Rationale:** The classifier has no I/O needs — all signals are on the product objects already. A pure function is trivially testable, has no lifecycle, and can be called synchronously inside `generateBrief` without async complexity.

**Alternative considered:** A separate `ArticleClassifierService` class. Rejected — adds lifecycle overhead with no benefit when there's no state or external dependency.

---

### D2 — Five article types, pattern-matched in priority order

**Decision:** The five types and their detection conditions (checked in order):

| Type | Condition | Example hook |
|---|---|---|
| `hero` | Top product score ≥ 2× second product score, rank 1, watchers present | "Danmarks mest ønskede X ifølge 200+ prisovervågere" |
| `deal` | Top product has `priceDrop` ≥ 10% AND watchers present | "Populær X er faldet X% i pris — stadig meget efterspurgt" |
| `brand-vs-brand` | Top 2 products from different brands within 20% of each other's score | "Makita eller Bosch — hvilken X vinder?" |
| `budget-tiers` | Top 3+ products span a price range ≥ 100% (cheapest × 2 ≤ most expensive) | "Bedste X til alle budgetter" |
| `roundup` | Default — no stronger pattern detected | "De bedste X i 2025" |

Priority order matters: `hero` and `deal` are checked first because they represent the clearest single-product signals. `brand-vs-brand` before `budget-tiers` because brand rivalry is a stronger editorial angle than price spread alone.

**Alternative considered:** Machine learning / scoring model. Rejected — dataset is too small and the patterns are well-understood domain rules that are easier to audit and adjust.

---

### D3 — `articleType` and `articleHook` are optional in the schema with safe defaults

**Decision:** Add both fields as `z.string().optional()` to `ContentBriefSchema`. Brief generator always sets them, but consumers that don't use them are unaffected.

**Rationale:** Avoids a breaking change for any existing test fixtures or consumers that construct `ContentBrief` objects directly.

---

### D4 — Hook is generated in Danish only

**Decision:** The hook sentence is always Danish, regardless of site locale.

**Rationale:** All configured sites currently target DK. Internationalisation of hooks is deferred until a non-DK site is configured. The hook is a suggestion, not a hard requirement — the AI can rephrase it.

## Risks / Trade-offs

- **Pattern overlap** — a product can satisfy both `deal` and `hero` conditions. Priority order (D2) resolves this deterministically, but may not always pick the most interesting angle. Mitigation: rules are easy to tune once real output is reviewed.
- **Single product edge case** — if only one product is found, the classifier always returns `hero` (one product is by definition dominant). The hook must handle this gracefully.
- **Hook quality** — generated hooks are mechanical. They provide structure but may need rewording. The AI is expected to treat the hook as a starting point, not copy it verbatim.

## Migration Plan

1. Add types to `ContentBriefSchema` (optional fields — no migration needed for existing data)
2. Implement classifier as pure function
3. Wire into `generateBrief` after product selection
4. Update affected tests
5. No deployment steps beyond normal release — no data migration, no env var changes
