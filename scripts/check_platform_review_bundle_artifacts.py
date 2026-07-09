from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    KNOWN_TARGETS,
    PROTECTED_GOAL_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    accepted_record_source_file,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    exact_safe_file_name,
    read_json,
)
from finalize_platform_verified_evidence_record import (  # noqa: E402
    check_archive_entry_safety,
    finalize_platform_verified_evidence_record,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strict_errors = strict_platform_goal_arg_errors(args)
    if strict_errors:
        for error in strict_errors:
            print(f"platform review bundle artifacts: {error}", file=sys.stderr)
        return 2
    required_targets = required_targets_from_args(args)
    registry = read_json(args.registry)
    errors = check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=args.bundle_dir,
        required_targets=required_targets,
        required_release_tag=args.release_tag,
        require_final_record_assets=args.require_final_record_assets,
    )
    if errors:
        for error in errors:
            print(f"platform review bundle artifacts: {error}", file=sys.stderr)
        return 1
    print("platform review bundle artifact checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate accepted platform evidence records against downloaded review bundle artifacts."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=EVIDENCE_PATH,
        help="accepted platform evidence registry JSON",
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="directory containing review bundle manifest, ZIP and SHA-256 sidecar files",
    )
    parser.add_argument(
        "--require-target",
        action="append",
        choices=sorted(KNOWN_TARGETS),
        default=[],
        help="require a bundle-backed accepted evidence record for this protected target",
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help="require bundle-backed accepted evidence for all protected goal targets; requires --release-tag",
    )
    parser.add_argument(
        "--release-tag",
        help="When requiring targets, require bundle-backed accepted evidence for this exact release tag.",
    )
    parser.add_argument(
        "--require-final-record-assets",
        action="store_true",
        help=(
            "Also require each finalized public accepted-record JSON asset in --bundle-dir "
            "and verify it matches the accepted registry entry."
        ),
    )
    return parser.parse_args(argv)


def strict_platform_goal_arg_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    errors.extend(check_registry_path(args.registry))
    if args.require_goal_targets and not args.release_tag:
        errors.append("--require-goal-targets requires --release-tag vX.Y.Z")
    return errors


def check_registry_path(path: object) -> list[str]:
    path_errors, path_value = path_arg_value(path, "accepted evidence registry")
    if path_errors:
        return path_errors
    assert path_value is not None
    errors = check_path_not_reserved_workspace_root(path_value, "accepted evidence registry")
    if errors:
        return errors
    if path_value.is_symlink():
        return [f"accepted evidence registry must not be a symlink: {path_value}"]
    return check_path_parent_symlinks(path_value, "accepted evidence registry")


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def required_target_filter(raw_targets: object) -> tuple[set[str], bool]:
    if raw_targets is None:
        return set(), False
    if isinstance(raw_targets, str):
        raw_targets = (raw_targets,)
    try:
        target_values = tuple(raw_targets)
    except TypeError:
        return set(), True
    targets = {
        target
        for target in target_values
        if isinstance(target, str) and target and target == target.strip()
    }
    return targets, bool(target_values)


def required_targets_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    targets, _has_required_targets = required_target_filter(args.require_target)
    if args.require_goal_targets:
        targets.update(PROTECTED_GOAL_TARGETS)
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets) + tuple(
        sorted(targets - set(PROTECTED_GOAL_TARGETS))
    )


def check_platform_review_bundle_artifacts(
    *,
    registry: dict[str, Any],
    bundle_dir: object,
    required_targets: tuple[str, ...] | list[str] | set[str] | None = None,
    required_release_tag: str | None = None,
    require_final_record_assets: bool = False,
) -> list[str]:
    validation_errors = check_platform_verified_evidence(
        registry=registry,
        required_targets=required_targets,
        required_release_tag=required_release_tag,
        require_review_bundles=True,
    )
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return validation_errors or ["accepted_evidence must be a list"]
    if validation_errors and not has_record_scoped_validation_errors(validation_errors, rows):
        return validation_errors
    path_errors, bundle_dir_path = path_arg_value(bundle_dir, "review bundle directory")
    if path_errors:
        return [*validation_errors, *path_errors]
    assert bundle_dir_path is not None
    hint_errors = check_directory_path_hint(bundle_dir_path, "review bundle directory")
    if hint_errors:
        return [*validation_errors, *hint_errors]
    reserved_errors = check_path_not_reserved_workspace_root(bundle_dir_path, "review bundle directory")
    if reserved_errors:
        return [*validation_errors, *reserved_errors]
    if bundle_dir_path.is_symlink():
        return [*validation_errors, f"review bundle directory must not be a symlink: {bundle_dir_path}"]
    parent_errors = check_path_parent_symlinks(bundle_dir_path, "review bundle directory")
    if parent_errors:
        return [*validation_errors, *parent_errors]
    bundle_root = bundle_dir_path.resolve()
    if not bundle_root.is_dir():
        return [*validation_errors, f"review bundle directory missing: {bundle_dir_path}"]
    artifact_errors: list[str] = []
    for record in records_for_artifact_validation(
        rows,
        required_targets=required_targets,
        required_release_tag=required_release_tag,
    ):
        if isinstance(record, dict):
            artifact_errors.extend(
                check_record_review_bundle_artifacts(
                    record,
                    bundle_root,
                    require_final_record_asset=require_final_record_assets,
                )
            )
    return [*validation_errors, *artifact_errors]


