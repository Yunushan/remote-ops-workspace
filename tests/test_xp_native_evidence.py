from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any


def test_xp_native_evidence_contract_passes_current_tree() -> None:
    checker = _load_xp_native_evidence_checker()

    assert checker.main(["--contract"]) == 0


def test_xp_native_evidence_contract_requires_proof_file_binding() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["required_smoke_command_bindings"] = [
        item
        for item in contract["required_smoke_command_bindings"]
        if item != "--proof-file xp-smoke-proof/<smoke_id>.txt"
    ]

    errors = checker.check_contract(contract)

    assert (
        "XP native evidence contract must require tracked runner, target, release-tag, "
        "smoke-id, evidence-file, and proof-file bindings"
    ) in errors


def test_xp_native_evidence_accepts_x86_bundle(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    _write_artifact_set(assets, names)
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, data)
    evidence.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = checker.check_xp_native_evidence(evidence, assets_dir=assets)

    assert errors == []


def test_xp_native_evidence_rejects_current_stack_claim(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["toolchain"]["current_python_pyqt6_stack"] = True
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence toolchain.current_python_pyqt6_stack must be False" in errors


def test_xp_native_evidence_rejects_missing_host_identity(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["host_identity"]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence host_identity must be an object" in errors


def test_xp_native_evidence_rejects_host_identity_target_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["host_identity"]["target"] = "windows-xp-native-x64"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence host_identity.target must be windows-xp-native-x86" in errors


def test_xp_native_evidence_rejects_unsanitized_host_identity_label(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["host_identity"]["host_label"] = "Yunus-PC"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 evidence host_identity.host_label must be a sanitized lab label, got 'Yunus-PC'"
        in errors
    )


def test_xp_native_evidence_rejects_missing_smoke(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"] = evidence["smoke_results"][:1]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("windows-xp-native-x86 evidence missing smoke results" in error for error in errors)


def test_xp_native_evidence_rejects_duplicate_smoke_result(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["smoke_results"].append(dict(evidence["smoke_results"][0]))
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence contains duplicate smoke results: ['cli_launch']" in errors


def test_xp_native_evidence_rejects_unexpected_smoke_result(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    evidence["smoke_results"].append(
        {
            "id": "unsupported_extra_probe",
            "passed": True,
            "command": (
                "scripts/xp_smoke_runner.cmd --target windows-xp-native-x64 "
                "--smoke-id unsupported_extra_probe"
            ),
            "evidence_file": "xp-smoke-evidence/unsupported_extra_probe.txt",
            "evidence_sha256": "",
        }
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence contains unexpected smoke results: ['unsupported_extra_probe']" in errors


def test_xp_native_evidence_rejects_sensitive_pattern(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["notes"] = "operator used token=example"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "XP native evidence contains forbidden sensitive pattern: token=" in errors


def test_xp_native_evidence_rejects_template_marker_in_json(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["notes"] = "TODO replace with real XP host output"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "XP native evidence contains forbidden sensitive pattern: TODO" in errors
    assert "XP native evidence contains forbidden sensitive pattern: replace with real" in errors


def test_xp_native_evidence_rejects_template_marker_in_smoke_file(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x64", tag)
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text("Template evidence: replace with real XP host output\n", encoding="utf-8")
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("cli_launch evidence_file contains forbidden sensitive pattern: replace with real" in error for error in errors)
    assert any("cli_launch evidence_file contains forbidden sensitive pattern: template evidence" in error for error in errors)


def test_xp_native_evidence_rejects_missing_smoke_evidence_file(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    (tmp_path / evidence["smoke_results"][0]["evidence_file"]).unlink()
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("smoke result cli_launch evidence_file missing" in error for error in errors)


def test_xp_native_evidence_rejects_unscoped_smoke_evidence_file(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke = evidence["smoke_results"][0]
    smoke["evidence_file"] = "cli_launch.txt"
    smoke["command"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file cli_launch.txt"
    )
    smoke_path = tmp_path / smoke["evidence_file"]
    smoke_path.write_text(
        "xp smoke target: windows-xp-native-x86\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: cli_launch\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    smoke["evidence_sha256"] = _sha256(smoke_path)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 smoke result cli_launch evidence_file must be xp-smoke-evidence/cli_launch.txt" in errors


def test_xp_native_evidence_rejects_smoke_evidence_missing_target_binding(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        "xp smoke release: v1.0.2\n"
        "xp smoke id: cli_launch\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file target binding must be "
        "['windows-xp-native-x86'], got []"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_wrong_smoke_id_binding(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        "xp smoke target: windows-xp-native-x64\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: loopback_profile_dry_run\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file smoke-id binding must be "
        "['cli_launch'], got ['loopback_profile_dry_run']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_wrong_release_binding(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        "xp smoke target: windows-xp-native-x86\n"
        "xp smoke release: v9.9.9\n"
        "xp smoke id: cli_launch\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file release binding must be "
        "['v1.0.2'], got ['v9.9.9']"
    ) in errors


def test_xp_native_evidence_rejects_missing_legacy_crypto_security_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "legacy_crypto_profile_scoped")
    smoke_file = tmp_path / result["evidence_file"]
    smoke_file.write_text(
        f"xp smoke target: {evidence['target']}\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: legacy_crypto_profile_scoped\n"
        "legacy compatibility profile: isolated-opt-in\n"
        "weak crypto global default: false\n",
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result legacy_crypto_profile_scoped evidence_file "
        "missing security proof line: legacy crypto scope: profile-only"
    ) in errors


def test_xp_native_evidence_rejects_missing_modern_defaults_security_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "modern_defaults_unchanged")
    smoke_file = tmp_path / result["evidence_file"]
    smoke_file.write_text(
        f"xp smoke target: {evidence['target']}\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: modern_defaults_unchanged\n"
        "modern TLS minimum: TLS 1.2\n"
        "modern defaults unchanged: true\n"
        "weak crypto global default: false\n",
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result modern_defaults_unchanged evidence_file "
        "missing security proof line: modern TLS preferred: TLS 1.3"
    ) in errors


def test_xp_native_evidence_rejects_missing_smoke_command(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["smoke_results"][0]["command"]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 smoke result cli_launch missing command provenance" in errors


def test_xp_native_evidence_rejects_placeholder_smoke_command(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["command"] = "<command>"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 smoke result cli_launch command must be concrete, got '<command>'" in errors


def test_xp_native_evidence_rejects_smoke_command_target_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["command"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x64 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt"
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--target windows-xp-native-x86, got ['windows-xp-native-x64']"
    ) in errors


def test_xp_native_evidence_rejects_untracked_smoke_runner_command(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["command"] = (
        "xp-smoke-runner --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt"
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("command must start with 'scripts/xp_smoke_runner.cmd'" in error for error in errors)


def test_xp_native_evidence_rejects_smoke_command_proof_file_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["command"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt "
        "--proof-file xp-smoke-proof/other.txt"
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--proof-file xp-smoke-proof/cli_launch.txt, got ['xp-smoke-proof/other.txt']"
    ) in errors


def test_xp_native_evidence_rejects_missing_security_patch_evidence(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["security"]["patch_evidence"]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence security.patch_evidence must be an object" in errors


def test_xp_native_evidence_rejects_smoke_evidence_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["evidence_sha256"] = "0" * 64
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("smoke result cli_launch evidence_file SHA-256 mismatch" in error for error in errors)


def test_xp_native_evidence_rejects_artifact_validation_tag_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x64", tag)
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        f"--tag {tag}",
        "--tag v9.9.9",
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"windows-xp-native-x64 evidence artifact_validation.command must include exactly one --tag {tag}, "
        "got ['v9.9.9']"
    ) in errors


def test_xp_native_evidence_rejects_x64_without_sp2_and_edition(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "x64", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["os"]["edition"]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence os.service_pack must include 'SP2', got 'x64'" in errors
    assert (
        "windows-xp-native-x64 evidence os.edition must be "
        "'Professional x64 Edition', got None"
    ) in errors


def test_xp_native_evidence_rejects_duplicate_artifact_validation_tag(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = (
        f"{evidence['artifact_validation']['command']} --tag v9.9.9"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"windows-xp-native-x86 evidence artifact_validation.command must include exactly one --tag {tag}, "
        f"got ['{tag}', 'v9.9.9']"
    ) in errors


def test_xp_native_evidence_rejects_missing_artifact_validation_assets_dir(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --tag v1.0.2"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact_validation.command must include exactly one --assets-dir, got []"
        in errors
    )


def test_xp_native_evidence_rejects_placeholder_artifact_validation_assets_dir(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir <artifact-dir> --tag v1.0.2"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "XP native evidence contains forbidden sensitive pattern: <artifact-dir>" in errors
    assert (
        "windows-xp-native-x86 evidence artifact_validation.command --assets-dir must be concrete, "
        "got '<artifact-dir>'"
    ) in errors


def test_xp_native_evidence_rejects_unscoped_artifact_validation_assets_dir(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir native-dist/windows-xp --tag v1.0.2"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact_validation.command --assets-dir "
        "must include target path segment 'windows-xp-native-x86', got 'native-dist/windows-xp'"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence artifact_validation.command --assets-dir "
        "must include release_tag path segment 'v1.0.2', got 'native-dist/windows-xp'"
    ) in errors


def test_xp_native_evidence_rejects_inexact_artifact_list(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, [*names[:-1], names[0]])
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("windows-xp-native-x86 evidence artifacts contain duplicate names" in error for error in errors)
    assert any("windows-xp-native-x86 evidence artifacts missing expected names" in error for error in errors)


def _valid_evidence(
    target: str,
    arch: str,
    service_pack: str,
    release_tag: str,
    artifacts: list[str],
) -> dict[str, Any]:
    smoke_ids = [
        "cli_launch",
        "gui_or_legacy_host_ui_launch",
        "loopback_profile_dry_run",
        "artifact_manifest_validation",
        "legacy_crypto_profile_scoped",
        "modern_defaults_unchanged",
    ]
    os_record = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": service_pack,
    }
    if arch == "x64":
        os_record["edition"] = "Professional x64 Edition"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "os": os_record,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "host_identity": {
            "schema_version": 1,
            "target": target,
            "release_tag": release_tag,
            "host_label": f"xp-{arch}-lab-01",
            "evidence_run_id": f"xp-{arch}-{release_tag.removeprefix('v').replace('.', '-')}-20260620t120000z",
            "observed_at_utc": "2026-06-20T12:00:00Z",
            "operator_private_data_redacted": True,
            "os": dict(os_record),
            "toolchain": {
                "separate_legacy_toolchain": True,
                "current_python_pyqt6_stack": False,
                "description": "Separate legacy XP-capable native host toolchain",
            },
        },
        "artifact_validation": {
            "passed": True,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir native-dist/windows-xp/{target}/{release_tag} --tag {release_tag}"
            ),
        },
        "artifacts": artifacts or [f"remote-ops-workspace-{target}-placeholder"],
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": True,
                "command": (
                    f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
                    f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt"
                ),
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": hashlib.sha256(smoke_id.encode()).hexdigest(),
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": {
                "tls_minimum_modern_profiles": "TLS 1.2",
                "tls_preferred_modern_profiles": "TLS 1.3",
                "legacy_compatibility_profile": "isolated-opt-in",
                "cve_patch_reviewed": True,
            },
        },
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        security_lines = _security_smoke_lines(str(result["id"]))
        path.write_text(
            f"xp smoke target: {evidence['target']}\n"
            f"xp smoke release: {evidence['release_tag']}\n"
            f"xp smoke id: {result['id']}\n"
            f"{security_lines}"
            f"{result['id']} passed on Windows XP evidence host\n",
            encoding="utf-8",
        )
        result["evidence_sha256"] = _sha256(path)


def _security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
        )
    return ""


def _required_artifact_names(checker: Any, target: str, tag: str) -> list[str]:
    promotion = checker.read_json(Path("configs/platform_parity_promotion.json"))
    entries = checker.promotion_entries(promotion, [])
    version = checker.version_from_tag(tag, [])
    return [checker.expand_version(name, version) for name in checker.required_artifacts(entries[target])]


def _write_artifact_set(root: Path, names: list[str]) -> None:
    payload_names = [
        name
        for name in names
        if not name.endswith("SHA256SUMS.txt") and not name.endswith("manifest.json")
    ]
    manifest_name = next(name for name in names if name.endswith("manifest.json"))
    sidecar_name = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    for name in payload_names:
        (root / name).write_bytes(_payload_bytes(name))
    records = [
        {
            "file": name,
            "size_bytes": (root / name).stat().st_size,
            "sha256": _sha256(root / name),
        }
        for name in payload_names
    ]
    (root / manifest_name).write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    sidecar_names = [*payload_names, manifest_name]
    (root / sidecar_name).write_text(
        "".join(f"{_sha256(root / name)}  {name}\n" for name in sidecar_names),
        encoding="utf-8",
    )


def _payload_bytes(name: str) -> bytes:
    payload = f"{name}\n".encode()
    if name.endswith(".zip"):
        return _zip_bytes(name, payload)
    return payload


def _zip_bytes(name: str, payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{name}.txt", payload)
    return buffer.getvalue()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_xp_native_evidence_checker():
    path = Path("scripts/check_xp_native_evidence.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_promotion_artifacts_checker():
    path = Path("scripts/check_platform_promotion_artifacts.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_artifacts_for_xp", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
