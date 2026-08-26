from __future__ import annotations

import builtins
import hashlib
import json
from base64 import b64encode
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import remote_ops_workspace.moba_customizer as customizer
from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_customizer import (
    build_enterprise_update_channel_plan,
    build_moba_professional_customizer_plan,
    build_professional_deployment_evidence_bundle_plan,
    build_professional_deployment_plan,
    canonical_update_manifest_payload,
    validate_professional_deployment_evidence,
    validate_professional_update_manifest,
    write_moba_professional_customizer_bundle,
    write_professional_deployment_evidence_bundle,
)

_UPDATE_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
UPDATE_PUBLIC_KEY = "ed25519:" + b64encode(
    _UPDATE_PRIVATE_KEY.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
).decode("ascii")


def test_moba_professional_customizer_bundle_contains_enterprise_assets(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    profiles_path = tmp_path / "profiles.json"
    logo_path = tmp_path / "logo.svg"
    settings_path.write_text(json.dumps({"version": 1, "theme": "dark"}), encoding="utf-8")
    profiles_path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "name": "corp-edge",
                        "protocol": "ssh",
                        "host": "192.0.2.10",
                        "username": "operator",
                        "group": "corp",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    logo_path.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    plan = build_moba_professional_customizer_plan(
        tmp_path / "bundle",
        brand_name="Corp Ops",
        organization="Example Corp",
        welcome_message="Welcome, operator.\nUse approved sessions only.",
        logo_path=logo_path,
        settings_path=settings_path,
        profiles_path=profiles_path,
        lock_settings=["theme=dark", "confirm_before_launch=true"],
    )
    bundle = write_moba_professional_customizer_bundle(plan)

    manifest = json.loads((bundle.root / "manifest.json").read_text(encoding="utf-8"))
    branding = json.loads((bundle.root / "branding" / "branding.json").read_text(encoding="utf-8"))
    policy = json.loads((bundle.root / "config" / "policy.json").read_text(encoding="utf-8"))
    profiles = json.loads((bundle.root / "config" / "profiles.json").read_text(encoding="utf-8"))
    sums = (bundle.root / "SHA256SUMS.txt").read_text(encoding="utf-8")

    assert manifest["brand_name"] == "Corp Ops"
    assert manifest["profile_count"] == 1
    assert manifest["locked_setting_count"] == 2
    assert branding["logo"] == "branding/logo.svg"
    assert "Welcome, operator." in (bundle.root / "welcome.txt").read_text(encoding="utf-8")
    assert policy["locked_settings"] == [
        {"key": "theme", "value": "dark"},
        {"key": "confirm_before_launch", "value": "true"},
    ]
    assert profiles["profiles"][0]["name"] == "corp-edge"
    assert "manifest.json" in sums
    assert "config/profiles.json" in bundle.sha256s


def test_moba_professional_customizer_rejects_existing_output_without_force(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "old.txt").write_text("existing", encoding="utf-8")
    plan = build_moba_professional_customizer_plan(output, brand_name="Corp Ops")

    try:
        write_moba_professional_customizer_bundle(plan)
    except FileExistsError as exc:
        assert "--force" in str(exc)
    else:
        raise AssertionError("customizer should not overwrite a non-empty output without --force")


def test_moba_professional_deployment_plan_covers_installers_locks_and_updates() -> None:
    plan = build_professional_deployment_plan(
        brand_name="Corp Ops",
        organization="Example Corp",
        version="1.0.2",
        update_url="https://updates.example.com/row/stable.json",
        update_public_key=UPDATE_PUBLIC_KEY,
        lock_settings=["theme=dark"],
    )

    assert plan.schema == "row.moba-professional.deployment-plan.v1"
    assert plan.installer_branding.installer_targets == ["windows-exe", "windows-msi"]
    assert plan.installer_branding.artifact_names["windows-exe"] == "corp-ops-1.0.2-setup.exe"
    assert plan.installer_branding.artifact_names["windows-msi"] == "corp-ops-1.0.2.msi"
    assert plan.policy_locks.locked_settings == [{"key": "theme", "value": "dark"}]
    assert "gui" in plan.policy_locks.enforcement_surfaces
    assert "launcher" in plan.policy_locks.enforcement_surfaces
    assert plan.update_channel.require_signature is True
    assert plan.update_channel.update_url == "https://updates.example.com/row/stable.json"


def test_moba_professional_update_channel_requires_https() -> None:
    try:
        build_enterprise_update_channel_plan(
            update_url="http://updates.example.com/row.json",
            public_key=UPDATE_PUBLIC_KEY,
        )
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("enterprise update channels must require HTTPS")


def test_moba_professional_update_channel_requires_ed25519_public_key() -> None:
    try:
        build_enterprise_update_channel_plan(
            update_url="https://updates.example.com/row.json",
            public_key="hmac-sha256:legacy-shared-secret",
        )
    except ValueError as exc:
        assert "ed25519" in str(exc)
    else:
        raise AssertionError("enterprise update channels must reject symmetric verifier secrets")


def test_moba_professional_update_manifest_accepts_signed_https_artifacts(tmp_path: Path) -> None:
    artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=artifact,
        public_key=UPDATE_PUBLIC_KEY,
    )

    result = validate_professional_update_manifest(
        manifest,
        public_key=UPDATE_PUBLIC_KEY,
        expected_channel="stable",
        expected_organization="Example Corp",
        assets_dir=tmp_path,
    )

    assert result.passed is True
    assert result.summary["signature_algorithm"] == "ed25519"
    assert result.summary["artifact_count"] == 1


