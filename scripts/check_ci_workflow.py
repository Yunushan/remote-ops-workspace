from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SUPPORTED_HOSTED_RUNNERS = {
    "ubuntu-24.04-arm",
    "ubuntu-latest",
    "windows-11-arm",
    "windows-2025-vs2026",
    "macos-14",
    "macos-15",
    "macos-15-intel",
    "macos-26",
    "macos-26-intel",
}


def main() -> int:
    errors = check_ci_workflow()
    if errors:
        for error in errors:
            print(f"CI workflow policy: {error}", file=sys.stderr)
        return 1
    print("CI workflow policy passed")
    return 0


def check_ci_workflow(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else CI_WORKFLOW.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(check_top_level_policy(text))
    errors.extend(check_repo_policy_job(text))
    errors.extend(check_coverage_job(text))
    errors.extend(check_test_job(text))
    errors.extend(check_python315_optional_dependencies_job(text))
    errors.extend(check_python315_readiness_job(text))
    errors.extend(check_mobile_web_job(text))
    errors.extend(check_web_container_job(text))
    errors.extend(check_web_recovery_job(text))
    errors.extend(check_android_emulator_web_job(text))
    errors.extend(check_ios_simulator_web_job(text))
    errors.extend(check_gui_render_job(text))
    errors.extend(check_gui_interactions_windows_job(text))
    errors.extend(check_native_windows_readiness_job(text))
    return errors


def check_top_level_policy(workflow: str) -> list[str]:
    errors: list[str] = []
    required_trigger_snippets = {
        "push:\n    branches: [main]": "ci workflow must run on pushes to main",
        "pull_request:\n    branches: [main]": "ci workflow must run on pull requests targeting main",
    }
    for snippet, error in required_trigger_snippets.items():
        if snippet not in workflow:
            errors.append(error)
    if "concurrency:\n  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}\n  cancel-in-progress: true" not in workflow:
        errors.append("ci workflow must cancel superseded runs for the same pull request or ref")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("ci workflow must default to read-only contents permission")
    if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' not in workflow:
        errors.append("ci workflow must opt JavaScript actions into Node.js 24")
    if "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION" in workflow:
        errors.append("ci workflow must not opt JavaScript actions into an insecure Node.js runtime")
    if "python -m pip install --upgrade pip" in workflow:
        errors.append("ci workflow must not upgrade pip outside the project dependency contract")
    if "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6" not in workflow:
        errors.append("ci workflow must checkout repository sources")
    if checkout_without_persist_false(workflow):
        errors.append("every ci checkout step must set persist-credentials: false")
    errors.extend(check_supported_hosted_runner_labels(workflow))
    return errors


def check_repo_policy_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "repo-policy")
    if not block:
        return ["ci workflow missing repo-policy job for single-row repository gates"]
    required_snippets = {
        "name: Repository policy and lint": "clear policy job label",
        "runs-on: ubuntu-latest": "stable policy runner",
        "timeout-minutes: 15": "bounded policy job timeout",
        'python-version: "3.12"': "stable policy Python version",
        "sudo apt-get install -y libegl1": "Qt headless runtime dependency",
        "python -m pip install -r requirements-dev.txt": "policy dependency installation",
        "truststore.inject_into_ssl()": "system trust-store initialization for dependency audit",
        "--strict --no-deps --disable-pip -r requirements-release.txt": (
            "exact release dependency vulnerability audit"
        ),
        "python scripts/verify.py --quick": "single-row repository verifier",
        "python -m ruff check src tests scripts": "single-row ruff lint",
        "python -m mypy src/remote_ops_workspace/gui.py --platform linux": (
            "Linux GUI type-safety gate"
        ),
        "python -m mypy src/remote_ops_workspace/gui.py --platform win32": (
            "Windows GUI type-safety gate"
        ),
        "python -m mypy src/remote_ops_workspace/gui.py --platform darwin": (
            "macOS GUI type-safety gate"
        ),
        "python scripts/check_non_gui_types.py": "bounded non-GUI production type gate",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci repo-policy job missing {label}: {snippet}")
    return errors


def check_coverage_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "coverage")
    if not block:
        return ["ci workflow missing coverage job for enforced Python branch coverage"]
    required_snippets = {
        "name: Python branch-aware coverage": "clear branch-aware coverage job label",
        "runs-on: windows-2025-vs2026": "stable Windows coverage runner",
        "timeout-minutes: 30": "bounded coverage job timeout",
        'QT_QPA_PLATFORM: "offscreen"': "deterministic headless Qt coverage platform",
        'python-version: "3.12"': "stable coverage Python version",
        'python -m pip install -e ".[desktop,security,dev]"': (
            "desktop, security and development dependency installation"
        ),
        "New-Item -ItemType Directory -Force -Path artifacts/coverage | Out-Null": (
            "explicit Windows coverage evidence directory"
        ),
        "python -m pytest -q": "direct full pytest execution",
        "--cov=remote_ops_workspace": "application source coverage",
        "--cov-branch": "branch coverage measurement",
        "--cov-report=term-missing": "human-readable missing-line report",
        "--cov-report=xml:artifacts/coverage/coverage.xml": "XML coverage evidence",
        "--cov-report=json:artifacts/coverage/coverage.json": "JSON coverage evidence",
        "python scripts/check_coverage_report.py": "aggregate and branch report validator",
        "--report artifacts/coverage/coverage.json": "validated JSON coverage report",
        "if: ${{ always() }}": "coverage evidence upload after pass or failure",
        "name: python-branch-aware-coverage": "dedicated coverage artifact name",
        "path: artifacts/coverage/": "dedicated coverage artifact path",
        "if-no-files-found: error": "failure when coverage evidence is missing",
        "include-hidden-files: false": "explicit hidden-file exclusion",
        "retention-days: 14": "bounded coverage evidence retention",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci coverage job missing {label}: {snippet}")
    threshold_match = re.search(r"--cov-fail-under(?:=|\s+)(\d+(?:\.\d+)?)", block)
    if threshold_match is None:
        errors.append("ci coverage job missing an explicit branch coverage failure threshold")
    elif float(threshold_match.group(1)) < 70:
        errors.append("ci coverage job aggregate coverage failure threshold must be at least 70")
    total_match = re.search(r"--min-total(?:=|\s+)(\d+(?:\.\d+)?)", block)
    if total_match is None:
        errors.append("ci coverage job missing validated aggregate coverage threshold")
    elif float(total_match.group(1)) < 70:
        errors.append("ci coverage job validated aggregate coverage threshold must be at least 70")
    branch_match = re.search(r"--min-branches(?:=|\s+)(\d+(?:\.\d+)?)", block)
    if branch_match is None:
        errors.append("ci coverage job missing pure branch coverage threshold")
    elif float(branch_match.group(1)) < 55:
        errors.append("ci coverage job pure branch coverage threshold must be at least 55")
    if "continue-on-error: true" in block:
        errors.append("ci coverage job must remain release-blocking")
    return errors


def check_test_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "test")
    if not block:
        return ["ci workflow missing test job"]
    if "timeout-minutes: 30" not in block:
        errors.append("ci test matrix must have a bounded 30 minute job timeout")
    for os_name in (
        "ubuntu-latest",
        "ubuntu-24.04-arm",
        "windows-2025-vs2026",
        "windows-11-arm",
        "macos-15-intel",
        "macos-26-intel",
        "macos-14",
        "macos-15",
        "macos-26",
    ):
        if not workflow_block_contains_token(block, os_name):
            errors.append(f"ci test matrix missing OS: {os_name}")
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14", "3.15"):
        if f'"{version}"' not in block:
            errors.append(f"ci test matrix missing Python {version}")
    for os_name in ("macos-26-intel", "macos-14", "macos-15", "macos-26"):
        for version in ("3.12", "3.13", "3.14", "3.15"):
            if not workflow_includes_matrix_entry(block, os_name=os_name, python_version=version):
                errors.append(f"ci test matrix missing macOS smoke row: {os_name} Python {version}")
    for os_name in ("ubuntu-24.04-arm", "windows-11-arm"):
        if not workflow_includes_matrix_entry(block, os_name=os_name, python_version="3.15"):
            errors.append(f"ci test matrix missing modern ARM64 smoke row: {os_name} Python 3.15")
    if "allow-prereleases: true" not in block:
        errors.append(
            "ci test job must allow the Python 3.15 prerelease until upstream GA is available"
        )
    intel_macos_snippets = {
        "Build maintained Intel macOS security dependencies": (
            "explicit Intel macOS maintained-security source-build step"
        ),
        "runner.os == 'macOS' && runner.arch == 'X64'": (
            "Intel macOS architecture condition"
        ),
        "--constraint requirements-release.txt pip setuptools wheel maturin cffi pycparser": (
            "pinned Intel macOS cryptography build dependencies"
        ),
        "--no-build-isolation --no-binary=cryptography": (
            "maintained Intel macOS cryptography source build"
        ),
        "runner.os != 'macOS' || runner.arch != 'X64'": (
            "non-Intel-macOS dependency condition"
        ),
    }
    for snippet, label in intel_macos_snippets.items():
        if snippet not in block:
            errors.append(f"ci test job missing {label}: {snippet}")
    if '".[security,dev]"' not in block:
        errors.append("ci test job must install security and dev extras")
    if "legacy-security" in block:
        errors.append("ci test job must not install the vulnerable legacy-security extra")
    windows_arm_security_snippets = {
        "Prepare pinned Windows ARM64 security source build": (
            "maintained Windows ARM64 security source-build step"
        ),
        "runner.os == 'Windows' && runner.arch == 'ARM64'": (
            "native Windows ARM64 source-build condition"
        ),
        r".\scripts\install_windows_arm64_security.ps1": (
            "pinned Windows ARM64 OpenSSL and cryptography installer"
        ),
    }
    for snippet, label in windows_arm_security_snippets.items():
        if snippet not in block:
            errors.append(f"ci test job missing {label}: {snippet}")
    if "python -m pytest -q" not in block:
        errors.append("ci test job must run pytest directly")
    if "python scripts/verify.py --lint" in block:
        errors.append("ci test matrix must not fan out the monolithic lint verifier")
    return errors


