from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_promotion_artifacts import (  # noqa: E402
    check_platform_promotion_artifacts,
    read_json,
)
from check_platform_verified_evidence import (  # noqa: E402
    LINUX_TARGETS,
    PROTECTED_GOAL_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    XP_TARGETS,
    check_linux_builder_identity,
    directory_path_has_file_suffix,
    format_values_by_target,
    release_source_workflow,
)
from check_xp_native_evidence import (  # noqa: E402
    artifact_validation_asset_dirs,
    check_xp_native_evidence,
)
from make_platform_verified_evidence_record import (  # noqa: E402
    PROMOTION_PATH,
    artifact_sha256_map,
    check_linux_smoke_evidence_file,
    linux_native_smoke_command,
)

RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_REPOSITORY_VALUE_RE = re.compile(rf"^{GITHUB_REPOSITORY_RE}$")
GITHUB_ACTIONS_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?$")
GITHUB_ACTIONS_RUN_REPOSITORY_RE = GITHUB_ACTIONS_RUN_RE
GITHUB_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FULL_GOAL_STRICT_ARTIFACTS_ERROR = (
    "full protected goal local evidence preflight must use strict artifact directories; "
    "--allow-extra-artifacts requires exactly one --target"
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = tuple(args.target or PROTECTED_GOAL_TARGETS)
    errors = check_platform_goal_local_evidence(
        root=args.root,
        release_tag=args.release_tag,
        targets=targets,
        linux_workflow_run_url=args.linux_workflow_run_url,
        linux_source_head_sha=args.linux_source_head_sha,
        linux_source_run_attempt=args.linux_source_run_attempt,
        strict_artifacts=not args.allow_extra_artifacts,
        assets_dir=args.assets_dir,
        linux_builder_evidence=args.linux_builder_evidence,
        linux_smoke_evidence=args.linux_smoke_evidence,
        xp_evidence=args.xp_evidence,
        xp_evidence_dir=args.xp_evidence_dir,
        xp_source_workflow_run_url=args.xp_source_workflow_run_url,
        xp_source_head_sha=args.xp_source_head_sha,
        xp_source_run_attempt=args.xp_source_run_attempt,
        repository=args.repository,
    )
    report = platform_goal_local_evidence_report(targets=targets, errors=errors)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if errors else 0
    if errors:
        for error in errors:
            print(f"platform goal local evidence: {error}", file=sys.stderr)
        return 1
    print(format_platform_goal_local_evidence_summary(report))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight staged local proof for protected platform promotion before "
            "generating accepted evidence records."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help=(
            "staging root containing <target>/<release-tag>/artifacts plus "
            "Linux builder/smoke evidence or XP evidence files"
        ),
    )
    parser.add_argument("--release-tag", required=True, help="release tag, for example v1.0.7")
    parser.add_argument(
        "--target",
        action="append",
        choices=PROTECTED_GOAL_TARGETS,
        help="protected target to check; repeat or omit for all four targets",
    )
    parser.add_argument(
        "--repository",
        help="expected GitHub owner/name repository for every source workflow run URL",
    )
    parser.add_argument(
        "--linux-workflow-run-url",
        help=(
            "GitHub Actions run URL that Linux builder and smoke evidence must bind; "
            "omitted values are inferred from each target's builder identity JSON"
        ),
    )
    parser.add_argument(
        "--linux-source-head-sha",
        help=(
            "40-character source commit SHA that Linux builder evidence must bind; "
            "omitted values are inferred from each target's builder identity JSON"
        ),
    )
    parser.add_argument(
        "--linux-source-run-attempt",
        type=int,
        help=(
            "positive GitHub Actions run attempt that Linux builder evidence must bind; "
            "omitted values are inferred from each target's builder identity JSON"
        ),
    )
    parser.add_argument(
        "--allow-extra-artifacts",
        action="store_true",
        help="allow files outside the exact required artifact set in each artifacts directory",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="explicit artifact directory for a single --target preflight",
    )
    parser.add_argument(
        "--linux-builder-evidence",
        type=Path,
        help="explicit Linux builder identity JSON for a single Linux --target preflight",
    )
    parser.add_argument(
        "--linux-smoke-evidence",
        type=Path,
        help="explicit Linux native smoke log for a single Linux --target preflight",
    )
    parser.add_argument(
        "--xp-evidence",
        type=Path,
        help="explicit XP evidence JSON for a single XP --target preflight",
    )
    parser.add_argument(
        "--xp-evidence-dir",
        type=Path,
        help="explicit XP smoke evidence directory for a single XP --target preflight",
    )
    parser.add_argument(
        "--xp-source-workflow-run-url",
        help="GitHub Actions run URL that the XP accepted-evidence source artifact must bind",
    )
    parser.add_argument(
        "--xp-source-head-sha",
        help="40-character source commit SHA that the XP accepted-evidence source artifact must bind",
    )
    parser.add_argument(
        "--xp-source-run-attempt",
        type=int,
        help="positive GitHub Actions run attempt that the XP accepted-evidence source artifact must bind",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable target-by-target local preflight parity report",
    )
    return parser.parse_args(argv)


