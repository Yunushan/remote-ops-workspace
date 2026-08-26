import importlib
import runpy
import sys

import pytest

import remote_ops_workspace.cli as cli


def test_package_module_entrypoint_returns_cli_status(monkeypatch) -> None:
    imported = importlib.import_module("remote_ops_workspace.__main__")
    assert imported.main is cli.main

    monkeypatch.setattr(cli, "main", lambda: 7)
    monkeypatch.delitem(sys.modules, "remote_ops_workspace.__main__")
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("remote_ops_workspace.__main__", run_name="__main__")

    assert exc_info.value.code == 7


def test_gui_module_entrypoint_returns_event_loop_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    imported = importlib.import_module("remote_ops_workspace.gui")
    monkeypatch.setattr(QApplication, "exec", lambda _self: 23)
    monkeypatch.delitem(sys.modules, "remote_ops_workspace.gui")
    try:
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("remote_ops_workspace.gui", run_name="__main__")
    finally:
        sys.modules["remote_ops_workspace.gui"] = imported
        app = QApplication.instance()
        if app is not None:
            for widget in app.topLevelWidgets():
                widget.close()
            app.processEvents()

    assert exc_info.value.code == 23


def test_gui_null_icon_and_dependency_error_without_cause(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")

    from remote_ops_workspace import gui

    monkeypatch.setattr(
        gui,
        "application_icon_path",
        lambda: tmp_path / "missing-application-icon.ico",
    )
    app, window = gui.create_main_window(
        ["gui-null-icon-edge"],
        show=False,
        preview_samples=False,
    )
    assert window is not None
    window.close()
    app.processEvents()

    def fail_startup(*_args, **_kwargs):
        raise gui.GuiDependencyError("controlled dependency failure")

    monkeypatch.setattr(gui, "create_main_window", fail_startup)
    assert gui.main() == 2
    output = capsys.readouterr().out
    assert output.strip() == "controlled dependency failure"
