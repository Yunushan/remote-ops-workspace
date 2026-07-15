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
        errors.extend(check_windows_native_smoke())
        errors.extend(check_native_release_tag_guards())
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

    profiles = required_list(python, "compatibility_profiles", errors)
    names: set[str] = set()
    for row in profiles:
        if not isinstance(row, dict):
            errors.append("python.compatibility_profiles rows must be objects")
            continue
        name = str(row.get("name", ""))
        profile_file = str(row.get("constraints_file", ""))
        overrides = row.get("package_overrides")
        targets = row.get("targets")
        if not name or name in names:
            errors.append("python.compatibility_profiles names must be non-empty and unique")
            continue
        names.add(name)
        if not profile_file or not isinstance(overrides, dict):
            errors.append(f"compatibility profile {name} must declare constraints_file and package_overrides")
            continue
        if not isinstance(targets, list) or not targets or not all(isinstance(item, str) for item in targets):
            errors.append(f"compatibility profile {name} must declare non-empty string targets")
        profile_expected = dict(expected)
        for package, version in overrides.items():
            normalized = normalize_package_name(str(package))
            if normalized not in expected:
                errors.append(f"compatibility profile {name} overrides unknown package {package}")
                continue
            profile_expected[normalized] = str(version)
        profile_actual = parse_requirement_pins(ROOT / profile_file, errors)
        if profile_actual != profile_expected:
            errors.append(
                f"{profile_file} pins must match compatibility profile {name} "
                f"(expected {profile_expected}, got {profile_actual})"
            )
    return errors


def check_workflow(
    toolchain: dict[str, object], workflow_text: str | None = None
) -> list[str]:
    errors: list[str] = []
    workflow = workflow_text if workflow_text is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
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

    profiles = {
        str(row.get("name")): row
        for row in required_list(python, "compatibility_profiles", errors)
        if isinstance(row, dict)
    }
    compatibility = profiles.get("legacy-wheel-architectures", {})
    compatibility_file = str(compatibility.get("constraints_file", ""))
    if set(compatibility.get("targets", [])) != {"windows-x86", "macos-x64"}:
        errors.append(
            "legacy-wheel-architectures profile must target exactly windows-x86 and macos-x64"
        )
    if compatibility.get("package_overrides") != {"cryptography": "48.0.1"}:
        errors.append(
            "legacy-wheel-architectures profile must pin cryptography 48.0.1"
        )
    for snippet, label in {
        f"--only-binary=cryptography --constraint {constraints_file}": (
            "binary-only modern cryptography installs"
        ),
        f"--only-binary=cryptography --constraint {compatibility_file}": (
            "binary-only compatibility cryptography installs"
        ),
        'if ("${{ matrix.arch }}" -eq "x86")': "explicit Windows x86 compatibility branch",
        'if [[ "${{ matrix.arch }}" == "x64" ]]': "explicit Intel macOS compatibility branch",
        "$ExpectedCryptography = \"48.0.1\"": "Windows compatibility version assertion",
        'expected_cryptography="48.0.1"': "macOS compatibility version assertion",
        "backend.openssl_version_text()": "cryptography/OpenSSL runtime import smoke",
    }.items():
        if snippet not in workflow:
            errors.append(f"release workflow missing {label}: {snippet}")

    windows_tool_rows = {
        str(row.get("name")): row
        for row in required_list(required_mapping(toolchain, "native_toolchains", errors), "windows", errors)
        if isinstance(row, dict)
    }
    inno_version = str(windows_tool_rows.get("innosetup", {}).get("version", ""))
    wix_version = str(windows_tool_rows.get("wix", {}).get("version", ""))
    if inno_version and f"choco install innosetup --version={inno_version}" not in workflow:
        errors.append(f"release workflow must pin Inno Setup to {inno_version}")
    if wix_version and f"dotnet tool install --global wix --version {wix_version}" not in workflow:
        errors.append(f"release workflow must pin WiX to {wix_version}")

    openssl = windows_tool_rows.get("openssl", {})
    openssl_version = str(openssl.get("version", ""))
    vcpkg_commit = str(openssl.get("vcpkg_commit", ""))
    triplet = str(openssl.get("triplet", ""))
    if openssl.get("targets") != ["windows-arm64"] or openssl.get("linkage") != "static":
        errors.append("Windows OpenSSL toolchain must be static and scoped only to windows-arm64")
    for snippet, label in {
        f'$VcpkgCommit = "{vcpkg_commit}"': "pinned Windows ARM64 vcpkg commit",
        "git -C $VcpkgRoot checkout --detach $VcpkgCommit": "detached pinned vcpkg checkout",
        f'& $Vcpkg install "openssl:{triplet}" --clean-after-build': (
            f"OpenSSL {openssl_version} ARM64 vcpkg install"
        ),
        f'installed\\{triplet}': "architecture-correct ARM64 OpenSSL root",
        '$env:OPENSSL_DIR = $OpenSslRoot': "explicit OpenSSL source-build root",
        '$env:OPENSSL_STATIC = "1"': "static OpenSSL linkage policy",
        '$env:OPENSSL_NO_VENDOR = "1"': "no untracked vendored OpenSSL fallback",
        f"python -m pip install --constraint {constraints_file} pip setuptools wheel maturin cffi pycparser": (
            "pinned Windows ARM64 cryptography build dependencies"
        ),
        f"--no-cache-dir --no-build-isolation --no-binary=cryptography --constraint {constraints_file}": (
            "deterministic Windows ARM64 cryptography source build"
        ),
        f'$ExpectedOpenSsl = "OpenSSL {openssl_version}"': "expected ARM64 OpenSSL runtime version",
        "actual_openssl.startswith('$ExpectedOpenSsl')": "ARM64 OpenSSL runtime version assertion",
    }.items():
        if snippet not in workflow:
            errors.append(f"release workflow missing {label}: {snippet}")
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
    for row in required_list(python, "compatibility_profiles", errors):
        if not isinstance(row, dict):
            continue
        constraints_file = str(row.get("constraints_file", ""))
        if constraints_file and f'"{constraints_file}"' not in helper:
            errors.append(f"source release bundles must include {constraints_file}")
    return errors


