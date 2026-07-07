from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from check_platform_promotion_artifacts import (  # noqa: E402
    check_platform_promotion_artifacts,
    expand_version,
    promotion_entries,
    required_artifacts,
    version_from_tag,
)
from check_platform_promotion_artifacts import (  # noqa: E402
    read_json as read_promotion_json,
)

CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
PROMOTION_TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
RESERVED_WORKSPACE_ROOTS = {".agents", ".codex", ".git", ".github"}
FILE_LIKE_DIRECTORY_SUFFIXES = (
    ".appimage",
    ".deb",
    ".exe",
    ".gz",
    ".json",
    ".log",
    ".msi",
    ".rpm",
    ".sha256",
    ".tar",
    ".tgz",
    ".txt",
    ".xz",
    ".zip",
)
REQUIRED_FORBIDDEN_EVIDENCE_PATTERNS = {
    "TODO",
    "placeholder",
    "replace with real",
    "template evidence",
    "<artifact-dir>",
    "<evidence-dir>",
    "<evidence.json>",
    "<replace-with-real-sha256>",
    "BEGIN PRIVATE KEY",
    "BEGIN OPENSSH PRIVATE KEY",
    "password=",
    "passwd=",
    "secret=",
    "token=",
}
REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS = {"security_update_channel", "cve_review_reference"}
FORBIDDEN_SECURITY_PROVENANCE_MARKERS = (
    "<",
    ">",
    "dummy",
    "placeholder",
    "replace",
    "test-",
    "todo",
)
SECURITY_PROVENANCE_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
RESERVED_SECURITY_PROVENANCE_URL_HOSTS = {"example.com", "example.org", "example.net"}
RESERVED_SECURITY_PROVENANCE_URL_SUFFIXES = (".example", ".invalid", ".test")
SECURITY_UPDATE_PROVENANCE_MARKERS = (
    "security-update",
    "security-updates",
    "windows-update",
    "microsoft-update",
    "update-catalog",
    "apt",
    "dnf",
    "yum",
    "apk",
    "patch",
    "hotfix",
    "kb",
    "usn-",
    "dsa-",
    "rhsa-",
    "alsa-",
    "errata",
)
CVE_REVIEW_PROVENANCE_MARKERS = (
    "cve-",
    "ghsa-",
    "advisory",
    "vulnerability",
    "security-advisory",
    "security-tracker",
    "release-notes",
    "security-review",
    "kb",
    "usn-",
    "dsa-",
    "rhsa-",
    "alsa-",
)
REQUIRED_SECURITY_PROVENANCE_NAMESPACES = {
    "security_update_channel": set(SECURITY_UPDATE_PROVENANCE_MARKERS),
    "cve_review_reference": set(CVE_REVIEW_PROVENANCE_MARKERS),
}
FORBIDDEN_HOST_IDENTITY_FIELDS = {
    "computer_name",
    "computername",
    "domain",
    "fqdn",
    "host_name",
    "hostname",
    "login",
    "runner_name",
    "user",
    "username",
}
HOST_IDENTITY_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
HOST_IDENTITY_RUN_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,127}$")
OBSERVED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
GITHUB_ACTIONS_RUN_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/actions/runs/\d+$")
RELEASE_SOURCE_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
XP_RELEASE_SOURCE_WORKFLOW = ".github/workflows/xp-native-evidence.yml"
REQUIRED_RELEASE_SOURCE_FIELDS = {"workflow", "workflow_run_url", "head_sha", "run_attempt"}
XP_VER_VERSION_MARKERS = {
    "windows-xp-native-x86": "5.1.",
    "windows-xp-native-x64": "5.2.",
}
XP_PROCESSOR_ARCHITECTURE_VALUES = {
    "windows-xp-native-x86": {"x86"},
    "windows-xp-native-x64": {"amd64"},
}
REQUIRED_HOST_IDENTITY_FIELDS = {
    "schema_version",
    "target",
    "release_tag",
    "host_label",
    "evidence_run_id",
    "observed_at_utc",
    "operator_private_data_redacted",
    "os",
    "toolchain",
}
XP_EVIDENCE_FIELDS = {
    "schema_version",
    "target",
    "release_tag",
    "release_source",
    "os",
    "toolchain",
    "host_identity",
    "artifact_validation",
    "artifacts",
    "smoke_results",
    "security",
}
XP_BASE_OS_FIELDS = {"name", "architecture", "service_pack"}
XP_TOOLCHAIN_FIELDS = {"separate_legacy_toolchain", "current_python_pyqt6_stack", "description"}
XP_SECURITY_FIELDS = {
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "weak_crypto_global_default",
    "patch_evidence",
}
XP_SECURITY_PATCH_FIELDS = {
    "tls_minimum_modern_profiles",
    "tls_preferred_modern_profiles",
    "legacy_compatibility_profile",
    "cve_patch_reviewed",
    "security_update_channel",
    "cve_review_reference",
}
XP_ARTIFACT_VALIDATION_FIELDS = {"passed", "command"}
XP_SMOKE_RESULT_FIELDS = {"id", "passed", "command", "evidence_file", "evidence_sha256"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    contract = read_json(CONTRACT_PATH)
    if args.contract or args.evidence is None:
        errors = check_contract(contract)
    else:
        errors = check_xp_native_evidence(
            args.evidence,
            assets_dir=args.assets_dir,
            evidence_dir=args.evidence_dir,
            contract=contract,
        )
    if errors:
        for error in errors:
            print(f"XP native evidence: {error}", file=sys.stderr)
        return 1
    print("XP native evidence checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate imported Windows XP native evidence.")
    parser.add_argument("--contract", action="store_true", help="validate the XP evidence contract")
    parser.add_argument("--evidence", type=Path, help="XP native evidence JSON file")
    parser.add_argument("--assets-dir", type=Path, help="optional directory containing XP native artifacts")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="optional directory containing smoke evidence files referenced by the XP evidence JSON",
    )
    return parser.parse_args(argv)


