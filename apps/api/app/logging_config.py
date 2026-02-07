"""Structured JSON logging for ingestion, normalization, and API requests.

Usage:
    from app.logging_config import get_logger
    logger = get_logger(__name__)
    logger.info("event.ingested", source="jira", entity_id="PROJ-1", duration_ms=42)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Emit one JSON object per log line with consistent fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge extra fields attached via `logger.info("msg", extra={...})`
        for key in ("source", "entity_type", "entity_id", "duration_ms",
                     "status_code", "method", "path", "error", "job_id",
                     "content_hash", "step", "count", "user_id", "role"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class StructuredLogger(logging.Logger):
    """Logger subclass that accepts keyword extras directly in log calls."""

    def _log(  # type: ignore[override]
        self,
        level: int,
        msg: object,
        args: Any,
        exc_info: Any = None,
        extra: dict[str, Any] | None = None,
        stack_info: bool = False,
        stacklevel: int = 1,
        **kwargs: Any,
    ) -> None:
        if extra is None:
            extra = {}
        extra.update(kwargs)
        super()._log(level, msg, args, exc_info=exc_info, extra=extra,
                      stack_info=stack_info, stacklevel=stacklevel + 1)


# Install our logger class globally
logging.setLoggerClass(StructuredLogger)

_configured = False


def configure_logging(*, level: str = "INFO") -> None:
    """Set up structured JSON logging on the root logger (idempotent)."""
    global _configured  # noqa: PLW0603
    if _configured:
        return
    _configured = True

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Return a StructuredLogger that supports keyword extras."""
    configure_logging()
    return logging.getLogger(name)  # type: ignore[return-value]


class Timer:
    """Context manager that measures wall-clock milliseconds."""

    def __init__(self) -> None:
        self.start: float = 0
        self.ms: float = 0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = (time.perf_counter() - self.start) * 1000
