from abc import ABC, abstractmethod


class IStepHandler(ABC):
    """
    Interface for custom post-processing after a pipeline step completes.

    Implement this to hook into step completion events:
    - Transform or validate output before it is stored
    - Trigger notifications or webhooks
    - Auto-publish when a specific step completes
    - Write output to external systems

    Register implementations in services/pipeline.py.
    """

    @abstractmethod
    def can_handle(self, step_name: str) -> bool:
        """Return True if this handler should run for the given step name."""
        ...

    @abstractmethod
    async def process(self, step_data: dict, output: str) -> dict:
        """
        Process the agent output for a completed step.

        Args:
            step_data: The step record dict (step_name, job_id, context, etc.)
            output: Raw agent output string

        Returns:
            Dict with at minimum: { "output": str, "status": "complete" | "failed" }
            May include additional fields stored back to step.input.
        """
        ...
