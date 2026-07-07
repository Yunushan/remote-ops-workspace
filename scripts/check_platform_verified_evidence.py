from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
XP_CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"

LINUX_TARGETS = {
    "linux-i386": {
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "artifact_template": "extended-linux-evidence-linux-i386-{release_tag}",
        "runner_labels": {"self-hosted", "linux", "i386"},
        "machine_names": {"i386", "i486", "i586", "i686", "x86"},
    },
    "linux-armhf": {
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "artifact_template": "extended-linux-evidence-linux-armhf-{release_tag}",
        "runner_labels": {"self-hosted", "linux", "armhf"},
        "machine_names": {"armv6l", "armv7l", "armv7hl", "armhf"},
    },
}
XP_TARGETS = {
    "windows-xp-native-x86": {
        "architecture": "x86",
        "workflow": ".github/workflows/xp-native-evidence.yml",
    },
    "windows-xp-native-x64": {
        "architecture": "x64",
        "workflow": ".github/workflows/xp-native-evidence.yml",
    },
}
XP_WORKFLOW_INPUT_KEYS = {
    "target",
    "release_tag",
    "release_asset_base_url",
    "assets_dir",
    "evidence_file",
    "evidence_dir",
}
XP_NATIVE_EVIDENCE_VALIDATION_COMMAND_FLAGS = {
    "--evidence",
    "--assets-dir",
    "--evidence-dir",
}
LINUX_WORKFLOW_INPUT_KEYS = {
    "target",
    "release_tag",
    "release_asset_base_url",
}
ARTIFACT_VALIDATION_COMMAND_FLAGS = {
    "--target",
    "--assets-dir",
    "--tag",
    "--strict",
}
COMMON_LOCAL_EVIDENCE_PREFLIGHT_FLAGS = {
    "--root",
    "--release-tag",
    "--target",
    "--assets-dir",
}
LINUX_LOCAL_EVIDENCE_PREFLIGHT_FLAGS = {
    *COMMON_LOCAL_EVIDENCE_PREFLIGHT_FLAGS,
    "--linux-builder-evidence",
    "--linux-smoke-evidence",
    "--linux-workflow-run-url",
    "--linux-source-head-sha",
    "--linux-source-run-attempt",
}
XP_LOCAL_EVIDENCE_PREFLIGHT_FLAGS = {
    *COMMON_LOCAL_EVIDENCE_PREFLIGHT_FLAGS,
    "--xp-evidence",
    "--xp-evidence-dir",
    "--xp-source-workflow-run-url",
    "--xp-source-head-sha",
    "--xp-source-run-attempt",
}
LINUX_STAGED_UPLOAD_COMMAND_FLAGS = {
    "--target",
    "--release-tag",
    "--source-dir",
    "--out-dir",
    "--force",
}
XP_STAGED_UPLOAD_COMMAND_FLAGS = {
    "--target",
    "--release-tag",
    "--assets-dir",
    "--evidence-output-dir",
    "--out-dir",
    "--force",
}
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
KNOWN_TARGETS = {*LINUX_TARGETS, *XP_TARGETS}
PROTECTED_GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
REVIEW_BUNDLE_TYPES = {
    "linux-i386": "extended-linux-native-evidence",
    "linux-armhf": "extended-linux-native-evidence",
    "windows-xp-native-x86": "windows-xp-native-host-evidence",
    "windows-xp-native-x64": "windows-xp-native-host-evidence",
}
REQUIRED_LINUX_CHECKS = {
    "builder_preflight",
    "native_build",
    "native_smoke",
    "artifact_validation",
    "release_asset_attachment",
}
REQUIRED_LINUX_SMOKE_IDS = {
    "native_smoke",
}
REQUIRED_LINUX_SMOKE_ARCHES = {
    "linux-i386": "i386",
    "linux-armhf": "armhf",
}
REQUIRED_LINUX_SMOKE_ARTIFACT_TEMPLATES = {
    "linux-i386": (
        "remote-ops-workspace-v{version}-linux-i386.deb",
        "remote-ops-workspace-v{version}-linux-i686.rpm",
        "remote-ops-workspace-v{version}-linux-i686.AppImage",
    ),
    "linux-armhf": (
        "remote-ops-workspace-v{version}-linux-armhf.deb",
        "remote-ops-workspace-v{version}-linux-armv7hl.rpm",
        "remote-ops-workspace-v{version}-linux-armhf.AppImage",
    ),
}
REQUIRED_LINUX_SMOKE_STEPS = (
    "DEB install",
    "DEB verify",
    "DEB upgrade",
    "DEB uninstall",
    "RPM install",
    "RPM verify",
    "RPM upgrade",
    "RPM uninstall",
    "AppImage install",
    "AppImage verify",
    "AppImage upgrade",
    "AppImage uninstall",
)
REQUIRED_XP_CHECKS = {
    "xp_native_evidence_validation",
    "artifact_validation",
    "vm_or_host_smoke",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "release_asset_attachment",
}
COMMON_EVIDENCE_KEYS = {
    "artifact_sha256",
    "artifact_validation_command",
    "checks",
    "evidence_type",
    "local_evidence_preflight_command",
    "promotion_config_sha256",
    "readiness_percent",
    "release_asset_source",
    "release_asset_urls",
    "release_tag",
    "status",
    "staged_upload_command",
    "target",
    "workflow",
    "workflow_inputs",
}
FINALIZED_EVIDENCE_KEYS = {
    "finalized_record_release_asset_url",
    "review_bundle",
}
LINUX_EVIDENCE_KEYS = COMMON_EVIDENCE_KEYS | {
    "artifact_name",
    "builder_identity",
    "builder_identity_sha256",
    "linux_evidence_sources",
    "linux_smoke_evidence_sha256",
    "linux_smoke_summary",
    "native_build_command",
    "native_smoke_command",
    "runner_labels",
    "workflow_run_url",
}
XP_EVIDENCE_KEYS = COMMON_EVIDENCE_KEYS | {
    "architecture",
    "current_python_pyqt6_stack",
    "native_evidence_validation_command",
    "separate_legacy_toolchain",
    "xp_evidence_contract_sha256",
    "xp_evidence_sha256",
    "xp_evidence_sources",
    "xp_evidence_summary",
    "xp_host_identity_sha256",
    "xp_smoke_evidence_sha256",
}
LINUX_EVIDENCE_SOURCE_RECORD_KEYS = {"file", "sha256", "size_bytes"}
XP_EVIDENCE_SOURCE_RECORD_KEYS = {"file", "path", "sha256", "size_bytes"}
XP_SMOKE_EVIDENCE_SOURCE_RECORD_KEYS = {"file", "sha256", "size_bytes"}
REQUIRED_XP_SMOKE_IDS = {
    "cli_launch",
    "gui_or_legacy_host_ui_launch",
    "loopback_profile_dry_run",
    "artifact_manifest_validation",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
}
REQUIRED_XP_SMOKE_COMMAND_PREFIX = "scripts/xp_smoke_runner.cmd"
REQUIRED_XP_TOOLCHAIN_FLAGS = {
    "separate_legacy_toolchain": True,
    "current_python_pyqt6_stack": False,
}
REQUIRED_XP_SECURITY_FLAGS = {
    "legacy_crypto_profile_scoped": True,
    "modern_defaults_unchanged": True,
    "weak_crypto_global_default": False,
}
XP_EVIDENCE_SUMMARY_KEYS = {
    "target",
    "release_tag",
    "host_identity",
    "os",
    "toolchain",
    "release_source",
    "security",
    "smoke_ids",
    "smoke_evidence_files",
    "smoke_commands",
}
XP_RELEASE_SOURCE_SUMMARY_KEYS = {
    "workflow",
    "workflow_run_url",
    "head_sha",
    "run_attempt",
}
XP_HOST_IDENTITY_KEYS = {
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
XP_OS_BASE_KEYS = {
    "name",
    "architecture",
    "service_pack",
}
XP_SUMMARY_TOOLCHAIN_KEYS = set(REQUIRED_XP_TOOLCHAIN_FLAGS)
XP_HOST_TOOLCHAIN_KEYS = set(REQUIRED_XP_TOOLCHAIN_FLAGS) | {"description"}
XP_SECURITY_KEYS = set(REQUIRED_XP_SECURITY_FLAGS) | {"patch_evidence"}
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
RELEASE_ASSET_SOURCE_TYPES = {"github-actions-artifact"}
RELEASE_ASSET_SOURCE_KEYS = {
    "artifact_name",
    "contains_files",
    "head_sha",
    "run_attempt",
    "type",
    "workflow",
    "workflow_run_url",
}
REVIEW_BUNDLE_KEYS = {
    "archive",
    "bundle_type",
    "manifest",
    "release_asset_urls",
    "sha256s",
}
REVIEW_BUNDLE_RECORD_KEYS = {"file", "sha256", "size_bytes"}
RELEASE_SOURCE_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HOST_IDENTITY_LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
HOST_IDENTITY_RUN_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{7,127}$")
OBSERVED_AT_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
REQUIRED_SECURITY_PATCH_EVIDENCE = {
    "tls_minimum_modern_profiles": "TLS 1.2",
    "tls_preferred_modern_profiles": "TLS 1.3",
    "legacy_compatibility_profile": "isolated-opt-in",
    "cve_patch_reviewed": True,
}
REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS = (
    "security_update_channel",
    "cve_review_reference",
)
XP_SECURITY_PATCH_EVIDENCE_KEYS = set(REQUIRED_SECURITY_PATCH_EVIDENCE) | set(
    REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS
)
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
REQUIRED_LINUX_SECURITY_SMOKE_VALUE_LINES = (
    "native installer smoke python ssl openssl",
    "native installer smoke openssl cli version",
    "native installer smoke security update channel",
    "native installer smoke CVE review reference",
)
REQUIRED_LINUX_SECURITY_SMOKE_LINES = (
    "native installer smoke TLS minimum modern profiles: TLS 1.2",
    "native installer smoke TLS preferred modern profiles: TLS 1.3",
    "native installer smoke legacy compatibility profile: isolated-opt-in",
    "native installer smoke legacy crypto scope: profile-only",
    "native installer smoke weak crypto global default: false",
    "native installer smoke modern defaults unchanged: true",
)
FORBIDDEN_LINUX_SECURITY_SMOKE_LINES = (
    "native installer smoke TLS minimum modern profiles: TLS 1.0",
    "native installer smoke TLS minimum modern profiles: TLS 1.1",
    "native installer smoke TLS preferred modern profiles: TLS 1.0",
    "native installer smoke TLS preferred modern profiles: TLS 1.1",
    "native installer smoke legacy compatibility profile: global",
    "native installer smoke legacy compatibility profile: global-default",
    "native installer smoke legacy crypto scope: global",
    "native installer smoke legacy crypto scope: global-default",
    "native installer smoke weak crypto global default: true",
    "native installer smoke modern defaults unchanged: false",
)
REQUIRED_LINUX_TOOLS = {
    "bash",
    "curl",
    "dpkg",
    "dpkg-deb",
    "getconf",
    "openssl",
    "rpm",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
}
REQUIRED_LINUX_DPKG_ARCHES = {
    "linux-i386": {"i386"},
    "linux-armhf": {"armhf"},
}
REQUIRED_LINUX_USERLAND_BITS = {
    "linux-i386": "32",
    "linux-armhf": "32",
}
LINUX_BUILDER_IDENTITY_KEYS = {
    "schema_version",
    "target",
    "release_tag",
    "workflow_run_url",
    "workflow_run_attempt",
    "workflow_ref",
    "workflow_sha",
    "source_head_sha",
    "observed_git_head_sha",
    "git_worktree_clean",
    "sys_platform",
    "platform_machine",
    "uname_machine",
    "dpkg_architecture",
    "userland_bits",
    "os_release",
    "kernel_release",
    "glibc_version",
    "python_version",
    "host_identity",
    "sudo_non_interactive",
    "required_tools",
    "security_patch_evidence",
}
LINUX_BUILDER_HOST_IDENTITY_KEYS = {
    "schema_version",
    "target",
    "release_tag",
    "workflow_run_url",
    "workflow_run_attempt",
    "host_label",
    "evidence_run_id",
    "observed_at_utc",
    "operator_private_data_redacted",
}
LINUX_SECURITY_PATCH_EVIDENCE_KEYS = {
    *REQUIRED_SECURITY_PATCH_EVIDENCE,
    *REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS,
    "python_ssl_openssl",
    "openssl_cli_version",
}
LINUX_SMOKE_SUMMARY_KEYS = {
    "target",
    "release_tag",
    "workflow_run_url",
    "workflow_run_attempt",
    "source_head_sha",
    "git_head_sha",
    "target_arch",
    "host_label",
    "evidence_run_id",
    "observed_at_utc",
    "uname_machine",
    "dpkg_architecture",
    "userland_bits",
    "os_release",
    "kernel_release",
    "glibc_version",
    "python_ssl_openssl",
    "openssl_cli_version",
    "security",
}
LINUX_SMOKE_SECURITY_SUMMARY_KEYS = {
    "tls_minimum_modern_profiles",
    "tls_preferred_modern_profiles",
    "legacy_compatibility_profile",
    "legacy_crypto_scope",
    "weak_crypto_global_default",
    "modern_defaults_unchanged",
    "security_update_channel",
    "cve_review_reference",
}
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_ACTIONS_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?$")
GITHUB_ACTIONS_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)/?$")
GITHUB_RELEASE_BASE_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)$"
)
GITHUB_RELEASE_ASSET_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)/.+"
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args([] if argv is None else argv)
    strict_errors = strict_platform_goal_arg_errors(args)
    if strict_errors:
        for error in strict_errors:
            print(f"platform verified evidence: {error}", file=sys.stderr)
        return 2
    required_targets = required_targets_from_args(args)
    try:
        errors = check_platform_verified_evidence(
            required_targets=required_targets,
            required_release_tag=args.release_tag,
            require_review_bundles=True,
        )
    except ValueError as exc:
        print(f"platform verified evidence: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"platform verified evidence: {error}", file=sys.stderr)
        return 1
    if required_targets:
        print(
            "platform verified evidence checks passed "
            f"for required targets: {', '.join(required_targets)}"
        )
    else:
        print("platform verified evidence checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate accepted platform evidence records."
    )
    parser.add_argument(
        "--require-target",
        action="append",
        choices=sorted(KNOWN_TARGETS),
        default=[],
        help="Require an accepted evidence record for this protected target.",
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help=(
            "Require accepted evidence for Linux i386, Linux armhf, "
            "Windows XP native x86, and Windows XP native x64; requires --release-tag."
        ),
    )
    parser.add_argument(
        "--require-review-bundles",
        action="store_true",
        help="Require each accepted evidence record to bind the packaged review bundle digests.",
    )
    parser.add_argument(
        "--allow-unfinalized-candidates",
        action="store_true",
        help=(
            "Deprecated guardrail: rejected by this CLI because "
            "configs/platform_verified_evidence.json is finalized-only."
        ),
    )
    parser.add_argument(
        "--release-tag",
        help="When requiring targets, require accepted evidence for this exact release tag.",
    )
    return parser.parse_args(argv)


def strict_platform_goal_arg_errors(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    _targets, target_errors = required_target_values(args.require_target)
    errors.extend(target_errors)
    if args.allow_unfinalized_candidates:
        errors.append(
            "--allow-unfinalized-candidates cannot be used with "
            "configs/platform_verified_evidence.json; validate unfinalized "
            "candidate records through the candidate-generation workflow before finalization"
        )
    if args.require_goal_targets and not args.release_tag:
        errors.append("--require-goal-targets requires --release-tag vX.Y.Z")
    return errors


def required_target_values(raw_targets: object) -> tuple[set[str], list[str]]:
    if raw_targets is None:
        return set(), []
    if isinstance(raw_targets, str):
        raw_targets = (raw_targets,)
    try:
        target_values = iter(raw_targets)
    except TypeError:
        return set(), [f"platform verified evidence required targets must be iterable, got {raw_targets!r}"]
    targets: set[str] = set()
    errors: list[str] = []
    for target in target_values:
        if not isinstance(target, str) or not target.strip():
            errors.append(f"platform verified evidence required target must be a non-empty string, got {target!r}")
            continue
        targets.add(target.strip())
    return targets, errors


def required_targets_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    targets, _errors = required_target_values(args.require_target)
    if args.require_goal_targets:
        targets.update(PROTECTED_GOAL_TARGETS)
    return tuple(target for target in PROTECTED_GOAL_TARGETS if target in targets) + tuple(
        sorted(targets - set(PROTECTED_GOAL_TARGETS))
    )


def check_platform_verified_evidence(
    *,
    registry: dict[str, Any] | None = None,
    promotion: dict[str, Any] | None = None,
    required_targets: tuple[str, ...] | list[str] | set[str] | None = None,
    required_release_tag: str | None = None,
    require_review_bundles: bool = False,
    check_consistency: bool = True,
) -> list[str]:
    registry_data = read_json(EVIDENCE_PATH) if registry is None else registry
    promotion_data = read_json(PROMOTION_PATH) if promotion is None else promotion
    errors: list[str] = []
    errors.extend(check_schema(registry_data))
    if errors:
        return errors
    promotion_entries = promotion_entries_by_id(promotion_data, errors)
    promotion_hash = promotion_config_sha256(promotion_data)
    invalid_targets: set[str] = set()
    for entry in registry_data.get("accepted_evidence", []):
        if not isinstance(entry, dict):
            errors.append("accepted_evidence entries must be objects")
            continue
        raw_target = entry.get("target", "")
        target = accepted_evidence_target(entry)
        entry_errors: list[str] = []
        if not isinstance(raw_target, str):
            entry_errors.append(f"accepted_evidence target must be a string, got {raw_target!r}")
        elif target in LINUX_TARGETS:
            entry_errors.extend(
                check_linux_evidence(
                    entry,
                    promotion_entries,
                    promotion_hash,
                    require_review_bundle=require_review_bundles,
                )
            )
        elif target in XP_TARGETS:
            entry_errors.extend(
                check_xp_evidence(
                    entry,
                    promotion_entries,
                    promotion_hash,
                    require_review_bundle=require_review_bundles,
                )
            )
        else:
            entry_errors.append(f"accepted_evidence target is not protected: {target}")
        if entry_errors and target:
            invalid_targets.add(target)
        errors.extend(entry_errors)
    if check_consistency:
        errors.extend(check_registry_consistency(registry_data))
    if required_targets:
        errors.extend(
            check_required_targets(
                registry_data,
                required_targets,
                required_release_tag=required_release_tag,
                invalid_targets=invalid_targets,
            )
        )
    return errors


def check_required_targets(
    registry: dict[str, Any],
    required_targets: tuple[str, ...] | list[str] | set[str],
    *,
    required_release_tag: str | None = None,
    invalid_targets: set[str] | None = None,
) -> list[str]:
    requested, target_errors = required_target_set(required_targets)
    invalid, invalid_target_errors = required_target_set(invalid_targets or set())
    if target_errors or invalid_target_errors:
        return target_errors + [
            error.replace("required platform evidence target", "invalid platform evidence target")
            for error in invalid_target_errors
        ]
    unknown = sorted(requested - KNOWN_TARGETS)
    if unknown:
        return [f"required platform evidence targets are not protected: {unknown}"]
    if set(PROTECTED_GOAL_TARGETS).issubset(requested) and required_release_tag is None:
        return ["protected platform goal required targets require --release-tag vX.Y.Z"]
    if required_release_tag is not None and not isinstance(required_release_tag, str):
        return [f"required_release_tag must be a string, got {required_release_tag!r}"]
    if required_release_tag is not None and not re.fullmatch(r"v\d+\.\d+\.\d+", required_release_tag):
        return [f"required_release_tag must look like vX.Y.Z: {required_release_tag}"]
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    accepted_targets: set[str] = set()
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        target = accepted_evidence_target(entry)
        if (
            target
            and entry.get("status") == "accepted"
            and entry.get("readiness_percent") == 100.0
            and (required_release_tag is None or entry.get("release_tag") == required_release_tag)
            and target not in invalid
        ):
            accepted_targets.add(target)
    missing = sorted(requested - accepted_targets)
    if required_release_tag is not None:
        if missing:
            return [
                f"missing required accepted evidence targets for release_tag {required_release_tag}: {missing}"
            ]
        if set(PROTECTED_GOAL_TARGETS).issubset(requested):
            entries: dict[str, dict[str, Any]] = {}
            for entry in rows:
                if not isinstance(entry, dict):
                    continue
                target = accepted_evidence_target(entry)
                if (
                    target in PROTECTED_GOAL_TARGETS
                    and entry.get("status") == "accepted"
                    and entry.get("release_tag") == required_release_tag
                    and target not in invalid
                ):
                    entries[target] = entry
            consistency_errors = check_protected_goal_release_consistency(entries, required_release_tag)
            if consistency_errors:
                return consistency_errors
        return []
    if missing:
        return [f"missing required accepted evidence targets: {missing}"]
    return []


def required_target_set(raw_targets: Any) -> tuple[set[str], list[str]]:
    targets: set[str] = set()
    errors: list[str] = []
    for target in raw_targets:
        if not isinstance(target, str) or not target.strip():
            errors.append(
                "required platform evidence target must be a non-empty string, "
                f"got {target!r}"
            )
            continue
        targets.add(target.strip())
    return targets, errors


def accepted_evidence_target(entry: dict[str, Any]) -> str:
    target = entry.get("target", "")
    return target if isinstance(target, str) else ""


def accepted_evidence_release_tag(entry: dict[str, Any]) -> str:
    release_tag = entry.get("release_tag", "")
    return release_tag.strip() if isinstance(release_tag, str) else ""


def check_protected_goal_release_consistency(
    entries: dict[str, dict[str, Any]],
    release_tag: str,
) -> list[str]:
    errors: list[str] = []
    repositories_by_target = {
        target: release_asset_repositories(entry.get("release_asset_urls"))
        for target, entry in entries.items()
        if target in PROTECTED_GOAL_TARGETS
    }
    repository_scope_errors = release_repository_scope_errors(
        repositories_by_target,
        (
            "protected platform goal evidence "
            f"for release_tag {release_tag} must derive exactly one safe GitHub release repository"
        ),
    )
    errors.extend(repository_scope_errors)
    if not repository_scope_errors:
        repositories = {
            next(iter(repositories))
            for repositories in repositories_by_target.values()
        }
        if len(repositories) != 1:
            errors.append(
                "protected platform goal evidence "
                f"for release_tag {release_tag} must use one GitHub release repository, "
                f"got {format_repositories_by_target(repositories_by_target)}"
            )
    heads_by_target = release_source_heads_by_target(entries)
    if len(heads_by_target) == len(PROTECTED_GOAL_TARGETS) and len(set(heads_by_target.values())) != 1:
        errors.append(
            "protected platform goal evidence "
            f"for release_tag {release_tag} must use one release source head SHA, "
            f"got {format_values_by_target(heads_by_target)}"
        )
    for run_url, attempts_by_target in sorted(release_source_run_attempt_conflicts(entries).items()):
        formatted = {target: attempts_by_target[target] for target in sorted(attempts_by_target)}
        errors.append(
            "protected platform goal evidence "
            f"for release_tag {release_tag} must not reuse one release source workflow run URL "
            f"with conflicting run attempts, got {run_url}: {formatted}"
        )
    return errors


def check_schema(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1 or isinstance(registry.get("schema_version"), bool):
        errors.append("configs/platform_verified_evidence.json schema_version must be 1")
    policy = str(registry.get("policy", ""))
    if "Only accepted evidence records" not in policy:
        errors.append("platform verified evidence policy must explain accepted evidence records")
    if "SHA-256" not in policy:
        errors.append("platform verified evidence policy must require per-artifact SHA-256 digests")
    if "safe relative non-link native archive entries" not in policy:
        errors.append(
            "platform verified evidence policy must require safe relative non-link native archive entries"
        )
    if "exact safe checksum and native manifest file references" not in policy:
        errors.append(
            "platform verified evidence policy must require exact safe checksum and native manifest file references"
        )
    if "target architecture/format manifest binding" not in policy:
        errors.append(
            "platform verified evidence policy must require target architecture/format manifest binding"
        )
    if "exact safe release asset URL filenames" not in policy:
        errors.append(
            "platform verified evidence policy must require exact safe release asset URL filenames"
        )
    if "exact required check lists" not in policy:
        errors.append("platform verified evidence policy must require exact accepted evidence check lists")
    if "exact workflow dispatch input sets" not in policy:
        errors.append("platform verified evidence policy must require exact workflow dispatch input sets")
    if "workflow dispatch release repository binding" not in policy:
        errors.append("platform verified evidence policy must require workflow dispatch release repository binding")
    if "exact evidence source record fields" not in policy:
        errors.append("platform verified evidence policy must require exact evidence source record fields")
    if "exact release source and review bundle fields" not in policy:
        errors.append("platform verified evidence policy must require exact release source and review bundle fields")
    if "builder identity" not in policy:
        errors.append("platform verified evidence policy must require Linux builder identity evidence")
    if "builder identity SHA-256" not in policy:
        errors.append("platform verified evidence policy must require Linux builder identity SHA-256 binding")
    if "builder identity release/run" not in policy:
        errors.append("platform verified evidence policy must require Linux builder identity release/run binding")
    if "Linux builder workflow provenance binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder workflow provenance binding")
    if "exact Linux builder identity fields" not in policy:
        errors.append("platform verified evidence policy must require exact Linux builder identity fields")
    if "Linux builder/smoke source file binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder/smoke source file binding")
    if "Linux builder/smoke host identity binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder/smoke host identity binding")
    if "Linux builder/smoke security evidence binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder/smoke security evidence binding")
    if "Linux builder source head SHA binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder source head SHA binding")
    if "Linux builder observed Git HEAD binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder observed Git HEAD binding")
    if "Linux builder clean checkout binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder clean checkout binding")
    if "Linux builder/smoke runtime OS identity binding" not in policy:
        errors.append("platform verified evidence policy must require Linux builder/smoke runtime OS identity binding")
    if "Linux builder host identity" not in policy:
        errors.append("platform verified evidence policy must require Linux builder host identity binding")
    if "Linux builder rpm and non-interactive sudo evidence" not in policy:
        errors.append("platform verified evidence policy must require Linux rpm and non-interactive sudo evidence")
    if "Linux security patch evidence" not in policy:
        errors.append("platform verified evidence policy must require Linux security patch evidence")
    if "Linux security smoke proof-line binding" not in policy:
        errors.append("platform verified evidence policy must require Linux security smoke proof-line binding")
    if "exact Linux smoke proof-line occurrence binding" not in policy:
        errors.append("platform verified evidence policy must require exact Linux smoke proof-line occurrence binding")
    if "case-insensitive Linux forbidden security proof-line rejection" not in policy:
        errors.append(
            "platform verified evidence policy must require case-insensitive Linux forbidden security proof-line rejection"
        )
    if "Linux native smoke summary binding" not in policy:
        errors.append("platform verified evidence policy must require Linux native smoke summary binding")
    if "Linux native build and smoke command provenance" not in policy:
        errors.append("platform verified evidence policy must require Linux native build and smoke command provenance")
    if "Linux smoke evidence SHA-256" not in policy:
        errors.append("platform verified evidence policy must require Linux smoke evidence SHA-256 binding")
    if "Linux smoke release/run/source head SHA binding" not in policy:
        errors.append("platform verified evidence policy must require Linux smoke release/run/source head SHA binding")
    if "Linux smoke runtime architecture and userland binding" not in policy:
        errors.append("platform verified evidence policy must require Linux smoke runtime architecture and userland binding")
    if "Linux smoke sanitized host identity and observed-at timestamp binding" not in policy:
        errors.append(
            "platform verified evidence policy must require Linux smoke sanitized host identity and observed-at timestamp binding"
        )
    if "Linux workflow dispatch inputs" not in policy:
        errors.append("platform verified evidence policy must require Linux workflow dispatch input binding")
    if "XP workflow dispatch inputs" not in policy:
        errors.append("platform verified evidence policy must require XP workflow dispatch input binding")
    if "XP evidence source file binding" not in policy:
        errors.append("platform verified evidence policy must require XP evidence source file binding")
    if "XP evidence release source binding" not in policy:
        errors.append("platform verified evidence policy must require XP evidence release source binding")
    if "XP evidence bundle" not in policy:
        errors.append("platform verified evidence policy must require XP evidence bundle digests")
    if "XP evidence validation command binding" not in policy:
        errors.append("platform verified evidence policy must require XP evidence validation command binding")
    if "review-bundle manifest release asset URL binding" not in policy:
        errors.append(
            "platform verified evidence policy must require review-bundle manifest release asset URL binding"
        )
    if "review bundle manifest" not in policy:
        errors.append("platform verified evidence policy must require review bundle manifest binding")
    if "review bundle release asset URLs" not in policy:
        errors.append("platform verified evidence policy must require review bundle release asset URL binding")
    if "release-importable artifact source" not in policy:
        errors.append("platform verified evidence policy must require release-importable artifact source binding")
    if "source artifact repository-id binding" not in policy:
        errors.append("platform verified evidence policy must require source artifact repository-id binding")
    if "source artifact run-created timestamp binding" not in policy:
        errors.append("platform verified evidence policy must require source artifact run-created timestamp binding")
    if "source artifact run-start timestamp binding" not in policy:
        errors.append("platform verified evidence policy must require source artifact run-start timestamp binding")
    if "source artifact run-window timestamp binding" not in policy:
        errors.append("platform verified evidence policy must require source artifact run-window timestamp binding")
    if "source artifact retention expiration binding" not in policy:
        errors.append("platform verified evidence policy must require source artifact retention expiration binding")
    if "release source head SHA binding" not in policy:
        errors.append("platform verified evidence policy must require release source head SHA binding")
    if "release source run-attempt binding" not in policy:
        errors.append("platform verified evidence policy must require release source run-attempt binding")
    if "same release source workflow run URL cannot carry conflicting run attempts" not in policy:
        errors.append(
            "platform verified evidence policy must forbid conflicting run attempts "
            "for one release source workflow run URL"
        )
    if (
        "protected platform goal records for one release must use one release source head SHA "
        "and target-specific release source workflow files plus positive release source run attempts"
        not in policy
    ):
        errors.append(
            "platform verified evidence policy must require protected platform goal source workflow, "
            "source head SHA and run-attempt binding"
        )
    if (
        "partial protected platform goal records must use one release_tag, GitHub repository, "
        "target-specific release source workflow file, release source head SHA and positive "
        "release source run attempt before promotion"
        not in policy
    ):
        errors.append(
            "platform verified evidence policy must require partial protected platform goal release scope, "
            "workflow and run-attempt binding"
        )
    if (
        "Windows XP x86/x64 pairs must use the same release_tag, GitHub repository, "
        "target-specific release source workflow file, release source head SHA and positive "
        "release source run attempts"
        not in policy
    ):
        errors.append(
            "platform verified evidence policy must require Windows XP pair source workflow, "
            "source head SHA and run-attempt binding"
        )
    if "release source workflow file binding" not in policy:
        errors.append("platform verified evidence policy must require release source workflow file binding")
    if "local protected-goal evidence preflight command binding" not in policy:
        errors.append(
            "platform verified evidence policy must require local protected-goal evidence preflight command binding"
        )
    if "source artifact staged upload command binding" not in policy:
        errors.append(
            "platform verified evidence policy must require source artifact staged upload command binding"
        )
    if "staged upload source/evidence/output root separation" not in policy:
        errors.append(
            "platform verified evidence policy must require staged upload source/evidence/output root separation"
        )
    if "finalized accepted-record source file" not in policy:
        errors.append("platform verified evidence policy must require finalized accepted-record source file binding")
    if "finalized accepted-record release asset URL binding" not in policy:
        errors.append(
            "platform verified evidence policy must require finalized accepted-record release asset URL binding"
        )
    if "canonical finalized accepted-record JSON byte binding" not in policy:
        errors.append(
            "platform verified evidence policy must require canonical finalized accepted-record JSON byte binding"
        )
    if "published native and review-bundle release asset byte binding" not in policy:
        errors.append(
            "platform verified evidence policy must require published native and review-bundle release asset byte binding"
        )
    if "published release asset GitHub id/API URL binding" not in policy:
        errors.append(
            "platform verified evidence policy must require published release asset GitHub id/API URL binding"
        )
    if "Linux release source artifact names must be target/release-scoped" not in policy:
        errors.append(
            "platform verified evidence policy must require target/release-scoped Linux release source artifacts"
        )
    if "Linux accepted evidence command paths must be target/release-scoped" not in policy:
        errors.append(
            "platform verified evidence policy must require target/release-scoped Linux accepted evidence paths"
        )
    if "XP release source artifact names must be target/release-scoped" not in policy:
        errors.append("platform verified evidence policy must require target/release-scoped XP release source artifacts")
    if "XP accepted evidence command paths must be target/release-scoped" not in policy:
        errors.append("platform verified evidence policy must require target/release-scoped XP accepted evidence paths")
    if "review bundle archive" not in policy:
        errors.append("platform verified evidence policy must require review bundle archive binding")
    if "safe relative non-symlink review bundle archive entries" not in policy:
        errors.append(
            "platform verified evidence policy must require safe relative non-symlink review bundle archive entries"
        )
    if "review bundle SHA-256 sidecar" not in policy:
        errors.append("platform verified evidence policy must require review bundle SHA-256 sidecar binding")
    if (
        "release uploads must include those review bundle files with matching size" not in policy
        or "checksum-sidecar coverage" not in policy
    ):
        errors.append(
            "platform verified evidence policy must require release upload review bundle size, "
            "SHA-256, and checksum-sidecar coverage"
        )
    if "canonical finalized accepted-record JSON with matching size and SHA-256" not in policy:
        errors.append(
            "platform verified evidence policy must require release upload finalized accepted-record "
            "canonical JSON size and SHA-256 binding"
        )
    if "XP evidence contract SHA-256" not in policy:
        errors.append("platform verified evidence policy must require XP evidence contract SHA-256 binding")
    if "XP evidence summary" not in policy:
        errors.append("platform verified evidence policy must require XP evidence summary binding")
    if "exact XP evidence summary fields" not in policy:
        errors.append("platform verified evidence policy must require exact XP evidence summary fields")
    if "XP host identity SHA-256" not in policy:
        errors.append("platform verified evidence policy must require XP host identity SHA-256 binding")
    if "XP sanitized target-scoped host identity binding" not in policy:
        errors.append("platform verified evidence policy must require XP sanitized target-scoped host identity binding")
    if "XP security patch evidence" not in policy:
        errors.append("platform verified evidence policy must require XP security patch evidence binding")
    if "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance" not in policy:
        errors.append("platform verified evidence policy must require tracked XP smoke runner provenance")
    if "canonical XP smoke proof-file command binding" not in policy:
        errors.append("platform verified evidence policy must require canonical XP smoke proof-file command binding")
    if "XP security smoke command provenance binding" not in policy:
        errors.append("platform verified evidence policy must require XP security smoke command provenance binding")
    if "XP smoke evidence-file summary binding" not in policy:
        errors.append("platform verified evidence policy must require XP smoke evidence-file summary binding")
    if "XP smoke host identity binding" not in policy:
        errors.append("platform verified evidence policy must require XP smoke host identity binding")
    if "XP smoke observed-at timestamp binding" not in policy:
        errors.append("platform verified evidence policy must require XP smoke observed-at timestamp binding")
    if "XP smoke OS identity binding" not in policy:
        errors.append("platform verified evidence policy must require XP smoke OS identity binding")
    if "XP smoke host probe proof-line binding" not in policy:
        errors.append("platform verified evidence policy must require XP smoke host probe proof-line binding")
    if "exact XP smoke proof-line occurrence binding" not in policy:
        errors.append("platform verified evidence policy must require exact XP smoke proof-line occurrence binding")
    if "case-insensitive XP forbidden security proof-line rejection" not in policy:
        errors.append(
            "platform verified evidence policy must require case-insensitive XP forbidden security proof-line rejection"
        )
    if "XP security smoke proof-line binding" not in policy:
        errors.append("platform verified evidence policy must require XP security smoke proof-line binding")
    if "promotion config SHA-256" not in policy:
        errors.append("platform verified evidence policy must require promotion config SHA-256 binding")
    if "unique target" not in policy:
        errors.append("platform verified evidence policy must require unique target records")
    if "no unrecognized top-level fields" not in policy:
        errors.append("platform verified evidence policy must reject unrecognized top-level fields")
    if "Windows XP x86/x64 pairs must use the same release_tag, GitHub repository" not in policy:
        errors.append("platform verified evidence policy must require same release_tag and GitHub repository for XP pairs")
    if "same GitHub repository" not in policy:
        errors.append("platform verified evidence policy must require same GitHub repository")
    accepted = registry.get("accepted_evidence")
    if not isinstance(accepted, list):
        errors.append("platform verified evidence accepted_evidence must be a list")
    return errors


