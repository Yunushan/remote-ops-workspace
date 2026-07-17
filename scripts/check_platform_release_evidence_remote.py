from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_promotion_artifacts import (  # noqa: E402
    CHECKSUM_SUFFIX,
    MANIFEST_SUFFIX,
    artifact_reference_name_is_safe,
    expected_manifest_architecture,
    expected_manifest_format,
    manifest_record_filename,
    manifest_records,
)
from check_platform_review_bundle_artifacts import canonical_public_record_bytes  # noqa: E402
from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    GITHUB_RELEASE_ASSET_RE,
    GITHUB_REPOSITORY_RE,
    PROMOTION_PATH,
    PROTECTED_GOAL_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    accepted_artifact_names,
    accepted_record_source_file,
    case_insensitive_name_collisions,
    check_platform_verified_evidence,
    exact_safe_file_name,
    read_json,
    release_asset_url_filename,
    release_source_workflow,
    review_bundle_expected_files,
)

GITHUB_API = "https://api.github.com"
PROTECTED_RELEASE_ASSET_PATTERNS = {
    "linux-i386": (
        r"^platform-verified-evidence-linux-i386(?:-final)?\.json$",
        r"^extended-linux-evidence-bundle-linux-i386-v\d+\.\d+\.\d+(?:\.json|\.zip|-SHA256SUMS\.txt)$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-i386\.deb$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686\.",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686-native-",
    ),
    "linux-armhf": (
        r"^platform-verified-evidence-linux-armhf(?:-final)?\.json$",
        r"^extended-linux-evidence-bundle-linux-armhf-v\d+\.\d+\.\d+(?:\.json|\.zip|-SHA256SUMS\.txt)$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.deb$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-armv7hl\.",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf-native-",
    ),
    "windows-xp-native-x86": (
        r"^platform-verified-evidence-windows-xp-native-x86(?:-final)?\.json$",
        r"^xp-native-evidence-bundle-windows-xp-native-x86-v\d+\.\d+\.\d+(?:\.json|\.zip|-SHA256SUMS\.txt)$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x86-native",
    ),
    "windows-xp-native-x64": (
        r"^platform-verified-evidence-windows-xp-native-x64(?:-final)?\.json$",
        r"^xp-native-evidence-bundle-windows-xp-native-x64-v\d+\.\d+\.\d+(?:\.json|\.zip|-SHA256SUMS\.txt)$",
        r"^remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x64-native",
    ),
}
GOAL_RELEASE_AUDIT_REQUIRED_FLAGS = (
    ("--require-source-runs", "require_source_runs"),
    ("--require-source-artifact-bytes", "require_source_artifact_bytes"),
    ("--require-final-record-bytes", "require_final_record_bytes"),
    ("--require-release-asset-bytes", "require_release_asset_bytes"),
    ("--require-tag-source-head", "require_tag_source_head"),
)
GITHUB_ACTIONS_RUN_FIXTURE_RE = re.compile(
    rf"^https://github\.com/{GITHUB_REPOSITORY_RE}/actions/runs/[1-9]\d*$"
)
GITHUB_ACTIONS_RUN_ID_RE = re.compile(r"^[1-9]\d*$")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    arg_errors = strict_arg_errors(args)
    if arg_errors:
        for error in arg_errors:
            print(f"platform release evidence remote: {error}", file=sys.stderr)
        return 2

    registry = read_json(args.registry)
    promotion = read_json(args.promotion)
    required_targets = required_targets_from_args(args, registry)
    registry_errors = remote_registry_preflight_errors(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    if registry_errors and not args.require_goal_targets:
        for error in dict.fromkeys(registry_errors):
            print(f"platform release evidence remote: {error}", file=sys.stderr)
        return 1
    release, release_errors = load_release_data(args)
    source_runs, source_run_errors = load_source_runs(args, registry, required_targets)
    workflow_runs, workflow_errors = load_workflow_runs(args, registry, required_targets)
    source_artifacts, source_artifact_errors = load_source_artifacts(args, registry, required_targets)
    source_artifact_bytes, source_artifact_byte_errors = load_source_artifact_bytes(
        args,
        registry,
        required_targets,
        source_artifacts,
    )
    final_record_bytes, final_record_errors = load_final_record_bytes(args, registry, required_targets)
    release_asset_bytes, release_asset_byte_errors = load_release_asset_bytes(
        args,
        registry,
        required_targets,
    )
    tag_ref, tag_object, tag_errors = load_release_tag_data(args)
    errors = [
        *release_errors,
        *source_run_errors,
        *workflow_errors,
        *source_artifact_errors,
        *source_artifact_byte_errors,
        *final_record_errors,
        *release_asset_byte_errors,
        *tag_errors,
    ]
    if release is None:
        errors.extend(registry_errors)
    if release is not None:
        errors.extend(
            check_remote_platform_release_evidence(
                registry=registry,
                promotion=promotion,
                release=release,
                source_runs_by_run=source_runs,
                workflow_runs_by_workflow=workflow_runs,
                source_artifacts_by_run=source_artifacts,
                source_artifact_bytes_by_run=source_artifact_bytes,
                final_record_bytes_by_url=final_record_bytes,
                release_asset_bytes_by_url=release_asset_bytes,
                tag_ref=tag_ref,
                tag_object=tag_object,
                release_tag=args.release_tag,
                required_targets=required_targets,
                require_source_runs=args.require_source_runs,
                require_source_artifact_bytes=args.require_source_artifact_bytes,
                require_final_record_bytes=args.require_final_record_bytes,
                require_release_asset_bytes=args.require_release_asset_bytes,
                require_tag_source_head=args.require_tag_source_head,
            )
        )
    if errors:
        for error in dict.fromkeys(errors):
            print(f"platform release evidence remote: {error}", file=sys.stderr)
        return 1
    print(f"platform release evidence remote passed for {args.release_tag}")
    return 0


def remote_registry_preflight_errors(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> list[str]:
    if required_targets:
        return check_platform_verified_evidence(
            registry=registry,
            required_targets=required_targets,
            required_release_tag=release_tag,
            require_review_bundles=True,
        )
    return check_platform_verified_evidence(registry=registry)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a GitHub release and optional workflow-run metadata for "
            "protected Linux i386/armhf and Windows XP native-host evidence."
        )
    )
    parser.add_argument("--repository", help="GitHub repository in owner/name form")
    parser.add_argument("--release-tag", required=True, help="release tag, for example v1.0.7")
    parser.add_argument("--registry", type=Path, default=EVIDENCE_PATH)
    parser.add_argument("--promotion", type=Path, default=PROMOTION_PATH)
    parser.add_argument(
        "--release-json",
        type=Path,
        help="read GitHub release JSON from a file instead of the live API",
    )
    parser.add_argument(
        "--workflow-runs-json",
        action="append",
        default=[],
        metavar="WORKFLOW=PATH",
        help=(
            "read workflow runs JSON for a workflow file path, for example "
            ".github/workflows/extended-platform-evidence.yml=runs.json; "
            "--require-source-runs offline audits still require --source-run-json"
        ),
    )
    parser.add_argument(
        "--source-run-json",
        action="append",
        default=[],
        metavar="RUN=PATH",
        help=(
            "read exact source workflow run metadata for a run URL or run id, for example "
            "https://github.com/owner/repo/actions/runs/12345=run.json"
        ),
    )
    parser.add_argument(
        "--source-artifacts-json",
        action="append",
        default=[],
        metavar="RUN=PATH",
        help=(
            "read source workflow artifact metadata for a run URL or run id, for example "
            "https://github.com/owner/repo/actions/runs/12345=artifacts.json"
        ),
    )
    parser.add_argument(
        "--source-artifact-zip",
        action="append",
        default=[],
        metavar="RUN=PATH",
        help=(
            "read the exact source workflow artifact ZIP for a run URL or run id, "
            "for example https://github.com/owner/repo/actions/runs/12345=artifact.zip"
        ),
    )
    parser.add_argument(
        "--final-record-json",
        action="append",
        default=[],
        metavar="URL=PATH",
        help=(
            "read a published finalized accepted-record JSON asset from a local file for "
            "offline byte verification, for example "
            "https://github.com/owner/repo/releases/download/v1.0.7/platform-verified-evidence-linux-i386-final.json=record.json"
        ),
    )
    parser.add_argument(
        "--release-asset",
        action="append",
        default=[],
        metavar="URL=PATH",
        help=(
            "read a published native or review-bundle release asset from a local file for "
            "offline byte verification, for example "
            "https://github.com/owner/repo/releases/download/v1.0.7/remote-ops-workspace-v1.0.7-linux-i386.deb=asset.deb"
        ),
    )
    parser.add_argument(
        "--tag-ref-json",
        type=Path,
        help=(
            "read GitHub git/ref tag JSON from a file instead of the live API for "
            "release tag source-head verification"
        ),
    )
    parser.add_argument(
        "--tag-object-json",
        type=Path,
        help=(
            "read GitHub annotated git/tag object JSON from a file instead of the live API "
            "when --tag-ref-json points at an annotated tag"
        ),
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help=(
            "require all protected platform goal targets for the release tag; "
            "also requires the strict source-run, source-artifact byte, final-record byte, "
            "release-asset byte and tag source-head proof flags"
        ),
    )
    parser.add_argument(
        "--require-source-runs",
        action="store_true",
        help="require each accepted record source workflow run to be present and successful",
    )
    parser.add_argument(
        "--require-source-artifact-bytes",
        action="store_true",
        help=(
            "download or fixture each source workflow artifact ZIP and verify its "
            "internal file list, SHA-256 values and known sizes match accepted evidence"
        ),
    )
    parser.add_argument(
        "--require-final-record-bytes",
        action="store_true",
        help=(
            "download or fixture each finalized accepted-record release asset and byte-compare "
            "it with the canonical public accepted registry record"
        ),
    )
    parser.add_argument(
        "--require-release-asset-bytes",
        action="store_true",
        help=(
            "download or fixture each protected native and review-bundle release asset "
            "and hash the actual bytes against accepted evidence"
        ),
    )
    parser.add_argument(
        "--require-tag-source-head",
        action="store_true",
        help=(
            "require the published Git tag ref/object to resolve to the same source head "
            "SHA used by the accepted release evidence records"
        ),
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def strict_arg_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    errors.extend(check_local_fixture_path(args.registry, "--registry file"))
    errors.extend(check_local_fixture_path(args.promotion, "--promotion file"))
    repository_errors, repository = normalize_repository_arg(args.repository)
    errors.extend(repository_errors)
    if repository is not None:
        args.repository = repository
    if args.require_goal_targets:
        missing_goal_flags = [
            flag
            for flag, attr in GOAL_RELEASE_AUDIT_REQUIRED_FLAGS
            if not getattr(args, attr)
        ]
        if missing_goal_flags:
            errors.append(
                "--require-goal-targets requires strict published release proof flags: "
                f"{', '.join(missing_goal_flags)}"
            )
    if args.require_source_artifact_bytes and not args.require_source_runs:
        errors.append("--require-source-artifact-bytes requires --require-source-runs")
    if not args.release_json and not args.repository:
        errors.append("--repository is required unless --release-json is provided")
    if args.require_source_runs and not args.repository:
        exact_run_paths = source_run_json_paths(args)
        if not exact_run_paths:
            errors.append(
                "--require-source-runs without --repository requires --source-run-json "
                "for exact accepted source run metadata"
            )
        artifact_runs = source_artifact_json_paths(args)
        if not artifact_runs:
            errors.append("--require-source-runs without --repository requires --source-artifacts-json")
    if args.require_source_artifact_bytes and not args.repository and not source_artifact_zip_paths(args):
        errors.append("--require-source-artifact-bytes without --repository requires --source-artifact-zip")
    if args.require_final_record_bytes and not args.repository and not final_record_json_paths(args):
        errors.append("--require-final-record-bytes without --repository requires --final-record-json")
    if args.require_release_asset_bytes and not args.repository and not release_asset_paths(args):
        errors.append("--require-release-asset-bytes without --repository requires --release-asset")
    if args.require_tag_source_head and not args.repository and not args.tag_ref_json:
        errors.append("--require-tag-source-head without --repository requires --tag-ref-json")
    for raw in args.workflow_runs_json:
        if "=" not in str(raw):
            errors.append(f"--workflow-runs-json must be WORKFLOW=PATH, got {raw!r}")
    for raw in args.source_run_json:
        if "=" not in str(raw):
            errors.append(f"--source-run-json must be RUN=PATH, got {raw!r}")
    for raw in args.source_artifacts_json:
        if "=" not in str(raw):
            errors.append(f"--source-artifacts-json must be RUN=PATH, got {raw!r}")
    for raw in args.source_artifact_zip:
        if "=" not in str(raw):
            errors.append(f"--source-artifact-zip must be RUN=PATH, got {raw!r}")
    for raw in args.final_record_json:
        if "=" not in str(raw):
            errors.append(f"--final-record-json must be URL=PATH, got {raw!r}")
    for raw in args.release_asset:
        if "=" not in str(raw):
            errors.append(f"--release-asset must be URL=PATH, got {raw!r}")
    errors.extend(source_run_fixture_key_errors(args.source_run_json, "--source-run-json"))
    errors.extend(source_run_fixture_key_errors(args.source_artifacts_json, "--source-artifacts-json"))
    errors.extend(source_run_fixture_key_errors(args.source_artifact_zip, "--source-artifact-zip"))
    errors.extend(release_asset_fixture_url_errors(args.final_record_json, "--final-record-json"))
    errors.extend(release_asset_fixture_url_errors(args.release_asset, "--release-asset"))
    errors.extend(duplicate_workflow_fixture_errors(args.workflow_runs_json, "--workflow-runs-json"))
    errors.extend(duplicate_run_fixture_errors(args.source_run_json, "--source-run-json"))
    errors.extend(duplicate_run_fixture_errors(args.source_artifacts_json, "--source-artifacts-json"))
    errors.extend(duplicate_run_fixture_errors(args.source_artifact_zip, "--source-artifact-zip"))
    errors.extend(duplicate_url_fixture_errors(args.final_record_json, "--final-record-json"))
    errors.extend(duplicate_url_fixture_errors(args.release_asset, "--release-asset"))
    return errors


def normalize_repository_arg(repository: object) -> tuple[list[str], str | None]:
    if repository is None:
        return [], None
    if not isinstance(repository, str):
        return [f"--repository must be a string GitHub owner/name value, got {repository!r}"], None
    normalized = repository.strip().strip("/")
    if not normalized:
        return ["--repository must be a non-empty GitHub owner/name value"], None
    if not re.fullmatch(GITHUB_REPOSITORY_RE, normalized):
        return [f"--repository must be a GitHub owner/name value, got {repository!r}"], None
    return [], normalized


def source_run_fixture_key_errors(raw_values: list[str], flag: str) -> list[str]:
    errors: list[str] = []
    for raw in raw_values:
        text = str(raw)
        if "=" not in text:
            continue
        run, _path = text.split("=", 1)
        if not canonical_source_run_fixture_key(run):
            errors.append(
                f"{flag} RUN must be a bare run id or canonical GitHub Actions run URL "
                f"without surrounding whitespace or trailing slash, got {run!r}"
            )
    return errors


def canonical_source_run_fixture_key(run: str) -> bool:
    return bool(
        run
        and run == run.strip()
        and run == run.rstrip("/")
        and (GITHUB_ACTIONS_RUN_ID_RE.fullmatch(run) or GITHUB_ACTIONS_RUN_FIXTURE_RE.fullmatch(run))
    )


def release_asset_fixture_url_errors(raw_values: list[str], flag: str) -> list[str]:
    errors: list[str] = []
    for raw in raw_values:
        text = str(raw)
        if "=" not in text:
            continue
        url, _path = text.split("=", 1)
        if not canonical_release_asset_fixture_url(url):
            errors.append(
                f"{flag} URL must be a canonical GitHub release asset URL without "
                f"surrounding whitespace, query, fragment, or unsafe filename, got {url!r}"
            )
    return errors


def canonical_release_asset_fixture_url(url: str) -> bool:
    return bool(
        url
        and url == url.strip()
        and GITHUB_RELEASE_ASSET_RE.fullmatch(url)
        and release_asset_url_filename(url)
    )


def duplicate_workflow_fixture_errors(raw_values: list[str], flag: str) -> list[str]:
    workflows: dict[str, int] = {}
    for raw in raw_values:
        text = str(raw)
        if "=" not in text:
            continue
        workflow, _path = text.split("=", 1)
        workflow_key = normalize_workflow_key(workflow)
        workflows[workflow_key] = workflows.get(workflow_key, 0) + 1
    duplicates = sorted(workflow for workflow, count in workflows.items() if count > 1)
    if duplicates:
        return [f"{flag} contains duplicate workflow fixtures: {duplicates}"]
    return []


def duplicate_run_fixture_errors(raw_values: list[str], flag: str) -> list[str]:
    runs: dict[str, int] = {}
    for raw in raw_values:
        text = str(raw)
        if "=" not in text:
            continue
        run, _path = text.split("=", 1)
        run_key = normalize_run_key(run)
        runs[run_key] = runs.get(run_key, 0) + 1
    duplicates = sorted(run for run, count in runs.items() if count > 1)
    if duplicates:
        return [f"{flag} contains duplicate run fixtures: {duplicates}"]
    return []


def duplicate_url_fixture_errors(raw_values: list[str], flag: str) -> list[str]:
    urls: dict[str, int] = {}
    for raw in raw_values:
        text = str(raw)
        if "=" not in text:
            continue
        url, _path = text.split("=", 1)
        url_key = normalize_url_key(url)
        urls[url_key] = urls.get(url_key, 0) + 1
    duplicates = sorted(url for url, count in urls.items() if count > 1)
    if duplicates:
        return [f"{flag} contains duplicate URL fixtures: {duplicates}"]
    return []


def required_targets_from_args(
    args: argparse.Namespace,
    registry: dict[str, Any],
) -> tuple[str, ...]:
    if args.require_goal_targets:
        return PROTECTED_GOAL_TARGETS
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return ()
    targets = {
        accepted_record_target(row)
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == args.release_tag
        and accepted_record_target(row) in PROTECTED_GOAL_TARGETS
    }
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets)


