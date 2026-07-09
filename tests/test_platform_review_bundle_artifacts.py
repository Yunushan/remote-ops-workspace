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


def test_platform_review_bundle_artifacts_validates_final_record_asset_when_required(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    _write_final_record_asset(record, tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        require_final_record_assets=True,
    )

    assert errors == []


def test_platform_review_bundle_artifacts_requires_final_record_asset_when_requested(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        require_final_record_assets=True,
    )

    assert (
        "linux-i386 finalized accepted-record asset missing from bundle directory: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_final_record_asset_drift(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    final_record = _write_final_record_asset(record, tmp_path)
    data = json.loads(final_record.read_text(encoding="utf-8"))
    data["readiness_percent"] = 99.0
    final_record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        require_final_record_assets=True,
    )

    assert (
        "linux-i386 finalized accepted-record asset must match accepted registry record: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_platform_review_bundle_artifacts_rejects_noncanonical_final_record_asset(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    final_record = _write_final_record_asset(record, tmp_path)
    final_record.write_bytes((json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
    registry = _registry_with(record)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        require_final_record_assets=True,
    )

    assert (
        "linux-i386 finalized accepted-record asset must use canonical sorted JSON: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_platform_review_bundle_artifacts_final_asset_helper_rejects_malformed_target(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")

    errors = validator.check_final_record_asset({"target": True}, tmp_path)

    assert errors == ["finalized accepted-record asset target must be a string, got True"]
    assert not (tmp_path / "platform-verified-evidence-True-final.json").exists()


def test_platform_review_bundle_artifacts_final_asset_helper_rejects_non_string_record_keys(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    record[True] = "coerced-private-field"
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    final_record.write_text("{}\n", encoding="utf-8")

    errors = validator.check_final_record_asset(record, tmp_path)

    assert errors == [
        "linux-i386 finalized accepted-record registry keys must be strings, got True"
    ]


def test_platform_review_bundle_artifacts_public_record_does_not_stringify_keys(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    record["_scratch"] = "private"
    record[True] = "coerced"

    public = validator.public_record(record)

    assert "_scratch" not in public
    assert True not in public
    assert "True" not in public
    assert public["target"] == "linux-i386"


def test_platform_review_bundle_artifacts_target_filter_does_not_stringify_targets() -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    rows = [
        {"target": "True", "release_tag": "v1.0.2"},
        {"target": "linux-i386", "release_tag": "v1.0.2"},
    ]

    records = validator.records_for_artifact_validation(
        rows,
        required_targets=(True,),
        required_release_tag="v1.0.2",
    )

    assert records == []


def test_platform_review_bundle_artifacts_target_filter_does_not_normalize_padded_targets() -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    rows = [
        {"target": "linux-i386", "release_tag": "v1.0.2"},
    ]

    records = validator.records_for_artifact_validation(
        rows,
        required_targets=(" linux-i386",),
        required_release_tag="v1.0.2",
    )

    assert records == []


def test_platform_review_bundle_artifacts_rejects_symlinked_final_record_asset_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_linux_record(tmp_path)
    _write_final_record_asset(record, tmp_path)

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = validator.check_final_record_asset(record, tmp_path)

    assert errors == [
        f"linux-i386 finalized accepted-record asset path must not contain symlinked directories: {tmp_path}"
    ]


def test_platform_review_bundle_artifacts_scopes_final_record_assets_to_required_targets(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    linux_record = _finalized_linux_record(tmp_path)
    xp_record = _finalized_xp_record(tmp_path)
    _write_final_record_asset(linux_record, tmp_path)
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    registry = {**registry, "accepted_evidence": [linux_record, xp_record]}

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=tmp_path,
        required_targets=("linux-i386",),
        required_release_tag="v1.0.2",
        require_final_record_assets=True,
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


def test_platform_review_bundle_artifacts_goal_cli_requires_release_tag(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")

    assert validator.main(["--bundle-dir", str(tmp_path), "--require-goal-targets"]) == 2


def test_platform_review_bundle_artifacts_rejects_reserved_registry_path(tmp_path: Path) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    registry = Path(".github") / "platform_verified_evidence.json"
    args = validator.parse_args(
        [
            "--registry",
            str(registry),
            "--bundle-dir",
            str(tmp_path),
        ]
    )

    errors = validator.strict_platform_goal_arg_errors(args)

    assert errors == [
        "accepted evidence registry must not point inside reserved workspace directory "
        f"'.github': {registry}"
    ]


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


def test_platform_review_bundle_artifacts_rejects_boolean_review_bundle_size(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    bundle = tmp_path / "one-byte-review-bundle.zip"
    bundle.write_bytes(b"x")

    errors = validator.check_file_record(
        "linux-i386",
        "archive",
        bundle,
        {"file": bundle.name, "size_bytes": True, "sha256": validator.sha256_file(bundle)},
    )

    assert "linux-i386 review_bundle archive.size_bytes does not match file one-byte-review-bundle.zip" in errors


def test_platform_review_bundle_artifacts_rejects_non_string_review_bundle_sha(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    bundle = tmp_path / "one-byte-review-bundle.zip"
    bundle.write_bytes(b"x")

    errors = validator.check_file_record(
        "linux-i386",
        "archive",
        bundle,
        {"file": bundle.name, "size_bytes": bundle.stat().st_size, "sha256": True},
    )

    assert (
        "linux-i386 review_bundle archive.sha256 must be a string SHA-256 hex digest, "
        "got True"
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


def test_platform_review_bundle_artifacts_rejects_file_shaped_bundle_directory(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)
    bundle_dir = tmp_path / "review-bundles.zip"

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=bundle_dir,
    )

    assert f"review bundle directory must be a directory path, got {bundle_dir.as_posix()!r}" in errors
    assert not bundle_dir.exists()


def test_platform_review_bundle_artifacts_rejects_reserved_workspace_bundle_directory(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)
    bundle_dir = Path(".github") / "release-assets"

    errors = validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=bundle_dir,
    )

    assert (
        "review bundle directory must not point inside reserved workspace directory "
        f"'.github': {bundle_dir}"
    ) in errors
    assert not bundle_dir.exists()


def test_platform_review_bundle_artifacts_path_helpers_reject_non_path_args(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    registry = _registry_with(record)

    assert validator.check_registry_path("evidence.json") == [
        "accepted evidence registry path must be a pathlib.Path, got 'evidence.json'"
    ]
    assert validator.check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir="release-assets",
    ) == ["review bundle directory path must be a pathlib.Path, got 'release-assets'"]
    assert validator.check_record_review_bundle_artifacts(record, "release-assets") == [
        "review bundle directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert validator.check_final_record_asset(record, "release-assets") == [
        "windows-xp-native-x86 finalized accepted-record asset directory path "
        "must be a pathlib.Path, got 'release-assets'"
    ]
    assert validator.check_file_record(
        "linux-i386",
        "archive",
        "review-bundle.zip",
        {"size_bytes": 0, "sha256": "0" * 64},
    ) == [
        "linux-i386 review_bundle archive file path must be a pathlib.Path, "
        "got 'review-bundle.zip'"
    ]
    assert validator.check_path_parent_symlinks("review-bundles", "review bundle directory") == [
        "review bundle directory path must be a pathlib.Path, got 'review-bundles'"
    ]
    assert validator.check_directory_path_hint("review-bundles", "review bundle directory") == [
        "review bundle directory path must be a pathlib.Path, got 'review-bundles'"
    ]
    assert validator.check_path_not_reserved_workspace_root(
        "review-bundles",
        "review bundle directory",
    ) == ["review bundle directory path must be a pathlib.Path, got 'review-bundles'"]

    errors: list[str] = []
    assert validator.load_json("manifest.json", "review bundle manifest", errors) is None
    assert errors == [
        "review bundle manifest path must be a pathlib.Path, got 'manifest.json'"
    ]

    errors = []
    assert (
        validator.read_archive_file(
            "review-bundle.zip",
            "candidate.json",
            errors,
            "linux-i386",
        )
        is None
    )
    assert errors == [
        "linux-i386 review bundle archive path must be a pathlib.Path, "
        "got 'review-bundle.zip'"
    ]


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


def test_check_record_review_bundle_artifacts_rejects_non_string_bundle_file_name(
    tmp_path: Path,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    record = _finalized_xp_record(tmp_path)
    record["review_bundle"]["manifest"]["file"] = True

    errors = validator.check_record_review_bundle_artifacts(record, tmp_path)

    assert "windows-xp-native-x86 review_bundle manifest.file must be a string, got True" in errors


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


def test_platform_review_bundle_artifacts_rejects_non_string_manifest_candidate_file(
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
    data["candidate_record"]["file"] = True
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _refresh_review_bundle_record_hashes(record, bundle_helpers, manifest, archive, sidecar)

    errors = validator.check_platform_review_bundle_artifacts(
        registry=_registry_with(record),
        bundle_dir=tmp_path,
    )

    assert (
        "windows-xp-native-x86 review bundle manifest candidate_record.file "
        "must be a string, got True"
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


def test_platform_review_bundle_artifacts_reports_unreadable_candidate_entry(
    monkeypatch,
) -> None:
    validator = _load_script("check_platform_review_bundle_artifacts")
    candidate_name = "platform-verified-evidence-linux-i386.json"

    class UnreadableZipFile:
        def __init__(self, _path: Path) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def infolist(self) -> list[Any]:
            info = validator.zipfile.ZipInfo(candidate_name)
            info.external_attr = 0o100644 << 16
            return [info]

        def read(self, _filename: str) -> bytes:
            raise NotImplementedError("unsupported compression method")

    monkeypatch.setattr(validator.zipfile, "ZipFile", UnreadableZipFile)
    errors: list[str] = []

    result = validator.read_archive_file(
        Path("review-bundle.zip"),
        candidate_name,
        errors,
        "linux-i386",
    )

    assert result is None
    assert (
        "linux-i386 review bundle archive candidate_record is not readable: "
        "platform-verified-evidence-linux-i386.json: unsupported compression method"
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
    bundle_helpers._write_linux_smoke_evidence(
        smoke_path,
        target,
        candidate["artifact_sha256"],
        builder_evidence=bundle_helpers._candidate_builder_evidence_path(target, release_tag),
    )
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
            "release_asset_source": candidate["release_asset_source"],
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


def _write_final_record_asset(record: dict[str, Any], root: Path) -> Path:
    target = str(record["target"])
    path = root / f"platform-verified-evidence-{target}-final.json"
    path.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


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