def check_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema_version") != 1 or isinstance(contract.get("schema_version"), bool):
        errors.append("configs/xp_native_evidence_contract.json schema_version must be 1")
    targets = contract.get("targets")
    if not isinstance(targets, dict):
        return [*errors, "XP native evidence contract targets must be an object"]
    if set(targets) != PROMOTION_TARGETS:
        errors.append(
            "XP native evidence contract targets must exactly match "
            f"{sorted(PROMOTION_TARGETS)}, got {sorted(targets)}"
        )
    else:
        x86 = targets.get("windows-xp-native-x86", {})
        x64 = targets.get("windows-xp-native-x64", {})
        if not isinstance(x86, dict) or x86.get("minimum_service_pack") != "SP3":
            errors.append("XP x86 native evidence contract must require Windows XP SP3")
        if not isinstance(x64, dict) or x64.get("minimum_service_pack") != "SP2":
            errors.append("XP x64 native evidence contract must require Windows XP Professional x64 SP2")
        if not isinstance(x64, dict) or x64.get("required_edition") != "Professional x64 Edition":
            errors.append("XP x64 native evidence contract must require Professional x64 Edition")
    smoke_ids = contract.get("required_smoke_ids")
    if (
        not isinstance(smoke_ids, list)
        or len(smoke_ids) < 6
        or any(not isinstance(item, str) or not item for item in smoke_ids)
    ):
        errors.append("XP native evidence contract must list string required_smoke_ids")
    if contract.get("evidence_plain_file_required") is not True:
        errors.append("XP native evidence contract must require a plain non-symlink evidence JSON file")
    if contract.get("evidence_directory_plain_path_required") is not True:
        errors.append("XP native evidence contract must require a plain non-symlink evidence directory")
    if contract.get("required_smoke_evidence_file") is not True:
        errors.append("XP native evidence contract must require smoke evidence files")
    if contract.get("smoke_evidence_plain_file_required") is not True:
        errors.append("XP native evidence contract must require plain non-symlink smoke evidence files")
    smoke_fields = contract.get("required_smoke_result_fields")
    required_smoke_fields = {"id", "passed", "command", "evidence_file", "evidence_sha256"}
    if (
        not isinstance(smoke_fields, list)
        or any(not isinstance(item, str) for item in smoke_fields)
        or not required_smoke_fields.issubset(set(smoke_fields))
    ):
        errors.append(
            "XP native evidence contract must require smoke result id, passed, command, "
            "evidence_file, and evidence_sha256 fields"
        )
    release_source_fields = contract.get("required_release_source_fields")
    if (
        not isinstance(release_source_fields, list)
        or any(not isinstance(item, str) for item in release_source_fields)
        or not REQUIRED_RELEASE_SOURCE_FIELDS.issubset(set(release_source_fields))
    ):
        errors.append("XP native evidence contract must require release_source workflow, URL, head SHA and run attempt")
    command_bindings = contract.get("required_smoke_command_bindings")
    required_command_bindings = {
        "scripts/xp_smoke_runner.cmd",
        "--target <target>",
        "--release-tag <release_tag>",
        "--smoke-id <smoke_id>",
        "--evidence-file <evidence_file>",
        "--proof-file xp-smoke-proof/<smoke_id>.txt",
        "--host-label <host_label>",
        "--evidence-run-id <evidence_run_id>",
        "--observed-at-utc <observed_at_utc>",
        "--source-workflow-run-url <github-actions-run-url>",
        "--source-head-sha <github-actions-head-sha>",
        "--source-run-attempt <github-actions-run-attempt>",
        "--security-update-channel <security_update_channel>",
        "--cve-review-reference <cve_review_reference>",
    }
    if not isinstance(command_bindings, list) or not required_command_bindings.issubset(
        {str(item) for item in command_bindings}
    ):
        errors.append(
            "XP native evidence contract must require tracked runner, target, release-tag, "
            "smoke-id, evidence-file, and proof-file bindings"
        )
    command_prefix = str(contract.get("required_smoke_command_prefix", ""))
    if command_prefix != "scripts/xp_smoke_runner.cmd":
        errors.append("XP native evidence contract must require scripts/xp_smoke_runner.cmd")
    else:
        runner_path = ROOT / command_prefix
        if not runner_path.is_file():
            errors.append("XP native smoke runner script is missing: scripts/xp_smoke_runner.cmd")
        else:
            try:
                runner_text = runner_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append("XP native smoke runner script must be UTF-8 text")
            else:
                for snippet in (
                    "--target",
                    "--release-tag",
                    "--smoke-id",
                    "--evidence-file",
                    "--proof-file",
                    "--host-label",
                    "--host-label must use target-scoped prefix",
                    "--evidence-run-id",
                    "--evidence-run-id must use target-scoped prefix",
                    "--observed-at-utc",
                    "--observed-at-utc must use YYYY-MM-DDTHH:MM:SSZ",
                    "--source-workflow-run-url",
                    "--source-head-sha",
                    "--source-head-sha must be a lowercase 40-character Git commit SHA",
                    "--source-run-attempt",
                    "--source-run-attempt must be a positive integer",
                    "--source-workflow-run-url must be a GitHub Actions run URL",
                    "REQUESTED_SOURCE_RUN_ID",
                    "--source-workflow-run-url must end with a numeric GitHub Actions run id",
                    "REQUESTED_SOURCE_REPOSITORY",
                    "GITHUB_SHA",
                    "must match --source-head-sha",
                    "GITHUB_RUN_ATTEMPT",
                    "must match --source-run-attempt",
                    "GITHUB_RUN_ID",
                    "GITHUB_REPOSITORY",
                    "must match --source-workflow-run-url",
                    "--os-name",
                    "--os-architecture",
                    "--os-service-pack",
                    "--os-edition",
                    "--security-update-channel",
                    "--security-update-channel is required for XP security smoke evidence",
                    "--cve-review-reference",
                    "--cve-review-reference is required for XP security smoke evidence",
                    "proof file must include security update channel",
                    "proof file must include CVE review reference",
                    "ver",
                    "PROCESSOR_ARCHITECTURE",
                    "wmic os get Caption",
                ):
                    if snippet not in runner_text:
                        errors.append(f"XP native smoke runner script must handle {snippet}")
    smoke_root = str(contract.get("smoke_evidence_root", ""))
    if "evidence JSON directory" not in smoke_root:
        errors.append("XP native evidence contract must document smoke evidence file resolution")
    if contract.get("required_smoke_evidence_file_pattern") != "xp-smoke-evidence/<smoke_id>.txt":
        errors.append(
            "XP native evidence contract must require smoke evidence files under "
            "xp-smoke-evidence/<smoke_id>.txt"
        )
    if contract.get("exact_smoke_proof_line_occurrences_required") is not True:
        errors.append("XP native evidence contract must require exact single-occurrence smoke proof lines")
    if contract.get("forbidden_security_smoke_lines_case_insensitive") is not True:
        errors.append("XP native evidence contract must require case-insensitive forbidden security proof-line rejection")
    binding_lines = contract.get("required_smoke_evidence_binding_lines")
    required_binding_lines = {
        "xp smoke target: <target>",
        "xp smoke release: <release_tag>",
        "xp smoke id: <smoke_id>",
        "xp smoke os name: <os.name>",
        "xp smoke os architecture: <os.architecture>",
        "xp smoke os service pack: <os.service_pack>",
        "xp smoke os edition: <os.edition when required>",
        "xp smoke host probe command: ver",
        "xp smoke host probe output: <ver output>",
        "xp smoke processor architecture env: <PROCESSOR_ARCHITECTURE>",
        "xp smoke processor architecture w6432 env: <PROCESSOR_ARCHITEW6432 or empty>",
        "xp smoke wmic os caption: <wmic Caption>",
        "xp smoke wmic os csdversion: <wmic CSDVersion>",
        "xp smoke host label: <host_label>",
        "xp smoke evidence run id: <evidence_run_id>",
        "xp smoke observed at utc: <observed_at_utc>",
        "xp smoke source workflow run: <github-actions-run-url>",
        "xp smoke source head sha: <github-actions-head-sha>",
        "xp smoke source run attempt: <github-actions-run-attempt>",
    }
    if not isinstance(binding_lines, list) or not required_binding_lines.issubset(
        {str(item) for item in binding_lines}
    ):
        errors.append(
            "XP native evidence contract must require smoke evidence target, release-tag, smoke-id, "
            "OS identity, host probe, host-label and evidence-run-id binding lines"
        )
    artifact_manifest_lines = contract.get("required_artifact_manifest_smoke_evidence_lines")
    required_artifact_manifest_lines = {
        "xp smoke artifact file: <required native artifact>",
        "xp smoke artifact file: <required manifest>",
        "xp smoke artifact file: <required SHA256SUMS>",
        "xp smoke artifact manifest validated: true",
        "xp smoke artifact sha256s validated: true",
    }
    if not isinstance(artifact_manifest_lines, list) or not required_artifact_manifest_lines.issubset(
        {str(item) for item in artifact_manifest_lines}
    ):
        errors.append(
            "XP native evidence contract must require artifact_manifest_validation "
            "smoke proof lines for every release artifact, manifest, and SHA256SUMS sidecar"
        )
    security_lines = contract.get("required_security_smoke_evidence_lines")
    required_security_lines = {
        "legacy_crypto_profile_scoped": {
            "legacy compatibility profile: isolated-opt-in",
            "legacy crypto scope: profile-only",
            "weak crypto global default: false",
        },
        "modern_defaults_unchanged": {
            "modern TLS minimum: TLS 1.2",
            "modern TLS preferred: TLS 1.3",
            "modern defaults unchanged: true",
            "weak crypto global default: false",
        },
    }
    if not isinstance(security_lines, dict):
        errors.append("XP native evidence contract must define required_security_smoke_evidence_lines")
    else:
        for smoke_id, required_lines in sorted(required_security_lines.items()):
            actual_lines = security_lines.get(smoke_id)
            if not isinstance(actual_lines, list) or not required_lines.issubset(
                {str(item) for item in actual_lines}
            ):
                errors.append(
                    "XP native evidence contract required_security_smoke_evidence_lines "
                    f"missing {smoke_id} proof lines"
                )
    forbidden_security_lines = contract.get("forbidden_security_smoke_evidence_lines")
    required_forbidden_security_lines = {
        "legacy_crypto_profile_scoped": {
            "legacy compatibility profile: global",
            "legacy crypto scope: global",
            "legacy crypto scope: global-default",
            "weak crypto global default: true",
        },
        "modern_defaults_unchanged": {
            "modern TLS minimum: TLS 1.0",
            "modern TLS minimum: TLS 1.1",
            "modern TLS preferred: TLS 1.0",
            "modern TLS preferred: TLS 1.1",
            "modern defaults unchanged: false",
            "weak crypto global default: true",
        },
    }
    if not isinstance(forbidden_security_lines, dict):
        errors.append("XP native evidence contract must define forbidden_security_smoke_evidence_lines")
    else:
        for smoke_id, forbidden_lines in sorted(required_forbidden_security_lines.items()):
            actual_lines = forbidden_security_lines.get(smoke_id)
            if not isinstance(actual_lines, list) or not forbidden_lines.issubset(
                {str(item) for item in actual_lines}
            ):
                errors.append(
                    "XP native evidence contract forbidden_security_smoke_evidence_lines "
                    f"missing {smoke_id} contradiction lines"
                )
    host_identity_fields = contract.get("required_host_identity_fields")
    if not isinstance(host_identity_fields, list) or not REQUIRED_HOST_IDENTITY_FIELDS.issubset(
        {str(item) for item in host_identity_fields}
    ):
        errors.append("XP native evidence contract must require sanitized host identity fields")
    host_identity_policy = str(contract.get("host_identity_policy", ""))
    if "sanitized" not in host_identity_policy or "Do not record" not in host_identity_policy:
        errors.append("XP native evidence contract must document sanitized host identity policy")
    if contract.get("required_artifact_list_exact") is not True:
        errors.append("XP native evidence contract must require exact artifact lists")
    if contract.get("artifact_validation_tag_must_match_release_tag") is not True:
        errors.append("XP native evidence contract must require artifact validation tag matching")
    for key in ("required_security_flags", "required_toolchain_flags"):
        value = contract.get(key)
        if not isinstance(value, dict) or not value:
            errors.append(f"XP native evidence contract must define {key}")
    patch_evidence = contract.get("required_security_patch_evidence")
    if not isinstance(patch_evidence, dict) or not patch_evidence:
        errors.append("XP native evidence contract must define required_security_patch_evidence")
    provenance_fields = contract.get("required_security_patch_provenance_fields")
    if not isinstance(provenance_fields, list) or not REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS.issubset(
        {str(item) for item in provenance_fields}
    ):
        errors.append("XP native evidence contract must require security patch provenance fields")
    smoke_provenance_fields = contract.get("required_security_smoke_provenance_fields")
    if not isinstance(smoke_provenance_fields, list) or not REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS.issubset(
        {str(item) for item in smoke_provenance_fields}
    ):
        errors.append("XP native evidence contract must require security smoke provenance fields")
    errors.extend(check_security_provenance_namespace_contract(contract))
    forbidden_identity_fields = contract.get("forbidden_host_identity_fields")
    if not isinstance(forbidden_identity_fields, list):
        errors.append("XP native evidence contract must define forbidden_host_identity_fields")
    else:
        missing_fields = sorted(FORBIDDEN_HOST_IDENTITY_FIELDS - {str(item) for item in forbidden_identity_fields})
        if missing_fields:
            errors.append(
                "XP native evidence contract forbidden_host_identity_fields missing required entries: "
                f"{missing_fields}"
            )
    forbidden = contract.get("forbidden_evidence_patterns")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("XP native evidence contract must define forbidden_evidence_patterns")
    else:
        missing_patterns = sorted(REQUIRED_FORBIDDEN_EVIDENCE_PATTERNS - {str(item) for item in forbidden})
        if missing_patterns:
            errors.append(
                "XP native evidence contract forbidden_evidence_patterns missing required entries: "
                f"{missing_patterns}"
            )
    return errors


