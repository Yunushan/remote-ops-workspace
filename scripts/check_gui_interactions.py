from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import sys
import tempfile
from collections.abc import MutableMapping
from pathlib import Path

try:
    from check_real_gui_render import (
        collect_qt_font_render_evidence,
        default_qt_platform,
        prepare_preset_live_state,
        validate_non_overlapping_bounds,
        validate_qt_font_render_evidence,
    )
except ModuleNotFoundError:
    from scripts.check_real_gui_render import (
        collect_qt_font_render_evidence,
        default_qt_platform,
        prepare_preset_live_state,
        validate_non_overlapping_bounds,
        validate_qt_font_render_evidence,
    )

SUPPORTED_WINDOW_SIZES = ((1024, 768), (1180, 720), (1366, 768), (1420, 820), (1920, 1080))
PRODUCT_KEYS = (
    "refresh",
    "new",
    "import",
    "edit",
    "remove",
    "connect",
    "files",
    "queue",
    "dry-run",
    "doctor",
    "split-h",
    "split-v",
)
LAYOUT_KEYS = ("new-layout", "edit-layout", "remove-layout", "open-layout")
MOBA_KEYS = (
    "session",
    "servers",
    "tools",
    "games",
    "sessions",
    "view",
    "split",
    "multiexec",
    "tunneling",
    "packages",
    "settings",
    "help",
)
MENU_OPERATIONS = (
    ("mobaxterm", "terminal", "new-local-terminal"),
    ("mobaxterm", "sessions", "connect-selected"),
    ("mobaxterm", "view", "refresh-profiles"),
    ("mobaxterm", "x-server", "x-server-status"),
    ("mobaxterm", "tools", "tools-status"),
    ("mobaxterm", "games", "games-status"),
    ("mobaxterm", "settings", "settings-status"),
    ("mobaxterm", "macros", "macros-status"),
    ("mobaxterm", "help", "run-doctor"),
    ("securecrt", "file", "connect-selected"),
    ("securecrt", "edit", "focus-find"),
    ("securecrt", "view", "refresh-profiles"),
    ("securecrt", "options", "edit-selected-profile"),
    ("securecrt", "transfer", "open-sftp"),
    ("securecrt", "script", "script-status"),
    ("securecrt", "tools", "key-manager-status"),
    ("securecrt", "window", "split-horizontal"),
    ("securecrt", "help", "help-topics"),
    ("mremoteng", "file", "create-profile"),
    ("mremoteng", "view", "refresh-profiles"),
    ("mremoteng", "connections", "connect-selected"),
    ("mremoteng", "tools", "external-tools-status"),
    ("mremoteng", "window", "split-horizontal"),
    ("mremoteng", "help", "help-topics"),
)
PRODUCT_CALLBACK_CONTRACTS = {
    "refresh": ("refresh_profiles", ()),
    "new": ("create_profile", ()),
    "import": ("import_profiles_with_preview", ()),
    "edit": ("edit_selected_profile", ()),
    "remove": ("remove_selected_profile", ()),
    "connect": ("connect_selected", (False,)),
    "files": ("open_files_selected", ()),
    "queue": ("open_transfer_queue_selected", ()),
    "dry-run": ("connect_selected", (True,)),
    "doctor": ("show_doctor", ()),
    "split-h": ("add_split", ("horizontal",)),
    "split-v": ("add_split", ("vertical",)),
}
LAYOUT_CALLBACK_CONTRACTS = {
    "new-layout": ("create_layout", ()),
    "edit-layout": ("edit_selected_layout", ()),
    "remove-layout": ("remove_selected_layout", ()),
    "open-layout": ("open_selected_layout", ()),
}
MOBA_CALLBACK_CONTRACTS = {
    "session": ("create_profile", ()),
    "servers": ("show_moba_servers_status", ()),
    "tools": ("show_moba_tools_status", ()),
    "games": ("show_moba_games_status", ()),
    "sessions": ("connect_selected", (False,)),
    "view": ("cycle_design_preset", ()),
    "split": ("add_split", ("horizontal",)),
    "multiexec": ("show_moba_multiexec_status", ()),
    "tunneling": ("show_moba_tunneling_status", ()),
    "packages": ("show_moba_packages_dialog", ()),
    "settings": ("show_moba_settings_status", ()),
    "help": ("show_moba_help_dialog", ()),
}
MENU_CALLBACK_CONTRACTS = {
    ("mobaxterm", "terminal"): ("open_local_terminal_tab", ()),
    ("mobaxterm", "sessions"): ("connect_selected", (False,)),
    ("mobaxterm", "view"): ("refresh_profiles", ()),
    ("mobaxterm", "x-server"): ("show_moba_x_server_status", ()),
    ("mobaxterm", "tools"): ("show_moba_tools_status", ()),
    ("mobaxterm", "games"): ("show_moba_games_status", ()),
    ("mobaxterm", "settings"): ("show_moba_settings_status", ()),
    ("mobaxterm", "macros"): ("show_moba_macros_status", ()),
    ("mobaxterm", "help"): ("show_doctor", ()),
    ("securecrt", "file"): ("connect_selected", (False,)),
    ("securecrt", "edit"): ("focus_find_control", ()),
    ("securecrt", "view"): ("refresh_profiles", ()),
    ("securecrt", "options"): ("edit_selected_profile", ()),
    ("securecrt", "transfer"): ("open_files_selected", ()),
    ("securecrt", "script"): ("show_securecrt_script_status", ()),
    ("securecrt", "tools"): ("show_key_manager_status", ()),
    ("securecrt", "window"): ("add_split", ("horizontal",)),
    ("securecrt", "help"): ("show_moba_help_dialog", ()),
    ("mremoteng", "file"): ("create_profile", ()),
    ("mremoteng", "view"): ("refresh_profiles", ()),
    ("mremoteng", "connections"): ("connect_selected", (False,)),
    ("mremoteng", "tools"): ("show_external_tools_status", ()),
    ("mremoteng", "window"): ("add_split", ("horizontal",)),
    ("mremoteng", "help"): ("show_moba_help_dialog", ()),
}


def callback_matches_contract(
    callback,
    expected_method: str,
    expected_constants: tuple[object, ...],
) -> bool:
    bound_method = getattr(callback, "__func__", None)
    if bound_method is not None:
        return bound_method.__name__ == expected_method and not expected_constants
    code = getattr(callback, "__code__", None)
    if code is None or expected_method not in code.co_names:
        return False
    return all(value in code.co_consts for value in expected_constants)


def callback_contract_detail(callback) -> dict[str, object]:
    bound_method = getattr(callback, "__func__", None)
    if bound_method is not None:
        return {"bound_method": bound_method.__name__}
    code = getattr(callback, "__code__", None)
    if code is None:
        return {"callback_type": type(callback).__name__}
    return {
        "code_names": list(code.co_names),
        "constants": [repr(value) for value in code.co_consts],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exercise real PyQt GUI controls and responsive layouts."
    )
    parser.add_argument("--out-dir", default="artifacts/gui-interactions")
    parser.add_argument("--require-pyqt6", action="store_true")
    return parser.parse_args()


