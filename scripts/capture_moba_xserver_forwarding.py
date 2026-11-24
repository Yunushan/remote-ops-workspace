"""Capture a packaged ROW X server and an authenticated OpenSSH X11 window."""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.launcher import build_launch_plan  # noqa: E402
from remote_ops_workspace.models import Profile  # noqa: E402
from scripts.check_moba_xserver_release_evidence import (  # noqa: E402
    FORWARDING_SCHEMA,
    INSTALLED_XSERVER,
    NATIVE_PROBE_ARGV,
    NATIVE_PROBE_PATH,
    NATIVE_PROBE_SCHEMA,
    REMOTE_DISPLAY_PROBE,
    validate_moba_x_server_live_release_evidence,
    validate_moba_x_server_release_asset_evidence,
)
from scripts.check_release_license_compliance import secure_regular_file, sha256_file  # noqa: E402
from scripts.debian_release_fixture import (  # noqa: E402
    PRODUCT_PACKAGE,
    ROW_EXECUTABLE,
    capture_native_debian_probe,
    install_release_deb,
)
from scripts.isolated_linux_fixture import require_offline_container  # noqa: E402

DISPLAY = ":16"
PORT = 22222
USER = "row-x11-proof"
DESKTOP_USER = "row-x11-desktop"
TITLE = "Remote Ops Workspace forwarded X11 clock"
TARGET = "linux-x86_64"
APP = ["/usr/bin/xclock", "-title", TITLE, "-geometry", "280x280+40+45"]