def test_moba_professional_update_manifest_rejects_tampered_signature(tmp_path: Path) -> None:
    artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=artifact,
        public_key=UPDATE_PUBLIC_KEY,
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["artifacts"][0]["url"] = "http://updates.example.com/corp-ops-1.0.2-setup.exe"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = validate_professional_update_manifest(
        manifest,
        public_key=UPDATE_PUBLIC_KEY,
        expected_channel="stable",
        assets_dir=tmp_path,
    )

    assert result.passed is False
    assert "artifacts[1].url must be an HTTPS URL" in result.errors
    assert "signature.payload_sha256 does not match canonical manifest payload" in result.errors


def test_moba_professional_deployment_evidence_accepts_complete_bundle(tmp_path: Path) -> None:
    bundle = _write_evidence_asset(tmp_path, "bundle.txt", "bundle manifest proof")
    installer = _write_evidence_asset(tmp_path, "installer.txt", "installer metadata proof")
    policy = _write_evidence_asset(tmp_path, "policy.txt", "policy lock proof")
    update = _write_evidence_asset(tmp_path, "update.txt", "update signature proof")
    update_artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    update_manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=update_artifact,
        public_key=UPDATE_PUBLIC_KEY,
    )
    evidence_path = tmp_path / "deployment.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema": "row.moba-professional.deployment-evidence.v1",
                "release_target": "windows-x64",
                "brand_name": "Corp Ops",
                "version": "1.0.2",
                "bundle_manifest": {
                    "status": "passed",
                    "command": "row customizer build --brand-name Corp Ops",
                    "evidence_file": "bundle.txt",
                    "evidence_sha256": _sha256(bundle),
                    "manifest_sha256": "a" * 64,
                    "sha256s_present": True,
                },
                "installer_branding": {
                    "status": "passed",
                    "command": "windows installer metadata smoke",
                    "evidence_file": "installer.txt",
                    "evidence_sha256": _sha256(installer),
                    "windows_exe_rebranded": True,
                    "windows_msi_rebranded": True,
                    "product_name_matches_brand": True,
                    "logo_applied": True,
                },
                "policy_locks": {
                    "status": "passed",
                    "command": "policy lock smoke",
                    "evidence_file": "policy.txt",
                    "evidence_sha256": _sha256(policy),
                    "locked_settings": [{"key": "theme", "value": "dark"}],
                    "surfaces": {
                        "cli": True,
                        "gui": True,
                        "web": True,
                        "profile-editor": True,
                        "quick-connect": True,
                        "launcher": True,
                    },
                },
                "update_channel": {
                    "status": "passed",
                    "command": "update channel smoke",
                    "evidence_file": "update.txt",
                    "evidence_sha256": _sha256(update),
                    "https_update_url": True,
                    "signature_verified": True,
                    "organization_channel": True,
                    "manifest_file": update_manifest.name,
                    "manifest_sha256": _sha256(update_manifest),
                    "public_key": UPDATE_PUBLIC_KEY,
                    "channel": "stable",
                    "organization": "Example Corp",
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_professional_deployment_evidence(evidence_path, assets_dir=tmp_path)

    assert result.passed is True
    assert result.summary["release_target"] == "windows-x64"
    assert result.summary["surface_count"] == 6
    assert result.summary["update_manifest"]["artifact_count"] == 1


def test_moba_professional_deployment_evidence_bundle_writer_accepts_complete_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    bundle = _write_evidence_asset(source, "bundle.txt", "bundle manifest proof")
    installer = _write_evidence_asset(source, "installer.txt", "installer metadata proof")
    policy = _write_evidence_asset(source, "policy.txt", "policy lock proof")
    update = _write_evidence_asset(source, "update.txt", "update signature proof")
    update_artifact = _write_evidence_asset(source, "corp-ops-1.0.2-setup.exe", "installer")
    update_manifest = _write_signed_update_manifest(
        source,
        artifact=update_artifact,
        public_key=UPDATE_PUBLIC_KEY,
    )
    deployment = build_professional_deployment_plan(
        brand_name="Corp Ops",
        organization="Example Corp",
        version="1.0.2",
        update_url="https://updates.example.com/row/stable.json",
        update_public_key=UPDATE_PUBLIC_KEY,
        lock_settings=["theme=dark"],
    )
    plan = build_professional_deployment_evidence_bundle_plan(
        deployment,
        out_dir=tmp_path / "bundle",
        bundle_manifest_evidence=bundle,
        installer_evidence=installer,
        policy_evidence=policy,
        update_evidence=update,
        update_manifest=update_manifest,
        bundle_manifest_sha256="a" * 64,
        release_target="windows-x64",
        surfaces={surface: True for surface in deployment.policy_locks.enforcement_surfaces},
        sha256s_present=True,
        windows_exe_rebranded=True,
        windows_msi_rebranded=True,
        product_name_matches_brand=True,
        logo_applied=True,
        https_update_url=True,
        signature_verified=True,
        organization_channel=True,
    )

    result = write_professional_deployment_evidence_bundle(plan)
    payload = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))

    assert result.validation.passed is True
    assert payload["schema"] == "row.moba-professional.deployment-evidence.v1"
    assert payload["update_channel"]["manifest_file"] == "evidence/update-manifest.json"
    assert "moba-professional-deployment.json" in result.files
    assert "evidence/update-manifest.json" in result.files
    assert "corp-ops-1.0.2-setup.exe" in result.files
    assert result.validation.summary["update_manifest"]["artifact_count"] == 1


