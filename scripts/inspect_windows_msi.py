"""Read the identity of the stock Windows MSI and its per-machine registration."""

from __future__ import annotations

import argparse
import ctypes as c
import hashlib
import json
import re
import stat
import sys
from contextlib import contextmanager
from ctypes import wintypes as win
from pathlib import Path, PureWindowsPath
from uuid import UUID

STOCK_UPGRADE = "{8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0}"
STOCK_CLI_COMPONENT = "{7689D62F-2557-4DD3-8C58-38C5E245E44C}"
TEMPLATES = {"Intel": "x86", "x64": "x64", "Arm64": "arm64"}
PROBES = ("before-install", "after-install", "after-reinstall", "after-uninstall")
READONLY = None
MACHINE = 4
LOCAL = 3
NO_MORE_ITEMS = 259
UNKNOWN_PRODUCT = 1605
SYSTEM32_ONLY = 0x800
LIMIT = 1024
HANDLE = c.c_uint


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def guid(value: str) -> str:
    identifier = UUID(value)
    require(identifier.int != 0, "Windows Installer identity must use a nonzero GUID")
    return "{" + str(identifier).upper() + "}"


def confirm(result: int, operation: str) -> None:
    if result != 0:
        raise ValueError(f"{operation} returned Windows Installer error {result}")


class Installer:
    def __init__(self) -> None:
        dll = c.WinDLL("msi.dll", winmode=SYSTEM32_ONLY)
        string, dword, uint = win.LPCWSTR, win.DWORD, c.c_uint
        pdword, phandle = c.POINTER(dword), c.POINTER(HANDLE)
        signatures = {
            "MsiOpenDatabaseW": (uint, string, string, phandle),
            "MsiDatabaseOpenViewW": (uint, HANDLE, string, phandle),
            "MsiViewExecute": (uint, HANDLE, HANDLE),
            "MsiViewFetch": (uint, HANDLE, phandle),
            "MsiGetSummaryInformationW": (uint, HANDLE, string, uint, phandle),
            "MsiSummaryInfoGetPropertyW": (uint, HANDLE, uint, c.POINTER(uint), c.c_void_p, c.c_void_p, win.LPWSTR, pdword),
            "MsiRecordGetStringW": (uint, HANDLE, uint, win.LPWSTR, pdword),
            "MsiCloseHandle": (uint, HANDLE),
            "MsiGetProductInfoExW": (uint, string, string, dword, string, win.LPWSTR, pdword),
            "MsiGetComponentPathExW": (c.c_int, string, string, string, dword, win.LPWSTR, pdword),
        }
        for name, (result, *arguments) in signatures.items():
            call = getattr(dll, name)
            call.argtypes = arguments
            call.restype = result
        self.dll = dll

    @contextmanager
    def handle(self, operation, *args):
        handle = HANDLE()
        confirm(operation(*args, c.byref(handle)), operation.__name__)
        try:
            yield handle
        finally:
            confirm(self.dll.MsiCloseHandle(handle), "MsiCloseHandle")

    def rows(self, database, query: str, columns: int) -> list[tuple[str, ...]]:
        with self.handle(self.dll.MsiDatabaseOpenViewW, database, query) as view:
            confirm(self.dll.MsiViewExecute(view, 0), "MsiViewExecute")
            rows = []
            while len(rows) < 256:
                record = HANDLE()
                result = self.dll.MsiViewFetch(view, c.byref(record))
                if result == NO_MORE_ITEMS:
                    return rows
                confirm(result, "MsiViewFetch")
                try:
                    fields = []
                    for column in range(1, columns + 1):
                        buffer, size = c.create_unicode_buffer(LIMIT), win.DWORD(LIMIT)
                        confirm(self.dll.MsiRecordGetStringW(record, column, buffer, c.byref(size)), "MsiRecordGetString")
                        fields.append(buffer.value)
                    rows.append(tuple(fields))
                finally:
                    confirm(self.dll.MsiCloseHandle(record), "MsiCloseHandle")
            raise ValueError("Windows Installer table exceeds the inspection bound")

    def summary(self, summary, field: int) -> str:
        buffer, size, kind = c.create_unicode_buffer(LIMIT), win.DWORD(LIMIT), c.c_uint()
        confirm(self.dll.MsiSummaryInfoGetPropertyW(summary, field, c.byref(kind), None, None, buffer, c.byref(size)),
                "MsiSummaryInfoGetProperty")
        return buffer.value

    def inspect(self, path: Path) -> dict:
        with self.handle(self.dll.MsiOpenDatabaseW, str(path), READONLY) as database:
            properties = dict(self.rows(database, "SELECT `Property`, `Value` FROM `Property`", 2))
            media = self.rows(database, "SELECT `Cabinet` FROM `Media`", 1)
            files = self.rows(database, "SELECT `Component_`, `FileName` FROM `File` WHERE `File` = 'RowExe'", 2)
            components = self.rows(
                database, "SELECT `ComponentId`, `KeyPath` FROM `Component` WHERE `Component` = 'RowExeComponent'", 2,
            )
            with self.handle(self.dll.MsiGetSummaryInformationW, database, None, 0) as summary:
                template = self.summary(summary, 7)
                package_code = guid(self.summary(summary, 9))
        require(bool(media) and all(cabinet.startswith("#") and len(cabinet) > 1 for cabinet, in media),
                "stock MSI must use embedded cabinets")
        require(len(files) == len(components) == 1 and files[0][0] == "RowExeComponent"
                and files[0][1].rsplit("|", 1)[-1].casefold() == "row.exe" and components[0][1] == "RowExe",
                "stock MSI must register row.exe as the launcher component key path")
        platform, separator, _ = template.partition(";")
        require(bool(separator), "Windows Installer architecture summary is missing")
        return {
            "architecture": TEMPLATES.get(platform.strip() or "Intel"),
            "package_code": package_code,
            "product_code": guid(properties["ProductCode"]),
            "upgrade_code": guid(properties["UpgradeCode"]),
            "row_component_code": guid(components[0][0]),
            "version": properties["ProductVersion"],
            "name": properties["ProductName"],
            "manufacturer": properties["Manufacturer"],
            "all_users": properties.get("ALLUSERS"),
            "per_user": properties.get("MSIINSTALLPERUSER", ""),
        }

    def product(self, product_code: str, field: str) -> str | None:
        buffer, size = c.create_unicode_buffer(LIMIT), win.DWORD(LIMIT)
        result = self.dll.MsiGetProductInfoExW(product_code, None, MACHINE, field, buffer, c.byref(size))
        if result == UNKNOWN_PRODUCT:
            return None
        confirm(result, f"MsiGetProductInfoEx({field})")
        return buffer.value

    def component_path(self, product_code: str, component_code: str) -> str:
        buffer = c.create_unicode_buffer(32768)
        size = win.DWORD(len(buffer))
        state = self.dll.MsiGetComponentPathExW(product_code, component_code, None, MACHINE, buffer, c.byref(size))
        require(state == LOCAL and bool(buffer.value), "the exact MSI has no locally installed row.exe key path")
        return buffer.value


