from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd().resolve()
SCOPE = "unreleased PR candidate runtime evidence; no release, signing trust, notarization, or compliance approval"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def fingerprint():
    names = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    files = [
        {"path": name, "sha256": digest(ROOT / name) if (ROOT / name).is_file() else "missing"}
        for name in sorted(names)
        if name
    ]
    material = "".join(row["path"] + "\0" + row["sha256"] + "\n" for row in files).encode()
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
        "tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"]).decode().strip(),
        "checkout_bytes_sha256": hashlib.sha256(material).hexdigest(),
        "files": files,
    }


def archive_inventory(path):
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(path))
    members = []
    for name, entry in sorted(reader.toc.items()):
        data = reader.extract(name)
        members.append(
            {
                "name": name,
                "toc": list(entry),
                "sha256": hashlib.sha256(data).hexdigest() if data is not None else None,
            }
        )
    result = {"path": str(path.relative_to(ROOT)), "artifact_sha256": digest(path), "toc": members}
    if "PYZ.pyz" in reader.toc:
        result["pyz_toc"] = {
            name: list(entry)
            for name, entry in sorted(reader.open_embedded_archive("PYZ.pyz").toc.items())
        }
    return result


def validate_windows_byte_binding(report, archives, target):
    """Bind the smoke's observed executable bytes to the inspected CArchives.

    This validates candidate-produced records, not independent approval or an
    adversarial runner. External runtime files are outside this narrow proof.
    """
    gui = target != "windows-x86"
    expected_roles = {"cli": "build/native/windows/pyinstaller-dist/row.exe"}
    paths = {"portable/bin/row.exe", "exe-install/bin/row.exe", "msi-install/bin/row.exe"}
    if gui:
        expected_roles["gui"] = "build/native/windows/pyinstaller-dist/row-gui.exe"
        paths.update({"portable/bin/row-gui.exe", "portable/Remote Ops Workspace GUI.exe",
                      "exe-install/bin/row-gui.exe", "msi-install/bin/row-gui.exe"})
    inspected = {item["path"].replace("\\", "/"): item["artifact_sha256"]
                 for item in archives if "inventory_error" not in item and item.get("toc")}
    if (
        type(report.get("schema_version")) is not int or report["schema_version"] != 1
        or report.get("target") != target or report.get("status") != "bound"
        or report.get("smoke_complete") is not True
        or set(report.get("required_paths", [])) != paths
    ):
        raise ValueError("candidate executable binding report is incomplete or belongs to another target")
    expected = report.get("expected_executables", [])
    if len(expected) != len(expected_roles) or {item.get("role") for item in expected} != set(expected_roles):
        raise ValueError("candidate executable binding has incomplete expected build outputs")
    hashes = {}
    for item in expected:
        role = item["role"]
        if item.get("path") != expected_roles[role] or inspected.get(item["path"]) != item.get("sha256"):
            raise ValueError("candidate expected executable bytes differ from inspected PyInstaller archive")
        hashes[role] = item["sha256"]
    observed = report.get("observations", [])
    if {item.get("path") for item in observed} != paths:
        raise ValueError("candidate smoke did not bind every required executable path")
    for item in observed:
        role = "cli" if item["path"].endswith("/row.exe") else "gui"
        if (
            item.get("role") != role or item.get("matched") is not True
            or item.get("expected_sha256") != hashes.get(role)
            or item.get("observed_sha256") != hashes.get(role)
        ):
            raise ValueError("candidate observed executable bytes do not match inspected PyInstaller archive")