def test_moba_professional_deployment_evidence_rejects_missing_surface(tmp_path: Path) -> None:
    bundle = _write_evidence_asset(tmp_path, "bundle.txt", "bundle manifest proof")
    installer = _write_evidence_asset(tmp_path, "installer.txt", "installer metadata proof")
    policy = _write_evidence_asset(tmp_path, "policy.txt", "policy lock proof")
    update = _write_evidence_asset(tmp_path, "update.txt", "update signature proof")
    update_artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    update_manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=update_artifact,
        public_key=UPDATE_PUBLIC_KEY,
    )
    evidence_path = tmp_path / "deployment.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema": "row.moba-professional.deployment-evidence.v1",
                "release_target": "windows-x64",
                "brand_name": "Corp Ops",
                "version": "1.0.2",
                "bundle_manifest": {
                    "status": "passed",
                    "command": "row customizer build --brand-name Corp Ops",
                    "evidence_file": "bundle.txt",
                    "evidence_sha256": _sha256(bundle),
                    "manifest_sha256": "a" * 64,
                    "sha256s_present": True,
                },
                "installer_branding": {
                    "status": "passed",
                    "command": "windows installer metadata smoke",
                    "evidence_file": "installer.txt",
                    "evidence_sha256": _sha256(installer),
                    "windows_exe_rebranded": True,
                    "windows_msi_rebranded": True,
                    "product_name_matches_brand": True,
                    "logo_applied": True,
                },
                "policy_locks": {
                    "status": "passed",
                    "command": "policy lock smoke",
                    "evidence_file": "policy.txt",
                    "evidence_sha256": _sha256(policy),
                    "locked_settings": [{"key": "theme", "value": "dark"}],
                    "surfaces": {
                        "cli": True,
                        "web": True,
                        "profile-editor": True,
                        "quick-connect": True,
                        "launcher": True,
                    },
                },
                "update_channel": {
                    "status": "passed",
                    "command": "update channel smoke",
                    "evidence_file": "update.txt",
                    "evidence_sha256": _sha256(update),
                    "https_update_url": True,
                    "signature_verified": True,
                    "organization_channel": True,
                    "manifest_file": update_manifest.name,
                    "manifest_sha256": _sha256(update_manifest),
                    "public_key": UPDATE_PUBLIC_KEY,
                    "channel": "stable",
                    "organization": "Example Corp",
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_professional_deployment_evidence(evidence_path, assets_dir=tmp_path)

    assert result.passed is False
    assert "policy_locks.surfaces.gui must be true" in result.errors


def test_customizer_cli_command_is_registered() -> None:
    args = build_parser().parse_args(
        ["customizer", "build", "--out", "dist/custom", "--brand-name", "Corp Ops"]
    )

    assert args.func.__name__ == "cmd_customizer_build"

    deployment = build_parser().parse_args(
        [
            "customizer",
            "deployment-plan",
            "--brand-name",
            "Corp Ops",
            "--update-url",
            "https://updates.example.com/row/stable.json",
            "--update-public-key",
            UPDATE_PUBLIC_KEY,
            "--lock-setting",
            "theme=dark",
            "--json",
        ]
    )
    assert deployment.func.__name__ == "cmd_customizer_deployment_plan"

    evidence_bundle = build_parser().parse_args(
        [
            "customizer",
            "evidence-bundle",
            "--brand-name",
            "Corp Ops",
            "--organization",
            "Example Corp",
            "--update-url",
            "https://updates.example.com/row/stable.json",
            "--update-public-key",
            UPDATE_PUBLIC_KEY,
            "--lock-setting",
            "theme=dark",
            "--out-dir",
            "artifacts/deployment",
            "--bundle-manifest-evidence",
            "bundle.txt",
            "--installer-evidence",
            "installer.txt",
            "--policy-evidence",
            "policy.txt",
            "--update-evidence",
            "update.txt",
            "--update-manifest",
            "stable-update.json",
            "--bundle-manifest-sha256",
            "a" * 64,
            "--sha256s-present",
            "--windows-exe-rebranded",
            "--windows-msi-rebranded",
            "--product-name-matches-brand",
            "--logo-applied",
            "--all-policy-surfaces-passed",
            "--https-update-url",
            "--signature-verified",
            "--organization-channel",
            "--json",
        ]
    )
    assert evidence_bundle.func.__name__ == "cmd_customizer_evidence_bundle"

    verify = build_parser().parse_args(
        ["customizer", "evidence-verify", "--evidence", "deployment.json", "--json"]
    )
    assert verify.func.__name__ == "cmd_customizer_evidence_verify"

    update = build_parser().parse_args(
        [
            "customizer",
            "update-verify",
            "--manifest",
            "stable.json",
            "--public-key",
            UPDATE_PUBLIC_KEY,
            "--channel",
            "stable",
            "--json",
        ]
    )
    assert update.func.__name__ == "cmd_customizer_update_verify"


def test_customizer_result_serializers_and_incomplete_evidence_plan(tmp_path: Path) -> None:
    deployment = build_professional_deployment_plan(
        brand_name="Corp Ops",
        organization="Example Corp",
        version="1.0.2",
        update_url="https://updates.example.com/stable.json",
        update_public_key=UPDATE_PUBLIC_KEY,
        lock_settings=["theme=dark"],
    )
    evidence_plan = build_professional_deployment_evidence_bundle_plan(
        deployment,
        out_dir=tmp_path / "evidence",
        bundle_manifest_evidence=tmp_path / "bundle.txt",
        installer_evidence=tmp_path / "installer.txt",
        policy_evidence=tmp_path / "policy.txt",
        update_evidence=tmp_path / "update.txt",
        update_manifest=tmp_path / "update.json",
        bundle_manifest_sha256="a" * 64,
    )
    validation = customizer.MobaProfessionalDeploymentEvidenceValidation(
        evidence_path="deployment.json",
        assets_dir=".",
        passed=False,
        errors=["expected"],
        warnings=[],
        summary={"surface_count": 0},
    )
    result = customizer.MobaProfessionalDeploymentEvidenceBundleResult(
        plan=evidence_plan,
        evidence_path="deployment.json",
        files=("deployment.json",),
        validation=validation,
        notes=["incomplete"],
    )
    update_validation = customizer.MobaProfessionalUpdateManifestValidation(
        manifest_path="update.json",
        assets_dir=".",
        passed=False,
        errors=["expected"],
        warnings=[],
        summary={"artifact_count": 0},
    )
    bundle = customizer.MobaProfessionalCustomizerBundle(
        root=tmp_path,
        files=[tmp_path / "manifest.json"],
        manifest={"schema_version": 1},
        sha256s={"manifest.json": "a" * 64},
    )

    assert bundle.to_dict()["root"] == str(tmp_path)
    assert deployment.to_dict()["installer_branding"]["brand_name"] == "Corp Ops"
    assert evidence_plan.to_dict()["sha256s_present"] is False
    assert "flags are incomplete" in evidence_plan.notes[-1]
    assert validation.to_dict()["passed"] is False
    assert result.to_dict()["files"] == ["deployment.json"]
    assert update_validation.to_dict()["summary"] == {"artifact_count": 0}


def test_customizer_plan_builders_reject_invalid_required_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="brand name is required"):
        build_moba_professional_customizer_plan(tmp_path / "bundle", brand_name=" ")
    with pytest.raises(ValueError, match="brand name is required"):
        customizer.build_installer_branding_plan(brand_name=" ")
    with pytest.raises(ValueError, match="at least one locked setting"):
        customizer.build_enterprise_policy_lock_plan(lock_settings=[])
    with pytest.raises(ValueError, match="interval must be positive"):
        build_enterprise_update_channel_plan(
            update_url="https://updates.example.com/stable.json",
            public_key=UPDATE_PUBLIC_KEY,
            interval_hours=0,
        )

    deployment = build_professional_deployment_plan(
        brand_name="Corp Ops",
        update_url="https://updates.example.com/stable.json",
        update_public_key=UPDATE_PUBLIC_KEY,
        lock_settings=["theme=dark"],
    )
    evidence_plan = build_professional_deployment_evidence_bundle_plan(
        deployment,
        out_dir=tmp_path / "evidence",
        bundle_manifest_evidence=tmp_path / "bundle.txt",
        installer_evidence=tmp_path / "installer.txt",
        policy_evidence=tmp_path / "policy.txt",
        update_evidence=tmp_path / "update.txt",
        update_manifest=tmp_path / "update.json",
        bundle_manifest_sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="bundle schema"):
        write_professional_deployment_evidence_bundle(replace(evidence_plan, schema="wrong"))

    output_file = tmp_path / "not-a-directory"
    output_file.write_text("occupied", encoding="utf-8")
    customizer_plan = build_moba_professional_customizer_plan(output_file, brand_name="Corp Ops")
    with pytest.raises(ValueError, match="must be a directory"):
        write_moba_professional_customizer_bundle(customizer_plan)


