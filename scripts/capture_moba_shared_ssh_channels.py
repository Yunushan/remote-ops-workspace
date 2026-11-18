"""Qualify the installed desktop's shared SSH channels against a private peer."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.capture_transport_terminal_probes import (  # noqa: E402
    PEER_COMMAND,
    PEER_PROGRAM,
    capture_grid,
    capture_modes,
    capture_vim,
    peer_observations,
)
from scripts.check_moba_transport_terminal_evidence import (  # noqa: E402
    CLIENT_HOST_KEY,
    MAX_CAPTURE_BYTES,
    SSH_VIEWS,
    TERMINAL_SFTP_SHA,
    TERMINAL_SOCKET,
    verify_connected_captures,
    verify_connection_states,
    verify_screen_captures,
    verify_ssh_channels,
)
from scripts.qt_release_capture import (  # noqa: E402
    EDITOR_ORIGINAL,
    EDITOR_USER,
    FIXTURE,
    HOST,
    PORT,
    run_capture,
    sha256,
    write_json,
)

SCREEN_FILES = {
    "terminal_grid": {"initial_screen": "initial-screen.json", "updated_screen": "updated-screen.json"},
    "alternate_screen": {"primary_before": "primary-before.json", "alternate_screen": "alternate-screen.json",
                         "primary_restored": "primary-restored.json"},
    "terminal_modes": {"mode_capture": "mode-capture.json"},
}
PEER_PROGRAM_SHA = re.compile(r"^ROW_PEER_HELPER_SHA256_([0-9a-f]{64})[ \t]*$", re.MULTILINE)


@dataclass(frozen=True)
class TransportPeer:
    host: str
    port: int
    user: str
    identity_file: Path
    known_hosts: Path
    sshd_log: Path


def capture(root: Path, raw: Path, identity: dict) -> None:
    peer = TransportPeer(HOST, PORT, EDITOR_USER, FIXTURE / "identity", FIXTURE / "known_hosts", FIXTURE / "sshd.log")
    report = capture_session(root, raw, peer)
    write_json(root / "local-qualification.json", {**identity, **report, "production_acceptance": False})


def capture_session(root: Path, raw: Path, peer: TransportPeer, *, native: bool = False) -> dict:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.storage import ProfileStore
    from remote_ops_workspace.terminal import terminal_plan_for_profile

    started_at = time.monotonic()
    initial_log = peer.sshd_log.stat()
    profile = Profile(
        name="shared-transport-proof", protocol="ssh", host=peer.host, port=peer.port, username=peer.user,
        identity_file=str(peer.identity_file),
        options={"strict_host_key_checking": "yes", "user_known_hosts_file": str(peer.known_hosts),
                 "identity_agent": "none"},
    )
    ProfileStore().save([profile])
    app, window = create_main_window(["transport-proof"], show=False)
    window.resize(1500, 960)
    window.show()
    window.set_design_preset("mobaxterm")
    original_plan = terminal_plan_for_profile(profile)
    client_log = raw / "ssh-client.log"
    plan = replace(original_plan, command=[
        original_plan.command[0], "-F", os.devnull, "-v", "-E", str(client_log),
        "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", f"GlobalKnownHostsFile={os.devnull}",
        *original_plan.command[1:],
    ])
    panel = window.open_moba_connected_session_tab(profile, plan, remote_path=f"/home/{peer.user}")
    pane, dock = panel.terminal_pane, window.moba_connected_dock
    if pane.ssh_connection is None or dock is None:
        raise ValueError("the connected desktop did not create a shared SSH terminal and dock")
    connection = pane.ssh_connection
    states: list[dict[str, object]] = []
    connection.changed.connect(lambda state: states.append(state.properties()))

    def wait_for(predicate, label: str) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(15)
        raise TimeoutError(
            f"{label}: {connection.state.properties()}\n"
            f"{dock.monitoring_output_buffer[-1000:]!r}\n{pane.output.toPlainText()[-2000:]}"
        )

    def submit(line: str) -> None:
        QTest.keyClicks(pane.output, line)
        QTest.keyClick(pane.output, Qt.Key.Key_Return)

    def document():
        return next((item for index in range(dock.file_table.topLevelItemCount())
                     if (item := dock.file_table.topLevelItem(index)).text(0) == "document.txt"), None)

    try:
        wait_for(lambda: connection.state.phase == "connected", "authenticated master")
        socket = dock.shared_ssh_control_path()
        if not socket or socket != pane.ssh_control_path:
            raise ValueError("SFTP and monitoring did not discover the terminal's SSH master")
        widgets = (pane.output, dock.browser, dock.remote_monitoring_panel)
        connected_views = {
            name: widget.property("sshConnectionState") for name, widget in zip(SSH_VIEWS, widgets, strict=True)
        }

        submit(r"""printf 'ROW_SHARED_%s\n' "$SSH_CONNECTION" """.strip())
        wait_for(lambda: TERMINAL_SOCKET.search(pane.output.toPlainText()), "terminal SSH socket round trip")
        match = TERMINAL_SOCKET.search(pane.output.toPlainText())
        assert match is not None
        client_address, client_port, endpoint, endpoint_port = match.groups()
        submit(r"""sha256sum -- document.txt | cut -d ' ' -f1 | sed 's/^/ROW_SFTP_SHA256_/'""")
        wait_for(lambda: TERMINAL_SFTP_SHA.search(pane.output.toPlainText()), "independent remote file digest")
        dock.request_sftp_refresh(reason="proof")
        wait_for(document, "SFTP listing on the shared SSH master")
        dock.file_table.itemDoubleClicked.emit(document(), 0)
        editor = dock.text_editor
        wait_for(lambda: editor.property("mobaTextEditorContentLoaded"), "SFTP file read")
        downloaded = editor.toPlainText().encode()
        if downloaded != EDITOR_ORIGINAL:
            raise ValueError("the SFTP browser did not return the expected peer file")

        dock.request_remote_monitoring_refresh(allow_prompt=True)
        wait_for(lambda: dock.property("mobaRemoteMonitoringRuntimeState") == "live", "remote monitoring sample")
        monitoring = bytes(dock.monitoring_output_buffer)
        if not monitoring:
            raise ValueError("monitoring did not retain an observed sample")

        authenticated_socket = " ".join(match.groups())
        if native:
            if (endpoint, int(endpoint_port)) != (peer.host, peer.port):
                raise ValueError("the observed native SSH listener differs from the administrator-pinned address")
            expected = sha256(Path(__file__).with_name("transport_terminal_peer.py").read_bytes())
            submit(f"sha256sum -- {PEER_PROGRAM} | cut -d ' ' -f1 | sed 's/^/ROW_PEER_HELPER_SHA256_/'")
            wait_for(lambda: PEER_PROGRAM_SHA.search(pane.output.toPlainText()), "exact peer challenge program")
            if PEER_PROGRAM_SHA.findall(pane.output.toPlainText()) != [expected]:
                raise ValueError("the native peer challenge program differs from the exact release checkout")
            submit(f"{PEER_COMMAND} native")
            if peer_observations(pane.output, wait_for, "native", authenticated_socket) != {"native_linux": True}:
                raise ValueError("the dedicated native peer did not pass host qualification")
        terminal_output = pane.output.toPlainText()
        grid = capture_grid(root, window, pane, wait_for, submit, authenticated_socket)
        vim = capture_vim(root, window, pane, wait_for, submit, authenticated_socket)
        modes = capture_modes(root, app, pane, wait_for, submit, authenticated_socket)
        if connection.state.attempt != 1 or dock.shared_ssh_control_path() != socket:
            raise ValueError("a screen probe replaced the authenticated SSH master")

        with peer.sshd_log.open("rb") as stream:
            observed_log = os.fstat(stream.fileno())
            if (observed_log.st_dev, observed_log.st_ino) != (initial_log.st_dev, initial_log.st_ino):
                raise ValueError("the dedicated SSH log was rotated during the capture")
            stream.seek(initial_log.st_size)
            sshd = stream.read(MAX_CAPTURE_BYTES + 1)
        if len(sshd) > MAX_CAPTURE_BYTES:
            raise ValueError("the dedicated SSH log exceeds the capture size limit")
        client = client_log.read_bytes()
        host_keys = [match[1] for line in client.decode().splitlines() if (match := CLIENT_HOST_KEY.fullmatch(line))]
        if len(host_keys) != 1:
            raise ValueError("the OpenSSH client did not observe one negotiated peer host key")
        host_key = base64.b64decode(host_keys[0] + "=").hex()
        endpoints = {
            "ssh_user": peer.user,
            "client_endpoint": {"address": client_address, "port": int(client_port)},
            "server_endpoint": {"address": endpoint, "port": int(endpoint_port)},
        }
        errors: list[str] = []
        verified = verify_ssh_channels(
            endpoints, {"sshd_log": sshd, "ssh_client_log": client}, host_key, errors,
        )
        verify_connected_captures({
            "transcript": terminal_output.encode(),
            "sftp_capture": downloaded,
            "monitoring_capture": monitoring,
        }, endpoints, errors)
        columns, rows = grid["initial"]
        for section, files in SCREEN_FILES.items():
            verify_screen_captures(
                section, {key: (root / name).read_bytes() for key, name in files.items()},
                {"columns": columns, "rows": rows, "application": vim["application"]}, endpoints, errors,
            )
        if errors:
            raise ValueError(f"SSH channel receipts failed: {errors}")

        submit("exit")
        wait_for(lambda: connection.state.phase == "closed", "remote shell exit")
        pane.request_stop(restart=True)
        wait_for(lambda: connection.state.phase == "connected" and connection.state.attempt == 2, "SSH reconnect")
        state_log = {"events": states.copy(), "connected_views": connected_views}
        verify_connection_states(json.dumps(state_log).encode(), 0, errors)
        if errors:
            raise ValueError(f"SSH state observations failed: {errors}")
        (root / "sshd.log").write_bytes(sshd)
        (root / "ssh-client.log").write_bytes(client)
        (root / "terminal.txt").write_text(terminal_output, encoding="utf-8")
        (root / "sftp.txt").write_bytes(downloaded)
        (root / "monitoring.txt").write_bytes(monitoring)
        write_json(root / "connection-state.json", state_log)
        captures = {file.name: sha256(file.read_bytes()) for file in sorted(root.iterdir())}
        return {
            **endpoints, "host_key_sha256": host_key, "verified_ssh_channel_count": verified,
            "connection_attempts": connection.state.attempt, "produced_capture_count": len(captures),
            "verified_screen_proof_count": len(SCREEN_FILES),
            "captures": captures, "grid": grid, "alternate_screen": vim, "terminal_modes": modes,
            "session_duration_seconds": time.monotonic() - started_at,
            "native_peer_verified": native,
        }
    finally:
        dock.shutdown_runtime()
        pane.stop()
        window.close()
        app.processEvents()


def main() -> int:
    run_capture(capture, __doc__ or "")
    print("Verified shared SSH, grid, Vim and terminal modes on one installed desktop session")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
