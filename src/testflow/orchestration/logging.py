"""
Structured logging for the TestFlow pipeline.

Uses Python's built-in logging with a JSON formatter for machine-readable output.
All pipeline events are logged to stdout and optionally to a log file.
"""
import json
import logging
import sys
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class PipelineRunStats:
    run_id: str
    topic: str
    keyword: str
    category_id: int
    article_type: str
    brief_attempts: int = 0
    article_attempts: int = 0
    optimization_attempts: int = 0
    total_phases: int = 0
    duration_sec: float = 0.0
    status: str = "in_progress"
    errors: list[str] = field(default_factory=list)


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra"):
            data.update(record.extra)
        return json.dumps(data, ensure_ascii=False)


def get_logger(name: str = "testflow") -> logging.Logger:
    """Return a logger with JSON formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# Module-level logger for convenience
log = get_logger()
