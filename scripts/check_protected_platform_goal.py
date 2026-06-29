from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    PROTECTED_GOAL_TARGETS,
    check_platform_verified_evidence,
    read_json,
)
from check_product_readiness import check_protected_requirement_commands  # noqa: E402
from check_release_publish_assets import check_release_assets  # noqa: E402

from remote_ops_workspace.features import _platform_verified_readiness  # noqa: E402

RELEASE_MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
REQUIRE_COMPLETE_RELEASE_TAG_ERROR = "--require-complete requires --release-tag vX.Y.Z"
REQUIRE_ASSETS_COMPLETE_ERROR = "--assets-dir requires --require-complete"
REQUIRE_ASSETS_RELEASE_TAG_ERROR = "--assets-dir requires --release-tag vX.Y.Z"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    arg_errors = strict_completion_arg_errors(args)
    if arg_errors:
        for error in arg_errors:
            print(f"protected platform goal: {error}", file=sys.stderr)
        return 2
    registry = read_json(args.registry)
    errors, goal = check_protected_platform_goal(
        registry=registry,
        release_tag=args.release_tag,
        require_complete=args.require_complete,
        assets_dir=args.assets_dir,
    )
    if args.json:
        print(json.dumps(goal, indent=2, sort_keys=True))
    else:
        print(format_goal_summary(goal))
        scope = format_goal_scope(goal)
        if scope:
            print(scope)
        if goal["missing_targets"]:
            print(f"missing targets: {', '.join(goal['missing_targets'])}")
        if args.require_complete or args.show_requirements:
            requirements = format_goal_requirements(goal)
            if requirements:
                print(requirements)
    if errors:
        for error in errors:
            print(f"protected platform goal: {error}", file=sys.stderr)
        return 1
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report or gate the protected platform goal for Linux i386, Linux armhf, "
            "Windows XP native x86, and Windows XP native x64."
        )
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=EVIDENCE_PATH,
        help="accepted platform evidence registry JSON",
    )
    parser.add_argument(
        "--release-tag",
        help="Report or require accepted evidence for this exact release tag.",
    )
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "Fail unless all protected goal targets have accepted evidence for "
            "--release-tag; requires --release-tag."
        ),
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help=(
            "Downloaded release asset directory to validate with --require-complete. "
            "This proves the accepted final records, review bundles, and native assets "
            "are present in the actual release output."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the protected goal parity block as JSON.",
    )
    parser.add_argument(
        "--show-requirements",
        action="store_true",
        help=(
            "Print a concise per-target proof checklist from "
            "platform_verified_readiness.protected_goal_parity."
        ),
    )
    return parser.parse_args(argv)


def strict_completion_arg_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.require_complete and not args.release_tag:
        errors.append(REQUIRE_COMPLETE_RELEASE_TAG_ERROR)
    if args.assets_dir is not None and not args.require_complete:
        errors.append(REQUIRE_ASSETS_COMPLETE_ERROR)
    if (
        args.assets_dir is not None
        and not args.release_tag
        and REQUIRE_COMPLETE_RELEASE_TAG_ERROR not in errors
    ):
        errors.append(REQUIRE_ASSETS_RELEASE_TAG_ERROR)
    return errors


