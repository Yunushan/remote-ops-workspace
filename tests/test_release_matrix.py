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
    script_targets = {
        item["platform_target_id"]
        for item in matrix["script_supported_native"]  # type: ignore[index]
    }
    assert script_targets == {"linux-i386", "linux-armhf"}

    platform_targets = load_platform_targets()
    rows = {item["id"]: item for item in platform_targets["release_architectures"]}
    for target_id in script_targets:
        assert rows[target_id]["release_tier"] == "script-supported-native"
        assert rows[target_id]["github_release_channel"] == "manual-script-native"


def test_release_matrix_checker_passes() -> None:
    checker = load_release_matrix_checker()
    assert checker.main() == 0
