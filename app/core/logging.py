"""
Structured logging setup.
Call `setup_logging()` once at application startup.
Use `get_logger(__name__)` in every module.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.config import get_settings

settings = get_settings()


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter – avoids heavy dependency on structlog/loguru."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        import traceback

        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = traceback.format_exception(*record.exc_info)
        if hasattr(record, "extra"):
            payload.update(record.extra)  # type: ignore[arg-type]
        return json.dumps(payload)


def setup_logging() -> None:
    """Configure root logger; call once at startup."""
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
            )
        )

    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.  Use as: logger = get_logger(__name__)"""
    return logging.getLogger(name)
