from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import inspect_windows_msi as msi


@pytest.fixture
def package():
    return {
        "name": "Remote Ops Workspace", "manufacturer": "Remote Ops Workspace Contributors",
        "upgrade_code": msi.STOCK_UPGRADE, "row_component_code": msi.STOCK_CLI_COMPONENT,
        "product_code": "{11111111-2222-3333-4444-555555555555}", "package_code": "{11111111-2222-3333-4444-666666666666}",
        "architecture": "x64", "version": "1.0.28", "all_users": "1", "per_user": "", "sha256": "a" * 64,
    }


@pytest.mark.parametrize(("change", "message"), [
    ("", ""),
    ("absent", "not installed per-machine"),
    ("advertised", "not installed per-machine"),
    ("cached-package", "PackageCode differs"),
    ("version", "ProductVersion differs"),
    ("relative", "not a row.exe file"),
    ("wrong-file", "not a row.exe file"),
])
def test_machine_registration_must_match_the_exact_msi_and_local_launcher(package, change, message):
    properties = {"State": "5", "PackageCode": package["package_code"], "VersionString": package["version"]}
    get_path = True
    path = r"C:\Program Files\Remote Ops Workspace\bin\row.exe"
    if change in {"absent", "advertised"}:
        properties["State"] = None if change == "absent" else "1"
        get_path = False
    if change == "cached-package":
        properties["PackageCode"] = package["product_code"]
        get_path = False
    if change == "version":
        properties["VersionString"] = "1.0.27"
        get_path = False
    if change == "relative":
        path = "row.exe"
    if change == "wrong-file":
        path = r"C:\Program Files\Remote Ops Workspace\bin\other.exe"

    def product(code, field):
        assert code == package["product_code"]
        return properties[field]

    def component_path(code, component):
        assert get_path
        assert (code, component) == (package["product_code"], msi.STOCK_CLI_COMPONENT)
        return path

    native = SimpleNamespace(product=product, component_path=component_path)
    if change:
        with pytest.raises(ValueError, match=message):
            msi.inspect_registration(native, package, "installed")
    else:
        assert msi.inspect_registration(native, package, "installed") == {
            "state": "installed", "package_code": package["package_code"], "version": package["version"], "row_path": path,
        }


def test_advertised_product_is_not_an_absent_registration(package):
    native = SimpleNamespace(product=lambda *_args: "1")
    with pytest.raises(ValueError, match="still has a per-machine registration"):
        msi.inspect_registration(native, package, "absent")
    native.product = lambda *_args: None
    assert msi.inspect_registration(native, package, "absent") == {"state": "absent"}


@pytest.mark.parametrize(("change", "message"), [
    ("", ""), ("missing", "observations are incomplete"),
    ("asset", "built MSI asset"), ("architecture", "architecture differs"),
    ("different-family", "stock Remote Ops Workspace package family"),
    ("registration", "registration differs at after-uninstall"),
    ("different-build", "registration differs at after-reinstall"),
])
def test_candidate_lifecycle_binds_the_exact_asset_and_all_registration_states(package, change, message):
    installed = {"state": "installed", "package_code": package["package_code"], "version": package["version"],
                 "row_path": "msi-install/bin/row.exe"}
    probes = [
        {"probe": probe, "package": dict(package), "registration": dict(installed if 0 < index < 3 else {"state": "absent"})}
        for index, probe in enumerate(msi.PROBES)
    ]
    assets = [{"path": "native-dist/windows/remote-ops-workspace-v1.0.28-windows-x64.msi", "sha256": package["sha256"]}]
    if change == "missing":
        probes.pop()
    if change == "asset":
        assets[0]["sha256"] = "b" * 64
    if change == "architecture":
        probes[0]["package"]["architecture"] = "arm64"
    if change == "different-family":
        probes[0]["package"]["upgrade_code"] = package["product_code"]
    if change == "registration":
        probes[-1]["registration"] = installed
    if change == "different-build":
        probes[2]["package"]["sha256"] = "b" * 64
    if change:
        with pytest.raises(ValueError, match=message):
            msi.validate_lifecycle(probes, "windows-x64", assets)
    else:
        msi.validate_lifecycle(probes, "windows-x64", assets)
