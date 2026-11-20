from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_production_readiness as gate

SUCCESS = "production readiness: 100/100 gates passed"
ORIGINS = "https://updates.example.org https://downloads.example.org"


@pytest.fixture
def tagged_checkout(tmp_path, monkeypatch):
    root = tmp_path / "tagged checkout"
    root.mkdir()
    git(root, "init", "--quiet")
    git(root, "commit", "--quiet", "--allow-empty", "-m", "Candidate")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "tag", "--annotate", "v1.0.28", "-m", "Candidate")
    inputs = {
        "RELEASE_REPOSITORY": "example/project",
        "RELEASE_TAG": "v1.0.28",
        "RELEASE_SHA": sha,
        "RELEASE_MOBAXTERM_REGISTRY_COMMIT": "b" * 40,
        "RELEASE_PROFESSIONAL_UPDATE_ORIGINS": ORIGINS,
    }
    for key in gate.DIRECTORIES:
        directory = Path(f"Evidence & records/{key}")
        (root / directory).mkdir(parents=True)
        inputs[key] = str(directory)
    for key in gate.FILES:
        path = Path(f"Evidence & records/{key}.json")
        (root / path).write_text("{}\n", encoding="utf-8")
        inputs[key] = str(path)
    for key, value in inputs.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(gate, "ROOT", root)
    return root, inputs


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", "user.name=Readiness tests", "-c", "user.email=test@example.org", *args],
        cwd=root,
        encoding="utf-8",
    ).strip()


def expected_commands(root, values):
    tag = values["RELEASE_TAG"]
    sha = values["RELEASE_SHA"]
    repository = values["RELEASE_REPOSITORY"]
    assets = str(root / values["RELEASE_ASSETS_DIR"])
    platform = str(root / values["RELEASE_PLATFORM_EVIDENCE_REGISTRY"])
    return [
        ["check_repository_cleanup.py", "--require-clean"],
        ["check_release_version.py", "--release-tag", tag],
        ["check_release_maturity.py", "--release-tag", tag],
        ["verify.py", "--production-quality", "--release-tag", tag],
        ["check_python315_ci_evidence.py", "--repository", repository, "--branch", "main", "--sha", sha],
        [
            "check_platform_verified_evidence.py", "--registry", platform,
            "--require-goal-targets", "--require-review-bundles", "--release-tag", tag,
        ],
        [
            "check_release_publish_assets.py", "--assets-dir", assets, "--tag", tag,
            "--repository", repository, "--evidence-registry", platform, "--require-platform-goal-targets",
            "--native-release-channel", "production-signed",
        ],
        [
            "check_release_license_compliance.py", "--assets-dir", assets, "--tag", tag,
            "--repository", repository, "--sha", sha,
            "--evidence", str(root / values["RELEASE_LICENSE_EVIDENCE"]),
            "--signature", str(root / values["RELEASE_LICENSE_SIGNATURE"]),
            "--evidence-root", str(root / values["RELEASE_LICENSE_EVIDENCE_ROOT"]),
            "--candidate-inventory", str(root / values["RELEASE_CANDIDATE_INVENTORY"]),
            "--candidate-qualification-archives", str(root / values["RELEASE_CANDIDATE_QUALIFICATION_ARCHIVES"]),
            "--protected-platform-registry", platform,
            "--platform-source-archives", str(root / values["RELEASE_PLATFORM_SOURCE_ARCHIVES"]),
            "--tag-governance-attestation", str(root / values["RELEASE_TAG_GOVERNANCE_ATTESTATION"]),
            "--tag-governance-signature", str(root / values["RELEASE_TAG_GOVERNANCE_SIGNATURE"]),
            "--verify-published-release",
        ],
        [
            "check_release_mobaxterm_parity.py", "--repository", repository, "--tag", tag, "--sha", sha,
            "--registry-commit", values["RELEASE_MOBAXTERM_REGISTRY_COMMIT"],
            "--assets-dir", assets, "--evidence-root", str(root / values["RELEASE_MOBAXTERM_EVIDENCE_ROOT"]),
        ],
        ["check_repository_governance.py", "--repository", repository, "--branch", "main", "--sha", sha,
         "--release-tag", tag],
        ["check_published_release_notes.py", "--repository", repository, "--tag", tag, "--channel", "production-signed"],
        ["check_repository_cleanup.py", "--require-clean"],
    ]


