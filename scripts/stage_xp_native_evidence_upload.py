from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_review_bundle_artifacts import (  # noqa: E402
    canonical_public_record_bytes,
    check_platform_review_bundle_artifacts,
)
from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    PROMOTION_PATH,
    RESERVED_WORKSPACE_ROOTS,
    XP_TARGETS,
    accepted_artifact_names,
    accepted_record_source_file,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    exact_safe_file_name,
    promotion_entries_by_id,
    read_json,
    review_bundle_expected_files,
)

SHA256_HEX_CHARS = set("0123456789abcdef")
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")


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
    assets_dir: object,
    evidence_output_dir: object,
    out_dir: object,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    if target not in XP_TARGETS:
        errors.append(f"unknown XP native target: {target}")
    release_tag_errors, release_tag = release_tag_value(release_tag)
    errors.extend(release_tag_errors)
    if errors:
        return errors
    assets_dir_errors, assets_dir_path = path_arg_value(
        assets_dir,
        "XP native asset directory",
    )
    evidence_output_dir_errors, evidence_output_dir_path = path_arg_value(
        evidence_output_dir,
        "XP evidence output directory",
    )
    out_dir_errors, out_dir_path = path_arg_value(
        out_dir,
        f"{target} staged upload output directory",
    )
    errors.extend(assets_dir_errors)
    errors.extend(evidence_output_dir_errors)
    errors.extend(out_dir_errors)
    if errors:
        return errors
    assert assets_dir_path is not None
    assert evidence_output_dir_path is not None
    assert out_dir_path is not None
    promotion = read_json(PROMOTION_PATH)
    promotion_entries = promotion_entries_by_id(promotion, errors)
    expected_assets = accepted_artifact_names(target, release_tag, promotion_entries)
    expected_evidence = set(review_bundle_expected_files(target, release_tag).values())
    final_record_name = accepted_record_source_file(target)
    expected_evidence.add(final_record_name)
    expected_upload_names = [
        *sorted(expected_assets),
        *sorted(expected_evidence),
    ]
    errors.extend(check_staged_upload_file_names(target, expected_upload_names))
    if not expected_assets:
        errors.append(f"{target} has no expected XP native assets for {release_tag}")
    if not expected_evidence:
        errors.append(f"{target} has no expected XP evidence bundle outputs for {release_tag}")
    if errors:
        return errors
    errors.extend(check_directory_path_hint(assets_dir_path, "XP native asset directory"))
    errors.extend(check_path_not_reserved_workspace_root(assets_dir_path, "XP native asset directory"))
    if assets_dir_path.is_symlink():
        errors.append(f"XP native asset directory must not be a symlink: {assets_dir_path}")
    elif not assets_dir_path.is_dir():
        errors.append(f"XP native asset directory missing: {assets_dir_path}")
    errors.extend(check_directory_path_hint(evidence_output_dir_path, "XP evidence output directory"))
    errors.extend(check_path_not_reserved_workspace_root(evidence_output_dir_path, "XP evidence output directory"))
    if evidence_output_dir_path.is_symlink():
        errors.append(f"XP evidence output directory must not be a symlink: {evidence_output_dir_path}")
    elif not evidence_output_dir_path.is_dir():
        errors.append(f"XP evidence output directory missing: {evidence_output_dir_path}")
    if errors:
        return errors
    errors.extend(
        check_staging_path_separation(
            target,
            assets_dir=assets_dir_path,
            evidence_output_dir=evidence_output_dir_path,
            out_dir=out_dir_path,
        )
    )
    if errors:
        return errors
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            assets_dir_path,
            label="XP native asset directory",
        )
    )
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            evidence_output_dir_path,
            label="XP evidence output directory",
        )
    )
    if errors:
        return errors

    source_files = {
        **source_map(
            assets_dir_path,
            expected_assets,
        ),
        **source_map(
            evidence_output_dir_path,
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
                assets_dir_path,
                expected_assets,
                label="XP native asset directory",
            )
        )
        allowed_workspace_files, manifest_errors = review_bundle_workspace_files_with_errors(
            target,
            final_record,
            bundle_dir=evidence_output_dir_path,
        )
        errors.extend(manifest_errors)
        errors.extend(
            check_source_directory_entries(
                target,
                evidence_output_dir_path,
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
                bundle_dir=evidence_output_dir_path,
            )
        )
    if errors:
        return errors
    errors.extend(prepare_output_directory(target, out_dir=out_dir_path, force=force))
    if errors:
        return errors
    source_hashes = {name: sha256_file(source) for name, source in sorted(source_files.items())}
    for name, source in sorted(source_files.items()):
        destination = out_dir_path / name
        errors.extend(check_destination_path(target, destination, name))
        if errors:
            return errors
        if destination.exists() and not force:
            return [f"refusing to overwrite staged XP upload file: {destination}"]
        shutil.copy2(source, destination)
    errors.extend(check_staged_output(target, out_dir=out_dir_path, expected_hashes=source_hashes))
    return []