def check_security_provenance_namespace_contract(contract: dict[str, Any]) -> list[str]:
    namespaces = contract.get("required_security_patch_provenance_namespaces")
    if not isinstance(namespaces, dict):
        return ["XP native evidence contract must require concrete security provenance namespaces"]
    errors: list[str] = []
    for field, required_markers in sorted(REQUIRED_SECURITY_PROVENANCE_NAMESPACES.items()):
        actual_markers = namespaces.get(field)
        if not isinstance(actual_markers, list):
            errors.append(
                f"XP native evidence contract must require concrete {field} provenance namespaces"
            )
            continue
        missing = sorted(required_markers - {str(marker) for marker in actual_markers})
        if missing:
            errors.append(
                f"XP native evidence contract concrete {field} provenance namespaces missing {missing}"
            )
    return errors


def check_xp_native_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
    evidence_dir: Path | None = None,
    contract: dict[str, Any] | None = None,
) -> list[str]:
    contract_data = read_json(CONTRACT_PATH) if contract is None else contract
    errors: list[str] = []
    evidence_root_input = evidence_dir or evidence_path.parent
    errors.extend(check_path_not_reserved_workspace_root(evidence_path, "evidence file"))
    errors.extend(check_path_not_reserved_workspace_root(evidence_root_input, "evidence directory"))
    if evidence_path.is_symlink():
        errors.append(f"evidence file must not be a symlink: {evidence_path}")
    if evidence_root_input.is_symlink():
        errors.append(f"evidence directory must not be a symlink: {evidence_root_input}")
    if not errors:
        errors.extend(check_path_parent_symlinks(evidence_root_input, "evidence directory"))
    if not errors:
        errors.extend(check_evidence_file_location(evidence_path, evidence_root_input))
    if errors:
        return errors
    if not evidence_path.is_file():
        return [f"evidence file missing: {evidence_path}"]
    try:
        raw_text = evidence_path.read_text(encoding="utf-8")
        evidence = json.loads(raw_text)
    except OSError as exc:
        return [f"evidence file is not readable JSON: {evidence_path}: {exc}"]
    except UnicodeDecodeError:
        return [f"evidence file must be UTF-8 JSON: {evidence_path}"]
    except json.JSONDecodeError as exc:
        return [f"evidence file is not valid JSON: {exc}"]
    if not isinstance(evidence, dict):
        return ["evidence file must contain a JSON object"]

    errors.extend(check_forbidden_patterns(raw_text, contract_data))
    target = str(evidence.get("target", ""))
    target_contract = target_contract_for(contract_data, target, errors)
    if target_contract is None:
        return errors
    errors.extend(check_unexpected_fields(f"{target} evidence", evidence, XP_EVIDENCE_FIELDS))
    if evidence.get("schema_version") != 1 or isinstance(evidence.get("schema_version"), bool):
        errors.append("XP native evidence schema_version must be 1")
    release_tag = str(evidence.get("release_tag", ""))
    if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
        errors.append(f"XP native evidence release_tag must look like vX.Y.Z, got {release_tag!r}")

    release_source = evidence.get("release_source")
    errors.extend(check_release_source(target, release_source))
    errors.extend(check_os(target, evidence.get("os"), target_contract))
    errors.extend(check_toolchain(target, evidence.get("toolchain"), contract_data))
    errors.extend(
        check_host_identity(
            target,
            release_tag,
            evidence.get("host_identity"),
            evidence.get("os"),
            evidence.get("toolchain"),
            target_contract,
            contract_data,
        )
    )
    errors.extend(check_security(target, evidence.get("security"), contract_data))
    evidence_root = evidence_root_input.resolve()
    errors.extend(
        check_smoke_results(
            target,
            release_tag,
            evidence.get("smoke_results"),
            contract_data,
            evidence_root,
            host_identity=evidence.get("host_identity"),
            os_identity=evidence.get("os"),
            release_source=release_source,
            security=evidence.get("security"),
        )
    )
    errors.extend(check_artifact_validation_record(target, evidence.get("artifact_validation"), release_tag))
    errors.extend(check_artifact_names(target, evidence.get("artifacts"), target_contract, release_tag))
    if assets_dir is not None and release_tag:
        errors.extend(
            check_platform_promotion_artifacts(
                target=target,
                assets_dir=assets_dir,
                tag=release_tag,
                strict=True,
            )
        )
    return errors


def check_evidence_file_location(evidence_path: Path, evidence_root_input: Path) -> list[str]:
    if evidence_root_input.exists() and not evidence_root_input.is_dir():
        return [f"evidence directory must be a directory: {evidence_root_input}"]
    evidence_root = evidence_root_input.resolve(strict=False)
    evidence_resolved = evidence_path.resolve(strict=False)
    errors: list[str] = []
    try:
        evidence_resolved.relative_to(evidence_root)
    except ValueError:
        errors.append(f"evidence file must stay inside evidence directory: {evidence_path}")

    relative_path: Path | None = None
    try:
        relative_path = evidence_path.relative_to(evidence_root_input)
    except ValueError:
        try:
            relative_path = evidence_resolved.relative_to(evidence_root)
        except ValueError:
            relative_path = None
    if relative_path is not None:
        symlink = first_symlink_in_relative_path(evidence_root_input, relative_path)
        if symlink is not None:
            errors.append(
                "evidence file path must not contain symlinks: "
                f"{display_relative_path(evidence_root_input, symlink)}"
            )
    return errors


def check_release_source(target: str, raw_source: Any) -> list[str]:
    if not isinstance(raw_source, dict):
        return [f"{target} evidence release_source must be an object"]
    errors: list[str] = []
    keys = {str(key) for key in raw_source}
    missing = sorted(REQUIRED_RELEASE_SOURCE_FIELDS - keys)
    unexpected = sorted(keys - REQUIRED_RELEASE_SOURCE_FIELDS)
    if missing:
        errors.append(f"{target} evidence release_source missing required fields: {missing}")
    if unexpected:
        errors.append(f"{target} evidence release_source has unexpected fields: {unexpected}")
    workflow = raw_source.get("workflow")
    if not isinstance(workflow, str):
        errors.append(f"{target} evidence release_source.workflow must be a string")
    elif workflow.strip() != XP_RELEASE_SOURCE_WORKFLOW:
        errors.append(f"{target} evidence release_source.workflow must be {XP_RELEASE_SOURCE_WORKFLOW}")
    workflow_run_url = raw_source.get("workflow_run_url")
    if not isinstance(workflow_run_url, str):
        errors.append(f"{target} evidence release_source.workflow_run_url must be a string")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url.strip().rstrip("/")):
        errors.append(f"{target} evidence release_source.workflow_run_url must be a GitHub Actions run URL")
    head_sha = raw_source.get("head_sha")
    if not isinstance(head_sha, str):
        errors.append(f"{target} evidence release_source.head_sha must be a string")
    elif not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(head_sha.strip()):
        errors.append(f"{target} evidence release_source.head_sha must be a 40-character lowercase Git SHA")
    run_attempt = raw_source.get("run_attempt")
    if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
        errors.append(f"{target} evidence release_source.run_attempt must be a positive integer")
    return errors


