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
    assert evidence["release_source"] == {
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "TODO-use-github-actions-run-url",
        "head_sha": "TODO-use-github-actions-head-sha",
        "run_attempt": "TODO-use-github-actions-run-attempt",
    }
    assert evidence["artifact_validation"]["passed"] is False
    assert evidence["artifact_validation"]["command"].endswith("--tag v1.0.2 --strict")
    assert evidence["host_identity"]["target"] == "windows-xp-native-x86"
    assert evidence["host_identity"]["operator_private_data_redacted"] is False
    assert "sanitized-lab-label" in evidence["host_identity"]["host_label"]
    assert evidence["security"]["weak_crypto_global_default"] is True
    assert evidence["security"]["patch_evidence"]["cve_patch_reviewed"] is False
    assert evidence["artifacts"] == [
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip",
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native-manifest.json",
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native-SHA256SUMS.txt",
    ]
    smoke_files = sorted((tmp_path / "xp-smoke-evidence").glob("*.txt"))
    assert len(smoke_files) == 6
    assert "xp smoke release: v1.0.2" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "legacy crypto scope: profile-only" in (
        tmp_path / "xp-smoke-evidence" / "legacy_crypto_profile_scoped.txt"
    ).read_text(encoding="utf-8")
    assert "modern TLS preferred: TLS 1.3" in (
        tmp_path / "xp-smoke-evidence" / "modern_defaults_unchanged.txt"
    ).read_text(encoding="utf-8")
    assert all(result["evidence_sha256"] == "<replace-with-real-sha256>" for result in evidence["smoke_results"])
    assert all(result["command"].startswith("scripts/xp_smoke_runner.cmd ") for result in evidence["smoke_results"])
    assert all("--evidence-file xp-smoke-evidence/" in result["command"] for result in evidence["smoke_results"])
    assert all("--proof-file xp-smoke-proof/" in result["command"] for result in evidence["smoke_results"])
    assert all(
        "--observed-at-utc TODO-use-YYYY-MM-DDTHH:MM:SSZ" in result["command"]
        for result in evidence["smoke_results"]
    )
    assert all(
        "--source-workflow-run-url TODO-use-github-actions-run-url" in result["command"]
        for result in evidence["smoke_results"]
    )
    assert all(
        "--source-head-sha TODO-use-github-actions-head-sha" in result["command"]
        for result in evidence["smoke_results"]
    )
    assert all(
        "--source-run-attempt TODO-use-github-actions-run-attempt" in result["command"]
        for result in evidence["smoke_results"]
    )
    assert all('--os-name "Windows XP"' in result["command"] for result in evidence["smoke_results"])
    assert all("--os-architecture x86" in result["command"] for result in evidence["smoke_results"])
    assert all("--os-service-pack SP3" in result["command"] for result in evidence["smoke_results"])
    assert "xp smoke observed at utc: TODO-use-YYYY-MM-DDTHH:MM:SSZ" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke source workflow run: TODO-use-github-actions-run-url" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke source head sha: TODO-use-github-actions-head-sha" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke source run attempt: TODO-use-github-actions-run-attempt" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke os name: Windows XP" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke os architecture: x86" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke os service pack: SP3 TODO replace with real winver evidence" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke host probe command: ver" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke host probe output: Microsoft Windows XP [Version 5.1.2600] TODO replace with real ver output" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke processor architecture env: x86 TODO replace with real %PROCESSOR_ARCHITECTURE% evidence" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke wmic os caption: Microsoft Windows XP Professional TODO replace with real WMIC Caption evidence" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")
    assert "xp smoke wmic os csdversion: Service Pack 3 TODO replace with real WMIC CSDVersion evidence" in (
        tmp_path / "xp-smoke-evidence" / "cli_launch.txt"
    ).read_text(encoding="utf-8")


