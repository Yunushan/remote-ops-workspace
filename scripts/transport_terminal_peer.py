"""Emit fixed terminal challenges from the existing SSH shell's PTY."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import termios
import tty
from pathlib import Path
from tempfile import TemporaryDirectory

VIM_CONFIG = r"""
set nocompatible noswapfile noerrorbells showmode laststatus=0
let &t_ti = "\<Esc>[?1049h\<Esc>[2 q"
let &t_te = "\<Esc>[?1049l"
let &t_SI = "\<Esc>[6 q"
let &t_EI = "\<Esc>[2 q"
"""


def send(data: bytes) -> None:
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def receive(expected: bytes) -> str:
    observed = bytearray()
    while len(observed) < len(expected):
        chunk = os.read(0, len(expected) - len(observed))
        if not chunk:
            raise EOFError("the terminal disconnected during the challenge")
        observed.extend(chunk)
    if observed != expected:
        raise ValueError(f"terminal sent {observed.hex()}, expected {expected.hex()}")
    return observed.hex()


def grid() -> dict:
    initial = os.get_terminal_size(0)
    if initial.columns < 80 or initial.lines < 24:
        raise ValueError(f"initial terminal size is too small: {initial}")
    prefix = "ROW_GRID_" + "a" * (initial.columns - 1 - len("ROW_GRID_"))
    send(("\x1b[2J\x1b[H" + prefix + "\x1b[31m界\u0301z\x1b[0m\x1b[6n").encode())
    cursor = receive(b"\x1b[2;4R")
    receive(b"r")
    resized = os.get_terminal_size(0)
    if resized.columns <= initial.columns or resized.lines != initial.lines:
        raise ValueError(f"the remote PTY did not receive the wider viewport: {resized}")
    send(b"\x1b[?1049h\x1b[1;1Houtside-top\x1b[2;1Htwo\x1b[3;1Hthree"
         b"\x1b[4;1Hfour\x1b[5;1Houtside-bottom\x1b[2;4r\x1b[4;1H\x1bD")
    receive(b"g")
    send(b"\x1b[3;1H\x1b[32mfour\x1b[0m")
    receive(b"q")
    send(b"\x1b[?1049l")
    return {"initial": list(initial), "resized": list(resized), "cursor_reply": cursor}


def vim() -> dict:
    executable = shutil.which("vim.basic") or shutil.which("vim")
    if executable is None:
        raise ValueError("the SSH peer requires a full Vim build")
    send("\x1b[2J\x1b[HROW_PRIMARY_界_e\u0301\x1b[4 q".encode())
    receive(b"v")
    with TemporaryDirectory(prefix="row-transport-vim-") as scratch:
        config = Path(scratch) / "vimrc"
        config.write_text(VIM_CONFIG, encoding="utf-8")
        subprocess.run([executable, "-Nu", str(config), "-n", "-i", "NONE", "--", "document.txt"],
                       env={**os.environ, "TERM": "xterm-256color"}, check=True, timeout=60)
    tty.setraw(0)
    return {"shell_input": receive(b"b")}


def modes() -> dict:
    send(b"\x1b[?1049h\x1b[1;1H\x1b[1;4;31mANSI16\x1b[0m"
         b"\x1b[2;1H\x1b[38;5;196mANSI256\x1b[0m"
         b"\x1b[3;1H\x1b[38;2;12;34;56mTRUECOLOR\x1b[0m"
         b"\x1b[7;4H\x1b[6n\x1b[6 q\x1bP$q q\x1b\\\x1b[?25l"
         b"\x1b[?1;2004;1000;1006h\x1b[8;1HROW_MODES_READY")
    seen = {
        "cursor_position": receive(b"\x1b[7;4R"),
        "cursor_shape_report": receive(b"\x1bP1$r6 q\x1b\\"),
        "application_up": receive(b"\x1bOA"),
        "bracketed_paste": receive(b"\x1b[200~paste-from-desktop\x1b[201~"),
        "mouse_press_release_wheel": receive(b"\x1b[<0;1;1M\x1b[<0;1;1m\x1b[<64;1;1M"),
    }
    send(b"\x1b[?1000;1006;2004;1l\x1b[?25h\x1b[9;1HROW_MOUSE_OFF")
    seen["unwrapped_input_after_mouse_off"] = receive(b"x")
    send(b"\x1b[?1049l")
    return seen


def native() -> dict:
    detector = shutil.which("systemd-detect-virt")
    if (
        sys.platform != "linux" or detector is None
        or any(Path(path).exists() for path in ("/.dockerenv", "/run/.containerenv"))
        or subprocess.run([detector, "--container", "--quiet"], check=False, timeout=5).returncode != 1
    ):
        raise ValueError("release observations require a non-container Linux SSH peer")
    return {"native_linux": True}


def main() -> int:
    if len(sys.argv) != 2 or not all(os.isatty(fd) for fd in (0, 1, 2)):
        raise ValueError("a named terminal challenge requires an interactive SSH PTY")
    stage = sys.argv[1]
    probe = {"grid": grid, "vim": vim, "modes": modes, "native": native}[stage]
    socket = os.environ.get("SSH_CONNECTION", "").split()
    if len(socket) != 4:
        raise ValueError("OpenSSH did not provide the authenticated connection endpoints")
    previous = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        observed = probe()
        # Keep each observation short enough to fit a normal terminal row.
        for key, value in observed.items():
            send(f"\r\nROW_PROBE_{key}={json.dumps(value, ensure_ascii=True)}".encode())
        send(f"\r\nROW_PROBE_SOCKET={' '.join(socket)}".encode())
    finally:
        termios.tcsetattr(0, termios.TCSANOW, previous)
    print(f"\nROW_PROBE_END_{stage}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
