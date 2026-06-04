import importlib.util
import sys
from pathlib import Path


def load_cleanup_checker():
    path = Path("scripts/check_repository_cleanup.py")
    spec = importlib.util.spec_from_file_location("check_repository_cleanup", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_repository_cleanup.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_repository_cleanup"] = module
    spec.loader.exec_module(module)
    return module


def test_repository_cleanup_checker_passes_current_tree() -> None:
    checker = load_cleanup_checker()
    assert checker.main([]) == 0


def test_conflict_marker_detection_reports_text_files(tmp_path: Path) -> None:
    checker = load_cleanup_checker()
    bad = tmp_path / "bad.py"
    bad.write_text("<<<<<<< HEAD\nprint('left')\n>>>>>>> branch\n", encoding="utf-8")

    errors = checker.check_conflict_markers(tmp_path, ["bad.py"])

    assert "bad.py:1 contains a merge conflict marker" in errors
    assert "bad.py:3 contains a merge conflict marker" in errors


def test_private_artifact_matcher_catches_sensitive_filenames() -> None:
    checker = load_cleanup_checker()

    assert checker.is_private_artifact("profiles.json")
    assert checker.is_private_artifact("ops/vault.json")
    assert checker.is_private_artifact("support-bundle-20260604.zip")
    assert checker.is_private_artifact("keys/id_ed25519.pem")
    assert not checker.is_private_artifact("configs/profiles.example.json")
    assert not checker.is_private_artifact("docs/SECURITY_MODEL.md")