def check_linux_evidence(
    entry: dict[str, Any],
    promotion_entries: dict[str, dict[str, Any]],
    promotion_hash: str,
    *,
    require_review_bundle: bool = False,
) -> list[str]:
    target = accepted_evidence_target(entry)
    expected = LINUX_TARGETS[target]
    errors = check_common_evidence(
        entry,
        target,
        REQUIRED_LINUX_CHECKS,
        promotion_entries,
        promotion_hash,
        require_review_bundle=require_review_bundle,
    )
    if entry.get("evidence_type") != "extended-linux-native":
        errors.append(f"{target} evidence_type must be extended-linux-native")
    if entry.get("workflow") != expected["workflow"]:
        errors.append(f"{target} workflow must be {expected['workflow']}")
    errors.extend(check_linux_command_provenance(target, entry, promotion_entries.get(target, {})))
    errors.extend(check_linux_workflow_inputs(target, entry))
    raw_release_tag = entry.get("release_tag", "")
    release_tag = raw_release_tag if isinstance(raw_release_tag, str) else ""
    expected_artifact_name = linux_release_source_artifact_name(target, release_tag)
    raw_workflow_run_url = entry.get("workflow_run_url", "")
    workflow_run_url = raw_workflow_run_url.strip().rstrip("/") if isinstance(raw_workflow_run_url, str) else ""
    workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url)
    if not isinstance(raw_workflow_run_url, str):
        errors.append(f"{target} workflow_run_url must be a string GitHub Actions run URL")
    elif not workflow_match:
        errors.append(f"{target} workflow_run_url must be a GitHub Actions run URL")
    else:
        release_repositories = release_asset_repositories(entry.get("release_asset_urls"))
        workflow_repository = workflow_match.group(1)
        if release_repositories and release_repositories != {workflow_repository}:
            errors.append(
                f"{target} workflow_run_url repository must match release asset repository "
                f"{sorted(release_repositories)}, got {workflow_repository}"
            )
    if entry.get("artifact_name") != expected_artifact_name:
        errors.append(f"{target} artifact_name must be {expected_artifact_name}")
    source = entry.get("release_asset_source")
    source_head_sha = ""
    source_run_attempt = None
    if isinstance(source, dict):
        raw_source_head_sha = source.get("head_sha", "")
        source_head_sha = raw_source_head_sha.strip() if isinstance(raw_source_head_sha, str) else ""
        source_run_attempt = source.get("run_attempt")
        if source.get("workflow_run_url") != entry.get("workflow_run_url"):
            errors.append(f"{target} release_asset_source.workflow_run_url must match workflow_run_url")
        if source.get("artifact_name") != expected_artifact_name:
            errors.append(f"{target} release_asset_source.artifact_name must be {expected_artifact_name}")
    errors.extend(check_linux_runner_labels(target, entry.get("runner_labels"), expected["runner_labels"]))
    errors.extend(
        check_linux_builder_identity(
            target,
            entry.get("builder_identity"),
            expected["machine_names"],
            release_tag=release_tag,
            workflow_run_url=workflow_run_url,
            workflow_run_attempt=source_run_attempt,
            source_head_sha=source_head_sha,
        )
    )
    errors.extend(check_linux_builder_identity_sha256(target, entry))
    errors.extend(check_linux_smoke_evidence_hashes(target, entry.get("linux_smoke_evidence_sha256")))
    errors.extend(
        check_linux_smoke_summary(
            target,
            entry.get("linux_smoke_summary"),
            release_tag=release_tag,
            workflow_run_url=workflow_run_url,
            workflow_run_attempt=source_run_attempt,
            source_head_sha=source_head_sha,
            expected_machines=expected["machine_names"],
            builder_identity=entry.get("builder_identity"),
        )
    )
    errors.extend(check_linux_evidence_sources(target, entry))
    return errors


def check_linux_runner_labels(target: str, raw_labels: Any, expected_labels: set[str]) -> list[str]:
    if not isinstance(raw_labels, list):
        return [f"{target} runner_labels must be a list"]
    errors: list[str] = []
    labels: list[str] = []
    for label in raw_labels:
        if not isinstance(label, str):
            errors.append(f"{target} runner_labels entries must be strings, got {label!r}")
            continue
        labels.append(label)
    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1
    actual = set(labels)
    case_collisions = case_insensitive_name_collisions(actual)
    if case_collisions:
        errors.append(
            f"{target} runner_labels must not collide on case-insensitive filesystems: {case_collisions}"
        )
    if not expected_labels.issubset(actual):
        errors.append(f"{target} runner_labels must include {sorted(expected_labels)}")
    duplicate_labels = sorted(label for label, count in label_counts.items() if count > 1)
    if duplicate_labels:
        errors.append(f"{target} runner_labels must not contain duplicates: {duplicate_labels}")
    return errors


def check_linux_command_provenance(
    target: str,
    entry: dict[str, Any],
    promotion_entry: dict[str, Any],
) -> list[str]:
    requirements = promotion_entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return [f"{target} promotion requirements must be an object"]
    arch = str(requirements.get("release_matrix_arch", ""))
    build_script = str(requirements.get("build_script", ""))
    smoke_script = str(requirements.get("smoke_script", ""))
    expected_build = f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash {build_script}"
    raw_workflow_run_url = entry.get("workflow_run_url", "")
    workflow_run_url = raw_workflow_run_url.strip().rstrip("/") if isinstance(raw_workflow_run_url, str) else ""
    source = entry.get("release_asset_source")
    raw_source_head_sha = source.get("head_sha", "") if isinstance(source, dict) else ""
    source_head_sha = raw_source_head_sha.strip() if isinstance(raw_source_head_sha, str) else ""
    source_run_attempt = source.get("run_attempt") if isinstance(source, dict) else ""
    raw_preflight_command = entry.get("local_evidence_preflight_command", "")
    preflight_command = raw_preflight_command if isinstance(raw_preflight_command, str) else ""
    builder_evidence_paths = command_argument_values(preflight_command, "--linux-builder-evidence")
    builder_evidence_path = builder_evidence_paths[0] if len(builder_evidence_paths) == 1 else "<builder-evidence>"
    expected_smoke = (
        f"bash {smoke_script} --target {target} "
        f"--workflow-run-url {workflow_run_url} --workflow-run-attempt {source_run_attempt} "
        f"--source-head-sha {source_head_sha} --builder-evidence {builder_evidence_path}"
    )
    errors: list[str] = []
    if entry.get("native_build_command") != expected_build:
        errors.append(f"{target} native_build_command must be {expected_build!r}")
    if len(builder_evidence_paths) != 1:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one "
            f"--linux-builder-evidence, got {builder_evidence_paths}"
        )
    if entry.get("native_smoke_command") != expected_smoke:
        errors.append(f"{target} native_smoke_command must be {expected_smoke!r}")
    return errors