def color_luminance(color) -> float:
    channels = []
    for value in (color.redF(), color.greenF(), color.blueF()):
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first, second) -> float:
    lighter, darker = sorted((color_luminance(first), color_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def configure_qt_platform_environment(
    environ: MutableMapping[str, str] | None = None,
    *,
    system_platform: str | None = None,
) -> str:
    """Select the host-native Qt plugin unless the caller chose one explicitly."""

    target = os.environ if environ is None else environ
    return target.setdefault("QT_QPA_PLATFORM", default_qt_platform(system_platform))


def window_size_is_acceptable(
    actual: tuple[int, int],
    requested: tuple[int, int],
    minimum: tuple[int, int],
) -> bool:
    """Accept host-clamped windows while preserving the requested responsive bounds."""

    actual_width, actual_height = actual
    requested_width, requested_height = requested
    minimum_width, minimum_height = minimum
    return (
        minimum_width <= actual_width <= requested_width
        and minimum_height <= actual_height <= requested_height
    )


def validate_responsive_bounds(
    context: str,
    bounds: list[dict[str, int | str]],
    container: dict[str, int],
    *,
    horizontal_only: bool = False,
) -> list[str]:
    """Validate accepted responsive geometry without depending on screenshots."""

    if not horizontal_only:
        return validate_non_overlapping_bounds(context, bounds, container)
    errors: list[str] = []
    container_left = container["x"]
    container_right = container_left + container["width"]
    for item in bounds:
        label = str(item["id"])
        x = int(item["x"])
        width = int(item["width"])
        height = int(item["height"])
        if width <= 0 or height <= 0:
            errors.append(f"{context} {label} has empty geometry")
        elif x < container_left or x + width > container_right:
            errors.append(
                f"{context} {label} extends outside the horizontal viewport"
            )
    return errors


def run(out_dir: Path, *, require_pyqt6: bool) -> tuple[list[dict[str, object]], list[str]]:
    configure_qt_platform_environment()
    os.environ["ROW_HOME"] = tempfile.mkdtemp(prefix="row-gui-interactions-")
    try:
        from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, QPoint, Qt, QTimer
        from PyQt6.QtGui import QPalette
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import (
            QApplication,
            QComboBox,
            QDialogButtonBox,
            QFrame,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPlainTextEdit,
            QScrollArea,
            QSplitter,
            QTextEdit,
            QToolButton,
        )
    except Exception as exc:
        if require_pyqt6:
            return [], [f"PyQt6 is required: {exc}"]
        detail = f"PyQt6 unavailable; interaction evidence was not produced: {exc}"
        return [{"name": "pyqt6-available", "passed": False, "detail": detail}], [detail]

    import remote_ops_workspace.gui as gui_module
    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.gui_designs import (
        GUI_DESIGN_PRESETS,
        gui_design_interaction_state,
        gui_design_mremoteng_connection_document_route,
        gui_design_remmina_clipboard_route,
        gui_design_remmina_profile_viewer_route,
        gui_design_remmina_screenshot_route,
        gui_design_remmina_sftp_transfer_route,
        gui_design_securecrt_sftp_browser_route,
        gui_design_termius_files_browser_route,
        gui_design_toolbar_actions,
        gui_design_workspace_surface,
    )
    from remote_ops_workspace.gui_editors import (
        layout_from_editor_data,
        profile_editor_protocols,
        profile_from_editor_data,
    )
    from remote_ops_workspace.layouts import validate_layout
    from remote_ops_workspace.profile_importers import import_profiles
    from remote_ops_workspace.terminal import (
        TerminalPanePlan,
        terminal_plan_for_command,
        terminal_plan_for_profile,
        terminal_plan_for_sftp_browser,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, object]] = []
    errors: list[str] = []
    captured_images: list[Path] = []

    def record(name: str, passed: bool, detail: object = "") -> None:
        detail_snapshot = copy.deepcopy(detail)
        checks.append(
            {"name": name, "passed": bool(passed), "detail": detail_snapshot}
        )
        if not passed:
            errors.append(f"{name}: {detail_snapshot}")

    app = QApplication.instance()
    if app is None:
        app = QApplication(["check-gui-interactions-font-preflight"])
    font_render_evidence = collect_qt_font_render_evidence(app)
    font_render_payload = font_render_evidence.to_dict()
    font_render_errors = validate_qt_font_render_evidence(font_render_evidence)
    capture_mode = f"live-pyqt6-{font_render_evidence.platform_name.lower()}"
    record(
        "font-render-preflight",
        not font_render_errors,
        {
            "capture_mode": capture_mode,
            "font_render_evidence": font_render_payload,
            "errors": font_render_errors,
        },
    )
    if font_render_errors:
        screen = app.primaryScreen()
        manifest = {
            "schema": "row.gui-interaction-evidence.v1",
            "capture_mode": capture_mode,
            "os": platform.platform(),
            "qt_platform_plugin": QApplication.platformName(),
            "qt_platform_env": os.environ.get("QT_QPA_PLATFORM", "native"),
            "qt_version": QT_VERSION_STR,
            "pyqt_version": PYQT_VERSION_STR,
            "font_render_evidence": font_render_payload,
            "screen": {
                "size": (
                    [screen.size().width(), screen.size().height()]
                    if screen is not None
                    else None
                ),
                "logical_dpi": (
                    screen.logicalDotsPerInch() if screen is not None else None
                ),
                "device_pixel_ratio": (
                    screen.devicePixelRatio() if screen is not None else None
                ),
            },
            "supported_window_sizes": [list(size) for size in SUPPORTED_WINDOW_SIZES],
            "checks": checks,
            "images": [],
            "errors": errors,
        }
        (out_dir / "interaction-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return checks, errors

    def capture(name: str, widget) -> None:
        path = out_dir / name
        widget.update()
        QApplication.processEvents()
        widget.repaint()
        QApplication.processEvents()
        if widget is window and QApplication.platformName().lower() == "windows":
            widget.raise_()
            widget.activateWindow()
            QApplication.processEvents()
            pixmap = widget.screen().grabWindow(int(widget.winId()))
        else:
            pixmap = widget.grab()
        saved = pixmap.save(str(path))
        record(f"capture-{Path(name).stem}", saved, str(path))
        if saved:
            captured_images.append(path)

    app, window = create_main_window(["check-gui-interactions"], show=True)
    app.processEvents()

    def bounds_in(container, widgets) -> tuple[dict[str, int], list[dict[str, int | str]]]:
        container_origin = container.mapTo(window, QPoint(0, 0))
        container_bounds = {
            "x": container_origin.x(),
            "y": container_origin.y(),
            "width": container.width(),
            "height": container.height(),
        }
        bounds = []
        for index, widget in enumerate(widgets):
            origin = widget.mapTo(window, QPoint(0, 0))
            bounds.append(
                {
                    "id": widget.objectName() or f"widget-{index}",
                    "x": origin.x(),
                    "y": origin.y(),
                    "width": widget.width(),
                    "height": widget.height(),
                }
            )
        return container_bounds, bounds

    def record_responsive_bounds(
        name: str,
        container,
        widgets,
        *,
        horizontal_only: bool = False,
    ) -> None:
        visible = [widget for widget in widgets if widget is not None and widget.isVisible()]
        if container is None or not container.isVisible() or not visible:
            record(
                name,
                False,
                {
                    "container": container.objectName() if container is not None else "missing",
                    "visible_widget_count": len(visible),
                },
            )
            return
        container_bounds, bounds = bounds_in(container, visible)
        geometry_errors = validate_responsive_bounds(
            name,
            bounds,
            container_bounds,
            horizontal_only=horizontal_only,
        )
        record(
            name,
            not geometry_errors,
            {
                "container": container_bounds,
                "widgets": bounds,
                "errors": geometry_errors,
            },
        )

    def record_minimum_size_preset_geometry(preset_id: str) -> None:
        """Record live 1024-wide containment and non-overlap evidence per preset."""

        if preset_id == "mobaxterm":
            home_index = window.find_tab_by_role("home")
            if home_index >= 0:
                window.tabs.setCurrentIndex(home_index)
            for _ in range(4):
                app.processEvents()
            window.configure_welcome_responsiveness()
            app.processEvents()
            welcome_scroll = window.findChild(QScrollArea, "welcomeScroll")
            welcome_panel = window.findChild(QFrame, "mobaHomeWelcomeSurface")
            record_responsive_bounds(
                "mobaxterm-welcome-horizontal-containment-1024x768",
                welcome_scroll.viewport() if welcome_scroll is not None else None,
                [welcome_panel],
                horizontal_only=True,
            )
            record(
                "mobaxterm-welcome-no-horizontal-scrollbar-1024x768",
                welcome_scroll is not None
                and welcome_scroll.isVisible()
                and welcome_scroll.horizontalScrollBar().maximum() == 0
                and not welcome_scroll.horizontalScrollBar().isVisible(),
                {
                    "maximum": (
                        welcome_scroll.horizontalScrollBar().maximum()
                        if welcome_scroll is not None
                        else None
                    ),
                    "visible": (
                        welcome_scroll.horizontalScrollBar().isVisible()
                        if welcome_scroll is not None
                        else None
                    ),
                },
            )

        preparation_errors = prepare_preset_live_state(window, preset_id)
        for _ in range(4):
            app.processEvents()
        record(
            f"preset-reference-state-prepared-{preset_id}-1024x768",
            not preparation_errors,
            preparation_errors,
        )
        if preset_id not in {"native", "mobaxterm"}:
            workspace = window.findChild(QFrame, "productWorkspaceSurface")
            record_responsive_bounds(
                f"{preset_id}-workspace-horizontal-containment-1024x768",
                window.tabs,
                [workspace],
                horizontal_only=True,
            )

        if preset_id == "securecrt":
            panel = window.findChild(QFrame, "secureCrtSessionStatusStrip")
            record_responsive_bounds(
                "securecrt-session-status-cells-non-overlap-1024x768",
                panel,
                panel.findChildren(QLabel, "secureCrtSessionStatusCell") if panel else [],
            )
        elif preset_id == "termius":
            panel = window.findChild(QFrame, "termiusHostIdentityStrip")
            record_responsive_bounds(
                "termius-host-identity-cells-non-overlap-1024x768",
                panel,
                panel.findChildren(QLabel, "termiusHostIdentityCell") if panel else [],
            )
        elif preset_id == "remmina":
            profile_panel = window.findChild(QFrame, "remminaProfileListChrome")
            rows = (
                profile_panel.findChildren(QFrame, "remminaProfileListRow")
                if profile_panel is not None
                else []
            )
            for index, row in enumerate(rows):
                record_responsive_bounds(
                    f"remmina-profile-row-{index}-cells-non-overlap-1024x768",
                    row,
                    row.findChildren(QLabel, "remminaProfileListCell"),
                )
        elif preset_id == "mremoteng":
            grid = window.findChild(QFrame, "mRemoteNgPropertyGrid")
            rows = (
                grid.findChildren(QFrame, "mRemoteNgPropertyGridRow")
                if grid is not None
                else []
            )
            for index, row in enumerate(rows):
                record_responsive_bounds(
                    f"mremoteng-property-row-{index}-cells-non-overlap-1024x768",
                    row,
                    row.findChildren(QLabel, "mRemoteNgPropertyGridCell"),
                )
        elif preset_id == "mobaxterm":
            telemetry = None
            for index in range(window.tabs.count()):
                candidate = window.tabs.widget(index)
                candidate_telemetry = (
                    candidate.findChild(QFrame, "mobaTelemetryBar")
                    if candidate is not None
                    else None
                )
                if candidate_telemetry is not None:
                    window.tabs.setCurrentIndex(index)
                    telemetry = candidate_telemetry
                    break
            for _ in range(4):
                app.processEvents()
            if telemetry is None or not telemetry.isVisible():
                window.connect_selected(False)
                for _ in range(4):
                    app.processEvents()
                for index in range(window.tabs.count()):
                    candidate = window.tabs.widget(index)
                    candidate_telemetry = (
                        candidate.findChild(QFrame, "mobaTelemetryBar")
                        if candidate is not None
                        else None
                    )
                    if candidate_telemetry is not None:
                        window.tabs.setCurrentIndex(index)
                        telemetry = candidate_telemetry
                        break
                for _ in range(4):
                    app.processEvents()
            record_responsive_bounds(
                "mobaxterm-telemetry-cells-non-overlap-1024x768",
                telemetry,
                telemetry.findChildren(QFrame, "mobaTelemetryCell") if telemetry else [],
            )

    record(
        "product-key-cardinality",
        tuple(window.product_toolbar_button_by_key) == PRODUCT_KEYS,
        list(window.product_toolbar_button_by_key),
    )
    record(
        "product-callback-cardinality",
        tuple(window.product_toolbar_callbacks) == PRODUCT_KEYS,
        list(window.product_toolbar_callbacks),
    )
    record(
        "layout-callback-cardinality",
        tuple(window.layout_toolbar_callbacks) == LAYOUT_KEYS,
        list(window.layout_toolbar_callbacks),
    )
    record(
        "moba-callback-cardinality",
        tuple(window.moba_ribbon_callbacks) == MOBA_KEYS,
        list(window.moba_ribbon_callbacks),
    )

    window.set_design_preset("native")
    app.processEvents()
    for width, height in SUPPORTED_WINDOW_SIZES:
        window.resize(width, height)
        app.processEvents()
        actual_size = (window.width(), window.height())
        minimum_size = (window.minimumSizeHint().width(), window.minimumSizeHint().height())
        main_extension = window.main_toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        layout_extension = window.layout_toolbar.findChild(QToolButton, "qt_toolbar_ext_button")
        product_geometry = {
            key: (button.geometry().x(), button.width(), button.geometry().right())
            for key, button in window.product_toolbar_button_by_key.items()
        }
        auxiliary = [
            window.layout_label,
            window.layout_select,
            *window.layout_toolbar_buttons,
            window.view_label,
            window.design_select,
            window.search_input,
            window.find_button,
        ]
        product_in_bounds = all(
            button.isVisible()
            and window.toolbar_widget_action(button).isVisible()
            and 0 <= button.geometry().x()
            and button.geometry().right() < window.main_toolbar.width()
            for button in window.product_toolbar_buttons
        )
        auxiliary_in_bounds = all(
            widget.isVisible()
            and window.toolbar_widget_action(widget).isVisible()
            and 0 <= widget.geometry().x()
            and widget.geometry().right() < window.layout_toolbar.width()
            for widget in auxiliary
        )
        record(
            f"window-size-{width}x{height}",
            window_size_is_acceptable(actual_size, (width, height), minimum_size),
            {
                "actual": list(actual_size),
                "requested": [width, height],
                "minimum": list(minimum_size),
            },
        )
        record(f"product-toolbar-in-bounds-{width}", product_in_bounds, product_geometry)
        record(
            f"layout-toolbar-in-bounds-{width}",
            auxiliary_in_bounds,
            {
                widget.objectName() or type(widget).__name__: widget.geometry().getRect()
                for widget in auxiliary
            },
        )
        record(
            f"no-main-overflow-{width}",
            main_extension is None or not main_extension.isVisible(),
            main_extension.isVisible() if main_extension is not None else "not-created",
        )
        record(
            f"no-layout-overflow-{width}",
            layout_extension is None or not layout_extension.isVisible(),
            layout_extension.isVisible() if layout_extension is not None else "not-created",
        )

    preset_ids = [preset.id for preset in GUI_DESIGN_PRESETS]
    for preset_id in preset_ids:
        window.set_design_preset(preset_id)
        window.resize(1024, 768)
        app.processEvents()
        app.processEvents()
        preset_buttons = (
            [
                *window.moba_ribbon_buttons,
                window.moba_x_server_button,
                window.moba_exit_button,
            ]
            if preset_id == "mobaxterm"
            else list(window.product_toolbar_buttons)
        )
        preset_toolbar_geometry = {
            button.objectName(): {
                "x": button.geometry().x(),
                "right": button.geometry().right(),
                "width": button.width(),
                "visible": button.isVisible(),
                "action_visible": window.toolbar_widget_action(button).isVisible(),
            }
            for button in preset_buttons
        }
        preset_extension = window.main_toolbar.findChild(
            QToolButton,
            "qt_toolbar_ext_button",
        )
        record(
            f"preset-window-size-{preset_id}-1024x768",
            window_size_is_acceptable(
                (window.width(), window.height()),
                (1024, 768),
                (window.minimumSizeHint().width(), window.minimumSizeHint().height()),
            ),
            {
                "actual": [window.width(), window.height()],
                "requested": [1024, 768],
                "minimum": [window.minimumSizeHint().width(), window.minimumSizeHint().height()],
            },
        )
        record(
            f"preset-toolbar-fit-{preset_id}-1024x768",
            all(
                button.isVisible()
                and window.toolbar_widget_action(button).isVisible()
                and 0 <= button.geometry().x()
                and button.geometry().right() < window.main_toolbar.width()
                for button in preset_buttons
            ),
            {
                "toolbar_width": window.main_toolbar.width(),
                "buttons": preset_toolbar_geometry,
            },
        )
        record(
            f"preset-no-toolbar-extension-{preset_id}-1024x768",
            preset_extension is None or not preset_extension.isVisible(),
            preset_extension.isVisible() if preset_extension is not None else "not-created",
        )
        if preset_id != "mobaxterm":
            compact_controls = [
                *window.product_toolbar_buttons,
                *window.layout_toolbar_buttons,
                window.find_button,
            ]
            record(
                f"preset-toolbar-compact-label-semantics-{preset_id}-1024x768",
                all(
                    (
                        button.toolButtonStyle()
                        == Qt.ToolButtonStyle.ToolButtonIconOnly
                        and bool(button.text())
                        and bool(button.toolTip())
                        and button.accessibleName() == button.text()
                    )
                    or (
                        button.toolButtonStyle()
                        in {
                            Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
                            Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
                        }
                        and button.width() >= button.sizeHint().width()
                    )
                    for button in compact_controls
                ),
                {
                    button.text(): {
                        "style": button.toolButtonStyle().name,
                        "tooltip": button.toolTip(),
                        "accessible_name": button.accessibleName(),
                        "width": button.width(),
                        "preferred": button.sizeHint().width(),
                    }
                    for button in compact_controls
                },
            )
        window.resize(1180, 720)
        app.processEvents()
        app.processEvents()
        record(
            f"post-preset-window-size-{preset_id}-1180x720",
            window_size_is_acceptable(
                (window.width(), window.height()),
                (1180, 720),
                (window.minimumSizeHint().width(), window.minimumSizeHint().height()),
            ),
            {
                "actual": [window.width(), window.height()],
                "requested": [1180, 720],
                "minimum": [window.minimumSizeHint().width(), window.minimumSizeHint().height()],
            },
        )
        if preset_id != "mobaxterm":
            window.resize(1920, 1080)
            app.processEvents()
            app.processEvents()
            wide_extension = window.main_toolbar.findChild(
                QToolButton,
                "qt_toolbar_ext_button",
            )
            record(
                f"preset-toolbar-full-labels-fit-{preset_id}-1920x1080",
                all(
                    button.toolButtonStyle()
                    == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                    and button.width() >= button.sizeHint().width()
                    for button in window.product_toolbar_buttons
                )
                and (wide_extension is None or not wide_extension.isVisible()),
                {
                    "toolbar_width": window.main_toolbar.width(),
                    "buttons": {
                        button.text(): {
                            "style": button.toolButtonStyle().name,
                            "width": button.width(),
                            "preferred": button.sizeHint().width(),
                        }
                        for button in window.product_toolbar_buttons
                    },
                    "extension_visible": (
                        wide_extension.isVisible()
                        if wide_extension is not None
                        else False
                    ),
                },
            )
            window.resize(1180, 720)
            app.processEvents()
            app.processEvents()
        unintended_shells = [
            window.tabs.tabText(index)
            for index in range(window.tabs.count())
            if window.tabs.tabText(index).startswith("Shell ")
        ]
        record(
            f"preset-transition-no-unintended-shell-{preset_id}",
            not unintended_shells,
            unintended_shells,
        )
        expected = list(gui_design_toolbar_actions(preset_id))
        actual = [
            (
                str(button.property("productToolbarKey") or ""),
                button.text(),
                button.toolTip(),
            )
            for button in window.product_toolbar_buttons
        ]
        record(
            f"toolbar-copy-{preset_id}",
            actual == expected,
            {"expected": expected, "actual": actual},
        )
        product_visible = [
            window.toolbar_widget_action(button).isVisible()
            for button in window.product_toolbar_buttons
        ]
        moba_visible = [
            window.toolbar_widget_action(button).isVisible()
            for button in window.moba_ribbon_buttons
        ]
        if preset_id == "mobaxterm":
            record(f"preset-isolation-{preset_id}", all(moba_visible) and not any(product_visible))
        else:
            record(f"preset-isolation-{preset_id}", all(product_visible) and not any(moba_visible))

    for preset_id in [preset.id for preset in GUI_DESIGN_PRESETS]:
        window.set_design_preset(preset_id)
        app.processEvents()
        original_callbacks = dict(window.home_action_callbacks)
        expected_operations = (
            {
                "primary": "open-local-terminal",
                "secondary": "recover-previous-sessions",
            }
            if preset_id in {"native", "mobaxterm"}
            else {
                "primary": "connect-selected",
                "secondary": "create-profile",
            }
        )
        expected_contracts = (
            {
                "primary": ("open_local_terminal_tab", ()),
                "secondary": ("recover_previous_sessions", ()),
            }
            if preset_id in {"native", "mobaxterm"}
            else {
                "primary": ("connect_selected", (False,)),
                "secondary": ("create_profile", ()),
            }
        )
        callback_contracts_match = all(
            callback_matches_contract(
                original_callbacks[key],
                method_name,
                constants,
            )
            for key, (method_name, constants) in expected_contracts.items()
        )
        dispatched_home_actions: list[str] = []
        window.home_action_callbacks = {
            key: (
                lambda action_key=key, dispatched=dispatched_home_actions: dispatched.append(
                    action_key
                )
            )
            for key in ("primary", "secondary")
        }
        window.home_primary_action.click()
        window.home_secondary_action.click()
        app.processEvents()
        expected_labels = gui_design_workspace_surface(preset_id).home_actions[:2]
        record(
            f"home-actions-route-by-design-{preset_id}",
            callback_contracts_match
            and window.home_action_operations == expected_operations
            and (
                window.home_primary_action.text(),
                window.home_secondary_action.text(),
            )
            == expected_labels
            and window.home_primary_action.property("homeActionOperation")
            == expected_operations["primary"]
            and window.home_secondary_action.property("homeActionOperation")
            == expected_operations["secondary"]
            and dispatched_home_actions == ["primary", "secondary"],
            {
                "labels": [
                    window.home_primary_action.text(),
                    window.home_secondary_action.text(),
                ],
                "operations": dict(window.home_action_operations),
                "contracts": {
                    key: callback_contract_detail(callback)
                    for key, callback in original_callbacks.items()
                },
                "dispatched": dispatched_home_actions,
            },
        )
        window.home_action_callbacks = original_callbacks

    preset_by_id = {preset.id: preset for preset in GUI_DESIGN_PRESETS}
    cycle_tab = QSplitter()
    cycle_tab_title = "Preset cycle proof"
    window.add_workspace_tab(cycle_tab, cycle_tab_title, role="session")
    app.processEvents()
    preset_cycle_sequence = [
        "native",
        *(preset_id for preset_id in preset_ids if preset_id != "native"),
        "native",
    ]
    cycle_tooltip_details: list[dict[str, object]] = []
    nonfocused_tooltip_details: list[dict[str, object]] = []
    cycle_tooltips_clean = True
    nonfocused_tooltips_clean = True
    moba_quick_tooltip = ""
    moba_quick_base_tooltip = ""
    for preset_id in preset_cycle_sequence:
        window.set_design_preset(preset_id)
        app.processEvents()
        cycle_index = window.tabs.indexOf(cycle_tab)
        state = gui_design_interaction_state(preset_id)
        base_tooltip = window.base_tab_tooltip(cycle_index)
        expected_tooltip = (
            f"{cycle_tab_title}: {state.active_tab_status}"
            if state.active_tab_status
            else cycle_tab_title
        )
        actual_tooltip = window.literal_tab_tooltip(cycle_index)
        cycle_step_clean = (
            cycle_index >= 0
            and window.tabs.currentWidget() is cycle_tab
            and base_tooltip == cycle_tab_title
            and actual_tooltip == expected_tooltip
        )
        cycle_tooltips_clean = cycle_tooltips_clean and cycle_step_clean
        cycle_tooltip_details.append(
            {
                "preset": preset_id,
                "base": base_tooltip,
                "expected": expected_tooltip,
                "actual": actual_tooltip,
                "clean": cycle_step_clean,
            }
        )

        seen_focus_widgets: set[int] = set()
        for control_key, widget in window.focus_interaction_widgets().items():
            if id(widget) in seen_focus_widgets:
                continue
            seen_focus_widgets.add(id(widget))
            if not widget.isVisible() or control_key == state.focused_control:
                continue
            stored_base = widget.property("interactionBaseTooltip")
            expected_base = stored_base if isinstance(stored_base, str) else ""
            actual = widget.toolTip()
            control_clean = actual == expected_base
            nonfocused_tooltips_clean = nonfocused_tooltips_clean and control_clean
            nonfocused_tooltip_details.append(
                {
                    "preset": preset_id,
                    "control": control_key,
                    "base": expected_base,
                    "actual": actual,
                    "clean": control_clean,
                }
            )
        if preset_id == "mobaxterm":
            moba_quick_tooltip = window.quick_connect.toolTip()
            base_value = window.quick_connect.property("interactionBaseTooltip")
            moba_quick_base_tooltip = base_value if isinstance(base_value, str) else ""

    record(
        "preset-cycle-replaces-tab-status-without-accumulation",
        cycle_tooltips_clean,
        cycle_tooltip_details,
    )
    record(
        "preset-cycle-restores-visible-nonfocused-control-tooltips",
        nonfocused_tooltips_clean and bool(nonfocused_tooltip_details),
        nonfocused_tooltip_details,
    )
    native_state = gui_design_interaction_state("native")
    record(
        "moba-to-native-restores-quick-connect-base-tooltip",
        bool(moba_quick_tooltip)
        and moba_quick_tooltip != moba_quick_base_tooltip
        and window.quick_connect.toolTip() == moba_quick_base_tooltip
        and str(window.quick_connect.property("interactionState") or "") == "normal"
        and preset_by_id["mobaxterm"].label not in window.quick_connect.toolTip()
        and native_state.status_note not in window.quick_connect.toolTip(),
        {
            "moba": moba_quick_tooltip,
            "base": moba_quick_base_tooltip,
            "native": window.quick_connect.toolTip(),
            "state": window.quick_connect.property("interactionState"),
        },
    )
    cycle_tab_index = window.tabs.indexOf(cycle_tab)
    window.close_tab(cycle_tab_index)
    app.processEvents()

    window.set_design_preset("native")
    inactive_tab = QSplitter()
    active_tab = QSplitter()
    inactive_title = "Inactive runtime status proof"
    active_title = "Active runtime status proof"
    inactive_index = window.add_workspace_tab(inactive_tab, inactive_title, role="session")
    window.add_workspace_tab(active_tab, active_title, role="session")
    app.processEvents()
    native_inactive_tooltip = window.literal_tab_tooltip(inactive_index)
    window.set_design_preset("securecrt")
    app.processEvents()
    securecrt_inactive_index = window.tabs.indexOf(inactive_tab)
    securecrt_inactive_before_selection = window.literal_tab_tooltip(
        securecrt_inactive_index
    )
    window.tabs.setCurrentIndex(securecrt_inactive_index)
    app.processEvents()
    securecrt_state = gui_design_interaction_state("securecrt")
    expected_securecrt_tooltip = (
        f"{inactive_title}: {securecrt_state.active_tab_status}"
    )
    record(
        "tab-switch-refreshes-current-preset-runtime-status",
        native_inactive_tooltip
        == f"{inactive_title}: {gui_design_interaction_state('native').active_tab_status}"
        and securecrt_inactive_before_selection == native_inactive_tooltip
        and window.base_tab_tooltip(securecrt_inactive_index) == inactive_title
        and window.literal_tab_tooltip(securecrt_inactive_index)
        == expected_securecrt_tooltip
        and "running"
        not in window.literal_tab_tooltip(securecrt_inactive_index),
        {
            "native_inactive": native_inactive_tooltip,
            "securecrt_before_selection": securecrt_inactive_before_selection,
            "securecrt_after_selection": window.literal_tab_tooltip(
                securecrt_inactive_index
            ),
            "base": window.base_tab_tooltip(securecrt_inactive_index),
            "expected": expected_securecrt_tooltip,
        },
    )
    for proof_tab in (active_tab, inactive_tab):
        proof_index = window.tabs.indexOf(proof_tab)
        if proof_index >= 0:
            window.close_tab(proof_index)
            app.processEvents()

    split_source = QSplitter()
    split_source_title = "Split runtime base proof"
    window.set_design_preset("native")
    window.add_workspace_tab(
        split_source,
        split_source_title,
        role="layout",
    )
    window.set_design_preset("securecrt")
    app.processEvents()
    split_source_runtime_tooltip = window.literal_tab_tooltip(
        window.tabs.indexOf(split_source)
    )
    window.add_split("horizontal")
    app.processEvents()
    split_wrapper = window.tabs.currentWidget()
    split_wrapper_index = window.tabs.currentIndex()
    expected_split_base = f"{split_source_title} · Split H"
    immediate_split_base = window.base_tab_tooltip(split_wrapper_index)
    immediate_split_tooltip = window.literal_tab_tooltip(split_wrapper_index)
    expected_immediate_split_tooltip = (
        f"{expected_split_base}: {securecrt_state.active_tab_status}"
    )
    split_cycle_details: list[dict[str, object]] = []
    split_cycle_clean = True
    for preset_id in ("termius", "native", "securecrt"):
        window.set_design_preset(preset_id)
        app.processEvents()
        split_wrapper_index = window.tabs.indexOf(split_wrapper)
        state = gui_design_interaction_state(preset_id)
        expected = f"{expected_split_base}: {state.active_tab_status}"
        actual_base = window.base_tab_tooltip(split_wrapper_index)
        actual = window.literal_tab_tooltip(split_wrapper_index)
        step_clean = actual_base == expected_split_base and actual == expected
        split_cycle_clean = split_cycle_clean and step_clean
        split_cycle_details.append(
            {
                "preset": preset_id,
                "base": actual_base,
                "expected": expected,
                "actual": actual,
                "clean": step_clean,
            }
        )
    record(
        "split-preset-cycle-uses-stable-base-tooltip",
        split_source_runtime_tooltip
        == f"{split_source_title}: {securecrt_state.active_tab_status}"
        and isinstance(split_wrapper, QSplitter)
        and split_wrapper.widget(0) is split_source
        and immediate_split_base == expected_split_base
        and immediate_split_tooltip == expected_immediate_split_tooltip
        and window.tab_role(window.tabs.indexOf(split_wrapper)) == "split"
        and split_cycle_clean,
        {
            "source_runtime_tooltip": split_source_runtime_tooltip,
            "expected_base": expected_split_base,
            "immediate_base": immediate_split_base,
            "immediate_tooltip": immediate_split_tooltip,
            "expected_immediate_tooltip": expected_immediate_split_tooltip,
            "cycle": split_cycle_details,
        },
    )
    for pane in window.terminal_panes_in(split_wrapper):
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(window.tabs.indexOf(split_wrapper))
    app.processEvents()

    window.set_design_preset("termius")
    app.processEvents()
    snippet_activations: list[str] = []
    window.termius_snippet_shortcut.activated.connect(
        lambda: snippet_activations.append("activated")
    )
    window.log.append("termius-global-search-proof")
    window.search_input.setText("termius-global-search-proof")
    window.search_input.setFocus()
    app.processEvents()
    QTest.keyClick(window.search_input, Qt.Key.Key_Return)
    app.processEvents()
    record(
        "termius-search-return-does-not-trigger-snippet",
        snippet_activations == []
        and not bool(
            window.termius_snippet_action.property("termiusSnippetRouteLiveTriggered")
        )
        and window.statusBar().currentMessage()
        == "Found in activity log: termius-global-search-proof",
        {
            "snippet_activations": list(snippet_activations),
            "snippet_triggered": window.termius_snippet_action.property(
                "termiusSnippetRouteLiveTriggered"
            ),
            "status": window.statusBar().currentMessage(),
        },
    )
    window.termius_snippet_card.setFocus()
    app.processEvents()
    QTest.keyClick(window.termius_snippet_card, Qt.Key.Key_Return)
    app.processEvents()
    record(
        "termius-snippet-card-return-triggers-once",
        snippet_activations == ["activated"]
        and bool(
            window.termius_snippet_action.property("termiusSnippetRouteLiveTriggered")
        ),
        {
            "snippet_activations": list(snippet_activations),
            "snippet_triggered": window.termius_snippet_action.property(
                "termiusSnippetRouteLiveTriggered"
            ),
        },
    )

    def profile_leaf_visibility() -> dict[str, bool]:
        return {
            str(item.data(0, Qt.ItemDataRole.UserRole)): not item.isHidden()
            for item in window.iter_profile_tree_items()
            if isinstance(item.data(0, Qt.ItemDataRole.UserRole), str)
        }

    stored_profile_names = sorted(profile.name for profile in window.store.load())
    no_match_profile = stored_profile_names[0] if stored_profile_names else ""
    no_match_query = "__row_no_profile_match__"
    for preset_id, filter_object, proof_name in (
        (
            "securecrt",
            "secureCrtSessionFilter",
            "securecrt-no-match-filter-clears-stale-selection",
        ),
        (
            "termius",
            "termiusHostSearch",
            "termius-no-match-filter-clears-stale-selection",
        ),
        (
            "mremoteng",
            "mRemoteNgDocumentFilter",
            "mremoteng-no-match-filter-clears-stale-selection",
        ),
    ):
        window.set_design_preset(preset_id)
        app.processEvents()
        profile_filter = window.findChild(QLineEdit, filter_object)
        if profile_filter is None:
            record(
                proof_name,
                False,
                {"missing_filter": filter_object},
            )
            continue
        profile_filter.clear()
        window.select_profile(no_match_profile)
        window.update_profile_action_states()
        app.processEvents()
        selected_before = window.selected_profile_name()
        profile_filter.setText(no_match_query)
        app.processEvents()
        leaf_visibility = profile_leaf_visibility()
        selection_actions = {
            key: {
                "widget_enabled": window.product_toolbar_button_by_key[key].isEnabled(),
                "action_enabled": window.toolbar_widget_action(
                    window.product_toolbar_button_by_key[key]
                ).isEnabled(),
                "interaction_state": window.product_toolbar_button_by_key[key].property(
                    "interactionState"
                ),
            }
            for key in ("edit", "remove", "connect", "files", "queue", "dry-run")
        }
        record(
            proof_name,
            bool(no_match_profile)
            and selected_before == no_match_profile
            and window.profile_list.currentItem() is None
            and window.selected_profile_name() is None
            and bool(leaf_visibility)
            and not any(leaf_visibility.values())
            and all(
                not detail["widget_enabled"]
                and not detail["action_enabled"]
                and detail["interaction_state"] == "disabled"
                for detail in selection_actions.values()
            ),
            {
                "query": profile_filter.text(),
                "selected_before": selected_before,
                "selected_after": window.selected_profile_name(),
                "current_item_after": (
                    window.profile_list.currentItem().text(0)
                    if window.profile_list.currentItem() is not None
                    else None
                ),
                "leaf_visibility": leaf_visibility,
                "actions": selection_actions,
            },
        )
        profile_filter.clear()
        app.processEvents()

    window.set_design_preset("termius")
    app.processEvents()
    termius_filter = window.findChild(QLineEdit, "termiusHostSearch")
    termius_query = stored_profile_names[-1] if stored_profile_names else "missing-profile"
    termius_filter.setText(termius_query)
    app.processEvents()
    termius_before = profile_leaf_visibility()
    window.set_design_preset("native")
    app.processEvents()
    window.set_design_preset("termius")
    app.processEvents()
    termius_after = profile_leaf_visibility()
    record(
        "termius-filter-remains-applied-after-preset-round-trip",
        termius_filter.text() == termius_query
        and termius_before == termius_after
        and termius_before.get(termius_query) is True
        and any(not visible for visible in termius_before.values()),
        {
            "query": termius_filter.text(),
            "before": termius_before,
            "after": termius_after,
        },
    )
    termius_filter.clear()
    app.processEvents()

    window.set_design_preset("remmina")
    app.processEvents()
    remmina_filter = window.findChild(QLineEdit, "remminaProfileFilter")
    remmina_rows = window.remmina_profile_list_chrome.findChildren(
        QFrame,
        "remminaProfileListRow",
    )
    remmina_query = (
        str(remmina_rows[0].property("remminaProfileName") or "")
        if remmina_rows
        else "missing-profile"
    )
    remmina_filter.setText(remmina_query)
    app.processEvents()

    def remmina_row_visibility() -> dict[str, bool]:
        return {
            str(row.property("remminaProfileRowKey") or ""): row.isVisible()
            for row in remmina_rows
        }

    remmina_before = remmina_row_visibility()
    window.set_design_preset("native")
    app.processEvents()
    window.set_design_preset("remmina")
    app.processEvents()
    remmina_after = remmina_row_visibility()
    record(
        "remmina-filter-remains-applied-after-preset-round-trip",
        remmina_filter.text() == remmina_query
        and remmina_before == remmina_after
        and any(remmina_before.values())
        and any(not visible for visible in remmina_before.values()),
        {
            "query": remmina_filter.text(),
            "before": remmina_before,
            "after": remmina_after,
        },
    )
    remmina_filter.clear()
    app.processEvents()

    routed_file_action_cases = (
        (
            "termius",
            "termius_files_action_buttons",
            "termius_files_queue",
            "termiusFilesRouteActionKey",
            gui_design_termius_files_browser_route(),
        ),
        (
            "remmina",
            "remmina_sftp_transfer_action_buttons",
            "remmina_sftp_transfer_queue",
            "remminaSftpTransferRouteActionKey",
            gui_design_remmina_sftp_transfer_route(),
        ),
        (
            "securecrt",
            "securecrt_sftp_action_buttons",
            "securecrt_sftp_queue",
            "secureCrtSftpBrowserActionKey",
            gui_design_securecrt_sftp_browser_route(),
        ),
    )
    for preset_id, buttons_attribute, queue_attribute, key_property, route in (
        routed_file_action_cases
    ):
        window.set_design_preset(preset_id)
        app.processEvents()
        buttons = list(getattr(window, buttons_attribute, []))
        queue = getattr(window, queue_attribute, None)
        initial_action_keys = [
            str(button.property(key_property) or "") for button in buttons
        ]
        action_details: list[dict[str, object]] = []
        all_actions_routed = (
            len(buttons) == len(route.toolbar_actions)
            and tuple(initial_action_keys) == route.toolbar_actions
        )
        for action_index, button in enumerate(buttons):
            action_key = (
                route.toolbar_actions[action_index]
                if action_index < len(route.toolbar_actions)
                else initial_action_keys[action_index]
            )
            expected_status = (
                route.action_status
                if action_key == route.action_key
                else f"{action_key} queued"
            )
            button.click()
            app.processEvents()
            live_status = str(button.property(route.live_status_property) or "")
            action_routed = (
                action_key in route.toolbar_actions
                and bool(button.property(route.live_triggered_property))
                and button.property(route.live_action_property) == action_key
                and button.property(route.captured_action_property) == action_key
                and live_status == expected_status
                and button.property(route.captured_status_property)
                == expected_status
                and queue is not None
                and expected_status in queue.text()
                and action_key in window.statusBar().currentMessage().lower()
            )
            all_actions_routed = all_actions_routed and action_routed
            action_details.append(
                {
                    "action": action_key,
                    "initial_action_key": initial_action_keys[action_index],
                    "triggered": button.property(route.live_triggered_property),
                    "live_action": button.property(route.live_action_property),
                    "captured_action": button.property(
                        route.captured_action_property
                    ),
                    "live_status": live_status,
                    "expected_status": expected_status,
                    "queue": queue.text() if queue is not None else "missing",
                    "status_bar": window.statusBar().currentMessage(),
                    "passed": action_routed,
                }
            )
        record(
            f"{preset_id}-files-toolbar-all-actions-route-live",
            all_actions_routed,
            action_details,
        )

    window.set_design_preset("mremoteng")
    window.resize(1180, 720)
    app.processEvents()
    mremoteng_route = gui_design_mremoteng_connection_document_route()
    document_buttons = window.mremoteng_document_control_buttons
    save_button = document_buttons["save"]
    save_button.click()
    app.processEvents()
    document_artifact_name = str(
        save_button.property("mRemoteNgDocumentSaveArtifact") or ""
    )
    document_artifact = Path(
        str(save_button.property("mRemoteNgDocumentSaveArtifactPath") or "")
    )
    document_payload = (
        json.loads(document_artifact.read_text(encoding="utf-8"))
        if document_artifact.is_file()
        else {}
    )
    record(
        "mremoteng-save-writes-private-safe-document-artifact",
        bool(save_button.property("mRemoteNgDocumentSaveTriggered"))
        and document_artifact_name == document_artifact.name
        and Path(document_artifact_name).name == document_artifact_name
        and document_artifact.is_file()
        and document_artifact.stat().st_size > 0
        and Path(os.environ["ROW_HOME"]).resolve() in document_artifact.resolve().parents
        and document_payload.get("schema") == "row.gui.mremoteng-document.v1"
        and document_payload.get("state") == "saved"
        and set(document_payload.get("profile", {}))
        == {"name", "protocol", "target"}
        and "credential" not in document_artifact.read_text(encoding="utf-8").lower()
        and "password" not in document_artifact.read_text(encoding="utf-8").lower()
        and str(Path(os.environ["ROW_HOME"]).resolve())
        not in window.statusBar().currentMessage()
        and str(Path(os.environ["ROW_HOME"]).resolve()) not in window.log.toPlainText(),
        {
            "artifact": document_artifact_name,
            "bytes": (
                document_artifact.stat().st_size
                if document_artifact.is_file()
                else 0
            ),
            "payload": document_payload,
            "status": window.statusBar().currentMessage(),
        },
    )
    reconnect_button = document_buttons["reconnect"]
    reconnect_button.click()
    app.processEvents()
    record(
        "mremoteng-reconnect-routes-statefully",
        bool(reconnect_button.property(mremoteng_route.live_triggered_property))
        and reconnect_button.property(mremoteng_route.live_state_property)
        == mremoteng_route.reconnect_state
        and mremoteng_route.selected_profile_name
        in window.statusBar().currentMessage(),
        {
            "triggered": reconnect_button.property(
                mremoteng_route.live_triggered_property
            ),
            "state": reconnect_button.property(mremoteng_route.live_state_property),
            "status": window.statusBar().currentMessage(),
        },
    )
    external_dialog_state: dict[str, object] = {}

    def inspect_external_tools_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        preview = (
            dialog.findChild(QTextEdit, "workflowPreview")
            if dialog is not None
            else None
        )
        external_dialog_state.update(
            opened=dialog is not None,
            title=dialog.windowTitle() if dialog is not None else "",
            safe_boundary=(
                "never downloaded or executed implicitly" in preview.toPlainText()
                if preview is not None
                else False
            ),
        )
        if dialog is not None:
            dialog.accept()

    external_button = document_buttons["external-tool"]
    QTimer.singleShot(50, inspect_external_tools_dialog)
    external_button.click()
    record(
        "mremoteng-external-tool-opens-safe-workflow",
        external_dialog_state
        == {
            "opened": True,
            "title": "External Tools",
            "safe_boundary": True,
        }
        and bool(external_button.property("mRemoteNgExternalToolsWorkflowOpened")),
        {
            **external_dialog_state,
            "route_property": external_button.property(
                "mRemoteNgExternalToolsWorkflowOpened"
            ),
            "status": window.statusBar().currentMessage(),
        },
    )
    dock_button = document_buttons["dock-view"]
    property_grid = window.mremoteng_property_grid_panel
    dock_initial = (
        dock_button.isChecked(),
        property_grid.isVisibleTo(window),
        str(dock_button.property("interactionState") or ""),
    )
    dock_button.click()
    app.processEvents()
    dock_hidden = (
        not dock_button.isChecked()
        and not property_grid.isVisible()
        and property_grid.property("mRemoteNgDockViewVisible") is False
        and dock_button.property("interactionState") == "normal"
    )
    dock_button.click()
    app.processEvents()
    dock_restored = (
        dock_button.isChecked()
        and property_grid.isVisibleTo(window)
        and property_grid.property("mRemoteNgDockViewVisible") is True
        and dock_button.property("interactionState") == "checked"
    )
    record(
        "mremoteng-dock-view-toggles-real-grid-and-state",
        dock_initial == (True, True, "checked")
        and dock_hidden
        and dock_restored,
        {
            "initial": dock_initial,
            "hidden": dock_hidden,
            "restored": dock_restored,
            "status": window.statusBar().currentMessage(),
        },
    )

    window.set_design_preset("remmina")
    window.resize(1180, 720)
    app.processEvents()
    viewer_route = gui_design_remmina_profile_viewer_route()
    clipboard_route = gui_design_remmina_clipboard_route()
    screenshot_route = gui_design_remmina_screenshot_route()
    viewer_buttons = window.remmina_viewer_control_buttons
    fit_button = viewer_buttons["fit"]
    scale_button = viewer_buttons["scale-100"]
    fit_button.click()
    app.processEvents()
    fit_state = (
        fit_button.isChecked()
        and not scale_button.isChecked()
        and window.remmina_viewer_controls_panel.property(
            "remminaViewerScaleMode"
        )
        == "fit"
        and fit_button.property(viewer_route.control_active_property) == "true"
        and scale_button.property(viewer_route.control_active_property) == "false"
    )
    scale_button.click()
    app.processEvents()
    scale_state = (
        not fit_button.isChecked()
        and scale_button.isChecked()
        and window.remmina_viewer_controls_panel.property(
            "remminaViewerScaleMode"
        )
        == "scale-100"
        and fit_button.property(viewer_route.control_active_property) == "false"
        and scale_button.property(viewer_route.control_active_property) == "true"
    )
    record(
        "remmina-fit-scale-controls-are-exclusive-and-stateful",
        fit_state and scale_state,
        {
            "fit_state": fit_state,
            "scale_state": scale_state,
            "fit_checked": fit_button.isChecked(),
            "scale_checked": scale_button.isChecked(),
            "mode": window.remmina_viewer_controls_panel.property(
                "remminaViewerScaleMode"
            ),
        },
    )
    clipboard_button = viewer_buttons["clipboard"]
    clipboard_initial = clipboard_button.isChecked()
    clipboard_button.click()
    app.processEvents()
    clipboard_disabled = (
        not clipboard_button.isChecked()
        and clipboard_button.property(clipboard_route.clipboard_state_property)
        == "clipboard off"
        and clipboard_button.property(clipboard_route.control_active_property)
        == "false"
        and clipboard_button.property("interactionState") == "normal"
    )
    clipboard_button.click()
    app.processEvents()
    clipboard_restored = (
        clipboard_button.isChecked()
        and clipboard_button.property(clipboard_route.clipboard_state_property)
        == "clipboard on"
        and clipboard_button.property(clipboard_route.control_active_property)
        == "true"
        and clipboard_button.property("interactionState") == "checked"
    )
    record(
        "remmina-clipboard-control-toggles-and-restores",
        clipboard_initial and clipboard_disabled and clipboard_restored,
        {
            "initial": clipboard_initial,
            "disabled": clipboard_disabled,
            "restored": clipboard_restored,
            "state": clipboard_button.property(
                clipboard_route.clipboard_state_property
            ),
        },
    )
    fullscreen_button = viewer_buttons["fullscreen"]
    pre_fullscreen_size = window.size()
    fullscreen_button.click()
    app.processEvents()
    fullscreen_entered = (
        window.isFullScreen()
        and fullscreen_button.isChecked()
        and fullscreen_button.property("remminaViewerFullscreen") is True
        and fullscreen_button.property("interactionState") == "checked"
    )
    fullscreen_button.click()
    app.processEvents()
    fullscreen_restored = (
        not window.isFullScreen()
        and not fullscreen_button.isChecked()
        and fullscreen_button.property("remminaViewerFullscreen") is False
        and fullscreen_button.property("interactionState") == "normal"
    )
    window.resize(pre_fullscreen_size)
    app.processEvents()
    record(
        "remmina-fullscreen-control-enters-and-restores-real-window-state",
        fullscreen_entered and fullscreen_restored,
        {
            "entered": fullscreen_entered,
            "restored": fullscreen_restored,
            "window_state": int(window.windowState().value),
            "status": window.statusBar().currentMessage(),
        },
    )
    screenshot_button = viewer_buttons["screenshot"]
    screenshot_button.click()
    app.processEvents()
    screenshot_path = Path(
        str(screenshot_button.property("remminaScreenshotCapturePath") or "")
    )
    screenshot_valid = (
        bool(screenshot_button.property(screenshot_route.live_triggered_property))
        and screenshot_path.is_file()
        and screenshot_path.stat().st_size > 8
        and screenshot_button.property("remminaScreenshotCaptureBytes")
        == screenshot_path.stat().st_size
        and screenshot_path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        and Path(os.environ["ROW_HOME"]).resolve() in screenshot_path.resolve().parents
        and screenshot_button.property(
            screenshot_route.live_capture_artifact_property
        )
        == screenshot_route.capture_artifact
        and str(Path(os.environ["ROW_HOME"]).resolve())
        not in window.statusBar().currentMessage()
        and str(Path(os.environ["ROW_HOME"]).resolve()) not in window.log.toPlainText()
    )
    record(
        "remmina-screenshot-control-writes-real-private-png",
        screenshot_valid,
        {
            "artifact": screenshot_route.capture_artifact,
            "bytes": screenshot_path.stat().st_size if screenshot_path.is_file() else 0,
            "triggered": screenshot_button.property(
                screenshot_route.live_triggered_property
            ),
            "state": screenshot_button.property(
                screenshot_route.live_capture_state_property
            ),
            "status": window.statusBar().currentMessage(),
        },
    )

    original_ensure_data_dir = gui_module.ensure_data_dir
    denied_data_dir_calls: list[str] = []

    def deny_data_dir_directly() -> Path:
        denied_data_dir_calls.append("called")
        raise OSError("direct ROW_HOME denial proof")

    gui_module.ensure_data_dir = deny_data_dir_directly
    try:
        window.set_design_preset("mremoteng")
        app.processEvents()
        blocked_save_button = window.mremoteng_document_control_buttons["save"]
        blocked_save_button.click()
        app.processEvents()
        save_failed_closed = (
            blocked_save_button.property("mRemoteNgDocumentSaveTriggered") is False
            and bool(blocked_save_button.property("mRemoteNgDocumentSaveError"))
            and "not writable" in window.statusBar().currentMessage()
        )
        window.set_design_preset("remmina")
        app.processEvents()
        blocked_screenshot_button = window.remmina_viewer_control_buttons[
            "screenshot"
        ]
        blocked_screenshot_button.click()
        app.processEvents()
        screenshot_failed_closed = (
            not bool(
                blocked_screenshot_button.property(
                    screenshot_route.live_triggered_property
                )
            )
            and bool(
                blocked_screenshot_button.property(
                    "remminaScreenshotCaptureError"
                )
            )
            and "capture failed" in window.statusBar().currentMessage()
        )
    finally:
        gui_module.ensure_data_dir = original_ensure_data_dir
    record(
        "gui-artifact-write-errors-fail-closed-without-slot-exception",
        save_failed_closed
        and screenshot_failed_closed
        and len(denied_data_dir_calls) == 2,
        {
            "save_failed_closed": save_failed_closed,
            "screenshot_failed_closed": screenshot_failed_closed,
            "ensure_data_dir_calls": len(denied_data_dir_calls),
        },
    )

    for preset_id in ("native", "mobaxterm", "native"):
        window.set_design_preset(preset_id)
        app.processEvents()
    window.resize(1180, 720)
    app.processEvents()
    record(
        "preset-transition-native-moba-native",
        not any(
            window.toolbar_widget_action(button).isVisible()
            for button in window.moba_ribbon_buttons
        )
        and all(
            window.toolbar_widget_action(button).isVisible()
            for button in window.product_toolbar_buttons
        ),
    )
    record(
        "preset-transition-exact-1180x720",
        (window.width(), window.height()) == (1180, 720),
        [window.width(), window.height()],
    )

    dispatch_profile = profile_from_editor_data(
        {
            "name": "gui-dispatch-proof",
            "protocol": "ssh",
            "host": "example.invalid",
            "port": "22",
        }
    )
    window.store.add(dispatch_profile)
    window.refresh_profiles()
    window.select_profile(dispatch_profile.name)
    window.update_profile_action_states()
    dispatch_layout = layout_from_editor_data(
        {
            "name": "gui-dispatch-layout",
            "orientation": "horizontal",
            "description": "Interaction dispatch proof",
            "panes": "command:python -V | Version\ncommand:python --version | Version 2",
        }
    )
    window.layout_store.add(dispatch_layout)
    window.refresh_layouts()
    window.layout_select.setCurrentText(dispatch_layout.name)
    window.update_layout_action_states()

    nested_plans = [
        TerminalPanePlan(
            title=f"Nested pane {index + 1}",
            command=[sys.executable, "-c", f"print('nested-pane-{index + 1}')"],
            source=f"nested-proof-{index + 1}",
        )
        for index in range(5)
    ]
    nested_profiles = [
        dispatch_profile,
        None,
        dispatch_profile,
        None,
        dispatch_profile,
    ]
    nested_panes = [
        window.new_terminal_pane(plan, profile=profile)
        for plan, profile in zip(nested_plans, nested_profiles, strict=True)
    ]
    nested_inner_horizontal = QSplitter(Qt.Orientation.Horizontal)
    nested_inner_horizontal.addWidget(nested_panes[2])
    nested_inner_horizontal.addWidget(nested_panes[3])
    nested_inner_vertical = QSplitter(Qt.Orientation.Vertical)
    nested_inner_vertical.setProperty("savedLayoutName", "nested-five-pane-binding")
    nested_inner_vertical.addWidget(nested_panes[1])
    nested_inner_vertical.addWidget(nested_inner_horizontal)
    nested_root = QSplitter(Qt.Orientation.Horizontal)
    nested_root.addWidget(nested_panes[0])
    nested_root.addWidget(nested_inner_vertical)
    nested_root.addWidget(nested_panes[4])
    for nested_splitter in (
        nested_root,
        nested_inner_vertical,
        nested_inner_horizontal,
    ):
        nested_splitter.setChildrenCollapsible(False)
        for child_index in range(nested_splitter.count()):
            nested_splitter.setCollapsible(child_index, False)
            nested_splitter.setStretchFactor(child_index, 1)
    nested_title = "Nested five-pane proof"
    nested_source_index = window.add_workspace_tab(
        nested_root,
        nested_title,
        role="split",
    )
    app.processEvents()
    nested_inner_horizontal.setSizes([360, 140])
    nested_inner_vertical.setSizes([230, 470])
    nested_root.setSizes([180, 520, 260])
    app.processEvents()

    def nested_splitter_detail(widget) -> dict[str, object]:
        if not isinstance(widget, QSplitter):
            return {
                "kind": "pane",
                "title": widget.plan.title,
                "command": widget.plan.printable(),
                "profile": widget.profile.name if widget.profile is not None else None,
            }
        return {
            "kind": "splitter",
            "orientation": (
                "horizontal"
                if widget.orientation() == Qt.Orientation.Horizontal
                else "vertical"
            ),
            "sizes": widget.sizes(),
            "saved_layout_name": widget.property("savedLayoutName"),
            "children": [
                nested_splitter_detail(widget.widget(index))
                for index in range(widget.count())
            ],
        }

    def nested_splitter_matches(source, duplicate) -> bool:
        source_is_splitter = isinstance(source, QSplitter)
        duplicate_is_splitter = isinstance(duplicate, QSplitter)
        if source_is_splitter != duplicate_is_splitter:
            return False
        if not source_is_splitter:
            return (
                source.plan.printable() == duplicate.plan.printable()
                and source.plan.title == duplicate.plan.title
                and source.profile == duplicate.profile
            )
        if (
            source.orientation() != duplicate.orientation()
            or source.count() != duplicate.count()
            or source.property("savedLayoutName")
            != duplicate.property("savedLayoutName")
            or any(duplicate.isCollapsible(index) for index in range(duplicate.count()))
        ):
            return False
        source_sizes = source.sizes()
        duplicate_sizes = duplicate.sizes()
        if (
            len(source_sizes) != len(duplicate_sizes)
            or sum(source_sizes) <= 0
            or sum(duplicate_sizes) <= 0
            or any(
                abs(
                    source_size / sum(source_sizes)
                    - duplicate_size / sum(duplicate_sizes)
                )
                > 0.03
                for source_size, duplicate_size in zip(
                    source_sizes,
                    duplicate_sizes,
                    strict=True,
                )
            )
        ):
            return False
        return all(
            nested_splitter_matches(source.widget(index), duplicate.widget(index))
            for index in range(source.count())
        )

    tabs_before_nested_duplicate = window.tabs.count()
    window.duplicate_current_tab()
    app.processEvents()
    nested_duplicate_index = window.tabs.currentIndex()
    nested_duplicate = window.tabs.currentWidget()
    nested_duplicate_panes = window.terminal_panes_in(nested_duplicate)
    record(
        "nested-five-pane-duplicate-preserves-recursive-topology",
        isinstance(nested_duplicate, QSplitter)
        and window.tabs.count() == tabs_before_nested_duplicate + 1
        and window.tab_role(nested_duplicate_index) == "split"
        and window.tabs.tabText(nested_duplicate_index) == f"{nested_title} copy"
        and len(nested_duplicate_panes) == 5
        and nested_splitter_matches(nested_root, nested_duplicate)
        and f"TAB DUPLICATED: {nested_title}" in window.log.toPlainText(),
        {
            "source": nested_splitter_detail(nested_root),
            "duplicate": nested_splitter_detail(nested_duplicate),
            "duplicate_role": window.tab_role(nested_duplicate_index),
            "duplicate_title": window.tabs.tabText(nested_duplicate_index),
            "pane_count": len(nested_duplicate_panes),
        },
    )
    for pane in nested_duplicate_panes:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(nested_duplicate_index)
    app.processEvents()
    for pane in nested_panes:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    nested_source_index = window.tabs.indexOf(nested_root)
    window.close_tab(nested_source_index)
    app.processEvents()

    window.set_design_preset("securecrt")
    app.processEvents()
    expected_selected_state = gui_design_interaction_state("securecrt")
    window.profile_list.setCurrentItem(None)
    window.update_profile_action_states()
    disabled_after_clear = {
        key: str(window.product_toolbar_button_by_key[key].property("interactionState") or "")
        for key in ("edit", "remove", "connect", "files", "queue", "dry-run")
    }
    window.select_profile(dispatch_profile.name)
    window.update_profile_action_states()
    restored_states = {
        key: str(window.product_toolbar_button_by_key[key].property("interactionState") or "")
        for key in ("edit", "remove", "connect", "files", "queue", "dry-run")
    }
    record(
        "profile-selection-restores-preset-interaction-states",
        set(disabled_after_clear.values()) == {"disabled"}
        and restored_states[expected_selected_state.active_toolbar_key] == "active"
        and restored_states[expected_selected_state.checked_toolbar_key] == "checked"
        and window.product_toolbar_button_by_key[
            expected_selected_state.checked_toolbar_key
        ].isChecked(),
        {"disabled": disabled_after_clear, "restored": restored_states},
    )
    window.set_design_preset("native")
    app.processEvents()

    policy_calls: list[dict[str, str]] = []
    original_policy_check = gui_module.assert_profile_launch_allowed

    def block_profile_launch(profile, *, surface: str = "launcher", **_kwargs) -> None:
        policy_calls.append(
            {
                "name": profile.name,
                "surface": surface,
                "command": profile.command or "",
            }
        )
        raise ValueError("interaction policy proof")

    gui_module.assert_profile_launch_allowed = block_profile_launch
    try:
        guarded_pane = window.new_terminal_pane(
            gui_module.terminal_plan_for_profile(dispatch_profile),
            profile=dispatch_profile,
        )
        app.processEvents()
        first_guard_count = len(policy_calls)
        guarded_pane.restart()
        app.processEvents()
        record(
            "terminal-policy-guard-blocks-start-and-restart",
            first_guard_count == 1
            and len(policy_calls) == 2
            and not guarded_pane.is_running()
            and guarded_pane.status.text() == "policy blocked"
            and guarded_pane.status.property("state") == "blocked"
            and "interaction policy proof" in guarded_pane.output.toPlainText()
            and all(item["surface"] == "gui" for item in policy_calls),
            {
                "calls": list(policy_calls),
                "output": guarded_pane.output.toPlainText(),
                "status": guarded_pane.status.text(),
                "status_state": guarded_pane.status.property("state"),
            },
        )
        try:
            window.layout_launch_profiles(dispatch_layout)
            layout_policy_blocked = False
        except ValueError as exc:
            layout_policy_blocked = "interaction policy proof" in str(exc)
        record(
            "layout-command-policy-preflight",
            layout_policy_blocked
            and len(policy_calls) == 3
            and policy_calls[-1]["surface"] == "gui"
            and bool(policy_calls[-1]["command"]),
            list(policy_calls),
        )
        guarded_pane.deleteLater()
        app.processEvents()
    finally:
        gui_module.assert_profile_launch_allowed = original_policy_check

    literal_plan = TerminalPanePlan(
        title="<b>literal title</b>",
        command=[sys.executable, "-V", "<i>literal argument</i>"],
        source="<u>literal source</u>",
    )
    literal_pane = window.new_terminal_pane(literal_plan)
    app.processEvents()
    record(
        "terminal-user-text-is-literal-and-tooltip-safe",
        literal_pane.title.textFormat() == Qt.TextFormat.PlainText
        and literal_pane.source.textFormat() == Qt.TextFormat.PlainText
        and literal_pane.command_preview.textFormat() == Qt.TextFormat.PlainText
        and "&lt;u&gt;literal source&lt;/u&gt;" in literal_pane.source.toolTip()
        and "&lt;i&gt;literal argument&lt;/i&gt;" in literal_pane.command_preview.toolTip(),
        {
            "title": literal_pane.title.text(),
            "source_tooltip": literal_pane.source.toolTip(),
            "command_tooltip": literal_pane.command_preview.toolTip(),
        },
    )
    literal_pane.stop()
    literal_pane.deleteLater()
    app.processEvents()

    def record_callback_contracts(name: str, callbacks, contracts) -> None:
        details = {}
        passed = tuple(callbacks) == tuple(contracts)
        for key, (expected_method, expected_constants) in contracts.items():
            callback = callbacks.get(key)
            matched = callback is not None and callback_matches_contract(
                callback,
                expected_method,
                expected_constants,
            )
            passed = passed and matched
            details[str(key)] = {
                "expected_method": expected_method,
                "expected_constants": list(expected_constants),
                "matched": matched,
                "actual": (
                    callback_contract_detail(callback)
                    if callback is not None
                    else {"missing": True}
                ),
            }
        record(name, passed, details)

    record_callback_contracts(
        "product-original-callback-contracts",
        window.product_toolbar_callbacks,
        PRODUCT_CALLBACK_CONTRACTS,
    )
    record_callback_contracts(
        "layout-original-callback-contracts",
        window.layout_toolbar_callbacks,
        LAYOUT_CALLBACK_CONTRACTS,
    )
    record_callback_contracts(
        "moba-original-callback-contracts",
        window.moba_ribbon_callbacks,
        MOBA_CALLBACK_CONTRACTS,
    )
    menu_callbacks = {
        (preset_id, action_key): window.product_menu_callbacks[preset_id][action_key]
        for preset_id, action_key in MENU_CALLBACK_CONTRACTS
    }
    record_callback_contracts(
        "product-menu-original-callback-contracts",
        menu_callbacks,
        MENU_CALLBACK_CONTRACTS,
    )

    dispatched: list[str] = []
    window.product_toolbar_callbacks = {
        key: (lambda action_key=key: dispatched.append(action_key)) for key in PRODUCT_KEYS
    }
    record(
        "product-buttons-enabled-for-selected-profile",
        all(
            button.isEnabled() and window.toolbar_widget_action(button).isEnabled()
            for button in window.product_toolbar_buttons
        ),
        {key: button.isEnabled() for key, button in window.product_toolbar_button_by_key.items()},
    )
    for button in window.product_toolbar_buttons:
        button.click()
    record("product-click-dispatch", tuple(dispatched) == PRODUCT_KEYS, list(dispatched))

    dispatched.clear()
    window.layout_toolbar_callbacks = {
        key: (lambda action_key=key: dispatched.append(action_key)) for key in LAYOUT_KEYS
    }
    record(
        "layout-buttons-enabled-for-selected-layout",
        all(
            button.isEnabled() and window.toolbar_widget_action(button).isEnabled()
            for button in window.layout_toolbar_buttons
        ),
        {
            key: button.isEnabled()
            for key, button in zip(LAYOUT_KEYS, window.layout_toolbar_buttons, strict=True)
        },
    )
    layout_label_widths = {
        key: {
            "available": button.width(),
            "required": button.fontMetrics().horizontalAdvance(button.text())
            + button.iconSize().width()
            + 18,
            "style": button.toolButtonStyle().name,
            "accessible_name": button.accessibleName(),
            "tooltip": button.toolTip(),
        }
        for key, button in zip(LAYOUT_KEYS, window.layout_toolbar_buttons, strict=True)
    }
    record(
        "layout-button-labels-not-clipped",
        all(
            item["available"] >= item["required"]
            or (
                item["style"] == Qt.ToolButtonStyle.ToolButtonIconOnly.name
                and bool(item["accessible_name"])
                and bool(item["tooltip"])
            )
            for item in layout_label_widths.values()
        ),
        layout_label_widths,
    )
    for button in window.layout_toolbar_buttons:
        button.click()
    record("layout-click-dispatch", tuple(dispatched) == LAYOUT_KEYS, list(dispatched))

    window.set_design_preset("mobaxterm")
    app.processEvents()
    dispatched.clear()
    window.moba_ribbon_callbacks = {
        key: (lambda action_key=key: dispatched.append(action_key)) for key in MOBA_KEYS
    }
    record(
        "moba-buttons-enabled",
        all(
            button.isEnabled() and window.toolbar_widget_action(button).isEnabled()
            for button in window.moba_ribbon_buttons
        ),
        {
            key: button.isEnabled()
            for key, button in zip(MOBA_KEYS, window.moba_ribbon_buttons, strict=True)
        },
    )
    for button in window.moba_ribbon_buttons:
        button.click()
    record("moba-click-dispatch", tuple(dispatched) == MOBA_KEYS, dispatched)

    quick_connect_runs: list[object] = []
    original_quick_connect_runner = window.run_quick_connect_candidate_value
    window.run_quick_connect_candidate_value = quick_connect_runs.append
    window.quick_connect.setText(dispatch_profile.name)
    app.processEvents()
    quick_connect_item = window.quick_connect_suggestions.topLevelItem(0)
    if quick_connect_item is not None:
        window.quick_connect_suggestions.setCurrentItem(quick_connect_item)
        window.quick_connect_suggestions.setFocus()
        app.processEvents()
        # A Qt double-click gesture emits itemActivated and itemDoubleClicked.
        # Replaying that signal pair directly is deterministic under both the
        # offscreen and native Windows plugins and catches duplicate wiring.
        window.quick_connect_suggestions.itemActivated.emit(quick_connect_item, 0)
        window.quick_connect_suggestions.itemDoubleClicked.emit(quick_connect_item, 0)
        app.processEvents()
    record(
        "quick-connect-double-click-dispatches-once",
        len(quick_connect_runs) == 1,
        [getattr(candidate, "label", repr(candidate)) for candidate in quick_connect_runs],
    )
    quick_connect_runs.clear()
    if quick_connect_item is not None:
        window.quick_connect_suggestions.setCurrentItem(quick_connect_item)
        window.quick_connect_suggestions.setFocus()
        app.processEvents()
        window.quick_connect_suggestions.itemActivated.emit(quick_connect_item, 0)
        app.processEvents()
    record(
        "quick-connect-keyboard-activation-dispatches-once",
        len(quick_connect_runs) == 1,
        [getattr(candidate, "label", repr(candidate)) for candidate in quick_connect_runs],
    )
    window.run_quick_connect_candidate_value = original_quick_connect_runner

    all_product_menus = [
        *window.moba_top_menus,
        *window.securecrt_top_menus,
        *window.mremoteng_top_menus,
    ]
    routed_menu_actions = [
        action
        for menu in all_product_menus
        for action in menu.actions()
        if action.property("menuActionKey")
    ]
    record("menu-actions-have-routes", len(routed_menu_actions) == 24, len(routed_menu_actions))
    menu_operations = tuple(
        (
            str(action.property("menuActionFamily") or ""),
            str(action.property("menuActionKey") or ""),
            str(action.property("menuActionOperation") or ""),
        )
        for action in routed_menu_actions
    )
    record("menu-actions-match-operations", menu_operations == MENU_OPERATIONS, menu_operations)
    dispatched_menus: list[str] = []
    for family, callbacks in window.product_menu_callbacks.items():
        window.product_menu_callbacks[family] = {
            key: (lambda route=f"{family}:{key}": dispatched_menus.append(route))
            for key in callbacks
        }
    for action in routed_menu_actions:
        action.trigger()
    expected_menu_dispatch = [f"{family}:{key}" for family, key, _operation in MENU_OPERATIONS]
    record("menu-click-dispatch", dispatched_menus == expected_menu_dispatch, dispatched_menus)

    window.set_design_preset("native")
    window.resize(1180, 720)
    app.processEvents()
    record(
        "native-main-exact-1180x720-before-capture",
        (window.width(), window.height()) == (1180, 720),
        [window.width(), window.height()],
    )
    capture("native-1180x720.png", window)

    def inspect_profile_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            record("profile-dialog-open", False, "no active modal widget")
            return
        scroll = dialog.findChild(QScrollArea, "profileFormScroll")
        buttons = dialog.findChild(QDialogButtonBox, "profileDialogButtons")
        protocol = dialog.findChild(QComboBox, "profileProtocol")
        error = dialog.findChild(QLabel, "profileValidationError")
        preset_note = dialog.findChild(QLabel, "profileProtocolDefaultsNote")
        name = dialog.findChild(QLineEdit, "profileName")
        host = dialog.findChild(QLineEdit, "profileHost")
        record("profile-dialog-open", True, dialog.geometry().getRect())
        record(
            "profile-dialog-screen-bounds",
            dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
            {
                "dialog_frame": dialog.frameGeometry().getRect(),
                "screen": dialog.screen().availableGeometry().getRect(),
            },
        )
        record("profile-dialog-scroll", scroll is not None and scroll.widgetResizable())
        record(
            "profile-dialog-footer-visible",
            buttons is not None
            and buttons.isVisible()
            and buttons.geometry().bottom() < dialog.height(),
            buttons.geometry().getRect() if buttons is not None else None,
        )
        expected_protocols = profile_editor_protocols()
        actual_protocols = tuple(protocol.itemText(index) for index in range(protocol.count()))
        record("profile-protocol-catalog", actual_protocols == expected_protocols, actual_protocols)
        record(
            "profile-protocol-closed-catalog",
            not protocol.isEditable() and protocol.lineEdit() is None,
            {
                "editable": protocol.isEditable(),
                "has_line_edit": protocol.lineEdit() is not None,
            },
        )
        legacy_index = actual_protocols.index("ssh1")
        legacy_help = str(
            protocol.itemData(legacy_index, Qt.ItemDataRole.ToolTipRole) or ""
        )
        record(
            "profile-legacy-ssh-guidance-complete",
            all(
                token in legacy_help
                for token in (
                    "allow_insecure_sshv1=true",
                    "legacy_target=windows-xp-32",
                    "windows-xp-64",
                    "allow_legacy_crypto=true",
                    "isolated legacy systems",
                )
            ),
            legacy_help,
        )
        record(
            "profile-protocol-popup-limit",
            protocol.maxVisibleItems() == 8,
            protocol.maxVisibleItems(),
        )
        protocol.showPopup()
        app.processEvents()
        popup = QApplication.activePopupWidget() or protocol.view().window()
        view_palette = protocol.view().palette()
        ratio = contrast_ratio(
            view_palette.color(QPalette.ColorRole.Text),
            view_palette.color(QPalette.ColorRole.Base),
        )
        record("profile-protocol-popup-contrast", ratio >= 4.5, round(ratio, 3))
        popup_capture = popup if popup is not None and popup.isVisible() else protocol.view()
        capture("profile-protocol-popup.png", popup_capture)
        protocol.hidePopup()
        name.setText("gui-interaction-proof")
        host.clear()
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.click()
        app.processEvents()
        record(
            "profile-invalid-save-stays-open",
            dialog.isVisible() and error.isVisible() and "requires host" in error.text(),
            error.text(),
        )
        record(
            "profile-dialog-user-text-is-literal",
            error.textFormat() == Qt.TextFormat.PlainText
            and preset_note is not None
            and preset_note.textFormat() == Qt.TextFormat.PlainText,
            {
                "error_format": error.textFormat().name,
                "preset_note_format": (
                    preset_note.textFormat().name if preset_note is not None else "missing"
                ),
            },
        )
        capture("profile-dialog-invalid.png", dialog)
        dialog.reject()

    QTimer.singleShot(50, inspect_profile_dialog)
    window.create_profile()

    valid_state: dict[str, object] = {}
    literal_profile_name = "gui-<b>literal</b>-proof"

    def save_valid_profile() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            valid_state["error"] = "no active modal widget"
            return
        dialog.findChild(QLineEdit, "profileName").setText(literal_profile_name)
        dialog.findChild(QLineEdit, "profileHost").setText("example.invalid")
        buttons = dialog.findChild(QDialogButtonBox, "profileDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(50, save_valid_profile)
    window.create_profile()
    try:
        saved = window.store.get(literal_profile_name)
    except KeyError:
        saved = None
    record(
        "profile-valid-save",
        saved is not None
        and saved.host == "example.invalid"
        and window.selected_profile_name() == literal_profile_name,
        valid_state or (saved.to_dict() if saved is not None else "not saved"),
    )
    literal_profile_item = None
    literal_tree_root = window.profile_list.invisibleRootItem()
    literal_tree_pending = [
        literal_tree_root.child(index) for index in range(literal_tree_root.childCount())
    ]
    while literal_tree_pending and literal_profile_item is None:
        candidate_item = literal_tree_pending.pop(0)
        if candidate_item.data(0, Qt.ItemDataRole.UserRole) == literal_profile_name:
            literal_profile_item = candidate_item
            break
        literal_tree_pending.extend(
            candidate_item.child(index) for index in range(candidate_item.childCount())
        )
    literal_tree_tooltip = literal_profile_item.toolTip(0) if literal_profile_item else ""
    record(
        "profile-tree-user-tooltip-is-html-escaped",
        literal_profile_item is not None
        and "&lt;b&gt;literal&lt;/b&gt;" in literal_tree_tooltip
        and "<b>literal</b>" not in literal_tree_tooltip,
        {
            "item_text": literal_profile_item.text(0) if literal_profile_item else "missing",
            "tooltip": literal_tree_tooltip,
        },
    )
    literal_log_line = f"PROFILE LITERAL LOG: {literal_profile_name}"
    window.log.append(literal_log_line)
    record(
        "activity-log-user-text-is-literal",
        literal_log_line in window.log.toPlainText(),
        window.log.toPlainText().splitlines()[-1],
    )
    if saved is not None:
        literal_tab_plan = terminal_plan_for_command(
            "python -V",
            title=literal_profile_name,
        )
        window.open_terminal_tab(
            literal_tab_plan,
            profile=saved,
            tab_title=literal_profile_name,
            tab_status="literal tooltip proof",
        )
        app.processEvents()
        literal_tab_index = window.tabs.currentIndex()
        literal_tab_widget = window.tabs.currentWidget()
        literal_tab_raw_tooltip = literal_tab_widget.property("tabTooltipPlainText")
        literal_tab_rendered_tooltip = window.tabs.tabToolTip(literal_tab_index)
        record(
            "profile-tab-tooltip-keeps-raw-literal-and-escaped-rendering",
            literal_tab_raw_tooltip
            == f"{literal_profile_name}: literal tooltip proof"
            and "&lt;b&gt;literal&lt;/b&gt;" in literal_tab_rendered_tooltip
            and "<b>literal</b>" not in literal_tab_rendered_tooltip,
            {
                "raw": literal_tab_raw_tooltip,
                "rendered": literal_tab_rendered_tooltip,
            },
        )
        tabs_before_literal_duplicate = window.tabs.count()
        window.duplicate_current_tab()
        app.processEvents()
        literal_duplicate_index = window.tabs.currentIndex()
        literal_duplicate_widget = window.tabs.currentWidget()
        literal_duplicate_panes = window.terminal_panes_in(literal_duplicate_widget)
        literal_duplicate_raw_tooltip = literal_duplicate_widget.property(
            "tabTooltipPlainText"
        )
        literal_duplicate_rendered_tooltip = window.tabs.tabToolTip(
            literal_duplicate_index
        )
        record(
            "plain-terminal-duplicate-preserves-identity-and-literal-tooltip",
            window.tabs.count() == tabs_before_literal_duplicate + 1
            and window.tab_role(literal_duplicate_index) == "terminal"
            and window.tabs.tabText(literal_duplicate_index)
            == f"{literal_profile_name} copy"
            and len(literal_duplicate_panes) == 1
            and literal_duplicate_panes[0].profile == saved
            and literal_duplicate_panes[0].plan.printable()
            == literal_tab_plan.printable()
            and literal_duplicate_raw_tooltip
            == f"{literal_profile_name} copy: duplicated"
            and "&lt;b&gt;literal&lt;/b&gt;" in literal_duplicate_rendered_tooltip
            and "<b>literal</b>" not in literal_duplicate_rendered_tooltip
            and f"TAB DUPLICATED: {literal_profile_name}" in window.log.toPlainText(),
            {
                "tab_title": window.tabs.tabText(literal_duplicate_index),
                "profile": (
                    literal_duplicate_panes[0].profile.name
                    if literal_duplicate_panes
                    and literal_duplicate_panes[0].profile is not None
                    else None
                ),
                "command": (
                    literal_duplicate_panes[0].plan.printable()
                    if literal_duplicate_panes
                    else None
                ),
                "raw_tooltip": literal_duplicate_raw_tooltip,
                "rendered_tooltip": literal_duplicate_rendered_tooltip,
            },
        )
        for pane in literal_duplicate_panes:
            if pane.is_running():
                pane.process.kill()
                pane.process.waitForFinished(1000)
        window.close_tab(literal_duplicate_index)
        app.processEvents()
        literal_tab_panes = window.terminal_panes_in(literal_tab_widget)
        for pane in literal_tab_panes:
            if pane.is_running():
                pane.process.kill()
                pane.process.waitForFinished(1000)
        window.close_tab(literal_tab_index)
        app.processEvents()
    else:
        record(
            "profile-tab-tooltip-keeps-raw-literal-and-escaped-rendering",
            False,
            "literal profile was not saved",
        )

    duplicate_state: dict[str, object] = {}

    def inspect_duplicate_reopen() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            duplicate_state["error"] = "dialog did not reopen"
            return
        error = dialog.findChild(QLabel, "profileValidationError")
        name = dialog.findChild(QLineEdit, "profileName")
        duplicate_state.update(
            visible=dialog.isVisible(),
            error_visible=error.isVisible(),
            error_text=error.text(),
            name=name.text(),
            plain_text=error.textFormat() == Qt.TextFormat.PlainText,
        )
        dialog.reject()

    def submit_duplicate_profile() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            duplicate_state["error"] = "no first duplicate dialog"
            return
        dialog.findChild(QLineEdit, "profileName").setText(literal_profile_name)
        dialog.findChild(QLineEdit, "profileHost").setText("example.invalid")
        QTimer.singleShot(50, inspect_duplicate_reopen)
        buttons = dialog.findChild(QDialogButtonBox, "profileDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(50, submit_duplicate_profile)
    window.create_profile()
    record(
        "profile-duplicate-reopens",
        duplicate_state.get("visible") is True
        and duplicate_state.get("error_visible") is True
        and "already exists" in str(duplicate_state.get("error_text", ""))
        and literal_profile_name in str(duplicate_state.get("error_text", ""))
        and duplicate_state.get("name") == literal_profile_name
        and duplicate_state.get("plain_text") is True,
        duplicate_state,
    )

    def inspect_workflow_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            record("workflow-dialog-open", False, "no active modal widget")
            return
        title = dialog.findChild(QLabel, "workflowTitle")
        subtitle = dialog.findChild(QLabel, "workflowSubtitle")
        record(
            "workflow-dialog-screen-bounds",
            dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
            {
                "dialog_frame": dialog.frameGeometry().getRect(),
                "screen": dialog.screen().availableGeometry().getRect(),
            },
        )
        record(
            "workflow-dialog-user-text-is-literal",
            title is not None
            and subtitle is not None
            and title.text() == "<b>literal workflow title</b>"
            and subtitle.text() == "<i>literal workflow subtitle</i>"
            and title.textFormat() == Qt.TextFormat.PlainText
            and subtitle.textFormat() == Qt.TextFormat.PlainText,
            {
                "title": title.text() if title is not None else "missing",
                "title_format": title.textFormat().name if title is not None else "missing",
                "subtitle": subtitle.text() if subtitle is not None else "missing",
                "subtitle_format": (
                    subtitle.textFormat().name if subtitle is not None else "missing"
                ),
            },
        )
        dialog.reject()

    QTimer.singleShot(50, inspect_workflow_dialog)
    window.show_workflow_dialog(
        "<b>literal workflow title</b>",
        "<i>literal workflow subtitle</i>",
        [("Proof", "ready", "Dialog remains within its parent screen.")],
        "Literal workflow detail",
    )

    def inspect_transfer_queue_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            record("transfer-queue-dialog-open", False, "no active modal widget")
            return
        subtitle = dialog.findChild(QLabel, "workflowSubtitle")
        buttons = dialog.findChild(QDialogButtonBox, "transferQueueDialogButtons")
        record(
            "transfer-queue-dialog-screen-bounds",
            dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
            {
                "dialog_frame": dialog.frameGeometry().getRect(),
                "screen": dialog.screen().availableGeometry().getRect(),
            },
        )
        record(
            "transfer-queue-dialog-literal-sticky-footer",
            subtitle is not None
            and literal_profile_name in subtitle.text()
            and subtitle.textFormat() == Qt.TextFormat.PlainText
            and buttons is not None
            and buttons.isVisible()
            and buttons.geometry().bottom() < dialog.height(),
            {
                "subtitle": subtitle.text() if subtitle is not None else "missing",
                "subtitle_format": (
                    subtitle.textFormat().name if subtitle is not None else "missing"
                ),
                "buttons": buttons.geometry().getRect() if buttons is not None else None,
            },
        )
        dialog.reject()

    window.select_profile(literal_profile_name)
    QTimer.singleShot(50, inspect_transfer_queue_dialog)
    window.open_transfer_queue_selected()

    profile_import_source = Path(os.environ["ROW_HOME"]) / "profile-import-proof.json"
    profile_import_source.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "name": "import-<b>literal</b>-proof",
                        "protocol": "ssh",
                        "host": "import.example.invalid",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile_import_result = import_profiles(profile_import_source, source_format="auto")
    import_dialog = window.create_profile_import_preview_dialog(
        str(profile_import_source),
        profile_import_result,
    )

    def inspect_profile_import_dialog() -> None:
        source = import_dialog.findChild(QLabel, "profileImportSource")
        buttons = import_dialog.findChild(QDialogButtonBox, "profileImportDialogButtons")
        record(
            "profile-import-dialog-screen-bounds",
            import_dialog.screen().availableGeometry().contains(import_dialog.frameGeometry()),
            {
                "dialog_frame": import_dialog.frameGeometry().getRect(),
                "screen": import_dialog.screen().availableGeometry().getRect(),
            },
        )
        record(
            "profile-import-dialog-literal-sticky-footer",
            source is not None
            and source.textFormat() == Qt.TextFormat.PlainText
            and str(profile_import_source) in source.text()
            and buttons is not None
            and buttons.isVisible()
            and buttons.geometry().bottom() < import_dialog.height(),
            {
                "source": source.text() if source is not None else "missing",
                "source_format": source.textFormat().name if source is not None else "missing",
                "buttons": buttons.geometry().getRect() if buttons is not None else None,
            },
        )
        import_dialog.reject()

    QTimer.singleShot(50, inspect_profile_import_dialog)
    import_dialog.exec()

    def inspect_remove_profile_message() -> None:
        dialog = QApplication.activeModalWidget()
        expected_text = f"Remove profile {literal_profile_name}?"
        is_message = isinstance(dialog, QMessageBox)
        record(
            "remove-profile-message-user-text-is-literal",
            is_message
            and dialog.text() == expected_text
            and dialog.textFormat() == Qt.TextFormat.PlainText,
            {
                "text": dialog.text() if is_message else "missing",
                "format": dialog.textFormat().name if is_message else "missing",
            },
        )
        if is_message:
            dialog.done(int(QMessageBox.StandardButton.No))

    window.select_profile(literal_profile_name)
    QTimer.singleShot(50, inspect_remove_profile_message)
    window.remove_selected_profile()
    try:
        retained_literal_profile = window.store.get(literal_profile_name)
    except KeyError:
        retained_literal_profile = None
    record(
        "remove-profile-no-keeps-literal-profile",
        retained_literal_profile is not None,
        retained_literal_profile.to_dict() if retained_literal_profile is not None else "missing",
    )

    def inspect_invalid_layout_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            record("layout-dialog-open", False, "no active modal widget")
            return
        scroll = dialog.findChild(QScrollArea, "layoutFormScroll")
        buttons = dialog.findChild(QDialogButtonBox, "layoutDialogButtons")
        name = dialog.findChild(QLineEdit, "layoutName")
        panes_editor = dialog.findChild(QPlainTextEdit, "layoutPanes")
        error = dialog.findChild(QLabel, "layoutValidationError")
        record("layout-dialog-open", True, dialog.geometry().getRect())
        record(
            "layout-dialog-screen-bounds",
            dialog.screen().availableGeometry().contains(dialog.frameGeometry()),
            {
                "dialog_frame": dialog.frameGeometry().getRect(),
                "screen": dialog.screen().availableGeometry().getRect(),
            },
        )
        record("layout-dialog-scroll", scroll is not None and scroll.widgetResizable())
        record(
            "layout-dialog-footer-visible",
            buttons is not None
            and buttons.isVisible()
            and buttons.geometry().bottom() < dialog.height(),
            buttons.geometry().getRect() if buttons is not None else None,
        )
        name.setText("gui-invalid-layout")
        panes_editor.clear()
        buttons.button(QDialogButtonBox.StandardButton.Save).click()
        app.processEvents()
        record(
            "layout-invalid-save-stays-open",
            dialog.isVisible()
            and error.isVisible()
            and "requires at least one pane" in error.text(),
            error.text(),
        )
        record(
            "layout-dialog-user-text-is-literal",
            error.textFormat() == Qt.TextFormat.PlainText,
            {"error_format": error.textFormat().name, "error_text": error.text()},
        )
        capture("layout-dialog-invalid.png", dialog)
        dialog.reject()

    QTimer.singleShot(50, inspect_invalid_layout_dialog)
    window.create_layout()

    def save_valid_layout() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return
        dialog.findChild(QLineEdit, "layoutName").setText("gui-valid-layout")
        dialog.findChild(QPlainTextEdit, "layoutPanes").setPlainText("command:python -V | Version")
        buttons = dialog.findChild(QDialogButtonBox, "layoutDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(50, save_valid_layout)
    window.create_layout()
    try:
        valid_layout = window.layout_store.get("gui-valid-layout")
    except KeyError:
        valid_layout = None
    record(
        "layout-valid-save",
        valid_layout is not None and window.layout_select.currentText() == "gui-valid-layout",
        valid_layout.to_dict() if valid_layout is not None else "not saved",
    )

    duplicate_layout_state: dict[str, object] = {}

    def inspect_duplicate_layout_reopen() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            duplicate_layout_state["error"] = "dialog did not reopen"
            return
        error = dialog.findChild(QLabel, "layoutValidationError")
        name = dialog.findChild(QLineEdit, "layoutName")
        duplicate_layout_state.update(
            visible=dialog.isVisible(),
            error_visible=error.isVisible(),
            error_text=error.text(),
            name=name.text(),
        )
        dialog.reject()

    def submit_duplicate_layout() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            duplicate_layout_state["error"] = "no first duplicate dialog"
            return
        dialog.findChild(QLineEdit, "layoutName").setText("gui-valid-layout")
        dialog.findChild(QPlainTextEdit, "layoutPanes").setPlainText("command:python -V | Version")
        QTimer.singleShot(50, inspect_duplicate_layout_reopen)
        buttons = dialog.findChild(QDialogButtonBox, "layoutDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(50, submit_duplicate_layout)
    window.create_layout()
    record(
        "layout-duplicate-reopens",
        duplicate_layout_state.get("visible") is True
        and duplicate_layout_state.get("error_visible") is True
        and "already exists" in str(duplicate_layout_state.get("error_text", ""))
        and duplicate_layout_state.get("name") == "gui-valid-layout",
        duplicate_layout_state,
    )

    sized_layout = layout_from_editor_data(
        {
            "name": "gui-sized-layout",
            "orientation": "horizontal",
            "description": "Before edit",
            "panes": "command:python -V | Version\ncommand:python --version | Version 2",
        }
    )
    sized_layout.splitter_sizes = [[300, 200]]
    validate_layout(sized_layout)
    window.layout_store.add(sized_layout)
    window.refresh_layouts()
    window.layout_select.setCurrentText(sized_layout.name)

    def edit_sized_layout() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            return
        dialog.findChild(QPlainTextEdit, "layoutDescription").setPlainText("After edit")
        buttons = dialog.findChild(QDialogButtonBox, "layoutDialogButtons")
        buttons.button(QDialogButtonBox.StandardButton.Save).click()

    QTimer.singleShot(50, edit_sized_layout)
    window.edit_selected_layout()
    retained_layout = window.layout_store.get(sized_layout.name)
    record(
        "layout-edit-retains-compatible-splitter-sizes",
        retained_layout.description == "After edit"
        and retained_layout.splitter_sizes == [[300, 200]],
        retained_layout.to_dict(),
    )

    window.layout_select.setCurrentText(sized_layout.name)
    window.open_selected_layout()
    app.processEvents()
    saved_layout_widget = window.tabs.currentWidget()
    saved_splitters = window.layout_splitters(saved_layout_widget)
    edge_splitter = saved_splitters[0]
    edge_splitter.setCollapsible(0, True)
    edge_splitter.setSizes([0] + [500] * (edge_splitter.count() - 1))
    raw_edge_sizes = edge_splitter.sizes()
    window.persist_layout_resize_state(sized_layout.name, saved_layout_widget)
    edge_saved_layout = window.layout_store.get(sized_layout.name)
    try:
        validate_layout(edge_saved_layout)
        edge_saved_layout_valid = True
    except ValueError:
        edge_saved_layout_valid = False
    window.restore_layout_splitter_sizes(
        saved_layout_widget,
        edge_saved_layout.splitter_sizes,
    )
    record(
        "layout-zero-edge-resize-remains-valid-and-noncollapsible",
        bool(raw_edge_sizes)
        and raw_edge_sizes[0] == 0
        and edge_saved_layout_valid
        and all(
            size > 0
            for splitter_sizes in edge_saved_layout.splitter_sizes
            for size in splitter_sizes
        )
        and all(
            not splitter.isCollapsible(index)
            for splitter in saved_splitters
            for index in range(splitter.count())
        ),
        {
            "raw_edge_sizes": raw_edge_sizes,
            "persisted": edge_saved_layout.splitter_sizes,
            "noncollapsible": [
                [not splitter.isCollapsible(index) for index in range(splitter.count())]
                for splitter in saved_splitters
            ],
        },
    )
    window.tabs.setCurrentIndex(window.tabs.indexOf(saved_layout_widget))
    tabs_before_layout_duplicate = window.tabs.count()
    window.duplicate_current_tab()
    app.processEvents()
    duplicate_layout_widget = window.tabs.currentWidget()
    duplicate_layout_index = window.tabs.currentIndex()
    duplicate_layout_created = (
        window.tabs.count() == tabs_before_layout_duplicate + 1
        and window.tab_role(duplicate_layout_index) == "layout"
        and duplicate_layout_widget.property("savedLayoutName") == sized_layout.name
        and window.tabs.tabText(duplicate_layout_index) == f"{sized_layout.name} copy"
        and window.base_tab_tooltip(duplicate_layout_index)
        == f"{sized_layout.name} copy"
    )
    duplicate_title_before_rename = window.tabs.tabText(duplicate_layout_index)
    duplicate_base_before_rename = window.base_tab_tooltip(duplicate_layout_index)
    duplicate_tooltip_before_rename = window.literal_tab_tooltip(
        duplicate_layout_index
    )
    window.tabs.setCurrentIndex(window.tabs.indexOf(saved_layout_widget))
    app.processEvents()
    saved_layout_before_split = window.layout_store.get(sized_layout.name).to_dict()
    window.add_split("horizontal")
    app.processEvents()
    wrapped_split = window.tabs.currentWidget()
    saved_layout_after_split = window.layout_store.get(sized_layout.name)
    try:
        validate_layout(saved_layout_after_split)
        saved_layout_valid = True
    except ValueError:
        saved_layout_valid = False
    record(
        "saved-layout-split-is-transient-wrapper",
        isinstance(wrapped_split, QSplitter)
        and window.tab_role(window.tabs.currentIndex()) == "split"
        and wrapped_split.widget(0) is saved_layout_widget
        and saved_layout_after_split.to_dict() == saved_layout_before_split
        and saved_layout_valid,
        {
            "role": window.tab_role(window.tabs.currentIndex()),
            "stored": saved_layout_after_split.to_dict(),
        },
    )

    renamed_layout_name = "gui-sized-layout-renamed"
    renamed_layout = copy.deepcopy(saved_layout_after_split)
    renamed_layout.name = renamed_layout_name
    window.save_layout(renamed_layout, sized_layout.name)
    edge_splitter.setSizes([420, 180])
    edge_splitter.splitterMoved.emit(edge_splitter.sizes()[0], 1)
    app.processEvents()
    try:
        window.layout_store.get(sized_layout.name)
        old_layout_absent = False
    except KeyError:
        old_layout_absent = True
    persisted_renamed_layout = window.layout_store.get(renamed_layout_name)
    persisted_renamed_sizes = [
        [int(size) for size in splitter.sizes()]
        for splitter in window.layout_splitters(saved_layout_widget)
    ]
    renamed_size_proportions_match = (
        len(persisted_renamed_layout.splitter_sizes) == len(persisted_renamed_sizes)
        and all(
            len(stored_sizes) == len(live_sizes)
            and sum(stored_sizes) > 0
            and sum(live_sizes) > 0
            and all(
                abs(stored / sum(stored_sizes) - live / sum(live_sizes)) <= 0.02
                for stored, live in zip(stored_sizes, live_sizes, strict=True)
            )
            for stored_sizes, live_sizes in zip(
                persisted_renamed_layout.splitter_sizes,
                persisted_renamed_sizes,
                strict=True,
            )
        )
    )
    record(
        "wrapped-open-layout-rename-retargets-resize-persistence",
        old_layout_absent
        and window.tabs.currentWidget() is wrapped_split
        and wrapped_split.widget(0) is saved_layout_widget
        and saved_layout_widget.property("savedLayoutName") == renamed_layout_name
        and window.tabs.tabText(window.tabs.currentIndex()).startswith(renamed_layout_name)
        and window.literal_tab_tooltip(window.tabs.currentIndex()).startswith(
            renamed_layout_name
        )
        and persisted_renamed_layout.splitter_sizes != edge_saved_layout.splitter_sizes
        and renamed_size_proportions_match,
        {
            "old_absent": old_layout_absent,
            "widget_layout_name": saved_layout_widget.property("savedLayoutName"),
            "tab_title": window.tabs.tabText(window.tabs.currentIndex()),
            "tab_tooltip_plain": window.literal_tab_tooltip(window.tabs.currentIndex()),
            "stored_sizes": persisted_renamed_layout.splitter_sizes,
            "live_sizes": persisted_renamed_sizes,
            "proportions_match": renamed_size_proportions_match,
        },
    )
    duplicate_layout_index = window.tabs.indexOf(duplicate_layout_widget)
    duplicate_splitters = window.layout_splitters(duplicate_layout_widget)
    if duplicate_splitters and duplicate_splitters[0].count() == 2:
        duplicate_splitters[0].setSizes([160, 440])
        duplicate_splitters[0].splitterMoved.emit(
            duplicate_splitters[0].sizes()[0],
            1,
        )
        app.processEvents()
    duplicate_live_sizes = [
        [int(size) for size in splitter.sizes()]
        for splitter in duplicate_splitters
    ]
    duplicate_bound_layout = window.layout_store.get(renamed_layout_name)
    duplicate_resize_persisted = (
        len(duplicate_bound_layout.splitter_sizes) == len(duplicate_live_sizes)
        and bool(duplicate_live_sizes)
        and all(
            len(stored_sizes) == len(live_sizes)
            and sum(stored_sizes) > 0
            and sum(live_sizes) > 0
            and all(
                abs(stored / sum(stored_sizes) - live / sum(live_sizes)) <= 0.02
                for stored, live in zip(stored_sizes, live_sizes, strict=True)
            )
            for stored_sizes, live_sizes in zip(
                duplicate_bound_layout.splitter_sizes,
                duplicate_live_sizes,
                strict=True,
            )
        )
    )
    record(
        "duplicated-open-layout-rename-retargets-title-tooltip-and-binding",
        duplicate_layout_created
        and duplicate_layout_index >= 0
        and window.tab_role(duplicate_layout_index) == "layout"
        and duplicate_layout_widget.property("savedLayoutName")
        == renamed_layout_name
        and window.tabs.tabText(duplicate_layout_index)
        == f"{renamed_layout_name} copy"
        and window.base_tab_tooltip(duplicate_layout_index)
        == f"{renamed_layout_name} copy"
        and window.literal_tab_tooltip(duplicate_layout_index).startswith(
            f"{renamed_layout_name} copy:"
        )
        and not window.literal_tab_tooltip(duplicate_layout_index).startswith(
            f"{sized_layout.name} copy"
        )
        and duplicate_resize_persisted,
        {
            "before": {
                "title": duplicate_title_before_rename,
                "base": duplicate_base_before_rename,
                "tooltip": duplicate_tooltip_before_rename,
            },
            "after": {
                "title": window.tabs.tabText(duplicate_layout_index),
                "base": window.base_tab_tooltip(duplicate_layout_index),
                "tooltip": window.literal_tab_tooltip(duplicate_layout_index),
                "saved_layout_name": duplicate_layout_widget.property(
                    "savedLayoutName"
                ),
            },
            "stored_sizes": duplicate_bound_layout.splitter_sizes,
            "live_sizes": duplicate_live_sizes,
            "resize_persisted": duplicate_resize_persisted,
        },
    )
    for pane in window.terminal_panes_in(duplicate_layout_widget):
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(duplicate_layout_index)
    app.processEvents()

    recovery_profile_plan = terminal_plan_for_profile(dispatch_profile)
    recovery_sftp_plan = terminal_plan_for_sftp_browser(dispatch_profile)
    for recovery_preset, recovery_proof_name in (
        (
            "securecrt",
            "recovery-securecrt-preserves-profile-and-sftp-tab-identity",
        ),
        (
            "termius",
            "recovery-termius-preserves-profile-and-sftp-tab-identity",
        ),
        (
            "remmina",
            "recovery-remmina-preserves-profile-and-sftp-tab-identity",
        ),
        (
            "mremoteng",
            "recovery-mremoteng-preserves-profile-and-sftp-tab-identity",
        ),
    ):
        window.set_design_preset(recovery_preset)
        app.processEvents()
        existing_recovery_widgets = {
            id(window.tabs.widget(index))
            for index in range(window.tabs.count())
            if window.tabs.widget(index) is not None
        }
        window.recent_terminal_plans = [
            (recovery_profile_plan, dispatch_profile),
            (recovery_sftp_plan, dispatch_profile),
        ]
        tabs_before_recovery_pair = window.tabs.count()
        window.recover_previous_sessions()
        app.processEvents()
        recovered_entries = []
        for index in range(window.tabs.count()):
            widget = window.tabs.widget(index)
            if widget is None or id(widget) in existing_recovery_widgets:
                continue
            panes = window.terminal_panes_in(widget)
            if len(panes) == 1:
                recovered_entries.append((index, widget, panes[0]))
        recovered_profile_entry = next(
            (
                entry
                for entry in recovered_entries
                if entry[2].plan.source == f"profile:{dispatch_profile.name}"
            ),
            None,
        )
        recovered_sftp_entry = next(
            (
                entry
                for entry in recovered_entries
                if entry[2].plan.source == f"sftp:{dispatch_profile.name}"
            ),
            None,
        )
        expected_profile_title = window.profile_tab_label(dispatch_profile)
        expected_sftp_title = recovery_sftp_plan.title
        recovered_profile_tooltip = (
            window.literal_tab_tooltip(recovered_profile_entry[0])
            if recovered_profile_entry is not None
            else ""
        )
        recovered_sftp_tooltip = (
            window.literal_tab_tooltip(recovered_sftp_entry[0])
            if recovered_sftp_entry is not None
            else ""
        )
        if recovered_profile_entry is not None:
            window.tabs.setCurrentIndex(recovered_profile_entry[0])
            app.processEvents()
        current_profile_tooltip = (
            window.literal_tab_tooltip(window.tabs.indexOf(recovered_profile_entry[1]))
            if recovered_profile_entry is not None
            else ""
        )
        current_state = gui_design_interaction_state(recovery_preset)
        recovery_pair_clean = (
            window.tabs.count() == tabs_before_recovery_pair + 2
            and len(recovered_entries) == 2
            and recovered_profile_entry is not None
            and recovered_sftp_entry is not None
            and window.current_design_id() == recovery_preset
            and window.tab_role(window.tabs.indexOf(recovered_profile_entry[1]))
            == "terminal"
            and window.tab_role(window.tabs.indexOf(recovered_sftp_entry[1]))
            == "terminal"
            and window.tabs.tabText(window.tabs.indexOf(recovered_profile_entry[1]))
            == expected_profile_title
            and window.tabs.tabText(window.tabs.indexOf(recovered_sftp_entry[1]))
            == expected_sftp_title
            and window.base_tab_tooltip(
                window.tabs.indexOf(recovered_profile_entry[1])
            )
            == expected_profile_title
            and window.base_tab_tooltip(window.tabs.indexOf(recovered_sftp_entry[1]))
            == expected_sftp_title
            and recovered_profile_tooltip
            == f"{expected_profile_title}: recovered"
            and recovered_sftp_tooltip == f"{expected_sftp_title}: recovered"
            and current_profile_tooltip
            == f"{expected_profile_title}: {current_state.active_tab_status}"
            and recovered_profile_entry[2].profile == dispatch_profile
            and recovered_sftp_entry[2].profile == dispatch_profile
            and all(
                window.moba_connected_state_in_widget(entry[1]) is None
                for entry in recovered_entries
            )
            and window.moba_connected_dock is None
            and window.moba_left_stack.currentWidget() is window.profile_list
        )
        record(
            recovery_proof_name,
            recovery_pair_clean,
            {
                "active_preset": window.current_design_id(),
                "expected_profile_title": expected_profile_title,
                "expected_sftp_title": expected_sftp_title,
                "entries": [
                    {
                        "title": window.tabs.tabText(window.tabs.indexOf(entry[1])),
                        "base": window.base_tab_tooltip(
                            window.tabs.indexOf(entry[1])
                        ),
                        "tooltip": window.literal_tab_tooltip(
                            window.tabs.indexOf(entry[1])
                        ),
                        "source": entry[2].plan.source,
                        "moba_state": window.moba_connected_state_in_widget(entry[1])
                        is not None,
                    }
                    for entry in recovered_entries
                ],
                "profile_recovered_tooltip": recovered_profile_tooltip,
                "sftp_recovered_tooltip": recovered_sftp_tooltip,
                "profile_current_tooltip": current_profile_tooltip,
                "moba_dock_present": window.moba_connected_dock is not None,
            },
        )
        for _index, widget, pane in recovered_entries:
            if pane.is_running():
                pane.process.kill()
                pane.process.waitForFinished(1000)
            live_index = window.tabs.indexOf(widget)
            if live_index >= 0:
                window.close_tab(live_index)
                app.processEvents()

    activated: list[bool] = []
    window.connect_selected = lambda dry_run=False: activated.append(bool(dry_run))
    profile_item = None
    iterator = window.profile_list.invisibleRootItem()
    pending = [iterator.child(index) for index in range(iterator.childCount())]
    while pending and profile_item is None:
        item = pending.pop(0)
        if item.data(0, Qt.ItemDataRole.UserRole):
            profile_item = item
            break
        pending.extend(item.child(index) for index in range(item.childCount()))
    if profile_item is not None:
        window.activate_profile_item(profile_item)
    record("profile-tree-activation", activated == [False], activated)

    window.set_design_preset("mobaxterm")
    app.processEvents()
    moba_plan = terminal_plan_for_command("python -V", title="Moba split proof")
    window.open_moba_connected_session_tab(
        dispatch_profile,
        moba_plan,
        tab_title="Moba split proof",
    )
    app.processEvents()
    original_moba_panel = window.tabs.currentWidget()
    original_moba_tab_count = window.tabs.count()
    window.add_split("horizontal")
    app.processEvents()
    moba_panel_after_split = window.tabs.currentWidget()
    moba_split = (
        moba_panel_after_split.terminal_splitter
        if moba_panel_after_split is original_moba_panel
        else None
    )
    moba_split_state = window.moba_connected_state_in_widget(moba_panel_after_split)
    moba_split_route = window.moba_connected_session_action_route_for_tab(
        window.tabs.currentIndex()
    )
    moba_sizes = moba_split.sizes() if isinstance(moba_split, QSplitter) else []
    moba_panes = (
        window.terminal_panes_in(moba_split)
        if isinstance(moba_split, QSplitter)
        else []
    )
    moba_balanced = (
        len(moba_sizes) == 2
        and min(moba_sizes) > 0
        and min(moba_sizes) / max(moba_sizes) >= 0.85
    )
    record(
        "moba-connected-split-preserves-panel-and-tab",
        moba_panel_after_split is original_moba_panel
        and isinstance(moba_split, QSplitter)
        and window.tabs.count() == original_moba_tab_count
        and window.tab_role(window.tabs.currentIndex()) == "terminal"
        and len(moba_panes) == 2
        and all(pane.profile == dispatch_profile for pane in moba_panes)
        and all(pane.plan.printable() == moba_plan.printable() for pane in moba_panes)
        and moba_balanced
        and moba_split_state is not None
        and moba_split_route is not None
        and window.moba_connected_dock is not None
        and window.moba_left_stack.currentWidget() is window.moba_connected_dock,
        {
            "same_panel": moba_panel_after_split is original_moba_panel,
            "tab_count": window.tabs.count(),
            "original_tab_count": original_moba_tab_count,
            "tab_role": window.tab_role(window.tabs.currentIndex()),
            "splitter_sizes": moba_sizes,
            "balanced": moba_balanced,
            "panes": (
                len(moba_panes)
            ),
            "pane_profiles": [
                pane.profile.name if pane.profile is not None else None for pane in moba_panes
            ],
            "pane_commands": [pane.plan.printable() for pane in moba_panes],
            "state_preserved": moba_split_state is not None,
            "route_preserved": moba_split_route is not None,
            "dock_preserved": (
                window.moba_connected_dock is not None
                and window.moba_left_stack.currentWidget() is window.moba_connected_dock
            ),
        },
    )
    expected_moba_transcript = (
        "\n".join(line.text for line in moba_split_state.terminal_transcript)
        if moba_split_state is not None
        else ""
    )
    moba_plain_pane_details = [
        {
            "plain_mode": pane.property("mobaPlainTerminalMode"),
            "header_visible": pane.header.isVisible(),
            "command_visible": pane.command_row.isVisible(),
            "input_visible": pane.input.isVisible(),
            "connected_route": pane.property("mobaConnectedRouteKey"),
            "identity_route": pane.property("mobaConnectedIdentityRouteKey"),
            "sftp_route": pane.property("mobaSftpTerminalFolderRouteKey"),
            "route_target": pane.property("mobaConnectedRouteTarget"),
            "route_path": pane.property("mobaSftpTerminalFolderRoutePath"),
            "transcript": pane.output.toPlainText(),
        }
        for pane in moba_panes
    ]
    record(
        "moba-split-panes-preserve-plain-connected-identity",
        moba_split_state is not None
        and len(moba_panes) == 2
        and all(
            bool(pane.property("mobaPlainTerminalMode"))
            and bool(pane.output.property("mobaPlainTerminalMode"))
            and not pane.header.isVisible()
            and not pane.command_row.isVisible()
            and not pane.input.isVisible()
            and bool(pane.property("mobaConnectedRouteKey"))
            and bool(pane.property("mobaConnectedIdentityRouteKey"))
            and bool(pane.property("mobaSftpTerminalFolderRouteKey"))
            and pane.property("mobaConnectedRouteTarget") == moba_split_state.target
            and pane.property("mobaSftpTerminalFolderRoutePath")
            == moba_split_state.remote_path
            and pane.output.toPlainText().startswith(expected_moba_transcript)
            for pane in moba_panes
        ),
        moba_plain_pane_details,
    )

    tabs_before_duplicate = window.tabs.count()
    window.duplicate_current_tab()
    app.processEvents()
    duplicate_tab_index = window.tabs.currentIndex()
    duplicate_moba_panel = window.tabs.currentWidget()
    duplicate_moba_state = window.moba_connected_state_in_widget(duplicate_moba_panel)
    duplicate_moba_panes = window.terminal_panes_in(duplicate_moba_panel)
    duplicate_moba_split = getattr(duplicate_moba_panel, "terminal_splitter", None)
    duplicate_moba_sizes = (
        duplicate_moba_split.sizes()
        if isinstance(duplicate_moba_split, QSplitter)
        else []
    )
    duplicate_size_proportions_match = (
        len(duplicate_moba_sizes) == len(moba_sizes)
        and sum(duplicate_moba_sizes) > 0
        and sum(moba_sizes) > 0
        and all(
            abs(
                duplicate_size / sum(duplicate_moba_sizes)
                - source_size / sum(moba_sizes)
            )
            <= 0.02
            for duplicate_size, source_size in zip(
                duplicate_moba_sizes,
                moba_sizes,
                strict=True,
            )
        )
    )
    record(
        "moba-connected-duplicate-preserves-identity-path-and-dock",
        moba_split_state is not None
        and duplicate_moba_state is not None
        and window.tabs.count() == tabs_before_duplicate + 1
        and window.tab_role(duplicate_tab_index) == "terminal"
        and duplicate_moba_state.profile_name == moba_split_state.profile_name
        and duplicate_moba_state.target == moba_split_state.target
        and duplicate_moba_state.remote_path == moba_split_state.remote_path
        and isinstance(duplicate_moba_split, QSplitter)
        and isinstance(moba_split, QSplitter)
        and duplicate_moba_split.orientation() == moba_split.orientation()
        and len(duplicate_moba_panes) == len(moba_panes)
        and duplicate_size_proportions_match
        and all(pane.profile == dispatch_profile for pane in duplicate_moba_panes)
        and all(
            pane.plan.printable() == moba_plan.printable()
            for pane in duplicate_moba_panes
        )
        and all(
            bool(pane.property("mobaPlainTerminalMode"))
            and not pane.header.isVisible()
            and not pane.command_row.isVisible()
            and not pane.input.isVisible()
            and pane.property("mobaConnectedRouteTarget") == duplicate_moba_state.target
            and pane.property("mobaSftpTerminalFolderRoutePath")
            == duplicate_moba_state.remote_path
            for pane in duplicate_moba_panes
        )
        and window.moba_connected_dock is not None
        and window.moba_left_stack.currentWidget() is window.moba_connected_dock
        and window.moba_connected_dock.state.target == duplicate_moba_state.target
        and window.moba_connected_dock.state.remote_path == duplicate_moba_state.remote_path,
        {
            "tab_role": window.tab_role(duplicate_tab_index),
            "tab_count": window.tabs.count(),
            "state": duplicate_moba_state.to_dict() if duplicate_moba_state is not None else None,
            "pane_profiles": [
                pane.profile.name if pane.profile is not None else None
                for pane in duplicate_moba_panes
            ],
            "pane_commands": [pane.plan.printable() for pane in duplicate_moba_panes],
            "source_sizes": moba_sizes,
            "duplicate_sizes": duplicate_moba_sizes,
            "size_proportions_match": duplicate_size_proportions_match,
        },
    )
    for pane in duplicate_moba_panes:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(duplicate_tab_index)
    app.processEvents()
    window.tabs.setCurrentIndex(window.tabs.indexOf(original_moba_panel))
    app.processEvents()

    window.set_design_preset("native")
    app.processEvents()
    native_source_sizes = moba_split.sizes() if isinstance(moba_split, QSplitter) else []
    native_tabs_before_duplicate = window.tabs.count()
    window.duplicate_current_tab()
    app.processEvents()
    native_duplicate_index = window.tabs.currentIndex()
    native_duplicate_panel = window.tabs.currentWidget()
    native_duplicate_state = window.moba_connected_state_in_widget(
        native_duplicate_panel
    )
    native_duplicate_split = getattr(native_duplicate_panel, "terminal_splitter", None)
    native_duplicate_panes = window.terminal_panes_in(native_duplicate_panel)
    native_duplicate_sizes = (
        native_duplicate_split.sizes()
        if isinstance(native_duplicate_split, QSplitter)
        else []
    )
    native_duplicate_proportions_match = (
        len(native_duplicate_sizes) == len(native_source_sizes)
        and sum(native_duplicate_sizes) > 0
        and sum(native_source_sizes) > 0
        and all(
            abs(
                duplicate_size / sum(native_duplicate_sizes)
                - source_size / sum(native_source_sizes)
            )
            <= 0.02
            for duplicate_size, source_size in zip(
                native_duplicate_sizes,
                native_source_sizes,
                strict=True,
            )
        )
    )
    native_duplicate_preserved = (
        moba_split_state is not None
        and native_duplicate_state is not None
        and window.current_design_id() == "native"
        and window.tabs.count() == native_tabs_before_duplicate + 1
        and window.tab_role(native_duplicate_index) == "terminal"
        and native_duplicate_state.profile_name == moba_split_state.profile_name
        and native_duplicate_state.target == moba_split_state.target
        and native_duplicate_state.connection_label
        == moba_split_state.connection_label
        and native_duplicate_state.remote_path == moba_split_state.remote_path
        and native_duplicate_state.follow_terminal_folder
        == moba_split_state.follow_terminal_folder
        and native_duplicate_state.file_entries == moba_split_state.file_entries
        and native_duplicate_state.sftp_list_plan == moba_split_state.sftp_list_plan
        and native_duplicate_state.follow_folder_plan
        == moba_split_state.follow_folder_plan
        and isinstance(native_duplicate_split, QSplitter)
        and isinstance(moba_split, QSplitter)
        and native_duplicate_split.orientation() == moba_split.orientation()
        and len(native_duplicate_panes) == len(moba_panes)
        and native_duplicate_proportions_match
        and all(pane.profile == dispatch_profile for pane in native_duplicate_panes)
        and all(
            pane.plan.printable() == moba_plan.printable()
            for pane in native_duplicate_panes
        )
        and all(
            bool(pane.property("mobaPlainTerminalMode"))
            and bool(pane.property("mobaConnectedIdentityRouteKey"))
            and bool(pane.property("mobaSftpTerminalFolderRouteKey"))
            and pane.property("mobaConnectedRouteTarget")
            == native_duplicate_state.target
            and pane.property("mobaSftpTerminalFolderRoutePath")
            == native_duplicate_state.remote_path
            for pane in native_duplicate_panes
        )
        and window.moba_connected_dock is None
        and window.moba_left_stack.currentWidget() is window.profile_list
    )
    record(
        "moba-native-duplicate-preserves-identity-path-sftp-and-splits",
        native_duplicate_preserved,
        {
            "active_preset": window.current_design_id(),
            "tab_role": window.tab_role(native_duplicate_index),
            "tab_count": window.tabs.count(),
            "source_state": (
                moba_split_state.to_dict() if moba_split_state is not None else None
            ),
            "duplicate_state": (
                native_duplicate_state.to_dict()
                if native_duplicate_state is not None
                else None
            ),
            "source_sizes": native_source_sizes,
            "duplicate_sizes": native_duplicate_sizes,
            "size_proportions_match": native_duplicate_proportions_match,
            "pane_count": len(native_duplicate_panes),
            "moba_dock_present": window.moba_connected_dock is not None,
            "left_stack_is_profile_tree": (
                window.moba_left_stack.currentWidget() is window.profile_list
            ),
        },
    )
    for pane in native_duplicate_panes:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(native_duplicate_index)
    app.processEvents()
    window.tabs.setCurrentIndex(window.tabs.indexOf(original_moba_panel))
    window.set_design_preset("mobaxterm")
    app.processEvents()
    record(
        "moba-native-duplicate-round-trip-restores-source-dock",
        native_duplicate_preserved
        and window.current_design_id() == "mobaxterm"
        and window.tabs.currentWidget() is original_moba_panel
        and window.moba_connected_dock is not None
        and window.moba_left_stack.currentWidget() is window.moba_connected_dock
        and moba_split_state is not None
        and window.moba_connected_dock.state.target == moba_split_state.target
        and window.moba_connected_dock.state.remote_path
        == moba_split_state.remote_path,
        {
            "active_preset": window.current_design_id(),
            "source_is_current": window.tabs.currentWidget() is original_moba_panel,
            "dock_state": (
                window.moba_connected_dock.state.to_dict()
                if window.moba_connected_dock is not None
                else None
            ),
        },
    )

    expected_recovery_path = window.moba_connected_remote_path_for_profile(dispatch_profile)
    window.recent_terminal_plans = [(moba_plan, dispatch_profile)]
    tabs_before_recovery = window.tabs.count()
    window.recover_previous_sessions()
    app.processEvents()
    recovered_tab_index = window.tabs.currentIndex()
    recovered_moba_panel = window.tabs.currentWidget()
    recovered_moba_state = window.moba_connected_state_in_widget(recovered_moba_panel)
    recovered_moba_panes = window.terminal_panes_in(recovered_moba_panel)
    record(
        "moba-recovery-preserves-identity-path-and-dock",
        recovered_moba_state is not None
        and window.tabs.count() == tabs_before_recovery + 1
        and window.tab_role(recovered_tab_index) == "terminal"
        and recovered_moba_state.profile_name == dispatch_profile.name
        and recovered_moba_state.target == dispatch_profile.display_target
        and recovered_moba_state.remote_path == expected_recovery_path
        and len(recovered_moba_panes) == 1
        and recovered_moba_panes[0].profile == dispatch_profile
        and recovered_moba_panes[0].plan.printable() == moba_plan.printable()
        and window.moba_connected_dock is not None
        and window.moba_left_stack.currentWidget() is window.moba_connected_dock
        and window.moba_connected_dock.state.target == recovered_moba_state.target
        and window.moba_connected_dock.state.remote_path == recovered_moba_state.remote_path,
        {
            "tab_role": window.tab_role(recovered_tab_index),
            "tab_count": window.tabs.count(),
            "expected_path": expected_recovery_path,
            "state": recovered_moba_state.to_dict() if recovered_moba_state is not None else None,
            "pane_profiles": [
                pane.profile.name if pane.profile is not None else None
                for pane in recovered_moba_panes
            ],
            "pane_commands": [pane.plan.printable() for pane in recovered_moba_panes],
        },
    )
    for pane in recovered_moba_panes:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close_tab(recovered_tab_index)
    app.processEvents()
    window.tabs.setCurrentIndex(window.tabs.indexOf(original_moba_panel))
    app.processEvents()
    window.open_moba_sftp_same_parameters()
    app.processEvents()
    record(
        "moba-split-sftp-same-parameters-preserves-target",
        dispatch_profile.display_target in window.statusBar().currentMessage()
        and " at /" in window.statusBar().currentMessage()
        and window.moba_connected_dock is not None,
        window.statusBar().currentMessage(),
    )

    window.open_local_terminal_tab()
    app.processEvents()
    original_terminal = window.tabs.currentWidget()
    original_tab_count = window.tabs.count()
    window.add_split("horizontal")
    app.processEvents()
    split = window.tabs.currentWidget()
    panes = window.terminal_panes_in(split) if split is not None else []
    record(
        "split-creates-active-pane-layout",
        isinstance(split, QSplitter)
        and split.orientation() == Qt.Orientation.Horizontal
        and len(panes) == 2
        and all(size > 0 for size in split.sizes())
        and all(pane.isVisible() for pane in panes),
        {
            "widget": type(split).__name__ if split is not None else None,
            "panes": len(panes),
            "sizes": split.sizes() if isinstance(split, QSplitter) else None,
            "visible": [pane.isVisible() for pane in panes],
        },
    )
    record(
        "split-preserves-active-terminal",
        isinstance(split, QSplitter)
        and split.widget(0) is original_terminal
        and window.tabs.count() == original_tab_count,
        {
            "same_terminal": isinstance(split, QSplitter) and split.widget(0) is original_terminal,
            "tab_count": window.tabs.count(),
            "original_tab_count": original_tab_count,
            "tab_role": window.tab_role(window.tabs.currentIndex()),
        },
    )
    window.set_design_preset("native")
    window.resize(1180, 720)
    app.processEvents()
    app.processEvents()
    record(
        "active-terminal-window-exact-1180x720",
        (window.width(), window.height()) == (1180, 720),
        {
            "actual": [window.width(), window.height()],
            "minimum": [window.minimumSizeHint().width(), window.minimumSizeHint().height()],
        },
    )
    terminal_toolbar_state = {
        key: {
            "text": button.text(),
            "visible": button.isVisible(),
            "action_visible": window.toolbar_widget_action(button).isVisible(),
            "enabled": button.isEnabled(),
        }
        for key, button in window.product_toolbar_button_by_key.items()
    }
    record(
        "active-terminal-product-toolbar-controls-present",
        all(
            state["text"] and state["visible"] and state["action_visible"]
            for state in terminal_toolbar_state.values()
        ),
        terminal_toolbar_state,
    )
    capture("native-terminal-split-1180x720.png", window)
    if len(panes) >= 2:
        first_pane, second_pane = panes[:2]
        first_pane.set_terminal_transcript("pane-one-only\n")
        second_pane.set_terminal_transcript("pane-two-only-needle\n")
        window.raise_()
        window.activateWindow()
        QTest.mouseClick(
            second_pane.output.viewport(),
            Qt.MouseButton.LeftButton,
            pos=second_pane.output.viewport().rect().center(),
        )
        app.processEvents()
        second_was_focused = second_pane.output.hasFocus()
        window.search_input.setText("pane-two-only-needle")
        window.focus_find_control()
        app.processEvents()
        record(
            "find-control-preserves-second-split-pane-target",
            second_was_focused
            and second_pane.output.textCursor().selectedText() == "pane-two-only-needle"
            and second_pane.output.hasFocus()
            and first_pane.output.textCursor().selectedText() == ""
            and window.active_terminal_pane() is second_pane
            and window.statusBar().currentMessage()
            == "Found in active terminal: pane-two-only-needle",
            {
                "first_selection": first_pane.output.textCursor().selectedText(),
                "second_selection": second_pane.output.textCursor().selectedText(),
                "second_was_focused": second_was_focused,
                "second_has_focus": second_pane.output.hasFocus(),
                "active_is_second": window.active_terminal_pane() is second_pane,
                "status": window.statusBar().currentMessage(),
            },
        )
    if panes:
        pane = panes[0]
        compact = all(
            button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
            for button in pane.terminal_action_buttons
        )
        record(
            "terminal-actions-compact-at-real-split-width",
            pane.width() < 620 and compact,
            {"pane_width": pane.width(), "compact": compact},
        )
        pane.set_terminal_transcript("alpha\nneedle-in-terminal\nomega\n")
        pane.output.setFocus()
        app.processEvents()
        window.search_input.setText("needle-in-terminal")
        window.search_input.returnPressed.emit()
        record(
            "search-enter-finds-active-terminal",
            pane.output.textCursor().selectedText() == "needle-in-terminal",
            pane.output.textCursor().selectedText(),
        )
        cursor = pane.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        cursor.movePosition(cursor.MoveOperation.NextWord, cursor.MoveMode.KeepAnchor)
        pane.output.setTextCursor(cursor)
        expected_clipboard = cursor.selectedText()
        pane.copy_command()
        record(
            "terminal-copy-prefers-selection",
            QApplication.clipboard().text() == expected_clipboard,
            QApplication.clipboard().text(),
        )

    # Run minimum-width geometry evidence after stateful interaction coverage,
    # because preparing product reference tabs intentionally changes selection
    # and should not influence the earlier callback assertions.
    for preset_id in preset_ids:
        window.set_design_preset(preset_id)
        window.resize(1024, 768)
        for _ in range(4):
            app.processEvents()
        record_minimum_size_preset_geometry(preset_id)

    image_records = []
    for path in sorted(set(captured_images)):
        image_records.append(
            {"path": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
        )
    screen = app.primaryScreen()
    manifest = {
        "schema": "row.gui-interaction-evidence.v1",
        "capture_mode": capture_mode,
        "os": platform.platform(),
        "qt_platform_plugin": QApplication.platformName(),
        "qt_platform_env": os.environ.get("QT_QPA_PLATFORM", "native"),
        "qt_version": QT_VERSION_STR,
        "pyqt_version": PYQT_VERSION_STR,
        "font_render_evidence": font_render_payload,
        "screen": {
            "size": [screen.size().width(), screen.size().height()] if screen is not None else None,
            "logical_dpi": screen.logicalDotsPerInch() if screen is not None else None,
            "device_pixel_ratio": screen.devicePixelRatio() if screen is not None else None,
        },
        "supported_window_sizes": [list(size) for size in SUPPORTED_WINDOW_SIZES],
        "checks": checks,
        "images": image_records,
        "errors": errors,
    }
    (out_dir / "interaction-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for pane in window.all_terminal_panes():
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1000)
    window.close()
    app.processEvents()
    return checks, errors


def main() -> int:
    args = parse_args()
    checks, errors = run(Path(args.out_dir), require_pyqt6=args.require_pyqt6)
    if errors:
        for error in errors:
            print(f"gui interaction: {error}")
        return 1
    print(f"gui interaction: {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
