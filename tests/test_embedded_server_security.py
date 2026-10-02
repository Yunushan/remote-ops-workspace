from __future__ import annotations

import json
import os
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import moba_servers, x11


@pytest.mark.parametrize("system", ["windows", "linux", "darwin"])
def test_x_server_cookie_is_generated_before_launch_and_shared_with_clients(tmp_path, monkeypatch, system):
    authority = tmp_path / "Xauthority"
    executable = {"windows": "vcxsrv", "linux": "Xvfb", "darwin": "Xquartz"}[system]
    plan = x11.build_moba_x_server_plan(
        ":34", system=system, which=lambda name: name if name == executable else None,
        display_probe=lambda _display: False, authority_path=authority,
    )
    calls = []

    def launch(command, env):
        assert authority.is_file()
        assert env["XAUTHORITY"] == str(authority)
        calls.append(command)
        return SimpleNamespace(pid=3434, poll=lambda: None)

    x11.start_moba_x_server(plan, state_path=tmp_path / "state.json", popen_factory=launch, identity_factory=lambda process: {"pid": process.pid, "kind": "test"})
    payload = authority.read_bytes()
    records = []
    while payload:
        family = struct.unpack("!H", payload[:2])[0]
        payload = payload[2:]
        fields = []
        for _ in range(4):
            length = struct.unpack("!H", payload[:2])[0]
            fields.append(payload[2:2 + length])
            payload = payload[2 + length:]
        records.append((family, fields))
    assert {family for family, _fields in records} == {0, 6, 256}
    assert all(fields[1] == b"34" and fields[2] == b"MIT-MAGIC-COOKIE-1" for _family, fields in records)
    assert len({fields[3] for _family, fields in records}) == 1
    assert len(records[0][1][3]) == 16
    assert "-ac" not in calls[0]
    assert calls[0][-2:] == (["-listen", "tcp"] if system == "windows" else ["-nolisten", "tcp"])
    assert "password" not in json.dumps(plan.to_dict())
    monkeypatch.setenv("XAUTHORITY", str(authority))
    assert x11.managed_x11_environment(":34") == {"DISPLAY": ":34", "XAUTHORITY": str(authority)}


def test_x_server_dry_run_does_not_create_cookie_and_tcp_opt_in_is_explicit(tmp_path):
    authority = tmp_path / "Xauthority"
    plan = x11.build_moba_x_server_plan(
        ":35", system="linux", which=lambda name: name if name == "Xvfb" else None,
        display_probe=lambda _display: False, authority_path=authority, allow_tcp=True,
    )
    assert plan.command[-2:] == ["-listen", "tcp"]
    x11.start_moba_x_server(plan, dry_run=True, state_path=tmp_path / "state.json")
    assert not authority.exists()


@pytest.mark.parametrize("command,environment", [
    (["Xorg", ":0", "-ac"], {}),
    (["Xorg", ":0"], {}),
    (["Xorg", ":0", "-auth"], {}),
    (["Xorg", ":0", "-auth", "a"], {"XAUTHORITY": "b"}),
])
def test_x_server_rejects_unauthenticated_or_mismatched_authority(command, environment):
    with pytest.raises(ValueError):
        x11._prepare_x_server_authority(command, environment, ":0")


@pytest.mark.parametrize("command", [["Xorg"], ["Xorg", ":0"], ["Xorg", ":0", "-auth"]])
def test_basic_x_server_run_cannot_bypass_authentication(command):
    with pytest.raises(ValueError, match="authorization"):
        x11.run_x_server(x11.XServerPlan(command, []))


@pytest.mark.parametrize("key", ["xlaunch", "xquartz"])
def test_gui_launch_wrappers_cannot_bypass_managed_x_security(key):
    runtime = x11.XServerRuntimeCandidate(key, key, key, True, "test")
    with pytest.raises(ValueError, match="direct"):
        x11._runtime_command(runtime, ":0", "windows")


