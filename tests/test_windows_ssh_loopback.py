from __future__ import annotations

import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import (
    openssh_command_without_windows_connection_sharing,
    terminal_plan_for_profile,
)
from remote_ops_workspace.windows_conpty import conpty_support

_REQUIRE_LOOPBACK = os.environ.get("ROW_REQUIRE_WINDOWS_SSH_LOOPBACK") == "1"
_USERNAME = "row-loopback"
_PASSWORD = "row-loopback-password"
_JUMP_USERNAME = "row-jump"
_JUMP_PASSWORD = "row-jump-password"
_COMMAND = "row-loopback-proof"
_RIGHT_PASTE_COMMAND = "row-right-click-paste-proof"
_MIDDLE_PASTE_COMMAND = "row-middle-click-paste-proof"
_ENABLE_BRACKETED_PASTE_COMMAND = "row-enable-bracketed-paste"
_BRACKETED_PASTE_TEXT = "row-bracketed-paste-proof"
_AUTHENTICATED = b"ROW-SSH-AUTHENTICATED"
_READY = b"ROW-SSH-READY>"
_ECHO = b"ROW-SSH-ECHO:row-loopback-proof"
_RIGHT_PASTE_ECHO = b"ROW-SSH-RIGHT-CLICK-PASTE"
_MIDDLE_PASTE_ECHO = b"ROW-SSH-MIDDLE-CLICK-PASTE"
_BRACKETED_PASTE_MODE_READY = b"ROW-SSH-BRACKETED-PASTE-MODE-READY"
_BRACKETED_PASTE_ECHO = b"ROW-SSH-BRACKETED-PASTE"
_BYE = b"ROW-SSH-BYE"
_SOCKET_REGRESSION = b"getsockname failed: not a socket"


def _optional_paramiko() -> Any | None:
    try:
        return importlib.import_module("paramiko")
    except ImportError:
        return None


class _PasswordServer:
    def __init__(
        self,
        paramiko_module: Any,
        *,
        username: str = _USERNAME,
        password: str = _PASSWORD,
        allow_shell: bool = True,
        direct_tcpip_target: tuple[str, int] | None = None,
    ) -> None:
        self._paramiko = paramiko_module
        self._username = username
        self._password = password
        self._allow_shell = allow_shell
        self._direct_tcpip_target = direct_tcpip_target
        self.shell_requested = threading.Event()
        self.authenticated = threading.Event()
        self.direct_tcpip_requested = threading.Event()
        self.direct_tcpip_destination: tuple[str, int] | None = None

    def interface(self) -> Any:
        owner = self
        paramiko_module = self._paramiko

        def check_auth_password(_interface: Any, username: str, password: str) -> int:
            if username == owner._username and password == owner._password:
                owner.authenticated.set()
                return paramiko_module.AUTH_SUCCESSFUL
            return paramiko_module.AUTH_FAILED

        def get_allowed_auths(_interface: Any, _username: str) -> str:
            return "password"

        def check_channel_request(_interface: Any, kind: str, _channel_id: int) -> int:
            if kind == "session" and owner._allow_shell:
                return paramiko_module.OPEN_SUCCEEDED
            return paramiko_module.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_direct_tcpip_request(
            _interface: Any,
            _channel_id: int,
            _origin: tuple[str, int],
            destination: tuple[str, int],
        ) -> int:
            normalized = (str(destination[0]), int(destination[1]))
            if owner._direct_tcpip_target is not None and normalized == owner._direct_tcpip_target:
                owner.direct_tcpip_destination = normalized
                owner.direct_tcpip_requested.set()
                return paramiko_module.OPEN_SUCCEEDED
            return paramiko_module.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_pty_request(
            _interface: Any,
            _channel: Any,
            _term: bytes,
            _width: int,
            _height: int,
            _pixel_width: int,
            _pixel_height: int,
            _modes: bytes,
        ) -> bool:
            return True

        def check_channel_shell_request(_interface: Any, _channel: Any) -> bool:
            if owner._allow_shell:
                owner.shell_requested.set()
                return True
            return False

        interface_type = type(
            "PasswordServerInterface",
            (paramiko_module.ServerInterface,),
            {
                "check_auth_password": check_auth_password,
                "get_allowed_auths": get_allowed_auths,
                "check_channel_request": check_channel_request,
                "check_channel_direct_tcpip_request": (check_channel_direct_tcpip_request),
                "check_channel_pty_request": check_channel_pty_request,
                "check_channel_shell_request": check_channel_shell_request,
            },
        )
        return interface_type()


