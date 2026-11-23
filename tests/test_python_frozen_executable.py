from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_python_frozen_executable as checker
from scripts.check_python_frozen_executable import (
    reset_managed_directory,
    validate_frozen_smokes,
)

EXPECTED_VERSION = "1.0.27"
EXPECTED_CATALOG = {
    "release_architectures": [{"id": "windows-x64", "bits": 64}],
    "windows_legacy_targets": [{"version": "Windows XP"}],
}


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(["row"], returncode, stdout=stdout, stderr=stderr)


def test_frozen_smokes_accept_real_version_and_platform_json() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(0, "remote-ops-workspace 1.0.27\n"),
        platforms_smoke=_completed(0, json.dumps(EXPECTED_CATALOG)),
        expected_version=EXPECTED_VERSION,
        expected_platforms=EXPECTED_CATALOG,
    )

    assert errors == []


def test_frozen_smokes_reject_failed_or_malformed_results() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(1, stderr="boom"),
        platforms_smoke=_completed(0, "not json"),
        expected_version=EXPECTED_VERSION,
        expected_platforms=EXPECTED_CATALOG,
    )

    assert "frozen --version smoke exited 1" in errors
    assert "frozen platforms --json smoke returned invalid JSON" in errors


def test_frozen_smokes_reject_empty_platform_object() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(0, "wrong product\n"),
        platforms_smoke=_completed(0, "{}"),
        expected_version=EXPECTED_VERSION,
        expected_platforms=EXPECTED_CATALOG,
    )

    assert f"frozen --version smoke must report ROW package version {EXPECTED_VERSION}" in errors
    assert "frozen platforms --json smoke differs from the checked-out platform catalog" in errors


def test_reset_managed_directory_stays_inside_root(tmp_path: Path) -> None:
    managed = tmp_path / "work"
    managed.mkdir()
    (managed / "stale.txt").write_text("stale", encoding="utf-8")

    reset_managed_directory(managed, root=tmp_path)

    assert managed.is_dir()
    assert list(managed.iterdir()) == []
    with pytest.raises(ValueError):
        reset_managed_directory(tmp_path, root=tmp_path)



def test_frozen_smokes_reject_stale_version_and_nonempty_partial_catalog() -> None:
    errors = validate_frozen_smokes(
        version_smoke=_completed(0, "remote-ops-workspace 1.0.26\n"),
        platforms_smoke=_completed(0, json.dumps({
            "release_architectures": EXPECTED_CATALOG["release_architectures"],
        })),
        expected_version=EXPECTED_VERSION,
        expected_platforms=EXPECTED_CATALOG,
    )

    assert errors == [
        f"frozen --version smoke must report ROW package version {EXPECTED_VERSION}",
        "frozen platforms --json smoke differs from the checked-out platform catalog",
    ]


def test_frozen_cli_launch_denial_retains_failed_artifact_evidence(tmp_path, monkeypatch, capsys) -> None:
    output = tmp_path / "evidence"
    content = b"fixture executable bytes"
    expected_project = tmp_path / "pyproject.toml"
    expected_project.write_text(f'[project]\nversion = "{EXPECTED_VERSION}"\n', encoding="utf-8")
    catalog_bytes = json.dumps(EXPECTED_CATALOG).encode("utf-8")
    expected_catalog = tmp_path / "configs" / "platform_targets.json"
    expected_catalog.parent.mkdir()
    expected_catalog.write_bytes(catalog_bytes)
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    def run(command, **kwargs):
        if command[1:3] == ["-m", "PyInstaller"]:
            if command[-1] == "--version":
                return _completed(0, "6.22.3\n")
            dist = Path(command[command.index("--distpath") + 1])
            name = command[command.index("--name") + 1]
            suffix = ".exe" if os.name == "nt" else ""
            (dist / f"{name}{suffix}").write_bytes(content)
            return _completed(0)
        assert kwargs["cwd"] == output
        raise PermissionError("Application Control denied launch")

    monkeypatch.setattr(checker, "subprocess", SimpleNamespace(
        run=run,
        CompletedProcess=subprocess.CompletedProcess,
        TimeoutExpired=subprocess.TimeoutExpired,
    ))
    interpreter = f"{checker.sys.version_info.major}.{checker.sys.version_info.minor}"
    assert checker.main(["--expected-python", interpreter, "--out-dir", str(output)]) == 1

    report = json.loads((output / "evidence.json").read_bytes())
    assert report["passed"] is False
    assert report["expected_project_version"] == EXPECTED_VERSION
    assert report["source_platform_catalog_sha256"] == hashlib.sha256(catalog_bytes).hexdigest()
    assert report["executable"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert report["smokes"]["version"]["returncode"] == 126
    assert "Application Control denied launch" in report["smokes"]["version"]["stderr"]
    assert "frozen --version smoke exited 126" in capsys.readouterr().err
