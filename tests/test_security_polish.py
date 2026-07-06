import importlib.util
import json
import sys
from pathlib import Path

from remote_ops_workspace.models import Profile
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


def test_security_polish_rejects_protected_goal_security_boundary_drift() -> None:
    checker = load_security_checker()
    platform_targets = _platform_targets()
    platform_targets["protected_readiness_goal"]["security_boundary"]["modern_tls_minimum"] = "TLS 1.0"

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_targets=platform_targets,
    )

    assert any(
        "platform_targets protected_readiness_goal.security_boundary must match" in error
        and "TLS 1.2" in error
        for error in errors
    )


def test_security_polish_uses_explicit_empty_security_baseline() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline={},
        xp_contract=_xp_contract(),
    )

    assert "security_baseline preferred_tls must stay TLS 1.3" in errors
    assert "Windows XP security policy must not claim native operator-host support" in errors


def test_security_polish_uses_explicit_empty_xp_contract() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract={},
    )

    assert any("XP native evidence contract required_security_flags must match" in error for error in errors)
    assert (
        "XP native evidence contract required_security_patch_provenance_namespaces "
        "must define cve_review_reference"
    ) in errors
    assert (
        "XP native evidence contract required_security_patch_provenance_namespaces "
        "must define security_update_channel"
    ) in errors


def test_security_polish_uses_explicit_empty_platform_security_constants() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_required_flags={},
        platform_required_patch_evidence={},
    )

    assert any("platform verified evidence REQUIRED_XP_SECURITY_FLAGS must match" in error for error in errors)
    assert any("platform verified evidence REQUIRED_SECURITY_PATCH_EVIDENCE must match" in error for error in errors)


def test_security_polish_rejects_xp_platform_target_native_host_drift() -> None:
    checker = load_security_checker()
    platform_targets = _platform_targets()
    xp_row = next(
        item
        for item in platform_targets["windows_legacy_targets"]
        if item["version"] == "Windows XP"
    )
    xp_row["host_tier"] = "native-host-supported"

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_targets=platform_targets,
    )

    assert "platform_targets Windows XP host_tier must be 'remote-target-only', got 'native-host-supported'" in errors


def test_security_polish_rejects_xp_platform_target_weak_crypto_note_drift() -> None:
    checker = load_security_checker()
    platform_targets = _platform_targets()
    xp_row = next(
        item
        for item in platform_targets["windows_legacy_targets"]
        if item["version"] == "Windows XP"
    )
    xp_row["notes"] = [
        note
        for note in xp_row["notes"]
        if "Legacy SSH/RDP crypto is blocked globally" not in note
    ]

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_targets=platform_targets,
    )

    assert "platform_targets Windows XP notes must include: Legacy SSH/RDP crypto is blocked globally" in errors


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


def test_security_polish_rejects_linux_security_smoke_line_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_linux_security_smoke_lines=(
            "native installer smoke TLS minimum modern profiles: TLS 1.2",
            "native installer smoke legacy compatibility profile: isolated-opt-in",
            "native installer smoke legacy crypto scope: profile-only",
            "native installer smoke weak crypto global default: false",
            "native installer smoke modern defaults unchanged: true",
        ),
    )

    assert any(
        "platform verified evidence REQUIRED_LINUX_SECURITY_SMOKE_LINES must include" in error
        and "native installer smoke TLS preferred modern profiles: TLS 1.3" in error
        for error in errors
    )


def test_security_polish_rejects_linux_forbidden_security_smoke_line_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_forbidden_linux_security_smoke_lines=(
            "native installer smoke TLS minimum modern profiles: TLS 1.0",
            "native installer smoke TLS minimum modern profiles: TLS 1.1",
            "native installer smoke weak crypto global default: true",
        ),
    )

    assert any(
        "platform verified evidence FORBIDDEN_LINUX_SECURITY_SMOKE_LINES must include" in error
        and "native installer smoke modern defaults unchanged: false" in error
        for error in errors
    )


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


def test_security_polish_rejects_xp_patch_provenance_field_drift() -> None:
    checker = load_security_checker()
    xp_contract = _xp_contract()
    xp_contract["required_security_patch_provenance_fields"] = ["security_update_channel"]

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
        "XP native evidence contract required_security_patch_provenance_fields must match" in error
        for error in errors
    )


def test_security_polish_rejects_xp_patch_provenance_namespace_drift() -> None:
    checker = load_security_checker()
    xp_contract = _xp_contract()
    xp_contract["required_security_patch_provenance_namespaces"]["security_update_channel"] = [
        "security-update"
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

    assert any(
        "XP native evidence contract required_security_patch_provenance_namespaces.security_update_channel "
        "must match platform verifier markers" in error
        and "windows-update" in error
        for error in errors
    )


def test_security_polish_rejects_platform_provenance_namespace_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
        platform_security_provenance_namespaces={
            "security_update_channel": ("security-update",),
            "cve_review_reference": ("cve-",),
        },
    )

    assert any(
        "XP native evidence contract required_security_patch_provenance_namespaces.security_update_channel "
        "must match platform verifier markers" in error
        and "windows-update" in error
        for error in errors
    )


def test_security_polish_rejects_runtime_feature_provenance_namespace_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
        feature_security_provenance_namespaces={
            "security_update_channel": ("security-update",),
            "cve_review_reference": ("cve-",),
        },
    )

    assert any(
        "runtime feature security provenance namespaces.security_update_channel "
        "must match platform verifier markers" in error
        and "windows-update" in error
        for error in errors
    )


def test_security_polish_rejects_builder_provenance_namespace_drift() -> None:
    checker = load_security_checker()

    errors = checker.check_legacy_security_policy(
        baseline=_security_baseline(),
        xp_contract=_xp_contract(),
        platform_required_flags={
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
        },
        builder_security_provenance_namespaces={
            "security_update_channel": ("security-update",),
            "cve_review_reference": ("cve-",),
        },
    )

    assert any(
        "Linux builder preflight security provenance namespaces.security_update_channel "
        "must match platform verifier markers" in error
        and "windows-update" in error
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


def test_security_polish_rejects_permissive_legacy_launcher_behavior() -> None:
    checker = load_security_checker()

    def permissive_build_plan(profile: Profile) -> object:
        return {"protocol": profile.protocol}

    errors = checker.check_legacy_launcher_behavior(
        build_plan=permissive_build_plan,
        profile_type=Profile,
        launcher_error_type=RuntimeError,
    )

    assert "SSHv1 launch must require an isolated XP legacy_target" in errors
    assert "SSHv1 launch must reject generic XP legacy_target aliases" in errors
    assert "SSHv1 launch must require the legacy_target key" in errors
    assert "weak SSH algorithms must require an isolated XP legacy_target" in errors
    assert "weak SSH algorithms must reject generic XP legacy_target aliases" in errors
    assert "RDP native security must require an isolated XP legacy_target" in errors
    assert "RDP native security must reject generic XP legacy_target aliases" in errors


def _security_baseline() -> dict[str, object]:
    return json.loads(Path("configs/security_baseline.json").read_text(encoding="utf-8"))


def _xp_contract() -> dict[str, object]:
    return json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))


def _platform_targets() -> dict[str, object]:
    return json.loads(Path("configs/platform_targets.json").read_text(encoding="utf-8"))
