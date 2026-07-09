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
            return _successful_view(command)
        if _is_artifacts_command(command):
            assert kwargs == {"capture_output": True, "text": True}
            return _successful_artifacts(command)
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
    assert commands[1] == _source_run_artifacts_command(importer)
    assert commands[2][:4] == ["gh", "run", "download", "12345"]
    assert sorted(path.name for path in out_dir.iterdir()) == sorted(importer.expected_release_files(record))


def test_import_record_rejects_non_path_output_and_download_root_without_running_gh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh subprocess should not run for malformed import paths")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=["release-assets"],
        download_root="download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "release asset import output directory must be a pathlib.Path, got ['release-assets']",
        "linux-i386 release asset import download root must be a pathlib.Path, got 'download'",
    ]


def test_import_record_rejects_noncanonical_release_asset_source_without_running_gh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source = record["release_asset_source"]
    assert isinstance(source, dict)
    source["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/12345/"
    source["artifact_name"] = " extended-linux-evidence-linux-i386-v1.0.2 "
    source["head_sha"] = f" {HEAD_SHA} "
    source["workflow"] = " .github/workflows/extended-platform-evidence.yml "
    record["release_tag"] = " v1.0.2 "

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh subprocess should not run for noncanonical source metadata")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source.workflow_run_url must be canonical without "
        "surrounding whitespace or trailing slash"
    ) in errors
    assert (
        "linux-i386 release_asset_source.artifact_name must not include surrounding whitespace"
    ) in errors
    assert "linux-i386 release_tag must not include surrounding whitespace" in errors
    assert "linux-i386 release_asset_source.head_sha must not include surrounding whitespace" in errors
    assert "linux-i386 release_asset_source.workflow must not include surrounding whitespace" in errors


def test_import_record_rejects_missing_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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


def test_validate_downloaded_final_record_rejects_symlinked_source_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    filename = "platform-verified-evidence-linux-i386-final.json"
    final_record = tmp_path / filename
    final_record.write_bytes(importer.canonical_public_record_bytes(record))

    def fake_is_symlink(self: Path) -> bool:
        return self == final_record

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = importer.validate_downloaded_final_record(record, source_root=tmp_path)

    assert errors == [
        f"linux-i386 finalized accepted record source file must not be a symlink: {filename}"
    ]


def test_validate_downloaded_final_record_rejects_symlinked_source_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_parent = tmp_path / "linked-downloads"
    source_root = source_parent / "download"
    source_root.mkdir(parents=True)
    filename = "platform-verified-evidence-linux-i386-final.json"
    (source_root / filename).write_bytes(importer.canonical_public_record_bytes(record))

    def fake_is_symlink(self: Path) -> bool:
        return self == source_parent

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.validate_downloaded_final_record(record, source_root=source_root)

    assert errors == [
        f"linux-i386 finalized accepted record source file path must not contain symlinked directories: {source_parent}"
    ]


