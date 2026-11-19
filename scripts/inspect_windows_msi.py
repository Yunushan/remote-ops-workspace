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
ROLLBACK_ACTIONS = ("InstallValidate", "InstallInitialize", "RemoveExistingProducts", "ProcessComponents",
                    "InstallFiles", "InstallFinalize")
ROLLBACK_BREAKERS = {"DisableRollback", "ForceReboot", "ScheduleReboot"}
DETECT_UPGRADE = "WIX_UPGRADE_DETECTED"
DETECT_DOWNGRADE = "WIX_DOWNGRADE_DETECTED"
UPGRADE_ACTIONS = ("FindRelatedProducts", "LaunchConditions", *ROLLBACK_ACTIONS)
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
            "MsiRecordIsNull": (win.BOOL, HANDLE, uint),
            "MsiCloseHandle": (uint, HANDLE),
            "MsiEnumRelatedProductsW": (uint, string, dword, dword, win.LPWSTR),
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

    def rows(self, database, query: str, columns: int, *, preserve_null=False) -> list[tuple[str | None, ...]]:
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
                        if preserve_null and self.dll.MsiRecordIsNull(record, column):
                            fields.append(None)
                            continue
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

    def upgrade_sequence(self, database) -> dict[str, int]:
        rows = self.rows(database, "SELECT `Action`, `Sequence` FROM `InstallExecuteSequence`", 2)
        return {action: int(sequence) for action, sequence in rows}

    def major_upgrade(self, database, properties: dict, sequence: dict, template: str) -> dict:
        rows = self.rows(database, "SELECT `UpgradeCode`, `VersionMin`, `VersionMax`, `Language`, "
                         "`Attributes`, `Remove`, `ActionProperty` FROM `Upgrade`", 7, preserve_null=True)
        conditions = {
            action: condition
            for action, condition in self.rows(database, "SELECT `Action`, `Condition` FROM `InstallExecuteSequence`", 2)
            if action in UPGRADE_ACTIONS
        }
        proof = {
            "rules": [list(row) for row in rows],
            "execute_conditions": conditions,
            "launch_conditions": [row[0] for row in self.rows(database, "SELECT `Condition` FROM `LaunchCondition`", 1)],
            "secure_properties": properties.get("SecureCustomProperties", "").split(";"),
            "authored_detection_properties": sorted({DETECT_UPGRADE, DETECT_DOWNGRADE}.intersection(properties)),
            "product_language": properties.get("ProductLanguage"),
            "template_languages": template.partition(";")[2].split(","),
        }
        validate_major_upgrade(proof, guid(properties["UpgradeCode"]), properties["ProductVersion"], sequence)
        return proof

    def inspect(self, path: Path, *, require_transactional_upgrade=False) -> dict:
        with self.handle(self.dll.MsiOpenDatabaseW, str(path), READONLY) as database:
            properties = dict(self.rows(database, "SELECT `Property`, `Value` FROM `Property`", 2))
            upgrade_sequence = self.upgrade_sequence(database)
            media = self.rows(database, "SELECT `Cabinet` FROM `Media`", 1)
            files = self.rows(database, "SELECT `Component_`, `FileName` FROM `File` WHERE `File` = 'RowExe'", 2)
            components = self.rows(
                database, "SELECT `ComponentId`, `KeyPath` FROM `Component` WHERE `Component` = 'RowExeComponent'", 2,
            )
            with self.handle(self.dll.MsiGetSummaryInformationW, database, None, 0) as summary:
                template = self.summary(summary, 7)
                package_code = guid(self.summary(summary, 9))
            major_upgrade = {}
            if require_transactional_upgrade:
                validate_upgrade_rollback(upgrade_sequence, properties.get("DISABLEROLLBACK", ""))
                major_upgrade["major_upgrade"] = self.major_upgrade(database, properties, upgrade_sequence, template)
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
            "product_language": properties.get("ProductLanguage"),
            "template_languages": template.partition(";")[2].split(","),
            "upgrade_sequence": upgrade_sequence,
            "disable_rollback": properties.get("DISABLEROLLBACK", ""),
            **major_upgrade,
        }

    def related_products(self, upgrade_code: str) -> tuple[str, ...]:
        products = []
        buffer = c.create_unicode_buffer(39)
        for index in range(64):
            result = self.dll.MsiEnumRelatedProductsW(upgrade_code, 0, index, buffer)
            if result == NO_MORE_ITEMS:
                return tuple(products)
            confirm(result, "MsiEnumRelatedProducts")
            products.append(guid(buffer.value))
        raise ValueError("related Windows Installer product list exceeds the inspection bound")

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
    if "product_language" in package:
        validate_language(package.get("product_language"), package.get("template_languages"))
    for field in ("package_code", "product_code"):
        require(isinstance(package.get(field), str) and guid(package[field]) == package[field],
                f"MSI {field} must be a canonical GUID")


