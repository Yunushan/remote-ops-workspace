from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_verified_evidence import (  # noqa: E402
    RESERVED_WORKSPACE_ROOTS,
    case_insensitive_name_collisions,
    directory_path_has_file_suffix,
)

PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
PYPROJECT_PATH = ROOT / "pyproject.toml"
CHECKSUM_SUFFIX = "SHA256SUMS.txt"
MANIFEST_SUFFIX = "manifest.json"
FORMAT_SIGNATURES: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    (".deb", (b"!<arch>\n",)),
    (".rpm", (bytes.fromhex("edabeedb"),)),
    (".AppImage", (b"\x7fELF",)),
    (".tar.gz", (bytes.fromhex("1f8b"),)),
    (".zip", (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")),
)
MANIFEST_ARCHITECTURE_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "linux-i386": (
        (r"-linux-i386\.deb$", "i386"),
        (r"-linux-i686\.rpm$", "i686"),
        (r"-linux-i686\.AppImage$", "i686"),
        (r"-linux-i686-native\.tar\.gz$", "i686"),
    ),
    "linux-armhf": (
        (r"-linux-armhf\.deb$", "armhf"),
        (r"-linux-armv7hl\.rpm$", "armv7hl"),
        (r"-linux-armhf\.AppImage$", "armhf"),
        (r"-linux-armhf-native\.tar\.gz$", "armhf"),
    ),
    "windows-xp-native-x86": (
        (r"-windows-xp-x86-native\.zip$", "x86"),
    ),
    "windows-xp-native-x64": (
        (r"-windows-xp-x64-native\.zip$", "x64"),
    ),
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    promotion = read_json(PROMOTION_PATH)
    if args.contract or args.target is None:
        errors = check_contract(promotion)
    else:
        if args.assets_dir is None:
            errors = ["--assets-dir is required when --target is used"]
        else:
            errors = check_platform_promotion_artifacts(
                target=args.target,
                assets_dir=args.assets_dir,
                tag=args.tag,
                strict=args.strict,
                promotion=promotion,
            )
    if errors:
        for error in errors:
            print(f"platform promotion artifacts: {error}", file=sys.stderr)
        return 1
    print("platform promotion artifact checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate real artifact evidence for extended platform promotion."
    )
    parser.add_argument(
        "--contract",
        action="store_true",
        help="validate that the promotion config declares artifact validation commands",
    )
    parser.add_argument(
        "--target",
        choices=sorted(expected_target_ids(read_json(PROMOTION_PATH))),
        help="promotion target to validate",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="directory containing the target's built native artifacts",
    )
    parser.add_argument(
        "--tag",
        help="release tag to validate, for example v1.0.2. Defaults to pyproject.toml",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="reject extra files in the artifact directory",
    )
    return parser.parse_args(argv)


def check_contract(promotion: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = promotion_entries(promotion, errors)
    for target_id, entry in entries.items():
        command = artifact_validation_command(entry, target_id, errors)
        artifact_dir = "<target-release-artifact-dir>"
        expected = (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target_id} --assets-dir {artifact_dir} --tag v<project.version> --strict"
        )
        if command != expected:
            errors.append(f"{target_id} artifact_validation_command must be: {expected}")
        required = required_artifacts(entry, target_id, errors)
        if not required:
            errors.append(f"{target_id} must declare required promotion artifacts")
            continue
        if not any(item.endswith(CHECKSUM_SUFFIX) for item in required):
            errors.append(f"{target_id} must require a {CHECKSUM_SUFFIX} sidecar")
        if not any(item.endswith(MANIFEST_SUFFIX) for item in required):
            errors.append(f"{target_id} must require a native {MANIFEST_SUFFIX}")
    return errors


def check_platform_promotion_artifacts(
    *,
    target: str,
    assets_dir: object,
    tag: str | None = None,
    strict: bool = False,
    promotion: dict[str, Any] | None = None,
) -> list[str]:
    promotion_data = read_json(PROMOTION_PATH) if promotion is None else promotion
    errors: list[str] = []
    entries = promotion_entries(promotion_data, errors)
    entry = entries.get(target)
    if entry is None:
        return [*errors, f"unknown promotion target: {target}"]
    version = version_from_tag(tag or f"v{read_project_version()}", errors)
    if errors:
        return errors
    path_errors, assets_path = path_arg_value(assets_dir, f"{target} artifact directory")
    if path_errors:
        return path_errors
    assert assets_path is not None
    hint_errors = check_directory_path_hint(assets_path, f"{target} artifact directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(assets_path, f"{target} artifact directory")
    if reserved_errors:
        return reserved_errors
    if assets_path.is_symlink():
        return [f"{target} artifact directory must not be a symlink: {assets_path}"]
    parent_errors = check_path_parent_symlinks(assets_path, f"{target} artifact directory")
    if parent_errors:
        return parent_errors
    root = assets_path.resolve()
    if not root.is_dir():
        return [f"artifact directory missing: {assets_path}"]
    entries_in_root = list(root.iterdir())
    entry_name_collisions = case_insensitive_name_collisions({path.name for path in entries_in_root})
    if entry_name_collisions:
        errors.append(
            f"{target} artifact directory entries must not collide on "
            f"case-insensitive filesystems: {entry_name_collisions}"
        )
    symlinks = sorted(path.name for path in entries_in_root if path.is_symlink())
    if symlinks:
        errors.append(f"{target} artifacts must not contain symlinks: {symlinks}")
    non_files = sorted(path.name for path in entries_in_root if not path.is_file() and not path.is_symlink())
    if non_files:
        errors.append(f"{target} artifacts must contain only regular files: {non_files}")

    expected = {expand_version(item, version) for item in required_artifacts(entry, target, errors)}
    actual = {path.name for path in entries_in_root if path.is_file()}
    missing = sorted(expected - actual)
    if missing:
        errors.append(f"{target} artifacts missing expected files: {missing}")
    if strict:
        extra = sorted(actual - expected)
        if extra:
            errors.append(f"{target} artifacts include unexpected files: {extra}")

    for filename in sorted(expected & actual):
        path = root / filename
        if path.stat().st_size <= 0:
            errors.append(f"{target} artifact is empty: {filename}")
        errors.extend(check_artifact_format(target, path))

    errors.extend(check_checksum_sidecar(target, root, expected))
    errors.extend(check_native_manifest(target, root, expected))
    return errors


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def check_artifact_format(target: str, path: object) -> list[str]:
    path_errors, path_value = path_arg_value(path, f"{target} artifact")
    if path_errors:
        return path_errors
    assert path_value is not None
    expected_signatures = signatures_for(path_value.name)
    if not expected_signatures:
        return []
    max_signature = max(len(signature) for signature in expected_signatures)
    try:
        with path_value.open("rb") as handle:
            header = handle.read(max_signature)
    except OSError as exc:
        return [f"{target} artifact cannot be read for format validation: {path_value.name}: {exc}"]
    if any(header.startswith(signature) for signature in expected_signatures):
        return check_archive_structure(target, path_value)
    expected_hex = ", ".join(signature.hex() for signature in expected_signatures)
    return [f"{target} artifact has invalid file signature for {path_value.name}; expected one of {expected_hex}"]


def check_archive_structure(target: str, path: object) -> list[str]:
    path_errors, path_value = path_arg_value(path, f"{target} archive artifact")
    if path_errors:
        return path_errors
    assert path_value is not None
    if path_value.name.endswith(".zip"):
        return check_zip_structure(target, path_value)
    if path_value.name.endswith(".tar.gz"):
        return check_tar_gz_structure(target, path_value)
    return []


def check_zip_structure(target: str, path: object) -> list[str]:
    path_errors, path_value = path_arg_value(path, f"{target} ZIP artifact")
    if path_errors:
        return path_errors
    assert path_value is not None
    try:
        with zipfile.ZipFile(path_value) as archive:
            infos = archive.infolist()
            entries = [item for item in infos if not item.is_dir()]
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"{target} ZIP artifact is not a readable archive: {path_value.name}: {exc}"]
    errors = check_zip_entry_safety(target, path_value.name, infos)
    if not entries:
        errors.append(f"{target} ZIP artifact must contain at least one file: {path_value.name}")
    empty_entries = sorted(item.filename for item in entries if item.file_size <= 0)
    if empty_entries:
        errors.append(f"{target} ZIP artifact contains empty files: {empty_entries}")
    return errors


def check_tar_gz_structure(target: str, path: object) -> list[str]:
    path_errors, path_value = path_arg_value(path, f"{target} tar.gz artifact")
    if path_errors:
        return path_errors
    assert path_value is not None
    try:
        with tarfile.open(path_value, mode="r:gz") as archive:
            members = archive.getmembers()
            entries = [item for item in members if item.isfile()]
    except (OSError, tarfile.TarError) as exc:
        return [f"{target} tar.gz artifact is not a readable archive: {path_value.name}: {exc}"]
    errors = check_tar_entry_safety(target, path_value.name, members)
    if not entries:
        errors.append(f"{target} tar.gz artifact must contain at least one file: {path_value.name}")
    empty_entries = sorted(item.name for item in entries if item.size <= 0)
    if empty_entries:
        errors.append(f"{target} tar.gz artifact contains empty files: {empty_entries}")
    return errors


def check_zip_entry_safety(target: str, archive_name: str, infos: list[zipfile.ZipInfo]) -> list[str]:
    encrypted_entries = sorted(info.filename for info in infos if zip_entry_is_encrypted(info))
    symlink_entries = sorted(info.filename for info in infos if zip_entry_is_symlink(info))
    non_regular_entries = sorted(
        info.filename for info in infos if zip_entry_declares_non_regular_file(info)
    )
    entry_names = [zip_entry_safety_name(info) for info in infos]
    entry_counts: dict[str, int] = {}
    for name in entry_names:
        entry_counts[name] = entry_counts.get(name, 0) + 1
    duplicate_entries = sorted(name for name, count in entry_counts.items() if count > 1)
    case_collisions = case_insensitive_name_collisions(set(entry_names))
    file_prefix_collisions = zip_file_prefix_collisions(infos)
    unsafe_entries = sorted(
        info.filename
        for info in infos
        if not archive_entry_name_is_safe(zip_entry_safety_name(info))
    )
    errors: list[str] = []
    if encrypted_entries:
        errors.append(f"{target} ZIP artifact {archive_name} entries must not be encrypted: {encrypted_entries}")
    if symlink_entries:
        errors.append(f"{target} ZIP artifact {archive_name} entries must not be symlinks: {symlink_entries}")
    if non_regular_entries:
        errors.append(
            f"{target} ZIP artifact {archive_name} entries must be regular files or directories: "
            f"{non_regular_entries}"
        )
    if duplicate_entries:
        errors.append(
            f"{target} ZIP artifact {archive_name} entries must not contain duplicates: "
            f"{duplicate_entries}"
        )
    if case_collisions:
        errors.append(
            f"{target} ZIP artifact {archive_name} entries must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    if file_prefix_collisions:
        errors.append(
            f"{target} ZIP artifact {archive_name} entries must not contain file/path-prefix "
            f"collisions: {file_prefix_collisions}"
        )
    if unsafe_entries:
        errors.append(f"{target} ZIP artifact {archive_name} entries must use safe relative paths: {unsafe_entries}")
    return errors


def zip_entry_safety_name(info: zipfile.ZipInfo) -> str:
    return info.filename.rstrip("/") if info.is_dir() else info.filename


def zip_file_prefix_collisions(infos: list[zipfile.ZipInfo]) -> list[str]:
    names = sorted({zip_entry_safety_name(info) for info in infos})
    file_names = sorted({info.filename for info in infos if not info.is_dir()})
    return sorted(
        f"{parent} -> {child}"
        for parent in file_names
        for child in names
        if parent != child and child.startswith(f"{parent}/")
    )


def zip_entry_is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)


def zip_entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    return file_type == 0o120000


def zip_entry_declares_non_regular_file(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type in (0, 0o100000, 0o120000) or info.is_dir():
        return False
    return True


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def check_path_parent_symlinks(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    check_path = path_value if path_value.is_absolute() else Path.cwd() / path_value
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink() and not is_allowed_platform_parent_symlink(parent):
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    raw_path = path_value.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def check_path_not_reserved_workspace_root(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    roots: list[Path] = [Path.cwd(), ROOT]
    seen_roots: set[Path] = set()
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if root_resolved in seen_roots:
            continue
        seen_roots.add(root_resolved)
        path_resolved = (
            path_value if path_value.is_absolute() else root_resolved / path_value
        ).resolve(strict=False)
        try:
            relative = path_resolved.relative_to(root_resolved)
        except ValueError:
            continue
        parts = tuple(part for part in relative.parts if part not in ("", "."))
        if not parts:
            continue
        reserved_root = parts[0]
        if reserved_root in RESERVED_WORKSPACE_ROOTS:
            return [
                f"{label} must not point inside reserved workspace directory "
                f"{reserved_root!r}: {path_value}"
            ]
    return []


def check_tar_entry_safety(target: str, archive_name: str, members: list[tarfile.TarInfo]) -> list[str]:
    unsafe_entries = sorted(member.name for member in members if not archive_entry_name_is_safe(member.name))
    unsafe_types = sorted(member.name for member in members if not member.isfile() and not member.isdir())
    entry_names = [tar_entry_safety_name(member) for member in members]
    entry_counts: dict[str, int] = {}
    for name in entry_names:
        entry_counts[name] = entry_counts.get(name, 0) + 1
    duplicate_entries = sorted(name for name, count in entry_counts.items() if count > 1)
    case_collisions = case_insensitive_name_collisions(set(entry_names))
    file_prefix_collisions = tar_file_prefix_collisions(members)
    errors: list[str] = []
    if unsafe_entries:
        errors.append(f"{target} tar.gz artifact {archive_name} entries must use safe relative paths: {unsafe_entries}")
    if unsafe_types:
        errors.append(
            f"{target} tar.gz artifact {archive_name} entries must be regular files or directories: {unsafe_types}"
        )
    if duplicate_entries:
        errors.append(
            f"{target} tar.gz artifact {archive_name} entries must not contain duplicates: "
            f"{duplicate_entries}"
        )
    if case_collisions:
        errors.append(
            f"{target} tar.gz artifact {archive_name} entries must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    if file_prefix_collisions:
        errors.append(
            f"{target} tar.gz artifact {archive_name} entries must not contain file/path-prefix "
            f"collisions: {file_prefix_collisions}"
        )
    return errors


def tar_entry_safety_name(member: tarfile.TarInfo) -> str:
    return member.name.rstrip("/") if member.isdir() else member.name


def tar_file_prefix_collisions(members: list[tarfile.TarInfo]) -> list[str]:
    names = sorted({tar_entry_safety_name(member) for member in members})
    file_names = sorted({member.name for member in members if member.isfile()})
    return sorted(
        f"{parent} -> {child}"
        for parent in file_names
        for child in names
        if parent != child and child.startswith(f"{parent}/")
    )


def archive_entry_name_is_safe(name: str) -> bool:
    if not name or "\\" in name:
        return False
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    return not posix_path.is_absolute() and not windows_path.is_absolute() and not windows_path.drive


def signatures_for(filename: str) -> tuple[bytes, ...]:
    for suffix, signatures in FORMAT_SIGNATURES:
        if filename.endswith(suffix):
            return signatures
    return ()


def check_checksum_sidecar(target: str, root: object, expected: set[str]) -> list[str]:
    path_errors, root_path = path_arg_value(root, f"{target} artifact directory")
    if path_errors:
        return path_errors
    assert root_path is not None
    errors: list[str] = []
    sidecars = sorted(item for item in expected if item.endswith(CHECKSUM_SUFFIX))
    if len(sidecars) != 1:
        return [f"{target} must declare exactly one checksum sidecar, got {sidecars}"]
    sidecar = root_path / sidecars[0]
    if not sidecar.is_file():
        return errors
    try:
        lines = [line.strip() for line in sidecar.read_text(encoding="utf-8").splitlines() if line.strip()]
    except UnicodeDecodeError:
        return [f"{target} checksum sidecar must be UTF-8 text: {sidecar.name}"]
    if not lines:
        return [f"{target} checksum sidecar must contain entries: {sidecar.name}"]

    expected_references = expected - {sidecar.name}
    referenced: set[str] = set()
    reference_counts: dict[str, int] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line)
        if not match:
            errors.append(f"{target} checksum sidecar has invalid line: {line}")
            continue
        checksum, raw_name = match.groups()
        if not artifact_reference_name_is_safe(raw_name):
            errors.append(
                f"{target} checksum sidecar reference must be an exact safe file name: {raw_name!r}"
            )
            continue
        filename = raw_name
        referenced.add(filename)
        reference_counts[filename] = reference_counts.get(filename, 0) + 1
        if filename not in expected_references:
            errors.append(f"{target} checksum sidecar references unexpected file: {filename}")
            continue
        path = root_path / filename
        if not path.is_file():
            errors.append(f"{target} checksum sidecar references missing file: {filename}")
            continue
        actual = sha256_file(path)
        if actual != checksum:
            errors.append(f"{target} checksum mismatch for {filename}")
    duplicates = sorted(name for name, count in reference_counts.items() if count > 1)
    if duplicates:
        errors.append(f"{target} checksum sidecar has duplicate references: {duplicates}")
    missing_refs = sorted(expected_references - referenced)
    if missing_refs:
        errors.append(f"{target} checksum sidecar missing references: {missing_refs}")
    return errors


def check_native_manifest(target: str, root: object, expected: set[str]) -> list[str]:
    path_errors, root_path = path_arg_value(root, f"{target} artifact directory")
    if path_errors:
        return path_errors
    assert root_path is not None
    manifests = sorted(item for item in expected if item.endswith(MANIFEST_SUFFIX))
    if len(manifests) != 1:
        return [f"{target} must declare exactly one native manifest, got {manifests}"]
    manifest_path = root_path / manifests[0]
    if not manifest_path.is_file():
        return []
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{target} native manifest is not valid JSON: {exc}"]

    records = manifest_records(raw_manifest)
    if records is None:
        return [f"{target} native manifest must be a list or contain an artifacts list"]
    payload_expected = {
        item
        for item in expected
        if not item.endswith(CHECKSUM_SUFFIX) and not item.endswith(MANIFEST_SUFFIX)
    }
    errors: list[str] = []
    by_name: dict[str, dict[str, Any]] = {}
    record_counts: dict[str, int] = {}
    for record in records:
        raw_filename = manifest_record_filename(record)
        if not raw_filename:
            errors.append(f"{target} native manifest contains record without file/path/name")
            continue
        if not artifact_reference_name_is_safe(raw_filename):
            errors.append(
                f"{target} native manifest record file/path/name must be an exact safe file name: {raw_filename!r}"
            )
            continue
        filename = raw_filename
        by_name[filename] = record
        record_counts[filename] = record_counts.get(filename, 0) + 1
    missing_records = sorted(payload_expected - set(by_name))
    if missing_records:
        errors.append(f"{target} native manifest missing payload records: {missing_records}")
    extra_records = sorted(set(by_name) - payload_expected)
    if extra_records:
        errors.append(f"{target} native manifest contains unexpected payload records: {extra_records}")
    duplicate_records = sorted(name for name, count in record_counts.items() if count > 1)
    if duplicate_records:
        errors.append(f"{target} native manifest contains duplicate payload records: {duplicate_records}")
    case_collisions = case_insensitive_name_collisions(set(record_counts))
    if case_collisions:
        errors.append(
            f"{target} native manifest payload records must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )

    for filename in sorted(payload_expected & set(by_name)):
        record = by_name[filename]
        path = root_path / filename
        if not path.is_file():
            continue
        size = record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{target} native manifest record {filename} missing positive size_bytes")
        elif size != path.stat().st_size:
            errors.append(f"{target} native manifest size mismatch for {filename}")
        checksum = record.get("sha256", "")
        if not lowercase_sha256_hex(checksum):
            errors.append(
                f"{target} native manifest record {filename} "
                "sha256 must be a lowercase SHA-256 hex digest"
            )
        elif checksum != sha256_file(path):
            errors.append(f"{target} native manifest checksum mismatch for {filename}")
        errors.extend(check_native_manifest_target_binding(target, filename, record))
    return errors


def check_native_manifest_target_binding(
    target: str,
    filename: str,
    record: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_architecture = expected_manifest_architecture(target, filename)
    if expected_architecture:
        raw_architecture = record.get("architecture", "")
        if not isinstance(raw_architecture, str):
            errors.append(
                f"{target} native manifest record {filename} architecture "
                f"must be a string, got {raw_architecture!r}"
            )
        elif raw_architecture.strip() != expected_architecture:
            errors.append(
                f"{target} native manifest record {filename} architecture must be "
                f"{expected_architecture!r}, got {record.get('architecture')!r}"
            )
    expected_format = expected_manifest_format(filename)
    if expected_format:
        raw_format = record.get("format", "")
        if not isinstance(raw_format, str):
            errors.append(
                f"{target} native manifest record {filename} format "
                f"must be a string, got {raw_format!r}"
            )
        elif raw_format.strip() != expected_format:
            errors.append(
                f"{target} native manifest record {filename} format must be "
                f"{expected_format!r}, got {record.get('format')!r}"
            )
    return errors


def expected_manifest_architecture(target: str, filename: str) -> str:
    for pattern, architecture in MANIFEST_ARCHITECTURE_PATTERNS.get(target, ()):
        if re.search(pattern, filename):
            return architecture
    return ""


def expected_manifest_format(filename: str) -> str:
    if filename.endswith(".tar.gz"):
        return "tar.gz"
    if filename.endswith(".AppImage"):
        return "AppImage"
    for suffix in (".deb", ".rpm", ".zip"):
        if filename.endswith(suffix):
            return suffix[1:]
    return ""


def manifest_records(raw_manifest: Any) -> list[dict[str, Any]] | None:
    if isinstance(raw_manifest, list):
        records = raw_manifest
    elif isinstance(raw_manifest, dict) and isinstance(raw_manifest.get("artifacts"), list):
        records = raw_manifest["artifacts"]
    else:
        return None
    if not all(isinstance(item, dict) for item in records):
        return None
    return records


def manifest_record_filename(record: dict[str, Any]) -> str:
    for key in ("file", "path", "name"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def artifact_reference_name_is_safe(name: str) -> bool:
    if not name or name.strip() != name or "/" in name or "\\" in name:
        return False
    if name in (".", ".."):
        return False
    windows_path = PureWindowsPath(name)
    posix_path = PurePosixPath(name)
    return not windows_path.drive and not windows_path.is_absolute() and not posix_path.is_absolute()


def promotion_entries(promotion: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    raw_entries = promotion.get("protected_targets")
    if not isinstance(raw_entries, list):
        errors.append("configs/platform_parity_promotion.json protected_targets must be a list")
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in raw_entries:
        if not isinstance(item, dict):
            errors.append("platform promotion protected target entries must be objects")
            continue
        target_id = item.get("id")
        if not isinstance(target_id, str) or not target_id:
            errors.append(
                "platform promotion protected target entry id "
                f"must be a non-empty string, got {target_id!r}"
            )
            continue
        if target_id in entries:
            errors.append(f"duplicate platform promotion target id: {target_id}")
            continue
        entries[target_id] = item
    return entries


def expected_target_ids(promotion: dict[str, Any]) -> set[str]:
    return {
        item.get("id")
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item.get("id")
    }


def required_artifacts(
    entry: dict[str, Any],
    target: str = "platform promotion target",
    errors: list[str] | None = None,
) -> list[str]:
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        if errors is not None:
            errors.append(f"{target} promotion_to_100_requires must be an object")
        return []
    artifact_key = "required_artifacts" if "required_artifacts" in requirements else "native_artifacts"
    raw_artifacts = requirements.get(artifact_key, [])
    if not isinstance(raw_artifacts, list):
        if errors is not None:
            errors.append(f"{target} {artifact_key} must be a list")
        return []
    artifacts: list[str] = []
    for index, item in enumerate(raw_artifacts):
        if not isinstance(item, str) or not item:
            if errors is not None:
                errors.append(
                    f"{target} {artifact_key}[{index}] "
                    f"must be a non-empty string, got {item!r}"
                )
            continue
        artifacts.append(item)
    return artifacts


def artifact_validation_command(
    entry: dict[str, Any],
    target: str = "platform promotion target",
    errors: list[str] | None = None,
) -> str:
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        if errors is not None:
            errors.append(f"{target} promotion_to_100_requires must be an object")
        return ""
    command = requirements.get("artifact_validation_command", "")
    if not isinstance(command, str):
        if errors is not None:
            errors.append(
                f"{target} artifact_validation_command "
                f"must be a string, got {command!r}"
            )
        return ""
    return command


def expand_version(value: str, version: str) -> str:
    return value.replace("<project.version>", version)


def version_from_tag(tag: str, errors: list[str]) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        errors.append(f"release tag must look like vX.Y.Z: {tag}")
        return ""
    return tag[1:]


def read_project_version() -> str:
    text = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError("pyproject.toml does not define project.version")
    return match.group(1)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
