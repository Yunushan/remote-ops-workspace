from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_windows_xp_legacy_candidate_workflow_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_windows_xp_legacy_candidate_workflow_requires_both_architectures() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-legacy-candidate.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("arch: [x86, x64]", "arch: [x64]")

    errors = checker.check_windows_xp_legacy_candidate_workflow(workflow)

    assert "legacy candidate workflow missing x86/x64 matrix: arch: [x86, x64]" in errors


def test_windows_xp_legacy_candidate_workflow_rejects_release_publish() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-legacy-candidate.yml").read_text(encoding="utf-8")
    workflow += "\n      - uses: softprops/action-gh-release@v2\n"

    errors = checker.check_windows_xp_legacy_candidate_workflow(workflow)

    assert "legacy candidate workflow must not publish a release or claim XP-host proof" in errors


def _load_checker():
    module_path = Path("scripts/check_windows_xp_legacy_candidate_workflow.py")
    spec = importlib.util.spec_from_file_location("check_windows_xp_legacy_candidate_workflow", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
