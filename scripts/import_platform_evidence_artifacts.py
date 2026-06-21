from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
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
    GITHUB_ACTIONS_RUN_RE,
    PROTECTED_GOAL_TARGETS,
    RELEASE_SOURCE_HEAD_SHA_RE,
    accepted_record_source_file,
    check_platform_verified_evidence,
    read_json,
    release_source_workflow,
)
from make_platform_verified_evidence_record import sha256_file  # noqa: E402

EXPECTED_SOURCE_WORKFLOW_NAMES = {
    "linux-i386": "extended-platform-evidence",
    "linux-armhf": "extended-platform-evidence",
    "windows-xp-native-x86": "xp-native-evidence",
    "windows-xp-native-x64": "xp-native-evidence",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    required_targets = required_targets_from_args(args)
    registry = read_json(args.registry)
    errors = check_platform_verified_evidence(
        registry=registry,
        required_targets=required_targets,
        required_release_tag=args.release_tag,
        require_review_bundles=True,
    )
    if errors:
        for error in errors:
            print(f"platform evidence import: {error}", file=sys.stderr)
        return 1

    records = accepted_records(registry, release_tag=args.release_tag, targets=required_targets)
    release_head_sha = None if args.dry_run else current_checkout_head_sha()
    import_errors = import_platform_evidence_artifacts(
        records,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
        release_head_sha=release_head_sha,
    )
    if import_errors:
        for error in import_errors:
            print(f"platform evidence import: {error}", file=sys.stderr)
        return 1
    print(f"platform evidence import passed for {len(records)} records")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download accepted protected-platform evidence artifacts from their "
            "recorded GitHub Actions source runs into the tagged release asset directory."
        )
    )
    parser.add_argument("--registry", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--release-tag", required=True, help="release tag, for example v1.0.2")
    parser.add_argument(
        "--require-target",
        action="append",
        choices=sorted(PROTECTED_GOAL_TARGETS),
        default=[],
        help="accepted evidence target to import",
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help="import all protected goal targets; requires accepted evidence for --release-tag",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate records and print gh commands without downloading artifacts",
    )
    return parser.parse_args(argv)


def required_targets_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    targets = set(str(target) for target in args.require_target)
    if args.require_goal_targets:
        targets.update(PROTECTED_GOAL_TARGETS)
    if not targets:
        targets.update(PROTECTED_GOAL_TARGETS)
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets)


def accepted_records(
    registry: dict[str, Any],
    *,
    release_tag: str,
    targets: tuple[str, ...],
) -> list[dict[str, Any]]:
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    target_set = set(targets)
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == release_tag
        and str(row.get("target", "")) in target_set
    ]


def import_platform_evidence_artifacts(
    records: list[dict[str, Any]],
    *,
    out_dir: Path,
    dry_run: bool = False,
    release_head_sha: str | None = None,
) -> list[str]:
    errors: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="platform-evidence-import-") as tmp:
        download_root = Path(tmp)
        for record in records:
            errors.extend(
                import_record(
                    record,
                    out_dir=out_dir,
                    download_root=download_root,
                    dry_run=dry_run,
                    release_head_sha=release_head_sha,
                )
            )
    return errors


def import_record(
    record: dict[str, Any],
    *,
    out_dir: Path,
    download_root: Path,
    dry_run: bool,
    release_head_sha: str | None = None,
) -> list[str]:
    target = str(record.get("target", ""))
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(run_url)
    artifact_name = str(source.get("artifact_name", "")).strip()
    expected_head_sha = str(source.get("head_sha", "")).strip()
    expected_workflow = release_source_workflow(target)
    workflow = str(source.get("workflow", "")).strip()
    if not run_match:
        return [f"{target} release_asset_source.workflow_run_url must be a GitHub Actions run URL"]
    if workflow != expected_workflow:
        return [f"{target} release_asset_source.workflow must be {expected_workflow}"]
    if not artifact_name:
        return [f"{target} release_asset_source.artifact_name must be set"]
    if not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(expected_head_sha):
        return [f"{target} release_asset_source.head_sha must be a 40-character lowercase Git SHA"]
    repository = run_match.group(1)
    run_id = run_url.rstrip("/").rsplit("/", 1)[-1]
    destination = download_root / target
    view_command = source_run_view_command(run_id, repository)
    command = [
        "gh",
        "run",
        "download",
        run_id,
        "--repo",
        repository,
        "--name",
        artifact_name,
        "--dir",
        str(destination),
    ]
    if dry_run:
        print(" ".join(view_command))
        print(" ".join(command))
    else:
        errors = verify_source_run(
            target,
            view_command,
            expected_head_sha=expected_head_sha,
            release_head_sha=release_head_sha,
        )
        if errors:
            return errors
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            return [f"{target} failed to download release_asset_source artifact {artifact_name}: {exc}"]
    if dry_run:
        return []
    errors = validate_source_artifact(record, source_root=destination)
    if errors:
        return errors
    errors = copy_expected_files(record, source_root=destination, out_dir=out_dir)
    if not errors:
        errors.extend(check_imported_hashes(record, out_dir=out_dir))
    if not errors:
        errors.extend(check_imported_review_bundle(record, out_dir=out_dir))
    return errors


def source_run_view_command(run_id: str, repository: str) -> list[str]:
    return [
        "gh",
        "run",
        "view",
        run_id,
        "--repo",
        repository,
        "--json",
        "conclusion,event,headSha,status,workflowName",
    ]


