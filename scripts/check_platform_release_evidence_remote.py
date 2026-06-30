from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_review_bundle_artifacts import canonical_public_record_bytes  # noqa: E402
from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    PROMOTION_PATH,
    PROTECTED_GOAL_TARGETS,
    accepted_artifact_names,
    accepted_record_source_file,
    check_platform_verified_evidence,
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
    release, release_errors = load_release_data(args)
    source_runs, source_run_errors = load_source_runs(args, registry, required_targets)
    workflow_runs, workflow_errors = load_workflow_runs(args, registry, required_targets)
    source_artifacts, source_artifact_errors = load_source_artifacts(args, registry, required_targets)
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
        *final_record_errors,
        *release_asset_byte_errors,
        *tag_errors,
    ]
    if release is not None:
        errors.extend(
            check_remote_platform_release_evidence(
                registry=registry,
                promotion=promotion,
                release=release,
                source_runs_by_run=source_runs,
                workflow_runs_by_workflow=workflow_runs,
                source_artifacts_by_run=source_artifacts,
                final_record_bytes_by_url=final_record_bytes,
                release_asset_bytes_by_url=release_asset_bytes,
                tag_ref=tag_ref,
                tag_object=tag_object,
                release_tag=args.release_tag,
                required_targets=required_targets,
                require_source_runs=args.require_source_runs,
                require_final_record_bytes=args.require_final_record_bytes,
                require_release_asset_bytes=args.require_release_asset_bytes,
                require_tag_source_head=args.require_tag_source_head,
            )
        )
    if errors:
        for error in errors:
            print(f"platform release evidence remote: {error}", file=sys.stderr)
        return 1
    print(f"platform release evidence remote passed for {args.release_tag}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a GitHub release and optional workflow-run metadata for "
            "protected Linux i386/armhf and Windows XP native-host evidence."
        )
    )
    parser.add_argument("--repository", help="GitHub repository in owner/name form")
    parser.add_argument("--release-tag", required=True, help="release tag, for example v1.0.2")
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
        "--final-record-json",
        action="append",
        default=[],
        metavar="URL=PATH",
        help=(
            "read a published finalized accepted-record JSON asset from a local file for "
            "offline byte verification, for example "
            "https://github.com/owner/repo/releases/download/v1.0.2/platform-verified-evidence-linux-i386-final.json=record.json"
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
            "https://github.com/owner/repo/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-i386.deb=asset.deb"
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
        help="require all protected platform goal targets for the release tag",
    )
    parser.add_argument(
        "--require-source-runs",
        action="store_true",
        help="require each accepted record source workflow run to be present and successful",
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
    for raw in args.final_record_json:
        if "=" not in str(raw):
            errors.append(f"--final-record-json must be URL=PATH, got {raw!r}")
    for raw in args.release_asset:
        if "=" not in str(raw):
            errors.append(f"--release-asset must be URL=PATH, got {raw!r}")
    return errors


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
        str(row.get("target", ""))
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == args.release_tag
        and str(row.get("target", "")) in PROTECTED_GOAL_TARGETS
    }
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets)


def load_release_data(args: argparse.Namespace) -> tuple[dict[str, Any] | None, list[str]]:
    if args.release_json:
        data, error = read_json_file(args.release_json)
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
        data, error = read_json_file(path)
        if error:
            errors.append(error)
            continue
        source_runs[normalize_run_key(run)] = data or {}
    if not args.require_source_runs:
        return source_runs, errors

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
        data, error = read_json_file(path)
        if error:
            errors.append(error)
            continue
        workflow_runs[workflow] = data or {}
    if args.require_source_runs and args.repository:
        return workflow_runs, errors
    if not args.require_source_runs:
        return workflow_runs, errors

    needed_workflows = source_workflows_for_records(
        registry,
        release_tag=args.release_tag,
        required_targets=required_targets,
    )
    if args.require_goal_targets:
        needed_workflows.update(release_source_workflow(target) for target in PROTECTED_GOAL_TARGETS)
    for workflow in sorted(needed_workflows - set(workflow_runs)):
        if not args.repository:
            continue
        workflow_file = quote(Path(workflow).name, safe="")
        url = f"{GITHUB_API}/repos/{args.repository}/actions/workflows/{workflow_file}/runs?per_page=100"
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
        data, error = read_json_file(path)
        if error:
            errors.append(error)
            continue
        source_artifacts[normalize_run_key(run)] = data or {}
    if not args.require_source_runs:
        return source_artifacts, errors

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


