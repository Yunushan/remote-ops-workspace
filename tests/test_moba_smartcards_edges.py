from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.moba_smartcards as smartcards
from remote_ops_workspace.models import Profile


def _profile(protocol: str = "ssh") -> Profile:
    return Profile(name="edge", protocol=protocol, host="edge.example", username="operator")


def _certificate(**overrides: str) -> smartcards.MobaSmartCardCertificate:
    values = {
        "certificate_id": "cert-1",
        "label": "Operator Card",
        "provider": "microsoft-capi",
    }
    values.update(overrides)
    return smartcards.MobaSmartCardCertificate(**values)


def test_certificate_and_release_value_objects_serialize(tmp_path: Path) -> None:
    certificate = smartcards.MobaSmartCardCertificate.from_dict(
        {
            "id": "cert-1",
            "subject": "CN=Operator",
            "provider": "windows-capi",
            "source": "store",
        }
    )
    assert certificate.label == "CN=Operator"
    assert certificate.to_dict()["provider"] == "microsoft-capi"

    validation = smartcards.MobaSmartCardReleaseEvidenceValidation(
        evidence_path="evidence.json",
        assets_dir=".",
        passed=False,
        errors=["missing"],
        warnings=[],
        summary={},
    )
    assert validation.to_dict()["errors"] == ["missing"]

    plan = smartcards.build_smartcard_release_evidence_bundle_plan(
        _profile(),
        _certificate(),
        out_dir=tmp_path,
        management_evidence=tmp_path / "management.txt",
        selection_evidence=tmp_path / "selection.txt",
        mobagent_evidence=tmp_path / "mobagent.txt",
        browser_evidence=tmp_path / "browser.txt",
    )
    assert "incomplete" in " ".join(plan.notes).lower()
    assert plan.to_dict()["certificate"]["id"] == "cert-1"
    result = smartcards.MobaSmartCardReleaseEvidenceBundleResult(
        plan=plan,
        evidence_path=plan.evidence_path,
        files=("evidence.json",),
        validation=validation,
        notes=[],
    )
    assert result.to_dict()["validation"]["passed"] is False


def test_pkcs11_inventory_and_management_surface_empty_states() -> None:
    inventory = smartcards.build_smartcard_inventory_plan("/usr/lib/opensc-pkcs11.so")
    assert inventory.commands == [["ssh-keygen", "-D", "/usr/lib/opensc-pkcs11.so"]]

    pending = smartcards.build_smartcard_management_gui_surface(certificates=[])
    assert pending.selected_certificate_id == "pending-selection"
    assert pending.selection_review is None
    assert pending.mobagent_plan is None
    assert pending.ssh_browser_plan is None
    assert len(pending.commands) == 1

    certificate_only = smartcards.build_smartcard_management_gui_surface(
        certificates=[_certificate()],
    )
    assert certificate_only.selection_review is None
    assert certificate_only.mobagent_plan is not None
    assert certificate_only.ssh_browser_plan is None
    assert certificate_only.commands[-1].startswith("row smartcard mobagent-plan")


def test_selection_and_browser_plans_reject_non_ssh_profiles() -> None:
    with pytest.raises(ValueError, match="requires an ssh profile"):
        smartcards.review_smartcard_certificate_selection(
            _profile("sftp"),
            "cert-1",
            [_certificate()],
        )
    with pytest.raises(ValueError, match="requires an ssh profile"):
        smartcards.build_smartcard_ssh_browser_plan(_profile("sftp"), "cert-1")


def test_selection_without_optional_certificate_metadata() -> None:
    review = smartcards.review_smartcard_certificate_selection(
        _profile(),
        "cert-1",
        [_certificate(public_key="", fingerprint_sha256="")],
    )
    assert review.allowed is True
    assert "smartcard_public_key" not in review.profile_options
    assert "smartcard_fingerprint_sha256" not in review.profile_options


def test_mobagent_rejects_unknown_action_and_supports_default_socketless_plan() -> None:
    with pytest.raises(ValueError, match="must be add, remove or list"):
        smartcards.build_mobagent_smartcard_plan("cert-1", action="replace")
    plan = smartcards.build_mobagent_smartcard_plan("cert-1", action="list")
    assert "--agent-socket" not in plan.command


