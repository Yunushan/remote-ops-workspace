from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
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
    GITHUB_ACTIONS_RUN_RE,
    GITHUB_RELEASE_ASSET_RE,
    GITHUB_REPOSITORY_RE,
    PROTECTED_GOAL_TARGETS,
    RELEASE_SOURCE_HEAD_SHA_RE,
    RESERVED_WORKSPACE_ROOTS,
    accepted_record_source_file,
    case_insensitive_name_collisions,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    exact_safe_file_name,
    linux_release_source_artifact_name,
    read_json,
    release_asset_repositories,
    release_asset_url_filename,
    release_source_workflow,
    xp_release_source_artifact_name,
)
from make_platform_verified_evidence_record import sha256_file  # noqa: E402

SOURCE_RUN_METADATA_JQ = (
    "{id: .id, nodeId: .node_id, url: .url, htmlUrl: .html_url, "
    "runNumber: .run_number, workflowId: .workflow_id, workflowUrl: .workflow_url, "
    "jobsUrl: .jobs_url, logsUrl: .logs_url, artifactsUrl: .artifacts_url, "
    "checkSuiteId: .check_suite_id, checkSuiteUrl: .check_suite_url, "
    "attempt: .run_attempt, status: .status, "
    "conclusion: .conclusion, event: .event, headSha: .head_sha, "
    "headBranch: .head_branch, path: .path, "
    "runCreatedAt: .created_at, "
    "runStartedAt: .run_started_at, "
    "runUpdatedAt: .updated_at, "
    "repositoryFullName: .repository.full_name, "
    "headRepositoryFullName: .head_repository.full_name, "
    "repositoryId: .repository.id, "
    "headRepositoryId: .head_repository.id}"
)
SOURCE_RUN_ARTIFACTS_PAGE_SIZE = 100
REQUIRE_VERIFY_SOURCE_RUN_DRY_RUN_ERROR = (
    "--dry-run for protected platform evidence imports requires --verify-source-run"
)
SHA256_HEX_CHARS = set("0123456789abcdef")


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
        repository=args.repository,
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
            "required for protected-platform evidence import dry-runs"
        ),
    )
    parser.add_argument(
        "--repository",
        help=(
            "expected GitHub owner/name repository for accepted release asset URLs "
            "and recorded source workflow runs"
        ),
    )
    return parser.parse_args(argv)


def strict_import_arg_errors(args: argparse.Namespace) -> list[str]:
    errors = check_registry_path(args.registry)
    out_dir_errors, _out_dir = path_arg_value(
        getattr(args, "out_dir", None),
        "release asset import output directory",
    )
    errors.extend(out_dir_errors)
    repository_errors, _repository = normalize_expected_repository(
        getattr(args, "repository", None)
    )
    errors.extend(repository_errors)
    requested_targets, target_errors = required_target_values(args.require_target)
    errors.extend(target_errors)
    if not args.dry_run or args.verify_source_run:
        return errors
    protected_targets = set(PROTECTED_GOAL_TARGETS)
    is_protected_import = (
        args.require_goal_targets
        or not requested_targets
        or bool(requested_targets & protected_targets)
    )
    if is_protected_import:
        errors.append(REQUIRE_VERIFY_SOURCE_RUN_DRY_RUN_ERROR)
    return errors


def normalize_expected_repository(repository: object) -> tuple[list[str], str | None]:
    if repository is None:
        return [], None
    if not isinstance(repository, str):
        return [
            f"platform evidence import repository must be a string owner/name value, got {repository!r}"
        ], None
    normalized = repository.strip().strip("/")
    if not normalized:
        return ["platform evidence import repository must be a non-empty owner/name value"], None
    if not re.fullmatch(GITHUB_REPOSITORY_RE, normalized):
        return [
            f"platform evidence import repository must be a GitHub owner/name value, got {repository!r}"
        ], None
    return [], normalized


def required_target_values(raw_targets: object) -> tuple[set[str], list[str]]:
    if raw_targets is None:
        return set(), []
    if isinstance(raw_targets, str):
        raw_targets = (raw_targets,)
    try:
        target_values = iter(raw_targets)
    except TypeError:
        return set(), [f"platform evidence import required targets must be iterable, got {raw_targets!r}"]
    targets: set[str] = set()
    errors: list[str] = []
    for target in target_values:
        if not isinstance(target, str) or not target.strip():
            errors.append(f"platform evidence import required target must be a non-empty string, got {target!r}")
            continue
        targets.add(target.strip())
    return targets, errors


def check_registry_path(path: object) -> list[str]:
    path_errors, registry_path = path_arg_value(path, "accepted evidence registry")
    if path_errors:
        return path_errors
    assert registry_path is not None
    errors = check_path_not_reserved_workspace_root(registry_path, "accepted evidence registry")
    if errors:
        return errors
    if registry_path.is_symlink():
        return [f"accepted evidence registry must not be a symlink: {registry_path}"]
    return check_path_parent_symlinks(registry_path, "accepted evidence registry")


def required_targets_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    targets, _errors = required_target_values(args.require_target)
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
        and accepted_import_target(row) in target_set
    ]


def import_platform_evidence_artifacts(
    records: list[dict[str, Any]],
    *,
    out_dir: object,
    dry_run: bool = False,
    verify_source_run_metadata: bool = False,
    release_head_sha: str | None = None,
    repository: object = None,
) -> list[str]:
    errors: list[str] = []
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    errors.extend(out_dir_errors)
    repository_errors, expected_repository = normalize_expected_repository(repository)
    errors.extend(repository_errors)
    if errors:
        return errors
    assert out_dir_path is not None
    errors.extend(check_import_record_targets_unique(records))
    if errors:
        return errors
    errors.extend(check_public_record_keys(records))
    if errors:
        return errors
    errors.extend(check_import_release_file_names(records))
    errors.extend(ensure_output_directory(out_dir_path))
    if records and not dry_run:
        errors.extend(check_output_directory_empty(out_dir_path))
    if errors:
        return errors
    if records and (not dry_run or verify_source_run_metadata):
        errors.extend(check_github_cli_available())
    if errors:
        return errors
    out_dir_path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="platform-evidence-import-") as tmp:
        download_root = Path(tmp)
        for record in records:
            errors.extend(
                import_record(
                    record,
                    out_dir=out_dir_path,
                    download_root=download_root,
                    dry_run=dry_run,
                    verify_source_run_metadata=verify_source_run_metadata,
                    release_head_sha=release_head_sha,
                    repository=expected_repository,
                )
            )
    return errors


