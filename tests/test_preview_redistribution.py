from __future__ import annotations

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import patch

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


def test_source_archive_records_pin_official_urls_versions_and_upstream_digests() -> None:
    module = checker()
    upstream_digests = {
        "pyqt6_source": "45dd60aa69976de1918b5ced6b4e7b6a25abd2a919ecef5fd5826ecc76718889",
        "qt_source": "6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33",
    }
    with patch.object(module, "fetch_upstream_checksum", side_effect=lambda key, _url, _filename: upstream_digests[key]):
        materials = module.evidence_materials(Path("redistribution-evidence"), "v1.0.27")
        records = module.source_archive_records(materials)

    assert records["pyqt6_source"] == {
        "component": "PyQt6",
        "version": "6.11.0",
        "filename": "pyqt6-6.11.0.tar.gz",
        "url": "https://files.pythonhosted.org/packages/8b/47/b25c13eca5bebc6505394d0223e46d7ebf0c57dcac2ed908d7d19b18ab6b/pyqt6-6.11.0.tar.gz",
        "sha256": "45dd60aa69976de1918b5ced6b4e7b6a25abd2a919ecef5fd5826ecc76718889",
        "upstream_checksum_page": "https://pypi.org/pypi/PyQt6/6.11.0/json",
    }
    assert records["qt_source"]["version"] == "6.11.2"
    assert records["qt_source"]["filename"] == "qt-everywhere-src-6.11.2.tar.xz"
    assert records["qt_source"]["url"].startswith("https://download.qt.io/official_releases/")
    assert records["qt_source"]["sha256"] == "6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33"


def test_official_checksum_parsers_extract_pinned_archive_digests() -> None:
    module = checker()
    filename = "pyqt6-6.11.0.tar.gz"
    digest = "45dd60aa69976de1918b5ced6b4e7b6a25abd2a919ecef5fd5826ecc76718889"
    pypi_payload = json.dumps({
        "urls": [{
            "filename": filename,
            "packagetype": "sdist",
            "digests": {"sha256": digest},
        }],
    }).encode()
    assert module.parse_upstream_checksum(pypi_payload, "pyqt6_source", filename) == digest

    qt_filename = "qt-everywhere-src-6.11.2.tar.xz"
    qt_digest = "6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33"
    qt_payload = (
        f"<h2>Mirrors for {qt_filename}</h2><dt>SHA-256 Hash:</dt><dd>{qt_digest}</dd>"
    ).encode()
    assert module.parse_upstream_checksum(qt_payload, "qt_source", qt_filename) == qt_digest


def test_upstream_digest_mismatch_fails_closed() -> None:
    module = checker()
    with patch.object(module, "fetch_upstream_checksum", return_value="0" * 64):
        with pytest.raises(ValueError, match="does not match the official upstream checksum"):
            module.evidence_materials(Path("redistribution-evidence"), "v1.0.27")


def test_source_archive_record_rejects_unpinned_hosts_or_versions(tmp_path: Path) -> None:
    module = checker()
    record = json.loads(Path("redistribution-evidence/PyQt6-6.11.0-source.json").read_text())
    record["url"] = "https://attacker.example/pyqt6-6.11.0.tar.gz"
    path = tmp_path / "source.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="official upstream archive"):
        module.source_archive_record(path, "pyqt6_source")


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