def check_python315_optional_dependencies_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "python315-optional-dependencies")
    if not block:
        return [
            "ci workflow missing python315-optional-dependencies job for Python 3.15 "
            "optional dependency and distribution verification"
        ]
    required_snippets = {
        "name: Python 3.15 optional dependencies, GUI, and build on ${{ matrix.os }}": (
            "clear Python 3.15 optional dependency and GUI job label"
        ),
        "timeout-minutes: 60": "bounded comprehensive Python 3.15 job timeout",
        "os: [ubuntu-latest, ubuntu-24.04-arm, windows-2025-vs2026, windows-11-arm, macos-15-intel, macos-15]": (
            "Python 3.15 x64 and ARM64 Linux, Windows and macOS host matrix"
        ),
        '          - os: ubuntu-latest\n            qt_platform: "offscreen"': (
            "Linux offscreen real-GUI render platform"
        ),
        '          - os: ubuntu-24.04-arm\n            qt_platform: "offscreen"': (
            "Linux ARM64 offscreen real-GUI render platform"
        ),
        '          - os: windows-2025-vs2026\n            qt_platform: "windows"': (
            "native Windows real-GUI render platform"
        ),
        '          - os: windows-11-arm\n            qt_platform: "windows"': (
            "native Windows ARM64 real-GUI render platform"
        ),
        (
            "          - os: macos-15-intel\n"
            "            # Hosted macOS is not guaranteed to expose a logged-in WindowServer.\n"
            "            # Keep the full application render deterministic and headless there.\n"
            '            qt_platform: "offscreen"'
        ): "hosted macOS offscreen real-GUI render platform",
        (
            "          - os: macos-15\n"
            "            # Hosted macOS is not guaranteed to expose a logged-in WindowServer.\n"
            "            # Keep the full application render deterministic and headless there.\n"
            '            qt_platform: "offscreen"'
        ): "hosted Apple Silicon macOS offscreen real-GUI render platform",
        'python-version: "3.15"': "Python 3.15 interpreter request",
        "allow-prereleases: true": "Python 3.15 release-candidate resolution",
        'QT_QPA_PLATFORM: "offscreen"': "headless Python 3.15 Qt platform",
        "libegl1": "Linux Qt EGL runtime dependency",
        "libgl1": "Linux Qt OpenGL runtime dependency",
        "libxkbcommon-x11-0": "Linux Qt xkbcommon runtime dependency",
        "libxcb-cursor0": "Linux Qt cursor runtime dependency",
        "Prepare pinned Windows ARM64 security source build": (
            "maintained Windows ARM64 security source-build step"
        ),
        "runner.os == 'Windows' && runner.arch == 'ARM64'": (
            "native Windows ARM64 source-build condition"
        ),
        r".\scripts\install_windows_arm64_security.ps1": (
            "pinned Windows ARM64 OpenSSL and cryptography installer"
        ),
        'python -m pip install -e ".[desktop,security,package,dev]"': (
            "complete Python 3.15 optional dependency installation"
        ),
        "Install Python 3.15 native Windows SSH evidence dependency": (
            "explicit Python 3.15 native Windows SSH evidence dependency step"
        ),
        'python -m pip install "paramiko==5.0.0"': (
            "pinned Python 3.15 loopback SSH evidence dependency"
        ),
        "python -m pip check": "Python 3.15 installed dependency consistency gate",
        "python scripts/check_optional_dependencies.py --require-extra desktop --require-extra security --require-extra package --require-extra dev": (
            "Python 3.15 desktop, security, package and development extra smoke"
        ),
        "python -m PyInstaller --version": "Python 3.15 PyInstaller startup smoke",
        "python scripts/write_python_runtime_evidence.py --expected-version 3.15": (
            "exact Python 3.15 runtime evidence producer"
        ),
        "--require-standard-gil --out artifacts/python315-runtime/runtime.json": (
            "standard GIL-enabled runtime evidence contract"
        ),
        "sys.version_info[:2] == (3, 15)": "resolved Python 3.15 assertion",
        "import cryptography, truststore": "Python 3.15 security dependency import smoke",
        "from PyQt6.QtCore import QT_VERSION_STR": "Python 3.15 PyQt6 import smoke",
        "from PyQt6.QtWidgets import QApplication, QLabel": (
            "Python 3.15 QtWidgets application smoke"
        ),
        "app = QApplication([])": "real Python 3.15 QApplication startup",
        "assert not label.grab().isNull()": "Python 3.15 Qt widget paint assertion",
        "Verify Python 3.15 offscreen QtWidgets application startup": (
            "explicit Python 3.15 offscreen QtWidgets startup step"
        ),
        "Run the complete test suite with Python 3.15 optional dependencies": (
            "full Python 3.15 test suite with optional dependencies present"
        ),
        "run: python -m pytest -q": "direct Python 3.15 full test suite execution",
        "Run Python 3.15 native Windows SSH and ConPTY evidence": (
            "explicit Python 3.15 native Windows SSH and ConPTY evidence step"
        ),
        '          ROW_REQUIRE_WINDOWS_SSH_LOOPBACK: "1"': (
            "fail-closed Python 3.15 native Windows SSH requirement"
        ),
        "          ROW_WINDOWS_SSH_EVIDENCE_DIR: artifacts/python315-windows-ssh": (
            "Python 3.15 native Windows SSH evidence output"
        ),
        "python -m pytest -q tests/test_windows_ssh_loopback.py": (
            "real Python 3.15 native Windows OpenSSH/ConPTY loopback tests"
        ),
        "--junitxml=artifacts/python315-windows-ssh/junit.xml": (
            "Python 3.15 native Windows SSH JUnit evidence"
        ),
        "Render every real GUI preset on Python 3.15": (
            "explicit Python 3.15 all-preset GUI render step"
        ),
        "timeout-minutes: 8": "bounded Python 3.15 GUI evidence steps",
        "QT_QPA_PLATFORM: ${{ matrix.qt_platform }}": (
            "host-native Python 3.15 full GUI render override"
        ),
        "python scripts/check_real_gui_render.py --out-dir artifacts/python315-gui": (
            "Python 3.15 all-preset application GUI renderer"
        ),
        "--require-pyqt6 --timeout-seconds 300": (
            "bounded Python 3.15 GUI evidence output"
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "Python 3.15 all-preset GUI interaction gate"
        ),
        "--out-dir artifacts/python315-interactions": (
            "Python 3.15 GUI interaction evidence output"
        ),
        "name: python315-gui-${{ matrix.os }}": "per-host Python 3.15 GUI artifact",
        "path: artifacts/python315-gui": "Python 3.15 GUI artifact path",
        "name: python315-interactions-${{ matrix.os }}": (
            "per-host Python 3.15 GUI interaction artifact"
        ),
        "path: artifacts/python315-interactions": (
            "Python 3.15 GUI interaction artifact path"
        ),
        "name: python315-distributions-${{ matrix.os }}": (
            "per-host Python 3.15 distribution artifact"
        ),
        "path: artifacts/python315-dist": "Python 3.15 distribution artifact path",
        "name: python315-runtime-${{ matrix.os }}": (
            "per-host exact Python 3.15 runtime artifact"
        ),
        "path: artifacts/python315-runtime": "Python 3.15 runtime artifact path",
        "python scripts/check_python_frozen_executable.py --expected-python 3.15": (
            "real Python 3.15 frozen executable build and launch smoke"
        ),
        "--out-dir artifacts/python315-frozen --timeout-seconds 720": (
            "bounded Python 3.15 frozen executable evidence"
        ),
        "name: python315-frozen-${{ matrix.os }}": (
            "per-host Python 3.15 frozen executable artifact"
        ),
        "path: artifacts/python315-frozen": "Python 3.15 frozen executable artifact path",
        "name: python315-windows-ssh-${{ matrix.os }}": (
            "per-host Python 3.15 native Windows SSH artifact"
        ),
        "path: artifacts/python315-windows-ssh": (
            "Python 3.15 native Windows SSH artifact path"
        ),
        (
            "        if: ${{ always() && runner.os == 'Windows' }}\n"
            "        with:\n"
            "          name: python315-windows-ssh-${{ matrix.os }}\n"
            "          path: artifacts/python315-windows-ssh\n"
            "          if-no-files-found: error\n"
            "          retention-days: 90"
        ): "fail-closed retained Python 3.15 native Windows SSH evidence upload",
        "if-no-files-found: error": "fail-closed Python 3.15 GUI artifact upload",
        "python -m build --sdist --wheel --outdir artifacts/python315-dist": (
            "Python 3.15 distribution build"
        ),
        "python scripts/check_python_distribution_install.py": (
            "clean Python 3.15 wheel and sdist installation verifier"
        ),
        "--dist-dir artifacts/python315-dist": "Python 3.15 built distribution input",
        "--out artifacts/python315-runtime/distribution-install.json": (
            "machine-readable Python 3.15 distribution installation evidence"
        ),
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(
                f"ci python315-optional-dependencies job missing {label}: {snippet}"
            )
    if "continue-on-error: true" in block:
        errors.append("ci python315-optional-dependencies job must remain release-blocking")
    if "--preset" in block:
        errors.append(
            "ci python315-optional-dependencies job must render the default complete preset set"
        )
    if block.count("if: ${{ always() }}") < 5:
        errors.append("ci Python 3.15 evidence uploads must run after success or failure")
    if block.count("if-no-files-found: error") < 6:
        errors.append("ci Python 3.15 evidence uploads must fail closed for all artifact groups")
    if block.count("retention-days: 90") < 6:
        errors.append(
            "ci Python 3.15 evidence artifacts must retain all six declared groups for 90 days"
        )
    return errors


def check_python315_readiness_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "python315-readiness")
    if not block:
        return ["ci workflow missing stable Python 3.15 readiness aggregate job"]

    active_lines = {
        "name": r'^    name: Python 3\.15 readiness\s*$',
        "needs": (
            r'^    needs:\s*\[\s*test\s*,\s*python315-optional-dependencies\s*\]\s*$'
        ),
        "always": r'^    if:\s*\$\{\{\s*always\(\)\s*\}\}\s*$',
        "runner": r'^    runs-on:\s*ubuntu-latest\s*$',
        "timeout": r'^    timeout-minutes:\s*5\s*$',
        "normal result": (
            r'^      NORMAL_MATRIX_RESULT:\s*\$\{\{\s*needs\.test\.result\s*\}\}\s*$'
        ),
        "optional result": (
            r'^      OPTIONAL_MATRIX_RESULT:\s*\$\{\{\s*'
            r'needs\.python315-optional-dependencies\.result\s*\}\}\s*$'
        ),
        "normal success assertion": (
            r'^          test "\$NORMAL_MATRIX_RESULT" = "success"\s*$'
        ),
        "optional success assertion": (
            r'^          test "\$OPTIONAL_MATRIX_RESULT" = "success"\s*$'
        ),
    }
    for label, pattern in active_lines.items():
        if re.search(pattern, block, re.MULTILINE) is None:
            errors.append(f"ci Python 3.15 readiness aggregate missing active {label}")
    if "continue-on-error: true" in block:
        errors.append("ci Python 3.15 readiness aggregate must fail closed")
    return errors