def check_protected_platform_goal(
    *,
    registry: dict[str, Any],
    release_tag: str | None = None,
    require_complete: bool = False,
    assets_dir: Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    validation_errors: list[str] = []
    record_validation_errors: list[str] = []
    release_asset_validation_errors: list[str] = []
    report_validation_errors: list[str] = []
    release_tag_valid = release_tag is None or re.fullmatch(r"v\d+\.\d+\.\d+", release_tag)
    if release_tag is not None and not release_tag_valid:
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag}")
    if require_complete and release_tag is None:
        errors.append(REQUIRE_COMPLETE_RELEASE_TAG_ERROR)
    if assets_dir is not None and not require_complete:
        errors.append(REQUIRE_ASSETS_COMPLETE_ERROR)
    if assets_dir is not None and release_tag is None:
        errors.append(REQUIRE_ASSETS_RELEASE_TAG_ERROR)
    if not (require_complete and release_tag is None):
        record_validation_errors.extend(
            check_platform_verified_evidence(
                registry=registry,
                require_review_bundles=True,
                check_consistency=False,
            )
        )
        validation_errors.extend(
            check_platform_verified_evidence(
                registry=registry,
                required_targets=PROTECTED_GOAL_TARGETS if require_complete else None,
                required_release_tag=release_tag,
                require_review_bundles=True,
            )
        )
        errors.extend(validation_errors)
    if assets_dir is not None and require_complete and release_tag is not None and release_tag_valid:
        release_asset_validation_errors.extend(
            check_release_assets(
                assets_dir,
                read_release_matrix(),
                tag=release_tag,
                evidence_registry=registry,
                require_platform_goal_targets=True,
            )
        )
        errors.extend(release_asset_validation_errors)
    goal_source_registry = invalid_evidence_goal_registry(registry) if record_validation_errors else registry
    goal_registry = strict_goal_registry(goal_source_registry, release_tag, require_complete=require_complete)
    goal = _platform_verified_readiness(evidence_registry=goal_registry)["protected_goal_parity"]
    report_validation_errors.extend(check_goal_requirement_metadata(goal))
    errors.extend(report_validation_errors)
    if release_tag is not None:
        goal = dict(goal)
        apply_required_release_tag(goal, release_tag)
    elif require_complete:
        goal = dict(goal)
        goal["complete"] = False
        goal["status"] = "release-tag-required"
        goal["scope_error"] = REQUIRE_COMPLETE_RELEASE_TAG_ERROR
    if release_asset_validation_errors and goal.get("complete"):
        goal = mark_release_assets_invalid(goal, release_asset_validation_errors)
    if report_validation_errors and goal.get("complete"):
        goal = mark_requirement_metadata_invalid(goal, report_validation_errors)
    if require_complete and not goal.get("complete"):
        missing_targets = list_values(goal.get("missing_targets"))
        if missing_targets:
            missing = ", ".join(missing_targets)
            errors.append(f"protected platform goal is incomplete: missing {missing}")
        elif not release_asset_validation_errors:
            errors.append(
                f"protected platform goal is incomplete: status={goal.get('status')}"
            )
    goal = attach_goal_error_context(
        goal,
        validation_errors=validation_errors,
        record_validation_errors=record_validation_errors,
        release_asset_validation_errors=release_asset_validation_errors,
        report_validation_errors=report_validation_errors,
        release_assets_dir=assets_dir,
        blocking_errors=errors,
    )
    return errors, goal


def mark_release_assets_invalid(
    goal: dict[str, Any],
    release_asset_validation_errors: list[str],
) -> dict[str, Any]:
    downgraded = dict(goal)
    downgraded["complete"] = False
    downgraded["status"] = "release-assets-invalid"
    downgraded["release_asset_provenance_complete"] = False
    downgraded["release_asset_error_count"] = len(
        unique_messages(release_asset_validation_errors)
    )
    return downgraded


def mark_requirement_metadata_invalid(
    goal: dict[str, Any],
    report_validation_errors: list[str],
) -> dict[str, Any]:
    downgraded = dict(goal)
    downgraded["complete"] = False
    downgraded["status"] = "requirement-metadata-invalid"
    downgraded["requirement_metadata_complete"] = False
    downgraded["requirement_metadata_error_count"] = len(
        unique_messages(report_validation_errors)
    )
    return downgraded


def check_goal_requirement_metadata(goal: dict[str, Any]) -> list[str]:
    requirements = goal.get("target_evidence_requirements")
    if not isinstance(requirements, list):
        return ["protected platform goal parity must expose target_evidence_requirements"]
    errors: list[str] = []
    for item in requirements:
        if not isinstance(item, dict):
            errors.append("protected platform goal parity requirement entries must be objects")
            continue
        target = item.get("target")
        errors.extend(
            check_protected_requirement_commands(
                target,
                item.get("required_commands"),
            )
        )
    return errors


def attach_goal_error_context(
    goal: dict[str, Any],
    *,
    validation_errors: list[str],
    record_validation_errors: list[str],
    release_asset_validation_errors: list[str],
    report_validation_errors: list[str],
    release_assets_dir: Path | None,
    blocking_errors: list[str],
) -> dict[str, Any]:
    enriched = dict(goal)
    enriched["validation_errors"] = unique_messages(validation_errors)
    enriched["record_validation_errors"] = unique_messages(record_validation_errors)
    enriched["release_asset_validation_errors"] = unique_messages(release_asset_validation_errors)
    enriched["report_validation_errors"] = unique_messages(report_validation_errors)
    enriched["release_assets_dir"] = str(release_assets_dir) if release_assets_dir is not None else ""
    enriched["blocking_errors"] = unique_messages(blocking_errors)
    return enriched


def read_release_matrix() -> dict[str, Any]:
    return json.loads(RELEASE_MATRIX_PATH.read_text(encoding="utf-8"))


