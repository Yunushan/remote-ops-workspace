from __future__ import annotations

import os
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import remote_ops_workspace.terminal as terminal
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile, Tunnel
from remote_ops_workspace.terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    split_shell_plans,
    ssh_command_with_control_path,
    ssh_connection_key,
    ssh_control_path_for_profile,
    terminal_plan_for_profile,
)


def test_terminal_plans_reject_empty_split_and_preserve_non_ssh_commands() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        split_shell_plans(0)

    plan = terminal_plan_for_profile(Profile(name="script", protocol="custom", command="echo ready"))

    assert plan.command == ["echo", "ready"]
    assert plan.notes == ["Custom command profile."]
    assert plan.printable() == "echo ready"


@pytest.mark.parametrize(
    ("line", "source", "command", "native_windows", "expected"),
    [
        ("clear", "shell", [r"C:\Windows\System32\cmd.exe"], True, "cls"),
        ("CLEAR", "shell", ["cmd.exe"], True, "cls"),
        ("clear", "shell", ["cmd.exe"], False, "clear"),
        ("clear", "command", ["cmd.exe"], True, "clear"),
        ("clear", "shell", ["powershell.exe"], True, "clear"),
        ("clear", "shell", [], True, "clear"),
        (" clear ", "shell", ["cmd.exe"], True, "cls"),
    ],
)
def test_local_shell_input_normalises_only_native_cmd_clear(
    monkeypatch: pytest.MonkeyPatch,
    line: str,
    source: str,
    command: list[str],
    native_windows: bool,
    expected: str,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: native_windows)
    plan = terminal.TerminalPanePlan(
        title="shell-input",
        command=command,
        source=source,
    )

    assert terminal.normalise_local_shell_input(line, plan) == expected


def test_terminal_profile_plan_preserves_explicit_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: False)
    monkeypatch.setattr(
        terminal,
        "build_launch_plan",
        lambda _profile: LaunchPlan(
            "ssh",
            ["ssh", "-o", "ConnectTimeout=30", "operator@target.example"],
            [],
        ),
    )

    plan = terminal_plan_for_profile(Profile(name="edge", protocol="ssh", host="target.example"))

    assert "ConnectTimeout=30" in plan.command
    assert "ConnectTimeout=10" not in plan.command
    assert not any("10 second TCP connection timeout" in note for note in plan.notes)


def test_openssh_short_option_parser_handles_operands_and_missing_values() -> None:
    assert terminal._openssh_short_argument(["ssh", "target"], 1) == (None, None, 1, "target")
    assert terminal._openssh_short_argument(["ssh", "-o"], 1) == ("o", None, 1, "")
    assert terminal._ssh_option_is_present(["ssh"], "ConnectTimeout") is False


def test_openssh_runtime_overrides_cover_empty_and_prefixed_options() -> None:
    assert openssh_command_with_overrides([], {"BatchMode": "yes"}) == []
    assert openssh_command_with_overrides(["ssh", "-v"], {}) == ["ssh", "-v"]

    adapted = openssh_command_with_overrides(
        ["ssh", "-voBatchMode=no", "operator@example.invalid"],
        {"BatchMode": "yes"},
    )

    assert adapted == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-v",
        "operator@example.invalid",
    ]


def test_windows_proxy_jump_validation_rejects_invalid_ipv6_and_missing_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="invalid IPv6"):
        terminal._windows_proxy_jump_spec("[1:2:3]")

    class HostlessMatch:
        @staticmethod
        def group(_name: str) -> None:
            return None

    monkeypatch.setattr(terminal.re, "fullmatch", lambda *_args, **_kwargs: HostlessMatch())
    with pytest.raises(ValueError, match="host is unavailable"):
        terminal._windows_proxy_jump_spec("host.example")


def test_windows_proxy_jump_validation_accepts_ipv6() -> None:
    assert terminal._windows_proxy_jump_spec("user@[2001:db8::1]:2222") == (
        "user@2001:db8::1",
        "2222",
    )


