from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.features import coverage_report  # noqa: E402

PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
PLATFORM_TARGETS_PATH = ROOT / "configs" / "platform_targets.json"
RELEASE_MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
RELEASE_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"

EXPECTED_PROMOTION_IDS = {
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
}
LINUX_PROMOTION_IDS = {"linux-i386", "linux-armhf"}
XP_PROMOTION_IDS = {"windows-xp-native-x86", "windows-xp-native-x64"}
LINUX_RELEASE_SOURCE_ARTIFACTS = {
    "linux-i386": "extended-linux-evidence-linux-i386-v<project.version>",
    "linux-armhf": "extended-linux-evidence-linux-armhf-v<project.version>",
}
LINUX_SECURITY_REQUIREMENTS = (
    "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, "
    "isolated legacy compatibility and CVE patch review",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
)
LINUX_SMOKE_EVIDENCE_REQUIREMENTS = (
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
XP_SECURITY_REQUIREMENTS = (
    "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
)
XP_SMOKE_EVIDENCE_REQUIREMENTS = (
    "launch CLI without unsupported Windows APIs",
    "open the selected GUI or legacy host UI without the current PyQt6 stack",
    "connect to loopback/local profile dry-run",
    "validate artifact manifest and SHA256SUMS on the Windows XP host before collector upload",
    "prove legacy crypto remains profile-scoped opt-in",
    "prove modern defaults remain unchanged",
)
XP_HOST_EVIDENCE_REQUIREMENTS = {
    "windows-xp-native-x86": (
        "Windows XP SP3 32-bit VM or physical host running "
        "scripts/xp_smoke_runner.cmd and artifact validation"
    ),
    "windows-xp-native-x64": (
        "Windows XP Professional x64 Edition SP2 VM or physical host running "
        "scripts/xp_smoke_runner.cmd and artifact validation"
    ),
}
XP_EVIDENCE_COLLECTOR_REQUIREMENT = (
    "modern self-hosted xp-evidence collector with Python 3.12 and GitHub Actions support; "
    "validates staged XP host proof but does not replace XP host smoke evidence"
)

LINUX_REQUIRED_PROMOTION_KEYS = {
    "platform_targets_release_tier",
    "platform_targets_github_release_channel",
    "release_matrix_default_native_job",
    "release_matrix_platform_target_id",
    "release_matrix_arch",
    "workflow_job",
    "workflow_arch",
    "workflow_runner_evidence",
    "build_script",
    "smoke_script",
    "smoke_evidence",
    "artifact_validation_command",
    "local_evidence_preflight_command",
    "accepted_evidence_candidate_command",
    "review_bundle_command",
    "finalized_evidence_record_command",
    "review_bundle_files",
    "required_artifacts",
    "security_requirements",
}
XP_REQUIRED_PROMOTION_KEYS = {
    "separate_legacy_toolchain",
    "xp_vm_or_self_hosted_runner",
    "xp_evidence_collector_runner",
    "release_source_workflow",
    "native_artifacts",
    "artifact_validation_command",
    "native_evidence_validation_command",
    "local_evidence_preflight_command",
    "accepted_evidence_candidate_command",
    "review_bundle_command",
    "finalized_evidence_record_command",
    "review_bundle_files",
    "smoke_evidence",
    "security_requirements",
}

REQUIRED_DOC_SNIPPETS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "Linux i386/armhf and Windows XP native-host promotion to 100% is gated",
        "configs/platform_parity_promotion.json",
        "python scripts/check_platform_parity_promotion.py",
        "python scripts/check_platform_promotion_artifacts.py",
        ".github/workflows/extended-platform-evidence.yml",
        "python scripts/check_xp_native_evidence.py",
        "configs/platform_verified_evidence.json",
        "python scripts/check_platform_verified_evidence.py",
        "python scripts/make_platform_verified_evidence_record.py",
        "python scripts/finalize_platform_verified_evidence_record.py",
    ),
    "docs/PLATFORM_SUPPORT.md": (
        "## Promotion to 100% for extended targets",
        "Linux i386/armhf and Windows XP native-host promotion to 100% is gated",
        "configs/platform_parity_promotion.json",
        "python scripts/check_platform_parity_promotion.py",
        "python scripts/check_platform_promotion_artifacts.py",
        ".github/workflows/extended-platform-evidence.yml",
        "python scripts/check_xp_native_evidence.py",
        "configs/platform_verified_evidence.json",
        "python scripts/check_platform_verified_evidence.py",
        "python scripts/make_platform_verified_evidence_record.py",
        "python scripts/finalize_platform_verified_evidence_record.py",
    ),
    "docs/RELEASE_STRATEGY.md": (
        "configs/platform_parity_promotion.json",
        "python scripts/check_platform_parity_promotion.py",
        "python scripts/check_platform_promotion_artifacts.py",
        ".github/workflows/extended-platform-evidence.yml",
        "python scripts/check_xp_native_evidence.py",
        "configs/platform_verified_evidence.json",
        "python scripts/check_platform_verified_evidence.py",
        "python scripts/make_platform_verified_evidence_record.py",
        "python scripts/finalize_platform_verified_evidence_record.py",
        "Linux i386 and Linux armhf can move from script-supported to default-native",
    ),
    "docs/FULL_FEATURE_COVERAGE.md": (
        "Linux i386/armhf and Windows XP native-host promotion to 100% is gated",
        "configs/platform_parity_promotion.json",
        "python scripts/check_platform_parity_promotion.py",
        "python scripts/check_platform_promotion_artifacts.py",
        ".github/workflows/extended-platform-evidence.yml",
        "python scripts/check_xp_native_evidence.py",
        "configs/platform_verified_evidence.json",
        "python scripts/check_platform_verified_evidence.py",
        "python scripts/make_platform_verified_evidence_record.py",
        "python scripts/finalize_platform_verified_evidence_record.py",
    ),
    "docs/VERIFYING.md": (
        "python scripts/check_platform_parity_promotion.py",
        "python scripts/check_platform_promotion_artifacts.py",
        "python scripts/check_extended_platform_evidence.py",
        "python scripts/check_xp_native_evidence.py",
        "python scripts/check_platform_verified_evidence.py",
        "python scripts/make_platform_verified_evidence_record.py",
        "python scripts/finalize_platform_verified_evidence_record.py",
        "Linux i386/armhf and Windows XP native-host promotion",
    ),
}


