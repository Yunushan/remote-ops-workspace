import importlib.util
from pathlib import Path


def test_native_release_hardening_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_native_hardening_checker_tracks_native_jobs() -> None:
    checker = _load_checker()

    assert checker.WORKFLOW_NATIVE_JOBS == ("windows-native", "macos-native", "linux-native")
    assert set(checker.NATIVE_SCRIPTS) == {"windows", "macos", "linux"}


def test_native_checksum_patterns_are_documented_in_scripts() -> None:
    checker = _load_checker()

    for platform, pattern in checker.CHECKSUM_PATTERNS.items():
        text = checker.NATIVE_SCRIPTS[platform].read_text(encoding="utf-8")
        assert pattern in text


def test_native_pyinstaller_entrypoints_use_launchers() -> None:
    checker = _load_checker()

    assert checker.check_pyinstaller_launchers() == []
    for platform in ("windows", "linux"):
        text = checker.NATIVE_SCRIPTS[platform].read_text(encoding="utf-8")
        assert "row_launcher.py" in text
        assert "__main__.py" not in text


def test_native_workflow_uploads_fail_if_assets_missing() -> None:
    checker = _load_checker()

    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    for job in checker.WORKFLOW_NATIVE_JOBS:
        block = checker.workflow_job_block(workflow, job)
        assert "if-no-files-found: error" in block
        assert "persist-credentials: false" in block


def _load_checker():
    path = Path("scripts/check_native_release_hardening.py")
    spec = importlib.util.spec_from_file_location("check_native_release_hardening_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
