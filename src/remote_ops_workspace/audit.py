from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .file_safety import append_jsonl_private
from .paths import ensure_data_dir
from .redaction import REDACTED, redact_value


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
    return redact_value(value)