def platform_goal_local_evidence_report(
    *,
    targets: tuple[object, ...],
    errors: list[str],
) -> dict[str, Any]:
    validated_targets, target_validation_errors = local_evidence_target_values(targets)
    target_errors = {target: [] for target in validated_targets}
    global_errors: list[str] = list(target_validation_errors)
    for error in errors:
        matched = False
        for target in validated_targets:
            if local_evidence_error_matches_target(error, target):
                target_errors[target].append(error)
                matched = True
                break
        if not matched:
            global_errors.append(error)

    blocked_by_global_errors = bool(global_errors)
    target_results: list[dict[str, Any]] = []
    passed_targets: list[str] = []
    failed_targets: list[str] = []
    for target in validated_targets:
        errors_for_target = target_errors[target]
        if blocked_by_global_errors and not errors_for_target:
            status = "blocked-by-global-error"
        elif errors_for_target:
            status = "failed"
        else:
            status = "passed"
            passed_targets.append(target)
        if status != "passed":
            failed_targets.append(target)
        target_results.append(
            {
                "target": target,
                "status": status,
                "errors": errors_for_target,
            }
        )

    target_count = len(validated_targets)
    passed_target_count = len(passed_targets)
    current_percent = (passed_target_count / target_count * 100.0) if target_count else 0.0
    return {
        "metric": "protected_platform_goal_local_evidence_preflight",
        "target_count": target_count,
        "passed_target_count": passed_target_count,
        "failed_target_count": len(failed_targets),
        "current_percent": round(current_percent, 1),
        "target_percent": 100.0,
        "gap_percent": round(100.0 - current_percent, 1),
        "complete": target_count > 0 and passed_target_count == target_count and not global_errors,
        "status": "local-preflight-passed" if passed_target_count == target_count and not global_errors else "missing-local-evidence",
        "passed_targets": passed_targets,
        "failed_targets": failed_targets,
        "global_errors": global_errors,
        "target_results": target_results,
    }


def format_platform_goal_local_evidence_summary(report: dict[str, Any]) -> str:
    passed_targets, target_errors = local_evidence_report_target_values(
        report.get("passed_targets", []),
        "passed_targets",
    )
    if target_errors:
        raise ValueError("; ".join(target_errors))
    targets = ", ".join(passed_targets)
    return (
        "platform goal local evidence preflight: "
        f"{report.get('passed_target_count', 0)}/{report.get('target_count', 0)} passed "
        f"({float(report.get('current_percent', 0.0)):.1f}%); "
        f"status={report.get('status', 'unknown')}; targets={targets}"
    )


def local_evidence_error_matches_target(error: str, target: str) -> bool:
    normalized = error.replace("\\", "/")
    return re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(target)}(?![A-Za-z0-9_.-])", normalized) is not None


def local_evidence_target_values(raw_targets: tuple[object, ...]) -> tuple[list[str], list[str]]:
    targets: list[str] = []
    errors: list[str] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, str) or not raw_target.strip():
            errors.append(
                "local evidence preflight target must be a non-empty string, "
                f"got {raw_target!r}"
            )
            continue
        target = raw_target.strip()
        if target not in PROTECTED_GOAL_TARGETS:
            errors.append(f"unknown protected target: {target}")
            continue
        targets.append(target)
    duplicate_targets = sorted({target for target in targets if targets.count(target) > 1})
    if duplicate_targets:
        errors.append(
            "local evidence preflight target list must not contain duplicates: "
            + ", ".join(duplicate_targets)
        )
    return targets, errors


def local_evidence_report_target_values(
    raw_targets: object,
    field_name: str,
) -> tuple[list[str], list[str]]:
    if not isinstance(raw_targets, list):
        return [], [
            f"platform goal local evidence report {field_name} must be a list of target strings"
        ]
    targets, errors = local_evidence_target_values(tuple(raw_targets))
    return targets, [
        error.replace(
            "local evidence preflight target",
            f"platform goal local evidence report {field_name} entry",
            1,
        )
        for error in errors
    ]


def local_evidence_release_tag_value(raw_release_tag: object) -> tuple[list[str], str]:
    if not isinstance(raw_release_tag, str) or not raw_release_tag:
        return [f"release_tag must be a non-empty string, got {raw_release_tag!r}"], ""
    if not RELEASE_TAG_RE.fullmatch(raw_release_tag):
        return [f"release_tag must look like vX.Y.Z: {raw_release_tag}"], ""
    return [], raw_release_tag


def local_evidence_repository_value(raw_repository: object) -> tuple[list[str], str | None]:
    if raw_repository is None:
        return [], None
    if not isinstance(raw_repository, str):
        return [f"--repository must be a string GitHub owner/name value, got {raw_repository!r}"], None
    repository = raw_repository.strip().strip("/")
    if not repository:
        return ["--repository must be a non-empty GitHub owner/name value"], None
    if not GITHUB_REPOSITORY_VALUE_RE.fullmatch(repository):
        return [f"--repository must be a GitHub owner/name value, got {raw_repository!r}"], None
    return [], repository


def local_evidence_required_path_value(raw_path: object, label: str) -> tuple[list[str], Path]:
    if not isinstance(raw_path, Path):
        return [f"{label} must be a pathlib.Path, got {raw_path!r}"], Path()
    return [], raw_path


