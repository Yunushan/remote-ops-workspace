from __future__ import annotations

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


def test_missing_review_and_signature_are_blocking() -> None:
    protection = _protection()
    protection["required_pull_request_reviews"] = None
    protection["required_signatures"] = {"enabled": False}
    errors = audit_protection(protection)
    assert "at least one required pull-request approval must be configured" in errors
    assert "signed commits must be enabled (required_signatures)" in errors


def test_missing_required_check_is_blocking() -> None:
    protection = _protection()
    protection["required_status_checks"]["contexts"].remove("CodeQL python")
    errors = audit_protection(protection)
    assert "required status check missing: CodeQL python" in errors
