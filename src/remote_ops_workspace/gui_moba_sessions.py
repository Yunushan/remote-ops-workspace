"""Coordinate connected terminal tabs and the MobaXterm preset's active SFTP dock."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QWidget

from . import gui_preset_properties
from .moba_connected import (
    MobaConnectedSessionState,
    build_moba_connected_session_state,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_window_title,
)
from .moba_ssh_browser import load_moba_ssh_browser_preferences

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStackedWidget, QTabWidget

    from .gui_connected import ConnectedSessionPanel, ConnectedSftpDock
    from .gui_terminal import TerminalPane
    from .gui_workspace import MobaWorkspaceTabBar
    from .models import Profile
    from .terminal import TerminalPanePlan


class MobaConnectedSessions:
    """Keep the active terminal, side dock, and connected-session metadata in sync."""

    if TYPE_CHECKING:
        _connected_session_panel_type: ClassVar[type[ConnectedSessionPanel]]
        _connected_sftp_dock_type: ClassVar[type[ConnectedSftpDock]]
        moba_connected_dock: ConnectedSftpDock | None
        moba_left_stack: QStackedWidget
        moba_tab_bar: MobaWorkspaceTabBar
        tabs: QTabWidget

        def add_workspace_tab(
            self, widget: QWidget, title: str, *, select: bool = True, role: str = "session",
        ) -> int: ...
        def apply_moba_tab_chrome(
            self, index: int, *, key: str, icon_key: str, tooltip: str, closeable: bool,
        ) -> None: ...
        def apply_moba_titlebar_chrome(self, title: str) -> None: ...
        def clear_deleted_tab_object_names(self, widget: QWidget) -> None: ...
        def current_design_is_moba(self) -> bool: ...
        def new_terminal_pane(
            self, plan: TerminalPanePlan, *, profile: Profile | None = None, autostart: bool = True,
        ) -> TerminalPane: ...
        def remember_terminal_plan(self, plan: TerminalPanePlan, *, profile: Profile | None = None) -> None: ...
        def session_action_capture_from_specs(
            self, specs: list[dict[str, object]],
        ) -> tuple[list[str], list[str], list[str], list[str]]: ...
        def set_literal_tab_tooltip(self, index: int, text: object, *, update_base: bool = True) -> None: ...
        def set_moba_quick_connect_connected_idle(self) -> None: ...
        def set_moba_rail_active(self, key: str) -> None: ...
        def setWindowTitle(self, title: str | None) -> None: ...  # noqa: N802
        def show_moba_profile_tree(self, *, preserve_connected_dock: bool = False) -> None: ...
        def start_terminal_pane_when_active(self, pane: TerminalPane, index: int) -> None: ...
        def tab_context_session_action_specs(self, index: int) -> list[dict[str, object]]: ...
        def update_session_status(self) -> None: ...

    def show_moba_connected_dock(self, state: MobaConnectedSessionState) -> None:
        if not hasattr(self, "moba_left_stack"):
            return
        widget = self.tabs.currentWidget()
        owner = widget if isinstance(widget, self._connected_session_panel_type) else None
        if owner is None and widget is not None:
            owner = widget.findChild(self._connected_session_panel_type)
        if (
            self.moba_connected_dock is not None
            and hasattr(self.moba_connected_dock, "can_reuse_for_state")
            and self.moba_connected_dock.session_panel is owner
            and self.moba_connected_dock.can_reuse_for_state(state)
        ):
            self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
            self.set_moba_quick_connect_connected_idle()
            self.set_moba_rail_active("sftp")
            title = moba_connected_window_title(state)
            self.setWindowTitle(title)
            self.apply_moba_titlebar_chrome(title)
            self.apply_moba_connected_identity_route_properties(state, cast(QWidget, self))
            self.apply_moba_connected_identity_route_properties(state, self.tabs)
            return
        if self.moba_connected_dock is not None:
            if hasattr(self.moba_connected_dock, "shutdown_runtime"):
                self.moba_connected_dock.shutdown_runtime()
            self.moba_left_stack.removeWidget(self.moba_connected_dock)
            self.moba_connected_dock.setMinimumSize(0, 0)
            self.clear_deleted_tab_object_names(self.moba_connected_dock)
            self.moba_connected_dock.deleteLater()
        self.moba_connected_dock = self._connected_sftp_dock_type(state)
        self.moba_connected_dock.session_panel = owner
        self.moba_left_stack.addWidget(self.moba_connected_dock)
        self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
        self.moba_connected_dock.initialize_background_state()
        if owner is not None:
            owner.terminal_pane.remoteDirectoryChanged.connect(
                self.moba_connected_dock.follow_reported_terminal_directory
            )
            self.moba_connected_dock.follow_reported_terminal_directory()
        self.set_moba_quick_connect_connected_idle()
        self.set_moba_rail_active("sftp")
        title = moba_connected_window_title(state)
        self.setWindowTitle(title)
        self.apply_moba_titlebar_chrome(title)
        self.apply_moba_connected_identity_route_properties(state, cast(QWidget, self))
        self.apply_moba_connected_identity_route_properties(state, self.tabs)

    def apply_moba_connected_identity_route_properties(
        self, state: MobaConnectedSessionState, widget: QWidget,
    ) -> None:
        route = moba_connected_session_identity_route(state)
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

    def current_moba_connected_dock_is_active(self) -> bool:
        return (
            hasattr(self, "moba_left_stack")
            and self.moba_connected_dock is not None
            and self.moba_left_stack.currentWidget() is self.moba_connected_dock
        )

    def refresh_moba_left_dock_for_current_tab(self) -> None:
        if not self.current_design_is_moba() or not hasattr(self, "moba_left_stack"):
            self.show_moba_profile_tree()
            return
        widget = self.tabs.currentWidget()
        state = self.moba_connected_state_in_widget(widget)
        if isinstance(state, MobaConnectedSessionState):
            self.show_moba_connected_dock(state)
        else:
            self.show_moba_profile_tree()

    @staticmethod
    def moba_connected_state_in_widget(widget: QWidget | None) -> MobaConnectedSessionState | None:
        if widget is None:
            return None
        state = getattr(widget, "moba_connected_state", None)
        if isinstance(state, MobaConnectedSessionState):
            return state
        for child in widget.findChildren(QWidget):
            state = getattr(child, "moba_connected_state", None)
            if isinstance(state, MobaConnectedSessionState):
                return state
        return None

    def apply_moba_connected_session_action_route_to_tab(
        self,
        panel: QWidget,
        state: MobaConnectedSessionState,
        tab_title: str,
        tab_index: int,
    ) -> None:
        if not self.current_design_is_moba() or tab_index < 0:
            return
        route = moba_connected_session_action_route(state)
        if tab_title not in {route.active_tab_label, route.reference_tab_label}:
            return
        specs = self.tab_context_session_action_specs(tab_index)
        action_keys, action_labels, enabled_keys, disabled_keys = self.session_action_capture_from_specs(specs)
        for widget in (panel, self.tabs, self.moba_tab_bar):
            gui_preset_properties.apply_moba_connected_session_action_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.captured_action_keys_property, action_keys)
            widget.setProperty(route.captured_action_labels_property, action_labels)
            widget.setProperty(route.captured_action_count_property, len(action_keys))
            widget.setProperty(route.captured_enabled_keys_property, enabled_keys)
            widget.setProperty(route.captured_disabled_keys_property, disabled_keys)

    def moba_connected_profile_supported(self, profile: Profile) -> bool:
        return self.current_design_is_moba() and profile.protocol.lower() in {"ssh", "sftp"}

    @staticmethod
    def moba_connected_remote_path_for_profile(profile: Profile) -> str:
        for key in ("moba_remote_path", "remote_path"):
            value = profile.options.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return profile.path or "/"

    @staticmethod
    def moba_connected_monitoring_output_for_profile(profile: Profile) -> str:
        value = profile.options.get("moba_monitoring_output")
        return value if isinstance(value, str) else ""

    def open_moba_connected_session_tab(
        self,
        profile: Profile,
        plan: TerminalPanePlan,
        *,
        remote_path: str = "/",
        tab_title: str | None = None,
        tab_status: str | None = None,
    ) -> ConnectedSessionPanel:
        try:
            ssh_browser_preferences = load_moba_ssh_browser_preferences()
        except (OSError, ValueError):
            ssh_browser_preferences = None
        state = build_moba_connected_session_state(
            profile,
            remote_path=remote_path,
            monitoring_output=self.moba_connected_monitoring_output_for_profile(profile),
            ssh_browser_preferences=ssh_browser_preferences,
        )
        panel = self._connected_session_panel_type(
            state,
            self.new_terminal_pane(plan, profile=profile, autostart=False),
        )
        panel.moba_connected_state = state
        if profile.protocol == "ssh" and plan.source == f"profile:{profile.name}":
            panel.terminal_pane.directory_report_host = profile.host
        self.remember_terminal_plan(plan, profile=profile)
        title = tab_title or moba_connected_tab_label(state)
        index = self.add_workspace_tab(panel, title, role="terminal")
        active_tab = next(item for item in moba_connected_tab_chrome_items(state) if item.key == "active-session")
        route = moba_connected_session_route(state)
        self.tabs.setProperty("mobaConnectedRouteKey", route.key)
        self.tabs.setProperty("mobaConnectedRouteRole", route.route_role)
        self.tabs.setProperty("mobaConnectedRouteActiveTabKey", route.active_tab_key)
        self.tabs.setProperty("mobaConnectedRouteActiveTabLabel", route.active_tab_label)
        self.tabs.setProperty("mobaConnectedRouteReferenceTabLabel", route.reference_tab_label)
        self.tabs.setProperty("mobaConnectedRouteActiveTabObject", route.active_tab_object)
        self.tabs.setProperty("mobaConnectedRouteConnectedPanelObject", route.connected_panel_object)
        self.tabs.setProperty("mobaConnectedRouteLeftDockObject", route.left_dock_object)
        self.tabs.setProperty("mobaConnectedRouteSftpBrowserObject", route.sftp_browser_object)
        self.tabs.setProperty("mobaConnectedRouteSftpPathObject", route.sftp_path_object)
        self.tabs.setProperty("mobaConnectedRouteSftpTableObject", route.sftp_table_object)
        self.tabs.setProperty("mobaConnectedRouteSshBannerObject", route.ssh_banner_object)
        self.tabs.setProperty("mobaConnectedRouteTerminalAreaObject", route.terminal_area_object)
        self.tabs.setProperty("mobaConnectedRouteTerminalOutputObject", route.terminal_output_object)
        self.tabs.setProperty("mobaConnectedRouteTelemetryBarObject", route.telemetry_bar_object)
        self.tabs.setProperty("mobaConnectedRouteTelemetryIdentityCellKey", route.telemetry_identity_cell_key)
        self.tabs.setProperty(route.target_property, route.target)
        self.tabs.setProperty(route.remote_path_property, route.remote_path)
        self.tabs.setProperty("mobaConnectedRouteRenderSource", route.render_source)
        self.apply_moba_tab_chrome(
            index,
            key=active_tab.key,
            icon_key=active_tab.icon_key,
            tooltip=active_tab.tooltip,
            closeable=active_tab.closeable,
        )
        self.apply_moba_connected_session_action_route_to_tab(panel, state, title, index)
        if tab_status:
            self.set_literal_tab_tooltip(
                index,
                f"{title}: {tab_status}",
                update_base=False,
            )
        if self.current_design_is_moba():
            self.show_moba_connected_dock(state)
        else:
            self.refresh_moba_left_dock_for_current_tab()
        self.update_session_status()
        self.start_terminal_pane_when_active(panel.terminal_pane, index)
        QTimer.singleShot(
            0,
            lambda panel=panel, index=index: (
                panel.terminal_pane.focus_terminal_input()
                if self.tabs.currentIndex() == index
                else None
            ),
        )
        return panel
