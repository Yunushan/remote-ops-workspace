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
    check_platform_verified_evidence,
    exact_safe_file_name,
    read_json,
)
from finalize_platform_verified_evidence_record import (  # noqa: E402
    check_archive_entry_safety,
    finalize_platform_verified_evidence_record,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    required_targets = required_targets_from_args(args)
    registry = read_json(args.registry)
    errors = check_platform_review_bundle_artifacts(
        registry=registry,
        bundle_dir=args.bundle_dir,
        required_targets=required_targets,
        required_release_tag=args.release_tag,
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
    return parser.parse_args(argv)


def required_targets_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    targets = set(str(target) for target in args.require_target)
    if args.require_goal_targets:
        targets.update(PROTECTED_GOAL_TARGETS)
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets) + tuple(
        sorted(targets - set(PROTECTED_GOAL_TARGETS))
    )


def check_platform_review_bundle_artifacts(
    *,
    registry: dict[str, Any],
    bundle_dir: Path,
    required_targets: tuple[str, ...] | list[str] | set[str] | None = None,
    required_release_tag: str | None = None,
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
    if bundle_dir.is_symlink():
        return [*validation_errors, f"review bundle directory must not be a symlink: {bundle_dir}"]
    parent_errors = check_path_parent_symlinks(bundle_dir, "review bundle directory")
    if parent_errors:
        return [*validation_errors, *parent_errors]
    bundle_root = bundle_dir.resolve()
    if not bundle_root.is_dir():
        return [*validation_errors, f"review bundle directory missing: {bundle_dir}"]
    artifact_errors: list[str] = []
    for record in rows:
        if isinstance(record, dict):
            artifact_errors.extend(check_record_review_bundle_artifacts(record, bundle_root))
    return [*validation_errors, *artifact_errors]


def has_record_scoped_validation_errors(errors: list[str], rows: list[Any]) -> bool:
    targets = {
        str(record.get("target", ""))
        for record in rows
        if isinstance(record, dict) and str(record.get("target", ""))
    }
    return any(error.startswith(f"{target} ") for error in errors for target in targets)


def check_record_review_bundle_artifacts(record: dict[str, Any], bundle_root: Path) -> list[str]:
    target = str(record.get("target", ""))
    review_bundle = record.get("review_bundle")
    if not isinstance(review_bundle, dict):
        return [f"{target} review_bundle must be an object"]
    errors: list[str] = []
    paths: dict[str, Path] = {}
    for key in ("manifest", "archive", "sha256s"):
        raw_record = review_bundle.get(key)
        if not isinstance(raw_record, dict):
            errors.append(f"{target} review_bundle {key} must be an object")
            continue
        filename = str(raw_record.get("file", ""))
        if not exact_safe_file_name(filename):
            errors.append(
                f"{target} review_bundle {key}.file must be an exact safe file name: {filename!r}"
            )
            continue
        path = bundle_root / filename
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
    return errors


def prefinalized_candidate_record(record: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(record)
    candidate.pop("review_bundle", None)
    candidate.pop("finalized_record_release_asset_url", None)
    source = candidate.get("release_asset_source")
    artifact_hashes = candidate.get("artifact_sha256")
    if isinstance(source, dict) and isinstance(artifact_hashes, dict):
        source_data = dict(source)
        source_data["contains_files"] = sorted(str(name) for name in artifact_hashes)
        candidate["release_asset_source"] = source_data
    return candidate


def check_file_record(target: str, key: str, path: Path, raw_record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if path.is_symlink():
        return [f"{target} review_bundle {key} file must not be a symlink: {path.name}"]
    if not path.is_file():
        return [f"{target} review_bundle {key} file missing: {path.name}"]
    expected_size = raw_record.get("size_bytes")
    if expected_size != path.stat().st_size:
        errors.append(f"{target} review_bundle {key}.size_bytes does not match file {path.name}")
    expected_sha = str(raw_record.get("sha256", ""))
    if expected_sha != sha256_file(path):
        errors.append(f"{target} review_bundle {key}.sha256 does not match file {path.name}")
    return errors


def candidate_record_name(target: str, manifest: dict[str, Any], errors: list[str]) -> str:
    raw_record = manifest.get("candidate_record")
    if not isinstance(raw_record, dict):
        errors.append(f"{target} review bundle manifest candidate_record must be an object")
        return ""
    filename = str(raw_record.get("file", ""))
    if not exact_safe_file_name(filename):
        errors.append(
            f"{target} review bundle manifest candidate_record.file must be an exact safe file name: {filename!r}"
        )
        return ""
    return filename


def read_archive_file(
    archive_path: Path,
    filename: str,
    errors: list[str],
    target: str,
) -> bytes | None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive_safety_errors = check_archive_entry_safety(archive.infolist())
            if archive_safety_errors:
                errors.extend(f"{target} {error}" for error in archive_safety_errors)
                return None
            try:
                return archive.read(filename)
            except KeyError:
                errors.append(f"{target} review bundle archive missing candidate_record: {filename}")
                return None
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"{target} review bundle archive is not a readable ZIP: {archive_path.name}: {exc}")
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


def load_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
