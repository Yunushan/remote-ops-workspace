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
from scripts import assemble_moba_professional_evidence as assembler
from scripts import capture_moba_professional_installers as native_capture
from scripts import capture_moba_professional_policy as policy_capture
from scripts import check_moba_professional_deployment_evidence as gate
from scripts import check_release_mobaxterm_parity as published
from scripts import isolated_linux_fixture, qt_release_capture
from scripts import make_mobaxterm_parity_evidence_record as generator


def test_policy_capture_rejects_modified_bundle_before_machine_installation(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    (bundle / "config").mkdir(parents=True)
    trusted = b'{"locked_settings":[{"key":"protocol","value":"ssh"}]}'
    (bundle / "config" / "policy.json").write_bytes(trusted.replace(b"ssh", b"rdp"))
    (bundle / "manifest.json").write_text(json.dumps({
        "project_version": "1.0.28",
        "files": [{"path": "config/policy.json", "size_bytes": len(trusted),
                   "sha256": hashlib.sha256(trusted).hexdigest()}],
    }), encoding="utf-8")
    monkeypatch.setattr(isolated_linux_fixture, "require_offline_container", lambda: None)
    monkeypatch.setattr(qt_release_capture, "verify_wheel", lambda wheel: ("v1.0.28", {"name": wheel.name}))

    def unexpected_provision(_policy):
        pytest.fail("a modified bundle reached machine policy installation")

    monkeypatch.setattr(policy_capture, "observe_policy", unexpected_provision)
    output = tmp_path / "review"
    with pytest.raises(ValueError, match="must match config/policy.json in the customizer manifest"):
        policy_capture.capture(tmp_path / "release.whl", bundle, output, local=True)
    assert not output.exists()


@pytest.mark.parametrize("damage", [None, "unreferenced", "outside-section"])
def test_native_capture_reads_only_linked_icon_resources(tmp_path, damage):
    image = b"qualification icon image"
    logo = struct.pack("<HHHBBBBHHII", 0, 1, 1, 16, 16, 0, 0, 1, 32, len(image), 22) + image
    pe, section, virtual = 64, 512, 0x1000
    optional = pe + 24
    section_header = optional + 224
    native = bytearray(1024)
    native[:2] = b"MZ"
    struct.pack_into("<I", native, 60, pe)
    struct.pack_into("<4sHHIIIHH", native, pe, b"PE\0\0", 0x14C, 1, 0, 0, 0, 224, 0)
    struct.pack_into("<H", native, optional, 0x10B)
    struct.pack_into("<I", native, optional + 92, 16)
    struct.pack_into("<II", native, optional + 96 + 16, virtual, 512)
    struct.pack_into("<8sIIII", native, section_header, b".rsrc\0\0\0", 512, virtual, 512, section)

    for relative, key, link in ((0, 3, 0x80000018), (24, 1, 0x80000030), (48, 1033, 72)):
        struct.pack_into("<HII", native, section + relative + 14, 1, key, link)
    payload = 256
    rva = virtual + (1024 if damage == "outside-section" else payload)
    struct.pack_into("<IIII", native, section + 72, rva, len(image), 0, 0)
    native[section + 128:section + 128 + len(image)] = image
    if damage != "unreferenced":
        native[section + payload:section + payload + len(image)] = image
    installer = tmp_path / "installer.exe"
    installer.write_bytes(native)

    if damage == "unreferenced":
        with pytest.raises(ValueError, match="no icon resource matching"):
            native_capture.find_icon(installer, logo)
    elif damage == "outside-section":
        with pytest.raises(ValueError, match="escape the supported resource range"):
            native_capture.find_icon(installer, logo)
    else:
        assert native_capture.find_icon(installer, logo) == (section + payload, image)


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
    locks = [{"key": "protocol", "value": "ssh"}]
    policy_data = json.dumps({"schema_version": 1, "locked_settings": locks}).encode()
    policy_file = put("enterprise-policy.json", policy_data)
    policy_digest = policy_file["evidence_sha256"]
    bundle_manifest = {
        "schema_version": 1, "brand_name": brand, "organization": publisher, "project_version": version,
        "files": [
            {"path": name, "sha256": ref["evidence_sha256"], "size_bytes": len(data)}
            for name, ref, data in (("branding/logo.ico", logo_ref, logo), ("welcome.txt", welcome_ref, welcome))
        ] + [{"path": "config/policy.json", "sha256": policy_digest, "size_bytes": len(policy_data)}],
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

    def denial(surface, action):
        return (
            f"enterprise policy blocked {surface} {action}: "
            f"{surface} cannot use locked enterprise setting protocol='telnet'; required 'ssh'"
        )

    writes = {
        "store_before": "1" * 64, "store_after_denial": "1" * 64,
        "store_after_allowance": "2" * 64, "saved_protocol": "ssh",
    }
    policy_capture = {
        **identity, "schema": gate.POLICY_CAPTURE_SCHEMA, "policy_document": policy_file,
        "installed_policy_sha256": policy_digest, "machine_policy_sha256": policy_digest,
        "machine_policy_write_refused": True, "machine_policy_unchanged": True,
        "portable_policy_writable": True, "gui_and_web_started_before_machine_install": True,
        "attempts": {"allowed_protocol": "ssh", "denied_protocol": "telnet"},
        "public_policy_before": {"status": 200, "body": {"active": False, "locked_settings": []}},
        "public_policy": {"status": 200, "body": {"active": True, "locked_settings": locks}},
        "gui_process": {"before": 14, "after": 14}, "web_process": {"before": 16, "after": 16},
        "web": {
            **writes, "denied": {"status": 400, "body": {"error": denial("web", "add")}},
            "allowed": {"status": 201, "body": {"protocol": "ssh"}},
        },
        "cli": {**writes, "denied": {"exit": 1, "stderr": denial("cli", "add")}, "allowed": {"exit": 0}},
        "profile-editor": {**writes, "denied": [denial("profile-editor", "add")]},
        "launcher": {
            "denied": denial("launcher", "launch"), "allowed_protocol": "ssh",
            "allowed_argv": ["ssh", "127.0.0.1"],
        },
    }
    for surface in ("gui", "quick-connect"):
        policy_capture[surface] = {
            "denied": [{"text": denial(surface, "launch")}],
            "tabs_before": 1, "tabs_after_denial": 1, "tabs_after_allowance": 2,
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
            "status": "passed", "command": "review policy",
            "locked_settings": locks, "surfaces": dict.fromkeys(REQUIRED_POLICY_SURFACES, True),
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
        envelope["policy_locks"].update(put("policy-capture.json", policy_capture))
        put("evidence.json", envelope)
        return root / "evidence.json"

    return SimpleNamespace(
        root=root, source_asset=source_asset, source=source, capture=capture, build=build_manifest,
        update=update, envelope=envelope, policy_capture=policy_capture, put=put, write_bundle=write_bundle,
    )


@pytest.mark.parametrize("failure", [
    None, "different-attempt", "different-bundle", "changed-artifact", "wrong-key", "missing-origin", "changed-delivery",
])
def test_assemble_professional_review_binds_captures_and_delivery(
    professional_bundle, tmp_path, monkeypatch, failure,
):
    item = professional_bundle
    wheel = tmp_path / "remote_ops_workspace-1.0.28-py3-none-any.whl"
    item.source_asset.rename(wheel)
    release_asset = {"name": wheel.name, "sha256": gate.sha256_file(wheel)}
    for capture in (item.capture, item.policy_capture):
        capture["release_asset"] = release_asset
    item.write_bundle()

    windows = item.root
    linux = tmp_path / "policy"
    linux.mkdir()
    for name in ("bundle-manifest.json", "policy-capture.json", "enterprise-policy.json"):
        (linux / name).write_bytes((windows / name).read_bytes())
    if failure == "different-bundle":
        with (linux / "bundle-manifest.json").open("ab") as stream:
            stream.write(b"\n")
    manifest_ref = item.envelope["bundle_manifest"]
    policy_manifest_ref = {**manifest_ref, "evidence_sha256": gate.sha256_file(linux / "bundle-manifest.json")}
    installer = {
        **{name: item.envelope[name] for name in (
            "source", "release_target", "brand_name", "version", "bundle_manifest", "installer_branding",
        )},
        "release_asset": release_asset,
        "update_manifest": {"evidence_file": "update.json", "evidence_sha256": gate.sha256_file(windows / "update.json")},
    }
    policy = {
        "source": {**item.source, **({"run_attempt": 2} if failure == "different-attempt" else {})},
        "release_asset": release_asset, "bundle_manifest": policy_manifest_ref, "policy_locks": item.envelope["policy_locks"],
    }
    item.put("installer-review.json", installer)
    (linux / "policy-review.json").write_text(json.dumps(policy), encoding="utf-8")
    urls = {item.update["update_url"]: windows / "update.json"}
    urls.update({row["url"]: windows / row["file"] for row in item.update["artifacts"]})
    if failure == "changed-artifact":
        (windows / item.update["artifacts"][0]["file"]).write_bytes(b"changed artifact")
    observed = []

    def responses(url, _settings, _deadline, _maximum, *, expected):
        observed.append(url)
        data = urls[url].read_bytes()
        if failure == "changed-delivery" and url.endswith(".msi"):
            data = b"!" + data[1:]
        assert len(data) == expected
        yield data

    monkeypatch.setattr(gate.update_channel, "_chunks", responses)
    output = tmp_path / "assembled"
    origins = [] if failure == "missing-origin" else ["https://updates.example.com"]
    public_key = item.envelope["update_channel"]["public_key"]
    if failure == "wrong-key":
        public_key = "ed25519:" + b64encode(bytes(32)).decode()
    failures = {
        "different-attempt": "same release wheel, tag and workflow attempt",
        "different-bundle": "same original customizer manifest",
        "changed-artifact": "signed update artifact SHA-256 differs",
        "wrong-key": "signature",
        "missing-origin": "at least one independently approved",
        "changed-delivery": "HTTPS delivery SHA-256 differs",
    }
    if failure:
        with pytest.raises(ValueError, match=failures[failure]):
            assembler.assemble(windows, linux, wheel, public_key, output, origins=origins)
        assert not output.exists()
        if failure != "changed-delivery":
            assert observed == []
        return

    evidence = assembler.assemble(windows, linux, wheel, public_key, output, origins=origins)
    assert evidence == output / "evidence.json"
    assert b"\r\n" not in evidence.read_bytes()
    assert observed[0] == item.update["update_url"] and set(observed) == set(urls)
    args = SimpleNamespace(
        article_id="professional-deployment", release_tag=item.source["release_tag"], release_target="windows-x64",
        evidence=evidence, assets_dir=output,
        release_asset_url=[f"https://github.com/example/row/releases/download/v1.0.28/{wheel.name}"],
        artifact=[f"{wheel.name}={wheel}"],
    )
    errors, candidate = generator.build_evidence_record(args)
    assert not errors
    summary = candidate["validation_summary"]["summary"]
    assert summary["verified_windows_installers"] == item.capture["installer_sha256"]
    assert summary["verified_policy_surfaces"] == sorted(REQUIRED_POLICY_SURFACES)
    assert not (output / "installer-review.json").exists()


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
    summary = candidate["validation_summary"]["summary"]
    assert summary["verified_windows_installers"] == item.capture["installer_sha256"]
    assert summary["verified_policy_surfaces"] == sorted(REQUIRED_POLICY_SURFACES)
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


@pytest.mark.parametrize(("mutation", "message"), [
    ("policy-flags-only", "valid JSON"),
    ("policy-wrong-source", "machine policy capture must bind the exact release source"),
    ("policy-wrong-file", "installed machine policy must match"),
    ("machine-writable", "must show protected policy"),
    ("web-restarted", "same web process"),
    ("web-allowed-denied-protocol", "HTTP 400 and 201"),
    ("editor-mutated-on-refusal", "profile-editor store must remain unchanged"),
    ("quick-connect-opened-denied-tab", "quick-connect must open one tab only"),
    ("launcher-vague-denial", "launcher denial must show the observed protocol lock"),
])
def test_release_gate_rejects_incomplete_policy_surface_observations(professional_bundle, mutation, message):
    item = professional_bundle
    capture = item.policy_capture
    if mutation == "policy-wrong-source":
        capture["source"] = {**item.source, "run_attempt": 4}
    if mutation == "policy-wrong-file":
        capture["machine_policy_sha256"] = "f" * 64
    if mutation == "machine-writable":
        capture["machine_policy_write_refused"] = False
    if mutation == "web-restarted":
        capture["web_process"]["after"] = 39
    if mutation == "web-allowed-denied-protocol":
        capture["web"]["denied"]["status"] = 201
    if mutation == "editor-mutated-on-refusal":
        capture["profile-editor"]["store_after_denial"] = "f" * 64
    if mutation == "quick-connect-opened-denied-tab":
        capture["quick-connect"]["tabs_after_denial"] = 2
    if mutation == "launcher-vague-denial":
        capture["launcher"]["denied"] = "blocked"
    path = item.write_bundle()
    if mutation == "policy-flags-only":
        item.envelope["policy_locks"].update(item.put("policy.txt", b"All policy surfaces passed"))
        item.put(path.name, item.envelope)
        assert validate_professional_deployment_evidence(path).passed
    result = gate.validate_professional_release_evidence(path)
    assert not result.passed
    assert any(message in error for error in result.errors), result.errors


@pytest.mark.parametrize(("mutation", "expected"), [
    ("", ""),
    ("different-installer", ".msi HTTPS delivery SHA-256 differs"),
    ("different-manifest", "signed manifest HTTPS delivery SHA-256 differs"),
    ("unsigned-review-edit", "reviewed deployment evidence SHA-256 differs"),
    ("unapproved-cdn", "URL must use an approved professional update origin"),
    ("missing-origins", "supply at least one independently approved"),
    ("local-published-origin", "requires a hosted HTTPS origin"),
])
def test_hosted_delivery_binds_all_reviewed_bytes_and_origin(professional_bundle, monkeypatch, mutation, expected):
    item = professional_bundle
    origins = ["https://updates.example.com"]
    if mutation == "missing-origins":
        origins = []
    if mutation == "local-published-origin":
        origins = ["https://127.0.0.1:1234"]
    if mutation == "unapproved-cdn":
        for row in item.update["artifacts"]:
            row["url"] = row["url"].replace("updates.", "cdn.")
    evidence = item.write_bundle()
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    if mutation == "unsigned-review-edit":
        evidence.write_bytes(evidence.read_bytes() + b"\n")
    manifest_url = item.update["update_url"]
    responses = {manifest_url: (item.root / "update.json").read_bytes()}
    responses.update({row["url"]: (item.root / row["file"]).read_bytes() for row in item.update["artifacts"]})
    if mutation == "different-installer":
        url = next(url for url in responses if url.endswith(".msi"))
        responses[url] = b"!" + responses[url][1:]
    if mutation == "different-manifest":
        responses[manifest_url] = b"!" + responses[manifest_url][1:]
    calls = []

    def chunks(url, settings, deadline, maximum, *, expected):
        calls.append(url)
        assert deadline > 0
        assert settings["allowed_origins"] == set(origins)
        assert maximum == expected == len(responses[url])
        yield responses[url][:6]
        yield responses[url][6:]

    monkeypatch.setattr(gate.update_channel, "_chunks", chunks)
    kwargs = {
        "assets_dir": item.root, "evidence_sha256": digest,
        "verified_installers": item.capture["installer_sha256"], "origins": origins, "published": True,
    }
    if expected:
        with pytest.raises(ValueError, match=expected):
            gate.verify_hosted_professional_update(evidence, **kwargs)
    else:
        gate.verify_hosted_professional_update(evidence, **kwargs)
        assert set(calls) == set(responses) and calls[0] == manifest_url
    if mutation in {"unapproved-cdn", "missing-origins", "local-published-origin", "unsigned-review-edit"}:
        assert calls == []
