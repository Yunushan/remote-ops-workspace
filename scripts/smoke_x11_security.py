"""Verify managed X11 cookie authentication and POSIX TCP isolation with Xvfb."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))


def main() -> int:
    from remote_ops_workspace.x11 import (
        _prepare_x_server_authority,
        build_moba_x_server_plan,
        is_x_display_in_use,
        managed_x11_environment,
        start_moba_x_server,
        stop_moba_x_server,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "posix":
        raise RuntimeError("Xvfb no-TCP security probe requires a POSIX host")
    binaries = args.runtime_root.resolve() / "usr/bin" if args.runtime_root else None
    xvfb = str(binaries / "Xvfb") if binaries else shutil.which("Xvfb")
    probe = str(binaries / "xdpyinfo") if binaries else shutil.which("xdpyinfo")
    xauth = shutil.which("xauth")
    if not xvfb or not probe or not xauth:
        raise RuntimeError("X11 security smoke requires Xvfb, xdpyinfo and xauth")
    environment = dict(os.environ)
    if args.runtime_root:
        libraries = args.runtime_root.resolve() / "usr/lib/x86_64-linux-gnu"
        environment["LD_LIBRARY_PATH"] = str(libraries) + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
    display = next(f":{number}" for number in range(91, 121) if not is_x_display_in_use(f":{number}"))
    scratch = REPOSITORY / ".tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="x11-security-smoke-", dir=scratch) as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(scratch.resolve())
        authority = directory / "Xauthority"
        state = directory / "state.json"
        plan = build_moba_x_server_plan(display, system="linux", which=lambda name: xvfb if name == "Xvfb" else None, packaged_roots=[], authority_path=authority)
        processes = []
        log = directory / "server.log"

        def spawn(command, env):
            with log.open("w", encoding="utf-8") as output:
                process = subprocess.Popen(command, env={**environment, **env}, stdout=output, stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        start_moba_x_server(plan, state_path=state, popen_factory=spawn)
        process = processes[0]
        inherited_authority = os.environ.get("XAUTHORITY")
        os.environ["XAUTHORITY"] = str(authority)
        try:
            client_environment = {**environment, **managed_x11_environment(display)}
            transported_environment = {**environment, **managed_x11_environment(f"unix/{display}")}
        finally:
            if inherited_authority is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = inherited_authority
        try:
            deadline = time.monotonic() + 10
            authorized = None
            while time.monotonic() < deadline:
                authorized = subprocess.run([probe], env=client_environment, capture_output=True, text=True, timeout=2)
                if authorized.returncode == 0:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"Xvfb exited: {log.read_text()}")
                time.sleep(0.1)
            assert authorized is not None and authorized.returncode == 0, authorized.stderr if authorized else "missing probe"
            assert "dimensions:" in authorized.stdout
            transported = subprocess.run([probe], env=transported_environment, capture_output=True, text=True, timeout=3)
            assert transported.returncode == 0 and "dimensions:" in transported.stdout, transported.stderr
            listed = subprocess.run([xauth, "-f", str(authority), "list"], env=environment, capture_output=True, text=True, timeout=3)
            assert listed.returncode == 0 and "MIT-MAGIC-COOKIE-1" in listed.stdout
            # Do not emit xauth stdout: it contains the real session cookie.
            empty = directory / "empty-authority"
            empty.write_bytes(b"")
            missing = subprocess.run([probe], env={**client_environment, "XAUTHORITY": str(empty)}, capture_output=True, text=True, timeout=3)
            assert missing.returncode != 0, "unauthenticated local client unexpectedly succeeded"
            wrong = directory / "wrong-authority"
            _prepare_x_server_authority([xvfb, display, "-auth", str(wrong)], {"XAUTHORITY": str(wrong)}, display)
            assert wrong.read_bytes() != authority.read_bytes()
            denied = subprocess.run([probe], env={**client_environment, "XAUTHORITY": str(wrong)}, capture_output=True, text=True, timeout=3)
            assert denied.returncode != 0, "wrong-cookie local client unexpectedly succeeded"
            tcp_port = 6000 + int(display[1:])
            for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
                for entry in table.read_text().splitlines()[1:]:
                    columns = entry.split()
                    assert not (columns[3] == "0A" and int(columns[1].split(":")[1], 16) == tcp_port), "X server unexpectedly opened a TCP listener"
            authority_digest = hashlib.sha256(authority.read_bytes()).hexdigest()
        finally:
            stopped = stop_moba_x_server(state_path=state)
            assert stopped.pid is None and stopped.state == "stopped"
            process.wait(timeout=5)
        payload = {
            "schema": "row.x11-security-smoke.v1", "passed": True,
            "checked_at": datetime.now(timezone.utc).isoformat(), "display": display,
            "runtime_sha256": hashlib.sha256(Path(xvfb).read_bytes()).hexdigest(),
            "probe_sha256": hashlib.sha256(Path(probe).read_bytes()).hexdigest(),
            "authority_sha256": authority_digest, "xauth_readable": True,
            "authorized_client_passed": True, "managed_client_environment_passed": True,
            "unix_transport_client_passed": True, "missing_cookie_denied": True,
            "wrong_cookie_denied": True, "tcp_ipv4_and_ipv6_listeners_absent": True,
            "process_stopped": process.poll() is not None,
            "limitations": ["POSIX Xvfb fixture; Windows VcXsrv/Xming listener/firewall behavior is not exercised"],
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Managed X11 security smoke passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