def check_gui_render_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "gui-render")
    if not block:
        return ["ci workflow missing gui-render job for live PyQt6 screenshots"]
    required_snippets = {
        "timeout-minutes: 15": "bounded live GUI render job timeout",
        'QT_QPA_PLATFORM: "offscreen"': "offscreen Qt platform",
        'python-version: "3.12"': "stable GUI smoke Python version",
        "sudo apt-get update": "Linux package index update for Qt runtime libraries",
        "fontconfig": "Qt font discovery runtime",
        "fonts-dejavu-core": "known readable Linux GUI font",
        "libegl1": "Qt EGL runtime library for PyQt6",
        "libgl1": "OpenGL runtime library for PyQt6",
        "libxkbcommon-x11-0": "Qt xkbcommon X11 runtime library",
        "libxcb-cursor0": "Qt xcb cursor runtime library",
        "Verify Linux GUI font discovery": "explicit Linux GUI font discovery gate",
        "fc-cache -f": "fresh Linux fontconfig cache",
        'fc-match "DejaVu Sans"': "known Linux GUI font match",
        "fc-list : family | grep -q .": "non-empty Linux Qt font inventory assertion",
        '".[desktop,security,dev]"': "desktop extra installation",
        "timeout-minutes: 8": "bounded live GUI render smoke step timeout",
        "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240": (
            "required bounded live GUI render smoke"
        ),
        "--out-dir artifacts/gui-real": "live GUI screenshot artifact output",
        "Validate real GUI render artifact": "live GUI artifact validation step",
        "timeout-minutes: 2": "bounded live GUI artifact validation timeout",
        "python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/gui-real": (
            "live GUI artifact validator"
        ),
        "Exercise GUI controls and responsive layouts": "Linux GUI interaction step",
        "timeout-minutes: 5": "bounded Linux GUI interaction step timeout",
        "python scripts/check_gui_interactions.py --require-pyqt6 --out-dir artifacts/gui-interactions": (
            "Linux GUI interaction gate"
        ),
        "name: gui-real-render": "dedicated live GUI screenshot artifact name",
        "path: artifacts/gui-real/*": "dedicated live GUI screenshot artifact path",
        "name: gui-interactions-linux-offscreen": "Linux GUI interaction artifact name",
        "path: artifacts/gui-interactions/*": "Linux GUI interaction artifact path",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": "live GUI screenshot artifact upload",
        "if-no-files-found: error": "artifact upload failure on missing live screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci gui-render job missing {label}: {snippet}")
    if "--preset " in block:
        errors.append("ci gui-render job must use the default all-preset live screenshot set")
    return errors


