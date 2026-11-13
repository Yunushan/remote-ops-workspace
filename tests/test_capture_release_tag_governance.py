from __future__ import annotations

import base64
import importlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from scripts.check_release_license_compliance import verify_tag_governance_signature


@pytest.mark.parametrize("scenario", ["approved", "hidden-bypass", "tag-moved", "untrusted-key"])
def test_capture_signs_only_live_protected_tag(
    tmp_path: Path, monkeypatch, scenario: str,
) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    capture = importlib.import_module("capture_release_tag_governance")
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    key = Ed25519PrivateKey.generate()
    enrolled = Ed25519PrivateKey.generate() if scenario == "untrusted-key" else key
    private_key = tmp_path / "auditor.pem"
    private_key.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    output = tmp_path / "proof"
    policy = {
        "tag_governance_attestation": {
            "state": "enforced",
            "max_validity_seconds": 300,
            "trusted_ed25519_keys": [{
                "key_id": "auditor-key",
                "public_key": base64.b64encode(enrolled.public_key().public_bytes_raw()).decode(),
            }],
        },
    }
    tag_reads = 0

    def gh(args: list[str], _label: str, _timeout: int) -> dict:
        nonlocal tag_reads
        endpoint = args[-1]
        if endpoint == f"repos/{repository}/git/ref/tags/{tag}":
            tag_reads += 1
            target = "b" * 40 if scenario == "tag-moved" and tag_reads == 2 else sha
            return {"object": {"type": "commit", "sha": target}}
        assert endpoint == f"repos/{repository}/contents/configs/release_compliance_policy.json?ref={sha}"
        return {
            "type": "file",
            "sha": "c" * 40,
            "encoding": "base64",
            "content": base64.b64encode(json.dumps(policy).encode()).decode(),
        }

    ruleset = {
        "id": 42,
        "target": "tag",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": [f"refs/tags/{tag}"], "exclude": []}},
        "rules": [{"type": "update"}, {"type": "deletion"}],
    }
    if scenario != "hidden-bypass":
        ruleset["bypass_actors"] = []
    monkeypatch.setenv("GH_TOKEN", "auditor-fixture")
    monkeypatch.setattr(capture, "run_gh_json", gh)
    monkeypatch.setattr(capture, "fetch_tag_rulesets", lambda _repo: {"rulesets": [ruleset]})
    args = [
        "--repository", repository, "--tag", tag, "--sha", sha,
        "--auditor-identity", "independent fixture", "--key-id", "auditor-key",
        "--private-key", str(private_key), "--out-dir", str(output),
    ]
    if scenario != "approved":
        assert capture.main(args) == 1
        assert not output.exists()
        return

    assert capture.main(args) == 0
    raw = (output / "tag-governance-attestation.json").read_bytes()
    signature = json.loads((output / "tag-governance-attestation.sig.json").read_bytes())
    verify_tag_governance_signature(raw, signature, policy)
    evidence = json.loads(raw)
    assert evidence["release_sha"] == sha
    assert evidence["ruleset_ids"] == [42]
    assert evidence["bypass_actors"] == []
    assert tag_reads == 2
