from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHOLE_FRAME_DISTANCE_LIMIT = 0.025
# A blinking block cursor can legitimately change most pixels in one sampled
# 32x32 tile.  Keep the threshold below the 0.20+ distance produced by a real
# localized blank/miniature corruption while allowing that cursor repaint.
LOCALIZED_TILE_DISTANCE_LIMIT = 0.10
REQUIRED_INTERACTION_STAGES = {
    "mouse-tab-switch": frozenset({"before", "pressed", "released", "settled"}),
    "ctrl-tab-switch": frozenset(
        {"before", "key-pressed", "key-released", "settled"}
    ),
    "active-tab-close": frozenset({"before", "close-returned", "settled"}),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise mouse, Ctrl+Tab, and active-close terminal tab transitions on "
            "native Windows and reject transient miniature, blank, or incorrectly "
            "sized terminal paints."
        )
    )
    parser.add_argument("--out-dir", default="artifacts/gui-tab-switch-windows")
    parser.add_argument("--require-native-windows", action="store_true")
    return parser.parse_args()


def normalized_rgb_distance(
    first: Iterable[tuple[int, int, int]],
    second: Iterable[tuple[int, int, int]],
) -> float:
    """Return the normalized mean RGB distance for equally sized samples."""

    first_samples = list(first)
    second_samples = list(second)
    if len(first_samples) != len(second_samples) or not first_samples:
        return 1.0
    channel_delta = sum(
        abs(left[0] - right[0])
        + abs(left[1] - right[1])
        + abs(left[2] - right[2])
        for left, right in zip(first_samples, second_samples, strict=True)
    )
    return channel_delta / (len(first_samples) * 255.0 * 3.0)


def maximum_tiled_rgb_distance(
    first: Sequence[tuple[int, int, int]],
    second: Sequence[tuple[int, int, int]],
    *,
    width: int,
    height: int,
    tile_size: int = 8,
) -> float:
    """Return the worst localized RGB distance instead of a whole-frame mean."""

    if (
        width < 1
        or height < 1
        or tile_size < 1
        or len(first) != width * height
        or len(second) != width * height
    ):
        return 1.0
    maximum = 0.0
    for top in range(0, height, tile_size):
        bottom = min(height, top + tile_size)
        for left in range(0, width, tile_size):
            right = min(width, left + tile_size)
            channel_delta = 0
            samples = 0
            for y in range(top, bottom):
                row = y * width
                for x in range(left, right):
                    first_pixel = first[row + x]
                    second_pixel = second[row + x]
                    channel_delta += (
                        abs(first_pixel[0] - second_pixel[0])
                        + abs(first_pixel[1] - second_pixel[1])
                        + abs(first_pixel[2] - second_pixel[2])
                    )
                    samples += 1
            if samples:
                maximum = max(maximum, channel_delta / (samples * 255.0 * 3.0))
    return maximum


def matches_stable_terminal_reference(
    *,
    source_distance: float,
    target_distance: float,
    localized_source_distance: float,
    localized_target_distance: float,
) -> bool:
    """Require the whole viewport and every terminal tile to match one reference."""

    return (
        source_distance <= WHOLE_FRAME_DISTANCE_LIMIT
        and localized_source_distance <= LOCALIZED_TILE_DISTANCE_LIMIT
    ) or (
        target_distance <= WHOLE_FRAME_DISTANCE_LIMIT
        and localized_target_distance <= LOCALIZED_TILE_DISTANCE_LIMIT
    )


def validate_required_interaction_coverage(
    frames: Sequence[dict[str, object]],
) -> list[str]:
    """Require native evidence frames for every supported tab transition route."""

    errors: list[str] = []
    for interaction, required_stages in REQUIRED_INTERACTION_STAGES.items():
        observed_stages = {
            str(frame.get("stage", ""))
            for frame in frames
            if frame.get("interaction") == interaction
        }
        missing = sorted(required_stages - observed_stages)
        if missing:
            errors.append(f"{interaction} is missing capture stages: {missing}")
    return errors


