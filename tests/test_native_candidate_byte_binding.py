from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures/native_candidate_byte_binding.ps1"
POWERSHELL = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")

VALIDATOR_SPEC = importlib.util.spec_from_file_location("binding_validator", ROOT / "scripts/candidate_native_proof.py")
VALIDATOR = importlib.util.module_from_spec(VALIDATOR_SPEC)
VALIDATOR_SPEC.loader.exec_module(VALIDATOR)


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.mark.skipif(os.name != "nt", reason="actual Windows fixture commands require Windows")
@pytest.mark.parametrize("case", [
    "wrong-cli", "wrong-gui", "wrong-resources", "matching-cli-launch", "all-paths", "changed-build",
])
def test_actual_wrong_bytes_are_refused_before_execution_with_public_path_receipt(tmp_path, case):
    # Execute authorized test commands directly; leave the machine's
    # script execution policy unchanged and never run the installer main body.
    commands = FIXTURE.read_text(encoding="utf-8").split("\n", 1)[1]
    commands = (
        "$FixtureRoot=" + _ps_quote(tmp_path) + ";$Case=" + _ps_quote(case)
        + ";$SmokeSource=" + _ps_quote(ROOT / "scripts/smoke_windows_native.ps1") + "\n" + commands
    )
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", commands],
        env={**os.environ, "PSMODULEPATH": str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/Modules")},
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BYTE_BINDING_FIXTURE_PASSED" in result.stdout
    # Positive control proves the native-command observer actually fires
    # while running trusted curl; refusal observes zero native/start attempts.
    invocations = json.loads((tmp_path / "command-invocations.json").read_text(encoding="utf-8"))
    assert invocations["native_command_attempts"] == (1 if case == "matching-cli-launch" else 0)
    assert invocations["start_process_attempts"] == 0
    receipt_path = tmp_path / "build/native-smoke/windows-x64/candidate-runtime-byte-binding.json"
    raw = receipt_path.read_text(encoding="utf-8")
    receipt = json.loads(raw)
    assert str(tmp_path) not in raw and str(tmp_path).replace("\\", "/") not in raw
    assert "approval" in receipt["scope"] and "excludes" in receipt["scope"]
    assert receipt["target"] == "windows-x64"
    assert {item["path"] for item in receipt["expected_executables"]} == {
        "build/native/windows/pyinstaller-dist/row.exe", "build/native/windows/pyinstaller-dist/row-gui.exe",
    }
    for item in receipt["expected_executables"]:
        assert len(item["sha256"]) == 64 and item["sha256"] == item["sha256"].lower()
    if case.startswith("wrong-"):
        assert receipt["status"] == "failed" and receipt["smoke_complete"] is False
        assert not (tmp_path / "unexpected-launch.txt").exists()
        assert receipt["observations"][-1]["matched"] is False
        assert receipt["observations"][-1]["observed_sha256"] != receipt["observations"][-1]["expected_sha256"]
    elif case == "all-paths":
        assert receipt["status"] == "bound" and receipt["smoke_complete"] is True
        assert {item["path"] for item in receipt["observations"]} == set(receipt["required_paths"])
        assert all(item["matched"] for item in receipt["observations"])
        archives = [{"path": item["path"], "artifact_sha256": hashlib.sha256((tmp_path / item["path"]).read_bytes()).hexdigest(), "toc": ["fixture"]}
                    for item in receipt["expected_executables"]]
        VALIDATOR.validate_windows_byte_binding(receipt, archives, "windows-x64")
        with pytest.raises(ValueError, match="MSI lifecycle observations are incomplete"):
            VALIDATOR.validate_windows_byte_binding(receipt, archives, "windows-x64", [])
        # A valid smoke receipt cannot borrow completeness from different
        # inspected executable bytes, target or claimed observation digests.
        for mutation in ("archive-bytes", "observed-bytes", "missing-path", "target", "incomplete", "boolean-schema"):
            changed_receipt = json.loads(json.dumps(receipt))
            changed_archives = json.loads(json.dumps(archives))
            target = "windows-x64"
            if mutation == "archive-bytes":
                changed_archives[0]["artifact_sha256"] = "0" * 64
            elif mutation == "observed-bytes":
                changed_receipt["observations"][0]["observed_sha256"] = "0" * 64
            elif mutation == "missing-path":
                changed_receipt["observations"].pop()
            elif mutation == "target":
                target = "windows-arm64"
            elif mutation == "incomplete":
                changed_receipt["smoke_complete"] = False
            else:
                changed_receipt["schema_version"] = True
            with pytest.raises(ValueError):
                VALIDATOR.validate_windows_byte_binding(changed_receipt, changed_archives, target)
    elif case == "changed-build":
        assert receipt["status"] == "failed" and receipt["smoke_complete"] is False
    else:
        assert receipt["status"] == "in-progress" and receipt["smoke_complete"] is False
        assert (tmp_path / "unexpected-launch.txt").read_text() == "verified trusted CLI version"
        assert receipt["observations"][-1]["matched"] is True
        observed = tmp_path / "build/native-smoke/windows-x64/portable/bin/row.exe"
        assert receipt["observations"][-1]["observed_sha256"] == hashlib.sha256(observed.read_bytes()).hexdigest()


@pytest.mark.skipif(os.name != "nt", reason="actual Windows fixture commands require Windows")
@pytest.mark.parametrize("case", ["host-local", "host-self-hosted", "host-wrong-checkout", "host-allowed", "host-existing-directory", "host-existing-owned-install", "host-existing-inno", "host-existing-msi", "host-registry-error", "host-registration-matcher", "deletion-escape", "deletion-prefix-sibling", "deletion-link", "deletion-linked-ancestor", "deletion-contained"])
def test_full_native_entry_and_recursive_deletion_guards(tmp_path, case):
    commands = FIXTURE.read_text(encoding="utf-8").split("\n", 1)[1]
    commands = "$FixtureRoot=" + _ps_quote(tmp_path) + ";$Case=" + _ps_quote(case) + ";$SmokeSource=" + _ps_quote(ROOT / "scripts/smoke_windows_native.ps1") + "\n" + commands
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", commands],
        env={**os.environ, "PSMODULEPATH": str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/Modules")},
        capture_output=True, text=True, timeout=45, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BYTE_BINDING_FIXTURE_PASSED" in result.stdout


def test_every_recursive_native_smoke_removal_uses_the_verified_helper():
    source = (ROOT / "scripts/smoke_windows_native.ps1").read_text(encoding="utf-8")
    recursive_removals = [line.strip() for line in source.splitlines() if "Remove-Item" in line and "-Recurse" in line]
    assert recursive_removals == ["Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop"]
    helper = source.split("function Remove-CandidateSmokeTree([string]$Path) {", 1)[1].split("\n}", 1)[0]
    assert helper.index("Assert-CandidateSmokePath $Path") < helper.index("Remove-Item -LiteralPath $Path")
    for target in ("$SmokeRoot", "$PortableInstallDir", "$VaultHome"):
        assert "Remove-CandidateSmokeTree " + target in source
    # This is a source regression only; fixture execution loads AST function
    # definitions and never evaluates the guarded installer main body.
    assert source.index("\nAssert-DisposableCandidateHost\n") < source.index("\nif (!$Version) {")



@pytest.mark.skipif(os.name != "nt", reason="Windows smoke hashing uses PowerShell")
@pytest.mark.parametrize("changed", [False, True])
def test_signed_windows_smoke_binds_zip_exe_and_msi_bytes(tmp_path, changed):
    source = (ROOT / "scripts/smoke_windows_native.ps1").read_text(encoding="utf-8")
    initial = source.split("\nInitialize-CandidateByteBinding\n", 1)[1].split("\n# extract /", 1)[0]
    final = source.rsplit('\nif ($RequireReleaseSigning -and $Arch -ne "x86") {', 1)[1]
    final = '\nif ($RequireReleaseSigning -and $Arch -ne "x86") {' + final.split("\nComplete-CandidateByteBinding", 1)[0]
    packages = {"NativeZip": "portable.zip", "SetupExe": "setup.exe", "Msi": "setup.msi"}
    setup = ["$ErrorActionPreference = 'Stop'", "$RequireReleaseSigning = $true", '$Arch = "x64"',
             "$script:CandidateByteBinding = [ordered]@{}", "function Save-CandidateByteBinding {}"]
    for variable, filename in packages.items():
        package = tmp_path / filename
        package.write_bytes(filename.encode())
        setup.append(f"${variable} = {_ps_quote(package)}")
    if changed:
        initial += '\n[IO.File]::WriteAllBytes($SetupExe, [byte[]](1, 2, 3))\n'
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command",
         "\n".join([*setup, initial, final, "$script:CandidateByteBinding.installer_sha256 | ConvertTo-Json"])],
        env={**os.environ, "PSMODULEPATH": str(POWERSHELL.parent / "Modules")},
        timeout=30, capture_output=True, text=True, check=False,
    )
    if changed:
        assert result.returncode != 0
        assert "Installer bytes changed during native smoke: setup.exe" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {
            filename: hashlib.sha256(filename.encode()).hexdigest() for filename in packages.values()
        }


