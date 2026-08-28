import pytest

from remote_ops_workspace.terminal_emulation import (
    ANSI_16_COLOR_PALETTE,
    ANSI_DEFAULT_BACKGROUND,
    ANSI_DEFAULT_FOREGROUND,
    TERMINAL_EMULATOR_BACKEND,
    AnsiTerminalTranscript,
    ansi_256_color,
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


def test_ansi_transcript_bounds_alternate_screen_redraws_and_restores_shell() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(40, 6)
    terminal.feed("shell prompt\n")

    assert terminal.feed(
        "\x1b[?1049h\x1b[2J\x1b[1;1Hone\n\x1b[1;1Htwo"
    ) == "two"
    assert terminal.screen_text().startswith("two\n")
    assert terminal.screen_text().count("\n") == 5
    assert terminal.feed("\x1b[?1049l") == "shell prompt\n"


def test_ansi_transcript_handles_vim_scroll_regions_and_cursor_save_restore() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(20, 6)

    terminal.feed("\x1b[?1049h\x1b[2J\x1b[1;1Hheader")
    assert terminal.alternate_screen_active is True
    terminal.feed("\x1b[2;1Hbefore\x1b[3;1Hmiddle\x1b[4;1Hafter")

    # Vim uses a scroll region plus insert/delete line and character controls
    # during redraw. Those controls must stay bounded inside the alternate
    # screen rather than corrupting the normal shell transcript.
    terminal.feed("\x1b[2;5r\x1b[3;1H\x1b[1Linserted\x1b[3;2H\x1b[1P")
    terminal.feed("\x1b7\x1b[6;6Hz\x1b8Q")
    assert "header" in terminal.text()
    assert "erted" in terminal.text()
    assert terminal.feed("\x1b[?1049l") == ""
    assert terminal.alternate_screen_active is False


def test_ansi_transcript_handles_vim_origin_insert_and_wrap_modes() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(20, 6)

    terminal.feed("\x1b[?1049h\x1b[2;5r\x1b[?6h\x1b[1;1Horigin")

    assert terminal.origin_mode_active is True
    assert terminal.cursor_row == 1
    assert terminal.text().splitlines()[1].startswith("origin")

    terminal.feed("\x1b[?6l\x1b[2J\x1b[?7l\x1b[1;20HX")
    terminal.feed("Y")
    assert terminal.screen_text().splitlines()[0][-1] == "Y"
    assert terminal.screen_text().splitlines()[1].strip() == ""

    terminal.feed("\x1b[?7h\x1b[1;20HX")
    terminal.feed("Y")
    assert terminal.screen_text().splitlines()[1].startswith("Y")

    terminal.feed("\x1b[1;1HAB\x1b[1;2H\x1b[4hX")
    assert terminal.insert_mode_active is True
    assert terminal.screen_text().splitlines()[0].startswith("AXB")
    terminal.feed("\x1b[4l\x1b[?1049l")


def test_ansi_transcript_restores_primary_modes_when_alternate_screen_closes() -> None:
    terminal = AnsiTerminalTranscript()

    # Readline commonly owns bracketed paste before Vim starts.  The editor
    # then changes several terminal modes and may leave without restoring all
    # of them, especially when it is interrupted during a redraw.
    terminal.feed("\x1b[?2004h")
    terminal.feed(
        "\x1b[?1049h\x1b[?1h\x1b[?25l\x1b[?6h\x1b[4h\x1b[?7l"
    )
    assert terminal.bracketed_paste_active is True
    assert terminal.application_cursor_keys_active is True
    assert terminal.cursor_visible is False
    assert terminal.origin_mode_active is True
    assert terminal.insert_mode_active is True
    assert terminal.auto_wrap_active is False

    terminal.feed("\x1b[?1049l")

    assert terminal.alternate_screen_active is False
    assert terminal.bracketed_paste_active is True
    assert terminal.application_cursor_keys_active is False
    assert terminal.cursor_visible is True
    assert terminal.origin_mode_active is False
    assert terminal.insert_mode_active is False
    assert terminal.auto_wrap_active is True


def test_ansi_transcript_answers_full_screen_queries_and_tracks_bracketed_paste() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(80, 24)

    terminal.feed("\x1b[?1049h\x1b[?2004h\x1b[6n\x1b[?1;2c")

    assert terminal.alternate_screen_active is True
    assert terminal.bracketed_paste_active is True
    assert terminal.take_pending_responses() == (
        b"\x1b[1;1R",
        b"\x1b[?1;2c",
    )
    assert terminal.take_pending_responses() == ()

    terminal.feed("\x1b[?2004l\x1b[?1049l")
    assert terminal.bracketed_paste_active is False


def test_literal_notice_is_not_consumed_or_styled_by_child_escape_state() -> None:
    terminal = AnsiTerminalTranscript()

    terminal.feed("prefix\x1b[")
    assert terminal.feed_literal("[host notice]\n") == "prefix[host notice]\n"
    terminal.feed("31mred")

    fragments = terminal.styled_fragments()
    notice = next(fragment for fragment in fragments if "[host notice]" in fragment.text)
    red = next(fragment for fragment in fragments if fragment.text == "red")
    assert notice.style.foreground is None
    assert notice.style.background is None
    assert red.style.foreground == ANSI_16_COLOR_PALETTE[1]


def test_end_of_stream_discards_partial_ansi_and_restores_primary_screen() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(40, 8)
    terminal.feed("shell prompt\n")
    terminal.feed("\x1b[?1h\x1b[?2004h\x1b[?25l\x1b[?1049hALT\x1b[")

    assert terminal.end_of_stream() == "shell prompt\n"
    assert terminal.alternate_screen_active is False
    assert terminal.application_cursor_keys_active is False
    assert terminal.bracketed_paste_active is False
    assert terminal.cursor_visible is True
    assert terminal.feed_literal("[process exited]\n") == (
        "shell prompt\n[process exited]\n"
    )


def test_ansi_transcript_tracks_application_cursor_keys_and_remote_cursor() -> None:
    terminal = AnsiTerminalTranscript()
    terminal.set_screen_size(40, 8)

    terminal.feed("\x1b[?1h\x1b[?25l\x1b[?1049h\x1b[4;7H")

    assert terminal.application_cursor_keys_active is True
    assert terminal.cursor_visible is False
    assert terminal.cursor_row == 3
    assert terminal.cursor_column == 6

    terminal.feed("\x1b[?1l\x1b[?25h")
    assert terminal.application_cursor_keys_active is False
    assert terminal.cursor_visible is True

    terminal.feed("\x1bc")
    assert terminal.alternate_screen_active is False
    assert terminal.application_cursor_keys_active is False
    assert terminal.cursor_visible is True
    assert terminal.cursor_row == 0
    assert terminal.cursor_column == 0


def test_ansi_transcript_rejects_non_positive_scrollback_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        AnsiTerminalTranscript(max_scrollback_lines=0)


def test_ansi_transcript_retains_basic_bright_background_and_reset_styles() -> None:
    terminal = AnsiTerminalTranscript()

    assert (
        terminal.feed(
            "plain \x1b[31mred \x1b[1;4;96;44mbold-cyan-blue"
            "\x1b[22;24;39;49m default\x1b[0m"
        )
        == "plain red bold-cyan-blue default"
    )
    fragments = terminal.styled_fragments()

    assert [fragment.text for fragment in fragments] == [
        "plain ",
        "red ",
        "bold-cyan-blue",
        " default",
    ]
    assert fragments[1].style.foreground == ANSI_16_COLOR_PALETTE[1]
    assert fragments[2].style.foreground == ANSI_16_COLOR_PALETTE[14]
    assert fragments[2].style.background == ANSI_16_COLOR_PALETTE[4]
    assert fragments[2].style.bold is True
    assert fragments[2].style.underline is True
    assert fragments[3].style.foreground is None
    assert fragments[3].style.background is None
    assert fragments[3].style.bold is False
    assert fragments[3].style.underline is False


def test_ansi_transcript_supports_256_rgb_and_inverse_colors_across_chunks() -> None:
    terminal = AnsiTerminalTranscript()

    terminal.feed("\x1b[38;5;")
    assert terminal.feed("196mindexed \x1b[48;2;1;2;3mbackground ") == (
        "indexed background "
    )
    assert terminal.feed("\x1b[7minverse\x1b[27;0m") == "indexed background inverse"
    fragments = terminal.styled_fragments()

    assert fragments[0].style.foreground == "#ff0000"
    assert fragments[1].style.background == "#010203"
    assert fragments[2].style.inverse is True
    assert fragments[2].style.resolved_colors() == ("#010203", "#ff0000")
    assert ansi_256_color(16) == "#000000"
    assert ansi_256_color(231) == "#ffffff"
    assert ansi_256_color(232) == "#080808"
    assert ansi_256_color(255) == "#eeeeee"


def test_ansi_transcript_supports_colon_rgb_with_optional_color_space() -> None:
    terminal = AnsiTerminalTranscript()

    terminal.feed(
        "\x1b[38:2::4:5:6mempty-space "
        "\x1b[48:2:0:7:8:9mzero-space\x1b[0m"
    )
    fragments = terminal.styled_fragments()

    assert fragments[0].style.foreground == "#040506"
    assert fragments[1].style.foreground == "#040506"
    assert fragments[1].style.background == "#070809"


def test_ansi_transcript_inverse_defaults_and_cursor_rewrite_keep_styles_aligned() -> None:
    terminal = AnsiTerminalTranscript()

    assert terminal.feed("\x1b[7mreverse\x1b[0m") == "reverse"
    assert terminal.styled_fragments()[0].style.resolved_colors() == (
        ANSI_DEFAULT_BACKGROUND,
        ANSI_DEFAULT_FOREGROUND,
    )

    assert terminal.feed("\r\x1b[32mready\x1b[0m") == "readyse"
    fragments = terminal.styled_fragments()
    assert fragments[0].text == "ready"
    assert fragments[0].style.foreground == ANSI_16_COLOR_PALETTE[2]
    assert fragments[1].text == "se"
    assert fragments[1].style.foreground is None


def test_ansi_transcript_slices_fragments_and_consumes_osc_payloads() -> None:
    terminal = AnsiTerminalTranscript()

    assert terminal.feed("a\x1b]0;secret title\a\x1b[34mblue\nnext") == "ablue\nnext"
    fragments = terminal.styled_fragments(start=2, end=7)

    assert "".join(fragment.text for fragment in fragments) == "lue\nn"
    assert fragments[0].start == 2
    assert fragments[-1].end == 7
    assert fragments[0].style.foreground == ANSI_16_COLOR_PALETTE[4]
    assert fragments[1].text == "\n"


def test_ansi_transcript_incremental_fragments_seek_into_large_scrollback() -> None:
    terminal = AnsiTerminalTranscript(max_scrollback_lines=3_000)
    terminal.feed("".join(f"line-{index}\n" for index in range(2_000)))
    terminal.feed("\x1b[31mlatest")

    source = terminal.text()
    start = source.rfind("latest")
    fragments = terminal.styled_fragments(start=start, end=len(source))

    assert "".join(fragment.text for fragment in fragments) == "latest"
    assert fragments[0].start == start
    assert fragments[-1].end == len(source)
    assert fragments[0].style.foreground == ANSI_16_COLOR_PALETTE[1]