def local_evidence_optional_path_value(raw_path: object | None, label: str) -> tuple[list[str], Path | None]:
    if raw_path is None:
        return [], None
    if not isinstance(raw_path, Path):
        return [f"{label} must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def check_platform_goal_local_evidence(
    *,
    root: object,
    release_tag: object,
    targets: tuple[object, ...] = PROTECTED_GOAL_TARGETS,
    linux_workflow_run_url: str | None = None,
    linux_source_head_sha: str | None = None,
    linux_source_run_attempt: int | None = None,
    strict_artifacts: bool = True,
    assets_dir: object | None = None,
    linux_builder_evidence: object | None = None,
    linux_smoke_evidence: object | None = None,
    xp_evidence: object | None = None,
    xp_evidence_dir: object | None = None,
    xp_source_workflow_run_url: str | None = None,
    xp_source_head_sha: str | None = None,
    xp_source_run_attempt: int | None = None,
    repository: object = None,
) -> list[str]:
    errors: list[str] = []
    release_tag_errors, release_tag_value = local_evidence_release_tag_value(release_tag)
    errors.extend(release_tag_errors)
    validated_targets, target_validation_errors = local_evidence_target_values(targets)
    errors.extend(target_validation_errors)
    if not validated_targets and not target_validation_errors:
        errors.append("at least one protected target is required for local evidence preflight")
    root_errors, root_path = local_evidence_required_path_value(root, "local evidence root")
    errors.extend(root_errors)
    assets_dir_errors, assets_dir_path = local_evidence_optional_path_value(assets_dir, "explicit artifact directory")
    errors.extend(assets_dir_errors)
    builder_errors, linux_builder_evidence_path = local_evidence_optional_path_value(
        linux_builder_evidence,
        "explicit Linux builder evidence",
    )
    errors.extend(builder_errors)
    smoke_errors, linux_smoke_evidence_path = local_evidence_optional_path_value(
        linux_smoke_evidence,
        "explicit Linux smoke evidence",
    )
    errors.extend(smoke_errors)
    xp_evidence_errors, xp_evidence_path = local_evidence_optional_path_value(
        xp_evidence,
        "explicit XP evidence file",
    )
    errors.extend(xp_evidence_errors)
    xp_evidence_dir_errors, xp_evidence_dir_path = local_evidence_optional_path_value(
        xp_evidence_dir,
        "explicit XP evidence directory",
    )
    errors.extend(xp_evidence_dir_errors)
    repository_errors, expected_repository = local_evidence_repository_value(repository)
    errors.extend(repository_errors)
    if not root_errors:
        errors.extend(check_directory_path_hint(root_path, "local evidence root"))
    if errors:
        return errors
    errors.extend(check_path_not_reserved_workspace_path(root_path, "local evidence root"))
    if errors:
        return errors
    if root_path.is_symlink():
        errors.append(f"local evidence root must not be a symlink: {root_path}")
        return errors
    root_parent_errors = check_path_parent_symlinks(root_path, "local evidence root")
    if root_parent_errors:
        errors.extend(root_parent_errors)
        return errors
    if not root_path.is_dir():
        errors.append(f"local evidence root missing: {root_path}")
        return errors
    if not strict_artifacts and len(validated_targets) != 1:
        errors.append(FULL_GOAL_STRICT_ARTIFACTS_ERROR)
        return errors
    if any(
        path is not None
        for path in (
            assets_dir_path,
            linux_builder_evidence_path,
            linux_smoke_evidence_path,
            xp_evidence_path,
            xp_evidence_dir_path,
        )
    ) and len(validated_targets) != 1:
        errors.append("explicit evidence paths require exactly one --target")
        return errors
    explicit_source_options = [
        option
        for option, value in (
            ("--linux-workflow-run-url", linux_workflow_run_url),
            ("--linux-source-head-sha", linux_source_head_sha),
            ("--linux-source-run-attempt", linux_source_run_attempt),
            ("--xp-source-workflow-run-url", xp_source_workflow_run_url),
            ("--xp-source-head-sha", xp_source_head_sha),
            ("--xp-source-run-attempt", xp_source_run_attempt),
        )
        if value is not None
    ]
    if explicit_source_options and len(validated_targets) != 1:
        errors.append(
            "explicit source binding options require exactly one --target: "
            + ", ".join(explicit_source_options)
        )
        return errors

    promotion = read_json(PROMOTION_PATH)
    for target in validated_targets:
        if target in LINUX_TARGETS:
            errors.extend(
                check_linux_local_evidence(
                    root=root_path,
                    release_tag=release_tag_value,
                    target=target,
                    promotion=promotion,
                    workflow_run_url=linux_workflow_run_url,
                    source_head_sha=linux_source_head_sha,
                    source_run_attempt=linux_source_run_attempt,
                    strict_artifacts=strict_artifacts,
                    assets_dir=assets_dir_path,
                    builder_evidence=linux_builder_evidence_path,
                    smoke_evidence=linux_smoke_evidence_path,
                )
            )
        elif target in XP_TARGETS:
            errors.extend(
                check_xp_local_evidence(
                    root=root_path,
                    release_tag=release_tag_value,
                    target=target,
                    strict_artifacts=strict_artifacts,
                    assets_dir=assets_dir_path,
                    evidence_file=xp_evidence_path,
                    evidence_dir=xp_evidence_dir_path,
                    source_workflow_run_url=xp_source_workflow_run_url,
                    source_head_sha=xp_source_head_sha,
                    source_run_attempt=xp_source_run_attempt,
                )
            )
        else:
            errors.append(f"unknown protected target: {target}")
    if not errors:
        errors.extend(
            check_multi_target_release_source_scope(
                root=root_path,
                release_tag=release_tag_value,
                targets=tuple(validated_targets),
                linux_workflow_run_url=linux_workflow_run_url,
                linux_source_head_sha=linux_source_head_sha,
                linux_source_run_attempt=linux_source_run_attempt,
                xp_source_workflow_run_url=xp_source_workflow_run_url,
                xp_source_head_sha=xp_source_head_sha,
                xp_source_run_attempt=xp_source_run_attempt,
                repository=expected_repository,
            )
        )
    return errors


