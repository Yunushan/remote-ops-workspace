from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

XP_SOURCE_WORKFLOW_RUN_URL = "https://github.com/example/remote-ops-workspace/actions/runs/54321"
XP_SOURCE_HEAD_SHA = "a" * 40
XP_SOURCE_RUN_ATTEMPT = 1


def test_platform_goal_local_evidence_rejects_missing_root(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path / "missing",
        release_tag="v1.0.2",
    )

    assert errors == [f"local evidence root missing: {tmp_path / 'missing'}"]


def test_platform_goal_local_evidence_rejects_symlinked_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
    )

    assert errors == [f"local evidence root must not be a symlink: {tmp_path}"]


def test_platform_goal_local_evidence_rejects_file_shaped_root(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    root = tmp_path / "platform-evidence.zip"

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag="v1.0.2",
    )

    assert errors == [f"local evidence root must be a directory path, got {root.as_posix()!r}"]
    assert not root.exists()


def test_platform_goal_local_evidence_requires_strict_artifacts_for_full_goal(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
        strict_artifacts=False,
    )

    assert errors == [checker.FULL_GOAL_STRICT_ARTIFACTS_ERROR]


def test_platform_goal_local_evidence_report_tracks_partial_target_failure() -> None:
    checker = _load_local_evidence_checker()

    report = checker.platform_goal_local_evidence_report(
        targets=("linux-i386", "linux-armhf"),
        errors=[
            "artifact directory missing: linux-i386\\v1.0.2\\artifacts",
            "linux-i386 native smoke evidence missing: staged/linux-i386/v1.0.2/native-smoke-linux-i386.log",
        ],
    )

    assert report["metric"] == "protected_platform_goal_local_evidence_preflight"
    assert report["passed_target_count"] == 1
    assert report["failed_target_count"] == 1
    assert report["current_percent"] == 50.0
    assert report["complete"] is False
    assert report["global_errors"] == []
    assert report["passed_targets"] == ["linux-armhf"]
    assert report["failed_targets"] == ["linux-i386"]
    assert report["target_results"][0]["status"] == "failed"
    assert len(report["target_results"][0]["errors"]) == 2
    assert report["target_results"][1]["status"] == "passed"


def test_platform_goal_local_evidence_report_blocks_targets_on_global_failure() -> None:
    checker = _load_local_evidence_checker()

    report = checker.platform_goal_local_evidence_report(
        targets=("linux-i386", "linux-armhf"),
        errors=["release_tag must look like vX.Y.Z: latest"],
    )

    assert report["passed_target_count"] == 0
    assert report["failed_target_count"] == 2
    assert report["current_percent"] == 0.0
    assert report["global_errors"] == ["release_tag must look like vX.Y.Z: latest"]
    assert report["target_results"][0]["status"] == "blocked-by-global-error"
    assert report["target_results"][1]["status"] == "blocked-by-global-error"


def test_platform_goal_local_evidence_rejects_symlinked_root_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    linked_parent = tmp_path / "linked-staging"
    root = linked_parent / "evidence"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag="v1.0.2",
    )

    assert errors == [
        f"local evidence root path must not contain symlinked directories: {linked_parent}"
    ]


def test_platform_goal_local_evidence_accepts_linux_i386_staged_proof(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    workflow_run_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    source_head_sha = "a" * 40
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    builder = target_root / f"builder-identity-{target}.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url=workflow_run_url,
        source_head_sha=source_head_sha,
    )
    smoke = target_root / f"native-smoke-{target}.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url=workflow_run_url,
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
    )

    assert errors == []


def test_platform_goal_local_evidence_rejects_symlinked_linux_target_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    target = "linux-i386"
    tag = "v1.0.2"
    target_dir = tmp_path / target
    target_root = target_dir / tag

    def fake_is_symlink(self: Path) -> bool:
        return self in {target_dir, target_root}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        linux_source_head_sha="a" * 40,
    )

    assert f"{target} local Linux evidence target directory must not be a symlink: {target_dir}" in errors
    assert f"{target} local Linux evidence release directory must not be a symlink: {target_root}" in errors


