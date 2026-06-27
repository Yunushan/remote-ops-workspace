from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def test_stage_extended_linux_evidence_upload_copies_only_expected_files(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    staged = tmp_path / "linux-evidence-upload"
    source.mkdir(parents=True)
    expected_artifacts = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"extended-linux-evidence-bundle-{target}-{tag}.json",
        f"extended-linux-evidence-bundle-{target}-{tag}.zip",
        f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in [*expected_artifacts, *expected_evidence]:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (source / name).write_bytes(f"{name}\n".encode())
    _write_linux_final_record(source / f"platform-verified-evidence-{target}-final.json", target, source)

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=staged,
    )

    assert errors == []
    assert sorted(path.name for path in staged.iterdir()) == sorted(
        {*expected_artifacts, *expected_evidence}
    )


def test_stage_extended_linux_evidence_upload_rejects_extra_source_entries(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    source.mkdir(parents=True)
    expected_artifacts = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"extended-linux-evidence-bundle-{target}-{tag}.json",
        f"extended-linux-evidence-bundle-{target}-{tag}.zip",
        f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in [*expected_artifacts, *expected_evidence]:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (source / name).write_bytes(f"{name}\n".encode())
    _write_linux_final_record(source / f"platform-verified-evidence-{target}-final.json", target, source)
    (source / "native-smoke-linux-i386-working-copy.log").write_text(
        "raw smoke working copy is not bundled\n",
        encoding="utf-8",
    )
    (source / "builder-scratch").mkdir()

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert (
        "linux-i386 extended Linux evidence source directory contains files outside staged upload set: "
        "['builder-scratch', 'native-smoke-linux-i386-working-copy.log']"
    ) in errors


def test_stage_extended_linux_evidence_upload_rejects_hash_mismatch(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    source.mkdir(parents=True)
    expected_artifacts = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"extended-linux-evidence-bundle-{target}-{tag}.json",
        f"extended-linux-evidence-bundle-{target}-{tag}.zip",
        f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in [*expected_artifacts, *expected_evidence]:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (source / name).write_bytes(f"{name}\n".encode())
    _write_linux_final_record(source / f"platform-verified-evidence-{target}-final.json", target, source)
    (source / expected_artifacts[0]).write_text("tampered artifact\n", encoding="utf-8")
    (source / f"extended-linux-evidence-bundle-{target}-{tag}.zip").write_text(
        "tampered review bundle\n",
        encoding="utf-8",
    )

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert any("staged upload native artifact SHA-256 mismatch" in error for error in errors)
    assert any("staged upload review_bundle archive.sha256 mismatch" in error for error in errors)


def test_stage_extended_linux_evidence_upload_rejects_review_bundle_content_mismatch(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    source.mkdir(parents=True)
    expected_artifacts = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"extended-linux-evidence-bundle-{target}-{tag}.json",
        f"extended-linux-evidence-bundle-{target}-{tag}.zip",
        f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in [*expected_artifacts, *expected_evidence]:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (source / name).write_bytes(f"{name}\n".encode())
    final_record = source / f"platform-verified-evidence-{target}-final.json"
    _write_linux_final_record(final_record, target, source)
    record = json.loads(final_record.read_text(encoding="utf-8"))
    archive_name = f"extended-linux-evidence-bundle-{target}-{tag}.zip"
    archive_path = source / archive_name
    archive_path.write_text("not a readable review bundle\n", encoding="utf-8")
    record["review_bundle"]["archive"]["sha256"] = _sha256(archive_path)
    record["review_bundle"]["archive"]["size_bytes"] = archive_path.stat().st_size
    final_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert any(
        "staged upload review bundle failed re-finalization" in error
        and "review bundle archive is not a readable ZIP" in error
        for error in errors
    )


def test_stage_extended_linux_evidence_upload_rejects_release_source_file_set_drift() -> None:
    stager = _load_stager()
    record = {
        "release_asset_source": {
            "contains_files": [
                "expected.deb",
                "platform-verified-evidence-linux-i386-final.json",
            ],
        },
    }
    sources = {
        "expected.deb": Path("expected.deb"),
        "unexpected.zip": Path("unexpected.zip"),
    }

    errors = stager.check_release_source_file_set("linux-i386", record, sources)

    assert (
        "linux-i386 staged upload missing release_asset_source files: "
        "['platform-verified-evidence-linux-i386-final.json']"
    ) in errors
    assert "linux-i386 staged upload has files outside release_asset_source: ['unexpected.zip']" in errors


def test_stage_extended_linux_evidence_upload_rejects_symlinked_source_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    source = tmp_path / "native-dist" / "linux"
    source.mkdir(parents=True)

    def fake_is_symlink(path: Path) -> bool:
        return path == source

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.stage_extended_linux_evidence_upload(
        target="linux-i386",
        release_tag="v1.0.2",
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert f"extended Linux evidence source directory must not be a symlink: {source}" in errors


def test_stage_extended_linux_evidence_upload_rejects_file_shaped_source_directory(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    source = tmp_path / "linux-evidence.zip"
    source.mkdir()

    errors = stager.stage_extended_linux_evidence_upload(
        target="linux-i386",
        release_tag="v1.0.2",
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert (
        f"extended Linux evidence source directory must be a directory path, got {source.as_posix()!r}"
    ) in errors


def test_stage_extended_linux_evidence_upload_rejects_symlinked_source(monkeypatch) -> None:
    stager = _load_stager()
    sources = {
        "expected.deb": Path("expected.deb"),
        "platform-verified-evidence-linux-i386-final.json": Path("platform-verified-evidence-linux-i386-final.json"),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path.name == "platform-verified-evidence-linux-i386-final.json"

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("linux-i386", sources)

    assert (
        "linux-i386 staged upload source must not be a symlink: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_stage_extended_linux_evidence_upload_rejects_symlinked_source_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    source_parent = tmp_path / "linked-source"
    sources = {
        "expected.deb": source_parent / "expected.deb",
        "platform-verified-evidence-linux-i386-final.json": (
            source_parent / "platform-verified-evidence-linux-i386-final.json"
        ),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path == source_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("linux-i386", sources)

    assert (
        f"linux-i386 staged upload source expected.deb path must not contain symlinked directories: {source_parent}"
    ) in errors
    assert (
        "linux-i386 staged upload source platform-verified-evidence-linux-i386-final.json "
        f"path must not contain symlinked directories: {source_parent}"
    ) in errors


def test_stage_extended_linux_evidence_upload_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "linux-evidence-upload"
    out_dir.mkdir()

    def fake_is_symlink(path: Path) -> bool:
        return path == out_dir

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory("linux-i386", out_dir=out_dir, force=True)

    assert errors == [
        f"linux-i386 staged upload output directory must not be a symlink: {out_dir}"
    ]


def test_stage_extended_linux_evidence_upload_rejects_file_shaped_output_directory(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "linux-evidence-upload.zip"

    errors = stager.prepare_output_directory("linux-i386", out_dir=out_dir, force=False)

    assert errors == [
        f"linux-i386 staged upload output directory must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_stage_extended_linux_evidence_upload_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_parent = tmp_path / "linked-upload"
    out_dir = out_parent / "linux-evidence-upload"

    def fake_is_symlink(path: Path) -> bool:
        return path == out_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory("linux-i386", out_dir=out_dir, force=True)

    assert errors == [
        f"linux-i386 staged upload output directory path must not contain symlinked directories: {out_parent}"
    ]


def test_stage_extended_linux_evidence_upload_rejects_symlinked_output_child(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "linux-evidence-upload"
    out_dir.mkdir()
    child = out_dir / "old-upload-file.zip"
    child.write_text("old upload\n", encoding="utf-8")

    def fake_is_symlink(path: Path) -> bool:
        return path == child

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory("linux-i386", out_dir=out_dir, force=True)

    assert errors == [
        "linux-i386 staged upload output must not contain symlinks: old-upload-file.zip"
    ]
    assert child.exists()


def test_stage_extended_linux_evidence_upload_rejects_unsafe_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    symlink_destination = tmp_path / "linux-evidence-upload" / "expected.deb"
    directory_destination = tmp_path / "linux-evidence-upload" / "expected.rpm"
    directory_destination.mkdir(parents=True)

    def fake_is_symlink(path: Path) -> bool:
        return path == symlink_destination

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    assert stager.check_destination_path("linux-i386", symlink_destination, "expected.deb") == [
        "linux-i386 staged upload destination must not be a symlink: expected.deb"
    ]
    assert stager.check_destination_path("linux-i386", directory_destination, "expected.rpm") == [
        "linux-i386 staged upload destination must be a regular file: expected.rpm"
    ]


def test_stage_extended_linux_evidence_upload_rejects_staged_output_drift(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "linux-evidence-upload"
    out_dir.mkdir()
    (out_dir / "expected.deb").write_text("drifted artifact\n", encoding="utf-8")
    (out_dir / "unexpected.txt").write_text("unexpected upload file\n", encoding="utf-8")
    (out_dir / "nested").mkdir()
    expected_hashes = {
        "expected.deb": hashlib.sha256(b"expected artifact\n").hexdigest(),
        "missing.rpm": hashlib.sha256(b"missing rpm\n").hexdigest(),
    }

    errors = stager.check_staged_output(
        "linux-i386",
        out_dir=out_dir,
        expected_hashes=expected_hashes,
    )

    assert "linux-i386 staged upload output contains non-file entries: ['nested']" in errors
    assert "linux-i386 staged upload output missing expected files: ['missing.rpm']" in errors
    assert "linux-i386 staged upload output contains unexpected files: ['unexpected.txt']" in errors
    assert "linux-i386 staged upload output SHA-256 mismatch: expected.deb" in errors


def test_stage_extended_linux_evidence_upload_rejects_missing_expected_file(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    source.mkdir(parents=True)

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert errors
    assert any(f"{target} staged upload missing expected files" in error for error in errors)


def test_stage_extended_linux_evidence_upload_rejects_invalid_final_record(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = _linux_source_dir(tmp_path, target, tag)
    source.mkdir(parents=True)
    expected_artifacts = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"extended-linux-evidence-bundle-{target}-{tag}.json",
        f"extended-linux-evidence-bundle-{target}-{tag}.zip",
        f"extended-linux-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in [*expected_artifacts, *expected_evidence]:
        (source / name).write_bytes(f"{name}\n".encode())
    (source / f"platform-verified-evidence-{target}-final.json").write_text("{}\n", encoding="utf-8")

    errors = stager.stage_extended_linux_evidence_upload(
        target=target,
        release_tag=tag,
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert any(
        f"{target} finalized accepted record failed strict validation" in error
        for error in errors
    )


def test_stage_extended_linux_evidence_upload_rejects_unscoped_source_directory(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    source = tmp_path / "native-dist" / "linux"
    source.mkdir(parents=True)

    errors = stager.stage_extended_linux_evidence_upload(
        target="linux-i386",
        release_tag="v1.0.2",
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert (
        "extended Linux evidence source directory must include target path segment "
        f"'linux-i386', got {source.as_posix()!r}"
    ) in errors
    assert (
        "extended Linux evidence source directory must include release_tag path segment "
        f"'v1.0.2', got {source.as_posix()!r}"
    ) in errors


def test_stage_extended_linux_evidence_upload_rejects_nonadjacent_target_release_scope(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    source = tmp_path / "platform-evidence-staging" / "v1.0.2" / "linux-i386" / "artifacts"
    source.mkdir(parents=True)

    errors = stager.stage_extended_linux_evidence_upload(
        target="linux-i386",
        release_tag="v1.0.2",
        source_dir=source,
        out_dir=tmp_path / "upload",
    )

    assert errors == [
        "extended Linux evidence source directory must include adjacent target/release path segment "
        f"linux-i386/v1.0.2, got {source.as_posix()!r}"
    ]


def test_stage_extended_linux_evidence_upload_rejects_overlapping_output_path(tmp_path: Path) -> None:
    stager = _load_stager()
    source = tmp_path / "native-dist" / "linux"
    source.mkdir(parents=True)

    errors = stager.stage_extended_linux_evidence_upload(
        target="linux-i386",
        release_tag="v1.0.2",
        source_dir=source,
        out_dir=source / "linux-evidence-upload",
    )

    assert (
        "linux-i386 extended Linux evidence source directory and staged upload output "
        "directory must be separate roots"
    ) in errors


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _linux_source_dir(tmp_path: Path, target: str, tag: str) -> Path:
    return tmp_path / "platform-evidence-staging" / target / tag / "artifacts"


def _write_linux_final_record(path: Path, target: str, source_dir: Path) -> None:
    assert target == "linux-i386"
    review_helpers = _load_platform_review_bundle_helpers()
    bundle_helpers = _load_finalize_helpers()
    record = review_helpers._finalized_linux_record(source_dir)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            (source_dir / str(name)).write_bytes(bundle_helpers._artifact_payload(str(name)))
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_stager() -> Any:
    path = Path("scripts/stage_extended_linux_evidence_upload.py")
    spec = importlib.util.spec_from_file_location("stage_extended_linux_evidence_upload", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_review_bundle_helpers() -> Any:
    path = Path("tests/test_platform_review_bundle_artifacts.py")
    spec = importlib.util.spec_from_file_location("platform_review_bundle_stage_linux_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_helpers() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_evidence_stage_linux_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker() -> Any:
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