def test_managed_x_environment_handles_later_cli_process_and_missing_authority(tmp_path, monkeypatch):
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    assert x11.managed_x11_environment() == {"DISPLAY": ":0"}
    authority = tmp_path / "x11" / "Xauthority-0"
    authority.parent.mkdir()
    authority.write_bytes(b"cookie")
    assert x11.managed_x11_environment()["XAUTHORITY"] == str(authority)


@pytest.mark.parametrize("service,executable", [("telnet", "telnetd"), ("nfs", "nfsd"), ("ftp", "ftpd")])
def test_unverifiable_daemon_bind_cannot_be_started(service, executable, tmp_path, monkeypatch):
    monkeypatch.setattr(moba_servers.importlib.util, "find_spec", lambda _name: None)
    plan = moba_servers.build_moba_server_plan(
        service, root=tmp_path, which=lambda name: executable if name == executable else None, packaged_roots=[], system="linux",
    )
    with pytest.raises(ValueError, match="cannot enforce"):
        moba_servers.start_moba_server(plan, state_dir=tmp_path, popen_factory=lambda *_args, **_kwargs: pytest.fail("must not spawn"))
    assert not (tmp_path / f"{service}-server-state.json").exists()
    suite = moba_servers.build_moba_server_suite_status(system="linux", which=lambda name: executable if name == executable else None, state_dir=tmp_path)
    assert next(row for row in suite.services if row.key == service).startable is False
    if service in {"telnet", "nfs"}:
        assert plan.command == []
        config = moba_servers.build_moba_server_config_plan(service, port=plan.port)
        assert config.settings["execution"]["mode"] == "host-managed"
        settings = config.settings["host_config"]
        if service == "telnet":
            assert settings["service"]["bind"] == "127.0.0.1"
            assert settings["service"]["disable"] == "yes"
        else:
            assert settings["nfs.conf"]["nfsd"]["host"] == "127.0.0.1"


