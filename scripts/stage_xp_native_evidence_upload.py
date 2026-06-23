from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_review_bundle_artifacts import (  # noqa: E402
    check_platform_review_bundle_artifacts,
)
from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    PROMOTION_PATH,
    XP_TARGETS,
    accepted_artifact_names,
    accepted_record_source_file,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    promotion_entries_by_id,
    read_json,
    review_bundle_expected_files,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = stage_xp_native_evidence_upload(
        target=args.target,
        release_tag=args.release_tag,
        assets_dir=args.assets_dir,
        evidence_output_dir=args.evidence_output_dir,
        out_dir=args.out_dir,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"stage XP native evidence upload: {error}", file=sys.stderr)
        return 1
    print(f"XP native evidence upload staged in {args.out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage only the exact Windows XP native release and evidence files "
            "that may be uploaded as a GitHub Actions artifact."
        )
    )
    parser.add_argument("--target", choices=sorted(XP_TARGETS), required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--evidence-output-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="overwrite an existing staged upload directory")
    return parser.parse_args(argv)


def stage_xp_native_evidence_upload(
    *,
    target: str,
    release_tag: str,
    assets_dir: Path,
    evidence_output_dir: Path,
    out_dir: Path,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    if target not in XP_TARGETS:
        errors.append(f"unknown XP native target: {target}")
    promotion = read_json(PROMOTION_PATH)
    promotion_entries = promotion_entries_by_id(promotion, errors)
    expected_assets = accepted_artifact_names(target, release_tag, promotion_entries)
    expected_evidence = set(review_bundle_expected_files(target, release_tag).values())
    final_record_name = accepted_record_source_file(target)
    expected_evidence.add(final_record_name)
    if not expected_assets:
        errors.append(f"{target} has no expected XP native assets for {release_tag}")
    if not expected_evidence:
        errors.append(f"{target} has no expected XP evidence bundle outputs for {release_tag}")
    errors.extend(check_directory_path_hint(assets_dir, "XP native asset directory"))
    if assets_dir.is_symlink():
        errors.append(f"XP native asset directory must not be a symlink: {assets_dir}")
    elif not assets_dir.is_dir():
        errors.append(f"XP native asset directory missing: {assets_dir}")
    errors.extend(check_directory_path_hint(evidence_output_dir, "XP evidence output directory"))
    if evidence_output_dir.is_symlink():
        errors.append(f"XP evidence output directory must not be a symlink: {evidence_output_dir}")
    elif not evidence_output_dir.is_dir():
        errors.append(f"XP evidence output directory missing: {evidence_output_dir}")
    if errors:
        return errors
    errors.extend(
        check_staging_path_separation(
            target,
            assets_dir=assets_dir,
            evidence_output_dir=evidence_output_dir,
            out_dir=out_dir,
        )
    )
    if errors:
        return errors
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            assets_dir,
            label="XP native asset directory",
        )
    )
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            evidence_output_dir,
            label="XP evidence output directory",
        )
    )
    if errors:
        return errors

    source_files = {
        **source_map(
            assets_dir,
            expected_assets,
        ),
        **source_map(
            evidence_output_dir,
            expected_evidence,
        ),
    }
    missing = sorted(name for name, path in source_files.items() if not path.is_file())
    if missing:
        return [f"{target} staged upload missing expected files: {missing}"]
    errors.extend(check_source_paths(target, source_files))
    if errors:
        return errors
    final_record_errors, final_record = check_final_record(
        target,
        release_tag,
        source_files[final_record_name],
    )
    errors.extend(final_record_errors)
    if final_record:
        errors.extend(
            check_source_directory_entries(
                target,
                assets_dir,
                expected_assets,
                label="XP native asset directory",
            )
        )
        allowed_workspace_files = review_bundle_workspace_files(
            final_record,
            bundle_dir=evidence_output_dir,
        )
        errors.extend(
            check_source_directory_entries(
                target,
                evidence_output_dir,
                expected_evidence | allowed_workspace_files,
                label="XP evidence output directory",
            )
        )
        errors.extend(check_release_source_file_set(target, final_record, source_files))
        errors.extend(check_source_hashes(target, final_record, source_files))
        errors.extend(
            check_review_bundle_artifacts(
                target,
                release_tag,
                final_record,
                bundle_dir=evidence_output_dir,
            )
        )
    if errors:
        return errors
    errors.extend(prepare_output_directory(target, out_dir=out_dir, force=force))
    if errors:
        return errors
    for name, source in sorted(source_files.items()):
        destination = out_dir / name
        errors.extend(check_destination_path(target, destination, name))
        if errors:
            return errors
        if destination.exists() and not force:
            return [f"refusing to overwrite staged XP upload file: {destination}"]
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


