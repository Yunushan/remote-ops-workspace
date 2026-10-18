from __future__ import annotations

import logging
import os
import sys
from typing import IO

from .redaction import redact_text

LOG_LEVEL_ENV = "ROW_LOG_LEVEL"
LOGGER_NAME = "remote_ops_workspace"
DEFAULT_LOG_LEVEL = "WARNING"
VALID_LOG_LEVELS = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RedactingFormatter(logging.Formatter):
    """Format records through the shared redaction layer so secrets never leak."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def resolve_log_level(value: str | None) -> str:
    candidate = (value if value is not None else os.environ.get(LOG_LEVEL_ENV, "")).strip().upper()
    if not candidate:
        return DEFAULT_LOG_LEVEL
    if candidate not in VALID_LOG_LEVELS:
        raise ValueError(f"unsupported log level: {value!r}")
    return candidate


def configure_logging(level: str | None = None, *, stream: IO[str] | None = None) -> logging.Logger:
    resolved = resolve_log_level(level)
    logger = logging.getLogger(LOGGER_NAME)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    for existing in tuple(logger.handlers):
        logger.removeHandler(existing)
        existing.close()
    logger.addHandler(handler)
    logger.setLevel(resolved)
    logger.propagate = False
    return logger


def diagnostic_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
