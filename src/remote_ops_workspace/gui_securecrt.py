from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from .gui_designs import (
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_sftp_browser_route,
    gui_design_securecrt_sftp_tab_route,
)
from .gui_dialogs import _literal_label
from .gui_icons import draw_securecrt_session_manager_action_icon
from .gui_values import _safe_tooltip_html

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QStatusBar


class SecureCrtWorkspace:
    """Build the SecureCRT terminal, session manager and command controls."""

    if TYPE_CHECKING:
        securecrt_host_input: QLineEdit
        securecrt_keyword_input: QLineEdit

        def connect_selected(self, dry_run: bool) -> None: ...
        def create_profile(self) -> None: ...
        def edit_selected_profile(self) -> None: ...
        def filter_profile_tree(self, text: str) -> None: ...
        def generated_icon(
            self, size: int, draw: Callable[[QPainter, int], None], *, antialias: bool = True,
        ) -> QIcon: ...
        def statusBar(self) -> QStatusBar: ...

    def build_securecrt_runtime_terminal_surface(self) -> QFrame:
        """Build the terminal-first SecureCRT document surface.

        This is intentionally a real Qt widget tree (rather than a
        screenshot): the tab/header and transcript remain selectable and
        can be replaced by a live terminal pane when a session is opened.
        """
        panel = QFrame()
        panel.setObjectName("secureCrtRuntimeTerminalSurface")
        panel.setProperty("designPreset", "securecrt")
        panel.setProperty("secureCrtRuntimeSurfaceRole", "terminal-document")
        panel.setMinimumHeight(340)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "QFrame#secureCrtRuntimeTerminalSurface {"
            "background: #003b45; border: 1px solid #777777; }"
            "QLabel#secureCrtRuntimeTerminalHeader {"
            "background: #f7f7f7; color: #202020; padding: 6px 9px;"
            "border: 1px solid #c5c5c5; }"
            "QLabel#secureCrtRuntimeTerminalState {"
            "background: #f7f7f7; color: #297137; padding: 6px 9px;"
            "border: 1px solid #c5c5c5; }"
            "QPlainTextEdit#secureCrtRuntimeTranscript {"
            "background: #003b45; color: #d3e6e3; border: 0px;"
            "selection-background-color: #1c6b79;"
            "font-family: Consolas, 'Courier New'; font-size: 10pt; }"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(0)
        title = QLabel("SSH2: edge-prod.example.invalid")
        title.setObjectName("secureCrtRuntimeTerminalHeader")
        title.setProperty("secureCrtRuntimeSurfaceField", "target")
        state = QLabel("Connected")
        state.setObjectName("secureCrtRuntimeTerminalState")
        state.setProperty("secureCrtRuntimeSurfaceField", "status")
        header.addWidget(title, 1)
        header.addWidget(state)
        layout.addLayout(header)

        transcript = QPlainTextEdit()
        transcript.setObjectName("secureCrtRuntimeTranscript")
        transcript.setReadOnly(True)
        transcript.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        transcript.setProperty("secureCrtRuntimeSurfaceField", "transcript")
        transcript.setProperty("secureCrtRuntimeTranscriptSource", "session-terminal")
        transcript.setPlainText(
            "show interface serial 0\n"
            "Serial0 is up, line protocol is up\n"
            "  Hardware is MCI Serial\n"
            "  Internet address is 155.155.155.90/28, subnet mask is 255.255.255.240\n"
            "  MTU 1500 bytes, BW 1544 Kbit, DLY 20000 usec,\n"
            "     76762 drops; input queue 0/75, 301 drops\n"
            "  54283 packets output, 65566998 bytes, 0 underruns\n"
            "  2 carrier transitions\n"
            "Router#"
        )
        # Preserve the familiar SecureCRT ANSI cues in the live surface:
        # commands/prompts are yellow, warnings are red, and transcript
        # detail stays a cool white on the teal terminal background.
        ansi_lines = (
            (0, "#fff65c"),
            (1, "#fff65c"),
            (5, "#e9a000"),
            (7, "#ff3d35"),
            (8, "#fff65c"),
        )
        cursor = QTextCursor(transcript.document())
        for line_number, color in ansi_lines:
            cursor.setPosition(0)
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, line_number)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.MoveAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            cursor.mergeCharFormat(text_format)
        layout.addWidget(transcript, 1)
        return panel

    def build_securecrt_session_manager_chrome(self) -> QFrame:
        chrome = gui_design_securecrt_session_manager_chrome()
        route = gui_design_securecrt_session_manager_route()
        filter_route = gui_design_securecrt_session_manager_filter_route()
        sftp_route = gui_design_securecrt_sftp_tab_route()
        panel = QFrame()
        panel.setObjectName("secureCrtSessionManagerChrome")
        panel.setProperty("designPreset", "securecrt")
        panel.setProperty("secureCrtSessionRouteKey", route.key)
        panel.setProperty("secureCrtSessionRouteRole", route.route_role)
        panel.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
        panel.setProperty("secureCrtSessionRouteSelectedTreeLabel", route.selected_tree_label)
        panel.setProperty("secureCrtSessionRouteSessionManagerObject", route.session_manager_object)
        panel.setProperty("secureCrtSessionRouteActionKey", route.session_manager_action_key)
        panel.setProperty("secureCrtSessionRouteActionObject", route.session_manager_action_object)
        panel.setProperty("secureCrtSessionRouteStatusStripObject", route.status_strip_object)
        panel.setProperty("secureCrtSessionRouteStatusFieldKey", route.status_field_key)
        panel.setProperty("secureCrtSessionRouteStatusFieldObject", route.status_field_object)
        panel.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
        panel.setProperty("secureCrtSessionRouteTarget", route.target_value)
        panel.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
        panel.setProperty("secureCrtSessionRouteSession", route.session_value)
        panel.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
        panel.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
        panel.setProperty("secureCrtSftpTabRouteKey", sftp_route.key)
        panel.setProperty("secureCrtSftpTabRouteRole", sftp_route.route_role)
        panel.setProperty("secureCrtSftpTabRouteWorkflowKey", sftp_route.workflow_card_key)
        panel.setProperty("secureCrtSftpTabRouteSelectedProfile", sftp_route.selected_profile_name)
        panel.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", sftp_route.selected_tree_label)
        panel.setProperty("secureCrtSftpTabRouteActiveTab", sftp_route.active_tab_label)
        panel.setProperty("secureCrtSftpTabRouteTabLabel", sftp_route.sftp_tab_label)
        panel.setProperty("secureCrtSftpTabRouteStatusStripObject", sftp_route.status_strip_object)
        panel.setProperty("secureCrtSftpTabRouteStatusFieldKey", sftp_route.status_field_key)
        panel.setProperty("secureCrtSftpTabRouteStatusFieldObject", sftp_route.status_field_object)
        panel.setProperty("secureCrtSftpTabRouteStatus", sftp_route.status_value)
        panel.setProperty("secureCrtSftpTabRouteTransferState", sftp_route.transfer_state)
        panel.setProperty("secureCrtSftpTabRouteRenderSource", sftp_route.render_source)
        filter_route_properties = {
            "secureCrtSessionFilterRouteKey": filter_route.key,
            "secureCrtSessionFilterRouteRole": filter_route.route_role,
            "secureCrtSessionFilterRouteSessionManagerObject": filter_route.session_manager_object,
            "secureCrtSessionFilterRouteFilterObject": filter_route.filter_object,
            "secureCrtSessionFilterRouteSelectedTreeObject": filter_route.selected_tree_object,
            "secureCrtSessionFilterRouteSelectedProfile": filter_route.selected_profile_name,
            "secureCrtSessionFilterRouteSelectedTreeLabel": filter_route.selected_tree_label,
            "secureCrtSessionFilterRouteQuery": filter_route.expected_query,
            "secureCrtSessionFilterRoutePlaceholder": filter_route.expected_placeholder,
            "secureCrtSessionFilterRouteMatchedLabel": filter_route.matched_result_label,
            "secureCrtSessionFilterRouteSignal": filter_route.change_signal,
            "secureCrtSessionFilterRouteHandler": filter_route.handler_name,
            "secureCrtSessionFilterRouteRenderSource": filter_route.render_source,
        }
        for property_name, property_value in filter_route_properties.items():
            panel.setProperty(property_name, property_value)
        panel.setProperty("secureCrtSessionManagerActionKeys", [action.key for action in chrome.actions])
        panel.setProperty("secureCrtSessionFilterPlaceholder", chrome.filter_placeholder)
        panel.setProperty("secureCrtSessionManagerStaticTitleX", chrome.static_title_x)
        panel.setProperty("secureCrtSessionManagerStaticTitleY", chrome.static_title_y)
        panel.setProperty("secureCrtSessionManagerStaticFilterY", chrome.static_filter_y)
        panel.setProperty("secureCrtSessionManagerStaticFilterXMargin", chrome.static_filter_x_margin)
        panel.setProperty("secureCrtSessionManagerStaticFilterHeight", chrome.static_filter_height)
        panel.setProperty("secureCrtSessionManagerStaticFilterPlaceholderX", chrome.static_filter_placeholder_x)
        panel.setProperty("secureCrtSessionManagerStaticFilterPlaceholderY", chrome.static_filter_placeholder_y)
        panel.setProperty("secureCrtSessionManagerLiveMaxHeight", chrome.live_max_height)
        panel.setProperty("secureCrtSessionManagerLiveSpacing", chrome.live_spacing)
        panel.setProperty("secureCrtSessionManagerLiveTitleSpacing", chrome.live_title_spacing)
        panel.setProperty("secureCrtSessionManagerLiveFilterHeight", chrome.live_filter_height)
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
        title.setObjectName("secureCrtSessionManagerTitle")
        title_row.addWidget(title, 1)
        for action in chrome.actions:
            button = QToolButton()
            button.setObjectName("secureCrtSessionManagerAction")
            button.setProperty("secureCrtSessionManagerActionKey", action.key)
            button.setProperty("secureCrtSessionManagerIconKey", action.icon_key)
            button.setProperty("secureCrtSessionManagerActionLabel", action.label)
            button.setProperty("secureCrtSessionManagerStaticX", action.static_x)
            button.setProperty("secureCrtSessionManagerStaticY", action.static_y)
            button.setProperty("secureCrtSessionManagerStaticButtonSize", action.static_button_size)
            button.setProperty("secureCrtSessionManagerStaticIconX", action.static_icon_x)
            button.setProperty("secureCrtSessionManagerStaticIconY", action.static_icon_y)
            button.setProperty("secureCrtSessionManagerStaticIconSize", action.static_icon_size)
            button.setProperty("secureCrtSessionManagerLiveIconSize", action.live_icon_size)
            button.setProperty("secureCrtSessionManagerLiveButtonSize", action.live_button_size)
            button.setProperty("secureCrtSessionManagerRenderSource", action.render_source)
            button.setProperty("secureCrtSessionRouteKey", route.key)
            button.setProperty("secureCrtSessionRouteRole", route.route_role)
            button.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
            button.setProperty("secureCrtSessionRouteSelectedTreeLabel", route.selected_tree_label)
            button.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
            button.setProperty("secureCrtSessionRouteTarget", route.target_value)
            button.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
            button.setProperty("secureCrtSessionRouteSession", route.session_value)
            button.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
            button.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
            button.setProperty(
                "secureCrtSessionRouteActive",
                "true" if action.key == route.session_manager_action_key else "false",
            )
            button.setToolTip(action.tooltip)
            button.setIcon(self.securecrt_session_manager_action_icon(action.icon_key, size=action.live_icon_size))
            button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(action.live_button_size, action.live_button_size))
            button.clicked.connect(
                lambda _checked=False, key=action.key: self.run_securecrt_session_manager_action(key)
            )
            title_row.addWidget(button)
        layout.addLayout(title_row)

        self.securecrt_session_filter = QLineEdit()
        self.securecrt_session_filter.setObjectName("secureCrtSessionFilter")
        self.securecrt_session_filter.setPlaceholderText(chrome.filter_placeholder)
        self.securecrt_session_filter.setProperty("secureCrtSessionManagerLiveFilterHeight", chrome.live_filter_height)
        for property_name, property_value in filter_route_properties.items():
            self.securecrt_session_filter.setProperty(property_name, property_value)
        self.securecrt_session_filter.setFixedHeight(chrome.live_filter_height)
        self.securecrt_session_filter.textChanged.connect(self.filter_profile_tree)
        layout.addWidget(self.securecrt_session_filter)
        panel.setVisible(False)
        return panel

    def securecrt_session_manager_action_icon(self, icon_key: str, *, size: int) -> QIcon:
        return self.generated_icon(
            size,
            lambda painter, logical_size: draw_securecrt_session_manager_action_icon(
                painter, icon_key, logical_size
            ),
        )

    def run_securecrt_session_manager_action(self, key: str) -> None:
        actions = {
            "connect": lambda: self.connect_selected(False),
            "new-folder": self.create_profile,
            "properties": self.edit_selected_profile,
        }
        action = actions.get(key)
        if action is None:
            self.statusBar().showMessage(f"Session Manager action: {key}")
            return
        action()

    def build_securecrt_session_status_strip_evidence(self) -> QFrame:
        chrome = gui_design_securecrt_session_status_strip()
        route = gui_design_securecrt_session_manager_route()
        sftp_route = gui_design_securecrt_sftp_tab_route()
        panel = QFrame()
        panel.setObjectName("secureCrtSessionStatusStrip")
        panel.setProperty("designPreset", "securecrt")
        panel.setProperty("secureCrtSessionRouteKey", route.key)
        panel.setProperty("secureCrtSessionRouteRole", route.route_role)
        panel.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
        panel.setProperty("secureCrtSessionRouteSelectedTreeLabel", route.selected_tree_label)
        panel.setProperty("secureCrtSessionRouteSessionManagerObject", route.session_manager_object)
        panel.setProperty("secureCrtSessionRouteActionKey", route.session_manager_action_key)
        panel.setProperty("secureCrtSessionRouteActionObject", route.session_manager_action_object)
        panel.setProperty("secureCrtSessionRouteStatusStripObject", route.status_strip_object)
        panel.setProperty("secureCrtSessionRouteStatusFieldKey", route.status_field_key)
        panel.setProperty("secureCrtSessionRouteStatusFieldObject", route.status_field_object)
        panel.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
        panel.setProperty("secureCrtSessionRouteTarget", route.target_value)
        panel.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
        panel.setProperty("secureCrtSessionRouteSession", route.session_value)
        panel.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
        panel.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
        panel.setProperty("secureCrtSftpTabRouteKey", sftp_route.key)
        panel.setProperty("secureCrtSftpTabRouteRole", sftp_route.route_role)
        panel.setProperty("secureCrtSftpTabRouteWorkflowKey", sftp_route.workflow_card_key)
        panel.setProperty("secureCrtSftpTabRouteSelectedProfile", sftp_route.selected_profile_name)
        panel.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", sftp_route.selected_tree_label)
        panel.setProperty("secureCrtSftpTabRouteActiveTab", sftp_route.active_tab_label)
        panel.setProperty("secureCrtSftpTabRouteTabLabel", sftp_route.sftp_tab_label)
        panel.setProperty("secureCrtSftpTabRouteStatusStripObject", sftp_route.status_strip_object)
        panel.setProperty("secureCrtSftpTabRouteStatusFieldKey", sftp_route.status_field_key)
        panel.setProperty("secureCrtSftpTabRouteStatusFieldObject", sftp_route.status_field_object)
        panel.setProperty("secureCrtSftpTabRouteStatus", sftp_route.status_value)
        panel.setProperty("secureCrtSftpTabRouteTransferState", sftp_route.transfer_state)
        panel.setProperty("secureCrtSftpTabRouteRenderSource", sftp_route.render_source)
        panel.setProperty("secureCrtSessionStatusFieldKeys", [field.key for field in chrome.fields])
        panel.setProperty("secureCrtSessionStatusTitleWidth", chrome.title_width)
        panel.setProperty("secureCrtSessionStatusStaticTitleX", chrome.static_title_x)
        panel.setProperty("secureCrtSessionStatusStaticTitleY", chrome.static_title_y)
        panel.setProperty("secureCrtSessionStatusStaticCellStartX", chrome.static_cell_start_x)
        panel.setProperty("secureCrtSessionStatusStaticCellGap", chrome.static_cell_gap)
        panel.setProperty("secureCrtSessionStatusLiveSpacing", chrome.live_spacing)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(
            chrome.live_margin_left,
            chrome.live_margin_top,
            chrome.live_margin_right,
            chrome.live_margin_bottom,
        )
        layout.setSpacing(chrome.live_spacing)

        title = QLabel(chrome.title)
        title.setObjectName("secureCrtSessionStatusTitle")
        title.setMinimumWidth(chrome.title_width)
        title.setMaximumWidth(chrome.title_width)
        layout.addWidget(title)
        compact_values = {
            "session": "edge-prod",
            "target": "edge-prod:22",
            "protocol": "SSH2+SFTP",
            "cipher": "chacha20",
            "sftp": "files-prod",
            "log": "session.log",
            "state": "connected",
        }
        compact_widths = {
            # The status strip can be only ~520 px wide at the accepted
            # 1024-wide window.  Keep each compact value independent and
            # let its full canonical value live in the accessible label
            # and tooltip rather than allowing sibling cells to overlap.
            "session": 44,
            "target": 62,
            "protocol": 44,
            "cipher": 48,
            "sftp": 42,
            "log": 44,
            "state": 44,
        }
        for field in chrome.fields:
            full_text = f"{field.label}: {field.value}"
            display_text = compact_values[field.key]
            compact_width = compact_widths[field.key]
            tooltip_text = f"{full_text}\n{field.tooltip}"
            cell = _literal_label(display_text)
            cell.setObjectName("secureCrtSessionStatusCell")
            cell.setProperty("secureCrtSessionStatusKey", field.key)
            cell.setProperty("secureCrtSessionStatusLabel", field.label)
            cell.setProperty("secureCrtSessionStatusValue", field.value)
            cell.setProperty("secureCrtSessionStatusWidth", field.static_width)
            cell.setProperty("secureCrtSessionStatusRole", field.role)
            cell.setProperty("secureCrtSessionStatusStaticY", field.static_y)
            cell.setProperty("secureCrtSessionStatusStaticHeight", field.static_height)
            cell.setProperty("secureCrtSessionStatusStaticLabelX", field.static_label_x)
            cell.setProperty("secureCrtSessionStatusStaticLabelY", field.static_label_y)
            cell.setProperty("secureCrtSessionStatusStaticValueX", field.static_value_x)
            cell.setProperty("secureCrtSessionStatusStaticValueY", field.static_value_y)
            cell.setProperty("secureCrtSessionStatusLiveMinWidth", field.live_min_width)
            cell.setProperty("secureCrtSessionStatusLiveCellHeight", field.live_cell_height)
            cell.setProperty("secureCrtSessionStatusFullText", full_text)
            cell.setProperty("secureCrtSessionStatusDisplayText", display_text)
            cell.setProperty("secureCrtSessionStatusTooltipText", tooltip_text)
            cell.setProperty("secureCrtSessionStatusCompactMinWidth", compact_width)
            if field.key == route.status_field_key:
                cell.setProperty("secureCrtSessionRouteKey", route.key)
                cell.setProperty("secureCrtSessionRouteRole", route.route_role)
                cell.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
                cell.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
                cell.setProperty("secureCrtSessionRouteTarget", route.target_value)
                cell.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
                cell.setProperty("secureCrtSessionRouteSession", route.session_value)
                cell.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
                cell.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
            if field.key == sftp_route.status_field_key:
                cell.setProperty("secureCrtSftpTabRouteKey", sftp_route.key)
                cell.setProperty("secureCrtSftpTabRouteRole", sftp_route.route_role)
                cell.setProperty("secureCrtSftpTabRouteWorkflowKey", sftp_route.workflow_card_key)
                cell.setProperty("secureCrtSftpTabRouteSelectedProfile", sftp_route.selected_profile_name)
                cell.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", sftp_route.selected_tree_label)
                cell.setProperty("secureCrtSftpTabRouteActiveTab", sftp_route.active_tab_label)
                cell.setProperty("secureCrtSftpTabRouteTabLabel", sftp_route.sftp_tab_label)
                cell.setProperty("secureCrtSftpTabRouteStatusStripObject", sftp_route.status_strip_object)
                cell.setProperty("secureCrtSftpTabRouteStatusFieldKey", sftp_route.status_field_key)
                cell.setProperty("secureCrtSftpTabRouteStatusFieldObject", sftp_route.status_field_object)
                cell.setProperty("secureCrtSftpTabRouteStatus", sftp_route.status_value)
                cell.setProperty("secureCrtSftpTabRouteTransferState", sftp_route.transfer_state)
                cell.setProperty("secureCrtSftpTabRouteRenderSource", sftp_route.render_source)
            cell.setToolTip(_safe_tooltip_html(tooltip_text))
            cell.setAccessibleName(full_text)
            cell.setMinimumWidth(compact_width)
            cell.setMinimumHeight(field.live_cell_height)
            cell.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(cell, compact_width)
        layout.addStretch(1)
        return panel

    @staticmethod
    def apply_securecrt_sftp_browser_action_route_properties(
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
            "secureCrtSftpBrowserRouteKey": route.key,
            "secureCrtSftpBrowserRouteRole": route.route_role,
            "secureCrtSftpBrowserTabRouteKey": route.sftp_tab_route_key,
            "secureCrtSftpBrowserObject": route.browser_object,
            "secureCrtSftpBrowserToolbarObject": route.toolbar_object,
            "secureCrtSftpBrowserPathObject": route.path_object,
            "secureCrtSftpBrowserTableObject": route.table_object,
            "secureCrtSftpBrowserRowObject": route.row_object,
            "secureCrtSftpBrowserQueueObject": route.queue_object,
            "secureCrtSftpBrowserSelectedProfile": route.selected_profile_name,
            "secureCrtSftpBrowserSelectedTreeLabel": route.selected_tree_label,
            "secureCrtSftpBrowserTabLabel": route.sftp_tab_label,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "secureCrtSftpBrowserActiveRowName": route.active_row_name,
            "secureCrtSftpBrowserQueueLabel": route.transfer_queue_label,
            route.queue_state_property: route.transfer_status,
            "secureCrtSftpBrowserActionObject": route.action_object,
            "secureCrtSftpBrowserActionKey": action_value,
            "secureCrtSftpBrowserActionLabel": route.action_label,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_property: triggered,
            route.captured_action_property: action_value if triggered else "",
            route.captured_status_property: status_value if triggered else "",
            route.live_triggered_property: triggered,
            route.live_action_property: action_value,
            route.live_status_property: status_value,
            "secureCrtSftpBrowserRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_securecrt_sftp_browser_action(self, action_key: str | None = None) -> None:
        route = gui_design_securecrt_sftp_browser_route()
        action_value = action_key or route.action_key
        status_value = (
            route.action_status
            if action_value == route.action_key
            else f"{action_value} queued"
        )
        queue = getattr(self, "securecrt_sftp_queue", None)
        if queue is not None:
            queue.setText(f"Queue: {route.transfer_queue_label} ({status_value})")
        route_widgets = (
            getattr(self, "securecrt_sftp_browser_panel", None),
            getattr(self, "securecrt_sftp_toolbar", None),
            getattr(self, "securecrt_sftp_path", None),
            getattr(self, "securecrt_sftp_table", None),
            queue,
            *getattr(self, "securecrt_sftp_action_buttons", []),
            getattr(self, "securecrt_sftp_active_row", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_securecrt_sftp_browser_action_route_properties(
                route_widget,
                route,
                triggered=True,
                action_key=action_value,
                status=status_value,
            )
        self.statusBar().showMessage(f"SecureCRT SFTP {action_value}: {status_value}")

    def build_securecrt_sftp_browser_evidence(self) -> QFrame:
        route = gui_design_securecrt_sftp_browser_route()
        actions_value = "|".join(route.toolbar_actions)
        route_props = {
            "secureCrtSftpBrowserRouteKey": route.key,
            "secureCrtSftpBrowserRouteRole": route.route_role,
            "secureCrtSftpBrowserTabRouteKey": route.sftp_tab_route_key,
            "secureCrtSftpBrowserObject": route.browser_object,
            "secureCrtSftpBrowserToolbarObject": route.toolbar_object,
            "secureCrtSftpBrowserPathObject": route.path_object,
            "secureCrtSftpBrowserTableObject": route.table_object,
            "secureCrtSftpBrowserRowObject": route.row_object,
            "secureCrtSftpBrowserQueueObject": route.queue_object,
            "secureCrtSftpBrowserSelectedProfile": route.selected_profile_name,
            "secureCrtSftpBrowserSelectedTreeLabel": route.selected_tree_label,
            "secureCrtSftpBrowserTabLabel": route.sftp_tab_label,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "secureCrtSftpBrowserActiveRowName": route.active_row_name,
            "secureCrtSftpBrowserQueueLabel": route.transfer_queue_label,
            "secureCrtSftpBrowserQueueState": route.transfer_status,
            "secureCrtSftpBrowserRenderSource": route.render_source,
        }
        panel = QFrame()
        panel.setObjectName(route.browser_object)
        for property_name, value in route_props.items():
            panel.setProperty(property_name, value)
        self.securecrt_sftp_browser_panel = panel
        self.apply_securecrt_sftp_browser_action_route_properties(panel, route)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(5)

        header = QHBoxLayout()
        title = _literal_label(f"SFTP - {route.sftp_tab_label}")
        title.setObjectName("secureCrtSftpTitle")
        title.setProperty("secureCrtSftpBrowserRouteKey", route.key)
        title.setProperty("secureCrtSftpBrowserTabLabel", route.sftp_tab_label)
        queue = _literal_label(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
        queue.setObjectName(route.queue_object)
        for property_name, value in route_props.items():
            queue.setProperty(property_name, value)
        self.securecrt_sftp_queue = queue
        self.apply_securecrt_sftp_browser_action_route_properties(queue, route)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(queue)
        layout.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName(route.toolbar_object)
        for property_name, value in route_props.items():
            toolbar.setProperty(property_name, value)
        self.securecrt_sftp_toolbar = toolbar
        self.apply_securecrt_sftp_browser_action_route_properties(toolbar, route)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.securecrt_sftp_action_buttons = []
        for action_key in route.toolbar_actions:
            action = QToolButton()
            action.setObjectName(route.action_object)
            action.setProperty("secureCrtSftpBrowserRouteKey", route.key)
            action.setProperty("secureCrtSftpBrowserActionKey", action_key)
            action.setProperty(route.toolbar_actions_property, actions_value)
            self.apply_securecrt_sftp_browser_action_route_properties(
                action,
                route,
                action_key=action_key,
            )
            self.securecrt_sftp_action_buttons.append(action)
            if action_key == route.action_key:
                self.securecrt_sftp_action_button = action
            action.clicked.connect(
                lambda _checked=False, key=action_key: self.handle_securecrt_sftp_browser_action(
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
        self.securecrt_sftp_path = path
        self.apply_securecrt_sftp_browser_action_route_properties(path, route)
        layout.addWidget(path)

        table = QFrame()
        table.setObjectName(route.table_object)
        for property_name, value in route_props.items():
            table.setProperty(property_name, value)
        self.securecrt_sftp_table = table
        self.apply_securecrt_sftp_browser_action_route_properties(table, route)
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(2)
        header_row = QLabel("Name        Size     Modified")
        header_row.setObjectName("secureCrtSftpHeader")
        table_layout.addWidget(header_row)
        for row in route.file_rows:
            row_frame = QFrame()
            row_frame.setObjectName(route.row_object)
            for property_name, value in route_props.items():
                row_frame.setProperty(property_name, value)
            row_frame.setProperty(route.row_name_property, row.name)
            row_frame.setProperty(route.row_kind_property, row.kind)
            row_frame.setProperty(route.row_selected_property, row.selected)
            row_frame.setProperty("secureCrtSftpBrowserRowKey", row.key)
            row_frame.setProperty("secureCrtSftpBrowserRowSize", row.size)
            row_frame.setProperty("secureCrtSftpBrowserRowModified", row.modified)
            self.apply_securecrt_sftp_browser_action_route_properties(row_frame, route)
            if row.name == route.active_row_name:
                self.securecrt_sftp_active_row = row_frame
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(4, 1, 4, 1)
            row_layout.setSpacing(8)
            name = _literal_label(row.name)
            name.setObjectName("secureCrtSftpRowName")
            size = _literal_label(row.size)
            size.setObjectName("secureCrtSftpRowSize")
            modified = _literal_label(row.modified)
            modified.setObjectName("secureCrtSftpRowModified")
            row_layout.addWidget(name, 2)
            row_layout.addWidget(size, 1)
            row_layout.addWidget(modified, 1)
            table_layout.addWidget(row_frame)
        layout.addWidget(table)
        return panel

    @staticmethod
    def apply_securecrt_command_window_send_route_properties(
        widget,
        route,
        chrome,
        *,
        submitted: bool = False,
        command: str | None = None,
        status: str | None = None,
    ) -> None:
        command_value = chrome.command if command is None else command
        status_value = chrome.status if status is None else status
        properties = {
            "secureCrtCommandRouteKey": route.key,
            "secureCrtCommandRouteRole": route.route_role,
            "secureCrtCommandRouteSourceWindowObject": route.source_window_object,
            "secureCrtCommandRouteTargetScopeObject": route.target_scope_object,
            "secureCrtCommandRouteCommandInputObject": route.command_input_object,
            "secureCrtCommandRouteSendControlObject": route.send_control_object,
            "secureCrtCommandRouteStatusObject": route.status_object,
            "secureCrtCommandRouteCommand": command_value,
            "secureCrtCommandRouteTargetScope": chrome.target_scope,
            "secureCrtCommandRouteSendLabel": chrome.send_label,
            "secureCrtCommandRouteStatus": status_value,
            route.captured_property: submitted,
            route.captured_command_property: command_value if submitted else "",
            route.captured_target_scope_property: chrome.target_scope if submitted else "",
            route.captured_status_property: status_value if submitted else "",
            route.signal_property: route.signal,
            route.secondary_signal_property: route.secondary_signal,
            route.handler_property: route.handler,
            "secureCrtCommandRouteLiveSubmitted": submitted,
            "secureCrtCommandRouteLiveCommand": command_value,
            "secureCrtCommandRouteLiveTargetScope": chrome.target_scope,
            "secureCrtCommandRouteLiveStatus": status_value,
            "secureCrtCommandRouteRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_securecrt_command_window_send(self, _checked: bool = False) -> None:
        chrome = gui_design_securecrt_command_window_chrome()
        route = gui_design_securecrt_command_window_send_route()
        command_input = getattr(self, "securecrt_command_input", None)
        command = command_input.text().strip() if command_input is not None else chrome.command
        if not command:
            command = chrome.command
            if command_input is not None:
                command_input.setText(command)
        status_text = "sent"
        status = getattr(self, "securecrt_command_status", None)
        if status is not None:
            status.setText(status_text)
        route_widgets = (
            getattr(self, "securecrt_command_window", None),
            getattr(self, "securecrt_command_target", None),
            command_input,
            getattr(self, "securecrt_command_send", None),
            status,
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_securecrt_command_window_send_route_properties(
                route_widget,
                route,
                chrome,
                submitted=True,
                command=command,
                status=status_text,
            )
        self.statusBar().showMessage(f"SecureCRT command sent to {chrome.target_scope}: {command}")

    def build_securecrt_command_window_evidence(self) -> QFrame:
        chrome = gui_design_securecrt_command_window_chrome()
        send_route = gui_design_securecrt_command_window_send_route()
        panel = QFrame()
        panel.setObjectName("secureCrtCommandWindow")
        self.securecrt_command_window = panel
        panel.setProperty("secureCrtCommandWindowKey", chrome.key)
        panel.setProperty("secureCrtCommandStaticHeaderHeight", chrome.static_header_height)
        panel.setProperty("secureCrtCommandStaticTitleX", chrome.static_title_x)
        panel.setProperty("secureCrtCommandStaticTitleY", chrome.static_title_y)
        panel.setProperty("secureCrtCommandStaticHelperX", chrome.static_helper_x)
        panel.setProperty("secureCrtCommandStaticHelperY", chrome.static_helper_y)
        panel.setProperty("secureCrtCommandStaticControlY", chrome.static_control_y)
        panel.setProperty("secureCrtCommandStaticTargetWidth", chrome.static_target_width)
        panel.setProperty("secureCrtCommandStaticInputX", chrome.static_input_x)
        panel.setProperty("secureCrtCommandStaticSendWidth", chrome.static_send_width)
        panel.setProperty("secureCrtCommandLiveTargetMinWidth", chrome.live_target_min_width)
        panel.setProperty("secureCrtCommandLiveSendMinWidth", chrome.live_send_min_width)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(
            chrome.live_margin_left,
            chrome.live_margin_top,
            chrome.live_margin_right,
            chrome.live_margin_bottom,
        )
        layout.setSpacing(chrome.live_spacing)

        header = QHBoxLayout()
        header.setSpacing(chrome.live_header_spacing)
        title = QLabel(chrome.title)
        title.setObjectName("secureCrtCommandTitle")
        helper = QLabel(chrome.helper)
        helper.setObjectName("secureCrtCommandHelper")
        header.addWidget(title)
        header.addWidget(helper)
        header.addStretch(1)
        layout.addLayout(header)

        command_row = QHBoxLayout()
        command_row.setSpacing(chrome.live_row_spacing)
        target = _literal_label(chrome.target_scope)
        target.setObjectName("secureCrtCommandTarget")
        self.securecrt_command_target = target
        target.setProperty("secureCrtCommandWindowKey", chrome.key)
        target.setProperty("secureCrtCommandStaticTargetWidth", chrome.static_target_width)
        target.setProperty("secureCrtCommandLiveTargetMinWidth", chrome.live_target_min_width)
        target.setMinimumWidth(chrome.live_target_min_width)
        command_input = QLineEdit(chrome.command)
        command_input.setObjectName("secureCrtCommandInput")
        self.securecrt_command_input = command_input
        command_input.setProperty("secureCrtCommandWindowKey", chrome.key)
        command_input.setProperty("secureCrtCommandStaticInputX", chrome.static_input_x)
        command_input.setProperty("secureCrtCommandStaticInputTextX", chrome.static_input_text_x)
        command_input.setProperty("secureCrtCommandStaticInputTextY", chrome.static_input_text_y)
        command_input.setPlaceholderText(chrome.command)
        command_input.returnPressed.connect(self.handle_securecrt_command_window_send)
        send = QPushButton(chrome.send_label)
        send.setObjectName("secureCrtCommandSend")
        self.securecrt_command_send = send
        send.setProperty("secureCrtCommandWindowKey", chrome.key)
        send.setProperty("secureCrtCommandStaticSendWidth", chrome.static_send_width)
        send.setProperty("secureCrtCommandLiveSendMinWidth", chrome.live_send_min_width)
        send.setMinimumWidth(chrome.live_send_min_width)
        send.clicked.connect(self.handle_securecrt_command_window_send)
        status = _literal_label(chrome.status)
        status.setObjectName("secureCrtCommandStatus")
        self.securecrt_command_status = status
        status.setProperty("secureCrtCommandWindowKey", chrome.key)
        route_widgets = (panel, target, command_input, send, status)
        for route_widget in route_widgets:
            self.apply_securecrt_command_window_send_route_properties(route_widget, send_route, chrome)
        command_row.addWidget(target)
        command_row.addWidget(command_input, 1)
        command_row.addWidget(send)
        command_row.addWidget(status)
        layout.addLayout(command_row)
        return panel

    def focus_securecrt_host(self) -> None:
        self.securecrt_host_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.securecrt_host_input.selectAll()

    def focus_securecrt_keyword(self) -> None:
        self.securecrt_keyword_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.securecrt_keyword_input.selectAll()
