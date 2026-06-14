from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
XP_CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"

LINUX_TARGETS = {
    "linux-i386": {
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "artifact": "extended-linux-i386-native-evidence",
        "runner_labels": {"self-hosted", "linux", "i386"},
        "machine_names": {"i386", "i486", "i586", "i686", "x86"},
    },
    "linux-armhf": {
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "artifact": "extended-linux-armhf-native-evidence",
        "runner_labels": {"self-hosted", "linux", "armhf"},
        "machine_names": {"armv6l", "armv7l", "armv7hl", "armhf"},
    },
}
XP_TARGETS = {
    "windows-xp-native-x86": {"architecture": "x86"},
    "windows-xp-native-x64": {"architecture": "x64"},
}
KNOWN_TARGETS = {*LINUX_TARGETS, *XP_TARGETS}
REQUIRED_LINUX_CHECKS = {
    "builder_preflight",
    "native_build",
    "native_smoke",
    "artifact_validation",
    "release_asset_attachment",
}
REQUIRED_XP_CHECKS = {
    "xp_native_evidence_validation",
    "artifact_validation",
    "vm_or_host_smoke",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "release_asset_attachment",
}
REQUIRED_XP_SMOKE_IDS = {
    "cli_launch",
    "gui_or_legacy_host_ui_launch",
    "loopback_profile_dry_run",
    "artifact_manifest_validation",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
}
REQUIRED_XP_TOOLCHAIN_FLAGS = {
    "separate_legacy_toolchain": True,
    "current_python_pyqt6_stack": False,
}
REQUIRED_XP_SECURITY_FLAGS = {
    "legacy_crypto_profile_scoped": True,
    "modern_defaults_unchanged": True,
    "weak_crypto_global_default": False,
}
REQUIRED_LINUX_TOOLS = {
    "bash",
    "curl",
    "dpkg-deb",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
}
GITHUB_ACTIONS_RUN_RE = re.compile(r"^https://github\.com/([^/]+/[^/]+)/actions/runs/\d+/?$")
GITHUB_RELEASE_ASSET_RE = re.compile(
    r"^https://github\.com/([^/]+/[^/]+)/releases/download/(v\d+\.\d+\.\d+)/.+"
)


def main() -> int:
    errors = check_platform_verified_evidence()
    if errors:
        for error in errors:
            print(f"platform verified evidence: {error}", file=sys.stderr)
        return 1
    print("platform verified evidence checks passed")
    return 0


def check_platform_verified_evidence(
    *,
    registry: dict[str, Any] | None = None,
    promotion: dict[str, Any] | None = None,
) -> list[str]:
    registry_data = registry or read_json(EVIDENCE_PATH)
    promotion_data = promotion or read_json(PROMOTION_PATH)
    errors: list[str] = []
    errors.extend(check_schema(registry_data))
    if errors:
        return errors
    promotion_entries = promotion_entries_by_id(promotion_data, errors)
    promotion_hash = promotion_config_sha256(promotion_data)
    for entry in registry_data.get("accepted_evidence", []):
        if not isinstance(entry, dict):
            errors.append("accepted_evidence entries must be objects")
            continue
        target = str(entry.get("target", ""))
        if target in LINUX_TARGETS:
            errors.extend(check_linux_evidence(entry, promotion_entries, promotion_hash))
        elif target in XP_TARGETS:
            errors.extend(check_xp_evidence(entry, promotion_entries, promotion_hash))
        else:
            errors.append(f"accepted_evidence target is not protected: {target}")
    errors.extend(check_registry_consistency(registry_data))
    return errors


