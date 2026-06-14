from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from remote_ops_workspace.features import coverage_report

ROOT = Path(__file__).resolve().parents[1]
MOBILE_MATRIX_PATH = ROOT / "configs" / "mobile_test_matrix.json"
PLATFORM_TARGETS_PATH = ROOT / "configs" / "platform_targets.json"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"

ANDROID_API_LEVELS = [31, 32, 33, 34, 35, 36]
IOS_VERSIONS = [
    "iOS/iPadOS 15",
    "iOS/iPadOS 16",
    "iOS/iPadOS 17",
    "iOS/iPadOS 18",
    "iOS/iPadOS 26",
]


def main() -> int:
    errors = check_mobile_support()
    if errors:
        for error in errors:
            print(f"mobile support: {error}", file=sys.stderr)
        return 1
    print("mobile support contract passed")
    return 0


def check_mobile_support() -> list[str]:
    matrix = read_json(MOBILE_MATRIX_PATH)
    platform_targets = read_json(PLATFORM_TARGETS_PATH)
    workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    docs = {
        "README.md": (ROOT / "README.md").read_text(encoding="utf-8"),
        "docs/ANDROID.md": (ROOT / "docs" / "ANDROID.md").read_text(encoding="utf-8"),
        "docs/IOS.md": (ROOT / "docs" / "IOS.md").read_text(encoding="utf-8"),
        "docs/PLATFORM_SUPPORT.md": (ROOT / "docs" / "PLATFORM_SUPPORT.md").read_text(encoding="utf-8"),
        "docs/RELEASE_STRATEGY.md": (ROOT / "docs" / "RELEASE_STRATEGY.md").read_text(encoding="utf-8"),
    }
    report = coverage_report()

    errors: list[str] = []
    errors.extend(check_matrix(matrix))
    errors.extend(check_platform_alignment(matrix, platform_targets))
    errors.extend(check_workflow(workflow))
    errors.extend(check_docs(docs))
    errors.extend(check_readiness(report))
    return errors


