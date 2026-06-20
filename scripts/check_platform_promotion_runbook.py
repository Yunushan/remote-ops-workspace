from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
RUNBOOK_PATH = ROOT / "docs" / "PLATFORM_PROMOTION_RUNBOOK.md"

COMMON_SNIPPETS = (
    "python scripts/check_platform_parity_promotion.py",
    "python scripts/check_platform_verified_evidence.py",
    "python scripts/check_protected_platform_goal.py",
    "python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --release-tag v<project.version>",
    "python scripts/check_release_publish_assets.py",
    "python scripts/check_release_publish_assets.py --require-platform-goal-targets",
    "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir>",
    "python scripts/make_extended_linux_evidence_bundle.py",
    "python scripts/make_xp_native_evidence_bundle.py",
    "python scripts/make_platform_verified_evidence_record.py",
    "python scripts/finalize_platform_verified_evidence_record.py",
    "--append-registry",
    "configs/platform_verified_evidence.json",
)
LINUX_SNIPPETS = (
    ".github/workflows/extended-platform-evidence.yml",
    "release_asset_base_url",
    "--builder-evidence",
    "--linux-smoke-evidence",
    "--smoke-evidence",
    "linux_smoke_evidence_sha256.native_smoke",
    "builder-identity",
    "python3 scripts/check_extended_platform_builder.py --target",
    "--release-tag v<project.version> --workflow-run-url <github-actions-run-url> --out",
    "native_build_command",
    "native_smoke_command",
    "native installer smoke workflow run",
    "scripts/make_linux_native.sh",
)
XP_SNIPPETS = (
    "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>",
    "--xp-evidence-dir",
    "cli_launch",
    "gui_or_legacy_host_ui_launch",
    "loopback_profile_dry_run",
    "artifact_manifest_validation",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
)
XP_X64_SNIPPETS = (
    "SP2",
    "Professional x64 Edition",
    "os.service_pack",
    "os.edition",
)


def main() -> int:
    errors = check_platform_promotion_runbook()
    if errors:
        for error in errors:
            print(f"platform promotion runbook: {error}", file=sys.stderr)
        return 1
    print("platform promotion runbook passed")
    return 0


def check_platform_promotion_runbook(
    *,
    runbook_text: str | None = None,
    promotion: dict[str, Any] | None = None,
) -> list[str]:
    text = runbook_text if runbook_text is not None else RUNBOOK_PATH.read_text(encoding="utf-8")
    promotion_data = promotion or read_json(PROMOTION_PATH)
    errors: list[str] = []
    if "# Platform Promotion Runbook" not in text:
        errors.append("docs/PLATFORM_PROMOTION_RUNBOOK.md must have a platform promotion title")
    for snippet in COMMON_SNIPPETS:
        if snippet not in text:
            errors.append(f"promotion runbook missing common snippet: {snippet}")

    protected = promotion_data.get("protected_targets")
    if not isinstance(protected, list) or not protected:
        return [*errors, "configs/platform_parity_promotion.json protected_targets must be a non-empty list"]
    for raw_target in protected:
        if not isinstance(raw_target, dict):
            errors.append("platform promotion protected target entries must be objects")
            continue
        errors.extend(check_target_section(text, raw_target))
    return errors


def check_target_section(text: str, target: dict[str, Any]) -> list[str]:
    target_id = str(target.get("id", ""))
    errors: list[str] = []
    if f"Target id: `{target_id}`" not in text:
        errors.append(f"promotion runbook missing target id section: {target_id}")
    for key in (
        "current_readiness_percent",
        "current_status",
        "target_readiness_percent",
    ):
        expected = str(target.get(key, ""))
        if expected and expected not in text:
            errors.append(f"{target_id} runbook missing {key}: {expected}")
    for blocker in target.get("current_blockers", []):
        if str(blocker) not in text:
            errors.append(f"{target_id} runbook missing blocker: {blocker}")
    requirements = target.get("promotion_to_100_requires", {})
    if not isinstance(requirements, dict):
        return [*errors, f"{target_id} promotion_to_100_requires must be an object"]
    errors.extend(check_required_artifacts(text, target_id, requirements))
    errors.extend(check_required_commands(text, target_id, requirements))
    if target_id.startswith("linux-"):
        errors.extend(check_linux_runbook(text, target_id, requirements))
    if target_id.startswith("windows-xp-native-"):
        errors.extend(check_xp_runbook(text, target_id, requirements))
    return errors


def check_required_artifacts(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    artifacts = requirements.get("required_artifacts", requirements.get("native_artifacts", []))
    if not isinstance(artifacts, list) or not artifacts:
        return [f"{target_id} runbook checker expected required artifacts"]
    errors: list[str] = []
    for artifact in artifacts:
        if str(artifact) not in text:
            errors.append(f"{target_id} runbook missing required artifact: {artifact}")
    return errors


def check_required_commands(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    artifact_command = str(requirements.get("artifact_validation_command", ""))
    if artifact_command and artifact_command not in text:
        errors.append(f"{target_id} runbook missing artifact validation command: {artifact_command}")
    evidence_command = str(requirements.get("native_evidence_validation_command", ""))
    if evidence_command and evidence_command not in text:
        errors.append(f"{target_id} runbook missing native evidence validation command: {evidence_command}")
    smoke_script = str(requirements.get("smoke_script", ""))
    if smoke_script and smoke_script not in text:
        errors.append(f"{target_id} runbook missing smoke script: {smoke_script}")
    return errors


def check_linux_runbook(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for snippet in LINUX_SNIPPETS:
        if snippet not in text:
            errors.append(f"{target_id} runbook missing Linux snippet: {snippet}")
    runner_evidence = str(requirements.get("workflow_runner_evidence", ""))
    if runner_evidence and runner_evidence not in text:
        errors.append(f"{target_id} runbook missing runner evidence: {runner_evidence}")
    candidate_name = f"platform-verified-evidence-{target_id}.json"
    if candidate_name not in text:
        errors.append(f"{target_id} runbook missing candidate evidence record: {candidate_name}")
    return errors


def check_xp_runbook(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for snippet in XP_SNIPPETS:
        if snippet not in text:
            errors.append(f"{target_id} runbook missing XP snippet: {snippet}")
    runner = str(requirements.get("xp_vm_or_self_hosted_runner", ""))
    if runner and runner not in text:
        errors.append(f"{target_id} runbook missing XP runner requirement: {runner}")
    if target_id.endswith("x64"):
        for snippet in XP_X64_SNIPPETS:
            if snippet not in text:
                errors.append(f"{target_id} runbook missing XP x64 snippet: {snippet}")
    if requirements.get("separate_legacy_toolchain") is True and "separate XP-capable legacy toolchain" not in text:
        errors.append(f"{target_id} runbook missing separate XP-capable legacy toolchain wording")
    for item in requirements.get("security_requirements", []):
        if str(item) not in text:
            errors.append(f"{target_id} runbook missing security requirement: {item}")
    return errors


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
