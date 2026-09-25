from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def checker():
    path = ROOT / "scripts" / "check_preview_redistribution.py"
    spec = importlib.util.spec_from_file_location("check_preview_redistribution", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_package_inventory_matches_real_release_matrix() -> None:
    module = checker()
    names = module.expected_native_assets("v1.0.27")
    assert len(names) == 35
    assert len([name for name in names if module.NATIVE_PACKAGE.fullmatch(name)]) == 21
    assert {target: len(module.target_asset_names("v1.0.27", target)) for target in module.BUILD_TARGETS} == {
        "windows-x86": 5,
        "windows-x64": 5,
        "windows-arm64": 5,
        "macos-x64": 4,
        "macos-arm64": 4,
        "linux-x86_64": 6,
        "linux-aarch64": 6,
    }


def test_missing_evidence_fails_before_native_publication(tmp_path: Path) -> None:
    module = checker()
    with pytest.raises(ValueError, match="preview evidence manifest.*missing"):
        module.evidence_materials(tmp_path / "redistribution-evidence", "v1.0.27")


def test_commercial_channel_has_no_self_asserted_bypass(tmp_path: Path) -> None:
    module = checker()
    evidence = tmp_path / "redistribution-evidence"
    evidence.mkdir()
    (evidence / "preview.json").write_text(
        json.dumps({"schema_version": 1, "release_tag": "v1.0.27", "channel": "commercial", "materials": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="verifiable vendor grant"):
        module.evidence_materials(evidence, "v1.0.27")


def test_packaged_license_bytes_are_read_from_real_archives(tmp_path: Path) -> None:
    module = checker()
    zip_path = tmp_path / "portable.zip"
    tar_path = tmp_path / "portable.tar.gz"
    payload = b"Third party release notices\n"
    with zipfile.ZipFile(zip_path, "w") as package:
        package.writestr("docs/THIRD_PARTY_NOTICES.md", payload)
    with tarfile.open(tar_path, "w:gz") as package:
        member = tarfile.TarInfo("usr/share/doc/THIRD_PARTY_NOTICES.md")
        member.size = len(payload)
        package.addfile(member, io.BytesIO(payload))
    assert module.embedded_file_bytes(zip_path, "THIRD_PARTY_NOTICES.md") == payload
    assert module.embedded_file_bytes(tar_path, "THIRD_PARTY_NOTICES.md") == payload
    assert module.embedded_file_bytes(zip_path, "PyQt6-GPL-3.0.txt") is None


def test_builder_inventory_rejects_unhashed_native_bytes(tmp_path: Path) -> None:
    module = checker()
    assets = tmp_path / "assets"
    inventories = tmp_path / "inventory"
    assets.mkdir()
    inventories.mkdir()
    tag = "v1.0.27"
    sha = "a" * 40
    for target in module.BUILD_TARGETS:
        names = module.target_asset_names(tag, target)
        for name in names:
            (assets / name).write_bytes(b"actual asset")
        (inventories / f"{target}.json").write_text(
            json.dumps({
                "schema_version": 1,
                "repository": "owner/project",
                "release_tag": tag,
                "release_sha": sha,
                "target": target,
                "distributions": {"PyQt6": "6.11.0", "PyQt6-Qt6": "6.11.2"},
                "assets_sha256": {name: "0" * 64 for name in names},
            }),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="digest differs"):
        module.check_builder_inventories(inventories, assets, tag, sha, "owner/project")