def validate_posix_byte_binding(report, archives, target, assets, launchers=()):
    """Validate per-probe entrypoint hashes; external runtime files are excluded."""
    import re

    from candidate_posix_byte_binding import APPIMAGE_LAUNCHER, target_contract

    outputs, paths, probes = target_contract(target)
    if not isinstance(report, dict) or (
        type(report.get("schema_version")) is not int or report["schema_version"] != 1
        or report.get("target") != target or report.get("status") != "bound"
        or report.get("smoke_complete") is not True
        or set(report.get("required_paths", [])) != set(paths)
        or {(row["path"], row["phase"], row["probe"]) for row in report.get("required_probes", [])} != probes
    ):
        raise ValueError("candidate POSIX executable binding report is incomplete or belongs to another target")
    expected = report.get("expected_executables", [])
    if len(expected) != len(outputs) or {row.get("role") for row in expected} != set(outputs):
        raise ValueError("candidate POSIX expected build outputs are incomplete")
    hashes = {}
    for row in expected:
        role = row["role"]
        inspected = [item for item in archives if item.get("path", "").replace("\\", "/") == outputs[role]
                     and "inventory_error" not in item and item.get("toc")]
        if len(inspected) != 1 or row.get("path") != outputs[role] or row.get("sha256") != inspected[0].get("artifact_sha256"):
            raise ValueError("candidate POSIX executable bytes differ from inspected original PyInstaller archive")
        hashes[role] = row["sha256"]
    observations = report.get("observations", [])
    if {(row["path"], row["phase"], row["probe"]) for row in observations} != probes:
        raise ValueError("candidate POSIX smoke did not bind every required probe")
    for row in observations:
        role = paths[row["path"]]
        if row.get("role") != role or row.get("matched") is not True or row.get("expected_sha256") != hashes[role] or row.get("observed_sha256") != hashes[role]:
            raise ValueError("candidate POSIX observed executable bytes do not match inspected original PyInstaller archive")
    packages = report.get("expected_packages", [])
    package_observations = report.get("package_observations", [])
    if target.startswith("linux-"):
        if len(packages) != 2 or {row.get("role") for row in packages} != {"appimage-runtime", "appimage-launcher"}:
            raise ValueError("candidate AppImage build artifact or launcher binding is missing")
        hashes = {}
        for package in packages:
            package_path = package.get("path", "")
            if package["role"] == "appimage-launcher":
                if package_path != APPIMAGE_LAUNCHER:
                    raise ValueError("candidate AppImage launcher source path is not canonical")
            elif (
                not isinstance(package_path, str) or "\\" in package_path
                or Path(package_path).is_absolute() or ".." in Path(package_path).parts
                or not re.fullmatch(r"remote-ops-workspace-v[0-9]+\.[0-9]+\.[0-9]+-" + re.escape(target) + r"\.AppImage", Path(package_path).name)
            ):
                raise ValueError("candidate AppImage runtime source path belongs to another target")
            source = assets if package["role"] == "appimage-runtime" else launchers
            matching = [row for row in source if row.get("path", "").replace("\\", "/") == package.get("path")]
            if len(matching) != 1 or matching[0].get("sha256") != package.get("sha256"):
                raise ValueError("candidate AppImage runtime or launcher bytes differ from recorded build output")
            hashes[package["role"]] = package["sha256"]
        required_packages = {("appimage/runtime.AppImage", stage, "extract") for stage in ("install", "reinstall")}
        required_packages.update({("appimage/AppRun", stage, probe) for stage in ("install", "reinstall") for probe in ("version", "platforms")})
        if {(row["path"], row["phase"], row["probe"]) for row in package_observations} != required_packages:
            raise ValueError("candidate AppImage runtime or launcher was not checked before every invocation")
        for row in package_observations:
            role = "appimage-runtime" if row["path"] == "appimage/runtime.AppImage" else "appimage-launcher"
            if row.get("role") != role or row.get("matched") is not True or row.get("expected_sha256") != hashes[role] or row.get("observed_sha256") != hashes[role]:
                raise ValueError("candidate observed AppImage runtime or launcher bytes differ from recorded build output")

    elif packages or package_observations:
        raise ValueError("unexpected package runtime binding for macOS")


GUI_PYZ_REQUIRED_MODULES = (
    "remote_ops_workspace.gui_terminal",
    "remote_ops_workspace.gui_processes",
    "remote_ops_workspace.gui_values",
    "remote_ops_workspace.terminal_output",
    "remote_ops_workspace.gui_workspace",
)
GUI_PYZ_ARCHIVE_PATHS = {
    "windows-x64": "build/native/windows/pyinstaller-dist/row-gui.exe",
    "windows-arm64": "build/native/windows/pyinstaller-dist/row-gui.exe",
    "macos-x64": (
        "build/native/macos/pyinstaller-dist/Remote Ops Workspace.app/"
        "Contents/MacOS/Remote Ops Workspace"
    ),
    "macos-arm64": (
        "build/native/macos/pyinstaller-dist/Remote Ops Workspace.app/"
        "Contents/MacOS/Remote Ops Workspace"
    ),
}
GUI_PYZ_CLI_ARCHIVE_PATHS = {
    "windows-x64": "build/native/windows/pyinstaller-dist/row.exe",
    "windows-arm64": "build/native/windows/pyinstaller-dist/row.exe",
    "windows-x86": "build/native/windows/pyinstaller-dist/row.exe",
    "linux-x86_64": "build/native/linux/pyinstaller-dist/row",
    "linux-aarch64": "build/native/linux/pyinstaller-dist/row",
}


