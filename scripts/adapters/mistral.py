import json
import logging
import os
import time

from adapters.base import BaseAdapter

log = logging.getLogger(__name__)

# Mistral pricing $/M tokens - update if models change
_PRICING = {
    "mistral-large-latest":  (2.00, 6.00),
    "mistral-medium-latest": (0.40, 2.00),
    "mistral-small-latest":  (0.20, 0.60),
    "open-mistral-nemo":     (0.15, 0.15),
}
_DEFAULT_PRICING = (2.00, 6.00)

# Free tier: ~1 req/s hard limit. 1.2s gives a small margin.
# Override with MISTRAL_MIN_INTERVAL env var (seconds, float).
_DEFAULT_MIN_INTERVAL = 1.2
_MAX_RETRIES = 4


class MistralAdapter(BaseAdapter):
    """
    Adapter for Mistral AI via the mistralai SDK.

    Default model: mistral-large-latest.
    Requires MISTRAL_API_KEY environment variable.

    Rate limiting:
      Enforces a minimum interval between calls (default 1.2s, free-tier safe).
      On 429 the adapter reads Retry-After if present, otherwise backs off
      exponentially (5s → 10s → 20s → 40s) before retrying up to 4 times.
      Set MISTRAL_MIN_INTERVAL=0 to disable the inter-call floor (paid tier).

    Usage:
        python run_pipeline.py --adapter mistral --api-url http://localhost:8000 --api-key changeme
        python run_pipeline.py --adapter mistral --adapter-model mistral-small-latest ...
    """

    def __init__(self, model: str = "mistral-large-latest") -> None:
        from mistralai.client.sdk import Mistral  # noqa: PLC0415
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY environment variable not set. "
                "Get a key at https://console.mistral.ai"
            )
        self._client = Mistral(api_key=api_key)
        self.model_name = model
        self.last_usage: dict = {}
        self._min_interval = float(os.environ.get("MISTRAL_MIN_INTERVAL", _DEFAULT_MIN_INTERVAL))
        self._last_call: float = 0.0

    def _call_with_backoff(self, instruction: str) -> object:
        """Call the Mistral API, respecting min interval and retrying on 429."""
        backoff = 5.0
        for attempt in range(_MAX_RETRIES + 1):
            # Enforce minimum inter-call interval
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)

            try:
                self._last_call = time.monotonic()
                return self._client.chat.complete(
                    model=self.model_name,
                    messages=[{"role": "user", "content": instruction}],
                    temperature=0.7,
                    max_tokens=8192,
                )
            except Exception as e:
                err = str(e)
                is_rate_limit = "429" in err or "rate limit" in err.lower() or "too many" in err.lower()
                if is_rate_limit and attempt < _MAX_RETRIES:
                    # Try to honour Retry-After if it appears in the error message
                    retry_after = backoff
                    import re
                    m = re.search(r'retry.after[^\d]*(\d+)', err, re.IGNORECASE)
                    if m:
                        retry_after = float(m.group(1)) + 1.0
                    log.warning(
                        "Mistral rate limit hit (attempt %d/%d) - sleeping %.0fs",
                        attempt + 1, _MAX_RETRIES, retry_after,
                    )
                    time.sleep(retry_after)
                    backoff = min(backoff * 2, 60.0)
                else:
                    raise RuntimeError(f"Mistral API error: {e}") from e
        raise RuntimeError("Mistral: exhausted retries after repeated rate limit errors")

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)
        log.info("Sending instruction to Mistral %s (size: %d chars)", self.model_name, len(instruction))

        response = self._call_with_backoff(instruction)

        if not response.choices:
            raise RuntimeError("Mistral returned no choices")

        output = (response.choices[0].message.content or "").strip()
        if not output:
            raise RuntimeError("Mistral returned empty output")

        # Strip markdown code fences if model wrapped output in ```json ... ```
        if output.startswith("```"):
            lines = output.splitlines()
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            output = "\n".join(lines[1:end]).strip()

        # Parse and re-serialise JSON to strip any trailing junk
        try:
            parsed, _ = json.JSONDecoder(strict=False).raw_decode(output)
            output = json.dumps(parsed, ensure_ascii=False)
        except (ValueError, json.JSONDecodeError):
            pass

        # Cost tracking
        usage = response.usage
        inp = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        in_cost, out_cost = _PRICING.get(self.model_name, _DEFAULT_PRICING)
        cost = (inp * in_cost + out * out_cost) / 1_000_000
        self.last_usage = {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": cost,
        }

        return output