def test_customizer_bundle_without_logo_and_json_loaders(tmp_path: Path) -> None:
    plan = build_moba_professional_customizer_plan(tmp_path / "bundle", brand_name="Corp Ops")
    bundle = write_moba_professional_customizer_bundle(plan)
    branding = json.loads((bundle.root / "branding" / "branding.json").read_text(encoding="utf-8"))
    assert branding["logo"] == ""

    json_list = tmp_path / "list.json"
    json_list.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON must be an object"):
        customizer._load_json_object(json_list, "settings")

    profiles_list = tmp_path / "profiles-list.json"
    profiles_list.write_text(
        json.dumps([{"name": "edge", "protocol": "ssh", "host": "192.0.2.10"}]),
        encoding="utf-8",
    )
    assert customizer._load_profiles(profiles_list)[0].name == "edge"

    invalid_root = tmp_path / "profiles-root.json"
    invalid_root.write_text("1", encoding="utf-8")
    with pytest.raises(ValueError, match="object or list"):
        customizer._load_profiles(invalid_root)

    invalid_collection = tmp_path / "profiles-collection.json"
    invalid_collection.write_text('{"profiles": "bad"}', encoding="utf-8")
    with pytest.raises(ValueError, match="requires a profiles list"):
        customizer._load_profiles(invalid_collection)

    invalid_entry = tmp_path / "profiles-entry.json"
    invalid_entry.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError, match="entry 1 must be an object"):
        customizer._load_profiles(invalid_entry)