def check_schema(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("schema_version") != 1:
        errors.append("configs/platform_verified_evidence.json schema_version must be 1")
    policy = str(registry.get("policy", ""))
    if "Only accepted evidence records" not in policy:
        errors.append("platform verified evidence policy must explain accepted evidence records")
    if "SHA-256" not in policy:
        errors.append("platform verified evidence policy must require per-artifact SHA-256 digests")
    if "builder identity" not in policy:
        errors.append("platform verified evidence policy must require Linux builder identity evidence")
    if "builder identity SHA-256" not in policy:
        errors.append("platform verified evidence policy must require Linux builder identity SHA-256 binding")
    if "workflow dispatch inputs" not in policy:
        errors.append("platform verified evidence policy must require Linux workflow dispatch input binding")
    if "XP evidence bundle" not in policy:
        errors.append("platform verified evidence policy must require XP evidence bundle digests")
    if "XP evidence contract SHA-256" not in policy:
        errors.append("platform verified evidence policy must require XP evidence contract SHA-256 binding")
    if "XP evidence summary" not in policy:
        errors.append("platform verified evidence policy must require XP evidence summary binding")
    if "promotion config SHA-256" not in policy:
        errors.append("platform verified evidence policy must require promotion config SHA-256 binding")
    if "unique target" not in policy:
        errors.append("platform verified evidence policy must require unique target records")
    if "same release_tag" not in policy:
        errors.append("platform verified evidence policy must require same release_tag for XP pairs")
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
) -> list[str]:
    target = str(entry.get("target", ""))
    expected = LINUX_TARGETS[target]
    errors = check_common_evidence(entry, target, REQUIRED_LINUX_CHECKS, promotion_entries, promotion_hash)
    if entry.get("evidence_type") != "extended-linux-native":
        errors.append(f"{target} evidence_type must be extended-linux-native")
    if entry.get("workflow") != expected["workflow"]:
        errors.append(f"{target} workflow must be {expected['workflow']}")
    errors.extend(check_linux_workflow_inputs(target, entry))
    workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(str(entry.get("workflow_run_url", "")))
    if not workflow_match:
        errors.append(f"{target} workflow_run_url must be a GitHub Actions run URL")
    else:
        release_repositories = release_asset_repositories(entry.get("release_asset_urls"))
        workflow_repository = workflow_match.group(1)
        if release_repositories and release_repositories != {workflow_repository}:
            errors.append(
                f"{target} workflow_run_url repository must match release asset repository "
                f"{sorted(release_repositories)}, got {workflow_repository}"
            )
    if entry.get("artifact_name") != expected["artifact"]:
        errors.append(f"{target} artifact_name must be {expected['artifact']}")
    labels = set(str(label) for label in entry.get("runner_labels", []))
    if not expected["runner_labels"].issubset(labels):
        errors.append(f"{target} runner_labels must include {sorted(expected['runner_labels'])}")
    errors.extend(check_linux_builder_identity(target, entry.get("builder_identity"), expected["machine_names"]))
    errors.extend(check_linux_builder_identity_sha256(target, entry))
    return errors


def check_linux_workflow_inputs(target: str, entry: dict[str, Any]) -> list[str]:
    raw_inputs = entry.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        return [f"{target} evidence must include workflow_inputs object"]
    errors: list[str] = []
    release_tag = str(entry.get("release_tag", ""))
    if raw_inputs.get("target") != target:
        errors.append(f"{target} workflow_inputs target must be {target}")
    if raw_inputs.get("release_tag") != release_tag:
        errors.append(f"{target} workflow_inputs release_tag must match record release_tag {release_tag}")
    base_url = str(raw_inputs.get("release_asset_base_url", "")).rstrip("/")
    expected_suffix = f"/releases/download/{release_tag}"
    if not base_url.startswith("https://github.com/") or not base_url.endswith(expected_suffix):
        errors.append(
            f"{target} workflow_inputs release_asset_base_url must be a GitHub release download URL "
            f"ending in {expected_suffix}"
        )
    release_assets = entry.get("release_asset_urls")
    if isinstance(release_assets, list) and base_url:
        if any(not str(url).startswith(f"{base_url}/") for url in release_assets):
            errors.append(f"{target} workflow_inputs release_asset_base_url must prefix every release_asset_url")
    return errors


def check_linux_builder_identity_sha256(target: str, entry: dict[str, Any]) -> list[str]:
    raw_identity = entry.get("builder_identity")
    digest = str(entry.get("builder_identity_sha256", ""))
    errors: list[str] = []
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"{target} builder_identity_sha256 must be a SHA-256 hex digest")
        return errors
    if not isinstance(raw_identity, dict):
        return errors
    if digest != json_sha256(raw_identity):
        errors.append(f"{target} builder_identity_sha256 must match builder_identity JSON SHA-256")
    return errors


def check_linux_builder_identity(target: str, raw_identity: Any, expected_machines: set[str]) -> list[str]:
    if not isinstance(raw_identity, dict):
        return [f"{target} evidence must include builder_identity object"]
    errors: list[str] = []
    if raw_identity.get("schema_version") != 1:
        errors.append(f"{target} builder_identity schema_version must be 1")
    if raw_identity.get("target") != target:
        errors.append(f"{target} builder_identity target must be {target}")
    sys_platform = str(raw_identity.get("sys_platform", ""))
    if not sys_platform.startswith("linux"):
        errors.append(f"{target} builder_identity sys_platform must start with linux")
    for key in ("platform_machine", "uname_machine"):
        value = str(raw_identity.get(key, "")).lower()
        if value not in expected_machines:
            errors.append(f"{target} builder_identity {key} must be one of {sorted(expected_machines)}, got {value!r}")
    version = python_version_tuple(str(raw_identity.get("python_version", "")))
    if version < (3, 10):
        errors.append(f"{target} builder_identity python_version must be 3.10 or newer")
    tools = raw_identity.get("required_tools")
    if not isinstance(tools, dict):
        errors.append(f"{target} builder_identity required_tools must be an object")
    else:
        missing_tools = sorted(tool for tool in REQUIRED_LINUX_TOOLS if not str(tools.get(tool, "")).strip())
        if missing_tools:
            errors.append(f"{target} builder_identity missing required tool paths: {missing_tools}")
    return errors


