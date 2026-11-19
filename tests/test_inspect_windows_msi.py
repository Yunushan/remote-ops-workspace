from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts import inspect_windows_msi as msi

UPGRADE_SEQUENCE = {
    "FindRelatedProducts": 25, "LaunchConditions": 100,
    "InstallValidate": 1400, "InstallInitialize": 1500, "RemoveExistingProducts": 1501,
    "ProcessComponents": 1600, "InstallFiles": 4000, "InstallFinalize": 6600,
}


@pytest.fixture
def major_upgrade():
    return {
        "rules": [
            [msi.STOCK_UPGRADE, None, "1.0.28", None, "1", None, msi.DETECT_UPGRADE],
            [msi.STOCK_UPGRADE, "1.0.28", None, None, "2", None, msi.DETECT_DOWNGRADE],
        ],
        "execute_conditions": dict.fromkeys(msi.UPGRADE_ACTIONS, ""),
        "launch_conditions": [f"NOT {msi.DETECT_DOWNGRADE}"],
        "secure_properties": [msi.DETECT_UPGRADE, msi.DETECT_DOWNGRADE],
        "authored_detection_properties": [],
        "product_language": "0", "template_languages": ["0"],
    }


@pytest.fixture
def package(major_upgrade):
    return {
        "name": "Remote Ops Workspace", "manufacturer": "Remote Ops Workspace Contributors",
        "upgrade_code": msi.STOCK_UPGRADE, "row_component_code": msi.STOCK_CLI_COMPONENT,
        "product_code": "{11111111-2222-3333-4444-555555555555}", "package_code": "{11111111-2222-3333-4444-666666666666}",
        "architecture": "x64", "version": "1.0.28", "all_users": "1", "per_user": "", "sha256": "a" * 64,
        "upgrade_sequence": dict(UPGRADE_SEQUENCE), "disable_rollback": "",
        "major_upgrade": major_upgrade, "product_language": "0", "template_languages": ["0"],
    }


@pytest.mark.parametrize(("change", "message"), [
    ("", ""),
    ("absent", "not installed per-machine"),
    ("advertised", "not installed per-machine"),
    ("cached-package", "PackageCode differs"),
    ("version", "ProductVersion differs"),
    ("language", "ProductLanguage differs"),
    ("relative", "not a row.exe file"),
    ("wrong-file", "not a row.exe file"),
])
def test_machine_registration_must_match_the_exact_msi_and_local_launcher(package, change, message):
    properties = {"State": "5", "PackageCode": package["package_code"], "VersionString": package["version"], "Language": "0"}
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
    if change == "language":
        properties["Language"] = "1033"
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
    (None, ""),
    ("early-removal", "inside the installation transaction"),
    ("late-removal", "inside the installation transaction"),
    ("interleaved", "immediately after InstallInitialize"),
    ("missing-action", "sequence is incomplete"),
    ("disable-action", "must preserve rollback"),
    ("reboot-action", "must preserve rollback"),
    ("disable-property", "must preserve rollback"),
])
def test_upgrade_schedule_keeps_old_product_removal_in_the_rollback_transaction(change, message):
    sequence = dict(UPGRADE_SEQUENCE)
    disabled = ""
    if change == "early-removal":
        sequence["RemoveExistingProducts"] = 1401
    if change == "late-removal":
        sequence["RemoveExistingProducts"] = 6601
    if change == "interleaved":
        sequence.update(RemoveExistingProducts=1502, ExtraAction=1501)
    if change == "missing-action":
        del sequence["InstallInitialize"]
    if change == "disable-action":
        sequence["DisableRollback"] = 3500
    if change == "reboot-action":
        sequence["ScheduleReboot"] = 6400
    if change == "disable-property":
        disabled = "1"

    if change:
        with pytest.raises(ValueError, match=message):
            msi.validate_upgrade_rollback(sequence, disabled)
    else:
        msi.validate_upgrade_rollback(sequence, disabled)


@pytest.mark.parametrize(("defect", "message"), [
    ("none", ""),
    ("no-rules", "remove all older products"),
    ("ignore-remove-error", "remove all older products"),
    ("only-detect", "remove all older products"),
    ("age-floor", "remove all older products"),
    ("wrong-family", "remove all older products"),
    ("partial-removal", "remove all older products"),
    ("empty-removal-expression", "remove all older products"),
    ("conditional-removal", "must run unconditionally"),
    ("find-after-validation", "must run unconditionally"),
    ("no-downgrade-block", "refuse installation over a newer product"),
    ("missing-secure-property", "must reach the elevated installer"),
    ("preset-detection", "must reach the elevated installer"),
    ("unsupported-language", "must appear in its template summary"),
])
def test_compiled_upgrade_rule_must_actually_remove_the_predecessor(major_upgrade, defect, message):
    sequence = dict(UPGRADE_SEQUENCE)
    rule = major_upgrade["rules"][0]
    if defect == "no-rules":
        major_upgrade["rules"] = []
    if defect == "ignore-remove-error":
        rule[4] = "5"
    if defect == "only-detect":
        rule[4] = "2"
    if defect == "age-floor":
        rule[1] = "1.0.27"
    if defect == "wrong-family":
        rule[0] = "{11111111-1111-1111-1111-111111111111}"
    if defect in {"partial-removal", "empty-removal-expression"}:
        rule[5] = "CLI" if defect == "partial-removal" else ""
    if defect == "conditional-removal":
        major_upgrade["execute_conditions"]["RemoveExistingProducts"] = "0"
    if defect == "find-after-validation":
        sequence["FindRelatedProducts"] = 1401
    if defect == "no-downgrade-block":
        major_upgrade["launch_conditions"].clear()
    if defect == "missing-secure-property":
        major_upgrade["secure_properties"].remove(msi.DETECT_UPGRADE)
    if defect == "preset-detection":
        major_upgrade["authored_detection_properties"].append(msi.DETECT_UPGRADE)
    if defect == "unsupported-language":
        major_upgrade["template_languages"] = ["1033"]
    if message:
        with pytest.raises(ValueError, match=message):
            msi.validate_major_upgrade(major_upgrade, msi.STOCK_UPGRADE, "1.0.28", sequence)
    else:
        msi.validate_major_upgrade(major_upgrade, msi.STOCK_UPGRADE, "1.0.28", sequence)


@pytest.mark.parametrize(("change", "message"), [
    ("", ""), ("missing", "observations are incomplete"),
    ("asset", "built MSI asset"), ("architecture", "architecture differs"),
    ("different-family", "stock Remote Ops Workspace package family"),
    ("registration", "registration differs at after-uninstall"),
    ("different-build", "registration differs at after-reinstall"),
    ("old-schedule", "inside the installation transaction"),
    ("missing-upgrade-proof", "related-product rules are missing"),
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
    if change == "old-schedule":
        probes[0]["package"]["upgrade_sequence"] = {**UPGRADE_SEQUENCE, "RemoveExistingProducts": 1401}
    if change == "missing-upgrade-proof":
        probes[0]["package"].pop("major_upgrade")
    if change:
        with pytest.raises(ValueError, match=message):
            msi.validate_lifecycle(probes, "windows-x64", assets)
    else:
        msi.validate_lifecycle(probes, "windows-x64", assets)