def validate_settled_interaction_frames(
    frames: Sequence[dict[str, object]],
) -> list[str]:
    """Require each interaction to settle on the full target terminal surface."""

    errors: list[str] = []
    for frame in frames:
        if frame.get("stage") != "settled":
            continue
        interaction = str(frame.get("interaction", "unknown"))
        name = str(frame.get("name", "unnamed"))
        if frame.get("current_role") != "target":
            errors.append(f"{interaction}/{name}: target terminal is not active")
        if float(frame.get("target_distance", 1.0)) > WHOLE_FRAME_DISTANCE_LIMIT:
            errors.append(
                f"{interaction}/{name}: target terminal whole-viewport paint did not settle"
            )
        if (
            float(frame.get("localized_target_distance", 1.0))
            > LOCALIZED_TILE_DISTANCE_LIMIT
        ):
            errors.append(
                f"{interaction}/{name}: target terminal localized paint did not settle"
            )
    return errors


def validate_active_close_prepaint_contract(
    frames: Sequence[dict[str, object]],
) -> list[str]:
    """Require the close-returned frame to prove guarded successor exposure."""

    close_frames = [
        frame
        for frame in frames
        if frame.get("interaction") == "active-tab-close"
        and frame.get("stage") == "close-returned"
    ]
    if not close_frames:
        return ["active-tab-close has no close-returned evidence frame"]
    if not any(
        frame.get("active_tab_close_prepaint_guarded") is True
        for frame in close_frames
    ):
        return [
            "active-tab-close did not assert terminalActiveTabClosePrepaintGuarded"
        ]
    return []


def validate_alternate_screen_frames(
    frames: Sequence[dict[str, object]],
) -> list[str]:
    """Require every frame to retain a live process-driven full-screen grid."""

    errors: list[str] = []
    for frame in frames:
        name = frame.get("name", "unnamed")
        if frame.get("alternate_screen_active") is not True:
            errors.append(f"{name}: current terminal left alternate-screen mode")
        if frame.get("live_process_redraw_active") is not True:
            errors.append(f"{name}: current terminal redraw process is not running")
        flush_count = frame.get("terminal_output_flush_count")
        if (
            not isinstance(flush_count, int)
            or isinstance(flush_count, bool)
            or flush_count < 1
        ):
            errors.append(f"{name}: no readyRead output batch reached the terminal")
    return errors


def validate_terminal_frame_geometry(frame: dict[str, object]) -> list[str]:
    """Reject a visible terminal page that does not fill the tab workspace."""

    errors: list[str] = []
    tabs = frame.get("tabs")
    page = frame.get("page")
    viewport = frame.get("output_viewport")
    if not isinstance(tabs, dict) or not isinstance(page, dict) or not isinstance(viewport, dict):
        return ["frame geometry is incomplete"]

    tab_width = int(tabs.get("width", 0))
    tab_height = int(tabs.get("height", 0))
    page_width = int(page.get("width", 0))
    page_height = int(page.get("height", 0))
    viewport_width = int(viewport.get("width", 0))
    viewport_height = int(viewport.get("height", 0))
    visible_terminal_count = int(frame.get("visible_terminal_count", 0))

    if tab_width < 1 or tab_height < 1:
        errors.append("tab workspace has no usable size")
        return errors
    if page_width < max(300, int(tab_width * 0.72)):
        errors.append("terminal page is transiently undersized horizontally")
    if page_height < max(240, int(tab_height * 0.72)):
        errors.append("terminal page is transiently undersized vertically")
    if viewport_width < max(260, int(tab_width * 0.55)):
        errors.append("terminal output viewport is transiently undersized horizontally")
    if viewport_height < max(160, int(tab_height * 0.42)):
        errors.append("terminal output viewport is transiently undersized vertically")
    if visible_terminal_count != 1:
        errors.append(
            f"expected one visible terminal page, observed {visible_terminal_count}"
        )
    if not bool(frame.get("page_visible")):
        errors.append("current terminal page is not visible")
    return errors


