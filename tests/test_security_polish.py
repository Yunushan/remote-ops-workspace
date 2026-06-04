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
