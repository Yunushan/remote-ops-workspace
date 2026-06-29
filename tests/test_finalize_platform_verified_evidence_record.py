from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


def test_finalize_platform_verified_evidence_record_binds_review_bundle(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    artifact_archive_files = _attach_artifact_files(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_path,
        target,
        candidate["artifact_sha256"],
        builder_evidence=_candidate_builder_evidence_path(target, release_tag),
    )
    smoke_sha = _sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "release_asset_source": candidate["release_asset_source"],
            "validated_commands": _linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": _file_record(builder_path),
            "smoke_evidence": [_smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)],
            "candidate_record": _file_record(candidate_path),
            "artifacts": _artifact_records(candidate),
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
    assert record["review_bundle"]["bundle_type"] == "extended-linux-native-evidence"
    assert record["review_bundle"]["manifest"]["file"] == manifest.name
    assert record["review_bundle"]["manifest"]["sha256"] == _sha256(manifest)
    assert record["review_bundle"]["archive"]["sha256"] == _sha256(archive)
    assert record["review_bundle"]["sha256s"]["sha256"] == _sha256(sidecar)
    assert record["review_bundle"]["release_asset_urls"] == [
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{manifest.name}",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{archive.name}",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{sidecar.name}",
    ]
    assert (
        record["finalized_record_release_asset_url"]
        == f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/"
        f"platform-verified-evidence-{target}-final.json"
    )
    assert manifest.name in record["release_asset_source"]["contains_files"]
    assert archive.name in record["release_asset_source"]["contains_files"]
    assert sidecar.name in record["release_asset_source"]["contains_files"]
    assert (
        f"platform-verified-evidence-{target}-final.json"
        in record["release_asset_source"]["contains_files"]
    )


def test_finalize_platform_verified_evidence_record_rejects_symlinked_candidate_record(
    tmp_path: Path, monkeypatch
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )

    def fake_is_symlink(self: Path) -> bool:
        return self.name == candidate_path.name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert f"candidate evidence record file must not be a symlink: {candidate_path}" in errors


