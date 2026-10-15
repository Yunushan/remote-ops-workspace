"""Check the application-owner contract without importing or constructing Qt."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _selected_application_lookup():
    source = Path(__file__).resolve().parents[1] / "src/remote_ops_workspace/gui.py"
    module = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    factory = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "create_main_window"
    )
    selected = [
        node for node in factory.body
        if isinstance(node, ast.FunctionDef) and node.name == "_application_instance"
    ]
    assert len(selected) == 1
    namespace = {"QApplication": _Application}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_application_instance"]


class _Application:
    current = None
    queries = 0

    def __init__(self):
        raise AssertionError("the lookup must not create a replacement application")

    @classmethod
    def instance(cls):
        cls.queries += 1
        return cls.current


class _DerivedApplication(_Application):
    pass


class _CoreApplication:
    """A non-widget application is not a suitable owner for a GUI window."""


@pytest.mark.parametrize("current", [None, _CoreApplication(), object()], ids=[
    "missing-owner", "core-only-owner", "unrelated-owner",
])
def test_missing_or_wrong_application_owner_refuses_before_widget_use(current):
    lookup = _selected_application_lookup()
    _Application.current = current
    _Application.queries = 0

    with pytest.raises(RuntimeError) as refusal:
        lookup()

    assert str(refusal.value) == "required GUI value is unavailable: Qt application"
    assert _Application.current is current
    assert _Application.queries == 1


@pytest.mark.parametrize("owner_type", [_Application, _DerivedApplication], ids=[
    "existing-owner", "derived-existing-owner",
])
def test_existing_gui_application_owner_is_returned_without_replacement(owner_type):
    lookup = _selected_application_lookup()
    current = object.__new__(owner_type)
    _Application.current = current
    _Application.queries = 0

    assert lookup() is current
    assert _Application.current is current
    assert _Application.queries == 1
