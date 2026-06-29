from __future__ import annotations

import re
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
LINUX_PROTECTED_SECURITY_REQUIREMENTS = (
    "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, "
    "isolated legacy compatibility and CVE patch review",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
)
XP_PROTECTED_SECURITY_REQUIREMENTS = (
    "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
)
LINUX_PROTECTED_SMOKE_EVIDENCE_REQUIREMENTS = (
    "capture native smoke log with target, release tag, workflow run URL, workflow run attempt, source head SHA and observed git HEAD SHA",
    "consume matching builder identity evidence during native smoke and bind host identity plus security provenance from it",
    "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp into the native smoke log",
    "prove 32-bit Linux userland and target architecture on the builder",
    "bind DEB, RPM and AppImage SHA-256 lines into the native smoke log",
    "verify DEB install, verify, upgrade and uninstall",
    "verify RPM install, verify, upgrade and uninstall",
    "verify AppImage install, verify, upgrade and uninstall",
    "prove TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy crypto and modern defaults unchanged",
)
XP_PROTECTED_SMOKE_EVIDENCE_REQUIREMENTS = (
    "launch CLI without unsupported Windows APIs",
    "open the selected GUI or legacy host UI without the current PyQt6 stack",
    "connect to loopback/local profile dry-run",
    "validate artifact manifest and SHA256SUMS on the Windows XP host before collector upload",
    "prove legacy crypto remains profile-scoped opt-in",
    "prove modern defaults remain unchanged",
)
LINUX_PROTECTED_TARGETS = {"linux-i386", "linux-armhf"}
XP_PROTECTED_TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
RELEASE_ASSET_SOURCE_REQUIREMENT_KEYS = {
    "artifact_name",
    "contains_files",
    "head_sha",
    "run_attempt",
    "type",
    "workflow",
    "workflow_run_url",
}
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = re.compile(rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+\Z")
GITHUB_ACTIONS_RUN_RE = re.compile(
    rf"https://github\.com/{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+/actions/runs/\d+\Z"
)
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+\Z")
SOURCE_HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")


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
    for row in platform_rows:
        errors.extend(check_accepted_evidence_row_bindings(row))
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
        if goal.get("target_count") != (len(required) if isinstance(required, list) else 0):
            errors.append("protected platform goal parity target_count must match required_targets")
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
        expected_gap = round(max(100.0 - expected_percent, 0.0), 1)
        if goal.get("gap_percent") != expected_gap:
            errors.append("protected platform goal parity gap_percent must match accepted target count")
        if not isinstance(goal.get("release_source_provenance_complete"), bool):
            errors.append("protected platform goal parity must expose release_source_provenance_complete")
        provenance_complete = goal.get("release_source_provenance_complete") is True
        complete = len(present) == len(required) and bool(required) and provenance_complete
        if goal.get("complete") is not complete:
            errors.append(
                "protected platform goal parity complete flag must match accepted target count "
                "and release source provenance"
            )
        expected_status = expected_protected_goal_status(
            complete=complete,
            accepted_count=len(present) if isinstance(present, list) else 0,
            target_count=len(required) if isinstance(required, list) else 0,
            release_repositories=goal.get("release_repositories"),
            release_tags=goal.get("release_tags"),
            release_source_heads=goal.get("release_source_heads"),
        )
        if goal.get("status") != expected_status:
            errors.append(
                "protected platform goal parity status must be "
                f"{expected_status}"
            )
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
                errors.extend(check_protected_requirement_boundary(target, item.get("support_boundary")))
                errors.extend(check_builder_or_host_evidence(target, item.get("builder_or_host_evidence")))
                errors.extend(check_smoke_evidence_requirements(target, item.get("smoke_evidence")))
                accepted_record = item.get("accepted_evidence_record")
                if not isinstance(accepted_record, dict):
                    errors.append(f"{target} protected platform requirement missing accepted_evidence_record")
                else:
                    errors.extend(check_required_accepted_evidence_record(target, accepted_record))
                errors.extend(check_protected_requirement_commands(target, item.get("required_commands")))
                errors.extend(
                    check_required_review_bundle_files(
                        target,
                        item.get("required_review_bundle_files"),
                        expected_requirement_release_tag(accepted_record),
                    )
                )
                errors.extend(check_release_asset_source_requirement(target, item, accepted_record))
                security = item.get("security_requirements")
                if target in LINUX_PROTECTED_TARGETS:
                    errors.extend(
                        check_security_requirement_items(
                            target,
                            security,
                            LINUX_PROTECTED_SECURITY_REQUIREMENTS,
                            "Linux protected platform requirement",
                        )
                    )
                if target in XP_PROTECTED_TARGETS:
                    errors.extend(
                        check_security_requirement_items(
                            target,
                            security,
                            XP_PROTECTED_SECURITY_REQUIREMENTS,
                            "XP protected platform requirement",
                        )
                    )
    return errors


def check_accepted_evidence_row_bindings(row: dict[str, object]) -> list[str]:
    present = row.get("accepted_evidence_present_targets")
    if not isinstance(present, list) or not present:
        return []
    target = row.get("target")
    errors: list[str] = []
    for field in (
        "accepted_evidence_release_tags",
        "accepted_evidence_release_repositories",
        "accepted_evidence_release_source_heads",
        "accepted_evidence_release_source_run_attempts",
        "accepted_evidence_release_source_run_urls",
        "accepted_evidence_release_source_workflows",
    ):
        value = row.get(field)
        if not isinstance(value, dict):
            errors.append(f"{target} accepted evidence row must expose {field}")
            continue
        if sorted(str(key) for key in value) != sorted(str(item) for item in present):
            errors.append(f"{target} accepted evidence {field} must cover present accepted targets")
            continue
        for present_target in present:
            binding = value.get(str(present_target))
            errors.extend(check_accepted_evidence_binding_value(target, str(present_target), field, binding))
    return errors


def check_accepted_evidence_binding_value(
    row_target: object,
    accepted_target: str,
    field: str,
    value: object,
) -> list[str]:
    label = f"{row_target} accepted evidence {field}[{accepted_target}]"
    if field == "accepted_evidence_release_tags":
        if not isinstance(value, str) or not RELEASE_TAG_RE.fullmatch(value):
            return [f"{label} must be a concrete vX.Y.Z release tag"]
        return []
    if field == "accepted_evidence_release_repositories":
        if not isinstance(value, list) or len(value) != 1:
            return [f"{label} must list exactly one GitHub release repository"]
        repository = str(value[0])
        if not GITHUB_REPOSITORY_RE.fullmatch(repository):
            return [f"{label} must be a GitHub owner/repository slug"]
        return []
    if field == "accepted_evidence_release_source_heads":
        if not isinstance(value, str) or not SOURCE_HEAD_RE.fullmatch(value):
            return [f"{label} must be a 40-character lowercase Git SHA"]
        return []
    if field == "accepted_evidence_release_source_run_attempts":
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return [f"{label} must be a positive integer GitHub Actions run attempt"]
        return []
    if field == "accepted_evidence_release_source_run_urls":
        if not isinstance(value, str) or not GITHUB_ACTIONS_RUN_RE.fullmatch(value):
            return [f"{label} must be a GitHub Actions run URL"]
        return []
    if field == "accepted_evidence_release_source_workflows":
        expected = expected_release_asset_source_workflow(accepted_target)
        if value != expected:
            return [f"{label} must be {expected}"]
        return []
    return []


def check_required_accepted_evidence_record(
    target: object,
    accepted_record: dict[str, object],
) -> list[str]:
    target_text = str(target)
    errors: list[str] = []
    if accepted_record.get("registry") != "configs/platform_verified_evidence.json":
        errors.append(f"{target_text} protected platform requirement must point at accepted evidence registry")
    if accepted_record.get("target") != target_text:
        errors.append(
            f"{target_text} protected platform requirement accepted_evidence_record.target must match target"
        )
    if accepted_record.get("status") != "accepted":
        errors.append(
            f"{target_text} protected platform requirement accepted_evidence_record.status must be accepted"
        )
    if accepted_record.get("readiness_percent") != 100.0:
        errors.append(
            f"{target_text} protected platform requirement accepted_evidence_record.readiness_percent must be 100.0"
        )
    release_tag = accepted_record.get("release_tag")
    if release_tag != "v<project.version>" and (
        not isinstance(release_tag, str) or not RELEASE_TAG_RE.fullmatch(release_tag)
    ):
        errors.append(
            f"{target_text} protected platform requirement accepted_evidence_record.release_tag "
            "must be v<project.version> or a concrete vX.Y.Z release tag"
        )
    if accepted_record.get("review_bundle_required") is not True:
        errors.append(
            f"{target_text} protected platform requirement accepted_evidence_record.review_bundle_required must be true"
        )
    return errors


def check_protected_requirement_boundary(target: object, raw_boundary: object) -> list[str]:
    target_text = str(target)
    if not isinstance(raw_boundary, str) or not raw_boundary.strip():
        return [f"{target_text} protected platform requirement missing support_boundary"]
    boundary = raw_boundary.strip()
    if target_text in LINUX_PROTECTED_TARGETS:
        required = (
            "remains manual-script-supported",
            "manual-script-native",
            "until accepted builder, artifact, smoke and release evidence exists",
        )
    elif target_text in XP_PROTECTED_TARGETS:
        required = (
            "Windows XP native-host remote-target-only",
            "XP remote-target coverage does not imply native-host readiness",
        )
    else:
        return [f"{target_text} protected platform requirement uses an unknown protected target"]
    missing = [snippet for snippet in required if snippet not in boundary]
    if missing:
        return [f"{target_text} protected platform requirement support_boundary missing: {missing}"]
    return []


def expected_builder_or_host_evidence(target: str) -> str:
    return {
        "linux-i386": "matching self-hosted i386/i686 Linux runner or equivalent real i386 builder",
        "linux-armhf": "matching self-hosted armv7l/armhf Linux runner or equivalent real armhf builder",
        "windows-xp-native-x86": (
            "Windows XP SP3 32-bit VM or physical host running scripts/xp_smoke_runner.cmd "
            "and artifact validation; collector: modern self-hosted xp-evidence collector "
            "with Python 3.12 and GitHub Actions support; validates staged XP host proof "
            "but does not replace XP host smoke evidence"
        ),
        "windows-xp-native-x64": (
            "Windows XP Professional x64 Edition SP2 VM or physical host running "
            "scripts/xp_smoke_runner.cmd and artifact validation; collector: modern "
            "self-hosted xp-evidence collector with Python 3.12 and GitHub Actions support; "
            "validates staged XP host proof but does not replace XP host smoke evidence"
        ),
    }.get(target, "")


def check_builder_or_host_evidence(target: object, raw_evidence: object) -> list[str]:
    target_text = str(target)
    expected = expected_builder_or_host_evidence(target_text)
    if not expected:
        return [f"{target_text} protected platform requirement uses an unknown builder/host evidence target"]
    if raw_evidence != expected:
        return [f"{target_text} protected platform requirement builder_or_host_evidence must be {expected}"]
    return []


def check_smoke_evidence_requirements(target: object, raw_smoke: object) -> list[str]:
    target_text = str(target)
    if target_text in LINUX_PROTECTED_TARGETS:
        expected_values = LINUX_PROTECTED_SMOKE_EVIDENCE_REQUIREMENTS
    elif target_text in XP_PROTECTED_TARGETS:
        expected_values = XP_PROTECTED_SMOKE_EVIDENCE_REQUIREMENTS
    else:
        return []
    if not isinstance(raw_smoke, list) or not raw_smoke:
        return [f"{target_text} protected platform requirement missing smoke_evidence"]
    values = [str(item) for item in raw_smoke]
    expected = set(expected_values)
    errors: list[str] = []
    duplicate_values = sorted({value for value in values if values.count(value) > 1})
    if duplicate_values:
        errors.append(
            f"{target_text} protected platform requirement smoke_evidence contains duplicates: {duplicate_values}"
        )
    missing = [item for item in expected_values if item not in values]
    if missing:
        errors.append(f"{target_text} protected platform requirement smoke_evidence missing: {missing}")
    unexpected = sorted(set(values) - expected)
    if unexpected:
        errors.append(f"{target_text} protected platform requirement smoke_evidence has unexpected items: {unexpected}")
    return errors


def check_protected_requirement_commands(
    target: object,
    raw_commands: object,
) -> list[str]:
    target_text = str(target)
    if not isinstance(raw_commands, dict):
        return [f"{target_text} protected platform requirement missing required_commands"]
    command_keys = {str(key) for key in raw_commands}
    expected_commands = expected_protected_requirement_commands(target_text)
    if not expected_commands:
        return [f"{target_text} protected platform requirement uses an unknown command target"]
    expected_keys = set(expected_commands)
    errors: list[str] = []
    missing = sorted(expected_keys - command_keys)
    if missing:
        errors.append(f"{target_text} protected platform requirement required_commands missing: {missing}")
    unexpected = sorted(command_keys - expected_keys)
    if unexpected:
        errors.append(
            f"{target_text} protected platform requirement required_commands has unexpected keys: "
            f"{unexpected}"
        )
    for key, expected in sorted(expected_commands.items()):
        if raw_commands.get(key) != expected:
            errors.append(
                f"{target_text} protected platform requirement {key} must be {expected!r}"
            )
    return errors


def expected_protected_requirement_commands(target: str) -> dict[str, str]:
    if target in LINUX_PROTECTED_TARGETS:
        return expected_linux_protected_requirement_commands(target)
    if target in XP_PROTECTED_TARGETS:
        return expected_xp_protected_requirement_commands(target)
    return {}


def expected_linux_protected_requirement_commands(target: str) -> dict[str, str]:
    arch = "i386" if target == "linux-i386" else "armhf"
    source_artifact = f"extended-linux-evidence-{target}-v<project.version>"
    candidate = f"platform-verified-evidence-{target}.json"
    bundle_stem = f"extended-linux-evidence-bundle-{target}-v<project.version>"
    final_record = f"platform-verified-evidence-{target}-final.json"
    return {
        "artifact_validation_command": (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target} --assets-dir <target-release-artifact-dir> "
            "--tag v<project.version> --strict"
        ),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py "
            "--root . --release-tag v<project.version> "
            f"--target {target} "
            "--assets-dir <target-release-artifact-dir> "
            "--linux-builder-evidence <builder-identity.json> "
            "--linux-smoke-evidence <native-smoke-log> "
            "--linux-workflow-run-url <github-actions-run-url> "
            "--linux-source-head-sha <github-actions-head-sha> "
            "--linux-source-run-attempt <github-actions-run-attempt>"
        ),
        "accepted_evidence_candidate_command": (
            "python scripts/make_platform_verified_evidence_record.py "
            f"--target {target} --release-tag v<project.version> "
            "--assets-dir <target-release-artifact-dir> "
            "--release-asset-base-url <github-release-download-url> "
            "--workflow-run-url <github-actions-run-url> "
            f"--release-source-artifact-name {source_artifact} "
            "--release-source-head-sha <github-actions-head-sha> "
            "--release-source-run-attempt <github-actions-run-attempt> "
            "--builder-evidence <builder-identity.json> "
            "--linux-smoke-evidence <native-smoke-log> "
            "--local-evidence-root . "
            "--staged-upload-out-dir <release-upload-staging-dir> "
            f"--runner-label self-hosted --runner-label linux --runner-label {arch} "
            f"--out <{candidate}>"
        ),
        "review_bundle_command": (
            "python scripts/make_extended_linux_evidence_bundle.py "
            f"--target {target} --release-tag v<project.version> "
            "--assets-dir <target-release-artifact-dir> "
            "--builder-evidence <builder-identity.json> "
            "--smoke-evidence <native-smoke-log> "
            f"--candidate-record <{candidate}> "
            "--out-dir <target-release-artifact-dir>"
        ),
        "finalized_evidence_record_command": (
            "python scripts/finalize_platform_verified_evidence_record.py "
            f"--candidate-record <{candidate}> "
            f"--bundle-manifest <target-release-artifact-dir>/{bundle_stem}.json "
            f"--bundle-archive <target-release-artifact-dir>/{bundle_stem}.zip "
            f"--bundle-sha256s <target-release-artifact-dir>/{bundle_stem}-SHA256SUMS.txt "
            f"--out <target-release-artifact-dir>/{final_record} --append-registry"
        ),
        "staged_upload_command": expected_staged_upload_command(target),
    }


