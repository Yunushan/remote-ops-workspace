"""Interactive controls in the Moba-style Servers window."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .embedded_cron import default_crontab_path, read_crontab_text, save_crontab_text
from .gui_dialogs import WorkflowDialog, _literal_label
from .gui_server_lifecycle import DEFAULT_STOP_SECONDS, ServerLifecycleManager, ServicePreferences
from .gui_values import _required_gui_value, restore_document_format
from .moba_servers import MobaEmbeddedServerGuiConfigRow, MobaEmbeddedServerGuiConfigSurface


class ServerSettingsDialog(QDialog):
    def __init__(self, service: str, manager: ServerLifecycleManager, parent: QWidget) -> None:
        super().__init__(parent)
        self.service = service
        self.manager = manager
        self.setWindowTitle(f"{service.capitalize()} server settings")
        prefs = manager.preferences(service)
        form = QFormLayout(self)
        self.timeout = QCheckBox("Stop server after")
        self.seconds = QSpinBox()
        self.seconds.setRange(1, 65535)
        self.seconds.setSuffix(" s")
        self.seconds.setValue(prefs.auto_stop_seconds or DEFAULT_STOP_SECONDS)
        self.timeout.toggled.connect(self.seconds.setEnabled)
        self.timeout.setChecked(prefs.auto_stop_seconds is not None)
        self.seconds.setEnabled(self.timeout.isChecked())
        form.addRow(self.timeout, self.seconds)
        self.autostart = QCheckBox("Start Cron when Remote Ops Workspace starts")
        if service == "cron":
            self.autostart.setChecked(prefs.start_with_app)
            form.addRow(self.autostart)
            self.schedule_path = _literal_label(default_crontab_path())
            self.schedule_path.setWordWrap(True)
            self.schedule_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow("Crontab file", self.schedule_path)
            edit = QPushButton("Edit crontab…")
            edit.clicked.connect(self.edit_crontab)
            form.addRow(edit)
        else:
            form.addRow("Default client", _literal_label("iperf -c 127.0.0.1"))
        self.error = _literal_label("")
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save_settings)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def save_settings(self) -> None:
        seconds = self.seconds.value() if self.timeout.isChecked() else None
        try:
            self.manager.save_preferences(self.service, ServicePreferences(seconds, self.autostart.isChecked()))
        except (OSError, ValueError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()

    def edit_crontab(self) -> None:
        try:
            baseline = read_crontab_text()
        except (OSError, ValueError) as exc:
            self.error.setText(str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit crontab")
        layout = QVBoxLayout(dialog)
        layout.addWidget(_literal_label("Minute  Hour  Day of month  Month  Day of week  Command"))
        editor = QPlainTextEdit(baseline)
        editor.setAccessibleName("Crontab")
        layout.addWidget(editor)
        error = _literal_label("")
        error.setWordWrap(True)
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        def save() -> None:
            try:
                document = _required_gui_value(editor.document(), "crontab editor document")
                save_crontab_text(restore_document_format(baseline, document.toRawText()), expected=baseline)
            except (OSError, ValueError) as exc:
                error.setText(str(exc))
                return
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()


class ServerRowControls(QWidget):
    def __init__(
        self, entry: MobaEmbeddedServerGuiConfigRow, row: QTreeWidgetItem,
        manager: ServerLifecycleManager, dialog: WorkflowDialog,
    ) -> None:
        super().__init__(dialog.rows)
        self.entry = entry
        self.service = entry.service
        self.row = row
        self.manager = manager
        self.dialog = dialog
        actions = QHBoxLayout(self)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(3)
        self.start_button = QToolButton()
        self.stop_button = QToolButton()
        settings = QToolButton()
        for button, label in ((self.start_button, "Start"), (self.stop_button, "Stop"), (settings, "Settings")):
            button.setText(label)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(label) + 32)
            button.setAccessibleName(f"{row.text(0)} {label}")
            actions.addWidget(button)
        self.start_button.clicked.connect(self.start)
        self.stop_button.clicked.connect(self.stop)
        settings.clicked.connect(self.configure)
        self.update_state(self.service, "running" if row.text(1) == "running" else "stopped", "")
        manager.changed.connect(self.update_state)

    def start(self) -> None:
        self.dialog.rows.setCurrentItem(self.row)
        self.manager.start(self.service)

    def stop(self) -> None:
        self.dialog.rows.setCurrentItem(self.row)
        self.manager.stop(self.service)

    def configure(self) -> None:
        self.dialog.rows.setCurrentItem(self.row)
        try:
            settings = ServerSettingsDialog(self.service, self.manager, self.dialog)
        except (OSError, ValueError) as exc:
            self.dialog.detail.setPlainText(str(exc))
            return
        settings.exec()

    def update_state(self, service: str, state: str, detail: str) -> None:
        if self.service != service:
            return
        self.row.setText(1, state)
        self.start_button.setEnabled(state == "stopped")
        self.stop_button.setEnabled(state == "running")
        record = self.manager.observed_records.get(service)
        if service == "cron":
            path = record.command[-1] if record and record.running else default_crontab_path()
            description = f"Schedule file: {path}"
        elif record and record.running:
            host = f"[{record.host}]" if ":" in record.host else record.host
            endpoint = f"{host}:{record.port}"
            self.row.setText(2, endpoint)
            description = f"{record.runtime_key} listening on {endpoint}"
        else:
            self.row.setText(2, "127.0.0.1:5001" if self.entry.runtime_available else "Iperf 2 required")
            description = "Local Iperf 2 client: iperf -c 127.0.0.1"
        self.row.setData(2, Qt.ItemDataRole.UserRole, description)
        if self.dialog.rows.currentItem() is self.row:
            message = f"{self.row.text(0)}\n{detail}" if detail else _row_detail(self.entry, description)
            if self.dialog.detail.toPlainText() != message:
                self.dialog.detail.setPlainText(message)


def _row_detail(entry: MobaEmbeddedServerGuiConfigRow, description: str) -> str:
    return "\n".join((entry.label, description, entry.config_action, entry.start_action, entry.stop_action))


def add_server_controls(
    dialog: WorkflowDialog, surface: MobaEmbeddedServerGuiConfigSurface, manager: ServerLifecycleManager,
) -> None:
    tree = dialog.rows
    tree.setHeaderLabels(["Service", "State", "Configuration", "Controls"])
    dialog.detail.setMaximumHeight(100)
    for index, entry in enumerate(surface.rows):
        if entry.service in {"cron", "iperf"}:
            row = tree.topLevelItem(index)
            assert row is not None  # WorkflowDialog creates one item per surface row.
            if entry.service == "iperf":
                row.setToolTip(2, "Requires an iperf (version 2) executable on PATH or in the ROW daemon bundle.")
            controls = ServerRowControls(entry, row, manager, dialog)
            row.setSizeHint(0, QSize(0, controls.sizeHint().height() + 4))
            tree.setItemWidget(row, 3, controls)
    header = _required_gui_value(tree.header(), "server table header")
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def show_selection(current: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        selected = surface.rows[tree.indexOfTopLevelItem(current)]
        description = current.data(2, Qt.ItemDataRole.UserRole) or current.text(2)
        dialog.detail.setPlainText(_row_detail(selected, description))

    tree.currentItemChanged.connect(show_selection)
    timer = QTimer(dialog)

    def refresh() -> None:
        manager.refresh("cron")
        manager.refresh("iperf")

    timer.timeout.connect(refresh)
    timer.start(4000)
    dialog.finished.connect(timer.stop)
    dialog.finished.connect(dialog.deleteLater)
    refresh()
