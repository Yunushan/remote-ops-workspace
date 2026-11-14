#!/usr/bin/env python3
"""Verify that downloaded release bytes came from one exact-tag release run.

The local publish-asset checker proves that an asset directory is internally
complete.  This checker closes the remaining remote boundary: every local file
must match GitHub's size and digest, and every asset in the certified inventory
must have SLSA provenance issued by the exact release workflow and source SHA.
Final verification requires one common completed successful run; the narrowly
scoped draft-transaction mode instead binds every draft asset to the current
tag-triggered run before the draft is promoted. Operators can verify a single
downloaded file against the immutable published release and its promotion run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_release_license_compliance import (  # noqa: E402
    POLICY_PATH,
    check_tag_governance_attestation,
    parse_timestamp,
    read_json_object,
    verify_tag_governance_signature,
)
from check_release_publish_assets import (  # noqa: E402
    MATRIX_PATH,
    expected_release_assets,
)
from check_release_tag_governance import check_redistribution_approval  # noqa: E402
from fetch_release_tag_governance import promotion_transaction, require_transaction  # noqa: E402

PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
RELEASE_WORKFLOW = ".github/workflows/release-promotion.yml"
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SHA_RE = re.compile(r"[0-9a-f]{40}")
TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
RUN_INVOCATION_RE = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/actions/runs/([1-9]\d*)/attempts/([1-9]\d*)"
)
GhJsonRunner = Callable[[list[str], str, int], Any]


@dataclass(frozen=True, order=True)
class RunInvocation:
    repository: str
    run_id: int
    attempt: int

    @property
    def url(self) -> str:
        return (
            f"https://github.com/{self.repository}/actions/runs/"
            f"{self.run_id}/attempts/{self.attempt}"
        )


def main(
    argv: list[str] | None = None,
    *,
    check_published_at: Callable[[datetime], list[str]] | None = None,
    audited_inputs: dict[Path, str] | None = None,
) -> int:
    args = parse_args(argv)
    try:
        draft_values = (
            args.draft_release_id,
            args.draft_transaction_run_id,
            args.draft_transaction_run_attempt,
        )
        if any(value is None for value in draft_values) and any(
            value is not None for value in draft_values
        ):
            raise ValueError(
                "draft release id, run id, and attempt must be supplied together"
            )
        draft_transaction = draft_values[0] is not None
        if draft_transaction and any(value < 1 for value in draft_values):
            raise ValueError("draft release id, run id, and attempt must be positive")
        if args.recheck_draft_bytes and not draft_transaction:
            raise ValueError("--recheck-draft-bytes requires the exact draft transaction")
        current_values = (
            args.current_transaction_run_id,
            args.current_transaction_run_attempt,
        )
        if any(value is None for value in current_values) and any(
            value is not None for value in current_values
        ):
            raise ValueError("current transaction run id and attempt must be supplied together")
        current_transaction = current_values[0] is not None
        if current_transaction and any(value < 1 for value in current_values):
            raise ValueError("current transaction run id and attempt must be positive")
        completed_values = (args.completed_promotion_run_id, args.completed_promotion_run_attempt)
        completed_promotion = any(value is not None for value in completed_values)
        if completed_promotion and any(value is None or value < 1 for value in completed_values):
            raise ValueError("completed promotion run id and attempt must be supplied together and positive")
        if draft_transaction and current_transaction:
            raise ValueError("draft and published current-transaction modes are mutually exclusive")
        single_asset = args.asset is not None
        if single_asset and (draft_transaction or current_transaction):
            raise ValueError("--asset requires a completed published release, outside a transaction")
        governance_paths = (args.governance_attestation, args.governance_signature)
        verify_governance = any(path is not None for path in governance_paths)
        if verify_governance and (
            None in governance_paths or draft_transaction or single_asset
        ):
            raise ValueError("governance verification requires both proof files and a complete published release")
        if completed_promotion and (not verify_governance or current_transaction or args.published_release_id is None):
            raise ValueError("exact completed promotion requires governance proof and a numeric published release id")
        if check_published_at is not None and (not verify_governance or current_transaction):
            raise ValueError("publication-time checks require a completed release with verified governance")
        approval_paths = (args.redistribution_evidence, args.redistribution_signature)
        approval = None
        if any(path is not None for path in approval_paths):
            if (
                not (current_transaction or completed_promotion) or not verify_governance
                or audited_inputs is not None or None in approval_paths
            ):
                raise ValueError("explicit redistribution inputs require both files and an exact published promotion")
            evidence_path, signature_path = approval_paths
            assert evidence_path is not None and signature_path is not None
            evidence_bytes, evidence = read_json_object(evidence_path, "signed redistribution approval")
            signature_bytes, signature = read_json_object(signature_path, "redistribution approval signature")
            approval = (evidence_bytes, evidence, signature)
            audited_inputs = {
                evidence_path: hashlib.sha256(evidence_bytes).hexdigest(),
                signature_path: hashlib.sha256(signature_bytes).hexdigest(),
            }
        if audited_inputs is not None and not verify_governance:
            raise ValueError("audited input checks require verified governance")
        if args.published_release_id is not None and args.published_release_id < 1:
            raise ValueError("published release id must be positive")
        repository = normalize_repository(args.repository)
        sha = normalize_sha(args.sha)
        tag = normalize_tag(args.tag)
        matrix = read_json(MATRIX_PATH, "release matrix")
        standard_assets = expected_release_assets(matrix, tag=tag)
        if single_asset:
            asset = args.asset.absolute()
            if not safe_asset_name(asset.name) or asset.is_symlink() or not asset.is_file():
                raise ValueError("--asset must identify a regular file with its published name")
            local_assets = {asset.name: asset}
        else:
            local_assets, local_errors = local_release_assets(args.assets_dir)
            if local_errors:
                raise RuntimeError("; ".join(local_errors))

        if draft_transaction and args.published_release_id is not None:
            raise ValueError("draft and published numeric release ids are mutually exclusive")
        numeric_release_id = args.draft_release_id or args.published_release_id
        release_endpoint = (
            f"repos/{repository}/releases/{numeric_release_id}"
            if numeric_release_id is not None
            else f"repos/{repository}/releases/tags/{quote(tag, safe='')}"
        )
        release = run_gh_json(
            ["api", release_endpoint],
            "GitHub release metadata",
            60,
        )
        release = release_with_all_assets(
            release,
            repository=repository,
            tag=tag,
            expected_draft=draft_transaction,
            require_immutable=not draft_transaction,
            expected_release_id=numeric_release_id,
        )
        if approval is not None:
            policy_bytes, policy = read_json_object(POLICY_PATH, "release compliance policy")
            published_at = parse_timestamp(release.get("published_at"), "GitHub release published_at")
            approval_errors = check_redistribution_approval(
                *approval, policy_bytes, policy, repository, tag, sha, now=published_at,
            )
            if approval_errors:
                raise ValueError("; ".join(approval_errors))
        errors = check_release_asset_bytes(
            release,
            local_assets,
            repository=repository,
            tag=tag,
            required_standard_assets=standard_assets,
            expected_draft=draft_transaction,
            require_immutable=not draft_transaction,
            expected_release_id=numeric_release_id,
            verify_single_asset=single_asset,
        )
        if errors:
            raise RuntimeError("; ".join(errors))
        if args.recheck_draft_bytes:
            print(f"Verified {len(local_assets)} unchanged draft assets against the local inventory")
            return 0

        invocations_by_asset: dict[str, set[RunInvocation]] = {}
        for name in sorted(local_assets):
            path = local_assets[name]
            payload = verify_attestation(
                path,
                repository=repository,
                sha=sha,
                tag=tag,
            )
            invocations, attestation_errors = verified_run_invocations(
                payload,
                asset_name=name,
                asset_sha256=sha256_file(path),
                repository=repository,
                sha=sha,
                tag=tag,
            )
            if attestation_errors:
                errors.extend(attestation_errors)
            invocations_by_asset[name] = invocations

        common = common_run_invocations(invocations_by_asset)
        if verify_governance:
            assert args.governance_attestation is not None
            assert args.governance_signature is not None
            proof_invocations = verified_governance_invocations(
                args.governance_attestation,
                args.governance_signature,
                release=release,
                repository=repository,
                tag=tag,
                sha=sha,
            )
            common.intersection_update(proof_invocations)
            if not common:
                errors.append("governance proof and release assets must share the same promotion attempt")
        for path, digest in (audited_inputs or {}).items():
            invocations, attestation_errors = verified_run_invocations(
                verify_attestation(path, repository=repository, sha=sha, tag=tag),
                asset_name="signed redistribution approval input",
                asset_sha256=digest,
                repository=repository,
                sha=sha,
                tag=tag,
            )
            errors.extend(attestation_errors)
            common.intersection_update(invocations)
            if not common:
                errors.append("signed redistribution approval must share the successful promotion attempt")

        if not common:
            errors.append(
                "certified release assets do not share one certificate-bound release workflow "
                "run attempt"
            )
        if draft_transaction:
            expected = RunInvocation(
                repository,
                args.draft_transaction_run_id,
                args.draft_transaction_run_attempt,
            )
            if expected not in common:
                errors.append(
                    "draft release assets are not all attested by the current exact-tag "
                    f"workflow run attempt {expected.url}"
                )
            if errors:
                raise RuntimeError("; ".join(dict.fromkeys(errors)))
            print(
                "draft release transaction provenance passed: "
                f"{len(local_assets)}/{len(local_assets)} draft bytes match and share "
                f"{expected.url}"
            )
            return 0
        if current_transaction:
            expected = RunInvocation(
                repository,
                args.current_transaction_run_id,
                args.current_transaction_run_attempt,
            )
            if expected not in common:
                errors.append(
                    "published transaction assets are not all attested by the current exact-tag "
                    f"promotion run attempt {expected.url}"
                )
            if errors:
                raise RuntimeError("; ".join(dict.fromkeys(errors)))
            print(
                "published release transaction provenance passed: "
                f"{len(local_assets)}/{len(local_assets)} immutable release bytes match and "
                f"share {expected.url}; completed-success certification remains external"
            )
            return 0
        if completed_promotion:
            expected = RunInvocation(repository, *completed_values)
            common.intersection_update({expected})
            if not common:
                errors.append(f"release assets and governance proof do not share the triggering promotion {expected.url}")
        successful: list[RunInvocation] = []
        publication_errors: list[str] = []
        for invocation in sorted(common, reverse=True):
            payload = run_gh_json(
                [
                    "api",
                    f"repos/{repository}/actions/runs/{invocation.run_id}/"
                    f"attempts/{invocation.attempt}",
                ],
                f"release workflow run {invocation.url}",
                60,
            )
            run_errors = check_release_run(
                payload,
                invocation=invocation,
                repository=repository,
                sha=sha,
                tag=tag,
            )
            if verify_governance and not run_errors:
                run_errors = check_publication_in_run(release, payload)
                publication_errors.extend(run_errors)
            if not run_errors:
                successful.append(invocation)
        if common and not successful:
            errors.extend(publication_errors)
            errors.append(
                "no common certificate-bound release workflow run attempt completed successfully "
                f"for exact source SHA {sha}"
            )
        if errors:
            raise RuntimeError("; ".join(dict.fromkeys(errors)))
        if check_published_at is not None:
            published_at = parse_timestamp(release.get("published_at"), "GitHub release published_at")
            errors = check_published_at(published_at)
            if errors:
                raise RuntimeError("; ".join(dict.fromkeys(errors)))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release provenance: {exc}", file=sys.stderr)
        return 1

    chosen = max(successful)
    if single_asset:
        print(
            f"release asset provenance passed: {asset.name} matches immutable {tag} "
            f"and its completed promotion run {chosen.url}"
        )
        return 0
    print(
        "release provenance passed: "
        f"{len(local_assets)}/{len(local_assets)} published bytes match; "
        f"{len(local_assets)}/{len(local_assets)} certified assets share {chosen.url}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Match downloaded release bytes to GitHub and verify exact-SHA SLSA provenance "
            "for an entire release directory or one published asset."
        )
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--assets-dir", type=Path, help="verify the complete published or draft inventory")
    inputs.add_argument("--asset", type=Path, help="verify one downloaded file from an immutable published release")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--draft-release-id", type=int)
    parser.add_argument("--published-release-id", type=int)
    parser.add_argument("--draft-transaction-run-id", type=int)
    parser.add_argument("--draft-transaction-run-attempt", type=int)
    parser.add_argument("--recheck-draft-bytes", action="store_true")
    parser.add_argument("--current-transaction-run-id", type=int)
    parser.add_argument("--current-transaction-run-attempt", type=int)
    parser.add_argument("--completed-promotion-run-id", type=int)
    parser.add_argument("--completed-promotion-run-attempt", type=int)
    parser.add_argument("--governance-attestation", type=Path)
    parser.add_argument("--governance-signature", type=Path)
    parser.add_argument("--redistribution-evidence", type=Path)
    parser.add_argument("--redistribution-signature", type=Path)
    return parser.parse_args(argv)


def verified_governance_invocations(
    attestation_path: Path,
    signature_path: Path,
    *,
    release: dict[str, Any],
    repository: str,
    tag: str,
    sha: str,
) -> set[RunInvocation]:
    _, policy = read_json_object(POLICY_PATH, "release compliance policy")
    attestation_bytes, attestation = read_json_object(attestation_path, "tag governance attestation")
    signature_bytes, signature = read_json_object(signature_path, "tag governance signature")
    governance_policy = policy.get("tag_governance_attestation")
    if not isinstance(governance_policy, dict) or governance_policy.get("state") != "enforced":
        raise ValueError("tag governance attestation policy is not enforced")
    verify_tag_governance_signature(attestation_bytes, signature, policy)
    published_at = parse_timestamp(release.get("published_at"), "GitHub release published_at")
    if published_at > datetime.now(timezone.utc):
        raise ValueError("GitHub release published_at must not be in the future")
    errors = check_tag_governance_attestation(
        attestation,
        policy=policy,
        repository=repository,
        tag=tag,
        sha=sha,
        now=published_at,
    )
    if errors:
        raise ValueError("; ".join(errors))

    proofs: dict[str, set[RunInvocation]] = {}
    for label, path, data in (
        ("tag governance attestation", attestation_path, attestation_bytes),
        ("tag governance signature", signature_path, signature_bytes),
    ):
        payload = verify_attestation(path, repository=repository, sha=sha, tag=tag)
        invocations, errors = verified_run_invocations(
            payload,
            asset_name=label,
            asset_sha256=hashlib.sha256(data).hexdigest(),
            repository=repository,
            sha=sha,
            tag=tag,
        )
        if errors:
            raise ValueError("; ".join(errors))
        proofs[label] = invocations
    common = common_run_invocations(proofs)
    matching = set()
    for invocation in common:
        try:
            require_transaction(
                attestation,
                promotion_transaction(invocation.run_id, invocation.attempt, "publish", release.get("id")),
            )
        except ValueError:
            continue
        matching.add(invocation)
    if not matching:
        raise ValueError("governance proof and signature must bind the published release and promotion attempt")
    return matching


def check_publication_in_run(release: dict[str, Any], run: dict[str, Any]) -> list[str]:
    published_at = parse_timestamp(release.get("published_at"), "GitHub release published_at")
    run_started_at = parse_timestamp(run.get("run_started_at"), "GitHub run run_started_at")
    run_updated_at = parse_timestamp(run.get("updated_at"), "GitHub run updated_at")
    if not run_started_at <= published_at <= run_updated_at:
        return ["release publication time falls outside the common successful promotion attempt"]
    return []


def normalize_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise ValueError("repository must be owner/name")
    return repository


def normalize_sha(value: str) -> str:
    sha = value.strip().lower()
    if SHA_RE.fullmatch(sha) is None:
        raise ValueError("sha must be a full 40-character hexadecimal commit id")
    return sha


def normalize_tag(value: str) -> str:
    tag = value.strip()
    if TAG_RE.fullmatch(tag) is None:
        raise ValueError("tag must look like vX.Y.Z")
    return tag


def read_json(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def run_gh_json(args: list[str], label: str, timeout: int) -> Any:
    gh = shutil.which("gh")
    if gh is None:
        raise RuntimeError(
            "GitHub CLI is required for cryptographic release provenance verification"
        )
    environment = os.environ.copy()
    environment.update({"GH_PROMPT_DISABLED": "1", "GH_PAGER": "cat", "NO_COLOR": "1"})
    try:
        completed = subprocess.run(
            [gh, *args],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{label} command failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:2000]
        raise RuntimeError(f"{label} command failed: {detail or 'no diagnostic output'}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label} did not return valid JSON") from exc


def local_release_assets(root: Path) -> tuple[dict[str, Path], list[str]]:
    if root.is_symlink():
        return {}, [f"release asset directory must not be a symlink: {root}"]
    if not root.is_dir():
        return {}, [f"release asset directory missing: {root}"]
    errors: list[str] = []
    assets: dict[str, Path] = {}
    casefolded: dict[str, str] = {}
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_symlink():
            errors.append(f"release asset must not be a symlink: {path.name}")
            continue
        if not path.is_file():
            errors.append(f"release asset directory must contain root files only: {path.name}")
            continue
        folded = path.name.casefold()
        if folded in casefolded:
            errors.append(
                "release asset names collide on case-insensitive filesystems: "
                f"{casefolded[folded]!r}, {path.name!r}"
            )
            continue
        casefolded[folded] = path.name
        assets[path.name] = path
    if not assets:
        errors.append("release asset directory must contain files")
    return assets, errors


def release_with_all_assets(
    release: Any,
    *,
    repository: str,
    tag: str,
    expected_draft: bool,
    require_immutable: bool,
    expected_release_id: int | None,
) -> dict[str, Any]:
    errors = release_identity_errors(
        release,
        tag=tag,
        expected_draft=expected_draft,
        require_immutable=require_immutable,
        expected_release_id=expected_release_id,
    )
    if errors:
        raise ValueError("; ".join(errors))
    release_id = release.get("id")
    if type(release_id) is not int or release_id < 1:
        raise ValueError("GitHub release metadata must contain a positive ID")
    pages = run_gh_json(
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repository}/releases/{release_id}/assets?per_page=100",
        ],
        "GitHub release asset list",
        60,
    )
    if not isinstance(pages, list) or not pages or not all(isinstance(page, list) for page in pages):
        raise ValueError("GitHub release assets must be paginated lists")
    return {**release, "assets": [item for page in pages for item in page]}


def release_identity_errors(
    release: Any,
    *,
    tag: str,
    expected_draft: bool,
    require_immutable: bool,
    expected_release_id: int | None,
) -> list[str]:
    if not isinstance(release, dict):
        return ["GitHub release metadata must be a JSON object"]
    errors: list[str] = []
    if release.get("tag_name") != tag:
        errors.append(f"production release tag_name must be {tag!r}")
    if expected_release_id is not None and release.get("id") != expected_release_id:
        state = "draft" if expected_draft else "published"
        errors.append(f"{state} release id must be {expected_release_id}")
    if release.get("draft") is not expected_draft:
        state = "be a draft" if expected_draft else "not be a draft"
        errors.append(f"production release transaction must {state}")
    if release.get("prerelease") is not False:
        errors.append("published production release must not be a prerelease")
    if require_immutable and release.get("immutable") is not True:
        errors.append("published production release must have GitHub immutable releases enabled")
    return errors


def check_release_asset_bytes(
    release: Any,
    local_assets: dict[str, Path],
    *,
    repository: str,
    tag: str,
    required_standard_assets: set[str],
    expected_draft: bool = False,
    require_immutable: bool = True,
    expected_release_id: int | None = None,
    verify_single_asset: bool = False,
) -> list[str]:
    if verify_single_asset and (expected_draft or not require_immutable or len(local_assets) != 1):
        return ["single-asset verification requires one file from an immutable published release"]
    errors = release_identity_errors(
        release,
        tag=tag,
        expected_draft=expected_draft,
        require_immutable=require_immutable,
        expected_release_id=expected_release_id,
    )
    if not isinstance(release, dict):
        return errors
    raw_assets = release.get("assets")
    if not isinstance(raw_assets, list):
        return [*errors, "published release assets must be a list"]

    remote: dict[str, dict[str, Any]] = {}
    folded_names: dict[str, str] = {}
    asset_ids: set[int] = set()
    for index, item in enumerate(raw_assets):
        if not isinstance(item, dict):
            errors.append(f"published release asset at index {index} must be an object")
            continue
        name = item.get("name")
        if not safe_asset_name(name):
            errors.append(f"published release asset name must be an exact safe file name: {name!r}")
            continue
        assert isinstance(name, str)
        folded = name.casefold()
        if folded in folded_names:
            errors.append(
                "published release contains duplicate or case-colliding asset names: "
                f"{folded_names[folded]!r}, {name!r}"
            )
            continue
        folded_names[folded] = name
        remote[name] = item
        if expected_draft:
            asset_id = item.get("id")
            if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id < 1:
                errors.append(f"draft release asset {name} must have a positive API id")
            elif asset_id in asset_ids:
                errors.append(f"draft release asset API id is duplicated: {asset_id}")
            else:
                asset_ids.add(asset_id)
                expected_api_url = (
                    f"https://api.github.com/repos/{repository}/releases/assets/{asset_id}"
                )
                if item.get("url") != expected_api_url:
                    errors.append(
                        f"draft release asset {name} API url must be {expected_api_url!r}"
                    )

    local_names = set(local_assets)
    remote_names = set(remote)
    inventory_names = remote_names if verify_single_asset else local_names
    missing_standard = sorted(required_standard_assets - inventory_names)
    if missing_standard:
        location = "published" if verify_single_asset else "local"
        errors.append(f"{location} release assets missing standard files: {missing_standard}")
    if local_names != remote_names:
        missing_remote = sorted(local_names - remote_names)
        missing_local = sorted(remote_names - local_names)
        if missing_remote:
            errors.append(f"published release missing downloaded local files: {missing_remote}")
        if missing_local and not verify_single_asset:
            errors.append(f"downloaded release directory missing published files: {missing_local}")

    for name in sorted(local_names & remote_names):
        path = local_assets[name]
        item = remote[name]
        size = path.stat().st_size
        digest = sha256_file(path)
        if size <= 0:
            errors.append(f"local release asset must be non-empty: {name}")
        if item.get("state") != "uploaded":
            errors.append(f"published release asset {name} state must be 'uploaded'")
        if item.get("size") != size:
            errors.append(
                f"published release asset {name} size must match downloaded bytes: "
                f"expected {size}, got {item.get('size')!r}"
            )
        if item.get("digest") != f"sha256:{digest}":
            errors.append(
                f"published release asset {name} digest must match downloaded bytes: "
                f"expected sha256:{digest}, got {item.get('digest')!r}"
            )
        if not expected_draft:
            expected_url = (
                f"https://github.com/{repository}/releases/download/{tag}/"
                f"{quote(name, safe='')}"
            )
            if item.get("browser_download_url") != expected_url:
                errors.append(
                    f"published release asset {name} browser_download_url must be {expected_url!r}"
                )
    return errors


def safe_asset_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


def verify_attestation(path: Path, *, repository: str, sha: str, tag: str) -> Any:
    return run_gh_json(
        [
            "attestation",
            "verify",
            str(path),
            "--repo",
            repository,
            "--signer-workflow",
            f"{repository}/{RELEASE_WORKFLOW}",
            "--source-digest",
            sha,
            "--source-ref",
            f"refs/tags/{tag}",
            "--predicate-type",
            PREDICATE_TYPE,
            "--deny-self-hosted-runners",
            "--limit",
            "100",
            "--format",
            "json",
        ],
        f"SLSA provenance verification for {path.name}",
        120,
    )


def verified_run_invocations(
    payload: Any,
    *,
    asset_name: str,
    asset_sha256: str,
    repository: str,
    sha: str,
    tag: str,
) -> tuple[set[RunInvocation], list[str]]:
    if not isinstance(payload, list) or not payload:
        return set(), [f"{asset_name} attestation verification returned no results"]
    required_ref = f"refs/tags/{tag}"
    accepted: set[RunInvocation] = set()
    rejected: list[str] = []
    for index, item in enumerate(payload):
        prefix = f"{asset_name} attestation result {index}"
        if not isinstance(item, dict):
            rejected.append(f"{prefix} must be an object")
            continue
        verification = item.get("verificationResult")
        if not isinstance(verification, dict):
            rejected.append(f"{prefix} missing verificationResult")
            continue
        timestamps = verification.get("verifiedTimestamps")
        if not isinstance(timestamps, list) or not timestamps:
            rejected.append(f"{prefix} has no verified transparency/timestamp witness")
            continue
        signature = verification.get("signature")
        certificate = signature.get("certificate") if isinstance(signature, dict) else None
        if not isinstance(certificate, dict):
            rejected.append(f"{prefix} missing verified certificate")
            continue
        if certificate_value(certificate, "sourceRepositoryURI") != f"https://github.com/{repository}":
            rejected.append(f"{prefix} source repository URI is not exact")
            continue
        if str(certificate_value(certificate, "sourceRepositoryDigest")).lower() != sha:
            rejected.append(f"{prefix} source repository digest is not {sha}")
            continue
        source_ref = certificate_value(certificate, "sourceRepositoryRef")
        if source_ref != required_ref:
            rejected.append(
                f"{prefix} source repository ref must be {required_ref!r}, "
                f"got {source_ref!r}"
            )
            continue
        if certificate_value(certificate, "runnerEnvironment") != "github-hosted":
            rejected.append(f"{prefix} runner environment must be github-hosted")
            continue
        trigger = certificate_value(certificate, "buildTrigger", "githubWorkflowTrigger")
        if trigger != "workflow_dispatch":
            rejected.append(
                f"{prefix} build trigger must be an exact-tag release promotion dispatch"
            )
            continue
        if not statement_has_digest(verification.get("statement"), asset_sha256):
            rejected.append(f"{prefix} statement does not contain the downloaded asset digest")
            continue
        raw_invocation = certificate_value(
            certificate,
            "runInvocationURI",
            "runnerInvocationURI",
        )
        invocation = parse_run_invocation(raw_invocation, repository)
        if invocation is None:
            rejected.append(f"{prefix} has invalid certificate-bound run invocation URI")
            continue
        accepted.add(invocation)
    if accepted:
        return accepted, []
    detail = "; ".join(rejected[:5])
    return set(), [f"{asset_name} has no acceptable exact-SHA release attestation: {detail}"]


def certificate_value(certificate: dict[str, Any], *names: str) -> Any:
    wanted = {name.casefold() for name in names}
    for key, value in certificate.items():
        if isinstance(key, str) and key.casefold() in wanted:
            return value
    return None


def statement_has_digest(statement: Any, digest: str) -> bool:
    if not isinstance(statement, dict):
        return False
    if statement.get("predicateType") != PREDICATE_TYPE:
        return False
    subjects = statement.get("subject")
    if not isinstance(subjects, list):
        return False
    return any(
        isinstance(subject, dict)
        and isinstance(subject.get("digest"), dict)
        and subject["digest"].get("sha256") == digest
        for subject in subjects
    )


def parse_run_invocation(value: Any, repository: str) -> RunInvocation | None:
    if not isinstance(value, str):
        return None
    match = RUN_INVOCATION_RE.fullmatch(value)
    if match is None or match.group(1).casefold() != repository.casefold():
        return None
    return RunInvocation(repository=repository, run_id=int(match.group(2)), attempt=int(match.group(3)))


def common_run_invocations(
    invocations_by_asset: dict[str, set[RunInvocation]],
) -> set[RunInvocation]:
    if not invocations_by_asset:
        return set()
    values = iter(invocations_by_asset.values())
    common = set(next(values))
    for invocations in values:
        common.intersection_update(invocations)
    return common


def check_release_run(
    payload: Any,
    *,
    invocation: RunInvocation,
    repository: str,
    sha: str,
    tag: str,
) -> list[str]:
    if not isinstance(payload, dict):
        return [f"release workflow run {invocation.url} metadata must be an object"]
    errors: list[str] = []
    expected = {
        "id": invocation.run_id,
        "run_attempt": invocation.attempt,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
    }
    for key, value in expected.items():
        actual = payload.get(key)
        if key == "head_sha" and isinstance(actual, str):
            actual = actual.lower()
        if actual != value:
            errors.append(
                f"release workflow run {invocation.url} {key} must be {value!r}, got {actual!r}"
            )
    if not workflow_path_matches(payload.get("path"), RELEASE_WORKFLOW, tag):
        errors.append(
            f"release workflow run {invocation.url} path must identify "
            f"{RELEASE_WORKFLOW!r} at tag {tag!r}"
        )
    if payload.get("event") != "workflow_dispatch":
        errors.append(
            f"release workflow run {invocation.url} event must be workflow_dispatch"
        )
    if payload.get("head_branch") != tag:
        errors.append(
            f"release workflow run {invocation.url} head_branch must be {tag!r}"
        )
    for key in ("repository", "head_repository"):
        row = payload.get(key)
        full_name = row.get("full_name") if isinstance(row, dict) else None
        if not isinstance(full_name, str) or full_name.casefold() != repository.casefold():
            errors.append(
                f"release workflow run {invocation.url} {key}.full_name must be {repository!r}"
            )
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def workflow_path_matches(value: Any, workflow: str, tag: str) -> bool:
    return isinstance(value, str) and value in {
        workflow,
        f"{workflow}@{tag}",
        f"{workflow}@refs/tags/{tag}",
    }


if __name__ == "__main__":
    raise SystemExit(main())
