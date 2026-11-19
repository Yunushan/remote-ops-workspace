"""Stage and preflight an authenticated stock Windows x64 MSI upgrade."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from sysconfig import get_platform

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from check_release_provenance import (  # noqa: E402
    native_installer_signature_commands,
    verify_platform_signature,
)
from inspect_windows_msi import (  # noqa: E402
    Installer,
    fingerprint,
    inspect_registration,
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


def preflight(args, policy, workspace: Path) -> dict:
    previous_version = _release_version(args.previous_version)
    require(previous_version < _release_version(args.version), "update-version-not-newer")
    previous_policy = load_policy(args.previous_policy)
    settings, previous_settings = policy.settings, previous_policy.settings
    require(all(settings[key] == previous_settings[key] for key in TRUST_IDENTITY), "rollback-trust-identity-refused")
    require(previous_version >= _release_version(settings["minimum_version"]), "rollback-version-below-policy-minimum")
    stage, previous_stage = (Path(os.path.abspath(path)) for path in (args.stage, args.previous_stage))
    require(not (stage.is_relative_to(previous_stage) or previous_stage.is_relative_to(stage)),
            "managed-update-directories-overlap")

    native = Installer()
    with (
        verified_recovered_stage(previous_policy, previous_stage, current_home=workspace,
                                 expected_version=args.previous_version) as (old_root, old_manifest, old_result),
        verified_recovered_stage(policy, stage, current_home=workspace,
                                 expected_version=args.version) as (new_root, new_manifest, new_result),
    ):
        previous = package_identity(native, old_root, old_manifest, candidate=False)
        candidate = package_identity(native, new_root, new_manifest, candidate=True)
        require(previous["product_code"] != candidate["product_code"]
                and previous["package_code"] != candidate["package_code"], "major-upgrade-identity-refused")
        try:
            require(native.related_products(previous["upgrade_code"]) == (previous["product_code"],),
                    "msi-related-products-refused")
            registration = inspect_registration(native, previous, "installed")
            inspect_registration(native, candidate, "absent")
            launcher = Path(registration["row_path"])
            expected = program_files() / "Remote Ops Workspace" / "bin" / "row.exe"
            require(launcher == expected and launcher.resolve(strict=True) == expected, "msi-launcher-path-refused")
            launcher_digest = fingerprint(launcher)
        except UpdateError:
            raise
        except (OSError, ValueError) as exc:
            raise UpdateError("msi-registration-refused") from exc
        return {"phase": "msi-preflight-passed", "target": TARGET, "install_permitted": False,
                "authenticode_and_timestamp_checked": True, "previous_launcher_sha256": launcher_digest,
                "previous_stage": old_result, "candidate_stage": new_result,
                "previous_msi": previous, "candidate_msi": candidate}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    stage = actions.add_parser("stage", help="stage a signed asset set for an exact version")
    check = actions.add_parser("preflight", help="verify the staged candidate and rollback MSIs")
    for command in (stage, check):
        command.add_argument("--policy", type=Path, required=True)
        command.add_argument("--stage", type=Path, required=True)
        command.add_argument("--version", required=True)
    check.add_argument("--previous-policy", type=Path, required=True)
    check.add_argument("--previous-stage", type=Path, required=True)
    check.add_argument("--previous-version", required=True)
    args = parser.parse_args(argv)
    try:
        require(sys.platform == "win32" and get_platform() == "win-amd64", "windows-x64-required")
        workspace = data_dir()
        policy = load_policy(args.policy)
        _release_version(args.version)
        result = (stage_update(policy, args.stage, current_home=workspace, expected_version=args.version)
                  if args.action == "stage" else preflight(args, policy, workspace))
    except UpdateError as exc:
        print(json.dumps({"phase": "refused", "refusal": str(exc), "install_permitted": False}))
        return 1
    except (OSError, ValueError):
        print(json.dumps({"phase": "refused", "refusal": "windows-msi-preflight-input-refused", "install_permitted": False}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
