#!/usr/bin/env python3
"""Retrieve a fresh, independently signed proof for one promotion operation."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

from check_release_license_compliance import (
    check_tag_governance_attestation,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    read_json_object,
    strict_b64,
    verify_tag_governance_signature,
)
from check_release_remote_preconditions import get_json, require_token

ATTESTATION = "tag-governance-attestation.json"
SIGNATURE = "tag-governance-attestation.sig.json"
API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
MAX_PROOF_BYTES = 64 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--draft-id", type=int)
    parser.add_argument("--operation", choices=("create-draft", "publish"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        transaction = promotion_transaction(args.run_id, args.run_attempt, args.operation, args.draft_id)
        repository = normalize_repository(args.repository)
        tag = normalize_tag(args.tag)
        sha = normalize_sha(args.sha)
        _, policy = read_json_object(args.policy, "release compliance policy")
        governance = policy.get("tag_governance_attestation")
        if not isinstance(governance, dict) or governance.get("state") != "enforced":
            raise ValueError("tag governance attestation policy is not enforced")
        ref = proof_ref(transaction)
        if args.draft_id is not None:
            print(f"Numeric draft release ID: {args.draft_id}", flush=True)
        print(f"Waiting for independent tag governance proof on {ref}", flush=True)
        attestation, signature = fetch_proof(repository, ref, require_token("GITHUB_TOKEN"))
        verify_proof(attestation, signature, policy, repository, tag, sha, transaction)
        args.out_dir.mkdir(mode=0o700)
        for name, raw in ((ATTESTATION, attestation), (SIGNATURE, signature)):
            with (args.out_dir / name).open("xb") as handle:
                handle.write(raw)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"release governance refresh: {exc}", file=sys.stderr)
        return 1
    print(f"Independent tag governance proof verified for {args.operation}")
    return 0


def promotion_transaction(
    run_id: int | None, attempt: int | None, operation: str | None, draft_id: int | None,
) -> dict[str, Any]:
    if type(run_id) is not int or run_id < 1 or type(attempt) is not int or attempt < 1:
        raise ValueError("promotion run ID and attempt must be positive integers")
    if operation == "publish":
        if type(draft_id) is not int or draft_id < 1:
            raise ValueError("publication proof must bind a positive draft release ID")
    elif operation != "create-draft" or draft_id is not None:
        raise ValueError("draft creation proof must bind the create-draft operation without a release ID")
    return {"run_id": run_id, "run_attempt": attempt, "operation": operation, "draft_release_id": draft_id}


def proof_ref(transaction: dict[str, Any]) -> str:
    return f"refs/heads/release-governance/{transaction['run_id']}/{transaction['run_attempt']}/{transaction['operation']}"


def require_transaction(attestation: dict[str, Any], expected_transaction: dict[str, Any]) -> None:
    transaction = attestation.get("promotion_transaction")
    if not isinstance(transaction, dict) or set(transaction) != set(expected_transaction) or any(
        type(transaction[name]) is not type(expected) or transaction[name] != expected
        for name, expected in expected_transaction.items()
    ):
        raise ValueError("governance proof must bind the exact promotion transaction")


def fetch_proof(repository: str, ref: str, token: str) -> tuple[bytes, bytes]:
    base = f"{API_ROOT}/repos/{repository}"
    ref_url = f"{base}/git/ref/{ref.removeprefix('refs/')}"
    deadline = time.monotonic() + 900
    while True:
        try:
            payload, _ = get_json(ref_url, token, api_version=API_VERSION)
            break
        except RuntimeError as exc:
            if not isinstance(exc.__cause__, HTTPError) or exc.__cause__.code != 404:
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("independent auditor proof did not arrive within 15 minutes") from exc
            time.sleep(min(10, remaining))
    if not isinstance(payload, dict) or payload.get("ref") != ref:
        raise ValueError("governance proof ref response must match the exact requested ref")
    target = payload.get("object")
    commit = target.get("sha") if isinstance(target, dict) and target.get("type") == "commit" else None
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("governance proof ref must point to a commit")
    return fetch_file(base, commit, ATTESTATION, token), fetch_file(base, commit, SIGNATURE, token)


def fetch_file(base: str, commit: str, name: str, token: str) -> bytes:
    payload, _ = get_json(f"{base}/contents/{name}?ref={commit}", token, api_version=API_VERSION)
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "file"
        or payload.get("path") != name
        or payload.get("encoding") != "base64"
        or type(payload.get("size")) is not int
        or not 0 < payload["size"] <= MAX_PROOF_BYTES
        or not isinstance(payload.get("content"), str)
    ):
        raise ValueError(f"governance proof file is invalid: {name}")
    encoded = "".join(payload["content"].split())
    if len(encoded) > ((MAX_PROOF_BYTES + 2) // 3) * 4:
        raise ValueError(f"governance proof exceeds the size limit: {name}")
    raw = strict_b64(encoded, name)
    if len(raw) != payload["size"]:
        raise ValueError(f"governance proof size differs from its metadata: {name}")
    return raw


def verify_proof(
    attestation_bytes: bytes,
    signature_bytes: bytes,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    sha: str,
    expected_transaction: dict[str, Any],
) -> None:
    attestation = json.loads(attestation_bytes)
    signature = json.loads(signature_bytes)
    if not isinstance(attestation, dict) or not isinstance(signature, dict):
        raise ValueError("governance attestation and signature must be JSON objects")
    verify_tag_governance_signature(attestation_bytes, signature, policy)
    require_transaction(attestation, expected_transaction)
    errors = check_tag_governance_attestation(attestation, policy=policy, repository=repository, tag=tag, sha=sha)
    if errors:
        raise ValueError("; ".join(errors))


if __name__ == "__main__":
    raise SystemExit(main())
