"""
Unit tests for the adapter prompt/content split (scripts/adapters/base.py).

The work payload separates `prompt` (stable step instruction = system prompt) from
`content` (per-article data = user message). These tests pin that split so model
adapters keep delivering the two on the right channels.

Run: python -m pytest tests/test_adapters.py
"""

import pathlib
import sys

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from adapters.base import BaseAdapter  # noqa: E402


class _StubAdapter(BaseAdapter):
    """Minimal concrete adapter so we can exercise the base helpers."""

    def run(self, prompt: str, content: dict) -> str:  # pragma: no cover - not called
        return ""


_A = _StubAdapter()

# Mirrors the shape of build_step_input(): note `prompt` is present in content too,
# and must NOT be echoed into the user message.
_CONTENT = {
    "prompt": "You are a writer. Output JSON.",
    "context": {"brief": {"article_type": "hero", "products": [{"name": "X"}]}},
    "previous_output": '{"article": "hej"}',
    "step_name": "optimize_seo",
    "attempt": 1,
}


def test_user_message_excludes_prompt():
    msg = _A.build_user_message(_CONTENT)
    assert "You are a writer" not in msg
    assert "prompt:" not in msg


def test_user_message_includes_content_keys():
    msg = _A.build_user_message(_CONTENT)
    assert "context:" in msg
    assert "previous_output:" in msg
    assert "step_name: optimize_seo" in msg
    assert "attempt: 1" in msg


def test_user_message_serialises_dicts_as_json():
    msg = _A.build_user_message(_CONTENT)
    # dict values are JSON (parseable), not Python repr (single quotes / True)
    assert '"article_type": "hero"' in msg
    assert "'article_type'" not in msg


def test_build_instruction_is_system_plus_user():
    prompt = _CONTENT["prompt"]
    instruction = _A.build_instruction(prompt, _CONTENT)
    user = _A.build_user_message(_CONTENT)
    # Agentic path: system prompt prepended, separator, then the user message.
    assert instruction == f"{prompt}\n\n---\n\n{user}"
    assert instruction.startswith(prompt)


def test_empty_content_yields_empty_user_message():
    assert _A.build_user_message({"prompt": "sys only"}) == ""