def test_platform_goal_local_evidence_rejects_symlinked_linux_proof_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    workflow_run_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    source_head_sha = "a" * 40
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    builder = target_root / f"builder-identity-{target}.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url=workflow_run_url,
        source_head_sha=source_head_sha,
    )
    smoke = target_root / f"native-smoke-{target}.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url=workflow_run_url,
    )
    symlink_names = {builder.name, smoke.name}

    def fake_is_symlink(self: Path) -> bool:
        return self.name in symlink_names

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
    )

    assert f"{target} builder identity evidence must not be a symlink: {builder}" in errors
    assert f"{target} native smoke evidence must not be a symlink: {smoke}" in errors


def test_platform_goal_local_evidence_rejects_symlinked_linux_proof_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    target = "linux-i386"
    tag = "v1.0.2"
    artifact_parent = tmp_path / "artifact-parent"
    artifacts = artifact_parent / "artifacts"
    artifacts.mkdir(parents=True)
    evidence_parent = tmp_path / "evidence-parent"
    evidence_parent.mkdir()
    builder = evidence_parent / f"builder-identity-{target}.json"
    builder.write_text("{}\n", encoding="utf-8")
    smoke = evidence_parent / f"native-smoke-{target}.log"
    smoke.write_text("linux smoke placeholder\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self in {artifact_parent, evidence_parent}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        linux_source_head_sha="a" * 40,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    assert f"{target} artifact directory path must not contain symlinked directories: {artifact_parent}" in errors
    assert f"{target} builder identity evidence path must not contain symlinked directories: {evidence_parent}" in errors
    assert f"{target} native smoke evidence path must not contain symlinked directories: {evidence_parent}" in errors


def test_platform_goal_local_evidence_rejects_linux_inputs_outside_root(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    root = tmp_path / "staged-root"
    root.mkdir()
    outside = tmp_path / "outside"
    artifacts = outside / "artifacts"
    artifacts.mkdir(parents=True)
    target = "linux-i386"
    builder = outside / f"builder-identity-{target}.json"
    smoke = outside / f"native-smoke-{target}.log"
    builder.write_text("{}\n", encoding="utf-8")
    smoke.write_text("linux smoke placeholder\n", encoding="utf-8")

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag="v1.0.2",
        targets=(target,),
        linux_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        linux_source_head_sha="a" * 40,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    assert f"{target} artifact directory must stay inside local evidence root: {artifacts}" in errors
    assert f"{target} builder identity evidence must stay inside local evidence root: {builder}" in errors
    assert f"{target} native smoke evidence must stay inside local evidence root: {smoke}" in errors


def test_platform_goal_local_evidence_rejects_file_shaped_linux_artifact_directory(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    target = "linux-i386"
    tag = "v1.0.2"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts.zip"

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        linux_source_head_sha="a" * 40,
        assets_dir=artifacts,
        linux_builder_evidence=target_root / f"builder-identity-{target}.json",
        linux_smoke_evidence=target_root / f"native-smoke-{target}.log",
    )

    assert errors == [
        f"{target} artifact directory must be a directory path, got {artifacts.as_posix()!r}"
    ]


def test_platform_goal_local_evidence_rejects_linux_inputs_outside_target_release_scope(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    root = tmp_path
    shared = root / "shared-linux-evidence"
    artifacts = shared / "artifacts"
    artifacts.mkdir(parents=True)
    target = "linux-i386"
    builder = shared / f"builder-identity-{target}.json"
    smoke = shared / f"native-smoke-{target}.log"
    builder.write_text("{}\n", encoding="utf-8")
    smoke.write_text("linux smoke placeholder\n", encoding="utf-8")

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag="v1.0.2",
        targets=(target,),
        linux_workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        linux_source_head_sha="a" * 40,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    expected_scope = f"{target}/v1.0.2"
    assert (
        f"{target} artifact directory must include target/release path segment "
        f"{expected_scope} under local evidence root: {artifacts}"
    ) in errors
    assert (
        f"{target} builder identity evidence must include target/release path segment "
        f"{expected_scope} under local evidence root: {builder}"
    ) in errors
    assert (
        f"{target} native smoke evidence must include target/release path segment "
        f"{expected_scope} under local evidence root: {smoke}"
    ) in errors


def test_platform_goal_local_evidence_accepts_linux_explicit_target_release_scoped_paths(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    workflow_run_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    source_head_sha = "a" * 40
    target_root = tmp_path / target / tag
    artifacts = target_root / "release" / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence_dir = target_root / "proof"
    evidence_dir.mkdir()
    builder = evidence_dir / f"builder-identity-{target}.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url=workflow_run_url,
        source_head_sha=source_head_sha,
    )
    smoke = evidence_dir / f"native-smoke-{target}.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url=workflow_run_url,
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    assert errors == []


def test_platform_goal_local_evidence_accepts_linux_workspace_prefixed_release_paths(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    workflow_run_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    source_head_sha = "a" * 40
    artifacts = tmp_path / "staged" / target / tag / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence_dir = tmp_path / "evidence" / target / tag
    evidence_dir.mkdir(parents=True)
    builder = evidence_dir / f"builder-identity-{target}.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url=workflow_run_url,
        source_head_sha=source_head_sha,
    )
    smoke = evidence_dir / f"native-smoke-{target}.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url=workflow_run_url,
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    assert errors == []


def test_platform_goal_local_evidence_accepts_linux_targets_with_inferred_run_bindings(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    source_head_sha = "a" * 40
    run_urls = {
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "linux-armhf": "https://github.com/example/remote-ops-workspace/actions/runs/67890",
    }
    for target, workflow_run_url in run_urls.items():
        target_root = tmp_path / target / tag
        artifacts = target_root / "artifacts"
        artifacts.mkdir(parents=True)
        names = fixtures._required_names(artifact_checker, target, tag)
        fixtures._write_artifact_set(artifacts, names)
        builder = target_root / f"builder-identity-{target}.json"
        fixtures._write_builder_evidence(
            builder,
            target,
            release_tag=tag,
            workflow_run_url=workflow_run_url,
            source_head_sha=source_head_sha,
        )
        smoke = target_root / f"native-smoke-{target}.log"
        fixtures._write_linux_smoke_evidence(
            smoke,
            target,
            fixtures._smoke_artifact_hashes(artifacts, names),
            workflow_run_url=workflow_run_url,
            source_head_sha=source_head_sha,
        )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=("linux-i386", "linux-armhf"),
    )

    assert errors == []


def test_platform_goal_local_evidence_rejects_linux_source_head_drift(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    source_heads = {
        "linux-i386": "a" * 40,
        "linux-armhf": "b" * 40,
    }
    run_urls = {
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "linux-armhf": "https://github.com/example/remote-ops-workspace/actions/runs/67890",
    }
    for target, workflow_run_url in run_urls.items():
        target_root = tmp_path / target / tag
        artifacts = target_root / "artifacts"
        artifacts.mkdir(parents=True)
        names = fixtures._required_names(artifact_checker, target, tag)
        fixtures._write_artifact_set(artifacts, names)
        builder = target_root / f"builder-identity-{target}.json"
        fixtures._write_builder_evidence(
            builder,
            target,
            release_tag=tag,
            workflow_run_url=workflow_run_url,
            source_head_sha=source_heads[target],
        )
        smoke = target_root / f"native-smoke-{target}.log"
        fixtures._write_linux_smoke_evidence(
            smoke,
            target,
            fixtures._smoke_artifact_hashes(artifacts, names),
            workflow_run_url=workflow_run_url,
            source_head_sha=source_heads[target],
        )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=("linux-i386", "linux-armhf"),
    )

    assert (
        "local protected platform evidence must use one release source head SHA before promotion"
        in errors[0]
    )
    assert "'linux-i386': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'" in errors[0]
    assert "'linux-armhf': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'" in errors[0]


def test_platform_goal_local_evidence_rejects_misnamed_linux_proof_inputs(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    workflow_run_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    source_head_sha = "a" * 40
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence_dir = target_root / "proof"
    evidence_dir.mkdir()
    builder = evidence_dir / "builder-identity-linux-armhf.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url=workflow_run_url,
        source_head_sha=source_head_sha,
    )
    smoke = evidence_dir / "native-smoke-linux-armhf.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url=workflow_run_url,
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
        assets_dir=artifacts,
        linux_builder_evidence=builder,
        linux_smoke_evidence=smoke,
    )

    assert (
        f"{target} builder identity evidence file name must be "
        f"builder-identity-{target}.json: {builder}"
    ) in errors
    assert (
        f"{target} native smoke evidence file name must be "
        f"native-smoke-{target}.log: {smoke}"
    ) in errors


def test_platform_goal_local_evidence_rejects_invalid_inferred_linux_run_bindings(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    builder = target_root / f"builder-identity-{target}.json"
    fixtures._write_builder_evidence(
        builder,
        target,
        release_tag=tag,
        workflow_run_url="https://example.invalid/not-actions",
        source_head_sha="A" * 40,
    )
    smoke = target_root / f"native-smoke-{target}.log"
    fixtures._write_linux_smoke_evidence(
        smoke,
        target,
        fixtures._smoke_artifact_hashes(artifacts, names),
        workflow_run_url="https://example.invalid/not-actions",
        source_head_sha="A" * 40,
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
    )

    assert f"{target} builder_identity.workflow_run_url must be a GitHub Actions run URL" in errors
    assert (
        f"{target} builder_identity.source_head_sha must be a 40-character lowercase Git SHA"
    ) in errors


def test_platform_goal_local_evidence_requires_linux_run_bindings(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    (tmp_path / "linux-i386").mkdir()

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )

    assert "linux-i386 --linux-workflow-run-url is required for local Linux evidence preflight" in errors
    assert "linux-i386 --linux-source-head-sha is required for local Linux evidence preflight" in errors


def test_platform_goal_local_evidence_rejects_invalid_linux_run_bindings(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    target = "linux-i386"
    (tmp_path / target).mkdir()

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
        targets=(target,),
        linux_workflow_run_url="https://example.invalid/not-actions",
        linux_source_head_sha="A" * 40,
    )

    assert f"{target} --linux-workflow-run-url must be a GitHub Actions run URL" in errors
    assert f"{target} --linux-source-head-sha must be a 40-character lowercase Git SHA" in errors


def test_platform_goal_local_evidence_requires_xp_source_bindings(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    target = "windows-xp-native-x86"
    (tmp_path / target / "v1.0.2").mkdir(parents=True)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
        targets=(target,),
    )

    assert f"{target} --xp-source-workflow-run-url is required for local XP evidence preflight" in errors
    assert f"{target} --xp-source-head-sha is required for local XP evidence preflight" in errors


def test_platform_goal_local_evidence_rejects_invalid_xp_source_bindings(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    target = "windows-xp-native-x64"
    (tmp_path / target / "v1.0.2").mkdir(parents=True)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag="v1.0.2",
        targets=(target,),
        xp_source_workflow_run_url="https://example.invalid/not-actions",
        xp_source_head_sha="A" * 40,
    )

    assert f"{target} --xp-source-workflow-run-url must be a GitHub Actions run URL" in errors
    assert f"{target} --xp-source-head-sha must be a 40-character lowercase Git SHA" in errors


def test_platform_goal_local_evidence_accepts_xp_x86_staged_proof(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"{target}/{tag}/artifacts",
    )
    fixtures._attach_smoke_evidence_files(target_root, evidence)
    (target_root / "xp-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        xp_source_workflow_run_url=XP_SOURCE_WORKFLOW_RUN_URL,
        xp_source_head_sha=XP_SOURCE_HEAD_SHA,
        xp_source_run_attempt=XP_SOURCE_RUN_ATTEMPT,
    )

    assert errors == []


def test_platform_goal_local_evidence_accepts_xp_targets_with_inferred_source_bindings(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    staged_sources = {
        "windows-xp-native-x86": {
            "arch": "x86",
            "service_pack": "SP3",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/11111",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        },
        "windows-xp-native-x64": {
            "arch": "x64",
            "service_pack": "SP2",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/22222",
            "head_sha": "a" * 40,
            "run_attempt": 2,
        },
    }
    for target, source in staged_sources.items():
        target_root = tmp_path / target / tag
        artifacts = target_root / "artifacts"
        artifacts.mkdir(parents=True)
        names = fixtures._required_names(artifact_checker, target, tag)
        fixtures._write_artifact_set(artifacts, names)
        evidence = fixtures._valid_xp_evidence(
            target,
            str(source["arch"]),
            str(source["service_pack"]),
            tag,
            names,
        )
        evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
            f"native-dist/windows-xp/{target}/{tag}",
            f"{target}/{tag}/artifacts",
        )
        _set_xp_release_source(
            evidence,
            workflow_run_url=str(source["workflow_run_url"]),
            head_sha=str(source["head_sha"]),
            run_attempt=int(source["run_attempt"]),
        )
        fixtures._attach_smoke_evidence_files(target_root, evidence)
        (target_root / "xp-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=tuple(staged_sources),
    )

    assert errors == []


def test_platform_goal_local_evidence_rejects_xp_source_head_drift(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    staged_sources = {
        "windows-xp-native-x86": {
            "arch": "x86",
            "service_pack": "SP3",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/11111",
            "head_sha": "a" * 40,
            "run_attempt": 1,
        },
        "windows-xp-native-x64": {
            "arch": "x64",
            "service_pack": "SP2",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/22222",
            "head_sha": "b" * 40,
            "run_attempt": 2,
        },
    }
    for target, source in staged_sources.items():
        target_root = tmp_path / target / tag
        artifacts = target_root / "artifacts"
        artifacts.mkdir(parents=True)
        names = fixtures._required_names(artifact_checker, target, tag)
        fixtures._write_artifact_set(artifacts, names)
        evidence = fixtures._valid_xp_evidence(
            target,
            str(source["arch"]),
            str(source["service_pack"]),
            tag,
            names,
        )
        evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
            f"native-dist/windows-xp/{target}/{tag}",
            f"{target}/{tag}/artifacts",
        )
        _set_xp_release_source(
            evidence,
            workflow_run_url=str(source["workflow_run_url"]),
            head_sha=str(source["head_sha"]),
            run_attempt=int(source["run_attempt"]),
        )
        fixtures._attach_smoke_evidence_files(target_root, evidence)
        (target_root / "xp-evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=tuple(staged_sources),
    )

    assert (
        "local protected platform evidence must use one release source head SHA before promotion"
        in errors[0]
    )
    assert "'windows-xp-native-x86': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'" in errors[0]
    assert "'windows-xp-native-x64': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'" in errors[0]


def test_platform_goal_local_evidence_rejects_invalid_inferred_xp_source_bindings(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence = {
        "release_source": {
            "workflow_run_url": "https://example.invalid/not-actions",
            "head_sha": "A" * 40,
            "run_attempt": "first",
        }
    }
    (target_root / "xp-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
    )

    assert f"{target} XP evidence release_source.workflow_run_url must be a GitHub Actions run URL" in errors
    assert f"{target} XP evidence release_source.head_sha must be a 40-character lowercase Git SHA" in errors
    assert f"{target} XP evidence release_source.run_attempt must be a positive integer" in errors


def test_platform_goal_local_evidence_rejects_explicit_xp_source_binding_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"{target}/{tag}/artifacts",
    )
    fixtures._attach_smoke_evidence_files(target_root, evidence)
    (target_root / "xp-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )
    expected_url = "https://github.com/example/remote-ops-workspace/actions/runs/99999"

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        xp_source_workflow_run_url=expected_url,
        xp_source_head_sha="b" * 40,
        xp_source_run_attempt=2,
    )

    assert (
        f"{target} XP evidence release_source.workflow_run_url must match "
        f"--xp-source-workflow-run-url {expected_url}, got 'https://github.com/example/remote-ops-workspace/actions/runs/54321'"
    ) in errors
    assert (
        f"{target} XP evidence release_source.head_sha must match "
        f"--xp-source-head-sha {'b' * 40}, got '{'a' * 40}'"
    ) in errors
    assert (
        f"{target} XP evidence release_source.run_attempt must match "
        "--xp-source-run-attempt 2, got 1"
    ) in errors


def test_platform_goal_local_evidence_rejects_symlinked_xp_target_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    target = "windows-xp-native-x86"
    tag = "v1.0.2"
    target_dir = tmp_path / target
    target_root = target_dir / tag

    def fake_is_symlink(self: Path) -> bool:
        return self in {target_dir, target_root}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
    )

    assert f"{target} XP evidence target directory must not be a symlink: {target_dir}" in errors
    assert f"{target} XP evidence release directory must not be a symlink: {target_root}" in errors


def test_platform_goal_local_evidence_rejects_symlinked_xp_proof_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"{target}/{tag}/artifacts",
    )
    fixtures._attach_smoke_evidence_files(target_root, evidence)
    evidence_file = target_root / "xp-evidence.json"
    evidence_file.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    evidence_dir = tmp_path / "explicit-xp-evidence-dir"
    evidence_dir.mkdir()

    def fake_is_symlink(self: Path) -> bool:
        return self in {evidence_file, evidence_dir}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        xp_evidence_dir=evidence_dir,
    )

    assert f"{target} XP evidence file must not be a symlink: {evidence_file}" in errors
    assert f"{target} XP evidence directory must not be a symlink: {evidence_dir}" in errors


def test_platform_goal_local_evidence_rejects_symlinked_xp_proof_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_local_evidence_checker()
    target = "windows-xp-native-x86"
    tag = "v1.0.2"
    artifact_parent = tmp_path / "artifact-parent"
    artifacts = artifact_parent / "artifacts"
    artifacts.mkdir(parents=True)
    evidence_parent = tmp_path / "evidence-parent"
    evidence_dir = evidence_parent / "xp-evidence"
    evidence_dir.mkdir(parents=True)
    evidence_file = evidence_dir / "xp-evidence.json"
    evidence_file.write_text("{}\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self in {artifact_parent, evidence_parent}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=evidence_file,
        xp_evidence_dir=evidence_dir,
    )

    assert f"{target} artifact directory path must not contain symlinked directories: {artifact_parent}" in errors
    assert f"{target} XP evidence file path must not contain symlinked directories: {evidence_parent}" in errors
    assert f"{target} XP evidence directory path must not contain symlinked directories: {evidence_parent}" in errors


def test_platform_goal_local_evidence_rejects_xp_inputs_outside_root(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    root = tmp_path / "staged-root"
    root.mkdir()
    outside = tmp_path / "outside"
    artifacts = outside / "artifacts"
    evidence_dir = outside / "xp-evidence"
    evidence_dir.mkdir(parents=True)
    evidence_file = evidence_dir / "xp-evidence.json"
    evidence_file.write_text("{}\n", encoding="utf-8")
    target = "windows-xp-native-x86"

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag="v1.0.2",
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=evidence_file,
        xp_evidence_dir=evidence_dir,
    )

    assert f"{target} artifact directory must stay inside local evidence root: {artifacts}" in errors
    assert f"{target} XP evidence file must stay inside local evidence root: {evidence_file}" in errors
    assert f"{target} XP evidence directory must stay inside local evidence root: {evidence_dir}" in errors


def test_platform_goal_local_evidence_rejects_file_shaped_xp_directories(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    target = "windows-xp-native-x86"
    tag = "v1.0.2"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts.zip"
    evidence_dir = target_root / "xp-evidence.zip"

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=target_root / "xp-evidence.json",
        xp_evidence_dir=evidence_dir,
    )

    assert f"{target} artifact directory must be a directory path, got {artifacts.as_posix()!r}" in errors
    assert f"{target} XP evidence directory must be a directory path, got {evidence_dir.as_posix()!r}" in errors


def test_platform_goal_local_evidence_rejects_xp_inputs_outside_target_release_scope(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    root = tmp_path
    shared = root / "shared-xp-evidence"
    artifacts = shared / "artifacts"
    evidence_dir = shared / "evidence"
    evidence_dir.mkdir(parents=True)
    evidence_file = evidence_dir / "xp-evidence.json"
    evidence_file.write_text("{}\n", encoding="utf-8")
    target = "windows-xp-native-x86"
    tag = "v1.0.2"

    errors = checker.check_platform_goal_local_evidence(
        root=root,
        release_tag=tag,
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=evidence_file,
        xp_evidence_dir=evidence_dir,
    )

    expected_scope = f"{target}/{tag}"
    assert (
        f"{target} artifact directory must include target/release path segment "
        f"{expected_scope} under local evidence root: {artifacts}"
    ) in errors
    assert (
        f"{target} XP evidence file must include target/release path segment "
        f"{expected_scope} under local evidence root: {evidence_file}"
    ) in errors
    assert (
        f"{target} XP evidence directory must include target/release path segment "
        f"{expected_scope} under local evidence root: {evidence_dir}"
    ) in errors


def test_platform_goal_local_evidence_accepts_xp_explicit_target_scoped_paths(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "release" / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence_dir = target_root / "proof"
    evidence_dir.mkdir()
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"{target}/{tag}/release/artifacts",
    )
    fixtures._attach_smoke_evidence_files(evidence_dir, evidence)
    evidence_file = evidence_dir / "xp-evidence.json"
    evidence_file.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=evidence_file,
        xp_evidence_dir=evidence_dir,
        xp_source_workflow_run_url=XP_SOURCE_WORKFLOW_RUN_URL,
        xp_source_head_sha=XP_SOURCE_HEAD_SHA,
        xp_source_run_attempt=XP_SOURCE_RUN_ATTEMPT,
    )

    assert errors == []


def test_platform_goal_local_evidence_accepts_xp_workspace_prefixed_release_paths(tmp_path: Path) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    artifacts = tmp_path / "native-dist" / "windows-xp" / target / tag
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence_dir = tmp_path / "evidence" / target / tag
    evidence_dir.mkdir(parents=True)
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"native-dist/windows-xp/{target}/{tag}",
    )
    fixtures._attach_smoke_evidence_files(evidence_dir, evidence)
    evidence_file = evidence_dir / "xp-evidence.json"
    evidence_file.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        assets_dir=artifacts,
        xp_evidence=evidence_file,
        xp_evidence_dir=evidence_dir,
        xp_source_workflow_run_url=XP_SOURCE_WORKFLOW_RUN_URL,
        xp_source_head_sha=XP_SOURCE_HEAD_SHA,
        xp_source_run_attempt=XP_SOURCE_RUN_ATTEMPT,
    )

    assert errors == []


