"""Observe a pinned previous macOS PKG on an official disposable host only.

No installer, application, encrypted recovery or release operation is enabled.
The default plan action performs no native operation or network request.
"""

from __future__ import annotations

import argparse
import codecs
import ctypes
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import re
import stat
import struct
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from xml.parsers import expat

ROOT = Path.cwd().resolve()
REPO = "Yunushan/remote-ops-workspace"
APP_REL = "Applications/Remote Ops Workspace.app"
APP_ID = "io.github.remoteopsworkspace.app"
MAX_PKG = 150 * 1024 * 1024
MAX_PUBLIC = 4 * 1024 * 1024
MAX_ROWS = 30000
# Accepted bytes per receipt query; retained stdout remains a bounded line.
MAX_RECEIPT_FILE_BYTES = MAX_ROWS * (1024 + 3)
MAX_NODES = 30000
MAX_XML = 4 * 1024 * 1024
MAX_XML_DEPTH = 24
MAX_XML_TEXT = 1024 * 1024
MAX_XML_METADATA = 256 * 1024
MAX_EXPANDED = 512 * 1024 * 1024
MAX_NETWORK_METADATA = 2 * 1024 * 1024
MAX_SOURCE_TOTAL = 512 * 1024 * 1024
MAX_PRIVATE_COMMAND_BYTES = 256 * 1024 * 1024
READONLY_SYSTEM_TOOLS = (
    "/usr/bin/git",
    "/usr/bin/man",
    "/bin/cat",
    "/usr/bin/lsbom",
    "/usr/sbin/pkgutil",
)
REPORT = "build/native-smoke/macos-x64/previous-pkg-metadata.json"
CONTRACTS = (
    "scripts/observe_macos_previous_pkg.py",
    "tests/test_observe_macos_previous_pkg.py",
    ".github/workflows/macos-previous-pkg-metadata.yml",
    "src/remote_ops_workspace/process_status.py",
)
PREVIOUS = {
    "repository": REPO,
    "release_id": 382583184,
    "tag": "v1.0.24",
    "tag_commit": "2165989ca9f3ffbd59a8f27a296cda3fb295a404",
    "published_at": "2026-09-04T08:39:52Z",
    "prerelease": True,
    "asset_id": 544041419,
    "asset_name": "remote-ops-workspace-v1.0.24-macos-x64.pkg",
    "size": 34437450,
    "sha256": "5ee8f22aea77f82b20641ce46d440eeff63af1ed35ae1e4ad478f07be34a217a",
    "browser_download_url": "https://github.com/Yunushan/remote-ops-workspace/releases/download/v1.0.24/remote-ops-workspace-v1.0.24-macos-x64.pkg",
}
SOURCE_BINDING = None
# Bootstrap source identity can itself fail in an owned Git child. This exact
# reviewed stdlib-only cleanup source authorizes that first leader's cleanup.
BOOTSTRAP_CLEANUP_SHA = "0b886bbb7e502c9c3848feb08d139872d57861209bbe3bdc85ed82783c7d3ab5"
REFUSAL_CONTEXT = None
RECEIPT_OPERATIONS = frozenset(("info", "files", "projection", "relevance"))
COMMAND_DIAGNOSTIC_STAGES = frozenset((
    "launch", "pipe-start", "wait", "exit-deadline", "pipe-drain", "output-deadline",
    "private-output", "expected-exit", "returned",
))
RECEIPT_STREAM_DIAGNOSTIC_KEYS = (
    "receipt_stream_stdout_bytes", "receipt_stream_stdout_sha256", "receipt_stream_stdout_bound_bytes",
    "receipt_stream_stderr_bytes", "receipt_stream_stderr_sha256", "receipt_stream_stderr_bound_bytes",
    "receipt_stream_stdout_eof", "receipt_stream_stderr_eof", "receipt_stream_complete",
    "receipt_stream_hashes_partial",
)
COMMAND_DIAGNOSTIC_KEYS = (
    "command_stage", "command_stdout_bytes", "command_stdout_sha256", "command_stdout_bound_bytes",
    "command_stderr_bytes", "command_stderr_sha256", "command_stderr_bound_bytes",
    "command_stdout_overflow_observed", "command_stderr_overflow_observed",
    "command_stdout_read_error_observed", "command_stderr_read_error_observed",
    "command_stdin_write_error_observed", "command_live_pipe_threads",
    *RECEIPT_STREAM_DIAGNOSTIC_KEYS,
)
REFUSAL_CODES = frozenset(
    (
        "actual-official-intel-macos15-required",
        "bom-magic-unobserved",
        "bom-output-byte-bound",
        "bom-output-encoding",
        "bom-output-row-bound",
        "bom-path-alias-or-duplicate",
        "bom-requested-column-layout-unobserved",
        "canonical-metadata-contract-untracked",
        "capability-parent-identity-changed",
        "capability-parent-shape",
        "command-late-completed-exit",
        "command-late-completed-output",
        "command-lifetime-uncertain",
        "command-output-bound-or-read",
        "command-pipe-lifetime-or-bound",
        "command-stdin-bound",
        "command-timeout",
        "command-unexpected-exit",
        "compressed-stream-bound-or-tail",
        "compressed-stream-malformed",
        "default-owned-child-reaping-required",
        "diagnostic-phase-refused",
        "duplicate-json-field",
        "exact-branch-dispatch-source-required",
        "exact-clean-official-source-required",
        "exact-workflow-ref-required",
        "executed-workflow-contract-mismatch",
        "getattrlist-abi-unobserved",
        "getattrlist-capability-layout-unobserved",
        "getattrlist-capability-truncated",
        "harness-deadline",
        "input-changed-during-read",
        "installed-manual-bound",
        "installed-manual-controls",
        "installed-manual-encoding-unobserved",
        "installed-manual-field-ambiguity",
        "json-byte-bound",
        "json-layout-unobserved",
        "metadata-command-or-aggregate-bound",
        "metadata-component-checksum-mismatch",
        "metadata-component-expanded-bound",
        "metadata-input-source-or-command-uncertain",
        "metadata-overall-deadline",
        "noncanonical-numeric-metadata",
        "numeric-metadata-bound",
        "official-download-redirect-refused",
        "official-network-byte-bound",
        "official-network-length-refused",
        "official-network-response-refused",
        "official-network-url-refused",
        "official-public-hosted-event-required",
        "owned-cleanup-source-changed",
        "owned-directory-containment",
        "package-info-root-unobserved",
        "previous-asset-identity-changed",
        "previous-publication-identity-changed",
        "previous-release-asset-membership-changed",
        "previous-tag-identity-changed",
        "previous-whole-package-bytes-mismatch",
        "private-metadata-directory-shape",
        "public-output-bound-or-existing",
        "receipt-location-unobserved",
        "receipt-files-row-bound",
        "receipt-files-stderr-unobserved",
        "receipt-metadata-bound",
        "receipt-metadata-layout-unobserved",
        "receipt-namespace-bound-or-alias",
        "receipt-namespace-encoding",
        "receipt-path-alias-or-duplicate",
        "regular-input-bound-or-link",
        "relevant-receipt-projection-bound",
        "runner-output-protocol-shape",
        "same-repository-pr-source-required",
        "system-tool-bound-type-or-ownership-refused",
        "system-tool-index-refused",
        "system-tool-nofollow-unavailable",
        "tracked-source-byte-bound",
        "tracked-source-path-layout",
        "tracked-source-path-link",
        "unsafe-member-name",
        "unsupported-event",
        "whole-pkg-bound",
        "xar-component-alias",
        "xar-component-count-bound",
        "xar-component-span-bound",
        "xar-header-unobserved",
        "xar-overlapping-component-spans",
        "xar-required-field-unobserved",
        "xar-toc-checksum-mismatch",
        "xar-toc-layout-unobserved",
        "xar-toc-size-mismatch",
        "xml-bound-or-entity",
        "xml-malformed",
        "xml-markup-unobserved",
        "xml-metadata-bound",
        "xml-node-or-depth-bound",
        "xml-text-bound",
    )
)


class Refusal(ValueError):
    """Static public code only; never include raw tool metadata or network URLs."""


class EvidenceError(Refusal):
    """Canonical bounded command runner's existing static failures."""


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def alias(value):
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", value).casefold())


def regular(path, maximum, *, allow_empty=False):
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not (0 if allow_empty else 1) <= before.st_size <= maximum
    ):
        raise Refusal("regular-input-bound-or-link")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    after_path = path.lstat()

    def fields(item):
        return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns

    # Path and fd ctime semantics differ on Windows. Compare complete identity
    # within each API plus shared dev/inode/size/mtime across APIs; neither loses
    # its before/after ctime guard on the actual future Darwin host.
    if (
        fields(before) != fields(after_path)
        or fields(opened) != fields(after)
        or fields(before)[:4] != fields(opened)[:4]
        or len(raw) != before.st_size
    ):
        raise Refusal("input-changed-during-read")
    return raw



def _system_tool_stat_identity(item):
    return (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_uid,
        item.st_gid,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
        getattr(item, "st_flags", None),
    )


def readonly_system_tool_bytes(index):
    """Read only a fixed root-owned system tool; its hardlinks are OS metadata."""

    if type(index) is not int or not 0 <= index < len(READONLY_SYSTEM_TOOLS):
        raise Refusal("system-tool-index-refused")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if type(nofollow) is not int or nofollow <= 0:
        raise Refusal("system-tool-nofollow-unavailable")
    path = Path(READONLY_SYSTEM_TOOLS[index])
    before = path.lstat()
    if (
        type(before.st_mode) is not int
        or not stat.S_ISREG(before.st_mode)
        or type(before.st_uid) is not int
        or before.st_uid != 0
        or type(before.st_gid) is not int
        or not 0 <= before.st_gid <= (1 << 32) - 1
        or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or type(before.st_nlink) is not int
        or not 1 <= before.st_nlink <= MAX_ROWS
        or type(before.st_size) is not int
        or not 1 <= before.st_size <= 16 * 1024 * 1024
    ):
        raise Refusal("system-tool-bound-type-or-ownership-refused")
    fd = os.open(path, os.O_RDONLY | nofollow)
    try:
        stream = os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        opened = os.fstat(stream.fileno())
        if _system_tool_stat_identity(before) != _system_tool_stat_identity(opened):
            raise Refusal("input-changed-during-read")
        raw = stream.read(before.st_size + 1)
        after = os.fstat(stream.fileno())
    after_path = path.lstat()
    if (
        _system_tool_stat_identity(before) != _system_tool_stat_identity(after)
        or _system_tool_stat_identity(before) != _system_tool_stat_identity(after_path)
        or len(raw) != before.st_size
    ):
        raise Refusal("input-changed-during-read")
    return raw

