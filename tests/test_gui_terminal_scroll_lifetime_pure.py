from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_selected_methods():
    """Execute only actual selected methods, with explicit Qt/value mocks."""

    source_path = Path(__file__).resolve().parents[1] / "src/remote_ops_workspace/gui_terminal.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    pane = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "TerminalPane")
    methods = {node.name: node for node in pane.body if isinstance(node, ast.FunctionDef)}
    selected = [copy.deepcopy(methods[name]) for name in (
        "scroll_terminal_to_end", "settle_terminal_scroll", "prepare_for_close", "_set_terminal_scroll_value",
    )]
    initialization = []
    for statement in methods["__init__"].body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
            and target.value.id == "self" and target.attr in {
                "_terminal_scroll_generation", "_terminal_scroll_settle_generation",
                "_terminal_scroll_closed", "_terminal_scroll_timer",
            }
            for target in statement.targets
        ):
            initialization.append(copy.deepcopy(statement))
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            owner = statement.value.func
            if isinstance(owner, ast.Attribute) and (
                isinstance(owner.value, ast.Attribute) and owner.value.attr == "_terminal_scroll_timer"
                or isinstance(owner.value, ast.Attribute) and owner.value.attr == "timeout"
                and isinstance(owner.value.value, ast.Attribute) and owner.value.value.attr == "_terminal_scroll_timer"
            ):
                initialization.append(copy.deepcopy(statement))
    assert len(initialization) == 6
    initializer = ast.parse("def initialize_scroll(self):\n    pass\n").body[0]
    initializer.body = initialization
    selected.append(initializer)
    implementation = ast.Module(body=[ast.ClassDef(
        name="SelectedPane", bases=[], keywords=[], body=selected, decorator_list=[],
    )], type_ignores=[])
    ast.fix_missing_locations(implementation)
    namespace = {
        "QTimer": _Timer,
        "QTextCursor": SimpleNamespace(MoveOperation=SimpleNamespace(End="document-end")),
        "_required_gui_value": lambda value, _description: value,
    }
    exec(compile(implementation, str(source_path), "exec"), namespace)
    return namespace["SelectedPane"]


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        assert self.callback is None
        self.callback = callback


class _Timer:
    """Scheduling mock; actual QObject destruction is tested only on hosts."""

    def __init__(self, parent):
        self.owner = parent
        self.single_shot = False
        self.timeout = _Signal()
        self.active = False
        self.starts = []
        self.stops = 0

    def setSingleShot(self, value):  # noqa: N802
        self.single_shot = value

    def start(self, interval):
        self.starts.append(interval)
        self.active = True

    def stop(self):
        self.stops += 1
        self.active = False

    def fire(self):
        assert self.active
        self.active = False
        self.timeout.callback()


class _Bar:
    def __init__(self, output):
        self.output = output
        self.limit = 50
        self.value = 0

    def maximum(self):
        self.output.touch("maximum")
        return self.limit

    def setValue(self, value):  # noqa: N802
        self.output.touch("set-value")
        self.value = value


class _Output:
    def __init__(self):
        self.calls = []
        self.fail_call = None
        self.deleted = False
        self.bar = _Bar(self)
        self.properties = {}

    def touch(self, call):
        if self.deleted or self.fail_call == call:
            raise RuntimeError("mock native access refused")
        self.calls.append(call)

    def verticalScrollBar(self):  # noqa: N802
        self.touch("bar")
        return self.bar

    def moveCursor(self, operation):  # noqa: N802
        self.touch("move-cursor")
        assert operation == "document-end"

    def ensureCursorVisible(self):  # noqa: N802
        self.touch("ensure-visible")

    def setProperty(self, key, value):  # noqa: N802
        self.touch("property")
        self.properties[key] = value


def _pane():
    pane = _load_selected_methods()()
    pane.initialize_scroll()
    pane.output = _Output()
    pane.terminal_emulator = SimpleNamespace(alternate_screen_active=False)
    pane._terminal_follow_output = True
    pane._terminal_force_follow_output = False
    pane._terminal_scroll_programmatic = 0
    pane._stop_timer = _Timer(pane)
    pane._restart_when_output_drained = True
    pane._restart_after_stop = True
    pane.cleanup_observations = []

    def set_property(key, value):
        pane.cleanup_observations.append((
            key, value, pane._terminal_scroll_closed,
            pane._terminal_scroll_timer.active, pane._terminal_scroll_generation,
        ))

    pane.setProperty = set_property
    pane.reset_process_output_pipeline = lambda: pane.cleanup_observations.append("pipeline-reset")
    return pane


def test_owned_timer_initialization_uses_actual_constructor_statements():
    pane = _pane()
    timer = pane._terminal_scroll_timer
    assert timer.owner is pane
    assert timer.single_shot is True
    assert timer.timeout.callback.__self__ is pane
    assert timer.timeout.callback.__func__ is type(pane).settle_terminal_scroll
    assert pane._terminal_scroll_closed is False