def test_bundle_plan_records_disallowed_selection_defensively(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = SimpleNamespace(allowed=False, certificate_id="cert-1")
    mobagent = SimpleNamespace(command=["mobagent", "smartcard", "list", "cert-1"])
    browser = SimpleNamespace(certificate_id="cert-1")
    surface = SimpleNamespace(
        provider="microsoft-capi",
        selection_review=selection,
        mobagent_plan=mobagent,
        ssh_browser_plan=browser,
    )
    monkeypatch.setattr(smartcards, "build_smartcard_management_gui_surface", lambda **_kwargs: surface)
    plan = smartcards.build_smartcard_release_evidence_bundle_plan(
        _profile(),
        _certificate(),
        out_dir=tmp_path,
        management_evidence=tmp_path / "management.txt",
        selection_evidence=tmp_path / "selection.txt",
        mobagent_evidence=tmp_path / "mobagent.txt",
        browser_evidence=tmp_path / "browser.txt",
    )
    assert any("selection is not allowed" in note for note in plan.notes)


def test_bundle_writer_rejects_wrong_schema(tmp_path: Path) -> None:
    plan = smartcards.build_smartcard_release_evidence_bundle_plan(
        _profile(),
        _certificate(),
        out_dir=tmp_path,
        management_evidence=tmp_path / "management.txt",
        selection_evidence=tmp_path / "selection.txt",
        mobagent_evidence=tmp_path / "mobagent.txt",
        browser_evidence=tmp_path / "browser.txt",
    )
    plan.schema = "wrong"
    with pytest.raises(ValueError, match="bundle schema"):
        smartcards.write_smartcard_release_evidence_bundle(plan)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not valid JSON"),
        ("[]", "root must be a JSON object"),
    ],
)
def test_evidence_validator_rejects_malformed_roots(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(content, encoding="utf-8")
    result = smartcards.validate_smartcard_release_evidence(evidence)
    assert any(message in error for error in result.errors)


def test_evidence_validator_reports_missing_file_and_required_fields(tmp_path: Path) -> None:
    result = smartcards.validate_smartcard_release_evidence(tmp_path / "missing.json")
    assert result.passed is False
    assert any("cannot be read" in error for error in result.errors)
    assert any("schema must be" in error for error in result.errors)
    assert any("management_interface.gui_visible must be true" in error for error in result.errors)
    assert any("ssh_session_selection.profile_saved must be true" in error for error in result.errors)
    assert any("mobagent.global_add_setting must be true" in error for error in result.errors)
    assert any("ssh_browser.sftp_browser_open must be true" in error for error in result.errors)


def test_evidence_helpers_reject_invalid_shapes_and_digests() -> None:
    errors: list[str] = []
    assert smartcards._optional_sha256("", "digest") == ""
    assert smartcards._required_sha256("\n", "digest", errors) == "\n"
    assert any("digest is invalid" in error for error in errors)

    with pytest.raises(ValueError, match="control characters"):
        smartcards._required_sha256("\n", "digest")
    with pytest.raises(ValueError, match="lowercase 64-character"):
        smartcards._required_sha256("not-a-digest", "digest")
    assert smartcards._required_sha256("not-a-digest", "digest", errors) == "not-a-digest"
    assert smartcards._required_mapping({"item": []}, "item", errors) == {}
    assert smartcards._required_text({"item": "bad\ntext"}, "item", errors) == "bad\ntext"
    assert smartcards._required_text({}, "item", errors) == ""
    assert any("item must be a JSON object" in error for error in errors)
    assert any("item must be a non-empty string" in error for error in errors)


def test_action_evidence_and_asset_validation_fail_closed(tmp_path: Path) -> None:
    errors: list[str] = []
    smartcards._validate_action_evidence({}, tmp_path, errors, "action")
    assert "action.status must be passed" in errors
    assert "action.command must record the executed action" in errors

    absolute = tmp_path / "absolute.txt"
    smartcards._validate_asset_hash(tmp_path, str(absolute), "a" * 64, errors, "absolute")
    smartcards._validate_asset_hash(tmp_path, "missing.txt", "a" * 64, errors, "missing")
    directory = tmp_path / "directory"
    directory.mkdir()
    smartcards._validate_asset_hash(tmp_path, "directory", "a" * 64, errors, "directory")
    file_path = tmp_path / "asset.txt"
    file_path.write_text("content", encoding="utf-8")
    smartcards._validate_asset_hash(tmp_path, "asset.txt", "a" * 64, errors, "mismatch")

    assert any("absolute.evidence_file is invalid" in error for error in errors)
    assert any("missing.evidence_file does not exist" in error for error in errors)
    assert any("directory.evidence_file is not a file" in error for error in errors)
    assert any("mismatch.evidence_sha256 does not match" in error for error in errors)
    with pytest.raises(ValueError, match="inside assets_dir"):
        smartcards._resolve_evidence_asset(tmp_path, "../escape.txt")


def test_evidence_copy_rejects_missing_source_and_skips_copy_to_same_target(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    with pytest.raises(ValueError, match="evidence file is missing"):
        smartcards._copy_evidence_asset(
            tmp_path / "missing.txt",
            evidence_dir,
            "management-interface",
            tmp_path,
        )

    target = evidence_dir / "management-interface.txt"
    target.write_text("already present", encoding="utf-8")
    relative = smartcards._copy_evidence_asset(
        target,
        evidence_dir,
        "management-interface",
        tmp_path,
    )
    assert relative == "evidence/management-interface.txt"


def test_invalid_evidence_document_exercises_boolean_contracts(tmp_path: Path) -> None:
    evidence = tmp_path / "invalid.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "release_target": "target",
                "certificate": {
                    "id": "cert-1",
                    "provider": "microsoft-capi",
                    "fingerprint_sha256": "bad",
                    "openssh_public_key": "ssh-rsa AAAA",
                },
                "management_interface": {},
                "ssh_session_selection": {},
                "mobagent": {},
                "ssh_browser": {},
            }
        ),
        encoding="utf-8",
    )
    result = smartcards.validate_smartcard_release_evidence(evidence, assets_dir=tmp_path)
    assert result.passed is False
    assert len(result.errors) > 10
