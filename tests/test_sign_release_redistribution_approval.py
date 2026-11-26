from __future__ import annotations

import base64
import hashlib
import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from scripts.check_release_license_compliance import verify_evidence_signature


@pytest.mark.parametrize(
    ("scenario", "error"),
    [
        ("encrypted", ""), ("unencrypted", ""), ("unenrolled", "signature is invalid"),
        ("expired", "approval has expired"), ("foreign-release", "release_sha"),
        ("wrong-policy", "policy_sha256"), ("blocked-policy", "must be independently approved"),
        ("noninteractive", "open an interactive terminal"), ("bad-passphrase", "could not unlock"),
        ("existing-output", "File exists"),
    ],
)
def test_signer_preserves_exact_reviewed_bytes_and_fails_closed(tmp_path, monkeypatch, capsys, scenario, error):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    signer = importlib.import_module("sign_release_redistribution_approval")
    key_loader = importlib.import_module("release_review_key")
    key = Ed25519PrivateKey.generate()
    enrolled = Ed25519PrivateKey.generate() if scenario == "unenrolled" else key
    policy = {
        "policy_status": "blocked-pending-independent-review" if scenario == "blocked-policy" else "approved",
        "closed_world_inventory_approved": True,
        "trusted_ed25519_keys": [{
            "key_id": "test-reviewer",
            "public_key": base64.b64encode(enrolled.public_key().public_bytes_raw()).decode("ascii"),
        }],
    }
    policy_path = tmp_path / "release_compliance_policy.json"
    policy_path.write_bytes(json.dumps(policy).encode())
    now = datetime.now(timezone.utc)
    approval = {
        "schema_version": 1,
        "decision": "approved",
        "repository": "example/project",
        "release_tag": "v1.2.3",
        "release_sha": "b" * 40 if scenario == "foreign-release" else "a" * 40,
        "policy_sha256": "b" * 64 if scenario == "wrong-policy" else hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "reviewed_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(minutes=-1 if scenario == "expired" else 5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    approval_path = tmp_path / "release-evidence.json"
    payload = (json.dumps(approval, indent=4).replace("\n", "\r\n") + "\r\n").encode()
    approval_path.write_bytes(payload)
    signature_path = tmp_path / "release-evidence.sig.json"
    if scenario == "existing-output":
        signature_path.write_bytes(b"original signature")
    private_key = tmp_path / "reviewer.pem"
    encryption = (BestAvailableEncryption(b"disposable passphrase")
                  if scenario in {"encrypted", "noninteractive", "bad-passphrase"} else NoEncryption())
    private_key.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, encryption))
    monkeypatch.setattr(key_loader.sys.stdin, "isatty", lambda: scenario != "noninteractive")
    monkeypatch.setattr(key_loader.getpass, "getpass", lambda _: "wrong" if scenario == "bad-passphrase" else "disposable passphrase")
    arguments = [
        "--repository", "example/project", "--tag", "v1.2.3", "--sha", "a" * 40,
        "--policy", str(policy_path), "--approval", str(approval_path),
        "--key-id", "test-reviewer", "--private-key", str(private_key),
    ]
    assert signer.main(arguments) == bool(error)
    assert approval_path.read_bytes() == payload
    if error:
        assert error.lower() in capsys.readouterr().err.lower()
        if scenario == "existing-output":
            assert signature_path.read_bytes() == b"original signature"
        else:
            assert not signature_path.exists()
    else:
        signature = json.loads(signature_path.read_bytes())
        verify_evidence_signature(payload, signature, policy)
        with pytest.raises(ValueError, match="signature is invalid"):
            verify_evidence_signature(payload.replace(b"\r\n", b"\n"), signature, policy)