def records_for_artifact_validation(
    rows: list[Any],
    *,
    required_targets: tuple[str, ...] | list[str] | set[str] | None = None,
    required_release_tag: str | None = None,
) -> list[dict[str, Any]]:
    target_filter, has_target_filter = required_target_filter(required_targets)
    records: list[dict[str, Any]] = []
    for record in rows:
        if not isinstance(record, dict):
            continue
        target = accepted_record_target(record)
        if has_target_filter and target not in target_filter:
            continue
        if required_release_tag and record.get("release_tag") != required_release_tag:
            continue
        records.append(record)
    return records


def has_record_scoped_validation_errors(errors: list[str], rows: list[Any]) -> bool:
    targets = {
        accepted_record_target(record)
        for record in rows
        if isinstance(record, dict) and accepted_record_target(record)
    }
    return any(error.startswith(f"{target} ") for error in errors for target in targets)


def check_record_review_bundle_artifacts(
    record: dict[str, Any],
    bundle_root: object,
    *,
    require_final_record_asset: bool = False,
) -> list[str]:
    target = accepted_record_target(record)
    if not target:
        return [f"review bundle accepted evidence target must be a string, got {record.get('target')!r}"]
    review_bundle = record.get("review_bundle")
    if not isinstance(review_bundle, dict):
        return [f"{target} review_bundle must be an object"]
    path_errors, bundle_root_path = path_arg_value(bundle_root, "review bundle directory")
    if path_errors:
        return path_errors
    assert bundle_root_path is not None
    errors: list[str] = []
    paths: dict[str, Path] = {}
    for key in ("manifest", "archive", "sha256s"):
        raw_record = review_bundle.get(key)
        if not isinstance(raw_record, dict):
            errors.append(f"{target} review_bundle {key} must be an object")
            continue
        raw_filename = raw_record.get("file", "")
        if not isinstance(raw_filename, str):
            errors.append(f"{target} review_bundle {key}.file must be a string, got {raw_filename!r}")
            continue
        filename = raw_filename
        if not exact_safe_file_name(filename):
            errors.append(
                f"{target} review_bundle {key}.file must be an exact safe file name: {filename!r}"
            )
            continue
        path = bundle_root_path / filename
        paths[key] = path
        errors.extend(check_file_record(target, key, path, raw_record))
    if errors:
        return errors

    manifest = load_json(paths["manifest"], f"{target} review bundle manifest", errors)
    if manifest is None:
        return errors
    candidate_name = candidate_record_name(target, manifest, errors)
    if not candidate_name:
        return errors
    candidate_bytes = read_archive_file(paths["archive"], candidate_name, errors, target)
    if candidate_bytes is None:
        return errors
    candidate = parse_json_bytes(candidate_bytes, f"{target} archived candidate_record", errors)
    if candidate is None:
        return errors
    expected_candidate = prefinalized_candidate_record(record)
    if candidate != expected_candidate:
        errors.append(
            f"{target} archived candidate_record must match accepted evidence record before finalization"
        )

    with tempfile.TemporaryDirectory(prefix=f"{target}-bundle-") as raw_tmp:
        candidate_path = Path(raw_tmp) / candidate_name
        candidate_path.write_bytes(candidate_bytes)
        finalizer_errors, finalized = finalize_platform_verified_evidence_record(
            candidate_record=candidate_path,
            bundle_manifest=paths["manifest"],
            bundle_archive=paths["archive"],
            bundle_sha256s=paths["sha256s"],
        )
    errors.extend(f"{target} {error}" for error in finalizer_errors)
    if not finalizer_errors and finalized != record:
        errors.append(f"{target} finalized review bundle record must match accepted evidence registry entry")
    if require_final_record_asset:
        errors.extend(check_final_record_asset(record, bundle_root_path))
    return errors


def check_final_record_asset(record: dict[str, Any], bundle_root: object) -> list[str]:
    target = accepted_record_target(record)
    if not target:
        return [f"finalized accepted-record asset target must be a string, got {record.get('target')!r}"]
    path_errors, bundle_root_path = path_arg_value(bundle_root, f"{target} finalized accepted-record asset directory")
    if path_errors:
        return path_errors
    assert bundle_root_path is not None
    filename = accepted_record_source_file(target)
    path = bundle_root_path / filename
    parent_errors = check_path_parent_symlinks(path, f"{target} finalized accepted-record asset")
    if parent_errors:
        return parent_errors
    if path.is_symlink():
        return [f"{target} finalized accepted-record asset must not be a symlink: {filename}"]
    if not path.is_file():
        return [f"{target} finalized accepted-record asset missing from bundle directory: {filename}"]
    try:
        raw_bytes = path.read_bytes()
        data = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} finalized accepted-record asset is not readable JSON: {filename}: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} finalized accepted-record asset must contain a JSON object: {filename}"]
    key_errors = public_record_key_errors(target, record)
    if key_errors:
        return key_errors
    if data != public_record(record):
        return [f"{target} finalized accepted-record asset must match accepted registry record: {filename}"]
    if raw_bytes != canonical_public_record_bytes(record):
        return [f"{target} finalized accepted-record asset must use canonical sorted JSON: {filename}"]
    return []


