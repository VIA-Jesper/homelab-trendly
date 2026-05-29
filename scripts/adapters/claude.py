import subprocess
import sys

from adapters.base import BaseAdapter

# On Windows, npm/pipx global binaries are .cmd wrappers
_CLAUDE = "claude.cmd" if sys.platform == "win32" else "claude"


class ClaudeAdapter(BaseAdapter):
    """
    Adapter for the Claude CLI (claude command).
    Install: npm install -g @anthropic-ai/claude-code
    Docs: https://docs.anthropic.com/en/docs/claude-code

    Uses --print for non-interactive mode and --instruction-file to avoid
    shell escaping issues with long prompts.
    """

    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
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
