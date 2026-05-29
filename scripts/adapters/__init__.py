from adapters.augment import AugmentAdapter
from adapters.base import BaseAdapter
from adapters.claude import ClaudeAdapter
from adapters.openclaw import OpenClawAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "augment": AugmentAdapter,
    "claude": ClaudeAdapter,
    "openclaw": OpenClawAdapter,
}


def get_adapter(name: str) -> BaseAdapter:
    cls = ADAPTERS.get(name)
    if not cls:
        available = ", ".join(ADAPTERS.keys())
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return cls()
