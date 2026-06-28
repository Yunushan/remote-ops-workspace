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
    GITHUB_RELEASE_ASSET_RE,
    PROTECTED_GOAL_TARGETS,
    RELEASE_SOURCE_HEAD_SHA_RE,
    accepted_record_source_file,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    exact_safe_file_name,
    linux_release_source_artifact_name,
    read_json,
    release_asset_repositories,
    release_source_workflow,
    xp_release_source_artifact_name,
)
from make_platform_verified_evidence_record import sha256_file  # noqa: E402

SOURCE_RUN_METADATA_JQ = (
    "{id: .id, htmlUrl: .html_url, attempt: .run_attempt, status: .status, "
    "conclusion: .conclusion, event: .event, headSha: .head_sha, path: .path}"
)
SOURCE_RUN_ARTIFACTS_PAGE_SIZE = 100
REQUIRE_VERIFY_SOURCE_RUN_DRY_RUN_ERROR = (
    "--dry-run for the protected platform goal requires --verify-source-run"
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    arg_errors = strict_import_arg_errors(args)
    if arg_errors:
        for error in arg_errors:
            print(f"platform evidence import: {error}", file=sys.stderr)
        return 2
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
    release_head_sha = current_checkout_head_sha()
    import_errors = import_platform_evidence_artifacts(
        records,
        out_dir=args.out_dir,
        dry_run=args.dry_run,
        verify_source_run_metadata=args.verify_source_run,
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
    parser.add_argument(
        "--verify-source-run",
        action="store_true",
        help=(
            "inspect each recorded GitHub Actions source run and source artifact "
            "inventory during --dry-run; real imports always verify source-run "
            "metadata and artifact inventory before downloading artifacts; "
            "required for protected-goal dry-runs"
        ),
    )
    return parser.parse_args(argv)


def strict_import_arg_errors(args: argparse.Namespace) -> list[str]:
    if not args.dry_run or args.verify_source_run:
        return []
    requested_targets = set(str(target) for target in args.require_target)
    protected_targets = set(PROTECTED_GOAL_TARGETS)
    is_full_goal = args.require_goal_targets or not requested_targets or requested_targets == protected_targets
    if is_full_goal:
        return [REQUIRE_VERIFY_SOURCE_RUN_DRY_RUN_ERROR]
    return []


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
    verify_source_run_metadata: bool = False,
    release_head_sha: str | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(ensure_output_directory(out_dir))
    if records and not dry_run:
        errors.extend(check_output_directory_empty(out_dir))
    if errors:
        return errors
    if records and (not dry_run or verify_source_run_metadata):
        errors.extend(check_github_cli_available())
    if errors:
        return errors
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
                    verify_source_run_metadata=verify_source_run_metadata,
                    release_head_sha=release_head_sha,
                )
            )
    return errors


def ensure_output_directory(out_dir: Path) -> list[str]:
    hint_errors = check_directory_path_hint(out_dir, "release asset import output directory")
    if hint_errors:
        return hint_errors
    if out_dir.is_symlink():
        return [f"release asset import output directory must not be a symlink: {out_dir}"]
    parent_errors = check_path_parent_symlinks(out_dir, "release asset import output directory")
    if parent_errors:
        return parent_errors
    if out_dir.exists() and not out_dir.is_dir():
        return [f"release asset import output path must be a directory: {out_dir}"]
    return []


def check_output_directory_empty(out_dir: Path) -> list[str]:
    if not out_dir.exists():
        return []
    entries = sorted(path.name for path in out_dir.iterdir())
    if entries:
        return [
            "release asset import output directory must be empty before import: "
            f"{entries}"
        ]
    return []


def check_github_cli_available() -> list[str]:
    if shutil.which("gh") is None:
        return [
            "GitHub CLI `gh` is required to import accepted platform evidence artifacts; "
            "install gh or run inside GitHub Actions with GH_TOKEN configured"
        ]
    return []


