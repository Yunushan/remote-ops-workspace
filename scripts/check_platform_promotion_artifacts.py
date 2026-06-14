from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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
        command = artifact_validation_command(entry)
        expected = (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target_id} --assets-dir <artifact-dir> --tag v<project.version>"
        )
        if command != expected:
            errors.append(f"{target_id} artifact_validation_command must be: {expected}")
        required = required_artifacts(entry)
        if not required:
            errors.append(f"{target_id} must declare required promotion artifacts")
            continue
        if not any(str(item).endswith(CHECKSUM_SUFFIX) for item in required):
            errors.append(f"{target_id} must require a {CHECKSUM_SUFFIX} sidecar")
        if not any(str(item).endswith(MANIFEST_SUFFIX) for item in required):
            errors.append(f"{target_id} must require a native {MANIFEST_SUFFIX}")
    return errors


def check_platform_promotion_artifacts(
    *,
    target: str,
    assets_dir: Path,
    tag: str | None = None,
    strict: bool = False,
    promotion: dict[str, Any] | None = None,
) -> list[str]:
    promotion_data = promotion or read_json(PROMOTION_PATH)
    errors: list[str] = []
    entries = promotion_entries(promotion_data, errors)
    entry = entries.get(target)
    if entry is None:
        return [*errors, f"unknown promotion target: {target}"]
    version = version_from_tag(tag or f"v{read_project_version()}", errors)
    if errors:
        return errors
    root = assets_dir.resolve()
    if not root.is_dir():
        return [f"artifact directory missing: {assets_dir}"]

    expected = {expand_version(str(item), version) for item in required_artifacts(entry)}
    actual = {path.name for path in root.iterdir() if path.is_file()}
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


def check_artifact_format(target: str, path: Path) -> list[str]:
    expected_signatures = signatures_for(path.name)
    if not expected_signatures:
        return []
    max_signature = max(len(signature) for signature in expected_signatures)
    try:
        with path.open("rb") as handle:
            header = handle.read(max_signature)
    except OSError as exc:
        return [f"{target} artifact cannot be read for format validation: {path.name}: {exc}"]
    if any(header.startswith(signature) for signature in expected_signatures):
        return check_archive_structure(target, path)
    expected_hex = ", ".join(signature.hex() for signature in expected_signatures)
    return [f"{target} artifact has invalid file signature for {path.name}; expected one of {expected_hex}"]


def check_archive_structure(target: str, path: Path) -> list[str]:
    if path.name.endswith(".zip"):
        return check_zip_structure(target, path)
    if path.name.endswith(".tar.gz"):
        return check_tar_gz_structure(target, path)
    return []


def check_zip_structure(target: str, path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = [item for item in archive.infolist() if not item.is_dir()]
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"{target} ZIP artifact is not a readable archive: {path.name}: {exc}"]
    if not entries:
        return [f"{target} ZIP artifact must contain at least one file: {path.name}"]
    empty_entries = sorted(item.filename for item in entries if item.file_size <= 0)
    if empty_entries:
        return [f"{target} ZIP artifact contains empty files: {empty_entries}"]
    return []


def check_tar_gz_structure(target: str, path: Path) -> list[str]:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            entries = [item for item in archive.getmembers() if item.isfile()]
    except (OSError, tarfile.TarError) as exc:
        return [f"{target} tar.gz artifact is not a readable archive: {path.name}: {exc}"]
    if not entries:
        return [f"{target} tar.gz artifact must contain at least one file: {path.name}"]
    empty_entries = sorted(item.name for item in entries if item.size <= 0)
    if empty_entries:
        return [f"{target} tar.gz artifact contains empty files: {empty_entries}"]
    return []


def signatures_for(filename: str) -> tuple[bytes, ...]:
    for suffix, signatures in FORMAT_SIGNATURES:
        if filename.endswith(suffix):
            return signatures
    return ()


def check_checksum_sidecar(target: str, root: Path, expected: set[str]) -> list[str]:
    errors: list[str] = []
    sidecars = sorted(item for item in expected if item.endswith(CHECKSUM_SUFFIX))
    if len(sidecars) != 1:
        return [f"{target} must declare exactly one checksum sidecar, got {sidecars}"]
    sidecar = root / sidecars[0]
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
        filename = Path(raw_name).name
        referenced.add(filename)
        reference_counts[filename] = reference_counts.get(filename, 0) + 1
        if filename not in expected_references:
            errors.append(f"{target} checksum sidecar references unexpected file: {filename}")
            continue
        path = root / filename
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


def check_native_manifest(target: str, root: Path, expected: set[str]) -> list[str]:
    manifests = sorted(item for item in expected if item.endswith(MANIFEST_SUFFIX))
    if len(manifests) != 1:
        return [f"{target} must declare exactly one native manifest, got {manifests}"]
    manifest_path = root / manifests[0]
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
        filename = manifest_record_filename(record)
        if filename:
            by_name[filename] = record
            record_counts[filename] = record_counts.get(filename, 0) + 1
        else:
            errors.append(f"{target} native manifest contains record without file/path/name")
    missing_records = sorted(payload_expected - set(by_name))
    if missing_records:
        errors.append(f"{target} native manifest missing payload records: {missing_records}")
    extra_records = sorted(set(by_name) - payload_expected)
    if extra_records:
        errors.append(f"{target} native manifest contains unexpected payload records: {extra_records}")
    duplicate_records = sorted(name for name, count in record_counts.items() if count > 1)
    if duplicate_records:
        errors.append(f"{target} native manifest contains duplicate payload records: {duplicate_records}")

    for filename in sorted(payload_expected & set(by_name)):
        record = by_name[filename]
        path = root / filename
        if not path.is_file():
            continue
        size = record.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            errors.append(f"{target} native manifest record {filename} missing positive size_bytes")
        elif size != path.stat().st_size:
            errors.append(f"{target} native manifest size mismatch for {filename}")
        checksum = str(record.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            errors.append(f"{target} native manifest record {filename} missing sha256")
        elif checksum != sha256_file(path):
            errors.append(f"{target} native manifest checksum mismatch for {filename}")
    return errors


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
            return Path(value).name
    return ""


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
        target_id = str(item.get("id", ""))
        if not target_id:
            errors.append("platform promotion protected target entry missing id")
            continue
        if target_id in entries:
            errors.append(f"duplicate platform promotion target id: {target_id}")
            continue
        entries[target_id] = item
    return entries


def expected_target_ids(promotion: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict) and item.get("id")
    }


def required_artifacts(entry: dict[str, Any]) -> list[str]:
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return []
    raw_artifacts = requirements.get("required_artifacts", requirements.get("native_artifacts", []))
    if not isinstance(raw_artifacts, list):
        return []
    return [str(item) for item in raw_artifacts]


def artifact_validation_command(entry: dict[str, Any]) -> str:
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return ""
    return str(requirements.get("artifact_validation_command", ""))


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
