from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QShowEvent, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .enterprise_policy import assert_profile_launch_allowed
from .file_transfer import (
    SftpQueuePlan,
    build_sftp_queue_plan,
    parse_transfer_item_spec,
    preview_local_path,
)
from .gui_editors import (
    layout_from_editor_data,
    layout_to_editor_data,
    profile_editor_protocols,
    profile_from_editor_data,
    profile_to_editor_data,
    protocol_preset_editor_data,
)
from .gui_processes import _background_process
from .layouts import Layout, layout_splitter_size_lengths, validate_layout
from .models import Profile
from .process_status import ProcessStatusError
from .profile_importers import ProfileImportResult
from .terminal import openssh_command_without_windows_connection_sharing

T = TypeVar("T")


class RequiredGuiValue(Protocol):
    def __call__(self, value: T | None, description: str, /) -> T: ...


@dataclass(frozen=True)
class DialogServices:
    """GUI helpers supplied at the optional Qt boundary."""

    size_for_screen: Callable[..., None]
    clamp_to_screen: Callable[[QDialog], None]
    literal_label: Callable[[object], QLabel]
    require_value: RequiredGuiValue


class ScreenBoundedDialog(QDialog):
    def __init__(self, parent: QWidget | None, *, services: DialogServices) -> None:
        super().__init__(parent)
        self.services = services

    def showEvent(self, event: QShowEvent | None) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.services.clamp_to_screen(self))


