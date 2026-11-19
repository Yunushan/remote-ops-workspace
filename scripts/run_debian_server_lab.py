"""Capture eight Debian release protocol receipts using disposable Docker fixtures."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import sha256_file, valid_sha256  # noqa: E402
from scripts.debian_release_fixture import actions_source, release_deb_version  # noqa: E402

RUN = (
    "run", "--rm", "--pull", "never", "--platform", "linux/amd64",
    "--cap-drop", "NET_ADMIN", "--cap-drop", "NET_RAW", "--cap-drop", "SYS_ADMIN",
    "--security-opt", "no-new-privileges",
)
RESULT_OWNER = """
owner=$1
shift
if [[ $owner != - ]]; then
    trap 'chown -R -- "$owner" /proof' EXIT
fi
"$@"
"""


def docker(*args: str, timeout: int = 30, check: bool = True) -> str:
    return subprocess.run(
        ("docker", *args), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=check,
    ).stdout.strip()


def mount(path: Path, target: str, *, writable: bool = False) -> tuple[str, str]:
    spec = f"type=bind,source={path},target={target}"
    return "--mount", spec if writable else spec + ",readonly"


def capture(image: str, package: Path, digest: str, output: Path, *, local: bool = False) -> None:
    name = package.name
    package = package.resolve(strict=True)
    version = release_deb_version(name, "linux-x86_64")
    if not package.is_file() or not valid_sha256(digest) or sha256_file(package) != digest:
        raise ValueError("the tested Debian asset does not match the supplied SHA-256")
    if output.exists() or output.is_symlink():
        raise ValueError("the capture output must be a new directory")
    output = output.absolute()
    source = None if local else actions_source(f"v{version}")
    if not local:
        capture_release_identity({"source": source, "release_asset": {"name": name, "sha256": digest}}, "lab capture")
    image_id = docker("image", "inspect", "--format", "{{.Id}}", image)
    prefix = f"row-debian-servers-{uuid4().hex}"
    owner = f"{os.getuid()}:{os.getgid()}" if sys.platform != "win32" else "-"
    asset = f"/release/{name}"

    with TemporaryDirectory(prefix=".debian-server-lab-", dir=output.parent) as scratch:
        scratch_path = Path(scratch)
        input_dir, proof = scratch_path / "input", scratch_path / "proof"
        input_dir.mkdir()
        proof.mkdir()
        mode = ("--local",)
        if source is not None:
            (input_dir / "source.json").write_text(json.dumps(source) + "\n", encoding="utf-8")
            mode = ("--source", "/input/source.json")
        shared = (
            *mount(ROOT, "/src"), *mount(package, asset), *mount(input_dir, "/input"),
            *mount(proof, "/proof", writable=True), "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--entrypoint", "bash", image_id, "-ec", RESULT_OWNER, "debian-lab", owner,
        )
        nfs_container = f"{prefix}-nfs"
        try:
            print(docker(
                *RUN, "--name", nfs_container, "--network", "none", *shared,
                "bash", "/src/scripts/debian_server_nfs_lab.sh", asset, digest, "/proof/nfs",
                timeout=420,
            ))
        finally:
            docker("rm", "--force", nfs_container, check=False)
        if not (proof / "nfs" / "captures.json").is_file():
            raise ValueError("the NFS guest did not return a client receipt")

        # tftpd uses AI_ADDRCONFIG and needs a configured non-loopback
        # interface. Clients still contact only the fixture's loopback ports.
        network = docker("network", "create", "--internal", prefix)
        managed_container = f"{prefix}-managed"
        try:
            print(docker(
                *RUN, "--name", managed_container, "--network", network, *shared,
                "python", "/src/scripts/capture_debian_server_clients.py",
                "--deb", asset, *mode, "--out", "/proof/combined", "managed", "--nfs-capture", "/proof/nfs",
                timeout=180,
            ))
        finally:
            docker("rm", "--force", managed_container, check=False)
            docker("network", "rm", network, check=False)
        if not (proof / "combined" / "captures.json").is_file() or sha256_file(package) != digest:
            raise ValueError("combined capture did not bind the unchanged Debian asset")
        (proof / "combined").rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="local Debian fixture image")
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--local", action="store_true", help="rehearse without release provenance")
    args = parser.parse_args()
    try:
        capture(args.image, args.deb, args.sha256, args.out, local=args.local)
    except subprocess.CalledProcessError as error:
        print(error.stdout or "", file=sys.stderr)
        parser.exit(1, f"Debian lab failed with exit status {error.returncode}\n{error.stderr or ''}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Debian lab failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