def check_gui_interactions_windows_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "gui-interactions-windows")
    if not block:
        return [
            "ci workflow missing gui-interactions-windows job for native Windows PyQt6 controls"
        ]
    active_lines = {
        r"^    name: Native Windows PyQt6 render and interactions\s*$": (
            "clear native Windows render and interaction job label"
        ),
        r"^    runs-on: windows-2025-vs2026\s*$": (
            "repository-approved native Windows runner"
        ),
        r"^    timeout-minutes: 40\s*$": "bounded native Windows GUI job timeout",
        r'^      QT_QPA_PLATFORM: "windows"\s*$': "native Windows Qt platform",
        r'^      ROW_REQUIRE_WINDOWS_SSH_LOOPBACK: "1"\s*$': (
            "release-blocking native Windows SSH loopback contract"
        ),
        r"^      ROW_WINDOWS_SSH_EVIDENCE_DIR: artifacts/windows-ssh-loopback\s*$": (
            "native Windows SSH structured evidence output"
        ),
        r'^          python-version: "3\.12"\s*$': (
            "stable native Windows GUI Python version"
        ),
        r'^        run: python -m pip install -e "\.\[desktop,security,dev\]"\s*$': (
            "desktop verification dependencies"
        ),
        r'^        run: python -m pip install "paramiko==5\.0\.0"\s*$': (
            "pinned secret-free loopback SSH test server dependency"
        ),
        r"^      - name: Verify real Windows ConPTY terminal transport\s*$": (
            "real Windows ConPTY transport verification step"
        ),
        r"^        run: python -m pytest -q tests/test_windows_conpty\.py tests/test_qt_terminal_process\.py\s*$": (
            "real Windows ConPTY transport tests"
        ),
        r"^      - name: Verify native Windows OpenSSH authentication through Qt ConPTY\s*$": (
            "authenticated native OpenSSH through Qt ConPTY gate"
        ),
        r"^        run: python -m pytest -q tests/test_windows_ssh_loopback\.py --junitxml=artifacts/windows-ssh-loopback/junit\.xml\s*$": (
            "native Windows OpenSSH loopback authentication and I/O test"
        ),
        r"^      - name: Render full GUI on native Windows\s*$": (
            "native Windows full GUI render step"
        ),
        r"^        run: python scripts/check_real_gui_render\.py --require-pyqt6 --timeout-seconds 240 --out-dir artifacts/gui-real-windows\s*$": (
            "native Windows all-preset GUI render gate"
        ),
        r"^      - name: Validate native Windows GUI render artifact\s*$": (
            "native Windows GUI artifact validation step"
        ),
        r"^        run: python scripts/check_real_gui_render_artifact\.py --artifact-dir artifacts/gui-real-windows\s*$": (
            "native Windows GUI artifact validator"
        ),
        r"^      - name: Exercise native Windows controls and responsive layouts\s*$": (
            "native Windows interaction step"
        ),
        r"^        timeout-minutes: 8\s*$": (
            "bounded native Windows interaction step timeout"
        ),
        r"^        run: python scripts/check_gui_interactions\.py --require-pyqt6 --out-dir artifacts/gui-interactions-windows\s*$": (
            "native Windows GUI interaction gate"
        ),
        r"^      - name: Capture native Windows terminal tab-switch paint turns\s*$": (
            "native Windows terminal tab paint capture step"
        ),
        r"^        run: python scripts/check_windows_tab_switch_paint\.py --require-native-windows --out-dir artifacts/gui-tab-switch-windows\s*$": (
            "native Windows real tab-bar click and transient paint gate"
        ),
        r"^      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\s*$": (
            "native Windows GUI interaction artifact upload"
        ),
        r"^          name: gui-real-render-windows\s*$": (
            "native Windows GUI render artifact name"
        ),
        r"^          path: artifacts/gui-real-windows/\*\s*$": (
            "native Windows GUI render artifact path"
        ),
        r"^          name: gui-interactions-windows\s*$": (
            "native Windows GUI interaction artifact name"
        ),
        r"^          path: artifacts/gui-interactions-windows/\*\s*$": (
            "native Windows GUI interaction artifact path"
        ),
        r"^          name: gui-tab-switch-paint-windows\s*$": (
            "native Windows terminal tab paint artifact name"
        ),
        r"^          path: artifacts/gui-tab-switch-windows/\*\s*$": (
            "native Windows terminal tab paint artifact path"
        ),
        r"^          name: windows-ssh-loopback-conpty\s*$": (
            "native Windows SSH loopback evidence artifact name"
        ),
        r"^          path: artifacts/windows-ssh-loopback/\*\s*$": (
            "native Windows SSH loopback evidence artifact path"
        ),
    }
    for pattern, label in active_lines.items():
        if re.search(pattern, block, re.MULTILINE) is None:
            errors.append(f"ci gui-interactions-windows job missing active {label}")
    upload_action_pattern = (
        r"^      - uses: actions/upload-artifact@"
        r"043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\s*$"
    )
    if len(re.findall(upload_action_pattern, block, re.MULTILINE)) != 4:
        errors.append(
            "ci gui-interactions-windows job must retain four active evidence uploads"
        )
    if len(
        re.findall(r"^          if-no-files-found: error\s*$", block, re.MULTILINE)
    ) != 4:
        errors.append(
            "ci gui-interactions-windows job must fail closed for all four evidence uploads"
        )
    if "--preset " in block:
        errors.append(
            "ci gui-interactions-windows job must use the default all-preset native Windows render set"
        )
    return errors