def run(argv: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                          encoding="utf-8", timeout=20, check=check)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_sshd(scratch: Path) -> Path:
    home = Path("/home") / USER
    run(["useradd", "--create-home", "--home-dir", str(home), "--shell", "/bin/sh", USER])
    client_key, host_key = scratch / "identity", scratch / "host_key"
    for key in (client_key, host_key):
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)])
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(mode=0o700)
    authorized = ssh_dir / "authorized_keys"
    authorized.write_bytes(client_key.with_suffix(".pub").read_bytes())
    authorized.chmod(0o600)
    run(["chown", f"{USER}:{USER}", str(ssh_dir), str(authorized)])
    known_host = f"[127.0.0.1]:{PORT} " + host_key.with_suffix(".pub").read_text(encoding="utf-8")
    (scratch / "known_hosts").write_text(known_host, encoding="utf-8")
    Path("/run/sshd").mkdir(exist_ok=True)
    config = scratch / "sshd_config"
    config.write_text("\n".join([
        "ListenAddress 127.0.0.1", f"Port {PORT}", f"HostKey {host_key}", f"PidFile {scratch / 'sshd.pid'}",
        f"AllowUsers {USER}", f"AuthorizedKeysFile {authorized}",
        "AuthenticationMethods publickey", "PasswordAuthentication no",
        "KbdInteractiveAuthentication no", "PermitRootLogin no", "UsePAM yes", "X11Forwarding yes",
        "X11UseLocalhost yes", "XAuthLocation /usr/bin/xauth", "AllowTcpForwarding no", "AllowAgentForwarding no",
        "LogLevel VERBOSE",
    ]) + "\n", encoding="utf-8")
    run(["/usr/sbin/sshd", "-t", "-f", str(config)])
    return config


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_for_sshd(process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 8
    while process.poll() is None and time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise ValueError("isolated SSH daemon did not listen on loopback")


def forward_window(
    scratch: Path, root: Path, env: dict[str, str], *, client_prefix: tuple[str, ...] = (),
) -> dict[str, Any]:
    profile = Profile("Isolated X11", "ssh", host="127.0.0.1", port=PORT, username=USER,
                      identity_file=str(scratch / "identity"), options={"x11": "trusted"})
    plan = build_launch_plan(profile)
    if "-Y" not in plan.command:
        raise ValueError("ROW launcher did not request trusted X11 forwarding")
    ssh = [plan.command[0], "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
           "-o", "StrictHostKeyChecking=yes", "-o", "GlobalKnownHostsFile=/dev/null",
           "-o", f"UserKnownHostsFile={scratch / 'known_hosts'}", *plan.command[1:]]
    control = ["-x" if argument == "-Y" else argument for argument in ssh] + [REMOTE_DISPLAY_PROBE]
    control_stdout = run([*client_prefix, *control], env=env).stdout
    if control_stdout != "remote_display=\n":
        raise ValueError("control session unexpectedly received a remote X11 display")
    command = shlex.join(APP)
    argv = [*ssh, f"{REMOTE_DISPLAY_PROBE}; exec {command}"]
    with (scratch / "ssh-stderr.log").open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen([*client_prefix, *argv], env=env, text=True, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=stderr)
        try:
            assert process.stdout is not None
            if not select.select([process.stdout], [], [], 12)[0]:
                raise ValueError("remote shell did not report its forwarded display")
            match = re.fullmatch(r"remote_display=(localhost:[0-9]+\.[0-9]+)\n", process.stdout.readline())
            if match is None:
                raise ValueError("OpenSSH did not establish a loopback-scoped remote X11 display")
            remote = match[1]
            window_id = wait_for_window(process, env)
            info = root / "window.txt"
            info.write_text(run(["xwininfo", "-id", window_id], env=env).stdout, encoding="utf-8")
            raw = scratch / "window.xwd"
            run(["xwd", "-silent", "-id", window_id, "-out", str(raw)], env=env)
            run(["magick", str(raw), f"PNG24:{root / 'window.png'}"], env=env)
        finally:
            stop_process(process)
    return {
        "schema": FORWARDING_SCHEMA, "display": DISPLAY, "remote_display": remote,
        "ssh_argv": argv, "control_argv": control, "control_stdout": control_stdout,
        "window_id": window_id, "window_title": TITLE, "window_info": "window.txt",
        "window_info_sha256": sha256_file(info), "screenshot_sha256": sha256_file(root / "window.png"),
        "command": command,
    }


def wait_for_window(process: subprocess.Popen, env: dict[str, str]) -> str:
    deadline = time.monotonic() + 12
    pattern = re.compile(rf'^\s*(0x[0-9a-fA-F]+) "{re.escape(TITLE)}"', re.M)
    while process.poll() is None and time.monotonic() < deadline:
        tree = run(["xwininfo", "-root", "-tree"], env=env).stdout
        if match := pattern.search(tree):
            return match[1]
        time.sleep(0.1)
    raise ValueError("no forwarded X11 clock appeared on the managed display")


def copy_installed_runtime(bundle: Path) -> Path:
    installed = Path(INSTALLED_XSERVER)
    manifest, error = secure_regular_file(installed, "xserver-runtime.json", "installed X server manifest")
    if manifest is None:
        raise ValueError(error)
    document = json.loads(manifest.read_bytes())
    runtime = document.get("runtime") if isinstance(document, dict) else None
    if not isinstance(runtime, dict):
        raise ValueError("the installed X server manifest lacks runtime metadata")
    executable, error = secure_regular_file(installed, runtime.get("executable"), "installed X server executable")
    if executable is None:
        raise ValueError(error)
    files = set(run(["dpkg-query", "--listfiles", "--", PRODUCT_PACKAGE]).stdout.splitlines())
    if not {str(manifest), str(executable)} <= files:
        raise ValueError("the tested Debian package must own the X server manifest and executable")
    if sha256_file(executable) != runtime.get("sha256"):
        raise ValueError("the installed X server differs from its package manifest")
    snapshot = bundle / executable.relative_to(installed)
    snapshot.parent.mkdir(parents=True)
    shutil.copy2(manifest, bundle / manifest.name)
    shutil.copy2(executable, snapshot)
    return executable


def prepare_desktop_client(scratch: Path, env: dict[str, str]) -> tuple[Path, int, tuple[str, ...]]:
    import pwd

    run(["useradd", "--create-home", "--shell", "/bin/sh", DESKTOP_USER])
    account = pwd.getpwnam(DESKTOP_USER)
    home = Path(account.pw_dir)
    home.chmod(0o700)
    for filename in ("identity", "known_hosts"):
        target = home / filename
        shutil.copyfile(scratch / filename, target)
        target.chmod(0o600)
        os.chown(target, account.pw_uid, account.pw_gid)
    socket_dir = Path("/tmp/.X11-unix")
    if not socket_dir.exists():
        socket_dir.mkdir()
        socket_dir.chmod(0o1777)
    env.update(HOME=str(home), USER=DESKTOP_USER, LOGNAME=DESKTOP_USER,
               ROW_HOME=str(home / "row"), XAUTHORITY=str(home / "Xauthority"))
    return home, account.pw_uid, (
        "/usr/bin/setpriv", "--reuid", str(account.pw_uid), "--regid", str(account.pw_gid),
        "--clear-groups", "--inh-caps=-all", "--ambient-caps=-all", "--no-new-privs", "--",
    )


def capture(
    row: Path, output: Path, *, release_deb: Path | None = None, installed_runtime: bool = False,
) -> None:
    require_offline_container()
    if installed_runtime and release_deb is None:
        raise ValueError("installed X server capture requires the tested Debian package")
    if os.uname().machine != "x86_64":
        raise ValueError("this qualification uses a Linux x86_64 Xvfb runtime")
    if output.exists() or output.is_symlink():
        raise ValueError("output must be a new directory")
    with (TemporaryDirectory(prefix="row-x11-", dir="/run") as private,
          TemporaryDirectory(prefix=".x11-evidence-", dir=output.parent) as staging):
        scratch = Path(private)
        root = Path(staging) / "capture"
        root.mkdir()
        release = {}
        if release_deb is not None:
            asset, source = install_release_deb(root, release_deb, TARGET)
            release["release_asset"] = asset
            row = Path(ROW_EXECUTABLE)
            if source is not None:
                release["source"] = source
        row = row.resolve(strict=True)
        bundle = root / "bundle"
        env = {**os.environ, "LC_ALL": "C", "DISPLAY": DISPLAY, "ROW_HOME": str(scratch / "row"),
               "XAUTHORITY": str(scratch / "Xauthority"), "ROW_XSERVER_RUNTIME_DIR": str(bundle)}
        packaged = None
        if installed_runtime:
            env.pop("ROW_XSERVER_RUNTIME_DIR")
            packaged = copy_installed_runtime(bundle)
        else:
            run([str(row), "x11", "bundle-runtime", "--out", str(bundle), "--runtime", "xvfb",
                 "--source", "/usr/bin/Xvfb", "--system", "linux", "--release-target", TARGET], env=env)
        config = prepare_sshd(scratch)
        client, uid, prefix = (
            prepare_desktop_client(scratch, env) if packaged is not None else (scratch, None, ())
        )
        daemon_log = scratch / "sshd.log"
        with daemon_log.open("w", encoding="utf-8") as log:
            daemon = subprocess.Popen(["/usr/sbin/sshd", "-D", "-e", "-f", str(config)], stderr=log)
            try:
                wait_for_sshd(daemon)
                try:
                    # Xvfb can inherit the CLI's descriptors and outlive its process.
                    with ((root / "start.json").open("w", encoding="utf-8") as stdout,
                          (scratch / "xserver.log").open("w", encoding="utf-8") as stderr):
                        subprocess.run(
                            [*prefix, str(row), "x11", "start", "--display", DISPLAY,
                             "--authority-file", env["XAUTHORITY"], "--json"],
                            env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=20, check=True,
                        )
                    capture_smoke(row, root, env, client_prefix=prefix, scratch=client)
                    if packaged is not None:
                        capture_installed_runtime(root, packaged, uid, prefix)
                    receipt = forward_window(client, root, env, client_prefix=prefix)
                finally:
                    run([*prefix, str(row), "x11", "stop"], env=env)
            except subprocess.CalledProcessError as exc:
                raise ValueError(f"{exc}\n{exc.stderr or ''}{daemon_log.read_text(encoding='utf-8')}") from exc
            finally:
                stop_process(daemon)
        finish_evidence(root, receipt, release)
        if release_deb is not None:
            capture_native_debian_probe(root, release["release_asset"], TARGET, schema=NATIVE_PROBE_SCHEMA,
                                        receipt_path=NATIVE_PROBE_PATH, argv=NATIVE_PROBE_ARGV, env=env)
        validator = (validate_moba_x_server_release_asset_evidence if "source" in release
                     else validate_moba_x_server_live_release_evidence)
        result = validator(root / "evidence.json", assets_dir=root)
        if not result.passed:
            raise ValueError(f"forwarded X11 evidence failed its release checks: {result.errors}")
        root.rename(output)


def capture_installed_runtime(root: Path, packaged: Path, uid: int | None, prefix: tuple[str, ...]) -> None:
    start = json.loads((root / "start.json").read_bytes())
    pid = start["lifecycle"]["pid"]
    proc = Path("/proc") / str(pid)
    executable = proc / "exe"
    observed = run([*prefix, "readlink", "--", str(executable)]).stdout.strip()
    if observed != str(packaged) or start["command"][0] != str(packaged):
        raise ValueError("the managed X server did not launch from the tested Debian package")
    status = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line)
    uids = [int(value) for value in status["Uid"].split()]
    if uid is None or uid <= 0 or uids != [uid] * 4 or int(status["CapEff"], 16) != 0:
        raise ValueError("the package-owned X server must run as the ordinary desktop user without effective capabilities")
    digest = run([*prefix, "sha256sum", "--", str(executable)]).stdout.split()[0]
    write_json(root / "installed-xserver.json", {
        "executable": str(packaged), "pid": pid, "sha256": digest, "owner": PRODUCT_PACKAGE,
        "uids": uids, "effective_capabilities": 0,
    })


