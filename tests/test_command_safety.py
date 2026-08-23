from __future__ import annotations

import os

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
