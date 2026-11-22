from __future__ import annotations

import threading
from dataclasses import replace
from unittest.mock import Mock

import pytest

pytest.importorskip("PyQt6.QtCore")
from PyQt6.QtWidgets import QApplication

from remote_ops_workspace import gui_server_lifecycle as controls


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row"))
    desktop = QApplication.instance() or QApplication([])
    obj = controls.ServerLifecycleManager(desktop)
    yield obj
    obj.shutdown()
    obj._executor.shutdown(wait=True)


@pytest.fixture
def backend(monkeypatch):
    records = {}
    started, stopped = [], []

    def start(service):
        record = controls.MobaEmbeddedServerLifecycleRecord(
            service, "", 0, service, [service], "started", pid=len(started) + 100,
            started_at=str(len(started)), running=True, process_identity={"test": len(started)},
        )
        records[service] = record
        started.append(record)
        return record

    def stop(service, *, expected_record):
        assert records[service] == expected_record
        stopped.append(expected_record)
        records[service] = replace(expected_record, running=False, state="stopped")
        return records[service]

    monkeypatch.setattr(controls, "load_moba_server_record", records.get)
    monkeypatch.setattr(controls, "build_moba_server_plan", lambda service: service)
    monkeypatch.setattr(controls, "start_moba_server", start)
    monkeypatch.setattr(controls, "stop_moba_server", stop)
    return records, started, stopped


def drain(manager):
    manager._executor.submit(lambda: None).result(timeout=5)
    manager._collect()


def test_preferences_defaults_merge_and_validation(manager):
    path = manager._path
    assert manager.preferences("cron") == controls.ServicePreferences(360, False)
    manager.startup()
    manager.startup()
    assert not path.parent.exists()
    manager.save_preferences("iperf", controls.ServicePreferences(None))
    manager.save_preferences("cron", controls.ServicePreferences(65535, True))
    assert manager.preferences("iperf") == controls.ServicePreferences(None)
    assert manager.preferences("cron") == controls.ServicePreferences(65535, True)
    for value in (True, "1", 0, 65536):
        with pytest.raises(ValueError, match="65535"):
            controls.ServicePreferences(value)
    with pytest.raises(ValueError, match="true or false"):
        controls.ServicePreferences(1, 0)
    for service in ("iperf", "bad"):
        with pytest.raises(ValueError, match="Only Cron"):
            manager.save_preferences(service, controls.ServicePreferences(1, True))
    with pytest.raises(ValueError, match="Unknown"):
        manager.preferences("bad")
    with pytest.raises(ValueError, match="Unknown"):
        manager.start("bad")
    path.write_text("[]")
    with pytest.raises(ValueError, match="Invalid server preferences"):
        manager.save_preferences("cron", controls.ServicePreferences())
    assert path.read_text() == "[]"
    path.write_text('{"cron":false}')
    with pytest.raises(ValueError, match="Invalid cron"):
        manager.preferences("cron")


def test_startup_refuses_unreadable_settings(manager):
    observed = []
    manager.changed.connect(lambda *event: observed.append(event))
    manager._path.parent.mkdir(parents=True)
    manager._path.write_text("{")
    manager.startup()
    assert observed[-1][:2] == ("cron", "stopped")
    assert observed[-1][2]
    assert not manager._pending


def test_owning_window_close_preserves_services_for_second_window(tmp_path, monkeypatch, backend):
    from remote_ops_workspace.gui import create_main_window

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "shared"))
    app, first = create_main_window(["first"], show=True)
    _, second = create_main_window(["second"], show=True)
    manager = first.server_lifecycle
    _, started, stopped = backend
    try:
        assert second.server_lifecycle is manager
        manager.start("cron")
        drain(manager)
        first.close()
        first.release_server_lifecycle()
        assert second.isVisible() and not manager._closed and not stopped
        second.close()
        manager._executor.shutdown(wait=True)
        assert manager._closed and stopped == started and len(stopped) == 1
    finally:
        first.close()
        second.close()
        app.processEvents()


def test_unused_manager_close_does_not_start_a_worker(manager, monkeypatch):
    submit = Mock()
    monkeypatch.setattr(manager._executor, "submit", submit)
    manager.shutdown()
    submit.assert_not_called()


def test_application_shutdown_can_precede_last_window_release(tmp_path, monkeypatch):
    from PyQt6.QtCore import QObject

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = QObject()
    manager, release = controls.ServerLifecycleManager.attach_window(app, window)
    manager.shutdown()
    release()
    assert manager._closed


