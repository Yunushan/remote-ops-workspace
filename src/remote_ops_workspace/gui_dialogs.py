from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .gui_editors import (
    layout_from_editor_data,
    layout_to_editor_data,
    profile_editor_protocols,
    profile_from_editor_data,
    profile_to_editor_data,
    protocol_preset_editor_data,
)
from .layouts import Layout, layout_splitter_size_lengths, validate_layout
from .models import Profile
from .profile_importers import ProfileImportResult

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
