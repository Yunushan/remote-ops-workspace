from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import terminal as terminal_module
from remote_ops_workspace import windows_conpty
from remote_ops_workspace.terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
)


def test_runtime_overrides_do_not_rewrite_option_operands_or_remote_command() -> None:
    command = [
        "ssh",
        "-F",
        "-oBatchMode=no",
        "target.example",
        "-o",
        "BatchMode=no",
    ]

    adapted = openssh_command_with_overrides(command, {"BatchMode": "yes"})

    assert adapted[:3] == ["ssh", "-o", "BatchMode=yes"]
    assert adapted[3:] == command[1:]


@pytest.mark.parametrize(
    "tail",
    [
        ["target.example", "-M", "remote-command"],
        ["--", "-M"],
        ["-F", "-Mconfig", "target.example"],
    ],
)
def test_windows_mux_rewrite_stops_at_destination_and_consumes_option_values(
    monkeypatch,
    tail: list[str],
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)

    adapted = openssh_command_without_windows_connection_sharing(["ssh.exe", *tail])

    assert adapted[:9] == [
        "ssh.exe",
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
        "-o",
        "ControlPath=none",
    ]
    assert adapted[9:] == tail


def test_windows_proxy_jump_separates_user_host_ipv6_and_port(monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    command = [
        "ssh.exe",
        "-J",
        "jump-user@[2001:db8::7]:2222",
        "target.example",
    ]

    adapted = openssh_command_without_windows_connection_sharing(command)
    proxy = next(value for value in adapted if value.startswith("ProxyCommand="))
    expected_child = subprocess.list2cmdline(
        [
            terminal_module._windows_proxy_child_executable("ssh.exe"),
            "-S",
            "none",
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPersist=no",
            "-o",
            "ControlPath=none",
            "-o",
            "ProxyCommand=none",
            "-o",
            "ProxyJump=none",
            "-p",
            "2222",
            "-W",
            "[%h]:%p",
            "--",
            "jump-user@2001:db8::7",
        ]
    )

    assert proxy == f"ProxyCommand={expected_child}"


def test_windows_proxy_jump_rewrite_ignores_remote_j_option(monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    command = ["ssh.exe", "target.example", "-J", "remote-argument"]

    adapted = openssh_command_without_windows_connection_sharing(command)

    assert not any(value.startswith("ProxyCommand=") for value in adapted)
    assert adapted[-3:] == command[-3:]


def test_proxy_jump_child_uses_trusted_windows_resolver(monkeypatch) -> None:
    observed: list[str] = []
    expected = r"C:\Windows\System32\OpenSSH\ssh.exe"
    monkeypatch.setattr(terminal_module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        windows_conpty,
        "resolve_windows_executable",
        lambda executable: observed.append(executable) or expected,
    )

    child = terminal_module._windows_proxy_child_executable("ssh.exe")

    assert observed == ["ssh.exe"]
    assert child == expected


def test_embedded_openssh_detection_uses_windows_path_semantics() -> None:
    profile = SimpleNamespace(protocol="ssh")

    assert terminal_module._is_embedded_openssh(
        profile,
        [r"C:\Windows\System32\OpenSSH\ssh.exe", "operator@host"],
    ) is True


def test_explicit_extensionless_windows_path_honors_pathext(
    monkeypatch,
    tmp_path: Path,
) -> None:
    executable = tmp_path / "bin" / "tool"
    executable.parent.mkdir()
    expected = executable.with_name("tool.EXE")
    expected.write_bytes(b"test executable")
    monkeypatch.setenv("PATHEXT", ".EXE;.CMD")

    resolved = windows_conpty._resolve_windows_executable(os.fspath(executable))

    assert Path(resolved) == expected.resolve()
