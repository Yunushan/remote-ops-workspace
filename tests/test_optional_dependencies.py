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
    assert checker.OPTIONAL_MODULES["desktop"] == ("PyQt6",)
    assert checker.OPTIONAL_MODULES["security"] == ("cryptography", "truststore")
    assert checker.OPTIONAL_MODULES["package"] == ("build", "PyInstaller")


def test_optional_desktop_smoke_uses_bounded_render_subprocess(monkeypatch, tmp_path: Path) -> None:
    checker = _load_optional_checker()
    calls: dict[str, object] = {}

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
    assert calls["env"]["QT_QPA_PLATFORM"] == "offscreen"


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