def check_final_record(target: str, release_tag: str, final_record: Path) -> tuple[list[str], dict[str, Any] | None]:
    if final_record.is_symlink():
        return [f"{target} finalized accepted record must not be a symlink: {final_record.name}"], None
    parent_errors = check_path_parent_symlinks(final_record, f"{target} finalized accepted record")
    if parent_errors:
        return parent_errors, None
    try:
        raw_bytes = final_record.read_bytes()
        record = json.loads(raw_bytes.decode("utf-8"))
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
    if raw_bytes != canonical_public_record_bytes(record):
        errors.append(f"{target} finalized accepted record must use canonical sorted JSON: {final_record.name}")
    return [f"{target} finalized accepted record failed strict validation: {error}" for error in errors], record


def check_source_hashes(target: str, record: dict[str, Any], sources: dict[str, Path]) -> list[str]:
    errors: list[str] = []
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        artifact_items: list[tuple[str, Any]] = []
        unsafe_artifacts: list[str] = []
        for name, digest in artifact_hashes.items():
            if not isinstance(name, str):
                errors.append(f"{target} staged upload artifact_sha256 keys must be strings, got {name!r}")
                continue
            if not exact_safe_file_name(name):
                unsafe_artifacts.append(name)
                continue
            artifact_items.append((name, digest))
        for filename, expected_sha in sorted(artifact_items, key=lambda item: item[0]):
            if not lowercase_sha256_hex(expected_sha):
                errors.append(
                    f"{target} staged upload artifact_sha256.{filename} "
                    "must be a lowercase SHA-256 hex digest"
                )
                continue
            path = sources.get(filename)
            if path is None:
                continue
            if path.is_symlink():
                errors.append(f"{target} staged upload native artifact must not be a symlink: {filename}")
                continue
            if path.is_file() and sha256_file(path) != expected_sha:
                errors.append(f"{target} staged upload native artifact SHA-256 mismatch: {filename}")
        if unsafe_artifacts:
            errors.append(
                f"{target} staged upload artifact_sha256 keys must be exact safe file names: "
                f"{sorted(unsafe_artifacts)}"
            )
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_bundle_files: list[str] = []
        for key in ("manifest", "archive", "sha256s"):
            raw_record = review_bundle.get(key)
            if not isinstance(raw_record, dict):
                continue
            raw_filename = raw_record.get("file", "")
            if not isinstance(raw_filename, str) or not exact_safe_file_name(raw_filename):
                errors.append(
                    f"{target} staged upload review_bundle {key}.file "
                    f"must be an exact safe file name, got {raw_filename!r}"
                )
                continue
            filename = raw_filename
            review_bundle_files.append(filename)
            path = sources.get(filename)
            if path is None:
                continue
            if path.is_symlink():
                errors.append(f"{target} staged upload review_bundle {key} must not be a symlink: {filename}")
                continue
            if not path.is_file():
                continue
            expected_size = raw_record.get("size_bytes")
            if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size != path.stat().st_size:
                errors.append(f"{target} staged upload review_bundle {key}.size_bytes mismatch: {filename}")
            expected_sha256 = raw_record.get("sha256", "")
            if not lowercase_sha256_hex(expected_sha256):
                errors.append(
                    f"{target} staged upload review_bundle {key}.sha256 "
                    f"must be a lowercase SHA-256 hex digest: {filename}"
                )
            elif expected_sha256 != sha256_file(path):
                errors.append(f"{target} staged upload review_bundle {key}.sha256 mismatch: {filename}")
        duplicate_files = sorted(
            {filename for filename in review_bundle_files if review_bundle_files.count(filename) > 1}
        )
        if duplicate_files:
            errors.append(f"{target} staged upload review_bundle files must not contain duplicates: {duplicate_files}")
        case_groups: dict[str, set[str]] = {}
        for filename in review_bundle_files:
            case_groups.setdefault(filename.casefold(), set()).add(filename)
        case_collisions = sorted(
            {
                filename
                for group in case_groups.values()
                if len(group) > 1
                for filename in group
            }
        )
        if case_collisions:
            errors.append(
                f"{target} staged upload review_bundle files must not collide on "
                f"case-insensitive filesystems: {case_collisions}"
            )
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
        require_final_record_assets=True,
    )
    return [
        f"{target} staged upload review bundle failed re-finalization: {error}"
        for error in errors
    ]


