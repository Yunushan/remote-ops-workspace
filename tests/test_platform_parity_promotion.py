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