def test_windows_proxy_child_rewrites_sibling_and_rejects_interpreted_metacharacters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "linux")

    assert terminal._windows_proxy_child_executable(r"C:\OpenSSH\sftp.exe") == r"C:\OpenSSH\ssh.exe"
    with pytest.raises(ValueError, match="unsafe for ProxyCommand"):
        terminal._windows_proxy_child_executable(r"C:\bad&directory\sftp.exe")


def test_windows_ssh_config_args_cover_empty_missing_and_unsafe_paths() -> None:
    assert terminal._windows_ssh_config_args(["ssh"]) == []

    with pytest.raises(ValueError, match="requires a configuration path"):
        terminal._windows_ssh_config_args(["ssh", "-F"])
    with pytest.raises(ValueError, match="configuration path is unsafe"):
        terminal._windows_ssh_config_args(["ssh", "-F", r"C:\bad&config"])


def test_windows_proxy_jump_rewrite_handles_none_and_prefixed_forms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    disabled = ["ssh", "-o", "ProxyJump=none", "target.example"]

    assert terminal._windows_command_with_hardened_proxy_jump(disabled, "ssh") == disabled
    assert terminal._windows_command_with_hardened_proxy_jump(["ssh", "-v"], "ssh") == ["ssh", "-v"]

    long_prefixed = terminal._windows_command_with_hardened_proxy_jump(
        ["ssh", "-voProxyJump=bastion.example", "target.example"],
        "ssh",
    )
    short_prefixed = terminal._windows_command_with_hardened_proxy_jump(
        ["ssh", "-vJbastion.example", "target.example"],
        "ssh",
    )

    assert "-v" in long_prefixed
    assert "-v" in short_prefixed
    assert any(argument.startswith("ProxyCommand=") for argument in long_prefixed)
    assert any(argument.startswith("ProxyCommand=") for argument in short_prefixed)


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (["ssh", "-o", "ProxyJump=", "target.example"], "requires a destination"),
        (["ssh", "-J"], "-J requires a destination"),
        (
            ["ssh", "-J", "one.example", "-J", "two.example", "target.example"],
            "accepts one explicit proxy_jump",
        ),
        (
            [
                "ssh",
                "-o",
                "ProxyCommand=ssh bastion -W %h:%p",
                "-J",
                "bastion.example",
                "target.example",
            ],
            "cannot combine proxy_jump and ProxyCommand",
        ),
    ],
)
def test_windows_proxy_jump_rewrite_rejects_ambiguous_forms(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
    message: str,
) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "linux")

    with pytest.raises(ValueError, match=message):
        terminal._windows_command_with_hardened_proxy_jump(command, "ssh")


def test_windows_mux_cleanup_preserves_prefixed_flags_and_value_operands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: True)
    monkeypatch.setattr(terminal.sys, "platform", "linux")

    long_option = openssh_command_without_windows_connection_sharing(
        ["ssh.exe", "-voControlMaster=auto", "target.example"]
    )
    clustered = openssh_command_without_windows_connection_sharing(
        ["ssh.exe", "-MB", "bind-interface", "target.example"]
    )
    option_only = openssh_command_without_windows_connection_sharing(["ssh.exe", "-v"])

    assert "-v" in long_option
    assert "ControlMaster=auto" not in long_option
    assert ["-B", "bind-interface"] == clustered[-3:-1]
    assert "-v" in option_only


