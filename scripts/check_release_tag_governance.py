#!/usr/bin/env python3
"""Revalidate a short-lived signed tag-governance proof immediately before mutation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_release_license_compliance import (
    check_tag_governance_attestation,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    read_json_object,
    verify_tag_governance_signature,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--attestation", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    try:
        _, policy = read_json_object(args.policy, "release compliance policy")
        attestation_bytes, attestation = read_json_object(
            args.attestation,
            "tag governance attestation",
        )
        _, signature = read_json_object(args.signature, "tag governance signature")
        governance = policy.get("tag_governance_attestation")
        if not isinstance(governance, dict) or governance.get("state") != "enforced":
            raise ValueError("tag governance attestation policy is not enforced")
        verify_tag_governance_signature(attestation_bytes, signature, policy)
        errors = check_tag_governance_attestation(
            attestation,
            policy=policy,
            repository=normalize_repository(args.repository),
            tag=normalize_tag(args.tag),
            sha=normalize_sha(args.sha),
        )
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release tag governance: {exc}", file=sys.stderr)
        return 1
    print("release tag governance proof passed at mutation boundary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
