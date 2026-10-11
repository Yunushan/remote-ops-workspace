from __future__ import annotations

import difflib
import hashlib
import ntpath
import os
import posixpath
import re
import shlex
import sys
import time
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol

from PyQt6.QtCore import (
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
    QSyntaxHighlighter,
    QTextCharFormat,
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
    QSizePolicy,
    QSplitter,
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

from .file_transfer import (
    SftpBatchPlan,
    SftpQueuePlan,
    build_sftp_get_plan,
    build_sftp_list_plan,
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
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
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
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_terminal_transcript_row_geometry,
)
from .gui_processes import _background_process
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value, _safe_tooltip_html
from .moba_connected import (
    MobaConnectedSessionState,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_text_editor_route,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
    moba_telemetry_cells,
    normalise_remote_path,
    parse_remote_monitoring_output,
    parse_sftp_ls_output,
)
from .moba_text import (
    MobaTextEditorTabPlan,
    build_moba_text_editor_tab_plan,
    prepare_managed_edit_cache,
    write_text_document,
)
from .models import Profile
from .terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    ssh_command_with_control_path,
)


if TYPE_CHECKING:
    class ConnectedSftpDock(QFrame):
        state: MobaConnectedSessionState

        @abstractmethod
        def __init__(self, state: MobaConnectedSessionState) -> None: ...
        @abstractmethod
        def main_window(self) -> ConnectedMainWindow | None: ...
        @abstractmethod
        def can_reuse_for_state(self, state: MobaConnectedSessionState) -> bool: ...
        @abstractmethod
        def initialize_background_state(self) -> None: ...
        @abstractmethod
        def schedule_background_state_activation(self, delay_ms: int = 0) -> None: ...
        @abstractmethod
        def shutdown_runtime(self) -> None: ...

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
else:
    ConnectedSftpDock = QFrame
    ConnectedSessionPanel = QWidget


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
    def create_transfer_queue_dialog(self, profile: Profile) -> ConnectedTransferQueue: ...
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
    _literal_message_box = services.literal_message_box
    _widget_style = services.widget_style

    SFTP_ROW_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 41
    SFTP_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 42
    SFTP_ROW_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 43
    SFTP_ROW_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 44
    SFTP_ROW_CONTRACT_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 45
    SFTP_ROW_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 46
    SFTP_ROW_SOURCE_PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 47
    SFTP_ROW_INDEX_ROLE = int(Qt.ItemDataRole.UserRole) + 48
    SFTP_ROW_SELECTED_BY_ROUTE_ROLE = int(Qt.ItemDataRole.UserRole) + 49
    SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 50


    class MobaTextEditorHighlighter(QSyntaxHighlighter):
        def __init__(self, document, syntax: str) -> None:
            super().__init__(document)
            self.set_syntax(syntax)

        def set_syntax(self, syntax: str) -> None:
            self.syntax = syntax
            self.patterns = self.patterns_for_syntax(syntax)
            self.rehighlight()

        @staticmethod
        def patterns_for_syntax(syntax: str) -> list[tuple[str, str]]:
            common = [
                (r"(?m)#.*$", "#6a9955"),
                (r"(?m)//.*$", "#6a9955"),
                (r"\"(?:[^\"\\]|\\.)*\"", "#ce9178"),
                (r"\b\d+(?:\.\d+)?\b", "#b5cea8"),
            ]
            if syntax in {"json", "javascript", "typescript"}:
                return [*common, (r"\b(?:true|false|null)\b", "#569cd6")]
            if syntax in {"shell", "powershell"}:
                return [*common, (r"\b(?:if|then|else|fi|for|do|done|set|function)\b", "#569cd6")]
            if syntax in {"ssh-config", "ini", "systemd", "nginx"}:
                return [*common, (r"(?m)^[A-Za-z0-9_.-]+(?=\s|=)", "#9cdcfe")]
            if syntax == "log":
                return [*common, (r"\b(?:error|failed|denied|warning|ok|success)\b", "#dcdcaa")]
            return common

        def highlightBlock(self, text: str | None) -> None:
            source = text or ""
            for pattern, color in self.patterns:
                text_format = QTextCharFormat()
                text_format.setForeground(QColor(color))
                for match in re.finditer(pattern, source, re.IGNORECASE):
                    start, end = match.span()
                    self.setFormat(start, end - start, text_format)

    class MobaSftpDock(ConnectedSftpDock):
        OPERATIONAL_ACTIONS = frozenset(
            {
                "parent-folder",
                "download",
                "upload",
                "connect",
                "tools",
                "terminal",
            }
        )
        UNAVAILABLE_ACTION_DETAILS = {
            "new-folder": "Use Tools > Transfer queue to review and run mkdir safely.",
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

        def apply_connected_text_editor_route_properties(self, widget, *, triggered: bool = False, status: str = "ready") -> None:
            route = moba_connected_text_editor_route(self.state)
            properties = {
                "mobaTextEditorSchema": route.schema,
                "mobaTextEditorProfile": route.profile_name,
                "mobaTextEditorRemotePath": route.remote_path,
                "mobaTextEditorLocalPath": route.local_path,
                "mobaTextEditorSyntax": route.syntax,
                "mobaTextEditorEncoding": route.encoding,
                "mobaTextEditorRemoteSha256": route.remote_sha256,
                "mobaTextEditorOpenedFromSftpBrowser": route.opened_from_sftp_browser,
                "mobaTextEditorSourceBrowserObject": route.source_browser_object,
                "mobaTextEditorSourceTableObject": route.source_table_object,
                "mobaTextEditorSourceRowName": route.source_row_name,
                "mobaTextEditorSourceRowIndex": route.source_row_index,
                "mobaTextEditorTabObject": route.editor_tab_object,
                "mobaTextEditorObject": route.editor_object,
                "mobaTextEditorSaveActionObject": route.save_action_object,
                "mobaTextEditorDiffActionObject": route.diff_action_object,
                "mobaTextEditorOpenSignal": route.open_signal,
                "mobaTextEditorSaveSignal": route.save_signal,
                "mobaTextEditorDiffSignal": route.diff_signal,
                "mobaTextEditorOpenCommand": list(route.open_command),
                "mobaTextEditorOpenBatchCommands": list(route.open_batch_commands),
                "mobaTextEditorSaveCommand": list(route.save_command),
                "mobaTextEditorSaveBatchCommands": list(route.save_batch_commands),
                "mobaTextEditorConflictPolicy": route.conflict_policy,
                "mobaTextEditorCapturedOpen": triggered,
                "mobaTextEditorStatus": status,
                "mobaTextEditorDirty": False,
                "mobaTextEditorRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def __init__(self, state: MobaConnectedSessionState) -> None:
            QFrame.__init__(self)
            self.setObjectName("mobaConnectedLeftDock")
            self.state = replace(
                state,
                file_entries=self.filtered_sftp_entries(state.file_entries),
            )
            self.active_remote_path = normalise_remote_path(self.state.remote_path)
            self.monitoring_control_widgets: dict[str, QAbstractButton] = {}
            self.monitoring_output_buffer = bytearray()
            self.runtime_shutting_down = False
            self.background_auth_retry_attempt = 0
            self._background_password: bytearray | None = None
            self.setProperty("mobaBackgroundSshCredentialSource", "")
            self._background_auth_prompt_buffers = {
                "monitoring": bytearray(),
                "sftp": bytearray(),
                "text-editor": bytearray(),
            }
            self._background_auth_password_sent = {
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
            self.monitoring_generation = 0
            self.monitoring_active_generation = 0
            self._monitoring_manual_request = False
            self.monitoring_refresh_timer = QTimer(self)
            self.monitoring_refresh_timer.setInterval(
                gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds * 1000
            )
            self.monitoring_refresh_timer.timeout.connect(
                self.request_remote_monitoring_refresh
            )
            # Monitoring is periodic and must never open a visible interactive
            # prompt. Reusing the active SSH control path or configured key/
            # agent remains non-interactive; a session-only password may use
            # the hidden PTY transport after an explicit manual auth action.
            self.monitoring_process = _background_process(self, interactive_auth=True)
            self.monitoring_process.setProperty(
                "mobaMonitoringNonInteractive",
                True,
            )
            self.monitoring_process.setProcessChannelMode(
                QProcess.ProcessChannelMode.MergedChannels
            )
            self.monitoring_process.readyReadStandardOutput.connect(
                self.read_remote_monitoring_output
            )
            self.monitoring_process.finished.connect(
                self.handle_remote_monitoring_finished
            )
            self.monitoring_process.errorOccurred.connect(
                self.handle_remote_monitoring_error
            )
            self.sftp_refresh_output_buffer = bytearray()
            self.sftp_refresh_plan: SftpBatchPlan | None = None
            self.sftp_refresh_generation = 0
            self.sftp_refresh_active_generation = 0
            self.sftp_refresh_request_path = ""
            self.sftp_refresh_pending: tuple[str, str] | None = None
            self.sftp_refresh_process = _background_process(self, interactive_auth=True)
            self.sftp_refresh_process.setProcessChannelMode(
                QProcess.ProcessChannelMode.MergedChannels
            )
            self.sftp_refresh_process.started.connect(
                self.write_sftp_refresh_batch
            )
            self.sftp_refresh_process.readyReadStandardOutput.connect(
                self.read_sftp_refresh_output
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
            self.text_editor_output_buffer = bytearray()
            self.text_editor_process = _background_process(self, interactive_auth=True)
            self.text_editor_process.setProcessChannelMode(
                QProcess.ProcessChannelMode.MergedChannels
            )
            self.text_editor_process.started.connect(
                self.write_text_editor_sftp_batch
            )
            self.text_editor_process.readyReadStandardOutput.connect(
                self.read_text_editor_sftp_output
            )
            self.text_editor_process.finished.connect(
                self.handle_text_editor_sftp_finished
            )
            self.text_editor_process.errorOccurred.connect(
                self.handle_text_editor_sftp_error
            )
            self.text_editor_timeout = QTimer(self)
            self.text_editor_timeout.setSingleShot(True)
            self.text_editor_timeout.timeout.connect(
                self.cancel_text_editor_sftp_timeout
            )
            self.text_editor_auth_probe_timer = QTimer(self)
            self.text_editor_auth_probe_timer.setSingleShot(True)
            self.text_editor_auth_probe_timer.setInterval(1200)
            self.text_editor_auth_probe_timer.timeout.connect(
                lambda: self.write_text_editor_sftp_batch(force=True)
            )
            self.text_editor_generation = 0
            self.text_editor_active_generation = 0
            self.text_editor_operation = ""
            self.text_editor_tab_plan: MobaTextEditorTabPlan | None = None
            self.text_editor_sftp_plan: SftpBatchPlan | None = None
            self.text_editor_pending_sftp: tuple[str, SftpBatchPlan, str, str] | None = None
            self.text_editor_remote_path = ""
            self.text_editor_local_path = ""
            self.text_editor_probe_path = ""
            self.text_editor_baseline_text = ""
            self.text_editor_original_remote_sha256 = ""
            self.text_editor_cache_sha256 = ""
            self.text_editor_save_force = False
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
            parent_item = QTreeWidgetItem([chrome.parent_row_label, "", ""])
            self.apply_sftp_file_row_icon(parent_item, chrome.parent_row_kind)
            self.apply_sftp_routed_file_row_metadata(
                parent_item,
                routed_rows,
                row_index=0,
                name=chrome.parent_row_label,
                selected=True,
            )
            parent_item.setSizeHint(0, QSize(0, density.file_row_height))
            parent_item.setToolTip(0, "parent directory")
            self.file_table.addTopLevelItem(parent_item)
            for row_index, entry in enumerate(self.state.file_entries, start=1):
                item = QTreeWidgetItem([entry.name, str(entry.size_kb), entry.modified])
                self.apply_sftp_file_row_icon(item, entry.kind)
                self.apply_sftp_routed_file_row_metadata(
                    item,
                    routed_rows,
                    row_index=row_index,
                    name=entry.name,
                    selected=False,
                )
                item.setSizeHint(0, QSize(0, density.file_row_height))
                item.setToolTip(0, _safe_tooltip_html(f"{entry.kind}: {entry.name}"))
                self.file_table.addTopLevelItem(item)
            parent_item.setSelected(True)
            self.file_table.setCurrentItem(parent_item)
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

        def shared_ssh_control_path(self) -> str:
            """Find the running terminal that owns this session's SSH master."""

            main_window = self.main_window()
            if main_window is None or not hasattr(main_window, "tabs"):
                return ""
            pane_provider = getattr(main_window, "all_terminal_panes", None)
            if callable(pane_provider):
                panes = pane_provider()
            else:
                current = main_window.tabs.currentWidget()
                if current is None:
                    return ""
                panes = main_window.terminal_panes_in(current)
            for pane in panes:
                pane_profile = getattr(pane, "profile", None)
                if (
                    pane_profile is None
                    or pane_profile.name != self.state.profile_name
                    or not pane.is_running()
                ):
                    continue
                control_path = str(getattr(pane, "ssh_control_path", "") or "")
                if control_path:
                    return control_path
            return ""

        def background_ssh_auth_capability(self, profile: Profile | None) -> tuple[bool, str]:
            """Return whether an automatic, non-interactive SSH child is defensible."""

            if profile is None:
                return False, "connected profile was not found"
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
            for process_kind in self._background_auth_password_sent:
                self._background_auth_password_sent[process_kind] = False
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
            if self._background_auth_password_sent[process_kind]:
                return
            prompt_buffer = self._background_auth_prompt_buffers[process_kind]
            prompt_buffer.extend(payload)
            del prompt_buffer[:-1024]
            prompt = prompt_buffer.decode(errors="replace")[-768:]
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
            accepted = process.write(bytes(password) + b"\r")
            if accepted <= 0:
                return
            self._background_auth_password_sent[process_kind] = True
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

        def schedule_background_auth_retry(self) -> None:
            """Retry background clients after the interactive SSH prompt completes."""

            if self.runtime_shutting_down:
                return
            profile = self.profile_for_sftp_action()
            available, _detail = self.background_ssh_auth_capability(profile)
            if not available:
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

        def set_sftp_runtime_status(self, message: str, *, state: str) -> None:
            badge = getattr(self, "sftp_status_badge", None)
            auth_detail = self.background_ssh_auth_detail()
            tooltip = (
                f"{message}\n"
                f"{auth_detail}"
            )
            if badge is not None:
                badge.setProperty("state", state)
                badge.setProperty("mobaSftpStatusBadgeState", state)
                badge.setProperty("mobaSftpStatusBadgeMessage", message)
                badge.setToolTip(_safe_tooltip_html(tooltip))
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
                table.setToolTip(_safe_tooltip_html(tooltip))

        def build_text_editor_toolbar(self) -> QFrame:
            toolbar = QFrame()
            toolbar.setObjectName("mobaTextEditorToolbar")
            self.apply_connected_text_editor_route_properties(toolbar)
            layout = QHBoxLayout(toolbar)
            layout.setContentsMargins(0, 4, 0, 2)
            layout.setSpacing(4)
            self.text_editor_save_button = self.text_editor_action_button(
                "save",
                "SP_DialogSaveButton",
                "mobaTextEditorSaveAction",
                self.handle_moba_text_editor_save,
            )
            self.text_editor_diff_button = self.text_editor_action_button(
                "diff",
                "SP_FileDialogDetailedView",
                "mobaTextEditorDiffAction",
                self.handle_moba_text_editor_diff,
            )
            layout.addWidget(self.text_editor_save_button)
            layout.addWidget(self.text_editor_diff_button)
            layout.addStretch(1)
            close_button = self.text_editor_action_button(
                "close",
                "SP_DialogCancelButton",
                "mobaTextEditorCloseAction",
                self.hide_moba_text_editor,
            )
            close_button.setToolTip("Close the inline editor")
            self.text_editor_close_button = close_button
            layout.addWidget(close_button)
            return toolbar

        def build_text_editor(self) -> QPlainTextEdit:
            route = moba_connected_text_editor_route(self.state)
            editor = QPlainTextEdit()
            editor.setObjectName(route.editor_object)
            self.apply_connected_text_editor_route_properties(editor)
            editor.setPlainText("")
            editor.setPlaceholderText(
                "Remote content is not loaded. Use Download to retrieve the file first."
            )
            editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            editor.setFixedHeight(116)
            editor.setReadOnly(True)
            editor.setProperty("mobaTextEditorContentLoaded", False)
            editor.setProperty("mobaTextEditorSyntheticPreviewSuppressed", True)
            editor.textChanged.connect(self.handle_moba_text_editor_changed)
            self.text_editor_highlighter = MobaTextEditorHighlighter(editor.document(), route.syntax)
            self.text_editor_save_button.setEnabled(False)
            self.text_editor_diff_button.setEnabled(False)
            return editor

        def text_editor_action_button(self, action_key: str, icon_name: str, object_name: str, handler) -> QToolButton:
            route = moba_connected_text_editor_route(self.state)
            button = QToolButton()
            button.setObjectName(object_name)
            button.setProperty("mobaTextEditorActionKey", action_key)
            button.setProperty("mobaTextEditorActionObject", object_name)
            button.setProperty("mobaTextEditorRemotePath", route.remote_path)
            button.setProperty("mobaTextEditorRenderSource", route.render_source)
            button.setIcon(_widget_style(self).standardIcon(self.standard_icon(icon_name)))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(QSize(24, 22))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.clicked.connect(handler)
            return button

        def text_editor_route_widgets(self) -> tuple[QWidget, ...]:
            return tuple(
                widget
                for widget in (
                    self,
                    getattr(self, "browser", None),
                    getattr(self, "file_table", None),
                    getattr(self, "text_editor_toolbar", None),
                    getattr(self, "text_editor", None),
                    getattr(self, "text_editor_save_button", None),
                    getattr(self, "text_editor_diff_button", None),
                )
                if widget is not None
            )

        def update_text_editor_state_from_plan(
            self,
            plan: MobaTextEditorTabPlan,
            *,
            source_row_name: str,
            source_row_index: int,
            remote_sha256: str = "",
        ) -> None:
            current = self.state.text_editor
            self.state = replace(
                self.state,
                text_editor=replace(
                    current,
                    schema=plan.schema,
                    profile_name=plan.profile_name,
                    remote_path=plan.remote_path,
                    local_path=plan.local_path,
                    syntax=plan.syntax,
                    encoding=plan.encoding,
                    remote_sha256=remote_sha256,
                    opened_from_sftp_browser=plan.opened_from_sftp_browser,
                    source_row_name=source_row_name,
                    source_row_index=source_row_index,
                    open_command=tuple(plan.download_plan.command),
                    open_batch_commands=tuple(plan.download_plan.batch_commands),
                    save_command=tuple(plan.save_plan.command),
                    save_batch_commands=tuple(plan.save_plan.batch_commands),
                    conflict_policy=plan.conflict_policy,
                    preview_text="",
                    render_source="connected-sftp-browser-text-editor",
                ),
            )
            self.text_editor_highlighter.set_syntax(plan.syntax)

        def set_text_editor_runtime_state(
            self,
            *,
            status: str,
            dirty: bool | None = None,
            content_loaded: bool | None = None,
            remote_sha256: str | None = None,
            operation: str | None = None,
        ) -> None:
            editor = getattr(self, "text_editor", None)
            if editor is None:
                return
            effective_dirty = (
                bool(editor.property("mobaTextEditorDirty"))
                if dirty is None
                else bool(dirty)
            )
            effective_loaded = (
                bool(editor.property("mobaTextEditorContentLoaded"))
                if content_loaded is None
                else bool(content_loaded)
            )
            for widget in self.text_editor_route_widgets():
                widget.setProperty("mobaTextEditorStatus", status)
                widget.setProperty("mobaTextEditorDirty", effective_dirty)
                widget.setProperty("mobaTextEditorContentLoaded", effective_loaded)
                if remote_sha256 is not None:
                    widget.setProperty("mobaTextEditorRemoteSha256", remote_sha256)
                if operation is not None:
                    widget.setProperty("mobaTextEditorOperation", operation)
            operation_is_locked = operation == "upload"
            editor.setReadOnly(not effective_loaded or operation_is_locked)
            save_button = getattr(self, "text_editor_save_button", None)
            if save_button is not None:
                save_button.setEnabled(effective_loaded and effective_dirty)
                save_button.setProperty("mobaTextEditorDirty", effective_dirty)
            diff_button = getattr(self, "text_editor_diff_button", None)
            if diff_button is not None:
                diff_button.setEnabled(effective_loaded)
                diff_button.setProperty("mobaTextEditorDirty", effective_dirty)

        def handle_moba_text_editor_open_from_item(self, item: QTreeWidgetItem, _column: int) -> None:
            remote_path = self.text_editor_remote_path_for_item(item)
            if not remote_path:
                return
            editor = getattr(self, "text_editor", None)
            if editor is None:
                return
            if (
                bool(editor.property("mobaTextEditorContentLoaded"))
                and bool(editor.property("mobaTextEditorDirty"))
            ):
                current_path = self.text_editor_remote_path or "the current document"
                choice = _literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Unsaved editor changes",
                    (
                        f"Discard unsaved changes to {current_path} and open "
                        f"{remote_path}?"
                    ),
                    buttons=(
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No
                    ),
                    default_button=QMessageBox.StandardButton.No,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    self.show_sftp_status("Opening the file was cancelled; unsaved changes were kept")
                    return
            profile = self.profile_for_sftp_action()
            if profile is None:
                self.show_sftp_status(
                    "Text editor unavailable: connected profile was not found"
                )
                return
            try:
                plan = build_moba_text_editor_tab_plan(profile, remote_path)
                prepare_managed_edit_cache(plan.local_path)
            except (OSError, ValueError) as exc:
                self.show_sftp_status(f"Text editor unavailable: {exc}")
                return
            self.cancel_text_editor_sftp_operation()
            self.text_editor_tab_plan = plan
            self.text_editor_remote_path = plan.remote_path
            self.text_editor_local_path = plan.local_path
            self.text_editor_probe_path = ""
            self.text_editor_baseline_text = ""
            self.text_editor_original_remote_sha256 = ""
            self.text_editor_cache_sha256 = ""
            self.text_editor_save_force = False
            self.update_text_editor_state_from_plan(
                plan,
                source_row_name=item.text(0),
                source_row_index=int(item.data(0, SFTP_ROW_INDEX_ROLE) or -1),
            )
            previous = editor.blockSignals(True)
            try:
                editor.clear()
            finally:
                editor.blockSignals(previous)
            save_button = getattr(self, "text_editor_save_button", None)
            diff_button = getattr(self, "text_editor_diff_button", None)
            toolbar = getattr(self, "text_editor_toolbar", None)
            widgets = [
                self,
                getattr(self, "browser", None),
                getattr(self, "file_table", None),
                editor,
                save_button,
                diff_button,
                toolbar,
            ]
            for widget in widgets:
                if widget is None:
                    continue
                self.apply_connected_text_editor_route_properties(widget, triggered=True, status="opened")
                widget.setProperty("mobaTextEditorRemotePath", plan.remote_path)
                widget.setProperty("mobaTextEditorLocalPath", plan.local_path)
                widget.setProperty("mobaTextEditorCapturedRowName", item.text(0))
                widget.setProperty("mobaTextEditorCapturedOpenSignal", "itemDoubleClicked")
                widget.setProperty("mobaTextEditorDirty", False)
                widget.setProperty("mobaTextEditorContentLoaded", False)
                widget.setProperty("mobaTextEditorOnDemand", True)
            editor.setPlaceholderText(
                f"Downloading {plan.remote_path}..."
            )
            editor.setReadOnly(True)
            if toolbar is not None:
                toolbar.setVisible(True)
            editor.setVisible(True)
            self.setProperty("mobaTextEditorOnDemandVisible", True)
            self.set_text_editor_runtime_state(
                status="downloading",
                dirty=False,
                content_loaded=False,
                operation="open",
            )
            if not self.ensure_background_authentication_for_request():
                self.set_text_editor_runtime_state(
                    status="auth-required",
                    dirty=False,
                    content_loaded=False,
                    operation="open",
                )
                editor.setPlaceholderText(
                    f"Authentication required to download {plan.remote_path}."
                )
                return
            self.show_sftp_status(f"Downloading {plan.remote_path} for editing")
            self.start_text_editor_sftp_operation("open", plan.download_plan)

        def hide_moba_text_editor(self, *_args) -> None:
            self.cancel_text_editor_sftp_operation()
            toolbar = getattr(self, "text_editor_toolbar", None)
            editor = getattr(self, "text_editor", None)
            if toolbar is not None:
                toolbar.setVisible(False)
            if editor is not None:
                editor.setVisible(False)
            self.setProperty("mobaTextEditorOnDemandVisible", False)

        def handle_moba_text_editor_changed(self) -> None:
            editor = getattr(self, "text_editor", None)
            if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
                return
            self.set_text_editor_runtime_state(
                status="modified",
                dirty=True,
                content_loaded=True,
                operation="idle",
            )

        def handle_moba_text_editor_save(self) -> None:
            editor = getattr(self, "text_editor", None)
            if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
                self.show_sftp_status("Text editor save unavailable: remote content is not loaded")
                return
            if not bool(editor.property("mobaTextEditorDirty")):
                self.show_sftp_status("Text editor has no unsaved changes")
                return
            if self.text_editor_active_generation:
                self.show_sftp_status("Text editor is still transferring")
                return
            profile = self.profile_for_sftp_action()
            if profile is None:
                self.show_sftp_status("Text editor save unavailable: connected profile was not found")
                return
            if not self.ensure_background_authentication_for_request():
                return
            local_path = Path(self.text_editor_local_path)
            probe_path = local_path.with_name(f"{local_path.name}.remote-check")
            try:
                probe_plan = build_sftp_get_plan(
                    profile,
                    self.text_editor_remote_path,
                    local_path=probe_path,
                    allow_overwrite=True,
                )
            except ValueError as exc:
                self.show_sftp_status(f"Text editor save unavailable: {exc}")
                return
            self.text_editor_probe_path = str(probe_path)
            self.text_editor_save_force = False
            self.set_text_editor_runtime_state(
                status="checking-remote",
                dirty=True,
                content_loaded=True,
                operation="save-check",
            )
            self.show_sftp_status(
                f"Checking {self.text_editor_remote_path} for remote changes"
            )
            self.start_text_editor_sftp_operation("save-check", probe_plan)

        def handle_moba_text_editor_diff(self) -> None:
            editor = getattr(self, "text_editor", None)
            if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
                self.show_sftp_status("Text editor diff unavailable: remote content is not loaded")
                return
            current_text = editor.toPlainText()
            diff_lines = list(
                difflib.unified_diff(
                    self.text_editor_baseline_text.splitlines(keepends=True),
                    current_text.splitlines(keepends=True),
                    fromfile=self.text_editor_remote_path,
                    tofile=f"{self.text_editor_remote_path} (editor)",
                    n=3,
                )
            )
            diff_text = "".join(diff_lines)
            self.capture_moba_text_editor_action("diff", status="diff-ready")
            for widget in self.text_editor_route_widgets():
                widget.setProperty("mobaTextEditorDiffText", diff_text)
                widget.setProperty("mobaTextEditorDiffEqual", not bool(diff_text))
                widget.setProperty(
                    "mobaTextEditorDiffHunkCount",
                    sum(1 for line in diff_lines if line.startswith("@@")),
                )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("Remote text diff")
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(
                "No changes from the downloaded remote baseline."
                if not diff_text
                else "Local editor changes compared with the downloaded remote baseline:"
            )
            box.setDetailedText(diff_text or "No changes")
            box.exec()

        def capture_moba_text_editor_action(self, action: str, *, status: str) -> None:
            editor = getattr(self, "text_editor", None)
            route = moba_connected_text_editor_route(self.state)
            line_count = len(editor.toPlainText().splitlines()) if editor is not None else 0
            dirty = bool(editor is not None and editor.property("mobaTextEditorDirty"))
            content_loaded = bool(
                editor is not None
                and editor.property("mobaTextEditorContentLoaded")
            )
            for widget in self.text_editor_route_widgets():
                self.apply_connected_text_editor_route_properties(widget, triggered=True, status=status)
                widget.setProperty("mobaTextEditorCapturedAction", action)
                widget.setProperty("mobaTextEditorCapturedLineCount", line_count)
                widget.setProperty("mobaTextEditorCapturedSaveBatchCommands", list(route.save_batch_commands))
                widget.setProperty("mobaTextEditorCapturedConflictPolicy", route.conflict_policy)
                widget.setProperty("mobaTextEditorDirty", dirty)
                widget.setProperty("mobaTextEditorContentLoaded", content_loaded)
                if action == "save":
                    widget.setProperty("mobaTextEditorCapturedSave", True)
                    widget.setProperty("mobaTextEditorDirty", False)
                elif action == "diff":
                    widget.setProperty("mobaTextEditorCapturedDiff", True)

        def text_editor_remote_path_for_item(self, item: QTreeWidgetItem) -> str:
            kind = str(item.data(0, SFTP_ROW_KIND_ROLE) or "")
            name = item.text(0).strip()
            if kind != "file" or not name:
                return ""
            base = str(
                item.data(0, SFTP_ROW_SOURCE_PATH_ROLE)
                or self.active_remote_path
            ).rstrip("/")
            if not base:
                base = "/"
            return f"/{name}" if base == "/" else f"{base}/{name}"

        def text_editor_preview_for_remote_path(self, remote_path: str) -> str:
            del remote_path
            return ""

        def start_text_editor_sftp_operation(
            self,
            operation: str,
            plan: SftpBatchPlan,
        ) -> bool:
            """Run one editor transfer without blocking the Qt event loop."""

            if self.runtime_shutting_down:
                return False
            process = self.text_editor_process
            if process.state() != QProcess.ProcessState.NotRunning:
                self.text_editor_generation += 1
                self.text_editor_active_generation = 0
                self.text_editor_pending_sftp = (
                    operation,
                    plan,
                    self.text_editor_remote_path,
                    self.text_editor_local_path,
                )
                process.kill()
                self.show_sftp_status("Text editor transfer queued")
                return True
            self.text_editor_generation += 1
            request_generation = self.text_editor_generation
            self.text_editor_active_generation = request_generation
            self.text_editor_operation = operation
            self.text_editor_sftp_plan = plan
            self.text_editor_output_buffer.clear()
            self._background_auth_prompt_buffers["text-editor"].clear()
            self._background_auth_password_sent["text-editor"] = False
            runtime_command = openssh_command_with_overrides(
                list(plan.command),
                self.background_ssh_overrides(),
            )
            runtime_command = openssh_command_without_windows_connection_sharing(
                runtime_command
            )
            control_path = self.shared_ssh_control_path()
            if control_path:
                runtime_command = ssh_command_with_control_path(
                    runtime_command,
                    control_path,
                    master=False,
                )
            try:
                process.setProgram(runtime_command[0])
                process.setArguments(runtime_command[1:])
                process.start()
            except (OSError, RuntimeError) as exc:
                self.text_editor_active_generation = 0
                self.set_text_editor_runtime_state(
                    status="error",
                    operation="idle",
                )
                self.show_sftp_status(f"Text editor transfer could not start: {exc}")
                if operation == "save-check":
                    self.clear_text_editor_probe_file()
                self.schedule_pending_text_editor_sftp()
                return False
            self.text_editor_timeout.start(30_000)
            return True

        def clear_text_editor_probe_file(self) -> None:
            probe_path = self.text_editor_probe_path
            self.text_editor_probe_path = ""
            if not probe_path:
                return
            try:
                Path(probe_path).unlink(missing_ok=True)
            except OSError:
                pass

        def cancel_text_editor_sftp_operation(self) -> None:
            self.text_editor_generation += 1
            self.text_editor_active_generation = 0
            self.text_editor_pending_sftp = None
            self.text_editor_timeout.stop()
            self.text_editor_auth_probe_timer.stop()
            self.clear_text_editor_probe_file()
            if self.text_editor_process.state() != QProcess.ProcessState.NotRunning:
                self.text_editor_process.kill()

        def text_editor_sftp_request_is_current(self) -> bool:
            return bool(
                not self.runtime_shutting_down
                and self.text_editor_active_generation != 0
                and self.text_editor_active_generation == self.text_editor_generation
            )

        def write_text_editor_sftp_batch(self, *, force: bool = False) -> None:
            if not self.text_editor_sftp_request_is_current():
                return
            if self._background_password and not force:
                if not self.text_editor_auth_probe_timer.isActive():
                    self.text_editor_auth_probe_timer.start()
                return
            self.text_editor_auth_probe_timer.stop()
            plan = self.text_editor_sftp_plan
            if plan is None:
                return
            accepted = self.text_editor_process.write(
                plan.batch_input().encode("utf-8")
            )
            self.text_editor_process.closeWriteChannel()
            if accepted < 0:
                self.show_sftp_status(
                    "Text editor transfer failed: batch input was not accepted"
                )

        def read_text_editor_sftp_output(self) -> None:
            payload = bytes(self.text_editor_process.readAllStandardOutput())
            self._submit_background_password_if_prompt("text-editor", payload)
            self.text_editor_output_buffer.extend(payload)

        def handle_text_editor_sftp_error(self, error) -> None:
            self.text_editor_timeout.stop()
            self.text_editor_auth_probe_timer.stop()
            operation = self.text_editor_operation
            request_is_current = self.text_editor_sftp_request_is_current()
            self.text_editor_active_generation = 0
            if operation == "save-check":
                self.clear_text_editor_probe_file()
            if request_is_current:
                detail = getattr(error, "name", str(error))
                self.set_text_editor_runtime_state(
                    status="error",
                    operation="idle",
                )
                self.show_sftp_status(f"Text editor transfer error: {detail}")
            self.schedule_pending_text_editor_sftp()

        def cancel_text_editor_sftp_timeout(self) -> None:
            if self.text_editor_process.state() == QProcess.ProcessState.NotRunning:
                return
            request_is_current = self.text_editor_sftp_request_is_current()
            operation = self.text_editor_operation
            self.text_editor_active_generation = 0
            self.text_editor_auth_probe_timer.stop()
            if operation == "save-check":
                self.clear_text_editor_probe_file()
            self.text_editor_process.kill()
            if request_is_current:
                self.set_text_editor_runtime_state(
                    status="error",
                    operation="idle",
                )
                self.show_sftp_status("Text editor transfer timed out after 30 seconds")

        def handle_text_editor_sftp_finished(
            self,
            exit_code: int,
            _exit_status: QProcess.ExitStatus,
        ) -> None:
            self.text_editor_timeout.stop()
            self.text_editor_auth_probe_timer.stop()
            request_is_current = self.text_editor_sftp_request_is_current()
            self.read_text_editor_sftp_output()
            output = self.text_editor_output_buffer.decode(errors="replace")
            operation = self.text_editor_operation
            self.text_editor_active_generation = 0
            if not request_is_current:
                self.schedule_pending_text_editor_sftp()
                return
            if exit_code != 0:
                if operation == "save-check":
                    self.clear_text_editor_probe_file()
                detail = next(
                    (line.strip() for line in reversed(output.splitlines()) if line.strip()),
                    f"exit {exit_code}",
                )
                self.set_text_editor_runtime_state(
                    status="error",
                    operation="idle",
                )
                self.show_sftp_status(
                    f"Text editor {operation} failed: {detail[:160]}"
                )
                self.schedule_background_auth_retry()
                self.schedule_pending_text_editor_sftp()
                return
            try:
                if operation == "open":
                    self.finish_text_editor_open()
                elif operation == "save-check":
                    self.finish_text_editor_save_check()
                elif operation == "upload":
                    self.finish_text_editor_upload()
                else:
                    self.show_sftp_status(f"Text editor completed unknown operation: {operation}")
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                self.set_text_editor_runtime_state(
                    status="error",
                    operation="idle",
                )
                self.show_sftp_status(f"Text editor transfer result was invalid: {exc}")
            self.schedule_pending_text_editor_sftp()

        def schedule_pending_text_editor_sftp(self) -> None:
            pending = self.text_editor_pending_sftp
            self.text_editor_pending_sftp = None
            if pending is None or self.runtime_shutting_down:
                return
            operation, plan, remote_path, local_path = pending

            def start_pending() -> None:
                if self.runtime_shutting_down:
                    return
                self.text_editor_remote_path = remote_path
                self.text_editor_local_path = local_path
                self.start_text_editor_sftp_operation(operation, plan)

            QTimer.singleShot(0, start_pending)

        @staticmethod
        def text_editor_file_sha256(path: Path) -> str:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        def finish_text_editor_open(self) -> None:
            path = Path(self.text_editor_local_path)
            encoding = self.state.text_editor.encoding or "utf-8"
            payload = path.read_bytes()
            if b"\x00" in payload:
                raise ValueError("remote file appears to be binary; text editing was refused")
            text = payload.decode(encoding)
            digest = self.text_editor_file_sha256(path)
            editor = self.text_editor
            previous = editor.blockSignals(True)
            try:
                editor.setPlainText(text)
            finally:
                editor.blockSignals(previous)
            editor.setPlaceholderText("")
            self.text_editor_baseline_text = text
            self.text_editor_original_remote_sha256 = digest
            self.text_editor_cache_sha256 = digest
            route = self.state.text_editor
            self.state = replace(
                self.state,
                text_editor=replace(route, remote_sha256=digest),
            )
            for widget in self.text_editor_route_widgets():
                self.apply_connected_text_editor_route_properties(
                    widget,
                    triggered=True,
                    status="loaded",
                )
                widget.setProperty("mobaTextEditorCapturedOpenSignal", "itemDoubleClicked")
            self.set_text_editor_runtime_state(
                status="loaded",
                dirty=False,
                content_loaded=True,
                remote_sha256=digest,
                operation="idle",
            )
            self.show_sftp_status(
                f"Loaded {self.text_editor_remote_path} for editing"
            )

        def finish_text_editor_save_check(self) -> None:
            probe = Path(self.text_editor_probe_path)
            try:
                current_digest = self.text_editor_file_sha256(probe)
            finally:
                self.clear_text_editor_probe_file()
            conflict = current_digest != self.text_editor_original_remote_sha256
            self.text_editor_save_force = conflict
            if conflict:
                choice = _literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Remote file changed",
                    (
                        f"{self.text_editor_remote_path} changed after it was opened. "
                        "Overwrite the newer remote version?"
                    ),
                    buttons=(
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.No
                    ),
                    default_button=QMessageBox.StandardButton.No,
                )
                if choice != QMessageBox.StandardButton.Yes:
                    self.set_text_editor_runtime_state(
                        status="conflict",
                        dirty=True,
                        content_loaded=True,
                        operation="idle",
                    )
                    self.show_sftp_status("Text editor save cancelled after remote conflict")
                    return
            editor = self.text_editor
            try:
                result = write_text_document(
                    self.text_editor_local_path,
                    editor.toPlainText(),
                    expected_sha256=self.text_editor_cache_sha256,
                    backup=True,
                    encoding=self.state.text_editor.encoding or "utf-8",
                )
            except (OSError, ValueError) as exc:
                self.set_text_editor_runtime_state(
                    status="error",
                    dirty=True,
                    content_loaded=True,
                    operation="idle",
                )
                self.show_sftp_status(f"Text editor cache save failed: {exc}")
                return
            self.text_editor_cache_sha256 = result.new_sha256
            tab_plan = self.text_editor_tab_plan
            if tab_plan is None:
                self.show_sftp_status("Text editor upload unavailable: editor plan is missing")
                return
            self.set_text_editor_runtime_state(
                status="uploading",
                dirty=True,
                content_loaded=True,
                operation="upload",
            )
            self.show_sftp_status(
                f"Uploading edited {self.text_editor_remote_path}"
            )
            self.start_text_editor_sftp_operation("upload", tab_plan.save_plan)

        def finish_text_editor_upload(self) -> None:
            digest = self.text_editor_file_sha256(Path(self.text_editor_local_path))
            self.text_editor_baseline_text = self.text_editor.toPlainText()
            self.text_editor_original_remote_sha256 = digest
            self.text_editor_cache_sha256 = digest
            route = self.state.text_editor
            self.state = replace(
                self.state,
                text_editor=replace(route, remote_sha256=digest),
            )
            self.capture_moba_text_editor_action("save", status="saved")
            self.set_text_editor_runtime_state(
                status="saved",
                dirty=False,
                content_loaded=True,
                remote_sha256=digest,
                operation="idle",
            )
            self.show_sftp_status(
                f"Saved {self.text_editor_remote_path} to the remote host"
            )

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

        def apply_sftp_file_row_icon(self, item: QTreeWidgetItem, kind: str) -> None:
            row_icon = gui_design_moba_sftp_file_row_icon(kind)
            item.setData(0, Qt.ItemDataRole.UserRole, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_KEY_ROLE, row_icon.icon_key)
            item.setData(0, SFTP_ROW_KIND_ROLE, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_SIZE_ROLE, row_icon.static_size)
            item.setData(0, SFTP_ROW_ICON_RENDER_ROLE, row_icon.render_source)
            item.setIcon(0, self.sftp_file_row_icon(row_icon.icon_key, size=row_icon.static_size))

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

        def activate_initial_monitoring_state(self) -> None:
            control = self.monitoring_control_widgets.get("remote-monitoring")
            self.set_remote_monitoring_runtime(
                bool(control is not None and control.isChecked()),
                immediate=True,
            )

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
                auth_detail = self.background_ssh_auth_detail()
                tooltip = (
                    f"{message}\n"
                    f"{auth_detail}"
                )
                control.setProperty("state", state)
                control.setProperty("mobaMonitoringStatusBadgeState", state)
                control.setProperty("mobaMonitoringStatusBadgeMessage", message)
                control.setToolTip(_safe_tooltip_html(tooltip))
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

        def monitoring_surface_is_current(self) -> bool:
            if self.runtime_shutting_down:
                return False
            main_window = self.main_window()
            if main_window is not None and hasattr(main_window, "moba_connected_dock"):
                return main_window.moba_connected_dock is self
            return True

        def remote_monitoring_request_is_current(self) -> bool:
            control = self.monitoring_control_widgets.get("remote-monitoring")
            return (
                self.monitoring_surface_is_current()
                and self.monitoring_active_generation != 0
                and self.monitoring_active_generation
                == self.monitoring_generation
                and control is not None
                and (control.isChecked() or self._monitoring_manual_request)
            )

        def shutdown_runtime(self) -> None:
            if self.runtime_shutting_down:
                return
            self.runtime_shutting_down = True
            self.monitoring_generation += 1
            self.monitoring_active_generation = 0
            self._monitoring_manual_request = False
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
                and self.active_remote_path == state.remote_path
                and self.state.monitoring_plan == state.monitoring_plan
                and self.state.sftp_list_plan == state.sftp_list_plan
                and self.state.follow_folder_plan == state.follow_folder_plan
                and self.state.banner == state.banner
                and self.state.smartcard_selection
                == state.smartcard_selection
            )

        def set_remote_monitoring_runtime(
            self,
            enabled: bool,
            *,
            immediate: bool,
            start_periodic: bool = True,
        ) -> None:
            active = bool(enabled)
            self.set_remote_monitoring_expanded(active)
            for widget in (
                self,
                getattr(self, "browser", None),
                getattr(self, "remote_monitoring_panel", None),
                getattr(self, "remote_monitoring_controls", None),
            ):
                if widget is not None:
                    widget.setProperty(
                        "mobaRemoteMonitoringRuntimeActive",
                        active,
                    )
            refresh_button = getattr(self, "monitoring_refresh_button", None)
            if refresh_button is not None:
                # Manual refresh is also the recovery path for password-only
                # SSH on Windows, so it must remain usable while the periodic
                # toggle is paused.
                refresh_button.setEnabled(True)
            if active:
                if start_periodic and not self.monitoring_refresh_timer.isActive():
                    self.monitoring_refresh_timer.start()
                self.set_remote_monitoring_status(
                    "Monitoring on · waiting for live data",
                    state="starting",
                )
                if immediate:
                    QTimer.singleShot(0, self.request_remote_monitoring_refresh)
                return
            self.monitoring_generation += 1
            self.monitoring_active_generation = 0
            self._monitoring_manual_request = False
            self.monitoring_refresh_timer.stop()
            if self.monitoring_process.state() != QProcess.ProcessState.NotRunning:
                self.monitoring_process.kill()
            self.set_remote_monitoring_status("Monitoring off", state="paused")

        def monitoring_runtime_command(self) -> list[str]:
            command = list(self.state.monitoring_plan.command)
            if not command:
                return command
            executable = ntpath.basename(command[0]).lower()
            if executable in {"ssh", "ssh.exe"}:
                command = openssh_command_without_windows_connection_sharing(command)
                command = openssh_command_with_overrides(command, self.background_ssh_overrides())
                control_path = self.shared_ssh_control_path()
                if control_path:
                    command = ssh_command_with_control_path(
                        command,
                        control_path,
                        master=False,
                    )
            return command

        def request_remote_monitoring_refresh(
            self,
            *_args,
            allow_prompt: bool = False,
        ) -> None:
            if self.runtime_shutting_down or not self.monitoring_surface_is_current():
                return
            control = self.monitoring_control_widgets.get("remote-monitoring")
            manual_request = bool(allow_prompt)
            if control is None or (not control.isChecked() and not manual_request):
                return
            if manual_request:
                auth_ready = self.ensure_background_authentication_for_request(
                    allow_prompt=True,
                )
            else:
                auth_ready = self.ensure_background_authentication_for_request()
            if not auth_ready:
                if manual_request:
                    self.set_remote_monitoring_status(
                        "Monitoring authentication required",
                        state="auth-required",
                    )
                    return
                self.setProperty("mobaBackgroundSshApplyingAuthGate", True)
                try:
                    control.setChecked(False)
                finally:
                    self.setProperty("mobaBackgroundSshApplyingAuthGate", False)
                return
            self._monitoring_manual_request = manual_request and not control.isChecked()
            count = int(
                self.property("mobaRemoteMonitoringRefreshRequestCount") or 0
            ) + 1
            for widget in (
                self,
                getattr(self, "remote_monitoring_panel", None),
                control,
            ):
                if widget is not None:
                    widget.setProperty(
                        "mobaRemoteMonitoringRefreshRequestCount",
                        count,
                    )
            if self.monitoring_process.state() != QProcess.ProcessState.NotRunning:
                self.set_remote_monitoring_status(
                    "Monitoring refresh already running",
                    state="refreshing",
                )
                return
            command = self.monitoring_runtime_command()
            if not command:
                self.set_remote_monitoring_status(
                    "Monitoring unavailable: empty command",
                    state="error",
                )
                return
            self.monitoring_output_buffer.clear()
            self.monitoring_generation += 1
            self.monitoring_active_generation = self.monitoring_generation
            self._background_auth_prompt_buffers["monitoring"].clear()
            self._background_auth_password_sent["monitoring"] = False
            self.set_remote_monitoring_status(
                "Refreshing live telemetry…",
                state="refreshing",
            )
            self.monitoring_process.setProgram(command[0])
            self.monitoring_process.setArguments(command[1:])
            self.monitoring_process.start()

        def read_remote_monitoring_output(self) -> None:
            payload = bytes(self.monitoring_process.readAllStandardOutput())
            self._submit_background_password_if_prompt("monitoring", payload)
            self.monitoring_output_buffer.extend(payload)

        def handle_remote_monitoring_error(self, error) -> None:
            request_is_current = self.remote_monitoring_request_is_current()
            self.monitoring_active_generation = 0
            self._monitoring_manual_request = False
            if not request_is_current:
                return
            self.set_remote_monitoring_status(
                f"Monitoring error: {error.name}",
                state="error",
            )
            self.setProperty("mobaRemoteMonitoringLastError", error.name)
            self.schedule_background_auth_retry()

        def handle_remote_monitoring_finished(
            self,
            exit_code: int,
            _exit_status: QProcess.ExitStatus,
        ) -> None:
            request_is_current = self.remote_monitoring_request_is_current()
            self.read_remote_monitoring_output()
            output = self.monitoring_output_buffer.decode(errors="replace")
            self.monitoring_active_generation = 0
            self._monitoring_manual_request = False
            if not request_is_current:
                return
            snapshot = parse_remote_monitoring_output(output) if exit_code == 0 else None
            if snapshot is None:
                detail = next(
                    (line.strip() for line in reversed(output.splitlines()) if line.strip()),
                    f"exit {exit_code}",
                )
                if "permission denied" in detail.lower() and "password" in detail.lower():
                    detail = (
                        "password-only SSH cannot run background monitoring; "
                        "configure key or agent authentication"
                    )
                elif "host key verification failed" in detail.lower():
                    detail = (
                        "host key not trusted; verify it in the terminal, then refresh"
                    )
                shared_control = self.shared_ssh_control_path()
                self.set_remote_monitoring_status(
                    (
                        f"Waiting for terminal SSH authentication: {detail[:120]}"
                        if shared_control
                        else f"Monitoring unavailable: {detail[:120]}"
                    ),
                    state="auth-required" if shared_control else "error",
                )
                self.setProperty("mobaRemoteMonitoringLastError", detail)
                self.schedule_background_auth_retry()
                return
            if not self.apply_live_remote_monitoring_snapshot(snapshot):
                return
            refreshed_at = time.strftime("%H:%M:%S")
            last_refresh = getattr(self, "monitoring_last_refresh_label", None)
            if last_refresh is not None:
                last_refresh.setText(refreshed_at)
                last_refresh.setToolTip(f"Last successful refresh: {refreshed_at}")
            self.setProperty("mobaRemoteMonitoringLastRefresh", refreshed_at)
            self.background_auth_retry_attempt = 0
            self.background_auth_retry_timer.stop()
            self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", False)
            self.set_remote_monitoring_status(
                f"Live · {refreshed_at}",
                state="live",
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
            matching_panels: list[MobaConnectedSessionPanel] = []
            if main_window is not None:
                for index in range(main_window.tabs.count()):
                    candidate = main_window.tabs.widget(index)
                    if (
                        isinstance(candidate, MobaConnectedSessionPanel)
                        and candidate.state.profile_name == live_state.profile_name
                        and candidate.state.target == live_state.target
                    ):
                        matching_panels.append(candidate)
            for panel in matching_panels:
                self._update_live_telemetry_panel(panel, live_state)
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

        def handle_moba_follow_terminal_folder_toggled(self, checked: bool) -> None:
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
            if checked:
                self.request_sftp_refresh(reason="follow-enabled")
            elif self.sftp_refresh_process.state() != QProcess.ProcessState.NotRunning:
                self.sftp_refresh_generation += 1
                self.sftp_refresh_active_generation = 0
                self.sftp_refresh_pending = None
                self.sftp_refresh_process.kill()

        def request_sftp_refresh(self, *, reason: str = "manual") -> None:
            if self.runtime_shutting_down:
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
            except ValueError as exc:
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
            self._background_auth_password_sent["sftp"] = False
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
            accepted = self.sftp_refresh_process.write(
                plan.batch_input().encode("utf-8")
            )
            self.sftp_refresh_process.closeWriteChannel()
            if accepted < 0:
                self.show_sftp_status(
                    "SFTP refresh failed: batch input was not accepted"
                )

        def read_sftp_refresh_output(self) -> None:
            payload = bytes(self.sftp_refresh_process.readAllStandardOutput())
            self._submit_background_password_if_prompt("sftp", payload)
            self.sftp_refresh_output_buffer.extend(payload)

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
            output = self.sftp_refresh_output_buffer.decode(errors="replace")
            self.sftp_refresh_active_generation = 0
            if not request_is_current:
                if not self.runtime_shutting_down:
                    self.show_sftp_status("SFTP refresh superseded")
                self.schedule_pending_sftp_refresh()
                return
            if exit_code != 0:
                detail = next(
                    (line.strip() for line in reversed(output.splitlines()) if line.strip()),
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
            entries = self.filtered_sftp_entries(parse_sftp_ls_output(output))
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

        def apply_live_sftp_entries(
            self,
            entries,
            *,
            request_path: str,
            plan,
        ) -> None:
            entries = self.filtered_sftp_entries(entries)
            density = gui_design_moba_sftp_dock_layout()
            chrome = gui_design_moba_sftp_browser_chrome()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            routed_rows = gui_design_moba_sftp_routed_file_rows()
            selected_path = normalise_remote_path(request_path)
            self.state = replace(
                self.state,
                remote_path=selected_path,
                file_entries=entries,
                sftp_list_plan=plan,
                follow_folder_plan=plan,
            )
            self.file_table.clear()
            parent_item = QTreeWidgetItem([chrome.parent_row_label, "", ""])
            self.apply_sftp_file_row_icon(parent_item, chrome.parent_row_kind)
            self.apply_sftp_routed_file_row_metadata(
                parent_item,
                routed_rows,
                row_index=0,
                name=chrome.parent_row_label,
                selected=True,
                source_path=selected_path,
            )
            parent_item.setSizeHint(0, QSize(0, density.file_row_height))
            parent_item.setToolTip(0, "parent directory")
            self.file_table.addTopLevelItem(parent_item)
            for row_index, entry in enumerate(entries, start=1):
                item = QTreeWidgetItem(
                    [entry.name, str(entry.size_kb), entry.modified]
                )
                self.apply_sftp_file_row_icon(item, entry.kind)
                self.apply_sftp_routed_file_row_metadata(
                    item,
                    routed_rows,
                    row_index=row_index,
                    name=entry.name,
                    selected=False,
                    source_path=selected_path,
                )
                item.setSizeHint(0, QSize(0, density.file_row_height))
                item.setToolTip(
                    0,
                    _safe_tooltip_html(f"{entry.kind}: {entry.name}"),
                )
                self.file_table.addTopLevelItem(item)
            parent_item.setSelected(True)
            self.file_table.setCurrentItem(parent_item)
            self.apply_sftp_follow_folder_route_properties(
                self.file_table,
                follow_route,
            )
            self.update_sftp_action_states()

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
            for action_key, button in getattr(self, "sftp_action_buttons", {}).items():
                operational = action_key in self.OPERATIONAL_ACTIONS
                transfer_action = action_key in {"download", "upload"}
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

        def navigate_moba_sftp_path(self, raw_path: str) -> bool:
            try:
                normalized = posixpath.normpath(normalise_remote_path(raw_path))
            except ValueError as exc:
                self.path.setText(self.active_remote_path)
                self.path.selectAll()
                self.path.setProperty("mobaSftpPathNavigationError", str(exc))
                self.show_sftp_status(f"SFTP path rejected: {exc}")
                return False
            if not normalized.startswith("/"):
                normalized = f"/{normalized}"
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
            if hasattr(self, "file_table"):
                for index in range(self.file_table.topLevelItemCount()):
                    item = self.file_table.topLevelItem(index)
                    if item is not None:
                        item.setData(0, SFTP_ROW_SOURCE_PATH_ROLE, normalized)
            if hasattr(self, "sftp_transfer_queue"):
                self.sftp_transfer_queue.setText(f"Path: {normalized}")
            self.show_sftp_status(f"SFTP path: {normalized}")
            follow_control = self.monitoring_control_widgets.get(
                "follow-terminal-folder"
            )
            if follow_control is not None and follow_control.isChecked():
                self.request_sftp_refresh(reason="path-change")
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
                    lambda: self.open_sftp_context_item(selected),
                ),
                "SFTP open action",
            )
            open_action.setEnabled(open_ready)
            menu.addSeparator()
            download_action = _required_gui_value(
                menu.addAction(
                    "Download",
                    lambda: self.show_moba_sftp_toolbar_action("download"),
                ),
                "SFTP download action",
            )
            download_action.setEnabled(transfer_ready)
            menu.addAction(
                "Upload here",
                lambda: self.show_moba_sftp_toolbar_action("upload"),
            )
            copy_action = _required_gui_value(
                menu.addAction(
                    "Copy remote path",
                    lambda: self.copy_sftp_context_path(selected),
                ),
                "SFTP copy-path action",
            )
            copy_action.setEnabled(open_ready)
            menu.addSeparator()
            menu.addAction(
                "Parent folder",
                lambda: self.show_moba_sftp_toolbar_action("parent-folder"),
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
            return main_window.profile_by_name(self.state.profile_name)

        def show_sftp_status(self, message: str) -> None:
            main_window = self.main_window()
            if main_window is None:
                return
            status_bar = main_window.statusBar()
            if status_bar is not None:
                status_bar.showMessage(message)
            main_window.log.append(message)

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
                operation = shlex.join(
                    [
                        "get",
                        *(["-r"] if kind == "dir" else []),
                        remote_path,
                        f"./{name}",
                    ]
                )
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
                operation = shlex.join(["put", local_path, remote_path])
            dialog = main_window.create_transfer_queue_dialog(profile)
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
            terminal_output = pane.output
            terminal_output.setProperty("mobaTerminalFocusRequested", True)
            terminal_output.setFocus(Qt.FocusReason.OtherFocusReason)
            QTimer.singleShot(
                0,
                lambda: terminal_output.setFocus(Qt.FocusReason.OtherFocusReason),
            )
            self.show_sftp_status(f"Reconnecting {self.state.profile_name}")
            return True

        def focus_moba_sftp_terminal(self) -> bool:
            main_window = self.main_window()
            pane = main_window.active_terminal_pane() if main_window is not None else None
            if pane is None:
                self.show_sftp_status("Terminal unavailable: no active session pane")
                return False
            terminal_output = pane.output
            terminal_output.setProperty("mobaTerminalFocusRequested", True)
            terminal_output.setFocus(Qt.FocusReason.OtherFocusReason)
            QTimer.singleShot(
                0,
                lambda: terminal_output.setFocus(Qt.FocusReason.OtherFocusReason),
            )
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
            if not self.dispatch_moba_sftp_toolbar_action(action.key):
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

    return MobaSftpDock, MobaConnectedSessionPanel
