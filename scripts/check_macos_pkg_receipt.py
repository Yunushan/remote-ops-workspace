"""Check stock macOS PKG metadata and the installed receipt for a native smoke run."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from xml.etree import ElementTree

APP_ID = "io.github.remoteopsworkspace.app"
APP = "Applications/Remote Ops Workspace.app"
LAUNCHER = f"{APP}/Contents/MacOS/Remote Ops Workspace"
COMPONENT = "remote-ops-workspace-component.pkg"
METADATA_LIMIT = 64 * 1024
PATH_LIST_LIMIT = 4 * 1024 * 1024


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_text(path: Path, limit: int) -> str:
    require(path.is_file() and not path.is_symlink(), f"missing or linked PKG evidence file {path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(0 < len(raw) <= limit, f"invalid PKG evidence size for {path.name}")
    return raw.decode("utf-8")


def read_xml(path: Path) -> ElementTree.Element:
    text = read_text(path, METADATA_LIMIT)
    require(re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE) is None,
            "PKG metadata must not declare a document type or entity")
    return ElementTree.fromstring(text)


def check_package(expanded: Path, version: str) -> None:
    distribution = read_xml(expanded / "Distribution")
    supported = distribution.findall("./volume-check/allowed-os-versions/os-version")
    require(distribution.tag == "installer-gui-script" and len(supported) == 1
            and supported[0].attrib in ({"min": "14.4"}, {"min": "14.4.0"}),
            "PKG distribution must require macOS 14.4 or later")
    references = [(entry.get("id"), entry.get("version"), entry.text.strip().removeprefix("#"))
                  for entry in distribution.findall("pkg-ref") if entry.text and entry.text.strip()]
    require(references == [(APP_ID, version, COMPONENT)],
            "PKG distribution must reference the exact application component and version")
    component = expanded / COMPONENT
    require(component.is_dir() and not component.is_symlink(), "expected the expanded stock PKG component")
    info = read_xml(component / "PackageInfo")
    expected = {"identifier": APP_ID, "version": version, "install-location": "/", "auth": "root", "relocatable": "false"}
    require(info.tag == "pkg-info" and all(info.get(key) == value for key, value in expected.items()),
            "PKG component identity, version, or root install location differs from the stock package")
    require(all(not row.attrib and not len(row) and not (row.text or "").strip() for row in info.findall("relocate")),
            "PKG component declares a relocation")
    require(info.find(".//scripts") is None and not (component / "Scripts").exists()
            and not (component / "Scripts").is_symlink(), "stock PKG component must not contain installer scripts")


def app_paths(path: Path) -> set[str]:
    """Project the BOM or receipt listing onto the exact application paths."""
    paths: set[str] = set()
    aliases: set[str] = set()
    for line in read_text(path, PATH_LIST_LIMIT).split("\n"):
        line = line.removesuffix("\r")
        if not line:
            continue
        name = unicodedata.normalize("NFC", line.removeprefix("./"))
        if name in {"", ".", "Applications"}:
            # Native readers can omit the root node and shared parent.
            continue
        require(not any(part in {"", ".", ".."} for part in name.split("/"))
                and all(ord(char) >= 32 and ord(char) != 127 for char in name),
                "PKG file inventory contains an unsafe path")
        require(name == APP or name.startswith(APP + "/"), "PKG file inventory includes paths outside the stock app")
        alias = name.casefold()
        require(alias not in aliases, "PKG file inventory contains duplicate or aliased paths")
        aliases.add(alias)
        paths.add(name)
    require(LAUNCHER in paths, "PKG file inventory does not include the app executable")
    return paths


def check_receipt(info_path: Path, files: Path, expected: set[str], version: str) -> None:
    values = {}
    for line in read_text(info_path, METADATA_LIMIT).splitlines():
        key, separator, value = line.partition(":")
        require(separator == ":" and key not in values, "installed PKG receipt contains invalid metadata")
        values[key] = value.strip()
    require((values.get("package-id"), values.get("version"), values.get("volume")) == (APP_ID, version, "/")
            and values.get("location") in {"", "/", "."}, "installed PKG receipt identity, version, or root location differs")
    actual = app_paths(files)
    require(expected == actual,
            f"installed PKG receipt differs from the package BOM ({len(expected - actual)} missing, "
            f"{len(actual - expected)} unexpected app paths)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    staged = commands.add_parser("package", help="check the expanded package and its BOM")
    staged.add_argument("--expanded", type=Path, required=True)
    installed = commands.add_parser("receipt", help="compare the installed receipt with the package BOM")
    installed.add_argument("--info", type=Path, required=True)
    installed.add_argument("--files", type=Path, required=True)
    for command in (staged, installed):
        command.add_argument("--version", required=True)
        command.add_argument("--bom-paths", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        expected = app_paths(args.bom_paths)
        if args.command == "package":
            check_package(args.expanded, args.version)
            print(f"native installer smoke PKG distribution: macOS 14.4 minimum, {len(expected)} stock app paths")
        else:
            check_receipt(args.info, args.files, expected, args.version)
            print(f"native installer smoke PKG receipt: {APP_ID} {args.version}, {len(expected)} package paths matched")
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        print(f"macOS PKG evidence: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
