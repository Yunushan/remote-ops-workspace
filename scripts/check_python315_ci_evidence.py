from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

EXPECTED_WORKFLOW_PATH = ".github/workflows/ci.yml"
EXPECTED_JOB_NAME = "Python 3.15 readiness"
EXPECTED_JOB_NAMES = (EXPECTED_JOB_NAME, "Native Windows readiness")
JOBS_PAGE_SIZE = 100
MAX_WAIT_SECONDS = 7200.0
MAX_POLL_INTERVAL_SECONDS = 300.0
WAITABLE_RUN_STATUSES = frozenset({"in_progress", "pending", "queued", "requested", "waiting"})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Require successful Python 3.15 and native Windows CI evidence "
            "for an exact commit."
        )
    )
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--sha", required=True, help="Exact release source commit SHA")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--workflow", default="ci.yml")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="Bounded time to wait for an exact-SHA push run to appear and complete.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=15.0,
        help="Delay between exact-SHA workflow-run queries while waiting.",
    )
    parser.add_argument("--runs-json", type=Path, help="Offline workflow-runs fixture")
    parser.add_argument("--jobs-json", type=Path, help="Offline workflow-jobs fixture")
    return parser.parse_args(argv)


def normalize_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if repository.count("/") != 1 or any(not part for part in repository.split("/")):
        raise ValueError("repository must be owner/name")
    return repository


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def fetch_json(url: str, *, token: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "remote-ops-workspace-release-preflight",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"GitHub Actions request failed with HTTP {exc.code}") from exc
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"GitHub Actions request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("GitHub Actions response must be a JSON object")
    return value