def fixed_text(parent, tag):
    nodes = parent.findall(tag)
    if len(nodes) != 1 or not isinstance(nodes[0].text, str):
        raise Refusal("xar-required-field-unobserved")
    return nodes[0].text


def decimal(value, maximum):
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,11})", value):
        raise Refusal("noncanonical-numeric-metadata")
    result = int(value)
    if result > maximum:
        raise Refusal("numeric-metadata-bound")
    return result


def package_projection(raw, parser):
    """Observe exact TOC; extract only bounded Bom/PackageInfo to private memory."""
    if not 28 <= len(raw) <= MAX_PKG:
        raise Refusal("whole-pkg-bound")
    magic, header_size, version, compressed, expanded, algorithm = struct.unpack(
        "!4sHHQQI", raw[:28]
    )
    if (
        magic != b"xar!"
        or header_size != 28
        or version != 1
        or algorithm not in (1, 3)
        or not 0 < compressed <= parser.MAX_XML
        or not 0 < expanded <= parser.MAX_XML
        or 28 + compressed > len(raw)
    ):
        raise Refusal("xar-header-unobserved")
    compressed_toc = raw[28 : 28 + compressed]
    toc_raw = parser.bounded_decode(compressed_toc, limit=parser.MAX_XML)
    if len(toc_raw) != expanded:
        raise Refusal("xar-toc-size-mismatch")
    tree = parser.public_xml(toc_raw)
    if tree.tag != "xar" or len(tree) != 1 or tree[0].tag != "toc":
        raise Refusal("xar-toc-layout-unobserved")
    toc, heap = tree[0], memoryview(raw)[28 + compressed :]
    checksum = toc.findall("checksum")
    name = "sha1" if algorithm == 1 else "sha256"
    digest = hashlib.new(name, compressed_toc).digest()
    if (
        len(checksum) != 1
        or checksum[0].get("style") != name
        or fixed_text(checksum[0], "offset") != "0"
        or fixed_text(checksum[0], "size") != str(len(digest))
        or heap[: len(digest)] != digest
    ):
        raise Refusal("xar-toc-checksum-mismatch")
    records, materials, aliases, spans = [], {}, set(), [(0, len(digest))]
    known = {"Bom", "PackageInfo", "Payload", "Scripts", "Distribution", "Resources"}
    for file in toc.iter("file"):
        if len(records) >= 64:
            raise Refusal("xar-component-count-bound")
        member = parser.member_name(fixed_text(file, "name"))
        key = alias(member)
        if key in aliases:
            raise Refusal("xar-component-alias")
        aliases.add(key)
        row = {
            "name": member if member in known else None,
            "name_sha256": sha(member.encode()),
            "type": "file" if fixed_text(file, "type") == "file" else "unobserved",
            "nested_children": len(file.findall("file")),
        }
        data = file.findall("data")
        if len(data) != 1 or row["type"] != "file" or row["nested_children"]:
            row["data_status"] = "unobserved-layout"
            records.append(row)
            continue
        node = data[0]
        offset, length, size = (
            decimal(fixed_text(node, field), MAX_PKG) for field in ("offset", "length", "size")
        )
        encoding = node.findall("encoding")
        if len(encoding) != 1 or not length or offset + length > len(heap):
            raise Refusal("xar-component-span-bound")
        style = encoding[0].get("style", "")
        stored = heap[offset : offset + length]
        spans.append((offset, offset + length))
        row.update(
            offset=offset,
            stored_bytes=length,
            expanded_bytes_declared=size,
            stored_sha256=sha(stored),
            stored_prefix_hex=bytes(stored[:8]).hex(),
            codec=style
            if style
            in {
                "application/octet-stream",
                "application/x-gzip",
                "application/x-bzip2",
                "application/x-lzma",
                "application/x-xz",
            }
            else "unobserved",
            codec_sha256=sha(style.encode()),
            data_status="stored-bytes-observed",
        )
        if member in {"Bom", "PackageInfo"}:
            bound = 16 * 1024 * 1024 if member == "Bom" else parser.MAX_XML
            if size > bound:
                raise Refusal("metadata-component-expanded-bound")
            if style == "application/octet-stream":
                material = bytes(stored)
            elif style == "application/x-gzip":
                # Observe the wrapper bytes; do not assume the style implies RFC1952.
                material = parser.bounded_decode(
                    bytes(stored), gzip_stream=stored[:2] == b"\x1f\x8b", limit=bound
                )
            else:
                row["data_status"] = "metadata-codec-unobserved"
                records.append(row)
                continue
            checks = node.findall("extracted-checksum")
            if (
                len(material) != size
                or len(checks) != 1
                or checks[0].get("style") not in {"sha1", "sha256"}
                or hashlib.new(checks[0].get("style"), material).hexdigest() != checks[0].text
            ):
                raise Refusal("metadata-component-checksum-mismatch")
            materials[member] = material
            row.update(data_status="extracted-metadata-observed", extracted_sha256=sha(material))
        records.append(row)
    end, gaps = 0, 0
    for start, stop in sorted(spans):
        if start < end:
            raise Refusal("xar-overlapping-component-spans")
        gaps += start - end
        end = stop
    gaps += len(heap) - end
    return {
        "whole_pkg_bytes": len(raw),
        "whole_pkg_sha256": sha(raw),
        "toc_sha256": sha(toc_raw),
        "toc_codec": "zlib",
        "checksum_algorithm": name,
        "components": records,
        "unaccounted_heap_bytes": gaps,
        "nested_or_unobserved_layout": any(
            row["data_status"] == "unobserved-layout" for row in records
        ),
        "scripts_component_observed": any(row["name"] == "Scripts" for row in records),
        "payload_expanded": False,
        "script_contents_executed": False,
    }, materials


def package_info_projection(raw, parser):
    tree = parser.public_xml(raw)
    if tree.tag != "pkg-info":
        raise Refusal("package-info-root-unobserved")
    version = tree.get("version", "")
    scripts = [
        node
        for node in tree.iter()
        if node.tag in {"scripts", "preinstall", "postinstall", "preflight", "postflight"}
    ]
    allowed = {
        "identifier",
        "version",
        "install-location",
        "auth",
        "format-version",
        "generator-version",
    }
    return {
        "raw_sha256": sha(raw),
        "identifier_is_expected": tree.get("identifier") == APP_ID,
        "version": version
        if re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version)
        else None,
        "install_location_is_root": tree.get("install-location") == "/",
        "auth_is_root": tree.get("auth") == "root",
        "unprojected_root_attribute_count": len(set(tree.attrib) - allowed),
        "script_element_count": len(scripts),
        "script_metadata_sha256": sha(
            json.dumps(
                [{"tag": node.tag, "attrs": node.attrib} for node in scripts], sort_keys=True
            ).encode()
        ),
        "unprojected_tag_count": sum(
            node.tag
            not in {
                "pkg-info",
                "payload",
                "bundle",
                "bundle-version",
                "upgrade-bundle",
                "update-bundle",
                "atomic-update-bundle",
                "strict-identifier",
                "scripts",
                "preinstall",
                "postinstall",
                "preflight",
                "postflight",
            }
            for node in tree.iter()
        ),
        "package_identity_approval": False,
    }


def _bom_failed_row_facts(line, columns, index, reason):
    """Bounded syntax facts only; never project paths, values or semantics."""
    raw = line.encode("utf-8")
    facts = {
        "bom_failed_row_index": index,
        "bom_failed_column_count": len(columns),
        "bom_failed_line_size_bytes": len(raw),
        "bom_failed_line_sha256": sha(raw),
        "bom_failed_layout_class": reason,
    }
    for column in range(1, 5):
        field = columns[column] if column < len(columns) else None
        if field is None:
            category = "absent"
        elif not field:
            category = "empty"
        elif re.fullmatch(r"[0-7]+", field):
            category = "ascii-octal-digits"
        elif re.fullmatch(r"[0-9]+", field):
            category = "ascii-decimal-digits"
        elif field.isascii():
            category = "ascii-other"
        else:
            category = "non-ascii"
        prefix = "bom_failed_column_" + str(column)
        facts[prefix + "_class"] = category
        facts[prefix + "_characters"] = 0 if field is None else len(field)
        facts[prefix + "_size_bytes"] = 0 if field is None else len(field.encode("utf-8"))
    return facts


def bom_projection(raw, parser):
    """Public requested columns only; installed lsbom contract is still unqualified."""
    if len(raw) > MAX_PUBLIC:
        raise Refusal("bom-output-byte-bound")
    facts = {"bom_output_sha256": sha(raw), "bom_size_bytes": len(raw), "bom_decoder": "strict-utf8"}
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        diagnostic_phase(
            "installed-bom-reader", **facts, bom_utf8_valid=False,
            bom_decode_error_offset=exc.start, bom_decode_error_width=exc.end - exc.start,
        )
        raise Refusal("bom-output-encoding") from exc
    facts.update(bom_utf8_valid=True, bom_row_count=len(lines))
    diagnostic_phase("installed-bom-reader", **facts)
    if len(lines) > MAX_ROWS:
        raise Refusal("bom-output-row-bound")
    rows, keys, unprojected, app_aliases = [], set(), 0, 0
    for index, line in enumerate(lines, 1):
        columns = line.split("\t")
        if (
            len(columns) != 5
            or not re.fullmatch(r"[0-7]{1,8}", columns[1])
            or any(not re.fullmatch(r"[0-9]{1,12}", field) for field in columns[2:4])
            or (
                not re.fullmatch(r"[0-9]{1,12}", columns[4])
                and not (columns[4] == "" and stat.S_ISDIR(int(columns[1], 8)))
            )
        ):
            reason = (
                "column-count" if len(columns) != 5 else
                "mode-field" if not re.fullmatch(r"[0-7]{1,8}", columns[1]) else
                "numeric-field"
            )
            diagnostic_phase(
                "installed-bom-reader", **facts,
                **_bom_failed_row_facts(line, columns, index, reason),
            )
            raise Refusal("bom-requested-column-layout-unobserved")
        path = parser.member_name(columns[0], root=True)
        key = alias(path)
        if key in keys:
            raise Refusal("bom-path-alias-or-duplicate")
        keys.add(key)
        app_aliases += int(
            (key == alias(APP_REL) or key.startswith(alias(APP_REL) + "/"))
            and path != APP_REL
            and not path.startswith(APP_REL + "/")
        )
        if path in {".", "Applications", APP_REL} or path.startswith(APP_REL + "/"):
            rows.append({"path": path, "requested_columns_as_strings": columns[1:]})
        else:
            unprojected += 1
    return {
        "output_sha256": sha(raw),
        "requested_format": "fmugs",
        "rows": rows,
        "unprojected_path_count": unprojected,
        "nonliteral_app_alias_count": app_aliases,
        "all_rows_parsed": True,
        "ownership_mode_size_semantics": "unqualified-until-installed-manual-and-output-review",
        "bom_payload_agreement": "not-checked",
        "native_ownership_proof": False,
    }


