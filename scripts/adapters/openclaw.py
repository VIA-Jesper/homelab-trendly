import subprocess
import sys
import tempfile
from pathlib import Path

from adapters.base import BaseAdapter

# On Windows, npm/pipx global binaries are .cmd wrappers
_OPENCLAW = "openclaw.cmd" if sys.platform == "win32" else "openclaw"


class OpenClawAdapter(BaseAdapter):
    """
    Adapter for the OpenClaw CLI.
    Install: https://openclaw.dev (or via npm/pip - check their docs)

    Passes the full instruction via a temp file to avoid shell escaping issues.
    Adjust the command flags below if OpenClaw uses different CLI conventions.
    """

    def run(self, prompt: str, content: dict) -> str:
        instruction = self.build_instruction(prompt, content)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(instruction)
            tmp_path = Path(f.name)

        try:
            result = subprocess.run(
                [_OPENCLAW, "--print", "--file", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"openclaw exited with code {result.returncode}: {result.stderr}"
                )

            output = result.stdout.strip()
            if not output:
                raise RuntimeError("openclaw returned empty output")

            return output
        finally:
            tmp_path.unlink(missing_ok=True)