def check_native_windows_readiness_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "native-windows-readiness")
    if not block:
        return ["ci workflow missing stable Native Windows readiness aggregate job"]

    active_lines = {
        "name": r"^    name: Native Windows readiness\s*$",
        "needs": r"^    needs:\s*\[\s*gui-interactions-windows\s*\]\s*$",
        "always": r"^    if:\s*\$\{\{\s*always\(\)\s*\}\}\s*$",
        "runner": r"^    runs-on:\s*ubuntu-latest\s*$",
        "timeout": r"^    timeout-minutes:\s*5\s*$",
        "native Windows result": (
            r"^      NATIVE_WINDOWS_RESULT:\s*\$\{\{\s*"
            r"needs\.gui-interactions-windows\.result\s*\}\}\s*$"
        ),
        "native Windows success assertion": (
            r'^          test "\$NATIVE_WINDOWS_RESULT" = "success"\s*$'
        ),
    }
    for label, pattern in active_lines.items():
        if re.search(pattern, block, re.MULTILINE) is None:
            errors.append(f"ci Native Windows readiness aggregate missing active {label}")
    if "continue-on-error: true" in block:
        errors.append("ci Native Windows readiness aggregate must fail closed")
    return errors


def check_mobile_web_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "mobile-web")
    if not block:
        return ["ci workflow missing mobile-web job for Android/iOS Web/PWA contract"]
    required_snippets = {
        "runs-on: ubuntu-latest": "stable Linux runner",
        "timeout-minutes: 10": "bounded mobile Web/PWA smoke timeout",
        'python-version: "3.12"': "stable mobile Web/PWA smoke Python version",
        'python -m pip install -e ".[dev]"': "dev dependency installation",
        "tests/test_web_hardening.py": "Web/PWA hardening tests",
        "tests/test_mobile_support.py": "mobile support contract tests",
        "tests/test_platform_targets.py": "mobile platform target tests",
        "tests/test_platform_support_truth.py": "platform truth tests",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci mobile-web job missing {label}: {snippet}")
    return errors


def check_web_container_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "web-container")
    if not block:
        return ["ci workflow missing web-container job for live Web/PWA container smoke"]
    errors: list[str] = []
    required_snippets = {
        "name: Web/PWA container smoke": "clear container smoke job label",
        "runs-on: ubuntu-latest": "stable Linux container runner",
        "timeout-minutes: 15": "bounded container smoke job timeout",
        "docker compose -p row-web-smoke -f docker/compose.yaml": "isolated Compose project name",
        "compose down --volumes --remove-orphans": "container and volume cleanup",
        "trap cleanup EXIT": "guaranteed container cleanup",
        "compose up --detach --build": "actual Compose image build and startup",
        "http://127.0.0.1:8765/healthz": "loopback health smoke",
        "{{.Config.User}}": "non-root runtime user assertion",
        '"10001:10001"': "expected non-root runtime user",
        "{{.HostConfig.ReadonlyRootfs}}": "read-only root filesystem assertion",
        "{{.HostConfig.PidsLimit}}": "PID limit assertion",
        "{{.HostConfig.CapDrop}}": "capability-drop assertion",
        "{{.HostConfig.SecurityOpt}}": "no-new-privileges assertion",
        "compose exec -T remote-ops-web sh -c 'test -w /data && touch /data/.row-write-smoke && rm /data/.row-write-smoke'": (
            "writable non-root data-volume smoke"
        ),
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci web-container job missing {label}: {snippet}")
    return errors


def check_web_recovery_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "web-recovery")
    if not block:
        return ["ci workflow missing web-recovery job for destructive backup and restore evidence"]
    errors: list[str] = []
    required_snippets = {
        "name: Web/PWA backup and restore drill": "clear recovery drill job label",
        "runs-on: ubuntu-latest": "stable recovery drill runner",
        "timeout-minutes: 20": "bounded recovery drill timeout",
        'python-version: "3.12"': "stable recovery evidence Python version",
        "python scripts/run_web_recovery_drill.py": "real recovery drill runner",
        "--project-name row-web-recovery": "isolated recovery Compose project",
        "--output artifacts/recovery/web-recovery-evidence.json": "sanitized evidence output",
        '--repository "$GITHUB_REPOSITORY"': "repository-bound recovery evidence",
        '--source-sha "$GITHUB_SHA"': "source-bound recovery evidence",
        '--workflow-run-url "$workflow_run_url"': "workflow-run-bound recovery evidence",
        '--run-attempt "$GITHUB_RUN_ATTEMPT"': "workflow-attempt-bound recovery evidence",
        "python scripts/check_web_recovery_evidence.py": "independent retained evidence validation",
        "if: ${{ always() }}": "failure-path evidence retention",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": (
            "pinned recovery evidence upload"
        ),
        "name: web-recovery-evidence-${{ github.sha }}-${{ github.run_attempt }}": (
            "source and attempt scoped recovery artifact"
        ),
        "path: artifacts/recovery/web-recovery-evidence.json": "JSON-only recovery artifact",
        "if-no-files-found: error": "missing recovery evidence failure",
        "retention-days: 30": "bounded recovery evidence retention",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci web-recovery job missing {label}: {snippet}")
    if ".tar" in block or "remote-ops-data.tar" in block:
        errors.append("ci web-recovery job must not upload backup payloads")
    return errors