def check_linux_workflow_inputs(target: str, entry: dict[str, Any]) -> list[str]:
    raw_inputs = entry.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        return [f"{target} evidence must include workflow_inputs object"]
    errors: list[str] = []
    input_keys: set[str] = set()
    for key in raw_inputs:
        if not isinstance(key, str):
            errors.append(f"{target} workflow_inputs keys must be strings, got {key!r}")
            continue
        input_keys.add(key)
    case_collisions = case_insensitive_name_collisions(input_keys)
    if case_collisions:
        errors.append(
            f"{target} workflow_inputs keys must not collide on case-insensitive filesystems: {case_collisions}"
        )
    missing_keys = sorted(LINUX_WORKFLOW_INPUT_KEYS - input_keys)
    unexpected_keys = sorted(input_keys - LINUX_WORKFLOW_INPUT_KEYS)
    if missing_keys:
        errors.append(f"{target} workflow_inputs missing keys: {missing_keys}")
    if unexpected_keys:
        errors.append(f"{target} workflow_inputs unexpected keys: {unexpected_keys}")
    raw_release_tag = entry.get("release_tag", "")
    release_tag = raw_release_tag if isinstance(raw_release_tag, str) else ""
    if raw_inputs.get("target") != target:
        errors.append(f"{target} workflow_inputs target must be {target}")
    if raw_inputs.get("release_tag") != release_tag:
        errors.append(f"{target} workflow_inputs release_tag must match record release_tag {release_tag}")
    base_url = str(raw_inputs.get("release_asset_base_url", ""))
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    if not release_match or release_match.group(2) != release_tag:
        errors.append(
            f"{target} workflow_inputs release_asset_base_url must be exactly "
            f"https://github.com/<owner>/<repo>/releases/download/{release_tag}"
        )
    release_assets = entry.get("release_asset_urls")
    if isinstance(release_assets, list) and base_url:
        if any(not str(url).startswith(f"{base_url}/") for url in release_assets):
            errors.append(f"{target} workflow_inputs release_asset_base_url must prefix every release_asset_url")
    source = entry.get("release_asset_source")
    raw_source_workflow_run_url = source.get("workflow_run_url", "") if isinstance(source, dict) else ""
    source_workflow_run_url = (
        raw_source_workflow_run_url.strip().rstrip("/")
        if isinstance(raw_source_workflow_run_url, str)
        else ""
    )
    source_match = GITHUB_ACTIONS_RUN_RE.fullmatch(source_workflow_run_url)
    if release_match and source_match and release_match.group(1) != source_match.group(1):
        errors.append(
            f"{target} workflow_inputs release_asset_base_url repository must match "
            f"release_asset_source.workflow_run_url repository {source_match.group(1)}, "
            f"got {release_match.group(1)}"
        )
    return errors


def check_linux_builder_identity_sha256(target: str, entry: dict[str, Any]) -> list[str]:
    raw_identity = entry.get("builder_identity")
    raw_digest = entry.get("builder_identity_sha256", "")
    errors: list[str] = []
    if not isinstance(raw_digest, str):
        errors.append(f"{target} builder_identity_sha256 must be a string SHA-256 hex digest")
        return errors
    digest = raw_digest
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"{target} builder_identity_sha256 must be a SHA-256 hex digest")
        return errors
    if not isinstance(raw_identity, dict):
        return errors
    if contains_non_string_json_object_key(raw_identity):
        errors.append(f"{target} builder_identity JSON object keys must be strings for SHA-256 verification")
        return errors
    if digest != json_sha256(raw_identity):
        errors.append(f"{target} builder_identity_sha256 must match builder_identity JSON SHA-256")
    return errors


def check_linux_evidence_sources(target: str, entry: dict[str, Any]) -> list[str]:
    raw_sources = entry.get("linux_evidence_sources")
    if not isinstance(raw_sources, dict):
        return [f"{target} linux_evidence_sources must be an object"]
    errors: list[str] = []
    expected_keys = {"builder_identity", "native_smoke"}
    keys: set[str] = set()
    for key in raw_sources:
        if not isinstance(key, str):
            errors.append(f"{target} linux_evidence_sources keys must be strings, got {key!r}")
            continue
        keys.add(key)
    case_collisions = case_insensitive_name_collisions(keys)
    if case_collisions:
        errors.append(
            f"{target} linux_evidence_sources keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing_keys = sorted(expected_keys - keys)
    unexpected_keys = sorted(keys - expected_keys)
    if missing_keys:
        errors.append(f"{target} linux_evidence_sources missing keys: {missing_keys}")
    if unexpected_keys:
        errors.append(f"{target} linux_evidence_sources unexpected keys: {unexpected_keys}")
    smoke_hashes = entry.get("linux_smoke_evidence_sha256")
    expected_records = {
        "builder_identity": {
            "file": f"builder-identity-{target}.json",
            "sha256": str(entry.get("builder_identity_sha256", "")),
        },
        "native_smoke": {
            "file": f"native-smoke-{target}.log",
            "sha256": str(
                smoke_hashes.get("native_smoke", "")
                if isinstance(smoke_hashes, dict)
                else ""
            ),
        },
    }
    for key, expected in expected_records.items():
        record = raw_sources.get(key)
        if not isinstance(record, dict):
            errors.append(f"{target} linux_evidence_sources.{key} must be an object")
            continue
        errors.extend(
            check_exact_object_keys(
                target,
                f"linux_evidence_sources.{key}",
                record,
                LINUX_EVIDENCE_SOURCE_RECORD_KEYS,
            )
        )
        if record.get("file") != expected["file"]:
            errors.append(f"{target} linux_evidence_sources.{key}.file must be {expected['file']}")
        if record.get("sha256") != expected["sha256"]:
            errors.append(f"{target} linux_evidence_sources.{key}.sha256 must match {key} evidence SHA-256")
        size = record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{target} linux_evidence_sources.{key}.size_bytes must be a positive integer")
    return errors


def check_exact_object_keys(
    target: str,
    label: str,
    raw_object: dict[str, Any],
    allowed_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    keys: set[str] = set()
    for key in raw_object:
        if not isinstance(key, str):
            errors.append(f"{target} {label} keys must be strings, got {key!r}")
            continue
        keys.add(key)
    case_collisions = case_insensitive_name_collisions(keys)
    missing = sorted(allowed_keys - keys)
    unexpected = sorted(keys - allowed_keys)
    if case_collisions:
        errors.append(
            f"{target} {label} keys must not collide on case-insensitive filesystems: {case_collisions}"
        )
    if missing:
        errors.append(f"{target} {label} missing fields: {missing}")
    if unexpected:
        errors.append(f"{target} {label} unexpected fields: {unexpected}")
    return errors


def required_string_field(
    target: str,
    label: str,
    key: str,
    raw_object: dict[str, Any],
    errors: list[str],
    *,
    display_key: str | None = None,
) -> tuple[str, bool]:
    raw_value = raw_object.get(key, "")
    if not isinstance(raw_value, str):
        errors.append(f"{target} {label} {display_key or key} must be a string")
        return "", False
    return raw_value.strip(), True


def check_linux_smoke_summary(
    target: str,
    raw_summary: Any,
    *,
    release_tag: str,
    workflow_run_url: str,
    workflow_run_attempt: object,
    source_head_sha: str,
    expected_machines: set[str],
    builder_identity: Any,
) -> list[str]:
    if not isinstance(raw_summary, dict):
        return [f"{target} linux_smoke_summary must be an object"]

    errors: list[str] = []
    errors.extend(check_exact_object_keys(target, "linux_smoke_summary", raw_summary, LINUX_SMOKE_SUMMARY_KEYS))
    if raw_summary.get("target") != target:
        errors.append(f"{target} linux_smoke_summary target must be {target}")
    if raw_summary.get("release_tag") != release_tag:
        errors.append(f"{target} linux_smoke_summary release_tag must match record release_tag {release_tag}")
    if raw_summary.get("workflow_run_url") != workflow_run_url:
        errors.append(f"{target} linux_smoke_summary workflow_run_url must match record workflow_run_url")

    summary_attempt = raw_summary.get("workflow_run_attempt")
    if not isinstance(summary_attempt, int) or isinstance(summary_attempt, bool) or summary_attempt < 1:
        errors.append(f"{target} linux_smoke_summary workflow_run_attempt must be a positive integer")
    elif summary_attempt != workflow_run_attempt:
        errors.append(f"{target} linux_smoke_summary workflow_run_attempt must match release_asset_source.run_attempt")

    summary_source_head, summary_source_head_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "source_head_sha",
        raw_summary,
        errors,
    )
    if summary_source_head_is_string and not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(summary_source_head):
        errors.append(f"{target} linux_smoke_summary source_head_sha must be a 40-character lowercase Git SHA")
    elif summary_source_head_is_string and summary_source_head != source_head_sha:
        errors.append(f"{target} linux_smoke_summary source_head_sha must match release_asset_source.head_sha")

    summary_git_head, summary_git_head_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "git_head_sha",
        raw_summary,
        errors,
    )
    if summary_git_head_is_string and not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(summary_git_head):
        errors.append(f"{target} linux_smoke_summary git_head_sha must be a 40-character lowercase Git SHA")
    elif summary_git_head_is_string and summary_git_head != source_head_sha:
        errors.append(f"{target} linux_smoke_summary git_head_sha must match release_asset_source.head_sha")

    expected_arch = REQUIRED_LINUX_SMOKE_ARCHES[target]
    if raw_summary.get("target_arch") != expected_arch:
        errors.append(f"{target} linux_smoke_summary target_arch must be {expected_arch!r}")

    raw_uname_machine, uname_machine_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "uname_machine",
        raw_summary,
        errors,
    )
    uname_machine = raw_uname_machine.lower()
    if uname_machine_is_string and uname_machine not in expected_machines:
        errors.append(
            f"{target} linux_smoke_summary uname_machine must be one of {sorted(expected_machines)}, "
            f"got {uname_machine!r}"
        )
    raw_dpkg_architecture, dpkg_architecture_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "dpkg_architecture",
        raw_summary,
        errors,
    )
    dpkg_architecture = raw_dpkg_architecture.lower()
    expected_dpkg_arches = REQUIRED_LINUX_DPKG_ARCHES[target]
    if dpkg_architecture_is_string and dpkg_architecture not in expected_dpkg_arches:
        errors.append(
            f"{target} linux_smoke_summary dpkg_architecture must be one of "
            f"{sorted(expected_dpkg_arches)}, got {dpkg_architecture!r}"
        )
    expected_bits = REQUIRED_LINUX_USERLAND_BITS[target]
    userland_bits, userland_bits_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "userland_bits",
        raw_summary,
        errors,
    )
    if userland_bits_is_string and userland_bits != expected_bits:
        errors.append(f"{target} linux_smoke_summary userland_bits must be {expected_bits!r}, got {userland_bits!r}")

    builder = builder_identity if isinstance(builder_identity, dict) else {}
    builder_host = builder.get("host_identity") if isinstance(builder.get("host_identity"), dict) else {}
    host_label, host_label_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "host_label",
        raw_summary,
        errors,
    )
    if host_label_is_string and (
        not HOST_IDENTITY_LABEL_RE.fullmatch(host_label) or not host_label.startswith(f"{target}-")
    ):
        errors.append(f"{target} linux_smoke_summary host_label must be a sanitized target-scoped label, got {host_label!r}")
    elif host_label_is_string and builder_host:
        expected_host_label = str(builder_host.get("host_label", "")).strip()
        if expected_host_label and host_label != expected_host_label:
            errors.append(
                f"{target} linux_smoke_summary host_label must match "
                f"builder_identity.host_identity.host_label {expected_host_label!r}, got {host_label!r}"
            )

    evidence_run_id, evidence_run_id_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "evidence_run_id",
        raw_summary,
        errors,
    )
    if evidence_run_id_is_string and (
        not HOST_IDENTITY_RUN_RE.fullmatch(evidence_run_id) or not evidence_run_id.startswith(f"{target}-")
    ):
        errors.append(
            f"{target} linux_smoke_summary evidence_run_id must be a sanitized target-scoped run id, "
            f"got {evidence_run_id!r}"
        )
    elif evidence_run_id_is_string and builder_host:
        expected_run_id = str(builder_host.get("evidence_run_id", "")).strip()
        if expected_run_id and evidence_run_id != expected_run_id:
            errors.append(
                f"{target} linux_smoke_summary evidence_run_id must match "
                f"builder_identity.host_identity.evidence_run_id {expected_run_id!r}, got {evidence_run_id!r}"
            )

    observed_at_value, observed_at_is_string = required_string_field(
        target,
        "linux_smoke_summary",
        "observed_at_utc",
        raw_summary,
        errors,
    )
    observed_at = observed_at_utc_datetime(observed_at_value)
    if observed_at_is_string and observed_at is None:
        errors.append(
            f"{target} linux_smoke_summary observed_at_utc must be UTC ISO-8601 seconds ending in Z, "
            f"got {observed_at_value!r}"
        )
    elif observed_at_is_string and builder_host:
        builder_observed_at_value = str(builder_host.get("observed_at_utc", "")).strip()
        builder_observed_at = observed_at_utc_datetime(builder_observed_at_value)
        if builder_observed_at is not None and observed_at < builder_observed_at:
            errors.append(
                f"{target} linux_smoke_summary observed_at_utc must not be earlier than "
                f"builder_identity.host_identity.observed_at_utc {builder_observed_at_value!r}, "
                f"got {observed_at_value!r}"
            )

    runtime_bindings = {
        "os_release": "os_release",
        "kernel_release": "kernel_release",
        "glibc_version": "glibc_version",
    }
    for summary_key, builder_key in runtime_bindings.items():
        value, value_is_string = required_string_field(
            target,
            "linux_smoke_summary",
            summary_key,
            raw_summary,
            errors,
        )
        if not value_is_string:
            continue
        if not value:
            errors.append(f"{target} linux_smoke_summary {summary_key} must be set")
            continue
        expected_value = str(builder.get(builder_key, "")).strip()
        if expected_value and value != expected_value:
            errors.append(
                f"{target} linux_smoke_summary {summary_key} must match "
                f"builder_identity.{builder_key} {expected_value!r}, got {value!r}"
            )

    builder_security = builder.get("security_patch_evidence") if isinstance(builder.get("security_patch_evidence"), dict) else {}
    for summary_key, builder_key in (
        ("python_ssl_openssl", "python_ssl_openssl"),
        ("openssl_cli_version", "openssl_cli_version"),
    ):
        value, value_is_string = required_string_field(
            target,
            "linux_smoke_summary",
            summary_key,
            raw_summary,
            errors,
        )
        if not value_is_string:
            continue
        if not value:
            errors.append(f"{target} linux_smoke_summary {summary_key} must be set")
            continue
        if not is_concrete_security_provenance(value):
            errors.append(f"{target} linux_smoke_summary {summary_key} must be concrete")
        expected_value = str(builder_security.get(builder_key, "")).strip()
        if expected_value and value != expected_value:
            errors.append(
                f"{target} linux_smoke_summary {summary_key} must match "
                f"builder_identity.security_patch_evidence.{builder_key} {expected_value!r}, got {value!r}"
            )

    errors.extend(check_linux_smoke_summary_security(target, raw_summary.get("security"), builder_security))
    return errors


def check_linux_smoke_summary_security(
    target: str,
    raw_security: Any,
    builder_security: dict[str, Any],
) -> list[str]:
    if not isinstance(raw_security, dict):
        return [f"{target} linux_smoke_summary security must be an object"]

    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "linux_smoke_summary security",
            raw_security,
            LINUX_SMOKE_SECURITY_SUMMARY_KEYS,
        )
    )
    expected_values: dict[str, object] = {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "legacy_crypto_scope": "profile-only",
        "weak_crypto_global_default": False,
        "modern_defaults_unchanged": True,
    }
    for key, expected in sorted(expected_values.items()):
        if raw_security.get(key) != expected:
            errors.append(f"{target} linux_smoke_summary security.{key} must be {expected!r}")

    for key in ("security_update_channel", "cve_review_reference"):
        value, value_is_string = required_string_field(
            target,
            "linux_smoke_summary",
            key,
            raw_security,
            errors,
            display_key=f"security.{key}",
        )
        if not value_is_string:
            continue
        if not value:
            errors.append(f"{target} linux_smoke_summary security.{key} must be set")
        elif not is_concrete_security_provenance(value, key):
            errors.append(f"{target} linux_smoke_summary security.{key} must name concrete non-placeholder provenance")

    for key in (
        "tls_minimum_modern_profiles",
        "tls_preferred_modern_profiles",
        "legacy_compatibility_profile",
        "security_update_channel",
        "cve_review_reference",
    ):
        expected = builder_security.get(key)
        if expected is not None and raw_security.get(key) != expected:
            errors.append(
                f"{target} linux_smoke_summary security.{key} must match "
                f"builder_identity.security_patch_evidence.{key} {expected!r}, got {raw_security.get(key)!r}"
            )
    return errors


def check_linux_required_tool_paths(target: str, raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, dict):
        return [f"{target} builder_identity required_tools must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "builder_identity required_tools",
            raw_tools,
            REQUIRED_LINUX_TOOLS,
        )
    )
    missing_tools = sorted(tool for tool in REQUIRED_LINUX_TOOLS if not str(raw_tools.get(tool, "")).strip())
    if missing_tools:
        errors.append(f"{target} builder_identity missing required tool paths: {missing_tools}")
    for tool in sorted(REQUIRED_LINUX_TOOLS):
        value = str(raw_tools.get(tool, "")).strip()
        if not value:
            continue
        if "<" in value or ">" in value:
            errors.append(f"{target} builder_identity required_tools.{tool} must be concrete, got {value!r}")
        elif not value.startswith("/"):
            errors.append(
                f"{target} builder_identity required_tools.{tool} must be an absolute Linux path, got {value!r}"
            )
    return errors


def check_linux_builder_identity(
    target: str,
    raw_identity: Any,
    expected_machines: set[str],
    *,
    release_tag: str,
    workflow_run_url: str,
    workflow_run_attempt: object,
    source_head_sha: str,
) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} evidence must include builder_identity object"]
    errors: list[str] = []
    errors.extend(check_exact_object_keys(target, "builder_identity", raw_identity, LINUX_BUILDER_IDENTITY_KEYS))
    if raw_identity.get("schema_version") != 1 or isinstance(raw_identity.get("schema_version"), bool):
        errors.append(f"{target} builder_identity schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} builder_identity target must be {target}")
    if raw_identity.get("release_tag") != release_tag:
        errors.append(f"{target} builder_identity release_tag must match record release_tag {release_tag}")
    if raw_identity.get("workflow_run_url") != workflow_run_url:
        errors.append(f"{target} builder_identity workflow_run_url must match record workflow_run_url")
    errors.extend(
        check_linux_builder_workflow_identity(
            target,
            raw_identity,
            workflow_run_url=workflow_run_url,
            source_head_sha=source_head_sha,
        )
    )
    if raw_identity.get("workflow_run_attempt") != workflow_run_attempt:
        errors.append(
            f"{target} builder_identity workflow_run_attempt must match release_asset_source.run_attempt"
        )
    if raw_identity.get("source_head_sha") != source_head_sha:
        errors.append(f"{target} builder_identity source_head_sha must match release_asset_source.head_sha")
    if raw_identity.get("observed_git_head_sha") != source_head_sha:
        errors.append(f"{target} builder_identity observed_git_head_sha must match release_asset_source.head_sha")
    if raw_identity.get("git_worktree_clean") is not True:
        errors.append(f"{target} builder_identity git_worktree_clean must be true")
    sys_platform = str(raw_identity.get("sys_platform", ""))
    if not sys_platform.startswith("linux"):
        errors.append(f"{target} builder_identity sys_platform must start with linux")
    if raw_identity.get("sudo_non_interactive") is not True:
        errors.append(f"{target} builder_identity sudo_non_interactive must be true")
    for key in ("platform_machine", "uname_machine"):
        value = str(raw_identity.get(key, "")).lower()
        if value not in expected_machines:
            errors.append(f"{target} builder_identity {key} must be one of {sorted(expected_machines)}, got {value!r}")
    dpkg_architecture = str(raw_identity.get("dpkg_architecture", "")).lower()
    expected_dpkg_arches = REQUIRED_LINUX_DPKG_ARCHES[target]
    if dpkg_architecture not in expected_dpkg_arches:
        errors.append(
            f"{target} builder_identity dpkg_architecture must be one of "
            f"{sorted(expected_dpkg_arches)}, got {dpkg_architecture!r}"
        )
    userland_bits = str(raw_identity.get("userland_bits", ""))
    expected_bits = REQUIRED_LINUX_USERLAND_BITS[target]
    if userland_bits != expected_bits:
        errors.append(f"{target} builder_identity userland_bits must be {expected_bits!r}, got {userland_bits!r}")
    version = python_version_tuple(str(raw_identity.get("python_version", "")))
    if version < (3, 10):
        errors.append(f"{target} builder_identity python_version must be 3.10 or newer")
    errors.extend(check_linux_runtime_identity(target, raw_identity))
    errors.extend(check_linux_required_tool_paths(target, raw_identity.get("required_tools")))
    errors.extend(
        check_linux_builder_host_identity(
            target,
            release_tag,
            workflow_run_url,
            workflow_run_attempt,
            raw_identity.get("host_identity"),
        )
    )
    errors.extend(check_linux_security_patch_evidence(target, raw_identity.get("security_patch_evidence")))
    return errors


def check_linux_builder_workflow_identity(
    target: str,
    raw_identity: dict[str, Any],
    *,
    workflow_run_url: str,
    source_head_sha: str,
) -> list[str]:
    errors: list[str] = []
    expected_workflow = release_source_workflow(target)
    workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url.rstrip("/"))
    expected_repository = workflow_match.group(1).lower() if workflow_match else ""
    workflow_ref = str(raw_identity.get("workflow_ref", "")).strip()
    if not workflow_ref:
        errors.append(f"{target} builder_identity workflow_ref must be set")
    else:
        expected_prefix = f"{expected_repository}/{expected_workflow}@"
        if not expected_repository or not workflow_ref.lower().startswith(expected_prefix.lower()):
            errors.append(
                f"{target} builder_identity workflow_ref must point at "
                f"{expected_prefix}<ref>, got {workflow_ref!r}"
            )
    workflow_sha = str(raw_identity.get("workflow_sha", "")).strip()
    if not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(workflow_sha):
        errors.append(f"{target} builder_identity workflow_sha must be a 40-character lowercase Git SHA")
    elif workflow_sha != source_head_sha:
        errors.append(f"{target} builder_identity workflow_sha must match release_asset_source.head_sha")
    return errors


