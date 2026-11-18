from __future__ import annotations

import re
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


def test_signing_inventory_matches_the_production_workflow() -> None:
    workflow = (preconditions.ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    preflight = workflow.split("  release-preflight:\n", 1)[1].split("      - name: Detect release signing readiness\n", 1)
    assert "    environment: release\n" in preflight[0]
    step = preflight[1].split("      - name:", 1)[0]
    configured = set(re.findall(r"\$\{\{ secrets\.(ROW_[A-Z0-9_]+) \}\}", step))
    checked = {name for line in re.findall(r"(?m)^ +for name in ([^;]+); do$", step) for name in line.split()}
    assert configured == checked == preconditions.RELEASE_SIGNING_SECRETS


@pytest.mark.parametrize("missing", [set(), {"ROW_WINDOWS_TIMESTAMP_URL", "ROW_MACOS_NOTARY_KEY_ID"}])
def test_signing_uses_the_protected_environment_and_reports_missing_names(monkeypatch, missing) -> None:
    names = (preconditions.RELEASE_SIGNING_SECRETS - missing) | {"UNRELATED_ENTRY"}

    def get_json(url, token, *, api_version):
        assert url == f"{REPOSITORY_URL}/environments/release/secrets?per_page=100"
        assert token == "fixture" and api_version == "2026-03-10"
        return {"total_count": len(names), "secrets": [{"name": name} for name in names]}, {}

    monkeypatch.setattr(preconditions, "get_json", get_json)
    if missing:
        with pytest.raises(RuntimeError, match="missing signing secrets") as exc:
            preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")
        assert all(name in str(exc.value) for name in missing)
        assert "UNRELATED_ENTRY" not in str(exc.value)
    else:
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")


@pytest.mark.parametrize(("payload", "error"), [
    ({"total_count": 101, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": 2, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": True, "secrets": [{"name": "KEY"}]}, "incomplete"),
    ({"total_count": 1, "secrets": [{"name": "private value"}]}, "malformed"),
    ({"total_count": 2, "secrets": [{"name": "KEY"}, {"name": "KEY"}]}, "duplicate"),
])
def test_signing_rejects_unverified_inventory(monkeypatch, payload, error) -> None:
    monkeypatch.setattr(preconditions, "get_json", lambda *args, **kwargs: (payload, {}))
    with pytest.raises(RuntimeError, match=error):
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")


@pytest.mark.parametrize("dedicated_token", [False, True])
def test_signing_command_can_run_before_other_pre_tag_checks(monkeypatch, capsys, dedicated_token) -> None:
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("GITHUB_TOKEN", "default-fixture")
    monkeypatch.delenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", raising=False)
    if dedicated_token:
        monkeypatch.setenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", "signing-fixture")
    calls = []
    monkeypatch.setattr(preconditions, "require_signing_secret_inventory", lambda *args: calls.append(args))
    assert preconditions.main(["signing", "--repository", REPOSITORY]) == 0
    assert calls == [(API_ROOT, REPOSITORY, "signing-fixture" if dedicated_token else "default-fixture")]
    assert "signing passed" in capsys.readouterr().out


def test_signing_access_failure_reports_the_required_permission(monkeypatch) -> None:
    def denied(*args, **kwargs):
        raise RuntimeError("remote response body")

    monkeypatch.setattr(preconditions, "get_json", denied)
    with pytest.raises(RuntimeError, match="Environments read access") as exc:
        preconditions.require_signing_secret_inventory(API_ROOT, REPOSITORY, "fixture")
    assert "remote response body" not in str(exc.value)


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


@pytest.mark.parametrize(("tag_created_during_audit", "signing_ready"), [(False, True), (True, True), (False, False)])
def test_pre_tag_cli_keeps_checks_source_bound_and_rechecks_refs(
    monkeypatch, capsys, tag_created_during_audit, signing_ready,
) -> None:
    calls = []
    coordinates = ("--repository", REPOSITORY, "--branch", "main")
    monkeypatch.setenv("GITHUB_API_URL", API_ROOT)
    monkeypatch.setenv("GITHUB_TOKEN", "namespace-token")
    monkeypatch.setenv("GH_TOKEN", "governance-token")
    monkeypatch.setenv("ROW_RELEASE_SIGNING_INVENTORY_TOKEN", "signing-token")
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

    def check_signing(*args):
        calls.append(("signing", *args))
        if not signing_ready:
            raise RuntimeError("missing signing secrets in the release environment")

    monkeypatch.setattr(preconditions, "check_remote_pre_tag_refs", check_remote)
    monkeypatch.setattr(preconditions, "run_release_check", check_script)
    monkeypatch.setattr(preconditions, "require_immutable_enabled", lambda *args: calls.append(("immutable", *args)))
    monkeypatch.setattr(preconditions, "require_signing_secret_inventory", check_signing)
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
        ("signing", API_ROOT, REPOSITORY, "signing-token"),
    ]
    captured = capsys.readouterr()
    if not signing_ready:
        assert result == 1
        assert "missing signing secrets in the release environment" in captured.err
        assert captured.out == ""
        assert calls == expected
        return

    expected += [
        ("check_python315_ci_evidence.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--sha", RELEASE_SHA),
        ("check_repository_governance.py", *coordinates, "--release-tag", RELEASE_TAG),
        ("check_platform_evidence_runner_readiness.py", "--repository", REPOSITORY, "--require-goal-targets", "--require-idle"),
        ("namespace", API_ROOT, REPOSITORY, RELEASE_TAG, "namespace-token", True),
    ]
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
