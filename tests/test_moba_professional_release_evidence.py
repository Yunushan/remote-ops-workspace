from __future__ import annotations

import hashlib
import json
import struct
from base64 import b64encode
from types import SimpleNamespace

import pytest

from remote_ops_workspace.moba_customizer import (
    REQUIRED_POLICY_SURFACES,
    canonical_update_manifest_payload,
    validate_professional_deployment_evidence,
)
from scripts import check_moba_professional_deployment_evidence as gate
from scripts import check_release_mobaxterm_parity as published
from scripts import make_mobaxterm_parity_evidence_record as generator


@pytest.fixture
def professional_bundle(tmp_path):
    ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    key = ed25519.Ed25519PrivateKey.generate()
    public_key = "ed25519:" + b64encode(key.public_key().public_bytes_raw()).decode()
    root = tmp_path / "reviewed" / "professional-deployment"
    root.mkdir(parents=True)
    source_asset = tmp_path / "row-source.zip"
    source_asset.write_bytes(b"fixture source")
    source = {
        "repository": "example/row", "release_tag": "v1.0.28", "head_sha": "c" * 40,
        "workflow_run_url": "https://github.com/example/row/actions/runs/42", "run_attempt": 3,
    }
    identity = {
        "source": source,
        "release_asset": {"name": source_asset.name, "sha256": hashlib.sha256(source_asset.read_bytes()).hexdigest()},
    }

    def put(name, value):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        (root / name).write_bytes(data)
        return {"evidence_file": name, "evidence_sha256": hashlib.sha256(data).hexdigest()}

    brand, publisher, version = "Fixture", "Example Corp", "1.0.28"
    title = f"{brand} Remote Ops Workspace"
    deployment_id = "38F685FF-3B81-4386-999B-06AC5AE6155F"
    embedded_icon = b"fixture ICO image"
    logo = struct.pack("<HHHBBBBHHII", 0, 1, 1, 16, 16, 0, 0, 1, 32, len(embedded_icon), 22) + embedded_icon
    welcome = b"Hello from the deployment fixture.\n"
    pe = b"PE\0\0\x4c\x01\x01\0" + bytes(16)
    section = b".rsrc\0\0\0" + bytes(8) + struct.pack("<II", len(embedded_icon), 128) + bytes(16)
    exe = b"MZ" + bytes(58) + struct.pack("<I", 64) + pe + section + embedded_icon
    msi = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"fixture MSI payload"
    exe_name, msi_name = f"fixture-{version}-setup.exe", f"fixture-{version}.msi"
    artifacts = [
        {
            "name": name, "sha256": put(name, content)["evidence_sha256"], "size_bytes": len(content),
        }
        for name, content in ((exe_name, exe), (msi_name, msi))
    ]
    logo_ref, welcome_ref = put("logo.ico", logo), put("welcome.txt", welcome)
    bundle_manifest = {
        "schema_version": 1, "brand_name": brand, "organization": publisher, "project_version": version,
        "files": [
            {"path": name, "sha256": ref["evidence_sha256"], "size_bytes": len(data)}
            for name, ref, data in (("branding/logo.ico", logo_ref, logo), ("welcome.txt", welcome_ref, welcome))
        ],
    }
    build_manifest = {
        "deployment_id": deployment_id, "product_name": title, "publisher": publisher,
        "version": version, "architecture": "x64", "artifacts": artifacts,
        "icon_sha256": logo_ref["evidence_sha256"], "welcome_sha256": welcome_ref["evidence_sha256"],
    }
    msi_database = f"""
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="{title}" Manufacturer="{publisher}" Version="{version}" UpgradeCode="{{{deployment_id}}}">
    <Property Id="ARPPRODUCTICON" Value="RemoteOpsWorkspaceIcon" />
    <Icon Id="RemoteOpsWorkspaceIcon" />
    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLFOLDER" Name="Remote Ops Workspace {deployment_id}">
        <Directory Id="DOCSDIR"><Component Id="Docs"><File Id="WelcomeFile" Name="welcome.txt" /></Component></Directory>
      </Directory>
    </StandardDirectory>
  </Package>
</Wix>
""".encode()
    capture = {
        **identity, "schema": gate.INSTALLER_CAPTURE_SCHEMA, "logo": logo_ref, "welcome": welcome_ref,
        "installer_sha256": {row["name"]: row["sha256"] for row in artifacts},
        "exe_icon": put("exe-icon.bin", embedded_icon), "exe_icon_offset": 128,
        "exe_version": put("exe-version.json", {"ProductName": title, "CompanyName": publisher, "ProductVersion": version}),
        "msi_database": put("msi.wxs", msi_database), "msi_icon": put("msi-icon.ico", logo),
        "msi_welcome": put("msi-welcome.txt", welcome),
    }
    update = {
        "schema": "row.moba-professional.update-manifest.v1", "channel": "stable", "organization": publisher,
        "version": version, "update_url": "https://updates.example.com/channel.json",
        "artifacts": [
            {**row, "target": "windows-x64", "file": row["name"], "url": f"https://updates.example.com/{row['name']}"}
            for row in artifacts
        ],
    }
    envelope = {
        **identity, "schema": "row.moba-professional.deployment-evidence.v1", "release_target": "windows-x64",
        "brand_name": brand, "version": version,
        "policy_locks": {
            **put("policy.txt", b"fixture policy observations"), "status": "passed", "command": "review policy",
            "locked_settings": ["ssh.require_host_key"], "surfaces": dict.fromkeys(REQUIRED_POLICY_SURFACES, True),
        },
        "installer_branding": {
            "status": "passed", "command": "inspect Windows packages", "windows_exe_rebranded": True,
            "windows_msi_rebranded": True, "product_name_matches_brand": True, "logo_applied": True,
        },
        "update_channel": {
            **put("channel.txt", b"fixture channel observations"), "status": "passed", "command": "review signed manifest",
            "channel": "stable", "organization": publisher, "public_key": public_key, "https_update_url": True,
            "signature_verified": True, "organization_channel": True,
        },
    }

    def write_bundle():
        capture["build_manifest"] = put("build-manifest.json", build_manifest)
        proof = put("bundle-manifest.json", bundle_manifest)
        envelope["bundle_manifest"] = {
            **proof, "status": "passed", "command": "review bundle", "sha256s_present": True,
            "manifest_sha256": proof["evidence_sha256"],
        }
        canonical = canonical_update_manifest_payload(update)
        update["signature"] = {
            "algorithm": "ed25519", "value": b64encode(key.sign(canonical)).decode(),
            "payload_sha256": hashlib.sha256(canonical).hexdigest(),
        }
        signed = put("update.json", update)
        envelope["update_channel"].update(manifest_file=signed["evidence_file"], manifest_sha256=signed["evidence_sha256"])
        envelope["installer_branding"].update(put("installer-capture.json", capture))
        put("evidence.json", envelope)
        return root / "evidence.json"

    return SimpleNamespace(
        root=root, source_asset=source_asset, source=source, capture=capture, build=build_manifest,
        update=update, envelope=envelope, put=put, write_bundle=write_bundle,
    )