def check_directory_path_hint(path: Path, label: str) -> list[str]:
    raw_path = path.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def import_record(
    record: dict[str, Any],
    *,
    out_dir: Path,
    download_root: Path,
    dry_run: bool,
    verify_source_run_metadata: bool = False,
    release_head_sha: str | None = None,
) -> list[str]:
    target = str(record.get("target", ""))
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(run_url)
    artifact_name = str(source.get("artifact_name", "")).strip()
    release_tag = str(record.get("release_tag", "")).strip()
    expected_head_sha = str(source.get("head_sha", "")).strip()
    expected_run_attempt = source.get("run_attempt")
    expected_workflow = release_source_workflow(target)
    workflow = str(source.get("workflow", "")).strip()
    if not run_match:
        return [f"{target} release_asset_source.workflow_run_url must be a GitHub Actions run URL"]
    if workflow != expected_workflow:
        return [f"{target} release_asset_source.workflow must be {expected_workflow}"]
    if not artifact_name:
        return [f"{target} release_asset_source.artifact_name must be set"]
    if not release_tag:
        return [f"{target} release_tag must be set"]
    expected_artifact_name = expected_release_source_artifact_name(target, release_tag)
    if not expected_artifact_name:
        return [f"{target} is not a protected platform evidence target"]
    if artifact_name != expected_artifact_name:
        return [f"{target} release_asset_source.artifact_name must be {expected_artifact_name}"]
    url_errors = check_import_release_url_tags(record, release_tag)
    if url_errors:
        return url_errors
    if not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(expected_head_sha):
        return [f"{target} release_asset_source.head_sha must be a 40-character lowercase Git SHA"]
    if (
        not isinstance(expected_run_attempt, int)
        or isinstance(expected_run_attempt, bool)
        or expected_run_attempt < 1
    ):
        return [f"{target} release_asset_source.run_attempt must be a positive integer"]
    checkout_errors = check_release_checkout_head_sha(
        target,
        expected_head_sha=expected_head_sha,
        release_head_sha=release_head_sha,
    )
    if checkout_errors:
        return checkout_errors
    repository = run_match.group(1)
    release_repositories = release_repositories_for_import_record(record)
    if not release_repositories:
        return [f"{target} release asset import must have GitHub release asset URLs"]
    if release_repositories != {repository}:
        return [
            f"{target} release_asset_source.workflow_run_url repository must match "
            f"release asset repositories {sorted(release_repositories)}, got {repository}"
        ]
    run_id = run_url.rstrip("/").rsplit("/", 1)[-1]
    destination = download_root / target
    metadata_command = source_run_attempt_metadata_command(
        run_id,
        repository,
        expected_run_attempt,
    )
    artifacts_command = source_run_artifacts_command(run_id, repository)
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
        declared_file_errors = check_release_source_declared_files_for_record(record)
        if declared_file_errors:
            return declared_file_errors
        print(" ".join(metadata_command))
        print(" ".join(artifacts_command))
        print(" ".join(command))
        if verify_source_run_metadata:
            errors = verify_source_run(
                target,
                metadata_command,
                expected_run_id=run_id,
                expected_workflow_run_url=run_url,
                expected_head_sha=expected_head_sha,
                expected_run_attempt=expected_run_attempt,
                release_head_sha=release_head_sha,
            )
            if errors:
                return errors
            return verify_source_artifact(
                target,
                artifacts_command,
                artifact_name=artifact_name,
                expected_repository=repository,
                expected_run_id=run_id,
                expected_head_sha=expected_head_sha,
            )
    else:
        errors = verify_source_run(
            target,
            metadata_command,
            expected_run_id=run_id,
            expected_workflow_run_url=run_url,
            expected_head_sha=expected_head_sha,
            expected_run_attempt=expected_run_attempt,
            release_head_sha=release_head_sha,
        )
        if errors:
            return errors
        errors = verify_source_artifact(
            target,
            artifacts_command,
            artifact_name=artifact_name,
            expected_repository=repository,
            expected_run_id=run_id,
            expected_head_sha=expected_head_sha,
        )
        if errors:
            return errors
        declared_file_errors = check_release_source_declared_files_for_record(record)
        if declared_file_errors:
            return declared_file_errors
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


def check_import_release_url_tags(record: dict[str, Any], release_tag: str) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    for label, url in import_release_asset_urls(record):
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(url)
        if not match:
            errors.append(f"{target} {label} must be a GitHub release asset URL: {url}")
            continue
        if match.group(2) != release_tag:
            errors.append(f"{target} {label} tag must match release_tag {release_tag}: {url}")
    return errors