def check_unexpected_fields(label: str, raw_object: dict[str, Any], allowed_fields: set[str]) -> list[str]:
    unexpected = sorted(str(key) for key in raw_object if str(key) not in allowed_fields)
    if not unexpected:
        return []
    return [f"{label} unexpected fields: {unexpected}"]


def check_os(
    target: str,
    raw_os: Any,
    target_contract: dict[str, Any],
    *,
    label: str | None = None,
) -> list[str]:
    label = label or f"{target} evidence os"
    if not isinstance(raw_os, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    allowed_fields = set(XP_BASE_OS_FIELDS)
    if target_contract.get("required_edition"):
        allowed_fields.add("edition")
    errors.extend(check_unexpected_fields(label, raw_os, allowed_fields))
    for key in ("name", "architecture"):
        expected = target_contract.get(key if key != "name" else "os_name")
        actual = raw_os.get(key)
        if not isinstance(actual, str):
            errors.append(f"{label}.{key} must be a string")
        elif actual != expected:
            errors.append(f"{label}.{key} must be {expected!r}, got {raw_os.get(key)!r}")
    expected_edition = str(target_contract.get("required_edition", ""))
    raw_edition = raw_os.get("edition")
    if expected_edition and not isinstance(raw_edition, str):
        errors.append(f"{label}.edition must be a string")
    elif expected_edition and raw_edition != expected_edition:
        errors.append(f"{label}.edition must be {expected_edition!r}, got {raw_os.get('edition')!r}")
    raw_service_pack = raw_os.get("service_pack")
    expected_service_pack = str(target_contract.get("minimum_service_pack", ""))
    if not isinstance(raw_service_pack, str):
        errors.append(f"{label}.service_pack must be a string")
    elif expected_service_pack and expected_service_pack not in raw_service_pack:
        errors.append(
            f"{label}.service_pack must include {expected_service_pack!r}, got {raw_service_pack!r}"
        )
    return errors


def check_toolchain(
    target: str,
    raw_toolchain: Any,
    contract: dict[str, Any],
    *,
    label: str | None = None,
) -> list[str]:
    label = label or f"{target} evidence toolchain"
    if not isinstance(raw_toolchain, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    errors.extend(check_unexpected_fields(label, raw_toolchain, XP_TOOLCHAIN_FIELDS))
    required_flags = contract.get("required_toolchain_flags", {})
    for key, expected in required_flags.items():
        if raw_toolchain.get(key) is not expected:
            errors.append(f"{label}.{key} must be {expected!r}")
    description = raw_toolchain.get("description")
    if not isinstance(description, str):
        errors.append(f"{label}.description must be a string")
    elif len(description.strip()) < 12:
        errors.append(f"{label}.description must describe the XP-capable toolchain")
    return errors


def check_host_identity(
    target: str,
    release_tag: str,
    raw_identity: Any,
    raw_os: Any,
    raw_toolchain: Any,
    target_contract: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} evidence host_identity must be an object"]
    errors: list[str] = []
    required_fields = {str(item) for item in contract.get("required_host_identity_fields", [])}
    missing = sorted(required_fields - set(raw_identity))
    if missing:
        errors.append(f"{target} evidence host_identity missing required fields: {missing}")
    errors.extend(check_unexpected_fields(f"{target} evidence host_identity", raw_identity, required_fields))
    forbidden_fields = sorted(
        field
        for field in raw_identity
        if str(field).lower() in forbidden_host_identity_fields(contract)
    )
    if forbidden_fields:
        errors.append(f"{target} evidence host_identity contains forbidden private fields: {forbidden_fields}")
    if raw_identity.get("schema_version") != 1 or isinstance(raw_identity.get("schema_version"), bool):
        errors.append(f"{target} evidence host_identity.schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} evidence host_identity.target must be {target}")
    if raw_identity.get("release_tag") != release_tag:
        errors.append(f"{target} evidence host_identity.release_tag must match evidence release_tag {release_tag}")

    raw_host_label = raw_identity.get("host_label")
    host_prefix = xp_host_identity_prefix(target)
    if not isinstance(raw_host_label, str):
        errors.append(f"{target} evidence host_identity.host_label must be a string")
        host_label = ""
        host_label_valid = False
    else:
        host_label = raw_host_label.strip()
        host_label_valid = bool(HOST_IDENTITY_LABEL_RE.fullmatch(host_label)) and host_label.startswith(host_prefix)
        if not host_label_valid:
            errors.append(
                f"{target} evidence host_identity.host_label must be a sanitized target-scoped lab label, "
                f"got {host_label!r}"
            )
    raw_evidence_run_id = raw_identity.get("evidence_run_id")
    if not isinstance(raw_evidence_run_id, str):
        errors.append(f"{target} evidence host_identity.evidence_run_id must be a string")
        evidence_run_id = ""
        evidence_run_id_valid = False
    else:
        evidence_run_id = raw_evidence_run_id.strip()
        evidence_run_id_valid = bool(HOST_IDENTITY_RUN_RE.fullmatch(evidence_run_id)) and evidence_run_id.startswith(host_prefix)
        if not evidence_run_id_valid:
            errors.append(
                f"{target} evidence host_identity.evidence_run_id must be a sanitized target-scoped run id, "
                f"got {evidence_run_id!r}"
            )
    raw_observed_at = raw_identity.get("observed_at_utc")
    if not isinstance(raw_observed_at, str):
        errors.append(f"{target} evidence host_identity.observed_at_utc must be a string")
        observed_at = ""
        observed_at_valid = False
    else:
        observed_at = raw_observed_at.strip()
        observed_at_valid = bool(OBSERVED_AT_UTC_RE.fullmatch(observed_at))
        if not observed_at_valid:
            errors.append(
                f"{target} evidence host_identity.observed_at_utc must be UTC ISO-8601 seconds ending in Z, "
                f"got {observed_at!r}"
            )
    if observed_at_valid and evidence_run_id_valid:
        expected_run_marker = xp_host_identity_run_marker(release_tag, observed_at)
        if expected_run_marker not in evidence_run_id:
            errors.append(
                f"{target} evidence host_identity.evidence_run_id must include release/observed-at marker "
                f"{expected_run_marker!r}, got {evidence_run_id!r}"
            )
    if raw_identity.get("operator_private_data_redacted") is not True:
        errors.append(f"{target} evidence host_identity.operator_private_data_redacted must be true")

    expected_os = normalized_host_os(raw_os)
    identity_os = raw_identity.get("os")
    if not isinstance(identity_os, dict):
        errors.append(f"{target} evidence host_identity.os must be an object")
    else:
        errors.extend(
            check_os(
                target,
                identity_os,
                target_contract,
                label=f"{target} evidence host_identity.os",
            )
        )
        if identity_os != expected_os:
            errors.append(f"{target} evidence host_identity.os must match evidence os")

    expected_toolchain = normalized_host_toolchain(raw_toolchain)
    identity_toolchain = raw_identity.get("toolchain")
    if not isinstance(identity_toolchain, dict):
        errors.append(f"{target} evidence host_identity.toolchain must be an object")
    else:
        errors.extend(
            check_toolchain(
                target,
                identity_toolchain,
                contract,
                label=f"{target} evidence host_identity.toolchain",
            )
        )
        if identity_toolchain != expected_toolchain:
            errors.append(f"{target} evidence host_identity.toolchain must match evidence toolchain identity")
    return errors


def forbidden_host_identity_fields(contract: dict[str, Any]) -> set[str]:
    raw_fields = contract.get("forbidden_host_identity_fields")
    if isinstance(raw_fields, list):
        return {str(item).lower() for item in raw_fields}
    return FORBIDDEN_HOST_IDENTITY_FIELDS


def xp_host_identity_prefix(target: str) -> str:
    if target.endswith("x86"):
        return "xp-x86-"
    if target.endswith("x64"):
        return "xp-x64-"
    return f"{target}-"


def xp_host_identity_run_marker(release_tag: str, observed_at_utc: str) -> str:
    version = release_tag.removeprefix("v").replace(".", "-")
    observed_marker = observed_at_utc.replace("-", "").replace(":", "").replace("T", "t").removesuffix("Z")
    return f"{version}-{observed_marker}z"


def normalized_host_os(raw_os: Any) -> dict[str, Any]:
    if not isinstance(raw_os, dict):
        return {}
    keys = ("name", "architecture", "service_pack", "edition")
    return {key: raw_os[key] for key in keys if key in raw_os}


def normalized_host_toolchain(raw_toolchain: Any) -> dict[str, Any]:
    if not isinstance(raw_toolchain, dict):
        return {}
    keys = ("separate_legacy_toolchain", "current_python_pyqt6_stack", "description")
    return {key: raw_toolchain[key] for key in keys if key in raw_toolchain}


def check_security(target: str, raw_security: Any, contract: dict[str, Any]) -> list[str]:
    if not isinstance(raw_security, dict):
        return [f"{target} evidence security must be an object"]
    errors: list[str] = []
    errors.extend(check_unexpected_fields(f"{target} evidence security", raw_security, XP_SECURITY_FIELDS))
    required_flags = contract.get("required_security_flags", {})
    for key, expected in required_flags.items():
        if raw_security.get(key) is not expected:
            errors.append(f"{target} evidence security.{key} must be {expected!r}")
    patch_evidence = raw_security.get("patch_evidence")
    if not isinstance(patch_evidence, dict):
        errors.append(f"{target} evidence security.patch_evidence must be an object")
        return errors
    errors.extend(
        check_unexpected_fields(
            f"{target} evidence security.patch_evidence",
            patch_evidence,
            XP_SECURITY_PATCH_FIELDS,
        )
    )
    required_patch_evidence = contract.get("required_security_patch_evidence", {})
    if isinstance(required_patch_evidence, dict):
        for key, expected in required_patch_evidence.items():
            if patch_evidence.get(key) != expected:
                errors.append(f"{target} evidence security.patch_evidence.{key} must be {expected!r}")
    required_patch_provenance = contract.get("required_security_patch_provenance_fields", [])
    if isinstance(required_patch_provenance, list):
        for key in sorted(str(item) for item in required_patch_provenance):
            value = patch_evidence.get(key, "")
            if not isinstance(value, str):
                errors.append(f"{target} evidence security.patch_evidence.{key} must be a string")
            elif not value.strip():
                errors.append(f"{target} evidence security.patch_evidence.{key} must be set")
            elif not is_concrete_security_provenance(value, key):
                errors.append(
                    f"{target} evidence security.patch_evidence.{key} "
                    "must name concrete non-placeholder provenance"
                )
    return errors


def security_patch_provenance_value(patch_evidence: dict[str, Any], field: str) -> str:
    value = patch_evidence.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def is_concrete_security_provenance(value: str, field: str = "") -> bool:
    lowered = value.strip().lower()
    if (
        not lowered
        or any(marker in lowered for marker in FORBIDDEN_SECURITY_PROVENANCE_MARKERS)
        or has_reserved_security_provenance_url(value)
    ):
        return False
    if field == "security_update_channel":
        return any(marker in lowered for marker in SECURITY_UPDATE_PROVENANCE_MARKERS)
    if field == "cve_review_reference":
        return any(marker in lowered for marker in CVE_REVIEW_PROVENANCE_MARKERS)
    return True


def has_reserved_security_provenance_url(value: str) -> bool:
    for match in SECURITY_PROVENANCE_URL_RE.finditer(value):
        raw_url = match.group(0).rstrip(".,);]}")
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            return True
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme.casefold() != "https":
            return True
        if host in RESERVED_SECURITY_PROVENANCE_URL_HOSTS:
            return True
        if any(host.endswith(suffix) for suffix in RESERVED_SECURITY_PROVENANCE_URL_SUFFIXES):
            return True
    return False


def check_smoke_results(
    target: str,
    release_tag: str,
    raw_results: Any,
    contract: dict[str, Any],
    evidence_root: Path,
    *,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
    security: Any,
) -> list[str]:
    if not isinstance(raw_results, list):
        return [f"{target} evidence smoke_results must be a list"]
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    smoke_ids: list[str] = []
    for item in raw_results:
        if not isinstance(item, dict):
            errors.append(f"{target} smoke result entries must be objects")
            continue
        raw_smoke_id = item.get("id")
        smoke_id = raw_smoke_id if isinstance(raw_smoke_id, str) else ""
        expected_fields = contract.get("required_smoke_result_fields")
        allowed_fields = (
            {field for field in expected_fields if isinstance(field, str)}
            if isinstance(expected_fields, list)
            else XP_SMOKE_RESULT_FIELDS
        )
        errors.extend(
            check_unexpected_fields(
                f"{target} smoke result {smoke_id or '<missing-id>'}",
                item,
                allowed_fields,
            )
        )
        if not isinstance(raw_smoke_id, str):
            errors.append(f"{target} smoke result entry id must be a string")
            continue
        if not smoke_id:
            errors.append(f"{target} smoke result entry missing id")
            continue
        smoke_ids.append(smoke_id)
        by_id[smoke_id] = item
    required = {
        item
        for item in contract.get("required_smoke_ids", [])
        if isinstance(item, str) and item
    }
    actual = set(smoke_ids)
    missing = sorted(required - set(by_id))
    if missing:
        errors.append(f"{target} evidence missing smoke results: {missing}")
    unexpected = sorted(actual - required)
    if unexpected:
        errors.append(f"{target} evidence contains unexpected smoke results: {unexpected}")
    duplicates = sorted(smoke_id for smoke_id in actual if smoke_ids.count(smoke_id) > 1)
    if duplicates:
        errors.append(f"{target} evidence contains duplicate smoke results: {duplicates}")
    for smoke_id in sorted(required & set(by_id)):
        item = by_id[smoke_id]
        if item.get("passed") is not True:
            errors.append(f"{target} smoke result {smoke_id} must have passed=true")
        evidence_sha = item.get("evidence_sha256", "")
        if not lowercase_sha256_hex(evidence_sha):
            errors.append(
                f"{target} smoke result {smoke_id} evidence_sha256 "
                "must be a lowercase SHA-256 hex digest"
            )
        errors.extend(
            check_smoke_command(
                target,
                release_tag,
                smoke_id,
                item,
                contract,
                host_identity=host_identity,
                os_identity=os_identity,
                release_source=release_source,
                security=security,
            )
        )
        errors.extend(
            check_smoke_evidence_file(
                target,
                release_tag,
                smoke_id,
                item,
                evidence_root,
                contract,
                host_identity=host_identity,
                os_identity=os_identity,
                release_source=release_source,
                security=security,
            )
        )
    return errors


def check_smoke_command(
    target: str,
    release_tag: str,
    smoke_id: str,
    item: dict[str, Any],
    contract: dict[str, Any],
    *,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
    security: Any,
) -> list[str]:
    raw_command = item.get("command")
    if raw_command is None:
        return [f"{target} smoke result {smoke_id} missing command provenance"]
    if not isinstance(raw_command, str):
        return [f"{target} smoke result {smoke_id} command must be a string"]
    command = raw_command.strip()
    if not command:
        return [f"{target} smoke result {smoke_id} missing command provenance"]
    if "<" in command or ">" in command:
        return [f"{target} smoke result {smoke_id} command must be concrete, got {command!r}"]
    errors: list[str] = []
    command_prefix = str(contract.get("required_smoke_command_prefix", ""))
    if command_prefix and not command.startswith(f"{command_prefix} "):
        errors.append(
            f"{target} smoke result {smoke_id} command must start with {command_prefix!r}, got {command!r}"
        )
    raw_evidence_file = item.get("evidence_file")
    evidence_file: str | None
    if raw_evidence_file is None:
        evidence_file = ""
    elif not isinstance(raw_evidence_file, str):
        errors.append(f"{target} smoke result {smoke_id} evidence_file must be a string")
        evidence_file = None
    else:
        evidence_file = raw_evidence_file.strip()
    errors.extend(
        check_smoke_command_binding(
            target,
            release_tag,
            smoke_id,
            command,
            evidence_file=evidence_file,
            label=f"{target} smoke result {smoke_id} command",
            host_identity=host_identity,
            os_identity=os_identity,
            release_source=release_source,
            security=security,
            contract=contract,
        )
    )
    return errors


def check_smoke_command_binding(
    target: str,
    release_tag: str,
    smoke_id: str,
    command: str,
    *,
    evidence_file: str | None = None,
    label: str,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
    security: Any,
    contract: dict[str, Any],
) -> list[str]:
    expected_values = {
        "--target": target,
        "--release-tag": release_tag,
        "--smoke-id": smoke_id,
        "--proof-file": f"xp-smoke-proof/{smoke_id}.txt",
    }
    if evidence_file is not None:
        expected_values["--evidence-file"] = evidence_file
    if isinstance(host_identity, dict):
        expected_values["--host-label"] = str(host_identity.get("host_label", ""))
        expected_values["--evidence-run-id"] = str(host_identity.get("evidence_run_id", ""))
        expected_values["--observed-at-utc"] = str(host_identity.get("observed_at_utc", ""))
    if isinstance(release_source, dict):
        expected_values["--source-workflow-run-url"] = str(release_source.get("workflow_run_url", "")).rstrip("/")
        expected_values["--source-head-sha"] = str(release_source.get("head_sha", ""))
        expected_values["--source-run-attempt"] = str(release_source.get("run_attempt", ""))
    if isinstance(os_identity, dict):
        expected_values["--os-name"] = str(os_identity.get("name", ""))
        expected_values["--os-architecture"] = str(os_identity.get("architecture", ""))
        expected_values["--os-service-pack"] = str(os_identity.get("service_pack", ""))
        edition = str(os_identity.get("edition", "")).strip()
        if edition:
            expected_values["--os-edition"] = edition
    errors: list[str] = []
    for flag, expected in expected_values.items():
        values = command_flag_values(command, flag)
        if values != [expected]:
            errors.append(f"{label} must include exactly one {flag} {expected}, got {values}")
    if isinstance(os_identity, dict) and not str(os_identity.get("edition", "")).strip():
        edition_values = command_flag_values(command, "--os-edition")
        if edition_values:
            errors.append(f"{label} must omit --os-edition for this target, got {edition_values}")
    if smoke_id_requires_security_provenance(smoke_id, contract):
        patch_evidence = security.get("patch_evidence") if isinstance(security, dict) else None
        if isinstance(patch_evidence, dict):
            security_command_flags = {
                "--security-update-channel": "security_update_channel",
                "--cve-review-reference": "cve_review_reference",
            }
            for flag, field in security_command_flags.items():
                expected = security_patch_provenance_value(patch_evidence, field)
                if expected:
                    values = command_flag_values(command, flag)
                    if values != [expected]:
                        errors.append(f"{label} must include exactly one {flag} {expected}, got {values}")
    return errors


def smoke_id_requires_security_provenance(smoke_id: str, contract: dict[str, Any]) -> bool:
    required = contract.get("required_security_smoke_evidence_lines")
    return isinstance(required, dict) and smoke_id in {str(key) for key in required}


def command_flag_values(command: str, flag: str) -> list[str]:
    pattern = rf'(?:^|\s){re.escape(flag)}\s+(?:"([^"]+)"|(\S+))(?=\s|$)'
    return [quoted or bare for quoted, bare in re.findall(pattern, command)]


def check_smoke_evidence_file(
    target: str,
    release_tag: str,
    smoke_id: str,
    item: dict[str, Any],
    evidence_root: Path,
    contract: dict[str, Any],
    *,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
    security: Any,
) -> list[str]:
    if contract.get("required_smoke_evidence_file") is not True:
        return []
    raw_file = item.get("evidence_file")
    if not isinstance(raw_file, str):
        return [f"{target} smoke result {smoke_id} evidence_file must be a string"]
    if not raw_file:
        return [f"{target} smoke result {smoke_id} missing evidence_file"]
    expected_file = f"xp-smoke-evidence/{smoke_id}.txt"
    if raw_file != expected_file:
        return [f"{target} smoke result {smoke_id} evidence_file must be {expected_file}"]
    evidence_file = Path(raw_file)
    if evidence_file.is_absolute():
        return [f"{target} smoke result {smoke_id} evidence_file must be relative"]
    symlink = first_symlink_in_relative_path(evidence_root, evidence_file)
    if symlink is not None:
        return [
            f"{target} smoke result {smoke_id} evidence_file path must not contain symlinks: "
            f"{display_relative_path(evidence_root, symlink)}"
        ]
    resolved = (evidence_root / evidence_file).resolve()
    try:
        resolved.relative_to(evidence_root)
    except ValueError:
        return [f"{target} smoke result {smoke_id} evidence_file must stay inside evidence directory"]
    if not resolved.is_file():
        return [f"{target} smoke result {smoke_id} evidence_file missing: {raw_file}"]
    data = resolved.read_bytes()
    if not data:
        return [f"{target} smoke result {smoke_id} evidence_file must not be empty: {raw_file}"]
    expected_sha = item.get("evidence_sha256", "")
    actual_sha = hashlib.sha256(data).hexdigest()
    errors: list[str] = []
    if lowercase_sha256_hex(expected_sha) and actual_sha != expected_sha:
        errors.append(f"{target} smoke result {smoke_id} evidence_file SHA-256 mismatch: {raw_file}")
    errors.extend(check_forbidden_patterns_bytes(data, contract, label=f"{smoke_id} evidence_file"))
    errors.extend(
        check_smoke_evidence_binding(
            target,
            release_tag,
            smoke_id,
            data,
            host_identity=host_identity,
            os_identity=os_identity,
            release_source=release_source,
        )
    )
    errors.extend(check_security_smoke_evidence_lines(target, smoke_id, data, contract, security=security))
    errors.extend(check_artifact_manifest_smoke_evidence(target, release_tag, smoke_id, data, contract))
    return errors


def first_symlink_in_relative_path(root: Path, relative_path: Path) -> Path | None:
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


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


def display_relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def check_smoke_evidence_binding(
    target: str,
    release_tag: str,
    smoke_id: str,
    data: bytes,
    *,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} smoke result {smoke_id} evidence_file must be UTF-8 text for binding validation: {exc}"]
    targets = xp_smoke_line_values(text, "xp smoke target")
    smoke_ids = xp_smoke_line_values(text, "xp smoke id")
    release_tags = xp_smoke_line_values(text, "xp smoke release")
    host_labels = xp_smoke_line_values(text, "xp smoke host label")
    evidence_run_ids = xp_smoke_line_values(text, "xp smoke evidence run id")
    observed_at_values = xp_smoke_line_values(text, "xp smoke observed at utc")
    source_workflow_run_urls = [value.rstrip("/") for value in xp_smoke_line_values(text, "xp smoke source workflow run")]
    source_head_shas = xp_smoke_line_values(text, "xp smoke source head sha")
    source_run_attempts = xp_smoke_line_values(text, "xp smoke source run attempt")
    os_names = xp_smoke_line_values(text, "xp smoke os name")
    os_architectures = xp_smoke_line_values(text, "xp smoke os architecture")
    os_service_packs = xp_smoke_line_values(text, "xp smoke os service pack")
    os_editions = xp_smoke_line_values(text, "xp smoke os edition")
    host_probe_commands = xp_smoke_line_values(text, "xp smoke host probe command")
    host_probe_outputs = xp_smoke_line_values(text, "xp smoke host probe output")
    processor_architectures = xp_smoke_line_values(text, "xp smoke processor architecture env")
    processor_architectures_w6432 = xp_smoke_line_values(text, "xp smoke processor architecture w6432 env")
    wmic_os_captions = xp_smoke_line_values(text, "xp smoke wmic os caption")
    wmic_os_csdversions = xp_smoke_line_values(text, "xp smoke wmic os csdversion")
    errors: list[str] = []
    if targets != [target]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file target binding must be {[target]}, got {targets}"
        )
    if release_tags != [release_tag]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file release binding must be {[release_tag]}, got {release_tags}"
        )
    if smoke_ids != [smoke_id]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file smoke-id binding must be {[smoke_id]}, got {smoke_ids}"
        )
    expected_host_label = ""
    expected_run_id = ""
    expected_observed_at = ""
    if isinstance(host_identity, dict):
        expected_host_label = str(host_identity.get("host_label", ""))
        expected_run_id = str(host_identity.get("evidence_run_id", ""))
        expected_observed_at = str(host_identity.get("observed_at_utc", ""))
    if host_labels != [expected_host_label]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file host-label binding "
            f"must be {[expected_host_label]}, got {host_labels}"
        )
    if evidence_run_ids != [expected_run_id]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file evidence-run-id binding "
            f"must be {[expected_run_id]}, got {evidence_run_ids}"
        )
    if observed_at_values != [expected_observed_at]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file observed-at-utc binding "
            f"must be {[expected_observed_at]}, got {observed_at_values}"
        )
    expected_source_workflow_run_url = ""
    expected_source_head_sha = ""
    expected_source_run_attempt = ""
    if isinstance(release_source, dict):
        expected_source_workflow_run_url = str(release_source.get("workflow_run_url", "")).rstrip("/")
        expected_source_head_sha = str(release_source.get("head_sha", ""))
        expected_source_run_attempt = str(release_source.get("run_attempt", ""))
    if source_workflow_run_urls != [expected_source_workflow_run_url]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file source workflow run binding "
            f"must be {[expected_source_workflow_run_url]}, got {source_workflow_run_urls}"
        )
    if source_head_shas != [expected_source_head_sha]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file source head SHA binding "
            f"must be {[expected_source_head_sha]}, got {source_head_shas}"
        )
    if source_run_attempts != [expected_source_run_attempt]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file source run attempt binding "
            f"must be {[expected_source_run_attempt]}, got {source_run_attempts}"
        )
    expected_os_name = ""
    expected_os_architecture = ""
    expected_os_service_pack = ""
    expected_os_edition = ""
    if isinstance(os_identity, dict):
        expected_os_name = str(os_identity.get("name", "")).strip()
        expected_os_architecture = str(os_identity.get("architecture", "")).strip()
        expected_os_service_pack = str(os_identity.get("service_pack", "")).strip()
        expected_os_edition = str(os_identity.get("edition", "")).strip()
    if os_names != [expected_os_name]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file OS name binding "
            f"must be {[expected_os_name]}, got {os_names}"
        )
    if os_architectures != [expected_os_architecture]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file OS architecture binding "
            f"must be {[expected_os_architecture]}, got {os_architectures}"
        )
    if os_service_packs != [expected_os_service_pack]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file OS service-pack binding "
            f"must be {[expected_os_service_pack]}, got {os_service_packs}"
        )
    if expected_os_edition and os_editions != [expected_os_edition]:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file OS edition binding "
            f"must be {[expected_os_edition]}, got {os_editions}"
        )
    if not expected_os_edition and os_editions:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file OS edition binding "
            f"must be omitted for this target, got {os_editions}"
        )
    errors.extend(
        check_xp_smoke_host_probe_binding(
            target,
            smoke_id,
            host_probe_commands=host_probe_commands,
            host_probe_outputs=host_probe_outputs,
            processor_architectures=processor_architectures,
            processor_architectures_w6432=processor_architectures_w6432,
            wmic_os_captions=wmic_os_captions,
            wmic_os_csdversions=wmic_os_csdversions,
            os_identity=os_identity,
        )
    )
    return errors


