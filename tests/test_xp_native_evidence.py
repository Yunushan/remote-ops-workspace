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


def test_xp_native_evidence_contract_rejects_boolean_schema_version() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["schema_version"] = True

    errors = checker.check_contract(contract)

    assert "configs/xp_native_evidence_contract.json schema_version must be 1" in errors


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


def test_xp_native_evidence_contract_requires_release_source_fields() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["required_release_source_fields"] = ["workflow", "workflow_run_url", "head_sha"]

    errors = checker.check_contract(contract)

    assert "XP native evidence contract must require release_source workflow, URL, head SHA and run attempt" in errors


def test_xp_native_evidence_contract_requires_security_smoke_provenance_fields() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["required_security_smoke_provenance_fields"] = ["security_update_channel"]

    errors = checker.check_contract(contract)

    assert "XP native evidence contract must require security smoke provenance fields" in errors


def test_xp_native_evidence_contract_requires_security_provenance_namespaces() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    del contract["required_security_patch_provenance_namespaces"]

    errors = checker.check_contract(contract)

    assert "XP native evidence contract must require concrete security provenance namespaces" in errors


def test_xp_native_evidence_contract_rejects_weakened_security_provenance_namespaces() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["required_security_patch_provenance_namespaces"]["cve_review_reference"] = [
        marker
        for marker in contract["required_security_patch_provenance_namespaces"]["cve_review_reference"]
        if marker != "cve-"
    ]

    errors = checker.check_contract(contract)

    assert "XP native evidence contract concrete cve_review_reference provenance namespaces missing ['cve-']" in errors


def test_xp_native_evidence_contract_requires_artifact_manifest_smoke_lines() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    contract["required_artifact_manifest_smoke_evidence_lines"] = [
        "xp smoke artifact manifest validated: true"
    ]

    errors = checker.check_contract(contract)

    assert (
        "XP native evidence contract must require artifact_manifest_validation "
        "smoke proof lines for every release artifact, manifest, and SHA256SUMS sidecar"
    ) in errors


def test_xp_native_evidence_contract_requires_exact_smoke_proof_line_occurrences() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    del contract["exact_smoke_proof_line_occurrences_required"]

    errors = checker.check_contract(contract)

    assert "XP native evidence contract must require exact single-occurrence smoke proof lines" in errors


def test_xp_native_evidence_contract_requires_case_insensitive_forbidden_security_lines() -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    del contract["forbidden_security_smoke_lines_case_insensitive"]

    errors = checker.check_contract(contract)

    assert (
        "XP native evidence contract must require "
        "case-insensitive forbidden security proof-line rejection"
    ) in errors


