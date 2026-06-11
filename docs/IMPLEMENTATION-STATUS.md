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
3. **No real product specs in production.** Live PriceRunner public API only returns
   platform-meta (brand/rating/watchers/rank/merchantCount) - all excluded. So on
   REAL data, value_signals currently fires **price comparisons only**; the spec
   comparisons need a spec-enrichment source (see Next steps #1).
4. Minor: "din have af rum" (garbled), "samlet sett" (Norwegian), SEO title 47 chars
   (target 50-60). Fluency slips - candidates for a 2B language/proofing check.

## Next steps (priority order)

1. **Product spec enrichment (the big one).** Source real specs (suction Pa, battery,
   tank, mop, auto-empty) for products - e.g. scrape the PR product-page spec table
   or another source. Without it the spec-delta value is dormant on real articles.
2. **value_signals spec deltas.** Add ranked values + gaps so the model cites real
   numbers; kills defect #1 at the source. Pairs with #1.
3. **Phase 2B - QA uniqueness gate.** New `IQACheck` in `api/services/qa.py`: lexical
   similarity vs existing articles + boilerplate guard + numeric-claim backstop (the
   QA-as-net idea) + optional language check.
4. **Daily scheduler (cron).** Wrap `plan_slots.py` to queue 1-2 slots/day = the
   "continuously agentic" autopilot.
5. **Phase 2C schema JSON-LD; 2D internal-link clusters** (from the coverage ledger).
6. **Deferred:** Phase 1.5 new formats (alternatives/worth_it/buying_guide);
   Phase 2.5 refresh loop (stale -> update > redirect > delete; good background
   subagent); Phase 3 semantic-similarity gate.

The optimization pass (prompt/framing tuning, defects #1/#2/#4) is the user's to run
against generated results; spec enrichment (#1) is the next build-side unblocker.

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