def test_finalize_platform_verified_evidence_record_rejects_already_finalized_candidate(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
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

    assert record == {}
    assert (
        "candidate evidence record must be unfinalized before finalization; "
        "remove fields: ['finalized_record_release_asset_url', 'review_bundle']"
    ) in errors


def test_finalize_platform_verified_evidence_record_requires_strict_candidate_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    monkeypatch.setattr(
        finalizer,
        "check_unfinalized_candidate_record",
        lambda candidate: ["candidate strict validation sentinel failure"],
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "candidate strict validation sentinel failure" in errors


def test_finalize_platform_verified_evidence_record_rejects_mixed_bundle_directories(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    copied_dir = tmp_path / "copied-sidecar"
    copied_dir.mkdir()
    copied_sidecar = copied_dir / sidecar.name
    copied_sidecar.write_text(sidecar.read_text(encoding="utf-8"), encoding="utf-8")

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=copied_sidecar,
    )

    assert record == {}
    assert any("review bundle files must be siblings in one directory" in error for error in errors)


def test_finalize_platform_verified_evidence_record_rejects_xp_candidate_name_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    copied_candidate = tmp_path / f"platform-verified-evidence-{target}-copy.json"
    copied_candidate.write_bytes(candidate_path.read_bytes())
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["candidate_record"] = _file_record(copied_candidate)
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    _replace_archive_entries(
        archive,
        replacements={
            manifest.name: manifest.read_bytes(),
            copied_candidate.name: copied_candidate.read_bytes(),
        },
        remove={candidate_path.name},
    )
    _rewrite_sidecar(sidecar, manifest=manifest, archive=archive)

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=copied_candidate,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        f"candidate evidence record file name must be platform-verified-evidence-{target}.json, "
        f"got 'platform-verified-evidence-{target}-copy.json'"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_wrong_output_file_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    wrong_output = tmp_path / "finalized-record.json"

    rc = finalizer.main(
        [
            "--candidate-record",
            str(candidate_path),
            "--bundle-manifest",
            str(manifest),
            "--bundle-archive",
            str(archive),
            "--bundle-sha256s",
            str(sidecar),
            "--out",
            str(wrong_output),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not wrong_output.exists()
    assert (
        "finalize platform evidence record: finalized platform evidence record output file name must be "
        "platform-verified-evidence-windows-xp-native-x86-final.json, got 'finalized-record.json'"
    ) in captured.err


def test_finalize_platform_verified_evidence_record_requires_output_for_registry_append(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    registry = tmp_path / "platform_verified_evidence.json"

    rc = finalizer.main(
        [
            "--candidate-record",
            str(candidate_path),
            "--bundle-manifest",
            str(manifest),
            "--bundle-archive",
            str(archive),
            "--bundle-sha256s",
            str(sidecar),
            "--append-registry",
            "--registry",
            str(registry),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not registry.exists()
    assert (
        "finalize platform evidence record: --append-registry requires --out "
        "so the finalized release artifact is written before registry append"
    ) in captured.err


def test_finalize_platform_verified_evidence_record_rejects_output_outside_bundle_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    output_dir = tmp_path / "copied-final-record"
    output_dir.mkdir()
    output = output_dir / f"platform-verified-evidence-{target}-final.json"

    rc = finalizer.main(
        [
            "--candidate-record",
            str(candidate_path),
            "--bundle-manifest",
            str(manifest),
            "--bundle-archive",
            str(archive),
            "--bundle-sha256s",
            str(sidecar),
            "--out",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert not output.exists()
    assert (
        "finalize platform evidence record: finalized platform evidence record output file "
        "must be written next to review bundle files:"
    ) in captured.err


def test_finalize_platform_verified_evidence_record_rejects_symlinked_input_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    finalizer = _load_finalizer()
    linked_parent = tmp_path / "linked-bundle"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    for label, filename in (
        ("candidate evidence record", "platform-verified-evidence-linux-i386.json"),
        ("review bundle manifest", "extended-linux-evidence-bundle-linux-i386-v1.0.2.json"),
        ("review bundle archive", "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip"),
        ("review bundle SHA-256 sidecar", "extended-linux-evidence-bundle-linux-i386-v1.0.2-SHA256SUMS.txt"),
    ):
        errors: list[str] = []
        path = linked_parent / "bundle" / filename

        assert not finalizer.check_input_file(path, label, errors)
        assert errors == [
            f"{label} file path must not contain symlinked directories: {linked_parent}"
        ]


def test_finalize_platform_verified_evidence_record_rejects_unsafe_output_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    finalizer = _load_finalizer()
    output = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    output.write_text("{}\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == output

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = finalizer.check_text_output_path(
        output,
        "finalized platform evidence record output file",
    )

    assert errors == [
        f"finalized platform evidence record output file must not be a symlink: {output}"
    ]


def test_finalize_platform_verified_evidence_record_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    finalizer = _load_finalizer()
    output_parent = tmp_path / "linked-output" / "records"
    output = output_parent / "platform-verified-evidence-linux-i386-final.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path / "linked-output"

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = finalizer.check_text_output_path(
        output,
        "finalized platform evidence record output file",
    )

    assert errors == [
        "finalized platform evidence record output file directory path must not contain symlinked directories: "
        f"{tmp_path / 'linked-output'}"
    ]


def test_finalize_platform_verified_evidence_record_rejects_archive_missing_candidate(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    artifact_archive_files = _attach_artifact_files(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_path,
        target,
        candidate["artifact_sha256"],
        builder_evidence=_candidate_builder_evidence_path(target, release_tag),
    )
    smoke_sha = _sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "release_asset_source": candidate["release_asset_source"],
            "validated_commands": _linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": _file_record(builder_path),
            "smoke_evidence": [_smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)],
            "candidate_record": _file_record(candidate_path),
            "artifacts": _artifact_records(candidate),
        },
        archive_files={
            **artifact_archive_files,
            builder_path.name: builder_path.read_bytes(),
            smoke_path.name: smoke_path.read_bytes(),
        },
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle archive missing expected entries: ['platform-verified-evidence-linux-i386.json']" in errors


def test_finalize_platform_verified_evidence_record_rejects_symlinked_archive_entry(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    _rewrite_archive_entry_as_symlink(archive, "xp-evidence.json")
    _rewrite_sidecar(sidecar, manifest=manifest, archive=archive)

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle archive entries must not be symlinks: ['xp-evidence.json']" in errors


def test_finalize_platform_verified_evidence_record_rejects_unsafe_archive_entry_names() -> None:
    finalizer = _load_finalizer()
    absolute = zipfile.ZipInfo("/absolute.txt")
    traversal = zipfile.ZipInfo("../escape.txt")
    windows_drive = zipfile.ZipInfo("C:/escape.txt")
    backslash = zipfile.ZipInfo("safe.txt")
    backslash.filename = "nested\\escape.txt"

    errors = finalizer.check_archive_entry_safety([absolute, traversal, windows_drive, backslash])

    assert (
        "review bundle archive entries must use safe relative paths: "
        "['../escape.txt', '/absolute.txt', 'C:/escape.txt', 'nested\\\\escape.txt']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_weak_linux_smoke_log(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    artifact_archive_files = _attach_artifact_files(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    smoke_path.write_text("linux-i386 native smoke passed\n", encoding="utf-8")
    smoke_sha = _sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "release_asset_source": candidate["release_asset_source"],
            "validated_commands": _linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": _file_record(builder_path),
            "smoke_evidence": [_smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)],
            "candidate_record": _file_record(candidate_path),
            "artifacts": _artifact_records(candidate),
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

    assert record == {}
    assert any(
        "linux-i386 archived native_smoke evidence missing required line: "
        "native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        f"--builder-evidence {_candidate_builder_evidence_path(target, release_tag)}"
        in error
        for error in errors
    )


def test_finalize_platform_verified_evidence_record_rejects_linux_builder_smoke_identity_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    artifact_archive_files = _attach_artifact_files(candidate)
    candidate["builder_identity"]["host_identity"]["evidence_run_id"] = "linux-i386-1-0-2-run-99999"
    candidate["builder_identity"]["host_identity"]["observed_at_utc"] = "2026-06-20T12:30:00Z"
    builder_sha = helpers._json_sha256(candidate["builder_identity"])
    candidate["builder_identity_sha256"] = builder_sha
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    _sync_linux_source_record(candidate, "builder_identity", builder_sha, builder_path.stat().st_size)
    _write_linux_smoke_evidence(
        smoke_path,
        target,
        candidate["artifact_sha256"],
        builder_evidence=_candidate_builder_evidence_path(target, release_tag),
    )
    smoke_sha = _sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "release_asset_source": candidate["release_asset_source"],
            "validated_commands": _linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": _file_record(builder_path),
            "smoke_evidence": [_smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)],
            "candidate_record": _file_record(candidate_path),
            "artifacts": _artifact_records(candidate),
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

    assert record == {}
    assert (
        "linux-i386 archived native_smoke evidence native installer smoke evidence run id must match "
        "builder_identity.host_identity.evidence_run_id 'linux-i386-1-0-2-run-99999', "
        "got 'linux-i386-1-0-2-run-12345'"
    ) in errors
    assert (
        "linux-i386 archived native_smoke evidence native installer smoke observed at utc must not be earlier than "
        "builder_identity.host_identity.observed_at_utc '2026-06-20T12:30:00Z', "
        "got '2026-06-20T12:00:00Z'"
    ) in errors


def test_finalize_platform_verified_evidence_record_binds_xp_review_bundle(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
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
    assert record["review_bundle"]["bundle_type"] == "windows-xp-native-host-evidence"
    assert record["review_bundle"]["archive"]["file"] == archive.name
    assert record["review_bundle"]["release_asset_urls"] == [
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{manifest.name}",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{archive.name}",
        f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/{sidecar.name}",
    ]
    assert (
        record["finalized_record_release_asset_url"]
        == f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}/"
        f"platform-verified-evidence-{target}-final.json"
    )
    assert manifest.name in record["release_asset_source"]["contains_files"]
    assert archive.name in record["release_asset_source"]["contains_files"]
    assert sidecar.name in record["release_asset_source"]["contains_files"]
    assert (
        f"platform-verified-evidence-{target}-final.json"
        in record["release_asset_source"]["contains_files"]
    )


def test_finalize_platform_verified_evidence_record_rejects_xp_workflow_input_drift(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["workflow_inputs"]["assets_dir"] = "native-dist/windows-xp/windows-xp-native-x86/v1.0.3"
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
    _rewrite_sidecar(sidecar, manifest=manifest, archive=archive)

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle manifest workflow_inputs must match candidate record" in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_summary_mismatch(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        evidence_mutator=lambda evidence: evidence["os"].update({"service_pack": "SP2"}),
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle archive XP evidence summary must match candidate xp_evidence_summary" in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_smoke_hash_mismatch(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)

    def corrupt_smoke_hash(evidence: dict[str, Any]) -> None:
        smoke_results = evidence["smoke_results"]
        assert isinstance(smoke_results, list)
        smoke_results[0]["evidence_sha256"] = "0" * 64

    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        evidence_mutator=corrupt_smoke_hash,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        "review bundle archive XP smoke evidence hashes must match candidate xp_smoke_evidence_sha256"
        in errors
    )


def test_finalize_platform_verified_evidence_record_rejects_xp_archived_smoke_binding_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x64"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)

    def corrupt_smoke_binding(smoke_id: str, text: str) -> str:
        if smoke_id == "cli_launch":
            return text.replace("xp smoke id: cli_launch", "xp smoke id: loopback_profile_dry_run")
        return text

    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        smoke_text_mutator=corrupt_smoke_binding,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file smoke-id binding must be "
        "['cli_launch'], got ['loopback_profile_dry_run']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_archived_smoke_release_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x64"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)

    def corrupt_smoke_release(smoke_id: str, text: str) -> str:
        if smoke_id == "cli_launch":
            return text.replace("xp smoke release: v1.0.2", "xp smoke release: v9.9.9")
        return text

    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        smoke_text_mutator=corrupt_smoke_release,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file release binding must be "
        "['v1.0.2'], got ['v9.9.9']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_archived_smoke_source_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x64"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)

    def corrupt_smoke_source(smoke_id: str, text: str) -> str:
        if smoke_id == "cli_launch":
            return text.replace(
                f"xp smoke source head sha: {'a' * 40}",
                f"xp smoke source head sha: {'b' * 40}",
            )
        return text

    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        smoke_text_mutator=corrupt_smoke_source,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file source head SHA binding "
        f"must be [{repr('a' * 40)}], got [{repr('b' * 40)}]"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_archived_security_smoke_gap(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x64"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)

    def remove_security_line(smoke_id: str, text: str) -> str:
        if smoke_id == "modern_defaults_unchanged":
            return text.replace("modern TLS preferred: TLS 1.3\n", "")
        return text

    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
        smoke_text_mutator=remove_security_line,
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert (
        "windows-xp-native-x64 smoke result modern_defaults_unchanged evidence_file "
        "missing security proof line: modern TLS preferred: TLS 1.3"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_manifest_host_identity_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["host_identity"]["host_label"] = "xp-x86-lab-02"
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle manifest host_identity must match candidate xp_evidence_summary" in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_manifest_toolchain_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["toolchain"]["current_python_pyqt6_stack"] = True
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle manifest toolchain must match candidate xp_evidence_summary" in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_manifest_security_mismatch(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x64"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
        tmp_path,
        candidate,
        target=target,
        release_tag=release_tag,
    )
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["security"]["modern_defaults_unchanged"] = False
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle manifest security must match candidate xp_evidence_summary" in errors


def test_finalize_platform_verified_evidence_record_rejects_candidate_bundle_mismatch(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    release_tag = "v1.0.2"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    artifact_archive_files = _attach_artifact_files(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    builder_path = tmp_path / "builder-identity-linux-i386.json"
    builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
    smoke_path = tmp_path / "native-smoke-linux-i386.log"
    _write_linux_smoke_evidence(
        smoke_path,
        target,
        candidate["artifact_sha256"],
        builder_evidence=_candidate_builder_evidence_path(target, release_tag),
    )
    smoke_sha = _sha256(smoke_path)
    candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
    _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
    manifest_candidate = dict(candidate)
    manifest_candidate["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    bundled_candidate_path = tmp_path / "bundled-platform-verified-evidence-linux-i386.json"
    bundled_candidate_path.write_text(json.dumps(manifest_candidate, indent=2) + "\n", encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
        bundle_type="extended-linux-native-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "release_asset_source": candidate["release_asset_source"],
            "validated_commands": _linux_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "workflow_run_url": candidate["workflow_run_url"],
            "runner_labels": candidate["runner_labels"],
            "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
            "builder_evidence": _file_record(builder_path),
            "smoke_evidence": [_smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)],
            "candidate_record": _file_record(bundled_candidate_path, name=candidate_path.name),
            "artifacts": _artifact_records(candidate),
        },
        archive_files={
            **artifact_archive_files,
            builder_path.name: builder_path.read_bytes(),
            smoke_path.name: smoke_path.read_bytes(),
            candidate_path.name: bundled_candidate_path.read_bytes(),
        },
    )

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert "review bundle manifest candidate_record.sha256 must match platform-verified-evidence-linux-i386.json" in errors
    assert "review bundle archive candidate_record must match candidate evidence record" in errors


def test_finalize_platform_verified_evidence_record_rejects_placeholder_validated_command() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "extended-linux-native-evidence",
        "validated_commands": [
            candidate["native_build_command"],
            candidate["native_smoke_command"],
            candidate["local_evidence_preflight_command"],
            candidate["staged_upload_command"],
            (
                "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
                "--assets-dir <artifact-dir> --tag v1.0.2 --strict"
            ),
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert any("validated_commands entry must be concrete" in error for error in errors)
    assert "review bundle manifest validated_commands must match Linux candidate command provenance" in errors


def test_finalize_platform_verified_evidence_record_rejects_missing_linux_local_preflight_command() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "extended-linux-native-evidence",
        "validated_commands": [
            candidate["native_build_command"],
            candidate["native_smoke_command"],
            candidate["staged_upload_command"],
            candidate["artifact_validation_command"],
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert (
        "review bundle manifest validated_commands must include exactly one local evidence preflight command"
    ) in errors
    assert "review bundle manifest validated_commands must match Linux candidate command provenance" in errors


def test_finalize_platform_verified_evidence_record_rejects_missing_staged_upload_command() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "extended-linux-native-evidence",
        "validated_commands": [
            candidate["native_build_command"],
            candidate["native_smoke_command"],
            candidate["local_evidence_preflight_command"],
            candidate["artifact_validation_command"],
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert (
        "review bundle manifest validated_commands must include exactly one staged upload command"
    ) in errors
    assert "review bundle manifest validated_commands must match Linux candidate command provenance" in errors


def test_finalize_platform_verified_evidence_record_rejects_release_asset_url_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "promotion_config_sha256": candidate["promotion_config_sha256"],
        "release_asset_urls": [*candidate["release_asset_urls"], "https://github.com/example/other/releases/download/v1.0.2/extra.zip"],
        "validated_commands": _linux_validated_commands(candidate),
        "candidate_record": _file_record(candidate_path),
        "artifacts": _artifact_records(candidate),
    }

    errors = finalizer.check_candidate_manifest_binding(candidate_path, candidate, manifest)

    assert "review bundle manifest release_asset_urls must match candidate record" in errors


def test_finalize_platform_verified_evidence_record_rejects_linux_release_source_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    release_source = dict(candidate["release_asset_source"])
    release_source["head_sha"] = "b" * 40
    manifest = {
        "bundle_type": "extended-linux-native-evidence",
        "promotion_config_sha256": candidate["promotion_config_sha256"],
        "release_asset_urls": candidate["release_asset_urls"],
        "release_asset_source": release_source,
        "validated_commands": _linux_validated_commands(candidate),
        "workflow": candidate["workflow"],
        "workflow_inputs": candidate["workflow_inputs"],
        "workflow_run_url": candidate["workflow_run_url"],
        "runner_labels": candidate["runner_labels"],
        "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
        "builder_evidence": {
            "file": "builder-identity-linux-i386.json",
            "sha256": candidate["builder_identity_sha256"],
            "size_bytes": 100,
        },
        "smoke_evidence": [
            {
                "id": "native_smoke",
                "file": "native-smoke-linux-i386.log",
                "sha256": candidate["linux_smoke_evidence_sha256"]["native_smoke"],
                "size_bytes": 100,
            }
        ],
        "candidate_record": _file_record(candidate_path),
        "artifacts": _artifact_records(candidate),
    }

    errors = finalizer.check_candidate_manifest_binding(candidate_path, candidate, manifest)

    assert "review bundle manifest release_asset_source must match candidate record" in errors


def test_finalize_platform_verified_evidence_record_rejects_candidate_release_source_extra_file(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    source = candidate["release_asset_source"]
    assert isinstance(source, dict)
    source["contains_files"] = [*source["contains_files"], "operator-notes.txt"]
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
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

    assert record == {}
    assert (
        "candidate release_asset_source.contains_files has files outside native artifacts: "
        "['operator-notes.txt']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_candidate_release_source_finalization_only_files(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    source = candidate["release_asset_source"]
    assert isinstance(source, dict)
    source["contains_files"] = [
        *source["contains_files"],
        f"xp-native-evidence-bundle-{target}-{release_tag}.json",
        f"platform-verified-evidence-{target}-final.json",
    ]
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
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

    assert record == {}
    assert (
        "candidate release_asset_source.contains_files must not include "
        "finalization-only files before finalization: "
        f"['platform-verified-evidence-{target}-final.json', "
        f"'xp-native-evidence-bundle-{target}-{release_tag}.json']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_candidate_release_source_missing_artifact(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    missing_artifact = sorted(candidate["artifact_sha256"])[0]
    source = candidate["release_asset_source"]
    assert isinstance(source, dict)
    source["contains_files"] = [
        filename
        for filename in source["contains_files"]
        if filename != missing_artifact
    ]
    candidate_path, manifest, archive, sidecar = _write_xp_candidate_and_bundle(
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

    assert record == {}
    assert (
        "candidate release_asset_source.contains_files missing native artifacts: "
        f"['{missing_artifact}']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_path_qualified_candidate_release_url() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._linux_record("linux-i386")
    _unfinalized_candidate(candidate)
    candidate["release_asset_urls"][0] = candidate["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )
    expected_files = {
        "manifest": "extended-linux-evidence-bundle-linux-i386-v1.0.2.json",
        "archive": "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
        "sha256s": "extended-linux-evidence-bundle-linux-i386-v1.0.2-SHA256SUMS.txt",
    }

    bundle_errors, bundle_urls = finalizer.review_bundle_release_asset_urls(candidate, expected_files)
    final_errors, final_url = finalizer.finalized_record_release_asset_url(candidate)

    assert bundle_urls == []
    assert final_url == ""
    assert any("candidate release_asset_url file name must be an exact safe file name" in error for error in bundle_errors)
    assert any("candidate release_asset_url file name must be an exact safe file name" in error for error in final_errors)


def test_finalize_platform_verified_evidence_record_rejects_missing_xp_validation_command() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._xp_record("windows-xp-native-x86")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "windows-xp-native-host-evidence",
        "validated_commands": [
            candidate["local_evidence_preflight_command"],
            candidate["staged_upload_command"],
            candidate["artifact_validation_command"],
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert "review bundle manifest validated_commands must include exactly one XP evidence validation command" in errors
    assert "review bundle manifest validated_commands must match XP bundle validation commands" in errors


def test_finalize_platform_verified_evidence_record_rejects_missing_xp_local_preflight_command() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._xp_record("windows-xp-native-x86")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "windows-xp-native-host-evidence",
        "validated_commands": [
            candidate["native_evidence_validation_command"],
            candidate["staged_upload_command"],
            candidate["artifact_validation_command"],
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert (
        "review bundle manifest validated_commands must include exactly one local evidence preflight command"
    ) in errors
    assert "review bundle manifest validated_commands must match XP bundle validation commands" in errors


def test_finalize_platform_verified_evidence_record_rejects_xp_validation_command_drift() -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    candidate = helpers._xp_record("windows-xp-native-x86")
    _unfinalized_candidate(candidate)
    manifest = {
        "bundle_type": "windows-xp-native-host-evidence",
        "validated_commands": [
            "python scripts/check_xp_native_evidence.py --evidence other-xp-evidence.json --assets-dir native-dist/windows-xp",
            candidate["local_evidence_preflight_command"],
            candidate["staged_upload_command"],
            candidate["artifact_validation_command"],
            "python scripts/check_platform_verified_evidence.py",
        ],
    }

    errors = finalizer.check_manifest_validated_commands(candidate, manifest)

    assert "review bundle manifest validated_commands must match XP bundle validation commands" in errors


def test_finalize_platform_verified_evidence_record_rejects_sidecar_mismatch(tmp_path: Path) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "windows-xp-native-x86"
    release_tag = "v1.0.2"
    candidate = helpers._xp_record(target)
    _unfinalized_candidate(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-windows-xp-native-x86.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        tmp_path,
        stem=f"xp-native-evidence-bundle-{target}-{release_tag}",
        bundle_type="windows-xp-native-host-evidence",
        target=target,
        release_tag=release_tag,
    )
    sidecar.write_text("0" * 64 + f"  {manifest.name}\n", encoding="utf-8")

    errors, record = finalizer.finalize_platform_verified_evidence_record(
        candidate_record=candidate_path,
        bundle_manifest=manifest,
        bundle_archive=archive,
        bundle_sha256s=sidecar,
    )

    assert record == {}
    assert any("review bundle SHA-256 sidecar missing entries" in error for error in errors)


def test_finalize_platform_verified_evidence_record_rejects_sidecar_extra_and_duplicate_lines(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    manifest = tmp_path / "review-bundle.json"
    archive = tmp_path / "review-bundle.zip"
    sidecar = tmp_path / "review-bundle-SHA256SUMS.txt"
    manifest.write_text("{}\n", encoding="utf-8")
    archive.write_bytes(b"bundle archive bytes")
    expected_manifest = f"{_sha256(manifest)}  {manifest.name}"
    expected_archive = f"{_sha256(archive)}  {archive.name}"
    sidecar.write_text(
        f"{expected_manifest}\n{expected_manifest}\n{expected_archive}\n{'0' * 64}  extra.zip\n",
        encoding="utf-8",
    )

    errors = finalizer.check_bundle_sidecar(sidecar, manifest, archive)

    assert f"review bundle SHA-256 sidecar contains unexpected entries: ['{'0' * 64}  extra.zip']" in errors
    assert f"review bundle SHA-256 sidecar contains duplicate entries: ['{expected_manifest}']" in errors


def test_finalize_platform_verified_evidence_record_rejects_duplicate_archive_entries(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    manifest = tmp_path / "review-bundle.json"
    archive = tmp_path / "review-bundle.zip"
    manifest.write_text(json.dumps({"bundle_type": "unknown"}) + "\n", encoding="utf-8")
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zipped:
            zipped.write(manifest, arcname=manifest.name)
            zipped.write(manifest, arcname=manifest.name)

    errors = finalizer.check_bundle_archive(archive, manifest, {"bundle_type": "unknown"}, {})

    assert f"review bundle archive contains duplicate entries: ['{manifest.name}']" in errors


def test_finalize_platform_verified_evidence_record_rejects_duplicate_manifest_bundle_records(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    manifest = tmp_path / "extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    archive = tmp_path / "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip"
    smoke = tmp_path / "native-smoke-linux-i386.log"
    manifest.write_text(json.dumps({"bundle_type": "extended-linux-native-evidence"}) + "\n", encoding="utf-8")
    smoke.write_text("smoke evidence\n", encoding="utf-8")
    manifest_data = {
        "bundle_type": "extended-linux-native-evidence",
        "builder_evidence": {"file": smoke.name, "size_bytes": smoke.stat().st_size, "sha256": _sha256(smoke)},
        "candidate_record": {"file": smoke.name, "size_bytes": smoke.stat().st_size, "sha256": _sha256(smoke)},
    }
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.write(manifest, arcname=manifest.name)
        zipped.write(smoke, arcname=smoke.name)

    errors = finalizer.check_archive_expected_entries(
        {manifest.name: zipfile.ZipInfo(manifest.name), smoke.name: zipfile.ZipInfo(smoke.name)},
        manifest,
        manifest_data,
    )

    assert f"review bundle manifest references duplicate bundle entries: ['{smoke.name}']" in errors


def test_finalize_platform_verified_evidence_record_rejects_duplicate_manifest_artifact_files() -> None:
    finalizer = _load_finalizer()
    candidate = {
        "artifact_sha256": {
            "remote-ops-workspace-v1.0.2-linux-i386.deb": "1" * 64,
        }
    }
    manifest = {
        "artifacts": [
            {"file": "remote-ops-workspace-v1.0.2-linux-i386.deb", "sha256": "0" * 64},
            {"file": "remote-ops-workspace-v1.0.2-linux-i386.deb", "sha256": "1" * 64},
        ]
    }

    errors = finalizer.check_manifest_artifacts_match_candidate(candidate, manifest)

    assert (
        "review bundle manifest artifact entries contain duplicate files: "
        "['remote-ops-workspace-v1.0.2-linux-i386.deb']"
    ) in errors


def test_finalize_platform_verified_evidence_record_rejects_duplicate_manifest_smoke_ids() -> None:
    finalizer = _load_finalizer()
    candidate = {
        "linux_smoke_evidence_sha256": {
            "native_smoke": "1" * 64,
        }
    }
    manifest = {
        "smoke_evidence": [
            {"id": "native_smoke", "file": "native-smoke-old.log", "sha256": "0" * 64},
            {"id": "native_smoke", "file": "native-smoke-new.log", "sha256": "1" * 64},
        ]
    }

    errors = finalizer.check_manifest_smoke_hashes_match_candidate(
        candidate,
        manifest,
        candidate_field="linux_smoke_evidence_sha256",
    )

    assert "review bundle manifest smoke_evidence entries contain duplicate ids: ['native_smoke']" in errors


def test_finalize_platform_verified_evidence_record_rejects_linux_manifest_evidence_name_drift(
    tmp_path: Path,
) -> None:
    finalizer = _load_finalizer()
    helpers = _load_platform_verified_evidence_tests()
    target = "linux-i386"
    candidate = helpers._linux_record(target)
    _unfinalized_candidate(candidate)
    candidate_path = tmp_path / "platform-verified-evidence-linux-i386.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "bundle_type": "extended-linux-native-evidence",
        "promotion_config_sha256": candidate["promotion_config_sha256"],
        "release_asset_urls": candidate["release_asset_urls"],
        "release_asset_source": candidate["release_asset_source"],
        "validated_commands": _linux_validated_commands(candidate),
        "workflow": candidate["workflow"],
        "workflow_inputs": candidate["workflow_inputs"],
        "workflow_run_url": candidate["workflow_run_url"],
        "runner_labels": candidate["runner_labels"],
        "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
        "builder_evidence": {
            "file": "builder.json",
            "sha256": candidate["builder_identity_sha256"],
            "size_bytes": 100,
        },
        "smoke_evidence": [
            {
                "id": "native_smoke",
                "file": "native-smoke.log",
                "sha256": candidate["linux_smoke_evidence_sha256"]["native_smoke"],
                "size_bytes": 100,
            }
        ],
        "candidate_record": _file_record(candidate_path),
        "artifacts": _artifact_records(candidate),
    }

    errors = finalizer.check_candidate_manifest_binding(candidate_path, candidate, manifest)

    assert "review bundle manifest builder_evidence.file must be builder-identity-linux-i386.json" in errors
    assert "review bundle manifest native_smoke file must be native-smoke-linux-i386.log" in errors


def _unfinalized_candidate(candidate: dict[str, object]) -> None:
    candidate.pop("review_bundle", None)
    candidate.pop("finalized_record_release_asset_url", None)
    source = candidate.get("release_asset_source")
    artifact_hashes = candidate.get("artifact_sha256")
    if isinstance(source, dict) and isinstance(artifact_hashes, dict):
        source["contains_files"] = sorted(str(name) for name in artifact_hashes)


def _write_bundle_files(
    root: Path,
    *,
    stem: str,
    bundle_type: str,
    target: str,
    release_tag: str,
    manifest_records: dict[str, dict[str, object]] | None = None,
    archive_files: dict[str, bytes] | None = None,
) -> tuple[Path, Path, Path]:
    manifest_records = manifest_records or {}
    archive_files = archive_files or {}
    manifest = root / f"{stem}.json"
    archive = root / f"{stem}.zip"
    sidecar = root / f"{stem}-SHA256SUMS.txt"
    data = {
        "schema_version": 1,
        "bundle_type": bundle_type,
        "target": target,
        "release_tag": release_tag,
        **manifest_records,
    }
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.write(manifest, arcname=manifest.name)
        for name, payload in archive_files.items():
            zipped.writestr(name, payload)
    sidecar.write_text(
        f"{_sha256(manifest)}  {manifest.name}\n{_sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )
    return manifest, archive, sidecar


def _rewrite_sidecar(sidecar: Path, *, manifest: Path, archive: Path) -> None:
    sidecar.write_text(
        f"{_sha256(manifest)}  {manifest.name}\n{_sha256(archive)}  {archive.name}\n",
        encoding="utf-8",
    )


def _rewrite_archive_entry_as_symlink(archive: Path, entry_name: str) -> None:
    with zipfile.ZipFile(archive) as zipped:
        entries = [(info, zipped.read(info.filename)) for info in zipped.infolist()]
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for old_info, payload in entries:
            info = zipfile.ZipInfo(old_info.filename)
            info.date_time = old_info.date_time
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = old_info.external_attr
            if old_info.filename == entry_name:
                info.external_attr = 0o120777 << 16
            zipped.writestr(info, payload)


def _replace_archive_entries(
    archive: Path,
    *,
    replacements: dict[str, bytes],
    remove: set[str],
) -> None:
    with zipfile.ZipFile(archive) as zipped:
        entries = {
            info.filename: zipped.read(info.filename)
            for info in zipped.infolist()
            if not info.is_dir() and info.filename not in remove and info.filename not in replacements
        }
    entries.update(replacements)
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, payload in entries.items():
            zipped.writestr(name, payload)


def _write_xp_candidate_and_bundle(
    root: Path,
    candidate: dict[str, object],
    *,
    target: str,
    release_tag: str,
    evidence_mutator: Any | None = None,
    smoke_text_mutator: Any | None = None,
) -> tuple[Path, Path, Path, Path]:
    smoke_hashes = candidate["xp_smoke_evidence_sha256"]
    assert isinstance(smoke_hashes, dict)
    summary = candidate["xp_evidence_summary"]
    assert isinstance(summary, dict)
    release_source = summary["release_source"]
    assert isinstance(release_source, dict)
    host_identity = summary["host_identity"]
    assert isinstance(host_identity, dict)
    os_identity = summary["os"]
    assert isinstance(os_identity, dict)
    host_probe_lines = _xp_host_probe_lines(target, os_identity)
    smoke_records: list[dict[str, object]] = []
    archive_files: dict[str, bytes] = {}
    for smoke_id in sorted(smoke_hashes):
        smoke_file = root / "xp-smoke-evidence" / f"{smoke_id}.txt"
        smoke_file.parent.mkdir(parents=True, exist_ok=True)
        smoke_text = (
            f"xp smoke target: {target}\n"
            f"xp smoke release: {release_tag}\n"
            f"xp smoke id: {smoke_id}\n"
            f"xp smoke os name: {os_identity['name']}\n"
            f"xp smoke os architecture: {os_identity['architecture']}\n"
            f"xp smoke os service pack: {os_identity['service_pack']}\n"
            + (
                f"xp smoke os edition: {os_identity['edition']}\n"
                if "edition" in os_identity
                else ""
            )
            + host_probe_lines
            + f"xp smoke host label: {host_identity['host_label']}\n"
            f"xp smoke evidence run id: {host_identity['evidence_run_id']}\n"
            f"xp smoke observed at utc: {host_identity['observed_at_utc']}\n"
            f"xp smoke source workflow run: {release_source['workflow_run_url']}\n"
            f"xp smoke source head sha: {release_source['head_sha']}\n"
            f"xp smoke source run attempt: {release_source['run_attempt']}\n"
            f"{_xp_security_smoke_lines(str(smoke_id))}"
            f"{smoke_id} smoke evidence\n"
        )
        if smoke_text_mutator is not None:
            smoke_text = smoke_text_mutator(str(smoke_id), smoke_text)
        smoke_file.write_text(smoke_text, encoding="utf-8")
        smoke_hashes[smoke_id] = _sha256(smoke_file)
        sources = candidate.get("xp_evidence_sources")
        if isinstance(sources, dict) and isinstance(sources.get("smoke_evidence"), dict):
            smoke_sources = sources["smoke_evidence"]
            if isinstance(smoke_sources.get(smoke_id), dict):
                smoke_sources[smoke_id]["size_bytes"] = smoke_file.stat().st_size
                smoke_sources[smoke_id]["sha256"] = smoke_hashes[smoke_id]
        archive_name = f"xp-smoke-evidence/{smoke_id}.txt"
        smoke_records.append(_smoke_file_record(smoke_file, smoke_id=str(smoke_id), name=archive_name))
        archive_files[archive_name] = smoke_file.read_bytes()

    xp_evidence = root / "xp-evidence.json"
    evidence_data = _xp_evidence_from_candidate(candidate)
    if evidence_mutator is not None:
        evidence_mutator(evidence_data)
    xp_evidence.write_text(json.dumps(evidence_data, indent=2) + "\n", encoding="utf-8")
    candidate["xp_evidence_sha256"] = _sha256(xp_evidence)
    sources = candidate.get("xp_evidence_sources")
    if isinstance(sources, dict) and isinstance(sources.get("evidence"), dict):
        sources["evidence"]["size_bytes"] = xp_evidence.stat().st_size
        sources["evidence"]["sha256"] = candidate["xp_evidence_sha256"]
    archive_files["xp-evidence.json"] = xp_evidence.read_bytes()
    archive_files.update(_attach_artifact_files(candidate))

    candidate_path = root / f"platform-verified-evidence-{target}.json"
    candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    manifest, archive, sidecar = _write_bundle_files(
        root,
        stem=f"xp-native-evidence-bundle-{target}-{release_tag}",
        bundle_type="windows-xp-native-host-evidence",
        target=target,
        release_tag=release_tag,
        manifest_records={
            "promotion_config_sha256": candidate["promotion_config_sha256"],
            "release_asset_urls": candidate["release_asset_urls"],
            "validated_commands": _xp_validated_commands(candidate),
            "workflow": candidate["workflow"],
            "workflow_inputs": candidate["workflow_inputs"],
            "release_asset_source": candidate["release_asset_source"],
            "xp_evidence_sources": candidate["xp_evidence_sources"],
            "xp_evidence_contract_sha256": candidate["xp_evidence_contract_sha256"],
            "host_identity": candidate["xp_evidence_summary"]["host_identity"],
            "toolchain": candidate["xp_evidence_summary"]["toolchain"],
            "security": candidate["xp_evidence_summary"]["security"],
            "candidate_record": _file_record(candidate_path),
            "evidence": _file_record(xp_evidence, name="xp-evidence.json"),
            "smoke_evidence": smoke_records,
            "artifacts": _artifact_records(candidate),
        },
        archive_files={**archive_files, candidate_path.name: candidate_path.read_bytes()},
    )
    return candidate_path, manifest, archive, sidecar


def _xp_host_probe_lines(target: str, os_identity: dict[str, Any]) -> str:
    if target.endswith("x64"):
        ver_output = "Microsoft Windows [Version 5.2.3790]"
        processor_architecture = "AMD64"
        caption = "Microsoft Windows XP Professional x64 Edition"
    else:
        ver_output = "Microsoft Windows XP [Version 5.1.2600]"
        processor_architecture = "x86"
        caption = "Microsoft Windows XP Professional"
    service_pack = str(os_identity["service_pack"]).removeprefix("SP")
    return (
        "xp smoke host probe command: ver\n"
        f"xp smoke host probe output: {ver_output}\n"
        f"xp smoke processor architecture env: {processor_architecture}\n"
        "xp smoke processor architecture w6432 env: \n"
        f"xp smoke wmic os caption: {caption}\n"
        f"xp smoke wmic os csdversion: Service Pack {service_pack}\n"
    )


def _xp_security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    return ""


def _linux_validated_commands(candidate: dict[str, object]) -> list[str]:
    return [
        str(candidate["native_build_command"]),
        str(candidate["native_smoke_command"]),
        str(candidate["local_evidence_preflight_command"]),
        str(candidate["staged_upload_command"]),
        str(candidate["artifact_validation_command"]),
        "python scripts/check_platform_verified_evidence.py",
    ]


def _xp_validated_commands(candidate: dict[str, object]) -> list[str]:
    return [
        str(candidate["native_evidence_validation_command"]),
        str(candidate["local_evidence_preflight_command"]),
        str(candidate["staged_upload_command"]),
        str(candidate["artifact_validation_command"]),
        "python scripts/check_platform_verified_evidence.py",
    ]


def _xp_evidence_from_candidate(candidate: dict[str, object]) -> dict[str, object]:
    summary = candidate["xp_evidence_summary"]
    smoke_hashes = candidate["xp_smoke_evidence_sha256"]
    assert isinstance(summary, dict)
    assert isinstance(smoke_hashes, dict)
    smoke_commands = summary["smoke_commands"]
    assert isinstance(smoke_commands, dict)
    return {
        "schema_version": 1,
        "target": summary["target"],
        "release_tag": summary["release_tag"],
        "release_source": copy.deepcopy(summary["release_source"]),
        "host_identity": copy.deepcopy(summary["host_identity"]),
        "os": copy.deepcopy(summary["os"]),
        "toolchain": copy.deepcopy(summary["toolchain"]),
        "smoke_results": [
            {
                "id": str(smoke_id),
                "passed": True,
                "command": str(smoke_commands[smoke_id]),
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": str(digest),
            }
            for smoke_id, digest in sorted(smoke_hashes.items())
        ],
        "security": copy.deepcopy(summary["security"]),
    }


def _file_record(path: Path, *, name: str | None = None) -> dict[str, object]:
    return {
        "file": name or path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _smoke_file_record(path: Path, *, smoke_id: str, name: str) -> dict[str, object]:
    record = _file_record(path, name=name)
    record["id"] = smoke_id
    return record


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
        if name.endswith((".deb", ".rpm", ".AppImage"))
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


def _candidate_builder_evidence_path(target: str, release_tag: str) -> str:
    return f"evidence/{target}/{release_tag}/builder-identity-{target}.json"


def _artifact_records(candidate: dict[str, object]) -> list[dict[str, object]]:
    hashes = candidate["artifact_sha256"]
    assert isinstance(hashes, dict)
    return [
        {
            "file": str(name),
            "size_bytes": len(_artifact_payload(str(name))),
            "sha256": str(digest),
        }
        for name, digest in sorted(hashes.items())
    ]


def _attach_artifact_files(candidate: dict[str, object]) -> dict[str, bytes]:
    hashes = candidate["artifact_sha256"]
    assert isinstance(hashes, dict)
    archive_files: dict[str, bytes] = {}
    for name in sorted(str(name) for name in hashes):
        payload = _artifact_payload(name)
        hashes[name] = hashlib.sha256(payload).hexdigest()
        archive_files[name] = payload
    return archive_files


def _artifact_payload(name: str) -> bytes:
    return f"{name} review artifact payload\n".encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_finalizer() -> Any:
    path = Path("scripts/finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_verified_evidence_record", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_tests() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_test_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