class _LoopbackSshServer:
    def __init__(self, paramiko_module: Any) -> None:
        self._paramiko = paramiko_module
        self._password_server = _PasswordServer(paramiko_module)
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(15.0)
        self.port = int(self._listener.getsockname()[1])
        self.host_key = self._paramiko.RSAKey.generate(2048)
        self.received_commands: list[str] = []
        self.received_bracketed_pastes: list[str] = []
        self.failure: BaseException | None = None
        self._transport: Any | None = None
        self._channel: Any | None = None
        self._thread = threading.Thread(
            target=self._serve,
            name="row-windows-ssh-loopback",
            daemon=True,
        )

    @property
    def authenticated(self) -> bool:
        return self._password_server.authenticated.is_set()

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        connection: socket.socket | None = None
        try:
            connection, _address = self._listener.accept()
            connection.settimeout(15.0)
            transport = self._paramiko.Transport(connection)
            self._transport = transport
            transport.add_server_key(self.host_key)
            transport.start_server(server=self._password_server.interface())
            channel = transport.accept(timeout=15.0)
            if channel is None:
                raise TimeoutError("native OpenSSH did not open a session channel")
            self._channel = channel
            channel.settimeout(15.0)
            if not self._password_server.shell_requested.wait(timeout=15.0):
                raise TimeoutError("native OpenSSH did not request an interactive shell")
            channel.sendall(_AUTHENTICATED + b"\r\n" + _READY + b" ")

            pending = bytearray()
            while transport.is_active() and not channel.closed:
                payload = channel.recv(4096)
                if not payload:
                    break
                pending.extend(payload)
                # Bracketed paste is an out-of-band terminal input envelope,
                # not a command line.  Record and consume complete envelopes
                # before parsing CR/LF-delimited shell commands so this native
                # loopback gate can prove the exact bytes produced by the GUI.
                while True:
                    start_marker = b"\x1b[200~"
                    end_marker = b"\x1b[201~"
                    start = pending.find(start_marker)
                    if start < 0:
                        break
                    end = pending.find(end_marker, start + len(start_marker))
                    if end < 0:
                        break
                    pasted = bytes(pending[start + len(start_marker) : end])
                    del pending[start : end + len(end_marker)]
                    self.received_bracketed_pastes.append(
                        pasted.decode("utf-8", errors="replace")
                    )
                    channel.sendall(_BRACKETED_PASTE_ECHO + b"\r\n" + _READY + b" ")
                while True:
                    cr = pending.find(b"\r")
                    lf = pending.find(b"\n")
                    boundaries = [index for index in (cr, lf) if index >= 0]
                    if not boundaries:
                        break
                    boundary = min(boundaries)
                    command = bytes(pending[:boundary]).decode("utf-8", errors="replace")
                    del pending[: boundary + 1]
                    while bytes(pending[:1]) in {b"\r", b"\n"}:
                        del pending[:1]
                    command = command.strip()
                    if not command:
                        continue
                    self.received_commands.append(command)
                    if command == _COMMAND:
                        channel.sendall(_ECHO + b"\r\n" + _READY + b" ")
                    elif command == _RIGHT_PASTE_COMMAND:
                        channel.sendall(_RIGHT_PASTE_ECHO + b"\r\n" + _READY + b" ")
                    elif command == _MIDDLE_PASTE_COMMAND:
                        channel.sendall(_MIDDLE_PASTE_ECHO + b"\r\n" + _READY + b" ")
                    elif command == _ENABLE_BRACKETED_PASTE_COMMAND:
                        # Negotiate the mode through the actual remote-output
                        # channel, as readline/Vim do.  The GUI test must not
                        # mutate its emulator directly and call that transport
                        # evidence.
                        channel.sendall(
                            b"\x1b[?2004h"
                            + _BRACKETED_PASTE_MODE_READY
                            + b"\r\n"
                            + _READY
                            + b" "
                        )
                    elif command == "exit":
                        channel.sendall(_BYE + b"\r\n")
                        channel.send_exit_status(0)
                        return
                    else:
                        channel.sendall(b"ROW-SSH-UNEXPECTED:" + command.encode() + b"\r\n")
        except BaseException as exc:  # pragma: no cover - surfaced by the test
            self.failure = exc
        finally:
            if self._channel is not None:
                with suppress(Exception):
                    self._channel.close()
            if self._transport is not None:
                with suppress(Exception):
                    self._transport.close()
            if connection is not None:
                with suppress(OSError):
                    connection.close()
            with suppress(OSError):
                self._listener.close()

    def close(self) -> None:
        if self._channel is not None:
            with suppress(Exception):
                self._channel.close()
        if self._transport is not None:
            with suppress(Exception):
                self._transport.close()
        with suppress(OSError):
            self._listener.close()
        self._thread.join(timeout=5.0)

    def write_known_hosts(
        self,
        destination: Path,
        *,
        host_token: str | None = None,
        append: bool = False,
    ) -> None:
        """Pin this ephemeral server key using OpenSSH's non-default-port form."""

        token = host_token or f"[127.0.0.1]:{self.port}"
        mode = "a" if append else "w"
        with destination.open(mode, encoding="ascii", newline="\n") as stream:
            stream.write(f"{token} {self.host_key.get_name()} {self.host_key.get_base64()}\n")