def accepted_record_target(record: dict[str, Any]) -> str:
    target = record.get("target")
    return target if isinstance(target, str) else ""


def public_record_key_errors(target: str, record: dict[str, Any]) -> list[str]:
    invalid = [key for key in record if not isinstance(key, str)]
    if invalid:
        return [
            f"{target} finalized accepted-record registry keys must be strings, "
            f"got {invalid[0]!r}"
        ]
    return []


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if isinstance(key, str) and not key.startswith("_")
    }


def canonical_public_record_bytes(record: dict[str, Any]) -> bytes:
    return (json.dumps(public_record(record), indent=2, sort_keys=True) + "\n").encode("utf-8")


def prefinalized_candidate_record(record: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(record)
    candidate.pop("review_bundle", None)
    candidate.pop("finalized_record_release_asset_url", None)
    source = candidate.get("release_asset_source")
    artifact_hashes = candidate.get("artifact_sha256")
    if isinstance(source, dict) and isinstance(artifact_hashes, dict):
        source_data = dict(source)
        source_data["contains_files"] = sorted(
            name
            for name in artifact_hashes
            if isinstance(name, str) and exact_safe_file_name(name)
        )
        candidate["release_asset_source"] = source_data
    return candidate


def check_file_record(target: str, key: str, path: object, raw_record: dict[str, Any]) -> list[str]:
    path_errors, path_value = path_arg_value(path, f"{target} review_bundle {key} file")
    if path_errors:
        return path_errors
    assert path_value is not None
    errors: list[str] = []
    if path_value.is_symlink():
        return [f"{target} review_bundle {key} file must not be a symlink: {path_value.name}"]
    if not path_value.is_file():
        return [f"{target} review_bundle {key} file missing: {path_value.name}"]
    expected_size = raw_record.get("size_bytes")
    if (
        not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
        or expected_size != path_value.stat().st_size
    ):
        errors.append(f"{target} review_bundle {key}.size_bytes does not match file {path_value.name}")
    expected_sha = raw_record.get("sha256", "")
    if not isinstance(expected_sha, str):
        errors.append(
            f"{target} review_bundle {key}.sha256 must be a string SHA-256 hex digest, "
            f"got {expected_sha!r}"
        )
    elif expected_sha != sha256_file(path_value):
        errors.append(f"{target} review_bundle {key}.sha256 does not match file {path_value.name}")
    return errors


def candidate_record_name(target: str, manifest: dict[str, Any], errors: list[str]) -> str:
    raw_record = manifest.get("candidate_record")
    if not isinstance(raw_record, dict):
        errors.append(f"{target} review bundle manifest candidate_record must be an object")
        return ""
    raw_filename = raw_record.get("file", "")
    if not isinstance(raw_filename, str):
        errors.append(
            f"{target} review bundle manifest candidate_record.file must be a string, "
            f"got {raw_filename!r}"
        )
        return ""
    filename = raw_filename
    if not exact_safe_file_name(filename):
        errors.append(
            f"{target} review bundle manifest candidate_record.file must be an exact safe file name: {filename!r}"
        )
        return ""
    return filename


def read_archive_file(
    archive_path: object,
    filename: str,
    errors: list[str],
    target: str,
) -> bytes | None:
    path_errors, archive_path_value = path_arg_value(archive_path, f"{target} review bundle archive")
    if path_errors:
        errors.extend(path_errors)
        return None
    assert archive_path_value is not None
    try:
        with zipfile.ZipFile(archive_path_value) as archive:
            archive_safety_errors = check_archive_entry_safety(archive.infolist())
            if archive_safety_errors:
                errors.extend(f"{target} {error}" for error in archive_safety_errors)
                return None
            try:
                return archive.read(filename)
            except KeyError:
                errors.append(f"{target} review bundle archive missing candidate_record: {filename}")
                return None
            except (RuntimeError, NotImplementedError, OSError, zipfile.BadZipFile) as exc:
                errors.append(f"{target} review bundle archive candidate_record is not readable: {filename}: {exc}")
                return None
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"{target} review bundle archive is not a readable ZIP: {archive_path_value.name}: {exc}")
        return None


def parse_json_bytes(raw_data: bytes, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(raw_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not UTF-8 JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return data


def load_json(path: object, label: str, errors: list[str]) -> dict[str, Any] | None:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        errors.extend(path_errors)
        return None
    assert path_value is not None
    try:
        data = json.loads(path_value.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not readable JSON: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


if __name__ == "__main__":
    raise SystemExit(main())
