from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"\d+\.\d+")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, evidence = run_frozen_executable_smoke(
        expected_python=args.expected_python,
        out_dir=args.out_dir,
        timeout_seconds=args.timeout_seconds,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if errors:
        for error in errors:
            print(f"Python frozen executable smoke: {error}", file=sys.stderr)
        return 1
    print(
        "Python frozen executable smoke passed: "
        f"Python {evidence['python']['major_minor']}, "
        f"PyInstaller {evidence['pyinstaller']['version']}, "
        f"sha256={evidence['executable']['sha256']}"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build the package-aware ROW CLI as a real PyInstaller one-file executable, "
            "launch it, and record reproducible runtime evidence."
        )
    )
    parser.add_argument(
        "--expected-python",
        required=True,
        help="required interpreter major.minor, for example 3.15",
    )
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    return parser.parse_args(argv)


def run_frozen_executable_smoke(
    *,
    expected_python: str,
    out_dir: Path,
    timeout_seconds: int,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    actual_python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if not VERSION_RE.fullmatch(expected_python):
        errors.append("--expected-python must look like major.minor")
    if actual_python != expected_python:
        errors.append(
            f"interpreter mismatch: expected Python {expected_python}, got {actual_python}"
        )
    if timeout_seconds < 30:
        errors.append("--timeout-seconds must be at least 30")

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "passed": False,
        "python": {
            "expected_major_minor": expected_python,
            "major_minor": actual_python,
            "version": sys.version,
            "executable": str(Path(sys.executable).resolve()),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
        },
        "pyinstaller": {},
        "executable": {},
        "smokes": {},
        "errors": errors,
    }
    if errors:
        return errors, evidence

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    launcher = out_dir / "row_frozen_smoke_launcher.py"
    dist_dir = out_dir / "dist"
    work_dir = out_dir / "work"
    spec_dir = out_dir / "spec"
    for managed in (dist_dir, work_dir, spec_dir):
        reset_managed_directory(managed, root=out_dir)
    launcher.write_text(
        "from remote_ops_workspace.cli import main\n\nraise SystemExit(main())\n",
        encoding="utf-8",
    )

    pyinstaller_version = run_command(
        [sys.executable, "-m", "PyInstaller", "--version"],
        timeout_seconds=60,
    )
    evidence["pyinstaller"] = command_evidence(pyinstaller_version)
    if pyinstaller_version.returncode != 0:
        errors.append("PyInstaller version probe failed")
        evidence["errors"] = errors
        return errors, evidence
    version_text = pyinstaller_version.stdout.strip()
    if not version_text:
        errors.append("PyInstaller version probe returned empty output")
        evidence["errors"] = errors
        return errors, evidence
    evidence["pyinstaller"]["version"] = version_text

    name = "row-python-frozen-smoke"
    build_command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--name",
        name,
        "--console",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--collect-submodules",
        "remote_ops_workspace",
        "--collect-data",
        "remote_ops_workspace",
        "--add-data",
        f"{ROOT / 'configs'}{os.pathsep}remote_ops_workspace/configs",
        "--add-data",
        f"{ROOT / 'apps' / 'web'}{os.pathsep}remote_ops_workspace/web",
        "--copy-metadata",
        "remote-ops-workspace",
        "--exclude-module",
        "PyQt6",
        "--exclude-module",
        "remote_ops_workspace.gui",
        "--exclude-module",
        "remote_ops_workspace.gui_designs",
        "--exclude-module",
        "remote_ops_workspace.gui_editors",
        str(launcher),
    ]
    build = run_command(build_command, timeout_seconds=timeout_seconds, cwd=ROOT)
    evidence["build"] = command_evidence(build)
    if build.returncode != 0:
        errors.append(f"PyInstaller one-file build failed with exit code {build.returncode}")

    executable = dist_dir / f"{name}{'.exe' if os.name == 'nt' else ''}"
    if not executable.is_file():
        errors.append(f"PyInstaller did not create the expected executable: {executable}")
    if errors:
        evidence["errors"] = errors
        return errors, evidence

    evidence["executable"] = {
        "name": executable.name,
        "size": executable.stat().st_size,
        "sha256": sha256_file(executable),
    }
    if executable.stat().st_size <= 0:
        errors.append("frozen executable is empty")

    version_smoke = run_command(
        [str(executable), "--version"],
        timeout_seconds=min(timeout_seconds, 120),
    )
    platforms_smoke = run_command(
        [str(executable), "platforms", "--json"],
        timeout_seconds=min(timeout_seconds, 120),
    )
    evidence["smokes"] = {
        "version": command_evidence(version_smoke),
        "platforms_json": command_evidence(platforms_smoke),
    }
    errors.extend(
        validate_frozen_smokes(
            version_smoke=version_smoke,
            platforms_smoke=platforms_smoke,
        )
    )
    evidence["passed"] = not errors
    evidence["errors"] = errors
    return errors, evidence


def validate_frozen_smokes(
    *,
    version_smoke: subprocess.CompletedProcess[str],
    platforms_smoke: subprocess.CompletedProcess[str],
) -> list[str]:
    errors: list[str] = []
    if version_smoke.returncode != 0:
        errors.append(f"frozen --version smoke exited {version_smoke.returncode}")
    elif not version_smoke.stdout.strip().startswith("remote-ops-workspace "):
        errors.append("frozen --version smoke did not report the ROW package version")
    if platforms_smoke.returncode != 0:
        errors.append(f"frozen platforms --json smoke exited {platforms_smoke.returncode}")
    else:
        try:
            payload = json.loads(platforms_smoke.stdout)
        except json.JSONDecodeError:
            errors.append("frozen platforms --json smoke returned invalid JSON")
        else:
            if not isinstance(payload, dict) or not payload:
                errors.append("frozen platforms --json smoke returned an empty or non-object payload")
    return errors


def reset_managed_directory(path: Path, *, root: Path) -> None:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    if resolved == root.resolve():
        raise ValueError("refusing to reset the evidence root")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def run_command(
    command: list[str],
    *,
    timeout_seconds: int,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=str(exc.stdout or ""),
            stderr=f"timed out after {timeout_seconds} seconds\n{exc.stderr or ''}",
        )


def command_evidence(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return {
        "command": [str(part) for part in result.args],
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