def test_import_record_rejects_final_record_source_file_drift(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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


def test_import_record_rejects_noncanonical_final_record_source_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        final_record = destination / "platform-verified-evidence-linux-i386-final.json"
        final_record.write_text(
            json.dumps(importer.public_record(record), indent=2) + "\n",
            encoding="utf-8",
        )
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
        "linux-i386 finalized accepted record source file must use canonical sorted JSON: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_import_record_rejects_unexpected_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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


def test_validate_source_artifact_rejects_non_path_source_root(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    errors = importer.validate_source_artifact(record, source_root="downloaded")

    assert errors == [
        "linux-i386 downloaded artifact directory must be a pathlib.Path, got 'downloaded'"
    ]


def test_validate_source_artifact_rejects_unsafe_release_source_file_entries(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_file = str(record["release_asset_source"]["contains_files"][0])
    record["release_asset_source"]["contains_files"] = [
        first_file,
        first_file,
        "../operator-private.log",
        "nested/raw-smoke.log",
        True,
    ]

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert any(
        "linux-i386 release_asset_source.contains_files entries must be exact safe file names" in error
        and "'../operator-private.log'" in error
        and "'nested/raw-smoke.log'" in error
        and "True" in error
        for error in errors
    )
    assert f"linux-i386 release_asset_source.contains_files contains duplicates: ['{first_file}']" in errors


def test_validate_source_artifact_rejects_case_colliding_release_source_file_entries(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_file = str(record["release_asset_source"]["contains_files"][0])
    record["release_asset_source"]["contains_files"].append(first_file.upper())

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert any(
        "linux-i386 release_asset_source.contains_files must not collide on case-insensitive filesystems"
        in error
        and first_file in error
        and first_file.upper() in error
        for error in errors
    )


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


def test_validate_source_artifact_rejects_malformed_expected_file_metadata(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["artifact_sha256"][True] = "0" * 64
    record["review_bundle"]["archive"]["file"] = False

    errors = importer.validate_source_artifact(record, source_root=tmp_path / "downloaded")

    assert errors == [
        "linux-i386 release asset import artifact_sha256 keys must be strings, got True",
        "linux-i386 release asset import review_bundle archive.file must be a string, got False",
    ]


def test_validate_source_artifact_rejects_ambiguous_expected_file_metadata(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    duplicate_record = _record(tmp_path)
    duplicate_file = duplicate_record["review_bundle"]["manifest"]["file"]
    duplicate_record["review_bundle"]["archive"]["file"] = duplicate_file
    collision_record = _record(tmp_path)
    collision_file = str(collision_record["review_bundle"]["manifest"]["file"])
    collision_record["review_bundle"]["sha256s"]["file"] = collision_file.upper()

    duplicate_errors = importer.validate_source_artifact(
        duplicate_record,
        source_root=tmp_path / "downloaded",
    )
    collision_errors = importer.validate_source_artifact(
        collision_record,
        source_root=tmp_path / "downloaded",
    )

    assert (
        "linux-i386 release asset import expected files must not contain duplicates: "
        f"['{duplicate_file}']"
    ) in duplicate_errors
    assert any(
        "linux-i386 release asset import expected files must not collide on "
        "case-insensitive filesystems" in error
        and collision_file in error
        and collision_file.upper() in error
        for error in collision_errors
    )


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


def test_validate_source_artifact_rejects_downloaded_boolean_review_bundle_size(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "downloaded"
    _write_source_files(record, source_root)
    manifest = record["review_bundle"]["manifest"]
    manifest["size_bytes"] = True

    errors = importer.validate_source_artifact(record, source_root=source_root)

    assert (
        "linux-i386 downloaded source artifact review bundle manifest size_bytes mismatch: "
        f"{manifest['file']}"
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


def test_copy_expected_files_rejects_non_path_source_and_output_args(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    errors = importer.copy_expected_files(
        record,
        source_root="download",
        out_dir=True,
    )

    assert errors == [
        "linux-i386 downloaded artifact directory must be a pathlib.Path, got 'download'",
        "release asset import output directory must be a pathlib.Path, got True",
    ]


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


def test_import_platform_evidence_artifacts_rejects_reserved_workspace_output_directory() -> None:
    importer = _load_importer()
    out_dir = Path(".github") / "release-assets"

    errors = importer.import_platform_evidence_artifacts([], out_dir=out_dir, dry_run=True)

    assert errors == [
        "release asset import output directory must not point inside "
        f"reserved workspace directory '.github': {out_dir}"
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_reserved_registry_path(tmp_path: Path) -> None:
    importer = _load_importer()
    registry = Path(".github") / "platform_verified_evidence.json"
    args = importer.parse_args(
        [
            "--registry",
            str(registry),
            "--release-tag",
            "v1.0.2",
            "--out-dir",
            str(tmp_path / "release-assets"),
        ]
    )

    errors = importer.strict_import_arg_errors(args)

    assert errors == [
        "accepted evidence registry must not point inside reserved workspace directory "
        f"'.github': {registry}"
    ]


def test_import_platform_evidence_artifacts_rejects_non_path_registry_and_output_args(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    args = importer.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--out-dir",
            str(tmp_path / "release-assets"),
            "--verify-source-run",
        ]
    )
    args.registry = True
    args.out_dir = ["release-assets"]

    errors = importer.strict_import_arg_errors(args)

    assert "accepted evidence registry must be a pathlib.Path, got True" in errors
    assert (
        "release asset import output directory must be a pathlib.Path, got ['release-assets']"
        in errors
    )


def test_import_platform_evidence_artifacts_rejects_non_path_output_directory() -> None:
    importer = _load_importer()

    errors = importer.import_platform_evidence_artifacts(
        [],
        out_dir=True,
        dry_run=True,
    )

    assert errors == ["release asset import output directory must be a pathlib.Path, got True"]


def test_import_platform_evidence_artifacts_rejects_invalid_expected_repository(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    out_dir = tmp_path / "release-assets"

    errors = importer.import_platform_evidence_artifacts(
        [],
        out_dir=out_dir,
        dry_run=True,
        repository="not-a-repository",
    )

    assert errors == [
        "platform evidence import repository must be a GitHub owner/name value, "
        "got 'not-a-repository'"
    ]
    assert not out_dir.exists()


def test_check_output_directory_empty_rejects_non_path_arg() -> None:
    importer = _load_importer()

    errors = importer.check_output_directory_empty("release-assets")

    assert errors == [
        "release asset import output directory must be a pathlib.Path, got 'release-assets'"
    ]


def test_import_platform_evidence_artifacts_path_parent_helper_rejects_non_path_arg() -> None:
    importer = _load_importer()

    errors = importer.check_path_parent_symlinks(True, "downloaded artifact directory")

    assert errors == ["downloaded artifact directory must be a pathlib.Path, got True"]


def test_import_platform_evidence_artifacts_rejects_non_string_required_target(
    tmp_path: Path,
) -> None:
    importer = _load_importer()
    args = importer.parse_args(
        [
            "--registry",
            str(tmp_path / "platform_verified_evidence.json"),
            "--release-tag",
            "v1.0.2",
            "--out-dir",
            str(tmp_path / "release-assets"),
            "--dry-run",
        ]
    )
    args.require_target = [True]

    errors = importer.strict_import_arg_errors(args)

    assert "platform evidence import required target must be a non-empty string, got True" in errors
    assert importer.REQUIRE_VERIFY_SOURCE_RUN_DRY_RUN_ERROR in errors
    assert importer.required_targets_from_args(args) == tuple(importer.PROTECTED_GOAL_TARGETS)


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


def test_import_platform_evidence_artifacts_rejects_nonempty_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    out_dir.mkdir()
    stale_file = out_dir / "stale.txt"
    stale_file.write_text("stale\n", encoding="utf-8")

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when output directory is not empty")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "release asset import output directory must be empty before import: ['stale.txt']"
    ]
    assert stale_file.exists()


def test_import_platform_evidence_artifacts_dry_run_allows_nonempty_output_directory(
    tmp_path: Path,
    capsys,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    out_dir.mkdir()
    (out_dir / "stale.txt").write_text("stale\n", encoding="utf-8")

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == []
    assert "gh run download 12345" in capsys.readouterr().out


def test_import_platform_evidence_artifacts_rejects_duplicate_record_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = importer.public_record(_record(tmp_path))
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted import records contain duplicate targets")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record, dict(record)],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "release asset import accepted records must target each platform once: linux-i386"
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_non_string_record_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = importer.public_record(_record(tmp_path))
    record["target"] = True
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted import record target is malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "release asset import accepted record target must be a non-empty string, got True"
    ]
    assert not out_dir.exists()


def test_accepted_records_does_not_stringify_malformed_target() -> None:
    importer = _load_importer()
    registry = {
        "accepted_evidence": [
            {
                "status": "accepted",
                "readiness_percent": 100.0,
                "release_tag": "v1.0.2",
                "target": True,
            }
        ]
    }

    records = importer.accepted_records(
        registry,
        release_tag="v1.0.2",
        targets=("True",),
    )

    assert records == []


def test_import_platform_evidence_artifacts_rejects_non_string_public_record_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record[True] = "manual scratch"
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted import record keys are malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 accepted evidence public record keys must be strings, got True"
    ]
    assert True not in importer.public_record(record)
    assert "_source_files" not in importer.public_record(record)
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_case_colliding_public_record_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["TARGET"] = record["target"]
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted import record keys collide")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 accepted evidence public record keys must not collide on "
        "case-insensitive filesystems: ['TARGET', 'target']"
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_non_string_expected_output_file_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["artifact_sha256"][True] = "0" * 64
    record["review_bundle"]["manifest"]["file"] = False
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when import output file names are malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release asset import artifact_sha256 keys must be strings, got True",
        "linux-i386 release asset import review_bundle manifest.file must be a string, got False",
    ]
    assert not out_dir.exists()


def test_import_platform_evidence_artifacts_rejects_ambiguous_output_file_names() -> None:
    importer = _load_importer()

    errors = importer.check_import_release_file_names(
        [
            {
                "target": "linux-i386",
                "artifact_sha256": {
                    "remote-ops-workspace-v1.0.2-linux-i386.deb": "a" * 64,
                    "Readme.txt": "b" * 64,
                    "nested/escape.deb": "c" * 64,
                },
            },
            {
                "target": "linux-armhf",
                "artifact_sha256": {
                    "remote-ops-workspace-v1.0.2-linux-i386.deb": "d" * 64,
                    "readme.txt": "e" * 64,
                },
            },
        ]
    )

    assert (
        "release asset import expected output file names must be exact safe file names: "
        "['linux-i386:nested/escape.deb']"
    ) in errors
    assert (
        "release asset import expected output file names must be unique across accepted records: "
        "['remote-ops-workspace-v1.0.2-linux-i386.deb']"
    ) in errors
    assert (
        "release asset import expected output file names must not collide on case-insensitive filesystems: "
        "['Readme.txt', 'readme.txt']"
    ) in errors


def test_import_platform_evidence_artifacts_rejects_output_name_collision_before_gh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = importer.public_record(_record(tmp_path))
    duplicate_name = sorted(importer.expected_release_files(record))[0]
    colliding_record = {
        "target": "linux-armhf",
        "artifact_sha256": {duplicate_name: "0" * 64},
    }
    out_dir = tmp_path / "release-assets"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted import records collide on output names")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_platform_evidence_artifacts(
        [record, colliding_record],
        out_dir=out_dir,
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "release asset import expected output file names must be unique across accepted records: "
        f"['{duplicate_name}']"
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


def test_copy_expected_files_rejects_malformed_expected_file_metadata(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["artifact_sha256"][True] = "0" * 64
    record["review_bundle"]["manifest"]["file"] = False

    errors = importer.copy_expected_files(
        record,
        source_root=tmp_path / "download",
        out_dir=tmp_path / "release-assets",
    )

    assert errors == [
        "linux-i386 release asset import artifact_sha256 keys must be strings, got True",
        "linux-i386 release asset import review_bundle manifest.file must be a string, got False",
    ]


def test_copy_expected_files_rejects_ambiguous_expected_file_metadata(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    duplicate_file = record["review_bundle"]["manifest"]["file"]
    record["review_bundle"]["archive"]["file"] = duplicate_file

    errors = importer.copy_expected_files(
        record,
        source_root=tmp_path / "download",
        out_dir=tmp_path / "release-assets",
    )

    assert errors == [
        "linux-i386 release asset import expected files must not contain duplicates: "
        f"['{duplicate_file}']"
    ]


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
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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
                    "headBranch": "v1.0.2",
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


def test_import_record_rejects_source_workflow_run_path_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
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


def test_import_record_rejects_non_string_release_source_provenance_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source = record["release_asset_source"]
    record["release_tag"] = True
    source["workflow_run_url"] = False
    source["workflow"] = 123
    source["artifact_name"] = ["extended-linux-evidence-linux-i386-v1.0.2"]
    source["head_sha"] = {"sha": HEAD_SHA}

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release source provenance fields are malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source.workflow_run_url must be a string, got False",
        "linux-i386 release_asset_source.artifact_name must be a string, "
        "got ['extended-linux-evidence-linux-i386-v1.0.2']",
        "linux-i386 release_tag must be a string, got True",
        "linux-i386 release_asset_source.head_sha must be a string, got {'sha': "
        f"'{HEAD_SHA}'" + "}",
        "linux-i386 release_asset_source.workflow must be a string, got 123",
    ]


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


def test_import_record_rejects_path_qualified_release_asset_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_urls"][0] = str(record["release_asset_urls"][0]).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release asset URL file name is unsafe")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any(
        "linux-i386 release_asset_urls file name must be an exact safe file name" in error
        and "/releases/download/v1.0.2/nested/" in error
        for error in errors
    )


def test_import_record_rejects_non_string_release_asset_url_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_urls"].append(True)
    record["review_bundle"]["release_asset_urls"].append(False)

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release asset URL entries are malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 release_asset_urls entries must be strings, got True" in errors
    assert "linux-i386 review_bundle release_asset_urls entries must be strings, got False" in errors


def test_import_record_rejects_malformed_release_asset_url_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_urls"] = True
    record["review_bundle"]["release_asset_urls"] = False
    record["finalized_record_release_asset_url"] = True

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release asset URL fields are malformed")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 release_asset_urls must be a list, got True" in errors
    assert "linux-i386 review_bundle release_asset_urls must be a list, got False" in errors
    assert "linux-i386 finalized_record_release_asset_url must be a string, got True" in errors


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


def test_import_record_rejects_release_asset_urls_outside_expected_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def wrong_repository(url: str) -> str:
        return url.replace(
            "https://github.com/example/remote-ops-workspace/",
            "https://github.com/other/remote-ops-workspace/",
        )

    record["release_asset_urls"][0] = wrong_repository(record["release_asset_urls"][0])
    record["review_bundle"]["release_asset_urls"][0] = wrong_repository(
        record["review_bundle"]["release_asset_urls"][0]
    )
    record["finalized_record_release_asset_url"] = wrong_repository(
        record["finalized_record_release_asset_url"]
    )

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when accepted release asset URLs are out of scope")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
        repository="example/remote-ops-workspace",
    )

    assert any(
        "linux-i386 release_asset_urls repository must match release repository "
        "example/remote-ops-workspace" in error
        for error in errors
    )
    assert any(
        "linux-i386 review_bundle release_asset_urls repository must match release repository "
        "example/remote-ops-workspace" in error
        for error in errors
    )
    assert any(
        "linux-i386 finalized_record_release_asset_url repository must match release repository "
        "example/remote-ops-workspace" in error
        for error in errors
    )


def test_import_record_rejects_source_workflow_outside_expected_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["workflow_run_url"] = (
        "https://github.com/other/remote-ops-workspace/actions/runs/12345"
    )

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when source workflow run is out of scope")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
        repository="example/remote-ops-workspace",
    )

    assert errors == [
        "linux-i386 release_asset_source.workflow_run_url repository must match "
        "release repository example/remote-ops-workspace, got other/remote-ops-workspace"
    ]


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
                    "headBranch": "v1.0.2",
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
                    "headBranch": "v1.0.2",
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
                    "headBranch": "v1.0.2",
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
                    "headBranch": "v1.0.2",
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
                    "headBranch": "v1.0.2",
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


def test_import_record_rejects_boolean_source_workflow_run_attempt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, attempt=True)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run attempt must be a positive integer, "
        "got True"
    ) in errors


def test_import_record_rejects_source_workflow_run_release_tag_ref_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, headBranch="main")

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run headBranch must match release_tag "
        "v1.0.2, got 'main'"
    ) in errors


def test_import_record_rejects_source_workflow_run_started_before_created(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            runCreatedAt="2026-06-30T12:01:00Z",
            runStartedAt="2026-06-30T12:00:00Z",
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
        "linux-i386 release_asset_source workflow run runStartedAt "
        "must be at or after runCreatedAt 2026-06-30T12:01:00Z, "
        "got '2026-06-30T12:00:00Z'"
    ) in errors


def test_import_record_rejects_padded_source_workflow_run_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            nodeId=" WFR_kwLO12345",
            runCreatedAt=" 2026-06-30T11:59:00Z",
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
        "linux-i386 release_asset_source workflow run nodeId must be a non-empty string, "
        "got ' WFR_kwLO12345'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run runCreatedAt must be a GitHub ISO-8601 "
        "timestamp, got ' 2026-06-30T11:59:00Z'"
    ) in errors


