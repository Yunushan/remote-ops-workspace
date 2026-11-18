from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .gui_processes import _background_process
from .moba_smartcards import build_smartcard_inventory_plan
from .smartcard_keys import smartcard_public_keys


class SmartCardDialog(QDialog):
    """Discover a configured provider and manage its keys in the SSH agent."""

    def __init__(
        self,
        parent: QWidget,
        provider: str,
        identity_agent: str | None,
        *,
        profile_name: str = "",
        pinned_key: str = "",
        save_profile_key: Callable[[str, str | None], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("PKCS#11 smart cards")
        self.resize(680, 365)
        self.identity_agent = identity_agent
        self.pinned_key = pinned_key
        self.save_profile_key = save_profile_key
        self.operation: str | None = None
        self.close_result: int | None = None
        self.failure = ""
        self.output = bytearray()
        self.pin = bytearray()

        self.process = _background_process(self)
        if os.name != "nt":
            # Give ssh-add pipe-backed stdin even when ROW was launched from a terminal.
            # The Windows PyQt stubs omit these Unix-only classes.
            params = getattr(QProcess, "UnixProcessParameters")()  # noqa: B009
            params.flags = getattr(QProcess, "UnixProcessFlag").CreateNewSession  # noqa: B009
            self.process.setUnixProcessParameters(params)
        self.process.started.connect(self.send_input)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.process.readAllStandardError)
        self.process.finished.connect(self.finish)
        self.process.errorOccurred.connect(self.process_error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timed_out)

        layout = QVBoxLayout(self)
        label = QLabel("PKCS#11 library")
        layout.addWidget(label)
        path_row = QHBoxLayout()
        self.provider = QLineEdit(provider)
        self.provider.setPlaceholderText("Absolute path to an installed PKCS#11 library")
        label.setBuddy(self.provider)
        self.browse = QPushButton("Browse…")
        self.browse.clicked.connect(self.choose_library)
        path_row.addWidget(self.provider, 1)
        path_row.addWidget(self.browse)
        layout.addLayout(path_row)

        self.keys = QListWidget()
        self.keys.setAccessibleName("Discovered OpenSSH public keys")
        self.keys.itemSelectionChanged.connect(self.update_controls)
        self.provider.textChanged.connect(self.keys.clear)
        layout.addWidget(self.keys, 1)
        self.status = QLabel("Choose a library you trust, then refresh to read its public keys.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.use_key = QPushButton("Use key for profile", self)
        self.use_key.setAutoDefault(False)
        self.use_key.clicked.connect(lambda: self.change_profile_key(clear=False))
        self.clear_key = QPushButton("Clear saved selection", self)
        self.clear_key.setAutoDefault(False)
        self.clear_key.clicked.connect(lambda: self.change_profile_key(clear=True))
        if save_profile_key is not None:
            profile_row = QHBoxLayout()
            profile_label = QLabel(f"SSH profile: {profile_name}")
            profile_label.setTextFormat(Qt.TextFormat.PlainText)
            profile_row.addWidget(profile_label, 1)
            profile_row.addWidget(self.use_key)
            profile_row.addWidget(self.clear_key)
            layout.addLayout(profile_row)
        else:
            self.use_key.hide()
            self.clear_key.hide()

        action_row = QHBoxLayout()
        self.refresh = QPushButton("Refresh keys")
        self.refresh.clicked.connect(self.discover)
        self.copy = QPushButton("Copy public key")
        self.copy.clicked.connect(self.copy_key)
        self.load = QPushButton("Load into SSH agent")
        self.load.clicked.connect(lambda: self.change_agent(load=True))
        self.unload = QPushButton("Remove from SSH agent")
        self.unload.clicked.connect(lambda: self.change_agent(load=False))
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for button in (self.refresh, self.copy, self.load, self.unload, close):
            button.setAutoDefault(False)
            action_row.addWidget(button)
        layout.addLayout(action_row)
        self.update_controls()

    def update_controls(self) -> None:
        idle = self.operation is None
        for control in (self.provider, self.browse, self.refresh, self.load, self.unload):
            control.setEnabled(idle)
        has_key = self.keys.currentItem() is not None
        self.copy.setEnabled(idle and has_key)
        self.use_key.setEnabled(idle and self.save_profile_key is not None and has_key)
        self.clear_key.setEnabled(idle and bool(self.pinned_key))

    def choose_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PKCS#11 library", "", "Libraries (*.dll *.so *.dylib);;All files (*)")
        if path:
            self.provider.setText(path)

    def library_path(self) -> str:
        plan = build_smartcard_inventory_plan(self.provider.text().strip())
        command = plan.commands[0]
        path = Path(command[-1])
        if command[0] != "ssh-keygen" or not path.is_absolute() or not path.is_file():
            raise ValueError("Choose the absolute path to an installed PKCS#11 library.")
        return str(path)

    def discover(self) -> None:
        self.keys.clear()
        try:
            path = self.library_path()
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
            return
        self.run("discover", ["ssh-keygen", "-D", path], QProcessEnvironment.systemEnvironment())

    def copy_key(self) -> None:
        item = self.keys.currentItem()
        clipboard = QApplication.clipboard()
        if item is not None and clipboard is not None:
            clipboard.setText(str(item.data(Qt.ItemDataRole.UserRole)))
            self.status.setText("OpenSSH public key copied.")

    def change_profile_key(self, *, clear: bool) -> None:
        if self.save_profile_key is None:
            return
        item = self.keys.currentItem()
        if not clear and item is None:
            return
        try:
            if clear:
                self.save_profile_key("", None)
                self.pinned_key = ""
                self.status.setText("Saved smart-card key selection cleared.")
            else:
                assert item is not None
                key = str(item.data(Qt.ItemDataRole.UserRole))
                self.save_profile_key(self.library_path(), key)
                self.pinned_key = key
                self.status.setText(f"Saved {item.text()} for this SSH profile.")
        except (KeyError, OSError, ValueError) as exc:
            self.status.setText(str(exc))
        self.update_controls()

    def change_agent(self, *, load: bool) -> None:
        try:
            path = self.library_path()
            environment = self.agent_environment()
        except (OSError, ValueError) as exc:
            self.status.setText(str(exc))
            return
        if load:
            pin, accepted = QInputDialog.getText(
                self, "Load card into SSH agent", "Enter the PIN for this card.", QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return
            if any(char in pin for char in "\r\n\x00"):
                self.status.setText("Enter the PIN on a single line.")
                return
            self.pin.extend((pin + "\n").encode("utf-8"))
            self.run("load", ["ssh-add", "-s", path], environment)
        elif QMessageBox.question(
            self, "Remove card from SSH agent", "Remove all keys supplied by this provider from the SSH agent?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.run("unload", ["ssh-add", "-e", path], environment)

    def agent_environment(self) -> QProcessEnvironment:
        env = QProcessEnvironment.systemEnvironment()
        override = self.identity_agent
        if override and override.casefold() == "none":
            raise ValueError("The selected profile disables its SSH agent.")
        if override and override != "SSH_AUTH_SOCK":
            socket = os.path.expanduser(override)
            if socket.startswith("$"):
                socket = env.value(socket[1:].removeprefix("{").removesuffix("}"))
                if not socket:
                    raise ValueError("The profile’s SSH agent environment variable is empty.")
            env.insert("SSH_AUTH_SOCK", socket)
        return env

    def run(self, operation: str, command: list[str], environment: QProcessEnvironment) -> None:
        self.operation = operation
        self.failure = ""
        self.output.clear()
        self.status.setText("Running OpenSSH…")
        self.update_controls()
        environment.insert("SSH_ASKPASS_REQUIRE", "never")
        self.process.setProcessEnvironment(environment)
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.timer.start(15_000)
        self.process.start()

    def send_input(self) -> None:
        if self.pin:
            self.process.write(bytes(self.pin))
            self.clear_pin()
        self.process.closeWriteChannel()

    def clear_pin(self) -> None:
        self.pin[:] = b"\0" * len(self.pin)
        self.pin.clear()

    def read_output(self) -> None:
        chunk = bytes(self.process.readAllStandardOutput())
        if self.operation == "discover" and not self.failure:
            if len(self.output) + len(chunk) > 1024 * 1024:
                self.failure = "The provider returned more than 1 MiB of public-key output."
                self.process.kill()
                return
            self.output.extend(chunk)

    def process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.failure = "The OpenSSH client could not start. Check that ssh-keygen and ssh-add are installed."
            self.finish(1, QProcess.ExitStatus.CrashExit)

    def timed_out(self) -> None:
        self.failure = "The OpenSSH operation timed out."
        self.process.kill()

    def finish(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if self.operation is None:
            return
        self.timer.stop()
        self.clear_pin()
        self.read_output()
        operation, self.operation = self.operation, None
        if self.close_result is not None:
            super().done(self.close_result)
            return
        if self.failure:
            self.status.setText(self.failure)
        elif exit_code or exit_status != QProcess.ExitStatus.NormalExit:
            self.status.setText("OpenSSH failed. Check the card, library, and SSH agent configuration.")
        elif operation == "discover":
            selected_row = 0
            for row, (fingerprint, key) in enumerate(smartcard_public_keys(bytes(self.output))):
                item = QListWidgetItem(f"{key.split()[0]}  {fingerprint}")
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.keys.addItem(item)
                if key == self.pinned_key:
                    selected_row = row
            if self.keys.count():
                self.keys.setCurrentRow(selected_row)
                self.status.setText(f"Found {self.keys.count()} OpenSSH public key(s).")
            else:
                self.status.setText("The provider returned no OpenSSH public keys.")
        elif operation == "load":
            self.status.setText("OpenSSH loaded provider keys into the SSH agent.")
        else:
            self.status.setText("OpenSSH removed provider keys from the SSH agent.")
        self.update_controls()

    def done(self, result: int) -> None:
        if self.operation is None:
            super().done(result)
            return
        self.close_result = result
        self.clear_pin()
        self.process.kill()
