from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from scripts import check_repository_governance as governance
from scripts.check_repository_governance import audit_check_runs, audit_protection

SHA = "a" * 40


def _protection() -> dict:
    contexts = list(governance.REQUIRED_CHECKS)
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": contexts,
            "checks": [
                {"context": name, "app_id": governance.GITHUB_ACTIONS_APP_ID}
                for name in contexts
            ],
        },
        "required_pull_request_reviews": {"required_approving_review_count": 1},
        "enforce_admins": {"enabled": True},
        "required_linear_history": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "required_signatures": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }


def _check_runs() -> dict:
    runs = [
        {
            "id": index,
            "name": name,
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "app": {
                "id": governance.GITHUB_ACTIONS_APP_ID,
                "slug": governance.GITHUB_ACTIONS_APP_SLUG,
            },
            "check_suite": {"id": 101 if "CodeQL" not in name else 102},
            "details_url": (
                "https://github.com/fixture/fixture/actions/runs/"
                f"{1001 if 'CodeQL' not in name else 1002}/job/{2000 + index}"
            ),
        }
        for index, name in enumerate(governance.REQUIRED_CHECKS, start=1)
    ]
    return {"total_count": len(runs), "check_runs": runs}


def _check_suites() -> dict:
    suites = [
        {
            "id": suite_id,
            "head_sha": SHA,
            "app": {
                "id": governance.GITHUB_ACTIONS_APP_ID,
                "slug": governance.GITHUB_ACTIONS_APP_SLUG,
            },
        }
        for suite_id in (101, 102)
    ]
    return {"total_count": len(suites), "check_suites": suites}


def _workflow_runs() -> dict:
    runs = [
        {
            "id": 1001,
            "check_suite_id": 101,
            "head_sha": SHA,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/ci.yml@main",
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": "fixture/fixture"},
            "head_repository": {"full_name": "fixture/fixture"},
        },
        {
            "id": 1002,
            "check_suite_id": 102,
            "head_sha": SHA,
            "head_branch": "main",
            "event": "push",
            "path": ".github/workflows/codeql.yml@main",
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": "fixture/fixture"},
            "head_repository": {"full_name": "fixture/fixture"},
        },
    ]
    return {"total_count": len(runs), "workflow_runs": runs}


def _audit_check_runs(
    payload: dict | None = None,
    *,
    suites: dict | None = None,
    workflows: dict | None = None,
    repository: str = "fixture/fixture",
) -> list[str]:
    return audit_check_runs(
        _check_runs() if payload is None else payload,
        SHA,
        check_suites_payload=_check_suites() if suites is None else suites,
        workflow_runs_payload=_workflow_runs() if workflows is None else workflows,
        repository=repository,
    )


def _tag_rulesets() -> dict:
    rulesets = [
        {
            "id": 501,
            "name": "immutable production tags",
            "target": "tag",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {"include": ["refs/tags/v*"], "exclude": []}
            },
            "rules": [{"type": "update"}, {"type": "deletion"}],
        }
    ]
    return {"total_count": len(rulesets), "rulesets": rulesets}


def test_complete_protection_passes() -> None:
    assert audit_protection(_protection()) == []


def test_missing_review_and_signature_are_allowed_by_default() -> None:
    protection = _protection()
    protection["required_pull_request_reviews"] = None
    protection["required_signatures"] = {"enabled": False}
    assert audit_protection(protection) == []


def test_missing_review_and_signature_are_blocking_in_strict_mode() -> None:
    protection = _protection()
    protection["required_pull_request_reviews"] = None
    protection["required_signatures"] = {"enabled": False}
    errors = audit_protection(protection, require_review=True, require_signed_commits=True)
    assert "at least one required pull-request approval must be configured" in errors
    assert "signed commits must be enabled (required_signatures)" in errors


def test_missing_required_check_is_blocking() -> None:
    protection = _protection()
    protection["required_status_checks"]["contexts"].remove("CodeQL python")
    protection["required_status_checks"]["checks"] = [
        item
        for item in protection["required_status_checks"]["checks"]
        if item["context"] != "CodeQL python"
    ]
    errors = audit_protection(protection)
    assert "required status check missing: CodeQL python" in errors


