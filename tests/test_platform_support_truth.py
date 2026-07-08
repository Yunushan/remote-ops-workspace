from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from remote_ops_workspace.features import coverage_report


def test_platform_support_truth_checker_passes_current_tree() -> None:
    checker = _load_platform_support_truth_checker()

    assert checker.main() == 0


def test_platform_support_truth_uses_explicit_empty_platform_targets() -> None:
    checker = _load_platform_support_truth_checker()

    errors = checker.check_platform_support_truth(platform_targets={})

    assert "platform catalog must declare protected_readiness_goal contract" in errors
    assert "missing platform architecture target: linux-i386" in errors


def test_platform_support_truth_uses_explicit_empty_report() -> None:
    checker = _load_platform_support_truth_checker()

    errors = checker.check_platform_support_truth(report={})

    assert any("platform readiness targets must match platform catalog" in error for error in errors)
    assert any("protected platform goal report required_targets must match" in error for error in errors)


def test_platform_support_truth_rejects_fake_bit_width() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    rows = {item["id"]: item for item in targets["release_architectures"]}
    rows["windows-x86"]["bits"] = 128

    errors = checker.check_platform_catalog(targets)

    assert "platform target windows-x86 uses unsupported bit width: 128" in errors


def test_platform_support_truth_rejects_missing_protected_readiness_contract() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    del targets["protected_readiness_goal"]

    errors = checker.check_platform_catalog(targets)

    assert "platform catalog must declare protected_readiness_goal contract" in errors


def test_platform_support_truth_rejects_missing_protected_linux_checksum_asset() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    rows = {item["id"]: item for item in targets["release_architectures"]}
    rows["linux-i386"]["assets"].remove(
        "remote-ops-workspace-v1.0.2-linux-i686-native-SHA256SUMS.txt"
    )

    errors = checker.check_platform_catalog(targets)

    assert (
        "platform target linux-i386 assets must include protected promotion artifacts: "
        "['remote-ops-workspace-v1.0.2-linux-i686-native-SHA256SUMS.txt']"
    ) in errors


def test_platform_support_truth_rejects_weak_protected_asset_gate() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    targets["protected_readiness_goal"]["release_asset_provenance_gate"] = (
        "python scripts/check_protected_platform_goal.py --release-tag v<project.version>"
    )

    errors = checker.check_platform_catalog(targets)

    assert any("release_asset_provenance_gate must be" in error for error in errors)


def test_platform_support_truth_rejects_manual_linux_promoted_to_default() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    matrix = _load_json("configs/release_matrix.json")
    matrix["default_github_release"]["native_jobs"][2]["platform_target_ids"].append("linux-i386")
    matrix["script_supported_native"] = [
        item for item in matrix["script_supported_native"] if item["platform_target_id"] != "linux-i386"
    ]

    errors = checker.check_release_matrix_alignment(targets, matrix)

    assert any("default native release targets must exactly match" in error for error in errors)
    assert any("script-supported release targets must exactly match" in error for error in errors)


def test_platform_support_truth_rejects_inflated_manual_readiness() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    rows["linux-armhf"]["current_percent"] = 100.0
    rows["linux-armhf"]["gap_percent"] = 0.0
    rows["linux-armhf"]["status"] = "verified-default-native"
    rows["linux-armhf"]["verified_readiness_scope"] = True

    errors = checker.check_platform_readiness_report(targets, report)

    assert "linux-armhf readiness score must be 70.0%, got 100.0%" in errors
    assert "linux-armhf readiness status must be manual-script-supported, got verified-default-native" in errors
    assert "linux-armhf verified_readiness_scope must be False, got True" in errors


def test_platform_support_truth_rejects_protected_goal_report_catalog_drift() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["required_targets"] = [
        target for target in goal["required_targets"] if target != "linux-armhf"
    ]

    errors = checker.check_platform_readiness_report(targets, report)

    assert any(
        "protected platform goal report required_targets must match platform catalog"
        in error
        for error in errors
    )