def main() -> int:
    errors = check_platform_parity_promotion()
    if errors:
        for error in errors:
            print(f"platform parity promotion: {error}", file=sys.stderr)
        return 1
    print("platform parity promotion checks passed")
    return 0


def check_platform_parity_promotion(
    *,
    promotion: dict[str, Any] | None = None,
    platform_targets: dict[str, Any] | None = None,
    release_matrix: dict[str, Any] | None = None,
    workflow: str | None = None,
    report: dict[str, Any] | None = None,
    docs: dict[str, str] | None = None,
) -> list[str]:
    promotion_data = promotion or read_json(PROMOTION_PATH)
    platform_data = platform_targets or read_json(PLATFORM_TARGETS_PATH)
    matrix = release_matrix or read_json(RELEASE_MATRIX_PATH)
    workflow_text = workflow if workflow is not None else RELEASE_WORKFLOW_PATH.read_text(encoding="utf-8")
    coverage = report or coverage_report()
    doc_text = docs or read_docs(REQUIRED_DOC_SNIPPETS)

    errors: list[str] = []
    errors.extend(check_schema(promotion_data))
    if errors:
        return errors

    entries = rows_by_key(promotion_data.get("protected_targets", []), "id", errors)
    release_rows = rows_by_key(platform_data.get("release_architectures", []), "id", errors)
    legacy_rows = rows_by_key(platform_data.get("windows_legacy_targets", []), "version", errors)
    readiness_rows = rows_by_key(
        coverage.get("platform_verified_readiness", {}).get("targets", []),
        "target",
        errors,
    )

    for target_id in sorted(LINUX_PROMOTION_IDS):
        entry = entries.get(target_id)
        if entry is not None:
            errors.extend(
                check_linux_promotion_entry(
                    entry,
                    release_rows,
                    readiness_rows,
                    matrix,
                    workflow_text,
                )
            )
    for target_id in sorted(XP_PROMOTION_IDS):
        entry = entries.get(target_id)
        if entry is not None:
            errors.extend(check_xp_promotion_entry(entry, legacy_rows, readiness_rows))

    errors.extend(check_docs(doc_text))
    return errors


