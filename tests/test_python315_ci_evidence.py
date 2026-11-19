from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

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
            "repository": {"full_name": "example/project"},
            "head_repository": {"full_name": "example/project"},
            "status": status,
            "conclusion": conclusion,
        }
    ]
    return {"total_count": len(runs), "workflow_runs": runs}


def _jobs(*, conclusion: str = "success") -> dict:
    jobs = [
        {
            "id": job_id,
            "run_id": 123,
            "run_attempt": 1,
            "head_sha": SHA,
            "name": name,
            "status": "completed",
            "conclusion": conclusion,
            "labels": [runner] if runner else [],
            "steps": [
                {"name": step, "status": "completed", "conclusion": "success"}
                for step in steps
            ],
        }
        for job_id, (name, (runner, steps)) in enumerate(evidence.REQUIRED_CI_JOBS.items(), 456)
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
    assert evidence.validate_readiness_job(_jobs(), run=run) == []


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


@pytest.mark.parametrize(("field", "value"), [
    ("repository", {"full_name": "other/project"}),
    ("head_repository", {"full_name": "fork/project"}),
    ("head_repository", None),
])
def test_ci_evidence_rejects_a_run_without_the_exact_repository_identity(field, value) -> None:
    payload = _runs(status="queued", conclusion=None)
    payload["workflow_runs"][0][field] = value
    run, errors = evidence.select_exact_push_run(
        payload, repository="example/project", sha=SHA, branch="main",
    )

    assert run is None
    assert errors == [f"matching CI workflow run {field}.full_name must match example/project"]


@pytest.mark.parametrize(("path", "matches"), [
    (".github/workflows/ci.yml", True),
    (".github/workflows/ci.yml@main", True),
    (".github/workflows/ci.yml@refs/heads/main", True),
    (".github/workflows/ci.yml@refs/heads/other", False),
    (".github/workflows/ci.yml@refs/tags/main", False),
])
def test_ci_evidence_binds_workflow_path_to_the_expected_branch(path, matches) -> None:
    payload = _runs()
    payload["workflow_runs"][0]["path"] = path
    run, errors = evidence.select_exact_push_run(
        payload, repository="Example/Project", sha=SHA, branch="main",
    )

    assert (run is not None) is matches
    assert (not errors) is matches


def test_readiness_job_must_be_unique_and_successful() -> None:
    run = _runs()["workflow_runs"][0]
    failed = evidence.validate_readiness_job(_jobs(conclusion="skipped"), run=run)
    duplicate = _jobs()
    duplicate["jobs"].append(dict(duplicate["jobs"][0], id=789))
    duplicate["total_count"] = len(duplicate["jobs"])

    assert any("conclusion must be success" in error for error in failed)
    assert any(
        "expected exactly one" in error
        for error in evidence.validate_readiness_job(duplicate, run=run)
    )


def test_native_windows_readiness_job_is_required_and_must_succeed() -> None:
    run = _runs()["workflow_runs"][0]
    missing = _jobs()
    missing["jobs"] = [
        job for job in missing["jobs"] if job["name"] != "Native Windows readiness"
    ]
    missing["total_count"] = len(missing["jobs"])
    failed = _jobs()
    failed["jobs"][1]["conclusion"] = "failure"

    assert any(
        "expected exactly one 'Native Windows readiness'" in error
        for error in evidence.validate_readiness_job(missing, run=run)
    )
    assert any(
        "Native Windows readiness conclusion must be success" in error
        for error in evidence.validate_readiness_job(failed, run=run)
    )


@pytest.mark.parametrize(("field", "value"), [
    ("run_id", 124),
    ("run_attempt", 2),
    ("run_attempt", True),
    ("head_sha", "b" * 40),
    ("head_sha", None),
])
def test_successful_readiness_jobs_must_bind_the_selected_run(field, value) -> None:
    run = _runs()["workflow_runs"][0]
    jobs = _jobs()
    jobs["jobs"][1][field] = value

    assert evidence.validate_readiness_job(jobs, run=run) == [
        f"Native Windows readiness {field} must match the selected CI run",
    ]



def test_successful_aggregates_do_not_cover_a_missing_runtime_host() -> None:
    jobs = _jobs()
    name = "Python 3.15 optional dependencies, GUI, and build on ubuntu-24.04-arm"
    jobs["jobs"] = [job for job in jobs["jobs"] if job["name"] != name]
    jobs["total_count"] = len(jobs["jobs"])

    assert evidence.validate_readiness_job(jobs, run=_runs()["workflow_runs"][0]) == [
        f"expected exactly one {name!r} job in the accepted run, found 0",
    ]


def test_runtime_job_must_report_the_expected_host_and_attempt() -> None:
    jobs = _jobs()
    name = "Python 3.15 optional dependencies, GUI, and build on windows-11-arm"
    job = next(job for job in jobs["jobs"] if job["name"] == name)
    job.update(labels=["windows-2025-vs2026"], run_attempt=2)

    assert evidence.validate_readiness_job(jobs, run=_runs()["workflow_runs"][0]) == [
        f"{name} run_attempt must match the selected CI run",
        f"{name} must report runner label 'windows-11-arm'",
    ]


@pytest.mark.parametrize(("step_count", "expected"), [
    (0, "must report exactly one"),
    (1, "must complete successfully"),
    (2, "must report exactly one"),
])
def test_readiness_requires_one_successful_frozen_cli_step(step_count, expected) -> None:
    jobs = _jobs()
    name = "Python 3.15 optional dependencies, GUI, and build on macos-15-intel"
    step = "Build and launch a real Python 3.15 frozen CLI executable"
    job = next(job for job in jobs["jobs"] if job["name"] == name)
    job["steps"] = [entry for entry in job["steps"] if entry["name"] != step] + [
        {"name": step, "status": "completed", "conclusion": "skipped"}
        for _ in range(step_count)
    ]

    errors = evidence.validate_readiness_job(jobs, run=_runs()["workflow_runs"][0])
    assert len(errors) == 1 and name in errors[0] and step in errors[0] and expected in errors[0]


def test_native_windows_job_requires_conpty_and_paint_steps() -> None:
    jobs = _jobs()
    name = "Native Windows PyQt6 render and interactions"
    job = next(job for job in jobs["jobs"] if job["name"] == name)
    missing = {
        "Verify real Windows ConPTY terminal transport",
        "Capture native Windows terminal tab-switch paint turns",
    }
    job["steps"] = [step for step in job["steps"] if step["name"] not in missing]

    assert set(evidence.validate_readiness_job(jobs, run=_runs()["workflow_runs"][0])) == {
        f"{name} must report exactly one {step!r} step" for step in missing
    }


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
    assert jobs_url.endswith("/actions/runs/123/attempts/2/jobs?per_page=20&page=3")
    assert "filter=" not in jobs_url


def test_actions_request_retries_transient_server_errors(monkeypatch) -> None:
    url = "https://api.github.test/actions"
    first_error = HTTPError(url, 502, "Bad Gateway", {}, BytesIO())
    second_error = HTTPError(url, 503, "Service Unavailable", {}, BytesIO())
    responses = iter([first_error, second_error, BytesIO(b'{"jobs": []}')])
    requested: list[str] = []
    sleeps: list[int] = []

    def open_response(request, *, timeout):
        assert timeout == 30
        requested.append(request.full_url)
        response = next(responses)
        if isinstance(response, HTTPError):
            raise response
        return response

    monkeypatch.setattr(evidence, "urlopen", open_response)
    monkeypatch.setattr(evidence.time, "sleep", sleeps.append)

    assert evidence.fetch_json(url, token="fixture") == {"jobs": []}
    assert requested == [url, url, url]
    assert sleeps == [1, 2]
    assert first_error.fp.closed and second_error.fp.closed


@pytest.mark.parametrize(("status", "expected_sleeps"), [(403, []), (503, [1, 2])])
def test_actions_request_fails_after_allowed_attempts(monkeypatch, status, expected_sleeps) -> None:
    sleeps: list[int] = []

    def refuse_request(request, *, timeout):
        raise HTTPError(request.full_url, status, "GitHub API error", {}, BytesIO())

    monkeypatch.setattr(evidence, "urlopen", refuse_request)
    monkeypatch.setattr(evidence.time, "sleep", sleeps.append)

    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        evidence.fetch_json("https://api.github.test/actions", token="fixture")
    assert sleeps == expected_sleeps


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
        for index in range(1, 29)
    ]
    all_jobs = ordinary_jobs + _jobs()["jobs"]
    pages = {
        1: {"total_count": len(all_jobs), "jobs": all_jobs[:20]},
        2: {"total_count": len(all_jobs), "jobs": all_jobs[20:]},
    }
    requested_pages: list[int] = []

    def fetch_page(page: int) -> dict:
        requested_pages.append(page)
        return pages[page]

    payload = evidence.collect_paginated_attempt_jobs(fetch_page)

    assert requested_pages == [1, 2]
    assert payload["total_count"] == len(all_jobs)
    assert payload["jobs"] == all_jobs
    assert evidence.validate_readiness_job(payload, run=_runs()["workflow_runs"][0]) == []


def test_rejects_truncated_or_inconsistent_attempt_job_pages() -> None:
    truncated = {
        "total_count": 21,
        "jobs": [
            {
                "id": index,
                "name": f"ordinary-{index}",
                "status": "completed",
                "conclusion": "success",
            }
            for index in range(1, 20)
        ],
    }
    with pytest.raises(RuntimeError, match="ended before total_count"):
        evidence.collect_paginated_attempt_jobs(lambda _page: truncated)

    pages = {
        1: {
            "total_count": 21,
            "jobs": [
                {
                    "id": index,
                    "name": f"ordinary-{index}",
                    "status": "completed",
                    "conclusion": "success",
                }
                for index in range(1, 21)
            ],
        },
        2: {
            "total_count": 22,
            "jobs": [
                {
                    "id": 21,
                    "name": "Python 3.15 readiness",
                    "status": "completed",
                    "conclusion": "success",
                }
            ],
        },
    }
    with pytest.raises(RuntimeError, match="total_count changed"):
        evidence.collect_paginated_attempt_jobs(lambda page: pages[page])