def receipt_projection(info_raw, files_raw, parser):
    if len(info_raw) > 65536 or len(files_raw) > MAX_PUBLIC:
        raise Refusal("receipt-metadata-bound")
    try:
        info = plistlib.loads(info_raw)
        lines = files_raw.decode("utf-8").splitlines()
    except Exception as exc:
        raise Refusal("receipt-metadata-layout-unobserved") from exc
    if (
        not isinstance(info, dict)
        or len(lines) > MAX_ROWS
        or not isinstance(info.get("volume"), str)
        or not isinstance(info.get("install-location"), str)
    ):
        raise Refusal("receipt-metadata-layout-unobserved")
    location = info["install-location"]
    if not location.startswith("/") or len(location.encode()) > 1024:
        raise Refusal("receipt-location-unobserved")
    base = location[1:].removesuffix("/")
    if base:
        parser.member_name(base)
    app_key, keys, claims, aliases, data_claims = alias(APP_REL), set(), 0, 0, 0
    for line in lines:
        name = parser.member_name(line, root=True)
        joined = base + "/" + name if base and name != "." else base or name
        key = alias(joined)
        if key in keys:
            raise Refusal("receipt-path-alias-or-duplicate")
        keys.add(key)
        if key == app_key or key.startswith(app_key + "/"):
            claims += 1
            aliases += int(joined != APP_REL and not joined.startswith(APP_REL + "/"))
        data_key = "system/volumes/data/" + app_key
        data_claims += int(key == data_key or key.startswith(data_key + "/"))
    return {
        "info_sha256": sha(info_raw),
        "files_sha256": sha(files_raw),
        "path_count": len(lines),
        "volume_is_root": info["volume"] == "/",
        "install_location_is_root": location == "/",
        "lexical_app_claim_count": claims,
        "app_alias_claim_count": aliases,
        "data_namespace_claim_count": data_claims,
        "physical_namespace_identity": "unobserved",
        "receipt_ownership_approval": False,
    }


class ReceiptFilesProjection:
    """Incremental exact UTF-8/splitlines projection; private aliases stay bounded."""

    def __init__(self, info_raw, parser, *, maximum=MAX_RECEIPT_FILE_BYTES):
        if len(info_raw) > 65536 or type(maximum) is not int or not 1 <= maximum <= MAX_RECEIPT_FILE_BYTES:
            raise Refusal("receipt-metadata-bound")
        try:
            self.info = plistlib.loads(info_raw)
        except Exception as exc:
            raise Refusal("receipt-metadata-layout-unobserved") from exc
        if (not isinstance(self.info, dict) or not isinstance(self.info.get("volume"), str)
                or not isinstance(self.info.get("install-location"), str)):
            raise Refusal("receipt-metadata-layout-unobserved")
        self.location = self.info["install-location"]
        if not self.location.startswith("/") or len(self.location.encode()) > 1024:
            raise Refusal("receipt-location-unobserved")
        self.base = self.location[1:].removesuffix("/")
        if self.base:
            parser.member_name(self.base)
        self.parser, self.maximum = parser, maximum
        self.info_sha256 = sha(info_raw)
        self.decoder = codecs.getincrementaldecoder("utf-8")("strict")
        self.raw_digest = hashlib.sha256()
        self.raw_bytes = 0
        self.line, self.line_bytes, self.after_cr = [], 0, False
        self.keys = set()
        self.app_key = alias(APP_REL)
        self.rows = self.claims = self.aliases = self.data_claims = 0
        self.finished = False

    def _row(self):
        self.rows += 1
        if self.rows > MAX_ROWS:
            raise Refusal("receipt-files-row-bound")
        name = self.parser.member_name("".join(self.line), root=True)
        joined = self.base + "/" + name if self.base and name != "." else self.base or name
        key = alias(joined)
        if key in self.keys:
            raise Refusal("receipt-path-alias-or-duplicate")
        self.keys.add(key)
        if key == self.app_key or key.startswith(self.app_key + "/"):
            self.claims += 1
            self.aliases += int(joined != APP_REL and not joined.startswith(APP_REL + "/"))
        data_key = "system/volumes/data/" + self.app_key
        self.data_claims += int(key == data_key or key.startswith(data_key + "/"))
        self.line.clear()
        self.line_bytes = 0

    def _text(self, text):
        for char in text:
            if self.after_cr:
                self.after_cr = False
                if char == "\n":
                    continue
            if char in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029":
                self._row()
                self.after_cr = char == "\r"
            else:
                self.line_bytes += len(char.encode("utf-8"))
                if self.line_bytes > 1024:
                    raise Refusal("unsafe-member-name")
                self.line.append(char)

    def feed(self, raw):
        if self.finished or type(raw) is not bytes or len(raw) > 65536:
            raise Refusal("receipt-metadata-layout-unobserved")
        if self.raw_bytes + len(raw) > self.maximum:
            raise Refusal("receipt-metadata-bound")
        self.raw_bytes += len(raw)
        self.raw_digest.update(raw)
        try:
            self._text(self.decoder.decode(raw, final=False))
        except UnicodeError as exc:
            raise Refusal("receipt-metadata-layout-unobserved") from exc
        if len(self.decoder.getstate()[0]) > 3:
            raise Refusal("receipt-metadata-layout-unobserved")

    def finish(self):
        if self.finished:
            raise Refusal("receipt-metadata-layout-unobserved")
        try:
            self._text(self.decoder.decode(b"", final=True))
        except UnicodeError as exc:
            raise Refusal("receipt-metadata-layout-unobserved") from exc
        if self.line:
            self._row()
        self.finished = True

    def result(self):
        if not self.finished:
            raise Refusal("receipt-metadata-layout-unobserved")
        return {
            "info_sha256": self.info_sha256,
            "files_sha256": self.raw_digest.hexdigest(),
            "path_count": self.rows,
            "volume_is_root": self.info["volume"] == "/",
            "install_location_is_root": self.location == "/",
            "lexical_app_claim_count": self.claims,
            "app_alias_claim_count": self.aliases,
            "data_namespace_claim_count": self.data_claims,
            "physical_namespace_identity": "unobserved",
            "receipt_ownership_approval": False,
        }


class ReceiptCommandStream:
    """Hash and charge every read byte; only an owned successful EOF is complete."""

    def __init__(self, projection, charge):
        self.projection, self.charge = projection, charge
        self.bounds = (projection.maximum, 1024 * 1024)
        self.counts = [0, 0]
        self.digests = [hashlib.sha256(), hashlib.sha256()]
        self.eofs = [False, False]
        self.lock = threading.Lock()
        self.failure_code = None
        self.complete = False

    def read_limit(self, index):
        with self.lock:
            # One over-bound sentinel may be read only to refuse; it is charged.
            return min(65536, max(1, self.bounds[index] + 1 - self.counts[index]))

    def consume(self, index, raw):
        with self.lock:
            self.counts[index] += len(raw)
            self.digests[index].update(raw)
            count = self.counts[index]
        self.charge(len(raw))
        if count > self.bounds[index]:
            raise EvidenceError("command-output-bound-or-read")
        if index == 0:
            self.projection.feed(raw)

    def eof(self, index):
        if index == 0:
            self.projection.finish()
        with self.lock:
            self.eofs[index] = True

    def fail(self, error):
        code = str(error) if isinstance(error, Refusal) else "receipt-metadata-layout-unobserved"
        if code not in REFUSAL_CODES:
            code = "receipt-metadata-layout-unobserved"
        with self.lock:
            if self.failure_code is None:
                self.failure_code = code

    def ready(self):
        with self.lock:
            if self.failure_code is not None or not all(self.eofs):
                raise EvidenceError("command-pipe-lifetime-or-bound")
            if self.counts[1]:
                raise Refusal("receipt-files-stderr-unobserved")

    def snapshot(self):
        with self.lock:
            return {
                "receipt_stream_stdout_bytes": self.counts[0],
                "receipt_stream_stdout_sha256": self.digests[0].hexdigest(),
                "receipt_stream_stdout_bound_bytes": self.bounds[0],
                "receipt_stream_stderr_bytes": self.counts[1],
                "receipt_stream_stderr_sha256": self.digests[1].hexdigest(),
                "receipt_stream_stderr_bound_bytes": self.bounds[1],
                "receipt_stream_stdout_eof": self.eofs[0],
                "receipt_stream_stderr_eof": self.eofs[1],
                "receipt_stream_complete": self.complete,
                "receipt_stream_hashes_partial": not self.complete,
            }


def receipt_stream_checkpoint(stage, stream):
    if (REFUSAL_CONTEXT is not None and REFUSAL_CONTEXT["phase"] == "receipt-info-and-files"
            and REFUSAL_CONTEXT["observed"].get("receipt_operation") == "files"):
        diagnostic_phase("receipt-info-and-files", command_stage=stage, **stream.snapshot())


def capabilities_projection(raw):
    if len(raw) != 36:
        raise Refusal("getattrlist-capability-layout-unobserved")
    length, *words = struct.unpack("<9I", raw)
    if length != 36:
        raise Refusal("getattrlist-capability-truncated")
    caps, valid = words[0], words[4]
    return {
        "raw_sha256": sha(raw),
        "format_capabilities": caps,
        "format_valid": valid,
        "declared_case_sensitive": bool(caps & 0x100) if valid & 0x100 else None,
        "declared_case_preserving": bool(caps & 0x200) if valid & 0x200 else None,
        "unicode_equivalence": "not-empirically-observed",
        "physical_alias_ownership": "unobserved",
    }


