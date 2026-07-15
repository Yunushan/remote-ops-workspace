from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.features import coverage_report  # noqa: E402

PLATFORM_TARGETS_PATH = ROOT / "configs" / "platform_targets.json"
RELEASE_MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
LINUX_PROTECTED_TARGETS = {"linux-i386", "linux-armhf"}
XP_PROTECTED_TARGET_ORDER = ["windows-xp-native-x86", "windows-xp-native-x64"]
XP_PROTECTED_TARGETS = set(XP_PROTECTED_TARGET_ORDER)
PROTECTED_GOAL_TARGET_ORDER = [
    "linux-i386",
    "linux-armhf",
    *XP_PROTECTED_TARGET_ORDER,
]
PROTECTED_GOAL_TARGETS = set(PROTECTED_GOAL_TARGET_ORDER)
PROTECTED_RELEASE_SOURCE_WORKFLOWS = {
    "linux-i386": ".github/workflows/extended-platform-evidence.yml",
    "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
    "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    "windows-xp-native-x64": ".github/workflows/xp-native-evidence.yml",
}
PROTECTED_LINUX_CATALOG_ASSETS = {
    "linux-i386": {
        "remote-ops-workspace-v1.0.4-linux-i386.deb",
        "remote-ops-workspace-v1.0.4-linux-i686.rpm",
        "remote-ops-workspace-v1.0.4-linux-i686.AppImage",
        "remote-ops-workspace-v1.0.4-linux-i686-native.tar.gz",
        "remote-ops-workspace-v1.0.4-linux-i686-native-manifest.json",
        "remote-ops-workspace-v1.0.4-linux-i686-native-SHA256SUMS.txt",
    },
    "linux-armhf": {
        "remote-ops-workspace-v1.0.4-linux-armhf.deb",
        "remote-ops-workspace-v1.0.4-linux-armv7hl.rpm",
        "remote-ops-workspace-v1.0.4-linux-armhf.AppImage",
        "remote-ops-workspace-v1.0.4-linux-armhf-native.tar.gz",
        "remote-ops-workspace-v1.0.4-linux-armhf-native-manifest.json",
        "remote-ops-workspace-v1.0.4-linux-armhf-native-SHA256SUMS.txt",
    },
}
PROTECTED_READINESS_GATE_COMMANDS = {
    "accepted_evidence_gate": (
        "python scripts/check_platform_verified_evidence.py "
        "--require-goal-targets --require-review-bundles --release-tag v<project.version>"
    ),
    "protected_goal_gate": (
        "python scripts/check_protected_platform_goal.py "
        "--release-tag v<project.version> --require-records-complete"
    ),
    "release_asset_provenance_gate": (
        "python scripts/check_protected_platform_goal.py "
        "--release-tag v<project.version> --require-complete "
        "--assets-dir <release-assets-dir> --repository <owner>/<repo>"
    ),
    "published_release_audit_gate": (
        "python scripts/verify.py --quick --no-cli-smoke "
        "--require-platform-goal-targets --release-tag v<project.version> "
        "--platform-review-bundle-dir <bundle-dir> "
        "--release-assets-dir <release-assets-dir> "
        "--release-repository <owner>/<repo>"
    ),
}
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
SOURCE_HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]+$")

EXPECTED_ARCHITECTURES: dict[str, dict[str, Any]] = {
    "windows-x86": {
        "bits": 32,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "windows-x64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "windows-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "linux-i386": {
        "bits": 32,
        "release_tier": "script-supported-native",
        "github_release_channel": "manual-script-native",
        "score": 70.0,
        "status": "manual-script-supported",
    },
    "linux-x86_64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "linux-armhf": {
        "bits": 32,
        "release_tier": "script-supported-native",
        "github_release_channel": "manual-script-native",
        "score": 70.0,
        "status": "manual-script-supported",
    },
    "linux-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "macos-x64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "macos-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "android-armv7": {
        "bits": 32,
        "release_tier": "termux-web",
        "github_release_channel": "default-termux-web",
        "score": 100.0,
        "status": "verified-termux-web-mobile",
    },
    "android-arm64": {
        "bits": 64,
        "release_tier": "termux-web",
        "github_release_channel": "default-termux-web",
        "score": 100.0,
        "status": "verified-termux-web-mobile",
    },
    "ios-web": {
        "bits": 64,
        "release_tier": "web-pwa",
        "github_release_channel": "default-web-pwa",
        "score": 100.0,
        "status": "verified-ios-web-pwa",
    },
}

EXPECTED_LEGACY_WINDOWS: dict[str, dict[str, Any]] = {
    "Windows 8.1": {
        "host_tier": "best-effort-source",
        "remote_target_tier": "supported",
        "score": 60.0,
        "status": "best-effort-source-host",
    },
    "Windows 8": {
        "host_tier": "legacy-source-only",
        "remote_target_tier": "supported",
        "score": 45.0,
        "status": "legacy-source-only",
    },
    "Windows 7": {
        "host_tier": "legacy-source-only",
        "remote_target_tier": "supported",
        "score": 45.0,
        "status": "legacy-source-only",
    },
    "Windows Vista": {
        "host_tier": "remote-target-only",
        "remote_target_tier": "supported",
        "score": 25.0,
        "status": "remote-target-only",
    },
    "Windows XP": {
        "host_tier": "remote-target-only",
        "remote_target_tier": "supported",
        "remote_target_coverage_percent": 100.0,
        "architectures": ["x86", "x64"],
        "security_profile": "isolated-legacy-opt-in",
        "score": 25.0,
        "status": "remote-target-only",
    },
}

