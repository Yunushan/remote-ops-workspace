from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SUPPORTED_HOSTED_RUNNERS = {
    "ubuntu-latest",
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
    errors.extend(check_test_job(text))
    errors.extend(check_mobile_web_job(text))
    errors.extend(check_android_emulator_web_job(text))
    errors.extend(check_ios_simulator_web_job(text))
    errors.extend(check_gui_render_job(text))
    errors.extend(check_gui_interactions_windows_job(text))
    return errors


def check_top_level_policy(workflow: str) -> list[str]:
    errors: list[str] = []
    for trigger in ("push:", "pull_request:"):
        if trigger not in workflow:
            errors.append(f"ci workflow must run on {trigger.rstrip(':')}")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("ci workflow must default to read-only contents permission")
    if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' not in workflow:
        errors.append("ci workflow must opt JavaScript actions into Node.js 24")
    if "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION" in workflow:
        errors.append("ci workflow must not opt JavaScript actions into an insecure Node.js runtime")
    if "python -m pip install --upgrade pip" in workflow:
        errors.append("ci workflow must not upgrade pip outside the project dependency contract")
    if "actions/checkout@v6" not in workflow:
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
        'python -m pip install -e ".[security,dev]"': "policy dependency installation",
        "python scripts/verify.py --quick": "single-row repository verifier",
        "python -m ruff check src tests scripts": "single-row ruff lint",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci repo-policy job missing {label}: {snippet}")
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
        "windows-2025-vs2026",
        "macos-15-intel",
        "macos-26-intel",
        "macos-14",
        "macos-15",
        "macos-26",
    ):
        if not workflow_block_contains_token(block, os_name):
            errors.append(f"ci test matrix missing OS: {os_name}")
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        if f'"{version}"' not in block:
            errors.append(f"ci test matrix missing Python {version}")
    for os_name in ("macos-26-intel", "macos-14", "macos-15", "macos-26"):
        for version in ("3.12", "3.13", "3.14"):
            if not workflow_includes_matrix_entry(block, os_name=os_name, python_version=version):
                errors.append(f"ci test matrix missing macOS smoke row: {os_name} Python {version}")
    if '".[security,dev]"' not in block:
        errors.append("ci test job must install security and dev extras")
    if "python -m pytest -q" not in block:
        errors.append("ci test job must run pytest directly")
    if "python scripts/verify.py --lint" in block:
        errors.append("ci test matrix must not fan out the monolithic lint verifier")
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
        "actions/upload-artifact@v7": "live GUI screenshot artifact upload",
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
    required_snippets = {
        "name: Native Windows PyQt6 render and interactions": (
            "clear native Windows render and interaction job label"
        ),
        "runs-on: windows-2025-vs2026": "repository-approved native Windows runner",
        "timeout-minutes: 20": "bounded native Windows GUI job timeout",
        'QT_QPA_PLATFORM: "windows"': "native Windows Qt platform",
        'python-version: "3.12"': "stable native Windows GUI Python version",
        'python -m pip install -e ".[desktop,security,dev]"': "desktop verification dependencies",
        "Render full GUI on native Windows": "native Windows full GUI render step",
        "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240 --out-dir artifacts/gui-real-windows": (
            "native Windows all-preset GUI render gate"
        ),
        "Validate native Windows GUI render artifact": (
            "native Windows GUI artifact validation step"
        ),
        "python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/gui-real-windows": (
            "native Windows GUI artifact validator"
        ),
        "Exercise native Windows controls and responsive layouts": "native Windows interaction step",
        "timeout-minutes: 8": "bounded native Windows interaction step timeout",
        "python scripts/check_gui_interactions.py --require-pyqt6 --out-dir artifacts/gui-interactions-windows": (
            "native Windows GUI interaction gate"
        ),
        "actions/upload-artifact@v7": "native Windows GUI interaction artifact upload",
        "name: gui-real-render-windows": "native Windows GUI render artifact name",
        "path: artifacts/gui-real-windows/*": "native Windows GUI render artifact path",
        "name: gui-interactions-windows": "native Windows GUI interaction artifact name",
        "path: artifacts/gui-interactions-windows/*": "native Windows GUI interaction artifact path",
        "if-no-files-found: error": "missing native Windows interaction artifact failure",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci gui-interactions-windows job missing {label}: {snippet}")
    if "--preset " in block:
        errors.append(
            "ci gui-interactions-windows job must use the default all-preset native Windows render set"
        )
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


def check_android_emulator_web_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "android-emulator-web")
    if not block:
        return ["ci workflow missing android-emulator-web job for Android API Web/PWA smoke"]
    required_snippets = {
        "runs-on: ubuntu-latest": "stable Linux Android runner",
        "timeout-minutes: 35": "bounded Android emulator job timeout",
        "fail-fast: false": "non-cancelling Android API matrix",
        "api-level: [31, 32, 33, 34, 35, 36]": "Android 12-16 API matrix",
        'python-version: "3.12"': "stable Android smoke Python version",
        'python -m pip install -e ".[dev]"': "dev dependency installation",
        "tests/test_mobile_support.py": "mobile support contract tests",
        "Configure Android SDK command-line tools": "Android SDK command-line tools PATH setup",
        "cmdline-tools/latest/bin": "Android SDK command-line tools discovery path",
        "ANDROID_HOME=$sdk_root": "Android SDK home export",
        "ANDROID_AVD_HOME=$avd_home": "durable Android AVD home export",
        "GITHUB_PATH": "Android SDK executable PATH export",
        "sdkmanager": "Android SDK package installation",
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
        "scripts/check_mobile_emulator_smoke.py --platform android": "Android emulator smoke helper",
        "--android-api ${{ matrix.api-level }}": "Android API assertion",
        "http://10.0.2.2:8765/index.html": "Android emulator host loopback URL",
        "actions/upload-artifact@v7": "Android smoke screenshot upload",
        "if-no-files-found: error": "artifact upload failure on missing Android screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci android-emulator-web job missing {label}: {snippet}")
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
        "actions/upload-artifact@v7": "iOS smoke screenshot upload",
        "if-no-files-found: error": "artifact upload failure on missing iOS screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci ios-simulator-web job missing {label}: {snippet}")
    return errors


def checkout_without_persist_false(workflow: str) -> bool:
    lines = workflow.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s+- uses: actions/checkout@v6\s*$", line):
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
