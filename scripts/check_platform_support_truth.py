from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.features import coverage_report  # noqa: E402

PLATFORM_TARGETS_PATH = ROOT / "configs" / "platform_targets.json"
RELEASE_MATRIX_PATH = ROOT / "configs" / "release_matrix.json"

EXPECTED_ARCHITECTURES: dict[str, dict[str, Any]] = {
    "windows-x86": {
        "bits": 32,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "windows-x64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "windows-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "linux-i386": {
        "bits": 32,
        "release_tier": "script-supported-native",
        "github_release_channel": "manual-script-native",
        "score": 70.0,
        "status": "manual-script-supported",
    },
    "linux-x86_64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "linux-armhf": {
        "bits": 32,
        "release_tier": "script-supported-native",
        "github_release_channel": "manual-script-native",
        "score": 70.0,
        "status": "manual-script-supported",
    },
    "linux-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "macos-x64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "macos-arm64": {
        "bits": 64,
        "release_tier": "native",
        "github_release_channel": "default-native",
        "score": 100.0,
        "status": "verified-default-native",
    },
    "android-armv7": {
        "bits": 32,
        "release_tier": "termux-web",
        "github_release_channel": "default-termux-web",
        "score": 85.0,
        "status": "termux-web-default",
    },
    "android-arm64": {
        "bits": 64,
        "release_tier": "termux-web",
        "github_release_channel": "default-termux-web",
        "score": 85.0,
        "status": "termux-web-default",
    },
}

EXPECTED_LEGACY_WINDOWS: dict[str, dict[str, Any]] = {
    "Windows 8.1": {
        "host_tier": "best-effort-source",
        "remote_target_tier": "supported",
        "score": 60.0,
        "status": "best-effort-source-host",
    },
    "Windows 8": {
        "host_tier": "legacy-source-only",
        "remote_target_tier": "supported",
        "score": 45.0,
        "status": "legacy-source-only",
    },
    "Windows 7": {
        "host_tier": "legacy-source-only",
        "remote_target_tier": "supported",
        "score": 45.0,
        "status": "legacy-source-only",
    },
    "Windows Vista": {
        "host_tier": "remote-target-only",
        "remote_target_tier": "supported",
        "score": 25.0,
        "status": "remote-target-only",
    },
    "Windows XP": {
        "host_tier": "remote-target-only",
        "remote_target_tier": "supported",
        "score": 25.0,
        "status": "remote-target-only",
    },
}

REQUIRED_DOC_SNIPPETS: dict[str, tuple[str, ...]] = {
    "README.md": (
        "Platform verified readiness is still separate and currently reports **75.6% overall**",
        "Windows XP/Vista/7/8 are supported as legacy remote targets, not as first-class",
        "Linux `i386`/`i686` and `armhf` outputs for matching builders, but those are not uploaded",
    ),
    "docs/PLATFORM_SUPPORT.md": (
        "Architecture support is declared in `configs/platform_targets.json`",
        "python scripts/check_platform_support_truth.py",
        "Windows Vista and Windows XP as remote targets only.",
        "i386/i686: 32-bit x86 Linux packages, script-supported only.",
        "armv7l/armhf: 32-bit ARM Linux packages, script-supported only.",
        "APK-style artifacts remain out of scope until there is a real native Android wrapper.",
    ),
    "docs/RELEASE_STRATEGY.md": (
        "Linux `i386`/`i686` and `armv7l`/`armhf` native outputs are script-supported",
        "Treats Windows XP, Vista, Windows 7 and Windows 8.0 as legacy remote targets",
        "Android remains Termux plus Web/PWA until there is a real native Android wrapper.",
    ),
    "docs/FULL_FEATURE_COVERAGE.md": (
        "Platform verified readiness",
        "Platform verified readiness remains separate",
    ),
}

MISLEADING_PLATFORM_CLAIMS = (
    "8-bit support",
    "16-bit support",
    "128-bit support",
    "Windows XP native installer",
    "Windows Vista native installer",
    "Windows 7 native installer",
    "Windows 8 native installer",
    "Linux i386 default native",
    "Linux armhf default native",
    "APK is published",
)


def main() -> int:
    errors = check_platform_support_truth()
    if errors:
        for error in errors:
            print(f"platform support truth: {error}", file=sys.stderr)
        return 1
    print("platform support truth checks passed")
    return 0


def check_platform_support_truth(
    *,
    platform_targets: dict[str, Any] | None = None,
    release_matrix: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    docs: dict[str, str] | None = None,
) -> list[str]:
    platform_data = platform_targets or read_json(PLATFORM_TARGETS_PATH)
    matrix = release_matrix or read_json(RELEASE_MATRIX_PATH)
    coverage = report or coverage_report()
    doc_text = docs or read_docs(REQUIRED_DOC_SNIPPETS)

    errors: list[str] = []
    errors.extend(check_platform_catalog(platform_data))
    errors.extend(check_release_matrix_alignment(platform_data, matrix))
    errors.extend(check_platform_readiness_report(platform_data, coverage))
    errors.extend(check_platform_docs(doc_text, coverage))
    return errors


