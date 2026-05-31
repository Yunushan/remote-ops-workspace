from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def platform_targets_path() -> Path:
    return repo_root() / "configs" / "platform_targets.json"


def load_platform_targets(path: Path | None = None) -> dict[str, Any]:
    target = path or platform_targets_path()
    return json.loads(target.read_text(encoding="utf-8"))


def release_architectures(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_platform_targets(path).get("release_architectures", []))


def windows_legacy_targets(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_platform_targets(path).get("windows_legacy_targets", []))