def expected_xp_protected_requirement_commands(target: str) -> dict[str, str]:
    candidate = f"platform-verified-evidence-{target}.json"
    bundle_stem = f"xp-native-evidence-bundle-{target}-v<project.version>"
    final_record = f"platform-verified-evidence-{target}-final.json"
    source_artifact = f"xp-native-evidence-{target}-v<project.version>"
    return {
        "artifact_validation_command": (
            "python scripts/check_platform_promotion_artifacts.py "
            f"--target {target} --assets-dir <target-release-artifact-dir> "
            "--tag v<project.version> --strict"
        ),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            "--evidence <target-release-evidence.json> "
            "--assets-dir <target-release-artifact-dir> "
            "--evidence-dir <target-release-evidence-dir>"
        ),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py "
            "--root . --release-tag v<project.version> "
            f"--target {target} "
            "--assets-dir <target-release-artifact-dir> "
            "--xp-evidence <target-release-evidence.json> "
            "--xp-evidence-dir <target-release-evidence-dir> "
            "--xp-source-workflow-run-url <github-actions-run-url> "
            "--xp-source-head-sha <github-actions-head-sha> "
            "--xp-source-run-attempt <github-actions-run-attempt>"
        ),
        "accepted_evidence_candidate_command": (
            "python scripts/make_platform_verified_evidence_record.py "
            f"--target {target} --release-tag v<project.version> "
            "--assets-dir <target-release-artifact-dir> "
            "--release-asset-base-url <github-release-download-url> "
            "--release-source-workflow-run-url <github-actions-run-url> "
            f"--release-source-artifact-name {source_artifact} "
            "--release-source-head-sha <github-actions-head-sha> "
            "--release-source-run-attempt <github-actions-run-attempt> "
            "--local-evidence-root . "
            "--xp-evidence <target-release-evidence.json> "
            "--xp-evidence-dir <target-release-evidence-dir> "
            "--staged-upload-out-dir <release-upload-staging-dir> "
            "--xp-evidence-output-dir <xp-evidence-output-dir> "
            f"--out <{candidate}>"
        ),
        "review_bundle_command": (
            "python scripts/make_xp_native_evidence_bundle.py "
            f"--target {target} "
            "--evidence <target-release-evidence.json> "
            f"--candidate-record <{candidate}> "
            "--assets-dir <target-release-artifact-dir> "
            "--evidence-dir <target-release-evidence-dir> "
            "--out-dir <xp-evidence-output-dir>"
        ),
        "finalized_evidence_record_command": (
            "python scripts/finalize_platform_verified_evidence_record.py "
            f"--candidate-record <{candidate}> "
            f"--bundle-manifest <xp-evidence-output-dir>/{bundle_stem}.json "
            f"--bundle-archive <xp-evidence-output-dir>/{bundle_stem}.zip "
            f"--bundle-sha256s <xp-evidence-output-dir>/{bundle_stem}-SHA256SUMS.txt "
            f"--out <xp-evidence-output-dir>/{final_record} --append-registry"
        ),
        "staged_upload_command": expected_staged_upload_command(target),
    }