def test_customizer_policy_logo_text_and_surface_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a list"):
        customizer._policy_with_locked_settings({"locked_settings": "bad"}, [])
    for malformed in (1, {"value": "dark"}, {"key": "theme"}):
        with pytest.raises(ValueError, match="entries must contain key and value"):
            customizer._policy_with_locked_settings({"locked_settings": [malformed]}, [])
    with pytest.raises(ValueError, match="duplicate locked setting"):
        customizer._policy_with_locked_settings(
            {
                "locked_settings": [
                    {"key": "theme", "value": "dark"},
                    {"key": "theme", "value": "light"},
                ]
            },
            [],
        )
    with pytest.raises(ValueError, match="must be key=value"):
        customizer._policy_with_locked_settings({}, ["theme"])
    with pytest.raises(ValueError, match="duplicate locked setting"):
        customizer._policy_with_locked_settings(
            {"locked_settings": [{"key": "theme", "value": "dark"}]},
            ["theme=light"],
        )

    with pytest.raises(ValueError, match="does not exist"):
        customizer._validate_logo_path(tmp_path / "missing.png")
    invalid_logo = tmp_path / "logo.txt"
    invalid_logo.write_text("logo", encoding="utf-8")
    with pytest.raises(ValueError, match="must use one of"):
        customizer._validate_logo_path(invalid_logo)

    with pytest.raises(ValueError, match="is required"):
        customizer._clean_multiline_text("", "welcome")
    with pytest.raises(ValueError, match="control characters"):
        customizer._clean_multiline_text("bad\x01", "welcome")
    with pytest.raises(ValueError, match="control characters"):
        customizer._clean_multiline_text("bad\x7f", "welcome")
    assert customizer._clean_multiline_text("one\r\ntwo\rthree", "welcome") == "one\ntwo\nthree"
    assert customizer._artifact_slug("---") == "remote-ops-workspace"

    with pytest.raises(ValueError, match="surface is required"):
        customizer._normalise_policy_surfaces([" "])
    with pytest.raises(ValueError, match="at least one"):
        customizer._normalise_policy_surfaces([])
    assert customizer._normalise_policy_surfaces(["GUI", "gui"]) == ["gui"]


