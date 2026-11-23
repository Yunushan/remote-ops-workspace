from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .gui_designs import (
    gui_design_termius_files_browser_route,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_port_forward_route,
    gui_design_termius_snippet_route,
    gui_design_termius_sync_route,
)
from .gui_dialogs import _literal_label
from .gui_values import _required_gui_value, _safe_tooltip_html, _widget_style

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStatusBar, QStyle

    from .gui_terminal import TerminalPane


class TermiusWorkspace:
    """Build the Termius host, snippet and file browser surfaces."""

    if TYPE_CHECKING:
        def create_profile(self) -> None: ...
        def filter_profile_tree(self, text: str) -> None: ...
        def refresh_profiles(self) -> None: ...
        def standard_icon(self, icon_name: str) -> QStyle.StandardPixmap: ...
        def statusBar(self) -> QStatusBar: ...
        def toggle_product_terminal_drawer(self, drawer: QWidget, button: QToolButton) -> None: ...

    @staticmethod
    def apply_termius_snippet_run_route_properties(
        widget,
        route,
        *,
        triggered: bool = False,
        command: str | None = None,
        status: str | None = None,
    ) -> None:
        command_value = command or route.snippet_command
        status_value = status or route.snippet_state
        properties = {
            "termiusSnippetRouteKey": route.key,
            "termiusSnippetRouteRole": route.route_role,
            route.workflow_key_property: route.workflow_card_key,
            "termiusSnippetRouteWorkflowCardObject": route.workflow_card_object,
            "termiusSnippetRouteTitleObject": route.workflow_title_object,
            "termiusSnippetRoutePrimaryObject": route.workflow_primary_object,
            "termiusSnippetRouteSecondaryObject": route.workflow_secondary_object,
            "termiusSnippetRouteActionObject": route.action_object,
            "termiusSnippetRouteShortcutObject": route.shortcut_object,
            "termiusSnippetRouteIdentityObject": route.host_identity_object,
            "termiusSnippetRouteIdentityFieldKey": route.identity_field_key,
            "termiusSnippetRouteIdentityCellObject": route.identity_cell_object,
            route.active_tab_property: route.active_tab_label,
            "termiusSnippetRouteSelectedProfile": route.selected_profile_name,
            "termiusSnippetRouteTitle": route.workflow_title,
            route.command_property: command_value,
            route.status_property: status_value,
            "termiusSnippetRouteDetailLine": route.detail_line,
            "termiusSnippetRouteActionLabel": route.action_label,
            "termiusSnippetRouteShortcutSequence": route.shortcut_sequence,
            route.captured_property: triggered,
            route.captured_command_property: command_value if triggered else "",
            route.captured_target_profile_property: route.selected_profile_name if triggered else "",
            route.captured_status_property: status_value if triggered else "",
            route.signal_property: route.signal,
            route.secondary_signal_property: route.secondary_signal,
            route.handler_property: route.handler,
            route.live_triggered_property: triggered,
            route.live_command_property: command_value,
            route.live_target_profile_property: route.selected_profile_name,
            route.live_status_property: status_value,
            "termiusSnippetRouteRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_termius_snippet_run(self, _checked: bool = False) -> None:
        route = gui_design_termius_snippet_route()
        command = route.snippet_command
        status = "ran"
        route_widgets = (
            getattr(self, "termius_snippet_workflow_panel", None),
            getattr(self, "termius_snippet_card", None),
            getattr(self, "termius_snippet_title", None),
            getattr(self, "termius_snippet_primary", None),
            getattr(self, "termius_snippet_secondary", None),
            getattr(self, "termius_snippet_action", None),
            getattr(self, "termius_snippet_shortcut", None),
            getattr(self, "termius_snippet_identity_panel", None),
            getattr(self, "termius_snippet_identity_cell", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_termius_snippet_run_route_properties(
                route_widget,
                route,
                triggered=True,
                command=command,
                status=status,
            )
        self.statusBar().showMessage(f"Termius snippet ran on {route.selected_profile_name}: {command}")

    def build_termius_native_sftp_surface(
        self,
        terminal_pane: TerminalPane | None = None,
    ) -> QFrame:
        """Connected Termius-style dual-pane SFTP workspace.

        The widget tree deliberately mirrors the supplied desktop capture:
        dark navy chrome, host/path headers, two file tables, and a selected
        transfer row.  It is live Qt content so rows remain selectable and
        the toolbar routes through the same file-sync handler as the
        evidence panel below it.
        """
        route = gui_design_termius_files_browser_route()
        panel = QFrame()
        panel.setObjectName("termiusNativeSftpSurface")
        panel.setProperty("designPreset", "termius")
        panel.setProperty("termiusNativeSurfaceRole", "connected-dual-sftp")
        panel.setProperty("termiusFilesRouteKey", route.key)
        panel.setMinimumHeight(360)
        panel.setStyleSheet(
            "QFrame#termiusNativeSftpSurface { background: #111b2b; border: 1px solid #2b4668; }"
            "QLabel#termiusNativeSftpChip { background: #1b2c43; color: #c6d8ee; border: 1px solid #355476; padding: 4px 16px; border-radius: 10px; }"
            "QLabel#termiusNativeSftpChip[selected=true] { background: #2c4668; color: #f4f8ff; }"
            "QFrame#termiusNativeSftpPane { background: #111b2b; border: 0px; }"
            "QTreeWidget#termiusNativeSftpTable { background: #111b2b; color: #c7d8ec; border: 1px solid #2e496b; alternate-background-color: #15243a; }"
            "QTreeWidget#termiusNativeSftpTable::item:selected { background: #1d654b; color: #ffffff; border: 1px solid #38c98a; }"
            "QHeaderView::section { background: #16263c; color: #88a6c7; border: 0px; padding: 4px; }"
            "QToolButton#termiusNativeSftpAction { background: #1b2c43; color: #b7cbe2; border: 1px solid #3c5878; padding: 3px 10px; border-radius: 4px; }"
            "QFrame#termiusNativeTerminalDrawer { background: #0d1624; border: 1px solid #2e496b; }"
            "QTextEdit#terminalOutput { background: #0d1624; color: #d9e8f8; border: 0px;"
            "font-family: Consolas, 'Courier New'; font-size: 9pt; }"
            "QLineEdit#terminalInput { background: #111b2b; color: #f4f8ff; border: 1px solid #3c5878;"
            "padding: 3px 6px; font-family: Consolas, 'Courier New'; }"
        )
        root = QVBoxLayout(panel)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(7)
        top = QHBoxLayout()
        menu = QLabel("☰")
        menu.setStyleSheet("color: #d6e4f4; font-size: 15pt;")
        top.addWidget(menu)
        for label_text, active in (("Vaults", False), ("SFTP", True)):
            chip = QLabel(label_text)
            chip.setObjectName("termiusNativeSftpChip")
            chip.setProperty("selected", active)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top.addWidget(chip)
        top.addStretch(1)
        top.addWidget(_literal_label("edge-prod  ·  SSH"))
        terminal_toggle: QToolButton | None = None
        if terminal_pane is not None:
            terminal_toggle = QToolButton()
            terminal_toggle.setObjectName("termiusNativeTerminalToggle")
            terminal_toggle.setText("Terminal")
            terminal_toggle.setToolTip("Show or hide the connected terminal")
            top.addWidget(terminal_toggle)
        root.addLayout(top)

        panes = QHBoxLayout()
        panes.setSpacing(8)
        for pane_index in range(2):
            sftp_pane = QFrame()
            sftp_pane.setObjectName("termiusNativeSftpPane")
            pane_layout = QVBoxLayout(sftp_pane)
            pane_layout.setContentsMargins(4, 0, 4, 0)
            pane_layout.setSpacing(5)
            header = QHBoxLayout()
            identity = _literal_label("Ubuntu\noperator@edge-prod")
            identity.setStyleSheet("color: #e5eefb; font-weight: 600;")
            header.addWidget(identity)
            header.addStretch(1)
            for action_key in ("sync", "download"):
                button = QToolButton()
                button.setObjectName("termiusNativeSftpAction")
                button.setText(action_key.title())
                button.setToolTip(f"{action_key.title()} SFTP pane")
                button.clicked.connect(lambda _checked=False, key=action_key: self.handle_termius_files_sync(key))
                header.addWidget(button)
            pane_layout.addLayout(header)
            path = _literal_label("/  /home  /operator")
            path.setStyleSheet("background: #0d1624; color: #b8d4f2; padding: 5px; border: 1px solid #2e4767;")
            pane_layout.addWidget(path)
            table = QTreeWidget()
            table.setObjectName("termiusNativeSftpTable")
            table.setColumnCount(3)
            table.setHeaderLabels(["Name", "Date modified", "Size"])
            table.setRootIsDecorated(False)
            table.setAlternatingRowColors(True)
            table.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
            for index, (name, modified, size) in enumerate(
                (("..", "—", "—"), ("apps", "Jun 06, 2026", "—"), ("logs", "Jun 06, 2026", "—"), ("README.txt", "Jun 04, 2026", "3 KB"), (".bash_history", "Jun 06, 2026", "2 KB"))
            ):
                item = QTreeWidgetItem([name, modified, size])
                item.setData(0, Qt.ItemDataRole.UserRole, "folder" if index < 3 else "file")
                table.addTopLevelItem(item)
                if index == (1 if pane_index == 0 else 3):
                    table.setCurrentItem(item)
            table.itemDoubleClicked.connect(lambda item, _column: self.open_sftp_context_item(item))
            pane_layout.addWidget(table, 1)
            panes.addWidget(sftp_pane, 1)
        root.addLayout(panes, 1)
        if terminal_pane is not None:
            terminal_drawer = QFrame()
            terminal_drawer.setObjectName("termiusNativeTerminalDrawer")
            terminal_drawer.setProperty("productTerminalDrawerPreset", "termius")
            terminal_drawer.setProperty("productTerminalDrawerState", "closed")
            drawer_layout = QVBoxLayout(terminal_drawer)
            drawer_layout.setContentsMargins(4, 4, 4, 4)
            drawer_layout.addWidget(terminal_pane)
            terminal_pane.header.setVisible(False)
            terminal_pane.setProperty("termiusNativeTerminalEmbedded", True)
            terminal_pane.setMinimumSize(0, 0)
            terminal_pane.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            terminal_drawer.setVisible(False)
            root.addWidget(terminal_drawer)
            terminal_button = _required_gui_value(
                terminal_toggle,
                "Termius terminal toggle",
            )
            terminal_button.clicked.connect(
                lambda _checked=False, drawer=terminal_drawer, button=terminal_button:
                self.toggle_product_terminal_drawer(drawer, button)
            )
        return panel

    def open_sftp_context_item(self, item: QTreeWidgetItem | None) -> None:
        """Record a connected Termius SFTP row activation safely.

        The product-reference SFTP surface is a real selectable Qt view,
        but it does not own the MobaXterm SFTP dock's transfer controller.
        Keep double-click behavior explicit and observable without calling
        a method that only exists on ``MobaSftpDock``.
        """
        if item is None:
            return
        name = item.text(0).strip()
        kind = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if not name:
            return
        window = cast(QWidget, self)
        window.setProperty("termiusNativeSftpOpenedItem", name)
        window.setProperty("termiusNativeSftpOpenedKind", kind)
        surface = window.findChild(QFrame, "termiusNativeSftpSurface")
        if surface is not None:
            surface.setProperty("termiusNativeSftpOpenedItem", name)
            surface.setProperty("termiusNativeSftpOpenedKind", kind)

    def build_termius_header_chips_evidence(self) -> QFrame:
        sync_route = gui_design_termius_sync_route()
        port_forward_route = gui_design_termius_port_forward_route()
        panel = QFrame()
        panel.setObjectName("termiusHeaderChips")
        panel.setProperty("designPreset", "termius")
        panel.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
        panel.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
        panel.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
        panel.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
        panel.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
        panel.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
        panel.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
        panel.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
        panel.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
        panel.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
        panel.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
        panel.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
        panel.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
        panel.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
        panel.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
        panel.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(8)
        layout.addStretch(1)
        for chip in gui_design_termius_header_chips():
            label = QLabel(chip.label)
            label.setObjectName("termiusHeaderChip")
            label.setProperty("termiusHeaderChipKey", chip.key)
            label.setToolTip(chip.tooltip)
            label.setMinimumWidth(104)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if chip.key == sync_route.header_chip_key:
                label.setProperty("termiusSyncRouteKey", sync_route.key)
                label.setProperty("termiusSyncRouteRole", sync_route.route_role)
                label.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                label.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                label.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                label.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                label.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                label.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                label.setProperty("termiusSyncRouteState", sync_route.sync_state)
                label.setProperty("termiusSyncRouteChipLabel", chip.label)
                label.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
            if chip.key == port_forward_route.header_chip_key:
                label.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
                label.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
                label.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
                label.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
                label.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
                label.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
                label.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
                label.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
                label.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
                label.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
                label.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
                label.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
                label.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
                label.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
                label.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
                label.setProperty(port_forward_route.chip_label_property, chip.label)
                label.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
            layout.addWidget(label)
        return panel

    def build_termius_host_identity_strip_evidence(self) -> QFrame:
        strip = gui_design_termius_host_identity_strip()
        sync_route = gui_design_termius_sync_route()
        host_route = gui_design_termius_host_selection_route()
        port_forward_route = gui_design_termius_port_forward_route()
        snippet_route = gui_design_termius_snippet_route()
        files_route = gui_design_termius_files_browser_route()
        panel = QFrame()
        panel.setObjectName("termiusHostIdentityStrip")
        panel.setProperty("designPreset", "termius")
        panel.setProperty("termiusHostRouteKey", host_route.key)
        panel.setProperty("termiusHostRouteRole", host_route.route_role)
        panel.setProperty("termiusHostRouteSelectedProfile", host_route.selected_profile_name)
        panel.setProperty("termiusHostRouteSelectedTreeLabel", host_route.selected_tree_label)
        panel.setProperty("termiusHostRouteHostsPanelObject", host_route.hosts_panel_object)
        panel.setProperty("termiusHostRouteIdentityObject", host_route.host_identity_object)
        panel.setProperty("termiusHostRouteIdentityFieldKey", host_route.identity_field_key)
        panel.setProperty("termiusHostRouteIdentityCellObject", host_route.identity_cell_object)
        panel.setProperty("termiusHostRouteActiveTab", host_route.active_tab_label)
        panel.setProperty("termiusHostRouteTarget", host_route.target_value)
        panel.setProperty("termiusHostRouteProtocol", host_route.protocol_value)
        panel.setProperty("termiusHostRouteIdentityValue", host_route.host_value)
        panel.setProperty("termiusHostRouteRenderSource", host_route.render_source)
        panel.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
        panel.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
        panel.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
        panel.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
        panel.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
        panel.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
        panel.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
        panel.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
        panel.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
        panel.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
        panel.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
        panel.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
        panel.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
        panel.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
        panel.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
        panel.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
        panel.setProperty("termiusSnippetRouteKey", snippet_route.key)
        panel.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
        panel.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
        panel.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
        panel.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
        panel.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
        panel.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
        panel.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
        panel.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
        panel.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
        panel.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
        panel.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
        panel.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
        panel.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
        self.termius_snippet_identity_panel = panel
        self.apply_termius_snippet_run_route_properties(panel, snippet_route)
        panel.setProperty("termiusFilesRouteKey", files_route.key)
        panel.setProperty("termiusFilesRouteRole", files_route.route_role)
        panel.setProperty("termiusFilesRouteHostSelectionKey", files_route.host_selection_route_key)
        panel.setProperty("termiusFilesRouteIdentityObject", files_route.host_identity_object)
        panel.setProperty("termiusFilesRouteIdentityFieldKey", files_route.identity_field_key)
        panel.setProperty("termiusFilesRouteIdentityCellObject", files_route.identity_cell_object)
        panel.setProperty("termiusFilesRouteBrowserObject", files_route.files_browser_object)
        panel.setProperty("termiusFilesRouteActiveTab", files_route.active_tab_label)
        panel.setProperty("termiusFilesRouteSelectedProfile", files_route.selected_profile_name)
        panel.setProperty("termiusFilesRouteSelectedTreeLabel", files_route.selected_tree_label)
        panel.setProperty("termiusFilesRouteState", files_route.files_state)
        panel.setProperty("termiusFilesRoutePath", files_route.remote_path)
        panel.setProperty("termiusFilesRouteQueueState", files_route.transfer_status)
        panel.setProperty("termiusFilesRouteRenderSource", files_route.render_source)
        self.termius_files_identity_panel = panel
        self.apply_termius_files_sync_route_properties(panel, files_route)
        panel.setProperty("termiusHostIdentityFieldKeys", [field.key for field in strip.fields])
        panel.setProperty("termiusHostIdentityTitleWidth", strip.title_width)
        panel.setProperty("termiusHostIdentityStaticTitleX", strip.static_title_x)
        panel.setProperty("termiusHostIdentityStaticTitleY", strip.static_title_y)
        panel.setProperty("termiusHostIdentityStaticCellStartX", strip.static_cell_start_x)
        panel.setProperty("termiusHostIdentityStaticCellGap", strip.static_cell_gap)
        panel.setProperty("termiusHostIdentityLiveSpacing", strip.live_spacing)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(
            strip.live_margin_left,
            strip.live_margin_top,
            strip.live_margin_right,
            strip.live_margin_bottom,
        )
        layout.setSpacing(strip.live_spacing)

        title = QLabel(strip.title)
        title.setObjectName("termiusHostIdentityTitle")
        title.setMinimumWidth(strip.title_width)
        title.setMaximumWidth(strip.title_width)
        layout.addWidget(title)
        compact_values = {
            "host": "edge-prod",
            "identity": "prod-ed25519",
            "chain": "direct",
            "files": "SFTP",
            "forward": "8080 to :80",
            "snippet": "row status",
            "sync": "current",
        }
        compact_widths = {
            "host": 58,
            "identity": 74,
            "chain": 46,
            "files": 50,
            "forward": 68,
            "snippet": 68,
            "sync": 50,
        }
        for field in strip.fields:
            full_text = f"{field.label}: {field.value}"
            display_text = compact_values[field.key]
            compact_width = compact_widths[field.key]
            tooltip_text = f"{full_text}\n{field.tooltip}"
            cell = _literal_label(display_text)
            cell.setObjectName("termiusHostIdentityCell")
            cell.setProperty("termiusHostIdentityKey", field.key)
            cell.setProperty("termiusHostIdentityLabel", field.label)
            cell.setProperty("termiusHostIdentityValue", field.value)
            cell.setProperty("termiusHostIdentityWidth", field.static_width)
            cell.setProperty("termiusHostIdentityRole", field.role)
            cell.setProperty("termiusHostIdentityStaticY", field.static_y)
            cell.setProperty("termiusHostIdentityStaticHeight", field.static_height)
            cell.setProperty("termiusHostIdentityStaticLabelX", field.static_label_x)
            cell.setProperty("termiusHostIdentityStaticLabelY", field.static_label_y)
            cell.setProperty("termiusHostIdentityStaticValueX", field.static_value_x)
            cell.setProperty("termiusHostIdentityStaticValueY", field.static_value_y)
            cell.setProperty("termiusHostIdentityLiveMinWidth", field.live_min_width)
            cell.setProperty("termiusHostIdentityLiveCellHeight", field.live_cell_height)
            cell.setProperty("termiusHostIdentityFullText", full_text)
            cell.setProperty("termiusHostIdentityDisplayText", display_text)
            cell.setProperty("termiusHostIdentityTooltipText", tooltip_text)
            cell.setProperty("termiusHostIdentityCompactMinWidth", compact_width)
            cell.setToolTip(_safe_tooltip_html(tooltip_text))
            cell.setAccessibleName(full_text)
            cell.setMinimumWidth(compact_width)
            cell.setMinimumHeight(field.live_cell_height)
            cell.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if field.key == sync_route.identity_field_key:
                cell.setProperty("termiusSyncRouteKey", sync_route.key)
                cell.setProperty("termiusSyncRouteRole", sync_route.route_role)
                cell.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                cell.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                cell.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                cell.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                cell.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                cell.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                cell.setProperty("termiusSyncRouteState", sync_route.sync_state)
                cell.setProperty("termiusSyncRouteIdentityValue", field.value)
                cell.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
            if field.key == host_route.identity_field_key:
                cell.setProperty("termiusHostRouteKey", host_route.key)
                cell.setProperty("termiusHostRouteRole", host_route.route_role)
                cell.setProperty("termiusHostRouteSelectedProfile", host_route.selected_profile_name)
                cell.setProperty("termiusHostRouteSelectedTreeLabel", host_route.selected_tree_label)
                cell.setProperty("termiusHostRouteActiveTab", host_route.active_tab_label)
                cell.setProperty("termiusHostRouteTarget", host_route.target_value)
                cell.setProperty("termiusHostRouteProtocol", host_route.protocol_value)
                cell.setProperty("termiusHostRouteIdentityValue", host_route.host_value)
                cell.setProperty("termiusHostRouteRenderSource", host_route.render_source)
            if field.key == port_forward_route.identity_field_key:
                cell.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
                cell.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
                cell.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
                cell.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
                cell.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
                cell.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
                cell.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
                cell.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
                cell.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
                cell.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
                cell.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
                cell.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
                cell.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
                cell.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
                cell.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
                cell.setProperty("termiusPortForwardRouteIdentityValue", field.value)
                cell.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
            if field.key == snippet_route.identity_field_key:
                self.termius_snippet_identity_cell = cell
                cell.setProperty("termiusSnippetRouteKey", snippet_route.key)
                cell.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
                cell.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
                cell.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
                cell.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
                cell.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
                cell.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
                cell.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
                cell.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
                cell.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
                cell.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
                cell.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
                cell.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
                cell.setProperty("termiusSnippetRouteIdentityValue", field.value)
                cell.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
                self.apply_termius_snippet_run_route_properties(cell, snippet_route)
            if field.key == files_route.identity_field_key:
                self.termius_files_identity_cell = cell
                cell.setProperty("termiusFilesRouteKey", files_route.key)
                cell.setProperty("termiusFilesRouteRole", files_route.route_role)
                cell.setProperty("termiusFilesRouteHostSelectionKey", files_route.host_selection_route_key)
                cell.setProperty("termiusFilesRouteIdentityObject", files_route.host_identity_object)
                cell.setProperty("termiusFilesRouteIdentityFieldKey", files_route.identity_field_key)
                cell.setProperty("termiusFilesRouteIdentityCellObject", files_route.identity_cell_object)
                cell.setProperty("termiusFilesRouteBrowserObject", files_route.files_browser_object)
                cell.setProperty("termiusFilesRouteActiveTab", files_route.active_tab_label)
                cell.setProperty("termiusFilesRouteSelectedProfile", files_route.selected_profile_name)
                cell.setProperty("termiusFilesRouteSelectedTreeLabel", files_route.selected_tree_label)
                cell.setProperty("termiusFilesRouteIdentityValue", field.value)
                cell.setProperty("termiusFilesRouteState", files_route.files_state)
                cell.setProperty("termiusFilesRoutePath", files_route.remote_path)
                cell.setProperty("termiusFilesRouteQueueState", files_route.transfer_status)
                cell.setProperty("termiusFilesRouteRenderSource", files_route.render_source)
                self.apply_termius_files_sync_route_properties(cell, files_route)
            layout.addWidget(cell, compact_width)
        layout.addStretch(1)
        return panel

    @staticmethod
    def apply_termius_files_sync_route_properties(
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
            "termiusFilesRouteKey": route.key,
            "termiusFilesRouteRole": route.route_role,
            "termiusFilesRouteHostSelectionKey": route.host_selection_route_key,
            "termiusFilesRouteIdentityObject": route.host_identity_object,
            "termiusFilesRouteIdentityFieldKey": route.identity_field_key,
            "termiusFilesRouteIdentityCellObject": route.identity_cell_object,
            "termiusFilesRouteBrowserObject": route.files_browser_object,
            "termiusFilesRouteToolbarObject": route.toolbar_object,
            "termiusFilesRoutePathObject": route.path_object,
            "termiusFilesRouteTableObject": route.table_object,
            "termiusFilesRouteRowObject": route.row_object,
            "termiusFilesRouteQueueObject": route.queue_object,
            route.active_tab_property: route.active_tab_label,
            "termiusFilesRouteSelectedProfile": route.selected_profile_name,
            "termiusFilesRouteSelectedTreeLabel": route.selected_tree_label,
            route.identity_value_property: route.files_state,
            "termiusFilesRouteState": route.files_state,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "termiusFilesRouteActiveRowName": route.active_row_name,
            "termiusFilesRouteQueueLabel": route.transfer_queue_label,
            route.queue_state_property: route.transfer_status,
            "termiusFilesRouteActionObject": route.action_object,
            "termiusFilesRouteActionKey": action_value,
            "termiusFilesRouteActionLabel": route.action_label,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_property: triggered,
            route.captured_action_property: action_value if triggered else "",
            route.captured_status_property: status_value if triggered else "",
            route.live_triggered_property: triggered,
            route.live_action_property: action_value,
            route.live_status_property: status_value,
            "termiusFilesRouteRenderSource": route.render_source,
        }
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)

    def handle_termius_files_sync(self, action_key: str | None = None) -> None:
        route = gui_design_termius_files_browser_route()
        action_value = action_key or route.action_key
        status_value = (
            route.action_status
            if action_value == route.action_key
            else f"{action_value} queued"
        )
        queue = getattr(self, "termius_files_queue", None)
        if queue is not None:
            queue.setText(f"Queue: {route.transfer_queue_label} ({status_value})")
        route_widgets = (
            getattr(self, "termius_files_identity_panel", None),
            getattr(self, "termius_files_identity_cell", None),
            getattr(self, "termius_files_browser_panel", None),
            getattr(self, "termius_files_toolbar", None),
            getattr(self, "termius_files_path", None),
            getattr(self, "termius_files_table", None),
            queue,
            *getattr(self, "termius_files_action_buttons", []),
            getattr(self, "termius_files_active_row", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_termius_files_sync_route_properties(
                route_widget,
                route,
                triggered=True,
                action_key=action_value,
                status=status_value,
            )
        self.statusBar().showMessage(f"Termius files {action_value}: {status_value}")

    def build_termius_files_browser_evidence(self) -> QFrame:
        route = gui_design_termius_files_browser_route()
        actions_value = "|".join(route.toolbar_actions)
        route_props = {
            "termiusFilesRouteKey": route.key,
            "termiusFilesRouteRole": route.route_role,
            "termiusFilesRouteHostSelectionKey": route.host_selection_route_key,
            "termiusFilesRouteIdentityObject": route.host_identity_object,
            "termiusFilesRouteIdentityFieldKey": route.identity_field_key,
            "termiusFilesRouteIdentityCellObject": route.identity_cell_object,
            "termiusFilesRouteBrowserObject": route.files_browser_object,
            "termiusFilesRouteToolbarObject": route.toolbar_object,
            "termiusFilesRoutePathObject": route.path_object,
            "termiusFilesRouteTableObject": route.table_object,
            "termiusFilesRouteRowObject": route.row_object,
            "termiusFilesRouteQueueObject": route.queue_object,
            route.active_tab_property: route.active_tab_label,
            "termiusFilesRouteSelectedProfile": route.selected_profile_name,
            "termiusFilesRouteSelectedTreeLabel": route.selected_tree_label,
            route.identity_value_property: route.files_state,
            "termiusFilesRouteState": route.files_state,
            route.path_property: route.remote_path,
            route.toolbar_actions_property: actions_value,
            "termiusFilesRouteActiveRowName": route.active_row_name,
            "termiusFilesRouteQueueLabel": route.transfer_queue_label,
            "termiusFilesRouteQueueState": route.transfer_status,
            "termiusFilesRouteRenderSource": route.render_source,
        }
        panel = QFrame()
        panel.setObjectName(route.files_browser_object)
        for property_name, value in route_props.items():
            panel.setProperty(property_name, value)
        self.termius_files_browser_panel = panel
        self.apply_termius_files_sync_route_properties(panel, route)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(5)

        header = QHBoxLayout()
        title = _literal_label(f"Files - {route.selected_profile_name}")
        title.setObjectName("termiusFilesTitle")
        title.setProperty("termiusFilesRouteKey", route.key)
        title.setProperty("termiusFilesRouteState", route.files_state)
        queue = _literal_label(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
        queue.setObjectName(route.queue_object)
        for property_name, value in route_props.items():
            queue.setProperty(property_name, value)
        self.termius_files_queue = queue
        self.apply_termius_files_sync_route_properties(queue, route)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(queue)
        layout.addLayout(header)

        toolbar = QFrame()
        toolbar.setObjectName(route.toolbar_object)
        for property_name, value in route_props.items():
            toolbar.setProperty(property_name, value)
        self.termius_files_toolbar = toolbar
        self.apply_termius_files_sync_route_properties(toolbar, route)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(6)
        self.termius_files_action_buttons = []
        for action_key in route.toolbar_actions:
            action = QToolButton()
            action.setObjectName(route.action_object)
            action.setProperty("termiusFilesRouteKey", route.key)
            action.setProperty("termiusFilesRouteActionKey", action_key)
            action.setProperty(route.toolbar_actions_property, actions_value)
            self.apply_termius_files_sync_route_properties(action, route, action_key=action_key)
            self.termius_files_action_buttons.append(action)
            if action_key == route.action_key:
                self.termius_files_action_button = action
            action.clicked.connect(
                lambda _checked=False, key=action_key: self.handle_termius_files_sync(
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
        self.termius_files_path = path
        self.apply_termius_files_sync_route_properties(path, route)
        layout.addWidget(path)

        table = QFrame()
        table.setObjectName(route.table_object)
        for property_name, value in route_props.items():
            table.setProperty(property_name, value)
        self.termius_files_table = table
        self.apply_termius_files_sync_route_properties(table, route)
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(2)
        header_row = QLabel("Name        Size     Modified")
        header_row.setObjectName("termiusFilesHeader")
        table_layout.addWidget(header_row)
        for row in route.file_rows:
            row_frame = QFrame()
            row_frame.setObjectName(route.row_object)
            for property_name, value in route_props.items():
                row_frame.setProperty(property_name, value)
            row_frame.setProperty(route.row_name_property, row.name)
            row_frame.setProperty(route.row_kind_property, row.kind)
            row_frame.setProperty(route.row_selected_property, row.selected)
            row_frame.setProperty("termiusFilesRouteRowKey", row.key)
            row_frame.setProperty("termiusFilesRouteRowSize", row.size)
            row_frame.setProperty("termiusFilesRouteRowModified", row.modified)
            self.apply_termius_files_sync_route_properties(row_frame, route)
            if row.name == route.active_row_name:
                self.termius_files_active_row = row_frame
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(4, 1, 4, 1)
            row_layout.setSpacing(8)
            name = _literal_label(row.name)
            name.setObjectName("termiusFilesRowName")
            size = _literal_label(row.size)
            size.setObjectName("termiusFilesRowSize")
            modified = _literal_label(row.modified)
            modified.setObjectName("termiusFilesRowModified")
            row_layout.addWidget(name, 2)
            row_layout.addWidget(size, 1)
            row_layout.addWidget(modified, 1)
            table_layout.addWidget(row_frame)
        layout.addWidget(table)
        return panel

    def build_termius_hosts_chrome(self) -> QFrame:
        chrome = gui_design_termius_hosts_chrome()
        sync_route = gui_design_termius_sync_route()
        host_route = gui_design_termius_host_selection_route()
        panel = QFrame()
        panel.setObjectName("termiusHostsChrome")
        panel.setProperty("designPreset", "termius")
        panel.setProperty("termiusHostRouteKey", host_route.key)
        panel.setProperty("termiusHostRouteRole", host_route.route_role)
        panel.setProperty("termiusHostRouteSelectedProfile", host_route.selected_profile_name)
        panel.setProperty("termiusHostRouteSelectedTreeLabel", host_route.selected_tree_label)
        panel.setProperty("termiusHostRouteHostsPanelObject", host_route.hosts_panel_object)
        panel.setProperty("termiusHostRouteIdentityObject", host_route.host_identity_object)
        panel.setProperty("termiusHostRouteIdentityFieldKey", host_route.identity_field_key)
        panel.setProperty("termiusHostRouteIdentityCellObject", host_route.identity_cell_object)
        panel.setProperty("termiusHostRouteActiveTab", host_route.active_tab_label)
        panel.setProperty("termiusHostRouteTarget", host_route.target_value)
        panel.setProperty("termiusHostRouteProtocol", host_route.protocol_value)
        panel.setProperty("termiusHostRouteIdentityValue", host_route.host_value)
        panel.setProperty("termiusHostRouteRenderSource", host_route.render_source)
        panel.setProperty("termiusHostsActionKeys", [action.key for action in chrome.actions])
        panel.setProperty("termiusHostSearchPlaceholder", chrome.filter_placeholder)
        panel.setMaximumHeight(94)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setSpacing(5)
        title = QLabel(chrome.title)
        title.setObjectName("termiusHostsTitle")
        title_row.addWidget(title, 1)
        for action in chrome.actions:
            button = QToolButton()
            button.setObjectName("termiusHostsAction")
            button.setProperty("termiusHostsActionKey", action.key)
            button.setProperty("termiusHostsIconKey", action.icon_key)
            button.setProperty("termiusHostsActionLabel", action.label)
            button.setProperty("termiusHostsStaticX", action.static_x)
            button.setToolTip(action.tooltip)
            if action.key == sync_route.hosts_action_key:
                button.setProperty("termiusSyncRouteKey", sync_route.key)
                button.setProperty("termiusSyncRouteRole", sync_route.route_role)
                button.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                button.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                button.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                button.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                button.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                button.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                button.setProperty("termiusSyncRouteState", sync_route.sync_state)
                button.setProperty("termiusSyncRouteActionLabel", action.label)
                button.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
            button.setIcon(
                _widget_style(cast(QWidget, self)).standardIcon(
                    self.standard_icon(
                        self.termius_hosts_icon_name(action.icon_key)
                    )
                )
            )
            button.setIconSize(QSize(14, 14))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(24, 24))
            button.clicked.connect(lambda _checked=False, key=action.key: self.run_termius_hosts_action(key))
            title_row.addWidget(button)
        layout.addLayout(title_row)

        self.termius_host_search = QLineEdit()
        self.termius_host_search.setObjectName("termiusHostSearch")
        self.termius_host_search.setPlaceholderText(chrome.filter_placeholder)
        self.termius_host_search.setMinimumHeight(24)
        self.termius_host_search.textChanged.connect(self.filter_profile_tree)
        layout.addWidget(self.termius_host_search)
        panel.setVisible(False)
        return panel

    def termius_hosts_icon_name(self, icon_key: str) -> str:
        icon_map = {
            "plus": "SP_FileDialogNewFolder",
            "key": "SP_FileDialogDetailedView",
            "sync": "SP_BrowserReload",
        }
        return icon_map.get(icon_key, "SP_FileIcon")

    def run_termius_hosts_action(self, key: str) -> None:
        actions = {
            "new-host": self.create_profile,
            "keychain": lambda: self.statusBar().showMessage("Termius-style keychain: vault identity list"),
            "sync-hosts": self.refresh_profiles,
        }
        action = actions.get(key)
        if action is None:
            self.statusBar().showMessage(f"Termius Hosts action: {key}")
            return
        action()