def xp_smoke_line_values(text: str, key: str) -> list[str]:
    prefix = f"{key}:"
    return sorted(
        line.split(":", 1)[1].strip()
        for raw_line in text.splitlines()
        if (line := raw_line.strip()).startswith(prefix)
    )


def check_xp_smoke_host_probe_binding(
    target: str,
    smoke_id: str,
    *,
    host_probe_commands: list[str],
    host_probe_outputs: list[str],
    processor_architectures: list[str],
    processor_architectures_w6432: list[str],
    wmic_os_captions: list[str],
    wmic_os_csdversions: list[str],
    os_identity: Any,
) -> list[str]:
    label = f"{target} smoke result {smoke_id} evidence_file"
    errors: list[str] = []
    if host_probe_commands != ["ver"]:
        errors.append(f"{label} host-probe command must be ['ver'], got {host_probe_commands}")
    expected_marker = XP_VER_VERSION_MARKERS.get(target, "")
    if len(host_probe_outputs) != 1 or not expected_marker or expected_marker not in host_probe_outputs[0]:
        errors.append(
            f"{label} host-probe ver output must contain Windows XP version marker "
            f"{expected_marker!r}, got {host_probe_outputs}"
        )
    normalized_arches = {value.lower() for value in processor_architectures}
    normalized_w6432 = {value.lower() for value in processor_architectures_w6432 if value}
    if len(processor_architectures_w6432) != 1:
        errors.append(
            f"{label} processor architecture w6432 env must have exactly one proof line, "
            f"got {processor_architectures_w6432}"
        )
    if target == "windows-xp-native-x86":
        if normalized_arches != XP_PROCESSOR_ARCHITECTURE_VALUES[target]:
            errors.append(
                f"{label} processor architecture env must be ['x86'] for XP x86, "
                f"got {processor_architectures}"
            )
        if normalized_w6432:
            errors.append(
                f"{label} processor architecture w6432 env must be empty for XP x86, "
                f"got {processor_architectures_w6432}"
            )
    if target == "windows-xp-native-x64":
        if "amd64" not in normalized_arches and "amd64" not in normalized_w6432:
            errors.append(
                f"{label} processor architecture env must prove AMD64 for XP x64, "
                f"got PROCESSOR_ARCHITECTURE={processor_architectures}, "
                f"PROCESSOR_ARCHITEW6432={processor_architectures_w6432}"
            )
    caption = wmic_os_captions[0] if len(wmic_os_captions) == 1 else ""
    caption_lower = caption.lower()
    if len(wmic_os_captions) != 1 or "windows" not in caption_lower or "xp" not in caption_lower:
        errors.append(f"{label} WMIC OS caption must prove Windows XP, got {wmic_os_captions}")
    if target == "windows-xp-native-x86" and "x64" in caption_lower:
        errors.append(f"{label} WMIC OS caption must not be x64 for XP x86, got {wmic_os_captions}")
    if target == "windows-xp-native-x64" and "x64" not in caption_lower:
        errors.append(f"{label} WMIC OS caption must prove x64 edition, got {wmic_os_captions}")
    expected_service_pack = ""
    if isinstance(os_identity, dict):
        expected_service_pack = str(os_identity.get("service_pack", "")).strip()
    if len(wmic_os_csdversions) != 1 or not service_pack_probe_matches(
        wmic_os_csdversions[0],
        expected_service_pack,
    ):
        errors.append(
            f"{label} WMIC OS CSDVersion must prove {expected_service_pack!r}, "
            f"got {wmic_os_csdversions}"
        )
    return errors