def python_version_tuple(version: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version)
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def check_xp_evidence(
    entry: dict[str, Any],
    promotion_entries: dict[str, dict[str, Any]],
    promotion_hash: str,
) -> list[str]:
    target = str(entry.get("target", ""))
    expected = XP_TARGETS[target]
    errors = check_common_evidence(entry, target, REQUIRED_XP_CHECKS, promotion_entries, promotion_hash)
    if entry.get("evidence_type") != "windows-xp-native-host":
        errors.append(f"{target} evidence_type must be windows-xp-native-host")
    if entry.get("architecture") != expected["architecture"]:
        errors.append(f"{target} architecture must be {expected['architecture']}")
    command = str(entry.get("native_evidence_validation_command", ""))
    expected_command = (
        "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>"
    )
    if command != expected_command:
        errors.append(f"{target} native_evidence_validation_command must be {expected_command!r}")
    if entry.get("separate_legacy_toolchain") is not True:
        errors.append(f"{target} separate_legacy_toolchain must be true")
    if entry.get("current_python_pyqt6_stack") is not False:
        errors.append(f"{target} current_python_pyqt6_stack must be false")
    evidence_sha = str(entry.get("xp_evidence_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha):
        errors.append(f"{target} xp_evidence_sha256 must be a SHA-256 hex digest")
    contract_sha = str(entry.get("xp_evidence_contract_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", contract_sha):
        errors.append(f"{target} xp_evidence_contract_sha256 must be a SHA-256 hex digest")
    elif contract_sha != xp_native_evidence_contract_sha256():
        errors.append(f"{target} xp_evidence_contract_sha256 must match current XP evidence contract SHA-256")
    errors.extend(check_xp_evidence_summary(target, str(entry.get("release_tag", "")), entry.get("xp_evidence_summary")))
    errors.extend(check_xp_smoke_evidence_hashes(target, entry.get("xp_smoke_evidence_sha256")))
    return errors


def check_xp_evidence_summary(target: str, release_tag: str, raw_summary: Any) -> list[str]:
    if not isinstance(raw_summary, dict):
        return [f"{target} xp_evidence_summary must be an object"]
    errors: list[str] = []
    if raw_summary.get("target") != target:
        errors.append(f"{target} xp_evidence_summary target must be {target}")
    if raw_summary.get("release_tag") != release_tag:
        errors.append(f"{target} xp_evidence_summary release_tag must match record release_tag {release_tag}")

    os_data = raw_summary.get("os")
    if not isinstance(os_data, dict):
        errors.append(f"{target} xp_evidence_summary os must be an object")
    else:
        if os_data.get("name") != "Windows XP":
            errors.append(f"{target} xp_evidence_summary os.name must be Windows XP")
        if os_data.get("architecture") != XP_TARGETS[target]["architecture"]:
            errors.append(f"{target} xp_evidence_summary os.architecture must be {XP_TARGETS[target]['architecture']}")
        if not str(os_data.get("service_pack", "")).strip():
            errors.append(f"{target} xp_evidence_summary os.service_pack must be set")

    toolchain = raw_summary.get("toolchain")
    if not isinstance(toolchain, dict):
        errors.append(f"{target} xp_evidence_summary toolchain must be an object")
    else:
        for flag, expected in sorted(REQUIRED_XP_TOOLCHAIN_FLAGS.items()):
            if toolchain.get(flag) is not expected:
                errors.append(f"{target} xp_evidence_summary toolchain.{flag} must be {str(expected).lower()}")

    security = raw_summary.get("security")
    if not isinstance(security, dict):
        errors.append(f"{target} xp_evidence_summary security must be an object")
    else:
        for flag, expected in sorted(REQUIRED_XP_SECURITY_FLAGS.items()):
            if security.get(flag) is not expected:
                errors.append(f"{target} xp_evidence_summary security.{flag} must be {str(expected).lower()}")

    smoke_ids = raw_summary.get("smoke_ids")
    if not isinstance(smoke_ids, list):
        errors.append(f"{target} xp_evidence_summary smoke_ids must be a list")
    else:
        actual = {str(smoke_id) for smoke_id in smoke_ids}
        missing = sorted(REQUIRED_XP_SMOKE_IDS - actual)
        unexpected = sorted(actual - REQUIRED_XP_SMOKE_IDS)
        if missing:
            errors.append(f"{target} xp_evidence_summary smoke_ids missing: {missing}")
        if unexpected:
            errors.append(f"{target} xp_evidence_summary smoke_ids unexpected: {unexpected}")
    return errors


def check_xp_smoke_evidence_hashes(target: str, raw_hashes: Any) -> list[str]:
    if not isinstance(raw_hashes, dict):
        return [f"{target} xp_smoke_evidence_sha256 must be an object"]
    errors: list[str] = []
    hashes = {str(name): str(value) for name, value in raw_hashes.items()}
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


def check_common_evidence(
    entry: dict[str, Any],
    target: str,
    required_checks: set[str],
    promotion_entries: dict[str, dict[str, Any]],
    promotion_hash: str,
) -> list[str]:
    errors: list[str] = []
    if entry.get("status") != "accepted":
        errors.append(f"{target} evidence status must be accepted")
    if entry.get("readiness_percent") != 100.0:
        errors.append(f"{target} evidence readiness_percent must be 100.0")
    release_tag = str(entry.get("release_tag", ""))
    if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
        errors.append(f"{target} release_tag must look like vX.Y.Z")
    checks = set(str(check) for check in entry.get("checks", []))
    missing_checks = sorted(required_checks - checks)
    if missing_checks:
        errors.append(f"{target} evidence missing required checks: {missing_checks}")
    command = str(entry.get("artifact_validation_command", ""))
    errors.extend(check_artifact_validation_command(target, release_tag, command))
    promotion_config_sha = str(entry.get("promotion_config_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", promotion_config_sha):
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
            url_text = str(url)
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
            filename = Path(url_text).name
            actual_names.add(filename)
            asset_name_counts[filename] = asset_name_counts.get(filename, 0) + 1
        if len(release_repositories) > 1:
            errors.append(
                f"{target} release asset URLs must use one GitHub repository, got {sorted(release_repositories)}"
            )
        duplicate_assets = sorted(name for name, count in asset_name_counts.items() if count > 1)
        if duplicate_assets:
            errors.append(f"{target} release asset URLs contain duplicate files: {duplicate_assets}")
        unexpected_assets = sorted(actual_names - expected_artifact_names)
        if unexpected_assets:
            errors.append(f"{target} release asset URLs reference unexpected files: {unexpected_assets}")
        missing_assets = sorted(expected_artifact_names - actual_names)
        if missing_assets:
            errors.append(f"{target} evidence missing release asset URLs for: {missing_assets}")
    return errors


def release_asset_repositories(raw_assets: Any) -> set[str]:
    if not isinstance(raw_assets, list):
        return set()
    repositories: set[str] = set()
    for url in raw_assets:
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(str(url))
        if match:
            repositories.add(match.group(1))
    return repositories


def check_artifact_validation_command(target: str, release_tag: str, command: str) -> list[str]:
    expected_prefix = f"python scripts/check_platform_promotion_artifacts.py --target {target} "
    errors: list[str] = []
    if not command.startswith(expected_prefix):
        errors.append(f"{target} artifact_validation_command must start with {expected_prefix!r}")
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    if tags != [release_tag]:
        errors.append(
            f"{target} artifact_validation_command must include exactly one --tag {release_tag}, got {tags}"
        )
    return errors


def check_artifact_sha256(target: str, raw_hashes: Any, expected_artifact_names: set[str]) -> list[str]:
    if not isinstance(raw_hashes, dict):
        return [f"{target} evidence must include artifact_sha256 map"]
    errors: list[str] = []
    hashes = {str(name): str(value) for name, value in raw_hashes.items()}
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


def check_registry_consistency(registry: dict[str, Any]) -> list[str]:
    rows = registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    errors: list[str] = []
    by_target: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target", ""))
        if target:
            by_target.setdefault(target, []).append(item)
    for target, entries in sorted(by_target.items()):
        if len(entries) > 1:
            errors.append(f"accepted_evidence target must be unique: {target}")

    xp_entries = {
        target: entries[0]
        for target, entries in by_target.items()
        if target in XP_TARGETS and len(entries) == 1
    }
    if set(XP_TARGETS).issubset(xp_entries):
        release_tags = {str(entry.get("release_tag", "")) for entry in xp_entries.values()}
        if len(release_tags) != 1:
            errors.append(
                "Windows XP native evidence pair must use one release_tag, "
                f"got {sorted(release_tags)}"
            )
    return errors


def promotion_entries_by_id(
    promotion: dict[str, Any],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for item in promotion.get("protected_targets", []):
        if not isinstance(item, dict):
            errors.append("promotion protected target entries must be objects")
            continue
        target = str(item.get("id", ""))
        if target:
            entries[target] = item
    missing = sorted(KNOWN_TARGETS - set(entries))
    if missing:
        errors.append(f"promotion config missing protected target entries: {missing}")
    return entries


def promotion_config_sha256(promotion: dict[str, Any]) -> str:
    return json_sha256(promotion)


def xp_native_evidence_contract_sha256() -> str:
    return json_sha256(read_json(XP_CONTRACT_PATH))


def json_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
