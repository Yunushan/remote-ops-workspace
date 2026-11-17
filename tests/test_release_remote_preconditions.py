from __future__ import annotations

from subprocess import CompletedProcess

import pytest

from scripts import check_release_remote_preconditions as preconditions

API_ROOT = "https://api.github.com"
REPOSITORY = "owner/repo"
REPOSITORY_URL = f"{API_ROOT}/repos/{REPOSITORY}"
RELEASES_PATH = "/repositories/123/releases"
FIRST_PAGE = f"{REPOSITORY_URL}/releases?per_page=100"
SECOND_PAGE = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=2"
RELEASE_TAG = "v1.2.3"
RELEASE_SHA = "a" * 40


@pytest.mark.parametrize("collision", [False, True])
@pytest.mark.parametrize("require_push", [False, True])
def test_namespace_checks_numeric_pages_and_accepts_terminal_link(monkeypatch, collision, require_push) -> None:
    previous_page = f"{API_ROOT}{RELEASES_PATH}?per_page=100&page=1"
    responses = {
        REPOSITORY_URL: ({"id": 123, "full_name": "Owner/Repo", "permissions": {"push": True}}, {}),
        FIRST_PAGE: ([], {"Link": f'<{SECOND_PAGE}>; rel="next", <{SECOND_PAGE}>; rel="last"'}),
        SECOND_PAGE: (
            [{"tag_name": "v1.2.3" if collision else "v1.2.2", "draft": True}],
            {"Link": f'<{previous_page}>; rel="prev", <{previous_page}>; rel="first"'},
        ),
    }
    visited = []

    def get_json(url, token, *, api_version):
        assert token == "fixture"
        assert api_version == "2022-11-28"
        visited.append(url)
        return responses[url]

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if collision:
        with pytest.raises(RuntimeError, match="already uses tag/name"):
            preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture", require_push=require_push)
    else:
        preconditions.require_unused_namespace(API_ROOT, REPOSITORY, "v1.2.3", "fixture", require_push=require_push)
    assert visited == list(responses)


@pytest.mark.parametrize(
    "next_url",
    [
        SECOND_PAGE.replace("api.github.com", "elsewhere.example"),
        SECOND_PAGE.replace("/123/", "/999/"),
        SECOND_PAGE.replace("page=2", "page=3"),
        SECOND_PAGE.replace("per_page=100", "per_page=1"),
    ],
)
def test_next_release_page_must_stay_in_the_exact_repository_and_sequence(next_url) -> None:
    with pytest.raises(RuntimeError, match="expected HTTPS endpoint or page"):
        preconditions.next_page_url(
            f'<{next_url}>; rel="next"',
            current=FIRST_PAGE,
            allowed_paths={"/repos/owner/repo/releases", RELEASES_PATH},
            expected_page=2,
        )


@pytest.mark.parametrize("permissions", [None, {"push": False}, {"push": 1}, {"pull": True}])
def test_pre_tag_namespace_requires_draft_visibility_before_listing(monkeypatch, permissions) -> None:
    def get_json(url, _token, *, api_version):
        assert url == REPOSITORY_URL
        assert api_version == "2022-11-28"
        return {"id": 123, "full_name": REPOSITORY, "permissions": permissions}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    with pytest.raises(RuntimeError, match="repository push access so draft releases are visible"):
        preconditions.require_unused_namespace(API_ROOT, REPOSITORY, RELEASE_TAG, "fixture", require_push=True)


@pytest.mark.parametrize(("tag_status", "error"), [(0, "already exists"), (128, "could not establish"), (2, None)])
def test_local_pre_tag_requires_matching_head_and_definite_tag_absence(monkeypatch, tag_status, error) -> None:
    responses = iter([CompletedProcess([], 0, RELEASE_SHA + "\n"), CompletedProcess([], tag_status, "")])
    monkeypatch.setattr(preconditions, "run_git", lambda *args: next(responses))
    if error is not None:
        with pytest.raises(RuntimeError, match=error):
            preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)
    else:
        preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)


@pytest.mark.parametrize("head_status", [0, 128])
def test_local_pre_tag_rejects_other_head_or_unreadable_checkout(monkeypatch, head_status) -> None:
    def run_git(*args):
        assert args == ("rev-parse", "--verify", "HEAD^{commit}")
        return CompletedProcess([], head_status, "b" * 40 + "\n")

    monkeypatch.setattr(preconditions, "run_git", run_git)
    with pytest.raises(RuntimeError, match="HEAD must match the selected SHA"):
        preconditions.check_local_pre_tag_refs(RELEASE_TAG, RELEASE_SHA)


