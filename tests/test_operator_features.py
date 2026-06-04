from pathlib import Path

import remote_ops_workspace.launcher as launcher_module
from remote_ops_workspace.audit import _redact
from remote_ops_workspace.broadcast import build_broadcast_plans, run_broadcast
from remote_ops_workspace.cli import build_parser, cmd_vault_get
from remote_ops_workspace.file_transfer import (
    build_sftp_get_plan,
    build_sftp_interactive_plan,
    build_sftp_list_plan,
    build_sftp_put_plan,
)
from remote_ops_workspace.keys import build_keygen_plan
from remote_ops_workspace.launcher import LauncherError, build_launch_plan
from remote_ops_workspace.layouts import (
    Layout,
    LayoutPane,
    LayoutStore,
    build_layout_terminal_plans,
    run_layout_terminal_plans,
    validate_layout,
)
from remote_ops_workspace.models import Profile, Tunnel
from remote_ops_workspace.network_tools import build_network_tool_plan
from remote_ops_workspace.snippets import Snippet, SnippetStore
from remote_ops_workspace.terminal import (
    default_shell_command,
    split_shell_plans,
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


def test_layout_store_roundtrip(tmp_path: Path) -> None:
    store = LayoutStore(tmp_path / "layouts.json")
    layout = Layout(name="triage", orientation="horizontal", panes=[LayoutPane(profile="edge")])
    store.add(layout)
    assert store.get("triage").panes[0].profile == "edge"


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
    assert plan.command[:3] == ["ssh", "-p", "22"]
    assert plan.command[-1] == "admin@192.0.2.10"


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
    plan = build_network_tool_plan("ping", "example.com", count=1)
    assert plan.command[0] == "ping"
    assert "example.com" in plan.command


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


def test_vault_get_requires_explicit_reveal_mode() -> None:
    args = build_parser().parse_args(["vault", "get", "prod/router-password"])
    try:
        cmd_vault_get(args)
    except ValueError as exc:
        assert "refusing to print secret by default" in str(exc)
    else:
        raise AssertionError("vault get should require --show or --out")


def test_audit_redacts_secret_command_arguments() -> None:
    payload = {"command": ["ssh-keygen", "-N", "top-secret"], "api_token": "abc"}
    redacted = _redact(payload)
    assert redacted["command"] == ["ssh-keygen", "-N", "***REDACTED***"]
    assert redacted["api_token"] == "***REDACTED***"
