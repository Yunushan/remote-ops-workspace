"""Isolated release-wheel capture helpers for the live Qt evidence fixtures."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
from collections.abc import Callable
from importlib.metadata import distribution
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZipFile

FIXTURE = Path("/fixture")
HOST = "row-qt-server"
PORT = 2222
EDITOR_USER = "rowedit"
MACRO_USER = "rowmacro"
EDITOR_ORIGINAL = "opening fixture: café\n".encode()
TARGET = "linux-x86_64"


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



def run_capture(capture: Callable[[Path, Path, dict[str, Any]], None], description: str) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    require_fixture()
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("release capture output must be a new directory")
    tag, asset = verify_wheel(args.wheel)
    from scripts.debian_release_fixture import actions_source

    identity: dict[str, Any] = {"release_target": TARGET, "release_asset": asset}
    if source := actions_source(tag):
        identity["source"] = source
    with TemporaryDirectory(prefix=".qt-capture-", dir=args.out.parent) as work:
        raw, root = Path(work) / "raw", Path(work) / "review"
        raw.mkdir()
        root.mkdir()
        with TemporaryDirectory(prefix="row-qt-state-") as home:
            os.environ.update(ROW_HOME=home, QT_QPA_PLATFORM="offscreen")
            capture(root, raw, identity)
        # Only the completed review files leave the private fixture directory.
        for path in root.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        root.chmod(0o755)
        root.rename(args.out)
