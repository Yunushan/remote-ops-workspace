from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from remote_ops_workspace import moba_servers, x11
from remote_ops_workspace.process_status import ProcessIdentityError, terminate_owned_process
from remote_ops_workspace.state_lock import FileLockTimeoutError, lock_path_for
from remote_ops_workspace.workspace_backup import create_workspace_backup, restore_workspace_backup


def _lifecycle(kind, home):
    home.mkdir(exist_ok=True)
    if kind == "x11":
        plan = x11.build_moba_x_server_plan(
            ":93", system="linux", packaged_roots=[],
            which=lambda name: "Xvfb" if name == "Xvfb" else None,
            display_probe=lambda _display: False, authority_path=home / "Xauthority",
        )
        state = home / "xserver-state.json"

        def start(**kwargs):
            return x11.start_moba_x_server(plan, state_path=state, **kwargs)

        def load(**kwargs):
            return x11.load_moba_x_server_record(state_path=state, **kwargs)

        def stop(**kwargs):
            return x11.stop_moba_x_server(state_path=state, **kwargs)

        module = x11
    else:
        plan = moba_servers.build_moba_server_plan("http", root=home)
        directory = home / "servers"
        state = directory / "http-server-state.json"

        def start(**kwargs):
            return moba_servers.start_moba_server(plan, state_dir=directory, **kwargs)

        def load(**kwargs):
            return moba_servers.load_moba_server_record("http", state_dir=directory, **kwargs)

        def stop(**kwargs):
            return moba_servers.stop_moba_server("http", state_dir=directory, **kwargs)

        module = moba_servers
    return module, state, start, load, stop


def _spawn_owned(children):
    def launch(_command, env):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        children.append(process)
        return process

    return launch