def import_release_asset_urls(record: dict[str, Any]) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    raw_release_urls = record.get("release_asset_urls")
    if isinstance(raw_release_urls, list):
        urls.extend(("release_asset_urls", str(url)) for url in raw_release_urls)
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        raw_bundle_urls = review_bundle.get("release_asset_urls")
        if isinstance(raw_bundle_urls, list):
            urls.extend(("review_bundle release_asset_urls", str(url)) for url in raw_bundle_urls)
    finalized_url = record.get("finalized_record_release_asset_url")
    if isinstance(finalized_url, str):
        urls.append(("finalized_record_release_asset_url", finalized_url))
    return urls


def expected_release_source_artifact_name(target: str, release_tag: str) -> str:
    if target.startswith("linux-"):
        return linux_release_source_artifact_name(target, release_tag)
    if target.startswith("windows-xp-native-"):
        return xp_release_source_artifact_name(target, release_tag)
    return ""


def release_repositories_for_import_record(record: dict[str, Any]) -> set[str]:
    repositories = release_asset_repositories(record.get("release_asset_urls"))
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        repositories.update(release_asset_repositories(review_bundle.get("release_asset_urls")))
    finalized_url = record.get("finalized_record_release_asset_url")
    if isinstance(finalized_url, str):
        repositories.update(release_asset_repositories([finalized_url]))
    return repositories


def source_run_attempt_metadata_command(
    run_id: str,
    repository: str,
    run_attempt: int,
) -> list[str]:
    return [
        "gh",
        "api",
        f"repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}",
        "--jq",
        SOURCE_RUN_METADATA_JQ,
    ]


def source_run_artifacts_command(run_id: str, repository: str) -> list[str]:
    return [
        "gh",
        "api",
        f"repos/{repository}/actions/runs/{run_id}/artifacts?per_page={SOURCE_RUN_ARTIFACTS_PAGE_SIZE}",
    ]


def verify_source_run(
    target: str,
    command: list[str],
    *,
    expected_run_id: str,
    expected_workflow_run_url: str,
    expected_head_sha: str,
    expected_run_attempt: int,
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
    if str(data.get("id", "")) != expected_run_id:
        errors.append(
            f"{target} release_asset_source workflow run id must match accepted record "
            f"{expected_run_id}, got {data.get('id')!r}"
        )
    if str(data.get("htmlUrl", "")).rstrip("/") != expected_workflow_run_url.rstrip("/"):
        errors.append(
            f"{target} release_asset_source workflow run htmlUrl must match accepted record "
            f"{expected_workflow_run_url}, got {data.get('htmlUrl')!r}"
        )
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
    expected_workflow = release_source_workflow(target)
    if data.get("path") != expected_workflow:
        errors.append(
            f"{target} release_asset_source workflow run path must be {expected_workflow!r}, "
            f"got {data.get('path')!r}"
        )
    if data.get("headSha") != expected_head_sha:
        errors.append(
            f"{target} release_asset_source workflow run headSha must match accepted record "
            f"{expected_head_sha}, got {data.get('headSha')!r}"
        )
    if data.get("attempt") != expected_run_attempt:
        errors.append(
            f"{target} release_asset_source workflow run attempt must match accepted record "
            f"{expected_run_attempt}, got {data.get('attempt')!r}"
        )
    errors.extend(
        check_release_checkout_head_sha(
            target,
            expected_head_sha=expected_head_sha,
            release_head_sha=release_head_sha,
        )
    )
    return errors


def verify_source_artifact(
    target: str,
    command: list[str],
    *,
    artifact_name: str,
    expected_repository: str,
    expected_run_id: str,
    expected_head_sha: str,
) -> list[str]:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return [f"{target} failed to inspect release_asset_source artifacts: {exc}"]
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return [f"{target} release_asset_source artifact metadata is not JSON: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} release_asset_source artifact metadata must be a JSON object"]
    raw_artifacts = data.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return [f"{target} release_asset_source artifact metadata must include artifacts list"]
    total_count = data.get("total_count")
    if (
        not isinstance(total_count, int)
        or isinstance(total_count, bool)
        or total_count != len(raw_artifacts)
    ):
        return [
            f"{target} release_asset_source artifact metadata total_count must match "
            f"the complete artifacts list length, got {total_count!r} for {len(raw_artifacts)} artifacts"
        ]
    matches = [
        artifact
        for artifact in raw_artifacts
        if isinstance(artifact, dict) and artifact.get("name") == artifact_name
    ]
    if len(matches) != 1:
        return [
            f"{target} release_asset_source artifact list must contain exactly one "
            f"{artifact_name!r}, got {len(matches)}"
        ]
    artifact = matches[0]
    errors: list[str] = []
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} id must be a positive integer, "
            f"got {artifact_id!r}"
        )
    else:
        expected_archive_url = (
            f"https://api.github.com/repos/{expected_repository}/actions/artifacts/{artifact_id}/zip"
        )
        if artifact.get("archive_download_url") != expected_archive_url:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} archive_download_url "
                f"must be {expected_archive_url!r}, got {artifact.get('archive_download_url')!r}"
            )
    if artifact.get("expired") is not False:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} must not be expired, "
            f"got {artifact.get('expired')!r}"
        )
    size = artifact.get("size_in_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} size_in_bytes must be positive, "
            f"got {size!r}"
        )
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} workflow_run must be an object"
        )
    else:
        artifact_run_id = workflow_run.get("id")
        if str(artifact_run_id) != expected_run_id:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.id must match "
                f"run {expected_run_id}, got {artifact_run_id!r}"
            )
        artifact_head_sha = str(workflow_run.get("head_sha", "")).strip()
        if artifact_head_sha != expected_head_sha:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.head_sha must match "
                f"accepted record {expected_head_sha}, got {artifact_head_sha!r}"
            )
    return errors


