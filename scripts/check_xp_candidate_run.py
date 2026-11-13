"""Authenticate locally downloaded XP candidate evidence against GitHub Actions."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from check_platform_promotion_artifacts import check_zip_entry_safety, sha256_file
from check_xp_candidate_build_inputs import ENTRY_LIMIT, RECEIPT_LIMIT, check_build_inputs
from release_candidate_inventory import (
    GitHubClient,
    check_artifact_metadata,
    normalize_digest,
    normalize_repository,
    normalize_repository_from_api,
    normalize_sha,
    normalize_tag,
    positive_int,
    workflow_path_matches,
)

WORKFLOW = ".github/workflows/xp-legacy-candidate.yml"


def check_run(
    run: dict[str, Any], *, repository: str, tag: str, sha: str, run_id: int, attempt: int,
) -> None:
    expected = {
        "id": run_id,
        "run_attempt": attempt,
        "event": "push",
        "head_branch": tag,
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError("XP evidence must come from the successful exact-tag build attempt")
    if not workflow_path_matches(run.get("path"), WORKFLOW, tag):
        raise ValueError("XP evidence run does not use the legacy candidate workflow")
    if normalize_repository_from_api(run).casefold() != repository.casefold():
        raise ValueError("XP evidence run belongs to a different repository")


def check_tag(client: GitHubClient, tag: str, sha: str) -> None:
    ref = client.json(f"git/ref/tags/{tag}")
    if ref.get("ref") != f"refs/tags/{tag}":
        raise ValueError("GitHub returned a different XP release ref")
    target = ref["object"]
    for _ in range(8):
        actual = normalize_sha(target["sha"])
        if target.get("type") == "commit" and actual == sha:
            return
        if target.get("type") != "tag":
            break
        target = client.json(f"git/tags/{actual}")["object"]
    raise ValueError("the live XP release tag does not resolve to the expected source SHA")


def verify_archive(
    client: GitHubClient, path: Path, *, artifact_id: int, name: str, run_id: int, sha: str,
    started: datetime, ended: datetime,
) -> None:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= ENTRY_LIMIT:
        raise ValueError(f"XP artifact {name} must be a bounded regular ZIP file")
    metadata = client.json(f"actions/artifacts/{artifact_id}")
    digest = normalize_digest(metadata.get("digest"), "XP artifact digest")
    check_artifact_metadata(
        metadata, artifact_id=artifact_id, name=name, digest=digest, run_id=run_id, release_sha=sha,
    )
    created = datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
    if not started <= created <= ended:
        raise ValueError(f"XP artifact {name} was created outside the candidate job window")
    if metadata.get("size_in_bytes") != path.stat().st_size or digest != f"sha256:{sha256_file(path)}":
        raise ValueError(f"XP artifact {name} does not match the GitHub archive bytes")


def extract_expected(path: Path, dest: Path, limits: dict[str, int]) -> None:
    with zipfile.ZipFile(path) as bundle:
        members = bundle.infolist()
        if len(members) != len(limits) or {item.filename for item in members} != set(limits):
            raise ValueError(f"{path.name} does not contain the exact XP evidence files")
        errors = check_zip_entry_safety("XP candidate evidence", path.name, members)
        if errors:
            raise ValueError(errors[0])
        for item in members:
            if not 0 < item.file_size <= limits[item.filename]:
                raise ValueError(f"{item.filename} is outside its allowed size range")
            (dest / item.filename).write_bytes(bundle.read(item))


def verify_candidate(
    client: GitHubClient,
    *,
    repository: str,
    tag: str,
    sha: str,
    arch: str,
    run_id: int,
    attempt: int,
    candidate: Path,
    candidate_id: int,
    receipt: Path,
    receipt_id: int,
    assets_dir: Path,
) -> None:
    check_tag(client, tag, sha)
    run = client.json(f"actions/runs/{run_id}/attempts/{attempt}")
    check_run(run, repository=repository, tag=tag, sha=sha, run_id=run_id, attempt=attempt)
    jobs = client.json(f"actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")["jobs"]
    matching_jobs = [job for job in jobs if job.get("name") == f"Windows XP signed candidate ({arch})"]
    if len(matching_jobs) != 1:
        raise ValueError(f"XP build attempt must contain one {arch} candidate job")
    job = matching_jobs[0]
    expected_job = {
        "status": "completed", "conclusion": "success", "head_sha": sha,
        "run_id": run_id, "run_attempt": attempt,
    }
    verified_steps = [
        step for step in job.get("steps", [])
        if step.get("name") == "Verify XP candidate build receipt" and step.get("conclusion") == "success"
    ]
    if any(job.get(key) != value for key, value in expected_job.items()) or len(verified_steps) != 1:
        raise ValueError(f"XP {arch} job must successfully verify the receipt before upload")
    started = datetime.fromisoformat(verified_steps[0]["completed_at"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
    for prefix, path, artifact_id in (
        ("legacy-candidate", candidate, candidate_id),
        ("build-inputs", receipt, receipt_id),
    ):
        verify_archive(
            client, path, artifact_id=artifact_id, name=f"windows-xp-{prefix}-{arch}-{attempt}",
            run_id=run_id, sha=sha, started=started, ended=ended,
        )
    base = f"remote-ops-workspace-{tag}-windows-xp-{arch}-native"
    limits = {
        f"{base}.zip": ENTRY_LIMIT,
        f"{base}-manifest.json": RECEIPT_LIMIT,
        f"{base}-SHA256SUMS.txt": RECEIPT_LIMIT,
    }
    with tempfile.TemporaryDirectory(prefix="row-xp-evidence-") as temp:
        root = Path(temp).resolve()
        extracted = root / "candidate"
        extracted.mkdir()
        extract_expected(candidate, extracted, limits)
        extract_expected(receipt, root, {"xp-build-inputs.json": RECEIPT_LIMIT})
        errors = check_build_inputs(
            root / "xp-build-inputs.json", extracted, repository=repository, arch=arch,
            tag=tag, source_ref=f"refs/tags/{tag}", source_sha=sha, run_id=str(run_id),
            run_attempt=str(attempt),
        )
        if errors:
            raise ValueError("\n".join(errors))
        for name in limits:
            path = assets_dir / name
            if (
                path.is_symlink() or not path.is_file()
                or path.stat().st_size != (extracted / name).stat().st_size
                or sha256_file(path) != sha256_file(extracted / name)
            ):
                raise ValueError(f"{name} does not match the authenticated XP candidate")
    check_tag(client, tag, sha)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("x86", "x64"), required=True)
    for option in ("repository", "tag", "sha", "run-id", "attempt", "candidate-id", "receipt-id"):
        parser.add_argument(f"--{option}", required=True)
    for option in ("candidate", "receipt", "assets-dir"):
        parser.add_argument(f"--{option}", required=True, type=Path)
    args = parser.parse_args()
    try:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
        repository = normalize_repository(args.repository)
        sha = normalize_sha(args.sha)
        source = Path(__file__).resolve().parents[1]
        checkout = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True, check=True,
        )
        if checkout.stdout.strip() != sha:
            raise ValueError("check out the exact XP release commit before verifying its evidence")
        changes = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=source, capture_output=True, text=True, check=True,
        )
        if changes.stdout:
            raise ValueError("the XP release checkout has tracked changes")
        verify_candidate(
            GitHubClient(repository, token), repository=repository, tag=normalize_tag(args.tag),
            sha=sha, arch=args.arch, run_id=positive_int(args.run_id, "run ID"),
            attempt=positive_int(args.attempt, "run attempt"), candidate=args.candidate,
            candidate_id=positive_int(args.candidate_id, "candidate artifact ID"),
            receipt=args.receipt, receipt_id=positive_int(args.receipt_id, "receipt artifact ID"),
            assets_dir=args.assets_dir,
        )
    except (
        OSError, ValueError, KeyError, TypeError, AttributeError,
        RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile,
    ) as exc:
        print(f"XP candidate run: {exc}", file=sys.stderr)
        return 1
    print("XP release files match the authenticated candidate and build receipt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