def observe_capabilities(path):
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(before.st_mode):
        raise Refusal("capability-parent-shape")

    class AttrList(ctypes.Structure):
        _fields_ = [
            ("bitmapcount", ctypes.c_uint16),
            ("reserved", ctypes.c_uint16),
            *(
                (name, ctypes.c_uint32)
                for name in ("common", "volume", "directory", "file", "fork")
            ),
        ]

    if ctypes.sizeof(AttrList) != 24:
        raise Refusal("getattrlist-abi-unobserved")
    attributes = AttrList(5, 0, 0, 0x80020000, 0, 0, 0)
    buffer = ctypes.create_string_buffer(36)
    api = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True).getattrlist
    api.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(AttrList),
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_ulong,
    ]
    api.restype = ctypes.c_int
    result = api(os.fsencode(path), ctypes.byref(attributes), buffer, 36, 1)
    after = path.lstat()
    if (before.st_dev, before.st_ino, before.st_mode) != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
    ):
        raise Refusal("capability-parent-identity-changed")
    if result != 0:
        return {
            "status": "unsupported-or-unobserved",
            "errno": ctypes.get_errno(),
            "unicode_equivalence": "not-empirically-observed",
        }
    return {"status": "declared-capabilities-only", **capabilities_projection(buffer.raw)}


def manual_projection(raw):
    if len(raw) > 512 * 1024:
        raise Refusal("installed-manual-bound")
    # The command requests en_US.UTF-8. Record decoder facts, never raw text or
    # a guessed encoding for an earlier unobserved host output.
    facts = {
        "manual_raw_sha256": sha(raw),
        "manual_size_bytes": len(raw),
        "manual_decoder": "strict-utf8",
    }
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        diagnostic_phase(
            "installed-lsbom-manual",
            **facts,
            manual_utf8_valid=False,
            manual_decode_error_offset=exc.start,
            manual_decode_error_width=exc.end - exc.start,
        )
        raise Refusal("installed-manual-encoding-unobserved") from exc
    diagnostic_phase("installed-lsbom-manual", **facts, manual_utf8_valid=True)
    # Linear bounded overstrike removal; no repeated full-text substitutions.
    normalized = []
    for char in text:
        if char == "\b":
            if not normalized or normalized[-1] in "\n\r":
                raise Refusal("installed-manual-controls")
            normalized.pop()
        elif ord(char) < 32 and char not in "\t\n\r\f":
            raise Refusal("installed-manual-controls")
        elif ord(char) == 127:
            raise Refusal("installed-manual-controls")
        elif ord(char) > 127 and unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}:
            # Includes bidi/format controls and Unicode line separators; they
            # cannot manufacture an ASCII field line or disappear in overstrike.
            raise Refusal("installed-manual-controls")
        else:
            normalized.append(char)
    text = "".join(normalized)
    fields = {}
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*([fmugs])\s+([A-Za-z][A-Za-z0-9 ()/.,:-]{0,180})\s*", line, flags=re.ASCII
        )
        if match:
            if match[1] in fields:
                raise Refusal("installed-manual-field-ambiguity")
            fields[match[1]] = match[2].strip()
    return {
        "raw_sha256": sha(raw),
        "requested_parameter_descriptions": fields,
        "all_requested_descriptions_observed": set(fields) == set("fmugs"),
        "output_schema_independently_qualified": False,
    }


def public_save(path, record):
    raw = (json.dumps(record, indent=2) + "\n").encode()
    if len(raw) > MAX_PUBLIC or path.exists() or path.is_symlink():
        raise Refusal("public-output-bound-or-existing")
    with path.open("xb") as stream:
        stream.write(raw)


def member_name(value: str, *, root=False) -> str:
    if value in {".", "./"} and root:
        return "."
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > 1024
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise Refusal("unsafe-member-name")
    if value.startswith("./"):
        value = value[2:]
    value = value.removesuffix("/")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise Refusal("unsafe-member-name")
    return value


def public_xml(raw: bytes) -> ET.Element:
    if not isinstance(raw, bytes) or len(raw) > MAX_XML:
        raise Refusal("xml-bound-or-entity")
    # Expat calls declaration handlers after decoding the input encoding, before
    # the declaration can introduce entities. TreeBuilder receives only events
    # that have already passed construction-time node/depth/text/metadata bounds.
    parser = expat.ParserCreate()
    builder = ET.TreeBuilder()
    depth, count, text_size, metadata_size = 0, 0, 0, 0

    def declaration(*_args):
        raise Refusal("xml-bound-or-entity")

    def start(tag, attrs):
        nonlocal depth, count, metadata_size
        if count >= MAX_NODES or depth > MAX_XML_DEPTH:
            raise Refusal("xml-node-or-depth-bound")
        metadata_size += len(tag) + sum(len(key) + len(value) for key, value in attrs.items())
        if (
            len(tag) > 128
            or len(attrs) > 32
            or metadata_size > MAX_XML_METADATA
            or any(len(key) > 128 or len(value) > 4096 for key, value in attrs.items())
        ):
            raise Refusal("xml-metadata-bound")
        count += 1
        depth += 1
        builder.start(tag, attrs)

    def end(tag):
        nonlocal depth
        builder.end(tag)
        depth -= 1

    def data(value):
        nonlocal text_size
        text_size += len(value)
        if text_size > MAX_XML_TEXT:
            raise Refusal("xml-text-bound")
        builder.data(value)

    def unsupported_markup(*_args):
        raise Refusal("xml-markup-unobserved")

    parser.StartDoctypeDeclHandler = declaration
    parser.EntityDeclHandler = declaration
    parser.UnparsedEntityDeclHandler = declaration
    parser.ExternalEntityRefHandler = declaration
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = data
    parser.CommentHandler = parser.ProcessingInstructionHandler = unsupported_markup
    try:
        parser.Parse(raw, True)
        return builder.close()
    except (expat.ExpatError, ET.ParseError) as exc:
        raise Refusal("xml-malformed") from exc


def bounded_decode(raw: bytes, *, gzip_stream=False, limit=MAX_EXPANDED) -> bytes:
    decoder = zlib.decompressobj(31 if gzip_stream else 15)
    try:
        data = decoder.decompress(raw, limit + 1)
    except zlib.error as exc:
        raise Refusal("compressed-stream-malformed") from exc
    if len(data) > limit or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data:
        raise Refusal("compressed-stream-bound-or-tail")
    return data


class Commands:
    """Bounded output/deadline, retained real Popen leader; no PID/group signals."""

    def __init__(self, private: Path | None = None):
        self.private = private
        self.uncertain = False
        self.calls = []
        self.started = time.monotonic()

    def capture(
        self,
        command: list[str],
        environment=None,
        *,
        timeout=180,
        limit=4 * 1024 * 1024,
        expected=0,
        stdin_payload: bytes | None = None,
        _receipt_stream=None,
    ) -> bytes:
        if self.uncertain:
            raise EvidenceError("command-lifetime-uncertain")
        if stdin_payload is not None and len(stdin_payload) > 65536:
            raise EvidenceError("command-stdin-bound")
        if _receipt_stream is not None and (
            type(self) is not MetadataCommands or type(_receipt_stream) is not ReceiptCommandStream
            or stdin_payload is not None or type(expected) is not int or expected != 0
            or not command_allowed(command, self.private) or command[:2] != ["/usr/sbin/pkgutil", "--files"]
        ):
            raise Refusal("metadata-command-or-aggregate-bound")
        if os.name == "posix":
            import signal

            if signal.getsignal(signal.SIGCHLD) != signal.SIG_DFL:
                raise EvidenceError("default-owned-child-reaping-required")
        remaining = 1500 - (time.monotonic() - self.started)
        if remaining <= 0:
            self.uncertain = True
            raise EvidenceError("harness-deadline")
        timeout = min(timeout, remaining)
        deadline = min(time.monotonic() + timeout, self.started + 1500)
        env = environment or {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        failed = threading.Event()
        stream_overflow = [threading.Event(), threading.Event()]
        stream_read_failed = [threading.Event(), threading.Event()]
        stdin_write_failed = threading.Event()

        def drain(stream, index, bound):
            try:
                while chunk := stream.read(_receipt_stream.read_limit(index) if _receipt_stream is not None else 65536):
                    if _receipt_stream is not None:
                        try:
                            _receipt_stream.consume(index, chunk)
                        except BaseException as exc:
                            _receipt_stream.fail(exc)
                            failed.set()
                            return
                        if index == 0:
                            continue
                    if len(buffers[index]) + len(chunk) > bound:
                        stream_overflow[index].set()
                        overflow.set()
                    else:
                        buffers[index].extend(chunk)
                if _receipt_stream is not None:
                    try:
                        _receipt_stream.eof(index)
                    except BaseException as exc:
                        _receipt_stream.fail(exc)
                        failed.set()
            except OSError:
                stream_read_failed[index].set()
                failed.set()

        command_stage = "launch"
        receipt_command_checkpoint(command_stage)
        child = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_payload is not None else subprocess.DEVNULL,
            env=env,
            cwd=ROOT,
        )
        threads = []
        reason = None
        cleanup_attempted = False
        cleanup_error = None
        try:
            threads = [
                threading.Thread(target=drain, args=(child.stdout, 0, limit), daemon=True),
                threading.Thread(target=drain, args=(child.stderr, 1, 1024 * 1024), daemon=True),
            ]
            if stdin_payload is not None:

                def feed():
                    try:
                        child.stdin.write(stdin_payload)
                        child.stdin.close()
                    except OSError:
                        stdin_write_failed.set()
                        failed.set()

                threads.append(threading.Thread(target=feed, daemon=True))
            command_stage = "pipe-start"
            for thread in threads:
                thread.start()
            command_stage = "wait"
            while True:
                if _receipt_stream is not None and _receipt_stream.failure_code is not None:
                    raise Refusal(_receipt_stream.failure_code)
                if overflow.is_set() or failed.is_set():
                    raise EvidenceError("command-output-bound-or-read")
                wait = deadline - time.monotonic()
                if wait <= 0:
                    raise EvidenceError("command-timeout")
                try:
                    exit_code = child.wait(timeout=min(0.1, wait))
                    break
                except subprocess.TimeoutExpired:
                    pass
            command_stage = "exit-deadline"
            if time.monotonic() >= deadline:
                raise EvidenceError("command-late-completed-exit")
            command_stage = "pipe-drain"
            for thread in threads:
                thread.join(max(0, min(1, deadline - time.monotonic())))
            if _receipt_stream is not None and _receipt_stream.failure_code is not None:
                raise Refusal(_receipt_stream.failure_code)
            if any(thread.is_alive() for thread in threads) or overflow.is_set() or failed.is_set():
                raise EvidenceError("command-pipe-lifetime-or-bound")
            command_stage = "output-deadline"
            if time.monotonic() >= deadline:
                raise EvidenceError("command-late-completed-output")
            if _receipt_stream is not None:
                if type(exit_code) is not int or exit_code != expected:
                    raise EvidenceError("command-unexpected-exit")
                _receipt_stream.ready()
        except BaseException as exc:
            self.uncertain = True
            reason = type(exc).__name__
            # The shared helper signals only this retained owned child. It does
            # not prove grandchildren gone; uncertainty blocks package cleanup.
            cleanup_attempted = True
            try:
                owned = load_module(
                    ROOT / "src/remote_ops_workspace/process_status.py", "row_linux_owned_cleanup"
                )
                owned.terminate_owned_process(child, timeout_seconds=5)
            except Exception as cleanup_exc:
                cleanup_error = type(cleanup_exc).__name__
            raise
        finally:
            self.calls.append(
                {
                    "step": len(self.calls) + 1,
                    "leader_exit_confirmed": child.returncode is not None,
                    "exit_code": child.returncode,
                    "execution_uncertain": self.uncertain,
                    "failure_type": reason,
                    "leader_cleanup_attempted": cleanup_attempted,
                    "leader_cleanup_error_type": cleanup_error,
                    "process_tree_cleanup": "not-proven",
                }
            )
            receipt_command_checkpoint(
                command_stage, streams=(bytes(buffers[0]), bytes(buffers[1])), limit=limit,
                flags=(stream_overflow[0].is_set(), stream_overflow[1].is_set(),
                    stream_read_failed[0].is_set(), stream_read_failed[1].is_set(),
                    stdin_write_failed.is_set()),
                live_threads=sum(thread.is_alive() for thread in threads),
            )
            if _receipt_stream is not None:
                receipt_stream_checkpoint(command_stage, _receipt_stream)
            if not any(thread.is_alive() for thread in threads):
                child.stdout.close()
                child.stderr.close()
                if child.stdin is not None and not child.stdin.closed:
                    child.stdin.close()
        receipt_command_checkpoint("private-output")
        if self.private is not None and _receipt_stream is None:
            serial = len(self.calls)
            (self.private / f"command-{serial}.stdout").write_bytes(buffers[0])
            (self.private / f"command-{serial}.stderr").write_bytes(buffers[1])
        receipt_command_checkpoint("expected-exit")
        if type(exit_code) is not int or exit_code != expected:
            raise EvidenceError("command-unexpected-exit")
        if _receipt_stream is not None:
            _receipt_stream.complete = True
        receipt_command_checkpoint("returned")
        if _receipt_stream is not None:
            receipt_stream_checkpoint("returned", _receipt_stream)
        return bytes(buffers[0] + buffers[1])


