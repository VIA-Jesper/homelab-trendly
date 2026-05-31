import json
import shutil
import subprocess
import sys

from adapters.base import BaseAdapter


def _find_claude() -> str:
    resolved = shutil.which("claude")
    if resolved:
        return resolved
    if sys.platform == "win32":
        resolved = shutil.which("claude.cmd")
        if resolved:
            return resolved
    raise FileNotFoundError(
        "claude executable not found on PATH. "
        "Install with: npm install -g @anthropic-ai/claude-code"
    )


_CLAUDE = _find_claude()


class ClaudeAdapter(BaseAdapter):
    """
    Adapter for the Claude CLI (claude command).
    Install: npm install -g @anthropic-ai/claude-code

    Uses --output-format json so the CLI returns a structured envelope with
    token counts and cost_usd alongside the result text. After each run,
    self.last_usage contains {"input_tokens", "output_tokens", "cost_usd"}.
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model
        self.last_usage: dict = {}

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)

        proc = subprocess.run(
            [_CLAUDE, "--print", "--model", self.model, "--output-format", "json"],
            input=instruction,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited with code {proc.returncode}: {proc.stderr[:400]}"
            )

        raw = proc.stdout.strip()
        if not raw:
            raise RuntimeError("claude returned empty output")

        # Parse the JSON envelope the CLI wraps around the result
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError:
            # Unexpected: CLI returned plain text, not JSON — treat as raw output
            self.last_usage = {}
            return raw

        if envelope.get("is_error"):
            raise RuntimeError(f"claude reported error: {envelope.get('result', '')[:400]}")

        output = envelope.get("result", "").strip()
        if not output:
            raise RuntimeError("claude returned empty result in JSON envelope")

        # Strip markdown code fences if the model wrapped JSON output in ```json ... ```
        if output.startswith("```"):
            lines = output.splitlines()
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            output = "\n".join(lines[1:end]).strip()

        # Capture usage for the caller to log / store
        # CLI uses total_cost_usd (not cost_usd); input_tokens is only new tokens —
        # cache_read_input_tokens holds the bulk of the context on warm runs.
        usage = envelope.get("usage", {})
        self.last_usage = {
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_write_tokens": usage.get("cache_creation_input_tokens", 0),
            "cost_usd": envelope.get("total_cost_usd", 0.0),
        }

        return output