def expected_staged_upload_command(target: str) -> str:
    if target in LINUX_PROTECTED_TARGETS:
        return (
            "python scripts/stage_extended_linux_evidence_upload.py "
            f"--target {target} "
            "--release-tag v<project.version> "
            "--source-dir <target-release-artifact-dir> "
            "--out-dir <release-upload-staging-dir> "
            "--force"
        )
    if target in XP_PROTECTED_TARGETS:
        return (
            "python scripts/stage_xp_native_evidence_upload.py "
            f"--target {target} "
            "--release-tag v<project.version> "
            "--assets-dir <target-release-artifact-dir> "
            "--evidence-output-dir <xp-evidence-output-dir> "
            "--out-dir <release-upload-staging-dir> "
            "--force"
        )
    return ""


def check_release_asset_source_requirement(
    target: object,
    item: dict[str, object],
    accepted_record: object,
) -> list[str]:
    target_text = str(target)
    source = item.get("release_asset_source_required")
    if not isinstance(source, dict):
        return [f"{target_text} protected platform requirement missing release_asset_source_required"]
    errors: list[str] = []
    keys = {str(key) for key in source}
    missing_keys = sorted(RELEASE_ASSET_SOURCE_REQUIREMENT_KEYS - keys)
    if missing_keys:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required "
            f"missing keys: {missing_keys}"
        )
    if source.get("type") != "github-actions-artifact":
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.type "
            "must be github-actions-artifact"
        )
    expected_workflow = expected_release_asset_source_workflow(target_text)
    if source.get("workflow") != expected_workflow:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.workflow "
            f"must be {expected_workflow}"
        )
    release_tag = expected_requirement_release_tag(accepted_record)
    expected_artifact = expected_release_asset_source_artifact_name(target_text, release_tag)
    if source.get("artifact_name") != expected_artifact:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.artifact_name "
            f"must be {expected_artifact}"
        )
    workflow_run_url = str(source.get("workflow_run_url", ""))
    if "GitHub Actions run URL" not in workflow_run_url:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.workflow_run_url "
            "must require a GitHub Actions run URL"
        )
    if source.get("head_sha") != "40-character lowercase Git SHA matching release source":
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.head_sha "
            "must require the release source Git SHA"
        )
    if source.get("run_attempt") != "positive GitHub Actions run attempt matching release source":
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.run_attempt "
            "must require the release source run attempt"
        )
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.contains_files "
            "must be a non-empty list"
        )
        return errors
    files = [str(filename) for filename in raw_files]
    duplicate_files = sorted({filename for filename in files if files.count(filename) > 1})
    if duplicate_files:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.contains_files "
            f"contains duplicates: {duplicate_files}"
        )
    expected_files = expected_release_asset_source_files(target_text, item)
    missing_files = sorted(expected_files - set(files))
    if missing_files:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.contains_files "
            f"missing files: {missing_files}"
        )
    unexpected_files = sorted(set(files) - expected_files)
    if unexpected_files:
        errors.append(
            f"{target_text} protected platform requirement release_asset_source_required.contains_files "
            f"has unexpected files: {unexpected_files}"
        )
    return errors


