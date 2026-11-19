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
from tempfile import TemporaryDirectory
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
ROLLBACK_REQUIRED_CONDITION = f"NOT {DETECT_UPGRADE} OR (NOT RollbackDisabled AND NOT DISABLEROLLBACK)"
ROLLBACK_REQUIRED_MESSAGE = "Enable Windows Installer rollback before upgrading this product."
EXPECTED_PREDECESSOR = "ROW_EXPECTED_PREDECESSOR"
EXPECTED_PREDECESSOR_CONDITION = f"NOT {EXPECTED_PREDECESSOR} OR {DETECT_UPGRADE} ~= {EXPECTED_PREDECESSOR}"
UPGRADE_ACTIONS = ("FindRelatedProducts", "LaunchConditions", *ROLLBACK_ACTIONS)
READONLY = None
MACHINE = 4
LOCAL = 3
NO_MORE_ITEMS = 259
UNKNOWN_PRODUCT = 1605
SYSTEM32_ONLY = 0x800
UILEVEL_NONE = 2
INSTALL_PROPERTIES = "REBOOT=ReallySuppress"
LIMIT = 1024
MAX_PATH = 260
MAX_LAUNCHER_BYTES = 150 * 1024 * 1024
ROW_FILE_KEY = "RowExe"
FILE_NOT_COMPRESSED = 0x2000
FILE_IN_CABINET = 0x11
NEED_NEW_CABINET = 0x12
FILE_EXTRACTED = 0x13
FILEOP_ABORT = 0
FILEOP_DOIT = 1
FILEOP_SKIP = 2
ERROR_INVALID_DATA = 13
HANDLE = c.c_uint


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def guid(value: str) -> str:
    identifier = UUID(value)
    require(identifier.int != 0, "Windows Installer identity must use a nonzero GUID")
    return "{" + str(identifier).upper() + "}"