def strict_json(raw, maximum=MAX_NETWORK_METADATA):
    if len(raw) > maximum:
        raise Refusal("json-byte-bound")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal("duplicate-json-field")
            result[key] = value
        return result

    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Refusal("json-layout-unobserved") from exc


def positive_decimal(value):
    return isinstance(value, str) and re.fullmatch(r"[1-9][0-9]{0,19}", value) is not None


def commit(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def public_repo(value):
    return (
        isinstance(value, dict) and value.get("full_name") == REPO and value.get("private") is False
    )


def validate_event(values, event):
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_API_URL": "https://api.github.com",
    }
    if (
        not isinstance(event, dict)
        or any(values.get(key) != expected for key, expected in required.items())
        or not public_repo(event.get("repository"))
        or not commit(values.get("ROW_EXPECTED_SOURCE_SHA"))
        or not commit(values.get("GITHUB_SHA"))
        or not commit(values.get("GITHUB_WORKFLOW_SHA"))
        or any(
            not positive_decimal(values.get(key)) for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT")
        )
    ):
        raise Refusal("official-public-hosted-event-required")
    kind, ref, expected = (
        values.get("GITHUB_EVENT_NAME"),
        values.get("GITHUB_REF", ""),
        values["ROW_EXPECTED_SOURCE_SHA"],
    )
    if kind == "pull_request":
        pr = event.get("pull_request")
        if not isinstance(pr, dict):
            raise Refusal("same-repository-pr-source-required")
        head, base, number = pr.get("head"), pr.get("base"), event.get("number")
        if (
            event.get("action") not in {"opened", "synchronize", "reopened"}
            or type(number) is not int
            or not 0 < number <= 2147483647
            or not isinstance(head, dict)
            or not isinstance(base, dict)
            or not public_repo(head.get("repo"))
            or not public_repo(base.get("repo"))
            or base.get("ref") != "main"
            or head.get("sha") != expected
            or not commit(base.get("sha"))
            or ref != f"refs/pull/{number}/merge"
        ):
            raise Refusal("same-repository-pr-source-required")
    elif kind == "workflow_dispatch":
        if (
            expected != values["GITHUB_SHA"]
            or not isinstance(ref, str)
            or not re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9_./-]{0,199}", ref)
            or ".." in ref
            or "//" in ref
            or ref.endswith(("/", "."))
        ):
            raise Refusal("exact-branch-dispatch-source-required")
    else:
        raise Refusal("unsupported-event")
    workflow_path = ".github/workflows/macos-previous-pkg-metadata.yml"
    if values.get("GITHUB_WORKFLOW_REF") != REPO + "/" + workflow_path + "@" + ref:
        raise Refusal("exact-workflow-ref-required")
    return {
        "repository": REPO,
        "event": kind,
        "event_sha": values["GITHUB_SHA"],
        "source_sha": expected,
        "run_id": values["GITHUB_RUN_ID"],
        "run_attempt": values["GITHUB_RUN_ATTEMPT"],
        "ref_sha256": sha(ref.encode()),
        "workflow_sha": values["GITHUB_WORKFLOW_SHA"],
        "workflow_path": workflow_path,
    }


def hosted_gate(root):
    # Refuse local/fork/private claims before platform helpers, event-file reads,
    # library calls, subprocesses or network activity.
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_OS": "macOS",
        "RUNNER_ARCH": "X64",
        "GITHUB_REPOSITORY": REPO,
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_API_URL": "https://api.github.com",
    }
    if any(os.environ.get(key) != value for key, value in required.items()):
        raise Refusal("official-public-hosted-event-required")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    run = validate_event(os.environ, strict_json(regular(event_path, MAX_NETWORK_METADATA)))
    if (
        os.name != "posix"
        or sys.platform != "darwin"
        or platform.system() != "Darwin"
        or platform.machine() != "x86_64"
        or platform.mac_ver()[0].split(".")[0] != "15"
        or platform.python_version() != "3.14.7"
        or platform.python_implementation() != "CPython"
        or struct.calcsize("P") != 8
        or not root.is_absolute()
        or root.is_symlink()
        or any(parent.is_symlink() for parent in root.parents)
        or os.environ.get("GITHUB_WORKSPACE") != str(root)
        or root.resolve() != root
        or Path(__file__).absolute() != root / "scripts/observe_macos_previous_pkg.py"
        or Path(__file__).resolve() != Path(__file__).absolute()
    ):
        raise Refusal("actual-official-intel-macos15-required")
    return run


def load_module(path, name):
    # Commands can load only this source-bound owned-child cleanup helper.
    relative = "src/remote_ops_workspace/process_status.py"
    # Initial owned Git commands establish SOURCE_BINDING. Their failure still
    # needs retained-leader cleanup; a fixed reviewed byte pin covers bootstrap.
    expected = (
        BOOTSTRAP_CLEANUP_SHA if SOURCE_BINDING is None else SOURCE_BINDING["contracts"][relative]
    )
    if (
        path != ROOT / relative
        or path.resolve() != path
        or sha(regular(path, 2 * 1024 * 1024)) != expected
    ):
        raise Refusal("owned-cleanup-source-changed")
    raw = regular(path, 2 * 1024 * 1024)
    if sha(raw) != expected:
        raise Refusal("owned-cleanup-source-changed")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def command_allowed(command, private):
    if not isinstance(command, list) or any(not isinstance(part, str) for part in command):
        return False
    fixed = [
        ["/usr/bin/git", "rev-parse", "HEAD"],
        ["/usr/bin/git", "rev-parse", "HEAD^{tree}"],
        ["/usr/bin/git", "ls-files", "-z"],
        ["/usr/bin/git", "status", "--porcelain", "--untracked-files=no"],
        ["/usr/bin/git", "config", "--get", "remote.origin.url"],
        ["/usr/bin/man", "-P", "/bin/cat", "8", "lsbom"],
        ["/usr/sbin/pkgutil", "--pkgs"],
    ]
    if command in fixed:
        return True
    if isinstance(private, Path) and command == [
        "/usr/bin/lsbom",
        "-p",
        "fmugs",
        str(private / "Bom"),
    ]:
        return True
    return (
        len(command) == 3
        and command[0] == "/usr/sbin/pkgutil"
        and command[1] in {"--pkg-info-plist", "--files"}
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}", command[2]) is not None
    )


class MetadataCommands(Commands):
    """Canonical leader/deadline guards plus a read-only allowlist and aggregate cap."""

    def __init__(self):
        super().__init__()
        self.retained_output_bytes = 0
        self.output_lock = threading.Lock()

    def remaining(self):
        remaining = 1500 - (time.monotonic() - self.started)
        if self.uncertain or remaining <= 0:
            self.uncertain = True
            raise Refusal("metadata-overall-deadline")
        return remaining

    def capture(self, command, environment=None, **kwargs):
        if (
            environment is not None
            or not command_allowed(command, self.private)
            or len(self.calls) >= 4050
            or self.retained_output_bytes >= MAX_PRIVATE_COMMAND_BYTES
        ):
            raise Refusal("metadata-command-or-aggregate-bound")
        result = super().capture(
            command,
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "en_US.UTF-8",
                "LC_ALL": "en_US.UTF-8",
            },
            **kwargs,
        )
        self.retained_output_bytes += len(result)
        if self.retained_output_bytes > MAX_PRIVATE_COMMAND_BYTES:
            raise Refusal("metadata-command-or-aggregate-bound")
        self.remaining()
        return result


    def receipt_files(self, identifier, info_raw, parser):
        """Only the full validated pkgutil file namespace may use streaming."""
        command = ["/usr/sbin/pkgutil", "--files", identifier]
        if (not command_allowed(command, self.private)
                or len(self.calls) >= 4050 or self.retained_output_bytes >= MAX_PRIVATE_COMMAND_BYTES):
            raise Refusal("metadata-command-or-aggregate-bound")
        self.remaining()
        projection = ReceiptFilesProjection(info_raw, parser,
            maximum=min(MAX_RECEIPT_FILE_BYTES, MAX_PRIVATE_COMMAND_BYTES - self.retained_output_bytes))

        def charge(count):
            with self.output_lock:
                # Legacy counter name; streamed bytes are processed, never retained.
                self.retained_output_bytes += count
                if self.retained_output_bytes > MAX_PRIVATE_COMMAND_BYTES:
                    raise Refusal("metadata-command-or-aggregate-bound")

        stream = ReceiptCommandStream(projection, charge)
        super().capture(command, {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}, timeout=30, _receipt_stream=stream)
        self.remaining()
        return projection.result()


