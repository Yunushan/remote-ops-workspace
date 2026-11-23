from __future__ import annotations

import os
from dataclasses import replace

import pytest


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6")
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["server-controls"], show=False)
    yield window
    window.close()
    app.processEvents()


@pytest.mark.parametrize("iperf_available", [False, True])
def test_servers_window_routes_independent_lifecycle_actions(desktop, monkeypatch, iperf_available):
    from PyQt6.QtWidgets import QToolButton

    from remote_ops_workspace import gui_operator_workflows as workflows
    from remote_ops_workspace.gui_dialogs import WorkflowDialog
    from remote_ops_workspace.gui_server_controls import ServerRowControls, ServerSettingsDialog

    manager = desktop.server_lifecycle
    surface = workflows.build_moba_server_gui_config_surface()
    rows = tuple(
        replace(row, runtime_available=iperf_available, status="running" if iperf_available else "missing")
        if row.service == "iperf" else row for row in surface.rows
    )
    monkeypatch.setattr(workflows, "build_moba_server_gui_config_surface", lambda **_: replace(surface, rows=rows))
    calls = []
    for name in ("start", "stop", "refresh"):
        monkeypatch.setattr(manager, name, lambda service, action=name: calls.append((action, service)))

    opened = []
    monkeypatch.setattr(ServerSettingsDialog, "exec", lambda dialog: opened.append(dialog.service))

    def interact(dialog):
        controls = {widget.service: widget for widget in dialog.findChildren(ServerRowControls)}
        assert set(controls) == {"cron", "iperf"}
        cron, iperf = controls["cron"], controls["iperf"]
        tree = dialog.rows
        tree.setCurrentItem(tree.topLevelItem(0))
        assert "row servers start http" in dialog.detail.toPlainText()
        tree.setCurrentItem(None)
        assert iperf.row.text(2) == ("127.0.0.1:5001" if iperf_available else "Iperf 2 required")
        assert iperf.stop_button.isEnabled() is iperf_available
        manager.changed.emit("iperf", "stopped", "")
        assert calls == [("refresh", "cron"), ("refresh", "iperf")]
        assert cron.start_button.isEnabled() and not cron.stop_button.isEnabled()
        cron.start_button.click()
        assert "Schedule file:" in dialog.detail.toPlainText()
        manager.changed.emit("cron", "starting", "")
        assert not cron.start_button.isEnabled() and not cron.stop_button.isEnabled()
        manager.changed.emit("cron", "running", "started in test workspace")
        assert cron.row.text(1) == "running" and iperf.row.text(1) == "stopped"
        assert dialog.detail.toPlainText().endswith("started in test workspace")
        cron.stop_button.click()
        iperf.start_button.click()
        assert "iperf -c 127.0.0.1" in dialog.detail.toPlainText()
        assert calls[-3:] == [("start", "cron"), ("stop", "cron"), ("start", "iperf")]
        from remote_ops_workspace.moba_servers import MobaEmbeddedServerLifecycleRecord

        live = MobaEmbeddedServerLifecycleRecord(
            "iperf", "::1", 55201, "iperf3", ["iperf3", "-s"], "started", running=True,
        )
        for host, endpoint in (("::1", "[::1]:55201"), ("127.0.0.1", "127.0.0.1:55201")):
            manager.observed_records["iperf"] = replace(live, host=host)
            manager.changed.emit("iperf", "running", "")
            assert iperf.row.text(2) == endpoint
            assert f"iperf3 listening on {endpoint}" in dialog.detail.toPlainText()
        manager.observed_records["cron"] = replace(live, service="cron", command=["row", "--crontab", "custom-tab"])
        manager.changed.emit("cron", "running", "")
        tree.setCurrentItem(cron.row)
        assert "Schedule file: custom-tab" in dialog.detail.toPlainText()
        manager.changed.emit("cron", "running", "")
        next(b for b in iperf.findChildren(QToolButton) if b.text().startswith("Settings")).click()
        assert opened == ["iperf"]
        monkeypatch.setattr(manager, "preferences", lambda *_: _refuse("preferences unreadable"))
        cron.configure()
        assert dialog.detail.toPlainText() == "preferences unreadable"
        dialog.reject()

    monkeypatch.setattr(WorkflowDialog, "exec", interact)
    desktop.show_moba_servers_status()


def _refuse(message):
    raise ValueError(message)


def test_settings_defaults_disabled_timeout_and_persistence(desktop, monkeypatch):
    from remote_ops_workspace.gui_server_controls import ServerSettingsDialog

    manager = desktop.server_lifecycle
    cron = ServerSettingsDialog("cron", manager, desktop)
    assert cron.timeout.isChecked() and not cron.autostart.isChecked()
    assert (cron.seconds.minimum(), cron.seconds.maximum(), cron.seconds.value()) == (1, 65535, 360)
    cron.timeout.setChecked(False)
    assert not cron.seconds.isEnabled()
    cron.autostart.setChecked(True)
    cron.save_settings()
    restored = ServerSettingsDialog("cron", manager, desktop)
    assert restored.autostart.isChecked() and not restored.seconds.isEnabled()
    iperf = ServerSettingsDialog("iperf", manager, desktop)
    assert iperf.timeout.isChecked() and iperf.seconds.value() == 360
    iperf.seconds.setValue(12)
    iperf.save_settings()
    assert manager.preferences("iperf").auto_stop_seconds == 12
    monkeypatch.setattr(manager, "save_preferences", lambda *_: _refuse("settings write failed"))
    restored.save_settings()
    assert not restored.result() and restored.error.text() == "settings write failed"


def test_crontab_editor_keeps_invalid_text_and_checks_concurrent_edits(desktop, monkeypatch):
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit

    from remote_ops_workspace import gui_server_controls as controls
    from remote_ops_workspace.embedded_cron import read_crontab_text, save_crontab_text

    view = controls.ServerSettingsDialog("cron", desktop.server_lifecycle, desktop)
    original = "# keep\u00a0spaces\r\n"
    save_crontab_text(original, expected="")
    schedule = original + "# local job\r\n"

    def edit(dialog):
        editor = dialog.findChild(QPlainTextEdit)
        save = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
        editor.setPlainText("invalid schedule")
        save.click()
        assert "invalid crontab" in " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert editor.toPlainText() == "invalid schedule" and not dialog.result()
        editor.setPlainText(schedule)
        save.click()
        assert dialog.result() == QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", edit)
    view.edit_crontab()
    assert read_crontab_text() == schedule

    def concurrent(dialog):
        save_crontab_text("# concurrent\n", expected=schedule)
        dialog.findChild(QPlainTextEdit).setPlainText("# local change\n")
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
        assert "changed" in " ".join(label.text() for label in dialog.findChildren(QLabel))
        assert not dialog.result()
        dialog.reject()

    monkeypatch.setattr(QDialog, "exec", concurrent)
    view.edit_crontab()
    assert read_crontab_text() == "# concurrent\n"
    monkeypatch.setattr(controls, "read_crontab_text", lambda: _refuse("crontab unreadable"))
    view.edit_crontab()
    assert view.error.text() == "crontab unreadable"
