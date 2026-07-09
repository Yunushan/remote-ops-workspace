from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_platform_promotion_runbook_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_platform_promotion_runbook_uses_explicit_empty_promotion() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion={})

    assert "configs/platform_parity_promotion.json protected_targets must be a non-empty list" in errors


def test_platform_promotion_runbook_rejects_missing_target_id() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace("Target id: `linux-i386`", "Target id: `linux-i386-missing`")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "promotion runbook missing target id section: linux-i386" in errors


def test_platform_promotion_runbook_rejects_missing_blocker() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    blocker = promotion["protected_targets"][0]["current_blockers"][0]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(blocker, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing blocker: {blocker}" in errors


def test_platform_promotion_runbook_requires_protected_goal_gate() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/check_protected_platform_goal.py",
        "python scripts/removed_protected_platform_goal.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("check_protected_platform_goal.py" in error for error in errors)


def test_platform_promotion_runbook_requires_bundle_backed_strict_verify() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        (
            "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets "
            "--release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> "
            "--release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>"
        ),
        "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--platform-review-bundle-dir <bundle-dir>" in error for error in errors)
    assert any("--release-assets-dir <release-assets-dir>" in error for error in errors)
    assert any("--release-repository <owner>/<repo>" in error for error in errors)


def test_platform_promotion_runbook_requires_asset_backed_strict_publish() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        (
            "python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> "
            "--tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets"
        ),
        "python scripts/check_release_publish_assets.py --require-platform-goal-targets",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--assets-dir <release-assets-dir>" in error for error in errors)
    assert any("--tag v<project.version>" in error for error in errors)
    assert any("--repository <owner>/<repo>" in error for error in errors)


