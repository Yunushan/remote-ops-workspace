"""Unsigned runtime observations for independent compliance review.

No native binary, installer, archive command or package code is executed.
The CLI consumes the existing candidate finish receipt after its creation.
Opaque formats remain explicit gaps. See docs/UNSIGNED_RUNTIME_OBSERVATIONS.md.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import email.parser
import gzip
import hashlib
import io
import json
import lzma
import os
import platform
import re
import stat
import struct
import sys
import sysconfig
import tarfile
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

SCHEMA = "row.unsigned-runtime-observations.v1"
TARGETS = {
    "windows-x86",
    "windows-x64",
    "windows-arm64",
    "macos-x64",
    "macos-arm64",
    "linux-x86_64",
    "linux-aarch64",
}
HEX = re.compile(r"[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"[0-9]+(?:\.[A-Za-z0-9]+)*(?:[-+][A-Za-z0-9.]+)?\Z")
COOKIE = b"MEI\014\013\012\013\016"
PE_MAGICS = (
    b"\xfe\xed\xfa\xce",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
)


class Refusal(ValueError):
    """Only literal error codes are exposed; paths/private metadata stay in evidence."""


@dataclass(frozen=True)
class Limits:
    json_bytes: int = 16 * 1024 * 1024
    input_bytes: int = 512 * 1024 * 1024
    expanded_bytes: int = 1024 * 1024 * 1024
    member_bytes: int = 256 * 1024 * 1024
    license_bytes: int = 4 * 1024 * 1024
    retained_license_bytes: int = 64 * 1024 * 1024
    members: int = 100000
    distributions: int = 512
    metadata_bytes: int = 4 * 1024 * 1024
    source_files: int = 15000
    archive_depth: int = 2
    aggregate_input_bytes: int = 2 * 1024 * 1024 * 1024
    gaps: int = 4096


DEFAULT_LIMITS = Limits()
GLOBAL_BOUNDS = {
    "global-inventory-node-bound",
    "global-gap-count-bound",
    "expanded-byte-bound",
    "member-bound",
    "retained-license-byte-bound",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def integer(value: object, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def relative(raw: object, *, archive: bool = False) -> str:
    if not isinstance(raw, str) or not raw or len(raw) > 1024:
        raise Refusal("path-invalid")
    if archive:
        while raw.startswith("./"):
            raw = raw[2:]
        raw = raw.rstrip("/")
    if (
        not raw
        or raw != raw.strip()
        or "\\" in raw
        or ":" in raw
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        raise Refusal("path-invalid")
    parts = raw.split("/")
    if len(parts) > 64 or any(p in ("", ".", "..") for p in parts):
        raise Refusal("path-invalid")
    if PurePosixPath(raw).is_absolute():
        raise Refusal("path-invalid")
    # Windows device/trailing-dot aliases must not become evidence output names.
    for part in parts:
        stem = part.split(".", 1)[0].casefold()
        if (
            part.endswith((" ", "."))
            or stem in {"con", "prn", "aux", "nul"}
            or re.fullmatch(r"(?:com|lpt)[1-9]", stem)
        ):
            raise Refusal("path-invalid")
    return raw


def receipt_relative(raw: object, target: str) -> str:
    """Normalize only typed Windows receipt separators, never archive/output paths."""
    if isinstance(raw, str) and "\\" in raw:
        if not target.startswith("windows-") or "/" in raw:
            raise Refusal("receipt-path-separator-invalid")
        raw = raw.replace("\\", "/")
    return relative(raw)


def plain(path: Path, *, directory: bool = False) -> os.stat_result:
    # Inspect every ancestor before resolving; a junction is not an ordinary path.
    for item in reversed((path, *path.parents)):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise Refusal("reparse-input")
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise Refusal("input-kind-invalid")
    return info


def child(root: Path, name: object, *, directory: bool = False) -> Path:
    path = root.joinpath(*relative(name).split("/"))
    plain(path, directory=directory)
    if not path.resolve().is_relative_to(root.resolve()):
        raise Refusal("input-root-escape")
    return path


def read(path: Path, maximum: int) -> bytes:
    before = plain(path)
    if before.st_size > maximum:
        raise Refusal("input-byte-bound")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise Refusal("input-changed")
        raw = stream.read(maximum + 1)
    after = plain(path)
    if len(raw) != before.st_size or (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise Refusal("input-changed")
    return raw


def load(raw: bytes, *, array: bool = False) -> dict | list:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal("json-duplicate-key")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Refusal("json-invalid") from exc
    if not isinstance(value, list if array else dict):
        raise Refusal("json-array-required" if array else "json-object-required")
    return value


def decompressed(raw: bytes, method: str, maximum: int) -> bytes:
    if method == "gzip":
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            result = stream.read(maximum + 1)
    elif method == "xz":
        decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
        result = decoder.decompress(raw, max_length=maximum + 1)
        if not decoder.eof or decoder.unused_data:
            raise Refusal("compressed-bound-or-trailing-data")
    elif method == "bzip2":
        decoder = bz2.BZ2Decompressor()
        result = decoder.decompress(raw, max_length=maximum + 1)
        if not decoder.eof or decoder.unused_data:
            raise Refusal("compressed-bound-or-trailing-data")
    elif method == "zlib":
        decoder = zlib.decompressobj()
        result = decoder.decompress(raw, maximum + 1)
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise Refusal("compressed-bound-or-trailing-data")
    else:
        raise Refusal("compression-backend-unobserved")
    if len(result) > maximum:
        raise Refusal("expanded-byte-bound")
    return result


def license_name(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return any(
        re.search(
            r"(?i)(?:^|[-_.])(?:licen[sc]es?|copying|copyright|notices?|legal|exceptions)(?:[-_.]|$)",
            p,
        )
        for p in parts
    )


def native_kind(raw: bytes) -> str | None:
    if raw.startswith(b"\x7fELF"):
        return "ELF"
    if raw.startswith(b"MZ"):
        return "PE-candidate"
    if raw[:4] in PE_MAGICS:
        return "Mach-O-candidate"
    return None


class Observations:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.blobs: dict[str, bytes] = {}
        self.files: list[dict] = []
        self.licenses: dict[str, list[dict]] = {}
        self.gaps: list[dict] = []
        self.expanded = 0
        self.nodes = 0

    def node(self):
        self.nodes += 1
        if self.nodes > self.limits.members:
            raise Refusal("global-inventory-node-bound")

    def gap(self, code: str, reference: str):
        if len(self.gaps) >= self.limits.gaps:
            raise Refusal("global-gap-count-bound")
        self.gaps.append({"code": code, "reference": reference})

    def observe(self, name: str, raw: bytes, reference: str, *, package: str | None = None) -> dict:
        name = relative(name)
        if len(self.files) >= self.limits.members or len(raw) > self.limits.member_bytes:
            raise Refusal("member-bound")
        self.expanded += len(raw)
        if self.expanded > self.limits.expanded_bytes:
            raise Refusal("expanded-byte-bound")
        row = {"path": name, "reference": reference, "size_bytes": len(raw), "sha256": digest(raw)}
        kind = native_kind(raw)
        if kind:
            row["native_format_observation"] = kind
            row["component_identity"] = "unknown"
            row["exact_component_version"] = None
        self.files.append(row)
        if license_name(name):
            if not raw:
                self.gap("empty-license-material", reference)
            elif len(raw) > self.limits.license_bytes:
                self.gap("license-material-bound", reference)
            else:
                sha = digest(raw)
                if sha not in self.blobs:
                    if (
                        sum(map(len, self.blobs.values())) + len(raw)
                        > self.limits.retained_license_bytes
                    ):
                        raise Refusal("retained-license-byte-bound")
                    self.blobs[sha] = raw
                record = {
                    "path": name,
                    "file": f"files/licenses/{sha}.bin",
                    "size_bytes": len(raw),
                    "sha256": sha,
                }
                self.licenses.setdefault(package or reference, []).append(record)
        return row


def scan_carchive(raw: bytes, label: str, observations: Observations, depth: int = 0):
    # Parse the documented PyInstaller2.1 cookie/TOC without importing package code.
    offset = raw.rfind(COOKIE, max(0, len(raw) - 131072))
    if offset < 0:
        return False
    if len(raw) < offset + 88:
        raise Refusal("carchive-cookie-invalid")
    magic, package_len, toc_offset, toc_len, python_code, library = struct.unpack(
        "!8sIIII64s", raw[offset : offset + 88]
    )
    start = offset + 88 - package_len
    toc_start = start + toc_offset
    if (
        magic != COOKIE
        or start < 0
        or toc_len > observations.limits.json_bytes
        or not start <= toc_start <= toc_start + toc_len <= offset
    ):
        raise Refusal("carchive-cookie-invalid")
    cursor, seen = toc_start, set()
    while cursor < toc_start + toc_len:
        observations.node()
        if cursor + 18 > toc_start + toc_len:
            raise Refusal("carchive-toc-invalid")
        length, position, stored, size, compression, kind = struct.unpack(
            "!iIIIBc", raw[cursor : cursor + 18]
        )
        if length < 19 or cursor + length > toc_start + toc_len or compression not in (0, 1):
            raise Refusal("carchive-toc-invalid")
        encoded = raw[cursor + 18 : cursor + length].rstrip(b"\0")
        if b"\0" in encoded:
            raise Refusal("carchive-name-invalid")
        try:
            name = encoded.decode("utf-8")
        except UnicodeError as exc:
            raise Refusal("carchive-name-invalid") from exc
        cursor += length
        if kind == b"o":
            observations.gap("carchive-runtime-option-unclassified", label)
            continue
        name = relative(name)
        if name.casefold() in seen:
            raise Refusal("duplicate-member")
        seen.add(name.casefold())
        if (
            size > observations.limits.member_bytes
            or stored > observations.limits.input_bytes
            or start + position < start
            or start + position + stored > toc_start
        ):
            raise Refusal("carchive-member-bound")
        if kind in (b"n", b"d"):
            observations.gap("carchive-indirection-unobserved", f"{label}::{name}")
            continue
        payload = raw[start + position : start + position + stored]
        data = decompressed(payload, "zlib", size) if compression else payload
        if len(data) != size:
            raise Refusal("carchive-member-size-mismatch")
        observations.observe(
            f"carchive/{name}", data, f"{label}::{name}", package=label.split("::", 1)[0]
        )
        if kind in (b"z", b"Z"):
            observations.gap("pyz-module-ownership-unclassified", f"{label}::{name}")
    observations.gap("bootloader-version-and-runtime-closure-unverified", label)
    return {
        "python_cookie_code_observed": python_code,
        "python_library_name_observed": library.split(b"\0", 1)[0].decode(
            "utf-8", errors="replace"
        ),
    }


def checked_members(entries, observations: Observations):
    seen = set()
    count = 0
    total = 0
    for name, size, regular, data in entries:
        observations.node()
        count += 1
        if count > observations.limits.members:
            raise Refusal("member-count-bound")
        name = relative(name, archive=True)
        if name.casefold() in seen:
            raise Refusal("duplicate-member")
        seen.add(name.casefold())
        if not integer(size) or size > observations.limits.member_bytes:
            raise Refusal("member-byte-bound")
        total += size
        if total > observations.limits.expanded_bytes:
            raise Refusal("expanded-byte-bound")
        if not regular:
            if data is None:  # directory
                continue
            raise Refusal("link-or-special-member")
        raw = data()
        if len(raw) != size:
            raise Refusal("member-size-mismatch")
        yield name, raw


def zip_members(raw: bytes, observations: Observations):
    end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    if end < 0 or end + 22 > len(raw):
        raise Refusal("zip-directory-invalid")
    _, disk, start_disk, disk_count, count, directory_size, directory_offset, comment = (
        struct.unpack("<4s4H2IH", raw[end : end + 22])
    )
    if (
        disk
        or start_disk
        or count != disk_count
        or count == 65535
        or count > observations.limits.members
        or directory_size > observations.limits.json_bytes
        or directory_offset + directory_size != end
        or end + 22 + comment != len(raw)
    ):
        raise Refusal("zip-directory-bound-or-zip64-unobserved")

    def extras(raw_extra):
        position = 0
        seen = set()
        while position < len(raw_extra):
            observations.node()
            if position + 4 > len(raw_extra):
                raise Refusal("zip-extra-invalid")
            kind, length = struct.unpack("<HH", raw_extra[position : position + 4])
            position += 4 + length
            # Only inert timestamp/uid/gid metadata is observed. ZIP64,
            # Unicode alias names and Unix link extras remain unobserved.
            if kind not in {0x000A, 0x5455, 0x5855, 0x7875} or kind in seen or length > 64:
                raise Refusal("zip-extra-semantics-unobserved")
            seen.add(kind)
            if position > len(raw_extra):
                raise Refusal("zip-extra-invalid")

    cursor, entries, spans = directory_offset, [], []
    directory_end = directory_offset + directory_size
    while cursor < directory_end:
        observations.node()
        if cursor + 46 > directory_end:
            raise Refusal("zip-directory-invalid")
        header = struct.unpack("<4s6H3I5H2I", raw[cursor : cursor + 46])
        (
            signature,
            _made,
            needed,
            flags,
            method,
            mtime,
            mdate,
            crc,
            stored,
            size,
            name_size,
            extra_size,
            comment_size,
            disk_start,
            _internal,
            external,
            offset,
        ) = header
        next_cursor = cursor + 46 + name_size + extra_size + comment_size
        if (
            signature != b"PK\x01\x02"
            or next_cursor > directory_end
            or disk_start
            or len(entries) >= observations.limits.members
            or name_size > 1024
        ):
            raise Refusal("zip-directory-count-or-entry-invalid")
        if flags & ~0x808 or method not in (0, 8) or needed > 20:
            raise Refusal("zip-codec-or-flags-unobserved")
        encoded = raw[cursor + 46 : cursor + 46 + name_size]
        name = encoded.decode("utf-8" if flags & 0x800 else "cp437")
        relative(name, archive=True)
        extra = raw[cursor + 46 + name_size : cursor + 46 + name_size + extra_size]
        extras(extra)
        if offset + 30 > directory_offset:
            raise Refusal("zip-local-offset-invalid")
        local = struct.unpack("<4s5H3I2H", raw[offset : offset + 30])
        (
            local_sig,
            local_needed,
            local_flags,
            local_method,
            local_time,
            local_date,
            local_crc,
            local_stored,
            local_size,
            local_name,
            local_extra,
        ) = local
        data_start = offset + 30 + local_name + local_extra
        data_end = data_start + stored
        if (
            local_sig != b"PK\x03\x04"
            or (local_needed, local_flags, local_method, local_time, local_date)
            != (needed, flags, method, mtime, mdate)
            or local_name != name_size
            or raw[offset + 30 : offset + 30 + local_name] != encoded
            or data_end > directory_offset
        ):
            raise Refusal("zip-local-central-metadata-mismatch")
        extras(raw[offset + 30 + local_name : data_start])
        span_end = data_end
        if flags & 8:
            if (
                local_crc not in (0, crc)
                or local_stored not in (0, stored)
                or local_size not in (0, size)
            ):
                raise Refusal("zip-local-central-metadata-mismatch")
            descriptor_start = data_end + (
                4 if raw[data_end : data_end + 4] == b"PK\x07\x08" else 0
            )
            span_end = descriptor_start + 12
            if span_end > directory_offset or struct.unpack(
                "<III", raw[descriptor_start:span_end]
            ) != (crc, stored, size):
                raise Refusal("zip-descriptor-invalid")
        elif (local_crc, local_stored, local_size) != (crc, stored, size):
            raise Refusal("zip-local-central-metadata-mismatch")
        mode = external >> 16
        directory = name.endswith("/")
        kind = stat.S_IFMT(mode)
        if (
            kind not in (0, stat.S_IFREG, stat.S_IFDIR)
            or (directory and kind == stat.S_IFREG)
            or (not directory and kind == stat.S_IFDIR)
        ):
            raise Refusal("link-or-special-member")
        if directory and (stored or size):
            raise Refusal("zip-directory-payload-invalid")
        if method == 0 and stored != size:
            raise Refusal("zip-stored-size-mismatch")

        def payload(start=data_start, end=data_end, method=method, size=size, crc=crc):
            data = raw[start:end]
            if method == 8:
                decoder = zlib.decompressobj(-15)
                data = decoder.decompress(data, size + 1)
                if not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
                    raise Refusal("zip-deflate-bound-or-trailing-data")
            if len(data) != size or zlib.crc32(data) & 0xFFFFFFFF != crc:
                raise Refusal("zip-expanded-size-or-crc-mismatch")
            return data

        entries.append((name, size, not directory, None if directory else payload))
        spans.append((offset, span_end))
        cursor = next_cursor
    if len(entries) != count or cursor != directory_end:
        raise Refusal("zip-directory-count-mismatch")
    expected = 0
    for start, stop in sorted(spans):
        if start != expected:
            raise Refusal("zip-overlap-or-unaccounted-local-bytes")
        expected = stop
    if expected != directory_offset:
        raise Refusal("zip-overlap-or-unaccounted-local-bytes")
    yield from checked_members(entries, observations)


def tar_members(raw: bytes, observations: Observations):
    if raw.startswith(b"\x1f\x8b"):
        raw = decompressed(raw, "gzip", observations.limits.expanded_bytes)
    elif raw.startswith(b"\xfd7zXZ\0"):
        raw = decompressed(raw, "xz", observations.limits.expanded_bytes)
    elif raw.startswith(b"BZh"):
        raw = decompressed(raw, "bzip2", observations.limits.expanded_bytes)

    # tarfile intentionally hides GNU/PAX metadata and stops at the first end
    # block. Inspect plain raw headers so those bytes cannot masquerade as a
    # completely observed payload or conceal a second archive.
    def number(field):
        field = field.rstrip(b"\0 ").lstrip(b" ")
        if not field:
            return 0
        if any(c not in b"01234567" for c in field):
            raise Refusal("tar-numeric-metadata-unobserved")
        return int(field, 8)

    def text(field):
        encoded = field.rstrip(b"\0")
        if b"\0" in encoded:
            raise Refusal("tar-name-invalid")
        return encoded.decode("utf-8")

    def entries():
        cursor = 0
        if len(raw) % 512:
            raise Refusal("tar-block-size-invalid")
        while cursor + 512 <= len(raw):
            block = raw[cursor : cursor + 512]
            if block == b"\0" * 512:
                if cursor + 1024 > len(raw) or any(raw[cursor:]):
                    raise Refusal("tar-trailing-or-end-block-invalid")
                return
            observations.node()
            if number(block[148:156]) != sum(block[:148]) + 8 * 32 + sum(block[156:]):
                raise Refusal("tar-header-checksum-invalid")
            kind, size = block[156:157], number(block[124:136])
            if kind in (b"x", b"g", b"L", b"K", b"S"):
                raise Refusal("tar-extended-metadata-unobserved")
            if block[257:263] not in (b"ustar\0", b"ustar ", b"\0" * 6):
                raise Refusal("tar-format-unobserved")
            name, prefix = text(block[:100]), text(block[345:500])
            if prefix:
                name = f"{prefix}/{name}"
            start, end = cursor + 512, cursor + 512 + size
            padded_end = (end + 511) // 512 * 512
            if end > len(raw) or padded_end > len(raw) or any(raw[end:padded_end]):
                raise Refusal("tar-payload-or-padding-invalid")
            cursor = padded_end
            if name in (".", "./") and kind == b"5" and size == 0:
                continue
            directory = kind == b"5"
            regular = kind in (b"0", b"\0")
            if block[157:257].rstrip(b"\0") or (directory and size):
                raise Refusal("link-or-special-member")
            yield (
                name,
                size,
                regular,
                None if directory else lambda start=start, end=end: raw[start:end],
            )
        raise Refusal("tar-end-block-missing")

    yield from checked_members(entries(), observations)


def deb_tar(raw: bytes, observations: Observations) -> bytes:
    if not raw.startswith(b"!<arch>\n"):
        raise Refusal("deb-ar-invalid")
    cursor, data, names = 8, None, set()
    while cursor < len(raw):
        observations.node()
        if cursor + 60 > len(raw):
            raise Refusal("deb-ar-invalid")
        header = raw[cursor : cursor + 60]
        if header[58:] != b"`\n":
            raise Refusal("deb-ar-invalid")
        try:
            name = header[:16].decode("ascii").rstrip(" /")
            size = int(header[48:58].decode("ascii").strip())
        except (UnicodeError, ValueError) as exc:
            raise Refusal("deb-ar-invalid") from exc
        if size < 0 or name in names or cursor + 60 + size > len(raw):
            raise Refusal("deb-ar-invalid")
        names.add(name)
        relative(name)
        payload = raw[cursor + 60 : cursor + 60 + size]
        if name.startswith("data.tar"):
            if data is not None:
                raise Refusal("deb-data-duplicate")
            data = payload
        elif name == "debian-binary" and payload != b"2.0\n":
            raise Refusal("deb-version-invalid")
        end = cursor + 60 + size
        if size % 2 and raw[end : end + 1] != b"\n":
            raise Refusal("deb-ar-padding-invalid")
        cursor = end + size % 2
    if data is None or "debian-binary" not in names:
        raise Refusal("deb-data-missing")
    return data


def rpm_payload(raw: bytes, limits: Limits) -> bytes:
    if not raw.startswith(b"\xed\xab\xee\xdb") or len(raw) < 112:
        raise Refusal("rpm-lead-invalid")

    def header(offset):
        if raw[offset : offset + 4] != b"\x8e\xad\xe8\x01" or offset + 16 > len(raw):
            raise Refusal("rpm-header-invalid")
        count, size = struct.unpack("!II", raw[offset + 8 : offset + 16])
        end = offset + 16 + count * 16 + size
        if count > 65536 or size > limits.json_bytes or end > len(raw):
            raise Refusal("rpm-header-bound")
        records = {}
        store = offset + 16 + count * 16
        for index in range(count):
            tag, kind, position, number = struct.unpack(
                "!IIII", raw[offset + 16 + index * 16 : offset + 32 + index * 16]
            )
            if tag in records or position >= size:
                raise Refusal("rpm-header-invalid")
            records[tag] = (kind, number, raw[store + position : store + size].split(b"\0", 1)[0])
        return end, records

    signature_end, _ = header(96)
    end, records = header((signature_end + 7) & ~7)
    if records.get(1124) != (6, 1, b"cpio"):
        raise Refusal("rpm-payload-format-unobserved")
    method = records.get(1125)
    if method is None or method[:2] != (6, 1):
        raise Refusal("rpm-payload-codec-unobserved")
    codec = {b"gzip": "gzip", b"xz": "xz", b"bzip2": "bzip2"}.get(method[2])
    if codec is None:
        raise Refusal("rpm-payload-codec-unobserved")
    return decompressed(raw[end:], codec, limits.expanded_bytes)


def cpio_members(raw: bytes, observations: Observations):
    def entries():
        cursor = 0
        while cursor < len(raw):
            if raw[cursor : cursor + 6] != b"070701" or cursor + 110 > len(raw):
                raise Refusal("cpio-header-invalid")
            try:
                values = [int(raw[cursor + 6 + n * 8 : cursor + 14 + n * 8], 16) for n in range(13)]
            except ValueError as exc:
                raise Refusal("cpio-header-invalid") from exc
            mode, links, size, name_size = values[1], values[4], values[6], values[11]
            name_start = cursor + 110
            if not 1 <= name_size <= 1025 or name_start + name_size > len(raw):
                raise Refusal("cpio-name-bound")
            encoded = raw[name_start : name_start + name_size]
            if encoded[-1:] != b"\0" or b"\0" in encoded[:-1]:
                raise Refusal("cpio-name-invalid")
            try:
                name = encoded[:-1].decode("utf-8")
            except UnicodeError as exc:
                raise Refusal("cpio-name-invalid") from exc
            start = (name_start + name_size + 3) & ~3
            end = start + size
            if end > len(raw):
                raise Refusal("cpio-payload-invalid")
            cursor = (end + 3) & ~3
            if name == "TRAILER!!!":
                if size or any(raw[cursor:]):
                    raise Refusal("cpio-trailer-invalid")
                return
            if links > 1 and stat.S_ISREG(mode):
                raise Refusal("cpio-hardlink-unobserved")
            yield (
                name,
                size,
                stat.S_ISREG(mode),
                None if stat.S_ISDIR(mode) else lambda start=start, end=end: raw[start:end],
            )
        raise Refusal("cpio-trailer-missing")

    yield from checked_members(entries(), observations)


def scan_package(raw: bytes, name: str, observations: Observations):
    if raw.startswith(b"PK\x03\x04"):
        entries = zip_members(raw, observations)
        backend = "bounded-zip32-deflate"
    elif name.endswith((".tar", ".tar.gz", ".tar.xz", ".tgz")):
        entries = tar_members(raw, observations)
        backend = "bounded-tar"
    elif name.endswith(".deb"):
        entries = tar_members(deb_tar(raw, observations), observations)
        backend = "ar-data-tar"
    elif name.endswith(".rpm"):
        entries = cpio_members(rpm_payload(raw, observations.limits), observations)
        backend = "rpm-header-cpio"
    else:
        observations.gap("opaque-package-format-unobserved", name)
        return {"backend": None, "all_regular_payload_files_observed": False, "license_records": []}
    start = len(observations.files)
    for member, data in entries:
        observations.observe(member, data, f"{name}::{member}", package=name)
        if native_kind(data):
            scan_carchive(data, f"{name}::{member}", observations)
    return {
        "backend": backend,
        "all_regular_payload_files_observed": True,
        "observed_file_count": len(observations.files) - start,
        "license_records": observations.licenses.get(name, []),
    }


def inspect_distributions(
    raw: bytes, limits: Limits, source_root: Path | None = None
) -> list[dict]:
    payload = load(raw)
    if set(payload) - {"version", "pip_version", "installed", "environment"}:
        raise Refusal("pip-public-schema-unrecognized")
    environment = payload.get("environment", {})
    if not isinstance(environment, dict) or set(environment) - {
        "implementation_name",
        "implementation_version",
        "os_name",
        "platform_machine",
        "platform_python_implementation",
        "platform_release",
        "platform_system",
        "platform_version",
        "python_full_version",
        "python_version",
        "sys_platform",
    }:
        raise Refusal("pip-public-schema-unrecognized")
    installed = payload.get("installed")
    if (
        payload.get("version") != "1"
        or not isinstance(installed, list)
        or not 1 <= len(installed) <= limits.distributions
    ):
        raise Refusal("pip-inspect-shape-invalid")
    result, seen = [], set()
    metadata_fields = {
        "metadata_version",
        "name",
        "version",
        "summary",
        "description",
        "description_content_type",
        "keywords",
        "home_page",
        "download_url",
        "author",
        "author_email",
        "maintainer",
        "maintainer_email",
        "license",
        "license_expression",
        "license_file",
        "classifier",
        "platform",
        "supported_platform",
        "requires_python",
        "requires_dist",
        "requires_external",
        "provides_dist",
        "obsoletes_dist",
        "project_url",
        "provides_extra",
        "dynamic",
        "requires",
        "provides",
        "obsoletes",
    }
    for item in installed:
        if not isinstance(item, dict) or set(item) - {
            "metadata",
            "metadata_location",
            "installer",
            "requested",
            "direct_url",
        }:
            raise Refusal("pip-public-schema-unrecognized")
        metadata = item.get("metadata") if isinstance(item, dict) else None
        if not isinstance(metadata, dict) or set(metadata) - metadata_fields:
            raise Refusal("pip-public-schema-unrecognized")
        if "direct_url" in item:
            validate_direct_url(item["direct_url"], source_root)
        for field in ("home_page", "download_url", "project_url"):
            values = metadata.get(field, [])
            for value in values if isinstance(values, list) else [values]:
                if isinstance(value, str):
                    for token in value.split():
                        if "://" in token:
                            public_url(token)
        name = metadata.get("name") if isinstance(metadata, dict) else None
        version = metadata.get("version") if isinstance(metadata, dict) else None
        if (
            not isinstance(name, str)
            or len(name) > 128
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) is None
        ):
            raise Refusal("distribution-name-invalid")
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if (
            normalized in seen
            or not isinstance(version, str)
            or len(version) > 64
            or VERSION.fullmatch(version) is None
        ):
            raise Refusal("distribution-version-or-duplicate-invalid")
        seen.add(normalized)
        result.append(
            {
                "name": name,
                "normalized_name": normalized,
                "version": version,
                "origin": "python-distribution",
                "scope": None,
                "license_expression": None,
                "classification_status": "unclassified",
                "license_files": [],
                "metadata_license_expression_claim": metadata.get("license_expression"),
                "metadata_license_claim": metadata.get("license"),
                "metadata_location": item.get("metadata_location"),
            }
        )
    return sorted(result, key=lambda item: item["normalized_name"])


def public_url(value: object):
    if not isinstance(value, str) or len(value) > 8192:
        raise Refusal("pip-url-invalid")
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise Refusal("pip-url-credential-refused")
    # Unknown query/fragment values can carry credentials under arbitrary names.
    # Refuse their retention instead of claiming a token-name filter sanitizes them.
    if parsed.query or parsed.fragment:
        raise Refusal("pip-url-credential-refused")
    if parsed.scheme not in {"http", "https", "file"} or (
        parsed.scheme != "file" and not parsed.hostname
    ):
        raise Refusal("pip-url-source-unobserved")
    return parsed


def validate_direct_url(value: object, source_root: Path | None):
    if not isinstance(value, dict) or set(value) - {
        "url",
        "vcs_info",
        "dir_info",
        "archive_info",
        "subdirectory",
    }:
        raise Refusal("pip-direct-url-schema-unrecognized")
    parsed = public_url(value.get("url"))
    for key, fields in (
        ("vcs_info", {"vcs", "commit_id", "requested_revision"}),
        ("dir_info", {"editable"}),
        ("archive_info", {"hash", "hashes"}),
    ):
        if key in value and (not isinstance(value[key], dict) or set(value[key]) - fields):
            raise Refusal("pip-direct-url-schema-unrecognized")
    # The candidate installs its own bound checkout directly. Remote direct
    # origins/VCS/archives need a future reviewed lock/provenance adapter;
    # a URL or archive hash alone does not establish eligible public inputs.
    if (
        parsed.scheme != "file"
        or parsed.netloc
        or source_root is None
        or set(value) - {"url", "dir_info"}
        or "dir_info" not in value
    ):
        raise Refusal("pip-direct-url-origin-unobserved")
    path = unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    if not Path(path).is_absolute() or Path(os.path.abspath(path)) != source_root.absolute():
        raise Refusal("pip-direct-url-source-root-mismatch")


def walk_files(root: Path, observations: Observations, reference: str, *, permit_gaps: bool):
    """Stream directory entries; no os.walk list allocation or silent onerror."""
    pending = [root]
    while pending:
        directory = pending.pop()
        plain(directory, directory=True)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    observations.node()
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                        if permit_gaps:
                            observations.gap("stage-reparse-unobserved", reference)
                            continue
                        raise Refusal("metadata-reparse-unobserved")
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode):
                        yield Path(entry.path)
                    elif permit_gaps:
                        observations.gap("stage-special-file-unobserved", reference)
                    else:
                        raise Refusal("metadata-special-file-unobserved")
        except OSError as exc:
            raise Refusal(
                "stage-directory-unreadable" if permit_gaps else "metadata-directory-unreadable"
            ) from exc


def installed_identities(site_roots: list[Path], observations: Observations) -> dict[str, str]:
    """Read direct dist-info/egg-info only; do not load installed entry-point code."""
    identities = {}
    for root in site_roots:
        plain(root, directory=True)
        with os.scandir(root) as entries:
            for entry in entries:
                observations.node()
                if not entry.name.endswith((".dist-info", ".egg-info")):
                    continue
                path = Path(entry.path)
                plain(path, directory=True)
                metadata_name = "METADATA" if path.name.endswith(".dist-info") else "PKG-INFO"
                metadata = email.parser.BytesParser().parsebytes(
                    read(child(path, metadata_name), observations.limits.metadata_bytes),
                    headersonly=True,
                )
                name, version = metadata.get("Name"), metadata.get("Version")
                if not isinstance(name, str) or not isinstance(version, str):
                    raise Refusal("installed-metadata-identity-invalid")
                normalized = re.sub(r"[-_.]+", "-", name).lower()
                if normalized in identities or len(identities) >= observations.limits.distributions:
                    raise Refusal("installed-metadata-duplicate-or-bound")
                identities[normalized] = version
    return identities


def scan_metadata(components: list[dict], site_roots: list[Path], observations: Observations):
    roots = [root.resolve() for root in site_roots]
    if installed_identities(site_roots, observations) != {
        item["normalized_name"]: item["version"] for item in components
    }:
        raise Refusal("actual-installed-metadata-pip-inventory-mismatch")
    for root in site_roots:
        plain(root, directory=True)
    for component in components:
        ref = f"installed-distribution:{component['normalized_name']}"
        raw_location = component.pop("metadata_location")
        if not isinstance(raw_location, str) or not Path(raw_location).is_absolute():
            observations.gap("distribution-metadata-location-unobserved", ref)
            continue
        location = Path(raw_location)
        try:
            plain(location, directory=True)
            root = next(
                (value for value in roots if location.resolve().is_relative_to(value)), None
            )
            if root is None:
                raise Refusal("distribution-metadata-root-escape")
            metadata_raw = read(child(location, "METADATA"), observations.limits.metadata_bytes)
            metadata = email.parser.BytesParser().parsebytes(metadata_raw, headersonly=True)
            if (
                metadata.get("Name") != component["name"]
                or metadata.get("Version") != component["version"]
            ):
                raise Refusal("distribution-metadata-identity-mismatch")
            component["metadata_sha256"] = digest(metadata_raw)
            component["metadata_license_expression_claim"] = metadata.get("License-Expression")
            metadata_rel = location.relative_to(root).as_posix()
            for path in walk_files(location, observations, ref, permit_gaps=False):
                name = f"{metadata_rel}/{path.relative_to(location).as_posix()}"
                if license_name(name):
                    observations.observe(
                        name, read(path, observations.limits.license_bytes), ref, package=ref
                    )
            component["license_files"] = observations.licenses.get(ref, [])
            record = child(location, "RECORD")
            record_raw = read(record, observations.limits.metadata_bytes)
            known, native_records, count = set(), [], 0
            for fields in csv.reader(io.StringIO(record_raw.decode("utf-8"))):
                observations.node()
                count += 1
                if len(fields) != 3 or fields[0] in known:
                    raise Refusal("distribution-record-invalid")
                known.add(fields[0])
                try:
                    name = relative(fields[0])
                    path = child(root, name)
                except (Refusal, OSError):
                    observations.gap("distribution-record-outside-root-or-nonregular", ref)
                    continue
                # RECORD digests are claims. Hash actual native bytes and license material.
                if (
                    Path(name).suffix.lower() in {".dll", ".so", ".pyd", ".dylib", ".exe"}
                    or ".so." in name
                ):
                    data = read(path, observations.limits.member_bytes)
                    row = observations.observe(name, data, ref, package=ref)
                    native_records.append(row)
                elif license_name(name) and name not in {
                    value["path"] for value in component["license_files"]
                }:
                    observations.observe(
                        name, read(path, observations.limits.license_bytes), ref, package=ref
                    )
            component["license_files"] = observations.licenses.get(ref, [])
            component["installed_native_observations"] = native_records
            component["record_sha256"] = digest(record_raw)
            component["record_entry_count"] = count
            component["installed_files_all_hashed"] = False
        except (OSError, UnicodeError, Refusal) as exc:
            if isinstance(exc, Refusal) and str(exc) in GLOBAL_BOUNDS:
                raise
            observations.gap(
                str(exc) if isinstance(exc, Refusal) else "distribution-metadata-unavailable", ref
            )
        if not component["license_files"]:
            observations.gap("distribution-license-material-unobserved", ref)


def source_snapshot(root: Path, source: dict, limits: Limits):
    if not isinstance(source, dict) or not SHA.fullmatch(str(source.get("head", ""))):
        raise Refusal("source-binding-invalid")
    files = source.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= limits.source_files:
        raise Refusal("source-file-inventory-invalid")
    seen = set()
    for item in files:
        if not isinstance(item, dict) or not HEX.fullmatch(str(item.get("sha256", ""))):
            raise Refusal("source-file-binding-invalid")
        name = relative(item.get("path"))
        if name.casefold() in seen:
            raise Refusal("source-file-duplicate")
        seen.add(name.casefold())
        if digest(read(child(root, name), limits.input_bytes)) != item["sha256"]:
            raise Refusal("source-file-bytes-mismatch")
    material = "".join(
        f"{row['path']}\0{row['sha256']}\n" for row in sorted(files, key=lambda row: row["path"])
    ).encode()
    if digest(material) != source.get("checkout_bytes_sha256"):
        raise Refusal("source-fingerprint-mismatch")
    return {
        "head": source["head"],
        "checkout_bytes_sha256": source["checkout_bytes_sha256"],
        "files": [{"path": row["path"], "sha256": row["sha256"]} for row in files],
    }


def collect(
    root: Path,
    target: str,
    sha: str,
    proof_dir: str,
    stage_dir: str,
    site_roots: list[Path],
    runtime: dict,
    limits: Limits = DEFAULT_LIMITS,
    runtime_root: Path | None = None,
    repository: str | None = None,
):
    if target not in TARGETS or not SHA.fullmatch(sha):
        raise Refusal("candidate-identity-invalid")
    plain(root, directory=True)
    proof = child(root, proof_dir, directory=True)
    stage = child(root, stage_dir, directory=True)
    raw_finish = read(child(proof, "finish.json"), limits.json_bytes)
    finish = load(raw_finish)
    raw_bind = read(child(proof, "bind.json"), limits.json_bytes)
    bind = load(raw_bind)
    observed_repository = finish.get("repository", repository)
    if (
        not isinstance(observed_repository, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", observed_repository)
        is None
        or observed_repository.split("/")[1] in {".", ".."}
        or (repository is not None and observed_repository != repository)
        or any(
            not isinstance(finish.get(key), str)
            or re.fullmatch(r"[1-9][0-9]{0,19}", finish[key]) is None
            for key in ("run_id", "run_attempt")
        )
    ):
        raise Refusal("candidate-public-identity-invalid")
    for receipt in (finish, bind):
        receipt_source = receipt.get("source")
        if not isinstance(receipt_source, dict):
            raise Refusal("source-binding-invalid")
        if receipt.get("target") != target or receipt_source.get("head") != sha:
            raise Refusal("candidate-receipt-identity-mismatch")
    version = runtime.get("version")
    expected_bits = 32 if target == "windows-x86" else 64
    builder = bind.get("python")
    if (
        runtime.get("implementation") != "CPython"
        or not isinstance(version, str)
        or not VERSION.fullmatch(version)
        or runtime.get("pointer_bits") != expected_bits
        or not isinstance(builder, dict)
        or str(builder.get("version", "")).split(" ", 1)[0] != version
    ):
        raise Refusal("actual-builder-runtime-receipt-mismatch")
    source = finish.get("source")
    if (
        finish.get("source_unchanged") is not True
        or source != bind.get("source")
        or finish.get("pip_inspect_returncode") != 0
        or finish.get("pip_inspect_json_valid") is not True
    ):
        raise Refusal("candidate-receipt-not-complete")
    public_source = source_snapshot(root, source, limits)
    public_runtime = {key: runtime[key] for key in ("version", "implementation", "pointer_bits")}
    if "executable_sha256" in runtime:
        if not isinstance(runtime["executable_sha256"], str) or not HEX.fullmatch(
            runtime["executable_sha256"]
        ):
            raise Refusal("builder-executable-digest-invalid")
        public_runtime["executable_sha256"] = runtime["executable_sha256"]
        public_runtime["running_interpreter_path_resolved"] = (
            runtime.get("running_interpreter_path_resolved") is True
        )
    raw_inspect = read(child(proof, "pip-inspect.json"), limits.json_bytes)
    if digest(raw_inspect) != finish.get("pip_inspect_sha256"):
        raise Refusal("pip-inspect-byte-mismatch")
    raw_archives = read(child(proof, "pyinstaller-archives.json"), limits.json_bytes)
    if digest(raw_archives) != finish.get("pyinstaller_archive_inventory_sha256"):
        raise Refusal("carchive-receipt-byte-mismatch")
    archives = load(raw_archives, array=True)
    if not 1 <= len(archives) <= 32:
        raise Refusal("carchive-receipt-shape-invalid")
    observations = Observations(limits)
    components = inspect_distributions(raw_inspect, limits, root)
    scan_metadata(components, site_roots, observations)
    runtime_component = {
        "name": "CPython",
        "version": runtime.get("version"),
        "origin": "python-runtime",
        "scope": None,
        "license_expression": None,
        "license_files": [],
        "classification_status": "unclassified",
        "observation_scope": "builder-runtime",
        "packaged_version_verified": False,
    }
    components.append(runtime_component)
    if runtime_root is not None:
        plain(runtime_root, directory=True)
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.rst"):
            path = runtime_root / name
            if path.exists():
                observations.observe(
                    f"CPython/{name}",
                    read(path, limits.license_bytes),
                    "builder-runtime",
                    package="builder-runtime",
                )
        runtime_component["license_files"] = observations.licenses.get("builder-runtime", [])
    observations.gap("builder-cpython-license-and-packaged-version-unverified", "builder-runtime")
    for path in walk_files(stage, observations, stage_dir, permit_gaps=True):
        name = path.relative_to(root).as_posix()
        try:
            data = read(path, limits.member_bytes)
            observations.observe(path.relative_to(stage).as_posix(), data, name)
        except Refusal as exc:
            if str(exc) in GLOBAL_BOUNDS:
                raise
            observations.gap(str(exc), name)
    cookie_hints = []
    for archive in archives:
        if not isinstance(archive, dict):
            raise Refusal("carchive-receipt-shape-invalid")
        path = child(root, receipt_relative(archive.get("path"), target))
        if not path.is_relative_to(stage):
            raise Refusal("carchive-stage-root-mismatch")
        data = read(path, limits.member_bytes)
        if digest(data) != archive.get("artifact_sha256"):
            raise Refusal("carchive-executable-byte-mismatch")
        cookie = scan_carchive(data, path.relative_to(root).as_posix(), observations)
        if not cookie:
            raise Refusal("carchive-cookie-unobserved")
        cookie_hints.append({"reference": path.relative_to(root).as_posix(), **cookie})
    components.append(
        {
            "name": "PyInstaller bootloader",
            "version": None,
            "origin": "pyinstaller-bootloader",
            "scope": None,
            "license_expression": None,
            "license_files": [],
            "classification_status": "unclassified",
            "observed_executable_count": len(archives),
            "carchive_runtime_hints": cookie_hints,
            "observation_scope": "CArchive cookie/TOC; bootloader identity/version not proved",
        }
    )
    assets, seen, asset_inputs = {}, set(), 0
    manifest = finish.get("assets")
    if not isinstance(manifest, list) or not 1 <= len(manifest) <= 32:
        raise Refusal("asset-inventory-invalid")
    for item in manifest:
        if not isinstance(item, dict):
            raise Refusal("asset-binding-invalid")
        name = receipt_relative(item.get("path"), target)
        if (
            name.casefold() in seen
            or not integer(item.get("size"), 1)
            or not HEX.fullmatch(str(item.get("sha256", "")))
        ):
            raise Refusal("asset-binding-invalid")
        seen.add(name.casefold())
        asset_inputs += item["size"]
        if asset_inputs > limits.aggregate_input_bytes:
            raise Refusal("aggregate-input-byte-bound")
        data = read(child(root, name), limits.input_bytes)
        if len(data) != item["size"] or digest(data) != item["sha256"]:
            raise Refusal("asset-byte-mismatch")
        key = PurePosixPath(name).name
        if key in assets:
            raise Refusal("asset-basename-duplicate")
        if key.endswith(("-manifest.json", "SHA256SUMS.txt")):
            result = {
                "backend": "metadata-only",
                "all_regular_payload_files_observed": False,
                "license_records": [],
            }
        else:
            try:
                result = scan_package(data, key, observations)
            except (
                Refusal,
                ValueError,
                OSError,
                EOFError,
                tarfile.TarError,
                zipfile.BadZipFile,
                lzma.LZMAError,
                zlib.error,
                struct.error,
            ) as exc:
                if isinstance(exc, Refusal) and str(exc) in GLOBAL_BOUNDS:
                    raise
                observations.gap(
                    str(exc) if isinstance(exc, Refusal) else "archive-parser-refused", key
                )
                result = {
                    "backend": "refused",
                    "all_regular_payload_files_observed": False,
                    "license_records": observations.licenses.get(key, []),
                }
        assets[key] = {"sha256": digest(data), "size_bytes": len(data), **result}
    observations.gap("external-host-runtime-dependency-closure-unobserved", target)
    observations.gap("legal-license-and-bundled-build-only-classification-required", target)
    native_components = {}
    for row in observations.files:
        if "native_format_observation" not in row:
            continue
        key = row["sha256"]
        component = native_components.setdefault(
            key,
            {
                "name": f"unidentified-native-{key}",
                "version": None,
                "origin": "native-component",
                "scope": None,
                "license_expression": None,
                "license_files": [],
                "classification_status": "unclassified",
                "sha256": key,
                "format_observed": row["native_format_observation"],
                "references": [],
            },
        )
        component["references"].append(row["reference"])
    components.extend(native_components.values())
    source_snapshot(root, source, limits)
    # Recheck all bound input bytes after parsing. This is not an adversarial race guarantee.
    for filename, original in (
        ("finish.json", raw_finish),
        ("bind.json", raw_bind),
        ("pip-inspect.json", raw_inspect),
        ("pyinstaller-archives.json", raw_archives),
    ):
        if read(child(proof, filename), limits.json_bytes) != original:
            raise Refusal("candidate-input-changed")
    for item in manifest:
        if (
            digest(read(child(root, receipt_relative(item["path"], target)), limits.input_bytes))
            != item["sha256"]
        ):
            raise Refusal("asset-changed-after-scan")
    record = {
        "schema": SCHEMA,
        "decision": "unapproved",
        "signed": False,
        "repository": observed_repository,
        "release_tag": None,
        "source_sha": sha,
        "target": target,
        "closed_world_complete": False,
        "classification_complete": False,
        "all_installed_distributions_recorded": True,
        "artifact_contents_scanned": False,
        "runtime_observations": public_runtime,
        "source_binding": public_source,
        "source_binding_authority": "locally rehashed candidate receipts; no independent run attestation",
        "run_id": finish.get("run_id"),
        "run_attempt": finish.get("run_attempt"),
        "inputs": {
            "finish_sha256": digest(raw_finish),
            "bind_sha256": digest(raw_bind),
            "carchive_report_sha256": digest(raw_archives),
        },
        "realized_environment": {
            "reference": "actual candidate pip inspect --local capture",
            "format": "pip-inspect-v1",
            "file": "raw/pip-inspect.json",
            "size_bytes": len(raw_inspect),
            "sha256": digest(raw_inspect),
        },
        "components": components,
        "assets": assets,
        "observed_files": observations.files,
        "artifact_license_files": {
            name: value["license_records"] for name, value in assets.items()
        },
        "unresolved": observations.gaps,
        "limits": vars(limits),
        "scope": "Unsigned observations for external review; no component classification, legal approval, package execution or complete external runtime claim",
    }
    # Raw transport receipts may contain extra/private fields; only their hashes
    # and the validated facts above are retained. Exact pip bytes remain necessary
    # for the existing compliance verifier and are schema/URL checked first.
    raw_inputs = {"raw/pip-inspect.json": raw_inspect}
    return record, {
        **raw_inputs,
        **{f"files/licenses/{key}.bin": value for key, value in observations.blobs.items()},
    }


def write_new_bundle(output: Path, record: dict, blobs: dict[str, bytes]):
    if output.exists():
        raise Refusal("output-must-be-new")
    plain(output.parent, directory=True)
    output.mkdir(mode=0o700)
    try:
        for name, data in blobs.items():
            target = output.joinpath(*relative(name).split("/"))
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            plain(target.parent, directory=True)
            with target.open("xb") as stream:
                stream.write(data)
        with (output / "observations.json").open("xb") as stream:
            stream.write(canonical(record) + b"\n")
        with (output / "COMPLETE-OBSERVATIONS-ONLY").open("xb") as stream:
            stream.write(b"Unsigned and unapproved. Unknowns are not completed requirements.\n")
    except Exception:
        # Retain failed staging for inspection; never promote without the final marker.
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--sha", required=True)
    parser.add_argument("--proof-dir", required=True)
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if (
            os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or not re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ID", ""))
            or not re.fullmatch(r"[1-9][0-9]*", os.environ.get("GITHUB_RUN_ATTEMPT", ""))
        ):
            raise Refusal("collector-hosted-capture-only")
        executable = Path(sys.executable).resolve(strict=True)
        runtime = {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "pointer_bits": struct.calcsize("P") * 8,
            "executable_sha256": digest(read(executable, Limits().input_bytes)),
            "running_interpreter_path_resolved": True,
        }
        roots = sorted({Path(sysconfig.get_path(value)) for value in ("purelib", "platlib")})
        output = root.joinpath(*relative(args.output).split("/"))
        record, blobs = collect(
            root,
            args.target,
            args.sha,
            args.proof_dir,
            args.stage_dir,
            roots,
            runtime,
            runtime_root=Path(sys.base_prefix),
            repository=os.environ.get("GITHUB_REPOSITORY"),
        )
        if (
            record["run_id"] != os.environ["GITHUB_RUN_ID"]
            or record["run_attempt"] != os.environ["GITHUB_RUN_ATTEMPT"]
        ):
            raise Refusal("collector-current-run-receipt-mismatch")
        write_new_bundle(output, record, blobs)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RecursionError,
        struct.error,
        EOFError,
    ) as exc:
        print(str(exc) if isinstance(exc, Refusal) else "collector-io-refused", file=sys.stderr)
        return 1
    print(
        f"unsigned runtime observations captured: {len(record['components'])} components; {len(record['unresolved'])} unresolved observations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
