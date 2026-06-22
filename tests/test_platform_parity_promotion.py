from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


def test_platform_parity_promotion_checker_passes_current_tree() -> None:
    checker = _load_platform_parity_promotion_checker()

    assert checker.main() == 0


def test_platform_parity_promotion_rejects_fake_linux_100() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "linux-i386")
    entry["current_readiness_percent"] = 100.0
    entry["current_status"] = "verified-default-native"

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert "linux-i386 current_readiness_percent must match current evidence 70.0, got 100.0" in errors
    assert "linux-i386 current_status must match current evidence 'manual-script-supported'" in "\n".join(errors)


def test_platform_parity_promotion_rejects_linux_default_without_workflow_evidence() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    platform_targets = _load_json("configs/platform_targets.json")
    release_matrix = _load_json("configs/release_matrix.json")
    report = deepcopy(checker.coverage_report())
    platform_row = _platform_row(platform_targets, "linux-armhf")
    platform_row["release_tier"] = "native"
    platform_row["github_release_channel"] = "default-native"
    entry = _promotion_entry(promotion, "linux-armhf")
    entry["current_release_tier"] = "native"
    entry["current_github_release_channel"] = "default-native"
    entry["current_readiness_percent"] = 100.0
    entry["current_status"] = "verified-default-native"
    readiness = _readiness_row(report, "linux-armhf")
    readiness["current_percent"] = 100.0
    readiness["gap_percent"] = 0.0
    readiness["status"] = "verified-default-native"
    readiness["verified_readiness_scope"] = True

    errors = checker.check_platform_parity_promotion(
        promotion=promotion,
        platform_targets=platform_targets,
        release_matrix=release_matrix,
        report=report,
    )

    assert "linux-armhf 100% promotion requires default native release matrix membership" in errors
    assert "linux-armhf 100% promotion requires linux-native matrix arch armhf" in errors
    assert "linux-armhf 100% promotion requires workflow arch armhf" in errors


def test_platform_parity_promotion_requires_finalized_evidence_contract() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "linux-i386")
    requirements = entry["promotion_to_100_requires"]
    requirements["accepted_evidence_candidate_command"] += " --append-registry"

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert "linux-i386 accepted_evidence_candidate_command must not append unfinalized candidates" in errors


def test_platform_parity_promotion_requires_local_evidence_preflight() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "linux-i386")
    del entry["promotion_to_100_requires"]["local_evidence_preflight_command"]

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert "linux-i386 promotion_to_100_requires missing keys: ['local_evidence_preflight_command']" in errors


def test_platform_parity_promotion_rejects_xp_local_preflight_without_xp_evidence_dir() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x64")
    command = entry["promotion_to_100_requires"]["local_evidence_preflight_command"]
    entry["promotion_to_100_requires"]["local_evidence_preflight_command"] = command.replace(
        " --xp-evidence-dir <target-release-evidence-dir>",
        "",
    )

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert any("windows-xp-native-x64 local_evidence_preflight_command must be" in error for error in errors)


def test_platform_parity_promotion_rejects_generic_xp_release_source_artifact_name() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x86")
    requirements = entry["promotion_to_100_requires"]
    requirements["accepted_evidence_candidate_command"] = requirements[
        "accepted_evidence_candidate_command"
    ].replace(
        "xp-native-evidence-windows-xp-native-x86-v<project.version>",
        "<github-actions-artifact-name>",
    )

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert (
        "windows-xp-native-x86 accepted_evidence_candidate_command must bind release source "
        "artifact name '--release-source-artifact-name "
        "xp-native-evidence-windows-xp-native-x86-v<project.version>'"
    ) in errors


def test_platform_parity_promotion_rejects_missing_linux_release_source_artifact_name() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "linux-armhf")
    requirements = entry["promotion_to_100_requires"]
    requirements["accepted_evidence_candidate_command"] = requirements[
        "accepted_evidence_candidate_command"
    ].replace(
        " --release-source-artifact-name extended-linux-evidence-linux-armhf-v<project.version>",
        "",
    )

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert (
        "linux-armhf accepted_evidence_candidate_command must bind release source "
        "artifact name '--release-source-artifact-name "
        "extended-linux-evidence-linux-armhf-v<project.version>'"
    ) in errors


def test_platform_parity_promotion_rejects_missing_release_source_head_sha() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "linux-i386")
    requirements = entry["promotion_to_100_requires"]
    requirements["accepted_evidence_candidate_command"] = requirements[
        "accepted_evidence_candidate_command"
    ].replace(" --release-source-head-sha <github-actions-head-sha>", "")

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert "linux-i386 accepted_evidence_candidate_command must bind release source head SHA" in errors


def test_linux_blockers_describe_evidence_activated_publish_contracts() -> None:
    promotion = _load_json("configs/platform_parity_promotion.json")

    for target_id in ("linux-i386", "linux-armhf"):
        entry = _promotion_entry(promotion, target_id)
        blockers = "\n".join(entry["current_blockers"])
        assert "No release publish contract currently requires" not in blockers
        assert (
            "No accepted evidence record is present yet to activate publish-time requirements "
            f"for {target_id} checksum, manifest and review-bundle assets."
        ) in blockers


def test_platform_parity_promotion_requires_review_bundle_candidate_record() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x86")
    requirements = entry["promotion_to_100_requires"]
    requirements["review_bundle_command"] = requirements["review_bundle_command"].replace(
        " --candidate-record <platform-verified-evidence-windows-xp-native-x86.json>",
        "",
    )

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert (
        "windows-xp-native-x86 review_bundle_command must bind the candidate record with --candidate-record"
        in errors
    )


def test_platform_parity_promotion_rejects_fake_xp_native_stack_support() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x86")
    entry["current_stack_supported"] = True

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert (
        "windows-xp-native-x86 current_stack_supported must remain false until "
        "XP-native evidence exists"
    ) in errors


def test_platform_parity_promotion_requires_xp_source_workflow() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x64")
    entry["promotion_to_100_requires"]["release_source_workflow"] = ".github/workflows/ci.yml"

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert (
        "windows-xp-native-x64 release_source_workflow must be "
        ".github/workflows/xp-native-evidence.yml"
    ) in errors


def test_platform_parity_promotion_rejects_xp_100_without_vm_evidence() -> None:
    checker = _load_platform_parity_promotion_checker()
    promotion = _load_json("configs/platform_parity_promotion.json")
    entry = _promotion_entry(promotion, "windows-xp-native-x64")
    entry["current_readiness_percent"] = 100.0

    errors = checker.check_platform_parity_promotion(promotion=promotion)

    assert "windows-xp-native-x64 current_readiness_percent must match current evidence 25.0" in "\n".join(errors)
    assert "windows-xp-native-x64 cannot claim 100% until XP VM and native artifact evidence is added" in errors


def _promotion_entry(promotion: dict[str, Any], target_id: str) -> dict[str, Any]:
    return {
        item["id"]: item
        for item in promotion["protected_targets"]
    }[target_id]


def _platform_row(platform_targets: dict[str, Any], target_id: str) -> dict[str, Any]:
    return {
        item["id"]: item
        for item in platform_targets["release_architectures"]
    }[target_id]


def _readiness_row(report: dict[str, Any], target_id: str) -> dict[str, Any]:
    return {
        item["target"]: item
        for item in report["platform_verified_readiness"]["targets"]
    }[target_id]


def _load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_platform_parity_promotion_checker():
    path = Path("scripts/check_platform_parity_promotion.py")
    spec = importlib.util.spec_from_file_location("check_platform_parity_promotion", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
