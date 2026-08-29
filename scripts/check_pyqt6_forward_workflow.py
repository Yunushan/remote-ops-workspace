from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "pyqt6-forward-compatibility.yml"


def main() -> int:
    errors = check_workflow()
    if errors:
        for error in errors:
            print(f"PyQt6 forward workflow: {error}", file=sys.stderr)
        return 1
    print("PyQt6 forward-compatibility workflow policy passed")
    return 0


def check_workflow(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    required_top_level = {
        "name: PyQt6 forward compatibility": "clear workflow name",
        '    - cron: "17 3 * * 1"': "weekly scheduled probe",
        "  workflow_dispatch:": "manual forward-compatibility dispatch",
        "concurrency:\n  group: pyqt6-forward-compatibility-${{ github.workflow }}-${{ github.ref }}\n  cancel-in-progress: true": (
            "superseded-run cancellation"
        ),
        "permissions:\n  contents: read": "read-only repository permission",
        'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"': "Node.js 24 action mode",
    }
    for snippet, label in required_top_level.items():
        if snippet not in text:
            errors.append(f"missing {label}: {snippet}")

    block = workflow_job_block(text, "pyqt6-forward-compatibility")
    if not block:
        return errors + ["missing pyqt6-forward-compatibility job"]

    required_job = {
        "name: PyQt6 6.12 forward compatibility on ${{ matrix.os }}": "clear PyQt6 target job label",
        "runs-on: ${{ matrix.os }}": "cross-platform forward-compatibility runner",
        "timeout-minutes: 45": "bounded forward-compatibility job timeout",
        "strategy:\n      fail-fast: false\n      matrix:\n        include:": "cross-platform target matrix",
        "os: ubuntu-latest": "Linux target runner",
        "os: windows-2025-vs2026": "Windows target runner",
        "os: macos-15-intel": "macOS target runner",
        "QT_QPA_PLATFORM: ${{ matrix.qt_platform }}": "runner-native Qt platform selection",
        'PIP_DISABLE_PIP_VERSION_CHECK: "1"': "pip version-check suppression",
        'PIP_NO_CACHE_DIR: "1"': "pip cache suppression",
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": (
            "pinned repository checkout"
        ),
        "persist-credentials: false": "credential-free repository checkout",
        "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6": (
            "pinned Python setup action"
        ),
        'python-version: "3.15"': "Python 3.15 interpreter",
        "allow-prereleases: true": "Python 3.15 prerelease resolution",
        "name: Install Linux Qt runtime libraries": "Linux Qt runtime dependencies",
        "if: runner.os == 'Linux'": "Linux-only Qt dependency installation",
        'python -m pip install -e ".[desktop,security,package,dev]" --pre': (
            "complete prerelease GUI verification environment"
        ),
        "--extra-index-url https://www.riverbankcomputing.com/pypi/simple/": (
            "Riverbank prerelease package index"
        ),
        "name: Select exact PyQt6 6.12 line when published": (
            "target-line selection step"
        ),
        "python -m pip index versions PyQt6": "PyQt6 target availability query",
        '"PyQt6>=6.12.0,<6.13.0"': "exact PyQt6 6.12 dependency range",
        '"PyQt6-Qt6>=6.12.0,<6.13.0"': "exact Qt 6.12 dependency range",
        "--upgrade-strategy eager": "eager PyQt6 dependency upgrades",
        "--only-binary PyQt6,PyQt6-Qt6,PyQt6-sip": "binary PyQt6 runtime wheels",
        '"PYQT6_TARGET_AVAILABLE=$targetAvailable"': "target availability propagation",
        "python scripts/check_pyqt6_compatibility.py --require-pyqt6 --target-version 6.12.0": (
            "PyQt6 6.12 runtime contract"
        ),
        "python scripts/check_pyqt6_compatibility.py --require-pyqt6 --target-version 6.12.0 --require-target": (
            "strict PyQt6 6.12 runtime contract"
        ),
        "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 300": (
            "all-preset PyQt6 render evidence"
        ),
        "--out-dir artifacts/pyqt6-forward-render": "forward render evidence directory",
        "python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/pyqt6-forward-render": (
            "forward render evidence validator"
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "all-control PyQt6 interaction evidence"
        ),
        "--out-dir artifacts/pyqt6-forward-interactions": "forward interaction evidence directory",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": (
            "pinned evidence upload action"
        ),
        "if: ${{ always() }}": "evidence upload after failures",
        "name: pyqt6-forward-compatibility-${{ matrix.os }}": "forward-compatibility artifact name",
        "path: artifacts/pyqt6-forward-*": "forward-compatibility artifact path",
        "if-no-files-found: error": "fail-closed evidence upload",
        "include-hidden-files: false": "hidden-file exclusion",
        "retention-days: 30": "bounded evidence retention",
    }
    for snippet, label in required_job.items():
        if snippet not in block:
            errors.append(f"job missing {label}: {snippet}")
    if "continue-on-error: true" in block:
        errors.append("forward-compatibility job must not hide runtime failures")
    if "--preset " in block:
        errors.append("forward-compatibility job must exercise the default complete preset set")
    if block.count("actions/upload-artifact@") != 1:
        errors.append("forward-compatibility job must retain one complete evidence upload")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())
