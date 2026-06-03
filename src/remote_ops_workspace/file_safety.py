from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
PUBLIC_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
PRIVATE_DIR_MODE = stat.S_IRWXU


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    chmod_best_effort(path, PRIVATE_DIR_MODE)


def chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


def write_json_atomic(
    path: Path,
    data: Any,
    *,
    private: bool = False,
    sort_keys: bool = True,
    indent: int = 2,
) -> None:
    payload = json.dumps(data, indent=indent, sort_keys=sort_keys) + "\n"
    write_text_atomic(path, payload, private=private)


def write_text_atomic(path: Path, text: str, *, private: bool = False) -> None:
    _write_bytes_atomic(path, text.encode("utf-8"), private=private)


def write_bytes_atomic(path: Path, payload: bytes, *, private: bool = False) -> None:
    _write_bytes_atomic(path, payload, private=private)


def append_jsonl_private(path: Path, record: Any) -> None:
    ensure_private_dir(path.parent)
    line = json.dumps(record, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    chmod_best_effort(path, PRIVATE_FILE_MODE)


def _write_bytes_atomic(path: Path, payload: bytes, *, private: bool) -> None:
    ensure_private_dir(path.parent)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    mode = PRIVATE_FILE_MODE if private else PUBLIC_FILE_MODE
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        chmod_best_effort(temp_path, mode)
        os.replace(temp_path, path)
        chmod_best_effort(path, mode)
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