def source_binding(root, commands, expected):
    head = (
        commands.capture(["/usr/bin/git", "rev-parse", "HEAD"], timeout=30).decode("ascii").strip()
    )
    tree = (
        commands.capture(["/usr/bin/git", "rev-parse", "HEAD^{tree}"], timeout=30)
        .decode("ascii")
        .strip()
    )
    remote = (
        commands.capture(["/usr/bin/git", "config", "--get", "remote.origin.url"], timeout=30)
        .decode("ascii")
        .strip()
    )
    if (
        head != expected
        or not commit(tree)
        or remote not in {"https://github.com/" + REPO, "https://github.com/" + REPO + ".git"}
        or commands.capture(
            ["/usr/bin/git", "status", "--porcelain", "--untracked-files=no"], timeout=30
        )
    ):
        raise Refusal("exact-clean-official-source-required")
    raw_names = commands.capture(["/usr/bin/git", "ls-files", "-z"], timeout=30)
    try:
        names = raw_names.decode("utf-8").split("\0")
    except UnicodeError as exc:
        raise Refusal("tracked-source-path-layout") from exc
    if not names or names[-1] != "" or len(names) > 50001 or len(set(names[:-1])) != len(names) - 1:
        raise Refusal("tracked-source-path-layout")
    rows, total = [], 0
    for name in sorted(names[:-1]):
        if member_name(name) != name:
            raise Refusal("tracked-source-path-layout")
        path = root / name
        if path.resolve() != path:
            raise Refusal("tracked-source-path-link")
        data = regular(path, MAX_PKG, allow_empty=True)
        total += len(data)
        if total > MAX_SOURCE_TOTAL:
            raise Refusal("tracked-source-byte-bound")
        rows.append({"path": name, "sha256": sha(data)})
        commands.remaining()
    indexed = {row["path"]: row["sha256"] for row in rows}
    if not set(CONTRACTS).issubset(indexed):
        raise Refusal("canonical-metadata-contract-untracked")
    material = "".join(row["path"] + "\0" + row["sha256"] + "\n" for row in rows).encode()
    return {
        "head": head,
        "tree": tree,
        "checkout_bytes_sha256": sha(material),
        "tracked_file_count": len(rows),
        "tracked_total_bytes": total,
        "contracts": {name: indexed[name] for name in CONTRACTS},
    }


def redirect_allowed(url, asset):
    if not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
    ):
        return False
    if not asset:
        return not parsed.query and (
            parsed.hostname == "api.github.com"
            and parsed.path.startswith("/repos/" + REPO + "/")
            or parsed.hostname == "raw.githubusercontent.com"
            and re.fullmatch(
                "/"
                + re.escape(REPO)
                + r"/[0-9a-f]{40}/\.github/workflows/macos-previous-pkg-metadata\.yml",
                parsed.path,
            )
            is not None
        )
    if parsed.hostname == "github.com":
        return url == PREVIOUS["browser_download_url"]
    return parsed.hostname in {
        "release-assets.githubusercontent.com",
        "objects.githubusercontent.com",
    } and parsed.path.startswith("/github-production-release-asset/")


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, asset):
        self.asset = asset
        self.hops = 0
        self.hosts = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > 5 or not self.asset or not redirect_allowed(newurl, True):
            raise Refusal("official-download-redirect-refused")
        self.hosts.append(urllib.parse.urlsplit(newurl).hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, maximum, commands, destination=None):
    asset = destination is not None
    if not redirect_allowed(url, asset):
        raise Refusal("official-network-url-refused")
    redirects = RestrictedRedirect(asset)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), redirects)
    headers = {
        "User-Agent": "ROW-old-macos-pkg-metadata",
        "Accept": "application/octet-stream" if asset else "application/vnd.github+json",
        "Accept-Encoding": "identity",
    }
    if not asset:
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    raw, total, value = bytearray(), 0, hashlib.sha256()
    with opener.open(request, timeout=min(20, commands.remaining())) as response:
        if (
            response.status != 200
            or not redirect_allowed(response.geturl(), asset)
            or response.headers.get("Content-Encoding", "identity") != "identity"
        ):
            raise Refusal("official-network-response-refused")
        length = response.headers.get("Content-Length")
        if length is not None and (
            re.fullmatch(r"[0-9]{1,12}", length) is None
            or int(length) > maximum
            or asset
            and int(length) != maximum
        ):
            raise Refusal("official-network-length-refused")
        stream = destination.open("xb") if asset else None
        try:
            while True:
                commands.remaining()
                chunk = response.read1(min(65536, maximum - total + 1))
                commands.remaining()
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise Refusal("official-network-byte-bound")
                value.update(chunk)
                if stream is not None:
                    stream.write(chunk)
                else:
                    raw.extend(chunk)
        finally:
            if stream is not None:
                stream.close()
    return bytes(raw), {
        "size": total,
        "sha256": value.hexdigest(),
        "redirect_count": redirects.hops,
        "redirect_hosts": redirects.hosts,
        "authenticated_request": False,
    }


def validate_previous_identity(release, tag, asset):
    if (
        not all(isinstance(value, dict) for value in (release, tag, asset))
        or type(release.get("id")) is not int
        or release["id"] != PREVIOUS["release_id"]
        or release.get("tag_name") != PREVIOUS["tag"]
        or release.get("published_at") != PREVIOUS["published_at"]
        or release.get("draft") is not False
        or release.get("prerelease") is not PREVIOUS["prerelease"]
    ):
        raise Refusal("previous-publication-identity-changed")
    expected_object = {
        "sha": PREVIOUS["tag_commit"],
        "type": "commit",
        "url": "https://api.github.com/repos/" + REPO + "/git/commits/" + PREVIOUS["tag_commit"],
    }
    if tag.get("ref") != "refs/tags/" + PREVIOUS["tag"] or tag.get("object") != expected_object:
        raise Refusal("previous-tag-identity-changed")
    required = {
        "id": PREVIOUS["asset_id"],
        "name": PREVIOUS["asset_name"],
        "size": PREVIOUS["size"],
        "digest": "sha256:" + PREVIOUS["sha256"],
        "browser_download_url": PREVIOUS["browser_download_url"],
        "state": "uploaded",
    }
    if (
        type(asset.get("id")) is not int
        or type(asset.get("size")) is not int
        or any(asset.get(key) != value for key, value in required.items())
    ):
        raise Refusal("previous-asset-identity-changed")
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > 500:
        raise Refusal("previous-release-asset-membership-changed")
    matches = [
        row for row in assets if isinstance(row, dict) and row.get("id") == PREVIOUS["asset_id"]
    ]
    if (
        len(matches) != 1
        or type(matches[0].get("id")) is not int
        or type(matches[0].get("size")) is not int
        or any(matches[0].get(key) != value for key, value in required.items())
    ):
        raise Refusal("previous-release-asset-membership-changed")
    return {
        "release_id": PREVIOUS["release_id"],
        "prerelease": PREVIOUS["prerelease"],
        "tag": PREVIOUS["tag"],
        "tag_commit": PREVIOUS["tag_commit"],
        "asset_id": PREVIOUS["asset_id"],
        "size": PREVIOUS["size"],
        "sha256": PREVIOUS["sha256"],
    }


def previous_identity(commands, private, suffix):
    root = "https://api.github.com/repos/" + REPO + "/"
    values, digests = [], []
    for name in ("releases/382583184", "git/ref/tags/v1.0.24", "releases/assets/544041419"):
        raw, facts = fetch(root + name, MAX_NETWORK_METADATA, commands)
        values.append(strict_json(raw))
        digests.append(facts["sha256"])
        (private / ("public-api-" + str(len(values)) + "-" + suffix + ".json")).write_bytes(raw)
    return {**validate_previous_identity(*values), "metadata_sha256": digests}


def executed_workflow_binding(commands, source, run):
    workflow_url = (
        "https://raw.githubusercontent.com/"
        + REPO
        + "/"
        + run["workflow_sha"]
        + "/"
        + run["workflow_path"]
    )
    workflow_raw, workflow_network = fetch(workflow_url, 256 * 1024, commands)
    if sha(workflow_raw) != source["contracts"][run["workflow_path"]]:
        raise Refusal("executed-workflow-contract-mismatch")
    return workflow_network


def safe_directory(path, root):
    if not path.is_absolute() or root not in path.parents or path.resolve() != path:
        raise Refusal("owned-directory-containment")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not stat.S_ISDIR(path.lstat().st_mode):
        raise Refusal("owned-directory-containment")


def publication_recheck(before, after):
    # Download counts and other mutable public API fields may change. Immutable
    # release/tag/asset identity was revalidated separately on both responses.
    keys = {"release_id", "prerelease", "tag", "tag_commit", "asset_id", "size", "sha256"}
    if (
        not isinstance(before, dict)
        or not isinstance(after, dict)
        or before.get("prerelease") is not PREVIOUS["prerelease"]
        or after.get("prerelease") is not PREVIOUS["prerelease"]
        or any(before.get(key) != after.get(key) for key in keys)
    ):
        raise Refusal("previous-publication-identity-changed")
    return {
        "before_metadata_sha256": before["metadata_sha256"],
        "after_metadata_sha256": after["metadata_sha256"],
        "immutable_identity_equal": True,
    }


def command_stream_facts(streams, limit, flags, live_threads):
    """Bounded retained-buffer snapshots only, never a full output/prefix claim."""
    if (
        type(streams) is not tuple or len(streams) != 2
        or any(type(raw) is not bytes for raw in streams)
        or type(limit) is not int or not 1 <= limit <= 4 * 1024 * 1024
        or len(streams[0]) > limit or len(streams[1]) > 1024 * 1024
        or type(flags) is not tuple or len(flags) != 5
        or any(type(value) is not bool for value in flags)
        or type(live_threads) is not int or not 0 <= live_threads <= 3
    ):
        raise Refusal("diagnostic-phase-refused")
    return {
        "command_stdout_bytes": len(streams[0]), "command_stdout_sha256": sha(streams[0]),
        "command_stdout_bound_bytes": limit,
        "command_stderr_bytes": len(streams[1]), "command_stderr_sha256": sha(streams[1]),
        "command_stderr_bound_bytes": 1024 * 1024,
        "command_stdout_overflow_observed": flags[0], "command_stderr_overflow_observed": flags[1],
        "command_stdout_read_error_observed": flags[2], "command_stderr_read_error_observed": flags[3],
        "command_stdin_write_error_observed": flags[4], "command_live_pipe_threads": live_threads,
    }


