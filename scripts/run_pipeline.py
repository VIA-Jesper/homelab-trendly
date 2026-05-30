"""
run_pipeline.py - Worker loop for the affiliate pipeline.

Started by cron (once or twice a day). Polls GET /api/v1/work until the queue
is empty, spawning one agent call per task. Exits cleanly when done or on error.

Usage:
    python run_pipeline.py --adapter claude --api-url http://localhost --api-key changeme
    python run_pipeline.py --adapter augment --api-url https://your-domain.com --api-key secret
"""

import argparse
import logging
import sys
import time

import requests

sys.path.insert(0, __file__.replace("run_pipeline.py", ""))
from adapters import get_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _fmt_usage(usage: dict) -> str:
    if not usage:
        return ""
    inp = usage.get("input_tokens", 0)
    cached = usage.get("cache_read_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = usage.get("cost_usd", 0.0)
    cache_str = f" (+{cached:,} cached)" if cached else ""
    return f"{inp:,}{cache_str} in + {out:,} out · ${cost:.4f}"


def run(api_url: str, api_key: str, adapter_name: str) -> None:
    adapter = get_adapter(adapter_name)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    work_url = f"{api_url.rstrip('/')}/api/v1/work"

    log.info("Starting pipeline worker with adapter=%s", adapter_name)

    total_cost = 0.0

    while True:
        try:
            response = requests.get(work_url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            log.error("Failed to poll /work: %s", e)
            sys.exit(1)

        task = response.json()

        if task.get("status") == "empty":
            log.info("Queue empty. Total cost this run: $%.4f", total_cost)
            break

        task_id = task["task_id"]
        prompt = task.get("prompt", "")
        content = task.get("content", {})
        step_name = content.get("step_name", "unknown")

        log.info("Running task %s (step: %s)", task_id, step_name)

        try:
            output = adapter.run(prompt, content)
        except RuntimeError as e:
            log.error("Agent error on task %s: %s", task_id, e)
            try:
                requests.post(
                    f"{work_url}/{task_id}/fail",
                    headers=headers,
                    json={"error": str(e)},
                    timeout=10,
                )
            except Exception as report_err:
                log.warning("Could not report failure for task %s: %s", task_id, report_err)
            continue

        usage = getattr(adapter, "last_usage", {})
        if usage:
            total_cost += usage.get("cost_usd", 0.0)
            log.info("  %s: %s", step_name, _fmt_usage(usage))

        try:
            submit = requests.post(
                f"{work_url}/{task_id}",
                headers=headers,
                json={"output": output, "usage": usage or None},
                timeout=30,
            )
            submit.raise_for_status()
            result = submit.json()
            log.info(
                "Task %s complete. Job status: %s  |  Run total: $%.4f",
                task_id, result.get("job_status"), total_cost,
            )
        except requests.RequestException as e:
            log.error("Failed to submit result for task %s: %s", task_id, e)
            sys.exit(1)

        time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiliate pipeline worker")
    parser.add_argument("--adapter",  required=True, help="Agent adapter: claude, augment")
    parser.add_argument("--api-url",  required=True, help="API base URL")
    parser.add_argument("--api-key",  required=True, help="API key (X-API-Key header)")
    args = parser.parse_args()

    run(api_url=args.api_url, api_key=args.api_key, adapter_name=args.adapter)


if __name__ == "__main__":
    main()
