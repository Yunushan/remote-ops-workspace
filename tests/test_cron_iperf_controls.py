from __future__ import annotations

import json
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import cli_managed_runtime as cli
from remote_ops_workspace import moba_servers as servers
from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.embedded_cron import cron_phase, default_crontab_path


def test_iperf_modes_require_the_selected_protocol_and_exact_bind(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    def resolve(name):
        return "/opt/test/iperf3" if name == "iperf3" else None
    options = dict(which=resolve, packaged_roots=[], system="Linux")
    default = servers.build_moba_server_plan("iperf", **options)
    assert default.port == 5001 and default.runtime.key == "iperf2"
    assert not default.runtime.available
    three = servers.build_moba_server_plan("iperf", iperf_version=3, **options)
    assert three.command == ["/opt/test/iperf3", "-s", "-B", "127.0.0.1", "-p", "5201"]
    assert servers.build_moba_server_plan("iperf", iperf_version=3, port=6294, **options).port == 6294
    with pytest.raises(ValueError, match="cannot enforce required authentication"):
        servers.start_moba_server(servers.build_moba_server_plan("iperf", iperf_version=3,
                                                                hardening_profile="strict-private", **options))
    with pytest.raises(ValueError, match="require.*TLS"):
        servers.start_moba_server(servers.build_moba_server_plan("iperf", iperf_version=3, require_tls=True, **options))
    surface = servers.build_moba_server_gui_config_surface(**options, state_dir=tmp_path)
    rows = {row.service: row for row in surface.rows}
    assert rows["iperf"].status == "missing"
    assert rows["cron"].start_action == "row servers start cron"


def test_iperf_refuses_occupied_port_before_starting_or_recording(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen(1)
        port = other.getsockname()[1]
        plan = servers.build_moba_server_plan("iperf", port=port, which=lambda name: name, packaged_roots=[])
        with pytest.raises(ValueError, match=f"cannot bind 127.0.0.1:{port}"):
            servers.start_moba_server(plan, popen_factory=pytest.fail)
        assert not servers.moba_server_state_path("iperf").exists()
    servers._require_available_iperf_port("127.0.0.1", port)
    monkeypatch.delattr(socket, "SO_EXCLUSIVEADDRUSE", raising=False)
    servers._require_available_iperf_port("127.0.0.1", port)
    v6 = servers.build_moba_server_plan("iperf", host="::1", packaged_roots=[])
    assert v6.command[1:] == ["-s", "-V", "-B", "::1", "-p", "5001"]


def test_iperf_status_reports_an_existing_v3_session(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    def launch(argv, **kwargs):
        return SimpleNamespace(pid=8899, poll=lambda: None)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    plan = servers.build_moba_server_plan("iperf", port=port, iperf_version=3,
                                         which=lambda name: name, packaged_roots=[])
    state = tmp_path / "state"
    servers.start_moba_server(plan, state_dir=state, popen_factory=launch,
                              identity_factory=lambda child: {"pid": child.pid, "kind": "test"})
    status = servers.build_moba_server_suite_status(state_dir=state, pid_probe=lambda _pid: True,
                                                   which=lambda name: name, packaged_roots=[])
    iperf = next(service for service in status.services if service.key == "iperf")
    assert iperf.selected_runtime == "iperf3" and iperf.lifecycle.port == port
    monkeypatch.setattr(servers, "recorded_process_is_running", lambda *_args: False)
    collected = []
    monkeypatch.setattr(servers, "terminate_recorded_process", lambda pid, _identity: collected.append(pid))
    replacement = servers.start_moba_server(plan, state_dir=state, popen_factory=launch,
                                           identity_factory=lambda child: {"pid": child.pid, "kind": "test"})
    assert collected == [8899] and replacement.pid == 8899
    assert servers.stop_moba_server("iperf", state_dir=state).state == "stopped"
    assert collected == [8899, 8899]


@pytest.mark.parametrize("service,kwargs", [
    ("http", {"crontab": Path("ignored")}), ("ftp", {"iperf_version": 2}), ("iperf", {"iperf_version": 1}),
    ("cron", {"port": 5001}), ("cron", {"allow_public_bind": True}), ("cron", {"host": "localhost"}),
    ("cron", {"require_auth": True}), ("cron", {"require_tls": True}),
])
def test_incompatible_control_settings_are_reported(service, kwargs):
    with pytest.raises(ValueError):
        servers.build_moba_server_config_plan(service, **kwargs)


def test_cron_plan_and_config_have_no_listener_and_preserve_logical_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    config = servers.build_moba_server_config_plan("cron")
    assert (config.host, config.port) == ("", 0)
    assert config.settings["crontab"] == str(default_crontab_path())
    assert not config.public_bind_allowed and not config.settings["network"]["public_bind_active"]
    assert not servers.build_moba_server_config_plan("cron", hardening_profile="strict-private").auth_required
    plan = servers.build_moba_server_plan("cron")
    assert (plan.host, plan.port, plan.public_bind) == ("", 0, False)
    assert plan.command == [sys.executable, "-m", "remote_ops_workspace", "servers", "_cron-runtime", "--crontab", str(default_crontab_path())]
    assert servers.start_moba_server(plan, dry_run=True).state == "dry-run"
    assert not default_crontab_path().exists()
    with pytest.raises(ValueError, match="built-in"):
        servers.build_moba_server_runtime_bundle_plan(tmp_path, "cron")


def test_frozen_cron_uses_independent_extraction_and_expected_stop_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(servers, "_frozen_server_command", lambda service, label: ["row.exe", "servers", f"_{service}-runtime"])
    plan = servers.build_moba_server_plan("cron")
    assert plan.command[:3] == ["row.exe", "servers", "_cron-runtime"]
    seen = []

    def launch(argv, **details):
        seen.append(details)
        env = details["env"]
        assert servers.change_cron_phase(Path(env["ROW_CRON_CONTROL_FILE"]), env["ROW_CRON_GENERATION"], ("pending",), "ready")
        return SimpleNamespace(pid=7788, poll=lambda: None)

    state = tmp_path / "state"
    record = servers.start_moba_server(plan, state_dir=state, popen_factory=launch,
                                       identity_factory=lambda child: {"pid": child.pid, "kind":"test"})
    assert seen[0]["env"]["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
    assert seen[0]["stdout"] == servers.subprocess.DEVNULL and default_crontab_path().is_file()
    kwargs = dict(state_dir=state, pid_probe=lambda _pid: True)
    before = Path(record.state_path).read_bytes()
    for stale in (
        replace(record, service="iperf"), replace(record, pid=4444), replace(record, started_at="replaced"),
        replace(record, cron_generation="other"), replace(record, process_identity=None), replace(record, process_identity={"kind":"different"}),
    ):
        with pytest.raises(servers.ServerOwnershipChanged):
            servers.stop_moba_server("cron", expected_record=stale, terminator=pytest.fail, **kwargs)
    assert Path(record.state_path).read_bytes() == before
    stopped = []
    result = servers.stop_moba_server("cron", expected_record=record, terminator=stopped.append, **kwargs)
    assert stopped == [7788] and result.state == "stopped" and result.port == 0
    with pytest.raises(servers.ServerOwnershipChanged):
        servers.stop_moba_server("cron", expected_record=record, terminator=pytest.fail, **kwargs)
    with pytest.raises(servers.ServerOwnershipChanged):
        servers.stop_moba_server("cron", expected_record=record, state_dir=tmp_path / "missing")


def test_startup_failure_preserves_ownership_and_stop_can_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    plan = servers.build_moba_server_plan("cron")
    state = tmp_path / "state"
    state_path = servers.moba_server_state_path("cron", state_dir=state)
    control = state_path.with_suffix(".control")
    opts = dict(state_dir=state, identity_factory=lambda child: {"pid": child.pid, "kind": "test"})
    def cannot_spawn(*_args, **_kwargs):
        raise OSError("spawn failed")
    with pytest.raises(OSError, match="spawn failed"):
        servers.start_moba_server(plan, popen_factory=cannot_spawn, **opts)
    assert not state_path.exists() and cron_phase(control).startswith("revoked ")
    with pytest.raises(OSError, match="spawn failed"):
        servers.start_moba_server(servers.build_moba_server_plan("http"), popen_factory=cannot_spawn, **opts)
    exited = SimpleNamespace(pid=9876, poll=lambda: 7)
    reaped = []
    monkeypatch.setattr(servers, "terminate_owned_process", reaped.append)
    with pytest.raises(ProcessLookupError, match="exited before"):
        servers.start_moba_server(servers.build_moba_server_plan("http"), popen_factory=lambda *_args, **_kw: exited, **opts)
    assert reaped == [exited]

    def slow_exit(timeout):
        raise subprocess.TimeoutExpired("test-cron", timeout)
    child = SimpleNamespace(pid=8765, poll=lambda: None, wait=slow_exit)
    def no_ack(*_args):
        raise ValueError("no ack")
    monkeypatch.setattr(servers, "wait_for_cron_ready", no_ack)
    with pytest.raises(ValueError, match="startup was cancelled"):
        servers.start_moba_server(plan, popen_factory=lambda *_a, **_kw: child, **opts)
    stored = json.loads(state_path.read_text())
    assert stored["state"] == "started" and stored["pid"] == child.pid
    assert cron_phase(control) == f"revoked {stored['cron_generation']}"
    monkeypatch.setattr(servers, "recorded_process_is_running", lambda *_args: True)
    monkeypatch.setattr(servers, "CRON_STOP_TIMEOUT", 0)
    monkeypatch.setattr(servers, "terminate_recorded_process", pytest.fail)
    with pytest.raises(ValueError, match="shutdown is pending"):
        servers.stop_moba_server("cron", state_dir=state, pid_probe=lambda _pid: True)
    assert json.loads(state_path.read_text()) == stored
    checks = iter([True, False])
    monkeypatch.setattr(servers, "recorded_process_is_running", lambda *_args: next(checks))
    monkeypatch.setattr(servers, "CRON_STOP_TIMEOUT", 2)
    monkeypatch.setattr(servers, "terminate_recorded_process", lambda *_args: None)
    stopped = servers.stop_moba_server("cron", state_dir=state, pid_probe=lambda _pid: True)
    assert stopped.state == "stopped" and stopped.pid is None
    child.wait = lambda timeout: 0
    def replace_generation(control, generation, _process):
        assert servers.change_cron_phase(control, "newer", (), "pending")
    monkeypatch.setattr(servers, "wait_for_cron_ready", replace_generation)
    with pytest.raises(ValueError, match="generation changed"):
        servers.start_moba_server(plan, popen_factory=lambda *_a, **_kw: child, **opts)
    assert cron_phase(control) == "pending newer"
    assert json.loads(state_path.read_text())["cron_generation"] != stored["cron_generation"]


def test_external_owned_only_posix_cron_uses_worker_lease_and_never_signals(tmp_path, monkeypatch):
    import threading
    import time

    from remote_ops_workspace.embedded_cron import exclusive_file_lock

    monkeypatch.setenv("ROW_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(servers, "uses_cron_worker_lease", lambda: True)
    def no_retained_handle(*_args):
        raise servers.ProcessIdentityError("independent CLI")
    monkeypatch.setattr(servers, "recorded_process_is_running", no_retained_handle)
    monkeypatch.setattr(servers, "terminate_recorded_process", pytest.fail)
    state = tmp_path / "state"
    control = servers.moba_server_state_path("cron", state_dir=state).with_suffix(".control")
    identity = {"version":1, "kind":"owned", "pid":7788, "token":"original"}
    def launch(_command, *, env, **_streams):
        assert servers.change_cron_phase(control, env["ROW_CRON_GENERATION"], ("pending",), "ready")
        return SimpleNamespace(pid=7788, poll=lambda: None)
    opts = dict(state_dir=state, popen_factory=launch, identity_factory=lambda _p: identity)
    plan = servers.build_moba_server_plan("cron")
    old = servers.start_moba_server(plan, **opts)
    assert not servers.load_moba_server_record("cron", state_dir=state).running
    current = servers.start_moba_server(plan, **opts)
    assert old.cron_generation != current.cron_generation
    acquired = threading.Event()
    def worker():
        with exclusive_file_lock(control.with_suffix(".worker")):
            acquired.set()
            deadline = time.monotonic() + 5
            while cron_phase(control) == f"active {current.cron_generation}" and time.monotonic() < deadline:
                time.sleep(.01)
    child = threading.Thread(target=worker)
    child.start()
    try:
        assert acquired.wait(2)
        assert servers.load_moba_server_record("cron", state_dir=state).running
        with pytest.raises(ValueError, match="already running"):
            servers.start_moba_server(plan, **opts)
        with pytest.raises(servers.ServerOwnershipChanged):
            servers.stop_moba_server("cron", state_dir=state, expected_record=old)
        assert servers.stop_moba_server("cron", state_dir=state).state == "stopped"
    finally:
        child.join(6)
    assert not child.is_alive()
    assert not servers.load_moba_server_record("cron", state_dir=state).running
    for generation, ident in [("", identity), ("token", None), ("token", {**identity, "kind":"linux"}),
                              ("token", {**identity, "version":3}), ("token", {**identity, "pid":6677}),
                              ("token", {**identity, "token":""})]:
        with pytest.raises(servers.ProcessIdentityError):
            servers._server_process_running(7788, ident, generation, control)
    monkeypatch.setattr(servers, "uses_cron_worker_lease", lambda: False)
    with pytest.raises(servers.ProcessIdentityError):
        servers._server_process_running(7788, identity, "token", control)


def test_cli_control_entry_points_and_evidence_scope(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    parser = build_parser()
    def invoke(argv):
        args = parser.parse_args(["servers", *argv])
        return args.func(args)

    assert invoke(["config-plan", "cron"]) == 0
    assert f"crontab: {default_crontab_path()}" in capsys.readouterr().out
    assert invoke(["start", "iperf", "--iperf-version", "3", "--dry-run", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["runtime"]["key"] == "iperf3" and plan["port"] == 5201
    received = []
    monkeypatch.setattr(cli, "run_cron", received.append)
    assert invoke(["_cron-runtime", "--crontab", str(tmp_path / "jobs")]) == 0
    assert received == [tmp_path / "jobs"]
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"schema":servers.SERVER_RELEASE_EVIDENCE_SCHEMA,"release_target":"test","services":[{"service":"cron"}]}))
    checked = servers.validate_moba_server_release_evidence(evidence)
    assert any("outside the v1" in error for error in checked.errors)
    assert {"cron", "iperf"}.isdisjoint(servers.SERVER_DEFAULT_PORTS)
