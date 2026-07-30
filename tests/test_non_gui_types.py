from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_non_gui_type_gate_accepts_bounded_gui_debt() -> None:
    checker = _load_checker()
    output = "\n".join(
        [
            "src/remote_ops_workspace/gui.py:10: error: first [union-attr]",
            "src\\remote_ops_workspace\\gui.py:20: error: second [attr-defined]",
            "Found 2 errors in 1 file (checked 49 source files)",
        ]
    )

    assert checker.check_mypy_output(output, 1) == ([], 2)


def test_non_gui_type_gate_checks_each_modern_host_platform() -> None:
    checker = _load_checker()

    assert checker.MYPY_PLATFORMS == ("linux", "win32", "darwin")


def test_non_gui_type_gate_rejects_error_outside_gui() -> None:
    checker = _load_checker()
    output = "src/remote_ops_workspace/storage.py:10: error: unsafe type [arg-type]"

    errors, gui_errors = checker.check_mypy_output(output, 1)

    assert gui_errors == 0
    assert errors == ["non-GUI production type error reported in src/remote_ops_workspace/storage.py"]


def test_non_gui_type_gate_rejects_gui_regression() -> None:
    checker = _load_checker()
    output = "\n".join(
        f"src/remote_ops_workspace/gui.py:{index}: error: regression [union-attr]"
        for index in range(1, checker.GUI_ERROR_BASELINE + 2)
    )

    errors, gui_errors = checker.check_mypy_output(output, 1)

    assert gui_errors == checker.GUI_ERROR_BASELINE + 1
    assert errors == [
        "GUI type errors increased from the 382-error baseline to 383"
    ]


def test_non_gui_type_gate_rejects_unparseable_mypy_failure() -> None:
    checker = _load_checker()

    errors, gui_errors = checker.check_mypy_output("mypy: configuration failed", 2)

    assert gui_errors == 0
    assert errors == [
        "mypy execution failed with exit 2",
    ]


def test_non_gui_type_gate_accepts_fully_clean_source() -> None:
    checker = _load_checker()

    assert checker.check_mypy_output("Success: no issues found", 0) == ([], 0)


def _load_checker():
    path = Path("scripts/check_non_gui_types.py")
    spec = importlib.util.spec_from_file_location("check_non_gui_types", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