def check_multi_target_release_source_scope(
    *,
    root: Path,
    release_tag: str,
    targets: tuple[str, ...],
    linux_workflow_run_url: str | None,
    linux_source_head_sha: str | None,
    linux_source_run_attempt: int | None,
    xp_source_workflow_run_url: str | None,
    xp_source_head_sha: str | None,
    xp_source_run_attempt: int | None,
    repository: str | None = None,
) -> list[str]:
    bindings = local_release_source_bindings(
        root=root,
        release_tag=release_tag,
        targets=targets,
        linux_workflow_run_url=linux_workflow_run_url,
        linux_source_head_sha=linux_source_head_sha,
        linux_source_run_attempt=linux_source_run_attempt,
        xp_source_workflow_run_url=xp_source_workflow_run_url,
        xp_source_head_sha=xp_source_head_sha,
        xp_source_run_attempt=xp_source_run_attempt,
    )
    errors: list[str] = []
    if repository is not None:
        repositories_by_target = {
            target: binding["repository"]
            for target, binding in bindings.items()
            if binding.get("repository")
        }
        mismatched = {
            target: actual_repository
            for target, actual_repository in repositories_by_target.items()
            if actual_repository != repository
        }
        if mismatched or len(repositories_by_target) != len(targets):
            errors.append(
                "local protected platform evidence source repository must match "
                f"--repository {repository}, got {format_values_by_target(repositories_by_target)}"
            )
    if len(targets) < 2:
        return errors
    heads_by_target = {
        target: binding["head_sha"]
        for target, binding in bindings.items()
        if binding.get("head_sha")
    }
    if len(heads_by_target) == len(targets) and len(set(heads_by_target.values())) != 1:
        errors.append(
            "local protected platform evidence must use one release source head SHA "
            f"before promotion, got {format_values_by_target(heads_by_target)}"
        )
    repositories_by_target = {
        target: binding["repository"]
        for target, binding in bindings.items()
        if binding.get("repository")
    }
    if len(repositories_by_target) == len(targets) and len(set(repositories_by_target.values())) != 1:
        errors.append(
            "local protected platform evidence must use one GitHub repository "
            f"before promotion, got {format_values_by_target(repositories_by_target)}"
        )
    workflow_run_urls = {
        target: binding["workflow_run_url"]
        for target, binding in bindings.items()
        if binding.get("workflow_run_url") and binding.get("run_attempt")
    }
    for workflow_run_url in sorted(set(workflow_run_urls.values())):
        attempts_by_target = {
            target: bindings[target]["run_attempt"]
            for target, target_workflow_run_url in workflow_run_urls.items()
            if target_workflow_run_url == workflow_run_url
        }
        if len(attempts_by_target) > 1 and len(set(attempts_by_target.values())) != 1:
            errors.append(
                "local protected platform evidence must use one source run attempt per workflow run URL "
                f"before promotion: {workflow_run_url} got {format_values_by_target(attempts_by_target)}"
            )
    return errors


def local_release_source_bindings(
    *,
    root: Path,
    release_tag: str,
    targets: tuple[str, ...],
    linux_workflow_run_url: str | None,
    linux_source_head_sha: str | None,
    linux_source_run_attempt: int | None,
    xp_source_workflow_run_url: str | None,
    xp_source_head_sha: str | None,
    xp_source_run_attempt: int | None,
) -> dict[str, dict[str, str]]:
    bindings: dict[str, dict[str, str]] = {}
    for target in targets:
        if target in LINUX_TARGETS:
            raw_workflow_run_url: object = linux_workflow_run_url
            raw_head_sha: object = linux_source_head_sha
            raw_run_attempt: object = linux_source_run_attempt
            if raw_workflow_run_url is None or raw_head_sha is None or raw_run_attempt is None:
                builder_path = root / target / release_tag / f"builder-identity-{target}.json"
                builder = read_json(builder_path) if builder_path.is_file() else {}
                if raw_workflow_run_url is None:
                    raw_workflow_run_url = builder.get("workflow_run_url", "")
                if raw_head_sha is None:
                    raw_head_sha = builder.get("source_head_sha", "")
                if raw_run_attempt is None:
                    raw_run_attempt = builder.get("workflow_run_attempt")
        elif target in XP_TARGETS:
            raw_workflow_run_url = xp_source_workflow_run_url
            raw_head_sha = xp_source_head_sha
            raw_run_attempt = xp_source_run_attempt
            if raw_workflow_run_url is None or raw_head_sha is None or raw_run_attempt is None:
                evidence_path = root / target / release_tag / "xp-evidence.json"
                evidence = read_json(evidence_path) if evidence_path.is_file() else {}
                source = evidence.get("release_source") if isinstance(evidence, dict) else {}
                source = source if isinstance(source, dict) else {}
                if raw_workflow_run_url is None:
                    raw_workflow_run_url = source.get("workflow_run_url", "")
                if raw_head_sha is None:
                    raw_head_sha = source.get("head_sha", "")
                if raw_run_attempt is None:
                    raw_run_attempt = source.get("run_attempt")
        else:
            continue
        workflow_run_url = typed_release_source_string(raw_workflow_run_url)
        head_sha = typed_release_source_string(raw_head_sha)
        bindings[target] = {
            "workflow_run_url": workflow_run_url,
            "repository": repository_from_workflow_run_url(workflow_run_url),
            "head_sha": head_sha,
            "run_attempt": typed_release_source_run_attempt(raw_run_attempt),
        }
    return bindings


def typed_release_source_string(raw_value: object) -> str:
    if not isinstance(raw_value, str):
        return ""
    return raw_value


def typed_release_source_run_attempt(raw_value: object) -> str:
    if not isinstance(raw_value, int) or isinstance(raw_value, bool) or raw_value < 1:
        return ""
    return str(raw_value)


def repository_from_workflow_run_url(workflow_run_url: str) -> str:
    if workflow_run_url != workflow_run_url.strip() or workflow_run_url != workflow_run_url.rstrip("/"):
        return ""
    match = GITHUB_ACTIONS_RUN_REPOSITORY_RE.fullmatch(workflow_run_url)
    return match.group(1) if match else ""