def check_release_checkout_head_sha(
    target: str,
    *,
    expected_head_sha: str,
    release_head_sha: str | None,
) -> list[str]:
    if release_head_sha is not None and expected_head_sha != release_head_sha:
        return [
            f"{target} release_asset_source.head_sha must match release checkout {release_head_sha}, "
            f"got {expected_head_sha}"
        ]
    return []


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
    unsafe_files = sorted(filename for filename in expected_files if not exact_safe_file_name(filename))
    if unsafe_files:
        return [f"{target} release asset import expected files must be exact safe file names: {unsafe_files}"]
    if source_root.is_symlink():
        errors.append(f"{target} downloaded artifact directory must not be a symlink: {source_root}")
    else:
        errors.extend(check_path_parent_symlinks(source_root, f"{target} downloaded artifact directory"))
    if not source_root.is_dir():
        errors.append(f"{target} downloaded artifact directory missing: {source_root}")
    for filename in sorted(expected_files):
        source = source_root / filename
        if source.is_symlink():
            errors.append(f"{target} release asset import source must not be a symlink: {filename}")
        elif not source.is_file():
            errors.append(f"{target} downloaded artifact missing expected release file: {filename}")
    errors.extend(ensure_output_directory(out_dir))
    if errors:
        return errors
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename in sorted(expected_files):
        source = source_root / filename
        destination = out_dir / filename
        if destination.is_symlink():
            errors.append(f"{target} release asset import destination must not be a symlink: {filename}")
            continue
        if destination.exists() and not destination.is_file():
            errors.append(f"{target} release asset import destination must be a regular file: {filename}")
            continue
        if destination.exists() and sha256_file(destination) != sha256_file(source):
            errors.append(f"{target} release asset import would overwrite different file: {filename}")
            continue
        shutil.copy2(source, destination)
    return errors


def validate_source_artifact(record: dict[str, Any], *, source_root: Path) -> list[str]:
    target = str(record.get("target", ""))
    source_errors, expected_files = release_source_contains_files(record)
    if source_errors:
        return source_errors
    declared_errors = check_release_source_declared_files_for_record(record)
    if declared_errors:
        return declared_errors
    errors = validate_downloaded_source_file_set(
        target,
        source_root=source_root,
        expected_files=expected_files,
    )
    if errors:
        return errors
    errors = check_downloaded_source_hashes(record, source_root=source_root)
    if errors:
        return errors
    return validate_downloaded_final_record(record, source_root=source_root)


def check_release_source_declared_files_for_record(record: dict[str, Any]) -> list[str]:
    target = str(record.get("target", ""))
    source_errors, declared_files = release_source_contains_files(record)
    if source_errors:
        return source_errors
    return check_release_source_declared_files(
        target,
        declared_files=declared_files,
        expected_files=expected_release_files(record),
    )


def check_release_source_declared_files(
    target: str,
    *,
    declared_files: set[str],
    expected_files: set[str],
) -> list[str]:
    errors: list[str] = []
    missing = sorted(expected_files - declared_files)
    if missing:
        errors.append(f"{target} release_asset_source.contains_files missing expected files: {missing}")
    unexpected = sorted(declared_files - expected_files)
    if unexpected:
        errors.append(f"{target} release_asset_source.contains_files has unexpected files: {unexpected}")
    return errors


