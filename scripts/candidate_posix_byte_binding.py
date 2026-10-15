"""Record hashes immediately before candidate POSIX smoke probes.

This is candidate-produced evidence, excluding hostile file replacement races,
external runtime closure, publisher trust and independent approval. It launches
no application: shell smoke functions call check before their native probes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPORT_NAME = "candidate-runtime-byte-binding.json"
APPIMAGE_LAUNCHER = "build/native/linux/Remote_Ops_Workspace.AppDir/AppRun"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def target_contract(target):
    if target in ("macos-x64", "macos-arm64"):
        original = "build/native/macos/pyinstaller-dist/Remote Ops Workspace.app/Contents/MacOS/Remote Ops Workspace"
        paths = {
            f"{kind}/Remote Ops Workspace.app/Contents/MacOS/Remote Ops Workspace": "gui"
            for kind in ("dmg", "pkg")
        }
        probes = {
            (path, phase, probe)
            for path in paths
            for phase, probe in (
                ("install", "platforms"),
                ("install", "gui"),
                ("reinstall", "platforms"),
            )
        }
        return {"gui": original}, paths, probes
    if target in ("linux-x86_64", "linux-aarch64"):
        paths = {f"{kind}/usr/bin/row": "cli" for kind in ("deb", "rpm", "appimage")}
        probes = {
            (path, phase, probe)
            for path in paths
            for phase in ("install", "reinstall")
            for probe in ("version", "platforms")
        }
        return {"cli": "build/native/linux/pyinstaller-dist/row"}, paths, probes
    raise ValueError("unsupported POSIX candidate target")


def save(path, value):
    """Replace one report atomically; each check is a sequential smoke step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".binding-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def regular_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("candidate binding requires a regular non-symlink file")


def initialize(root, target, report_path, appimage=None):
    from candidate_native_proof import archive_inventory

    outputs, paths, probes = target_contract(target)
    expected = []
    for role, relative in outputs.items():
        path = root / relative
        regular_file(path)
        inventory = archive_inventory(path)
        if not inventory.get("toc") or inventory.get("artifact_sha256") != digest(path):
            raise ValueError("original PyInstaller executable inventory is incomplete")
        expected.append({"role": role, "path": relative, "sha256": inventory["artifact_sha256"]})
    packages = []
    if target.startswith("linux-"):
        if appimage is None:
            raise ValueError("candidate AppImage build artifact is required")
        regular_file(appimage)
        relative = appimage.resolve().relative_to(root.resolve()).as_posix()
        if not re.fullmatch(
            r"remote-ops-workspace-v[0-9]+\.[0-9]+\.[0-9]+-" + re.escape(target) + r"\.AppImage",
            appimage.name,
        ):
            raise ValueError("candidate AppImage artifact belongs to another target")
        packages.append({"role": "appimage-runtime", "path": relative, "sha256": digest(appimage)})
        launcher = root / APPIMAGE_LAUNCHER
        regular_file(launcher)
        packages.append(
            {"role": "appimage-launcher", "path": APPIMAGE_LAUNCHER, "sha256": digest(launcher)}
        )
    report = {
        "schema_version": 1,
        "target": target,
        "status": "pending",
        "smoke_complete": False,
        "required_paths": sorted(paths),
        "expected_executables": expected,
        "required_probes": [
            dict(path=path, phase=phase, probe=probe) for path, phase, probe in sorted(probes)
        ],
        "observations": [],
        "expected_packages": packages,
        "package_observations": [],
    }
    save(report_path, report)
    return report


def load(report_path, target):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    outputs, paths, probes = target_contract(target)
    if not isinstance(report, dict) or (
        type(report.get("schema_version")) is not int
        or report["schema_version"] != 1
        or report.get("target") != target
        or report.get("smoke_complete") is not False
        or report.get("status") not in ("pending", "mismatch")
        or set(report.get("required_paths", [])) != set(paths)
        or {(row["path"], row["phase"], row["probe"]) for row in report.get("required_probes", [])}
        != probes
    ):
        raise ValueError("candidate binding report target or probe contract changed")
    expected = report.get("expected_executables", [])
    if len(expected) != len(outputs) or {row.get("role") for row in expected} != set(outputs):
        raise ValueError("candidate binding expected executable roles changed")
    for row in expected:
        if row.get("path") != outputs[row["role"]] or not re.fullmatch(
            r"[0-9a-f]{64}", row.get("sha256", "")
        ):
            raise ValueError("candidate binding expected executable identity changed")
    return report