def test_import_record_rejects_source_workflow_run_id_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, id=99999)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run id must match accepted record 12345, got 99999"
        in errors
    )


def test_import_record_rejects_source_workflow_run_identity_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            id="12345",
            nodeId="",
            runNumber=0,
            workflowId="445566",
            checkSuiteId=False,
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
        "linux-i386 release_asset_source workflow run id must be a positive integer, got '12345'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run nodeId must be a non-empty string, got ''"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run runNumber must be a positive integer, got 0"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run workflowId must be a positive integer, got '445566'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run checkSuiteId must be a positive integer, got False"
        in errors
    )


def test_import_record_rejects_source_workflow_run_url_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            htmlUrl="https://github.com/example/remote-ops-workspace/actions/runs/99999",
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
        "linux-i386 release_asset_source workflow run htmlUrl must match accepted record "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345, "
        "got 'https://github.com/example/remote-ops-workspace/actions/runs/99999'"
    ) in errors


def test_import_record_rejects_noncanonical_source_workflow_run_html_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            htmlUrl="https://github.com/example/remote-ops-workspace/actions/runs/12345/",
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
        "linux-i386 release_asset_source workflow run htmlUrl must match accepted record "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345, "
        "got 'https://github.com/example/remote-ops-workspace/actions/runs/12345/'"
    ) in errors


