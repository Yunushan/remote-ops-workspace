from __future__ import annotations

import sys

from .doctor import run_doctor
from .file_transfer import build_sftp_queue_plan, parse_transfer_item_spec, preview_local_path
from .gui_designs import GUI_DESIGN_PRESETS, get_gui_design_preset
from .gui_editors import (
    layout_from_editor_data,
    layout_to_editor_data,
    profile_from_editor_data,
    profile_to_editor_data,
)
from .gui_lifecycle import ProcessStopPolicy, ProcessStopResult, stop_process
from .launcher import LauncherError, build_launch_plan
from .layouts import Layout, LayoutStore, build_layout_terminal_plans
from .storage import ProfileStore
from .terminal import (
    TerminalPanePlan,
    split_shell_plans,
    terminal_plan_for_profile,
    terminal_plan_for_sftp_browser,
)


class GuiDependencyError(RuntimeError):
    pass


def create_main_window(argv: list[str] | None = None, *, show: bool = False):
    try:
        from PyQt6.QtCore import QProcess, QSize, Qt
        from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSplitter,
            QStyle,
            QTabWidget,
            QTextEdit,
            QToolBar,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover - optional dependency
        raise GuiDependencyError("PyQt6 is not installed. Install with: pip install -e '.[desktop]'") from exc

    class TerminalPane(QWidget):
        STOP_POLICY = ProcessStopPolicy()

        def __init__(self, plan: TerminalPanePlan) -> None:
            super().__init__()
            self.setObjectName("terminalPane")
            self.plan = plan
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

            self.output = QTextEdit()
            self.output.setObjectName("terminalOutput")
            self.output.setReadOnly(True)
            self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.input = QLineEdit()
            self.input.setObjectName("terminalInput")
            self.input.setPlaceholderText("stdin")
            self.status = QLabel("ready")
            self.status.setObjectName("paneStatus")
            self.start_button = QPushButton("Start")
            self.stop_button = QPushButton("Stop")

            controls = QHBoxLayout()
            controls.addWidget(self.status, 1)
            controls.addWidget(self.start_button)
            controls.addWidget(self.stop_button)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.addLayout(controls)
            layout.addWidget(self.output, 1)
            layout.addWidget(self.input)

            self.start_button.clicked.connect(self.start)
            self.stop_button.clicked.connect(self.stop)
            self.input.returnPressed.connect(self.send_input)
            self.process.readyReadStandardOutput.connect(self.read_stdout)
            self.process.readyReadStandardError.connect(self.read_stderr)
            self.process.started.connect(self.on_started)
            self.process.errorOccurred.connect(lambda error: self.append_text(f"\n[error] {error.name}\n"))
            self.process.finished.connect(self.on_finished)
            self.update_process_actions()
            self.start()

        def is_running(self) -> bool:
            return self.process.state() != QProcess.ProcessState.NotRunning

        def start(self) -> None:
            if self.is_running():
                return
            if not self.plan.command:
                self.append_text("[error] empty terminal command\n")
                return
            self.output.clear()
            self.status.setText("starting")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.input.setEnabled(False)
            self.append_text(f"$ {self.plan.printable()}\n")
            for note in self.plan.notes:
                self.append_text(f"[note] {note}\n")
            self.process.setProgram(self.plan.command[0])
            self.process.setArguments(self.plan.command[1:])
            self.process.start()
            self.update_process_actions()

        def stop(self, policy: ProcessStopPolicy | None = None) -> ProcessStopResult:
            if not self.is_running():
                self.update_process_actions()
                return ProcessStopResult(
                    was_running=False,
                    terminate_requested=False,
                    kill_requested=False,
                    finished=True,
                )
            self.status.setText("stopping")
            self.stop_button.setEnabled(False)
            self.append_text("\n[process stopping]\n")
            result = stop_process(
                self.process,
                not_running_state=QProcess.ProcessState.NotRunning,
                policy=policy or self.STOP_POLICY,
            )
            if result.kill_requested:
                self.append_text("[process killed after graceful stop timeout]\n")
            if not result.finished:
                self.append_text("[warning] process did not exit after kill request]\n")
            self.update_process_actions()
            return result

        def send_input(self) -> None:
            line = self.input.text()
            self.input.clear()
            if not self.is_running():
                self.append_text("[stdin ignored: process is not running]\n")
                return
            self.process.write((line + "\n").encode("utf-8"))

        def read_stdout(self) -> None:
            self.append_text(bytes(self.process.readAllStandardOutput()).decode(errors="replace"))

        def read_stderr(self) -> None:
            self.append_text(bytes(self.process.readAllStandardError()).decode(errors="replace"))

        def append_text(self, text: str) -> None:
            if not text:
                return
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.insertPlainText(text)
            self.output.moveCursor(QTextCursor.MoveOperation.End)

        def on_started(self) -> None:
            self.status.setText("running")
            self.update_process_actions()

        def on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
            self.status.setText(f"exited {exit_code}")
            self.append_text(f"\n[process exited: {exit_code}, {exit_status.name}]\n")
            self.update_process_actions()

        def update_process_actions(self) -> None:
            running = self.is_running()
            self.start_button.setEnabled(not running)
            self.stop_button.setEnabled(running)
            self.input.setEnabled(running)

    class ProfileDialog(QDialog):
        def __init__(self, profile=None, parent=None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Profile")
            self.resize(520, 660)
            data = profile_to_editor_data(profile)
            self.fields: dict[str, object] = {}
            form = QFormLayout(self)

            for key, label in [
                ("name", "Name"),
                ("protocol", "Protocol"),
                ("host", "Host"),
                ("port", "Port"),
                ("username", "Username"),
                ("group", "Group"),
                ("tags", "Tags"),
                ("path", "Path"),
                ("url", "URL"),
                ("command", "Command"),
                ("identity_file", "Identity file"),
                ("credential_ref", "Credential ref"),
            ]:
                widget = QLineEdit(data[key])
                self.fields[key] = widget
                form.addRow(label, widget)

            description = QPlainTextEdit()
            description.setPlainText(data["description"])
            description.setMaximumBlockCount(200)
            self.fields["description"] = description
            form.addRow("Description", description)

            options = QPlainTextEdit()
            options.setPlainText(data["options"])
            options.setPlaceholderText("key=value")
            self.fields["options"] = options
            form.addRow("Options", options)

            tunnels = QPlainTextEdit()
            tunnels.setPlainText(data["tunnels"])
            tunnels.setPlaceholderText("dynamic:1080\nlocal:15432:127.0.0.1:5432")
            self.fields["tunnels"] = tunnels
            form.addRow("Tunnels", tunnels)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            form.addRow(buttons)

        def editor_data(self) -> dict[str, str]:
            data: dict[str, str] = {}
            for key, widget in self.fields.items():
                if isinstance(widget, QPlainTextEdit):
                    data[key] = widget.toPlainText()
                else:
                    data[key] = widget.text()
            return data

        def profile(self):
            return profile_from_editor_data(self.editor_data())

    class LayoutDialog(QDialog):
        def __init__(self, layout=None, parent=None) -> None:
            super().__init__(parent)
            self.setWindowTitle("Layout")
            self.resize(520, 520)
            data = layout_to_editor_data(layout)
            form = QFormLayout(self)
            self.name = QLineEdit(data["name"])
            self.orientation = QComboBox()
            self.orientation.addItems(["grid", "horizontal", "vertical"])
            self.orientation.setCurrentText(data["orientation"])
            self.description = QPlainTextEdit()
            self.description.setPlainText(data["description"])
            self.panes = QPlainTextEdit()
            self.panes.setPlainText(data["panes"])
            self.panes.setPlaceholderText("profile:edge | Edge\ncommand:python -V | Version")
            form.addRow("Name", self.name)
            form.addRow("Orientation", self.orientation)
            form.addRow("Description", self.description)
            form.addRow("Panes", self.panes)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            form.addRow(buttons)

        def editor_data(self) -> dict[str, str]:
            return {
                "name": self.name.text(),
                "orientation": self.orientation.currentText(),
                "description": self.description.toPlainText(),
                "panes": self.panes.toPlainText(),
            }

        def layout(self) -> Layout:
            return layout_from_editor_data(self.editor_data())

    class TransferQueueDialog(QDialog):
        def __init__(self, profile, parent=None) -> None:
            super().__init__(parent)
            self.profile = profile
            self.setWindowTitle(f"Transfer Queue: {profile.name}")
            self.resize(640, 620)

            root = QVBoxLayout(self)
            form = QFormLayout()
            self.operations = QPlainTextEdit()
            self.operations.setPlaceholderText(
                "get /etc/hosts ./hosts.copy\nput ./build.tar.gz /tmp/build.tar.gz\nmkdir /tmp/releases"
            )
            self.local_preview_path = QLineEdit()
            self.local_preview_path.setPlaceholderText("Local file or directory")
            self.force_destructive = QCheckBox("Force destructive actions")
            form.addRow("Operations", self.operations)
            form.addRow("Local preview", self.local_preview_path)
            form.addRow("", self.force_destructive)
            root.addLayout(form)

            controls = QHBoxLayout()
            self.preview_button = QPushButton("Preview Queue")
            self.local_preview_button = QPushButton("Preview Local")
            controls.addWidget(self.preview_button)
            controls.addWidget(self.local_preview_button)
            controls.addStretch(1)
            root.addLayout(controls)

            self.preview = QTextEdit()
            self.preview.setReadOnly(True)
            self.preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            root.addWidget(self.preview, 1)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

            self.preview_button.clicked.connect(self.refresh_queue_preview)
            self.local_preview_button.clicked.connect(self.refresh_local_preview)

        def queue_plan(self):
            items = []
            for line in self.operations.toPlainText().splitlines():
                raw = line.strip()
                if raw and not raw.startswith("#"):
                    items.append(parse_transfer_item_spec(raw))
            return build_sftp_queue_plan(self.profile, items, force=self.force_destructive.isChecked())

        def refresh_queue_preview(self) -> None:
            try:
                plan = self.queue_plan()
            except ValueError as exc:
                self.preview.setPlainText(f"error: {exc}")
                return
            lines = [plan.printable(), "", "queue:"]
            for index, command in enumerate(plan.batch_commands, start=1):
                lines.append(f"{index}. {command}")
            for note in plan.notes:
                lines.append(f"note: {note}")
            self.preview.setPlainText("\n".join(lines))

        def refresh_local_preview(self) -> None:
            try:
                preview = preview_local_path(self.local_preview_path.text())
            except ValueError as exc:
                self.preview.setPlainText(f"error: {exc}")
                return
            data = preview.to_dict()
            lines = [f"{data['path']}: {data['kind']}"]
            if data.get("size") is not None:
                lines.append(f"size: {data['size']}")
            for child in data.get("children", []):
                lines.append(f"  {child}")
            if data.get("binary"):
                lines.append("binary: true")
            if data.get("truncated"):
                lines.append("truncated: true")
            if data.get("text"):
                lines.append("")
                lines.append(str(data["text"]))
            if data.get("error"):
                lines.append(f"error: {data['error']}")
            self.preview.setPlainText("\n".join(lines))

    class MainWindow(QMainWindow):
        CLOSE_STOP_POLICY = ProcessStopPolicy(terminate_timeout_ms=2000, kill_timeout_ms=500)

        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("remoteOpsMain")
            self.setWindowTitle("Remote Ops Workspace")
            self.resize(1180, 720)
            self.store = ProfileStore()
            self.store.init(with_examples=True)
            self.layout_store = LayoutStore()

            self.main_toolbar = QToolBar("Main")
            self.main_toolbar.setObjectName("mainToolbar")
            self.main_toolbar.setMovable(False)
            self.addToolBar(self.main_toolbar)
            self.refresh_button = self.toolbar_button("Refresh", "SP_BrowserReload", "Reload profiles")
            self.new_profile_button = self.toolbar_button("New", "SP_FileIcon", "Create profile")
            self.edit_profile_button = self.toolbar_button("Edit", "SP_FileDialogDetailedView", "Edit selected profile")
            self.remove_profile_button = self.toolbar_button("Remove", "SP_TrashIcon", "Remove selected profile")
            self.remove_profile_button.setObjectName("dangerAction")
            self.connect_button = self.toolbar_button("Connect", "SP_MediaPlay", "Open selected profile")
            self.connect_button.setObjectName("primaryAction")
            self.files_button = self.toolbar_button("Files", "SP_DirIcon", "Open SFTP browser")
            self.queue_button = self.toolbar_button("Queue", "SP_FileDialogListView", "Preview transfer queue")
            self.dry_run_button = self.toolbar_button("Dry Run", "SP_CommandLink", "Show launch command")
            self.doctor_button = self.toolbar_button("Doctor", "SP_MessageBoxInformation", "Run doctor checks")
            self.split_h_button = self.toolbar_button("Split H", "SP_TitleBarShadeButton", "Open horizontal split")
            self.split_v_button = self.toolbar_button("Split V", "SP_TitleBarUnshadeButton", "Open vertical split")
            self.layout_select = QComboBox()
            self.layout_select.setObjectName("layoutSelect")
            self.layout_select.setMinimumWidth(180)
            self.design_select = QComboBox()
            self.design_select.setObjectName("designSelect")
            self.design_select.setMinimumWidth(170)
            for preset in GUI_DESIGN_PRESETS:
                self.design_select.addItem(preset.label, preset.id)
            self.new_layout_button = self.toolbar_button("New Layout", "SP_FileIcon", "Create layout")
            self.edit_layout_button = self.toolbar_button("Edit Layout", "SP_FileDialogDetailedView", "Edit selected layout")
            self.remove_layout_button = self.toolbar_button("Remove Layout", "SP_TrashIcon", "Remove selected layout")
            self.remove_layout_button.setObjectName("dangerAction")
            self.open_layout_button = self.toolbar_button("Open Layout", "SP_DialogOpenButton", "Open selected layout")
            self.search_input = QLineEdit()
            self.search_input.setObjectName("toolbarSearch")
            self.search_input.setPlaceholderText("Search log")
            self.find_button = self.toolbar_button("Find", "SP_FileDialogContentsView", "Find in log")
            for button in [
                self.refresh_button,
                self.new_profile_button,
                self.edit_profile_button,
                self.remove_profile_button,
                self.connect_button,
                self.files_button,
                self.queue_button,
                self.dry_run_button,
                self.doctor_button,
                self.split_h_button,
                self.split_v_button,
            ]:
                self.main_toolbar.addWidget(button)
            self.main_toolbar.addSeparator()
            view_label = QLabel("View")
            view_label.setObjectName("toolbarLabel")
            self.main_toolbar.addWidget(view_label)
            self.main_toolbar.addWidget(self.design_select)
            self.main_toolbar.addWidget(self.layout_select)
            for button in [self.new_layout_button, self.edit_layout_button, self.remove_layout_button]:
                self.main_toolbar.addWidget(button)
            self.main_toolbar.addWidget(self.open_layout_button)
            self.main_toolbar.addSeparator()
            self.main_toolbar.addWidget(self.search_input)
            self.main_toolbar.addWidget(self.find_button)

            self.profile_list = QListWidget()
            self.profile_list.setObjectName("profileTree")
            self.profile_list.setMinimumWidth(300)
            self.tabs = QTabWidget()
            self.tabs.setObjectName("sessionTabs")
            self.tabs.setTabsClosable(True)
            self.tabs.setMovable(True)
            self.log = QTextEdit()
            self.log.setObjectName("activityLog")
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Launch output, dry-run commands and doctor reports appear here.")

            self.workspace = QSplitter(Qt.Orientation.Vertical)
            self.workspace.setObjectName("workspace")
            self.workspace.addWidget(self.tabs)
            self.workspace.addWidget(self.log)
            self.workspace.setStretchFactor(0, 3)
            self.workspace.setStretchFactor(1, 1)

            self.root_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.root_splitter.setObjectName("rootWorkspace")
            self.root_splitter.addWidget(self.profile_list)
            self.root_splitter.addWidget(self.workspace)
            self.root_splitter.setStretchFactor(1, 1)
            self.setCentralWidget(self.root_splitter)

            self.refresh_button.clicked.connect(self.refresh_profiles)
            self.new_profile_button.clicked.connect(self.create_profile)
            self.edit_profile_button.clicked.connect(self.edit_selected_profile)
            self.remove_profile_button.clicked.connect(self.remove_selected_profile)
            self.connect_button.clicked.connect(lambda: self.connect_selected(False))
            self.files_button.clicked.connect(self.open_files_selected)
            self.queue_button.clicked.connect(self.open_transfer_queue_selected)
            self.dry_run_button.clicked.connect(lambda: self.connect_selected(True))
            self.doctor_button.clicked.connect(self.show_doctor)
            self.split_h_button.clicked.connect(lambda: self.add_split("horizontal"))
            self.split_v_button.clicked.connect(lambda: self.add_split("vertical"))
            self.new_layout_button.clicked.connect(self.create_layout)
            self.edit_layout_button.clicked.connect(self.edit_selected_layout)
            self.remove_layout_button.clicked.connect(self.remove_selected_layout)
            self.open_layout_button.clicked.connect(self.open_selected_layout)
            self.tabs.tabCloseRequested.connect(self.close_tab)
            self.design_select.currentIndexChanged.connect(self.apply_selected_design)
            self.find_button.clicked.connect(self.find_log_text)
            QShortcut(QKeySequence("Ctrl+R"), self, activated=self.refresh_profiles)
            QShortcut(QKeySequence("Ctrl+N"), self, activated=self.create_profile)
            QShortcut(QKeySequence("Ctrl+E"), self, activated=self.edit_selected_profile)
            QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self.connect_selected(False))
            QShortcut(QKeySequence("Ctrl+Shift+H"), self, activated=lambda: self.add_split("horizontal"))
            QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=lambda: self.add_split("vertical"))
            QShortcut(QKeySequence("Ctrl+L"), self, activated=self.open_selected_layout)
            QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_input.setFocus)
            self.refresh_profiles()
            self.refresh_layouts()
            self.add_welcome_tab()
            self.apply_selected_design()

        def toolbar_button(self, label: str, icon_name: str, tooltip: str) -> QPushButton:
            button = QPushButton(label)
            button.setToolTip(tooltip)
            button.setIcon(self.style().standardIcon(self.standard_icon(icon_name)))
            return button

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

        def refresh_profiles(self) -> None:
            self.profile_list.clear()
            for profile in self.store.load():
                item = QListWidgetItem(f"{profile.group}/{profile.name}  [{profile.protocol}]  {profile.display_target}")
                item.setData(Qt.ItemDataRole.UserRole, profile.name)
                self.profile_list.addItem(item)
            self.refresh_layouts()

        def refresh_layouts(self) -> None:
            self.layout_select.clear()
            for layout in self.layout_store.load():
                self.layout_select.addItem(layout.name)

        def apply_selected_design(self, *_args) -> None:
            preset_id = self.design_select.currentData() or "native"
            try:
                preset = get_gui_design_preset(str(preset_id))
            except ValueError:
                preset = get_gui_design_preset("native")
            self.setStyleSheet(preset.stylesheet)
            self.main_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
            self.profile_list.setMinimumWidth(min(preset.profile_width, 380))
            self.profile_list.setSpacing(preset.list_spacing)
            self.root_splitter.setSizes([preset.profile_width, max(620, self.width() - preset.profile_width)])
            self.workspace.setSizes([max(420, self.height() - preset.log_height), preset.log_height])
            self.tabs.setTabPosition(self.tab_position_for_design(preset.tab_position))
            self.tabs.setDocumentMode(preset.document_mode)
            self.log.setPlaceholderText(
                f"{preset.description}\n\nLaunch output, dry-run commands and doctor reports appear here."
            )
            self.statusBar().showMessage(f"View: {preset.label}")

        def tab_position_for_design(self, value: str):
            if value == "west":
                return QTabWidget.TabPosition.West
            if value == "south":
                return QTabWidget.TabPosition.South
            if value == "east":
                return QTabWidget.TabPosition.East
            return QTabWidget.TabPosition.North

        def selected_profile_name(self) -> str | None:
            item = self.profile_list.currentItem()
            if not item:
                return None
            return item.data(Qt.ItemDataRole.UserRole)

        def create_profile(self) -> None:
            dialog = ProfileDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                profile = dialog.profile()
                self.store.add(profile)
                self.refresh_profiles()
                self.select_profile(profile.name)
                self.log.append(f"PROFILE SAVED: {profile.name}")
            except ValueError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def edit_selected_profile(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                current = self.store.get(name)
            except KeyError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))
                return
            dialog = ProfileDialog(current, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                profile = dialog.profile()
                self.save_profile(profile, original_name=name)
                self.refresh_profiles()
                self.select_profile(profile.name)
                self.log.append(f"PROFILE UPDATED: {profile.name}")
            except (KeyError, ValueError) as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def remove_selected_profile(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            answer = QMessageBox.question(self, "Remove profile", f"Remove profile {name}?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.store.remove(name)
                self.refresh_profiles()
                self.log.append(f"PROFILE REMOVED: {name}")
            except KeyError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def save_profile(self, profile, original_name: str) -> None:
            profiles = self.store.load(resolve=False)
            if profile.name != original_name and any(item.name == profile.name for item in profiles):
                raise ValueError(f"profile already exists: {profile.name}")
            profiles = [item for item in profiles if item.name != original_name]
            profiles.append(profile)
            self.store.save(sorted(profiles, key=lambda item: (item.group, item.name)))

        def select_profile(self, name: str) -> None:
            for row in range(self.profile_list.count()):
                item = self.profile_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == name:
                    self.profile_list.setCurrentRow(row)
                    return

        def connect_selected(self, dry_run: bool) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                plan = build_launch_plan(profile)
                prefix = "DRY RUN" if dry_run else "LAUNCHED"
                if dry_run:
                    self.log.append(f"{prefix}: {plan.printable()}")
                    for note in plan.notes:
                        self.log.append(f"  note: {note}")
                else:
                    pane_plan = terminal_plan_for_profile(profile)
                    self.open_terminal_tab(pane_plan)
                    self.log.append(f"{prefix}: {pane_plan.printable()}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Launch failed", str(exc))

        def open_files_selected(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                pane_plan = terminal_plan_for_sftp_browser(profile)
                self.open_terminal_tab(pane_plan)
                self.log.append(f"FILES: {pane_plan.printable()}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "SFTP failed", str(exc))

        def open_transfer_queue_selected(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                dialog = TransferQueueDialog(profile, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                plan = dialog.queue_plan()
                self.log.append(f"QUEUE: {plan.printable()}")
                for command in plan.batch_commands:
                    self.log.append(f"  {command}")
                for note in plan.notes:
                    self.log.append(f"  note: {note}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Transfer queue failed", str(exc))

        def show_doctor(self) -> None:
            self.log.append(run_doctor().to_json())

        def find_log_text(self) -> None:
            needle = self.search_input.text()
            if not needle:
                return
            if not self.log.find(needle):
                cursor = self.log.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                self.log.setTextCursor(cursor)
                self.log.find(needle)

        def add_welcome_tab(self) -> None:
            box = QWidget()
            layout = QVBoxLayout(box)
            label = QLabel("Remote Ops Workspace\n\nUse the profile list and toolbar to launch process-backed session panes.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
            self.tabs.addTab(box, "Welcome")

        def open_terminal_tab(self, plan: TerminalPanePlan) -> None:
            pane = self.new_terminal_pane(plan)
            self.tabs.addTab(pane, plan.title)
            self.tabs.setCurrentWidget(pane)
            self.update_session_status()

        def add_split(self, direction: str) -> None:
            orientation = Qt.Orientation.Horizontal if direction == "horizontal" else Qt.Orientation.Vertical
            splitter = QSplitter(orientation)
            for plan in split_shell_plans(2):
                splitter.addWidget(self.new_terminal_pane(plan))
            self.tabs.addTab(splitter, f"Split {self.tabs.count()}")
            self.tabs.setCurrentWidget(splitter)
            self.update_session_status()

        def create_layout(self) -> None:
            dialog = LayoutDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                layout = dialog.layout()
                self.layout_store.add(layout)
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT SAVED: {layout.name}")
            except ValueError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def edit_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            try:
                current = self.layout_store.get(name)
            except KeyError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))
                return
            dialog = LayoutDialog(current, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                layout = dialog.layout()
                self.save_layout(layout, original_name=name)
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT UPDATED: {layout.name}")
            except (KeyError, ValueError) as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def remove_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            answer = QMessageBox.question(self, "Remove layout", f"Remove layout {name}?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.layout_store.remove(name)
                self.refresh_layouts()
                self.log.append(f"LAYOUT REMOVED: {name}")
            except KeyError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def save_layout(self, layout: Layout, original_name: str) -> None:
            layouts = self.layout_store.load()
            if layout.name != original_name and any(item.name == layout.name for item in layouts):
                raise ValueError(f"layout already exists: {layout.name}")
            layouts = [item for item in layouts if item.name != original_name]
            layouts.append(layout)
            self.layout_store.save(sorted(layouts, key=lambda item: item.name))

        def open_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            try:
                layout = self.layout_store.get(name)
                plans = build_layout_terminal_plans(layout, self.store)
                widget = self.layout_widget(layout, plans)
                self.tabs.addTab(widget, layout.name)
                self.tabs.setCurrentWidget(widget)
                self.log.append(f"LAYOUT: {layout.name} ({len(plans)} panes)")
                self.update_session_status()
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def layout_widget(self, layout: Layout, plans: list[TerminalPanePlan]) -> QWidget:
            if len(plans) == 1:
                return self.new_terminal_pane(plans[0])
            if layout.orientation == "vertical":
                splitter = QSplitter(Qt.Orientation.Vertical)
                for plan in plans:
                    splitter.addWidget(self.new_terminal_pane(plan))
                return splitter
            if layout.orientation == "horizontal":
                splitter = QSplitter(Qt.Orientation.Horizontal)
                for plan in plans:
                    splitter.addWidget(self.new_terminal_pane(plan))
                return splitter
            root = QSplitter(Qt.Orientation.Vertical)
            for offset in range(0, len(plans), 2):
                row = QSplitter(Qt.Orientation.Horizontal)
                for plan in plans[offset : offset + 2]:
                    row.addWidget(self.new_terminal_pane(plan))
                root.addWidget(row)
            return root

        def new_terminal_pane(self, plan: TerminalPanePlan) -> TerminalPane:
            pane = TerminalPane(plan)
            pane.process.started.connect(self.update_session_status)
            pane.process.finished.connect(lambda *_args: self.update_session_status())
            return pane

        def close_tab(self, index: int) -> None:
            widget = self.tabs.widget(index)
            if widget is None:
                return
            running = [pane for pane in self.terminal_panes_in(widget) if pane.is_running()]
            if running and not self.confirm_stop_processes("Close tab", len(running)):
                return
            self.stop_terminal_panes(running)
            title = self.tabs.tabText(index)
            self.tabs.removeTab(index)
            widget.deleteLater()
            self.log.append(f"TAB CLOSED: {title}")
            self.update_session_status()

        def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]:
            panes: list[TerminalPane] = []
            if isinstance(widget, TerminalPane):
                panes.append(widget)
            panes.extend(widget.findChildren(TerminalPane))
            return panes

        def all_terminal_panes(self) -> list[TerminalPane]:
            panes: list[TerminalPane] = []
            seen: set[int] = set()
            for index in range(self.tabs.count()):
                widget = self.tabs.widget(index)
                if widget is None:
                    continue
                for pane in self.terminal_panes_in(widget):
                    key = id(pane)
                    if key in seen:
                        continue
                    seen.add(key)
                    panes.append(pane)
            return panes

        def running_terminal_panes(self) -> list[TerminalPane]:
            return [pane for pane in self.all_terminal_panes() if pane.is_running()]

        def stop_terminal_panes(self, panes: list[TerminalPane]) -> None:
            stopped = 0
            killed = 0
            unfinished = 0
            for pane in panes:
                result = pane.stop(self.CLOSE_STOP_POLICY)
                if result.was_running:
                    stopped += 1
                if result.kill_requested:
                    killed += 1
                if not result.finished:
                    unfinished += 1
            if stopped:
                detail = f"STOPPED: {stopped} process pane(s)"
                if killed:
                    detail += f", {killed} killed after timeout"
                if unfinished:
                    detail += f", {unfinished} still exiting"
                self.log.append(detail)

        def confirm_stop_processes(self, title: str, count: int) -> bool:
            answer = QMessageBox.question(
                self,
                title,
                f"Stop {count} running process pane(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer == QMessageBox.StandardButton.Yes

        def update_session_status(self) -> None:
            running = len(self.running_terminal_panes())
            if running:
                self.statusBar().showMessage(f"Running process panes: {running}")
            else:
                self.statusBar().showMessage("No running process panes")

        def closeEvent(self, event) -> None:
            running = self.running_terminal_panes()
            if running and not self.confirm_stop_processes("Quit Remote Ops Workspace", len(running)):
                event.ignore()
                return
            self.stop_terminal_panes(running)
            event.accept()

    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or sys.argv)
    window = MainWindow()
    if show:
        window.show()
    return app, window


def main() -> int:
    try:
        app, _window = create_main_window(sys.argv, show=True)
    except GuiDependencyError as exc:
        print(str(exc))
        if exc.__cause__ is not None:
            print(exc.__cause__)
        return 2
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
