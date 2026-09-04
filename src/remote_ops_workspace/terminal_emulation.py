"""Small, dependency-free ANSI transcript emulator for embedded terminal panes.

This intentionally implements a bounded transcript rather than claiming a full
PTY.  It makes normal interactive command output readable when programs use
carriage returns, backspaces, common SGR colors, and CSI erase/clear controls.
Small alternate-screen support is included for full-screen programs such as
``htop``: their cursor-addressed redraws stay inside a bounded screen buffer
instead of being appended as a new, rapidly scrolling transcript.  Styling is
retained beside (not inside) the plain-text transcript so copying, searching,
and selecting output never exposes escape sequences.
"""

from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field

TERMINAL_EMULATOR_BACKEND = "ansi-transcript-v1"

# A high-contrast ANSI palette suitable for the dark embedded terminal.  The
# first eight entries are normal colors and the remaining eight are bright.
ANSI_16_COLOR_PALETTE: tuple[str, ...] = (
    "#000000",
    "#cd3131",
    "#0dbc79",
    "#e5e510",
    "#2472c8",
    "#bc3fbc",
    "#11a8cd",
    "#e5e5e5",
    "#666666",
    "#f14c4c",
    "#23d18b",
    "#f5f543",
    "#3b8eea",
    "#d670d6",
    "#29b8db",
    "#ffffff",
)
ANSI_DEFAULT_FOREGROUND = "#f0f0f0"
ANSI_DEFAULT_BACKGROUND = "#1c1c1c"


@dataclass(frozen=True, slots=True)
class AnsiTextStyle:
    """The bounded subset of SGR attributes retained by the transcript."""

    foreground: str | None = None
    background: str | None = None
    bold: bool = False
    underline: bool = False
    inverse: bool = False

    def resolved_colors(
        self,
        default_foreground: str = ANSI_DEFAULT_FOREGROUND,
        default_background: str = ANSI_DEFAULT_BACKGROUND,
    ) -> tuple[str | None, str | None]:
        """Return effective colors, including inverse-video defaults."""

        if not self.inverse:
            return self.foreground, self.background
        return (
            self.background or default_background,
            self.foreground or default_foreground,
        )


ANSI_DEFAULT_STYLE = AnsiTextStyle()


@dataclass(frozen=True, slots=True)
class AnsiTerminalFragment:
    """A continuous plain-text range that shares one ANSI style."""

    start: int
    end: int
    text: str
    style: AnsiTextStyle


def ansi_256_color(index: int) -> str:
    """Resolve an xterm 256-color palette index to ``#rrggbb``."""

    value = max(0, min(255, int(index)))
    if value < 16:
        return ANSI_16_COLOR_PALETTE[value]
    if value < 232:
        cube = value - 16
        red, remainder = divmod(cube, 36)
        green, blue = divmod(remainder, 6)
        levels = (0, 95, 135, 175, 215, 255)
        return f"#{levels[red]:02x}{levels[green]:02x}{levels[blue]:02x}"
    grey = 8 + (value - 232) * 10
    return f"#{grey:02x}{grey:02x}{grey:02x}"


