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
    private_dir = assets / "operator-private"
    private_dir.mkdir()
    (private_dir / "local-admin-notes.txt").write_text("must not be uploaded\n", encoding="utf-8")

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
    assert not (staged / "operator-private").exists()
    assert not (staged / "local-admin-notes.txt").exists()


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
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._xp_record(target)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            artifact_hashes[name] = _sha256(assets_dir / str(name))
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            item = review_bundle.get(key)
            if isinstance(item, dict):
                item_path = evidence_output_dir / str(item["file"])
                item["sha256"] = _sha256(item_path)
                item["size_bytes"] = item_path.stat().st_size
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


def _load_platform_verified_evidence_helpers() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_stage_xp_helpers", path)
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