def test_import_record_rejects_non_string_source_workflow_run_html_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, htmlUrl=True)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 release_asset_source workflow run htmlUrl must be a string, got True" in errors


def test_repository_from_workflow_run_url_rejects_noncanonical_run_url() -> None:
    importer = _load_importer()

    assert importer.repository_from_workflow_run_url(
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) == "example/remote-ops-workspace"
    assert importer.repository_from_workflow_run_url(
        "https://github.com/example/remote-ops-workspace/actions/runs/12345/"
    ) == ""


def test_import_record_rejects_source_workflow_run_endpoint_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            url="https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999",
            workflowUrl="https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/999",
            jobsUrl="https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/jobs",
            logsUrl="https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/logs",
            artifactsUrl=(
                "https://api.github.com/repos/example/remote-ops-workspace/"
                "actions/runs/99999/artifacts"
            ),
            checkSuiteUrl="https://api.github.com/repos/example/remote-ops-workspace/check-suites/1",
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
        "linux-i386 release_asset_source workflow run url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run workflowUrl must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/445566', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/999'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run jobsUrl must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/jobs', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/jobs'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run logsUrl must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/logs', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/logs'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run artifactsUrl must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/artifacts', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/artifacts'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run checkSuiteUrl must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/check-suites/998877', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/check-suites/1'"
    ) in errors


def test_import_record_rejects_source_workflow_run_repository_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(
            command,
            repositoryFullName="other/remote-ops-workspace",
            headRepositoryFullName="example/forked-remote-ops-workspace",
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
        "linux-i386 release_asset_source workflow run repositoryFullName must match accepted record "
        "example/remote-ops-workspace, got 'other/remote-ops-workspace'"
    ) in errors
    assert (
        "linux-i386 release_asset_source workflow run headRepositoryFullName must match accepted record "
        "example/remote-ops-workspace, got 'example/forked-remote-ops-workspace'"
    ) in errors


def test_import_record_rejects_missing_source_workflow_run_repository_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, repositoryId=None)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run repositoryId "
        "must be a positive integer, got None"
    ) in errors


def test_import_record_rejects_missing_source_workflow_run_head_repository_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert _is_metadata_command(command)
        return _source_run_metadata(command, headRepositoryId="1001")

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run headRepositoryId "
        "must be a positive integer, got '1001'"
    ) in errors


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
            "--verify-source-run",
        ]
    )

    assert result == 1


def test_import_platform_evidence_artifacts_cli_requires_source_run_verification_for_single_target_dry_run(
    tmp_path: Path,
    capsys,
) -> None:
    importer = _load_importer()
    registry = tmp_path / "platform_verified_evidence.json"

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

    assert result == 2
    assert (
        "platform evidence import: --dry-run for protected platform evidence imports "
        "requires --verify-source-run"
    ) in capsys.readouterr().err


def test_import_platform_evidence_artifacts_cli_requires_source_run_verification_for_goal_dry_run(
    tmp_path: Path,
    capsys,
) -> None:
    importer = _load_importer()
    registry = tmp_path / "platform_verified_evidence.json"

    result = importer.main(
        [
            "--registry",
            str(registry),
            "--release-tag",
            "v1.0.2",
            "--require-goal-targets",
            "--out-dir",
            str(tmp_path / "release-assets"),
            "--dry-run",
        ]
    )

    assert result == 2
    assert (
        "platform evidence import: --dry-run for protected platform evidence imports requires --verify-source-run"
        in capsys.readouterr().err
    )