def load_release_data(args: argparse.Namespace) -> tuple[dict[str, Any] | None, list[str]]:
    if args.release_json:
        data, error = read_json_file(args.release_json, "--release-json fixture")
        return data, ([error] if error else [])
    url = f"{GITHUB_API}/repos/{args.repository}/releases/tags/{quote(args.release_tag, safe='')}"
    return fetch_json(url, timeout=args.timeout)


def load_source_runs(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    configured_paths = source_run_json_paths(args)
    source_runs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for run, path in configured_paths.items():
        data, error = read_json_file(path, "--source-run-json fixture")
        if error:
            errors.append(error)
            continue
        source_runs[normalize_run_key(run)] = data or {}
    if not args.require_source_runs:
        return source_runs, errors
    expected_keys = expected_source_run_fixture_keys(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    unexpected_keys = sorted(set(source_runs) - expected_keys)
    if unexpected_keys:
        errors.append(
            "--source-run-json contains fixtures outside required accepted "
            f"source-run scope: {unexpected_keys}"
        )
    errors.extend(
        source_run_alias_fixture_errors(
            source_runs,
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
            flag="--source-run-json",
        )
    )
    if not args.repository:
        errors.extend(
            missing_source_run_fixture_errors(
                source_runs,
                registry,
                release_tag=args.release_tag,
                required_targets=required_targets,
                flag="--source-run-json",
            )
        )

    for run_url in sorted(
        source_run_urls_for_records(
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
        )
    ):
        run_key = normalize_run_key(run_url)
        if run_key in source_runs:
            continue
        if not args.repository:
            continue
        run_id = run_key.rsplit("/", 1)[-1]
        run_attempt = source_run_attempt_for_url(
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
            run_url=run_url,
        )
        if run_attempt is None:
            continue
        url = source_run_attempt_api_url(args.repository, run_id, run_attempt)
        data, error = fetch_json(url, timeout=args.timeout)
        if error:
            errors.extend(error)
            continue
        source_runs[run_key] = data or {}
    return source_runs, errors


def load_workflow_runs(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    configured_paths = workflow_run_json_paths(args)
    workflow_runs: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for workflow, path in configured_paths.items():
        data, error = read_json_file(path, "--workflow-runs-json fixture")
        if error:
            errors.append(error)
            continue
        workflow_runs[workflow] = data or {}
    if not args.require_source_runs:
        return workflow_runs, errors

    needed_workflows = source_workflows_for_records(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    if args.require_goal_targets:
        needed_workflows.update(release_source_workflow(target) for target in PROTECTED_GOAL_TARGETS)
    unexpected_workflows = sorted(set(configured_paths) - needed_workflows)
    if unexpected_workflows:
        errors.append(
            "--workflow-runs-json contains fixtures outside required accepted "
            f"workflow scope: {unexpected_workflows}"
        )
    for workflow in sorted(needed_workflows - set(workflow_runs)):
        if not args.repository:
            continue
        url = workflow_runs_api_url(args.repository, workflow, args.release_tag)
        data, error = fetch_json(url, timeout=args.timeout)
        if error:
            errors.extend(error)
            continue
        workflow_runs[workflow] = data or {}
    return workflow_runs, errors


def load_source_artifacts(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    configured_paths = source_artifact_json_paths(args)
    source_artifacts: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for run, path in configured_paths.items():
        data, error = read_json_file(path, "--source-artifacts-json fixture")
        if error:
            errors.append(error)
            continue
        source_artifacts[normalize_run_key(run)] = data or {}
    if not args.require_source_runs:
        return source_artifacts, errors
    expected_keys = expected_source_run_fixture_keys(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    unexpected_keys = sorted(set(source_artifacts) - expected_keys)
    if unexpected_keys:
        errors.append(
            "--source-artifacts-json contains fixtures outside required accepted "
            f"source-run scope: {unexpected_keys}"
        )
    errors.extend(
        source_run_alias_fixture_errors(
            source_artifacts,
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
            flag="--source-artifacts-json",
        )
    )
    if not args.repository:
        errors.extend(
            missing_source_run_fixture_errors(
                source_artifacts,
                registry,
                release_tag=args.release_tag,
                required_targets=required_targets,
                flag="--source-artifacts-json",
            )
        )

    for run_url in sorted(
        source_run_urls_for_records(
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
        )
    ):
        run_key = normalize_run_key(run_url)
        if run_key in source_artifacts:
            continue
        if not args.repository:
            continue
        run_id = run_key.rsplit("/", 1)[-1]
        url = f"{GITHUB_API}/repos/{args.repository}/actions/runs/{quote(run_id, safe='')}/artifacts?per_page=100"
        data, error = fetch_json(url, timeout=args.timeout)
        if error:
            errors.extend(error)
            continue
        source_artifacts[run_key] = data or {}
    return source_artifacts, errors


def load_source_artifact_bytes(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
    source_artifacts_by_run: dict[str, dict[str, Any]],
) -> tuple[dict[str, bytes], list[str]]:
    configured_paths = source_artifact_zip_paths(args)
    artifact_bytes: dict[str, bytes] = {}
    errors: list[str] = []
    for run, path in configured_paths.items():
        data, error = read_bytes_file(path, "--source-artifact-zip fixture")
        if error:
            errors.append(error)
            continue
        artifact_bytes[normalize_run_key(run)] = data or b""
    if not args.require_source_artifact_bytes:
        return artifact_bytes, errors
    expected_keys = expected_source_run_fixture_keys(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    unexpected_keys = sorted(set(artifact_bytes) - expected_keys)
    if unexpected_keys:
        errors.append(
            "--source-artifact-zip contains fixtures outside required accepted "
            f"source-run scope: {unexpected_keys}"
        )
    errors.extend(
        source_run_alias_fixture_errors(
            artifact_bytes,
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
            flag="--source-artifact-zip",
        )
    )
    if not args.repository:
        errors.extend(
            missing_source_run_fixture_errors(
                artifact_bytes,
                registry,
                release_tag=args.release_tag,
                required_targets=required_targets,
                flag="--source-artifact-zip",
            )
        )

    for target, record in sorted(
        accepted_records_by_target(
            registry,
            release_tag=args.release_tag,
            targets=required_targets,
        ).items()
    ):
        source = record.get("release_asset_source")
        if not isinstance(source, dict):
            continue
        source_values, source_errors = source_artifact_expected_values(target, source)
        if source_errors:
            continue
        run_url = source_values["workflow_run_url"]
        run_key = normalize_run_key(run_url)
        if not run_key or run_key in artifact_bytes:
            continue
        if not args.repository:
            continue
        artifact = source_artifact_record_for_run(target, record, source_artifacts_by_run)
        if not artifact:
            continue
        archive_errors, archive_url = source_artifact_archive_download_url_for_fetch(
            target,
            artifact,
            repository=args.repository,
        )
        if archive_errors:
            errors.extend(archive_errors)
            continue
        data, fetch_errors = fetch_bytes(archive_url, timeout=args.timeout)
        if fetch_errors:
            errors.extend(fetch_errors)
            continue
        artifact_bytes[run_key] = data or b""
    return artifact_bytes, errors


def load_final_record_bytes(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, bytes], list[str]]:
    configured_paths = final_record_json_paths(args)
    records_by_url: dict[str, bytes] = {}
    errors: list[str] = []
    for url, path in configured_paths.items():
        data, error = read_bytes_file(path, "--final-record-json fixture")
        if error:
            errors.append(error)
            continue
        records_by_url[url] = data or b""
    if not args.require_final_record_bytes:
        return records_by_url, errors
    expected_urls = expected_final_record_byte_urls(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    unexpected_urls = sorted(set(configured_paths) - expected_urls)
    if unexpected_urls:
        errors.append(
            "--final-record-json contains fixtures outside required accepted "
            f"final-record byte scope: {unexpected_urls}"
        )
    if not args.repository:
        missing_urls = sorted(expected_urls - set(records_by_url))
        if missing_urls:
            errors.append(
                "--final-record-json missing fixtures for required accepted "
                f"final-record bytes: {missing_urls}"
            )

    for target, url in sorted(
        finalized_record_urls_for_records(
            registry,
            release_tag=args.release_tag,
            required_targets=required_targets,
        ).items()
    ):
        url_key = normalize_url_key(url)
        if url_key in records_by_url:
            continue
        if not args.repository:
            continue
        expected_url = expected_finalized_record_release_url(
            args.repository,
            args.release_tag,
            target,
        )
        if url_key != expected_url:
            errors.append(
                f"{target} finalized accepted-record release asset URL must be {expected_url} "
                f"before live byte fetch, got {url_key!r}"
            )
            continue
        data, fetch_errors = fetch_bytes(url, timeout=args.timeout)
        if fetch_errors:
            errors.extend(fetch_errors)
            continue
        records_by_url[url_key] = data or b""
    return records_by_url, errors


def load_release_asset_bytes(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, bytes], list[str]]:
    configured_paths = release_asset_paths(args)
    assets_by_url: dict[str, bytes] = {}
    errors: list[str] = []
    for url, path in configured_paths.items():
        data, error = read_bytes_file(path, "--release-asset fixture")
        if error:
            errors.append(error)
            continue
        assets_by_url[url] = data or b""
    if not args.require_release_asset_bytes:
        return assets_by_url, errors
    expected_urls = expected_release_asset_byte_urls(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    unexpected_urls = sorted(set(configured_paths) - expected_urls)
    if unexpected_urls:
        errors.append(
            "--release-asset contains fixtures outside required release "
            f"asset byte scope: {unexpected_urls}"
        )
    if not args.repository:
        missing_urls = sorted(expected_urls - set(assets_by_url))
        if missing_urls:
            errors.append(
                "--release-asset missing fixtures for required release asset bytes: "
                f"{missing_urls}"
            )

    for target, record in sorted(
        accepted_records_by_target(
            registry,
            release_tag=args.release_tag,
            targets=required_targets,
        ).items()
    ):
        for asset in expected_release_asset_byte_sources(record):
            url = asset.get("url")
            filename = str(asset.get("filename", ""))
            if not url:
                continue
            url_key = normalize_url_key(str(url))
            if url_key in assets_by_url:
                continue
            if not args.repository:
                continue
            expected_url = expected_release_asset_url(
                args.repository,
                args.release_tag,
                filename,
            )
            if url_key != expected_url:
                errors.append(
                    f"{target} release asset {filename} URL must be {expected_url} "
                    f"before live byte fetch, got {url_key!r}"
                )
                continue
            data, fetch_errors = fetch_bytes(url_key, timeout=args.timeout)
            if fetch_errors:
                errors.extend(fetch_errors)
                continue
            assets_by_url[url_key] = data or b""
    return assets_by_url, errors


def load_release_tag_data(
    args: argparse.Namespace,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    if not args.require_tag_source_head:
        return None, None, []
    errors: list[str] = []
    tag_ref: dict[str, Any] | None
    if args.tag_ref_json:
        tag_ref, error = read_json_file(args.tag_ref_json, "--tag-ref-json fixture")
        if error:
            errors.append(error)
    elif args.repository:
        url = f"{GITHUB_API}/repos/{args.repository}/git/ref/tags/{quote(args.release_tag, safe='')}"
        tag_ref, fetch_errors = fetch_json(url, timeout=args.timeout)
        errors.extend(fetch_errors)
    else:
        tag_ref = None
    tag_object: dict[str, Any] | None = None
    object_record = tag_ref.get("object") if isinstance(tag_ref, dict) else None
    object_type = object_record.get("type") if isinstance(object_record, dict) else None
    object_sha = object_record.get("sha") if isinstance(object_record, dict) else ""
    if object_type == "tag":
        if args.tag_object_json:
            tag_object, error = read_json_file(args.tag_object_json, "--tag-object-json fixture")
            if error:
                errors.append(error)
        elif args.repository and is_lower_git_sha(object_sha):
            url = f"{GITHUB_API}/repos/{args.repository}/git/tags/{quote(object_sha, safe='')}"
            tag_object, fetch_errors = fetch_json(url, timeout=args.timeout)
            errors.extend(fetch_errors)
        elif not args.repository:
            errors.append(
                f"release tag {args.release_tag} annotated tag object metadata missing "
                "for offline audit; supply --tag-object-json"
            )
    return tag_ref, tag_object, errors


def workflow_run_json_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.workflow_runs_json:
        text = str(raw)
        if "=" not in text:
            continue
        workflow, path = text.split("=", 1)
        paths[normalize_workflow_key(workflow)] = Path(path)
    return paths


def source_run_json_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.source_run_json:
        text = str(raw)
        if "=" not in text:
            continue
        run, path = text.split("=", 1)
        paths[run] = Path(path)
    return paths


def source_artifact_json_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.source_artifacts_json:
        text = str(raw)
        if "=" not in text:
            continue
        run, path = text.split("=", 1)
        paths[run] = Path(path)
    return paths


def source_artifact_zip_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.source_artifact_zip:
        text = str(raw)
        if "=" not in text:
            continue
        run, path = text.split("=", 1)
        paths[run] = Path(path)
    return paths


def final_record_json_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.final_record_json:
        text = str(raw)
        if "=" not in text:
            continue
        url, path = text.split("=", 1)
        paths[normalize_url_key(url)] = Path(path)
    return paths


def release_asset_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for raw in args.release_asset:
        text = str(raw)
        if "=" not in text:
            continue
        url, path = text.split("=", 1)
        paths[normalize_url_key(url)] = Path(path)
    return paths


def normalize_run_key(run: str) -> str:
    return str(run).strip().rstrip("/")


def normalize_workflow_key(workflow: str) -> str:
    return str(workflow).strip()


def normalize_url_key(url: str) -> str:
    return str(url).strip()


def expected_finalized_record_release_url(repository: str, release_tag: str, target: str) -> str:
    return (
        f"https://github.com/{repository}/releases/download/"
        f"{release_tag}/{accepted_record_source_file(target)}"
    )


def expected_release_asset_url(repository: str, release_tag: str, filename: str) -> str:
    return f"https://github.com/{repository}/releases/download/{release_tag}/{filename}"


def expected_release_asset_api_url(repository: str, asset_id: int) -> str:
    return f"{GITHUB_API}/repos/{repository}/releases/assets/{quote(str(asset_id), safe='')}"


def expected_release_api_url(repository: str, release_id: int) -> str:
    return f"{GITHUB_API}/repos/{repository}/releases/{quote(str(release_id), safe='')}"


def expected_release_assets_api_url(repository: str, release_id: int) -> str:
    return f"{expected_release_api_url(repository, release_id)}/assets"


def expected_release_html_url(repository: str, release_tag: str) -> str:
    return f"https://github.com/{repository}/releases/tag/{quote(release_tag, safe='')}"


def expected_release_upload_url(repository: str, release_id: int) -> str:
    return (
        f"https://uploads.github.com/repos/{repository}/releases/"
        f"{quote(str(release_id), safe='')}/assets{{?name,label}}"
    )


def repository_from_release_asset_url(url: Any) -> str:
    if not isinstance(url, str) or url != url.strip():
        return ""
    if not release_asset_url_filename(url):
        return ""
    match = GITHUB_RELEASE_ASSET_RE.fullmatch(url)
    if not match:
        return ""
    return match.group(1)


def read_json_file(path: object, label: str = "JSON fixture") -> tuple[dict[str, Any] | None, str | None]:
    path_errors = check_local_fixture_path(path, label)
    if path_errors:
        return None, path_errors[0]
    assert isinstance(path, Path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"failed to read JSON {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"JSON file must contain an object: {path}"
    return data, None


def check_local_fixture_path(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    errors = check_path_not_reserved_workspace_root(path_value, label)
    if errors:
        return errors
    if path_value.is_symlink():
        return [f"{label} path must not be a symlink: {path_value}"]
    return check_path_parent_symlinks(path_value, label)


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


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


def fetch_json(url: str, *, timeout: float) -> tuple[dict[str, Any] | None, list[str]]:
    request = Request(url, headers=github_api_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - exercised manually against live GitHub.
        return None, [fetch_error_message(url, exc)]
    if not isinstance(data, dict):
        return None, [f"GitHub API response must be a JSON object: {url}"]
    return data, []


def read_bytes_file(path: object, label: str = "byte fixture") -> tuple[bytes | None, str | None]:
    path_errors = check_local_fixture_path(path, label)
    if path_errors:
        return None, path_errors[0]
    assert isinstance(path, Path)
    try:
        return path.read_bytes(), None
    except OSError as exc:
        return None, f"failed to read bytes {path}: {exc}"


def fetch_bytes(url: str, *, timeout: float) -> tuple[bytes | None, list[str]]:
    request = Request(url, headers=github_api_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), []
    except Exception as exc:  # pragma: no cover - exercised manually against live GitHub.
        return None, [fetch_error_message(url, exc)]


def fetch_error_message(url: str, exc: Exception) -> str:
    message = f"failed to fetch {url}: {exc}"
    if github_rate_limit_error(exc):
        message += (
            "; GitHub API rate limit exceeded during live release evidence audit; "
            "set GH_TOKEN or GITHUB_TOKEN with contents:read and actions:read access, "
            "or wait for the rate limit reset"
        )
    return message


def github_rate_limit_error(exc: Exception) -> bool:
    if not isinstance(exc, HTTPError) or exc.code != 403:
        return False
    detail = str(exc).casefold()
    if "rate limit" in detail:
        return True
    remaining = http_error_header(exc, "x-ratelimit-remaining")
    return remaining == "0"


def http_error_header(exc: HTTPError, name: str) -> str | None:
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    try:
        value = headers.get(name) or headers.get(name.title())
    except AttributeError:
        value = None
    return str(value).strip() if value is not None else None


def github_api_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Codex"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def is_lower_git_sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def check_remote_platform_release_evidence(
    *,
    registry: dict[str, Any],
    promotion: dict[str, Any],
    release: dict[str, Any],
    workflow_runs_by_workflow: dict[str, dict[str, Any]],
    source_runs_by_run: dict[str, dict[str, Any]] | None = None,
    source_artifacts_by_run: dict[str, dict[str, Any]] | None = None,
    source_artifact_bytes_by_run: dict[str, bytes] | None = None,
    final_record_bytes_by_url: dict[str, bytes] | None = None,
    release_asset_bytes_by_url: dict[str, bytes] | None = None,
    tag_ref: dict[str, Any] | None = None,
    tag_object: dict[str, Any] | None = None,
    release_tag: str,
    required_targets: tuple[str, ...],
    require_source_runs: bool = False,
    require_source_artifact_bytes: bool = False,
    require_final_record_bytes: bool = False,
    require_release_asset_bytes: bool = False,
    require_tag_source_head: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_platform_verified_evidence(registry=registry))
    if required_targets:
        errors.extend(
            check_platform_verified_evidence(
                registry=registry,
                required_targets=required_targets,
                required_release_tag=release_tag,
                require_review_bundles=True,
            )
        )
    errors.extend(check_release_metadata(release, release_tag))
    release_assets = release_asset_names(release)
    release_assets_by_name, asset_metadata_errors = release_assets_by_name_checked(release)
    errors.extend(asset_metadata_errors)
    required_assets = required_release_assets_by_target(
        promotion,
        release_tag=release_tag,
        targets=required_targets,
    )
    errors.extend(
        check_unexpected_protected_release_assets(
            release_assets,
            expected_assets_by_target=required_assets,
            release_tag=release_tag,
        )
    )
    for target, filenames in required_assets.items():
        missing = sorted(filenames - release_assets)
        if missing:
            errors.append(
                f"{target} remote release {release_tag} missing protected evidence assets: {missing}"
            )
    records = accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    )
    if require_tag_source_head:
        errors.extend(
            check_release_tag_source_head(
                records,
                release_tag=release_tag,
                tag_ref=tag_ref,
                tag_object=tag_object,
            )
        )
    for target, record in records.items():
        errors.extend(
            check_published_release_asset_metadata(
                target,
                record,
                release_assets_by_name=release_assets_by_name,
                release_created_at=release.get("created_at"),
            )
        )
        if require_final_record_bytes:
            errors.extend(
                check_published_final_record_bytes(
                    target,
                    record,
                    final_record_bytes_by_url=final_record_bytes_by_url or {},
                )
            )
        if require_release_asset_bytes:
            errors.extend(
                check_published_release_asset_bytes(
                    target,
                    record,
                    release_asset_bytes_by_url=release_asset_bytes_by_url or {},
                    release_assets_by_name=release_assets_by_name,
                )
            )
            errors.extend(
                check_published_native_manifest_bytes(
                    target,
                    record,
                    release_asset_bytes_by_url=release_asset_bytes_by_url or {},
                )
            )
    if require_source_runs:
        for target in required_targets:
            record = records.get(target)
            if record is None:
                errors.append(f"{target} accepted evidence record missing; cannot verify release source run")
                errors.extend(
                    check_missing_record_source_workflow(
                        target,
                        workflow_runs_by_workflow,
                        release_tag=release_tag,
                    )
                )
                continue
            errors.extend(
                check_record_source_run(
                    target,
                    record,
                    workflow_runs_by_workflow,
                    source_runs_by_run=source_runs_by_run or {},
                )
            )
            errors.extend(
                check_record_source_artifact(
                    target,
                    record,
                    source_artifacts_by_run or {},
                    source_runs_by_run=source_runs_by_run or {},
                )
            )
            if require_source_artifact_bytes:
                errors.extend(
                    check_record_source_artifact_zip_bytes(
                        target,
                        record,
                        source_artifacts_by_run=source_artifacts_by_run or {},
                        source_artifact_bytes_by_run=source_artifact_bytes_by_run or {},
                    )
                )
    return errors


def check_missing_record_source_workflow(
    target: str,
    workflow_runs_by_workflow: dict[str, dict[str, Any]],
    *,
    release_tag: str,
) -> list[str]:
    workflow = release_source_workflow(target)
    runs_document = workflow_runs_by_workflow.get(workflow)
    if not isinstance(runs_document, dict):
        return [f"{target} source workflow runs missing for {workflow}; no accepted record can be verified"]
    runs = runs_document.get("workflow_runs")
    if not isinstance(runs, list):
        return [f"{target} source workflow runs for {workflow} must include workflow_runs list"]
    release_tag_dispatch_runs = [
        run for run in runs
        if isinstance(run, dict)
        and run.get("event") == "workflow_dispatch"
        and first_present(run, "head_branch", "headBranch") == release_tag
    ]
    if not release_tag_dispatch_runs:
        return [
            f"{target} source workflow {workflow} has no runs available for "
            f"release_tag {release_tag}; dispatch native evidence before accepting this target"
        ]
    return []


def check_release_metadata(release: dict[str, Any], release_tag: str) -> list[str]:
    errors: list[str] = []
    if release.get("tag_name") != release_tag:
        errors.append(f"remote release tag_name must be {release_tag}, got {release.get('tag_name')!r}")
    release_id = release.get("id")
    if not isinstance(release_id, int) or isinstance(release_id, bool) or release_id <= 0:
        errors.append(f"remote release {release_tag} id must be a positive integer, got {release_id!r}")
    else:
        repositories = release_repositories_from_assets(release)
        if len(repositories) > 1:
            errors.append(
                f"remote release {release_tag} assets must use one GitHub release repository, "
                f"got {sorted(repositories)}"
            )
        elif repositories:
            repository = next(iter(repositories))
            expected_url = expected_release_api_url(repository, release_id)
            if release.get("url") != expected_url:
                errors.append(
                    f"remote release {release_tag} url must be {expected_url!r}, "
                    f"got {release.get('url')!r}"
                )
            expected_html_url = expected_release_html_url(repository, release_tag)
            if release.get("html_url") != expected_html_url:
                errors.append(
                    f"remote release {release_tag} html_url must be {expected_html_url!r}, "
                    f"got {release.get('html_url')!r}"
                )
            expected_assets_url = expected_release_assets_api_url(repository, release_id)
            if release.get("assets_url") != expected_assets_url:
                errors.append(
                    f"remote release {release_tag} assets_url must be {expected_assets_url!r}, "
                    f"got {release.get('assets_url')!r}"
                )
            expected_upload_url = expected_release_upload_url(repository, release_id)
            if release.get("upload_url") != expected_upload_url:
                errors.append(
                    f"remote release {release_tag} upload_url must be {expected_upload_url!r}, "
                    f"got {release.get('upload_url')!r}"
                )
    if release.get("draft") is not False:
        errors.append(f"remote release {release_tag} must not be draft")
    if release.get("prerelease") is not False:
        errors.append(f"remote release {release_tag} must not be prerelease")
    created_at = parse_github_timestamp(release.get("created_at"))
    if created_at is None:
        errors.append(
            f"remote release {release_tag} created_at must be a GitHub ISO-8601 timestamp, "
            f"got {release.get('created_at')!r}"
        )
    published_at = parse_github_timestamp(release.get("published_at"))
    if published_at is None:
        errors.append(
            f"remote release {release_tag} published_at must be a GitHub ISO-8601 timestamp, "
            f"got {release.get('published_at')!r}"
        )
    if created_at is not None and published_at is not None and published_at < created_at:
        errors.append(
            f"remote release {release_tag} published_at must be at or after created_at "
            f"{release.get('created_at')}, got {release.get('published_at')!r}"
        )
    assets = release.get("assets")
    if not isinstance(assets, list):
        errors.append(f"remote release {release_tag} assets must be a list")
    return errors


def release_repositories_from_assets(release: dict[str, Any]) -> set[str]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return set()
    repositories: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        repository = repository_from_release_asset_url(asset.get("browser_download_url"))
        if repository:
            repositories.add(repository)
    return repositories


def release_asset_names(release: dict[str, Any]) -> set[str]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return set()
    names: set[str] = set()
    for asset in assets:
        if isinstance(asset, dict):
            name = asset.get("name")
            if isinstance(name, str) and name:
                names.add(name)
    return names


def release_assets_by_name_checked(
    release: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return {}, []
    by_name: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    case_groups: dict[str, set[str]] = {}
    errors: list[str] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"remote release asset at index {index} must be an object, got {asset!r}")
            continue
        name = asset.get("name")
        if not isinstance(name, str) or not name:
            errors.append(
                f"remote release asset at index {index} name must be a non-empty string, "
                f"got {name!r}"
            )
            continue
        if not exact_safe_file_name(name):
            errors.append(f"remote release asset name must be an exact safe file name: {name!r}")
        counts[name] = counts.get(name, 0) + 1
        case_groups.setdefault(name.casefold(), set()).add(name)
        by_name.setdefault(name, asset)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"remote release contains duplicate asset names: {duplicates}")
    case_collisions = sorted(
        {
            name
            for group in case_groups.values()
            if len(group) > 1
            for name in group
        }
    )
    if case_collisions:
        errors.append(
            f"remote release asset names must not collide on case-insensitive filesystems: {case_collisions}"
        )
    return by_name, errors


def check_unexpected_protected_release_assets(
    release_assets: set[str],
    *,
    expected_assets_by_target: dict[str, set[str]],
    release_tag: str,
) -> list[str]:
    expected_assets = set().union(*expected_assets_by_target.values()) if expected_assets_by_target else set()
    unexpected_by_target: dict[str, list[str]] = {}
    for asset in sorted(release_assets - expected_assets):
        for target in protected_release_asset_targets(asset):
            unexpected_by_target.setdefault(target, []).append(asset)
    return [
        (
            f"{target} remote release {release_tag} contains protected platform assets "
            f"not expected for this audited evidence scope: {assets}"
        )
        for target, assets in sorted(unexpected_by_target.items())
    ]


def protected_release_asset_targets(asset_name: str) -> set[str]:
    targets: set[str] = set()
    for target, patterns in PROTECTED_RELEASE_ASSET_PATTERNS.items():
        if any(re.search(pattern, asset_name) for pattern in patterns):
            targets.add(target)
    return targets


def check_published_release_asset_metadata(
    target: str,
    record: dict[str, Any],
    *,
    release_assets_by_name: dict[str, dict[str, Any]],
    release_created_at: Any = None,
) -> list[str]:
    errors: list[str] = []
    for filename, expected in sorted(expected_published_assets(record).items()):
        asset = release_assets_by_name.get(filename)
        if not isinstance(asset, dict):
            continue
        errors.extend(
            check_published_release_asset_timestamps(
                target,
                filename,
                asset,
                release_created_at=release_created_at,
            )
        )
        if asset.get("state") != "uploaded":
            errors.append(
                f"{target} remote release asset {filename} state must be uploaded, "
                f"got {asset.get('state')!r}"
            )
        node_id = asset.get("node_id")
        if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
            errors.append(
                f"{target} remote release asset {filename} node_id must be a non-empty string, "
                f"got {node_id!r}"
            )
        content_type = asset.get("content_type")
        if (
            not isinstance(content_type, str)
            or not content_type
            or content_type != content_type.strip()
        ):
            errors.append(
                f"{target} remote release asset {filename} content_type must be a non-empty string, "
                f"got {content_type!r}"
            )
        download_count = asset.get("download_count")
        if (
            not isinstance(download_count, int)
            or isinstance(download_count, bool)
            or download_count < 0
        ):
            errors.append(
                f"{target} remote release asset {filename} download_count "
                f"must be a non-negative integer, got {download_count!r}"
            )
        expected_url = expected.get("browser_download_url")
        if expected_url and asset.get("browser_download_url") != expected_url:
            errors.append(
                f"{target} remote release asset {filename} browser_download_url must be "
                f"{expected_url!r}, got {asset.get('browser_download_url')!r}"
            )
        asset_id = asset.get("id")
        if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id <= 0:
            errors.append(
                f"{target} remote release asset {filename} id must be a positive integer, "
                f"got {asset_id!r}"
            )
        elif expected_url:
            repository = repository_from_release_asset_url(expected_url)
            if repository:
                expected_api_url = expected_release_asset_api_url(repository, asset_id)
                if asset.get("url") != expected_api_url:
                    errors.append(
                        f"{target} remote release asset {filename} url must be "
                        f"{expected_api_url!r}, got {asset.get('url')!r}"
                    )
        expected_sha = expected.get("sha256")
        if expected_sha:
            expected_digest = f"sha256:{expected_sha}"
            if asset.get("digest") != expected_digest:
                errors.append(
                    f"{target} remote release asset {filename} digest must be "
                    f"{expected_digest}, got {asset.get('digest')!r}"
                )
        asset_size = asset.get("size")
        if not isinstance(asset_size, int) or isinstance(asset_size, bool) or asset_size <= 0:
            errors.append(
                f"{target} remote release asset {filename} size must be a positive integer, "
                f"got {asset_size!r}"
            )
        expected_size = expected.get("size")
        if expected_size is not None and asset_size != expected_size:
            errors.append(
                f"{target} remote release asset {filename} size must be "
                f"{expected_size}, got {asset_size!r}"
            )
    return errors


def check_published_release_asset_timestamps(
    target: str,
    filename: str,
    asset: dict[str, Any],
    *,
    release_created_at: Any = None,
) -> list[str]:
    errors: list[str] = []
    raw_created_at = asset.get("created_at")
    raw_updated_at = asset.get("updated_at")
    created_at = parse_github_timestamp(raw_created_at)
    updated_at = parse_github_timestamp(raw_updated_at)
    parsed_release_created_at = parse_github_timestamp(release_created_at)
    if created_at is None:
        errors.append(
            f"{target} remote release asset {filename} created_at "
            f"must be a GitHub ISO-8601 timestamp, got {raw_created_at!r}"
        )
    if updated_at is None:
        errors.append(
            f"{target} remote release asset {filename} updated_at "
            f"must be a GitHub ISO-8601 timestamp, got {raw_updated_at!r}"
        )
    if created_at is not None and updated_at is not None and updated_at < created_at:
        errors.append(
            f"{target} remote release asset {filename} updated_at "
            f"must be at or after created_at {raw_created_at}, got {raw_updated_at!r}"
        )
    if (
        created_at is not None
        and parsed_release_created_at is not None
        and created_at < parsed_release_created_at
    ):
        errors.append(
            f"{target} remote release asset {filename} created_at "
            f"must be at or after release created_at {release_created_at}, got {raw_created_at!r}"
        )
    return errors


def check_published_final_record_bytes(
    target: str,
    record: dict[str, Any],
    *,
    final_record_bytes_by_url: dict[str, bytes],
) -> list[str]:
    url = record.get("finalized_record_release_asset_url")
    if not isinstance(url, str) or not url.strip():
        return [f"{target} finalized accepted-record release asset URL must be set"]
    if not canonical_release_asset_fixture_url(url):
        return [
            f"{target} finalized accepted-record release asset URL must be a canonical GitHub "
            f"release asset URL before byte verification, got {url!r}"
        ]
    url_key = normalize_url_key(url)
    published_bytes = final_record_bytes_by_url.get(url_key)
    if published_bytes is None:
        return [f"{target} finalized accepted-record release asset bytes missing for {url_key}"]
    expected_bytes = canonical_public_record_bytes(record)
    if published_bytes != expected_bytes:
        return [
            f"{target} finalized accepted-record release asset bytes must match "
            "canonical public accepted registry record"
        ]
    return []


def check_published_release_asset_bytes(
    target: str,
    record: dict[str, Any],
    *,
    release_asset_bytes_by_url: dict[str, bytes],
    release_assets_by_name: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    release_assets_by_name = release_assets_by_name or {}
    for asset in expected_release_asset_byte_sources(record):
        filename = str(asset.get("filename", ""))
        url = asset.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{target} release asset {filename} URL must be set before byte verification")
            continue
        if not canonical_release_asset_fixture_url(url):
            errors.append(
                f"{target} release asset {filename} URL must be a canonical GitHub release asset URL "
                f"before byte verification, got {url!r}"
            )
            continue
        url_key = normalize_url_key(url)
        published_bytes = release_asset_bytes_by_url.get(url_key)
        if published_bytes is None:
            errors.append(f"{target} published release asset bytes missing for {filename} at {url_key}")
            continue
        expected_sha = asset.get("sha256", "")
        actual_sha = hashlib.sha256(published_bytes).hexdigest()
        if not lowercase_sha256_hex(expected_sha):
            errors.append(
                f"{target} published release asset {filename} accepted evidence sha256 "
                "must be a lowercase SHA-256 hex digest"
            )
        elif actual_sha != expected_sha:
            errors.append(
                f"{target} published release asset {filename} bytes SHA-256 must match "
                f"accepted evidence {expected_sha}, got {actual_sha}"
            )
        metadata = release_assets_by_name.get(filename)
        metadata_size = metadata.get("size") if isinstance(metadata, dict) else None
        if metadata_size is not None and len(published_bytes) != metadata_size:
            errors.append(
                f"{target} published release asset {filename} byte size must match "
                f"remote release metadata {metadata_size}, got {len(published_bytes)}"
            )
        expected_size = asset.get("size")
        if expected_size is not None:
            if not positive_int(expected_size):
                errors.append(
                    f"{target} published release asset {filename} accepted evidence size "
                    "must be a positive integer"
                )
            elif len(published_bytes) != expected_size:
                errors.append(
                    f"{target} published release asset {filename} byte size must match "
                    f"accepted evidence {expected_size}, got {len(published_bytes)}"
                )
    return errors


def check_published_native_manifest_bytes(
    target: str,
    record: dict[str, Any],
    *,
    release_asset_bytes_by_url: dict[str, bytes],
) -> list[str]:
    sources_by_filename = {
        str(asset.get("filename", "")): asset
        for asset in expected_release_asset_byte_sources(record)
        if asset.get("filename")
    }
    artifact_hashes = record.get("artifact_sha256")
    if not isinstance(artifact_hashes, dict):
        return [f"{target} accepted evidence artifact_sha256 must be an object for native manifest byte audit"]
    manifest_names = sorted(name for name in artifact_hashes if str(name).endswith(MANIFEST_SUFFIX))
    if len(manifest_names) != 1:
        return [f"{target} published native manifest byte audit requires exactly one native manifest, got {manifest_names}"]
    manifest_name = str(manifest_names[0])
    manifest_source = sources_by_filename.get(manifest_name, {})
    manifest_url = manifest_source.get("url")
    if not isinstance(manifest_url, str) or not manifest_url.strip():
        return [f"{target} published native manifest {manifest_name} URL must be set before byte verification"]
    if not canonical_release_asset_fixture_url(manifest_url):
        return [
            f"{target} published native manifest {manifest_name} URL must be a canonical GitHub "
            f"release asset URL before byte verification, got {manifest_url!r}"
        ]
    manifest_bytes = release_asset_bytes_by_url.get(normalize_url_key(manifest_url))
    if manifest_bytes is None:
        return [f"{target} published native manifest bytes missing for {manifest_name} at {manifest_url}"]
    try:
        raw_manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} published native manifest {manifest_name} is not UTF-8 JSON: {exc}"]
    records = manifest_records(raw_manifest)
    if records is None:
        return [f"{target} published native manifest {manifest_name} must be a list or contain an artifacts list"]

    expected_payloads = {
        str(name)
        for name in artifact_hashes
        if not str(name).endswith(CHECKSUM_SUFFIX) and not str(name).endswith(MANIFEST_SUFFIX)
    }
    record_counts: dict[str, int] = {}
    records_by_name: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for raw_record in records:
        filename = manifest_record_filename(raw_record)
        if not filename:
            errors.append(f"{target} published native manifest {manifest_name} contains record without file/path/name")
            continue
        if not artifact_reference_name_is_safe(filename):
            errors.append(
                f"{target} published native manifest {manifest_name} record file/path/name "
                f"must be an exact safe file name: {filename!r}"
            )
            continue
        record_counts[filename] = record_counts.get(filename, 0) + 1
        records_by_name[filename] = raw_record

    missing = sorted(expected_payloads - set(records_by_name))
    if missing:
        errors.append(f"{target} published native manifest {manifest_name} missing payload records: {missing}")
    extra = sorted(set(records_by_name) - expected_payloads)
    if extra:
        errors.append(f"{target} published native manifest {manifest_name} contains unexpected payload records: {extra}")
    duplicates = sorted(name for name, count in record_counts.items() if count > 1)
    if duplicates:
        errors.append(f"{target} published native manifest {manifest_name} contains duplicate payload records: {duplicates}")
    case_collisions = case_insensitive_name_collisions(set(record_counts))
    if case_collisions:
        errors.append(
            f"{target} published native manifest {manifest_name} payload records must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )

    for filename in sorted(expected_payloads & set(records_by_name)):
        raw_record = records_by_name[filename]
        source = sources_by_filename.get(filename, {})
        url = source.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{target} published native manifest {manifest_name} payload {filename} URL must be set")
            continue
        if not canonical_release_asset_fixture_url(url):
            errors.append(
                f"{target} published native manifest {manifest_name} payload {filename} URL must be "
                f"a canonical GitHub release asset URL before byte verification, got {url!r}"
            )
            continue
        published_bytes = release_asset_bytes_by_url.get(normalize_url_key(url))
        if published_bytes is None:
            errors.append(
                f"{target} published native manifest {manifest_name} payload {filename} bytes missing at {url}"
            )
            continue
        expected_size = raw_record.get("size_bytes")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size <= 0:
            errors.append(
                f"{target} published native manifest record {filename} size_bytes must be a positive integer"
            )
        elif len(published_bytes) != expected_size:
            errors.append(
                f"{target} published native manifest record {filename} size_bytes must match "
                f"published asset bytes, got {expected_size} vs {len(published_bytes)}"
            )
        expected_sha = raw_record.get("sha256")
        if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            errors.append(
                f"{target} published native manifest record {filename} "
                "sha256 must be a lowercase SHA-256 hex digest"
            )
        elif hashlib.sha256(published_bytes).hexdigest() != expected_sha:
            errors.append(
                f"{target} published native manifest record {filename} sha256 must match published asset bytes"
            )
        expected_architecture = expected_manifest_architecture(target, filename)
        if expected_architecture:
            raw_architecture = raw_record.get("architecture")
            if not isinstance(raw_architecture, str) or raw_architecture != expected_architecture:
                errors.append(
                    f"{target} published native manifest record {filename} architecture must be "
                    f"{expected_architecture!r}, got {raw_architecture!r}"
                )
        expected_format = expected_manifest_format(filename)
        if expected_format:
            raw_format = raw_record.get("format")
            if not isinstance(raw_format, str) or raw_format != expected_format:
                errors.append(
                    f"{target} published native manifest record {filename} format must be "
                    f"{expected_format!r}, got {raw_format!r}"
                )
    return errors


def expected_release_asset_byte_sources(record: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    artifact_hashes = record.get("artifact_sha256")
    release_urls = release_urls_by_filename(record.get("release_asset_urls"))
    if isinstance(artifact_hashes, dict):
        for name, digest in sorted(
            (
                (filename, digest)
                for filename, digest in artifact_hashes.items()
                if isinstance(filename, str) and exact_safe_file_name(filename)
            ),
            key=lambda item: item[0],
        ):
            sources.append(
                {
                    "filename": name,
                    "url": release_urls.get(name),
                    "sha256": digest if isinstance(digest, str) else "",
                }
            )
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_urls = release_urls_by_filename(review_bundle.get("release_asset_urls"))
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = bundle_record.get("file", "")
            if not isinstance(filename, str) or not exact_safe_file_name(filename):
                continue
            sources.append(
                {
                    "filename": filename,
                    "url": review_urls.get(filename),
                    "sha256": bundle_record.get("sha256", "")
                    if isinstance(bundle_record.get("sha256", ""), str)
                    else "",
                    "size": bundle_record.get("size_bytes"),
                }
            )
    return sources


def expected_final_record_byte_urls(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> set[str]:
    return {
        normalize_url_key(url)
        for url in finalized_record_urls_for_records(
            registry,
            release_tag=release_tag,
            required_targets=required_targets,
        ).values()
    }


def expected_release_asset_byte_urls(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> set[str]:
    urls: set[str] = set()
    for record in accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    ).values():
        for asset in expected_release_asset_byte_sources(record):
            url = asset.get("url")
            if isinstance(url, str) and url.strip():
                urls.add(normalize_url_key(url))
    return urls


def expected_published_assets(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    target = accepted_record_target(record)
    artifact_hashes = record.get("artifact_sha256")
    release_urls = release_urls_by_filename(record.get("release_asset_urls"))
    if isinstance(artifact_hashes, dict):
        for name, digest in sorted(
            (
                (filename, digest)
                for filename, digest in artifact_hashes.items()
                if isinstance(filename, str) and exact_safe_file_name(filename)
            ),
            key=lambda item: item[0],
        ):
            expected[name] = {
                "browser_download_url": release_urls.get(name),
                "sha256": digest if isinstance(digest, str) else "",
            }
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_urls = release_urls_by_filename(review_bundle.get("release_asset_urls"))
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = bundle_record.get("file", "")
            if not isinstance(filename, str) or not exact_safe_file_name(filename):
                continue
            expected[filename] = {
                "browser_download_url": review_urls.get(filename),
                "sha256": bundle_record.get("sha256", "")
                if isinstance(bundle_record.get("sha256", ""), str)
                else "",
                "size": bundle_record.get("size_bytes"),
            }
    finalized_url = record.get("finalized_record_release_asset_url")
    if isinstance(finalized_url, str):
        filename = release_asset_url_filename(finalized_url)
        if filename:
            final_bytes = canonical_public_record_bytes(record)
            expected[filename] = {
                "browser_download_url": finalized_url,
                "sha256": hashlib.sha256(final_bytes).hexdigest(),
                "size": len(final_bytes),
            }
    elif target:
        expected.setdefault(accepted_record_source_file(target), {})
    return expected


def release_urls_by_filename(raw_urls: Any) -> dict[str, str]:
    if not isinstance(raw_urls, list):
        return {}
    urls: dict[str, str] = {}
    for raw_url in raw_urls:
        if not isinstance(raw_url, str):
            continue
        url = raw_url
        filename = release_asset_url_filename(url)
        if filename:
            urls[filename] = url
    return urls


def required_release_assets_by_target(
    promotion: dict[str, Any],
    *,
    release_tag: str,
    targets: tuple[str, ...],
) -> dict[str, set[str]]:
    entries = promotion_entries_by_id(promotion)
    return {
        target: required_release_assets_for_target(entries, target, release_tag)
        for target in targets
    }


def required_release_assets_for_target(
    promotion_entries: dict[str, dict[str, Any]],
    target: str,
    release_tag: str,
) -> set[str]:
    assets = set(accepted_artifact_names(target, release_tag, promotion_entries))
    assets.update(review_bundle_expected_files(target, release_tag).values())
    assets.add(accepted_record_source_file(target))
    return assets


def promotion_entries_by_id(promotion: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = promotion.get("protected_targets", [])
    if not isinstance(rows, list):
        return {}
    return {
        target_id: row
        for row in rows
        if isinstance(row, dict)
        and isinstance(target_id := row.get("id"), str)
        and target_id
        and target_id == target_id.strip()
    }


def accepted_records_by_target(
    registry: dict[str, Any],
    *,
    release_tag: str,
    targets: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    target_set = set(targets)
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return {}
    return {
        target: row
        for row in rows
        if isinstance(row, dict)
        and (target := accepted_record_target(row)) in target_set
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == release_tag
    }


def accepted_record_target(record: dict[str, Any]) -> str:
    target = record.get("target")
    if not isinstance(target, str) or not target or target != target.strip():
        return ""
    return target


def check_release_tag_source_head(
    records_by_target: dict[str, dict[str, Any]],
    *,
    release_tag: str,
    tag_ref: dict[str, Any] | None,
    tag_object: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    expected_heads, head_errors = accepted_release_source_heads(records_by_target)
    errors.extend(head_errors)
    if len(expected_heads) == 0:
        errors.append(
            f"release tag {release_tag} source-head audit requires accepted "
            "release_asset_source.head_sha values"
        )
    elif len(expected_heads) > 1:
        errors.append(
            f"release tag {release_tag} source-head audit requires one accepted "
            f"source head SHA, got {expected_heads}"
        )
    tag_head, tag_errors = release_tag_resolved_head(
        tag_ref,
        tag_object=tag_object,
        release_tag=release_tag,
    )
    errors.extend(tag_errors)
    if len(expected_heads) == 1 and tag_head is not None and tag_head != expected_heads[0]:
        errors.append(
            f"remote release tag {release_tag} Git object must resolve to accepted "
            f"release source head {expected_heads[0]}, got {tag_head}"
        )
    return errors


def accepted_release_source_heads(
    records_by_target: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    heads: set[str] = set()
    for target, record in sorted(records_by_target.items()):
        source = record.get("release_asset_source")
        if not isinstance(source, dict):
            errors.append(f"{target} release_asset_source must be an object for release tag audit")
            continue
        head_sha = source.get("head_sha")
        if not isinstance(head_sha, str) or head_sha != head_sha.strip() or not is_lower_git_sha(head_sha):
            errors.append(
                f"{target} release_asset_source.head_sha must be a 40-character "
                "lowercase Git SHA for release tag audit"
            )
            continue
        heads.add(head_sha)
    return sorted(heads), errors


def release_tag_resolved_head(
    tag_ref: dict[str, Any] | None,
    *,
    tag_object: dict[str, Any] | None,
    release_tag: str,
) -> tuple[str | None, list[str]]:
    if not isinstance(tag_ref, dict):
        return None, [f"release tag {release_tag} ref metadata missing for source-head audit"]
    errors: list[str] = []
    expected_ref = f"refs/tags/{release_tag}"
    if tag_ref.get("ref") != expected_ref:
        errors.append(f"release tag ref must be {expected_ref!r}, got {tag_ref.get('ref')!r}")
    raw_object = tag_ref.get("object")
    if not isinstance(raw_object, dict):
        return None, [*errors, f"release tag {release_tag} ref object must be an object"]
    object_type = raw_object.get("type")
    object_sha = raw_object.get("sha")
    if not is_lower_git_sha(object_sha):
        errors.append(
            f"release tag {release_tag} ref object.sha must be a 40-character lowercase Git SHA"
        )
    valid_object_sha = object_sha if is_lower_git_sha(object_sha) else None
    if object_type == "commit":
        return valid_object_sha, errors
    if object_type != "tag":
        errors.append(f"release tag {release_tag} ref object.type must be commit or tag, got {object_type!r}")
        return None, errors
    if not isinstance(tag_object, dict):
        return None, [
            *errors,
            f"release tag {release_tag} annotated tag object metadata missing for {object_sha}",
        ]
    tag_object_sha = tag_object.get("sha")
    if not is_lower_git_sha(tag_object_sha):
        errors.append(
            f"release tag {release_tag} annotated tag object sha must be a "
            "40-character lowercase Git SHA"
        )
    elif valid_object_sha is not None and tag_object_sha != valid_object_sha:
        errors.append(
            f"release tag {release_tag} annotated tag object sha must match ref object "
            f"{valid_object_sha}, got {tag_object_sha}"
        )
    if tag_object.get("tag") != release_tag:
        errors.append(
            f"release tag {release_tag} annotated tag object tag must be {release_tag!r}, "
            f"got {tag_object.get('tag')!r}"
        )
    raw_target = tag_object.get("object")
    if not isinstance(raw_target, dict):
        return None, [*errors, f"release tag {release_tag} annotated tag object.object must be an object"]
    if raw_target.get("type") != "commit":
        errors.append(
            f"release tag {release_tag} annotated tag object target type must be commit, "
            f"got {raw_target.get('type')!r}"
        )
    commit_sha = raw_target.get("sha")
    if not is_lower_git_sha(commit_sha):
        errors.append(
            f"release tag {release_tag} annotated tag target sha must be a "
            "40-character lowercase Git SHA"
        )
        return None, errors
    return commit_sha, errors


def finalized_record_urls_for_records(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> dict[str, str]:
    urls: dict[str, str] = {}
    for record in accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    ).values():
        target = accepted_record_target(record)
        url = record.get("finalized_record_release_asset_url")
        if target and isinstance(url, str) and url.strip():
            urls[target] = url.strip()
    return urls


def source_workflows_for_records(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> set[str]:
    workflows: set[str] = set()
    for record in accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    ).values():
        source = record.get("release_asset_source")
        if isinstance(source, dict):
            workflow = source.get("workflow")
            if isinstance(workflow, str) and workflow.strip():
                workflow = workflow.strip()
                workflows.add(workflow)
    return workflows


def source_run_urls_for_records(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> set[str]:
    urls: set[str] = set()
    for record in accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    ).values():
        source = record.get("release_asset_source")
        if isinstance(source, dict):
            run_url = source.get("workflow_run_url")
            if isinstance(run_url, str) and run_url.strip():
                if run_url == run_url.strip() and run_url == run_url.rstrip("/"):
                    urls.add(run_url)
    return urls


def expected_source_run_fixture_keys(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
) -> set[str]:
    keys: set[str] = set()
    for run_url in source_run_urls_for_records(
        registry,
        release_tag=release_tag,
        required_targets=required_targets,
    ):
        run_key = normalize_run_key(run_url)
        if run_key:
            keys.add(run_key)
            keys.add(run_key.rsplit("/", 1)[-1])
    return keys


def source_run_alias_fixture_errors(
    documents_by_run: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
    flag: str,
) -> list[str]:
    errors: list[str] = []
    for run_url in sorted(
        source_run_urls_for_records(
            registry,
            release_tag=release_tag,
            required_targets=required_targets,
        )
    ):
        run_key = normalize_run_key(run_url)
        aliases = source_run_aliases(documents_by_run, run_key)
        if len(aliases) > 1:
            errors.append(
                f"{flag} contains ambiguous aliases for accepted source run "
                f"{run_key}: {aliases}"
            )
    return errors


def source_run_aliases(documents_by_run: dict[str, Any], run_key: str) -> list[str]:
    run_id = run_key.rsplit("/", 1)[-1] if run_key else ""
    return [alias for alias in (run_key, run_id) if alias and alias in documents_by_run]


def missing_source_run_fixture_errors(
    documents_by_run: dict[str, dict[str, Any]],
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
    flag: str,
) -> list[str]:
    missing: list[str] = []
    for run_url in sorted(
        source_run_urls_for_records(
            registry,
            release_tag=release_tag,
            required_targets=required_targets,
        )
    ):
        run_key = normalize_run_key(run_url)
        run_id = run_key.rsplit("/", 1)[-1] if run_key else ""
        if (run_key and run_key in documents_by_run) or (run_id and run_id in documents_by_run):
            continue
        missing.append(run_key)
    if missing:
        return [
            f"{flag} missing fixtures for required accepted source runs: {missing}"
        ]
    return []


def source_run_attempt_for_url(
    registry: dict[str, Any],
    *,
    release_tag: str,
    required_targets: tuple[str, ...],
    run_url: str,
) -> int | None:
    normalized = normalize_run_key(run_url)
    for record in accepted_records_by_target(
        registry,
        release_tag=release_tag,
        targets=required_targets,
    ).values():
        source = record.get("release_asset_source")
        if not isinstance(source, dict):
            continue
        source_run_url_raw = source.get("workflow_run_url")
        if not isinstance(source_run_url_raw, str):
            continue
        if (
            source_run_url_raw != source_run_url_raw.strip()
            or source_run_url_raw != source_run_url_raw.rstrip("/")
        ):
            continue
        source_run_url = source_run_url_raw
        if source_run_url != normalized:
            continue
        attempt = source.get("run_attempt")
        if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0:
            return attempt
    return None


def source_run_api_url(repository: str, run_id: str | int) -> str:
    return f"{GITHUB_API}/repos/{repository}/actions/runs/{quote(str(run_id), safe='')}"


def workflow_runs_api_url(repository: str, workflow: str, release_tag: str) -> str:
    workflow_file = quote(Path(workflow).name, safe="")
    ref_name = quote(release_tag, safe="")
    return (
        f"{GITHUB_API}/repos/{repository}/actions/workflows/{workflow_file}/runs"
        f"?branch={ref_name}&event=workflow_dispatch&per_page=100"
    )


def source_run_child_api_url(repository: str, run_id: str | int, endpoint: str) -> str:
    return f"{source_run_api_url(repository, run_id)}/{quote(endpoint, safe='')}"


def source_run_attempt_api_url(repository: str, run_id: str, run_attempt: int) -> str:
    return (
        f"{source_run_api_url(repository, run_id)}"
        f"/attempts/{quote(str(run_attempt), safe='')}"
    )


def source_workflow_api_url(repository: str, workflow_id: str | int) -> str:
    return f"{GITHUB_API}/repos/{repository}/actions/workflows/{quote(str(workflow_id), safe='')}"


def check_suite_api_url(repository: str, check_suite_id: str | int) -> str:
    return f"{GITHUB_API}/repos/{repository}/check-suites/{quote(str(check_suite_id), safe='')}"


def source_artifact_api_url(repository: str, artifact_id: int) -> str:
    return f"{GITHUB_API}/repos/{repository}/actions/artifacts/{quote(str(artifact_id), safe='')}"


def check_record_source_run(
    target: str,
    record: dict[str, Any],
    workflow_runs_by_workflow: dict[str, dict[str, Any]],
    *,
    source_runs_by_run: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    source_values, source_errors = source_run_expected_values(target, source)
    if source_errors:
        return source_errors
    workflow = source_values["workflow"]
    run_url = source_values["workflow_run_url"]
    run_id = run_url.rsplit("/", 1)[-1] if run_url else ""
    source_run_aliases_present = source_run_aliases(source_runs_by_run or {}, normalize_run_key(run_url))
    if len(source_run_aliases_present) > 1:
        return [
            f"{target} exact source workflow run metadata contains ambiguous aliases for "
            f"accepted source run {run_url}: {source_run_aliases_present}"
        ]
    exact_run = exact_source_run_document(run_url, source_runs_by_run or {})
    if isinstance(exact_run, dict):
        return check_source_run_record(target, exact_run, record)
    if source_runs_by_run and not workflow_runs_by_workflow:
        return [f"{target} exact source workflow run metadata missing for {run_url}"]
    runs_document = workflow_runs_by_workflow.get(workflow)
    if not isinstance(runs_document, dict):
        return [f"{target} source workflow runs missing for {workflow}"]
    runs = runs_document.get("workflow_runs")
    if not isinstance(runs, list):
        return [f"{target} source workflow runs for {workflow} must include workflow_runs list"]
    matches = [
        run for run in runs
        if isinstance(run, dict)
        and (
            str(run.get("id", "")) == run_id
            or str(run.get("html_url", "")) == run_url
        )
    ]
    if len(matches) != 1:
        return [
            f"{target} source workflow runs for {workflow} must contain exactly one "
            f"run {run_url}, got {len(matches)}"
        ]
    return check_source_run_record(target, matches[0], record)


def exact_source_run_document(
    run_url: str,
    source_runs_by_run: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not source_runs_by_run:
        return None
    run_key = normalize_run_key(run_url)
    aliases = source_run_aliases(source_runs_by_run, run_key)
    document = source_runs_by_run.get(aliases[0]) if aliases else None
    return document if isinstance(document, dict) else None


def check_source_run_record(
    target: str,
    run: dict[str, Any],
    record: dict[str, Any],
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    source_values, errors = source_run_expected_values(target, source)
    expected_run_url = source_values.get("workflow_run_url", "")
    expected_run_id = expected_run_url.rsplit("/", 1)[-1] if expected_run_url else ""
    expected_run_id_int = int(expected_run_id) if expected_run_id.isdecimal() else None
    run_id = run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        errors.append(
            f"{target} source workflow run id must be a positive integer, got {run_id!r}"
        )
    elif expected_run_id_int is not None and run_id != expected_run_id_int:
        errors.append(
            f"{target} source workflow run id must match accepted record "
            f"{expected_run_id}, got {run_id!r}"
        )
    actual_url = str(first_present(run, "html_url", "htmlUrl") or "")
    if actual_url != expected_run_url:
        errors.append(
            f"{target} source workflow run html_url must match accepted record "
            f"{expected_run_url}, got {first_present(run, 'html_url', 'htmlUrl')!r}"
        )
    expected_repository = repository_from_run_url(expected_run_url)
    api_url = first_present(run, "url", "api_url", "apiUrl")
    if expected_repository and expected_run_id_int is not None:
        expected_api_url = source_run_api_url(expected_repository, expected_run_id_int)
        if api_url != expected_api_url:
            errors.append(
                f"{target} source workflow run url must be {expected_api_url!r}, "
                f"got {api_url!r}"
            )
    node_id = first_present(run, "node_id", "nodeId")
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
        errors.append(f"{target} source workflow run node_id must be a non-empty string, got {node_id!r}")
    run_number = first_present(run, "run_number", "runNumber")
    if not isinstance(run_number, int) or isinstance(run_number, bool) or run_number <= 0:
        errors.append(
            f"{target} source workflow run run_number must be a positive integer, got {run_number!r}"
        )
    workflow_id = first_present(run, "workflow_id", "workflowId")
    if not isinstance(workflow_id, int) or isinstance(workflow_id, bool) or workflow_id <= 0:
        errors.append(
            f"{target} source workflow run workflow_id must be a positive integer, got {workflow_id!r}"
        )
    elif expected_repository:
        expected_workflow_url = source_workflow_api_url(expected_repository, workflow_id)
        workflow_url = first_present(run, "workflow_url", "workflowUrl")
        if workflow_url != expected_workflow_url:
            errors.append(
                f"{target} source workflow run workflow_url must be {expected_workflow_url!r}, "
                f"got {workflow_url!r}"
            )
    if expected_repository and expected_run_id_int is not None:
        for field, camel_field, endpoint in (
            ("jobs_url", "jobsUrl", "jobs"),
            ("logs_url", "logsUrl", "logs"),
            ("artifacts_url", "artifactsUrl", "artifacts"),
        ):
            expected_endpoint_url = source_run_child_api_url(
                expected_repository,
                expected_run_id_int,
                endpoint,
            )
            endpoint_url = first_present(run, field, camel_field)
            if endpoint_url != expected_endpoint_url:
                errors.append(
                    f"{target} source workflow run {field} must be {expected_endpoint_url!r}, "
                    f"got {endpoint_url!r}"
                )
    check_suite_id = first_present(run, "check_suite_id", "checkSuiteId")
    if not isinstance(check_suite_id, int) or isinstance(check_suite_id, bool) or check_suite_id <= 0:
        errors.append(
            f"{target} source workflow run check_suite_id must be a positive integer, got {check_suite_id!r}"
        )
    elif expected_repository:
        expected_check_suite_url = check_suite_api_url(expected_repository, check_suite_id)
        check_suite_url = first_present(run, "check_suite_url", "checkSuiteUrl")
        if check_suite_url != expected_check_suite_url:
            errors.append(
                f"{target} source workflow run check_suite_url must be {expected_check_suite_url!r}, "
                f"got {check_suite_url!r}"
            )
    for field in ("repository", "head_repository"):
        actual_repository = nested_full_name(run, field)
        if actual_repository != expected_repository:
            errors.append(
                f"{target} source workflow run {field}.full_name must match accepted record "
                f"{expected_repository}, got {actual_repository!r}"
            )
        raw_record = run.get(field)
        raw_id = raw_record.get("id") if isinstance(raw_record, dict) else None
        if nested_positive_int(run, field, "id") is None:
            errors.append(
                f"{target} source workflow run {field}.id must be a positive integer, "
                f"got {raw_id!r}"
            )
    if run.get("status") != "completed":
        errors.append(f"{target} source workflow run status must be completed, got {run.get('status')!r}")
    if run.get("conclusion") != "success":
        errors.append(f"{target} source workflow run conclusion must be success, got {run.get('conclusion')!r}")
    if run.get("event") != "workflow_dispatch":
        errors.append(f"{target} source workflow run event must be workflow_dispatch, got {run.get('event')!r}")
    expected_release_tag = str(record.get("release_tag", "")).strip()
    actual_head_branch = first_present(run, "head_branch", "headBranch")
    if actual_head_branch != expected_release_tag:
        errors.append(
            f"{target} source workflow run head_branch must match release_tag "
            f"{expected_release_tag}, got {actual_head_branch!r}"
        )
    expected_head = source_values.get("head_sha", "")
    actual_head = first_present(run, "head_sha", "headSha")
    if actual_head != expected_head:
        errors.append(
            f"{target} source workflow run head_sha must match accepted record {expected_head}, "
            f"got {actual_head!r}"
        )
    expected_attempt = source.get("run_attempt")
    actual_attempt = first_present(run, "run_attempt", "attempt")
    if not isinstance(actual_attempt, int) or isinstance(actual_attempt, bool) or actual_attempt <= 0:
        errors.append(
            f"{target} source workflow run run_attempt must be a positive integer, "
            f"got {actual_attempt!r}"
        )
    elif actual_attempt != expected_attempt:
        errors.append(
            f"{target} source workflow run run_attempt must match accepted record "
            f"{expected_attempt}, got {actual_attempt!r}"
        )
    expected_path = source_values.get("workflow", "")
    actual_path = run.get("path")
    if actual_path != expected_path:
        errors.append(
            f"{target} source workflow run path must be {expected_path!r}, got {actual_path!r}"
        )
    run_created_at = first_present(run, "created_at", "createdAt", "run_created_at", "runCreatedAt")
    if parse_github_timestamp(run_created_at) is None:
        errors.append(
            f"{target} source workflow run created_at must be a GitHub ISO-8601 timestamp, "
            f"got {run_created_at!r}"
        )
    run_started_at = first_present(run, "run_started_at", "runStartedAt")
    if parse_github_timestamp(run_started_at) is None:
        errors.append(
            f"{target} source workflow run run_started_at must be a GitHub ISO-8601 timestamp, "
            f"got {run_started_at!r}"
        )
    run_updated_at = first_present(run, "updated_at", "updatedAt", "run_updated_at", "runUpdatedAt")
    if parse_github_timestamp(run_updated_at) is None:
        errors.append(
            f"{target} source workflow run updated_at must be a GitHub ISO-8601 timestamp, "
            f"got {run_updated_at!r}"
        )
    created = parse_github_timestamp(run_created_at)
    start = parse_github_timestamp(run_started_at)
    updated = parse_github_timestamp(run_updated_at)
    if created is not None and start is not None and start < created:
        errors.append(
            f"{target} source workflow run run_started_at must be at or after created_at "
            f"{run_created_at}, got {run_started_at!r}"
        )
    if start is not None and updated is not None and updated < start:
        errors.append(
            f"{target} source workflow run updated_at must be at or after run_started_at "
            f"{run_started_at}, got {run_updated_at!r}"
        )
    return errors


def source_run_expected_values(target: str, source: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    values: dict[str, str] = {}
    workflow = source.get("workflow")
    if not isinstance(workflow, str) or not workflow.strip():
        errors.append(f"{target} release_asset_source.workflow must be a non-empty string for source run audit")
    else:
        values["workflow"] = workflow.strip()
    run_url = source.get("workflow_run_url")
    if not isinstance(run_url, str) or not run_url.strip():
        errors.append(
            f"{target} release_asset_source.workflow_run_url must be a non-empty string for source run audit"
        )
    elif run_url != run_url.strip() or run_url != run_url.rstrip("/"):
        errors.append(
            f"{target} release_asset_source.workflow_run_url must be canonical without "
            "surrounding whitespace or trailing slash for source run audit"
        )
    else:
        values["workflow_run_url"] = run_url
    head_sha = source.get("head_sha")
    if not isinstance(head_sha, str) or head_sha != head_sha.strip() or not is_lower_git_sha(head_sha):
        errors.append(
            f"{target} release_asset_source.head_sha must be a 40-character lowercase Git SHA for source run audit"
        )
    else:
        values["head_sha"] = head_sha
    return values, errors


def source_artifact_expected_values(target: str, source: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    values, errors = source_run_expected_values(target, source)
    artifact_name = source.get("artifact_name")
    if not isinstance(artifact_name, str) or not artifact_name.strip():
        errors.append(
            f"{target} release_asset_source.artifact_name must be a non-empty string for source artifact audit"
        )
    else:
        values["artifact_name"] = artifact_name.strip()
    return values, errors


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def nested_full_name(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if isinstance(value, dict):
        return str(value.get("full_name", "")).strip()
    return ""


def nested_positive_int(mapping: dict[str, Any], key: str, nested_key: str) -> int | None:
    value = mapping.get(key)
    if not isinstance(value, dict):
        return None
    raw_value = value.get(nested_key)
    if isinstance(raw_value, int) and not isinstance(raw_value, bool) and raw_value > 0:
        return raw_value
    return None


def valid_source_run_created_at(run: dict[str, Any]) -> str | None:
    raw_value = first_present(run, "created_at", "createdAt", "run_created_at", "runCreatedAt")
    if parse_github_timestamp(raw_value) is None:
        return None
    return str(raw_value).strip()


def valid_source_run_started_at(run: dict[str, Any]) -> str | None:
    raw_value = first_present(run, "run_started_at", "runStartedAt")
    if parse_github_timestamp(raw_value) is None:
        return None
    return str(raw_value).strip()


def valid_source_run_updated_at(run: dict[str, Any]) -> str | None:
    raw_value = first_present(run, "updated_at", "updatedAt", "run_updated_at", "runUpdatedAt")
    if parse_github_timestamp(raw_value) is None:
        return None
    return str(raw_value).strip()


def parse_github_timestamp(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    text = raw_value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def check_record_source_artifact(
    target: str,
    record: dict[str, Any],
    source_artifacts_by_run: dict[str, dict[str, Any]],
    *,
    source_runs_by_run: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    source_values, source_errors = source_artifact_expected_values(target, source)
    if source_errors:
        return source_errors
    run_url = source_values["workflow_run_url"]
    artifact_name = source_values["artifact_name"]
    run_key = normalize_run_key(run_url)
    artifact_aliases = source_run_aliases(source_artifacts_by_run, run_key)
    if len(artifact_aliases) > 1:
        return [
            f"{target} source workflow artifacts contain ambiguous aliases for accepted "
            f"source run {run_key}: {artifact_aliases}"
        ]
    document = source_artifacts_by_run.get(artifact_aliases[0]) if artifact_aliases else None
    if not isinstance(document, dict):
        return [f"{target} source workflow artifacts missing for {run_url}"]
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list):
        return [f"{target} source workflow artifacts for {run_url} must include artifacts list"]
    total_count = document.get("total_count")
    if (
        not isinstance(total_count, int)
        or isinstance(total_count, bool)
        or total_count != len(artifacts)
    ):
        return [
            f"{target} source workflow artifact metadata total_count must match "
            f"the complete artifacts list length, got {total_count!r} for {len(artifacts)} artifacts"
        ]
    errors: list[str] = []
    if len(artifacts) != 1:
        errors.append(
            f"{target} source workflow artifact list must contain only the "
            f"target-scoped evidence artifact {artifact_name!r}, got {len(artifacts)} artifacts"
        )
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("name") == artifact_name
    ]
    if len(matches) != 1:
        errors.append(
            f"{target} source workflow artifact list must contain exactly one "
            f"{artifact_name!r}, got {len(matches)}"
        )
        return errors
    source_run = exact_source_run_document(run_url, source_runs_by_run or {})
    expected_repository_id = (
        nested_positive_int(source_run, "repository", "id")
        if isinstance(source_run, dict)
        else None
    )
    expected_head_repository_id = (
        nested_positive_int(source_run, "head_repository", "id")
        if isinstance(source_run, dict)
        else None
    )
    expected_run_created_at = (
        valid_source_run_created_at(source_run)
        if isinstance(source_run, dict)
        else None
    )
    expected_run_started_at = (
        valid_source_run_started_at(source_run)
        if isinstance(source_run, dict)
        else None
    )
    expected_run_updated_at = (
        valid_source_run_updated_at(source_run)
        if isinstance(source_run, dict)
        else None
    )
    errors.extend(
        check_source_artifact_record(
            target,
            matches[0],
            record,
            expected_repository_id=expected_repository_id,
            expected_head_repository_id=expected_head_repository_id,
            expected_run_created_at=expected_run_created_at,
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    return errors


def source_artifact_record_for_run(
    target: str,
    record: dict[str, Any],
    source_artifacts_by_run: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return None
    source_values, source_errors = source_artifact_expected_values(target, source)
    if source_errors:
        return None
    artifact_name = source_values["artifact_name"]
    run_url = source_values["workflow_run_url"]
    run_key = normalize_run_key(run_url)
    run_id = run_key.rsplit("/", 1)[-1] if run_key else ""
    document = (
        source_artifacts_by_run[run_key]
        if run_key in source_artifacts_by_run
        else source_artifacts_by_run.get(run_id)
    )
    if not isinstance(document, dict):
        return None
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("name") == artifact_name
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def source_artifact_archive_download_url_for_fetch(
    target: str,
    artifact: dict[str, Any],
    *,
    repository: str,
) -> tuple[list[str], str]:
    artifact_name = artifact.get("name")
    label = (
        artifact_name
        if isinstance(artifact_name, str) and artifact_name.strip()
        else "source workflow artifact"
    )
    artifact_id = artifact.get("id")
    errors: list[str] = []
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        errors.append(
            f"{target} source workflow artifact {label} id must be a positive integer "
            f"before byte fetch, got {artifact_id!r}"
        )
    raw_archive_url = artifact.get("archive_download_url")
    if not isinstance(raw_archive_url, str) or not raw_archive_url.strip():
        errors.append(
            f"{target} source workflow artifact {label} archive_download_url must be "
            f"a non-empty string before byte fetch, got {raw_archive_url!r}"
        )
        return errors, ""
    if raw_archive_url != raw_archive_url.strip():
        errors.append(
            f"{target} source workflow artifact {label} archive_download_url must not "
            f"have surrounding whitespace before byte fetch, got {raw_archive_url!r}"
        )
    archive_url = raw_archive_url
    if isinstance(artifact_id, int) and not isinstance(artifact_id, bool) and artifact_id > 0:
        expected_url = f"{source_artifact_api_url(repository, artifact_id)}/zip"
        if archive_url != expected_url:
            errors.append(
                f"{target} source workflow artifact {label} archive_download_url must be "
                f"{expected_url!r} before byte fetch, got {archive_url!r}"
            )
    if errors:
        return errors, ""
    return [], archive_url


def check_record_source_artifact_zip_bytes(
    target: str,
    record: dict[str, Any],
    *,
    source_artifacts_by_run: dict[str, dict[str, Any]],
    source_artifact_bytes_by_run: dict[str, bytes],
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    source_values, source_errors = source_artifact_expected_values(target, source)
    if source_errors:
        return source_errors
    artifact_name = source_values["artifact_name"]
    run_url = source_values["workflow_run_url"]
    run_key = normalize_run_key(run_url)
    byte_aliases = source_run_aliases(source_artifact_bytes_by_run, run_key)
    if len(byte_aliases) > 1:
        return [
            f"{target} source workflow artifact ZIP bytes contain ambiguous aliases for "
            f"accepted source run {run_key}: {byte_aliases}"
        ]
    archive_bytes = source_artifact_bytes_by_run.get(byte_aliases[0]) if byte_aliases else None
    if archive_bytes is None:
        return [f"{target} source workflow artifact ZIP bytes missing for {run_url}"]
    errors: list[str] = []
    artifact_record = source_artifact_record_for_run(target, record, source_artifacts_by_run)
    if isinstance(artifact_record, dict):
        artifact_size = artifact_record.get("size_in_bytes")
        if (
            isinstance(artifact_size, int)
            and not isinstance(artifact_size, bool)
            and artifact_size != len(archive_bytes)
        ):
            errors.append(
                f"{target} source workflow artifact {artifact_name} size_in_bytes "
                f"must match downloaded ZIP byte length {len(archive_bytes)}, got {artifact_size!r}"
            )
    file_bytes_or_error = source_artifact_zip_file_bytes(archive_bytes)
    if isinstance(file_bytes_or_error, str):
        errors.append(
            f"{target} source workflow artifact {artifact_name} ZIP is invalid: {file_bytes_or_error}"
        )
        return errors
    expected_files = {
        str(filename)
        for filename in source.get("contains_files", [])
        if isinstance(filename, str)
    }
    actual_files = set(file_bytes_or_error)
    expected_byte_sources = expected_source_artifact_zip_byte_sources(record)
    missing_files = sorted(expected_files - actual_files)
    if missing_files:
        errors.append(
            f"{target} source workflow artifact {artifact_name} ZIP missing files: {missing_files}"
        )
    unexpected_files = sorted(actual_files - expected_files)
    if unexpected_files:
        errors.append(
            f"{target} source workflow artifact {artifact_name} ZIP has unexpected files: {unexpected_files}"
        )
    for filename in sorted(expected_files & actual_files):
        actual_bytes = file_bytes_or_error[filename]
        expected = expected_byte_sources.get(filename)
        if expected is None:
            errors.append(
                f"{target} source workflow artifact {artifact_name} ZIP file {filename} "
                "has no accepted byte expectation"
            )
            continue
        if not actual_bytes:
            errors.append(
                f"{target} source workflow artifact {artifact_name} ZIP file {filename} must not be empty"
            )
        expected_sha = expected.get("sha256", "")
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        if not lowercase_sha256_hex(expected_sha):
            errors.append(
                f"{target} source workflow artifact {artifact_name} ZIP file {filename} "
                "accepted SHA-256 expectation must be a lowercase SHA-256 hex digest"
            )
        elif actual_sha != expected_sha:
            errors.append(
                f"{target} source workflow artifact {artifact_name} ZIP file {filename} "
                f"bytes SHA-256 must match accepted evidence {expected_sha}, got {actual_sha}"
            )
        expected_size = expected.get("size")
        if expected_size is not None:
            if not positive_int(expected_size):
                errors.append(
                    f"{target} source workflow artifact {artifact_name} ZIP file {filename} "
                    "accepted byte size expectation must be a positive integer"
                )
            elif len(actual_bytes) != expected_size:
                errors.append(
                    f"{target} source workflow artifact {artifact_name} ZIP file {filename} "
                    f"byte size must match accepted evidence {expected_size}, got {len(actual_bytes)}"
                )
    return errors


def expected_source_artifact_zip_byte_sources(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        filename: metadata
        for filename, metadata in expected_published_assets(record).items()
        if exact_safe_file_name(filename)
    }


def source_artifact_zip_names(archive_bytes: bytes) -> list[str] | str:
    entries_or_error = source_artifact_zip_file_bytes(archive_bytes)
    if isinstance(entries_or_error, str):
        return entries_or_error
    return sorted(entries_or_error)


def source_artifact_zip_file_bytes(archive_bytes: bytes) -> dict[str, bytes] | str:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            entries: dict[str, bytes] = {}
            duplicates: list[str] = []
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if not name:
                    continue
                if name.endswith("/"):
                    return f"contains directory entry {info.filename!r}"
                if "/" in name or not exact_safe_file_name(name):
                    return f"contains non-root or unsafe file name {info.filename!r}"
                if zip_info_is_encrypted(info):
                    return f"contains encrypted entry {info.filename!r}"
                if zip_info_is_symlink(info):
                    return f"contains symlink entry {info.filename!r}"
                if zip_info_declares_non_regular_file(info):
                    return f"contains non-regular file entry {info.filename!r}"
                if zip_info_declares_unexpected_regular_file_permissions(info):
                    return (
                        "contains regular file entry with non-0644 permissions "
                        f"{info.filename!r}"
                    )
                if name in entries:
                    duplicates.append(name)
                    continue
                entries[name] = archive.read(info)
            if duplicates:
                return f"contains duplicate files {sorted(set(duplicates))}"
            case_collisions = case_insensitive_name_collisions(set(entries))
            if case_collisions:
                return f"contains files that collide on case-insensitive filesystems {case_collisions}"
            if not entries:
                return "contains no files"
            return entries
    except zipfile.BadZipFile as exc:
        return str(exc)
    except RuntimeError as exc:
        return str(exc)
    except OSError as exc:
        return str(exc)


def zip_info_is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)


def zip_info_is_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def zip_info_declares_non_regular_file(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    return file_type not in (0, 0o100000)


def zip_info_declares_unexpected_regular_file_permissions(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0o177777
    file_type = unix_mode & 0o170000
    if file_type != 0o100000:
        return False
    permissions = unix_mode & 0o7777
    return permissions != 0o644


def check_source_artifact_record(
    target: str,
    artifact: dict[str, Any],
    record: dict[str, Any],
    *,
    expected_repository_id: int | None = None,
    expected_head_repository_id: int | None = None,
    expected_run_created_at: str | None = None,
    expected_run_started_at: str | None = None,
    expected_run_updated_at: str | None = None,
) -> list[str]:
    source = record.get("release_asset_source")
    if not isinstance(source, dict):
        return [f"{target} release_asset_source must be an object"]
    source_values, source_errors = source_artifact_expected_values(target, source)
    if source_errors:
        return source_errors
    artifact_name = source_values["artifact_name"]
    run_url = source_values["workflow_run_url"]
    run_id = run_url.rsplit("/", 1)[-1] if run_url else ""
    repository = repository_from_run_url(run_url)
    expected_head = source_values["head_sha"]
    errors: list[str] = []
    actual_name = artifact.get("name")
    if actual_name != artifact_name:
        errors.append(
            f"{target} source workflow artifact name must match accepted record "
            f"{artifact_name!r}, got {actual_name!r}"
        )
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        errors.append(
            f"{target} source workflow artifact {artifact_name} id must be a positive integer, "
            f"got {artifact_id!r}"
        )
    elif repository:
        expected_url = source_artifact_api_url(repository, artifact_id)
        if artifact.get("url") != expected_url:
            errors.append(
                f"{target} source workflow artifact {artifact_name} url "
                f"must be {expected_url!r}, got {artifact.get('url')!r}"
            )
        expected_archive_url = (
            f"{source_artifact_api_url(repository, artifact_id)}/zip"
        )
        if artifact.get("archive_download_url") != expected_archive_url:
            errors.append(
                f"{target} source workflow artifact {artifact_name} archive_download_url "
                f"must be {expected_archive_url!r}, got {artifact.get('archive_download_url')!r}"
            )
    node_id = artifact.get("node_id")
    if not isinstance(node_id, str) or not node_id or node_id != node_id.strip():
        errors.append(
            f"{target} source workflow artifact {artifact_name} node_id "
            f"must be a non-empty string, got {node_id!r}"
        )
    if artifact.get("expired") is not False:
        errors.append(
            f"{target} source workflow artifact {artifact_name} must not be expired, "
            f"got {artifact.get('expired')!r}"
        )
    size = artifact.get("size_in_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        errors.append(
            f"{target} source workflow artifact {artifact_name} size_in_bytes must be positive, "
            f"got {size!r}"
        )
    errors.extend(
        check_source_artifact_created_within_run_window(
            target,
            artifact_name,
            first_present(artifact, "created_at", "createdAt"),
            expected_run_created_at=expected_run_created_at,
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    errors.extend(
        check_source_artifact_updated_within_run_window(
            target,
            artifact_name,
            first_present(artifact, "updated_at", "updatedAt"),
            first_present(artifact, "created_at", "createdAt"),
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    errors.extend(
        check_source_artifact_expiration(
            target,
            artifact_name,
            first_present(artifact, "expires_at", "expiresAt"),
            raw_created_at=first_present(artifact, "created_at", "createdAt"),
            raw_updated_at=first_present(artifact, "updated_at", "updatedAt"),
        )
    )
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append(f"{target} source workflow artifact {artifact_name} workflow_run must be an object")
    else:
        expected_run_id = int(run_id) if run_id.isdecimal() else None
        artifact_run_id = workflow_run.get("id")
        if not isinstance(artifact_run_id, int) or isinstance(artifact_run_id, bool) or artifact_run_id <= 0:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.id "
                f"must be a positive integer, got {artifact_run_id!r}"
            )
        elif expected_run_id is not None and artifact_run_id != expected_run_id:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.id must match "
                f"run {run_id}, got {artifact_run_id!r}"
            )
        artifact_head = workflow_run.get("head_sha")
        if (
            not isinstance(artifact_head, str)
            or artifact_head != artifact_head.strip()
            or not is_lower_git_sha(artifact_head)
        ):
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.head_sha "
                f"must be a 40-character lowercase Git SHA, got {artifact_head!r}"
            )
        elif artifact_head != expected_head:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.head_sha must match "
                f"accepted record {expected_head}, got {artifact_head!r}"
            )
        artifact_repository_id = workflow_run.get("repository_id")
        if (
            not isinstance(artifact_repository_id, int)
            or isinstance(artifact_repository_id, bool)
            or artifact_repository_id <= 0
        ):
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.repository_id "
                f"must be a positive integer, got {artifact_repository_id!r}"
            )
        elif expected_repository_id is not None and artifact_repository_id != expected_repository_id:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.repository_id "
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
                f"{target} source workflow artifact {artifact_name} workflow_run.head_repository_id "
                f"must be a positive integer, got {artifact_head_repository_id!r}"
            )
        elif (
            expected_head_repository_id is not None
            and artifact_head_repository_id != expected_head_repository_id
        ):
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.head_repository_id "
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
            f"{target} source workflow artifact {artifact_name} expires_at "
            f"must be a GitHub ISO-8601 timestamp, got {raw_expires_at!r}"
        ]
    errors: list[str] = []
    created_at = parse_github_timestamp(raw_created_at)
    if created_at is not None and expires_at <= created_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} expires_at "
            f"must be after created_at {raw_created_at}, got {raw_expires_at!r}"
        )
    updated_at = parse_github_timestamp(raw_updated_at)
    if updated_at is not None and expires_at <= updated_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} expires_at "
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
            f"{target} source workflow artifact {artifact_name} created_at "
            f"must be a GitHub ISO-8601 timestamp when exact source run timestamps are known, "
            f"got {raw_created_at!r}"
        ]
    errors: list[str] = []
    if run_created_at is not None and created_at < run_created_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} created_at "
            f"must be at or after exact source run creation {expected_run_created_at}, "
            f"got {raw_created_at!r}"
        )
    if run_started_at is not None and created_at < run_started_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} created_at "
            f"must be at or after exact source run start {expected_run_started_at}, "
            f"got {raw_created_at!r}"
        )
    if run_updated_at is not None and created_at > run_updated_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} created_at "
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
    expected_run_started_at: str | None,
    expected_run_updated_at: str | None,
) -> list[str]:
    if expected_run_started_at is None and expected_run_updated_at is None:
        return []
    run_started_at = parse_github_timestamp(expected_run_started_at)
    run_updated_at = parse_github_timestamp(expected_run_updated_at)
    artifact_updated_at = parse_github_timestamp(raw_updated_at)
    if artifact_updated_at is None:
        return [
            f"{target} source workflow artifact {artifact_name} updated_at "
            f"must be a GitHub ISO-8601 timestamp when exact source run timestamps are known, "
            f"got {raw_updated_at!r}"
        ]
    errors: list[str] = []
    if run_started_at is not None and artifact_updated_at < run_started_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} updated_at "
            f"must be at or after exact source run start {expected_run_started_at}, "
            f"got {raw_updated_at!r}"
        )
    if run_updated_at is not None and artifact_updated_at > run_updated_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} updated_at "
            f"must be at or before exact source run update {expected_run_updated_at}, "
            f"got {raw_updated_at!r}"
        )
    created_at = parse_github_timestamp(raw_created_at)
    if created_at is not None and artifact_updated_at < created_at:
        errors.append(
            f"{target} source workflow artifact {artifact_name} updated_at "
            f"must be at or after created_at {raw_created_at}, got {raw_updated_at!r}"
        )
    return errors


def repository_from_run_url(run_url: str) -> str:
    prefix = "https://github.com/"
    marker = "/actions/runs/"
    if not run_url.startswith(prefix) or marker not in run_url:
        return ""
    repository = run_url[len(prefix):].split(marker, 1)[0]
    return repository.strip("/")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
