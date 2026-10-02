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
    record["native_pyinstaller_inventory_complete"] = (
        args.native_build_outcome == "success"
        and expected_archives.issubset(observed_archives)
        and not any("inventory_error" in item for item in archives)
    )
    record["native_pyinstaller_inventory_scope"] = (
        "Expected executable CArchive parsing only; excludes external/installed runtime closure and independent runtime/license approval"
    )
    record["native_executable_byte_binding"] = {"status": "not-bound", "scope": "Executable bytes observed immediately before smoke launch, excludes adversarial races and external runtime closure"}
    binding_error = None
    if args.target.startswith("windows-"):
        binding_path = ROOT / "build/native-smoke" / args.target / "candidate-runtime-byte-binding.json"
        if binding_path.is_file():
            record["native_executable_byte_binding"].update(report_path=str(binding_path.relative_to(ROOT)).replace("\\", "/"), report_sha256=digest(binding_path))
            try:
                validate_windows_byte_binding(json.loads(binding_path.read_text(encoding="utf-8")), archives, args.target)
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
    if args.target.startswith("windows-") and args.native_smoke_outcome == "success" and binding_error:
        raise RuntimeError(binding_error)
    if not record["installed_project_sources_match_checkout"]:
        raise RuntimeError("installed project source bytes differ from candidate checkout")
    if not record["source_unchanged"]:
        raise RuntimeError("tracked checkout bytes changed while building or validating candidate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