def test_import_platform_evidence_artifacts_cli_requires_source_run_verification_for_all_targets_dry_run(
    tmp_path: Path,
    capsys,
) -> None:
    importer = _load_importer()
    registry = tmp_path / "platform_verified_evidence.json"
    args = [
        "--registry",
        str(registry),
        "--release-tag",
        "v1.0.2",
        "--out-dir",
        str(tmp_path / "release-assets"),
        "--dry-run",
    ]
    for target in sorted(importer.PROTECTED_GOAL_TARGETS):
        args.extend(["--require-target", target])

    result = importer.main(args)

    assert result == 2
    assert (
        "platform evidence import: --dry-run for protected platform evidence imports requires --verify-source-run"
        in capsys.readouterr().err
    )


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
    assert "gh api repos/example/remote-ops-workspace/actions/runs/12345/artifacts?per_page=100" in captured.out
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out
    assert "--name extended-linux-evidence-linux-i386-v1.0.2" in captured.out


def test_import_record_dry_run_rejects_declared_source_file_drift(
    tmp_path: Path,
    capsys,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source = record["release_asset_source"]
    source["contains_files"] = [
        name
        for name in source["contains_files"]
        if name != "platform-verified-evidence-linux-i386-final.json"
    ]

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source.contains_files missing expected files: "
        "['platform-verified-evidence-linux-i386-final.json']"
    ]
    assert capsys.readouterr().out == ""


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
        assert kwargs == {"capture_output": True, "text": True}
        if _is_metadata_command(command):
            return _successful_view(command)
        assert _is_artifacts_command(command)
        return _successful_artifacts(command)

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
    assert commands == [
        _source_run_metadata_command(importer),
        _source_run_artifacts_command(importer),
    ]
    assert not (tmp_path / "download").exists()
    captured = capsys.readouterr()
    assert "gh api repos/example/remote-ops-workspace/actions/runs/12345/attempts/1" in captured.out
    assert "gh api repos/example/remote-ops-workspace/actions/runs/12345/artifacts?per_page=100" in captured.out
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out


def test_import_record_dry_run_rejects_missing_source_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        if _is_metadata_command(command):
            return _successful_view(command)
        assert _is_artifacts_command(command)
        return _successful_artifacts(command, artifacts=[])

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
        verify_source_run_metadata=True,
        release_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source artifact list must contain only the "
        "target-scoped evidence artifact 'extended-linux-evidence-linux-i386-v1.0.2', "
        "got 0 artifacts",
        "linux-i386 release_asset_source artifact list must contain exactly one "
        "'extended-linux-evidence-linux-i386-v1.0.2', got 0",
    ]


def test_import_record_dry_run_rejects_extra_source_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        if _is_metadata_command(command):
            return _successful_view(command)
        assert _is_artifacts_command(command)
        artifacts = json.loads(_successful_artifacts(command).stdout)["artifacts"]
        artifacts.append(
            {
                "id": 98766,
                "name": "raw-builder-output",
                "archive_download_url": (
                    "https://api.github.com/repos/example/remote-ops-workspace/"
                    "actions/artifacts/98766/zip"
                ),
                "expired": False,
                "size_in_bytes": 512,
                "created_at": "2026-06-30T12:03:00Z",
                "updated_at": "2026-06-30T12:04:00Z",
                "workflow_run": {
                    "id": 12345,
                    "head_sha": HEAD_SHA,
                    "repository_id": 1001,
                    "head_repository_id": 1001,
                },
            }
        )
        return _successful_artifacts(command, artifacts=artifacts)

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
        "linux-i386 release_asset_source artifact list must contain only the "
        "target-scoped evidence artifact 'extended-linux-evidence-linux-i386-v1.0.2', "
        "got 2 artifacts"
    ) in errors


def test_verify_source_artifact_rejects_expired_or_empty_artifact(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": True,
                    "size_in_bytes": 0,
                    "workflow_run": {"id": 12345, "head_sha": HEAD_SHA},
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "must not be expired, got True"
    ) in errors
    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "size_in_bytes must be positive, got 0"
    ) in errors


def test_verify_source_artifact_rejects_missing_expiration(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        artifact = json.loads(_successful_artifacts(command_arg).stdout)["artifacts"][0]
        artifact.pop("expires_at")
        return _successful_artifacts(command_arg, artifacts=[artifact])

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "expires_at must be a GitHub ISO-8601 timestamp, got None"
    ) in errors


def test_verify_source_artifact_rejects_stale_expiration(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        artifact = json.loads(_successful_artifacts(command_arg).stdout)["artifacts"][0]
        artifact["expires_at"] = "2026-06-30T12:03:30Z"
        return _successful_artifacts(command_arg, artifacts=[artifact])

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "expires_at must be after updated_at 2026-06-30T12:04:00Z, "
        "got '2026-06-30T12:03:30Z'"
    ) in errors


def test_verify_source_artifact_rejects_partial_artifact_inventory(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(command_arg, total_count=101)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source artifact metadata total_count must match "
        "the complete artifacts list length, got 101 for 1 artifacts"
    ]


def test_verify_source_artifact_rejects_wrong_workflow_run_binding(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)
    bad_head_sha = "b" * 40

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "workflow_run": {"id": 99999, "head_sha": bad_head_sha},
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.id must match run 12345, got 99999"
    ) in errors
    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        f"workflow_run.head_sha must match accepted record {HEAD_SHA}, got {bad_head_sha!r}"
    ) in errors


def test_verify_source_artifact_rejects_non_string_workflow_run_head_sha(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "workflow_run": {"id": 12345, "head_sha": True},
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.head_sha must be a string, got True"
    ) in errors