def upgrade_properties(expected_predecessor: str) -> str:
    return f"{INSTALL_PROPERTIES} {EXPECTED_PREDECESSOR}={guid(expected_predecessor)}"


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
            "MsiSetInternalUI": (uint, uint, c.c_void_p),
            "MsiInstallProductW": (uint, string, string),
            "MsiDatabaseOpenViewW": (uint, HANDLE, string, phandle),
            "MsiViewExecute": (uint, HANDLE, HANDLE),
            "MsiViewFetch": (uint, HANDLE, phandle),
            "MsiGetSummaryInformationW": (uint, HANDLE, string, uint, phandle),
            "MsiSummaryInfoGetPropertyW": (uint, HANDLE, uint, c.POINTER(uint), c.c_void_p, c.c_void_p, win.LPWSTR, pdword),
            "MsiRecordGetStringW": (uint, HANDLE, uint, win.LPWSTR, pdword),
            "MsiCreateRecord": (HANDLE, uint),
            "MsiRecordSetStringW": (uint, HANDLE, uint, string),
            "MsiRecordReadStream": (uint, HANDLE, uint, c.c_void_p, pdword),
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
        launch_conditions = self.rows(database, "SELECT `Condition`, `Description` FROM `LaunchCondition`", 2)
        proof = {
            "rules": [list(row) for row in rows],
            "execute_conditions": conditions,
            "launch_conditions": [condition for condition, _ in launch_conditions],
            "rollback_required_message": dict(launch_conditions).get(ROLLBACK_REQUIRED_CONDITION),
            "authored_expected_predecessor": EXPECTED_PREDECESSOR in properties,
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

    def launcher_payload_sha256(self, path: Path) -> str:
        """Hash the stock launcher in its embedded cabinet without installing the MSI."""
        with TemporaryDirectory(prefix="row-msi-payload-") as temporary:
            work = Path(temporary)
            cabinet = work / "payload.cab"
            with self.handle(self.dll.MsiOpenDatabaseW, str(path.absolute()), READONLY) as database:
                rows = self.rows(
                    database, "SELECT `FileSize`, `Sequence`, `Attributes` FROM `File` WHERE `File` = 'RowExe'", 3,
                )
                require(len(rows) == 1, "MSI must identify exactly one RowExe payload")
                raw_size, sequence, attributes = rows[0]
                size = int(raw_size)
                require(0 < size <= MAX_LAUNCHER_BYTES and not (int(attributes or "0") & FILE_NOT_COMPRESSED),
                        "MSI launcher must be a bounded, compressed file")
                media = self.rows(
                    database, "SELECT `LastSequence`, `Cabinet` FROM `Media` ORDER BY `DiskId`", 2,
                )
                cabinet_name = embedded_cabinet_name(int(sequence), media)
                self.copy_cabinet_stream(database, cabinet_name, cabinet, path.stat().st_size)
            launcher = work / "launcher.bin"
            extract_cabinet_launcher(cabinet, launcher, size)
            return fingerprint(launcher)

    def copy_cabinet_stream(self, database, name: str, output: Path, limit: int) -> None:
        dll = self.dll
        query = "SELECT `Data` FROM `_Streams` WHERE `Name` = ?"
        with self.handle(dll.MsiDatabaseOpenViewW, database, query) as view:
            parameter = dll.MsiCreateRecord(1)
            require(bool(parameter), "could not allocate the MSI cabinet query parameter")
            try:
                confirm(dll.MsiRecordSetStringW(parameter, 1, name), "set cabinet stream name")
                confirm(dll.MsiViewExecute(view, parameter), "find cabinet stream")
                with self.handle(dll.MsiViewFetch, view) as record, output.open("xb") as stream:
                    buffer = c.create_string_buffer(1024 * 1024)
                    written = 0
                    while True:
                        count = win.DWORD(len(buffer))
                        confirm(dll.MsiRecordReadStream(record, 1, buffer, c.byref(count)), "read cabinet stream")
                        written += count.value
                        require(written <= limit and count.value <= len(buffer), "MSI cabinet stream exceeds its size bound")
                        stream.write(buffer[:count.value])
                        if count.value < len(buffer):
                            break
                    require(written > 0, "MSI cabinet stream is empty")
            finally:
                confirm(dll.MsiCloseHandle(parameter), "close cabinet query parameter")

    def install_upgrade(self, path: Path, expected_predecessor: str) -> int:
        properties = upgrade_properties(expected_predecessor)
        previous_ui = self.dll.MsiSetInternalUI(UILEVEL_NONE, None)
        try:
            return self.dll.MsiInstallProductW(str(path), properties)
        finally:
            self.dll.MsiSetInternalUI(previous_ui, None)

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


class CabinetMember(c.Structure):
    _fields_ = [
        ("name", win.LPCWSTR), ("size", win.DWORD), ("error", win.DWORD),
        ("date", win.WORD), ("time", win.WORD), ("attributes", win.WORD),
        ("destination", c.c_wchar * MAX_PATH),
    ]


class CabinetExtraction(c.Structure):
    _fields_ = [("target", win.LPCWSTR), ("source", win.LPCWSTR),
                ("error", win.UINT), ("flags", win.DWORD)]


def embedded_cabinet_name(sequence: int, media: list[tuple[str | None, ...]]) -> str:
    require(sequence > 0, "MSI launcher has no valid media sequence")
    last_sequence = 0
    for raw_end, cabinet in media:
        end = int(raw_end)
        require(end >= last_sequence, "MSI media sequences are out of order")
        if last_sequence < sequence <= end:
            require(bool(cabinet and cabinet.startswith("#") and len(cabinet) > 1),
                    "MSI launcher must use an embedded cabinet")
            return cabinet[1:]
        last_sequence = end
    raise ValueError("MSI launcher sequence has no matching cabinet")


def extract_cabinet_launcher(cabinet: Path, output: Path, size: int) -> None:
    destination = str(output.absolute())
    require(len(destination.encode("utf-16-le")) // 2 < MAX_PATH, "MSI payload temporary path is too long")
    iterate = c.WinDLL("setupapi.dll", winmode=SYSTEM32_ONLY, use_last_error=True).SetupIterateCabinetW
    callback_type = c.WINFUNCTYPE(win.UINT, c.c_void_p, win.UINT, c.c_size_t, c.c_size_t)
    iterate.argtypes = (win.LPCWSTR, win.DWORD, callback_type, c.c_void_p)
    iterate.restype = win.BOOL
    found = False
    extracted = False

    @callback_type
    def notification(_context, event, param, _unused):
        nonlocal found, extracted
        if event == FILE_IN_CABINET:
            member = CabinetMember.from_address(param)
            if member.name != ROW_FILE_KEY:
                return FILEOP_SKIP
            if found or member.error or member.size != size:
                return FILEOP_ABORT
            found = True
            # Select a fixed scratch path. Cabinet member names never determine the output path.
            member.destination = destination
            return FILEOP_DOIT
        if event == NEED_NEW_CABINET:
            return ERROR_INVALID_DATA
        if event == FILE_EXTRACTED:
            result = CabinetExtraction.from_address(param)
            if result.error or result.target != destination:
                return ERROR_INVALID_DATA
            extracted = True
        return 0

    if not iterate(str(cabinet.absolute()), 0, notification, None):
        raise OSError(c.get_last_error(), "MSI launcher cabinet extraction failed")
    require(found and extracted and output.stat().st_size == size, "MSI cabinet did not yield the exact RowExe size")


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
    if "launcher_payload_sha256" in package:
        payload = package["launcher_payload_sha256"]
        require(isinstance(payload, str) and re.fullmatch(r"[0-9a-f]{64}", payload) is not None,
                "MSI launcher payload digest is invalid")
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
    require(ROLLBACK_REQUIRED_CONDITION in launch_conditions
            and proof.get("rollback_required_message") == ROLLBACK_REQUIRED_MESSAGE,
            "MSI must require Windows Installer rollback for major upgrades")
    secure = proof.get("secure_properties")
    require(isinstance(secure, list) and DETECT_UPGRADE in secure and DETECT_DOWNGRADE in secure
            and proof.get("authored_detection_properties") == [],
            "MSI related-product detection properties must reach the elevated installer and start unset")
    validate_language(proof.get("product_language"), proof.get("template_languages"))


def validate_managed_upgrade(proof) -> None:
    require(
        isinstance(proof, dict)
        and isinstance(proof.get("launch_conditions"), list)
        and EXPECTED_PREDECESSOR_CONDITION in proof["launch_conditions"]
        and isinstance(proof.get("secure_properties"), list) and EXPECTED_PREDECESSOR in proof["secure_properties"]
        and proof.get("authored_expected_predecessor") is False,
        "MSI must bind a managed upgrade to its exact detected predecessor",
    )


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
    if "launcher_payload_sha256" in package:
        installed["launcher_sha256"] = package["launcher_payload_sha256"]
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
                validate_managed_upgrade(major_upgrade)
            result = {"upgrade_sequence": sequence, "major_upgrade": major_upgrade, "sha256": original}
        else:
            package = native.inspect(args.package.absolute(), require_transactional_upgrade=args.require_transactional_upgrade)
            if args.require_transactional_upgrade:
                package["launcher_payload_sha256"] = native.launcher_payload_sha256(args.package)
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