def _cleanup(children):
    for process in children:
        terminate_owned_process(process)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_owned_child_status_verified_stop_allows_unedited_workspace_backup(kind, tmp_path):
    home = tmp_path / "home"
    _module, state, start, load, stop = _lifecycle(kind, home)
    children = []
    try:
        started = start(popen_factory=_spawn_owned(children))
        assert started.process_identity and started.process_identity["pid"] == started.pid
        assert json.loads(state.read_text())["process_identity"] == started.process_identity
        loaded = load()
        assert loaded.running is True
        assert loaded.process_identity == started.process_identity
        stopped = stop()
        assert children[0].poll() is not None
        assert stopped.pid is None and stopped.state == "stopped" and stopped.running is False
        assert json.loads(state.read_text())["pid"] is None
        assert load().running is False
        assert stop().pid is None
        archive = tmp_path / "archive.json"
        create_workspace_backup(home, archive, "synthetic lifecycle passphrase", offline_confirmed=True)
        restored = tmp_path / "restored"
        restore_workspace_backup(archive, restored, "synthetic lifecycle passphrase", current_home=home, offline_confirmed=True)
        assert (restored / state.relative_to(home)).read_bytes() == state.read_bytes()
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
@pytest.mark.parametrize("failure", ["capture", "persist"])
def test_launch_capture_or_state_failure_reaps_actual_owned_child_preserving_prior_bytes(kind, failure, tmp_path, monkeypatch):
    module, state, start, _load, _stop = _lifecycle(kind, tmp_path / "home")
    state.parent.mkdir(exist_ok=True)
    stopped = start(dry_run=True).to_dict()
    stopped.update(state="stopped", dry_run=False)
    prior = json.dumps(stopped).encode() + b"\n"
    state.write_bytes(prior)
    children = []

    def denied(*_args, **_kwargs):
        raise OSError("injected identity or persistence failure")

    if failure == "capture":
        monkeypatch.setattr(module, "register_process", denied)
    else:
        monkeypatch.setattr(module, "write_json_atomic", denied)
    try:
        with pytest.raises(OSError, match="injected"):
            start(popen_factory=_spawn_owned(children))
        assert len(children) == 1 and children[0].poll() is not None
        assert state.read_bytes() == prior
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
@pytest.mark.parametrize("identity_kind", ["legacy", "mismatch"])
def test_unverifiable_or_reused_pid_record_never_kills_current_real_child(kind, identity_kind, tmp_path):
    _module, state, start, load, stop = _lifecycle(kind, tmp_path / "home")
    children = []
    try:
        start(popen_factory=_spawn_owned(children))
        record = json.loads(state.read_text())
        if identity_kind == "legacy":
            record.pop("process_identity")
        else:
            identity = record["process_identity"]
            key = {"windows": "creation_time", "linux": "start_ticks", "owned": "token"}[identity["kind"]]
            identity[key] = identity[key] + 1 if key != "token" else "different-owned-instance"
        state.write_text(json.dumps(record), encoding="utf-8")
        prior = state.read_bytes()
        with pytest.raises(ProcessIdentityError):
            load()
        with pytest.raises(ProcessIdentityError):
            stop()
        with pytest.raises(ProcessIdentityError):
            start(popen_factory=_spawn_owned(children))
        assert children[0].poll() is None
        assert len(children) == 1
        assert state.read_bytes() == prior
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_default_stop_does_not_trust_inactive_pid_probe_or_commit_before_exit(kind, tmp_path, monkeypatch):
    module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    children = []
    try:
        started = start(popen_factory=_spawn_owned(children))
        prior = state.read_bytes()
        calls = []

        def unconfirmed(pid, identity):
            calls.append((pid, identity))
            raise TimeoutError("same process did not exit")

        monkeypatch.setattr(module, "terminate_recorded_process", unconfirmed)
        with pytest.raises(TimeoutError, match="did not exit"):
            stop(pid_probe=lambda _pid: False)
        assert calls == [(started.pid, started.process_identity)]
        assert state.read_bytes() == prior
        assert children[0].poll() is None
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_started_record_without_pid_cannot_be_claimed_stopped(kind, tmp_path):
    _module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    record = start(dry_run=True).to_dict()
    record["state"] = "started"
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    prior = state.read_bytes()
    with pytest.raises(ValueError, match="no verifiable process"):
        stop()
    assert state.read_bytes() == prior


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_malformed_identity_is_refused_before_stop_changes_state(kind, tmp_path):
    _module, state, start, load, stop = _lifecycle(kind, tmp_path / "home")
    record = start(dry_run=True).to_dict()
    record["state"] = "stopped"
    record["process_identity"] = ["invalid JSON identity"]
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    prior = state.read_bytes()
    with pytest.raises(ValueError, match="process_identity must be a JSON object"):
        load()
    with pytest.raises(ValueError, match="process_identity must be a JSON object"):
        stop()
    assert state.read_bytes() == prior


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_explicit_completed_stop_seam_can_finish_inactive_test_record(kind, tmp_path):
    _module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    record = start(dry_run=True).to_dict()
    record.update(state="started", pid=99999)
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    calls = []
    stopped = stop(pid_probe=lambda _pid: False, terminator=calls.append)
    assert stopped.pid is None and stopped.state == "stopped" and calls == []


@pytest.mark.parametrize("kind", ["x11", "server"])
@pytest.mark.parametrize("state_label", ["started", "stopped"])
def test_repeated_start_refuses_before_cookie_or_process_mutation(kind, state_label, tmp_path):
    _module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    children = []
    try:
        original = start(popen_factory=_spawn_owned(children))
        if state_label == "stopped":
            payload = json.loads(state.read_text())
            payload["state"] = "stopped"
            state.write_text(json.dumps(payload), encoding="utf-8")
        prior = state.read_bytes()
        authority = state.parent / "Xauthority"
        prior_cookie = authority.read_bytes() if authority.exists() else None
        with pytest.raises(ValueError, match="already running"):
            start(popen_factory=_spawn_owned(children))
        assert len(children) == 1 and children[0].poll() is None
        assert state.read_bytes() == prior
        if prior_cookie is not None:
            assert authority.read_bytes() == prior_cookie
        assert stop().process_identity == original.process_identity
        assert lock_path_for(state).is_file()
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
@pytest.mark.parametrize("changes", [
    {"state": "unknown"},
    {"state": "stopped", "dry_run": True},
    {"state": "stopped", "running": True},
    {"state": "started", "pid": None},
])
def test_ambiguous_existing_record_refuses_start_without_launch_or_cookie(kind, changes, tmp_path):
    _module, state, start, _load, _stop = _lifecycle(kind, tmp_path / "home")
    record = start(dry_run=True).to_dict()
    record.update(state="stopped", dry_run=False)
    record.update(changes)
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps(record), encoding="utf-8")
    prior = state.read_bytes()
    with pytest.raises(ValueError, match="active or ambiguous"):
        start(popen_factory=lambda *_args, **_kwargs: pytest.fail("ambiguous state must not launch"))
    assert state.read_bytes() == prior
    assert not (state.parent / "Xauthority").exists()


