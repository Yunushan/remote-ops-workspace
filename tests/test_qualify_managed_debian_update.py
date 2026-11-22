from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import qualify_managed_debian_update as drill


@pytest.mark.parametrize(("target", "architecture", "machine", "native"), [
    ("linux-x86_64", "amd64", "x86_64", True),
    ("linux-arm64", "arm64", "aarch64", True),
    ("linux-arm64", "amd64", "x86_64", False),
    ("linux-arm64", "arm64", "x86_64", False),
    ("linux-arm64", "amd64", "aarch64", False),
    ("linux-x86_64", "arm64", "aarch64", False),
])
def test_native_container_checks_target_before_installed_package(tmp_path, monkeypatch, target, architecture, machine, native):
    (tmp_path / ".dockerenv").touch()
    (tmp_path / "sys/class/net/lo").mkdir(parents=True)
    monkeypatch.setattr(drill, "Path", lambda path: tmp_path / path.lstrip("/"))
    monkeypatch.setattr(drill.sys, "platform", "linux")
    monkeypatch.setattr(drill.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(drill.platform, "machine", lambda: machine)

    def dpkg(*args):
        assert args == ("/usr/bin/dpkg", "--print-architecture")
        return architecture

    def query(*args):
        assert native and args == ("/usr/bin/dpkg-query", "--show", drill.PACKAGE)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(drill, "checked", dpkg)
    monkeypatch.setattr(drill, "command", query)
    if native:
        assert drill.validate_container(target) == (architecture, machine)
    else:
        with pytest.raises(RuntimeError, match="requires a native"):
            drill.validate_container(target)


@pytest.mark.parametrize(("architecture", "filename_arch", "control_arch", "matches"), [
    ("amd64", "amd64", "amd64", True),
    ("arm64", "arm64", "arm64", True),
    ("arm64", "amd64", "arm64", False),
    ("arm64", "arm64", "amd64", False),
    ("amd64", "amd64", "arm64", False),
])
def test_installer_name_control_and_digest_must_match_target(
    tmp_path, monkeypatch, architecture, filename_arch, control_arch, matches,
):
    name = tmp_path / f"{drill.PACKAGE}-v1.0.24-linux-{filename_arch}.deb"
    name.write_bytes(b"pinned fixture")
    monkeypatch.setattr(drill, "checked", lambda *_: f"{drill.PACKAGE}\t1.0.24\t{control_arch}")
    digest = hashlib.sha256(name.read_bytes()).hexdigest()
    if matches:
        assert drill.validate_deb(name, digest, architecture) == "1.0.24"
    else:
        with pytest.raises(ValueError, match="package identity"):
            drill.validate_deb(name, digest, architecture)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        drill.validate_deb(name, "0" * 64, architecture)


@pytest.mark.parametrize(("arguments", "architecture", "target"), [
    ({}, "amd64", "linux-x86_64"), ({"target": "linux-arm64"}, "arm64", "linux-arm64"),
])
def test_signed_stage_manifest_and_trust_policy_bind_the_release_target(tmp_path, arguments, architecture, target):
    package = tmp_path / f"{drill.PACKAGE}-v1.0.24-linux-{architecture}.deb"
    package.write_bytes(b"qualified package")
    signer = Ed25519PrivateKey.generate()
    payloads = {}
    policy_path, _ = drill.stage_policy(
        tmp_path, "previous", package, "1.0.24", "1.0.24", origin="https://localhost:8765",
        now=datetime.now(timezone.utc), signer=signer, payloads=payloads, **arguments,
    )
    policy = json.loads(policy_path.read_bytes())
    manifest = json.loads(payloads["/previous/manifest.json"])
    signer.public_key().verify(base64.b64decode(manifest["signature"]["value"]), drill.canonical_update_manifest_payload(manifest))
    assert policy["selected_target"] == target and policy["approved_targets"] == [target]
    assert manifest["artifacts"][0]["target"] == target
    assert payloads[f"/previous/{package.name}"] == package.read_bytes()
