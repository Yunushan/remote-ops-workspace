"""Stage, preflight, and apply an authenticated stock Windows x64 MSI upgrade."""

from __future__ import annotations

import argparse
import ctypes as c
import json
import os
import sys
from contextlib import contextmanager
from ctypes import wintypes as win
from pathlib import Path
from sysconfig import get_platform

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from check_release_provenance import (  # noqa: E402
    native_installer_signature_commands,
    verify_platform_signature,
)
from inspect_windows_msi import (  # noqa: E402
    SYSTEM32_ONLY,
    Installer,
    fingerprint,
    inspect_registration,
    validate_managed_upgrade,
    validate_package,
)

from remote_ops_workspace.paths import data_dir  # noqa: E402
from remote_ops_workspace.update_channel import (  # noqa: E402
    POLICY_SCHEMA_V2,
    UpdateError,
    _release_version,
    load_update_policy,
    stage_update,
    verified_recovered_stage,
)

TARGET = "windows-x64"
INSTALL_ALREADY_RUNNING = 1618
REBOOT_RESULTS = {1641, 3010}
APPLIED_PHASES = {"msi-applied", "msi-already-applied"}
TRUST_IDENTITY = ("organization", "channel", "public_key", "selected_target")


def require(condition: bool, code: str) -> None:
    if not condition:
        raise UpdateError(code)


def load_policy(path: Path):
    policy = load_update_policy(path)
    settings = policy.settings
    require(settings["schema"] == POLICY_SCHEMA_V2, "managed-update-requires-v2-policy")
    require(settings["selected_target"] == TARGET, "managed-update-target-refused")
    return policy