def test_xp_native_evidence_contract_requires_runner_source_env_binding(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    contract = checker.read_json(Path("configs/xp_native_evidence_contract.json"))
    runner = tmp_path / "scripts" / "xp_smoke_runner.cmd"
    runner.parent.mkdir()
    runner.write_text(
        "scripts/xp_smoke_runner.cmd --target --release-tag --smoke-id "
        "--evidence-file --proof-file --host-label --evidence-run-id "
        "--observed-at-utc --source-workflow-run-url --source-head-sha "
        "--source-run-attempt --os-name --os-architecture --os-service-pack "
        "--os-edition ver PROCESSOR_ARCHITECTURE wmic os get Caption\n",
        encoding="utf-8",
    )
    checker.ROOT = tmp_path

    errors = checker.check_contract(contract)

    assert any(
        "XP native smoke runner script must handle --source-workflow-run-url must be a GitHub Actions run URL"
        in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --source-workflow-run-url must end with a numeric GitHub Actions run id"
        in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --host-label must use target-scoped prefix" in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --evidence-run-id must use target-scoped prefix" in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --observed-at-utc must use YYYY-MM-DDTHH:MM:SSZ" in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --source-head-sha must be a lowercase 40-character Git commit SHA"
        in error
        for error in errors
    )
    assert any(
        "XP native smoke runner script must handle --source-run-attempt must be a positive integer" in error
        for error in errors
    )
    assert any("XP native smoke runner script must handle GITHUB_SHA" in error for error in errors)
    assert any("XP native smoke runner script must handle GITHUB_RUN_ID" in error for error in errors)
    assert any("XP native smoke runner script must handle GITHUB_RUN_ATTEMPT" in error for error in errors)
    assert any("XP native smoke runner script must handle GITHUB_REPOSITORY" in error for error in errors)


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


def test_xp_native_evidence_uses_explicit_empty_contract(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_xp_native_evidence(path, contract={})

    assert "XP native evidence contract targets must be an object" in errors


def test_xp_native_evidence_rejects_unreadable_json(tmp_path: Path, monkeypatch) -> None:
    checker = _load_xp_native_evidence_checker()
    path = tmp_path / "xp-evidence.json"
    path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self == path:
            raise OSError("locked evidence file")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    errors = checker.check_xp_native_evidence(path)

    assert any(
        f"evidence file is not readable JSON: {path}: locked evidence file" in error
        for error in errors
    )


def test_xp_native_evidence_rejects_boolean_schema_versions(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["schema_version"] = True
    evidence["host_identity"]["schema_version"] = True
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "XP native evidence schema_version must be 1" in errors
    assert "windows-xp-native-x86 evidence host_identity.schema_version must be 1" in errors


def test_xp_native_evidence_rejects_extra_asset_file(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    assets = tmp_path / "assets"
    assets.mkdir()
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    _write_artifact_set(assets, names)
    (assets / "unexpected.txt").write_text("extra\n", encoding="utf-8")
    evidence = tmp_path / "xp-evidence.json"
    data = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, data)
    evidence.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_xp_native_evidence(evidence, assets_dir=assets)

    assert "windows-xp-native-x86 artifacts include unexpected files: ['unexpected.txt']" in errors


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


def test_xp_native_evidence_rejects_missing_release_source(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["release_source"]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence release_source must be an object" in errors


def test_xp_native_evidence_rejects_malformed_release_source(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["release_source"]["workflow_run_url"] = (
        "https://github.com/example/remote-ops-workspace/actions/workflows/xp-native-evidence.yml"
    )
    evidence["release_source"]["head_sha"] = "A" * 40
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence release_source.workflow_run_url must be a GitHub Actions run URL" in errors
    assert "windows-xp-native-x64 evidence release_source.head_sha must be a 40-character lowercase Git SHA" in errors


def test_xp_native_evidence_rejects_noncanonical_release_source(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["release_source"]["workflow"] = " .github/workflows/xp-native-evidence.yml "
    evidence["release_source"]["workflow_run_url"] = (
        "https://github.com/example/remote-ops-workspace/actions/runs/12345/"
    )
    evidence["release_source"]["head_sha"] = f" {'a' * 40} "
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence release_source.workflow must not include surrounding whitespace" in errors
    assert (
        "windows-xp-native-x86 evidence release_source.workflow_run_url must be canonical without "
        "surrounding whitespace or trailing slash"
    ) in errors
    assert "windows-xp-native-x86 evidence release_source.head_sha must not include surrounding whitespace" in errors


def test_xp_native_evidence_rejects_non_string_release_source_fields(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["release_source"]["workflow"] = True
    evidence["release_source"]["workflow_run_url"] = 12345
    evidence["release_source"]["head_sha"] = False
    evidence["release_source"]["run_attempt"] = "1"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence release_source.workflow must be a string" in errors
    assert "windows-xp-native-x86 evidence release_source.workflow_run_url must be a string" in errors
    assert "windows-xp-native-x86 evidence release_source.head_sha must be a string" in errors
    assert "windows-xp-native-x86 evidence release_source.run_attempt must be a positive integer" in errors


def test_xp_native_evidence_rejects_non_string_os_and_toolchain_identity_fields(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["os"]["name"] = True
    evidence["os"]["architecture"] = ["x64"]
    evidence["os"]["service_pack"] = ["SP2"]
    evidence["os"]["edition"] = False
    evidence["toolchain"]["description"] = True
    evidence["host_identity"]["os"]["name"] = True
    evidence["host_identity"]["os"]["architecture"] = ["x64"]
    evidence["host_identity"]["os"]["service_pack"] = ["SP2"]
    evidence["host_identity"]["os"]["edition"] = False
    evidence["host_identity"]["toolchain"]["description"] = False
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x64 evidence os.name must be a string" in errors
    assert "windows-xp-native-x64 evidence os.architecture must be a string" in errors
    assert "windows-xp-native-x64 evidence os.service_pack must be a string" in errors
    assert "windows-xp-native-x64 evidence os.edition must be a string" in errors
    assert "windows-xp-native-x64 evidence toolchain.description must be a string" in errors
    assert "windows-xp-native-x64 evidence host_identity.os.name must be a string" in errors
    assert "windows-xp-native-x64 evidence host_identity.os.architecture must be a string" in errors
    assert "windows-xp-native-x64 evidence host_identity.os.service_pack must be a string" in errors
    assert "windows-xp-native-x64 evidence host_identity.os.edition must be a string" in errors
    assert "windows-xp-native-x64 evidence host_identity.toolchain.description must be a string" in errors


def test_xp_native_evidence_rejects_non_string_host_identity_run_fields(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["host_identity"]["host_label"] = True
    evidence["host_identity"]["evidence_run_id"] = ["xp-x86-1-0-2-20260620t120000z"]
    evidence["host_identity"]["observed_at_utc"] = 123
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence host_identity.host_label must be a string" in errors
    assert "windows-xp-native-x86 evidence host_identity.evidence_run_id must be a string" in errors
    assert "windows-xp-native-x86 evidence host_identity.observed_at_utc must be a string" in errors
    assert all("got 'True'" not in error for error in errors)


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
        "windows-xp-native-x64 evidence host_identity.host_label must be a sanitized target-scoped lab label, "
        "got 'Yunus-PC'"
        in errors
    )


def test_xp_native_evidence_rejects_private_host_identity_fields(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["host_identity"]["host_label"] = "yunus-pc"
    evidence["host_identity"]["evidence_run_id"] = "manual-run-20260620t120000z"
    evidence["host_identity"]["hostname"] = "yunus-pc"
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence host_identity.host_label must be a sanitized target-scoped lab label, "
        "got 'yunus-pc'"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence host_identity.evidence_run_id must be a sanitized target-scoped run id, "
        "got 'manual-run-20260620t120000z'"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence host_identity contains forbidden private fields: ['hostname']"
    ) in errors


def test_xp_native_evidence_rejects_unexpected_evidence_fields(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["operator_note"] = "manual review"
    evidence["release_source"]["scratch"] = "manual"
    evidence["os"]["computer_name"] = "private-xp-host"
    evidence["toolchain"]["tool_path"] = "C:\\private\\toolchain"
    evidence["host_identity"]["runner_name"] = "private-runner"
    evidence["host_identity"]["os"]["hostname"] = "private-xp-host"
    evidence["host_identity"]["toolchain"]["builder_user"] = "private-user"
    evidence["artifact_validation"]["operator_note"] = "manual review"
    evidence["smoke_results"][0]["operator_note"] = "manual review"
    evidence["security"]["operator_note"] = "manual review"
    evidence["security"]["patch_evidence"]["operator_note"] = "manual review"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence unexpected fields: ['operator_note']" in errors
    assert "windows-xp-native-x86 evidence release_source has unexpected fields: ['scratch']" in errors
    assert "windows-xp-native-x86 evidence os unexpected fields: ['computer_name']" in errors
    assert "windows-xp-native-x86 evidence toolchain unexpected fields: ['tool_path']" in errors
    assert "windows-xp-native-x86 evidence host_identity unexpected fields: ['runner_name']" in errors
    assert (
        "windows-xp-native-x86 evidence host_identity contains forbidden private fields: ['runner_name']"
    ) in errors
    assert "windows-xp-native-x86 evidence host_identity.os unexpected fields: ['hostname']" in errors
    assert (
        "windows-xp-native-x86 evidence host_identity.toolchain unexpected fields: ['builder_user']"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence artifact_validation unexpected fields: ['operator_note']"
    ) in errors
    assert "windows-xp-native-x86 smoke result cli_launch unexpected fields: ['operator_note']" in errors
    assert "windows-xp-native-x86 evidence security unexpected fields: ['operator_note']" in errors
    assert (
        "windows-xp-native-x86 evidence security.patch_evidence unexpected fields: ['operator_note']"
    ) in errors


def test_xp_native_evidence_rejects_run_id_not_bound_to_observed_at(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["host_identity"]["evidence_run_id"] = "xp-x86-1-0-2-20260620t123000z"
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence host_identity.evidence_run_id must include "
        "release/observed-at marker '1-0-2-20260620t120000z', got 'xp-x86-1-0-2-20260620t123000z'"
    ) in errors


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


def test_xp_native_evidence_rejects_symlinked_evidence_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_xp_native_evidence(path)

    assert f"evidence file must not be a symlink: {path}" in errors


def test_xp_native_evidence_rejects_symlinked_evidence_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_xp_native_evidence(path, evidence_dir=tmp_path)

    assert f"evidence directory must not be a symlink: {tmp_path}" in errors


def test_xp_native_evidence_rejects_symlinked_evidence_directory_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    linked_parent = tmp_path / "linked-evidence"
    evidence_root = linked_parent / "xp-evidence-root"
    path = evidence_root / "xp-evidence.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == linked_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_xp_native_evidence(path, evidence_dir=evidence_root)

    assert errors == [
        f"evidence directory path must not contain symlinked directories: {linked_parent}"
    ]


def test_xp_native_evidence_rejects_reserved_workspace_evidence_file() -> None:
    checker = _load_xp_native_evidence_checker()
    path = Path(".github") / "xp-evidence.json"

    errors = checker.check_xp_native_evidence(path, evidence_dir=Path("xp-evidence"))

    assert (
        "evidence file must not point inside reserved workspace directory "
        f"'.github': {path}"
    ) in errors
    assert not path.exists()


def test_xp_native_evidence_rejects_reserved_workspace_evidence_directory() -> None:
    checker = _load_xp_native_evidence_checker()
    evidence_dir = Path(".git") / "xp-evidence"
    path = evidence_dir / "xp-evidence.json"

    errors = checker.check_xp_native_evidence(path, evidence_dir=evidence_dir)

    assert (
        "evidence file must not point inside reserved workspace directory "
        f"'.git': {path}"
    ) in errors
    assert (
        "evidence directory must not point inside reserved workspace directory "
        f"'.git': {evidence_dir}"
    ) in errors


def test_xp_native_evidence_path_helpers_reject_non_path_args() -> None:
    checker = _load_xp_native_evidence_checker()

    assert checker.check_xp_native_evidence(
        "xp-evidence.json",
        evidence_dir=["xp-evidence"],
        assets_dir=True,
        contract={},
    ) == [
        "evidence file path must be a pathlib.Path, got 'xp-evidence.json'",
        "evidence directory path must be a pathlib.Path, got ['xp-evidence']",
        "XP native artifact directory path must be a pathlib.Path, got True",
    ]
    assert checker.check_evidence_file_location(
        "xp-evidence.json",
        ["xp-evidence"],
    ) == [
        "evidence file path must be a pathlib.Path, got 'xp-evidence.json'",
        "evidence directory path must be a pathlib.Path, got ['xp-evidence']",
    ]
    assert checker.check_smoke_evidence_file(
        "windows-xp-native-x86",
        "v1.0.2",
        "cli_launch",
        {"evidence_file": "xp-smoke-evidence/cli_launch.txt"},
        "xp-evidence",
        {"required_smoke_evidence_file": True},
        host_identity={},
        os_identity={},
        release_source={},
        security={},
    ) == [
        "windows-xp-native-x86 smoke evidence directory path must be a pathlib.Path, "
        "got 'xp-evidence'"
    ]
    assert checker.check_path_parent_symlinks("xp-evidence", "evidence directory") == [
        "evidence directory path must be a pathlib.Path, got 'xp-evidence'"
    ]
    assert checker.check_path_not_reserved_workspace_root("xp-evidence", "evidence directory") == [
        "evidence directory path must be a pathlib.Path, got 'xp-evidence'"
    ]


def test_xp_native_evidence_rejects_evidence_file_outside_evidence_directory(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence_root = tmp_path / "evidence-root"
    evidence_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(evidence_root, evidence)
    path = outside / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path, evidence_dir=evidence_root)

    assert f"evidence file must stay inside evidence directory: {path}" in errors


def test_xp_native_evidence_rejects_symlinked_evidence_file_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence_root = tmp_path / "evidence-root"
    evidence_parent = evidence_root / "linked-parent"
    evidence_parent.mkdir(parents=True)
    path = evidence_parent / "xp-evidence.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == evidence_parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_xp_native_evidence(path, evidence_dir=evidence_root)

    assert "evidence file path must not contain symlinks: linked-parent" in errors


def test_xp_native_evidence_rejects_symlinked_smoke_evidence_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    symlink_name = "cli_launch.txt"

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file path must not contain symlinks: "
        "xp-smoke-evidence/cli_launch.txt"
    ) in errors


def test_xp_native_evidence_rejects_symlinked_smoke_evidence_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    symlink_name = "xp-smoke-evidence"

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file path must not contain symlinks: "
        "xp-smoke-evidence"
    ) in errors


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


def test_xp_native_evidence_rejects_smoke_evidence_host_identity_binding_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        "xp smoke target: windows-xp-native-x86\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: cli_launch\n"
        "xp smoke host label: xp-x86-lab-02\n"
        "xp smoke evidence run id: xp-x86-1-0-2-other\n"
        "xp smoke observed at utc: 2026-06-20T12:30:00Z\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file host-label binding must be "
        "['xp-x86-lab-01'], got ['xp-x86-lab-02']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file evidence-run-id binding must be "
        "['xp-x86-1-0-2-20260620t120000z'], got ['xp-x86-1-0-2-other']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file observed-at-utc binding must be "
        "['2026-06-20T12:00:00Z'], got ['2026-06-20T12:30:00Z']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_release_source_binding_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8").replace(
            "xp smoke source head sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "xp smoke source head sha: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file source head SHA binding "
        "must be ['aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'], got "
        "['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_command_source_workflow_run_trailing_slash(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    expected = evidence["release_source"]["workflow_run_url"]
    evidence["smoke_results"][0]["command"] = evidence["smoke_results"][0]["command"].replace(
        f"--source-workflow-run-url {expected}",
        f"--source-workflow-run-url {expected}/",
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        f"--source-workflow-run-url {expected}, got ['{expected}/']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_source_workflow_run_trailing_slash(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    expected = evidence["release_source"]["workflow_run_url"]
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8").replace(
            f"xp smoke source workflow run: {expected}",
            f"xp smoke source workflow run: {expected}/",
        ),
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file source workflow run binding "
        f"must be ['{expected}'], got ['{expected}/']"
    ) in errors


def test_xp_native_evidence_rejects_duplicate_smoke_source_binding_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    duplicate_line = f"xp smoke source head sha: {evidence['release_source']['head_sha']}\n"
    smoke_file.write_text(smoke_file.read_text(encoding="utf-8") + duplicate_line, encoding="utf-8")
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    expected = evidence["release_source"]["head_sha"]
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file source head SHA binding "
        f"must be ['{expected}'], got ['{expected}', '{expected}']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_os_identity_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    host_identity = evidence["host_identity"]
    smoke_file.write_text(
        "xp smoke target: windows-xp-native-x64\n"
        "xp smoke release: v1.0.2\n"
        "xp smoke id: cli_launch\n"
        "xp smoke os name: Windows 7\n"
        "xp smoke os architecture: x86\n"
        "xp smoke os service pack: SP1\n"
        "xp smoke os edition: Ultimate\n"
        f"xp smoke host label: {host_identity['host_label']}\n"
        f"xp smoke evidence run id: {host_identity['evidence_run_id']}\n"
        f"xp smoke observed at utc: {host_identity['observed_at_utc']}\n"
        "cli_launch passed on Windows XP evidence host\n",
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file OS name binding "
        "must be ['Windows XP'], got ['Windows 7']"
    ) in errors
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file OS architecture binding "
        "must be ['x64'], got ['x86']"
    ) in errors
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file OS service-pack binding "
        "must be ['SP2'], got ['SP1']"
    ) in errors
    assert (
        "windows-xp-native-x64 smoke result cli_launch evidence_file OS edition binding "
        "must be ['Professional x64 Edition'], got ['Ultimate']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_host_probe_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_file = tmp_path / evidence["smoke_results"][0]["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8")
        .replace("Microsoft Windows XP [Version 5.1.2600]", "Microsoft Windows [Version 6.1.7601]")
        .replace("xp smoke processor architecture env: x86", "xp smoke processor architecture env: AMD64")
        .replace("xp smoke processor architecture w6432 env: ", "xp smoke processor architecture w6432 env: AMD64")
        .replace("xp smoke wmic os caption: Microsoft Windows XP Professional", "xp smoke wmic os caption: Microsoft Windows 7 Ultimate")
        .replace("xp smoke wmic os csdversion: Service Pack 3", "xp smoke wmic os csdversion: Service Pack 1"),
        encoding="utf-8",
    )
    evidence["smoke_results"][0]["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file host-probe ver output "
        "must contain Windows XP version marker '5.1.', got ['Microsoft Windows [Version 6.1.7601]']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file processor architecture env "
        "must be ['x86'] for XP x86, got ['AMD64']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file processor architecture w6432 env "
        "must be empty for XP x86, got ['AMD64']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file WMIC OS caption "
        "must prove Windows XP, got ['Microsoft Windows 7 Ultimate']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_file WMIC OS CSDVersion "
        "must prove 'SP3', got ['Service Pack 1']"
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


def test_xp_native_evidence_rejects_missing_security_smoke_provenance_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "legacy_crypto_profile_scoped")
    smoke_file = tmp_path / result["evidence_file"]
    missing_line = "CVE review reference: vendor-cve-advisory-review-2026-06"
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8").replace(f"{missing_line}\n", ""),
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result legacy_crypto_profile_scoped evidence_file "
        "missing security proof line: CVE review reference: vendor-cve-advisory-review-2026-06"
    ) in errors


def test_xp_native_evidence_rejects_duplicate_security_smoke_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "legacy_crypto_profile_scoped")
    smoke_file = tmp_path / result["evidence_file"]
    duplicate_line = "legacy crypto scope: profile-only\n"
    smoke_file.write_text(smoke_file.read_text(encoding="utf-8") + duplicate_line, encoding="utf-8")
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result legacy_crypto_profile_scoped evidence_file "
        "must include exactly one security proof line: legacy crypto scope: profile-only (got 2)"
    ) in errors


def test_xp_native_evidence_rejects_forbidden_legacy_crypto_security_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "legacy_crypto_profile_scoped")
    smoke_file = tmp_path / result["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8") + "weak crypto global default: true\n",
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result legacy_crypto_profile_scoped evidence_file "
        "contains forbidden security proof line: weak crypto global default: true"
    ) in errors


