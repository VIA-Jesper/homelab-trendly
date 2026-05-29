import subprocess
import sys
import tempfile
from pathlib import Path

from adapters.base import BaseAdapter

# On Windows, npm global binaries are .cmd wrappers - subprocess needs the full name
_AUGGIE = "auggie.cmd" if sys.platform == "win32" else "auggie"


class AugmentAdapter(BaseAdapter):
    """
    Adapter for Augment agent CLI (auggie).

    Uses non-interactive print mode so the script can capture output:
      auggie --print --quiet --instruction-file <tmpfile>

    - --print     : run once without the interactive TUI, exit when done
    - --quiet     : only output the final answer (no tool call noise)
    - --instruction-file : reads the full prompt from a file, avoiding
                           shell escaping issues with long/special content

    Requires auggie to be installed and logged in:
      npm install -g @augmentcode/auggie
      auggie login
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
                [_AUGGIE, "--print", "--quiet", "--instruction-file", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=600,  # content generation can take a while
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"auggie exited with code {result.returncode}: {result.stderr}"
                )

            output = result.stdout.strip()
            if not output:
                raise RuntimeError("auggie returned empty output")

            return output
        finally:
            tmp_path.unlink(missing_ok=True)