def expected_requirement_release_tag(accepted_record: object) -> str:
    if isinstance(accepted_record, dict):
        release_tag = str(accepted_record.get("release_tag", ""))
        if release_tag:
            return release_tag
    return "v<project.version>"


def expected_release_asset_source_workflow(target: str) -> str:
    if target in LINUX_PROTECTED_TARGETS:
        return ".github/workflows/extended-platform-evidence.yml"
    if target in XP_PROTECTED_TARGETS:
        return ".github/workflows/xp-native-evidence.yml"
    return ""


def expected_release_asset_source_artifact_name(target: str, release_tag: str) -> str:
    if target in LINUX_PROTECTED_TARGETS:
        return f"extended-linux-evidence-{target}-{release_tag}"
    if target in XP_PROTECTED_TARGETS:
        return f"xp-native-evidence-{target}-{release_tag}"
    return ""


def expected_review_bundle_files(target: str, release_tag: str) -> set[str]:
    if target in LINUX_PROTECTED_TARGETS:
        stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
    elif target in XP_PROTECTED_TARGETS:
        stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
    else:
        return set()
    return {f"{stem}.json", f"{stem}.zip", f"{stem}-SHA256SUMS.txt"}


def expected_release_asset_source_files(target: str, item: dict[str, object]) -> set[str]:
    files = requirement_string_set(item.get("required_artifacts"))
    files.update(requirement_string_set(item.get("required_review_bundle_files")))
    files.add(f"platform-verified-evidence-{target}-final.json")
    return files