class _LoopbackJumpSshServer:
    """One-hop SSH server that forwards exactly one direct-tcpip destination."""

    def __init__(
        self,
        paramiko_module: Any,
        *,
        target_host: str,
        target_port: int,
    ) -> None:
        self._paramiko = paramiko_module
        self._target = (target_host, target_port)
        self._password_server = _PasswordServer(
            paramiko_module,
            username=_JUMP_USERNAME,
            password=_JUMP_PASSWORD,
            allow_shell=False,
            direct_tcpip_target=self._target,
        )
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(15.0)
        self.port = int(self._listener.getsockname()[1])
        self.host_key = self._paramiko.RSAKey.generate(2048)
        self.failure: BaseException | None = None
        self.forwarded_to_target = 0
        self.forwarded_from_target = 0
        self._transport: Any | None = None
        self._channel: Any | None = None
        self._connection: socket.socket | None = None
        self._outbound: socket.socket | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._serve,
            name="row-windows-ssh-jump-loopback",
            daemon=True,
        )

    @property
    def authenticated(self) -> bool:
        return self._password_server.authenticated.is_set()

    @property
    def direct_tcpip_destination(self) -> tuple[str, int] | None:
        return self._password_server.direct_tcpip_destination

    def start(self) -> None:
        self._thread.start()

    def _pump_channel_to_target(self) -> None:
        assert self._channel is not None
        assert self._outbound is not None
        try:
            while not self._stop.is_set():
                try:
                    payload = self._channel.recv(65536)
                except TimeoutError:
                    continue
                if not payload:
                    break
                self._outbound.sendall(payload)
                self.forwarded_to_target += len(payload)
        except (EOFError, OSError):
            pass
        finally:
            self._stop.set()

    def _pump_target_to_channel(self) -> None:
        assert self._channel is not None
        assert self._outbound is not None
        try:
            while not self._stop.is_set():
                try:
                    payload = self._outbound.recv(65536)
                except TimeoutError:
                    continue
                if not payload:
                    break
                self._channel.sendall(payload)
                self.forwarded_from_target += len(payload)
        except (EOFError, OSError):
            pass
        finally:
            self._stop.set()

    def _serve(self) -> None:
        workers: list[threading.Thread] = []
        try:
            connection, _address = self._listener.accept()
            self._connection = connection
            connection.settimeout(15.0)
            transport = self._paramiko.Transport(connection)
            self._transport = transport
            transport.add_server_key(self.host_key)
            transport.start_server(server=self._password_server.interface())
            channel = transport.accept(timeout=15.0)
            if channel is None:
                raise TimeoutError("native OpenSSH did not open a jump channel")
            self._channel = channel
            channel.settimeout(0.25)
            if not self._password_server.direct_tcpip_requested.wait(timeout=15.0):
                raise TimeoutError("native OpenSSH did not request direct-tcpip forwarding")
            destination = self._password_server.direct_tcpip_destination
            if destination != self._target:
                raise RuntimeError(f"jump requested unexpected destination {destination!r}")
            outbound = socket.create_connection(self._target, timeout=15.0)
            self._outbound = outbound
            outbound.settimeout(0.25)
            workers = [
                threading.Thread(
                    target=self._pump_channel_to_target,
                    name="row-jump-to-target",
                    daemon=True,
                ),
                threading.Thread(
                    target=self._pump_target_to_channel,
                    name="row-target-to-jump",
                    daemon=True,
                ),
            ]
            for worker in workers:
                worker.start()
            while transport.is_active() and not self._stop.wait(0.05):
                pass
        except BaseException as exc:  # pragma: no cover - surfaced by the test
            self.failure = exc
        finally:
            self._stop.set()
            if self._outbound is not None:
                with suppress(OSError):
                    self._outbound.shutdown(socket.SHUT_RDWR)
            for worker in workers:
                worker.join(timeout=2.0)
            if self._channel is not None:
                with suppress(Exception):
                    self._channel.close()
            if self._transport is not None:
                with suppress(Exception):
                    self._transport.close()
            if self._outbound is not None:
                with suppress(OSError):
                    self._outbound.close()
            if self._connection is not None:
                with suppress(OSError):
                    self._connection.close()
            with suppress(OSError):
                self._listener.close()

    def close(self) -> None:
        self._stop.set()
        if self._outbound is not None:
            with suppress(OSError):
                self._outbound.shutdown(socket.SHUT_RDWR)
        if self._channel is not None:
            with suppress(Exception):
                self._channel.close()
        if self._transport is not None:
            with suppress(Exception):
                self._transport.close()
        with suppress(OSError):
            self._listener.close()
        self._thread.join(timeout=5.0)

    def write_known_hosts(
        self,
        destination: Path,
        *,
        host_token: str,
        append: bool = False,
    ) -> None:
        mode = "a" if append else "w"
        with destination.open(mode, encoding="ascii", newline="\n") as stream:
            stream.write(f"{host_token} {self.host_key.get_name()} {self.host_key.get_base64()}\n")