def test_missing_python315_readiness_check_is_blocking() -> None:
    protection = _protection()
    protection["required_status_checks"]["contexts"].remove("Python 3.15 readiness")
    protection["required_status_checks"]["checks"] = [
        item
        for item in protection["required_status_checks"]["checks"]
        if item["context"] != "Python 3.15 readiness"
    ]

    errors = audit_protection(protection)

    assert "required status check missing: Python 3.15 readiness" in errors


def test_missing_native_windows_readiness_check_is_blocking() -> None:
    protection = _protection()
    protection["required_status_checks"]["contexts"].remove("Native Windows readiness")
    protection["required_status_checks"]["checks"] = [
        item
        for item in protection["required_status_checks"]["checks"]
        if item["context"] != "Native Windows readiness"
    ]

    errors = audit_protection(protection)

    assert "required status check missing: Native Windows readiness" in errors


def test_required_status_check_must_be_bound_to_configured_app() -> None:
    protection = _protection()
    protection["required_status_checks"]["checks"][0]["app_id"] = 999999

    errors = audit_protection(protection)

    assert any(
        "Repository policy and lint must be bound to app_id 15368 (github-actions)"
        in error
        for error in errors
    )


def test_legacy_context_without_app_binding_is_rejected() -> None:
    protection = _protection()
    protection["required_status_checks"]["checks"] = []

    errors = audit_protection(protection)

    assert any("must have exactly one GitHub App binding; found 0" in error for error in errors)


def test_exact_sha_required_check_runs_pass() -> None:
    assert _audit_check_runs() == []


def test_same_name_check_from_wrong_app_cannot_satisfy_gate() -> None:
    payload = _check_runs()
    payload["check_runs"][0]["app"] = {"id": 999999, "slug": "lookalike-checks"}

    errors = _audit_check_runs(payload)

    assert any(
        "Repository policy and lint must come from app_id 15368 (github-actions)"
        in error
        for error in errors
    )


def test_check_suite_must_share_configured_app_and_sha() -> None:
    suites = _check_suites()
    suites["check_suites"][0]["app"] = {"id": 999999, "slug": "lookalike-checks"}
    suites["check_suites"][0]["head_sha"] = "b" * 40

    errors = _audit_check_runs(suites=suites)

    assert any("check suite 101 is not owned by app_id 15368" in error for error in errors)
    assert any(f"check suite 101 is not bound to SHA {SHA}" in error for error in errors)


def test_check_run_must_resolve_to_expected_successful_workflow() -> None:
    workflows = _workflow_runs()
    workflows["workflow_runs"][0]["path"] = ".github/workflows/lookalike.yml"
    workflows["workflow_runs"][0]["conclusion"] = "failure"

    errors = _audit_check_runs(workflows=workflows)

    assert any(
        "workflow run 1001 path must identify '.github/workflows/ci.yml' on 'main'"
        in error
        for error in errors
    )
    assert any("workflow run 1001 conclusion must be 'success'" in error for error in errors)


def test_check_run_rejects_details_url_from_another_repository() -> None:
    payload = _check_runs()
    payload["check_runs"][0]["details_url"] = (
        "https://github.com/attacker/lookalike/actions/runs/1001/job/2001"
    )

    errors = _audit_check_runs(payload)

    assert any("details_url is not a repository GitHub Actions job" in error for error in errors)


def test_exact_sha_must_be_full_length() -> None:
    with pytest.raises(ValueError, match="full 40-character"):
        governance.normalize_sha("abc123")


def test_exact_sha_required_check_run_must_exist() -> None:
    payload = _check_runs()
    payload["check_runs"] = payload["check_runs"][:-1]
    payload["total_count"] -= 1

    errors = _audit_check_runs(payload)

    assert f"required check run missing for SHA {SHA}: CodeQL javascript-typescript" in errors


def test_exact_sha_required_check_run_must_be_successful_and_completed() -> None:
    payload = _check_runs()
    payload["check_runs"][0]["status"] = "in_progress"
    payload["check_runs"][0]["conclusion"] = None

    errors = _audit_check_runs(payload)

    assert "required check run Repository policy and lint status must be completed" in errors[0]
    assert "required check run Repository policy and lint conclusion must be success" in errors[1]


