from __future__ import annotations

import pytest

import remote_ops_workspace.terminal_emulation as terminal


def test_ansi_palette_clamps_and_resolves_non_inverse_colors() -> None:
    assert terminal.ansi_256_color(-10) == terminal.ANSI_16_COLOR_PALETTE[0]
    assert terminal.ansi_256_color(15) == terminal.ANSI_16_COLOR_PALETTE[15]
    assert terminal.ansi_256_color(999) == "#eeeeee"
    style = terminal.AnsiTextStyle(foreground="#010203", background="#040506")
    assert style.resolved_colors() == ("#010203", "#040506")


def test_reset_and_resize_active_alternate_screen() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("normal\x1b[?1049hfull")
    transcript.set_screen_size(10, 2)

    assert transcript.screen_text().count("\n") == 4
    assert transcript._screen_columns == 20
    assert transcript._screen_rows == 5

    transcript.reset()
    assert transcript.text() == ""
    assert transcript.alternate_screen_active is False
    assert transcript.auto_wrap_active is True


def test_feed_and_literal_handle_tabs_controls_and_cursor_rewrites() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    assert transcript.feed("\tA\x00") == "        A"
    assert transcript.feed_literal("\rB\bC\tD\x00") == "C       D"


def test_end_of_stream_and_screen_text_on_primary_screen() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("primary")
    assert transcript.end_of_stream() == "primary"
    assert transcript.screen_text() == "primary"


def test_styled_fragments_cover_screen_rows_empty_ranges_and_cache_reuse() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("one\ntwo")
    assert transcript.styled_fragments(start=2, end=2) == ()
    assert transcript._cached_render_rows() is transcript._cached_render_rows()
    assert transcript._cached_render_row_offsets() is transcript._cached_render_row_offsets()
    assert transcript._render_rows()[0][0] == "one"

    transcript.feed("\x1b[?1049h\x1b[1;1Hred")
    fragments = transcript.styled_fragments(start=0, end=6, screen=True)
    assert "".join(fragment.text for fragment in fragments).startswith("red\n")
    assert len(transcript._alternate_all_render_rows()) == transcript._screen_rows
    assert transcript._render_rows()[0][0] == "red"

    empty_alt = terminal.AnsiTerminalTranscript()
    empty_alt._alternate_screen = True
    assert empty_alt._alternate_render_rows() == [("", [])]


def test_escape_parser_rejects_invalid_state_and_bounds_sequences() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    with pytest.raises(RuntimeError, match="without an active sequence"):
        transcript._feed_escape("x")

    transcript.feed("\x1b[" + "1" * 65 + "xvisible")
    assert transcript.text().endswith("visible")

    transcript.feed("\x1b]title\x1b\\after")
    assert transcript.text().endswith("visibleafter")
    transcript.feed("\x1bP" + "x" * 4097 + "tail")
    assert transcript.text().endswith("visibleafterxtail")

    transcript.feed("\x1bZ")
    assert transcript.take_pending_responses() == (b"\x1b[?1;2c",)
    transcript.feed("\x1bx")
    assert transcript._escape is None


def test_escape_cursor_save_restore_without_saved_state_and_repeated_screen_modes() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("\x1b[?1049h\x1b8\x1b[2;3H\x1b7\x1b[4;5H\x1b8")
    assert (transcript.cursor_row, transcript.cursor_column) == (1, 2)

    transcript.feed("\x1b[?1049h")
    transcript._enter_alternate_screen()
    transcript.feed("\x1b[?1049l")
    transcript._leave_alternate_screen()
    assert transcript.alternate_screen_active is False


def test_device_status_and_attribute_queries() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("\x1b[5n\x1b[>0c\x1b[c\x1b[?999h")
    assert transcript.take_pending_responses() == (
        b"\x1b[0n",
        b"\x1b[>0;10;1c",
        b"\x1b[?1;2c",
    )


