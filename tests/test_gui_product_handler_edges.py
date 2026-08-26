from __future__ import annotations

import os

import pytest

from remote_ops_workspace.models import Profile


def _set_closure_value(monkeypatch, function, name: str, value) -> None:
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    monkeypatch.setattr(closure[index], "cell_contents", value)


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-product-handler-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1080, 720)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_mremoteng_document_controls_save_reconnect_tool_and_dock_edges(
    gui_window,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtWidgets import QFrame, QToolButton

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import (
        gui_design_mremoteng_connection_document_route,
    )

    _app, window = gui_window
    panel = QFrame(window)
    button = QToolButton(panel)
    dock = QFrame(window)
    window.mremoteng_document_controls_panel = panel
    window.mremoteng_property_grid_panel = dock
    window.mremoteng_document_control_buttons = {
        key: button
        for key in ("save", "reconnect", "external-tool", "dock-view")
    }
    window.mremoteng_reconnect_button = button
    window.mremoteng_connection_route_row = None
    window.mremoteng_connection_route_effective_cell = None

    route = gui_design_mremoteng_connection_document_route()
    window.apply_mremoteng_reconnect_route_properties(panel, route)
    assert panel.property(route.captured_property) is False
    window.apply_mremoteng_reconnect_route_properties(
        panel,
        route,
        triggered=True,
        reconnect_state="controlled-reconnect",
    )
    assert panel.property(route.captured_property) is True
    assert panel.property(route.captured_state_property) == "controlled-reconnect"

    profile = Profile(
        name="mRemote edge/profile",
        protocol="rdp",
        host="rdp.example.invalid",
        username="operator",
    )
    monkeypatch.setattr(window, "selected_profile_for_workflow", lambda: profile)
    monkeypatch.setattr(gui, "ensure_data_dir", lambda: tmp_path)
    artifact = window.save_mremoteng_document_artifact()
    assert artifact.is_file()
    assert "mRemote-edge-profile" in artifact.name

    monkeypatch.setattr(window, "selected_profile_for_workflow", lambda: None)
    monkeypatch.setattr(window, "profile_by_name", lambda _name: None)
    fallback_artifact = window.save_mremoteng_document_artifact()
    assert fallback_artifact.is_file()

    saved_artifact = tmp_path / "saved-document.json"
    saved_artifact.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        window,
        "save_mremoteng_document_artifact",
        lambda: saved_artifact,
    )
    window.handle_mremoteng_document_control("save")
    assert panel.property("mRemoteNgDocumentSaveTriggered") is True
    assert panel.property("mRemoteNgDocumentSaveArtifactBytes") == 2

    monkeypatch.setattr(
        window,
        "save_mremoteng_document_artifact",
        lambda: (_ for _ in ()).throw(OSError("read-only storage")),
    )
    window.handle_mremoteng_document_control("save")
    assert panel.property("mRemoteNgDocumentSaveTriggered") is False
    assert "read-only storage" in panel.property("mRemoteNgDocumentSaveError")

    window.handle_mremoteng_document_control("reconnect", True)
    assert panel.property(route.captured_property) is True
    assert "reconnected" in window.statusBar().currentMessage()

    tool_calls: list[str] = []
    monkeypatch.setattr(
        window,
        "show_external_tools_status",
        lambda: tool_calls.append("tools"),
    )
    window.handle_mremoteng_document_control("external-tool")
    assert tool_calls == ["tools"]
    assert panel.property("mRemoteNgExternalToolsWorkflowOpened") is True

    window.handle_mremoteng_document_control("dock-view", True)
    assert dock.isVisible() is True
    assert panel.property("mRemoteNgDockViewVisible") is True
    window.handle_mremoteng_document_control("dock-view", False)
    assert dock.isVisible() is False
    assert button.isChecked() is False

    window.mremoteng_document_controls_panel = None
    window.mremoteng_property_grid_panel = None
    window.mremoteng_document_control_buttons = {}
    window.handle_mremoteng_document_control("dock-view", True)
    with pytest.raises(RuntimeError, match="unsupported mRemoteNG"):
        window.handle_mremoteng_document_control("unknown")


