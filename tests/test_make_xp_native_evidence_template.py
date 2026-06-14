from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_make_xp_native_evidence_template_writes_incomplete_bundle(tmp_path: Path) -> None:
    maker = _load_template_maker()

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    )

    assert errors == []
    evidence = json.loads((tmp_path / "xp-evidence.json").read_text(encoding="utf-8"))
    assert evidence["target"] == "windows-xp-native-x86"
    assert evidence["release_tag"] == "v1.0.2"
    assert evidence["artifact_validation"]["passed"] is False
    assert evidence["security"]["weak_crypto_global_default"] is True
    assert evidence["artifacts"] == [
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip",
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native-manifest.json",
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native-SHA256SUMS.txt",
    ]
    smoke_files = sorted((tmp_path / "xp-smoke-evidence").glob("*.txt"))
    assert len(smoke_files) == 6
    assert all(result["evidence_sha256"] == "<replace-with-real-sha256>" for result in evidence["smoke_results"])


def test_xp_native_evidence_template_does_not_validate_as_real_evidence(tmp_path: Path) -> None:
    maker = _load_template_maker()
    checker = _load_xp_native_evidence_checker()
    assert maker.make_xp_native_evidence_template(
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    ) == []

    errors = checker.check_xp_native_evidence(tmp_path / "xp-evidence.json")

    assert any("artifact_validation.passed must be true" in error for error in errors)
    assert any("smoke result cli_launch must have passed=true" in error for error in errors)
    assert any("smoke result cli_launch missing evidence_sha256" in error for error in errors)
    assert any("security.weak_crypto_global_default must be False" in error for error in errors)


def test_make_xp_native_evidence_template_rejects_overwrite_without_force(tmp_path: Path) -> None:
    maker = _load_template_maker()
    assert maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    ) == []

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    )

    assert any("refusing to overwrite existing evidence template" in error for error in errors)


def _load_template_maker():
    path = Path("scripts/make_xp_native_evidence_template.py")
    spec = importlib.util.spec_from_file_location("make_xp_native_evidence_template", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_xp_native_evidence_checker():
    path = Path("scripts/check_xp_native_evidence.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence_for_template", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
