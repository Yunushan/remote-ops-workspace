from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyledItemDelegate,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .file_safety import write_json_atomic
from .gui_designs import (
    gui_design_interaction_state,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome,
)
from .gui_dialogs import _literal_label
from .gui_editors import profile_editor_protocols
from .gui_icons import draw_mremoteng_document_control_icon
from .gui_profile_tree import MREMOTENG_CONFIG_ROLE
from .gui_values import _safe_tooltip_html
from .models import Profile
from .paths import data_dir, ensure_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtCore import QAbstractItemModel, QLocale, QModelIndex
    from PyQt6.QtGui import QKeyEvent, QPainter
    from PyQt6.QtWidgets import QStatusBar, QStyleOptionViewItem, QTextEdit, QWidget

    from .gui_terminal import TerminalPane
    from .storage import ProfileStore


class _ConfigPropertyGrid(QTreeWidget):
    def keyPressEvent(self, event: QKeyEvent | None) -> None:  # noqa: N802
        key = cast("QKeyEvent", event)
        if (
            key.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2)
            and key.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
            and self.state() != QAbstractItemView.State.EditingState
        ):
            self.editItem(self.currentItem(), 1)
            key.accept()
            return
        super().keyPressEvent(event)


class _ConfigValueDelegate(QStyledItemDelegate):
    def __init__(self, grid: QTreeWidget, save_value: Callable[[str, str, str, str], None]) -> None:
        super().__init__(grid)
        self.save_value = save_value

    def displayText(self, value: object, locale: QLocale) -> str:  # noqa: N802
        return str(value or "—")

    def createEditor(  # noqa: N802
        self, parent: QWidget | None, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> QWidget:
        context = index.data(Qt.ItemDataRole.UserRole)
        editor: QComboBox | QLineEdit
        if context[1] == "protocol":
            editor = QComboBox(parent)
            editor.addItems([protocol.upper() for protocol in profile_editor_protocols()])
            editor.setCurrentText(context[2])

            def accept_protocol() -> None:
                self.commitData.emit(editor)
                self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)

            editor.activated.connect(accept_protocol)
        else:
            editor = QLineEdit(context[2], parent)
            editor.selectAll()
        editor.setProperty("configProperty", context)
        return editor

    def setEditorData(self, editor: QWidget | None, index: QModelIndex) -> None:  # noqa: N802
        """Keep in-progress input when a preceding cell's save refreshes this row."""

    def setModelData(  # noqa: N802
        self, editor: QWidget | None, model: QAbstractItemModel | None, index: QModelIndex,
    ) -> None:
        cell = cast("QLineEdit | QComboBox", editor)
        name, field, original = cell.property("configProperty")
        value = (cell.currentText() if isinstance(cell, QComboBox) else cell.text()).strip()
        if value != original:
            self.save_value(name, field, original, value)


