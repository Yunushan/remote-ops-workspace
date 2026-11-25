#!/usr/bin/env python3
"""Sign the exact redistribution approval reviewed by an independent reviewer."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import sys
import warnings
from pathlib import Path

from check_release_license_compliance import (
    check_review_window,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    read_json_object,
    verify_evidence_signature,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


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
    if args.private_key.is_symlink() or not args.private_key.is_file():
        raise ValueError("reviewer's private key must be a regular file")
    key_bytes = args.private_key.read_bytes()
    if key_bytes.lstrip().startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----"):
        if not sys.stdin.isatty():
            raise ValueError("open an interactive terminal to unlock the reviewer's key")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Reviewer key passphrase: ").encode("utf-8")
    else:
        password = None
    try:
        key = load_pem_private_key(key_bytes, password=password)
    except (ValueError, TypeError) as exc:
        raise ValueError("could not unlock an Ed25519 PKCS#8 PEM key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("the reviewer key must be Ed25519")
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
    except (OSError, ValueError, RuntimeError, TypeError, EOFError, getpass.GetPassWarning) as exc:
        print(f"redistribution approval signing: {exc}", file=sys.stderr)
        return 1
    print(f"Verified detached redistribution signature at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
