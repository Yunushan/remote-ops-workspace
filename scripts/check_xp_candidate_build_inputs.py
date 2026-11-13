"""Verify an XP build receipt against the exact source and candidate files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from check_platform_promotion_artifacts import (
    check_platform_promotion_artifacts,
    lowercase_sha256_hex,
    read_project_version,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_LIMIT = 16 * 1024
ENTRY_LIMIT = 16 * 1024 * 1024
EXECUTABLE = "bin/row-xp-host.exe"
PACKAGE_FILES = {EXECUTABLE, "README_XP.txt", "docs/LICENSE", "docs/NOTICE"}


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_receipt(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= RECEIPT_LIMIT:
        raise ValueError("build receipt must be a small, regular JSON file")
    value = json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("build receipt must be a JSON object")
    return value


def check_build_inputs(
    receipt_path: Path,
    assets_dir: Path,
    *,
    repository: str,
    arch: str,
    tag: str,
    source_ref: str,
    source_sha: str,
    run_id: str,
    run_attempt: str,
    root: Path = ROOT,
) -> list[str]:
    if not (
        arch in {"x86", "x64"}
        and re.fullmatch(r"v\d+\.\d+\.\d+", tag)
        and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        and source_ref.startswith("refs/")
        and (not source_ref.startswith("refs/tags/") or source_ref == f"refs/tags/{tag}")
        and re.fullmatch(r"[0-9a-f]{40}", source_sha)
        and all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run_id, run_attempt))
    ):
        return ["expected candidate identity is invalid"]

    target = f"windows-xp-native-{arch}"
    errors = check_platform_promotion_artifacts(
        target=target, assets_dir=assets_dir, tag=tag, strict=True,
    )
    if errors:
        return errors
    receipt = read_receipt(receipt_path)
    reference_lock = root / "legacy/xp_host/net40-references.json"
    lock = json.loads(reference_lock.read_bytes(), object_pairs_hook=unique_object)
    template = root / "legacy/xp_host/RemoteOpsXpHost.template.cs"
    source = template.read_text(encoding="utf-8").replace("@VERSION@", tag[1:])
    base = f"remote-ops-workspace-{tag}-windows-xp-{arch}-native"
    archive = assets_dir / f"{base}.zip"
    manifest = assets_dir / f"{base}-manifest.json"
    expected = {
        "schema_version": 1,
        "target": target,
        "release_tag": tag,
        "repository": repository,
        "source_ref": source_ref,
        "source_sha": source_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "reference_lock_sha256": sha256_file(reference_lock),
        "reference_package": lock["package"],
        "reference_package_version": lock["version"],
        "reference_package_sha256": lock["sha256"],
        "reference_assemblies": lock["assemblies"],
        "generated_source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "archive_sha256": sha256_file(archive),
        "native_manifest_sha256": sha256_file(manifest),
    }
    if set(receipt) != set(expected) | {"compiler", "executable_sha256"}:
        errors.append("build receipt fields must match the expected schema")
    for key, value in expected.items():
        if type(receipt.get(key)) is not type(value) or receipt[key] != value:
            errors.append(f"build receipt {key} does not match the expected input")
    compiler = receipt.get("compiler")
    if not (
        isinstance(compiler, dict)
        and set(compiler) == {"name", "file_version", "sha256"}
        and compiler["name"] == "csc.exe"
        and isinstance(compiler["file_version"], str)
        and compiler["file_version"].strip()
        and lowercase_sha256_hex(compiler["sha256"])
    ):
        errors.append("build receipt compiler observation is invalid")
    errors.extend(check_package(archive, arch, receipt.get("executable_sha256"), root))
    return errors


def matches_pe_architecture(executable: bytes, arch: str) -> bool:
    if len(executable) < 64 or executable[:2] != b"MZ":
        return False
    offset = int.from_bytes(executable[60:64], "little")
    machine, magic = {"x86": (0x014C, 0x010B), "x64": (0x8664, 0x020B)}[arch]
    return (
        64 <= offset <= len(executable) - 26
        and executable[offset:offset + 4] == b"PE\0\0"
        and int.from_bytes(executable[offset + 4:offset + 6], "little") == machine
        and int.from_bytes(executable[offset + 24:offset + 26], "little") == magic
    )


def check_package(archive: Path, arch: str, executable_sha256: Any, root: Path) -> list[str]:
    with zipfile.ZipFile(archive) as package:
        files = {entry.filename: entry for entry in package.infolist() if not entry.is_dir()}
        if set(files) != PACKAGE_FILES:
            return ["XP archive must contain exactly the executable, README, LICENSE, and NOTICE"]
        if any(not 0 < entry.file_size <= ENTRY_LIMIT for entry in files.values()):
            return ["XP archive entries must be nonempty and within the verification size limit"]
        errors = []
        executable = package.read(files[EXECUTABLE])
        if hashlib.sha256(executable).hexdigest() != executable_sha256:
            errors.append("build receipt executable digest does not match the XP archive")
        if not matches_pe_architecture(executable, arch):
            errors.append(f"XP archive executable does not have the expected {arch} PE headers")
        for name in ("LICENSE", "NOTICE"):
            packaged = package.read(files[f"docs/{name}"]).replace(b"\r\n", b"\n")
            if packaged != (root / name).read_bytes().replace(b"\r\n", b"\n"):
                errors.append(f"XP archive {name} does not match the source")
        return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--arch", choices=("x86", "x64"), required=True)
    parser.add_argument("--tag", default=f"v{read_project_version()}")
    for option in ("repository", "source-ref", "source-sha", "run-id", "run-attempt"):
        parser.add_argument(f"--{option}", required=True)
    args = parser.parse_args()
    try:
        errors = check_build_inputs(
            args.receipt, args.assets_dir, repository=args.repository, arch=args.arch,
            tag=args.tag, source_ref=args.source_ref, source_sha=args.source_sha,
            run_id=args.run_id, run_attempt=args.run_attempt,
        )
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"XP build inputs: {error}", file=sys.stderr)
        return 1
    print("XP build receipt matches the candidate files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
