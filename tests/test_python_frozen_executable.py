from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.check_python_frozen_executable import (
    reset_managed_directory,
    validate_frozen_smokes,
)


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(["row"], returncode, stdout=stdout, stderr=stderr)


def test_frozen_smokes_accept_real_version_and_platform_json() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(0, "remote-ops-workspace 1.0.24\n"),
        platforms_smoke=_completed(0, json.dumps({"targets": ["windows-x64"]})),
    )

    assert errors == []


def test_frozen_smokes_reject_failed_or_malformed_results() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(1, stderr="boom"),
        platforms_smoke=_completed(0, "not json"),
    )

    assert "frozen --version smoke exited 1" in errors
    assert "frozen platforms --json smoke returned invalid JSON" in errors


def test_frozen_smokes_reject_empty_platform_object() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(0, "wrong product\n"),
        platforms_smoke=_completed(0, "{}"),
    )

    assert "frozen --version smoke did not report the ROW package version" in errors
    assert "frozen platforms --json smoke returned an empty or non-object payload" in errors


def test_reset_managed_directory_stays_inside_root(tmp_path: Path) -> None:
    managed = tmp_path / "work"
    managed.mkdir()
    (managed / "stale.txt").write_text("stale", encoding="utf-8")

    reset_managed_directory(managed, root=tmp_path)

    assert managed.is_dir()
    assert list(managed.iterdir()) == []
    with pytest.raises(ValueError):
        reset_managed_directory(tmp_path, root=tmp_path)