def verify_source_run(
    target: str,
    command: list[str],
    *,
    expected_head_sha: str,
    release_head_sha: str | None = None,
) -> list[str]:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"{target} failed to inspect release_asset_source workflow run: {exc}"]
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [f"{target} release_asset_source workflow run metadata is not JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} release_asset_source workflow run metadata must be a JSON object"]
    errors: list[str] = []
    if data.get("status") != "completed":
        errors.append(
            f"{target} release_asset_source workflow run status must be completed, got {data.get('status')!r}"
        )
    if data.get("conclusion") != "success":
        errors.append(
            f"{target} release_asset_source workflow run conclusion must be success, got {data.get('conclusion')!r}"
        )
    if data.get("event") != "workflow_dispatch":
        errors.append(
            f"{target} release_asset_source workflow run event must be workflow_dispatch, got {data.get('event')!r}"
        )
    expected_workflow = EXPECTED_SOURCE_WORKFLOW_NAMES.get(target)
    if expected_workflow and data.get("workflowName") != expected_workflow:
        errors.append(
            f"{target} release_asset_source workflow run name must be {expected_workflow!r}, "
            f"got {data.get('workflowName')!r}"
        )
    if data.get("headSha") != expected_head_sha:
        errors.append(
            f"{target} release_asset_source workflow run headSha must match accepted record "
            f"{expected_head_sha}, got {data.get('headSha')!r}"
        )
    if release_head_sha is not None and expected_head_sha != release_head_sha:
        errors.append(
            f"{target} release_asset_source.head_sha must match release checkout {release_head_sha}, "
            f"got {expected_head_sha}"
        )
    return errors


def current_checkout_head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def copy_expected_files(record: dict[str, Any], *, source_root: Path, out_dir: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    expected_files = expected_release_files(record)
    if not source_root.is_dir():
        errors.append(f"{target} downloaded artifact directory missing: {source_root}")
    for filename in sorted(expected_files):
        source = source_root / filename
        if source.is_symlink():
            errors.append(f"{target} release asset import source must not be a symlink: {filename}")
        elif not source.is_file():
            errors.append(f"{target} downloaded artifact missing expected release file: {filename}")
    if errors:
        return errors
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in sorted(expected_files):
        source = source_root / filename
        destination = out_dir / filename
        if destination.exists() and sha256_file(destination) != sha256_file(source):
            errors.append(f"{target} release asset import would overwrite different file: {filename}")
            continue
        shutil.copy2(source, destination)
    return errors


def validate_source_artifact(record: dict[str, Any], *, source_root: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors = validate_downloaded_source_file_set(
        target,
        source_root=source_root,
        expected_files=expected_source_files(record),
    )
    if errors:
        return errors
    return validate_downloaded_final_record(record, source_root=source_root)


def validate_downloaded_source_file_set(
    target: str,
    *,
    source_root: Path,
    expected_files: set[str],
) -> list[str]:
    if not source_root.is_dir():
        return [f"{target} downloaded artifact directory missing: {source_root}"]
    errors: list[str] = []
    root_files: set[str] = set()
    root_directories: list[str] = []
    root_symlinks: list[str] = []
    for child in source_root.iterdir():
        if child.is_symlink():
            root_symlinks.append(child.name)
        elif child.is_file():
            root_files.add(child.name)
        elif child.is_dir():
            root_directories.append(child.name)
    if root_symlinks:
        errors.append(f"{target} downloaded artifact must not contain symlinks: {sorted(root_symlinks)}")
    if root_directories:
        errors.append(
            f"{target} downloaded artifact must contain root files only, found directories: {sorted(root_directories)}"
        )
    for filename in sorted(expected_files - root_files):
        errors.append(f"{target} downloaded artifact missing expected release file: {filename}")
    unexpected = sorted(root_files - expected_files)
    if unexpected:
        errors.append(f"{target} downloaded artifact contains unexpected files: {unexpected}")
    return errors


def check_imported_hashes(record: dict[str, Any], *, out_dir: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for filename, digest in sorted(artifact_hashes.items()):
            path = out_dir / str(filename)
            if path.is_file() and sha256_file(path) != str(digest):
                errors.append(f"{target} imported native artifact SHA-256 mismatch: {filename}")
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = str(bundle_record.get("file", ""))
            path = out_dir / filename
            if path.is_file() and sha256_file(path) != str(bundle_record.get("sha256", "")):
                errors.append(f"{target} imported review bundle {key} SHA-256 mismatch: {filename}")
    return errors


def check_imported_review_bundle(record: dict[str, Any], *, out_dir: Path) -> list[str]:
    registry = read_json(EVIDENCE_PATH)
    errors = check_platform_review_bundle_artifacts(
        registry={**registry, "accepted_evidence": [public_record(record)]},
        bundle_dir=out_dir,
    )
    return [f"{str(record.get('target', ''))} imported review bundle validation failed: {error}" for error in errors]


def expected_release_files(record: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        files.update(str(name) for name in artifact_hashes)
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if isinstance(bundle_record, dict):
                filename = str(bundle_record.get("file", ""))
                if filename:
                    files.add(filename)
    return files


def expected_source_files(record: dict[str, Any]) -> set[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return expected_release_files(record)
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list):
        return expected_release_files(record)
    return {Path(str(name)).name for name in raw_files if str(name).strip()}


def validate_downloaded_final_record(record: dict[str, Any], *, source_root: Path) -> list[str]:
    target = str(record.get("target", ""))
    if target not in PROTECTED_GOAL_TARGETS:
        return []
    filename = accepted_record_source_file(target)
    path = source_root / filename
    if not path.is_file():
        return [f"{target} downloaded artifact missing finalized accepted record: {filename}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} finalized accepted record source file is not readable JSON: {filename}: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} finalized accepted record source file must contain a JSON object: {filename}"]
    if data != public_record(record):
        return [f"{target} finalized accepted record source file must match accepted registry record: {filename}"]
    return []


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if not str(key).startswith("_")}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