def service_pack_probe_matches(probe_value: str, expected_service_pack: str) -> bool:
    match = re.fullmatch(r"SP(\d+)", expected_service_pack.strip(), flags=re.IGNORECASE)
    if not match:
        return False
    number = match.group(1)
    normalized = re.sub(r"[^a-z0-9]+", " ", probe_value.lower()).strip()
    compact = normalized.replace(" ", "")
    return f"service pack {number}" in normalized or f"sp{number}" in compact


def check_artifact_manifest_smoke_evidence(
    target: str,
    release_tag: str,
    smoke_id: str,
    data: bytes,
    contract: dict[str, Any],
) -> list[str]:
    if smoke_id != "artifact_manifest_validation":
        return []
    if not isinstance(contract.get("required_artifact_manifest_smoke_evidence_lines"), list):
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [
            f"{target} smoke result {smoke_id} evidence_file must be UTF-8 text for artifact proof: {exc}"
        ]
    errors: list[str] = []
    expected = expected_artifact_names(target, release_tag, errors)
    if not expected:
        return errors
    artifact_lines = xp_smoke_line_values(text, "xp smoke artifact file")
    expected_lines = sorted(expected)
    if artifact_lines != expected_lines:
        errors.append(
            f"{target} smoke result {smoke_id} evidence_file artifact list proof "
            f"must match expected release artifacts {expected_lines}, got {artifact_lines}"
        )
    errors.extend(
        check_required_xp_smoke_proof_lines(
            target,
            smoke_id,
            text,
            (
                "xp smoke artifact manifest validated: true",
                "xp smoke artifact sha256s validated: true",
            ),
            proof_kind="artifact",
        )
    )
    return errors