def receipt_command_checkpoint(stage, *, streams=None, limit=None, flags=None, live_threads=None):
    # No new I/O or diagnostic scope for Git, manual, BOM or other commands.
    if (
        REFUSAL_CONTEXT is not None
        and REFUSAL_CONTEXT["phase"] == "receipt-info-and-files"
        and REFUSAL_CONTEXT["observed"].get("receipt_operation") in {"info", "files"}
    ):
        facts = {} if streams is None else command_stream_facts(streams, limit, flags, live_threads)
        diagnostic_phase("receipt-info-and-files", command_stage=stage, **facts)


def diagnostic_phase(phase, **facts):
    if phase not in {
        "executed-workflow-bind",
        "previous-public-identity-and-download",
        "previous-toc",
        "readonly-system-tool",
        "package-info",
        "installed-lsbom-manual",
        "installed-bom-reader",
        "receipt-namespace",
        "receipt-info-and-files",
        "declared-filesystem-capabilities",
        "source-publication-and-input-readback",
        "public-output",
    }:
        raise Refusal("diagnostic-phase-refused")
    if REFUSAL_CONTEXT is not None:
        REFUSAL_CONTEXT["phase"] = phase
        if phase == "receipt-info-and-files" and "receipt_operation" in facts:
            # An attempted operation cannot inherit the preceding command's
            # captured streams; a new receipt cannot inherit old info/files hashes.
            for key in COMMAND_DIAGNOSTIC_KEYS:
                REFUSAL_CONTEXT["observed"].pop(key, None)
            if facts["receipt_operation"] == "info":
                for key in ("receipt_info_sha256", "receipt_files_sha256"):
                    REFUSAL_CONTEXT["observed"].pop(key, None)
        if phase == "readonly-system-tool":
            # A new literal tool must not inherit another tool's stat facts.
            for key in (
                "system_tool_index",
                "system_tool_size_bytes",
                "system_tool_link_count",
                "system_tool_is_regular",
            ):
                REFUSAL_CONTEXT["observed"].pop(key, None)
        if phase == "installed-lsbom-manual":
            for key in (
                "manual_raw_sha256", "manual_size_bytes", "manual_decoder", "manual_utf8_valid",
                "manual_decode_error_offset", "manual_decode_error_width",
            ):
                REFUSAL_CONTEXT["observed"].pop(key, None)
        if phase == "installed-bom-reader":
            # Each call supplies a complete current projection; no stale row or
            # decoder failure may be inherited by a later capture or success.
            for key in (
                "bom_output_sha256", "bom_size_bytes", "bom_decoder", "bom_utf8_valid",
                "bom_decode_error_offset", "bom_decode_error_width", "bom_row_count",
                "bom_failed_row_index", "bom_failed_column_count", "bom_failed_line_size_bytes",
                "bom_failed_line_sha256", "bom_failed_layout_class",
                *("bom_failed_column_" + str(column) + suffix
                  for column in range(1, 5)
                  for suffix in ("_class", "_characters", "_size_bytes")),
            ):
                REFUSAL_CONTEXT["observed"].pop(key, None)
        for key, value in facts.items():
            if key in {
                "whole_pkg_sha256",
                "toc_sha256",
                "bom_output_sha256",
                "receipt_info_sha256",
                "receipt_files_sha256",
            }:
                if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
                    REFUSAL_CONTEXT["observed"][key] = value
            elif key in {"component_count", "receipt_namespace_count", "receipts_queried"}:
                if type(value) is int and 0 <= value <= MAX_ROWS:
                    REFUSAL_CONTEXT["observed"][key] = value
            elif phase == "receipt-info-and-files":
                if (
                    (key == "receipt_operation" and type(value) is str and value in RECEIPT_OPERATIONS)
                    or (key == "receipt_query_index" and type(value) is int and 1 <= value <= 2000)
                    or (key == "command_stage" and type(value) is str and value in COMMAND_DIAGNOSTIC_STAGES)
                    or (key in {"command_stdout_sha256", "command_stderr_sha256"}
                        and type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value))
                    or (key in {"command_stdout_bytes", "command_stdout_bound_bytes"}
                        and type(value) is int and 0 <= value <= 4 * 1024 * 1024)
                    or (key in {"command_stderr_bytes", "command_stderr_bound_bytes"}
                        and type(value) is int and 0 <= value <= 1024 * 1024)
                    or (key in {"command_stdout_overflow_observed", "command_stderr_overflow_observed",
                        "command_stdout_read_error_observed", "command_stderr_read_error_observed",
                        "command_stdin_write_error_observed"} and type(value) is bool)
                    or (key == "command_live_pipe_threads" and type(value) is int and 0 <= value <= 3)
                    or (key in {"receipt_stream_stdout_sha256", "receipt_stream_stderr_sha256"}
                        and type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value))
                    or (key == "receipt_stream_stdout_bytes" and type(value) is int
                        and 0 <= value <= MAX_RECEIPT_FILE_BYTES + 1)
                    or (key == "receipt_stream_stdout_bound_bytes" and type(value) is int
                        and 1 <= value <= MAX_RECEIPT_FILE_BYTES)
                    or (key == "receipt_stream_stderr_bytes" and type(value) is int
                        and 0 <= value <= 1024 * 1024 + 1)
                    or (key == "receipt_stream_stderr_bound_bytes" and type(value) is int and value == 1024 * 1024)
                    or (key in {"receipt_stream_stdout_eof", "receipt_stream_stderr_eof",
                        "receipt_stream_complete", "receipt_stream_hashes_partial"} and type(value) is bool)
                ):
                    REFUSAL_CONTEXT["observed"][key] = value
            elif phase == "readonly-system-tool":
                if (
                    (key == "system_tool_index" and type(value) is int and 0 <= value < 5)
                    or (
                        key == "system_tool_size_bytes"
                        and type(value) is int
                        and 0 <= value <= (1 << 63) - 1
                    )
                    or (
                        key == "system_tool_link_count"
                        and type(value) is int
                        and 0 <= value <= MAX_ROWS
                    )
                    or (key == "system_tool_is_regular" and type(value) is bool)
                ):
                    REFUSAL_CONTEXT["observed"][key] = value

            elif phase == "installed-lsbom-manual":
                if (
                    (key == "manual_raw_sha256" and isinstance(value, str)
                     and re.fullmatch(r"[0-9a-f]{64}", value))
                    or (key == "manual_size_bytes" and type(value) is int and 0 <= value <= 512 * 1024)
                    or (key == "manual_decoder" and type(value) is str and value == "strict-utf8")
                    or (key == "manual_utf8_valid" and type(value) is bool)
                    or (key == "manual_decode_error_offset" and type(value) is int and 0 <= value <= 512 * 1024)
                    or (key == "manual_decode_error_width" and type(value) is int and 1 <= value <= 4)
                ):
                    REFUSAL_CONTEXT["observed"][key] = value

            elif phase == "installed-bom-reader":
                if (
                    (key == "bom_size_bytes" and type(value) is int and 0 <= value <= MAX_PUBLIC)
                    or (key == "bom_decoder" and type(value) is str and value == "strict-utf8")
                    or (key == "bom_utf8_valid" and type(value) is bool)
                    or (key == "bom_decode_error_offset" and type(value) is int and 0 <= value <= MAX_PUBLIC)
                    or (key == "bom_decode_error_width" and type(value) is int and 1 <= value <= 4)
                    or (key == "bom_row_count" and type(value) is int and 0 <= value <= MAX_PUBLIC + 1)
                    or (key == "bom_failed_row_index" and type(value) is int and 1 <= value <= MAX_ROWS)
                    or (key == "bom_failed_column_count" and type(value) is int and 1 <= value <= MAX_PUBLIC + 1)
                    or (key == "bom_failed_line_size_bytes" and type(value) is int and 0 <= value <= MAX_PUBLIC)
                    or (key == "bom_failed_line_sha256" and type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value))
                    or (key == "bom_failed_layout_class" and type(value) is str
                        and value in {"column-count", "mode-field", "numeric-field"})
                    or (re.fullmatch(r"bom_failed_column_[1-4]_class", key) and type(value) is str
                        and value in {"absent", "empty", "ascii-octal-digits", "ascii-decimal-digits", "ascii-other", "non-ascii"})
                    or (re.fullmatch(r"bom_failed_column_[1-4]_(?:characters|size_bytes)", key)
                        and type(value) is int and 0 <= value <= MAX_PUBLIC)
                ):
                    REFUSAL_CONTEXT["observed"][key] = value

def readonly_system_tool_hashes():
    result = {}
    for index, name in enumerate(READONLY_SYSTEM_TOOLS):
        # The fixed index identifies the attempted literal path even if lstat
        # itself fails. Metadata is bounded public stat data, not tool output.
        diagnostic_phase("readonly-system-tool", system_tool_index=index)
        path = Path(name)
        before = path.lstat()
        diagnostic_phase(
            "readonly-system-tool",
            system_tool_index=index,
            system_tool_size_bytes=before.st_size,
            system_tool_link_count=before.st_nlink,
            system_tool_is_regular=stat.S_ISREG(before.st_mode),
        )
        # Only these literal root-owned tools may have stable system hardlinks.
        result[name] = sha(readonly_system_tool_bytes(index))
    return result


def public_refusal(code):
    # Only a successfully guarded/bound source may publish a failure record.
    # A failed capture never acquires an observations-complete/approval claim.
    if REFUSAL_CONTEXT is None or SOURCE_BINDING is None:
        return
    destination = ROOT / REPORT
    safe_directory(destination.parent, ROOT)
    record = {
        "schema": "row.macos-previous-pkg-metadata.v1",
        "status": "refused",
        "source": REFUSAL_CONTEXT["source"],
        "run": REFUSAL_CONTEXT["run"],
        "phase": REFUSAL_CONTEXT["phase"],
        "reason_code": code if code in REFUSAL_CODES else "metadata-input-or-runtime-refusal",
        "observed": REFUSAL_CONTEXT["observed"],
        "source_unchanged": "not-established",
        "installer_execution": False,
        "app_execution": False,
        "encryption_execution": False,
        "approval": False,
        "signing_trust": False,
        "readiness_credit": 0,
    }
    public_save(destination, record)
    emit_receipt_marker()