def _process_events_until(
    app: Any,
    predicate: Any,
    *,
    timeout: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "condition was not reached while processing Qt events"


def _write_ci_evidence(
    *,
    ssh: str,
    windows_build: int | None,
    output: bytes,
) -> None:
    evidence_dir = os.environ.get("ROW_WINDOWS_SSH_EVIDENCE_DIR", "").strip()
    if not evidence_dir:
        return
    version_probe = subprocess.run(
        [ssh, "-V"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    ssh_version = (version_probe.stderr or version_probe.stdout).strip()
    payload = {
        "schema_version": 1,
        "platform": "windows-native",
        "windows_build": windows_build,
        "client": {
            "path": ssh,
            "version": ssh_version,
        },
        "transport": "native OpenSSH over QtConPtyProcess/WindowsConPtyProcess",
        "server": "ephemeral in-process SSHv2 server bound to 127.0.0.1",
        "proofs": {
            "strict_host_key_verification": True,
            "interactive_password_prompt_observed": b"password:" in output.lower(),
            "authentication_accepted": _AUTHENTICATED in output,
            "terminal_input_round_trip": _ECHO in output,
            "remote_output_observed": _READY in output and _BYE in output,
            "clean_exit": True,
            "getsockname_failed_not_a_socket_absent": (_SOCKET_REGRESSION not in output.lower()),
        },
    }
    destination = Path(evidence_dir) / "evidence.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_gui_ci_evidence(
    *,
    ssh: str,
    windows_build: int | None,
    command: list[str],
    transcript: str,
) -> None:
    evidence_dir = os.environ.get("ROW_WINDOWS_SSH_EVIDENCE_DIR", "").strip()
    if not evidence_dir:
        return
    payload = {
        "schema_version": 1,
        "platform": "windows-native",
        "windows_build": windows_build,
        "client_path": ssh,
        "production_path": (
            "Profile -> terminal_plan_for_profile -> MainWindow.open_terminal_tab -> "
            "TerminalPane -> Qt keyboard/mouse/clipboard events -> "
            "QtConPtyProcess/WindowsConPtyProcess"
        ),
        "runtime_command": command,
        "proofs": {
            "profile_launch_plan_used": True,
            "real_gui_terminal_pane_used": True,
            "native_windows_conpty_used": True,
            "strict_host_key_verification": True,
            "password_entered_through_qt_key_events": True,
            "password_not_rendered_in_transcript": _PASSWORD not in transcript,
            "authentication_accepted": _AUTHENTICATED.decode() in transcript,
            "terminal_input_round_trip": _ECHO.decode() in transcript,
            "right_click_mouse_paste_round_trip": (
                _RIGHT_PASTE_ECHO.decode() in transcript
            ),
            "right_click_dispatched_by_qt": True,
            "middle_click_mouse_paste_round_trip": (
                _MIDDLE_PASTE_ECHO.decode() in transcript
            ),
            "remote_bracketed_paste_negotiation_observed": (
                _BRACKETED_PASTE_MODE_READY.decode() in transcript
            ),
            "bracketed_paste_round_trip": (
                _BRACKETED_PASTE_ECHO.decode() in transcript
            ),
            "remote_output_observed": (
                _READY.decode() in transcript and _BYE.decode() in transcript
            ),
            "getsockname_failed_not_a_socket_absent": (
                _SOCKET_REGRESSION.decode() not in transcript.lower()
            ),
        },
    }
    destination = Path(evidence_dir) / "terminal-pane-evidence.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_proxy_jump_ci_evidence(
    *,
    ssh: str,
    windows_build: int | None,
    command: list[str],
    output: bytes,
    jump: _LoopbackJumpSshServer,
    target: _LoopbackSshServer,
) -> None:
    evidence_dir = os.environ.get("ROW_WINDOWS_SSH_EVIDENCE_DIR", "").strip()
    if not evidence_dir:
        return
    proxy_command = next(argument for argument in command if argument.startswith("ProxyCommand="))
    payload = {
        "schema_version": 1,
        "platform": "windows-native",
        "windows_build": windows_build,
        "client_path": ssh,
        "transport": (
            "native Windows OpenSSH parent -> hardened standalone ProxyCommand "
            "child -> Paramiko direct-tcpip jump -> separate Paramiko target"
        ),
        "runtime_command": command,
        "jump_destination": list(jump.direct_tcpip_destination or ()),
        "forwarded_bytes": {
            "to_target": jump.forwarded_to_target,
            "from_target": jump.forwarded_from_target,
        },
        "proofs": {
            "hardened_proxy_command_rewrite_used": True,
            "proxy_child_connection_sharing_disabled": all(
                marker in proxy_command
                for marker in (
                    "ControlMaster=no",
                    "ControlPersist=no",
                    "ControlPath=none",
                    "ProxyCommand=none",
                    "ProxyJump=none",
                )
            ),
            "strict_jump_host_key_pinned": True,
            "strict_target_host_key_pinned": True,
            "two_password_prompts_observed": output.lower().count(b"password:") >= 2,
            "jump_authentication_accepted": jump.authenticated,
            "target_authentication_accepted": target.authenticated,
            "direct_tcpip_reached_separate_target": (
                jump.direct_tcpip_destination == ("127.0.0.1", target.port)
            ),
            "bidirectional_forwarding_observed": (
                jump.forwarded_to_target > 0 and jump.forwarded_from_target > 0
            ),
            "terminal_input_round_trip": _ECHO in output,
            "remote_output_observed": _READY in output and _BYE in output,
            "passwords_not_rendered": (
                _PASSWORD.encode() not in output and _JUMP_PASSWORD.encode() not in output
            ),
            "clean_exit": True,
            "getsockname_failed_not_a_socket_absent": (_SOCKET_REGRESSION not in output.lower()),
        },
    }
    destination = Path(evidence_dir) / "proxy-jump-evidence.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows SSH/ConPTY gate")
