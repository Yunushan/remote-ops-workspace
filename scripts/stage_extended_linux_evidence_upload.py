from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    LINUX_TARGETS,
    PROMOTION_PATH,
    accepted_artifact_names,
    accepted_record_source_file,
    check_platform_verified_evidence,
    promotion_entries_by_id,
    read_json,
    review_bundle_expected_files,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = stage_extended_linux_evidence_upload(
        target=args.target,
        release_tag=args.release_tag,
        source_dir=args.source_dir,
        out_dir=args.out_dir,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"stage extended Linux evidence upload: {error}", file=sys.stderr)
        return 1
    print(f"extended Linux evidence upload staged in {args.out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage only the exact Linux i386/armhf release and evidence files "
            "that may be uploaded as a GitHub Actions artifact."
        )
    )
    parser.add_argument("--target", choices=sorted(LINUX_TARGETS), required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="overwrite an existing staged upload directory")
    return parser.parse_args(argv)


def stage_extended_linux_evidence_upload(
    *,
    target: str,
    release_tag: str,
    source_dir: Path,
    out_dir: Path,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    if target not in LINUX_TARGETS:
        errors.append(f"unknown extended Linux target: {target}")
    promotion = read_json(PROMOTION_PATH)
    promotion_entries = promotion_entries_by_id(promotion, errors)
    expected_files = accepted_artifact_names(target, release_tag, promotion_entries)
    expected_files.update(review_bundle_expected_files(target, release_tag).values())
    final_record_name = accepted_record_source_file(target)
    expected_files.add(final_record_name)
    if not expected_files:
        errors.append(f"{target} has no expected Linux evidence upload files for {release_tag}")
    if not source_dir.is_dir():
        errors.append(f"extended Linux evidence source directory missing: {source_dir}")
    if errors:
        return errors
    errors.extend(check_staging_path_separation(target, source_dir=source_dir, out_dir=out_dir))
    if errors:
        return errors

    sources = source_map(source_dir, expected_files)
    missing = sorted(name for name, path in sources.items() if not path.is_file())
    if missing:
        return [f"{target} staged upload missing expected files: {missing}"]
    errors.extend(check_source_paths(target, sources))
    if errors:
        return errors
    final_record_errors, final_record = check_final_record(
        target,
        release_tag,
        sources[final_record_name],
    )
    errors.extend(final_record_errors)
    if final_record:
        errors.extend(check_release_source_file_set(target, final_record, sources))
        errors.extend(check_source_hashes(target, final_record, sources))
    if errors:
        return errors

    if out_dir.exists():
        if not force:
            return [f"refusing to overwrite existing extended Linux staged upload directory: {out_dir}"]
        if not out_dir.is_dir():
            return [f"extended Linux staged upload output exists and is not a directory: {out_dir}"]
        for child in out_dir.iterdir():
            if child.is_dir():
                return [
                    f"refusing to clear staged upload directory containing subdirectory: {child}"
                ]
            child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, source in sorted(sources.items()):
        destination = out_dir / name
        if destination.exists() and not force:
            return [f"refusing to overwrite staged extended Linux upload file: {destination}"]
        shutil.copy2(source, destination)
    return []


def check_final_record(target: str, release_tag: str, final_record: Path) -> tuple[list[str], dict[str, Any] | None]:
    try:
        record = json.loads(final_record.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} finalized accepted record is not readable JSON: {final_record.name}: {exc}"], None
    if not isinstance(record, dict):
        return [f"{target} finalized accepted record must be a JSON object: {final_record.name}"], None
    registry = finalized_record_registry(record)
    errors = check_platform_verified_evidence(
        registry=registry,
        required_targets=(target,),
        required_release_tag=release_tag,
        require_review_bundles=True,
    )
    return [f"{target} finalized accepted record failed strict validation: {error}" for error in errors], record


def check_source_hashes(target: str, record: dict[str, Any], sources: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for filename, expected_sha in sorted(artifact_hashes.items()):
            path = sources.get(str(filename))
            if path is not None and path.is_file() and sha256_file(path) != str(expected_sha):
                errors.append(f"{target} staged upload native artifact SHA-256 mismatch: {filename}")
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            raw_record = review_bundle.get(key)
            if not isinstance(raw_record, dict):
                continue
            filename = str(raw_record.get("file", ""))
            path = sources.get(filename)
            if path is None or not path.is_file():
                continue
            if raw_record.get("size_bytes") != path.stat().st_size:
                errors.append(f"{target} staged upload review_bundle {key}.size_bytes mismatch: {filename}")
            if str(raw_record.get("sha256", "")) != sha256_file(path):
                errors.append(f"{target} staged upload review_bundle {key}.sha256 mismatch: {filename}")
    return errors


def check_release_source_file_set(
    target: str,
    record: dict[str, Any],
    sources: dict[str, Path],
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} finalized accepted record release_asset_source must be an object"]
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        return [f"{target} finalized accepted record release_asset_source.contains_files must be a non-empty list"]
    expected = {str(filename) for filename in raw_files}
    actual = {str(filename) for filename in sources}
    errors: list[str] = []
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append(f"{target} staged upload missing release_asset_source files: {missing}")
    if unexpected:
        errors.append(f"{target} staged upload has files outside release_asset_source: {unexpected}")
    return errors


def check_source_paths(target: str, sources: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    for filename, path in sorted(sources.items()):
        if path.is_symlink():
            errors.append(f"{target} staged upload source must not be a symlink: {filename}")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finalized_record_registry(record: dict[str, Any]) -> dict[str, Any]:
    registry = read_json(EVIDENCE_PATH)
    return {**registry, "accepted_evidence": [record]}


def source_map(root: Path, filenames: set[str]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for filename in sorted(filenames):
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            files[filename] = Path("__invalid__")
            continue
        path = root / filename
        files[filename] = root / f"__directory_not_allowed__{filename}" if path.is_dir() else path
    return files


def check_staging_path_separation(target: str, *, source_dir: Path, out_dir: Path) -> list[str]:
    if paths_overlap(source_dir, out_dir):
        return [
            f"{target} extended Linux evidence source directory and staged upload output "
            "directory must be separate roots"
        ]
    return []


def paths_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    return path_contains(left_resolved, right_resolved) or path_contains(right_resolved, left_resolved)


def path_contains(parent: Path, child: Path) -> bool:
    return child == parent or child.is_relative_to(parent)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
