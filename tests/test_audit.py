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
