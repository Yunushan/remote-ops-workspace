from __future__ import annotations

import re
from abc import abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import (
    QPoint,
    QSize,
    Qt,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .gui_designs import (
    gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_terminal_transcript_row_geometry,
)
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value, _safe_tooltip_html
from .moba_connected import (
    MobaConnectedSessionState,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
    moba_telemetry_cells,
)

if TYPE_CHECKING:
    from .gui_connected import ConnectedGuiServices

    class ConnectedSessionPanel(QWidget):
        state: MobaConnectedSessionState
        moba_connected_state: MobaConnectedSessionState
        terminal_pane: TerminalPane
        terminal_splitter: QSplitter

        @abstractmethod
        def __init__(
            self, state: MobaConnectedSessionState, terminal_pane: TerminalPane,
        ) -> None: ...
        @abstractmethod
        def add_terminal_split(self, pane: TerminalPane, orientation: Qt.Orientation) -> QSplitter: ...

        @staticmethod
        def telemetry_label_text(label: QLabel, cell, available_width: int) -> str: ...
else:
    ConnectedSessionPanel = QWidget


def create_connected_terminal_class(services: ConnectedGuiServices) -> type[ConnectedSessionPanel]:
    """Build the terminal panel type for one window's services."""
    _application_clipboard = services.application_clipboard
    _literal_label = services.literal_label

    class MobaConnectedSessionPanel(ConnectedSessionPanel):
        def __init__(self, state: MobaConnectedSessionState, terminal_pane: TerminalPane) -> None:
            QWidget.__init__(self)
            self.setObjectName("mobaConnectedSession")
            self.setMinimumSize(0, 0)
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self.state = state
            self.moba_connected_state = state
            self.terminal_pane = terminal_pane
            self.apply_connected_session_route_properties(self)
            self.apply_connected_identity_route_properties(self)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            root.addWidget(self.build_terminal_area(), 1)
            root.addWidget(self.build_telemetry_bar())
            self._connected_session_layout: QVBoxLayout = root

        def apply_connected_session_route_properties(self, widget) -> None:
            route = moba_connected_session_route(self.state)
            properties = {
                "mobaConnectedRouteKey": route.key,
                "mobaConnectedRouteRole": route.route_role,
                "mobaConnectedRouteActiveTabKey": route.active_tab_key,
                "mobaConnectedRouteActiveTabLabel": route.active_tab_label,
                "mobaConnectedRouteReferenceTabLabel": route.reference_tab_label,
                "mobaConnectedRouteActiveTabObject": route.active_tab_object,
                "mobaConnectedRouteConnectedPanelObject": route.connected_panel_object,
                "mobaConnectedRouteLeftDockObject": route.left_dock_object,
                "mobaConnectedRouteSftpBrowserObject": route.sftp_browser_object,
                "mobaConnectedRouteSftpPathObject": route.sftp_path_object,
                "mobaConnectedRouteSftpTableObject": route.sftp_table_object,
                "mobaConnectedRouteSshBannerObject": route.ssh_banner_object,
                "mobaConnectedRouteTerminalAreaObject": route.terminal_area_object,
                "mobaConnectedRouteTerminalOutputObject": route.terminal_output_object,
                "mobaConnectedRouteTelemetryBarObject": route.telemetry_bar_object,
                "mobaConnectedRouteTelemetryIdentityCellKey": route.telemetry_identity_cell_key,
                route.target_property: route.target,
                route.remote_path_property: route.remote_path,
                "mobaConnectedRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_identity_route_properties(self, widget) -> None:
            route = moba_connected_session_identity_route(self.state)
            properties = {
                "mobaConnectedIdentityRouteKey": route.key,
                "mobaConnectedIdentityRouteRole": route.route_role,
                "mobaConnectedIdentityWindowTitle": route.window_title,
                "mobaConnectedIdentityActiveTabLabel": route.active_tab_label,
                "mobaConnectedIdentityReferenceTabLabel": route.reference_tab_label,
                "mobaConnectedIdentityBannerTarget": route.banner_target,
                "mobaConnectedIdentityWebConsoleLine": route.web_console_line,
                "mobaConnectedIdentityTerminalPrompt": route.terminal_prompt,
                "mobaConnectedIdentityTelemetryTarget": route.telemetry_target,
                "mobaConnectedIdentityTargetEndpoint": route.target_endpoint,
                "mobaConnectedIdentityRemotePath": route.remote_path,
                "mobaConnectedIdentityRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_sftp_terminal_folder_route_properties(self, widget) -> None:
            route = moba_sftp_terminal_folder_route(self.state)
            properties = {
                "mobaSftpTerminalFolderRouteKey": route.key,
                "mobaSftpTerminalFolderRouteRole": route.route_role,
                "mobaSftpTerminalFolderRouteTerminalAreaObject": route.terminal_area_object,
                "mobaSftpTerminalFolderRouteTerminalOutputObject": route.terminal_output_object,
                "mobaSftpTerminalFolderRouteSourceControlObject": route.source_control_object,
                "mobaSftpTerminalFolderRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpTerminalFolderRouteTargetPathObject": route.target_path_object,
                "mobaSftpTerminalFolderRouteTargetTableObject": route.target_table_object,
                "mobaSftpTerminalFolderRouteParentRowLabel": route.parent_row_label,
                "mobaSftpTerminalFolderRouteSelectedRowKind": route.selected_row_kind,
                "mobaSftpTerminalFolderRoutePath": route.remote_path,
                "mobaSftpTerminalFolderRoutePlan": route.list_command,
                "mobaSftpTerminalFolderRouteEnabled": route.follow_enabled,
                "mobaSftpTerminalFolderRouteRowRouteProperty": route.row_route_property,
                "mobaSftpTerminalFolderRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def build_terminal_area(self) -> QWidget:
            area = QWidget()
            area.setObjectName("mobaTerminalArea")
            area.setMinimumSize(0, 0)
            area.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self.apply_connected_session_route_properties(area)
            self.apply_sftp_terminal_folder_route_properties(area)
            area.setProperty("mobaFixedBannerVisible", False)
            area.setProperty("mobaRightUtilityRailVisible", False)
            area.setProperty("mobaRightUtilityRoutesRetainedInMenu", True)
            layout = QHBoxLayout(area)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            terminal_stack = QWidget()
            terminal_stack.setObjectName("mobaTerminalStack")
            terminal_stack.setMinimumSize(0, 0)
            terminal_stack.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            stack_layout = QVBoxLayout(terminal_stack)
            stack_layout.setContentsMargins(0, 0, 0, 0)
            stack_layout.setSpacing(0)
            self.apply_terminal_transcript_evidence()
            self.apply_moba_plain_terminal_mode()
            self.terminal_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.terminal_splitter.setObjectName("mobaTerminalSplitter")
            self.terminal_splitter.setMinimumSize(0, 0)
            self.terminal_splitter.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            self.terminal_splitter.setChildrenCollapsible(False)
            self.terminal_splitter.addWidget(self.terminal_pane)
            self.terminal_splitter.setCollapsible(0, False)
            self.terminal_splitter.setStretchFactor(0, 1)
            stack_layout.addWidget(self.terminal_splitter, 1)
            layout.addWidget(terminal_stack, 1)
            return area

        def add_terminal_split(
            self,
            pane: TerminalPane,
            orientation: Qt.Orientation,
        ) -> QSplitter:
            self.apply_terminal_transcript_evidence(pane)
            self.apply_moba_plain_terminal_mode(pane)
            self.terminal_splitter.setOrientation(orientation)
            self.terminal_splitter.addWidget(pane)
            self.terminal_splitter.setChildrenCollapsible(False)
            for index in range(self.terminal_splitter.count()):
                self.terminal_splitter.setCollapsible(index, False)
                self.terminal_splitter.setStretchFactor(index, 1)
            self.terminal_splitter.setSizes([1000] * self.terminal_splitter.count())
            return self.terminal_splitter

        def apply_terminal_transcript_evidence(self, pane: TerminalPane | None = None) -> None:
            pane = pane or self.terminal_pane
            pane.set_launch_command_echo_visible(False)
            pane.set_startup_preamble(self.moba_startup_preamble(pane))
            pane.output.setProperty("mobaTerminalTranscriptKeys", [])
            pane.output.setProperty("mobaTerminalTranscriptTones", [])
            pane.output.setProperty("mobaTerminalTranscriptPreviewOnly", False)
            pane.output.setProperty("mobaTerminalTranscriptInjected", False)
            pane.output.setProperty("mobaSyntheticConnectedTranscriptSuppressed", True)
            pane.output.setProperty("mobaFixedBannerVisible", False)
            self.apply_connected_session_route_properties(pane.output)
            self.apply_connected_identity_route_properties(pane.output)
            self.apply_sftp_terminal_folder_route_properties(pane.output)
            pane.output.setProperty("mobaConnectedIdentityWebConsoleLine", "")
            pane.output.setProperty("mobaConnectedIdentityTerminalPrompt", "")

        def moba_startup_preamble(self, pane: TerminalPane | None = None) -> str:
            pane = pane or self.terminal_pane
            command = set(pane.plan.command)
            compression = "requested" if "-C" in command else "not requested"
            x11 = (
                "requested"
                if any(flag in command for flag in {"-X", "-Y"})
                else "not requested"
            )
            return "\n".join(
                [
                    "* Remote Ops Workspace *",
                    "  (SSH client, SFTP browser, and remote tools)",
                    f"> SSH session target: {self.state.target}",
                    "* Direct SSH: requested",
                    f"* SSH compression: {compression}",
                    "* SSH browser: requested",
                    f"* X11 forwarding: {x11}",
                    "> Waiting for authentication and server output.",
                ]
            )

        def apply_moba_plain_terminal_mode(self, pane: TerminalPane | None = None) -> None:
            pane = pane or self.terminal_pane
            geometry = gui_design_moba_terminal_transcript_row_geometry()
            native_pty = bool(getattr(pane.process, "is_pty", False))
            process_property = getattr(pane.process, "property", lambda _name: None)
            pipe_fallback = bool(
                process_property("terminalOpenSshPipeFallback")
            ) or not native_pty
            self.apply_connected_session_route_properties(pane)
            self.apply_connected_identity_route_properties(pane)
            self.apply_sftp_terminal_folder_route_properties(pane)
            pane.setProperty("mobaPlainTerminalMode", True)
            pane.setProperty("mobaTerminalHeaderVisible", False)
            pane.setProperty("mobaTerminalCommandRowVisible", False)
            pane.setProperty("mobaTerminalInputVisible", pipe_fallback)
            pane.setProperty("mobaTerminalDirectInput", True)
            pane.setProperty(
                "mobaTerminalInputMode",
                "explicit-pipe-line-fallback"
                if pipe_fallback
                else "native-pty-direct",
            )
            pane.header.setVisible(False)
            pane.command_row.setVisible(False)
            pane.input.setVisible(pipe_fallback)
            pane.input.setPlaceholderText(
                "Type a command and press Enter (non-PTY fallback)"
            )
            pane.input.setToolTip(
                "This field is shown only because this process is using an explicit "
                "non-PTY pipe fallback."
            )
            pane.input.setAccessibleName("Terminal command input")
            pane.output.setProperty("mobaPlainTerminalMode", True)
            pane.output.setProperty("mobaTerminalDirectInput", True)
            pane.output.setProperty("mobaTerminalLineInputFallback", pipe_fallback)
            pane.output.setProperty("mobaTerminalNativePty", native_pty)
            pane.output.setToolTip(
                "Click the terminal and type. Right-click or middle-click pastes; "
                "Shift+Right-click opens copy, paste, save, telemetry, and session actions."
            )
            pane.output_context_menu_builder = self.build_moba_terminal_context_menu
            pane.output.setProperty("mobaTerminalTranscriptGeometryKeys", [row.key for row in geometry])
            pane.output.setProperty("mobaTerminalTranscriptX", [row.static_x for row in geometry])
            pane.output.setProperty("mobaTerminalTranscriptY", [row.static_y for row in geometry])
            pane.output.setProperty("mobaTerminalTranscriptRowHeight", [row.row_height for row in geometry])
            pane.output.setProperty("mobaTerminalTranscriptFontSize", [row.font_size for row in geometry])

        def build_moba_terminal_context_menu(self, pane: TerminalPane) -> QMenu:
            menu = QMenu(pane.output)
            menu.setObjectName("mobaTerminalContextMenu")
            selection = bool(pane.output.textCursor().selectedText())
            copy_action = _required_gui_value(
                menu.addAction("Copy"),
                "terminal context copy action",
            )
            copy_action.setEnabled(selection)
            copy_action.triggered.connect(pane.copy_terminal_selection)
            save_action = _required_gui_value(
                menu.addAction("Save to file"),
                "terminal context save action",
            )
            save_action.setEnabled(bool(pane._rendered_terminal_text))
            save_action.triggered.connect(
                lambda _checked=False, active_pane=pane: self.save_terminal_to_file(
                    active_pane
                )
            )
            menu.addSeparator()
            cells = {
                cell.key: cell
                for cell in moba_telemetry_cells(self.state)
            }
            for key, frame in getattr(self, "telemetry_cell_frames", {}).items():
                label = (
                    "host"
                    if key == "target"
                    else (
                        cells[key].label.lower()
                        if key in cells
                        else key.replace("-", " ")
                    )
                )
                action = _required_gui_value(
                    menu.addAction(f"Display {label} information"),
                    f"terminal telemetry action for {key}",
                )
                action.setCheckable(True)
                action.setChecked(frame.isVisible())
                action.setProperty("mobaTelemetryVisibilityKey", key)
                action.toggled.connect(
                    lambda checked, cell_key=key: self.set_telemetry_cell_visible(
                        cell_key,
                        checked,
                    )
                )

            menu.addSeparator()
            paste_action = _required_gui_value(
                menu.addAction("Paste"),
                "terminal context paste action",
            )
            paste_action.setEnabled(bool(_application_clipboard().text()))
            paste_action.triggered.connect(pane.paste_to_terminal)
            select_action = _required_gui_value(
                menu.addAction("Select all"),
                "terminal context select-all action",
            )
            select_action.triggered.connect(pane.output.selectAll)

            dock = self.active_moba_sftp_dock()
            if dock is not None:
                monitoring_menu = _required_gui_value(
                    menu.addMenu("Monitoring"),
                    "terminal monitoring menu",
                )
                monitoring_menu.setObjectName("mobaMonitoringContextMenu")
                monitoring_control = dock.monitoring_control_widgets.get(
                    "remote-monitoring"
                )
                monitoring_action = _required_gui_value(
                    monitoring_menu.addAction("Remote monitoring enabled"),
                    "remote monitoring toggle action",
                )
                monitoring_action.setCheckable(True)
                monitoring_action.setChecked(
                    bool(
                        monitoring_control is not None
                        and monitoring_control.isChecked()
                    )
                )
                if monitoring_control is not None:
                    monitoring_action.toggled.connect(
                        monitoring_control.setChecked
                    )
                follow_control = dock.monitoring_control_widgets.get(
                    "follow-terminal-folder"
                )
                follow_action = _required_gui_value(
                    monitoring_menu.addAction("Follow terminal folder"),
                    "follow terminal folder action",
                )
                follow_action.setCheckable(True)
                follow_action.setChecked(
                    bool(follow_control is not None and follow_control.isChecked())
                )
                if follow_control is not None:
                    follow_action.toggled.connect(follow_control.setChecked)

            tools_menu = _required_gui_value(
                menu.addMenu("Session tools"),
                "terminal session tools menu",
            )
            session_route = gui_design_moba_session_edge_action_route()
            session_handlers = dict(
                zip(
                    session_route.action_keys,
                    session_route.action_handlers,
                    strict=True,
                )
            )
            for session_action_spec in gui_design_moba_session_edge_actions():
                action = _required_gui_value(
                    tools_menu.addAction(session_action_spec.label),
                    f"session edge action for {session_action_spec.key}",
                )
                action.setProperty("mobaSessionEdgeKey", session_action_spec.key)
                action.triggered.connect(
                    lambda _checked=False, handler=session_handlers[
                        session_action_spec.key
                    ]: self.dispatch_moba_workspace_action(handler)
                )
            utility_route = gui_design_moba_right_utility_action_route()
            utility_handlers = dict(
                zip(
                    utility_route.action_keys,
                    utility_route.action_handlers,
                    strict=True,
                )
            )
            for utility_action_spec in gui_design_moba_right_utility_actions():
                action = _required_gui_value(
                    tools_menu.addAction(utility_action_spec.label),
                    f"right utility action for {utility_action_spec.key}",
                )
                action.setProperty("mobaRightUtilityKey", utility_action_spec.key)
                action.triggered.connect(
                    lambda _checked=False, handler=utility_handlers[
                        utility_action_spec.key
                    ]: self.dispatch_moba_workspace_action(handler)
                )

            menu.addSeparator()
            restart_action = _required_gui_value(
                menu.addAction("Restart session"),
                "terminal restart-session action",
            )
            restart_action.setEnabled(bool(pane.plan.command))
            restart_action.triggered.connect(pane.restart)
            stop_action = _required_gui_value(
                menu.addAction("Stop session"),
                "terminal stop-session action",
            )
            stop_action.setEnabled(pane.is_running())
            stop_action.triggered.connect(pane.request_stop)
            return menu

        def active_moba_sftp_dock(self):
            dock = getattr(self.window(), "moba_connected_dock", None)
            if dock is None:
                return None
            if dock.state.profile_name != self.state.profile_name:
                return None
            return dock

        def dispatch_moba_workspace_action(self, handler_name: str) -> None:
            handler = getattr(self.window(), handler_name, None)
            if callable(handler):
                handler()
                return
            fallback = getattr(self, handler_name, None)
            if callable(fallback):
                fallback()

        def save_terminal_to_file(self, pane: TerminalPane) -> None:
            stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", pane.plan.title).strip("-")
            filename, _selected_filter = QFileDialog.getSaveFileName(
                self,
                "Save terminal transcript",
                f"{stem or 'terminal'}.txt",
                "Text files (*.txt);;All files (*)",
            )
            if not filename:
                return
            try:
                Path(filename).write_text(
                    pane._rendered_terminal_text,
                    encoding="utf-8",
                )
            except OSError as exc:
                self.setProperty("mobaTerminalSaveError", str(exc))
                status_bar = getattr(self.window(), "statusBar", lambda: None)()
                if status_bar is not None:
                    status_bar.showMessage(f"Could not save terminal output: {exc}")
                return
            self.setProperty("mobaTerminalSavedPath", filename)
            status_bar = getattr(self.window(), "statusBar", lambda: None)()
            if status_bar is not None:
                status_bar.showMessage(f"Saved terminal output to {filename}", 5000)

        def set_telemetry_cell_visible(self, key: str, visible: bool) -> None:
            frame = getattr(self, "telemetry_cell_frames", {}).get(key)
            if frame is None:
                return
            frame.setVisible(bool(visible))
            frame.setProperty("mobaTelemetryUserVisible", bool(visible))
            visible_keys = [
                cell_key
                for cell_key, cell_frame in self.telemetry_cell_frames.items()
                if cell_frame.isVisible()
            ]
            self.telemetry_bar.setProperty(
                "mobaTelemetryVisibleCellKeys",
                visible_keys,
            )
            self.telemetry_bar.setProperty(
                "mobaTelemetryVisibilityChangedKey",
                key,
            )

        def show_moba_terminal_context_menu(
            self,
            source: QWidget,
            position: QPoint,
        ) -> None:
            pane = self.moba_terminal_context_pane(source)
            menu = self.build_moba_terminal_context_menu(pane)
            menu.exec(source.mapToGlobal(position))
            menu.deleteLater()

        def moba_terminal_context_pane(self, source: QWidget) -> TerminalPane:
            """Route shared chrome actions to the split that originated or owns focus."""

            candidate: QWidget | None = source
            while candidate is not None:
                if isinstance(candidate, TerminalPane):
                    return candidate
                candidate = candidate.parentWidget()
            main_window = services.main_window(self.window())
            active = (
                main_window.active_terminal_pane()
                if main_window is not None
                else None
            )
            if (
                isinstance(active, TerminalPane)
                and hasattr(self, "terminal_splitter")
                and self.terminal_splitter.indexOf(active) >= 0
            ):
                return active
            return self.terminal_pane

        def install_moba_terminal_context_menu(self, widget: QWidget) -> None:
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(
                lambda position, source=widget: self.show_moba_terminal_context_menu(
                    source,
                    position,
                )
            )

        def build_right_utility_rail(self) -> QFrame:
            chrome = gui_design_moba_right_utility_rail_chrome()
            route = gui_design_moba_right_utility_action_route()
            rail = QFrame()
            rail.setObjectName("mobaRightUtilityRail")
            rail.setProperty("mobaRightUtilityRouteKey", route.key)
            rail.setProperty("mobaRightUtilityRouteRole", route.route_role)
            rail.setProperty("mobaRightUtilityRouteRailObject", route.rail_object)
            rail.setProperty("mobaRightUtilityRouteActionObject", route.action_object)
            rail.setProperty(route.action_keys_property, list(route.action_keys))
            rail.setProperty("mobaRightUtilityRouteRenderSource", route.render_source)
            rail.setProperty("mobaRightUtilityRailStaticWidth", chrome.static_width)
            rail.setProperty("mobaRightUtilityRailLiveWidth", chrome.live_width)
            rail.setProperty("mobaRightUtilityRailMargins", [chrome.margin_left, chrome.margin_top, chrome.margin_right, chrome.margin_bottom])
            rail.setProperty("mobaRightUtilityRailActionSpacing", chrome.action_spacing)
            rail.setProperty("mobaRightUtilityRailSessionEdgeTopY", chrome.session_edge_top_y)
            rail.setProperty("mobaRightUtilityRailSessionEdgeHeight", chrome.session_edge_height)
            rail.setProperty("mobaRightUtilityRailSessionEdgeIconX", chrome.session_edge_icon_x)
            rail.setProperty("mobaRightUtilityRailSessionEdgeIconSize", chrome.session_edge_icon_size)
            rail.setFixedWidth(chrome.live_width)
            layout = QVBoxLayout(rail)
            layout.setContentsMargins(chrome.margin_left, chrome.margin_top, chrome.margin_right, chrome.margin_bottom)
            layout.setSpacing(chrome.action_spacing)
            layout.addWidget(self.build_session_edge_controls())
            route_handlers = dict(zip(route.action_keys, route.action_handlers, strict=True))
            for action in gui_design_moba_right_utility_actions():
                button = QToolButton()
                button.setObjectName("mobaRightUtilityAction")
                button.setProperty("mobaRightUtilityKey", action.key)
                button.setProperty("mobaRightUtilityIconKey", action.icon_key)
                button.setProperty("mobaRightUtilityRouteKey", route.key)
                button.setProperty("mobaRightUtilityRouteRole", route.route_role)
                button.setProperty(route.action_key_property, action.key)
                button.setProperty(route.action_label_property, action.label)
                button.setProperty(route.action_object_property, route.action_object)
                button.setProperty(route.icon_key_property, action.icon_key)
                button.setProperty("mobaRightUtilityRouteHandler", route_handlers[action.key])
                button.setProperty(route.action_keys_property, list(route.action_keys))
                button.setProperty("mobaRightUtilityRouteRenderSource", route.render_source)
                button.setProperty("mobaRightUtilityStaticX", action.static_x)
                button.setProperty("mobaRightUtilityStaticY", action.static_y)
                button.setProperty("mobaRightUtilityStaticSize", action.static_size)
                button.setProperty("mobaRightUtilityLiveIconSize", action.live_icon_size)
                button.setProperty("mobaRightUtilityButtonSize", action.button_size)
                button.setProperty("mobaRightUtilityRenderSource", action.render_source)
                button.setToolTip(action.tooltip)
                button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
                button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
                button.setFixedSize(QSize(action.button_size, action.button_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.clicked.connect(getattr(self, route_handlers[action.key]))
                layout.addWidget(button)
            layout.addStretch(1)
            return rail

        def build_session_edge_controls(self) -> QFrame:
            chrome = gui_design_moba_right_utility_rail_chrome()
            route = gui_design_moba_session_edge_action_route()
            controls = QFrame()
            controls.setObjectName("mobaSessionEdgeControls")
            actions = gui_design_moba_session_edge_actions()
            controls.setProperty("mobaSessionEdgeRouteKey", route.key)
            controls.setProperty("mobaSessionEdgeRouteRole", route.route_role)
            controls.setProperty("mobaSessionEdgeRouteControlsObject", route.controls_object)
            controls.setProperty("mobaSessionEdgeRouteActionObject", route.action_object)
            controls.setProperty("mobaSessionEdgeRoutePlacement", route.placement)
            controls.setProperty(route.action_keys_property, list(route.action_keys))
            controls.setProperty("mobaSessionEdgeRouteRenderSource", route.render_source)
            controls.setProperty("mobaSessionEdgeActionKeys", [action.key for action in actions])
            controls.setProperty("mobaSessionEdgePlacement", "tab-strip-overlay")
            controls.setProperty("mobaSessionEdgeTopY", chrome.session_edge_top_y)
            controls.setProperty("mobaSessionEdgeStaticHeight", chrome.session_edge_height)
            controls.setProperty("mobaSessionEdgeIconX", chrome.session_edge_icon_x)
            controls.setProperty("mobaSessionEdgeIconSize", chrome.session_edge_icon_size)
            controls.setProperty(
                "mobaSessionEdgeRelativeY",
                [action.relative_y(chrome.session_edge_top_y) for action in actions],
            )
            controls.setFixedWidth(chrome.live_width)
            controls.setFixedHeight(chrome.session_edge_height)
            route_handlers = dict(zip(route.action_keys, route.action_handlers, strict=True))
            for action in actions:
                relative_y = action.relative_y(chrome.session_edge_top_y)
                button = QToolButton(controls)
                button.setObjectName("mobaSessionEdgeAction")
                button.setProperty("mobaSessionEdgeKey", action.key)
                button.setProperty("mobaSessionEdgeIconKey", action.icon_key)
                button.setProperty("mobaSessionEdgeRouteKey", route.key)
                button.setProperty("mobaSessionEdgeRouteRole", route.route_role)
                button.setProperty(route.action_key_property, action.key)
                button.setProperty(route.action_label_property, action.label)
                button.setProperty(route.action_object_property, route.action_object)
                button.setProperty(route.icon_key_property, action.icon_key)
                button.setProperty("mobaSessionEdgeRouteHandler", route_handlers[action.key])
                button.setProperty(route.action_keys_property, list(route.action_keys))
                button.setProperty("mobaSessionEdgeRouteRenderSource", route.render_source)
                button.setProperty("mobaSessionEdgeStaticY", action.static_y)
                button.setProperty("mobaSessionEdgeRelativeY", relative_y)
                button.setProperty("mobaSessionEdgeIconX", chrome.session_edge_icon_x)
                button.setProperty("mobaSessionEdgeIconSize", chrome.session_edge_icon_size)
                button.setProperty("mobaSessionEdgeStaticSize", action.static_size)
                button.setProperty("mobaSessionEdgeLiveIconSize", action.live_icon_size)
                button.setProperty("mobaSessionEdgeButtonSize", action.button_size)
                button.setProperty("mobaSessionEdgeRenderSource", action.render_source)
                button.setToolTip(action.tooltip)
                button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
                button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
                button.setFixedSize(QSize(action.button_size, action.button_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setGeometry(
                    chrome.session_edge_icon_x,
                    relative_y,
                    action.button_size,
                    action.button_size,
                )
                button.clicked.connect(getattr(self, route_handlers[action.key]))
            return controls

        def show_moba_session_attachment(self, *_args) -> None:
            self.record_moba_panel_action("session-edge", "attachment")

        def show_moba_session_settings(self, *_args) -> None:
            self.record_moba_panel_action("session-edge", "settings")

        def show_moba_clipboard_hints(self, *_args) -> None:
            self.record_moba_panel_action("right-utility", "clipboard")

        def show_moba_terminal_settings(self, *_args) -> None:
            self.record_moba_panel_action("right-utility", "settings")

        def show_moba_tools_status(self, *_args) -> None:
            self.record_moba_panel_action("right-utility", "tools")

        def record_moba_panel_action(self, route_role: str, action_key: str) -> None:
            self.setProperty("mobaConnectedLastActionRouteRole", route_role)
            self.setProperty("mobaConnectedLastActionKey", action_key)
            status_bar = getattr(self.window(), "statusBar", lambda: None)()
            if status_bar is not None:
                status_bar.showMessage(
                    f"{action_key.replace('-', ' ').title()} selected",
                    3000,
                )

        def moba_utility_icon(self, icon_key: str, fill: str) -> QIcon:
            scale = max(1.0, float(self.devicePixelRatioF()))
            pixel_size = max(1, int(round(20 * scale)))
            pixmap = QPixmap(pixel_size, pixel_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.scale(scale, scale)
            color = QColor(fill)
            try:
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if icon_key == "clip":
                    painter.drawArc(5, 3, 10, 13, 35 * 16, 280 * 16)
                    painter.drawArc(8, 5, 6, 10, 35 * 16, 280 * 16)
                    painter.drawLine(9, 14, 6, 11)
                elif icon_key == "spark":
                    painter.drawLine(10, 3, 10, 17)
                    painter.drawLine(3, 10, 17, 10)
                    painter.drawLine(5, 5, 15, 15)
                    painter.drawLine(15, 5, 5, 15)
                elif icon_key == "gear":
                    painter.drawEllipse(6, 6, 8, 8)
                    painter.drawEllipse(8, 8, 4, 4)
                    for start, end in (
                        ((10, 2), (10, 6)),
                        ((10, 14), (10, 18)),
                        ((2, 10), (6, 10)),
                        ((14, 10), (18, 10)),
                        ((4, 4), (7, 7)),
                        ((16, 4), (13, 7)),
                        ((4, 16), (7, 13)),
                        ((16, 16), (13, 13)),
                    ):
                        painter.drawLine(*start, *end)
                elif icon_key == "arrow-left":
                    painter.drawLine(14, 5, 7, 10)
                    painter.drawLine(7, 10, 14, 15)
                    painter.drawLine(7, 10, 17, 10)
                elif icon_key == "arrow-right":
                    painter.drawLine(6, 5, 13, 10)
                    painter.drawLine(13, 10, 6, 15)
                    painter.drawLine(3, 10, 13, 10)
                elif icon_key == "close":
                    painter.drawLine(6, 6, 14, 14)
                    painter.drawLine(14, 6, 6, 14)
                else:
                    painter.drawRect(4, 4, 12, 12)
            finally:
                painter.end()
            pixmap.setDevicePixelRatio(scale)
            return QIcon(pixmap)

        def build_ssh_banner_slot(self) -> QFrame:
            chrome = gui_design_moba_ssh_banner_chrome()
            slot = QFrame()
            slot.setObjectName("mobaSshBannerSlot")
            self.apply_connected_session_route_properties(slot)
            slot.setProperty("mobaBannerLeftOffset", chrome.static_left_offset)
            slot.setProperty("mobaBannerTopOffset", chrome.static_top_offset)
            slot.setProperty("mobaBannerTerminalGap", chrome.terminal_gap)
            slot.setFixedHeight(chrome.static_top_offset + chrome.static_height + chrome.terminal_gap)
            banner = self.build_ssh_banner()
            banner.setParent(slot)
            banner.setGeometry(
                chrome.static_left_offset,
                chrome.static_top_offset,
                chrome.static_width,
                chrome.static_height,
            )
            return slot

        def apply_ssh_banner_row_geometry(self, label: QLabel, key: str) -> None:
            geometry = gui_design_moba_ssh_banner_row_geometry_for(key)
            label.setProperty("mobaSshBannerRowKey", geometry.key)
            label.setProperty("mobaSshBannerRowX", geometry.static_x)
            label.setProperty("mobaSshBannerRowY", geometry.static_y)
            label.setProperty("mobaSshBannerRowWidth", geometry.static_width)
            label.setProperty("mobaSshBannerRowHeight", geometry.static_height)
            label.setProperty("mobaSshBannerRowCentered", geometry.centered)
            label.setGeometry(
                geometry.static_x,
                geometry.static_y,
                geometry.static_width,
                geometry.static_height,
            )
            if geometry.centered:
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        @staticmethod
        def apply_ssh_banner_font(
            label: QLabel,
            *,
            pixel_size: int,
            bold: bool = False,
        ) -> None:
            font = QFont("Cascadia Mono")
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPixelSize(pixel_size)
            font.setBold(bold)
            font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            label.setFont(font)
            label.setProperty("mobaBannerTextHinting", "PreferFullHinting")
            label.setProperty("mobaBannerTextPixelSize", pixel_size)

        def build_ssh_banner(self) -> QFrame:
            chrome = gui_design_moba_ssh_banner_chrome()
            banner = QFrame()
            banner.setObjectName("mobaSshBanner")
            self.apply_connected_session_route_properties(banner)
            self.apply_connected_identity_route_properties(banner)
            banner.setProperty("mobaBannerTitle", chrome.title)
            banner.setProperty("mobaBannerSubtitle", chrome.subtitle)
            banner.setProperty("mobaBannerTargetIntro", chrome.target_intro)
            banner.setProperty("mobaBannerCapabilityLabelWidth", chrome.capability_label_width)
            banner.setProperty("mobaBannerFooterPrefix", chrome.footer_prefix)
            banner.setProperty("mobaBannerCapabilityKeys", [row.key for row in self.state.banner.capability_rows()])
            banner.setProperty("mobaBannerFooterLinks", list(self.state.banner.footer_links()))
            banner.setProperty("mobaBannerWidth", chrome.static_width)
            banner.setProperty("mobaBannerHeight", chrome.static_height)
            banner.setProperty("mobaBannerLeftOffset", chrome.static_left_offset)
            banner.setProperty("mobaBannerTopOffset", chrome.static_top_offset)
            banner.setProperty("mobaBannerTerminalGap", chrome.terminal_gap)
            banner.setProperty(
                "mobaSshBannerRowGeometryKeys",
                [geometry.key for geometry in gui_design_moba_ssh_banner_row_geometry()],
            )
            banner.setFixedSize(QSize(chrome.static_width, chrome.static_height))
            title = _literal_label(f"{chrome.heading_prefix}{chrome.title}{chrome.heading_suffix}")
            title.setParent(banner)
            title.setObjectName("mobaSshBannerTitle")
            self.apply_ssh_banner_font(title, pixel_size=14, bold=True)
            self.apply_ssh_banner_row_geometry(title, "title")
            subtitle = _literal_label(chrome.subtitle)
            subtitle.setParent(banner)
            subtitle.setObjectName("mobaSshBannerSubtitle")
            self.apply_ssh_banner_font(subtitle, pixel_size=12)
            self.apply_ssh_banner_row_geometry(subtitle, "subtitle")
            target = _literal_label(f"> {chrome.target_intro} {self.state.banner.title}")
            target.setParent(banner)
            target.setObjectName("mobaSshBannerTargetLine")
            self.apply_ssh_banner_font(target, pixel_size=12)
            self.apply_connected_identity_route_properties(target)
            target.setProperty("mobaSshBannerTarget", self.state.banner.title)
            target.setProperty("mobaSshBannerTargetIntro", chrome.target_intro)
            self.apply_ssh_banner_row_geometry(target, "target")
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            for row in self.state.banner.capability_rows():
                label = _literal_label(f"  * {row.line(label_width=chrome.capability_label_width)}")
                label.setParent(banner)
                label.setObjectName("mobaSshBannerCapability")
                self.apply_ssh_banner_font(label, pixel_size=12)
                label.setProperty("mobaSshBannerCapabilityKey", row.key)
                label.setProperty("mobaSshBannerCapabilityLabel", row.label)
                label.setProperty("mobaSshBannerCapabilityValue", row.value)
                label.setProperty("mobaSshBannerCapabilityStatus", row.status)
                label.setProperty("capabilityStatus", row.status)
                self.apply_ssh_banner_row_geometry(label, row.key)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            help_link, website_link = self.state.banner.footer_links()
            footer = _literal_label(f"> {chrome.footer_prefix} {help_link} or visit our {website_link}.")
            footer.setParent(banner)
            footer.setObjectName("mobaSshBannerFooter")
            self.apply_ssh_banner_font(footer, pixel_size=12)
            footer.setProperty("mobaSshBannerFooterLinks", [help_link, website_link])
            self.apply_ssh_banner_row_geometry(footer, "footer")
            footer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return banner

        def rebuild_telemetry_bar(self, *, hidden_keys: set[str] | None = None) -> QFrame:
            """Recreate the fixed status strip when live metrics add cells."""

            layout = self._connected_session_layout
            old_bar = getattr(self, "telemetry_bar", None)
            insert_at = layout.indexOf(old_bar) if old_bar is not None else -1
            if insert_at < 0:
                insert_at = layout.count()
            if old_bar is not None:
                layout.removeWidget(old_bar)
                old_bar.setParent(None)
                old_bar.deleteLater()
            bar = self.build_telemetry_bar()
            layout.insertWidget(insert_at, bar)
            for key in hidden_keys or set():
                frame = self.telemetry_cell_frames.get(key)
                if frame is None:
                    continue
                frame.setVisible(False)
                frame.setProperty("mobaTelemetryUserVisible", False)
            bar.setProperty(
                "mobaTelemetryVisibleCellKeys",
                [
                    key
                    for key, frame in self.telemetry_cell_frames.items()
                    if frame.property("mobaTelemetryUserVisible") is not False
                ],
            )
            layout.invalidate()
            layout.activate()
            return bar

        def build_telemetry_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("mobaTelemetryBar")
            self.telemetry_bar = bar
            self.telemetry_cell_frames: dict[str, QFrame] = {}
            self.apply_connected_session_route_properties(bar)
            self.apply_connected_identity_route_properties(bar)
            route = gui_design_moba_monitoring_telemetry_route()
            cells = moba_telemetry_cells(self.state)
            geometry_items = moba_telemetry_cell_geometry(
                tuple(cell.key for cell in cells)
            )
            bar.setProperty("mobaTelemetryGeometryKeys", [geometry.key for geometry in geometry_items])
            bar.setProperty("mobaTelemetryStartX", geometry_items[0].static_x)
            bar.setProperty("mobaTelemetryBarHeight", 24)
            bar.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            bar.setProperty("mobaMonitoringTelemetryRouteRole", route.route_role)
            bar.setProperty("mobaMonitoringTelemetrySourcePanelObject", route.source_panel_object)
            bar.setProperty("mobaMonitoringTelemetrySourceControl", route.source_control_key)
            bar.setProperty("mobaMonitoringTelemetrySurface", route.telemetry_surface)
            bar.setProperty("mobaMonitoringTelemetryMetricCellKeys", list(route.target_metric_cell_keys))
            bar.setProperty("mobaMonitoringTelemetryIdentityCellKey", route.target_identity_cell_key)
            bar.setProperty("mobaTelemetryDataSource", "unavailable-until-live")
            bar.setProperty("mobaTelemetryLive", False)
            bar.setProperty("mobaTerminalContextMenuObject", "mobaTerminalContextMenu")
            bar.setFixedHeight(24)
            self.install_moba_terminal_context_menu(bar)
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(geometry_items[0].static_x, 0, 7, 0)
            layout.setSpacing(0)
            for cell in cells:
                geometry = moba_telemetry_cell_geometry_for(cell.key)
                cell_frame = QFrame()
                cell_frame.setObjectName("mobaTelemetryCell")
                self.telemetry_cell_frames[cell.key] = cell_frame
                cell_frame.setProperty("mobaTelemetryKey", cell.key)
                cell_frame.setProperty("mobaTelemetryIconKey", cell.icon_key)
                cell_frame.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                cell_frame.setProperty("mobaTelemetryIconSize", cell.icon_size)
                cell_frame.setProperty("mobaTelemetryDisplayText", cell.display_text)
                if cell.key == "target":
                    self.apply_connected_identity_route_properties(cell_frame)
                cell_frame.setProperty("mobaTelemetryCellStaticX", geometry.static_x)
                cell_frame.setProperty("mobaTelemetryCellStaticY", geometry.static_y)
                cell_frame.setProperty("mobaTelemetryCellWidth", geometry.width)
                cell_frame.setProperty("mobaTelemetryCellHeight", geometry.height)
                cell_frame.setProperty("mobaTelemetrySeparatorTop", geometry.separator_top)
                cell_frame.setProperty("mobaTelemetrySeparatorBottom", geometry.separator_bottom)
                cell_frame.setProperty("mobaMonitoringTelemetryRouted", cell.key in route.target_metric_cell_keys)
                cell_frame.setProperty("mobaTelemetryLivePreferredWidth", geometry.width)
                cell_frame.setToolTip(
                    _safe_tooltip_html(f"{cell.label}: {cell.display_text}")
                )
                # Telemetry cells are a fixed-width status strip, not a
                # stretchable form row.  Ignored size policies let Qt squeeze
                # them to a few pixels when the terminal is resized, which is
                # why values appeared as clipped/blank boxes in the bottom
                # monitoring bar.
                # Keep the compact contract's minimum width unconstrained so
                # Qt can negotiate the status strip at narrow window sizes.
                # The fixed policy, child label hint, and maximum width still
                # preserve the measured cell width when space is available
                # without turning the strip into a hard minimum.
                cell_frame.setMinimumWidth(0)
                cell_frame.setMaximumWidth(geometry.width)
                cell_frame.setFixedHeight(geometry.height)
                cell_frame.setSizePolicy(
                    QSizePolicy.Policy.Fixed,
                    QSizePolicy.Policy.Fixed,
                )
                self.install_moba_terminal_context_menu(cell_frame)
                cell_layout = QHBoxLayout(cell_frame)
                cell_layout.setContentsMargins(geometry.icon_x, 0, 5, 0)
                cell_layout.setSpacing(geometry.label_x - geometry.icon_x - geometry.icon_size)
                icon = QLabel()
                icon.setObjectName("mobaTelemetryIcon")
                icon.setProperty("mobaTelemetryKey", cell.key)
                icon.setProperty("mobaTelemetryIconKey", cell.icon_key)
                icon.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                icon.setProperty("mobaTelemetryIconX", geometry.icon_x)
                icon.setProperty("mobaTelemetryIconY", geometry.icon_y)
                icon.setProperty("mobaTelemetryIconSize", geometry.icon_size)
                icon.setProperty("mobaTelemetryIconRender", "generated-pixmap")
                icon.setPixmap(self.telemetry_icon_pixmap(cell))
                icon.setFixedSize(QSize(geometry.icon_size, geometry.icon_size))
                icon.setToolTip(_safe_tooltip_html(cell.label))
                self.install_moba_terminal_context_menu(icon)
                cell_layout.addWidget(icon)
                label = _literal_label("")
                label.setObjectName("mobaTelemetryItem")
                label.setProperty("mobaTelemetryKey", cell.key)
                label.setProperty("mobaTelemetryDisplayText", cell.display_text)
                if cell.key == "target":
                    self.apply_connected_identity_route_properties(label)
                label.setProperty("mobaTelemetryLabelX", geometry.label_x)
                label.setProperty("mobaTelemetryLabelY", geometry.label_y)
                label.setProperty("mobaTelemetryLabelFontSize", geometry.label_font_size)
                label.setProperty(
                    "mobaTelemetryRenderedText",
                    self.telemetry_label_text(
                        label,
                        cell,
                        geometry.width - geometry.label_x - 8,
                    ),
                )
                label.setText(str(label.property("mobaTelemetryRenderedText")))
                label.setToolTip(
                    _safe_tooltip_html(f"{cell.label}: {cell.display_text}")
                )
                label.setMinimumWidth(
                    max(1, geometry.width - geometry.label_x - 8)
                )
                label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
                self.install_moba_terminal_context_menu(label)
                cell_layout.addWidget(label, 1)
                layout.addWidget(cell_frame, geometry.width)
            layout.addStretch(1)
            bar.setProperty(
                "mobaTelemetryVisibleCellKeys",
                list(self.telemetry_cell_frames),
            )
            return bar

        def generated_icon_pixmap(
            self,
            size: int,
            draw: Callable[[QPainter, int], None],
            *,
            antialias: bool = True,
        ) -> QPixmap:
            scale = max(1.0, float(self.devicePixelRatioF()))
            pixel_size = max(1, int(round(size * scale)))
            pixmap = QPixmap(pixel_size, pixel_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
            painter.scale(scale, scale)
            try:
                draw(painter, size)
            finally:
                painter.end()
            pixmap.setDevicePixelRatio(scale)
            return pixmap

        def telemetry_icon_pixmap(self, cell) -> QPixmap:
            size = cell.icon_size

            def draw(painter: QPainter, logical_size: int) -> None:
                accent = QColor(cell.icon_accent)
                dark = QColor("#101010")

                def pen(color: QColor, width: int = 1) -> None:
                    painter.setPen(QPen(color, width))

                def brush(color: QColor) -> None:
                    painter.setBrush(QBrush(color))

                pen(accent)
                brush(dark)
                painter.drawRect(0, 0, logical_size - 1, logical_size - 1)
                mid = logical_size // 2
                icon_key = cell.icon_key
                if icon_key == "host":
                    painter.drawRect(3, 3, logical_size - 6, logical_size - 8)
                    painter.drawLine(4, logical_size - 3, logical_size - 4, logical_size - 3)
                elif icon_key == "cpu":
                    painter.drawRect(3, 3, logical_size - 6, logical_size - 6)
                    painter.drawPoint(mid, 4)
                    painter.drawPoint(mid, logical_size - 4)
                    painter.drawPoint(4, mid)
                    painter.drawPoint(logical_size - 4, mid)
                elif icon_key in {"memory", "disk"}:
                    painter.drawRect(3, 4, logical_size - 6, logical_size - 8)
                    painter.drawLine(4, logical_size - 5, logical_size - 4, logical_size - 5)
                elif icon_key == "upload":
                    pen(accent, 2)
                    painter.drawLine(mid, logical_size - 3, mid, 3)
                    painter.drawLine(mid, 3, mid - 3, 6)
                    painter.drawLine(mid, 3, mid + 3, 6)
                elif icon_key == "download":
                    pen(accent, 2)
                    painter.drawLine(mid, 3, mid, logical_size - 3)
                    painter.drawLine(mid, logical_size - 3, mid - 3, logical_size - 6)
                    painter.drawLine(mid, logical_size - 3, mid + 3, logical_size - 6)
                elif icon_key == "connection":
                    pen(accent, 2)
                    painter.drawArc(2, 3, logical_size - 4, logical_size, 200 * 16, 140 * 16)
                elif icon_key == "process":
                    painter.drawLine(3, 4, logical_size - 3, 4)
                    painter.drawLine(3, 7, logical_size - 5, 7)
                    painter.drawLine(3, 10, logical_size - 6, 10)

            return self.generated_icon_pixmap(size, draw, antialias=False)

        @staticmethod
        def telemetry_label_text(
            label: QLabel,
            cell,
            available_width: int,
        ) -> str:
            """Fit live values into the fixed footer without losing their full tooltip."""

            display_text = str(cell.display_text)
            if display_text in {"Unavailable", "Connections: unavailable"}:
                display_text = "N/A"
            return label.fontMetrics().elidedText(
                display_text,
                Qt.TextElideMode.ElideRight,
                max(1, available_width),
            )

    return MobaConnectedSessionPanel