def test_customizer_required_value_helpers_fail_closed() -> None:
    errors: list[str] = []
    assert customizer._required_sha256("bad\x01", "digest", errors) == "bad\x01"
    assert "digest is invalid" in errors[0]
    with pytest.raises(ValueError, match="control characters"):
        customizer._required_sha256("bad\x01", "digest")

    errors = []
    assert customizer._required_sha256("ABC", "digest", errors) == "ABC"
    assert "lowercase 64-character" in errors[0]
    with pytest.raises(ValueError, match="lowercase 64-character"):
        customizer._required_sha256("ABC", "digest")

    errors = []
    assert customizer._required_mapping({"section": []}, "section", errors) == {}
    assert errors == ["section must be a JSON object"]

    errors = []
    assert customizer._required_text({"name": "bad\x01"}, "name", errors) == "bad\x01"
    assert "name is invalid" in errors[0]
    assert customizer._required_text({"name": 1}, "name", errors) == ""
    assert "must be a non-empty string" in errors[-1]

    errors = []
    customizer._validate_action_evidence(
        {"status": "failed", "command": "", "evidence_file": "", "evidence_sha256": ""},
        Path("."),
        errors,
        "action",
    )
    assert "action.status must be passed" in errors
    assert "action.command must record the executed action" in errors