def test_platform_goal_local_evidence_rejects_xp_artifact_validation_assets_dir_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_local_evidence_checker()
    fixtures = _load_record_fixtures()
    artifact_checker = fixtures._load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{artifact_checker.read_project_version()}"
    target_root = tmp_path / target / tag
    artifacts = target_root / "artifacts"
    artifacts.mkdir(parents=True)
    names = fixtures._required_names(artifact_checker, target, tag)
    fixtures._write_artifact_set(artifacts, names)
    evidence = fixtures._valid_xp_evidence(target, "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"native-dist/windows-xp/{target}/{tag}",
        f"staged/{target}/{tag}/artifacts",
    )
    fixtures._attach_smoke_evidence_files(target_root, evidence)
    (target_root / "xp-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = checker.check_platform_goal_local_evidence(
        root=tmp_path,
        release_tag=tag,
        targets=(target,),
        xp_source_workflow_run_url=XP_SOURCE_WORKFLOW_RUN_URL,
        xp_source_head_sha=XP_SOURCE_HEAD_SHA,
        xp_source_run_attempt=XP_SOURCE_RUN_ATTEMPT,
    )

    assert (
        f"{target} XP evidence artifact_validation.command --assets-dir must match "
        f"local artifacts path {target}/{tag}/artifacts, got ['staged/{target}/{tag}/artifacts']"
    ) in errors


def _set_xp_release_source(
    evidence: dict,
    *,
    workflow_run_url: str,
    head_sha: str,
    run_attempt: int,
) -> None:
    previous = dict(evidence["release_source"])
    evidence["release_source"] = {
        **previous,
        "workflow_run_url": workflow_run_url,
        "head_sha": head_sha,
        "run_attempt": run_attempt,
    }
    for result in evidence["smoke_results"]:
        command = str(result["command"])
        command = command.replace(
            f"--source-workflow-run-url {previous['workflow_run_url']}",
            f"--source-workflow-run-url {workflow_run_url}",
        )
        command = command.replace(
            f"--source-head-sha {previous['head_sha']}",
            f"--source-head-sha {head_sha}",
        )
        command = command.replace(
            f"--source-run-attempt {previous['run_attempt']}",
            f"--source-run-attempt {run_attempt}",
        )
        result["command"] = command


def _load_local_evidence_checker():
    return _load_module(
        "check_platform_goal_local_evidence",
        Path("scripts/check_platform_goal_local_evidence.py"),
    )


def _load_record_fixtures():
    return _load_module(
        "test_make_platform_verified_evidence_record_fixtures",
        Path("tests/test_make_platform_verified_evidence_record.py"),
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