def test_native_windows_ssh_auth_input_output_over_qt_conpty(tmp_path: Path) -> None:
    """Prove the production SSH transport against a secret-free loopback server."""

    paramiko_module = _optional_paramiko()
    if paramiko_module is None:
        if _REQUIRE_LOOPBACK:
            pytest.fail("required Paramiko loopback SSH server dependency is unavailable")
        pytest.skip("Paramiko loopback SSH server dependency is unavailable")

    support = conpty_support()
    assert support.supported, support.reason
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")
    assert ssh is not None, "native Windows OpenSSH client is unavailable"

    qt_core = importlib.import_module("PyQt6.QtCore")
    qt_widgets = importlib.import_module("PyQt6.QtWidgets")
    qt_terminal_process = importlib.import_module("remote_ops_workspace.qt_terminal_process")
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication(
        ["remote-ops-workspace-windows-ssh-loopback"]
    )
    server = _LoopbackSshServer(paramiko_module)
    known_hosts = tmp_path / "known_hosts"
    server.write_known_hosts(known_hosts)
    server.start()
    command = openssh_command_without_windows_connection_sharing(
        [
            ssh,
            "-o",
            "BatchMode=no",
            "-o",
            "PreferredAuthentications=password",
            "-o",
            "PasswordAuthentication=yes",
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "NumberOfPasswordPrompts=1",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts.as_posix()}",
            "-o",
            "GlobalKnownHostsFile=NUL",
            "-o",
            "LogLevel=ERROR",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(server.port),
            "-tt",
            f"{_USERNAME}@127.0.0.1",
        ]
    )
    assert command[1:3] == ["-S", "none"]
    assert "ControlMaster=no" in command
    assert "ControlPersist=no" in command

    process = qt_terminal_process.QtConPtyProcess()
    output = bytearray()
    errors: list[Any] = []
    finished: list[tuple[int, Any]] = []
    process.readyReadStandardOutput.connect(lambda: output.extend(process.readAllStandardOutput()))
    process.errorOccurred.connect(errors.append)
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProgram(command[0])
    process.setArguments(command[1:])

    try:
        process.start()
        try:
            _process_events_until(app, lambda: b"password:" in output.lower())
        except AssertionError:
            pytest.fail(
                "loopback password prompt was not observed; "
                f"output={bytes(output)!r}; errors={errors!r}; "
                f"server_failure={server.failure!r}"
            )
        assert _SOCKET_REGRESSION not in output.lower()

        assert process.write((_PASSWORD + "\r").encode()) > 0
        session = process._session
        assert session is not None
        session.flush(timeout=3.0)
        _process_events_until(app, lambda: _AUTHENTICATED in output)
        _process_events_until(app, lambda: _READY in output)
        assert server.authenticated
        assert _SOCKET_REGRESSION not in output.lower()

        assert process.write((_COMMAND + "\r").encode()) > 0
        session.flush(timeout=3.0)
        try:
            _process_events_until(app, lambda: _ECHO in output)
        except AssertionError:
            pytest.fail(
                "loopback command did not round-trip; "
                f"output={bytes(output)!r}; commands={server.received_commands!r}; "
                f"server_failure={server.failure!r}"
            )
        assert _COMMAND in server.received_commands

        assert process.write(b"exit\r") > 0
        session.flush(timeout=3.0)
        _process_events_until(app, lambda: _BYE in output)
        _process_events_until(app, lambda: bool(finished))

        assert errors == []
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
        assert "exit" in server.received_commands
        assert _SOCKET_REGRESSION not in output.lower()
        assert server.failure is None
        _write_ci_evidence(
            ssh=ssh,
            windows_build=support.windows_build,
            output=bytes(output),
        )
    finally:
        process.close()
        server.close()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows SSH/ConPTY gate")
