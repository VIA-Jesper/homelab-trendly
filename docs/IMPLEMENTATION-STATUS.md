# Implementation status - dedup & scaling work

> Resume doc. If a session is killed, read this + `docs/dedup-scaling-plan.md`
> (architecture) to pick up exactly where we left off. Last updated: 2026-06-11.

Branch: `chore/no-ticket-coverage-dedup` (no PRs - push to this branch as phases
complete). Architecture/rationale lives in `docs/dedup-scaling-plan.md`; this file
tracks *what is built, what is verified, and what is next*.

## Goal (recap)

Continuously produce 30-60 articles/month per site, scale vertically (more
formats/segments) and horizontally (more sites), without cannibalizing ourselves
or tripping Google's scaled-content-abuse policy. Unit of work = a **slot**
`(category, format, segment/product/pair)`, not a product. Deterministic planner +
coverage ledger is the scale engine; the LLM is boxed to writing the article body.

## Commits on this branch (newest first)

| Commit | What | Pushed? |
|---|---|---|
| `4bf8f8e` | Phase 2A value injection + evergreen best_of | **NO (local only)** |
| `d1a96ea` | Phase 1 deterministic slot planner | yes |
| `a6168d7` | em/en dash strip repo-wide | yes |
| `d808b98` | Phase 0 slot-based de-dup coverage ledger | yes |

## Phase status

- **Phase 0 - coverage ledger + gate: DONE.** `job_products` + `job_coverage`
  tables, canonical keys in `api/services/dedup.py`, slot-collision gate in
  `api/routes/jobs.py` (409 `duplicate_slot`, `force:true` bypass), slug recorded
  at publish (`api/routes/publish.py`). `scripts/backfill_coverage.py` for old jobs.
- **Phase 1 - deterministic planner: DONE.** `scripts/plan_slots.py` (enumerate ->
  subtract covered -> rank -> emit). Formats in `affiliate-pipeline/formats_v1.json`;
  segments in `affiliate-pipeline/segments/<category>_v1.json`. `/from-products`
  gained an optional `segment`. Slot identity keys on `brief.category_slug`.
- **Phase 2A - value injection: DONE (committed, not pushed).**
  `api/services/value_signals.py` computes comparative facts (price rank, spec
  leads/laggards, unique features) across a brief's own products; carried on
  `ContentBrief.value_signals`; generator prompts require citing them. Platform
  signals (rating/watchers/rank/shop count) excluded so nothing uncitable leaks.
  On real data this currently yields **price comparisons only** - spec comparisons
  are parked until we have a confirmed spec API (see Follow-ups).
- **best_of = evergreen (Option B): DONE.** Stable slot_key (`...:roundup:best`),
  year in title not slug, planner never re-mints it yearly. Hero prompt forbids the
  year in the slug.

## Verification done

- `python -m pytest tests` -> **25 passed** (dedup 12, coverage 1, value_signals 12).
- End-to-end smoke: planner enumerates 54 robotstoevsugere slots, `--execute`
  creates jobs through the gate, coverage filtering drops covered slots on re-run,
  409 on duplicate, `force:true` -> 201. DB cleaned back to seeded state after.
- Generation test (Sonnet writes, Opus grades) on a hero brief with real
  products/prices + illustrative specs: **8/10**. Evergreen slug correct,
  value_signals heavily + accurately cited (price deltas, spec leaders/laggards),
  0 em dashes, full structure. Defects found -> see "Known defects" below.

## Known defects / findings (input to the optimization pass)