def check_linux_local_evidence(
    *,
    root: object,
    release_tag: str,
    target: str,
    promotion: dict[str, Any],
    workflow_run_url: str | None,
    source_head_sha: str | None,
    source_run_attempt: object,
    strict_artifacts: bool,
    assets_dir: object | None = None,
    builder_evidence: object | None = None,
    smoke_evidence: object | None = None,
) -> list[str]:
    errors: list[str] = []
    root_errors, root_path = local_evidence_required_path_value(root, "local evidence root")
    assets_dir_errors, assets_dir_path = local_evidence_optional_path_value(
        assets_dir,
        f"{target} artifact directory",
    )
    builder_errors, builder_evidence_path = local_evidence_optional_path_value(
        builder_evidence,
        f"{target} builder identity evidence",
    )
    smoke_errors, smoke_evidence_path = local_evidence_optional_path_value(
        smoke_evidence,
        f"{target} native smoke evidence",
    )
    errors.extend(root_errors)
    errors.extend(assets_dir_errors)
    errors.extend(builder_errors)
    errors.extend(smoke_errors)
    if errors:
        return errors
    assert root_path is not None
    target_dir = root_path / target
    target_root = target_dir / release_tag
    artifacts_dir = assets_dir_path or target_root / "artifacts"
    builder_evidence = builder_evidence_path or target_root / f"builder-identity-{target}.json"
    smoke_evidence = smoke_evidence_path or target_root / f"native-smoke-{target}.log"
    if target_dir.is_symlink():
        errors.append(f"{target} local Linux evidence target directory must not be a symlink: {target_dir}")
    if target_root.is_symlink():
        errors.append(f"{target} local Linux evidence release directory must not be a symlink: {target_root}")
    errors.extend(check_directory_path_hint(artifacts_dir, f"{target} artifact directory"))
    if errors:
        return errors
    errors.extend(check_path_parent_symlinks(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_parent_symlinks(builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_parent_symlinks(smoke_evidence, f"{target} native smoke evidence"))
    errors.extend(check_path_inside_root(root_path, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_root(root_path, builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_inside_root(root_path, smoke_evidence, f"{target} native smoke evidence"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, smoke_evidence, f"{target} native smoke evidence"))
    errors.extend(check_path_inside_target_root(target_root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_target_root(target_root, builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_inside_target_root(target_root, smoke_evidence, f"{target} native smoke evidence"))
    if errors:
        return errors
    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=artifacts_dir,
            tag=release_tag,
            strict=strict_artifacts,
            promotion=promotion,
        )
    )
    infer_linux_bindings = builder_evidence.is_file() and builder_evidence.name == f"builder-identity-{target}.json"
    if not workflow_run_url and not infer_linux_bindings:
        errors.append(f"{target} --linux-workflow-run-url is required for local Linux evidence preflight")
    elif workflow_run_url is not None and not isinstance(workflow_run_url, str):
        errors.append(f"{target} --linux-workflow-run-url must be a string")
    elif workflow_run_url and (
        workflow_run_url != workflow_run_url.strip() or workflow_run_url != workflow_run_url.rstrip("/")
    ):
        errors.append(
            f"{target} --linux-workflow-run-url must be canonical without "
            "surrounding whitespace or trailing slash"
        )
    elif workflow_run_url and not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url):
        errors.append(f"{target} --linux-workflow-run-url must be a GitHub Actions run URL")
    if not source_head_sha and not infer_linux_bindings:
        errors.append(f"{target} --linux-source-head-sha is required for local Linux evidence preflight")
    elif source_head_sha is not None and not isinstance(source_head_sha, str):
        errors.append(f"{target} --linux-source-head-sha must be a string")
    elif source_head_sha and source_head_sha != source_head_sha.strip():
        errors.append(f"{target} --linux-source-head-sha must not include surrounding whitespace")
    elif source_head_sha and not GITHUB_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{target} --linux-source-head-sha must be a 40-character lowercase Git SHA")
    if source_run_attempt is None and not infer_linux_bindings:
        errors.append(f"{target} --linux-source-run-attempt is required for local Linux evidence preflight")
    elif source_run_attempt is not None and (
        not isinstance(source_run_attempt, int)
        or isinstance(source_run_attempt, bool)
        or source_run_attempt < 1
    ):
        errors.append(f"{target} --linux-source-run-attempt must be a positive integer")
    if builder_evidence.is_symlink():
        errors.append(f"{target} builder identity evidence must not be a symlink: {builder_evidence}")
    elif not builder_evidence.is_file():
        errors.append(f"{target} builder identity evidence missing: {builder_evidence}")
    elif builder_evidence.name != f"builder-identity-{target}.json":
        errors.append(
            f"{target} builder identity evidence file name must be "
            f"builder-identity-{target}.json: {builder_evidence}"
        )
    if smoke_evidence.is_symlink():
        errors.append(f"{target} native smoke evidence must not be a symlink: {smoke_evidence}")
    elif not smoke_evidence.is_file():
        errors.append(f"{target} native smoke evidence missing: {smoke_evidence}")
    elif smoke_evidence.name != f"native-smoke-{target}.log":
        errors.append(
            f"{target} native smoke evidence file name must be "
            f"native-smoke-{target}.log: {smoke_evidence}"
        )
    if errors:
        return errors

    builder_identity, json_errors = read_json_object(builder_evidence, f"{target} builder identity evidence")
    if json_errors:
        return json_errors
    raw_resolved_workflow_run_url = (
        workflow_run_url
        if workflow_run_url is not None
        else builder_identity.get("workflow_run_url", "")
    )
    resolved_workflow_run_url = raw_resolved_workflow_run_url
    raw_resolved_source_head_sha = (
        source_head_sha
        if source_head_sha is not None
        else builder_identity.get("source_head_sha", "")
    )
    resolved_source_head_sha = raw_resolved_source_head_sha
    resolved_source_run_attempt = (
        source_run_attempt
        if source_run_attempt is not None
        else builder_identity.get("workflow_run_attempt")
    )
    errors.extend(
        check_linux_resolved_run_bindings(
            target,
            workflow_run_url=resolved_workflow_run_url,
            source_head_sha=resolved_source_head_sha,
            source_run_attempt=resolved_source_run_attempt,
            inferred_workflow_run_url=not workflow_run_url,
            inferred_source_head_sha=not source_head_sha,
            inferred_source_run_attempt=source_run_attempt is None,
        )
    )
    if errors:
        return errors
    if not isinstance(resolved_workflow_run_url, str) or not isinstance(resolved_source_head_sha, str):
        return errors
    errors.extend(
        check_linux_builder_identity(
            target,
            builder_identity,
            LINUX_TARGETS[target]["machine_names"],
            release_tag=release_tag,
            workflow_run_url=resolved_workflow_run_url,
            workflow_run_attempt=resolved_source_run_attempt,
            source_head_sha=resolved_source_head_sha,
        )
    )
    artifact_hashes = artifact_sha256_map(target, release_tag, artifacts_dir, promotion)
    errors.extend(
        check_linux_smoke_evidence_file(
            target,
            release_tag,
            linux_native_smoke_command(
                target,
                promotion,
                resolved_workflow_run_url,
                int(resolved_source_run_attempt),
                resolved_source_head_sha,
                builder_evidence,
            ),
            resolved_workflow_run_url,
            int(resolved_source_run_attempt),
            smoke_evidence,
            source_head_sha=resolved_source_head_sha,
            artifact_sha256=artifact_hashes,
            builder_identity=builder_identity,
        )
    )
    return errors


def check_linux_resolved_run_bindings(
    target: str,
    *,
    workflow_run_url: object,
    source_head_sha: object,
    source_run_attempt: object,
    inferred_workflow_run_url: bool,
    inferred_source_head_sha: bool,
    inferred_source_run_attempt: bool,
) -> list[str]:
    errors: list[str] = []
    workflow_label = (
        "builder_identity.workflow_run_url"
        if inferred_workflow_run_url
        else "--linux-workflow-run-url"
    )
    source_label = (
        "builder_identity.source_head_sha"
        if inferred_source_head_sha
        else "--linux-source-head-sha"
    )
    attempt_label = (
        "builder_identity.workflow_run_attempt"
        if inferred_source_run_attempt
        else "--linux-source-run-attempt"
    )
    if workflow_run_url is None or workflow_run_url == "":
        errors.append(f"{target} {workflow_label} is required for local Linux evidence preflight")
    elif not isinstance(workflow_run_url, str):
        errors.append(f"{target} {workflow_label} must be a string")
    elif workflow_run_url != workflow_run_url.strip() or workflow_run_url != workflow_run_url.rstrip("/"):
        errors.append(
            f"{target} {workflow_label} must be canonical without surrounding whitespace or trailing slash"
        )
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url):
        errors.append(f"{target} {workflow_label} must be a GitHub Actions run URL")
    if source_head_sha is None or source_head_sha == "":
        errors.append(f"{target} {source_label} is required for local Linux evidence preflight")
    elif not isinstance(source_head_sha, str):
        errors.append(f"{target} {source_label} must be a string")
    elif source_head_sha != source_head_sha.strip():
        errors.append(f"{target} {source_label} must not include surrounding whitespace")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{target} {source_label} must be a 40-character lowercase Git SHA")
    if (
        not isinstance(source_run_attempt, int)
        or isinstance(source_run_attempt, bool)
        or source_run_attempt < 1
    ):
        errors.append(f"{target} {attempt_label} must be a positive integer")
    return errors


def check_xp_local_evidence(
    *,
    root: object,
    release_tag: str,
    target: str,
    strict_artifacts: bool,
    assets_dir: object | None = None,
    evidence_file: object | None = None,
    evidence_dir: object | None = None,
    source_workflow_run_url: str | None = None,
    source_head_sha: str | None = None,
    source_run_attempt: int | None = None,
) -> list[str]:
    errors: list[str] = []
    root_errors, root_path = local_evidence_required_path_value(root, "local evidence root")
    assets_dir_errors, assets_dir_path = local_evidence_optional_path_value(
        assets_dir,
        f"{target} artifact directory",
    )
    evidence_file_errors, evidence_file_path = local_evidence_optional_path_value(
        evidence_file,
        f"{target} XP evidence file",
    )
    evidence_dir_errors, evidence_dir_path = local_evidence_optional_path_value(
        evidence_dir,
        f"{target} XP evidence directory",
    )
    errors.extend(root_errors)
    errors.extend(assets_dir_errors)
    errors.extend(evidence_file_errors)
    errors.extend(evidence_dir_errors)
    if errors:
        return errors
    assert root_path is not None
    target_dir = root_path / target
    target_root = target_dir / release_tag
    artifacts_dir = assets_dir_path or target_root / "artifacts"
    evidence_file = evidence_file_path or target_root / "xp-evidence.json"
    evidence_dir = evidence_dir_path or target_root
    if target_dir.is_symlink():
        errors.append(f"{target} XP evidence target directory must not be a symlink: {target_dir}")
    if target_root.is_symlink():
        errors.append(f"{target} XP evidence release directory must not be a symlink: {target_root}")
    errors.extend(check_directory_path_hint(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_directory_path_hint(evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    errors.extend(check_path_parent_symlinks(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_parent_symlinks(evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_parent_symlinks(evidence_dir, f"{target} XP evidence directory"))
    errors.extend(check_path_inside_root(root_path, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_root(root_path, evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_inside_root(root_path, evidence_dir, f"{target} XP evidence directory"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_not_reserved_workspace_root(root_path, evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    if evidence_file.is_symlink():
        errors.append(f"{target} XP evidence file must not be a symlink: {evidence_file}")
    if evidence_dir.is_symlink():
        errors.append(f"{target} XP evidence directory must not be a symlink: {evidence_dir}")
    if errors:
        return errors
    errors.extend(check_path_inside_target_root(target_root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_target_root(target_root, evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_inside_target_root(target_root, evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=artifacts_dir,
            tag=release_tag,
            strict=strict_artifacts,
        )
    )
    if not evidence_file.is_file():
        errors.append(f"{target} XP evidence file missing: {evidence_file}")
        errors.extend(
            check_xp_source_bindings(
                target,
                workflow_run_url=source_workflow_run_url,
                source_head_sha=source_head_sha,
                source_run_attempt=source_run_attempt,
            )
        )
    if errors:
        return errors
    evidence, json_errors = read_json_object(evidence_file, f"{target} XP evidence")
    if json_errors:
        return json_errors
    errors.extend(
        check_xp_resolved_source_bindings(
            target,
            evidence,
            workflow_run_url=source_workflow_run_url,
            source_head_sha=source_head_sha,
            source_run_attempt=source_run_attempt,
        )
    )
    if errors:
        return errors
    errors.extend(
        check_xp_native_evidence(
            evidence_file,
            assets_dir=artifacts_dir,
            evidence_dir=evidence_dir,
        )
    )
    if isinstance(evidence, dict) and evidence.get("release_tag") != release_tag:
        errors.append(
            f"{target} XP evidence release_tag must match --release-tag {release_tag}, "
            f"got {evidence.get('release_tag')!r}"
        )
    if isinstance(evidence, dict):
        asset_dirs = artifact_validation_asset_dirs(evidence)
        expected_assets_dir = local_evidence_path_value(root, artifacts_dir)
        if asset_dirs != [expected_assets_dir]:
            errors.append(
                f"{target} XP evidence artifact_validation.command --assets-dir must match "
                f"local artifacts path {expected_assets_dir}, got {asset_dirs}"
            )
    return errors


def check_xp_source_bindings(
    target: str,
    *,
    workflow_run_url: object,
    source_head_sha: object,
    source_run_attempt: object,
    workflow_label: str = "--xp-source-workflow-run-url",
    source_label: str = "--xp-source-head-sha",
    attempt_label: str = "--xp-source-run-attempt",
) -> list[str]:
    errors: list[str] = []
    if workflow_run_url is None or workflow_run_url == "":
        errors.append(f"{target} {workflow_label} is required for local XP evidence preflight")
    elif not isinstance(workflow_run_url, str):
        errors.append(f"{target} {workflow_label} must be a string")
    elif workflow_run_url != workflow_run_url.strip() or workflow_run_url != workflow_run_url.rstrip("/"):
        errors.append(
            f"{target} {workflow_label} must be canonical without surrounding whitespace or trailing slash"
        )
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url):
        errors.append(f"{target} {workflow_label} must be a GitHub Actions run URL")
    if source_head_sha is None or source_head_sha == "":
        errors.append(f"{target} {source_label} is required for local XP evidence preflight")
    elif not isinstance(source_head_sha, str):
        errors.append(f"{target} {source_label} must be a string")
    elif source_head_sha != source_head_sha.strip():
        errors.append(f"{target} {source_label} must not include surrounding whitespace")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{target} {source_label} must be a 40-character lowercase Git SHA")
    if source_run_attempt is None:
        errors.append(f"{target} {attempt_label} is required for local XP evidence preflight")
    elif not isinstance(source_run_attempt, int) or isinstance(source_run_attempt, bool) or source_run_attempt < 1:
        errors.append(f"{target} {attempt_label} must be a positive integer")
    return errors


def check_xp_resolved_source_bindings(
    target: str,
    evidence: dict[str, Any],
    *,
    workflow_run_url: str | None,
    source_head_sha: str | None,
    source_run_attempt: int | None,
) -> list[str]:
    source = evidence.get("release_source") if isinstance(evidence, dict) else None
    if not isinstance(source, dict):
        return [f"{target} XP evidence release_source must be an object for local XP evidence preflight"]

    raw_workflow_run_url = source.get("workflow_run_url")
    raw_source_head_sha = source.get("head_sha")
    actual_source_run_attempt = source.get("run_attempt")
    raw_workflow = source.get("workflow")
    actual_workflow_run_url = raw_workflow_run_url
    actual_source_head_sha = raw_source_head_sha
    actual_workflow = raw_workflow
    expected_workflow = release_source_workflow(target)
    explicit_workflow_run_url = workflow_run_url is not None and workflow_run_url != ""
    explicit_source_head_sha = source_head_sha is not None and source_head_sha != ""
    expected_workflow_run_url = actual_workflow_run_url
    if explicit_workflow_run_url:
        expected_workflow_run_url = workflow_run_url
    expected_source_head_sha = actual_source_head_sha
    if explicit_source_head_sha:
        expected_source_head_sha = source_head_sha
    expected_source_run_attempt: object = (
        source_run_attempt if source_run_attempt is not None else actual_source_run_attempt
    )
    errors = check_xp_source_bindings(
        target,
        workflow_run_url=expected_workflow_run_url,
        source_head_sha=expected_source_head_sha,
        source_run_attempt=expected_source_run_attempt,
        workflow_label=(
            "--xp-source-workflow-run-url"
            if explicit_workflow_run_url
            else "XP evidence release_source.workflow_run_url"
        ),
        source_label=(
            "--xp-source-head-sha"
            if explicit_source_head_sha
            else "XP evidence release_source.head_sha"
        ),
        attempt_label=(
            "--xp-source-run-attempt"
            if source_run_attempt is not None
            else "XP evidence release_source.run_attempt"
        ),
    )
    if not isinstance(actual_workflow, str):
        errors.append(f"{target} XP evidence release_source.workflow must be a string")
    elif actual_workflow != actual_workflow.strip():
        errors.append(
            f"{target} XP evidence release_source.workflow must not include surrounding whitespace"
        )
    elif actual_workflow != expected_workflow:
        errors.append(
            f"{target} XP evidence release_source.workflow must be {expected_workflow}, "
            f"got {actual_workflow!r}"
        )
    if (
        explicit_workflow_run_url
        and isinstance(expected_workflow_run_url, str)
        and actual_workflow_run_url != expected_workflow_run_url
    ):
        errors.append(
            f"{target} XP evidence release_source.workflow_run_url must match "
            f"--xp-source-workflow-run-url {expected_workflow_run_url}, got {actual_workflow_run_url!r}"
        )
    if (
        explicit_source_head_sha
        and isinstance(expected_source_head_sha, str)
        and actual_source_head_sha != expected_source_head_sha
    ):
        errors.append(
            f"{target} XP evidence release_source.head_sha must match "
            f"--xp-source-head-sha {expected_source_head_sha}, got {actual_source_head_sha!r}"
        )
    if source_run_attempt is not None and actual_source_run_attempt != expected_source_run_attempt:
        errors.append(
            f"{target} XP evidence release_source.run_attempt must match "
            f"--xp-source-run-attempt {expected_source_run_attempt}, got {actual_source_run_attempt!r}"
        )
    return errors


def local_evidence_path_value(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_json_object(path: object, label: str) -> tuple[dict[str, Any], list[str]]:
    path_errors, path_value = local_evidence_required_path_value(path, label)
    if path_errors:
        return {}, path_errors
    assert path_value is not None
    try:
        data = json.loads(path_value.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, [f"{label} is not readable JSON: {path_value}: {exc}"]
    except UnicodeDecodeError as exc:
        return {}, [f"{label} must be UTF-8 JSON: {path_value}: {exc}"]
    except json.JSONDecodeError as exc:
        return {}, [f"{label} is not valid JSON: {path_value}: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{label} must contain a JSON object: {path_value}"]
    return data, []


def check_path_inside_root(root: object, path: object, label: str) -> list[str]:
    root_errors, root_path = local_evidence_required_path_value(root, "local evidence root")
    path_errors, path_value = local_evidence_required_path_value(path, label)
    errors = root_errors + path_errors
    if errors:
        return errors
    assert root_path is not None
    assert path_value is not None
    root_resolved = root_path.resolve(strict=False)
    path_resolved = path_value.resolve(strict=False)
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError:
        return [f"{label} must stay inside local evidence root: {path_value}"]
    return []


def check_path_inside_target_root(target_root: object, path: object, label: str) -> list[str]:
    target_root_errors, target_root_path = local_evidence_required_path_value(
        target_root,
        "target release directory",
    )
    path_errors, path_value = local_evidence_required_path_value(path, label)
    errors = target_root_errors + path_errors
    if errors:
        return errors
    assert target_root_path is not None
    assert path_value is not None
    target_root_resolved = target_root_path.resolve(strict=False)
    path_resolved = path_value.resolve(strict=False)
    target = target_root_path.name
    release_tag = ""
    root_resolved = target_root_resolved.parent
    if target_root_path.parent != target_root_path:
        target = target_root_path.parent.name
        release_tag = target_root_path.name
        root_resolved = target_root_resolved.parent.parent
    try:
        relative = path_resolved.relative_to(root_resolved)
    except ValueError:
        return [f"{label} must stay inside local evidence root: {path_value}"]
    parts = relative.parts
    if target and release_tag:
        for index, part in enumerate(parts[:-1]):
            if part == target and parts[index + 1] == release_tag:
                return []
        return [
            f"{label} must include target/release path segment "
            f"{target}/{release_tag} under local evidence root: {path_value}"
        ]
    return []


def check_path_not_reserved_workspace_root(root: object, path: object, label: str) -> list[str]:
    root_errors, root_path = local_evidence_required_path_value(root, "local evidence root")
    path_errors, path_value = local_evidence_required_path_value(path, label)
    errors = root_errors + path_errors
    if errors:
        return errors
    assert root_path is not None
    assert path_value is not None
    root_resolved = root_path.resolve(strict=False)
    path_resolved = path_value.resolve(strict=False)
    try:
        relative = path_resolved.relative_to(root_resolved)
    except ValueError:
        return []
    parts = tuple(part for part in relative.parts if part not in ("", "."))
    if not parts:
        return []
    reserved_root = parts[0]
    if reserved_root in RESERVED_WORKSPACE_ROOTS:
        return [
            f"{label} must not point inside reserved workspace directory "
            f"{reserved_root!r}: {path_value}"
        ]
    return []


def check_path_not_reserved_workspace_path(path: object, label: str) -> list[str]:
    path_errors, path_value = local_evidence_required_path_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    raw_parts = [
        str(part)
        for part in path_value.parts
        if str(part) not in ("", ".", path_value.anchor)
    ]
    for part in raw_parts:
        if part in RESERVED_WORKSPACE_ROOTS:
            return [
                f"{label} must not point inside reserved workspace directory "
                f"{part!r}: {path_value}"
            ]
    return []


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def check_path_parent_symlinks(path: object, label: str) -> list[str]:
    path_errors, path_value = local_evidence_required_path_value(path, label)
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
    path_errors, path_value = local_evidence_required_path_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    raw_path = path_value.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
