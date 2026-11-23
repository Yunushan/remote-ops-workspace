from __future__ import annotations

import os
import posixpath
import re
import stat
import sys
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol

from PyQt6.QtCore import (
    QMetaObject,
    QPoint,
    QProcess,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QBrush,
    QClipboard,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QStatusBar,
    QStyle,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .command_safety import CommandSafetyError
from .file_transfer import (
    SftpBatchPlan,
    SftpQueueItem,
    SftpQueuePlan,
    build_sftp_list_plan,
    format_transfer_item_spec,
)
from .gui_connected_terminal import (
    ConnectedSessionPanel as ConnectedSessionPanel,
)
from .gui_connected_terminal import (
    create_connected_terminal_class,
)
from .gui_designs import (
    gui_design_moba_connected_dock_frame,
    gui_design_moba_follow_terminal_folder_control_route,
    gui_design_moba_monitoring_control_geometry,
    gui_design_moba_monitoring_control_geometry_for,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_remote_monitoring_control_route,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_geometry_for,
    gui_design_moba_sftp_toolbar_action_route,
)
from .gui_processes import _background_process
from .gui_remote_monitoring import RemoteMonitoringRuntime
from .gui_sftp_editor import (
    SFTP_ROW_INDEX_ROLE,
    SFTP_ROW_KIND_ROLE,
    SFTP_ROW_SOURCE_PATH_ROLE,
    SftpTextEditor,
)
from .gui_ssh_connection import SharedSshConnectionState
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value, _safe_tooltip_html
from .launcher import LauncherError, pinned_smartcard_uses_agent
from .moba_connected import (
    MobaConnectedSessionState,
    moba_connected_session_route,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cells,
    normalise_remote_path,
    parse_sftp_ls_output,
)
from .models import Profile
from .smartcard_keys import PINNED_SMARTCARD_KEY
from .terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    ssh_command_with_control_path,
    ssh_connection_key,
    ssh_control_path_for_profile,
)

if TYPE_CHECKING:
    class ConnectedSftpDock(SftpTextEditor):
        state: MobaConnectedSessionState
        session_panel: ConnectedSessionPanel | None = None

        @abstractmethod
        def __init__(self, state: MobaConnectedSessionState) -> None: ...
        @abstractmethod
        def main_window(self) -> ConnectedMainWindow | None: ...
        @abstractmethod
        def can_reuse_for_state(self, state: MobaConnectedSessionState) -> bool: ...
        @abstractmethod
        def initialize_background_state(self) -> None: ...
        @abstractmethod
        def follow_reported_terminal_directory(self) -> bool: ...
        @abstractmethod
        def schedule_background_state_activation(self, delay_ms: int = 0) -> None: ...
        @abstractmethod
        def sync_shared_ssh_connection(self) -> SharedSshConnectionState | None: ...
        @abstractmethod
        def shutdown_runtime(self) -> None: ...

else:
    ConnectedSftpDock = SftpTextEditor


class ConnectedTransferQueue(Protocol):
    @property
    def operations(self) -> QPlainTextEdit: ...

    def refresh_queue_preview(self) -> None: ...
    def run_queue(self) -> None: ...
    def exec(self) -> int: ...
    def queue_plan(self) -> SftpQueuePlan: ...


class ConnectedMainWindow(Protocol):
    @property
    def tabs(self) -> QTabWidget: ...

    @property
    def log(self) -> QTextEdit: ...

    @property
    def moba_connected_dock(self) -> object | None: ...

    def statusBar(self) -> QStatusBar | None: ...  # noqa: N802
    def profile_by_name(self, name: str | None) -> Profile | None: ...
    def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]: ...
    def all_terminal_panes(self) -> list[TerminalPane]: ...
    def active_terminal_pane(self) -> TerminalPane | None: ...
    def create_transfer_queue_dialog(
        self,
        profile: Profile,
        *,
        prepare_command: Callable[[list[str]], list[str]] = ...,
        on_item_completed: Callable[[SftpQueueItem], None] | None = None,
    ) -> ConnectedTransferQueue: ...
    def show_moba_tools_status(self) -> None: ...


class LiteralLabel(Protocol):
    def __call__(self, text: object = "", parent: QWidget | None = None) -> QLabel: ...