def test_strict_gate_passes_inputs_as_arguments_and_rechecks_exact_git_identity(
    tagged_checkout, monkeypatch, capsys,
):
    root, values = tagged_checkout
    real_run = subprocess.run
    observed = []

    def run(args, **kwargs):
        assert kwargs["cwd"] == root
        assert not kwargs.get("shell", False)
        if args[0] == "git":
            assert args[1:4] == ["rev-parse", "--verify", "--end-of-options"]
            observed.append(args[4])
            return real_run(args, **kwargs)
        assert args[0] == sys.executable
        assert args[1].startswith("scripts/")
        assert kwargs["check"] is True
        observed.append([Path(args[1]).name, *args[2:]])

    monkeypatch.setattr(gate.subprocess, "run", run)
    assert gate.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == SUCCESS
    assert captured.err == ""
    identity = ["refs/tags/v1.0.28^{commit}", "HEAD^{commit}"]
    commands = expected_commands(root, values)
    assert observed == [*identity, *commands[:-1], *identity, commands[-1]]


def test_preflight_reports_missing_inputs_together_without_running_commands(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    required = (
        set(gate.IDENTITIES) | set(gate.DIRECTORIES) | set(gate.FILES) | {"RELEASE_PROFESSIONAL_UPDATE_ORIGINS"}
    )
    for key in required:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(gate.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("ran a command"))
    assert gate.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert all(key in captured.err for key in required)
    assert len(captured.err.splitlines()) == len(required)


def test_preflight_refuses_empty_evidence_and_uses_default_assets_directory(tagged_checkout):
    root, values = tagged_checkout
    default = root / "release-assets"
    default.mkdir()
    values.pop("RELEASE_ASSETS_DIR")
    (root / values["RELEASE_LICENSE_EVIDENCE"]).write_bytes(b"")
    inputs, errors = gate.read_inputs(values)
    assert inputs["RELEASE_ASSETS_DIR"] == str(default)
    assert len(errors) == 1 and errors[0].startswith("RELEASE_LICENSE_EVIDENCE ")


@pytest.mark.parametrize("move_at_end", [False, True])
@pytest.mark.parametrize("changed_ref", ["local release tag", "checkout HEAD"])
def test_tag_or_head_drift_refuses_certification(
    tagged_checkout, monkeypatch, capsys, move_at_end, changed_ref,
):
    root, _ = tagged_checkout
    commands = []

    def drift():
        if changed_ref == "local release tag":
            git(root, "tag", "-d", "v1.0.28")
        else:
            git(root, "commit", "--quiet", "--allow-empty", "-m", "Different checkout")

    def run(command):
        commands.append(command)
        if move_at_end and command[0] == "check_published_release_notes.py":
            drift()

    monkeypatch.setattr(gate, "run_gate", run)
    if not move_at_end:
        drift()
    assert gate.main([]) == 2
    captured = capsys.readouterr()
    assert SUCCESS not in captured.out
    assert changed_ref in captured.err
    if move_at_end:
        assert commands[-1][0] == "check_published_release_notes.py"
    else:
        assert commands == []


@pytest.mark.parametrize("failed_at", ["check_release_license_compliance.py", "final cleanup"])
def test_failed_gate_keeps_its_exit_status_and_never_prints_success(
    tagged_checkout, monkeypatch, capsys, failed_at,
):
    root, inputs = tagged_checkout
    expected = expected_commands(root, inputs)
    observed = []

    def run(command):
        observed.append(command)
        if command[0] == failed_at or (failed_at == "final cleanup" and len(observed) == len(expected)):
            raise subprocess.CalledProcessError(3, [sys.executable, f"scripts/{command[0]}", *command[1:]])

    monkeypatch.setattr(gate, "run_gate", run)
    assert gate.main([]) == 3
    captured = capsys.readouterr()
    assert SUCCESS not in captured.out
    assert "failed with exit code 3" in captured.err
    assert observed == expected[:len(observed)]
    if failed_at == "final cleanup":
        assert observed == expected
    else:
        assert observed[-1][0] == failed_at


def test_make_target_delegates_and_exports_all_inputs():
    makefile = Path("Makefile").read_text(encoding="utf-8")
    target = makefile.split("production-readiness:\n", 1)[1].split("\nrun-web:", 1)[0]
    assert target.strip() == "python scripts/check_production_readiness.py"
    exports = {
        word
        for line in makefile.splitlines() if line.startswith("export ")
        for word in line.partition("?=")[0].split()[1:]
    }
    assert exports == (
        set(gate.IDENTITIES) | set(gate.DIRECTORIES) | set(gate.FILES) | {"RELEASE_PROFESSIONAL_UPDATE_ORIGINS"}
    )