def check_review_bundle_artifacts(
    target: str,
    release_tag: str,
    record: dict[str, Any],
    *,
    bundle_dir: Path,
) -> list[str]:
    errors = check_platform_review_bundle_artifacts(
        registry=finalized_record_registry(record),
        bundle_dir=bundle_dir,
        required_targets=(target,),
        required_release_tag=release_tag,
    )
    return [
        f"{target} staged upload review bundle failed re-finalization: {error}"
        for error in errors
    ]


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
        else:
            errors.extend(
                check_path_parent_symlinks(
                    path,
                    f"{target} staged upload source {filename}",
                )
            )
    return errors


def check_source_directory_entries(
    target: str,
    root: Path,
    expected_files: set[str],
    *,
    label: str,
) -> list[str]:
    allowed_entries = {filename for filename in expected_files if safe_relative_path(filename)}
    for filename in list(allowed_entries):
        allowed_entries.update(parent_directories(filename))
    actual: set[str] = set()
    symlinked: list[str] = []
    for path in root.rglob("*"):
        name = path.relative_to(root).as_posix()
        actual.add(name)
        if path.is_symlink():
            symlinked.append(name)
    errors: list[str] = []
    if symlinked:
        errors.append(f"{target} {label} contains symlinked entries: {sorted(symlinked)}")
    unexpected = sorted(actual - allowed_entries)
    if unexpected:
        errors.append(f"{target} {label} contains files outside staged upload set: {unexpected}")
    return errors


def review_bundle_workspace_files(record: dict[str, Any], *, bundle_dir: Path) -> set[str]:
    manifest = read_review_bundle_manifest(record, bundle_dir=bundle_dir)
    if not manifest:
        return set()
    files: set[str] = set()
    for raw_record in review_bundle_manifest_file_records(manifest):
        if not isinstance(raw_record, dict):
            continue
        filename = str(raw_record.get("file", ""))
        if safe_relative_path(filename):
            files.add(filename)
    return files


def read_review_bundle_manifest(record: dict[str, Any], *, bundle_dir: Path) -> dict[str, Any] | None:
    review_bundle = record.get("review_bundle")
    if not isinstance(review_bundle, dict):
        return None
    manifest_record = review_bundle.get("manifest")
    if not isinstance(manifest_record, dict):
        return None
    filename = str(manifest_record.get("file", ""))
    if not safe_relative_path(filename):
        return None
    manifest_path = bundle_dir / filename
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return manifest if isinstance(manifest, dict) else None


def review_bundle_manifest_file_records(manifest: dict[str, Any]) -> list[Any]:
    records: list[Any] = []
    bundle_type = str(manifest.get("bundle_type", ""))
    if bundle_type == "extended-linux-native-evidence":
        records.extend([manifest.get("builder_evidence"), manifest.get("candidate_record")])
        records.extend(manifest.get("smoke_evidence", []))
        records.extend(manifest.get("artifacts", []))
    elif bundle_type == "windows-xp-native-host-evidence":
        records.extend([manifest.get("candidate_record"), manifest.get("evidence")])
        records.extend(manifest.get("smoke_evidence", []))
        records.extend(manifest.get("artifacts", []))
    return records


