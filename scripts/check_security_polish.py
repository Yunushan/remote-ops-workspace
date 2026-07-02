from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.redaction import REDACTED, is_sensitive_key, redact_value  # noqa: E402

SECRET_SAMPLES = (
    "inline-secret",
    "next-token",
    "rdp-secret",
    "url-secret",
    "bearer-secret",
    "prod/router-password",
)


def main() -> int:
    errors: list[str] = []
    errors.extend(check_redaction_samples())
    errors.extend(check_support_bundle_redaction())
    errors.extend(check_legacy_security_policy())
    errors.extend(check_docs_and_verifier())
    if errors:
        for error in errors:
            print(f"security polish: {error}", file=sys.stderr)
        return 1
    print("production security polish passed")
    return 0


def check_redaction_samples() -> list[str]:
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
    redacted = redact_value(payload)
    serialized = json.dumps(redacted, sort_keys=True)
    errors = []
    for sample in SECRET_SAMPLES:
        if sample in serialized:
            errors.append(f"redaction leaked sample secret: {sample}")
    if REDACTED not in serialized:
        errors.append("redaction output must include the standard redaction marker")
    for key in ("credential_ref", "password", "api_token", "private_key", "auth_cookie"):
        if not is_sensitive_key(key):
            errors.append(f"is_sensitive_key must classify {key!r} as sensitive")
    return errors


def check_support_bundle_redaction() -> list[str]:
    support_bundle = read("scripts/support_bundle.py")
    tests = read("tests/test_support_bundle.py")
    errors = []
    if "is_sensitive_key" not in support_bundle:
        errors.append("support_bundle.py must use shared sensitive-key classification")
    if "sensitive_option_key_count" not in support_bundle:
        errors.append("support_bundle.py must report sensitive option key counts without names")
    if '"api_token" not in serialized' not in tests:
        errors.append("support bundle tests must assert sensitive option key names are excluded")
    return errors


def check_docs_and_verifier() -> list[str]:
    errors = []
    verifier = read("scripts/verify.py")
    if "scripts/check_security_polish.py" not in verifier:
        errors.append("scripts/verify.py must run scripts/check_security_polish.py")
    docs = "\n".join(
        read(path)
        for path in (
            "SECURITY.md",
            "docs/SECURITY_MODEL.md",
            "docs/VERIFYING.md",
        )
    )
    for snippet in (
        "assignment-style secret arguments",
        "URL-embedded passwords",
        "sensitive option key names",
        "python scripts/check_security_polish.py",
        "TLS 1.3 preferred and TLS 1.2 minimum",
        "legacy_target=windows-xp-32",
        "allow_legacy_crypto=true",
        "allow_legacy_rdp_security=true",
        "generic XP labels such as `xp`, `winxp` and `windows-xp`",
        "`legacy_platform` alias key",
        "Linux i386/armhf security smoke proof lines",
    ):
        if snippet not in docs:
            errors.append(f"security docs missing required snippet: {snippet}")
    return errors