def validate_package(package: dict, architecture: str, version: str | None = None) -> None:
    require(package.get("name") == "Remote Ops Workspace"
            and package.get("manufacturer") == "Remote Ops Workspace Contributors"
            and package.get("upgrade_code") == STOCK_UPGRADE
            and package.get("row_component_code") == STOCK_CLI_COMPONENT,
            "MSI does not belong to the stock Remote Ops Workspace package family")
    require(package.get("architecture") == architecture, "MSI summary architecture differs from the release target")
    require(isinstance(package.get("version"), str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", package["version"]) is not None
            and (version is None or package["version"] == version), "MSI ProductVersion differs from the release version")
    require(package.get("all_users") == "1" and package.get("per_user") == "", "stock MSI must have per-machine scope")
    for field in ("package_code", "product_code"):
        require(isinstance(package.get(field), str) and guid(package[field]) == package[field],
                f"MSI {field} must be a canonical GUID")


def inspect_registration(native, package: dict, state: str) -> dict:
    product_code = package["product_code"]
    registered = native.product(product_code, "State")
    if state == "absent":
        require(registered is None, "MSI ProductCode still has a per-machine registration")
        return {"state": "absent"}
    require(registered == "5", "MSI ProductCode is not installed per-machine")
    registered_package = native.product(product_code, "PackageCode")
    require(registered_package is not None and guid(registered_package) == package["package_code"],
            "registered PackageCode differs from the exact MSI")
    version = native.product(product_code, "VersionString")
    require(version == package["version"], "registered ProductVersion differs from the exact MSI")
    row = native.component_path(product_code, package["row_component_code"])
    path = PureWindowsPath(row)
    require(path.is_absolute() and path.name.casefold() == "row.exe", "registered component path is not a row.exe file")
    return {"state": "installed", "package_code": package["package_code"], "version": version, "row_path": row}


def validate_lifecycle(probes, target: str, assets: list[dict] | None = None) -> None:
    require(isinstance(probes, list) and len(probes) == len(PROBES) and all(isinstance(row, dict) for row in probes)
            and tuple(row.get("probe") for row in probes) == PROBES, "candidate MSI lifecycle observations are incomplete")
    package = probes[0].get("package")
    require(isinstance(package, dict), "candidate MSI package identity is missing")
    validate_package(package, target.removeprefix("windows-"))
    digest = package.get("sha256")
    require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
            "candidate MSI package digest is invalid")
    if assets is not None:
        name = f"remote-ops-workspace-v{package['version']}-{target}.msi"
        packages = [row.get("sha256") for row in assets if PureWindowsPath(row["path"]).name == name]
        require(packages == [digest], "candidate MSI lifecycle package differs from the built MSI asset")
    absent = {"state": "absent"}
    installed = {"state": "installed", "package_code": package["package_code"], "version": package["version"],
                 "row_path": "msi-install/bin/row.exe"}
    for observation, expected in zip(probes, (absent, installed, installed, absent), strict=True):
        require(observation.get("package") == package and observation.get("registration") == expected,
                f"candidate MSI lifecycle registration differs at {observation['probe']}")


def fingerprint(path: Path) -> str:
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and not (getattr(before, "st_file_attributes", 0) & 0x400),
            "MSI must be a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.lstat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns),
            "MSI changed during inspection")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--architecture", choices=tuple(TEMPLATES.values()), required=True)
    parser.add_argument("--version")
    parser.add_argument("--state", choices=("absent", "installed"))
    args = parser.parse_args()
    try:
        require(sys.platform == "win32", "native MSI inspection requires Windows")
        original = fingerprint(args.package)
        native = Installer()
        package = native.inspect(args.package.absolute())
        validate_package(package, args.architecture, args.version)
        registration = inspect_registration(native, package, args.state) if args.state else None
        require(fingerprint(args.package) == original, "MSI bytes changed during native inspection")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"MSI inspection refused: {error}\n")
    print(json.dumps({"package": {**package, "sha256": original}, "registration": registration}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
