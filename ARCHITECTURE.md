# Architecture — Danish Affiliate Content Pipeline

> **Agent orientation:** Read this file first. It explains why the system is built the way it is, what tradeoffs were accepted, and where the sharp edges are. Cross-reference `FLOW.md`, `WIDGET-SYSTEM-REFERENCE.md`, and `PRICERUNNER-SCRAPER-REFERENCE.md` for operational detail.

---

## What this system does

Automated Danish affiliate article pipeline. Given a PriceRunner product category, it:
1. Fetches live product data (prices, rankings, watcher counts) via `PriceRunnerClient`
2. Classifies the data into one of 6 article formats (`ArticleClassifier`)
3. Builds a structured content brief (`BriefBuilder`)
4. Runs a multi-agent generation + review loop (orchestrated via `FLOW.md`)
5. Validates compliance, SEO, CRO, and Danish voice quality (`validate-article.ts`)
6. Renders widgets and affiliate links into the final HTML
7. (Future) Publishes to WordPress via REST API

The output is a publish-ready JSON object (`article` + `placements` + `seo`) that maps to a WordPress post.

---

## System map

```
PriceRunner API
    │
    ▼
PriceRunnerClient         scraper/pricerunner-client.ts
    │
    ▼
BriefBuilder              services/brief-builder.ts
  └─ ArticleClassifier    services/article-classifier.ts
  └─ DuplicateGuard       services/duplicate-guard.ts
    │
    ▼
ContentBrief (JSON)       types/index.ts → ContentBriefSchema
    │
    ├──► Generator Agent (ACP, ask-mode)
    │       base: prompts/agents/generator.md
    │       + type module: prompts/agents/generator-types/$TYPE.md
    │       output: article JSON
    │
    ├──► Validator (local script)
    │       scripts/validate-article.ts
    │       reads type rules from: config/article-types.json
    │
    ├──► Reviewer Agents ×3 (ACP, parallel, ask-mode)
    │       SEO / CRO / Voice
    │       output: critique JSON with verdict + issues
    │
    ├──► Critiquer Agent (ACP, ask-mode)
    │       merges all critiques → revised article JSON
    │
    └──► insertPlacements → convertMarkdownToHtml → insertAffiliateLinks
             services/widget-inserter.ts
             services/affiliate-linker.ts
             output: final HTML for WordPress or preview
```

---

## Article types

Six formats. Classifier selects automatically; orchestrator can override via `$ARTICLE_TYPE`.

| Type | Trigger signal | Key constraint |
|---|---|---|
| `roundup` | 3-5 products, mixed popularity | ≥80 words per product section |
| `hero` | 1 dominant product (rank 1, high watchers) | Star product gets full treatment; brief alternatives |
| `deal` | Price drop ≥15% on any product | Short (450-700w), urgency-first |
| `brand-vs-brand` | 2 products from different brands | Must include comparison table + winner |
| `budget-tiers` | Products spanning ≥2 price brackets | Bracket structure: budget / mid / premium |
| `single-product-review` | Exactly 1 product in brief | Pros/Cons/Verdict structure required |

Type-specific numerics (word counts, AI-tells, CRO weights) live in `config/article-types.json`.
Type-specific writing instructions live in `prompts/agents/generator-types/$TYPE.md`.

---

## Architectural decisions

### ADR-001 · Ask-mode sub-agents only
**Date:** 2025 (initial)
**Decision:** All ACP sub-agents run with `"mcpServers": []` and no mutating tools.
**Reasoning:** Sub-agents are untrusted text producers. Allowing them file-write access would let a prompt-injected brief corrupt prompts or code. The orchestrator is the sole writer.
**Consequence:** Every sub-agent output must be collected as text and validated by the orchestrator before writing. JSON parse errors must be handled explicitly.

### ADR-002 · Prompt composition: base + type module concatenation
**Date:** 2025
**Decision:** Generator prompt = `generator.md` (universal rules) + `generator-types/$TYPE.md` (structural instructions), concatenated by the orchestrator at runtime.
**Reasoning:** A single monolithic generator prompt would require every rule to be conditioned on article type, making the prompt unmaintainable. Separation lets each type module be reasoned about independently and updated without touching universal rules.
**Consequence:** The orchestrator must always read and concatenate both files. The type module is authoritative for structure; `generator.md` is authoritative for universal rules. Conflicts: type module wins.

