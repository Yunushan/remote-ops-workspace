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
    RESERVED_WORKSPACE_ROOTS,
    check_platform_verified_evidence,
    read_json,
)
from check_product_readiness import check_protected_requirement_commands  # noqa: E402
from check_release_publish_assets import check_release_assets  # noqa: E402

from remote_ops_workspace.features import _platform_verified_readiness  # noqa: E402

RELEASE_MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
REQUIRE_COMPLETE_RELEASE_TAG_ERROR = "--require-complete requires --release-tag vX.Y.Z"
REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR = "--require-records-complete requires --release-tag vX.Y.Z"
REQUIRE_COMPLETE_ASSETS_DIR_ERROR = (
    "--require-complete requires --assets-dir <release-assets-dir>; "
    "use --require-records-complete for records-only pre-release checks"
)
REQUIRE_COMPLETE_MODE_CONFLICT_ERROR = (
    "--require-complete and --require-records-complete are mutually exclusive"
)
REQUIRE_ASSETS_COMPLETE_ERROR = "--assets-dir requires --require-complete"
REQUIRE_ASSETS_RELEASE_TAG_ERROR = "--assets-dir requires --release-tag vX.Y.Z"
GOAL_STRING_LIST_FIELDS = {
    "missing_targets",
    "accepted_targets",
    "release_tags",
    "release_repositories",
    "release_source_heads",
}
GOAL_STRING_VALUE_MAP_FIELDS = {
    "release_source_workflows",
    "selected_release_source_workflows",
    "release_source_run_urls",
    "selected_release_source_run_urls",
}
GOAL_POSITIVE_INT_VALUE_MAP_FIELDS = {
    "release_source_run_attempts",
    "selected_release_source_run_attempts",
}
GOAL_NESTED_STRING_KEY_MAP_FIELDS = {
    "release_source_run_attempt_conflicts",
}


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
        require_records_complete=args.require_records_complete,
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
        if args.require_complete or args.require_records_complete or args.show_requirements:
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
            "Fail unless all protected goal targets have accepted evidence, "
            "source-run provenance and release assets for --release-tag; "
            "requires --release-tag and --assets-dir."
        ),
    )
    parser.add_argument(
        "--require-records-complete",
        action="store_true",
        help=(
            "Fail unless all protected goal targets have accepted records and "
            "source-run provenance for --release-tag. This is the records-only "
            "pre-release gate; it does not prove published release assets."
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
    errors.extend(check_registry_path(args.registry))
    if args.require_complete and args.require_records_complete:
        errors.append(REQUIRE_COMPLETE_MODE_CONFLICT_ERROR)
    if args.require_complete and not args.release_tag:
        errors.append(REQUIRE_COMPLETE_RELEASE_TAG_ERROR)
    if args.require_records_complete and not args.release_tag:
        errors.append(REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR)
    if args.require_complete and args.assets_dir is None:
        errors.append(REQUIRE_COMPLETE_ASSETS_DIR_ERROR)
    if args.assets_dir is not None and not args.require_complete:
        errors.append(REQUIRE_ASSETS_COMPLETE_ERROR)
    if (
        args.assets_dir is not None
        and not args.release_tag
        and REQUIRE_COMPLETE_RELEASE_TAG_ERROR not in errors
    ):
        errors.append(REQUIRE_ASSETS_RELEASE_TAG_ERROR)
    return errors


def check_registry_path(path: Path) -> list[str]:
    errors = check_path_not_reserved_workspace_root(path, "accepted evidence registry")
    if errors:
        return errors
    if path.is_symlink():
        return [f"accepted evidence registry must not be a symlink: {path}"]
    return check_path_parent_symlinks(path, "accepted evidence registry")


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink() and not is_allowed_platform_parent_symlink(parent):
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_path_not_reserved_workspace_root(path: Path, label: str) -> list[str]:
    roots: list[Path] = [Path.cwd(), ROOT]
    seen_roots: set[Path] = set()
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if root_resolved in seen_roots:
            continue
        seen_roots.add(root_resolved)
        path_resolved = (path if path.is_absolute() else root_resolved / path).resolve(strict=False)
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
                f"{reserved_root!r}: {path}"
            ]
    return []


def check_protected_platform_goal(
    *,
    registry: dict[str, Any],
    release_tag: str | None = None,
    require_complete: bool = False,
    require_records_complete: bool = False,
    assets_dir: Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    validation_errors: list[str] = []
    record_validation_errors: list[str] = []
    release_asset_validation_errors: list[str] = []
    report_validation_errors: list[str] = []
    release_tag_valid = release_tag is None or re.fullmatch(r"v\d+\.\d+\.\d+", release_tag)
    require_records_gate = require_complete or require_records_complete
    if release_tag is not None and not release_tag_valid:
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag}")
    if require_complete and require_records_complete:
        errors.append(REQUIRE_COMPLETE_MODE_CONFLICT_ERROR)
    if require_complete and release_tag is None:
        errors.append(REQUIRE_COMPLETE_RELEASE_TAG_ERROR)
    if require_records_complete and release_tag is None:
        errors.append(REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR)
    if require_complete and assets_dir is None:
        errors.append(REQUIRE_COMPLETE_ASSETS_DIR_ERROR)
    if assets_dir is not None and not require_complete:
        errors.append(REQUIRE_ASSETS_COMPLETE_ERROR)
    if assets_dir is not None and release_tag is None:
        errors.append(REQUIRE_ASSETS_RELEASE_TAG_ERROR)
    if not (require_records_gate and release_tag is None):
        record_validation_errors.extend(
            check_platform_verified_evidence(
                registry=registry,
                require_review_bundles=True,
                check_consistency=False,
            )
        )
        record_validation_errors.extend(check_duplicate_accepted_evidence_targets(registry))
        validation_errors.extend(
            check_platform_verified_evidence(
                registry=registry,
                required_targets=PROTECTED_GOAL_TARGETS if require_records_gate else None,
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
    goal_registry = strict_goal_registry(
        goal_source_registry,
        release_tag,
        require_complete=require_records_gate,
    )
    goal = _platform_verified_readiness(evidence_registry=goal_registry)["protected_goal_parity"]
    report_validation_errors.extend(check_goal_requirement_metadata(goal))
    errors.extend(report_validation_errors)
    if release_tag is not None:
        goal = dict(goal)
        apply_required_release_tag(goal, release_tag)
    elif require_records_gate:
        goal = dict(goal)
        goal["complete"] = False
        goal["status"] = "release-tag-required"
        goal["scope_error"] = (
            REQUIRE_COMPLETE_RELEASE_TAG_ERROR
            if require_complete
            else REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR
        )
    record_complete = bool(goal.get("record_complete"))
    if release_asset_validation_errors and record_complete:
        goal = mark_release_assets_invalid(goal, release_asset_validation_errors)
    elif assets_dir is not None and require_complete and release_tag is not None and record_complete:
        goal = mark_release_assets_valid(goal)
    if report_validation_errors and record_complete:
        goal = mark_requirement_metadata_invalid(goal, report_validation_errors)
    records_gate_complete = record_complete and not report_validation_errors
    if require_records_gate and not records_gate_complete:
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
        record_complete=record_complete,
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
    downgraded["release_backed_complete"] = False
    downgraded["completion_evidence"] = "release-assets-invalid"
    downgraded["release_asset_error_count"] = len(
        unique_messages(release_asset_validation_errors)
    )
    return downgraded


def mark_release_assets_valid(goal: dict[str, Any]) -> dict[str, Any]:
    proven = dict(goal)
    proven["release_asset_provenance_complete"] = True
    proven["complete"] = bool(proven.get("record_complete"))
    proven["status"] = "complete" if proven["complete"] else proven.get("status")
    proven["release_backed_complete"] = proven["complete"]
    proven["completion_evidence"] = "release-assets"
    proven["release_asset_error_count"] = 0
    return proven


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
    errors.extend(check_goal_release_scope_metadata(goal))
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


def check_goal_release_scope_metadata(goal: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in sorted(GOAL_STRING_LIST_FIELDS):
        errors.extend(check_goal_string_list_field(goal, field))
    for field in sorted(GOAL_STRING_VALUE_MAP_FIELDS):
        errors.extend(check_goal_string_value_map_field(goal, field))
    for field in sorted(GOAL_POSITIVE_INT_VALUE_MAP_FIELDS):
        errors.extend(check_goal_positive_int_value_map_field(goal, field))
    for field in sorted(GOAL_NESTED_STRING_KEY_MAP_FIELDS):
        raw = goal.get(field)
        if raw is None:
            continue
        if not isinstance(raw, dict):
            errors.append(f"protected platform goal parity {field} must be a map")
            continue
        errors.extend(check_string_key_mapping(raw, field))
        for key, value in raw.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, dict):
                errors.append(f"protected platform goal parity {field}.{key} must be a map")
                continue
            errors.extend(check_positive_int_value_mapping(value, f"{field}.{key}"))
    return errors


def check_goal_string_list_field(goal: dict[str, Any], field: str) -> list[str]:
    raw = goal.get(field)
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [f"protected platform goal parity {field} must be a list"]
    errors: list[str] = []
    values: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"protected platform goal parity {field} entries must be non-empty strings, got {value!r}"
            )
            continue
        values.append(value)
    duplicates = duplicate_names(values)
    if duplicates:
        errors.append(f"protected platform goal parity {field} contains duplicates: {duplicates}")
    case_collisions = case_insensitive_name_collisions(set(values))
    if case_collisions:
        errors.append(
            f"protected platform goal parity {field} must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return errors


def check_goal_string_value_map_field(goal: dict[str, Any], field: str) -> list[str]:
    raw = goal.get(field)
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"protected platform goal parity {field} must be a map"]
    return check_string_value_mapping(raw, field)


def check_goal_positive_int_value_map_field(goal: dict[str, Any], field: str) -> list[str]:
    raw = goal.get(field)
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"protected platform goal parity {field} must be a map"]
    return check_positive_int_value_mapping(raw, field)


def check_string_key_mapping(raw: dict[Any, Any], field: str) -> list[str]:
    errors: list[str] = []
    keys: list[str] = []
    for key in raw:
        if not isinstance(key, str) or not key.strip():
            errors.append(
                f"protected platform goal parity {field} keys must be non-empty strings, got {key!r}"
            )
            continue
        keys.append(key)
    case_collisions = case_insensitive_name_collisions(set(keys))
    if case_collisions:
        errors.append(
            f"protected platform goal parity {field} keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    return errors


def check_string_value_mapping(raw: dict[Any, Any], field: str) -> list[str]:
    errors = check_string_key_mapping(raw, field)
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"protected platform goal parity {field}.{key} "
                f"must be a non-empty string, got {value!r}"
            )
    return errors


def check_positive_int_value_mapping(raw: dict[Any, Any], field: str) -> list[str]:
    errors = check_string_key_mapping(raw, field)
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(
                f"protected platform goal parity {field}.{key} "
                f"must be a positive integer, got {value!r}"
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
    record_complete: bool,
) -> dict[str, Any]:
    enriched = dict(goal)
    enriched["record_complete"] = record_complete
    enriched["completion_requires_release_asset_provenance"] = True
    release_backed_complete = bool(enriched.get("complete")) and bool(
        enriched.get("release_asset_provenance_complete")
    )
    enriched["release_backed_complete"] = release_backed_complete
    if release_backed_complete:
        enriched["completion_evidence"] = "release-assets"
    elif record_complete and not str(enriched.get("completion_evidence", "")).strip():
        enriched["completion_evidence"] = "accepted-records-only"
    elif not record_complete and not str(enriched.get("completion_evidence", "")).strip():
        enriched["completion_evidence"] = "incomplete"
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


def check_duplicate_accepted_evidence_targets(registry: dict[str, Any]) -> list[str]:
    records = registry.get("accepted_evidence", [])
    if not isinstance(records, list):
        return []
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        target = str(record.get("target", "")).strip()
        if target:
            counts[target] = counts.get(target, 0) + 1
    return [
        f"accepted_evidence target must be unique: {target}"
        for target, count in sorted(counts.items())
        if count > 1
    ]


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
    if "release_asset_provenance_command" in goal:
        goal["release_asset_provenance_command"] = replace_release_tag_placeholder(
            goal["release_asset_provenance_command"],
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
        "and per-record release source run attempts without conflicting attempts for one run URL"
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
    selected_run_urls = dict_values(goal.get("selected_release_source_run_urls"))
    run_urls = selected_run_urls or dict_values(goal.get("release_source_run_urls"))
    if run_urls:
        run_url_summary = ", ".join(
            f"{target}={run_url}" for target, run_url in sorted(run_urls.items())
        )
        label = (
            "selected release source run URLs"
            if aggregate_count != accepted_count
            else "accepted release source run URLs"
        )
        lines.append(f"{label}: {run_url_summary}")
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
    aggregate_run_urls = dict_values(goal.get("release_source_run_urls"))
    if aggregate_count != accepted_count and aggregate_run_urls and aggregate_run_urls != selected_run_urls:
        run_url_summary = ", ".join(
            f"{target}={run_url}" for target, run_url in sorted(aggregate_run_urls.items())
        )
        lines.append(f"aggregate accepted release source run URLs: {run_url_summary}")
    aggregate_run_attempts = dict_values(goal.get("release_source_run_attempts"))
    if aggregate_count != accepted_count and aggregate_run_attempts and aggregate_run_attempts != selected_run_attempts:
        attempts = ", ".join(
            f"{target}={attempt}" for target, attempt in sorted(aggregate_run_attempts.items())
        )
        lines.append(f"aggregate accepted release source run attempts: {attempts}")
    run_attempt_conflicts = dict_values(goal.get("release_source_run_attempt_conflicts"))
    if run_attempt_conflicts:
        conflict_parts: list[str] = []
        for run_url, raw_attempts in sorted(run_attempt_conflicts.items()):
            attempts_by_target = dict_values(raw_attempts)
            attempts = ", ".join(
                f"{target}={attempt}" for target, attempt in sorted(attempts_by_target.items())
            )
            conflict_parts.append(f"{run_url}: {attempts}")
        if conflict_parts:
            lines.append(f"conflicting release source run attempts: {'; '.join(conflict_parts)}")
    import_command = str(goal.get("release_import_dry_run_command", "")).strip()
    if import_command:
        lines.append(f"pre-release import dry-run: {import_command}")
    asset_command = str(goal.get("release_asset_provenance_command", "")).strip()
    if asset_command:
        lines.append(f"release asset provenance gate: {asset_command}")
    if goal.get("release_asset_provenance_complete") is True:
        lines.append("release asset provenance: complete")
    elif goal.get("release_assets_dir"):
        lines.append("release asset provenance: incomplete")
    if goal.get("release_backed_complete") is True:
        lines.append("release-backed completion: complete")
    elif goal.get("record_complete") is True:
        lines.append(
            "release-backed completion: pending release asset validation with --assets-dir"
        )
    if not any((release_tags, repositories, source_heads, workflows, run_urls, run_attempts)):
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
    return [value for value in raw if isinstance(value, str) and value.strip()]


def dict_values(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(key, str) and key.strip()}


def duplicate_names(names: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = counts.get(name, 0) + 1
    return sorted(name for name, count in counts.items() if count > 1)


def case_insensitive_name_collisions(names: set[str]) -> list[str]:
    names_by_folded: dict[str, list[str]] = {}
    for name in names:
        names_by_folded.setdefault(name.casefold(), []).append(name)
    return sorted(
        name
        for folded_names in names_by_folded.values()
        if len(folded_names) > 1
        for name in sorted(folded_names)
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