def test_control_path_contract_covers_disabled_explicit_success_and_io_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: False)

    assert ssh_control_path_for_profile(Profile(name="web", protocol="https")) == ""
    assert (
        ssh_control_path_for_profile(
            Profile(
                name="disabled",
                protocol="ssh",
                host="target.example",
                options={"ssh_connection_sharing": "off"},
            )
        )
        == ""
    )
    assert (
        ssh_control_path_for_profile(
            Profile(
                name="external",
                protocol="ssh",
                host="target.example",
                options={"ssh_control_path": "/tmp/external"},
            )
        )
        == ""
    )

    profile = Profile(name="edge", protocol="ssh", host="target.example", username="operator")
    monkeypatch.delattr(terminal.os, "geteuid", raising=False)
    assert ssh_control_path_for_profile(profile) == ""
    monkeypatch.setattr(terminal.os, "geteuid", lambda: 1000, raising=False)

    root, directory, endpoint = (MagicMock(spec=Path) for _ in range(3))
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: "/tmp")
    monkeypatch.setattr(terminal, "Path", lambda _: root)
    root.resolve.return_value = root
    root.__str__.return_value = "/tmp"
    root.parents = ()
    root.__truediv__.return_value = directory
    directory.__truediv__.return_value = endpoint
    endpoint.__str__.return_value = "/tmp/row-ssh-1000/cm-test"
    root.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
    directory.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=1000)
    endpoint.lstat.side_effect = FileNotFoundError
    assert ssh_control_path_for_profile(profile) == str(endpoint)
    root.__truediv__.assert_called_with("row-ssh-1000")
    directory.mkdir.assert_called_with(mode=0o700, exist_ok=True)
    endpoint.lstat.side_effect = None

    endpoint.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=1000)
    assert ssh_control_path_for_profile(profile) == str(endpoint)
    endpoint.lstat.return_value.st_uid = 1001
    assert ssh_control_path_for_profile(profile) == ""
    endpoint.lstat.return_value.st_mode = stat.S_IFREG | 0o600
    assert ssh_control_path_for_profile(profile) == ""

    directory.lstat.return_value.st_mode = stat.S_IFDIR | 0o777
    assert ssh_control_path_for_profile(profile) == ""
    directory.lstat.return_value.st_mode = stat.S_IFDIR | 0o700
    directory.lstat.return_value.st_uid = 1001
    assert ssh_control_path_for_profile(profile) == ""
    directory.lstat.return_value.st_mode = stat.S_IFLNK | 0o700
    assert ssh_control_path_for_profile(profile) == ""
    directory.chmod.assert_not_called()

    root.lstat.return_value.st_mode = stat.S_IFDIR | 0o777
    assert ssh_control_path_for_profile(profile) == ""
    root.lstat.return_value.st_mode = stat.S_IFDIR | 0o755
    root.lstat.return_value.st_uid = 1001
    assert ssh_control_path_for_profile(profile) == ""
    root.lstat.return_value.st_mode = stat.S_IFREG | 0o755
    assert ssh_control_path_for_profile(profile) == ""
    root.__str__.return_value = "/tmp/%h"
    assert ssh_control_path_for_profile(profile) == ""
    root.__str__.return_value = "/tmp"
    root.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
    directory.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=1000)
    endpoint.lstat.side_effect = FileNotFoundError

    # OpenSSH has to fit the terminator and its temporary suffix too.
    path_factory = MagicMock(return_value=root)
    monkeypatch.setattr(terminal, "Path", path_factory)
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: "/configured")
    endpoint.__str__.return_value = "/" + "a" * 85
    assert ssh_control_path_for_profile(profile) == str(endpoint)
    assert path_factory.call_args_list == [call("/configured")]

    too_long = MagicMock(spec=Path)
    too_long.__str__.return_value = "/" + "a" * 86
    path_factory.reset_mock()
    directory.__truediv__.side_effect = [too_long, endpoint]
    assert ssh_control_path_for_profile(profile) == str(endpoint)
    assert path_factory.call_args_list == [call("/configured"), call("/tmp")]

    directory.mkdir.reset_mock()
    directory.__truediv__.side_effect = [too_long, too_long]
    assert ssh_control_path_for_profile(profile) == ""
    directory.mkdir.assert_not_called()

    directory.__truediv__.side_effect = None
    root.lstat.side_effect = OSError("read-only")
    assert ssh_control_path_for_profile(profile) == ""


