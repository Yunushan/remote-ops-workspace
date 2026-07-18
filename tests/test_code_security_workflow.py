from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_code_security_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_code_security_workflow_requires_superseded_run_cancellation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/codeql.yml").read_text(encoding="utf-8").replace(
        "  cancel-in-progress: true\n",
        "",
    )

    errors = checker.check_code_security_workflow(workflow)

    assert any("superseded-run cancellation" in error for error in errors)


def test_code_security_workflow_requires_pinned_codeql_analysis() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/codeql.yml").read_text(encoding="utf-8").replace(
        f"github/codeql-action/analyze@{checker.CODEQL_PIN}",
        "github/codeql-action/analyze@v4",
    )

    errors = checker.check_code_security_workflow(workflow)

    assert any("pinned CodeQL analysis" in error for error in errors)


def _load_checker():
    path = Path("scripts/check_code_security_workflow.py")
    spec = importlib.util.spec_from_file_location("check_code_security_workflow_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
