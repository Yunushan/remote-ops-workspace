import pytest

from remote_ops_workspace.terminal_emulation import (
    TERMINAL_EMULATOR_BACKEND,
    AnsiTerminalTranscript,
)


def test_ansi_transcript_rewrites_carriage_return_progress_and_backspaces() -> None:
    terminal = AnsiTerminalTranscript()

    assert terminal.feed("download 10%\rdownload 42%") == "download 42%"
    assert terminal.feed("\b\bOK") == "download 4OK"


def test_ansi_transcript_consumes_sgr_and_erases_the_current_line() -> None:
    terminal = AnsiTerminalTranscript()

    assert terminal.feed("\x1b[31mwarning\x1b[0m\x1b[2Kready") == "ready"


def test_ansi_transcript_bounds_scrollback_and_supports_screen_clear() -> None:
    terminal = AnsiTerminalTranscript(max_scrollback_lines=2)

    assert terminal.feed("one\ntwo\nthree\n") == "two\nthree\n"
    assert terminal.feed("\x1b[2Jready") == "ready"
    assert TERMINAL_EMULATOR_BACKEND == "ansi-transcript-v1"


def test_ansi_transcript_rejects_non_positive_scrollback_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        AnsiTerminalTranscript(max_scrollback_lines=0)