def test_verify_source_artifact_rejects_padded_artifact_metadata(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "node_id": " MDEyOkFydGlmYWN0OTg3NjU=",
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765"
                    ),
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": " 2026-06-30T12:03:00Z",
                    "updated_at": "2026-06-30T12:04:00Z",
                    "expires_at": "2026-09-28T12:04:00Z",
                    "workflow_run": {"id": 12345, "head_sha": f"{HEAD_SHA} "},
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_run_created_at="2026-06-30T11:59:00Z",
        expected_run_started_at="2026-06-30T12:00:00Z",
        expected_run_updated_at="2026-06-30T12:05:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "node_id must be a non-empty string, got ' MDEyOkFydGlmYWN0OTg3NjU='"
    ) in errors
    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be a GitHub ISO-8601 timestamp when exact source run timestamps "
        "are known, got ' 2026-06-30T12:03:00Z'"
    ) in errors
    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        f"workflow_run.head_sha must match accepted record {HEAD_SHA}, got '{HEAD_SHA} '"
    ) in errors


def test_verify_source_artifact_rejects_wrong_workflow_run_repository_ids(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 2222,
                        "head_repository_id": 3333,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.repository_id must match exact source run repository id 1001, got 2222"
    ) in errors
    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.head_repository_id must match exact source run head repository id 1001, got 3333"
    ) in errors


def test_verify_source_artifact_rejects_artifact_created_before_exact_run_start(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T11:59:59Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
        expected_run_started_at="2026-06-30T12:00:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or after exact source run start 2026-06-30T12:00:00Z, "
        "got '2026-06-30T11:59:59Z'"
    ) in errors


def test_verify_source_artifact_rejects_artifact_created_before_exact_run_creation(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T11:58:59Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
        expected_run_created_at="2026-06-30T11:59:00Z",
        expected_run_started_at="2026-06-30T12:00:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or after exact source run creation 2026-06-30T11:59:00Z, "
        "got '2026-06-30T11:58:59Z'"
    ) in errors


def test_verify_source_artifact_rejects_artifact_created_after_exact_run_update(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T12:05:01Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
        expected_run_started_at="2026-06-30T12:00:00Z",
        expected_run_updated_at="2026-06-30T12:05:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or before exact source run update 2026-06-30T12:05:00Z, "
        "got '2026-06-30T12:05:01Z'"
    ) in errors


def test_verify_source_artifact_rejects_artifact_updated_after_exact_run_update(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T12:03:00Z",
                    "updated_at": "2026-06-30T12:05:01Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
        expected_run_started_at="2026-06-30T12:00:00Z",
        expected_run_updated_at="2026-06-30T12:05:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "updated_at must be at or before exact source run update 2026-06-30T12:05:00Z, "
        "got '2026-06-30T12:05:01Z'"
    ) in errors


def test_verify_source_artifact_rejects_artifact_updated_before_created_at(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T12:03:00Z",
                    "updated_at": "2026-06-30T12:02:59Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                }
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
        expected_repository_id=1001,
        expected_head_repository_id=1001,
        expected_run_started_at="2026-06-30T12:00:00Z",
        expected_run_updated_at="2026-06-30T12:05:00Z",
    )

    assert (
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "updated_at must be at or after created_at 2026-06-30T12:03:00Z, "
        "got '2026-06-30T12:02:59Z'"
    ) in errors


def test_verify_source_artifact_rejects_unbound_artifact_identity(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": "98765",
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "archive_download_url": "https://api.github.com/repos/other/repo/actions/artifacts/98765/zip",
                    "expired": False,
                    "size_in_bytes": 4096,
                    "expires_at": "2026-09-28T12:04:00Z",
                    "workflow_run": {"id": 12345, "head_sha": HEAD_SHA},
                },
                {
                    "id": 98766,
                    "name": "extended-linux-evidence-linux-armhf-v1.0.2",
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98766/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "expires_at": "2026-09-28T12:04:00Z",
                    "workflow_run": {"id": 12345, "head_sha": HEAD_SHA},
                },
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source artifact list must contain only the "
        "target-scoped evidence artifact 'extended-linux-evidence-linux-i386-v1.0.2', "
        "got 2 artifacts",
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "id must be a positive integer, got '98765'",
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "node_id must be a non-empty string, got None",
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.repository_id must be a positive integer, got None",
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.head_repository_id must be a positive integer, got None",
    ]