def check_linux_builder_host_identity(
    target: str,
    release_tag: str,
    workflow_run_url: str,
    workflow_run_attempt: object,
    raw_identity: Any,
) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} builder_identity host_identity must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "builder_identity host_identity",
            raw_identity,
            LINUX_BUILDER_HOST_IDENTITY_KEYS,
        )
    )
    if raw_identity.get("schema_version") != 1 or isinstance(raw_identity.get("schema_version"), bool):
        errors.append(f"{target} builder_identity host_identity.schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} builder_identity host_identity.target must be {target}")
    if raw_identity.get("release_tag") != release_tag:
        errors.append(
            f"{target} builder_identity host_identity.release_tag must match record release_tag {release_tag}"
        )
    if raw_identity.get("workflow_run_url") != workflow_run_url:
        errors.append(f"{target} builder_identity host_identity.workflow_run_url must match record workflow_run_url")
    if raw_identity.get("workflow_run_attempt") != workflow_run_attempt:
        errors.append(
            f"{target} builder_identity host_identity.workflow_run_attempt must match "
            "release_asset_source.run_attempt"
        )
    host_label = str(raw_identity.get("host_label", "")).strip()
    if not HOST_IDENTITY_LABEL_RE.fullmatch(host_label) or not host_label.startswith(f"{target}-"):
        errors.append(
            f"{target} builder_identity host_identity.host_label must be a sanitized target-scoped label, "
            f"got {host_label!r}"
        )
    evidence_run_id = str(raw_identity.get("evidence_run_id", "")).strip()
    if not HOST_IDENTITY_RUN_RE.fullmatch(evidence_run_id) or not evidence_run_id.startswith(f"{target}-"):
        errors.append(
            f"{target} builder_identity host_identity.evidence_run_id must be a sanitized target-scoped run id, "
            f"got {evidence_run_id!r}"
        )
    observed_at = str(raw_identity.get("observed_at_utc", "")).strip()
    if not OBSERVED_AT_UTC_RE.fullmatch(observed_at):
        errors.append(
            f"{target} builder_identity host_identity.observed_at_utc must be UTC ISO-8601 seconds ending in Z, "
            f"got {observed_at!r}"
        )
    if raw_identity.get("operator_private_data_redacted") is not True:
        errors.append(f"{target} builder_identity host_identity.operator_private_data_redacted must be true")
    forbidden_fields = sorted(
        field
        for field in raw_identity
        if str(field).lower() in FORBIDDEN_HOST_IDENTITY_FIELDS
    )
    if forbidden_fields:
        errors.append(f"{target} builder_identity host_identity contains forbidden private fields: {forbidden_fields}")
    return errors


