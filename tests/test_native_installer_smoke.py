from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_native_installer_smoke_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_native_installer_smoke_contract_covers_required_formats() -> None:
    config = json.loads(Path("configs/native_installer_smoke.json").read_text(encoding="utf-8"))
    formats = {
        item["format"]
        for platform in config["platforms"].values()
        for item in platform["formats"]
    }

    assert formats == {"exe", "msi", "dmg", "pkg", "deb", "rpm", "AppImage"}


def test_linux_rpm_smoke_uses_nodeps_on_ubuntu_runner() -> None:
    config = json.loads(Path("configs/native_installer_smoke.json").read_text(encoding="utf-8"))
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")
    rpm_lifecycle = next(
        item["lifecycle"]
        for item in config["platforms"]["linux"]["formats"]
        if item["format"] == "rpm"
    )

    assert "--nodeps" in rpm_lifecycle["install"]
    assert "--nodeps" in rpm_lifecycle["upgrade"]
    assert "--nodeps" in rpm_lifecycle["uninstall"]
    assert "rpm -Uvh --nodeps --replacepkgs" in script
    assert "rpm -e --nodeps remote-ops-workspace" in script


def test_linux_smoke_requires_source_head_sha_for_target_bound_evidence() -> None:
    script = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")

    assert "--source-head-sha is required with --target" in script
    assert "--source-head-sha requires --target" in script
    assert "--source-head-sha must be a 40-character lowercase Git SHA" in script
    assert "native installer smoke source head sha: $SOURCE_HEAD_SHA" in script


def _load_checker():
    path = Path("scripts/check_native_installer_smoke.py")
    spec = importlib.util.spec_from_file_location("native_installer_smoke_checker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
