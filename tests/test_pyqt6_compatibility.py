from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def test_pyqt6_policy_records_612_forward_target() -> None:
    checker = _load_checker()

    policy = checker.load_policy()

    assert policy.minimum_version == (6, 11, 0)
    assert policy.target_version == (6, 12, 0)
    assert policy.maximum_version_exclusive == (7, 0, 0)


def test_pyqt6_version_parser_accepts_prerelease_prefix() -> None:
    checker = _load_checker()

    assert checker.parse_version("v6.12.0.dev2") == (6, 12, 0)
    assert checker.parse_version("6.11") == (6, 11, 0)


def test_pyqt6_version_parser_rejects_non_version() -> None:
    checker = _load_checker()

    with pytest.raises(ValueError, match="major.minor"):
        checker.parse_version("not-a-version")


def test_pyqt6_target_must_stay_inside_supported_range() -> None:
    checker = _load_checker()
    policy = checker.load_policy()

    assert checker.validate_target_version(policy, (6, 10, 0))
    assert checker.validate_target_version(policy, (7, 0, 0))
    assert checker.validate_target_version(policy, (6, 12, 0)) == []


def test_pyqt6_runtime_accepts_current_minimum_and_defers_target() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.11.0",
        binding_version="6.11.0",
        qt_distribution_version="6.11.2",
        qt_version="6.11.0",
        sip_distribution_version="13.12.0",
    )

    assert checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=False,
    ) == []


def test_pyqt6_runtime_rejects_mismatched_binding_and_qt() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.12.0",
        binding_version="6.11.0",
        qt_distribution_version="6.12.0",
        qt_version="6.11.0",
        sip_distribution_version="13.12.0",
    )

    errors = checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=True,
    )

    assert any("distribution and imported binding" in error for error in errors)
    assert any("distribution and imported Qt" in error for error in errors)
    assert any("requires the PyQt6 and Qt distributions" in error for error in errors)


def test_pyqt6_runtime_rejects_mixed_binding_and_qt_generations() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.12.0",
        binding_version="6.12.0",
        qt_distribution_version="6.11.2",
        qt_version="6.11.0",
        sip_distribution_version="13.13.0",
    )

    errors = checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=False,
    )

    assert any("binding and bundled Qt runtime" in error for error in errors)
    assert any("requires the binding and Qt runtime to advance together" in error for error in errors)


def test_pyqt6_runtime_rejects_newer_line_without_target_coverage() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.13.0",
        binding_version="6.13.0",
        qt_distribution_version="6.13.1",
        qt_version="6.13.0",
        sip_distribution_version="13.13.0",
    )

    errors = checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=False,
    )

    assert any("newer than that target line" in error for error in errors)


def test_pyqt6_runtime_requires_target_when_requested() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.11.0",
        binding_version="6.11.0",
        qt_distribution_version="6.11.2",
        qt_version="6.11.0",
        sip_distribution_version="13.12.0",
    )

    errors = checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=True,
    )

    assert errors == [
        "PyQt6 target 6.12.0 requires the PyQt6 and Qt distributions plus imported runtimes "
        "to meet that version; installed PyQt6=6.11.0, binding=6.11.0, "
        "PyQt6-Qt6=6.11.2, Qt=6.11.0"
    ]


def test_pyqt6_check_runtime_reports_deferred_target(monkeypatch) -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.11.0",
        binding_version="6.11.0",
        qt_distribution_version="6.11.2",
        qt_version="6.11.0",
        sip_distribution_version="13.12.0",
    )
    monkeypatch.setattr(checker, "probe_runtime", lambda: runtime)
    monkeypatch.setattr(checker, "run_qt_widget_smoke", lambda: None)

    errors, messages = checker.check_runtime(
        checker.load_policy(),
        target_version=(6, 12, 0),
        require_pyqt6=True,
        require_target=False,
    )

    assert errors == []
    assert any("validation is deferred" in message for message in messages)


def test_pyqt6_check_runtime_accepts_target(monkeypatch) -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.12.0",
        binding_version="6.12.0",
        qt_distribution_version="6.12.0",
        qt_version="6.12.0",
        sip_distribution_version="13.13.0",
    )
    monkeypatch.setattr(checker, "probe_runtime", lambda: runtime)
    monkeypatch.setattr(checker, "run_qt_widget_smoke", lambda: None)

    errors, messages = checker.check_runtime(
        checker.load_policy(),
        target_version=(6, 12, 0),
        require_pyqt6=True,
        require_target=True,
    )

    assert errors == []
    assert messages == ["PyQt6 6.12.0 and Qt 6.12.0 satisfy the 6.12.0 target"]


def test_pyqt6_strict_target_requires_distribution_versions_too() -> None:
    checker = _load_checker()
    runtime = checker.PyQt6Runtime(
        distribution_version="6.11.0",
        binding_version="6.12.0",
        qt_distribution_version="6.11.2",
        qt_version="6.12.0",
        sip_distribution_version="13.13.0",
    )

    errors = checker.validate_runtime(
        runtime,
        checker.load_policy(),
        (6, 12, 0),
        require_target=True,
    )

    assert any("PyQt6 and Qt distributions plus imported runtimes" in error for error in errors)


def test_pyqt6_check_runtime_allows_missing_dependency_only_without_requirement(monkeypatch) -> None:
    checker = _load_checker()

    def missing_runtime():
        raise RuntimeError("missing distributions: PyQt6")

    monkeypatch.setattr(checker, "probe_runtime", missing_runtime)

    errors, messages = checker.check_runtime(
        checker.load_policy(),
        target_version=(6, 12, 0),
        require_pyqt6=False,
        require_target=False,
        run_widget_smoke=False,
    )
    assert errors == []
    assert any("check deferred" in message for message in messages)

    errors, messages = checker.check_runtime(
        checker.load_policy(),
        target_version=(6, 12, 0),
        require_pyqt6=True,
        require_target=False,
        run_widget_smoke=False,
    )
    assert messages == []
    assert errors == ["PyQt6 runtime is required but unavailable: missing distributions: PyQt6"]


def test_pyqt6_check_runtime_reports_platform_loader_errors(monkeypatch) -> None:
    checker = _load_checker()

    def broken_runtime():
        raise OSError("Qt platform plugin could not be loaded")

    monkeypatch.setattr(checker, "probe_runtime", broken_runtime)

    errors, messages = checker.check_runtime(
        checker.load_policy(),
        target_version=(6, 12, 0),
        require_pyqt6=True,
        require_target=False,
        run_widget_smoke=False,
    )

    assert messages == []
    assert errors == [
        "PyQt6 runtime is required but unavailable: Qt platform plugin could not be loaded"
    ]


def _load_checker():
    path = Path("scripts/check_pyqt6_compatibility.py")
    spec = importlib.util.spec_from_file_location("check_pyqt6_compatibility_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