def check_legacy_security_policy(
    *,
    baseline: dict[str, Any] | None = None,
    xp_contract: dict[str, Any] | None = None,
    platform_required_flags: dict[str, bool] | None = None,
    platform_required_patch_evidence: dict[str, Any] | None = None,
    platform_required_patch_provenance_fields: tuple[str, ...] | None = None,
    platform_linux_security_smoke_lines: tuple[str, ...] | None = None,
    platform_forbidden_linux_security_smoke_lines: tuple[str, ...] | None = None,
) -> list[str]:
    errors: list[str] = []
    baseline = baseline or json.loads(read("configs/security_baseline.json"))
    xp_contract = xp_contract or json.loads(read("configs/xp_native_evidence_contract.json"))
    platform_required_flags = platform_required_flags or load_platform_required_xp_security_flags()
    platform_required_patch_evidence = (
        platform_required_patch_evidence or load_platform_required_security_patch_evidence()
    )
    if platform_required_patch_provenance_fields is None:
        platform_required_patch_provenance_fields = load_platform_required_security_patch_provenance_fields()
    if platform_linux_security_smoke_lines is None:
        platform_linux_security_smoke_lines = load_platform_linux_security_smoke_lines()
    if platform_forbidden_linux_security_smoke_lines is None:
        platform_forbidden_linux_security_smoke_lines = load_platform_forbidden_linux_security_smoke_lines()
    modern = baseline.get("modern_defaults", {})
    if modern.get("preferred_tls") != "TLS 1.3":
        errors.append("security_baseline preferred_tls must stay TLS 1.3")
    if modern.get("minimum_tls") != "TLS 1.2":
        errors.append("security_baseline minimum_tls must stay TLS 1.2")
    for protocol in ("SSL 2.0", "SSL 3.0", "TLS 1.0", "TLS 1.1"):
        if protocol not in modern.get("deprecated_tls_protocols", []):
            errors.append(f"security_baseline must deprecate {protocol}")
    for key in (
        "ssh_legacy_crypto_default",
        "rdp_legacy_security_default",
        "weak_crypto_global_default",
    ):
        if modern.get(key) != "blocked":
            errors.append(f"security_baseline {key} must be blocked")

    xp_policy = baseline.get("legacy_windows_xp_remote_targets", {})
    if xp_policy.get("coverage_percent") != 100.0:
        errors.append("Windows XP remote-target security policy must keep 100.0% coverage")
    if xp_policy.get("architectures") != ["x86", "x64"]:
        errors.append("Windows XP remote-target security policy must cover x86 and x64")
    if xp_policy.get("native_operator_host") is not False:
        errors.append("Windows XP security policy must not claim native operator-host support")
    if xp_policy.get("profile_scope") != "per-target":
        errors.append("Windows XP legacy crypto policy must stay per-target scoped")

    expected_flags = {
        "legacy_crypto_profile_scoped": True,
        "modern_defaults_unchanged": True,
        "weak_crypto_global_default": False,
    }
    contract_flags = xp_contract.get("required_security_flags", {})
    if contract_flags != expected_flags:
        errors.append(
            "XP native evidence contract required_security_flags must match "
            f"{expected_flags}, got {contract_flags}"
        )
    if platform_required_flags != expected_flags:
        errors.append(
            "platform verified evidence REQUIRED_XP_SECURITY_FLAGS must match "
            f"{expected_flags}, got {platform_required_flags}"
        )
    expected_patch_evidence = {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
    }
    contract_patch_evidence = xp_contract.get("required_security_patch_evidence", {})
    if contract_patch_evidence != expected_patch_evidence:
        errors.append(
            "XP native evidence contract required_security_patch_evidence must match "
            f"{expected_patch_evidence}, got {contract_patch_evidence}"
        )
    if platform_required_patch_evidence != expected_patch_evidence:
        errors.append(
            "platform verified evidence REQUIRED_SECURITY_PATCH_EVIDENCE must match "
            f"{expected_patch_evidence}, got {platform_required_patch_evidence}"
        )
    expected_patch_provenance_fields = ("cve_review_reference", "security_update_channel")
    contract_patch_provenance_fields = tuple(
        sorted(str(item) for item in xp_contract.get("required_security_patch_provenance_fields", []))
    )
    if contract_patch_provenance_fields != expected_patch_provenance_fields:
        errors.append(
            "XP native evidence contract required_security_patch_provenance_fields must match "
            f"{list(expected_patch_provenance_fields)}, got {list(contract_patch_provenance_fields)}"
        )
    if tuple(sorted(platform_required_patch_provenance_fields)) != expected_patch_provenance_fields:
        errors.append(
            "platform verified evidence REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS must match "
            f"{list(expected_patch_provenance_fields)}, got {list(platform_required_patch_provenance_fields)}"
        )
    expected_linux_security_lines = {
        f"native installer smoke TLS minimum modern profiles: {modern.get('minimum_tls')}",
        f"native installer smoke TLS preferred modern profiles: {modern.get('preferred_tls')}",
        "native installer smoke legacy compatibility profile: isolated-opt-in",
        "native installer smoke legacy crypto scope: profile-only",
        "native installer smoke weak crypto global default: false",
        "native installer smoke modern defaults unchanged: true",
    }
    linux_security_lines = set(platform_linux_security_smoke_lines)
    missing_linux_security_lines = sorted(expected_linux_security_lines - linux_security_lines)
    if missing_linux_security_lines:
        errors.append(
            "platform verified evidence REQUIRED_LINUX_SECURITY_SMOKE_LINES must include "
            f"{missing_linux_security_lines}"
        )
    expected_forbidden_linux_security_lines = {
        "native installer smoke TLS minimum modern profiles: TLS 1.0",
        "native installer smoke TLS minimum modern profiles: TLS 1.1",
        "native installer smoke weak crypto global default: true",
        "native installer smoke modern defaults unchanged: false",
    }
    forbidden_linux_security_lines = set(platform_forbidden_linux_security_smoke_lines)
    missing_forbidden_linux_security_lines = sorted(
        expected_forbidden_linux_security_lines - forbidden_linux_security_lines
    )
    if missing_forbidden_linux_security_lines:
        errors.append(
            "platform verified evidence FORBIDDEN_LINUX_SECURITY_SMOKE_LINES must include "
            f"{missing_forbidden_linux_security_lines}"
        )
    smoke_ids = set(str(item) for item in xp_contract.get("required_smoke_ids", []))
    for smoke_id in ("legacy_crypto_profile_scoped", "modern_defaults_unchanged"):
        if smoke_id not in smoke_ids:
            errors.append(f"XP native evidence contract must require smoke id: {smoke_id}")
    required_profile_options = "\n".join(str(item) for item in xp_policy.get("required_profile_options", []))
    for snippet in (
        "legacy_target=windows-xp-32|windows-xp-64",
        "allow_legacy_crypto=true",
        "allow_legacy_rdp_security=true",
    ):
        if snippet not in required_profile_options:
            errors.append(f"Windows XP security baseline missing required profile option: {snippet}")

    launcher = read("src/remote_ops_workspace/launcher.py")
    for snippet in (
        "WEAK_SSH_ALGORITHMS_BY_OPTION",
        "allow_legacy_crypto",
        "allow_legacy_rdp_security",
        "legacy_target",
        "security == \"rdp\"",
    ):
        if snippet not in launcher:
            errors.append(f"launcher missing legacy security enforcement snippet: {snippet}")
    errors.extend(check_legacy_launcher_behavior())
    return errors


