from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

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
from check_platform_review_bundle_artifacts import canonical_public_record_bytes  # noqa: E402

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
    errors = [*release_errors, *source_run_errors, *workflow_errors, *source_artifact_errors]
    if release is not None:
        errors.extend(
            check_remote_platform_release_evidence(
                registry=registry,
                promotion=promotion,
                release=release,
                source_runs_by_run=source_runs,
                workflow_runs_by_workflow=workflow_runs,
                source_artifacts_by_run=source_artifacts,
                release_tag=args.release_tag,
                required_targets=required_targets,
                require_source_runs=args.require_source_runs,
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
            ".github/workflows/extended-platform-evidence.yml=runs.json"
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
        "--require-goal-targets",
        action="store_true",
        help="require all protected platform goal targets for the release tag",
    )
    parser.add_argument(
        "--require-source-runs",
        action="store_true",
        help="require each accepted record source workflow run to be present and successful",
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
            configured = workflow_run_json_paths(args)
            required_workflows = {
                release_source_workflow(target) for target in PROTECTED_GOAL_TARGETS
            }
            missing = sorted(required_workflows - set(configured))
            if missing:
                errors.append(
                    "--require-source-runs without --repository requires --source-run-json "
                    "or --workflow-runs-json "
                    f"for {missing}"
                )
        artifact_runs = source_artifact_json_paths(args)
        if not artifact_runs:
            errors.append("--require-source-runs without --repository requires --source-artifacts-json")
    for raw in args.workflow_runs_json:
        if "=" not in str(raw):
            errors.append(f"--workflow-runs-json must be WORKFLOW=PATH, got {raw!r}")
    for raw in args.source_run_json:
        if "=" not in str(raw):
            errors.append(f"--source-run-json must be RUN=PATH, got {raw!r}")
    for raw in args.source_artifacts_json:
        if "=" not in str(raw):
            errors.append(f"--source-artifacts-json must be RUN=PATH, got {raw!r}")
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


def normalize_run_key(run: str) -> str:
    return str(run).strip().rstrip("/")


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


def github_api_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Codex"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    return headers


def check_remote_platform_release_evidence(
    *,
    registry: dict[str, Any],
    promotion: dict[str, Any],
    release: dict[str, Any],
    workflow_runs_by_workflow: dict[str, dict[str, Any]],
    source_runs_by_run: dict[str, dict[str, Any]] | None = None,
    source_artifacts_by_run: dict[str, dict[str, Any]] | None = None,
    release_tag: str,
    required_targets: tuple[str, ...],
    require_source_runs: bool = False,
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
    for target, record in records.items():
        errors.extend(
            check_published_release_asset_metadata(
                target,
                record,
                release_assets_by_name=release_assets_by_name,
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


def check_record_source_artifact(
    target: str,
    record: dict[str, Any],
    source_artifacts_by_run: dict[str, dict[str, Any]],
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
    return check_source_artifact_record(target, matches[0], record)


def check_source_artifact_record(
    target: str,
    artifact: dict[str, Any],
    record: dict[str, Any],
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
