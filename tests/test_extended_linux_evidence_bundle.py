from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def test_extended_linux_evidence_bundle_packages_valid_i386_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    out_dir = assets

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=out_dir,
    )

    assert errors == []
    manifest = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}.json"
    archive = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}.zip"
    sidecar = out_dir / f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["target"] == target
    assert data["release_tag"] == tag
    assert data["bundle_type"] == "extended-linux-native-evidence"
    assert len(data["artifacts"]) == len(names)
    assert data["release_asset_urls"] == record["release_asset_urls"]
    assert data["release_asset_source"] == record["release_asset_source"]
    assert data["workflow_inputs"]["target"] == target
    assert data["security_patch_evidence"]["tls_minimum_modern_profiles"] == "TLS 1.2"
    assert data["security_patch_evidence"]["cve_patch_reviewed"] is True
    assert data["validated_commands"] == [
        record["native_build_command"],
        record["native_smoke_command"],
        record["local_evidence_preflight_command"],
        record["staged_upload_command"],
        record["artifact_validation_command"],
        "python scripts/check_platform_verified_evidence.py",
    ]
    assert all("<" not in command and ">" not in command for command in data["validated_commands"])
    assert data["smoke_evidence"] == [
        {
            "id": "native_smoke",
            "file": smoke.name,
            "size_bytes": smoke.stat().st_size,
            "sha256": _sha256(smoke),
        }
    ]
    with zipfile.ZipFile(archive) as zipped:
        names_in_archive = set(zipped.namelist())
        assert manifest.name in names_in_archive
        assert builder.name in names_in_archive
        assert smoke.name in names_in_archive
        assert candidate.name in names_in_archive
        assert set(names).issubset(names_in_archive)
    sidecar_text = sidecar.read_text(encoding="utf-8")
    assert f"{_sha256(manifest)}  {manifest.name}" in sidecar_text
    assert f"{_sha256(archive)}  {archive.name}" in sidecar_text


def test_extended_linux_evidence_bundle_reruns_local_protected_goal_preflight(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def fail_preflight(**kwargs):
        calls.append(kwargs)
        return ["sentinel local preflight failure"]

    monkeypatch.setattr(bundler, "check_local_protected_goal_preflight", fail_preflight)

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=assets,
    )

    assert errors == ["sentinel local preflight failure"]
    assert calls[0]["target"] == target
    assert calls[0]["candidate"] == record
    assert not (assets / f"extended-linux-evidence-bundle-{target}-{tag}.json").exists()


def test_extended_linux_evidence_bundle_rejects_unscoped_output_directory() -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")

    errors = bundler.check_target_release_path_segments(
        "linux-i386",
        "v1.0.2",
        Path("bundle"),
        label="extended Linux evidence bundle output directory",
    )

    assert any(
        "extended Linux evidence bundle output directory must include target path segment 'linux-i386'" in error
        for error in errors
    )
    assert any(
        "extended Linux evidence bundle output directory must include release_tag path segment 'v1.0.2'" in error
        for error in errors
    )


def test_extended_linux_evidence_bundle_rejects_artifact_hash_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    record["artifact_sha256"][names[0]] = "0" * 64
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert "candidate artifact_sha256 must match current artifact files" in errors


def test_extended_linux_evidence_bundle_rejects_extra_artifact_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    (assets / "unexpected-extra.txt").write_text("extra\n", encoding="utf-8")
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert "linux-i386 artifacts include unexpected files: ['unexpected-extra.txt']" in errors


def test_extended_linux_evidence_bundle_rejects_unscoped_evidence_file_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    wrong_builder = Path("builder.json")
    wrong_builder.write_bytes(builder.read_bytes())
    wrong_smoke = Path("native-smoke.log")
    wrong_smoke.write_bytes(smoke.read_bytes())
    wrong_candidate = Path("candidate.json")
    wrong_candidate.write_bytes(candidate.read_bytes())

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=wrong_builder,
        smoke_evidence=wrong_smoke,
        candidate_record=wrong_candidate,
        out_dir=Path("bundle"),
    )

    assert "builder evidence file name must be builder-identity-linux-i386.json, got 'builder.json'" in errors
    assert "smoke evidence file name must be native-smoke-linux-i386.log, got 'native-smoke.log'" in errors
    assert (
        "candidate evidence record file name must be platform-verified-evidence-linux-i386.json, "
        "got 'candidate.json'"
    ) in errors


