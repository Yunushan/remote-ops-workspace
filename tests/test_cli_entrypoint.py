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


def _run_row(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "remote_ops_workspace", *args],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
    )
