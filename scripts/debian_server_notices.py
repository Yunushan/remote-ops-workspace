"""Bind bundled distro notices to the exact Debian asset that ships them."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath
from tempfile import TemporaryFile
from typing import Any, NamedTuple

PAYLOAD = PurePosixPath("usr/lib/remote-ops-workspace/servers")
MANIFEST = "servers-runtime.json"
SCHEMA = "row.moba-servers.runtime-bundle.v1"
NOTICE_DIR = PurePosixPath("usr/share/doc/remote-ops-workspace/server-notices")
MOBAPT_NOTICE_DIR = PurePosixPath("usr/share/doc/remote-ops-workspace/mobapt-notices")
MOBAPT_CACHE_DIR = PurePosixPath("usr/lib/remote-ops-workspace/mobapt")
MOBAPT_REVIEW = "mobapt-debian-review.json"
MOBAPT_ASSEMBLY = "mobapt-cache-evidence.json"
EXTERNAL_SERVICES = frozenset({"tftp", "ssh", "sftp", "telnet", "vnc", "nfs"})
OPTIONAL_EXTERNAL_SERVICES = frozenset({"iperf"})
NOTICE_MAX_BYTES = 1024 * 1024
PACKAGE_RE = re.compile(r"[a-z0-9][a-z0-9+.-]+")
VERSION_RE = re.compile(r"(?:[0-9]+:)?[0-9][A-Za-z0-9.+~-]*")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class DebianNotice(NamedTuple):
    record: dict[str, Any]
    data: bytes


def observe_mobapt_notices(archive: tarfile.TarFile, release_tag: str) -> dict[str, DebianNotice]:
    members = [(PurePosixPath(entry.name), entry) for entry in archive.getmembers()]
    notice_members = [(path, entry) for path, entry in members if path.is_relative_to(MOBAPT_NOTICE_DIR)]
    if not notice_members and not any(path.is_relative_to(MOBAPT_CACHE_DIR) for path, _ in members):
        return {}

    def read_member(path: PurePosixPath) -> bytes:
        matches = [entry for name, entry in members if name == path]
        if len(matches) != 1:
            raise ValueError(f"Debian MobApt requires one packaged file at {path}")
        entry = matches[0]
        if (not entry.isfile() or entry.sparse is not None or entry.uid or entry.gid
                or entry.mode & 0o7133 or not 0 < entry.size <= NOTICE_MAX_BYTES):
            raise ValueError(f"invalid Debian MobApt file: {path}")
        stream = archive.extractfile(entry)
        if stream is None:
            raise ValueError(f"unreadable Debian MobApt file: {path}")
        with stream:
            return stream.read()

    review_path = MOBAPT_NOTICE_DIR / MOBAPT_REVIEW
    review = json.loads(read_member(review_path))
    assembly = read_member(MOBAPT_CACHE_DIR / MOBAPT_ASSEMBLY)
    if (
        not isinstance(review, dict) or review.get("release_tag") != release_tag
        or review.get("assembly_sha256") != hashlib.sha256(assembly).hexdigest()
        or not isinstance(inputs := review.get("debian_inputs"), dict) or not inputs
        or not isinstance(notice_digests := review.get("notices"), dict)
        or notice_digests.keys() != {f"{name}.copyright" for name in inputs}
    ):
        raise ValueError("invalid packaged MobApt Debian review or assembly binding")

    notices = {}
    allowed_directories = {MOBAPT_NOTICE_DIR}
    allowed_files = {review_path}
    for name, row in inputs.items():
        if (
            PACKAGE_RE.fullmatch(name) is None or not isinstance(row, dict)
            or not isinstance(version := row.get("version"), str) or VERSION_RE.fullmatch(version) is None
        ):
            raise ValueError("invalid packaged MobApt Debian component or version")
        directory = MOBAPT_NOTICE_DIR / name
        path = directory / "copyright"
        data = read_member(path)
        digest = hashlib.sha256(data).hexdigest()
        if digest != notice_digests[f"{name}.copyright"]:
            raise ValueError(f"packaged MobApt notice differs from its review: {name}")
        notices[name] = DebianNotice(
            {"path": path.as_posix(), "version": version, "sha256": digest, "size_bytes": len(data)}, data,
        )
        allowed_directories.add(directory)
        allowed_files.add(path)
    seen = set()
    for path, entry in notice_members:
        if path in seen or (
            path not in allowed_files
            and (path not in allowed_directories or not entry.isdir() or entry.uid or entry.gid or entry.mode & 0o7022)
        ):
            raise ValueError(f"unexpected Debian MobApt notice member: {path}")
        seen.add(path)
    return notices


def optional_external_services(services: object) -> frozenset[str]:
    if not isinstance(services, list):
        return frozenset()
    return frozenset(
        row["service"] for row in services
        if isinstance(row, dict) and isinstance(row.get("service"), str)
        and row["service"] in OPTIONAL_EXTERNAL_SERVICES
    )


def notice_records(manifest: dict) -> dict[str, dict[str, Any]]:
    """Validate the component records and cover each external daemon once."""
    remaining = set(EXTERNAL_SERVICES | optional_external_services(manifest.get("services")))
    value = manifest.get("debian_notices")
    if not isinstance(value, dict) or not value or len(value) > len(remaining):
        raise ValueError("Debian server bundle requires a distro notice inventory")
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


def verify_notice_members(archive: tarfile.TarFile, records: dict[str, dict[str, Any]]) -> dict[PurePosixPath, bytes]:
    expected = {notice_path(name): row for name, row in records.items()}
    directories = {*NOTICE_DIR.parents, NOTICE_DIR}
    seen = set()
    contents = {}
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
            raw = data.read()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Debian server notice differs from reviewed evidence: {path}")
        contents[path] = raw
    if missing := set(expected) - seen:
        raise ValueError(f"Debian package is missing reviewed server notices: {', '.join(map(str, sorted(missing)))}")
    return contents


def observe_debian_notices(
    archive: tarfile.TarFile,
    *,
    target: str,
    verify_runtime: bool = False,
    expected_runtime_sha256: str | None = None,
) -> dict[str, DebianNotice]:
    """Return the verified records and bytes from an opened Debian filesystem tar."""
    members = [(PurePosixPath(member.name), member) for member in archive.getmembers()]
    embedded = [member for path, member in members if path == PAYLOAD / MANIFEST]
    if not embedded and not any(
        path.is_relative_to(PAYLOAD) or path.is_relative_to(NOTICE_DIR) for path, _ in members
    ):
        if expected_runtime_sha256 is not None:
            raise ValueError("candidate Debian package is missing the reviewed server payload")
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
    if verify_runtime or expected_runtime_sha256 is not None:
        # The payload verifier also uses the notice reader's archive checks.
        from scripts.moba_debian_server_payload import (
            compare_payload_tar,
            reviewed_runtime_sha256,
            server_manifest,
        )

        document, expected = server_manifest(raw, target)
        if expected_runtime_sha256 is not None and reviewed_runtime_sha256(document) != expected_runtime_sha256:
            raise ValueError("candidate Debian server payload differs from the reviewed archive")
        compare_payload_tar(archive, expected)
    else:
        document = json.loads(raw)
        if (
            not isinstance(document, dict) or document.get("schema") != SCHEMA
            or document.get("system") != "linux" or document.get("release_target") != target
        ):
            raise ValueError("invalid Debian embedded server manifest")
    records = notice_records(document)
    contents = verify_notice_members(archive, records)
    return {name: DebianNotice(row, contents[notice_path(name)]) for name, row in records.items()}


def read_verified_debian_notices(
    package: Path, *, target: str, verify_runtime: bool = False, expected_runtime_sha256: str | None = None,
    mobapt_release_tag: str | None = None,
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
                notices = observe_debian_notices(
                    archive, target=target, verify_runtime=verify_runtime, expected_runtime_sha256=expected_runtime_sha256,
                )
                if mobapt_release_tag is not None:
                    mobapt = observe_mobapt_notices(archive, mobapt_release_tag)
                    if notices.keys() & mobapt.keys():
                        raise ValueError("Debian server and MobApt notice component names overlap")
                    notices.update(mobapt)
                return {name: notice.record for name, notice in notices.items()}
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as exc:
        raise ValueError("could not read Debian notices from the package") from exc