@pytest.mark.parametrize("outcome", ["tip", "ancestor", "unrelated", "unknown", "existing-tag", "unreachable", "bad-ref"])
def test_remote_pre_tag_binds_qualified_history_without_accepting_an_existing_tag(monkeypatch, outcome) -> None:
    branch = "refs/heads/main"
    tag_ref = f"refs/tags/{RELEASE_TAG}"
    live_tip = RELEASE_SHA if outcome == "tip" else "b" * 40
    stdout = f"{live_tip}\t{branch}\n"
    if outcome == "existing-tag":
        stdout += f"{RELEASE_SHA}\t{tag_ref}\n"
    if outcome == "bad-ref":
        stdout = "wrong format\n"
    errors = {
        "unrelated": "must be on remote main",
        "unknown": "could not verify remote main ancestry",
        "existing-tag": "remote tag .* already exists",
        "unreachable": "could not verify the remote branch",
        "bad-ref": "could not identify the live main commit",
    }

    def run_git(*args):
        if args[0] == "ls-remote":
            assert args == ("ls-remote", "--exit-code", "--refs", "--", f"https://github.com/{REPOSITORY}.git", branch, tag_ref)
            return CompletedProcess([], 128 if outcome == "unreachable" else 0, stdout)
        assert args == ("merge-base", "--is-ancestor", RELEASE_SHA, live_tip)
        assert outcome in {"ancestor", "unrelated", "unknown"}
        return CompletedProcess([], {"ancestor": 0, "unrelated": 1, "unknown": 128}[outcome], "")

    monkeypatch.setattr(preconditions, "run_git", run_git)
    if outcome in errors:
        with pytest.raises(RuntimeError, match=errors[outcome]):
            preconditions.check_remote_pre_tag_refs(REPOSITORY, RELEASE_TAG, RELEASE_SHA)
    else:
        preconditions.check_remote_pre_tag_refs(REPOSITORY, RELEASE_TAG, RELEASE_SHA)


@pytest.mark.parametrize("tag_created_during_audit", [False, True])
def test_pre_tag_cli_keeps_checks_source_bound_and_rechecks_refs(monkeypatch, capsys, tag_created_during_audit) -> None:
    calls = []
    coordinates = ("--repository", REPOSITORY, "--branch", "main")
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("GITHUB_TOKEN", "namespace-token")
    monkeypatch.setenv("GH_TOKEN", "governance-token")
    monkeypatch.setenv("ROW_RELEASE_IMMUTABILITY_TOKEN", "immutability-token")
    monkeypatch.setenv("ROW_PLATFORM_RUNNER_INVENTORY_TOKEN", "runner-token")
    monkeypatch.setattr(preconditions, "check_local_pre_tag_refs", lambda *args: calls.append(("local", *args)))

    def check_remote(*args):
        event = ("remote", *args)
        if event in calls and tag_created_during_audit:
            raise RuntimeError("remote tag created during audit")
        calls.append(event)

    def check_script(script, *args, env=None):
        calls.append((script, *args))
        if script == "check_platform_evidence_runner_readiness.py":
            assert env["GH_TOKEN"] == "runner-token"
        else:
            assert env is None

    monkeypatch.setattr(preconditions, "check_remote_pre_tag_refs", check_remote)
    monkeypatch.setattr(preconditions, "run_release_check", check_script)
    monkeypatch.setattr(preconditions, "require_immutable_enabled", lambda *args: calls.append(("immutable", *args)))
    monkeypatch.setattr(preconditions, "require_unused_namespace", lambda *args, require_push: calls.append(("namespace", *args, require_push)))

    result = preconditions.main(["pre-tag", "--repository", REPOSITORY, "--tag", RELEASE_TAG, "--sha", RELEASE_SHA])

    expected = [
        ("local", RELEASE_TAG, RELEASE_SHA),
        ("check_repository_cleanup.py", "--require-clean"),
        ("check_release_version.py", "--release-tag", RELEASE_TAG),
        ("check_release_maturity.py", "--release-tag", RELEASE_TAG),
        ("check_release_license_compliance.py", "--check-policy-only"),
        ("remote", REPOSITORY, RELEASE_TAG, RELEASE_SHA),
        ("immutable", API_ROOT, REPOSITORY, "immutability-token"),
        ("check_python315_ci_evidence.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--release-tag", RELEASE_TAG),
        ("check_platform_evidence_runner_readiness.py", "--repository", REPOSITORY, "--require-goal-targets", "--require-idle"),
        ("namespace", API_ROOT, REPOSITORY, RELEASE_TAG, "namespace-token", True),
    ]
    captured = capsys.readouterr()
    if tag_created_during_audit:
        assert result == 1
        assert "remote tag created during audit" in captured.err
        assert captured.out == ""
    else:
        expected.extend([
            ("remote", REPOSITORY, RELEASE_TAG, RELEASE_SHA),
            ("check_repository_cleanup.py", "--require-clean"),
            ("local", RELEASE_TAG, RELEASE_SHA),
        ])
        assert result == 0
        assert f"{REPOSITORY}@{RELEASE_SHA} and {RELEASE_TAG}" in captured.out
    assert calls == expected
