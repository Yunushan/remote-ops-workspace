"""Record and validate real Debian embedded-server client captures in the lab."""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import secrets
import select
import shlex
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

from scripts.assemble_debian_server_evidence import CAPTURES_INDEX  # noqa: E402
from scripts.capture_moba_xserver_forwarding import stop_process  # noqa: E402
from scripts.check_moba_server_release_evidence import (  # noqa: E402
    CLIENT_CAPTURE_SCHEMA,
    asset,
    read_capture_json,
    read_client_data,
    verify_client,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import secure_regular_file, sha256_file  # noqa: E402
from scripts.debian_release_fixture import (  # noqa: E402
    ROW_EXECUTABLE,
    install_release_deb,
    release_deb_version,
)
from scripts.debian_server_notices import PAYLOAD  # noqa: E402
from scripts.isolated_linux_fixture import NETWORK_OR_NAMESPACE_CAPABILITIES  # noqa: E402
from scripts.moba_debian_server_payload import server_payload  # noqa: E402

TARGET = "linux-x86_64"
HOST = "127.0.0.1"
MANAGED_PORTS = {"http": 18081, "ftp": 12121, "tftp": 16969, "ssh": 12222, "sftp": 12223, "vnc": 5927}
TELNET_PORT = 12323
USER = "row-server-proof"


def run(
    argv: list[str], *, env: dict[str, str], data: bytes | None = None, check: bool = True, timeout: int = 20,
) -> subprocess.CompletedProcess[bytes]:
    stdin = subprocess.DEVNULL if data is None else None
    result = subprocess.run(argv, env=env, input=data, stdin=stdin, capture_output=True, timeout=timeout, check=False)
    if check and result.returncode:
        raise ValueError(f"{Path(argv[0]).name} failed with exit status {result.returncode}")
    return result


def write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_lab(mode: str) -> None:
    if sys.platform != "linux" or os.geteuid() != 0:
        raise ValueError("server capture requires an isolated Linux lab with root")
    interfaces = Path("/proc/net/dev").read_text(encoding="ascii").splitlines()[2:]
    if mode == "nfs":
        if {line.partition(":")[0].strip() for line in interfaces} != {"lo"}:
            raise ValueError("NFS capture requires a guest with only a loopback interface")
        return
    capabilities = next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines()
                        if line.startswith("CapBnd:"))
    routes = Path("/proc/net/route").read_text(encoding="ascii").splitlines()[1:]
    ipv6_routes = Path("/proc/net/ipv6_route")
    ipv6_default = ipv6_routes.is_file() and any(
        fields[:2] == ["0" * 32, "00"] and int(fields[8], 16) & 0x201 == 1
        for fields in (line.split() for line in ipv6_routes.read_text(encoding="ascii").splitlines())
    )
    if (not Path("/.dockerenv").is_file() or int(capabilities, 16) & NETWORK_OR_NAMESPACE_CAPABILITIES
            or any(route.split()[1] == "00000000" for route in routes) or ipv6_default):
        raise ValueError("managed capture requires an isolated Docker network and dropped network and namespace capabilities")


