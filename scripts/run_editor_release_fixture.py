"""Run the release-wheel editor capture with a private Docker SSH peer."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from capture_moba_text_remote_edit import HOST, ORIGINAL, PORT, USER

ROOT = Path(__file__).resolve().parents[1]
RUN = ("run", "--pull", "never", "--platform", "linux/amd64", "--security-opt", "no-new-privileges")
KEYGEN = (
    "ssh-keygen -q -t ed25519 -N '' -f /tmp/client; "
    "ssh-keygen -q -t ed25519 -N '' -f /tmp/host; "
    "cp /tmp/client /client/identity; cp /tmp/client.pub /server/authorized_keys; "
    "cp /tmp/host /server/host_key; cp /tmp/host.pub /client/host_key.pub"
)
SSHD = f"""
useradd --create-home --shell /bin/sh {USER}
install -m 600 /input/host_key /tmp/host_key
install -d -m 700 -o {USER} -g {USER} /home/{USER}/.ssh
install -m 600 -o {USER} -g {USER} /input/authorized_keys /home/{USER}/.ssh/authorized_keys
install -m 600 -o {USER} -g {USER} /input/document.txt /home/{USER}/document.txt
mkdir -p /run/sshd
cat > /tmp/sshd_config <<'EOF'
ListenAddress 0.0.0.0
Port {PORT}
HostKey /tmp/host_key
AllowUsers {USER}
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
UsePAM yes
DisableForwarding yes
Subsystem sftp internal-sftp
LogLevel VERBOSE
EOF
exec /usr/sbin/sshd -D -E /log/sshd.log -f /tmp/sshd_config
"""
CLIENT = """
mkdir /fixture
install -m 600 /input/identity /fixture/identity
install -m 600 /input/known_hosts /fixture/known_hosts
ln -s /log/sshd.log /fixture/sshd.log
/opt/editor/bin/python -m pip install --no-index --no-deps "$1"
exec /opt/editor/bin/python -I /src/scripts/capture_moba_text_remote_edit.py --wheel "$1" --out "$2"
"""


def docker(*args: str, timeout: int = 30, check: bool = True) -> str:
    return subprocess.run(
        ("docker", *args), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=check,
    ).stdout.strip()


def mount(path: Path, target: str, *, writable: bool = False) -> tuple[str, str]:
    spec = f"type=bind,source={path},target={target}"
    return "--mount", spec if writable else f"{spec},readonly"


def wait_for_server(log: Path) -> None:
    started = f"Server listening on 0.0.0.0 port {PORT}."
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if log.is_file() and started in log.read_text(encoding="utf-8"):
            return
        time.sleep(0.1)
    raise TimeoutError("the private SSH fixture did not start")


def run_fixture(image: str, wheel: Path, output: Path) -> None:
    wheel = wheel.resolve(strict=True)
    output = output.absolute()
    if not wheel.is_file() or output.exists() or output.is_symlink():
        raise ValueError("the fixture requires a release wheel and a new evidence directory")
    image = docker("image", "inspect", "--format", "{{.Id}}", image)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".editor-fixture-", dir=output.parent) as scratch:
        root = Path(scratch)
        client, server, logs = (root / name for name in ("client", "server", "logs"))
        for directory in (client, server, logs):
            directory.mkdir()
        (logs / "sshd.log").touch(mode=0o600)
        docker(*RUN, "--rm", "--network", "none", *mount(client, "/client", writable=True),
               *mount(server, "/server", writable=True), image, "sh", "-ec", KEYGEN)
        host_key = (client / "host_key.pub").read_text(encoding="utf-8")
        (client / "known_hosts").write_text(f"[{HOST}]:{PORT} {host_key}", encoding="utf-8", newline="\n")
        (server / "document.txt").write_bytes(ORIGINAL)
        name = f"row-editor-{uuid4().hex}"
        network = docker("network", "create", "--internal", name)
        daemon = ""
        try:
            daemon = docker(
                *RUN, "--detach", "--rm", "--network", network, "--network-alias", HOST,
                *mount(server, "/input"), *mount(logs, "/log", writable=True), image, "sh", "-ec", SSHD,
            )
            wait_for_server(logs / "sshd.log")
            forwarded = ("GITHUB_ACTIONS", "GITHUB_REF", "GITHUB_SHA", "GITHUB_REPOSITORY",
                         "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
            env = [argument for key in forwarded for argument in ("--env", key)]
            print(docker(
                *RUN, "--rm", "--name", name, "--network", network, *env,
                *mount(ROOT, "/src"), *mount(wheel, f"/wheel/{wheel.name}"),
                *mount(client, "/input"), *mount(logs, "/log"), *mount(output.parent, "/proof", writable=True),
                image, "sh", "-ec", CLIENT, "editor-client", f"/wheel/{wheel.name}", f"/proof/{output.name}",
                timeout=180,
            ))
        except subprocess.CalledProcessError:
            log = logs / "sshd.log"
            if log.is_file():
                print("\n".join(log.read_text(encoding="utf-8").splitlines()[-30:]), file=sys.stderr)
            raise
        finally:
            docker("rm", "--force", name, check=False)
            if daemon:
                docker("rm", "--force", daemon, check=False)
            docker("network", "rm", network, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_fixture(args.image, args.wheel, args.out)
    except subprocess.CalledProcessError as exc:
        print(f"Editor fixture command failed ({exc.returncode}): {exc.stderr}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
