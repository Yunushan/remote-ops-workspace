from __future__ import annotations

import importlib.util
from pathlib import Path


def test_docs_consistency_checker_passes_current_tree() -> None:
    checker = _load_docs_checker()

    assert checker.main() == 0


def test_docs_consistency_checker_tracks_translation_snippets() -> None:
    checker = _load_docs_checker()

    assert "row vault status" in checker.README_REQUIRED_SNIPPETS
    assert "row plugins list" in checker.README_REQUIRED_SNIPPETS
    assert "--allow-public-bind" in checker.README_REQUIRED_SNIPPETS


def _load_docs_checker():
    path = Path("scripts/check_docs.py")
    spec = importlib.util.spec_from_file_location("check_docs_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
