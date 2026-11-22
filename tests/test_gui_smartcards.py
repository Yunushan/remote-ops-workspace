from __future__ import annotations

import base64
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from remote_ops_workspace.moba_smartcards import (
    build_smartcard_inventory_plan,
    smartcard_public_keys,
)

ALGORITHM = b"ssh-ed25519"
WIRE = len(ALGORITHM).to_bytes(4, "big") + ALGORITHM + b"\0\0\0\x20" + b"a" * 32
KEY = ALGORITHM + b" " + base64.b64encode(WIRE)
FINGERPRINT = "SHA256:" + base64.b64encode(hashlib.sha256(WIRE).digest()).decode().rstrip("=")


def test_inventory_strips_provider_prefix_and_parses_only_valid_unique_public_keys():
    assert build_smartcard_inventory_plan("PKCS11:/a path/provider.so").commands == [
        ["ssh-keygen", "-D", "/a path/provider.so"],
    ]
    assert smartcard_public_keys(b"\n".join((
        b"notice", b"tool AAAA", b"ssh-rsa @@@!", b"ssh-rsa " + base64.b64encode(WIRE),
        ALGORITHM + b" " + base64.b64encode(WIRE[:15]), KEY + b" token label", KEY + b" another comment",
    ))) == [(FINGERPRINT, KEY.decode())]