def test_candidate_and_published_audit_bind_exact_branded_installer_pair(professional_bundle):
    item = professional_bundle
    args = SimpleNamespace(
        article_id="professional-deployment", release_tag=item.source["release_tag"], release_target="windows-x64",
        evidence=item.write_bundle(), assets_dir=item.root,
        release_asset_url=["https://github.com/example/row/releases/download/v1.0.28/row-source.zip"],
        artifact=[f"{item.source_asset.name}={item.source_asset}"],
    )
    errors, candidate = generator.build_evidence_record(args)
    assert errors == []
    assert candidate["validation_summary"]["summary"]["verified_windows_installers"] == item.capture["installer_sha256"]
    published.verify_article_evidence(candidate, item.root.parent)
    item.source_asset.write_bytes(b"stale release source")
    errors, _ = generator.build_evidence_record(args)
    assert any("tested release asset must match" in error for error in errors)


@pytest.mark.parametrize(("mutation", "message"), [
    ("old-flags", "valid JSON"),
    ("wrong-workflow", "exact release source"),
    ("signed-without-msi", "must identify fixture-1.0.28.msi exactly once"),
    ("remote-only", "file path is invalid"),
    ("changed-msi", "evidence_sha256 does not match"),
    ("stale-capture", "both exact installer digests"),
    ("wrong-exe-icon", "icon resource must match"),
    ("wrong-exe-offset", "inside the exact EXE resource section"),
    ("wrong-msi-welcome", "welcome bytes must match"),
    ("stock-deployment", "must match the deployment"),
])
def test_professional_release_rejects_incomplete_branding_captures(professional_bundle, mutation, message):
    item = professional_bundle
    if mutation == "wrong-workflow":
        item.capture["source"] = {**item.source, "run_attempt": 4}
    if mutation == "signed-without-msi":
        item.update["artifacts"].pop()
    if mutation == "remote-only":
        item.update["artifacts"][0].pop("file")
    if mutation == "stale-capture":
        item.capture["installer_sha256"] = {}
    if mutation == "wrong-exe-icon":
        item.capture["exe_icon"] = item.put("exe-icon.bin", b"another resource")
    if mutation == "wrong-exe-offset":
        item.capture["exe_icon_offset"] = 0
    if mutation == "wrong-msi-welcome":
        item.capture["msi_welcome"] = item.put("msi-welcome.txt", b"another message")
    if mutation == "stock-deployment":
        item.build["deployment_id"] = "8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0"
    path = item.write_bundle()
    if mutation == "changed-msi":
        item.put("fixture-1.0.28.msi", b"another installer")
    if mutation == "old-flags":
        item.envelope["installer_branding"].update(item.put("unstructured.txt", b"Branding passed"))
        item.put(path.name, item.envelope)
        assert validate_professional_deployment_evidence(path).passed
    result = gate.validate_professional_release_evidence(path)
    assert not result.passed
    assert any(message in error for error in result.errors), result.errors
