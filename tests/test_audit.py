import os
import stat

from remote_ops_workspace.audit import append_event
from remote_ops_workspace.file_safety import PRIVATE_FILE_MODE


def test_append_event_redacts_and_writes_private_audit_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))

    path = append_event(
        "launch",
        {"command": ["ssh", "--password", "top-secret", "host"], "api_token": "abc"},
    )

    text = path.read_text(encoding="utf-8")
    assert "top-secret" not in text
    assert "abc" not in text
    assert "***REDACTED***" in text
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


def test_audit_redacts_inline_secret_arguments_and_url_passwords() -> None:
    from remote_ops_workspace.audit import _redact

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

    text = str(_redact(payload))

    assert "inline-secret" not in text
    assert "next-token" not in text
    assert "rdp-secret" not in text
    assert "url-secret" not in text
    assert "bearer-secret" not in text
    assert "prod/router-password" not in text
