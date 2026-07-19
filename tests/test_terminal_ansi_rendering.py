from __future__ import annotations

import pytest

from remote_ops_workspace.terminal import TerminalPanePlan

_CONPTY_INITIAL_SCREEN_FRAME = (
    "\x1b[?9001h\x1b[?1004h\x1b[?25l\x1b[2J\x1b[m\x1b[H"
    + "\r\n" * 24
    + "\x1b[H\x1b]0;C:\\Windows\\System32\\OpenSSH\\ssh.exe\x07\x1b[?25h"
)


@pytest.fixture
def terminal_pane(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["terminal-ansi-rendering"], show=False)
    pane = window.new_terminal_pane(
        TerminalPanePlan(title="ansi-render", command=[], source="test")
    )
    window.add_workspace_tab(pane, "ansi-render", role="terminal")
    window.resize(900, 600)
    window.show()
    app.processEvents()
    yield app, pane
    window.close()
    app.processEvents()


def _character_format(pane, position: int):
    from PyQt6.QtGui import QTextCursor

    cursor = pane.output.textCursor()
    cursor.setPosition(position)
    cursor.movePosition(
        QTextCursor.MoveOperation.NextCharacter,
        QTextCursor.MoveMode.KeepAnchor,
    )
    return cursor.charFormat()


def test_qt_terminal_renders_basic_256_rgb_bold_and_inverse_sgr(terminal_pane) -> None:
    _app, pane = terminal_pane

    pane.set_terminal_transcript(
        "plain "
        "\x1b[31mred\x1b[0m "
        "\x1b[1;4;38;5;46mbold\x1b[22;24;39m "
        "\x1b[48;2;1;2;3mback\x1b[0m "
        "\x1b[7minverse\x1b[0m"
    )

    assert pane.output.toPlainText() == "plain red bold back inverse"
    assert "\x1b" not in pane.output.toPlainText()
    assert _character_format(pane, 6).foreground().color().name() == "#cd3131"
    bold_format = _character_format(pane, 10)
    assert bold_format.foreground().color().name() == "#00ff00"
    assert bold_format.fontWeight() > 400
    assert bold_format.fontUnderline() is True
    assert _character_format(pane, 15).background().color().name() == "#010203"
    inverse_format = _character_format(pane, 20)
    from PyQt6.QtGui import QPalette

    palette = pane.output.palette()
    assert inverse_format.foreground().color().name() == palette.color(
        QPalette.ColorRole.Base
    ).name()
    assert inverse_format.background().color().name() == palette.color(
        QPalette.ColorRole.Text
    ).name()
    assert pane.output.property("terminalAnsiSgrColorEnabled") is True
    assert "rgb" in pane.output.property("terminalAnsiSgrCapabilities")


def test_explicit_ansi_color_wins_over_semantic_highlight(terminal_pane) -> None:
    _app, pane = terminal_pane

    pane.set_terminal_transcript("ready \x1b[31mready\x1b[0m")

    assert _character_format(pane, 0).foreground().color().name() == "#73d673"
    assert _character_format(pane, 6).foreground().color().name() == "#cd3131"

    # A carriage-return redraw can change only the style while leaving the
    # plain transcript identical.  The document format must still be refreshed.
    pane.set_terminal_transcript("same")
    pane.append_text("\r\x1b[31msame\x1b[0m")
    assert pane.output.toPlainText() == "same"
    assert _character_format(pane, 0).foreground().color().name() == "#cd3131"