def check_matrix(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if matrix.get("schema_version") != 1:
        errors.append("configs/mobile_test_matrix.json schema_version must be 1")
    if "APK" not in str(matrix.get("contract", "")) or "IPA" not in str(matrix.get("contract", "")):
        errors.append("mobile test matrix contract must explicitly reject native APK/IPA claims")

    android = require_mapping(matrix, "android", errors)
    android_apis = [int(item.get("api_level")) for item in android.get("supported_api_levels", [])]
    if android_apis != ANDROID_API_LEVELS:
        errors.append(f"Android API matrix must be {ANDROID_API_LEVELS}, got {android_apis}")
    if android.get("score") != 100.0 or android.get("status") != "verified-termux-web-mobile":
        errors.append("Android mobile matrix must score verified-termux-web-mobile at 100.0%")
    if android.get("native_apk") is not False:
        errors.append("Android mobile matrix must keep native_apk=false")
    if set(android.get("ci_jobs", [])) != {"mobile-web", "android-emulator-web"}:
        errors.append("Android mobile matrix must require mobile-web and android-emulator-web CI jobs")

    ios = require_mapping(matrix, "ios_ipados", errors)
    if ios.get("supported_versions") != IOS_VERSIONS:
        errors.append(f"iOS/iPadOS version matrix must be {IOS_VERSIONS}, got {ios.get('supported_versions')}")
    if ios.get("score") != 100.0 or ios.get("status") != "verified-ios-web-pwa":
        errors.append("iOS/iPadOS mobile matrix must score verified-ios-web-pwa at 100.0%")
    if ios.get("native_ipa") is not False:
        errors.append("iOS/iPadOS mobile matrix must keep native_ipa=false")
    if set(ios.get("ci_jobs", [])) != {"mobile-web", "ios-simulator-web"}:
        errors.append("iOS/iPadOS mobile matrix must require mobile-web and ios-simulator-web CI jobs")
    return errors


def check_platform_alignment(matrix: dict[str, Any], platform_targets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = {
        str(item.get("id")): item
        for item in platform_targets.get("release_architectures", [])
        if isinstance(item, dict)
    }
    android_ids = set(require_mapping(matrix, "android", errors).get("platform_target_ids", []))
    if android_ids != {"android-armv7", "android-arm64"}:
        errors.append(f"Android platform target ids must be android-armv7/android-arm64, got {sorted(android_ids)}")
    if rows.get("android-armv7", {}).get("bits") != 32:
        errors.append("android-armv7 must remain a 32-bit target")
    if rows.get("android-arm64", {}).get("bits") != 64:
        errors.append("android-arm64 must remain a 64-bit target")

    ios_target = str(require_mapping(matrix, "ios_ipados", errors).get("platform_target_id", ""))
    if ios_target != "ios-web":
        errors.append(f"iOS platform target id must be ios-web, got {ios_target!r}")
    if rows.get("ios-web", {}).get("github_release_channel") != "default-web-pwa":
        errors.append("ios-web must remain on the default-web-pwa release channel")
    return errors


def check_workflow(workflow: str) -> list[str]:
    errors: list[str] = []
    snippets = {
        "android-emulator-web:": "Android emulator Web/PWA job",
        "api-level: [31, 32, 33, 34, 35, 36]": "Android API 31-36 matrix",
        "sdkmanager": "Android SDK package installation",
        "avdmanager create avd": "Android AVD creation",
        "--platform android": "Android mobile smoke helper call",
        "--android-api ${{ matrix.api-level }}": "Android API smoke assertion",
        "ios-simulator-web:": "iOS simulator Web/PWA job",
        "runs-on: macos-26": "current macOS/Xcode simulator runner",
        "--platform ios": "iOS mobile smoke helper call",
        "actions/upload-artifact@v7": "mobile screenshot artifact upload",
    }
    for snippet, label in snippets.items():
        if snippet not in workflow:
            errors.append(f"ci workflow missing {label}: {snippet}")
    return errors


def check_docs(docs: dict[str, str]) -> list[str]:
    errors: list[str] = []
    required = {
        "README.md": (
            "Platform verified readiness is still separate and currently reports **100.0% overall**",
            "Android 12 through Android 16 (API 31-36)",
            "iOS/iPadOS 15 through 26.x",
        ),
        "docs/ANDROID.md": (
            "Android 12 through Android 16 (API 31-36)",
            "android-emulator-web",
            "No APK is published.",
        ),
        "docs/IOS.md": (
            "iOS/iPadOS 15 through 26.x",
            "ios-simulator-web",
            "No native `.ipa` artifact is published.",
        ),
        "docs/PLATFORM_SUPPORT.md": (
            "Android 12 through Android 16 (API 31-36)",
            "iOS/iPadOS 15 through 26.x",
        ),
        "docs/RELEASE_STRATEGY.md": (
            "android-emulator-web",
            "ios-simulator-web",
        ),
    }
    for path, snippets in required.items():
        text = docs.get(path, "")
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"{path} missing mobile support snippet: {snippet}")
    return errors


def check_readiness(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = {
        str(row.get("target")): row
        for row in report.get("platform_verified_readiness", {}).get("targets", [])
        if isinstance(row, dict)
    }
    for target in ("android-armv7", "android-arm64"):
        row = rows.get(target, {})
        if row.get("current_percent") != 100.0 or row.get("status") != "verified-termux-web-mobile":
            errors.append(f"{target} must report 100.0% verified-termux-web-mobile readiness")
    ios = rows.get("ios-web", {})
    if ios.get("current_percent") != 100.0 or ios.get("status") != "verified-ios-web-pwa":
        errors.append("ios-web must report 100.0% verified-ios-web-pwa readiness")
    return errors


def require_mapping(data: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        errors.append(f"configs/mobile_test_matrix.json {key} must be an object")
        return {}
    return value


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
