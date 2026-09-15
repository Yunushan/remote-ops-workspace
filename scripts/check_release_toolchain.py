from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_PATH = ROOT / "configs" / "release_toolchain.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
PIN_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9_.!+-]*)$")
APPIMAGETOOL_VERSION = "1.9.1"
APPIMAGETOOL_SHA256 = {
    "x86_64": "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
    "aarch64": "f0837e7448a0c1e4e650a93bb3e85802546e60654ef287576f46c71c126a9158",
    "i686": "7ad9ff47c203aae0149b18f6df9e3018b2e2f470ea644a0413e3ded39e9e3bdb",
    "armhf": "42b61cba5495d8aaf418a5c9a015a49b85ad92efabcbd3c341f1540440e4e23d",
}
APPIMAGE_RUNTIME_VERSION = "20251108"
APPIMAGE_RUNTIME_SHA256 = {
    "x86_64": "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
    "aarch64": "00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444",
    "i686": "e72ea0b140a0a16e680713238a6f30aad278b62c4ca17919c554864124515498",
    "armhf": "e9060d37577b8a29914ec12d8740add24e19ff29012fb1fa0f60daf62db0688d",
}


def main() -> int:
    errors: list[str] = []
    toolchain = load_toolchain(errors)
    if toolchain:
        errors.extend(check_python_constraints(toolchain))
        errors.extend(check_pyqt6_support(toolchain))
        errors.extend(check_python_build_backend(toolchain))
        errors.extend(check_workflow(toolchain))
        errors.extend(check_release_helper(toolchain))
        errors.extend(check_linux_appimagetool_script(toolchain))
        errors.extend(check_windows_native_smoke())
        errors.extend(check_native_release_tag_guards())
    if errors:
        for error in errors:
            print(f"release toolchain: {error}", file=sys.stderr)
        return 1
    print("release toolchain pinning policy passed")
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
        excluded = row.get("excluded_packages", [])
        targets = row.get("targets")
        if not name or name in names:
            errors.append("python.compatibility_profiles names must be non-empty and unique")
            continue
        names.add(name)
        if not profile_file or not isinstance(overrides, dict):
            errors.append(f"compatibility profile {name} must declare constraints_file and package_overrides")
            continue
        if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
            errors.append(f"compatibility profile {name} excluded_packages must be a string list")
            continue
        if not isinstance(targets, list) or not targets or not all(isinstance(item, str) for item in targets):
            errors.append(f"compatibility profile {name} must declare non-empty string targets")
        normalized_excluded = {
            normalize_package_name(package)
            for package in excluded
        }
        for package in normalized_excluded:
            if package not in expected:
                errors.append(f"compatibility profile {name} excludes unknown package {package}")
        profile_expected = {
            package: version
            for package, version in expected.items()
            if package not in normalized_excluded
        }
        for package, version in overrides.items():
            normalized = normalize_package_name(str(package))
            if normalized not in expected:
                errors.append(f"compatibility profile {name} overrides unknown package {package}")
                continue
            if normalized in normalized_excluded:
                errors.append(f"compatibility profile {name} both excludes and overrides {package}")
                continue
            profile_expected[normalized] = str(version)
        profile_actual = parse_requirement_pins(ROOT / profile_file, errors)
        if profile_actual != profile_expected:
            errors.append(
                f"{profile_file} pins must match compatibility profile {name} "
                f"(expected {profile_expected}, got {profile_actual})"
            )
    return errors


