from __future__ import annotations

from types import SimpleNamespace

import pytest

import remote_ops_workspace.launcher as launcher
from remote_ops_workspace.launcher import LauncherError
from remote_ops_workspace.models import Profile, Tunnel


def test_launch_plan_printable_and_launch_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = Profile(name="local", protocol="local-shell")
    opened: list[list[str]] = []
    monkeypatch.setattr(launcher, "assert_profile_launch_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command: opened.append(command))
    monkeypatch.delenv("SHELL", raising=False)
    monkeypatch.setenv("COMSPEC", "cmd.exe")

    dry_plan = launcher.launch(profile, dry_run=True)
    real_plan = launcher.launch(profile)

    assert dry_plan.printable() == "cmd.exe"
    assert real_plan.command == ["cmd.exe"]
    assert opened == [["cmd.exe"]]


def test_raw_custom_and_unsupported_protocol_defenses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_first_available", lambda _candidates: None)
    raw = launcher.build_launch_plan(Profile(name="socket", protocol="raw", host="example.test", port=9))
    assert raw.command == ["nc", "example.test", "9"]
    assert "Install nc" in raw.notes[0]

    custom = launcher.build_launch_plan(Profile(name="custom", protocol="custom", command="tool --check"))
    assert custom.command == ["tool", "--check"]

    empty_registry = SimpleNamespace(protocols=set(), plugin_for_protocol=lambda _protocol: None)
    monkeypatch.setattr(launcher, "load_plugin_registry", lambda: empty_registry)
    monkeypatch.setattr(launcher, "prepare_profile", lambda profile, **_kwargs: profile)
    with pytest.raises(LauncherError, match="custom profile requires command"):
        launcher.build_launch_plan(Profile(name="custom", protocol="custom"))
    with pytest.raises(LauncherError, match="unsupported protocol"):
        launcher.build_launch_plan(Profile(name="unknown", protocol="unknown"))


def test_protocol_clients_merge_plugins_and_reject_invalid_plugin_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = SimpleNamespace(protocol_clients=lambda: {"demo": ["demo-client"]})
    monkeypatch.setattr(launcher, "load_plugin_registry", lambda: registry)
    clients = launcher.protocol_clients()
    assert clients["ssh"] == ["ssh"]
    assert clients["demo"] == ["demo-client"]

    plugin = SimpleNamespace(
        name="broken",
        object=SimpleNamespace(build=lambda _profile: object()),
    )
    with pytest.raises(LauncherError, match="returned invalid launch plan"):
        launcher._build_plugin_plan(plugin, Profile(name="broken", protocol="demo"))


def test_smartcard_provider_conflicts_empty_values_and_agent_notes() -> None:
    with pytest.raises(LauncherError, match="must reference the same provider"):
        launcher._ssh_connection_option_args(
            {"pkcs11_provider": "/one.so", "smartcard_provider": "/two.so"}
        )
    assert launcher._smartcard_provider_path("   ", "provider") is None
    assert launcher._smartcard_provider_path("pkcs11: /one.so", "provider") == "/one.so"
    with pytest.raises(LauncherError, match="requires a provider path"):
        launcher._smartcard_provider_path("pkcs11: ", "provider")

    notes = launcher._ssh_smartcard_notes(
        {"mobagent_smartcard": "true", "identity_agent": "/tmp/agent.sock"}
    )
    assert any("MobAgent smart-card handoff" in note for note in notes)


def test_remote_and_invalid_ssh_tunnels() -> None:
    remote = Tunnel(
        mode="remote",
        local_host="127.0.0.1",
        local_port=8080,
        remote_host="127.0.0.1",
        remote_port=80,
    )
    assert launcher._ssh_tunnel_args([remote]) == ["-R", "127.0.0.1:8080:127.0.0.1:80"]
    with pytest.raises(LauncherError, match="unsupported tunnel mode"):
        launcher._ssh_tunnel_args([Tunnel(mode="invalid")])


def test_mosh_server_and_tunnel_warning() -> None:
    profile = Profile(
        name="mobile",
        protocol="mosh",
        host="example.test",
        options={"mosh_server": "mosh-server"},
        tunnels=[Tunnel(mode="dynamic", local_port=1080)],
    )
    plan = launcher.build_launch_plan(profile)
    assert "--server=mosh-server" in plan.command
    assert any("tunnel definitions are ignored" in note for note in plan.notes)


def test_kubernetes_minimal_and_all_routing_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_first_available", lambda _candidates: None)
    minimal = launcher.build_launch_plan(Profile(name="pod", protocol="k8s", host="api-0"))
    assert minimal.command == ["kubectl", "exec", "--stdin", "--tty", "api-0", "--", "/bin/sh"]

    complete = launcher.build_launch_plan(
        Profile(
            name="pod",
            protocol="kubernetes",
            host="api-0",
            command="/bin/bash -l",
            options={
                "context": "prod",
                "kubeconfig": "C:/keys/config",
                "namespace": "ops",
                "container": "api",
            },
        )
    )
    assert complete.command[:7] == [
        "kubectl",
        "--context",
        "prod",
        "--kubeconfig",
        "C:/keys/config",
        "--namespace",
        "ops",
    ]
    assert complete.command[-2:] == ["/bin/bash", "-l"]


@pytest.mark.parametrize(("windows", "expected"), [(False, "pwsh"), (True, "powershell.exe")])
def test_winrm_falls_back_when_no_powershell_is_discovered(
    monkeypatch: pytest.MonkeyPatch,
    windows: bool,
    expected: str,
) -> None:
    monkeypatch.setattr(launcher, "_first_available", lambda _candidates: None)
    monkeypatch.setattr(launcher, "_is_windows", lambda: windows)
    plan = launcher.build_launch_plan(Profile(name="win", protocol="winrm", host="example.test"))
    assert plan.command[0] == expected


def test_non_windows_rdp_fullscreen_and_explicit_disabled_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher, "_is_windows", lambda: False)
    monkeypatch.setattr(launcher, "_first_available", lambda _candidates: None)
    plan = launcher.build_launch_plan(
        Profile(
            name="desk",
            protocol="rdp",
            host="example.test",
            options={
                "fullscreen": "true",
                "dynamic_resolution": "false",
                "cert": "tofu",
                "clipboard": "true",
            },
        )
    )
    assert plan.command[0] == "xfreerdp"
    assert "/f" in plan.command
    assert "/dynamic-resolution" not in plan.command
    assert "/cert:tofu" in plan.command
    assert "/clipboard" in plan.command
    assert not any(argument.startswith("/sec:") for argument in plan.command)