REQUIRED_DOC_SNIPPETS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "Platform verified readiness is still separate and currently reports **100.0% overall**",
        "Windows XP/Vista/7/8 are supported as legacy remote targets, not as first-class",
        "Windows XP x86/x64 remote endpoints use isolated per-profile legacy opt-ins",
        "Linux `i386`/`i686` and `armhf` outputs for matching builders, but those are not uploaded",
        "manual Linux i386/armhf and legacy Windows rows remain visible outside the verified-readiness denominator",
        "`protected_readiness_goal` metadata block",
        "`not native-host/readiness proof`",
        "`configs/platform_verified_evidence.json`",
        "check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets",
        "release_asset_provenance_complete=false",
        "asset-backed protected goal gate",
        "check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
        "`linux_smoke_summary` carrying the native smoke release/run",
        "iOS/iPadOS is Web/PWA only; no native `.ipa` or App Store package is published.",
        "Android 12 through Android 16 (API 31-36)",
        "iOS/iPadOS 15 through 26.x",
    ),
    "docs/PLATFORM_SUPPORT.md": (
        "Architecture support is declared in `configs/platform_targets.json`",
        "`protected_readiness_goal`",
        "`static_catalog_boundary` of `not native-host/readiness proof`",
        "`status_source` pointing at `configs/platform_verified_evidence.json`",
        "`row platforms --json is the static platform catalog; use row features --coverage --json`",
        "`release_asset_provenance_gate`",
        "python scripts/check_platform_support_truth.py",
        "Evidence-backed protected readiness",
        "Release asset provenance",
        "static platform catalog is not native-host/readiness proof",
        "row features --coverage --json",
        "accepted records/release assets pending",
        "Windows Vista and Windows XP as remote targets only.",
        "Windows XP remote-target coverage is 100.0% for x86 and x64 endpoints",
        "i386/i686: 32-bit x86 Linux packages, script-supported only.",
        "armv7l/armhf: 32-bit ARM Linux packages, script-supported only.",
        "`dpkg --print-architecture`",
        "`getconf LONG_BIT=32`",
        "modern Windows 10/11, Linux and macOS defaults remain hardened",
        "`workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` matching `release_asset_source.head_sha`",
        "`git_worktree_clean=true`",
        "Linux smoke command includes the target id, workflow run URL, workflow run attempt and source head SHA",
        "observed Git HEAD SHA matches that source head SHA",
        "`linux_smoke_summary` that repeats the",
        "profile-only legacy crypto scope facts",
        "`scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`",
        "`scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`",
        "python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets",
        "A tag created before those workflows existed cannot be promoted",
        "python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>",
        "hash-checked as downloaded source artifacts before being copied into the release asset directory",
        "release_asset_provenance_complete=false",
        "asset-backed protected goal",
        "`record_complete`",
        "`release_backed_complete`",
        "`static_readiness_evidence_scope`",
        "`release_backed_readiness_complete=false`",
        "that strict verifier audits the intended already-published GitHub release",
        "published native/review-bundle asset bytes",
        "published final accepted-record JSON bytes",
        "`workflow_run.repository_id` and",
        "`workflow_run.head_repository_id`",
        "artifact `created_at` values outside the exact source run creation/start/update window",
        "canonical accepted-record JSON bytes",
        "native artifact SHA-256 plus review-bundle size/SHA-256 checks on the downloaded source artifact",
        "check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets",
        "`--host-label`, `--evidence-run-id` and `--observed-at-utc` command bindings",
        "`xp_evidence_summary.release_source` matching `release_asset_source`",
        "`--source-workflow-run-url`, `--source-head-sha` and `--source-run-attempt`",
        "`--os-name`, `--os-architecture`, `--os-service-pack` and required `--os-edition` command",
        "`xp smoke evidence run id`, `xp smoke observed at utc`",
        "`xp smoke source workflow run`",
        "`xp smoke source head sha`",
        "`xp smoke source run attempt`",
        "`xp smoke os name`, `xp smoke os architecture`, `xp smoke os service pack`, required",
        "`xp smoke host probe command`, `xp smoke host probe",
        "`xp smoke processor architecture env`, `xp smoke processor",
        "`xp smoke wmic os caption`",
        "`xp smoke wmic os csdversion`",
        "APK-style artifacts remain out of scope until there is a real native Android wrapper.",
        "iOS/iPadOS support is Web/PWA only; no native `.ipa` artifact is published.",
    ),
    "docs/RELEASE_STRATEGY.md": (
        "Linux `i386`/`i686` and `armv7l`/`armhf` native outputs are script-supported",
        "`dpkg --print-architecture` as `i386` or `armhf`",
        "`getconf LONG_BIT` as",
        "`linux_smoke_summary`",
        "weak crypto disabled by",
        "modern Windows 10/11,",
        "Treats Windows XP, Vista, Windows 7 and Windows 8.0 as legacy remote targets",
        "Windows XP x86/x64 remote endpoints use isolated per-profile legacy opt-ins",
        "`xp_evidence_summary.release_source` matching `release_asset_source`",
        "`xp smoke source head sha`",
        "downloaded source artifact native artifact SHA-256 values plus review-bundle size/SHA-256 values",
        "artifact created_at inside the exact source run creation/start/update window",
        "python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets",
        "refuses release tags that do not contain the tagged project version",
        "check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
        "release_asset_provenance_complete=false",
        "asset-backed protected goal",
        "record_complete",
        "release_backed_complete",
        "Android remains Termux plus Web/PWA until there is a real native Android wrapper.",
        "iOS/iPadOS remains Web/PWA-only until there is a real native iOS wrapper.",
    ),
    "docs/FULL_FEATURE_COVERAGE.md": (
        "Platform verified readiness",
        "Platform verified readiness remains separate",
        "release_asset_provenance_complete=false",
        "record_complete",
        "release_backed_complete",
        "static_readiness_evidence_scope",
        "release_backed_readiness_complete=false",
        "release_asset_provenance_command",
        "remote_release_evidence_audit_command",
        "Release asset provenance",
        "Asset provenance gate",
        "Remote evidence audit",
        "live published",
        "accepted-record/release-asset provenance note",
        "asset-backed protected goal gate",
        "same-run-URL conflicting-attempt accepted records",
    ),
}

