from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_smartcards import (
    MobaSmartCardCertificate,
    build_mobagent_smartcard_plan,
    build_smartcard_inventory_plan,
    build_smartcard_management_gui_surface,
    build_smartcard_release_evidence_bundle_plan,
    build_smartcard_ssh_browser_plan,
    review_smartcard_certificate_selection,
    validate_smartcard_release_evidence,
    write_smartcard_release_evidence_bundle,
)
from remote_ops_workspace.models import Profile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_smartcard_inventory_plan_tracks_capi_management_actions() -> None:
    plan = build_smartcard_inventory_plan("windows-capi")

    assert plan.schema == "row.moba-smartcard.inventory-plan.v1"
    assert plan.provider == "microsoft-capi"
    assert plan.retrieves_openssh_public_key is True
    assert "add-certificate" in plan.management_actions
    assert "export-openssh-public-key" in plan.management_actions
    assert plan.commands[0][0] == "powershell"


def test_smartcard_selection_review_applies_profile_options_and_multiplex_policy() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    certificate = MobaSmartCardCertificate(
        certificate_id="cert-1",
        label="Operator Card",
        provider="microsoft-capi",
        public_key="ssh-rsa AAAA operator-card",
        fingerprint_sha256="a" * 64,
    )

    review = review_smartcard_certificate_selection(
        profile,
        "cert-1",
        [certificate],
        add_to_mobagent=True,
    )

    assert review.schema == "row.moba-smartcard.selection-review.v1"
    assert review.allowed is True
    assert review.ssh_browser_multiplex_required is True
    assert review.mobagent_add_required is True
    assert review.profile_options["smartcard_auth"] == "true"
    assert review.profile_options["smartcard_provider"] == "microsoft-capi"
    assert review.profile_options["smartcard_certificate_id"] == "cert-1"
    assert review.profile_options["add_smartcard_to_mobagent"] == "true"
    assert review.profile_options["smartcard_fingerprint_sha256"] == "a" * 64


def test_smartcard_selection_review_blocks_missing_certificate_without_force() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid")

    review = review_smartcard_certificate_selection(profile, "missing", [])
    forced = review_smartcard_certificate_selection(profile, "missing", [], force=True)

    assert review.allowed is False
    assert "not found" in review.prompt
    assert forced.allowed is True


def test_mobagent_smartcard_plan_records_global_add_setting() -> None:
    plan = build_mobagent_smartcard_plan(
        "cert-1",
        provider="microsoft-capi",
        action="add",
        agent_socket="agent.sock",
    )

    assert plan.schema == "row.moba-smartcard.mobagent-plan.v1"
    assert plan.action == "add"
    assert plan.global_setting_key == "add_smartcard_to_mobagent"
    assert plan.command[:4] == ["mobagent", "smartcard", "add", "cert-1"]
    assert "--agent-socket" in plan.command


def test_smartcard_ssh_browser_plan_forces_same_parameters_and_multiplex() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")

    plan = build_smartcard_ssh_browser_plan(profile, "cert-1", add_to_mobagent=True)

    assert plan.schema == "row.moba-smartcard.ssh-browser-plan.v1"
    assert plan.profile_name == "edge"
    assert plan.ssh_browser_same_parameters is True
    assert plan.multiplex_mode_required is True
    assert plan.profile_options["ssh_browser_multiplex"] == "true"
    assert plan.profile_options["smartcard_certificate_id"] == "cert-1"
    assert plan.terminal_command[0] == "ssh"
    assert plan.sftp_command[0] == "sftp"


def test_smartcard_management_gui_surface_binds_inventory_selection_and_mobagent() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    certificate = MobaSmartCardCertificate(
        certificate_id="cert-1",
        label="Operator Card",
        provider="microsoft-capi",
        subject="CN=Operator",
        issuer="CN=Issuer",
        public_key="ssh-rsa AAAA operator-card",
        fingerprint_sha256="b" * 64,
    )

    surface = build_smartcard_management_gui_surface(
        provider="windows-capi",
        certificates=[certificate],
        selected_certificate_id="cert-1",
        profile=profile,
        add_to_mobagent=True,
    )
    data = surface.to_dict()

    assert data["schema"] == "row.moba-smartcard.gui-management-surface.v1"
    assert data["provider"] == "microsoft-capi"
    assert data["inventory_plan"]["schema"] == "row.moba-smartcard.inventory-plan.v1"
    assert "certificate-table" in data["gui_controls"]
    assert "export-openssh-public-key" in data["gui_controls"]
    assert data["certificate_rows"][0]["public_key_available"] is True
    assert data["selection_review"]["allowed"] is True
    assert data["selection_review"]["ssh_browser_multiplex_required"] is True
    assert data["mobagent_plan"]["action"] == "add"
    assert data["ssh_browser_plan"]["ssh_browser_same_parameters"] is True
    assert any(command.startswith("row smartcard select-review edge") for command in data["commands"])


