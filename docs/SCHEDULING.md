# Continuous production - scheduling guide

> For the agent/operator who will set up the recurring schedule. Nothing here is
> wired up automatically by design - this document is the instruction set. The
> building blocks already exist as scripts; scheduling = running three of them in
> order on a daily cadence.

## What runs, and in what order

The "continuously agentic" loop is three existing scripts, run daily in this order:

1. **Refresh the product pool** - pull current trending products + prices.
   ```
   python scripts/fetch_hot_products.py --site-only
   ```
   Writes `data/hot-products.jsonl` (the pool the planner ranks from). `--site-only`
   = trending per category (fast, ~50/category), good for daily. Use `--popular`
   (all-time, up to 200/category, slower) weekly if you want a deeper pool.

2. **Queue 1-2 new slots per category** - the deterministic planner.
   ```
   python scripts/plan_slots.py --category <slug> --count 1 --execute --api-key <KEY>
   ```
   Run once per category you publish (loop over your category slugs). It enumerates
   the category's slots, subtracts what the coverage ledger already covers, ranks the
   gaps, and POSTs the top `--count` to the API. **Idempotent:** already-covered slots
   are filtered out, and the API gate returns 409 (skipped) on any collision - safe to
   run every day. Start with `--count 1` per category; raise to hit your monthly target.

3. **Process the queue** - the worker that writes + QAs + publishes.
   ```
   python scripts/run_pipeline.py --adapter claude --api-url http://localhost:8000 --api-key <KEY>
   ```
   Polls `GET /api/v1/work` and runs one LLM call per pending step until the queue is
   empty, then exits. `--adapter claude` uses the claude CLI; `--adapter augment` is the
   alternative. This is the step that consumes an LLM and publishes to WordPress.

## Prerequisites (must be true before the schedule fires)

- **API server running** (the planner and worker both talk to it). From the repo root
  so `./trendly_local.db` resolves:
  ```
  python -m uvicorn main:app --app-dir api --host 127.0.0.1 --port 8000
  ```
  In production run this as a long-lived service (systemd / Windows service / container),
  not from the scheduled task.
- **`.env` configured** at repo root: `API_KEY`, `DATABASE_URL`, the PriceRunner partner
  id, and the WordPress creds (`WP_HUS_URL/USER/PASS`). Without WP creds, publish fails.
- **LLM access for the adapter** - the `claude` CLI on PATH (for `--adapter claude`) or
  the relevant key.
- **Sites + prompts seeded** in the DB (`scripts/load_prompts.py`, and at least one site).

## Cadence

- 1-2 articles/day = the target. At `--count 1` across ~2 categories/day you land ~30-60/month.
- Rotate categories across days rather than queuing every category every day, so output
  stays varied and the worker run stays short.
- Pool refresh: daily (`--site-only`). Deep refresh (`--popular`): weekly.
- The flagship `best_of` slot is evergreen and is created once per category, then never
  re-queued (refreshing its content is the future Phase 2.5 refresh loop, not this schedule).

## Scheduling on Windows (dev box - Task Scheduler)

Create a wrapper `daily-production.ps1` (the scheduling agent writes this) that runs the
three stages in order and stops on failure:
```powershell
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\jhe\Documents\Projects\OpenspecTest\homelab-trendly'
$py  = '.\.venv\Scripts\python.exe'
$key = $env:TRENDLY_API_KEY
& $py scripts\fetch_hot_products.py --site-only
foreach ($cat in @('robotstoevsugere','stovsugere')) {   # rotate/extend as needed
    & $py scripts\plan_slots.py --category $cat --count 1 --execute --api-key $key
}
& $py scripts\run_pipeline.py --adapter claude --api-url http://localhost:8000 --api-key $key
```
Register it (runs daily at 07:00):
```
schtasks /Create /TN "TrendlyDaily" /TR "powershell -NoProfile -File C:\...\daily-production.ps1" /SC DAILY /ST 07:00
```
The API server must already be running as a separate always-on service.

## Scheduling on Linux / docker (production)

A `daily-production.sh` wrapper running the same three stages, scheduled via crontab:
```
# m h dom mon dow   command
0 7 * * *  cd /app && ./daily-production.sh >> /var/log/trendly-daily.log 2>&1
```
In a container, an external scheduler (host cron, k8s CronJob, or a sidecar) should invoke
the wrapper; keep the API server as its own long-running container.

## Verification & monitoring

- After a run, confirm new coverage: `SELECT slot_key, slug FROM job_coverage ORDER BY ...`,
  and check job statuses moved toward `complete`.
- A dry-run of the planner (omit `--execute`) shows exactly what it would queue.
- The QA gate (QA-001..006) blocks slop / near-duplicates before publish; a job that fails
  QA is retried, then parked as `requires_review` rather than published - check for those.

## Decisions for the scheduling agent

- Which categories, and the per-day rotation (to hit the monthly target without dupes).
- Where the API server and worker live (same host? container?) and how the worker
  authenticates to the LLM.
- WordPress publish status: draft vs publish (paced rollout + a human spot-check on the
  first batch is strongly recommended before auto-publishing).
- Alerting on failures (the wrapper should surface a non-zero exit / log line).