MISLEADING_PLATFORM_CLAIMS = (
    "8-bit support",
    "16-bit support",
    "128-bit support",
    "Windows XP native installer",
    "Windows Vista native installer",
    "Windows 7 native installer",
    "Windows 8 native installer",
    "Linux i386 default native",
    "Linux armhf default native",
    "APK is published",
    "IPA is published",
    "iOS native installer",
)

DYNAMIC_PROTECTED_GOAL_DOC_PATHS = (
    "README.md",
    "docs/PLATFORM_SUPPORT.md",
    "docs/FULL_FEATURE_COVERAGE.md",
)


def main() -> int:
    errors = check_platform_support_truth()
    if errors:
        for error in errors:
            print(f"platform support truth: {error}", file=sys.stderr)
        return 1
    print("platform support truth checks passed")
    return 0


def check_platform_support_truth(
    *,
    platform_targets: dict[str, Any] | None = None,
    release_matrix: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    docs: dict[str, str] | None = None,
) -> list[str]:
    platform_data = read_json(PLATFORM_TARGETS_PATH) if platform_targets is None else platform_targets
    matrix = read_json(RELEASE_MATRIX_PATH) if release_matrix is None else release_matrix
    coverage = coverage_report() if report is None else report
    doc_text = read_docs(REQUIRED_DOC_SNIPPETS) if docs is None else docs

    errors: list[str] = []
    errors.extend(check_platform_catalog(platform_data))
    errors.extend(check_release_matrix_alignment(platform_data, matrix))
    errors.extend(check_platform_readiness_report(platform_data, coverage))
    errors.extend(check_platform_docs(doc_text, coverage))
    return errors


