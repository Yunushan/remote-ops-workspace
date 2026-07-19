"""Small, dependency-free ANSI transcript emulator for embedded terminal panes.

This intentionally implements a bounded stream transcript rather than claiming a
full PTY.  It makes normal interactive command output readable when programs
use carriage returns, backspaces, common SGR colors, and CSI erase/clear
controls.  Styling is retained beside (not inside) the plain-text transcript so
copying, searching, and selecting output never exposes escape sequences.
"""

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
    _lines: list[str] = field(default_factory=list)
    _line_styles: list[list[AnsiTextStyle]] = field(default_factory=list)
    _line: list[str] = field(default_factory=list)
    _styles: list[AnsiTextStyle] = field(default_factory=list)
    _column: int = 0
    _escape: str | None = None
    _style: AnsiTextStyle = ANSI_DEFAULT_STYLE

    def __post_init__(self) -> None:
        if self.max_scrollback_lines < 1:
            raise ValueError("max_scrollback_lines must be greater than zero")

    def reset(self) -> None:
        self._lines.clear()
        self._line_styles.clear()
        self._line.clear()
        self._styles.clear()
        self._column = 0
        self._escape = None
        self._style = ANSI_DEFAULT_STYLE

    def feed(self, text: str) -> str:
        """Apply a stream chunk and return the current transcript text.

        Supported SGR styling is retained separately for the Qt renderer.
        Unsupported CSI and string controls are consumed, rather than rendered
        as raw escape characters or control payloads.
        """

        for char in text:
            if self._escape is not None:
                self._feed_escape(char)
                continue
            if char == "\x1b":
                self._escape = ""
            elif char == "\r":
                self._column = 0
            elif char == "\n":
                self._newline()
            elif char == "\b":
                self._column = max(0, self._column - 1)
            elif char == "\t":
                for _ in range(8 - (self._column % 8)):
                    self._write(" ")
            elif char.isprintable():
                self._write(char)
        return self.text()

    def text(self) -> str:
        rows = [*self._lines, "".join(self._line)]
        return "\n".join(rows)

    def styled_fragments(
        self,
        start: int = 0,
        end: int | None = None,
    ) -> tuple[AnsiTerminalFragment, ...]:
        """Return styled ranges over the plain transcript.

        ``start`` and ``end`` use offsets in :meth:`text`.  Newline separators
        deliberately use the default style because formatting a paragraph
        separator has no visible terminal meaning.
        """

        source = self.text()
        lower = max(0, min(len(source), int(start)))
        upper = len(source) if end is None else max(lower, min(len(source), int(end)))
        if lower == upper:
            return ()

        rows = [
            *((line, styles) for line, styles in zip(self._lines, self._line_styles, strict=True)),
            ("".join(self._line), self._styles),
        ]
        fragments: list[AnsiTerminalFragment] = []
        fragment_start = lower
        fragment_text: list[str] = []
        fragment_style: AnsiTextStyle | None = None
        position = 0

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

        for row_index, (row, styles) in enumerate(rows):
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

    def _feed_escape(self, char: str) -> None:
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
        # Consume bounded one-character ESC controls.
        if len(sequence) >= 1:
            self._escape = None

    def _apply_csi(self, params: str, command: str) -> None:
        values = [int(value) if value.isdigit() else 0 for value in params.split(";") if value != ""]
        first = values[0] if values else 0
        if command == "m":
            self._apply_sgr(params)
        elif command == "K":
            if first in {0, 1}:  # end/beginning erase both preserve the cursor side.
                if first == 0:
                    del self._line[self._column :]
                    del self._styles[self._column :]
                else:
                    for index in range(min(self._column + 1, len(self._line))):
                        self._line[index] = " "
                        self._styles[index] = self._style
            elif first == 2:
                self._line.clear()
                self._styles.clear()
                self._column = 0
        elif command == "J" and first in {2, 3}:
            self._lines.clear()
            self._line_styles.clear()
            self._line.clear()
            self._styles.clear()
            self._column = 0
        elif command in {"G", "C"}:
            self._column = max(0, (first or 1) - 1) if command == "G" else self._column + (first or 1)
        elif command == "D":
            self._column = max(0, self._column - (first or 1))
        elif command in {"H", "f"}:
            # A stream transcript cannot revisit retained screen rows.  Home is
            # still useful for single-line status redraws and remains truthful.
            if not values or values in ([0], [1], [1, 1]):
                self._column = 0

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

    def _newline(self) -> None:
        self._lines.append("".join(self._line))
        self._line_styles.append(list(self._styles))
        overflow = len(self._lines) - self.max_scrollback_lines
        if overflow > 0:
            del self._lines[:overflow]
            del self._line_styles[:overflow]
        self._line.clear()
        self._styles.clear()
        self._column = 0

    def _write(self, char: str) -> None:
        if self._column > len(self._line):
            padding = self._column - len(self._line)
            self._line.extend(" " for _ in range(padding))
            self._styles.extend(ANSI_DEFAULT_STYLE for _ in range(padding))
        if self._column == len(self._line):
            self._line.append(char)
            self._styles.append(self._style)
        else:
            self._line[self._column] = char
            self._styles[self._column] = self._style
        self._column += 1