def test_open_scroll_settles_again_after_layout_changes():
    pane = _pane()
    pane.scroll_terminal_to_end()
    assert pane.output.bar.value == 50
    assert pane.output.properties == {"terminalFollowOutput": True}
    assert pane.output.calls.count("ensure-visible") == 1
    assert pane._terminal_scroll_timer.starts == [0]
    pane.output.bar.limit = 80
    pane._terminal_scroll_timer.fire()
    assert pane.output.bar.value == 80
    assert pane.output.calls.count("ensure-visible") == 2
    assert pane._terminal_scroll_programmatic == 0


def test_repeated_scroll_keeps_only_latest_generation_pending():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane.scroll_terminal_to_end()
    assert pane._terminal_scroll_generation == 2
    assert pane._terminal_scroll_settle_generation == 2
    assert pane._terminal_scroll_timer.starts == [0, 0]
    pane.output.bar.limit = 90
    pane._terminal_scroll_timer.fire()
    assert pane.output.bar.value == 90
    assert pane.output.calls.count("ensure-visible") == 3


@pytest.mark.parametrize("guard", ["closed", "generation", "alternate", "follow"])
def test_late_settle_refuses_before_any_native_access(guard):
    pane = _pane()
    pane.scroll_terminal_to_end()
    if guard == "closed":
        pane._terminal_scroll_closed = True
    elif guard == "generation":
        pane._terminal_scroll_generation += 1
    elif guard == "alternate":
        pane.terminal_emulator.alternate_screen_active = True
    else:
        pane._terminal_follow_output = False
    pane.output.deleted = True
    pane._terminal_scroll_timer.fire()


def test_closed_scroll_short_circuits_without_other_attributes_or_timer():
    pane = _load_selected_methods()()
    pane._terminal_scroll_closed = True
    pane.scroll_terminal_to_end()
    pane.settle_terminal_scroll()


def test_alternate_screen_keeps_viewport_and_invalidates_pending_settle():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane.terminal_emulator.alternate_screen_active = True
    pane._terminal_force_follow_output = True
    pane.scroll_terminal_to_end()
    assert pane.output.bar.value == 0
    assert pane._terminal_scroll_generation == 2
    assert pane._terminal_scroll_settle_generation == 1
    assert pane._terminal_follow_output is False
    assert pane._terminal_force_follow_output is False
    assert pane.output.properties["terminalFollowOutput"] is False
    pane.output.deleted = True
    pane._terminal_scroll_timer.fire()


def test_prepare_closes_stops_and_invalidates_before_native_cleanup():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane._stop_timer.start(60_000)
    pane.prepare_for_close()
    assert pane.cleanup_observations == [
        ("terminalClosing", True, True, False, 2), "pipeline-reset",
    ]
    assert pane._terminal_scroll_timer.stops == 1
    assert pane._stop_timer.active is False
    assert pane._restart_when_output_drained is False
    assert pane._restart_after_stop is False
    pane.output.deleted = True
    pane.settle_terminal_scroll()


def test_repeated_prepare_remains_closed_and_stopped():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane.prepare_for_close()
    pane.prepare_for_close()
    assert pane._terminal_scroll_generation == 3
    assert pane._terminal_scroll_timer.stops == 2
    assert pane._terminal_scroll_timer.active is False
    assert pane._terminal_scroll_closed is True


def test_closing_one_pane_preserves_other_pending_scroll():
    first, second = _pane(), _pane()
    first.scroll_terminal_to_end()
    second.scroll_terminal_to_end()
    first.prepare_for_close()
    first.output.deleted = True
    first.settle_terminal_scroll()
    second.output.bar.limit = 120
    second._terminal_scroll_timer.fire()
    assert first._terminal_scroll_timer is not second._terminal_scroll_timer
    assert second.output.bar.value == 120
    assert second._terminal_scroll_closed is False
    assert second._terminal_follow_output is True


@pytest.mark.parametrize("failure", ["bar", "set-value", "ensure-visible"])
def test_callback_native_failure_is_propagated_with_counter_restored(failure):
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane.output.fail_call = failure
    with pytest.raises(RuntimeError, match="mock native access refused"):
        pane._terminal_scroll_timer.fire()
    assert pane._terminal_scroll_programmatic == 0


def test_settle_preserves_existing_programmatic_depth():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane._terminal_scroll_programmatic = 3
    pane._terminal_scroll_timer.fire()
    assert pane._terminal_scroll_programmatic == 3


def test_prepared_pane_cannot_queue_another_scroll():
    pane = _pane()
    pane.scroll_terminal_to_end()
    pane.prepare_for_close()
    pane.output.deleted = True
    pane.scroll_terminal_to_end()
    assert pane._terminal_scroll_timer.starts == [0]
    assert pane._terminal_scroll_timer.active is False
