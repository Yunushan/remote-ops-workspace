from __future__ import annotations

import pytest

from scripts import check_python315_ci_evidence as evidence

SHA = "a" * 40


def _runs(
    *,
    conclusion: str | None = "success",
    run_id: int = 123,
    status: str = "completed",
) -> dict:
    runs = [
        {
            "id": run_id,
            "run_attempt": 1,
            "head_sha": SHA,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/ci.yml@main",
            "status": status,
            "conclusion": conclusion,
        }
    ]
    return {"total_count": len(runs), "workflow_runs": runs}


def _jobs(*, conclusion: str = "success") -> dict:
    jobs = [
        {
            "id": 456,
            "name": "Python 3.15 readiness",
            "status": "completed",
            "conclusion": conclusion,
        },
        {
            "id": 457,
            "name": "Native Windows readiness",
            "status": "completed",
            "conclusion": conclusion,
        },
    ]
    return {"total_count": len(jobs), "jobs": jobs}


def test_exact_successful_push_run_and_readiness_job_pass() -> None:
    run, errors = evidence.select_exact_push_run(
        _runs(),
        repository="example/project",
        sha=SHA,
        branch="main",
    )

    assert errors == []
    assert run is not None and run["id"] == 123
    assert evidence.validate_readiness_job(_jobs()) == []


def test_latest_matching_run_must_succeed() -> None:
    payload = _runs(run_id=123)
    payload["workflow_runs"].append(_runs(conclusion="failure", run_id=124)["workflow_runs"][0])
    payload["total_count"] = len(payload["workflow_runs"])

    run, errors = evidence.select_exact_push_run(
        payload,
        repository="example/project",
        sha=SHA,
        branch="main",
    )

    assert run is not None and run["id"] == 124
    assert any("conclusion must be success" in error for error in errors)


def test_pull_request_or_wrong_sha_cannot_satisfy_release_evidence() -> None:
    payload = _runs()
    payload["workflow_runs"][0]["event"] = "pull_request"

    run, errors = evidence.select_exact_push_run(
        payload,
        repository="example/project",
        sha=SHA,
        branch="main",
    )

    assert run is None
    assert any("no .github/workflows/ci.yml push run matches" in error for error in errors)


def test_readiness_job_must_be_unique_and_successful() -> None:
    failed = evidence.validate_readiness_job(_jobs(conclusion="skipped"))
    duplicate = _jobs()
    duplicate["jobs"].append(dict(duplicate["jobs"][0], id=789))
    duplicate["total_count"] = len(duplicate["jobs"])

    assert any("conclusion must be success" in error for error in failed)
    assert any("expected exactly one" in error for error in evidence.validate_readiness_job(duplicate))


def test_native_windows_readiness_job_is_required_and_must_succeed() -> None:
    missing = _jobs()
    missing["jobs"] = [
        job for job in missing["jobs"] if job["name"] != "Native Windows readiness"
    ]
    missing["total_count"] = len(missing["jobs"])
    failed = _jobs()
    failed["jobs"][1]["conclusion"] = "failure"

    assert any(
        "expected exactly one 'Native Windows readiness'" in error
        for error in evidence.validate_readiness_job(missing)
    )
    assert any(
        "Native Windows readiness conclusion must be success" in error
        for error in evidence.validate_readiness_job(failed)
    )


def test_urls_bind_workflow_sha_branch_run_and_attempt() -> None:
    runs_url = evidence.workflow_runs_url(
        "https://api.github.test",
        repository="example/project",
        workflow="ci.yml",
        sha=SHA,
        branch="main",
    )
    jobs_url = evidence.workflow_jobs_url(
        "https://api.github.test",
        repository="example/project",
        run_id=123,
        run_attempt=2,
        page=3,
    )

    assert "/repos/example/project/actions/workflows/ci.yml/runs?" in runs_url
    assert f"head_sha={SHA}" in runs_url
    assert "branch=main" in runs_url
    assert "event=push" in runs_url
    assert jobs_url.endswith("/actions/runs/123/attempts/2/jobs?per_page=100&page=3")
    assert "filter=" not in jobs_url


def test_waits_for_missing_then_queued_exact_sha_run_until_success() -> None:
    responses = iter(
        [
            {"total_count": 0, "workflow_runs": []},
            _runs(status="queued", conclusion=None),
            _runs(),
        ]
    )
    clock = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    run = evidence.wait_for_successful_exact_push_run(
        lambda: next(responses),
        repository="example/project",
        sha=SHA,
        branch="main",
        wait_seconds=30,
        poll_interval_seconds=5,
        sleep_fn=sleep,
        monotonic_fn=lambda: clock[0],
    )

    assert run["id"] == 123
    assert sleeps == [5, 5]


def test_wait_for_exact_sha_run_is_bounded_and_fail_closed() -> None:
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    with pytest.raises(RuntimeError, match="timed out after 10 seconds"):
        evidence.wait_for_successful_exact_push_run(
            lambda: _runs(status="in_progress", conclusion=None),
            repository="example/project",
            sha=SHA,
            branch="main",
            wait_seconds=10,
            poll_interval_seconds=6,
            sleep_fn=sleep,
            monotonic_fn=lambda: clock[0],
        )


def test_collects_all_attempt_job_pages_before_validating_readiness() -> None:
    ordinary_jobs = [
        {
            "id": index,
            "name": f"ordinary-{index}",
            "status": "completed",
            "conclusion": "success",
        }
        for index in range(1, 149)
    ]
    python_readiness = {
        "id": 149,
        "name": "Python 3.15 readiness",
        "status": "completed",
        "conclusion": "success",
    }
    native_windows_readiness = {
        "id": 150,
        "name": "Native Windows readiness",
        "status": "completed",
        "conclusion": "success",
    }
    pages = {
        1: {"total_count": 150, "jobs": ordinary_jobs[:100]},
        2: {
            "total_count": 150,
            "jobs": [
                *ordinary_jobs[100:],
                python_readiness,
                native_windows_readiness,
            ],
        },
    }
    requested_pages: list[int] = []

    def fetch_page(page: int) -> dict:
        requested_pages.append(page)
        return pages[page]

    payload = evidence.collect_paginated_attempt_jobs(fetch_page)

    assert requested_pages == [1, 2]
    assert payload["total_count"] == 150
    assert len(payload["jobs"]) == 150
    assert evidence.validate_readiness_job(payload) == []


def test_rejects_truncated_or_inconsistent_attempt_job_pages() -> None:
    truncated = {
        "total_count": 101,
        "jobs": [
            {
                "id": index,
                "name": f"ordinary-{index}",
                "status": "completed",
                "conclusion": "success",
            }
            for index in range(1, 100)
        ],
    }
    with pytest.raises(RuntimeError, match="ended before total_count"):
        evidence.collect_paginated_attempt_jobs(lambda _page: truncated)

    pages = {
        1: {
            "total_count": 101,
            "jobs": [
                {
                    "id": index,
                    "name": f"ordinary-{index}",
                    "status": "completed",
                    "conclusion": "success",
                }
                for index in range(1, 101)
            ],
        },
        2: {
            "total_count": 102,
            "jobs": [
                {
                    "id": 101,
                    "name": "Python 3.15 readiness",
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        },
    }
    with pytest.raises(RuntimeError, match="total_count changed"):
        evidence.collect_paginated_attempt_jobs(lambda page: pages[page])
