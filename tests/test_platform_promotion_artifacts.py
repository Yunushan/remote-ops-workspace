from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest


def test_platform_promotion_artifact_contract_passes_current_tree() -> None:
    checker = _load_platform_promotion_artifacts_checker()

    assert checker.main(["--contract"]) == 0


def test_platform_promotion_artifacts_accept_linux_i386_evidence(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert errors == []


def test_platform_promotion_artifacts_accept_windows_xp_x64_evidence(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names, manifest_as_object=True)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert errors == []


def test_platform_promotion_artifacts_use_explicit_empty_promotion(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=f"v{checker.read_project_version()}",
        promotion={},
    )

    assert "configs/platform_parity_promotion.json protected_targets must be a list" in errors


def test_platform_promotion_artifact_contract_rejects_non_string_target_id() -> None:
    checker = _load_platform_promotion_artifacts_checker()
    promotion = {"protected_targets": [{"id": True, "promotion_to_100_requires": {}}]}

    errors = checker.check_contract(promotion)

    assert (
        "platform promotion protected target entry id "
        "must be a non-empty string, got True"
    ) in errors


def test_platform_promotion_artifact_contract_rejects_non_string_required_artifact() -> None:
    checker = _load_platform_promotion_artifacts_checker()
    promotion = json.loads(json.dumps(checker.read_json(Path("configs/platform_parity_promotion.json"))))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    target["promotion_to_100_requires"]["required_artifacts"].append(True)

    errors = checker.check_contract(promotion)

    assert any(
        "linux-i386 required_artifacts[" in error
        and "must be a non-empty string, got True" in error
        for error in errors
    )


def test_platform_promotion_artifact_contract_rejects_non_string_validation_command() -> None:
    checker = _load_platform_promotion_artifacts_checker()
    promotion = json.loads(json.dumps(checker.read_json(Path("configs/platform_parity_promotion.json"))))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    target["promotion_to_100_requires"]["artifact_validation_command"] = True

    errors = checker.check_contract(promotion)

    assert (
        "linux-i386 artifact_validation_command must be a string, got True"
    ) in errors


def test_platform_promotion_artifacts_reject_non_string_required_artifact(
    tmp_path: Path,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    promotion = json.loads(json.dumps(checker.read_json(Path("configs/platform_parity_promotion.json"))))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    target["promotion_to_100_requires"]["required_artifacts"].append(True)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
        promotion=promotion,
    )

    assert any(
        "linux-i386 required_artifacts[" in error
        and "must be a non-empty string, got True" in error
        for error in errors
    )
    assert not any("artifacts missing expected files: ['True']" in error for error in errors)


def test_platform_promotion_artifacts_reject_checksum_mismatch(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    sidecar = _write_artifact_set(tmp_path, names)
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(sidecar.read_text(encoding="utf-8")[:64], "0" * 64, 1),
        encoding="utf-8",
    )

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("linux-armhf checksum mismatch" in error for error in errors)


def test_platform_promotion_artifacts_reject_missing_manifest_record(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    manifest.write_text("[]\n", encoding="utf-8")

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("windows-xp-native-x86 native manifest missing payload records" in error for error in errors)


def test_platform_promotion_artifacts_reject_manifest_path_reference(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    first_name = str(records[0]["file"])
    records[0]["file"] = f"dist/{first_name}"
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    _rewrite_sidecar_only(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x86 native manifest record file/path/name must be an exact safe file name: "
        f"'dist/{first_name}'"
    ) in errors


def test_platform_promotion_artifacts_reject_duplicate_checksum_reference(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    sidecar = _write_artifact_set(tmp_path, names)
    first_line = sidecar.read_text(encoding="utf-8").splitlines()[0]
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + first_line + "\n", encoding="utf-8")

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("linux-i386 checksum sidecar has duplicate references" in error for error in errors)


def test_platform_promotion_artifacts_reject_checksum_path_reference(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    sidecar = _write_artifact_set(tmp_path, names)
    payload_name = next(
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    )
    sidecar.write_text(
        sidecar.read_text(encoding="utf-8").replace(f"  {payload_name}", f"  ../{payload_name}", 1),
        encoding="utf-8",
    )

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"linux-i386 checksum sidecar reference must be an exact safe file name: '../{payload_name}'"
        in errors
    )


def test_platform_promotion_artifacts_reject_symlinked_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    symlink_name = next(name for name in names if name.endswith(".deb"))

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert f"linux-i386 artifacts must not contain symlinks: ['{symlink_name}']" in errors


def test_platform_promotion_artifacts_reject_non_file_artifact_entries(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    (tmp_path / "nested").mkdir()

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert "linux-i386 artifacts must contain only regular files: ['nested']" in errors


def test_platform_promotion_artifacts_reject_case_colliding_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    original_name = next(name for name in names if name.endswith(".deb"))
    colliding_name = original_name.upper()
    root = tmp_path.resolve()
    colliding_path = root / colliding_name
    path_type = type(tmp_path)
    original_iterdir = path_type.iterdir
    original_is_file = path_type.is_file

    def fake_iterdir(self: Path):
        entries = list(original_iterdir(self))
        if self == root:
            entries.append(colliding_path)
        return iter(entries)

    def fake_is_file(self: Path) -> bool:
        if self == colliding_path:
            return True
        return original_is_file(self)

    monkeypatch.setattr(path_type, "iterdir", fake_iterdir)
    monkeypatch.setattr(path_type, "is_file", fake_is_file)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    case_errors = [
        error
        for error in errors
        if error.startswith("linux-i386 artifact directory entries must not collide")
    ]
    assert case_errors
    assert original_name in case_errors[0]
    assert colliding_name in case_errors[0]


def test_platform_promotion_artifacts_reject_symlinked_artifact_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert f"windows-xp-native-x86 artifact directory must not be a symlink: {tmp_path}" in errors


def test_platform_promotion_artifacts_reject_file_shaped_artifact_directory(
    tmp_path: Path,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    assets_dir = tmp_path / "artifacts.zip"
    assets_dir.mkdir()

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=assets_dir,
        tag=tag,
    )

    assert errors == [
        f"linux-i386 artifact directory must be a directory path, got {assets_dir.as_posix()!r}"
    ]


def test_platform_promotion_artifact_path_helpers_reject_non_path_args() -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"

    assert checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir="artifacts",
        tag=tag,
    ) == ["linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"]
    assert checker.check_artifact_format("linux-i386", "artifact.zip") == [
        "linux-i386 artifact path must be a pathlib.Path, got 'artifact.zip'"
    ]
    assert checker.check_archive_structure("linux-i386", "artifact.zip") == [
        "linux-i386 archive artifact path must be a pathlib.Path, got 'artifact.zip'"
    ]
    assert checker.check_zip_structure("linux-i386", "artifact.zip") == [
        "linux-i386 ZIP artifact path must be a pathlib.Path, got 'artifact.zip'"
    ]
    assert checker.check_tar_gz_structure("linux-i386", "artifact.tar.gz") == [
        "linux-i386 tar.gz artifact path must be a pathlib.Path, got 'artifact.tar.gz'"
    ]
    assert checker.check_checksum_sidecar(
        "linux-i386",
        "artifacts",
        {"remote-ops-workspace-v1.0.2-linux-i386-SHA256SUMS.txt"},
    ) == ["linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"]
    assert checker.check_native_manifest(
        "linux-i386",
        "artifacts",
        {"remote-ops-workspace-v1.0.2-linux-i686-native-manifest.json"},
    ) == ["linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"]
    assert checker.check_path_parent_symlinks("artifacts", "linux-i386 artifact directory") == [
        "linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"
    ]
    assert checker.check_directory_path_hint("artifacts", "linux-i386 artifact directory") == [
        "linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"
    ]
    assert checker.check_path_not_reserved_workspace_root(
        "artifacts",
        "linux-i386 artifact directory",
    ) == ["linux-i386 artifact directory path must be a pathlib.Path, got 'artifacts'"]


def test_platform_promotion_artifacts_reject_reserved_workspace_artifact_directory() -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    assets_dir = Path(".github") / "linux-i386" / tag / "artifacts"

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=assets_dir,
        tag=tag,
    )

    assert errors == [
        "linux-i386 artifact directory must not point inside "
        f"reserved workspace directory '.github': {assets_dir}"
    ]
    assert not assets_dir.exists()


def test_platform_promotion_artifacts_reject_symlinked_artifact_directory_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    linked_parent = tmp_path / "linked-artifacts"
    assets_dir = linked_parent / "linux-i386"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=assets_dir,
        tag=tag,
    )

    assert errors == [
        f"linux-i386 artifact directory path must not contain symlinked directories: {linked_parent}"
    ]


def test_platform_promotion_artifacts_reject_unexpected_manifest_record(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    records.append({"file": "remote-ops-workspace-v1.0.2-windows-xp-x64-extra.zip", "size_bytes": 1, "sha256": "0" * 64})
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("windows-xp-native-x64 native manifest contains unexpected payload records" in error for error in errors)


def test_platform_promotion_artifacts_reject_duplicate_manifest_record(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    records.append(dict(records[0]))
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("linux-armhf native manifest contains duplicate payload records" in error for error in errors)


def test_platform_promotion_artifacts_reject_case_colliding_manifest_record(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    first_record = dict(records[0])
    first_name = str(first_record["file"])
    first_record["file"] = first_name.upper()
    records.append(first_record)
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any(
        "linux-armhf native manifest payload records must not collide on "
        "case-insensitive filesystems" in error
        and first_name in error
        and first_name.upper() in error
        for error in errors
    )


def test_platform_promotion_artifacts_reject_boolean_manifest_size_bytes(
    tmp_path: Path,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    payload = tmp_path / "remote-ops-workspace-v1.0.2-linux-i386.deb"
    payload.write_bytes(b"x")
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-linux-i386-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "file": payload.name,
                    "architecture": "i386",
                    "format": "deb",
                    "size_bytes": True,
                    "sha256": _sha256(payload),
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    errors = checker.check_native_manifest(
        "linux-i386",
        tmp_path,
        {payload.name, manifest.name},
    )

    assert (
        "linux-i386 native manifest record "
        "remote-ops-workspace-v1.0.2-linux-i386.deb missing positive size_bytes"
    ) in errors


def test_platform_promotion_artifacts_reject_malformed_manifest_hash_and_bindings(
    tmp_path: Path,
) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    payload = tmp_path / "remote-ops-workspace-v1.0.2-linux-i386.deb"
    payload.write_bytes(b"x")
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-linux-i386-manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "file": payload.name,
                    "architecture": True,
                    "format": False,
                    "size_bytes": payload.stat().st_size,
                    "sha256": True,
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    errors = checker.check_native_manifest(
        "linux-i386",
        tmp_path,
        {payload.name, manifest.name},
    )

    assert (
        "linux-i386 native manifest record "
        "remote-ops-workspace-v1.0.2-linux-i386.deb sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in errors
    assert (
        "linux-i386 native manifest record "
        "remote-ops-workspace-v1.0.2-linux-i386.deb architecture must be a string, got True"
    ) in errors
    assert (
        "linux-i386 native manifest record "
        "remote-ops-workspace-v1.0.2-linux-i386.deb format must be a string, got False"
    ) in errors
    assert all("native manifest checksum mismatch" not in error for error in errors)


def test_platform_promotion_artifacts_reject_manifest_architecture_drift(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    deb_record = next(record for record in records if str(record["file"]).endswith(".deb"))
    deb_record["architecture"] = "arm64"
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    _rewrite_sidecar_only(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any(
        "linux-armhf native manifest record "
        "remote-ops-workspace-v1.0.4-linux-armhf.deb architecture must be 'armhf', got 'arm64'"
        in error
        for error in errors
    )


def test_platform_promotion_artifacts_reject_manifest_format_drift(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names)
    manifest = next(tmp_path.glob("*manifest.json"))
    records = json.loads(manifest.read_text(encoding="utf-8"))
    records[0]["format"] = "tar.gz"
    manifest.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    _rewrite_sidecar_only(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any(
        "windows-xp-native-x64 native manifest record "
        "remote-ops-workspace-v1.0.4-windows-xp-x64-native.zip format must be 'zip', got 'tar.gz'"
        in error
        for error in errors
    )


def test_platform_promotion_artifacts_reject_invalid_payload_signature(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    deb = next(tmp_path.glob("*.deb"))
    deb.write_bytes(b"not a deb package\n")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("linux-i386 artifact has invalid file signature" in error for error in errors)


def test_platform_promotion_artifacts_reject_unreadable_tarball(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    tarball = next(tmp_path.glob("*.tar.gz"))
    tarball.write_bytes(bytes.fromhex("1f8b") + b"not a tar archive\n")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("linux-armhf tar.gz artifact is not a readable archive" in error for error in errors)


def test_platform_promotion_artifacts_reject_unreadable_zip(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    zip_path.write_bytes(b"PK\x03\x04not a zip archive\n")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any("windows-xp-native-x86 ZIP artifact is not a readable archive" in error for error in errors)


def test_platform_promotion_artifacts_reject_unsafe_zip_entry(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_entries(zip_path, {"payload/readme.txt": b"ok\n", "../escape.txt": b"escape\n"})
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x86 ZIP artifact {zip_path.name} entries must use safe relative paths: "
        "['../escape.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_zip_symlink_entry(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_symlink_entry(zip_path, "payload/link.txt")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x64 ZIP artifact {zip_path.name} entries must not be symlinks: "
        "['payload/link.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_zip_encrypted_entry(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_encrypted_entry(zip_path, "payload/proof.txt")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x64 ZIP artifact {zip_path.name} entries must not be encrypted: "
        "['payload/proof.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_zip_special_file_entry(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_mode_entry(zip_path, "payload/device", 0o020666)
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x86 ZIP artifact {zip_path.name} entries must be regular files or directories: "
        "['payload/device']"
    ) in errors


def test_platform_promotion_artifacts_reject_duplicate_zip_entries(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    with pytest.warns(UserWarning, match="Duplicate name"):
        _write_zip_with_duplicate_entries(zip_path, "payload/readme.txt")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x86 ZIP artifact {zip_path.name} entries must not contain duplicates: "
        "['payload/readme.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_zip_case_collisions(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x64", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_entries(
        zip_path,
        {
            "payload/readme.txt": b"ok\n",
            "PAYLOAD/README.TXT": b"other\n",
        },
    )
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x64",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any(
        f"windows-xp-native-x64 ZIP artifact {zip_path.name} entries must not collide on "
        "case-insensitive filesystems" in error
        and "payload/readme.txt" in error
        and "PAYLOAD/README.TXT" in error
        for error in errors
    )


def test_platform_promotion_artifacts_reject_zip_file_prefix_collision(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "windows-xp-native-x86", tag)
    _write_artifact_set(tmp_path, names)
    zip_path = next(tmp_path.glob("*.zip"))
    _write_zip_with_entries(
        zip_path,
        {
            "payload": b"file\n",
            "payload/readme.txt": b"nested\n",
        },
    )
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="windows-xp-native-x86",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"windows-xp-native-x86 ZIP artifact {zip_path.name} entries must not contain "
        "file/path-prefix collisions: ['payload -> payload/readme.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_tar_symlink_entry(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    tarball = next(tmp_path.glob("*.tar.gz"))
    _write_tar_with_symlink_entry(tarball, "payload/link.txt")
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"linux-armhf tar.gz artifact {tarball.name} entries must be regular files or directories: "
        "['payload/link.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_duplicate_tar_entries(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    tarball = next(tmp_path.glob("*.tar.gz"))
    _write_tar_with_entries(
        tarball,
        [
            ("payload/readme.txt", b"first\n"),
            ("payload/readme.txt", b"second\n"),
        ],
    )
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"linux-i386 tar.gz artifact {tarball.name} entries must not contain duplicates: "
        "['payload/readme.txt']"
    ) in errors


def test_platform_promotion_artifacts_reject_tar_case_collisions(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-armhf", tag)
    _write_artifact_set(tmp_path, names)
    tarball = next(tmp_path.glob("*.tar.gz"))
    _write_tar_with_entries(
        tarball,
        [
            ("payload/readme.txt", b"ok\n"),
            ("PAYLOAD/README.TXT", b"other\n"),
        ],
    )
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-armhf",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert any(
        f"linux-armhf tar.gz artifact {tarball.name} entries must not collide on "
        "case-insensitive filesystems" in error
        and "payload/readme.txt" in error
        and "PAYLOAD/README.TXT" in error
        for error in errors
    )


def test_platform_promotion_artifacts_reject_tar_file_prefix_collision(tmp_path: Path) -> None:
    checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{checker.read_project_version()}"
    names = _required_names(checker, "linux-i386", tag)
    _write_artifact_set(tmp_path, names)
    tarball = next(tmp_path.glob("*.tar.gz"))
    _write_tar_with_entries(
        tarball,
        [
            ("payload", b"file\n"),
            ("payload/readme.txt", b"nested\n"),
        ],
    )
    _rewrite_manifest_and_sidecar(tmp_path, names)

    errors = checker.check_platform_promotion_artifacts(
        target="linux-i386",
        assets_dir=tmp_path,
        tag=tag,
    )

    assert (
        f"linux-i386 tar.gz artifact {tarball.name} entries must not contain "
        "file/path-prefix collisions: ['payload -> payload/readme.txt']"
    ) in errors


def _required_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_artifact_set(root: Path, names: list[str], *, manifest_as_object: bool = False) -> Path:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]

    for name in payload_names:
        (root / name).write_bytes(_payload_bytes(name))

    return _rewrite_manifest_and_sidecar(root, names, manifest_as_object=manifest_as_object)


def _rewrite_manifest_and_sidecar(root: Path, names: list[str], *, manifest_as_object: bool = False) -> Path:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]
    manifest_name = next(name for name in names if name.endswith("manifest.json"))
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))

    records = [
        {
            "file": name,
            **_manifest_record_metadata(name),
            "size_bytes": (root / name).stat().st_size,
            "sha256": _sha256(root / name),
        }
        for name in payload_names
    ]
    manifest_data: Any = {"artifacts": records} if manifest_as_object else records
    manifest = root / manifest_name
    manifest.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    sidecar = root / sidecar_name
    sidecar_names = [*payload_names, manifest_name]
    sidecar.write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )
    return sidecar


def _rewrite_sidecar_only(root: Path, names: list[str]) -> Path:
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    sidecar_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt")
    ]
    sidecar = root / sidecar_name
    sidecar.write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )
    return sidecar


def _manifest_record_metadata(name: str) -> dict[str, str]:
    if name.endswith(".tar.gz"):
        return {"architecture": _artifact_architecture(name), "format": "tar.gz"}
    if name.endswith(".AppImage"):
        return {"architecture": _artifact_architecture(name), "format": "AppImage"}
    if name.endswith(".deb"):
        return {"architecture": _artifact_architecture(name), "format": "deb"}
    if name.endswith(".rpm"):
        return {"architecture": _artifact_architecture(name), "format": "rpm"}
    if name.endswith(".zip"):
        return {"architecture": _artifact_architecture(name), "format": "zip"}
    return {}


def _artifact_architecture(name: str) -> str:
    if "-linux-i386." in name:
        return "i386"
    if "-linux-i686." in name or "-linux-i686-native." in name:
        return "i686"
    if "-linux-armhf." in name or "-linux-armhf-native." in name:
        return "armhf"
    if "-linux-armv7hl." in name:
        return "armv7hl"
    if "-windows-xp-x86-native." in name:
        return "x86"
    if "-windows-xp-x64-native." in name:
        return "x64"
    return ""


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    if name.endswith(".deb"):
        return b"!<arch>\n" + payload
    if name.endswith(".rpm"):
        return bytes.fromhex("edabeedb") + payload
    if name.endswith(".AppImage"):
        return b"\x7fELF" + payload
    if name.endswith(".tar.gz"):
        return _tar_gz_bytes(name, payload)
    if name.endswith(".zip"):
        return _zip_bytes(name, payload)
    return payload


def _tar_gz_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=f"{name}.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}.txt", payload)
    return buffer.getvalue()


def _write_zip_with_entries(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)


def _write_zip_with_duplicate_entries(path: Path, entry_name: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(entry_name, b"first\n")
        archive.writestr(entry_name, b"second\n")


def _write_zip_with_symlink_entry(path: Path, entry_name: str) -> None:
    _write_zip_with_mode_entry(path, entry_name, 0o120777)


def _write_zip_with_encrypted_entry(path: Path, entry_name: str) -> None:
    _write_zip_with_mode_entry(path, entry_name, 0o100644)
    path.write_bytes(_set_zip_entry_flag_bits(path.read_bytes(), entry_name, 0x1))


def _write_zip_with_mode_entry(path: Path, entry_name: str, mode: int) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload/readme.txt", b"ok\n")
        info = zipfile.ZipInfo(entry_name)
        info.external_attr = mode << 16
        archive.writestr(info, b"target.txt")


def _set_zip_entry_flag_bits(raw_bytes: bytes, entry_name: str, flag_bits: int) -> bytes:
    data = bytearray(raw_bytes)
    wanted = entry_name.encode("utf-8")
    index = 0
    while index < len(data) - 4:
        signature = bytes(data[index:index + 4])
        if signature == b"PK\x03\x04":
            name_length = int.from_bytes(data[index + 26:index + 28], "little")
            extra_length = int.from_bytes(data[index + 28:index + 30], "little")
            name_start = index + 30
            name_end = name_start + name_length
            if bytes(data[name_start:name_end]) == wanted:
                data[index + 6:index + 8] = flag_bits.to_bytes(2, "little")
            index = name_end + extra_length
            continue
        if signature == b"PK\x01\x02":
            name_length = int.from_bytes(data[index + 28:index + 30], "little")
            extra_length = int.from_bytes(data[index + 30:index + 32], "little")
            comment_length = int.from_bytes(data[index + 32:index + 34], "little")
            name_start = index + 46
            name_end = name_start + name_length
            if bytes(data[name_start:name_end]) == wanted:
                data[index + 8:index + 10] = flag_bits.to_bytes(2, "little")
            index = name_end + extra_length + comment_length
            continue
        index += 1
    return bytes(data)


def _write_tar_with_symlink_entry(path: Path, entry_name: str) -> None:
    payload = b"ok\n"
    with tarfile.open(path, mode="w:gz") as archive:
        info = tarfile.TarInfo(name="payload/readme.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
        link = tarfile.TarInfo(name=entry_name)
        link.type = tarfile.SYMTYPE
        link.linkname = "../target.txt"
        archive.addfile(link)


def _write_tar_with_entries(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for name, payload in entries:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