def check_android_emulator_web_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "android-emulator-web")
    if not block:
        return ["ci workflow missing android-emulator-web job for Android API Web/PWA smoke"]
    required_snippets = {
        "runs-on: ubuntu-latest": "stable Linux Android runner",
        "name: Android emulator Web/PWA response smoke API": "real Android Web/PWA response job label",
        "timeout-minutes: 35": "bounded Android emulator job timeout",
        "fail-fast: false": "non-cancelling Android API matrix",
        "api-level: [31, 32, 33, 34, 35, 36]": "Android 12-16 API matrix",
        'python-version: "3.12"': "stable Android smoke Python version",
        'python -m pip install -e ".[dev]"': "dev dependency installation",
        "tests/test_mobile_support.py": "mobile support contract tests",
        "Start Web/PWA server": "host Web/PWA server startup",
        'WEB_PWA_URL="http://127.0.0.1:${WEB_PWA_PORT}/index.html"': "dynamic loopback Web/PWA URL",
        'python -m http.server "$WEB_PWA_PORT" --directory apps/web --bind 127.0.0.1': (
            "loopback-only host Web/PWA server"
        ),
        "Configure Android SDK command-line tools": "Android SDK command-line tools PATH setup",
        "cmdline-tools/latest/bin": "Android SDK command-line tools discovery path",
        "ANDROID_HOME=$sdk_root": "Android SDK home export",
        "ANDROID_AVD_HOME=$avd_home": "durable Android AVD home export",
        "GITHUB_PATH": "Android SDK executable PATH export",
        "sdkmanager": "Android SDK package installation",
        "google_apis;x86_64": "Android Google APIs system image for reliable hosted boot",
        "for attempt in 1 2 3": "bounded Android SDK installation retries",
        "removing transient cache and incomplete API": "Android SDK corrupt archive recovery",
        "Android SDK package installation failed after 3 attempts": "Android SDK retry exhaustion failure",
        "avdmanager create avd": "Android virtual device creation",
        "avdmanager list avd": "Android virtual device creation diagnostics",
        "Android AVD row-api-${{ matrix.api-level }} was not created": (
            "Android virtual device creation assertion"
        ),
        "Boot Android emulator": "Android emulator boot step",
        "timeout-minutes: 8": "bounded Android emulator boot timeout",
        "          emulator -list-avds": "Android emulator AVD visibility diagnostics",
        "Android AVD row-api-${{ matrix.api-level }} missing before emulator boot": (
            "Android emulator pre-boot AVD assertion"
        ),
        "emulator.pid": "Android emulator process tracking",
        "Android emulator process exited before adb connection": "Android emulator early-exit diagnostic",
        "Android emulator did not appear in adb devices within 180 seconds": (
            "Android emulator adb connection timeout diagnostic"
        ),
        "Android emulator did not complete boot within 180 seconds": (
            "Android emulator boot-completion timeout diagnostic"
        ),
        "adb devices -l": "Android emulator device-list diagnostics",
        "tail -200 emulator.log": "Android emulator log diagnostics",
        "sys.boot_completed": "Android emulator boot-completion check",
        "Map emulator loopback to host Web/PWA": "Android reverse-port mapping step",
        'adb reverse "tcp:${WEB_PWA_PORT}" "tcp:${WEB_PWA_PORT}"': "Android reverse-port mapping",
        "adb reverse --list": "Android reverse-port mapping assertion",
        "scripts/check_mobile_emulator_smoke.py --platform android": "Android emulator smoke helper",
        "--android-api ${{ matrix.api-level }}": "Android API assertion",
        '--url "$WEB_PWA_URL"': "emulator-routed Web/PWA URL",
        "timeout-minutes: 2": "bounded Android Web/PWA response smoke timeout",
        "tail -200 web-server.log": "Web/PWA server failure diagnostics",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": "Android smoke screenshot upload",
        "if-no-files-found: error": "artifact upload failure on missing Android screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci android-emulator-web job missing {label}: {snippet}")
    if "--skip-web-response" in block:
        errors.append("ci android-emulator-web job must not skip the emulator Web/PWA response assertion")
    return errors