def requirement_string_set(raw_value: object) -> set[str]:
    if not isinstance(raw_value, list):
        return set()
    return {str(item) for item in raw_value if str(item)}


def check_required_review_bundle_files(
    target: object,
    raw_files: object,
    release_tag: str,
) -> list[str]:
    target_text = str(target)
    if not isinstance(raw_files, list) or not raw_files:
        return [f"{target_text} protected platform requirement missing review bundle files"]
    files = [str(filename) for filename in raw_files]
    expected = expected_review_bundle_files(target_text, release_tag)
    errors: list[str] = []
    duplicate_files = sorted({filename for filename in files if files.count(filename) > 1})
    if duplicate_files:
        errors.append(
            f"{target_text} protected platform requirement review bundle files contain duplicates: {duplicate_files}"
        )
    missing_files = sorted(expected - set(files))
    if missing_files:
        errors.append(
            f"{target_text} protected platform requirement review bundle files missing: {missing_files}"
        )
    unexpected_files = sorted(set(files) - expected)
    if unexpected_files:
        errors.append(
            f"{target_text} protected platform requirement review bundle files has unexpected files: {unexpected_files}"
        )
    return errors


def check_security_requirement_items(
    target: object,
    raw_security: object,
    required_items: tuple[str, ...],
    label: str,
) -> list[str]:
    if not isinstance(raw_security, list):
        return [f"{target} {label} missing security_requirements"]
    actual = {str(item) for item in raw_security}
    missing = [item for item in required_items if item not in actual]
    if missing:
        return [f"{target} {label} missing security proof: {missing}"]
    return []