def test_application_owned_timers_follow_the_actual_run(manager, backend):
    records, started, stopped = backend
    events = []
    manager.changed.connect(lambda *event: events.append(event))
    manager.save_preferences("cron", controls.ServicePreferences(3, True))
    manager.startup()
    drain(manager)
    assert events == [("cron", "starting", ""), ("cron", "running", "")]
    assert manager._timers["cron"].isActive()
    assert 0 < manager._timers["cron"].remainingTime() <= 3000
    manager.save_preferences("cron", controls.ServicePreferences(None))
    assert not manager._timers["cron"].isActive()
    manager.save_preferences("cron", controls.ServicePreferences(1))
    manager._expire("cron")
    drain(manager)
    assert events[-2:] == [("cron", "stopping", ""), ("cron", "stopped", "")]
    assert stopped == started
    assert not manager._timers["cron"].isActive()
    manager._expire("cron")
    manager.stop("cron")
    drain(manager)
    assert len(stopped) == 1

    manager.start("cron")
    drain(manager)
    replacement = replace(records["cron"], pid=900, process_identity={"test": 901})
    records["cron"] = replacement
    manager._expire("cron")
    drain(manager)
    assert records["cron"] == replacement
    assert events[-1] == ("cron", "running", "")
    assert not manager._timers["cron"].isActive()
    manager.start("cron")
    drain(manager)
    assert len(started) == 2
    manager.stop("cron")
    drain(manager)
    assert stopped[-1] == replacement


def test_refresh_coalesces_conflicting_intent_and_close_drains_an_inflight_start(manager, backend, monkeypatch):
    records, started, stopped = backend
    entered, release = threading.Event(), threading.Event()

    def load(service):
        entered.set()
        assert release.wait(5)
        return records.get(service)

    monkeypatch.setattr(controls, "load_moba_server_record", load)
    manager.refresh("iperf")
    assert entered.wait(5)
    initial = manager._pending["iperf"]
    manager.refresh("iperf")
    manager._collect()
    assert manager._pending["iperf"] is initial
    manager.start("iperf")
    manager.start("iperf")
    manager.refresh("iperf")
    manager.stop("iperf")
    manager.start("iperf")
    manager.shutdown()
    manager.shutdown()
    manager.startup()
    manager.refresh("iperf")
    release.set()
    manager._executor.shutdown(wait=True)
    assert started == stopped and len(stopped) == 2
    assert not manager._pending
    assert not manager._poll.isActive()


def test_errors_do_not_drop_ownership_or_terminate_replacements(manager, backend, monkeypatch, caplog):
    records, started, stopped = backend
    events = []
    manager.changed.connect(lambda *event: events.append(event))
    monkeypatch.setattr(controls, "load_moba_server_record", Mock(side_effect=OSError("unreadable")))
    manager.refresh("iperf")
    drain(manager)
    assert events[-1] == ("iperf", "stopped", "unreadable")
    monkeypatch.setattr(controls, "load_moba_server_record", records.get)
    manager._path.parent.mkdir(parents=True)
    manager._path.write_text('{"iperf":{"auto_stop_seconds":0}}')
    manager.start("iperf")
    drain(manager)
    assert events[-1][:2] == ("iperf", "running") and "65535" in events[-1][2]
    assert manager._timers["iperf"].isActive()
    monkeypatch.setattr(controls, "stop_moba_server", Mock(side_effect=ValueError("changed during stop")))
    manager.stop("iperf")
    drain(manager)
    assert events[-1] == ("iperf", "running", "changed during stop")
    monkeypatch.setattr(controls, "load_moba_server_record", Mock(side_effect=OSError("transient state error")))
    manager.refresh("iperf")
    drain(manager)
    assert events[-1] == ("iperf", "running", "transient state error")
    manager.shutdown()
    manager._executor.shutdown(wait=True)
    assert "changed during stop" in caplog.text
    assert len(started) == 1 and not stopped


def test_worker_boundary_and_synchronous_close_during_change(manager, backend, monkeypatch):
    records, _, _ = backend
    events = []
    manager.changed.connect(lambda *event: events.append(event))
    monkeypatch.setattr(controls, "build_moba_server_plan", Mock(side_effect=KeyError("unexpected")))
    manager.start("iperf")
    drain(manager)
    assert events[-1][:2] == ("iperf", "stopped") and "unexpected" in events[-1][2]
    monkeypatch.setattr(controls, "build_moba_server_plan", lambda service: service)
    manager.start("iperf")
    drain(manager)
    monkeypatch.setattr(controls, "load_moba_server_record", Mock(side_effect=KeyError("unexpected")))
    manager.refresh("iperf")
    drain(manager)
    assert events[-1][:2] == ("iperf", "running")
    monkeypatch.setattr(controls, "load_moba_server_record", records.get)
    manager.changed.connect(lambda *_: manager.shutdown())
    manager.refresh("iperf")
    manager.refresh("cron")
    drain(manager)
    assert manager._closed
