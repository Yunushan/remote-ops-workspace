"""Remove hosted CPython search directories from staged Linux ELF RUNPATHs."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from pathlib import Path

# The setup-python release archives embed this absolute build-time directory.
# Other absolute paths, RPATH, and loader tokens such as $ORIGIN are site policy.
TOOLCACHE_LIB = re.compile(rb"/opt/hostedtoolcache/Python/[^/:]+/(?:x64|arm64|x86|arm)/lib/?")


def without_toolcache_runpath(data: bytes) -> bytes:
    if not data.startswith(b"\x7fELF") or b"/opt/hostedtoolcache/Python/" not in data:
        return data
    if data[5:7] != b"\x01\x01" or data[4] not in (1, 2):
        raise ValueError("Unsupported ELF encoding in Linux packaging input")
    wide = data[4] == 2
    header = struct.unpack_from("<16sHHIQQQIHHHHHH" if wide else "<16sHHIIIIIHHHHHH", data)
    section = struct.Struct("<IIQQQQIIQQ" if wide else "<IIIIIIIIII")
    dynamic = struct.Struct("<QQ" if wide else "<II")
    if header[11] != section.size or not header[12]:
        raise ValueError("Unsupported ELF section table")
    sections = [section.unpack_from(data, header[6] + i * section.size) for i in range(header[12])]
    tables = [s for s in sections if s[1] == 6]  # SHT_DYNAMIC
    if not tables:
        return data
    (table,) = tables
    strings = sections[table[6]]
    if strings[1] != 3 or table[9] != dynamic.size:
        raise ValueError("Invalid ELF dynamic string table")
    pool = data[strings[4] : strings[4] + strings[5]]
    start, end = table[4], table[4] + table[5]
    if end > len(data) or len(pool) != strings[5]:
        raise ValueError("Truncated ELF dynamic data")
    entries = list(dynamic.iter_unpack(data[start:end]))
    active = next(i for i, (tag, _) in enumerate(entries) if not tag)
    positions = [i for i, (tag, _) in enumerate(entries[:active]) if tag == 29]  # DT_RUNPATH
    if not positions:
        return data
    (index,) = positions
    offset = entries[index][1]
    nul = pool.index(b"\0", offset)
    paths = pool[offset:nul].split(b":")
    retained = [p for p in paths if not TOOLCACHE_LIB.fullmatch(p)]
    if retained == paths:
        return data
    result = bytearray(data)
    field = start + index * dynamic.size
    if not retained:
        # Keep the original string pool and the order of all other tags intact.
        # Leaving an empty RUNPATH could introduce a current-directory search.
        first_null = start + active * dynamic.size
        result[field:first_null] = data[field + dynamic.size : first_null + dynamic.size]
    else:
        value = b":".join(retained) + b"\0"
        existing = pool.find(value)
        if existing >= 0:
            dynamic.pack_into(result, field, 29, existing)
        else:
            # Linkers can share suffixes in .dynstr. Only overwrite private
            # storage. Conservatively treat aligned words in every section
            # linked to this string table as possible string offsets.
            first = pool.rfind(b"\0", 0, offset) + 1
            for s in sections:
                if s[6] != table[6] or s[5] == 0:
                    continue
                for at in range(s[4], s[4] + s[5] - 3, 4):
                    if field <= at < field + dynamic.size:
                        continue
                    if first <= struct.unpack_from("<I", data, at)[0] <= nul:
                        raise ValueError("Mixed hosted RUNPATH shares ELF string storage")
            pos = strings[4] + offset
            result[pos : pos + len(value)] = value
    return bytes(result)


def stage_binaries(binaries: list, directory: Path) -> list:
    staged = []
    changes = {}
    for name, source, kind in binaries:
        if kind in {"BINARY", "EXTENSION"}:
            original = Path(source).read_bytes()
            cleaned = without_toolcache_runpath(original)
            if cleaned is not original:
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError(f"Invalid PyInstaller binary destination: {name}")
                hashes = {
                    "input_sha256": hashlib.sha256(original).hexdigest(),
                    "staged_sha256": hashlib.sha256(cleaned).hexdigest(),
                }
                if name in changes and changes[name] != hashes:
                    raise ValueError(f"Conflicting staged ELF inputs for {name}")
                copy = directory / relative
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_bytes(cleaned)
                source = str(copy)
                changes[name] = hashes
        staged.append((name, source, kind))
    directory.with_suffix(".json").write_text(
        json.dumps(changes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return staged


def prepare_spec(path: Path) -> None:
    # PyInstaller's locked makespec CLI writes this boundary between collection
    # and one-file assembly. Fail explicitly if its generated recipe changes.
    marker = "\npyz = PYZ(a.pure)\n"
    spec = path.read_text(encoding="utf-8")
    if spec.count(marker) != 1:
        raise ValueError("Unrecognized PyInstaller one-file spec")
    insertion = (
        "\nfrom pathlib import Path\n"
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
        "from linux_frozen_runpaths import stage_binaries\n"
        "staged = stage_binaries(a.binaries + pyz.dependencies, Path(SPECPATH) / 'staged-elf')\n"
        "a.binaries, pyz.dependencies = staged[:len(a.binaries)], staged[len(a.binaries):]\n"
    )
    # PYZ adds separate bootstrap extensions such as _struct and zlib after Analysis.
    path.write_text(spec.replace(marker, marker + insertion), encoding="utf-8")


if __name__ == "__main__":
    prepare_spec(Path(sys.argv[1]))