def check_security_smoke_evidence_lines(
    target: str,
    smoke_id: str,
    data: bytes,
    contract: dict[str, Any],
    *,
    security: Any,
) -> list[str]:
    required = contract.get("required_security_smoke_evidence_lines")
    if not isinstance(required, dict):
        return []
    raw_lines = required.get(smoke_id)
    if not isinstance(raw_lines, list):
        return []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} smoke result {smoke_id} evidence_file must be UTF-8 text for security proof: {exc}"]
    errors: list[str] = []
    errors.extend(
        check_required_xp_smoke_proof_lines(
            target,
            smoke_id,
            text,
            [str(line) for line in raw_lines],
            proof_kind="security",
        )
    )
    errors.extend(
        check_security_smoke_provenance_lines(
            target,
            smoke_id,
            text,
            contract,
            security=security,
        )
    )
    forbidden = contract.get("forbidden_security_smoke_evidence_lines")
    if isinstance(forbidden, dict):
        raw_forbidden_lines = forbidden.get(smoke_id)
        if isinstance(raw_forbidden_lines, list):
            normalized_observed = xp_smoke_normalized_lines(text)
            for line in raw_forbidden_lines:
                forbidden_line = str(line).strip()
                if forbidden_line.lower() in normalized_observed:
                    errors.append(
                        f"{target} smoke result {smoke_id} evidence_file "
                        f"contains forbidden security proof line: {forbidden_line}"
            )
    return errors


def check_security_smoke_provenance_lines(
    target: str,
    smoke_id: str,
    text: str,
    contract: dict[str, Any],
    *,
    security: Any,
) -> list[str]:
    fields = contract.get("required_security_smoke_provenance_fields")
    if not isinstance(fields, list):
        return []
    patch_evidence = security.get("patch_evidence") if isinstance(security, dict) else None
    if not isinstance(patch_evidence, dict):
        return []
    labels = {
        "security_update_channel": "security update channel",
        "cve_review_reference": "CVE review reference",
    }
    errors: list[str] = []
    for field in sorted(str(item) for item in fields):
        expected_value = security_patch_provenance_value(patch_evidence, field)
        if not expected_value:
            continue
        label = labels.get(field, field.replace("_", " "))
        expected = f"{label}: {expected_value}"
        errors.extend(
            check_required_xp_smoke_proof_lines(
                target,
                smoke_id,
                text,
                (expected,),
                proof_kind="security",
            )
        )
    return errors


def xp_smoke_stripped_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def xp_smoke_normalized_lines(text: str) -> set[str]:
    return {line.lower() for line in xp_smoke_stripped_lines(text)}


def check_required_xp_smoke_proof_lines(
    target: str,
    smoke_id: str,
    text: str,
    required_lines: tuple[str, ...] | list[str],
    *,
    proof_kind: str,
) -> list[str]:
    observed = xp_smoke_stripped_lines(text)
    errors: list[str] = []
    for raw_line in required_lines:
        required_line = str(raw_line).strip()
        if not required_line:
            continue
        count = sum(1 for line in observed if line == required_line)
        if count == 0:
            errors.append(
                f"{target} smoke result {smoke_id} evidence_file missing {proof_kind} proof line: "
                f"{required_line}"
            )
        elif count != 1:
            errors.append(
                f"{target} smoke result {smoke_id} evidence_file must include exactly one "
                f"{proof_kind} proof line: {required_line} (got {count})"
            )
    return errors