def check_pyqt6_support(toolchain: dict[str, object]) -> list[str]:
    errors: list[str] = []
    raw_policy = toolchain.get("pyqt6_support")
    if not isinstance(raw_policy, dict):
        return ["configs/release_toolchain.json pyqt6_support must be an object"]

    minimum = str(raw_policy.get("minimum_version", ""))
    target = str(raw_policy.get("forward_compatibility_target", ""))
    maximum = str(raw_policy.get("maximum_version_exclusive", ""))
    probe = str(raw_policy.get("runtime_probe", ""))
    versions: dict[str, str] = {
        normalize_package_name(str(row.get("name", ""))): str(row.get("version", ""))
        for row in required_list(toolchain, "python_packages", errors)
        if isinstance(row, dict)
    }
    if not minimum or not target or not maximum or not probe:
        errors.append(
            "configs/release_toolchain.json pyqt6_support must declare minimum, target, "
            "maximum, and runtime_probe"
        )
        return errors

    try:
        minimum_key = version_key(minimum)
        target_key = version_key(target)
        maximum_key = version_key(maximum)
    except ValueError as exc:
        errors.append(f"configs/release_toolchain.json pyqt6_support has invalid version: {exc}")
        return errors

    expected_runtime_packages = ("pyqt6", "pyqt6-qt6", "pyqt6-sip")
    missing_runtime_packages = [
        package for package in expected_runtime_packages if package not in versions
    ]
    if missing_runtime_packages:
        errors.append(
            "release toolchain must pin the complete PyQt6 runtime: "
            + ", ".join(missing_runtime_packages)
        )
    if versions.get("pyqt6") != minimum:
        errors.append(
            "release toolchain PyQt6 pin must equal pyqt6_support.minimum_version: "
            f"expected {minimum}, got {versions.get('pyqt6', '<missing>')}"
        )
    for package in ("pyqt6", "pyqt6-qt6"):
        version = versions.get(package)
        if version is None:
            continue
        try:
            package_key = version_key(version)
        except ValueError as exc:
            errors.append(f"release toolchain {package} pin has invalid version: {exc}")
            continue
        if not minimum_key <= package_key < maximum_key:
            errors.append(
                f"release toolchain {package} pin must stay within the supported PyQt6 6.x range: "
                f"{minimum} <= {package} < {maximum}"
            )
    if not minimum_key < target_key < maximum_key:
        errors.append(
            "pyqt6_support versions must satisfy minimum < forward-compatibility target "
            "< maximum"
        )
    if maximum != "7.0.0":
        errors.append("pyqt6_support.maximum_version_exclusive must remain 7.0.0")
    if probe != "scripts/check_pyqt6_compatibility.py":
        errors.append(
            "pyqt6_support.runtime_probe must be scripts/check_pyqt6_compatibility.py"
        )
    if not (ROOT / probe).is_file():
        errors.append(f"pyqt6_support runtime probe is missing: {probe}")

    pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")
    expected_requirement = f'desktop = ["PyQt6>={minimum},<{maximum}"]'
    if expected_requirement not in pyproject:
        errors.append(
            "pyproject.toml desktop extra must allow the supported PyQt6 6.x range: "
            f"{expected_requirement}"
        )
    return errors