def expected_protected_goal_status(
    *,
    complete: bool,
    accepted_count: int,
    target_count: int,
    release_repositories: object,
    release_tags: object,
    release_source_heads: object,
) -> str:
    repositories = release_repositories if isinstance(release_repositories, list) else []
    tags = release_tags if isinstance(release_tags, list) else []
    source_heads = release_source_heads if isinstance(release_source_heads, list) else []
    if complete:
        return "complete"
    if target_count and accepted_count == target_count:
        return "missing-release-source-provenance"
    if len(repositories) > 1:
        return "mixed-release-repository-evidence"
    if len(tags) > 1:
        return "mixed-release-evidence"
    if len(source_heads) > 1:
        return "mixed-release-source-evidence"
    return "missing-accepted-evidence"


def expected_release_source_run_attempt_conflicts(
    run_urls_by_target: dict[str, object],
    attempts_by_target: dict[str, object],
) -> dict[str, dict[str, int]]:
    attempts_by_url: dict[str, dict[str, int]] = {}
    for target, run_url in sorted(run_urls_by_target.items()):
        attempt = attempts_by_target.get(target)
        if not isinstance(run_url, str) or not isinstance(attempt, int) or isinstance(attempt, bool):
            continue
        if attempt <= 0:
            continue
        attempts_by_url.setdefault(run_url.rstrip("/"), {})[str(target)] = attempt
    return {
        run_url: {
            target: attempts_by_target[target]
            for target in sorted(attempts_by_target)
        }
        for run_url, attempts_by_target in sorted(attempts_by_url.items())
        if len(set(attempts_by_target.values())) > 1
    }


