# Trendly - Affiliate Article Pipeline

Agentic pipeline for generating Danish affiliate articles at scale.
Fetches live product data from PriceRunner, generates articles via LLM, reviews them, and publishes to WordPress on a 24-hour schedule.

---

## How it works

```
PriceRunner catalog
      ↓
fetch_hot_products.py      - build/refresh the product pool (JSONL)
      ↓
queue_daily.py             - pick 1-2 products/day, recommend article type, create jobs
      ↓
API (FastAPI + SQLite)     - job queue, step sequencing, state, retry logic
      ↓
Worker (run_pipeline.py)   - pulls steps, calls LLM adapter, submits output
      ↓
Preview server             - review article, push as Draft or Schedule (24h)
      ↓
WordPress                  - published or scheduled post
```

**Separation of concerns:**
- The API handles all structure - step sequencing, retries, state, QA gating. Deterministic code.
- LLM agents handle all content - writing, SEO optimisation, QA review. Replaceable adapters.

---

## Daily workflow

**1. Refresh product pool (run weekly or when pool feels thin)**
```powershell
# ~50 trending products per category (fast, daily signal)
.venv\Scripts\python.exe scripts\fetch_hot_products.py --site-only

# 200 all-time popular per category - 5000+ products, run weekly
.venv\Scripts\python.exe scripts\fetch_hot_products.py --popular
```

**2. See what's available**
```powershell
.venv\Scripts\python.exe scripts\suggest_articles.py --recommend-type --limit 20
```

**3. Plan and queue jobs**
```powershell
# Dry-run first - see the plan
.venv\Scripts\python.exe scripts\queue_daily.py --count 2

# Execute when happy
.venv\Scripts\python.exe scripts\queue_daily.py --count 2 --execute
```

**4. Run the worker**
```powershell
# Gemini (fast, cheap) for everything
.venv\Scripts\python.exe scripts\run_pipeline.py --adapter gemini --adapter-model gemini-2.5-flash --api-url http://localhost:8000 --api-key changeme

# Opus for write_draft, Gemini for the rest
.venv\Scripts\python.exe scripts\run_pipeline.py --adapter gemini --adapter-model gemini-2.5-flash --step-adapter write_draft=claude:claude-opus-4-7 --api-url http://localhost:8000 --api-key changeme
```

**5. Review in preview server**
```powershell
.venv\Scripts\start-preview.ps1
# → http://localhost:8080
```

**6. Publish**
- **Push as Draft** - saves to WP draft for manual review
- **Schedule (24h)** - sets WP status `future`, auto-publishes 24h from now (requires QA pass)

---

## Article types

| Type | Products | When used |
|------|----------|-----------|
| `single-product-review` | 1 | Default - one product, full review |
| `hero` | 5-7 | Category roundup - 0 existing articles in category + 5+ candidates |
| `comparison` | 2-4 | Head-to-head between similar products (manual) |

`queue_daily.py` auto-selects type: **hero** for uncovered categories with enough candidates, **single-product-review** otherwise. Max one job per category per run.

---

## Pipeline steps (per article)

| Step | What happens |
|------|-------------|
| `write_draft` | LLM writes full Danish article from brief + prompt |
| `optimize_seo` | LLM optimises keyword density, title, meta description, CTAs |
| `qa_review` | LLM validates against QA checklist → PASS or FAIL + edits_needed |
| _(retry up to 3×)_ | On FAIL: re-queues write_draft with edits_needed injected |
| `score_article` | Scores SEO / CRO / readability (0-100) |
| _(publish)_ | Manual: preview server → Schedule (24h) or Draft |

---

## Scripts reference

| Script | Description |
|--------|-------------|
| `scripts/fetch_hot_products.py --site-only` | Trending products per category → JSONL |
| `scripts/fetch_hot_products.py --popular` | All-time popular (200/category, paginates v4 API) → JSONL |
| `scripts/suggest_articles.py` | Ranked candidate list, deduped against DB |
| `scripts/suggest_articles.py --recommend-type` | Adds hero/single recommendation per candidate |
| `scripts/queue_daily.py --count N` | Dry-run plan: hero bundles first, then top singles |
| `scripts/queue_daily.py --count N --execute` | Create jobs via API |
| `scripts/run_pipeline.py` | Worker loop - pulls steps, calls LLM, submits output |
| `scripts/preview_server.py` | Preview UI at localhost:8080 |
| `scripts/load_prompts.py` | Load/reload prompt files from `prompts/` into DB |
| `scripts/consume_queue.py` | Seed a remote instance from `queue-remote.json` |
| `scripts/export_jobs.py` | Export this instance's job list for import into the authority DB |
| `scripts/import_jobs.py` | Import an exported job list into the authority DB (dedup tracking) |
| `scripts/_gen_remote_queue.py` | Regenerate `queue-remote.json` from current product pool |