def python_version_tuple(version: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version)
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def check_linux_runtime_identity(target: str, raw_identity: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("os_release", "kernel_release", "glibc_version"):
        raw_value = raw_identity.get(key, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if not isinstance(raw_value, str):
            errors.append(f"{target} builder_identity {key} must be a string")
        elif not value:
            errors.append(f"{target} builder_identity {key} must be set")
    return errors


def check_xp_evidence(
    entry: dict[str, Any],
    promotion_entries: dict[str, dict[str, Any]],
    promotion_hash: str,
    *,
    require_review_bundle: bool = False,
) -> list[str]:
    target = accepted_evidence_target(entry)
    expected = XP_TARGETS[target]
    errors = check_common_evidence(
        entry,
        target,
        REQUIRED_XP_CHECKS,
        promotion_entries,
        promotion_hash,
        require_review_bundle=require_review_bundle,
    )
    if entry.get("evidence_type") != "windows-xp-native-host":
        errors.append(f"{target} evidence_type must be windows-xp-native-host")
    if entry.get("architecture") != expected["architecture"]:
        errors.append(f"{target} architecture must be {expected['architecture']}")
    raw_release_tag = entry.get("release_tag", "")
    release_tag = raw_release_tag if isinstance(raw_release_tag, str) else ""
    raw_command = entry.get("native_evidence_validation_command", "")
    command = raw_command if isinstance(raw_command, str) else ""
    if not isinstance(raw_command, str):
        errors.append(f"{target} native_evidence_validation_command must be a string command, got {raw_command!r}")
    errors.extend(check_xp_native_evidence_validation_command(target, release_tag, command))
    errors.extend(check_xp_workflow_inputs(target, entry, promotion_entries.get(target, {})))
    if entry.get("separate_legacy_toolchain") is not True:
        errors.append(f"{target} separate_legacy_toolchain must be true")
    if entry.get("current_python_pyqt6_stack") is not False:
        errors.append(f"{target} current_python_pyqt6_stack must be false")
    raw_evidence_sha = entry.get("xp_evidence_sha256", "")
    evidence_sha = raw_evidence_sha if isinstance(raw_evidence_sha, str) else ""
    if not isinstance(raw_evidence_sha, str):
        errors.append(f"{target} xp_evidence_sha256 must be a string SHA-256 hex digest")
    elif not re.fullmatch(r"[0-9a-f]{64}", evidence_sha):
        errors.append(f"{target} xp_evidence_sha256 must be a SHA-256 hex digest")
    raw_contract_sha = entry.get("xp_evidence_contract_sha256", "")
    contract_sha = raw_contract_sha if isinstance(raw_contract_sha, str) else ""
    if not isinstance(raw_contract_sha, str):
        errors.append(f"{target} xp_evidence_contract_sha256 must be a string SHA-256 hex digest")
    elif not re.fullmatch(r"[0-9a-f]{64}", contract_sha):
        errors.append(f"{target} xp_evidence_contract_sha256 must be a SHA-256 hex digest")
    elif contract_sha != xp_native_evidence_contract_sha256():
        errors.append(f"{target} xp_evidence_contract_sha256 must match current XP evidence contract SHA-256")
    raw_summary = entry.get("xp_evidence_summary")
    errors.extend(check_xp_evidence_summary(target, release_tag, raw_summary))
    errors.extend(
        check_xp_evidence_summary_release_source(
            target,
            raw_summary.get("release_source") if isinstance(raw_summary, dict) else None,
            entry.get("release_asset_source"),
        )
    )
    host_identity = raw_summary.get("host_identity") if isinstance(raw_summary, dict) else None
    errors.extend(check_xp_host_identity_sha256(target, entry.get("xp_host_identity_sha256", ""), host_identity))
    errors.extend(check_xp_smoke_evidence_hashes(target, entry.get("xp_smoke_evidence_sha256")))
    errors.extend(check_xp_evidence_sources(target, entry))
    return errors


def check_xp_evidence_sources(target: str, entry: dict[str, Any]) -> list[str]:
    raw_sources = entry.get("xp_evidence_sources")
    if not isinstance(raw_sources, dict):
        return [f"{target} xp_evidence_sources must be an object"]
    errors: list[str] = []
    expected_keys = {"evidence", "smoke_evidence"}
    keys: set[str] = set()
    for key in raw_sources:
        if not isinstance(key, str):
            errors.append(f"{target} xp_evidence_sources keys must be strings, got {key!r}")
            continue
        keys.add(key)
    case_collisions = case_insensitive_name_collisions(keys)
    if case_collisions:
        errors.append(
            f"{target} xp_evidence_sources keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing_keys = sorted(expected_keys - keys)
    unexpected_keys = sorted(keys - expected_keys)
    if missing_keys:
        errors.append(f"{target} xp_evidence_sources missing keys: {missing_keys}")
    if unexpected_keys:
        errors.append(f"{target} xp_evidence_sources unexpected keys: {unexpected_keys}")

    raw_inputs = entry.get("workflow_inputs")
    workflow_inputs = raw_inputs if isinstance(raw_inputs, dict) else {}
    evidence_record = raw_sources.get("evidence")
    if not isinstance(evidence_record, dict):
        errors.append(f"{target} xp_evidence_sources.evidence must be an object")
    else:
        errors.extend(
            check_exact_object_keys(
                target,
                "xp_evidence_sources.evidence",
                evidence_record,
                XP_EVIDENCE_SOURCE_RECORD_KEYS,
            )
        )
        if evidence_record.get("file") != "xp-evidence.json":
            errors.append(f"{target} xp_evidence_sources.evidence.file must be xp-evidence.json")
        if evidence_record.get("path") != workflow_inputs.get("evidence_file"):
            errors.append(f"{target} xp_evidence_sources.evidence.path must match workflow_inputs evidence_file")
        if evidence_record.get("sha256") != entry.get("xp_evidence_sha256"):
            errors.append(f"{target} xp_evidence_sources.evidence.sha256 must match xp_evidence_sha256")
        size = evidence_record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{target} xp_evidence_sources.evidence.size_bytes must be a positive integer")

    raw_summary = entry.get("xp_evidence_summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    raw_smoke_files = summary.get("smoke_evidence_files")
    smoke_files = raw_smoke_files if isinstance(raw_smoke_files, dict) else {}
    raw_smoke_hashes = entry.get("xp_smoke_evidence_sha256")
    smoke_hashes = raw_smoke_hashes if isinstance(raw_smoke_hashes, dict) else {}
    raw_smoke_sources = raw_sources.get("smoke_evidence")
    if not isinstance(raw_smoke_sources, dict):
        errors.append(f"{target} xp_evidence_sources.smoke_evidence must be an object")
        return errors
    smoke_source_keys: set[str] = set()
    for key in raw_smoke_sources:
        if not isinstance(key, str):
            errors.append(f"{target} xp_evidence_sources.smoke_evidence smoke ids must be strings, got {key!r}")
            continue
        smoke_source_keys.add(key)
    case_collisions = case_insensitive_name_collisions(smoke_source_keys)
    if case_collisions:
        errors.append(
            f"{target} xp_evidence_sources.smoke_evidence smoke ids must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing_smoke_keys = sorted(REQUIRED_XP_SMOKE_IDS - smoke_source_keys)
    unexpected_smoke_keys = sorted(smoke_source_keys - REQUIRED_XP_SMOKE_IDS)
    if missing_smoke_keys:
        errors.append(f"{target} xp_evidence_sources.smoke_evidence missing smoke ids: {missing_smoke_keys}")
    if unexpected_smoke_keys:
        errors.append(f"{target} xp_evidence_sources.smoke_evidence unexpected smoke ids: {unexpected_smoke_keys}")
    for smoke_id in sorted(REQUIRED_XP_SMOKE_IDS):
        record = raw_smoke_sources.get(smoke_id)
        if not isinstance(record, dict):
            errors.append(f"{target} xp_evidence_sources.smoke_evidence.{smoke_id} must be an object")
            continue
        errors.extend(
            check_exact_object_keys(
                target,
                f"xp_evidence_sources.smoke_evidence.{smoke_id}",
                record,
                XP_SMOKE_EVIDENCE_SOURCE_RECORD_KEYS,
            )
        )
        if record.get("file") != smoke_files.get(smoke_id):
            errors.append(
                f"{target} xp_evidence_sources.smoke_evidence.{smoke_id}.file "
                "must match xp_evidence_summary smoke_evidence_files"
            )
        if record.get("sha256") != smoke_hashes.get(smoke_id):
            errors.append(
                f"{target} xp_evidence_sources.smoke_evidence.{smoke_id}.sha256 "
                "must match xp_smoke_evidence_sha256"
            )
        size = record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(
                f"{target} xp_evidence_sources.smoke_evidence.{smoke_id}.size_bytes "
                "must be a positive integer"
            )
    return errors


def check_xp_workflow_inputs(
    target: str,
    entry: dict[str, Any],
    promotion_entry: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    requirements = promotion_entry.get("promotion_to_100_requires", {})
    expected_workflow = (
        str(requirements.get("release_source_workflow", ""))
        if isinstance(requirements, dict)
        else ""
    )
    if entry.get("workflow") != expected_workflow:
        errors.append(f"{target} workflow must be {expected_workflow}")
    raw_inputs = entry.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        errors.append(f"{target} evidence must include workflow_inputs object")
        return errors

    input_keys: set[str] = set()
    for key in raw_inputs:
        if not isinstance(key, str):
            errors.append(f"{target} workflow_inputs keys must be strings, got {key!r}")
            continue
        input_keys.add(key)
    case_collisions = case_insensitive_name_collisions(input_keys)
    if case_collisions:
        errors.append(
            f"{target} workflow_inputs keys must not collide on case-insensitive filesystems: {case_collisions}"
        )
    missing_keys = sorted(XP_WORKFLOW_INPUT_KEYS - input_keys)
    unexpected_keys = sorted(input_keys - XP_WORKFLOW_INPUT_KEYS)
    if missing_keys:
        errors.append(f"{target} workflow_inputs missing keys: {missing_keys}")
    if unexpected_keys:
        errors.append(f"{target} workflow_inputs unexpected keys: {unexpected_keys}")

    raw_release_tag = entry.get("release_tag", "")
    release_tag = raw_release_tag if isinstance(raw_release_tag, str) else ""
    if raw_inputs.get("target") != target:
        errors.append(f"{target} workflow_inputs target must be {target}")
    if raw_inputs.get("release_tag") != release_tag:
        errors.append(f"{target} workflow_inputs release_tag must match record release_tag {release_tag}")

    base_url = str(raw_inputs.get("release_asset_base_url", ""))
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    if not release_match or release_match.group(2) != release_tag:
        errors.append(
            f"{target} workflow_inputs release_asset_base_url must be exactly "
            f"https://github.com/<owner>/<repo>/releases/download/{release_tag}"
        )
    release_assets = entry.get("release_asset_urls")
    if isinstance(release_assets, list) and base_url:
        if any(not str(url).startswith(f"{base_url}/") for url in release_assets):
            errors.append(f"{target} workflow_inputs release_asset_base_url must prefix every release_asset_url")

    source = entry.get("release_asset_source")
    raw_source_workflow_run_url = source.get("workflow_run_url", "") if isinstance(source, dict) else ""
    source_workflow_run_url = (
        raw_source_workflow_run_url.strip().rstrip("/")
        if isinstance(raw_source_workflow_run_url, str)
        else ""
    )
    source_match = GITHUB_ACTIONS_RUN_RE.fullmatch(source_workflow_run_url)
    if release_match and source_match and release_match.group(1) != source_match.group(1):
        errors.append(
            f"{target} workflow_inputs release_asset_base_url repository must match "
            f"release_asset_source.workflow_run_url repository {source_match.group(1)}, "
            f"got {release_match.group(1)}"
        )

    raw_command = entry.get("native_evidence_validation_command", "")
    command = raw_command if isinstance(raw_command, str) else ""
    command_paths = xp_native_evidence_validation_command_paths(command)
    path_bindings = {
        "evidence_file": ("--evidence", command_paths["evidence_file"], True, False),
        "assets_dir": ("--assets-dir", command_paths["assets_dir"], False, True),
        "evidence_dir": ("--evidence-dir", command_paths["evidence_dir"], False, True),
    }
    for input_key, (command_flag, command_values, require_json, require_directory) in path_bindings.items():
        input_value = str(raw_inputs.get(input_key, "")).strip()
        if not input_value:
            errors.append(f"{target} workflow_inputs {input_key} must be set")
            continue
        if len(command_values) == 1 and input_value != command_values[0]:
            errors.append(
                f"{target} workflow_inputs {input_key} must match "
                f"native_evidence_validation_command {command_flag}"
            )
        errors.extend(
            check_xp_validation_command_path(
                target,
                input_key,
                input_value,
                command_label="workflow_inputs",
                require_json_hint=require_json,
                require_directory_hint=require_directory,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    return errors


def xp_native_evidence_validation_command_paths(command: str) -> dict[str, list[str]]:
    return {
        "evidence_file": re.findall(r"(?:^|\s)--evidence\s+(\S+)(?=\s|$)", command),
        "assets_dir": re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command),
        "evidence_dir": re.findall(r"(?:^|\s)--evidence-dir\s+(\S+)(?=\s|$)", command),
    }


def check_xp_native_evidence_validation_command(target: str, release_tag: str, command: str) -> list[str]:
    expected_prefix = "python scripts/check_xp_native_evidence.py "
    errors: list[str] = []
    if not command.startswith(expected_prefix):
        errors.append(f"{target} native_evidence_validation_command must start with {expected_prefix!r}")
    errors.extend(
        check_no_unexpected_command_flags(
            target,
            "native_evidence_validation_command",
            command,
            XP_NATIVE_EVIDENCE_VALIDATION_COMMAND_FLAGS,
        )
    )
    evidence_paths = re.findall(r"(?:^|\s)--evidence\s+(\S+)(?=\s|$)", command)
    if len(evidence_paths) != 1:
        errors.append(
            f"{target} native_evidence_validation_command must include exactly one --evidence, "
            f"got {evidence_paths}"
        )
    elif "<" in evidence_paths[0] or ">" in evidence_paths[0]:
        errors.append(
            f"{target} native_evidence_validation_command --evidence must be concrete, "
            f"got {evidence_paths[0]!r}"
        )
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--evidence",
                evidence_paths[0],
                command_label="native_evidence_validation_command",
                require_json_hint=True,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1:
        errors.append(
            f"{target} native_evidence_validation_command must include exactly one --assets-dir, "
            f"got {asset_dirs}"
        )
    elif "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        errors.append(
            f"{target} native_evidence_validation_command --assets-dir must be concrete, "
            f"got {asset_dirs[0]!r}"
        )
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--assets-dir",
                asset_dirs[0],
                command_label="native_evidence_validation_command",
                require_directory_hint=True,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    evidence_dirs = re.findall(r"(?:^|\s)--evidence-dir\s+(\S+)(?=\s|$)", command)
    if len(evidence_dirs) != 1:
        errors.append(
            f"{target} native_evidence_validation_command must include exactly one --evidence-dir, "
            f"got {evidence_dirs}"
        )
    elif "<" in evidence_dirs[0] or ">" in evidence_dirs[0]:
        errors.append(
            f"{target} native_evidence_validation_command --evidence-dir must be concrete, "
            f"got {evidence_dirs[0]!r}"
        )
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--evidence-dir",
                evidence_dirs[0],
                command_label="native_evidence_validation_command",
                require_directory_hint=True,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    return errors


def check_xp_validation_command_path(
    target: str,
    flag: str,
    raw_path: str,
    *,
    command_label: str,
    require_directory_hint: bool = False,
    require_json_hint: bool = False,
    require_target_scope: bool = False,
    require_release_scope: bool = False,
    require_target_release_scope: bool = False,
    release_tag: str = "",
) -> list[str]:
    path = raw_path.strip()
    errors: list[str] = []
    if any(char in path for char in "*?"):
        errors.append(f"{target} {command_label} {flag} must not contain wildcards, got {raw_path!r}")
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
        errors.append(f"{target} {command_label} {flag} must be workspace-relative, got {raw_path!r}")
    if any(part == ".." for part in parts):
        errors.append(f"{target} {command_label} {flag} must not traverse directories")
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if not normalized_parts:
        errors.append(f"{target} {command_label} {flag} must not point at the workspace root")
    else:
        reserved_root = normalized_parts[0]
        if reserved_root in RESERVED_WORKSPACE_ROOTS:
            errors.append(
                f"{target} {command_label} {flag} "
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
                f"{target} {command_label} {flag} "
                f"must not contain hidden path segments: {hidden_segments}"
            )
    if require_directory_hint and directory_path_has_file_suffix(path):
        errors.append(f"{target} {command_label} {flag} must be a directory path, got {raw_path!r}")
    if require_json_hint and not path.endswith(".json"):
        errors.append(f"{target} {command_label} {flag} must point to an XP evidence JSON file")
    check_target_scope = require_target_scope or require_target_release_scope
    check_release_scope = require_release_scope or require_target_release_scope
    if check_target_scope and normalized_parts:
        if target not in normalized_parts:
            errors.append(
                f"{target} {command_label} {flag} "
                f"must include target path segment {target!r}, got {raw_path!r}"
            )
    if check_release_scope and normalized_parts:
        if release_tag not in normalized_parts:
            errors.append(
                f"{target} {command_label} {flag} "
                f"must include release_tag path segment {release_tag!r}, got {raw_path!r}"
            )
    return errors


def directory_path_has_file_suffix(raw_path: str) -> bool:
    path = raw_path.strip()
    if not path:
        return False
    leaf = PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name
    leaf = leaf.lower()
    return any(leaf.endswith(suffix) for suffix in FILE_LIKE_DIRECTORY_SUFFIXES)


def check_xp_evidence_summary(target: str, release_tag: str, raw_summary: Any) -> list[str]:
    if not isinstance(raw_summary, dict):
        return [f"{target} xp_evidence_summary must be an object"]
    errors: list[str] = []
    errors.extend(check_exact_object_keys(target, "xp_evidence_summary", raw_summary, XP_EVIDENCE_SUMMARY_KEYS))
    if raw_summary.get("target") != target:
        errors.append(f"{target} xp_evidence_summary target must be {target}")
    if raw_summary.get("release_tag") != release_tag:
        errors.append(f"{target} xp_evidence_summary release_tag must match record release_tag {release_tag}")

    errors.extend(check_xp_host_identity_summary(target, release_tag, raw_summary.get("host_identity")))

    os_data = raw_summary.get("os")
    if not isinstance(os_data, dict):
        errors.append(f"{target} xp_evidence_summary os must be an object")
    else:
        errors.extend(check_exact_object_keys(target, "xp_evidence_summary os", os_data, xp_os_identity_keys(target)))
        target_contract = xp_target_contract(target)
        if os_data.get("name") != "Windows XP":
            errors.append(f"{target} xp_evidence_summary os.name must be Windows XP")
        if os_data.get("architecture") != XP_TARGETS[target]["architecture"]:
            errors.append(f"{target} xp_evidence_summary os.architecture must be {XP_TARGETS[target]['architecture']}")
        service_pack = str(os_data.get("service_pack", ""))
        expected_service_pack = str(target_contract.get("minimum_service_pack", ""))
        if expected_service_pack and expected_service_pack not in service_pack:
            errors.append(
                f"{target} xp_evidence_summary os.service_pack must include "
                f"{expected_service_pack!r}, got {service_pack!r}"
            )
        elif not service_pack.strip():
            errors.append(f"{target} xp_evidence_summary os.service_pack must be set")
        expected_edition = str(target_contract.get("required_edition", ""))
        if expected_edition and os_data.get("edition") != expected_edition:
            errors.append(
                f"{target} xp_evidence_summary os.edition must be "
                f"{expected_edition!r}, got {os_data.get('edition')!r}"
            )

    toolchain = raw_summary.get("toolchain")
    if not isinstance(toolchain, dict):
        errors.append(f"{target} xp_evidence_summary toolchain must be an object")
    else:
        errors.extend(
            check_exact_object_keys(
                target,
                "xp_evidence_summary toolchain",
                toolchain,
                XP_SUMMARY_TOOLCHAIN_KEYS,
            )
        )
        for flag, expected in sorted(REQUIRED_XP_TOOLCHAIN_FLAGS.items()):
            if toolchain.get(flag) is not expected:
                errors.append(f"{target} xp_evidence_summary toolchain.{flag} must be {str(expected).lower()}")

    security = raw_summary.get("security")
    if not isinstance(security, dict):
        errors.append(f"{target} xp_evidence_summary security must be an object")
    else:
        errors.extend(
            check_exact_object_keys(
                target,
                "xp_evidence_summary security",
                security,
                XP_SECURITY_KEYS,
            )
        )
        for flag, expected in sorted(REQUIRED_XP_SECURITY_FLAGS.items()):
            if security.get(flag) is not expected:
                errors.append(f"{target} xp_evidence_summary security.{flag} must be {str(expected).lower()}")
        errors.extend(check_xp_security_patch_evidence(target, security.get("patch_evidence")))

    smoke_ids = raw_summary.get("smoke_ids")
    if not isinstance(smoke_ids, list):
        errors.append(f"{target} xp_evidence_summary smoke_ids must be a list")
    else:
        actual_list: list[str] = []
        for smoke_id in smoke_ids:
            if not isinstance(smoke_id, str):
                errors.append(f"{target} xp_evidence_summary smoke_ids entries must be strings, got {smoke_id!r}")
                continue
            actual_list.append(smoke_id)
        actual = set(actual_list)
        duplicate_smoke_ids = sorted(smoke_id for smoke_id in actual if actual_list.count(smoke_id) > 1)
        if duplicate_smoke_ids:
            errors.append(f"{target} xp_evidence_summary smoke_ids contains duplicates: {duplicate_smoke_ids}")
        case_collisions = case_insensitive_name_collisions(actual)
        if case_collisions:
            errors.append(
                f"{target} xp_evidence_summary smoke_ids must not collide on "
                f"case-insensitive filesystems: {case_collisions}"
            )
        missing = sorted(REQUIRED_XP_SMOKE_IDS - actual)
        unexpected = sorted(actual - REQUIRED_XP_SMOKE_IDS)
        if missing:
            errors.append(f"{target} xp_evidence_summary smoke_ids missing: {missing}")
        if unexpected:
            errors.append(f"{target} xp_evidence_summary smoke_ids unexpected: {unexpected}")
    errors.extend(check_xp_smoke_evidence_files(target, raw_summary.get("smoke_evidence_files")))
    errors.extend(
        check_xp_smoke_commands(
            target,
            release_tag,
            raw_summary.get("smoke_commands"),
            raw_summary.get("smoke_evidence_files"),
            raw_summary.get("host_identity"),
            raw_summary.get("os"),
            raw_summary.get("release_source"),
            raw_summary.get("security"),
        )
    )
    return errors


def check_xp_evidence_summary_release_source(
    target: str,
    raw_summary_source: Any,
    raw_release_asset_source: Any,
) -> list[str]:
    if not isinstance(raw_summary_source, dict):
        return [f"{target} xp_evidence_summary release_source must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "xp_evidence_summary release_source",
            raw_summary_source,
            XP_RELEASE_SOURCE_SUMMARY_KEYS,
        )
    )
    if not isinstance(raw_release_asset_source, dict):
        return errors
    for field in ("workflow", "workflow_run_url", "head_sha"):
        if not isinstance(raw_summary_source.get(field), str):
            errors.append(f"{target} xp_evidence_summary release_source.{field} must be a string")
    summary_run_attempt = raw_summary_source.get("run_attempt")
    if (
        not isinstance(summary_run_attempt, int)
        or isinstance(summary_run_attempt, bool)
        or summary_run_attempt < 1
    ):
        errors.append(f"{target} xp_evidence_summary release_source.run_attempt must be a positive integer")
    for field in ("workflow", "workflow_run_url", "head_sha", "run_attempt"):
        summary_value = raw_summary_source.get(field)
        release_value = raw_release_asset_source.get(field)
        if field == "workflow_run_url":
            summary_value = summary_value.rstrip("/") if isinstance(summary_value, str) else summary_value
            release_value = release_value.rstrip("/") if isinstance(release_value, str) else release_value
        if summary_value != release_value:
            errors.append(
                f"{target} xp_evidence_summary release_source.{field} must match "
                f"release_asset_source.{field}"
            )
    return errors


def check_xp_host_identity_sha256(target: str, raw_digest: Any, raw_identity: Any) -> list[str]:
    if not isinstance(raw_digest, str):
        return [f"{target} xp_host_identity_sha256 must be a string SHA-256 hex digest"]
    digest = raw_digest
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        return [f"{target} xp_host_identity_sha256 must be a SHA-256 hex digest"]
    if isinstance(raw_identity, dict) and contains_non_string_json_object_key(raw_identity):
        return [
            f"{target} xp_evidence_summary host_identity JSON object keys must be strings "
            "for SHA-256 verification"
        ]
    if isinstance(raw_identity, dict) and digest != json_sha256(raw_identity):
        return [f"{target} xp_host_identity_sha256 must match xp_evidence_summary host_identity"]
    return []


def check_xp_host_identity_summary(target: str, release_tag: str, raw_identity: Any) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} xp_evidence_summary host_identity must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "xp_evidence_summary host_identity",
            raw_identity,
            XP_HOST_IDENTITY_KEYS,
        )
    )
    if raw_identity.get("schema_version") != 1 or isinstance(raw_identity.get("schema_version"), bool):
        errors.append(f"{target} xp_evidence_summary host_identity.schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} xp_evidence_summary host_identity.target must be {target}")
    if raw_identity.get("release_tag") != release_tag:
        errors.append(
            f"{target} xp_evidence_summary host_identity.release_tag must match record release_tag {release_tag}"
        )
    forbidden_fields = sorted(
        field
        for field in raw_identity
        if str(field).lower() in FORBIDDEN_HOST_IDENTITY_FIELDS
    )
    if forbidden_fields:
        errors.append(
            f"{target} xp_evidence_summary host_identity contains forbidden private fields: {forbidden_fields}"
        )
    host_label = str(raw_identity.get("host_label", "")).strip()
    host_prefix = xp_host_identity_prefix(target)
    if not HOST_IDENTITY_LABEL_RE.fullmatch(host_label) or not host_label.startswith(host_prefix):
        errors.append(
            f"{target} xp_evidence_summary host_identity.host_label must be a sanitized target-scoped lab label, "
            f"got {host_label!r}"
        )
    evidence_run_id = str(raw_identity.get("evidence_run_id", "")).strip()
    if not HOST_IDENTITY_RUN_RE.fullmatch(evidence_run_id) or not evidence_run_id.startswith(host_prefix):
        errors.append(
            f"{target} xp_evidence_summary host_identity.evidence_run_id must be a sanitized target-scoped run id, "
            f"got {evidence_run_id!r}"
        )
    observed_at = str(raw_identity.get("observed_at_utc", "")).strip()
    if not OBSERVED_AT_UTC_RE.fullmatch(observed_at):
        errors.append(
            f"{target} xp_evidence_summary host_identity.observed_at_utc must be UTC ISO-8601 seconds ending in Z, "
            f"got {observed_at!r}"
        )
    else:
        expected_run_marker = xp_host_identity_run_marker(release_tag, observed_at)
        if expected_run_marker not in evidence_run_id:
            errors.append(
                f"{target} xp_evidence_summary host_identity.evidence_run_id must include "
                f"release/observed-at marker {expected_run_marker!r}, got {evidence_run_id!r}"
            )
    if raw_identity.get("operator_private_data_redacted") is not True:
        errors.append(f"{target} xp_evidence_summary host_identity.operator_private_data_redacted must be true")

    identity_os = raw_identity.get("os")
    if not isinstance(identity_os, dict):
        errors.append(f"{target} xp_evidence_summary host_identity.os must be an object")
    else:
        errors.extend(
            check_exact_object_keys(
                target,
                "xp_evidence_summary host_identity.os",
                identity_os,
                xp_os_identity_keys(target),
            )
        )
        target_contract = xp_target_contract(target)
        if identity_os.get("name") != "Windows XP":
            errors.append(f"{target} xp_evidence_summary host_identity.os.name must be Windows XP")
        if identity_os.get("architecture") != XP_TARGETS[target]["architecture"]:
            errors.append(
                f"{target} xp_evidence_summary host_identity.os.architecture must be "
                f"{XP_TARGETS[target]['architecture']}"
            )
        service_pack = str(identity_os.get("service_pack", ""))
        expected_service_pack = str(target_contract.get("minimum_service_pack", ""))
        if expected_service_pack and expected_service_pack not in service_pack:
            errors.append(
                f"{target} xp_evidence_summary host_identity.os.service_pack must include "
                f"{expected_service_pack!r}, got {service_pack!r}"
            )
        expected_edition = str(target_contract.get("required_edition", ""))
        if expected_edition and identity_os.get("edition") != expected_edition:
            errors.append(
                f"{target} xp_evidence_summary host_identity.os.edition must be "
                f"{expected_edition!r}, got {identity_os.get('edition')!r}"
            )

    identity_toolchain = raw_identity.get("toolchain")
    if not isinstance(identity_toolchain, dict):
        errors.append(f"{target} xp_evidence_summary host_identity.toolchain must be an object")
    else:
        errors.extend(
            check_exact_object_keys(
                target,
                "xp_evidence_summary host_identity.toolchain",
                identity_toolchain,
                XP_HOST_TOOLCHAIN_KEYS,
            )
        )
        for flag, expected in sorted(REQUIRED_XP_TOOLCHAIN_FLAGS.items()):
            if identity_toolchain.get(flag) is not expected:
                errors.append(
                    f"{target} xp_evidence_summary host_identity.toolchain.{flag} "
                    f"must be {str(expected).lower()}"
                )
        description = str(identity_toolchain.get("description", ""))
        if len(description.strip()) < 12:
            errors.append(
                f"{target} xp_evidence_summary host_identity.toolchain.description "
                "must describe the XP-capable toolchain"
            )
    return errors


def xp_os_identity_keys(target: str) -> set[str]:
    keys = set(XP_OS_BASE_KEYS)
    if str(xp_target_contract(target).get("required_edition", "")).strip():
        keys.add("edition")
    return keys


def check_xp_security_patch_evidence(target: str, raw_evidence: Any) -> list[str]:
    errors = check_security_patch_evidence(
        target,
        raw_evidence,
        prefix="xp_evidence_summary security.patch_evidence",
    )
    if not isinstance(raw_evidence, dict):
        return errors
    errors.extend(
        check_exact_object_keys(
            target,
            "xp_evidence_summary security.patch_evidence",
            raw_evidence,
            XP_SECURITY_PATCH_EVIDENCE_KEYS,
        )
    )
    return errors


def xp_host_identity_prefix(target: str) -> str:
    if target in XP_TARGETS:
        return f"xp-{XP_TARGETS[target]['architecture']}-"
    return f"{target}-"


def xp_host_identity_run_marker(release_tag: str, observed_at_utc: str) -> str:
    version = release_tag.removeprefix("v").replace(".", "-")
    observed_marker = observed_at_utc.replace("-", "").replace(":", "").replace("T", "t").removesuffix("Z")
    return f"{version}-{observed_marker}z"


def check_xp_smoke_evidence_files(target: str, raw_files: Any) -> list[str]:
    if not isinstance(raw_files, dict):
        return [f"{target} xp_evidence_summary smoke_evidence_files must be an object"]
    errors: list[str] = []
    files: dict[str, str] = {}
    for name, value in raw_files.items():
        if not isinstance(name, str):
            errors.append(
                f"{target} xp_evidence_summary smoke_evidence_files smoke ids must be strings, got {name!r}"
            )
            continue
        if not isinstance(value, str):
            errors.append(
                f"{target} xp_evidence_summary smoke_evidence_files {name} "
                f"must be a string path, got {value!r}"
            )
            continue
        files[name] = value.strip()
    case_collisions = case_insensitive_name_collisions(set(files))
    if case_collisions:
        errors.append(
            f"{target} xp_evidence_summary smoke_evidence_files smoke ids must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing = sorted(REQUIRED_XP_SMOKE_IDS - set(files))
    if missing:
        errors.append(f"{target} xp_evidence_summary smoke_evidence_files missing smoke ids: {missing}")
    unexpected = sorted(set(files) - REQUIRED_XP_SMOKE_IDS)
    if unexpected:
        errors.append(f"{target} xp_evidence_summary smoke_evidence_files unexpected smoke ids: {unexpected}")
    seen_files: dict[str, list[str]] = {}
    for smoke_id, filename in sorted(files.items()):
        if smoke_id not in REQUIRED_XP_SMOKE_IDS:
            continue
        if not filename:
            errors.append(f"{target} xp_evidence_summary smoke_evidence_files {smoke_id} must be set")
            continue
        expected_file = f"xp-smoke-evidence/{smoke_id}.txt"
        if filename != expected_file:
            errors.append(
                f"{target} xp_evidence_summary smoke_evidence_files {smoke_id} "
                f"must be {expected_file}, got {filename!r}"
            )
        if "<" in filename or ">" in filename:
            errors.append(
                f"{target} xp_evidence_summary smoke_evidence_files {smoke_id} must be concrete, got {filename!r}"
            )
        path = Path(filename)
        if path.is_absolute():
            errors.append(f"{target} xp_evidence_summary smoke_evidence_files {smoke_id} must be relative")
        if ".." in path.parts:
            errors.append(f"{target} xp_evidence_summary smoke_evidence_files {smoke_id} must not traverse directories")
        seen_files.setdefault(filename, []).append(smoke_id)
    duplicates = {
        filename: sorted(smoke_ids)
        for filename, smoke_ids in seen_files.items()
        if len(smoke_ids) > 1
    }
    if duplicates:
        errors.append(f"{target} xp_evidence_summary smoke_evidence_files duplicate file bindings: {duplicates}")
    return errors


def check_xp_smoke_commands(
    target: str,
    release_tag: str,
    raw_commands: Any,
    raw_files: Any,
    raw_host_identity: Any,
    raw_os_identity: Any,
    raw_release_source: Any,
    raw_security: Any,
) -> list[str]:
    if not isinstance(raw_commands, dict):
        return [f"{target} xp_evidence_summary smoke_commands must be an object"]
    errors: list[str] = []
    commands: dict[str, str] = {}
    for name, value in raw_commands.items():
        if not isinstance(name, str):
            errors.append(f"{target} xp_evidence_summary smoke_commands smoke ids must be strings, got {name!r}")
            continue
        if not isinstance(value, str):
            errors.append(
                f"{target} xp_evidence_summary smoke_commands {name} must be a string command, got {value!r}"
            )
            continue
        commands[name] = value.strip()
    case_collisions = case_insensitive_name_collisions(set(commands))
    if case_collisions:
        errors.append(
            f"{target} xp_evidence_summary smoke_commands smoke ids must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    evidence_files = (
        {name: value.strip() for name, value in raw_files.items() if isinstance(name, str) and isinstance(value, str)}
        if isinstance(raw_files, dict)
        else {}
    )
    missing = sorted(REQUIRED_XP_SMOKE_IDS - set(commands))
    if missing:
        errors.append(f"{target} xp_evidence_summary smoke_commands missing smoke ids: {missing}")
    unexpected = sorted(set(commands) - REQUIRED_XP_SMOKE_IDS)
    if unexpected:
        errors.append(f"{target} xp_evidence_summary smoke_commands unexpected smoke ids: {unexpected}")
    for smoke_id, command in sorted(commands.items()):
        if smoke_id not in REQUIRED_XP_SMOKE_IDS:
            continue
        if not command:
            errors.append(f"{target} xp_evidence_summary smoke_commands {smoke_id} must be set")
        elif "<" in command or ">" in command:
            errors.append(
                f"{target} xp_evidence_summary smoke_commands {smoke_id} must be concrete, got {command!r}"
            )
        elif not command.startswith(f"{REQUIRED_XP_SMOKE_COMMAND_PREFIX} "):
            errors.append(
                f"{target} xp_evidence_summary smoke_commands {smoke_id} "
                f"must start with {REQUIRED_XP_SMOKE_COMMAND_PREFIX!r}, got {command!r}"
            )
        else:
            errors.extend(
                check_xp_smoke_command_binding(
                    target,
                    release_tag,
                    smoke_id,
                    command,
                    evidence_file=evidence_files.get(smoke_id),
                    host_identity=raw_host_identity,
                    os_identity=raw_os_identity,
                    release_source=raw_release_source,
                    security=raw_security,
                )
            )
    return errors


def check_xp_smoke_command_binding(
    target: str,
    release_tag: str,
    smoke_id: str,
    command: str,
    *,
    evidence_file: str | None = None,
    host_identity: Any,
    os_identity: Any,
    release_source: Any,
    security: Any,
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
        raw_workflow_run_url = release_source.get("workflow_run_url", "")
        expected_values["--source-workflow-run-url"] = (
            raw_workflow_run_url.strip().rstrip("/")
            if isinstance(raw_workflow_run_url, str)
            else ""
        )
        raw_head_sha = release_source.get("head_sha", "")
        expected_values["--source-head-sha"] = raw_head_sha if isinstance(raw_head_sha, str) else ""
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
            errors.append(
                f"{target} xp_evidence_summary smoke_commands {smoke_id} "
                f"must include exactly one {flag} {expected}, got {values}"
            )
    if isinstance(os_identity, dict) and not str(os_identity.get("edition", "")).strip():
        edition_values = command_flag_values(command, "--os-edition")
        if edition_values:
            errors.append(
                f"{target} xp_evidence_summary smoke_commands {smoke_id} "
                f"must omit --os-edition for this target, got {edition_values}"
            )
    if smoke_id in {"legacy_crypto_profile_scoped", "modern_defaults_unchanged"}:
        patch_evidence = security.get("patch_evidence") if isinstance(security, dict) else None
        if isinstance(patch_evidence, dict):
            security_command_flags = {
                "--security-update-channel": "security_update_channel",
                "--cve-review-reference": "cve_review_reference",
            }
            for flag, field in security_command_flags.items():
                expected = str(patch_evidence.get(field, "")).strip()
                if expected:
                    values = command_flag_values(command, flag)
                    if values != [expected]:
                        errors.append(
                            f"{target} xp_evidence_summary smoke_commands {smoke_id} "
                            f"must include exactly one {flag} {expected}, got {values}"
                        )
    return errors


def command_flag_values(command: str, flag: str) -> list[str]:
    pattern = rf'(?:^|\s){re.escape(flag)}\s+(?:"([^"]+)"|(\S+))(?=\s|$)'
    return [quoted or bare for quoted, bare in re.findall(pattern, command)]


def check_security_patch_evidence(
    target: str,
    raw_evidence: Any,
    *,
    prefix: str = "builder_identity security_patch_evidence",
) -> list[str]:
    if not isinstance(raw_evidence, dict):
        return [f"{target} {prefix} must be an object"]
    errors: list[str] = []
    for key, expected in sorted(REQUIRED_SECURITY_PATCH_EVIDENCE.items()):
        if raw_evidence.get(key) != expected:
            errors.append(f"{target} {prefix}.{key} must be {expected!r}")
    for key in REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS:
        value = str(raw_evidence.get(key, ""))
        if not value.strip():
            errors.append(f"{target} {prefix}.{key} must be set")
        elif not is_concrete_security_provenance(value, key):
            errors.append(f"{target} {prefix}.{key} must name concrete non-placeholder provenance")
    return errors


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


def check_linux_security_patch_evidence(target: str, raw_evidence: Any) -> list[str]:
    errors = check_security_patch_evidence(target, raw_evidence)
    if not isinstance(raw_evidence, dict):
        return errors
    errors.extend(
        check_exact_object_keys(
            target,
            "builder_identity security_patch_evidence",
            raw_evidence,
            LINUX_SECURITY_PATCH_EVIDENCE_KEYS,
        )
    )
    for key in ("python_ssl_openssl", "openssl_cli_version"):
        if not str(raw_evidence.get(key, "")).strip():
            errors.append(f"{target} builder_identity security_patch_evidence.{key} must be set")
    return errors


def check_xp_smoke_evidence_hashes(target: str, raw_hashes: Any) -> list[str]:
    if not isinstance(raw_hashes, dict):
        return [f"{target} xp_smoke_evidence_sha256 must be an object"]
    errors: list[str] = []
    hashes: dict[str, str] = {}
    for name, value in raw_hashes.items():
        if not isinstance(name, str):
            errors.append(f"{target} xp_smoke_evidence_sha256 smoke ids must be strings, got {name!r}")
            continue
        if not isinstance(value, str):
            errors.append(f"{target} xp_smoke_evidence_sha256 for {name} must be a string SHA-256 hex digest")
            continue
        hashes[name] = str(value)
    case_collisions = case_insensitive_name_collisions(set(hashes))
    if case_collisions:
        errors.append(
            f"{target} xp_smoke_evidence_sha256 smoke ids must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing = sorted(REQUIRED_XP_SMOKE_IDS - set(hashes))
    if missing:
        errors.append(f"{target} xp_smoke_evidence_sha256 missing smoke ids: {missing}")
    unexpected = sorted(set(hashes) - REQUIRED_XP_SMOKE_IDS)
    if unexpected:
        errors.append(f"{target} xp_smoke_evidence_sha256 has unexpected smoke ids: {unexpected}")
    for smoke_id, digest in sorted(hashes.items()):
        if smoke_id in REQUIRED_XP_SMOKE_IDS and not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{target} xp_smoke_evidence_sha256 for {smoke_id} must be a SHA-256 hex digest")
    return errors


def check_linux_smoke_evidence_hashes(target: str, raw_hashes: Any) -> list[str]:
    if not isinstance(raw_hashes, dict):
        return [f"{target} linux_smoke_evidence_sha256 must be an object"]
    errors: list[str] = []
    hashes: dict[str, str] = {}
    for name, value in raw_hashes.items():
        if not isinstance(name, str):
            errors.append(f"{target} linux_smoke_evidence_sha256 smoke ids must be strings, got {name!r}")
            continue
        if not isinstance(value, str):
            errors.append(f"{target} linux_smoke_evidence_sha256 for {name} must be a string SHA-256 hex digest")
            continue
        hashes[name] = str(value)
    case_collisions = case_insensitive_name_collisions(set(hashes))
    if case_collisions:
        errors.append(
            f"{target} linux_smoke_evidence_sha256 smoke ids must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing = sorted(REQUIRED_LINUX_SMOKE_IDS - set(hashes))
    if missing:
        errors.append(f"{target} linux_smoke_evidence_sha256 missing smoke ids: {missing}")
    unexpected = sorted(set(hashes) - REQUIRED_LINUX_SMOKE_IDS)
    if unexpected:
        errors.append(f"{target} linux_smoke_evidence_sha256 has unexpected smoke ids: {unexpected}")
    for smoke_id, digest in sorted(hashes.items()):
        if smoke_id in REQUIRED_LINUX_SMOKE_IDS and not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{target} linux_smoke_evidence_sha256 for {smoke_id} must be a SHA-256 hex digest")
    return errors


def check_linux_smoke_log_text(
    target: str,
    release_tag: str,
    native_smoke_command: str,
    workflow_run_url: str,
    text: str,
    *,
    workflow_run_attempt: int,
    source_head_sha: str,
    label: str = "linux_smoke_evidence",
    artifact_sha256: Any | None = None,
) -> list[str]:
    arch = REQUIRED_LINUX_SMOKE_ARCHES.get(target, "")
    source_head_sha = source_head_sha.strip()
    workflow_run_attempt_text = str(workflow_run_attempt)
    expected_dpkg_arches = REQUIRED_LINUX_DPKG_ARCHES.get(target, set())
    expected_userland_bits = REQUIRED_LINUX_USERLAND_BITS.get(target, "")
    expected_machines = LINUX_TARGETS.get(target, {}).get("machine_names", set())
    expected_host_label = f"{target}-builder"
    expected_evidence_run_id = linux_smoke_evidence_run_id(target, release_tag, workflow_run_url)
    expected_command = (
        f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
        f"--target {target} --workflow-run-url {workflow_run_url} "
        f"--workflow-run-attempt {workflow_run_attempt_text} --source-head-sha {source_head_sha}"
    )
    builder_evidence_paths = command_flag_values(native_smoke_command, "--builder-evidence")
    builder_evidence_path = builder_evidence_paths[0] if len(builder_evidence_paths) == 1 else "<builder-evidence>"
    expected_command = f"{expected_command} --builder-evidence {builder_evidence_path}"
    required_lines = [
        f"native installer smoke command: {expected_command}",
        f"native installer smoke release: {release_tag}",
        f"native installer smoke target arch: {arch}",
        f"native installer smoke target: {target}",
        f"native installer smoke workflow run: {workflow_run_url}",
        f"native installer smoke workflow run attempt: {workflow_run_attempt_text}",
        f"native installer smoke source head sha: {source_head_sha}",
        f"native installer smoke git head sha: {source_head_sha}",
        f"native installer smoke userland bits: {expected_userland_bits}",
        *REQUIRED_LINUX_SECURITY_SMOKE_LINES,
        *[f"native installer smoke: {step}" for step in REQUIRED_LINUX_SMOKE_STEPS],
        f"native installer smoke passed for Linux {arch}",
    ]
    errors: list[str] = []
    if not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{target} {label} source head SHA must be a 40-character lowercase Git SHA")
    if not isinstance(workflow_run_attempt, int) or isinstance(workflow_run_attempt, bool) or workflow_run_attempt < 1:
        errors.append(f"{target} {label} workflow run attempt must be a positive integer")
    if native_smoke_command != expected_command:
        errors.append(f"{target} {label} command provenance must be {expected_command!r}")
    if len(builder_evidence_paths) != 1:
        errors.append(
            f"{target} {label} command provenance must include exactly one "
            f"--builder-evidence, got {builder_evidence_paths}"
        )
    if not text.strip():
        return [*errors, f"{target} {label} must not be empty"]
    errors.extend(check_required_linux_smoke_exact_lines(target, label, text, required_lines))
    errors.extend(
        check_linux_smoke_runtime_line(
            target,
            label,
            text,
            "native installer smoke uname machine",
            expected_machines,
        )
    )
    errors.extend(
        check_linux_smoke_runtime_line(
            target,
            label,
            text,
            "native installer smoke dpkg architecture",
            expected_dpkg_arches,
        )
    )
    errors.extend(
        check_linux_smoke_identity_line(
            target,
            label,
            text,
            "native installer smoke host label",
            expected_host_label,
        )
    )
    errors.extend(
        check_linux_smoke_identity_line(
            target,
            label,
            text,
            "native installer smoke evidence run id",
            expected_evidence_run_id,
        )
    )
    errors.extend(check_linux_smoke_observed_at_line(target, label, text))
    errors.extend(check_linux_smoke_runtime_identity_lines(target, label, text))
    errors.extend(check_linux_smoke_security_value_lines(target, label, text))
    errors.extend(check_forbidden_linux_smoke_security_lines(target, label, text))
    if artifact_sha256 is not None:
        errors.extend(check_linux_smoke_artifact_sha256_lines(target, release_tag, text, artifact_sha256, label=label))
    return errors


def check_required_linux_smoke_exact_lines(
    target: str,
    label: str,
    text: str,
    required_lines: list[str],
) -> list[str]:
    lines = text.splitlines()
    errors: list[str] = []
    for required_line in required_lines:
        count = sum(1 for line in lines if line == required_line)
        if count == 0:
            errors.append(f"{target} {label} missing required line: {required_line}")
        elif count != 1:
            errors.append(
                f"{target} {label} must include exactly one required line: "
                f"{required_line} (got {count})"
            )
    return errors


def linux_smoke_evidence_run_id(target: str, release_tag: str, workflow_run_url: str) -> str:
    version = release_tag.removeprefix("v").replace(".", "-")
    match = GITHUB_ACTIONS_RUN_ID_RE.search(workflow_run_url)
    run_id = match.group(1) if match else ""
    return f"{target}-{version}-run-{run_id}"


def check_linux_smoke_identity_line(
    target: str,
    label: str,
    text: str,
    key: str,
    expected_value: str,
) -> list[str]:
    values = linux_smoke_line_values(text, key)
    if not values:
        return [f"{target} {label} missing required line: {key}: {expected_value}"]
    if len(values) != 1:
        return [f"{target} {label} must include exactly one {key} value, got {values}"]
    if values[0] != expected_value:
        return [f"{target} {label} {key} must be {expected_value!r}, got {values[0]!r}"]
    return []


def check_linux_smoke_observed_at_line(target: str, label: str, text: str) -> list[str]:
    key = "native installer smoke observed at utc"
    values = linux_smoke_line_values(text, key)
    if not values:
        return [f"{target} {label} missing required line: {key}: <UTC ISO-8601 seconds ending in Z>"]
    if len(values) != 1:
        return [f"{target} {label} must include exactly one {key} value, got {values}"]
    value = values[0]
    if not OBSERVED_AT_UTC_RE.fullmatch(value):
        return [
            f"{target} {label} {key} must be UTC ISO-8601 seconds ending in Z, got {value!r}"
        ]
    return []


def check_linux_smoke_runtime_identity_lines(target: str, label: str, text: str) -> list[str]:
    errors: list[str] = []
    for key in (
        "native installer smoke os release",
        "native installer smoke kernel release",
        "native installer smoke glibc version",
    ):
        values = linux_smoke_line_values(text, key)
        if not values:
            errors.append(f"{target} {label} missing required line: {key}: <runtime value>")
        elif len(values) != 1:
            errors.append(f"{target} {label} must include exactly one {key} value, got {values}")
        elif not values[0].strip():
            errors.append(f"{target} {label} {key} must not be empty")
    return errors


def linux_smoke_line_values(text: str, key: str) -> list[str]:
    prefix = f"{key}: "
    return [
        line.removeprefix(prefix).strip()
        for line in text.splitlines()
        if line.startswith(prefix)
    ]


def observed_at_utc_datetime(value: str) -> datetime | None:
    if not OBSERVED_AT_UTC_RE.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def check_linux_smoke_builder_identity_binding(
    target: str,
    label: str,
    text: str,
    raw_builder_identity: Any,
) -> list[str]:
    if not isinstance(raw_builder_identity, dict):
        return [f"{target} {label} builder/smoke host identity binding requires builder_identity object"]
    raw_host_identity = raw_builder_identity.get("host_identity")
    if not isinstance(raw_host_identity, dict):
        return [f"{target} {label} builder/smoke host identity binding requires builder_identity.host_identity object"]

    errors: list[str] = []
    expected_host_label = str(raw_host_identity.get("host_label", "")).strip()
    expected_run_id = str(raw_host_identity.get("evidence_run_id", "")).strip()
    expected_observed_at = str(raw_host_identity.get("observed_at_utc", "")).strip()

    smoke_host_labels = linux_smoke_line_values(text, "native installer smoke host label")
    if expected_host_label and len(smoke_host_labels) == 1 and smoke_host_labels[0] != expected_host_label:
        errors.append(
            f"{target} {label} native installer smoke host label must match "
            f"builder_identity.host_identity.host_label {expected_host_label!r}, got {smoke_host_labels[0]!r}"
        )
    elif not expected_host_label:
        errors.append(f"{target} {label} builder_identity.host_identity.host_label must be set for smoke binding")

    smoke_run_ids = linux_smoke_line_values(text, "native installer smoke evidence run id")
    if expected_run_id and len(smoke_run_ids) == 1 and smoke_run_ids[0] != expected_run_id:
        errors.append(
            f"{target} {label} native installer smoke evidence run id must match "
            f"builder_identity.host_identity.evidence_run_id {expected_run_id!r}, got {smoke_run_ids[0]!r}"
        )
    elif not expected_run_id:
        errors.append(
            f"{target} {label} builder_identity.host_identity.evidence_run_id must be set for smoke binding"
        )

    smoke_observed_values = linux_smoke_line_values(text, "native installer smoke observed at utc")
    builder_observed_at = observed_at_utc_datetime(expected_observed_at)
    smoke_observed_at = (
        observed_at_utc_datetime(smoke_observed_values[0])
        if len(smoke_observed_values) == 1
        else None
    )
    if not expected_observed_at:
        errors.append(
            f"{target} {label} builder_identity.host_identity.observed_at_utc must be set for smoke binding"
        )
    elif builder_observed_at is not None and smoke_observed_at is not None and smoke_observed_at < builder_observed_at:
        errors.append(
            f"{target} {label} native installer smoke observed at utc must not be earlier than "
            f"builder_identity.host_identity.observed_at_utc {expected_observed_at!r}, got {smoke_observed_values[0]!r}"
        )

    runtime_bindings = {
        "native installer smoke os release": "os_release",
        "native installer smoke kernel release": "kernel_release",
        "native installer smoke glibc version": "glibc_version",
    }
    for smoke_key, builder_key in runtime_bindings.items():
        expected_runtime_value = str(raw_builder_identity.get(builder_key, "")).strip()
        smoke_values = linux_smoke_line_values(text, smoke_key)
        if not expected_runtime_value:
            errors.append(f"{target} {label} builder_identity.{builder_key} must be set for smoke binding")
        elif len(smoke_values) == 1 and smoke_values[0] != expected_runtime_value:
            errors.append(
                f"{target} {label} {smoke_key} must match "
                f"builder_identity.{builder_key} {expected_runtime_value!r}, got {smoke_values[0]!r}"
            )

    raw_security = raw_builder_identity.get("security_patch_evidence")
    if not isinstance(raw_security, dict):
        errors.append(
            f"{target} {label} builder_identity.security_patch_evidence must be an object for smoke binding"
        )
    else:
        security_bindings = {
            "native installer smoke python ssl openssl": "python_ssl_openssl",
            "native installer smoke openssl cli version": "openssl_cli_version",
            "native installer smoke security update channel": "security_update_channel",
            "native installer smoke CVE review reference": "cve_review_reference",
        }
        for smoke_key, builder_key in security_bindings.items():
            expected_security_value = str(raw_security.get(builder_key, "")).strip()
            smoke_values = linux_smoke_line_values(text, smoke_key)
            if not expected_security_value:
                errors.append(
                    f"{target} {label} builder_identity.security_patch_evidence.{builder_key} "
                    "must be set for smoke binding"
                )
            elif len(smoke_values) == 1 and smoke_values[0] != expected_security_value:
                errors.append(
                    f"{target} {label} {smoke_key} must match "
                    f"builder_identity.security_patch_evidence.{builder_key} "
                    f"{expected_security_value!r}, got {smoke_values[0]!r}"
                )

    return errors


def check_linux_smoke_security_value_lines(target: str, label: str, text: str) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_LINUX_SECURITY_SMOKE_VALUE_LINES:
        prefix = f"{key}: "
        values = [
            line.removeprefix(prefix).strip()
            for line in text.splitlines()
            if line.startswith(prefix)
        ]
        if not values:
            errors.append(f"{target} {label} missing required line: {key}: <expected security value>")
            continue
        if len(values) != 1:
            errors.append(f"{target} {label} must include exactly one {key} value, got {values}")
            continue
        value = values[0]
        if not value or "<" in value or ">" in value:
            errors.append(f"{target} {label} {key} must be concrete, got {value!r}")
    return errors


def check_forbidden_linux_smoke_security_lines(target: str, label: str, text: str) -> list[str]:
    errors: list[str] = []
    normalized_text = text.lower()
    for line in FORBIDDEN_LINUX_SECURITY_SMOKE_LINES:
        if line.lower() in normalized_text:
            errors.append(f"{target} {label} contains forbidden security proof line: {line}")
    return errors


def check_linux_smoke_runtime_line(
    target: str,
    label: str,
    text: str,
    key: str,
    expected_values: set[str],
) -> list[str]:
    prefix = f"{key}: "
    values = sorted(
        {
            line.removeprefix(prefix).strip().lower()
            for line in text.splitlines()
            if line.startswith(prefix)
        }
    )
    if values == []:
        return [f"{target} {label} missing required line: {key}: <expected runtime value>"]
    if len(values) != 1:
        return [f"{target} {label} must include exactly one {key} value, got {values}"]
    value = values[0]
    if value not in expected_values:
        return [
            f"{target} {label} {key} must be one of {sorted(expected_values)}, got {value!r}"
        ]
    return []


def check_linux_smoke_artifact_sha256_lines(
    target: str,
    release_tag: str,
    text: str,
    raw_artifact_sha256: Any,
    *,
    label: str,
) -> list[str]:
    if not isinstance(raw_artifact_sha256, dict):
        return [f"{target} {label} artifact SHA-256 binding requires artifact_sha256 map"]
    expected_names = linux_smoke_artifact_names(target, release_tag)
    errors: list[str] = []
    expected_hashes: dict[str, str] = {}
    for name in expected_names:
        raw_digest = raw_artifact_sha256.get(name)
        if raw_digest is None:
            errors.append(f"{target} {label} artifact_sha256 for smoke-tested artifact {name} must be set")
            continue
        if not isinstance(raw_digest, str):
            errors.append(
                f"{target} {label} artifact_sha256 for smoke-tested artifact {name} "
                "must be a string SHA-256 hex digest"
            )
            continue
        expected_hashes[name] = raw_digest
    observed: dict[str, list[str]] = {}
    prefix = "native installer smoke artifact sha256: "
    for line in text.splitlines():
        if not line.startswith(prefix):
            continue
        parts = line.removeprefix(prefix).split()
        if len(parts) != 2:
            errors.append(f"{target} {label} malformed artifact SHA-256 line: {line}")
            continue
        filename, digest = parts
        observed.setdefault(filename, []).append(digest)
    unexpected = sorted(set(observed) - expected_names)
    if unexpected:
        errors.append(f"{target} {label} has unexpected artifact SHA-256 lines: {unexpected}")
    duplicates = sorted(name for name, digests in observed.items() if len(digests) > 1)
    if duplicates:
        errors.append(f"{target} {label} has duplicate artifact SHA-256 lines: {duplicates}")
    for filename, digest in sorted(expected_hashes.items()):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(
                f"{target} {label} artifact_sha256 for smoke-tested artifact {filename} "
                "must be a SHA-256 hex digest"
            )
            continue
        expected_line = f"{prefix}{filename} {digest}"
        if expected_line not in text:
            errors.append(f"{target} {label} missing required line: {expected_line}")
    return errors


def linux_smoke_artifact_names(target: str, release_tag: str) -> set[str]:
    version = release_tag.removeprefix("v")
    return {template.format(version=version) for template in REQUIRED_LINUX_SMOKE_ARTIFACT_TEMPLATES.get(target, ())}


def check_common_evidence(
    entry: dict[str, Any],
    target: str,
    required_checks: set[str],
    promotion_entries: dict[str, dict[str, Any]],
    promotion_hash: str,
    *,
    require_review_bundle: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_evidence_record_keys(target, entry, require_review_bundle=require_review_bundle))
    if entry.get("status") != "accepted":
        errors.append(f"{target} evidence status must be accepted")
    if entry.get("readiness_percent") != 100.0:
        errors.append(f"{target} evidence readiness_percent must be 100.0")
    raw_release_tag = entry.get("release_tag", "")
    release_tag = raw_release_tag if isinstance(raw_release_tag, str) else ""
    if not isinstance(raw_release_tag, str):
        errors.append(f"{target} release_tag must be a string")
    elif not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
        errors.append(f"{target} release_tag must look like vX.Y.Z")
    errors.extend(check_evidence_checks(target, entry.get("checks"), required_checks))
    raw_command = entry.get("artifact_validation_command", "")
    command = raw_command if isinstance(raw_command, str) else ""
    if not isinstance(raw_command, str):
        errors.append(f"{target} artifact_validation_command must be a string command, got {raw_command!r}")
    errors.extend(check_artifact_validation_command(target, release_tag, command))
    errors.extend(check_local_evidence_preflight_command(target, release_tag, entry))
    errors.extend(check_staged_upload_command(target, release_tag, entry))
    raw_promotion_config_sha = entry.get("promotion_config_sha256", "")
    promotion_config_sha = raw_promotion_config_sha if isinstance(raw_promotion_config_sha, str) else ""
    if not isinstance(raw_promotion_config_sha, str):
        errors.append(f"{target} promotion_config_sha256 must be a string SHA-256 hex digest")
    elif not re.fullmatch(r"[0-9a-f]{64}", promotion_config_sha):
        errors.append(f"{target} promotion_config_sha256 must be a SHA-256 hex digest")
    elif promotion_config_sha != promotion_hash:
        errors.append(f"{target} promotion_config_sha256 must match current promotion config SHA-256")
    expected_artifact_names = accepted_artifact_names(target, release_tag, promotion_entries)
    errors.extend(check_artifact_sha256(target, entry.get("artifact_sha256"), expected_artifact_names))
    release_assets = entry.get("release_asset_urls")
    if not isinstance(release_assets, list) or not release_assets:
        errors.append(f"{target} evidence must include release_asset_urls")
    else:
        actual_names: set[str] = set()
        asset_name_counts: dict[str, int] = {}
        release_repositories: set[str] = set()
        for url in release_assets:
            if not isinstance(url, str):
                errors.append(f"{target} release asset URL entries must be strings, got {url!r}")
                continue
            url_text = url
            match = GITHUB_RELEASE_ASSET_RE.fullmatch(url_text)
            if not match:
                errors.append(f"{target} release asset URL is not a GitHub release asset URL: {url_text}")
                continue
            release_repositories.add(match.group(1))
            url_release_tag = match.group(2)
            if url_release_tag != release_tag:
                errors.append(
                    f"{target} release asset URL tag must match release_tag {release_tag}: {url_text}"
                )
                continue
            filename = release_asset_url_filename(url_text)
            if not filename:
                errors.append(
                    f"{target} release asset URL file name must be an exact safe file name: {url_text}"
                )
                continue
            actual_names.add(filename)
            asset_name_counts[filename] = asset_name_counts.get(filename, 0) + 1
        if len(release_repositories) > 1:
            errors.append(
                f"{target} release asset URLs must use one GitHub repository, got {sorted(release_repositories)}"
            )
        duplicate_assets = sorted(name for name, count in asset_name_counts.items() if count > 1)
        if duplicate_assets:
            errors.append(f"{target} release asset URLs contain duplicate files: {duplicate_assets}")
        case_collisions = case_insensitive_name_collisions(actual_names)
        if case_collisions:
            errors.append(
                f"{target} release asset URL file names must not collide on case-insensitive filesystems: "
                f"{case_collisions}"
            )
        unexpected_assets = sorted(actual_names - expected_artifact_names)
        if unexpected_assets:
            errors.append(f"{target} release asset URLs reference unexpected files: {unexpected_assets}")
        missing_assets = sorted(expected_artifact_names - actual_names)
        if missing_assets:
            errors.append(f"{target} evidence missing release asset URLs for: {missing_assets}")
    review_bundle_files = set(review_bundle_expected_files(target, release_tag).values())
    expected_source_files = set(expected_artifact_names)
    has_review_bundle = isinstance(entry.get("review_bundle"), dict)
    has_finalized_record_url = "finalized_record_release_asset_url" in entry
    if require_review_bundle or has_review_bundle or has_finalized_record_url:
        expected_source_files.update(review_bundle_files)
        expected_source_files.add(accepted_record_source_file(target))
        errors.extend(check_finalized_record_release_asset_url(target, release_tag, entry))
        errors.extend(
            check_review_bundle(
                target,
                release_tag,
                entry.get("review_bundle"),
                entry.get("release_asset_urls"),
            )
        )
    errors.extend(
        check_release_asset_source(
            target,
            release_tag,
            entry.get("release_asset_source"),
            expected_files=expected_source_files,
            allowed_files=expected_source_files,
            native_release_assets=release_package_asset_urls(entry),
        )
    )
    return errors


def check_evidence_checks(
    target: str,
    raw_checks: Any,
    required_checks: set[str],
) -> list[str]:
    if not isinstance(raw_checks, list):
        return [f"{target} evidence checks must be a list"]
    errors: list[str] = []
    checks: list[str] = []
    for check in raw_checks:
        if not isinstance(check, str):
            errors.append(f"{target} evidence checks entries must be strings, got {check!r}")
            continue
        checks.append(check)
    check_counts: dict[str, int] = {}
    for check in checks:
        check_counts[check] = check_counts.get(check, 0) + 1
    actual = set(checks)
    case_collisions = case_insensitive_name_collisions(actual)
    if case_collisions:
        errors.append(
            f"{target} evidence checks must not collide on case-insensitive filesystems: {case_collisions}"
        )
    missing_checks = sorted(required_checks - actual)
    if missing_checks:
        errors.append(f"{target} evidence missing required checks: {missing_checks}")
    unexpected_checks = sorted(actual - required_checks)
    if unexpected_checks:
        errors.append(f"{target} evidence has unexpected checks: {unexpected_checks}")
    duplicate_checks = sorted(check for check, count in check_counts.items() if count > 1)
    if duplicate_checks:
        errors.append(f"{target} evidence has duplicate checks: {duplicate_checks}")
    return errors


def check_evidence_record_keys(
    target: str,
    entry: dict[str, Any],
    *,
    require_review_bundle: bool,
) -> list[str]:
    errors: list[str] = []
    keys: set[str] = set()
    for key in entry:
        if not isinstance(key, str):
            errors.append(f"{target} accepted evidence top-level keys must be strings, got {key!r}")
            continue
        keys.add(key)
    case_collisions = case_insensitive_name_collisions(keys)
    if case_collisions:
        errors.append(
            f"{target} accepted evidence top-level keys must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    if target in LINUX_TARGETS:
        allowed = set(LINUX_EVIDENCE_KEYS)
    elif target in XP_TARGETS:
        allowed = set(XP_EVIDENCE_KEYS)
    else:
        return errors
    if require_review_bundle or FINALIZED_EVIDENCE_KEYS & keys:
        allowed.update(FINALIZED_EVIDENCE_KEYS)
    unexpected = sorted(keys - allowed)
    if unexpected:
        errors.append(f"{target} accepted evidence has unexpected top-level fields: {unexpected}")
    return errors


def check_finalized_record_release_asset_url(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
) -> list[str]:
    if "finalized_record_release_asset_url" not in entry:
        return [f"{target} finalized_record_release_asset_url must be set"]
    raw_value = entry.get("finalized_record_release_asset_url")
    if not isinstance(raw_value, str):
        return [
            f"{target} finalized_record_release_asset_url must be a string GitHub release asset URL, "
            f"got {raw_value!r}"
        ]
    raw_url = raw_value.strip()
    if not raw_url:
        return [f"{target} finalized_record_release_asset_url must be set"]
    match = GITHUB_RELEASE_ASSET_RE.fullmatch(raw_url)
    if not match:
        return [f"{target} finalized_record_release_asset_url must be a GitHub release asset URL"]
    errors: list[str] = []
    repository = match.group(1)
    url_release_tag = match.group(2)
    if url_release_tag != release_tag:
        errors.append(
            f"{target} finalized_record_release_asset_url tag must match release_tag {release_tag}"
        )
    filename = release_asset_url_filename(raw_url)
    if not filename:
        errors.append(f"{target} finalized_record_release_asset_url file name must be an exact safe file name")
        return errors
    expected_file = accepted_record_source_file(target)
    if filename != expected_file:
        errors.append(f"{target} finalized_record_release_asset_url file must be {expected_file}")
    release_repositories = release_asset_repositories(entry.get("release_asset_urls"))
    review_bundle = entry.get("review_bundle")
    if isinstance(review_bundle, dict):
        release_repositories.update(release_asset_repositories(review_bundle.get("release_asset_urls")))
    if release_repositories and release_repositories != {repository}:
        errors.append(
            f"{target} finalized_record_release_asset_url repository must match release asset repository "
            f"{sorted(release_repositories)}, got {repository}"
        )
    return errors


def release_package_asset_urls(entry: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    raw_release_assets = entry.get("release_asset_urls")
    if isinstance(raw_release_assets, list):
        urls.extend(url for url in raw_release_assets if isinstance(url, str))
    review_bundle = entry.get("review_bundle")
    if isinstance(review_bundle, dict):
        raw_review_assets = review_bundle.get("release_asset_urls")
        if isinstance(raw_review_assets, list):
            urls.extend(url for url in raw_review_assets if isinstance(url, str))
    finalized_url = entry.get("finalized_record_release_asset_url")
    if isinstance(finalized_url, str):
        urls.append(finalized_url)
    return urls


def check_release_asset_source(
    target: str,
    release_tag: str,
    raw_source: Any,
    *,
    expected_files: set[str],
    allowed_files: set[str],
    native_release_assets: Any,
) -> list[str]:
    if not isinstance(raw_source, dict):
        return [f"{target} release_asset_source must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "release_asset_source",
            raw_source,
            RELEASE_ASSET_SOURCE_KEYS,
        )
    )
    raw_source_type = raw_source.get("type", "")
    if not isinstance(raw_source_type, str):
        errors.append(f"{target} release_asset_source.type must be a string")
    else:
        source_type = raw_source_type.strip()
        if source_type not in RELEASE_ASSET_SOURCE_TYPES:
            errors.append(
                f"{target} release_asset_source.type must be one of "
                f"{sorted(RELEASE_ASSET_SOURCE_TYPES)}, got {source_type!r}"
            )
    raw_workflow_run_url = raw_source.get("workflow_run_url", "")
    workflow_match = None
    if not isinstance(raw_workflow_run_url, str):
        errors.append(f"{target} release_asset_source.workflow_run_url must be a string")
    else:
        workflow_run_url = raw_workflow_run_url.strip().rstrip("/")
        workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url)
    if raw_workflow_run_url == "" or (isinstance(raw_workflow_run_url, str) and not workflow_match):
        errors.append(f"{target} release_asset_source.workflow_run_url must be a GitHub Actions run URL")
    elif workflow_match:
        release_repositories = release_asset_repositories(native_release_assets)
        workflow_repository = workflow_match.group(1)
        if release_repositories and release_repositories != {workflow_repository}:
            errors.append(
                f"{target} release_asset_source.workflow_run_url repository must match release asset repository "
                f"{sorted(release_repositories)}, got {workflow_repository}"
            )
    expected_workflow = release_source_workflow(target)
    raw_workflow = raw_source.get("workflow", "")
    if not isinstance(raw_workflow, str):
        errors.append(f"{target} release_asset_source.workflow must be a string")
    elif raw_workflow.strip() != expected_workflow:
        errors.append(f"{target} release_asset_source.workflow must be {expected_workflow}")
    raw_artifact_name = raw_source.get("artifact_name", "")
    if not isinstance(raw_artifact_name, str):
        errors.append(f"{target} release_asset_source.artifact_name must be a string")
    else:
        artifact_name = raw_artifact_name.strip()
        if (
            not artifact_name
            or "<" in artifact_name
            or ">" in artifact_name
            or "/" in artifact_name
            or "\\" in artifact_name
        ):
            errors.append(f"{target} release_asset_source.artifact_name must be a concrete artifact name")
        elif target in LINUX_TARGETS:
            expected_artifact_name = linux_release_source_artifact_name(target, release_tag)
            if artifact_name != expected_artifact_name:
                errors.append(
                    f"{target} release_asset_source.artifact_name must be {expected_artifact_name}"
                )
        elif target in XP_TARGETS:
            expected_artifact_name = xp_release_source_artifact_name(target, release_tag)
            if artifact_name != expected_artifact_name:
                errors.append(
                    f"{target} release_asset_source.artifact_name must be {expected_artifact_name}"
                )
    raw_head_sha = raw_source.get("head_sha", "")
    if not isinstance(raw_head_sha, str):
        errors.append(f"{target} release_asset_source.head_sha must be a string")
    elif not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(raw_head_sha.strip()):
        errors.append(f"{target} release_asset_source.head_sha must be a 40-character lowercase Git SHA")
    run_attempt = raw_source.get("run_attempt")
    if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
        errors.append(f"{target} release_asset_source.run_attempt must be a positive integer")
    raw_files = raw_source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        errors.append(f"{target} release_asset_source.contains_files must be a non-empty list")
        return errors
    files = [item for item in raw_files if isinstance(item, str)]
    file_counts: dict[str, int] = {}
    actual_files: set[str] = set()
    for item in raw_files:
        if not isinstance(item, str):
            errors.append(
                f"{target} release_asset_source.contains_files entries must be concrete file names, "
                f"got {item!r}"
            )
    for filename in files:
        file_counts[filename] = file_counts.get(filename, 0) + 1
        actual_files.add(filename)
        if "<" in filename or ">" in filename or not exact_safe_file_name(filename):
            errors.append(
                f"{target} release_asset_source.contains_files entries must be concrete file names, "
                f"got {filename!r}"
            )
    duplicate_files = sorted(name for name, count in file_counts.items() if count > 1)
    if duplicate_files:
        errors.append(f"{target} release_asset_source.contains_files contains duplicates: {duplicate_files}")
    case_collisions = case_insensitive_name_collisions(actual_files)
    if case_collisions:
        errors.append(
            f"{target} release_asset_source.contains_files must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    missing_files = sorted(expected_files - actual_files)
    if missing_files:
        errors.append(f"{target} release_asset_source.contains_files missing files: {missing_files}")
    unexpected_files = sorted(actual_files - allowed_files)
    if unexpected_files:
        errors.append(f"{target} release_asset_source.contains_files has unexpected files: {unexpected_files}")
    return errors


def check_review_bundle(
    target: str,
    release_tag: str,
    raw_bundle: Any,
    native_release_assets: Any,
) -> list[str]:
    if not isinstance(raw_bundle, dict):
        return [f"{target} review_bundle must be an object"]
    errors: list[str] = []
    errors.extend(
        check_exact_object_keys(
            target,
            "review_bundle",
            raw_bundle,
            REVIEW_BUNDLE_KEYS,
        )
    )
    expected_bundle_type = REVIEW_BUNDLE_TYPES[target]
    if raw_bundle.get("bundle_type") != expected_bundle_type:
        errors.append(f"{target} review_bundle bundle_type must be {expected_bundle_type}")
    expected_files = review_bundle_expected_files(target, release_tag)
    for key, expected_file in expected_files.items():
        raw_record = raw_bundle.get(key)
        if not isinstance(raw_record, dict):
            errors.append(f"{target} review_bundle {key} must be an object")
            continue
        errors.extend(
            check_exact_object_keys(
                target,
                f"review_bundle {key}",
                raw_record,
                REVIEW_BUNDLE_RECORD_KEYS,
            )
        )
        raw_file = raw_record.get("file", "")
        if not isinstance(raw_file, str):
            errors.append(f"{target} review_bundle {key}.file must be a string, got {raw_file!r}")
        elif raw_file != expected_file:
            errors.append(f"{target} review_bundle {key}.file must be {expected_file}")
        raw_digest = raw_record.get("sha256", "")
        if not isinstance(raw_digest, str):
            errors.append(
                f"{target} review_bundle {key}.sha256 must be a string SHA-256 hex digest, "
                f"got {raw_digest!r}"
            )
        elif not re.fullmatch(r"[0-9a-f]{64}", raw_digest):
            errors.append(f"{target} review_bundle {key}.sha256 must be a SHA-256 hex digest")
        size = raw_record.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            errors.append(f"{target} review_bundle {key}.size_bytes must be a positive integer")
    errors.extend(
        check_review_bundle_release_asset_urls(
            target,
            release_tag,
            raw_bundle.get("release_asset_urls"),
            expected_files=set(expected_files.values()),
            native_release_assets=native_release_assets,
        )
    )
    return errors


def check_review_bundle_release_asset_urls(
    target: str,
    release_tag: str,
    raw_urls: Any,
    *,
    expected_files: set[str],
    native_release_assets: Any,
) -> list[str]:
    if not isinstance(raw_urls, list) or not raw_urls:
        return [f"{target} review_bundle release_asset_urls must be a non-empty list"]
    errors: list[str] = []
    actual_files: set[str] = set()
    file_counts: dict[str, int] = {}
    bundle_repositories: set[str] = set()
    for url in raw_urls:
        if not isinstance(url, str):
            errors.append(
                f"{target} review_bundle release asset URL entries must be strings, got {url!r}"
            )
            continue
        url_text = url
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(url_text)
        if not match:
            errors.append(f"{target} review_bundle release asset URL is not a GitHub release asset URL: {url_text}")
            continue
        bundle_repositories.add(match.group(1))
        url_release_tag = match.group(2)
        if url_release_tag != release_tag:
            errors.append(
                f"{target} review_bundle release asset URL tag must match release_tag {release_tag}: {url_text}"
            )
            continue
        filename = release_asset_url_filename(url_text)
        if not filename:
            errors.append(
                f"{target} review_bundle release asset URL file name must be an exact safe file name: {url_text}"
            )
            continue
        actual_files.add(filename)
        file_counts[filename] = file_counts.get(filename, 0) + 1

    native_repositories = release_asset_repositories(native_release_assets)
    if native_repositories and bundle_repositories != native_repositories:
        errors.append(
            f"{target} review_bundle release asset URLs must use release asset repository "
            f"{sorted(native_repositories)}, got {sorted(bundle_repositories)}"
        )
    duplicate_files = sorted(name for name, count in file_counts.items() if count > 1)
    if duplicate_files:
        errors.append(f"{target} review_bundle release_asset_urls contain duplicate files: {duplicate_files}")
    case_collisions = case_insensitive_name_collisions(actual_files)
    if case_collisions:
        errors.append(
            f"{target} review_bundle release asset URL file names must not collide on "
            f"case-insensitive filesystems: {case_collisions}"
        )
    unexpected_files = sorted(actual_files - expected_files)
    if unexpected_files:
        errors.append(f"{target} review_bundle release_asset_urls reference unexpected files: {unexpected_files}")
    missing_files = sorted(expected_files - actual_files)
    if missing_files:
        errors.append(f"{target} review_bundle release_asset_urls missing files: {missing_files}")
    return errors


def review_bundle_expected_files(target: str, release_tag: str) -> dict[str, str]:
    stem = review_bundle_stem(target, release_tag)
    return {
        "manifest": f"{stem}.json",
        "archive": f"{stem}.zip",
        "sha256s": f"{stem}-SHA256SUMS.txt",
    }


def review_bundle_stem(target: str, release_tag: str) -> str:
    if target in LINUX_TARGETS:
        return f"extended-linux-evidence-bundle-{target}-{release_tag}"
    return f"xp-native-evidence-bundle-{target}-{release_tag}"


def release_asset_repositories(raw_assets: Any) -> set[str]:
    if not isinstance(raw_assets, list):
        return set()
    repositories: set[str] = set()
    for url in raw_assets:
        if not isinstance(url, str):
            continue
        text = url
        if not release_asset_url_filename(text):
            continue
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(text)
        if match:
            repositories.add(match.group(1))
    return repositories


def release_asset_url_filename(url: str) -> str:
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        return ""
    path_segments = parts.path.split("/")
    if (
        len(path_segments) != 7
        or path_segments[0] != ""
        or path_segments[3:5] != ["releases", "download"]
        or not path_segments[-1]
    ):
        return ""
    filename = unquote(path_segments[-1])
    return filename if exact_safe_file_name(filename) else ""


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


def exact_safe_file_name(filename: str) -> bool:
    if not filename or filename.strip() != filename or "/" in filename or "\\" in filename:
        return False
    if filename in (".", ".."):
        return False
    windows_path = PureWindowsPath(filename)
    posix_path = PurePosixPath(filename)
    return not windows_path.drive and not windows_path.is_absolute() and not posix_path.is_absolute()


def check_artifact_validation_command(target: str, release_tag: str, command: str) -> list[str]:
    expected_prefix = f"python scripts/check_platform_promotion_artifacts.py --target {target} "
    errors: list[str] = []
    if not command.startswith(expected_prefix):
        errors.append(f"{target} artifact_validation_command must start with {expected_prefix!r}")
    errors.extend(
        check_no_unexpected_command_flags(
            target,
            "artifact_validation_command",
            command,
            ARTIFACT_VALIDATION_COMMAND_FLAGS,
        )
    )
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1:
        errors.append(f"{target} artifact_validation_command must include exactly one --assets-dir, got {asset_dirs}")
    elif "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        errors.append(f"{target} artifact_validation_command --assets-dir must be concrete, got {asset_dirs[0]!r}")
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--assets-dir",
                asset_dirs[0],
                command_label="artifact_validation_command",
                require_directory_hint=True,
                require_target_release_scope=target in LINUX_TARGETS or target in XP_TARGETS,
                release_tag=release_tag,
            )
        )
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    if tags != [release_tag]:
        errors.append(
            f"{target} artifact_validation_command must include exactly one --tag {release_tag}, got {tags}"
        )
    strict_count = command_flag_count(command, "--strict")
    if strict_count != 1:
        errors.append(f"{target} artifact_validation_command must include exactly one --strict, got {strict_count}")
    return errors


def check_local_evidence_preflight_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
) -> list[str]:
    raw_command = entry.get("local_evidence_preflight_command", "")
    command = raw_command if isinstance(raw_command, str) else ""
    expected_prefix = "python scripts/check_platform_goal_local_evidence.py "
    errors: list[str] = []
    if not isinstance(raw_command, str):
        errors.append(
            f"{target} local_evidence_preflight_command must be a string command, got {raw_command!r}"
        )
    if not command.startswith(expected_prefix):
        errors.append(
            f"{target} local_evidence_preflight_command must start with {expected_prefix!r}"
        )
    errors.extend(
        check_no_unexpected_command_flags(
            target,
            "local_evidence_preflight_command",
            command,
            local_evidence_preflight_allowed_flags(target),
        )
    )
    roots = command_argument_values(command, "--root")
    root = roots[0] if len(roots) == 1 else ""
    if len(roots) != 1:
        errors.append(f"{target} local_evidence_preflight_command must include exactly one --root, got {roots}")
    elif "<" in root or ">" in root:
        errors.append(f"{target} local_evidence_preflight_command --root must be concrete, got {root!r}")
    else:
        errors.extend(check_local_evidence_root_path(target, root))
    release_tags = command_argument_values(command, "--release-tag")
    if release_tags != [release_tag]:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one --release-tag {release_tag}, "
            f"got {release_tags}"
        )
    targets = command_argument_values(command, "--target")
    if targets != [target]:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one --target {target}, got {targets}"
        )
    asset_dirs = command_argument_values(command, "--assets-dir")
    if len(asset_dirs) != 1:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one --assets-dir, got {asset_dirs}"
        )
    elif "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        errors.append(
            f"{target} local_evidence_preflight_command --assets-dir must be concrete, got {asset_dirs[0]!r}"
        )
    raw_artifact_command = entry.get("artifact_validation_command", "")
    artifact_command = raw_artifact_command if isinstance(raw_artifact_command, str) else ""
    artifact_asset_dirs = command_argument_values(artifact_command, "--assets-dir")
    if len(asset_dirs) == 1 and len(artifact_asset_dirs) == 1 and asset_dirs != artifact_asset_dirs:
        errors.append(
            f"{target} local_evidence_preflight_command --assets-dir must match artifact_validation_command "
            "--assets-dir"
        )
    if root:
        for flag, values in local_evidence_path_bindings(target, command).items():
            for value in values:
                if "<" not in value and ">" not in value:
                    errors.extend(check_path_under_local_evidence_root(target, root, flag, value))
    if target in LINUX_TARGETS:
        errors.extend(check_linux_local_evidence_preflight_command(target, release_tag, entry, command))
    elif target in XP_TARGETS:
        errors.extend(check_xp_local_evidence_preflight_command(target, release_tag, entry, command))
    return errors


