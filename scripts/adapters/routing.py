import logging

from adapters.base import BaseAdapter

log = logging.getLogger(__name__)


class RoutingAdapter(BaseAdapter):
    """
    Dispatches each pipeline step to a different adapter based on step_name.

    step_overrides: {step_name: adapter_instance}
    default: adapter used for any step not in step_overrides
    """

    def __init__(self, default: BaseAdapter, step_overrides: dict[str, BaseAdapter]) -> None:
        self.default = default
        self.step_overrides = step_overrides
        self.last_usage: dict = {}

    def run(self, prompt: str, content: dict) -> str:
        step = content.get("step_name", "")
        adapter = self.step_overrides.get(step, self.default)
        if step in self.step_overrides:
            log.info("Routing step '%s' to %s", step, type(adapter).__name__)
        result = adapter.run(prompt, content)
        self.last_usage = getattr(adapter, "last_usage", {})
        return result
