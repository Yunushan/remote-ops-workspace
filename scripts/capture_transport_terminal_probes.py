"""Exercise the terminal surface over an already authenticated SSH shell."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from scripts.qt_release_capture import write_json

PEER_COMMAND = "/usr/local/bin/python /usr/local/lib/row-transport-peer.py"


def terminal_grid_geometry(emulator) -> tuple[int, int]:
    return emulator._screen_columns, emulator._screen_rows


def peer_observations(output, wait_for, stage: str, socket: str) -> dict:
    marker = f"ROW_PROBE_END_{stage}"
    wait_for(lambda: marker in output.toPlainText().splitlines(), f"{stage} peer receipts")
    lines = output.toPlainText().splitlines()
    body = []
    for line in reversed(lines[:lines.index(marker)]):
        if not line.strip():
            continue
        if not line.startswith("ROW_PROBE_"):
            break
        body.append(line.removeprefix("ROW_PROBE_").split("=", 1))
    if len({entry[0] for entry in body}) != len(body):
        raise ValueError(f"{stage} peer observations contain duplicate fields")
    rows = dict(body)
    if rows.pop("SOCKET", None) != socket:
        raise ValueError(f"{stage} changed SSH connections during the terminal probe")
    return {key: json.loads(value) for key, value in rows.items()}


def capture_grid(root: Path, window, pane, wait_for, submit, socket: str) -> dict:
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.terminal_emulation import SOFT_LINE_BREAK

    output, emulator = pane.output, pane.terminal_emulator
    initial_size = terminal_grid_geometry(emulator)
    current = window.size()
    submit(f"{PEER_COMMAND} grid")

    def grid_line() -> str:
        return emulator.text().partition("ROW_GRID_")[2].split("\n", 1)[0]

    wait_for(lambda: f"{SOFT_LINE_BREAK}界\u0301z" in grid_line(), "Unicode cell wrapping")
    if not emulator.primary_reflow or emulator.cursor_display_position() != (1, 3):
        raise ValueError("the native terminal did not address the expected cells on a wrapped Unicode row")
    initial_line = grid_line()
    write_json(root / "initial-screen.json", {
        "geometry": list(initial_size), "line": initial_line, "cell_cursor": [1, 3],
    })
    window.resize(current.width() + 220, current.height())
    wait_for(lambda: terminal_grid_geometry(emulator)[0] > initial_size[0]
             and SOFT_LINE_BREAK not in grid_line(), "primary-screen reflow at wider viewport")
    resized = terminal_grid_geometry(emulator)
    updated_line = grid_line()
    if not updated_line or initial_line.replace(SOFT_LINE_BREAK, "") != updated_line:
        raise ValueError("the terminal grid changed logical text during reflow")
    QTest.qWait(150)
    QTest.keyClicks(output, "r")
    wait_for(lambda: emulator.alternate_screen_active
             and "outside-bottom" in output.toPlainText(), "bounded scroll region")
    rows = output.toPlainText().splitlines()[:5]
    if rows != ["outside-top", "three", "four", "", "outside-bottom"]:
        raise ValueError(f"scroll region changed rows outside its bounds: {rows}")

    document = output.document()
    unchanged, changed = (document.findBlockByNumber(index) for index in (0, 2))
    unchanged.setUserState(33)
    events: list[list[int]] = []

    def update(position: int, removed: int, inserted: int) -> None:
        events.append([position, removed, inserted])

    document.contentsChange.connect(update)
    try:
        QTest.keyClicks(output, "g")
        wait_for(lambda: changed.begin().fragment().charFormat().foreground().color().name() == "#0dbc79",
                 "style-only dirty row")
        if events != [[changed.position(), 4, 4]] or unchanged.userState() != 33:
            raise ValueError(f"the terminal redrew rows outside the style-only patch: {events}")
    finally:
        document.contentsChange.disconnect(update)
    QTest.keyClicks(output, "q")
    observed = peer_observations(output, wait_for, "grid", socket)
    if observed != {"initial": list(initial_size), "resized": list(resized), "cursor_reply": "1b5b323b3452"}:
        raise ValueError(f"the remote PTY dimensions or cursor reply differ from the desktop: {observed}")
    write_json(root / "updated-screen.json", {
        "geometry": list(resized), "line": updated_line, "remote": observed,
        "dirty_update": events[0], "scroll_region": rows, "ssh_connection": socket,
    })
    return {"initial": list(initial_size), "resized": list(resized), "dirty_row_updates": len(events)}


def capture_vim(root: Path, window, pane, wait_for, submit, socket: str) -> dict:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    output, emulator = pane.output, pane.terminal_emulator
    original = window.size()
    initial_size = terminal_grid_geometry(emulator)
    submit(f"{PEER_COMMAND} vim")
    wait_for(lambda: "ROW_PRIMARY_界_e\u0301" in output.toPlainText()
             and output.property("terminalRemoteCursorShape") == "underline", "initial primary screen")
    before = output.toPlainText()
    write_json(root / "primary-before.json", {"geometry": list(initial_size), "text": before})
    QTest.keyClicks(output, "v")
    wait_for(lambda: emulator.alternate_screen_active and "opening fixture: café" in output.toPlainText(),
             "real Vim alternate screen")
    alternate = output.toPlainText()
    window.resize(original.width() - 200, original.height() - 140)
    wait_for(lambda: terminal_grid_geometry(emulator) != initial_size
             and "opening fixture: café" in output.toPlainText(), "Vim resize")
    resized = terminal_grid_geometry(emulator)
    resized_text = output.toPlainText()
    QTest.keyClicks(output, "i")
    wait_for(lambda: "-- INSERT --" in output.toPlainText()
             and output.property("terminalRemoteCursorShape") == "bar", "Vim insert cursor")
    insert_text = output.toPlainText()
    QTest.keyClick(output, Qt.Key.Key_Escape)
    wait_for(lambda: output.property("terminalRemoteCursorShape") == "block", "Vim normal cursor")
    window.resize(original)
    wait_for(lambda: terminal_grid_geometry(emulator) == initial_size and emulator.alternate_screen_active,
             "return to initial Vim viewport")
    submit(":q!")
    wait_for(lambda: not emulator.alternate_screen_active and output.toPlainText() == before
             and output.property("terminalRemoteCursorShape") == "underline", "primary-screen restoration")
    write_json(root / "primary-restored.json", {"geometry": list(initial_size), "text": output.toPlainText()})
    QTest.keyClicks(output, "b")
    observed = peer_observations(output, wait_for, "vim", socket)
    if observed != {"shell_input": "62"}:
        raise ValueError(f"the peer did not receive input after Vim exited: {observed}")
    write_json(root / "alternate-screen.json", {
        "application": "vim", "text": alternate, "geometry": list(initial_size), "resized": list(resized),
        "resized_text": resized_text, "insert_text": insert_text,
        "cursor_modes": ["bar", "block"], "remote": observed, "ssh_connection": socket,
    })
    return {"application": "vim", "primary_restored": True, "shell_input_resumed": True}


def capture_modes(root: Path, app, pane, wait_for, submit, socket: str) -> dict:
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from PyQt6.QtTest import QTest

    output, viewport, emulator = pane.output, pane.output_viewport, pane.terminal_emulator
    submit(f"{PEER_COMMAND} modes")
    wait_for(lambda: "ROW_MODES_READY" in output.toPlainText()
             and output.property("terminalSgrMouseTrackingMode") == 1000, "terminal mode negotiation")
    if (
        not emulator.bracketed_paste_active or not emulator.alternate_screen_active
        or output.property("terminalRemoteCursorVisible") is not False
        or output.property("terminalRemoteCursorShape") != "bar"
    ):
        raise ValueError("the negotiated paste, mouse and cursor modes are not active")
    styles = [asdict(styles[0]) for _, styles in emulator.styled_alternate_rows()[:3]]
    if (
        [style["foreground"] for style in styles] != ["#cd3131", "#ff0000", "#0c2238"]
        or not styles[0]["bold"] or not styles[0]["underline"]
    ):
        raise ValueError(f"invalid ANSI, indexed or truecolor rendering: {styles}")
    QTest.keyClick(output, Qt.Key.Key_Up)
    app.clipboard().setText("paste-from-desktop")
    pane.paste_to_terminal()
    offset = output.document().documentMargin() + 1
    first = QPointF(offset, offset)
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=first.toPoint())
    event = QWheelEvent(first, first, QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(viewport, event)
    wait_for(lambda: "ROW_MOUSE_OFF" in output.toPlainText()
             and output.property("terminalSgrMouseTrackingMode") == 0, "mouse mode disabled remotely")
    if emulator.bracketed_paste_active or output.property("terminalRemoteCursorVisible") is not True:
        raise ValueError("the terminal did not restore local mouse, paste and cursor behavior")
    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=first.toPoint())
    QTest.keyClicks(output, "x")
    observed = peer_observations(output, wait_for, "modes", socket)
    write_json(root / "mode-capture.json", {
        "remote": observed, "styles": styles, "cursor_visibility": [False, True], "ssh_connection": socket,
    })
    return {"remote_mode_observations": len(observed), "color_modes": len(styles)}
