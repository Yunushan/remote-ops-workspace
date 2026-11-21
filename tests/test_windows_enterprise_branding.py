from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from remote_ops_workspace.moba_customizer import (
    build_installer_branding_plan,
    build_moba_professional_customizer_plan,
    write_moba_professional_customizer_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
DEPLOYMENT_ID = "38f685ff-3b81-4386-999b-06ac5ae6155f"
pytestmark = pytest.mark.skipif(os.name != "nt" or POWERSHELL is None, reason="requires Windows PowerShell")


@pytest.fixture
def enterprise_bundle(tmp_path):
    bundle = tmp_path / "enterprise bundle"
    logo = ROOT / "src/remote_ops_workspace/assets/remote_ops_workspace.ico"
    plan = build_moba_professional_customizer_plan(
        bundle, brand_name="Cedar & Lake", organization="Cedar's Lab", logo_path=logo,
        welcome_message="Welcome to the qualification workspace.",
    )
    write_moba_professional_customizer_bundle(plan)
    return bundle


def read_branding(bundle, deployment_id=DEPLOYMENT_ID):
    return subprocess.run(
        [
            POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command",
            "$ErrorActionPreference = 'Stop'; "
            ". ./scripts/windows_enterprise_branding.ps1; "
            "Read-WindowsEnterpriseBranding $env:ROW_TEST_BRAND_BUNDLE $env:ROW_TEST_BRAND_GUID '1.0.28'"
            " | ConvertTo-Json -Compress",
        ],
        cwd=ROOT,
        env={**os.environ, "ROW_TEST_BRAND_BUNDLE": str(bundle), "ROW_TEST_BRAND_GUID": deployment_id},
        capture_output=True, text=True, timeout=20, check=False,
    )


def test_native_branding_uses_the_customizer_plan_and_an_independent_upgrade_identity(enterprise_bundle):
    resolved = read_branding(enterprise_bundle)
    assert resolved.returncode == 0, resolved.stderr
    branding = json.loads(resolved.stdout)
    plan = build_installer_branding_plan(
        brand_name="Cedar & Lake", organization="Cedar's Lab", version="1.0.28",
    )
    assert branding["name"] == plan.product_name
    assert branding["publisher"] == plan.publisher
    assert branding["artifact_base"] + "-setup.exe" == plan.artifact_names["windows-exe"]
    assert branding["artifact_base"] + ".msi" == plan.artifact_names["windows-msi"]
    assert branding["inno_id"] == branding["msi_id"] == DEPLOYMENT_ID.upper()
    assert DEPLOYMENT_ID.upper() in branding["directory"]
    assert Path(branding["icon"]) == enterprise_bundle / "branding/logo.ico"
    assert Path(branding["welcome"]).read_text(encoding="utf-8").strip() == (
        "Welcome to the qualification workspace."
    )


@pytest.mark.parametrize("case", ("public-inno", "public-msi", "literal-newline", "outside-logo"))
def test_native_branding_rejects_public_ids_and_unsafe_installer_input(enterprise_bundle, case):
    path = enterprise_bundle / "branding/branding.json"
    metadata = json.loads(path.read_bytes())
    deployment_id = DEPLOYMENT_ID
    if case == "public-inno":
        deployment_id = "5C887096-F4E5-4AB8-8D6F-65052D08D284"
    elif case == "public-msi":
        deployment_id = "8F8A21B4-6E48-4B1A-9F5D-B9373E1807D0"
    elif case == "literal-newline":
        metadata["brand_name"] = "Cedar\nPrivilegesRequired=lowest"
    else:
        metadata["logo"] = "../elsewhere.ico"
    path.write_text(json.dumps(metadata), encoding="utf-8")
    result = read_branding(enterprise_bundle, deployment_id)
    assert result.returncode != 0
    assert "Enterprise" in result.stderr or "row customizer bundle" in result.stderr
