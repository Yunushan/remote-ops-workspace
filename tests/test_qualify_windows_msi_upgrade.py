from __future__ import annotations

import ctypes as c
import subprocess
import sys
from ctypes import wintypes as win
from types import SimpleNamespace

import pytest

from scripts import qualify_windows_msi_upgrade as upgrade
from scripts.inspect_windows_msi import ROLLBACK_ACTIONS


@pytest.mark.skipif(sys.platform != "win32", reason="requires native MSI records")
@pytest.mark.parametrize("preexisting_error", [False, True])
def test_install_decodes_native_action_records_and_clears_callback(tmp_path, preexisting_error):
    native = upgrade.UpgradeInstaller()
    records = native.dll
    records.MsiCreateRecord.argtypes = (c.c_uint,)
    records.MsiCreateRecord.restype = upgrade.HANDLE
    records.MsiRecordSetStringW.argtypes = (upgrade.HANDLE, c.c_uint, win.LPCWSTR)
    records.MsiRecordSetStringW.restype = c.c_uint

    launcher = tmp_path / "row.exe"
    launcher.write_bytes(b"previous")
    handler = None

    def set_handler(callback, mask, context, previous):
        nonlocal handler
        assert context is None and previous is None
        assert mask == ((1 << 8) | (1 << 1) | 1 if callback else 0)
        handler = callback if callback else None
        return records.MsiSetExternalUIRecord(callback, mask, context, previous)

    def message(action, description=""):
        record = records.MsiCreateRecord(3)
        try:
            assert records.MsiRecordSetStringW(record, 1, action) == 0
            assert records.MsiRecordSetStringW(record, 2, description) == 0
            return handler(None, upgrade.ACTION_START, record)
        finally:
            assert records.MsiCloseHandle(record) == 0

    def install(_path, properties):
        assert properties == "REBOOT=ReallySuppress"
        assert message("RemoveExistingProducts") == 0
        assert message("InstallFiles") == 0
        launcher.unlink()
        assert message("UnrelatedAction", description="InstallFiles") == 0
        if preexisting_error:
            assert handler(None, upgrade.INSTALL_ERROR, 0) == 0
        assert message("InstallFiles") == (0 if preexisting_error else upgrade.IDCANCEL)
        assert message("InstallFiles") == 0
        return upgrade.INSTALL_USER_EXIT

    native.dll = SimpleNamespace(MsiInstallProductW=install, MsiSetExternalUIRecord=set_handler,
                                 MsiRecordGetStringW=records.MsiRecordGetStringW)
    cancellation = upgrade.Cancellation(launcher)
    assert native.install(tmp_path / "fixture.msi", cancellation) == upgrade.INSTALL_USER_EXIT
    assert cancellation.requested == (not preexisting_error)
    assert cancellation.error_before_cancel == preexisting_error and handler is None


@pytest.mark.parametrize("modified", [False, True])
def test_release_msi_must_pass_provenance_and_keep_verified_bytes(tmp_path, monkeypatch, modified):
    tag, sha = "v1.0.29", "a" * 40
    path = tmp_path / f"remote-ops-workspace-{tag}-windows-x64.msi"
    trace = []

    def run(command, *, check, timeout):
        assert check and timeout > 0
        if command[0] == "gh":
            assert command[1:4] == ["release", "download", tag]
            assert command[4:] == ["--repo", upgrade.REPOSITORY, "--pattern", path.name, "--dir", str(tmp_path)]
            path.write_bytes(b"downloaded")
            trace.append("download")
            return
        assert command[3:] == ["--asset", str(path), "--repository", upgrade.REPOSITORY, "--tag", tag,
                               "--sha", sha, "--verify-platform-signature"]
        trace.append("provenance")
        if modified:
            path.write_bytes(b"tampered")
        else:
            raise subprocess.CalledProcessError(1, command)

    def inspect(package):
        assert package == path
        trace.append("inspect")
        return {}

    monkeypatch.setattr(upgrade.subprocess, "run", run)
    monkeypatch.setattr(upgrade, "validate_package", lambda *_: None)
    with pytest.raises(ValueError if modified else subprocess.CalledProcessError):
        upgrade.verified_msi(SimpleNamespace(inspect=inspect), tmp_path, tag, sha)
    assert trace == (["download", "provenance", "inspect"] if modified else ["download", "provenance"])


