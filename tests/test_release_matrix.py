import importlib.util
import json
import sys
from pathlib import Path

from remote_ops_workspace.platform_targets import load_platform_targets


def load_release_matrix_checker():
    path = Path("scripts/check_release_matrix.py")
    spec = importlib.util.spec_from_file_location("check_release_matrix", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_release_matrix.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_release_matrix"] = module
    spec.loader.exec_module(module)
    return module


def load_release_matrix() -> dict[str, object]:
    return json.loads(Path("configs/release_matrix.json").read_text(encoding="utf-8"))


def test_release_matrix_declares_default_native_jobs() -> None:
    matrix = load_release_matrix()
    jobs = {
        item["job"]: item
        for item in matrix["default_github_release"]["native_jobs"]  # type: ignore[index]
    }
    assert jobs["windows-native"]["arches"] == ["x86", "x64", "arm64"]
    assert jobs["macos-native"]["arches"] == ["x64", "arm64"]
    assert jobs["linux-native"]["arches"] == ["x86_64", "aarch64"]
    assert "linux-i386" not in jobs["linux-native"]["platform_target_ids"]
    assert "linux-armhf" not in jobs["linux-native"]["platform_target_ids"]


def test_release_matrix_separates_script_supported_linux_targets() -> None:
    matrix = load_release_matrix()
    script_rows = {
        item["platform_target_id"]: item
        for item in matrix["script_supported_native"]  # type: ignore[index]
    }
    script_targets = set(script_rows)
    assert script_targets == {"linux-i386", "linux-armhf"}
    assert (
        "remote-ops-workspace-v1.0.7-linux-i686-native-SHA256SUMS.txt"
        in script_rows["linux-i386"]["asset_patterns"]
    )
    assert (
        "remote-ops-workspace-v1.0.7-linux-armhf-native-SHA256SUMS.txt"
        in script_rows["linux-armhf"]["asset_patterns"]
    )

    platform_targets = load_platform_targets()
    rows = {item["id"]: item for item in platform_targets["release_architectures"]}
    for target_id in script_targets:
        assert rows[target_id]["release_tier"] == "script-supported-native"
        assert rows[target_id]["github_release_channel"] == "manual-script-native"
        assert set(script_rows[target_id]["asset_patterns"]) == set(rows[target_id]["assets"])


def test_release_matrix_declares_opt_in_protected_platform_promotion() -> None:
    matrix = load_release_matrix()
    promotion = matrix["protected_platform_promotion"]  # type: ignore[index]

    assert promotion["workflow_input"] == "include_protected_platform_evidence"
    assert promotion["evidence_job"] == "accepted-platform-evidence-assets"
    assert promotion["publish_job"] == "publish-protected-platform-evidence"
    assert set(promotion["targets"]) == {
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    }


def test_release_matrix_requires_real_32_bit_linux_builder_identity() -> None:
    checker = load_release_matrix_checker()
    matrix = load_release_matrix()
    platform_targets = load_platform_targets()
    matrix["script_supported_native"][0]["builder_requirement"] = "Run on any Linux host."

    errors = checker.check_platform_target_alignment(matrix, platform_targets)

    assert "linux-i386 builder_requirement must mention dpkg --print-architecture=i386" in errors
    assert "linux-i386 builder_requirement must mention getconf LONG_BIT=32" in errors
    assert "linux-i386 builder_requirement must mention rpm" in errors
    assert "linux-i386 builder_requirement must mention sudo -n true" in errors


def test_release_matrix_requires_script_supported_checksum_asset_pattern() -> None:
    checker = load_release_matrix_checker()
    matrix = load_release_matrix()
    platform_targets = load_platform_targets()
    matrix["script_supported_native"][0]["asset_patterns"].remove(
        "remote-ops-workspace-v1.0.7-linux-i686-native-SHA256SUMS.txt"
    )

    errors = checker.check_platform_target_alignment(matrix, platform_targets)

    assert "linux-i386 asset_patterns must include native SHA256SUMS sidecar" in errors
    assert any(
        "linux-i386 asset_patterns must match platform_targets assets" in error
        and "remote-ops-workspace-v1.0.7-linux-i686-native-SHA256SUMS.txt" in error
        for error in errors
    )


def test_release_matrix_rejects_stale_native_asset_pattern_versions() -> None:
    checker = load_release_matrix_checker()
    matrix = load_release_matrix()
    matrix["default_github_release"]["native_jobs"][2]["asset_patterns"][0] = (
        "remote-ops-workspace-v9.9.9-linux-<amd64|arm64>.deb"
    )
    matrix["script_supported_native"][0]["asset_patterns"][0] = (
        "remote-ops-workspace-v9.9.9-linux-i386.deb"
    )

    errors = checker.check_release_asset_pattern_versions(matrix)

    assert (
        "linux-native asset pattern must use current project version v1.0.7: "
        "remote-ops-workspace-v9.9.9-linux-<amd64|arm64>.deb"
    ) in errors
    assert (
        "linux-i386 asset pattern must use current project version v1.0.7: "
        "remote-ops-workspace-v9.9.9-linux-i386.deb"
    ) in errors


def test_release_matrix_docs_require_script_supported_asset_patterns(monkeypatch) -> None:
    checker = load_release_matrix_checker()
    matrix = load_release_matrix()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "docs/PLATFORM_PROMOTION_RUNBOOK.md":
            return text.replace(
                "- `remote-ops-workspace-v<project.version>-linux-i686-native-SHA256SUMS.txt`\n",
                "",
            )
        return text

    monkeypatch.setattr(checker, "read", fake_read)

    errors = checker.check_release_docs(matrix)

    assert (
        "release docs missing matrix asset pattern: "
        "remote-ops-workspace-v1.0.7-linux-i686-native-SHA256SUMS.txt"
    ) in errors


def test_release_matrix_keeps_mobile_web_targets_in_source_web_group() -> None:
    matrix = load_release_matrix()
    source_web_targets: set[str] = set()
    for item in matrix["source_or_remote_only"]:  # type: ignore[index]
        source_web_targets.update(item.get("platform_target_ids", []))

    assert {"android-armv7", "android-arm64", "ios-web"}.issubset(source_web_targets)

    rows = {item["id"]: item for item in load_platform_targets()["release_architectures"]}
    assert rows["android-armv7"]["github_release_channel"] == "default-termux-web"
    assert rows["android-arm64"]["github_release_channel"] == "default-termux-web"
    assert rows["ios-web"]["github_release_channel"] == "default-web-pwa"


def test_release_matrix_checker_passes() -> None:
    checker = load_release_matrix_checker()
    assert checker.main() == 0