def validate_upgrade_rollback(sequence, disable_rollback: str) -> None:
    require(isinstance(sequence, dict) and all(type(value) is int for value in sequence.values())
            and all(sequence.get(name, 0) > 0 for name in ROLLBACK_ACTIONS),
            "MSI upgrade rollback sequence is incomplete")
    positions = [sequence[name] for name in ROLLBACK_ACTIONS]
    require(positions == sorted(set(positions)),
            "MSI must remove the previous product inside the installation transaction")
    initialize, remove_previous = positions[1:3]
    require(not any(initialize < position <= remove_previous for name, position in sequence.items()
                    if name != "RemoveExistingProducts"),
            "MSI must remove the previous product immediately after InstallInitialize")
    require(disable_rollback == "" and not ROLLBACK_BREAKERS.intersection(sequence),
            "MSI upgrade must preserve rollback and suppress in-package reboot actions")


def validate_language(language, templates) -> None:
    require(isinstance(language, str) and re.fullmatch(r"[0-9]{1,5}", language) is not None
            and isinstance(templates, list) and language in templates,
            "MSI ProductLanguage must appear in its template summary")


def validate_major_upgrade(proof, upgrade_code: str, version: str, sequence: dict) -> None:
    require(isinstance(proof, dict), "compiled MSI related-product rules are missing")
    upgrade = [upgrade_code, None, version, None, "1", None, DETECT_UPGRADE]
    downgrade = [upgrade_code, version, None, None, "2", None, DETECT_DOWNGRADE]
    # A NULL Remove field lets Windows Installer uninstall all features.
    # An empty formatted expression or a feature list can leave parts behind.
    require(proof.get("rules") in ([upgrade, downgrade], [downgrade, upgrade]),
            "MSI must remove all older products in its family and detect newer versions without removing them")
    detection = sequence.get("FindRelatedProducts", 0)
    launch = sequence.get("LaunchConditions", 0)
    require(0 < detection < launch < sequence.get("InstallValidate", 0)
            and proof.get("execute_conditions") == dict.fromkeys(UPGRADE_ACTIONS, ""),
            "MSI related-product detection and transactional upgrade actions must run unconditionally in order")
    launch_conditions = proof.get("launch_conditions")
    require(isinstance(launch_conditions, list) and f"NOT {DETECT_DOWNGRADE}" in launch_conditions,
            "MSI must refuse installation over a newer product in its family")
    secure = proof.get("secure_properties")
    require(isinstance(secure, list) and DETECT_UPGRADE in secure and DETECT_DOWNGRADE in secure
            and proof.get("authored_detection_properties") == [],
            "MSI related-product detection properties must reach the elevated installer and start unset")
    validate_language(proof.get("product_language"), proof.get("template_languages"))


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
    if "product_language" in package:
        require(native.product(product_code, "Language") == package["product_language"],
                "registered ProductLanguage differs from the exact MSI")
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
    if assets is not None or "upgrade_sequence" in package:
        validate_upgrade_rollback(package.get("upgrade_sequence"), package.get("disable_rollback"))
    if assets is not None or "major_upgrade" in package:
        validate_major_upgrade(package.get("major_upgrade"), package["upgrade_code"], package["version"],
                               package.get("upgrade_sequence", {}))
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
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--architecture", choices=tuple(TEMPLATES.values()))
    mode.add_argument("--sequence-only", action="store_true", help="verify major-upgrade metadata for a stock or branded package")
    parser.add_argument("--version")
    parser.add_argument("--state", choices=("absent", "installed"))
    parser.add_argument("--require-transactional-upgrade", action="store_true")
    args = parser.parse_args()
    try:
        require(sys.platform == "win32", "native MSI inspection requires Windows")
        original = fingerprint(args.package)
        native = Installer()
        if args.sequence_only:
            require(not (args.version or args.state or args.require_transactional_upgrade),
                    "sequence-only inspection does not accept stock package or registration options")
            with native.handle(native.dll.MsiOpenDatabaseW, str(args.package.absolute()), READONLY) as database:
                sequence = native.upgrade_sequence(database)
                properties = dict(native.rows(database, "SELECT `Property`, `Value` FROM `Property`", 2))
                with native.handle(native.dll.MsiGetSummaryInformationW, database, None, 0) as summary:
                    template = native.summary(summary, 7)
                validate_upgrade_rollback(sequence, properties.get("DISABLEROLLBACK", ""))
                major_upgrade = native.major_upgrade(database, properties, sequence, template)
            result = {"upgrade_sequence": sequence, "major_upgrade": major_upgrade, "sha256": original}
        else:
            package = native.inspect(args.package.absolute(), require_transactional_upgrade=args.require_transactional_upgrade)
            validate_package(package, args.architecture, args.version)
            registration = inspect_registration(native, package, args.state) if args.state else None
            result = {"package": {**package, "sha256": original}, "registration": registration}
        require(fingerprint(args.package) == original, "MSI bytes changed during native inspection")
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"MSI inspection refused: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