@pytest.mark.parametrize("kind", ["x11", "server"])
@pytest.mark.parametrize("prior_state", ["verified-stopped", "completed-with-pid", "stopped-with-completed-pid"])
def test_start_replaces_only_confirmed_stopped_or_completed_record(kind, prior_state, tmp_path):
    _module, _state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    children = []
    try:
        first = start(popen_factory=_spawn_owned(children))
        if prior_state == "verified-stopped":
            stop()
        else:
            terminate_owned_process(children[0])
            if prior_state == "stopped-with-completed-pid":
                state = Path(first.state_path)
                payload = json.loads(state.read_text())
                payload["state"] = "stopped"
                state.write_text(json.dumps(payload), encoding="utf-8")
        second = start(popen_factory=_spawn_owned(children))
        assert second.pid == children[1].pid and second.process_identity != first.process_identity
        assert children[0].poll() is not None and children[1].poll() is None
        stop()
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_child_that_vanishes_after_identity_capture_is_reaped_without_record_commit(kind, tmp_path):
    module, state, start, _load, _stop = _lifecycle(kind, tmp_path / "home")
    children = []

    def exited_child(process):
        identity = module.register_process(process)
        terminate_owned_process(process)
        return identity

    try:
        with pytest.raises(ProcessLookupError, match="exited before"):
            start(popen_factory=_spawn_owned(children), identity_factory=exited_child)
        assert len(children) == 1 and children[0].poll() is not None
        assert not state.exists()
    finally:
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_concurrent_start_and_stop_share_one_serialized_record_transaction(kind, tmp_path):
    _module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    children = []
    first_launched = threading.Event()
    second_attempted = threading.Event()
    finish_launch = threading.Event()
    launch = _spawn_owned(children)

    def paused_launch(command, env):
        process = launch(command, env)
        first_launched.set()
        assert finish_launch.wait(5)
        return process

    def second_start():
        second_attempted.set()
        return start(popen_factory=launch)

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(start, popen_factory=paused_launch)
            try:
                assert first_launched.wait(5)
                second = workers.submit(second_start)
                assert second_attempted.wait(5)
                with pytest.raises(TimeoutError):
                    second.result(timeout=0.05)
                with pytest.raises(FileLockTimeoutError):
                    stop(lock_timeout_seconds=0.05)
                assert not state.exists() and len(children) == 1
            finally:
                finish_launch.set()
            started = first.result(timeout=5)
            with pytest.raises(ValueError, match="already running"):
                second.result(timeout=5)
        assert len(children) == 1 and json.loads(state.read_text())["pid"] == started.pid
        stop()
    finally:
        finish_launch.set()
        _cleanup(children)


@pytest.mark.parametrize("kind", ["x11", "server"])
def test_another_process_holding_record_lock_prevents_start_and_stop_mutation(kind, tmp_path):
    _module, state, start, _load, stop = _lifecycle(kind, tmp_path / "home")
    ready, release = tmp_path / "ready", tmp_path / "release"
    code = """
import sys, time
from pathlib import Path
from remote_ops_workspace.state_lock import exclusive_file_lock
with exclusive_file_lock(Path(sys.argv[1])):
    Path(sys.argv[2]).write_text('ready')
    while not Path(sys.argv[3]).exists():
        time.sleep(0.01)
"""
    owner = subprocess.Popen(
        [sys.executable, "-c", code, str(state), str(ready), str(release)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert owner.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        with pytest.raises(FileLockTimeoutError):
            start(lock_timeout_seconds=0.1, popen_factory=lambda *_args, **_kwargs: pytest.fail("locked start must not launch"))
        with pytest.raises(FileLockTimeoutError):
            stop(lock_timeout_seconds=0.1)
        assert not state.exists() and not (state.parent / "Xauthority").exists()
    finally:
        release.write_text("released", encoding="utf-8")
        owner.wait(timeout=5)
        terminate_owned_process(owner)
