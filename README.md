# Affiliate Pipeline

Agentic system for generating Danish affiliate articles at scale.
One API, stateless agents, unlimited sites.

---

## The approach

The core idea came from thinking about reliability. The problem with having an AI agent
orchestrate its own pipeline (read a runbook, retry on failure, write logs) is that you are
trusting probabilistic reasoning to do structural work. It works, until it doesn't.

The solution is a clear separation:

- **The system (Docker API) handles all structure** - step sequencing, retry counts, state,
  logging. This is deterministic code. It never fails silently.
- **Agents handle all content** - writing, optimising, reviewing. This is where reasoning
  actually matters and where an LLM earns its place.

Agents are fully stateless and replaceable. The system does not care whether you use Claude,
Augment, or anything else that can make an HTTP call.

---

## How it runs

### Orchestrator (runs once or twice a day via cron)

A lightweight Python script (not an agent) checks whether there is queued work. If there is,
it starts a worker agent. If the queue is empty, it exits. The script is the only persistent
process outside Docker. It requires no AI - it just checks a return value and spawns a process.

In the future the orchestrator could be replaced by an agent that queries site data, reasons
about what to write next (based on coverage gaps, seasonality, keyword opportunities), and
creates jobs via `POST /api/v1/jobs`. That agent makes the strategic decision. The system
executes it reliably.

### Worker (runs until queue is empty)

```
python scripts/run_pipeline.py --adapter claude --api-url https://your-domain --api-key secret
```

The worker loops:
1. `GET /api/v1/work` - receives one task (prompt + content) or `{ "status": "empty" }`
2. Passes the task to the agent adapter (Claude CLI, Augment, etc.)
3. `POST /api/v1/work/{task_id}` - submits the agent output
4. Repeats until empty, then exits

Each task is a clean agent invocation with a fresh context. No context window accumulation
across tasks. If a task fails, the system re-queues it. If the worker crashes mid-run, the
next cron trigger picks up where it left off - state lives in Postgres, not in the agent.

### Pipeline steps (per article)

| Step | What happens |
|---|---|
| `write_draft` | Agent writes the full Danish article from brief + prompt |
| `optimize_seo` | Agent optimises keyword density, meta description, CTA placement |
| `qa_review` | Agent validates against QA checklist, returns PASS or FAIL + edits_needed |
| _(retry)_ | On FAIL: system re-queues write_draft with edits_needed injected, up to 3 attempts |
| _(publish)_ | Not yet implemented - see Roadmap |

Steps are defined in `api/config.py`. Add, remove, or reorder steps without touching routes
or services.

---

## Directory structure

```
docker-compose.yml          api + postgres + caddy proxy
Caddyfile                   reverse proxy config
migrations/
  001_initial.sql           postgres schema

api/
  main.py                   fastapi app, api key auth
  config.py                 pipeline step definitions (config-driven)
  database.py               async sqlalchemy
  models/                   site, job, step, prompt (jsonb context fields)
  interfaces/               extension points (see Extensibility below)
  services/
    pipeline.py             step sequencing, retry logic, state transitions
    qa.py                   qa checks registry
  routes/
    work.py                 GET /work, POST /work/{id}
    jobs.py                 POST /jobs, GET /jobs/{id}
    sites.py                POST /sites, GET /sites/{id}/seed

scripts/
  run_pipeline.py           worker loop
  adapters/
    base.py                 adapter interface
    claude.py               claude cli adapter
    augment.py              augment adapter

prompts/                    danish prompt files - load into db on first run
  generate_v1.txt           article generation
  optimize_v1.txt           seo optimisation
  qa_v1.txt                 quality review
```

---

## API surface

All routes require `X-API-Key` header. `/health` is public.

| Method | Endpoint | Who uses it | What it does |
|---|---|---|---|
| GET | `/health` | anyone | liveness check |
| POST | `/api/v1/sites` | human setup | register a new site with seed config |
| GET | `/api/v1/sites/{id}/seed` | orchestrator | read site niche, goals, cadence |
| GET | `/api/v1/sites` | orchestrator | list active sites |
| POST | `/api/v1/jobs` | orchestrator | create article job, system queues all steps |
| GET | `/api/v1/jobs/{id}` | human debug | inspect job state and step history |
| GET | `/api/v1/work` | worker script | get next task or `{"status":"empty"}` |
| POST | `/api/v1/work/{id}` | worker script | submit agent output, system advances pipeline |

---

## Extensibility

The system is designed so that adding new capabilities does not require touching core logic.
Four interfaces define the extension points:

| Interface | File | Add this to... |
|---|---|---|
| `IDataProvider` | `api/interfaces/data_provider.py` | Plug in product catalogs, keyword APIs, trend data |
| `IQACheck` | `api/interfaces/qa_check.py` | Add new content quality checks |
| `IStepHandler` | `api/interfaces/step_handler.py` | Hook into step completion events |
| `IPublisher` | `api/interfaces/publisher.py` | Publish to WordPress, CMS, filesystem |

The `job.context` and `step.input` fields are JSONB - add product IDs, SEO data, external
links, widget config, or anything else without schema migrations.

---

## Getting started

**1. Configure environment**

Copy and edit the env file:
```
DATABASE_URL=postgresql+asyncpg://pipeline:pipeline_secret@db:5432/affiliate_pipeline
API_KEY=your-secret-key
LOG_LEVEL=INFO
```

**2. Start the stack**
```
docker compose up -d
```

**3. Load prompts into the database**

The prompt files in `prompts/` are the source of truth. On first run, update the placeholder
rows inserted by the migration with the actual content from those files.

**4. Create a site**
```
POST /api/v1/sites
{
  "name": "Bedste Hoeretelefoner",
  "domain": "bedste-hoeretelefoner.dk",
  "seed": {
    "niche": "consumer electronics - audio",
    "target_audience": "Danish consumers researching headphone purchases",
    "language": "da",
    "content_goals": ["SEO traffic", "affiliate conversions"],
    "publishing_cadence": "3 articles per week"
  }
}
```

**5. Create a job**
```
POST /api/v1/jobs
{
  "site_id": "<site-uuid>",
  "context": {
    "article_type": "review",
    "target_keyword": "sony wh-1000xm6 test",
    "affiliate_ids": ["WC-SONY-1000XM6"],
    "min_words": 1000
  },
  "reasoning": "New model released, low keyword competition, gap in site coverage"
}
```

**6. Run the worker**
```
python scripts/run_pipeline.py --adapter claude --api-url http://localhost --api-key your-secret-key
```

---

## Roadmap

- [ ] Publisher implementation (WordPress REST API)
- [ ] Prompt loader script (sync `prompts/*.txt` into DB on startup)
- [ ] Orchestrator agent (reasons about what to write next based on site data)
- [ ] Product catalog endpoints (`/products`, `/keywords/gaps`)
- [ ] Prompt versioning UI (update prompts without touching DB directly)
- [ ] Multi-site cron setup documentation
- [ ] OpenClaw adapter