def unique_messages(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        unique.append(message)
    return unique


def invalid_evidence_goal_registry(registry: dict[str, Any]) -> dict[str, Any]:
    filtered = dict(registry)
    filtered["accepted_evidence"] = []
    return filtered


def strict_goal_registry(
    registry: dict[str, Any],
    release_tag: str | None,
    *,
    require_complete: bool,
) -> dict[str, Any]:
    if require_complete and release_tag is None:
        filtered = dict(registry)
        filtered["accepted_evidence"] = []
        return filtered
    return filter_registry_for_release_tag(registry, release_tag)


def filter_registry_for_release_tag(
    registry: dict[str, Any],
    release_tag: str | None,
) -> dict[str, Any]:
    if release_tag is None:
        return registry
    filtered = dict(registry)
    records = registry.get("accepted_evidence", [])
    if isinstance(records, list):
        filtered["accepted_evidence"] = [
            record
            for record in records
            if isinstance(record, dict) and record.get("release_tag") == release_tag
        ]
    return filtered


def apply_required_release_tag(goal: dict[str, Any], release_tag: str) -> None:
    goal["release_tag"] = release_tag
    if "release_import_dry_run_command" in goal:
        goal["release_import_dry_run_command"] = replace_release_tag_placeholder(
            goal["release_import_dry_run_command"],
            release_tag,
        )
    for requirement in goal.get("target_evidence_requirements", []):
        if not isinstance(requirement, dict):
            continue
        requirement["required_release_tag"] = release_tag
        accepted_record = requirement.get("accepted_evidence_record")
        if isinstance(accepted_record, dict):
            accepted_record["release_tag"] = release_tag
        for key in (
            "required_artifacts",
            "required_review_bundle_files",
            "required_commands",
            "release_asset_source_required",
            "workflow_dispatch_command",
        ):
            if key in requirement:
                requirement[key] = replace_release_tag_placeholder(requirement[key], release_tag)


def replace_release_tag_placeholder(value: Any, release_tag: str) -> Any:
    if isinstance(value, str):
        return value.replace("v<project.version>", release_tag).replace(
            "<project.version>",
            release_tag.removeprefix("v"),
        )
    if isinstance(value, list):
        return [replace_release_tag_placeholder(item, release_tag) for item in value]
    if isinstance(value, dict):
        return {
            key: replace_release_tag_placeholder(item, release_tag)
            for key, item in value.items()
        }
    return value


def format_goal_summary(goal: dict[str, Any]) -> str:
    release = f" release_tag={goal['release_tag']}" if goal.get("release_tag") else ""
    return (
        "protected platform goal parity"
        f"{release}: {goal['accepted_target_count']}/{goal['target_count']} accepted "
        f"({goal['current_percent']:.1f}%); status={goal['status']}"
    )


def format_goal_scope(goal: dict[str, Any]) -> str:
    target_count = int(goal.get("target_count", 0) or 0)
    accepted_count = int(goal.get("accepted_target_count", 0) or 0)
    aggregate_count = int(goal.get("aggregate_accepted_target_count", accepted_count) or 0)
    lines = [
        "release scope: requires one release_tag, one GitHub release repository, "
        "per-target release source workflow files, one release source head SHA "
        "and per-record release source run attempts"
    ]
    if aggregate_count != accepted_count:
        lines.append(
            f"accepted in selected release scope: {accepted_count}/{target_count}; "
            f"aggregate accepted records: {aggregate_count}/{target_count}"
        )
    repositories = list_values(goal.get("release_repositories"))
    source_heads = list_values(goal.get("release_source_heads"))
    release_tags = list_values(goal.get("release_tags"))
    if release_tags:
        lines.append(f"accepted release tags: {', '.join(release_tags)}")
    if repositories:
        lines.append(f"accepted release repositories: {', '.join(repositories)}")
    if source_heads:
        lines.append(f"accepted release source heads: {', '.join(source_heads)}")
    selected_workflows = dict_values(goal.get("selected_release_source_workflows"))
    workflows = selected_workflows or dict_values(goal.get("release_source_workflows"))
    if workflows:
        workflow_summary = ", ".join(
            f"{target}={workflow}" for target, workflow in sorted(workflows.items())
        )
        label = (
            "selected release source workflows"
            if aggregate_count != accepted_count
            else "accepted release source workflows"
        )
        lines.append(f"{label}: {workflow_summary}")
    selected_run_attempts = dict_values(goal.get("selected_release_source_run_attempts"))
    run_attempts = selected_run_attempts or dict_values(goal.get("release_source_run_attempts"))
    if run_attempts:
        attempts = ", ".join(f"{target}={attempt}" for target, attempt in sorted(run_attempts.items()))
        label = (
            "selected release source run attempts"
            if aggregate_count != accepted_count
            else "accepted release source run attempts"
        )
        lines.append(f"{label}: {attempts}")
    aggregate_workflows = dict_values(goal.get("release_source_workflows"))
    if aggregate_count != accepted_count and aggregate_workflows and aggregate_workflows != selected_workflows:
        workflow_summary = ", ".join(
            f"{target}={workflow}" for target, workflow in sorted(aggregate_workflows.items())
        )
        lines.append(f"aggregate accepted release source workflows: {workflow_summary}")
    aggregate_run_attempts = dict_values(goal.get("release_source_run_attempts"))
    if aggregate_count != accepted_count and aggregate_run_attempts and aggregate_run_attempts != selected_run_attempts:
        attempts = ", ".join(
            f"{target}={attempt}" for target, attempt in sorted(aggregate_run_attempts.items())
        )
        lines.append(f"aggregate accepted release source run attempts: {attempts}")
    import_command = str(goal.get("release_import_dry_run_command", "")).strip()
    if import_command:
        lines.append(f"pre-release import dry-run: {import_command}")
    if not any((release_tags, repositories, source_heads, workflows, run_attempts)):
        lines.append("accepted release scope evidence: none")
    return "\n".join(lines)


def format_goal_requirements(goal: dict[str, Any]) -> str:
    requirements = goal.get("target_evidence_requirements", [])
    if not isinstance(requirements, list):
        return ""
    missing = set(str(target) for target in goal.get("missing_targets", []))
    rows = [item for item in requirements if isinstance(item, dict)]
    if missing:
        rows = [item for item in rows if str(item.get("target", "")) in missing]
    if not rows:
        return ""
    lines = ["required proof for missing targets:" if missing else "required proof for protected targets:"]
    for item in rows:
        target = str(item.get("target", ""))
        accepted = "accepted" if item.get("accepted") else "missing"
        lines.append(f"  {target}: {accepted}")
        boundary = str(item.get("support_boundary", ""))
        if boundary:
            lines.append(f"    boundary: {boundary}")
        accepted_record = item.get("accepted_evidence_record", {})
        if isinstance(accepted_record, dict):
            lines.append(
                "    accepted record: "
                f"{accepted_record.get('registry', 'configs/platform_verified_evidence.json')} "
                f"target={accepted_record.get('target', target)} "
                f"release_tag={accepted_record.get('release_tag', goal.get('release_tag', 'v<project.version>'))} "
                f"status={accepted_record.get('status', 'accepted')} "
                f"readiness={accepted_record.get('readiness_percent', 100.0)}"
            )
        artifacts = item.get("required_artifacts", [])
        review_bundles = item.get("required_review_bundle_files", [])
        if isinstance(artifacts, list) or isinstance(review_bundles, list):
            lines.append(
                "    release proof: "
                f"{len(artifacts) if isinstance(artifacts, list) else 0} artifacts, "
                f"{len(review_bundles) if isinstance(review_bundles, list) else 0} review-bundle files"
            )
        source = item.get("release_asset_source_required", {})
        if isinstance(source, dict):
            workflow = str(source.get("workflow", ""))
            artifact_name = str(source.get("artifact_name", ""))
            if workflow or artifact_name:
                lines.append(
                    "    source workflow: "
                    f"{workflow or '<missing>'}; artifact={artifact_name or '<missing>'}"
                )
        dispatch_command = str(item.get("workflow_dispatch_command", "")).strip()
        if dispatch_command:
            lines.append(f"    dispatch command: {dispatch_command}")
        commands = item.get("required_commands", {})
        if isinstance(commands, dict) and commands:
            lines.append(f"    commands: {', '.join(sorted(str(key) for key in commands))}")
            lines.append("    command templates:")
            for key in sorted(str(name) for name in commands):
                value = commands.get(key)
                if isinstance(value, str) and value.strip():
                    lines.append(f"      {key}: {value}")
        builder_or_host = str(item.get("builder_or_host_evidence", ""))
        if builder_or_host:
            lines.append(f"    builder/host: {builder_or_host}")
        smoke_evidence = item.get("smoke_evidence", [])
        if isinstance(smoke_evidence, list) and smoke_evidence:
            lines.append("    smoke evidence:")
            for value in smoke_evidence:
                lines.append(f"      - {value}")
        security = item.get("security_requirements", [])
        if isinstance(security, list) and security:
            lines.append(f"    security: {'; '.join(str(value) for value in security)}")
    return "\n".join(lines)


def list_values(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(value) for value in raw if str(value)]


def dict_values(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
