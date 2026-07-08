from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="xp smoke runner is a Windows cmd script")


def _clean_github_actions_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("GITHUB_SHA", "GITHUB_RUN_ATTEMPT", "GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
        env.pop(key, None)
    env.update(overrides)
    return env


def _run_xp_smoke_runner(tmp_path: Path, **overrides: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    runner = Path("scripts/xp_smoke_runner.cmd").resolve()
    proof = tmp_path / "proof.txt"
    output = tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    proof.write_text("cli launch proof: ok\n", encoding="utf-8")
    values = {
        "target": "windows-xp-native-x86",
        "release_tag": "v1.0.2",
        "smoke_id": "cli_launch",
        "evidence_file": str(output),
        "proof_file": str(proof),
        "host_label": "xp-x86-lab-01",
        "evidence_run_id": "xp-x86-1-0-2-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "source_workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "source_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "source_run_attempt": "1",
        "os_name": "Windows XP",
        "os_architecture": "x86",
        "os_service_pack": "SP3",
    }
    values.update(overrides)

    result = subprocess.run(
        [
            "cmd.exe",
            "/c",
            str(runner),
            "--target",
            values["target"],
            "--release-tag",
            values["release_tag"],
            "--smoke-id",
            values["smoke_id"],
            "--evidence-file",
            values["evidence_file"],
            "--proof-file",
            values["proof_file"],
            "--host-label",
            values["host_label"],
            "--evidence-run-id",
            values["evidence_run_id"],
            "--observed-at-utc",
            values["observed_at_utc"],
            "--source-workflow-run-url",
            values["source_workflow_run_url"],
            "--source-head-sha",
            values["source_head_sha"],
            "--source-run-attempt",
            values["source_run_attempt"],
            "--os-name",
            values["os_name"],
            "--os-architecture",
            values["os_architecture"],
            "--os-service-pack",
            values["os_service_pack"],
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        env=_clean_github_actions_env(),
    )
    return result, output


def test_xp_smoke_runner_writes_bound_evidence_from_proof_file(tmp_path: Path) -> None:
    runner = Path("scripts/xp_smoke_runner.cmd").resolve()
    proof = tmp_path / "proof.txt"
    output = tmp_path / "xp-smoke-evidence" / "modern_defaults_unchanged.txt"
    proof.write_text(
        "modern TLS minimum: TLS 1.2\n"
        "modern TLS preferred: TLS 1.3\n"
        "modern defaults unchanged: true\n"
        "weak crypto global default: false\n"
        "security update channel: vendor-security-updates-2026-06\n"
        "CVE review reference: vendor-cve-advisory-review-2026-06\n",
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
            "--security-update-channel",
            "vendor-security-updates-2026-06",
            "--cve-review-reference",
            "vendor-cve-advisory-review-2026-06",
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
        env=_clean_github_actions_env(),
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
    assert "security update channel: vendor-security-updates-2026-06" in text
    assert "CVE review reference: vendor-cve-advisory-review-2026-06" in text


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
        env=_clean_github_actions_env(),
    )

    assert result.returncode == 1
    assert "proof file is missing" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_github_repository_mismatch(tmp_path: Path) -> None:
    runner = Path("scripts/xp_smoke_runner.cmd").resolve()
    output = tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    env = _clean_github_actions_env(GITHUB_REPOSITORY="other/remote-ops-workspace")

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
            str(tmp_path / "proof.txt"),
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
        env=env,
    )

    assert result.returncode == 2
    assert "GITHUB_REPOSITORY other/remote-ops-workspace must match --source-workflow-run-url" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_nonnumeric_source_run_id(tmp_path: Path) -> None:
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
            str(tmp_path / "proof.txt"),
            "--host-label",
            "xp-x86-lab-01",
            "--evidence-run-id",
            "xp-x86-1-0-2-20260620t120000z",
            "--observed-at-utc",
            "2026-06-20T12:00:00Z",
            "--source-workflow-run-url",
            "https://github.com/example/remote-ops-workspace/actions/runs/not-a-run",
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
        env=_clean_github_actions_env(),
    )

    assert result.returncode == 2
    assert "--source-workflow-run-url must end with a numeric GitHub Actions run id" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_noncanonical_source_workflow_run_url(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(
        tmp_path,
        source_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345/",
    )

    assert result.returncode == 2
    assert "--source-workflow-run-url must be canonical without trailing slash" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_invalid_source_head_sha(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(
        tmp_path,
        source_head_sha="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    assert result.returncode == 2
    assert "--source-head-sha must be a lowercase 40-character Git commit SHA" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_invalid_source_run_attempt(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(tmp_path, source_run_attempt="0")

    assert result.returncode == 2
    assert "--source-run-attempt must be a positive integer" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_missing_security_provenance_flags(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(
        tmp_path,
        smoke_id="modern_defaults_unchanged",
        evidence_file=str(tmp_path / "xp-smoke-evidence" / "modern_defaults_unchanged.txt"),
    )

    assert result.returncode == 2
    assert "--security-update-channel is required for XP security smoke evidence" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_invalid_observed_at_utc(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(tmp_path, observed_at_utc="2026-06-20 12:00:00Z")

    assert result.returncode == 2
    assert "--observed-at-utc must use YYYY-MM-DDTHH:MM:SSZ" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_wrong_target_host_label_prefix(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(
        tmp_path,
        target="windows-xp-native-x64",
        host_label="xp-x86-lab-01",
        evidence_run_id="xp-x64-1-0-2-20260620t120000z",
        os_architecture="x64",
        os_service_pack="SP2",
    )

    assert result.returncode == 2
    assert "--host-label must use target-scoped prefix xp-x64-" in result.stderr
    assert not output.exists()


def test_xp_smoke_runner_rejects_wrong_target_evidence_run_id_prefix(tmp_path: Path) -> None:
    result, output = _run_xp_smoke_runner(
        tmp_path,
        target="windows-xp-native-x64",
        host_label="xp-x64-lab-01",
        evidence_run_id="xp-x86-1-0-2-20260620t120000z",
        os_architecture="x64",
        os_service_pack="SP2",
    )

    assert result.returncode == 2
    assert "--evidence-run-id must use target-scoped prefix xp-x64-" in result.stderr
    assert not output.exists()
