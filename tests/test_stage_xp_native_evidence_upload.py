from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


HISTORICAL_ACCEPTED_RECORD_TAG = "v1.0.2"


def test_stage_xp_native_evidence_upload_copies_only_expected_files(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = HISTORICAL_ACCEPTED_RECORD_TAG
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    staged = tmp_path / "xp-evidence-upload"
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=staged,
    )

    assert errors == []
    assert sorted(path.name for path in staged.iterdir()) == sorted(
        {*expected_assets, *expected_evidence}
    )


def test_stage_xp_native_evidence_upload_rejects_malformed_release_tag_before_file_set(
    tmp_path: Path,
) -> None:
    stager = _load_stager()

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag=True,
        assets_dir=tmp_path / "missing-assets",
        evidence_output_dir=tmp_path / "missing-evidence",
        out_dir=tmp_path / "xp-evidence-upload",
    )

    assert errors == ["XP staged upload release_tag must be a non-empty string, got True"]


def test_stage_xp_native_evidence_upload_rejects_non_path_inputs() -> None:
    stager = _load_stager()

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=True,
        evidence_output_dir=["xp-evidence-output"],
        out_dir=False,
    )

    assert errors == [
        "XP native asset directory must be a pathlib.Path, got True",
        "XP evidence output directory must be a pathlib.Path, got ['xp-evidence-output']",
        "windows-xp-native-x86 staged upload output directory must be a pathlib.Path, got False",
    ]


def test_stage_xp_native_evidence_upload_rejects_ambiguous_upload_file_names() -> None:
    stager = _load_stager()

    errors = stager.check_staged_upload_file_names(
        "windows-xp-native-x86",
        [
            "expected.zip",
            "expected.zip",
            "Readme.txt",
            "readme.txt",
            "nested/expected.zip",
        ],
    )

    assert (
        "windows-xp-native-x86 staged upload file names must be exact safe file names: "
        "['nested/expected.zip']"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload file names must be unique across artifacts and evidence outputs: "
        "['expected.zip']"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload file names must not collide on case-insensitive filesystems: "
        "['Readme.txt', 'readme.txt']"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_computed_upload_name_collision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{checker.read_project_version()}"
    duplicate = f"xp-native-evidence-bundle-{target}-{tag}.json"
    monkeypatch.setattr(stager, "accepted_artifact_names", lambda *_args: {duplicate})

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=tmp_path / "assets" / target / tag,
        evidence_output_dir=tmp_path / "evidence" / target / tag,
        out_dir=tmp_path / "xp-evidence-upload",
    )

    assert errors == [
        "windows-xp-native-x86 staged upload file names must be unique across artifacts and evidence outputs: "
        f"['{duplicate}']"
    ]