def test_exact_sha_required_check_run_rejects_other_commit() -> None:
    payload = _check_runs()
    payload["check_runs"][0]["head_sha"] = "b" * 40

    errors = _audit_check_runs(payload)

    assert f"required check run Repository policy and lint is not bound to SHA {SHA}" in errors[0]


def test_exact_sha_check_run_response_must_be_complete() -> None:
    payload = _check_runs()
    payload["total_count"] += 1

    assert _audit_check_runs(payload) == [
        "check-runs response is incomplete or inconsistent: total_count=6, received=5"
    ]


def test_exact_sha_check_run_response_over_page_limit_fails_closed() -> None:
    payload = _check_runs()
    payload["check_runs"].extend(
        {
            "id": index,
            "name": f"non-required-{index}",
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
        }
        for index in range(6, 101)
    )
    payload["total_count"] = 101

    assert _audit_check_runs(payload) == [
        "check-runs response is incomplete or inconsistent: total_count=101, received=100"
    ]


def test_latest_required_check_run_controls_result() -> None:
    payload = _check_runs()
    payload["check_runs"].append(
        {
            "id": 100,
            "name": "Repository policy and lint",
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "failure",
            "app": {
                "id": governance.GITHUB_ACTIONS_APP_ID,
                "slug": governance.GITHUB_ACTIONS_APP_SLUG,
            },
            "check_suite": {"id": 101},
            "details_url": "https://github.com/fixture/fixture/actions/runs/1001/job/9999",
        }
    )
    payload["total_count"] += 1

    errors = _audit_check_runs(payload)

    assert errors == [
        "required check run Repository policy and lint conclusion must be success, got 'failure'"
    ]


def test_release_tag_requires_active_non_bypassable_update_and_deletion_rules() -> None:
    assert governance.audit_tag_rulesets(_tag_rulesets(), "v1.2.3") == []


def test_release_tag_ruleset_must_apply_to_exact_tag() -> None:
    payload = _tag_rulesets()
    payload["rulesets"][0]["conditions"]["ref_name"] = {
        "include": ["refs/tags/v2*"],
        "exclude": [],
    }

    assert governance.audit_tag_rulesets(payload, "v1.2.3") == [
        "no active tag ruleset applies to refs/tags/v1.2.3"
    ]


