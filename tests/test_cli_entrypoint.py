from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_module_entrypoint_returns_nonzero_for_blocked_sshv1(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["ROW_HOME"] = str(tmp_path)

    init = _run_row(env, "init", "--no-examples")
    assert init.returncode == 0

    add = _run_row(
        env,
        "profile",
        "add",
        "--name",
        "legacy",
        "--protocol",
        "ssh1",
        "--host",
        "192.0.2.15",
        "--username",
        "admin",
    )
    assert add.returncode == 0

    blocked = _run_row(env, "connect", "legacy", "--dry-run")

    assert blocked.returncode == 1
    assert "allow_insecure_sshv1=true" in blocked.stderr


def test_module_entrypoint_rejects_invalid_profile_before_persisting(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["ROW_HOME"] = str(tmp_path)

    init = _run_row(env, "init", "--no-examples")
    assert init.returncode == 0

    add = _run_row(env, "profile", "add", "--name", "bad", "--protocol", "ssh")

    assert add.returncode == 1
    assert "ssh profile requires host" in add.stderr
    data = json.loads((tmp_path / "profiles.json").read_text(encoding="utf-8"))
    assert data["profiles"] == []


def test_module_entrypoint_coverage_prints_protected_platform_goal(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["ROW_HOME"] = str(tmp_path)

    result = _run_row(env, "features", "--coverage")

    assert result.returncode == 0
    assert "Platform verified readiness   : 100.0%" in result.stdout
    assert (
        "Verified denominator        : 10 included, 7 extended excluded; "
        "protected goal source=protected_goal_parity"
    ) in result.stdout
    assert (
        "Protected platform goal       : 0.0% "
        "(100.0% gap; 0/4 accepted; missing-accepted-evidence)"
    ) in result.stdout
    assert "Release asset provenance : not checked by static report" in result.stdout
    assert (
        "Asset provenance gate    : python scripts/check_protected_platform_goal.py "
        "--release-tag v<project.version> --require-complete --assets-dir <release-assets-dir>"
    ) in result.stdout
    assert (
        "Missing protected evidence  : linux-i386, linux-armhf, "
        "windows-xp-native-x86, windows-xp-native-x64"
    ) in result.stdout


def _run_row(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "remote_ops_workspace", *args],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
    )