@dataclass(slots=True)
class AnsiTerminalTranscript:
    """A bounded line transcript with the cursor controls common in CLI output."""

    max_scrollback_lines: int = 10_000
    _lines: list[list[str]] = field(default_factory=list)
    _line_styles: list[list[AnsiTextStyle]] = field(default_factory=list)
    _line: list[str] = field(default_factory=list)
    _styles: list[AnsiTextStyle] = field(default_factory=list)
    _column: int = 0
    _normal_cursor_row: int = 0
    _normal_saved_cursor: tuple[int, int] | None = None
    _escape: str | None = None
    _style: AnsiTextStyle = ANSI_DEFAULT_STYLE
    _screen_columns: int = 80
    _screen_rows: int = 24
    _alternate_screen: bool = False
    _alternate_lines: list[list[str]] = field(default_factory=list)
    _alternate_line_styles: list[list[AnsiTextStyle]] = field(default_factory=list)
    _alternate_row: int = 0
    _alternate_column: int = 0
    _alternate_top_margin: int = 0
    _alternate_bottom_margin: int = 0
    _alternate_saved_cursor: tuple[int, int] | None = None
    _bracketed_paste: bool = False
    _application_cursor_keys: bool = False
    _cursor_visible: bool = True
    _origin_mode: bool = False
    _insert_mode: bool = False
    _auto_wrap: bool = True
    _pending_responses: list[bytes] = field(default_factory=list)
    _saved_normal_state: tuple[
        list[list[str]],
        list[list[AnsiTextStyle]],
        list[str],
        list[AnsiTextStyle],
        int,
        int,
        tuple[int, int] | None,
    ] | None = None
    _saved_normal_modes: tuple[bool, bool, bool, bool, bool, bool] | None = None
    _render_revision: int = field(default=0, init=False, repr=False)
    _render_rows_cache: tuple[tuple[str, list[AnsiTextStyle]], ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _render_row_offsets_cache: tuple[int, ...] | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _text_cache: str | None = field(default=None, init=False, repr=False)
    _full_redraw_hint: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_scrollback_lines < 1:
            raise ValueError("max_scrollback_lines must be greater than zero")

    def reset(self) -> None:
        self._invalidate_render_cache()
        self._lines.clear()
        self._line_styles.clear()
        self._line.clear()
        self._styles.clear()
        self._column = 0
        self._normal_cursor_row = 0
        self._normal_saved_cursor = None
        self._escape = None
        self._style = ANSI_DEFAULT_STYLE
        self._alternate_screen = False
        self._alternate_lines.clear()
        self._alternate_line_styles.clear()
        self._alternate_row = 0
        self._alternate_column = 0
        self._alternate_top_margin = 0
        self._alternate_bottom_margin = 0
        self._alternate_saved_cursor = None
        self._bracketed_paste = False
        self._application_cursor_keys = False
        self._cursor_visible = True
        self._origin_mode = False
        self._insert_mode = False
        self._auto_wrap = True
        self._pending_responses.clear()
        self._saved_normal_state = None
        self._saved_normal_modes = None
        self._full_redraw_hint = True

    @property
    def alternate_screen_active(self) -> bool:
        """Whether the stream is currently drawing into the full-screen buffer."""

        return self._alternate_screen

    @property
    def bracketed_paste_active(self) -> bool:
        """Whether the application requested bracketed paste delimiters."""

        return self._bracketed_paste

    @property
    def application_cursor_keys_active(self) -> bool:
        """Whether DECCKM requests SS3 cursor/navigation key payloads."""

        return self._application_cursor_keys

    @property
    def cursor_visible(self) -> bool:
        """Whether the remote application requested a visible cursor."""

        return self._cursor_visible

    @property
    def origin_mode_active(self) -> bool:
        """Whether cursor addresses are relative to the active scroll region."""

        return self._origin_mode

    @property
    def insert_mode_active(self) -> bool:
        """Whether printable characters insert instead of replacing cells."""

        return self._insert_mode

    @property
    def auto_wrap_active(self) -> bool:
        """Whether a write past the last screen column wraps to the next row."""

        return self._auto_wrap

    @property
    def cursor_row(self) -> int:
        """Return the zero-based cursor row in the active screen buffer."""

        return self._cursor_row()

    @property
    def cursor_column(self) -> int:
        """Return the zero-based cursor column in the active screen buffer."""

        return self._cursor_column()

    def take_pending_responses(self) -> tuple[bytes, ...]:
        """Return and clear terminal-query responses requested by the child."""

        responses = tuple(self._pending_responses)
        self._pending_responses.clear()
        return responses

    def consume_full_redraw_hint(self) -> bool:
        """Return whether the last feed changed existing screen content.

        The GUI can safely use an append-only document update for ordinary
        output, but carriage returns and cursor-addressed redraws must rebuild
        the affected frame.  Keeping this bit in the parser avoids guessing
        from string prefixes, which is incorrect for progress bars, Vim, and
        readline edits.
        """

        hint = self._full_redraw_hint
        self._full_redraw_hint = False
        return hint

    def set_screen_size(self, columns: int, rows: int) -> None:
        """Set the virtual terminal size used by alternate-screen programs.

        The stream transcript does not need a size, but full-screen programs
        use the reported rows and columns to decide where to redraw.  Keeping
        this state in the emulator prevents ``htop``/``clear`` updates from
        growing the document indefinitely while leaving normal output
        behavior unchanged.
        """

        self._invalidate_render_cache()
        self._screen_columns = max(20, int(columns))
        self._screen_rows = max(5, int(rows))
        if self._alternate_screen:
            self._full_redraw_hint = True
            self._resize_alternate_screen()

    def feed(self, text: str) -> str:
        """Apply a stream chunk and return the current transcript text.

        Supported SGR styling is retained separately for the Qt renderer.
        Unsupported CSI and string controls are consumed, rather than rendered
        as raw escape characters or control payloads.
        """

        self._invalidate_render_cache()
        self._full_redraw_hint = False
        for char in text:
            if self._escape is not None:
                self._feed_escape(char)
                continue
            if char == "\x1b":
                self._escape = ""
            elif char == "\r":
                self._full_redraw_hint = True
                self._set_cursor_column(0)
            elif char == "\n":
                self._newline()
            elif char == "\b":
                self._full_redraw_hint = True
                self._set_cursor_column(max(0, self._cursor_column() - 1))
            elif char == "\t":
                for _ in range(8 - (self._cursor_column() % 8)):
                    self._write(" ")
            elif char.isprintable():
                self._write(char)
        return self.text()

    def feed_literal(self, text: str) -> str:
        """Append application-owned text outside the child ANSI parser.

        Status and lifecycle notices are not bytes from the terminal process.
        They must therefore remain readable even when the child stopped halfway
        through a CSI/OSC sequence or left a non-default SGR style active.  Keep
        the child's parser/style state for a still-running stream, but write the
        notice itself with the default style and never interpret control
        sequences embedded in an OS error string.
        """

        self._invalidate_render_cache()
        self._full_redraw_hint = False
        pending_escape = self._escape
        pending_style = self._style
        self._escape = None
        self._style = ANSI_DEFAULT_STYLE
        try:
            for char in text:
                if char == "\r":
                    self._full_redraw_hint = True
                    self._set_cursor_column(0)
                elif char == "\n":
                    self._newline()
                elif char == "\b":
                    self._full_redraw_hint = True
                    self._set_cursor_column(max(0, self._cursor_column() - 1))
                elif char == "\t":
                    for _ in range(8 - (self._cursor_column() % 8)):
                        self._write(" ")
                elif char.isprintable():
                    self._write(char)
        finally:
            self._escape = pending_escape
            self._style = pending_style
        return self.text()

    def end_of_stream(self) -> str:
        """Close child-owned terminal state at a process byte boundary.

        A crashed process cannot complete a partial escape sequence or emit the
        normal alternate-screen/style reset.  Abandon that incomplete parser
        state, restore the primary transcript, and reset input modes before the
        host application adds its exit diagnostics.
        """

        self._invalidate_render_cache()
        self._full_redraw_hint = True
        self._escape = None
        self._style = ANSI_DEFAULT_STYLE
        self._pending_responses.clear()
        if self._alternate_screen:
            self._leave_alternate_screen()
        # A process that ended while it owned the alternate screen cannot
        # restore the shell's input modes.  Clear the child-owned modes after
        # the primary screen has been restored so a later shell starts clean.
        self._bracketed_paste = False
        self._application_cursor_keys = False
        self._cursor_visible = True
        self._origin_mode = False
        self._insert_mode = False
        self._auto_wrap = True
        return self.text()

    def text(self) -> str:
        if self._alternate_screen:
            return "\n".join(line for line, _styles in self._alternate_render_rows())
        if self._text_cache is None:
            self._text_cache = "\n".join(
                row for row, _styles in self._cached_render_rows()
            )
        return self._text_cache

    def screen_text(self) -> str:
        """Return the visible screen, including blank rows, for a full-screen app.

        ``text()`` intentionally stays compact for copy/search consumers.  A
        real terminal viewport must retain all rows, however: trimming the
        blank rows below Vim's status line makes the editor appear vertically
        compressed and causes the scrollbar to jump while it redraws.
        """

        if not self._alternate_screen:
            return self.text()
        self._ensure_alternate_screen()
        return "\n".join("".join(line) for line in self._alternate_lines)

    def styled_fragments(
        self,
        start: int = 0,
        end: int | None = None,
        *,
        screen: bool = False,
    ) -> tuple[AnsiTerminalFragment, ...]:
        """Return styled ranges over the plain transcript.

        ``start`` and ``end`` use offsets in :meth:`text`.  Newline separators
        deliberately use the default style because formatting a paragraph
        separator has no visible terminal meaning.
        """

        source = self.screen_text() if screen else self.text()
        lower = max(0, min(len(source), int(start)))
        upper = len(source) if end is None else max(lower, min(len(source), int(end)))
        if lower == upper:
            return ()

        rows: Sequence[tuple[str, list[AnsiTextStyle]]]
        if screen and self._alternate_screen:
            rows = self._alternate_all_render_rows()
            row_start_index = 0
            position = 0
        else:
            rows = self._cached_render_rows()
            offsets = self._cached_render_row_offsets()
            row_start_index = max(0, bisect_right(offsets, lower) - 1)
            position = offsets[row_start_index]
        fragments: list[AnsiTerminalFragment] = []
        fragment_start = lower
        fragment_text: list[str] = []
        fragment_style: AnsiTextStyle | None = None

        def append_character(char: str, style: AnsiTextStyle) -> None:
            nonlocal fragment_start, fragment_style
            char_position = position
            if char_position < lower or char_position >= upper:
                return
            if fragment_style != style:
                if fragment_text:
                    text = "".join(fragment_text)
                    fragments.append(
                        AnsiTerminalFragment(
                            start=fragment_start,
                            end=fragment_start + len(text),
                            text=text,
                            style=fragment_style or ANSI_DEFAULT_STYLE,
                        )
                    )
                    fragment_text.clear()
                fragment_start = char_position
                fragment_style = style
            fragment_text.append(char)

        for row_index in range(row_start_index, len(rows)):
            row, styles = rows[row_index]
            row_start = position
            visible_start = max(0, lower - row_start)
            visible_end = min(len(row), upper - row_start)
            if visible_start < visible_end:
                position += visible_start
                for char, style in zip(
                    row[visible_start:visible_end],
                    styles[visible_start:visible_end],
                    strict=True,
                ):
                    append_character(char, style)
                    position += 1
                position = row_start + len(row)
            else:
                position += len(row)
            if row_index < len(rows) - 1:
                append_character("\n", ANSI_DEFAULT_STYLE)
                position += 1
            if position >= upper:
                break

        if fragment_text:
            text = "".join(fragment_text)
            fragments.append(
                AnsiTerminalFragment(
                    start=fragment_start,
                    end=fragment_start + len(text),
                    text=text,
                    style=fragment_style or ANSI_DEFAULT_STYLE,
                )
            )
        return tuple(fragments)

    def _invalidate_render_cache(self) -> None:
        self._render_revision += 1
        self._render_rows_cache = None
        self._render_row_offsets_cache = None
        self._text_cache = None

    def _cached_render_rows(self) -> tuple[tuple[str, list[AnsiTextStyle]], ...]:
        if self._render_rows_cache is None:
            self._render_rows_cache = tuple(
                [
                    *(
                        ("".join(line), styles)
                        for line, styles in zip(
                            self._lines,
                            self._line_styles,
                            strict=True,
                        )
                    ),
                    ("".join(self._line), self._styles),
                ]
            )
        return self._render_rows_cache

    def _cached_render_row_offsets(self) -> tuple[int, ...]:
        if self._render_row_offsets_cache is None:
            offsets: list[int] = []
            position = 0
            rows = self._cached_render_rows()
            for row_index, (row, _styles) in enumerate(rows):
                offsets.append(position)
                position += len(row)
                if row_index < len(rows) - 1:
                    position += 1
            self._render_row_offsets_cache = tuple(offsets)
        return self._render_row_offsets_cache

    def _render_rows(self) -> list[tuple[str, list[AnsiTextStyle]]]:
        if self._alternate_screen:
            return self._alternate_render_rows()
        return [
            *(
                ("".join(line), styles)
                for line, styles in zip(self._lines, self._line_styles, strict=True)
            ),
            ("".join(self._line), self._styles),
        ]

    def _alternate_render_rows(self) -> list[tuple[str, list[AnsiTextStyle]]]:
        if not self._alternate_lines:
            return [("", [])]
        last = 0
        for index, (line, styles) in enumerate(
            zip(self._alternate_lines, self._alternate_line_styles, strict=True)
        ):
            if line or styles:
                last = index
        return [
            ("".join(line), styles)
            for line, styles in zip(
                self._alternate_lines[: last + 1],
                self._alternate_line_styles[: last + 1],
                strict=True,
            )
        ]

    def _alternate_all_render_rows(self) -> list[tuple[str, list[AnsiTextStyle]]]:
        self._ensure_alternate_screen()
        return [
            ("".join(line), styles)
            for line, styles in zip(
                self._alternate_lines,
                self._alternate_line_styles,
                strict=True,
            )
        ]

    def _feed_escape(self, char: str) -> None:
        if self._escape is None:
            raise RuntimeError("escape parser entered without an active sequence")
        sequence = self._escape + char
        if sequence in {"[", "]", "P", "^", "_"}:
            self._escape = sequence
            return
        if sequence.startswith("["):
            if "@" <= char <= "~":
                self._apply_csi(sequence[1:-1], char)
                self._escape = None
                return
            if len(sequence) > 64:
                self._escape = None
            else:
                self._escape = sequence
            return
        if sequence.startswith(("]", "P", "^", "_")):
            if char == "\a" or sequence.endswith("\x1b\\") or len(sequence) > 4096:
                self._escape = None
            else:
                self._escape = sequence
            return
        if sequence == "Z":
            # DEC identification query (ESC Z), used by older Vim builds.
            self._pending_responses.append(b"\x1b[?1;2c")
            self._escape = None
            return
        if sequence in {"7", "8"}:
            # DEC save/restore cursor is still emitted by Vim and a number of
            # ncurses applications in addition to CSI s/u.
            if self._alternate_screen:
                if sequence == "7":
                    self._alternate_saved_cursor = (
                        self._alternate_row,
                        self._alternate_column,
                    )
                elif self._alternate_saved_cursor is not None:
                    self._alternate_row, self._alternate_column = self._alternate_saved_cursor
            self._escape = None
            return
        if sequence == "c":
            # RIS resets screen contents and private modes.  In particular,
            # leaving DECCKM or a hidden cursor sticky after Vim exits makes
            # the next shell appear unable to accept navigation input.
            self.reset()
            return
        # Consume bounded one-character ESC controls.
        if len(sequence) >= 1:
            self._escape = None

    def _apply_csi(self, params: str, command: str) -> None:
        private = params.startswith("?")
        raw_params = params[1:] if private else params
        values = [
            int(value) if value.isdigit() else 0
            for value in raw_params.split(";")
            if value != ""
        ]
        # CSI controls that address existing cells or change the active
        # screen need a complete frame rebuild.  SGR only changes the style
        # used by subsequent text, so treating every colour escape as a full
        # repaint makes fast terminal programs unnecessarily sluggish.
        if command not in {"m", "n", "c"}:
            self._full_redraw_hint = True
        if private and command in {"h", "l"} and any(
            mode in {47, 1047, 1049} for mode in values
        ):
            self._full_redraw_hint = True
        first = values[0] if values else 0
        if private and command in {"h", "l"}:
            enabled = command == "h"
            for mode in values:
                if mode == 1:
                    self._application_cursor_keys = enabled
                elif mode == 25:
                    self._cursor_visible = enabled
                elif mode == 6:
                    self._origin_mode = enabled
                    if self._alternate_screen:
                        self._set_alternate_cursor(
                            self._alternate_top_margin if enabled else 0,
                            0,
                        )
                elif mode == 7:
                    self._auto_wrap = enabled
                elif mode in {47, 1047, 1049}:
                    if enabled:
                        self._enter_alternate_screen()
                    else:
                        self._leave_alternate_screen()
                elif mode == 2004:
                    self._bracketed_paste = enabled
            return
        if command == "n":
            if first == 5:
                self._pending_responses.append(b"\x1b[0n")
            elif first == 6:
                row = self._cursor_row() + 1
                column = self._cursor_column() + 1
                self._pending_responses.append(f"\x1b[{row};{column}R".encode("ascii"))
            return
        if command == "c":
            if params.startswith(">"):
                self._pending_responses.append(b"\x1b[>0;10;1c")
            else:
                self._pending_responses.append(b"\x1b[?1;2c")
            return
        if command == "m":
            self._apply_sgr(params)
        elif self._alternate_screen:
            self._apply_alternate_csi(values, command)
        elif command == "K":
            line, styles = self._normal_cursor_line()
            if first in {0, 1}:  # end/beginning erase both preserve the cursor side.
                if first == 0:
                    del line[self._column :]
                    del styles[self._column :]
                else:
                    for index in range(min(self._column + 1, len(line))):
                        line[index] = " "
                        styles[index] = self._style
            elif first == 2:
                line.clear()
                styles.clear()
                self._column = 0
        elif command == "J":
            row = self._normal_cursor_row
            if first == 0:
                line, styles = self._normal_cursor_line()
                del line[self._column :]
                del styles[self._column :]
                for index in range(row + 1, len(self._lines)):
                    self._lines[index].clear()
                    self._line_styles[index].clear()
            elif first == 1:
                for index in range(min(row, len(self._lines))):
                    self._lines[index].clear()
                    self._line_styles[index].clear()
                line, styles = self._normal_cursor_line()
                for index in range(min(self._column + 1, len(line))):
                    line[index] = " "
                    styles[index] = self._style
            elif first in {2, 3}:
                self._lines.clear()
                self._line_styles.clear()
                self._line.clear()
                self._styles.clear()
                self._normal_cursor_row = 0
                self._column = 0
        elif command in {"G", "C"}:
            self._column = max(0, (first or 1) - 1) if command == "G" else self._column + (first or 1)
        elif command == "D":
            self._column = max(0, self._column - (first or 1))
        elif command in {"A", "B", "E", "F"}:
            amount = first or 1
            if command in {"A", "F"}:
                self._normal_cursor_row = max(0, self._normal_cursor_row - amount)
            else:
                self._normal_cursor_row = min(
                    len(self._lines),
                    self._normal_cursor_row + amount,
                )
            if command in {"E", "F"}:
                self._column = 0
        elif command == "d":
            self._normal_cursor_row = max(
                0,
                min(len(self._lines), (first or 1) - 1),
            )
        elif command in {"H", "f"}:
            # Bare home is emitted by ``clear`` and remains useful for the
            # stream transcript.  Keep parameterized primary-screen H/f
            # conservative; only the bounded alternate screen has a stable
            # viewport coordinate system for arbitrary addresses.
            if not values or values in ([0], [1], [0, 0], [1, 1]):
                self._normal_cursor_row = 0
                self._column = 0
        elif command == "s":
            self._normal_saved_cursor = (
                self._normal_cursor_row,
                self._column,
            )
        elif command == "u" and self._normal_saved_cursor is not None:
            self._normal_cursor_row, self._column = self._normal_saved_cursor

    def _apply_alternate_csi(self, values: list[int], command: str) -> None:
        """Apply cursor and erase controls to the bounded alternate screen."""

        first = values[0] if values else 0
        if command in {"h", "l"}:
            enabled = command == "h"
            for mode in values:
                if mode == 4:
                    self._insert_mode = enabled
            return
        if command == "r":
            top = (values[0] if values and values[0] else 1) - 1
            bottom = (
                (values[1] if len(values) > 1 and values[1] else self._screen_rows)
                - 1
            )
            if not 0 <= top < bottom < self._screen_rows:
                top, bottom = 0, self._screen_rows - 1
            self._alternate_top_margin = top
            self._alternate_bottom_margin = bottom
            self._set_alternate_cursor(top, 0)
            return
        if command == "K":
            mode = first
            self._ensure_alternate_screen()
            line = self._alternate_lines[self._alternate_row]
            styles = self._alternate_line_styles[self._alternate_row]
            column = self._alternate_column
            if mode == 0:
                del line[column:]
                del styles[column:]
            elif mode == 1:
                for index in range(min(column + 1, len(line))):
                    line[index] = " "
                    styles[index] = self._style
            elif mode == 2:
                line.clear()
                styles.clear()
            return
        if command == "J":
            mode = first
            self._ensure_alternate_screen()
            if mode in {2, 3}:
                self._clear_alternate_screen()
            elif mode == 0:
                line = self._alternate_lines[self._alternate_row]
                styles = self._alternate_line_styles[self._alternate_row]
                del line[self._alternate_column:]
                del styles[self._alternate_column:]
                for row in range(self._alternate_row + 1, self._screen_rows):
                    self._blank_alternate_row(row)
            elif mode == 1:
                for row in range(0, self._alternate_row):
                    self._blank_alternate_row(row)
                line = self._alternate_lines[self._alternate_row]
                styles = self._alternate_line_styles[self._alternate_row]
                for index in range(min(self._alternate_column + 1, len(line))):
                    line[index] = " "
                    styles[index] = self._style
            return
        if command in {"H", "f"}:
            row = (values[0] if values and values[0] else 1) - 1
            column = (values[1] if len(values) > 1 and values[1] else 1) - 1
            if self._origin_mode:
                row += self._alternate_top_margin
            self._set_alternate_cursor(row, column)
            return
        if command in {"A", "B", "E", "F"}:
            amount = first or 1
            top, bottom = self._alternate_row_limits()
            if command in {"A", "F"}:
                self._alternate_row = max(top, self._alternate_row - amount)
            else:
                self._alternate_row = min(bottom, self._alternate_row + amount)
            if command in {"E", "F"}:
                self._alternate_column = 0
            return
        if command == "d":
            top, bottom = self._alternate_row_limits()
            self._alternate_row = max(top, min(bottom, top + (first or 1) - 1))
            return
        if command == "G":
            self._alternate_column = max(0, min(self._screen_columns - 1, (first or 1) - 1))
            return
        if command == "C":
            self._alternate_column = min(
                self._screen_columns - 1,
                self._alternate_column + (first or 1),
            )
            return
        if command == "D":
            self._alternate_column = max(0, self._alternate_column - (first or 1))
            return
        if command in {"L", "M"}:
            self._insert_or_delete_alternate_lines(first or 1, insert=command == "L")
            return
        if command in {"S", "T"}:
            self._scroll_alternate_region(first or 1, down=command == "T")
            return
        if command in {"@", "P", "X"}:
            self._edit_alternate_columns(first or 1, command)
            return
        if command == "s":
            self._alternate_saved_cursor = (self._alternate_row, self._alternate_column)
        elif command == "u" and self._alternate_saved_cursor is not None:
            self._alternate_row, self._alternate_column = self._alternate_saved_cursor

    def _apply_sgr(self, params: str) -> None:
        # Most producers use semicolon parameters.  Accept the common colon
        # spelling too, including the optional empty color-space slot.
        values = self._sgr_values(params)
        index = 0
        while index < len(values):
            code = values[index]
            index += 1
            if code == 0:
                self._style = ANSI_DEFAULT_STYLE
            elif code == 1:
                self._style = self._replace_style(bold=True)
            elif code == 22:
                self._style = self._replace_style(bold=False)
            elif code == 4:
                self._style = self._replace_style(underline=True)
            elif code == 24:
                self._style = self._replace_style(underline=False)
            elif code == 7:
                self._style = self._replace_style(inverse=True)
            elif code == 27:
                self._style = self._replace_style(inverse=False)
            elif 30 <= code <= 37:
                self._style = self._replace_style(
                    foreground=ANSI_16_COLOR_PALETTE[code - 30]
                )
            elif code == 39:
                self._style = self._replace_style(foreground=None)
            elif 40 <= code <= 47:
                self._style = self._replace_style(
                    background=ANSI_16_COLOR_PALETTE[code - 40]
                )
            elif code in {38, 48}:
                color, consumed = self._extended_sgr_color(values[index:])
                index += consumed
                if color is not None:
                    key = "foreground" if code == 38 else "background"
                    self._style = self._replace_style(**{key: color})
            elif code == 49:
                self._style = self._replace_style(background=None)
            elif 90 <= code <= 97:
                self._style = self._replace_style(
                    foreground=ANSI_16_COLOR_PALETTE[8 + code - 90]
                )
            elif 100 <= code <= 107:
                self._style = self._replace_style(
                    background=ANSI_16_COLOR_PALETTE[8 + code - 100]
                )

    @staticmethod
    def _sgr_values(params: str) -> list[int]:
        if not params:
            return [0]
        values: list[int] = []
        for group in params.split(";"):
            if ":" not in group:
                values.append(int(group) if group.isdigit() else 0)
                continue
            parts = group.split(":")
            head = int(parts[0]) if parts[0].isdigit() else 0
            if head in {38, 48} and len(parts) >= 3:
                mode = int(parts[1]) if parts[1].isdigit() else 0
                components = parts[2:]
                if mode == 2 and len(components) >= 4 and components[0] in {"", "0"}:
                    # ISO-8613-6 permits an empty or zero color-space identifier
                    # between the mode and the RGB components.
                    components = components[1:]
                values.extend(
                    [
                        head,
                        mode,
                        *(
                            int(component) if component.isdigit() else 0
                            for component in components
                        ),
                    ]
                )
                continue
            values.extend(int(part) if part.isdigit() else 0 for part in parts)
        return values

    @staticmethod
    def _extended_sgr_color(values: list[int]) -> tuple[str | None, int]:
        if len(values) >= 2 and values[0] == 5:
            return ansi_256_color(values[1]), 2
        if len(values) >= 4 and values[0] == 2:
            red, green, blue = (max(0, min(255, value)) for value in values[1:4])
            return f"#{red:02x}{green:02x}{blue:02x}", 4
        return None, min(1, len(values))

    def _replace_style(self, **changes: str | bool | None) -> AnsiTextStyle:
        values: dict[str, str | bool | None] = {
            "foreground": self._style.foreground,
            "background": self._style.background,
            "bold": self._style.bold,
            "underline": self._style.underline,
            "inverse": self._style.inverse,
        }
        values.update(changes)
        return AnsiTextStyle(
            foreground=values["foreground"] if isinstance(values["foreground"], str) else None,
            background=values["background"] if isinstance(values["background"], str) else None,
            bold=bool(values["bold"]),
            underline=bool(values["underline"]),
            inverse=bool(values["inverse"]),
        )

    def _cursor_column(self) -> int:
        return self._alternate_column if self._alternate_screen else self._column

    def _cursor_row(self) -> int:
        return self._alternate_row if self._alternate_screen else self._normal_cursor_row

    def _set_cursor_column(self, value: int) -> None:
        if self._alternate_screen:
            self._alternate_column = max(0, min(self._screen_columns - 1, int(value)))
        else:
            self._column = max(0, int(value))

    def _normal_cursor_line(self) -> tuple[list[str], list[AnsiTextStyle]]:
        """Return the mutable normal-screen row currently under the cursor."""

        self._normal_cursor_row = max(
            0,
            min(len(self._lines), self._normal_cursor_row),
        )
        if self._normal_cursor_row == len(self._lines):
            return self._line, self._styles
        return (
            self._lines[self._normal_cursor_row],
            self._line_styles[self._normal_cursor_row],
        )

    def _ensure_alternate_screen(self) -> None:
        if not self._alternate_lines:
            self._alternate_lines = [[] for _ in range(self._screen_rows)]
            self._alternate_line_styles = [[] for _ in range(self._screen_rows)]
        if len(self._alternate_lines) != self._screen_rows:
            self._resize_alternate_screen()

    def _resize_alternate_screen(self) -> None:
        old_lines = self._alternate_lines
        old_styles = self._alternate_line_styles
        self._alternate_lines = [[] for _ in range(self._screen_rows)]
        self._alternate_line_styles = [[] for _ in range(self._screen_rows)]
        for row in range(min(len(old_lines), self._screen_rows)):
            self._alternate_lines[row] = list(old_lines[row][: self._screen_columns])
            self._alternate_line_styles[row] = old_styles[row][: self._screen_columns]
        self._alternate_row = min(self._alternate_row, self._screen_rows - 1)
        self._alternate_column = min(self._alternate_column, self._screen_columns - 1)
        self._alternate_top_margin = max(
            0,
            min(self._alternate_top_margin, self._screen_rows - 1),
        )
        self._alternate_bottom_margin = max(
            self._alternate_top_margin,
            min(self._alternate_bottom_margin or self._screen_rows - 1, self._screen_rows - 1),
        )

    def _blank_alternate_row(self, row: int) -> None:
        if 0 <= row < self._screen_rows:
            self._alternate_lines[row] = []
            self._alternate_line_styles[row] = []

    def _clear_alternate_screen(self) -> None:
        self._ensure_alternate_screen()
        for row in range(self._screen_rows):
            self._blank_alternate_row(row)
        self._alternate_row = self._alternate_top_margin if self._origin_mode else 0
        self._alternate_column = 0

    def _blank_alternate_row_data(self) -> tuple[str, list[AnsiTextStyle]]:
        return "", []

    def _insert_or_delete_alternate_lines(self, amount: int, *, insert: bool) -> None:
        self._ensure_alternate_screen()
        if not self._alternate_top_margin <= self._alternate_row <= self._alternate_bottom_margin:
            return
        count = max(1, min(self._screen_rows, int(amount)))
        row = self._alternate_row
        if insert:
            for _ in range(count):
                self._alternate_lines.insert(row, [])
                self._alternate_line_styles.insert(row, [])
                del self._alternate_lines[self._alternate_bottom_margin + 1]
                del self._alternate_line_styles[self._alternate_bottom_margin + 1]
        else:
            for _ in range(count):
                del self._alternate_lines[row]
                del self._alternate_line_styles[row]
                self._alternate_lines.insert(self._alternate_bottom_margin, [])
                self._alternate_line_styles.insert(self._alternate_bottom_margin, [])

    def _scroll_alternate_region(self, amount: int, *, down: bool) -> None:
        self._ensure_alternate_screen()
        top = self._alternate_top_margin
        bottom = self._alternate_bottom_margin
        count = max(1, min(bottom - top + 1, int(amount)))
        for _ in range(count):
            if down:
                self._alternate_lines.insert(top, [])
                self._alternate_line_styles.insert(top, [])
                del self._alternate_lines[bottom + 1]
                del self._alternate_line_styles[bottom + 1]
            else:
                del self._alternate_lines[top]
                del self._alternate_line_styles[top]
                self._alternate_lines.insert(bottom, [])
                self._alternate_line_styles.insert(bottom, [])

    def _edit_alternate_columns(self, amount: int, command: str) -> None:
        self._ensure_alternate_screen()
        line = list(self._alternate_lines[self._alternate_row])
        styles = self._alternate_line_styles[self._alternate_row]
        column = self._alternate_column
        count = max(1, min(self._screen_columns, int(amount)))
        if column > len(line):
            padding = column - len(line)
            line.extend(" " for _ in range(padding))
            styles.extend(ANSI_DEFAULT_STYLE for _ in range(padding))
        if command == "@":
            line[column:column] = [" "] * count
            styles[column:column] = [self._style] * count
        elif command == "P":
            del line[column : column + count]
            del styles[column : column + count]
        else:  # X: erase characters without shifting the remainder.
            end = min(self._screen_columns, column + count)
            if end > len(line):
                line.extend(" " for _ in range(end - len(line)))
                styles.extend(ANSI_DEFAULT_STYLE for _ in range(end - len(styles)))
            for index in range(column, end):
                line[index] = " "
                styles[index] = self._style
        self._alternate_lines[self._alternate_row] = line[: self._screen_columns]
        self._alternate_line_styles[self._alternate_row] = styles[: self._screen_columns]

    def _set_alternate_cursor(self, row: int, column: int) -> None:
        self._ensure_alternate_screen()
        top, bottom = self._alternate_row_limits()
        self._alternate_row = max(top, min(bottom, int(row)))
        self._alternate_column = max(0, min(self._screen_columns - 1, int(column)))

    def _alternate_row_limits(self) -> tuple[int, int]:
        if self._origin_mode:
            return self._alternate_top_margin, self._alternate_bottom_margin
        return 0, self._screen_rows - 1

    def _enter_alternate_screen(self) -> None:
        if self._alternate_screen:
            return
        self._saved_normal_state = (
            self._lines,
            self._line_styles,
            self._line,
            self._styles,
            self._column,
            self._normal_cursor_row,
            self._normal_saved_cursor,
        )
        self._saved_normal_modes = (
            self._bracketed_paste,
            self._application_cursor_keys,
            self._cursor_visible,
            self._origin_mode,
            self._insert_mode,
            self._auto_wrap,
        )
        self._alternate_screen = True
        self._alternate_lines = [[] for _ in range(self._screen_rows)]
        self._alternate_line_styles = [[] for _ in range(self._screen_rows)]
        self._alternate_row = 0
        self._alternate_column = 0
        self._alternate_top_margin = 0
        self._alternate_bottom_margin = self._screen_rows - 1
        self._alternate_saved_cursor = None

    def _leave_alternate_screen(self) -> None:
        if not self._alternate_screen:
            return
        self._alternate_screen = False
        saved = self._saved_normal_state
        self._saved_normal_state = None
        if saved is not None:
            (
                self._lines,
                self._line_styles,
                self._line,
                self._styles,
                self._column,
                self._normal_cursor_row,
                self._normal_saved_cursor,
            ) = saved
        saved_modes = self._saved_normal_modes
        self._saved_normal_modes = None
        if saved_modes is not None:
            (
                self._bracketed_paste,
                self._application_cursor_keys,
                self._cursor_visible,
                self._origin_mode,
                self._insert_mode,
                self._auto_wrap,
            ) = saved_modes
        else:
            # Be conservative for a screen buffer restored from an older
            # serialized state that predates mode preservation.
            self._bracketed_paste = False
            self._application_cursor_keys = False
            self._cursor_visible = True
            self._origin_mode = False
            self._insert_mode = False
            self._auto_wrap = True
        self._alternate_lines.clear()
        self._alternate_line_styles.clear()
        self._alternate_row = 0
        self._alternate_column = 0
        self._alternate_top_margin = 0
        self._alternate_bottom_margin = 0
        self._alternate_saved_cursor = None

    def _newline(self) -> None:
        if self._alternate_screen:
            self._ensure_alternate_screen()
            self._alternate_column = 0
            bottom = self._alternate_bottom_margin or self._screen_rows - 1
            top = min(self._alternate_top_margin, bottom)
            if self._alternate_row < bottom:
                self._alternate_row += 1
            else:
                self._alternate_lines.pop(top)
                self._alternate_line_styles.pop(top)
                self._alternate_lines.insert(bottom, [])
                self._alternate_line_styles.insert(bottom, [])
            return
        self._normal_cursor_row = max(
            0,
            min(len(self._lines), self._normal_cursor_row),
        )
        if self._normal_cursor_row < len(self._lines):
            self._normal_cursor_row = min(
                len(self._lines),
                self._normal_cursor_row + 1,
            )
            self._column = 0
            return
        self._lines.append(list(self._line))
        self._line_styles.append(list(self._styles))
        overflow = len(self._lines) - self.max_scrollback_lines
        if overflow > 0:
            del self._lines[:overflow]
            del self._line_styles[:overflow]
        self._line.clear()
        self._styles.clear()
        self._column = 0
        self._normal_cursor_row = len(self._lines)

    def _write(self, char: str) -> None:
        if self._alternate_screen:
            self._ensure_alternate_screen()
            if self._alternate_column >= self._screen_columns:
                if self._auto_wrap:
                    self._newline()
                else:
                    self._alternate_column = self._screen_columns - 1
            line = self._alternate_lines[self._alternate_row]
            styles = self._alternate_line_styles[self._alternate_row]
            if self._alternate_column > len(line):
                padding = self._alternate_column - len(line)
                line.extend(" " for _ in range(padding))
                styles.extend(ANSI_DEFAULT_STYLE for _ in range(padding))
            if self._insert_mode:
                line[self._alternate_column : self._alternate_column] = [char]
                styles[self._alternate_column : self._alternate_column] = [self._style]
                del line[self._screen_columns :]
                del styles[self._screen_columns :]
            elif self._alternate_column == len(line):
                line.append(char)
                styles.append(self._style)
            else:
                line[self._alternate_column] = char
                styles[self._alternate_column] = self._style
            self._alternate_lines[self._alternate_row] = line
            if self._auto_wrap:
                self._alternate_column = min(
                    self._screen_columns,
                    self._alternate_column + 1,
                )
            else:
                self._alternate_column = min(
                    self._screen_columns - 1,
                    self._alternate_column + 1,
                )
            return
        line, styles = self._normal_cursor_line()
        if self._column > len(line):
            padding = self._column - len(line)
            line.extend(" " for _ in range(padding))
            styles.extend(ANSI_DEFAULT_STYLE for _ in range(padding))
        if self._column == len(line):
            line.append(char)
            styles.append(self._style)
        else:
            line[self._column] = char
            styles[self._column] = self._style
        self._column += 1