def validate_gui_pyz_modules(archives, target):
    """Return a bounded result from archive_inventory records, without imports.

    A failed result must make native_pyinstaller_inventory_complete false.
    Ordinary modules use the recorded JSON PYZ entry [0, position, length].
    This verifies presence and entry shape, not compiled/source byte equality.
    """
    expected_path = GUI_PYZ_ARCHIVE_PATHS.get(target) if type(target) is str else None
    report = {
        "schema_version": 1,
        "status": "not-required" if expected_path is None else "failed",
        "scope": "Required GUI module presence and typed PYZ TOC entries; no compiled/source byte comparison",
        "role": None if expected_path is None else "gui",
        "path": expected_path,
        "artifact_sha256": None,
        "required_modules": [] if expected_path is None else list(GUI_PYZ_REQUIRED_MODULES),
        "observed_presence": {} if expected_path is None else dict.fromkeys(GUI_PYZ_REQUIRED_MODULES, False),
        "errors": [],
        "cli_observations": [],
    }
    if type(target) is not str or (target not in GUI_PYZ_ARCHIVE_PATHS and target not in GUI_PYZ_CLI_ARCHIVE_PATHS):
        report["status"] = "failed"
        report["errors"].append("unsupported-native-target")
        return report
    cli_path = GUI_PYZ_CLI_ARCHIVE_PATHS.get(target)
    if cli_path is not None and type(archives) is list:
        matching_cli = [
            row for row in archives
            if type(row) is dict and type(row.get("path")) is str
            and row["path"].replace("\\", "/") == cli_path
        ]
        if len(matching_cli) == 1:
            cli = matching_cli[0]
            cli_hash = cli.get("artifact_sha256")
            pyz = cli.get("pyz_toc")
            report["cli_observations"] = [{
                "role": "cli",
                "path": cli_path,
                "artifact_sha256": cli_hash.lower() if type(cli_hash) is str and len(cli_hash) == 64 and all(char in "0123456789abcdefABCDEF" for char in cli_hash) else None,
                "gui_modules_required": False,
                "observed_presence": {module: type(pyz) is dict and module in pyz for module in GUI_PYZ_REQUIRED_MODULES},
            }]
    if expected_path is None:
        return report
    if type(archives) is not list or any(type(row) is not dict for row in archives):
        report["errors"].append("archive-inventory-malformed")
        return report
    matching = [
        row
        for row in archives
        if type(row.get("path")) is str
        and row["path"].replace("\\", "/") == expected_path
    ]
    if len(matching) != 1:
        report["errors"].append("expected-gui-archive-not-unique")
        return report
    archive = matching[0]
    if "inventory_error" in archive:
        report["errors"].append("gui-archive-inventory-error")
    artifact_hash = archive.get("artifact_sha256")
    if (
        type(artifact_hash) is str
        and len(artifact_hash) == 64
        and all(char in "0123456789abcdefABCDEF" for char in artifact_hash)
    ):
        report["artifact_sha256"] = artifact_hash.lower()
    else:
        report["errors"].append("gui-artifact-sha256-malformed")
    toc = archive.get("toc")
    if (
        type(toc) is not list
        or not toc
        or any(type(entry) is not dict for entry in toc)
        or sum(entry.get("name") == "PYZ.pyz" for entry in toc) != 1
    ):
        report["errors"].append("gui-carchive-toc-malformed")
    pyz = archive.get("pyz_toc")
    if type(pyz) is not dict or not pyz:
        report["errors"].append("gui-pyz-toc-malformed")
        return report
    for module in GUI_PYZ_REQUIRED_MODULES:
        if module not in pyz:
            report["errors"].append("required-gui-module-missing:" + module)
            continue
        report["observed_presence"][module] = True
        entry = pyz[module]
        if (
            type(entry) is not list
            or len(entry) != 3
            or any(type(value) is not int for value in entry)
            or entry[0] != 0
            or entry[1] <= 0
            or entry[2] <= 0
        ):
            report["errors"].append("required-gui-pyz-entry-malformed:" + module)
    if not report["errors"]:
        report["status"] = "passed"
    return report


