"""Qualify the installed desktop's shared SSH channels against a private peer."""

from __future__ import annotations

import base64
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.capture_transport_terminal_probes import (  # noqa: E402
    capture_grid,
    capture_modes,
    capture_vim,
)
from scripts.check_moba_transport_terminal_evidence import (  # noqa: E402
    CLIENT_HOST_KEY,
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


def capture(root: Path, raw: Path, identity: dict) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.models import Profile
    from remote_ops_workspace.storage import ProfileStore
    from remote_ops_workspace.terminal import terminal_plan_for_profile

    profile = Profile(
        name="shared-transport-proof", protocol="ssh", host=HOST, port=PORT, username=EDITOR_USER,
        identity_file=str(FIXTURE / "identity"),
        options={"strict_host_key_checking": "yes", "user_known_hosts_file": str(FIXTURE / "known_hosts")},
    )
    ProfileStore().save([profile])
    app, window = create_main_window(["transport-proof"], show=False)
    window.resize(1500, 960)
    window.show()
    window.set_design_preset("mobaxterm")
    original_plan = terminal_plan_for_profile(profile)
    client_log = raw / "ssh-client.log"
    plan = replace(original_plan, command=[
        original_plan.command[0], "-v", "-E", str(client_log), *original_plan.command[1:],
    ])
    panel = window.open_moba_connected_session_tab(profile, plan, remote_path=f"/home/{EDITOR_USER}")
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
        peer, peer_port, endpoint, endpoint_port = match.groups()
        submit(r"""sha256sum -- document.txt | cut -d ' ' -f1 | sed 's/^/ROW_SFTP_SHA256_/'""")
        wait_for(lambda: TERMINAL_SFTP_SHA.search(pane.output.toPlainText()), "independent remote file digest")
        terminal_output = pane.output.toPlainText()

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
        grid = capture_grid(root, window, pane, wait_for, submit, authenticated_socket)
        vim = capture_vim(root, window, pane, wait_for, submit, authenticated_socket)
        modes = capture_modes(root, app, pane, wait_for, submit, authenticated_socket)
        if connection.state.attempt != 1 or dock.shared_ssh_control_path() != socket:
            raise ValueError("a screen probe replaced the authenticated SSH master")

        sshd = (FIXTURE / "sshd.log").read_bytes()
        client = client_log.read_bytes()
        host_keys = [match[1] for line in client.decode().splitlines() if (match := CLIENT_HOST_KEY.fullmatch(line))]
        if len(host_keys) != 1:
            raise ValueError("the OpenSSH client did not observe one negotiated peer host key")
        host_key = base64.b64decode(host_keys[0] + "=").hex()
        endpoints = {
            "ssh_user": EDITOR_USER,
            "client_endpoint": {"address": peer, "port": int(peer_port)},
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
        write_json(root / "local-qualification.json", {
            **identity, **endpoints, "host_key_sha256": host_key, "verified_ssh_channel_count": verified,
            "connection_attempts": connection.state.attempt, "produced_capture_count": len(captures),
            "verified_screen_proof_count": len(SCREEN_FILES),
            "captures": captures, "grid": grid, "alternate_screen": vim, "terminal_modes": modes,
            "production_acceptance": False,
        })
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
