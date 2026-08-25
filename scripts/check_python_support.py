from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = "pyproject.toml"
CI_WORKFLOW = ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ".github/workflows/release.yml"
PYTHON_SUPPORT_DOC = "docs/PYTHON_SUPPORT.md"
RELEASE_TOOLCHAIN = "configs/release_toolchain.json"
REPOSITORY_GOVERNANCE = "scripts/check_repository_governance.py"


def main() -> int:
    errors = check_python_support()
    if errors:
        for error in errors:
            print(f"Python support: {error}", file=sys.stderr)
        return 1
    print("Python 3.10-3.15 support contract passed")
    return 0


def check_python_support(overrides: dict[str, str] | None = None) -> list[str]:
    overrides = overrides or {}
    errors: list[str] = []

    pyproject = read(PYPROJECT, overrides)
    if 'requires-python = ">=3.10,<3.16"' not in pyproject:
        errors.append("pyproject.toml must bound source-host support to >=3.10,<3.16")
    if 'package = ["build>=1.2", "pyinstaller>=6.21"]' not in pyproject:
        errors.append(
            "pyproject.toml package extra must require pyinstaller>=6.21 for Python 3.15"
        )
    if 'desktop = ["PyQt6>=6.11.0"]' not in pyproject:
        errors.append(
            "pyproject.toml desktop extra must require PyQt6>=6.11.0 for Python 3.15"
        )
    for version in range(10, 16):
        classifier = f'"Programming Language :: Python :: 3.{version}"'
        if classifier not in pyproject:
            errors.append(f"pyproject.toml missing Python 3.{version} classifier")
    if '"Programming Language :: Python :: 3.16"' in pyproject:
        errors.append("pyproject.toml must not claim untested Python 3.16 support")

    workflow = read(CI_WORKFLOW, overrides)
    required_workflow_snippets = {
        'python-version: ["3.10", "3.11", "3.12", "3.13", "3.14", "3.15"]': (
            "normal compatibility matrix through Python 3.15"
        ),
        "  python315-optional-dependencies:": (
            "dedicated Python 3.15 optional dependency and distribution job"
        ),
        'python-version: "3.15"': "Python 3.15 interpreter request",
        "allow-prereleases: true": "pre-GA Python 3.15 resolution",
        'python -m pip install -e ".[desktop,security,package,dev]"': (
            "Python 3.15 desktop/security/package/development dependency install"
        ),
        "python -m pip check": "Python 3.15 dependency consistency gate",
        "python scripts/check_optional_dependencies.py --require-extra desktop --require-extra security --require-extra package --require-extra dev": (
            "Python 3.15 complete optional-extra smoke"
        ),
        "python -m PyInstaller --version": "Python 3.15 PyInstaller smoke",
        "python scripts/check_python_frozen_executable.py --expected-python 3.15": (
            "Python 3.15 real frozen executable build and launch smoke"
        ),
        "--out-dir artifacts/python315-frozen --timeout-seconds 720": (
            "bounded Python 3.15 frozen executable evidence"
        ),
        "python scripts/write_python_runtime_evidence.py --expected-version 3.15": (
            "exact Python 3.15 runtime evidence"
        ),
        "--require-standard-gil --out artifacts/python315-runtime/runtime.json": (
            "standard GIL-enabled Python 3.15 runtime evidence"
        ),
        "sys.version_info[:2] == (3, 15)": "resolved Python 3.15 assertion",
        "from PyQt6.QtWidgets import QApplication, QLabel": (
            "Python 3.15 QtWidgets application startup"
        ),
        "app = QApplication([])": "real Python 3.15 QApplication construction",
        "assert not label.grab().isNull()": "Python 3.15 widget paint assertion",
        "Verify Python 3.15 offscreen QtWidgets application startup": (
            "explicit Python 3.15 offscreen QtWidgets startup"
        ),
        "python scripts/check_real_gui_render.py --out-dir artifacts/python315-gui": (
            "Python 3.15 all-preset real application GUI render"
        ),
        "QT_QPA_PLATFORM: ${{ matrix.qt_platform }}": (
            "host-native Python 3.15 full GUI renderer platform"
        ),
        (
            "          - os: macos-15-intel\n"
            "            # Hosted macOS is not guaranteed to expose a logged-in WindowServer.\n"
            "            # Keep the full application render deterministic and headless there.\n"
            '            qt_platform: "offscreen"'
        ): "hosted macOS offscreen Python 3.15 GUI renderer",
        "--require-pyqt6 --timeout-seconds 300": (
            "bounded Python 3.15 GUI evidence capture"
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "Python 3.15 all-preset GUI interaction gate"
        ),
        "--out-dir artifacts/python315-interactions": (
            "Python 3.15 GUI interaction evidence"
        ),
        "name: python315-gui-${{ matrix.os }}": "per-host Python 3.15 GUI evidence artifact",
        "python -m build --sdist --wheel --outdir artifacts/python315-dist": (
            "Python 3.15 sdist and wheel build"
        ),
        "python scripts/check_python_distribution_install.py": (
            "Python 3.15 clean distribution installation verifier"
        ),
        "--out artifacts/python315-runtime/distribution-install.json": (
            "Python 3.15 distribution installation evidence"
        ),
        "name: python315-distributions-${{ matrix.os }}": (
            "per-host Python 3.15 distribution artifact"
        ),
        "name: python315-runtime-${{ matrix.os }}": (
            "per-host exact Python 3.15 runtime artifact"
        ),
        "name: python315-frozen-${{ matrix.os }}": (
            "per-host Python 3.15 frozen executable artifact"
        ),
        "retention-days: 90": "durable Python 3.15 evidence retention",
        "python -m pytest -q": "Python test execution",
    }
    for snippet, label in required_workflow_snippets.items():
        if snippet not in workflow:
            errors.append(f"ci workflow missing {label}: {snippet}")
    for runner in ("macos-26-intel", "macos-14", "macos-15", "macos-26"):
        row = f'          - os: {runner}\n            python-version: "3.15"'
        if row not in workflow:
            errors.append(f"ci workflow missing {runner} Python 3.15 host row")
    for runner in ("ubuntu-24.04-arm", "windows-11-arm"):
        row = f'          - os: {runner}\n            python-version: "3.15"'
        if row not in workflow:
            errors.append(f"ci workflow missing {runner} Python 3.15 ARM64 host row")
    python315_block = workflow_job_block(workflow, "python315-optional-dependencies")
    required_python315_block_snippets = {
        'python -m pip install -e ".[desktop,security,package,dev]"': (
            "Python 3.15 complete optional-extra environment"
        ),
        "python -m pip check": "Python 3.15 dependency consistency gate",
        "run: python -m pytest -q": "Python 3.15 full suite with optional extras installed",
        "python scripts/check_real_gui_render.py --out-dir artifacts/python315-gui": (
            "Python 3.15 all-preset real application GUI render"
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "Python 3.15 all-preset GUI interaction gate"
        ),
        "python scripts/check_python_distribution_install.py": (
            "Python 3.15 clean distribution installation verifier"
        ),
    }
    for snippet, label in required_python315_block_snippets.items():
        if python315_block and snippet not in python315_block:
            errors.append(f"ci Python 3.15 job missing {label}: {snippet}")
    if python315_block and "continue-on-error: true" in python315_block:
        errors.append(
            "Python 3.15 optional dependency verification must remain release-blocking"
        )
    if python315_block and "--preset" in python315_block:
        errors.append(
            "Python 3.15 optional dependency verification must exercise every GUI preset"
        )
    if python315_block and python315_block.count("retention-days: 90") < 6:
        errors.append("Python 3.15 must retain all six evidence artifact groups for 90 days")

    readiness_block = workflow_job_block(workflow, "python315-readiness")
    readiness_patterns = {
        "stable Python 3.15 readiness name": r"^    name: Python 3\.15 readiness\s*$",
        "both Python 3.15 upstream jobs": (
            r"^    needs:\s*\[\s*test\s*,\s*python315-optional-dependencies\s*\]\s*$"
        ),
        "fail-closed always evaluation": r"^    if:\s*\$\{\{\s*always\(\)\s*\}\}\s*$",
        "normal matrix success assertion": (
            r'^          test "\$NORMAL_MATRIX_RESULT" = "success"\s*$'
        ),
        "optional matrix success assertion": (
            r'^          test "\$OPTIONAL_MATRIX_RESULT" = "success"\s*$'
        ),
    }
    if not readiness_block:
        errors.append("ci workflow missing stable Python 3.15 readiness aggregate")
    else:
        for label, pattern in readiness_patterns.items():
            if re.search(pattern, readiness_block, re.MULTILINE) is None:
                errors.append(f"ci Python 3.15 readiness aggregate missing active {label}")

    native_windows_readiness_block = workflow_job_block(
        workflow, "native-windows-readiness"
    )
    native_windows_readiness_patterns = {
        "stable Native Windows readiness name": (
            r"^    name: Native Windows readiness\s*$"
        ),
        "native Windows upstream jobs": (
            r"^    needs:\s*\[\s*gui-interactions-windows\s*\]\s*$"
        ),
        "fail-closed always evaluation": r"^    if:\s*\$\{\{\s*always\(\)\s*\}\}\s*$",
        "native Windows success assertion": (
            r'^          test "\$NATIVE_WINDOWS_RESULT" = "success"\s*$'
        ),
    }
    if not native_windows_readiness_block:
        errors.append("ci workflow missing stable Native Windows readiness aggregate")
    else:
        for label, pattern in native_windows_readiness_patterns.items():
            if re.search(pattern, native_windows_readiness_block, re.MULTILINE) is None:
                errors.append(
                    f"ci Native Windows readiness aggregate missing active {label}"
                )

    governance = read(REPOSITORY_GOVERNANCE, overrides)
    if re.search(r'^\s+"Python 3\.15 readiness",\s*$', governance, re.MULTILINE) is None:
        errors.append("repository governance must require the Python 3.15 readiness context")
    if re.search(r'^\s+"Native Windows readiness",\s*$', governance, re.MULTILINE) is None:
        errors.append("repository governance must require the Native Windows readiness context")

    release_workflow = read(RELEASE_WORKFLOW, overrides)
    release_patterns = {
        "Actions read permission": r"^  actions:\s*read\s*$",
        "Python 3.15 and native Windows CI evidence step": (
            r"^      - name: Require successful Python 3\.15 and native Windows "
            r"CI evidence for release source\s*$"
        ),
        "exact release-source CI evidence command": (
            r"^          python scripts/check_python315_ci_evidence\.py\s*$"
        ),
        "release source SHA binding": r'^          --sha "\$\(git rev-parse HEAD\)"\s*$',
        "bounded release-source CI evidence wait": r"^          --wait-seconds 5400\s*$",
        "bounded release-source CI evidence polling": (
            r"^          --poll-interval-seconds 15\s*$"
        ),
    }
    for label, pattern in release_patterns.items():
        if re.search(pattern, release_workflow, re.MULTILINE) is None:
            errors.append(f"release workflow missing active Python 3.15 {label}")

    for readme in ("README.md", "README.tr.md"):
        text = read(readme, overrides)
        if "runtime-Python%203.10--3.15" not in text:
            errors.append(f"{readme} must advertise the bounded Python 3.10-3.15 runtime")
        if "docs/PYTHON_SUPPORT.md" not in text:
            errors.append(f"{readme} must link the Python support evidence boundary")

    support_doc = read(PYTHON_SUPPORT_DOC, overrides)
    required_doc_snippets = {
        "standard, GIL-enabled CPython 3.10 through 3.15": "standard runtime boundary",
        "3.15 release-candidate compatibility": "release-candidate evidence claim",
        "3.15 final-GA certification": "final-GA evidence distinction",
        "releaselevel=final": "machine-checked final-GA runtime distinction",
        "Linux x64 and ARM64, Windows x64 and ARM64, and macOS Intel and Apple Silicon": (
            "modern host architecture evidence boundary"
        ),
        "wheel and sdist in clean virtual environments": "installed distribution evidence",
        "PyInstaller 6.21 or newer": "Python 3.15-capable PyInstaller lower bound",
        "runtime.json": "exact runtime evidence artifact",
        "Free-threaded `3.15t` is not claimed": "free-threading exclusion",
        "pinned Python 3.12 release\n  toolchain": "release-toolchain distinction",
        "it is not a substitute for that six-host result": "hosted evidence boundary",
        "`Python 3.15 readiness`": "stable branch-protection context",
        "`Native Windows readiness`": "stable native Windows branch-protection context",
        "exact tagged source SHA": "release-source CI evidence binding",
        "waits for up to 90 minutes": "bounded release-source CI evidence wait",
        "rejects truncated or\ninconsistent API responses": (
            "complete paginated release-source CI evidence"
        ),
        "live `main` branch rule": "live branch-protection application requirement",
    }
    for snippet, label in required_doc_snippets.items():
        if snippet not in support_doc:
            errors.append(f"{PYTHON_SUPPORT_DOC} missing {label}")

    shell_version_check = "(3, 10) <= sys.version_info < (3, 16)"
    for installer in ("installers/install.sh", "installers/install-termux.sh", "installers/install.ps1"):
        text = read(installer, overrides)
        if shell_version_check not in text:
            errors.append(f"{installer} must reject runtimes outside Python 3.10-3.15")
        if "Python 3.10 through 3.15" not in text:
            errors.append(f"{installer} must explain the Python 3.10-3.15 boundary")
    batch = read("installers/install.bat", overrides)
    if "(3, 10) <= sys.version_info ^< (3, 16)" not in batch:
        errors.append("installers/install.bat must reject runtimes outside Python 3.10-3.15")
    if "Python 3.10 through 3.15" not in batch:
        errors.append("installers/install.bat must explain the Python 3.10-3.15 boundary")

    plugin_dev = read("src/remote_ops_workspace/plugin_dev.py", overrides)
    if 'requires-python = ">=3.10,<3.16"' not in plugin_dev:
        errors.append("plugin scaffold must inherit the Python >=3.10,<3.16 host boundary")

    targets = read("configs/platform_targets.json", overrides)
    for architecture in ("32-bit x86", "32-bit ARM"):
        snippet = (
            f"{architecture} Linux distributions with Python 3.10-3.14 and PyInstaller "
            "support; Python 3.15 remains outside this protected target claim"
        )
        if snippet not in targets:
            errors.append(
                "platform target support text must keep unproven Python 3.15 outside "
                f"the {architecture} protected claim"
            )

    toolchain = read(RELEASE_TOOLCHAIN, overrides)
    if '"version": "3.12"' not in toolchain:
        errors.append("release toolchain must keep its separately pinned Python 3.12 builder")

    return errors


def read(relative: str, overrides: dict[str, str]) -> str:
    if relative in overrides:
        return overrides[relative]
    return (ROOT / relative).read_text(encoding="utf-8")


def workflow_job_block(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
