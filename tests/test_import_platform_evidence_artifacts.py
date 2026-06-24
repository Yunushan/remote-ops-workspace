from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HEAD_SHA = "a" * 40


def test_import_record_downloads_expected_files_and_verifies_hashes(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    download_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"

    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert check is True
        if _is_metadata_command(command):
            assert kwargs == {"capture_output": True, "text": True}
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "attempt": 1,
                        "status": "completed",
                        "conclusion": "success",
                        "event": "workflow_dispatch",
                        "headSha": HEAD_SHA,
                        "path": ".github/workflows/extended-platform-evidence.yml",
                    }
                ),
            )
        assert kwargs == {}
        assert command[:6] == ["gh", "run", "download", "12345", "--repo", "example/remote-ops-workspace"]
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=out_dir,
        download_root=download_root,
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert errors == []
    assert commands[0] == _source_run_metadata_command(importer)
    assert commands[1][:4] == ["gh", "run", "download", "12345"]
    assert sorted(path.name for path in out_dir.iterdir()) == sorted(importer.expected_release_files(record))


def test_import_record_rejects_missing_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        Path(command[-1]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any("downloaded artifact missing expected release file" in error for error in errors)


def test_import_record_rejects_missing_final_record_source_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            if source_path.name == "platform-verified-evidence-linux-i386-final.json":
                continue
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 downloaded artifact missing expected release file: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_import_record_rejects_final_record_source_file_drift(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        final_record = destination / "platform-verified-evidence-linux-i386-final.json"
        data = json.loads(final_record.read_text(encoding="utf-8"))
        data["readiness_percent"] = 99.0
        final_record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 finalized accepted record source file must match accepted registry record: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_import_record_rejects_unexpected_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        (destination / "operator-private-builder.log").write_text("raw builder output\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 downloaded artifact contains unexpected files: ['operator-private-builder.log']" in errors


def test_import_record_rejects_nested_downloaded_artifact_directory(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        nested = destination / "native-dist"
        nested.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        (nested / "raw-smoke.log").write_text("raw nested output\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 downloaded artifact must contain root files only, found directories: ['native-dist']" in errors


def test_validate_source_artifact_rejects_missing_release_source_file_list(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    del record["release_asset_source"]["contains_files"]

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert "linux-i386 release_asset_source.contains_files must be a non-empty list" in errors


def test_validate_source_artifact_rejects_unsafe_release_source_file_entries(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_file = str(record["release_asset_source"]["contains_files"][0])
    record["release_asset_source"]["contains_files"] = [
        first_file,
        first_file,
        "../operator-private.log",
        "nested/raw-smoke.log",
    ]

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert (
        "linux-i386 release_asset_source.contains_files entries must be exact safe file names: "
        "['../operator-private.log', 'nested/raw-smoke.log']"
    ) in errors
    assert f"linux-i386 release_asset_source.contains_files contains duplicates: ['{first_file}']" in errors


def test_validate_source_artifact_rejects_missing_declared_expected_file(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source = record["release_asset_source"]
    final_record = "platform-verified-evidence-linux-i386-final.json"
    source["contains_files"] = [
        name for name in source["contains_files"] if name != final_record
    ]

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert (
        "linux-i386 release_asset_source.contains_files missing expected files: "
        "['platform-verified-evidence-linux-i386-final.json']"
    ) in errors


def test_validate_source_artifact_rejects_extra_declared_file(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["contains_files"].append("operator-private-builder.log")

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert (
        "linux-i386 release_asset_source.contains_files has unexpected files: "
        "['operator-private-builder.log']"
    ) in errors


def test_validate_source_artifact_rejects_downloaded_native_hash_mismatch(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "downloaded"
    _write_source_files(record, source_root)
    first_asset = next(iter(record["artifact_sha256"]))
    (source_root / str(first_asset)).write_bytes(b"tampered native artifact\n")

    errors = importer.validate_source_artifact(record, source_root=source_root)

    assert (
        f"linux-i386 downloaded source artifact native artifact SHA-256 mismatch: {first_asset}"
        in errors
    )


def test_validate_source_artifact_rejects_downloaded_review_bundle_hash_mismatch(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "downloaded"
    _write_source_files(record, source_root)
    manifest_name = str(record["review_bundle"]["manifest"]["file"])
    (source_root / manifest_name).write_text("{}\n", encoding="utf-8")

    errors = importer.validate_source_artifact(record, source_root=source_root)

    assert (
        "linux-i386 downloaded source artifact review bundle manifest SHA-256 mismatch: "
        f"{manifest_name}"
    ) in errors


def test_validate_downloaded_source_file_set_rejects_symlinked_source(
    tmp_path: Path, monkeypatch
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    source_root.mkdir()
    for source in record["_source_files"]:
        source_path = Path(str(source))
        (source_root / source_path.name).write_bytes(source_path.read_bytes())

    symlink_name = "platform-verified-evidence-linux-i386-final.json"

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.validate_downloaded_source_file_set(
        "linux-i386",
        source_root=source_root,
        expected_files=importer.expected_source_files(record),
    )

    assert f"linux-i386 downloaded artifact must not contain symlinks: ['{symlink_name}']" in errors


def test_validate_downloaded_source_file_set_rejects_symlinked_source_parent(
    tmp_path: Path, monkeypatch
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_parent = tmp_path / "linked-downloads"
    source_root = source_parent / "download"
    source_root.mkdir(parents=True)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        (source_root / source_path.name).write_bytes(source_path.read_bytes())

    def fake_is_symlink(self: Path) -> bool:
        return self == source_parent

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.validate_downloaded_source_file_set(
        "linux-i386",
        source_root=source_root,
        expected_files=importer.expected_source_files(record),
    )

    assert errors == [
        f"linux-i386 downloaded artifact directory path must not contain symlinked directories: {source_parent}"
    ]


def test_copy_expected_files_rejects_symlinked_source(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())
    symlink_name = sorted(expected_files)[0]

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert f"linux-i386 release asset import source must not be a symlink: {symlink_name}" in errors
    assert not (out_dir / symlink_name).exists()


def test_copy_expected_files_rejects_symlinked_source_parent(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_parent = tmp_path / "linked-downloads"
    source_root = source_parent / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir(parents=True)
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())

    def fake_is_symlink(self: Path) -> bool:
        return self == source_parent

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert (
        f"linux-i386 downloaded artifact directory path must not contain symlinked directories: {source_parent}"
    ) in errors
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    out_dir = tmp_path / "release-assets"

    def fake_is_symlink(self: Path) -> bool:
        return self == out_dir

    monkeypatch.setattr(type(out_dir), "is_symlink", fake_is_symlink)

    errors = importer.import_platform_evidence_artifacts([], out_dir=out_dir, dry_run=True)

    assert f"release asset import output directory must not be a symlink: {out_dir}" in errors
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_file_shaped_output_directory(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    out_dir = tmp_path / "release-assets.zip"

    errors = importer.import_platform_evidence_artifacts([], out_dir=out_dir, dry_run=True)

    assert errors == [
        f"release asset import output directory must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    out_parent = tmp_path / "linked-release"
    out_dir = out_parent / "release-assets"

    def fake_is_symlink(self: Path) -> bool:
        return self == out_parent

    monkeypatch.setattr(type(out_dir), "is_symlink", fake_is_symlink)

    errors = importer.import_platform_evidence_artifacts([], out_dir=out_dir, dry_run=True)

    assert errors == [
        f"release asset import output directory path must not contain symlinked directories: {out_parent}"
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_requires_gh_for_downloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    monkeypatch.setattr(importer.shutil, "which", lambda name: None if name == "gh" else "tool")

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh subprocess should not run when gh is unavailable")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "GitHub CLI `gh` is required to import accepted platform evidence artifacts; "
        "install gh or run inside GitHub Actions with GH_TOKEN configured"
    ]
    assert not out_dir.exists()


def test_copy_expected_files_rejects_symlinked_output_directory(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())

    def fake_is_symlink(self: Path) -> bool:
        return self == out_dir

    monkeypatch.setattr(type(out_dir), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert f"release asset import output directory must not be a symlink: {out_dir}" in errors
    assert not out_dir.exists()


def test_copy_expected_files_rejects_symlinked_output_parent(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_parent = tmp_path / "linked-release"
    out_dir = out_parent / "release-assets"
    source_root.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())

    def fake_is_symlink(self: Path) -> bool:
        return self == out_parent

    monkeypatch.setattr(type(out_dir), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert errors == [
        f"release asset import output directory path must not contain symlinked directories: {out_parent}"
    ]
    assert not out_dir.exists()


def test_copy_expected_files_rejects_symlinked_destination(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir()
    out_dir.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())
    symlink_name = sorted(expected_files)[0]

    def fake_is_symlink(self: Path) -> bool:
        return self.parent == out_dir and self.name == symlink_name

    monkeypatch.setattr(type(out_dir), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert f"linux-i386 release asset import destination must not be a symlink: {symlink_name}" in errors


def test_copy_expected_files_rejects_existing_destination_directory(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir()
    out_dir.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())
    directory_name = sorted(expected_files)[0]
    (out_dir / directory_name).mkdir()

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert f"linux-i386 release asset import destination must be a regular file: {directory_name}" in errors


def test_copy_expected_files_rejects_unsafe_expected_file_name(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["artifact_sha256"]["nested/file.bin"] = "a" * 64

    errors = importer.copy_expected_files(
        record,
        source_root=tmp_path / "download",
        out_dir=tmp_path / "release-assets",
    )

    assert (
        "linux-i386 release asset import expected files must be exact safe file names: "
        "['nested/file.bin']"
    ) in errors


def test_import_record_rejects_overwrite_with_different_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    out_dir.mkdir()
    first_asset = next(iter(record["artifact_sha256"]))
    (out_dir / str(first_asset)).write_bytes(b"different\n")

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=out_dir,
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any("release asset import would overwrite different file" in error for error in errors)


def test_import_record_rejects_tampered_source_file_before_copy(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    first_asset = next(iter(record["artifact_sha256"]))

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        _write_source_files(record, destination)
        (destination / str(first_asset)).write_bytes(b"tampered before release staging\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=out_dir,
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        f"linux-i386 downloaded source artifact native artifact SHA-256 mismatch: {first_asset}"
        in errors
    )
    assert not out_dir.exists()


def test_import_record_rejects_failed_source_workflow_run(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/extended-platform-evidence.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run conclusion must be success, got 'failure'"
        in errors
    )


def test_import_record_rejects_source_workflow_path_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["workflow"] = ".github/workflows/xp-native-evidence.yml"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release_asset_source.workflow is wrong")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source.workflow must be "
        ".github/workflows/extended-platform-evidence.yml"
    ) in errors


def test_import_record_rejects_source_artifact_name_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["artifact_name"] = "extended-linux-evidence-linux-armhf-v1.0.2"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when source artifact name is wrong")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source.artifact_name must be "
        "extended-linux-evidence-linux-i386-v1.0.2"
    ) in errors


def test_import_record_rejects_release_asset_url_tag_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_urls"][0] = str(record["release_asset_urls"][0]).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.3/",
    )

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release asset URL tag is wrong")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any(
        "linux-i386 release_asset_urls tag must match release_tag v1.0.2" in error
        and "/releases/download/v1.0.3/" in error
        for error in errors
    )


def test_import_record_rejects_source_workflow_repository_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["workflow_run_url"] = (
        "https://github.com/other/remote-ops-workspace/actions/runs/12345"
    )

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when source repository is wrong")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source.workflow_run_url repository must match "
        "release asset repositories ['example/remote-ops-workspace'], got other/remote-ops-workspace"
    ) in errors


def test_import_record_rejects_incomplete_or_non_dispatch_source_workflow_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "in_progress",
                    "conclusion": None,
                    "event": "push",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/other-workflow.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run status must be completed, got 'in_progress'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run conclusion must be success, got None"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run event must be workflow_dispatch, got 'push'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run path must be "
        "'.github/workflows/extended-platform-evidence.yml', "
        "got '.github/workflows/other-workflow.yml'"
    ) in errors


def test_import_record_rejects_source_workflow_path_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/ci.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run path must be "
        "'.github/workflows/extended-platform-evidence.yml', got '.github/workflows/ci.yml'"
        in errors
    )


def test_import_record_rejects_xp_source_workflow_path_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["target"] = "windows-xp-native-x86"
    record["release_asset_source"]["workflow"] = ".github/workflows/xp-native-evidence.yml"
    record["release_asset_source"]["artifact_name"] = "xp-native-evidence-windows-xp-native-x86-v1.0.2"

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/extended-platform-evidence.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "windows-xp-native-x86 release_asset_source workflow run path must be "
        "'.github/workflows/xp-native-evidence.yml', "
        "got '.github/workflows/extended-platform-evidence.yml'"
    ) in errors


def test_import_record_rejects_source_workflow_head_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": "b" * 40,
                    "path": ".github/workflows/extended-platform-evidence.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        f"linux-i386 release_asset_source workflow run headSha must match accepted record {HEAD_SHA}, "
        f"got '{'b' * 40}'"
    ) in errors


def test_import_record_rejects_source_workflow_run_attempt_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "attempt": 2,
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/extended-platform-evidence.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run attempt must match accepted record 1, got 2"
        in errors
    )


def test_import_record_rejects_release_checkout_head_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _successful_view(command)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha="c" * 40,
    )

    assert (
        f"linux-i386 release_asset_source.head_sha must match release checkout {'c' * 40}, got {HEAD_SHA}"
        in errors
    )


def test_import_record_dry_run_rejects_release_checkout_head_sha_mismatch(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        release_head_sha="c" * 40,
    )

    assert errors == [
        f"linux-i386 release_asset_source.head_sha must match release checkout {'c' * 40}, got {HEAD_SHA}"
    ]


def test_import_platform_evidence_artifacts_cli_dry_run_checks_release_checkout_head_sha(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = importer.public_record(_record(tmp_path))
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy": _platform_verified_evidence_policy(),
                "accepted_evidence": [record],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(importer, "current_checkout_head_sha", lambda: "c" * 40)

    result = importer.main(
        [
            "--registry",
            str(registry),
            "--release-tag",
            "v1.0.2",
            "--require-target",
            "linux-i386",
            "--out-dir",
            str(tmp_path / "release-assets"),
            "--dry-run",
        ]
    )

    assert result == 1


def test_import_record_dry_run_prints_gh_download_command(tmp_path: Path, capsys) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == []
    captured = capsys.readouterr()
    assert "gh api repos/example/remote-ops-workspace/actions/runs/12345/attempts/1" in captured.out
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out
    assert "--name extended-linux-evidence-linux-i386-v1.0.2" in captured.out


def test_import_record_dry_run_can_verify_source_run_without_download(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert check is True
        assert _is_metadata_command(command)
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_view(command)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        verify_source_run_metadata=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == []
    assert commands == [_source_run_metadata_command(importer)]
    assert not (tmp_path / "download").exists()
    captured = capsys.readouterr()
    assert "gh api repos/example/remote-ops-workspace/actions/runs/12345/attempts/1" in captured.out
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out


def test_import_record_dry_run_reports_verified_source_run_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "path": ".github/workflows/extended-platform-evidence.yml",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        verify_source_run_metadata=True,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run conclusion must be success, got 'failure'"
        in errors
    )


def test_expected_release_files_includes_native_review_bundle_and_final_record_files(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    expected_files = set(record["artifact_sha256"])
    expected_files.update(
        str(record["review_bundle"][key]["file"])
        for key in ("manifest", "archive", "sha256s")
    )
    expected_files.add("platform-verified-evidence-linux-i386-final.json")

    assert importer.expected_release_files(record) == expected_files


def test_check_imported_hashes_rejects_review_bundle_size_mismatch(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    manifest = record["review_bundle"]["manifest"]
    manifest["size_bytes"] = int(manifest["size_bytes"]) + 1

    errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert (
        "linux-i386 imported review bundle manifest size_bytes mismatch: "
        f"{manifest['file']}"
    ) in errors


def test_check_imported_hashes_rejects_missing_imported_files(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_artifact = next(iter(record["artifact_sha256"]))
    missing_bundle = str(record["review_bundle"]["archive"]["file"])
    (tmp_path / str(first_artifact)).unlink()
    (tmp_path / missing_bundle).unlink()

    errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert f"linux-i386 imported native artifact missing: {first_artifact}" in errors
    assert f"linux-i386 imported review bundle archive missing: {missing_bundle}" in errors


def test_import_record_rejects_tampered_review_bundle_content(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        manifest_name = str(record["review_bundle"]["manifest"]["file"])
        manifest_path = destination / manifest_name
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["candidate_record"]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        record["review_bundle"]["manifest"]["sha256"] = _sha256(manifest_path)
        final_record = destination / "platform-verified-evidence-linux-i386-final.json"
        final_record.write_text(json.dumps(importer.public_record(record), indent=2) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any(
        "linux-i386 imported review bundle validation failed: "
        "linux-i386 review bundle manifest candidate_record.sha256 must match "
        "platform-verified-evidence-linux-i386.json"
        in error
        for error in errors
    )


def _record(tmp_path: Path) -> dict[str, Any]:
    review_helpers = _load_platform_review_bundle_helpers()
    bundle_helpers = _load_finalize_tests()
    record = review_helpers._finalized_linux_record(tmp_path)
    artifact_hashes = record["artifact_sha256"]
    assert isinstance(artifact_hashes, dict)
    for filename in sorted(str(name) for name in artifact_hashes):
        (tmp_path / filename).write_bytes(bundle_helpers._artifact_payload(filename))
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    final_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    source_files = [tmp_path / str(name) for name in artifact_hashes]
    source_files.extend(
        tmp_path / str(record["review_bundle"][key]["file"])
        for key in ("manifest", "archive", "sha256s")
    )
    source_files.append(final_record)
    return {**record, "_source_files": source_files}


def _write_source_files(record: dict[str, Any], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        (destination / source_path.name).write_bytes(source_path.read_bytes())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _successful_view(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(
            {
                "attempt": 1,
                "status": "completed",
                "conclusion": "success",
                "event": "workflow_dispatch",
                "headSha": HEAD_SHA,
                "path": ".github/workflows/extended-platform-evidence.yml",
            }
        ),
    )


def _source_run_metadata_command(importer: Any) -> list[str]:
    return [
        "gh",
        "api",
        "repos/example/remote-ops-workspace/actions/runs/12345/attempts/1",
        "--jq",
        importer.SOURCE_RUN_METADATA_JQ,
    ]


def _is_metadata_command(command: list[str]) -> bool:
    return command[:3] == [
        "gh",
        "api",
        "repos/example/remote-ops-workspace/actions/runs/12345/attempts/1",
    ]


def _load_importer() -> Any:
    path = Path("scripts/import_platform_evidence_artifacts.py")
    spec = importlib.util.spec_from_file_location("import_platform_evidence_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_review_bundle_helpers() -> Any:
    path = Path("tests/test_platform_review_bundle_artifacts.py")
    spec = importlib.util.spec_from_file_location("platform_review_bundle_import_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_evidence_import_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _platform_verified_evidence_policy() -> str:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_import_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return str(module.POLICY)
