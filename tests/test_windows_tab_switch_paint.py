from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_checker():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_windows_tab_switch_paint.py"
    spec = importlib.util.spec_from_file_location("check_windows_tab_switch_paint", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_size_frame() -> dict[str, object]:
    return {
        "tabs": {"width": 900, "height": 600},
        "page": {"width": 890, "height": 560},
        "output_viewport": {"width": 820, "height": 420},
        "visible_terminal_count": 1,
        "page_visible": True,
    }


def required_interaction_frames(checker) -> list[dict[str, object]]:
    return [
        {
            "name": f"{interaction}-{stage}",
            "interaction": interaction,
            "stage": stage,
            "current_role": "target",
            "target_distance": 0.0,
            "localized_target_distance": 0.0,
            "alternate_screen_active": True,
            "live_process_redraw_active": True,
            "terminal_output_flush_count": 1,
            "active_tab_close_prepaint_guarded": (
                interaction == "active-tab-close" and stage == "close-returned"
            ),
        }
        for interaction, stages in checker.REQUIRED_INTERACTION_STAGES.items()
        for stage in stages
    ]


def test_normalized_rgb_distance_distinguishes_matching_and_blank_frames() -> None:
    checker = load_checker()

    reference = [(0, 51, 102)] * 20
    blank = [(30, 30, 30)] * 20

    assert checker.normalized_rgb_distance(reference, reference) == 0.0
    assert checker.normalized_rgb_distance(reference, blank) > 0.05
    assert checker.normalized_rgb_distance([], []) == 1.0


def test_localized_distance_rejects_small_centered_corruption() -> None:
    checker = load_checker()
    width = 128
    height = 96
    reference = [(0, 51, 102)] * (width * height)
    corrupted = list(reference)
    for y in range(34, 46):
        for x in range(50, 62):
            corrupted[y * width + x] = (255, 255, 255)

    whole_frame_distance = checker.normalized_rgb_distance(corrupted, reference)
    localized_distance = checker.maximum_tiled_rgb_distance(
        corrupted,
        reference,
        width=width,
        height=height,
        tile_size=16,
    )

    assert whole_frame_distance < 0.01
    assert localized_distance > 0.20
    assert not checker.matches_stable_terminal_reference(
        source_distance=whole_frame_distance,
        target_distance=1.0,
        localized_source_distance=localized_distance,
        localized_target_distance=1.0,
    )


def test_native_image_distance_tolerates_only_scrollbar_sized_viewport_delta() -> None:
    from PyQt6.QtGui import QColor, QImage

    checker = load_checker()
    wide = QImage(220, 120, QImage.Format.Format_RGB32)
    narrow = QImage(208, 120, QImage.Format.Format_RGB32)
    miniature = QImage(120, 70, QImage.Format.Format_RGB32)
    for image in (wide, narrow, miniature):
        image.fill(QColor("#123456"))

    assert checker._image_distance(wide, narrow) == 0.0
    assert checker._localized_image_distance(wide, narrow) == 0.0
    assert checker._image_distance(wide, miniature) == 1.0
    assert checker._localized_image_distance(wide, miniature) == 1.0


def test_terminal_frame_geometry_rejects_center_mini_terminal() -> None:
    checker = load_checker()
    frame = full_size_frame()
    frame["page"] = {"width": 240, "height": 160}
    frame["output_viewport"] = {"width": 190, "height": 90}

    errors = checker.validate_terminal_frame_geometry(frame)

    assert any("page is transiently undersized" in error for error in errors)
    assert any("output viewport is transiently undersized" in error for error in errors)


def test_terminal_frame_geometry_accepts_full_workspace_terminal() -> None:
    checker = load_checker()

    assert checker.validate_terminal_frame_geometry(full_size_frame()) == []


def test_required_interaction_coverage_requires_every_route_and_stage() -> None:
    checker = load_checker()
    frames = required_interaction_frames(checker)

    assert checker.validate_required_interaction_coverage(frames) == []

    incomplete = [
        frame
        for frame in frames
        if not (
            frame["interaction"] == "ctrl-tab-switch"
            and frame["stage"] == "key-released"
        )
    ]
    errors = checker.validate_required_interaction_coverage(incomplete)

    assert errors == [
        "ctrl-tab-switch is missing capture stages: ['key-released']"
    ]


def test_settled_interaction_frames_fail_closed_on_wrong_or_miniature_target() -> None:
    checker = load_checker()
    frames = required_interaction_frames(checker)

    assert checker.validate_settled_interaction_frames(frames) == []

    settled = next(frame for frame in frames if frame["stage"] == "settled")
    settled["current_role"] = "source"
    settled["target_distance"] = checker.WHOLE_FRAME_DISTANCE_LIMIT + 0.001
    settled["localized_target_distance"] = (
        checker.LOCALIZED_TILE_DISTANCE_LIMIT + 0.001
    )
    errors = checker.validate_settled_interaction_frames(frames)

    assert any("target terminal is not active" in error for error in errors)
    assert any("whole-viewport paint did not settle" in error for error in errors)
    assert any("localized paint did not settle" in error for error in errors)


def test_active_close_contract_requires_close_returned_guard_evidence() -> None:
    checker = load_checker()
    frames = required_interaction_frames(checker)

    assert checker.validate_active_close_prepaint_contract(frames) == []

    for frame in frames:
        frame["active_tab_close_prepaint_guarded"] = False
    assert checker.validate_active_close_prepaint_contract(frames) == [
        "active-tab-close did not assert terminalActiveTabClosePrepaintGuarded"
    ]
    without_close_returned = [
        frame
        for frame in frames
        if not (
            frame["interaction"] == "active-tab-close"
            and frame["stage"] == "close-returned"
        )
    ]
    assert checker.validate_active_close_prepaint_contract(
        without_close_returned
    ) == ["active-tab-close has no close-returned evidence frame"]


def test_alternate_screen_contract_requires_every_captured_transition_frame() -> None:
    checker = load_checker()
    frames = required_interaction_frames(checker)

    assert checker.validate_alternate_screen_frames(frames) == []

    frames[0]["alternate_screen_active"] = False
    assert checker.validate_alternate_screen_frames(frames) == [
        f"{frames[0]['name']}: current terminal left alternate-screen mode"
    ]

    frames[0]["alternate_screen_active"] = True
    frames[0]["live_process_redraw_active"] = False
    frames[0]["terminal_output_flush_count"] = 0
    assert checker.validate_alternate_screen_frames(frames) == [
        f"{frames[0]['name']}: current terminal redraw process is not running",
        f"{frames[0]['name']}: no readyRead output batch reached the terminal",
    ]


def test_manifest_declares_v4_real_conpty_alternate_screen_native_capture_contract(
    tmp_path,
) -> None:
    checker = load_checker()

    checker._write_manifest(
        tmp_path,
        [],
        [],
        [],
        qt_platform="windows",
    )
    manifest = json.loads(
        (tmp_path / "tab-switch-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["schema"] == "row.windows-tab-switch-paint.v4"
    assert manifest["capture_mode"] == (
        "native-win32-real-conpty-alternate-screen-mouse-ctrl-tab-active-close-per-event-turn"
    )
    assert manifest["required_interactions"] == [
        "active-tab-close",
        "ctrl-tab-switch",
        "mouse-tab-switch",
    ]


def test_checker_uses_real_mouse_keyboard_close_and_native_captures() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "check_windows_tab_switch_paint.py"
    ).read_text(encoding="utf-8")

    assert "QTest.mousePress(" in source
    assert "QTest.mouseRelease(" in source
    assert "QTest.keyPress(" in source
    assert "QTest.keyRelease(" in source
    assert "Qt.Key.Key_Tab" in source
    assert "Qt.KeyboardModifier.ControlModifier" in source
    assert "window.close_current_tab()" in source
    assert "window.confirm_stop_processes = accept_probe_close" in source
    assert "window.confirm_stop_processes = original_confirm_stop_processes" in source
    assert '"terminalActiveTabClosePrepaintGuarded"' in source
    assert "tab_bar.tabRect(target_index).center()" in source
    assert "window.screen().grabWindow(int(window.winId()))" in source
    assert "localized_source_distance" in source
    assert "maximum_tiled_rgb_distance" in source
    assert '"active-tab-close-prepaint-contract"' in source
    assert (
        '"real-process-alternate-screen-redraw-retained-across-transitions"'
        in source
    )
    assert '"required-tab-interactions-captured"' in source
    assert '"row.windows-tab-switch-paint.v4"' in source
    assert (
        '"native-win32-real-conpty-alternate-screen-mouse-ctrl-tab-active-close-per-event-turn"'
        in source
    )
    assert 'command = ["cmd.exe", "/d", "/q", "/c", *command]' in source
    assert "pane.append_process_text" not in source
    assert "QPlainTextEdit" not in source
    assert "pane.prepare_for_close()" in source
    assert "pane.process.kill()" in source
    assert "stable_viewport_reference" in source