def test_stage_xp_native_evidence_upload_rejects_extra_source_entries(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = HISTORICAL_ACCEPTED_RECORD_TAG
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )
    (assets / "operator-private").mkdir()
    (evidence_output / "xp-smoke-working-copy.txt").write_text("raw smoke proof\n", encoding="utf-8")

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert (
        "windows-xp-native-x86 XP native asset directory contains files outside staged upload set: "
        "['operator-private']"
    ) in errors
    assert (
        "windows-xp-native-x86 XP evidence output directory contains files outside staged upload set: "
        "['xp-smoke-working-copy.txt']"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_hash_mismatch(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = HISTORICAL_ACCEPTED_RECORD_TAG
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )
    (assets / expected_assets[0]).write_text("tampered artifact\n", encoding="utf-8")
    (evidence_output / f"xp-native-evidence-bundle-{target}-{tag}.zip").write_text(
        "tampered review bundle\n",
        encoding="utf-8",
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any("staged upload native artifact SHA-256 mismatch" in error for error in errors)
    assert any("staged upload review_bundle archive.sha256 mismatch" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_boolean_review_bundle_size(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    bundle = tmp_path / "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    bundle.write_bytes(b"x")
    record = {
        "review_bundle": {
            "archive": {
                "file": bundle.name,
                "size_bytes": True,
                "sha256": _sha256(bundle),
            },
        },
    }

    errors = stager.check_source_hashes("windows-xp-native-x86", record, {bundle.name: bundle})

    assert (
        "windows-xp-native-x86 staged upload review_bundle archive.size_bytes mismatch: "
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_malformed_hash_digests(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    artifact = tmp_path / "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip"
    bundle = tmp_path / "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    artifact.write_bytes(b"native artifact\n")
    bundle.write_bytes(b"review bundle\n")
    record = {
        "artifact_sha256": {artifact.name: True},
        "review_bundle": {
            "archive": {
                "file": bundle.name,
                "size_bytes": bundle.stat().st_size,
                "sha256": "A" * 64,
            },
        },
    }

    errors = stager.check_source_hashes(
        "windows-xp-native-x86",
        record,
        {
            artifact.name: artifact,
            bundle.name: bundle,
        },
    )

    assert (
        "windows-xp-native-x86 staged upload artifact_sha256."
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip "
        "must be a lowercase SHA-256 hex digest"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload review_bundle archive.sha256 "
        "must be a lowercase SHA-256 hex digest: "
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    ) in errors
    assert not any("native artifact SHA-256 mismatch" in error for error in errors)
    assert not any("review_bundle archive.sha256 mismatch" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_symlinked_source_hashes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    artifact = tmp_path / "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip"
    bundle = tmp_path / "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    artifact.write_bytes(b"native artifact\n")
    bundle.write_bytes(b"review bundle\n")
    record = {
        "artifact_sha256": {artifact.name: _sha256(artifact)},
        "review_bundle": {
            "archive": {
                "file": bundle.name,
                "size_bytes": bundle.stat().st_size,
                "sha256": _sha256(bundle),
            },
        },
    }

    def fake_is_symlink(self: Path) -> bool:
        return self in {artifact, bundle}

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_hashes(
        "windows-xp-native-x86",
        record,
        {
            artifact.name: artifact,
            bundle.name: bundle,
        },
    )

    assert (
        "windows-xp-native-x86 staged upload native artifact must not be a symlink: "
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload review_bundle archive must not be a symlink: "
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.zip"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_ambiguous_review_bundle_files(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    bundle = tmp_path / "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2.json"
    bundle.write_bytes(b"bundle\n")
    collision_file = bundle.name
    record = {
        "review_bundle": {
            "manifest": {
                "file": bundle.name,
                "size_bytes": bundle.stat().st_size,
                "sha256": _sha256(bundle),
            },
            "archive": {
                "file": bundle.name,
                "size_bytes": bundle.stat().st_size,
                "sha256": _sha256(bundle),
            },
            "sha256s": {
                "file": collision_file.upper(),
                "size_bytes": 1,
                "sha256": "0" * 64,
            },
        }
    }

    errors = stager.check_source_hashes("windows-xp-native-x86", record, {bundle.name: bundle})

    assert (
        "windows-xp-native-x86 staged upload review_bundle files must not contain duplicates: "
        f"['{bundle.name}']"
    ) in errors
    assert any(
        "windows-xp-native-x86 staged upload review_bundle files must not collide on "
        "case-insensitive filesystems" in error
        and collision_file in error
        and collision_file.upper() in error
        for error in errors
    )


def test_stage_xp_native_evidence_upload_rejects_malformed_review_bundle_file() -> None:
    stager = _load_stager()
    record = {"review_bundle": {"manifest": {"file": True}}}

    errors = stager.check_source_hashes("windows-xp-native-x86", record, {})

    assert (
        "windows-xp-native-x86 staged upload review_bundle manifest.file "
        "must be an exact safe file name, got True"
    ) in errors


def test_stage_xp_native_evidence_upload_reports_bad_review_bundle_manifest(
    tmp_path: Path,
) -> None:
    stager = _load_stager()

    files, errors = stager.review_bundle_workspace_files_with_errors(
        "windows-xp-native-x86",
        {"review_bundle": {"manifest": {"file": "../bundle.json"}}},
        bundle_dir=tmp_path,
    )

    assert files == set()
    assert errors == [
        "windows-xp-native-x86 staged upload review_bundle manifest.file "
        "must be an exact safe file name, got '../bundle.json'"
    ]

    manifest = tmp_path / "bundle-manifest.json"
    record = {"review_bundle": {"manifest": {"file": manifest.name}}}
    manifest.write_bytes(b"\xff\xfe")

    files, errors = stager.review_bundle_workspace_files_with_errors(
        "windows-xp-native-x86",
        record,
        bundle_dir=tmp_path,
    )

    assert files == set()
    assert any(
        "windows-xp-native-x86 staged upload review_bundle manifest is not readable JSON: "
        "bundle-manifest.json" in error
        for error in errors
    )

    manifest.write_text("[]\n", encoding="utf-8")

    files, errors = stager.review_bundle_workspace_files_with_errors(
        "windows-xp-native-x86",
        record,
        bundle_dir=tmp_path,
    )

    assert files == set()
    assert errors == [
        "windows-xp-native-x86 staged upload review_bundle manifest must be a JSON object: "
        "bundle-manifest.json"
    ]


def test_stage_xp_native_evidence_upload_rejects_non_string_artifact_hash_key() -> None:
    stager = _load_stager()
    record = {"artifact_sha256": {True: "0" * 64}}

    errors = stager.check_source_hashes("windows-xp-native-x86", record, {})

    assert (
        "windows-xp-native-x86 staged upload artifact_sha256 keys "
        "must be strings, got True"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_non_string_manifest_file_entry(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    manifest = tmp_path / "bundle-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "bundle_type": "windows-xp-native-host-evidence",
                "artifacts": [{"file": True}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    files, errors = stager.review_bundle_workspace_files_with_errors(
        "windows-xp-native-x86",
        {"review_bundle": {"manifest": {"file": manifest.name}}},
        bundle_dir=tmp_path,
    )

    assert files == set()
    assert (
        "windows-xp-native-x86 staged upload review_bundle manifest file entries "
        "must be strings, got True"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_unsafe_manifest_file_entry(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    manifest = tmp_path / "bundle-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "bundle_type": "windows-xp-native-host-evidence",
                "smoke_evidence": [{"file": "../xp-smoke.log"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    files, errors = stager.review_bundle_workspace_files_with_errors(
        "windows-xp-native-x86",
        {"review_bundle": {"manifest": {"file": manifest.name}}},
        bundle_dir=tmp_path,
    )

    assert files == set()
    assert (
        "windows-xp-native-x86 staged upload review_bundle manifest file entries "
        "must be safe relative paths, got '../xp-smoke.log'"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_review_bundle_content_mismatch(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = HISTORICAL_ACCEPTED_RECORD_TAG
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    final_record = evidence_output / f"platform-verified-evidence-{target}-final.json"
    _write_xp_final_record(final_record, target, assets, evidence_output)
    record = json.loads(final_record.read_text(encoding="utf-8"))
    archive_name = f"xp-native-evidence-bundle-{target}-{tag}.zip"
    archive_path = evidence_output / archive_name
    archive_path.write_text("not a readable XP review bundle\n", encoding="utf-8")
    record["review_bundle"]["archive"]["sha256"] = _sha256(archive_path)
    record["review_bundle"]["archive"]["size_bytes"] = archive_path.stat().st_size
    final_record.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any(
        "staged upload review bundle failed re-finalization" in error
        and "review bundle archive is not a readable ZIP" in error
        for error in errors
    )


def test_stage_xp_native_evidence_upload_requires_final_record_asset_review(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    captured: dict[str, Any] = {}

    def fake_review_bundle_checker(**kwargs: Any) -> list[str]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(stager, "check_platform_review_bundle_artifacts", fake_review_bundle_checker)

    errors = stager.check_review_bundle_artifacts(
        "windows-xp-native-x86",
        "v1.0.2",
        {"target": "windows-xp-native-x86"},
        bundle_dir=tmp_path,
    )

    assert errors == []
    assert captured["require_final_record_assets"] is True
    assert captured["required_targets"] == ("windows-xp-native-x86",)
    assert captured["required_release_tag"] == "v1.0.2"


def test_stage_xp_native_evidence_upload_rejects_noncanonical_final_record(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = HISTORICAL_ACCEPTED_RECORD_TAG
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    final_record = evidence_output / f"platform-verified-evidence-{target}-final.json"
    _write_xp_final_record(final_record, target, assets, evidence_output)
    record = json.loads(final_record.read_text(encoding="utf-8"))
    final_record.write_bytes((json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert (
        f"{target} finalized accepted record failed strict validation: "
        f"{target} finalized accepted record must use canonical sorted JSON: "
        f"platform-verified-evidence-{target}-final.json"
    ) in errors


def test_stage_xp_native_check_final_record_rejects_symlinked_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    target = "windows-xp-native-x86"
    evidence_parent = tmp_path / "linked-evidence"
    evidence_output = evidence_parent / "evidence-output"
    evidence_output.mkdir(parents=True)
    final_record = evidence_output / f"platform-verified-evidence-{target}-final.json"
    final_record.write_text("{}", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == evidence_parent

    monkeypatch.setattr(type(evidence_output), "is_symlink", fake_is_symlink)

    errors, record = stager.check_final_record(target, "v1.0.2", final_record)

    assert record is None
    assert errors == [
        f"{target} finalized accepted record path must not contain symlinked directories: {evidence_parent}"
    ]


def test_stage_xp_native_evidence_upload_rejects_release_source_file_set_drift() -> None:
    stager = _load_stager()
    record = {
        "release_asset_source": {
            "contains_files": [
                "expected.zip",
                "platform-verified-evidence-windows-xp-native-x86-final.json",
            ],
        },
    }
    sources = {
        "expected.zip": Path("expected.zip"),
        "unexpected.txt": Path("unexpected.txt"),
    }

    errors = stager.check_release_source_file_set("windows-xp-native-x86", record, sources)

    assert (
        "windows-xp-native-x86 staged upload missing release_asset_source files: "
        "['platform-verified-evidence-windows-xp-native-x86-final.json']"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload has files outside release_asset_source: ['unexpected.txt']"
        in errors
    )


def test_stage_xp_native_evidence_upload_rejects_unsafe_release_source_file_names() -> None:
    stager = _load_stager()
    record = {
        "release_asset_source": {
            "contains_files": [
                "expected.zip",
                "expected.zip",
                "nested/expected.zip",
                "C:expected.zip",
                r"C:\expected.zip",
                False,
            ],
        },
    }
    sources = {"expected.zip": Path("expected.zip")}

    errors = stager.check_release_source_file_set("windows-xp-native-x86", record, sources)

    assert any(
        "windows-xp-native-x86 finalized accepted record release_asset_source.contains_files "
        "entries must be exact safe file names" in error
        and "'nested/expected.zip'" in error
        and "'C:expected.zip'" in error
        and "'C:\\\\expected.zip'" in error
        and "False" in error
        for error in errors
    )
    assert (
        "windows-xp-native-x86 finalized accepted record release_asset_source.contains_files "
        "contains duplicate files: ['expected.zip']"
    ) in errors


def test_stage_xp_native_evidence_upload_source_map_rejects_cross_platform_paths(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    files = stager.source_map(
        tmp_path,
        {
            "expected.zip",
            "nested/expected.zip",
            "C:expected.zip",
            r"C:\expected.zip",
        },
    )

    assert files["expected.zip"] == tmp_path / "expected.zip"
    assert files["nested/expected.zip"] == Path("__invalid__")
    assert files["C:expected.zip"] == Path("__invalid__")
    assert files[r"C:\expected.zip"] == Path("__invalid__")


def test_stage_xp_native_evidence_upload_rejects_symlinked_source_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)

    def fake_is_symlink(path: Path) -> bool:
        return path in {assets, evidence_output}

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert f"XP native asset directory must not be a symlink: {assets}" in errors
    assert f"XP evidence output directory must not be a symlink: {evidence_output}" in errors


def test_stage_xp_native_evidence_upload_rejects_file_shaped_source_directories(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    assets = tmp_path / "assets.zip"
    evidence_output = tmp_path / "xp-evidence-output.zip"
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert f"XP native asset directory must be a directory path, got {assets.as_posix()!r}" in errors
    assert (
        f"XP evidence output directory must be a directory path, got {evidence_output.as_posix()!r}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_reserved_workspace_source_directories() -> None:
    stager = _load_stager()
    assets = Path(".github") / "windows-xp-native-x86" / "v1.0.2" / "artifacts"
    evidence_output = Path(".agents") / "windows-xp-native-x86" / "v1.0.2" / "evidence"

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=Path("xp-evidence-upload"),
    )

    assert (
        "XP native asset directory must not point inside "
        f"reserved workspace directory '.github': {assets}"
    ) in errors
    assert (
        "XP evidence output directory must not point inside "
        f"reserved workspace directory '.agents': {evidence_output}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_symlinked_source(monkeypatch) -> None:
    stager = _load_stager()
    sources = {
        "expected.zip": Path("expected.zip"),
        "platform-verified-evidence-windows-xp-native-x86-final.json": Path(
            "platform-verified-evidence-windows-xp-native-x86-final.json"
        ),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path.name == "platform-verified-evidence-windows-xp-native-x86-final.json"

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source must not be a symlink: "
        "platform-verified-evidence-windows-xp-native-x86-final.json"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_non_path_source_value() -> None:
    stager = _load_stager()
    sources = {
        "expected.zip": Path("expected.zip"),
        "platform-verified-evidence-windows-xp-native-x86-final.json": True,
    }

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source "
        "platform-verified-evidence-windows-xp-native-x86-final.json "
        "path must be a pathlib.Path, got True"
    ) in errors
    assert not any("reserved workspace" in error and "True" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_symlinked_source_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    source_parent = tmp_path / "linked-source"
    sources = {
        "expected.zip": source_parent / "expected.zip",
        "platform-verified-evidence-windows-xp-native-x86-final.json": (
            source_parent / "platform-verified-evidence-windows-xp-native-x86-final.json"
        ),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path == source_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source expected.zip "
        f"path must not contain symlinked directories: {source_parent}"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload source "
        "platform-verified-evidence-windows-xp-native-x86-final.json "
        f"path must not contain symlinked directories: {source_parent}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_reserved_workspace_source_file() -> None:
    stager = _load_stager()
    source = Path(".git") / "expected.zip"
    sources = {
        "expected.zip": source,
    }

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source expected.zip must not point inside "
        f"reserved workspace directory '.git': {source}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload"
    out_dir.mkdir()

    def fake_is_symlink(path: Path) -> bool:
        return path == out_dir

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        f"windows-xp-native-x86 staged upload output directory must not be a symlink: {out_dir}"
    ]


def test_stage_xp_native_evidence_upload_rejects_file_shaped_output_directory(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload.zip"

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=False,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output directory "
        f"must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_stage_xp_native_evidence_upload_rejects_non_path_output_directory() -> None:
    stager = _load_stager()

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=True,
        force=False,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output directory must be a pathlib.Path, got True"
    ]


def test_stage_xp_native_evidence_upload_path_helpers_reject_non_path_values() -> None:
    stager = _load_stager()

    assert stager.check_destination_path(
        "windows-xp-native-x86",
        True,
        "expected.zip",
    ) == [
        "windows-xp-native-x86 staged upload destination expected.zip must be a pathlib.Path, got True"
    ]
    assert stager.check_path_parent_symlinks(False, "XP native asset directory") == [
        "XP native asset directory must be a pathlib.Path, got False"
    ]
    assert stager.check_directory_path_hint("upload", "staged upload output directory") == [
        "staged upload output directory must be a pathlib.Path, got 'upload'"
    ]
    assert stager.check_path_not_reserved_workspace_root(0, "staged upload output directory") == [
        "staged upload output directory must be a pathlib.Path, got 0"
    ]
    assert stager.check_staging_path_separation(
        "windows-xp-native-x86",
        assets_dir=True,
        evidence_output_dir="evidence",
        out_dir=False,
    ) == [
        "windows-xp-native-x86 XP native asset directory must be a pathlib.Path, got True",
        "windows-xp-native-x86 XP evidence output directory must be a pathlib.Path, got 'evidence'",
        "windows-xp-native-x86 staged upload output directory must be a pathlib.Path, got False",
    ]
    assert stager.paths_overlap(True, Path("upload")) is True
    assert stager.path_contains(True, Path("upload")) is False


def test_stage_xp_native_evidence_upload_rejects_reserved_workspace_output_directory() -> None:
    stager = _load_stager()
    out_dir = Path(".codex") / "xp-evidence-upload"

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output directory must not point inside "
        f"reserved workspace directory '.codex': {out_dir}"
    ]
    assert not out_dir.exists()


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_parent = tmp_path / "linked-upload"
    out_dir = out_parent / "xp-evidence-upload"

    def fake_is_symlink(path: Path) -> bool:
        return path == out_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output directory "
        f"path must not contain symlinked directories: {out_parent}"
    ]


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_child(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload"
    out_dir.mkdir()
    child = out_dir / "old-upload-file.zip"
    child.write_text("old upload\n", encoding="utf-8")

    def fake_is_symlink(path: Path) -> bool:
        return path == child

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output must not contain symlinks: old-upload-file.zip"
    ]
    assert child.exists()


def test_stage_xp_native_evidence_upload_rejects_unsafe_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    symlink_destination = tmp_path / "xp-evidence-upload" / "expected.zip"
    directory_destination = tmp_path / "xp-evidence-upload" / "expected-manifest.json"
    directory_destination.mkdir(parents=True)

    def fake_is_symlink(path: Path) -> bool:
        return path == symlink_destination

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    assert stager.check_destination_path(
        "windows-xp-native-x86",
        symlink_destination,
        "expected.zip",
    ) == [
        "windows-xp-native-x86 staged upload destination must not be a symlink: expected.zip"
    ]
    assert stager.check_destination_path(
        "windows-xp-native-x86",
        directory_destination,
        "expected-manifest.json",
    ) == [
        "windows-xp-native-x86 staged upload destination must be a regular file: expected-manifest.json"
    ]


def test_stage_xp_native_evidence_upload_rejects_staged_output_drift(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload"
    out_dir.mkdir()
    (out_dir / "expected.zip").write_text("drifted artifact\n", encoding="utf-8")
    (out_dir / "unexpected.txt").write_text("unexpected upload file\n", encoding="utf-8")
    (out_dir / "nested").mkdir()
    expected_hashes = {
        "expected.zip": hashlib.sha256(b"expected artifact\n").hexdigest(),
        "missing-manifest.json": hashlib.sha256(b"missing manifest\n").hexdigest(),
    }

    errors = stager.check_staged_output(
        "windows-xp-native-x86",
        out_dir=out_dir,
        expected_hashes=expected_hashes,
    )

    assert (
        "windows-xp-native-x86 staged upload output contains non-file entries: ['nested']"
        in errors
    )
    assert (
        "windows-xp-native-x86 staged upload output missing expected files: "
        "['missing-manifest.json']"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload output contains unexpected files: ['unexpected.txt']"
        in errors
    )
    assert "windows-xp-native-x86 staged upload output SHA-256 mismatch: expected.zip" in errors


def test_stage_xp_native_evidence_upload_rejects_missing_expected_file(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{checker.read_project_version()}"
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert errors
    assert any(f"{target} staged upload missing expected files" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_invalid_final_record(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{checker.read_project_version()}"
    assets = _xp_assets_dir(tmp_path, target, tag)
    evidence_output = _xp_evidence_output_dir(tmp_path, target, tag)
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    (evidence_output / f"platform-verified-evidence-{target}-final.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any(
        f"{target} finalized accepted record failed strict validation" in error
        for error in errors
    )


def test_stage_xp_native_evidence_upload_rejects_unscoped_source_directories(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert (
        "XP native asset directory must include target path segment "
        f"'windows-xp-native-x86', got {assets.as_posix()!r}"
    ) in errors
    assert (
        "XP native asset directory must include release_tag path segment "
        f"'v1.0.2', got {assets.as_posix()!r}"
    ) in errors
    assert (
        "XP evidence output directory must include target path segment "
        f"'windows-xp-native-x86', got {evidence_output.as_posix()!r}"
    ) in errors
    assert (
        "XP evidence output directory must include release_tag path segment "
        f"'v1.0.2', got {evidence_output.as_posix()!r}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_nonadjacent_target_release_scope(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    assets = tmp_path / "native-dist" / "windows-xp" / "v1.0.2" / "windows-xp-native-x86"
    evidence_output = tmp_path / "xp-evidence-output" / "v1.0.2" / "windows-xp-native-x86"
    assets.mkdir(parents=True)
    evidence_output.mkdir(parents=True)

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert (
        "XP native asset directory must include adjacent target/release path segment "
        f"windows-xp-native-x86/v1.0.2, got {assets.as_posix()!r}"
    ) in errors
    assert (
        "XP evidence output directory must include adjacent target/release path segment "
        f"windows-xp-native-x86/v1.0.2, got {evidence_output.as_posix()!r}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_overlapping_staging_output_path(tmp_path: Path) -> None:
    stager = _load_stager()
    target = "windows-xp-native-x86"
    assets = tmp_path / "xp-staged" / "assets"
    evidence_output = tmp_path / "xp-staged" / "evidence-output"
    assets.mkdir(parents=True)
    evidence_output.mkdir()

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=assets / "xp-evidence-upload",
    )

    assert (
        "windows-xp-native-x86 XP native asset directory and staged upload output "
        "directory must be separate roots"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_asset_evidence_overlap(tmp_path: Path) -> None:
    stager = _load_stager()
    target = "windows-xp-native-x64"
    root = tmp_path / "xp-staged"
    assets = root / "assets"
    evidence_output = assets / "xp-evidence-output"
    evidence_output.mkdir(parents=True)

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=root / "xp-evidence-upload",
    )

    assert (
        "windows-xp-native-x64 XP native asset directory and evidence output directory "
        "must be separate roots"
    ) in errors


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _xp_assets_dir(tmp_path: Path, target: str, tag: str) -> Path:
    return tmp_path / "native-dist" / "windows-xp" / target / tag


def _xp_evidence_output_dir(tmp_path: Path, target: str, tag: str) -> Path:
    return tmp_path / "xp-evidence-output" / target / tag


def _write_xp_final_record(path: Path, target: str, assets_dir: Path, evidence_output_dir: Path) -> None:
    assert target == "windows-xp-native-x86"
    review_helpers = _load_platform_review_bundle_helpers()
    bundle_helpers = _load_finalize_helpers()
    record = review_helpers._finalized_xp_record(evidence_output_dir)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            (assets_dir / str(name)).write_bytes(bundle_helpers._artifact_payload(str(name)))
    path.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_stager() -> Any:
    path = Path("scripts/stage_xp_native_evidence_upload.py")
    spec = importlib.util.spec_from_file_location("stage_xp_native_evidence_upload", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_review_bundle_helpers() -> Any:
    path = Path("tests/test_platform_review_bundle_artifacts.py")
    spec = importlib.util.spec_from_file_location("platform_review_bundle_stage_xp_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_helpers() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_evidence_stage_xp_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker() -> Any:
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
