"""Stage and verify the embedded server payload of a Linux Debian release."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryFile

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_servers import (  # noqa: E402
    SERVER_OPENSSH_HELPER_DIR,
    SERVER_RUNTIME_MAX_BYTES,
    verify_packaged_openssh_helpers,
)
from scripts.check_linux_native_elf import validate_elf  # noqa: E402
from scripts.check_release_license_compliance import secure_regular_file, sha256_file  # noqa: E402
from scripts.debian_native_dependencies import debian_dependencies, dependency_field  # noqa: E402
from scripts.debian_release_fixture import release_deb_version  # noqa: E402

PAYLOAD = PurePosixPath("usr/lib/remote-ops-workspace/servers")
LAUNCHER = PurePosixPath("usr/bin/row")
MANIFEST = "servers-runtime.json"
SCHEMA = "row.moba-servers.runtime-bundle.v1"
ELF_TARGETS = {"linux-x86_64": "x86_64", "linux-arm64": "aarch64", "linux-i386": "i686", "linux-armhf": "armhf"}
SERVICES = frozenset({"http", "ftp", "tftp", "ssh", "sftp", "telnet", "vnc", "nfs"})
BUILTINS = {"http": ("python-http", "python"), "ftp": ("pyftpdlib", "pyftpdlib")}
EXTERNAL_SERVICES = SERVICES - BUILTINS.keys()
OPENSSH_DAEMON_KEYS = {"ssh": "sshd", "sftp": "sshd-sftp"}


def private_helper_reference(path: Path, name: str) -> bool:
    reference = f"/{PAYLOAD}/{SERVER_OPENSSH_HELPER_DIR}/{name}".encode("ascii") + b"\x00"
    return reference in path.read_bytes()


def server_payload(
    root: Path, target: str, required: frozenset[str] = SERVICES,
) -> tuple[dict, dict[str, str]]:
    elf = ELF_TARGETS.get(target)
    if elf is None:
        raise ValueError("unsupported Debian embedded server target")
    path, error = secure_regular_file(root, MANIFEST, "embedded server manifest")
    if path is None:
        raise ValueError(error)
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("embedded server manifest exceeds 1 MiB")
    document = json.loads(raw)
    if (
        not isinstance(document, dict) or document.get("schema") != SCHEMA
        or document.get("release_target") != target or document.get("system") != "linux"
        or not isinstance(services := document.get("services"), list) or len(services) != len(required)
    ):
        raise ValueError("embedded server manifest must describe the required services for the exact Linux target")
    digests = {MANIFEST: hashlib.sha256(raw).hexdigest()}
    seen = set()
    private_openssh = {}
    for row in services:
        service = row.get("service") if isinstance(row, dict) else None
        if not isinstance(service, str) or service not in required or service in seen:
            raise ValueError("embedded server manifest must describe each service exactly once")
        seen.add(service)
        runtime = row.get("runtime")
        if (
            not isinstance(runtime, dict) or runtime.get("source") != "packaged"
            or runtime.get("placeholder") is not False or runtime.get("bundled") is not True
            or not isinstance(runtime.get("key"), str) or not runtime["key"]
            or not isinstance(relative := runtime.get("executable"), str) or relative in digests
        ):
            raise ValueError(f"{service} requires a distinct packaged native runtime")
        parts = PurePosixPath(relative).parts
        if len(parts) != 4 or parts[:3] != ("linux", service, "bin") or relative != "/".join(parts):
            raise ValueError(f"{service} executable must use the installed runtime layout")
        if service in BUILTINS and (runtime["key"], parts[3]) != BUILTINS[service]:
            raise ValueError(f"{service} must use the packaged ROW launcher runtime")
        executable, error = secure_regular_file(root, relative, f"{service} daemon")
        if executable is None:
            raise ValueError(error)
        if not 0 < executable.stat().st_size <= SERVER_RUNTIME_MAX_BYTES:
            raise ValueError(f"{service} daemon has an invalid size")
        digest = sha256_file(executable)
        if digest != runtime.get("sha256"):
            raise ValueError(f"{service} daemon differs from its manifest digest")
        validate_elf(executable, elf)
        digests[relative] = digest
        if service in OPENSSH_DAEMON_KEYS and private_helper_reference(executable, "sshd-session"):
            if runtime["key"] != OPENSSH_DAEMON_KEYS[service] or parts[3] != "sshd":
                raise ValueError(f"{service} must record the correct packaged OpenSSH daemon")
            private_openssh[service] = digest
    if "openssh_helpers" in document:
        if private_openssh.keys() != OPENSSH_DAEMON_KEYS.keys() or len(set(private_openssh.values())) != 1:
            raise ValueError("SSH and SFTP must use the same OpenSSH daemon built for the package-owned helpers")
        helpers = verify_packaged_openssh_helpers(root, document["openssh_helpers"])
        for relative in helpers:
            validate_elf(root / relative, elf)
        session = root / SERVER_OPENSSH_HELPER_DIR / "sshd-session"
        if not private_helper_reference(session, "sshd-auth"):
            raise ValueError("sshd-session must reference the package-owned sshd-auth")
        digests.update(helpers)
    elif private_openssh:
        raise ValueError("the package-owned OpenSSH helper files must be recorded in the manifest")
    return document, digests


def stage_payload(source: Path, package_root: Path, target: str) -> str:
    document, expected = server_payload(source, target, EXTERNAL_SERVICES)
    destination = package_root / PAYLOAD
    launcher = package_root / LAUNCHER
    validate_elf(launcher, ELF_TARGETS[target])
    launcher_digest = sha256_file(launcher)
    destination.mkdir(parents=True, exist_ok=False)
    del expected[MANIFEST]
    for relative, digest in expected.items():
        staged = destination / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, staged)
        if sha256_file(staged) != digest:
            raise ValueError(f"the approved runtime changed while staging {relative}")
        staged.chmod(0o755)
    for service, (key, name) in BUILTINS.items():
        relative = f"linux/{service}/bin/{name}"
        staged = destination / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(launcher, staged)
        staged.chmod(0o755)
        document["services"].append({
            "service": service,
            "runtime": {
                "key": key, "label": f"ROW {service.upper()} launcher", "executable": relative,
                "source": "packaged", "bundled": True, "placeholder": False, "sha256": launcher_digest,
            },
        })
    document["debian_depends"] = debian_dependencies(launcher, (destination / name for name in expected))
    depends = dependency_field(document["debian_depends"])
    (destination / MANIFEST).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return depends


def compare_payload_tar(archive: tarfile.TarFile, expected: dict[str, str]) -> None:
    remaining = set(expected)
    directories = {parent for relative in expected for parent in (PAYLOAD / relative).parents}
    directories.update(LAUNCHER.parents)
    seen_directories = set()
    launcher_digest = None
    for item in archive:
        path = PurePosixPath(item.name)
        if path == LAUNCHER:
            if (
                launcher_digest is not None or not item.isfile()
                or item.uid != 0 or item.gid != 0 or item.mode & 0o7022 or not item.mode & 0o100
                or not 0 < item.size <= SERVER_RUNTIME_MAX_BYTES
            ):
                raise ValueError("Debian embedded server payload requires one native ROW launcher")
            data = archive.extractfile(item)
            if data is None:
                raise ValueError("cannot read the Debian ROW launcher")
            with data:
                launcher_digest = hashlib.file_digest(data, "sha256").hexdigest()
            continue
        if path in directories:
            if not item.isdir() or path in seen_directories or item.uid != 0 or item.gid != 0 or item.mode & 0o7022:
                raise ValueError(f"Debian embedded server payload has an untrusted directory: {path}")
            seen_directories.add(path)
            continue
        if not path.is_relative_to(PAYLOAD):
            continue
        if ".." in path.parts:
            raise ValueError("Debian embedded server payload has an unsafe path")
        relative = path.relative_to(PAYLOAD).as_posix()
        if (
            relative not in remaining or not item.isfile()
            or item.uid != 0 or item.gid != 0 or item.mode & 0o7022
            or not 0 < item.size <= SERVER_RUNTIME_MAX_BYTES
            or (relative != MANIFEST and not item.mode & 0o100)
        ):
            raise ValueError(f"Debian embedded server payload contains an unexpected member: {relative}")
        data = archive.extractfile(item)
        if data is None:
            raise ValueError(f"cannot read packaged server payload: {relative}")
        with data:
            if hashlib.file_digest(data, "sha256").hexdigest() != expected[relative]:
                raise ValueError(f"published Debian daemon or manifest differs from reviewed evidence: {relative}")
        remaining.remove(relative)
    if remaining:
        raise ValueError(f"published Debian package is missing the reviewed server payload members: {sorted(remaining)}")
    if launcher_digest is None or any(
        expected[f"linux/{service}/bin/{name}"] != launcher_digest for service, (_, name) in BUILTINS.items()
    ):
        raise ValueError("published HTTP and FTP runtime bytes must match the Debian ROW launcher")


def verify_debian_payload(package: Path, manifest: Path, target: str) -> None:
    release_deb_version(package.name, target)
    if manifest.name != MANIFEST:
        raise ValueError("reviewed embedded server manifest must be named servers-runtime.json")
    document, expected = server_payload(manifest.parent, target)
    try:
        with TemporaryFile() as payload:
            subprocess.run(
                ["dpkg-deb", "--fsys-tarfile", str(package.resolve())],
                stdout=payload, stderr=subprocess.PIPE, check=True, timeout=120,
            )
            payload.seek(0)
            with tarfile.open(fileobj=payload, mode="r:") as archive:
                compare_payload_tar(archive, expected)
        if "debian_depends" in document:
            depends = subprocess.check_output(
                ["dpkg-deb", "--field", str(package.resolve()), "Depends"], text=True, timeout=30,
            )
            if " ".join(depends.split()) != dependency_field(document["debian_depends"]):
                raise ValueError("published Debian Depends differs from the reviewed server runtime dependencies")
    except (subprocess.SubprocessError, tarfile.TarError) as exc:
        raise ValueError("could not read the published Debian server payload") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--debian-root", type=Path)
    operation.add_argument("--deb", type=Path)
    parser.add_argument("--target", required=True, choices=sorted(ELF_TARGETS))
    args = parser.parse_args()
    if args.deb:
        verify_debian_payload(args.deb, args.bundle / MANIFEST, args.target)
    else:
        print(stage_payload(args.bundle, args.debian_root, args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
