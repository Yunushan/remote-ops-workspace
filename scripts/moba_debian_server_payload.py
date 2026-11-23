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
    SERVER_OPENSSH_HELPERS,
    SERVER_RUNTIME_MAX_BYTES,
    verify_packaged_openssh_helpers,
)
from scripts.check_linux_native_elf import validate_elf  # noqa: E402
from scripts.check_release_license_compliance import secure_regular_file, sha256_file  # noqa: E402
from scripts.debian_native_dependencies import debian_dependencies, dependency_field  # noqa: E402
from scripts.debian_release_fixture import release_deb_version  # noqa: E402
from scripts.debian_server_notices import (  # noqa: E402
    EXTERNAL_SERVICES,
    MANIFEST,
    NOTICE_MAX_BYTES,
    PAYLOAD,
    SCHEMA,
    SHA256_RE,
    notice_path,
    notice_records,
    verify_notice_members,
)
from scripts.release_evidence_file import stream_sha256  # noqa: E402

LAUNCHER = PurePosixPath("usr/bin/row")
ELF_TARGETS = {"linux-x86_64": "x86_64", "linux-arm64": "aarch64", "linux-i386": "i686", "linux-armhf": "armhf"}
SERVICES = frozenset({"http", "ftp", "tftp", "ssh", "sftp", "telnet", "vnc", "nfs"})
BUILTINS = {"http": ("python-http", "python"), "ftp": ("pyftpdlib", "pyftpdlib")}
OPENSSH_DAEMON_KEYS = {"ssh": "sshd", "sftp": "sshd-sftp"}


def private_helper_reference(path: Path, name: str) -> bool:
    reference = f"/{PAYLOAD}/{SERVER_OPENSSH_HELPER_DIR}/{name}".encode("ascii") + b"\x00"
    return reference in path.read_bytes()


def server_manifest(
    raw: bytes, target: str, required: frozenset[str] = SERVICES,
) -> tuple[dict, dict[str, str]]:
    document = json.loads(raw)
    if (
        not isinstance(document, dict) or document.get("schema") != SCHEMA
        or document.get("release_target") != target or document.get("system") != "linux"
        or not isinstance(services := document.get("services"), list) or len(services) != len(required)
    ):
        raise ValueError("embedded server manifest must describe the required services for the exact Linux target")
    digests = {MANIFEST: hashlib.sha256(raw).hexdigest()}
    seen = set()
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
        digest = runtime.get("sha256")
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            raise ValueError(f"{service} daemon has an invalid manifest SHA-256")
        digests[relative] = digest
    if "openssh_helpers" in document:
        helpers = document["openssh_helpers"]
        if not isinstance(helpers, dict) or helpers.keys() != set(SERVER_OPENSSH_HELPERS):
            raise ValueError("OpenSSH helper manifest must record sshd-session and sshd-auth")
        for name, digest in helpers.items():
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise ValueError(f"OpenSSH helper has an invalid SHA-256: {name}")
            digests[f"{SERVER_OPENSSH_HELPER_DIR}/{name}"] = digest
    return document, digests


def reviewed_runtime_sha256(document: dict) -> str:
    """Fingerprint the manifest fields that staging carries into the package."""
    reviewed = {key: value for key, value in document.items() if key != "debian_depends"}
    reviewed["services"] = sorted(
        (row for row in document["services"] if row["service"] in EXTERNAL_SERVICES),
        key=lambda row: row["service"],
    )
    encoded = json.dumps(reviewed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
        raw = stream.read(NOTICE_MAX_BYTES + 1)
    if len(raw) > NOTICE_MAX_BYTES:
        raise ValueError("embedded server manifest exceeds 1 MiB")
    document, digests = server_manifest(raw, target, required)
    private_openssh = {}
    for row in document["services"]:
        service, runtime = row["service"], row["runtime"]
        relative = runtime["executable"]
        executable, error = secure_regular_file(root, relative, f"{service} daemon")
        if executable is None:
            raise ValueError(error)
        if not 0 < executable.stat().st_size <= SERVER_RUNTIME_MAX_BYTES:
            raise ValueError(f"{service} daemon has an invalid size")
        digest = sha256_file(executable)
        if digest != digests[relative]:
            raise ValueError(f"{service} daemon differs from its manifest digest")
        validate_elf(executable, elf)
        if service in OPENSSH_DAEMON_KEYS and private_helper_reference(executable, "sshd-session"):
            if runtime["key"] != OPENSSH_DAEMON_KEYS[service] or executable.name != "sshd":
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
    elif private_openssh:
        raise ValueError("the package-owned OpenSSH helper files must be recorded in the manifest")
    return document, digests


def verify_debian_notice_inputs(root: Path, value: object) -> dict[str, bytes]:
    notices = {}
    for name, row in notice_records(value).items():
        relative = f"notices/{name}.copyright"
        path, error = secure_regular_file(root, relative, "Debian server notice")
        if path is None:
            raise ValueError(error)
        with path.open("rb") as stream:
            data = stream.read(NOTICE_MAX_BYTES + 1)
        if len(data) != row["size_bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError(f"Debian server notice attachment differs from reviewed evidence: {relative}")
        notices[name] = data
    return notices


def stage_payload(source: Path, package_root: Path, target: str) -> str:
    document, expected = server_payload(source, target, EXTERNAL_SERVICES)
    notices = verify_debian_notice_inputs(source, document.get("debian_notices"))
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
    for name, data in notices.items():
        path = package_root / notice_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o644)
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
                launcher_digest = stream_sha256(data)
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
            if stream_sha256(data) != expected[relative]:
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
                if "debian_notices" in document:
                    verify_notice_members(archive, notice_records(document["debian_notices"]))
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
