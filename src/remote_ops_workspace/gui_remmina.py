from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .file_safety import write_bytes_atomic
from .gui_designs import (
    gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_filter_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route,
    gui_design_remmina_screenshot_route,
    gui_design_remmina_sftp_transfer_route,
    gui_design_remmina_viewer_controls,
)
from .gui_dialogs import _literal_label
from .gui_icons import draw_remmina_viewer_control_icon
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value, _safe_tooltip_html
from .paths import ensure_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QStatusBar, QTabWidget, QTextEdit


class RemminaWorkspace:
    """Build the Remmina profile list, viewer and transfer surfaces."""

    if TYPE_CHECKING:
        log: QTextEdit
        tabs: QTabWidget

        def filter_remmina_profile_rows(self, text: str) -> None: ...
        def generated_icon(
            self, size: int, draw: Callable[[QPainter, int], None], *, antialias: bool = True,
        ) -> QIcon: ...
        def isMaximized(self) -> bool: ...
        def set_interaction_state(self, widget: QToolButton, state: str) -> None: ...
        def showFullScreen(self) -> None: ...
        def showMaximized(self) -> None: ...
        def showNormal(self) -> None: ...
        def statusBar(self) -> QStatusBar: ...
        def toggle_product_terminal_drawer(self, drawer: QWidget, button: QToolButton) -> None: ...

    def build_remmina_native_viewer_surface(
        self,
        terminal_pane: TerminalPane | None = None,
    ) -> QFrame:
        """Connected Remmina-style viewer canvas with GTK-like controls."""
        route = gui_design_remmina_profile_viewer_route()
        panel = QFrame()
        panel.setObjectName("remminaNativeViewerSurface")
        panel.setProperty("designPreset", "remmina")
        panel.setProperty("remminaNativeSurfaceRole", "connected-viewer")
        panel.setProperty("remminaProfileViewerRouteKey", route.key)
        panel.setMinimumHeight(360)
        panel.setStyleSheet(
            "QFrame#remminaNativeViewerSurface { background: #edf1f5; border: 1px solid #b7c2cc; }"
            "QLabel#remminaNativeViewerCanvas { background: #1c1f22; color: #e9edf2; border: 1px solid #8d99a5; font-family: Consolas, 'Courier New'; }"
            "QToolButton#remminaNativeViewerAction { background: #ffffff; color: #354d64; border: 1px solid #aab8c6; padding: 4px 8px; }"
            "QToolButton#remminaNativeTerminalToggle { background: #ffffff; color: #354d64; border: 1px solid #aab8c6; padding: 4px 8px; }"
            "QLabel#remminaNativeViewerDetails { background: #ffffff; color: #334352; border: 1px solid #b7c2cc; padding: 8px; }"
            "QFrame#remminaNativeTerminalDrawer { background: #1c1f22; border: 1px solid #8d99a5; }"
            "QTextEdit#terminalOutput { background: #1c1f22; color: #e9edf2; border: 0px;"
            "font-family: Consolas, 'Courier New'; font-size: 9pt; }"
            "QLineEdit#terminalInput { background: #252a2f; color: #f2f5f8; border: 1px solid #8d99a5;"
            "padding: 3px 6px; font-family: Consolas, 'Courier New'; }"
        )
        root = QVBoxLayout(panel)
        root.setContentsMargins(8, 7, 8, 8)
        root.setSpacing(6)
        toolbar = QHBoxLayout()
        profile_chrome = gui_design_remmina_profile_list_chrome()
        selected_profile = next(
            (row.name for row in profile_chrome.rows if row.key == route.selected_profile_key),
            route.selected_profile_key,
        )
        toolbar.addWidget(_literal_label(f"{selected_profile} ({route.protocol})"))
        toolbar.addStretch(1)
        for control in gui_design_remmina_viewer_controls():
            button = QToolButton()
            button.setObjectName("remminaNativeViewerAction")
            button.setText(control.label)
            button.setToolTip(control.tooltip)
            button.setCheckable(control.key in {"fit", "scale-100", "clipboard", "fullscreen"})
            button.setChecked(control.key in {route.viewer_control_key, gui_design_remmina_clipboard_route().viewer_control_key})
            if control.key == gui_design_remmina_screenshot_route().viewer_control_key:
                button.clicked.connect(self.handle_remmina_screenshot_capture)
            else:
                button.clicked.connect(lambda checked=False, key=control.key: self.handle_remmina_viewer_control(key, checked))
            toolbar.addWidget(button)
        terminal_toggle: QToolButton | None = None
        if terminal_pane is not None:
            terminal_toggle = QToolButton()
            terminal_toggle.setObjectName("remminaNativeTerminalToggle")
            terminal_toggle.setText("Terminal")
            terminal_toggle.setToolTip("Show or hide the connected terminal")
            toolbar.addWidget(terminal_toggle)
        root.addLayout(toolbar)
        body = QHBoxLayout()
        viewer = QLabel("Remote desktop session\n\n\n\n\n\n\n\n\n\n\n\n\n\n\noperator@win-admin  ·  Connected")
        viewer.setObjectName("remminaNativeViewerCanvas")
        viewer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        viewer.setMinimumWidth(520)
        body.addWidget(viewer, 3)
        details = QLabel("Protocol   RDP\nStatus     Connected\nScale      100%\nClipboard  enabled\nScreenshot ready\n\nSFTP transfer\n/var/log  ·  1 queued")
        details.setObjectName("remminaNativeViewerDetails")
        details.setMinimumWidth(180)
        body.addWidget(details, 1)
        root.addLayout(body, 1)
        if terminal_pane is not None:
            terminal_drawer = QFrame()
            terminal_drawer.setObjectName("remminaNativeTerminalDrawer")
            terminal_drawer.setProperty("productTerminalDrawerPreset", "remmina")
            terminal_drawer.setProperty("productTerminalDrawerState", "closed")
            drawer_layout = QVBoxLayout(terminal_drawer)
            drawer_layout.setContentsMargins(4, 4, 4, 4)
            drawer_layout.addWidget(terminal_pane)
            terminal_pane.header.setVisible(False)
            terminal_pane.setProperty("remminaNativeTerminalEmbedded", True)
            terminal_pane.setMinimumSize(0, 0)
            terminal_pane.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            terminal_drawer.setVisible(False)
            root.addWidget(terminal_drawer)
            terminal_button = _required_gui_value(
                terminal_toggle,
                "Remmina terminal toggle",
            )
            terminal_button.clicked.connect(
                lambda _checked=False, drawer=terminal_drawer, button=terminal_button:
                self.toggle_product_terminal_drawer(drawer, button)
            )
        return panel

    @staticmethod
    def apply_remmina_screenshot_capture_route_properties(
        widget,
        route,
        *,
        captured: bool = False,
        capture_state: str | None = None,
        artifact: str | None = None,
    ) -> None:
        state_value = capture_state or route.capture_state
        artifact_value = artifact or route.capture_artifact
        properties = {
            "remminaScreenshotRouteKey": route.key,
            "remminaScreenshotRouteRole": route.route_role,
            "remminaScreenshotViewerControlsObject": route.viewer_controls_object,
            "remminaScreenshotViewerControlKey": route.viewer_control_key,
            "remminaScreenshotViewerControlObject": route.viewer_control_object,
            route.tab_label_property: route.active_tab_label,
            "remminaScreenshotRouteProtocol": route.protocol,
            route.capture_state_property: route.capture_state,
            route.capture_artifact_property: route.capture_artifact,
            "remminaScreenshotRouteStatusSegment": route.status_segment,
            "remminaScreenshotRouteDetailLine": route.detail_line,
            "remminaScreenshotRouteActivityLine": route.activity_line,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_property: captured,
            route.captured_state_property: state_value if captured else "",
            route.captured_artifact_property: (
                route.capture_artifact if captured else ""
            ),
            route.live_triggered_property: captured,
            route.live_capture_state_property: state_value,
            route.live_capture_artifact_property: route.capture_artifact,
            "remminaScreenshotCapturePath": (
                artifact_value if captured else ""
            ),
            "remminaScreenshotRouteRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_remmina_viewer_control(
        self,
        action_key: str,
        checked: bool = False,
    ) -> None:
        route = gui_design_remmina_profile_viewer_route()
        clipboard_route = gui_design_remmina_clipboard_route()
        buttons = getattr(self, "remmina_viewer_control_buttons", {})
        panel = getattr(self, "remmina_viewer_controls_panel", None)
        if action_key in {"fit", "scale-100"}:
            for key in ("fit", "scale-100"):
                button = buttons.get(key)
                if button is None:
                    continue
                active = key == action_key
                button.setChecked(active)
                button.setProperty(
                    route.control_active_property,
                    "true" if active else "false",
                )
                self.set_interaction_state(
                    button,
                    "checked" if active else "normal",
                )
            if panel is not None:
                panel.setProperty("remminaViewerScaleMode", action_key)
            self.statusBar().showMessage(
                "Remmina viewer scale: "
                + ("fit to viewer" if action_key == "fit" else "100%")
            )
            return
        if action_key == "clipboard":
            enabled = bool(checked)
            state_value = "clipboard on" if enabled else "clipboard off"
            button = buttons.get(action_key)
            for widget in (panel, button):
                if widget is not None:
                    widget.setProperty(
                        clipboard_route.clipboard_state_property,
                        state_value,
                    )
                    widget.setProperty(
                        clipboard_route.control_active_property,
                        "true" if enabled else "false",
                    )
            if button is not None:
                self.set_interaction_state(
                    button,
                    "checked" if enabled else "normal",
                )
            self.statusBar().showMessage(
                f"Remmina clipboard sync {'enabled' if enabled else 'disabled'}"
            )
            return
        if action_key == "fullscreen":
            enabled = bool(checked)
            button = buttons.get(action_key)
            if enabled:
                self._remmina_restore_maximized = self.isMaximized()
                self.showFullScreen()
            else:
                self.showNormal()
                if getattr(self, "_remmina_restore_maximized", False):
                    self.showMaximized()
            for widget in (panel, button):
                if widget is not None:
                    widget.setProperty("remminaViewerFullscreen", enabled)
            if button is not None:
                button.setChecked(enabled)
                self.set_interaction_state(
                    button,
                    "checked" if enabled else "normal",
                )
            self.statusBar().showMessage(
                f"Remmina viewer fullscreen {'enabled' if enabled else 'restored'}"
            )
            return
        raise RuntimeError(f"unsupported Remmina viewer control: {action_key}")

    def handle_remmina_screenshot_capture(self, _checked: bool = False) -> None:
        route = gui_design_remmina_screenshot_route()
        artifact_path: Path | None = None
        artifact_size = 0
        capture_error = ""
        try:
            artifact_path = (
                ensure_data_dir()
                / "gui-artifacts"
                / "remmina"
                / Path(route.capture_artifact).name
            )
            source = self.tabs.currentWidget() or cast(QWidget, self)
            pixmap = source.grab()
            encoded = QByteArray()
            buffer = QBuffer(encoded)
            if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError("could not open private screenshot buffer")
            try:
                if not pixmap.save(buffer, "PNG"):
                    raise RuntimeError("could not encode Remmina screenshot as PNG")
            finally:
                buffer.close()
            payload = encoded.data()
            if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Remmina screenshot encoder did not produce a PNG")
            write_bytes_atomic(artifact_path, payload, private=True)
            if artifact_path.is_file():
                artifact_size = artifact_path.stat().st_size
            artifact_valid = artifact_size == len(payload) and artifact_size > 0
        except (OSError, RuntimeError) as exc:
            artifact_valid = False
            capture_error = str(exc)
        state = "captured" if artifact_valid else "capture failed"
        route_widgets = (
            getattr(self, "remmina_viewer_controls_panel", None),
            getattr(self, "remmina_screenshot_button", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_remmina_screenshot_capture_route_properties(
                route_widget,
                route,
                captured=artifact_valid,
                capture_state=state,
                artifact=(
                    str(artifact_path)
                    if artifact_path is not None
                    else route.capture_artifact
                ),
            )
            route_widget.setProperty(
                "remminaScreenshotCaptureError",
                capture_error,
            )
            route_widget.setProperty(
                "remminaScreenshotCaptureBytes",
                artifact_size if artifact_valid else 0,
            )
        self.remmina_last_screenshot_path = (
            artifact_path if artifact_valid else None
        )
        if artifact_valid and artifact_path is not None:
            self.log.append(
                f"REMMINA SCREENSHOT SAVED: {artifact_path.name}"
            )
            self.statusBar().showMessage(
                f"Remmina screenshot captured: {artifact_path.name}"
            )
        else:
            self.statusBar().showMessage("Remmina screenshot capture failed")

    @staticmethod
    def apply_remmina_sftp_transfer_action_route_properties(
        widget,
        route,
        *,
        triggered: bool = False,
        action_key: str | None = None,
        status: str | None = None,
    ) -> None:
        actions_value = "|".join(route.toolbar_actions)
        action_value = action_key or route.action_key
        status_value = status or route.transfer_status
        properties = {
            "remminaSftpTransferRouteKey": route.key,
            "remminaSftpTransferRouteRole": route.route_role,
            "remminaSftpTransferRouteProfileListObject": route.profile_list_object,
            "remminaSftpTransferRouteSelectedProfileKey": route.selected_profile_key,
            route.selected_profile_property: route.selected_profile_name,
            "remminaSftpTransferRouteProtocol": route.selected_profile_protocol,
            "remminaSftpTransferRouteStatus": route.selected_profile_status,
            "remminaSftpTransferRouteSelectedProfileObject": route.selected_profile_object,
            "remminaSftpTransferRouteSelectedTreeLabel": route.selected_tree_label,
            "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
            "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
            "remminaSftpTransferRouteToolbarActionObject": route.toolbar_action_object,
            route.toolbar_active_property: "true",
            route.tab_label_property: route.active_tab_label,
            "remminaSftpTransferRoutePanelObject": route.transfer_panel_object,
            "remminaSftpTransferRouteToolbarObject": route.toolbar_object,
            "remminaSftpTransferRoutePathObject": route.path_object,
            "remminaSftpTransferRouteTableObject": route.table_object,
            "remminaSftpTransferRouteRowObject": route.row_object,
            "remminaSftpTransferRouteQueueObject": route.queue_object,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "remminaSftpTransferRouteActiveRowName": route.active_row_name,
            "remminaSftpTransferRouteQueueLabel": route.transfer_queue_label,
            route.queue_state_property: route.transfer_status,
            "remminaSftpTransferRouteDetailLine": route.detail_line,
            "remminaSftpTransferRouteActivityLine": route.activity_line,
            "remminaSftpTransferRouteActionObject": route.action_object,
            "remminaSftpTransferRouteActionKey": action_value,
            "remminaSftpTransferRouteActionLabel": route.action_label,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_property: triggered,
            route.captured_action_property: action_value if triggered else "",
            route.captured_status_property: status_value if triggered else "",
            route.live_triggered_property: triggered,
            route.live_action_property: action_value,
            route.live_status_property: status_value,
            "remminaSftpTransferRouteRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_remmina_sftp_transfer_action(self, action_key: str | None = None) -> None:
        route = gui_design_remmina_sftp_transfer_route()
        action_value = action_key or route.action_key
        status_value = (
            route.action_status
            if action_value == route.action_key
            else f"{action_value} queued"
        )
        queue = getattr(self, "remmina_sftp_transfer_queue", None)
        if queue is not None:
            queue.setText(f"Queue: {route.transfer_queue_label} ({status_value})")
        route_widgets = (
            getattr(self, "remmina_sftp_profile_panel", None),
            getattr(self, "remmina_sftp_profile_row", None),
            getattr(self, "remmina_sftp_transfer_panel", None),
            getattr(self, "remmina_sftp_transfer_toolbar", None),
            getattr(self, "remmina_sftp_transfer_path", None),
            getattr(self, "remmina_sftp_transfer_table", None),
            queue,
            *getattr(self, "remmina_sftp_transfer_action_buttons", []),
            getattr(self, "remmina_sftp_transfer_active_row", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_remmina_sftp_transfer_action_route_properties(
                route_widget,
                route,
                triggered=True,
                action_key=action_value,
                status=status_value,
            )
        self.statusBar().showMessage(f"Remmina SFTP {action_value}: {status_value}")

    def build_remmina_viewer_controls_evidence(self) -> QFrame:
        route = gui_design_remmina_profile_viewer_route()
        clipboard_route = gui_design_remmina_clipboard_route()
        screenshot_route = gui_design_remmina_screenshot_route()
        panel = QFrame()
        panel.setObjectName("remminaViewerControls")
        panel.setProperty("designPreset", "remmina")
        panel.setProperty("remminaProfileViewerRouteKey", route.key)
        panel.setProperty("remminaProfileViewerRouteRole", route.route_role)
        panel.setProperty("remminaProfileViewerSelectedProfileKey", route.selected_profile_key)
        panel.setProperty("remminaProfileViewerSelectedProfileObject", route.selected_profile_object)
        panel.setProperty("remminaProfileViewerControlsObject", route.viewer_controls_object)
        panel.setProperty("remminaProfileViewerControlKey", route.viewer_control_key)
        panel.setProperty("remminaProfileViewerControlObject", route.viewer_control_object)
        panel.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
        panel.setProperty("remminaProfileViewerProtocol", route.protocol)
        panel.setProperty("remminaProfileViewerStatus", route.profile_status)
        panel.setProperty("remminaProfileViewerRenderSource", route.render_source)
        panel.setProperty("remminaClipboardRouteKey", clipboard_route.key)
        panel.setProperty("remminaClipboardRouteRole", clipboard_route.route_role)
        panel.setProperty("remminaClipboardViewerControlsObject", clipboard_route.viewer_controls_object)
        panel.setProperty("remminaClipboardViewerControlKey", clipboard_route.viewer_control_key)
        panel.setProperty("remminaClipboardViewerControlObject", clipboard_route.viewer_control_object)
        panel.setProperty("remminaClipboardRouteActiveTab", clipboard_route.active_tab_label)
        panel.setProperty("remminaClipboardRouteProtocol", clipboard_route.protocol)
        panel.setProperty("remminaClipboardRouteState", clipboard_route.clipboard_state)
        panel.setProperty("remminaClipboardRouteStatusSegment", clipboard_route.status_segment)
        panel.setProperty("remminaClipboardRouteDetailLine", clipboard_route.detail_line)
        panel.setProperty("remminaClipboardRouteActivityLine", clipboard_route.activity_line)
        panel.setProperty("remminaClipboardRouteRenderSource", clipboard_route.render_source)
        panel.setProperty("remminaScreenshotRouteKey", screenshot_route.key)
        panel.setProperty("remminaScreenshotRouteRole", screenshot_route.route_role)
        panel.setProperty("remminaScreenshotViewerControlsObject", screenshot_route.viewer_controls_object)
        panel.setProperty("remminaScreenshotViewerControlKey", screenshot_route.viewer_control_key)
        panel.setProperty("remminaScreenshotViewerControlObject", screenshot_route.viewer_control_object)
        panel.setProperty("remminaScreenshotRouteActiveTab", screenshot_route.active_tab_label)
        panel.setProperty("remminaScreenshotRouteProtocol", screenshot_route.protocol)
        panel.setProperty("remminaScreenshotRouteState", screenshot_route.capture_state)
        panel.setProperty("remminaScreenshotRouteArtifact", screenshot_route.capture_artifact)
        panel.setProperty("remminaScreenshotRouteStatusSegment", screenshot_route.status_segment)
        panel.setProperty("remminaScreenshotRouteDetailLine", screenshot_route.detail_line)
        panel.setProperty("remminaScreenshotRouteActivityLine", screenshot_route.activity_line)
        panel.setProperty("remminaScreenshotRouteRenderSource", screenshot_route.render_source)
        self.remmina_viewer_controls_panel = panel
        self.apply_remmina_screenshot_capture_route_properties(panel, screenshot_route)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(6)
        layout.addStretch(1)
        self.remmina_viewer_control_buttons = {}
        for control in gui_design_remmina_viewer_controls():
            button = QToolButton()
            button.setObjectName("remminaViewerControl")
            button.setProperty("remminaViewerControlKey", control.key)
            button.setProperty("remminaViewerIconKey", control.icon_key)
            button.setProperty("remminaViewerControlStaticWidth", control.static_width)
            button.setProperty("remminaViewerControlStaticStep", control.static_step)
            button.setProperty("remminaViewerControlStaticY", control.static_y)
            button.setProperty("remminaViewerControlStaticHeight", control.static_height)
            button.setProperty("remminaViewerControlStaticIconX", control.static_icon_x)
            button.setProperty("remminaViewerControlStaticIconSize", control.static_icon_size)
            button.setProperty("remminaViewerControlStaticLabelX", control.static_label_x)
            button.setProperty("remminaViewerControlLiveIconSize", control.live_icon_size)
            button.setProperty("remminaViewerControlLiveMinWidth", control.live_min_width)
            button.setProperty("remminaViewerControlLiveButtonHeight", control.live_button_height)
            button.setProperty("remminaViewerControlRenderSource", control.render_source)
            self.remmina_viewer_control_buttons[control.key] = button
            if control.key == route.viewer_control_key:
                button.setProperty("remminaProfileViewerRouteKey", route.key)
                button.setProperty("remminaProfileViewerRouteRole", route.route_role)
                button.setProperty("remminaProfileViewerSelectedProfileKey", route.selected_profile_key)
                button.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                button.setProperty("remminaProfileViewerStatus", route.profile_status)
                button.setProperty(route.control_active_property, "true")
            else:
                button.setProperty(route.control_active_property, "false")
            if control.key == clipboard_route.viewer_control_key:
                button.setProperty("remminaClipboardRouteKey", clipboard_route.key)
                button.setProperty("remminaClipboardRouteRole", clipboard_route.route_role)
                button.setProperty(clipboard_route.tab_label_property, clipboard_route.active_tab_label)
                button.setProperty("remminaClipboardRouteProtocol", clipboard_route.protocol)
                button.setProperty(clipboard_route.clipboard_state_property, clipboard_route.clipboard_state)
                button.setProperty("remminaClipboardRouteStatusSegment", clipboard_route.status_segment)
                button.setProperty("remminaClipboardRouteDetailLine", clipboard_route.detail_line)
                button.setProperty("remminaClipboardRouteActivityLine", clipboard_route.activity_line)
                button.setProperty("remminaClipboardRouteRenderSource", clipboard_route.render_source)
                button.setProperty(clipboard_route.control_active_property, "true")
            else:
                button.setProperty(clipboard_route.control_active_property, "false")
            if control.key == screenshot_route.viewer_control_key:
                button.setProperty("remminaScreenshotRouteKey", screenshot_route.key)
                button.setProperty("remminaScreenshotRouteRole", screenshot_route.route_role)
                button.setProperty(screenshot_route.tab_label_property, screenshot_route.active_tab_label)
                button.setProperty("remminaScreenshotRouteProtocol", screenshot_route.protocol)
                button.setProperty(screenshot_route.capture_state_property, screenshot_route.capture_state)
                button.setProperty(screenshot_route.capture_artifact_property, screenshot_route.capture_artifact)
                button.setProperty("remminaScreenshotRouteStatusSegment", screenshot_route.status_segment)
                button.setProperty("remminaScreenshotRouteDetailLine", screenshot_route.detail_line)
                button.setProperty("remminaScreenshotRouteActivityLine", screenshot_route.activity_line)
                button.setProperty("remminaScreenshotRouteRenderSource", screenshot_route.render_source)
                button.setProperty(screenshot_route.control_active_property, "true")
                self.remmina_screenshot_button = button
                self.apply_remmina_screenshot_capture_route_properties(button, screenshot_route)
            else:
                button.setProperty(screenshot_route.control_active_property, "false")
            button.setText(control.label)
            button.setToolTip(control.tooltip)
            button.setIcon(self.remmina_viewer_control_icon(control.icon_key, size=control.live_icon_size))
            button.setIconSize(QSize(control.live_icon_size, control.live_icon_size))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setMinimumWidth(control.live_min_width)
            button.setMinimumHeight(control.live_button_height)
            stateful_keys = {"fit", "scale-100", "clipboard", "fullscreen"}
            button.setCheckable(control.key in stateful_keys)
            initially_checked = (
                control.key == route.viewer_control_key
                or control.key == clipboard_route.viewer_control_key
            )
            if button.isCheckable():
                button.setChecked(initially_checked)
                self.set_interaction_state(
                    button,
                    "checked" if initially_checked else "normal",
                )
            if control.key == screenshot_route.viewer_control_key:
                button.clicked.connect(self.handle_remmina_screenshot_capture)
            else:
                button.clicked.connect(
                    lambda checked=False, key=control.key: self.handle_remmina_viewer_control(
                        key,
                        checked,
                    )
                )
            layout.addWidget(button)
        return panel

    def build_remmina_sftp_transfer_evidence(self) -> QFrame:
        route = gui_design_remmina_sftp_transfer_route()
        actions_value = "|".join(route.toolbar_actions)
        route_props = {
            "remminaSftpTransferRouteKey": route.key,
            "remminaSftpTransferRouteRole": route.route_role,
            "remminaSftpTransferRouteProfileListObject": route.profile_list_object,
            "remminaSftpTransferRouteSelectedProfileKey": route.selected_profile_key,
            route.selected_profile_property: route.selected_profile_name,
            "remminaSftpTransferRouteProtocol": route.selected_profile_protocol,
            "remminaSftpTransferRouteStatus": route.selected_profile_status,
            "remminaSftpTransferRouteSelectedProfileObject": route.selected_profile_object,
            "remminaSftpTransferRouteSelectedTreeLabel": route.selected_tree_label,
            "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
            "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
            "remminaSftpTransferRouteToolbarActionObject": route.toolbar_action_object,
            route.tab_label_property: route.active_tab_label,
            "remminaSftpTransferRoutePanelObject": route.transfer_panel_object,
            "remminaSftpTransferRouteToolbarObject": route.toolbar_object,
            "remminaSftpTransferRoutePathObject": route.path_object,
            "remminaSftpTransferRouteTableObject": route.table_object,
            "remminaSftpTransferRouteRowObject": route.row_object,
            "remminaSftpTransferRouteQueueObject": route.queue_object,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "remminaSftpTransferRouteActiveRowName": route.active_row_name,
            "remminaSftpTransferRouteQueueLabel": route.transfer_queue_label,
            route.queue_state_property: route.transfer_status,
            "remminaSftpTransferRouteDetailLine": route.detail_line,
            "remminaSftpTransferRouteActivityLine": route.activity_line,
            "remminaSftpTransferRouteRenderSource": route.render_source,
        }
        panel = QFrame()
        panel.setObjectName(route.transfer_panel_object)
        for property_name, value in route_props.items():
            panel.setProperty(property_name, value)
        self.remmina_sftp_transfer_panel = panel
        self.apply_remmina_sftp_transfer_action_route_properties(panel, route)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(5)

        header = QHBoxLayout()
        title = _literal_label(f"SFTP transfer - {route.selected_profile_name}")
        title.setObjectName("remminaSftpTransferTitle")
        title.setProperty("remminaSftpTransferRouteKey", route.key)
        queue = _literal_label(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
        queue.setObjectName(route.queue_object)
        for property_name, value in route_props.items():
            queue.setProperty(property_name, value)
        self.remmina_sftp_transfer_queue = queue
        self.apply_remmina_sftp_transfer_action_route_properties(queue, route)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(queue)
        layout.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName(route.toolbar_object)
        for property_name, value in route_props.items():
            toolbar.setProperty(property_name, value)
        self.remmina_sftp_transfer_toolbar = toolbar
        self.apply_remmina_sftp_transfer_action_route_properties(toolbar, route)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.remmina_sftp_transfer_action_buttons = []
        for action_key in route.toolbar_actions:
            action = QToolButton()
            action.setObjectName(route.action_object)
            action.setProperty("remminaSftpTransferRouteKey", route.key)
            action.setProperty("remminaSftpTransferRouteActionKey", action_key)
            action.setProperty(route.toolbar_actions_property, actions_value)
            self.apply_remmina_sftp_transfer_action_route_properties(action, route, action_key=action_key)
            self.remmina_sftp_transfer_action_buttons.append(action)
            if action_key == route.action_key:
                self.remmina_sftp_transfer_action_button = action
            action.clicked.connect(
                lambda _checked=False, key=action_key: self.handle_remmina_sftp_transfer_action(
                    key
                )
            )
            action.setText(action_key.title())
            action.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            toolbar_layout.addWidget(action)
        toolbar_layout.addStretch(1)
        layout.addWidget(toolbar)

        path = _literal_label(f"Remote path: {route.remote_path}")
        path.setObjectName(route.path_object)
        for property_name, value in route_props.items():
            path.setProperty(property_name, value)
        self.remmina_sftp_transfer_path = path
        self.apply_remmina_sftp_transfer_action_route_properties(path, route)
        layout.addWidget(path)

        table = QFrame()
        table.setObjectName(route.table_object)
        for property_name, value in route_props.items():
            table.setProperty(property_name, value)
        self.remmina_sftp_transfer_table = table
        self.apply_remmina_sftp_transfer_action_route_properties(table, route)
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(2)
        header_row = QLabel("Name        Size     Modified")
        header_row.setObjectName("remminaSftpTransferHeader")
        table_layout.addWidget(header_row)
        for row in route.file_rows:
            row_frame = QFrame()
            row_frame.setObjectName(route.row_object)
            for property_name, value in route_props.items():
                row_frame.setProperty(property_name, value)
            row_frame.setProperty(route.row_name_property, row.name)
            row_frame.setProperty(route.row_kind_property, row.kind)
            row_frame.setProperty(route.row_selected_property, row.selected)
            row_frame.setProperty("remminaSftpTransferRouteRowKey", row.key)
            row_frame.setProperty("remminaSftpTransferRouteRowSize", row.size)
            row_frame.setProperty("remminaSftpTransferRouteRowModified", row.modified)
            self.apply_remmina_sftp_transfer_action_route_properties(row_frame, route)
            if row.name == route.active_row_name:
                self.remmina_sftp_transfer_active_row = row_frame
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(4, 1, 4, 1)
            row_layout.setSpacing(8)
            name = _literal_label(row.name)
            name.setObjectName("remminaSftpTransferRowName")
            size = _literal_label(row.size)
            size.setObjectName("remminaSftpTransferRowSize")
            modified = _literal_label(row.modified)
            modified.setObjectName("remminaSftpTransferRowModified")
            row_layout.addWidget(name, 2)
            row_layout.addWidget(size, 1)
            row_layout.addWidget(modified, 1)
            table_layout.addWidget(row_frame)
        layout.addWidget(table)
        return panel

    def remmina_viewer_control_icon(self, icon_key: str, *, size: int) -> QIcon:
        return self.generated_icon(
            size,
            lambda painter, logical_size: draw_remmina_viewer_control_icon(
                painter, icon_key, logical_size
            ),
        )

    def build_remmina_profile_list_chrome(self) -> QFrame:
        chrome = gui_design_remmina_profile_list_chrome()
        route = gui_design_remmina_profile_viewer_route()
        filter_route = gui_design_remmina_profile_filter_route()
        transfer_route = gui_design_remmina_sftp_transfer_route()
        panel = QFrame()
        panel.setObjectName("remminaProfileListChrome")
        panel.setProperty("designPreset", "remmina")
        panel.setProperty("remminaProfileColumnKeys", [column.key for column in chrome.columns])
        panel.setProperty("remminaProfileRowKeys", [row.key for row in chrome.rows])
        panel.setProperty("remminaProfileViewerRouteKey", route.key)
        panel.setProperty("remminaProfileViewerRouteRole", route.route_role)
        panel.setProperty("remminaProfileViewerSelectedProfileKey", route.selected_profile_key)
        panel.setProperty("remminaProfileViewerSelectedProfileObject", route.selected_profile_object)
        panel.setProperty("remminaProfileViewerControlsObject", route.viewer_controls_object)
        panel.setProperty("remminaProfileViewerControlKey", route.viewer_control_key)
        panel.setProperty("remminaProfileViewerControlObject", route.viewer_control_object)
        panel.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
        panel.setProperty("remminaProfileViewerProtocol", route.protocol)
        panel.setProperty("remminaProfileViewerStatus", route.profile_status)
        panel.setProperty("remminaProfileViewerRenderSource", route.render_source)
        filter_route_properties = {
            "remminaProfileFilterRouteKey": filter_route.key,
            "remminaProfileFilterRouteRole": filter_route.route_role,
            "remminaProfileFilterRouteProfileListObject": filter_route.profile_list_object,
            "remminaProfileFilterRouteFilterObject": filter_route.filter_object,
            "remminaProfileFilterRouteSelectedProfileKey": filter_route.selected_profile_key,
            "remminaProfileFilterRouteSelectedProfileObject": filter_route.selected_profile_object,
            "remminaProfileFilterRouteMatchedProfile": filter_route.matched_profile_name,
            "remminaProfileFilterRouteMatchedProtocol": filter_route.matched_protocol,
            "remminaProfileFilterRouteMatchedStatus": filter_route.matched_status,
            "remminaProfileFilterRouteQuery": filter_route.expected_query,
            "remminaProfileFilterRoutePlaceholder": filter_route.expected_placeholder,
            "remminaProfileFilterRouteActiveTab": filter_route.active_tab_label,
            "remminaProfileFilterRouteSignal": filter_route.change_signal,
            "remminaProfileFilterRouteHandler": filter_route.handler_name,
            "remminaProfileFilterRouteRenderSource": filter_route.render_source,
        }
        for property_name, property_value in filter_route_properties.items():
            panel.setProperty(property_name, property_value)
        panel.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
        panel.setProperty("remminaSftpTransferRouteRole", transfer_route.route_role)
        panel.setProperty("remminaSftpTransferRouteProfileListObject", transfer_route.profile_list_object)
        panel.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
        panel.setProperty("remminaSftpTransferRouteSelectedProfile", transfer_route.selected_profile_name)
        panel.setProperty("remminaSftpTransferRouteProtocol", transfer_route.selected_profile_protocol)
        panel.setProperty("remminaSftpTransferRouteStatus", transfer_route.selected_profile_status)
        panel.setProperty("remminaSftpTransferRouteSelectedProfileObject", transfer_route.selected_profile_object)
        panel.setProperty("remminaSftpTransferRouteSelectedTreeLabel", transfer_route.selected_tree_label)
        panel.setProperty("remminaSftpTransferRouteToolbarActionKey", transfer_route.toolbar_action_key)
        panel.setProperty("remminaSftpTransferRouteToolbarActionLabel", transfer_route.toolbar_action_label)
        panel.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
        panel.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
        panel.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
        panel.setProperty("remminaSftpTransferRouteQueueLabel", transfer_route.transfer_queue_label)
        panel.setProperty("remminaSftpTransferRouteRenderSource", transfer_route.render_source)
        self.remmina_sftp_profile_panel = panel
        self.apply_remmina_sftp_transfer_action_route_properties(panel, transfer_route)
        panel.setProperty("remminaProfileStaticFilterX", chrome.static_filter_x)
        panel.setProperty("remminaProfileStaticFilterY", chrome.static_filter_y)
        panel.setProperty("remminaProfileStaticFilterHeight", chrome.static_filter_height)
        panel.setProperty("remminaProfileStaticHeaderY", chrome.static_header_y)
        panel.setProperty("remminaProfileStaticRowStartY", chrome.static_row_start_y)
        panel.setProperty("remminaProfileStaticRowHeight", chrome.static_row_height)
        panel.setProperty("remminaProfileStaticRowStep", chrome.static_row_step)
        panel.setProperty("remminaProfileStaticCellStartX", chrome.static_cell_start_x)
        panel.setProperty("remminaProfileStaticCellY", chrome.static_cell_y)
        panel.setProperty("remminaProfileStaticStatusY", chrome.static_status_y)
        panel.setProperty("remminaProfileLiveMaxHeight", chrome.live_max_height)
        panel.setProperty("remminaProfileLiveSpacing", chrome.live_spacing)
        panel.setProperty("remminaProfileLiveRowMinHeight", chrome.live_row_min_height)
        panel.setMaximumHeight(chrome.live_max_height)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(
            chrome.live_margin_left,
            chrome.live_margin_top,
            chrome.live_margin_right,
            chrome.live_margin_bottom,
        )
        layout.setSpacing(chrome.live_spacing)

        title_row = QHBoxLayout()
        title_row.setSpacing(chrome.live_title_spacing)
        title = QLabel(chrome.title)
        title.setObjectName("remminaProfileListTitle")
        title_row.addWidget(title)
        filter_input = QLineEdit()
        filter_input.setObjectName("remminaProfileFilter")
        filter_input.setPlaceholderText(chrome.filter_placeholder)
        filter_input.setReadOnly(False)
        filter_input.setProperty("remminaProfileFilterWidth", chrome.live_filter_width)
        for property_name, property_value in filter_route_properties.items():
            filter_input.setProperty(property_name, property_value)
        filter_input.setMinimumWidth(chrome.live_filter_width)
        filter_input.textChanged.connect(self.filter_remmina_profile_rows)
        self.remmina_profile_filter = filter_input
        title_row.addWidget(filter_input, 1)
        layout.addLayout(title_row)

        header = QHBoxLayout()
        header.setSpacing(chrome.live_header_spacing)
        compact_column_widths = {
            "name": 78,
            "protocol": 45,
            "server": 78,
        }
        for column in chrome.columns:
            label = QLabel(column.label)
            label.setObjectName("remminaProfileListColumn")
            label.setProperty("remminaProfileColumnKey", column.key)
            label.setProperty("remminaProfileColumnWidth", column.static_width)
            label.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
            compact_width = compact_column_widths[column.key]
            label.setProperty("remminaProfileColumnCompactMinWidth", compact_width)
            label.setMinimumWidth(compact_width)
            label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            header.addWidget(label, compact_width)
        layout.addLayout(header)

        for row in chrome.rows:
            row_frame = QFrame()
            row_frame.setObjectName("remminaProfileListRow")
            row_frame.setProperty("remminaProfileRowKey", row.key)
            row_frame.setProperty("remminaProfileName", row.name)
            row_frame.setProperty("remminaProfileProtocol", row.protocol)
            row_frame.setProperty("remminaProfileServer", row.server)
            row_frame.setProperty("remminaProfileStatus", row.status)
            row_frame.setProperty("selectedRow", "true" if row.selected else "false")
            row_frame.setProperty("remminaProfileFilterRouteKey", filter_route.key)
            row_frame.setProperty("remminaProfileFilterRouteRole", filter_route.route_role)
            row_frame.setProperty("remminaProfileFilterRouteQuery", filter_route.expected_query)
            row_frame.setProperty(
                "remminaProfileFilterRouteMatched",
                "true" if row.key == filter_route.selected_profile_key else "false",
            )
            row_frame.setProperty("remminaProfileFilterRouteRenderSource", filter_route.render_source)
            if row.key == route.selected_profile_key:
                row_frame.setProperty("remminaProfileViewerRouteKey", route.key)
                row_frame.setProperty("remminaProfileViewerRouteRole", route.route_role)
                row_frame.setProperty("remminaProfileViewerControlKey", route.viewer_control_key)
                row_frame.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                row_frame.setProperty("remminaProfileViewerProtocol", route.protocol)
                row_frame.setProperty("remminaProfileViewerStatus", route.profile_status)
                row_frame.setProperty(route.selected_row_property, "true" if row.selected else "false")
            if row.key == filter_route.selected_profile_key:
                row_frame.setProperty("remminaProfileFilterRouteSelectedProfileKey", filter_route.selected_profile_key)
                row_frame.setProperty("remminaProfileFilterRouteMatchedProfile", filter_route.matched_profile_name)
                row_frame.setProperty("remminaProfileFilterRouteMatchedProtocol", filter_route.matched_protocol)
                row_frame.setProperty("remminaProfileFilterRouteMatchedStatus", filter_route.matched_status)
                row_frame.setProperty("remminaProfileFilterRouteActiveTab", filter_route.active_tab_label)
            if row.key == transfer_route.selected_profile_key:
                row_frame.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
                row_frame.setProperty("remminaSftpTransferRouteRole", transfer_route.route_role)
                row_frame.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
                row_frame.setProperty("remminaSftpTransferRouteSelectedProfile", transfer_route.selected_profile_name)
                row_frame.setProperty("remminaSftpTransferRouteProtocol", transfer_route.selected_profile_protocol)
                row_frame.setProperty("remminaSftpTransferRouteStatus", transfer_route.selected_profile_status)
                row_frame.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
                row_frame.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
                row_frame.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
                row_frame.setProperty("remminaSftpTransferRouteQueueLabel", transfer_route.transfer_queue_label)
                row_frame.setProperty("remminaSftpTransferRouteRenderSource", transfer_route.render_source)
                self.remmina_sftp_profile_row = row_frame
                self.apply_remmina_sftp_transfer_action_route_properties(row_frame, transfer_route)
            row_frame.setProperty("remminaProfileStaticRowHeight", chrome.static_row_height)
            row_frame.setProperty("remminaProfileStaticRowStep", chrome.static_row_step)
            row_frame.setProperty("remminaProfileLiveRowMinHeight", chrome.live_row_min_height)
            row_frame.setMinimumHeight(chrome.live_row_min_height)
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(
                chrome.live_row_margin_left,
                chrome.live_row_margin_top,
                chrome.live_row_margin_right,
                chrome.live_row_margin_bottom,
            )
            row_layout.setSpacing(chrome.live_row_spacing)
            values = {
                "name": row.name,
                "protocol": row.protocol,
                "server": row.server,
                "status": row.status,
            }
            display_values = {
                **values,
                "server": row.server.replace(".example.invalid", ""),
                "status": {
                    "scale 100%": "100%",
                    "fit window": "fit",
                    "file sharing": "files",
                }.get(row.status, row.status),
            }
            for column in chrome.columns:
                full_text = f"{column.label}: {values[column.key]}"
                display_text = display_values[column.key]
                compact_width = compact_column_widths[column.key]
                cell = _literal_label(display_text)
                cell.setObjectName("remminaProfileListCell")
                cell.setProperty("remminaProfileRowKey", row.key)
                cell.setProperty("remminaProfileColumnKey", column.key)
                cell.setProperty("remminaProfileCellValue", values[column.key])
                cell.setProperty("remminaProfileCellFullText", full_text)
                cell.setProperty("remminaProfileCellDisplayText", display_text)
                cell.setProperty("remminaProfileColumnWidth", column.static_width)
                cell.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
                cell.setProperty("remminaProfileColumnCompactMinWidth", compact_width)
                if row.key == route.selected_profile_key:
                    cell.setProperty("remminaProfileViewerRouteKey", route.key)
                    cell.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                    cell.setProperty("remminaProfileViewerStatus", route.profile_status)
                if row.key == transfer_route.selected_profile_key:
                    cell.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
                    cell.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
                    cell.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
                    cell.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
                    cell.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
                cell.setMinimumWidth(compact_width)
                cell.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                cell.setAccessibleName(full_text)
                cell.setToolTip(_safe_tooltip_html(full_text))
                row_layout.addWidget(cell, compact_width)
            status_full_text = f"Status: {row.status}"
            status_display_text = display_values["status"]
            status_compact_width = 47
            status = _literal_label(status_display_text)
            status.setObjectName("remminaProfileListCell")
            status.setProperty("remminaProfileRowKey", row.key)
            status.setProperty("remminaProfileColumnKey", "status")
            status.setProperty("remminaProfileCellValue", row.status)
            status.setProperty("remminaProfileCellFullText", status_full_text)
            status.setProperty("remminaProfileCellDisplayText", status_display_text)
            status.setProperty(
                "remminaProfileColumnCompactMinWidth",
                status_compact_width,
            )
            status.setProperty("remminaProfileStaticStatusY", chrome.static_status_y)
            if row.key == route.selected_profile_key:
                status.setProperty("remminaProfileViewerRouteKey", route.key)
                status.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                status.setProperty("remminaProfileViewerStatus", route.profile_status)
            status.setMinimumWidth(status_compact_width)
            status.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            status.setAccessibleName(status_full_text)
            status.setToolTip(_safe_tooltip_html(status_full_text))
            row_layout.addWidget(status, status_compact_width)
            layout.addWidget(row_frame)
        return panel