def local_evidence_path_bindings(target: str, command: str) -> dict[str, list[str]]:
    bindings = {"--assets-dir": command_argument_values(command, "--assets-dir")}
    if target in LINUX_TARGETS:
        bindings["--linux-builder-evidence"] = command_argument_values(command, "--linux-builder-evidence")
        bindings["--linux-smoke-evidence"] = command_argument_values(command, "--linux-smoke-evidence")
    elif target in XP_TARGETS:
        bindings["--xp-evidence"] = command_argument_values(command, "--xp-evidence")
        bindings["--xp-evidence-dir"] = command_argument_values(command, "--xp-evidence-dir")
    return bindings


def check_local_evidence_root_path(target: str, raw_root: str) -> list[str]:
    if raw_root == ".":
        return []
    return check_xp_validation_command_path(
        target,
        "--root",
        raw_root,
        command_label="local_evidence_preflight_command",
        require_directory_hint=True,
    )


def check_path_under_local_evidence_root(
    target: str,
    raw_root: str,
    flag: str,
    raw_path: str,
) -> list[str]:
    root_parts = relative_path_parts(raw_root)
    path_parts = relative_path_parts(raw_path)
    if root_parts and (len(path_parts) < len(root_parts) or path_parts[: len(root_parts)] != root_parts):
        return [
            f"{target} local_evidence_preflight_command {flag} "
            f"must stay under --root {raw_root}, got {raw_path!r}"
        ]
    return []