def test_extended_linux_evidence_bundle_rejects_symlinked_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    target = "linux-armhf"
    builder = tmp_path / "builder-identity-linux-armhf.json"
    smoke = tmp_path / "native-smoke-linux-armhf.log"
    candidate = tmp_path / "platform-verified-evidence-linux-armhf.json"
    for path in (builder, smoke, candidate):
        path.write_text("{}\n", encoding="utf-8")
    symlink_names = {builder.name, smoke.name, candidate.name}

    def fake_is_symlink(self: Path) -> bool:
        return self.name in symlink_names

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag="v1.0.2",
        assets_dir=tmp_path / "assets",
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert f"builder evidence file must not be a symlink: {builder}" in errors
    assert f"smoke evidence file must not be a symlink: {smoke}" in errors
    assert f"candidate evidence record file must not be a symlink: {candidate}" in errors


def test_extended_linux_evidence_bundle_rejects_symlinked_input_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    linked_root = tmp_path / "linked-evidence-root"
    builder = linked_root / "builder-identity-linux-armhf.json"
    smoke = linked_root / "native-smoke-linux-armhf.log"
    candidate = linked_root / "platform-verified-evidence-linux-armhf.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_root

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.make_extended_linux_evidence_bundle(
        target="linux-armhf",
        release_tag="v1.0.2",
        assets_dir=tmp_path / "assets",
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert (
        f"builder evidence file path must not contain symlinked directories: {linked_root}"
    ) in errors
    assert (
        f"smoke evidence file path must not contain symlinked directories: {linked_root}"
    ) in errors
    assert (
        f"candidate evidence record file path must not contain symlinked directories: {linked_root}"
    ) in errors


def test_extended_linux_evidence_bundle_rejects_finalized_candidate_record(
    tmp_path: Path,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    target = "linux-i386"
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text("{}\n", encoding="utf-8")
    smoke = tmp_path / "native-smoke-linux-i386.log"
    smoke.write_text("smoke\n", encoding="utf-8")
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(
        json.dumps(
            {
                "target": target,
                "release_tag": "v1.0.2",
                "finalized_record_release_asset_url": (
                    "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
                    "platform-verified-evidence-linux-i386-final.json"
                ),
                "review_bundle": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag="v1.0.2",
        assets_dir=tmp_path / "assets",
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert errors == [
        "candidate evidence record must be unfinalized before bundling; "
        "remove fields: ['finalized_record_release_asset_url', 'review_bundle']"
    ]


def test_extended_linux_evidence_bundle_rejects_missing_artifact_directory_before_hashing(
    tmp_path: Path,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    target = "linux-i386"
    builder = tmp_path / "builder-identity-linux-i386.json"
    builder.write_text(json.dumps({"target": target}, indent=2) + "\n", encoding="utf-8")
    smoke = tmp_path / "native-smoke-linux-i386.log"
    smoke.write_text("smoke\n", encoding="utf-8")
    candidate = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(
        json.dumps({"target": target, "release_tag": "v1.0.2"}, indent=2) + "\n",
        encoding="utf-8",
    )
    missing_assets = tmp_path / "missing-assets"

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag="v1.0.2",
        assets_dir=missing_assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=tmp_path / "bundle",
    )

    assert f"artifact directory missing: {missing_assets}" in errors


def test_extended_linux_evidence_bundle_rejects_file_shaped_artifact_directory(
    tmp_path: Path,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    assets = tmp_path / "artifacts.zip"
    assets.mkdir()

    errors = bundler.make_extended_linux_evidence_bundle(
        target="linux-i386",
        release_tag="v1.0.2",
        assets_dir=assets,
        builder_evidence=tmp_path / "builder-identity-linux-i386.json",
        smoke_evidence=tmp_path / "native-smoke-linux-i386.log",
        candidate_record=tmp_path / "platform-verified-evidence-linux-i386.json",
        out_dir=tmp_path / "bundle",
    )

    assert f"artifact directory must be a directory path, got {assets.as_posix()!r}" in errors


def test_extended_linux_evidence_bundle_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    def fake_is_symlink(self: Path) -> bool:
        return self == out_dir

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        f"extended Linux evidence bundle output directory must not be a symlink: {out_dir}"
    ]


def test_extended_linux_evidence_bundle_rejects_file_shaped_output_directory(
    tmp_path: Path,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    out_dir = tmp_path / "bundle.zip"
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        "extended Linux evidence bundle output directory "
        f"must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_extended_linux_evidence_bundle_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    out_parent = tmp_path / "linked-bundle-root"
    out_dir = out_parent / "bundle"
    outputs = (out_dir / "bundle.json", out_dir / "bundle.zip", out_dir / "bundle-SHA256SUMS.txt")

    def fake_is_symlink(self: Path) -> bool:
        return self == out_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(out_dir=out_dir, outputs=outputs, force=True)

    assert errors == [
        f"extended Linux evidence bundle output directory path must not contain symlinked directories: {out_parent}"
    ]


def test_extended_linux_evidence_bundle_rejects_unsafe_output_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()
    symlink_output = out_dir / "bundle.json"
    symlink_output.write_text("old manifest\n", encoding="utf-8")
    directory_output = out_dir / "bundle.zip"
    directory_output.mkdir()
    sidecar_output = out_dir / "bundle-SHA256SUMS.txt"

    def fake_is_symlink(self: Path) -> bool:
        return self == symlink_output

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = bundler.prepare_output_paths(
        out_dir=out_dir,
        outputs=(symlink_output, directory_output, sidecar_output),
        force=True,
    )

    assert "extended Linux evidence bundle output file must not be a symlink: bundle.json" in errors
    assert "extended Linux evidence bundle output must be a regular file: bundle.zip" in errors


def test_extended_linux_evidence_bundle_rejects_weak_smoke_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, valid_smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=valid_smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    weak_smoke = valid_smoke
    weak_smoke.write_text("linux-i386 native smoke passed\n", encoding="utf-8")
    smoke_sha = _sha256(weak_smoke)
    record["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(record, "native_smoke", smoke_sha, weak_smoke.stat().st_size)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=weak_smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert any(
        "linux-i386 linux_smoke_evidence missing required line: "
        "native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        f"--builder-evidence {builder.as_posix()}"
        in error
        for error in errors
    )


def test_extended_linux_evidence_bundle_rejects_builder_smoke_identity_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-i386"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "i386"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    builder_identity = json.loads(builder.read_text(encoding="utf-8"))
    builder_identity["host_identity"]["evidence_run_id"] = "linux-i386-1-0-2-run-99999"
    builder_identity["host_identity"]["observed_at_utc"] = "2026-06-20T12:30:00Z"
    builder.write_text(json.dumps(builder_identity, indent=2) + "\n", encoding="utf-8")
    builder_sha = generator.json_sha256(builder_identity)
    record["builder_identity"] = builder_identity
    record["builder_identity_sha256"] = builder_sha
    _sync_linux_source_record(record, "builder_identity", builder_sha, builder.stat().st_size)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-i386.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert (
        "linux-i386 linux_smoke_evidence native installer smoke evidence run id must match "
        "builder_identity.host_identity.evidence_run_id 'linux-i386-1-0-2-run-99999', "
        "got 'linux-i386-1-0-2-run-12345'"
    ) in errors
    assert (
        "linux-i386 linux_smoke_evidence native installer smoke observed at utc must not be earlier than "
        "builder_identity.host_identity.observed_at_utc '2026-06-20T12:30:00Z', "
        "got '2026-06-20T12:00:00Z'"
    ) in errors


def test_extended_linux_evidence_bundle_rejects_builder_smoke_runtime_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "armhf"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    builder_identity = json.loads(builder.read_text(encoding="utf-8"))
    builder_identity["os_release"] = "Debian GNU/Linux 13 (trixie)"
    builder_identity["kernel_release"] = "6.12.0-armhf-ci"
    builder_identity["glibc_version"] = "glibc 2.40"
    builder.write_text(json.dumps(builder_identity, indent=2) + "\n", encoding="utf-8")
    builder_sha = generator.json_sha256(builder_identity)
    record["builder_identity"] = builder_identity
    record["builder_identity_sha256"] = builder_sha
    _sync_linux_source_record(record, "builder_identity", builder_sha, builder.stat().st_size)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-armhf.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert (
        "linux-armhf linux_smoke_evidence native installer smoke os release must match "
        "builder_identity.os_release 'Debian GNU/Linux 13 (trixie)', "
        "got 'Debian GNU/Linux 12 (bookworm)'"
    ) in errors
    assert (
        "linux-armhf linux_smoke_evidence native installer smoke kernel release must match "
        "builder_identity.kernel_release '6.12.0-armhf-ci', got '6.1.0-i386-ci'"
    ) in errors
    assert (
        "linux-armhf linux_smoke_evidence native installer smoke glibc version must match "
        "builder_identity.glibc_version 'glibc 2.40', got 'glibc 2.36'"
    ) in errors


def test_extended_linux_evidence_bundle_rejects_builder_smoke_security_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundler = _load_script("make_extended_linux_evidence_bundle")
    generator = _load_script("make_platform_verified_evidence_record")
    artifact_checker = _load_script("check_platform_promotion_artifacts")
    target = "linux-armhf"
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, target, tag)
    monkeypatch.chdir(tmp_path)
    assets, builder, smoke = _stage_valid_linux_evidence_inputs(target, tag, names)
    errors, record = generator.build_evidence_record(
        SimpleNamespace(
            target=target,
            release_tag=tag,
            assets_dir=assets,
            release_asset_base_url=(
                f"https://github.com/example/remote-ops-workspace/releases/download/{tag}"
            ),
            workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
            release_source_head_sha="a" * 40,
            release_source_run_attempt=1,
            runner_label=["self-hosted", "linux", "armhf"],
            builder_evidence=builder,
            linux_smoke_evidence=smoke,
            xp_evidence=None,
            xp_evidence_dir=None,
        )
    )
    assert errors == []
    builder_identity = json.loads(builder.read_text(encoding="utf-8"))
    builder_identity["security_patch_evidence"]["security_update_channel"] = "vendor-security-updates-2026-07"
    builder_identity["security_patch_evidence"]["cve_review_reference"] = "vendor-cve-advisory-review-2026-07"
    builder.write_text(json.dumps(builder_identity, indent=2) + "\n", encoding="utf-8")
    builder_sha = generator.json_sha256(builder_identity)
    record["builder_identity"] = builder_identity
    record["builder_identity_sha256"] = builder_sha
    _sync_linux_source_record(record, "builder_identity", builder_sha, builder.stat().st_size)
    candidate = Path(target) / tag / "platform-verified-evidence-linux-armhf.json"
    candidate.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = bundler.make_extended_linux_evidence_bundle(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        builder_evidence=builder,
        smoke_evidence=smoke,
        candidate_record=candidate,
        out_dir=Path("bundle"),
    )

    assert (
        "linux-armhf linux_smoke_evidence native installer smoke security update channel must match "
        "builder_identity.security_patch_evidence.security_update_channel 'vendor-security-updates-2026-07', "
        "got 'vendor-security-updates-2026-06'"
    ) in errors
    assert (
        "linux-armhf linux_smoke_evidence native installer smoke CVE review reference must match "
        "builder_identity.security_patch_evidence.cve_review_reference 'vendor-cve-advisory-review-2026-07', "
        "got 'vendor-cve-advisory-review-2026-06'"
    ) in errors


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "workflow_ref": (
            "example/remote-ops-workspace/.github/workflows/"
            f"extended-platform-evidence.yml@{'a' * 40}"
        ),
        "workflow_sha": "a" * 40,
        "source_head_sha": "a" * 40,
        "observed_git_head_sha": "a" * 40,
        "git_worktree_clean": True,
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg": "/usr/bin/dpkg",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "getconf": "/usr/bin/getconf",
            "openssl": "/usr/bin/openssl",
            "rpm": "/usr/bin/rpm",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
        "security_patch_evidence": {
            "python_ssl_openssl": "OpenSSL 3.0.13",
            "openssl_cli_version": "OpenSSL 3.0.13",
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "cve_patch_reviewed": True,
            "security_update_channel": "vendor-security-updates-2026-06",
            "cve_review_reference": "vendor-cve-advisory-review-2026-06",
        },
    }


def _stage_valid_linux_evidence_inputs(
    target: str,
    tag: str,
    names: list[str],
) -> tuple[Path, Path, Path]:
    target_root = Path(target) / tag
    assets = target_root / "artifacts"
    assets.mkdir(parents=True)
    _write_artifact_set(assets, names)
    builder = target_root / f"builder-identity-{target}.json"
    builder.write_text(json.dumps(_builder_identity(target), indent=2) + "\n", encoding="utf-8")
    smoke = target_root / f"native-smoke-{target}.log"
    _write_linux_smoke_evidence(smoke, target, _smoke_artifact_hashes(assets, names))
    return assets, builder, smoke


def _linux_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_artifact_set(root: Path, names: list[str]) -> None:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]
    manifest_name = next(name for name in names if name.endswith("manifest.json"))
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    for name in payload_names:
        (root / name).write_bytes(_payload_bytes(name))
    records = [
        {
            "file": name,
            "size_bytes": (root / name).stat().st_size,
            "sha256": _sha256(root / name),
        }
        for name in payload_names
    ]
    (root / manifest_name).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    sidecar_names = [*payload_names, manifest_name]
    (root / sidecar_name).write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )


def _write_linux_smoke_evidence(
    path: Path,
    target: str,
    artifact_hashes: dict[str, str],
    *,
    workflow_run_url: str = "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    workflow_run_attempt: int = 1,
    source_head_sha: str = "a" * 40,
    builder_evidence: Path | str | None = None,
) -> None:
    arch = "i386" if target == "linux-i386" else "armhf"
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    run_id = workflow_run_url.rstrip("/").rsplit("/", 1)[-1]
    evidence_run_id = f"{target}-1-0-2-run-{run_id}"
    builder_evidence_path = (
        Path(builder_evidence).as_posix()
        if builder_evidence is not None
        else (path.parent / f"builder-identity-{target}.json").as_posix()
    )
    artifact_lines = [
        f"native installer smoke artifact sha256: {name} {artifact_hashes[name]}"
        for name in sorted(artifact_hashes)
    ]
    path.write_text(
        "\n".join(
            [
                f"native installer smoke command: bash scripts/smoke_linux_native.sh --arch {arch} "
                f"--dist native-dist/linux --target {target} --workflow-run-url {workflow_run_url} "
                f"--workflow-run-attempt {workflow_run_attempt} "
                f"--source-head-sha {source_head_sha} --builder-evidence {builder_evidence_path}",
                "native installer smoke release: v1.0.2",
                f"native installer smoke target arch: {arch}",
                f"native installer smoke target: {target}",
                f"native installer smoke workflow run: {workflow_run_url}",
                f"native installer smoke workflow run attempt: {workflow_run_attempt}",
                f"native installer smoke source head sha: {source_head_sha}",
                f"native installer smoke git head sha: {source_head_sha}",
                f"native installer smoke host label: {target}-builder",
                f"native installer smoke evidence run id: {evidence_run_id}",
                "native installer smoke observed at utc: 2026-06-20T12:00:00Z",
                f"native installer smoke uname machine: {machine}",
                f"native installer smoke dpkg architecture: {dpkg_arch}",
                "native installer smoke userland bits: 32",
                "native installer smoke os release: Debian GNU/Linux 12 (bookworm)",
                "native installer smoke kernel release: 6.1.0-i386-ci",
                "native installer smoke glibc version: glibc 2.36",
                "native installer smoke python ssl openssl: OpenSSL 3.0.13",
                "native installer smoke openssl cli version: OpenSSL 3.0.13",
                "native installer smoke security update channel: vendor-security-updates-2026-06",
                "native installer smoke CVE review reference: vendor-cve-advisory-review-2026-06",
                "native installer smoke TLS minimum modern profiles: TLS 1.2",
                "native installer smoke TLS preferred modern profiles: TLS 1.3",
                "native installer smoke legacy compatibility profile: isolated-opt-in",
                "native installer smoke legacy crypto scope: profile-only",
                "native installer smoke weak crypto global default: false",
                "native installer smoke modern defaults unchanged: true",
                *artifact_lines,
                "native installer smoke: DEB install",
                "native installer smoke: DEB verify",
                "native installer smoke: DEB upgrade",
                "native installer smoke: DEB uninstall",
                "native installer smoke: RPM install",
                "native installer smoke: RPM verify",
                "native installer smoke: RPM upgrade",
                "native installer smoke: RPM uninstall",
                "native installer smoke: AppImage install",
                "native installer smoke: AppImage verify",
                "native installer smoke: AppImage upgrade",
                "native installer smoke: AppImage uninstall",
                f"native installer smoke passed for Linux {arch}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _smoke_artifact_hashes(root: Path, names: list[str]) -> dict[str, str]:
    return {
        name: _sha256(root / name)
        for name in names
        if name.endswith((".deb", ".rpm", ".AppImage"))
    }


def _payload_bytes(name: str) -> bytes:
    if name.endswith(".deb"):
        return b"!<arch>\nlinux i386 deb payload\n"
    if name.endswith(".rpm"):
        return bytes.fromhex("edabeedb") + b"linux i386 rpm payload\n"
    if name.endswith(".AppImage"):
        return b"\x7fELFlinux i386 appimage payload\n"
    if name.endswith(".tar.gz"):
        return _tar_gz_bytes(name)
    return f"{name}\n".encode()


def _tar_gz_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    with io.BytesIO() as raw:
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            info = tarfile.TarInfo("Remote Ops Workspace Linux evidence payload.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return raw.getvalue()


def _sync_linux_source_record(
    record: dict[str, object],
    key: str,
    sha256: str,
    size_bytes: int,
) -> None:
    sources = record.get("linux_evidence_sources")
    if isinstance(sources, dict) and isinstance(sources.get(key), dict):
        source = sources[key]
        source["sha256"] = sha256
        source["size_bytes"] = size_bytes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