class Recorder:
    def __init__(self, root: Path, work: Path, package: Path, source_path: Path | None) -> None:
        self.root, self.work, self.package = root, work, package
        self.asset = {"name": package.name, "sha256": sha256_file(package)}
        version = release_deb_version(package.name, TARGET)
        self.source = read_capture_json(source_path, "source identity") if source_path else None
        if self.source is None:
            self.identity = {"source_head_sha": None, "workflow_run_url": None, "run_attempt": 0,
                             "tested_release_asset": self.asset}
        else:
            self.identity = capture_release_identity({"source": self.source, "release_asset": self.asset}, "lab capture")
            if self.identity["release_tag"] != f"v{version}":
                raise ValueError("source tag differs from the Debian package version")
        self.env = {
            "PATH": "/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "SHELL": "/bin/sh",
            "ROW_HOME": str(work / "row-home"), "HOME": str(work),
        }
        self.runtime: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []

    def verify_installed(self) -> None:
        extracted = self.work / "package"
        self.command("dpkg-deb", "--extract", str(self.package.resolve()), str(extracted), timeout=120)
        _, packaged = server_payload(extracted / PAYLOAD, TARGET)
        manifest, installed = server_payload(Path("/") / PAYLOAD, TARGET)
        if installed != packaged:
            raise ValueError("the installed daemon bytes differ from the tested Debian asset")
        self.runtime = {row["service"]: row["runtime"] for row in manifest["services"]}
        launcher = sha256_file(Path(ROW_EXECUTABLE))
        if launcher != sha256_file(extracted / ROW_EXECUTABLE.lstrip("/")) or launcher != self.runtime["http"]["sha256"]:
            raise ValueError("the installed ROW launcher differs from the Debian package")

    def command(self, *argv: str, **kwargs):
        return run(list(argv), env=self.env, **kwargs)

    def policy(self, service: str, port: int, *args: str) -> dict[str, Any]:
        return json.loads(self.command(ROW_EXECUTABLE, "servers", "config-plan", service, "--host", HOST,
                                       "--port", str(port), "--json", *args).stdout)

    def attachment(self, name: str, data: bytes) -> dict[str, str]:
        path = self.root / name
        with path.open("xb") as output:
            output.write(data)
        return {"file": name, "sha256": sha256_file(path)}

    def verify(self, observation: dict[str, Any]) -> None:
        service = observation["service"]
        reference = observation["receipt"]
        receipt = read_capture_json(asset(self.root, reference, "client receipt"), "client receipt")
        argv = receipt.get("argv")
        if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
            raise ValueError(f"{service} receipt requires recorded client arguments")
        verify_client(self.root, service, {
            "policy": observation["policy"], "runtime": self.runtime[service],
            "client_test": {"evidence_file": reference["file"], "evidence_sha256": reference["sha256"],
                            "command": shlex.join(argv)},
        }, self.identity, set())

    def record(self, service: str, policy: dict[str, Any], outcome: subprocess.CompletedProcess[bytes], capture: bytes,
               challenge: bytes | None = None, **extra: bytes) -> None:
        receipt = {
            "schema": CLIENT_CAPTURE_SCHEMA, "service": service, "runtime_sha256": self.runtime[service]["sha256"],
            "release_asset_sha256": self.asset["sha256"], "source_head_sha": self.identity["source_head_sha"],
            "workflow_run_url": self.identity["workflow_run_url"], "run_attempt": self.identity["run_attempt"],
            "endpoint": {"host": HOST, "port": policy["port"]},
            "argv": list(outcome.args), "exit_code": outcome.returncode,
            "capture": self.attachment(f"{service}.data", capture),
        }
        if challenge is not None:
            receipt["challenge"] = self.attachment(f"{service}-challenge.txt", challenge)
        for key, data in extra.items():
            receipt[key] = self.attachment(f"{service}-{key}.txt", data)
        reference = self.attachment(f"{service}-receipt.json", json.dumps(receipt, indent=2).encode() + b"\n")
        observation = {"service": service, "policy": policy, "receipt": reference}
        self.verify(observation)
        self.observations.append(observation)

    def include_nfs(self, source: Path) -> None:
        index_path, error = secure_regular_file(source, CAPTURES_INDEX, "NFS capture index")
        if index_path is None:
            raise ValueError(error)
        index = read_capture_json(index_path, "NFS capture index")
        services = index.get("services")
        if (
            index.get("source") != self.source or index.get("release_asset") != self.asset
            or not isinstance(services, list) or len(services) != 1
            or not isinstance(services[0], dict) or services[0].get("service") != "nfs"
            or not isinstance(services[0].get("policy"), dict)
        ):
            raise ValueError("NFS fragment must bind this release asset and source attempt")
        observation = services[0]
        receipt_path = asset(source, observation.get("receipt"), "NFS receipt")
        receipt = read_capture_json(receipt_path, "NFS receipt")
        for key in ("capture", "challenge", "mount_options", "rejected_sys_mount"):
            attachment = asset(source, receipt.get(key), key)
            if attachment.parent != source or (
                not attachment.name.startswith("nfs-") and attachment.name != "nfs.data"
            ):
                raise ValueError("unexpected NFS capture attachment path")
            self.attachment(attachment.name, read_client_data(attachment))
        if receipt_path.name != "nfs-receipt.json":
            raise ValueError("unexpected NFS receipt filename")
        self.attachment(receipt_path.name, receipt_path.read_bytes())
        self.verify(observation)
        self.observations.append(observation)

    def finish(self) -> None:
        if sha256_file(self.package) != self.asset["sha256"]:
            raise ValueError("the Debian asset changed during capture")
        write_json(self.root / CAPTURES_INDEX, {"source": self.source, "release_asset": self.asset,
                                                "services": self.observations})