def relative_path_parts(raw_path: str) -> tuple[str, ...]:
    path = raw_path.strip()
    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    if "\\" in path or windows_path.is_absolute() or bool(windows_path.drive):
        parts = windows_path.parts
    else:
        parts = posix_path.parts
    return tuple(part for part in parts if part not in ("", "."))


def check_linux_local_evidence_preflight_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
    command: str,
) -> list[str]:
    errors: list[str] = []
    for forbidden in ("--xp-evidence", "--xp-evidence-dir"):
        values = command_argument_values(command, forbidden)
        if values:
            errors.append(f"{target} local_evidence_preflight_command must not include {forbidden}, got {values}")
    builder_paths = command_argument_values(command, "--linux-builder-evidence")
    if len(builder_paths) != 1:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one --linux-builder-evidence, "
            f"got {builder_paths}"
        )
    elif not concrete_path_value(builder_paths[0]) or Path(builder_paths[0]).name != f"builder-identity-{target}.json":
        errors.append(
            f"{target} local_evidence_preflight_command --linux-builder-evidence must be "
            f"builder-identity-{target}.json"
        )
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--linux-builder-evidence",
                builder_paths[0],
                command_label="local_evidence_preflight_command",
                require_json_hint=True,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    smoke_paths = command_argument_values(command, "--linux-smoke-evidence")
    if len(smoke_paths) != 1:
        errors.append(
            f"{target} local_evidence_preflight_command must include exactly one --linux-smoke-evidence, "
            f"got {smoke_paths}"
        )
    elif not concrete_path_value(smoke_paths[0]) or Path(smoke_paths[0]).name != f"native-smoke-{target}.log":
        errors.append(
            f"{target} local_evidence_preflight_command --linux-smoke-evidence must be native-smoke-{target}.log"
        )
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--linux-smoke-evidence",
                smoke_paths[0],
                command_label="local_evidence_preflight_command",
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    workflow_urls = command_argument_values(command, "--linux-workflow-run-url")
    raw_workflow_url = entry.get("workflow_run_url", "")
    expected_workflow_url = raw_workflow_url.strip().rstrip("/") if isinstance(raw_workflow_url, str) else ""
    if workflow_urls != [expected_workflow_url]:
        errors.append(
            f"{target} local_evidence_preflight_command --linux-workflow-run-url must match workflow_run_url"
        )
    source = entry.get("release_asset_source")
    expected_head_sha = valid_release_source_head_sha(source)
    source_head_shas = command_argument_values(command, "--linux-source-head-sha")
    if source_head_shas != [expected_head_sha]:
        errors.append(
            f"{target} local_evidence_preflight_command --linux-source-head-sha must match "
            "release_asset_source.head_sha"
        )
    expected_run_attempt = valid_release_source_run_attempt_text(source)
    source_run_attempts = command_argument_values(command, "--linux-source-run-attempt")
    if source_run_attempts != [expected_run_attempt]:
        errors.append(
            f"{target} local_evidence_preflight_command --linux-source-run-attempt must match "
            "release_asset_source.run_attempt"
        )
    allow_extra_count = command_flag_count(command, "--allow-extra-artifacts")
    if allow_extra_count:
        errors.append(f"{target} local_evidence_preflight_command must not include --allow-extra-artifacts")
    return errors


