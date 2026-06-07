from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


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
    errors.extend(check_test_job(text))
    errors.extend(check_gui_render_job(text))
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
    return errors


def check_test_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "test")
    if not block:
        return ["ci workflow missing test job"]
    for os_name in ("ubuntu-latest", "windows-2025-vs2026", "macos-15-intel"):
        if os_name not in block:
            errors.append(f"ci test matrix missing OS: {os_name}")
    for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
        if f'"{version}"' not in block:
            errors.append(f"ci test matrix missing Python {version}")
    if '".[security,dev]"' not in block:
        errors.append("ci test job must install security and dev extras")
    if "python scripts/verify.py --lint" not in block:
        errors.append("ci test job must run the lint-enabled verifier")
    return errors


def check_gui_render_job(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "gui-render")
    if not block:
        return ["ci workflow missing gui-render job for live PyQt6 screenshots"]
    required_snippets = {
        'QT_QPA_PLATFORM: "offscreen"': "offscreen Qt platform",
        'python-version: "3.12"': "stable GUI smoke Python version",
        "sudo apt-get update": "Linux package index update for Qt runtime libraries",
        "libegl1": "Qt EGL runtime library for PyQt6",
        "libgl1": "OpenGL runtime library for PyQt6",
        "libxkbcommon-x11-0": "Qt xkbcommon X11 runtime library",
        "libxcb-cursor0": "Qt xcb cursor runtime library",
        '".[desktop,security,dev]"': "desktop extra installation",
        "python scripts/check_real_gui_render.py --require-pyqt6": "required live GUI render smoke",
        "--out-dir artifacts/gui-real": "live GUI screenshot artifact output",
        "actions/upload-artifact@v7": "live GUI screenshot artifact upload",
        "if-no-files-found: error": "artifact upload failure on missing live screenshots",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"ci gui-render job missing {label}: {snippet}")
    if "--preset " in block:
        errors.append("ci gui-render job must use the default all-preset live screenshot set")
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


if __name__ == "__main__":
    raise SystemExit(main())
