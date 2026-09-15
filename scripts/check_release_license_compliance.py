#!/usr/bin/env python3
"""Fail-closed audit for native third-party redistribution evidence.

This is an evidence verifier, not a legal opinion.  It deliberately rejects the
repository's initial blocked policy until an independent compliance authority
enrolls a real Ed25519 key and approves a closed-world policy.  A signed evidence
payload must bind exact release manifests and their artifact hashes, a fully
hashed realized dependency inventory, packaged license-file scans, and the
selected PyQt/Qt distribution channel.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs" / "release_compliance_policy.json"
TOOLCHAIN_PATH = ROOT / "configs" / "release_toolchain.json"
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
PROMOTION_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release-promotion.yml"
EXTENDED_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "extended-platform-evidence.yml"
XP_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "xp-native-evidence.yml"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
VERSION_RE = re.compile(r"\d+(?:\.\d+)+(?:[A-Za-z0-9_.+-]*)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        policy_bytes, policy = read_json_object(args.policy, "release compliance policy")
        _, toolchain = read_json_object(TOOLCHAIN_PATH, "release toolchain")
        _, matrix = read_json_object(MATRIX_PATH, "release matrix")
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        promotion_workflow = PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
        extended_workflow = EXTENDED_WORKFLOW_PATH.read_text(encoding="utf-8")
        xp_workflow = XP_WORKFLOW_PATH.read_text(encoding="utf-8")
        policy_root = args.policy_root or (
            args.policy.parent.parent
            if args.policy.parent.name == "configs"
            else args.policy.parent
        )
        errors = check_policy(
            policy,
            toolchain,
            policy_root=policy_root,
            workflow=workflow,
            promotion_workflow=promotion_workflow,
            extended_workflow=extended_workflow,
            xp_workflow=xp_workflow,
        )
        if errors:
            raise RuntimeError("; ".join(errors))
        if args.check_policy_only:
            print(
                "release license compliance policy passed: approved closed-world policy, "
                "fully hashed platform locks, and mandatory workflow enforcement are present"
            )
            return 0
        missing = [
            flag
            for flag, value in {
                "--assets-dir": args.assets_dir,
                "--repository": args.repository,
                "--tag": args.tag,
                "--sha": args.sha,
                "--evidence": args.evidence,
                "--signature": args.signature,
                "--protected-platform-registry": args.protected_platform_registry,
                "--candidate-inventory": args.candidate_inventory,
                "--tag-governance-attestation": args.tag_governance_attestation,
                "--tag-governance-signature": args.tag_governance_signature,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(f"full compliance audit requires: {', '.join(missing)}")
        repository = normalize_repository(args.repository)
        tag = normalize_tag(args.tag)
        sha = normalize_sha(args.sha)
        assert args.evidence is not None
        assert args.signature is not None
        assert args.assets_dir is not None
        assert args.protected_platform_registry is not None
        assert args.candidate_inventory is not None
        assert args.tag_governance_attestation is not None
        assert args.tag_governance_signature is not None
        evidence_bytes, evidence = read_json_object(args.evidence, "release compliance evidence")
        _, signature = read_json_object(args.signature, "release compliance signature")
        verify_evidence_signature(evidence_bytes, signature, policy)
        governance_bytes, governance = read_json_object(
            args.tag_governance_attestation,
            "tag governance attestation",
        )
        _, governance_signature = read_json_object(
            args.tag_governance_signature,
            "tag governance signature",
        )
        verify_tag_governance_signature(
            governance_bytes,
            governance_signature,
            policy,
        )
        evidence_root = args.evidence_root or args.evidence.parent
        errors = check_evidence(
            evidence,
            policy=policy,
            policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
            policy_root=policy_root,
            toolchain=toolchain,
            matrix=matrix,
            assets_dir=args.assets_dir,
            evidence_root=evidence_root,
            protected_platform_registry=args.protected_platform_registry,
            candidate_inventory=args.candidate_inventory,
            repository=repository,
            tag=tag,
            sha=sha,
        )
        errors.extend(
            check_tag_governance_attestation(
                governance,
                policy=policy,
                repository=repository,
                tag=tag,
                sha=sha,
            )
        )
        if errors:
            raise RuntimeError("; ".join(dict.fromkeys(errors)))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release license compliance: {exc}", file=sys.stderr)
        return 1
    print(
        "release license compliance passed: independently signed closed-world "
        "runtime and redistribution evidence matches exact native release bytes"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-policy-only", action="store_true")
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--tag")
    parser.add_argument("--sha")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--protected-platform-registry", type=Path)
    parser.add_argument("--candidate-inventory", type=Path)
    parser.add_argument("--tag-governance-attestation", type=Path)
    parser.add_argument("--tag-governance-signature", type=Path)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="root containing resolver locks, extracted license files, and review records",
    )
    parser.add_argument("--policy", type=Path, default=POLICY_PATH)
    parser.add_argument("--policy-root", type=Path)
    return parser.parse_args(argv)


def normalize_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise ValueError("repository must be owner/name")
    return repository


def normalize_tag(value: str) -> str:
    tag = value.strip()
    if TAG_RE.fullmatch(tag) is None:
        raise ValueError("tag must look like vX.Y.Z")
    return tag


def normalize_sha(value: str) -> str:
    sha = value.strip().lower()
    if COMMIT_RE.fullmatch(sha) is None:
        raise ValueError("sha must be a full 40-character hexadecimal commit id")
    return sha


def read_json_object(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"{label} must not be empty: {path}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return raw, value


def check_policy(
    policy: dict[str, Any],
    toolchain: dict[str, Any],
    *,
    policy_root: Path = ROOT,
    workflow: str | None = None,
    promotion_workflow: str | None = None,
    extended_workflow: str | None = None,
    xp_workflow: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if policy.get("schema_version") != 1:
        errors.append("release compliance policy schema_version must be 1")
    if policy.get("policy_status") != "approved":
        errors.append(
            "release compliance policy is not independently approved "
            f"(status={policy.get('policy_status')!r})"
        )
    if policy.get("closed_world_inventory_approved") is not True:
        errors.append("release compliance policy has no approved closed-world inventory")
    profiles = policy.get("required_profiles")
    if not isinstance(profiles, dict):
        errors.append("release compliance policy required_profiles must be an object")
    else:
        for profile in ("minimal-cli", "secure-cli", "gui-secure"):
            names = profiles.get(profile)
            if not isinstance(names, list) or not names or not all(
                isinstance(name, str) and name for name in names
            ):
                errors.append(f"release compliance policy profile {profile!r} is incomplete")
    keys = policy.get("trusted_ed25519_keys")
    if not isinstance(keys, list) or not keys:
        errors.append("release compliance policy has no trusted Ed25519 approver key")
    else:
        seen: set[str] = set()
        for index, item in enumerate(keys):
            label = f"trusted_ed25519_keys[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            key_id = item.get("key_id")
            if not isinstance(key_id, str) or not key_id or key_id in seen:
                errors.append(f"{label}.key_id must be non-empty and unique")
            else:
                seen.add(key_id)
            try:
                raw = strict_b64(item.get("public_key"), f"{label}.public_key")
                if len(raw) != 32:
                    errors.append(f"{label}.public_key must decode to 32 bytes")
            except ValueError as exc:
                errors.append(str(exc))
    governance = policy.get("tag_governance_attestation")
    governance_keys = (
        governance.get("trusted_ed25519_keys") if isinstance(governance, dict) else None
    )
    max_validity = governance.get("max_validity_seconds") if isinstance(governance, dict) else None
    if (
        not isinstance(governance, dict)
        or governance.get("state") != "enforced"
        or not isinstance(max_validity, int)
        or isinstance(max_validity, bool)
        or not 60 <= max_validity <= 900
    ):
        errors.append(
            "release compliance policy has no enforced short-lived out-of-band tag governance attestation"
        )
    if not isinstance(governance_keys, list) or not governance_keys:
        errors.append("release compliance policy has no trusted tag-governance auditor key")
    else:
        governance_key_ids: set[str] = set()
        for index, item in enumerate(governance_keys):
            label = f"tag_governance_attestation.trusted_ed25519_keys[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object")
                continue
            key_id = item.get("key_id")
            if (
                not isinstance(key_id, str)
                or not key_id
                or key_id in governance_key_ids
            ):
                errors.append(f"{label}.key_id must be non-empty and unique")
            else:
                governance_key_ids.add(key_id)
            try:
                raw = strict_b64(item.get("public_key"), f"{label}.public_key")
                if len(raw) != 32:
                    errors.append(f"{label}.public_key must decode to 32 bytes")
            except ValueError as exc:
                errors.append(str(exc))
    python = toolchain.get("python")
    version = python.get("version") if isinstance(python, dict) else None
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        errors.append("release toolchain must pin an exact CPython patch version")
    targets = policy.get("production_targets")
    if not isinstance(targets, list) or not targets or not all(
        isinstance(target, str) and target for target in targets
    ) or len(set(targets)) != len(targets):
        errors.append("release compliance policy production_targets must be unique and non-empty")
        targets = []
    enforcement = policy.get("build_lock_enforcement")
    locks = enforcement.get("platform_locks") if isinstance(enforcement, dict) else None
    if (
        not isinstance(enforcement, dict)
        or enforcement.get("state") != "enforced"
        or enforcement.get("fully_hashed") is not True
    ):
        errors.append("release compliance policy has no enforced fully hashed platform locks")
    if not isinstance(locks, dict) or set(locks) != set(targets):
        errors.append("release compliance platform lock inventory must exactly cover production targets")
        locks = {}
    active_workflow = "\n".join(
        line.split("#", 1)[0]
        for line in (workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")).splitlines()
    )
    selected_promotion_workflow = (
        promotion_workflow
        if promotion_workflow is not None
        else workflow
        if workflow is not None
        else PROMOTION_WORKFLOW_PATH.read_text(encoding="utf-8")
    )
    active_promotion_workflow = "\n".join(
        line.split("#", 1)[0]
        for line in selected_promotion_workflow.splitlines()
    )
    active_extended_workflow = "\n".join(
        line.split("#", 1)[0]
        for line in (
            extended_workflow
            if extended_workflow is not None
            else EXTENDED_WORKFLOW_PATH.read_text(encoding="utf-8")
        ).splitlines()
    )
    active_xp_workflow = "\n".join(
        line.split("#", 1)[0]
        for line in (
            xp_workflow
            if xp_workflow is not None
            else XP_WORKFLOW_PATH.read_text(encoding="utf-8")
        ).splitlines()
    )
    for target, raw_path in locks.items():
        if not safe_relative_path(raw_path):
            errors.append(f"release compliance lock for {target} has an unsafe path")
            continue
        assert isinstance(raw_path, str)
        lock_path, path_error = secure_regular_file(
            policy_root,
            raw_path,
            f"release compliance lock for {target}",
        )
        if path_error:
            errors.append(path_error)
            continue
        _, lock_errors = read_fully_hashed_lock(
            policy_root,
            {"file": raw_path},
            f"release compliance lock for {target}",
        )
        errors.extend(lock_errors)
        producer_workflow, job, matrix_arch = producer_for_target(
            target,
            release_workflow=active_workflow,
            extended_workflow=active_extended_workflow,
            xp_workflow=active_xp_workflow,
        )
        job_block = workflow_job_block(producer_workflow, job)
        if matrix_arch is not None and not matrix_row_binds_lock(
            job_block,
            matrix_arch,
            raw_path,
        ):
            errors.append(
                f"release workflow {job} matrix row {matrix_arch} does not bind "
                f"{target} to exact lock {raw_path}"
            )
        errors.extend(
            check_native_job_lock_usage(
                job_block,
                job,
                target,
                raw_path,
                allow_matrix_lock=matrix_arch is not None,
            )
        )
    verifier = policy.get("verifier_bootstrap")
    verifier_lock = verifier.get("lock_file") if isinstance(verifier, dict) else None
    if (
        not isinstance(verifier, dict)
        or verifier.get("state") != "enforced"
        or verifier.get("fully_hashed") is not True
        or not safe_relative_path(verifier_lock)
    ):
        errors.append("release compliance policy has no enforced fully hashed verifier bootstrap")
        verifier_lock = None
    if isinstance(verifier_lock, str):
        _, verifier_path_error = secure_regular_file(
            policy_root,
            verifier_lock,
            "release compliance verifier bootstrap lock",
        )
        if verifier_path_error:
            errors.append(verifier_path_error)
        verifier_versions, verifier_errors = read_fully_hashed_lock(
            policy_root,
            {"file": verifier_lock},
            "release compliance verifier bootstrap lock",
        )
        errors.extend(verifier_errors)
        if normalize_component_name("cryptography") not in verifier_versions:
            errors.append("release compliance verifier bootstrap lock must pin cryptography")
    required_publish_tokens = (
        "check_release_license_compliance.py",
        "--assets-dir release-assets",
        "--repository",
        "--tag",
        "--sha",
        "--policy",
        "--policy-root",
        "--evidence",
        "--signature",
        "--evidence-root",
        "--protected-platform-registry",
        "--candidate-inventory",
        "--tag-governance-attestation",
        "--tag-governance-signature",
    )
    publish_block = workflow_job_block(active_promotion_workflow, "promote-production-release")
    if not publish_block:
        publish_block = workflow_job_block(active_promotion_workflow, "publish")
    publish_steps = workflow_step_blocks(publish_block)
    verifier_indexes = [
        index
        for index, step in enumerate(publish_steps)
        if isinstance(verifier_lock, str)
        and any(
            re.match(r"^(?:python|python3)\s+-m\s+pip\s+install(?:\s|$)", command)
            and "--require-hashes" in command
            and verifier_lock in command
            and re.search(r"(?:--requirement(?:=|\s)|(?:^|\s)-r(?:\s|$))", command)
            for command in executable_run_commands(step)
        )
    ]
    if isinstance(verifier_lock, str) and not verifier_indexes:
        errors.append(
            "release workflow publish job does not bootstrap the compliance verifier "
            f"from {verifier_lock} with pip --require-hashes"
        )
    audit_indexes = [
        index
        for index, step in enumerate(publish_steps)
        if any(
            command_starts_python_script(command, "check_release_license_compliance.py")
            and all(token in command for token in required_publish_tokens[1:])
            for command in executable_run_commands(step)
        )
    ]
    upload_indexes = [
        index
        for index, step in enumerate(publish_steps)
        if "uses: softprops/action-gh-release" in step
        or any(
            command_starts_release_create(command)
            for command in executable_run_commands(step)
        )
    ]
    if not audit_indexes:
        errors.append(
            "release workflow has no mandatory exact-artifact license compliance audit before publish"
        )
    elif not upload_indexes or min(audit_indexes) > min(upload_indexes):
        errors.append("release workflow license compliance audit must run before release upload")
    elif verifier_indexes and max(verifier_indexes) > min(audit_indexes):
        errors.append("release workflow must install the hashed verifier before compliance audit")
    return errors


def verify_evidence_signature(
    evidence_bytes: bytes,
    signature: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    verify_ed25519_signature(
        evidence_bytes,
        signature,
        policy.get("trusted_ed25519_keys"),
        label="release compliance",
    )


def verify_tag_governance_signature(
    attestation_bytes: bytes,
    signature: dict[str, Any],
    policy: dict[str, Any],
) -> None:
    governance = policy.get("tag_governance_attestation")
    keys = governance.get("trusted_ed25519_keys") if isinstance(governance, dict) else None
    verify_ed25519_signature(
        attestation_bytes,
        signature,
        keys,
        label="tag governance",
    )


def verify_ed25519_signature(
    payload_bytes: bytes,
    signature: dict[str, Any],
    keys: Any,
    *,
    label: str,
) -> None:
    if signature.get("schema_version") != 1:
        raise ValueError(f"{label} signature schema_version must be 1")
    if signature.get("algorithm") != "ed25519":
        raise ValueError(f"{label} signature algorithm must be ed25519")
    key_id = signature.get("key_id")
    matched = [
        item
        for item in keys if isinstance(item, dict) and item.get("key_id") == key_id
    ] if isinstance(keys, list) else []
    if len(matched) != 1:
        raise ValueError(f"{label} signature key_id is not uniquely trusted")
    public_bytes = strict_b64(matched[0].get("public_key"), "trusted public key")
    signature_bytes = strict_b64(signature.get("signature"), f"{label} signature")
    if len(public_bytes) != 32 or len(signature_bytes) != 64:
        raise ValueError(f"{label} Ed25519 key/signature length is invalid")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise RuntimeError(f"cryptography is required to verify {label} approval") from exc
    try:
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature_bytes,
            payload_bytes,
        )
    except InvalidSignature as exc:
        raise ValueError(f"{label} signature is invalid") from exc


def strict_b64(value: Any, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty base64")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{label} must be valid base64") from exc


def check_evidence(
    evidence: dict[str, Any],
    *,
    policy: dict[str, Any],
    policy_sha256: str,
    policy_root: Path,
    toolchain: dict[str, Any],
    matrix: dict[str, Any],
    assets_dir: Path,
    evidence_root: Path,
    protected_platform_registry: Path,
    candidate_inventory: Path,
    repository: str,
    tag: str,
    sha: str,
    now: datetime | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_scalars = {
        "schema_version": 1,
        "decision": "approved",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "policy_sha256": policy_sha256,
    }
    for key, expected in expected_scalars.items():
        if evidence.get(key) != expected:
            errors.append(f"compliance evidence {key} must be {expected!r}")
    errors.extend(check_review_window(evidence, now=now))
    if assets_dir.is_symlink() or not assets_dir.is_dir():
        return [*errors, f"release asset directory must be a real directory: {assets_dir}"]
    if path_is_reparse(evidence_root) or not evidence_root.is_dir():
        return [*errors, f"compliance evidence root must be a real directory: {evidence_root}"]

    candidate_record = evidence.get("candidate_inventory")
    if not isinstance(candidate_record, dict) or not valid_evidence_record(candidate_record):
        errors.append("compliance evidence candidate_inventory record is invalid")
    else:
        errors.extend(
            check_evidence_file(
                candidate_record,
                evidence_root,
                "compliance release candidate inventory",
            )
        )
        bound_candidate, candidate_error = secure_regular_file(
            evidence_root,
            candidate_record.get("file"),
            "compliance release candidate inventory",
        )
        try:
            supplied_candidate = candidate_inventory.resolve(strict=True)
        except OSError:
            supplied_candidate = candidate_inventory
        if candidate_error or bound_candidate is None:
            pass
        elif supplied_candidate != bound_candidate.resolve(strict=True):
            errors.append(
                "compliance candidate inventory input must be the signed bundle file"
            )

    registry_record = evidence.get("protected_platform_registry")
    protected_registry: dict[str, Any] = {}
    if not isinstance(registry_record, dict) or not valid_evidence_record(registry_record):
        errors.append("compliance evidence protected_platform_registry record is invalid")
    else:
        errors.extend(
            check_evidence_file(
                registry_record,
                evidence_root,
                "compliance protected platform registry",
            )
        )
        raw_registry_file = registry_record.get("file")
        bound_registry, bound_error = secure_regular_file(
            evidence_root,
            raw_registry_file,
            "compliance protected platform registry",
        )
        try:
            supplied_registry = protected_platform_registry.resolve(strict=True)
        except OSError:
            supplied_registry = protected_platform_registry
        if bound_error or bound_registry is None:
            pass
        elif supplied_registry != bound_registry.resolve(strict=True):
            errors.append(
                "compliance protected platform registry input must be the signed bundle file"
            )
        else:
            try:
                protected_registry = json.loads(bound_registry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                errors.append("compliance protected platform registry must be valid JSON")
            if not isinstance(protected_registry, dict):
                errors.append("compliance protected platform registry must contain an object")
                protected_registry = {}

    expected_names = expected_native_manifest_names(matrix, tag, protected_registry)
    actual_paths = {
        path.name: path
        for path in assets_dir.iterdir()
        if path.is_file() and not path.is_symlink() and path.name.endswith("-native-manifest.json")
    }
    if set(actual_paths) != expected_names:
        errors.append(
            "native manifest inventory must exactly match the standard release matrix: "
            f"expected {sorted(expected_names)}, got {sorted(actual_paths)}"
        )
    records = evidence.get("native_manifests")
    if not isinstance(records, dict):
        return [*errors, "compliance evidence native_manifests must be an object"]
    if set(records) != set(actual_paths):
        errors.append(
            "signed compliance manifest inventory must exactly match local native manifests"
        )

    versions = required_versions(toolchain, tag)
    profiles = policy.get("required_profiles")
    assert isinstance(profiles, dict)
    for name, path in sorted(actual_paths.items()):
        record = records.get(name)
        if not isinstance(record, dict):
            errors.append(f"signed compliance record for {name} must be an object")
            continue
        manifest_hash = sha256_file(path)
        if record.get("sha256") != manifest_hash:
            errors.append(f"signed compliance record for {name} does not match manifest bytes")
        entries, manifest_errors = native_manifest_entries(path, assets_dir)
        errors.extend(manifest_errors)
        inventory = record.get("inventory")
        if not isinstance(inventory, dict):
            errors.append(f"signed compliance record for {name} inventory must be an object")
            continue
        inventory_hash = hashlib.sha256(canonical_json(inventory)).hexdigest()
        if record.get("inventory_sha256") != inventory_hash:
            errors.append(f"signed compliance record for {name} inventory_sha256 is invalid")
        profile = profile_for_manifest(name)
        target = target_for_manifest(name, matrix=matrix, tag=tag)
        enforcement = policy.get("build_lock_enforcement")
        locks = enforcement.get("platform_locks") if isinstance(enforcement, dict) else None
        expected_lock = locks.get(target) if isinstance(locks, dict) else None
        if not isinstance(expected_lock, str):
            errors.append(f"no enforced resolver lock is configured for {target}")
            continue
        tracked_lock_path = policy_root.joinpath(*PurePosixPath(expected_lock).parts)
        expected_lock_sha256 = sha256_file(tracked_lock_path)
        required = profiles.get(profile)
        if not isinstance(required, list):
            errors.append(f"no approved compliance profile for {name}")
            continue
        errors.extend(
            check_inventory(
                inventory,
                manifest_name=name,
                profile=profile,
                required_names=required,
                versions=versions,
                artifact_names=set(entries),
                evidence_root=evidence_root,
                expected_lock_file=expected_lock,
                expected_lock_sha256=expected_lock_sha256,
            )
        )
    return errors


def check_review_window(evidence: dict[str, Any], *, now: datetime | None) -> list[str]:
    errors: list[str] = []
    try:
        reviewed = parse_timestamp(evidence.get("reviewed_at"), "reviewed_at")
        expires = parse_timestamp(evidence.get("expires_at"), "expires_at")
    except ValueError as exc:
        return [str(exc)]
    current = now or datetime.now(timezone.utc)
    if reviewed > current:
        errors.append("compliance evidence reviewed_at must not be in the future")
    if expires <= reviewed:
        errors.append("compliance evidence expires_at must be after reviewed_at")
    if expires <= current:
        errors.append("compliance evidence approval has expired")
    return errors


def check_tag_governance_attestation(
    attestation: dict[str, Any],
    *,
    policy: dict[str, Any],
    repository: str,
    tag: str,
    sha: str,
    now: datetime | None = None,
) -> list[str]:
    """Validate a short-lived, independently signed GitHub tag-ruleset snapshot."""

    errors: list[str] = []
    expected = {
        "schema_version": 1,
        "decision": "approved",
        "source": "github-rulesets-api",
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "tag_update_blocked": True,
        "tag_deletion_blocked": True,
    }
    for field, value in expected.items():
        if attestation.get(field) != value:
            errors.append(f"tag governance attestation {field} must be {value!r}")
    if attestation.get("bypass_actors") != []:
        errors.append("tag governance attestation must prove an empty bypass actor set")
    ruleset_ids = attestation.get("ruleset_ids")
    if (
        not isinstance(ruleset_ids, list)
        or not ruleset_ids
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
            for value in ruleset_ids
        )
        or len(set(ruleset_ids)) != len(ruleset_ids)
    ):
        errors.append("tag governance attestation ruleset_ids must be unique positive integers")
    auditor = attestation.get("auditor")
    if (
        not isinstance(auditor, dict)
        or auditor.get("kind") not in {"github-app", "independent-automation"}
        or not isinstance(auditor.get("identity"), str)
        or not auditor.get("identity")
    ):
        errors.append("tag governance attestation must identify its out-of-band auditor")
    try:
        observed = parse_timestamp(attestation.get("observed_at"), "governance observed_at")
        expires = parse_timestamp(attestation.get("expires_at"), "governance expires_at")
    except ValueError as exc:
        return [*errors, str(exc)]
    current = now or datetime.now(timezone.utc)
    governance = policy.get("tag_governance_attestation")
    max_validity = governance.get("max_validity_seconds") if isinstance(governance, dict) else None
    if observed > current:
        errors.append("tag governance attestation observed_at must not be in the future")
    if expires <= observed:
        errors.append("tag governance attestation expires_at must be after observed_at")
    if expires <= current:
        errors.append("tag governance attestation has expired")
    if isinstance(max_validity, int) and (expires - observed).total_seconds() > max_validity:
        errors.append("tag governance attestation validity exceeds the approved short window")
    return errors


def parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"compliance evidence {label} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(
            f"compliance evidence {label} must be an RFC3339 UTC timestamp"
        ) from exc
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"compliance evidence {label} must use UTC")
    return parsed


def expected_native_manifest_names(
    matrix: dict[str, Any],
    tag: str,
    protected_registry: dict[str, Any] | None = None,
) -> set[str]:
    release = matrix.get("default_github_release")
    jobs = release.get("native_jobs") if isinstance(release, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("release matrix default native_jobs must be a list")
    version = tag.removeprefix("v")
    names: set[str] = set()
    for job in jobs:
        patterns = job.get("asset_patterns") if isinstance(job, dict) else None
        if not isinstance(patterns, list):
            raise ValueError("release matrix native job asset_patterns must be a list")
        for pattern in patterns:
            if not isinstance(pattern, str) or not pattern.endswith("-native-manifest.json"):
                continue
            normalized = pattern.replace("1.0.24", version)
            match = re.search(r"<([^>]+)>", normalized)
            if match is None:
                names.add(normalized)
                continue
            for choice in match.group(1).split("|"):
                names.add(normalized[: match.start()] + choice + normalized[match.end() :])
    for target in matrix.get("script_supported_native", []):
        patterns = target.get("asset_patterns") if isinstance(target, dict) else None
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            if isinstance(pattern, str) and pattern.endswith("-native-manifest.json"):
                names.add(pattern.replace("1.0.24", version))
    if isinstance(protected_registry, dict):
        for entry in protected_registry.get("accepted_evidence", []):
            if not isinstance(entry, dict) or entry.get("release_tag") != tag:
                continue
            names.update(native_manifest_names_in_value(entry))
    return names


def native_manifest_names_in_value(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            names.update(native_manifest_names_in_value(nested))
    elif isinstance(value, list):
        for nested in value:
            names.update(native_manifest_names_in_value(nested))
    elif isinstance(value, str):
        candidate = Path(unquote(urlsplit(value).path)).name
        if candidate.endswith("-native-manifest.json") and safe_asset_name(candidate):
            names.add(candidate)
    return names


def safe_asset_name(value: str) -> bool:
    return value not in {"", ".", ".."} and "/" not in value and "\\" not in value


def native_manifest_entries(
    path: Path,
    assets_dir: Path,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} is not valid JSON: {exc}"]
    if not isinstance(payload, list) or not payload:
        return {}, [f"{path.name} must contain a non-empty manifest list"]
    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(payload):
        label = f"{path.name} entry {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        raw_file = item.get("file")
        name = Path(raw_file).name if isinstance(raw_file, str) else ""
        if not name or not safe_relative_path(raw_file) or name in entries:
            errors.append(f"{label} file must be a unique safe artifact path")
            continue
        artifact = assets_dir / name
        if artifact.is_symlink() or not artifact.is_file():
            errors.append(f"{label} artifact is missing from release assets: {name}")
            continue
        if item.get("size_bytes") != artifact.stat().st_size:
            errors.append(f"{label} size_bytes does not match release asset {name}")
        if item.get("sha256") != sha256_file(artifact):
            errors.append(f"{label} sha256 does not match release asset {name}")
        entries[name] = item
    return entries, errors


def profile_for_manifest(name: str) -> str:
    if "-windows-x86-native-manifest.json" in name:
        return "minimal-cli"
    if re.search(r"-windows-xp-(?:x86|x64)-native-manifest\.json$", name):
        return "minimal-cli"
    if "-linux-" in name:
        return "secure-cli"
    if any(token in name for token in ("-windows-x64-", "-windows-arm64-", "-macos-")):
        return "gui-secure"
    raise ValueError(f"no third-party compliance profile for native manifest {name}")


def target_for_manifest(name: str, *, matrix: dict[str, Any], tag: str) -> str:
    """Map a concrete manifest name through matrix target IDs, never filename aliases."""

    version = tag.removeprefix("v")
    release = matrix.get("default_github_release")
    jobs = release.get("native_jobs") if isinstance(release, dict) else None
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, dict):
                continue
            targets = job.get("platform_target_ids")
            arches = job.get("arches")
            patterns = job.get("asset_patterns")
            if not isinstance(targets, list) or not isinstance(arches, list) or not isinstance(patterns, list):
                continue
            arch_targets = {
                str(arch): str(target)
                for arch, target in zip(arches, targets, strict=True)
            }
            for pattern in patterns:
                if not isinstance(pattern, str) or not pattern.endswith("-native-manifest.json"):
                    continue
                normalized = pattern.replace("1.0.24", version)
                match = re.search(r"<([^>]+)>", normalized)
                if match is None:
                    continue
                for arch in match.group(1).split("|"):
                    concrete = normalized[: match.start()] + arch + normalized[match.end() :]
                    if concrete == name and arch in arch_targets:
                        return arch_targets[arch]
    for target in matrix.get("script_supported_native", []):
        if not isinstance(target, dict) or not isinstance(target.get("platform_target_id"), str):
            continue
        for pattern in target.get("asset_patterns", []):
            if (
                isinstance(pattern, str)
                and pattern.endswith("-native-manifest.json")
                and pattern.replace("1.0.24", version) == name
            ):
                return target["platform_target_id"]
    xp_match = re.fullmatch(
        rf"remote-ops-workspace-v{re.escape(version)}-windows-xp-(x86|x64)-native-manifest\.json",
        name,
    )
    if xp_match is not None:
        return f"windows-xp-native-{xp_match.group(1)}"
    raise ValueError(f"cannot map native manifest to a production target: {name}")


def required_versions(toolchain: dict[str, Any], tag: str) -> dict[str, str]:
    python = toolchain.get("python")
    python_version = python.get("version") if isinstance(python, dict) else None
    if not isinstance(python_version, str):
        raise ValueError("release toolchain Python version is missing")
    versions = {
        normalize_component_name("CPython"): python_version,
        normalize_component_name("remote-ops-workspace"): tag.removeprefix("v"),
    }
    packages = toolchain.get("python_packages")
    if not isinstance(packages, list):
        raise ValueError("release toolchain python_packages must be a list")
    for item in packages:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            versions[normalize_component_name(item["name"])] = str(item.get("version", ""))
    return versions


def check_inventory(
    inventory: dict[str, Any],
    *,
    manifest_name: str,
    profile: str,
    required_names: list[str],
    versions: dict[str, str],
    artifact_names: set[str],
    evidence_root: Path,
    expected_lock_file: str,
    expected_lock_sha256: str,
) -> list[str]:
    prefix = f"{manifest_name} signed inventory"
    errors: list[str] = []
    required_flags = {
        "closed_world_complete": True,
        "artifact_contents_scanned": True,
        "all_installed_distributions_recorded": True,
        "classification_complete": True,
    }
    if inventory.get("schema_version") != 1:
        errors.append(f"{prefix} schema_version must be 1")
    if inventory.get("profile") != profile:
        errors.append(f"{prefix} profile must be {profile!r}")
    for key, expected in required_flags.items():
        if inventory.get(key) is not expected:
            errors.append(f"{prefix} {key} must be true")
    lock = inventory.get("resolver_lock")
    locked_versions: dict[str, str] = {}
    if not isinstance(lock, dict) or lock.get("fully_hashed") is not True:
        errors.append(f"{prefix} must bind a complete fully hashed resolver lock")
    elif (
        lock.get("format") != "pip-requirements"
        or lock.get("source_file") != expected_lock_file
        or not safe_relative_path(lock.get("file"))
        or not valid_sha256(lock.get("sha256"))
    ):
        errors.append(f"{prefix} resolver lock file/hash is invalid")
    elif lock.get("sha256") != expected_lock_sha256:
        errors.append(f"{prefix} resolver lock does not match the tracked build input")
    else:
        errors.extend(check_evidence_file(lock, evidence_root, f"{prefix} resolver lock"))
        locked_versions, lock_errors = read_fully_hashed_lock(
            evidence_root,
            lock,
            f"{prefix} resolver lock",
        )
        errors.extend(lock_errors)

    components = inventory.get("components")
    if not isinstance(components, list):
        return [*errors, f"{prefix} components must be a list"]
    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(components):
        label = f"{prefix} component {index}"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        name = item.get("name")
        version = item.get("version")
        normalized_name = normalize_component_name(name) if isinstance(name, str) else ""
        if not normalized_name or normalized_name in indexed:
            errors.append(f"{label} name must be non-empty and unique")
            continue
        indexed[normalized_name] = item
        if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
            errors.append(f"{label} version must be exact")
        if item.get("scope") not in {"bundled", "build-only"}:
            errors.append(f"{label} scope must be bundled or build-only")
        if item.get("origin") not in {
            "python-runtime",
            "python-distribution",
            "native-component",
            "pyinstaller-bootloader",
        }:
            errors.append(f"{label} origin is invalid")
        if not isinstance(item.get("license_expression"), str) or not item["license_expression"]:
            errors.append(f"{label} license_expression must be recorded")
        license_files = item.get("license_files")
        if item.get("scope") == "bundled" and not valid_license_files(license_files):
            errors.append(f"{label} bundled license_files are missing or invalid")
        elif item.get("scope") == "bundled":
            errors.extend(
                check_license_evidence_files(
                    license_files,
                    evidence_root,
                    f"{label} license file",
                )
            )

    realized = inventory.get("realized_environment")
    realized_versions: dict[str, str] = {}
    if not isinstance(realized, dict) or not valid_evidence_record(realized):
        errors.append(f"{prefix} realized_environment pip-inspect evidence is invalid")
    elif realized.get("format") != "pip-inspect-v1":
        errors.append(f"{prefix} realized_environment format must be pip-inspect-v1")
    else:
        errors.extend(
            check_evidence_file(realized, evidence_root, f"{prefix} realized environment")
        )
        realized_versions, realized_errors = read_pip_inspect(
            evidence_root,
            realized,
            f"{prefix} realized environment",
        )
        errors.extend(realized_errors)

    classified_versions = {
        normalized_name: str(item.get("version", ""))
        for normalized_name, item in indexed.items()
        if item.get("origin") == "python-distribution"
    }
    if realized_versions and classified_versions != realized_versions:
        errors.append(
            f"{prefix} component classifications must exactly match the realized "
            "pip environment"
        )
    third_party_realized = {
        name: version
        for name, version in realized_versions.items()
        if name != normalize_component_name("remote-ops-workspace")
    }
    if locked_versions and locked_versions != third_party_realized:
        errors.append(
            f"{prefix} fully hashed resolver lock must exactly match every realized "
            "third-party distribution"
        )
    for name in required_names:
        normalized_name = normalize_component_name(name)
        item = indexed.get(normalized_name)
        if item is None:
            errors.append(f"{prefix} missing required redistributed component {name}")
            continue
        if item.get("scope") != "bundled":
            errors.append(f"{prefix} required component {name} must be classified bundled")
        expected_version = versions.get(normalized_name)
        if expected_version is None or item.get("version") != expected_version:
            errors.append(
                f"{prefix} component {name} version must be {expected_version!r}"
            )

    scans = inventory.get("artifact_license_files")
    if not isinstance(scans, dict) or set(scans) != artifact_names:
        errors.append(f"{prefix} must contain a license-file extraction scan for every artifact")
    elif any(not valid_license_files(value) for value in scans.values()):
        errors.append(f"{prefix} artifact license-file extraction scans are invalid")
    else:
        for artifact_name, license_files in scans.items():
            errors.extend(
                check_license_evidence_files(
                    license_files,
                    evidence_root,
                    f"{prefix} {artifact_name} extracted license file",
                )
            )
        bundled_license_records = {
            license_record_key(item)
            for component in indexed.values()
            if component.get("scope") == "bundled"
            for item in component.get("license_files", [])
            if isinstance(item, dict)
        }
        for artifact_name, license_files in scans.items():
            scanned = {
                license_record_key(item)
                for item in license_files
                if isinstance(item, dict)
            }
            missing = bundled_license_records - scanned
            if missing:
                errors.append(
                    f"{prefix} {artifact_name} scan is missing bundled component license files"
                )

    if profile == "gui-secure":
        errors.extend(
            check_qt_channel(
                inventory.get("pyqt_qt_channel"),
                prefix=prefix,
                evidence_root=evidence_root,
            )
        )
    elif inventory.get("pyqt_qt_channel") not in (None, {}):
        errors.append(f"{prefix} non-GUI profile must not claim a PyQt/Qt channel")
    return errors


def check_qt_channel(value: Any, *, prefix: str, evidence_root: Path) -> list[str]:
    if not isinstance(value, dict):
        return [f"{prefix} must record the reviewed PyQt/Qt distribution channel"]
    errors: list[str] = []
    channel = value.get("channel")
    common = ("pyqt_terms", "qt_terms", "qt_component_inventory")
    for key in common:
        if not valid_evidence_record(value.get(key)):
            errors.append(f"{prefix} PyQt/Qt {key} evidence is invalid")
        else:
            errors.extend(
                check_evidence_file(value[key], evidence_root, f"{prefix} PyQt/Qt {key}")
            )
    if channel == "commercial":
        for key in ("pyqt_commercial_license", "qt_commercial_license"):
            if not valid_evidence_record(value.get(key)):
                errors.append(f"{prefix} commercial channel missing {key} evidence")
            else:
                errors.extend(
                    check_evidence_file(value[key], evidence_root, f"{prefix} {key}")
                )
    elif channel == "open-source":
        for key in (
            "application_license_review",
            "corresponding_source",
            "relink_mechanism",
        ):
            if not valid_evidence_record(value.get(key)):
                errors.append(f"{prefix} open-source channel missing {key} evidence")
            else:
                errors.extend(
                    check_evidence_file(value[key], evidence_root, f"{prefix} {key}")
                )
    else:
        errors.append(f"{prefix} PyQt/Qt channel must be commercial or open-source")
    return errors


def valid_evidence_record(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("reference"), str)
        and bool(value["reference"])
        and safe_relative_path(value.get("file"))
        and isinstance(value.get("size_bytes"), int)
        and not isinstance(value.get("size_bytes"), bool)
        and value["size_bytes"] > 0
        and valid_sha256(value.get("sha256"))
    )


def valid_license_files(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(item, dict)
            and safe_relative_path(item.get("path"))
            and safe_relative_path(item.get("file"))
            and isinstance(item.get("size_bytes"), int)
            and not isinstance(item.get("size_bytes"), bool)
            and item["size_bytes"] > 0
            and valid_sha256(item.get("sha256"))
            for item in value
        )
    )


def check_license_evidence_files(
    records: Any,
    evidence_root: Path,
    label: str,
) -> list[str]:
    if not isinstance(records, list):
        return [f"{label} records must be a list"]
    errors: list[str] = []
    for index, record in enumerate(records):
        if isinstance(record, dict):
            errors.extend(check_evidence_file(record, evidence_root, f"{label} {index}"))
    return errors


def check_evidence_file(
    record: dict[str, Any],
    evidence_root: Path,
    label: str,
) -> list[str]:
    raw_file = record.get("file")
    if not safe_relative_path(raw_file):
        return [f"{label} file path is invalid"]
    assert isinstance(raw_file, str)
    path, path_error = secure_regular_file(evidence_root, raw_file, label)
    if path_error:
        return [path_error]
    assert path is not None
    errors: list[str] = []
    if record.get("size_bytes") != path.stat().st_size:
        errors.append(f"{label} size_bytes does not match {raw_file}")
    if record.get("sha256") != sha256_file(path):
        errors.append(f"{label} sha256 does not match {raw_file}")
    return errors


def read_pip_inspect(
    evidence_root: Path,
    record: dict[str, Any],
    label: str,
) -> tuple[dict[str, str], list[str]]:
    raw_file = record.get("file")
    assert isinstance(raw_file, str)
    path, path_error = secure_regular_file(evidence_root, raw_file, label)
    if path_error:
        return {}, [path_error]
    assert path is not None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"{label} is not valid pip inspect JSON: {exc}"]
    installed = payload.get("installed") if isinstance(payload, dict) else None
    if not isinstance(installed, list) or not installed:
        return {}, [f"{label} installed inventory must be a non-empty list"]
    versions: dict[str, str] = {}
    errors: list[str] = []
    for index, item in enumerate(installed):
        metadata = item.get("metadata") if isinstance(item, dict) else None
        name = metadata.get("name") if isinstance(metadata, dict) else None
        version = metadata.get("version") if isinstance(metadata, dict) else None
        normalized = normalize_component_name(name) if isinstance(name, str) else ""
        if (
            not normalized
            or normalized in versions
            or not isinstance(version, str)
            or VERSION_RE.fullmatch(version) is None
        ):
            errors.append(f"{label} installed entry {index} name/version is invalid or duplicate")
            continue
        versions[normalized] = version
    return versions, errors


def read_fully_hashed_lock(
    evidence_root: Path,
    record: dict[str, Any],
    label: str,
) -> tuple[dict[str, str], list[str]]:
    raw_file = record.get("file")
    assert isinstance(raw_file, str)
    path, path_error = secure_regular_file(evidence_root, raw_file, label)
    if path_error:
        return {}, [path_error]
    assert path is not None
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {}, [f"{label} cannot be read: {exc}"]
    logical: list[str] = []
    current = ""
    for raw_line in raw_lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        current = f"{current} {line}".strip()
        if current.endswith("\\"):
            current = current[:-1].strip()
            continue
        logical.append(current)
        current = ""
    if current:
        logical.append(current)
    versions: dict[str, str] = {}
    errors: list[str] = []
    for index, line in enumerate(logical):
        if line.startswith("--"):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})(?:\s|$)", line)
        if match is None or not hashes:
            errors.append(f"{label} requirement {index} is not exact and SHA-256 hashed")
            continue
        name = normalize_component_name(match.group(1))
        version = match.group(2)
        if name in versions:
            errors.append(f"{label} contains duplicate distribution {match.group(1)!r}")
            continue
        versions[name] = version
    if not versions:
        errors.append(f"{label} contains no exact hashed requirements")
    return versions, errors


def license_record_key(record: dict[str, Any]) -> tuple[Any, Any, Any]:
    return record.get("path"), record.get("sha256"), record.get("size_bytes")


def normalize_component_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job)}:\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*\n|\Z)",
        workflow,
    )
    return match.group(1) if match else ""


def workflow_step_blocks(job_block: str) -> list[str]:
    starts = [
        match.start()
        for match in re.finditer(r"(?m)^\s{4,}-\s+(?:name:|uses:|run:)", job_block)
    ]
    return [
        job_block[start : starts[index + 1] if index + 1 < len(starts) else len(job_block)]
        for index, start in enumerate(starts)
    ]


def producer_for_target(
    target: str,
    *,
    release_workflow: str,
    extended_workflow: str,
    xp_workflow: str,
) -> tuple[str, str, str | None]:
    standard = {
        "windows-x86": ("windows-native", "x86"),
        "windows-x64": ("windows-native", "x64"),
        "windows-arm64": ("windows-native", "arm64"),
        "macos-x64": ("macos-native", "x64"),
        "macos-arm64": ("macos-native", "arm64"),
        "linux-x86_64": ("linux-native", "x86_64"),
        "linux-aarch64": ("linux-native", "aarch64"),
    }
    if target in standard:
        job, arch = standard[target]
        return release_workflow, job, arch
    if target == "linux-i386":
        return extended_workflow, "linux-i386-native-evidence", None
    if target == "linux-armhf":
        return extended_workflow, "linux-armhf-native-evidence", None
    if target in {"windows-xp-native-x86", "windows-xp-native-x64"}:
        return xp_workflow, "xp-native-evidence", None
    raise ValueError(f"release compliance target has no exact producer mapping: {target}")


def matrix_row_binds_lock(job_block: str, arch: str, lock_path: str) -> bool:
    rows = re.findall(
        rf"(?ms)^\s{{10}}-\s+arch:\s*['\"]?{re.escape(arch)}['\"]?\s*$"
        rf"(.*?)(?=^\s{{10}}-\s+arch:|^\s{{4}}[A-Za-z0-9_-]+:|\Z)",
        job_block,
    )
    if len(rows) != 1:
        return False
    return re.search(
        rf"(?m)^\s+lock:\s*['\"]?{re.escape(lock_path)}['\"]?\s*$",
        rows[0],
    ) is not None


def xp_target_step_binds_lock(job_block: str, target: str, lock_path: str) -> bool:
    condition = re.compile(
        rf"(?m)^\s*if:\s*\$\{{\{{\s*inputs\.target\s*==\s*['\"]{re.escape(target)}['\"]\s*\}}\}}\s*$"
    )
    for step in workflow_step_blocks(job_block):
        if condition.search(step) is None:
            continue
        if any(
            lock_path in command and "--require-hashes" in command
            for command in executable_run_commands(step)
        ):
            return True
    return False


def check_native_job_lock_usage(
    job_block: str,
    job: str,
    target: str,
    lock_path: str,
    *,
    allow_matrix_lock: bool = False,
) -> list[str]:
    errors: list[str] = []
    commands = executable_run_commands(job_block)
    pip_commands = [
        (index, command)
        for index, command in enumerate(commands)
        if re.match(r"^(?:python|python3)\s+-m\s+pip\s+install(?:\s|$)", command)
    ]
    lock_tokens = (lock_path, "${{ matrix.lock }}") if allow_matrix_lock else (lock_path,)
    lock_indexes = [
        index
        for index, command in pip_commands
        if "--require-hashes" in command
        and any(token in command for token in lock_tokens)
        and re.search(r"(?:--requirement(?:=|\s)|(?:^|\s)-r(?:\s|$))", command)
    ]
    if lock_path not in job_block or not lock_indexes:
        errors.append(
            f"release workflow {job} job does not consume {target} lock {lock_path} "
            "with executable pip --require-hashes"
        )
    if target.startswith("windows-xp-native-") and not xp_target_step_binds_lock(
        job_block,
        target,
        lock_path,
    ):
        errors.append(
            f"release workflow {job} has no target-conditional hashed lock install for {target}"
        )
    for _, command in pip_commands:
        uses_lock = (
            "--require-hashes" in command
            and any(token in command for token in lock_tokens)
            and re.search(r"(?:--requirement(?:=|\s)|(?:^|\s)-r(?:\s|$))", command)
        )
        if "--no-deps" not in command and not uses_lock:
            errors.append(
                f"release workflow {job} has a dependency-resolving pip install outside "
                f"the {target} hashed lock: {command}"
            )
    project_installs = [
        (index, command)
        for index, command in pip_commands
        if re.search(r"(?:^|\s)[\"']?\.\[", command)
    ]
    if not project_installs:
        errors.append(f"release workflow {job} has no explicit project/extras install")
    for index, command in project_installs:
        if "--no-deps" not in command:
            errors.append(
                f"release workflow {job} project/extras install must use --no-deps after "
                f"the {target} lock"
            )
        if not lock_indexes or index <= max(lock_indexes):
            errors.append(
                f"release workflow {job} project/extras install must occur after the "
                f"{target} hashed lock"
            )
    return errors


def executable_run_commands(job_block: str) -> list[str]:
    """Extract shell commands from YAML run scalars without accepting echo text/comments."""

    lines = job_block.splitlines()
    commands: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[index])
        if match is None:
            index += 1
            continue
        indent = len(match.group(1))
        value = match.group(2).strip()
        index += 1
        raw_commands: list[str] = []
        if value in {"|", "|-", "|+", ">", ">-", ">+"}:
            block_lines: list[str] = []
            while index < len(lines):
                raw = lines[index]
                if raw.strip() and len(raw) - len(raw.lstrip()) <= indent:
                    break
                block_lines.append(raw)
                index += 1
            nonempty_indents = [
                len(line) - len(line.lstrip()) for line in block_lines if line.strip()
            ]
            trim = min(nonempty_indents, default=0)
            stripped = [line[trim:] if len(line) >= trim else "" for line in block_lines]
            raw_commands = [" ".join(part.strip() for part in stripped)] if value.startswith(">") else stripped
        elif value:
            raw_commands = [value]
        commands.extend(normalize_shell_commands(raw_commands))
    return commands


def normalize_shell_commands(lines: list[str]) -> list[str]:
    commands: list[str] = []
    current = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(" #", 1)[0].strip()
        current = f"{current} {line}".strip()
        if current.endswith(("\\", "`")):
            current = current[:-1].strip()
            continue
        if not re.match(r"^(?:echo|printf|Write-(?:Host|Output))\b", current, re.IGNORECASE):
            commands.append(current)
        current = ""
    if current and not re.match(
        r"^(?:echo|printf|Write-(?:Host|Output))\b",
        current,
        re.IGNORECASE,
    ):
        commands.append(current)
    return commands


def command_starts_python_script(command: str, script_name: str) -> bool:
    return re.match(
        rf"^(?:python|python3)\s+(?:[^\s]+/)*scripts/{re.escape(script_name)}(?:\s|$)",
        command,
    ) is not None


def command_starts_release_create(command: str) -> bool:
    return re.match(r"^gh\s+api\s+--method\s+POST(?:\s|$)", command) is not None and bool(
        re.search(r"(?:^|\s)[\"']?repos/.+/releases[\"']?(?:\s|$)", command)
    )


def safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.strip() != value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def path_is_reparse(path: Path) -> bool:
    """Recognize POSIX symlinks and Windows symlinks/junctions/reparse points."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def secure_regular_file(
    root: Path,
    raw_file: Any,
    label: str,
) -> tuple[Path | None, str | None]:
    """Resolve a bundle file without permitting any reparse hop or root escape."""
    if not safe_relative_path(raw_file):
        return None, f"{label} file path is invalid"
    assert isinstance(raw_file, str)
    if path_is_reparse(root) or not root.is_dir():
        return None, f"{label} evidence root must be a real directory"
    try:
        resolved_root = root.resolve(strict=True)
        candidate = root
        for part in PurePosixPath(raw_file).parts:
            candidate = candidate / part
            candidate.lstat()
            if path_is_reparse(candidate):
                return None, f"{label} must not traverse a symlink or reparse point: {raw_file}"
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None, f"{label} evidence file is missing: {raw_file}"
    if not resolved.is_relative_to(resolved_root):
        return None, f"{label} escapes the evidence root: {raw_file}"
    if not candidate.is_file():
        return None, f"{label} evidence file is missing: {raw_file}"
    return candidate, None


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
