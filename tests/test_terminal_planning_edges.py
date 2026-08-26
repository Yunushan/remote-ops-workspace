from __future__ import annotations

from pathlib import Path

import pytest

import remote_ops_workspace.terminal as terminal
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    split_shell_plans,
    ssh_command_with_control_path,
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: False)
    monkeypatch.setattr(terminal.tempfile, "gettempdir", lambda: str(tmp_path))

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
    control_path = ssh_control_path_for_profile(profile)
    directory = Path(control_path).parent
    assert directory == tmp_path / "remote-ops-workspace" / "ssh-control"
    assert directory.exists()

    original_mkdir = Path.mkdir

    def fail_mkdir(_path: Path, *args: object, **kwargs: object) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    assert ssh_control_path_for_profile(profile) == ""
    monkeypatch.setattr(Path, "mkdir", original_mkdir)


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
