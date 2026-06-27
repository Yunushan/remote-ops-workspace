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


def test_platform_support_truth_rejects_fake_bit_width() -> None:
    checker = _load_platform_support_truth_checker()
    targets = _load_json("configs/platform_targets.json")
    rows = {item["id"]: item for item in targets["release_architectures"]}
    rows["windows-x86"]["bits"] = 128

    errors = checker.check_platform_catalog(targets)

    assert "platform target windows-x86 uses unsupported bit width: 128" in errors


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


def test_platform_support_truth_requires_tagged_strict_platform_publish_docs() -> None:
    checker = _load_platform_support_truth_checker()
    docs = _read_required_docs(checker)
    docs["README.md"] = docs["README.md"].replace(
        (
            "check_release_publish_assets.py --assets-dir <release-assets-dir> "
            "--tag v<project.version> --require-platform-goal-targets"
        ),
        "check_release_publish_assets.py --assets-dir <release-assets-dir> --require-platform-goal-targets",
    )
    docs["docs/PLATFORM_SUPPORT.md"] = docs["docs/PLATFORM_SUPPORT.md"].replace(
        (
            "python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> "
            "--require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run"
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


def _load_platform_support_truth_checker():
    path = Path("scripts/check_platform_support_truth.py")
    spec = importlib.util.spec_from_file_location("check_platform_support_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