def check_artifact_validation_record(target: str, raw_record: Any, release_tag: str) -> list[str]:
    if not isinstance(raw_record, dict):
        return [f"{target} evidence artifact_validation must be an object"]
    errors: list[str] = []
    errors.extend(
        check_unexpected_fields(
            f"{target} evidence artifact_validation",
            raw_record,
            XP_ARTIFACT_VALIDATION_FIELDS,
        )
    )
    if raw_record.get("passed") is not True:
        errors.append(f"{target} evidence artifact_validation.passed must be true")
    raw_command = raw_record.get("command")
    if not isinstance(raw_command, str):
        errors.append(f"{target} evidence artifact_validation.command must be a string")
        return errors
    command = raw_command
    expected = f"python scripts/check_platform_promotion_artifacts.py --target {target} "
    if not command.startswith(expected):
        errors.append(f"{target} evidence artifact_validation.command must start with {expected!r}")
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    if tags != [release_tag]:
        errors.append(
            f"{target} evidence artifact_validation.command must include exactly one --tag {release_tag}, got {tags}"
        )
    strict_count = command_flag_count(command, "--strict")
    if strict_count != 1:
        errors.append(
            f"{target} evidence artifact_validation.command must include exactly one --strict, got {strict_count}"
        )
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1:
        errors.append(
            f"{target} evidence artifact_validation.command must include exactly one --assets-dir, got {asset_dirs}"
        )
    elif "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        errors.append(f"{target} evidence artifact_validation.command --assets-dir must be concrete, got {asset_dirs[0]!r}")
    else:
        errors.extend(check_artifact_validation_assets_dir(target, release_tag, asset_dirs[0]))
    return errors


def check_artifact_validation_assets_dir(target: str, release_tag: str, raw_path: str) -> list[str]:
    path = raw_path.strip()
    errors: list[str] = []
    if any(char in path for char in "*?"):
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must not contain wildcards, got {raw_path!r}"
        )
    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    windows_absolute = windows_path.is_absolute() or bool(windows_path.drive)
    posix_absolute = posix_path.is_absolute()
    if "\\" in path or windows_absolute:
        parts = windows_path.parts
    else:
        parts = posix_path.parts
    is_absolute = windows_absolute or posix_absolute
    if is_absolute:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must be workspace-relative, got {raw_path!r}"
        )
    if any(part == ".." for part in parts):
        errors.append(f"{target} evidence artifact_validation.command --assets-dir must not traverse directories")
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if not normalized_parts:
        errors.append(f"{target} evidence artifact_validation.command --assets-dir must not point at the workspace root")
    else:
        reserved_root = normalized_parts[0]
        if reserved_root in RESERVED_WORKSPACE_ROOTS:
            errors.append(
                f"{target} evidence artifact_validation.command --assets-dir "
                f"must not point inside reserved workspace directory {reserved_root!r}"
            )
        hidden_segments = sorted(
            {
                part
                for part in normalized_parts
                if part.startswith(".") and part not in RESERVED_WORKSPACE_ROOTS
            }
        )
        if hidden_segments:
            errors.append(
                f"{target} evidence artifact_validation.command --assets-dir "
                f"must not contain hidden path segments: {hidden_segments}"
            )
    if target not in normalized_parts:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must include target path segment {target!r}, got {raw_path!r}"
        )
    if release_tag not in normalized_parts:
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must include release_tag path segment {release_tag!r}, got {raw_path!r}"
        )
    if directory_path_has_file_suffix(path):
        errors.append(
            f"{target} evidence artifact_validation.command --assets-dir "
            f"must be a directory path, got {raw_path!r}"
        )
    return errors


def directory_path_has_file_suffix(raw_path: str) -> bool:
    path = raw_path.strip()
    if not path:
        return False
    leaf = PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name
    leaf = leaf.lower()
    return any(leaf.endswith(suffix) for suffix in FILE_LIKE_DIRECTORY_SUFFIXES)


def command_flag_count(command: str, flag: str) -> int:
    return len(re.findall(rf"(?:^|\s){re.escape(flag)}(?=\s|$)", command))


def artifact_validation_asset_dirs(evidence: dict[str, Any]) -> list[str]:
    raw_record = evidence.get("artifact_validation")
    if not isinstance(raw_record, dict):
        return []
    command = raw_record.get("command")
    if not isinstance(command, str):
        return []
    return re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)


def check_artifact_names(
    target: str,
    raw_artifacts: Any,
    target_contract: dict[str, Any],
    release_tag: str,
) -> list[str]:
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        return [f"{target} evidence artifacts must be a non-empty list"]
    required_target = str(target_contract.get("required_artifact_target", ""))
    errors: list[str] = []
    artifact_names: list[str] = []
    for artifact in raw_artifacts:
        if not isinstance(artifact, str):
            errors.append(f"{target} evidence artifact name entries must be strings")
            continue
        artifact_name = artifact.strip()
        artifact_names.append(artifact_name)
        errors.extend(check_artifact_name_shape(target, artifact_name))
        if required_target not in artifact_name:
            errors.append(f"{target} evidence artifact name must include {required_target}: {artifact_name}")
    expected_artifacts = expected_artifact_names(target, release_tag, errors)
    if expected_artifacts:
        artifact_set = set(artifact_names)
        duplicate_artifacts = sorted(name for name in artifact_set if artifact_names.count(name) > 1)
        if duplicate_artifacts:
            errors.append(f"{target} evidence artifacts contain duplicate names: {duplicate_artifacts}")
        missing = sorted(expected_artifacts - artifact_set)
        if missing:
            errors.append(f"{target} evidence artifacts missing expected names: {missing}")
        unexpected = sorted(artifact_set - expected_artifacts)
        if unexpected:
            errors.append(f"{target} evidence artifacts contain unexpected names: {unexpected}")
    return errors


def check_artifact_name_shape(target: str, artifact_name: str) -> list[str]:
    path = artifact_name.strip()
    errors: list[str] = []
    if not path:
        return [f"{target} evidence artifact name must be set"]
    if any(char in path for char in "*?"):
        errors.append(f"{target} evidence artifact name must not contain wildcards: {artifact_name!r}")
    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    windows_absolute = windows_path.is_absolute() or bool(windows_path.drive)
    posix_absolute = posix_path.is_absolute()
    if windows_absolute or posix_absolute:
        errors.append(f"{target} evidence artifact name must be a file name, got {artifact_name!r}")
    parts = windows_path.parts if ("\\" in path or windows_absolute) else posix_path.parts
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if any(part == ".." for part in normalized_parts):
        errors.append(f"{target} evidence artifact name must not traverse directories: {artifact_name!r}")
    if normalized_parts != (path,):
        errors.append(f"{target} evidence artifact name must be a file name, got {artifact_name!r}")
    return errors


def expected_artifact_names(target: str, release_tag: str, errors: list[str]) -> set[str]:
    version_errors: list[str] = []
    version = version_from_tag(release_tag, version_errors)
    if version_errors:
        return set()
    promotion = read_promotion_json(PROMOTION_PATH)
    entries = promotion_entries(promotion, errors)
    entry = entries.get(target)
    if entry is None:
        errors.append(f"XP native evidence promotion config missing target: {target}")
        return set()
    return {expand_version(name, version) for name in required_artifacts(entry)}


def check_forbidden_patterns(raw_text: str, contract: dict[str, Any]) -> list[str]:
    return check_forbidden_patterns_text(raw_text, contract, label="XP native evidence")


def check_forbidden_patterns_text(raw_text: str, contract: dict[str, Any], *, label: str) -> list[str]:
    normalized = raw_text.lower()
    errors: list[str] = []
    for pattern in contract.get("forbidden_evidence_patterns", []):
        needle = str(pattern)
        if needle.lower() in normalized:
            errors.append(f"{label} contains forbidden sensitive pattern: {needle}")
    return errors


def check_forbidden_patterns_bytes(raw_data: bytes, contract: dict[str, Any], *, label: str) -> list[str]:
    normalized = raw_data.lower()
    errors: list[str] = []
    for pattern in contract.get("forbidden_evidence_patterns", []):
        needle = str(pattern).encode("utf-8").lower()
        if needle in normalized:
            errors.append(f"{label} contains forbidden sensitive pattern: {pattern}")
    return errors


def target_contract_for(
    contract: dict[str, Any],
    target: str,
    errors: list[str],
) -> dict[str, Any] | None:
    targets = contract.get("targets")
    if not isinstance(targets, dict):
        errors.append("XP native evidence contract targets must be an object")
        return None
    raw_target = targets.get(target)
    if not isinstance(raw_target, dict):
        errors.append(f"unknown XP native evidence target: {target}")
        return None
    return raw_target


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


if __name__ == "__main__":
    raise SystemExit(main())
