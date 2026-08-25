from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from remote_ops_workspace import command_safety


@pytest.mark.parametrize(
    ("command", "message"),
    [("", "is required"), ("   ", "must not be empty")],
)
def test_argv_rejects_empty_command_on_every_platform(
    command: str,
    message: str,
) -> None:
    with pytest.raises(command_safety.CommandSafetyError, match=message):
        command_safety.argv(command)


@pytest.mark.skipif(os.name != "nt", reason="native Windows command-line contract")
@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            r"C:\Windows\System32\OpenSSH\ssh.exe -i C:\Users\Yunus\.ssh\id_ed25519 operator@example.invalid",
            [
                r"C:\Windows\System32\OpenSSH\ssh.exe",
                "-i",
                r"C:\Users\Yunus\.ssh\id_ed25519",
                "operator@example.invalid",
            ],
        ),
        (
            r'"C:\Program Files\OpenSSH\ssh.exe" -i "C:\Users\Yunus Home\.ssh\id_ed25519" operator@example.invalid',
            [
                r"C:\Program Files\OpenSSH\ssh.exe",
                "-i",
                r"C:\Users\Yunus Home\.ssh\id_ed25519",
                "operator@example.invalid",
            ],
        ),
        (
            r"   C:\Windows\System32\OpenSSH\ssh.exe operator@example.invalid   ",
            [
                r"C:\Windows\System32\OpenSSH\ssh.exe",
                "operator@example.invalid",
            ],
        ),
    ],
)
def test_argv_uses_native_windows_quoting_without_losing_backslashes(
    command: str,
    expected: list[str],
) -> None:
    assert command_safety.argv(command) == expected


@pytest.mark.skipif(os.name == "nt", reason="POSIX parsing contract")
def test_argv_preserves_posix_shell_word_parsing() -> None:
    assert command_safety.argv("printf '%s value' payload") == [
        "printf",
        "%s value",
        "payload",
    ]


def test_text_host_option_and_port_validators_fail_closed() -> None:
    assert command_safety.clean_text(None, "optional", allow_empty=True) == ""
    assert command_safety.clean_text("", "optional", allow_empty=True) == ""
    assert command_safety.path_arg("C:/safe path", "path") == "C:/safe path"
    assert command_safety.port("22") == 22

    cases = (
        (lambda: command_safety.clean_text(None, "value"), "value is required"),
        (lambda: command_safety.clean_text("bad\nvalue", "value"), "control characters"),
        (lambda: command_safety.host("-oProxyCommand=bad"), "must not start"),
        (lambda: command_safety.host("two hosts"), "whitespace"),
        (lambda: command_safety.option_value("--unsafe", "option"), "must not start"),
        (lambda: command_safety.port(None), "port is required"),
        (lambda: command_safety.port(0), "between 1 and 65535"),
        (lambda: command_safety.port(65536), "between 1 and 65535"),
    )
    for operation, message in cases:
        with pytest.raises(command_safety.CommandSafetyError, match=message):
            operation()


def test_url_validator_rejects_ambiguous_or_secret_bearing_urls() -> None:
    assert command_safety.url("https://example.invalid/path") == "https://example.invalid/path"

    cases = (
        ("https://example.invalid/two words", "whitespace"),
        ("file:///etc/passwd", "scheme must be one of"),
        ("https:path-only", "requires a host"),
        ("https://user:secret@example.invalid", "embedded password"),
    )
    for value, message in cases:
        with pytest.raises(command_safety.CommandSafetyError, match=message):
            command_safety.url(value)


def test_posix_argv_reports_invalid_quoting(monkeypatch) -> None:
    monkeypatch.setattr(command_safety, "os", SimpleNamespace(name="posix"))
    assert command_safety.argv("ssh 'two words'") == ["ssh", "two words"]
    with pytest.raises(command_safety.CommandSafetyError, match="not a valid command line"):
        command_safety.argv("printf 'unterminated")


def test_windows_argv_reports_unavailable_native_parser(monkeypatch) -> None:
    monkeypatch.delitem(command_safety.ctypes.__dict__, "WinDLL", raising=False)
    with pytest.raises(command_safety.CommandSafetyError, match="API is unavailable"):
        command_safety._windows_command_line_to_argv("ssh host", "command")


def test_windows_argv_reports_native_parser_failure(monkeypatch) -> None:
    class NativeFunction:
        argtypes = None
        restype = None

        def __init__(self, result=None) -> None:
            self.result = result

        def __call__(self, *args):
            return self.result

    shell32 = SimpleNamespace(CommandLineToArgvW=NativeFunction())
    kernel32 = SimpleNamespace(LocalFree=NativeFunction())

    def fake_win_dll(name: str, *, use_last_error: bool):
        assert use_last_error is True
        return shell32 if name == "shell32" else kernel32

    monkeypatch.setitem(command_safety.ctypes.__dict__, "WinDLL", fake_win_dll)
    monkeypatch.setitem(command_safety.ctypes.__dict__, "get_last_error", lambda: 87)

    with pytest.raises(command_safety.CommandSafetyError, match="error 87"):
        command_safety._windows_command_line_to_argv("ssh host", "command")


def test_argv_list_shellish_text_and_display_validation() -> None:
    assert command_safety.argv_list(["ssh", "host"]) == ["ssh", "host"]
    assert command_safety.shellish_text("echo safe", "command") == "echo safe"
    assert command_safety.display(None) == ":0"
    assert command_safety.display(":10.2") == ":10.2"

    cases = (
        (lambda: command_safety.argv_list([]), "must not be empty"),
        (lambda: command_safety.shellish_text("line\nnext", "command"), "single line"),
        (lambda: command_safety.display("10"), "start with"),
        (lambda: command_safety.display(":1.screen"), "screen must be numeric"),
        (lambda: command_safety.display(":screen"), "number must be numeric"),
    )
    for operation, message in cases:
        with pytest.raises(command_safety.CommandSafetyError, match=message):
            operation()
