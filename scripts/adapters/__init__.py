from adapters.augment import AugmentAdapter
from adapters.base import BaseAdapter
from adapters.claude import ClaudeAdapter
from adapters.gemini import GeminiAdapter
from adapters.mistral import MistralAdapter
from adapters.openclaw import OpenClawAdapter
from adapters.routing import RoutingAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "augment": AugmentAdapter,
    "claude": ClaudeAdapter,
    "gemini": GeminiAdapter,
    "mistral": MistralAdapter,
    "openclaw": OpenClawAdapter,
}


def get_adapter(name: str, model: str | None = None) -> BaseAdapter:
    cls = ADAPTERS.get(name)
    if not cls:
        available = ", ".join(ADAPTERS.keys())
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return cls(model=model) if model else cls()
