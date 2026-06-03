from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_optional_dependency_checker_passes_current_environment() -> None:
    checker = _load_optional_checker()

    assert checker.main([]) == 0


def test_optional_dependency_declarations_match_expected_extras() -> None:
    checker = _load_optional_checker()

    assert checker.check_declared_extras() == []
    assert checker.OPTIONAL_MODULES["desktop"] == ("PyQt6",)
    assert checker.OPTIONAL_MODULES["security"] == ("cryptography",)
    assert checker.OPTIONAL_MODULES["package"] == ("build", "PyInstaller")


def test_optional_desktop_smoke_exercises_real_or_fail_closed_path(tmp_path: Path) -> None:
    checker = _load_optional_checker()

    errors, messages = checker.check_desktop_gui(tmp_path)

    assert errors == []
    assert any("desktop/PyQt6" in message for message in messages)


def test_optional_security_smoke_exercises_real_or_fail_closed_path(tmp_path: Path) -> None:
    checker = _load_optional_checker()

    errors, messages = checker.check_security_vault(tmp_path)

    assert errors == []
    assert any("security/cryptography" in message for message in messages)


def test_required_extra_reports_missing_modules_without_network() -> None:
    checker = _load_optional_checker()

    errors, _messages = checker.check_optional_modules(["desktop", "package"])

    for error in errors:
        assert "missing modules" in error


def _load_optional_checker():
    path = Path("scripts/check_optional_dependencies.py")
    spec = importlib.util.spec_from_file_location("check_optional_dependencies_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