@pytest.mark.skipif(os.name != "posix", reason="POSIX socket directory ownership")
def test_control_path_refuses_unsafe_existing_directory_or_link(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_SSH_CONTROL_PATH_MAX_BYTES", 4096)
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: str(tmp_path))
    profile = Profile(name="edge", protocol="ssh", host="target.example")
    directory = tmp_path / f"row-ssh-{os.geteuid()}"
    directory.mkdir()
    directory.chmod(0o777)
    assert ssh_control_path_for_profile(profile) == ""
    assert stat.S_IMODE(directory.stat().st_mode) == 0o777

    directory.rmdir()
    target = tmp_path / "other"
    target.mkdir(mode=0o700)
    directory.symlink_to(target, target_is_directory=True)
    assert ssh_control_path_for_profile(profile) == ""
    assert directory.is_symlink()
    assert list(target.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX socket directory ownership")
def test_control_path_refuses_replaceable_ancestors(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_SSH_CONTROL_PATH_MAX_BYTES", 4096)
    shared = tmp_path / "shared"
    shared.mkdir()
    shared.chmod(0o777)
    child = shared / "user-tmp"
    child.mkdir(mode=0o700)
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: str(child))
    profile = Profile(name="edge", protocol="ssh", host="target.example")
    assert ssh_control_path_for_profile(profile) == ""
    assert list(child.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX socket directory ownership")
def test_control_path_refuses_non_socket_at_expected_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(terminal, "_SSH_CONTROL_PATH_MAX_BYTES", 4096)
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: str(tmp_path))
    profile = Profile(name="edge", protocol="ssh", host="target.example")
    control_path = ssh_control_path_for_profile(profile)
    assert control_path
    path = Path(control_path)
    path.write_text("existing file", encoding="utf-8")
    assert ssh_control_path_for_profile(profile) == ""
    assert path.read_text(encoding="utf-8") == "existing file"


def test_ssh_connection_key_matches_launch_inputs_not_profile_labels() -> None:
    profile = Profile(name="edge", protocol="ssh", host="target.example", username="operator")
    key = ssh_connection_key(profile)
    assert ssh_connection_key(replace(profile, description="Updated label", port=22)) == key
    assert ssh_connection_key(replace(profile, options={"moba_monitoring_output": "cpu=2"})) == key
    for changes in (
        {"host": "other.example"},
        {"port": 2222},
        {"username": "admin"},
        {"identity_file": "another-key"},
        {"credential_ref": "another-entry"},
        {"options": {"proxy_jump": "jump.example"}},
        {"tunnels": [Tunnel(mode="dynamic", local_port=1080)]},
    ):
        assert ssh_connection_key(replace(profile, **changes)) != key


def test_control_path_command_handles_empty_unsupported_and_supported_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: False)

    assert ssh_command_with_control_path([], "/tmp/control", master=True) == []
    assert ssh_command_with_control_path(["ssh", "target"], "", master=True) == ["ssh", "target"]
    assert ssh_command_with_control_path(["curl", "https://example.com"], "/tmp/control", master=True) == [
        "curl",
        "https://example.com",
    ]

    adapted = ssh_command_with_control_path(["ssh", "target"], "/tmp/control", master=False)
    assert "ControlMaster=no" in adapted
    assert "ControlPath=/tmp/control" in adapted


def test_restored_terminal_plan_hardening_is_noop_or_note_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unchanged = terminal.TerminalPanePlan(title="local", command=["echo", "ready"])
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: False)
    assert terminal.harden_terminal_pane_plan_for_native_windows(unchanged) is unchanged

    monkeypatch.setattr(terminal, "_is_native_windows", lambda: True)
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    note = terminal._WINDOWS_OPENSSH_CONNECTION_SHARING_NOTE
    stale = terminal.TerminalPanePlan(
        title="edge",
        command=["ssh.exe", "-M", "operator@target.example"],
        notes=[note],
    )

    hardened = terminal.harden_terminal_pane_plan_for_native_windows(stale)

    assert hardened is not stale
    assert hardened.notes == [note]