def _semantic_receipt():
    hashes = {"cli": "a" * 64, "gui": "b" * 64}
    paths = ["portable/bin/row.exe", "exe-install/bin/row.exe", "msi-install/bin/row.exe", "portable/bin/row-gui.exe", "portable/Remote Ops Workspace GUI.exe", "exe-install/bin/row-gui.exe", "msi-install/bin/row-gui.exe"]
    expected = [{"role": role, "path": "build/native/windows/pyinstaller-dist/" + ("row.exe" if role == "cli" else "row-gui.exe"), "sha256": value} for role, value in hashes.items()]
    observed = []
    for path in paths:
        role = "cli" if path.endswith("/row.exe") else "gui"
        observed.append({"path": path, "role": role, "matched": True, "expected_sha256": hashes[role], "observed_sha256": hashes[role]})
    return {"schema_version": 1, "target": "windows-x64", "status": "bound", "smoke_complete": True, "required_paths": paths, "expected_executables": expected, "observations": observed}, [{"path": item["path"], "artifact_sha256": item["sha256"], "toc": ["semantic fixture"]} for item in expected]



def test_release_gui_archive_requires_binding_to_native_smoke(tmp_path, monkeypatch):
    import sys

    from scripts import inspect_windows_msi

    binding, archive_rows = _semantic_receipt()
    target = binding["target"]
    gui_archive = archive_rows[1]
    gui_archive["toc"] = [{"name": "PYZ.pyz"}]
    gui_archive["pyz_toc"] = {
        name: [0, position, 50]
        for position, name in enumerate(VALIDATOR.GUI_PYZ_REQUIRED_MODULES, start=1)
    }
    archives = {}
    for row in archive_rows:
        executable = tmp_path / row["path"]
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_bytes(b"inert fixture")
        archives[executable] = row
    assets = tmp_path / "native-dist/windows"
    assets.mkdir(parents=True)
    msi = assets / "remote-ops-workspace-v1.0.28-windows-x64.msi"
    msi.write_bytes(b"inert package")
    smoke = tmp_path / "build/native-smoke" / target / "candidate-runtime-byte-binding.json"
    report = smoke.with_name("gui-archive-proof.json")

    def check_lifecycle(_probes, native_target, native_assets):
        assert native_target == target
        assert native_assets == [{"path": msi.name, "sha256": hashlib.sha256(msi.read_bytes()).hexdigest()}]

    monkeypatch.setattr(inspect_windows_msi, "validate_lifecycle", check_lifecycle)
    monkeypatch.setattr(VALIDATOR, "ROOT", tmp_path)
    monkeypatch.setattr(VALIDATOR, "archive_inventory", archives.__getitem__)
    monkeypatch.setattr(sys, "argv", ["proof.py", "verify-gui", "--target", target, "--asset-dir", "native-dist/windows"])

    observation = next(row for row in binding["observations"] if row["role"] == "gui")
    observation["observed_sha256"] = "c" * 64
    VALIDATOR.save(smoke, binding)
    with pytest.raises(ValueError, match="observed executable bytes do not match"):
        VALIDATOR.main()
    assert not report.exists()

    observation["observed_sha256"] = gui_archive["artifact_sha256"]
    VALIDATOR.save(smoke, binding)
    assert VALIDATOR.main() == 0
    result = json.loads(report.read_bytes())
    assert result["status"] == "passed"
    assert result["artifact_sha256"] == gui_archive["artifact_sha256"]
    assert result["smoke_binding_sha256"] == hashlib.sha256(smoke.read_bytes()).hexdigest()


@pytest.mark.parametrize("change", [None, "archive-bytes", "observed-bytes", "missing-path", "target", "incomplete", "boolean-schema", "wrong-role"])
def test_candidate_validator_rejects_incorrect_byte_and_completeness_records_on_every_host(change):
    receipt, archives = _semantic_receipt()
    target = "windows-x64"
    if change == "archive-bytes":
        archives[0]["artifact_sha256"] = "0" * 64
    elif change == "observed-bytes":
        receipt["observations"][0]["observed_sha256"] = "0" * 64
    elif change == "missing-path":
        receipt["observations"].pop()
    elif change == "target":
        target = "windows-arm64"
    elif change == "incomplete":
        receipt["smoke_complete"] = False
    elif change == "boolean-schema":
        receipt["schema_version"] = True
    elif change == "wrong-role":
        receipt["observations"][0]["role"] = "gui"
    if change is None:
        VALIDATOR.validate_windows_byte_binding(receipt, archives, target)
    else:
        with pytest.raises(ValueError):
            VALIDATOR.validate_windows_byte_binding(receipt, archives, target)
