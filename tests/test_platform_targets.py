from pathlib import Path

from remote_ops_workspace.cli import main
from remote_ops_workspace.platform_targets import load_platform_targets

REQUIRED_ARCHITECTURES = {
    "windows-x86": 32,
    "windows-x64": 64,
    "windows-arm64": 64,
    "linux-i386": 32,
    "linux-x86_64": 64,
    "linux-armhf": 32,
    "linux-arm64": 64,
    "macos-x64": 64,
    "macos-arm64": 64,
    "android-armv7": 32,
    "android-arm64": 64,
    "ios-web": 64,
}

REQUIRED_LEGACY_WINDOWS = {
    "Windows XP",
    "Windows Vista",
    "Windows 7",
    "Windows 8",
    "Windows 8.1",
}


def test_platform_targets_cover_requested_architectures() -> None:
    targets = load_platform_targets()
    rows = {item["id"]: item for item in targets["release_architectures"]}
    assert set(REQUIRED_ARCHITECTURES).issubset(rows)
    for target_id, bits in REQUIRED_ARCHITECTURES.items():
        row = rows[target_id]
        assert row["bits"] == bits
        assert row["assets"]
        assert row["host_support"]
        assert row["github_release_channel"]
    assert rows["linux-i386"]["release_tier"] == "script-supported-native"
    assert rows["linux-i386"]["github_release_channel"] == "manual-script-native"
    assert rows["linux-armhf"]["release_tier"] == "script-supported-native"
    assert rows["linux-armhf"]["github_release_channel"] == "manual-script-native"
    assert rows["ios-web"]["release_tier"] == "web-pwa"
    assert rows["ios-web"]["github_release_channel"] == "default-web-pwa"
    for target_id in ("windows-x64", "linux-x86_64", "linux-arm64", "macos-arm64"):
        assert rows[target_id]["github_release_channel"] == "default-native"


def test_legacy_windows_targets_are_declared_as_remote_targets() -> None:
    targets = load_platform_targets()
    rows = {item["version"]: item for item in targets["windows_legacy_targets"]}
    assert REQUIRED_LEGACY_WINDOWS.issubset(rows)
    for version in REQUIRED_LEGACY_WINDOWS:
        row = rows[version]
        assert row["remote_target_tier"] == "supported"
        assert row["notes"]
    assert rows["Windows XP"]["remote_target_coverage_percent"] == 100.0
    assert rows["Windows XP"]["architectures"] == ["x86", "x64"]
    assert rows["Windows XP"]["security_profile"] == "isolated-legacy-opt-in"
    assert {"rdp", "vnc", "sshv1", "telnet", "serial"}.issubset(
        rows["Windows XP"]["supported_remote_protocols"]
    )


def test_native_release_scripts_reference_expanded_architectures() -> None:
    root = Path(__file__).resolve().parents[1]
    windows_script = (root / "scripts" / "make_windows_native.ps1").read_text(encoding="utf-8")
    linux_script = (root / "scripts" / "make_linux_native.sh").read_text(encoding="utf-8")
    assert '[ValidateSet("x86", "x64", "arm64")]' in windows_script
    assert "windows-$Arch" in windows_script
    for token in ("i386", "i686", "armv7l", "armhf", "aarch64", "arm64"):
        assert token in linux_script


def test_platforms_cli_reports_architecture_targets(capsys) -> None:
    assert main(["platforms"]) == 0
    output = capsys.readouterr().out
    assert "windows-x86" not in output
    assert "Windows" in output
    assert "x86" in output
    assert "arm64" in output
    assert "Windows XP" in output
    assert "100.0% x86/x64 isolated-legacy-opt-in" in output


def test_features_coverage_cli_reports_missing_platform_evidence(capsys) -> None:
    assert main(["features", "--coverage"]) == 0
    output = capsys.readouterr().out

    assert "linux-i386" in output
    assert "missing evidence linux-i386" in output
    assert "linux-armhf" in output
    assert "missing evidence linux-armhf" in output
    assert "Windows XP" in output
    assert "missing evidence windows-xp-native-x86, windows-xp-native-x64" in output