@contextlib.contextmanager
def managed(recorder: Recorder, service: str, *args: str):
    port = MANAGED_PORTS[service]
    output = recorder.work / "start.json"
    command = [ROW_EXECUTABLE, "servers", "start", service, "--host", HOST, "--port", str(port), "--json", *args]
    started = False
    try:
        with output.open("wb") as log:
            subprocess.run(command, env=recorder.env, stdout=log, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, timeout=15, check=True)
        started = True
        text = output.read_text(encoding="utf-8")
        record, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
        runtime = recorder.runtime[service]
        installed = Path("/") / PAYLOAD / runtime["executable"]
        if (not record["runtime"]["bundled"] or Path(record["runtime"]["executable"]) != installed
                or sha256_file(Path(record["command"][0])) != runtime["sha256"]
                or record["lifecycle"]["state"] != "started"):
            raise ValueError(f"{service} did not start from the verified packaged runtime")
        yield port, recorder.policy(service, port, *args)
    finally:
        stopped = recorder.command(ROW_EXECUTABLE, "servers", "stop", service, "--json", check=False)
        if started and (stopped.returncode or json.loads(stopped.stdout).get("running")):
            raise ValueError(f"{service} did not stop after capture")


def wait_tcp(port: int) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise ValueError(f"no local fixture listener on port {port}")


def capture_file_services(recorder: Recorder, served: Path, marker: bytes) -> None:
    options = ("--root", str(served))
    curl = ("curl", "-fsS", "--noproxy", "*", "--max-time", "8")
    with managed(recorder, "http", *options) as (port, policy):
        wait_tcp(port)
        result = recorder.command(*curl, f"http://{HOST}:{port}/proof.txt")
        recorder.record("http", policy, result, result.stdout, marker)
    with managed(recorder, "tftp", *options) as (port, policy):
        downloaded = recorder.work / "tftp-download"
        result = recorder.command("tftp", "-m", "binary", HOST, str(port), "-c", "get",
                                  str(served / "proof.txt"), str(downloaded), timeout=12)
        recorder.record("tftp", policy, result, downloaded.read_bytes(), marker)

    cert, key = recorder.work / "ftp-cert.pem", recorder.work / "ftp-key.pem"
    recorder.command("openssl", "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "1",
                     "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
                     "-keyout", str(key), "-out", str(cert))
    secret = secrets.token_hex(18)
    netrc = recorder.work / "ftp-login"
    netrc.touch(mode=0o600, exist_ok=False)
    netrc.write_text(f"machine localhost login rowproof password {secret}\n", encoding="ascii")
    credentials = {"ROW_FTP_USERNAME": "rowproof", "ROW_FTP_PASSWORD": secret,
                   "ROW_FTP_TLS_CERT": str(cert), "ROW_FTP_TLS_KEY": str(key)}
    recorder.env.update(credentials)
    try:
        with managed(recorder, "ftp", *options, "--require-tls") as (port, policy):
            wait_tcp(port)
            result = recorder.command(*curl, "--ssl-reqd", "--cacert", str(cert), "--netrc-file", str(netrc),
                                      f"ftp://localhost:{port}/proof.txt")
            recorder.record("ftp", policy, result, result.stdout, marker)
    finally:
        for key in credentials:
            del recorder.env[key]