def check_linux_appimagetool_script() -> list[str]:
    script = (ROOT / "scripts" / "make_linux_native.sh").read_text(encoding="utf-8")
    errors: list[str] = []
    if "https://github.com/AppImage/appimagetool/releases/download/continuous" not in script:
        errors.append("make_linux_native.sh must use the maintained AppImage/appimagetool upstream URL")
    if "APPIMAGETOOL_SHA256" not in script:
        errors.append("make_linux_native.sh must support APPIMAGETOOL_SHA256 verification")
    return errors


def check_windows_native_smoke(script_text: str | None = None) -> list[str]:
    script = (
        script_text
        if script_text is not None
        else (ROOT / "scripts" / "smoke_windows_native.ps1").read_text(encoding="utf-8")
    )
    errors: list[str] = []
    for snippet, label in {
        "function Test-RowVault": "packaged vault smoke helper",
        "vault init": "packaged vault initialization smoke",
        "vault status --json": "packaged vault status smoke",
        "$Status.backend_available": "packaged cryptography backend assertion",
        "Test-RowVault $PortableRow": "portable ZIP vault smoke",
        "Test-RowVault $ExeRow": "installed EXE vault smoke",
        "Test-RowVault $MsiRow": "installed MSI vault smoke",
    }.items():
        if snippet not in script:
            errors.append(f"smoke_windows_native.ps1 missing {label}: {snippet}")
    return errors


def check_native_release_tag_guards() -> list[str]:
    errors: list[str] = []
    scripts = {
        "scripts/make_release.py": ("RELEASE_TAG", "GITHUB_REF_TYPE", 'ref_name.startswith("v")'),
        "scripts/make_windows_native.ps1": ("$env:RELEASE_TAG", "$env:GITHUB_REF_TYPE", '.StartsWith("v")'),
        "scripts/make_macos_native.sh": ("${RELEASE_TAG:-}", "${GITHUB_REF_TYPE:-}", '"${GITHUB_REF_NAME}" == v*'),
    }
    for relative, snippets in scripts.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                errors.append(
                    f"{relative} missing workflow-dispatch-safe release tag guard: {snippet}"
                )
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
