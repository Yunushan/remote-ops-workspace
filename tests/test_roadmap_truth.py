from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_roadmap_truth_checker_passes_current_tree() -> None:
    checker = _load_roadmap_truth_checker()

    assert checker.main() == 0


def test_roadmap_truth_checker_rejects_stale_future_release_phase() -> None:
    checker = _load_roadmap_truth_checker()
    roadmap = Path("docs/ROADMAP.md").read_text(encoding="utf-8")
    stale = f"{roadmap}\n## v9.9.x\n\n- Ship Phase 2 Windows native installers (`.exe`, `.msi`) from CI.\n"

    errors = checker.check_roadmap_truth(stale)

    assert any("future roadmap still lists shipped Phase 2 Windows native releases" in error for error in errors)


def test_roadmap_truth_checker_requires_completed_snippets() -> None:
    checker = _load_roadmap_truth_checker()
    roadmap = Path("docs/ROADMAP.md").read_text(encoding="utf-8").replace(
        "Added sync provider interface.",
        "Added mounted-directory sync workflow.",
    )

    errors = checker.check_roadmap_truth(roadmap)

    assert "completed roadmap section missing sync provider interface: Added sync provider interface." in errors


def test_roadmap_truth_checker_rejects_stale_future_cli_workflow() -> None:
    checker = _load_roadmap_truth_checker()
    roadmap = Path("docs/ROADMAP.md").read_text(encoding="utf-8")
    stale = f"{roadmap}\n## v9.9.x\n\n- Add sync provider interface.\n"

    errors = checker.check_roadmap_truth(stale)

    assert "future roadmap still lists shipped sync provider interface: Add sync provider interface." in errors


def test_roadmap_truth_checker_requires_implementation_evidence(tmp_path: Path) -> None:
    checker = _load_roadmap_truth_checker()
    item = checker.IMPLEMENTED_ITEMS[0]

    errors = checker.check_evidence(item, root=tmp_path)

    assert any("evidence file missing" in error for error in errors)


def test_roadmap_truth_checker_tracks_native_smoke_as_completed() -> None:
    checker = _load_roadmap_truth_checker()

    labels = {item.label: item for item in checker.IMPLEMENTED_ITEMS}

    assert "native installer smoke contract" in labels
    assert "Add install, upgrade and uninstall smoke tests for native packages." in (
        labels["native installer smoke contract"].stale_future_snippets
    )


def _load_roadmap_truth_checker():
    path = Path("scripts/check_roadmap_truth.py")
    spec = importlib.util.spec_from_file_location("check_roadmap_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
