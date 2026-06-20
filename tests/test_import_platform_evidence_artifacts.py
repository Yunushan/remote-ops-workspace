from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any


def test_import_record_downloads_expected_files_and_verifies_hashes(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    download_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert command[:6] == [
            "gh",
            "run",
            "download",
            "12345",
            "--repo",
            "example/remote-ops-workspace",
        ]
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=out_dir,
        download_root=download_root,
        dry_run=False,
    )

    assert errors == []
    assert sorted(path.name for path in out_dir.iterdir()) == sorted(importer.expected_release_files(record))


def test_import_record_rejects_missing_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        Path(command[-1]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
    )

    assert any("downloaded artifact missing expected release file" in error for error in errors)


def test_import_record_rejects_overwrite_with_different_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    out_dir.mkdir()
    first_asset = next(iter(record["artifact_sha256"]))
    (out_dir / str(first_asset)).write_bytes(b"different\n")

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=out_dir,
        download_root=tmp_path / "download",
        dry_run=False,
    )

    assert any("release asset import would overwrite different file" in error for error in errors)


def test_import_record_dry_run_prints_gh_download_command(tmp_path: Path, capsys) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=True,
    )

    assert errors == []
    captured = capsys.readouterr()
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out
    assert "--name extended-linux-i386-native-evidence" in captured.out


def test_expected_release_files_includes_native_and_review_bundle_files(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    assert importer.expected_release_files(record) == {
        "remote-ops-workspace-v1.0.2-linux-i386.deb",
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.json",
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
        "extended-linux-evidence-bundle-linux-i386-v1.0.2-SHA256SUMS.txt",
    }


def _record(tmp_path: Path) -> dict[str, Any]:
    native = tmp_path / "remote-ops-workspace-v1.0.2-linux-i386.deb"
    manifest = tmp_path / "extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    archive = tmp_path / "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip"
    sidecar = tmp_path / "extended-linux-evidence-bundle-linux-i386-v1.0.2-SHA256SUMS.txt"
    for path in (native, manifest, archive, sidecar):
        path.write_bytes(f"{path.name}\n".encode())
    return {
        "target": "linux-i386",
        "artifact_sha256": {native.name: _sha256(native)},
        "release_asset_source": {
            "type": "github-actions-artifact",
            "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "artifact_name": "extended-linux-i386-native-evidence",
            "contains_files": [native.name, manifest.name, archive.name, sidecar.name],
        },
        "review_bundle": {
            "manifest": {"file": manifest.name, "sha256": _sha256(manifest)},
            "archive": {"file": archive.name, "sha256": _sha256(archive)},
            "sha256s": {"file": sidecar.name, "sha256": _sha256(sidecar)},
        },
        "_source_files": [native, manifest, archive, sidecar],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_importer() -> Any:
    path = Path("scripts/import_platform_evidence_artifacts.py")
    spec = importlib.util.spec_from_file_location("import_platform_evidence_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