1. **Hallucinated numeric spec delta.** Article said "naestbedste model har 50 min
   kortere" - wrong (real gap 20 min). Cause: `value_signals` gives spec *positions*
   (highest/lowest) but not numeric *deltas*, so the model guessed. Fix at source:
   add ranked spec values + pairwise deltas to value_signals (+ prompt rule "no
   numeric gap not in value_signals"). QA is a backstop, not the primary control.
2. **"i testen" framing = E-E-A-T risk.** Article implies hands-on testing we did
   not do. Prefer "i denne sammenligning" / "i feltet". Prompt rule unless we test.
3. **No real product specs in production - spec enrichment PARKED.** Live data only
   carries platform-meta (brand/rating/watchers/rank/merchantCount), all excluded. So
   on REAL data value_signals fires **price comparisons only**; spec comparisons are
   skipped until we have a confirmed spec API. See "Follow-ups" - we will NOT scrape
   the page on a guess.
4. Minor: "din have af rum" (garbled), "samlet sett" (Norwegian), SEO title 47 chars
   (target 50-60). Fluency slips - candidates for a 2B language/proofing check.

## Next steps (priority order, active/unblocked)

1. **Phase 2B - QA gate. DONE.** Three deterministic blockers in `api/services/qa.py`:
   QA-004 (no em/en dashes), QA-005 (forbidden AI-slop phrases + brief forbidden
   superlatives), QA-006 (cross-article lexical uniqueness). Uniqueness uses
   `api/services/similarity.py` (pure shingle-Jaccard); `pipeline._run_python_qa`
   fetches prior same-site article bodies (the optimize_seo outputs), computes max
   overlap, and injects `uniqueness_score` for QA-006 to gate on (threshold 0.35).
   Validated on real generated articles: different types 0.1%, two independent
   generations of the same roundup 4.1%, templated brand-swap near-dup 70.9% - the
   threshold sits cleanly in the gap. 46 tests total.
   Optional later: price-focused numeric-claim backstop; language check; semantic
   near-dup detection (= Phase 3 embeddings; lexical Jaccard does not catch rewrites).
2. **Daily scheduler - DOCUMENTED, not built (by decision).** See `docs/SCHEDULING.md`.
   The loop is three existing scripts run daily (`fetch_hot_products --site-only` ->
   `plan_slots --execute` per category -> `run_pipeline` worker). `run_pipeline.py` is
   already a cron-shaped worker. Left to an operator/scheduling agent to wire per the README.
3. **Phase 2D internal-link clusters - DONE.** `api/services/internal_links.py` (pure
   "Læs også" formatter) + `coverage.related_articles` (same-category published siblings,
   matched on the slot_key prefix - the category_slug column is unreliable across formats)
   wired into `publish.py` to append the cluster before widget insertion. 8 tests; empty
   no-op on a fresh site. Anchor text uses primary_keyword, else a de-slugified slug
   (improve later by storing the SEO title on the coverage row).
4. **Phase 2C schema JSON-LD - PARKED, low ROI (decided 2026-06-12).** Verified against a
   live published article (husforbegyndere.dk): the site runs **Yoast SEO v27.7**, which
   emits a connected graph - `Article`, `WebPage`, `ImageObject`, `BreadcrumbList`,
   `WebSite`, `Person/Organization` - but NOT `Product`, `Review`, `aggregateRating`, or
   `FAQPage`. Yoast covers the baseline; only product-level schema is missing. Parked because:
   - **Review / aggregateRating: do NOT add.** We do no genuine first-party reviews; faking
     review markup is an E-E-A-T / demotion risk (same issue as the "i testen" framing).
   - **FAQPage: low value** - Google restricted FAQ rich results to gov/health sites (2023).
   - **Product: the only real candidate**, but uncertain rich-result payoff for the plumbing.
   If revisited, the clean (conflict-free) path - NOT a Python `<script>` inject (WP strips
   `<script>` from REST post content, and a standalone block would not join Yoast's `@graph`):
   write product fields (price, brand, image, url) as post meta in `wp_publisher.py`, then a
   `register-product-schema.php` mu-plugin adding a `Product` piece to Yoast's graph via the
   `wpseo_schema_graph` filter (mirrors the existing `register-yoast-meta.php`).
5. **Deferred:** Phase 1.5 new formats (alternatives/worth_it/buying_guide);
   Phase 2.5 refresh loop (stale -> update > redirect > delete; good background
   subagent); Phase 3 semantic-similarity gate.

The optimization pass (prompt/framing tuning, defects #2/#4) is the user's to run
against generated results.

### Phase 1.5 note - buying_guide format (DOWN-PRIORITIZED, captured for later)

Liked but parked low. A buying_guide is an informational "sådan vælger du {category}"
article (teaches the buying decision; does not rank products - that is best_of). Build
criteria when revisited:
- **Singleton per category** (like best_of) - one guide per category, never more
  (multiple = cannibalization).
- **Gate on real decision dimensions** - only generate for a category that has enough
  products + defined segments/spec axes (the same config the segment roundups use). No
  guide for thin categories - this format is the most prone to thin-content demotion.
- **Content must be data-grounded, not generic** - cite the category's real price range
  and spec tradeoffs from the pool, structured around our segment matrix
  (budget/mellemklasse/premium, til kæledyr, med moppe). Never freeform "how to choose".
- **Acts as the internal-link cluster hub** - links down to the category's segment
  roundups + best_of + top reviews; gets more valuable as the category fills out.
- **Scaling:** scales horizontally (1/category/site, evergreen + renewable), no
  within-category multiplication. Buildable now as price/segment-focused; the
  spec-tradeoff depth needs the parked spec enrichment.
- **Work needed:** new `article_type` + prompt + brief builder (standard Phase 1.5).

## Follow-ups (parked - need input before building)

- **Spec enrichment - SKIPPED until a confirmed spec API (decided 2026-06-12).** Real
  product specs (suction kPa, battery mAh, runtime, tank L, features) would make
  value_signals produce genuine spec comparisons, not just price. Preference: source
  via a clean API, not page scraping. Everything below is *verified this session* so it
  is resumable without re-investigating.

  **What's verified:**
  - The specs DO exist and ARE extractable. They are server-side-rendered into the
    product page in a JSON object keyed `"specifications"`, grouped as
    `Produkt / Produktegenskaber / Ydeevne / Egenskaber / Strømkilde / Mål / Øvrigt`,
    each with an `attributes: [{name, value}]` list. Proven on Dreame X50 (id
    3391726225): Sugeevne 20.0 kPa, Batterikapacitet 6400 mAh, Batteritid 220 min,
    Støvbeholder 0.395 L, Egenskaber "Automatisk tømning, Moppefunktion", Vægt 4.53 kg,
    mål 350x350x111 mm. These are exactly the comparable specs value_signals needs.
  - **Working extraction recipe:** GET the product page
    (`https://www.pricerunner.dk/pl/<subcat>-<productId>/<slug>`) with **full browser
    headers** - a minimal User-Agent gets a `454` WAF block; full Chrome headers
    (UA + Accept + Accept-Language + Sec-Fetch-*) return `200`. Then find
    `"specifications":`, brace-match the following `{...}`, `json.loads` it directly
    (standard JSON with `\u` escapes), and flatten each group's `attributes`. ~1 MB/page.
  - **All documented JSON APIs are dead:** `pl/v5`, `pl/v4`, `productlistings/pl/initial`,
    `productinfo`, `listings/products` - all 404, under both `search-edge-rest` and
    `search-compare-gateway`. The frontend is a Klarna OWP SPA (bundles on
    owp.klarna.com); the live spec-API path is NOT in the page HTML (it's in the JS).

  **Preferred unblock (find the real API):** open a product page -> DevTools -> Network
  -> filter Fetch/XHR -> reload -> find the response containing "Sugeevne" -> copy its
  Request URL. That is the live spec endpoint; wire it into the client.

  **Fallback (verified, if no clean API surfaces):** the page-extraction recipe above.
  Fragile to Klarna frontend changes - wrap with graceful-empty fallback + a fixture test.

  **Build once specs flow in (from either source):** parse them into `RawProduct.specs`
  in `pricerunner_client` (the current v4 search path only sets brand/rating/meta - see
  `_map_v4_product`), then add **value_signals spec deltas** (ranked values + pairwise
  gaps) so the model cites exact numbers - this also kills demo defect #1 (the
  hallucinated "50 min"). The spec-comparison machinery in `value_signals.py` already
  exists and is tested; it just needs real specs as input. Spec-based segments
  (`til kæledyr`, `med moppe`) in the segment config light up at the same time.
  Until then value_signals = price comparisons only (real, working).

## How to run things (from repo root, Windows)

```
# tests
.venv\Scripts\python.exe -m pytest tests -q

# API server (must run from repo root so ./trendly_local.db matches the planner)
.venv\Scripts\python.exe -m uvicorn main:app --app-dir api --host 127.0.0.1 --port 8000

# planner: dry-run, then execute
.venv\Scripts\python.exe scripts\plan_slots.py --category robotstoevsugere --count 5
.venv\Scripts\python.exe scripts\plan_slots.py --category robotstoevsugere --count 5 --execute --api-key changeme

# reload prompts into the DB after editing prompts/*.txt
.venv\Scripts\python.exe scripts\load_prompts.py
```

Local dev DB `trendly_local.db` (gitignored) holds the seeded "hus" site + 7 prompts.
Pool `data/hot-products.jsonl` (gitignored) = 1100 products, 25 categories (~50 each).

## Hard constraints (do not violate)

- **No em dashes / en dashes anywhere** - plain hyphens only, repo-wide.
- **Never write to GBrain in this project** - use the local file memory.
- **No PRs** - one branch, push as phases complete. Ask before pushing.
- Never commit secrets; the partner-id/WP creds live in `.env` (gitignored).