---

## Running a second instance

A second Trendly instance (e.g. a remote worker) can be seeded with a curated job list so it covers different categories than the primary instance.

**On the primary machine** - regenerate `queue-remote.json` from the current product pool:
```powershell
.venv\Scripts\python.exe scripts\_gen_remote_queue.py
git add queue-remote.json && git commit -m "chore: refresh remote queue" && git push
```

**On the remote machine** - pull and seed:
```powershell
git pull

# Dry-run - see what would be queued
.venv\Scripts\python.exe scripts\consume_queue.py

# Queue all jobs (or --limit N for a subset)
.venv\Scripts\python.exe scripts\consume_queue.py --execute --api-url http://localhost:8000 --api-key changeme
```

**Run the worker (Claude-only remote):**
```powershell
.venv\Scripts\python.exe scripts\run_pipeline.py --adapter claude --adapter-model claude-opus-4-7 --api-url http://localhost:8000 --api-key changeme
```

`queue-remote.json` is generated with the primary instance's already-published categories excluded from hero slots, so the two instances naturally cover different ground.

---

## LLM adapters

```powershell
# Gemini
--adapter gemini --adapter-model gemini-2.5-flash

# Claude (API)
--adapter claude --adapter-model claude-sonnet-4-6

# Per-step routing (different model per step)
--adapter gemini --adapter-model gemini-2.5-flash --step-adapter write_draft=claude:claude-opus-4-7
```

---

## API reference

All routes require `X-API-Key` header.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness check |
| POST | `/api/v1/jobs/from-products` | Create job from PriceRunner URL(s) |
| GET | `/api/v1/jobs` | List jobs |
| GET | `/api/v1/jobs/{id}` | Job detail + step history |
| POST | `/api/v1/jobs/{id}/reset` | Reset job (optionally from a specific step) |
| POST | `/api/v1/jobs/{id}/publish?status=draft\|future\|publish` | Push to WordPress |
| GET | `/api/v1/work` | Worker: get next pending step |
| POST | `/api/v1/work/{id}` | Worker: submit step output |

**Create job example:**
```json
POST /api/v1/jobs/from-products
{
  "site_key": "hus",
  "article_type": "single-product-review",
  "product_urls": ["https://www.pricerunner.dk/pl/19-3206825946/..."],
  "editorial_note": "Lead with energy efficiency - big deal for Danish buyers right now.",
  "reasoning": "Rank 1 støvsugere, 200+ watchers, no existing article"
}
```

**Partial reset (rerun from a specific step):**
```json
POST /api/v1/jobs/{id}/reset
{ "from_step": "optimize_seo" }   // reruns from SEO onward, keeps write_draft
{ "from_step": "score_article" }  // just rescores
{}                                 // full reset
```

---

## Stack

```
docker-compose.yml     API + SQLite volume + Caddy proxy
api/
  main.py              FastAPI app, API key auth
  models/              Job, Step, Site, Prompt (SQLite via SQLAlchemy)
  services/
    pipeline.py        Step sequencing, retry logic, state transitions
    brief_builder.py   Builds ContentBrief from PriceRunner product data
    pricerunner_client.py  PriceRunner public API client (rate-limited, cached)
    wp_publisher.py    WordPress REST API publisher
    widget_inserter.py Injects PriceRunner affiliate widgets into article HTML
    qa.py              Python QA checks (word count, em dash, etc.)
  routes/
    jobs.py            Job creation + reset
    work.py            Worker endpoints
    publish.py         WP publish / schedule
prompts/
  generate_v1.txt      Article generation (single-product-review)
  types/hero.txt       Hero/roundup generation prompt
  optimize_v1.txt      SEO optimisation
  qa_v1.txt            QA review checklist
scripts/
  fetch_hot_products.py
  suggest_articles.py
  queue_daily.py
  run_pipeline.py
  preview_server.py
  load_prompts.py
  adapters/            claude, gemini, mistral, routing
```

---

## Site config

Sites are configured in `api/services/brief_builder.py` under `SITE_CONFIGS`.

```python
"hus": SiteConfig(
    domain="husforbegyndere.dk",
    wp_url="https://husforbegyndere.dk",
    pricerunner_country="DK",
    pricerunner_partner_id="adrunner_dk_husforbegyndere",
    min_words=700,
    ...
)
```

---

## Environment variables

```
API_KEY=changeme
DATABASE_URL=sqlite+aiosqlite:///./trendly_local.db
LOG_LEVEL=INFO
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
```
