from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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
    )

    assert errors == []


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
    )

    assert (
        f"{target} XP evidence artifact_validation.command --assets-dir must match "
        f"local artifacts path {target}/{tag}/artifacts, got ['staged/{target}/{tag}/artifacts']"
    ) in errors


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