def check_protected_goal_release_scope(goal: dict[str, object]) -> list[str]:
    errors: list[str] = []
    required_targets = goal.get("required_targets")
    selected_targets = goal.get("accepted_targets")
    release_tags = goal.get("release_tags")
    release_repositories = goal.get("release_repositories")
    release_source_heads = goal.get("release_source_heads")
    selected_release_source_run_attempts = goal.get("selected_release_source_run_attempts")
    selected_release_source_run_urls = goal.get("selected_release_source_run_urls")
    selected_release_source_workflows = goal.get("selected_release_source_workflows")
    release_source_run_attempts = goal.get("release_source_run_attempts")
    release_source_run_urls = goal.get("release_source_run_urls")
    reported_release_source_run_attempt_conflicts = goal.get("release_source_run_attempt_conflicts")
    release_source_workflows = goal.get("release_source_workflows")
    if not isinstance(release_tags, list):
        errors.append("protected platform goal parity must expose release_tags")
        release_tags = []
    if not isinstance(release_repositories, list):
        errors.append("protected platform goal parity must expose release_repositories")
        release_repositories = []
    if not isinstance(release_source_heads, list):
        errors.append("protected platform goal parity must expose release_source_heads")
        release_source_heads = []
    if not isinstance(selected_release_source_run_attempts, dict):
        errors.append("protected platform goal parity must expose selected_release_source_run_attempts")
        selected_release_source_run_attempts = {}
    if not isinstance(selected_release_source_run_urls, dict):
        errors.append("protected platform goal parity must expose selected_release_source_run_urls")
        selected_release_source_run_urls = {}
    if not isinstance(selected_release_source_workflows, dict):
        errors.append("protected platform goal parity must expose selected_release_source_workflows")
        selected_release_source_workflows = {}
    if not isinstance(release_source_run_attempts, dict):
        errors.append("protected platform goal parity must expose release_source_run_attempts")
        release_source_run_attempts = {}
    if not isinstance(release_source_run_urls, dict):
        errors.append("protected platform goal parity must expose release_source_run_urls")
        release_source_run_urls = {}
    if not isinstance(reported_release_source_run_attempt_conflicts, dict):
        errors.append("protected platform goal parity must expose release_source_run_attempt_conflicts")
        reported_release_source_run_attempt_conflicts = {}
    if not isinstance(release_source_workflows, dict):
        errors.append("protected platform goal parity must expose release_source_workflows")
        release_source_workflows = {}
    provenance_complete = goal.get("release_source_provenance_complete")
    if not isinstance(provenance_complete, bool):
        errors.append("protected platform goal parity must expose release_source_provenance_complete")
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
    accepted_targets = goal.get("aggregate_accepted_targets", goal.get("accepted_targets", []))
    if isinstance(accepted_targets, list) and isinstance(release_source_run_attempts, dict):
        missing_attempts = sorted(
            str(target)
            for target in accepted_targets
            if str(target) not in release_source_run_attempts
        )
        if missing_attempts:
            errors.append(
                "protected platform goal parity release_source_run_attempts missing accepted targets: "
                f"{missing_attempts}"
            )
        for target, attempt in sorted(release_source_run_attempts.items()):
            if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
                errors.append(
                    "protected platform goal parity release_source_run_attempts"
                    f"[{target}] must be a positive integer"
                )
    if isinstance(accepted_targets, list) and isinstance(release_source_run_urls, dict):
        missing_run_urls = sorted(
            str(target)
            for target in accepted_targets
            if str(target) not in release_source_run_urls
        )
        if missing_run_urls:
            errors.append(
                "protected platform goal parity release_source_run_urls missing accepted targets: "
                f"{missing_run_urls}"
            )
        for target, run_url in sorted(release_source_run_urls.items()):
            if not isinstance(run_url, str) or not GITHUB_ACTIONS_RUN_RE.fullmatch(run_url):
                errors.append(
                    "protected platform goal parity release_source_run_urls"
                    f"[{target}] must be a GitHub Actions run URL"
                )
    if isinstance(accepted_targets, list) and isinstance(release_source_workflows, dict):
        missing_workflows = sorted(
            str(target)
            for target in accepted_targets
            if str(target) not in release_source_workflows
        )
        if missing_workflows:
            errors.append(
                "protected platform goal parity release_source_workflows missing accepted targets: "
                f"{missing_workflows}"
            )
        for target, workflow in sorted(release_source_workflows.items()):
            expected = expected_release_asset_source_workflow(str(target))
            if workflow != expected:
                errors.append(
                    "protected platform goal parity release_source_workflows"
                    f"[{target}] must be {expected}"
                )
    if isinstance(selected_targets, list):
        selected_target_ids = {str(target) for target in selected_targets}
        if isinstance(selected_release_source_run_attempts, dict):
            missing_selected_attempts = sorted(
                target
                for target in selected_target_ids
                if target not in selected_release_source_run_attempts
            )
            if missing_selected_attempts:
                errors.append(
                    "protected platform goal parity selected_release_source_run_attempts "
                    f"missing selected targets: {missing_selected_attempts}"
                )
            unexpected_selected_attempts = sorted(
                str(target)
                for target in selected_release_source_run_attempts
                if str(target) not in selected_target_ids
            )
            if unexpected_selected_attempts:
                errors.append(
                    "protected platform goal parity selected_release_source_run_attempts "
                    f"contains targets outside selected release scope: {unexpected_selected_attempts}"
                )
            for target, attempt in sorted(selected_release_source_run_attempts.items()):
                if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
                    errors.append(
                        "protected platform goal parity selected_release_source_run_attempts"
                        f"[{target}] must be a positive integer"
                    )
        if isinstance(selected_release_source_run_urls, dict):
            missing_selected_run_urls = sorted(
                target
                for target in selected_target_ids
                if target not in selected_release_source_run_urls
            )
            if missing_selected_run_urls:
                errors.append(
                    "protected platform goal parity selected_release_source_run_urls "
                    f"missing selected targets: {missing_selected_run_urls}"
                )
            unexpected_selected_run_urls = sorted(
                str(target)
                for target in selected_release_source_run_urls
                if str(target) not in selected_target_ids
            )
            if unexpected_selected_run_urls:
                errors.append(
                    "protected platform goal parity selected_release_source_run_urls "
                    f"contains targets outside selected release scope: {unexpected_selected_run_urls}"
                )
            for target, run_url in sorted(selected_release_source_run_urls.items()):
                if not isinstance(run_url, str) or not GITHUB_ACTIONS_RUN_RE.fullmatch(run_url):
                    errors.append(
                        "protected platform goal parity selected_release_source_run_urls"
                        f"[{target}] must be a GitHub Actions run URL"
                    )
        if isinstance(selected_release_source_workflows, dict):
            missing_selected_workflows = sorted(
                target
                for target in selected_target_ids
                if target not in selected_release_source_workflows
            )
            if missing_selected_workflows:
                errors.append(
                    "protected platform goal parity selected_release_source_workflows "
                    f"missing selected targets: {missing_selected_workflows}"
                )
            unexpected_selected_workflows = sorted(
                str(target)
                for target in selected_release_source_workflows
                if str(target) not in selected_target_ids
            )
            if unexpected_selected_workflows:
                errors.append(
                    "protected platform goal parity selected_release_source_workflows "
                    f"contains targets outside selected release scope: {unexpected_selected_workflows}"
                )
            for target, workflow in sorted(selected_release_source_workflows.items()):
                expected = expected_release_asset_source_workflow(str(target))
                if workflow != expected:
                    errors.append(
                        "protected platform goal parity selected_release_source_workflows"
                        f"[{target}] must be {expected}"
                    )
    expected_conflicts = expected_release_source_run_attempt_conflicts(
        release_source_run_urls,
        release_source_run_attempts,
    )
    if reported_release_source_run_attempt_conflicts != expected_conflicts:
        errors.append(
            "protected platform goal parity release_source_run_attempt_conflicts must match "
            "release source run URLs and attempts"
        )
    if (
        isinstance(required_targets, list)
        and isinstance(selected_targets, list)
        and isinstance(selected_release_source_run_attempts, dict)
        and isinstance(selected_release_source_run_urls, dict)
        and isinstance(selected_release_source_workflows, dict)
        and isinstance(provenance_complete, bool)
    ):
        expected_provenance_complete = (
            bool(required_targets)
            and sorted(str(target) for target in selected_targets)
            == sorted(str(target) for target in required_targets)
            and all(str(target) in selected_release_source_run_attempts for target in required_targets)
            and all(str(target) in selected_release_source_run_urls for target in required_targets)
            and all(str(target) in selected_release_source_workflows for target in required_targets)
            and not expected_conflicts
        )
        if provenance_complete is not expected_provenance_complete:
            errors.append(
                "protected platform goal parity release_source_provenance_complete must match "
                "required target run-attempt, run URL, workflow and conflict coverage"
            )
    scope = str(goal.get("scope", ""))
    for snippet in (
        "one release_tag",
        "one GitHub release repository",
        "per-target release source workflow files",
        "one release source head SHA",
        "per-record release source run attempts",
        "without conflicting attempts for one run URL",
    ):
        if snippet not in scope:
            errors.append(f"protected platform goal parity scope must mention {snippet}")
    if goal.get("complete") is True:
        for key in ("release_tag", "release_repository", "release_source_head"):
            if not str(goal.get(key, "")):
                errors.append(f"protected platform goal parity complete state must expose {key}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