def main():
    parser = argparse.ArgumentParser(description=SCOPE)
    parser.add_argument("phase", choices=["bind", "finish"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--asset-dir", required=True)
    parser.add_argument("--native-build-outcome", default="not-run")
    parser.add_argument("--native-smoke-outcome", default="not-run")
    args = parser.parse_args()
    output = ROOT / "build/candidate-proof" / args.target
    output.mkdir(parents=True, exist_ok=True)
    observed = fingerprint()
    record = {
        "scope": SCOPE,
        "target": args.target,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": observed,
        "event_sha": os.environ.get("GITHUB_SHA"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_sha": os.environ.get("GITHUB_WORKFLOW_SHA"),
        "native_build_outcome": args.native_build_outcome,
        "native_smoke_outcome": args.native_smoke_outcome,
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "runner": {
            key: os.environ.get(key)
            for key in ["RUNNER_OS", "RUNNER_ARCH", "RUNNER_NAME", "ImageOS", "ImageVersion"]
        },
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }
    if observed["head"] != args.expected_sha:
        save(output / f"{args.phase}.json", record)
        raise RuntimeError("actual checkout HEAD differs from bound candidate SHA")
    if args.phase == "bind":
        if sys.version_info[:3] != (3, 14, 7) or sys.implementation.name != "cpython":
            raise RuntimeError("candidate builder must use CPython 3.14.7 exactly")
        if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], check=False).returncode:
            raise RuntimeError("candidate starts with changed tracked source")
        expected_bits = 32 if args.target == "windows-x86" else 64
        if struct.calcsize("P") * 8 != expected_bits:
            raise RuntimeError("candidate Python architecture differs from target")
        record["python"] = {
            "executable": sys.executable,
            "version": sys.version,
            "machine": platform.machine(),
            "platform": platform.platform(),
        }
        save(output / "bind.json", record)
        return 0
    before = json.loads((output / "bind.json").read_text(encoding="utf-8"))
    record["source_unchanged"] = all(
        observed[key] == before["source"][key] for key in ("head", "tree", "checkout_bytes_sha256")
    )
    record["assets"] = [
        {"path": str(path.relative_to(ROOT)), "sha256": digest(path), "size": path.stat().st_size}
        for path in sorted((ROOT / args.asset_dir).glob("*"))
        if path.is_file()
    ]
    package = importlib.util.find_spec("remote_ops_workspace")
    package_root = Path(package.origin).parent if package and package.origin else None
    record["installed_project_sources_match_checkout"] = package_root is not None and all(
        (package_root / path.relative_to(ROOT / "src/remote_ops_workspace")).is_file()
        and digest(path)
        == digest(package_root / path.relative_to(ROOT / "src/remote_ops_workspace"))
        for path in (ROOT / "src/remote_ops_workspace").rglob("*.py")
    )
    record["realized_distributions"] = sorted(
        [
            {
                "name": item.metadata["Name"],
                "version": item.version,
                "direct_url": item.read_text("direct_url.json"),
            }
            for item in importlib.metadata.distributions()
        ],
        key=lambda item: item["name"].lower(),
    )
    inspect = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "pip", "inspect", "--local"],
        capture_output=True,
        timeout=120,
        check=False,
    )
    (output / "pip-inspect.json").write_bytes(inspect.stdout)
    (output / "pip-inspect.stderr.log").write_bytes(inspect.stderr)
    record["pip_inspect_returncode"] = inspect.returncode
    record["pip_inspect_sha256"] = digest(output / "pip-inspect.json")
    record["pip_inspect_stderr_sha256"] = digest(output / "pip-inspect.stderr.log")
    try:
        inspect_record = json.loads(inspect.stdout.decode("utf-8"))
        if not isinstance(inspect_record, dict) or not isinstance(inspect_record.get("installed"), list):
            raise ValueError("pip inspect lacks its installed distribution inventory")
        record["pip_inspect_json_valid"] = True
    except (UnicodeError, ValueError) as exc:
        record["pip_inspect_json_valid"] = False
        record["pip_inspect_json_error"] = str(exc)
    archives = []
    for stage in (ROOT / "build/native").glob("*/pyinstaller-dist"):
        for path in stage.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name in ("row", "row.exe", "row-gui.exe", "Remote Ops Workspace"):
                try:
                    archives.append(archive_inventory(path))
                except Exception as exc:
                    archives.append(
                        {
                            "path": str(path.relative_to(ROOT)),
                            "artifact_sha256": digest(path),
                            "inventory_error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    expected_archives = (
        {"row.exe"}
        if args.target == "windows-x86"
        else {"row.exe", "row-gui.exe"}
        if args.target.startswith("windows-")
        else {"Remote Ops Workspace"}
        if args.target.startswith("macos-")
        else {"row"}
    )
    observed_archives = {
        Path(item["path"]).name
        for item in archives
        if "inventory_error" not in item and item.get("toc")
    }
    record["expected_pyinstaller_archives"] = sorted(expected_archives)
    record["required_gui_pyz_modules"] = validate_gui_pyz_modules(archives, args.target)
    record["native_pyinstaller_inventory_complete"] = (
        args.native_build_outcome == "success"
        and expected_archives.issubset(observed_archives)
        and not any("inventory_error" in item for item in archives)
        and record["required_gui_pyz_modules"]["status"] in ("passed", "not-required")
    )
    record["native_pyinstaller_inventory_scope"] = (
        "Expected executable CArchive parsing only; excludes external/installed runtime closure and independent runtime/license approval"
    )
    record["native_executable_byte_binding"] = {"status": "not-bound", "scope": "Executable bytes observed immediately before smoke launch, excludes adversarial races and external runtime closure"}
    binding_error = None
    record["native_packaged_launchers"] = []
    if args.target in ("linux-x86_64", "linux-aarch64"):
        launcher_path = ROOT / "build/native/linux/Remote_Ops_Workspace.AppDir/AppRun"
        if launcher_path.is_file() and not launcher_path.is_symlink():
            record["native_packaged_launchers"] = [{"path": launcher_path.relative_to(ROOT).as_posix(), "sha256": digest(launcher_path)}]
    binding_supported = args.target.startswith("windows-") or args.target in ("macos-x64", "macos-arm64", "linux-x86_64", "linux-aarch64")
    if binding_supported:
        binding_path = ROOT / "build/native-smoke" / args.target / "candidate-runtime-byte-binding.json"
        if binding_path.is_file():
            record["native_executable_byte_binding"].update(report_path=str(binding_path.relative_to(ROOT)).replace("\\", "/"), report_sha256=digest(binding_path))
            try:
                binding_report = json.loads(binding_path.read_text(encoding="utf-8"))
                if args.target.startswith("windows-"):
                    validate_windows_byte_binding(binding_report, archives, args.target)
                else:
                    validate_posix_byte_binding(binding_report, archives, args.target, record["assets"], record["native_packaged_launchers"])
                if args.native_smoke_outcome != "success":
                    raise ValueError("native smoke did not succeed")
                record["native_executable_byte_binding"]["status"] = "bound"
            except (ValueError, TypeError, KeyError) as exc:
                binding_error = str(exc)
                record["native_executable_byte_binding"].update(status="not-bound", error=binding_error)
        else:
            binding_error = "candidate executable byte binding report is missing"

    save(output / "pyinstaller-archives.json", archives)
    record["pyinstaller_archive_inventory_sha256"] = digest(output / "pyinstaller-archives.json")
    record["staged_license_materials_not_asserted_installed"] = [
        {"path": str(path.relative_to(ROOT)), "sha256": digest(path), "size": path.stat().st_size}
        for path in sorted((ROOT / "build/native").rglob("*"))
        if path.is_file()
        and not path.is_symlink()
        and any(token in path.name.lower() for token in ("license", "notice", "relinking"))
    ]
    record["gui_contract"] = (
        "frozen native GUI startup/profile-selection/paint"
        if args.target in ("windows-x64", "windows-arm64", "macos-x64", "macos-arm64")
        else "not included in the current native artifact contract; CLI proof only"
    )
    record["previous_native_upgrade_and_rollback"] = (
        "pending: existing script upgrade labels reinstall the same candidate; no previous native artifact fixture verified"
    )
    record["macos_signing_trust"] = (
        "ad-hoc only; no publisher identity, notarization or production trust"
        if args.target.startswith("macos-")
        else "not asserted"
    )
    save(output / "finish.json", record)
    if inspect.returncode != 0 or not record["pip_inspect_json_valid"]:
        raise RuntimeError("pip inspect failed; realized runtime inventory is incomplete")
    if args.native_build_outcome == "success" and not record["native_pyinstaller_inventory_complete"]:
        raise RuntimeError(
            "successful native build has missing or erroneous PyInstaller inventories"
        )
    if binding_supported and args.native_smoke_outcome == "success" and binding_error:
        raise RuntimeError(binding_error)
    if not record["installed_project_sources_match_checkout"]:
        raise RuntimeError("installed project source bytes differ from candidate checkout")
    if not record["source_unchanged"]:
        raise RuntimeError("tracked checkout bytes changed while building or validating candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
