import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import remote_ops_workspace.cli as cli_module
import remote_ops_workspace.launcher as launcher_module
import remote_ops_workspace.snippets as snippets_module
import remote_ops_workspace.terminal as terminal_module
from remote_ops_workspace.audit import _redact
from remote_ops_workspace.broadcast import BroadcastPlan, build_broadcast_plans, run_broadcast
from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.file_transfer import (
    build_sftp_get_plan,
    build_sftp_interactive_plan,
    build_sftp_list_plan,
    build_sftp_put_plan,
)
from remote_ops_workspace.keys import build_keygen_plan
from remote_ops_workspace.launcher import LauncherError, LaunchPlan, build_launch_plan
from remote_ops_workspace.layouts import (
    Layout,
    LayoutPane,
    LayoutRunResult,
    LayoutStore,
    build_layout_terminal_plans,
    layout_splitter_size_lengths,
    parse_layout_pane,
    run_layout_terminal_plans,
    validate_layout,
)
from remote_ops_workspace.models import Profile, Tunnel
from remote_ops_workspace.network_tools import build_network_tool_plan
from remote_ops_workspace.snippets import Snippet, SnippetStore, run_snippet
from remote_ops_workspace.terminal import (
    _embedded_terminal_command,
    default_shell_command,
    harden_terminal_pane_plan_for_native_windows,
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    split_shell_plans,
    ssh_command_with_control_path,
    ssh_control_path_for_profile,
    terminal_plan_for_command,
    terminal_plan_for_profile,
    terminal_plan_for_sftp_browser,
)
from remote_ops_workspace.x11 import build_x_server_plan


def test_snippet_store_roundtrip(tmp_path: Path) -> None:
    store = SnippetStore(tmp_path / "snippets.json")
    store.add(Snippet(name="uptime", command="uptime", tags=["ops"]))
    assert store.get("uptime").argv == ["uptime"]
    assert store.load()[0].tags == ["ops"]


def test_snippet_rejects_empty_command() -> None:
    try:
        _ = Snippet(name="empty", command="").argv
    except ValueError as exc:
        assert "must not be empty" in str(exc) or "is required" in str(exc)
    else:
        raise AssertionError("empty snippet commands should be rejected")


def test_snippet_store_replaces_removes_and_reports_missing_names(tmp_path: Path) -> None:
    store = SnippetStore(tmp_path / "snippets.json")
    store.add(Snippet(name="first", command="true"))
    store.add(Snippet(name="uptime", command="uptime"))

    assert store.get("uptime").command == "uptime"

    with pytest.raises(ValueError, match="already exists"):
        store.add(Snippet(name="uptime", command="uptime --pretty"))

    store.add(Snippet(name="uptime", command="uptime --pretty"), replace=True)
    assert store.get("uptime").command == "uptime --pretty"

    store.remove("uptime")
    with pytest.raises(KeyError, match="uptime"):
        store.get("uptime")
    with pytest.raises(KeyError, match="uptime"):
        store.remove("uptime")


def test_run_snippet_supports_dry_run_and_checked_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        snippets_module.subprocess,
        "run",
        lambda argv, *, check: calls.append((argv, check)),
    )
    snippet = Snippet(name="ready", command="echo ready")

    assert run_snippet(snippet, dry_run=True) == ["echo", "ready"]
    assert calls == []
    assert run_snippet(snippet) == ["echo", "ready"]
    assert calls == [(["echo", "ready"], True)]


def test_layout_store_roundtrip(tmp_path: Path) -> None:
    store = LayoutStore(tmp_path / "layouts.json")
    layout = Layout(name="triage", orientation="horizontal", panes=[LayoutPane(profile="edge")])
    store.add(layout)
    assert store.get("triage").panes[0].profile == "edge"


def test_layout_store_replaces_removes_and_reports_missing_names(tmp_path: Path) -> None:
    store = LayoutStore(tmp_path / "layouts.json")
    first = Layout(name="first", panes=[LayoutPane(command="true")])
    triage = Layout(name="triage", panes=[LayoutPane(command="uptime")])
    store.add(first)
    store.add(triage)

    assert store.get("triage").panes[0].command == "uptime"
    with pytest.raises(ValueError, match="already exists"):
        store.add(triage)

    replacement = Layout(name="triage", panes=[LayoutPane(command="hostname")])
    store.add(replacement, replace=True)
    assert store.get("triage").panes[0].command == "hostname"

    store.remove("triage")
    with pytest.raises(KeyError, match="triage"):
        store.get("triage")
    with pytest.raises(KeyError, match="triage"):
        store.remove("triage")


def test_layout_pane_parser_defaults_to_profile_reference() -> None:
    assert parse_layout_pane("edge") == LayoutPane(profile="edge")
    assert parse_layout_pane("profile:core") == LayoutPane(profile="core")
    assert parse_layout_pane("command:uptime") == LayoutPane(command="uptime")


def test_layout_store_roundtrips_nested_splitter_sizes(tmp_path: Path) -> None:
    store = LayoutStore(tmp_path / "layouts.json")
    layout = Layout(
        name="grid",
        panes=[LayoutPane(command="whoami"), LayoutPane(command="hostname"), LayoutPane(command="uptime")],
        splitter_sizes=[[400, 300], [240, 160], [400]],
    )
    store.add(layout)

    restored = store.get("grid")
    assert restored.splitter_sizes == [[400, 300], [240, 160], [400]]
    assert layout_splitter_size_lengths(restored) == [2, 2, 1]


def test_layout_validation_rejects_invalid_splitter_size_shape() -> None:
    layout = Layout(
        name="broken",
        orientation="horizontal",
        panes=[LayoutPane(command="whoami"), LayoutPane(command="hostname")],
        splitter_sizes=[[200]],
    )
    try:
        validate_layout(layout)
    except ValueError as exc:
        assert "splitter_sizes" in str(exc)
    else:
        raise AssertionError("layout splitter sizes must match the saved splitter structure")