def check_import_record_targets_unique(records: list[dict[str, Any]]) -> list[str]:
    target_counts: dict[str, int] = {}
    errors: list[str] = []
    for record in records:
        target = accepted_import_target(record)
        if not target:
            errors.append(
                "release asset import accepted record target must be a non-empty string, "
                f"got {record.get('target', '')!r}"
            )
            continue
        target_counts[target] = target_counts.get(target, 0) + 1
    duplicates = sorted(target for target, count in target_counts.items() if count > 1)
    if duplicates:
        errors.append(
            f"release asset import accepted records must target each platform once: {', '.join(duplicates)}"
        )
    return errors


def check_public_record_keys(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for record in records:
        errors.extend(public_record_key_errors(record))
    return errors


def public_record_key_errors(record: dict[str, Any]) -> list[str]:
    target = import_record_target_label(record)
    errors: list[str] = []
    public_keys: set[str] = set()
    for key in record:
        if not isinstance(key, str):
            errors.append(f"{target} accepted evidence public record keys must be strings, got {key!r}")
            continue
        if not key.startswith("_"):
            public_keys.add(key)
    case_collisions = case_insensitive_name_collisions(public_keys)
    if case_collisions:
        errors.append(
            f"{target} accepted evidence public record keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return errors


def check_import_release_file_names(records: list[dict[str, Any]]) -> list[str]:
    labels: list[tuple[str, str]] = []
    errors: list[str] = []
    for record in records:
        target = import_record_target_label(record)
        file_errors, filenames = expected_release_file_name_entries(record)
        errors.extend(file_errors)
        labels.extend((target, filename) for filename in filenames)
    unsafe = sorted(
        {
            f"{target}:{filename}"
            for target, filename in labels
            if not exact_safe_file_name(filename)
        }
    )
    if unsafe:
        errors.append(f"release asset import expected output file names must be exact safe file names: {unsafe}")
    counts: dict[str, int] = {}
    for _target, filename in labels:
        counts[filename] = counts.get(filename, 0) + 1
    duplicate_names = sorted(filename for filename, count in counts.items() if count > 1)
    if duplicate_names:
        errors.append(
            "release asset import expected output file names must be unique across accepted records: "
            f"{duplicate_names}"
        )
    case_groups: dict[str, set[str]] = {}
    for _target, filename in labels:
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
            "release asset import expected output file names must not collide on case-insensitive filesystems: "
            f"{case_collisions}"
        )
    return errors


def ensure_output_directory(out_dir: object) -> list[str]:
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    if out_dir_errors:
        return out_dir_errors
    assert out_dir_path is not None
    hint_errors = check_directory_path_hint(out_dir_path, "release asset import output directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(
        out_dir_path,
        "release asset import output directory",
    )
    if reserved_errors:
        return reserved_errors
    if out_dir_path.is_symlink():
        return [f"release asset import output directory must not be a symlink: {out_dir_path}"]
    parent_errors = check_path_parent_symlinks(out_dir_path, "release asset import output directory")
    if parent_errors:
        return parent_errors
    if out_dir_path.exists() and not out_dir_path.is_dir():
        return [f"release asset import output path must be a directory: {out_dir_path}"]
    return []


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def check_output_directory_empty(out_dir: object) -> list[str]:
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    if out_dir_errors:
        return out_dir_errors
    assert out_dir_path is not None
    if not out_dir_path.exists():
        return []
    entries = sorted(path.name for path in out_dir_path.iterdir())
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


def import_record(
    record: dict[str, Any],
    *,
    out_dir: object,
    download_root: object,
    dry_run: bool,
    verify_source_run_metadata: bool = False,
    release_head_sha: str | None = None,
    repository: object = None,
) -> list[str]:
    target = import_record_target_label(record)
    path_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    download_root_errors, download_root_path = path_arg_value(
        download_root,
        f"{target} release asset import download root",
    )
    path_errors.extend(download_root_errors)
    repository_errors, expected_repository = normalize_expected_repository(repository)
    path_errors.extend(repository_errors)
    if path_errors:
        return path_errors
    assert out_dir_path is not None
    assert download_root_path is not None
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    field_errors: list[str] = []
    raw_run_url = source.get("workflow_run_url", "")
    if isinstance(raw_run_url, str):
        run_url = raw_run_url.rstrip("/")
        if raw_run_url != run_url or raw_run_url != raw_run_url.strip():
            field_errors.append(
                f"{target} release_asset_source.workflow_run_url must be canonical without "
                "surrounding whitespace or trailing slash"
            )
    else:
        run_url = ""
        field_errors.append(
            f"{target} release_asset_source.workflow_run_url must be a string, got {raw_run_url!r}"
        )
    raw_artifact_name = source.get("artifact_name", "")
    if isinstance(raw_artifact_name, str):
        artifact_name = raw_artifact_name.strip()
        if raw_artifact_name != artifact_name:
            field_errors.append(
                f"{target} release_asset_source.artifact_name must not include surrounding whitespace"
            )
    else:
        artifact_name = ""
        field_errors.append(
            f"{target} release_asset_source.artifact_name must be a string, got {raw_artifact_name!r}"
        )
    raw_release_tag = record.get("release_tag", "")
    if isinstance(raw_release_tag, str):
        release_tag = raw_release_tag.strip()
        if raw_release_tag != release_tag:
            field_errors.append(f"{target} release_tag must not include surrounding whitespace")
    else:
        release_tag = ""
        field_errors.append(f"{target} release_tag must be a string, got {raw_release_tag!r}")
    raw_head_sha = source.get("head_sha", "")
    if isinstance(raw_head_sha, str):
        expected_head_sha = raw_head_sha.strip()
        if raw_head_sha != expected_head_sha:
            field_errors.append(
                f"{target} release_asset_source.head_sha must not include surrounding whitespace"
            )
    else:
        expected_head_sha = ""
        field_errors.append(
            f"{target} release_asset_source.head_sha must be a string, got {raw_head_sha!r}"
        )
    expected_workflow = release_source_workflow(target)
    raw_workflow = source.get("workflow", "")
    if isinstance(raw_workflow, str):
        workflow = raw_workflow.strip()
        if raw_workflow != workflow:
            field_errors.append(
                f"{target} release_asset_source.workflow must not include surrounding whitespace"
            )
    else:
        workflow = ""
        field_errors.append(
            f"{target} release_asset_source.workflow must be a string, got {raw_workflow!r}"
        )
    if field_errors:
        return field_errors
    run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(run_url)
    expected_run_attempt = source.get("run_attempt")
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
    url_errors = check_import_release_url_tags(
        record,
        release_tag,
        repository=expected_repository,
    )
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
    source_repository = run_match.group(1)
    if expected_repository is not None and source_repository != expected_repository:
        return [
            f"{target} release_asset_source.workflow_run_url repository must match "
            f"release repository {expected_repository}, got {source_repository}"
        ]
    release_repositories = release_repositories_for_import_record(record)
    if not release_repositories:
        return [f"{target} release asset import must have GitHub release asset URLs"]
    if release_repositories != {source_repository}:
        return [
            f"{target} release_asset_source.workflow_run_url repository must match "
            f"release asset repositories {sorted(release_repositories)}, got {source_repository}"
        ]
    run_id = run_url.rstrip("/").rsplit("/", 1)[-1]
    destination = download_root_path / target
    metadata_command = source_run_attempt_metadata_command(
        run_id,
        source_repository,
        expected_run_attempt,
    )
    artifacts_command = source_run_artifacts_command(run_id, source_repository)
    command = [
        "gh",
        "run",
        "download",
        run_id,
        "--repo",
        source_repository,
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
            source_run_observed: dict[str, Any] = {}
            errors = verify_source_run(
                target,
                metadata_command,
                expected_run_id=run_id,
                expected_workflow_run_url=run_url,
                expected_release_tag=release_tag,
                expected_head_sha=expected_head_sha,
                expected_run_attempt=expected_run_attempt,
                release_head_sha=release_head_sha,
                observed_source_run=source_run_observed,
            )
            if errors:
                return errors
            return verify_source_artifact(
                target,
                artifacts_command,
                artifact_name=artifact_name,
                expected_repository=source_repository,
                expected_run_id=run_id,
                expected_head_sha=expected_head_sha,
                expected_repository_id=source_run_observed.get("repository_id"),
                expected_head_repository_id=source_run_observed.get("head_repository_id"),
                expected_run_created_at=source_run_observed.get("run_created_at"),
                expected_run_started_at=source_run_observed.get("run_started_at"),
                expected_run_updated_at=source_run_observed.get("run_updated_at"),
            )
    else:
        source_run_observed: dict[str, Any] = {}
        errors = verify_source_run(
            target,
            metadata_command,
            expected_run_id=run_id,
            expected_workflow_run_url=run_url,
            expected_release_tag=release_tag,
            expected_head_sha=expected_head_sha,
            expected_run_attempt=expected_run_attempt,
            release_head_sha=release_head_sha,
            observed_source_run=source_run_observed,
        )
        if errors:
            return errors
        errors = verify_source_artifact(
            target,
            artifacts_command,
            artifact_name=artifact_name,
            expected_repository=source_repository,
            expected_run_id=run_id,
            expected_head_sha=expected_head_sha,
            expected_repository_id=source_run_observed.get("repository_id"),
            expected_head_repository_id=source_run_observed.get("head_repository_id"),
            expected_run_created_at=source_run_observed.get("run_created_at"),
            expected_run_started_at=source_run_observed.get("run_started_at"),
            expected_run_updated_at=source_run_observed.get("run_updated_at"),
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
    errors = copy_expected_files(record, source_root=destination, out_dir=out_dir_path)
    if not errors:
        errors.extend(check_imported_hashes(record, out_dir=out_dir_path))
    if not errors:
        errors.extend(check_imported_review_bundle(record, out_dir=out_dir_path))
    return errors


def check_import_release_url_tags(
    record: dict[str, Any],
    release_tag: str,
    *,
    repository: str | None = None,
) -> list[str]:
    target = import_record_target_label(record)
    errors: list[str] = []
    urls, url_shape_errors = import_release_asset_urls(record)
    errors.extend(f"{target} {error}" for error in url_shape_errors)
    for label, url in urls:
        if not isinstance(url, str):
            errors.append(f"{target} {label} entries must be strings, got {url!r}")
            continue
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(url)
        if not match:
            errors.append(f"{target} {label} must be a GitHub release asset URL: {url}")
            continue
        if repository is not None and match.group(1) != repository:
            errors.append(
                f"{target} {label} repository must match release repository {repository}: {url}"
            )
            continue
        if match.group(2) != release_tag:
            errors.append(f"{target} {label} tag must match release_tag {release_tag}: {url}")
            continue
        if not release_asset_url_filename(url):
            errors.append(f"{target} {label} file name must be an exact safe file name: {url}")
    return errors


def import_release_asset_urls(record: dict[str, Any]) -> tuple[list[tuple[str, Any]], list[str]]:
    urls: list[tuple[str, Any]] = []
    errors: list[str] = []
    raw_release_urls = record.get("release_asset_urls")
    if isinstance(raw_release_urls, list):
        urls.extend(("release_asset_urls", url) for url in raw_release_urls)
    elif raw_release_urls is not None:
        errors.append(f"release_asset_urls must be a list, got {raw_release_urls!r}")
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        raw_bundle_urls = review_bundle.get("release_asset_urls")
        if isinstance(raw_bundle_urls, list):
            urls.extend(("review_bundle release_asset_urls", url) for url in raw_bundle_urls)
        elif raw_bundle_urls is not None:
            errors.append(f"review_bundle release_asset_urls must be a list, got {raw_bundle_urls!r}")
    finalized_url = record.get("finalized_record_release_asset_url")
    if isinstance(finalized_url, str):
        urls.append(("finalized_record_release_asset_url", finalized_url))
    elif finalized_url is not None:
        errors.append(f"finalized_record_release_asset_url must be a string, got {finalized_url!r}")
    return urls, errors


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


def source_run_api_url(repository: str, run_id: str | int) -> str:
    return f"https://api.github.com/repos/{repository}/actions/runs/{run_id}"


def source_run_child_api_url(repository: str, run_id: str | int, endpoint: str) -> str:
    return f"{source_run_api_url(repository, run_id)}/{endpoint}"


def source_workflow_api_url(repository: str, workflow_id: str | int) -> str:
    return f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_id}"


def check_suite_api_url(repository: str, check_suite_id: str | int) -> str:
    return f"https://api.github.com/repos/{repository}/check-suites/{check_suite_id}"


def source_artifact_api_url(repository: str, artifact_id: str | int) -> str:
    return f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"


def verify_source_run(
    target: str,
    command: list[str],
    *,
    expected_run_id: str,
    expected_workflow_run_url: str,
    expected_release_tag: str,
    expected_head_sha: str,
    expected_run_attempt: int,
    release_head_sha: str | None = None,
    observed_source_run: dict[str, Any] | None = None,
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
    expected_run_id_int = int(expected_run_id) if expected_run_id.isdecimal() else None
    run_id = positive_int_value(data.get("id"))
    if run_id is None:
        errors.append(
            f"{target} release_asset_source workflow run id must be a positive integer, "
            f"got {data.get('id')!r}"
        )
    elif expected_run_id_int is not None and run_id != expected_run_id_int:
        errors.append(
            f"{target} release_asset_source workflow run id must match accepted record "
            f"{expected_run_id}, got {run_id!r}"
        )
    html_url = data.get("htmlUrl", "")
    if not isinstance(html_url, str):
        errors.append(
            f"{target} release_asset_source workflow run htmlUrl must be a string, "
            f"got {html_url!r}"
        )
    elif html_url != expected_workflow_run_url:
        errors.append(
            f"{target} release_asset_source workflow run htmlUrl must match accepted record "
            f"{expected_workflow_run_url}, got {html_url!r}"
        )
    expected_repository = repository_from_workflow_run_url(expected_workflow_run_url)
    if expected_run_id_int is not None:
        expected_api_url = source_run_api_url(expected_repository, expected_run_id_int)
        if data.get("url") != expected_api_url:
            errors.append(
                f"{target} release_asset_source workflow run url must be {expected_api_url!r}, "
                f"got {data.get('url')!r}"
            )
    node_id = data.get("nodeId")
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
        errors.append(
            f"{target} release_asset_source workflow run nodeId must be a non-empty string, "
            f"got {node_id!r}"
        )
    run_number = positive_int_value(data.get("runNumber"))
    if run_number is None:
        errors.append(
            f"{target} release_asset_source workflow run runNumber must be a positive integer, "
            f"got {data.get('runNumber')!r}"
        )
    workflow_id = positive_int_value(data.get("workflowId"))
    if workflow_id is None:
        errors.append(
            f"{target} release_asset_source workflow run workflowId must be a positive integer, "
            f"got {data.get('workflowId')!r}"
        )
    else:
        expected_workflow_url = source_workflow_api_url(expected_repository, workflow_id)
        if data.get("workflowUrl") != expected_workflow_url:
            errors.append(
                f"{target} release_asset_source workflow run workflowUrl must be "
                f"{expected_workflow_url!r}, got {data.get('workflowUrl')!r}"
            )
    if expected_run_id_int is not None:
        for field, endpoint in (
            ("jobsUrl", "jobs"),
            ("logsUrl", "logs"),
            ("artifactsUrl", "artifacts"),
        ):
            expected_endpoint_url = source_run_child_api_url(
                expected_repository,
                expected_run_id_int,
                endpoint,
            )
            if data.get(field) != expected_endpoint_url:
                errors.append(
                    f"{target} release_asset_source workflow run {field} must be "
                    f"{expected_endpoint_url!r}, got {data.get(field)!r}"
                )
    check_suite_id = positive_int_value(data.get("checkSuiteId"))
    if check_suite_id is None:
        errors.append(
            f"{target} release_asset_source workflow run checkSuiteId must be a positive integer, "
            f"got {data.get('checkSuiteId')!r}"
        )
    else:
        expected_check_suite_url = check_suite_api_url(expected_repository, check_suite_id)
        if data.get("checkSuiteUrl") != expected_check_suite_url:
            errors.append(
                f"{target} release_asset_source workflow run checkSuiteUrl must be "
                f"{expected_check_suite_url!r}, got {data.get('checkSuiteUrl')!r}"
            )
    if data.get("repositoryFullName") != expected_repository:
        errors.append(
            f"{target} release_asset_source workflow run repositoryFullName must match accepted record "
            f"{expected_repository}, got {data.get('repositoryFullName')!r}"
        )
    if data.get("headRepositoryFullName") != expected_repository:
        errors.append(
            f"{target} release_asset_source workflow run headRepositoryFullName must match accepted record "
            f"{expected_repository}, got {data.get('headRepositoryFullName')!r}"
        )
    if observed_source_run is not None:
        repository_id = positive_int_value(data.get("repositoryId"))
        head_repository_id = positive_int_value(data.get("headRepositoryId"))
        if repository_id is None:
            errors.append(
                f"{target} release_asset_source workflow run repositoryId "
                f"must be a positive integer, got {data.get('repositoryId')!r}"
            )
        else:
            observed_source_run["repository_id"] = repository_id
        if head_repository_id is None:
            errors.append(
                f"{target} release_asset_source workflow run headRepositoryId "
                f"must be a positive integer, got {data.get('headRepositoryId')!r}"
            )
        else:
            observed_source_run["head_repository_id"] = head_repository_id
        run_created_at = data.get("runCreatedAt")
        run_started_at = data.get("runStartedAt")
        run_updated_at = data.get("runUpdatedAt")
        if parse_github_timestamp(run_created_at) is None:
            errors.append(
                f"{target} release_asset_source workflow run runCreatedAt "
                f"must be a GitHub ISO-8601 timestamp, got {run_created_at!r}"
            )
        else:
            observed_source_run["run_created_at"] = run_created_at
        if parse_github_timestamp(run_started_at) is None:
            errors.append(
                f"{target} release_asset_source workflow run runStartedAt "
                f"must be a GitHub ISO-8601 timestamp, got {run_started_at!r}"
            )
        else:
            observed_source_run["run_started_at"] = run_started_at
        if parse_github_timestamp(run_updated_at) is None:
            errors.append(
                f"{target} release_asset_source workflow run runUpdatedAt "
                f"must be a GitHub ISO-8601 timestamp, got {run_updated_at!r}"
            )
        else:
            observed_source_run["run_updated_at"] = run_updated_at
        created = parse_github_timestamp(run_created_at)
        start = parse_github_timestamp(run_started_at)
        updated = parse_github_timestamp(run_updated_at)
        if created is not None and start is not None and start < created:
            errors.append(
                f"{target} release_asset_source workflow run runStartedAt "
                f"must be at or after runCreatedAt {run_created_at}, got {run_started_at!r}"
            )
        if start is not None and updated is not None and updated < start:
            errors.append(
                f"{target} release_asset_source workflow run runUpdatedAt "
                f"must be at or after runStartedAt {run_started_at}, got {run_updated_at!r}"
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
    if data.get("headBranch") != expected_release_tag:
        errors.append(
            f"{target} release_asset_source workflow run headBranch must match release_tag "
            f"{expected_release_tag}, got {data.get('headBranch')!r}"
        )
    actual_attempt = data.get("attempt")
    if positive_int_value(actual_attempt) is None:
        errors.append(
            f"{target} release_asset_source workflow run attempt must be a positive integer, "
            f"got {actual_attempt!r}"
        )
    elif actual_attempt != expected_run_attempt:
        errors.append(
            f"{target} release_asset_source workflow run attempt must match accepted record "
            f"{expected_run_attempt}, got {actual_attempt!r}"
        )
    errors.extend(
        check_release_checkout_head_sha(
            target,
            expected_head_sha=expected_head_sha,
            release_head_sha=release_head_sha,
        )
    )
    return errors


def repository_from_workflow_run_url(workflow_run_url: str) -> str:
    if workflow_run_url != workflow_run_url.strip() or workflow_run_url != workflow_run_url.rstrip("/"):
        return ""
    match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url)
    return match.group(1) if match else ""


def positive_int_value(raw_value: Any) -> int | None:
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and raw_value > 0:
        return raw_value
    return None


def parse_github_timestamp(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value or raw_value != raw_value.strip():
        return None
    text = raw_value
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def verify_source_artifact(
    target: str,
    command: list[str],
    *,
    artifact_name: str,
    expected_repository: str,
    expected_run_id: str,
    expected_head_sha: str,
    expected_repository_id: int | None = None,
    expected_head_repository_id: int | None = None,
    expected_run_created_at: str | None = None,
    expected_run_started_at: str | None = None,
    expected_run_updated_at: str | None = None,
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
    if len(raw_artifacts) != 1:
        errors = [
            f"{target} release_asset_source artifact list must contain only the "
            f"target-scoped evidence artifact {artifact_name!r}, got {len(raw_artifacts)} artifacts"
        ]
    else:
        errors = []
    if len(matches) != 1:
        errors.append(
            f"{target} release_asset_source artifact list must contain exactly one "
            f"{artifact_name!r}, got {len(matches)}"
        )
        return errors
    artifact = matches[0]
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} id must be a positive integer, "
            f"got {artifact_id!r}"
        )
    else:
        expected_url = source_artifact_api_url(expected_repository, artifact_id)
        if artifact.get("url") != expected_url:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} url "
                f"must be {expected_url!r}, got {artifact.get('url')!r}"
            )
        expected_archive_url = f"{source_artifact_api_url(expected_repository, artifact_id)}/zip"
        if artifact.get("archive_download_url") != expected_archive_url:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} archive_download_url "
                f"must be {expected_archive_url!r}, got {artifact.get('archive_download_url')!r}"
            )
    node_id = artifact.get("node_id")
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} node_id "
            f"must be a non-empty string, got {node_id!r}"
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
    errors.extend(
        check_source_artifact_created_within_run_window(
            target,
            artifact_name,
            artifact.get("created_at"),
            expected_run_created_at=expected_run_created_at,
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    errors.extend(
        check_source_artifact_updated_within_run_window(
            target,
            artifact_name,
            artifact.get("updated_at"),
            artifact.get("created_at"),
            expected_run_created_at=expected_run_created_at,
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    errors.extend(
        check_source_artifact_expiration(
            target,
            artifact_name,
            artifact.get("expires_at"),
            raw_created_at=artifact.get("created_at"),
            raw_updated_at=artifact.get("updated_at"),
        )
    )
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} workflow_run must be an object"
        )
    else:
        artifact_run_id = workflow_run.get("id")
        expected_run_id_int = int(expected_run_id) if expected_run_id.isdecimal() else None
        if not isinstance(artifact_run_id, int) or isinstance(artifact_run_id, bool) or artifact_run_id <= 0:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.id "
                f"must be a positive integer, got {artifact_run_id!r}"
            )
        elif expected_run_id_int is not None and artifact_run_id != expected_run_id_int:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.id must match "
                f"run {expected_run_id}, got {artifact_run_id!r}"
            )
        raw_artifact_head_sha = workflow_run.get("head_sha", "")
        if not isinstance(raw_artifact_head_sha, str):
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.head_sha "
                f"must be a string, got {raw_artifact_head_sha!r}"
            )
        elif raw_artifact_head_sha != expected_head_sha:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.head_sha must match "
                f"accepted record {expected_head_sha}, got {raw_artifact_head_sha!r}"
            )
        artifact_repository_id = workflow_run.get("repository_id")
        if (
            not isinstance(artifact_repository_id, int)
            or isinstance(artifact_repository_id, bool)
            or artifact_repository_id <= 0
        ):
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.repository_id "
                f"must be a positive integer, got {artifact_repository_id!r}"
            )
        elif expected_repository_id is not None and artifact_repository_id != expected_repository_id:
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.repository_id "
                f"must match exact source run repository id {expected_repository_id}, "
                f"got {artifact_repository_id!r}"
            )
        artifact_head_repository_id = workflow_run.get("head_repository_id")
        if (
            not isinstance(artifact_head_repository_id, int)
            or isinstance(artifact_head_repository_id, bool)
            or artifact_head_repository_id <= 0
        ):
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.head_repository_id "
                f"must be a positive integer, got {artifact_head_repository_id!r}"
            )
        elif (
            expected_head_repository_id is not None
            and artifact_head_repository_id != expected_head_repository_id
        ):
            errors.append(
                f"{target} release_asset_source artifact {artifact_name} workflow_run.head_repository_id "
                f"must match exact source run head repository id {expected_head_repository_id}, "
                f"got {artifact_head_repository_id!r}"
            )
    return errors