def safe_relative_path(filename: str) -> bool:
    if not filename or filename.strip() != filename or "\\" in filename:
        return False
    parts = filename.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    posix_path = PurePosixPath(filename)
    windows_path = PureWindowsPath(filename)
    return not posix_path.is_absolute() and not windows_path.is_absolute() and not windows_path.drive


def parent_directories(filename: str) -> set[str]:
    parts = filename.split("/")[:-1]
    return {"/".join(parts[:index]) for index in range(1, len(parts) + 1)}


def prepare_output_directory(target: str, *, out_dir: Path, force: bool) -> list[str]:
    hint_errors = check_directory_path_hint(out_dir, f"{target} staged upload output directory")
    if hint_errors:
        return hint_errors
    if out_dir.is_symlink():
        return [f"{target} staged upload output directory must not be a symlink: {out_dir}"]
    parent_errors = check_path_parent_symlinks(out_dir, f"{target} staged upload output directory")
    if parent_errors:
        return parent_errors
    if out_dir.exists():
        if not force:
            return [f"refusing to overwrite existing XP staged upload directory: {out_dir}"]
        if not out_dir.is_dir():
            return [f"XP staged upload output exists and is not a directory: {out_dir}"]
        for child in out_dir.iterdir():
            if child.is_symlink():
                return [f"{target} staged upload output must not contain symlinks: {child.name}"]
            if child.is_dir():
                return [
                    f"refusing to clear staged upload directory containing subdirectory: {child}"
                ]
            if not child.is_file():
                return [f"{target} staged upload output must contain regular files only: {child.name}"]
            child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    return []


def check_destination_path(target: str, destination: Path, filename: str) -> list[str]:
    if destination.is_symlink():
        return [f"{target} staged upload destination must not be a symlink: {filename}"]
    if destination.exists() and not destination.is_file():
        return [f"{target} staged upload destination must be a regular file: {filename}"]
    return []


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: Path, label: str) -> list[str]:
    raw_path = path.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def check_target_release_path_segments(
    target: str,
    release_tag: str,
    path: Path,
    *,
    label: str,
) -> list[str]:
    segments = {str(part) for part in path.parts if str(part)}
    raw_path = path.as_posix()
    errors: list[str] = []
    if target not in segments:
        errors.append(f"{label} must include target path segment {target!r}, got {raw_path!r}")
    if release_tag not in segments:
        errors.append(f"{label} must include release_tag path segment {release_tag!r}, got {raw_path!r}")
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


def source_map(
    root: Path,
    filenames: set[str],
) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for filename in sorted(filenames):
        path = root / filename
        if Path(filename).name != filename or "/" in filename or "\\" in filename:
            files[filename] = Path("__invalid__")
            continue
        files[filename] = path
        if path.is_dir():
            files[filename] = root / f"__directory_not_allowed__{filename}"
    return files


def check_staging_path_separation(
    target: str,
    *,
    assets_dir: Path,
    evidence_output_dir: Path,
    out_dir: Path,
) -> list[str]:
    errors: list[str] = []
    if paths_overlap(assets_dir, evidence_output_dir):
        errors.append(f"{target} XP native asset directory and evidence output directory must be separate roots")
    if paths_overlap(assets_dir, out_dir):
        errors.append(f"{target} XP native asset directory and staged upload output directory must be separate roots")
    if paths_overlap(evidence_output_dir, out_dir):
        errors.append(f"{target} XP evidence output directory and staged upload output directory must be separate roots")
    return errors


def paths_overlap(left: Path, right: Path) -> bool:
    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    return path_contains(left_resolved, right_resolved) or path_contains(right_resolved, left_resolved)


def path_contains(parent: Path, child: Path) -> bool:
    return child == parent or child.is_relative_to(parent)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
