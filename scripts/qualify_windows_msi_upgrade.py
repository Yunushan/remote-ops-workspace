"""Qualify rollback and retry between signed stock Windows releases or sealed candidates."""

from __future__ import annotations

import argparse
import ctypes as c
import json
import os
import platform
import subprocess
import sys
import zipfile
from contextlib import contextmanager
from ctypes import wintypes as win
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from check_release_provenance import (  # noqa: E402
    native_installer_signature_commands,
    normalize_sha,
    normalize_tag,
    verify_platform_signature,
)
from inspect_windows_msi import (  # noqa: E402
    HANDLE,
    LIMIT,
    STOCK_UPGRADE,
    Installer,
    confirm,
    fingerprint,
    inspect_registration,
    require,
    validate_package,
    validate_upgrade_rollback,
)
from release_candidate_inventory import GitHubClient  # noqa: E402
from windows_msi_candidate_source import InventoryPointer, materialize_msi  # noqa: E402

from remote_ops_workspace.windows_private_storage import _Native  # noqa: E402

REPOSITORY = "Yunushan/remote-ops-workspace"
RECEIPT = Path("build/native-smoke/windows-x64/signed-msi-upgrade.json")
ACTION_START = 0x08000000
FATAL_EXIT = 0x00000000
INSTALL_ERROR = 0x01000000
INSTALL_USER_EXIT = 1602
UILEVEL_NONE = 2
IDCANCEL = 2
INSTALLSTATE_ABSENT = 2


class Cancellation:
    def __init__(self, launcher: Path) -> None:
        self.launcher = launcher
        self.removal_started = False
        self.requested = False
        self.error_before_cancel = False

    def observe(self, action: str) -> int:
        if action == "RemoveExistingProducts":
            self.removal_started = True
        if action == "InstallFiles" and self.removal_started and not self.requested and not self.error_before_cancel:
            try:
                self.launcher.lstat()
            except FileNotFoundError:
                self.requested = True
                return IDCANCEL
        return 0


class UpgradeInstaller(Installer):
    def __init__(self) -> None:
        super().__init__()
        self.callback_type = c.WINFUNCTYPE(c.c_int, c.c_void_p, c.c_uint, HANDLE)
        signatures = {
            "MsiSetInternalUI": (c.c_uint, c.c_uint, c.c_void_p),
            "MsiSetExternalUIRecord": (c.c_uint, self.callback_type, win.DWORD, c.c_void_p, c.c_void_p),
            "MsiInstallProductW": (c.c_uint, win.LPCWSTR, win.LPCWSTR),
            "MsiConfigureProductExW": (c.c_uint, win.LPCWSTR, c.c_int, c.c_int, win.LPCWSTR),
        }
        for name, (result, *arguments) in signatures.items():
            call = getattr(self.dll, name)
            call.argtypes = arguments
            call.restype = result
        self.dll.MsiSetInternalUI(UILEVEL_NONE, None)

    def install(self, path: Path, cancellation: Cancellation | None = None) -> int:
        if cancellation is None:
            return self.dll.MsiInstallProductW(str(path), "REBOOT=ReallySuppress")
        callback_error = None

        @self.callback_type
        def on_action(_context, message, record):
            nonlocal callback_error
            message_type = message & 0xFF000000
            if message_type in (FATAL_EXIT, INSTALL_ERROR) and not cancellation.requested:
                cancellation.error_before_cancel = True
            if message_type != ACTION_START or not record:
                return 0
            try:
                # Field 1 is the action identifier. Field 2 is its description.
                buffer, length = c.create_unicode_buffer(LIMIT), win.DWORD(LIMIT)
                result = self.dll.MsiRecordGetStringW(record, 1, buffer, c.byref(length))
                if result == 0:
                    return cancellation.observe(buffer.value)
            except OSError as exc:
                callback_error = exc
            return 0

        messages = sum(1 << (message >> 24) for message in (FATAL_EXIT, INSTALL_ERROR, ACTION_START))
        confirm(self.dll.MsiSetExternalUIRecord(on_action, messages, None, None), "MsiSetExternalUIRecord")
        try:
            result = self.dll.MsiInstallProductW(str(path), "REBOOT=ReallySuppress")
        finally:
            confirm(self.dll.MsiSetExternalUIRecord(self.callback_type(), 0, None, None),
                    "clear MsiSetExternalUIRecord")
        if callback_error is not None:
            raise callback_error
        return result

    def require_no_related_products(self) -> None:
        require(not self.related_products(STOCK_UPGRADE), "expected no installed or advertised stock MSI products")

    def uninstall(self, product_code: str) -> None:
        confirm(self.dll.MsiConfigureProductExW(product_code, 0, INSTALLSTATE_ABSENT, "REBOOT=ReallySuppress"),
                "uninstall exact MSI product")


