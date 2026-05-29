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


def run(api_url: str, api_key: str, adapter_name: str) -> None:
    adapter = get_adapter(adapter_name)
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    work_url = f"{api_url.rstrip('/')}/api/v1/work"

    log.info("Starting pipeline worker with adapter=%s", adapter_name)

    while True:
        # Poll for next task
        try:
            response = requests.get(work_url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            log.error("Failed to poll /work: %s", e)
            sys.exit(1)

        task = response.json()

        if task.get("status") == "empty":
            log.info("Queue empty. Worker exiting.")
            break

        task_id = task["task_id"]
        prompt = task.get("prompt", "")
        content = task.get("content", {})

        log.info("Running task %s (step: %s)", task_id, content.get("step_name", "unknown"))

        # Run the agent - one clean invocation per task
        try:
            output = adapter.run(prompt, content)
        except RuntimeError as e:
            log.error("Agent error on task %s: %s", task_id, e)
            sys.exit(1)

        # Submit result
        try:
            submit = requests.post(
                f"{work_url}/{task_id}",
                headers=headers,
                json={"output": output},
                timeout=30,
            )
            submit.raise_for_status()
            result = submit.json()
            log.info("Task %s complete. Job status: %s", task_id, result.get("job_status"))
        except requests.RequestException as e:
            log.error("Failed to submit result for task %s: %s", task_id, e)
            sys.exit(1)

        # Brief pause between tasks to avoid hammering the API
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
