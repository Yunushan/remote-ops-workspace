from __future__ import annotations

import base64
import importlib
import json
from datetime import datetime, timedelta, timezone
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
        if endpoint == f"repos/{repository}/actions/runs/123/attempts/1":
            return {
                "id": 123, "run_attempt": 1, "status": "in_progress",
                "event": "workflow_dispatch", "head_branch": tag, "head_sha": sha,
                "path": f".github/workflows/release-promotion.yml@refs/tags/{tag}",
            }
        if endpoint == f"repos/{repository}/releases/77":
            return {"id": 77, "draft": True, "prerelease": False, "tag_name": tag, "target_commitish": sha}
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
        "--operation", "publish", "--run-id", "123", "--run-attempt", "1", "--draft-id", "77",
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
    assert evidence["promotion_transaction"] == {
        "operation": "publish", "run_id": 123, "run_attempt": 1, "draft_release_id": 77,
    }
    assert tag_reads == 2


def test_fetch_pins_both_files_to_the_same_git_commit(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    fetch = importlib.import_module("fetch_release_tag_governance")
    repository = "example/project"
    transaction = fetch.promotion_transaction(123, 1, "publish", 77)
    ref = fetch.proof_ref(transaction)
    commit = "a" * 40
    calls: list[str] = []
    files = {fetch.ATTESTATION: b"proof", fetch.SIGNATURE: b"signature"}

    def github(url: str, _token: str, *, api_version: str):
        calls.append(url)
        if "/git/ref/" in url:
            return {"ref": ref, "object": {"type": "commit", "sha": commit}}, {}
        name = url.split("/contents/")[1].split("?")[0]
        data = files[name]
        return {
            "type": "file", "path": name, "size": len(data),
            "encoding": "base64", "content": base64.b64encode(data).decode(),
        }, {}

    monkeypatch.setattr(fetch, "get_json", github)
    assert fetch.fetch_proof(repository, ref, "fixture-token") == (b"proof", b"signature")
    base = f"https://api.github.com/repos/{repository}"
    assert calls == [
        f"{base}/git/ref/heads/release-governance/123/1/publish",
        f"{base}/contents/{fetch.ATTESTATION}?ref={commit}",
        f"{base}/contents/{fetch.SIGNATURE}?ref={commit}",
    ]


def test_fetch_requires_exact_transaction_even_with_valid_auditor_signature(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    fetch = importlib.import_module("fetch_release_tag_governance")
    key = Ed25519PrivateKey.generate()
    policy = {"tag_governance_attestation": {
        "state": "enforced", "max_validity_seconds": 300, "trusted_ed25519_keys": [
            {"key_id": "auditor", "public_key": base64.b64encode(key.public_key().public_bytes_raw()).decode()},
        ],
    }}
    repository, tag, sha = "example/project", "v1.2.3", "a" * 40
    observed = datetime.now(timezone.utc)
    transaction = fetch.promotion_transaction(123, 1, "publish", 77)
    proof = json.dumps({
        "schema_version": 1, "decision": "approved", "source": "github-rulesets-api",
        "repository": repository, "release_tag": tag, "release_sha": sha,
        "tag_update_blocked": True, "tag_deletion_blocked": True,
        "bypass_actors": [], "ruleset_ids": [42],
        "auditor": {"kind": "github-app", "identity": "fixture"},
        "observed_at": observed.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "expires_at": (observed + timedelta(seconds=240)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "promotion_transaction": transaction,
    }).encode()
    signature = json.dumps({
        "schema_version": 1, "algorithm": "ed25519", "key_id": "auditor",
        "signature": base64.b64encode(key.sign(proof)).decode(),
    }).encode()

    fetch.verify_proof(proof, signature, policy, repository, tag, sha, transaction)
    with pytest.raises(ValueError, match="exact promotion transaction"):
        fetch.verify_proof(proof, signature, policy, repository, tag, sha, {**transaction, "draft_release_id": 78})