@pytest.fixture
def dialog(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    widgets = pytest.importorskip("PyQt6.QtWidgets")
    from remote_ops_workspace import gui_smartcards

    app = widgets.QApplication.instance() or widgets.QApplication([])
    parent = widgets.QWidget()
    process = Mock()
    process.write.side_effect = len
    process.readAllStandardOutput.return_value = b""
    monkeypatch.setattr(gui_smartcards, "_background_process", lambda _parent: process)
    qt = gui_smartcards.QProcess
    shim = SimpleNamespace(ProcessError=qt.ProcessError, ExitStatus=qt.ExitStatus,
                           UnixProcessParameters=SimpleNamespace, UnixProcessFlag=SimpleNamespace(CreateNewSession=1))
    monkeypatch.setattr(gui_smartcards, "QProcess", shim)
    monkeypatch.setattr(gui_smartcards, "os", SimpleNamespace(name="posix", path=gui_smartcards.os.path))
    path = tmp_path / "Middleware Library.so"
    path.write_bytes(b"fixture")
    widget = gui_smartcards.SmartCardDialog(parent, f"pkcs11:{path}", None)
    yield SimpleNamespace(app=app, parent=parent, module=gui_smartcards, widget=widget, process=process, path=str(path), qt=qt)
    if widget.operation is not None:
        widget.finish(1, qt.ExitStatus.CrashExit)
    widget.close()
    parent.close()


def test_inventory_launches_directly_refreshes_and_copies_public_keys(dialog, monkeypatch):
    widget, process = dialog.widget, dialog.process
    assert process.setUnixProcessParameters.call_args.args[0].flags == 1
    assert not widget.copy.isEnabled()
    widget.refresh.click()
    process.setProgram.assert_called_once_with("ssh-keygen")
    process.setArguments.assert_called_once_with(["-D", dialog.path])
    assert process.setProcessEnvironment.call_args.args[0].value("SSH_ASKPASS_REQUIRE") == "never"
    assert not widget.provider.isEnabled()
    widget.send_input()
    process.write.assert_not_called()
    process.closeWriteChannel.assert_called_once()
    process.readAllStandardOutput.side_effect = [KEY[:32], KEY[32:] + b" comment\n"]
    widget.read_output()
    widget.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert widget.keys.item(0).text() == f"ssh-ed25519  {FINGERPRINT}"
    assert widget.copy.isEnabled()
    widget.copy.click()
    assert dialog.app.clipboard().text() == KEY.decode()

    monkeypatch.setattr(dialog.module.QFileDialog, "getOpenFileName", lambda *_a: ("invalid-relative", ""))
    widget.browse.click()
    assert widget.keys.count() == 0
    widget.refresh.click()
    assert "absolute path" in widget.status.text()
    monkeypatch.setattr(dialog.module.QFileDialog, "getOpenFileName", lambda *_a: ("", ""))
    widget.browse.click()
    assert widget.provider.text() == "invalid-relative"
    widget.copy_key()
    widget.change_profile_key(clear=False)

    process.readAllStandardOutput.side_effect = None
    widget.provider.setText(dialog.path)
    widget.refresh.click()
    widget.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert "no OpenSSH public keys" in widget.status.text()
    widget.finish(0, dialog.qt.ExitStatus.NormalExit)


def test_agent_uses_masked_pin_on_stdin_and_authorized_provider_only(dialog, monkeypatch):
    widget, process, module = dialog.widget, dialog.process, dialog.module
    monkeypatch.setenv("SSH_AUTH_SOCK", "inherited-socket")
    assert widget.agent_environment().value("SSH_AUTH_SOCK") == "inherited-socket"
    widget.identity_agent = "SSH_AUTH_SOCK"
    assert widget.agent_environment().value("SSH_AUTH_SOCK") == "inherited-socket"
    widget.identity_agent = "chosen-socket"
    assert widget.agent_environment().value("SSH_AUTH_SOCK") == "chosen-socket"
    widget.identity_agent = "none"
    widget.load.click()
    assert "disables its SSH agent" in widget.status.text()
    widget.identity_agent = "\u0024{ROW_TEST_AGENT_SOCKET}"
    widget.load.click()
    assert "environment variable is empty" in widget.status.text()
    monkeypatch.setenv("ROW_TEST_AGENT_SOCKET", "chosen-socket")

    pin_prompt = Mock(side_effect=[("", False), ("11\n22", True), ("123456", True)])
    monkeypatch.setattr(module.QInputDialog, "getText", pin_prompt)
    widget.load.click()
    widget.load.click()
    assert "single line" in widget.status.text()
    process.start.assert_not_called()
    widget.load.click()
    assert pin_prompt.call_args.args[-1] == module.QLineEdit.EchoMode.Password
    process.setProgram.assert_called_once_with("ssh-add")
    process.setArguments.assert_called_once_with(["-s", dialog.path])
    assert process.setProcessEnvironment.call_args.args[0].value("SSH_AUTH_SOCK") == "chosen-socket"
    widget.send_input()
    process.write.assert_called_once_with(b"123456\n")
    assert not widget.pin
    widget.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert "loaded provider keys" in widget.status.text()

    answer = module.QMessageBox.StandardButton
    monkeypatch.setattr(module.QMessageBox, "question", Mock(side_effect=[answer.No, answer.Yes]))
    widget.unload.click()
    assert process.start.call_count == 1
    widget.unload.click()
    assert process.setArguments.call_args.args[0] == ["-e", dialog.path]
    widget.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert "removed provider keys" in widget.status.text()


def test_failed_process_timeout_oversize_and_cancel_are_reported(dialog):
    widget, process, qt = dialog.widget, dialog.process, dialog.qt
    widget.refresh.click()
    widget.process_error(qt.ProcessError.ReadError)
    widget.process_error(qt.ProcessError.FailedToStart)
    assert "OpenSSH client could not start" in widget.status.text()
    widget.refresh.click()
    widget.finish(1, qt.ExitStatus.NormalExit)
    assert "OpenSSH failed" in widget.status.text()
    widget.refresh.click()
    widget.finish(0, qt.ExitStatus.CrashExit)
    assert "OpenSSH failed" in widget.status.text()
    widget.refresh.click()
    process.readAllStandardOutput.return_value = b"x" * (1024 * 1024 + 1)
    widget.read_output()
    process.kill.assert_called_once()
    widget.finish(-1, qt.ExitStatus.CrashExit)
    assert "1 MiB" in widget.status.text()
    widget.refresh.click()
    widget.timed_out()
    widget.finish(-1, qt.ExitStatus.CrashExit)
    assert "timed out" in widget.status.text()
    widget.refresh.click()
    widget.reject()
    assert widget.operation == "discover"
    widget.finish(0, qt.ExitStatus.NormalExit)
    assert not widget.isVisible()
    assert widget.operation is None


def test_windows_inventory_leaves_unix_process_flags_unset(dialog, monkeypatch):
    monkeypatch.setattr(dialog.module.os, "name", "nt")
    dialog.process.setUnixProcessParameters.reset_mock()
    inventory = dialog.module.SmartCardDialog(dialog.parent, "", None)
    dialog.process.setUnixProcessParameters.assert_not_called()
    inventory.done(int(dialog.module.QDialog.DialogCode.Rejected))


def test_profile_key_controls_follow_selection_and_surface_store_errors(dialog):
    other_key = ALGORITHM + b" " + base64.b64encode(WIRE[:-1] + b"b")
    save = Mock()
    inventory = dialog.module.SmartCardDialog(dialog.parent, dialog.path, None, profile_name="card",
                                             pinned_key=other_key.decode(), save_profile_key=save)
    assert not inventory.use_key.isEnabled()
    inventory.change_profile_key(clear=False)
    save.assert_not_called()
    inventory.refresh.click()
    dialog.process.readAllStandardOutput.return_value = KEY + b"\n" + other_key + b"\n"
    inventory.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert inventory.keys.currentRow() == 1
    assert inventory.clear_key.isEnabled()
    inventory.keys.setCurrentRow(0)
    inventory.use_key.click()
    save.assert_called_once_with(dialog.path, KEY.decode())
    assert inventory.pinned_key == KEY.decode()
    save.side_effect = ValueError("write rejected by policy")
    inventory.clear_key.click()
    assert "write rejected by policy" in inventory.status.text()
    assert inventory.pinned_key == KEY.decode()
    save.side_effect = None
    inventory.clear_key.click()
    save.assert_called_with("", None)
    assert not inventory.clear_key.isEnabled()
    inventory.done(int(dialog.module.QDialog.DialogCode.Rejected))


def test_missing_saved_card_requires_explicit_replacement(dialog):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    other_key = ALGORITHM + b" " + base64.b64encode(WIRE[:-1] + b"b")
    save = Mock()
    inventory = dialog.module.SmartCardDialog(
        dialog.parent, dialog.path, None, profile_name="card",
        pinned_key=other_key.decode(), save_profile_key=save,
    )
    inventory.show()
    inventory.refresh.click()
    dialog.process.readAllStandardOutput.return_value = KEY + b"\n"
    inventory.finish(0, dialog.qt.ExitStatus.NormalExit)
    assert inventory.keys.count() == 1
    assert inventory.keys.currentItem() is None
    assert "saved key" in inventory.status.text().lower()
    assert not inventory.copy.isEnabled() and not inventory.use_key.isEnabled()
    assert inventory.clear_key.isEnabled()
    assert inventory.pinned_key == other_key.decode()
    save.assert_not_called()
    row = inventory.keys.item(0)
    QTest.mouseClick(inventory.keys.viewport(), Qt.MouseButton.LeftButton, pos=inventory.keys.visualItemRect(row).center())
    assert inventory.copy.isEnabled() and inventory.use_key.isEnabled()
    inventory.use_key.click()
    save.assert_called_once_with(dialog.path, KEY.decode())
    inventory.close()