def _rect_payload(widget, window) -> dict[str, int]:
    from PyQt6.QtCore import QPoint

    origin = widget.mapTo(window, QPoint(0, 0))
    return {
        "x": origin.x(),
        "y": origin.y(),
        "width": widget.width(),
        "height": widget.height(),
    }


def _sample_qimage(image, *, step: int = 8) -> list[tuple[int, int, int]]:
    from PyQt6.QtGui import QColor

    if image.isNull():
        return []
    return [
        (
            QColor.fromRgba(image.pixel(x, y)).red(),
            QColor.fromRgba(image.pixel(x, y)).green(),
            QColor.fromRgba(image.pixel(x, y)).blue(),
        )
        for y in range(0, image.height(), step)
        for x in range(0, image.width(), step)
    ]


def _sample_qimage_grid(
    image,
    *,
    step: int = 4,
) -> tuple[list[tuple[int, int, int]], int, int]:
    from PyQt6.QtGui import QColor

    if image.isNull():
        return [], 0, 0
    xs = list(range(0, image.width(), step))
    ys = list(range(0, image.height(), step))
    pixels = [
        (
            QColor.fromRgba(image.pixel(x, y)).red(),
            QColor.fromRgba(image.pixel(x, y)).green(),
            QColor.fromRgba(image.pixel(x, y)).blue(),
        )
        for y in ys
        for x in xs
    ]
    return pixels, len(xs), len(ys)


def _image_distance(first, second) -> float:
    pair = _common_viewport_overlap(first, second)
    if pair is None:
        return 1.0
    first, second = pair
    return normalized_rgb_distance(_sample_qimage(first), _sample_qimage(second))


def _localized_image_distance(first, second) -> float:
    pair = _common_viewport_overlap(first, second)
    if pair is None:
        return 1.0
    first, second = pair
    first_pixels, width, height = _sample_qimage_grid(first)
    second_pixels, second_width, second_height = _sample_qimage_grid(second)
    if (width, height) != (second_width, second_height):
        return 1.0
    # Eight sampled pixels represent a 32x32 physical-pixel tile. A small
    # centered child paint therefore cannot disappear into a whole-window mean.
    return maximum_tiled_rgb_distance(
        first_pixels,
        second_pixels,
        width=width,
        height=height,
        tile_size=8,
    )


def _common_viewport_overlap(first, second):
    """Align full terminal viewports across a small scrollbar-width change."""

    if first.isNull() or second.isNull():
        return None
    width = min(first.width(), second.width())
    height = min(first.height(), second.height())
    if width < 1 or height < 1:
        return None
    width_delta = abs(first.width() - second.width()) / max(
        first.width(), second.width()
    )
    height_delta = abs(first.height() - second.height()) / max(
        first.height(), second.height()
    )
    # The geometry validator independently requires a full-size terminal page.
    # This tolerance only accounts for a native scrollbar appearing between
    # the guarded old-frame paint and the new terminal's first paint.
    if width_delta > 0.08 or height_delta > 0.08:
        return None
    return first.copy(0, 0, width, height), second.copy(0, 0, width, height)


def _crop_native_image(image, logical_rect: dict[str, int], window) -> object:
    if image.isNull() or window.width() < 1 or window.height() < 1:
        return image.copy()
    scale_x = image.width() / window.width()
    scale_y = image.height() / window.height()
    x = max(0, round(logical_rect["x"] * scale_x))
    y = max(0, round(logical_rect["y"] * scale_y))
    width = max(1, round(logical_rect["width"] * scale_x))
    height = max(1, round(logical_rect["height"] * scale_y))
    return image.copy(x, y, min(width, image.width() - x), min(height, image.height() - y))


def _settle(app, turns: int = 3) -> None:
    from PyQt6.QtCore import QCoreApplication, QEventLoop

    for _ in range(turns):
        QCoreApplication.sendPostedEvents()
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)


