from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ensure_data_dir


def append_event(event_type: str, payload: dict[str, Any]) -> Path:
    path = ensure_data_dir() / "audit.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": _redact(payload),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("pass", "secret", "token", "key")):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