def check_ios_simulator_web_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "ios-simulator-web")
    if not block:
        return ["ci workflow missing ios-simulator-web job for iOS Web/PWA smoke"]
    required_snippets = {
        "runs-on: macos-26": "current macOS/Xcode simulator runner",
        "timeout-minutes: 20": "bounded iOS simulator job timeout",
        'python-version: "3.12"': "stable iOS smoke Python version",
        'python -m pip install -e ".[dev]"': "dev dependency installation",
        "tests/test_mobile_support.py": "mobile support contract tests",
        'sock.bind(("127.0.0.1", 0))': "dynamic loopback Web/PWA server port",
        'export WEB_PWA_URL="http://127.0.0.1:${WEB_PWA_PORT}/index.html"': (
            "exported iOS Web/PWA server URL"
        ),
        'python -m http.server "$WEB_PWA_PORT" --directory apps/web --bind 127.0.0.1': (
            "loopback-bound dynamic local Web/PWA server"
        ),
        'urllib.request.urlopen(os.environ["WEB_PWA_URL"], timeout=3)': (
            "iOS Web/PWA server readiness probe"
        ),
        "deadline = time.monotonic() + 90": "iOS Web/PWA server readiness timeout budget",
        "web-server.log": "server log diagnostics for iOS Web/PWA readiness failures",
        "Web/PWA server did not become reachable before iOS simulator smoke": (
            "clear iOS Web/PWA server readiness failure"
        ),
        "scripts/check_mobile_emulator_smoke.py --platform ios": "iOS simulator smoke helper",
        "--ios-open-url-attempts 3": "iOS simulator openurl retry budget",
        '--url "$WEB_PWA_URL"': "iOS simulator host loopback URL",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": "iOS smoke screenshot upload",
        "if-no-files-found: error": "artifact upload failure on missing iOS screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci ios-simulator-web job missing {label}: {snippet}")
    return errors