### ADR-003 · Config-driven validation numerics
**Date:** 2025
**Decision:** Word count ranges, CRO weight tables, and AI-tell lists live in `config/article-types.json`, not hardcoded in `validate-article.ts`.
**Reasoning:** Validation thresholds are tuned iteratively. Hardcoding them causes a code change every time a threshold is adjusted after testing. JSON config means prompt engineers can tune without touching TypeScript.
**Consequence:** `validate-article.ts` calls `getTypeRules(type)` from `article-type-config.ts` for every numeric check. Any new type must have an entry in `config/article-types.json` or validation will throw.

### ADR-004 · Agent-directed placement (not auto-insertion)
**Date:** 2025
**Decision:** The generator specifies widget and image positions explicitly via the `placements` array (`after_paragraph` index). The inserter executes them. There is no auto-detection of "best position".
**Reasoning:** Auto-insertion based on product mention detection (the legacy C# approach in `WIDGET-SYSTEM-REFERENCE.md`) produced unpredictable results when articles had non-standard structure. The generator agent understands the article structure it just wrote and can make better placement decisions.
**Consequence:** If the generator outputs an `after_paragraph` index that exceeds the article's paragraph count, `insertPlacements` clamps it to the last paragraph. Validators should warn but not fail on clamped placements.

### ADR-005 · Widget dual-rendering: PriceRunner embed vs Tailwind fallback
**Date:** 2026-05
**Decision:** `renderWidget` emits actual PriceRunner JS embed HTML (`product.js` / `singleproduct.js`) when `pricerunnerPartnerId` is set. Falls back to a styled Tailwind card when the env var is absent (local dev / test).
**Reasoning:** The preview server and production WordPress post use the same `insertPlacements` function. Using real PriceRunner embeds in production pulls live prices. The Tailwind fallback enables offline development without requiring partner credentials.
**Consequence:** Widget appearance in preview differs from production when partnerId is not set. The fallback card is intentionally styled to match the embed's approximate footprint. Tests that assert `rel="sponsored"` pass against both paths.

### ADR-006 · Widget variant alternation
**Date:** 2026-05
**Decision:** The first widget in article order uses `singleproduct.js` (lowest price, strong single CTA). Subsequent widgets alternate to `product.js` (top 3 offers), then back.
**Reasoning:** The first widget is typically the star product — a single lowest-price CTA converts better there. Later widgets (alternatives, roundup products) benefit from multi-offer display for comparison. The generator does not need to know about variants; alternation is handled transparently in `insertPlacements`.
**Consequence:** Widget variant is determined by position in the article, not by the brief or generator. If placement order changes, variants shift accordingly.

### ADR-007 · Partner ID stamped post-render, not in-generator
**Date:** 2026-05
**Decision:** `insertAffiliateLinks` runs a final regex pass that appends `?partnerId=...` to every `href` pointing to `pricerunner.dk` in the rendered HTML. The generator writes bare affiliate URLs.
**Reasoning:** The generator cannot know the partner ID (it is a site-level credential, not brief data). Requiring the generator to append it would mean leaking config into prompts. Post-render stamping is a single point of truth and catches both generated links and widget attribution links.
**Consequence:** Any PriceRunner URL that slips through without a partnerId in production is a bug in `appendPartnerIdToPrLinks`, not in the generator. Partner ID is read from `SITE_CONFIGS[siteKey].pricerunnerPartnerId` which maps to `PR_${SITE_KEY}_PARTNER_ID` env var.

### ADR-008 · PriceRunner brand not named in article body
**Date:** 2026-05
**Decision:** Generator prompt forbids naming "PriceRunner" in article body text. Popularity, rank, and watcher signals are referenced as platform-neutral facts ("topper kategorien", "50+ holder øje med prisen").
**Reasoning:** Excessive platform-name mentions read as sponsored content and erode editorial trust. Widget attribution text ("Annonce i samarbejde med PriceRunner") is auto-injected and is the only sanctioned appearance.
**Consequence:** Generator prompts and type modules must avoid framing brief signals as "PriceRunner data". Validator does not currently enforce this — it is a prompt-level constraint only.

### ADR-009 · External links required per article
**Date:** 2026-05
**Decision:** Every article must include 1-2 external links to authoritative sources (manufacturer site, brand page, official spec sheet). This is a generator prompt rule, not a validator check.
**Reasoning:** Google's link graph treats zero-external-link pages as thin content or link farms. Manufacturer links also serve as trust signals for EEAT (Expertise, Authority, Trustworthiness).
**Consequence:** Validator does not currently enforce external link presence. Future improvement: add an `externalLinkCount` check in Phase 2 of the flow.

### ADR-010 · WordPress publishing deferred
**Date:** 2026-05
**Decision:** `wp-publisher.ts` exists but the pipeline stops at the approved article JSON. No automated publish step.
**Reasoning:** WP publish is irreversible in production. Until the full review + approval loop is proven reliable across multiple categories, human-in-the-loop approval at Phase 4 is the gate. The publisher service is kept ready but not wired into the flow.
**Consequence:** The final output is `prompts/article-$CATEGORY-sample.json`. Publishing requires a manual step or future flow extension.

---

## Known issues and tech debt

| Area | Issue | Workaround |
|---|---|---|
| `generate.ts` | TS2345 type error on `reply.status(400)` | Pre-existing; does not affect runtime. Fix requires Fastify generic typing. |
| Validator | `⚠️ Product may be missing` on the star product | False positive when product name contains special chars that break the regex. Cosmetic warning only. |
| Validator | External link count not checked | ADR-009 is prompt-only. Add `externalLinkCount` metric to Phase 2. |
| Validator | PriceRunner name detection not enforced | ADR-008 is prompt-only. Could add a regex check for "PriceRunner" in body text. |
| Brief | All categories share one brief schema | New categories require manual `brief-$CATEGORY-sample.json` creation. No brief-gen UI. |
| Widget | `singleproduct.js` has no `onlyInStock` filter | PriceRunner's single-product endpoint does not support it. May show OOS products. |
| Flow | Cross-run retrospective depends on canonical wording | Phase 6b counts identical `change` strings. Minor wording differences defeat deduplication. |

---

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `PR_TECHBLOG_PARTNER_ID` | Yes (prod) | PriceRunner affiliate partner ID — appended to all PR links and widget embed URLs |
| `PR_BUDGETSHOP_PARTNER_ID` | Yes (prod) | Same for budgetshop site |
| `WP_TECHBLOG_BASE_URL` | Yes (prod) | WordPress REST API base URL |
| `WP_TECHBLOG_USER` | Yes (prod) | WordPress application username |
| `WP_TECHBLOG_APP_PASSWORD` | Yes (prod) | WordPress application password |

All variables are optional locally — services degrade gracefully (Tailwind widget fallback, no WP publish).

---

## Related documents

| Document | What it covers |
|---|---|
| [`.agents/flows/article-pipeline/FLOW.md`](.agents/flows/article-pipeline/FLOW.md) | Orchestration phases, agent models, parameter table, rollback procedure |
| [`WIDGET-SYSTEM-REFERENCE.md`](WIDGET-SYSTEM-REFERENCE.md) | Widget embed HTML, affiliate link insertion logic, placement algorithm detail |
| [`PRICERUNNER-SCRAPER-REFERENCE.md`](PRICERUNNER-SCRAPER-REFERENCE.md) | PriceRunner API client, data shape, category traversal |
| [`docs/llm-optimization.md`](docs/llm-optimization.md) | Implementation plan: llms.txt, Schema.org, EEAT signals, AI crawler config |
| [`config/article-types.json`](config/article-types.json) | Numeric thresholds referenced by ADR-003 |
| [`prompts/agents/generator-types/`](prompts/agents/generator-types/) | Type module prompts referenced by ADR-002 |

---

## Where to add a new article type

1. Add entry to `config/article-types.json` (word counts, CRO weights, AI-tells)
2. Create `prompts/agents/generator-types/$NEW_TYPE.md` (structure, tone, CRO, what to avoid)
3. Add `"$new-type"` to `ArticleTypeSchema` in `src/types/index.ts`
4. Add classification rule in `src/services/article-classifier.ts`
5. Run `npx tsc --noEmit` to confirm no type errors
6. Test: create a brief JSON, run the validator, run the flow