def create_account(recorder: Recorder, marker: bytes) -> tuple[Path, bytes]:
    recorder.command("useradd", "-m", "-s", "/bin/sh", USER)
    home = Path("/home") / USER
    (home / "proof.txt").write_bytes(marker)
    secret = secrets.token_hex(18).encode("ascii")
    recorder.command("chpasswd", data=USER.encode("ascii") + b":" + secret + b"\n")
    return home, secret


def capture_secure_shell(recorder: Recorder, home: Path, marker: bytes) -> None:
    identity, known = recorder.work / "identity", recorder.work / "known_hosts"
    recorder.command("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity))
    recorder.command("ssh-keygen", "-A")
    Path("/run/sshd").mkdir(exist_ok=True)
    private_dir = home / ".ssh"
    private_dir.mkdir(mode=0o700)
    keys = private_dir / "authorized_keys"
    keys.write_bytes(identity.with_suffix(".pub").read_bytes())
    keys.chmod(0o600)
    recorder.command("chown", "-R", f"{USER}:{USER}", str(private_dir))
    host_key = Path("/etc/ssh/ssh_host_ed25519_key.pub").read_text(encoding="ascii").strip()
    known.write_text("".join(f"[{HOST}]:{MANAGED_PORTS[s]} {host_key}\n" for s in ("ssh", "sftp")), encoding="ascii")
    auth = ("-F", "/dev/null", "-i", str(identity), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}")
    with managed(recorder, "ssh") as (port, policy):
        wait_tcp(port)
        result = recorder.command("ssh", *auth, "-p", str(port), f"{USER}@{HOST}", "cat proof.txt")
        recorder.record("ssh", policy, result, result.stdout, marker)
    with managed(recorder, "sftp") as (port, policy):
        wait_tcp(port)
        downloaded = recorder.work / "sftp-download"
        result = recorder.command("sftp", *auth, "-P", str(port), "-b", "-", f"{USER}@{HOST}",
                                  data=f'get proof.txt "{downloaded}"\n'.encode())
        recorder.record("sftp", policy, result, downloaded.read_bytes(), marker)


def capture_vnc(recorder: Recorder) -> None:
    display = ":27"
    bitmap = recorder.work / "framebuffer.xbm"
    values = ", ".join(["0x00, 0xff"] * 8 + ["0xff, 0x00"] * 8)
    bitmap.write_text("#define fixture_width 16\n#define fixture_height 16\n"
                      f"static unsigned char fixture_bits[] = {{\n{values}\n}};\n")
    xserver = subprocess.Popen(["Xvfb", display, "-screen", "0", "320x240x24", "-nolisten", "tcp", "-noreset"],
                               env=recorder.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        recorder.env["DISPLAY"] = display
        deadline = time.monotonic() + 8
        while recorder.command("xsetroot", "-bitmap", str(bitmap), "-fg", "#102070", "-bg",
                               "#d5ca50", check=False).returncode:
            if time.monotonic() >= deadline or xserver.poll() is not None:
                raise ValueError("the local Xvfb framebuffer was not ready")
            time.sleep(0.1)
        passwd = recorder.work / "vnc-password"
        runtime = Path("/") / PAYLOAD / recorder.runtime["vnc"]["executable"]
        recorder.command(str(runtime), "-storepasswd", secrets.token_hex(4), str(passwd))
        recorder.env["ROW_VNC_PASSWORD_FILE"] = str(passwd)
        with managed(recorder, "vnc") as (port, policy):
            wait_tcp(port)
            jpeg, png = recorder.work / "client.jpg", recorder.work / "client.png"
            result = recorder.command("vncsnapshot", "-nocursor", "-passwd", str(passwd), f"{HOST}:{port - 5900}", str(jpeg))
            recorder.command("convert", str(jpeg), f"PNG24:{png}")
            recorder.record("vnc", policy, result, png.read_bytes())
    finally:
        stop_process(xserver)


def telnet_session(recorder: Recorder, secret: bytes, expected: bytes):
    import pty

    argv = ["telnet", HOST, str(TELNET_PORT)]
    master, slave = pty.openpty()
    try:
        client = subprocess.Popen(argv, env={**recorder.env, "TERM": "xterm"}, stdin=slave, stdout=slave, stderr=slave)
    except OSError:
        os.close(master)
        raise
    finally:
        os.close(slave)
    transcript = bytearray()

    def expect(marker: bytes) -> None:
        before = len(transcript)
        deadline = time.monotonic() + 10
        while marker not in transcript[before:]:
            ready, _, _ = select.select([master], [], [], max(0, deadline - time.monotonic()))
            if not ready or len(transcript) > 65536:
                raise ValueError("the local Telnet client did not complete its login challenge")
            transcript.extend(os.read(master, 4096))

    try:
        expect(b"login:")
        os.write(master, USER.encode("ascii") + b"\n")
        expect(b"Password:")
        os.write(master, secret + b"\n")
        expect(b"$ ")
        os.write(master, b'cat proof.txt\n')
        expect(expected.strip())
        os.write(master, b"exit\n")
        return subprocess.CompletedProcess(argv, client.wait(timeout=10)), bytes(transcript).replace(secret, b"[redacted]")
    finally:
        stop_process(client)
        os.close(master)


def capture_telnet(recorder: Recorder, secret: bytes, marker: bytes) -> None:
    policy = recorder.policy("telnet", TELNET_PORT)
    configured = policy["settings"]["host_config"]["service"]
    runtime = Path("/") / PAYLOAD / recorder.runtime["telnet"]["executable"]
    settings = {**configured, "disable": "no", "server": str(runtime)}
    config = recorder.work / "xinetd-telnet.conf"
    config.write_text("service row-telnet-proof\n{\n" + "".join(f"    {key} = {value}\n"
                      for key, value in sorted(settings.items())) + "}\n", encoding="ascii")
    daemon = subprocess.Popen(["xinetd", "-dontfork", "-stayalive", "-f", str(config)], env=recorder.env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_tcp(TELNET_PORT)
        result, transcript = telnet_session(recorder, secret, marker)
        recorder.record("telnet", policy, result, transcript, marker)
    finally:
        stop_process(daemon)


def capture_managed(recorder: Recorder) -> None:
    asset, observed = install_release_deb(recorder.root, recorder.package, TARGET)
    if asset != recorder.asset or (observed is not None and observed != recorder.source):
        raise ValueError("the installed package or Actions attempt differs from the requested capture")
    recorder.verify_installed()
    marker = f"row-client-qualification-{secrets.token_hex(16)}\n".encode("ascii")
    served = recorder.work / "served"
    served.mkdir()
    (served / "proof.txt").write_bytes(marker)
    home, secret = create_account(recorder, marker)
    capture_file_services(recorder, served, marker)
    capture_secure_shell(recorder, home, marker)
    capture_vnc(recorder)
    capture_telnet(recorder, secret, marker)


def capture_nfs(recorder: Recorder, hostname: str, port: int, account: str, challenge: Path) -> None:
    if not 1 <= port <= 65535 or not account or account.startswith("-") or not challenge.name:
        raise ValueError("NFS capture requires a valid port, account and challenge file")
    if (
        not hostname or hostname.startswith("-") or "/" in hostname or ":" in hostname or "%" in hostname
        or not all(ipaddress.ip_address(row[4][0]).is_loopback for row in socket.getaddrinfo(hostname, port))
    ):
        raise ValueError("the NFS Kerberos hostname must resolve exclusively to loopback")
    recorder.verify_installed()
    threads = Path("/proc/fs/nfsd/threads")
    if threads.read_text().strip() != "0":
        raise ValueError("NFS capture requires a configured lab export with no running NFS threads")
    daemon = str(Path("/") / PAYLOAD / recorder.runtime["nfs"]["executable"])
    try:
        recorder.command(daemon, "4")
        if Path("/proc/fs/nfsd/portlist").read_text().split() != ["tcp", str(port)]:
            raise ValueError("the packaged NFS daemon did not start the configured TCP-only listener")
        capture_nfs_mounts(recorder, hostname, port, account, challenge)
    finally:
        if threads.read_text().strip() != "0":
            recorder.command(daemon, "0")


def capture_nfs_mounts(recorder: Recorder, hostname: str, port: int, account: str, challenge: Path) -> None:
    policy = recorder.policy("nfs", port)
    expected = challenge.read_bytes()
    authorized, unauthorized = recorder.work / "krb5p", recorder.work / "sys"
    authorized.mkdir(mode=0o755)
    unauthorized.mkdir()
    mount = ("mount", "-v", "-t", "nfs4", "-o")
    options = f"vers=4.2,proto=tcp,port={port},clientaddr={HOST},retry=0"
    endpoint = f"{hostname}:/"
    result = recorder.command(*mount, f"{options},sec=krb5p", endpoint, str(authorized))
    try:
        observed = recorder.command("runuser", "-u", account, "--", "cat", str(authorized / challenge.name)).stdout
        effective = recorder.command("findmnt", "-n", "-o", "SOURCE,FSTYPE,OPTIONS", str(authorized)).stdout
    finally:
        recorder.command("umount", str(authorized))
    denial = recorder.command(*mount, f"{options},sec=sys,nosharecache", endpoint, str(unauthorized), check=False)
    if denial.returncode == 0:
        recorder.command("umount", str(unauthorized))
        raise ValueError("the NFS export unexpectedly allowed a sec=sys mount")
    recorder.record("nfs", policy, result, observed, expected, mount_options=effective,
                    rejected_sys_mount=denial.stdout + denial.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deb", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path, help="exact source object from the waiting tagged workflow")
    mode.add_argument("--local", action="store_true", help="exercise clients without release provenance")
    commands = parser.add_subparsers(dest="capture", required=True)
    managed_parser = commands.add_parser("managed")
    managed_parser.add_argument("--nfs-capture", type=Path)
    nfs_parser = commands.add_parser("nfs")
    nfs_parser.add_argument("--hostname", required=True)
    nfs_parser.add_argument("--port", required=True, type=int)
    nfs_parser.add_argument("--account", required=True)
    nfs_parser.add_argument("--challenge", required=True, type=Path)
    args = parser.parse_args()
    try:
        require_lab(args.capture)
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("capture output must be a new directory")
        if args.source and args.capture == "managed" and args.nfs_capture is None:
            raise ValueError("a release capture requires the NFS fragment")
        with (TemporaryDirectory(prefix=".client-capture-", dir=args.out.parent) as temporary,
              TemporaryDirectory(prefix="row-client-lab-") as private):
            root = Path(temporary) / "captures"
            root.mkdir()
            work = Path(private)
            work.chmod(0o755)
            recorder = Recorder(root, work, args.deb, args.source)
            if args.capture == "nfs":
                capture_nfs(recorder, args.hostname, args.port, args.account, args.challenge)
            else:
                capture_managed(recorder)
                if args.nfs_capture is not None:
                    recorder.include_nfs(args.nfs_capture)
            recorder.finish()
            root.rename(args.out)
        print(f"Validated {len(recorder.observations)} Debian server client captures")
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Debian server capture failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
