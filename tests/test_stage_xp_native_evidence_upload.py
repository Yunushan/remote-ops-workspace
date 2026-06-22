from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def test_stage_xp_native_evidence_upload_copies_only_expected_files(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    staged = tmp_path / "xp-evidence-upload"
    assets.mkdir()
    evidence_output.mkdir()
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=staged,
    )

    assert errors == []
    assert sorted(path.name for path in staged.iterdir()) == sorted(
        {*expected_assets, *expected_evidence}
    )


def test_stage_xp_native_evidence_upload_rejects_extra_source_entries(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )
    (assets / "operator-private").mkdir()
    (evidence_output / "xp-smoke-working-copy.txt").write_text("raw smoke proof\n", encoding="utf-8")

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert (
        "windows-xp-native-x86 XP native asset directory contains files outside staged upload set: "
        "['operator-private']"
    ) in errors
    assert (
        "windows-xp-native-x86 XP evidence output directory contains files outside staged upload set: "
        "['xp-smoke-working-copy.txt']"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_hash_mismatch(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    _write_xp_final_record(
        evidence_output / f"platform-verified-evidence-{target}-final.json",
        target,
        assets,
        evidence_output,
    )
    (assets / expected_assets[0]).write_text("tampered artifact\n", encoding="utf-8")
    (evidence_output / f"xp-native-evidence-bundle-{target}-{tag}.zip").write_text(
        "tampered review bundle\n",
        encoding="utf-8",
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any("staged upload native artifact SHA-256 mismatch" in error for error in errors)
    assert any("staged upload review_bundle archive.sha256 mismatch" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_review_bundle_content_mismatch(
    tmp_path: Path,
) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x86"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        if name == f"platform-verified-evidence-{target}-final.json":
            continue
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    final_record = evidence_output / f"platform-verified-evidence-{target}-final.json"
    _write_xp_final_record(final_record, target, assets, evidence_output)
    record = json.loads(final_record.read_text(encoding="utf-8"))
    archive_name = f"xp-native-evidence-bundle-{target}-{tag}.zip"
    archive_path = evidence_output / archive_name
    archive_path.write_text("not a readable XP review bundle\n", encoding="utf-8")
    record["review_bundle"]["archive"]["sha256"] = _sha256(archive_path)
    record["review_bundle"]["archive"]["size_bytes"] = archive_path.stat().st_size
    final_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any(
        "staged upload review bundle failed re-finalization" in error
        and "review bundle archive is not a readable ZIP" in error
        for error in errors
    )


def test_stage_xp_native_evidence_upload_rejects_release_source_file_set_drift() -> None:
    stager = _load_stager()
    record = {
        "release_asset_source": {
            "contains_files": [
                "expected.zip",
                "platform-verified-evidence-windows-xp-native-x86-final.json",
            ],
        },
    }
    sources = {
        "expected.zip": Path("expected.zip"),
        "unexpected.txt": Path("unexpected.txt"),
    }

    errors = stager.check_release_source_file_set("windows-xp-native-x86", record, sources)

    assert (
        "windows-xp-native-x86 staged upload missing release_asset_source files: "
        "['platform-verified-evidence-windows-xp-native-x86-final.json']"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload has files outside release_asset_source: ['unexpected.txt']"
        in errors
    )


def test_stage_xp_native_evidence_upload_rejects_symlinked_source_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()

    def fake_is_symlink(path: Path) -> bool:
        return path in {assets, evidence_output}

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.stage_xp_native_evidence_upload(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert f"XP native asset directory must not be a symlink: {assets}" in errors
    assert f"XP evidence output directory must not be a symlink: {evidence_output}" in errors


def test_stage_xp_native_evidence_upload_rejects_symlinked_source(monkeypatch) -> None:
    stager = _load_stager()
    sources = {
        "expected.zip": Path("expected.zip"),
        "platform-verified-evidence-windows-xp-native-x86-final.json": Path(
            "platform-verified-evidence-windows-xp-native-x86-final.json"
        ),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path.name == "platform-verified-evidence-windows-xp-native-x86-final.json"

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source must not be a symlink: "
        "platform-verified-evidence-windows-xp-native-x86-final.json"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_symlinked_source_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    source_parent = tmp_path / "linked-source"
    sources = {
        "expected.zip": source_parent / "expected.zip",
        "platform-verified-evidence-windows-xp-native-x86-final.json": (
            source_parent / "platform-verified-evidence-windows-xp-native-x86-final.json"
        ),
    }

    def fake_is_symlink(path: Path) -> bool:
        return path == source_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.check_source_paths("windows-xp-native-x86", sources)

    assert (
        "windows-xp-native-x86 staged upload source expected.zip "
        f"path must not contain symlinked directories: {source_parent}"
    ) in errors
    assert (
        "windows-xp-native-x86 staged upload source "
        "platform-verified-evidence-windows-xp-native-x86-final.json "
        f"path must not contain symlinked directories: {source_parent}"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload"
    out_dir.mkdir()

    def fake_is_symlink(path: Path) -> bool:
        return path == out_dir

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        f"windows-xp-native-x86 staged upload output directory must not be a symlink: {out_dir}"
    ]


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_parent = tmp_path / "linked-upload"
    out_dir = out_parent / "xp-evidence-upload"

    def fake_is_symlink(path: Path) -> bool:
        return path == out_parent

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output directory "
        f"path must not contain symlinked directories: {out_parent}"
    ]


def test_stage_xp_native_evidence_upload_rejects_symlinked_output_child(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    out_dir = tmp_path / "xp-evidence-upload"
    out_dir.mkdir()
    child = out_dir / "old-upload-file.zip"
    child.write_text("old upload\n", encoding="utf-8")

    def fake_is_symlink(path: Path) -> bool:
        return path == child

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    errors = stager.prepare_output_directory(
        "windows-xp-native-x86",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "windows-xp-native-x86 staged upload output must not contain symlinks: old-upload-file.zip"
    ]
    assert child.exists()


def test_stage_xp_native_evidence_upload_rejects_unsafe_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stager = _load_stager()
    symlink_destination = tmp_path / "xp-evidence-upload" / "expected.zip"
    directory_destination = tmp_path / "xp-evidence-upload" / "expected-manifest.json"
    directory_destination.mkdir(parents=True)

    def fake_is_symlink(path: Path) -> bool:
        return path == symlink_destination

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)

    assert stager.check_destination_path(
        "windows-xp-native-x86",
        symlink_destination,
        "expected.zip",
    ) == [
        "windows-xp-native-x86 staged upload destination must not be a symlink: expected.zip"
    ]
    assert stager.check_destination_path(
        "windows-xp-native-x86",
        directory_destination,
        "expected-manifest.json",
    ) == [
        "windows-xp-native-x86 staged upload destination must be a regular file: expected-manifest.json"
    ]


def test_stage_xp_native_evidence_upload_rejects_missing_expected_file(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert errors
    assert any(f"{target} staged upload missing expected files" in error for error in errors)


def test_stage_xp_native_evidence_upload_rejects_invalid_final_record(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "windows-xp-native-x64"
    tag = f"v{checker.read_project_version()}"
    assets = tmp_path / "assets"
    evidence_output = tmp_path / "xp-evidence-output"
    assets.mkdir()
    evidence_output.mkdir()
    expected_assets = _required_artifact_names(checker, target, tag)
    expected_evidence = [
        f"xp-native-evidence-bundle-{target}-{tag}.json",
        f"xp-native-evidence-bundle-{target}-{tag}.zip",
        f"xp-native-evidence-bundle-{target}-{tag}-SHA256SUMS.txt",
        f"platform-verified-evidence-{target}-final.json",
    ]
    for name in expected_assets:
        (assets / name).write_bytes(f"{name}\n".encode())
    for name in expected_evidence:
        (evidence_output / name).write_bytes(f"{name}\n".encode())
    (evidence_output / f"platform-verified-evidence-{target}-final.json").write_text(
        "{}\n",
        encoding="utf-8",
    )

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag=tag,
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=tmp_path / "upload",
    )

    assert any(
        f"{target} finalized accepted record failed strict validation" in error
        for error in errors
    )


def test_stage_xp_native_evidence_upload_rejects_overlapping_staging_output_path(tmp_path: Path) -> None:
    stager = _load_stager()
    target = "windows-xp-native-x86"
    assets = tmp_path / "xp-staged" / "assets"
    evidence_output = tmp_path / "xp-staged" / "evidence-output"
    assets.mkdir(parents=True)
    evidence_output.mkdir()

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=assets / "xp-evidence-upload",
    )

    assert (
        "windows-xp-native-x86 XP native asset directory and staged upload output "
        "directory must be separate roots"
    ) in errors


def test_stage_xp_native_evidence_upload_rejects_asset_evidence_overlap(tmp_path: Path) -> None:
    stager = _load_stager()
    target = "windows-xp-native-x64"
    root = tmp_path / "xp-staged"
    assets = root / "assets"
    evidence_output = assets / "xp-evidence-output"
    evidence_output.mkdir(parents=True)

    errors = stager.stage_xp_native_evidence_upload(
        target=target,
        release_tag="v1.0.2",
        assets_dir=assets,
        evidence_output_dir=evidence_output,
        out_dir=root / "xp-evidence-upload",
    )

    assert (
        "windows-xp-native-x64 XP native asset directory and evidence output directory "
        "must be separate roots"
    ) in errors


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_xp_final_record(path: Path, target: str, assets_dir: Path, evidence_output_dir: Path) -> None:
    assert target == "windows-xp-native-x86"
    review_helpers = _load_platform_review_bundle_helpers()
    bundle_helpers = _load_finalize_helpers()
    record = review_helpers._finalized_xp_record(evidence_output_dir)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            (assets_dir / str(name)).write_bytes(bundle_helpers._artifact_payload(str(name)))
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_stager() -> Any:
    path = Path("scripts/stage_xp_native_evidence_upload.py")
    spec = importlib.util.spec_from_file_location("stage_xp_native_evidence_upload", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_review_bundle_helpers() -> Any:
    path = Path("tests/test_platform_review_bundle_artifacts.py")
    spec = importlib.util.spec_from_file_location("platform_review_bundle_stage_xp_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_helpers() -> Any:
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_evidence_stage_xp_helpers", path)
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