def test_primary_screen_erase_and_cursor_controls() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("abcdef\r\x1b[3C\x1b[0K")
    assert transcript.text() == "abc"

    transcript.feed("def\r\x1b[3C\x1b[1K")
    assert transcript.text() == "    ef"

    transcript.feed("\x1b[2Kready")
    assert transcript.text() == "ready"
    transcript.feed("\x1b[9Gx\x1b[2Dq")
    assert transcript.text().endswith("  qx")

    before = transcript.cursor_column
    transcript.feed("\x1b[2;2H")
    assert transcript.cursor_column == before
    transcript.feed("\x1b[H\x1b[3J")
    assert transcript.text() == ""


def test_alternate_erase_line_and_display_modes() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(20, 5)
    transcript.feed("\x1b[?1049h\x1b[1;1Hfirst\x1b[2;1Hsecond\x1b[3;1Hthird")

    transcript.feed("\x1b[2;3H\x1b[0K")
    assert transcript.screen_text().splitlines()[1] == "se"
    transcript.feed("cond\x1b[2;3H\x1b[1K")
    assert transcript.screen_text().splitlines()[1].startswith("   ond")
    transcript.feed("\x1b[2K")
    assert transcript.screen_text().splitlines()[1] == ""

    transcript.feed("\x1b[1;1Hone\x1b[2;1Htwo\x1b[3;1Hthree\x1b[2;2H\x1b[0J")
    rows = transcript.screen_text().splitlines()
    assert rows[0].startswith("one")
    assert rows[1] == "t"
    assert rows[2] == ""

    transcript.feed("\x1b[1;1Hone\x1b[2;1Htwo\x1b[3;1Hthree\x1b[2;2H\x1b[1J")
    rows = transcript.screen_text().splitlines()
    assert rows[0] == ""
    assert rows[1].startswith("  o")
    transcript.feed("\x1b[2J")
    assert transcript.text() == ""


def test_alternate_cursor_motion_absolute_and_origin_bounds() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(20, 6)
    transcript.feed("\x1b[?1049h\x1b[2;5r\x1b[?6h")
    transcript.feed("\x1b[3;4H\x1b[2A\x1b[1B\x1b[1E\x1b[1F")
    transcript.feed("\x1b[4d\x1b[9G\x1b[4C\x1b[2D")
    assert 1 <= transcript.cursor_row <= 4
    assert 0 <= transcript.cursor_column < 20

    transcript.feed("\x1b[5;2r")
    assert transcript._alternate_top_margin == 0
    assert transcript._alternate_bottom_margin == 5


def test_alternate_insert_delete_scroll_and_column_edits() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(20, 5)
    transcript.feed("\x1b[?1049h\x1b[1;1Hone\x1b[2;1Htwo\x1b[3;1Hthree")
    transcript.feed("\x1b[2;1H\x1b[2L\x1b[1M\x1b[1S\x1b[1T")

    transcript.feed("\x1b[2;5H\x1b[2@AB\x1b[1P\x1b[3X")
    assert len(transcript._alternate_lines) == 5

    transcript.feed("\x1b[2;10H\x1b[2X")
    transcript.feed("\x1b[s\x1b[4;4H\x1b[u")
    assert (transcript.cursor_row, transcript.cursor_column) == (1, 9)

    transcript._alternate_saved_cursor = None
    transcript.feed("\x1b[u")
    transcript._alternate_row = 4
    transcript._alternate_top_margin = 0
    transcript._alternate_bottom_margin = 2
    transcript._insert_or_delete_alternate_lines(1, insert=True)
    transcript._blank_alternate_row(-1)


def test_sgr_invalid_extended_colors_bright_background_and_colon_fallbacks() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("\x1b[100mbright\x1b[38;3mignored\x1b[0m")
    fragments = transcript.styled_fragments()
    assert fragments[0].style.background == terminal.ANSI_16_COLOR_PALETTE[8]
    assert terminal.AnsiTerminalTranscript._extended_sgr_color([]) == (None, 0)
    assert terminal.AnsiTerminalTranscript._extended_sgr_color([3]) == (None, 1)
    assert terminal.AnsiTerminalTranscript._extended_sgr_color([2, -1, 300, 4]) == ("#00ff04", 4)
    assert terminal.AnsiTerminalTranscript._sgr_values("bad:parts") == [0, 0]
    assert terminal.AnsiTerminalTranscript._sgr_values("38:2:1:2:3") == [38, 2, 1, 2, 3]


