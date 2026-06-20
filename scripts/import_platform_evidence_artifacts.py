from __future__ import annotations

import argparse
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

from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    GITHUB_ACTIONS_RUN_RE,
    PROTECTED_GOAL_TARGETS,
    check_platform_verified_evidence,
    read_json,
)
from make_platform_verified_evidence_record import sha256_file  # noqa: E402


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
    import_errors = import_platform_evidence_artifacts(
        records,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
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
) -> list[str]:
    errors: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="platform-evidence-import-") as tmp:
        download_root = Path(tmp)
        for record in records:
            errors.extend(import_record(record, out_dir=out_dir, download_root=download_root, dry_run=dry_run))
    return errors


def import_record(
    record: dict[str, Any],
    *,
    out_dir: Path,
    download_root: Path,
    dry_run: bool,
) -> list[str]:
    target = str(record.get("target", ""))
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(run_url)
    artifact_name = str(source.get("artifact_name", "")).strip()
    if not run_match:
        return [f"{target} release_asset_source.workflow_run_url must be a GitHub Actions run URL"]
    if not artifact_name:
        return [f"{target} release_asset_source.artifact_name must be set"]
    repository = run_match.group(1)
    run_id = run_url.rstrip("/").rsplit("/", 1)[-1]
    destination = download_root / target
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
        print(" ".join(command))
    else:
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            return [f"{target} failed to download release_asset_source artifact {artifact_name}: {exc}"]
    if dry_run:
        return []
    errors = copy_expected_files(record, source_root=destination, out_dir=out_dir)
    if not errors:
        errors.extend(check_imported_hashes(record, out_dir=out_dir))
    return errors


def copy_expected_files(record: dict[str, Any], *, source_root: Path, out_dir: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in sorted(expected_release_files(record)):
        matches = [path for path in source_root.rglob(filename) if path.is_file()]
        if not matches:
            errors.append(f"{target} downloaded artifact missing expected release file: {filename}")
            continue
        if len(matches) > 1:
            errors.append(f"{target} downloaded artifact contains duplicate release file: {filename}")
            continue
        destination = out_dir / filename
        if destination.exists() and sha256_file(destination) != sha256_file(matches[0]):
            errors.append(f"{target} release asset import would overwrite different file: {filename}")
            continue
        shutil.copy2(matches[0], destination)
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