def test_remmina_viewer_controls_terminal_drawer_and_screenshot_edges(
    gui_window,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtWidgets import QFrame, QToolButton, QWidget

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import (
        gui_design_remmina_clipboard_route,
        gui_design_remmina_screenshot_route,
    )

    _app, window = gui_window
    panel = QFrame(window)
    buttons = {
        key: QToolButton(panel)
        for key in ("fit", "scale-100", "clipboard", "fullscreen")
    }
    for button in buttons.values():
        button.setCheckable(True)
    window.remmina_viewer_controls_panel = panel
    window.remmina_viewer_control_buttons = buttons

    window.handle_remmina_viewer_control("fit")
    assert buttons["fit"].isChecked() is True
    assert buttons["scale-100"].isChecked() is False
    window.handle_remmina_viewer_control("scale-100")
    assert buttons["fit"].isChecked() is False
    assert buttons["scale-100"].isChecked() is True
    assert panel.property("remminaViewerScaleMode") == "scale-100"

    clipboard_route = gui_design_remmina_clipboard_route()
    window.handle_remmina_viewer_control("clipboard", True)
    assert (
        buttons["clipboard"].property(clipboard_route.clipboard_state_property)
        == "clipboard on"
    )
    window.handle_remmina_viewer_control("clipboard", False)
    assert (
        buttons["clipboard"].property(clipboard_route.clipboard_state_property)
        == "clipboard off"
    )

    fullscreen_calls: list[str] = []
    monkeypatch.setattr(window, "isMaximized", lambda: True)
    monkeypatch.setattr(window, "showFullScreen", lambda: fullscreen_calls.append("full"))
    monkeypatch.setattr(window, "showNormal", lambda: fullscreen_calls.append("normal"))
    monkeypatch.setattr(window, "showMaximized", lambda: fullscreen_calls.append("max"))
    window.handle_remmina_viewer_control("fullscreen", True)
    window.handle_remmina_viewer_control("fullscreen", False)
    assert fullscreen_calls == ["full", "normal", "max"]

    window._remmina_restore_maximized = False
    window.handle_remmina_viewer_control("fullscreen", False)
    assert fullscreen_calls[-1] == "normal"

    window.remmina_viewer_controls_panel = None
    window.remmina_viewer_control_buttons = {}
    window.handle_remmina_viewer_control("fit")
    window.handle_remmina_viewer_control("clipboard", True)
    window.handle_remmina_viewer_control("fullscreen", False)
    window.remmina_viewer_controls_panel = panel
    window.remmina_viewer_control_buttons = buttons
    with pytest.raises(RuntimeError, match="unsupported Remmina"):
        window.handle_remmina_viewer_control("unknown")

    drawer = QFrame(window)
    drawer.setVisible(False)
    toggle = QToolButton(window)
    window.toggle_product_terminal_drawer(drawer, toggle)
    assert drawer.property("productTerminalDrawerState") == "open"
    assert toggle.text() == "Hide terminal"
    window.toggle_product_terminal_drawer(drawer, toggle)
    assert drawer.property("productTerminalDrawerState") == "closed"
    assert toggle.text() == "Terminal"

    screenshot_button = QToolButton(panel)
    window.remmina_screenshot_button = screenshot_button
    route = gui_design_remmina_screenshot_route()
    window.apply_remmina_screenshot_capture_route_properties(panel, route)
    assert panel.property(route.captured_property) is False
    monkeypatch.setattr(gui, "ensure_data_dir", lambda: tmp_path)
    window.handle_remmina_screenshot_capture()
    screenshot_path = window.remmina_last_screenshot_path
    assert screenshot_path is not None and screenshot_path.is_file()
    assert screenshot_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert panel.property("remminaScreenshotCaptureBytes") > 0

    real_write = gui.write_bytes_atomic
    monkeypatch.setattr(
        gui,
        "write_bytes_atomic",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    window.handle_remmina_screenshot_capture()
    assert window.remmina_last_screenshot_path is None
    assert panel.property("remminaScreenshotCaptureError") == "disk full"
    monkeypatch.setattr(gui, "write_bytes_atomic", real_write)

    class _BadPixmap:
        @staticmethod
        def save(buffer, _format: str) -> bool:
            assert buffer.isOpen()
            buffer.write(b"not-a-png")
            return True

    class _BadGrabWidget(QWidget):
        def grab(self, *_args, **_kwargs):
            return _BadPixmap()

    bad_surface = _BadGrabWidget()
    bad_index = window.add_workspace_tab(bad_surface, "Bad screenshot", role="tool")
    window.set_workspace_tab_index(bad_index)
    window.handle_remmina_screenshot_capture()
    assert "did not produce a PNG" in panel.property("remminaScreenshotCaptureError")

    class _EncodeFailurePixmap:
        @staticmethod
        def save(_buffer, _format: str) -> bool:
            return False

    class _EncodeFailureWidget(QWidget):
        def grab(self, *_args, **_kwargs):
            return _EncodeFailurePixmap()

    failure_surface = _EncodeFailureWidget()
    failure_index = window.add_workspace_tab(
        failure_surface,
        "Encode failure",
        role="tool",
    )
    window.set_workspace_tab_index(failure_index)
    window.handle_remmina_screenshot_capture()
    assert "could not encode" in panel.property("remminaScreenshotCaptureError")


def test_product_document_and_screenshot_missing_widget_edges(
    gui_window,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtWidgets import QFrame, QToolButton, QTreeWidgetItem

    from remote_ops_workspace import gui

    _app, window = gui_window
    panel = QFrame(window)
    button = QToolButton(panel)
    saved = tmp_path / "document.json"
    saved.write_text("{}", encoding="utf-8")

    window.mremoteng_document_controls_panel = None
    window.mremoteng_document_control_buttons = {"save": button}
    monkeypatch.setattr(
        window,
        "save_mremoteng_document_artifact",
        lambda: (_ for _ in ()).throw(OSError("controlled failure")),
    )
    window.handle_mremoteng_document_control("save")
    assert button.property("mRemoteNgDocumentSaveTriggered") is False

    window.mremoteng_document_controls_panel = panel
    window.mremoteng_document_control_buttons = {"save": None}
    monkeypatch.setattr(window, "save_mremoteng_document_artifact", lambda: saved)
    window.handle_mremoteng_document_control("save")
    assert panel.property("mRemoteNgDocumentSaveTriggered") is True
    window.mremoteng_document_controls_panel = None
    window.mremoteng_document_control_buttons = {"external-tool": None}
    tools: list[str] = []
    monkeypatch.setattr(window, "show_external_tools_status", lambda: tools.append("tools"))
    window.handle_mremoteng_document_control("external-tool")
    assert tools == ["tools"]

    window.open_sftp_context_item(None)
    window.open_sftp_context_item(QTreeWidgetItem(["  "]))

    screenshot_root = tmp_path / "missing-screenshot-root"
    monkeypatch.setattr(gui, "ensure_data_dir", lambda: screenshot_root)
    monkeypatch.setattr(gui, "write_bytes_atomic", lambda *_args, **_kwargs: None)
    window.remmina_viewer_controls_panel = None
    window.remmina_screenshot_button = None
    window.handle_remmina_screenshot_capture()
    assert window.remmina_last_screenshot_path is None

    class _ClosedBuffer:
        def __init__(self, _encoded) -> None:
            return None

        @staticmethod
        def open(_mode) -> bool:
            return False

    _set_closure_value(
        monkeypatch,
        type(window).handle_remmina_screenshot_capture,
        "QBuffer",
        _ClosedBuffer,
    )
    window.handle_remmina_screenshot_capture()
    assert window.statusBar().currentMessage() == "Remmina screenshot capture failed"


def test_product_control_icon_unknown_key_fallbacks_are_visible(gui_window) -> None:
    _app, window = gui_window

    assert window.mremoteng_document_control_icon(
        "future-action",
        size=16,
    ).isNull() is False
    assert window.remmina_viewer_control_icon(
        "future-action",
        size=16,
    ).isNull() is False
