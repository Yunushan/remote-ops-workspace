"""Optional Qt workspace widgets with per-instance state and owner callbacks."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtGui import QFont, QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import QLabel, QTabBar, QTabWidget, QToolButton, QWidget

from .gui_designs import gui_design_moba_rail_chrome, gui_design_moba_rail_item_geometry_for


class MobaRailLabel(QLabel):
    def __init__(self, label: str, role: str, button: QToolButton) -> None:
        super().__init__(label)
        self.button = button
        chrome = gui_design_moba_rail_chrome()
        geometry = gui_design_moba_rail_item_geometry_for(role)
        self.setObjectName("mobaRailLabel")
        self.setProperty("mobaRailRole", role)
        self.setProperty("mobaRailLabel", label)
        self.setProperty("mobaRailStaticLabelY", geometry.static_label_y)
        self.setProperty("mobaRailLabelWidth", chrome.label_width)
        self.setProperty("mobaRailLabelHeight", chrome.label_height)
        self.setProperty("mobaRailLabelFontSize", chrome.label_font_size)
        self.setProperty("mobaRailTextRenderMode", "device-pixel-pixmap")
        self.setProperty("mobaRailTextHinting", "PreferFullHinting")
        self.setProperty("mobaRailTextTransformation", "none")
        self.setProperty("mobaRailTextPixmapRenderMode", "dpr-aware-rotated-pixmap")
        self.setProperty("mobaRailTextPixmapTransformation", "rotate-minus-90-before-paint")
        self.setProperty("mobaRailTextPixmapDevicePixelRatio", 1.0)
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(label)
        self.setAccessibleDescription(f"Open the {label} rail")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(chrome.label_width, chrome.label_height)
        self._rail_text_pixmap: QPixmap | None = None
        self._rail_text_cache_key: tuple[str, str, int, float, int, int] | None = None
        font = QFont("Segoe UI")
        font.setPixelSize(chrome.label_font_size)
        font.setBold(True)
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
        self.setFont(font)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.button.click()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.button.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.StyleChange,
        }:
            self._rail_text_pixmap = None
            self._rail_text_cache_key = None
        super().changeEvent(event)

    def rail_text_pixmap(self) -> QPixmap:
        dpr = max(1.0, float(self.devicePixelRatioF()))
        foreground = self.palette().color(self.foregroundRole())
        key = (
            self.text(),
            self.font().toString(),
            foreground.rgba(),
            round(dpr, 4),
            self.width(),
            self.height(),
        )
        if self._rail_text_pixmap is not None and self._rail_text_cache_key == key:
            return self._rail_text_pixmap
        logical_width = self.height()
        logical_height = self.width()
        source = QPixmap(
            max(1, round(logical_width * dpr)),
            max(1, round(logical_height * dpr)),
        )
        source.setDevicePixelRatio(dpr)
        source.fill(Qt.GlobalColor.transparent)
        source_painter = QPainter(source)
        source_painter.setRenderHint(
            QPainter.RenderHint.TextAntialiasing,
            True,
        )
        source_painter.setFont(self.font())
        source_painter.setPen(foreground)
        source_painter.drawText(
            0,
            0,
            logical_width,
            logical_height,
            Qt.AlignmentFlag.AlignCenter,
            self.text(),
        )
        source_painter.end()
        rotated = source.transformed(
            QTransform().rotate(-90),
            Qt.TransformationMode.SmoothTransformation,
        )
        rotated.setDevicePixelRatio(dpr)
        self._rail_text_pixmap = rotated
        self._rail_text_cache_key = key
        self.setProperty("mobaRailTextDevicePixelRatio", dpr)
        self.setProperty("mobaRailTextPixmapDevicePixelRatio", dpr)
        self.setProperty(
            "mobaRailTextPixmapPhysicalSize",
            [rotated.width(), rotated.height()],
        )
        self.setProperty(
            "mobaRailTextPixmapLogicalSize",
            [
                round(rotated.width() / dpr),
                round(rotated.height() / dpr),
            ],
        )
        self.setProperty("mobaRailTextPixmapReady", not rotated.isNull())
        return rotated

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        pixmap = self.rail_text_pixmap()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()


class MobaWorkspaceTabBar(QTabBar):
    """Apply measured tab widths only while the Moba preset is active."""

    TAB_RESIZE_HIT_WIDTH = 6
    TAB_RESIZE_MIN_WIDTH = 140
    TAB_RESIZE_MAX_WIDTH = 640

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.special_tab_handler: Callable[[int], None] | None = None
        self.tab_switch_prepare_handler: Callable[[int], None] | None = None
        self._pressed_special_key = ""
        self._stabilizing_special_tabs = False
        self._tab_resize_index = -1
        self._tab_resize_edge = ""
        self._tab_resize_start_x = 0
        self._tab_resize_start_width = 0
        self.setMouseTracking(True)
        self.setProperty("mobaTabWidthsUserResizable", True)
        self.tabMoved.connect(self.stabilize_special_tabs)

    def moba_tab_key(self, index: int) -> str:
        data = self.tabData(index)
        if not isinstance(data, dict):
            return ""
        return str(data.get("moba_key") or "")

    def activate_special_tab(self, index: int) -> bool:
        key = self.moba_tab_key(index)
        if key != "new-session" or not callable(self.special_tab_handler):
            return False
        self.special_tab_handler(index)
        return True

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            resize_target = self._tab_resize_target(event.position().toPoint())
            if resize_target is not None:
                index, edge = resize_target
                rect = self.tabRect(index)
                self._tab_resize_index = index
                self._tab_resize_edge = edge
                self._tab_resize_start_x = event.position().toPoint().x()
                self._tab_resize_start_width = rect.width()
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                event.accept()
                return
        index = self.tabAt(event.position().toPoint())
        self._pressed_special_key = self.moba_tab_key(index)
        if self.activate_special_tab(index):
            event.accept()
            return
        if (
            index >= 0
            and index != self.currentIndex()
            and callable(self.tab_switch_prepare_handler)
        ):
            # Freeze the old page before QTabBar changes the current page.
            # Waiting for QTabWidget.currentChanged is one paint too late
            # on Windows and can expose the new terminal at its transient
            # minimum geometry in the middle of the workspace.
            self.tab_switch_prepare_handler(index)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if (
            self.count() > 1
            and event.key()
            in {
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
            }
            and callable(self.tab_switch_prepare_handler)
        ):
            self.tab_switch_prepare_handler(-1)
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        position = event.position().toPoint()
        if self._tab_resize_index >= 0:
            self._resize_tab_width(position.x())
            event.accept()
            return
        if self._pressed_special_key in {"home", "new-session"}:
            event.accept()
            return
        if self._tab_resize_target(position) is not None:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._tab_resize_index >= 0:
            position = event.position().toPoint()
            self._resize_tab_width(position.x())
            self._tab_resize_index = -1
            self._tab_resize_edge = ""
            self._tab_resize_start_x = 0
            self._tab_resize_start_width = 0
            self.unsetCursor()
            event.accept()
            return
        special_key = self._pressed_special_key
        self._pressed_special_key = ""
        if special_key == "new-session":
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def stabilize_special_tabs(self, *_args) -> None:
        if self._stabilizing_special_tabs:
            return
        self._stabilizing_special_tabs = True
        try:
            home_index = next(
                (
                    index
                    for index in range(self.count())
                    if self.moba_tab_key(index) == "home"
                ),
                -1,
            )
            if home_index > 0:
                self.moveTab(home_index, 0)
            new_session_index = next(
                (
                    index
                    for index in range(self.count())
                    if self.moba_tab_key(index) == "new-session"
                ),
                -1,
            )
            if 0 <= new_session_index < self.count() - 1:
                self.moveTab(new_session_index, self.count() - 1)
        finally:
            self._stabilizing_special_tabs = False

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._tab_resize_index < 0:
            self.unsetCursor()
        super().leaveEvent(event)

    def _tab_resize_target(self, position) -> tuple[int, str] | None:
        if not bool(self.property("mobaCompactTabWidths")):
            return None
        hit_width = self.TAB_RESIZE_HIT_WIDTH
        candidates: list[tuple[int, int, str]] = []
        for index in range(self.count()):
            if self.moba_tab_key(index) in {"home", "new-session"}:
                continue
            rect = self.tabRect(index)
            if rect.isNull() or not rect.adjusted(-hit_width, -hit_width, hit_width, hit_width).contains(position):
                continue
            left_distance = abs(position.x() - rect.left())
            right_distance = abs(position.x() - rect.right())
            if left_distance <= hit_width:
                candidates.append((left_distance, index, "left"))
            if right_distance <= hit_width:
                candidates.append((right_distance, index, "right"))
        if not candidates:
            return None
        _distance, index, edge = min(candidates, key=lambda item: item[0])
        return index, edge

    def _resize_tab_width(self, position_x: int) -> None:
        index = self._tab_resize_index
        if index < 0 or index >= self.count() or self._tab_resize_start_width <= 0:
            return
        delta = int(position_x) - self._tab_resize_start_x
        if self._tab_resize_edge == "left":
            width = self._tab_resize_start_width - delta
        else:
            width = self._tab_resize_start_width + delta
        width = max(self.TAB_RESIZE_MIN_WIDTH, min(self.TAB_RESIZE_MAX_WIDTH, width))
        data = self.tabData(index)
        if not isinstance(data, dict):
            return
        if int(data.get("moba_width", 0) or 0) == width and data.get("moba_user_width") is True:
            return
        resized_data = dict(data)
        resized_data["moba_width"] = width
        resized_data["moba_user_width"] = True
        self.setTabData(index, resized_data)
        self._refresh_tab_layout(index)
        widget = self.parentWidget()
        if widget is not None:
            widget.updateGeometry()
        self.setProperty("mobaLastResizedTabIndex", index)
        self.setProperty("mobaLastResizedTabWidth", width)
        self.updateGeometry()
        self.update()

    def _refresh_tab_layout(self, index: int) -> None:
        """Make a changed ``tabSizeHint`` reach the live tab geometry."""

        # QTabBar caches tab rectangles. Re-setting the unchanged label is
        # a public Qt route that invalidates that cache without reaching
        # into private layout APIs or changing the visible tab text.
        self.setTabText(index, self.tabText(index))
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is None:
            return
        parent.updateGeometry()
        layout = parent.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()

    def tabSizeHint(self, index: int):  # noqa: N802
        hint = super().tabSizeHint(index)
        if not bool(self.property("mobaCompactTabWidths")):
            return hint
        data = self.tabData(index)
        if not isinstance(data, dict):
            return hint
        width = data.get("moba_width")
        height = data.get("moba_height")
        if not isinstance(width, int) or width <= 0:
            return hint
        return QSize(width, height if isinstance(height, int) and height > 0 else hint.height())


class ResponsiveWorkspaceTabs(QTabWidget):
    """Keep hidden, content-rich tabs from fixing the whole window above its usable size."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.tab_switch_prepare_handler: Callable[[int], None] | None = None

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if (
            index != self.currentIndex()
            and callable(self.tab_switch_prepare_handler)
        ):
            self.tab_switch_prepare_handler(index)
        super().setCurrentIndex(index)

    def setCurrentWidget(self, widget: QWidget | None) -> None:  # noqa: N802
        if widget is not None:
            index = self.indexOf(widget)
            if (
                index != self.currentIndex()
                and callable(self.tab_switch_prepare_handler)
            ):
                self.tab_switch_prepare_handler(index)
        super().setCurrentWidget(widget)

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), 520), min(hint.height(), 320))