def test_xp_native_evidence_rejects_case_variant_forbidden_security_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "legacy_crypto_profile_scoped")
    smoke_file = tmp_path / result["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8") + "Weak Crypto Global Default: TRUE\n",
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result legacy_crypto_profile_scoped evidence_file "
        "contains forbidden security proof line: weak crypto global default: true"
    ) in errors


def test_xp_native_evidence_rejects_forbidden_modern_defaults_security_proof_line(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x64", "x64", "SP2", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    result = next(item for item in evidence["smoke_results"] if item["id"] == "modern_defaults_unchanged")
    smoke_file = tmp_path / result["evidence_file"]
    smoke_file.write_text(
        smoke_file.read_text(encoding="utf-8")
        + "modern TLS minimum: TLS 1.0\n"
        + "modern defaults unchanged: false\n",
        encoding="utf-8",
    )
    result["evidence_sha256"] = _sha256(smoke_file)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result modern_defaults_unchanged evidence_file "
        "contains forbidden security proof line: modern TLS minimum: TLS 1.0"
    ) in errors
    assert (
        "windows-xp-native-x64 smoke result modern_defaults_unchanged evidence_file "
        "contains forbidden security proof line: modern defaults unchanged: false"
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


def test_xp_native_evidence_rejects_smoke_command_host_identity_binding_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke = evidence["smoke_results"][0]
    smoke["command"] = smoke["command"].replace(
        "--host-label xp-x86-lab-01",
        "--host-label xp-x86-lab-02",
    )
    smoke["command"] = smoke["command"].replace(
        "--evidence-run-id xp-x86-1-0-2-20260620t120000z",
        "--evidence-run-id xp-x86-1-0-2-other",
    )
    smoke["command"] = smoke["command"].replace(
        "--observed-at-utc 2026-06-20T12:00:00Z",
        "--observed-at-utc 2026-06-20T12:30:00Z",
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--host-label xp-x86-lab-01, got ['xp-x86-lab-02']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--evidence-run-id xp-x86-1-0-2-20260620t120000z, got ['xp-x86-1-0-2-other']"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--observed-at-utc 2026-06-20T12:00:00Z, got ['2026-06-20T12:30:00Z']"
    ) in errors


def test_xp_native_evidence_rejects_smoke_command_release_source_binding_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke = evidence["smoke_results"][0]
    smoke["command"] = smoke["command"].replace(
        "--source-head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "--source-head-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch command must include exactly one "
        "--source-head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, got "
        "['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb']"
    ) in errors


def test_xp_native_evidence_rejects_security_smoke_command_provenance_mismatch(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke = next(item for item in evidence["smoke_results"] if item["id"] == "modern_defaults_unchanged")
    smoke["command"] = smoke["command"].replace(
        "--security-update-channel vendor-security-updates-2026-06",
        "--security-update-channel stale-security-channel",
    )
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result modern_defaults_unchanged command must include exactly one "
        "--security-update-channel vendor-security-updates-2026-06, got ['stale-security-channel']"
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


def test_xp_native_evidence_rejects_missing_security_patch_provenance(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    del evidence["security"]["patch_evidence"]["cve_review_reference"]
    evidence["security"]["patch_evidence"]["security_update_channel"] = ""
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference must be set" in errors
    assert "windows-xp-native-x86 evidence security.patch_evidence.security_update_channel must be set" in errors


def test_xp_native_evidence_rejects_non_string_security_patch_provenance(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["security"]["patch_evidence"]["security_update_channel"] = True
    evidence["security"]["patch_evidence"]["cve_review_reference"] = [
        "vendor-cve-advisory-review-2026-06"
    ]
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference "
        "must be a string"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.security_update_channel "
        "must be a string"
    ) in errors
    assert not any(
        "--security-update-channel True" in error
        or "--cve-review-reference ['vendor-cve-advisory-review-2026-06']" in error
        for error in errors
    )


def test_xp_native_evidence_rejects_placeholder_security_patch_provenance(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["security"]["patch_evidence"]["security_update_channel"] = "test-security-update-channel"
    evidence["security"]["patch_evidence"]["cve_review_reference"] = "<replace-with-real-cve-review>"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_xp_native_evidence_rejects_vague_security_patch_provenance(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["security"]["patch_evidence"]["security_update_channel"] = "monthly maintenance baseline"
    evidence["security"]["patch_evidence"]["cve_review_reference"] = "internal review 2026 06"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_xp_native_evidence_rejects_reserved_https_security_patch_provenance(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["security"]["patch_evidence"][
        "security_update_channel"
    ] = "https://example.com/security-updates/windows-xp"
    evidence["security"]["patch_evidence"][
        "cve_review_reference"
    ] = "https://example.com/security-advisory/CVE-2026-0001"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_xp_native_evidence_rejects_generic_https_cve_review_reference(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["security"]["patch_evidence"]["security_update_channel"] = "vendor-security-updates-2026-07"
    evidence["security"]["patch_evidence"]["cve_review_reference"] = "https://security.vendor.com/releases/2026-07"
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_xp_native_evidence_rejects_smoke_evidence_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["evidence_sha256"] = "0" * 64
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any("smoke result cli_launch evidence_file SHA-256 mismatch" in error for error in errors)


def test_xp_native_evidence_rejects_malformed_smoke_evidence_hash(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["evidence_sha256"] = True
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 smoke result cli_launch evidence_sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in errors
    assert all(
        "smoke result cli_launch evidence_file SHA-256 mismatch" not in error
        for error in errors
    )


def test_xp_native_evidence_rejects_malformed_smoke_result_binding_fields(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["smoke_results"][0]["id"] = True
    evidence["smoke_results"][1]["command"] = ["scripts/xp_smoke_runner.cmd"]
    evidence["smoke_results"][2]["evidence_file"] = True
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert "windows-xp-native-x86 smoke result entry id must be a string" in errors
    assert (
        "windows-xp-native-x86 smoke result gui_or_legacy_host_ui_launch "
        "command must be a string"
    ) in errors
    assert (
        "windows-xp-native-x86 smoke result loopback_profile_dry_run "
        "evidence_file must be a string"
    ) in errors
    assert all("--evidence-file True" not in error for error in errors)


def test_xp_native_evidence_rejects_malformed_artifact_command_and_names(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x64"
    names = _required_artifact_names(artifact_checker, target, tag)
    evidence = _valid_evidence(target, "x64", "SP2", tag, list(names))
    _attach_smoke_evidence_files(tmp_path, evidence)
    evidence["artifact_validation"]["command"] = True
    evidence["artifacts"][0] = {"name": names[0]}
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert f"{target} evidence artifact_validation.command must be a string" in errors
    assert f"{target} evidence artifact name entries must be strings" in errors
    assert all("{'name':" not in error for error in errors)


def test_xp_native_evidence_rejects_missing_artifact_manifest_smoke_proof(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x86"
    names = _required_artifact_names(artifact_checker, target, tag)
    evidence = _valid_evidence(target, "x86", "SP3", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_path = tmp_path / "xp-smoke-evidence" / "artifact_manifest_validation.txt"
    removed = next(name for name in names if name.endswith("SHA256SUMS.txt"))
    smoke_path.write_text(
        smoke_path.read_text(encoding="utf-8").replace(f"xp smoke artifact file: {removed}\n", ""),
        encoding="utf-8",
    )
    for result in evidence["smoke_results"]:
        if result["id"] == "artifact_manifest_validation":
            result["evidence_sha256"] = _sha256(smoke_path)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert any(
        "smoke result artifact_manifest_validation evidence_file artifact list proof "
        "must match expected release artifacts" in error
        for error in errors
    )


def test_xp_native_evidence_rejects_artifact_manifest_smoke_without_validation_lines(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x64"
    names = _required_artifact_names(artifact_checker, target, tag)
    evidence = _valid_evidence(target, "x64", "SP2", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_path = tmp_path / "xp-smoke-evidence" / "artifact_manifest_validation.txt"
    smoke_path.write_text(
        smoke_path.read_text(encoding="utf-8").replace(
            "xp smoke artifact manifest validated: true\n"
            "xp smoke artifact sha256s validated: true\n",
            "",
        ),
        encoding="utf-8",
    )
    for result in evidence["smoke_results"]:
        if result["id"] == "artifact_manifest_validation":
            result["evidence_sha256"] = _sha256(smoke_path)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result artifact_manifest_validation evidence_file "
        "missing artifact proof line: xp smoke artifact manifest validated: true"
    ) in errors
    assert (
        "windows-xp-native-x64 smoke result artifact_manifest_validation evidence_file "
        "missing artifact proof line: xp smoke artifact sha256s validated: true"
    ) in errors


def test_xp_native_evidence_rejects_duplicate_artifact_manifest_smoke_proof_line(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    target = "windows-xp-native-x64"
    names = _required_artifact_names(artifact_checker, target, tag)
    evidence = _valid_evidence(target, "x64", "SP2", tag, names)
    _attach_smoke_evidence_files(tmp_path, evidence)
    smoke_path = tmp_path / "xp-smoke-evidence" / "artifact_manifest_validation.txt"
    duplicate_line = "xp smoke artifact manifest validated: true\n"
    smoke_path.write_text(smoke_path.read_text(encoding="utf-8") + duplicate_line, encoding="utf-8")
    for result in evidence["smoke_results"]:
        if result["id"] == "artifact_manifest_validation":
            result["evidence_sha256"] = _sha256(smoke_path)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x64 smoke result artifact_manifest_validation evidence_file "
        "must include exactly one artifact proof line: "
        "xp smoke artifact manifest validated: true (got 2)"
    ) in errors


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
    assert "windows-xp-native-x64 evidence os.edition must be a string" in errors


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


def test_xp_native_evidence_rejects_missing_artifact_validation_strict(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, names)
    evidence["artifact_validation"]["command"] = evidence["artifact_validation"]["command"].replace(
        " --strict",
        "",
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact_validation.command must include exactly one --strict, got 0"
        in errors
    )


def test_xp_native_evidence_rejects_missing_artifact_validation_assets_dir(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --tag v1.0.2 --strict"
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
        "--assets-dir <artifact-dir> --tag v1.0.2 --strict"
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
        "--assets-dir native-dist/windows-xp --tag v1.0.2 --strict"
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


def test_xp_native_evidence_rejects_file_shaped_artifact_validation_assets_dir(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip "
        "--tag v1.0.2 --strict"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact_validation.command --assets-dir "
        "must be a directory path, got "
        "'native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip'"
    ) in errors


def test_xp_native_evidence_rejects_windows_drive_artifact_validation_assets_dir(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir C:/staged/windows-xp-native-x86/v1.0.2/artifacts --tag v1.0.2 --strict"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact_validation.command --assets-dir "
        "must be workspace-relative, got 'C:/staged/windows-xp-native-x86/v1.0.2/artifacts'"
    ) in errors


def test_xp_native_evidence_rejects_reserved_and_hidden_artifact_validation_assets_dir(
    tmp_path: Path,
) -> None:
    checker = _load_xp_native_evidence_checker()
    target = "windows-xp-native-x86"
    evidence = _valid_evidence(target, "x86", "SP3", "v1.0.2", [])
    evidence["artifact_validation"]["command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir .github/{target}/v1.0.2/artifacts --tag v1.0.2 --strict"
    )
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"{target} evidence artifact_validation.command --assets-dir "
        "must not point inside reserved workspace directory '.github'"
    ) in errors

    evidence["artifact_validation"]["command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir staged/.private/{target}/v1.0.2/artifacts --tag v1.0.2 --strict"
    )
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        f"{target} evidence artifact_validation.command --assets-dir "
        "must not contain hidden path segments: ['.private']"
    ) in errors


def test_xp_native_evidence_rejects_path_qualified_artifact_name(tmp_path: Path) -> None:
    checker = _load_xp_native_evidence_checker()
    artifact_checker = _load_platform_promotion_artifacts_checker()
    tag = f"v{artifact_checker.read_project_version()}"
    names = _required_artifact_names(artifact_checker, "windows-xp-native-x86", tag)
    artifact_name = names[0]
    evidence = _valid_evidence("windows-xp-native-x86", "x86", "SP3", tag, list(names))
    evidence["artifacts"][0] = f"nested/{artifact_name}"
    _attach_smoke_evidence_files(tmp_path, evidence)
    path = tmp_path / "xp-evidence.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")

    errors = checker.check_xp_native_evidence(path)

    assert (
        "windows-xp-native-x86 evidence artifact name must be a file name, "
        f"got 'nested/{artifact_name}'"
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
    host_identity = {
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
    }
    release_source = _xp_release_source()
    security_patch = {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "release_source": release_source,
        "os": os_record,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
        "host_identity": host_identity,
        "artifact_validation": {
            "passed": True,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir native-dist/windows-xp/{target}/{release_tag} --tag {release_tag} --strict"
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
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt "
                    f"--host-label {host_identity['host_label']} "
                    f"--evidence-run-id {host_identity['evidence_run_id']} "
                    f"--observed-at-utc {host_identity['observed_at_utc']} "
                    f"--source-workflow-run-url {release_source['workflow_run_url']} "
                    f"--source-head-sha {release_source['head_sha']} "
                    f"--source-run-attempt {release_source['run_attempt']} "
                    f"--security-update-channel {security_patch['security_update_channel']} "
                    f"--cve-review-reference {security_patch['cve_review_reference']} "
                    f'--os-name "{os_record["name"]}" '
                    f"--os-architecture {os_record['architecture']} "
                    f"--os-service-pack {os_record['service_pack']}"
                    + (
                        f' --os-edition "{os_record["edition"]}"'
                        if "edition" in os_record
                        else ""
                    )
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
            "patch_evidence": security_patch,
        },
    }


def _xp_release_source() -> dict[str, object]:
    return {
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "head_sha": "a" * 40,
        "run_attempt": 1,
    }


def _attach_smoke_evidence_files(root: Path, evidence: dict[str, Any]) -> None:
    host_identity = evidence["host_identity"]
    release_source = evidence["release_source"]
    host_probe_lines = _xp_host_probe_lines(evidence["target"], evidence["os"])
    for result in evidence["smoke_results"]:
        path = root / result["evidence_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        security_lines = _security_smoke_lines(str(result["id"]))
        path.write_text(
            f"xp smoke target: {evidence['target']}\n"
            f"xp smoke release: {evidence['release_tag']}\n"
            f"xp smoke id: {result['id']}\n"
            f"xp smoke os name: {evidence['os']['name']}\n"
            f"xp smoke os architecture: {evidence['os']['architecture']}\n"
            f"xp smoke os service pack: {evidence['os']['service_pack']}\n"
            + (
                f"xp smoke os edition: {evidence['os']['edition']}\n"
                if "edition" in evidence["os"]
                else ""
            )
            + host_probe_lines
            + f"xp smoke host label: {host_identity['host_label']}\n"
            f"xp smoke evidence run id: {host_identity['evidence_run_id']}\n"
            f"xp smoke observed at utc: {host_identity['observed_at_utc']}\n"
            f"xp smoke source workflow run: {release_source['workflow_run_url']}\n"
            f"xp smoke source head sha: {release_source['head_sha']}\n"
            f"xp smoke source run attempt: {release_source['run_attempt']}\n"
            f"{_artifact_manifest_smoke_lines(evidence, str(result['id']))}"
            f"{security_lines}"
            f"{result['id']} passed on Windows XP evidence host\n",
            encoding="utf-8",
        )
        result["evidence_sha256"] = _sha256(path)


def _xp_host_probe_lines(target: str, os_identity: dict[str, Any]) -> str:
    if target.endswith("x64"):
        ver_output = "Microsoft Windows [Version 5.2.3790]"
        processor_architecture = "AMD64"
        caption = "Microsoft Windows XP Professional x64 Edition"
    else:
        ver_output = "Microsoft Windows XP [Version 5.1.2600]"
        processor_architecture = "x86"
        caption = "Microsoft Windows XP Professional"
    service_pack = str(os_identity["service_pack"]).removeprefix("SP")
    return (
        "xp smoke host probe command: ver\n"
        f"xp smoke host probe output: {ver_output}\n"
        f"xp smoke processor architecture env: {processor_architecture}\n"
        "xp smoke processor architecture w6432 env: \n"
        f"xp smoke wmic os caption: {caption}\n"
        f"xp smoke wmic os csdversion: Service Pack {service_pack}\n"
    )


def _security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
            "security update channel: vendor-security-updates-2026-06\n"
            "CVE review reference: vendor-cve-advisory-review-2026-06\n"
        )
    return ""


def _artifact_manifest_smoke_lines(evidence: dict[str, Any], smoke_id: str) -> str:
    if smoke_id != "artifact_manifest_validation":
        return ""
    return (
        "".join(f"xp smoke artifact file: {name}\n" for name in evidence["artifacts"])
        + "xp smoke artifact manifest validated: true\n"
        + "xp smoke artifact sha256s validated: true\n"
    )


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
            **_manifest_record_metadata(name),
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


def _manifest_record_metadata(name: str) -> dict[str, str]:
    if name.endswith(".zip"):
        return {"architecture": _artifact_architecture(name), "format": "zip"}
    return {}


def _artifact_architecture(name: str) -> str:
    if "-windows-xp-x86-native." in name:
        return "x86"
    if "-windows-xp-x64-native." in name:
        return "x64"
    return ""


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