def select_exact_push_run(
    payload: dict[str, Any],
    *,
    repository: str,
    sha: str,
    branch: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    raw_runs = payload.get("workflow_runs")
    if not isinstance(raw_runs, list):
        return None, ["workflow-runs response must contain workflow_runs"]
    total_count = payload.get("total_count")
    if not _nonnegative_int(total_count):
        return None, ["workflow-runs response must contain a non-negative integer total_count"]
    if total_count != len(raw_runs):
        return None, [
            "workflow-runs response is incomplete or inconsistent: "
            f"total_count={total_count}, received={len(raw_runs)}"
        ]
    expected_sha = sha.lower()
    candidates = [
        run
        for run in raw_runs
        if isinstance(run, dict)
        and str(run.get("head_sha", "")).lower() == expected_sha
        and run.get("head_branch") == branch
        and run.get("event") == "push"
        and _workflow_path_matches(run.get("path"))
    ]
    if not candidates:
        return None, [
            f"no {EXPECTED_WORKFLOW_PATH} push run matches {repository}@{branch} SHA {sha}"
        ]
    valid_ids = [run for run in candidates if _positive_int(run.get("id"))]
    if not valid_ids:
        return None, ["matching CI workflow runs must have positive integer ids"]
    run = max(valid_ids, key=lambda item: int(item["id"]))
    errors: list[str] = []
    if not _positive_int(run.get("run_attempt")):
        errors.append("matching CI workflow run must have a positive run_attempt")
    if run.get("status") != "completed":
        errors.append(f"matching CI workflow run status must be completed, got {run.get('status')!r}")
    if run.get("conclusion") != "success":
        errors.append(
            f"matching CI workflow run conclusion must be success, got {run.get('conclusion')!r}"
        )
    return run, errors


def wait_for_successful_exact_push_run(
    fetch_runs: Callable[[], dict[str, Any]],
    *,
    repository: str,
    sha: str,
    branch: str,
    wait_seconds: float,
    poll_interval_seconds: float,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    _validate_wait_settings(wait_seconds, poll_interval_seconds)
    deadline = monotonic_fn() + wait_seconds
    while True:
        run, errors = select_exact_push_run(
            fetch_runs(),
            repository=repository,
            sha=sha,
            branch=branch,
        )
        if run is not None and not errors:
            return run
        if not _run_evidence_is_waitable(run, errors):
            raise RuntimeError("; ".join(errors))
        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            detail = "; ".join(errors)
            raise RuntimeError(
                f"timed out after {wait_seconds:g} seconds waiting for exact-SHA CI evidence: "
                f"{detail}"
            )
        delay = min(poll_interval_seconds, remaining)
        print(
            "Python 3.15 and native Windows CI evidence pending; "
            f"retrying in {delay:g} seconds ({'; '.join(errors)})",
            flush=True,
        )
        sleep_fn(delay)


def validate_readiness_job(payload: dict[str, Any]) -> list[str]:
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        return ["workflow-jobs response must contain jobs"]
    total_count = payload.get("total_count")
    if not _nonnegative_int(total_count):
        return ["workflow-jobs response must contain a non-negative integer total_count"]
    if total_count != len(raw_jobs):
        return [
            "workflow-jobs response is incomplete or inconsistent: "
            f"total_count={total_count}, received={len(raw_jobs)}"
        ]
    job_ids = [job.get("id") for job in raw_jobs if isinstance(job, dict)]
    if len(job_ids) != len(raw_jobs) or any(not _positive_int(job_id) for job_id in job_ids):
        return ["workflow-jobs response must contain objects with positive integer ids"]
    if len(set(job_ids)) != len(job_ids):
        return ["workflow-jobs response contains duplicate job ids"]
    errors: list[str] = []
    for expected_name in EXPECTED_JOB_NAMES:
        matches = [
            job
            for job in raw_jobs
            if isinstance(job, dict) and job.get("name") == expected_name
        ]
        if len(matches) != 1:
            errors.append(
                f"expected exactly one {expected_name!r} job in the accepted run, "
                f"found {len(matches)}"
            )
            continue
        job = matches[0]
        if job.get("status") != "completed":
            errors.append(
                f"{expected_name} status must be completed, got {job.get('status')!r}"
            )
        if job.get("conclusion") != "success":
            errors.append(
                f"{expected_name} conclusion must be success, "
                f"got {job.get('conclusion')!r}"
            )
    return errors


def collect_paginated_attempt_jobs(
    fetch_page: Callable[[int], dict[str, Any]],
) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    expected_total: int | None = None
    page = 1
    while True:
        payload = fetch_page(page)
        raw_jobs = payload.get("jobs")
        total_count = payload.get("total_count")
        if not isinstance(raw_jobs, list):
            raise RuntimeError(f"workflow-jobs page {page} must contain jobs")
        if not _nonnegative_int(total_count):
            raise RuntimeError(
                f"workflow-jobs page {page} must contain a non-negative integer total_count"
            )
        if expected_total is None:
            expected_total = total_count
        elif total_count != expected_total:
            raise RuntimeError(
                "workflow-jobs pagination total_count changed: "
                f"expected {expected_total}, page {page} reported {total_count}"
            )
        if len(raw_jobs) > JOBS_PAGE_SIZE:
            raise RuntimeError(
                f"workflow-jobs page {page} exceeds requested page size {JOBS_PAGE_SIZE}"
            )
        for job in raw_jobs:
            if not isinstance(job, dict) or not _positive_int(job.get("id")):
                raise RuntimeError(
                    f"workflow-jobs page {page} must contain objects with positive integer ids"
                )
            job_id = int(job["id"])
            if job_id in seen_ids:
                raise RuntimeError(f"workflow-jobs pagination repeated job id {job_id}")
            seen_ids.add(job_id)
            jobs.append(job)
        if len(jobs) > expected_total:
            raise RuntimeError(
                "workflow-jobs pagination returned more jobs than total_count: "
                f"total_count={expected_total}, received={len(jobs)}"
            )
        if len(jobs) == expected_total:
            return {"total_count": expected_total, "jobs": jobs}
        if len(raw_jobs) < JOBS_PAGE_SIZE:
            raise RuntimeError(
                "workflow-jobs pagination ended before total_count: "
                f"total_count={expected_total}, received={len(jobs)}"
            )
        page += 1


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_wait_settings(wait_seconds: float, poll_interval_seconds: float) -> None:
    if not 0 <= wait_seconds <= MAX_WAIT_SECONDS:
        raise ValueError(f"--wait-seconds must be between 0 and {MAX_WAIT_SECONDS:g}")
    if not 0 < poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
        raise ValueError(
            "--poll-interval-seconds must be greater than 0 and no more than "
            f"{MAX_POLL_INTERVAL_SECONDS:g}"
        )


def _run_evidence_is_waitable(
    run: dict[str, Any] | None,
    errors: list[str],
) -> bool:
    if run is None:
        return len(errors) == 1 and errors[0].startswith(
            f"no {EXPECTED_WORKFLOW_PATH} push run matches"
        )
    return (
        _positive_int(run.get("run_attempt"))
        and run.get("status") in WAITABLE_RUN_STATUSES
        and run.get("conclusion") is None
    )


def _workflow_path_matches(value: Any) -> bool:
    return isinstance(value, str) and (
        value == EXPECTED_WORKFLOW_PATH or value.startswith(f"{EXPECTED_WORKFLOW_PATH}@")
    )


def workflow_runs_url(
    api_url: str,
    *,
    repository: str,
    workflow: str,
    sha: str,
    branch: str,
) -> str:
    query = urlencode(
        {
            "branch": branch,
            "event": "push",
            "head_sha": sha,
            "per_page": 100,
        }
    )
    return (
        f"{api_url.rstrip('/')}/repos/{repository}/actions/workflows/"
        f"{quote(workflow, safe='')}/runs?{query}"
    )


def workflow_jobs_url(
    api_url: str,
    *,
    repository: str,
    run_id: int,
    run_attempt: int,
    page: int = 1,
) -> str:
    query = urlencode({"per_page": JOBS_PAGE_SIZE, "page": page})
    return (
        f"{api_url.rstrip('/')}/repos/{repository}/actions/runs/{run_id}/attempts/"
        f"{run_attempt}/jobs?{query}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        repository = normalize_repository(args.repository)
        sha = args.sha.strip()
        if re.fullmatch(r"[0-9a-fA-F]{40}", sha) is None:
            raise ValueError("--sha must be a full 40-character hexadecimal commit id")
        branch = args.branch.strip()
        if not branch:
            raise ValueError("--branch must not be empty")
        _validate_wait_settings(args.wait_seconds, args.poll_interval_seconds)
        if bool(args.runs_json) != bool(args.jobs_json):
            raise ValueError("--runs-json and --jobs-json must be provided together")
        if args.runs_json:
            runs_payload = read_json(args.runs_json)
            run, errors = select_exact_push_run(
                runs_payload,
                repository=repository,
                sha=sha,
                branch=branch,
            )
            if errors or run is None:
                raise RuntimeError("; ".join(errors))
        else:
            token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
            if not token:
                raise ValueError("GITHUB_TOKEN or GH_TOKEN is required for live CI evidence")
            api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com")
            runs_url = workflow_runs_url(
                api_url,
                repository=repository,
                workflow=args.workflow,
                sha=sha,
                branch=branch,
            )
            run = wait_for_successful_exact_push_run(
                lambda: fetch_json(runs_url, token=token),
                repository=repository,
                sha=sha,
                branch=branch,
                wait_seconds=args.wait_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
        if args.jobs_json:
            jobs_payload = read_json(args.jobs_json)
        else:
            jobs_payload = collect_paginated_attempt_jobs(
                lambda page: fetch_json(
                    workflow_jobs_url(
                        api_url,
                        repository=repository,
                        run_id=int(run["id"]),
                        run_attempt=int(run["run_attempt"]),
                        page=page,
                    ),
                    token=token,
                )
            )
        job_errors = validate_readiness_job(jobs_payload)
        if job_errors:
            raise RuntimeError("; ".join(job_errors))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"Python 3.15 and native Windows CI evidence: {exc}", file=sys.stderr)
        return 1
    print(
        f"Python 3.15 and native Windows CI evidence passed: {repository}@{branch} "
        f"{sha} run {run['id']} attempt {run['run_attempt']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