def checkout_without_persist_false(workflow: str) -> bool:
    lines = workflow.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s+- uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6\s*$", line):
            continue
        indent = len(line) - len(line.lstrip())
        block: list[str] = []
        for candidate in lines[index + 1 :]:
            if re.match(rf"^\s{{{indent}}}- (uses|name): ", candidate):
                break
            block.append(candidate)
        if "persist-credentials: false" not in "\n".join(block):
            return True
    return False


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def workflow_block_contains_token(block: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])", block) is not None


def workflow_includes_matrix_entry(block: str, *, os_name: str, python_version: str) -> bool:
    pattern = rf'(?ms)^\s+- os: {re.escape(os_name)}\n\s+python-version: "{re.escape(python_version)}"\s*$'
    return re.search(pattern, block) is not None


def check_supported_hosted_runner_labels(workflow: str) -> list[str]:
    labels = sorted(discover_hosted_runner_labels(workflow))
    unknown = [label for label in labels if label not in SUPPORTED_HOSTED_RUNNERS]
    if unknown:
        allowed = ", ".join(sorted(SUPPORTED_HOSTED_RUNNERS))
        return [
            f"ci workflow contains unsupported GitHub-hosted runner label {label!r}; allowed labels: {allowed}"
            for label in unknown
        ]
    return []


def discover_hosted_runner_labels(workflow: str) -> set[str]:
    labels: set[str] = set()
    for match in re.finditer(r"(?m)^\s*runs-on:\s+([^\n#]+)", workflow):
        value = match.group(1).strip()
        if value.startswith("${{"):
            continue
        labels.update(parse_runner_label_value(value))
    test_block = workflow_job_block(workflow, "test")
    for match in re.finditer(r"(?m)^\s*(?:-\s*)?os:\s+([^\n#]+)", test_block):
        labels.update(parse_runner_label_value(match.group(1).strip()))
    return labels


def parse_runner_label_value(value: str) -> set[str]:
    text = value.strip().strip('"').strip("'")
    if not text:
        return set()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
        return {item.strip().strip('"').strip("'") for item in text.split(",") if item.strip()}
    return {text}


if __name__ == "__main__":
    raise SystemExit(main())