def emit_receipt_marker():
    # GitHub's step output enables upload only after our exclusive public write,
    # including safe refusal receipts. A preexisting arbitrary file is not an
    # upload input. This file is runner protocol, never captured as evidence.
    path = Path(os.environ.get("GITHUB_OUTPUT", ""))
    if (
        REFUSAL_CONTEXT is None
        or SOURCE_BINDING is None
        or not path.is_absolute()
        or path.resolve() != path
        or any(parent.is_symlink() for parent in path.parents)
    ):
        raise Refusal("runner-output-protocol-shape")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 65536:
        raise Refusal("runner-output-protocol-shape")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "wb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise Refusal("runner-output-protocol-shape")
        stream.write(b"public_receipt=saved\n")
        stream.flush()
        after = os.fstat(stream.fileno())
    after_path = path.lstat()
    if after.st_size != before.st_size + 21 or (after.st_dev, after.st_ino, after.st_size) != (
        after_path.st_dev,
        after_path.st_ino,
        after_path.st_size,
    ):
        raise Refusal("runner-output-protocol-shape")


def observe(root):
    global ROOT, SOURCE_BINDING, REFUSAL_CONTEXT
    SOURCE_BINDING, REFUSAL_CONTEXT = None, None
    run = hosted_gate(root)
    ROOT = root
    commands = MetadataCommands()
    # No helper module imports: only already reviewed pure parser code is defined.
    before = source_binding(root, commands, run["source_sha"])
    SOURCE_BINDING = before
    REFUSAL_CONTEXT = {
        "source": before,
        "run": run,
        "phase": "executed-workflow-bind",
        "observed": {},
    }
    parent = root / ".tmp"
    safe_directory(parent, root)
    private = parent / ("macos-previous-pkg-metadata-" + uuid.uuid4().hex)
    private.mkdir(mode=0o700)
    if stat.S_IMODE(private.stat().st_mode) != 0o700 or private.resolve() != private:
        raise Refusal("private-metadata-directory-shape")
    commands.private = private
    # GitHub's workflow commit is distinct from the checked-out PR head. Observe
    # its actual public bytes and require equality to the bound source contract;
    # never infer workflow-byte identity from a head/merge SHA relationship.
    workflow_network = executed_workflow_binding(commands, before, run)
    diagnostic_phase("previous-public-identity-and-download")
    print("phase=previous-public-identity-and-download", flush=True)
    identity = previous_identity(commands, private, "before")
    previous = private / PREVIOUS["asset_name"]
    _, network = fetch(PREVIOUS["browser_download_url"], PREVIOUS["size"], commands, previous)
    if network["size"] != PREVIOUS["size"] or network["sha256"] != PREVIOUS["sha256"]:
        raise Refusal("previous-whole-package-bytes-mismatch")
    raw = regular(previous, MAX_PKG)
    if len(raw) != PREVIOUS["size"] or sha(raw) != PREVIOUS["sha256"]:
        raise Refusal("previous-whole-package-bytes-mismatch")
    print("phase=previous-toc-and-readonly-system-metadata", flush=True)
    diagnostic_phase("previous-toc", whole_pkg_sha256=sha(raw))
    parser = sys.modules[__name__]
    package, material = package_projection(raw, parser)
    diagnostic_phase(
        "previous-toc", toc_sha256=package["toc_sha256"], component_count=len(package["components"])
    )
    record = {
        "schema": "row.macos-previous-pkg-metadata.v1",
        "status": "observations-with-unresolved-gates",
        "source": before,
        "run": run,
        "executed_workflow": workflow_network,
        "previous_identity": identity,
        "previous_download": network,
        "previous": package,
        "candidate_package": "not-captured",
        "readiness_credit": 0,
        "approval": False,
        "signing_trust": False,
        "installer_execution": False,
        "app_execution": False,
        "encryption_execution": False,
        "physical_ownership_proof": False,
        "process_tree_cleanup": "not-proven",
    }
    record["system_tool_sha256"] = readonly_system_tool_hashes()
    if "PackageInfo" in material:
        diagnostic_phase("package-info")
        record["package_info"] = package_info_projection(material["PackageInfo"], parser)
    if "Bom" in material:
        if not material["Bom"].startswith(b"BOMStore"):
            raise Refusal("bom-magic-unobserved")
        with (private / "Bom").open("xb") as stream:
            stream.write(material["Bom"])
        diagnostic_phase("installed-lsbom-manual")
        record["lsbom_manual"] = manual_projection(
            commands.capture(
                ["/usr/bin/man", "-P", "/bin/cat", "8", "lsbom"], timeout=30, limit=512 * 1024
            )
        )
        diagnostic_phase("installed-bom-reader")
        bom_raw = commands.capture(
            ["/usr/bin/lsbom", "-p", "fmugs", str(private / "Bom")], timeout=180
        )
        diagnostic_phase("installed-bom-reader", bom_output_sha256=sha(bom_raw))
        record["bom"] = bom_projection(bom_raw, parser)
    diagnostic_phase("receipt-namespace")
    namespace = commands.capture(["/usr/sbin/pkgutil", "--pkgs"], timeout=30, limit=65536)
    try:
        identifiers = namespace.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise Refusal("receipt-namespace-encoding") from exc
    if (
        len(identifiers) > 2000
        or len({alias(item) for item in identifiers}) != len(identifiers)
        or any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,255}", item) is None for item in identifiers
        )
    ):
        raise Refusal("receipt-namespace-bound-or-alias")
    receipts, hashes = [], []
    diagnostic_phase(
        "receipt-info-and-files", receipt_namespace_count=len(identifiers), receipts_queried=0
    )
    for query_index, identifier in enumerate(identifiers, 1):
        diagnostic_phase("receipt-info-and-files", receipt_query_index=query_index, receipt_operation="info")
        info = commands.capture(
            ["/usr/sbin/pkgutil", "--pkg-info-plist", identifier], timeout=30, limit=65536
        )
        diagnostic_phase("receipt-info-and-files", receipt_operation="files")
        row = commands.receipt_files(identifier, info, parser)
        diagnostic_phase("receipt-info-and-files", receipt_operation="projection")
        diagnostic_phase(
            "receipt-info-and-files", receipt_info_sha256=row["info_sha256"], receipt_files_sha256=row["files_sha256"]
        )
        hashes.append(
            {
                "identifier_sha256": sha(identifier.encode()),
                "info_sha256": row["info_sha256"],
                "files_sha256": row["files_sha256"],
            }
        )
        diagnostic_phase("receipt-info-and-files", receipts_queried=len(hashes))
        diagnostic_phase("receipt-info-and-files", receipt_operation="relevance")
        if (
            alias(identifier) == alias(APP_ID)
            or row["lexical_app_claim_count"]
            or row["data_namespace_claim_count"]
        ):
            if len(receipts) >= 64:
                raise Refusal("relevant-receipt-projection-bound")
            receipts.append(
                {
                    "is_exact_own_identifier": identifier == APP_ID,
                    "identifier_is_own_alias": alias(identifier) == alias(APP_ID)
                    and identifier != APP_ID,
                    "identifier_sha256": sha(identifier.encode()),
                    **row,
                }
            )
    record["receipts"] = {
        "namespace_sha256": sha(namespace),
        "namespace_count": len(identifiers),
        "all_listed_receipts_queried": True,
        "query_digest": sha(json.dumps(hashes, sort_keys=True).encode()),
        "relevant": receipts,
        "physical_namespace_complete": False,
    }
    diagnostic_phase("declared-filesystem-capabilities")
    record["filesystem"] = {
        "applications": observe_capabilities(Path("/Applications")),
        "private_parent": observe_capabilities(parent),
        "same_device_observed": Path("/Applications").stat().st_dev == parent.stat().st_dev,
        "installed_sdk_header_qualification": "not-observed",
        "unicode_empirical_probe": "not-enabled",
    }
    print("phase=source-publication-and-input-readback", flush=True)
    diagnostic_phase("source-publication-and-input-readback")
    readback = publication_recheck(identity, previous_identity(commands, private, "after"))
    if (
        sha(regular(previous, MAX_PKG)) != PREVIOUS["sha256"]
        or commands.capture(["/usr/sbin/pkgutil", "--pkgs"], timeout=30, limit=65536) != namespace
        or source_binding(root, commands, run["source_sha"]) != before
        or commands.uncertain
    ):
        raise Refusal("metadata-input-source-or-command-uncertain")
    record["source_unchanged"] = True
    record["previous_publication_rechecked"] = True
    record["publication_readback"] = readback
    record["command_leader_records"] = commands.calls
    record["unresolved"] = [
        "current-candidate-package-and-native-transition",
        "payload-cpio-and-all-script-content-inventory",
        "bom-column-semantics-and-payload-agreement",
        "installed-sdk-header-qualification",
        "empirical-unicode-and-physical-firmlink-ownership",
        "receipt-content-concurrency",
        "process-descendant-cleanup",
    ]
    destination = root / REPORT
    diagnostic_phase("public-output")
    safe_directory(destination.parent, root)
    commands.remaining()
    public_save(destination, record)
    commands.remaining()
    emit_receipt_marker()
    return {
        "status": record["status"],
        "output_sha256": sha(regular(destination, MAX_PUBLIC)),
        "actual_native_transition": False,
        "readiness_credit": 0,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", nargs="?", default="plan", choices=("plan", "capture", "run"))
    args = ap.parse_args(argv)
    if args.action == "plan":
        print(
            json.dumps(
                {
                    "status": "old-pkg-metadata-plan",
                    "previous": PREVIOUS,
                    "installer_execution": False,
                    "candidate_capture": False,
                    "readiness_credit": 0,
                }
            )
        )
        return 0
    if args.action == "run":
        print("privileged-run-disabled", file=sys.stderr)
        return 1
    try:
        print(json.dumps(observe(Path.cwd().resolve())))
        return 0
    except Exception as exc:
        code = (
            exc.args[0]
            if isinstance(exc, Refusal) and len(exc.args) == 1
            else "metadata-input-or-runtime-refusal"
        )
        if not isinstance(code, str) or code not in REFUSAL_CODES:
            code = "metadata-input-or-runtime-refusal"
        try:
            public_refusal(code)
        except Exception:
            # The original nonzero refusal is retained even if its public
            # diagnostic cannot be saved. Existing/unsafe outputs are refused.
            pass
        print("macos-previous-pkg-metadata-refused:" + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