def test_http_links_are_cyan_underlined_and_require_explicit_ctrl_click(
    terminal_pane,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QTextCursor
    from PyQt6.QtTest import QTest

    app, pane = terminal_pane
    href = "https://192.0.2.10:9090/"
    pane.set_terminal_transcript(f"Web console: {href}")

    link_start = pane.output.toPlainText().index(href)
    link_format = _character_format(pane, link_start)
    assert link_format.foreground().color().name() == "#54ccef"
    assert link_format.fontUnderline() is True
    assert link_format.isAnchor() is True
    assert link_format.anchorHref() == href
    assert pane.validated_terminal_link(href).toString() == href
    assert pane.validated_terminal_link("file:///etc/passwd") is None
    assert pane.validated_terminal_link("javascript:alert(1)") is None
    assert pane.output.property("terminalLinkAutoOpen") is False

    opened: list[str] = []

    def record_open(target: str) -> bool:
        opened.append(target)
        return True

    pane.open_terminal_link = record_open
    link_cursor = QTextCursor(pane.output.document())
    link_cursor.setPosition(link_start + 3)
    point = pane.output.cursorRect(link_cursor).center()
    QTest.mouseClick(
        pane.output.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        pos=point,
    )
    app.processEvents()

    assert opened == [href]


def test_stream_update_preserves_unchanged_multiline_selection(terminal_pane) -> None:
    from PyQt6.QtGui import QTextCursor

    app, pane = terminal_pane
    pane.set_terminal_transcript("alpha\nbeta\ngamma")
    cursor = pane.output.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
    pane.output.setTextCursor(cursor)

    pane.append_text("\ndelta")
    app.processEvents()

    selected = pane.output.textCursor()
    assert selected.hasSelection()
    assert selected.selectedText().replace("\u2029", "\n") == "alpha\nbeta"
    assert selected.anchor() == 0
    assert selected.position() == 10
    assert pane.output.property("terminalSelectionPreservedOnOutput") is True


def _arm_initial_pty_clear_recovery(pane) -> None:
    pane._pty_initial_clear_pending = True
    pane._pty_startup_probe = ""
    pane.output.setProperty("terminalInitialPtyClearRecoveryArmed", True)
    pane.output.setProperty("terminalInitialPtyClearNormalized", False)


def test_initial_conpty_clear_preserves_command_context_and_later_clear_works(
    terminal_pane,
) -> None:
    _app, pane = terminal_pane
    pane.plan = TerminalPanePlan(
        title="edge-prod",
        command=[
            "ssh.exe",
            "-tt",
            "-p",
            "22",
            "operator@edge-prod.example.invalid",
        ],
        source="test",
        notes=["strict host-key checks enabled"],
    )
    pane.startup_preamble = ""
    pane.show_launch_command = True
    context = pane.terminal_startup_context_text()
    pane.set_terminal_transcript(context)
    _arm_initial_pty_clear_recovery(pane)

    split_at = _CONPTY_INITIAL_SCREEN_FRAME.index("\x1b[2J") + 3
    pane.append_process_text(_CONPTY_INITIAL_SCREEN_FRAME[:split_at])
    pane.append_process_text(_CONPTY_INITIAL_SCREEN_FRAME[split_at:])

    output = pane.output.toPlainText()
    assert output == context
    assert output.startswith("$ ssh.exe -tt -p 22 operator@edge-prod.example.invalid")
    assert "[note] strict host-key checks enabled" in output
    assert "\x1b" not in output
    assert pane.output.property("terminalInitialPtyClearNormalized") is True
    assert pane.output.property("terminalInitialPtyClearRecoveryArmed") is False

    pane.append_process_text("before\n\x1b[2Jafter")
    assert pane.output.toPlainText() == "after"


def test_initial_conpty_clear_preserves_moba_preamble_without_command_echo(
    terminal_pane,
) -> None:
    _app, pane = terminal_pane
    pane.plan = TerminalPanePlan(
        title="edge-prod",
        command=["ssh.exe", "-tt", "operator@edge-prod.example.invalid"],
        source="test",
    )
    pane.set_terminal_transcript(f"$ {pane.plan.printable()}\n")
    pane.set_launch_command_echo_visible(False)
    pane.set_startup_preamble(
        "\n".join(
            [
                "* Remote Ops Workspace *",
                "> SSH session target: edge-prod.example.invalid:22",
                "> Waiting for authentication and server output.",
            ]
        )
    )
    context = pane.terminal_startup_context_text()
    _arm_initial_pty_clear_recovery(pane)

    pane.append_process_text(_CONPTY_INITIAL_SCREEN_FRAME)

    output = pane.output.toPlainText()
    assert output == context
    assert output.startswith("* Remote Ops Workspace *")
    assert "> Waiting for authentication and server output." in output
    assert "$ ssh.exe" not in output
    assert not output.startswith("\n")
    assert "\x1b" not in output