def test_native_windows_proxy_jump_two_hop_auth_input_output_over_qt_conpty(
    tmp_path: Path,
) -> None:
    """Traverse a pinned jump host and authenticate to a separate target."""

    paramiko_module = _optional_paramiko()
    if paramiko_module is None:
        if _REQUIRE_LOOPBACK:
            pytest.fail("required Paramiko loopback SSH server dependency is unavailable")
        pytest.skip("Paramiko loopback SSH server dependency is unavailable")

    support = conpty_support()
    assert support.supported, support.reason
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")
    assert ssh is not None, "native Windows OpenSSH client is unavailable"

    qt_core = importlib.import_module("PyQt6.QtCore")
    qt_widgets = importlib.import_module("PyQt6.QtWidgets")
    qt_terminal_process = importlib.import_module("remote_ops_workspace.qt_terminal_process")
    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication(
        ["remote-ops-workspace-windows-ssh-proxy-jump-loopback"]
    )
    target = _LoopbackSshServer(paramiko_module)
    jump = _LoopbackJumpSshServer(
        paramiko_module,
        target_host="127.0.0.1",
        target_port=target.port,
    )
    known_hosts = tmp_path / "proxy-jump-known-hosts"
    target.write_known_hosts(known_hosts, host_token="row-loopback-target")
    jump.write_known_hosts(
        known_hosts,
        host_token="row-loopback-jump",
        append=True,
    )
    config = tmp_path / "proxy-jump-config"
    config.write_text(
        "Host row-loopback-jump\n"
        "    HostName 127.0.0.1\n"
        f"    Port {jump.port}\n"
        f"    User {_JUMP_USERNAME}\n"
        "    HostKeyAlias row-loopback-jump\n"
        "Host row-loopback-target\n"
        "    HostName 127.0.0.1\n"
        f"    Port {target.port}\n"
        f"    User {_USERNAME}\n"
        "    HostKeyAlias row-loopback-target\n"
        "Host *\n"
        "    BatchMode no\n"
        "    PreferredAuthentications password\n"
        "    PasswordAuthentication yes\n"
        "    PubkeyAuthentication no\n"
        "    KbdInteractiveAuthentication no\n"
        "    NumberOfPasswordPrompts 1\n"
        "    StrictHostKeyChecking yes\n"
        f"    UserKnownHostsFile {known_hosts.as_posix()}\n"
        "    GlobalKnownHostsFile NUL\n"
        "    LogLevel ERROR\n"
        "    ConnectTimeout 10\n",
        encoding="ascii",
    )
    original = [
        ssh,
        "-F",
        str(config),
        "-J",
        "row-loopback-jump",
        "-tt",
        "row-loopback-target",
    ]
    command = openssh_command_without_windows_connection_sharing(original)
    proxy_command = next(argument for argument in command if argument.startswith("ProxyCommand="))
    assert "-J" not in command
    assert not any(argument.startswith("-J") for argument in command)
    assert command[1:3] == ["-S", "none"]
    assert "ControlMaster=no" in command
    assert "ControlPersist=no" in command
    assert "ControlMaster=no" in proxy_command
    assert "ControlPersist=no" in proxy_command
    assert "ControlPath=none" in proxy_command
    assert "ProxyCommand=none" in proxy_command
    assert "ProxyJump=none" in proxy_command
    assert "-W" in proxy_command
    assert "row-loopback-jump" in proxy_command

    target.start()
    jump.start()
    process = qt_terminal_process.QtConPtyProcess()
    output = bytearray()
    errors: list[Any] = []
    finished: list[tuple[int, Any]] = []
    process.readyReadStandardOutput.connect(lambda: output.extend(process.readAllStandardOutput()))
    process.errorOccurred.connect(errors.append)
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProgram(command[0])
    process.setArguments(command[1:])

    try:
        process.start()
        try:
            _process_events_until(app, lambda: b"password:" in output.lower())
        except AssertionError:
            pytest.fail(
                "jump-host password prompt was not observed; "
                f"output={bytes(output)!r}; errors={errors!r}; "
                f"jump_failure={jump.failure!r}"
            )
        assert process.write((_JUMP_PASSWORD + "\r").encode()) > 0
        session = process._session
        assert session is not None
        session.flush(timeout=3.0)
        _process_events_until(app, lambda: jump.authenticated)

        try:
            _process_events_until(
                app,
                lambda: output.lower().count(b"password:") >= 2,
            )
        except AssertionError:
            pytest.fail(
                "target password prompt was not observed through the jump; "
                f"output={bytes(output)!r}; errors={errors!r}; "
                f"jump_failure={jump.failure!r}; target_failure={target.failure!r}"
            )
        assert process.write((_PASSWORD + "\r").encode()) > 0
        session.flush(timeout=3.0)
        _process_events_until(app, lambda: target.authenticated)
        _process_events_until(app, lambda: _AUTHENTICATED in output)
        _process_events_until(app, lambda: _READY in output)
        assert jump.direct_tcpip_destination == ("127.0.0.1", target.port)
        assert _SOCKET_REGRESSION not in output.lower()

        assert process.write((_COMMAND + "\r").encode()) > 0
        session.flush(timeout=3.0)
        try:
            _process_events_until(app, lambda: _ECHO in output)
        except AssertionError:
            pytest.fail(
                "target command did not round-trip through the jump; "
                f"output={bytes(output)!r}; commands={target.received_commands!r}; "
                f"jump_failure={jump.failure!r}; target_failure={target.failure!r}"
            )
        assert _COMMAND in target.received_commands
        assert jump.forwarded_to_target > 0
        assert jump.forwarded_from_target > 0

        assert process.write(b"exit\r") > 0
        session.flush(timeout=3.0)
        _process_events_until(app, lambda: _BYE in output)
        _process_events_until(app, lambda: bool(finished))

        assert errors == []
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
        assert "exit" in target.received_commands
        assert _JUMP_PASSWORD.encode() not in output
        assert _PASSWORD.encode() not in output
        assert _SOCKET_REGRESSION not in output.lower()
        assert jump.failure is None
        assert target.failure is None
        _write_proxy_jump_ci_evidence(
            ssh=ssh,
            windows_build=support.windows_build,
            command=command,
            output=bytes(output),
            jump=jump,
            target=target,
        )
    finally:
        process.close()
        jump.close()
        target.close()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows SSH/ConPTY gate")
