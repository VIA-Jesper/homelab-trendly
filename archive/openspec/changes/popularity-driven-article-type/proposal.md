## Why

Products are selected by popularity score but every article is still written with the same neutral framing - the AI has no instruction about what kind of article to produce. When multiple products are passed with similar standing, the AI defaults to a comparison structure even when the data calls for something else (a hero deep-dive, a budget roundup, a deal alert). The article type should be derived from the signal pattern in the data, not left to chance.

## What Changes

- A **classifier** analyses the `popularityScore`, `rank`, `watchedLabel`, and `priceDrop` fields of the selected products and determines the appropriate `articleType` and a ready-made `articleHook`.
- `ContentBrief` gains two new fields: `articleType` (enum) and `articleHook` (string).
- The brief generator calls the classifier after product selection and before returning the brief.
- The AI receives a single unambiguous instruction on what format to produce, instead of raw competing signals.
- **No breaking change** to existing API consumers - both new fields are optional with safe defaults.

## Capabilities

### New Capabilities
- `article-classifier`: Classifies a ranked product list into one of five article types and generates a Danish-language hook sentence. Lives as a pure function alongside the brief generator.

### Modified Capabilities
- `brief`: REQ-BRIEF-002 changes - `ContentBrief` structure gains `articleType` and `articleHook`. REQ-BRIEF-001 changes - product selection now feeds into classification before the brief is returned.

## Impact

- `src/types/index.ts` - `ContentBriefSchema` and `ContentBrief` gain two fields
- `src/services/brief-generator.ts` - calls classifier after `getProductsByCategory`
- `src/services/article-classifier.ts` - new file (pure function, no I/O)
- `openspec/specs/brief/spec.md` - updated requirements
- `tests/unit/brief-generator.test.ts` - existing tests need new field assertions
- `tests/unit/article-classifier.test.ts` - new unit tests for classifier logic