@pytest.mark.parametrize(("scenario", "error"), [
    ("success", None),
    ("too-early", "must return user exit after removal"),
    ("wrong-result", "must return user exit after removal"),
    ("wrong-rollback-bytes", "did not restore the exact previous launcher"),
    ("candidate-still-registered", "candidate still registered"),
    ("modified-candidate", "MSI bytes changed"),
])
def test_qualification_requires_actual_removal_and_exact_restoration(tmp_path, monkeypatch, scenario, error):
    launcher = tmp_path / "Program Files" / "Remote Ops Workspace" / "bin" / "row.exe"
    home = tmp_path / "workspace"
    home.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "user"))

    def make_package(role, version):
        path = tmp_path / f"{role}.msi"
        path.write_text(role)
        return path, {
            "product_code": role, "package_code": f"{role}-package", "version": version,
            "row_component_code": "row-exe", "sha256": upgrade.fingerprint(path),
            "upgrade_sequence": dict(zip(ROLLBACK_ACTIONS, (1400, 1500, 1501, 1600, 4000, 6600), strict=True)),
            "disable_rollback": "",
        }

    previous = make_package("previous", "1.0.28")
    candidate = make_package("candidate", "1.0.29")
    packages = {"previous": previous[1], "candidate": candidate[1]}
    registered = set()
    operations = []

    def registration(_native, package, state):
        code = package["product_code"]
        if state == "absent":
            upgrade.require(code not in registered, f"{code} still registered")
            return {"state": "absent"}
        upgrade.require(code in registered, f"{code} registration missing")
        return {"state": "installed", "package_code": package["package_code"], "version": package["version"],
                "row_path": str(launcher)}

    def install(path, cancellation=None):
        operations.append(path.stem if cancellation is None else "cancel")
        if cancellation is not None:
            assert cancellation.observe("InstallFiles") == 0
            assert cancellation.observe("RemoveExistingProducts") == 0
            if scenario != "too-early":
                launcher.unlink()
                assert cancellation.observe("InstallFiles") == upgrade.IDCANCEL
            launcher.write_bytes(b"changed" if scenario == "wrong-rollback-bytes" else b"previous")
            if scenario == "candidate-still-registered":
                registered.add("candidate")
            return 1 if scenario == "wrong-result" else upgrade.INSTALL_USER_EXIT
        registered.clear()
        registered.add(path.stem)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_bytes(path.stem.encode())
        if scenario == "modified-candidate" and path.stem == "previous":
            candidate[0].write_bytes(b"changed before execution")
        return 0

    def uninstall(product_code):
        assert product_code == "candidate" and registered == {"candidate"}
        operations.append("uninstall")
        registered.clear()
        launcher.unlink()

    def no_products():
        assert not registered

    def cli(command, *, cwd, env, text, timeout):
        assert command == [str(launcher), "--version"] and cwd == home and env["ROW_HOME"] == str(home)
        role = "previous" if "previous" in registered else "candidate"
        return f"remote-ops-workspace {packages[role]['version']}\n"

    monkeypatch.setattr(upgrade.subprocess, "check_output", cli)
    monkeypatch.setattr(upgrade, "inspect_registration", registration)
    native = SimpleNamespace(require_no_related_products=no_products, install=install, uninstall=uninstall)
    report = {}
    phases = []

    def save():
        phases.append(report["phase"])
    if error:
        with pytest.raises(ValueError, match=error):
            upgrade.exercise(native, previous, candidate, launcher, home, report, save)
        assert "candidate" not in operations and "uninstall" not in operations
    else:
        upgrade.exercise(native, previous, candidate, launcher, home, report, save)
        assert report["status"] == "passed" and report["phase"] == "complete"
        assert report["previous_restored"] == report["previous_installed"]
        assert operations == ["previous", "cancel", "candidate", "uninstall"]
        assert phases[-1] == "complete"