def check(report_path, target, path, public_path, phase, probe, package=False):
    report = load(report_path, target)
    _, paths, probes = target_contract(target)
    if package:
        package_probe = public_path == "appimage/runtime.AppImage" and probe == "extract"
        launcher_probe = public_path == "appimage/AppRun" and probe in ("version", "platforms")
        if (
            not target.startswith("linux-")
            or phase not in ("install", "reinstall")
            or not (package_probe or launcher_probe)
        ):
            raise ValueError("unexpected candidate package probe")
        rows = report.get("expected_packages", [])
        roles = {row.get("role") for row in rows}
        if (
            len(rows) != 2
            or roles != {"appimage-runtime", "appimage-launcher"}
            or any(not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")) for row in rows)
        ):
            raise ValueError("candidate expected AppImage identity is incomplete")
        role = "appimage-runtime" if package_probe else "appimage-launcher"
        expected = next(row["sha256"] for row in rows if row["role"] == role)
        observations = report["package_observations"]
    else:
        if (public_path, phase, probe) not in probes:
            raise ValueError("unexpected candidate executable probe")
        role = paths[public_path]
        expected = next(
            row["sha256"] for row in report["expected_executables"] if row["role"] == role
        )
        observations = report["observations"]
    observed = None
    try:
        regular_file(path)
        observed = digest(path)
    except (OSError, ValueError):
        pass
    matched = observed == expected
    observations.append(
        {
            "path": public_path,
            "role": role,
            "phase": phase,
            "probe": probe,
            "expected_sha256": expected,
            "observed_sha256": observed,
            "matched": matched,
        }
    )
    if not matched:
        report["status"] = "mismatch"
    save(report_path, report)
    if not matched:
        raise ValueError("candidate executable byte mismatch before probe")


def complete(report_path, target):
    report = load(report_path, target)
    _, _, required = target_contract(target)
    observations = report["observations"]
    if report["status"] != "pending" or any(row.get("matched") is not True for row in observations):
        raise ValueError("candidate binding contains a failed executable check")
    if {(row["path"], row["phase"], row["probe"]) for row in observations} != required:
        raise ValueError("candidate binding did not observe every required probe")
    if target.startswith("linux-"):
        packages = report["package_observations"]
        required_packages = {
            ("appimage/runtime.AppImage", stage, "extract") for stage in ("install", "reinstall")
        }
        required_packages.update(
            {
                ("appimage/AppRun", stage, probe)
                for stage in ("install", "reinstall")
                for probe in ("version", "platforms")
            }
        )
        if (
            any(row.get("matched") is not True for row in packages)
            or {(row["path"], row["phase"], row["probe"]) for row in packages} != required_packages
        ):
            raise ValueError("candidate AppImage extraction bytes were not bound")
    report.update(status="bound", smoke_complete=True)
    save(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("init", "check", "complete"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--appimage", type=Path)
    parser.add_argument("--path", type=Path)
    parser.add_argument("--public-path")
    parser.add_argument("--stage", choices=("install", "reinstall"))
    parser.add_argument("--probe", choices=("version", "platforms", "gui", "extract"))
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()
    try:
        if args.phase == "init":
            initialize(args.root.resolve(), args.target, args.report, args.appimage)
        elif args.phase == "check":
            if (
                args.path is None
                or args.public_path is None
                or args.stage is None
                or args.probe is None
            ):
                raise ValueError("candidate check needs a path, stage and probe")
            check(
                args.report,
                args.target,
                args.path,
                args.public_path,
                args.stage,
                args.probe,
                args.package,
            )
        else:
            complete(args.report, args.target)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Never print an actual installed/private path, file contents or traceback.
        reason = (
            "byte mismatch before probe"
            if str(exc) == "candidate executable byte mismatch before probe"
            else type(exc).__name__
        )
        print("candidate executable binding failed: " + reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
