# Trendly — Remote Instance Quickstart

This instance is a secondary worker. It picks up a curated job list (`queue-remote.json`) that was generated on the primary instance to avoid category overlap.

---

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated (`claude` in PATH)
- WordPress credentials for husforbegyndere.dk in `.env`

---

## Setup

```powershell
# Install dependencies
.venv\Scripts\pip.exe install -r api/requirements.txt

# Copy and fill in secrets
cp .env.example .env
# Edit .env — set API_KEY, WP_URL, WP_USER, WP_APP_PASSWORD, ANTHROPIC_API_KEY
```

---

## Start the API

```powershell
cd api
..\.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000
```

Or via Docker:
```powershell
docker-compose up -d
```

---

## Load prompts into DB

Must be done once before running jobs (or after any prompt update):

```powershell
.venv\Scripts\python.exe scripts\load_prompts.py --api-url http://localhost:8000 --api-key changeme
```

---

## Seed jobs from queue-remote.json

`queue-remote.json` (repo root) contains a prioritized list of articles for this instance to generate. Heroes first (uncovered categories), then singles.

```powershell
# See what's in the queue
.venv\Scripts\python.exe scripts\consume_queue.py

# Queue the first 5 jobs to start
.venv\Scripts\python.exe scripts\consume_queue.py --limit 5 --execute --api-key changeme

# Queue everything
.venv\Scripts\python.exe scripts\consume_queue.py --execute --api-key changeme
```

---

## Run the worker

This instance uses Claude only (no Gemini/Mistral keys needed):

```powershell
# All steps via Claude Opus (best quality)
.venv\Scripts\python.exe scripts\run_pipeline.py --adapter claude --adapter-model claude-opus-4-7 --api-url http://localhost:8000 --api-key changeme

# Faster: Sonnet for all steps except write_draft
.venv\Scripts\python.exe scripts\run_pipeline.py --adapter claude --adapter-model claude-sonnet-4-6 --step-adapter write_draft=claude:claude-opus-4-7 --api-url http://localhost:8000 --api-key changeme
```

The worker polls until the queue is empty, then exits. Re-run it after queuing more jobs.

---

## Review and publish

```powershell
.venv\Scripts\python.exe scripts\preview_server.py --api-url http://localhost:8000 --api-key changeme
# → http://localhost:8080
```

- **Schedule (24h)** — schedules the post to go live 24 hours from now (requires QA pass)
- **Push as Draft** — saves to WP draft for manual review

---

## Queue more jobs

After the initial seed is exhausted, use the normal daily workflow:

```powershell
# Refresh product pool (weekly)
.venv\Scripts\python.exe scripts\fetch_hot_products.py --popular

# See candidates
.venv\Scripts\python.exe scripts\suggest_articles.py --recommend-type --limit 20

# Plan and queue
.venv\Scripts\python.exe scripts\queue_daily.py --count 2
.venv\Scripts\python.exe scripts\queue_daily.py --count 2 --execute
```

---

## Syncing back to the primary

When the remote has queued/published articles, export them so the primary can avoid duplicating that work:

```powershell
# On this (remote) machine:
.venv\Scripts\python.exe scripts\export_jobs.py
# → writes remote-jobs.json

git add remote-jobs.json
git commit -m "chore: sync remote job list back to primary"
git push
```

```powershell
# On the primary machine:
git pull

# Regenerate queue-remote.json — remote-jobs.json is read automatically
# to exclude already-covered products
.venv\Scripts\python.exe scripts\_gen_remote_queue.py

git add queue-remote.json
git commit -m "chore: refresh remote queue"
git push
```

Then pull on remote again and run `consume_queue.py` for the next batch.

---

## Refresh queue-remote.json (no sync needed)

When the primary instance publishes more articles but doesn't need remote feedback yet:

```powershell
# On primary machine:
.venv\Scripts\python.exe scripts\_gen_remote_queue.py
git add queue-remote.json && git commit -m "chore: refresh remote queue" && git push

# On this machine:
git pull
.venv\Scripts\python.exe scripts\consume_queue.py --execute --api-key changeme
```
