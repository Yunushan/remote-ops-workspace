from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

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
        update_public_key="hmac-sha256:corp-secret",
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
            public_key="hmac-sha256:corp-secret",
        )
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("enterprise update channels must require HTTPS")


def test_moba_professional_update_manifest_accepts_signed_https_artifacts(tmp_path: Path) -> None:
    artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=artifact,
        public_key="hmac-sha256:corp-secret",
    )

    result = validate_professional_update_manifest(
        manifest,
        public_key="hmac-sha256:corp-secret",
        expected_channel="stable",
        expected_organization="Example Corp",
        assets_dir=tmp_path,
    )

    assert result.passed is True
    assert result.summary["signature_algorithm"] == "hmac-sha256"
    assert result.summary["artifact_count"] == 1


def test_moba_professional_update_manifest_rejects_tampered_signature(tmp_path: Path) -> None:
    artifact = _write_evidence_asset(tmp_path, "corp-ops-1.0.2-setup.exe", "installer")
    manifest = _write_signed_update_manifest(
        tmp_path,
        artifact=artifact,
        public_key="hmac-sha256:corp-secret",
    )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["artifacts"][0]["url"] = "http://updates.example.com/corp-ops-1.0.2-setup.exe"
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = validate_professional_update_manifest(
        manifest,
        public_key="hmac-sha256:corp-secret",
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
        public_key="hmac-sha256:corp-secret",
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
                    "public_key": "hmac-sha256:corp-secret",
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
        public_key="hmac-sha256:corp-secret",
    )
    deployment = build_professional_deployment_plan(
        brand_name="Corp Ops",
        organization="Example Corp",
        version="1.0.2",
        update_url="https://updates.example.com/row/stable.json",
        update_public_key="hmac-sha256:corp-secret",
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
        public_key="hmac-sha256:corp-secret",
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
                    "public_key": "hmac-sha256:corp-secret",
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
            "hmac-sha256:corp-secret",
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
            "hmac-sha256:corp-secret",
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
            "hmac-sha256:corp-secret",
            "--channel",
            "stable",
            "--json",
        ]
    )
    assert update.func.__name__ == "cmd_customizer_update_verify"


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
    secret = public_key.split(":", 1)[1]
    payload["signature"] = {
        "algorithm": "hmac-sha256",
        "key_id": "corp",
        "value": hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest(),
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
    }
    path = root / "stable-update.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
