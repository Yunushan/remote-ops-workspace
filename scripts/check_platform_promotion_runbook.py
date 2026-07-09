from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
XP_NATIVE_EVIDENCE_CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"
RUNBOOK_PATH = ROOT / "docs" / "PLATFORM_PROMOTION_RUNBOOK.md"

COMMON_SNIPPETS = (
    "python scripts/check_platform_parity_promotion.py",
    "python scripts/check_platform_verified_evidence.py",
    "python scripts/check_protected_platform_goal.py",
    "python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-records-complete",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag v<project.version>",
    "python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets",
    "python scripts/check_release_publish_assets.py",
    "python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets",
    "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> --release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>",
    "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir <bundle-dir> --require-goal-targets --release-tag v<project.version> --require-final-record-assets",
    "python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>",
    "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> --ref v<project.version>",
    "gh workflow run xp-native-evidence.yml --repo <owner>/<repo> --ref v<project.version>",
    "remote auditor's\n`--require-goal-targets` mode refuses weaker published-release audits",
    "release_asset_provenance_complete=false",
    "record_complete",
    "release_backed_complete",
    "asset-backed protected goal",
    "workflow file path\nmust match `release_asset_source.workflow`",
    "artifact inventory must be complete",
    "exactly one `release_asset_source.artifact_name` entry",
    "`workflow_run.id` and `workflow_run.head_sha`",
    "wrong-artifact-run, missing-artifact, expired-artifact or empty-artifact source",
    "same workflow run URL cannot carry conflicting local run attempts",
    "python scripts/make_extended_linux_evidence_bundle.py",
    "Linux evidence bundle output directory must include the target id and release tag as path segments",
    "python scripts/make_xp_native_evidence_bundle.py",
    "XP evidence bundle output directory must include the target id and release tag as path segments",
    "python scripts/check_platform_goal_local_evidence.py",
    "python scripts/make_platform_verified_evidence_record.py",
    "python scripts/finalize_platform_verified_evidence_record.py",
    "staged native artifacts and review-bundle files must match the finalized accepted record hashes",
    "staged upload output must re-check the exact root file set",
    "pre-copy SHA-256 for every staged file",
    "downloaded source artifact native artifact SHA-256 mismatches",
    "staged review bundle must re-finalize to the accepted record before upload",
    "`if-no-files-found: error`",
    "`include-hidden-files: false`",
    "`retention-days: 90`",
    "validated_commands` includes the candidate `local_evidence_preflight_command",
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
    "linux_smoke_summary",
    "builder-identity-<target>.json`, `native-smoke-<target>.log`, `platform-verified-evidence-<target>.json",
    "builder-identity",
    "python3 scripts/check_extended_platform_builder.py --target",
    "--release-tag v<project.version> --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --out",
    "workflow_ref",
    "workflow_sha",
    "source_head_sha",
    "observed_git_head_sha",
    "git_worktree_clean=true",
    "native_build_command",
    "native_smoke_command",
    "native installer smoke workflow run",
    "native installer smoke workflow run attempt",
    "native installer smoke source head sha",
    "native installer smoke git head sha",
    "native installer smoke builder evidence",
    "native installer smoke host label",
    "native installer smoke evidence run id",
    "native installer smoke observed at utc",
    "native installer smoke uname machine",
    "native installer smoke dpkg architecture",
    "native installer smoke userland bits: 32",
    "native installer smoke artifact sha256: <artifact> <sha256>",
    "native installer smoke security update channel: <security-update-channel>",
    "native installer smoke CVE review reference: <cve-review-reference>",
    "native installer smoke TLS minimum modern profiles: TLS 1.2",
    "native installer smoke TLS preferred modern profiles: TLS 1.3",
    "native installer smoke legacy compatibility profile: isolated-opt-in",
    "native installer smoke legacy crypto scope: profile-only",
    "native installer smoke weak crypto global default: false",
    "native installer smoke modern defaults unchanged: true",
    "--source-head-sha <github-actions-head-sha>",
    "--workflow-run-attempt <github-actions-run-attempt>",
    "--builder-evidence <builder-identity.json>",
    "scripts/make_linux_native.sh",
    "python scripts/stage_extended_linux_evidence_upload.py",
    "--linux-builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log>",
    "--linux-source-head-sha <github-actions-head-sha>",
    "--linux-source-run-attempt <github-actions-run-attempt>",
    "--local-evidence-root <staged-root>",
    "must contain only the expected release artifacts for strict promotion",
    "platform-evidence-upload/<target>/<release_tag>",
    "raw Linux builder output directories are not uploaded by wildcard",
)
XP_SNIPPETS = (
    "python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>",
    "--xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --xp-source-workflow-run-url <github-actions-run-url> --xp-source-head-sha <github-actions-head-sha> --xp-source-run-attempt <github-actions-run-attempt>",
    "--xp-evidence-dir",
    "--source-workflow-run-url <github-actions-run-url>",
    "`xp_evidence_summary.release_source`",
    "`xp smoke source head sha: <github-actions-head-sha>`",
    "cli_launch",
    "gui_or_legacy_host_ui_launch",
    "loopback_profile_dry_run",
    "artifact_manifest_validation",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "`legacy_crypto_profile_scoped` smoke file must include `legacy compatibility profile: isolated-opt-in`, `legacy crypto scope: profile-only`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`",
    "`modern_defaults_unchanged` smoke file must include `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`, `modern defaults unchanged: true`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`",
    "python scripts/stage_xp_native_evidence_upload.py",
    "platform-evidence-upload/<target>/<release_tag>",
    "raw operator-supplied XP artifact or evidence directories are not uploaded by wildcard",
    "assets_dir, evidence_file and evidence_dir dispatch inputs must be workspace-relative staged paths that include the target id and release tag as path segments",
    "artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag` and exactly one `--strict`",
    "artifact_validation.command --assets-dir` must match `<target-release-artifact-dir>`",
    "`host_identity`, `toolchain` and `security` exactly match the candidate `xp_evidence_summary`",
    "XP host requirement: Windows XP",
    "modern self-hosted `xp-evidence` collector with Python 3.12 and GitHub Actions support",
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
    promotion_data = read_json(PROMOTION_PATH) if promotion is None else promotion
    errors: list[str] = []
    if "# Platform Promotion Runbook" not in text:
        errors.append("docs/PLATFORM_PROMOTION_RUNBOOK.md must have a platform promotion title")
    for snippet in COMMON_SNIPPETS:
        if snippet not in text:
            errors.append(f"promotion runbook missing common snippet: {snippet}")
    if "<final-record.json>" in text:
        errors.append(
            "promotion runbook must not use generic <final-record.json>; "
            "use the release-scoped platform-verified-evidence-<target>-final.json"
        )

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
    for key, label in (
        ("artifact_validation_command", "artifact validation command"),
        ("native_evidence_validation_command", "native evidence validation command"),
        ("local_evidence_preflight_command", "local evidence preflight command"),
        ("accepted_evidence_candidate_command", "accepted evidence candidate command"),
        ("review_bundle_command", "review bundle command"),
        ("finalized_evidence_record_command", "finalized evidence record command"),
    ):
        command = str(requirements.get(key, ""))
        if command and command not in text:
            errors.append(f"{target_id} runbook missing {label}: {command}")
        if key == "finalized_evidence_record_command":
            expected_dir = (
                "<target-release-artifact-dir>"
                if target_id.startswith("linux-")
                else "<xp-evidence-output-dir>"
            )
            expected_output = f"--out {expected_dir}/platform-verified-evidence-{target_id}-final.json"
            if "<final-record.json>" in command:
                errors.append(
                    f"{target_id} finalized evidence record command must not use generic <final-record.json>"
                )
            if expected_output not in command:
                errors.append(
                    f"{target_id} finalized evidence record command must write {expected_output}"
                )
    smoke_script = str(requirements.get("smoke_script", ""))
    if smoke_script and smoke_script not in text:
        errors.append(f"{target_id} runbook missing smoke script: {smoke_script}")
    return errors


def check_linux_runbook(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for snippet in LINUX_SNIPPETS:
        if snippet not in text:
            errors.append(f"{target_id} runbook missing Linux snippet: {snippet}")
    dispatch_command = linux_dispatch_command(target_id)
    if dispatch_command not in text:
        errors.append(
            f"{target_id} runbook missing Linux workflow dispatch command: {dispatch_command}"
        )
    runner_evidence = str(requirements.get("workflow_runner_evidence", ""))
    if runner_evidence and runner_evidence not in text:
        errors.append(f"{target_id} runbook missing runner evidence: {runner_evidence}")
    candidate_name = f"platform-verified-evidence-{target_id}.json"
    if candidate_name not in text:
        errors.append(f"{target_id} runbook missing candidate evidence record: {candidate_name}")
    for item in requirements.get("security_requirements", []):
        if str(item) not in text:
            errors.append(f"{target_id} runbook missing security requirement: {item}")
    return errors


def check_xp_runbook(text: str, target_id: str, requirements: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for snippet in XP_SNIPPETS:
        if snippet not in text:
            errors.append(f"{target_id} runbook missing XP snippet: {snippet}")
    dispatch_command = xp_dispatch_command(target_id)
    if dispatch_command not in text:
        errors.append(f"{target_id} runbook missing XP workflow dispatch command: {dispatch_command}")
    xp_contract = read_json(XP_NATIVE_EVIDENCE_CONTRACT_PATH)
    xp_target_contract = xp_contract.get("targets", {}).get(target_id, {})
    if not isinstance(xp_target_contract, dict):
        xp_target_contract = {}
    architecture = str(xp_target_contract.get("architecture", "")).strip()
    service_pack = str(xp_target_contract.get("minimum_service_pack", "")).strip()
    required_edition = str(xp_target_contract.get("required_edition", "")).strip()
    os_edition_proof = f"`xp smoke os edition: {required_edition}`, " if required_edition else ""
    if target_id.endswith("x64"):
        host_probe_proof = (
            "`xp smoke host probe command: ver`, "
            "`xp smoke host probe output: Microsoft Windows [Version 5.2.3790]`, "
            "`xp smoke processor architecture env: AMD64`, "
            "`xp smoke processor architecture w6432 env: <empty-or-AMD64>`, "
            "`xp smoke wmic os caption: Microsoft Windows XP Professional x64 Edition`, "
            "`xp smoke wmic os csdversion: Service Pack 2`, "
        )
    else:
        host_probe_proof = (
            "`xp smoke host probe command: ver`, "
            "`xp smoke host probe output: Microsoft Windows XP [Version 5.1.2600]`, "
            "`xp smoke processor architecture env: x86`, "
            "`xp smoke processor architecture w6432 env: <empty>`, "
            "`xp smoke wmic os caption: Microsoft Windows XP <edition>`, "
            "`xp smoke wmic os csdversion: Service Pack 3`, "
        )
    expected_proof_line = (
        f"Every smoke evidence file must include `xp smoke target: {target_id}`, "
        "`xp smoke release: v<project.version>`, `xp smoke id: <smoke_id>`, "
        f"`xp smoke os name: Windows XP`, `xp smoke os architecture: {architecture}`, "
        f"`xp smoke os service pack: {service_pack}`, "
        + os_edition_proof
        + host_probe_proof
        + "`xp smoke host label: <host_label>`, "
        "`xp smoke evidence run id: <evidence_run_id>`, "
        "`xp smoke observed at utc: <observed_at_utc>`, "
        "`xp smoke source workflow run: <github-actions-run-url>`, "
        "`xp smoke source head sha: <github-actions-head-sha>` and "
        "`xp smoke source run attempt: <github-actions-run-attempt>`."
    )
    if expected_proof_line not in text:
        errors.append(f"{target_id} runbook missing XP smoke OS and host identity proof line")
    runner = str(requirements.get("xp_vm_or_self_hosted_runner", ""))
    if runner and runner not in text:
        errors.append(f"{target_id} runbook missing XP runner requirement: {runner}")
    source_workflow = str(requirements.get("release_source_workflow", ""))
    if source_workflow and source_workflow not in text:
        errors.append(f"{target_id} runbook missing XP release source workflow: {source_workflow}")
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


def linux_dispatch_command(target_id: str) -> str:
    return (
        "gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> "
        f"-f target={target_id} "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url>"
    )


def xp_dispatch_command(target_id: str) -> str:
    return (
        "gh workflow run xp-native-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> "
        f"-f target={target_id} "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url> "
        "-f assets_dir=<target-release-artifact-dir> "
        "-f evidence_file=<target-release-evidence.json> "
        "-f evidence_dir=<target-release-evidence-dir>"
    )


if __name__ == "__main__":
    raise SystemExit(main())