def test_platform_support_truth_accepts_evidence_backed_linux_promotion() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    linux_i386 = rows["linux-i386"]
    linux_i386["current_percent"] = 100.0
    linux_i386["gap_percent"] = 0.0
    linux_i386["status"] = "verified-accepted-native-evidence"
    linux_i386["verified_readiness_scope"] = True
    _bind_accepted_evidence_row(linux_i386, ["linux-i386"])

    errors = checker.check_platform_readiness_report(targets, report)

    assert errors == []


def test_platform_support_truth_rejects_static_protected_row_release_asset_claim() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    linux_i386 = rows["linux-i386"]
    linux_i386["current_percent"] = 100.0
    linux_i386["gap_percent"] = 0.0
    linux_i386["status"] = "verified-accepted-native-evidence"
    linux_i386["verified_readiness_scope"] = True
    _bind_accepted_evidence_row(linux_i386, ["linux-i386"])
    linux_i386["release_asset_provenance_complete"] = True
    linux_i386["release_backed_readiness_complete"] = True
    linux_i386["static_readiness_evidence_scope"] = "accepted evidence"

    errors = checker.check_platform_readiness_report(targets, report)

    assert (
        "linux-i386 protected row must keep release_asset_provenance_complete=false "
        "in static readiness JSON"
    ) in errors
    assert (
        "linux-i386 protected row must keep release_backed_readiness_complete=false "
        "in static readiness JSON"
    ) in errors
    assert (
        "linux-i386 protected row static_readiness_evidence_scope must mention --assets-dir"
        in errors
    )


def test_platform_support_truth_accepts_partial_xp_native_evidence() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    xp = rows["Windows XP"]
    xp["status"] = "partial-xp-native-host-evidence"
    xp["accepted_evidence_present_targets"] = ["windows-xp-native-x86"]
    xp["accepted_evidence_missing_targets"] = ["windows-xp-native-x64"]
    _bind_accepted_evidence_row(xp, ["windows-xp-native-x86"])

    errors = checker.check_platform_readiness_report(targets, report)

    assert errors == []


def test_platform_support_truth_accepts_mixed_pair_as_partial_xp_native_evidence() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    xp = rows["Windows XP"]
    xp["status"] = "partial-xp-native-host-evidence"
    _bind_accepted_evidence_row(
        xp,
        ["windows-xp-native-x86", "windows-xp-native-x64"],
    )

    errors = checker.check_platform_readiness_report(targets, report)

    assert errors == []


def test_platform_support_truth_accepts_full_xp_native_evidence_promotion() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    xp = rows["Windows XP"]
    xp["current_percent"] = 100.0
    xp["gap_percent"] = 0.0
    xp["status"] = "verified-xp-native-host-evidence"
    xp["verified_readiness_scope"] = True
    _bind_accepted_evidence_row(
        xp,
        ["windows-xp-native-x86", "windows-xp-native-x64"],
    )

    errors = checker.check_platform_readiness_report(targets, report)

    assert errors == []


def test_platform_support_truth_rejects_unbound_evidence_backed_linux_promotion() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    report = deepcopy(coverage_report())
    rows = {row["target"]: row for row in report["platform_verified_readiness"]["targets"]}
    linux_i386 = rows["linux-i386"]
    linux_i386["current_percent"] = 100.0
    linux_i386["gap_percent"] = 0.0
    linux_i386["status"] = "verified-accepted-native-evidence"
    linux_i386["verified_readiness_scope"] = True

    errors = checker.check_platform_readiness_report(targets, report)

    assert (
        "linux-i386 evidence-backed readiness must expose accepted evidence "
        "present=['linux-i386'] and missing=[]"
    ) in errors
    assert "linux-i386 accepted evidence for linux-i386 must expose a concrete release tag" in errors


