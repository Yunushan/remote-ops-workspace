"""Exercise installer failure handling without installing packages or running the app."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


PWSH = shutil.which("pwsh")
INSTALLER = Path(__file__).resolve().parents[1] / "installers" / "install.ps1"
STAGES = ("version", "venv", "upgrade", "install", "init", "doctor", "welcome")

pytestmark = pytest.mark.skipif(
    os.name != "posix" or PWSH is None,
    reason="requires PowerShell and POSIX test executables",
)


def _fake_python(tmp_path: Path) -> Path:
    executable = tmp_path / "fake-python"
    executable.write_text(
        """#!/bin/sh
set -eu
case "$(basename "$0"):$1" in
  fake-python:-c) stage=version ;;
  fake-python:-m) stage=venv ;;
  python.exe:-m)
    if [ "$4" = "--upgrade" ]; then stage=upgrade; else stage=install; fi ;;
  row.exe:*) stage="$1" ;;
  *) exit 90 ;;
esac
printf '%s\\n' "$stage" >> "$ROW_INSTALLER_TEST_LOG"
if [ "${ROW_INSTALLER_FAIL_STAGE:-}" = "$stage" ]; then exit 42; fi
if [ "$stage" = venv ]; then
  mkdir -p .venv/Scripts
  cp "$0" .venv/Scripts/python.exe
  cp "$0" .venv/Scripts/row.exe
fi
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_installer(
    tmp_path: Path, fail_stage: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    executable = _fake_python(tmp_path)
    log = tmp_path / "stages.log"
    env = os.environ.copy()
    env.update(ROW_INSTALLER_TEST_LOG=str(log), ROW_INSTALLER_FAIL_STAGE=fail_stage)
    result = subprocess.run(
        [
            str(PWSH),
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(INSTALLER),
            "-Python",
            str(executable),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("fail_stage", STAGES)
def test_installer_stops_at_a_failed_native_command(tmp_path: Path, fail_stage: str) -> None:
    result, stages = _run_installer(tmp_path, fail_stage)

    assert result.returncode != 0
    assert stages == list(STAGES[: STAGES.index(fail_stage) + 1])
    assert "Activate this environment later" not in result.stdout


def test_installer_completes_when_all_native_commands_succeed(tmp_path: Path) -> None:
    result, stages = _run_installer(tmp_path, "")

    assert result.returncode == 0, result.stderr
    assert stages == list(STAGES)
    assert "Activate this environment later" in result.stdout
