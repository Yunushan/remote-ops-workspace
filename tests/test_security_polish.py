import importlib.util
import json
import sys
from pathlib import Path

from remote_ops_workspace.redaction import REDACTED, redact_value


def load_security_checker():
    path = Path("scripts/check_security_polish.py")
    spec = importlib.util.spec_from_file_location("check_security_polish", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_security_polish.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_security_polish"] = module
    spec.loader.exec_module(module)
    return module


def test_redaction_covers_assignment_style_and_url_secrets() -> None:
    payload = {
        "command": [
            "tool",
            "--password=inline-secret",
            "--token",
            "next-token",
            "/p:rdp-secret",
            "endpoint=https://admin:url-secret@example.com",
            "Authorization: Bearer bearer-secret",
        ],
        "credential_ref": "prod/router-password",
    }

    serialized = json.dumps(redact_value(payload))

    assert REDACTED in serialized
    for secret in (
        "inline-secret",
        "next-token",
        "rdp-secret",
        "url-secret",
        "bearer-secret",
        "prod/router-password",
    ):
        assert secret not in serialized


def test_security_polish_checker_passes() -> None:
    checker = load_security_checker()
    assert checker.main() == 0


def test_security_polish_rejects_xp_contract_security_flag_drift() -> None:
    checker = load_security_checker()
    baseline = _security_baseline()
    xp_contract = _xp_contract()
    xp_contract["required_security_flags"]["weak_crypto_global_default"] = True

    errors = checker.check_legacy_security_policy(
        baseline=baseline,
        xp_contract=xp_contract,
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
    )

    assert any("XP native evidence contract required_security_flags must match" in error for error in errors)


def test_security_polish_rejects_platform_checker_security_flag_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": True,
        },
    )

    assert any("platform verified evidence REQUIRED_XP_SECURITY_FLAGS must match" in error for error in errors)


def test_security_polish_rejects_xp_patch_evidence_drift() -> None:
    checker = load_security_checker()
    xp_contract = _xp_contract()
    xp_contract["required_security_patch_evidence"]["cve_patch_reviewed"] = False

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=xp_contract,
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
    )

    assert any(
        "XP native evidence contract required_security_patch_evidence must match" in error
        for error in errors
    )


def test_security_polish_rejects_missing_xp_security_smoke_id() -> None:
    checker = load_security_checker()
    xp_contract = _xp_contract()
    xp_contract["required_smoke_ids"] = [
        item
        for item in xp_contract["required_smoke_ids"]
        if item != "modern_defaults_unchanged"
    ]

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=xp_contract,
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
    )

    assert "XP native evidence contract must require smoke id: modern_defaults_unchanged" in errors


def _security_baseline() -> dict[str, object]:
    return json.loads(Path("configs/security_baseline.json").read_text(encoding="utf-8"))


def _xp_contract() -> dict[str, object]:
    return json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