def validate_downloaded_source_file_set(
    target: str,
    *,
    source_root: Path,
    expected_files: set[str],
) -> list[str]:
    if source_root.is_symlink():
        return [f"{target} downloaded artifact directory must not be a symlink: {source_root}"]
    parent_errors = check_path_parent_symlinks(source_root, f"{target} downloaded artifact directory")
    if parent_errors:
        return parent_errors
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


def check_downloaded_source_hashes(record: dict[str, Any], *, source_root: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for filename, digest in sorted(artifact_hashes.items()):
            path = source_root / str(filename)
            if not path.is_file():
                errors.append(f"{target} downloaded source artifact missing native artifact: {filename}")
                continue
            if sha256_file(path) != str(digest):
                errors.append(f"{target} downloaded source artifact native artifact SHA-256 mismatch: {filename}")
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = str(bundle_record.get("file", ""))
            path = source_root / filename
            if not path.is_file():
                errors.append(f"{target} downloaded source artifact missing review bundle {key}: {filename}")
                continue
            if bundle_record.get("size_bytes") != path.stat().st_size:
                errors.append(
                    f"{target} downloaded source artifact review bundle {key} size_bytes mismatch: {filename}"
                )
            if sha256_file(path) != str(bundle_record.get("sha256", "")):
                errors.append(
                    f"{target} downloaded source artifact review bundle {key} SHA-256 mismatch: {filename}"
                )
    return errors


def check_imported_hashes(record: dict[str, Any], *, out_dir: Path) -> list[str]:
    target = str(record.get("target", ""))
    errors: list[str] = []
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for filename, digest in sorted(artifact_hashes.items()):
            path = out_dir / str(filename)
            if not path.is_file():
                errors.append(f"{target} imported native artifact missing: {filename}")
                continue
            if sha256_file(path) != str(digest):
                errors.append(f"{target} imported native artifact SHA-256 mismatch: {filename}")
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = str(bundle_record.get("file", ""))
            path = out_dir / filename
            if not path.is_file():
                errors.append(f"{target} imported review bundle {key} missing: {filename}")
                continue
            if bundle_record.get("size_bytes") != path.stat().st_size:
                errors.append(f"{target} imported review bundle {key} size_bytes mismatch: {filename}")
            if sha256_file(path) != str(bundle_record.get("sha256", "")):
                errors.append(f"{target} imported review bundle {key} SHA-256 mismatch: {filename}")
    return errors


def check_imported_review_bundle(record: dict[str, Any], *, out_dir: Path) -> list[str]:
    registry = read_json(EVIDENCE_PATH)
    target = str(record.get("target", "")).strip()
    release_tag = str(record.get("release_tag", "")).strip()
    errors = check_platform_review_bundle_artifacts(
        registry={**registry, "accepted_evidence": [public_record(record)]},
        bundle_dir=out_dir,
        required_targets=(target,) if target else None,
        required_release_tag=release_tag or None,
        require_final_record_assets=True,
    )
    return [f"{target} imported review bundle validation failed: {error}" for error in errors]


def expected_release_files(record: dict[str, Any]) -> set[str]:
    files: set[str] = set()
    target = str(record.get("target", ""))
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
    if target in PROTECTED_GOAL_TARGETS:
        files.add(accepted_record_source_file(target))
    return files


def expected_source_files(record: dict[str, Any]) -> set[str]:
    errors, files = release_source_contains_files(record)
    if errors:
        return set()
    return files


def release_source_contains_files(record: dict[str, Any]) -> tuple[list[str], set[str]]:
    target = str(record.get("target", ""))
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"], set()
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        return [f"{target} release_asset_source.contains_files must be a non-empty list"], set()
    files = [str(name) for name in raw_files]
    unsafe = sorted({name for name in files if not exact_safe_file_name(name)})
    errors: list[str] = []
    if unsafe:
        errors.append(f"{target} release_asset_source.contains_files entries must be exact safe file names: {unsafe}")
    duplicates = sorted({name for name in files if files.count(name) > 1})
    if duplicates:
        errors.append(f"{target} release_asset_source.contains_files contains duplicates: {duplicates}")
    return errors, set(files)


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


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