def load_final_record_bytes(
    args: argparse.Namespace,
    registry: dict[str, Any],
    required_targets: tuple[str, ...],
) -> tuple[dict[str, bytes], list[str]]:
    configured_paths = final_record_json_paths(args)
    records_by_url: dict[str, bytes] = {}
    errors: list[str] = []
    for url, path in configured_paths.items():
        data, error = read_bytes_file(path)
        if error:
            errors.append(error)
            continue
        records_by_url[url] = data or b""
    if not args.require_final_record_bytes:
        return records_by_url, errors

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
        data, error = read_bytes_file(path)
        if error:
            errors.append(error)
            continue
        assets_by_url[url] = data or b""
    if not args.require_release_asset_bytes:
        return assets_by_url, errors

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
        tag_ref, error = read_json_file(args.tag_ref_json)
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
    object_sha = str(object_record.get("sha", "")).strip() if isinstance(object_record, dict) else ""
    if object_type == "tag":
        if args.tag_object_json:
            tag_object, error = read_json_file(args.tag_object_json)
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
        paths[workflow] = Path(path)
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


def normalize_url_key(url: str) -> str:
    return str(url).strip()


def expected_finalized_record_release_url(repository: str, release_tag: str, target: str) -> str:
    return (
        f"https://github.com/{repository}/releases/download/"
        f"{release_tag}/{accepted_record_source_file(target)}"
    )


def expected_release_asset_url(repository: str, release_tag: str, filename: str) -> str:
    return f"https://github.com/{repository}/releases/download/{release_tag}/{filename}"


def read_json_file(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"failed to read JSON {path}: {exc}"
    if not isinstance(data, dict):
        return None, f"JSON file must contain an object: {path}"
    return data, None


def fetch_json(url: str, *, timeout: float) -> tuple[dict[str, Any] | None, list[str]]:
    request = Request(url, headers=github_api_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - exercised manually against live GitHub.
        return None, [f"failed to fetch {url}: {exc}"]
    if not isinstance(data, dict):
        return None, [f"GitHub API response must be a JSON object: {url}"]
    return data, []


def read_bytes_file(path: Path) -> tuple[bytes | None, str | None]:
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
        return None, [f"failed to fetch {url}: {exc}"]


def github_api_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Codex"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def is_lower_git_sha(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value.strip()) is not None


def check_remote_platform_release_evidence(
    *,
    registry: dict[str, Any],
    promotion: dict[str, Any],
    release: dict[str, Any],
    workflow_runs_by_workflow: dict[str, dict[str, Any]],
    source_runs_by_run: dict[str, dict[str, Any]] | None = None,
    source_artifacts_by_run: dict[str, dict[str, Any]] | None = None,
    final_record_bytes_by_url: dict[str, bytes] | None = None,
    release_asset_bytes_by_url: dict[str, bytes] | None = None,
    tag_ref: dict[str, Any] | None = None,
    tag_object: dict[str, Any] | None = None,
    release_tag: str,
    required_targets: tuple[str, ...],
    require_source_runs: bool = False,
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
                )
            )
    if require_source_runs:
        for target in required_targets:
            record = records.get(target)
            if record is None:
                errors.append(f"{target} accepted evidence record missing; cannot verify release source run")
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
    return errors


def check_release_metadata(release: dict[str, Any], release_tag: str) -> list[str]:
    errors: list[str] = []
    if release.get("tag_name") != release_tag:
        errors.append(f"remote release tag_name must be {release_tag}, got {release.get('tag_name')!r}")
    if release.get("draft") is not False:
        errors.append(f"remote release {release_tag} must not be draft")
    if release.get("prerelease") is not False:
        errors.append(f"remote release {release_tag} must not be prerelease")
    assets = release.get("assets")
    if not isinstance(assets, list):
        errors.append(f"remote release {release_tag} assets must be a list")
    return errors


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
    errors: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        if not isinstance(name, str) or not name:
            continue
        counts[name] = counts.get(name, 0) + 1
        by_name.setdefault(name, asset)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"remote release contains duplicate asset names: {duplicates}")
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
) -> list[str]:
    errors: list[str] = []
    for filename, expected in sorted(expected_published_assets(record).items()):
        asset = release_assets_by_name.get(filename)
        if not isinstance(asset, dict):
            continue
        if asset.get("state") != "uploaded":
            errors.append(
                f"{target} remote release asset {filename} state must be uploaded, "
                f"got {asset.get('state')!r}"
            )
        expected_url = expected.get("browser_download_url")
        if expected_url and asset.get("browser_download_url") != expected_url:
            errors.append(
                f"{target} remote release asset {filename} browser_download_url must be "
                f"{expected_url!r}, got {asset.get('browser_download_url')!r}"
            )
        expected_sha = expected.get("sha256")
        if expected_sha:
            expected_digest = f"sha256:{expected_sha}"
            if asset.get("digest") != expected_digest:
                errors.append(
                    f"{target} remote release asset {filename} digest must be "
                    f"{expected_digest}, got {asset.get('digest')!r}"
                )
        expected_size = expected.get("size")
        if expected_size is not None and asset.get("size") != expected_size:
            errors.append(
                f"{target} remote release asset {filename} size must be "
                f"{expected_size}, got {asset.get('size')!r}"
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
) -> list[str]:
    errors: list[str] = []
    for asset in expected_release_asset_byte_sources(record):
        filename = str(asset.get("filename", ""))
        url = asset.get("url")
        if not isinstance(url, str) or not url.strip():
            errors.append(f"{target} release asset {filename} URL must be set before byte verification")
            continue
        url_key = normalize_url_key(url)
        published_bytes = release_asset_bytes_by_url.get(url_key)
        if published_bytes is None:
            errors.append(f"{target} published release asset bytes missing for {filename} at {url_key}")
            continue
        expected_sha = str(asset.get("sha256", ""))
        actual_sha = hashlib.sha256(published_bytes).hexdigest()
        if actual_sha != expected_sha:
            errors.append(
                f"{target} published release asset {filename} bytes SHA-256 must match "
                f"accepted evidence {expected_sha}, got {actual_sha}"
            )
        expected_size = asset.get("size")
        if expected_size is not None and len(published_bytes) != expected_size:
            errors.append(
                f"{target} published release asset {filename} byte size must match "
                f"accepted evidence {expected_size}, got {len(published_bytes)}"
            )
    return errors


