from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HEAD_SHA = "a" * 40


def test_import_record_downloads_expected_files_and_verifies_hashes(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    download_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"

    commands: list[list[str]] = []

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert check is True
        if command[:3] == ["gh", "run", "view"]:
            assert kwargs == {"capture_output": True, "text": True}
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "status": "completed",
                        "conclusion": "success",
                        "event": "workflow_dispatch",
                        "headSha": HEAD_SHA,
                        "workflowName": "extended-platform-evidence",
                    }
                ),
            )
        assert kwargs == {}
        assert command[:6] == ["gh", "run", "download", "12345", "--repo", "example/remote-ops-workspace"]
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
        release_head_sha=HEAD_SHA,
    )

    assert errors == []
    assert commands[0] == [
        "gh",
        "run",
        "view",
        "12345",
        "--repo",
        "example/remote-ops-workspace",
        "--json",
        "conclusion,event,headSha,status,workflowName",
    ]
    assert commands[1][:4] == ["gh", "run", "download", "12345"]
    assert sorted(path.name for path in out_dir.iterdir()) == sorted(importer.expected_release_files(record))


def test_import_record_rejects_missing_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        Path(command[-1]).mkdir(parents=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any("downloaded artifact missing expected release file" in error for error in errors)


def test_import_record_rejects_missing_final_record_source_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            if source_path.name == "platform-verified-evidence-linux-i386-final.json":
                continue
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 downloaded artifact missing expected release file: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_import_record_rejects_final_record_source_file_drift(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        final_record = destination / "platform-verified-evidence-linux-i386-final.json"
        data = json.loads(final_record.read_text(encoding="utf-8"))
        data["readiness_percent"] = 99.0
        final_record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 finalized accepted record source file must match accepted registry record: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_import_record_rejects_unexpected_downloaded_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        (destination / "operator-private-builder.log").write_text("raw builder output\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 downloaded artifact contains unexpected files: ['operator-private-builder.log']" in errors


def test_import_record_rejects_nested_downloaded_artifact_directory(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        destination = Path(command[-1])
        nested = destination / "native-dist"
        nested.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        (nested / "raw-smoke.log").write_text("raw nested output\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert "linux-i386 downloaded artifact must contain root files only, found directories: ['native-dist']" in errors


def test_validate_downloaded_source_file_set_rejects_symlinked_source(
    tmp_path: Path, monkeypatch
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    source_root.mkdir()
    for source in record["_source_files"]:
        source_path = Path(str(source))
        (source_root / source_path.name).write_bytes(source_path.read_bytes())

    symlink_name = "platform-verified-evidence-linux-i386-final.json"

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.validate_downloaded_source_file_set(
        "linux-i386",
        source_root=source_root,
        expected_files=importer.expected_source_files(record),
    )

    assert f"linux-i386 downloaded artifact must not contain symlinks: ['{symlink_name}']" in errors


def test_copy_expected_files_rejects_symlinked_source(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    source_root = tmp_path / "download"
    out_dir = tmp_path / "release-assets"
    source_root.mkdir()
    expected_files = importer.expected_release_files(record)
    for source in record["_source_files"]:
        source_path = Path(str(source))
        if source_path.name in expected_files:
            (source_root / source_path.name).write_bytes(source_path.read_bytes())
    symlink_name = sorted(expected_files)[0]

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(source_root), "is_symlink", fake_is_symlink)

    errors = importer.copy_expected_files(record, source_root=source_root, out_dir=out_dir)

    assert f"linux-i386 release asset import source must not be a symlink: {symlink_name}" in errors
    assert not (out_dir / symlink_name).exists()


def test_import_record_rejects_overwrite_with_different_file(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    out_dir = tmp_path / "release-assets"
    out_dir.mkdir()
    first_asset = next(iter(record["artifact_sha256"]))
    (out_dir / str(first_asset)).write_bytes(b"different\n")

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
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
        release_head_sha=HEAD_SHA,
    )

    assert any("release asset import would overwrite different file" in error for error in errors)


def test_import_record_rejects_failed_source_workflow_run(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "workflowName": "extended-platform-evidence",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run conclusion must be success, got 'failure'"
        in errors
    )


def test_import_record_rejects_source_workflow_path_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["release_asset_source"]["workflow"] = ".github/workflows/xp-native-evidence.yml"

    def fail_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise AssertionError("gh should not run when release_asset_source.workflow is wrong")

    monkeypatch.setattr(importer.subprocess, "run", fail_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source.workflow must be "
        ".github/workflows/extended-platform-evidence.yml"
    ) in errors


def test_import_record_rejects_incomplete_or_non_dispatch_source_workflow_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "in_progress",
                    "conclusion": None,
                    "event": "push",
                    "headSha": HEAD_SHA,
                    "workflowName": "other-workflow",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run status must be completed, got 'in_progress'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run conclusion must be success, got None"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run event must be workflow_dispatch, got 'push'"
        in errors
    )
    assert (
        "linux-i386 release_asset_source workflow run name must be 'extended-platform-evidence', "
        "got 'other-workflow'"
    ) in errors


def test_import_record_rejects_source_workflow_name_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "workflowName": "ci",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "linux-i386 release_asset_source workflow run name must be 'extended-platform-evidence', got 'ci'"
        in errors
    )


def test_import_record_rejects_xp_source_workflow_name_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)
    record["target"] = "windows-xp-native-x86"
    record["release_asset_source"]["workflow"] = ".github/workflows/xp-native-evidence.yml"
    record["release_asset_source"]["artifact_name"] = "xp-native-evidence-windows-xp-native-x86-v1.0.2"

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": HEAD_SHA,
                    "workflowName": "extended-platform-evidence",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        "windows-xp-native-x86 release_asset_source workflow run name must be 'xp-native-evidence', "
        "got 'extended-platform-evidence'"
    ) in errors


def test_import_record_rejects_source_workflow_head_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "headSha": "b" * 40,
                    "workflowName": "extended-platform-evidence",
                }
            ),
        )

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert (
        f"linux-i386 release_asset_source workflow run headSha must match accepted record {HEAD_SHA}, "
        f"got '{'b' * 40}'"
    ) in errors