def test_customizer_evidence_asset_copy_and_hash_failures(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    with pytest.raises(ValueError, match="evidence file is missing"):
        customizer._copy_evidence_asset(
            tmp_path / "missing.txt",
            evidence_dir,
            "missing",
            tmp_path,
        )

    same_source = evidence_dir / "same.txt"
    same_source.write_text("proof", encoding="utf-8")
    assert (
        customizer._copy_evidence_asset(same_source, evidence_dir, "same", tmp_path)
        == "evidence/same.txt"
    )

    errors: list[str] = []
    customizer._validate_asset_hash(tmp_path, "../escape.txt", "a" * 64, errors, "asset")
    assert "is invalid" in errors[-1]
    customizer._validate_asset_hash(tmp_path, "missing.txt", "a" * 64, errors, "asset")
    assert "does not exist" in errors[-1]
    directory = tmp_path / "directory"
    directory.mkdir()
    customizer._validate_asset_hash(tmp_path, "directory", "a" * 64, errors, "asset")
    assert "is not a file" in errors[-1]
    asset = tmp_path / "asset.txt"
    asset.write_text("proof", encoding="utf-8")
    customizer._validate_asset_hash(tmp_path, "asset.txt", "a" * 64, errors, "asset")
    assert "does not match" in errors[-1]

    errors = []
    customizer._require_https_url("bad\x01", "url", errors)
    assert "url is invalid" in errors[0]
    with pytest.raises(ValueError, match="relative to assets_dir"):
        customizer._resolve_evidence_asset(tmp_path, str(asset.resolve()))
    with pytest.raises(ValueError, match="inside assets_dir"):
        customizer._resolve_evidence_asset(tmp_path, "../escape.txt")


def test_customizer_update_artifact_copy_rejects_malformed_inputs(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="cannot be read for artifact copy"):
        customizer._copy_update_manifest_artifacts(tmp_path / "missing.json", tmp_path, root)

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON for artifact copy"):
        customizer._copy_update_manifest_artifacts(invalid_json, tmp_path, root)

    list_root = tmp_path / "list-root.json"
    list_root.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be a JSON object"):
        customizer._copy_update_manifest_artifacts(list_root, tmp_path, root)

    no_artifacts = tmp_path / "no-artifacts.json"
    no_artifacts.write_text('{"artifacts": {}}', encoding="utf-8")
    assert customizer._copy_update_manifest_artifacts(no_artifacts, tmp_path, root) == []

    skipped = tmp_path / "skipped.json"
    skipped.write_text('{"artifacts": [1, {}]}', encoding="utf-8")
    assert customizer._copy_update_manifest_artifacts(skipped, tmp_path, root) == []

    invalid_path = tmp_path / "invalid-path.json"
    invalid_path.write_text('{"artifacts": [{"file": "../escape.bin"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match=r"artifacts\[1\]\.file is invalid"):
        customizer._copy_update_manifest_artifacts(invalid_path, tmp_path, root)

    missing_asset = tmp_path / "missing-asset.json"
    missing_asset.write_text('{"artifacts": [{"file": "missing.bin"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="artifact file is missing"):
        customizer._copy_update_manifest_artifacts(missing_asset, tmp_path, root)

    same_asset = root / "same.bin"
    same_asset.write_bytes(b"artifact")
    same_manifest = root / "same.json"
    same_manifest.write_text('{"artifacts": [{"file": "same.bin"}]}', encoding="utf-8")
    assert customizer._copy_update_manifest_artifacts(same_manifest, root, root) == ["same.bin"]


def test_customizer_signature_helpers_reject_unsupported_or_malformed_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    errors: list[str] = []
    assert (
        customizer._verify_update_manifest_signature(
            "rsa",
            public_key=UPDATE_PUBLIC_KEY,
            signature_value="value",
            payload=b"payload",
            errors=errors,
        )
        is False
    )
    assert errors == ["signature.algorithm must be ed25519"]

    with pytest.raises(ValueError, match="not valid base64"):
        customizer._validate_update_public_key("ed25519:not-base64!")
    with pytest.raises(ValueError, match="must contain 32 raw bytes"):
        customizer._validate_update_public_key("ed25519:" + b64encode(b"short").decode("ascii"))

    errors = []
    assert customizer._verify_ed25519_signature("invalid", "value", b"payload", errors) is False
    assert "must use ed25519" in errors[0]

    original_import = builtins.__import__

    def fail_cryptography_import(name: str, *args: object, **kwargs: object) -> object:
        if name.startswith("cryptography"):
            raise ImportError("blocked for test")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_cryptography_import)
    errors = []
    assert customizer._verify_ed25519_signature(UPDATE_PUBLIC_KEY, "value", b"payload", errors) is False
    assert "cryptography is required" in errors[0]
    monkeypatch.setattr(builtins, "__import__", original_import)

    errors = []
    assert customizer._verify_ed25519_signature(UPDATE_PUBLIC_KEY, "%%%", b"payload", errors) is False
    assert "signature material is invalid" in errors[0]


def test_deployment_evidence_validator_rejects_unreadable_and_malformed_roots(
    tmp_path: Path,
) -> None:
    missing = validate_professional_deployment_evidence(tmp_path / "missing.json")
    assert missing.passed is False
    assert "cannot be read" in missing.errors[0]

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{", encoding="utf-8")
    invalid = validate_professional_deployment_evidence(invalid_json)
    assert "not valid JSON" in invalid.errors[0]

    list_root = tmp_path / "list.json"
    list_root.write_text("[]", encoding="utf-8")
    list_result = validate_professional_deployment_evidence(list_root)
    assert "root must be a JSON object" in list_result.errors[0]


def test_deployment_evidence_validator_reports_all_failed_contracts(tmp_path: Path) -> None:
    evidence = tmp_path / "deployment.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "release_target": "windows-x64",
                "brand_name": "Corp Ops",
                "version": "1.0.2",
                "bundle_manifest": {
                    "status": "failed",
                    "command": "",
                    "evidence_file": "",
                    "evidence_sha256": "",
                    "manifest_sha256": "bad",
                    "sha256s_present": False,
                },
                "installer_branding": {
                    "status": "failed",
                    "command": "",
                    "evidence_file": "",
                    "evidence_sha256": "",
                },
                "policy_locks": {
                    "status": "failed",
                    "command": "",
                    "evidence_file": "",
                    "evidence_sha256": "",
                    "locked_settings": [],
                    "surfaces": [],
                },
                "update_channel": {
                    "status": "failed",
                    "command": "",
                    "evidence_file": "",
                    "evidence_sha256": "",
                    "manifest_file": "../outside.json",
                    "manifest_sha256": "a" * 64,
                    "public_key": UPDATE_PUBLIC_KEY,
                    "channel": "stable",
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_professional_deployment_evidence(evidence, assets_dir=tmp_path)
    assert result.passed is False
    assert f"schema must be {customizer.MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA}" in result.errors
    assert "bundle_manifest.sha256s_present must be true" in result.errors
    assert "installer_branding.logo_applied must be true" in result.errors
    assert "policy_locks.locked_settings must be a non-empty list" in result.errors
    assert "policy_locks.surfaces must be an object" in result.errors
    assert "update_channel.signature_verified must be true" in result.errors
    assert any("manifest_file is invalid" in error for error in result.errors)


def test_deployment_evidence_validator_propagates_nested_manifest_errors(tmp_path: Path) -> None:
    nested_manifest = tmp_path / "nested.json"
    nested_manifest.write_text("{}", encoding="utf-8")
    evidence = tmp_path / "deployment.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": customizer.MOBA_PROFESSIONAL_DEPLOYMENT_EVIDENCE_SCHEMA,
                "release_target": "windows-x64",
                "brand_name": "Corp Ops",
                "version": "1.0.2",
                "bundle_manifest": {},
                "installer_branding": {},
                "policy_locks": {},
                "update_channel": {
                    "manifest_file": nested_manifest.name,
                    "manifest_sha256": _sha256(nested_manifest),
                    "public_key": UPDATE_PUBLIC_KEY,
                    "channel": "stable",
                },
            }
        ),
        encoding="utf-8",
    )
    result = validate_professional_deployment_evidence(evidence, assets_dir=tmp_path)
    assert any(error.startswith("update_channel.manifest:") for error in result.errors)


def test_update_manifest_validator_rejects_malformed_roots_and_artifacts(tmp_path: Path) -> None:
    missing = validate_professional_update_manifest(tmp_path / "missing.json", public_key=UPDATE_PUBLIC_KEY)
    assert "cannot be read" in missing.errors[0]

    invalid_json = tmp_path / "invalid-update.json"
    invalid_json.write_text("{", encoding="utf-8")
    invalid = validate_professional_update_manifest(invalid_json, public_key=UPDATE_PUBLIC_KEY)
    assert "not valid JSON" in invalid.errors[0]

    list_root = tmp_path / "list-update.json"
    list_root.write_text("[]", encoding="utf-8")
    root_result = validate_professional_update_manifest(list_root, public_key=UPDATE_PUBLIC_KEY)
    assert "root must be a JSON object" in root_result.errors[0]

    empty_artifacts = tmp_path / "empty-artifacts.json"
    empty_artifacts.write_text(
        json.dumps(
            {
                "schema": customizer.MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA,
                "channel": "stable",
                "organization": "Example Corp",
                "version": "1",
                "artifacts": {},
                "signature": {},
            }
        ),
        encoding="utf-8",
    )
    empty_result = validate_professional_update_manifest(
        empty_artifacts,
        public_key=UPDATE_PUBLIC_KEY,
    )
    assert "artifacts must be a non-empty list" in empty_result.errors

    malformed = tmp_path / "malformed-artifacts.json"
    malformed.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "channel": "actual",
                "organization": "Actual Org",
                "version": "1",
                "artifacts": [
                    1,
                    {
                        "target": "windows-x64",
                        "name": "same.exe",
                        "url": "",
                        "sha256": "a" * 64,
                        "size_bytes": -1,
                    },
                    {
                        "target": "windows-x64",
                        "name": "same.exe",
                        "url": "",
                        "sha256": "a" * 64,
                        "size_bytes": 0,
                    },
                ],
                "signature": {},
            }
        ),
        encoding="utf-8",
    )
    result = validate_professional_update_manifest(
        malformed,
        public_key=UPDATE_PUBLIC_KEY,
        expected_channel="expected",
        expected_organization="Expected Org",
    )
    assert f"schema must be {customizer.MOBA_PROFESSIONAL_UPDATE_MANIFEST_SCHEMA}" in result.errors
    assert "channel must match expected channel expected" in result.errors
    assert "organization must match expected organization Expected Org" in result.errors
    assert "artifacts[1] must be a JSON object" in result.errors
    assert "artifacts[2].size_bytes must be a non-negative integer" in result.errors
    assert "artifacts[3] duplicates target/name pair windows-x64/same.exe" in result.errors


def _write_evidence_asset(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_signed_update_manifest(root: Path, *, artifact: Path, public_key: str) -> Path:
    payload = {
        "schema": "row.moba-professional.update-manifest.v1",
        "channel": "stable",
        "organization": "Example Corp",
        "version": "1.0.2",
        "generated_at": "2026-06-19T00:00:00Z",
        "update_url": "https://updates.example.com/row/stable.json",
        "artifacts": [
            {
                "target": "windows-x64",
                "name": artifact.name,
                "url": f"https://updates.example.com/files/{artifact.name}",
                "sha256": _sha256(artifact),
                "size_bytes": artifact.stat().st_size,
                "file": artifact.name,
            }
        ],
    }
    canonical = canonical_update_manifest_payload(payload)
    assert public_key == UPDATE_PUBLIC_KEY
    payload["signature"] = {
        "algorithm": "ed25519",
        "key_id": "corp",
        "value": b64encode(_UPDATE_PRIVATE_KEY.sign(canonical)).decode("ascii"),
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    path = root / "stable-update.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
