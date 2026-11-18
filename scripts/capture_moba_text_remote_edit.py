"""Capture a real SFTP editor session through the installed release wheel."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
from importlib.metadata import distribution
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

FIXTURE = Path("/fixture")
HOST = "row-editor-server"
PORT = 2222
USER = "rowedit"
FILENAME = "document.txt"
REMOTE = f"/home/{USER}/{FILENAME}"
TARGET = "linux-x86_64"
ORIGINAL = "opening fixture: café\n".encode()
FIRST = b"first concurrent revision\n"
SECOND = b"newer concurrent revision\n"
EDITED = "operator editor bytes: résumé\n".encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_fixture() -> None:
    if (sys.platform != "linux" or os.uname().machine != "x86_64"
            or not Path("/.dockerenv").is_file()):
        raise ValueError("editor capture requires the Linux x86_64 fixture container")
    routes = Path("/proc/net/route").read_text(encoding="ascii").splitlines()[1:]
    if any(row.split()[1] == "00000000" for row in routes):
        raise ValueError("editor capture requires a network without an internet route")
    server = ipaddress.IPv4Address(socket.gethostbyname(HOST))
    if not server.is_private or server.is_loopback:
        raise ValueError("editor capture requires the private SSH fixture peer")


def verify_wheel(wheel: Path) -> tuple[str, dict[str, str]]:
    match = re.fullmatch(r"remote_ops_workspace-(\d+\.\d+\.\d+)-py3-none-any\.whl", wheel.name)
    installed = distribution("remote-ops-workspace")
    if match is None or installed.version != match[1] or wheel.is_symlink():
        raise ValueError("installed distribution must match the exact release wheel")
    package = Path(installed.locate_file("remote_ops_workspace")).resolve(strict=True)
    content = wheel.read_bytes()
    digest = sha256(content)
    with ZipFile(wheel) as archive:
        entries = [item for item in archive.infolist()
                   if item.filename.startswith("remote_ops_workspace/") and not item.is_dir()]
        if not entries or len({item.filename for item in entries}) != len(entries):
            raise ValueError("release wheel package files are missing or duplicated")
        for item in entries:
            _, relative = item.filename.split("/", 1)
            path = (package / relative).resolve(strict=True)
            if not path.is_relative_to(package) or path.read_bytes() != archive.read(item):
                raise ValueError(f"installed package bytes differ from the release wheel: {relative}")
    import remote_ops_workspace

    if Path(remote_ops_workspace.__file__).resolve().parent != package or sha256(wheel.read_bytes()) != digest:
        raise ValueError("capture must import the verified installed package")
    return f"v{installed.version}", {"name": wheel.name, "sha256": digest}


def server_file(content: bytes | None = None) -> bytes:
    command = f"cat {REMOTE}" if content is None else f"cat > {REMOTE}"
    return subprocess.run(
        ["/usr/bin/ssh", "-oBatchMode=yes", "-oStrictHostKeyChecking=yes", "-oIdentitiesOnly=yes",
         f"-oUserKnownHostsFile={FIXTURE / 'known_hosts'}", "-i", str(FIXTURE / "identity"),
         "-p", str(PORT), f"{USER}@{HOST}", command],
        input=content, capture_output=True, timeout=8, check=True,
    ).stdout


def capture_editor(root: Path, raw: Path):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.storage import ProfileStore
    from remote_ops_workspace.terminal import terminal_plan_for_profile

    profile = Profile(
        name="editor-proof", protocol="ssh", host=HOST, port=PORT, username=USER,
        identity_file=str(FIXTURE / "identity"),
        options={"strict_host_key_checking": "yes", "user_known_hosts_file": str(FIXTURE / "known_hosts")},
    )
    ProfileStore().save([profile])
    app, window = create_main_window(["editor-proof"], show=False, preview_samples=False)
    window.resize(1180, 800)
    window.show()
    window.set_design_preset("mobaxterm")
    panel = window.open_moba_connected_session_tab(
        profile, terminal_plan_for_profile(profile), remote_path=str(Path(REMOTE).parent),
    )
    app.processEvents()
    dock = window.moba_connected_dock
    editor = dock.text_editor
    dock.set_remote_monitoring_runtime(False, immediate=False)
    dialogs, pending, errors = [], [], []

    def answer_dialog() -> None:
        dialog = app.activeModalWidget()
        if not isinstance(dialog, QMessageBox):
            return
        try:
            title, button, revision = pending.pop(0)
            if dialog.windowTitle() != title:
                raise ValueError(f"unexpected editor dialog: {dialog.windowTitle()}")
            if revision is not None:
                server_file(revision)
            dialogs.append({
                "title": title, "decision": button.name,
                "default_is_no": dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.No),
                "text": dialog.text(), "detail": dialog.detailedText(),
                "remote_sha256_at_answer": sha256(server_file()),
            })
            dialog.button(button).click()
        except Exception as exc:
            errors.append(str(exc))
            dialog.reject()

    def wait_for(predicate) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if errors:
                raise ValueError(f"editor dialog failed: {errors[0]}")
            if predicate():
                return
            QTest.qWait(15)
        detail = dock.sftp_refresh_output_buffer.decode("utf-8", errors="replace")
        terminal = panel.terminal_pane.output.toPlainText()
        raise TimeoutError(
            f"editor capture timed out: {window.statusBar().currentMessage()}\n{detail}\n{terminal[-3000:]}"
        )

    def find_document():
        return next((item for index in range(dock.file_table.topLevelItemCount())
                     if (item := dock.file_table.topLevelItem(index)).text(0) == FILENAME), None)

    def save_with(*decisions) -> None:
        pending.extend(("Remote file changed", button, revision) for button, revision in decisions)
        if not dock.text_editor_save_button.isEnabled():
            raise ValueError("the connected editor did not offer Save")
        dock.text_editor_save_button.click()
        wait_for(lambda: not pending and not dock.text_editor_active_generation
                 and not dock.text_editor_review_in_progress)

    timer = QTimer()
    timer.timeout.connect(answer_dialog)
    timer.start(20)
    try:
        if server_file() != ORIGINAL:
            raise ValueError("the SSH fixture does not contain the expected initial UTF-8 bytes")
        dock.request_sftp_refresh(reason="proof")
        wait_for(lambda: dock.file_table.isVisible() and find_document())
        dock.file_table.itemDoubleClicked.emit(find_document(), 0)
        wait_for(lambda: editor.isVisible() and editor.property("mobaTextEditorContentLoaded"))
        opened = editor.toPlainText().encode()
        if opened != ORIGINAL or editor.property("mobaTextEditorRemoteSha256") != sha256(opened):
            raise ValueError("the connected editor did not open the fixture through SFTP")
        editor.setPlainText(EDITED.decode())
        pending.append(("Remote text diff", QMessageBox.StandardButton.Ok, None))
        dock.text_editor_diff_button.click()
        wait_for(lambda: not pending)

        server_file(FIRST)
        save_with((QMessageBox.StandardButton.No, None))
        first = server_file()
        if first != FIRST or editor.property("mobaTextEditorStatus") != "conflict":
            raise ValueError("the first declined overwrite changed the remote file")
        save_with((QMessageBox.StandardButton.Yes, SECOND), (QMessageBox.StandardButton.No, None))
        second = server_file()
        staged = editor.toPlainText().encode()
        if second != SECOND or staged != EDITED or editor.property("mobaTextEditorStatus") != "conflict":
            raise ValueError("the new remote revision was not protected by a fresh overwrite review")
        save_with((QMessageBox.StandardButton.Yes, None))
        saved = server_file()
        if (saved != staged or editor.property("mobaTextEditorStatus") != "saved"
                or editor.property("mobaTextEditorDirty")):
            raise ValueError("the approved save did not upload the staged editor bytes")

        (raw / "opened.txt").write_bytes(opened)
        (raw / "saved.txt").write_bytes(saved)
        write_json(raw / "dialogs.json", dialogs)
        for name, data in (("first_conflict", first), ("second_conflict", second),
                           ("staged", staged), ("server_readback", server_file())):
            (root / f"{name}.txt").write_bytes(data)
        write_json(root / "diagnostics.json", {
            "status": window.statusBar().currentMessage(), "errors": errors,
            "sftp_output": dock.text_editor_output_buffer.decode("utf-8", errors="replace"),
        })
        return profile, sha256(opened)
    finally:
        timer.stop()
        dock.shutdown_runtime()
        panel.terminal_pane.stop()
        window.close()
        app.processEvents()


def bind_attachment(path: Path) -> dict[str, str]:
    return {"evidence_file": path.name, "evidence_sha256": sha256(path.read_bytes())}


def assemble(root: Path, raw: Path, profile, opened_digest: str, identity: dict) -> None:
    from remote_ops_workspace.moba_text import (
        build_moba_text_release_evidence_bundle_plan,
        write_moba_text_release_evidence_bundle,
    )
    from scripts.check_moba_text_remote_edit_evidence import (
        read_attachment,
        validate_remote_editor_release_evidence,
        verify_editor_capture,
    )

    (root / "sshd.log").write_bytes((FIXTURE / "sshd.log").read_bytes())
    capture = {
        "schema": "row.moba-text.connected-edit-capture.v1", "status": "passed",
        "profile": profile.name, "remote_path": REMOTE, "ssh_login": USER,
        "declined_remote_sha256": sha256((root / "first_conflict.txt").read_bytes()),
        "changed_during_approval_remote_sha256": sha256((root / "second_conflict.txt").read_bytes()),
        **identity,
    }
    for name in ("first_conflict", "second_conflict", "staged", "server_readback", "diagnostics", "sshd"):
        suffix = {"diagnostics": ".json", "sshd": ".log"}.get(name, ".txt")
        capture["sshd_log" if name == "sshd" else name] = bind_attachment(root / f"{name}{suffix}")
    write_json(raw / "capture.json", capture)
    plan = build_moba_text_release_evidence_bundle_plan(
        profile, REMOTE, out_dir=root, local_path=root / "staged.txt", remote_sha256=opened_digest,
        open_evidence=raw / "opened.txt", save_review_evidence=raw / "dialogs.json",
        save_evidence=raw / "saved.txt", connected_evidence=raw / "capture.json", release_target=TARGET,
        real_connected_session=True, sftp_browser_open=True, editor_tab_visible=True,
    )
    bundle = write_moba_text_release_evidence_bundle(plan, profile=profile)
    if not bundle.validation.passed:
        raise ValueError(f"editor evidence bundle failed: {bundle.validation.errors}")
    path = Path(bundle.evidence_path).rename(root / "evidence.json")
    manifest = {**json.loads(path.read_bytes()), **identity}
    write_json(path, manifest)
    if "source" in identity:
        result = validate_remote_editor_release_evidence(path, assets_dir=root)
        if not result.passed:
            raise ValueError(f"release editor evidence failed: {result.errors}")
    else:
        actions = {name: read_attachment(root, manifest[name], name)
                   for name in ("open_action", "save_review", "save_action")}
        result = verify_editor_capture(root, manifest, capture, actions)
        write_json(root / "local-qualification.json", {**result, **identity, "production_acceptance": False})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_fixture()
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("editor capture output must be a new directory")
    tag, asset = verify_wheel(args.wheel)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.debian_release_fixture import actions_source

    identity = {"release_target": TARGET, "release_asset": asset}
    if source := actions_source(tag):
        identity["source"] = source
    with TemporaryDirectory(prefix=".editor-capture-", dir=args.out.parent) as work:
        raw, root = Path(work) / "raw", Path(work) / "review"
        raw.mkdir()
        root.mkdir()
        with TemporaryDirectory(prefix="row-editor-state-") as home:
            os.environ.update(ROW_HOME=home, QT_QPA_PLATFORM="offscreen")
            profile, opened = capture_editor(root, raw)
            assemble(root, raw, profile, opened, identity)
        # The fixture runs as root, but the hosted artifact uploader does not.
        # Only the reviewed capture is made readable outside the private work tree.
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        root.chmod(0o755)
        root.rename(args.out)
    print("Connected editor verified the installed wheel, live SFTP diff and both overwrite refusals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
