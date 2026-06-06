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

    assert "remote-ops-workspace-v1.0.2-linux-<i386|amd64|armhf|arm64>.deb" in (
        checker.STALE_DEFAULT_ARTIFACT_SNIPPETS
    )
    assert "remote-ops-workspace-v1.0.2-linux-<amd64|arm64>.deb" in checker.REQUIRED_DOC_SNIPPETS


def test_release_truth_checker_requires_release_preflight_job() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "  release-preflight:",
        "  release_preflight_disabled:",
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow missing release-preflight job" in errors


def test_release_truth_checker_requires_node24_javascript_action_runtime() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow must opt JavaScript actions into Node.js 24" in errors


def test_release_truth_checker_rejects_insecure_node_runtime_opt_out() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8") + (
        "\nenv:\n  ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION: true\n"
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow must not opt JavaScript actions into an insecure Node.js runtime" in errors


def test_release_truth_checker_requires_build_jobs_to_need_preflight() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "  source-and-python:\n    needs: release-preflight\n",
        "  source-and-python:\n",
    )

    errors = checker.check_release_preflight(workflow)

    assert "source-and-python must depend on release-preflight" in errors


def test_release_truth_checker_requires_preflight_cleanup_command() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_repository_cleanup.py --require-clean",
        "python scripts/check_repository_cleanup.py",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("clean checkout requirement" in error for error in errors)


def _load_release_truth_checker():
    path = Path("scripts/check_release_truth.py")
    spec = importlib.util.spec_from_file_location("check_release_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
