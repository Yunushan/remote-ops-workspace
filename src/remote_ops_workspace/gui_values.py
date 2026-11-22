from __future__ import annotations

import difflib
import html
import re
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStyle, QWidget

_GuiValue = TypeVar("_GuiValue")


def _safe_tooltip_html(text: str) -> str:
    """Render arbitrary launch/profile text literally inside a Qt tooltip."""

    escaped = html.escape(text).replace("\n", "<br>")
    return f"<qt>{escaped}</qt>"


def _required_gui_value(value: _GuiValue | None, label: str) -> _GuiValue:
    if value is None:
        raise RuntimeError(f"required GUI value is unavailable: {label}")
    return value


def _widget_style(widget: QWidget) -> QStyle:
    return _required_gui_value(widget.style(), f"style for {type(widget).__name__}")


def restore_document_format(baseline: str, qt_text: str) -> str:
    """Restore the original signature and paragraph endings hidden by QTextDocument."""
    signature = "\ufeff" if baseline.startswith("\ufeff") else ""
    text = baseline[len(signature):]
    parts = re.split(r"(\r\n|[\r\n\u2029])", text)
    lines, endings = parts[::2], parts[1::2]
    if qt_text == "\u2029".join(lines):
        return baseline
    first_ending = endings[0] if endings else "\n"
    if len(set(endings)) <= 1:
        return signature + qt_text.replace("\u2029", first_ending)

    # Keep matching lines' separators in mixed-format files. Replacement
    # lines inherit the replaced separators; new lines use the first style.
    edited_lines = qt_text.split("\u2029")
    edited_endings = [first_ending] * (len(edited_lines) - 1)
    matcher = difflib.SequenceMatcher(None, lines, edited_lines)
    for _tag, i, j, k, end in matcher.get_opcodes():
        for index, ending in zip(range(k, min(end, len(edited_endings))), endings[i:j], strict=False):
            edited_endings[index] = ending
    edited_endings.append("")
    return signature + "".join(line + ending for line, ending in zip(edited_lines, edited_endings, strict=True))
