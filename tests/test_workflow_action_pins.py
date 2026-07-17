from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_workflow_action_pins_cover_checked_in_workflows() -> None:
    checker = _load_checker()

    assert checker.check_workflow_action_pins() == []


def test_workflow_action_pins_reject_floating_action_tags() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    floating = workflow.replace(
        f"actions/checkout@{checker.ACTION_PINS['actions/checkout']}",
        "actions/checkout@v6",
        1,
    )

    errors = checker.check_workflow_action_pins({"ci.yml": floating})

    assert any("ci.yml must pin actions/checkout@" in error for error in errors)


def test_workflow_action_pins_reject_unapproved_actions() -> None:
    checker = _load_checker()

    errors = checker.check_workflow_action_pins(
        {"example.yml": "jobs:\n  test:\n    steps:\n      - uses: owner/action@0123456789abcdef0123456789abcdef01234567\n"}
    )

    assert errors == [
        "example.yml uses unapproved action owner/action; add an explicitly reviewed immutable pin"
    ]


def _load_checker():
    path = Path("scripts/check_workflow_action_pins.py")
    spec = importlib.util.spec_from_file_location("workflow_action_pins", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