def test_layout_validation_rejects_orientation_splitter_count_and_nonpositive_sizes() -> None:
    panes = [LayoutPane(command="one"), LayoutPane(command="two")]
    with pytest.raises(ValueError, match="orientation must be one of"):
        validate_layout(Layout(name="bad", orientation="diagonal", panes=panes))
    with pytest.raises(ValueError, match="splitter entries"):
        validate_layout(
            Layout(
                name="bad-count",
                orientation="horizontal",
                panes=panes,
                splitter_sizes=[[100, 100], [50]],
            )
        )
    with pytest.raises(ValueError, match="positive integers"):
        validate_layout(
            Layout(
                name="bad-size",
                orientation="horizontal",
                panes=panes,
                splitter_sizes=[[100, 0]],
            )
        )


def test_layout_validation_rejects_empty_layout() -> None:
    try:
        validate_layout(Layout(name="empty", panes=[]))
    except ValueError as exc:
        assert "at least one pane" in str(exc)
    else:
        raise AssertionError("empty layouts should be rejected")


def test_layout_validation_rejects_ambiguous_pane() -> None:
    try:
        validate_layout(Layout(name="bad", panes=[LayoutPane(profile="edge", command="top")]))
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("layout panes should not accept both profile and command")


def test_layout_terminal_plans_include_profiles_and_commands(tmp_path: Path) -> None:
    from remote_ops_workspace.storage import ProfileStore

    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"))
    layout = Layout(
        name="triage",
        orientation="horizontal",
        panes=[LayoutPane(profile="edge"), LayoutPane(command="python -V", title="Version")],
    )
    plans = build_layout_terminal_plans(layout, store)
    assert [plan.title for plan in plans] == ["edge", "Version"]
    assert plans[0].command[0] == "ssh"
    assert plans[1].command == ["python", "-V"]


def test_layout_run_dry_run_returns_per_pane_results() -> None:
    layout = Layout(name="triage", panes=[LayoutPane(command="python -V", title="Version")])
    plans = build_layout_terminal_plans(layout)
    results = run_layout_terminal_plans(plans, dry_run=True)
    assert len(results) == 1
    assert results[0].dry_run is True
    assert results[0].pid is None
    assert results[0].command == ["python", "-V"]
    assert results[0].to_dict() == {
        "title": "Version",
        "command": ["python", "-V"],
        "pid": None,
        "dry_run": True,
    }


