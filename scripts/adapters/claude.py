import shutil
import subprocess
import sys

from adapters.base import BaseAdapter


def _find_claude() -> str:
    # Try the resolved path first (handles .exe, .cmd, or bare 'claude')
    resolved = shutil.which("claude")
    if resolved:
        return resolved
    # Fallback: npm global installs on Windows use a .cmd wrapper
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
    Docs: https://docs.anthropic.com/en/docs/claude-code

    Uses --print for non-interactive mode and --instruction-file to avoid
    shell escaping issues with long prompts.
    """

    def __init__(self, model: str = "claude-sonnet-4-6") -> None:
        self.model = model

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)

        # Claude Code reads the prompt from stdin when piped, which avoids
        # any shell escaping issues with long or special-character content.
        result = subprocess.run(
            [_CLAUDE, "--print", "--model", self.model],
            input=instruction,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"claude exited with code {result.returncode}: {result.stderr}"
            )

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("claude returned empty output")

        return output