def hosted_source() -> str:
    require(sys.platform == "win32" and platform.machine() == "AMD64", "requires a native Windows x64 runner")
    required_env = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/windows-msi-upgrade-qualification.yml@refs/heads/main",
    }
    require(all(os.environ.get(key) == value for key, value in required_env.items()),
            "requires the canonical main-branch workflow on a disposable GitHub-hosted runner")
    require(os.environ.get("GITHUB_WORKSPACE") and Path(os.environ["GITHUB_WORKSPACE"]).resolve() == ROOT,
            "hosted Windows upgrade checkout does not match the source root")
    source = normalize_sha(os.environ.get("GITHUB_SHA", ""))
    observed = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    require(source == observed, "workflow source differs from the hosted checkout")
    return source


def release_pair(args: argparse.Namespace) -> tuple[tuple[str, str], tuple[str, str]]:
    previous, candidate = (normalize_tag(tag) for tag in (args.previous_tag, args.candidate_tag))
    old_sha, new_sha = (normalize_sha(sha) for sha in (args.previous_sha, args.candidate_sha))
    previous_version, candidate_version = (tuple(map(int, tag[1:].split("."))) for tag in (previous, candidate))
    require(previous_version < candidate_version and old_sha != new_sha, "expected two ordered release tags and distinct commits")
    return (previous, old_sha), (candidate, new_sha)


@contextmanager
def verified_msi(native: Installer, storage, directory: Path, tag: str, sha: str, *,
                 candidate=False, inventory: InventoryPointer | None = None):
    if inventory is None:
        path = directory / f"remote-ops-workspace-{tag}-windows-x64.msi"
        subprocess.run(["gh", "release", "download", tag, "--repo", REPOSITORY, "--pattern", path.name,
                        "--dir", str(directory)], check=True, timeout=240)
        source = {"kind": "immutable-release"}
        expected = None
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        require(bool(token), "sealed candidate verification requires a GitHub token")
        client = GitHubClient(REPOSITORY, token, api_url="https://api.github.com")
        path, expected, source = materialize_msi(client, REPOSITORY, directory, tag, sha, inventory)
    held = storage.open_file(str(path), read_only=True)
    try:
        digest = fingerprint(path)
        if expected is None:
            subprocess.run([sys.executable, "-I", str(ROOT / "scripts/check_release_provenance.py"),
                            "--asset", str(path), "--repository", REPOSITORY, "--tag", tag,
                            "--sha", sha, "--verify-platform-signature"], check=True, timeout=300)
        else:
            require(digest == expected["sha256"] and path.stat().st_size == expected["size"],
                    "locked MSI does not match the sealed candidate inventory")
            verify_platform_signature(native_installer_signature_commands(path, registered_sdk=True))
        package = native.inspect(path, require_transactional_upgrade=candidate)
        validate_package(package, "x64", tag[1:])
        require(fingerprint(path) == digest, "Windows MSI changed during provenance and identity verification")
        yield path, {**package, "sha256": digest, "release_tag": tag, "release_sha": sha,
                     "name_on_release": path.name, "source": source}
    finally:
        storage.close(held)


def launcher_snapshot(native: Installer, package: dict, expected: Path, home: Path) -> dict:
    registration = inspect_registration(native, package, "installed")
    path = Path(registration["row_path"])
    require(path == expected and path.resolve(strict=True) == expected, "MSI launcher is outside stock Program Files")
    digest = fingerprint(path)
    env = os.environ.copy()
    env["ROW_HOME"] = str(home)
    output = subprocess.check_output([str(path), "--version"], cwd=home, env=env, text=True, timeout=60).strip()
    require(output == f"remote-ops-workspace {package['version']}" and fingerprint(path) == digest,
            "registered MSI launcher version or bytes differ")
    return {**registration, "row_path": "Program Files/Remote Ops Workspace/bin/row.exe", "launcher_sha256": digest}