def check_python_build_backend(
    toolchain: dict[str, object], pyproject_text: str | None = None
) -> list[str]:
    errors: list[str] = []
    package_rows = required_list(toolchain, "python_packages", errors)
    versions = {
        normalize_package_name(str(row.get("name", ""))): str(row.get("version", ""))
        for row in package_rows
        if isinstance(row, dict)
    }
    setuptools_version = versions.get("setuptools")
    wheel_version = versions.get("wheel")
    if not setuptools_version or not wheel_version:
        errors.append("release toolchain must pin setuptools and wheel for the Python build backend")
        return errors
    pyproject = pyproject_text if pyproject_text is not None else PYPROJECT_PATH.read_text(encoding="utf-8")
    expected = f'requires = ["setuptools=={setuptools_version}", "wheel=={wheel_version}"]'
    if expected not in pyproject:
        errors.append(
            "pyproject.toml build-system.requires must pin setuptools and wheel to "
            "configs/release_toolchain.json"
        )
    if 'build-backend = "setuptools.build_meta"' not in pyproject:
        errors.append("pyproject.toml must use the setuptools.build_meta PEP 517 backend")
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
    compatibility = profiles.get("windows-x86-vault-fail-closed", {})
    compatibility_file = str(compatibility.get("constraints_file", ""))
    if compatibility.get("targets") != ["windows-x86"]:
        errors.append(
            "windows-x86-vault-fail-closed profile must target exactly windows-x86"
        )
    if compatibility.get("package_overrides") != {}:
        errors.append("windows-x86-vault-fail-closed profile must not override packages")
    if set(compatibility.get("excluded_packages", [])) != {
        "bcrypt",
        "cryptography",
        "truststore",
    }:
        errors.append(
            "windows-x86-vault-fail-closed profile must exclude bcrypt, cryptography, and truststore"
        )
    expected_backend = {
        "feature": "encrypted-vault",
        "state": "unavailable-fail-closed",
        "minimum_safe_cryptography": "50.0.0",
    }
    if compatibility.get("security_backend") != expected_backend:
        errors.append("windows-x86-vault-fail-closed profile has invalid backend policy")
    if "legacy-security" in workflow:
        errors.append("release workflow must not install the vulnerable legacy-security extra")
    package_versions = {
        normalize_package_name(str(row.get("name", ""))): str(row.get("version", ""))
        for row in required_list(toolchain, "python_packages", errors)
        if isinstance(row, dict)
    }
    cryptography_version = package_versions.get("cryptography")
    if not cryptography_version:
        errors.append("release toolchain must pin cryptography for native release checks")
    if cryptography_version:
        expected_windows_pin = f'$ExpectedCryptography = "{cryptography_version}"'
        if workflow.count(expected_windows_pin) != 2:
            errors.append(
                "release workflow must set the current cryptography version in both "
                "Windows x64 and ARM64 branches"
            )
        expected_macos_pin = f'expected_cryptography="{cryptography_version}"'
        if workflow.count(expected_macos_pin) != 2:
            errors.append(
                "release workflow must set the current cryptography version in both "
                "macOS x64 and ARM64 branches"
            )
    for snippet, label in {
        f"--only-binary=cryptography --constraint {constraints_file}": (
            "binary-only modern cryptography installs"
        ),
        f'--constraint {compatibility_file} pip setuptools wheel ".[package]"': (
            "Windows x86 fail-closed package install"
        ),
        'if ("${{ matrix.arch }}" -eq "x86")': "explicit Windows x86 compatibility branch",
        'if [[ "${{ matrix.arch }}" == "x64" ]]': "explicit Intel macOS source-build branch",
        "python -m pip uninstall -y bcrypt cryptography truststore": (
            "Windows x86 backend exclusion"
        ),
        "find_spec('bcrypt') is None": "Windows x86 bcrypt absence assertion",
        "find_spec('cryptography') is None": "Windows x86 backend absence assertion",
        '--no-build-isolation --no-binary=cryptography --constraint requirements-release.txt ".[desktop,security,package]"': (
            "maintained Intel macOS cryptography source build"
        ),
        f'$ExpectedCryptography = "{cryptography_version}"': (
            "Windows maintained cryptography version assertion"
        ),
        f'expected_cryptography="{cryptography_version}"': "macOS maintained version assertion",
        f"assert cryptography.__version__ == '{cryptography_version}'": (
            "Linux maintained cryptography version assertion"
        ),
        "import bcrypt, cryptography": "bcrypt/cryptography runtime import smoke",
        "assert bcrypt.__version__ == '5.0.0'": "pinned bcrypt runtime version assertion",
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
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    python = required_mapping(toolchain, "python", errors)
    if not python:
        return errors
    source_date_epoch = str(python.get("source_date_epoch", ""))
    if f"DEFAULT_SOURCE_DATE_EPOCH = {int(source_date_epoch):_}" not in helper:
        errors.append(f"make_release.py default SOURCE_DATE_EPOCH must be {source_date_epoch}")
    if "release_toolchain_metadata()" not in helper:
        errors.append("make_release.py manifest must include release_toolchain_metadata()")
    if 'build_env.setdefault("SOURCE_DATE_EPOCH", str(source_date_epoch()))' not in helper:
        errors.append("make_release.py must pass SOURCE_DATE_EPOCH into the Python package build")
    if "normalize_python_sdist(sdist)" not in helper:
        errors.append("make_release.py must normalize Python sdist archive metadata")
    if "build_release_environment_sbom" not in helper or "importlib.metadata.distributions()" not in helper:
        errors.append(
            "make_release.py must generate a source/Python release-environment CycloneDX SBOM"
        )
    if '"requirements-release.txt"' not in helper:
        errors.append("source release bundles must include requirements-release.txt")
    for packaging_file in ("MANIFEST.in", "setup.py"):
        if f'"{packaging_file}"' not in helper:
            errors.append(f"source release bundles must include {packaging_file}")
    for row in required_list(python, "compatibility_profiles", errors):
        if not isinstance(row, dict):
            continue
        constraints_file = str(row.get("constraints_file", ""))
        if constraints_file and f'"{constraints_file}"' not in helper:
            errors.append(f"source release bundles must include {constraints_file}")
    if '".[desktop,security,package]"' not in workflow:
        errors.append(
            "release workflow must install the source/Python release environment before SBOM generation"
        )
    return errors


def check_linux_appimagetool_script(
    toolchain: dict[str, object],
    script_text: str | None = None,
    workflow_text: str | None = None,
) -> list[str]:
    script = (
        script_text
        if script_text is not None
        else (ROOT / "scripts" / "make_linux_native.sh").read_text(encoding="utf-8")
    )
    workflow = workflow_text if workflow_text is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    script = strip_unquoted_comments(script)
    workflow = strip_unquoted_comments(workflow)
    errors: list[str] = []
    linux_tools = {
        str(row.get("name")): row
        for row in required_list(
            required_mapping(toolchain, "native_toolchains", errors), "linux", errors
        )
        if isinstance(row, dict)
    }
    appimagetool = linux_tools.get("appimagetool")
    if not isinstance(appimagetool, dict):
        return [*errors, "release toolchain must declare the Linux appimagetool input"]
    expected_url = (
        "https://github.com/AppImage/appimagetool/releases/download/"
        f"{APPIMAGETOOL_VERSION}/appimagetool-{{arch}}.AppImage"
    )
    if appimagetool.get("provider") != "github-release":
        errors.append("release toolchain appimagetool provider must be github-release")
    if appimagetool.get("version") != APPIMAGETOOL_VERSION:
        errors.append(f"release toolchain appimagetool version must be {APPIMAGETOOL_VERSION}")
    if appimagetool.get("url_template") != expected_url:
        errors.append("release toolchain appimagetool URL must use the pinned 1.9.1 release tag")
    if appimagetool.get("sha256") != APPIMAGETOOL_SHA256:
        errors.append("release toolchain appimagetool SHA-256 pins must match every supported architecture")
    runtime = appimagetool.get("embedded_runtime")
    expected_runtime_url = (
        "https://github.com/AppImage/type2-runtime/releases/download/"
        f"{APPIMAGE_RUNTIME_VERSION}/runtime-{{arch}}"
    )
    if not isinstance(runtime, dict):
        errors.append("release toolchain must declare the AppImage embedded type-2 runtime")
        runtime = {}
    if runtime.get("provider") != "github-release":
        errors.append("release toolchain AppImage runtime provider must be github-release")
    if runtime.get("version") != APPIMAGE_RUNTIME_VERSION:
        errors.append(f"release toolchain AppImage runtime version must be {APPIMAGE_RUNTIME_VERSION}")
    if runtime.get("url_template") != expected_runtime_url:
        errors.append("release toolchain AppImage runtime URL must use the pinned release tag")
    if runtime.get("sha256") != APPIMAGE_RUNTIME_SHA256:
        errors.append("release toolchain AppImage runtime SHA-256 pins must match every supported architecture")
    required_script_snippets = {
        'APPIMAGETOOL_VERSION="${APPIMAGETOOL_VERSION:-1.9.1}"': "pinned appimagetool version",
        'if [[ "$APPIMAGETOOL_VERSION" != "1.9.1" ]]': "appimagetool version override guard",
        "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGETOOL_VERSION}/": (
            "versioned AppImage/appimagetool release URL"
        ),
        'if [[ "$APPIMAGETOOL_SHA256" != "$EXPECTED_APPIMAGETOOL_SHA256" ]]': (
            "reviewed checksum override guard"
        ),
        'echo "${EXPECTED_APPIMAGETOOL_SHA256}  ${APPIMAGETOOL}" | sha256sum -c -': (
            "mandatory checksum verification before execution"
        ),
        "curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error": (
            "HTTPS-only fail-closed appimagetool download"
        ),
        'APPIMAGE_RUNTIME_VERSION="${APPIMAGE_RUNTIME_VERSION:-20251108}"': (
            "pinned AppImage runtime version"
        ),
        'if [[ "$APPIMAGE_RUNTIME_VERSION" != "20251108" ]]': (
            "AppImage runtime version override guard"
        ),
        "https://github.com/AppImage/type2-runtime/releases/download/${APPIMAGE_RUNTIME_VERSION}/": (
            "versioned AppImage type-2 runtime URL"
        ),
        'if [[ "$APPIMAGE_RUNTIME_SHA256" != "$EXPECTED_APPIMAGE_RUNTIME_SHA256" ]]': (
            "reviewed AppImage runtime checksum override guard"
        ),
        'echo "${EXPECTED_APPIMAGE_RUNTIME_SHA256}  ${APPIMAGE_RUNTIME}" | sha256sum -c -': (
            "mandatory AppImage runtime checksum verification before execution"
        ),
        '--runtime-file "$APPIMAGE_RUNTIME"': "explicit reviewed AppImage runtime input",
    }
    for digest in APPIMAGETOOL_SHA256.values():
        required_script_snippets[digest] = "architecture-specific reviewed appimagetool SHA-256"
    for digest in APPIMAGE_RUNTIME_SHA256.values():
        required_script_snippets[digest] = "architecture-specific reviewed AppImage runtime SHA-256"
    for snippet, label in required_script_snippets.items():
        if snippet not in script:
            errors.append(f"make_linux_native.sh missing {label}: {snippet}")
    if "/continuous/" in script:
        errors.append("make_linux_native.sh must not download appimagetool from a mutable continuous tag")
    if "command -v appimagetool" in script:
        errors.append("make_linux_native.sh must not execute an unverified PATH appimagetool")
    for snippet, label in {
        'APPIMAGETOOL_VERSION: "1.9.1"': "pinned appimagetool version environment",
        "APPIMAGETOOL_SHA256: ${{ matrix.appimagetool_sha256 }}": (
            "matrix-bound appimagetool checksum environment"
        ),
        'APPIMAGE_RUNTIME_VERSION: "20251108"': "pinned AppImage runtime version environment",
        "APPIMAGE_RUNTIME_SHA256: ${{ matrix.appimage_runtime_sha256 }}": (
            "matrix-bound AppImage runtime checksum environment"
        ),
        f"appimagetool_sha256: {APPIMAGETOOL_SHA256['x86_64']}": "x86_64 appimagetool checksum pin",
        f"appimagetool_sha256: {APPIMAGETOOL_SHA256['aarch64']}": "aarch64 appimagetool checksum pin",
        f"appimage_runtime_sha256: {APPIMAGE_RUNTIME_SHA256['x86_64']}": (
            "x86_64 AppImage runtime checksum pin"
        ),
        f"appimage_runtime_sha256: {APPIMAGE_RUNTIME_SHA256['aarch64']}": (
            "aarch64 AppImage runtime checksum pin"
        ),
    }.items():
        if snippet not in workflow:
            errors.append(f"release workflow missing {label}: {snippet}")
    return errors


def strip_unquoted_comments(text: str) -> str:
    """Remove shell/YAML comments without treating quoted hashes as comments."""
    active: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        kept: list[str] = []
        for char in line:
            if escaped:
                kept.append(char)
                escaped = False
                continue
            if char == "\\" and quote != "'":
                kept.append(char)
                escaped = True
                continue
            if char in {"'", '"'}:
                if quote is None:
                    quote = char
                elif quote == char:
                    quote = None
                kept.append(char)
                continue
            if char == "#" and quote is None:
                break
            kept.append(char)
        active.append("".join(kept).rstrip())
    return "\n".join(active)


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
        '$ExpectedVaultBackend = $Arch -ne "x86"': "architecture-specific vault expectation",
        "vault backend availability did not match expected state": "backend state assertion",
        "vault init unexpectedly succeeded without a maintained backend": "fail-closed init assertion",
        "vault did not remain uninitialized and fail closed": "fail-closed persistence assertion",
        "$PreviousErrorActionPreference = $ErrorActionPreference": "expected-failure error preference capture",
        '$ErrorActionPreference = "Continue"': "expected-failure native command handling",
        "$ErrorActionPreference = $PreviousErrorActionPreference": "expected-failure error preference restore",
        'Test-RowVault $PortableRow "portable ZIP" $ExpectedVaultBackend': "portable ZIP vault smoke",
        'Test-RowVault $ExeRow "EXE install" $ExpectedVaultBackend': "installed EXE vault smoke",
        'Test-RowVault $MsiRow "MSI install" $ExpectedVaultBackend': "installed MSI vault smoke",
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


def version_key(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(value)
    return int(parts[0]), int(parts[1]), int(parts[2])


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
