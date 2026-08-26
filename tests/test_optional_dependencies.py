from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_optional_dependency_checker_passes_current_environment(monkeypatch) -> None:
    checker = _load_optional_checker()
    monkeypatch.setattr(
        checker,
        "check_desktop_gui",
        lambda tmp_path: ([], ["desktop/PyQt6 bounded live render smoke passed for native preset"]),
    )

    assert checker.main([]) == 0


def test_optional_dependency_declarations_match_expected_extras() -> None:
    checker = _load_optional_checker()

    assert checker.check_declared_extras() == []
    assert checker.EXPECTED_EXTRA_SNIPPETS["package"] == (
        '"build>=1.2"',
        '"pyinstaller>=6.21"',
    )
    assert checker.OPTIONAL_MODULES["desktop"] == ("PyQt6",)
    assert checker.OPTIONAL_MODULES["security"] == ("bcrypt", "cryptography", "truststore")
    assert checker.OPTIONAL_MODULES["package"] == ("build", "PyInstaller")
    assert "legacy-security" not in checker.EXPECTED_EXTRA_SNIPPETS


def test_optional_dependency_checker_rejects_pre_python315_pyinstaller_floor() -> None:
    checker = _load_optional_checker()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").replace(
        '"pyinstaller>=6.21"',
        '"pyinstaller>=6.0"',
        1,
    )

    errors = checker.check_declared_extras(pyproject)

    assert (
        'pyproject.toml optional extra package missing dependency "pyinstaller>=6.21"'
        in errors
    )


def test_optional_dependency_checker_rejects_pre_python315_pyqt_floor() -> None:
    checker = _load_optional_checker()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").replace(
        '"PyQt6>=6.11.0"',
        '"PyQt6>=6.6"',
        1,
    )

    errors = checker.check_declared_extras(pyproject)

    assert (
        'pyproject.toml optional extra desktop missing dependency "PyQt6>=6.11.0"'
        in errors
    )


def test_optional_dependency_checker_rejects_vulnerable_legacy_security_extra() -> None:
    checker = _load_optional_checker()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    pyproject += (
        "\nlegacy-security = "
        '["cryptography==48.0.1", "truststore>=0.10"]\n'
    )

    errors = checker.check_declared_extras(pyproject)

    assert "pyproject.toml must not declare the vulnerable legacy-security extra" in errors
    assert "pyproject.toml must not declare the known-vulnerable cryptography 48.0.1 pin" in errors


def test_optional_desktop_smoke_uses_bounded_render_subprocess(monkeypatch, tmp_path: Path) -> None:
    checker = _load_optional_checker()
    calls: dict[str, object] = {}
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    class FakeCompletedProcess:
        returncode = 0
        stdout = "real GUI render check passed\n"
        stderr = ""

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["timeout"] = kwargs["timeout"]
        calls["env"] = kwargs["env"]
        return FakeCompletedProcess()

    monkeypatch.setattr(checker, "module_available", lambda module: module == "PyQt6")
    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    errors, messages = checker.check_desktop_gui(tmp_path, render_timeout_seconds=7)

    assert errors == []
    assert messages == ["desktop/PyQt6 bounded live render smoke passed for native preset"]
    assert calls["timeout"] == 22
    assert "--timeout-seconds" in calls["command"]
    assert "7" in calls["command"]
    assert calls["env"]["QT_QPA_PLATFORM"] == checker.desktop_gui_qt_platform()
    if checker.desktop_gui_qt_scale_factor() is not None:
        assert calls["env"]["QT_SCALE_FACTOR"] == "1"


def test_optional_desktop_smoke_uses_native_windows_and_headless_non_windows_backends() -> None:
    checker = _load_optional_checker()

    assert checker.desktop_gui_qt_platform("win32") == "windows"
    assert checker.desktop_gui_qt_platform("linux") == "offscreen"
    assert checker.desktop_gui_qt_platform("darwin") == "offscreen"
    assert checker.desktop_gui_qt_scale_factor("win32") == "1"
    assert checker.desktop_gui_qt_scale_factor("linux") is None


def test_optional_desktop_smoke_reports_subprocess_timeout(monkeypatch, tmp_path: Path) -> None:
    checker = _load_optional_checker()

    def fake_run(_command, **_kwargs):
        raise checker.subprocess.TimeoutExpired(cmd="check_real_gui_render.py", timeout=22)

    monkeypatch.setattr(checker, "module_available", lambda module: module == "PyQt6")
    monkeypatch.setattr(checker.subprocess, "run", fake_run)

    errors, messages = checker.check_desktop_gui(tmp_path, render_timeout_seconds=7)

    assert errors == ["desktop/PyQt6 live render smoke exceeded 22 seconds"]
    assert messages == []


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
