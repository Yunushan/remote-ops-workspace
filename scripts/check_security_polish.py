from __future__ import annotations

import json
import sys
from pathlib import Path


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
    ):
        if snippet not in docs:
            errors.append(f"security docs missing required snippet: {snippet}")
    return errors


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
