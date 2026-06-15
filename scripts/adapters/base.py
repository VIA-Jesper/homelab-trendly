import json
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """
    Base class for agent adapters.
    Each adapter wraps one agentic runtime (Claude CLI, Augment, OpenClaw, etc.)

    The adapter receives a prompt + content dict and returns the agent's output as a string.
    That's all it does - the pipeline loop lives in run_pipeline.py.
    """

    @abstractmethod
    def run(self, prompt: str, content: dict) -> str:
        """
        Execute the agent with the given prompt and content.

        Args:
            prompt: The step instruction blob (persona + rules + output contract).
                    It is stable per (step, article_type) and carries no per-article
                    data, so model adapters deliver it as the SYSTEM prompt. Agentic
                    CLIs that have no separate system channel fold it into the user
                    turn via build_instruction().
            content: Full task context (previous_output, job context, etc.) - the
                    variable per-article data, delivered as the user message.

        Returns:
            Agent output as a plain string.

        Raises:
            RuntimeError: If the agent exits with a non-zero status or produces no output.
        """
        ...

    def build_user_message(self, content: dict) -> str:
        """
        Render the task content (brief, previous_output, qa_feedback, ...) into a
        single user-turn string.

        Dicts and lists are JSON-serialised so agents receive valid, readable JSON
        rather than Python repr strings. This matters for the generator prompt which
        reads structured data from context.brief - Python repr is not parseable JSON.

        The "prompt" key is skipped: the step instruction is delivered separately as
        the system prompt, not repeated inside the user turn.
        """
        parts = []
        for k, v in content.items():
            if k == "prompt":
                continue
            if isinstance(v, (dict, list)):
                parts.append(f"{k}:\n{json.dumps(v, ensure_ascii=False, indent=2)}")
            else:
                parts.append(f"{k}: {v}")
        return "\n\n".join(parts)

    def build_instruction(self, prompt: str, content: dict) -> str:
        """
        Combine system prompt + user message into ONE string.

        Used by agentic adapters (auggie, openclaw) that drive a full agent with its
        own baked-in system prompt and expose no separate system-prompt channel, so
        our instruction must ride in the user turn. Model adapters (claude/gemini/
        mistral) instead send `prompt` as the system prompt and build_user_message()
        as the user turn.
        """
        return f"{prompt}\n\n---\n\n{self.build_user_message(content)}"
