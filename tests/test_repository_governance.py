from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.error import URLError

from scripts import check_repository_governance as governance
from scripts.check_repository_governance import audit_protection


def _protection() -> dict:
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": [
                "Repository policy and lint",
                "CodeQL python",
                "CodeQL javascript-typescript",
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
    errors = audit_protection(protection)
    assert "required status check missing: CodeQL python" in errors


def test_fetch_protection_uses_gh_after_python_tls_failure(monkeypatch) -> None:
    protection = _protection()
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(governance.shutil, "which", lambda name: "gh.exe")

    def fail_urlopen(*args, **kwargs):
        raise URLError("certificate verify failed")

    def fake_run(args, **kwargs):
        assert args[:3] == ["gh.exe", "api", "https://api.github.com/repos/example/project/branches/main/protection"]
        assert kwargs["env"]["GH_TOKEN"] == "test-token"
        return SimpleNamespace(stdout=json.dumps(protection))

    monkeypatch.setattr(governance, "urlopen", fail_urlopen)
    monkeypatch.setattr(governance.subprocess, "run", fake_run)

    assert governance.fetch_protection("example/project", "main") == protection
