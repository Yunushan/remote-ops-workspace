from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .file_safety import append_jsonl_private
from .paths import ensure_data_dir

SENSITIVE_KEY_TOKENS = ("pass", "secret", "token", "key")
SENSITIVE_ARG_NAMES = {
    "-N",
    "--new-passphrase",
    "--passphrase",
    "--password",
    "--secret",
    "--token",
}
REDACTED = "***REDACTED***"


def append_event(event_type: str, payload: dict[str, Any]) -> Path:
    path = ensure_data_dir() / "audit.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": _redact(payload),
    }
    append_jsonl_private(path, record)
    return path


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(token in key.lower() for token in SENSITIVE_KEY_TOKENS):
                redacted[key] = REDACTED
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return _redact_sequence(value)
    return value


def _redact_sequence(value: list[Any]) -> list[Any]:
    redacted: list[Any] = []
    redact_next = False
    for item in value:
        if redact_next:
            redacted.append(REDACTED)
            redact_next = False
            continue
        if isinstance(item, str) and item in SENSITIVE_ARG_NAMES:
            redacted.append(item)
            redact_next = True
            continue
        redacted.append(_redact(item))
    return redacted