def package_identity(native: Installer, root: Path, manifest, *, candidate: bool) -> dict:
    name = f"remote-ops-workspace-v{manifest.version}-{TARGET}.msi"
    asset = next((row for row in manifest.artifacts if (row.target, row.name) == (TARGET, name)), None)
    require(asset is not None, "selected-msi-absent")
    path = root / name
    try:
        verify_platform_signature(native_installer_signature_commands(path, registered_sdk=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise UpdateError("msi-authenticode-refused") from exc
    try:
        package = native.inspect(path, require_transactional_upgrade=candidate)
        validate_package(package, "x64", manifest.version)
        package["launcher_payload_sha256"] = native.launcher_payload_sha256(path)
    except (KeyError, OSError, ValueError) as exc:
        raise UpdateError("msi-package-identity-refused") from exc
    return {**package, "sha256": asset.sha256, "size_bytes": asset.size, "asset": name}


def program_files() -> Path:
    import winreg

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion",
                        access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        location, kind = winreg.QueryValueEx(key, "ProgramFilesDir")
    result = Path(location)
    require(kind == winreg.REG_SZ and result.is_absolute() and result.resolve(strict=True) == result,
            "stock-program-files-refused")
    return result


@contextmanager
def verified_pair(args, policy, workspace: Path, native: Installer, *, applying: bool = False):
    previous_version = _release_version(args.previous_version)
    require(previous_version < _release_version(args.version), "update-version-not-newer")
    previous_policy = load_policy(args.previous_policy)
    settings, previous_settings = policy.settings, previous_policy.settings
    require(all(settings[key] == previous_settings[key] for key in TRUST_IDENTITY), "rollback-trust-identity-refused")
    require(previous_version >= _release_version(settings["minimum_version"]), "rollback-version-below-policy-minimum")
    stage, previous_stage = (Path(os.path.abspath(path)) for path in (args.stage, args.previous_stage))
    require(not (stage.is_relative_to(previous_stage) or previous_stage.is_relative_to(stage)),
            "managed-update-directories-overlap")

    with (
        verified_recovered_stage(previous_policy, previous_stage, current_home=workspace,
                                 expected_version=args.previous_version,
                                 check_consumer_deadline=not applying) as (old_root, old_manifest, old_result),
        verified_recovered_stage(policy, stage, current_home=workspace,
                                 expected_version=args.version,
                                 check_consumer_deadline=not applying) as (new_root, new_manifest, new_result),
    ):
        previous = package_identity(native, old_root, old_manifest, candidate=False)
        candidate = package_identity(native, new_root, new_manifest, candidate=True)
        require(previous["product_code"] != candidate["product_code"]
                and previous["package_code"] != candidate["package_code"], "major-upgrade-identity-refused")
        details = {"target": TARGET, "install_permitted": False, "authenticode_and_timestamp_checked": True,
                   "previous_stage": old_result, "candidate_stage": new_result,
                   "previous_msi": previous, "candidate_msi": candidate}
        yield previous, candidate, new_root / candidate["asset"], details


def installed_launcher(native: Installer, installed: dict, absent: dict, expected: Path) -> str:
    try:
        require(native.related_products(installed["upgrade_code"]) == (installed["product_code"],),
                "msi-related-products-refused")
        registration = inspect_registration(native, installed, "installed")
        inspect_registration(native, absent, "absent")
        launcher = Path(registration["row_path"])
        require(launcher == expected and launcher.resolve(strict=True) == expected, "msi-launcher-path-refused")
        digest = fingerprint(launcher)
        require(digest == installed["launcher_payload_sha256"], "msi-launcher-bytes-refused")
        return digest
    except UpdateError:
        raise
    except (OSError, ValueError) as exc:
        raise UpdateError("msi-registration-refused") from exc


def stock_launcher() -> Path:
    try:
        return program_files() / "Remote Ops Workspace" / "bin" / "row.exe"
    except UpdateError:
        raise
    except (OSError, ValueError) as exc:
        raise UpdateError("msi-registration-refused") from exc


def preflight(args, policy, workspace: Path) -> dict:
    native = Installer()
    with verified_pair(args, policy, workspace, native) as (previous, candidate, _, details):
        digest = installed_launcher(native, previous, candidate, stock_launcher())
        return {**details, "phase": "msi-preflight-passed", "previous_launcher_sha256": digest}


def apply_verified_pair(native: Installer, previous: dict, candidate: dict, path: Path, launcher: Path) -> dict:
    """Apply already-authenticated MSI bytes while both staged files are held read-only."""
    try:
        validate_managed_upgrade(candidate.get("major_upgrade"))
    except ValueError as exc:
        raise UpdateError("msi-managed-predecessor-guard-refused") from exc

    if native.related_products(previous["upgrade_code"]) == (candidate["product_code"],):
        digest = installed_launcher(native, candidate, previous, launcher)
        return {"phase": "msi-already-applied", "installed_launcher_sha256": digest}

    previous_digest = installed_launcher(native, previous, candidate, launcher)
    require(fingerprint(path) == candidate["sha256"], "msi-candidate-bytes-refused")
    try:
        result = native.install_upgrade(path, previous["product_code"])
    except (OSError, ValueError):
        return {"phase": "msi-state-unverified", "refusal": "msi-installer-call-failed"}

    outcome = {"installer_exit_code": result, "previous_launcher_sha256": previous_digest}
    if result == INSTALL_ALREADY_RUNNING:
        return {**outcome, "phase": "msi-installer-busy"}
    if result in REBOOT_RESULTS:
        return {**outcome, "phase": "msi-reboot-required"}
    try:
        if result == 0:
            digest = installed_launcher(native, candidate, previous, launcher)
            return {**outcome, "phase": "msi-applied", "installed_launcher_sha256": digest}
        digest = installed_launcher(native, previous, candidate, launcher)
        return {**outcome, "phase": "msi-previous-preserved", "installed_launcher_sha256": digest}
    except UpdateError as exc:
        return {**outcome, "phase": "msi-state-unverified", "refusal": str(exc)}


def is_elevated_administrator() -> bool:
    check = c.WinDLL("shell32.dll", winmode=SYSTEM32_ONLY).IsUserAnAdmin
    check.argtypes = ()
    check.restype = win.BOOL
    return bool(check())


def apply(args, policy, workspace: Path) -> dict:
    native = Installer()
    with verified_pair(args, policy, workspace, native, applying=True) as (previous, candidate, path, details):
        outcome = apply_verified_pair(native, previous, candidate, path, stock_launcher())
        return {**details, **outcome}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    stage = actions.add_parser("stage", help="stage a signed asset set for an exact version")
    check = actions.add_parser("preflight", help="verify the staged candidate and rollback MSIs")
    install = actions.add_parser("apply", help="apply the staged MSI with native rollback on failure")
    operations = {"preflight": preflight, "apply": apply}
    for command in (stage, check, install):
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--stage", type=Path, required=True)
        command.add_argument("--version", required=True)
    for command in (check, install):
        command.add_argument("--previous-policy", type=Path, required=True)
        command.add_argument("--previous-stage", type=Path, required=True)
        command.add_argument("--previous-version", required=True)
    args = parser.parse_args(argv)
    try:
        require(sys.platform == "win32" and get_platform() == "win-amd64", "windows-x64-required")
        if args.action == "apply":
            require(is_elevated_administrator(), "elevated-windows-administrator-required")
        workspace = data_dir()
        policy = load_policy(args.policy)
        _release_version(args.version)
        result = (stage_update(policy, args.stage, current_home=workspace, expected_version=args.version)
                  if args.action == "stage" else operations[args.action](args, policy, workspace))
    except UpdateError as exc:
        print(json.dumps({"phase": "refused", "refusal": str(exc), "install_permitted": False}))
        return 1
    except (OSError, ValueError):
        refusal = "windows-msi-input-refused" if args.action == "apply" else "windows-msi-preflight-input-refused"
        print(json.dumps({"phase": "refused", "refusal": refusal, "install_permitted": False}))
        return 1
    print(json.dumps(result, indent=2))
    return int(args.action == "apply" and result["phase"] not in APPLIED_PHASES)


if __name__ == "__main__":
    sys.exit(main())