def test_platform_support_truth_rejects_native_legacy_windows_claim() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["README.md"] += "\nWindows XP native installer is available.\n"

    errors = checker.check_platform_docs(docs, coverage_report())

    assert "platform docs contain misleading support claim: Windows XP native installer" in errors


def test_platform_support_truth_requires_generated_platform_rows() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/FULL_FEATURE_COVERAGE.md"] = docs["docs/FULL_FEATURE_COVERAGE.md"].replace(
        "| linux-i386 | Linux i386 | manual-script-native | 70.0% | 30.0% | manual-script-supported |",
        "| linux-i386 | Linux i386 | default-native | 100.0% | 0.0% | verified-default-native |",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any("missing generated platform row" in error and "linux-i386" in error for error in errors)


def test_platform_support_truth_requires_current_protected_goal_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["README.md"] = docs["README.md"].replace(
        (
            "Protected platform goal parity is **0.0%** for the current "
            "accepted-evidence registry (status=missing-accepted-evidence)"
        ),
        "Protected platform goal parity is complete",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "README.md missing current protected platform goal snippet" in error
        and "Protected platform goal parity is **0.0%**" in error
        and "status=missing-accepted-evidence" in error
        for error in errors
    )


def test_platform_support_truth_requires_full_coverage_attempt_conflict_boundary() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    snippet = "same-run-URL conflicting-attempt accepted records"
    assert snippet in docs["docs/FULL_FEATURE_COVERAGE.md"]
    docs["docs/FULL_FEATURE_COVERAGE.md"] = docs["docs/FULL_FEATURE_COVERAGE.md"].replace(
        snippet,
        "accepted records with varied run attempts",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/FULL_FEATURE_COVERAGE.md missing platform truth snippet" in error
        and "same-run-URL conflicting-attempt accepted records" in error
        for error in errors
    )


def test_platform_support_truth_requires_full_coverage_remote_release_audit_boundary() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    snippet = "Remote evidence audit"
    assert snippet in docs["docs/FULL_FEATURE_COVERAGE.md"]
    docs["docs/FULL_FEATURE_COVERAGE.md"] = docs["docs/FULL_FEATURE_COVERAGE.md"].replace(
        snippet,
        "Release evidence note",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/FULL_FEATURE_COVERAGE.md missing platform truth snippet" in error
        and "Remote evidence audit" in error
        for error in errors
    )


def test_platform_support_truth_requires_platforms_cli_evidence_boundary_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = (
        docs["docs/PLATFORM_SUPPORT.md"]
        .replace("Evidence-backed protected\nreadiness", "Protected platform summary")
        .replace("Release asset provenance", "Release asset state")
        .replace(
            "static platform catalog is not native-host/readiness\nproof",
            "static platform catalog describes supported targets",
        )
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "Evidence-backed protected readiness" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "Release asset provenance" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "static platform catalog is not native-host/readiness proof" in error
        for error in errors
    )


def test_platform_support_truth_requires_cli_asset_provenance_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/FULL_FEATURE_COVERAGE.md"] = docs["docs/FULL_FEATURE_COVERAGE.md"].replace(
        "Release asset\nprovenance",
        "Release byte\nproof",
    )
    docs["docs/FULL_FEATURE_COVERAGE.md"] = docs["docs/FULL_FEATURE_COVERAGE.md"].replace(
        "`release_asset_provenance_command`",
        "`asset_gate_command`",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/FULL_FEATURE_COVERAGE.md missing platform truth snippet" in error
        and "Release asset provenance" in error
        for error in errors
    )
    assert any(
        "docs/FULL_FEATURE_COVERAGE.md missing platform truth snippet" in error
        and "release_asset_provenance_command" in error
        for error in errors
    )


