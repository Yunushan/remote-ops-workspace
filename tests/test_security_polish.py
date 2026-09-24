import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import SplitResult

from remote_ops_workspace import redaction
from remote_ops_workspace.models import Profile
from remote_ops_workspace.redaction import REDACTED, redact_text, redact_value


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


def test_redaction_covers_sensitive_key_aliases_and_nested_sequences() -> None:
    payload = {
        "api_key": "api-secret",
        "identity-file": "C:/Users/operator/.ssh/id_ed25519",
        "nested": ("safe", {"authorization": "Bearer nested-secret"}),
        "safe_label": "visible",
    }

    redacted = redact_value(payload)

    assert redacted["api_key"] == REDACTED
    assert redacted["identity-file"] == REDACTED
    assert redacted["nested"] == ("safe", {"authorization": REDACTED})
    assert redacted["safe_label"] == "visible"


def test_redaction_covers_sshpass_password_forms_without_treating_generic_port_flags_as_secrets() -> None:
    payload = {
        "argv-separated": ["sshpass", "-p", "separated-secret", "ssh", "edge"],
        "argv-attached": ["C:\\tools\\sshpass.exe", "-pattached-secret", "ssh", "edge"],
        "command-separated": "sshpass -v -p 'quoted-secret' ssh edge",
        "command-attached": "sshpass.exe -pinline-secret ssh edge",
        "ordinary-port": ["ssh", "-p", "2222", "edge"],
    }

    redacted = redact_value(payload)
    serialized = json.dumps(redacted)

    for secret in ("separated-secret", "attached-secret", "quoted-secret", "inline-secret"):
        assert secret not in serialized
    assert redacted["ordinary-port"] == ["ssh", "-p", "2222", "edge"]


def test_redaction_handles_direct_urls_assignments_and_non_string_values() -> None:
    values = redact_value(
        [
            "api_key=assignment-secret",
            "https://admin:url-secret@example.invalid:8443/path?mode=read",
            "https://admin:port-secret@example.invalid:not-a-port/path",
            "https://admin:ipv6-secret@[::1]:8443/path",
            "https://:missing-user@example.invalid/path",
            "https://[invalid-ipv6",
            42,
        ]
    )

    assert values[0] == f"api_key={REDACTED}"
    assert values[1] == f"https://admin:{REDACTED}@example.invalid:8443/path?mode=read"
    assert values[2] == f"https://admin:{REDACTED}@example.invalid/path"
    assert values[3] == f"https://admin:{REDACTED}@[::1]:8443/path"
    assert values[4] == f"https://:{REDACTED}@example.invalid/path"
    assert values[5] == "https://[invalid-ipv6"
    assert values[6] == 42
    assert redact_text("prefix api_key=callback-secret suffix") == (
        f"prefix api_key={REDACTED} suffix"
    )
    assert redact_text("https://user:hostless-secret@/path") == (
        f"https://user:{REDACTED}@/path"
    )
    assert redact_value(["mode=read"]) == ["mode=read"]


def test_redaction_handles_long_unmatched_keys_and_schemes() -> None:
    non_secret = "a" * 12_000
    assert redact_text(non_secret) == non_secret
    assert redact_text(f"{non_secret}token{non_secret}") == f"{non_secret}token{non_secret}"
    malformed_urls = "h://u:p" * 2_000
    assert redact_text(malformed_urls) == malformed_urls


def test_redaction_keeps_embedded_url_and_assignment_boundaries() -> None:
    assert redact_text("1https://user:first@host +://user:visible@host") == (
        f"1https://user:{REDACTED}@host +://user:visible@host"
    )
    assert redact_text("public=visible opaqueapikey:secret") == (
        f"public=visible opaqueapikey:{REDACTED}"
    )


def test_redaction_handles_url_like_text_inside_a_password() -> None:
    assert redact_text("https://user:inner://guest:secret@host") == (
        f"https://user:{REDACTED}@host"
    )


def test_redaction_finds_embedded_url_after_an_earlier_at_sign() -> None:
    assert redact_text("contact@https://user:secret@host") == (
        f"contact@https://user:{REDACTED}@host"
    )


def test_redaction_rejects_invalid_scheme_from_legacy_urlsplit(monkeypatch) -> None:
    parsed = SplitResult("1https", "user:first@host +:", "//user:visible@host", "", "")
    monkeypatch.setattr(redaction, "urlsplit", lambda _: parsed)

    assert redact_text("1https://user:first@host +://user:visible@host") == (
        f"1https://user:{REDACTED}@host +://user:visible@host"
    )


def test_security_polish_checker_passes() -> None:
    checker = load_security_checker()
    assert checker.main() == 0


def test_security_polish_does_not_log_failed_redaction_sample_values(monkeypatch, capsys) -> None:
    checker = load_security_checker()
    monkeypatch.setattr(checker, "redact_value", lambda payload: payload)
    monkeypatch.setattr(checker, "check_support_bundle_redaction", lambda: [])
    monkeypatch.setattr(checker, "check_legacy_security_policy", lambda: [])
    monkeypatch.setattr(checker, "check_docs_and_verifier", lambda: [])
    monkeypatch.setattr(checker, "check_profile_only_security_defaults", lambda: [])

    assert checker.main() == 1
    stderr = capsys.readouterr().err
    assert "redaction leaked synthetic sample #1" in stderr
    for sample in checker.SECRET_SAMPLES:
        assert sample not in stderr


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


def test_security_polish_rejects_cleartext_protocol_default_drift() -> None:
    checker = load_security_checker()
    baseline = _security_baseline()
    baseline["modern_defaults"]["cleartext_protocol_default"] = "allowed"
    baseline["cleartext_legacy_protocols"]["default"] = "allowed"

    errors = checker.check_legacy_security_policy(
        baseline=baseline,
        xp_contract=_xp_contract(),
    )

    assert "security_baseline cleartext_protocol_default must be blocked" in errors
    assert "security_baseline cleartext legacy protocol default must be blocked" in errors


def test_security_polish_rejects_permissive_group_security_defaults() -> None:
    checker = load_security_checker()

    errors = checker.check_profile_only_security_defaults(
        normalize_defaults=lambda defaults: defaults,
        validation_error_type=RuntimeError,
    )

    assert "group defaults must reject profile-only security option: allow_insecure_cleartext" in errors


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
    for protocol in ("ftp", "rlogin", "rsh", "telnet"):
        assert f"{protocol} launch must require explicit per-profile cleartext opt-in" in errors


def _security_baseline() -> dict[str, object]:
    return json.loads(Path("configs/security_baseline.json").read_text(encoding="utf-8"))


def _xp_contract() -> dict[str, object]:
    return json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))


def _platform_targets() -> dict[str, object]:
    return json.loads(Path("configs/platform_targets.json").read_text(encoding="utf-8"))
