from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_PATH = ROOT / "configs" / "release_toolchain.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9_.!+-]*)$")


def main() -> int:
    errors: list[str] = []
    toolchain = load_toolchain(errors)
    if toolchain:
        errors.extend(check_python_constraints(toolchain))
        errors.extend(check_workflow(toolchain))
        errors.extend(check_release_helper(toolchain))
        errors.extend(check_linux_appimagetool_script())
    if errors:
        for error in errors:
            print(f"release toolchain: {error}", file=sys.stderr)
        return 1
    print("release toolchain reproducibility passed")
    return 0


def load_toolchain(errors: list[str]) -> dict[str, object] | None:
    try:
        data = json.loads(TOOLCHAIN_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing {repo_path(TOOLCHAIN_PATH)}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{repo_path(TOOLCHAIN_PATH)} is not valid JSON: {exc}")
        return None
    if data.get("schema_version") != 1:
        errors.append("configs/release_toolchain.json schema_version must be 1")
    return data


def check_python_constraints(toolchain: dict[str, object]) -> list[str]:
    errors: list[str] = []
    python = required_mapping(toolchain, "python", errors)
    package_rows = required_list(toolchain, "python_packages", errors)
    if not python or not package_rows:
        return errors

    constraints_file = str(python.get("constraints_file", ""))
    if constraints_file != "requirements-release.txt":
        errors.append("python.constraints_file must be requirements-release.txt")
        return errors

    expected = {
        normalize_package_name(str(row.get("name", ""))): str(row.get("version", ""))
        for row in package_rows
        if isinstance(row, dict)
    }
    actual = parse_requirement_pins(ROOT / constraints_file, errors)
    if actual != expected:
        errors.append(
            "requirements-release.txt pins must match configs/release_toolchain.json "
            f"(expected {expected}, got {actual})"
        )
    return errors


def check_workflow(toolchain: dict[str, object]) -> list[str]:
    errors: list[str] = []
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    python = required_mapping(toolchain, "python", errors)
    if not python:
        return errors

    python_version = str(python.get("version", ""))
    source_date_epoch = str(python.get("source_date_epoch", ""))
    constraints_file = str(python.get("constraints_file", ""))
    if f'python-version: "{python_version}"' not in workflow:
        errors.append(f"release workflow must use Python {python_version}")
    if f'SOURCE_DATE_EPOCH: "{source_date_epoch}"' not in workflow:
        errors.append(f"release workflow must set SOURCE_DATE_EPOCH={source_date_epoch}")
    if f"--constraint {constraints_file}" not in workflow:
        errors.append(f"release workflow must install Python release deps with --constraint {constraints_file}")
    if "python -m pip install --upgrade" in workflow:
        errors.append("release workflow must not use unbounded pip install --upgrade")

    windows_tools = {
        str(row.get("name")): str(row.get("version"))
        for row in required_list(required_mapping(toolchain, "native_toolchains", errors), "windows", errors)
        if isinstance(row, dict)
    }
    inno_version = windows_tools.get("innosetup")
    wix_version = windows_tools.get("wix")
    if inno_version and f"choco install innosetup --version={inno_version}" not in workflow:
        errors.append(f"release workflow must pin Inno Setup to {inno_version}")
    if wix_version and f"dotnet tool install --global wix --version {wix_version}" not in workflow:
        errors.append(f"release workflow must pin WiX to {wix_version}")
    return errors


def check_release_helper(toolchain: dict[str, object]) -> list[str]:
    errors: list[str] = []
    helper = (ROOT / "scripts" / "make_release.py").read_text(encoding="utf-8")
    python = required_mapping(toolchain, "python", errors)
    if not python:
        return errors
    source_date_epoch = str(python.get("source_date_epoch", ""))
    if f"DEFAULT_SOURCE_DATE_EPOCH = {int(source_date_epoch):_}" not in helper:
        errors.append(f"make_release.py default SOURCE_DATE_EPOCH must be {source_date_epoch}")
    if "release_toolchain_metadata()" not in helper:
        errors.append("make_release.py manifest must include release_toolchain_metadata()")
    if '"requirements-release.txt"' not in helper:
        errors.append("source release bundles must include requirements-release.txt")
    return errors


def check_linux_appimagetool_script() -> list[str]:
    script = (ROOT / "scripts" / "make_linux_native.sh").read_text(encoding="utf-8")
    errors: list[str] = []
    if "https://github.com/AppImage/appimagetool/releases/download/continuous" not in script:
        errors.append("make_linux_native.sh must use the maintained AppImage/appimagetool upstream URL")
    if "APPIMAGETOOL_SHA256" not in script:
        errors.append("make_linux_native.sh must support APPIMAGETOOL_SHA256 verification")
    return errors


def parse_requirement_pins(path: Path, errors: list[str]) -> dict[str, str]:
    pins: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        errors.append(f"missing {repo_path(path)}")
        return pins
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_RE.fullmatch(line)
        if not match:
            errors.append(f"{repo_path(path)}:{number} must be an exact NAME==VERSION pin")
            continue
        name, version = match.groups()
        pins[normalize_package_name(name)] = version
    return pins


def required_mapping(parent: dict[str, object], key: str, errors: list[str]) -> dict[str, object]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"configs/release_toolchain.json {key} must be an object")
        return {}
    return value


def required_list(parent: dict[str, object], key: str, errors: list[str]) -> list[object]:
    value = parent.get(key)
    if not isinstance(value, list):
        errors.append(f"configs/release_toolchain.json {key} must be a list")
        return []
    return value


def normalize_package_name(name: str) -> str:
    return name.lower().replace("_", "-")


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
