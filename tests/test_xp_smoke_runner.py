from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="xp smoke runner is a Windows cmd script")


def test_xp_smoke_runner_writes_bound_evidence_from_proof_file(tmp_path: Path) -> None:
    runner = Path("scripts/xp_smoke_runner.cmd").resolve()
    proof = tmp_path / "proof.txt"
    output = tmp_path / "xp-smoke-evidence" / "modern_defaults_unchanged.txt"
    proof.write_text(
        "modern TLS minimum: TLS 1.2\n"
        "modern TLS preferred: TLS 1.3\n"
        "modern defaults unchanged: true\n"
        "weak crypto global default: false\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(runner),
            "--target",
            "windows-xp-native-x86",
            "--release-tag",
            "v1.0.2",
            "--smoke-id",
            "modern_defaults_unchanged",
            "--evidence-file",
            str(output),
            "--proof-file",
            str(proof),
            "--host-label",
            "xp-x86-lab-01",
            "--evidence-run-id",
            "xp-x86-1-0-2-20260620t120000z",
            "--observed-at-utc",
            "2026-06-20T12:00:00Z",
            "--source-workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "--source-head-sha",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--source-run-attempt",
            "1",
            "--os-name",
            "Windows XP",
            "--os-architecture",
            "x86",
            "--os-service-pack",
            "SP3",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    text = output.read_text(encoding="utf-8")
    assert "xp smoke target: windows-xp-native-x86" in text
    assert "xp smoke release: v1.0.2" in text
    assert "xp smoke id: modern_defaults_unchanged" in text
    assert "xp smoke os name: Windows XP" in text
    assert "xp smoke os architecture: x86" in text
    assert "xp smoke os service pack: SP3" in text
    assert "xp smoke host probe command: ver" in text
    assert "xp smoke host probe output:" in text
    assert "xp smoke processor architecture env:" in text
    assert "xp smoke processor architecture w6432 env:" in text
    assert "xp smoke wmic os caption:" in text
    assert "xp smoke wmic os csdversion:" in text
    assert "xp smoke host label: xp-x86-lab-01" in text
    assert "xp smoke evidence run id: xp-x86-1-0-2-20260620t120000z" in text
    assert "xp smoke observed at utc: 2026-06-20T12:00:00Z" in text
    assert "xp smoke source workflow run: https://github.com/example/remote-ops-workspace/actions/runs/12345" in text
    assert "xp smoke source head sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" in text
    assert "xp smoke source run attempt: 1" in text
    assert "modern TLS preferred: TLS 1.3" in text
    assert "weak crypto global default: false" in text


def test_xp_smoke_runner_requires_existing_proof_file(tmp_path: Path) -> None:
    runner = Path("scripts/xp_smoke_runner.cmd").resolve()
    output = tmp_path / "xp-smoke-evidence" / "cli_launch.txt"

    result = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(runner),
            "--target",
            "windows-xp-native-x86",
            "--release-tag",
            "v1.0.2",
            "--smoke-id",
            "cli_launch",
            "--evidence-file",
            str(output),
            "--proof-file",
            str(tmp_path / "missing-proof.txt"),
            "--host-label",
            "xp-x86-lab-01",
            "--evidence-run-id",
            "xp-x86-1-0-2-20260620t120000z",
            "--observed-at-utc",
            "2026-06-20T12:00:00Z",
            "--source-workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "--source-head-sha",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--source-run-attempt",
            "1",
            "--os-name",
            "Windows XP",
            "--os-architecture",
            "x86",
            "--os-service-pack",
            "SP3",
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "proof file is missing" in result.stderr
    assert not output.exists()