def check_xp_local_evidence_preflight_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
    command: str,
) -> list[str]:
    errors: list[str] = []
    for forbidden in (
        "--linux-builder-evidence",
        "--linux-smoke-evidence",
        "--linux-workflow-run-url",
        "--linux-source-head-sha",
        "--linux-source-run-attempt",
    ):
        values = command_argument_values(command, forbidden)
        if values:
            errors.append(f"{target} local_evidence_preflight_command must not include {forbidden}, got {values}")
    allow_extra_count = command_flag_count(command, "--allow-extra-artifacts")
    if allow_extra_count:
        errors.append(f"{target} local_evidence_preflight_command must not include --allow-extra-artifacts")

    source = entry.get("release_asset_source")
    expected_workflow_url = valid_release_source_workflow_run_url(source)
    workflow_urls = command_argument_values(command, "--xp-source-workflow-run-url")
    if workflow_urls != [expected_workflow_url]:
        errors.append(
            f"{target} local_evidence_preflight_command --xp-source-workflow-run-url must match "
            "release_asset_source.workflow_run_url"
        )
    expected_head_sha = valid_release_source_head_sha(source)
    source_head_shas = command_argument_values(command, "--xp-source-head-sha")
    if source_head_shas != [expected_head_sha]:
        errors.append(
            f"{target} local_evidence_preflight_command --xp-source-head-sha must match "
            "release_asset_source.head_sha"
        )
    expected_run_attempt = valid_release_source_run_attempt_text(source)
    source_run_attempts = command_argument_values(command, "--xp-source-run-attempt")
    if source_run_attempts != [expected_run_attempt]:
        errors.append(
            f"{target} local_evidence_preflight_command --xp-source-run-attempt must match "
            "release_asset_source.run_attempt"
        )

    raw_native_command = entry.get("native_evidence_validation_command", "")
    native_command = raw_native_command if isinstance(raw_native_command, str) else ""
    native_paths = xp_native_evidence_validation_command_paths(native_command)
    path_bindings = {
        "--xp-evidence": ("--evidence", native_paths["evidence_file"], True, False),
        "--assets-dir": ("--assets-dir", native_paths["assets_dir"], False, True),
        "--xp-evidence-dir": ("--evidence-dir", native_paths["evidence_dir"], False, True),
    }
    for preflight_flag, (native_flag, native_values, require_json, require_directory) in path_bindings.items():
        values = command_argument_values(command, preflight_flag)
        if len(values) != 1:
            errors.append(
                f"{target} local_evidence_preflight_command must include exactly one {preflight_flag}, "
                f"got {values}"
            )
            continue
        if native_values and values != native_values:
            errors.append(
                f"{target} local_evidence_preflight_command {preflight_flag} must match "
                f"native_evidence_validation_command {native_flag}"
            )
        errors.extend(
            check_xp_validation_command_path(
                target,
                preflight_flag,
                values[0],
                command_label="local_evidence_preflight_command",
                require_json_hint=require_json,
                require_directory_hint=require_directory,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    return errors


def check_staged_upload_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
) -> list[str]:
    raw_command = entry.get("staged_upload_command", "")
    command = raw_command if isinstance(raw_command, str) else ""
    expected_prefix = (
        "python scripts/stage_extended_linux_evidence_upload.py "
        if target in LINUX_TARGETS
        else "python scripts/stage_xp_native_evidence_upload.py "
    )
    errors: list[str] = []
    if not isinstance(raw_command, str):
        errors.append(f"{target} staged_upload_command must be a string command, got {raw_command!r}")
    if not command.startswith(expected_prefix):
        errors.append(f"{target} staged_upload_command must start with {expected_prefix!r}")
    errors.extend(
        check_no_unexpected_command_flags(
            target,
            "staged_upload_command",
            command,
            staged_upload_allowed_flags(target),
        )
    )
    targets = command_argument_values(command, "--target")
    if targets != [target]:
        errors.append(
            f"{target} staged_upload_command must include exactly one --target {target}, got {targets}"
        )
    release_tags = command_argument_values(command, "--release-tag")
    if release_tags != [release_tag]:
        errors.append(
            f"{target} staged_upload_command must include exactly one --release-tag {release_tag}, "
            f"got {release_tags}"
        )
    out_dirs = command_argument_values(command, "--out-dir")
    if len(out_dirs) != 1:
        errors.append(f"{target} staged_upload_command must include exactly one --out-dir, got {out_dirs}")
    elif not concrete_path_value(out_dirs[0]):
        errors.append(f"{target} staged_upload_command --out-dir must be concrete, got {out_dirs[0]!r}")
    else:
        errors.extend(
            check_xp_validation_command_path(
                target,
                "--out-dir",
                out_dirs[0],
                command_label="staged_upload_command",
                require_directory_hint=True,
                require_target_release_scope=True,
                release_tag=release_tag,
            )
        )
    force_count = command_flag_count(command, "--force")
    if force_count != 1:
        errors.append(f"{target} staged_upload_command must include exactly one --force, got {force_count}")
    if target in LINUX_TARGETS:
        errors.extend(check_linux_staged_upload_command(target, release_tag, entry, command))
    elif target in XP_TARGETS:
        errors.extend(check_xp_staged_upload_command(target, release_tag, entry, command))
    return errors


def check_linux_staged_upload_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
    command: str,
) -> list[str]:
    errors: list[str] = []
    source_dirs = command_argument_values(command, "--source-dir")
    if len(source_dirs) != 1:
        errors.append(
            f"{target} staged_upload_command must include exactly one --source-dir, got {source_dirs}"
        )
        return errors
    source_dir = source_dirs[0]
    if not concrete_path_value(source_dir):
        errors.append(f"{target} staged_upload_command --source-dir must be concrete, got {source_dir!r}")
        return errors
    raw_artifact_command = entry.get("artifact_validation_command", "")
    artifact_command = raw_artifact_command if isinstance(raw_artifact_command, str) else ""
    artifact_asset_dirs = command_argument_values(artifact_command, "--assets-dir")
    if len(artifact_asset_dirs) == 1 and source_dirs != artifact_asset_dirs:
        errors.append(
            f"{target} staged_upload_command --source-dir must match artifact_validation_command --assets-dir"
        )
    out_dirs = command_argument_values(command, "--out-dir")
    if len(out_dirs) == 1 and command_paths_overlap(source_dir, out_dirs[0]):
        errors.append(
            f"{target} staged_upload_command --out-dir must be a separate root from --source-dir"
        )
    errors.extend(
        check_xp_validation_command_path(
            target,
            "--source-dir",
            source_dir,
            command_label="staged_upload_command",
            require_directory_hint=True,
            require_target_release_scope=True,
            release_tag=release_tag,
        )
    )
    return errors


def check_xp_staged_upload_command(
    target: str,
    release_tag: str,
    entry: dict[str, Any],
    command: str,
) -> list[str]:
    errors: list[str] = []
    out_dirs = command_argument_values(command, "--out-dir")
    asset_dirs = command_argument_values(command, "--assets-dir")
    if len(asset_dirs) != 1:
        errors.append(f"{target} staged_upload_command must include exactly one --assets-dir, got {asset_dirs}")
    else:
        assets_dir = asset_dirs[0]
        if not concrete_path_value(assets_dir):
            errors.append(f"{target} staged_upload_command --assets-dir must be concrete, got {assets_dir!r}")
        else:
            raw_artifact_command = entry.get("artifact_validation_command", "")
            artifact_command = raw_artifact_command if isinstance(raw_artifact_command, str) else ""
            artifact_asset_dirs = command_argument_values(artifact_command, "--assets-dir")
            if len(artifact_asset_dirs) == 1 and asset_dirs != artifact_asset_dirs:
                errors.append(
                    f"{target} staged_upload_command --assets-dir must match "
                    "artifact_validation_command --assets-dir"
                )
            errors.extend(
                check_xp_validation_command_path(
                    target,
                    "--assets-dir",
                    assets_dir,
                    command_label="staged_upload_command",
                    require_directory_hint=True,
                    require_target_release_scope=True,
                    release_tag=release_tag,
                )
            )
    output_dirs = command_argument_values(command, "--evidence-output-dir")
    if len(output_dirs) != 1:
        errors.append(
            f"{target} staged_upload_command must include exactly one --evidence-output-dir, "
            f"got {output_dirs}"
        )
    else:
        output_dir = output_dirs[0]
        if not concrete_path_value(output_dir):
            errors.append(
                f"{target} staged_upload_command --evidence-output-dir must be concrete, got {output_dir!r}"
            )
        else:
            errors.extend(
                check_xp_validation_command_path(
                    target,
                    "--evidence-output-dir",
                    output_dir,
                    command_label="staged_upload_command",
                    require_directory_hint=True,
                    require_target_release_scope=True,
                    release_tag=release_tag,
                )
            )
    if len(asset_dirs) == 1 and len(output_dirs) == 1 and command_paths_overlap(asset_dirs[0], output_dirs[0]):
        errors.append(
            f"{target} staged_upload_command --assets-dir and --evidence-output-dir must be separate roots"
        )
    if len(asset_dirs) == 1 and len(out_dirs) == 1 and command_paths_overlap(asset_dirs[0], out_dirs[0]):
        errors.append(
            f"{target} staged_upload_command --out-dir must be a separate root from --assets-dir"
        )
    if len(output_dirs) == 1 and len(out_dirs) == 1 and command_paths_overlap(output_dirs[0], out_dirs[0]):
        errors.append(
            f"{target} staged_upload_command --out-dir must be a separate root from --evidence-output-dir"
        )
    return errors


def command_paths_overlap(left: str, right: str) -> bool:
    left_parts = normalized_command_path_parts(left)
    right_parts = normalized_command_path_parts(right)
    if not left_parts or not right_parts:
        return False
    return path_parts_contain(left_parts, right_parts) or path_parts_contain(right_parts, left_parts)


def normalized_command_path_parts(raw_path: str) -> tuple[str, ...]:
    path = raw_path.strip().replace("\\", "/")
    parts = PurePosixPath(path).parts
    return tuple(part for part in parts if part not in ("", ".", "/"))


def path_parts_contain(parent: tuple[str, ...], child: tuple[str, ...]) -> bool:
    return len(parent) <= len(child) and child[: len(parent)] == parent


def command_argument_values(command: str, flag: str) -> list[str]:
    return re.findall(rf"(?:^|\s){re.escape(flag)}\s+(\S+)(?=\s|$)", command)


def command_flag_count(command: str, flag: str) -> int:
    return len(re.findall(rf"(?:^|\s){re.escape(flag)}(?=\s|$)", command))


def command_flags(command: str) -> list[str]:
    return re.findall(r"(?<!\S)(--[A-Za-z0-9][A-Za-z0-9_-]*)(?=\s|=|$)", command)


def check_no_unexpected_command_flags(
    target: str,
    command_label: str,
    command: str,
    allowed_flags: set[str],
) -> list[str]:
    unexpected = sorted(set(command_flags(command)) - allowed_flags)
    if unexpected:
        return [f"{target} {command_label} has unexpected flags: {unexpected}"]
    return []


def local_evidence_preflight_allowed_flags(target: str) -> set[str]:
    if target in LINUX_TARGETS:
        return LINUX_LOCAL_EVIDENCE_PREFLIGHT_FLAGS
    if target in XP_TARGETS:
        return XP_LOCAL_EVIDENCE_PREFLIGHT_FLAGS
    return COMMON_LOCAL_EVIDENCE_PREFLIGHT_FLAGS


def staged_upload_allowed_flags(target: str) -> set[str]:
    if target in LINUX_TARGETS:
        return LINUX_STAGED_UPLOAD_COMMAND_FLAGS
    if target in XP_TARGETS:
        return XP_STAGED_UPLOAD_COMMAND_FLAGS
    return {"--target", "--release-tag", "--out-dir", "--force"}


def concrete_path_value(value: str) -> bool:
    return bool(value) and "<" not in value and ">" not in value


def check_artifact_sha256(target: str, raw_hashes: Any, expected_artifact_names: set[str]) -> list[str]:
    if not isinstance(raw_hashes, dict):
        return [f"{target} evidence must include artifact_sha256 map"]
    errors: list[str] = []
    hashes: dict[str, str] = {}
    for name, value in raw_hashes.items():
        if not isinstance(name, str) or not exact_safe_file_name(name):
            errors.append(f"{target} artifact_sha256 keys must be exact safe file names, got {name!r}")
            continue
        if not isinstance(value, str):
            errors.append(f"{target} artifact_sha256 for {name} must be a string SHA-256 hex digest")
            continue
        hashes[name] = str(value)
    case_collisions = case_insensitive_name_collisions(set(hashes))
    if case_collisions:
        errors.append(
            f"{target} artifact_sha256 keys must not collide on case-insensitive filesystems: "
            f"{case_collisions}"
        )
    missing_hashes = sorted(expected_artifact_names - set(hashes))
    if missing_hashes:
        errors.append(f"{target} artifact_sha256 missing entries for: {missing_hashes}")
    unexpected_hashes = sorted(set(hashes) - expected_artifact_names)
    if unexpected_hashes:
        errors.append(f"{target} artifact_sha256 references unexpected files: {unexpected_hashes}")
    for filename, digest in sorted(hashes.items()):
        if filename in expected_artifact_names and not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{target} artifact_sha256 for {filename} must be a SHA-256 hex digest")
    return errors


def accepted_artifact_names(
    target: str,
    release_tag: str,
    promotion_entries: dict[str, dict[str, Any]],
) -> set[str]:
    entry = promotion_entries.get(target, {})
    requirements = entry.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return set()
    raw_artifacts = requirements.get("required_artifacts", requirements.get("native_artifacts", []))
    if not isinstance(raw_artifacts, list):
        return set()
    version = release_tag.removeprefix("v")
    return {str(item).replace("<project.version>", version) for item in raw_artifacts}


def xp_release_source_artifact_name(target: str, release_tag: str) -> str:
    return f"xp-native-evidence-{target}-{release_tag}"


def linux_release_source_artifact_name(target: str, release_tag: str) -> str:
    template = str(LINUX_TARGETS[target]["artifact_template"])
    return template.format(release_tag=release_tag)


def release_source_workflow(target: str) -> str:
    if target in LINUX_TARGETS:
        return str(LINUX_TARGETS[target]["workflow"])
    if target in XP_TARGETS:
        return str(XP_TARGETS[target]["workflow"])
    return ""


def accepted_record_source_file(target: str) -> str:
    return f"platform-verified-evidence-{target}-final.json"


def check_registry_consistency(registry: dict[str, Any]) -> list[str]:
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    errors: list[str] = []
    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        target = accepted_evidence_target(item)
        if target:
            by_target.setdefault(target, []).append(item)
    for target, entries in sorted(by_target.items()):
        if len(entries) > 1:
            errors.append(f"accepted_evidence target must be unique: {target}")

    protected_entries = {
        target: entries[0]
        for target, entries in by_target.items()
        if target in PROTECTED_GOAL_TARGETS and len(entries) == 1
    }
    errors.extend(check_partial_protected_goal_release_scope(protected_entries))

    xp_entries = {
        target: entries[0]
        for target, entries in by_target.items()
        if target in XP_TARGETS and len(entries) == 1
    }
    if set(XP_TARGETS).issubset(xp_entries):
        release_tags = {
            release_tag
            for entry in xp_entries.values()
            if (release_tag := accepted_evidence_release_tag(entry))
        }
        if len(release_tags) != 1:
            errors.append(
                "Windows XP native evidence pair must use one release_tag, "
                f"got {sorted(release_tags)}"
            )
        repositories_by_target = {
            target: release_asset_repositories(entry.get("release_asset_urls"))
            for target, entry in xp_entries.items()
        }
        repository_scope_errors = release_repository_scope_errors(
            repositories_by_target,
            "Windows XP native evidence pair must derive exactly one safe GitHub release repository",
        )
        errors.extend(repository_scope_errors)
        if not repository_scope_errors:
            repositories = {
                next(iter(repositories))
                for repositories in repositories_by_target.values()
            }
            if len(repositories) != 1:
                errors.append(
                    "Windows XP native evidence pair must use one GitHub release repository, "
                    f"got {format_repositories_by_target(repositories_by_target)}"
                )
        heads_by_target = release_source_heads_by_target(xp_entries)
        if len(heads_by_target) == len(XP_TARGETS) and len(set(heads_by_target.values())) != 1:
            errors.append(
                "Windows XP native evidence pair must use one release source head SHA, "
                f"got {format_values_by_target(heads_by_target)}"
            )
    return errors


def check_partial_protected_goal_release_scope(entries: dict[str, dict[str, Any]]) -> list[str]:
    if len(entries) < 2:
        return []
    errors: list[str] = []
    release_tags_by_target = {
        target: release_tag
        for target, entry in entries.items()
        if (release_tag := accepted_evidence_release_tag(entry))
    }
    if len(release_tags_by_target) == len(entries) and len(set(release_tags_by_target.values())) != 1:
        errors.append(
            "partial protected platform goal evidence must use one release_tag before promotion, "
            f"got {format_values_by_target(release_tags_by_target)}"
        )
    repositories_by_target = {
        target: release_asset_repositories(entry.get("release_asset_urls"))
        for target, entry in entries.items()
    }
    repository_scope_errors = release_repository_scope_errors(
        repositories_by_target,
        "partial protected platform goal evidence must derive exactly one safe GitHub release repository before promotion",
    )
    errors.extend(repository_scope_errors)
    if not repository_scope_errors:
        repositories = {
            next(iter(repositories))
            for repositories in repositories_by_target.values()
        }
        if len(repositories) != 1:
            errors.append(
                "partial protected platform goal evidence must use one GitHub release repository before promotion, "
                f"got {format_repositories_by_target(repositories_by_target)}"
            )
    heads_by_target = release_source_heads_by_target(entries)
    if len(heads_by_target) == len(entries) and len(set(heads_by_target.values())) != 1:
        errors.append(
            "partial protected platform goal evidence must use one release source head SHA before promotion, "
            f"got {format_values_by_target(heads_by_target)}"
        )
    for run_url, attempts_by_target in sorted(release_source_run_attempt_conflicts(entries).items()):
        formatted = {target: attempts_by_target[target] for target in sorted(attempts_by_target)}
        errors.append(
            "partial protected platform goal evidence must not reuse one release source workflow run URL "
            f"with conflicting run attempts before promotion, got {run_url}: {formatted}"
        )
    return errors


def release_repository_scope_errors(
    repositories_by_target: dict[str, set[str]],
    label: str,
) -> list[str]:
    ambiguous = {
        target: sorted(repositories)
        for target, repositories in sorted(repositories_by_target.items())
        if len(repositories) != 1
    }
    if not ambiguous:
        return []
    return [f"{label}, got {ambiguous}"]


def release_source_run_attempt_conflicts(
    entries: dict[str, dict[str, Any]],
) -> dict[str, dict[str, int]]:
    run_attempts_by_url: dict[str, dict[str, int]] = {}
    for target, entry in sorted(entries.items()):
        source = entry.get("release_asset_source")
        run_url = valid_release_source_workflow_run_url(source)
        run_attempt = source.get("run_attempt") if isinstance(source, dict) else None
        if (
            not run_url
            or not isinstance(run_attempt, int)
            or isinstance(run_attempt, bool)
            or run_attempt <= 0
        ):
            continue
        run_attempts_by_url.setdefault(run_url, {})[target] = run_attempt
    return {
        run_url: attempts_by_target
        for run_url, attempts_by_target in sorted(run_attempts_by_url.items())
        if len(set(attempts_by_target.values())) != 1
    }


def format_repositories_by_target(repositories_by_target: dict[str, set[str]]) -> dict[str, list[str]]:
    return {
        target: sorted(repositories)
        for target, repositories in sorted(repositories_by_target.items())
    }


def release_source_heads_by_target(entries: dict[str, dict[str, Any]]) -> dict[str, str]:
    heads: dict[str, str] = {}
    for target, entry in sorted(entries.items()):
        source = entry.get("release_asset_source")
        head_sha = valid_release_source_head_sha(source)
        if head_sha:
            heads[target] = head_sha
    return heads


def valid_release_source_workflow_run_url(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    raw_url = source.get("workflow_run_url")
    if not isinstance(raw_url, str):
        return ""
    workflow_run_url = raw_url.strip().rstrip("/")
    if not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url):
        return ""
    return workflow_run_url


def valid_release_source_head_sha(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    raw_head_sha = source.get("head_sha")
    if not isinstance(raw_head_sha, str):
        return ""
    head_sha = raw_head_sha.strip()
    if not RELEASE_SOURCE_HEAD_SHA_RE.fullmatch(head_sha):
        return ""
    return head_sha


def valid_release_source_run_attempt_text(source: Any) -> str:
    if not isinstance(source, dict):
        return ""
    run_attempt = source.get("run_attempt")
    if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt < 1:
        return ""
    return str(run_attempt)


def format_values_by_target(values_by_target: dict[str, str]) -> dict[str, str]:
    return {target: values_by_target[target] for target in sorted(values_by_target)}


def promotion_entries_by_id(
    promotion: dict[str, Any],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for item in promotion.get("protected_targets", []):
        if not isinstance(item, dict):
            errors.append("promotion protected target entries must be objects")
            continue
        raw_target = item.get("id", "")
        if not isinstance(raw_target, str) or not raw_target.strip():
            errors.append(
                "promotion protected target id must be a non-empty string, "
                f"got {raw_target!r}"
            )
            continue
        entries[raw_target.strip()] = item
    missing = sorted(KNOWN_TARGETS - set(entries))
    if missing:
        errors.append(f"promotion config missing protected target entries: {missing}")
    return entries


def promotion_config_sha256(promotion: dict[str, Any]) -> str:
    return json_sha256(promotion)


def xp_native_evidence_contract_sha256() -> str:
    return json_sha256(read_json(XP_CONTRACT_PATH))


def xp_target_contract(target: str) -> dict[str, Any]:
    targets = read_json(XP_CONTRACT_PATH).get("targets", {})
    if not isinstance(targets, dict):
        return {}
    target_contract = targets.get(target, {})
    return target_contract if isinstance(target_contract, dict) else {}


def contains_non_string_json_object_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            not isinstance(key, str) or contains_non_string_json_object_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(contains_non_string_json_object_key(child) for child in value)
    return False


def json_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    path_errors = check_json_input_path(path, "JSON evidence source")
    if path_errors:
        raise ValueError(path_errors[0])
    return json.loads(path.read_text(encoding="utf-8"))


def check_json_input_path(path: Path, label: str) -> list[str]:
    errors = check_path_not_reserved_workspace_root(path, label)
    if errors:
        return errors
    if path.is_symlink():
        return [f"{label} must not be a symlink: {path}"]
    return check_path_parent_symlinks(path, label)


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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