def test_verify_source_artifact_rejects_archive_download_url_mismatch(monkeypatch) -> None:
    importer = _load_importer()
    command = _source_run_artifacts_command(importer)

    def fake_run(command_arg: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command_arg == command
        assert check is True
        assert kwargs == {"capture_output": True, "text": True}
        return _successful_artifacts(
            command_arg,
            artifacts=[
                {
                    "id": 98765,
                    "node_id": "MDEyOkFydGlmYWN0OTg3NjU=",
                    "name": "extended-linux-evidence-linux-i386-v1.0.2",
                    "url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        "actions/artifacts/98765"
                    ),
                    "archive_download_url": "https://api.github.com/repos/other/repo/actions/artifacts/98765/zip",
                    "expired": False,
                    "size_in_bytes": 4096,
                    "expires_at": "2026-09-28T12:04:00Z",
                    "workflow_run": {
                        "id": 12345,
                        "head_sha": HEAD_SHA,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                    },
                },
            ],
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.verify_source_artifact(
        "linux-i386",
        command,
        artifact_name="extended-linux-evidence-linux-i386-v1.0.2",
        expected_repository="example/remote-ops-workspace",
        expected_run_id="12345",
        expected_head_sha=HEAD_SHA,
    )

    assert errors == [
        "linux-i386 release_asset_source artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "archive_download_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/artifacts/98765/zip', "
        "got 'https://api.github.com/repos/other/repo/actions/artifacts/98765/zip'"
    ]


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
                    "headBranch": "v1.0.2",
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


def test_check_imported_hashes_rejects_boolean_review_bundle_size(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    manifest = record["review_bundle"]["manifest"]
    manifest["size_bytes"] = True

    errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert (
        "linux-i386 imported review bundle manifest size_bytes mismatch: "
        f"{manifest['file']}"
    ) in errors


def test_check_imported_hashes_rejects_malformed_review_bundle_metadata(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["review_bundle"]["manifest"]["file"] = True
    record["review_bundle"]["archive"]["size_bytes"] = 0
    record["review_bundle"]["archive"]["sha256"] = True
    record["review_bundle"]["sha256s"]["sha256"] = "A" * 64

    downloaded_errors = importer.check_downloaded_source_hashes(record, source_root=tmp_path)
    imported_errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert (
        "linux-i386 downloaded source artifact review_bundle manifest.file "
        "must be an exact safe file name, got True"
    ) in downloaded_errors
    assert (
        "linux-i386 downloaded source artifact review_bundle archive.size_bytes "
        "must be a positive integer"
    ) in downloaded_errors
    assert (
        "linux-i386 downloaded source artifact review_bundle archive.sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in downloaded_errors
    assert (
        "linux-i386 downloaded source artifact review_bundle sha256s.sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in downloaded_errors
    assert not any("review bundle archive SHA-256 mismatch" in error for error in downloaded_errors)
    assert not any("review bundle sha256s SHA-256 mismatch" in error for error in downloaded_errors)
    assert (
        "linux-i386 imported review_bundle manifest.file must be an exact safe file name, got True"
        in imported_errors
    )
    assert (
        "linux-i386 imported review_bundle archive.size_bytes must be a positive integer"
        in imported_errors
    )
    assert (
        "linux-i386 imported review_bundle archive.sha256 must be a lowercase SHA-256 hex digest"
        in imported_errors
    )
    assert (
        "linux-i386 imported review_bundle sha256s.sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in imported_errors
    assert not any("review bundle archive SHA-256 mismatch" in error for error in imported_errors)
    assert not any("review bundle sha256s SHA-256 mismatch" in error for error in imported_errors)


def test_release_import_hash_and_final_record_helpers_reject_non_path_dirs(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    downloaded_errors = importer.check_downloaded_source_hashes(record, source_root="downloaded")
    imported_errors = importer.check_imported_hashes(record, out_dir="release-assets")
    review_errors = importer.check_imported_review_bundle(record, out_dir=False)
    final_record_errors = importer.validate_downloaded_final_record(record, source_root=["downloaded"])

    assert downloaded_errors == [
        "linux-i386 downloaded artifact directory must be a pathlib.Path, got 'downloaded'"
    ]
    assert imported_errors == [
        "release asset import output directory must be a pathlib.Path, got 'release-assets'"
    ]
    assert review_errors == [
        "release asset import output directory must be a pathlib.Path, got False"
    ]
    assert final_record_errors == [
        "linux-i386 downloaded artifact directory must be a pathlib.Path, got ['downloaded']"
    ]


def test_check_imported_hashes_rejects_ambiguous_review_bundle_files(tmp_path: Path) -> None:
    importer = _load_importer()
    duplicate_record = _record(tmp_path)
    duplicate_file = duplicate_record["review_bundle"]["manifest"]["file"]
    duplicate_record["review_bundle"]["archive"]["file"] = duplicate_file
    collision_record = _record(tmp_path)
    collision_file = str(collision_record["review_bundle"]["manifest"]["file"])
    collision_record["review_bundle"]["sha256s"]["file"] = collision_file.upper()

    duplicate_downloaded_errors = importer.check_downloaded_source_hashes(
        duplicate_record,
        source_root=tmp_path,
    )
    duplicate_imported_errors = importer.check_imported_hashes(duplicate_record, out_dir=tmp_path)
    collision_downloaded_errors = importer.check_downloaded_source_hashes(
        collision_record,
        source_root=tmp_path,
    )
    collision_imported_errors = importer.check_imported_hashes(collision_record, out_dir=tmp_path)

    assert (
        "linux-i386 downloaded source artifact review_bundle files must not contain duplicates: "
        f"['{duplicate_file}']"
    ) in duplicate_downloaded_errors
    assert (
        "linux-i386 imported review_bundle files must not contain duplicates: "
        f"['{duplicate_file}']"
    ) in duplicate_imported_errors
    assert any(
        "linux-i386 downloaded source artifact review_bundle files must not collide on "
        "case-insensitive filesystems" in error
        and collision_file in error
        and collision_file.upper() in error
        for error in collision_downloaded_errors
    )
    assert any(
        "linux-i386 imported review_bundle files must not collide on "
        "case-insensitive filesystems" in error
        and collision_file in error
        and collision_file.upper() in error
        for error in collision_imported_errors
    )


def test_check_downloaded_source_hashes_rejects_symlinked_native_and_review_bundle_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_artifact = next(iter(record["artifact_sha256"]))
    manifest = record["review_bundle"]["manifest"]
    artifact_path = tmp_path / str(first_artifact)
    manifest_path = tmp_path / str(manifest["file"])

    def fake_is_symlink(self: Path) -> bool:
        return self in {artifact_path, manifest_path}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = importer.check_downloaded_source_hashes(record, source_root=tmp_path)

    assert (
        "linux-i386 downloaded source artifact native artifact must not be a symlink: "
        f"{first_artifact}"
    ) in errors
    assert (
        "linux-i386 downloaded source artifact review bundle manifest "
        f"must not be a symlink: {manifest['file']}"
    ) in errors


def test_check_imported_hashes_rejects_symlinked_native_and_review_bundle_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_artifact = next(iter(record["artifact_sha256"]))
    manifest = record["review_bundle"]["manifest"]
    artifact_path = tmp_path / str(first_artifact)
    manifest_path = tmp_path / str(manifest["file"])

    def fake_is_symlink(self: Path) -> bool:
        return self in {artifact_path, manifest_path}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert f"linux-i386 imported native artifact must not be a symlink: {first_artifact}" in errors
    assert (
        f"linux-i386 imported review bundle manifest must not be a symlink: {manifest['file']}"
        in errors
    )


def test_check_imported_hashes_rejects_non_string_artifact_hash_key(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["artifact_sha256"][True] = "0" * 64

    downloaded_errors = importer.check_downloaded_source_hashes(record, source_root=tmp_path)
    imported_errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert (
        "linux-i386 downloaded source artifact artifact_sha256 keys "
        "must be exact safe file names, got True"
    ) in downloaded_errors
    assert (
        "linux-i386 imported native artifact artifact_sha256 keys "
        "must be exact safe file names, got True"
    ) in imported_errors


def test_check_imported_hashes_rejects_malformed_artifact_hash_digest(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_artifact = next(iter(record["artifact_sha256"]))
    record["artifact_sha256"][first_artifact] = True
    second_artifact = next(name for name in record["artifact_sha256"] if name != first_artifact)
    record["artifact_sha256"][second_artifact] = "A" * 64

    downloaded_errors = importer.check_downloaded_source_hashes(record, source_root=tmp_path)
    imported_errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert (
        f"linux-i386 downloaded source artifact artifact_sha256.{first_artifact} "
        "must be a lowercase SHA-256 hex digest"
    ) in downloaded_errors
    assert (
        f"linux-i386 downloaded source artifact artifact_sha256.{second_artifact} "
        "must be a lowercase SHA-256 hex digest"
    ) in downloaded_errors
    assert (
        f"linux-i386 imported native artifact artifact_sha256.{first_artifact} "
        "must be a lowercase SHA-256 hex digest"
    ) in imported_errors
    assert (
        f"linux-i386 imported native artifact artifact_sha256.{second_artifact} "
        "must be a lowercase SHA-256 hex digest"
    ) in imported_errors
    assert not any("native artifact SHA-256 mismatch" in error for error in downloaded_errors)
    assert not any("native artifact SHA-256 mismatch" in error for error in imported_errors)


def test_check_imported_hashes_rejects_case_colliding_artifact_hash_keys(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    first_artifact = next(iter(record["artifact_sha256"]))
    record["artifact_sha256"][first_artifact.upper()] = "0" * 64

    downloaded_errors = importer.check_downloaded_source_hashes(record, source_root=tmp_path)
    imported_errors = importer.check_imported_hashes(record, out_dir=tmp_path)

    assert any(
        "linux-i386 downloaded source artifact artifact_sha256 keys must not collide on "
        "case-insensitive filesystems" in error
        and first_artifact in error
        and first_artifact.upper() in error
        for error in downloaded_errors
    )
    assert any(
        "linux-i386 imported native artifact artifact_sha256 keys must not collide on "
        "case-insensitive filesystems" in error
        and first_artifact in error
        and first_artifact.upper() in error
        for error in imported_errors
    )


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


def test_check_imported_review_bundle_requires_final_record_asset(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    _write_source_files(record, tmp_path)
    (tmp_path / "platform-verified-evidence-linux-i386-final.json").unlink()

    errors = importer.check_imported_review_bundle(record, out_dir=tmp_path)

    assert (
        "linux-i386 imported review bundle validation failed: "
        "linux-i386 finalized accepted-record asset missing from bundle directory: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_check_imported_review_bundle_binds_target_and_release_tag(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_check_platform_review_bundle_artifacts(**kwargs: Any) -> list[str]:
        calls.append(kwargs)
        return []

    monkeypatch.setattr(
        importer,
        "check_platform_review_bundle_artifacts",
        fake_check_platform_review_bundle_artifacts,
    )

    errors = importer.check_imported_review_bundle(record, out_dir=tmp_path)

    assert errors == []
    assert len(calls) == 1
    assert calls[0]["required_targets"] == ("linux-i386",)
    assert calls[0]["required_release_tag"] == "v1.0.2"
    assert calls[0]["require_final_record_assets"] is True


def test_import_record_rejects_tampered_review_bundle_content(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if _is_metadata_command(command):
            return _successful_view(command)
        if _is_artifacts_command(command):
            return _successful_artifacts(command)
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
        final_record.write_bytes(importer.canonical_public_record_bytes(record))
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
    final_record.write_bytes(
        json.dumps(record, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
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


def _source_run_metadata(
    command: list[str],
    **overrides: object,
) -> subprocess.CompletedProcess[str]:
    data = {
        "id": 12345,
        "nodeId": "WFR_kwLO12345",
        "url": "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345",
        "htmlUrl": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "runNumber": 77,
        "workflowId": 445566,
        "workflowUrl": (
            "https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/445566"
        ),
        "jobsUrl": "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/jobs",
        "logsUrl": "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/logs",
        "artifactsUrl": (
            "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/artifacts"
        ),
        "checkSuiteId": 998877,
        "checkSuiteUrl": "https://api.github.com/repos/example/remote-ops-workspace/check-suites/998877",
        "repositoryFullName": "example/remote-ops-workspace",
        "headRepositoryFullName": "example/remote-ops-workspace",
        "repositoryId": 1001,
        "headRepositoryId": 1001,
        "runCreatedAt": "2026-06-30T11:59:00Z",
        "runStartedAt": "2026-06-30T12:00:00Z",
        "runUpdatedAt": "2026-06-30T12:05:00Z",
        "attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "event": "workflow_dispatch",
        "headSha": HEAD_SHA,
        "headBranch": "v1.0.2",
        "path": ".github/workflows/extended-platform-evidence.yml",
    }
    data.update(overrides)
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(data),
    )


def _successful_view(command: list[str]) -> subprocess.CompletedProcess[str]:
    return _source_run_metadata(command)


def _successful_artifacts(
    command: list[str],
    *,
    artifacts: list[dict[str, object]] | None = None,
    total_count: int | None = None,
) -> subprocess.CompletedProcess[str]:
    if artifacts is None:
        artifacts = [
            {
                "id": 98765,
                "node_id": "MDEyOkFydGlmYWN0OTg3NjU=",
                "name": "extended-linux-evidence-linux-i386-v1.0.2",
                "url": (
                    "https://api.github.com/repos/example/remote-ops-workspace/"
                    "actions/artifacts/98765"
                ),
                "archive_download_url": (
                    "https://api.github.com/repos/example/remote-ops-workspace/"
                    "actions/artifacts/98765/zip"
                ),
                "expired": False,
                "size_in_bytes": 4096,
                "created_at": "2026-06-30T12:03:00Z",
                "updated_at": "2026-06-30T12:04:00Z",
                "expires_at": "2026-09-28T12:04:00Z",
                "workflow_run": {
                    "id": 12345,
                    "head_sha": HEAD_SHA,
                    "repository_id": 1001,
                    "head_repository_id": 1001,
                },
            }
        ]
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(
            {
                "total_count": len(artifacts) if total_count is None else total_count,
                "artifacts": artifacts,
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


def _source_run_artifacts_command(importer: Any) -> list[str]:
    return [
        "gh",
        "api",
        "repos/example/remote-ops-workspace/actions/runs/12345/artifacts?per_page=100",
    ]


def _is_metadata_command(command: list[str]) -> bool:
    return command[:3] == [
        "gh",
        "api",
        "repos/example/remote-ops-workspace/actions/runs/12345/attempts/1",
    ]


def _is_artifacts_command(command: list[str]) -> bool:
    return command == [
        "gh",
        "api",
        "repos/example/remote-ops-workspace/actions/runs/12345/artifacts?per_page=100",
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