def test_strict_private_refuses_public_bind_even_with_opt_in(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        moba_servers.build_moba_server_config_plan("ftp", host="0.0.0.0", root=tmp_path, hardening_profile="strict-private", allow_public_bind=True)


def test_ftp_plan_matches_auth_and_transport_policy_without_secrets(tmp_path):
    plan = moba_servers.build_moba_server_plan("ftp", root=tmp_path, host="0.0.0.0", allow_public_bind=True)
    config = moba_servers.build_moba_server_config_plan("ftp", root=tmp_path, host="0.0.0.0", allow_public_bind=True, require_auth=False)
    assert config.auth_required is True
    assert config.tls_required is True
    assert plan.environment["ROW_FTP_TLS_REQUIRED"] == "1"
    assert "remote_ops_workspace.embedded_ftp" in plan.command
    assert "ROW_FTP_PASSWORD" not in plan.environment


@pytest.mark.parametrize("service,keyword,error", [("http", "require_tls", "TLS"), ("http", "hardening_profile", "authentication"), ("tftp", "hardening_profile", "authentication")])
def test_start_refuses_security_requirements_plain_adapters_cannot_enforce(tmp_path, monkeypatch, service, keyword, error):
    options = {keyword: True if keyword == "require_tls" else "strict-private"}
    plan = moba_servers.build_moba_server_plan(service, root=tmp_path, which=lambda name: name, **options)
    with pytest.raises(ValueError, match=error):
        moba_servers.start_moba_server(plan, state_dir=tmp_path)


def test_ftp_start_requires_credentials_and_the_authenticated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(moba_servers.importlib.util, "find_spec", lambda _name: None)
    plan = moba_servers.build_moba_server_plan("ftp", root=tmp_path, which=lambda name: name if name == "pyftpdlib" else None)
    monkeypatch.delenv("ROW_FTP_USERNAME", raising=False)
    monkeypatch.delenv("ROW_FTP_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="ROW_FTP_USERNAME"):
        moba_servers.start_moba_server(plan, state_dir=tmp_path)
    monkeypatch.setenv("ROW_FTP_USERNAME", "audit-user")
    monkeypatch.setenv("ROW_FTP_PASSWORD", "FAKE-AUDIT-PASSWORD")
    with pytest.raises(ValueError, match="pyftpdlib"):
        moba_servers.start_moba_server(plan, state_dir=tmp_path)
    monkeypatch.setattr(moba_servers.importlib.util, "find_spec", lambda _name: object())
    record = moba_servers.start_moba_server(plan, state_dir=tmp_path, popen_factory=lambda _command, env: SimpleNamespace(pid=44, poll=lambda: None), identity_factory=lambda process: {"pid": process.pid, "kind": "test"})
    assert "FAKE-AUDIT-PASSWORD" not in json.dumps(record.to_dict())


def test_ftps_start_refuses_missing_tls_runtime_before_spawning(tmp_path, monkeypatch):
    monkeypatch.setattr(moba_servers.importlib.util, "find_spec", lambda name: object() if name == "pyftpdlib" else None)
    monkeypatch.setenv("ROW_FTP_USERNAME", "audit-user")
    monkeypatch.setenv("ROW_FTP_PASSWORD", "FAKE-AUDIT-PASSWORD")
    cert, key = tmp_path / "certificate", tmp_path / "key"
    cert.write_bytes(b"test certificate")
    key.write_bytes(b"test key")
    monkeypatch.setenv("ROW_FTP_TLS_CERT", str(cert))
    monkeypatch.setenv("ROW_FTP_TLS_KEY", str(key))
    plan = moba_servers.build_moba_server_plan("ftp", root=tmp_path, require_tls=True, which=lambda _name: None)
    with pytest.raises(ValueError, match="pyOpenSSL"):
        moba_servers.start_moba_server(plan, state_dir=tmp_path)


def test_vnc_auth_file_required_and_launched_command_carries_same_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ROW_VNC_PASSWORD_FILE", raising=False)
    plan = moba_servers.build_moba_server_plan("vnc", which=lambda name: name if name == "x11vnc" else None)
    with pytest.raises(ValueError, match="ROW_VNC_PASSWORD_FILE"):
        moba_servers.start_moba_server(plan, state_dir=tmp_path)
    password_file = tmp_path / "vnc-passwd"
    password_file.write_bytes(b"fake encrypted VNC password")
    monkeypatch.setenv("ROW_VNC_PASSWORD_FILE", str(password_file))
    plan = moba_servers.build_moba_server_plan("vnc", which=lambda name: name if name == "x11vnc" else None)
    assert plan.command[-2:] == ["-rfbauth", str(password_file)]
    moba_servers.start_moba_server(plan, state_dir=tmp_path, popen_factory=lambda *_args, **_kwargs: SimpleNamespace(pid=45, poll=lambda: None), identity_factory=lambda process: {"pid": process.pid, "kind": "test"})


@pytest.mark.parametrize("runtime,password_kind,expected", [
    (None, None, False), ("vncserver", "file", False), ("x11vnc", None, False),
    ("x11vnc", "missing", False), ("x11vnc", "directory", False), ("x11vnc", "file", True),
])
def test_vnc_suite_startable_matches_authenticated_launch_prerequisites(runtime, password_kind, expected, tmp_path, monkeypatch):
    monkeypatch.delenv("ROW_VNC_PASSWORD_FILE", raising=False)
    password_file = tmp_path / "vnc-passwd"
    if password_kind == "file":
        password_file.write_bytes(b"fake encrypted VNC password")
    elif password_kind == "directory":
        password_file.mkdir()
    if password_kind:
        monkeypatch.setenv("ROW_VNC_PASSWORD_FILE", str(password_file))
    def which(name):
        return name if name == runtime else None

    suite = moba_servers.build_moba_server_suite_status(system="linux", which=which, packaged_roots=[], state_dir=tmp_path)
    status = next(item for item in suite.services if item.key == "vnc")
    assert status.startable is expected
    assert status.available is (runtime is not None)
    if expected:
        plan = moba_servers.build_moba_server_plan("vnc", system="linux", which=which, packaged_roots=[])
        assert plan.command[-2:] == ["-rfbauth", str(password_file)]
        moba_servers.start_moba_server(plan, state_dir=tmp_path, popen_factory=lambda *_args, **_kwargs: SimpleNamespace(pid=4545, poll=lambda: None), identity_factory=lambda process: {"pid": process.pid, "kind": "test"})
    else:
        assert any("ROW_VNC_PASSWORD_FILE" in note for note in status.notes)


def test_native_ftp_runner_uses_cli_helper_or_refuses_missing_package(tmp_path, monkeypatch):
    monkeypatch.setattr(moba_servers.sys, "frozen", True, raising=False)
    monkeypatch.setattr(moba_servers.sys, "executable", str(tmp_path / "row-gui.exe"))
    with pytest.raises(ValueError, match="CLI helper"):
        moba_servers._ftp_runner_command()
    name = "row.exe" if os.name == "nt" else "row"
    helper = tmp_path / "bin" / name
    helper.parent.mkdir()
    helper.write_bytes(b"fake helper")
    assert moba_servers._ftp_runner_command() == [str(helper), "servers", "_ftp-runtime"]


def test_native_macos_ftp_runner_reuses_argument_aware_app_launcher(tmp_path, monkeypatch):
    executable = tmp_path / "RemoteOpsWorkspace"
    executable.write_bytes(b"fake app launcher")
    monkeypatch.setattr(moba_servers.sys, "frozen", True, raising=False)
    monkeypatch.setattr(moba_servers.sys, "executable", str(executable))
    monkeypatch.setattr(moba_servers.platform, "system", lambda: "Darwin")
    assert moba_servers._ftp_runner_command() == [str(executable), "servers", "_ftp-runtime"]


def test_basic_x_server_builder_preserves_authenticated_managed_command(monkeypatch):
    managed = x11.build_moba_x_server_plan(":36", system="windows", which=lambda _name: None, packaged_roots=[], display_probe=lambda _display: False)
    assert any("No detected X server runtime" in note for note in managed.notes)
    assert managed.printable().startswith("vcxsrv :36")
    monkeypatch.setattr(x11, "build_moba_x_server_plan", lambda **_kwargs: managed)
    basic = x11.build_x_server_plan(":36")
    assert basic.command == managed.command
    assert "-auth" in basic.command


def test_xauth_location_prefers_an_existing_path_executable(tmp_path):
    executable = tmp_path / "xauth.exe"
    executable.write_bytes(b"fake xauth")
    assert x11.managed_xauth_location(which=lambda name: str(executable) if name == "xauth" else None) == str(executable)


@pytest.mark.parametrize("name", ["xauth.exe", "xauth"])
def test_xauth_location_finds_the_selected_windows_runtime_sibling(tmp_path, name):
    runtime = tmp_path / "vcxsrv.exe"
    runtime.write_bytes(b"fake runtime")
    executable = tmp_path / name
    executable.write_bytes(b"fake xauth")
    assert x11.managed_xauth_location(system="windows", packaged_roots=[], which=lambda candidate: str(runtime) if candidate == "vcxsrv" else None) == str(executable)


def test_xauth_location_does_not_claim_missing_tool(tmp_path):
    runtime = tmp_path / "vcxsrv.exe"
    assert x11.managed_xauth_location(system="windows", packaged_roots=[], which=lambda candidate: str(runtime) if candidate == "vcxsrv" else None) is None


@pytest.mark.parametrize("available", [True, False])
def test_xauth_location_checks_standard_xquartz_installation(tmp_path, monkeypatch, available):
    path_type = type(tmp_path)
    original = path_type.is_file
    monkeypatch.setattr(path_type, "is_file", lambda path: available if path.as_posix() == "/opt/X11/bin/xauth" else original(path))
    found = x11.managed_xauth_location(system="darwin", packaged_roots=[], which=lambda candidate: str(tmp_path / "Xquartz") if candidate == "Xquartz" else None)
    assert found == (str(Path("/opt/X11/bin/xauth")) if available else None)