def test_platform_promotion_runbook_requires_strict_verify_import_dry_run() -> None:
    checker = _load_checker()
    command = (
        "python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> "
        "--require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run "
        "--repository <owner>/<repo>"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        command,
        "python scripts/import_platform_evidence_artifacts.py --dry-run",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--release-tag v<project.version>" in error for error in errors)
    assert any("--require-goal-targets" in error for error in errors)
    assert any("--out-dir <release-assets-dir>" in error for error in errors)
    assert any("--verify-source-run" in error for error in errors)


def test_platform_promotion_runbook_requires_live_release_repository_verify() -> None:
    checker = _load_checker()
    command = (
        "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets "
        "--release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> "
        "--release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        command,
        "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets "
        "--release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> "
        "--release-assets-dir <release-assets-dir>",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--release-repository <owner>/<repo>" in error for error in errors)


def test_platform_promotion_runbook_requires_published_release_audit_command() -> None:
    checker = _load_checker()
    command = (
        "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> "
        "--release-tag v<project.version> --require-goal-targets --require-source-runs "
        "--require-source-artifact-bytes --require-final-record-bytes "
        "--require-release-asset-bytes --require-tag-source-head"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        command,
        "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo>",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--release-tag v<project.version>" in error for error in errors)
    assert any("--require-source-runs" in error for error in errors)
    assert any("--require-source-artifact-bytes" in error for error in errors)
    assert any("--require-final-record-bytes" in error for error in errors)
    assert any("--require-release-asset-bytes" in error for error in errors)
    assert any("--require-tag-source-head" in error for error in errors)


def test_platform_promotion_runbook_requires_evidence_workflow_dispatch_commands() -> None:
    checker = _load_checker()
    text = (
        Path("docs/PLATFORM_PROMOTION_RUNBOOK.md")
        .read_text(encoding="utf-8")
        .replace("gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> --ref v<project.version>", "")
        .replace("gh workflow run xp-native-evidence.yml --repo <owner>/<repo> --ref v<project.version>", "")
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("gh workflow run extended-platform-evidence.yml" in error for error in errors)
    assert any("gh workflow run xp-native-evidence.yml" in error for error in errors)


def test_platform_promotion_runbook_requires_source_ref_gate_before_dispatch() -> None:
    checker = _load_checker()
    command = (
        "python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> "
        "--release-tag v<project.version> --require-goal-targets"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        command,
        "python scripts/check_platform_evidence_source_ref.py --help",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("check_platform_evidence_source_ref.py" in error for error in errors)
    assert any("--require-goal-targets" in error for error in errors)


def test_platform_promotion_runbook_requires_remote_audit_fail_closed_note() -> None:
    checker = _load_checker()
    snippet = (
        "remote auditor's\n"
        "`--require-goal-targets` mode refuses weaker published-release audits"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        snippet,
        "`--require-goal-targets` mode checks release assets",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("weaker published-release audits" in error for error in errors)


def test_platform_promotion_runbook_requires_staged_upload_hash_binding() -> None:
    checker = _load_checker()
    snippet = "staged native artifacts and review-bundle files must match the finalized accepted record hashes"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("finalized accepted record hashes" in error for error in errors)


def test_platform_promotion_runbook_requires_downloaded_source_hash_preflight() -> None:
    checker = _load_checker()
    snippet = "downloaded source artifact native artifact SHA-256 mismatches"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("downloaded source artifact native artifact SHA-256 mismatches" in error for error in errors)


def test_platform_promotion_runbook_requires_staged_review_bundle_refinalization() -> None:
    checker = _load_checker()
    snippet = "staged review bundle must re-finalize to the accepted record before upload"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("re-finalize to the accepted record before upload" in error for error in errors)


def test_platform_promotion_runbook_requires_final_record_asset_bundle_validation() -> None:
    checker = _load_checker()
    command = (
        "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir <bundle-dir> "
        "--require-goal-targets --release-tag v<project.version> --require-final-record-assets"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        command,
        command.replace(" --require-final-record-assets", ""),
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--require-final-record-assets" in error for error in errors)


def test_platform_promotion_runbook_requires_target_release_scoped_bundle_outputs() -> None:
    checker = _load_checker()
    linux_snippet = "Linux evidence bundle output directory must include the target id and release tag as path segments"
    xp_snippet = "XP evidence bundle output directory must include the target id and release tag as path segments"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace(linux_snippet, "Linux evidence bundle output directory must be plain")
    text = text.replace(xp_snippet, "XP evidence bundle output directory must be plain")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any(linux_snippet in error for error in errors)
    assert any(xp_snippet in error for error in errors)


def test_platform_promotion_runbook_rejects_generic_final_record_placeholder() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    target = "linux-i386"
    exact = f"<target-release-artifact-dir>/platform-verified-evidence-{target}-final.json"
    stale = "<final-record.json>"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(exact, stale)
    for item in promotion["protected_targets"]:
        if item["id"] == target:
            requirements = item["promotion_to_100_requires"]
            requirements["finalized_evidence_record_command"] = requirements[
                "finalized_evidence_record_command"
            ].replace(exact, stale)

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert any("must not use generic <final-record.json>" in error for error in errors)
    assert any(
        f"{target} finalized evidence record command must write --out {exact}" in error
        for error in errors
    )


def test_platform_promotion_runbook_requires_local_goal_preflight() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/check_platform_goal_local_evidence.py",
        "python scripts/removed.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("check_platform_goal_local_evidence.py" in error for error in errors)


def test_platform_promotion_runbook_requires_local_preflight_attempt_conflict_boundary() -> None:
    checker = _load_checker()
    snippet = "same workflow run URL cannot carry conflicting local run attempts"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    assert snippet in text
    text = text.replace(
        snippet,
        "same workflow run URL can carry separate local run attempts",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("conflicting local run attempts" in error for error in errors)


def test_platform_promotion_runbook_requires_xp_x64_edition_evidence() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "Professional x64 Edition",
        "x64",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "windows-xp-native-x64 runbook missing XP x64 snippet: Professional x64 Edition" in errors


def test_platform_promotion_runbook_requires_xp_source_workflow() -> None:
    checker = _load_checker()
    workflow = ".github/workflows/xp-native-evidence.yml"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(workflow, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert f"windows-xp-native-x86 runbook missing XP release source workflow: {workflow}" in errors


def test_platform_promotion_runbook_requires_xp_host_collector_boundary() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace("XP host requirement: Windows XP", "XP host requirement removed")
    text = text.replace(
        "modern self-hosted `xp-evidence` collector with Python 3.12 and GitHub Actions support",
        "XP runner",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("XP host requirement" in error for error in errors)
    assert any("xp-evidence" in error and "collector" in error for error in errors)


def test_platform_promotion_runbook_requires_xp_scoped_upload_staging() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/stage_xp_native_evidence_upload.py",
        "python scripts/removed.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("stage_xp_native_evidence_upload.py" in error for error in errors)


def test_platform_promotion_runbook_requires_target_dispatch_commands() -> None:
    checker = _load_checker()
    linux_command = (
        "gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> -f target=linux-i386 "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url>"
    )
    xp_command = (
        "gh workflow run xp-native-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> -f target=windows-xp-native-x86 "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url> "
        "-f assets_dir=<target-release-artifact-dir> "
        "-f evidence_file=<target-release-evidence.json> "
        "-f evidence_dir=<target-release-evidence-dir>"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace(linux_command, "gh workflow run extended-platform-evidence.yml")
    text = text.replace(xp_command, "gh workflow run xp-native-evidence.yml")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert f"linux-i386 runbook missing Linux workflow dispatch command: {linux_command}" in errors
    assert f"windows-xp-native-x86 runbook missing XP workflow dispatch command: {xp_command}" in errors


def test_platform_promotion_runbook_requires_xp_target_release_scoped_dispatch_paths() -> None:
    checker = _load_checker()
    snippet = (
        "assets_dir, evidence_file and evidence_dir dispatch inputs must be "
        "workspace-relative staged paths that include the target id and release tag as path segments"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        snippet,
        "assets_dir, evidence_file and evidence_dir dispatch inputs must be workspace-relative staged paths",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("target id and release tag as path segments" in error for error in errors)


def test_platform_promotion_runbook_requires_xp_host_identity_smoke_proof_lines() -> None:
    checker = _load_checker()
    snippet = (
        "Every smoke evidence file must include `xp smoke target: windows-xp-native-x86`, "
        "`xp smoke release: v<project.version>`, `xp smoke id: <smoke_id>`, "
        "`xp smoke os name: Windows XP`, `xp smoke os architecture: x86`, "
        "`xp smoke os service pack: SP3`, "
        "`xp smoke host probe command: ver`, "
        "`xp smoke host probe output: Microsoft Windows XP [Version 5.1.2600]`, "
        "`xp smoke processor architecture env: x86`, "
        "`xp smoke processor architecture w6432 env: <empty>`, "
            "`xp smoke wmic os caption: Microsoft Windows XP <edition>`, "
            "`xp smoke wmic os csdversion: Service Pack 3`, "
            "`xp smoke host label: <host_label>`, "
            "`xp smoke evidence run id: <evidence_run_id>`, "
            "`xp smoke observed at utc: <observed_at_utc>`, "
            "`xp smoke source workflow run: <github-actions-run-url>`, "
            "`xp smoke source head sha: <github-actions-head-sha>` and "
            "`xp smoke source run attempt: <github-actions-run-attempt>`."
        )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        snippet,
        (
            "Every smoke evidence file must include `xp smoke target: windows-xp-native-x86`, "
            "`xp smoke release: v<project.version>` and `xp smoke id: <smoke_id>`."
        ),
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "windows-xp-native-x86 runbook missing XP smoke OS and host identity proof line" in errors


def test_platform_promotion_runbook_requires_linux_target_scoped_evidence_filenames() -> None:
    checker = _load_checker()
    snippet = "builder-identity-<target>.json`, `native-smoke-<target>.log`, `platform-verified-evidence-<target>.json"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("native-smoke-<target>.log" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_builder_source_head_sha() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        " --source-head-sha <github-actions-head-sha>",
        "",
    )
    text = text.replace("`observed_git_head_sha`", "`observed_checkout_sha`")
    text = text.replace("`workflow_ref`", "`workflow_file_ref`")
    text = text.replace("`workflow_sha`", "`workflow_file_sha`")
    text = text.replace("`git_worktree_clean=true`", "`checkout_clean=true`")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--source-head-sha <github-actions-head-sha>" in error for error in errors)
    assert any("observed_git_head_sha" in error for error in errors)
    assert any("workflow_ref" in error for error in errors)
    assert any("workflow_sha" in error for error in errors)
    assert any("git_worktree_clean=true" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_smoke_runtime_and_hash_proof() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "`native installer smoke userland bits: 32`, ",
        "",
    )
    text = text.replace(
        "one `native installer smoke artifact sha256: <artifact> <sha256>` line for each expected DEB/RPM/AppImage artifact, ",
        "",
    )
    text = text.replace(
        "`native installer smoke workflow run attempt: <github-actions-run-attempt>`, ",
        "",
    )
    text = text.replace(
        "`native installer smoke git head sha: <github-actions-head-sha>`, ",
        "",
    )
    text = text.replace("`native installer smoke host label: linux-i386-builder`, ", "")
    text = text.replace("`native installer smoke host label: linux-armhf-builder`, ", "")
    text = text.replace(
        "`native installer smoke evidence run id: linux-i386-<release>-run-<github-actions-run-id>`, ",
        "",
    )
    text = text.replace(
        "`native installer smoke evidence run id: linux-armhf-<release>-run-<github-actions-run-id>`, ",
        "",
    )
    text = text.replace("`native installer smoke observed at utc: <YYYY-MM-DDTHH:MM:SSZ>`, ", "")
    text = text.replace(
        "`native installer smoke security update channel: <security-update-channel>`, ",
        "",
    )
    text = text.replace(
        "`native installer smoke CVE review reference: <cve-review-reference>`, ",
        "",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("native installer smoke userland bits: 32" in error for error in errors)
    assert any("native installer smoke artifact sha256: <artifact> <sha256>" in error for error in errors)
    assert any("native installer smoke workflow run attempt" in error for error in errors)
    assert any("native installer smoke git head sha" in error for error in errors)
    assert any("native installer smoke host label" in error for error in errors)
    assert any("native installer smoke evidence run id" in error for error in errors)
    assert any("native installer smoke observed at utc" in error for error in errors)
    assert any("native installer smoke security update channel" in error for error in errors)
    assert any("native installer smoke CVE review reference" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_security_boundaries() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    security_requirement = target["promotion_to_100_requires"]["security_requirements"][1]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        security_requirement,
        "",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing security requirement: {security_requirement}" in errors


def test_platform_promotion_runbook_requires_xp_security_smoke_provenance() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "`security update channel: <security-update-channel>` and ",
        "",
    )
    text = text.replace(
        "`security update channel: <security-update-channel>`, ",
        "",
    )
    text = text.replace(
        "`CVE review reference: <cve-review-reference>`",
        "`CVE review reference removed`",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("security update channel: <security-update-channel>" in error for error in errors)
    assert any("CVE review reference: <cve-review-reference>" in error for error in errors)


def test_platform_promotion_runbook_requires_exact_candidate_command() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    command = target["promotion_to_100_requires"]["accepted_evidence_candidate_command"]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(command, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing accepted evidence candidate command: {command}" in errors


def _load_checker():
    path = Path("scripts/check_platform_promotion_runbook.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_runbook", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