class ProfileDialog(ScreenBoundedDialog):
    def __init__(self, profile: Profile | None = None, parent: QWidget | None = None, *, services: DialogServices) -> None:
        super().__init__(parent, services=services)
        self.setObjectName("workflowDialog")
        self.setWindowTitle("Profile")
        self.services.size_for_screen(
            self,
            parent,
            maximum_width=560,
            maximum_height=720,
            minimum_width=460,
            minimum_height=420,
        )
        data = profile_to_editor_data(profile)
        self.fields: dict[str, QLineEdit | QComboBox | QPlainTextEdit] = {}
        self._validated_profile: Profile | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("Session profile")
        title.setObjectName("workflowTitle")
        subtitle = QLabel(
            "Create or edit a connection profile, including tunnels and protocol options."
        )
        subtitle.setObjectName("workflowSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("profileFormScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_body = QWidget()
        form_body.setObjectName("profileFormBody")
        form = QFormLayout(form_body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

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
            widget: QLineEdit | QComboBox
            if key == "protocol":
                widget = QComboBox()
                widget.setEditable(False)
                widget.setMaxVisibleItems(8)
                protocols = list(profile_editor_protocols())
                if data[key] not in protocols:
                    protocols.append(data[key])
                widget.addItems(protocols)
                widget.setCurrentText(data[key])
                model = self.services.require_value(
                    widget.model(),
                    "profile protocol model",
                )
                for row, protocol in enumerate(protocols):
                    if protocol in {"ssh1", "sshv1"}:
                        model.setData(
                            model.index(row, 0),
                            "Legacy SSH v1: launch requires allow_insecure_sshv1=true, "
                            "legacy_target=windows-xp-32 or windows-xp-64, and "
                            "allow_legacy_crypto=true; use only for isolated legacy systems.",
                            Qt.ItemDataRole.ToolTipRole,
                        )
            else:
                widget = QLineEdit(data[key])
            widget.setObjectName(f"profile{key.title().replace('_', '')}")
            self.fields[key] = widget
            form.addRow(label, widget)

        self.preset_button = QPushButton("Apply protocol defaults")
        self.preset_button.setObjectName("profileProtocolDefaults")
        self.preset_note = QLabel(
            "Sets safe port and option defaults; existing identity fields are kept."
        )
        self.preset_note.setObjectName("profileProtocolDefaultsNote")
        self.preset_note.setTextFormat(Qt.TextFormat.PlainText)
        self.preset_note.setWordWrap(True)
        self.preset_button.clicked.connect(self.apply_protocol_preset)
        preset_row = QWidget()
        preset_row.setObjectName("profileProtocolDefaultsRow")
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(10)
        preset_layout.addWidget(self.preset_button)
        preset_layout.addWidget(self.preset_note, 1)
        form.addRow(preset_row)

        description = QPlainTextEdit()
        description.setPlainText(data["description"])
        description.setMaximumBlockCount(200)
        self.configure_multiline_editor(description, "profileDescription")
        self.fields["description"] = description
        form.addRow("Description", description)

        options = QPlainTextEdit()
        options.setPlainText(data["options"])
        options.setPlaceholderText("key=value")
        self.configure_multiline_editor(options, "profileOptions")
        self.fields["options"] = options
        form.addRow("Options", options)

        tunnels = QPlainTextEdit()
        tunnels.setPlainText(data["tunnels"])
        tunnels.setPlaceholderText("dynamic:1080\nlocal:15432:127.0.0.1:5432")
        self.configure_multiline_editor(tunnels, "profileTunnels")
        self.fields["tunnels"] = tunnels
        form.addRow("Tunnels", tunnels)

        self.form_scroll.setWidget(form_body)
        root.addWidget(self.form_scroll, 1)

        self.validation_error = QLabel()
        self.validation_error.setObjectName("profileValidationError")
        self.validation_error.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_error.setWordWrap(True)
        self.validation_error.setVisible(False)
        root.addWidget(self.validation_error)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.setObjectName("profileDialogButtons")
        self.save_button = self.services.require_value(
            self.buttons.button(QDialogButtonBox.StandardButton.Save),
            "profile dialog save button",
        )
        self.save_button.setObjectName("primaryAction")
        self.save_button.setDefault(True)
        self.buttons.accepted.connect(self.submit)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    @staticmethod
    def configure_multiline_editor(editor: QPlainTextEdit, object_name: str) -> None:
        editor.setObjectName(object_name)
        editor.setMinimumHeight(72)
        editor.setMaximumHeight(96)
        editor.resize(editor.width(), 84)
        editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def submit(self) -> None:
        try:
            self._validated_profile = profile_from_editor_data(self.editor_data())
        except ValueError as exc:
            self.show_validation_error(str(exc))
            return
        self.validation_error.setVisible(False)
        self.accept()

    def show_validation_error(self, message: str) -> None:
        self._validated_profile = None
        self.validation_error.setText(f"Cannot save profile: {message}")
        self.validation_error.setVisible(True)
        normalized = message.lower()
        field_key = next(
            (
                key
                for token, key in (
                    ("profile name", "name"),
                    ("already exists", "name"),
                    ("protocol", "protocol"),
                    ("host", "host"),
                    ("port", "port"),
                    ("url", "url"),
                    ("command", "command"),
                    ("identity", "identity_file"),
                    ("credential", "credential_ref"),
                    ("tunnel", "tunnels"),
                    ("option", "options"),
                )
                if token in normalized
            ),
            "name",
        )
        widget = self.fields.get(field_key)
        if isinstance(widget, QWidget):
            self.form_scroll.ensureWidgetVisible(widget)
            widget.setFocus()

    def apply_protocol_preset(self) -> None:
        protocol = self.fields["protocol"]
        if not isinstance(protocol, QComboBox):
            return
        preset = protocol_preset_editor_data(protocol.currentText())
        port = self.fields["port"]
        options = self.fields["options"]
        if isinstance(port, QLineEdit) and "port" in preset:
            port.setText(preset["port"])
        if isinstance(options, QPlainTextEdit) and "options" in preset:
            options.setPlainText(preset["options"])
        self.preset_note.setText(f"Applied {protocol.currentText().upper()} defaults.")

    def editor_data(self) -> dict[str, str]:
        data: dict[str, str] = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QPlainTextEdit):
                data[key] = widget.toPlainText()
            elif isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            else:
                data[key] = widget.text()
        return data

    def profile(self) -> Profile:
        if self._validated_profile is not None:
            return self._validated_profile
        return profile_from_editor_data(self.editor_data())

class ProfileImportPreviewDialog(ScreenBoundedDialog):
    def __init__(self, source: str, result: ProfileImportResult, parent: QWidget | None = None, *, services: DialogServices) -> None:
        super().__init__(parent, services=services)
        self.setObjectName("profileImportPreviewDialog")
        self.setWindowTitle("Import profile preview")
        self.services.size_for_screen(
            self,
            parent,
            maximum_width=660,
            maximum_height=480,
            minimum_width=420,
            minimum_height=320,
        )
        root = QVBoxLayout(self)
        title = self.services.literal_label("Profile import preview")
        title.setObjectName("workflowTitle")
        root.addWidget(title)
        source_label = self.services.literal_label(
            f"Source: {source}\nFormat: {result.source_format}\nProfiles: {len(result.profiles)}"
        )
        source_label.setObjectName("profileImportSource")
        root.addWidget(source_label)
        preview = QTreeWidget()
        preview.setObjectName("profileImportPreview")
        preview.setColumnCount(4)
        preview.setHeaderLabels(["Name", "Protocol", "Target", "Group"])
        preview.setRootIsDecorated(False)
        for profile in result.profiles:
            preview.addTopLevelItem(
                QTreeWidgetItem([profile.name, profile.protocol, profile.display_target, profile.group])
            )
        preview.resizeColumnToContents(0)
        preview.resizeColumnToContents(1)
        root.addWidget(preview, 1)
        if result.warnings:
            warnings = QTextEdit()
            warnings.setObjectName("profileImportWarnings")
            warnings.setReadOnly(True)
            warnings.setMaximumHeight(96)
            warnings.setPlainText("\n".join(f"warning: {item}" for item in result.warnings))
            root.addWidget(warnings)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.setObjectName("profileImportDialogButtons")
        import_button = self.services.require_value(
            buttons.button(QDialogButtonBox.StandardButton.Ok),
            "profile import confirmation button",
        )
        import_button.setText("Import profiles")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

class LayoutDialog(ScreenBoundedDialog):
    def __init__(self, layout: Layout | None = None, parent: QWidget | None = None, *, services: DialogServices) -> None:
        super().__init__(parent, services=services)
        self.setObjectName("workflowDialog")
        self.setWindowTitle("Layout")
        self.services.size_for_screen(
            self,
            parent,
            maximum_width=560,
            maximum_height=660,
            minimum_width=460,
            minimum_height=420,
        )
        data = layout_to_editor_data(layout)
        self._original_layout: Layout | None = layout
        self._validated_layout: Layout | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)
        title = QLabel("Workspace layout")
        title.setObjectName("workflowTitle")
        subtitle = QLabel("Arrange multiple terminal panes from profiles and commands.")
        subtitle.setObjectName("workflowSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.form_scroll = QScrollArea()
        self.form_scroll.setObjectName("layoutFormScroll")
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.form_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        form_body = QWidget()
        form_body.setObjectName("layoutFormBody")
        form = QFormLayout(form_body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(8)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name = QLineEdit(data["name"])
        self.name.setObjectName("layoutName")
        self.orientation = QComboBox()
        self.orientation.setObjectName("layoutOrientation")
        self.orientation.addItems(["grid", "horizontal", "vertical"])
        self.orientation.setCurrentText(data["orientation"])
        self.description = QPlainTextEdit()
        self.description.setObjectName("layoutDescription")
        self.description.setPlainText(data["description"])
        self.description.setMinimumHeight(76)
        self.description.setMaximumHeight(96)
        self.panes = QPlainTextEdit()
        self.panes.setObjectName("layoutPanes")
        self.panes.setPlainText(data["panes"])
        self.panes.setPlaceholderText("profile:edge | Edge\ncommand:python -V | Version")
        self.panes.setMinimumHeight(150)
        form.addRow("Name", self.name)
        form.addRow("Orientation", self.orientation)
        form.addRow("Description", self.description)
        form.addRow("Panes", self.panes)
        self.form_scroll.setWidget(form_body)
        root.addWidget(self.form_scroll, 1)

        self.validation_error = QLabel()
        self.validation_error.setObjectName("layoutValidationError")
        self.validation_error.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_error.setWordWrap(True)
        self.validation_error.setVisible(False)
        root.addWidget(self.validation_error)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.setObjectName("layoutDialogButtons")
        self.save_button = self.services.require_value(
            self.buttons.button(QDialogButtonBox.StandardButton.Save),
            "layout dialog save button",
        )
        self.save_button.setObjectName("primaryAction")
        self.save_button.setDefault(True)
        self.buttons.accepted.connect(self.submit)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def submit(self) -> None:
        try:
            self._validated_layout = self.parsed_layout()
        except ValueError as exc:
            self.show_validation_error(str(exc))
            return
        self.validation_error.setVisible(False)
        self.accept()

    def show_validation_error(self, message: str) -> None:
        self._validated_layout = None
        self.validation_error.setText(f"Cannot save layout: {message}")
        self.validation_error.setVisible(True)
        target = (
            self.panes
            if "pane" in message.lower()
            else self.orientation
            if "orientation" in message.lower()
            else self.name
        )
        self.form_scroll.ensureWidgetVisible(target)
        target.setFocus()

    def parsed_layout(self) -> Layout:
        parsed = layout_from_editor_data(self.editor_data())
        original = self._original_layout
        if original is not None and layout_splitter_size_lengths(
            parsed
        ) == layout_splitter_size_lengths(original):
            parsed.splitter_sizes = [list(sizes) for sizes in original.splitter_sizes]
            validate_layout(parsed)
        return parsed

    def editor_data(self) -> dict[str, str]:
        return {
            "name": self.name.text(),
            "orientation": self.orientation.currentText(),
            "description": self.description.toPlainText(),
            "panes": self.panes.toPlainText(),
        }

    def workspace_layout(self) -> Layout:
        if self._validated_layout is not None:
            return self._validated_layout
        return self.parsed_layout()


class LiteralTextEdit(QTextEdit):
    """QTextEdit whose append API never interprets terminal or profile text as HTML."""

    def append(self, text: object) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if cursor.position() > 0:
            cursor.insertBlock()
        cursor.insertText(str(text), QTextCharFormat())
        self.setTextCursor(cursor)
        self.ensureCursorVisible()


class TransferQueueDialog(ScreenBoundedDialog):
    def __init__(
        self,
        profile: Profile,
        parent: QWidget | None = None,
        *,
        services: DialogServices,
        process_factory=None,
    ) -> None:
        super().__init__(parent, services=services)
        self.setObjectName("workflowDialog")
        self.profile = profile
        self.setWindowTitle(f"Transfer Queue: {profile.name}")
        self.services.size_for_screen(
            self,
            parent,
            maximum_width=640,
            maximum_height=620,
            minimum_width=420,
            minimum_height=360,
        )

        root = QVBoxLayout(self)
        title = self.services.literal_label("Transfer queue")
        title.setObjectName("workflowTitle")
        subtitle = self.services.literal_label(f"Build and preview SFTP operations for {profile.name}.")
        subtitle.setObjectName("workflowSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)
        form = QFormLayout()
        self.operations = QPlainTextEdit()
        self.operations.setMinimumHeight(90)
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
        self.run_button = QPushButton("Run Queue")
        self.cancel_queue_button = QPushButton("Cancel Queue")
        self.cancel_queue_button.setObjectName("cancelTransferQueue")
        self.cancel_queue_button.setEnabled(False)
        controls.addWidget(self.preview_button)
        controls.addWidget(self.local_preview_button)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_queue_button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.preview = LiteralTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.preview.setMinimumHeight(100)
        root.addWidget(self.preview, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.setObjectName("transferQueueDialogButtons")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.preview_button.clicked.connect(self.refresh_queue_preview)
        self.local_preview_button.clicked.connect(self.refresh_local_preview)
        self.run_button.clicked.connect(self.run_queue)
        self.cancel_queue_button.clicked.connect(self.cancel_queue)
        self._process_factory = process_factory or _background_process
        self.active_queue_plan: SftpQueuePlan | None = None
        self.active_queue_index = 0
        self.active_queue_process: QProcess | None = None
        self.queue_cancel_requested = False
        self.queue_cancel_timer = QTimer(self)
        self.queue_cancel_timer.setSingleShot(True)
        self.queue_cancel_timer.setInterval(1500)
        self.queue_cancel_timer.timeout.connect(self.kill_cancelled_queue_process)

    def queue_is_active(self) -> bool:
        return self.active_queue_plan is not None

    def set_queue_controls_active(self, active: bool) -> None:
        for widget in (
            self.operations,
            self.local_preview_path,
            self.force_destructive,
            self.preview_button,
            self.local_preview_button,
            self.run_button,
        ):
            widget.setEnabled(not active)
        for standard_button in (
            QDialogButtonBox.StandardButton.Ok,
            QDialogButtonBox.StandardButton.Cancel,
        ):
            button = self.buttons.button(standard_button)
            if button is not None:
                button.setEnabled(not active)
        self.cancel_queue_button.setEnabled(active and not self.queue_cancel_requested)

    def finish_queue_execution(self, message: str) -> None:
        process = self.active_queue_process
        self.queue_cancel_timer.stop()
        self.active_queue_plan = None
        self.active_queue_index = 0
        self.active_queue_process = None
        self.queue_cancel_requested = False
        self.set_queue_controls_active(False)
        if message:
            self.preview.append(message)
        if process is not None:
            process.deleteLater()

    def accept(self) -> None:
        if self.queue_is_active():
            return
        super().accept()

    def reject(self) -> None:
        if self.queue_is_active():
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self.queue_is_active():
            event.ignore()
            return
        super().closeEvent(event)

    def queue_plan(self) -> SftpQueuePlan:
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

    def run_queue(self) -> None:
        if self.queue_is_active():
            return
        try:
            assert_profile_launch_allowed(self.profile, surface="gui")
            plan = self.queue_plan()
        except ValueError as exc:
            self.preview.setPlainText(f"error: {exc}")
            return
        if plan.destructive and not plan.force:
            self.preview.setPlainText("error: destructive queue actions require Force destructive actions before execution")
            return
        self.active_queue_plan = plan
        self.active_queue_index = 0
        self.active_queue_process = None
        self.queue_cancel_requested = False
        self.preview.clear()
        self.set_queue_controls_active(True)
        self.preview.append(f"queue started: {len(plan.items)} operation(s)")
        self.run_next_queue_item()

    def run_next_queue_item(self) -> None:
        plan = self.active_queue_plan
        if plan is None:
            return
        if self.active_queue_index >= len(plan.items):
            self.finish_queue_execution("queue completed")
            return
        index = self.active_queue_index
        command = plan.batch_commands[index]
        self.preview.append(f"{index + 1}/{len(plan.items)} {plan.items[index].action}: running")
        process = self._process_factory(self)
        runtime_command = openssh_command_without_windows_connection_sharing(list(plan.command))
        process.setProgram(runtime_command[0])
        process.setArguments(runtime_command[1:])
        process.readyReadStandardOutput.connect(
            lambda active=process: self.preview.append(bytes(active.readAllStandardOutput()).decode(errors="replace").rstrip())
        )
        process.readyReadStandardError.connect(
            lambda active=process: self.preview.append(bytes(active.readAllStandardError()).decode(errors="replace").rstrip())
        )
        process.started.connect(lambda active=process, queued=command: self.write_queue_command(active, queued))
        process.finished.connect(
            lambda exit_code, _status, active=process, queued_index=index: self.finish_queue_item(
                active, queued_index, exit_code
            )
        )
        process.errorOccurred.connect(
            lambda error, active=process, queued_index=index: self.handle_queue_process_error(
                active, queued_index, error
            )
        )
        self.active_queue_process = process
        process.start()

    def write_queue_command(self, process: QProcess, command: str) -> None:
        process.write(f"{command}\n".encode())
        process.closeWriteChannel()

    def finish_queue_item(self, process: QProcess, index: int, exit_code: int) -> None:
        plan = self.active_queue_plan
        if plan is None or process is not self.active_queue_process:
            return
        self.queue_cancel_timer.stop()
        self.active_queue_process = None
        process.deleteLater()
        if self.queue_cancel_requested:
            self.finish_queue_execution("queue cancelled")
            return
        if exit_code != 0:
            self.preview.append(f"{index + 1}/{len(plan.items)} {plan.items[index].action}: failed (exit {exit_code})")
            self.finish_queue_execution("queue stopped after failure")
            return
        self.preview.append(f"{index + 1}/{len(plan.items)} {plan.items[index].action}: completed")
        self.active_queue_index += 1
        self.run_next_queue_item()

    def handle_queue_process_error(self, process: QProcess, index: int, error) -> None:
        if process is not self.active_queue_process or self.active_queue_plan is None:
            return
        if self.queue_cancel_requested:
            if process.state() == QProcess.ProcessState.NotRunning:
                self.finish_queue_execution("queue cancelled")
            return
        if error == QProcess.ProcessError.FailedToStart:
            detail = process.errorString().strip() or "unknown process start error"
            self.preview.append(f"{index + 1}: failed to start ({detail})")
            self.finish_queue_execution("queue stopped after failure")

    def cancel_queue(self) -> None:
        if not self.queue_is_active() or self.queue_cancel_requested:
            return
        self.queue_cancel_requested = True
        self.set_queue_controls_active(True)
        self.preview.append("queue cancellation requested")
        process = self.active_queue_process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            self.finish_queue_execution("queue cancelled")
            return
        process.terminate()
        self.queue_cancel_timer.start()

    def kill_cancelled_queue_process(self) -> None:
        if not self.queue_cancel_requested:
            return
        process = self.active_queue_process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            self.finish_queue_execution("queue cancelled")
            return
        self.preview.append("queue process did not terminate; killing it")
        process.kill()

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
        children = data.get("children")
        if isinstance(children, (list, tuple)):
            for child in children:
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

class WorkflowDialog(ScreenBoundedDialog):
    def __init__(
        self,
        title: str,
        subtitle: str,
        rows: list[tuple[str, str, str]],
        detail: str,
        actions: Sequence[tuple[str, Callable[..., object]]] | None = None,
        parent: QWidget | None = None,
        *,
        services: DialogServices,
        message_handler: Callable[..., object],
    ) -> None:
        super().__init__(parent, services=services)
        self.message_handler = message_handler
        self.setObjectName("workflowDialog")
        self.setWindowTitle(title)
        self.services.size_for_screen(
            self,
            parent,
            maximum_width=660,
            maximum_height=520,
            minimum_width=420,
            minimum_height=360,
        )

        root = QVBoxLayout(self)
        root.setSpacing(10)
        title_label = self.services.literal_label(title)
        title_label.setObjectName("workflowTitle")
        subtitle_label = self.services.literal_label(subtitle)
        subtitle_label.setObjectName("workflowSubtitle")
        subtitle_label.setWordWrap(True)
        root.addWidget(title_label)
        root.addWidget(subtitle_label)

        self.rows = QTreeWidget()
        self.rows.setObjectName("workflowRows")
        self.rows.setColumnCount(3)
        self.rows.setHeaderLabels(["Workflow", "State", "Detail"])
        self.rows.setRootIsDecorated(False)
        for workflow, state, row_detail in rows:
            item = QTreeWidgetItem([workflow, state, row_detail])
            self.rows.addTopLevelItem(item)
        self.rows.resizeColumnToContents(0)
        self.rows.resizeColumnToContents(1)
        root.addWidget(self.rows, 1)

        self.detail = QTextEdit()
        self.detail.setObjectName("workflowPreview")
        self.detail.setReadOnly(True)
        self.detail.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.detail.setPlainText(detail)
        root.addWidget(self.detail, 1)

        action_footer = QFrame()
        action_footer.setObjectName("workflowFooter")
        action_row = QHBoxLayout(action_footer)
        action_row.setContentsMargins(0, 0, 0, 0)
        for label, callback in actions or []:
            button = QToolButton()
            button.setObjectName("workflowAction")
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.clicked.connect(self.workflow_action(callback))
            action_row.addWidget(button)
        action_row.addStretch(1)
        close_button = QToolButton()
        close_button.setObjectName("workflowAction")
        close_button.setText("Close")
        close_button.clicked.connect(self.accept)
        action_row.addWidget(close_button)
        root.addWidget(action_footer)

    def workflow_action(self, callback):
        def run(*_args) -> None:
            try:
                callback()
            except (OSError, ProcessStatusError) as exc:
                self.message_handler(QMessageBox.Icon.Warning, "Workspace operation failed", str(exc))
                return
            self.accept()

        return run
