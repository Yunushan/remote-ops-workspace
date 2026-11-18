"""Native Linux pseudoterminal for an interactive desktop subprocess."""

from __future__ import annotations

import errno
import os
import shutil
import signal
import struct
import subprocess
import threading
import time
from collections.abc import Sequence

_READ_BUDGET = 64 * 1024
_INPUT_LIMIT = 1024 * 1024


class PtyWriteError(OSError):
    operation = "write"


def _set_window_size(fd: int, columns: int, rows: int) -> None:
    import fcntl
    import termios

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))  # type: ignore[attr-defined]


class LinuxPtyProcess:
    def __init__(
        self,
        argv: Sequence[str],
        *,
        columns: int,
        rows: int,
        env: dict[str, str] | None = None,
    ) -> None:
        self._argv = tuple(argv)
        self._columns = columns
        self._rows = rows
        self._environment = dict(os.environ if env is None else env)
        if not self._environment.get("TERM") or self._environment["TERM"] == "dumb":
            self._environment["TERM"] = "xterm-256color"
        self._master: int | None = None
        self.pid: int | None = None
        self._returncode: int | None = None
        self.output_eof = False
        self.output_ready = threading.Event()
        self.io_error: PtyWriteError | None = None
        self._input = bytearray()
        self._input_closed = False

    def start(self) -> None:
        executable = shutil.which(self._argv[0], path=os.pathsep.join(os.get_exec_path(self._environment)))
        if executable is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self._argv[0])
        master, slave = os.openpty()  # type: ignore[attr-defined]
        try:
            os.set_blocking(master, False)  # type: ignore[attr-defined]
            _set_window_size(master, self._columns, self._rows)
            # Open the slave after creating the child's session, so it also
            # becomes the controlling tty. Opening it here or only duping the
            # inherited slave would leave OpenSSH without /dev/tty.
            self.pid = os.posix_spawn(  # type: ignore[attr-defined]
                executable,
                self._argv,
                self._environment,
                file_actions=[
                    (os.POSIX_SPAWN_OPEN, 0, os.ttyname(slave), os.O_RDWR, 0),  # type: ignore[attr-defined]
                    (os.POSIX_SPAWN_DUP2, 0, 1),  # type: ignore[attr-defined]
                    (os.POSIX_SPAWN_DUP2, 0, 2),  # type: ignore[attr-defined]
                ],
                setsid=True,
                setsigmask=(),
                setsigdef=(signal.SIGPIPE,),  # type: ignore[attr-defined]
            )
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self._master = master

    def read_all(self) -> bytes:
        if self._master is None or self.output_eof:
            return b""
        output = bytearray()
        while len(output) < _READ_BUDGET:
            try:
                chunk = os.read(self._master, _READ_BUDGET - len(output))
            except BlockingIOError:
                break
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                # Linux reports EIO on the master after the last slave closes.
                chunk = b""
            if not chunk:
                self.output_eof = True
                break
            output.extend(chunk)
        return bytes(output)

    def write(self, data: bytes) -> int:
        if self._master is None or self._input_closed or self.output_eof:
            raise BrokenPipeError("terminal input is closed")
        if len(self._input) + len(data) > _INPUT_LIMIT:
            raise BlockingIOError("terminal input queue is full")
        self._input.extend(data)
        self._flush_input(self._master)
        return len(data)

    def _flush_input(self, fd: int) -> None:
        try:
            sent = os.write(fd, self._input)
        except BlockingIOError:
            return
        except OSError as exc:
            self._input.clear()
            raise PtyWriteError(str(exc)) from exc
        del self._input[:sent]

    def close_input(self) -> None:
        # A PTY has one bidirectional master. Send the terminal's conventional
        # end-of-input key without closing the descriptor used to drain output.
        if not self._input_closed:
            self.write(b"\x04")
            self._input_closed = True

    def resize(self, columns: int, rows: int) -> None:
        if self._master is not None:
            _set_window_size(self._master, columns, rows)

    def take_resize_error(self) -> None:
        return None

    def begin_output_shutdown(self) -> None:
        """The master stays readable until its slave sends EOF."""

    def poll(self) -> int | None:
        if self.pid is None or self._returncode is not None:
            return self._returncode
        observed, status = os.waitpid(self.pid, os.WNOHANG)  # type: ignore[attr-defined]
        if observed:
            self._returncode = os.waitstatus_to_exitcode(status)
        elif self._master is not None and self._input and not self.output_eof:
            try:
                self._flush_input(self._master)
            except PtyWriteError as exc:
                self.io_error = exc
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        started = time.monotonic()
        while True:
            code = self.poll()
            if code is not None:
                return code
            if timeout is not None and time.monotonic() - started >= timeout:
                raise subprocess.TimeoutExpired(self._argv, timeout)
            time.sleep(0.005)

    def _signal_group(self, signum: int) -> None:
        if self.pid is not None and self.poll() is None:
            try:
                os.killpg(self.pid, signum)  # type: ignore[attr-defined]
            except ProcessLookupError:
                pass

    def terminate(self) -> None:
        self._signal_group(signal.SIGTERM)

    def kill(self) -> None:
        self._signal_group(signal.SIGKILL)  # type: ignore[attr-defined]

    def _reap_after_kill(self, pid: int) -> None:
        _, status = os.waitpid(pid, 0)
        self._returncode = os.waitstatus_to_exitcode(status)

    def close(self, *, terminate: bool = True, timeout: float = 1.0) -> None:
        try:
            if terminate and self.pid is not None and self.poll() is None:
                self.kill()
                try:
                    self.wait(timeout)
                except subprocess.TimeoutExpired:
                    threading.Thread(
                        target=self._reap_after_kill,
                        args=(self.pid,),
                        name="remote-ops-linux-pty-reaper",
                        daemon=True,
                    ).start()
        finally:
            if self._master is not None:
                os.close(self._master)
                self._master = None
            self.output_eof = True
