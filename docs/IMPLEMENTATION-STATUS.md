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

1. **Phase 2B - QA gate.** DONE so far: QA-004 (no em/en dashes, BLOCKER) + QA-005
   (forbidden AI-slop phrases + brief forbidden superlatives, BLOCKER) in
   `api/services/qa.py`, 10 tests, verified clean on the sample article. Remaining:
   cross-article lexical similarity vs existing articles (the real "uniqueness" check
   - needs corpus/DB access in `pipeline._run_python_qa`, which the sync `IQACheck`
   interface does not have, so it is a slightly bigger touch); a price-focused
   numeric-claim backstop; optional language check.
2. **Daily scheduler (cron).** Wrap `plan_slots.py` to queue 1-2 slots/day = the
   "continuously agentic" autopilot.
3. **Phase 2C schema JSON-LD; 2D internal-link clusters** (from the coverage ledger).
4. **Deferred:** Phase 1.5 new formats (alternatives/worth_it/buying_guide);
   Phase 2.5 refresh loop (stale -> update > redirect > delete; good background
   subagent); Phase 3 semantic-similarity gate.

The optimization pass (prompt/framing tuning, defects #2/#4) is the user's to run
against generated results.

## Follow-ups (parked - need input before building)

- **Spec enrichment - need a confirmed spec API; SKIPPED until then.** Real product
  specs (suction kPa, battery mAh, runtime, tank L, features) would make value_signals
  produce genuine spec comparisons, not just price. The data exists (SSR'd into the
  product page as a clean `specifications` JSON), but we will NOT scrape it on a guess.
  Status of what was actually checked: all documented endpoints 404 (`pl/v5`, `pl/v4`,
  `productlistings/pl/initial`, `productinfo`, `listings/products`, under both
  `search-edge-rest` and `search-compare-gateway`); the frontend is a Klarna OWP SPA;
  the live spec-API path is not in the page HTML. **To unblock:** capture the live
  request from a browser (DevTools -> Network -> Fetch/XHR -> reload -> find the
  response containing "Sugeevne"/"specifications" -> copy the Request URL), or
  reverse-engineer the Klarna JS bundles. Once a real endpoint is confirmed: add a
  fetch + parser into `RawProduct.specs`, then add **value_signals spec deltas**
  (ranked values + gaps) so the model cites exact numbers (kills demo defect #1).
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