def check_staged_upload_file_names(target: str, filenames: list[str]) -> list[str]:
    errors: list[str] = []
    unsafe = sorted({filename for filename in filenames if not exact_safe_file_name(filename)})
    if unsafe:
        errors.append(f"{target} staged upload file names must be exact safe file names: {unsafe}")
    duplicates = sorted({filename for filename in filenames if filenames.count(filename) > 1})
    if duplicates:
        errors.append(
            f"{target} staged upload file names must be unique across artifacts and evidence outputs: {duplicates}"
        )
    case_groups: dict[str, set[str]] = {}
    for filename in filenames:
        case_groups.setdefault(filename.casefold(), set()).add(filename)
    case_collisions = sorted(
        {
            filename
            for group in case_groups.values()
            if len(group) > 1
            for filename in group
        }
    )
    if case_collisions:
        errors.append(
            f"{target} staged upload file names must not collide on case-insensitive filesystems: "
            f"{case_collisions}"
        )
    return errors


def release_tag_value(release_tag: object) -> tuple[list[str], str]:
    if not isinstance(release_tag, str) or not release_tag:
        return [f"XP staged upload release_tag must be a non-empty string, got {release_tag!r}"], ""
    if release_tag.strip() != release_tag or not RELEASE_TAG_RE.fullmatch(release_tag):
        return [f"XP staged upload release_tag must look like vX.Y.Z, got {release_tag!r}"], ""
    return [], release_tag


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


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
    errors: list[str] = []
    unsafe = sorted(
        {
            filename if isinstance(filename, str) else repr(filename)
            for filename in raw_files
            if not isinstance(filename, str) or not exact_safe_file_name(filename)
        }
    )
    if unsafe:
        errors.append(
            f"{target} finalized accepted record release_asset_source.contains_files "
            f"entries must be exact safe file names: {unsafe}"
        )
    files = [filename for filename in raw_files if isinstance(filename, str)]
    duplicates = sorted({filename for filename in files if files.count(filename) > 1})
    if duplicates:
        errors.append(
            f"{target} finalized accepted record release_asset_source.contains_files "
            f"contains duplicate files: {duplicates}"
        )
    if errors:
        return errors
    expected = set(files)
    actual = set(sources)
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
        errors.extend(
            check_path_not_reserved_workspace_root(
                path,
                f"{target} staged upload source {filename}",
            )
        )
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
    files, _ = review_bundle_workspace_files_with_errors(
        "platform",
        record,
        bundle_dir=bundle_dir,
    )
    return files


def review_bundle_workspace_files_with_errors(
    target: str,
    record: dict[str, Any],
    *,
    bundle_dir: Path,
) -> tuple[set[str], list[str]]:
    manifest, errors = read_review_bundle_manifest_with_errors(
        target,
        record,
        bundle_dir=bundle_dir,
    )
    if manifest is None:
        return set(), errors
    files: set[str] = set()
    for raw_record in review_bundle_manifest_file_records(manifest):
        if not isinstance(raw_record, dict):
            continue
        raw_filename = raw_record.get("file", "")
        if not isinstance(raw_filename, str):
            errors.append(
                f"{target} staged upload review_bundle manifest file entries "
                f"must be strings, got {raw_filename!r}"
            )
            continue
        filename = raw_filename
        if safe_relative_path(filename):
            files.add(filename)
    return files, errors


def read_review_bundle_manifest(record: dict[str, Any], *, bundle_dir: Path) -> dict[str, Any] | None:
    manifest, _ = read_review_bundle_manifest_with_errors(
        "platform",
        record,
        bundle_dir=bundle_dir,
    )
    return manifest