class LiteralMessageBox(Protocol):
    def __call__(
        self,
        parent: QWidget | None,
        icon: QMessageBox.Icon,
        title: object,
        message: object,
        *,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox.StandardButton: ...


@dataclass(frozen=True)
class ConnectedGuiServices:
    """Window-local helpers used by the connected SSH and SFTP component."""

    main_window: Callable[[QWidget | None], ConnectedMainWindow | None]
    application_clipboard: Callable[[], QClipboard]
    literal_label: LiteralLabel
    literal_message_box: LiteralMessageBox
    widget_style: Callable[[QWidget], QStyle]


def create_moba_connected_classes(
    services: ConnectedGuiServices,
) -> tuple[type[ConnectedSftpDock], type[ConnectedSessionPanel]]:
    """Keep component class identity and main-window admission local to a factory."""

    _application_clipboard = services.application_clipboard
    _literal_label = services.literal_label
    _widget_style = services.widget_style

    SFTP_ROW_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 41
    SFTP_ROW_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 43
    SFTP_ROW_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 44
    SFTP_ROW_CONTRACT_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 45
    SFTP_ROW_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 46
    SFTP_ROW_SELECTED_BY_ROUTE_ROLE = int(Qt.ItemDataRole.UserRole) + 49
    SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 50


    class MobaSftpDock(ConnectedSftpDock, RemoteMonitoringRuntime):
        OPERATIONAL_ACTIONS = frozenset(
            {
                "parent-folder",
                "download",
                "upload",
                "new-folder",
                "connect",
                "tools",
                "terminal",
            }
        )
        UNAVAILABLE_ACTION_DETAILS = {
            "new-file": "Remote file creation is not available in the connected dock.",
            "delete": "Use Tools > Transfer queue for guarded rm/rmdir operations.",
            "ascii-mode": "ASCII transfer mode is not supported by the SFTP queue backend.",
            "split-view": "Split file comparison is not available in the connected dock.",
        }

        def main_window(self) -> ConnectedMainWindow | None:
            return services.main_window(self.window())

        @staticmethod
        def apply_connected_dock_frame_properties(widget) -> None:
            frame = gui_design_moba_connected_dock_frame()
            properties = {
                "mobaConnectedDockSideWidth": frame.side_width,
                "mobaConnectedDockRailWidth": frame.rail_width,
                "mobaConnectedDockX": frame.dock_x,
                "mobaConnectedDockY": frame.dock_y,
                "mobaConnectedDockWidth": frame.dock_width,
                "mobaConnectedDockHeight": frame.dock_height,
                "mobaConnectedDockWorkspaceX": frame.workspace_x,
                "mobaConnectedDockQuickConnectY": frame.quick_connect_y,
                "mobaConnectedDockQuickConnectHeight": frame.quick_connect_height,
                "mobaConnectedDockStatusY": frame.status_y,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_sftp_dock_density_properties(widget, density) -> None:
            widget.setProperty("mobaSftpDockInnerMargin", density.inner_margin)
            widget.setProperty("mobaSftpToolbarHeight", density.toolbar_height)
            widget.setProperty("mobaSftpPathHeight", density.path_height)
            widget.setProperty("mobaSftpHeaderHeight", density.table_header_height)
            widget.setProperty("mobaSftpRowHeight", density.file_row_height)
            widget.setProperty("mobaSftpMonitoringHeight", density.monitoring_height)
            widget.setProperty("mobaSftpStaticMaxRows", density.static_max_rows)
            widget.setProperty("mobaSftpToolbarSeparatorWidth", density.toolbar_separator_width)

        @staticmethod
        def moba_sftp_toolbar_action_index(route, action_key: str) -> int:
            try:
                return route.action_keys.index(action_key)
            except ValueError:
                return 0

        def apply_sftp_toolbar_action_route_properties(
            self,
            widget,
            route,
            *,
            triggered: bool = False,
            action_key: str | None = None,
            status: str | None = None,
        ) -> None:
            action_value = action_key or route.action_keys[1]
            action_index = self.moba_sftp_toolbar_action_index(route, action_value)
            status_value = status or route.action_statuses[action_index]
            properties = {
                "mobaSftpToolbarRouteKey": route.key,
                "mobaSftpToolbarRouteRole": route.route_role,
                "mobaSftpToolbarRouteToolbarObject": route.toolbar_object,
                "mobaSftpToolbarRouteActionObject": route.action_object,
                "mobaSftpToolbarRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpToolbarRouteTargetPathObject": route.target_path_object,
                "mobaSftpToolbarRouteTargetTableObject": route.target_table_object,
                "mobaSftpToolbarRouteQueueObject": route.queue_object,
                route.action_key_property: action_value,
                route.action_label_property: route.action_labels[action_index],
                route.action_object_property: route.action_object,
                route.icon_key_property: route.action_icon_keys[action_index],
                route.group_key_property: route.action_group_keys[action_index],
                route.tooltip_property: route.action_tooltips[action_index],
                "mobaSftpToolbarRouteSignal": route.signal,
                "mobaSftpToolbarRouteHandler": route.action_handlers[action_index],
                route.action_keys_property: list(route.action_keys),
                "mobaSftpToolbarRouteActionGroups": list(route.action_group_keys),
                route.captured_property: triggered,
                "mobaSftpToolbarRouteCapturedAction": action_value if triggered else "",
                route.captured_status_property: status_value if triggered else "",
                route.live_triggered_property: triggered,
                "mobaSftpToolbarRouteLiveAction": action_value,
                route.live_status_property: status_value,
                "mobaSftpToolbarRouteActionStatuses": list(route.action_statuses),
                "mobaSftpToolbarRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_sftp_follow_folder_route_properties(self, widget, route) -> None:
            follow_plan = self.state.follow_folder_plan.printable_batch()
            properties = {
                "mobaSftpFollowRouteKey": route.key,
                "mobaSftpFollowRouteRole": route.route_role,
                "mobaSftpFollowRouteSourceControlKey": route.source_control_key,
                "mobaSftpFollowRouteSourceControlObject": route.source_control_object,
                "mobaSftpFollowRouteSourcePathProperty": route.source_path_property,
                "mobaSftpFollowRouteSourcePlanProperty": route.source_plan_property,
                "mobaSftpFollowRouteSourceEnabledProperty": route.source_enabled_property,
                "mobaSftpFollowRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpFollowRouteTargetPathObject": route.target_path_object,
                "mobaSftpFollowRouteTargetTableObject": route.target_table_object,
                "mobaSftpFollowRouteTargetPathProperty": route.target_path_property,
                "mobaSftpFollowRouteTargetPlanProperty": route.target_plan_property,
                "mobaSftpFollowRouteTargetEnabledProperty": route.target_enabled_property,
                "mobaSftpFollowRouteRenderSource": route.render_source,
                "mobaSftpFollowRoutePath": self.state.remote_path,
                "mobaSftpFollowRoutePlan": follow_plan,
                "mobaSftpFollowRouteEnabled": self.state.follow_terminal_folder,
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

        def apply_sftp_routed_file_rows_properties(self, widget, rows, route) -> None:
            properties = {
                "mobaSftpRoutedRowsKey": rows.key,
                "mobaSftpRoutedRowsRole": rows.route_role,
                "mobaSftpRoutedRowsFollowRouteKey": rows.follow_route_key,
                "mobaSftpRoutedRowsTargetTableObject": rows.target_table_object,
                "mobaSftpRoutedRowsContractProperty": rows.row_contract_property,
                "mobaSftpRoutedRowsRouteProperty": rows.row_route_property,
                "mobaSftpRoutedRowsPathProperty": rows.row_path_property,
                "mobaSftpRoutedRowsIndexProperty": rows.row_index_property,
                "mobaSftpRoutedRowsSelectedProperty": rows.row_selected_property,
                "mobaSftpRoutedRowsParentRowName": rows.parent_row_name,
                "mobaSftpRoutedRowsSelectedRowKind": rows.selected_row_kind,
                "mobaSftpRoutedRowsRenderSource": rows.render_source,
                "mobaSftpRoutedRowsSourcePath": self.state.remote_path,
                "mobaSftpRoutedRowsEnabled": self.state.follow_terminal_folder,
                "mobaSftpRoutedRowsPlan": self.state.follow_folder_plan.printable_batch(),
                "mobaSftpRoutedRowsRoutePathProperty": route.target_path_property,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

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

        def apply_connected_ssh_browser_state_properties(self, widget) -> None:
            browser_state = self.state.ssh_browser_state
            properties = {
                "mobaSshBrowserLocation": browser_state.location,
                "mobaSshBrowserTerminalVisible": browser_state.terminal_visible,
                "mobaSshBrowserVisible": browser_state.browser_visible,
                "mobaSshBrowserOverwriteConfirmation": browser_state.overwrite_confirmation,
                "mobaSshBrowserColumnWidthMap": dict(browser_state.column_widths),
                "mobaSshBrowserPreferenceRenderSource": browser_state.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_smartcard_selection_properties(self, widget) -> None:
            selection = self.state.smartcard_selection
            properties = {
                "mobaSmartcardSelectionEnabled": selection.enabled,
                "mobaSmartcardProvider": selection.provider_label,
                "mobaSmartcardProviderKey": selection.provider_key,
                "mobaSmartcardCertificateId": selection.certificate_id,
                "mobaSmartcardCertificateLabel": selection.certificate_label,
                "mobaSmartcardPublicKey": selection.public_key,
                "mobaSmartcardAddToMobAgent": selection.add_to_mobagent,
                "mobaSmartcardAgentSocket": selection.agent_socket,
                "mobaSmartcardPkcs11Provider": selection.pkcs11_provider,
                "mobaSmartcardProfileOptionKeys": list(selection.profile_option_keys),
                "mobaSmartcardSelectionRenderSource": selection.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def __init__(self, state: MobaConnectedSessionState) -> None:
            QFrame.__init__(self)
            self.session_panel: ConnectedSessionPanel | None = None
            self._connected_services = services
            self.setObjectName("mobaConnectedLeftDock")
            self.state = replace(
                state,
                file_entries=self.filtered_sftp_entries(state.file_entries),
            )
            self.active_remote_path = normalise_remote_path(self.state.remote_path)
            self.monitoring_control_widgets: dict[str, QAbstractButton] = {}
            self.runtime_shutting_down = False
            self.background_auth_retry_attempt = 0
            self._background_password: bytearray | None = None
            self.setProperty("mobaBackgroundSshCredentialSource", "")
            self._background_auth_prompt_buffers = {
                "monitoring": bytearray(),
                "sftp": bytearray(),
                "text-editor": bytearray(),
            }
            self._background_auth_prompt_complete = {
                "monitoring": False,
                "sftp": False,
                "text-editor": False,
            }
            self.background_auth_retry_timer = QTimer(self)
            self.background_auth_retry_timer.setSingleShot(True)
            self.background_auth_retry_timer.timeout.connect(
                self.retry_background_authentication
            )
            self.background_state_activation_timer = QTimer(self)
            self.background_state_activation_timer.setSingleShot(True)
            self.background_state_activation_timer.timeout.connect(
                self.activate_initial_background_state
            )
            self.initialize_monitoring_runtime(_background_process)
            self.sftp_refresh_output_buffer = bytearray()
            self.sftp_refresh_error_buffer = bytearray()
            self.sftp_refresh_plan: SftpBatchPlan | None = None
            self.sftp_refresh_generation = 0
            self.sftp_refresh_active_generation = 0
            self.sftp_refresh_request_path = ""
            self.sftp_refresh_pending: tuple[str, str] | None = None
            self.sftp_refresh_process = _background_process(self, interactive_auth=True)
            # Pipe-backed Qt processes can lose rows from large OpenSSH
            # listings with merged channels. A ConPTY still has one stream.
            self.sftp_refresh_process.setProcessChannelMode(
                QProcess.ProcessChannelMode.SeparateChannels
            )
            self.sftp_refresh_process.started.connect(
                self.write_sftp_refresh_batch
            )
            self.sftp_refresh_process.readyReadStandardOutput.connect(
                self.read_sftp_refresh_output
            )
            self.sftp_refresh_process.readyReadStandardError.connect(
                self.read_sftp_refresh_error
            )
            self.sftp_refresh_process.finished.connect(
                self.handle_sftp_refresh_finished
            )
            self.sftp_refresh_process.errorOccurred.connect(
                self.handle_sftp_refresh_error
            )
            self.sftp_refresh_timeout = QTimer(self)
            self.sftp_refresh_timeout.setSingleShot(True)
            self.sftp_refresh_timeout.timeout.connect(
                self.cancel_sftp_refresh_timeout
            )
            self.sftp_auth_probe_timer = QTimer(self)
            self.sftp_auth_probe_timer.setSingleShot(True)
            self.sftp_auth_probe_timer.setInterval(1200)
            self.sftp_auth_probe_timer.timeout.connect(
                lambda: self.write_sftp_refresh_batch(force=True)
            )
            self.initialize_text_editor_runtime(_background_process)
            frame = gui_design_moba_connected_dock_frame()
            density = gui_design_moba_sftp_dock_layout()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            routed_rows = gui_design_moba_sftp_routed_file_rows()
            self.apply_connected_dock_frame_properties(self)
            self.apply_connected_session_route_properties(self)
            self.apply_connected_ssh_browser_state_properties(self)
            self.apply_connected_smartcard_selection_properties(self)
            self.apply_connected_text_editor_route_properties(self)
            self.setMinimumWidth(min(frame.dock_width, 280))
            self.setMinimumHeight(min(frame.dock_height, 320))

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            browser = QFrame()
            browser.setObjectName("mobaSftpBrowser")
            browser.setMinimumWidth(min(frame.dock_width, 280))
            browser.setMinimumHeight(min(frame.dock_height, 320))
            self.browser = browser
            self.apply_connected_dock_frame_properties(browser)
            self.apply_connected_session_route_properties(browser)
            self.apply_connected_ssh_browser_state_properties(browser)
            self.apply_connected_smartcard_selection_properties(browser)
            self.apply_connected_text_editor_route_properties(browser)
            self.apply_sftp_dock_density_properties(browser, density)
            self.apply_sftp_follow_folder_route_properties(browser, follow_route)
            self.apply_sftp_terminal_folder_route_properties(browser)
            browser.setVisible(self.state.ssh_browser_state.browser_visible)
            outer_layout.addWidget(browser)

            layout = QVBoxLayout(browser)
            layout.setContentsMargins(
                density.inner_margin,
                density.inner_margin,
                density.inner_margin,
                density.inner_margin,
            )
            layout.setSpacing(0)

            toolbar = QFrame()
            toolbar.setObjectName("mobaSftpToolbar")
            toolbar.setProperty("mobaSftpToolbarHeight", density.toolbar_height)
            toolbar.setFixedHeight(density.toolbar_height)
            toolbar_route = gui_design_moba_sftp_toolbar_action_route()
            self.toolbar = toolbar
            self.sftp_action_buttons: dict[str, QToolButton] = {}
            self.apply_sftp_toolbar_action_route_properties(self, toolbar_route)
            self.apply_sftp_toolbar_action_route_properties(toolbar, toolbar_route)
            self.apply_sftp_toolbar_action_route_properties(browser, toolbar_route)
            toolbar_geometry = gui_design_moba_sftp_toolbar_action_geometry()
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(
                toolbar_geometry[0].button_x,
                toolbar_geometry[0].button_y,
                0,
                toolbar_geometry[0].button_y,
            )
            toolbar_layout.setSpacing(0)
            for action in gui_design_moba_sftp_dock_actions():
                button = self.tool_button(action, density)
                self.sftp_action_buttons[action.key] = button
                toolbar_layout.addWidget(button)
                if action.separator_after:
                    toolbar_layout.addWidget(self.toolbar_separator(action, density))
            transfer_button = self.build_sftp_transfer_menu_button()
            toolbar_layout.addWidget(transfer_button)
            toolbar_layout.addStretch(1)
            self.sftp_status_badge = self.sftp_action_buttons.get("connect")
            self._sftp_status_default_icon = (
                self.sftp_status_badge.icon()
                if self.sftp_status_badge is not None
                else QIcon()
            )
            layout.addWidget(toolbar)

            chrome = gui_design_moba_sftp_browser_chrome()
            column_widths = [
                self.state.ssh_browser_state.column_widths.get(column.key, column.static_width)
                for column in chrome.columns
            ]
            path = QLineEdit()
            path.setObjectName("mobaSftpPath")
            path.setText(self.state.remote_path)
            path.setPlaceholderText(chrome.path_placeholder)
            path.setProperty("mobaSftpPathDropdownMarker", chrome.dropdown_marker)
            path.setProperty("mobaSftpPathHeight", density.path_height)
            path.setProperty("mobaSftpPathTextX", chrome.path_text_x)
            path.setProperty("mobaSftpPathTextY", chrome.path_text_y)
            path.setProperty("mobaSftpPathFontSize", chrome.path_font_size)
            path.setProperty("mobaSftpDropdownRightOffset", chrome.dropdown_right_offset)
            path.setProperty("mobaSftpDropdownY", chrome.dropdown_y)
            path.setProperty("mobaSftpDropdownFontSize", chrome.dropdown_font_size)
            self.apply_sftp_follow_folder_route_properties(path, follow_route)
            self.apply_sftp_terminal_folder_route_properties(path)
            self.apply_sftp_toolbar_action_route_properties(path, toolbar_route)
            self.apply_connected_session_route_properties(path)
            self.apply_connected_ssh_browser_state_properties(path)
            self.apply_connected_smartcard_selection_properties(path)
            self.apply_connected_text_editor_route_properties(path)
            path.setFixedHeight(density.path_height)
            path.setToolTip(_safe_tooltip_html(self.state.follow_folder_plan.printable_batch()))
            path.returnPressed.connect(self.handle_moba_sftp_path_entered)
            self.path = path
            layout.addSpacing(density.path_gap)
            layout.addWidget(path)

            self.file_table = QTreeWidget()
            self.file_table.setObjectName("mobaSftpFileTable")
            self.file_table.setColumnCount(len(chrome.columns))
            self.file_table.setHeaderLabels([column.label for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnKeys", [column.key for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnLabels", [column.label for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnWidths", column_widths)
            self.file_table.setProperty("mobaSftpColumnWidthSource", self.state.ssh_browser_state.render_source)
            self.file_table.setProperty("mobaSftpParentRowLabel", chrome.parent_row_label)
            self.file_table.setProperty("mobaSftpParentRowKind", chrome.parent_row_kind)
            self.file_table.setProperty("mobaSftpSelectedRowKind", chrome.selected_row_kind)
            self.file_table.setProperty("mobaSftpHeaderHeight", density.table_header_height)
            self.file_table.setProperty("mobaSftpHeaderLabelY", chrome.header_label_y)
            self.file_table.setProperty("mobaSftpHeaderFontSize", chrome.header_font_size)
            self.file_table.setProperty("mobaSftpRowHeight", density.file_row_height)
            self.file_table.setProperty("mobaSftpRowTopOffset", chrome.row_top_offset)
            self.file_table.setProperty("mobaSftpRowIconX", chrome.row_icon_x)
            self.file_table.setProperty("mobaSftpRowIconYOffset", chrome.row_icon_y_offset)
            self.file_table.setProperty("mobaSftpRowNameX", chrome.row_name_x)
            self.file_table.setProperty("mobaSftpRowSizeX", chrome.row_size_x)
            self.file_table.setProperty("mobaSftpRowModifiedX", chrome.row_modified_x)
            self.file_table.setProperty("mobaSftpRowTextYOffset", chrome.row_text_y_offset)
            self.file_table.setProperty("mobaSftpRowTextFontSize", chrome.row_text_font_size)
            self.file_table.setProperty("mobaSftpRowModifiedFontSize", chrome.row_modified_font_size)
            self.file_table.setProperty(
                "mobaSftpFileRowIconKinds",
                [row_icon.kind for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
            self.file_table.setProperty(
                "mobaSftpFileRowIconKeys",
                [row_icon.icon_key for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
            self.apply_sftp_follow_folder_route_properties(self.file_table, follow_route)
            self.apply_sftp_routed_file_rows_properties(self.file_table, routed_rows, follow_route)
            self.apply_sftp_terminal_folder_route_properties(self.file_table)
            self.apply_sftp_toolbar_action_route_properties(self.file_table, toolbar_route)
            self.apply_connected_session_route_properties(self.file_table)
            self.apply_connected_ssh_browser_state_properties(self.file_table)
            self.apply_connected_smartcard_selection_properties(self.file_table)
            self.apply_connected_text_editor_route_properties(self.file_table)
            self.file_table.setIconSize(QSize(density.toolbar_icon_size, density.toolbar_icon_size))
            self.file_table.setRootIsDecorated(False)
            self.file_table.setUniformRowHeights(True)
            self.file_table.setSortingEnabled(False)
            self.file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            file_header = _required_gui_value(
                self.file_table.header(),
                "SFTP file table header",
            )
            file_header.setFixedHeight(density.table_header_height)
            file_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            file_header.setStretchLastSection(False)
            for column_index, width in enumerate(column_widths):
                self.file_table.setColumnWidth(column_index, width)
            self.populate_sftp_file_table(self.state.file_entries, self.active_remote_path)
            self.file_table.currentItemChanged.connect(self.update_sftp_action_states)
            self.file_table.itemDoubleClicked.connect(self.handle_moba_text_editor_open_from_item)
            self.file_table.customContextMenuRequested.connect(self.show_sftp_context_menu)
            layout.addSpacing(density.table_header_gap)
            layout.addWidget(self.file_table, 1)

            self.text_editor_toolbar = self.build_text_editor_toolbar()
            self.text_editor_toolbar.setVisible(False)
            self.text_editor_toolbar.setProperty("mobaTextEditorOnDemand", True)
            layout.addWidget(self.text_editor_toolbar)
            self.text_editor = self.build_text_editor()
            self.text_editor.setVisible(False)
            self.text_editor.setProperty("mobaTextEditorOnDemand", True)
            layout.addWidget(self.text_editor)

            queue = QLabel("Queue: SFTP toolbar idle")
            queue.setObjectName(toolbar_route.queue_object)
            self.apply_sftp_toolbar_action_route_properties(queue, toolbar_route)
            queue.setVisible(False)
            self.sftp_transfer_queue = queue
            layout.addWidget(queue)

            layout.addWidget(self.build_remote_monitoring(density))
            self.update_sftp_action_states()
            self.set_sftp_runtime_status("SFTP listing idle", state="idle")
            self.schedule_background_state_activation()

        @staticmethod
        def filtered_sftp_entries(entries):
            """Keep the single synthetic parent row authoritative."""

            return tuple(entry for entry in entries if entry.name.strip() not in {".", ".."})

        def _shared_ssh_panes(self) -> list[TerminalPane]:
            main_window = self.main_window()
            key = self.state.ssh_connection_key
            if not key or main_window is None or not hasattr(main_window, "tabs"):
                return []
            current = main_window.tabs.currentWidget()
            visible = main_window.terminal_panes_in(current) if current is not None else []
            pane_provider = getattr(main_window, "all_terminal_panes", None)
            other_panes = [pane for pane in pane_provider() if pane not in visible] if callable(pane_provider) else []
            panes = [*visible, *other_panes]
            return [pane for pane in panes if getattr(pane, "ssh_connection_key", "") == key]

        def shared_ssh_control_path(self) -> str:
            """Find an available OpenSSH control socket for this session."""

            for pane in self._shared_ssh_panes():
                if not pane.is_running():
                    continue
                connection = getattr(pane, "ssh_connection", None)
                if connection is not None and connection.state.phase != "connected":
                    continue
                control_path = str(getattr(pane, "ssh_control_path", "") or "")
                if not control_path:
                    continue
                try:
                    mode = Path(control_path).lstat().st_mode
                except OSError:
                    continue
                # OpenSSH creates the control socket after authentication.
                if stat.S_ISSOCK(mode):
                    return control_path
            return ""

        def sync_shared_ssh_connection(self) -> SharedSshConnectionState | None:
            states = [
                connection.state
                for pane in self._shared_ssh_panes()
                if (connection := getattr(pane, "ssh_connection", None)) is not None
            ]
            selected = next((state for state in states if state.phase == "connected"), None)
            if selected is None and states:
                selected = next((state for state in states if state.phase not in {"idle", "closed"}), states[0])
            snapshot = selected.properties() if selected is not None else None
            description = selected.description() if selected is not None else ""
            self.setProperty("sshConnectionDescription", description)
            sftp_status = getattr(self, "sftp_status_badge", None)
            monitoring = self.monitoring_control_widgets.get("remote-monitoring")
            for widget in (self, self.browser, sftp_status, self.remote_monitoring_panel, monitoring):
                if widget is not None:
                    widget.setProperty("sshConnectionState", snapshot)
            for badge, message_key in (
                (sftp_status, "mobaSftpStatusBadgeMessage"),
                (monitoring, "mobaMonitoringStatusBadgeMessage"),
            ):
                if badge is not None:
                    message = str(badge.property(message_key) or "")
                    badge.setToolTip(self._background_ssh_tooltip(message))
                    badge.setAccessibleDescription("\n".join(filter(None, (message, description))))
            return selected

        def _background_ssh_tooltip(self, message: str) -> str:
            description = str(self.property("sshConnectionDescription") or "")
            return _safe_tooltip_html("\n".join(filter(None, (message, description, self.background_ssh_auth_detail()))))

        def _waiting_for_shared_ssh(self) -> bool:
            snapshot = self.property("sshConnectionState")
            return isinstance(snapshot, dict) and snapshot["phase"] != "connected"

        def background_ssh_auth_capability(self, profile: Profile | None) -> tuple[bool, str]:
            """Return whether an automatic, non-interactive SSH child is defensible."""

            if profile is None:
                return False, "connected profile was not found"
            if PINNED_SMARTCARD_KEY in profile.options:
                if self.shared_ssh_control_path():
                    return True, "active terminal SSH connection (shared control socket)"
                if ssh_control_path_for_profile(profile):
                    return False, "waiting for the terminal to authenticate with the saved smart-card key"
                try:
                    if pinned_smartcard_uses_agent(profile.options):
                        return True, "configured SSH agent for the saved smart-card key"
                except LauncherError as exc:
                    return False, str(exc)
                return False, "the saved smart-card key needs an authenticated terminal or a configured SSH agent"
            if self._background_password and self.background_auth_password_supported():
                return True, "encrypted-vault credential loaded for this session"
            if self.shared_ssh_control_path():
                return True, "active terminal SSH connection (shared control socket)"
            if profile.identity_file:
                identity = Path(profile.identity_file).expanduser()
                if identity.is_file():
                    return True, f"identity file: {identity}"
                return False, f"configured identity file was not found: {identity}"
            normalized = {
                str(key).strip().lower(): str(value).strip()
                for key, value in profile.options.items()
            }
            for key in ("identity_agent", "ssh_identity_agent", "mobagent_socket"):
                if normalized.get(key):
                    return True, f"configured SSH agent: {key}"
            if os.environ.get("SSH_AUTH_SOCK"):
                return True, "SSH_AUTH_SOCK agent"
            if any(
                normalized.get(key, "").lower() in {"1", "true", "yes", "on"}
                for key in ("use_ssh_agent", "ssh_agent", "background_auth")
            ):
                return True, "explicit SSH-agent background-auth setting"
            return (
                False,
                "background SSH uses a separate non-interactive process and requires "
                "a trusted host key plus key or agent authentication; use "
                "Authenticate background tools to load a vault credential or enter "
                "a session password",
            )

        def background_auth_transport_is_pty(self) -> bool:
            """Return whether both hidden background clients can accept a password."""

            return bool(
                getattr(self.monitoring_process, "is_pty", False)
                and getattr(self.sftp_refresh_process, "is_pty", False)
            )

        def background_auth_password_supported(self) -> bool:
            """Return whether this platform can use a session password for background SSH."""

            # POSIX keeps the established QProcess pipe-based authentication path;
            # native Windows OpenSSH requires ConPTY so password prompts are not
            # sent to an invisible or unrelated console window.
            return sys.platform != "win32" or self.background_auth_transport_is_pty()

        def background_ssh_auth_detail(self) -> str:
            """Describe the authentication route currently used by background tools."""

            profile = self.profile_for_sftp_action()
            if profile is not None and PINNED_SMARTCARD_KEY in profile.options:
                return self.background_ssh_auth_capability(profile)[1]
            if self._background_password and self.background_auth_password_supported():
                source = str(self.property("mobaBackgroundSshCredentialSource") or "")
                source_detail = (
                    "a profile credential loaded from the encrypted vault"
                    if source == "encrypted-vault"
                    else "a password entered for this GUI session"
                )
                return (
                    "A separate non-interactive SSH process uses "
                    f"{source_detail}; the secret "
                    "is submitted through hidden native terminal transports."
                )
            if self.shared_ssh_control_path():
                return (
                    "The active terminal owns a private SSH control connection, so this "
                    "background request reuses the authenticated session."
                )
            return (
                "This background request uses a separate non-interactive SSH process; "
                "terminal password prompts are not shared. A trusted host key and key "
                "or agent authentication are required, or use Authenticate background "
                "tools for a session-only password."
            )

        def _clear_background_password(self) -> None:
            password = self._background_password
            self._background_password = None
            if password is not None:
                password.clear()
            for buffer in self._background_auth_prompt_buffers.values():
                buffer.clear()
            self.setProperty("mobaBackgroundSshCredentialLoaded", False)
            self.setProperty("mobaBackgroundSshCredentialSource", "")

        def background_ssh_overrides(self) -> dict[str, str]:
            """Build the runtime-only auth policy for one hidden SSH child."""

            if not self._background_password:
                return {
                    "BatchMode": "yes",
                    "ConnectTimeout": "5",
                    "StrictHostKeyChecking": "yes",
                }
            return {
                "BatchMode": "no",
                "ConnectTimeout": "5",
                "StrictHostKeyChecking": "yes",
                # Password injection is supported only for a direct target.
                # Command-line OpenSSH options are processed before ambient
                # configuration, so these values prevent ~/.ssh/config from
                # introducing a password-prompting helper or jump process.
                "ProxyJump": "none",
                "ProxyCommand": "none",
                "PasswordAuthentication": "yes",
                "KbdInteractiveAuthentication": "yes",
                "PreferredAuthentications": "password,keyboard-interactive",
                "NumberOfPasswordPrompts": "1",
            }

        def _submit_background_password_if_prompt(
            self,
            process_kind: str,
            payload: bytes,
        ) -> None:
            """Answer one OpenSSH prompt through the hidden ConPTY only."""

            password = self._background_password
            if not password or process_kind not in self._background_auth_prompt_buffers:
                return
            if self._background_auth_prompt_complete[process_kind]:
                return
            prompt_buffer = self._background_auth_prompt_buffers[process_kind]
            prompt_buffer.extend(payload)
            del prompt_buffer[:-1024]
            prompt = prompt_buffer.decode(errors="replace")[-768:]
            # ConPTY can surround the OpenSSH prompt with cursor and title updates.
            prompt = re.sub(
                r"\x1b(?:\[(?:\?[0-9;]+[hl]|[0-9;]*[mHJC])|\]0;[^\x07\x1b]*(?:\x07|\x1b\\))",
                "",
                prompt,
            )
            if not self.background_password_prompt_matches_target(prompt):
                if re.search(
                    r"(?i)(?:password|passphrase)[^:\r\n]{0,240}:\s*$",
                    prompt,
                ):
                    prompt_buffer.clear()
                return
            process = {
                "monitoring": self.monitoring_process,
                "sftp": self.sftp_refresh_process,
                "text-editor": self.text_editor_process,
            }.get(process_kind)
            if process is None:
                return
            # Win32 OpenSSH can consume the next console character after CR.
            # LF ends the password without reading into the SFTP batch.
            ending = b"\n" if getattr(process, "is_pty", False) else b"\r"
            accepted = process.write(bytes(password) + ending)
            if accepted <= 0:
                return
            self._background_auth_prompt_complete[process_kind] = True
            prompt_buffer.clear()
            if process_kind == "sftp":
                self.sftp_auth_probe_timer.stop()
                QTimer.singleShot(
                    0,
                    lambda: self.write_sftp_refresh_batch(force=True),
                )
            elif process_kind == "text-editor":
                self.text_editor_auth_probe_timer.stop()
                QTimer.singleShot(
                    0,
                    lambda: self.write_text_editor_sftp_batch(force=True),
                )

        def background_password_prompt_matches_target(self, prompt: str) -> bool:
            """Accept only a direct target's explicit OpenSSH password prompt.

            Generic keyboard-interactive prompts, private-key passphrase prompts,
            and multi-hop/custom-proxy sessions deliberately require agent/key or
            shared-control authentication so a bastion/helper cannot receive the
            target credential.
            """

            profile = self.profile_for_sftp_action()
            if profile is None or not profile.host:
                return False
            if any(
                profile.options.get(key)
                for key in ("proxy_jump", "jump_host", "proxy_command")
            ):
                return False
            tail = prompt.rsplit("\n", 1)[-1].rsplit("\r", 1)[-1].strip()
            if "passphrase" in tail.lower():
                return False
            if not re.search(r"(?i)password[^:\r\n]{0,240}:\s*$", tail):
                return False
            target = re.escape(profile.host)
            if profile.username:
                identities = (f"{re.escape(profile.username)}@{target}", target)
                identity_pattern = "|".join(identities)
            else:
                # With no explicit User, OpenSSH can display the local/configured
                # username, but the host token must still be an exact match.
                identity_pattern = rf"(?:[^@\s']+@)?{target}"
            return bool(
                re.fullmatch(
                    rf"(?:{identity_pattern})'s password:\s*",
                    tail,
                    flags=re.IGNORECASE,
                )
            )

        def authenticate_background_tools(self) -> bool:
            """Unlock one profile credential for this GUI session only."""

            profile = self.profile_for_sftp_action()
            if profile is None:
                message = "Background SSH authentication requires a connected profile."
                self.set_sftp_runtime_status(message, state="auth-required")
                self.set_remote_monitoring_status(message, state="auth-required")
                self.show_sftp_status(message)
                return False
            if PINNED_SMARTCARD_KEY in profile.options:
                self.show_sftp_status(self.background_ssh_auth_capability(profile)[1])
                return False
            credential_ref = str(profile.credential_ref or "").strip() if profile else ""
            if not self.background_auth_password_supported():
                message = (
                    "Background password authentication needs native Windows ConPTY; "
                    "configure a key or SSH agent on this platform."
                )
                self.set_sftp_runtime_status(message, state="auth-required")
                self.set_remote_monitoring_status(message, state="auth-required")
                self.show_sftp_status(message)
                return False
            if credential_ref:
                prompt, accepted = QInputDialog.getText(
                    self,
                    "Authenticate background tools",
                    f"Vault passphrase for {credential_ref}:",
                    QLineEdit.EchoMode.Password,
                )
                source = "encrypted-vault"
                if not accepted:
                    self.show_sftp_status("Background SSH authentication cancelled")
                    return False
                if not prompt:
                    self.show_sftp_status("Vault passphrase is required")
                    return False
                try:
                    from .vault import LocalVault

                    secret = LocalVault().get(credential_ref, prompt)
                except Exception as exc:  # noqa: BLE001 - fail closed at the GUI boundary
                    detail = str(exc).strip() or "credential could not be loaded"
                    self.set_sftp_runtime_status(
                        f"Background authentication failed: {detail[:120]}",
                        state="error",
                    )
                    self.set_remote_monitoring_status(
                        f"Background authentication failed: {detail[:120]}",
                        state="error",
                    )
                    self.show_sftp_status(f"Background authentication failed: {detail[:120]}")
                    return False
                empty_message = "Vault credential is empty"
            else:
                target = f"{profile.username or 'user'}@{profile.host or 'host'}"
                secret, accepted = QInputDialog.getText(
                    self,
                    "Authenticate background tools",
                    f"SSH password for {target}:",
                    QLineEdit.EchoMode.Password,
                )
                source = "session-prompt"
                if not accepted:
                    self.show_sftp_status("Background SSH authentication cancelled")
                    return False
                if not secret:
                    self.show_sftp_status("SSH password is required")
                    return False
                empty_message = "SSH password is empty"
            secret_bytes = secret.encode("utf-8")
            del secret
            if not secret_bytes:
                self.show_sftp_status(empty_message)
                return False
            self._clear_background_password()
            self._background_password = bytearray(secret_bytes)
            del secret_bytes
            self.setProperty("mobaBackgroundSshCredentialRef", credential_ref)
            self.setProperty("mobaBackgroundSshCredentialSource", source)
            self.setProperty("mobaBackgroundSshCredentialLoaded", True)
            self.show_sftp_status(
                "Background SSH credential loaded for this session"
            )
            self._apply_initial_background_state(start_runtime=True)
            return True

        def ensure_background_authentication_for_request(
            self,
            *,
            allow_prompt: bool = False,
        ) -> bool:
            """Require background auth without opening an implicit modal prompt."""

            profile = self.profile_for_sftp_action()
            available, _detail = self.background_ssh_auth_capability(profile)
            if available:
                return True
            if profile is not None and allow_prompt:
                return self.authenticate_background_tools()
            if profile is not None:
                detail = self.background_ssh_auth_detail()
                message = f"Background SSH authentication required: {detail}"
                self.set_sftp_runtime_status(message, state="auth-required")
                self.set_remote_monitoring_status(message, state="auth-required")
                self.show_sftp_status(message)
                return False
            return True

        def schedule_background_auth_retry(self, *, waiting_for_smartcard: bool = False) -> None:
            """Retry background clients after the interactive SSH prompt completes."""

            if self.runtime_shutting_down:
                return
            profile = self.profile_for_sftp_action()
            available, _detail = self.background_ssh_auth_capability(profile)
            if not available and not waiting_for_smartcard:
                return
            self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", True)
            self.background_auth_retry_attempt = min(
                self.background_auth_retry_attempt + 1,
                5,
            )
            delay_ms = min(
                15_000,
                1_000 * (2 ** (self.background_auth_retry_attempt - 1)),
            )
            self.setProperty("mobaBackgroundSshRetryDelayMs", delay_ms)
            if not self.background_auth_retry_timer.isActive():
                self.background_auth_retry_timer.start(delay_ms)

        def retry_background_authentication(self) -> None:
            if self.runtime_shutting_down:
                return
            if not bool(self.property("mobaBackgroundSshWaitingForTerminalAuth")):
                return
            self.activate_initial_background_state()

        def initialize_background_state(self) -> None:
            """Publish auth/runtime state before deferred SSH work begins."""

            if self.runtime_shutting_down:
                return
            self.background_state_activation_timer.stop()
            self.update_sftp_action_states()
            self._apply_initial_background_state(start_runtime=False)
            self.schedule_background_state_activation()

        def schedule_background_state_activation(self, delay_ms: int = 0) -> None:
            """Run background-state setup only while this dock is alive."""

            if self.runtime_shutting_down:
                return
            self.background_state_activation_timer.start(max(0, int(delay_ms)))

        def activate_initial_background_state(self) -> None:
            self._apply_initial_background_state(start_runtime=True)

        def _apply_initial_background_state(self, *, start_runtime: bool) -> None:
            if self.runtime_shutting_down:
                return
            profile = self.profile_for_sftp_action()
            self.sync_shared_ssh_connection()
            if self._waiting_for_shared_ssh():
                available, detail = False, "waiting for the managed terminal SSH connection"
            else:
                available, detail = self.background_ssh_auth_capability(profile)
            auth_gate_forced_monitoring_off = bool(
                self.property("mobaBackgroundSshAuthGateForcedMonitoringOff")
            )
            for widget in (
                self,
                getattr(self, "browser", None),
                getattr(self, "file_table", None),
            ):
                if widget is not None:
                    widget.setProperty("mobaBackgroundSshAuthAvailable", available)
                    widget.setProperty("mobaBackgroundSshAuthDetail", detail)
            if available:
                self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", False)
                self.set_sftp_runtime_status(
                    f"Initial SFTP refresh pending ({detail})",
                    state="pending",
                )
                if not start_runtime:
                    control = self.monitoring_control_widgets.get("remote-monitoring")
                    self.set_remote_monitoring_runtime(
                        bool(control is not None and control.isChecked()),
                        immediate=False,
                        start_periodic=False,
                    )
                    return
                restored_monitoring = False
                control = self.monitoring_control_widgets.get("remote-monitoring")
                if (
                    auth_gate_forced_monitoring_off
                    and self.shared_ssh_control_path()
                    and control is not None
                    and not control.isChecked()
                ):
                    restored_monitoring = True
                    self.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", False)
                    control.setChecked(True)
                self.request_sftp_refresh(reason="initial-key-agent-auth")
                if not restored_monitoring:
                    self.activate_initial_monitoring_state()
                return
            self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", True)
            self.set_sftp_runtime_status(
                f"SFTP auto-refresh skipped: {detail}",
                state="auth-required",
            )
            control = self.monitoring_control_widgets.get("remote-monitoring")
            if control is not None and control.isChecked():
                self.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", True)
                self.setProperty("mobaBackgroundSshApplyingAuthGate", True)
                try:
                    control.setChecked(False)
                finally:
                    self.setProperty("mobaBackgroundSshApplyingAuthGate", False)
            self.set_remote_monitoring_runtime(False, immediate=False)
            self.set_remote_monitoring_status(
                f"Monitoring not started automatically: {detail}",
                state="auth-required",
            )
            if (start_runtime and profile is not None and PINNED_SMARTCARD_KEY in profile.options
                and self.background_auth_retry_attempt < 5 and ssh_control_path_for_profile(profile)):
                self.schedule_background_auth_retry(waiting_for_smartcard=True)

        def set_sftp_runtime_status(self, message: str, *, state: str) -> None:
            badge = getattr(self, "sftp_status_badge", None)
            tooltip = self._background_ssh_tooltip(message)
            if badge is not None:
                badge.setProperty("state", state)
                badge.setProperty("mobaSftpStatusBadgeState", state)
                badge.setProperty("mobaSftpStatusBadgeMessage", message)
                badge.setToolTip(tooltip)
                badge.setAccessibleDescription(message)
                status_icon = {
                    "pending": QStyle.StandardPixmap.SP_BrowserReload,
                    "refreshing": QStyle.StandardPixmap.SP_BrowserReload,
                    "ready": QStyle.StandardPixmap.SP_DialogApplyButton,
                    "error": QStyle.StandardPixmap.SP_MessageBoxWarning,
                    "auth-required": QStyle.StandardPixmap.SP_MessageBoxWarning,
                }.get(state)
                badge.setIcon(
                    _widget_style(self).standardIcon(status_icon)
                    if status_icon is not None
                    else self._sftp_status_default_icon
                )
                badge_style = _widget_style(badge)
                badge_style.unpolish(badge)
                badge_style.polish(badge)
                badge.update()
            for widget in (
                self,
                getattr(self, "browser", None),
                getattr(self, "file_table", None),
            ):
                if widget is not None:
                    widget.setProperty("mobaSftpRuntimeState", state)
                    widget.setProperty("mobaSftpRuntimeMessage", message)
            table = getattr(self, "file_table", None)
            if table is not None:
                table.setToolTip(tooltip)

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

        def generated_icon(
            self,
            size: int,
            draw: Callable[[QPainter, int], None],
            *,
            antialias: bool = True,
        ) -> QIcon:
            return QIcon(self.generated_icon_pixmap(size, draw, antialias=antialias))

        def apply_sftp_file_row_icon(
            self, item: QTreeWidgetItem, kind: str, icons: dict[tuple[str, int], QIcon],
        ) -> None:
            row_icon = gui_design_moba_sftp_file_row_icon(kind)
            item.setData(0, Qt.ItemDataRole.UserRole, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_KEY_ROLE, row_icon.icon_key)
            item.setData(0, SFTP_ROW_KIND_ROLE, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_SIZE_ROLE, row_icon.static_size)
            item.setData(0, SFTP_ROW_ICON_RENDER_ROLE, row_icon.render_source)
            key = row_icon.icon_key, row_icon.static_size
            if key not in icons:
                icons[key] = self.sftp_file_row_icon(row_icon.icon_key, size=row_icon.static_size)
            item.setIcon(0, icons[key])

        def apply_sftp_routed_file_row_metadata(
            self,
            item: QTreeWidgetItem,
            rows,
            *,
            row_index: int,
            name: str,
            selected: bool,
            source_path: str | None = None,
        ) -> None:
            routed_path = normalise_remote_path(
                source_path or self.active_remote_path
            )
            item.setData(0, SFTP_ROW_CONTRACT_KEY_ROLE, rows.key)
            item.setData(0, SFTP_ROW_ROUTE_KEY_ROLE, rows.follow_route_key)
            item.setData(0, SFTP_ROW_SOURCE_PATH_ROLE, routed_path)
            item.setData(0, SFTP_ROW_INDEX_ROLE, row_index)
            item.setData(0, SFTP_ROW_SELECTED_BY_ROUTE_ROLE, selected)
            item.setData(0, SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE, moba_sftp_terminal_folder_route(self.state).key)
            item.setToolTip(
                1,
                _safe_tooltip_html(f"{rows.row_path_property}: {routed_path}"),
            )
            item.setToolTip(2, _safe_tooltip_html(f"{rows.row_route_property}: {rows.follow_route_key}"))
            if item.text(0) != name:
                item.setText(0, name)

        def sftp_file_row_icon(self, icon_key: str, *, size: int) -> QIcon:
            return self.generated_icon(
                size,
                lambda painter, logical_size: self.draw_sftp_file_row_icon(
                    painter, icon_key, logical_size
                ),
            )

        def draw_sftp_file_row_icon(self, painter: QPainter, icon_key: str, size: int) -> None:
            outline = QColor("#343a40")
            folder = QColor("#f2c744")
            parent_folder = QColor("#f5d96a")
            file_fill = QColor("#d7dde5")
            folded = QColor("#eef2f7")
            muted = QColor("#6b7280")
            if icon_key in {"folder", "folder-up"}:
                painter.setPen(QPen(outline, 1))
                painter.setBrush(QBrush(parent_folder if icon_key == "folder-up" else folder))
                painter.drawRect(0, 4, size - 1, size - 5)
                painter.setBrush(QBrush(QColor("#ffe58a")))
                painter.drawRect(2, 2, max(6, size // 2), 3)
                if icon_key == "folder-up":
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor("#2f6fb1")))
                    mid = size // 2
                    painter.drawPolygon(QPoint(mid, 4), QPoint(mid - 3, 8), QPoint(mid + 3, 8))
                return
            painter.setPen(QPen(outline, 1))
            painter.setBrush(QBrush(file_fill))
            painter.drawRect(2, 1, size - 3, size - 2)
            painter.setBrush(QBrush(folded))
            painter.drawPolygon(QPoint(size - 5, 1), QPoint(size - 1, 5), QPoint(size - 5, 5))
            painter.setPen(QPen(muted, 1))
            painter.drawLine(4, 7, size - 4, 7)
            painter.drawLine(4, 10, size - 5, 10)

        def build_remote_monitoring(self, density) -> QFrame:
            chrome = gui_design_moba_remote_monitoring_dock_chrome()
            route = gui_design_moba_monitoring_telemetry_route()
            control_route = gui_design_moba_remote_monitoring_control_route()
            follow_control_route = gui_design_moba_follow_terminal_folder_control_route()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            metric_keys = [metric.key for metric in gui_design_moba_monitoring_metrics()]
            panel = QFrame()
            panel.setObjectName("mobaRemoteMonitoring")
            self.remote_monitoring_panel = panel
            panel.setProperty("mobaSftpMonitoringHeight", density.monitoring_height)
            panel.setProperty("mobaSftpMonitoringDividerOffset", density.monitoring_divider_offset)
            panel.setProperty("mobaSftpMonitoringMetricRowGap", density.monitoring_metric_row_gap)
            panel.setProperty("mobaRemoteMonitoringCompact", chrome.compact)
            panel.setProperty("mobaRemoteMonitoringTelemetrySurface", chrome.telemetry_surface)
            panel.setProperty("mobaRemoteMonitoringMetricKeys", metric_keys)
            panel.setProperty("mobaRemoteMonitoringVisibleMetricKeys", list(chrome.visible_metric_keys))
            panel.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            panel.setProperty("mobaMonitoringTelemetryRouteRole", route.route_role)
            panel.setProperty("mobaMonitoringTelemetryTargetBarObject", route.target_bar_object)
            panel.setProperty("mobaMonitoringTelemetryTargetCellObject", route.target_cell_object)
            panel.setProperty("mobaMonitoringTelemetryMetricCellKeys", list(route.target_metric_cell_keys))
            panel.setProperty("mobaMonitoringTelemetryIdentityCellKey", route.target_identity_cell_key)
            panel.setProperty("mobaRemoteMonitoringRefreshSeconds", chrome.refresh_seconds)
            panel.setProperty("mobaRemoteMonitoringStaticHeight", chrome.static_height)
            panel.setProperty("mobaRemoteMonitoringDividerOffset", chrome.divider_offset)
            panel.setProperty("mobaRemoteMonitoringDividerLeftInset", chrome.divider_left_inset)
            panel.setProperty("mobaRemoteMonitoringDividerRightInset", chrome.divider_right_inset)
            panel.setProperty("mobaRemoteMonitoringContentLeft", chrome.content_left)
            panel.setProperty("mobaRemoteMonitoringIconCenterX", chrome.icon_center_x)
            panel.setProperty("mobaRemoteMonitoringMetricRowGap", chrome.metric_row_gap)
            panel.setProperty("mobaRemoteMonitoringLiveControlsWidth", chrome.live_controls_width)
            panel.setProperty("mobaRemoteMonitoringCommand", self.state.monitoring_plan.printable())
            panel.setProperty("mobaRemoteMonitoringFollowPlan", self.state.follow_folder_plan.printable_batch())
            self.apply_remote_monitoring_control_route_properties(panel, control_route)
            panel.setProperty(control_route.captured_property, True)
            panel.setProperty(control_route.captured_checked_property, control_route.expected_checked)
            panel.setProperty(control_route.captured_command_property, self.state.monitoring_plan.printable())
            panel.setProperty(control_route.captured_refresh_seconds_property, chrome.refresh_seconds)
            panel.setProperty(control_route.live_checked_property, control_route.expected_checked)
            follow_plan = self.state.follow_folder_plan.printable_batch()
            self.apply_follow_terminal_folder_control_route_properties(panel, follow_control_route)
            panel.setProperty(follow_control_route.captured_property, True)
            panel.setProperty(follow_control_route.captured_checked_property, self.state.follow_terminal_folder)
            panel.setProperty(follow_control_route.captured_path_property, self.state.remote_path)
            panel.setProperty(follow_control_route.captured_plan_property, follow_plan)
            panel.setProperty(follow_control_route.live_checked_property, self.state.follow_terminal_folder)
            panel.setProperty(follow_control_route.live_path_property, self.state.remote_path)
            panel.setProperty(follow_control_route.live_plan_property, follow_plan)
            self.apply_sftp_follow_folder_route_properties(panel, follow_route)
            self.apply_sftp_terminal_folder_route_properties(panel)
            panel.setProperty(
                "mobaMonitoringControlGeometryKeys",
                [geometry.key for geometry in gui_design_moba_monitoring_control_geometry()],
            )
            panel.setFixedHeight(chrome.static_height)
            panel.setProperty("mobaRemoteMonitoringAlwaysCompact", True)
            panel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            panel.customContextMenuRequested.connect(
                self.show_remote_monitoring_context_menu
            )
            controls = QFrame(panel)
            controls.setObjectName("mobaMonitoringControls")
            self.remote_monitoring_controls = controls
            controls.setGeometry(
                0,
                0,
                chrome.live_controls_width,
                chrome.static_height,
            )
            controls.setProperty("mobaRemoteMonitoringLiveControlsWidth", chrome.live_controls_width)
            controls.setProperty("mobaRemoteMonitoringStaticHeight", chrome.static_height)
            controls.setProperty(
                "mobaMonitoringControlGeometryKeys",
                [geometry.key for geometry in gui_design_moba_monitoring_control_geometry()],
            )
            for control in gui_design_moba_monitoring_controls():
                widget = self.monitoring_control_widget(control)
                self.monitoring_control_widgets[control.key] = widget
                geometry = gui_design_moba_monitoring_control_geometry_for(control.key)
                widget.setParent(controls)
                widget.setGeometry(
                    geometry.anchor_x,
                    geometry.static_y,
                    geometry.live_width,
                    max(geometry.row_height + 4, geometry.icon_size + 4),
                )
            status = _literal_label("Monitoring ready", controls)
            status.setObjectName("mobaMonitoringStatus")
            # The two live affordances share the row above the fixed
            # follow-folder control.  Keeping them in that row avoids the
            # compact footer controls painting over one another at runtime.
            status.setGeometry(42, 29, 104, 18)
            status.setToolTip(
                "Live values replace preview telemetry after a successful SSH refresh."
            )
            self.monitoring_status_label = status
            refresh_button = QToolButton(controls)
            refresh_button.setObjectName("mobaMonitoringRefresh")
            refresh_button.setText("Refresh now")
            refresh_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            refresh_button.setIcon(
                _widget_style(self).standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
            )
            refresh_button.setGeometry(148, 27, 108, 23)
            refresh_button.clicked.connect(
                lambda _checked=False: self.request_remote_monitoring_refresh(
                    allow_prompt=True,
                )
            )
            self.monitoring_refresh_button = refresh_button
            last_refresh = _literal_label("not refreshed", controls)
            last_refresh.setObjectName("mobaMonitoringLastRefresh")
            # The timestamp is retained as a tooltip/property for automation
            # and accessibility, while the compact footer renders it inline
            # in the status label after a successful refresh.  A third visible
            # control would overlap the fixed follow-folder row.
            last_refresh.setGeometry(148, 50, 108, 19)
            last_refresh.setVisible(False)
            last_refresh.setToolTip("Last successful refresh: not refreshed")
            self.monitoring_last_refresh_label = last_refresh
            self.monitoring_detail_widgets = [
                status,
                refresh_button,
                last_refresh,
            ]
            # Keep operational feedback and the manual refresh affordance
            # visible even while monitoring is paused.  The timestamp remains
            # available through the status text, tooltip, and property so the
            # compact footer does not overlap the follow-folder checkbox.
            status.setVisible(True)
            refresh_button.setVisible(True)
            for metric in gui_design_moba_monitoring_metrics():
                label = _literal_label(self.monitoring_metric_text(metric), panel)
                label.setObjectName("mobaMonitoringMetric")
                label.setProperty("mobaMonitoringMetricKey", metric.key)
                label.setProperty("mobaMonitoringMetricVisibleInDock", metric.key in chrome.visible_metric_keys)
                label.setProperty("mobaMonitoringMetricTelemetrySurface", chrome.telemetry_surface)
                label.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
                label.setVisible(False)
            remote_control = self.monitoring_control_widgets.get("remote-monitoring")
            self.set_remote_monitoring_expanded(
                bool(remote_control is not None and remote_control.isChecked())
            )
            return panel

        @staticmethod
        def apply_remote_monitoring_control_route_properties(widget, route) -> None:
            properties = {
                "mobaRemoteMonitoringControlRouteKey": route.key,
                "mobaRemoteMonitoringControlRouteRole": route.route_role,
                "mobaRemoteMonitoringControlSourcePanelObject": route.source_panel_object,
                "mobaRemoteMonitoringControlSourceObject": route.source_control_object,
                "mobaRemoteMonitoringControlSourceKey": route.source_control_key,
                "mobaRemoteMonitoringControlSourceLabel": route.source_control_label,
                "mobaRemoteMonitoringControlSourceType": route.source_control_type,
                "mobaRemoteMonitoringControlExpectedChecked": route.expected_checked,
                "mobaRemoteMonitoringControlCommandProperty": route.command_property,
                "mobaRemoteMonitoringControlRefreshProperty": route.refresh_seconds_property,
                "mobaRemoteMonitoringControlCheckedProperty": route.checked_property,
                "mobaRemoteMonitoringControlTelemetryRouteKey": route.telemetry_route_key,
                "mobaRemoteMonitoringControlTelemetrySurface": route.telemetry_surface,
                "mobaRemoteMonitoringControlTargetBarObject": route.target_bar_object,
                "mobaRemoteMonitoringControlTargetMetricCellKeys": list(route.target_metric_cell_keys),
                "mobaRemoteMonitoringControlCapturedProperty": route.captured_property,
                "mobaRemoteMonitoringControlCapturedCheckedProperty": route.captured_checked_property,
                "mobaRemoteMonitoringControlCapturedCommandProperty": route.captured_command_property,
                "mobaRemoteMonitoringControlCapturedRefreshProperty": route.captured_refresh_seconds_property,
                route.signal_property: route.signal,
                route.handler_property: route.handler,
                route.live_checked_property: route.expected_checked,
                "mobaRemoteMonitoringControlRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_follow_terminal_folder_control_route_properties(widget, route) -> None:
            properties = {
                "mobaFollowTerminalFolderControlRouteKey": route.key,
                "mobaFollowTerminalFolderControlRouteRole": route.route_role,
                "mobaFollowTerminalFolderControlSourcePanelObject": route.source_panel_object,
                "mobaFollowTerminalFolderControlSourceObject": route.source_control_object,
                "mobaFollowTerminalFolderControlSourceKey": route.source_control_key,
                "mobaFollowTerminalFolderControlSourceLabel": route.source_control_label,
                "mobaFollowTerminalFolderControlSourceType": route.source_control_type,
                "mobaFollowTerminalFolderControlExpectedChecked": route.expected_checked,
                "mobaFollowTerminalFolderControlSourcePathProperty": route.source_path_property,
                "mobaFollowTerminalFolderControlSourcePlanProperty": route.source_plan_property,
                "mobaFollowTerminalFolderControlSourceEnabledProperty": route.source_enabled_property,
                "mobaFollowTerminalFolderControlTargetBrowserObject": route.target_browser_object,
                "mobaFollowTerminalFolderControlTargetPathObject": route.target_path_object,
                "mobaFollowTerminalFolderControlTargetTableObject": route.target_table_object,
                "mobaFollowTerminalFolderControlTargetPathProperty": route.target_path_property,
                "mobaFollowTerminalFolderControlTargetPlanProperty": route.target_plan_property,
                "mobaFollowTerminalFolderControlTargetEnabledProperty": route.target_enabled_property,
                "mobaFollowTerminalFolderControlCapturedProperty": route.captured_property,
                "mobaFollowTerminalFolderControlCapturedCheckedProperty": route.captured_checked_property,
                "mobaFollowTerminalFolderControlCapturedPathProperty": route.captured_path_property,
                "mobaFollowTerminalFolderControlCapturedPlanProperty": route.captured_plan_property,
                route.signal_property: route.signal,
                route.handler_property: route.handler,
                route.live_checked_property: route.expected_checked,
                route.live_path_property: "",
                route.live_plan_property: "",
                "mobaFollowTerminalFolderControlRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def monitoring_control_widget(self, control):
            if control.control_type == "checkbox":
                widget = QCheckBox(control.label)
                widget.setObjectName("mobaFollowTerminalFolder")
            else:
                widget = QToolButton()
                widget.setObjectName("mobaMonitoringControl")
                widget.setText(control.label)
                widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                widget.setAutoRaise(True)
            widget.setProperty("mobaMonitoringControlKey", control.key)
            widget.setProperty("mobaMonitoringControlIconKey", control.icon_key)
            widget.setProperty("mobaMonitoringControlType", control.control_type)
            widget.setProperty("mobaMonitoringControlDefaultChecked", control.checked)
            route = gui_design_moba_monitoring_telemetry_route()
            widget.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            widget.setProperty("mobaMonitoringTelemetrySurface", route.telemetry_surface)
            geometry = gui_design_moba_monitoring_control_geometry_for(control.key)
            widget.setProperty("mobaMonitoringControlStaticX", geometry.anchor_x)
            widget.setProperty("mobaMonitoringControlStaticY", geometry.static_y)
            widget.setProperty("mobaMonitoringControlIconX", geometry.icon_x)
            widget.setProperty("mobaMonitoringControlIconSize", geometry.icon_size)
            widget.setProperty("mobaMonitoringControlLabelX", geometry.label_x)
            widget.setProperty("mobaMonitoringControlLabelYOffset", geometry.label_y_offset)
            widget.setProperty("mobaMonitoringControlLabelFontSize", geometry.label_font_size)
            widget.setProperty("mobaMonitoringControlLabelBold", geometry.label_bold)
            widget.setProperty("mobaMonitoringControlCheckSize", geometry.check_size)
            widget.setProperty("mobaMonitoringControlCheckYOffset", geometry.check_y_offset)
            widget.setProperty("mobaMonitoringControlCheckmarkPoints", [list(point) for point in geometry.checkmark_points])
            widget.setProperty("mobaMonitoringControlRowHeight", geometry.row_height)
            widget.setProperty("mobaMonitoringControlLiveWidth", geometry.live_width)
            control_font = QFont()
            control_font.setPointSize(geometry.label_font_size)
            control_font.setBold(geometry.label_bold)
            control_font.setHintingPreference(
                QFont.HintingPreference.PreferFullHinting
            )
            widget.setFont(control_font)
            widget.setCheckable(True)
            widget.setChecked(self.monitoring_control_checked(control))
            widget.setToolTip(_safe_tooltip_html(self.monitoring_control_tooltip(control)))
            widget.setIcon(self.monitoring_control_icon(control.icon_key))
            widget.setIconSize(QSize(geometry.icon_size, geometry.icon_size))
            widget.setMinimumHeight(geometry.row_height)
            if control.key == "remote-monitoring":
                control_route = gui_design_moba_remote_monitoring_control_route()
                self.apply_remote_monitoring_control_route_properties(widget, control_route)
                widget.setProperty(control_route.checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_property, True)
                widget.setProperty(control_route.captured_checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_command_property, self.state.monitoring_plan.printable())
                widget.setProperty(
                    control_route.captured_refresh_seconds_property,
                    gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds,
                )
                widget.setProperty(control_route.live_checked_property, widget.isChecked())
                widget.setProperty("mobaMonitoringCommand", self.state.monitoring_plan.printable())
                widget.setProperty(
                    "mobaMonitoringRefreshSeconds",
                    gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds,
                )
                widget.toggled.connect(self.handle_moba_remote_monitoring_toggled)
            if control.key == "follow-terminal-folder":
                control_route = gui_design_moba_follow_terminal_folder_control_route()
                follow_route = gui_design_moba_sftp_follow_folder_route()
                follow_plan = self.state.follow_folder_plan.printable_batch()
                self.apply_follow_terminal_folder_control_route_properties(widget, control_route)
                widget.setProperty("mobaMonitoringFollowPlan", follow_plan)
                widget.setProperty("mobaMonitoringFollowPath", self.state.remote_path)
                widget.setProperty("mobaMonitoringFollowEnabled", self.state.follow_terminal_folder)
                widget.setProperty(control_route.captured_property, True)
                widget.setProperty(control_route.captured_checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_path_property, self.state.remote_path)
                widget.setProperty(control_route.captured_plan_property, follow_plan)
                widget.setProperty(control_route.live_checked_property, widget.isChecked())
                widget.setProperty(control_route.live_path_property, self.state.remote_path)
                widget.setProperty(control_route.live_plan_property, follow_plan)
                self.apply_sftp_follow_folder_route_properties(widget, follow_route)
                self.apply_sftp_terminal_folder_route_properties(widget)
                widget.toggled.connect(self.handle_moba_follow_terminal_folder_toggled)
            return widget

        def monitoring_control_checked(self, control) -> bool:
            if control.key == "follow-terminal-folder":
                return self.state.follow_terminal_folder
            return bool(control.checked)

        def set_remote_monitoring_expanded(self, expanded: bool) -> None:
            panel = getattr(self, "remote_monitoring_panel", None)
            if panel is None:
                return
            chrome = gui_design_moba_remote_monitoring_dock_chrome()
            status = getattr(self, "monitoring_status_label", None)
            refresh_button = getattr(self, "monitoring_refresh_button", None)
            last_refresh = getattr(self, "monitoring_last_refresh_label", None)
            if status is not None:
                status.setVisible(True)
            if refresh_button is not None:
                refresh_button.setVisible(True)
            if last_refresh is not None:
                last_refresh.setVisible(False)
            height = chrome.static_height
            panel.setFixedHeight(height)
            # ``Expanded`` is a geometry contract: the connected layout stays
            # compact even while runtime monitoring is enabled.  The separate
            # runtime-requested property carries the live toggle state.
            panel.setProperty("mobaRemoteMonitoringExpanded", False)
            panel.setProperty("mobaRemoteMonitoringRuntimeRequested", bool(expanded))
            panel.setProperty("mobaRemoteMonitoringLiveHeight", height)
            controls = getattr(self, "remote_monitoring_controls", None)
            if controls is not None:
                controls.setFixedHeight(height)
                controls.setProperty("mobaRemoteMonitoringExpanded", False)
            panel.updateGeometry()

        def set_remote_monitoring_status(
            self,
            message: str,
            *,
            state: str,
        ) -> None:
            label = getattr(self, "monitoring_status_label", None)
            if label is not None:
                label.setText(message)
                label.setProperty("state", state)
                label.setToolTip(_safe_tooltip_html(message))
                label_style = _widget_style(label)
                label_style.unpolish(label)
                label_style.polish(label)
                label.update()
            control = self.monitoring_control_widgets.get("remote-monitoring")
            if control is not None:
                control.setProperty("state", state)
                control.setProperty("mobaMonitoringStatusBadgeState", state)
                control.setProperty("mobaMonitoringStatusBadgeMessage", message)
                control.setToolTip(self._background_ssh_tooltip(message))
                control.setAccessibleDescription(message)
                status_icon = {
                    "starting": QStyle.StandardPixmap.SP_BrowserReload,
                    "refreshing": QStyle.StandardPixmap.SP_BrowserReload,
                    "live": QStyle.StandardPixmap.SP_DialogApplyButton,
                    "error": QStyle.StandardPixmap.SP_MessageBoxWarning,
                    "auth-required": QStyle.StandardPixmap.SP_MessageBoxWarning,
                }.get(state)
                control.setIcon(
                    _widget_style(self).standardIcon(status_icon)
                    if status_icon is not None
                    else self.monitoring_control_icon("monitor")
                )
                control_style = _widget_style(control)
                control_style.unpolish(control)
                control_style.polish(control)
                control.update()
            panel = getattr(self, "remote_monitoring_panel", None)
            for widget in (self, panel):
                if widget is not None:
                    widget.setProperty("mobaRemoteMonitoringRuntimeState", state)
                    widget.setProperty("mobaRemoteMonitoringRuntimeMessage", message)

        def shutdown_runtime(self) -> None:
            if self.runtime_shutting_down:
                return
            self.runtime_shutting_down = True
            self._invalidate_monitoring_request()
            self.sftp_refresh_generation += 1
            self.sftp_refresh_active_generation = 0
            self.sftp_refresh_pending = None
            self.monitoring_refresh_timer.stop()
            self.background_auth_retry_timer.stop()
            self.background_state_activation_timer.stop()
            self.sftp_refresh_timeout.stop()
            self.sftp_auth_probe_timer.stop()
            self.text_editor_timeout.stop()
            self.text_editor_auth_probe_timer.stop()
            self.text_editor_generation += 1
            self.text_editor_active_generation = 0
            self.text_editor_pending_sftp = None
            for process in (
                self.monitoring_process,
                self.sftp_refresh_process,
                self.text_editor_process,
            ):
                process.blockSignals(True)
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.kill()
                close_process = getattr(process, "close", None)
                if callable(close_process):
                    close_process()
            self._clear_background_password()
            self.setProperty("mobaRuntimeShutdown", True)
            self.setProperty("mobaRemoteMonitoringRuntimeActive", False)
            self.set_remote_monitoring_status(
                "Monitoring stopped",
                state="stopped",
            )

        def can_reuse_for_state(
            self,
            state: MobaConnectedSessionState,
        ) -> bool:
            return (
                not self.runtime_shutting_down
                and self.state.profile_name == state.profile_name
                and self.state.target == state.target
                and self.state.ssh_connection_key == state.ssh_connection_key
                and self.active_remote_path == state.remote_path
                and self.state.monitoring_plan == state.monitoring_plan
                and self.state.sftp_list_plan == state.sftp_list_plan
                and self.state.follow_folder_plan == state.follow_folder_plan
                and self.state.banner == state.banner
                and self.state.smartcard_selection
                == state.smartcard_selection
            )

        def _update_live_telemetry_panel(self, panel, live_state) -> None:
            panel.state = live_state
            panel.moba_connected_state = live_state
            cells = tuple(moba_telemetry_cells(live_state))
            existing_keys = tuple(panel.telemetry_cell_frames)
            live_keys = tuple(getattr(cell, "key", "") for cell in cells)
            telemetry_bar = panel.findChild(QFrame, "mobaTelemetryBar")
            if live_keys != existing_keys:
                can_rebuild = bool(cells) and all(
                    all(
                        hasattr(cell, attribute)
                        for attribute in (
                            "icon_key",
                            "icon_accent",
                            "icon_size",
                            "label",
                            "value",
                            "display_text",
                            "width",
                        )
                    )
                    for cell in cells
                )
                if can_rebuild:
                    hidden_keys = {
                        key
                        for key, frame in panel.telemetry_cell_frames.items()
                        if frame.property("mobaTelemetryUserVisible") is False
                    }
                    try:
                        telemetry_bar = panel.rebuild_telemetry_bar(
                            hidden_keys=hidden_keys,
                        )
                    except (AttributeError, KeyError, TypeError):
                        # A stale/headless test double must not prevent the
                        # current live snapshot from updating existing cells.
                        telemetry_bar = panel.findChild(
                            QFrame,
                            "mobaTelemetryBar",
                        )
            if telemetry_bar is None:
                return
            telemetry_bar.setProperty("mobaTelemetryDataSource", "live-ssh")
            telemetry_bar.setProperty("mobaTelemetryLive", True)
            for cell in cells:
                frame = next(
                    (
                        candidate
                        for candidate in telemetry_bar.findChildren(
                            QFrame,
                            "mobaTelemetryCell",
                        )
                        if candidate.property("mobaTelemetryKey") == cell.key
                    ),
                    None,
                )
                if frame is None:
                    continue
                frame.setProperty("mobaTelemetryDisplayText", cell.display_text)
                frame.setToolTip(
                    _safe_tooltip_html(f"{cell.label}: {cell.display_text}")
                )
                label = next(
                    (
                        candidate
                        for candidate in frame.findChildren(
                            QLabel,
                            "mobaTelemetryItem",
                        )
                        if candidate.property("mobaTelemetryKey") == cell.key
                    ),
                    None,
                )
                if label is not None:
                    rendered_text = MobaConnectedSessionPanel.telemetry_label_text(
                        label,
                        cell,
                        int(frame.property("mobaTelemetryCellWidth") or frame.width())
                        - 30,
                    )
                    label.setText(rendered_text)
                    label.setProperty(
                        "mobaTelemetryDisplayText",
                        cell.display_text,
                    )
                    label.setProperty(
                        "mobaTelemetryRenderedText",
                        rendered_text,
                    )
                    label.setToolTip(
                        _safe_tooltip_html(f"{cell.label}: {cell.display_text}")
                    )
                    label.updateGeometry()
                frame.updateGeometry()
            telemetry_bar.updateGeometry()

        def apply_live_remote_monitoring_snapshot(self, snapshot) -> bool:
            if not self.monitoring_surface_is_current():
                return False
            live_state = replace(self.state, monitoring=snapshot)
            self.state = live_state
            main_window = self.main_window()
            matching_panels: list[ConnectedSessionPanel] = []
            if main_window is not None:
                for index in range(main_window.tabs.count()):
                    candidate = main_window.tabs.widget(index)
                    if (
                        isinstance(candidate, MobaConnectedSessionPanel)
                        and candidate.state.profile_name == live_state.profile_name
                        and candidate.state.target == live_state.target
                        and candidate.state.ssh_connection_key == live_state.ssh_connection_key
                    ):
                        matching_panels.append(candidate)
            for panel in matching_panels:
                self._update_live_telemetry_panel(panel, replace(panel.state, monitoring=snapshot))
            return True

        def build_remote_monitoring_context_menu(self) -> QMenu:
            menu = QMenu(self)
            menu.setObjectName("mobaRemoteMonitoringContextMenu")
            control = self.monitoring_control_widgets.get("remote-monitoring")
            enabled_action = _required_gui_value(
                menu.addAction("Remote monitoring enabled"),
                "remote-monitoring action",
            )
            enabled_action.setCheckable(True)
            enabled_action.setChecked(
                bool(control is not None and control.isChecked())
            )
            if control is not None:
                enabled_action.toggled.connect(control.setChecked)
            refresh_action = _required_gui_value(
                menu.addAction(
                    "Refresh now",
                    lambda _checked=False: self.request_remote_monitoring_refresh(
                        allow_prompt=True,
                    ),
                ),
                "monitoring-refresh action",
            )
            refresh_action.setEnabled(control is not None)
            auth_action = _required_gui_value(
                menu.addAction(
                    "Authenticate background tools",
                    self.authenticate_background_tools,
                ),
                "monitoring-authentication action",
            )
            profile = self.profile_for_sftp_action()
            auth_action.setEnabled(
                bool(profile is not None)
                and not bool(self._background_password)
            )
            auth_action.setToolTip(
                "Load a vault credential or enter an SSH password for this session"
            )
            follow_control = self.monitoring_control_widgets.get(
                "follow-terminal-folder"
            )
            follow_action = _required_gui_value(
                menu.addAction("Follow terminal folder"),
                "follow-terminal-folder action",
            )
            follow_action.setCheckable(True)
            follow_action.setChecked(
                bool(follow_control is not None and follow_control.isChecked())
            )
            if follow_control is not None:
                follow_action.toggled.connect(follow_control.setChecked)
            menu.addSeparator()
            menu.addAction(
                "Copy monitoring command",
                lambda: _application_clipboard().setText(
                    self.state.monitoring_plan.printable()
                ),
            )
            return menu

        def show_remote_monitoring_context_menu(self, position: QPoint) -> None:
            menu = self.build_remote_monitoring_context_menu()
            menu.exec(self.remote_monitoring_panel.mapToGlobal(position))
            menu.deleteLater()

        def handle_moba_remote_monitoring_toggled(self, checked: bool) -> None:
            route = gui_design_moba_remote_monitoring_control_route()
            auth_gate_applying = bool(
                self.property("mobaBackgroundSshApplyingAuthGate")
            )
            if not checked and not auth_gate_applying:
                self.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", False)
            command = self.state.monitoring_plan.printable()
            refresh_seconds = gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds
            widgets = [
                self,
                getattr(self, "browser", None),
                getattr(self, "remote_monitoring_panel", None),
                self.monitoring_control_widgets.get(route.source_control_key),
            ]
            for widget in widgets:
                if widget is None:
                    continue
                self.apply_remote_monitoring_control_route_properties(widget, route)
                widget.setProperty(route.checked_property, bool(checked))
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_checked_property, bool(checked))
                widget.setProperty(route.captured_command_property, command)
                widget.setProperty(route.captured_refresh_seconds_property, refresh_seconds)
                widget.setProperty(route.live_checked_property, bool(checked))
                widget.setProperty(route.command_property, command)
                widget.setProperty(route.refresh_seconds_property, refresh_seconds)
                widget.setProperty("mobaRemoteMonitoringLiveEnabled", bool(checked))
            self.set_remote_monitoring_runtime(bool(checked), immediate=bool(checked))

        def follow_reported_terminal_directory(self) -> bool:
            panel = self.session_panel
            if self.runtime_shutting_down or not self.state.follow_terminal_folder or panel is None:
                return False
            pane = panel.terminal_pane
            path = pane.remote_directory
            if not path or path == self.active_remote_path or pane.property("terminalClosing"):
                return False
            if (
                pane.process.state() != QProcess.ProcessState.Running
                or pane.profile is None
                or self.profile_for_sftp_action() != pane.profile
            ):
                return False
            return self.navigate_moba_sftp_path(path, reason="terminal-folder")

        def handle_moba_follow_terminal_folder_toggled(self, checked: bool) -> None:
            self.state = replace(self.state, follow_terminal_folder=checked)
            if self.session_panel is not None:
                self.session_panel.state = self.state
                self.session_panel.moba_connected_state = self.state
            control_route = gui_design_moba_follow_terminal_folder_control_route()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            follow_plan = self.state.follow_folder_plan.printable_batch()
            widgets = [
                self,
                getattr(self, "browser", None),
                getattr(self, "path", None),
                getattr(self, "file_table", None),
                getattr(self, "remote_monitoring_panel", None),
                self.monitoring_control_widgets.get(control_route.source_control_key),
            ]
            for widget in widgets:
                if widget is None:
                    continue
                self.apply_follow_terminal_folder_control_route_properties(widget, control_route)
                self.apply_sftp_follow_folder_route_properties(widget, follow_route)
                widget.setProperty(control_route.source_enabled_property, bool(checked))
                widget.setProperty(control_route.target_enabled_property, bool(checked))
                widget.setProperty(control_route.captured_property, True)
                widget.setProperty(control_route.captured_checked_property, bool(checked))
                widget.setProperty(control_route.captured_path_property, self.state.remote_path)
                widget.setProperty(control_route.captured_plan_property, follow_plan)
                widget.setProperty(control_route.live_checked_property, bool(checked))
                widget.setProperty(control_route.live_path_property, self.state.remote_path)
                widget.setProperty(control_route.live_plan_property, follow_plan)
                widget.setProperty("mobaMonitoringFollowPath", self.state.remote_path)
                widget.setProperty("mobaMonitoringFollowPlan", follow_plan)
                widget.setProperty("mobaMonitoringFollowEnabled", bool(checked))
                widget.setProperty("mobaSftpFollowRouteEnabled", bool(checked))
                widget.setProperty("mobaSftpTerminalFolderRouteEnabled", bool(checked))
                widget.setProperty("mobaSftpRoutedRowsEnabled", bool(checked))
            if hasattr(self, "path"):
                self.path.setToolTip(
                    _safe_tooltip_html(
                        follow_plan if checked else "Follow terminal folder is disabled"
                    )
                )
            # Listings for the selected path still need to finish when follow is off.
            if checked and not self.follow_reported_terminal_directory():
                self.request_sftp_refresh(reason="follow-enabled")

        def request_sftp_refresh(self, *, reason: str = "manual") -> None:
            if self.runtime_shutting_down:
                return
            auto_refresh = reason in {"initial-key-agent-auth", "follow-enabled", "path-change", "terminal-folder"}
            if auto_refresh and self._waiting_for_shared_ssh():
                self.set_sftp_runtime_status(
                    "SFTP is waiting for the managed SSH connection",
                    state="auth-required",
                )
                return
            if not self.ensure_background_authentication_for_request():
                return
            count = int(self.property("mobaSftpRefreshRequestCount") or 0) + 1
            for widget in (
                self,
                getattr(self, "browser", None),
                getattr(self, "file_table", None),
            ):
                if widget is not None:
                    widget.setProperty("mobaSftpRefreshRequestCount", count)
                    widget.setProperty("mobaSftpRefreshLastReason", reason)
            request_path = normalise_remote_path(self.active_remote_path)
            self.sftp_refresh_generation += 1
            request_generation = self.sftp_refresh_generation
            if self.sftp_refresh_process.state() != QProcess.ProcessState.NotRunning:
                self.sftp_refresh_pending = (request_path, reason)
                self.set_sftp_runtime_status(
                    f"SFTP refresh queued for {request_path}",
                    state="pending",
                )
                self.show_sftp_status(
                    f"SFTP refresh queued for {request_path}"
                )
                return
            profile = self.profile_for_sftp_action()
            if profile is None:
                self.set_sftp_runtime_status(
                    "SFTP refresh unavailable: connected profile was not found",
                    state="error",
                )
                self.show_sftp_status(
                    "SFTP refresh unavailable: connected profile was not found"
                )
                return
            try:
                plan = build_sftp_list_plan(profile, request_path)
            except (LauncherError, ValueError) as exc:
                self.set_sftp_runtime_status(
                    f"SFTP refresh unavailable: {exc}",
                    state="error",
                )
                self.show_sftp_status(f"SFTP refresh unavailable: {exc}")
                return
            self.sftp_refresh_plan = plan
            self.sftp_refresh_active_generation = request_generation
            self.sftp_refresh_request_path = request_path
            self.sftp_refresh_output_buffer.clear()
            self.sftp_refresh_error_buffer.clear()
            refresh_message = (
                f"Refreshing SFTP listing for {profile.display_target} at {request_path}"
            )
            self.set_sftp_runtime_status(refresh_message, state="refreshing")
            self.show_sftp_status(refresh_message)
            runtime_command = openssh_command_with_overrides(
                list(plan.command),
                self.background_ssh_overrides(),
            )
            runtime_command = openssh_command_without_windows_connection_sharing(runtime_command)
            control_path = self.shared_ssh_control_path()
            if control_path:
                runtime_command = ssh_command_with_control_path(
                    runtime_command,
                    control_path,
                    master=False,
                )
            self.sftp_refresh_process.setProgram(runtime_command[0])
            self.sftp_refresh_process.setArguments(runtime_command[1:])
            self._background_auth_prompt_buffers["sftp"].clear()
            self._background_auth_prompt_complete["sftp"] = False
            self.sftp_refresh_process.start()
            self.sftp_refresh_timeout.start(10_000)

        def write_sftp_refresh_batch(self, *, force: bool = False) -> None:
            if (
                self.runtime_shutting_down
                or self.sftp_refresh_active_generation == 0
            ):
                return
            if self._background_password and not force:
                if not self.sftp_auth_probe_timer.isActive():
                    self.sftp_auth_probe_timer.start()
                return
            self.sftp_auth_probe_timer.stop()
            plan = self.sftp_refresh_plan
            if plan is None:
                return
            accepted = self._write_connected_sftp_batch(self.sftp_refresh_process, plan, "sftp")
            if accepted < 0:
                self.show_sftp_status(
                    "SFTP refresh failed: batch input was not accepted"
                )

        def _write_connected_sftp_batch(
            self, process: QProcess, plan: SftpBatchPlan, process_kind: str,
        ) -> int:
            # The credential may be submitted only before the first batch command.
            self._background_auth_prompt_complete[process_kind] = True
            payload = plan.batch_input()
            if getattr(process, "is_pty", False):
                # Closing the ConPTY input pipe can end the process before SFTP
                # consumes its console input. Exit through the batch instead.
                return process.write((payload + "quit\n").replace("\n", "\r").encode("utf-8"))
            accepted = process.write(payload.encode("utf-8"))
            process.closeWriteChannel()
            return accepted

        def read_sftp_refresh_output(self) -> None:
            payload = bytes(self.sftp_refresh_process.readAllStandardOutput())
            self._submit_background_password_if_prompt("sftp", payload)
            self.sftp_refresh_output_buffer.extend(payload)

        def read_sftp_refresh_error(self) -> None:
            payload = bytes(self.sftp_refresh_process.readAllStandardError())
            self.sftp_refresh_error_buffer.extend(payload)

        def handle_sftp_refresh_error(self, error) -> None:
            self.sftp_refresh_timeout.stop()
            self.sftp_auth_probe_timer.stop()
            request_is_current = self.sftp_refresh_request_is_current()
            self.sftp_refresh_active_generation = 0
            if request_is_current:
                self.setProperty("mobaSftpRefreshLastError", error.name)
                self.set_sftp_runtime_status(
                    f"SFTP refresh error: {error.name}",
                    state="error",
                )
                self.show_sftp_status(f"SFTP refresh error: {error.name}")
            self.schedule_pending_sftp_refresh()

        def cancel_sftp_refresh_timeout(self) -> None:
            if self.sftp_refresh_process.state() == QProcess.ProcessState.NotRunning:
                return
            self.sftp_auth_probe_timer.stop()
            self.sftp_refresh_process.kill()
            if self.sftp_refresh_request_is_current():
                self.setProperty("mobaSftpRefreshLastError", "timeout")
                self.set_sftp_runtime_status(
                    "SFTP refresh timed out after 10 seconds",
                    state="error",
                )
                self.show_sftp_status("SFTP refresh timed out after 10 seconds")

        def sftp_refresh_request_is_current(self) -> bool:
            return (
                not self.runtime_shutting_down
                and self.sftp_refresh_active_generation != 0
                and self.sftp_refresh_active_generation
                == self.sftp_refresh_generation
                and self.sftp_refresh_request_path
                == normalise_remote_path(self.active_remote_path)
            )

        def schedule_pending_sftp_refresh(self) -> None:
            pending = self.sftp_refresh_pending
            self.sftp_refresh_pending = None
            if pending is None or self.runtime_shutting_down:
                return
            pending_path, pending_reason = pending

            def start_pending() -> None:
                if (
                    not self.runtime_shutting_down
                    and normalise_remote_path(self.active_remote_path)
                    == pending_path
                ):
                    self.request_sftp_refresh(reason=pending_reason)

            QTimer.singleShot(0, start_pending)

        def handle_sftp_refresh_finished(
            self,
            exit_code: int,
            _exit_status: QProcess.ExitStatus,
        ) -> None:
            self.sftp_refresh_timeout.stop()
            self.sftp_auth_probe_timer.stop()
            request_is_current = self.sftp_refresh_request_is_current()
            self.read_sftp_refresh_output()
            self.read_sftp_refresh_error()
            self.sftp_refresh_active_generation = 0
            if not request_is_current:
                if not self.runtime_shutting_down:
                    self.show_sftp_status("SFTP refresh superseded")
                self.schedule_pending_sftp_refresh()
                return
            if exit_code != 0:
                diagnostics = (
                    self.sftp_refresh_error_buffer.decode(errors="replace").strip()
                    or self.sftp_refresh_output_buffer.decode(errors="replace")
                )
                detail = next(
                    (line.strip() for line in reversed(diagnostics.splitlines()) if line.strip()),
                    f"exit {exit_code}",
                )
                self.setProperty("mobaSftpRefreshLastError", detail)
                shared_control = self.shared_ssh_control_path()
                self.set_sftp_runtime_status(
                    (
                        f"Waiting for terminal SSH authentication: {detail[:100]}"
                        if shared_control
                        else f"SFTP refresh failed: {detail[:100]}"
                    ),
                    state="auth-required" if shared_control else "error",
                )
                self.show_sftp_status(
                    f"Waiting for terminal SSH authentication: {detail[:100]}"
                    if shared_control
                    else f"SFTP refresh failed: {detail[:100]}"
                )
                self.schedule_background_auth_retry()
                self.schedule_pending_sftp_refresh()
                return
            output = self.sftp_refresh_output_buffer.decode(errors="replace")
            entries = self.filtered_sftp_entries(
                parse_sftp_ls_output(output, directory=self.sftp_refresh_request_path)
            )
            self.apply_live_sftp_entries(
                entries,
                request_path=self.sftp_refresh_request_path,
                plan=self.sftp_refresh_plan,
            )
            self.setProperty("mobaSftpRefreshLastError", "")
            self.background_auth_retry_attempt = 0
            self.background_auth_retry_timer.stop()
            self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", False)
            self.set_sftp_runtime_status(
                f"SFTP listing refreshed: {len(entries)} entries",
                state="ready",
            )
            self.show_sftp_status(
                f"SFTP listing refreshed: {len(entries)} entries"
            )
            self.schedule_pending_sftp_refresh()

        def remember_sftp_location(self, path, entries, plan) -> None:
            self.state = replace(
                self.state,
                remote_path=path,
                file_entries=entries,
                sftp_list_plan=plan,
                follow_folder_plan=plan,
            )
            if self.session_panel is not None:
                self.session_panel.state = self.state
                self.session_panel.moba_connected_state = self.state

        def apply_live_sftp_entries(
            self,
            entries,
            *,
            request_path: str,
            plan,
        ) -> None:
            entries = self.filtered_sftp_entries(entries)
            selected_path = normalise_remote_path(request_path)
            self.remember_sftp_location(selected_path, entries, plan)
            self.populate_sftp_file_table(entries, selected_path)
            self.apply_sftp_follow_folder_route_properties(
                self.file_table,
                gui_design_moba_sftp_follow_folder_route(),
            )
            self.update_sftp_action_states()

        def populate_sftp_file_table(self, entries, source_path: str) -> None:
            density = gui_design_moba_sftp_dock_layout()
            chrome = gui_design_moba_sftp_browser_chrome()
            routed_rows = gui_design_moba_sftp_routed_file_rows()
            row_size = QSize(0, density.file_row_height)
            # Reuse the current display's icons only for this batch of rows.
            icons: dict[tuple[str, int], QIcon] = {}
            parent_item = QTreeWidgetItem([chrome.parent_row_label, "", ""])
            self.apply_sftp_file_row_icon(parent_item, chrome.parent_row_kind, icons)
            self.apply_sftp_routed_file_row_metadata(
                parent_item,
                routed_rows,
                row_index=0,
                name=chrome.parent_row_label,
                selected=True,
                source_path=source_path,
            )
            parent_item.setSizeHint(0, row_size)
            parent_item.setToolTip(0, "parent directory")
            items = [parent_item]
            for row_index, entry in enumerate(entries, start=1):
                item = QTreeWidgetItem(
                    [entry.name, str(entry.size_kb), entry.modified]
                )
                self.apply_sftp_file_row_icon(item, entry.kind, icons)
                self.apply_sftp_routed_file_row_metadata(
                    item,
                    routed_rows,
                    row_index=row_index,
                    name=entry.name,
                    selected=False,
                    source_path=source_path,
                )
                item.setSizeHint(0, row_size)
                item.setToolTip(
                    0,
                    _safe_tooltip_html(f"{entry.kind}: {entry.name}"),
                )
                items.append(item)
            self.file_table.clear()
            self.file_table.addTopLevelItems(items)
            parent_item.setSelected(True)
            self.file_table.setCurrentItem(parent_item)

        def monitoring_control_tooltip(self, control) -> str:
            if control.key == "follow-terminal-folder":
                return f"{control.tooltip}\n{self.state.follow_folder_plan.printable_batch()}"
            if control.key == "remote-monitoring":
                auth_detail = self.background_ssh_auth_detail()
                return (
                    f"{control.tooltip}\n{self.state.monitoring_plan.printable()}\n"
                    f"{auth_detail}"
                )
            return control.tooltip

        def monitoring_metric_text(self, metric) -> str:
            monitoring = self.state.monitoring
            if metric.source == "cpu_percent":
                value = (
                    "Unavailable"
                    if monitoring.cpu_percent is None
                    else f"{monitoring.cpu_percent}%"
                )
            elif metric.source == "memory_label":
                value = monitoring.memory_label or "Unavailable"
            elif metric.source == "disk_label":
                value = monitoring.disk_label or "Unavailable"
            elif metric.source == "network_pair":
                value = (
                    "Unavailable"
                    if monitoring.net_up_mbps is None
                    or monitoring.net_down_mbps is None
                    else (
                        f"{monitoring.net_up_mbps:.2f}/"
                        f"{monitoring.net_down_mbps:.2f} Mb/s"
                    )
                )
            elif metric.source == "load_average":
                value = monitoring.load_average or "Unavailable"
            elif metric.source == "process_count":
                value = (
                    "Unavailable"
                    if monitoring.process_count is None
                    else str(monitoring.process_count)
                )
            else:
                value = "Unavailable"
            return f"{metric.label} {value}".strip()

        def update_sftp_action_states(self, *_args) -> None:
            selected = self.file_table.currentItem() if hasattr(self, "file_table") else None
            selected_name = selected.text(0).strip() if selected is not None else ""
            selected_kind = (
                str(selected.data(0, SFTP_ROW_KIND_ROLE) or "") if selected is not None else ""
            )
            download_ready = selected_kind in {"file", "dir"} and selected_name not in {"", ".."}
            profile = self.profile_for_sftp_action()
            sftp_ready = bool(
                profile is not None
                and profile.protocol.lower().strip() in {"ssh", "sftp"}
                and profile.host
            )
            tooltips = {action.key: action.tooltip for action in gui_design_moba_sftp_dock_actions()}
            for action_key, button in getattr(self, "sftp_action_buttons", {}).items():
                operational = action_key in self.OPERATIONAL_ACTIONS
                transfer_action = action_key in {"download", "upload", "new-folder"}
                enabled = operational and (not transfer_action or sftp_ready) and (
                    action_key != "download" or download_ready
                )
                button.setEnabled(enabled)
                button.setProperty("mobaSftpActionOperational", operational)
                button.setProperty("mobaSftpActionRuntimeEnabled", enabled)
                if not sftp_ready and operational and transfer_action:
                    button.setToolTip("Connect an SSH/SFTP profile before using this action")
                elif action_key == "download" and operational and not download_ready:
                    button.setToolTip("Select a remote file or directory to download")
                elif operational and transfer_action:
                    button.setToolTip(tooltips[action_key])
            transfer_actions = getattr(self, "sftp_transfer_menu_actions", {})
            download_menu_action = transfer_actions.get("download")
            upload_menu_action = transfer_actions.get("upload")
            if download_menu_action is not None:
                download_menu_action.setEnabled(
                    bool(self.sftp_action_buttons.get("download") is not None
                         and self.sftp_action_buttons["download"].isEnabled())
                )
            if upload_menu_action is not None:
                upload_menu_action.setEnabled(
                    bool(self.sftp_action_buttons.get("upload") is not None
                         and self.sftp_action_buttons["upload"].isEnabled())
                )

        def handle_moba_sftp_path_entered(self) -> None:
            self.navigate_moba_sftp_path(self.path.text())

        def navigate_moba_sftp_path(self, raw_path: str, *, reason: str = "path-change") -> bool:
            try:
                normalized = posixpath.normpath(normalise_remote_path(raw_path))
                if not normalized.startswith("/"):
                    normalized = f"/{normalized}"
                if normalized != self.active_remote_path:
                    profile = self.profile_for_sftp_action()
                    if profile is not None:
                        plan = build_sftp_list_plan(profile, normalized)
                        self.remember_sftp_location(normalized, (), plan)
            except (LauncherError, ValueError) as exc:
                self.path.setText(self.active_remote_path)
                self.path.selectAll()
                self.path.setProperty("mobaSftpPathNavigationError", str(exc))
                self.show_sftp_status(f"SFTP path rejected: {exc}")
                return False
            if normalized != self.active_remote_path and hasattr(self, "file_table"):
                self.file_table.clear()
            self.active_remote_path = normalized
            self.path.setText(normalized)
            navigation_count = int(self.path.property("mobaSftpPathNavigationCount") or 0) + 1
            route_widgets = (
                self,
                getattr(self, "browser", None),
                self.path,
                getattr(self, "file_table", None),
            )
            for widget in route_widgets:
                if widget is None:
                    continue
                widget.setProperty("mobaSftpLivePath", normalized)
                widget.setProperty("mobaSftpPathNavigationCount", navigation_count)
                widget.setProperty("mobaSftpPathNavigationError", "")
                widget.setProperty("mobaSftpFollowRoutePath", normalized)
                widget.setProperty("mobaSftpTerminalFolderRoutePath", normalized)
                widget.setProperty("mobaConnectedRouteRemotePath", normalized)
            if hasattr(self, "sftp_transfer_queue"):
                self.sftp_transfer_queue.setText(f"Path: {normalized}")
            self.show_sftp_status(f"SFTP path: {normalized}")
            self.request_sftp_refresh(reason=reason)
            return True

        def selected_sftp_item(self) -> tuple[str, str] | None:
            item = self.file_table.currentItem() if hasattr(self, "file_table") else None
            if item is None:
                return None
            name = item.text(0).strip()
            kind = str(item.data(0, SFTP_ROW_KIND_ROLE) or "")
            if not name or name == ".." or kind not in {"file", "dir"}:
                return None
            return name, kind

        def sftp_remote_path_for_item(self, item: QTreeWidgetItem | None) -> str:
            if item is None:
                return self.active_remote_path
            name = item.text(0).strip()
            kind = str(item.data(0, SFTP_ROW_KIND_ROLE) or "")
            if name == ".." or kind == "parent-dir":
                return str(PurePosixPath(self.active_remote_path).parent)
            return str(PurePosixPath(self.active_remote_path) / name)

        def open_sftp_context_item(self, item: QTreeWidgetItem | None) -> None:
            if item is None:
                return
            name = item.text(0).strip()
            kind = str(item.data(0, SFTP_ROW_KIND_ROLE) or "")
            if name == ".." or kind in {"dir", "parent-dir"}:
                self.navigate_moba_sftp_path(self.sftp_remote_path_for_item(item))
                return
            self.handle_moba_text_editor_open_from_item(item, 0)

        def copy_sftp_context_path(self, item: QTreeWidgetItem | None) -> None:
            path = self.sftp_remote_path_for_item(item)
            _application_clipboard().setText(path)
            self.show_sftp_status(f"Copied remote path: {path}")

        def build_sftp_context_menu(
            self,
            item: QTreeWidgetItem | None = None,
        ) -> QMenu:
            if item is not None:
                self.file_table.setCurrentItem(item)
                item.setSelected(True)
            selected = item or self.file_table.currentItem()
            menu_path = self.active_remote_path

            def for_current_listing(action, *args):
                if not self.runtime_shutting_down and self.active_remote_path == menu_path and self.file_table.currentItem() is selected:
                    action(*args)

            kind = (
                str(selected.data(0, SFTP_ROW_KIND_ROLE) or "")
                if selected is not None
                else ""
            )
            name = selected.text(0).strip() if selected is not None else ""
            open_ready = bool(selected is not None and name)
            transfer_ready = kind in {"file", "dir"} and name not in {"", ".."}
            menu = QMenu(self.file_table)
            menu.setObjectName("mobaSftpContextMenu")
            open_action = _required_gui_value(
                menu.addAction(
                    "Open" if kind == "file" else "Open folder",
                    lambda: for_current_listing(self.open_sftp_context_item, selected),
                ),
                "SFTP open action",
            )
            open_action.setEnabled(open_ready)
            menu.addSeparator()
            download_action = _required_gui_value(
                menu.addAction(
                    "Download",
                    lambda: for_current_listing(self.show_moba_sftp_toolbar_action, "download"),
                ),
                "SFTP download action",
            )
            download_action.setEnabled(transfer_ready)
            menu.addAction(
                "Upload here",
                lambda: for_current_listing(self.show_moba_sftp_toolbar_action, "upload"),
            )
            copy_action = _required_gui_value(
                menu.addAction(
                    "Copy remote path",
                    lambda: for_current_listing(self.copy_sftp_context_path, selected),
                ),
                "SFTP copy-path action",
            )
            copy_action.setEnabled(open_ready)
            menu.addSeparator()
            menu.addAction(
                "Parent folder",
                lambda: for_current_listing(self.show_moba_sftp_toolbar_action, "parent-folder"),
            )
            auth_action = _required_gui_value(
                menu.addAction(
                    "Authenticate background tools",
                    self.authenticate_background_tools,
                ),
                "SFTP authenticate action",
            )
            profile = self.profile_for_sftp_action()
            auth_action.setEnabled(
                bool(profile is not None)
                and not bool(self._background_password)
            )
            auth_action.setToolTip(
                "Load a vault credential or enter an SSH password for this session"
            )
            menu.addAction(
                "Refresh listing",
                lambda: self.request_sftp_refresh(reason="context-menu"),
            )
            menu.addAction(
                "Reconnect",
                lambda: self.show_moba_sftp_toolbar_action("connect"),
            )
            menu.addAction(
                "Focus terminal",
                lambda: self.show_moba_sftp_toolbar_action("terminal"),
            )
            return menu

        def show_sftp_context_menu(self, position: QPoint) -> None:
            item = self.file_table.itemAt(position)
            if item is not None:
                self.file_table.setCurrentItem(item)
            menu = self.build_sftp_context_menu(item)
            viewport = _required_gui_value(
                self.file_table.viewport(),
                "SFTP file table viewport",
            )
            menu.exec(viewport.mapToGlobal(position))
            menu.deleteLater()

        def profile_for_sftp_action(self) -> Profile | None:
            main_window = self.main_window()
            if main_window is None:
                return None
            profile = main_window.profile_by_name(self.state.profile_name)
            if profile is None or ssh_connection_key(profile) != self.state.ssh_connection_key:
                return None
            return profile

        def show_sftp_status(self, message: str) -> None:
            main_window = self.main_window()
            if main_window is None:
                return
            status_bar = main_window.statusBar()
            if status_bar is not None:
                status_bar.showMessage(message)
            main_window.log.append(message)

        def prepare_sftp_queue_command(self, profile: Profile, command: list[str]) -> list[str]:
            if self.runtime_shutting_down or self.profile_for_sftp_action() != profile:
                raise ValueError("the connected SSH profile changed")
            control_path = self.shared_ssh_control_path()
            if control_path:
                return ssh_command_with_control_path(command, control_path, master=False)
            return openssh_command_without_windows_connection_sharing(command)

        def open_moba_sftp_transfer_workflow(self, action_key: str) -> bool:
            main_window = self.main_window()
            profile = self.profile_for_sftp_action()
            if profile is None or main_window is None:
                self.show_sftp_status("SFTP transfer unavailable: connected profile was not found")
                return False
            if action_key == "download":
                selected = self.selected_sftp_item()
                if selected is None:
                    self.show_sftp_status("Select a remote file or directory to download")
                    return False
                name, kind = selected
                remote_path = str(PurePosixPath(self.active_remote_path) / name)
                arguments = ["get", *(["-r"] if kind == "dir" else []), remote_path, f"./{name}"]
            else:
                local_path, _selected_filter = QFileDialog.getOpenFileName(
                    self,
                    "Select local file to upload",
                    "",
                    "All files (*)",
                )
                if not local_path:
                    self.show_sftp_status("SFTP upload cancelled")
                    return False
                remote_path = str(PurePosixPath(self.active_remote_path) / Path(local_path).name)
                arguments = ["put", local_path, remote_path]
            operation = format_transfer_item_spec(arguments)
            dialog = main_window.create_transfer_queue_dialog(
                profile, prepare_command=partial(self.prepare_sftp_queue_command, profile)
            )
            dialog.operations.setPlainText(operation)
            dialog.refresh_queue_preview()
            dialog.run_queue()
            result = dialog.exec()
            if result == QDialog.DialogCode.Accepted:
                plan = dialog.queue_plan()
                main_window.log.append(f"QUEUE: {plan.printable()}")
            self.show_sftp_status(
                f"SFTP {action_key} workflow {'completed' if result == QDialog.DialogCode.Accepted else 'closed'}"
            )
            return True

        def open_moba_sftp_new_folder_workflow(self) -> bool:
            main_window = self.main_window()
            profile = self.profile_for_sftp_action()
            if self.runtime_shutting_down or main_window is None or profile is None:
                return False
            parent_path = self.active_remote_path
            name, accepted = QInputDialog.getText(
                self, "New remote folder", "Name of the folder to create"
            )
            if not accepted:
                return True
            if (
                not name.strip()
                or not name.isprintable()
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
            ):
                self.show_sftp_status("Enter a single remote folder name")
                return True
            remote_path = str(PurePosixPath(parent_path) / name)

            def prepare_command(command: list[str]) -> list[str]:
                command = openssh_command_with_overrides(
                    command, {"BatchMode": "yes", "ConnectTimeout": "5", "StrictHostKeyChecking": "yes"},
                )
                return self.prepare_sftp_queue_command(profile, command)

            def refresh_created_folder(item: SftpQueueItem) -> None:
                if (
                    item.action == "mkdir"
                    and item.remote_path == remote_path
                    and self.active_remote_path == parent_path
                ):
                    self.request_sftp_refresh(reason="new-folder")

            operation = format_transfer_item_spec(["mkdir", remote_path])
            dialog = main_window.create_transfer_queue_dialog(
                profile,
                prepare_command=prepare_command,
                on_item_completed=refresh_created_folder,
            )
            dialog.operations.setPlainText(operation)
            dialog.refresh_queue_preview()
            dialog.exec()
            return True

        def reconnect_moba_sftp_session(self) -> bool:
            main_window = self.main_window()
            if main_window is None:
                self.show_sftp_status("Reconnect unavailable: main window is unavailable")
                return False
            current = main_window.tabs.currentWidget()
            panes = main_window.terminal_panes_in(current) if current is not None else []
            pane = next(
                (
                    item
                    for item in panes
                    if item.profile is not None and item.profile.name == self.state.profile_name
                ),
                panes[0] if panes else None,
            )
            if pane is None:
                self.show_sftp_status("Reconnect unavailable: no terminal pane is attached")
                return False
            pane.restart()
            self._focus_sftp_terminal_output(pane.output)
            self.show_sftp_status(f"Reconnecting {self.state.profile_name}")
            return True

        @staticmethod
        def _focus_sftp_terminal_output(output: QWidget) -> None:
            output.setProperty("mobaTerminalFocusRequested", True)
            output.setFocus(Qt.FocusReason.OtherFocusReason)
            # QWidget's setFocus() slot uses OtherFocusReason. Qt drops the
            # queued call if closing the tab destroys its receiver first.
            QMetaObject.invokeMethod(output, "setFocus", Qt.ConnectionType.QueuedConnection)

        def focus_moba_sftp_terminal(self) -> bool:
            main_window = self.main_window()
            pane = main_window.active_terminal_pane() if main_window is not None else None
            if pane is None:
                self.show_sftp_status("Terminal unavailable: no active session pane")
                return False
            self._focus_sftp_terminal_output(pane.output)
            self.show_sftp_status(f"Terminal focused at {self.active_remote_path}")
            return True

        def dispatch_moba_sftp_toolbar_action(self, action_key: str) -> bool:
            if bool(self.property("mobaSftpToolbarRouteSuppressDialog")):
                return True
            if action_key == "parent-folder":
                parent = str(PurePosixPath(self.active_remote_path).parent)
                return self.navigate_moba_sftp_path(parent)
            if action_key in {"download", "upload"}:
                return self.open_moba_sftp_transfer_workflow(action_key)
            if action_key == "new-folder":
                return self.open_moba_sftp_new_folder_workflow()
            if action_key == "connect":
                return self.reconnect_moba_sftp_session()
            if action_key == "tools":
                main_window = self.main_window()
                if main_window is None:
                    return False
                main_window.show_moba_tools_status()
                return True
            if action_key == "terminal":
                return self.focus_moba_sftp_terminal()
            return False

        def show_moba_sftp_toolbar_action(self, action_key: str) -> None:
            action = next(
                (item for item in gui_design_moba_sftp_dock_actions() if item.key == action_key),
                None,
            )
            if action is None:
                return
            route = gui_design_moba_sftp_toolbar_action_route()
            action_index = self.moba_sftp_toolbar_action_index(route, action.key)
            operational = action.key in self.OPERATIONAL_ACTIONS
            status_value = route.action_statuses[action_index] if operational else "unavailable"
            queue = getattr(self, "sftp_transfer_queue", None)
            if queue is not None:
                queue.setText(f"Queue: {action.label} ({status_value})")
            clicked_button = getattr(self, "sftp_action_buttons", {}).get(action.key)
            route_widgets = (
                self,
                getattr(self, "browser", None),
                getattr(self, "toolbar", None),
                getattr(self, "path", None),
                getattr(self, "file_table", None),
                queue,
                clicked_button,
            )
            for route_widget in route_widgets:
                if route_widget is None:
                    continue
                self.apply_sftp_toolbar_action_route_properties(
                    route_widget,
                    route,
                    triggered=True,
                    action_key=action.key,
                    status=status_value,
                )
                route_widget.setProperty("mobaSftpToolbarRouteLastActionKey", action.key)
            if not operational:
                self.show_sftp_status(
                    f"SFTP {action.label} unavailable: "
                    f"{self.UNAVAILABLE_ACTION_DETAILS.get(action.key, action.tooltip)}"
                )
                return
            try:
                completed = self.dispatch_moba_sftp_toolbar_action(action.key)
            except CommandSafetyError as exc:
                self.show_sftp_status(f"SFTP {action.label}: {exc}")
                return
            if not completed:
                self.show_sftp_status(f"SFTP {action.label} did not complete")

        def build_sftp_transfer_menu_button(self) -> QToolButton:
            """Expose a WinSCP/FileZilla-style transfer action selector.

            The connected dock already has individual upload/download toolbar
            actions and a context menu.  A single labelled selector makes the
            same workflows discoverable without relying on tiny icon-only
            buttons or a right click, while still routing through the existing
            guarded SFTP queue implementation.
            """

            button = QToolButton()
            button.setObjectName("mobaSftpTransferMenu")
            button.setText("Transfer")
            button.setAccessibleName("File transfer actions")
            button.setToolTip(
                "Choose a WinSCP/FileZilla-style upload or download workflow"
            )
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setIcon(
                self.sftp_action_icon("download", "#2f84d8", size=16)
            )
            button.setIconSize(QSize(16, 16))
            button.setFixedHeight(24)
            button.setMinimumWidth(72)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            menu.setObjectName("mobaSftpTransferMenuPopup")
            download = _required_gui_value(
                menu.addAction(
                    "Download selected…",
                    lambda: self.show_moba_sftp_toolbar_action("download"),
                ),
                "SFTP transfer download action",
            )
            upload = _required_gui_value(
                menu.addAction(
                    "Upload files…",
                    lambda: self.show_moba_sftp_toolbar_action("upload"),
                ),
                "SFTP transfer upload action",
            )
            menu.addSeparator()
            open_browser = _required_gui_value(
                menu.addAction(
                    "Refresh remote listing",
                    lambda: self.request_sftp_refresh(reason="transfer-menu"),
                ),
                "SFTP transfer refresh action",
            )
            open_browser.setToolTip(
                "Refresh the remote folder before choosing a transfer"
            )
            auth_action = _required_gui_value(
                menu.addAction(
                    "Authenticate background tools",
                    self.authenticate_background_tools,
                ),
                "SFTP transfer authenticate action",
            )
            profile = self.profile_for_sftp_action()
            auth_action.setEnabled(
                bool(profile is not None)
                and not bool(self._background_password)
            )
            auth_action.setToolTip(
                "Load a vault credential or enter an SSH password for this session"
            )
            self.sftp_transfer_menu_actions = {
                "download": download,
                "upload": upload,
                "refresh": open_browser,
                "authenticate": auth_action,
            }
            button.setMenu(menu)
            self.sftp_transfer_menu_button = button
            return button

        def tool_button(self, action, density) -> QToolButton:
            geometry = gui_design_moba_sftp_toolbar_action_geometry_for(action.key)
            route = gui_design_moba_sftp_toolbar_action_route()
            button = QToolButton()
            button.setObjectName("mobaSftpAction")
            button.setProperty("mobaSftpActionKey", action.key)
            button.setProperty("mobaSftpIconKey", action.icon_key)
            button.setProperty("mobaSftpActionGroupKey", action.group_key)
            button.setProperty("mobaSftpActionSeparatorAfter", action.separator_after)
            button.setProperty("mobaSftpActionStaticX", geometry.button_x)
            button.setProperty("mobaSftpActionStaticY", geometry.button_y)
            button.setProperty("mobaSftpActionButtonSize", geometry.button_size)
            button.setProperty("mobaSftpActionIconX", geometry.icon_x)
            button.setProperty("mobaSftpActionIconY", geometry.icon_y)
            button.setProperty("mobaSftpActionIconSize", geometry.icon_size)
            button.setProperty("mobaSftpActionSeparatorX", geometry.separator_x)
            operational = action.key in self.OPERATIONAL_ACTIONS
            button.setProperty("mobaSftpActionOperational", operational)
            button.setEnabled(operational)
            self.apply_sftp_toolbar_action_route_properties(button, route, action_key=action.key)
            button.setText(action.label)
            button.setToolTip(
                action.tooltip
                if operational
                else self.UNAVAILABLE_ACTION_DETAILS.get(action.key, action.tooltip)
            )
            button.setIcon(self.sftp_action_icon(action.icon_key, action.color, size=geometry.icon_size))
            button.setIconSize(QSize(geometry.icon_size, geometry.icon_size))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(geometry.button_size, geometry.button_size))
            button.clicked.connect(lambda _checked=False, action_key=action.key: self.show_moba_sftp_toolbar_action(action_key))
            return button

        def toolbar_separator(self, action, density) -> QFrame:
            separator = QFrame()
            separator.setObjectName("mobaSftpToolbarSeparator")
            separator.setProperty("mobaSftpSeparatorAfterActionKey", action.key)
            separator.setProperty("mobaSftpSeparatorGroupKey", action.group_key)
            separator.setProperty("mobaSftpSeparatorWidth", density.toolbar_separator_width)
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            separator.setFixedWidth(density.toolbar_separator_width)
            return separator

        def sftp_action_icon(self, icon_key: str, fill: str, *, size: int = 20) -> QIcon:
            return self.generated_icon(
                size,
                lambda painter, logical_size: self.draw_sftp_action_icon(
                    painter, icon_key, QColor(fill), logical_size
                ),
            )

        def draw_sftp_action_icon(self, painter: QPainter, icon_key: str, fill: QColor, size: int) -> None:
            white = QColor("#ffffff")
            dark = QColor("#101010")
            yellow = QColor("#ffd866")
            blue = QColor("#2f6fb1")
            mid = size // 2

            def pen(color: QColor, width: int = 1) -> None:
                painter.setPen(QPen(color, width))

            def brush(color: QColor) -> None:
                painter.setBrush(QBrush(color))

            brush(fill)
            pen(QColor("#303030"))
            painter.drawRect(1, 1, size - 2, size - 2)

            if icon_key in {"parent-folder", "new-folder"}:
                brush(yellow)
                pen(dark)
                painter.drawRect(4, 8, size - 7, size - 7)
                painter.drawRect(5, 6, 7, 4)
                if icon_key == "parent-folder":
                    brush(blue)
                    pen(blue)
                    painter.drawPolygon(
                        QPolygon(
                            [
                                QPoint(mid, 5),
                                QPoint(mid - 4, 10),
                                QPoint(mid + 4, 10),
                            ]
                        )
                    )
                    painter.drawRect(mid - 1, 9, 2, 6)
                else:
                    pen(QColor("#1c7a38"), 2)
                    painter.drawLine(mid, 8, mid, size - 5)
                    painter.drawLine(mid - 4, 12, mid + 4, 12)
            elif icon_key in {"download", "upload"}:
                direction = 1 if icon_key == "download" else -1
                pen(white, 2)
                painter.drawLine(mid, 5 if direction == 1 else 10, mid, 13 if direction == 1 else 16)
                if direction == 1:
                    painter.drawPolygon(
                        QPolygon(
                            [
                                QPoint(mid - 4, 12),
                                QPoint(mid + 4, 12),
                                QPoint(mid, 17),
                            ]
                        )
                    )
                else:
                    painter.drawPolygon(
                        QPolygon(
                            [
                                QPoint(mid - 4, 9),
                                QPoint(mid + 4, 9),
                                QPoint(mid, 4),
                            ]
                        )
                    )
                painter.drawRect(5, 15, size - 10, 2)
            elif icon_key == "connect":
                brush(QColor("#55cc7a"))
                pen(white, 2)
                painter.drawEllipse(4, 4, size - 8, size - 8)
                painter.drawLine(mid, 5, mid, mid)
            elif icon_key == "new-file":
                brush(QColor("#d7dde5"))
                pen(dark)
                painter.drawRect(5, 4, size - 8, size - 6)
                pen(QColor("#1c7a38"), 2)
                painter.drawLine(mid, 8, mid, size - 6)
                painter.drawLine(mid - 4, 12, mid + 4, 12)
            elif icon_key == "delete":
                pen(white, 2)
                painter.drawLine(5, 5, size - 5, size - 5)
                painter.drawLine(size - 5, 5, 5, size - 5)
            elif icon_key == "ascii-mode":
                pen(white, 1)
                painter.drawText(5, 15, "A")
            elif icon_key == "split-view":
                pen(white, 2)
                painter.drawRect(5, 5, size - 10, size - 10)
                painter.drawLine(mid, 5, mid, size - 5)
            elif icon_key == "tools":
                pen(white, 2)
                painter.drawLine(5, 5, size - 6, size - 6)
                painter.drawLine(size - 6, 5, 6, size - 5)
            elif icon_key == "terminal":
                brush(QColor("#111111"))
                pen(QColor("#d7d7d7"))
                painter.drawRect(4, 5, size - 8, size - 9)
                pen(QColor("#35d7c7"), 2)
                painter.drawLine(7, 9, 11, 12)
                painter.drawLine(11, 12, 7, 15)

        def monitoring_control_icon(self, icon_key: str, *, size: int = 20) -> QIcon:
            def draw(painter: QPainter, logical_size: int) -> None:
                cyan = QColor("#35d7c7")
                dark = QColor("#101010")
                painter.setPen(QPen(cyan, 1))
                painter.setBrush(QBrush(dark))
                if icon_key == "monitor":
                    painter.drawRect(3, 4, logical_size - 6, logical_size - 8)
                    painter.setPen(QPen(cyan, 2))
                    painter.drawLine(6, 12, 9, 8)
                    painter.drawLine(9, 8, 12, 14)
                    painter.drawLine(12, 14, 15, 7)
                    painter.drawLine(logical_size // 2, logical_size - 4, logical_size // 2, logical_size - 2)
                    painter.drawLine(6, logical_size - 2, logical_size - 6, logical_size - 2)
                elif icon_key == "follow-folder":
                    painter.setBrush(QBrush(QColor("#ffd866")))
                    painter.setPen(QPen(QColor("#303030"), 1))
                    painter.drawRect(3, 8, logical_size - 6, logical_size - 7)
                    painter.drawRect(4, 6, 7, 4)
                    painter.setPen(QPen(QColor("#1c7a38"), 2))
                    painter.drawLine(logical_size - 8, logical_size - 7, logical_size - 5, logical_size - 4)
                    painter.drawLine(logical_size - 5, logical_size - 4, logical_size - 2, logical_size - 10)
                else:
                    painter.drawEllipse(4, 4, logical_size - 8, logical_size - 8)

            return self.generated_icon(size, draw)

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

    MobaConnectedSessionPanel = create_connected_terminal_class(services)
    return MobaSftpDock, MobaConnectedSessionPanel
