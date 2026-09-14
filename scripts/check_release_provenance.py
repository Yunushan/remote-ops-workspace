#!/usr/bin/env python3
"""Verify that downloaded release bytes came from one exact-tag release run.

The local publish-asset checker proves that an asset directory is internally
complete.  This checker closes the remaining remote boundary: every local file
must match GitHub's size and digest, and every asset in the certified inventory
must have SLSA provenance issued by the exact release workflow and source SHA.
Final verification requires one common completed successful run; the narrowly
scoped draft-transaction mode instead binds every draft asset to the current
tag-triggered run before the draft is promoted.
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
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_release_publish_assets import (  # noqa: E402
    MATRIX_PATH,
    expected_release_assets,
)

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


def main(argv: list[str] | None = None) -> int:
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
        if draft_transaction and current_transaction:
            raise ValueError("draft and published current-transaction modes are mutually exclusive")
        if args.published_release_id is not None and args.published_release_id < 1:
            raise ValueError("published release id must be positive")
        repository = normalize_repository(args.repository)
        sha = normalize_sha(args.sha)
        tag = normalize_tag(args.tag)
        matrix = read_json(MATRIX_PATH, "release matrix")
        standard_assets = expected_release_assets(matrix, tag=tag)
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
        errors = check_release_asset_bytes(
            release,
            local_assets,
            repository=repository,
            tag=tag,
            required_standard_assets=standard_assets,
            expected_draft=draft_transaction,
            require_immutable=not draft_transaction,
            expected_release_id=numeric_release_id,
        )
        if errors:
            raise RuntimeError("; ".join(errors))

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
        successful: list[RunInvocation] = []
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
            if not run_errors:
                successful.append(invocation)
        if common and not successful:
            errors.append(
                "no common certificate-bound release workflow run attempt completed successfully "
                f"for exact source SHA {sha}"
            )
        if errors:
            raise RuntimeError("; ".join(dict.fromkeys(errors)))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release provenance: {exc}", file=sys.stderr)
        return 1

    chosen = max(successful)
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
            "for every asset in the certified release inventory."
        )
    )
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--draft-release-id", type=int)
    parser.add_argument("--published-release-id", type=int)
    parser.add_argument("--draft-transaction-run-id", type=int)
    parser.add_argument("--draft-transaction-run-attempt", type=int)
    parser.add_argument("--current-transaction-run-id", type=int)
    parser.add_argument("--current-transaction-run-attempt", type=int)
    return parser.parse_args(argv)


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
    missing_standard = sorted(required_standard_assets - local_names)
    if missing_standard:
        errors.append(f"local release assets missing standard files: {missing_standard}")
    if local_names != remote_names:
        missing_remote = sorted(local_names - remote_names)
        missing_local = sorted(remote_names - local_names)
        if missing_remote:
            errors.append(f"published release missing downloaded local files: {missing_remote}")
        if missing_local:
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