def check_legacy_launcher_behavior(
    *,
    build_plan: Any | None = None,
    profile_type: Any | None = None,
    launcher_error_type: type[Exception] | None = None,
) -> list[str]:
    if build_plan is None or profile_type is None or launcher_error_type is None:
        from remote_ops_workspace.launcher import LauncherError, build_launch_plan
        from remote_ops_workspace.models import Profile

        build_plan = build_launch_plan
        profile_type = Profile
        launcher_error_type = LauncherError

    scenarios = (
        (
            "SSHv1 launch must require an isolated XP legacy_target",
            profile_type(
                name="sshv1-missing-target",
                protocol="ssh1",
                host="192.0.2.10",
                options={"allow_insecure_sshv1": "true", "allow_legacy_crypto": "true"},
            ),
        ),
        (
            "SSHv1 launch must reject generic XP legacy_target aliases",
            profile_type(
                name="sshv1-generic-target",
                protocol="ssh1",
                host="192.0.2.10",
                options={
                    "allow_insecure_sshv1": "true",
                    "legacy_target": "windows-xp",
                    "allow_legacy_crypto": "true",
                },
            ),
        ),
        (
            "SSHv1 launch must require the legacy_target key",
            profile_type(
                name="sshv1-legacy-platform-alias",
                protocol="ssh1",
                host="192.0.2.10",
                options={
                    "allow_insecure_sshv1": "true",
                    "legacy_platform": "windows-xp-32",
                    "allow_legacy_crypto": "true",
                },
            ),
        ),
        (
            "weak SSH algorithms must require an isolated XP legacy_target",
            profile_type(
                name="weak-ssh-missing-target",
                protocol="ssh",
                host="192.0.2.10",
                options={"kex_algorithms": "+diffie-hellman-group1-sha1", "allow_legacy_crypto": "true"},
            ),
        ),
        (
            "weak SSH algorithms must reject generic XP legacy_target aliases",
            profile_type(
                name="weak-ssh-generic-target",
                protocol="ssh",
                host="192.0.2.10",
                options={
                    "kex_algorithms": "+diffie-hellman-group1-sha1",
                    "legacy_target": "windows-xp",
                    "allow_legacy_crypto": "true",
                },
            ),
        ),
        (
            "RDP native security must require an isolated XP legacy_target",
            profile_type(
                name="rdp-missing-target",
                protocol="rdp",
                host="192.0.2.10",
                options={"security": "rdp", "allow_legacy_rdp_security": "true"},
            ),
        ),
        (
            "RDP native security must reject generic XP legacy_target aliases",
            profile_type(
                name="rdp-generic-target",
                protocol="rdp",
                host="192.0.2.10",
                options={
                    "security": "rdp",
                    "legacy_target": "windows-xp",
                    "allow_legacy_rdp_security": "true",
                },
            ),
        ),
    )

    errors: list[str] = []
    for message, profile in scenarios:
        try:
            build_plan(profile)
        except launcher_error_type:
            continue
        errors.append(message)
    return errors


def load_platform_required_xp_security_flags() -> dict[str, bool]:
    path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence_security", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    flags = getattr(module, "REQUIRED_XP_SECURITY_FLAGS", {})
    if not isinstance(flags, dict):
        return {}
    return {str(key): value for key, value in flags.items() if isinstance(value, bool)}


def load_platform_required_security_patch_evidence() -> dict[str, Any]:
    path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence_security_patch", path)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    evidence = getattr(module, "REQUIRED_SECURITY_PATCH_EVIDENCE", {})
    return evidence if isinstance(evidence, dict) else {}


def load_platform_required_security_patch_provenance_fields() -> tuple[str, ...]:
    path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence_security_patch", path)
    if spec is None or spec.loader is None:
        return ()
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    fields = getattr(module, "REQUIRED_SECURITY_PATCH_PROVENANCE_FIELDS", ())
    if not isinstance(fields, (list, tuple, set)):
        return ()
    return tuple(str(field) for field in fields)


def load_platform_linux_security_smoke_lines() -> tuple[str, ...]:
    path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence_linux_security", path)
    if spec is None or spec.loader is None:
        return ()
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    lines = getattr(module, "REQUIRED_LINUX_SECURITY_SMOKE_LINES", ())
    if not isinstance(lines, (list, tuple, set)):
        return ()
    return tuple(str(line) for line in lines)


def load_platform_forbidden_linux_security_smoke_lines() -> tuple[str, ...]:
    path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence_linux_forbidden_security", path)
    if spec is None or spec.loader is None:
        return ()
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    lines = getattr(module, "FORBIDDEN_LINUX_SECURITY_SMOKE_LINES", ())
    if not isinstance(lines, (list, tuple, set)):
        return ()
    return tuple(str(line) for line in lines)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
