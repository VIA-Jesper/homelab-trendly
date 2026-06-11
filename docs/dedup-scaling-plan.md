# Dedup & scaling architecture

> Goal: produce 30-60 articles/month per site, scale to many sites, without
> cannibalizing ourselves or tripping Google's scaled-content-abuse policy.

One sentence: **we add a deterministic planning + coverage layer on top of the
existing pipeline, and shift the unit of work from "a product" to "a slot."**

## The problem

- **Cannibalization:** multiple articles competing for the same intent (e.g. two
  "Bedste robotstøvsuger 2026"). At hundreds of products this compounds.
- **Google risk:** AI affiliate content with no unique value / no first-hand
  experience and specs copied from the source gets demoted (March 2026 core
  update: 40-70% losses on exactly this profile). Templates are fine; *thin*
  templated content is not.

## What we're changing (and why)

| Shift | From | To | Why |
|---|---|---|---|
| Unit of work | product | **slot** = `(category, format, segment/product/pair)` | variety *and* uniqueness at scale |
| Coverage | derived on the fly (scan every job's JSON) | **explicit ledger** (tables) | turns dedup into a lookup; enables planning |
| Generation | reactive (rank products, hope no dup) | **coverage-driven** (enumerate slots, subtract covered, fill gaps) | continuous production model |
| Article space | hardcoded types | **declarative config** (formats + per-category segments) | expand by editing data, not code |
| Site | implicit | **the production unit** (per-site coverage) | cannibalization is within-domain; scale = add site units |
| Quality | afterthought | **structural gate** (unique data + QA uniqueness) | dedup earns the right to rank; value is what ranks |
| LLM | tempted to plan/title | **body only** | determinism, debuggability, no drift |

## Before / after flow

```
NOW:   hot-products.jsonl -> rank products -> ad-hoc dup check -> job -> write -> publish

AFTER: config(formats+segments) + product pool + COVERAGE LEDGER
         -> planner: enumerate slots -> subtract covered -> rank gaps
         -> API gate: product/keyword overlap check + record coverage
         -> pipeline writes (real data injected) -> QA uniqueness gate
         -> publish -> record slug back to ledger
```

The coverage ledger is the spine: the planner reads it to find gaps; the gate
writes to it to prevent collisions.

## The slot matrix

A slot is one publishable article identity. Each format has a multiplicity rule:

| Format | Multiplicity | Keyword pattern |
|---|---|---|
| single_review | 1 / product | `{product} test` |
| alternatives | 1 / product | `alternativer til {product}` |
| worth_it | 1 / product | `er {product} pengene værd` |
| comparison | eligible pairs | `{a} vs {b}` |
| segment_roundup | 1 / segment | `bedste {cat} til {segment}` |
| buying_guide | **singleton** | `sådan vælger du {cat}` |
| best_of | **singleton** | `bedste {cat} {year}` |

**Segments** are the roundup multiplier without repeats: `til kæledyr`,
`under 3000 kr`, `med mopfunktion`, `til små lejligheder`. Each = distinct
keyword = distinct article. One category -> dozens of non-overlapping articles;
only the two singletons ever say "bedste".

## Plan

**Phase 0 - Dedup hygiene (foundation)**
- `api/services/dedup.py` - canonical product key + slot key (pure, shared by API + planner)
- coverage tables: `job_products`, `job_coverage` (SQLAlchemy models -> created via `create_all`; mirror in `migrations/002_*.sql` for Postgres)
- `api/routes/jobs.py` - replace the brittle dup check with product-overlap (cross-type, per-site) + slot-key collision; write coverage on create
- `api/routes/publish.py` - record final WP slug into coverage
- `scripts/suggest_articles.py` + `queue_daily.py` - use shared `dedup`, key category on slug
- `scripts/backfill_coverage.py` - populate ledger from existing jobs

**Phase 1 - Deterministic slot planner (scale engine) [DONE]**
- `affiliate-pipeline/formats_v1.json` - format registry (multiplicity, keyword/title templates, article_type). single_review -> single-product-review; segment_roundup + best_of -> hero.
- `affiliate-pipeline/segments/<category>_v1.json` - segment rules. Price-band only for now (the hot-products pool has no specs); spec-based segments (til kaeledyr, med moppe) go under match.spec once product enrichment lands (Phase 2), no planner change needed.
- `scripts/plan_slots.py` - `enumerate -> subtract covered -> rank -> emit top K`. No LLM. Dry-run by default; `--execute` POSTs to the gate.
- `/from-products` gained an optional `segment` so segmented roundups get a segment-aware slot_key.
- Fix (caught by the smoke test): slot identity keys on `brief.category_slug` (stable ASCII slug), not the display `category` (hero uses singular Danish for content) - keeps planner and API slots consistent across formats.
- Verified end-to-end on robotstoevsugere: planner creates single + hero slots; coverage-driven filtering drops covered slots on re-run.

**Phase 1.5 - New formats (only when needed)**
- `alternatives`, `worth_it`, `buying_guide` each need an `article_type` + prompt + brief builder. Add after existing-type formats prove out.

**Phase 2 - Value + ranking (before scaling volume)**
- inject real PR data per article (price, price history, watchers, spec deltas)
- QA uniqueness gate (~80% unique); schema (Product/Review/FAQ); internal-link clusters
- human review on a sample + paced publishing

**Phase 3 - Semantic gate (when volume grows)**
- embedding fingerprint as planner admission check + thin-content guard (catches
  intent overlap lexical keys miss, e.g. "test" vs "anmeldelse")

## Lean / maintainability principles

- **Reuse, don't rebuild:** pipeline (API/worker/steps) + LLM body gen untouched.
- **Config-as-data:** the article space grows by editing YAML, not code.
- **Pure & deterministic planner:** function of `(config, pool, coverage)` - unit-testable, no hidden state.
- **Single source of truth:** one coverage ledger; one `dedup` module shared by API + scripts (replaces today's duplicated, buggy checks - Phase 0 is partly a *simplification*).
- **YAGNI:** one category + existing types first; no new types and no embeddings until volume needs them.
- **Refuse complexity:** segment rules stay dumb predicates (price band, one spec flag), no rules engine; new article types only when structurally different; no multi-tenant abstractions before site #2.

## What we are NOT changing

The pipeline itself (API / worker / steps), LLM body generation, the per-site
model. The LLM stays boxed to writing prose. We bolt a deterministic planning
brain onto a pipeline that already executes well.

## Open decisions

- Migrations: local SQLite is built from SQLAlchemy models via `create_all`
  (`scripts/load_prompts.py`); the Postgres/docker path uses `migrations/*.sql`.
  New tables need both a model and a `002_*.sql`.
- New article types (Phase 1.5): add standalone vs fold into `hero`/`single`.