def test_smartcard_release_evidence_accepts_complete_bundle(tmp_path: Path) -> None:
    management_log = tmp_path / "management.txt"
    selection_log = tmp_path / "selection.txt"
    mobagent_log = tmp_path / "mobagent.txt"
    browser_log = tmp_path / "browser.txt"
    management_log.write_text("smartcard management ui listed cert\n", encoding="utf-8")
    selection_log.write_text("profile expert setting selected cert\n", encoding="utf-8")
    mobagent_log.write_text("mobagent loaded cert\n", encoding="utf-8")
    browser_log.write_text("ssh browser multiplex same parameters\n", encoding="utf-8")
    evidence = tmp_path / "smartcard-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-smartcard.release-evidence.v1",
                "release_target": "windows-x64",
                "certificate": {
                    "id": "cert-1",
                    "provider": "microsoft-capi",
                    "fingerprint_sha256": "a" * 64,
                    "openssh_public_key": "ssh-rsa AAAA operator-card",
                },
                "management_interface": {
                    "status": "passed",
                    "command": "row smartcard inventory-plan --provider microsoft-capi",
                    "evidence_file": "management.txt",
                    "evidence_sha256": _sha256(management_log),
                    "gui_visible": True,
                    "add_remove_controls": True,
                    "openssh_public_key_visible": True,
                },
                "ssh_session_selection": {
                    "status": "passed",
                    "command": "row smartcard select-review edge --certificate-id cert-1",
                    "evidence_file": "selection.txt",
                    "evidence_sha256": _sha256(selection_log),
                    "expert_setting_visible": True,
                    "certificate_selected": True,
                    "profile_saved": True,
                },
                "mobagent": {
                    "status": "passed",
                    "command": "row smartcard mobagent-plan --certificate-id cert-1",
                    "evidence_file": "mobagent.txt",
                    "evidence_sha256": _sha256(mobagent_log),
                    "global_add_setting": True,
                    "agent_loaded_certificate": True,
                },
                "ssh_browser": {
                    "status": "passed",
                    "command": "row smartcard ssh-browser-plan edge --certificate-id cert-1",
                    "evidence_file": "browser.txt",
                    "evidence_sha256": _sha256(browser_log),
                    "same_parameters_sftp": True,
                    "multiplex_mode": True,
                    "real_connected_session": True,
                    "sftp_browser_open": True,
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_smartcard_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["certificate_id"] == "cert-1"


def test_smartcard_release_evidence_bundle_writer_creates_valid_bundle(tmp_path: Path) -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    certificate = MobaSmartCardCertificate(
        certificate_id="cert-1",
        label="Operator Card",
        provider="windows-capi",
        public_key="ssh-rsa AAAA operator-card",
        fingerprint_sha256="a" * 64,
    )
    management_log = tmp_path / "source-management.txt"
    selection_log = tmp_path / "source-selection.txt"
    mobagent_log = tmp_path / "source-mobagent.txt"
    browser_log = tmp_path / "source-browser.txt"
    management_log.write_text("smartcard management ui listed cert\n", encoding="utf-8")
    selection_log.write_text("profile expert setting selected cert\n", encoding="utf-8")
    mobagent_log.write_text("mobagent loaded cert\n", encoding="utf-8")
    browser_log.write_text("ssh browser multiplex same parameters\n", encoding="utf-8")

    plan = build_smartcard_release_evidence_bundle_plan(
        profile,
        certificate,
        out_dir=tmp_path / "bundle",
        management_evidence=management_log,
        selection_evidence=selection_log,
        mobagent_evidence=mobagent_log,
        browser_evidence=browser_log,
        release_target="windows-x64",
        add_to_mobagent=True,
        gui_visible=True,
        add_remove_controls=True,
        openssh_public_key_visible=True,
        expert_setting_visible=True,
        certificate_selected=True,
        profile_saved=True,
        global_add_setting=True,
        agent_loaded_certificate=True,
        same_parameters_sftp=True,
        multiplex_mode=True,
        real_connected_session=True,
        sftp_browser_open=True,
    )
    result = write_smartcard_release_evidence_bundle(plan)

    assert result.validation.passed is True
    assert result.validation.errors == []
    assert "moba-smartcard-release.json" in result.files
    assert "evidence/ssh-browser.txt" in result.files
    assert Path(result.evidence_path).is_file()


def test_smartcard_release_evidence_rejects_missing_multiplex(tmp_path: Path) -> None:
    action = tmp_path / "action.txt"
    action.write_text("passed\n", encoding="utf-8")
    passed_action = {
        "status": "passed",
        "command": "action",
        "evidence_file": "action.txt",
        "evidence_sha256": _sha256(action),
    }
    evidence = tmp_path / "smartcard-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-smartcard.release-evidence.v1",
                "release_target": "windows-x64",
                "certificate": {
                    "id": "cert-1",
                    "provider": "microsoft-capi",
                    "fingerprint_sha256": "a" * 64,
                    "openssh_public_key": "ssh-rsa AAAA operator-card",
                },
                "management_interface": {
                    **passed_action,
                    "gui_visible": True,
                    "add_remove_controls": True,
                    "openssh_public_key_visible": True,
                },
                "ssh_session_selection": {
                    **passed_action,
                    "expert_setting_visible": True,
                    "certificate_selected": True,
                    "profile_saved": True,
                },
                "mobagent": {
                    **passed_action,
                    "global_add_setting": True,
                    "agent_loaded_certificate": True,
                },
                "ssh_browser": {
                    **passed_action,
                    "same_parameters_sftp": True,
                    "multiplex_mode": False,
                    "real_connected_session": True,
                    "sftp_browser_open": True,
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_smartcard_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "ssh_browser.multiplex_mode must be true" in result.errors


def test_smartcard_cli_commands_are_registered() -> None:
    parser = build_parser()
    inventory = parser.parse_args(["smartcard", "inventory-plan", "--json"])
    selection = parser.parse_args(
        [
            "smartcard",
            "select-review",
            "edge",
            "--certificate-id",
            "cert-1",
            "--certificate",
            "cert-1|Operator Card|microsoft-capi",
            "--json",
        ]
    )
    mobagent = parser.parse_args(["smartcard", "mobagent-plan", "--certificate-id", "cert-1", "--json"])
    browser = parser.parse_args(["smartcard", "ssh-browser-plan", "edge", "--certificate-id", "cert-1", "--json"])
    evidence_bundle = parser.parse_args(
        [
            "smartcard",
            "evidence-bundle",
            "edge",
            "--certificate-id",
            "cert-1",
            "--certificate",
            "cert-1|Operator Card|microsoft-capi|aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa|ssh-rsa AAAA operator-card",
            "--out-dir",
            "artifact",
            "--management-evidence",
            "management.txt",
            "--selection-evidence",
            "selection.txt",
            "--mobagent-evidence",
            "mobagent.txt",
            "--browser-evidence",
            "browser.txt",
            "--add-to-mobagent",
            "--gui-visible",
            "--add-remove-controls",
            "--openssh-public-key-visible",
            "--expert-setting-visible",
            "--certificate-selected",
            "--profile-saved",
            "--global-add-setting",
            "--agent-loaded-certificate",
            "--same-parameters-sftp",
            "--multiplex-mode",
            "--real-connected-session",
            "--sftp-browser-open",
            "--json",
        ]
    )
    evidence = parser.parse_args(["smartcard", "evidence-verify", "--evidence", "smartcard.json", "--json"])

    assert inventory.func.__name__ == "cmd_smartcard_inventory_plan"
    assert selection.func.__name__ == "cmd_smartcard_select_review"
    assert mobagent.func.__name__ == "cmd_smartcard_mobagent_plan"
    assert browser.func.__name__ == "cmd_smartcard_ssh_browser_plan"
    assert evidence_bundle.func.__name__ == "cmd_smartcard_evidence_bundle"
    assert evidence.func.__name__ == "cmd_smartcard_evidence_verify"