def test_release_tag_ruleset_rejects_bypass_actors_and_hidden_bypass_state() -> None:
    payload = _tag_rulesets()
    payload["rulesets"][0]["bypass_actors"] = [
        {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
    ]
    assert governance.audit_tag_rulesets(payload, "v1.2.3") == [
        "every active tag ruleset applying to refs/tags/v1.2.3 has bypass actors"
    ]

    del payload["rulesets"][0]["bypass_actors"]
    assert governance.audit_tag_rulesets(payload, "v1.2.3") == [
        "cannot prove release-tag immutability because applicable ruleset bypass_actors "
        "are hidden; use a token with ruleset write visibility"
    ]


def test_release_tag_ruleset_requires_both_update_and_deletion_rules() -> None:
    payload = _tag_rulesets()
    payload["rulesets"][0]["rules"] = [{"type": "update"}]

    assert governance.audit_tag_rulesets(payload, "v1.2.3") == [
        "release tag refs/tags/v1.2.3 is not protected against deletion"
    ]


def test_release_tag_ruleset_exclusion_wins_over_include() -> None:
    payload = _tag_rulesets()
    payload["rulesets"][0]["conditions"]["ref_name"]["exclude"] = [
        "refs/tags/v1.2.3"
    ]

    assert governance.audit_tag_rulesets(payload, "v1.2.3") == [
        "no active tag ruleset applies to refs/tags/v1.2.3"
    ]


def test_fetch_protection_uses_gh_after_python_tls_failure(monkeypatch) -> None:
    protection = _protection()
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(governance.shutil, "which", lambda name: "gh.exe")

    def fail_urlopen(*args, **kwargs):
        raise URLError("certificate verify failed")

    def fake_run(args, **kwargs):
        assert args[:3] == [
            "gh.exe",
            "api",
            "repos/example/project/branches/main/protection",
        ]
        assert kwargs["env"]["GH_TOKEN"] == "test-token"
        return SimpleNamespace(stdout=json.dumps(protection))

    monkeypatch.setattr(governance, "urlopen", fail_urlopen)
    monkeypatch.setattr(governance.subprocess, "run", fake_run)

    assert governance.fetch_protection("example/project", "main") == protection


def test_fetch_check_runs_uses_exact_sha_endpoint(monkeypatch) -> None:
    payload = _check_runs()
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(governance.shutil, "which", lambda name: "gh.exe")

    def fake_run(args, **kwargs):
        assert args[:3] == [
            "gh.exe",
            "api",
            f"repos/example/project/commits/{SHA}/check-runs?filter=latest&per_page=100",
        ]
        return SimpleNamespace(stdout=json.dumps(payload))

    monkeypatch.setattr(governance.subprocess, "run", fake_run)

    assert governance.fetch_check_runs("example/project", SHA) == payload


def test_fetch_check_suite_and_workflow_evidence_is_sha_and_branch_scoped(monkeypatch) -> None:
    seen: list[tuple[str, str]] = []

    def fake_fetch(url: str, *, label: str) -> dict:
        seen.append((url, label))
        return _check_suites() if label == "check-suites" else _workflow_runs()

    monkeypatch.setattr(governance, "_fetch_github_object", fake_fetch)

    assert governance.fetch_check_suites("example/project", SHA) == _check_suites()
    assert governance.fetch_workflow_runs("example/project", SHA, "main") == _workflow_runs()
    assert f"commits/{SHA}/check-suites?per_page=100" in seen[0][0]
    assert "branch=main" in seen[1][0]
    assert "event=push" in seen[1][0]
    assert f"head_sha={SHA}" in seen[1][0]


def test_fetch_tag_rulesets_loads_inherited_detailed_records(monkeypatch) -> None:
    list_urls: list[str] = []
    detail_urls: list[str] = []

    def fake_list(url: str, *, label: str) -> list[dict]:
        list_urls.append(url)
        return [{"id": 501, "name": "immutable production tags"}]

    def fake_object(url: str, *, label: str) -> dict:
        detail_urls.append(url)
        return _tag_rulesets()["rulesets"][0]

    monkeypatch.setattr(governance, "_fetch_github_list", fake_list)
    monkeypatch.setattr(governance, "_fetch_github_object", fake_object)

    assert governance.fetch_tag_rulesets("example/project") == _tag_rulesets()
    assert "includes_parents=true" in list_urls[0]
    assert "targets=tag" in list_urls[0]
    assert "/rulesets/501?includes_parents=true" in detail_urls[0]


def test_main_audits_offline_protection_and_exact_sha_check_runs(monkeypatch, capsys) -> None:
    protection_path = Path("protection.json")
    check_runs_path = Path("check-runs.json")
    check_suites_path = Path("check-suites.json")
    workflow_runs_path = Path("workflow-runs.json")
    tag_rulesets_path = Path("tag-rulesets.json")

    def fake_load_fixture(path: Path) -> dict:
        values = {
            protection_path: _protection(),
            check_runs_path: _check_runs(),
            check_suites_path: _check_suites(),
            workflow_runs_path: _workflow_runs(),
        }
        return values[path]

    monkeypatch.setattr(governance, "load_fixture", fake_load_fixture)
    monkeypatch.setattr(governance, "load_rulesets_fixture", lambda path: _tag_rulesets())

    result = governance.main(
        [
            "--protection-json",
            str(protection_path),
            "--check-runs-json",
            str(check_runs_path),
            "--check-suites-json",
            str(check_suites_path),
            "--workflow-runs-json",
            str(workflow_runs_path),
            "--sha",
            SHA,
            "--release-tag",
            "v1.2.3",
            "--tag-rulesets-json",
            str(tag_rulesets_path),
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert f"SHA {SHA}" in output
    assert "immutable-tag v1.2.3" in output
