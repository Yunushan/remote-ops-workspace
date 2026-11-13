#!/usr/bin/env python3
"""Capture and sign live tag protection on the independent auditor's host."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from check_platform_evidence_source_ref import fetch_tagged_file, resolve_tag_commit
from check_release_license_compliance import (
    check_tag_governance_attestation,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    verify_tag_governance_signature,
)
from check_release_provenance import run_gh_json
from check_repository_governance import fetch_tag_rulesets, protected_tag_ruleset_ids
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from fetch_release_tag_governance import promotion_transaction, proof_ref


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--auditor-identity", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--operation", choices=("create-draft", "publish"))
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--draft-id", type=int)
    args = parser.parse_args(argv)
    try:
        capture(args)
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"tag governance capture: {exc}", file=sys.stderr)
        return 1
    print(f"Signed tag governance proof saved in {args.out_dir}")
    return 0


def capture(args: argparse.Namespace) -> None:
    repository = normalize_repository(args.repository)
    tag = normalize_tag(args.tag)
    sha = normalize_sha(args.sha)
    if not args.auditor_identity or args.auditor_identity != args.auditor_identity.strip():
        raise ValueError("auditor identity must be non-empty without surrounding whitespace")
    if not args.auditor_identity.isprintable():
        raise ValueError("auditor identity must contain only printable characters")
    if not os.environ.get("GH_TOKEN"):
        raise ValueError("GH_TOKEN is required for the independent auditor's GitHub access")
    transaction = None
    if any(value is not None for value in (args.operation, args.run_id, args.run_attempt, args.draft_id)):
        transaction = promotion_transaction(args.run_id, args.run_attempt, args.operation, args.draft_id)

    def fetch(endpoint: str) -> dict[str, Any]:
        data = run_gh_json(
            ["api", "--hostname", "github.com", f"repos/{repository}/{endpoint}"],
            "auditor GitHub input",
            30,
        )
        if not isinstance(data, dict):
            raise ValueError("auditor GitHub input must be a JSON object")
        return data

    def require_tag() -> None:
        observed_sha, errors = resolve_tag_commit(fetch, tag)
        if errors:
            raise ValueError("; ".join(errors))
        if observed_sha != sha:
            raise ValueError("live release tag does not point to the requested commit")

    require_tag()
    if transaction is not None:
        run = fetch(f"actions/runs/{transaction['run_id']}/attempts/{transaction['run_attempt']}")
        if (
            run.get("id") != transaction["run_id"]
            or run.get("run_attempt") != transaction["run_attempt"]
            or run.get("status") != "in_progress"
            or run.get("event") != "workflow_dispatch"
            or run.get("head_branch") != tag
            or run.get("head_sha") != sha
            or run.get("path") not in {
                ".github/workflows/release-promotion.yml",
                f".github/workflows/release-promotion.yml@refs/tags/{tag}",
                f".github/workflows/release-promotion.yml@{tag}",
            }
        ):
            raise ValueError("auditor proof requires the live exact-tag promotion run attempt")
        if args.operation == "publish":
            draft = fetch(f"releases/{args.draft_id}")
            if (
                draft.get("id") != args.draft_id
                or draft.get("draft") is not True
                or draft.get("prerelease") is not False
                or draft.get("tag_name") != tag
                or draft.get("target_commitish") != sha
            ):
                raise ValueError("auditor publication proof requires the exact unpublished draft")
    policy_text, errors = fetch_tagged_file(fetch, sha, "configs/release_compliance_policy.json")
    if errors or policy_text is None:
        raise ValueError("; ".join(errors) or "exact release policy is missing")
    policy = json.loads(policy_text)
    governance = policy.get("tag_governance_attestation") if isinstance(policy, dict) else None
    if not isinstance(governance, dict) or governance.get("state") != "enforced":
        raise ValueError("tag governance policy at the exact commit must be enforced")
    lifetime = governance.get("max_validity_seconds")
    if type(lifetime) is not int or not 60 <= lifetime <= 900:
        raise ValueError("tag governance policy has an invalid proof lifetime")
    if args.private_key.is_symlink() or not args.private_key.is_file():
        raise ValueError("auditor private key must be a regular file")
    key = load_pem_private_key(args.private_key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("auditor private key must be Ed25519")
    observed = datetime.now(timezone.utc).replace(microsecond=0)
    ids, errors = protected_tag_ruleset_ids(fetch_tag_rulesets(repository), tag)
    if errors:
        raise ValueError("; ".join(errors))
    require_tag()

    payload: dict[str, Any] = {
        "schema_version": 1,
        "decision": "approved",
        "source": "github-rulesets-api",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "tag_update_blocked": True,
        "tag_deletion_blocked": True,
        "bypass_actors": [],
        "ruleset_ids": ids,
        "auditor": {"kind": "independent-automation", "identity": args.auditor_identity},
        "observed_at": utc_text(observed),
        "expires_at": utc_text(observed + timedelta(seconds=lifetime)),
    }
    if transaction is not None:
        payload["promotion_transaction"] = transaction
    errors = check_tag_governance_attestation(payload, policy=policy, repository=repository, tag=tag, sha=sha)
    if errors:
        raise ValueError("; ".join(errors))
    encoded = json_bytes(payload)
    signature = {
        "schema_version": 1,
        "algorithm": "ed25519",
        "key_id": args.key_id,
        "signature": base64.b64encode(key.sign(encoded)).decode("ascii"),
    }
    verify_tag_governance_signature(encoded, signature, policy)
    args.out_dir.mkdir()
    for name, data in (
        ("tag-governance-attestation.json", encoded),
        ("tag-governance-attestation.sig.json", json_bytes(signature)),
    ):
        with (args.out_dir / name).open("xb") as output:
            output.write(data)
    if transaction is not None:
        print(f"Proof ref: {proof_ref(transaction)}")


def utc_text(timestamp: datetime) -> str:
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