def check_source_artifact_expiration(
    target: str,
    artifact_name: str,
    raw_expires_at: Any,
    *,
    raw_created_at: Any,
    raw_updated_at: Any,
) -> list[str]:
    expires_at = parse_github_timestamp(raw_expires_at)
    if expires_at is None:
        return [
            f"{target} release_asset_source artifact {artifact_name} expires_at "
            f"must be a GitHub ISO-8601 timestamp, got {raw_expires_at!r}"
        ]
    errors: list[str] = []
    created_at = parse_github_timestamp(raw_created_at)
    if created_at is not None and expires_at <= created_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} expires_at "
            f"must be after created_at {raw_created_at}, got {raw_expires_at!r}"
        )
    updated_at = parse_github_timestamp(raw_updated_at)
    if updated_at is not None and expires_at <= updated_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} expires_at "
            f"must be after updated_at {raw_updated_at}, got {raw_expires_at!r}"
        )
    return errors


def check_source_artifact_created_within_run_window(
    target: str,
    artifact_name: str,
    raw_created_at: Any,
    *,
    expected_run_created_at: str | None,
    expected_run_started_at: str | None,
    expected_run_updated_at: str | None,
) -> list[str]:
    if (
        expected_run_created_at is None
        and expected_run_started_at is None
        and expected_run_updated_at is None
    ):
        return []
    run_created_at = parse_github_timestamp(expected_run_created_at)
    run_started_at = parse_github_timestamp(expected_run_started_at)
    run_updated_at = parse_github_timestamp(expected_run_updated_at)
    created_at = parse_github_timestamp(raw_created_at)
    if created_at is None:
        return [
            f"{target} release_asset_source artifact {artifact_name} created_at "
            f"must be a GitHub ISO-8601 timestamp when exact source run timestamps are known, "
            f"got {raw_created_at!r}"
        ]
    errors: list[str] = []
    if run_created_at is not None and created_at < run_created_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} created_at "
            f"must be at or after exact source run creation {expected_run_created_at}, "
            f"got {raw_created_at!r}"
        )
    if run_started_at is not None and created_at < run_started_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} created_at "
            f"must be at or after exact source run start {expected_run_started_at}, "
            f"got {raw_created_at!r}"
        )
    if run_updated_at is not None and created_at > run_updated_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} created_at "
            f"must be at or before exact source run update {expected_run_updated_at}, "
            f"got {raw_created_at!r}"
        )
    return errors