def test_xp_native_evidence_template_does_not_validate_as_real_evidence(tmp_path: Path) -> None:
    maker = _load_template_maker()
    checker = _load_xp_native_evidence_checker()
    assert maker.make_xp_native_evidence_template(
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    ) == []

    errors = checker.check_xp_native_evidence(tmp_path / "xp-evidence.json")

    assert any("XP native evidence contains forbidden sensitive pattern: TODO" in error for error in errors)
    assert any("XP native evidence contains forbidden sensitive pattern: placeholder" in error for error in errors)
    assert any("XP native evidence contains forbidden sensitive pattern: replace with real" in error for error in errors)
    assert any("XP native evidence contains forbidden sensitive pattern: <artifact-dir>" in error for error in errors)
    assert any(
        "XP native evidence contains forbidden sensitive pattern: <replace-with-real-sha256>" in error
        for error in errors
    )
    assert any("cli_launch evidence_file contains forbidden sensitive pattern: template evidence" in error for error in errors)
    assert any("artifact_validation.passed must be true" in error for error in errors)
    assert any("smoke result cli_launch must have passed=true" in error for error in errors)
    assert any(
        "smoke result cli_launch evidence_sha256 must be a lowercase SHA-256 hex digest" in error
        for error in errors
    )
    assert any("security.weak_crypto_global_default must be False" in error for error in errors)
    assert any("security.patch_evidence.tls_minimum_modern_profiles must be 'TLS 1.2'" in error for error in errors)
    assert any("security.patch_evidence.cve_patch_reviewed must be True" in error for error in errors)


def test_make_xp_native_evidence_template_includes_x64_sp2_edition(tmp_path: Path) -> None:
    maker = _load_template_maker()

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        out_dir=tmp_path,
    )

    assert errors == []
    evidence = json.loads((tmp_path / "xp-evidence.json").read_text(encoding="utf-8"))
    assert evidence["os"]["service_pack"].startswith("SP2")
    assert evidence["os"]["edition"].startswith("Professional x64 Edition")


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


def test_make_xp_native_evidence_template_rejects_symlinked_output_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_template_maker()

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
        force=True,
    )

    assert errors == [f"XP native evidence template output directory must not be a symlink: {tmp_path}"]


def test_make_xp_native_evidence_template_rejects_file_shaped_output_root(
    tmp_path: Path,
) -> None:
    maker = _load_template_maker()
    out_dir = tmp_path / "xp-evidence.json"

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "XP native evidence template output directory "
        f"must be a directory path, got {out_dir.as_posix()!r}"
    ]
    assert not out_dir.exists()


def test_make_xp_native_evidence_template_rejects_reserved_workspace_output_root() -> None:
    maker = _load_template_maker()
    out_dir = Path(".github") / "xp-template"

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        "XP native evidence template output directory must not point inside "
        f"reserved workspace directory '.github': {out_dir}"
    ]
    assert not out_dir.exists()


def test_make_xp_native_evidence_template_rejects_symlinked_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_template_maker()
    out_parent = tmp_path / "linked-output"
    out_dir = out_parent / "xp-template"

    def fake_is_symlink(self: Path) -> bool:
        return self == out_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=out_dir,
        force=True,
    )

    assert errors == [
        f"XP native evidence template output directory path must not contain symlinked directories: {out_parent}"
    ]


def test_make_xp_native_evidence_template_rejects_unsafe_existing_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    maker = _load_template_maker()
    evidence = tmp_path / "xp-evidence.json"
    evidence.write_text("{}\n", encoding="utf-8")
    smoke_dir = tmp_path / "xp-smoke-evidence"
    smoke_dir.mkdir()
    smoke_file = smoke_dir / "cli_launch.txt"
    smoke_file.write_text("old smoke\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self in {evidence, smoke_file}

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
        force=True,
    )

    assert f"XP native evidence template file must not be a symlink: {evidence}" in errors
    assert f"XP native evidence template smoke file must not be a symlink: {smoke_file}" in errors


def test_make_xp_native_evidence_template_rejects_non_directory_smoke_path(tmp_path: Path) -> None:
    maker = _load_template_maker()
    smoke_dir = tmp_path / "xp-smoke-evidence"
    smoke_dir.write_text("not a directory\n", encoding="utf-8")

    errors = maker.make_xp_native_evidence_template(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        out_dir=tmp_path,
        force=True,
    )

    assert errors == [f"XP native evidence template smoke path must be a directory: {smoke_dir}"]


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