def test_platform_support_truth_requires_tagged_strict_platform_publish_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["README.md"] = docs["README.md"].replace(
        (
            "check_release_publish_assets.py --assets-dir <release-assets-dir> "
            "--tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets"
        ),
        "check_release_publish_assets.py --assets-dir <release-assets-dir> --require-platform-goal-targets",
    )
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        (
            "python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> "
            "--require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run "
            "--repository <owner>/<repo>"
        ),
        "python scripts/import_platform_evidence_artifacts.py --dry-run",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any("README.md missing platform truth snippet" in error and "--tag v<project.version>" in error for error in errors)
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "--release-tag v<project.version>" in error
        and "--verify-source-run" in error
        for error in errors
    )


def test_platform_support_truth_requires_downloaded_source_hash_preflight_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        "hash-checked as downloaded",
        "checked before platform promotion",
    )
    docs["docs/RELEASE_STRATEGY.md"] = docs["docs/RELEASE_STRATEGY.md"].replace(
        "downloaded source artifact native artifact",
        "downloaded source artifact checks",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "hash-checked as downloaded source artifacts" in error
        for error in errors
    )
    assert any(
        "docs/RELEASE_STRATEGY.md missing platform truth snippet" in error
        and "downloaded source artifact native artifact SHA-256 values" in error
        for error in errors
    )


def test_platform_support_truth_requires_published_release_audit_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = (
        docs["docs/PLATFORM_SUPPORT.md"]
        .replace(
            "that strict verifier audits the intended already-published GitHub release",
            "use the strict verifier",
        )
        .replace(
            "published native/review-bundle asset bytes and published final\naccepted-record JSON bytes",
            "published evidence files",
        )
        .replace("`workflow_run.repository_id` and\n`workflow_run.head_repository_id`", "`workflow_run.id`")
        .replace(
            "artifact `created_at` values outside the exact source run creation/start/update window",
            "stale artifact timestamps",
        )
        .replace("canonical\naccepted-record JSON bytes", "accepted record metadata")
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "that strict verifier audits the intended already-published GitHub release" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "published native/review-bundle asset bytes" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "published final accepted-record JSON bytes" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "workflow_run.repository_id" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "artifact `created_at` values outside the exact source run creation/start/update window" in error
        for error in errors
    )
    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "canonical accepted-record JSON bytes" in error
        for error in errors
    )


def test_platform_support_truth_requires_final_record_asset_import_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["README.md"] = docs["README.md"].replace(" --require-final-record-assets", "")
    docs["docs/RELEASE_STRATEGY.md"] = docs["docs/RELEASE_STRATEGY.md"].replace(
        " --require-final-record-assets",
        "",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "README.md missing platform truth snippet" in error
        and "--require-final-record-assets" in error
        for error in errors
    )
    assert any(
        "docs/RELEASE_STRATEGY.md missing platform truth snippet" in error
        and "--require-final-record-assets" in error
        for error in errors
    )


def test_platform_support_truth_requires_linux_smoke_run_attempt_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        (
            "scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 "
            "--workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> "
            "--source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>"
        ),
        (
            "scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 "
            "--workflow-run-url <github-actions-run-url> --source-head-sha <github-actions-head-sha> "
            "--builder-evidence <builder-identity.json>"
        ),
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "--workflow-run-attempt <github-actions-run-attempt>" in error
        for error in errors
    )


def test_platform_support_truth_requires_linux_smoke_builder_evidence_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        (
            "--source-head-sha <github-actions-head-sha> "
            "--builder-evidence <builder-identity.json>"
        ),
        "--source-head-sha <github-actions-head-sha>",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "--builder-evidence <builder-identity.json>" in error
        for error in errors
    )


def test_platform_support_truth_requires_linux_smoke_git_head_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        "observed Git HEAD SHA matches that source head SHA",
        "smoke log includes source metadata",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "observed Git HEAD SHA matches that source head SHA" in error
        for error in errors
    )


def test_platform_support_truth_requires_linux_builder_git_head_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        "`workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` matching `release_asset_source.head_sha`",
        "`source_head_sha` matching `release_asset_source.head_sha`",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "`workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`" in error
        for error in errors
    )


