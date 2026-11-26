#!/usr/bin/env python3
"""Sign the exact redistribution approval reviewed by an independent reviewer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from check_release_license_compliance import (
    check_review_window,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    read_json_object,
    verify_evidence_signature,
)
from release_review_key import load_review_key


def sign_approval(args: argparse.Namespace) -> Path:
    if args.approval.name != "release-evidence.json":
        raise ValueError("expected the reviewed release-evidence.json")
    policy_bytes, policy = read_json_object(args.policy, "release compliance policy")
    if policy.get("policy_status") != "approved" or policy.get("closed_world_inventory_approved") is not True:
        raise ValueError("the redistribution policy must be independently approved before signing")
    payload, approval = read_json_object(args.approval, "reviewed redistribution approval")
    expected = {
        "schema_version": 1,
        "decision": "approved",
        "repository": normalize_repository(args.repository),
        "release_tag": normalize_tag(args.tag),
        "release_sha": normalize_sha(args.sha),
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
    }
    for name, value in expected.items():
        if type(approval.get(name)) is not type(value) or approval[name] != value:
            raise ValueError(f"reviewed redistribution approval {name} does not match the requested release and policy")
    errors = check_review_window(approval, now=None)
    if errors:
        raise ValueError("\n".join(errors))
    key = load_review_key(args.private_key, role="reviewer")
    signature = {
        "schema_version": 1,
        "algorithm": "ed25519",
        "key_id": args.key_id,
        "signature": base64.b64encode(key.sign(payload)).decode("ascii"),
    }
    verify_evidence_signature(payload, signature, policy)
    output = args.approval.with_name("release-evidence.sig.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(signature, stream, indent=2)
        stream.write("\n")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    try:
        output = sign_approval(parser.parse_args(argv))
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        print(f"redistribution approval signing: {exc}", file=sys.stderr)
        return 1
    print(f"Verified detached redistribution signature at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
