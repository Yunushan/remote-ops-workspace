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


def _write_zip_with_symlink_entry(path: Path, entry_name: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload/readme.txt", b"ok\n")
        info = zipfile.ZipInfo(entry_name)
        info.external_attr = 0o120777 << 16
        archive.writestr(info, b"target.txt")


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
