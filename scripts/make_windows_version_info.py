"""Generate the Windows PE version resource shared by the native launchers."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


def version_resource(version: str, product_name: str, publisher: str) -> str:
    if not re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", version):
        raise ValueError("Windows release version must contain three numeric components")
    numbers = tuple(map(int, version.split(".")))
    if any(number > 65535 for number in numbers):
        raise ValueError("Windows release version components must fit in 16 bits")
    fixed = (*numbers, 0)
    strings = {
        "CompanyName": publisher,
        "FileDescription": product_name,
        "FileVersion": version,
        "ProductName": product_name,
        "ProductVersion": version,
    }
    entries = "\n".join(f"            StringStruct({key!r}, {value!r})," for key, value in strings.items())
    return f"""VSVersionInfo(
    ffi=FixedFileInfo(
        filevers={fixed!r}, prodvers={fixed!r}, mask=63, flags=0,
        OS=262148, fileType=1, subtype=0, date=(0, 0),
    ),
    kids=[
        StringFileInfo([StringTable('040904B0', [
{entries}
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--publisher", required=True)
    args = parser.parse_args()
    try:
        text = version_resource(args.version, args.product_name, args.publisher)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
