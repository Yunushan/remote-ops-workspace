from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_pyqt6_forward_workflow_policy_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_pyqt6_forward_workflow_requires_scheduled_and_manual_triggers() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/pyqt6-forward-compatibility.yml").read_text(
        encoding="utf-8"
    )

    errors = checker.check_workflow(source.replace('    - cron: "17 3 * * 1"\n', ""))
    manual_errors = checker.check_workflow(source.replace("  workflow_dispatch:\n", ""))

    assert any("weekly scheduled probe" in error for error in errors)
    assert any("manual forward-compatibility dispatch" in error for error in manual_errors)


def test_pyqt6_forward_workflow_requires_real_runtime_and_gui_evidence() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/pyqt6-forward-compatibility.yml").read_text(
        encoding="utf-8"
    )
    mutations = {
        "python scripts/check_pyqt6_compatibility.py --require-pyqt6 --target-version 6.12.0": (
            "python scripts/check_pyqt6_compatibility.py",
            "PyQt6 6.12 runtime contract",
        ),
        "python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 300": (
            "python scripts/check_real_gui_render.py --preset native",
            "all-preset PyQt6 render evidence",
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "python scripts/check_gui_interactions.py",
            "all-control PyQt6 interaction evidence",
        ),
        "--extra-index-url https://www.riverbankcomputing.com/pypi/simple/": (
            "--extra-index-url https://pypi.org/simple/",
            "Riverbank prerelease package index",
        ),
        '"PyQt6>=6.12.0,<6.13.0"': (
            '"PyQt6>=6.11.0,<6.12.0"',
            "exact PyQt6 6.12 dependency range",
        ),
        "--only-binary PyQt6,PyQt6-Qt6,PyQt6-sip": (
            "--only-binary PyQt6",
            "binary PyQt6 runtime wheels",
        ),
    }

    for original, (replacement, label) in mutations.items():
        errors = checker.check_workflow(source.replace(original, replacement))
        assert any(label in error for error in errors)


def test_pyqt6_forward_workflow_requires_fail_closed_evidence_upload() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/pyqt6-forward-compatibility.yml").read_text(
        encoding="utf-8"
    )

    errors = checker.check_workflow(source.replace("if-no-files-found: error", "if-no-files-found: warn"))
    advisory = checker.check_workflow(source.replace("if: ${{ always() }}", "if: success()"))

    assert any("fail-closed evidence upload" in error for error in errors)
    assert any("evidence upload after failures" in error for error in advisory)


def _load_checker():
    path = Path("scripts/check_pyqt6_forward_workflow.py")
    spec = importlib.util.spec_from_file_location("check_pyqt6_forward_workflow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
