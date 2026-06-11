import json
import logging
import os
import re
import time

from adapters.base import BaseAdapter

log = logging.getLogger(__name__)

# Gemini 3.1 Pro Preview pricing ($/M tokens) - tracked even on free tier
# so cost figures are comparable to Claude runs.
_INPUT_COST_PER_M = 1.25
_OUTPUT_COST_PER_M = 10.00

# Free tier limits vary by model (10-15 RPM). 6.5s is safe for the most
# restrictive (10 RPM). Set GEMINI_MIN_INTERVAL=0 to disable on paid tier.
_DEFAULT_MIN_INTERVAL = 6.5
_MAX_RETRIES = 4


class GeminiAdapter(BaseAdapter):
    """
    Adapter for Google Gemini via the google-genai SDK.

    Default model: gemini-3.1-pro-preview (free tier: limited experimental quota).
    Requires GEMINI_API_KEY environment variable - get a key at aistudio.google.com.

    Rate limiting:
      Enforces a minimum interval between calls (default 6.5s, free-tier safe).
      On 429/ResourceExhausted the adapter backs off exponentially before retrying.
      Set GEMINI_MIN_INTERVAL=0 to disable the floor (paid tier / Vertex).

    Usage:
        $env:GEMINI_API_KEY = "your-key"
        python run_pipeline.py --adapter gemini --api-url http://localhost:8000 --api-key changeme
    """

    def __init__(self, model: str = "gemini-3.1-pro-preview") -> None:
        from google import genai  # noqa: PLC0415 - lazy import, only loaded when using Gemini
        from google.genai import types as _types  # noqa: PLC0415
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable not set. "
                "Get a free key at https://aistudio.google.com"
            )
        self._client = genai.Client(api_key=api_key)
        self._types = _types
        self.model_name = model
        self.last_usage: dict = {}
        self._min_interval = float(os.environ.get("GEMINI_MIN_INTERVAL", _DEFAULT_MIN_INTERVAL))
        self._last_call: float = 0.0

    def _call_with_backoff(self, instruction: str) -> object:
        """Call the Gemini API, respecting min interval and retrying on rate limit errors."""
        backoff = 15.0
        for attempt in range(_MAX_RETRIES + 1):
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)

            try:
                self._last_call = time.monotonic()
                return self._client.models.generate_content(
                    model=self.model_name,
                    contents=instruction,
                    config=self._types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=16384,
                    ),
                )
            except Exception as e:
                err = str(e)
                is_rate_limit = (
                    "429" in err
                    or "resourceexhausted" in err.lower()
                    or "rate limit" in err.lower()
                    or "quota" in err.lower()
                )
                if is_rate_limit and attempt < _MAX_RETRIES:
                    retry_after = backoff
                    m = re.search(r'retry.after[^\d]*(\d+)', err, re.IGNORECASE)
                    if m:
                        retry_after = float(m.group(1)) + 1.0
                    log.warning(
                        "Gemini rate limit hit (attempt %d/%d) - sleeping %.0fs",
                        attempt + 1, _MAX_RETRIES, retry_after,
                    )
                    time.sleep(retry_after)
                    backoff = min(backoff * 2, 120.0)
                else:
                    raise RuntimeError(f"Gemini API error: {e}") from e
        raise RuntimeError("Gemini: exhausted retries after repeated rate limit errors")

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)
        log.info("Sending instruction to Gemini %s (size: %d chars)", self.model_name, len(instruction))

        response = self._call_with_backoff(instruction)

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates - likely a safety block")

        output = response.text.strip()
        if not output:
            raise RuntimeError("Gemini returned empty output")

        # Strip markdown code fences if model wrapped output in ```json ... ```
        if output.startswith("```"):
            lines = output.splitlines()
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            output = "\n".join(lines[1:end]).strip()

        # Gemini sometimes writes literal newlines inside JSON strings, or adds
        # trailing characters after the closing brace. Use raw_decode so we
        # parse only the first complete JSON value and discard any trailing junk.
        try:
            parsed, _ = json.JSONDecoder(strict=False).raw_decode(output)
            output = json.dumps(parsed, ensure_ascii=False)
        except (ValueError, json.JSONDecodeError):
            pass  # Not JSON output - return as-is

        # Capture usage for cost tracking
        usage = response.usage_metadata
        inp = getattr(usage, "prompt_token_count", 0) or 0
        out = getattr(usage, "candidates_token_count", 0) or 0
        cost = (inp * _INPUT_COST_PER_M + out * _OUTPUT_COST_PER_M) / 1_000_000
        self.last_usage = {
            "input_tokens": inp,
            "output_tokens": out,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": cost,
        }

        return output
