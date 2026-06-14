from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_mobile_support_matrix_declares_tested_android_and_ios_versions() -> None:
    matrix = json.loads(Path("configs/mobile_test_matrix.json").read_text(encoding="utf-8"))

    assert [item["api_level"] for item in matrix["android"]["supported_api_levels"]] == [31, 32, 33, 34, 35, 36]
    assert matrix["android"]["native_apk"] is False
    assert matrix["android"]["status"] == "verified-termux-web-mobile"
    assert matrix["ios_ipados"]["supported_versions"] == [
        "iOS/iPadOS 15",
        "iOS/iPadOS 16",
        "iOS/iPadOS 17",
        "iOS/iPadOS 18",
        "iOS/iPadOS 26",
    ]
    assert matrix["ios_ipados"]["native_ipa"] is False
    assert matrix["ios_ipados"]["status"] == "verified-ios-web-pwa"


def test_mobile_support_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_mobile_support_checker_rejects_dropped_android_api() -> None:
    checker = _load_checker()
    matrix = json.loads(Path("configs/mobile_test_matrix.json").read_text(encoding="utf-8"))
    matrix["android"]["supported_api_levels"] = matrix["android"]["supported_api_levels"][:-1]

    errors = checker.check_matrix(matrix)

    assert any("Android API matrix must be" in error for error in errors)


def _load_checker():
    path = Path("scripts/check_mobile_support.py")
    spec = importlib.util.spec_from_file_location("check_mobile_support_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
