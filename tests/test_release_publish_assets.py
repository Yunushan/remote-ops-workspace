from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def test_release_publish_asset_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main([]) == 0


def test_expected_release_assets_expand_default_matrix() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix)

    assert "remote_ops_workspace-0.1.0-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v0.1.0-windows-x86-setup.exe" in assets
    assert "remote-ops-workspace-v0.1.0-macos-arm64.pkg" in assets
    assert "remote-ops-workspace-v0.1.0-linux-amd64.deb" in assets
    assert "remote-ops-workspace-v0.1.0-linux-aarch64-native-SHA256SUMS.txt" in assets


def test_publish_contract_requires_validation_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag",
        "python scripts/check_release_matrix.py # disabled publish asset validation",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("publish asset validation" in error for error in errors)


def test_release_assets_report_missing_expected_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    errors = checker.check_release_assets(tmp_path, matrix, tag="v0.1.0")

    assert any("missing expected files" in error for error in errors)


def test_release_assets_accept_complete_synthetic_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v0.1.0")

    assert errors == []


def test_release_assets_reject_checksum_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    checksum = tmp_path / "remote-ops-workspace-v0.1.0-SHA256SUMS.txt"
    checksum.write_text("0" * 64 + "  remote_ops_workspace-0.1.0-py3-none-any.whl\n", encoding="utf-8")

    errors = checker.check_release_assets(tmp_path, matrix, tag="v0.1.0")

    assert any("checksum mismatch" in error for error in errors)


def _write_synthetic_release_assets(checker, matrix: dict[str, object], root: Path) -> None:
    expected = checker.expected_release_assets(matrix, tag="v0.1.0")
    source_manifest_artifacts = checker.expected_source_manifest_artifacts(matrix, tag="v0.1.0")
    release_manifest = "remote-ops-workspace-v0.1.0-release-manifest.json"
    checksum_assets = {asset for asset in expected if asset.endswith("SHA256SUMS.txt")}

    for asset in sorted(expected - checksum_assets - {release_manifest}):
        (root / asset).write_bytes(f"{asset}\n".encode())

    manifest_payload = {
        "schema_version": 1,
        "artifacts": [
            {
                "file": f"dist/{asset}",
                "size_bytes": (root / asset).stat().st_size,
                "sha256": _sha256(root / asset),
            }
            for asset in sorted(source_manifest_artifacts)
        ],
    }
    (root / release_manifest).write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    reference_assets = sorted(expected - checksum_assets)
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in reference_assets) + "\n"
    for checksum in checksum_assets:
        (root / checksum).write_text(checksum_lines, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_matrix() -> dict[str, object]:
    return json.loads(Path("configs/release_matrix.json").read_text(encoding="utf-8"))


def _load_checker():
    path = Path("scripts/check_release_publish_assets.py")
    spec = importlib.util.spec_from_file_location("check_release_publish_assets_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
