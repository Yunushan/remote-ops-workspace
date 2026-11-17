#!/usr/bin/env python3
"""Revalidate a short-lived signed tag-governance proof immediately before mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from check_release_license_compliance import (
    check_review_window,
    check_tag_governance_attestation,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    read_json_object,
    verify_evidence_signature,
    verify_tag_governance_signature,
)
from fetch_release_tag_governance import promotion_transaction, require_transaction


def recheck_redistribution_approval(
    evidence_path: Path,
    signature_path: Path,
    policy_bytes: bytes,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    sha: str,
    *,
    now: datetime | None = None,
) -> list[str]:
    evidence_bytes, evidence = read_json_object(evidence_path, "release compliance evidence")
    _, signature = read_json_object(signature_path, "release compliance signature")
    return check_redistribution_approval(
        evidence_bytes, evidence, signature, policy_bytes, policy, repository, tag, sha, now=now,
    )


def check_redistribution_approval(
    evidence_bytes: bytes,
    evidence: dict[str, Any],
    signature: dict[str, Any],
    policy_bytes: bytes,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    sha: str,
    *,
    now: datetime | None,
) -> list[str]:
    verify_evidence_signature(evidence_bytes, signature, policy)
    expected = {
        "schema_version": 1,
        "decision": "approved",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
    }
    errors = [
        f"release compliance approval {key} does not match this transaction"
        for key, value in expected.items()
        if evidence.get(key) != value
    ]
    return errors + check_review_window(evidence, now=now)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--operation", choices=("create-draft", "publish"))
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--run-attempt", type=int)
    parser.add_argument("--draft-id", type=int)
    parser.add_argument("--redistribution-evidence", type=Path)
    parser.add_argument("--redistribution-signature", type=Path)
    args = parser.parse_args(argv)
    try:
        policy_bytes, policy = read_json_object(args.policy, "release compliance policy")
        repository = normalize_repository(args.repository)
        tag = normalize_tag(args.tag)
        sha = normalize_sha(args.sha)
        attestation_bytes, attestation = read_json_object(
            args.attestation,
            "tag governance attestation",
        )
        _, signature = read_json_object(args.signature, "tag governance signature")
        governance = policy.get("tag_governance_attestation")
        if not isinstance(governance, dict) or governance.get("state") != "enforced":
            raise ValueError("tag governance attestation policy is not enforced")
        verify_tag_governance_signature(attestation_bytes, signature, policy)
        transaction = any(value is not None for value in (args.operation, args.run_id, args.run_attempt, args.draft_id))
        if transaction:
            require_transaction(
                attestation,
                promotion_transaction(args.run_id, args.run_attempt, args.operation, args.draft_id),
            )
        evidence_args = (args.redistribution_evidence, args.redistribution_signature)
        if (transaction or any(path is not None for path in evidence_args)) and None in evidence_args:
            raise ValueError("release mutation requires both signed redistribution approval inputs")
        errors = []
        if args.redistribution_evidence is not None and args.redistribution_signature is not None:
            errors.extend(recheck_redistribution_approval(
                args.redistribution_evidence, args.redistribution_signature,
                policy_bytes, policy, repository, tag, sha,
            ))
        errors.extend(check_tag_governance_attestation(
            attestation, policy=policy, repository=repository, tag=tag, sha=sha,
        ))
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release tag governance: {exc}", file=sys.stderr)
        return 1
    print("release tag governance proof passed at mutation boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
