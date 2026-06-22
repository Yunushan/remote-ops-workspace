from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SRC = ROOT / "src"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import check_platform_verified_evidence as platform_evidence_checker  # noqa: E402

from remote_ops_workspace.features import coverage_report, load_feature_manifest  # noqa: E402

IMPLEMENTED_STATUSES = {
    "implemented",
    "implemented-adapter",
    "implemented-cli",
    "implemented-cli-gui",
    "implemented-gui",
    "implemented-optional",
    "implemented-shell",
}


def main() -> int:
    errors = check_product_readiness()
    if errors:
        for error in errors:
            print(f"coverage truth: {error}", file=sys.stderr)
        return 1
    print("coverage truth checks passed")
    return 0


def check_product_readiness() -> list[str]:
    errors: list[str] = []
    errors.extend(
        f"platform verified evidence registry: {error}"
        for error in platform_evidence_checker.check_platform_verified_evidence(
            require_review_bundles=True
        )
    )
    manifest = load_feature_manifest()
    report = coverage_report()
    scoring = manifest.get("coverage_scoring", {})
    adapter_weights = report["adapter_ready_status_weights"]
    parity_weights = report["production_parity_status_weights"]

    for status in IMPLEMENTED_STATUSES:
        if adapter_weights.get(status) != 1.0:
            errors.append(f"implemented status {status} must score 1.0 for adapter-ready coverage")
    for status, weight in adapter_weights.items():
        if not str(status).startswith("implemented") and float(weight) >= 1.0:
            errors.append(f"non-implemented status {status} must remain below 1.0 adapter-ready weight")
    for status in IMPLEMENTED_STATUSES:
        if parity_weights.get(status) != adapter_weights.get(status):
            errors.append(f"workflow parity status {status} must match adapter-ready weight")
    for status, weight in parity_weights.items():
        if not str(status).startswith("implemented") and float(weight) >= 1.0:
            errors.append(f"non-implemented status {status} must remain below 1.0 workflow parity weight")

    for key in (
        "adapter_ready_feature_overrides",
        "adapter_ready_target_overrides",
        "production_parity_feature_overrides",
        "production_parity_target_overrides",
        "product_ready_feature_overrides",
        "product_ready_target_overrides",
    ):
        if scoring.get(key) not in ({}, None):
            errors.append(f"{key} must not be used to force coverage percentages")

    adapter = report["adapter_ready_coverage"]
    rows = [adapter["overall"], *adapter["products"]]
    for row in rows:
        if row["current_percent"] != row["target_percent"]:
            errors.append(
                f"{row['product']} adapter-ready coverage is {row['current_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if row["gap_percent"] != 0.0:
            errors.append(f"{row['product']} adapter-ready gap must be 0.0%, got {row['gap_percent']}%")
    parity = report["production_parity_coverage"]
    parity_rows = [parity["overall"], *parity["products"]]
    workflow_evidence = {
        row["product"]: row for row in report.get("workflow_parity_evidence", [])
    }
    for row in parity_rows:
        if row["current_percent"] != row["target_percent"]:
            errors.append(
                f"{row['product']} workflow parity is {row['current_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if row["gap_percent"] != 0.0:
            errors.append(f"{row['product']} workflow parity gap must be 0.0%, got {row['gap_percent']}%")
        evidence = workflow_evidence.get(row["product"])
        if evidence is None:
            errors.append(f"{row['product']} workflow parity row must expose JSON evidence")
            continue
        if evidence.get("native_clone_claimed") is not False:
            errors.append(f"{row['product']} workflow parity must not claim proprietary native clone parity")
        if evidence.get("coverage_percent") != row["current_percent"]:
            errors.append(f"{row['product']} workflow parity evidence percentage does not match coverage row")
        if evidence.get("feature_count") != row["feature_count"]:
            errors.append(f"{row['product']} workflow parity evidence feature count does not match coverage row")
        if evidence.get("partial_feature_count") != 0:
            errors.append(f"{row['product']} workflow parity has partial feature evidence")
        if evidence.get("missing_release_evidence_count") != 0:
            errors.append(f"{row['product']} workflow parity is missing release-backed evidence")
        if evidence.get("full_parity_feature_count") != row["feature_count"]:
            errors.append(f"{row['product']} workflow parity full evidence count does not cover every feature")
        for item in evidence.get("feature_evidence", []):
            if item.get("counts_as_full_parity") and not item.get("release_backed"):
                errors.append(f"{row['product']} feature {item.get('id')} lacks release-backed parity evidence")
            if item.get("counts_as_full_parity") and not item.get("evidence_refs"):
                errors.append(f"{row['product']} feature {item.get('id')} lacks evidence refs")

    platform = report["platform_verified_readiness"]
    platform_rows = platform.get("targets", [])
    if not platform_rows:
        errors.append("platform verified readiness must include release and legacy targets")
    partial_rows = [row for row in platform_rows if row["current_percent"] < 100.0]
    if not partial_rows:
        errors.append("platform verified readiness must expose partial non-default targets")
    for row in partial_rows:
        if row.get("verified_readiness_scope") is not False:
            errors.append(f"{row['target']} partial compatibility row must stay outside verified readiness scope")
    if platform.get("overall", {}).get("current_percent") != 100.0:
        errors.append("platform verified readiness overall must be 100 for verified-scope targets")
    goal = platform.get("protected_goal_parity", {})
    if not isinstance(goal, dict):
        errors.append("platform verified readiness must expose protected_goal_parity")
    else:
        required = goal.get("required_targets", [])
        present = goal.get("accepted_targets", [])
        missing = goal.get("missing_targets", [])
        accepted_count = goal.get("accepted_target_count")
        aggregate_present = goal.get("aggregate_accepted_targets", [])
        aggregate_missing = goal.get("aggregate_missing_targets", [])
        aggregate_count = goal.get("aggregate_accepted_target_count")
        if required != [
            "linux-i386",
            "linux-armhf",
            "windows-xp-native-x86",
            "windows-xp-native-x64",
        ]:
            errors.append("protected platform goal parity must list the four protected targets")
        if not isinstance(present, list) or not isinstance(missing, list):
            errors.append("protected platform goal parity must expose accepted and missing target lists")
        elif sorted(present + missing) != sorted(required):
            errors.append("protected platform goal parity accepted/missing targets must partition required targets")
        if accepted_count != len(present):
            errors.append("protected platform goal parity accepted_target_count must match accepted_targets")
        if not isinstance(aggregate_present, list) or not isinstance(aggregate_missing, list):
            errors.append("protected platform goal parity must expose aggregate accepted and missing target lists")
        elif sorted(aggregate_present + aggregate_missing) != sorted(required):
            errors.append("protected platform goal parity aggregate accepted/missing targets must partition required targets")
        if aggregate_count != len(aggregate_present):
            errors.append("protected platform goal parity aggregate_accepted_target_count must match aggregate_accepted_targets")
        expected_percent = round((len(present) / len(required) * 100.0), 1) if required else 0.0
        if goal.get("current_percent") != expected_percent:
            errors.append("protected platform goal parity current_percent must match accepted target count")
        complete = len(present) == len(required) and bool(required)
        if goal.get("complete") is not complete:
            errors.append("protected platform goal parity complete flag must match accepted target count")
        errors.extend(check_protected_goal_release_scope(goal))
        requirements = goal.get("target_evidence_requirements")
        if not isinstance(requirements, list):
            errors.append("protected platform goal parity must expose target_evidence_requirements")
        else:
            requirement_targets = [
                item.get("target") for item in requirements if isinstance(item, dict)
            ]
            if sorted(requirement_targets) != sorted(required):
                errors.append("protected platform goal parity requirements must cover every protected target")
            for item in requirements:
                if not isinstance(item, dict):
                    errors.append("protected platform goal parity requirement entries must be objects")
                    continue
                target = item.get("target")
                accepted_record = item.get("accepted_evidence_record")
                if not isinstance(accepted_record, dict):
                    errors.append(f"{target} protected platform requirement missing accepted_evidence_record")
                elif accepted_record.get("registry") != "configs/platform_verified_evidence.json":
                    errors.append(f"{target} protected platform requirement must point at accepted evidence registry")
                commands = item.get("required_commands")
                if not isinstance(commands, dict) or "artifact_validation_command" not in commands:
                    errors.append(f"{target} protected platform requirement missing artifact validation command")
                if not isinstance(commands, dict) or "local_evidence_preflight_command" not in commands:
                    errors.append(f"{target} protected platform requirement missing local evidence preflight command")
                if not item.get("required_review_bundle_files"):
                    errors.append(f"{target} protected platform requirement missing review bundle files")
                if target in {"windows-xp-native-x86", "windows-xp-native-x64"}:
                    security = item.get("security_requirements")
                    if not isinstance(security, list) or "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto" not in security:
                        errors.append(f"{target} protected platform requirement missing modern-default security proof")
    return errors


def check_protected_goal_release_scope(goal: dict[str, object]) -> list[str]:
    errors: list[str] = []
    release_tags = goal.get("release_tags")
    release_repositories = goal.get("release_repositories")
    release_source_heads = goal.get("release_source_heads")
    if not isinstance(release_tags, list):
        errors.append("protected platform goal parity must expose release_tags")
        release_tags = []
    if not isinstance(release_repositories, list):
        errors.append("protected platform goal parity must expose release_repositories")
        release_repositories = []
    if not isinstance(release_source_heads, list):
        errors.append("protected platform goal parity must expose release_source_heads")
        release_source_heads = []
    if not isinstance(goal.get("release_tag"), str):
        errors.append("protected platform goal parity must expose release_tag")
    if not isinstance(goal.get("release_repository"), str):
        errors.append("protected platform goal parity must expose release_repository")
    if not isinstance(goal.get("release_source_head"), str):
        errors.append("protected platform goal parity must expose release_source_head")
    if goal.get("release_consistent") is not (len(release_tags) <= 1):
        errors.append("protected platform goal parity release_consistent must match release_tags")
    if goal.get("release_repository_consistent") is not (len(release_repositories) <= 1):
        errors.append(
            "protected platform goal parity release_repository_consistent must match release_repositories"
        )
    if goal.get("release_source_head_consistent") is not (len(release_source_heads) <= 1):
        errors.append(
            "protected platform goal parity release_source_head_consistent must match release_source_heads"
        )
    scope = str(goal.get("scope", ""))
    for snippet in ("one release_tag", "one GitHub release repository", "one release source head SHA"):
        if snippet not in scope:
            errors.append(f"protected platform goal parity scope must mention {snippet}")
    if goal.get("complete") is True:
        for key in ("release_tag", "release_repository", "release_source_head"):
            if not str(goal.get(key, "")):
                errors.append(f"protected platform goal parity complete state must expose {key}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
