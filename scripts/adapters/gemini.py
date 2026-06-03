import logging
import os

import google.generativeai as genai

from adapters.base import BaseAdapter

log = logging.getLogger(__name__)

# Gemini 2.5 Flash paid-tier pricing ($/M tokens).
# Tracked even on free tier so cost figures are comparable to Claude runs.
_INPUT_COST_PER_M = 0.075
_OUTPUT_COST_PER_M = 0.30


class GeminiAdapter(BaseAdapter):
    """
    Adapter for Google Gemini via the google-generativeai SDK.

    Default model: gemini-2.5-flash (free tier: 1,500 req/day, no card required).
    Requires GEMINI_API_KEY environment variable — get a key at aistudio.google.com.

    Usage:
        $env:GEMINI_API_KEY = "your-key"
        python run_pipeline.py --adapter gemini --api-url http://localhost:8000 --api-key changeme
    """

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable not set. "
                "Get a free key at https://aistudio.google.com"
            )
        genai.configure(api_key=api_key)
        self.model_name = model
        self._model = genai.GenerativeModel(model)
        self.last_usage: dict = {}

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)
        log.info("Sending instruction to Gemini %s (size: %d chars)", self.model_name, len(instruction))

        try:
            response = self._model.generate_content(
                instruction,
                generation_config=genai.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=16384,
                ),
            )
        except Exception as e:
            raise RuntimeError(f"Gemini API error: {e}") from e

        if not response.candidates:
            raise RuntimeError("Gemini returned no candidates — likely a safety block")

        output = response.text.strip()
        if not output:
            raise RuntimeError("Gemini returned empty output")

        # Strip markdown code fences if model wrapped output in ```json ... ```
        if output.startswith("```"):
            lines = output.splitlines()
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            output = "\n".join(lines[1:end]).strip()

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
        log.info("  Gemini usage: %s", f"{inp:,} in + {out:,} out · ${cost:.4f} (est.)")

        return output
