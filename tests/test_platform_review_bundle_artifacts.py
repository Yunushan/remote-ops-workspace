from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def test_platform_review_bundle_artifacts_validates_finalized_xp_bundle(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert errors == []


def test_platform_review_bundle_artifacts_validates_finalized_linux_bundle(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert errors == []


def test_platform_review_bundle_artifacts_accepts_required_release_tag(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=("windows-xp-native-x86",),
        required_release_tag="v1.0.2",
    )

    assert errors == []


def test_platform_review_bundle_artifacts_goal_targets_require_release_tag(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=validator.PROTECTED_GOAL_TARGETS,
    )

    assert errors == ["protected platform goal required targets require --release-tag vX.Y.Z"]


def test_platform_review_bundle_artifacts_rejects_required_release_tag_mismatch(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=("windows-xp-native-x86",),
        required_release_tag="v1.0.3",
    )

    assert errors == [
        "missing required accepted evidence targets for release_tag v1.0.3: "
        "['windows-xp-native-x86']"
    ]


def test_platform_review_bundle_artifacts_rejects_review_bundle_hash_mismatch(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["review_bundle"]["archive"]["sha256"] = "0" * 64
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 review_bundle archive.sha256 does not match file "
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_symlinked_bundle_file(
    tmp_path: Path, monkeypatch
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    archive_name = str(record["review_bundle"]["archive"]["file"])
    registry = _registry_with(record)

    def fake_is_symlink(self: Path) -> bool:
        return self.name == archive_name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        f"windows-xp-native-x86 review_bundle archive file must not be a symlink: {archive_name}"
        in errors
    )


def test_platform_review_bundle_artifacts_rejects_symlinked_bundle_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert f"review bundle directory must not be a symlink: {tmp_path}" in errors


def test_platform_review_bundle_artifacts_rejects_symlinked_bundle_directory_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)
    bundle_parent = tmp_path / "linked-parent"
    bundle_dir = bundle_parent / "review-bundles"
    bundle_dir.mkdir(parents=True)

    def fake_is_symlink(self: Path) -> bool:
        return self == bundle_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=bundle_dir,
    )

    assert errors == [
        f"review bundle directory path must not contain symlinked directories: {bundle_parent}"
    ]


def test_check_record_review_bundle_artifacts_rejects_unsafe_bundle_file_name(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["review_bundle"]["archive"]["file"] = "../xp-native-evidence-bundle.zip"

    errors = validator.check_record_review_bundle_artifacts(record, tmp_path)

    assert (
        "windows-xp-native-x86 review_bundle archive.file must be an exact safe file name: "
        "'../xp-native-evidence-bundle.zip'"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_unsafe_manifest_candidate_file(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    bundle_helpers = _load_finalize_tests()
    record = _finalized_xp_record(tmp_path)
    review_bundle = record["review_bundle"]
    manifest = tmp_path / str(review_bundle["manifest"]["file"])
    archive = tmp_path / str(review_bundle["archive"]["file"])
    sidecar = tmp_path / str(review_bundle["sha256s"]["file"])
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["candidate_record"]["file"] = "nested/platform-verified-evidence-windows-xp-native-x86.json"
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _refresh_review_bundle_record_hashes(record, bundle_helpers, manifest, archive, sidecar)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 review bundle manifest candidate_record.file must be "
        "an exact safe file name: 'nested/platform-verified-evidence-windows-xp-native-x86.json'"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_symlinked_archive_entry(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    bundle_helpers = _load_finalize_tests()
    record = _finalized_xp_record(tmp_path)
    review_bundle = record["review_bundle"]
    manifest = tmp_path / str(review_bundle["manifest"]["file"])
    archive = tmp_path / str(review_bundle["archive"]["file"])
    sidecar = tmp_path / str(review_bundle["sha256s"]["file"])
    bundle_helpers._rewrite_archive_entry_as_symlink(archive, "xp-evidence.json")
    bundle_helpers._rewrite_sidecar(sidecar, manifest=manifest, archive=archive)
    _refresh_review_bundle_record_hashes(record, bundle_helpers, manifest, archive, sidecar)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 review bundle archive entries must not be symlinks: "
        "['xp-evidence.json']"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_registry_candidate_drift(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["checks"] = [*record["checks"], "tampered-after-finalization"]
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 archived candidate_record must match accepted evidence record before finalization"
        in errors
    )


def test_prefinalized_candidate_record_removes_finalization_only_source_files(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)

    candidate = validator.prefinalized_candidate_record(record)

    assert "finalized_record_release_asset_url" not in candidate
    assert set(candidate["release_asset_source"]["contains_files"]) == set(record["artifact_sha256"])
    assert "platform-verified-evidence-linux-i386-final.json" not in candidate["release_asset_source"]["contains_files"]
    assert all(
        not str(name).startswith("extended-linux-evidence-bundle-")
        for name in candidate["release_asset_source"]["contains_files"]
    )


def _finalized_xp_record(tmp_path: Path) -> dict[str, Any]:
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    helpers = _load_platform_verified_evidence_tests()
    bundle_helpers = _load_finalize_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = _prefinalized_candidate(helpers._xp_record(target))
    candidate_path, manifest, archive, sidecar = bundle_helpers._write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert errors == []
    return record


def _finalized_linux_record(tmp_path: Path) -> dict[str, Any]:
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    helpers = _load_platform_verified_evidence_tests()
    bundle_helpers = _load_finalize_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = _prefinalized_candidate(helpers._linux_record(target))
    artifact_archive_files = bundle_helpers._attach_artifact_files(candidate)

    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    bundle_helpers._write_linux_smoke_evidence(smoke_path, target, candidate["artifact_sha256"])
    smoke_sha = bundle_helpers._sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")

    manifest, archive, sidecar = bundle_helpers._write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "validated_commands": bundle_helpers._linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": bundle_helpers._file_record(builder_path),
            "smoke_evidence": [
                bundle_helpers._smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)
            ],
            "candidate_record": bundle_helpers._file_record(candidate_path),
            "artifacts": bundle_helpers._artifact_records(candidate),
        },
        archive_files={
            **artifact_archive_files,
            builder_path.name: builder_path.read_bytes(),
            smoke_path.name: smoke_path.read_bytes(),
            candidate_path.name: candidate_path.read_bytes(),
        },
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert errors == []
    return record


def _registry_with(record: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": [record]}


def _prefinalized_candidate(record: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(record)
    candidate.pop("review_bundle", None)
    candidate.pop("finalized_record_release_asset_url", None)
    source = candidate.get("release_asset_source")
    artifact_hashes = candidate.get("artifact_sha256")
    if isinstance(source, dict) and isinstance(artifact_hashes, dict):
        source_data = dict(source)
        source_data["contains_files"] = sorted(str(name) for name in artifact_hashes)
        candidate["release_asset_source"] = source_data
    return candidate


def _sync_linux_source_record(
    record: dict[str, Any],
    key: str,
    sha256: str,
    size_bytes: int,
) -> None:
    sources = record.get("linux_evidence_sources")
    if isinstance(sources, dict) and isinstance(sources.get(key), dict):
        source = sources[key]
        source["sha256"] = sha256
        source["size_bytes"] = size_bytes


def _refresh_review_bundle_record_hashes(
    record: dict[str, Any],
    bundle_helpers: Any,
    manifest: Path,
    archive: Path,
    sidecar: Path,
) -> None:
    review_bundle = record["review_bundle"]
    for key, path in (("manifest", manifest), ("archive", archive), ("sha256s", sidecar)):
        review_bundle[key]["size_bytes"] = path.stat().st_size
        review_bundle[key]["sha256"] = bundle_helpers._sha256(path)


def _load_script(name: str) -> Any:
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_tests() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_test_helpers_for_bundles", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_verified_evidence_test_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
