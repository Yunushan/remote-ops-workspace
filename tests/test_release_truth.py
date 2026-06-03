from __future__ import annotations

import importlib.util
from pathlib import Path


def test_release_truth_checker_passes_current_tree() -> None:
    checker = _load_release_truth_checker()

    assert checker.main() == 0


def test_release_truth_checker_tracks_default_workflow_arches() -> None:
    checker = _load_release_truth_checker()

    assert checker.WORKFLOW_ARCHES["windows-native"] == {"x86", "x64", "arm64"}
    assert checker.WORKFLOW_ARCHES["macos-native"] == {"x64", "arm64"}
    assert checker.WORKFLOW_ARCHES["linux-native"] == {"x86_64", "aarch64"}


def test_release_truth_checker_rejects_stale_default_linux_patterns() -> None:
    checker = _load_release_truth_checker()

    assert "remote-ops-workspace-v0.1.0-linux-<i386|amd64|armhf|arm64>.deb" in (
        checker.STALE_DEFAULT_ARTIFACT_SNIPPETS
    )
    assert "remote-ops-workspace-v0.1.0-linux-<amd64|arm64>.deb" in checker.REQUIRED_DOC_SNIPPETS


def _load_release_truth_checker():
    path = Path("scripts/check_release_truth.py")
    spec = importlib.util.spec_from_file_location("check_release_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
