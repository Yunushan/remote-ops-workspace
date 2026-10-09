import argparse
import json
import os
import stat

import pytest

from remote_ops_workspace import cli, redaction
from remote_ops_workspace.audit import append_event
from remote_ops_workspace.file_safety import PRIVATE_FILE_MODE
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


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


@pytest.mark.parametrize(
    ("command", "secrets"),
    [
        ('tool --password "audit password" --token audit-token', ("audit password", "audit-token")),
        ('tool --password="inline password" /p:"windows password"', ("inline password", "windows password")),
        ('sshpass -p "helper password" ssh edge', ("helper password",)),
        ('sshpass -p"attached password" ssh edge', ("attached password",)),
        ('sh -c "tool --password nested-password --token nested-token"', ("nested-password", "nested-token")),
        (
            'sh -c "tool --password=\'quoted nested password\' /p:\'quoted nested windows\'"',
            ("quoted nested password", "quoted nested windows"),
        ),
        (r'bash -c "tool \"--password\" nested-quoted-secret"', ("nested-quoted-secret",)),
        (r'bash -c "sshpass \"-p\" nested-sshpass-secret ssh edge"', ("nested-sshpass-secret",)),
        ('sh -c "tool --pass\'word\' concatenated-option-secret"', ("concatenated-option-secret",)),
        ('sh -c "tool --password \'unterminated-shell-secret"', ("unterminated-shell-secret",)),
        ('cmd /c "tool --password cmd-script-secret"', ("cmd-script-secret",)),
        ('pwsh -Command "tool --password powershell-script-secret"', ("powershell-script-secret",)),
        ('powershell -Enc encoded-script-secret', ("encoded-script-secret",)),
        (r'fish --command="tool \"--password\" fish-script-secret"', ("fish-script-secret",)),
        ('env bash --noprofile -lc "tool --password environment-script-secret"', ("environment-script-secret",)),
        ('ssh edge sh -c "tool --password remote-script-secret"', ("remote-script-secret",)),
        ('sh -c "printf %s $1" sh positional-script-secret', ("positional-script-secret",)),
    ],
)
def test_connect_dry_run_redacts_every_command_copy_in_persisted_audit(
    tmp_path, monkeypatch, command, secrets
) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    ProfileStore().add(Profile(name="audit-probe", protocol="custom", command=command))

    def forbid_launch(*args, **kwargs):
        raise AssertionError("dry-run must not launch a process")

    monkeypatch.setattr("remote_ops_workspace.launcher.subprocess.Popen", forbid_launch)
    assert cli.cmd_connect(argparse.Namespace(name="audit-probe", dry_run=True)) == 0

    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    event = json.loads(text)
    assert event["event_type"] == "connect.dry_run"
    assert "***REDACTED***" in event["payload"]["profile"]["command"]
    assert any("***REDACTED***" in argument for argument in event["payload"]["command"])
    for secret in secrets:
        assert secret not in text


def test_audit_command_text_fails_closed_and_preserves_safe_text() -> None:
    from remote_ops_workspace.audit import _redact

    payload = {
        "profile": {"command": 'tool --password "unterminated secret'},
        "safe": {"command": 'tool --port 2222 "ordinary value"'},
        "empty": {"command": ""},
    }
    redacted = _redact(payload)
    if os.name == "nt":
        # The native Windows grammar accepts an unmatched final quote.
        assert "unterminated secret" not in redacted["profile"]["command"]
    else:
        assert redacted["profile"]["command"] == "***REDACTED***"
    assert redacted["safe"]["command"] == payload["safe"]["command"]
    assert redacted["empty"]["command"] == ""


def test_audit_omits_command_text_when_platform_parser_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise redaction.safe.CommandSafetyError("platform command parser unavailable")

    monkeypatch.setattr(redaction.safe, "argv", unavailable)
    assert redaction.redact_value({"command": "tool --password parser-secret"}) == {
        "command": "***REDACTED***"
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('tool --password "a quoted password" tail', 'tool --password ***REDACTED*** tail'),
        ('tool --password "unterminated password', 'tool --password ***REDACTED***'),
        ('password="a quoted password"; safe=value', 'password=***REDACTED***; safe=value'),
        ("token='single quoted token' suffix", "token=***REDACTED*** suffix"),
        (r"tool --secret escaped\ password tail", 'tool --secret ***REDACTED*** tail'),
        ('tool /P:"windows password" tail', 'tool /P:***REDACTED*** tail'),
        ('tool --password "outer --token inner-secret" tail', 'tool --password ***REDACTED*** tail'),
        ('tool --password ', 'tool --password '),
    ],
)
def test_audit_redacts_complete_secret_tokens_in_nested_command_text(text, expected) -> None:
    assert redaction.redact_text(text) == expected


def test_audit_treats_shell_arguments_as_opaque_and_preserves_structured_values() -> None:
    assert redaction.redact_value(["ssh", "edge", r"C:\\Tools\\BASH.EXE", "-c", "script", "argument"]) == [
        "ssh", "edge", r"C:\\Tools\\BASH.EXE", redaction.REDACTED, redaction.REDACTED, redaction.REDACTED,
    ]
    assert redaction.redact_value([{"command": "tool --port 2222"}, "ordinary", "sh"]) == [
        {"command": "tool --port 2222"}, "ordinary", "sh",
    ]
