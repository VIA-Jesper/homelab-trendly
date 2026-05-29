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
            prompt: The instruction prompt for this pipeline step
            content: Full task context (previous_output, job context, etc.)

        Returns:
            Agent output as a plain string.

        Raises:
            RuntimeError: If the agent exits with a non-zero status or produces no output.
        """
        ...

    def build_instruction(self, prompt: str, content: dict) -> str:
        """
        Combine prompt and content into a single instruction string for the agent.
        Override this if the adapter needs a different format.
        """
        context_block = "\n".join(f"{k}: {v}" for k, v in content.items() if k != "prompt")
        return f"{prompt}\n\n---\n{context_block}"