def capture_smoke(
    row: Path, root: Path, env: dict[str, str], *, client_prefix: tuple[str, ...] = (), scratch: Path | None = None,
) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if run([*client_prefix, "xdpyinfo", "-display", DISPLAY], env=env, check=False).returncode == 0:
            output = (scratch if client_prefix and scratch is not None else root) / "smoke.json"
            run([*client_prefix, str(row), "x11", "smoke", "--display", DISPLAY, "--out", str(output)], env=env)
            if output.parent != root:
                shutil.copyfile(output, root / output.name)
            return
        time.sleep(0.1)
    raise ValueError("packaged Xvfb did not accept the authenticated display probe")


def finish_evidence(root: Path, receipt: dict[str, Any], release: dict[str, Any]) -> None:
    manifest_name = "bundle/xserver-runtime.json"
    manifest_path = root / manifest_name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bundled = manifest["runtime"]
    runtime = {key: bundled[key] for key in ("key", "sha256", "source", "bundled")}
    runtime.update(executable=f"bundle/{bundled['executable']}", manifest=manifest_name,
                   manifest_sha256=sha256_file(manifest_path), start="start.json", start_sha256=sha256_file(root / "start.json"))
    installed = root / "installed-xserver.json"
    if installed.is_file():
        runtime.update(installed_runtime=installed.name, installed_runtime_sha256=sha256_file(installed))
    smoke_sha256 = sha256_file(root / "smoke.json")
    receipt.update(runtime_sha256=runtime["sha256"], start_sha256=runtime["start_sha256"], smoke_sha256=smoke_sha256)
    write_json(root / "forwarding.json", receipt)
    write_json(root / "evidence.json", {
        **release,
        "schema": "row.moba-xserver.release-evidence.v1", "release_target": manifest["release_target"],
        "platform": "linux", "display": DISPLAY, "runtime": runtime,
        "smoke": {"passed": True, "status": "passed", "evidence_file": "smoke.json", "evidence_sha256": smoke_sha256},
        "forwarded_gui_app": {
            "status": "passed", "x11_forwarding": "trusted", "window_observed": True, "command": receipt["command"],
            "screenshot": "window.png", "screenshot_sha256": receipt["screenshot_sha256"],
            "receipt": "forwarding.json", "receipt_sha256": sha256_file(root / "forwarding.json"),
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    native = parser.add_mutually_exclusive_group()
    native.add_argument("--row", type=Path, help="preinstalled ROW executable for local capture")
    native.add_argument("--release-deb", type=Path, help="install and qualify the exact Debian release asset")
    parser.add_argument("--installed-runtime", action="store_true", help="require Xvfb owned by the tested Debian package")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        capture(args.row or Path(ROW_EXECUTABLE), args.out, release_deb=args.release_deb,
                installed_runtime=args.installed_runtime)
    except subprocess.CalledProcessError as exc:
        print(f"X11 capture: {exc}\n{exc.stderr or ''}", file=sys.stderr)
        return 1
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"X11 capture: {exc}", file=sys.stderr)
        return 1
    print(f"X11 forwarding evidence passed: {args.out / 'evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