class MRemoteNgWorkspace:
    """Build the mRemoteNG document panes, controls and property grid."""

    if TYPE_CHECKING:
        log: QTextEdit
        profile_list: QTreeWidget
        mremoteng_left_property_grid_panel: QFrame
        mremoteng_protocol_label: QLabel
        store: ProfileStore

        def active_terminal_pane(self) -> TerminalPane | None: ...
        def property(self, name: str) -> object: ...
        def all_terminal_panes(self) -> list[TerminalPane]: ...
        def selected_profile_name(self) -> str | None: ...
        def create_profile(self) -> None: ...
        def edit_selected_profile(self) -> None: ...
        def refresh_profiles(self) -> None: ...
        def select_profile(self, name: str) -> None: ...
        def filter_profile_tree(self, text: str) -> None: ...
        def generated_icon(
            self, size: int, draw: Callable[[QPainter, int], None], *, antialias: bool = True,
        ) -> QIcon: ...
        def profile_by_name(self, name: str | None) -> Profile | None: ...
        def selected_profile_for_workflow(self) -> Profile | None: ...
        def set_interaction_state(self, widget: QWidget, state: str) -> None: ...
        def show_external_tools_status(self, *_args: object) -> None: ...
        def statusBar(self) -> QStatusBar: ...

    def add_mremoteng_tab_options(self, tools: QMenu) -> None:
        options = QMenu("Options", tools)
        tools.addMenu(options)
        action = QAction("Double click on tab closes it", options)
        action.setCheckable(True)
        options.addAction(action)
        self.mremoteng_double_click_close = action

        path = data_dir() / "mremoteng-double-click-closes-tab.json"
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 64:
                raise ValueError("expected a small regular file")
            value = path.read_bytes().strip()
            if value not in (b"true", b"false"):
                raise ValueError("expected true or false")
            enabled = value == b"true"
        except FileNotFoundError:
            enabled = True
        except (OSError, ValueError) as exc:
            enabled = False
            self.statusBar().showMessage(f"Cannot read the mRemoteNG tab option: {exc}", 8000)
        action.setChecked(enabled)

        def save(checked: bool) -> None:
            try:
                write_json_atomic(path, checked, private=True)
            except OSError as exc:
                action.setChecked(not checked)
                self.statusBar().showMessage(f"Cannot save the mRemoteNG tab option: {exc}", 8000)

        action.triggered.connect(save)

    def save_mremoteng_property(self, name: str, field: str, original: str, value: str) -> str:
        def update(profiles: list[Profile], defaults: dict[str, dict[str, object]]) -> list[Profile]:
            positions = {profile.name: i for i, profile in enumerate(profiles)}
            position = positions[name]
            profile = profiles[position]
            data = profile.to_dict()
            effective = data[field] or defaults.get(profile.group, {}).get(field, "")
            expected = original.lower() if field == "protocol" else original
            if str(effective) != expected:
                raise ValueError("This property changed since editing began.")
            if field == "name" and value in positions:
                raise ValueError(f"profile already exists: {value}")
            profiles[position] = Profile.from_dict({**data, field: value})
            return profiles

        try:
            self.store.update_profiles(update, surface="profile-editor", action="replace")
        except (KeyError, OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Cannot save {field}: {exc}", 8000)
            return name
        return value if field == "name" else name

    def build_mremoteng_config_dock(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("mRemoteNgConfigDock")
        panel.setProperty("mRemoteNgDockViewVisible", True)
        self.mremoteng_property_grid_panel = panel
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Config"))
        heading.addStretch()
        edit = QToolButton()
        edit.setText("Edit…")
        edit.setAccessibleName("Edit selected connection")
        edit.clicked.connect(self.edit_selected_profile)
        heading.addWidget(edit)
        layout.addLayout(heading)
        grid = _ConfigPropertyGrid()
        grid.setObjectName("mRemoteNgConnectionProperties")
        grid.setColumnCount(2)
        grid.setHeaderHidden(True)
        grid.setRootIsDecorated(False)
        grid.setUniformRowHeights(True)
        grid.setAccessibleName("Effective connection properties")
        grid.setToolTip("Click a value or press Enter to edit it. Enter applies the value. Escape cancels.")
        fields = {
            "Name": "name", "Protocol": "protocol", "Hostname": "host",
            "Port": "port", "Username": "username", "Group": "group",
        }
        rows = [QTreeWidgetItem(grid, [label, ""]) for label in fields]
        for row in rows:
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
        grid.setCurrentItem(rows[0], 1)
        grid.resizeColumnToContents(0)
        refresh_timer = QTimer(grid)
        refresh_timer.setSingleShot(True)
        renames: dict[str, str] = {}
        refreshing = False

        def save_value(name: str, field: str, original: str, value: str) -> None:
            if name != self.selected_profile_name():
                return
            current_name = renames.get(name, name)
            new_name = self.save_mremoteng_property(current_name, field, original, value)
            if new_name != current_name:
                renames[name] = new_name
            refresh_timer.start(0)

        delegate = _ConfigValueDelegate(grid, save_value)
        grid.setItemDelegateForColumn(1, delegate)
        grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        grid.itemClicked.connect(lambda row, column: grid.editItem(row, 1) if column == 1 else None)
        grid.setMaximumHeight(145)
        layout.addWidget(grid)
        empty = QLabel("Select a connection to view its properties.")
        empty.setWordWrap(True)
        layout.addWidget(empty)
        preview = bool(self.property("guiPreviewSamples"))
        if not preview:
            self.mremoteng_protocol_label.setToolTip("Selected connection protocol")

        def update_config(current: QTreeWidgetItem | None) -> None:
            if refreshing:
                return
            values = current.data(0, MREMOTENG_CONFIG_ROLE) if current is not None else None
            active = grid.indexWidget(grid.currentIndex())
            if active is not None:
                name, field, original = active.property("configProperty")
                if values and renames.get(name, name) == values[0]:
                    active.setProperty("configProperty", (values[0], field, original))
                else:
                    delegate.closeEditor.emit(active, QStyledItemDelegate.EndEditHint.RevertModelCache)
            if not preview:
                self.mremoteng_protocol_label.setText(values[1] if values else "")
            edit.setEnabled(bool(values))
            grid.setVisible(bool(values))
            empty.setVisible(not values)
            for row, field, value in zip(rows, fields.values(), values or [""] * len(rows), strict=True):
                row.setText(1, value)
                row.setData(1, Qt.ItemDataRole.UserRole, (values[0], field, value) if values else None)

        def refresh() -> None:
            nonlocal refreshing
            selected = self.selected_profile_name()
            refreshing = True
            try:
                self.refresh_profiles()
                new_name = renames.get(selected or "")
                if new_name is not None:
                    self.select_profile(new_name)
            finally:
                refreshing = False
            update_config(self.profile_list.currentItem())
            renames.clear()

        refresh_timer.timeout.connect(refresh)
        self.profile_list.currentItemChanged.connect(update_config)
        update_config(self.profile_list.currentItem())
        return panel

    def build_mremoteng_start_page(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("welcomePanel")
        panel.setProperty("welcomePreferredWidth", 620)
        panel.setProperty("welcomeMaximumWidth", 1060)
        layout = QVBoxLayout(panel)
        layout.addWidget(self.build_mremoteng_document_controls_evidence())
        instructions = QLabel("Double-click a saved connection in the Connections tree to open a session.")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        new_connection = QPushButton("New connection…")
        new_connection.clicked.connect(self.create_profile)
        layout.addWidget(new_connection, 0, Qt.AlignmentFlag.AlignLeft)
        return panel

    def build_mremoteng_runtime_document_surface(
        self,
        pane: TerminalPane | None = None,
    ) -> QFrame:
        """Build the docked split-document canvas used by mRemoteNG."""
        panel = QFrame()
        panel.setObjectName("mRemoteNgRuntimeDocumentSurface")
        panel.setProperty("designPreset", "mremoteng")
        panel.setProperty("mRemoteNgRuntimeSurfaceRole", "split-document-canvas")
        panel.setMinimumHeight(310)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        panel.setStyleSheet(
            "QFrame#mRemoteNgRuntimeDocumentSurface {"
            "background: #ececf1; border: 1px solid #a9a9b0; }"
            "QLabel#mRemoteNgRuntimeTab {"
            "background: #ffffff; color: #263746; padding: 5px 8px;"
            "border: 1px solid #a9b8c7; }"
            "QFrame#mRemoteNgRuntimePane {"
            "background: #000000; border: 1px solid #777777; }"
            "QPlainTextEdit#mRemoteNgRuntimeTranscript {"
            "background: #000000; color: #e8e8e8; border: 0px;"
            "font-family: Consolas, 'Courier New'; font-size: 9pt; }"
            "QWidget#terminalPane { background: #000000; border: 0px; }"
            "QTextEdit#terminalOutput { background: #000000; color: #e8e8e8; border: 0px;"
            "font-family: Consolas, 'Courier New'; font-size: 9pt; }"
            "QLineEdit#terminalInput { background: #111111; color: #f2f2f2; border: 1px solid #777777;"
            "padding: 3px 6px; font-family: Consolas, 'Courier New'; }"
            "QLabel#mRemoteNgRuntimeNotification {"
            "background: #ffffff; color: #4a4a4a; padding: 5px 8px;"
            "border: 1px solid #a7b1bc; }"
        )
        root = QVBoxLayout(panel)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        tabs = QHBoxLayout()
        tabs.setSpacing(2)
        for label_text in ("edge-prod [SSH]", "win-admin [RDP]", "sftp-ops"):
            tab = QLabel(label_text)
            tab.setObjectName("mRemoteNgRuntimeTab")
            tab.setProperty("mRemoteNgRuntimeTabLabel", label_text)
            tabs.addWidget(tab)
        tabs.addStretch(1)
        root.addLayout(tabs)

        panes = QHBoxLayout()
        panes.setSpacing(5)
        rdp = QFrame()
        rdp.setObjectName("mRemoteNgRuntimePane")
        rdp_layout = QVBoxLayout(rdp)
        rdp_layout.setContentsMargins(10, 8, 10, 8)
        rdp_title = QLabel("Exchange 1 · RDP")
        rdp_title.setStyleSheet("color: #f2f2f2; font-weight: 600;")
        rdp_layout.addWidget(rdp_title)
        rdp_screen = QLabel("Recycle Bin\n\n\n\n\n\n\n\n\n\n\n\n                 19:08")
        rdp_screen.setStyleSheet("color: #f2f2f2; background: #111111; padding: 8px;")
        rdp_screen.setMinimumHeight(205)
        rdp_layout.addWidget(rdp_screen, 1)

        ssh = QFrame()
        ssh.setObjectName("mRemoteNgRuntimePane")
        ssh_layout = QVBoxLayout(ssh)
        ssh_layout.setContentsMargins(7, 5, 7, 5)
        ssh_title = QLabel("Proxy Server · SSH2")
        ssh_title.setStyleSheet("color: #f2f2f2; font-weight: 600;")
        ssh_layout.addWidget(ssh_title)
        if pane is None:
            transcript = QPlainTextEdit()
            transcript.setObjectName("mRemoteNgRuntimeTranscript")
            transcript.setReadOnly(True)
            transcript.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            transcript.setPlainText(
                "Using username 'operator'.\n"
                "Authenticated with public key from agent\n"
                "Welcome to Ubuntu 22.04 LTS\n\n"
                "System load:  0.01      Processes: 173\n"
                "Memory usage: 37%       Users logged in: 0\n"
                "IP address for ens160: 10.32.0.42\n\n"
                "operator@edge-prod:~$"
            )
            ssh_layout.addWidget(transcript, 1)
        else:
            pane.header.setVisible(False)
            pane.setProperty("mRemoteNgRuntimeEmbedded", True)
            pane.setMinimumSize(0, 0)
            pane.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            ssh_layout.addWidget(pane, 1)
        panes.addWidget(rdp, 3)
        panes.addWidget(ssh, 2)
        root.addLayout(panes, 1)

        notification = QLabel("Notifications   ·   Connected to Proxy Server via SSH2   ·   Exchange 1 opened")
        notification.setObjectName("mRemoteNgRuntimeNotification")
        notification.setProperty("mRemoteNgRuntimeNotificationState", "connected")
        root.addWidget(notification)
        return panel

    @staticmethod
    def apply_mremoteng_reconnect_route_properties(
        widget,
        route,
        *,
        triggered: bool = False,
        reconnect_state: str | None = None,
        profile_name: str | None = None,
    ) -> None:
        state_value = reconnect_state or route.workspace_state
        profile_name = route.selected_profile_name if profile_name is None else profile_name
        properties = {
            "mRemoteNgConnectionRouteKey": route.key,
            "mRemoteNgConnectionRouteRole": route.route_role,
            "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
            "mRemoteNgConnectionRouteSelectedTreeLabel": route.selected_tree_label,
            "mRemoteNgConnectionRouteDocumentControlsObject": route.document_controls_object,
            "mRemoteNgConnectionRouteDocumentControlKey": route.document_control_key,
            "mRemoteNgConnectionRouteDocumentControlObject": route.document_control_object,
            "mRemoteNgConnectionRoutePropertyGridObject": route.property_grid_object,
            "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
            "mRemoteNgConnectionRoutePropertyCellObject": route.property_cell_object,
            route.tab_label_property: route.active_tab_label,
            "mRemoteNgConnectionRouteProtocol": route.protocol,
            "mRemoteNgConnectionRouteState": route.workspace_state,
            route.property_value_property: route.property_value,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_property: triggered,
            route.captured_state_property: state_value if triggered else "",
            route.captured_profile_property: profile_name if triggered else "",
            route.live_triggered_property: triggered,
            route.live_state_property: state_value,
            route.live_profile_property: profile_name,
            "mRemoteNgConnectionRouteRenderSource": route.render_source,
        }
        for property_name, property_value in properties.items():
            widget.setProperty(property_name, property_value)

    def handle_mremoteng_document_reconnect(self, _checked: bool = False) -> None:
        route = gui_design_mremoteng_connection_document_route()
        pane = self.active_terminal_pane()
        if pane is None:
            selected = self.selected_profile_name()
            pane = next((
                session for session in reversed(self.all_terminal_panes())
                if session.profile is not None and session.profile.name == selected
            ), None)
        name = ""
        if pane is not None:
            name = pane.profile.name if pane.profile is not None else pane.plan.title
            pane.restart()
        route_widgets = (
            getattr(self, "profile_list", None),
            getattr(self, "mremoteng_document_controls_panel", None),
            getattr(self, "mremoteng_reconnect_button", None),
            getattr(self, "mremoteng_property_grid_panel", None),
            getattr(self, "mremoteng_connection_route_row", None),
            getattr(self, "mremoteng_connection_route_effective_cell", None),
        )
        for route_widget in route_widgets:
            if route_widget is None:
                continue
            self.apply_mremoteng_reconnect_route_properties(
                route_widget,
                route,
                triggered=pane is not None,
                reconnect_state=route.reconnect_state if pane is not None else "no open connection",
                profile_name=name,
            )
        self.statusBar().showMessage(
            f"Reconnect requested for {name}" if pane is not None
            else "Open a connection before reconnecting."
        )

    def save_mremoteng_document_artifact(self) -> Path:
        profile = self.selected_profile_for_workflow()
        if profile is None:
            raise ValueError("Select a connection before saving its document.")
        profile_name = profile.name
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", profile_name).strip(".-")
        artifact_path = (
            ensure_data_dir()
            / "gui-artifacts"
            / "mremoteng"
            / f"{safe_name or 'connection'}-document.json"
        )
        payload = {
            "schema": "row.gui.mremoteng-document.v1",
            "state": "saved",
            "profile": {
                "name": profile_name,
                "protocol": profile.protocol,
                "target": profile.display_target,
            },
        }
        write_json_atomic(artifact_path, payload, private=True)
        return artifact_path

    def handle_mremoteng_document_control(
        self,
        action_key: str,
        checked: bool = False,
    ) -> None:
        buttons = getattr(self, "mremoteng_document_control_buttons", {})
        button = buttons.get(action_key)
        panel = getattr(self, "mremoteng_document_controls_panel", None)
        if action_key == "save":
            try:
                artifact_path = self.save_mremoteng_document_artifact()
                artifact_size = artifact_path.stat().st_size
            except (OSError, ValueError) as exc:
                for widget in (panel, button):
                    if widget is None:
                        continue
                    widget.setProperty("mRemoteNgDocumentSaveTriggered", False)
                    widget.setProperty(
                        "mRemoteNgDocumentSaveError",
                        str(exc),
                    )
                    widget.setProperty("mRemoteNgDocumentSaveArtifact", "")
                    widget.setProperty("mRemoteNgDocumentSaveArtifactPath", "")
                    widget.setProperty("mRemoteNgDocumentSaveArtifactBytes", 0)
                self.log.append("MREMOTENG DOCUMENT SAVE FAILED")
                self.statusBar().showMessage(
                    f"Could not save connection document: {exc}"
                )
                return
            for widget in (panel, button):
                if widget is None:
                    continue
                widget.setProperty("mRemoteNgDocumentSaveTriggered", True)
                widget.setProperty("mRemoteNgDocumentSaveError", "")
                widget.setProperty(
                    "mRemoteNgDocumentSaveArtifact",
                    artifact_path.name,
                )
                widget.setProperty(
                    "mRemoteNgDocumentSaveArtifactPath",
                    str(artifact_path),
                )
                widget.setProperty(
                    "mRemoteNgDocumentSaveArtifactBytes",
                    artifact_size,
                )
            self.log.append(
                f"MREMOTENG DOCUMENT SAVED: {artifact_path.name}"
            )
            self.statusBar().showMessage(
                f"mRemoteNG document saved: {artifact_path.name}"
            )
            return
        if action_key == "reconnect":
            self.handle_mremoteng_document_reconnect(checked)
            return
        if action_key == "external-tool":
            for widget in (panel, button):
                if widget is not None:
                    widget.setProperty(
                        "mRemoteNgExternalToolsWorkflowOpened",
                        True,
                    )
            self.show_external_tools_status()
            return
        if action_key == "dock-view":
            dock = getattr(self, "mremoteng_property_grid_panel", None)
            visible = bool(checked)
            for view in (dock, self.mremoteng_left_property_grid_panel):
                if view is not None:
                    view.setVisible(visible)
                    view.setProperty("mRemoteNgDockViewVisible", visible)
            if button is not None:
                button.setChecked(visible)
                self.set_interaction_state(
                    button,
                    "checked" if visible else "normal",
                )
            if panel is not None:
                panel.setProperty("mRemoteNgDockViewVisible", visible)
            self.statusBar().showMessage(
                f"mRemoteNG property dock {'shown' if visible else 'hidden'}"
            )
            return
        raise RuntimeError(f"unsupported mRemoteNG document control: {action_key}")

    def build_mremoteng_document_controls_evidence(self) -> QFrame:
        chrome = gui_design_mremoteng_document_toolbar_chrome()
        route = gui_design_mremoteng_connection_document_route()
        filter_route = gui_design_mremoteng_document_filter_route()
        state = gui_design_interaction_state("mremoteng")
        panel = QFrame()
        panel.setObjectName("mRemoteNgDocumentControls")
        panel.setProperty("designPreset", "mremoteng")
        panel.setProperty("mRemoteNgConnectionRouteKey", route.key)
        panel.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
        panel.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
        panel.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
        panel.setProperty("mRemoteNgConnectionRoutePropertyGridObject", route.property_grid_object)
        panel.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
        panel.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
        panel.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
        panel.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
        panel.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
        panel.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
        panel.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
        self.mremoteng_document_controls_panel = panel
        self.apply_mremoteng_reconnect_route_properties(panel, route)
        filter_route_properties = {
            "mRemoteNgDocumentFilterRouteKey": filter_route.key,
            "mRemoteNgDocumentFilterRouteRole": filter_route.route_role,
            "mRemoteNgDocumentFilterRouteDocumentControlsObject": filter_route.document_controls_object,
            "mRemoteNgDocumentFilterRouteFilterObject": filter_route.filter_object,
            "mRemoteNgDocumentFilterRouteSelectedTreeObject": filter_route.selected_tree_object,
            "mRemoteNgDocumentFilterRouteSelectedProfile": filter_route.selected_profile_name,
            "mRemoteNgDocumentFilterRouteMatchedTreeLabel": filter_route.selected_tree_label,
            "mRemoteNgDocumentFilterRouteMatchedProtocol": filter_route.matched_protocol,
            "mRemoteNgDocumentFilterRouteMatchedState": filter_route.matched_state,
            "mRemoteNgDocumentFilterRouteQuery": filter_route.expected_query,
            "mRemoteNgDocumentFilterRoutePlaceholder": filter_route.expected_placeholder,
            "mRemoteNgDocumentFilterRouteActiveTab": filter_route.active_tab_label,
            "mRemoteNgDocumentFilterRouteSignal": filter_route.change_signal,
            "mRemoteNgDocumentFilterRouteHandler": filter_route.handler_name,
            "mRemoteNgDocumentFilterRouteRenderSource": filter_route.render_source,
        }
        for property_name, property_value in filter_route_properties.items():
            panel.setProperty(property_name, property_value)
        panel.setProperty("mRemoteNgDocumentTitleWidth", chrome.title_width)
        panel.setProperty("mRemoteNgDocumentStaticHeight", chrome.static_height)
        panel.setProperty("mRemoteNgDocumentStaticButtonStartX", chrome.static_button_start_x)
        panel.setProperty("mRemoteNgDocumentStaticButtonGap", chrome.static_button_gap)
        panel.setProperty("mRemoteNgDocumentStaticFilterWidth", chrome.static_filter_width)
        panel.setProperty("mRemoteNgDocumentStaticFilterY", chrome.static_filter_y)
        panel.setProperty("mRemoteNgDocumentStaticFilterHeight", chrome.static_filter_height)
        panel.setProperty("mRemoteNgDocumentLiveSpacing", chrome.live_spacing)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(
            chrome.live_margin_left,
            chrome.live_margin_top,
            chrome.live_margin_right,
            chrome.live_margin_bottom,
        )
        layout.setSpacing(chrome.live_spacing)

        preview = bool(self.property("guiPreviewSamples"))
        title = QLabel(chrome.title if preview else "Connection")
        title.setObjectName("mRemoteNgDocumentTitle")
        title.setMinimumWidth(chrome.title_width)
        title.setMaximumWidth(chrome.title_width)
        layout.addWidget(title)
        self.mremoteng_document_control_buttons = {}
        for control in gui_design_mremoteng_document_controls():
            button = QToolButton()
            button.setObjectName("mRemoteNgDocumentControl")
            button.setProperty("mRemoteNgDocumentControlKey", control.key)
            button.setProperty("mRemoteNgDocumentIconKey", control.icon_key)
            button.setProperty("mRemoteNgDocumentStaticWidth", control.static_width)
            button.setProperty("mRemoteNgDocumentStaticY", control.static_y)
            button.setProperty("mRemoteNgDocumentStaticHeight", control.static_height)
            button.setProperty("mRemoteNgDocumentStaticIconX", control.static_icon_x)
            button.setProperty("mRemoteNgDocumentStaticIconY", control.static_icon_y)
            button.setProperty("mRemoteNgDocumentStaticIconSize", control.static_icon_size)
            button.setProperty("mRemoteNgDocumentStaticLabelX", control.static_label_x)
            button.setProperty("mRemoteNgDocumentStaticLabelY", control.static_label_y)
            button.setProperty("mRemoteNgDocumentLiveIconSize", control.live_icon_size)
            button.setProperty("mRemoteNgDocumentLiveMinWidth", control.live_min_width)
            button.setProperty("mRemoteNgDocumentLiveButtonHeight", control.live_button_height)
            button.setProperty("mRemoteNgDocumentRenderSource", control.render_source)
            self.mremoteng_document_control_buttons[control.key] = button
            if control.key == route.document_control_key:
                button.setProperty("mRemoteNgConnectionRouteKey", route.key)
                button.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
                button.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
                button.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
                button.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
                button.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
                button.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
                button.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                button.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
                button.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
                button.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                button.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                button.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
                button.setProperty(route.control_active_property, "true")
                self.mremoteng_reconnect_button = button
                self.apply_mremoteng_reconnect_route_properties(button, route)
            else:
                button.setProperty(route.control_active_property, "false")
            button.setText(control.label)
            button.setToolTip(
                "Save a JSON summary of the selected connection" if control.key == "save" and not preview
                else control.tooltip
            )
            dock_checked = control.key == "dock-view" and bool(
                self.mremoteng_left_property_grid_panel.property("mRemoteNgDockViewVisible")
            )
            control_state = "checked" if control.key == "external-tool" or dock_checked else "normal"
            button.setCheckable(control.key == "dock-view")
            button.setChecked(dock_checked)
            self.set_interaction_state(button, control_state)
            button.setIcon(self.mremoteng_document_control_icon(control.icon_key, size=control.live_icon_size))
            button.setIconSize(QSize(control.live_icon_size, control.live_icon_size))
            button.setMinimumWidth(control.live_min_width)
            button.setMinimumHeight(control.live_button_height)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.clicked.connect(
                lambda checked=False, key=control.key: self.handle_mremoteng_document_control(
                    key,
                    checked,
                )
            )
            layout.addWidget(button)
        layout.addStretch(1)

        filter_input = QLineEdit()
        filter_input.setObjectName("mRemoteNgDocumentFilter")
        filter_input.setPlaceholderText(chrome.filter_placeholder)
        filter_input.setProperty("mRemoteNgDocumentFilterWidth", chrome.live_filter_width)
        filter_input.setProperty("mRemoteNgDocumentFilterHeight", chrome.live_filter_height)
        for property_name, property_value in filter_route_properties.items():
            filter_input.setProperty(property_name, property_value)
        filter_input.setMinimumWidth(chrome.live_filter_width)
        filter_input.setMaximumWidth(chrome.live_filter_width)
        filter_input.setFixedHeight(chrome.live_filter_height)
        self.mremoteng_document_filter = filter_input
        self.set_interaction_state(
            filter_input,
            "focused" if state.focused_control == "tree-filter" else "normal",
        )
        filter_input.textChanged.connect(self.filter_profile_tree)
        # Match mRemoteNG's document-toolbar geometry: the filter is pinned
        # to the chrome's explicit top inset instead of being vertically
        # centered by platform-dependent QLineEdit size hints.  Native
        # Windows fonts make the line edit four pixels taller than Qt's
        # offscreen fallback, so centering otherwise drifts the control
        # below the shared reference boundary.
        layout.addWidget(filter_input, 0, Qt.AlignmentFlag.AlignTop)
        return panel

    def mremoteng_document_control_icon(self, icon_key: str, *, size: int) -> QIcon:
        return self.generated_icon(
            size,
            lambda painter, logical_size: draw_mremoteng_document_control_icon(
                painter, icon_key, logical_size
            ),
        )

    def build_mremoteng_property_grid_evidence(self) -> QFrame:
        chrome = gui_design_mremoteng_property_grid_chrome()
        route = gui_design_mremoteng_connection_document_route()
        inheritance_route = gui_design_mremoteng_inheritance_route()
        inheritance_route_properties = {
            "mRemoteNgInheritanceRouteKey": inheritance_route.key,
            "mRemoteNgInheritanceRouteRole": inheritance_route.route_role,
            "mRemoteNgInheritanceRouteWorkflowKey": inheritance_route.workflow_card_key,
            "mRemoteNgInheritanceRouteWorkflowCardObject": inheritance_route.workflow_card_object,
            "mRemoteNgInheritanceRouteTitleObject": inheritance_route.workflow_title_object,
            "mRemoteNgInheritanceRoutePrimaryObject": inheritance_route.workflow_primary_object,
            "mRemoteNgInheritanceRouteSecondaryObject": inheritance_route.workflow_secondary_object,
            "mRemoteNgInheritanceRoutePropertyGridObject": inheritance_route.property_grid_object,
            "mRemoteNgInheritanceRoutePropertyRowKey": inheritance_route.property_row_key,
            "mRemoteNgInheritanceRoutePropertyCellObject": inheritance_route.property_cell_object,
            "mRemoteNgInheritanceRouteActiveTab": inheritance_route.active_tab_label,
            "mRemoteNgInheritanceRouteSelectedProfile": inheritance_route.selected_profile_name,
            "mRemoteNgInheritanceRouteSelectedTreeLabel": inheritance_route.selected_tree_label,
            "mRemoteNgInheritanceRouteTitle": inheritance_route.workflow_title,
            "mRemoteNgInheritanceRouteInheritedPropertyLabel": inheritance_route.inherited_property_label,
            "mRemoteNgInheritanceRouteInheritedValue": inheritance_route.inherited_value,
            "mRemoteNgInheritanceRouteInheritedSource": inheritance_route.inherited_source,
            "mRemoteNgInheritanceRouteState": inheritance_route.inheritance_state,
            "mRemoteNgInheritanceRouteRenderSource": inheritance_route.render_source,
        }
        panel = QFrame()
        panel.setObjectName("mRemoteNgPropertyGrid")
        panel.setProperty("designPreset", "mremoteng")
        panel.setProperty("mRemoteNgDockViewVisible", True)
        panel.setProperty("mRemoteNgPropertyColumnKeys", [column.key for column in chrome.columns])
        panel.setProperty("mRemoteNgPropertyRowKeys", [row.key for row in chrome.rows])
        panel.setProperty("mRemoteNgConnectionRouteKey", route.key)
        panel.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
        panel.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
        panel.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
        panel.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
        panel.setProperty("mRemoteNgConnectionRoutePropertyGridObject", route.property_grid_object)
        panel.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
        panel.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
        panel.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
        panel.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
        panel.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
        panel.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
        panel.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
        self.mremoteng_property_grid_panel = panel
        self.apply_mremoteng_reconnect_route_properties(panel, route)
        for property_name, property_value in inheritance_route_properties.items():
            panel.setProperty(property_name, property_value)
        panel.setMaximumHeight(176)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(4)

        title_row = QHBoxLayout()
        title = QLabel(chrome.title)
        title.setObjectName("mRemoteNgPropertyGridTitle")
        scope = QLabel(chrome.scope_label)
        scope.setObjectName("mRemoteNgPropertyGridScope")
        scope.setProperty("mRemoteNgPropertyScope", chrome.scope_label)
        state = QLabel(chrome.inheritance_label)
        state.setObjectName("mRemoteNgPropertyGridScope")
        state.setProperty("mRemoteNgPropertyInheritanceLabel", chrome.inheritance_label)
        title_row.addWidget(title)
        title_row.addWidget(scope)
        title_row.addStretch(1)
        title_row.addWidget(state)
        layout.addLayout(title_row)

        header = QHBoxLayout()
        header.setSpacing(3)
        compact_widths = {
            "property": 72,
            "inherited": 60,
            "effective": 76,
            "source": 68,
        }
        for column in chrome.columns:
            label = QLabel(column.label)
            label.setObjectName("mRemoteNgPropertyGridColumn")
            label.setProperty("mRemoteNgPropertyColumnKey", column.key)
            label.setProperty("mRemoteNgPropertyColumnWidth", column.static_width)
            preferred_width = max(72, min(column.static_width, 190))
            compact_width = compact_widths[column.key]
            label.setProperty("mRemoteNgPropertyLivePreferredWidth", preferred_width)
            label.setProperty("mRemoteNgPropertyLiveCompactMinWidth", compact_width)
            label.setMinimumWidth(compact_width)
            label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            header.addWidget(label, compact_width)
        layout.addLayout(header)

        for row in chrome.rows:
            row_frame = QFrame()
            row_frame.setObjectName("mRemoteNgPropertyGridRow")
            row_frame.setProperty("mRemoteNgPropertyRowKey", row.key)
            row_frame.setProperty("mRemoteNgPropertyInherited", "true" if row.inherited else "false")
            row_frame.setProperty("inherited", "true" if row.inherited else "false")
            if row.key == route.property_row_key:
                row_frame.setProperty("mRemoteNgConnectionRouteKey", route.key)
                row_frame.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
                row_frame.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
                row_frame.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                row_frame.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
                row_frame.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
                row_frame.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                row_frame.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
                row_frame.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                row_frame.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
                self.mremoteng_connection_route_row = row_frame
                self.apply_mremoteng_reconnect_route_properties(row_frame, route)
            if row.key == inheritance_route.property_row_key:
                for property_name, property_value in inheritance_route_properties.items():
                    row_frame.setProperty(property_name, property_value)
                row_frame.setProperty(inheritance_route.workflow_key_property, inheritance_route.workflow_card_key)
                row_frame.setProperty(inheritance_route.active_tab_property, inheritance_route.active_tab_label)
                row_frame.setProperty(inheritance_route.status_property, inheritance_route.inheritance_state)
                row_frame.setProperty(
                    inheritance_route.inherited_value_property,
                    inheritance_route.inherited_value,
                )
            row_layout = QHBoxLayout(row_frame)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            values = {
                "property": row.property_label,
                "inherited": row.inherited_from,
                "effective": row.effective_value,
                "source": row.source,
            }
            for column in chrome.columns:
                cell = _literal_label(values[column.key])
                cell.setObjectName("mRemoteNgPropertyGridCell")
                cell.setProperty("mRemoteNgPropertyRowKey", row.key)
                cell.setProperty("mRemoteNgPropertyColumnKey", column.key)
                cell.setProperty("mRemoteNgPropertyCellValue", values[column.key])
                full_text = f"{column.label}: {values[column.key]}"
                preferred_width = max(72, min(column.static_width, 190))
                compact_width = compact_widths[column.key]
                cell.setProperty("mRemoteNgPropertyCellFullText", full_text)
                cell.setProperty("mRemoteNgPropertyLivePreferredWidth", preferred_width)
                cell.setProperty("mRemoteNgPropertyLiveCompactMinWidth", compact_width)
                if row.key == route.property_row_key:
                    cell.setProperty("mRemoteNgConnectionRouteKey", route.key)
                    cell.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                    cell.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                    cell.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
                    cell.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                    self.apply_mremoteng_reconnect_route_properties(cell, route)
                    if column.key == "effective":
                        self.mremoteng_connection_route_effective_cell = cell
                if row.key == inheritance_route.property_row_key:
                    for property_name, property_value in inheritance_route_properties.items():
                        cell.setProperty(property_name, property_value)
                    cell.setProperty(inheritance_route.workflow_key_property, inheritance_route.workflow_card_key)
                    cell.setProperty(inheritance_route.active_tab_property, inheritance_route.active_tab_label)
                    cell.setProperty(inheritance_route.status_property, inheritance_route.inheritance_state)
                    cell.setProperty(
                        inheritance_route.inherited_value_property,
                        inheritance_route.inherited_value,
                    )
                cell.setMinimumWidth(compact_width)
                cell.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                cell.setAccessibleName(full_text)
                cell.setToolTip(
                    _safe_tooltip_html(full_text)
                )
                row_layout.addWidget(cell, compact_width)
            layout.addWidget(row_frame)
        return panel
