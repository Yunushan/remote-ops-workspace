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
    source = tmp_path / "native-dist" / "linux"
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
    scratch = source / "builder-scratch"
    scratch.mkdir()
    (scratch / "package-cache.txt").write_text("must not be uploaded\n", encoding="utf-8")
    (source / "native-smoke-linux-i386.log").write_text("raw smoke log stays bundled only\n", encoding="utf-8")

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
    assert not (staged / "builder-scratch").exists()
    assert not (staged / "native-smoke-linux-i386.log").exists()


def test_stage_extended_linux_evidence_upload_rejects_hash_mismatch(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-i386"
    tag = f"v{checker.read_project_version()}"
    source = tmp_path / "native-dist" / "linux"
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


def test_stage_extended_linux_evidence_upload_rejects_missing_expected_file(tmp_path: Path) -> None:
    stager = _load_stager()
    checker = _load_platform_promotion_artifacts_checker()
    target = "linux-armhf"
    tag = f"v{checker.read_project_version()}"
    source = tmp_path / "native-dist" / "linux"
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
    source = tmp_path / "native-dist" / "linux"
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


def _write_linux_final_record(path: Path, target: str, source_dir: Path) -> None:
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record(target)
    artifact_hashes = record.get("artifact_sha256")
    if isinstance(artifact_hashes, dict):
        for name in artifact_hashes:
            artifact_hashes[name] = _sha256(source_dir / str(name))
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        for key in ("manifest", "archive", "sha256s"):
            item = review_bundle.get(key)
            if isinstance(item, dict):
                item_path = source_dir / str(item["file"])
                item["sha256"] = _sha256(item_path)
                item["size_bytes"] = item_path.stat().st_size
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


def _load_platform_verified_evidence_helpers() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_evidence_stage_linux_helpers", path)
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