def test_alternate_screen_resize_preserves_bounded_content() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(30, 7)
    transcript.feed("\x1b[?1049h\x1b[7;30HZ")
    transcript.set_screen_size(20, 5)

    assert len(transcript._alternate_lines) == 5
    assert transcript.cursor_row == 4
    assert transcript.cursor_column == 19


def test_alternate_newline_scrolls_region_and_no_wrap_overwrites_last_cell() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(20, 5)
    transcript.feed("\x1b[?1049h\x1b[?7l\x1b[5;20HX")
    transcript.feed("Y\nZ")

    assert transcript.cursor_row == 4
    assert transcript.screen_text().splitlines()[-1].startswith("Z")


def test_primary_and_alternate_writes_pad_cursor_gaps() -> None:
    primary = terminal.AnsiTerminalTranscript()
    primary.feed("\x1b[5Gx")
    assert primary.text() == "    x"

    alternate = terminal.AnsiTerminalTranscript()
    alternate.feed("\x1b[?1049h\x1b[1;5Hx")
    assert alternate.text() == "    x"


def test_styled_fragments_clip_newlines_and_tolerate_empty_cached_rows() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("a\nb")
    fragments = transcript.styled_fragments(start=0, end=1)
    assert tuple(fragment.text for fragment in fragments) == ("a",)

    transcript._text_cache = "x"
    transcript._render_rows_cache = ()
    transcript._render_row_offsets_cache = (0,)
    assert transcript.styled_fragments(start=0, end=1) == ()


def test_normal_dec_controls_queries_and_ignored_csi_modes() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("normal\x1b7moved\x1b8")
    transcript.feed("\x1b[?6h\x1b[6n\x1b[7n")
    transcript._apply_csi("3", "K")
    transcript._apply_csi("2;2", "H")
    transcript._apply_csi("", "z")

    assert transcript.take_pending_responses() == (b"\x1b[1;12R",)
    assert transcript.text() == "normalmoved"
    assert transcript.origin_mode_active is True

    transcript._escape = ""
    transcript._feed_escape("")
    assert transcript._escape == ""


def test_alternate_ignored_modes_and_initialization_edges() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript._ensure_alternate_screen()
    assert len(transcript._alternate_lines) == transcript._screen_rows

    transcript._alternate_lines = [[]]
    transcript._alternate_line_styles = [[]]
    transcript._ensure_alternate_screen()
    assert len(transcript._alternate_lines) == transcript._screen_rows

    transcript._alternate_screen = True
    transcript._set_cursor_column(999)
    assert transcript.cursor_column == transcript._screen_columns - 1
    transcript._apply_alternate_csi([5], "h")
    transcript._apply_alternate_csi([3], "K")
    transcript._apply_alternate_csi([4], "J")
    assert transcript._blank_alternate_row_data() == ("", [])


def test_alternate_erase_existing_cells_leave_without_padding() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("\x1b[?1049habcdef\x1b[1;2H\x1b[2X")
    assert transcript.screen_text().splitlines()[0] == "a  def"


def test_leave_alternate_without_saved_primary_state() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript._alternate_screen = True
    transcript._saved_normal_state = None
    transcript._leave_alternate_screen()
    assert transcript.alternate_screen_active is False


def test_no_wrap_clamps_an_out_of_bounds_alternate_cursor() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.set_screen_size(20, 5)
    transcript.feed("\x1b[?1049h\x1b[?7l")
    transcript._alternate_column = transcript._screen_columns
    transcript._write("X")

    assert transcript.cursor_column == transcript._screen_columns - 1
    assert transcript.screen_text().splitlines()[0].endswith("X")


def test_bright_background_sgr_continues_to_a_following_parameter() -> None:
    transcript = terminal.AnsiTerminalTranscript()
    transcript.feed("\x1b[100;999;0mplain")
    assert transcript.styled_fragments()[0].style == terminal.ANSI_DEFAULT_STYLE