def test_x2go_accepts_an_empty_saved_layout() -> None:
    plan = launcher._build_x2go(Profile(name="layout", protocol="x2go"))
    assert plan.command == ["x2goclient"]


@pytest.mark.parametrize(
    ("platform_name", "expected"),
    [("darwin", "open"), ("linux", "xdg-open")],
)
def test_url_builder_generates_target_and_selects_platform_launcher(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    expected: str,
) -> None:
    monkeypatch.setattr(launcher, "_is_windows", lambda: False)
    monkeypatch.setattr(launcher.sys, "platform", platform_name)
    plan = launcher._build_url(Profile(name="web", protocol="https", host="example.test"), "https")
    assert plan.command == [expected, "https://example.test:443"]


def test_serial_requires_device() -> None:
    with pytest.raises(LauncherError, match="serial profile requires"):
        launcher._build_serial(Profile(name="serial", protocol="serial"))


@pytest.mark.parametrize(
    ("executable", "options", "expected", "expects_note"),
    [
        ("picocom", {}, "picocom", False),
        ("cu", {"data_bits": "7"}, "cu", True),
        ("screen", {}, "screen", False),
    ],
)
def test_posix_serial_launchers(
    monkeypatch: pytest.MonkeyPatch,
    executable: str,
    options: dict[str, str],
    expected: str,
    expects_note: bool,
) -> None:
    monkeypatch.setattr(launcher, "_is_windows", lambda: False)
    monkeypatch.setattr(launcher, "_first_available", lambda _candidates: executable)
    plan = launcher._build_serial(
        Profile(name="serial", protocol="serial", path="/dev/ttyUSB0", options=options)
    )
    assert plan.command[0] == expected
    assert bool(plan.notes) is expects_note


def test_launcher_validation_helpers_reject_malformed_values() -> None:
    with pytest.raises(LauncherError, match="requires host"):
        launcher._host(Profile(name="missing", protocol="ssh"))
    with pytest.raises(LauncherError, match="must not contain whitespace"):
        launcher._validate_proxy_jump("jump-one, jump-two")
    with pytest.raises(LauncherError, match="positive integer"):
        launcher._baud("0")
    with pytest.raises(LauncherError, match="must be true or false"):
        launcher._bool_value("maybe", "feature")
    with pytest.raises(LauncherError, match="between 10 and 20"):
        launcher._option_bounded_int({"size": "21"}, "size", minimum=10, maximum=20)
    with pytest.raises(LauncherError, match="positive integer"):
        launcher._positive_int_value("-1", "count")
    with pytest.raises(LauncherError, match="must be one of"):
        launcher._option_enum({"mode": "invalid"}, "mode", allowed={"good"})
    with pytest.raises(LauncherError, match="must not contain whitespace"):
        launcher._option_token("two words", "token")


def test_geometry_rdp_drive_and_port_range_validation() -> None:
    with pytest.raises(LauncherError, match="WIDTHxHEIGHT"):
        launcher._geometry("1920", "geometry")
    with pytest.raises(LauncherError, match="16384 or smaller"):
        launcher._geometry("16385x1080", "geometry")
    with pytest.raises(LauncherError, match="cannot be combined"):
        launcher._rdp_dimension_args({"geometry": "800x600", "width": "800", "height": "600"})
    assert launcher._rdp_dimension_args({"width": "800", "height": "600"}) == ["/w:800", "/h:600"]
    with pytest.raises(LauncherError, match="must be set together"):
        launcher._rdp_dimension_args({"width": "800"})
    with pytest.raises(LauncherError, match="must use name,path"):
        launcher._rdp_drive("share")

    assert launcher._mosh_port("60000") == "60000"
    with pytest.raises(LauncherError, match="start must be between"):
        launcher._mosh_port("65536")
    with pytest.raises(LauncherError, match="ascending order"):
        launcher._mosh_port("60010:60000")


def test_serial_and_algorithm_token_validation() -> None:
    assert launcher._ssh_algorithm_tokens(",+aes256-gcm@openssh.com,,^ssh-ed25519") == [
        "aes256-gcm@openssh.com",
        "ssh-ed25519",
    ]
    with pytest.raises(LauncherError, match="serial parity"):
        launcher._serial_parity("invalid")
    with pytest.raises(LauncherError, match="serial stop_bits"):
        launcher._serial_stop_bits("3")
    with pytest.raises(LauncherError, match="serial flow"):
        launcher._serial_flow("invalid")


def test_launcher_discovers_available_client_and_uses_it_for_raw_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        launcher.shutil,
        "which",
        lambda candidate: "C:/Tools/nc.exe" if candidate == "ncat" else None,
    )
    assert launcher._first_available(["missing", "ncat"]) == "ncat"
    plan = launcher.build_launch_plan(
        Profile(name="raw", protocol="raw", host="example.test", port=9)
    )
    assert plan.command == ["ncat", "example.test", "9"]