def test_platform_support_truth_requires_linux_builder_clean_checkout_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        "`git_worktree_clean=true`",
        "`checkout_clean=true`",
    )

    errors = checker.check_platform_docs(docs, coverage_report())

    assert any(
        "docs/PLATFORM_SUPPORT.md missing platform truth snippet" in error
        and "`git_worktree_clean=true`" in error
        for error in errors
    )


def test_platform_support_truth_tracks_required_targets() -> None:
    checker = _load_platform_support_truth_checker()

    assert checker.EXPECTED_ARCHITECTURES["windows-x86"]["bits"] == 32
    assert checker.EXPECTED_ARCHITECTURES["linux-i386"]["github_release_channel"] == "manual-script-native"
    assert checker.EXPECTED_ARCHITECTURES["linux-armhf"]["github_release_channel"] == "manual-script-native"
    assert checker.EXPECTED_ARCHITECTURES["android-armv7"]["github_release_channel"] == "default-termux-web"
    assert checker.EXPECTED_ARCHITECTURES["android-armv7"]["status"] == "verified-termux-web-mobile"
    assert checker.EXPECTED_ARCHITECTURES["ios-web"]["github_release_channel"] == "default-web-pwa"
    assert checker.EXPECTED_ARCHITECTURES["ios-web"]["status"] == "verified-ios-web-pwa"
    assert checker.EXPECTED_LEGACY_WINDOWS["Windows XP"]["host_tier"] == "remote-target-only"


def test_platform_support_truth_requires_xp_release_source_docs() -> None:
    checker = _load_platform_support_truth_checker()

    assert "`xp_evidence_summary.release_source` matching `release_asset_source`" in (
        checker.REQUIRED_DOC_SNIPPETS["docs/PLATFORM_SUPPORT.md"]
    )
    assert "`xp smoke source head sha`" in checker.REQUIRED_DOC_SNIPPETS["docs/PLATFORM_SUPPORT.md"]


def _read_required_docs(checker: Any) -> dict[str, str]:
    return {
        path: Path(path).read_text(encoding="utf-8")
        for path in checker.REQUIRED_DOC_SNIPPETS
    }


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _bind_accepted_evidence_row(row: dict[str, Any], targets: list[str]) -> None:
    required = (
        ["windows-xp-native-x86", "windows-xp-native-x64"]
        if any(target.startswith("windows-xp-native-") for target in targets)
        else targets
    )
    row["accepted_evidence_required_targets"] = required
    row["accepted_evidence_present_targets"] = targets
    row["accepted_evidence_missing_targets"] = [
        target for target in required if target not in targets
    ]
    row["accepted_evidence_record_complete"] = sorted(required) == sorted(targets)
    row["release_asset_provenance_complete"] = False
    row["release_backed_readiness_complete"] = False
    row["static_readiness_evidence_scope"] = (
        "accepted-record/source-run metadata only; run "
        "python scripts/check_protected_platform_goal.py --release-tag v<project.version> "
        "--require-complete --assets-dir <release-assets-dir> --repository <owner>/<repo> "
        "for published release asset byte proof"
    )
    row["accepted_evidence_release_tags"] = {target: "v1.0.2" for target in targets}
    row["accepted_evidence_release_repositories"] = {
        target: ["example/remote-ops-workspace"] for target in targets
    }
    row["accepted_evidence_release_source_heads"] = {target: "a" * 40 for target in targets}
    row["accepted_evidence_release_source_run_attempts"] = {target: 1 for target in targets}
    row["accepted_evidence_release_source_workflows"] = {
        target: (
            ".github/workflows/xp-native-evidence.yml"
            if target.startswith("windows-xp-native-")
            else ".github/workflows/extended-platform-evidence.yml"
        )
        for target in targets
    }


def _load_platform_support_truth_checker():
    path = Path("scripts/check_platform_support_truth.py")
    spec = importlib.util.spec_from_file_location("check_platform_support_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
