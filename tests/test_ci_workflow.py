from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_ci_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_ci_workflow_requires_lint_enabled_verifier() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "python scripts/verify.py --lint",
        "python scripts/verify.py",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci test job must run the lint-enabled verifier" in errors


def test_ci_workflow_requires_dedicated_gui_render_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  gui-render:",
        "  gui_render_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing gui-render job for live PyQt6 screenshots" in errors


def test_ci_workflow_requires_linux_qt_runtime_libraries() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "            libegl1 \\\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci gui-render job missing Qt EGL runtime library for PyQt6: libegl1" in errors


def test_ci_workflow_requires_checkout_credentials_disabled() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          persist-credentials: false\n",
        "",
        1,
    )

    errors = checker.check_ci_workflow(workflow)

    assert "every ci checkout step must set persist-credentials: false" in errors


def _load_checker():
    path = Path("scripts/check_ci_workflow.py")
    spec = importlib.util.spec_from_file_location("check_ci_workflow_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