def expected_release_asset_byte_sources(record: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    artifact_hashes = record.get("artifact_sha256")
    release_urls = release_urls_by_filename(record.get("release_asset_urls"))
    if isinstance(artifact_hashes, dict):
        for filename, digest in sorted(artifact_hashes.items()):
            name = str(filename)
            sources.append(
                {
                    "filename": name,
                    "url": release_urls.get(name),
                    "sha256": str(digest),
                }
            )
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_urls = release_urls_by_filename(review_bundle.get("release_asset_urls"))
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = str(bundle_record.get("file", ""))
            if not filename:
                continue
            sources.append(
                {
                    "filename": filename,
                    "url": review_urls.get(filename),
                    "sha256": str(bundle_record.get("sha256", "")),
                    "size": bundle_record.get("size_bytes"),
                }
            )
    return sources


def expected_published_assets(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    expected: dict[str, dict[str, Any]] = {}
    target = str(record.get("target", ""))
    artifact_hashes = record.get("artifact_sha256")
    release_urls = release_urls_by_filename(record.get("release_asset_urls"))
    if isinstance(artifact_hashes, dict):
        for filename, digest in sorted(artifact_hashes.items()):
            name = str(filename)
            expected[name] = {
                "browser_download_url": release_urls.get(name),
                "sha256": str(digest),
            }
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_urls = release_urls_by_filename(review_bundle.get("release_asset_urls"))
        for key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(key)
            if not isinstance(bundle_record, dict):
                continue
            filename = str(bundle_record.get("file", ""))
            if not filename:
                continue
            expected[filename] = {
                "browser_download_url": review_urls.get(filename),
                "sha256": str(bundle_record.get("sha256", "")),
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
        url = str(raw_url)
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
        str(row.get("id", "")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
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
        str(row.get("target", "")): row
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == release_tag
        and str(row.get("target", "")) in target_set
    }


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
        head_sha = str(source.get("head_sha", "")).strip()
        if not is_lower_git_sha(head_sha):
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
    object_sha = str(raw_object.get("sha", "")).strip()
    if not is_lower_git_sha(object_sha):
        errors.append(
            f"release tag {release_tag} ref object.sha must be a 40-character lowercase Git SHA"
        )
    if object_type == "commit":
        return object_sha if is_lower_git_sha(object_sha) else None, errors
    if object_type != "tag":
        errors.append(f"release tag {release_tag} ref object.type must be commit or tag, got {object_type!r}")
        return None, errors
    if not isinstance(tag_object, dict):
        return None, [
            *errors,
            f"release tag {release_tag} annotated tag object metadata missing for {object_sha}",
        ]
    tag_object_sha = str(tag_object.get("sha", "")).strip()
    if not is_lower_git_sha(tag_object_sha):
        errors.append(
            f"release tag {release_tag} annotated tag object sha must be a "
            "40-character lowercase Git SHA"
        )
    elif is_lower_git_sha(object_sha) and tag_object_sha != object_sha:
        errors.append(
            f"release tag {release_tag} annotated tag object sha must match ref object "
            f"{object_sha}, got {tag_object_sha}"
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
    commit_sha = str(raw_target.get("sha", "")).strip()
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
        target = str(record.get("target", ""))
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
            workflow = str(source.get("workflow", "")).strip()
            if workflow:
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
            run_url = str(source.get("workflow_run_url", "")).strip().rstrip("/")
            if run_url:
                urls.add(run_url)
    return urls


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
        source_run_url = normalize_run_key(str(source.get("workflow_run_url", "")))
        if source_run_url != normalized:
            continue
        attempt = source.get("run_attempt")
        if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0:
            return attempt
    return None


def source_run_attempt_api_url(repository: str, run_id: str, run_attempt: int) -> str:
    return (
        f"{GITHUB_API}/repos/{repository}/actions/runs/{quote(str(run_id), safe='')}"
        f"/attempts/{quote(str(run_attempt), safe='')}"
    )


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
    workflow = str(source.get("workflow", "")).strip()
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_id = run_url.rsplit("/", 1)[-1] if run_url else ""
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
            or str(run.get("html_url", "")).rstrip("/") == run_url
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
    run_id = run_key.rsplit("/", 1)[-1] if run_key else ""
    document = (
        source_runs_by_run[run_key]
        if run_key in source_runs_by_run
        else source_runs_by_run.get(run_id)
    )
    return document if isinstance(document, dict) else None


def check_source_run_record(
    target: str,
    run: dict[str, Any],
    record: dict[str, Any],
) -> list[str]:
    source = record.get("release_asset_source")
    source = source if isinstance(source, dict) else {}
    errors: list[str] = []
    expected_run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    expected_run_id = expected_run_url.rsplit("/", 1)[-1] if expected_run_url else ""
    if str(run.get("id", "")) != expected_run_id:
        errors.append(
            f"{target} source workflow run id must match accepted record "
            f"{expected_run_id}, got {run.get('id')!r}"
        )
    actual_url = str(first_present(run, "html_url", "htmlUrl") or "").rstrip("/")
    if actual_url != expected_run_url:
        errors.append(
            f"{target} source workflow run html_url must match accepted record "
            f"{expected_run_url}, got {first_present(run, 'html_url', 'htmlUrl')!r}"
        )
    expected_repository = repository_from_run_url(expected_run_url)
    for field in ("repository", "head_repository"):
        actual_repository = nested_full_name(run, field)
        if actual_repository != expected_repository:
            errors.append(
                f"{target} source workflow run {field}.full_name must match accepted record "
                f"{expected_repository}, got {actual_repository!r}"
            )
    if run.get("status") != "completed":
        errors.append(f"{target} source workflow run status must be completed, got {run.get('status')!r}")
    if run.get("conclusion") != "success":
        errors.append(f"{target} source workflow run conclusion must be success, got {run.get('conclusion')!r}")
    if run.get("event") != "workflow_dispatch":
        errors.append(f"{target} source workflow run event must be workflow_dispatch, got {run.get('event')!r}")
    expected_head = str(source.get("head_sha", ""))
    actual_head = first_present(run, "head_sha", "headSha")
    if actual_head != expected_head:
        errors.append(
            f"{target} source workflow run head_sha must match accepted record {expected_head}, "
            f"got {actual_head!r}"
        )
    expected_attempt = source.get("run_attempt")
    actual_attempt = first_present(run, "run_attempt", "attempt")
    if actual_attempt != expected_attempt:
        errors.append(
            f"{target} source workflow run run_attempt must match accepted record "
            f"{expected_attempt}, got {actual_attempt!r}"
        )
    expected_path = str(source.get("workflow", ""))
    actual_path = run.get("path")
    if actual_path != expected_path:
        errors.append(
            f"{target} source workflow run path must be {expected_path!r}, got {actual_path!r}"
        )
    run_started_at = first_present(run, "run_started_at", "runStartedAt")
    if run_started_at is not None and parse_github_timestamp(run_started_at) is None:
        errors.append(
            f"{target} source workflow run run_started_at must be a GitHub ISO-8601 timestamp, "
            f"got {run_started_at!r}"
        )
    run_updated_at = first_present(run, "updated_at", "updatedAt", "run_updated_at", "runUpdatedAt")
    if run_updated_at is not None and parse_github_timestamp(run_updated_at) is None:
        errors.append(
            f"{target} source workflow run updated_at must be a GitHub ISO-8601 timestamp, "
            f"got {run_updated_at!r}"
        )
    start = parse_github_timestamp(run_started_at)
    updated = parse_github_timestamp(run_updated_at)
    if start is not None and updated is not None and updated < start:
        errors.append(
            f"{target} source workflow run updated_at must be at or after run_started_at "
            f"{run_started_at}, got {run_updated_at!r}"
        )
    return errors


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
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_id = run_url.rsplit("/", 1)[-1] if run_url else ""
    artifact_name = str(source.get("artifact_name", "")).strip()
    run_key = normalize_run_key(run_url)
    document = (
        source_artifacts_by_run[run_key]
        if run_key in source_artifacts_by_run
        else source_artifacts_by_run.get(run_id)
    )
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
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("name") == artifact_name
    ]
    if len(matches) != 1:
        return [
            f"{target} source workflow artifact list must contain exactly one "
            f"{artifact_name!r}, got {len(matches)}"
        ]
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
    return check_source_artifact_record(
        target,
        matches[0],
        record,
        expected_repository_id=expected_repository_id,
        expected_head_repository_id=expected_head_repository_id,
        expected_run_started_at=expected_run_started_at,
        expected_run_updated_at=expected_run_updated_at,
    )


def check_source_artifact_record(
    target: str,
    artifact: dict[str, Any],
    record: dict[str, Any],
    *,
    expected_repository_id: int | None = None,
    expected_head_repository_id: int | None = None,
    expected_run_started_at: str | None = None,
    expected_run_updated_at: str | None = None,
) -> list[str]:
    source = record.get("release_asset_source")
    source = source if isinstance(source, dict) else {}
    artifact_name = str(source.get("artifact_name", "")).strip()
    run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    run_id = run_url.rsplit("/", 1)[-1] if run_url else ""
    repository = repository_from_run_url(run_url)
    expected_head = str(source.get("head_sha", "")).strip()
    errors: list[str] = []
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool) or artifact_id <= 0:
        errors.append(
            f"{target} source workflow artifact {artifact_name} id must be a positive integer, "
            f"got {artifact_id!r}"
        )
    elif repository:
        expected_archive_url = (
            f"{GITHUB_API}/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        )
        if artifact.get("archive_download_url") != expected_archive_url:
            errors.append(
                f"{target} source workflow artifact {artifact_name} archive_download_url "
                f"must be {expected_archive_url!r}, got {artifact.get('archive_download_url')!r}"
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
            expected_run_started_at=expected_run_started_at,
            expected_run_updated_at=expected_run_updated_at,
        )
    )
    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict):
        errors.append(f"{target} source workflow artifact {artifact_name} workflow_run must be an object")
    else:
        artifact_run_id = workflow_run.get("id")
        if str(artifact_run_id) != run_id:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.id must match "
                f"run {run_id}, got {artifact_run_id!r}"
            )
        artifact_head = str(workflow_run.get("head_sha", "")).strip()
        if artifact_head != expected_head:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.head_sha must match "
                f"accepted record {expected_head}, got {artifact_head!r}"
            )
        if expected_repository_id is not None and workflow_run.get("repository_id") != expected_repository_id:
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.repository_id "
                f"must match exact source run repository id {expected_repository_id}, "
                f"got {workflow_run.get('repository_id')!r}"
            )
        if (
            expected_head_repository_id is not None
            and workflow_run.get("head_repository_id") != expected_head_repository_id
        ):
            errors.append(
                f"{target} source workflow artifact {artifact_name} workflow_run.head_repository_id "
                f"must match exact source run head repository id {expected_head_repository_id}, "
                f"got {workflow_run.get('head_repository_id')!r}"
            )
    return errors


def check_source_artifact_created_within_run_window(
    target: str,
    artifact_name: str,
    raw_created_at: Any,
    *,
    expected_run_started_at: str | None,
    expected_run_updated_at: str | None,
) -> list[str]:
    if expected_run_started_at is None and expected_run_updated_at is None:
        return []
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


def repository_from_run_url(run_url: str) -> str:
    prefix = "https://github.com/"
    marker = "/actions/runs/"
    if not run_url.startswith(prefix) or marker not in run_url:
        return ""
    repository = run_url[len(prefix):].split(marker, 1)[0]
    return repository.strip("/")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