def check_source_artifact_updated_within_run_window(
    target: str,
    artifact_name: str,
    raw_updated_at: Any,
    raw_created_at: Any,
    *,
    expected_run_created_at: str | None,
    expected_run_started_at: str | None,
    expected_run_updated_at: str | None,
) -> list[str]:
    if (
        expected_run_created_at is None
        and expected_run_started_at is None
        and expected_run_updated_at is None
    ):
        return []
    run_created_at = parse_github_timestamp(expected_run_created_at)
    run_started_at = parse_github_timestamp(expected_run_started_at)
    run_updated_at = parse_github_timestamp(expected_run_updated_at)
    updated_at = parse_github_timestamp(raw_updated_at)
    if updated_at is None:
        return [
            f"{target} release_asset_source artifact {artifact_name} updated_at "
            f"must be a GitHub ISO-8601 timestamp when exact source run timestamps are known, "
            f"got {raw_updated_at!r}"
        ]
    errors: list[str] = []
    if run_created_at is not None and updated_at < run_created_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} updated_at "
            f"must be at or after exact source run creation {expected_run_created_at}, "
            f"got {raw_updated_at!r}"
        )
    if run_started_at is not None and updated_at < run_started_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} updated_at "
            f"must be at or after exact source run start {expected_run_started_at}, "
            f"got {raw_updated_at!r}"
        )
    if run_updated_at is not None and updated_at > run_updated_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} updated_at "
            f"must be at or before exact source run update {expected_run_updated_at}, "
            f"got {raw_updated_at!r}"
        )
    created_at = parse_github_timestamp(raw_created_at)
    if created_at is not None and updated_at < created_at:
        errors.append(
            f"{target} release_asset_source artifact {artifact_name} updated_at "
            f"must be at or after created_at {raw_created_at}, got {raw_updated_at!r}"
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


def copy_expected_files(record: dict[str, Any], *, source_root: object, out_dir: object) -> list[str]:
    target = import_record_target_label(record)
    errors: list[str] = []
    expected_file_errors, expected_file_names = expected_release_file_name_entries(record)
    if expected_file_errors:
        return expected_file_errors
    expected_files = set(expected_file_names)
    unsafe_files = sorted(filename for filename in expected_files if not exact_safe_file_name(filename))
    if unsafe_files:
        return [f"{target} release asset import expected files must be exact safe file names: {unsafe_files}"]
    source_root_errors, source_root_path = path_arg_value(
        source_root,
        f"{target} downloaded artifact directory",
    )
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    errors.extend(source_root_errors)
    errors.extend(out_dir_errors)
    if errors:
        return errors
    assert source_root_path is not None
    assert out_dir_path is not None
    if source_root_path.is_symlink():
        errors.append(f"{target} downloaded artifact directory must not be a symlink: {source_root_path}")
    else:
        errors.extend(check_path_parent_symlinks(source_root_path, f"{target} downloaded artifact directory"))
    if not source_root_path.is_dir():
        errors.append(f"{target} downloaded artifact directory missing: {source_root_path}")
    for filename in sorted(expected_files):
        source = source_root_path / filename
        if source.is_symlink():
            errors.append(f"{target} release asset import source must not be a symlink: {filename}")
        elif not source.is_file():
            errors.append(f"{target} downloaded artifact missing expected release file: {filename}")
    errors.extend(ensure_output_directory(out_dir_path))
    if errors:
        return errors
    out_dir_path.mkdir(parents=True, exist_ok=True)
    for filename in sorted(expected_files):
        source = source_root_path / filename
        destination = out_dir_path / filename
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


def validate_source_artifact(record: dict[str, Any], *, source_root: object) -> list[str]:
    target = import_record_target_label(record)
    source_errors, expected_files = release_source_contains_files(record)
    if source_errors:
        return source_errors
    declared_errors = check_release_source_declared_files_for_record(record)
    if declared_errors:
        return declared_errors
    source_root_errors, source_root_path = path_arg_value(
        source_root,
        f"{target} downloaded artifact directory",
    )
    if source_root_errors:
        return source_root_errors
    assert source_root_path is not None
    errors = validate_downloaded_source_file_set(
        target,
        source_root=source_root_path,
        expected_files=expected_files,
    )
    if errors:
        return errors
    errors = check_downloaded_source_hashes(record, source_root=source_root_path)
    if errors:
        return errors
    return validate_downloaded_final_record(record, source_root=source_root_path)


def check_release_source_declared_files_for_record(record: dict[str, Any]) -> list[str]:
    target = import_record_target_label(record)
    source_errors, declared_files = release_source_contains_files(record)
    if source_errors:
        return source_errors
    expected_file_errors, expected_file_names = expected_release_file_name_entries(record)
    if expected_file_errors:
        return expected_file_errors
    return check_release_source_declared_files(
        target,
        declared_files=declared_files,
        expected_files=set(expected_file_names),
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
    source_root: object,
    expected_files: set[str],
) -> list[str]:
    source_root_errors, source_root_path = path_arg_value(
        source_root,
        f"{target} downloaded artifact directory",
    )
    if source_root_errors:
        return source_root_errors
    assert source_root_path is not None
    if source_root_path.is_symlink():
        return [f"{target} downloaded artifact directory must not be a symlink: {source_root_path}"]
    parent_errors = check_path_parent_symlinks(source_root_path, f"{target} downloaded artifact directory")
    if parent_errors:
        return parent_errors
    if not source_root_path.is_dir():
        return [f"{target} downloaded artifact directory missing: {source_root_path}"]
    errors: list[str] = []
    root_files: set[str] = set()
    root_directories: list[str] = []
    root_symlinks: list[str] = []
    for child in source_root_path.iterdir():
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


def checked_artifact_hash_items(record: dict[str, Any], *, label: str) -> tuple[list[tuple[str, Any]], list[str]]:
    target = import_record_target_label(record)
    artifact_hashes = record.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        return [], []
    items: list[tuple[str, Any]] = []
    errors: list[str] = []
    for filename, digest in artifact_hashes.items():
        if not isinstance(filename, str) or not exact_safe_file_name(filename):
            errors.append(f"{target} {label} artifact_sha256 keys must be exact safe file names, got {filename!r}")
            continue
        if not lowercase_sha256_hex(digest):
            errors.append(
                f"{target} {label} artifact_sha256.{filename} "
                "must be a lowercase SHA-256 hex digest"
            )
            continue
        items.append((filename, digest))
    case_collisions = case_insensitive_name_collisions({filename for filename, _digest in items})
    if case_collisions:
        errors.append(
            f"{target} {label} artifact_sha256 keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return sorted(items, key=lambda item: item[0]), errors


def checked_review_bundle_records(
    record: dict[str, Any],
    *,
    label: str,
) -> tuple[list[tuple[str, str, Any, str]], list[str]]:
    target = import_record_target_label(record)
    review_bundle = record.get("review_bundle")
    if not isinstance(review_bundle, dict):
        return [], []
    records: list[tuple[str, str, Any, str]] = []
    errors: list[str] = []
    for key in ("manifest", "archive", "sha256s"):
        bundle_record = review_bundle.get(key)
        if not isinstance(bundle_record, dict):
            continue
        raw_filename = bundle_record.get("file", "")
        if not isinstance(raw_filename, str) or not exact_safe_file_name(raw_filename):
            errors.append(
                f"{target} {label} review_bundle {key}.file must be an exact safe file name, "
                f"got {raw_filename!r}"
            )
            continue
        raw_size = bundle_record.get("size_bytes")
        if not isinstance(raw_size, int) or isinstance(raw_size, bool) or raw_size <= 0:
            errors.append(f"{target} {label} review_bundle {key}.size_bytes must be a positive integer")
        raw_sha256 = bundle_record.get("sha256", "")
        if not lowercase_sha256_hex(raw_sha256):
            errors.append(
                f"{target} {label} review_bundle {key}.sha256 must be a lowercase SHA-256 hex digest"
            )
            continue
        records.append((key, raw_filename, raw_size, raw_sha256))
    filename_counts: dict[str, int] = {}
    for _key, filename, _size, _sha256 in records:
        filename_counts[filename] = filename_counts.get(filename, 0) + 1
    duplicate_files = sorted(filename for filename, count in filename_counts.items() if count > 1)
    if duplicate_files:
        errors.append(
            f"{target} {label} review_bundle files must not contain duplicates: "
            f"{duplicate_files}"
        )
    case_collisions = case_insensitive_name_collisions({filename for _key, filename, _size, _sha256 in records})
    if case_collisions:
        errors.append(
            f"{target} {label} review_bundle files must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return records, errors


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA256_HEX_CHARS


def check_downloaded_source_hashes(record: dict[str, Any], *, source_root: object) -> list[str]:
    target = import_record_target_label(record)
    source_root_errors, source_root_path = path_arg_value(
        source_root,
        f"{target} downloaded artifact directory",
    )
    if source_root_errors:
        return source_root_errors
    assert source_root_path is not None
    artifact_items, errors = checked_artifact_hash_items(record, label="downloaded source artifact")
    for filename, digest in artifact_items:
        path = source_root_path / filename
        if path.is_symlink():
            errors.append(
                f"{target} downloaded source artifact native artifact must not be a symlink: {filename}"
            )
            continue
        if not path.is_file():
            errors.append(f"{target} downloaded source artifact missing native artifact: {filename}")
            continue
        if sha256_file(path) != digest:
            errors.append(f"{target} downloaded source artifact native artifact SHA-256 mismatch: {filename}")
    bundle_records, bundle_errors = checked_review_bundle_records(
        record,
        label="downloaded source artifact",
    )
    errors.extend(bundle_errors)
    for key, filename, expected_size, expected_sha256 in bundle_records:
        path = source_root_path / filename
        if path.is_symlink():
            errors.append(
                f"{target} downloaded source artifact review bundle {key} "
                f"must not be a symlink: {filename}"
            )
            continue
        if not path.is_file():
            errors.append(f"{target} downloaded source artifact missing review bundle {key}: {filename}")
            continue
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size != path.stat().st_size:
            errors.append(
                f"{target} downloaded source artifact review bundle {key} size_bytes mismatch: {filename}"
            )
        if sha256_file(path) != expected_sha256:
            errors.append(
                f"{target} downloaded source artifact review bundle {key} SHA-256 mismatch: {filename}"
            )
    return errors


def check_imported_hashes(record: dict[str, Any], *, out_dir: object) -> list[str]:
    target = import_record_target_label(record)
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    if out_dir_errors:
        return out_dir_errors
    assert out_dir_path is not None
    artifact_items, errors = checked_artifact_hash_items(record, label="imported native artifact")
    for filename, digest in artifact_items:
        path = out_dir_path / filename
        if path.is_symlink():
            errors.append(f"{target} imported native artifact must not be a symlink: {filename}")
            continue
        if not path.is_file():
            errors.append(f"{target} imported native artifact missing: {filename}")
            continue
        if sha256_file(path) != digest:
            errors.append(f"{target} imported native artifact SHA-256 mismatch: {filename}")
    bundle_records, bundle_errors = checked_review_bundle_records(
        record,
        label="imported",
    )
    errors.extend(bundle_errors)
    for key, filename, expected_size, expected_sha256 in bundle_records:
        path = out_dir_path / filename
        if path.is_symlink():
            errors.append(f"{target} imported review bundle {key} must not be a symlink: {filename}")
            continue
        if not path.is_file():
            errors.append(f"{target} imported review bundle {key} missing: {filename}")
            continue
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size != path.stat().st_size:
            errors.append(f"{target} imported review bundle {key} size_bytes mismatch: {filename}")
        if sha256_file(path) != expected_sha256:
            errors.append(f"{target} imported review bundle {key} SHA-256 mismatch: {filename}")
    return errors


def check_imported_review_bundle(record: dict[str, Any], *, out_dir: object) -> list[str]:
    public_errors = public_record_key_errors(record)
    if public_errors:
        return public_errors
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "release asset import output directory")
    if out_dir_errors:
        return out_dir_errors
    assert out_dir_path is not None
    registry = read_json(EVIDENCE_PATH)
    target = accepted_import_target(record)
    release_tag = record.get("release_tag", "")
    if not isinstance(release_tag, str):
        release_tag = ""
    errors = check_platform_review_bundle_artifacts(
        registry={**registry, "accepted_evidence": [public_record(record)]},
        bundle_dir=out_dir_path,
        required_targets=(target,) if target else None,
        required_release_tag=release_tag or None,
        require_final_record_assets=True,
    )
    return [f"{target} imported review bundle validation failed: {error}" for error in errors]


def expected_release_file_names(record: dict[str, Any]) -> list[str]:
    _errors, files = expected_release_file_name_entries(record)
    return files


def expected_release_file_name_entries(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    files: list[str] = []
    target = import_record_target_label(record)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            if not isinstance(name, str):
                errors.append(
                    f"{target} release asset import artifact_sha256 keys must be strings, got {name!r}"
                )
                continue
            files.append(name)
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if isinstance(bundle_record, dict):
                filename = bundle_record.get("file", "")
                if not isinstance(filename, str):
                    errors.append(
                        f"{target} release asset import review_bundle {key}.file "
                        f"must be a string, got {filename!r}"
                    )
                    continue
                if filename:
                    files.append(filename)
    accepted_target = accepted_import_target(record)
    if accepted_target in PROTECTED_GOAL_TARGETS:
        files.append(accepted_record_source_file(accepted_target))
    file_counts: dict[str, int] = {}
    for filename in files:
        file_counts[filename] = file_counts.get(filename, 0) + 1
    duplicate_files = sorted(filename for filename, count in file_counts.items() if count > 1)
    if duplicate_files:
        errors.append(
            f"{target} release asset import expected files must not contain duplicates: "
            f"{duplicate_files}"
        )
    case_collisions = case_insensitive_name_collisions(set(files))
    if case_collisions:
        errors.append(
            f"{target} release asset import expected files must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return errors, files


def expected_release_files(record: dict[str, Any]) -> set[str]:
    return set(expected_release_file_names(record))


def expected_source_files(record: dict[str, Any]) -> set[str]:
    errors, files = release_source_contains_files(record)
    if errors:
        return set()
    return files


def release_source_contains_files(record: dict[str, Any]) -> tuple[list[str], set[str]]:
    target = import_record_target_label(record)
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"], set()
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        return [f"{target} release_asset_source.contains_files must be a non-empty list"], set()
    files = [name for name in raw_files if isinstance(name, str)]
    unsafe = sorted(
        {
            name if isinstance(name, str) else repr(name)
            for name in raw_files
            if not isinstance(name, str) or not exact_safe_file_name(name)
        }
    )
    errors: list[str] = []
    if unsafe:
        errors.append(f"{target} release_asset_source.contains_files entries must be exact safe file names: {unsafe}")
    duplicates = sorted({name for name in files if files.count(name) > 1})
    if duplicates:
        errors.append(f"{target} release_asset_source.contains_files contains duplicates: {duplicates}")
    case_collisions = case_insensitive_name_collisions(set(files))
    if case_collisions:
        errors.append(
            f"{target} release_asset_source.contains_files must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return errors, set(files)


def validate_downloaded_final_record(record: dict[str, Any], *, source_root: object) -> list[str]:
    target = accepted_import_target(record)
    if target not in PROTECTED_GOAL_TARGETS:
        return []
    filename = accepted_record_source_file(target)
    source_root_errors, source_root_path = path_arg_value(
        source_root,
        f"{target} downloaded artifact directory",
    )
    if source_root_errors:
        return source_root_errors
    assert source_root_path is not None
    path = source_root_path / filename
    parent_errors = check_path_parent_symlinks(path, f"{target} finalized accepted record source file")
    if parent_errors:
        return parent_errors
    if path.is_symlink():
        return [f"{target} finalized accepted record source file must not be a symlink: {filename}"]
    if not path.is_file():
        return [f"{target} downloaded artifact missing finalized accepted record: {filename}"]
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return [f"{target} finalized accepted record source file is not readable JSON: {filename}: {exc}"]
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} finalized accepted record source file is not readable JSON: {filename}: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} finalized accepted record source file must contain a JSON object: {filename}"]
    public_errors = public_record_key_errors(record)
    if public_errors:
        return public_errors
    if data != public_record(record):
        return [f"{target} finalized accepted record source file must match accepted registry record: {filename}"]
    if raw_bytes != canonical_public_record_bytes(record):
        return [f"{target} finalized accepted record source file must use canonical sorted JSON: {filename}"]
    return []


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if isinstance(key, str) and not key.startswith("_")}


def accepted_import_target(record: dict[str, Any]) -> str:
    target = record.get("target", "")
    if not isinstance(target, str):
        return ""
    return target.strip()


def import_record_target_label(record: dict[str, Any]) -> str:
    return accepted_import_target(record) or "<unknown>"


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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
