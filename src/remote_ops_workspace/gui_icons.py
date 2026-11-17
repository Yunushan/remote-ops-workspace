"""Qt painters for workspace toolbar, tree and control icons."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygon


def draw_securecrt_toolbar_icon(
    painter: QPainter,
    icon_key: str,
    primary: QColor,
    dark: QColor,
    white: QColor,
    muted: QColor,
    size: int,
) -> None:
    """Paint one compact SecureCRT/Remmina-style toolbar glyph."""
    color = primary
    mid = size // 2

    def pen(value: QColor, width: int = 1) -> None:
        painter.setPen(QPen(value, width))

    def brush(value: QColor) -> None:
        painter.setBrush(QBrush(value))

    pen(color)
    painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    if icon_key == "session-manager":
        brush(color)
        painter.drawRect(2, 6, size - 4, size - 8)
        pen(white)
        painter.drawRect(4, 4, 7, 3)
        return
    if icon_key == "new-session":
        pen(color, 1)
        painter.drawRect(2, 2, size - 4, size - 6)
        pen(color, 2)
        painter.drawLine(mid, 5, mid, size - 7)
        painter.drawLine(5, mid - 1, size - 5, mid - 1)
        return
    if icon_key == "properties":
        pen(color, 2)
        painter.drawRect(4, 3, size - 8, size - 6)
        painter.drawLine(6, 6, size - 6, 6)
        painter.drawLine(6, 9, size - 6, 9)
        return
    if icon_key == "delete":
        pen(color, 2)
        painter.drawLine(4, 4, size - 4, size - 4)
        painter.drawLine(size - 4, 4, 4, size - 4)
        return
    if icon_key in {"connect", "open-connection"}:
        brush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(4, 3), QPoint(size - 3, mid), QPoint(4, size - 3)]))
        if icon_key == "open-connection":
            pen(color, 1)
            brush(dark)
            painter.drawRect(1, 5, 4, size - 10)
        return
    if icon_key in {"sftp", "import-session", "import-connections"}:
        brush(color)
        painter.setPen(QPen(white, 1))
        painter.drawRect(2, 6, size - 4, size - 8)
        painter.drawLine(5, 11, size - 5, 11)
        return
    if icon_key == "transfer":
        pen(color, 2)
        painter.drawLine(3, 6, size - 4, 6)
        painter.drawLine(size - 5, 4, size - 2, 6)
        painter.drawLine(size - 5, 8, size - 2, 6)
        painter.drawLine(size - 3, 12, 4, 12)
        painter.drawLine(5, 10, 2, 12)
        painter.drawLine(5, 14, 2, 12)
        return
    if icon_key in {"command", "script"}:
        brush(dark)
        pen(color, 1)
        painter.drawRect(2, 3, size - 4, size - 6)
        pen(color, 2)
        painter.drawLine(5, 7, 9, 10)
        painter.drawLine(9, 10, 5, 13)
        return
    if icon_key in {"tools", "external-tool"}:
        pen(color, 2)
        painter.drawLine(4, 4, size - 5, size - 5)
        painter.drawLine(size - 5, 4, 5, size - 4)
        return
    if icon_key in {"tile-h", "tile-v"}:
        pen(color, 2)
        painter.drawRect(2, 3, size - 4, size - 6)
        if icon_key == "tile-h":
            painter.drawLine(2, mid, size - 2, mid)
        else:
            painter.drawLine(mid, 3, mid, size - 3)
        return
    if icon_key == "refresh-tree":
        pen(color, 2)
        painter.drawArc(3, 3, size - 6, size - 6, 40 * 16, 280 * 16)
        brush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygon([QPoint(size - 4, 4), QPoint(size - 1, 7), QPoint(size - 6, 9)]))
        return
    # Unknown import/diagnostics actions still get a clear, compact
    # outline rather than falling back to the large native icon.
    pen(muted if not icon_key else color)
    painter.drawRect(3, 3, size - 6, size - 6)


def draw_mremoteng_toolbar_icon(
    painter: QPainter,
    icon_key: str,
    primary: QColor,
    dark: QColor,
    _white: QColor,
    _size: int,
) -> None:
    """Paint the compact legacy mRemoteNG connection-toolbar glyph."""
    draw_securecrt_toolbar_icon(
        painter,
        icon_key,
        primary,
        dark,
        primary,
        primary,
        _size,
    )


def draw_moba_ribbon_icon(painter: QPainter, icon_key: str, fill: QColor, size: int) -> None:
    white = QColor("#ffffff")
    dark = QColor("#101010")
    green = QColor("#42d66b")
    blue = QColor("#4da3ff")
    cyan = QColor("#26d0d4")
    red = QColor("#ff614f")
    yellow = QColor("#f7d63f")
    mid = size // 2

    def pen(color: QColor, width: int = 1) -> None:
        painter.setPen(QPen(color, width))

    def brush(color: QColor) -> None:
        painter.setBrush(QBrush(color))

    brush(fill)
    pen(fill)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 4, 4)

    if icon_key == "session":
        brush(dark)
        pen(white, 2)
        painter.drawRect(8, 7, size - 16, size - 13)
        brush(green)
        pen(green)
        painter.drawRect(11, 11, 6, 4)
        brush(white)
        painter.drawRect(11, size - 6, size - 22, 2)
    elif icon_key == "servers":
        pen(white, 2)
        painter.drawLine(mid, 7, 8, size - 8)
        painter.drawLine(mid, 7, size - 8, size - 8)
        painter.drawLine(8, size - 8, size - 8, size - 8)
        brush(cyan)
        for x, y in [(mid, 7), (8, size - 8), (size - 8, size - 8)]:
            painter.drawEllipse(x - 4, y - 4, 8, 8)
    elif icon_key == "tools":
        pen(white, 4)
        painter.drawLine(10, 8, size - 8, size - 10)
        brush(red)
        pen(red)
        painter.drawRect(size - 12, 5, 6, 8)
        brush(yellow)
        painter.drawRect(6, size - 12, 9, 5)
    elif icon_key == "games":
        brush(white)
        pen(dark)
        painter.drawRoundedRect(5, 13, size - 10, 13, 6, 6)
        pen(dark, 2)
        painter.drawLine(10, 19, 17, 19)
        painter.drawLine(13, 16, 13, 22)
        brush(red)
        painter.drawEllipse(size - 14, 16, 5, 5)
        brush(blue)
        painter.drawEllipse(size - 9, 20, 5, 5)
    elif icon_key == "sessions":
        brush(yellow)
        pen(dark)
        painter.drawLine(mid, 4, mid + 4, 12)
        painter.drawLine(mid + 4, 12, size - 5, 12)
        painter.drawLine(size - 5, 12, mid + 6, 18)
        painter.drawLine(mid + 6, 18, mid + 9, size - 5)
        painter.drawLine(mid + 9, size - 5, mid, 21)
        painter.drawLine(mid, 21, 7, size - 5)
        painter.drawLine(7, size - 5, mid - 6, 18)
        painter.drawLine(mid - 6, 18, 5, 12)
        painter.drawLine(5, 12, mid - 4, 12)
        painter.drawLine(mid - 4, 12, mid, 4)
    elif icon_key in {"view", "split"}:
        brush(blue if icon_key == "view" else cyan)
        pen(white, 2)
        painter.drawRect(7, 7, size - 14, size - 14)
        painter.drawLine(7, mid, size - 7, mid)
        painter.drawLine(mid, 7, mid, size - 7)
    elif icon_key == "multiexec":
        pen(white, 3)
        painter.drawLine(mid, 6, mid, size - 8)
        pen(white, 2)
        painter.drawLine(mid, 13, 8, size - 8)
        painter.drawLine(mid, 13, size - 8, size - 8)
        brush(blue)
        pen(blue)
        for x, y in [(mid, 6), (8, size - 8), (size - 8, size - 8)]:
            painter.drawEllipse(x - 3, y - 3, 6, 6)
    elif icon_key == "tunneling":
        pen(white, 4)
        painter.drawLine(7, 13, size - 7, 13)
        painter.drawLine(10, 21, size - 10, 21)
        brush(green)
        pen(green)
        painter.drawRect(6, 10, 6, 6)
        painter.drawRect(size - 12, 10, 6, 6)
    elif icon_key == "packages":
        brush(white)
        pen(dark)
        painter.drawRect(8, 8, size - 16, size - 16)
        pen(blue, 2)
        painter.drawLine(8, 14, mid, 8)
        painter.drawLine(mid, 8, size - 8, 14)
        painter.drawLine(mid, 8, mid, size - 8)
    elif icon_key == "settings":
        brush(fill)
        pen(white, 3)
        painter.drawEllipse(8, 8, size - 16, size - 16)
        for dx, dy in [(0, -9), (0, 9), (-9, 0), (9, 0)]:
            painter.drawLine(mid, mid, mid + dx, mid + dy)
        brush(yellow)
        pen(yellow)
        painter.drawEllipse(mid - 3, mid - 3, 6, 6)
    elif icon_key == "help":
        brush(blue)
        pen(white, 2)
        painter.drawEllipse(6, 5, size - 12, size - 10)
        pen(white, 2)
        painter.drawText(12, 23, "?")
    elif icon_key == "xserver":
        pen(green, 4)
        painter.drawLine(7, 7, size - 7, size - 7)
        pen(blue, 4)
        painter.drawLine(size - 7, 7, 7, size - 7)
        pen(red, 2)
        painter.drawLine(mid, 6, mid, size - 6)
    elif icon_key == "exit":
        brush(QColor("#e2473f"))
        pen(QColor("#e2473f"))
        painter.drawEllipse(3, 3, size - 6, size - 6)
        pen(white, 3)
        painter.drawLine(mid, 8, mid, mid + 2)
        painter.drawArc(8, 8, size - 16, size - 16, 35 * 16, 290 * 16)
    elif icon_key == "home":
        brush(QColor("#f5f5f5"))
        pen(QColor("#d7d7d7"))
        painter.drawLine(mid, 5, size - 6, 13)
        painter.drawLine(mid, 5, 6, 13)
        painter.drawRect(9, 13, size - 18, size - 20)
        brush(red)
        pen(red)
        painter.drawRect(mid - 2, size - 14, 5, 7)
    elif icon_key == "terminal-key":
        brush(QColor("#2b2b2b"))
        pen(QColor("#d6a72d"), 2)
        painter.drawRect(5, 5, size - 10, size - 10)
        pen(yellow, 2)
        painter.drawLine(9, 12, mid, 12)
        painter.drawLine(mid, 12, size - 10, size - 8)
        brush(yellow)
        painter.drawRect(8, size - 12, 6, 4)
    elif icon_key == "plus":
        brush(QColor("#303030"))
        pen(QColor("#9ca3af"), 2)
        painter.drawRoundedRect(4, 4, size - 8, size - 8, 3, 3)
        painter.drawLine(mid, 8, mid, size - 8)
        painter.drawLine(8, mid, size - 8, mid)


def draw_profile_tree_generated_icon(painter: QPainter, icon_key: str, *, group: bool, size: int) -> None:
    fill = QColor("#f4c430" if group else "#35d7c7")
    outline = QColor("#d7dde5")
    dark = QColor("#151515")
    muted = QColor("#7d8792")
    painter.setPen(QPen(outline, 1))
    painter.setBrush(QBrush(fill if group else Qt.BrushStyle.NoBrush))
    if icon_key == "folder":
        painter.drawRect(1, 5, size - 2, size - 6)
        painter.drawRect(3, 3, max(5, size // 2), 4)
        return
    if icon_key == "database":
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(1, 1, size - 2, max(5, size // 3))
        painter.drawRect(1, size // 4, size - 2, max(5, size - 7))
        painter.drawEllipse(1, size - 7, size - 2, 5)
        return
    if icon_key == "sftp":
        painter.setBrush(QBrush(fill))
        painter.drawRect(2, 5, size - 4, size - 6)
        painter.drawRect(3, 3, max(5, size // 2), 4)
        painter.setPen(QPen(dark, 1))
        painter.drawLine(4, size - 5, size - 4, size - 5)
        painter.drawLine(size - 6, size - 7, size - 3, size - 5)
        painter.drawLine(size - 6, size - 3, size - 3, size - 5)
        return
    if icon_key == "pin":
        painter.setPen(QPen(fill, 1))
        painter.setBrush(QBrush(fill))
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(size // 2, 1),
                    QPoint(size - 2, size // 2),
                    QPoint(size // 2 + 2, size // 2 + 2),
                    QPoint(size // 2, size - 1),
                    QPoint(size // 2 - 2, size // 2 + 2),
                    QPoint(2, size // 2),
                ]
            )
        )
        return
    if icon_key in {"shell", "command", "ssh", "ssh2", "host"}:
        painter.setPen(QPen(fill, 1))
        painter.setBrush(QBrush(dark))
        painter.drawRect(1, 2, size - 2, size - 3)
        painter.drawLine(4, 6, 7, size // 2)
        painter.drawLine(7, size // 2, 4, size - 5)
        painter.drawLine(9, size - 5, size - 3, size - 5)
        if icon_key == "ssh2":
            painter.setPen(QPen(outline, 1))
            painter.drawText(size - 6, 8, "2")
        elif icon_key == "command":
            painter.setPen(QPen(muted, 1))
            painter.drawRect(size - 6, 4, 3, 3)
        return
    if icon_key in {"rdp", "vnc"}:
        painter.setPen(QPen(fill, 1))
        painter.setBrush(QBrush(dark if icon_key == "vnc" else QColor("#d8e6f3")))
        painter.drawRect(1, 2, size - 2, size - 5)
        painter.drawRect(4, size - 3, size - 8, 2)
        if icon_key == "vnc":
            painter.drawLine(4, 5, size - 4, size - 5)
            painter.drawLine(size - 4, 5, 4, size - 5)
        return
    if icon_key == "snippet":
        painter.setPen(QPen(fill, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(3, 1, size - 6, size - 2)
        painter.drawLine(5, 5, size - 5, 5)
        painter.drawLine(5, 8, size - 5, 8)
        painter.drawLine(5, 11, size - 7, 11)
        return
    painter.setPen(QPen(fill, 1))
    painter.drawRect(2, 2, size - 4, size - 4)


def draw_mremoteng_document_control_icon(painter: QPainter, icon_key: str, size: int) -> None:
    primary = QColor("#2f6fb1")
    dark = QColor("#35516a")
    fill = QColor("#e8edf3")
    painter.setPen(QPen(primary, 1))
    painter.setBrush(QBrush(fill))
    if icon_key == "database":
        painter.drawEllipse(2, 2, size - 4, 4)
        painter.drawRect(2, 4, size - 4, size - 7)
        painter.drawArc(2, size - 6, size - 4, 4, 0, -180 * 16)
        painter.drawLine(2, 7, size - 2, 7)
        return
    if icon_key == "ssh":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(1, 4, 5, 5)
        painter.drawLine(6, 6, size - 2, 6)
        painter.drawLine(size - 5, 6, size - 5, 10)
        painter.drawLine(size - 2, 6, size - 2, 9)
        return
    if icon_key == "external":
        painter.drawRect(1, 4, size - 6, size - 6)
        painter.setPen(QPen(dark, 1))
        painter.drawLine(size - 7, 2, size - 2, 2)
        painter.drawLine(size - 2, 2, size - 2, 7)
        painter.drawLine(size - 8, 8, size - 2, 2)
        return
    if icon_key == "rdp":
        painter.drawRect(1, 3, size - 2, size - 6)
        painter.drawLine(size // 2, size - 3, size // 2, size - 1)
        painter.drawLine(4, size - 1, size - 4, size - 1)
        painter.setPen(QPen(dark, 1))
        painter.drawLine(3, 6, size - 4, 6)
        return
    painter.setPen(QPen(dark, 1))
    painter.drawText(2, size - 3, icon_key[:1].upper())


def draw_remmina_viewer_control_icon(painter: QPainter, icon_key: str, size: int) -> None:
    primary = QColor("#2f6fb1")
    dark = QColor("#35516a")
    fill = QColor("#e8edf3")
    painter.setPen(QPen(primary, 1))
    painter.setBrush(QBrush(fill))
    if icon_key == "fit":
        painter.drawRect(2, 2, size - 4, size - 4)
        painter.drawLine(4, 4, 7, 4)
        painter.drawLine(4, 4, 4, 7)
        painter.drawLine(size - 5, size - 5, size - 8, size - 5)
        painter.drawLine(size - 5, size - 5, size - 5, size - 8)
        return
    if icon_key == "scale":
        painter.drawRect(2, 4, size - 4, size - 6)
        painter.setPen(QPen(dark, 1))
        painter.drawText(4, size - 3, "1")
        return
    if icon_key == "clipboard":
        painter.drawRect(4, 3, size - 7, size - 5)
        painter.drawRect(6, 1, size - 11, 4)
        painter.setPen(QPen(dark, 1))
        painter.drawLine(6, 7, size - 5, 7)
        painter.drawLine(6, 10, size - 6, 10)
        return
    if icon_key == "fullscreen":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(2, 2, size - 4, size - 4)
        painter.drawLine(4, 6, 4, 4)
        painter.drawLine(4, 4, 6, 4)
        painter.drawLine(size - 5, size - 7, size - 5, size - 5)
        painter.drawLine(size - 7, size - 5, size - 5, size - 5)
        return
    if icon_key == "screenshot":
        painter.drawRect(2, 5, size - 4, size - 7)
        painter.drawRect(5, 3, 5, 3)
        painter.setBrush(QBrush(primary))
        painter.drawEllipse(size // 2 - 2, size // 2 - 1, 4, 4)
        return
    painter.drawEllipse(3, 3, size - 6, size - 6)


def draw_securecrt_session_manager_action_icon(painter: QPainter, icon_key: str, size: int) -> None:
    primary = QColor("#d7a84a")
    dark = QColor("#201a0e")
    painter.setPen(QPen(primary, 1))
    painter.setBrush(QBrush(primary))
    if icon_key == "folder":
        painter.drawRect(1, 4, size - 2, size - 5)
        painter.drawRect(2, 2, max(4, size // 2), 3)
        return
    if icon_key == "properties":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(2, 2, size - 4, size - 4)
        painter.setPen(QPen(dark, 1))
        painter.drawLine(4, 5, size - 4, 5)
        painter.drawLine(4, 8, size - 5, 8)
        painter.drawLine(4, 11, size - 6, 11)
        return
    painter.drawPolygon(QPoint(3, 2), QPoint(size - 3, size // 2), QPoint(3, size - 2))