def run(
    out_dir: Path,
    *,
    require_native_windows: bool,
) -> tuple[list[dict[str, object]], list[str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []
    errors: list[str] = []

    def record(name: str, passed: bool, detail: object = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            errors.append(f"{name}: {detail}")

    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")
    elif require_native_windows:
        error = "native Windows tab-switch paint evidence requires a win32 host"
        record("native-windows-host", False, error)
        _write_manifest(out_dir, checks, errors, [], qt_platform="unavailable")
        return checks, errors
    else:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:
        error = f"PyQt6 is required for native tab-switch evidence: {exc}"
        record("pyqt6-available", False, error)
        _write_manifest(out_dir, checks, errors, [], qt_platform="unavailable")
        return checks, errors

    app = QApplication.instance()
    if app is None:
        app = QApplication(["check-windows-tab-switch-paint"])
    qt_platform = QApplication.platformName().lower()
    is_native_windows = sys.platform == "win32" and qt_platform == "windows"
    record(
        "native-windows-qt-platform",
        is_native_windows or not require_native_windows,
        {"host": sys.platform, "qt_platform": qt_platform},
    )
    if require_native_windows and not is_native_windows:
        _write_manifest(out_dir, checks, errors, [], qt_platform=qt_platform)
        return checks, errors

    with tempfile.TemporaryDirectory(prefix="row-tab-paint-") as row_home:
        os.environ["ROW_HOME"] = row_home
        from remote_ops_workspace.gui import create_main_window
        from remote_ops_workspace.terminal import TerminalPanePlan

        app, window = create_main_window(
            ["check-windows-tab-switch-paint"],
            show=True,
            preview_samples=True,
        )
        window.set_design_preset("mobaxterm")
        screen = window.screen()
        available = screen.availableGeometry()
        width = max(900, min(1180, available.width() - 80))
        height = max(600, min(720, available.height() - 80))
        window.resize(width, height)
        window.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )
        window.raise_()
        window.activateWindow()
        _settle(app, 4)

        source_probe_text = (
            "SOURCE TERMINAL TAB - REAL PTY ALTERNATE-SCREEN REFERENCE\n"
            + "source geometry sentinel 0123456789\n" * 28
        )
        target_probe_text = (
            "TARGET TERMINAL TAB - REAL PTY ALTERNATE-SCREEN REFERENCE\n"
            + "target geometry sentinel ABCDEFGHIJ\n" * 28
        )

        def real_alternate_screen_plan(role: str, probe_text: str) -> TerminalPanePlan:
            producer = (
                "import sys,time\n"
                f"text={probe_text!r}\n"
                "sys.stdout.write('\\x1b[?1049h\\x1b[2J\\x1b[H'+text)\n"
                "sys.stdout.flush()\n"
                "try:\n"
                "  while True:\n"
                "    sys.stdout.write('\\x1b[H'+text)\n"
                "    sys.stdout.flush()\n"
                # A 40 Hz redraw is continuous and representative of ncurses,
                # while still leaving deterministic event turns for native
                # screenshot capture on constrained CI desktops.
                "    time.sleep(0.025)\n"
                "except (BrokenPipeError, KeyboardInterrupt):\n"
                "  pass\n"
            )
            producer_path = Path(row_home) / f"{role}-alternate-screen-producer.py"
            producer_path.write_text(producer, encoding="utf-8")
            command = [sys.executable, "-u", str(producer_path)]
            if sys.platform == "win32":
                # The production backend selects ConPTY for local shell
                # commands.  cmd.exe only launches the Python ANSI producer;
                # every captured redraw still crosses the actual ConPTY reader,
                # readyRead signal, UTF-8 batcher and terminal emulator.
                command = ["cmd.exe", "/d", "/q", "/c", *command]
            return TerminalPanePlan(
                title=f"Paint {role}",
                command=command,
                source="shell",
            )

        source = window.new_terminal_pane(
            real_alternate_screen_plan("source", source_probe_text),
            autostart=True,
        )
        target = window.new_terminal_pane(
            real_alternate_screen_plan("target", target_probe_text),
            autostart=True,
        )
        source.setProperty("tabPaintProbeRole", "source")
        target.setProperty("tabPaintProbeRole", "target")
        source.output.setStyleSheet(
            "QTextEdit#terminalOutput { background: #003366; color: #f4fbff; "
            "border: 4px solid #19a7ce; }"
        )
        target.output.setStyleSheet(
            "QTextEdit#terminalOutput { background: #663300; color: #fff8e8; "
            "border: 4px solid #ffb000; }"
        )
        source_index = window.add_workspace_tab(
            source, "Paint source", select=True, role="terminal"
        )
        target_index = window.add_workspace_tab(
            target, "Paint target", select=False, role="terminal"
        )
        for _attempt in range(200):
            _settle(app, 1)
            if (
                source.is_running()
                and target.is_running()
                and source.terminal_emulator.alternate_screen_active
                and target.terminal_emulator.alternate_screen_active
                and int(source.output.property("terminalOutputFlushCount") or 0) > 0
                and int(target.output.property("terminalOutputFlushCount") or 0) > 0
            ):
                break
            QTest.qWait(10)
        else:
            raise RuntimeError(
                "real process paint probes did not reach alternate-screen mode"
            )

        def stable_viewport_reference(pane, index: int):
            """Capture after live ConPTY redraw and viewport geometry settle."""

            window.tabs.setCurrentIndex(index)
            previous_geometry: tuple[object, ...] | None = None
            stable_turns = 0
            starting_flush_count = int(
                pane.output.property("terminalOutputFlushCount") or 0
            )
            for _attempt in range(240):
                _settle(app, 1)
                QTest.qWait(10)
                rect = _rect_payload(pane.output_viewport, window)
                scrollbar = pane.output.verticalScrollBar()
                geometry = (
                    rect["x"],
                    rect["y"],
                    rect["width"],
                    rect["height"],
                    scrollbar.isVisible(),
                    scrollbar.minimum(),
                    scrollbar.maximum(),
                    pane.output.document().size().width(),
                    pane.output.document().size().height(),
                )
                flush_count = int(
                    pane.output.property("terminalOutputFlushCount") or 0
                )
                if geometry == previous_geometry and flush_count > starting_flush_count:
                    stable_turns += 1
                else:
                    stable_turns = 0
                previous_geometry = geometry
                if stable_turns >= 4:
                    native_image = window.screen().grabWindow(
                        int(window.winId())
                    ).toImage()
                    return _crop_native_image(native_image, rect, window)
            raise RuntimeError(
                "real process terminal viewport did not stabilize before reference capture"
            )

        target_viewport_reference = stable_viewport_reference(target, target_index)
        source_viewport_reference = stable_viewport_reference(source, source_index)

        images: list[Path] = []
        frames: list[dict[str, object]] = []

        def capture_frame(
            name: str,
            *,
            interaction: str,
            stage: str,
        ) -> dict[str, object]:
            current = window.tabs.currentWidget()
            current_panes = (
                window.terminal_panes_in(current) if current is not None else []
            )
            pane = current_panes[0] if current_panes else None
            probe_panes = []
            for tab_index in range(window.tabs.count()):
                tab_widget = window.tabs.widget(tab_index)
                if tab_widget is None:
                    continue
                probe_panes.extend(
                    candidate
                    for candidate in window.terminal_panes_in(tab_widget)
                    if str(candidate.property("tabPaintProbeRole") or "")
                    in {"source", "target"}
                )
            visible_panes = [
                candidate for candidate in probe_panes if candidate.isVisibleTo(window)
            ]
            native_pixmap = window.screen().grabWindow(int(window.winId()))
            native_image = native_pixmap.toImage()
            viewport_rect = (
                _rect_payload(pane.output_viewport, window) if pane else {}
            )
            native_viewport = (
                _crop_native_image(native_image, viewport_rect, window)
                if viewport_rect
                else native_image.copy()
            )
            path = out_dir / f"tab-switch-{name}.png"
            saved = not native_pixmap.isNull() and native_pixmap.save(str(path))
            if saved:
                images.append(path)
            raw_prepaint_target = window.tabs.property("terminalTabPrepaintTargetIndex")
            prepaint_target_index = (
                raw_prepaint_target
                if isinstance(raw_prepaint_target, int)
                and not isinstance(raw_prepaint_target, bool)
                else -1
            )
            frame: dict[str, object] = {
                "name": name,
                "interaction": interaction,
                "stage": stage,
                "current_index": window.tabs.currentIndex(),
                "current_role": (
                    str(pane.property("tabPaintProbeRole") or "") if pane else ""
                ),
                "tabs": _rect_payload(window.tabs, window),
                "page": _rect_payload(pane, window) if pane else {},
                "output_viewport": viewport_rect,
                "page_visible": bool(pane and pane.isVisibleTo(window)),
                "alternate_screen_active": bool(
                    pane and pane.terminal_emulator.alternate_screen_active
                ),
                "live_process_redraw_active": bool(pane and pane.is_running()),
                "terminal_process_backend": (
                    str(pane.output.property("terminalProcessBackend") or "")
                    if pane
                    else ""
                ),
                "terminal_output_flush_count": (
                    int(pane.output.property("terminalOutputFlushCount") or 0)
                    if pane
                    else 0
                ),
                "visible_terminal_count": len(visible_panes),
                # Window chrome and tab labels legitimately change during a
                # transition. Compare the complete native terminal viewport;
                # the independent geometry gate rejects a centered miniature.
                "source_distance": round(
                    _image_distance(native_viewport, source_viewport_reference), 6
                ),
                "target_distance": round(
                    _image_distance(native_viewport, target_viewport_reference), 6
                ),
                "localized_source_distance": round(
                    _localized_image_distance(
                        native_viewport,
                        source_viewport_reference,
                    ),
                    6,
                ),
                "localized_target_distance": round(
                    _localized_image_distance(
                        native_viewport,
                        target_viewport_reference,
                    ),
                    6,
                ),
                "native_capture_saved": saved,
                "native_capture_size": [native_pixmap.width(), native_pixmap.height()],
                "prepaint_guard_active": bool(
                    window.tabs.property("terminalTabPrepaintGuardActive")
                ),
                "prepaint_target_index": prepaint_target_index,
                "transition_active": bool(
                    window.tabs.property("terminalTabTransitionActive")
                ),
                "active_tab_close_prepaint_guarded": bool(
                    window.tabs.property("terminalActiveTabClosePrepaintGuarded")
                ),
                "updates_enabled": window.tabs.updatesEnabled(),
            }
            frame["geometry_errors"] = validate_terminal_frame_geometry(frame)
            frames.append(frame)
            return frame

        capture_frame(
            "before-click",
            interaction="mouse-tab-switch",
            stage="before",
        )
        tab_bar = window.tabs.tabBar()
        target_point = tab_bar.tabRect(target_index).center()
        QTest.mouseMove(tab_bar, target_point)
        QTest.mousePress(
            tab_bar,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            target_point,
        )
        capture_frame(
            "mouse-pressed",
            interaction="mouse-tab-switch",
            stage="pressed",
        )
        QTest.mouseRelease(
            tab_bar,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            target_point,
        )
        capture_frame(
            "mouse-released",
            interaction="mouse-tab-switch",
            stage="released",
        )
        for turn in range(1, 7):
            _settle(app, 1)
            capture_frame(
                f"event-turn-{turn}",
                interaction="mouse-tab-switch",
                stage="settled",
            )
        mouse_selected_target = (
            window.tabs.currentIndex() == target_index
            and window.tabs.currentWidget() is target
        )

        window.tabs.setCurrentIndex(source_index)
        _settle(app, 4)
        capture_frame(
            "ctrl-tab-before",
            interaction="ctrl-tab-switch",
            stage="before",
        )
        active_page = window.tabs.currentWidget()
        if active_page is None:
            raise RuntimeError("Ctrl+Tab paint probe has no active source page")
        QTest.keyPress(
            active_page,
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ControlModifier,
        )
        capture_frame(
            "ctrl-tab-key-pressed",
            interaction="ctrl-tab-switch",
            stage="key-pressed",
        )
        QTest.keyRelease(
            active_page,
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.ControlModifier,
        )
        capture_frame(
            "ctrl-tab-key-released",
            interaction="ctrl-tab-switch",
            stage="key-released",
        )
        for turn in range(1, 7):
            _settle(app, 1)
            capture_frame(
                f"ctrl-tab-event-turn-{turn}",
                interaction="ctrl-tab-switch",
                stage="settled",
            )
        ctrl_tab_selected_target = window.tabs.currentWidget() is target

        window.tabs.setCurrentIndex(source_index)
        _settle(app, 4)
        window.tabs.setProperty("terminalActiveTabClosePrepaintGuarded", False)
        capture_frame(
            "active-close-before",
            interaction="active-tab-close",
            stage="before",
        )
        confirmed_close: list[tuple[str, int]] = []
        original_confirm_stop_processes = window.confirm_stop_processes

        def accept_probe_close(title: str, count: int) -> bool:
            confirmed_close.append((title, count))
            return title == "Close tab" and count == 1

        # Production keeps its interactive safety prompt. This unattended
        # native evidence harness deterministically accepts only the one close
        # action that it is explicitly exercising.
        window.confirm_stop_processes = accept_probe_close
        try:
            window.close_current_tab()
        finally:
            window.confirm_stop_processes = original_confirm_stop_processes
        source_removed = window.tabs.indexOf(source) == -1
        capture_frame(
            "active-close-returned",
            interaction="active-tab-close",
            stage="close-returned",
        )
        active_close_prepaint_guarded = bool(
            window.tabs.property("terminalActiveTabClosePrepaintGuarded")
        )
        for turn in range(1, 7):
            _settle(app, 1)
            capture_frame(
                f"active-close-event-turn-{turn}",
                interaction="active-tab-close",
                stage="settled",
            )
        successor_index = window.tabs.indexOf(target)
        active_close_exposed_target = (
            source_removed
            and successor_index >= 0
            and window.tabs.currentIndex() == successor_index
            and window.tabs.currentWidget() is target
        )

        geometry_errors = [
            f"{frame['name']}: {message}"
            for frame in frames
            for message in frame["geometry_errors"]  # type: ignore[union-attr]
        ]
        reference_errors = [
            f"{frame['name']}: frame differs from both stable terminal references"
            for frame in frames
            if not matches_stable_terminal_reference(
                source_distance=float(frame["source_distance"]),
                target_distance=float(frame["target_distance"]),
                localized_source_distance=float(frame["localized_source_distance"]),
                localized_target_distance=float(frame["localized_target_distance"]),
            )
        ]
        interaction_errors = validate_required_interaction_coverage(frames)
        settled_errors = validate_settled_interaction_frames(frames)
        active_close_contract_errors = validate_active_close_prepaint_contract(frames)
        alternate_screen_errors = validate_alternate_screen_frames(frames)
        native_capture_errors = [
            f"{frame['name']}: native Win32 window capture failed"
            for frame in frames
            if not frame["native_capture_saved"]
        ]

        record(
            "real-tab-bar-mouse-click-selected-target",
            mouse_selected_target,
            {
                "source_index": source_index,
                "target_index": target_index,
                "tab_point": [target_point.x(), target_point.y()],
            },
        )
        record(
            "ctrl-tab-shortcut-selected-target",
            ctrl_tab_selected_target,
            {
                "source_index": source_index,
                "target_index": target_index,
            },
        )
        record(
            "active-tab-close-exposed-stable-successor",
            active_close_exposed_target
            and not [
                error
                for error in settled_errors
                if error.startswith("active-tab-close/")
            ],
            {
                "source_removed": source_removed,
                "successor_index": successor_index,
                "current_index": window.tabs.currentIndex(),
                "current_role": (
                    str(target.property("tabPaintProbeRole") or "")
                    if successor_index >= 0
                    else ""
                ),
            },
        )
        record(
            "active-tab-close-prepaint-contract",
            active_close_prepaint_guarded
            and confirmed_close == [("Close tab", 1)]
            and not active_close_contract_errors,
            {
                "terminalActiveTabClosePrepaintGuarded": (
                    active_close_prepaint_guarded
                ),
                "confirmation_calls": confirmed_close,
                "errors": active_close_contract_errors,
            },
        )
        record(
            "required-tab-interactions-captured",
            not interaction_errors,
            {"errors": interaction_errors},
        )
        record(
            "real-process-alternate-screen-redraw-retained-across-transitions",
            not alternate_screen_errors and target.is_running(),
            {
                "errors": alternate_screen_errors,
                "target_backend": str(
                    target.output.property("terminalProcessBackend") or ""
                ),
                "target_flush_count": int(
                    target.output.property("terminalOutputFlushCount") or 0
                ),
            },
        )
        record(
            "tab-switch-frames-fill-terminal-workspace",
            not geometry_errors,
            {"errors": geometry_errors, "frames": frames},
        )
        record(
            "tab-switch-has-no-blank-or-miniature-paint",
            not reference_errors and not settled_errors,
            {"reference_errors": reference_errors, "settled_errors": settled_errors},
        )
        record(
            "native-window-frames-captured-every-event-turn",
            not native_capture_errors and len(images) == len(frames),
            {"errors": native_capture_errors, "frame_count": len(frames)},
        )
        record(
            "tab-prepaint-guard-completes",
            not bool(window.tabs.property("terminalTabPrepaintGuardActive"))
            and window.tabs.updatesEnabled(),
            {
                "guard_active": bool(
                    window.tabs.property("terminalTabPrepaintGuardActive")
                ),
                "updates_enabled": window.tabs.updatesEnabled(),
            },
        )

        # This is an unattended evidence command.  Stop both real producers
        # explicitly before closing the window so MainWindow never opens its
        # interactive "stop running processes" confirmation dialog.
        for pane in (source, target):
            if pane.is_running():
                pane.prepare_for_close()
                pane.process.kill()
        for _attempt in range(500):
            _settle(app, 1)
            if not source.is_running() and not target.is_running():
                break
            QTest.qWait(10)
        else:
            raise RuntimeError("real tab-paint producer did not stop during teardown")
        window.close()
        _settle(app, 2)
        _write_manifest(
            out_dir,
            checks,
            errors,
            images,
            qt_platform=qt_platform,
            frames=frames,
        )
    return checks, errors


def _write_manifest(
    out_dir: Path,
    checks: Sequence[dict[str, object]],
    errors: Sequence[str],
    images: Sequence[Path],
    *,
    qt_platform: str,
    frames: Sequence[dict[str, object]] = (),
) -> None:
    manifest = {
        "schema": "row.windows-tab-switch-paint.v4",
        "capture_mode": (
            "native-win32-real-conpty-alternate-screen-mouse-ctrl-tab-active-close-per-event-turn"
        ),
        "required_interactions": sorted(REQUIRED_INTERACTION_STAGES),
        "os": platform.platform(),
        "qt_platform_plugin": qt_platform,
        "checks": list(checks),
        "frames": list(frames),
        "images": [
            {"path": path.name, "bytes": path.stat().st_size}
            for path in images
            if path.is_file()
        ],
        "errors": list(errors),
    }
    (out_dir / "tab-switch-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    checks, errors = run(
        Path(args.out_dir),
        require_native_windows=args.require_native_windows,
    )
    for check in checks:
        state = "PASS" if check["passed"] else "FAIL"
        print(f"{state}: {check['name']}")
    if errors:
        for error in errors:
            print(f"native Windows tab-switch paint: {error}", file=sys.stderr)
        return 1
    print("native Windows tab-switch paint evidence passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
