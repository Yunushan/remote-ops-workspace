"""Small, dependency-free ANSI transcript emulator for embedded terminal panes.

This intentionally implements a bounded stream transcript rather than claiming a
full PTY.  It makes normal interactive command output readable when programs
use carriage returns, backspaces, and common CSI erase/clear controls.
"""

from dataclasses import dataclass, field

TERMINAL_EMULATOR_BACKEND = "ansi-transcript-v1"


@dataclass(slots=True)
class AnsiTerminalTranscript:
    """A bounded line transcript with the cursor controls common in CLI output."""

    max_scrollback_lines: int = 10_000
    _lines: list[str] = field(default_factory=list)
    _line: list[str] = field(default_factory=list)
    _column: int = 0
    _escape: str | None = None

    def __post_init__(self) -> None:
        if self.max_scrollback_lines < 1:
            raise ValueError("max_scrollback_lines must be greater than zero")

    def reset(self) -> None:
        self._lines.clear()
        self._line.clear()
        self._column = 0
        self._escape = None

    def feed(self, text: str) -> str:
        """Apply a stream chunk and return the current transcript text.

        SGR styling is intentionally ignored: the Qt widget supplies its own
        syntax highlighting. Unsupported CSI controls are consumed, rather than
        rendered as raw escape characters.
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

    def _feed_escape(self, char: str) -> None:
        sequence = self._escape + char
        if sequence == "[":
            self._escape = sequence
            return
        if not sequence.startswith("["):
            self._escape = None
            return
        if "@" <= char <= "~":
            self._apply_csi(sequence[1:-1], char)
            self._escape = None
            return
        if len(sequence) > 32:
            self._escape = None
        else:
            self._escape = sequence

    def _apply_csi(self, params: str, command: str) -> None:
        values = [int(value) if value.isdigit() else 0 for value in params.split(";") if value != ""]
        first = values[0] if values else 0
        if command == "K":
            if first in {0, 1}:  # end/beginning erase both preserve the cursor side.
                if first == 0:
                    del self._line[self._column :]
                else:
                    for index in range(min(self._column + 1, len(self._line))):
                        self._line[index] = " "
            elif first == 2:
                self._line.clear()
                self._column = 0
        elif command == "J" and first in {2, 3}:
            self._lines.clear()
            self._line.clear()
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

    def _newline(self) -> None:
        self._lines.append("".join(self._line))
        overflow = len(self._lines) - self.max_scrollback_lines
        if overflow > 0:
            del self._lines[:overflow]
        self._line.clear()
        self._column = 0

    def _write(self, char: str) -> None:
        if self._column > len(self._line):
            self._line.extend(" " for _ in range(self._column - len(self._line)))
        if self._column == len(self._line):
            self._line.append(char)
        else:
            self._line[self._column] = char
        self._column += 1