def check_platform_catalog(platform_targets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = rows_by_key(platform_targets.get("release_architectures", []), "id", errors)
    legacy_rows = rows_by_key(platform_targets.get("windows_legacy_targets", []), "version", errors)
    errors.extend(
        check_protected_readiness_catalog_contract(
            platform_targets.get("protected_readiness_goal")
        )
    )

    for target_id, expected in EXPECTED_ARCHITECTURES.items():
        row = rows.get(target_id)
        if row is None:
            errors.append(f"missing platform architecture target: {target_id}")
            continue
        errors.extend(check_expected_fields(f"platform target {target_id}", row, expected))
        bits = row.get("bits")
        if bits not in (32, 64):
            errors.append(f"platform target {target_id} uses unsupported bit width: {bits}")
        if bits == 32 and "32-bit" not in searchable_target_text(row):
            errors.append(f"32-bit platform target {target_id} must explain 32-bit support boundaries")
        if not row.get("assets"):
            errors.append(f"platform target {target_id} must declare release assets")
        errors.extend(check_protected_linux_catalog_assets(target_id, row))

    for version, expected in EXPECTED_LEGACY_WINDOWS.items():
        row = legacy_rows.get(version)
        if row is None:
            errors.append(f"missing legacy Windows target: {version}")
            continue
        errors.extend(check_expected_fields(f"legacy Windows target {version}", row, expected))
        if "native" not in searchable_target_text(row).lower():
            errors.append(f"legacy Windows target {version} must explain native-host limits")
        if version == "Windows XP":
            protocols = set(row.get("supported_remote_protocols", []))
            for protocol in ("rdp", "vnc", "ssh", "sshv1", "telnet", "serial", "raw"):
                if protocol not in protocols:
                    errors.append(f"Windows XP remote target support must include {protocol}")

    return errors


def check_protected_linux_catalog_assets(target_id: str, row: dict[str, Any]) -> list[str]:
    expected_assets = PROTECTED_LINUX_CATALOG_ASSETS.get(target_id)
    if expected_assets is None:
        return []
    raw_assets = row.get("assets")
    if not isinstance(raw_assets, list):
        return [f"platform target {target_id} assets must be a list"]
    actual_assets = {str(asset) for asset in raw_assets}
    missing = sorted(expected_assets - actual_assets)
    if missing:
        return [
            f"platform target {target_id} assets must include protected promotion artifacts: {missing}"
        ]
    return []


def check_protected_readiness_catalog_contract(raw_goal: Any) -> list[str]:
    label = "platform protected_readiness_goal"
    if not isinstance(raw_goal, dict):
        return ["platform catalog must declare protected_readiness_goal contract"]

    errors: list[str] = []
    if raw_goal.get("required_targets") != PROTECTED_GOAL_TARGET_ORDER:
        errors.append(
            f"{label} required_targets must be {PROTECTED_GOAL_TARGET_ORDER!r}, "
            f"got {raw_goal.get('required_targets')!r}"
        )
    if raw_goal.get("status_source") != "configs/platform_verified_evidence.json":
        errors.append(f"{label} status_source must point at configs/platform_verified_evidence.json")

    boundary = normalize_text(str(raw_goal.get("static_catalog_boundary", "")))
    if boundary != "not native-host/readiness proof":
        errors.append(f"{label} static_catalog_boundary must be not native-host/readiness proof")

    guidance = normalize_text(str(raw_goal.get("static_json_consumer_guidance", "")))
    if "row platforms --json is the static platform catalog" not in guidance:
        errors.append(f"{label} guidance must say row platforms --json is the static catalog")
    if "row features --coverage --json" not in guidance:
        errors.append(f"{label} guidance must point to row features --coverage --json")

    for key, expected in PROTECTED_READINESS_GATE_COMMANDS.items():
        actual = normalize_command(str(raw_goal.get(key, "")))
        if actual != normalize_command(expected):
            errors.append(f"{label} {key} must be {expected!r}, got {raw_goal.get(key)!r}")

    sources = raw_goal.get("target_evidence_sources")
    if not isinstance(sources, dict):
        errors.append(f"{label} target_evidence_sources must be an object")
    else:
        actual_targets = set(str(target) for target in sources)
        if actual_targets != PROTECTED_GOAL_TARGETS:
            errors.append(
                f"{label} target_evidence_sources must cover exactly "
                f"{sorted(PROTECTED_GOAL_TARGETS)}, got {sorted(actual_targets)}"
            )
        for target, workflow in PROTECTED_RELEASE_SOURCE_WORKFLOWS.items():
            if sources.get(target) != workflow:
                errors.append(f"{label} evidence source for {target} must be {workflow}")

    security = raw_goal.get("security_boundary")
    if not isinstance(security, dict):
        errors.append(f"{label} security_boundary must be an object")
    else:
        expected_security = {
            "legacy_compatibility_profile": "isolated-opt-in",
            "legacy_crypto_scope": "profile-only",
            "weak_crypto_global_default": False,
            "modern_defaults_unchanged": True,
            "modern_tls_minimum": "TLS 1.2",
            "modern_tls_preferred": "TLS 1.3",
        }
        for key, expected in expected_security.items():
            if security.get(key) != expected:
                errors.append(f"{label} security_boundary.{key} must be {expected!r}")

    return errors


def check_release_matrix_alignment(platform_targets: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = rows_by_key(platform_targets.get("release_architectures", []), "id", errors)
    native_ids = {target_id for target_id, row in rows.items() if row.get("release_tier") == "native"}
    script_ids = {
        target_id
        for target_id, row in rows.items()
        if row.get("release_tier") == "script-supported-native"
    }
    web_release_ids = {
        target_id for target_id, row in rows.items() if row.get("release_tier") in {"termux-web", "web-pwa"}
    }

    default_ids: set[str] = set()
    native_jobs = matrix.get("default_github_release", {}).get("native_jobs", [])
    if not isinstance(native_jobs, list):
        errors.append("release matrix default_github_release.native_jobs must be a list")
    else:
        for index, job in enumerate(native_jobs):
            if not isinstance(job, dict):
                errors.append(
                    f"release matrix default_github_release.native_jobs[{index}] must be an object"
                )
                continue
            raw_job_name = job.get("job")
            job_name = (
                raw_job_name
                if isinstance(raw_job_name, str) and raw_job_name
                else f"default_github_release.native_jobs[{index}]"
            )
            default_ids.update(
                exact_string_set(
                    job.get("platform_target_ids", []),
                    f"release matrix {job_name} platform_target_ids",
                    errors,
                )
            )

    matrix_script_ids: set[str] = set()
    script_rows = matrix.get("script_supported_native", [])
    if not isinstance(script_rows, list):
        errors.append("release matrix script_supported_native must be a list")
    else:
        for index, item in enumerate(script_rows):
            if not isinstance(item, dict):
                errors.append(f"release matrix script_supported_native[{index}] must be an object")
                continue
            target_id = exact_string_value(
                item.get("platform_target_id"),
                f"release matrix script_supported_native[{index}].platform_target_id",
                errors,
            )
            if target_id:
                matrix_script_ids.add(target_id)

    matrix_web_release_ids: set[str] = set()
    matrix_legacy_versions: set[str] = set()
    source_rows = matrix.get("source_or_remote_only", [])
    if not isinstance(source_rows, list):
        errors.append("release matrix source_or_remote_only must be a list")
    else:
        for index, item in enumerate(source_rows):
            if not isinstance(item, dict):
                errors.append(f"release matrix source_or_remote_only[{index}] must be an object")
                continue
            matrix_web_release_ids.update(
                exact_string_set(
                    item.get("platform_target_ids", []),
                    f"release matrix source_or_remote_only[{index}].platform_target_ids",
                    errors,
                )
            )
            matrix_legacy_versions.update(
                exact_string_set(
                    item.get("windows_legacy_target_versions", []),
                    f"release matrix source_or_remote_only[{index}].windows_legacy_target_versions",
                    errors,
                )
            )

    if default_ids != native_ids:
        errors.append(
            "default native release targets must exactly match native platform targets "
            f"(expected {sorted(native_ids)}, got {sorted(default_ids)})"
        )
    if matrix_script_ids != script_ids:
        errors.append(
            "script-supported release targets must exactly match script-supported platform targets "
            f"(expected {sorted(script_ids)}, got {sorted(matrix_script_ids)})"
        )
    if matrix_web_release_ids != web_release_ids:
        errors.append(
            "mobile/Web release targets must exactly match termux-web and web-pwa platform targets "
            f"(expected {sorted(web_release_ids)}, got {sorted(matrix_web_release_ids)})"
        )
    legacy_versions = set(EXPECTED_LEGACY_WINDOWS)
    if matrix_legacy_versions != legacy_versions:
        errors.append(
            "legacy Windows release matrix targets must exactly match declared legacy Windows targets "
            f"(expected {sorted(legacy_versions)}, got {sorted(matrix_legacy_versions)})"
        )
    return errors


def exact_string_set(raw_values: Any, label: str, errors: list[str]) -> set[str]:
    if not isinstance(raw_values, list):
        errors.append(f"{label} must be a list")
        return set()
    values: set[str] = set()
    for index, raw_value in enumerate(raw_values):
        value = exact_string_value(raw_value, f"{label}[{index}]", errors)
        if value:
            values.add(value)
    return values


def exact_string_value(raw_value: Any, label: str, errors: list[str]) -> str:
    if not isinstance(raw_value, str) or not raw_value:
        errors.append(f"{label} must be a non-empty string, got {raw_value!r}")
        return ""
    if raw_value != raw_value.strip():
        errors.append(f"{label} must not include surrounding whitespace, got {raw_value!r}")
        return ""
    return raw_value


def check_platform_readiness_report(
    platform_targets: dict[str, Any],
    report: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    platform = report.get("platform_verified_readiness", {})
    target_rows = rows_by_key(platform.get("targets", []), "target", errors)
    expected_targets = {*EXPECTED_ARCHITECTURES, *EXPECTED_LEGACY_WINDOWS}
    actual_targets = set(target_rows)
    if actual_targets != expected_targets:
        errors.append(
            "platform readiness targets must match platform catalog "
            f"(expected {sorted(expected_targets)}, got {sorted(actual_targets)})"
        )

    for target_id, expected in EXPECTED_ARCHITECTURES.items():
        row = target_rows.get(target_id)
        if row is None:
            continue
        errors.extend(check_readiness_row(target_id, row, expected))
    for version, expected in EXPECTED_LEGACY_WINDOWS.items():
        row = target_rows.get(version)
        if row is None:
            continue
        errors.extend(check_readiness_row(version, row, expected))
        if row.get("remote_target_tier") != "supported":
            errors.append(f"{version} readiness row must keep remote_target_tier=supported")
        if version == "Windows XP":
            if row.get("remote_target_coverage_percent") != 100.0:
                errors.append("Windows XP readiness row must report 100.0% remote target coverage")
            if row.get("legacy_architectures") != ["x86", "x64"]:
                errors.append("Windows XP readiness row must report x86 and x64 legacy architectures")
            if row.get("security_profile") != "isolated-legacy-opt-in":
                errors.append("Windows XP readiness row must report isolated-legacy-opt-in security profile")

    expected_overall = expected_platform_overall(platform_targets)
    actual_overall = platform.get("overall", {}).get("current_percent")
    if actual_overall != expected_overall:
        errors.append(f"platform readiness overall must be {expected_overall}%, got {actual_overall}%")
    errors.extend(
        check_protected_readiness_report_alignment(
            platform_targets.get("protected_readiness_goal"),
            platform,
        )
    )
    return errors


def check_protected_readiness_report_alignment(
    raw_goal_contract: Any,
    platform_report: dict[str, Any],
) -> list[str]:
    if not isinstance(raw_goal_contract, dict):
        return []

    goal = platform_report.get("protected_goal_parity", {})
    if not isinstance(goal, dict):
        return ["platform readiness report must expose protected_goal_parity"]

    errors: list[str] = []
    required_targets = raw_goal_contract.get("required_targets")
    if goal.get("required_targets") != required_targets:
        errors.append(
            "protected platform goal report required_targets must match "
            f"platform catalog protected_readiness_goal (expected {required_targets!r}, "
            f"got {goal.get('required_targets')!r})"
        )
    if goal.get("target_count") != len(PROTECTED_GOAL_TARGET_ORDER):
        errors.append("protected platform goal report target_count must match catalog required targets")

    expected_asset_command = normalize_command(
        str(raw_goal_contract.get("release_asset_provenance_gate", ""))
    )
    actual_asset_command = normalize_command(
        release_tag_template_command(
            str(goal.get("release_asset_provenance_command", "")),
            str(goal.get("release_tag", "")),
        )
    )
    if actual_asset_command != expected_asset_command:
        errors.append(
            "protected platform goal report release_asset_provenance_command must match "
            "platform catalog release_asset_provenance_gate"
        )
    if goal.get("release_asset_provenance_complete") is not False:
        errors.append(
            "static protected platform goal report must keep "
            "release_asset_provenance_complete=false"
        )
    return errors


def check_platform_docs(docs: dict[str, str], report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = normalize_text(docs.get(path, ""))
        if not text:
            errors.append(f"missing platform support doc text: {path}")
            continue
        for snippet in snippets:
            if normalize_text(snippet) not in text:
                errors.append(f"{path} missing platform truth snippet: {snippet}")

    combined = normalize_text("\n".join(docs.values()))
    for claim in MISLEADING_PLATFORM_CLAIMS:
        if normalize_text(claim) in combined:
            errors.append(f"platform docs contain misleading support claim: {claim}")

    errors.extend(check_dynamic_protected_goal_docs(docs, report))

    full_coverage = docs.get("docs/FULL_FEATURE_COVERAGE.md", "")
    for row in report.get("platform_verified_readiness", {}).get("targets", []):
        expected = (
            f"| {row['target']} | {row['platform']} {row['cpu_arch']} | {row['channel']} | "
            f"{row['current_percent']:.1f}% | {row['gap_percent']:.1f}% | {row['status']} |"
        )
        if expected not in full_coverage:
            errors.append(f"docs/FULL_FEATURE_COVERAGE.md missing generated platform row: {expected}")
    overall = report.get("platform_verified_readiness", {}).get("overall", {})
    expected_overall = (
        f"| **Overall** | **{overall.get('product', 'Verified targets')}** | **mixed** | "
        f"**{overall.get('current_percent', 0.0):.1f}%** | "
        f"**{overall.get('gap_percent', 0.0):.1f}%** | **mixed readiness** |"
    )
    if expected_overall not in full_coverage:
        errors.append(f"docs/FULL_FEATURE_COVERAGE.md missing platform overall row: {expected_overall}")
    return errors


def check_dynamic_protected_goal_docs(
    docs: dict[str, str],
    report: dict[str, Any],
) -> list[str]:
    platform = report.get("platform_verified_readiness", {})
    goal = platform.get("protected_goal_parity", {}) if isinstance(platform, dict) else {}
    if not isinstance(goal, dict):
        return ["platform readiness report must expose protected_goal_parity for docs"]
    try:
        current_percent = float(goal.get("current_percent", 0.0))
    except (TypeError, ValueError):
        current_percent = 0.0
    status = str(goal.get("status", "unknown"))
    snippet = (
        f"Protected platform goal parity is **{current_percent:.1f}%** for the "
        f"current accepted-evidence registry (status={status})"
    )
    normalized_snippet = normalize_text(snippet)
    errors: list[str] = []
    for path in DYNAMIC_PROTECTED_GOAL_DOC_PATHS:
        if normalized_snippet not in normalize_text(docs.get(path, "")):
            errors.append(
                f"{path} missing current protected platform goal snippet: {snippet}"
            )
    return errors


def check_expected_fields(label: str, row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_value in expected.items():
        if key in {"score", "status"}:
            continue
        actual = row.get(key)
        if actual != expected_value:
            errors.append(f"{label} {key} must be {expected_value!r}, got {actual!r}")
    return errors


def check_readiness_row(target: str, row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    effective_expected, evidence_errors = evidence_adjusted_readiness_expectation(target, row, expected)
    errors.extend(evidence_errors)
    if row.get("current_percent") != effective_expected["score"]:
        errors.append(
            f"{target} readiness score must be {effective_expected['score']}%, "
            f"got {row.get('current_percent')}%"
        )
    if row.get("gap_percent") != round(100.0 - float(effective_expected["score"]), 1):
        errors.append(f"{target} readiness gap must match score {effective_expected['score']}%")
    if row.get("status") != effective_expected["status"]:
        errors.append(
            f"{target} readiness status must be {effective_expected['status']}, "
            f"got {row.get('status')}"
        )
    expected_scope = expected_verified_readiness_scope(effective_expected)
    if row.get("verified_readiness_scope") is not expected_scope:
        errors.append(
            f"{target} verified_readiness_scope must be {expected_scope}, "
            f"got {row.get('verified_readiness_scope')}"
        )
    if float(effective_expected["score"]) < 100.0 and row.get("status") == "verified-default-native":
        errors.append(f"{target} partial target must not report verified-default-native")
    return errors


def evidence_adjusted_readiness_expectation(
    target: str,
    row: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    if target in LINUX_PROTECTED_TARGETS:
        return linux_readiness_expectation(target, row, expected)
    if target == "Windows XP":
        return xp_readiness_expectation(row, expected)
    return expected, []


def linux_readiness_expectation(
    target: str,
    row: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    status = str(row.get("status", ""))
    has_accepted = accepted_evidence_lists_match(
        row,
        required_targets=[target],
        present_targets=[target],
        missing_targets=[],
    )
    if status != "verified-accepted-native-evidence" and not has_accepted:
        return expected, []

    promoted = {
        **expected,
        "score": 100.0,
        "status": "verified-accepted-native-evidence",
    }
    errors: list[str] = []
    if not has_accepted:
        errors.append(
            f"{target} evidence-backed readiness must expose accepted evidence "
            f"present={[target]!r} and missing=[]"
        )
    errors.extend(check_static_release_asset_provenance_fields(target, row, [target], [target]))
    errors.extend(check_release_binding_fields(target, row, [target]))
    return promoted, errors


def xp_readiness_expectation(
    row: dict[str, Any],
    expected: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    status = str(row.get("status", ""))
    present = accepted_evidence_values(row, "accepted_evidence_present_targets")
    has_xp_evidence = bool(set(present) & XP_PROTECTED_TARGETS)
    has_full_pair = accepted_evidence_lists_match(
        row,
        required_targets=XP_PROTECTED_TARGET_ORDER,
        present_targets=XP_PROTECTED_TARGET_ORDER,
        missing_targets=[],
    )
    if status not in {
        "verified-xp-native-host-evidence",
        "partial-xp-native-host-evidence",
    } and not has_xp_evidence:
        return expected, []

    if status == "verified-xp-native-host-evidence":
        promoted = {
            **expected,
            "score": 100.0,
            "status": "verified-xp-native-host-evidence",
        }
        errors: list[str] = []
        if not has_full_pair:
            errors.append(
                "Windows XP native-host readiness must expose accepted evidence "
                "for both XP x86 and XP x64 with no missing targets"
            )
        errors.extend(
            check_static_release_asset_provenance_fields(
                "Windows XP",
                row,
                XP_PROTECTED_TARGET_ORDER,
                XP_PROTECTED_TARGET_ORDER,
            )
        )
        errors.extend(check_release_binding_fields("Windows XP", row, XP_PROTECTED_TARGET_ORDER))
        return promoted, errors

    partial = {**expected, "status": "partial-xp-native-host-evidence"}
    errors = check_xp_partial_evidence_lists(row)
    present_targets = [target for target in XP_PROTECTED_TARGET_ORDER if target in set(present)]
    errors.extend(
        check_static_release_asset_provenance_fields(
            "Windows XP",
            row,
            XP_PROTECTED_TARGET_ORDER,
            present_targets,
        )
    )
    errors.extend(check_release_binding_fields("Windows XP", row, present_targets))
    return partial, errors


def check_xp_partial_evidence_lists(row: dict[str, Any]) -> list[str]:
    required = accepted_evidence_values(row, "accepted_evidence_required_targets")
    present = accepted_evidence_values(row, "accepted_evidence_present_targets")
    missing = accepted_evidence_values(row, "accepted_evidence_missing_targets")
    present_set = set(present)
    missing_set = set(missing)
    required_set = set(required)
    errors: list[str] = []
    if required_set != XP_PROTECTED_TARGETS:
        errors.append(
            "Windows XP partial native-host evidence must expose required XP x86/x64 targets"
        )
    if not present_set or not present_set.issubset(XP_PROTECTED_TARGETS):
        errors.append(
            "Windows XP partial native-host evidence must expose at least one accepted XP target"
        )
    if not missing_set.issubset(XP_PROTECTED_TARGETS):
        errors.append(
            "Windows XP partial native-host evidence missing targets must stay within XP x86/x64"
        )
    if required_set == XP_PROTECTED_TARGETS and present_set | missing_set != XP_PROTECTED_TARGETS:
        errors.append(
            "Windows XP partial native-host evidence present/missing targets must cover XP x86/x64"
        )
    return errors


def accepted_evidence_lists_match(
    row: dict[str, Any],
    *,
    required_targets: list[str],
    present_targets: list[str],
    missing_targets: list[str],
) -> bool:
    return (
        accepted_evidence_values(row, "accepted_evidence_required_targets") == required_targets
        and accepted_evidence_values(row, "accepted_evidence_present_targets") == present_targets
        and accepted_evidence_values(row, "accepted_evidence_missing_targets") == missing_targets
    )


def accepted_evidence_values(row: dict[str, Any], field: str) -> list[str]:
    raw = row.get(field)
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def check_release_binding_fields(
    row_label: str,
    row: dict[str, Any],
    targets: list[str],
) -> list[str]:
    if not targets:
        return []
    errors: list[str] = []
    tags = row.get("accepted_evidence_release_tags")
    repositories = row.get("accepted_evidence_release_repositories")
    heads = row.get("accepted_evidence_release_source_heads")
    attempts = row.get("accepted_evidence_release_source_run_attempts")
    workflows = row.get("accepted_evidence_release_source_workflows")
    for target in targets:
        if not isinstance(tags, dict) or not RELEASE_TAG_RE.fullmatch(str(tags.get(target, ""))):
            errors.append(f"{row_label} accepted evidence for {target} must expose a concrete release tag")
        raw_repositories = repositories.get(target) if isinstance(repositories, dict) else None
        if (
            not isinstance(raw_repositories, list)
            or len(raw_repositories) != 1
            or GITHUB_REPOSITORY_RE.fullmatch(str(raw_repositories[0])) is None
        ):
            errors.append(
                f"{row_label} accepted evidence for {target} must expose exactly one GitHub repository"
            )
        if not isinstance(heads, dict) or SOURCE_HEAD_RE.fullmatch(str(heads.get(target, ""))) is None:
            errors.append(f"{row_label} accepted evidence for {target} must expose a source head SHA")
        attempt = attempts.get(target) if isinstance(attempts, dict) else None
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            errors.append(
                f"{row_label} accepted evidence for {target} must expose a positive source run attempt"
            )
        expected_workflow = PROTECTED_RELEASE_SOURCE_WORKFLOWS[target]
        if not isinstance(workflows, dict) or workflows.get(target) != expected_workflow:
            errors.append(
                f"{row_label} accepted evidence for {target} must expose workflow {expected_workflow}"
            )
    return errors


def check_static_release_asset_provenance_fields(
    row_label: str,
    row: dict[str, Any],
    required_targets: list[str],
    present_targets: list[str],
) -> list[str]:
    record_complete = bool(required_targets) and sorted(required_targets) == sorted(present_targets)
    errors: list[str] = []
    if row.get("accepted_evidence_record_complete") is not record_complete:
        errors.append(
            f"{row_label} protected row accepted_evidence_record_complete must match "
            "accepted record target coverage"
        )
    if row.get("release_asset_provenance_complete") is not False:
        errors.append(
            f"{row_label} protected row must keep release_asset_provenance_complete=false "
            "in static readiness JSON"
        )
    if row.get("release_backed_readiness_complete") is not False:
        errors.append(
            f"{row_label} protected row must keep release_backed_readiness_complete=false "
            "in static readiness JSON"
        )
    scope = str(row.get("static_readiness_evidence_scope", ""))
    for snippet in ("accepted-record/source-run metadata only", "--require-complete", "--assets-dir"):
        if snippet not in scope:
            errors.append(
                f"{row_label} protected row static_readiness_evidence_scope must mention {snippet}"
            )
    return errors


def expected_platform_overall(platform_targets: dict[str, Any]) -> float:
    expected_scores: list[float] = []
    for item in platform_targets.get("release_architectures", []):
        expected = EXPECTED_ARCHITECTURES.get(str(item.get("id")))
        if expected and expected_verified_readiness_scope(expected):
            expected_scores.append(float(expected["score"]))
    for item in platform_targets.get("windows_legacy_targets", []):
        expected = EXPECTED_LEGACY_WINDOWS.get(str(item.get("version")))
        if expected and expected_verified_readiness_scope(expected):
            expected_scores.append(float(expected["score"]))
    if not expected_scores:
        return 0.0
    return round(sum(expected_scores) / len(expected_scores), 1)


def expected_verified_readiness_scope(expected: dict[str, Any]) -> bool:
    return str(expected.get("status", "")) in {
        "verified-default-native",
        "verified-accepted-native-evidence",
        "verified-xp-native-host-evidence",
        "verified-termux-web-mobile",
        "verified-ios-web-pwa",
    }


def rows_by_key(raw_rows: Any, key: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_rows, list):
        errors.append(f"platform support rows for {key} must be a list")
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in raw_rows:
        if not isinstance(item, dict):
            errors.append(f"platform support row for {key} must be an object")
            continue
        row_key = item.get(key, "")
        if not isinstance(row_key, str) or not row_key:
            errors.append(
                f"platform support row key {key} must be a non-empty string, "
                f"got {row_key!r}"
            )
            continue
        if row_key != row_key.strip():
            errors.append(
                f"platform support row key {key} must not include surrounding "
                f"whitespace, got {row_key!r}"
            )
            continue
        if row_key in rows:
            errors.append(f"duplicate platform support row: {row_key}")
            continue
        rows[row_key] = item
    return rows


def searchable_target_text(row: dict[str, Any]) -> str:
    parts = [str(row.get("host_support", ""))]
    parts.extend(str(item) for item in row.get("notes", []) if isinstance(item, str))
    return " ".join(parts)


def read_docs(required: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in required
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\|", "|")).strip()


def normalize_command(command: str) -> str:
    return re.sub(r"\s+", " ", command).strip()


def release_tag_template_command(command: str, release_tag: str) -> str:
    if RELEASE_TAG_RE.fullmatch(release_tag):
        return command.replace(f"--release-tag {release_tag}", "--release-tag v<project.version>")
    return command


def clone_json(data: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(data)


if __name__ == "__main__":
    raise SystemExit(main())
