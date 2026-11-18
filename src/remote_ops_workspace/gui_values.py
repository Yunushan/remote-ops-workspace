from __future__ import annotations

import html
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