def read_review_bundle_manifest_with_errors(
    target: str,
    record: dict[str, Any],
    *,
    bundle_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    review_bundle = record.get("review_bundle")
    if not isinstance(review_bundle, dict):
        return None, []
    manifest_record = review_bundle.get("manifest")
    if not isinstance(manifest_record, dict):
        return None, []
    raw_filename = manifest_record.get("file", "")
    if not isinstance(raw_filename, str) or not exact_safe_file_name(raw_filename):
        return None, [
            f"{target} staged upload review_bundle manifest.file "
            f"must be an exact safe file name, got {raw_filename!r}"
        ]
    filename = raw_filename
    manifest_path = bundle_dir / filename
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [
            f"{target} staged upload review_bundle manifest is not readable JSON: "
            f"{filename}: {exc}"
        ]
    if not isinstance(manifest, dict):
        return None, [
            f"{target} staged upload review_bundle manifest must be a JSON object: "
            f"{filename}"
        ]
    return manifest, []


def review_bundle_manifest_file_records(manifest: dict[str, Any]) -> list[Any]:
    records: list[Any] = []
    raw_bundle_type = manifest.get("bundle_type", "")
    bundle_type = raw_bundle_type if isinstance(raw_bundle_type, str) else ""
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


def prepare_output_directory(target: str, *, out_dir: object, force: bool) -> list[str]:
    out_dir_errors, out_dir_path = path_arg_value(
        out_dir,
        f"{target} staged upload output directory",
    )
    if out_dir_errors:
        return out_dir_errors
    assert out_dir_path is not None
    hint_errors = check_directory_path_hint(out_dir_path, f"{target} staged upload output directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(
        out_dir_path,
        f"{target} staged upload output directory",
    )
    if reserved_errors:
        return reserved_errors
    if out_dir_path.is_symlink():
        return [f"{target} staged upload output directory must not be a symlink: {out_dir_path}"]
    parent_errors = check_path_parent_symlinks(out_dir_path, f"{target} staged upload output directory")
    if parent_errors:
        return parent_errors
    if out_dir_path.exists():
        if not force:
            return [f"refusing to overwrite existing XP staged upload directory: {out_dir_path}"]
        if not out_dir_path.is_dir():
            return [f"XP staged upload output exists and is not a directory: {out_dir_path}"]
        for child in out_dir_path.iterdir():
            if child.is_symlink():
                return [f"{target} staged upload output must not contain symlinks: {child.name}"]
            if child.is_dir():
                return [
                    f"refusing to clear staged upload directory containing subdirectory: {child}"
                ]
            if not child.is_file():
                return [f"{target} staged upload output must contain regular files only: {child.name}"]
            child.unlink()
    out_dir_path.mkdir(parents=True, exist_ok=True)
    return []


def check_destination_path(target: str, destination: Path, filename: str) -> list[str]:
    if destination.is_symlink():
        return [f"{target} staged upload destination must not be a symlink: {filename}"]
    if destination.exists() and not destination.is_file():
        return [f"{target} staged upload destination must be a regular file: {filename}"]
    return []


def check_staged_output(
    target: str,
    *,
    out_dir: Path,
    expected_hashes: dict[str, str],
) -> list[str]:
    if out_dir.is_symlink():
        return [f"{target} staged upload output directory must not be a symlink: {out_dir}"]
    if not out_dir.is_dir():
        return [f"{target} staged upload output directory missing after copy: {out_dir}"]
    errors: list[str] = []
    root_files: set[str] = set()
    symlinked: list[str] = []
    non_files: list[str] = []
    for child in out_dir.iterdir():
        if child.is_symlink():
            symlinked.append(child.name)
        elif child.is_file():
            root_files.add(child.name)
        else:
            non_files.append(child.name)
    if symlinked:
        errors.append(f"{target} staged upload output contains symlinked entries: {sorted(symlinked)}")
    if non_files:
        errors.append(f"{target} staged upload output contains non-file entries: {sorted(non_files)}")
    expected_files = set(expected_hashes)
    missing = sorted(expected_files - root_files)
    unexpected = sorted(root_files - expected_files)
    if missing:
        errors.append(f"{target} staged upload output missing expected files: {missing}")
    if unexpected:
        errors.append(f"{target} staged upload output contains unexpected files: {unexpected}")
    for filename, expected_sha in sorted(expected_hashes.items()):
        path = out_dir / filename
        if filename in root_files and sha256_file(path) != expected_sha:
            errors.append(f"{target} staged upload output SHA-256 mismatch: {filename}")
    return errors


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink() and not is_allowed_platform_parent_symlink(parent):
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: Path, label: str) -> list[str]:
    raw_path = path.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def check_path_not_reserved_workspace_root(path: Path, label: str) -> list[str]:
    roots: list[Path] = [Path.cwd(), ROOT]
    seen_roots: set[Path] = set()
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if root_resolved in seen_roots:
            continue
        seen_roots.add(root_resolved)
        path_resolved = (path if path.is_absolute() else root_resolved / path).resolve(strict=False)
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
                f"{reserved_root!r}: {path}"
            ]
    return []


def check_target_release_path_segments(
    target: str,
    release_tag: str,
    path: Path,
    *,
    label: str,
) -> list[str]:
    parts = tuple(str(part) for part in path.parts if str(part))
    segments = set(parts)
    raw_path = path.as_posix()
    errors: list[str] = []
    if target not in segments:
        errors.append(f"{label} must include target path segment {target!r}, got {raw_path!r}")
    if release_tag not in segments:
        errors.append(f"{label} must include release_tag path segment {release_tag!r}, got {raw_path!r}")
    if not errors and not has_adjacent_target_release_segments(parts, target, release_tag):
        errors.append(
            f"{label} must include adjacent target/release path segment "
            f"{target}/{release_tag}, got {raw_path!r}"
        )
    return errors


def has_adjacent_target_release_segments(
    parts: tuple[str, ...],
    target: str,
    release_tag: str,
) -> bool:
    return any(
        part == target and index + 1 < len(parts) and parts[index + 1] == release_tag
        for index, part in enumerate(parts)
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_HEX_CHARS


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
        if not exact_safe_file_name(filename):
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