def test_import_record_rejects_release_checkout_head_sha_mismatch(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["gh", "run", "view"]
        return _successful_view(command)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha="c" * 40,
    )

    assert (
        f"linux-i386 release_asset_source.head_sha must match release checkout {'c' * 40}, got {HEAD_SHA}"
        in errors
    )


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
    assert "gh run view 12345 --repo example/remote-ops-workspace" in captured.out
    assert "gh run download 12345 --repo example/remote-ops-workspace" in captured.out
    assert "--name extended-linux-evidence-linux-i386-v1.0.2" in captured.out


def test_expected_release_files_includes_native_and_review_bundle_files(tmp_path: Path) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    expected_files = set(record["artifact_sha256"])
    expected_files.update(
        str(record["review_bundle"][key]["file"])
        for key in ("manifest", "archive", "sha256s")
    )

    assert importer.expected_release_files(record) == expected_files


def test_import_record_rejects_tampered_review_bundle_content(tmp_path: Path, monkeypatch) -> None:
    importer = _load_importer()
    record = _record(tmp_path)

    def fake_run(command: list[str], check: bool, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["gh", "run", "view"]:
            return _successful_view(command)
        destination = Path(command[-1])
        destination.mkdir(parents=True)
        for source in record["_source_files"]:
            source_path = Path(str(source))
            (destination / source_path.name).write_bytes(source_path.read_bytes())
        manifest_name = str(record["review_bundle"]["manifest"]["file"])
        manifest_path = destination / manifest_name
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["candidate_record"]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        record["review_bundle"]["manifest"]["sha256"] = _sha256(manifest_path)
        final_record = destination / "platform-verified-evidence-linux-i386-final.json"
        final_record.write_text(json.dumps(importer.public_record(record), indent=2) + "\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(importer.subprocess, "run", fake_run)

    errors = importer.import_record(
        record,
        out_dir=tmp_path / "release-assets",
        download_root=tmp_path / "download",
        dry_run=False,
        release_head_sha=HEAD_SHA,
    )

    assert any(
        "linux-i386 imported review bundle validation failed: "
        "linux-i386 review bundle manifest candidate_record.sha256 must match "
        "platform-verified-evidence-linux-i386.json"
        in error
        for error in errors
    )


def _record(tmp_path: Path) -> dict[str, Any]:
    review_helpers = _load_platform_review_bundle_helpers()
    bundle_helpers = _load_finalize_tests()
    record = review_helpers._finalized_linux_record(tmp_path)
    artifact_hashes = record["artifact_sha256"]
    assert isinstance(artifact_hashes, dict)
    for filename in sorted(str(name) for name in artifact_hashes):
        (tmp_path / filename).write_bytes(bundle_helpers._artifact_payload(filename))
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    final_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    source_files = [tmp_path / str(name) for name in artifact_hashes]
    source_files.extend(
        tmp_path / str(record["review_bundle"][key]["file"])
        for key in ("manifest", "archive", "sha256s")
    )
    source_files.append(final_record)
    return {**record, "_source_files": source_files}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _successful_view(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        command,
        0,
        stdout=json.dumps(
            {
                "status": "completed",
                "conclusion": "success",
                "event": "workflow_dispatch",
                "headSha": HEAD_SHA,
                "workflowName": "extended-platform-evidence",
            }
        ),
    )


def _load_importer() -> Any:
    path = Path("scripts/import_platform_evidence_artifacts.py")
    spec = importlib.util.spec_from_file_location("import_platform_evidence_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_review_bundle_helpers() -> Any:
    path = Path("tests/test_platform_review_bundle_artifacts.py")
    spec = importlib.util.spec_from_file_location("platform_review_bundle_import_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_evidence_import_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