def check_platform_catalog(platform_targets: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    rows = rows_by_key(platform_targets.get("release_architectures", []), "id", errors)
    legacy_rows = rows_by_key(platform_targets.get("windows_legacy_targets", []), "version", errors)

    for target_id, expected in EXPECTED_ARCHITECTURES.items():
        row = rows.get(target_id)
        if row is None:
            errors.append(f"missing platform architecture target: {target_id}")
            continue
        errors.extend(check_expected_fields(f"platform target {target_id}", row, expected))
        bits = row.get("bits")
        if bits not in (32, 64):
            errors.append(f"platform target {target_id} uses unsupported bit width: {bits}")
        if bits == 32 and "32-bit" not in searchable_target_text(row):
            errors.append(f"32-bit platform target {target_id} must explain 32-bit support boundaries")
        if not row.get("assets"):
            errors.append(f"platform target {target_id} must declare release assets")

    for version, expected in EXPECTED_LEGACY_WINDOWS.items():
        row = legacy_rows.get(version)
        if row is None:
            errors.append(f"missing legacy Windows target: {version}")
            continue
        errors.extend(check_expected_fields(f"legacy Windows target {version}", row, expected))
        if "native" not in searchable_target_text(row).lower():
            errors.append(f"legacy Windows target {version} must explain native-host limits")

    return errors


def check_release_matrix_alignment(platform_targets: dict[str, Any], matrix: dict[str, Any]) -> list[str]:
    rows = {
        str(item.get("id")): item
        for item in platform_targets.get("release_architectures", [])
        if isinstance(item, dict)
    }
    native_ids = {target_id for target_id, row in rows.items() if row.get("release_tier") == "native"}
    script_ids = {
        target_id
        for target_id, row in rows.items()
        if row.get("release_tier") == "script-supported-native"
    }
    termux_ids = {target_id for target_id, row in rows.items() if row.get("release_tier") == "termux-web"}

    default_ids: set[str] = set()
    for job in matrix.get("default_github_release", {}).get("native_jobs", []):
        if isinstance(job, dict):
            default_ids.update(str(item) for item in job.get("platform_target_ids", []))
    matrix_script_ids = {
        str(item.get("platform_target_id"))
        for item in matrix.get("script_supported_native", [])
        if isinstance(item, dict)
    }
    matrix_termux_ids: set[str] = set()
    matrix_legacy_versions: set[str] = set()
    for item in matrix.get("source_or_remote_only", []):
        if not isinstance(item, dict):
            continue
        matrix_termux_ids.update(str(target_id) for target_id in item.get("platform_target_ids", []))
        matrix_legacy_versions.update(str(version) for version in item.get("windows_legacy_target_versions", []))

    errors: list[str] = []
    if default_ids != native_ids:
        errors.append(
            "default native release targets must exactly match native platform targets "
            f"(expected {sorted(native_ids)}, got {sorted(default_ids)})"
        )
    if matrix_script_ids != script_ids:
        errors.append(
            "script-supported release targets must exactly match script-supported platform targets "
            f"(expected {sorted(script_ids)}, got {sorted(matrix_script_ids)})"
        )
    if matrix_termux_ids != termux_ids:
        errors.append(
            "Termux/Web release targets must exactly match termux-web platform targets "
            f"(expected {sorted(termux_ids)}, got {sorted(matrix_termux_ids)})"
        )
    legacy_versions = set(EXPECTED_LEGACY_WINDOWS)
    if matrix_legacy_versions != legacy_versions:
        errors.append(
            "legacy Windows release matrix targets must exactly match declared legacy Windows targets "
            f"(expected {sorted(legacy_versions)}, got {sorted(matrix_legacy_versions)})"
        )
    return errors


def check_platform_readiness_report(
    platform_targets: dict[str, Any],
    report: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    platform = report.get("platform_verified_readiness", {})
    target_rows = rows_by_key(platform.get("targets", []), "target", errors)
    expected_targets = {*EXPECTED_ARCHITECTURES, *EXPECTED_LEGACY_WINDOWS}
    actual_targets = set(target_rows)
    if actual_targets != expected_targets:
        errors.append(
            "platform readiness targets must match platform catalog "
            f"(expected {sorted(expected_targets)}, got {sorted(actual_targets)})"
        )

    for target_id, expected in EXPECTED_ARCHITECTURES.items():
        row = target_rows.get(target_id)
        if row is None:
            continue
        errors.extend(check_readiness_row(target_id, row, expected))
    for version, expected in EXPECTED_LEGACY_WINDOWS.items():
        row = target_rows.get(version)
        if row is None:
            continue
        errors.extend(check_readiness_row(version, row, expected))
        if row.get("remote_target_tier") != "supported":
            errors.append(f"{version} readiness row must keep remote_target_tier=supported")

    expected_overall = expected_platform_overall(platform_targets)
    actual_overall = platform.get("overall", {}).get("current_percent")
    if actual_overall != expected_overall:
        errors.append(f"platform readiness overall must be {expected_overall}%, got {actual_overall}%")
    if actual_overall == 100.0:
        errors.append("platform readiness overall must not be 100% while manual and legacy targets exist")
    return errors


def check_platform_docs(docs: dict[str, str], report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, snippets in REQUIRED_DOC_SNIPPETS.items():
        text = normalize_text(docs.get(path, ""))
        if not text:
            errors.append(f"missing platform support doc text: {path}")
            continue
        for snippet in snippets:
            if normalize_text(snippet) not in text:
                errors.append(f"{path} missing platform truth snippet: {snippet}")

    combined = normalize_text("\n".join(docs.values()))
    for claim in MISLEADING_PLATFORM_CLAIMS:
        if normalize_text(claim) in combined:
            errors.append(f"platform docs contain misleading support claim: {claim}")

    full_coverage = docs.get("docs/FULL_FEATURE_COVERAGE.md", "")
    for row in report.get("platform_verified_readiness", {}).get("targets", []):
        expected = (
            f"| {row['target']} | {row['platform']} {row['cpu_arch']} | {row['channel']} | "
            f"{row['current_percent']:.1f}% | {row['gap_percent']:.1f}% | {row['status']} |"
        )
        if expected not in full_coverage:
            errors.append(f"docs/FULL_FEATURE_COVERAGE.md missing generated platform row: {expected}")
    overall = report.get("platform_verified_readiness", {}).get("overall", {})
    expected_overall = (
        f"| **Overall** | **All targets** | **mixed** | "
        f"**{overall.get('current_percent', 0.0):.1f}%** | "
        f"**{overall.get('gap_percent', 0.0):.1f}%** | **mixed readiness** |"
    )
    if expected_overall not in full_coverage:
        errors.append(f"docs/FULL_FEATURE_COVERAGE.md missing platform overall row: {expected_overall}")
    return errors


def check_expected_fields(label: str, row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected_value in expected.items():
        if key in {"score", "status"}:
            continue
        actual = row.get(key)
        if actual != expected_value:
            errors.append(f"{label} {key} must be {expected_value!r}, got {actual!r}")
    return errors


def check_readiness_row(target: str, row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if row.get("current_percent") != expected["score"]:
        errors.append(f"{target} readiness score must be {expected['score']}%, got {row.get('current_percent')}%")
    if row.get("gap_percent") != round(100.0 - float(expected["score"]), 1):
        errors.append(f"{target} readiness gap must match score {expected['score']}%")
    if row.get("status") != expected["status"]:
        errors.append(f"{target} readiness status must be {expected['status']}, got {row.get('status')}")
    if float(expected["score"]) < 100.0 and row.get("status") == "verified-default-native":
        errors.append(f"{target} partial target must not report verified-default-native")
    return errors


def expected_platform_overall(platform_targets: dict[str, Any]) -> float:
    expected_scores: list[float] = []
    for item in platform_targets.get("release_architectures", []):
        expected = EXPECTED_ARCHITECTURES.get(str(item.get("id")))
        if expected:
            expected_scores.append(float(expected["score"]))
    for item in platform_targets.get("windows_legacy_targets", []):
        expected = EXPECTED_LEGACY_WINDOWS.get(str(item.get("version")))
        if expected:
            expected_scores.append(float(expected["score"]))
    if not expected_scores:
        return 0.0
    return round(sum(expected_scores) / len(expected_scores), 1)


def rows_by_key(raw_rows: Any, key: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_rows, list):
        errors.append(f"platform support rows for {key} must be a list")
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for item in raw_rows:
        if not isinstance(item, dict):
            errors.append(f"platform support row for {key} must be an object")
            continue
        row_key = str(item.get(key, ""))
        if not row_key:
            errors.append(f"platform support row missing key: {key}")
            continue
        if row_key in rows:
            errors.append(f"duplicate platform support row: {row_key}")
            continue
        rows[row_key] = item
    return rows


def searchable_target_text(row: dict[str, Any]) -> str:
    parts = [str(row.get("host_support", ""))]
    parts.extend(str(item) for item in row.get("notes", []) if isinstance(item, str))
    return " ".join(parts)


def read_docs(required: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in required
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\|", "|")).strip()


def clone_json(data: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(data)


if __name__ == "__main__":
    raise SystemExit(main())
