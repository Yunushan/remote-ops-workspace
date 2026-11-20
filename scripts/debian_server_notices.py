"""Bind distro notices to the exact Debian asset that ships the server suite."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryFile
from typing import Any

PAYLOAD = PurePosixPath("usr/lib/remote-ops-workspace/servers")
MANIFEST = "servers-runtime.json"
SCHEMA = "row.moba-servers.runtime-bundle.v1"
NOTICE_DIR = PurePosixPath("usr/share/doc/remote-ops-workspace/server-notices")
EXTERNAL_SERVICES = frozenset({"tftp", "ssh", "sftp", "telnet", "vnc", "nfs"})
NOTICE_MAX_BYTES = 1024 * 1024
PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9+.-]+")
VERSION_RE = re.compile(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+~-]*")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def notice_records(value: Any) -> dict[str, dict[str, Any]]:
    """Validate the component records and cover each external daemon once."""
    if not isinstance(value, dict) or not value or len(value) > len(EXTERNAL_SERVICES):
        raise ValueError("Debian server bundle requires a distro notice inventory")
    remaining = set(EXTERNAL_SERVICES)
    for name, row in value.items():
        if (
            not isinstance(name, str) or PACKAGE_RE.fullmatch(name) is None
            or not isinstance(row, dict) or set(row) != {"version", "services", "sha256", "size_bytes"}
            or not isinstance(row["version"], str) or VERSION_RE.fullmatch(row["version"]) is None
            or not isinstance(row["sha256"], str) or SHA256_RE.fullmatch(row["sha256"]) is None
            or type(row["size_bytes"]) is not int or not 0 < row["size_bytes"] <= NOTICE_MAX_BYTES
        ):
            raise ValueError(f"invalid Debian server notice record: {name!r}")
        services = row["services"]
        if (
            not isinstance(services, list) or not services
            or not all(isinstance(service, str) for service in services)
            or len(set(services)) != len(services) or not set(services) <= remaining
        ):
            raise ValueError(f"Debian server notice services must be unique and external: {name}")
        remaining.difference_update(services)
    if remaining:
        raise ValueError(f"Debian server notices are missing services: {', '.join(sorted(remaining))}")
    return value


def notice_path(component: str) -> PurePosixPath:
    return NOTICE_DIR / f"{component}.copyright"


def verify_notice_members(archive: tarfile.TarFile, records: dict[str, dict[str, Any]]) -> None:
    expected = {notice_path(name): row for name, row in records.items()}
    directories = {*NOTICE_DIR.parents, NOTICE_DIR}
    seen = set()
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if path in directories:
            if path in seen or not member.isdir() or member.uid or member.gid or member.mode & 0o7022:
                raise ValueError(f"untrusted Debian server notice directory: {path}")
            seen.add(path)
            continue
        if not path.is_relative_to(NOTICE_DIR):
            continue
        if (
            path in seen or path not in expected or not member.isfile()
            or member.uid or member.gid or member.mode & 0o7133
        ):
            raise ValueError(f"unexpected member in the Debian server notice directory: {path}")
        seen.add(path)
        row = expected[path]
        if member.size != row["size_bytes"]:
            raise ValueError(f"Debian server notice size differs from reviewed evidence: {path}")
        data = archive.extractfile(member)
        if data is None:
            raise ValueError(f"cannot read Debian server notice: {path}")
        with data:
            if hashlib.file_digest(data, "sha256").hexdigest() != row["sha256"]:
                raise ValueError(f"Debian server notice differs from reviewed evidence: {path}")
    if missing := set(expected) - seen:
        raise ValueError(f"Debian package is missing reviewed server notices: {', '.join(map(str, sorted(missing)))}")


def read_verified_debian_notices(
    package: Path, *, target: str, verify_runtime: bool = False,
) -> dict[str, dict[str, Any]]:
    """Verify notices and optionally the recorded server runtime in a Debian asset."""
    try:
        with TemporaryFile() as payload:
            subprocess.run(
                ["dpkg-deb", "--fsys-tarfile", str(package.resolve())],
                stdout=payload, stderr=subprocess.PIPE, check=True, timeout=120,
            )
            payload.seek(0)
            with tarfile.open(fileobj=payload, mode="r:") as archive:
                members = [(PurePosixPath(member.name), member) for member in archive.getmembers()]
                embedded = [member for path, member in members if path == PAYLOAD / MANIFEST]
                if not embedded and not any(
                    path.is_relative_to(PAYLOAD) or path.is_relative_to(NOTICE_DIR) for path, _ in members
                ):
                    return {}
                if (
                    len(embedded) != 1 or not embedded[0].isfile()
                    or embedded[0].uid or embedded[0].gid or embedded[0].mode & 0o7022
                    or not 0 < embedded[0].size <= NOTICE_MAX_BYTES
                ):
                    raise ValueError("Debian embedded server payload requires a regular runtime manifest")
                stream = archive.extractfile(embedded[0])
                if stream is None:
                    raise ValueError("cannot read the Debian embedded server manifest")
                with stream:
                    raw = stream.read()
                if verify_runtime:
                    # The payload verifier also uses the notice reader's archive checks.
                    from scripts.moba_debian_server_payload import (
                        compare_payload_tar,
                        server_manifest,
                    )

                    document, expected = server_manifest(raw, target)
                    compare_payload_tar(archive, expected)
                else:
                    document = json.loads(raw)
                    if (
                        not isinstance(document, dict) or document.get("schema") != SCHEMA
                        or document.get("system") != "linux" or document.get("release_target") != target
                    ):
                        raise ValueError("invalid Debian embedded server manifest")
                records = notice_records(document.get("debian_notices"))
                verify_notice_members(archive, records)
                return records
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        raise ValueError("could not read Debian server notices from the package") from exc