def test_native_windows_ssh_profile_gui_keyboard_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Prove the complete profile-to-GUI input path used by the desktop app."""

    paramiko_module = _optional_paramiko()
    if paramiko_module is None:
        if _REQUIRE_LOOPBACK:
            pytest.fail("required Paramiko loopback SSH server dependency is unavailable")
        pytest.skip("Paramiko loopback SSH server dependency is unavailable")

    support = conpty_support()
    assert support.supported, support.reason
    ssh = shutil.which("ssh.exe") or shutil.which("ssh")
    assert ssh is not None, "native Windows OpenSSH client is unavailable"

    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    server = _LoopbackSshServer(paramiko_module)
    known_hosts = tmp_path / "known_hosts"
    server.write_known_hosts(known_hosts)
    profile = Profile(
        name="native-windows-loopback",
        protocol="ssh",
        host="127.0.0.1",
        port=server.port,
        username=_USERNAME,
        options={
            "connect_timeout": "10",
            "strict_host_key_checking": "yes",
            "user_known_hosts_file": known_hosts.as_posix(),
            "log_level": "error",
        },
    )
    plan = terminal_plan_for_profile(profile)
    control_path_index = plan.command.index("-S")
    assert plan.command[control_path_index + 1] == "none"
    assert "-tt" in plan.command
    assert "ControlMaster=no" in plan.command
    assert "ControlPersist=no" in plan.command

    gui = importlib.import_module("remote_ops_workspace.gui")
    qt_core = importlib.import_module("PyQt6.QtCore")
    qt_gui = importlib.import_module("PyQt6.QtGui")
    qt_test = importlib.import_module("PyQt6.QtTest")
    app, window = gui.create_main_window(
        ["remote-ops-workspace-windows-ssh-gui-loopback"],
        show=True,
    )
    pane: Any | None = None
    try:
        window.set_design_preset("mobaxterm")
        # Start the bounded listener only after the first PyQt import and window
        # construction. On a cold Python 3.15 runner those operations can take
        # longer than the listener's accept timeout even though OpenSSH itself
        # connects immediately once the terminal pane launches.
        server.start()
        window.open_terminal_tab(plan, profile=profile)
        _process_events_until(
            app,
            lambda: (
                bool(window.all_terminal_panes()) and window.all_terminal_panes()[-1].is_running()
            ),
        )
        pane = window.all_terminal_panes()[-1]
        assert bool(getattr(pane.process, "is_pty", False))
        assert pane.output.property("terminalProcessBackend") == "windows-conpty"
        assert pane.focusProxy() is pane.output

        _process_events_until(
            app,
            lambda: "password:" in pane.output.toPlainText().lower(),
        )
        pane.output.setFocus(qt_core.Qt.FocusReason.OtherFocusReason)
        qt_test.QTest.keyClicks(pane.output, _PASSWORD)
        qt_test.QTest.keyClick(pane.output, qt_core.Qt.Key.Key_Return)
        _process_events_until(
            app,
            lambda: _AUTHENTICATED.decode() in pane.output.toPlainText(),
        )
        _process_events_until(
            app,
            lambda: _READY.decode() in pane.output.toPlainText(),
        )
        assert server.authenticated
        assert _PASSWORD not in pane.output.toPlainText()

        qt_test.QTest.keyClicks(pane.output, _COMMAND)
        qt_test.QTest.keyClick(pane.output, qt_core.Qt.Key.Key_Return)
        _process_events_until(
            app,
            lambda: _ECHO.decode() in pane.output.toPlainText(),
        )
        assert _COMMAND in server.received_commands

        class _DeterministicClipboard:
            def __init__(self) -> None:
                self.value = ""

            def setText(self, value: str) -> None:  # noqa: N802
                self.value = value

            def text(self, _mode=None) -> str:
                return self.value

            def supportsSelection(self) -> bool:  # noqa: N802
                return False

        clipboard = _DeterministicClipboard()
        pane._terminal_clipboard_provider = lambda: clipboard
        assert pane.output.property("terminalRightClickPasteEnabled") is True
        assert pane.output.property("terminalMiddleClickPasteEnabled") is True

        clipboard.setText(_RIGHT_PASTE_COMMAND + "\r")
        right_click = qt_gui.QContextMenuEvent(
            qt_gui.QContextMenuEvent.Reason.Mouse,
            pane.output_viewport.rect().center(),
            pane.output_viewport.mapToGlobal(pane.output_viewport.rect().center()),
        )
        assert app.sendEvent(pane.output_viewport, right_click) is True
        assert right_click.isAccepted()
        _process_events_until(
            app,
            lambda: _RIGHT_PASTE_ECHO.decode() in pane.output.toPlainText(),
        )
        assert _RIGHT_PASTE_COMMAND in server.received_commands
        assert pane.output.property("terminalLastPasteGesture") == "right-click"

        clipboard.setText(_MIDDLE_PASTE_COMMAND + "\r")
        qt_test.QTest.mouseClick(
            pane.output_viewport,
            qt_core.Qt.MouseButton.MiddleButton,
        )
        _process_events_until(
            app,
            lambda: _MIDDLE_PASTE_ECHO.decode() in pane.output.toPlainText(),
        )
        assert _MIDDLE_PASTE_COMMAND in server.received_commands
        assert pane.output.property("terminalLastPasteGesture") == "middle-click"

        # Ask the remote shell to negotiate bracketed paste as Vim/readline do,
        # then prove the exact envelope crosses the real Qt -> ConPTY ->
        # OpenSSH -> SSH server path.  No emulator state is injected locally.
        qt_test.QTest.keyClicks(pane.output, _ENABLE_BRACKETED_PASTE_COMMAND)
        qt_test.QTest.keyClick(pane.output, qt_core.Qt.Key.Key_Return)
        _process_events_until(
            app,
            lambda: (
                _BRACKETED_PASTE_MODE_READY.decode() in pane.output.toPlainText()
                and pane.terminal_emulator.bracketed_paste_active
            ),
        )
        assert _ENABLE_BRACKETED_PASTE_COMMAND in server.received_commands
        clipboard.setText(_BRACKETED_PASTE_TEXT)
        qt_test.QTest.mouseClick(
            pane.output_viewport,
            qt_core.Qt.MouseButton.MiddleButton,
        )
        _process_events_until(
            app,
            lambda: _BRACKETED_PASTE_TEXT in server.received_bracketed_pastes,
        )
        _process_events_until(
            app,
            lambda: _BRACKETED_PASTE_ECHO.decode() in pane.output.toPlainText(),
        )
        assert pane.output.property("terminalLastPasteWasBracketed") is True

        qt_test.QTest.keyClicks(pane.output, "exit")
        qt_test.QTest.keyClick(pane.output, qt_core.Qt.Key.Key_Return)
        _process_events_until(
            app,
            lambda: _BYE.decode() in pane.output.toPlainText(),
        )
        _process_events_until(app, lambda: not pane.is_running())

        transcript = pane.output.toPlainText()
        assert pane.status.text() == "exited 0"
        assert _SOCKET_REGRESSION.decode() not in transcript.lower()
        assert server.failure is None
        _write_gui_ci_evidence(
            ssh=ssh,
            windows_build=support.windows_build,
            command=plan.command,
            transcript=transcript,
        )
    finally:
        if pane is not None and pane.is_running():
            pane.prepare_for_close()
            pane.process.kill()
            _process_events_until(app, lambda: not pane.is_running(), timeout=5.0)
        window.close()
        app.processEvents()
        server.close()