def test_layout_run_launches_each_process(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        pid = 42

    monkeypatch.setattr("remote_ops_workspace.layouts.subprocess.Popen", lambda _command: Process())
    results = run_layout_terminal_plans(
        [terminal_plan_for_command("python -V", title="Version")]
    )

    assert results == [LayoutRunResult("Version", ["python", "-V"], pid=42)]


@pytest.mark.parametrize(
    ("splitter_sizes", "message"),
    [
        (None, None),
        ("bad", "must be a list"),
        ([1], "entries must be lists"),
    ],
)
def test_layout_deserialization_validates_splitter_size_shape(splitter_sizes, message) -> None:
    payload = {
        "name": "layout",
        "panes": [{"command": "uptime"}],
        "splitter_sizes": splitter_sizes,
    }
    if message is None:
        assert Layout.from_dict(payload).splitter_sizes == []
    else:
        with pytest.raises(ValueError, match=message):
            Layout.from_dict(payload)


def test_terminal_plan_for_command_uses_argv_list() -> None:
    plan = terminal_plan_for_command("python -V", title="version")
    assert plan.title == "version"
    assert plan.command == ["python", "-V"]
    assert plan.source == "command"


def test_default_shell_command_is_platform_aware() -> None:
    assert default_shell_command({"COMSPEC": "powershell.exe"}, system="Windows") == ["powershell.exe"]
    assert default_shell_command({"SHELL": "/bin/zsh"}, system="Linux") == ["/bin/zsh"]


def test_split_shell_plans_have_real_commands() -> None:
    plans = split_shell_plans(2)
    assert [plan.title for plan in plans] == ["Shell 1", "Shell 2"]
    assert all(plan.command for plan in plans)


def test_terminal_plan_for_profile_uses_launcher() -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", username="admin")
    plan = terminal_plan_for_profile(profile)
    assert plan.title == "edge"
    assert plan.command[:2] == ["ssh", "-tt"]
    assert ["-p", "22"] == plan.command[plan.command.index("-p") : plan.command.index("-p") + 2]
    if terminal_module._is_native_windows():
        assert "ControlMaster=no" in plan.command
        socket_index = plan.command.index("-S")
        assert plan.command[socket_index : socket_index + 2] == ["-S", "none"]
        assert "ControlPersist=no" in plan.command
    else:
        assert not any(argument.startswith("Control") for argument in plan.command)
    assert "ConnectTimeout=10" in plan.command
    assert not any("StrictHostKeyChecking=" in argument for argument in plan.command)
    assert plan.command[-1] == "admin@192.0.2.10"
    assert any("10 second TCP connection timeout" in note for note in plan.notes)


def test_embedded_terminal_tty_adaptation_is_scoped_and_idempotent() -> None:
    ssh_profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")
    custom_profile = Profile(name="custom", protocol="custom", command="ssh example.invalid")

    assert _embedded_terminal_command(custom_profile, ["ssh", "example.invalid"]) == [
        "ssh",
        "example.invalid",
    ]
    for tty_flag in ("-t", "-tt", "-T"):
        command = ["ssh", tty_flag, "example.invalid"]
        adapted = _embedded_terminal_command(ssh_profile, command)
        assert adapted[:2] == ["ssh", tty_flag]
        assert "ConnectTimeout=10" in adapted
        assert not any("StrictHostKeyChecking=" in argument for argument in adapted)
        assert adapted[-1] == "example.invalid"


def test_embedded_terminal_preserves_explicit_ssh_safety_options() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid")
    command = [
        "ssh",
        "-o",
        "ConnectTimeout=30",
        "-oStrictHostKeyChecking=yes",
        "example.invalid",
    ]

    adapted = _embedded_terminal_command(profile, command)

    assert adapted[0:2] == ["ssh", "-tt"]
    assert adapted.count("ConnectTimeout=30") == 1
    assert adapted.count("-oStrictHostKeyChecking=yes") == 1
    assert "ConnectTimeout=10" not in adapted
    assert "StrictHostKeyChecking=accept-new" not in adapted


def test_openssh_runtime_overrides_replace_prompt_capable_options_without_mutation() -> None:
    original = [
        "C:\\Windows\\System32\\OpenSSH\\ssh.exe",
        "-o",
        "StrictHostKeyChecking=ask",
        "-oBatchMode=no",
        "-o",
        "ConnectTimeout=30",
        "operator@example.invalid",
    ]

    adapted = openssh_command_with_overrides(
        original,
        {
            "BatchMode": "yes",
            "ConnectTimeout": "5",
            "StrictHostKeyChecking": "yes",
        },
    )

    assert original[1:3] == ["-o", "StrictHostKeyChecking=ask"]
    assert adapted.count("BatchMode=yes") == 1
    assert adapted.count("ConnectTimeout=5") == 1
    assert adapted.count("StrictHostKeyChecking=yes") == 1
    assert not any("=ask" in argument or "=no" in argument for argument in adapted)
    assert adapted[-1] == "operator@example.invalid"


def test_ssh_control_socket_reuse_is_private_and_background_clients_cannot_create_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # The generated socket contract is intentionally POSIX-only.  Native
    # Windows OpenSSH cannot create the AF_UNIX socket used by ControlPath.
    if terminal_module._is_native_windows():
        return
    monkeypatch.setattr(terminal_module.tempfile, "gettempdir", lambda: str(tmp_path))
    profile = Profile(
        name="shared-edge",
        protocol="ssh",
        host="192.0.2.10",
        port=2222,
        username="operator",
    )

    control_path = ssh_control_path_for_profile(profile)
    assert control_path
    assert Path(control_path).parent == tmp_path / "remote-ops-workspace" / "ssh-control"

    terminal_command = ssh_command_with_control_path(
        ["ssh", "-o", "ControlMaster=no", "operator@192.0.2.10"],
        control_path,
        master=True,
    )
    background_command = ssh_command_with_control_path(
        ["sftp", "operator@192.0.2.10"],
        control_path,
        master=False,
    )
    assert "ControlMaster=auto" in terminal_command
    assert "ControlPath=" + control_path in terminal_command
    assert "ControlMaster=no" in background_command
    assert "ControlPath=" + control_path in background_command

    disabled = Profile(
        name="no-share",
        protocol="ssh",
        host="192.0.2.10",
        options={"ssh_multiplex": "false"},
    )
    assert ssh_control_path_for_profile(disabled) == ""
    explicitly_disabled = Profile(
        name="explicit-no-share",
        protocol="ssh",
        host="192.0.2.10",
        options={"ControlMaster": "no"},
    )
    assert ssh_control_path_for_profile(explicitly_disabled) == ""


def test_native_windows_openssh_skips_control_socket_reuse(monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    profile = Profile(
        name="windows-edge",
        protocol="ssh",
        host="192.0.2.10",
        username="operator",
    )
    command = ["ssh", "operator@192.0.2.10"]

    assert ssh_control_path_for_profile(profile) == ""
    assert ssh_command_with_control_path(
        command,
        r"C:\Users\operator\AppData\Local\Temp\cm-edge",
        master=True,
    ) == [
        "ssh",
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
        "-o",
        "ControlPath=none",
        "operator@192.0.2.10",
    ]


def test_native_windows_openssh_removes_stale_connection_sharing_options(
    monkeypatch,
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    original = [
        "ssh.exe",
        "-M",
        "-S",
        r"C:\Temp\remote-ops-control.sock",
        "-o",
        "ControlMaster=auto",
        "-oControlPath=C:/Temp/remote-ops-control.sock",
        "-o",
        "ControlPersist=10m",
        "-o",
        "StrictHostKeyChecking=yes",
        "operator@example.invalid",
    ]

    adapted = openssh_command_without_windows_connection_sharing(original)

    assert original[1:4] == ["-M", "-S", r"C:\Temp\remote-ops-control.sock"]
    assert adapted == [
        "ssh.exe",
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
        "-o",
        "ControlPath=none",
        "-o",
        "StrictHostKeyChecking=yes",
        "operator@example.invalid",
    ]


@pytest.mark.parametrize(
    "jump_arguments",
    [
        ["-J", "jump-user@bastion.example:2222"],
        ["-Jjump-user@bastion.example:2222"],
        ["-o", "ProxyJump=jump-user@bastion.example:2222"],
        ["-oProxyJump=jump-user@bastion.example:2222"],
    ],
)
def test_native_windows_openssh_hardens_proxy_jump_child(
    monkeypatch,
    jump_arguments: list[str],
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    ssh = r"C:\Windows\System32\OpenSSH\ssh.exe"
    config = r"C:\Users\operator\ssh config"
    original = [
        ssh,
        "-F",
        config,
        *jump_arguments,
        "-o",
        "StrictHostKeyChecking=yes",
        "operator@target.example",
    ]

    adapted = openssh_command_without_windows_connection_sharing(original)
    proxy_option = next(
        argument for argument in adapted if argument.startswith("ProxyCommand=")
    )
    expected_child = subprocess.list2cmdline(
        [
            ssh,
            "-F",
            config,
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
            "jump-user@bastion.example",
        ]
    )

    assert original[-1] == "operator@target.example"
    assert not any(
        argument == "-J"
        or argument.startswith("-J")
        or "ProxyJump=jump-user" in argument
        for argument in adapted
    )
    assert proxy_option == f"ProxyCommand={expected_child}"
    assert "StrictHostKeyChecking=yes" in adapted
    assert "StrictHostKeyChecking" not in expected_child
    assert adapted[-1] == "operator@target.example"


@pytest.mark.parametrize(
    "jump_arguments",
    [
        ["-J", "none"],
        ["-Jnone"],
        ["-J", "NoNe"],
        ["-JNoNe"],
    ],
)
def test_native_windows_openssh_preserves_disabled_proxy_jump(
    monkeypatch,
    jump_arguments: list[str],
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    original = ["ssh.exe", *jump_arguments, "operator@target.example"]

    adapted = openssh_command_without_windows_connection_sharing(original)

    assert not any(argument.startswith("ProxyCommand=") for argument in adapted)
    start = adapted.index(jump_arguments[0])
    assert adapted[start : start + len(jump_arguments)] == jump_arguments
    assert adapted[-1] == "operator@target.example"


@pytest.mark.parametrize(
    "jump_spec",
    [
        "first.example,second.example",
        "bastion.example&calc.exe",
        "user@[fe80::1%12]",
        " bastion.example",
        "bastion.example:70000",
    ],
)
def test_native_windows_openssh_rejects_unprovable_proxy_jump_forms(
    monkeypatch,
    jump_spec: str,
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)

    with pytest.raises(ValueError, match="native Windows"):
        openssh_command_without_windows_connection_sharing(
            ["ssh.exe", "-J", jump_spec, "target.example"]
        )


@pytest.mark.parametrize(
    ("stale", "preserved"),
    [
        (["-MN"], ["-N"]),
        (["-Sfoo"], []),
        (["-MSfoo"], []),
        (["-vMSfoo"], ["-v"]),
        (["-NvS", "foo"], ["-Nv"]),
        (["-vMp22"], ["-vp22"]),
        (["-p22MSfoo"], ["-p22MSfoo"]),
    ],
)
def test_native_windows_openssh_removes_clustered_mux_short_options(
    monkeypatch,
    stale: list[str],
    preserved: list[str],
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    target = "operator@example.invalid"

    adapted = openssh_command_without_windows_connection_sharing(
        ["ssh.exe", *stale, target]
    )

    assert adapted[:7] == [
        "ssh.exe",
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
    ]
    assert adapted[7:] == ["-o", "ControlPath=none", *preserved, target]


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows OpenSSH contract")
@pytest.mark.parametrize(
    "stale",
    [[], ["-MN"], ["-Sfoo"], ["-MSfoo"], ["-vMSfoo"]],
)
def test_native_windows_openssh_standalone_switch_overrides_mux_config(
    tmp_path: Path,
    stale: list[str],
) -> None:
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")
    if ssh is None:
        pytest.skip("native OpenSSH client is unavailable")
    config = tmp_path / "mux-enabled-ssh-config"
    config.write_text(
        "Host *\n"
        "    ControlMaster auto\n"
        "    ControlPath C:/remote-ops-workspace-test-control.sock\n"
        "    ControlPersist 10m\n",
        encoding="utf-8",
    )
    target = "operator@example.invalid"
    runtime = openssh_command_without_windows_connection_sharing(
        [ssh, *stale, "-F", str(config), target]
    )

    probe = subprocess.run(
        [*runtime[:-1], "-G", target],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    effective = {
        line.split(maxsplit=1)[0].lower(): line.split(maxsplit=1)[1].strip().lower()
        for line in probe.stdout.splitlines()
        if len(line.split(maxsplit=1)) == 2
    }

    assert runtime[1:3] == ["-S", "none"]
    assert effective["controlmaster"] == "false"
    assert effective.get("controlpath", "none") == "none"
    assert effective["controlpersist"] in {"0", "no"}


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows OpenSSH contract")
def test_native_windows_proxy_jump_effective_parent_and_child_are_hardened(
    tmp_path: Path,
) -> None:
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")
    if ssh is None:
        pytest.skip("native OpenSSH client is unavailable")
    known_hosts = tmp_path / "jump-known-hosts"
    config = tmp_path / "proxy-jump-config"
    config.write_text(
        "Host bastion\n"
        "    HostName bastion.example.invalid\n"
        "    StrictHostKeyChecking yes\n"
        f"    UserKnownHostsFile {known_hosts.as_posix()}\n"
        "    ControlMaster auto\n"
        "    ControlPath C:/unsafe-configured-control.sock\n"
        "    ControlPersist yes\n"
        "    ProxyJump nested.example.invalid\n"
        "Host target.example.invalid\n"
        "    ProxyJump config-only.example.invalid\n",
        encoding="utf-8",
    )
    target = "target.example.invalid"
    runtime = openssh_command_without_windows_connection_sharing(
        [ssh, "-F", str(config), "-J", "bastion", target]
    )
    expected_child = [
        ssh,
        "-F",
        str(config),
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
        "-W",
        "[%h]:%p",
        "--",
        "bastion",
    ]
    expected_proxy_command = subprocess.list2cmdline(expected_child)

    parent_probe = subprocess.run(
        [*runtime[:-1], "-G", target],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    parent_effective = {
        line.split(maxsplit=1)[0].lower(): line.split(maxsplit=1)[1].strip()
        for line in parent_probe.stdout.splitlines()
        if len(line.split(maxsplit=1)) == 2
    }
    assert parent_effective["proxycommand"].casefold() == expected_proxy_command.casefold()
    assert "config-only.example.invalid" not in parent_effective["proxycommand"]
    assert parent_effective["controlmaster"].lower() == "false"
    assert parent_effective.get("controlpath", "none").lower() == "none"
    assert parent_effective["controlpersist"].lower() in {"0", "no"}

    # ``-W`` is irrelevant to configuration expansion, so replace it with -G
    # and prove the exact child flags win over the jump host's hostile mux and
    # nested-proxy stanza without weakening that host's verification policy.
    child_probe_args = expected_child[: expected_child.index("-W")]
    child_probe = subprocess.run(
        [*child_probe_args, "-G", "bastion"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    child_effective = {
        line.split(maxsplit=1)[0].lower(): line.split(maxsplit=1)[1].strip().lower()
        for line in child_probe.stdout.splitlines()
        if len(line.split(maxsplit=1)) == 2
    }
    assert child_effective["hostname"] == "bastion.example.invalid"
    assert child_effective["controlmaster"] == "false"
    assert child_effective.get("controlpath", "none") == "none"
    assert child_effective["controlpersist"] in {"0", "no"}
    assert child_effective["stricthostkeychecking"] == "true"
    assert "proxycommand" not in child_effective


def test_non_windows_openssh_preserves_connection_sharing_options(monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: False)
    command = [
        "ssh",
        "-o",
        "ControlMaster=auto",
        "-oControlPath=/tmp/remote-ops.sock",
        "operator@example.invalid",
    ]

    assert openssh_command_without_windows_connection_sharing(command) == command


def test_sftp_list_plan_uses_batch_stdin() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10", username="admin")
    plan = build_sftp_list_plan(profile, "/var/log")
    assert plan.command[:3] == ["sftp", "-b", "-"]
    assert "-P" in plan.command
    assert plan.command[-1] == "admin@192.0.2.10"
    assert plan.batch_commands == ["ls -la /var/log"]
    assert plan.batch_input().endswith("\n")


def test_sftp_put_plan_quotes_paths_with_spaces() -> None:
    profile = Profile(name="files", protocol="sftp", host="192.0.2.10")
    local_path = Path("local dir/report.txt")
    plan = build_sftp_put_plan(profile, local_path, remote_path="/tmp/report copy.txt")
    assert plan.batch_commands == [f"put '{local_path}' '/tmp/report copy.txt'"]


def test_sftp_get_plan_rejects_option_like_remote_path() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    try:
        build_sftp_get_plan(profile, "-bad")
    except ValueError as exc:
        assert "remote path must not start with '-'" in str(exc)
    else:
        raise AssertionError("option-like SFTP remote paths should be rejected")


def test_sftp_browser_rejects_non_ssh_profiles() -> None:
    try:
        build_sftp_interactive_plan(Profile(name="web", protocol="https", url="https://example.com"))
    except ValueError as exc:
        assert "requires an ssh or sftp profile" in str(exc)
    else:
        raise AssertionError("SFTP browser should reject non-SSH profiles")


def test_terminal_plan_for_sftp_browser_uses_interactive_sftp() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10", username="admin")
    plan = terminal_plan_for_sftp_browser(profile)
    assert plan.title == "Files: files"
    assert plan.command[0] == "sftp"
    assert plan.command[-1] == "admin@192.0.2.10"
    assert plan.source == "sftp:files"


def test_native_windows_sftp_browser_removes_stale_connection_sharing_options(
    monkeypatch,
) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    monkeypatch.setattr(
        terminal_module,
        "build_sftp_interactive_plan",
        lambda _profile: LaunchPlan(
            "sftp",
            [
                "sftp.exe",
                "-o",
                "ControlMaster=auto",
                "-oControlPath=C:/Temp/remote-ops-control.sock",
                "-o",
                "ControlPersist=10m",
                "admin@example.invalid",
            ],
            ["restored SFTP plan"],
        ),
    )

    plan = terminal_plan_for_sftp_browser(
        Profile(name="files", protocol="ssh", host="example.invalid", username="admin")
    )

    assert "ControlPath=none" in plan.command
    assert "ControlMaster=no" in plan.command
    assert "ControlPersist=no" in plan.command
    assert not any("remote-ops-control.sock" in argument for argument in plan.command)
    assert any("connection sharing options were ignored" in note for note in plan.notes)


def test_native_windows_restored_terminal_plan_is_hardened(monkeypatch) -> None:
    monkeypatch.setattr(terminal_module, "_is_native_windows", lambda: True)
    plan = harden_terminal_pane_plan_for_native_windows(
        terminal_module.TerminalPanePlan(
            title="restored",
            command=[
                "ssh.exe",
                "-S",
                r"C:\Temp\remote-ops-control.sock",
                "-o",
                "ControlMaster=auto",
                "operator@example.invalid",
            ],
            source="restored-layout",
        )
    )

    assert plan.command[1:7] == [
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
    ]
    assert any("connection sharing options were ignored" in note for note in plan.notes)


def test_keygen_plan_uses_ssh_keygen(tmp_path: Path) -> None:
    plan = build_keygen_plan(tmp_path / "id_ed25519", comment="lab")
    assert plan.command[:2] == ["ssh-keygen", "-t"]
    assert "ed25519" in plan.command
    assert "lab" in plan.command


def test_keygen_plan_redacts_env_passphrase(tmp_path: Path) -> None:
    plan = build_keygen_plan(tmp_path / "id_ed25519", passphrase="top-secret")
    assert plan.native is True
    assert "top-secret" not in plan.command
    assert "top-secret" not in plan.printable()
    assert "***REDACTED***" in plan.command


def test_fido_keygen_rejects_env_passphrase(tmp_path: Path) -> None:
    try:
        build_keygen_plan(tmp_path / "id_ed25519_sk", key_type="ed25519-sk", passphrase="top-secret")
    except ValueError as exc:
        assert "--passphrase-env is not supported" in str(exc)
    else:
        raise AssertionError("FIDO keygen passphrase should not be accepted through argv/env automation")


def test_fido_keygen_plan_supports_resident_keys(tmp_path: Path) -> None:
    plan = build_keygen_plan(tmp_path / "id_ed25519_sk", key_type="ed25519-sk", resident=True)
    assert "ed25519-sk" in plan.command
    assert "resident" in plan.command


def test_network_tool_plan_uses_argv_list() -> None:
    target = "192.0.2.1"
    plan = build_network_tool_plan("ping", target, count=1)
    assert plan.command[0] == "ping"
    assert plan.command[-1] == target


def test_network_tool_rejects_option_like_target() -> None:
    try:
        build_network_tool_plan("ping", "-I")
    except ValueError as exc:
        assert "must not start with '-'" in str(exc)
    else:
        raise AssertionError("option-like network targets should be rejected")


def test_ssh_proxy_jump_and_tunnels() -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        options={"proxy_jump": "bastion"},
        tunnels=[Tunnel(mode="dynamic", local_port=1080)],
    )
    plan = build_launch_plan(profile)
    assert "-J" in plan.command
    assert "bastion" in plan.command
    assert "-D" in plan.command
    assert "127.0.0.1:1080" in plan.command


def test_ssh_option_depth_builds_open_ssh_options() -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        identity_file="/home/me/.ssh/id_ed25519",
        options={
            "compression": "true",
            "connect_timeout": "10",
            "keepalive_interval": "30",
            "keepalive_count": "3",
            "strict_host_key_checking": "accept-new",
            "user_known_hosts_file": "/tmp/known_hosts",
            "log_level": "error",
            "ciphers": "aes256-gcm@openssh.com,chacha20-poly1305@openssh.com",
            "forward_agent": "yes",
        },
    )
    plan = build_launch_plan(profile)
    assert "-C" in plan.command
    assert "-A" in plan.command
    assert "ConnectTimeout=10" in plan.command
    assert "ServerAliveInterval=30" in plan.command
    assert "ServerAliveCountMax=3" in plan.command
    assert "StrictHostKeyChecking=accept-new" in plan.command
    assert "UserKnownHostsFile=/tmp/known_hosts" in plan.command
    assert "LogLevel=ERROR" in plan.command
    assert "Ciphers=aes256-gcm@openssh.com,chacha20-poly1305@openssh.com" in plan.command


def test_ssh_smartcard_certificate_options_build_open_ssh_args() -> None:
    profile = Profile(
        name="smartcard-edge",
        protocol="ssh",
        host="192.0.2.10",
        username="admin",
        options={
            "smartcard_auth": "true",
            "smartcard_provider": "microsoft-capi",
            "pkcs11_provider": "/usr/lib/opensc-pkcs11.so",
            "certificate_file": "/home/admin/.ssh/id_ed25519-cert.pub",
            "identity_agent": "/tmp/ssh-agent.sock",
            "security_key_provider": "internal",
        },
    )
    plan = build_launch_plan(profile)

    assert plan.command[:3] == ["ssh", "-p", "22"]
    assert "-I" in plan.command
    assert "/usr/lib/opensc-pkcs11.so" in plan.command
    assert "CertificateFile=/home/admin/.ssh/id_ed25519-cert.pub" in plan.command
    assert "IdentityAgent=/tmp/ssh-agent.sock" in plan.command
    assert "SecurityKeyProvider=internal" in plan.command
    assert plan.command[-1] == "admin@192.0.2.10"
    assert any("Smart-card/certificate SSH auth requested" in note for note in plan.notes)
    assert any("Microsoft CryptoAPI/CAPI smart-card provider requested" in note for note in plan.notes)


def test_mosh_option_depth_builds_flags_and_ssh_handoff() -> None:
    profile = Profile(
        name="mobile",
        protocol="mosh",
        host="192.0.2.10",
        port=2222,
        username="admin",
        identity_file="/home/me/.ssh/id_ed25519",
        options={
            "agent_forward": "true",
            "compression": "true",
            "mosh_port": "60000:60010",
            "predict": "always",
            "bind_server": "any",
        },
    )
    plan = build_launch_plan(profile)
    assert plan.command[0] == "mosh"
    assert "--port=60000:60010" in plan.command
    assert "--predict=always" in plan.command
    assert "--bind-server=any" in plan.command
    assert "ssh -p 2222 -i /home/me/.ssh/id_ed25519 -C -A" in plan.command
    assert plan.command[-1] == "admin@192.0.2.10"


def test_rdp_option_depth_builds_freerdp_args() -> None:
    original_windows = launcher_module._is_windows
    original_first_available = launcher_module._first_available
    launcher_module._is_windows = lambda: False
    launcher_module._first_available = lambda candidates: "xfreerdp"
    try:
        profile = Profile(
            name="desk",
            protocol="rdp",
            host="192.0.2.20",
            username="administrator",
            options={
                "domain": "LAB",
                "geometry": "1600x900",
                "cert_ignore": "true",
                "clipboard": "false",
                "drive": "share,/tmp/share",
                "scale": "140",
                "security": "nla",
                "audio": "true",
                "multimon": "true",
            },
        )
        plan = build_launch_plan(profile)
    finally:
        launcher_module._is_windows = original_windows
        launcher_module._first_available = original_first_available
    assert plan.command[:3] == ["xfreerdp", "/v:192.0.2.20:3389", "/u:administrator"]
    assert "/d:LAB" in plan.command
    assert "/w:1600" in plan.command
    assert "/h:900" in plan.command
    assert "/dynamic-resolution" in plan.command
    assert "/cert:ignore" in plan.command
    assert "/clipboard:false" in plan.command
    assert "/drive:share,/tmp/share" in plan.command
    assert "/scale:140" in plan.command
    assert "/sec:nla" in plan.command
    assert "/sound" in plan.command
    assert "/multimon" in plan.command


def test_rdp_native_security_requires_isolated_legacy_opt_in() -> None:
    original_windows = launcher_module._is_windows
    launcher_module._is_windows = lambda: False
    try:
        profile = Profile(
            name="xp",
            protocol="rdp",
            host="192.0.2.20",
            options={"security": "rdp"},
        )
        try:
            build_launch_plan(profile)
        except LauncherError as exc:
            assert "allow_legacy_rdp_security=true" in str(exc)
        else:
            raise AssertionError("RDP native security should require explicit XP legacy opt-in")
    finally:
        launcher_module._is_windows = original_windows


def test_windows_rdp_native_security_requires_isolated_legacy_opt_in() -> None:
    original_windows = launcher_module._is_windows
    launcher_module._is_windows = lambda: True
    try:
        profile = Profile(
            name="xp",
            protocol="rdp",
            host="192.0.2.20",
            options={"security": "rdp", "allow_legacy_rdp_security": "true"},
        )
        try:
            build_launch_plan(profile)
        except LauncherError as exc:
            assert "legacy_target=windows-xp-32/windows-xp-64" in str(exc)
        else:
            raise AssertionError("Windows RDP native security should require an XP legacy target")
    finally:
        launcher_module._is_windows = original_windows


def test_rdp_native_security_rejects_generic_xp_legacy_target_alias() -> None:
    original_windows = launcher_module._is_windows
    launcher_module._is_windows = lambda: False
    try:
        profile = Profile(
            name="xp",
            protocol="rdp",
            host="192.0.2.20",
            options={
                "security": "rdp",
                "legacy_target": "windows-xp",
                "allow_legacy_rdp_security": "true",
            },
        )
        try:
            build_launch_plan(profile)
        except LauncherError as exc:
            assert "legacy_target=windows-xp-32/windows-xp-64" in str(exc)
        else:
            raise AssertionError("generic XP legacy target alias should not unlock RDP native security")
    finally:
        launcher_module._is_windows = original_windows


def test_rdp_native_security_allows_explicit_xp_remote_target_profile() -> None:
    original_windows = launcher_module._is_windows
    original_first_available = launcher_module._first_available
    launcher_module._is_windows = lambda: False
    launcher_module._first_available = lambda candidates: "xfreerdp"
    try:
        profile = Profile(
            name="xp",
            protocol="rdp",
            host="192.0.2.20",
            options={
                "security": "rdp",
                "legacy_target": "windows-xp-32",
                "allow_legacy_rdp_security": "true",
            },
        )
        plan = build_launch_plan(profile)
    finally:
        launcher_module._is_windows = original_windows
        launcher_module._first_available = original_first_available
    assert "/sec:rdp" in plan.command


def test_windows_rdp_option_depth_builds_mstsc_args() -> None:
    original_windows = launcher_module._is_windows
    launcher_module._is_windows = lambda: True
    try:
        profile = Profile(
            name="desk",
            protocol="rdp",
            host="192.0.2.20",
            options={"admin": "true", "fullscreen": "true", "multimon": "true", "prompt": "true"},
        )
        plan = build_launch_plan(profile)
    finally:
        launcher_module._is_windows = original_windows
    assert plan.command == ["mstsc", "/v:192.0.2.20:3389", "/f", "/admin", "/multimon", "/prompt"]


def test_vnc_option_depth_builds_viewer_args() -> None:
    profile = Profile(
        name="console",
        protocol="vnc",
        host="192.0.2.30",
        options={
            "fullscreen": "true",
            "view_only": "true",
            "shared": "true",
            "geometry": "1280x720",
            "password_file": "/tmp/vnc.pass",
            "encoding": "tight",
            "quality": "7",
            "compression": "4",
        },
    )
    plan = build_launch_plan(profile)
    assert "-FullScreen" in plan.command
    assert "-ViewOnly" in plan.command
    assert "-Shared" in plan.command
    assert "-geometry" in plan.command
    assert "1280x720" in plan.command
    assert "-passwd" in plan.command
    assert "/tmp/vnc.pass" in plan.command
    assert "-PreferredEncoding" in plan.command
    assert "tight" in plan.command
    assert "-QualityLevel" in plan.command
    assert "7" in plan.command
    assert "-CompressLevel" in plan.command
    assert "4" in plan.command


def test_spice_option_depth_builds_remote_viewer_args() -> None:
    profile = Profile(
        name="vm",
        protocol="spice",
        host="192.0.2.40",
        options={"fullscreen": "true", "title": "Lab VM", "zoom": "125", "audio": "false"},
    )
    plan = build_launch_plan(profile)
    assert "--full-screen" in plan.command
    assert "--title" in plan.command
    assert "Lab VM" in plan.command
    assert "--zoom=125" in plan.command
    assert "--spice-disable-audio" in plan.command
    assert plan.command[-1] == "spice://192.0.2.40:5900"


def test_x2go_option_depth_builds_session_args() -> None:
    profile = Profile(
        name="linux-desktop",
        protocol="x2go",
        host="192.0.2.50",
        username="admin",
        port=2222,
        options={
            "session": "xfce-lab",
            "session_type": "XFCE",
            "command": "XFCE",
            "geometry": "1440x900",
            "fullscreen": "true",
            "link": "lan",
            "pack": "16m-jpeg",
        },
    )
    plan = build_launch_plan(profile)
    assert "--session" in plan.command
    assert "xfce-lab" in plan.command
    assert "--session-type" in plan.command
    assert "XFCE" in plan.command
    assert "--command" in plan.command
    assert "--geometry" in plan.command
    assert "1440x900" in plan.command
    assert "--fullscreen" in plan.command
    assert "--link" in plan.command
    assert "lan" in plan.command
    assert "--pack" in plan.command
    assert "16m-jpeg" in plan.command


def test_serial_option_depth_builds_putty_sercfg() -> None:
    original_windows = launcher_module._is_windows
    launcher_module._is_windows = lambda: True
    try:
        profile = Profile(
            name="switch",
            protocol="serial",
            path="COM3",
            options={"baud": "9600", "data_bits": "7", "parity": "even", "stop_bits": "2", "flow": "rtscts"},
        )
        plan = build_launch_plan(profile)
    finally:
        launcher_module._is_windows = original_windows
    assert plan.command == ["putty", "-serial", "COM3", "-sercfg", "9600,7,e,2,R"]


def test_launch_rejects_option_like_host() -> None:
    try:
        build_launch_plan(Profile(name="bad", protocol="ssh", host="-oProxyCommand=calc"))
    except ValueError as exc:
        assert "must not start with '-'" in str(exc)
    else:
        raise AssertionError("option-like hosts should be rejected")


def test_proxy_command_requires_explicit_unsafe_opt_in() -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        options={"proxy_command": "nc %h %p"},
    )
    try:
        build_launch_plan(profile)
    except LauncherError as exc:
        assert "proxy_command is disabled" in str(exc)
    else:
        raise AssertionError("proxy_command should require explicit opt-in")


def test_proxy_command_allows_explicit_unsafe_opt_in() -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        options={"proxy_command": "nc %h %p", "allow_unsafe_proxy_command": "true"},
    )
    plan = build_launch_plan(profile)
    assert "-o" in plan.command
    assert "ProxyCommand=nc %h %p" in plan.command


def test_url_launcher_rejects_unsafe_scheme() -> None:
    try:
        build_launch_plan(Profile(name="bad", protocol="http", url="file:///C:/Windows/System32/calc.exe"))
    except ValueError as exc:
        assert "url scheme" in str(exc)
    else:
        raise AssertionError("non-http URL schemes should be rejected")


def test_windows_url_launcher_avoids_cmd_start() -> None:
    original = launcher_module._is_windows
    launcher_module._is_windows = lambda: True
    try:
        plan = build_launch_plan(Profile(name="docs", protocol="https", url="https://example.com"))
    finally:
        launcher_module._is_windows = original
    assert plan.command[:2] == ["rundll32.exe", "url.dll,FileProtocolHandler"]
    assert "cmd" not in plan.command


def test_raw_socket_requires_explicit_port() -> None:
    try:
        build_launch_plan(Profile(name="raw", protocol="raw", host="192.0.2.10"))
    except ValueError as exc:
        assert "raw profile requires explicit port" in str(exc)
    else:
        raise AssertionError("raw socket profiles should require an explicit port")


def test_broadcast_builds_ssh_command_per_profile() -> None:
    profiles = [
        Profile(name="a", protocol="ssh", host="192.0.2.10"),
        Profile(name="b", protocol="ssh", host="192.0.2.11"),
    ]
    plans = build_broadcast_plans(profiles, "hostname")
    assert len(plans) == 2
    assert plans[0].profile_name == "a"
    assert plans[0].command[-1] == "hostname"


def test_broadcast_dry_run_returns_per_profile_results() -> None:
    plans = build_broadcast_plans([Profile(name="a", protocol="ssh", host="192.0.2.10")], "hostname")
    results = run_broadcast(plans, dry_run=True)
    assert len(results) == 1
    assert results[0].profile_name == "a"
    assert results[0].dry_run is True
    assert results[0].ok is True
    assert results[0].to_dict()["ok"] is True


def test_broadcast_rejects_multiline_command() -> None:
    try:
        build_broadcast_plans([Profile(name="a", protocol="ssh", host="192.0.2.10")], "hostname\nwhoami")
    except ValueError as exc:
        assert "control characters" in str(exc) or "single line" in str(exc)
    else:
        raise AssertionError("multiline broadcast commands should be rejected")


def test_broadcast_rejects_non_ssh_profiles() -> None:
    with pytest.raises(ValueError, match="supports ssh profiles only"):
        build_broadcast_plans(
            [Profile(name="web", protocol="https", url="https://example.invalid")],
            "hostname",
        )


def test_broadcast_executes_commands_and_reports_process_output(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = BroadcastPlan("edge", ["ssh", "edge", "hostname"], ["test"])

    monkeypatch.setattr(
        "remote_ops_workspace.broadcast.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 7, "stdout", "stderr"),
    )

    result = run_broadcast([plan], timeout=3)[0]

    assert plan.printable() == "ssh edge hostname"
    assert result.returncode == 7
    assert result.stdout == "stdout"
    assert result.stderr == "stderr"
    assert not result.ok


def test_broadcast_timeout_decodes_partial_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = BroadcastPlan("edge", ["ssh", "edge", "hostname"], [])

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            plan.command,
            2,
            output=b"partial-\xff",
            stderr=None,
        )

    monkeypatch.setattr("remote_ops_workspace.broadcast.subprocess.run", timeout)

    result = run_broadcast([plan], timeout=2)[0]

    assert result.returncode == 124
    assert result.stdout == "partial-\ufffd"
    assert result.stderr == "timed out after 2 seconds"


def test_x11_plan_is_argv_list() -> None:
    plan = build_x_server_plan(":9")
    assert isinstance(plan.command, list)
    assert plan.command


def test_x11_rejects_invalid_display() -> None:
    try:
        build_x_server_plan("not-a-display")
    except ValueError as exc:
        assert "display must start" in str(exc)
    else:
        raise AssertionError("invalid X display names should be rejected")


def test_vault_get_requires_private_output_file() -> None:
    try:
        build_parser().parse_args(["vault", "get", "prod/router-password"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("vault get should require --out")


def test_vault_get_writes_secret_only_to_private_file(tmp_path: Path, monkeypatch, capsys) -> None:
    class FakeVault:
        def get(self, _name: str, _passphrase: str) -> str:
            return "top-secret"

    output = tmp_path / "retrieved-secret"
    args = build_parser().parse_args(["vault", "get", "prod/router-password", "--out", str(output)])
    monkeypatch.setattr(cli_module, "LocalVault", FakeVault)
    monkeypatch.setattr(cli_module, "_vault_passphrase", lambda **_kwargs: "passphrase")

    assert cli_module.cmd_vault_get(args) == 0
    assert output.read_text(encoding="utf-8") == "top-secret"
    assert capsys.readouterr().out == f"secret written: {output}\n"


def test_audit_redacts_secret_command_arguments() -> None:
    payload = {"command": ["ssh-keygen", "-N", "top-secret"], "api_token": "abc"}
    redacted = _redact(payload)
    assert redacted["command"] == ["ssh-keygen", "-N", "***REDACTED***"]
    assert redacted["api_token"] == "***REDACTED***"