def exercise(native: UpgradeInstaller, previous: tuple[Path, dict], candidate: tuple[Path, dict],
             launcher: Path, home: Path, report: dict, save) -> None:
    old_path, old = previous
    new_path, new = candidate
    require(old["product_code"] != new["product_code"] and old["package_code"] != new["package_code"],
            "major upgrade requires distinct ProductCode and PackageCode values")
    validate_upgrade_rollback(new["upgrade_sequence"], new["disable_rollback"])
    native.require_no_related_products()
    for directory in (launcher.parents[1], Path(os.environ["LOCALAPPDATA"]) / "Remote Ops Workspace"):
        require(not os.path.lexists(directory), "Windows MSI drill refuses a preexisting stock install directory")

    def install(path: Path, package: dict, cancellation: Cancellation | None = None) -> int:
        require(fingerprint(path) == package["sha256"], "MSI bytes changed before execution")
        result = native.install(path, cancellation)
        require(fingerprint(path) == package["sha256"], "MSI bytes changed during execution")
        return result

    report["phase"] = "install-previous"
    save()
    confirm(install(old_path, old), "install previous signed MSI")
    before = launcher_snapshot(native, old, launcher, home)
    inspect_registration(native, new, "absent")
    report.update(phase="cancel-upgrade", previous_installed=before)
    save()

    cancellation = Cancellation(launcher)
    result = install(new_path, new, cancellation)
    report["cancellation"] = {"exit_code": result, "removal_started": cancellation.removal_started,
                              "installer_error_before_cancel": cancellation.error_before_cancel,
                              "previous_launcher_absent_at_cancel": cancellation.requested}
    save()
    require(result == INSTALL_USER_EXIT and cancellation.requested,
            "interrupted upgrade must return user exit after removal of the previous launcher")
    restored = launcher_snapshot(native, old, launcher, home)
    inspect_registration(native, new, "absent")
    require(restored == before, "cancelled upgrade did not restore the exact previous launcher and registration")
    report.update(phase="retry-upgrade", previous_restored=restored, candidate_absent_after_cancel=True)
    save()

    confirm(install(new_path, new), "retry signed MSI upgrade")
    upgraded = launcher_snapshot(native, new, launcher, home)
    inspect_registration(native, old, "absent")
    require(upgraded["launcher_sha256"] != before["launcher_sha256"], "successful upgrade retained the previous launcher bytes")
    report.update(phase="uninstall-candidate", candidate_installed=upgraded, previous_absent_after_retry=True)
    save()
    native.uninstall(new["product_code"])
    native.require_no_related_products()
    require(not os.path.lexists(launcher), "candidate launcher remains after uninstall")
    report.update(phase="complete", status="passed", stock_products_absent_after_uninstall=True)
    save()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("previous-tag", "previous-sha", "candidate-tag", "candidate-sha"):
        parser.add_argument("--" + name, required=True)
    for name in ("previous-inventory", "candidate-inventory"):
        parser.add_argument("--" + name, type=InventoryPointer.parse, metavar="COORDINATES",
                            help="use an attested candidate with RUN_ID ARTIFACT_ID sha256:DIGEST")
    args = parser.parse_args()
    try:
        source = hosted_source()
        previous_ref, candidate_ref = release_pair(args)
        output = ROOT / RECEIPT
        output.parent.mkdir(parents=True, exist_ok=True)
        require(not os.path.lexists(output), "Windows MSI drill refuses to overwrite an existing receipt")
        report = {"schema": "row.signed-windows-msi-upgrade.v1", "status": "failed", "phase": "verify-release-assets",
                  "source_commit": source, "run_id": os.environ["GITHUB_RUN_ID"],
                  "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "target": "windows-x64"}

        def save() -> None:
            temporary = output.with_suffix(".tmp")
            temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            temporary.replace(output)

        save()
        native = UpgradeInstaller()
        storage = _Native()
        launcher = Path(os.environ["ProgramFiles"]) / "Remote Ops Workspace/bin/row.exe"
        with TemporaryDirectory(prefix="row-signed-msi-", dir=os.environ["RUNNER_TEMP"]) as directory:
            staging = Path(directory)
            with (
                verified_msi(native, storage, staging, *previous_ref, inventory=args.previous_inventory) as previous,
                verified_msi(native, storage, staging, *candidate_ref, candidate=True,
                             inventory=args.candidate_inventory) as candidate,
            ):
                for name in ("GH_TOKEN", "GITHUB_TOKEN"):
                    os.environ.pop(name, None)
                report.update(previous=previous[1], candidate=candidate[1], input_read_only_sharing_held=True)
                home = staging / "workspace"
                home.mkdir()
                exercise(native, previous, candidate, launcher, home, report, save)
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Windows MSI upgrade qualification: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
