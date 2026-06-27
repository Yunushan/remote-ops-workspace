from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_builder_identity_context_accepts_release_run_and_source_sha(monkeypatch) -> None:
    builder = _load_builder()
    _clear_github_env(monkeypatch)
    monkeypatch.setattr(builder, "git_head_sha", lambda: "a" * 40)
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: "")

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert errors == []


def test_builder_identity_context_accepts_github_workflow_provenance(monkeypatch) -> None:
    builder = _load_builder()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/remote-ops-workspace")
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@refs/heads/main",
    )
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "a" * 40)

    errors = builder.check_github_actions_context(
        "linux-i386",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert errors == []


def test_builder_identity_context_requires_lowercase_source_sha() -> None:
    builder = _load_builder()

    errors = builder.check_builder_identity_context(
        "linux-armhf",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "A" * 40,
    )

    assert "linux-armhf builder identity --source-head-sha must be a 40-character lowercase Git SHA" in errors


def test_builder_identity_context_requires_observed_git_head(monkeypatch) -> None:
    builder = _load_builder()
    _clear_github_env(monkeypatch)
    monkeypatch.setattr(builder, "git_head_sha", lambda: "")
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: "")

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert "linux-i386 builder identity requires git rev-parse HEAD for source head binding" in errors


def test_builder_identity_context_rejects_observed_git_head_mismatch(monkeypatch) -> None:
    builder = _load_builder()
    _clear_github_env(monkeypatch)
    monkeypatch.setattr(builder, "git_head_sha", lambda: "b" * 40)
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: "")

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert (
        f"linux-i386 builder identity observed git HEAD {'b' * 40} "
        f"must match --source-head-sha {'a' * 40}"
    ) in errors


def test_builder_identity_context_requires_git_status_for_clean_checkout(monkeypatch) -> None:
    builder = _load_builder()
    _clear_github_env(monkeypatch)
    monkeypatch.setattr(builder, "git_head_sha", lambda: "a" * 40)
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: None)

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert "linux-i386 builder identity requires git status --porcelain for clean checkout proof" in errors


def test_builder_identity_context_rejects_dirty_git_worktree(monkeypatch) -> None:
    builder = _load_builder()
    _clear_github_env(monkeypatch)
    monkeypatch.setattr(builder, "git_head_sha", lambda: "a" * 40)
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: "M scripts/check_extended_platform_builder.py")

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert "linux-i386 builder identity requires a clean git worktree before native build" in errors


def test_builder_identity_context_rejects_github_actions_env_mismatch(monkeypatch) -> None:
    builder = _load_builder()
    monkeypatch.setattr(builder, "git_head_sha", lambda: "a" * 40)
    monkeypatch.setattr(builder, "git_status_porcelain", lambda: "")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_RUN_ID", "54321")
    monkeypatch.setenv("GITHUB_REPOSITORY", "other/remote-ops-workspace")
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "other/remote-ops-workspace/.github/workflows/ci.yml@refs/heads/main",
    )
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "b" * 40)

    errors = builder.check_builder_identity_context(
        "linux-i386",
        "v1.0.2",
        "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        1,
        "a" * 40,
    )

    assert f"linux-i386 GITHUB_SHA {'b' * 40} must match --source-head-sha {'a' * 40}" in errors
    assert "linux-i386 GITHUB_RUN_ATTEMPT 2 must match --workflow-run-attempt 1" in errors
    assert (
        "linux-i386 GITHUB_RUN_ID 54321 must match --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors
    assert (
        "linux-i386 GITHUB_REPOSITORY other/remote-ops-workspace must match --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors
    assert (
        "linux-i386 GITHUB_WORKFLOW_REF "
        "other/remote-ops-workspace/.github/workflows/ci.yml@refs/heads/main must point at "
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@<ref>"
    ) in errors
    assert f"linux-i386 GITHUB_WORKFLOW_SHA {'b' * 40} must match --source-head-sha {'a' * 40}" in errors


def test_builder_identity_records_source_head_sha(monkeypatch) -> None:
    builder = _load_builder()
    monkeypatch.setattr(builder, "git_head_sha", lambda: "a" * 40)
    monkeypatch.setattr(builder, "git_worktree_clean", lambda: True)
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@refs/heads/main",
    )
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "a" * 40)

    identity = builder.builder_identity(
        "linux-i386",
        release_tag="v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        workflow_run_attempt=1,
        source_head_sha="a" * 40,
    )

    assert identity["workflow_run_attempt"] == 1
    assert identity["workflow_ref"] == (
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@refs/heads/main"
    )
    assert identity["workflow_sha"] == "a" * 40
    assert identity["host_identity"]["workflow_run_attempt"] == 1
    assert identity["source_head_sha"] == "a" * 40
    assert identity["observed_git_head_sha"] == "a" * 40
    assert identity["git_worktree_clean"] is True


def test_builder_identity_output_path_requires_target_scoped_name(tmp_path: Path) -> None:
    builder = _load_builder()
    output = tmp_path / "builder.json"

    errors = builder.check_builder_identity_output_path("linux-i386", output)

    assert (
        "linux-i386 builder identity output file name must be "
        "builder-identity-linux-i386.json, got 'builder.json'"
    ) in errors


def test_builder_security_patch_evidence_rejects_placeholder_provenance(monkeypatch) -> None:
    builder = _load_builder()
    evidence = builder.security_patch_evidence()
    evidence["security_update_channel"] = "test-security-update-channel"
    evidence["cve_review_reference"] = "<replace-with-real-cve-review>"
    monkeypatch.setattr(builder, "security_patch_evidence", lambda: evidence)

    errors = builder.check_security_patch_evidence("linux-i386")

    assert (
        "linux-i386 builder security update channel evidence must name concrete non-placeholder provenance"
        in errors
    )
    assert "linux-i386 builder CVE review reference evidence must name concrete non-placeholder provenance" in errors


def _load_builder():
    path = Path("scripts/check_extended_platform_builder.py")
    spec = importlib.util.spec_from_file_location("check_extended_platform_builder", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _clear_github_env(monkeypatch) -> None:
    for name in (
        "GITHUB_ACTIONS",
        "GITHUB_SHA",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_REPOSITORY",
        "GITHUB_WORKFLOW_REF",
        "GITHUB_WORKFLOW_SHA",
    ):
        monkeypatch.delenv(name, raising=False)