def check_schema(promotion: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if promotion.get("schema_version") != 1:
        errors.append("configs/platform_parity_promotion.json schema_version must be 1")
    if "100% real parity" not in str(promotion.get("goal", "")):
        errors.append("platform parity promotion goal must explicitly describe 100% real parity")

    raw_entries = promotion.get("protected_targets")
    if not isinstance(raw_entries, list):
        return [*errors, "platform parity promotion protected_targets must be a list"]
    entries = rows_by_key(raw_entries, "id", errors)
    actual_ids = set(entries)
    if actual_ids != EXPECTED_PROMOTION_IDS:
        errors.append(
            "platform parity promotion protected targets must exactly match "
            f"{sorted(EXPECTED_PROMOTION_IDS)}, got {sorted(actual_ids)}"
        )
    for target_id, entry in entries.items():
        if entry.get("target_readiness_percent") != 100.0:
            errors.append(f"{target_id} target_readiness_percent must be 100.0")
        blockers = entry.get("current_blockers")
        if not isinstance(blockers, list) or not blockers:
            errors.append(f"{target_id} must list current_blockers before promotion")
        requirements = entry.get("promotion_to_100_requires")
        if not isinstance(requirements, dict):
            errors.append(f"{target_id} promotion_to_100_requires must be an object")
            continue
        required_keys = LINUX_REQUIRED_PROMOTION_KEYS if target_id in LINUX_PROMOTION_IDS else XP_REQUIRED_PROMOTION_KEYS
        missing_keys = sorted(required_keys - set(requirements))
        if missing_keys:
            errors.append(f"{target_id} promotion_to_100_requires missing keys: {missing_keys}")
    return errors


def check_linux_promotion_entry(
    entry: dict[str, Any],
    release_rows: dict[str, dict[str, Any]],
    readiness_rows: dict[str, dict[str, Any]],
    matrix: dict[str, Any],
    workflow: str,
) -> list[str]:
    target_id = str(entry.get("platform_target_id", ""))
    row = release_rows.get(target_id)
    readiness = readiness_rows.get(target_id)
    label = str(entry.get("id", target_id))
    errors: list[str] = []
    if row is None:
        return [f"{label} references missing platform target {target_id}"]
    if readiness is None:
        return [f"{label} references missing platform readiness row {target_id}"]

    errors.extend(
        check_current_field(label, entry, "current_release_tier", row.get("release_tier"))
    )
    errors.extend(
        check_current_field(
            label,
            entry,
            "current_github_release_channel",
            row.get("github_release_channel"),
        )
    )
    errors.extend(
        check_current_field(
            label,
            entry,
            "current_readiness_percent",
            readiness.get("current_percent"),
        )
    )
    errors.extend(check_current_field(label, entry, "current_status", readiness.get("status")))

    default_ids = default_native_target_ids(matrix)
    script_ids = script_supported_target_ids(matrix)
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return errors

    if float(entry.get("current_readiness_percent", 0.0)) < 100.0:
        if target_id in default_ids:
            errors.append(f"{label} is below 100% but is already in default native release targets")
        if target_id not in script_ids:
            errors.append(f"{label} must remain in script_supported_native until promotion evidence exists")
    else:
        errors.extend(
            check_linux_100_evidence(
                label,
                target_id,
                row,
                matrix,
                workflow,
                requirements,
            )
        )

    errors.extend(check_script_requirement(label, requirements, "build_script"))
    errors.extend(check_script_requirement(label, requirements, "smoke_script"))
    errors.extend(check_linux_smoke_evidence_requirements(label, requirements))
    errors.extend(check_artifact_validation_command(label, requirements))
    errors.extend(check_local_evidence_preflight_command(label, requirements, kind="linux"))
    errors.extend(check_finalized_evidence_requirements(label, requirements, kind="linux"))
    artifacts = requirements.get("required_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) < 5:
        errors.append(f"{label} must list required 100% release artifacts")
    else:
        for artifact in artifacts:
            if "<project.version>" not in str(artifact):
                errors.append(f"{label} artifact must use <project.version> placeholder: {artifact}")
    errors.extend(check_security_requirements(label, requirements, LINUX_SECURITY_REQUIREMENTS))
    return errors


def check_linux_100_evidence(
    label: str,
    target_id: str,
    row: dict[str, Any],
    matrix: dict[str, Any],
    workflow: str,
    requirements: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    expected_release_tier = requirements.get("platform_targets_release_tier")
    expected_channel = requirements.get("platform_targets_github_release_channel")
    if row.get("release_tier") != expected_release_tier:
        errors.append(f"{label} 100% promotion requires release_tier={expected_release_tier}")
    if row.get("github_release_channel") != expected_channel:
        errors.append(f"{label} 100% promotion requires github_release_channel={expected_channel}")

    default_ids = default_native_target_ids(matrix)
    if target_id not in default_ids:
        errors.append(f"{label} 100% promotion requires default native release matrix membership")

    job_name = str(requirements.get("release_matrix_default_native_job", ""))
    matrix_arch = str(requirements.get("release_matrix_arch", ""))
    workflow_arch = str(requirements.get("workflow_arch", ""))
    job_arches = default_native_job_arches(matrix, job_name)
    if matrix_arch not in job_arches:
        errors.append(f"{label} 100% promotion requires {job_name} matrix arch {matrix_arch}")
    job_block = workflow_job_block(workflow, str(requirements.get("workflow_job", "")))
    if not job_block:
        errors.append(f"{label} 100% promotion requires workflow job {job_name}")
    elif not re.search(rf"(?m)^\s+- arch:\s*{re.escape(workflow_arch)}\s*$", job_block):
        errors.append(f"{label} 100% promotion requires workflow arch {workflow_arch}")
    return errors


def check_xp_promotion_entry(
    entry: dict[str, Any],
    legacy_rows: dict[str, dict[str, Any]],
    readiness_rows: dict[str, dict[str, Any]],
) -> list[str]:
    version = str(entry.get("legacy_windows_version", ""))
    row = legacy_rows.get(version)
    readiness = readiness_rows.get(version)
    label = str(entry.get("id", version))
    errors: list[str] = []
    if row is None:
        return [f"{label} references missing legacy Windows target {version}"]
    if readiness is None:
        return [f"{label} references missing platform readiness row {version}"]

    errors.extend(check_current_field(label, entry, "current_host_tier", row.get("host_tier")))
    errors.extend(
        check_current_field(
            label,
            entry,
            "remote_target_coverage_percent",
            row.get("remote_target_coverage_percent"),
        )
    )
    errors.extend(
        check_current_field(
            label,
            entry,
            "current_readiness_percent",
            readiness.get("current_percent"),
        )
    )
    errors.extend(check_current_field(label, entry, "current_status", readiness.get("status")))

    if entry.get("current_stack_supported") is not False:
        errors.append(f"{label} current_stack_supported must remain false until XP-native evidence exists")
    if entry.get("requires_separate_legacy_toolchain") is not True:
        errors.append(f"{label} must require a separate legacy toolchain for XP native host readiness")
    if float(entry.get("current_readiness_percent", 0.0)) >= 100.0:
        errors.append(f"{label} cannot claim 100% until XP VM and native artifact evidence is added")

    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return errors
    if requirements.get("separate_legacy_toolchain") is not True:
        errors.append(f"{label} promotion requires separate_legacy_toolchain=true")
    expected_xp_host = XP_HOST_EVIDENCE_REQUIREMENTS.get(label)
    if requirements.get("xp_vm_or_self_hosted_runner") != expected_xp_host:
        errors.append(f"{label} xp_vm_or_self_hosted_runner must be {expected_xp_host}")
    if requirements.get("xp_evidence_collector_runner") != XP_EVIDENCE_COLLECTOR_REQUIREMENT:
        errors.append(
            f"{label} xp_evidence_collector_runner must be {XP_EVIDENCE_COLLECTOR_REQUIREMENT}"
        )
    source_workflow = str(requirements.get("release_source_workflow", ""))
    if source_workflow != ".github/workflows/xp-native-evidence.yml":
        errors.append(f"{label} release_source_workflow must be .github/workflows/xp-native-evidence.yml")
    elif not (ROOT / source_workflow).is_file():
        errors.append(f"{label} release_source_workflow file is missing: {source_workflow}")
    expected_arch = str(entry.get("architecture", ""))
    artifacts = requirements.get("native_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) < 3:
        errors.append(f"{label} must list XP native artifact requirements")
    else:
        for artifact in artifacts:
            artifact_text = str(artifact)
            if expected_arch not in artifact_text:
                errors.append(f"{label} artifact must include architecture {expected_arch}: {artifact}")
            if "<project.version>" not in artifact_text:
                errors.append(f"{label} artifact must use <project.version> placeholder: {artifact}")
    errors.extend(check_xp_smoke_evidence_requirements(label, requirements))
    errors.extend(check_security_requirements(label, requirements, XP_SECURITY_REQUIREMENTS))
    errors.extend(check_artifact_validation_command(label, requirements))
    errors.extend(check_xp_native_evidence_validation_command(label, requirements))
    errors.extend(check_local_evidence_preflight_command(label, requirements, kind="xp"))
    errors.extend(check_finalized_evidence_requirements(label, requirements, kind="xp"))
    return errors


def check_security_requirements(
    label: str,
    requirements: dict[str, Any],
    required_items: tuple[str, ...],
) -> list[str]:
    raw_requirements = requirements.get("security_requirements")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        return [f"{label} promotion requires non-empty security_requirements"]
    actual = {str(item) for item in raw_requirements}
    missing = [item for item in required_items if item not in actual]
    if missing:
        return [f"{label} security_requirements missing: {missing}"]
    return []


def check_linux_smoke_evidence_requirements(
    label: str,
    requirements: dict[str, Any],
) -> list[str]:
    raw_requirements = requirements.get("smoke_evidence")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        return [f"{label} promotion requires non-empty smoke_evidence"]
    values = [str(item) for item in raw_requirements]
    expected = set(LINUX_SMOKE_EVIDENCE_REQUIREMENTS)
    errors: list[str] = []
    duplicate_values = sorted({value for value in values if values.count(value) > 1})
    if duplicate_values:
        errors.append(f"{label} smoke_evidence contains duplicates: {duplicate_values}")
    missing = [item for item in LINUX_SMOKE_EVIDENCE_REQUIREMENTS if item not in values]
    if missing:
        errors.append(f"{label} smoke_evidence missing: {missing}")
    unexpected = sorted(set(values) - expected)
    if unexpected:
        errors.append(f"{label} smoke_evidence has unexpected items: {unexpected}")
    return errors


def check_xp_smoke_evidence_requirements(
    label: str,
    requirements: dict[str, Any],
) -> list[str]:
    raw_requirements = requirements.get("smoke_evidence")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        return [f"{label} promotion requires non-empty smoke_evidence"]
    values = [str(item) for item in raw_requirements]
    expected = set(XP_SMOKE_EVIDENCE_REQUIREMENTS)
    errors: list[str] = []
    duplicate_values = sorted({value for value in values if values.count(value) > 1})
    if duplicate_values:
        errors.append(f"{label} smoke_evidence contains duplicates: {duplicate_values}")
    missing = [item for item in XP_SMOKE_EVIDENCE_REQUIREMENTS if item not in values]
    if missing:
        errors.append(f"{label} smoke_evidence missing: {missing}")
    unexpected = sorted(set(values) - expected)
    if unexpected:
        errors.append(f"{label} smoke_evidence has unexpected items: {unexpected}")
    return errors


def check_docs(docs: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = normalize_text(docs.get(path, ""))
        if not text:
            errors.append(f"missing platform parity promotion doc text: {path}")
            continue
        for snippet in snippets:
            if normalize_text(snippet) not in text:
                errors.append(f"{path} missing platform parity promotion snippet: {snippet}")
    return errors


def check_current_field(label: str, entry: dict[str, Any], key: str, actual: Any) -> list[str]:
    if entry.get(key) != actual:
        return [f"{label} {key} must match current evidence {actual!r}, got {entry.get(key)!r}"]
    return []


def check_script_requirement(label: str, requirements: dict[str, Any], key: str) -> list[str]:
    value = requirements.get(key)
    if not isinstance(value, str) or not value:
        return [f"{label} promotion requires {key}"]
    script_path = value.split()[0]
    if not (ROOT / script_path).is_file():
        return [f"{label} promotion {key} points to missing file: {script_path}"]
    return []


def check_artifact_validation_command(label: str, requirements: dict[str, Any]) -> list[str]:
    command = requirements.get("artifact_validation_command")
    if not isinstance(command, str) or not command:
        return [f"{label} promotion requires artifact_validation_command"]
    artifact_dir = "<target-release-artifact-dir>"
    expected = (
        "python scripts/check_platform_promotion_artifacts.py "
        f"--target {label} --assets-dir {artifact_dir} --tag v<project.version> --strict"
    )
    if command != expected:
        return [f"{label} artifact_validation_command must be {expected!r}"]
    if not (ROOT / "scripts" / "check_platform_promotion_artifacts.py").is_file():
        return [f"{label} artifact validation script is missing"]
    return []


def check_xp_native_evidence_validation_command(label: str, requirements: dict[str, Any]) -> list[str]:
    command = requirements.get("native_evidence_validation_command")
    if not isinstance(command, str) or not command:
        return [f"{label} promotion requires native_evidence_validation_command"]
    expected = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence <target-release-evidence.json> "
        "--assets-dir <target-release-artifact-dir> "
        "--evidence-dir <target-release-evidence-dir>"
    )
    if command != expected:
        return [f"{label} native_evidence_validation_command must be {expected!r}"]
    if not (ROOT / "scripts" / "check_xp_native_evidence.py").is_file():
        return [f"{label} XP native evidence validation script is missing"]
    return []


def check_local_evidence_preflight_command(
    label: str,
    requirements: dict[str, Any],
    *,
    kind: str,
) -> list[str]:
    command = requirements.get("local_evidence_preflight_command")
    if not isinstance(command, str) or not command:
        return [f"{label} promotion requires local_evidence_preflight_command"]
    if kind == "linux":
        expected = (
            "python scripts/check_platform_goal_local_evidence.py "
            "--root . "
            "--release-tag v<project.version> "
            f"--target {label} "
            "--assets-dir <target-release-artifact-dir> "
            "--linux-builder-evidence <builder-identity.json> "
            "--linux-smoke-evidence <native-smoke-log> "
            "--linux-workflow-run-url <github-actions-run-url> "
            "--linux-source-head-sha <github-actions-head-sha> "
            "--linux-source-run-attempt <github-actions-run-attempt>"
        )
    else:
        expected = (
            "python scripts/check_platform_goal_local_evidence.py "
            "--root . "
            "--release-tag v<project.version> "
            f"--target {label} "
            "--assets-dir <target-release-artifact-dir> "
            "--xp-evidence <target-release-evidence.json> "
            "--xp-evidence-dir <target-release-evidence-dir> "
            "--xp-source-workflow-run-url <github-actions-run-url> "
            "--xp-source-head-sha <github-actions-head-sha> "
            "--xp-source-run-attempt <github-actions-run-attempt>"
        )
    if command != expected:
        return [f"{label} local_evidence_preflight_command must be {expected!r}"]
    if not (ROOT / "scripts" / "check_platform_goal_local_evidence.py").is_file():
        return [f"{label} local evidence preflight script is missing"]
    return []


def check_finalized_evidence_requirements(
    label: str,
    requirements: dict[str, Any],
    *,
    kind: str,
) -> list[str]:
    errors: list[str] = []
    candidate = str(requirements.get("accepted_evidence_candidate_command", ""))
    if not candidate.startswith(f"python scripts/make_platform_verified_evidence_record.py --target {label} "):
        errors.append(f"{label} accepted_evidence_candidate_command must generate a candidate for {label}")
    if "--append-registry" in candidate:
        errors.append(f"{label} accepted_evidence_candidate_command must not append unfinalized candidates")
    if "--out " not in candidate:
        errors.append(f"{label} accepted_evidence_candidate_command must write a candidate with --out")
    if "--release-source-head-sha <github-actions-head-sha>" not in candidate:
        errors.append(f"{label} accepted_evidence_candidate_command must bind release source head SHA")
    if "--release-source-run-attempt <github-actions-run-attempt>" not in candidate:
        errors.append(f"{label} accepted_evidence_candidate_command must bind release source run attempt")
    if "--local-evidence-root ." not in candidate:
        errors.append(
            f"{label} accepted_evidence_candidate_command must bind the local evidence root"
        )
    if kind == "linux":
        if "--linux-smoke-evidence <native-smoke-log>" not in candidate:
            errors.append(f"{label} accepted_evidence_candidate_command must bind Linux smoke evidence")
        expected_source_artifact = LINUX_RELEASE_SOURCE_ARTIFACTS.get(label, "")
        expected_source_artifact_arg = f"--release-source-artifact-name {expected_source_artifact}"
        if expected_source_artifact and expected_source_artifact_arg not in candidate:
            errors.append(
                f"{label} accepted_evidence_candidate_command must bind release source artifact name "
                f"{expected_source_artifact_arg!r}"
            )
    if kind == "xp":
        if "--release-source-workflow-run-url <github-actions-run-url>" not in candidate:
            errors.append(f"{label} accepted_evidence_candidate_command must bind release source workflow run")
        expected_source_artifact_arg = (
            f"--release-source-artifact-name xp-native-evidence-{label}-v<project.version>"
        )
        if expected_source_artifact_arg not in candidate:
            errors.append(
                f"{label} accepted_evidence_candidate_command must bind release source artifact name "
                f"{expected_source_artifact_arg!r}"
            )
    if not (ROOT / "scripts" / "make_platform_verified_evidence_record.py").is_file():
        errors.append(f"{label} accepted evidence record generator is missing")

    review = str(requirements.get("review_bundle_command", ""))
    expected_review_script = (
        "make_extended_linux_evidence_bundle.py"
        if kind == "linux"
        else "make_xp_native_evidence_bundle.py"
    )
    if not review.startswith(f"python scripts/{expected_review_script} --target {label} "):
        errors.append(f"{label} review_bundle_command must package a review bundle for {label}")
    if "--candidate-record" not in review:
        errors.append(f"{label} review_bundle_command must bind the candidate record with --candidate-record")
    if kind == "linux" and "--smoke-evidence <native-smoke-log>" not in review:
        errors.append(f"{label} review_bundle_command must bind Linux smoke evidence")
    expected_out_dir = "<target-release-artifact-dir>" if kind == "linux" else "<xp-evidence-output-dir>"
    if f"--out-dir {expected_out_dir}" not in review:
        errors.append(f"{label} review_bundle_command must write to {expected_out_dir}")
    if not (ROOT / "scripts" / expected_review_script).is_file():
        errors.append(f"{label} review bundle script is missing")

    final = str(requirements.get("finalized_evidence_record_command", ""))
    if not final.startswith("python scripts/finalize_platform_verified_evidence_record.py "):
        errors.append(f"{label} finalized_evidence_record_command must use the platform evidence finalizer")
    for required_arg in (
        "--candidate-record",
        "--bundle-manifest",
        "--bundle-archive",
        "--bundle-sha256s",
        "--out",
        "--append-registry",
    ):
        if required_arg not in final:
            errors.append(f"{label} finalized_evidence_record_command must include {required_arg}")
    if not (ROOT / "scripts" / "finalize_platform_verified_evidence_record.py").is_file():
        errors.append(f"{label} platform evidence finalizer is missing")

    bundle_files = requirements.get("review_bundle_files")
    if not isinstance(bundle_files, list) or len(bundle_files) != 3:
        errors.append(f"{label} review_bundle_files must list manifest, archive and SHA-256 sidecar")
        return errors
    stem = (
        f"extended-linux-evidence-bundle-{label}-v<project.version>"
        if kind == "linux"
        else f"xp-native-evidence-bundle-{label}-v<project.version>"
    )
    expected_files = {
        f"{stem}.json",
        f"{stem}.zip",
        f"{stem}-SHA256SUMS.txt",
    }
    actual_files = {str(item) for item in bundle_files}
    if actual_files != expected_files:
        errors.append(f"{label} review_bundle_files must be {sorted(expected_files)}")
    for filename in expected_files:
        expected_path = f"{expected_out_dir}/{filename}"
        if expected_path not in final:
            errors.append(f"{label} finalized_evidence_record_command must bind review bundle file {expected_path}")
    expected_final_record = f"--out {expected_out_dir}/platform-verified-evidence-{label}-final.json"
    if expected_final_record not in final:
        errors.append(
            f"{label} finalized_evidence_record_command must write finalized record next to review bundle with "
            f"{expected_final_record}"
        )
    return errors


def default_native_target_ids(matrix: dict[str, Any]) -> set[str]:
    target_ids: set[str] = set()
    for job in matrix.get("default_github_release", {}).get("native_jobs", []):
        if isinstance(job, dict):
            target_ids.update(str(item) for item in job.get("platform_target_ids", []))
    return target_ids


def default_native_job_arches(matrix: dict[str, Any], job_name: str) -> set[str]:
    for job in matrix.get("default_github_release", {}).get("native_jobs", []):
        if isinstance(job, dict) and job.get("job") == job_name:
            return {str(arch) for arch in job.get("arches", [])}
    return set()


def script_supported_target_ids(matrix: dict[str, Any]) -> set[str]:
    return {
        str(item.get("platform_target_id"))
        for item in matrix.get("script_supported_native", [])
        if isinstance(item, dict)
    }


def rows_by_key(raw_rows: Any, key: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_rows, list):
        errors.append(f"platform parity promotion rows for {key} must be a list")
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in raw_rows:
        if not isinstance(item, dict):
            errors.append(f"platform parity promotion row for {key} must be an object")
            continue
        row_key = str(item.get(key, ""))
        if not row_key:
            errors.append(f"platform parity promotion row missing key: {key}")
            continue
        if row_key in rows:
            errors.append(f"duplicate platform parity promotion row: {row_key}")
            continue
        rows[row_key] = item
    return rows


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def read_docs(required: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path in required}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\|", "|")).strip()


if __name__ == "__main__":
    raise SystemExit(main())
