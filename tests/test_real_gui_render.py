from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_real_gui_render_checker_passes_or_verifies_fail_closed_path(tmp_path: Path) -> None:
    checker = _load_checker()

    if checker.module_available("PyQt6"):
        assert checker.DEFAULT_RENDER_TIMEOUT_SECONDS == 240
        return

    errors, messages = checker.check_real_gui_render(["native"], out_dir=tmp_path)

    assert errors == []
    assert any("captured" in message or "fail-closed" in message for message in messages)


def test_real_gui_render_main_wires_timeout_without_opening_gui(monkeypatch) -> None:
    checker = _load_checker()
    calls: dict[str, object] = {}

    def fake_check_real_gui_render(
        preset_ids: list[str],
        *,
        out_dir: Path | None = None,
        require_pyqt6: bool = False,
    ) -> tuple[list[str], list[str]]:
        calls["preset_ids"] = preset_ids
        calls["out_dir"] = out_dir
        calls["require_pyqt6"] = require_pyqt6
        return [], ["fake live render"]

    monkeypatch.setattr(checker, "check_real_gui_render", fake_check_real_gui_render)

    assert checker.main(["--timeout-seconds", "0", "--require-pyqt6", "--preset", "native"]) == 0
    assert calls == {
        "preset_ids": ["native"],
        "out_dir": None,
        "require_pyqt6": True,
    }


def test_real_gui_render_require_pyqt6_fails_when_missing() -> None:
    checker = _load_checker()

    if checker.module_available("PyQt6"):
        return

    errors, messages = checker.check_real_gui_render(["native"], require_pyqt6=True)

    assert errors == ["PyQt6 is required for live GUI render capture"]
    assert any("fail-closed" in message for message in messages)


def test_real_gui_render_metrics_reject_blank_capture() -> None:
    checker = _load_checker()
    samples = [(255, 255, 255)] * 100

    metrics = checker.metrics_from_samples(1180, 720, samples)

    assert metrics.distinct_colors == 1
    assert metrics.luminance_range == 0
    assert checker.validate_metrics("native", metrics)


def test_real_gui_render_metrics_accept_detailed_capture() -> None:
    checker = _load_checker()
    samples = []
    for index in range(120):
        samples.append(((index * 13) % 255, (index * 29) % 255, (index * 47) % 255))

    metrics = checker.metrics_from_samples(1180, 720, samples)

    assert metrics.distinct_colors >= checker.MIN_DISTINCT_COLORS
    assert metrics.luminance_range >= checker.MIN_LUMINANCE_RANGE
    assert metrics.non_background_ratio >= checker.MIN_NON_BACKGROUND_RATIO
    assert checker.validate_metrics("native", metrics) == []


def test_real_gui_render_metrics_reject_capture_wider_than_requested_size() -> None:
    checker = _load_checker()
    samples = [((index * 13) % 255, (index * 29) % 255, (index * 47) % 255) for index in range(120)]

    metrics = checker.metrics_from_samples(
        checker.REQUESTED_SIZE[0] + 1, checker.REQUESTED_SIZE[1], samples
    )
    errors = checker.validate_metrics("native", metrics)

    assert any("must not exceed requested size" in error for error in errors)


def test_real_gui_render_font_preflight_rejects_empty_font_inventory() -> None:
    checker = _load_checker()
    evidence = checker.FontRenderEvidence(
        platform_name="offscreen",
        family_count=0,
        selected_family="",
        raw_font_valid=False,
        glyph_indexes=(),
        rendered_ink_pixels=0,
    )

    errors = checker.validate_qt_font_render_evidence(evidence)

    assert any("exposes no usable font families" in error for error in errors)
    assert any("readable glyph rendering is required" in error for error in errors)


def test_real_gui_render_font_preflight_rejects_tofu_glyph_substitution() -> None:
    checker = _load_checker()
    evidence = checker.FontRenderEvidence(
        platform_name="offscreen",
        family_count=1,
        selected_family="Fallback",
        raw_font_valid=True,
        glyph_indexes=(1,) * len(checker.FONT_PROBE_TEXT),
        rendered_ink_pixels=900,
    )

    errors = checker.validate_qt_font_render_evidence(evidence)

    assert any("tofu substitution is not accepted" in error for error in errors)


def test_real_gui_render_font_selection_rejects_tofu_glyph_substitution() -> None:
    checker = _load_checker()

    assert checker.usable_font_probe_glyphs((1,) * len(checker.FONT_PROBE_TEXT)) is False
    assert (
        checker.usable_font_probe_glyphs(
            tuple(range(1, len(checker.FONT_PROBE_TEXT) + 1))
        )
        is True
    )


def test_real_gui_render_font_preflight_accepts_distinct_rendered_glyphs() -> None:
    checker = _load_checker()
    evidence = checker.FontRenderEvidence(
        platform_name="windows",
        family_count=300,
        selected_family="Segoe UI",
        raw_font_valid=True,
        glyph_indexes=tuple(range(1, len(checker.FONT_PROBE_TEXT) + 1)),
        rendered_ink_pixels=900,
    )

    assert checker.validate_qt_font_render_evidence(evidence) == []


def test_real_gui_render_uses_native_windows_backend_by_default() -> None:
    checker = _load_checker()

    assert checker.default_qt_platform("win32") == "windows"
    assert checker.default_qt_platform("darwin") == "cocoa"
    assert checker.default_qt_platform("linux") == "offscreen"
    assert checker.default_qt_scale_factor("win32") == "1"
    assert checker.default_qt_scale_factor("linux") is None
    assert checker.effective_qt_scale_factor("1.25", "win32") == "1.25"
    assert checker.effective_qt_scale_factor("1.5", "linux") == "1.5"
    assert checker.effective_qt_scale_factor(None, "win32") == "1"
    assert checker.effective_qt_scale_factor(None, "linux") is None


def test_real_gui_render_capture_preserves_explicit_scale_factor(monkeypatch) -> None:
    checker = _load_checker()
    observed: dict[str, str | None] = {}

    def fake_capture_live_gui(_preset_ids, *, out_dir=None):
        observed["scale_factor"] = checker.os.environ.get("QT_SCALE_FACTOR")
        observed["out_dir"] = str(out_dir) if out_dir is not None else None
        return [], [], []

    monkeypatch.setenv("QT_SCALE_FACTOR", "1.25")
    monkeypatch.setattr(checker, "_capture_live_gui", fake_capture_live_gui)

    errors, messages = checker.capture_live_gui(["mobaxterm"])

    assert errors == []
    assert messages == []
    assert observed["scale_factor"] == "1.25"
    assert checker.os.environ["QT_SCALE_FACTOR"] == "1.25"


def test_real_gui_render_moba_live_contract_requires_usable_crisp_surfaces() -> None:
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    contract_source = source[
        source.index("def check_preset_live_contract") :
        source.index("def live_tab_labels")
    ]

    assert '"mobaTerminalInputVisible": not native_pty' in contract_source
    assert "native PTY terminal input must be hidden" in contract_source
    assert "explicit pipe fallback input must be visible" in contract_source
    assert "mobaTerminalLineInputFallback" in contract_source
    assert "mobaTerminalContextMenu" in contract_source
    assert "telemetry context-menu route drifted" in contract_source
    assert "mobaSyntheticConnectedTranscriptSuppressed" in contract_source
    assert "preview-only connected transcript data" in contract_source
    assert "preview-only remote rows" in contract_source
    assert "must stay disabled without a remote item" in source
    assert "Waiting for authentication and server output." in contract_source
    assert "terminal startup preamble must be part of scrollback" in contract_source
    assert "terminal scrollback is missing its startup preamble" in contract_source
    assert "must not expose a fixed SSH banner" in contract_source
    assert "must not expose a permanent right utility rail" in contract_source
    assert "connected layout must not instantiate" in contract_source
    assert "mobaBackgroundSshAuthAvailable" in contract_source
    assert "mobaBackgroundSshAuthDetail" in contract_source
    assert "auth-required state" in contract_source
    assert "separate non-interactive SSH process" in contract_source
    assert "key or agent authentication are required" in contract_source
    assert '"Monitoring"' in contract_source
    assert '"Telemetry"' not in contract_source
    assert "transcript_keys =" not in contract_source
    assert "transcript_tones =" not in contract_source
    assert "for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT" not in contract_source
    assert "Last login: Sat Jun  6 05:27:50 2026" in contract_source
    assert "banner_frame.frameWidth() != 1" not in contract_source
    assert "mobaRightUtilityRailStaticWidth" not in contract_source
    assert "right utility action route rail" not in contract_source
    assert "QFont.HintingPreference.PreferFullHinting" in contract_source
    assert '"mobaRailTextRenderMode"' in contract_source
    assert '"device-pixel-pixmap"' in contract_source
    assert '"mobaRailTextDevicePixelRatio"' in contract_source


def test_real_gui_render_normalizes_high_dpi_capture_dimensions() -> None:
    checker = _load_checker()

    assert checker.logical_capture_size(1775, 1025, 1.25) == (1420, 820)
    assert checker.logical_capture_size(1420, 820, 1.0) == (1420, 820)
    assert checker.logical_capture_size(1420, 820, 0.0) == (1420, 820)


def test_real_gui_render_capture_binds_font_evidence_and_platform_mode() -> None:
    checker = _load_checker()
    evidence = checker.FontRenderEvidence(
        platform_name="windows",
        family_count=300,
        selected_family="Segoe UI",
        raw_font_valid=True,
        glyph_indexes=tuple(range(1, len(checker.FONT_PROBE_TEXT) + 1)),
        rendered_ink_pixels=900,
    )
    capture = checker.CaptureResult(
        preset_id="native",
        preset_label="Native",
        metrics=checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25),
        font_render_evidence=evidence,
    )

    assert checker.capture_mode_for_captures([capture]) == "live-pyqt6-windows"
    assert capture.to_dict()["font_render_evidence"]["selected_family"] == "Segoe UI"


def test_real_gui_render_validates_real_remmina_screenshot_artifact(tmp_path: Path) -> None:
    checker = _load_checker()
    artifact = tmp_path / "win-admin-rdp-screenshot.png"
    payload = b"\x89PNG\r\n\x1a\nreal-capture"
    artifact.write_bytes(payload)

    assert (
        checker.validate_remmina_screenshot_capture_artifact(
            "viewer-controls",
            str(artifact.resolve()),
            len(payload),
            artifact.name,
        )
        == []
    )


def test_real_gui_render_rejects_unproved_remmina_screenshot_artifact(tmp_path: Path) -> None:
    checker = _load_checker()
    artifact = tmp_path / "win-admin-rdp-screenshot.png"
    artifact.write_bytes(b"not-a-png")

    relative_errors = checker.validate_remmina_screenshot_capture_artifact(
        "viewer-controls",
        artifact.name,
        artifact.stat().st_size,
        artifact.name,
    )
    png_errors = checker.validate_remmina_screenshot_capture_artifact(
        "viewer-controls",
        str(artifact.resolve()),
        artifact.stat().st_size,
        artifact.name,
    )

    assert any("must be absolute" in error for error in relative_errors)
    assert any("must contain a PNG artifact" in error for error in png_errors)


def test_real_gui_render_manifest_contract_names_required_widgets() -> None:
    checker = _load_checker()
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert checker.MANIFEST_NAME == "real-gui-render-manifest.json"
    assert checker.DEFAULT_RENDER_TIMEOUT_SECONDS == 240
    assert checker.REQUIRED_WIDGETS["designSelect"] == "view preset selector"
    assert checker.REQUIRED_WIDGETS["layoutToolbar"] == "layout toolbar"
    assert checker.REQUIRED_WIDGETS["activityLog"] == "activity log"
    assert checker.COMMON_REQUIRED_WIDGETS["productWorkflowEvidence"] == "product workflow evidence strip"
    assert checker.COMMON_REQUIRED_WIDGETS["productWorkspaceSurface"] == "product workspace evidence surface"
    assert checker.SECURECRT_REQUIRED_WIDGETS["secureCrtCommandInput"] == "SecureCRT live command-window input"
    assert checker.SECURECRT_REQUIRED_WIDGETS["secureCrtCommandSend"] == "SecureCRT live command-window Send control"
    assert checker.MOBA_CONNECTED_REQUIRED_WIDGETS["mobaConnectedLeftDock"] == "Moba connected SFTP/monitoring dock"
    assert checker.MOBA_CONNECTED_REQUIRED_WIDGETS["mobaSftpBrowser"] == "Moba SFTP browser"
    assert checker.PRODUCT_STYLE_PRESETS == {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
    assert checker.EXPECTED_MOBA_SESSION_TREE_CHROME.profile_row_height == 34
    assert checker.EXPECTED_PRODUCT_TREE_ICON_KEYS["mobaxterm"]["sftp-ops"] == "sftp"
    assert checker.EXPECTED_MOBA_RAIL_ROLES == {"collapse", "sessions", "favorites", "tools", "macros", "sftp"}
    assert checker.EXPECTED_MOBA_CONNECTED_DOCK_FRAME.rail_width == 28
    assert checker.EXPECTED_MOBA_RAIL_CHROME.rail_width == 28
    assert checker.EXPECTED_MOBA_RAIL_ITEM_GEOMETRY_BY_ROLE["sftp"].static_label_y == 354
    assert "visible_matches" in source
    assert "def run_render_child" in source
    assert "subprocess.run" in source
    assert "def render_child_command" in source
    assert "--render-child" in source
    assert "timed out after" in source
    assert "window.findChildren(QWidget, object_name)" in source
    assert checker.EXPECTED_MOBA_TOP_MENU_KEYS == [
        "terminal",
        "sessions",
        "view",
        "x-server",
        "tools",
        "games",
        "settings",
        "macros",
        "help",
    ]
    assert checker.EXPECTED_MOBA_TOP_MENU_LABELS == [
        "Terminal",
        "Sessions",
        "View",
        "X server",
        "Tools",
        "Games",
        "Settings",
        "Macros",
        "Help",
    ]
    assert checker.EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE.key == "moba-ribbon-edge-action-route"
    assert checker.EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE.xserver_handler == "show_moba_x_server_status"
    assert checker.EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE.exit_handler == "close"
    assert checker.EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.key == "moba-right-utility-action-route"
    assert checker.EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_handlers == (
        "show_moba_clipboard_hints",
        "show_moba_terminal_settings",
        "show_moba_tools_status",
    )
    assert checker.EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.key == "moba-session-edge-action-route"
    assert checker.EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_handlers == (
        "show_moba_session_attachment",
        "show_moba_session_settings",
    )
    assert checker.EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.key == "moba-sftp-toolbar-action-route"
    assert checker.EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys == tuple(
        action.key for action in checker.EXPECTED_MOBA_SFTP_ACTIONS
    )
    assert set(checker.EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_handlers) == {
        "show_moba_sftp_toolbar_action"
    }
    assert checker.EXPECTED_SECURECRT_TOP_MENU_KEYS == [
        "file",
        "edit",
        "view",
        "options",
        "transfer",
        "script",
        "tools",
        "window",
        "help",
    ]
    assert checker.EXPECTED_SECURECRT_TOP_MENU_LABELS == [
        "File",
        "Edit",
        "View",
        "Options",
        "Transfer",
        "Script",
        "Tools",
        "Window",
        "Help",
    ]
    assert checker.EXPECTED_SECURECRT_TOP_TOOLBAR_KEYS[:6] == [
        "refresh",
        "new",
        "import",
        "edit",
        "remove",
        "connect",
    ]
    assert checker.EXPECTED_SECURECRT_TOP_TOOLBAR_ICON_KEYS["files"] == "sftp"
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_CHROME.placeholder == "Quick connect..."
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_CHROME.dropdown_marker == "v"
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_CHROME.static_height == 24
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.preview_query == "edge-prod.example.invalid"
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.expected_kinds == ("profile", "direct")
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.max_visible_rows == 4
    assert checker.EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.row_height == 22
    assert checker.EXPECTED_MOBA_HOME_WELCOME_CHROME.title == "Remote Ops Workspace"
    assert checker.EXPECTED_MOBA_HOME_WELCOME_CHROME.search_width == 405
    assert checker.EXPECTED_MOBA_HOME_WELCOME_CHROME.recent_title == "Recent sessions"
    assert checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS == []
    assert checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_TONES == []
    assert "terminal" in checker.EXPECTED_MOBA_SFTP_ACTION_KEYS
    assert checker.EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY_BY_KEY["ascii-mode"].icon_x == 196
    assert checker.EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_marker == "v"
    assert checker.EXPECTED_MOBA_SFTP_COLUMN_KEYS == ["name", "size", "modified"]
    assert checker.EXPECTED_MOBA_SFTP_COLUMN_LABELS == ["Name", "Size (KB)", "Last modified"]
    assert checker.EXPECTED_MOBA_MONITORING_METRIC_KEYS == {
        "cpu",
        "memory",
        "disk",
        "network",
        "load",
        "processes",
    }
    assert checker.EXPECTED_MOBA_MONITORING_CONTROL_KEYS == {
        "remote-monitoring",
        "follow-terminal-folder",
    }
    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.compact is True
    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.visible_metric_keys == ()
    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface == "bottom-telemetry-bar"
    assert checker.EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key == "remote-monitoring-to-bottom-telemetry"
    assert checker.EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_bar_object == "mobaTelemetryBar"
    assert (
        checker.EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.key
        == "moba-follow-terminal-folder-control-route"
    )
    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE.handler == "handle_moba_remote_monitoring_toggled"
    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE.signal == "toggled"
    assert checker.EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.source_control_key == "follow-terminal-folder"
    assert checker.EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.target_path_object == "mobaSftpPath"
    assert checker.EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.handler == (
        "handle_moba_follow_terminal_folder_toggled"
    )
    assert checker.EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.signal == "toggled"
    assert checker.EXPECTED_MOBA_CONNECTED_SESSION_ROUTE.key == "moba-active-connected-session-route"
    assert checker.EXPECTED_MOBA_CONNECTED_SESSION_ROUTE.active_tab_key == "active-session"
    assert checker.EXPECTED_MOBA_CONNECTED_SESSION_ROUTE.telemetry_identity_cell_key == "target"
    assert checker.EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE.key == "moba-connected-session-identity-route"
    assert checker.EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE.telemetry_target == "edge-prod.example.invalid:22"
    assert [control.icon_key for control in checker.EXPECTED_MOBA_MONITORING_CONTROLS] == [
        "monitor",
        "follow-folder",
    ]
    assert checker.EXPECTED_MOBA_STATUS_KEYS == {"sftp-ready", "cpu-monitor", "ssh-browser"}
    assert checker.EXPECTED_MOBA_STATUS_CHROME.notice == "REMOTE OPS WORKSPACE"
    assert checker.EXPECTED_MOBA_BOTTOM_EDGE_KEYS == {"tab-left", "tab-right", "close-active"}
    assert checker.EXPECTED_MOBA_BOTTOM_EDGE_ICON_KEYS["close-active"] == "close"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.key == "send-to-all-sessions"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.command == "$ row doctor --json"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.signal == "clicked"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.secondary_signal == "returnPressed"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.handler == "handle_securecrt_command_window_send"
    assert checker.EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.live_submitted_property == (
        "secureCrtCommandRouteLiveSubmitted"
    )
    assert checker.EXPECTED_SECURECRT_TREE_ICON_KEYS["Session Database"] == "database"
    assert checker.EXPECTED_SECURECRT_TREE_ICON_KEYS["edge-prod (SSH2)"] == "ssh2"
    assert checker.EXPECTED_SECURECRT_TREE_ICON_KEYS["files-prod (SFTP)"] == "sftp"
    assert checker.EXPECTED_SECURECRT_TREE_ICON_KEYS["jump-host (SSH2)"] == "pin"
    assert checker.EXPECTED_SECURECRT_TREE_ROW_KINDS["Folder: Sessions"] == "group"
    assert checker.EXPECTED_SECURECRT_TREE_ICON_SIZES["Session Database"] == 16
    assert checker.EXPECTED_PRODUCT_TREE_ICON_KEYS["termius"]["prod-cluster  ssh host"] == "host"
    assert checker.EXPECTED_PRODUCT_TREE_ICON_KEYS["termius"]["jump-host  ssh host"] == "pin"
    assert checker.EXPECTED_PRODUCT_TREE_ICON_KEYS["remmina"]["VNC - linux-console"] == "vnc"
    assert checker.EXPECTED_PRODUCT_TREE_ICON_KEYS["mremoteng"]["win-admin [RDP]"] == "rdp"
    assert checker.EXPECTED_SECURECRT_SESSION_STATUS_KEYS == [
        "session",
        "target",
        "protocol",
        "cipher",
        "sftp",
        "log",
        "state",
    ]
    assert checker.EXPECTED_SECURECRT_SESSION_STATUS_STRIP.fields[1].value == "edge-prod.example.invalid:22"
    assert checker.EXPECTED_REMMINA_VIEWER_CONTROL_KEYS == [
        "fit",
        "scale-100",
        "clipboard",
        "fullscreen",
        "screenshot",
    ]
    assert checker.EXPECTED_REMMINA_PROFILE_COLUMN_KEYS == ["name", "protocol", "server"]
    assert checker.EXPECTED_REMMINA_PROFILE_ROW_KEYS == ["win-admin", "linux-console", "sftp-ops"]
    assert checker.EXPECTED_REMMINA_PROFILE_LIST_CHROME.filter_placeholder == "Filter by name or protocol"
    assert checker.EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.key == "remmina-selected-profile-viewer-route"
    assert checker.EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.active_tab_label == "RDP - win-admin"
    assert checker.EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.viewer_control_key == "scale-100"
    assert checker.EXPECTED_REMMINA_PROFILE_FILTER_ROUTE.key == "remmina-profile-filter-route"
    assert checker.EXPECTED_REMMINA_PROFILE_FILTER_ROUTE.expected_query == "rdp"
    assert checker.EXPECTED_REMMINA_PROFILE_FILTER_ROUTE.selected_profile_key == "win-admin"
    assert checker.EXPECTED_REMMINA_CLIPBOARD_ROUTE.key == "remmina-clipboard-sync-route"
    assert checker.EXPECTED_REMMINA_CLIPBOARD_ROUTE.viewer_control_key == "clipboard"
    assert checker.EXPECTED_REMMINA_CLIPBOARD_ROUTE.status_segment == "Clipboard on"
    assert checker.EXPECTED_REMMINA_SCREENSHOT_ROUTE.key == "remmina-screenshot-capture-route"
    assert checker.EXPECTED_REMMINA_SCREENSHOT_ROUTE.handler == "handle_remmina_screenshot_capture"
    assert checker.EXPECTED_REMMINA_SCREENSHOT_ROUTE.live_triggered_property == "remminaScreenshotRouteLiveTriggered"
    assert checker.EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE.key == "remmina-sftp-transfer-route"
    assert checker.EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE.handler == "handle_remmina_sftp_transfer_action"
    assert checker.EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE.live_triggered_property == (
        "remminaSftpTransferRouteLiveTriggered"
    )
    assert checker.EXPECTED_TERMIUS_HEADER_CHIP_KEYS == [
        "vault-unlocked",
        "sync-current",
        "port-forward-ready",
    ]
    assert checker.EXPECTED_TERMIUS_HOSTS_ACTION_KEYS == ["new-host", "keychain", "sync-hosts"]
    assert checker.EXPECTED_TERMIUS_HOSTS_ICON_KEYS == {
        "new-host": "plus",
        "keychain": "key",
        "sync-hosts": "sync",
    }
    assert checker.EXPECTED_TERMIUS_HOSTS_CHROME.filter_placeholder == "Search hosts"
    assert checker.EXPECTED_TERMIUS_HOST_IDENTITY_KEYS == [
        "host",
        "identity",
        "chain",
        "files",
        "forward",
        "snippet",
        "sync",
    ]
    assert checker.EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields[1].value == "prod-ed25519"
    assert checker.EXPECTED_MREMOTENG_TOP_MENU_KEYS == [
        "file",
        "view",
        "connections",
        "tools",
        "window",
        "help",
    ]
    assert checker.EXPECTED_MREMOTENG_TOP_TOOLBAR_KEYS[:7] == [
        "refresh",
        "new",
        "import",
        "edit",
        "remove",
        "connect",
        "files",
    ]
    assert checker.EXPECTED_MREMOTENG_TOP_TOOLBAR_ICON_KEYS["files"] == "external-tool"
    assert checker.EXPECTED_MREMOTENG_DOCUMENT_CONTROL_KEYS == [
        "save",
        "reconnect",
        "external-tool",
        "dock-view",
    ]
    assert checker.EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.title == "Connections.xml"
    assert checker.EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS == ["property", "inherited", "effective", "source"]
    assert checker.EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS == [
        "protocol",
        "hostname",
        "credential",
        "external",
        "inheritance",
    ]
    assert checker.EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.scope_label == "edge-prod [SSH]"
    assert checker.EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.key == (
        "mremoteng-selected-connection-document-route"
    )
    assert checker.EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.document_control_key == "reconnect"
    assert checker.EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_row_key == "protocol"
    assert checker.EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.handler == "handle_mremoteng_document_reconnect"
    assert checker.EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.live_triggered_property == (
        "mRemoteNgConnectionRouteLiveTriggered"
    )
    assert checker.EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE.key == "mremoteng-document-filter-route"
    assert checker.EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE.expected_query == "edge"
    assert checker.EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE.selected_tree_label == "edge-prod [SSH]"
    assert checker.EXPECTED_MREMOTENG_INHERITANCE_ROUTE.key == "mremoteng-inheritance-route"
    assert checker.EXPECTED_MREMOTENG_INHERITANCE_ROUTE.workflow_card_key == "inheritance-grid"
    assert checker.EXPECTED_MREMOTENG_INHERITANCE_ROUTE.property_row_key == "credential"
    assert checker.EXPECTED_MREMOTENG_INHERITANCE_ROUTE.inherited_value == "operator key reference"


def test_real_gui_render_defaults_to_every_preset() -> None:
    checker = _load_checker()

    assert checker.select_presets(None) == [preset.id for preset in checker.GUI_DESIGN_PRESETS]


def test_real_gui_render_monitoring_checked_expectation_is_auth_aware() -> None:
    checker = _load_checker()

    assert checker.EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE.expected_checked is True
    assert checker.expected_moba_monitoring_checked(True) is True
    assert checker.expected_moba_monitoring_checked(False) is False


def test_real_gui_render_uses_preset_specific_widget_contracts() -> None:
    checker = _load_checker()

    native_widgets = checker.required_widgets_for_preset("native")
    native_present_widgets = checker.present_widgets_for_preset("native")
    moba_widgets = checker.required_widgets_for_preset("mobaxterm")
    moba_present_widgets = checker.present_widgets_for_preset("mobaxterm")

    assert "designSelect" not in native_widgets
    assert "toolbarSearch" not in native_widgets
    assert native_present_widgets["designSelect"] == "view preset selector"
    assert native_present_widgets["toolbarSearch"] == "toolbar search"
    assert "designSelect" not in moba_widgets
    assert "toolbarSearch" not in moba_widgets
    assert "profileTree" not in moba_widgets
    assert "productWorkflowEvidence" not in moba_widgets
    assert checker.required_widgets_for_preset("termius")["termiusHostIdentityStrip"] == (
        "Termius host identity strip"
    )
    assert checker.required_widgets_for_preset("termius")["termiusHostsChrome"] == (
        "Termius Hosts search/action chrome"
    )
    assert checker.required_widgets_for_preset("securecrt")["secureCrtMenuBar"] == "SecureCRT top menu bar"
    assert checker.required_widgets_for_preset("remmina")["remminaProfileListChrome"] == (
        "Remmina profile list chrome"
    )
    assert checker.required_widgets_for_preset("remmina")["remminaSftpTransferPanel"] == (
        "Remmina SFTP transfer panel"
    )
    assert checker.required_widgets_for_preset("mremoteng")["mRemoteNgMenuBar"] == "mRemoteNG top menu bar"
    assert checker.required_widgets_for_preset("mremoteng")["mRemoteNgPropertyGrid"] == (
        "mRemoteNG property inheritance grid"
    )
    assert moba_present_widgets == {}
    assert moba_widgets["mobaQuickConnectChrome"] == "Moba quick connect chrome"
    assert moba_widgets["quickConnect"] == "Moba quick connect field"
    assert moba_widgets["mobaRibbonButton"] == "Moba ribbon action"
    assert moba_widgets["mobaConnectedLeftDock"] == "Moba connected SFTP/monitoring dock"
    assert moba_widgets["terminalPane"] == "Moba native terminal pane"
    assert moba_widgets["terminalOutput"] == "Moba native terminal output"
    assert moba_widgets["mobaTelemetryBar"] == "Moba bottom telemetry bar"
    assert "mobaSshBanner" not in moba_widgets
    assert "mobaRightUtilityRail" not in moba_widgets


def test_real_gui_render_contract_helper_maps_product_labels() -> None:
    checker = _load_checker()
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert checker.interaction_label_for_key("mobaxterm", "tools") == "Tools"
    assert checker.interaction_label_for_key("securecrt", "files") == "SFTP"
    assert checker.interaction_label_for_key("termius", "doctor") == "Vault"
    assert checker.interaction_label_for_key("remmina", "queue") == "Transfer"
    assert checker.interaction_label_for_key("mremoteng", "files") == "External"
    assert checker.tab_position_name("west") == "west"
    assert '"profile-filter": "remminaProfileFilter"' in source
    assert "profile filter must expose focused interactionState" in source
    assert '"tree-filter": "mRemoteNgDocumentFilter"' in source
    assert "document filter must expose focused interactionState" in source


def test_real_gui_render_tracks_live_content_contract_labels() -> None:
    checker = _load_checker()

    assert checker.PRESET_REFERENCE_PROFILES == {
        "mobaxterm": "edge-prod",
        "securecrt": "edge-prod",
        "termius": "edge-prod",
        "remmina": "win-admin",
        "mremoteng": "edge-prod",
    }
    assert checker.EXPECTED_LIVE_REFERENCE_TAB_LABELS["mobaxterm"] == "edge-prod.example.invalid (operator)"
    assert checker.EXPECTED_LIVE_REFERENCE_TAB_LABELS["securecrt"] == "edge-prod (SSH2)"
    assert checker.EXPECTED_LIVE_REFERENCE_TAB_LABELS["remmina"] == "RDP - win-admin"
    assert "edge-prod [SSH]" in checker.EXPECTED_LIVE_TREE_LABELS["mremoteng"]
    assert "Vault / Teams" in checker.EXPECTED_LIVE_TREE_LABELS["termius"]
    assert checker.EXPECTED_MOBA_TELEMETRY_KEYS == {
        "target",
        "cpu",
        "memory",
        "disk",
        "net-up",
        "net-down",
        "connections",
        "processes",
    }


def test_real_gui_render_collects_live_tab_and_tree_labels() -> None:
    checker = _load_checker()

    tabs = _FakeTabs(["Start Page", "edge-prod (SSH2)", "+"])
    tree = _FakeTree([_FakeTreeItem("Session Database", [_FakeTreeItem("Folder: examples")])])

    assert checker.live_tab_labels(tabs) == {"Start Page", "edge-prod (SSH2)", "+"}
    assert checker.collect_tree_labels(tree) == {"Session Database", "Folder: examples"}
    assert set(checker.collect_tree_items_by_label(tree)) == {"Session Database", "Folder: examples"}


def test_real_gui_render_contract_checks_live_workflow_cards() -> None:
    checker = _load_checker()
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "check_live_workflow_cards" in source
    assert "gui_design_workflow_cards" in source
    assert [card.title for card in checker.gui_design_workflow_cards("remmina")] == [
        "Protocol viewer",
        "Scaling controls",
        "Clipboard sync",
    ]


def test_real_gui_render_contract_checks_live_workspace_surface_text() -> None:
    checker = _load_checker()
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    remmina_required = checker.required_workspace_surface_texts("remmina")
    remmina_reference = checker.required_reference_state_texts("remmina")
    assert {
        "Remote desktop viewer",
        "win-admin (RDP)",
        "Scale    : 100%",
        "Viewer tab: win-admin",
        "SFTP transfer: queue ready",
    } <= remmina_required
    assert "active-tab: RDP - win-admin" in remmina_reference
    assert "sidebar: Connection Profiles" in remmina_reference

    securecrt_required = checker.required_workspace_surface_texts("securecrt")
    assert "Command window: enabled" in securecrt_required
    assert "$ ssh -p 22 operator@edge-prod.example" in securecrt_required
    assert checker.required_securecrt_command_window_texts() == {
        "Command Window",
        "send command to active tab or all sessions",
        "All Sessions",
        "$ row doctor --json",
        "Send",
        "ready",
    }
    assert "Target: edge-prod.example.invalid:22" in checker.required_securecrt_session_status_texts()
    assert "Cipher: chacha20-poly1305" in checker.required_securecrt_session_status_texts()
    assert "SFTP: files-prod tab" in checker.required_securecrt_session_status_texts()
    assert "Options" in checker.required_securecrt_top_chrome_texts()
    assert "New Session" in checker.required_securecrt_top_chrome_texts()
    assert "Connections" in checker.required_mremoteng_top_chrome_texts()
    assert "New Conn" in checker.required_mremoteng_top_chrome_texts()
    assert "Forward: 8080 -> localhost:80" in checker.required_termius_host_identity_texts()
    assert "Identity: prod-ed25519" in checker.required_termius_host_identity_texts()
    assert "check_live_reference_state" in source
    assert "check_live_securecrt_session_status_strip" in source
    assert "check_live_securecrt_session_manager_route" in source
    assert "check_live_securecrt_session_manager_filter_route" in source
    assert "check_live_securecrt_sftp_tab_route" in source
    assert "check_live_securecrt_sftp_browser_route" in source
    assert "check_securecrt_sftp_browser_live_action" in source
    assert "securecrt-sftp-browser-live-action-route" in source
    assert "handle_securecrt_sftp_browser_action" in source
    assert "check_live_termius_host_identity_strip" in source
    assert "check_live_termius_host_selection_route" in source
    assert "check_live_termius_port_forward_route" in source
    assert "check_live_termius_snippet_route" in source
    assert "check_termius_snippet_live_run" in source
    assert "check_live_securecrt_command_window" in source
    assert "check_securecrt_command_window_live_submission" in source
    assert "check_live_securecrt_top_chrome" in source
    assert "check_live_mremoteng_top_chrome" in source
    assert "check_live_remmina_clipboard_route" in source
    assert "check_live_remmina_screenshot_route" in source
    assert "check_remmina_screenshot_live_capture" in source
    assert "check_live_remmina_sftp_transfer_route" in source
    assert "check_remmina_sftp_transfer_live_action" in source
    assert "remmina-sftp-transfer-live-queue-route" in source
    assert "handle_remmina_sftp_transfer_action" in source
    assert "gui_design_reference_state" in source
    assert "check_live_preset_reference_tab_route" in source
    assert "reference-tab-activation-route" in source
    assert "check_live_preset_reference_surface_route" in source
    assert "check_live_preset_reference_tab_chrome_route" in source
    assert "reference-tab-chrome-evidence-route" in source
    assert "expected_preset_reference_tab_chrome_route" in source
    assert "check_live_preset_reference_status_bar_route" in source
    assert "reference-status-bar-evidence-route" in source
    assert "expected_preset_reference_status_bar_route" in source
    assert "check_live_preset_reference_session_action_route" in source
    assert "reference-session-actions-route" in source
    assert "expected_preset_reference_session_action_route" in source
    assert "check_live_moba_connected_session_action_route" in source
    assert "connected-session-actions-route" in source
    assert "build_tab_context_menu" in source
    assert "connected session action menu" in source
    assert "route.menu_object" in source
    assert "expected_moba_connected_session_action_route" in source
    assert "EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE" in source
    assert "remote-monitoring-control-route" in source
    assert "expected_moba_remote_monitoring_control_route" in source
    assert "handle_moba_remote_monitoring_toggled" in source
    assert "mobaRemoteMonitoringControlLiveChecked" in source
    assert "EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE" in source
    assert "follow-terminal-folder-control-route" in source
    assert "expected_moba_follow_terminal_folder_control_route" in source
    assert "handle_moba_follow_terminal_folder_toggled" in source
    assert "mobaFollowTerminalFolderControlLiveChecked" in source
    assert "EXPECTED_SECURECRT_SESSION_MANAGER_FILTER_ROUTE" in source
    assert "securecrt-session-manager-filter-route" in source
    assert "expected_securecrt_session_manager_filter_route" in source
    assert "EXPECTED_SECURECRT_SFTP_TAB_ROUTE" in source
    assert "securecrt-sftp-tab-route" in source
    assert "expected_securecrt_sftp_tab_route" in source
    assert "EXPECTED_SECURECRT_SFTP_BROWSER_ROUTE" in source
    assert "securecrt-sftp-browser-route" in source
    assert "expected_securecrt_sftp_browser_route" in source
    assert "EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE" in source
    assert "check_mremoteng_reconnect_live_route" in source
    assert "mremoteng-connection-reconnect-live-route" in source
    assert "handle_mremoteng_document_reconnect" in source
    assert "EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE" in source
    assert "check_live_mremoteng_document_filter_route" in source
    assert "mremoteng-document-filter-route" in source
    assert "expected_mremoteng_document_filter_route" in source
    assert "EXPECTED_MREMOTENG_INHERITANCE_ROUTE" in source
    assert "check_live_mremoteng_inheritance_route" in source
    assert "mremoteng-inheritance-route" in source
    assert "expected_mremoteng_inheritance_route" in source
    assert "EXPECTED_REMMINA_SCREENSHOT_ROUTE" in source
    assert "remmina-screenshot-route" in source
    assert "remmina-screenshot-live-capture-route" in source
    assert "expected_remmina_screenshot_route" in source
    assert "handle_remmina_screenshot_capture" in source
    assert "route.live_triggered_property" in source
    assert "EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE" in source
    assert "remmina-sftp-transfer-route" in source
    assert "remmina-sftp-transfer-live-queue-route" in source
    assert "expected_remmina_sftp_transfer_route" in source
    assert "EXPECTED_TERMIUS_PORT_FORWARD_ROUTE" in source
    assert "termius-port-forward-route" in source
    assert "expected_termius_port_forward_route" in source
    assert "EXPECTED_TERMIUS_SNIPPET_ROUTE" in source
    assert "termius-snippet-route" in source
    assert "termius-snippet-live-run-route" in source
    assert "expected_termius_snippet_route" in source
    assert "handle_termius_snippet_run" in source
    assert "route.live_triggered_property" in source
    assert "check_live_termius_files_browser_route" in source
    assert "check_termius_files_sync_live_action" in source
    assert "EXPECTED_TERMIUS_FILES_BROWSER_ROUTE" in source
    assert "termius-files-browser-route" in source
    assert "termius-files-browser-live-sync-route" in source
    assert "expected_termius_files_browser_route" in source
    assert "handle_termius_files_sync" in source
    assert "reference-surface-evidence-route" in source
    assert "expected_preset_reference_surface_route" in source
    assert "check_live_preset_reference_control_route" in source
    assert "reference-control-evidence-route" in source
    assert "expected_preset_reference_control_route" in source
    assert "check_live_preset_reference_input_route" in source
    assert "reference-input-evidence-route" in source
    assert "expected_preset_reference_input_route" in source
    assert "check_live_preset_reference_transcript_route" in source
    assert "reference-transcript-evidence-route" in source
    assert "expected_preset_reference_transcript_route" in source
    assert "check_live_preset_keyboard_shortcut_route" in source
    assert "preset-keyboard-shortcut-route" in source
    assert "expected_preset_keyboard_shortcut_route" in source
    assert "check_live_preset_command_surface_route" in source
    assert "preset-command-surface-route" in source
    assert "expected_preset_command_surface_route" in source
    assert "check_live_preset_focus_interaction_route" in source
    assert "preset-focus-interaction-route" in source
    assert "expected_preset_focus_interaction_route" in source
    assert "check_live_preset_home_search_route" in source
    assert "preset-home-search-route" in source
    assert "expected_preset_home_search_route" in source


def test_real_gui_render_manifest_records_complete_capture_set(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    captures = [
        checker.CaptureResult("native", "Native", metrics, path="native-live.png"),
        checker.CaptureResult(
            "mobaxterm",
            "MobaXterm-style",
            metrics,
            path="mobaxterm-live.png",
            contract_evidence=_complete_contract_evidence(checker, "mobaxterm"),
        ),
    ]

    checker.write_manifest(tmp_path, captures, ["native", "mobaxterm"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["selected_preset_ids"] == ["native", "mobaxterm"]
    assert manifest["captured_preset_ids"] == ["native", "mobaxterm"]
    assert manifest["expected_capture_count"] == 2
    assert manifest["actual_capture_count"] == 2
    assert manifest["complete_preset_capture"] is True
    assert manifest["missing_capture_preset_ids"] == []
    assert manifest["extra_capture_preset_ids"] == []
    assert manifest["measured_contract_evidence_required_preset_ids"] == ["mobaxterm"]
    assert manifest["measured_contract_evidence_complete"] is True
    assert manifest["missing_contract_evidence_preset_ids"] == []
    assert manifest["incomplete_contract_evidence_preset_ids"] == []
    assert manifest["failed_contract_evidence_preset_ids"] == []


def test_real_gui_render_manifest_records_missing_capture_set(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    captures = [
        checker.CaptureResult("native", "Native", metrics, path="native-live.png"),
    ]

    checker.write_manifest(tmp_path, captures, ["native", "mobaxterm"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["complete_preset_capture"] is False
    assert manifest["missing_capture_preset_ids"] == ["mobaxterm"]
    assert manifest["extra_capture_preset_ids"] == []


def test_real_gui_render_capture_result_records_measured_contract_evidence(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    evidence = {
        "layout_measurements": [
            {
                "id": "session-manager-width",
                "widget": "leftPanel",
                "bounds": {"x": 20, "y": 100, "width": 280, "height": 600},
                "passed": True,
            }
        ],
        "topology_measurements": [
            {
                "id": "sidebar-left-of-tabs",
                "from": "leftPanel",
                "to": "sessionTabs",
                "relation": "left_of",
                "gap": 20,
                "passed": True,
            }
        ],
    }
    captures = [
        checker.CaptureResult(
            "securecrt",
            "SecureCRT-style",
            metrics,
            path="securecrt-live.png",
            contract_evidence=evidence,
        ),
    ]

    checker.write_manifest(tmp_path, captures, ["securecrt"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    capture = manifest["captures"][0]
    assert capture["contract_evidence"] == evidence
    assert capture["contract_evidence"]["layout_measurements"][0]["bounds"]["width"] == 280
    assert capture["contract_evidence"]["topology_measurements"][0]["gap"] == 20
    assert manifest["measured_contract_evidence_required_preset_ids"] == ["securecrt"]
    assert manifest["measured_contract_evidence_complete"] is False
    assert manifest["incomplete_contract_evidence_preset_ids"] == ["securecrt"]


def test_real_gui_render_manifest_audits_missing_measured_contract_evidence(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    captures = [
        checker.CaptureResult("securecrt", "SecureCRT-style", metrics, path="securecrt-live.png"),
    ]

    checker.write_manifest(tmp_path, captures, ["securecrt"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["measured_contract_evidence_required_preset_ids"] == ["securecrt"]
    assert manifest["measured_contract_evidence_complete"] is False
    assert manifest["missing_contract_evidence_preset_ids"] == ["securecrt"]
    assert manifest["incomplete_contract_evidence_preset_ids"] == []
    assert manifest["failed_contract_evidence_preset_ids"] == []


def test_real_gui_render_manifest_audits_complete_measured_contract_evidence(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    captures = [
        checker.CaptureResult(
            "securecrt",
            "SecureCRT-style",
            metrics,
            path="securecrt-live.png",
            contract_evidence=_complete_contract_evidence(checker, "securecrt"),
        ),
    ]

    checker.write_manifest(tmp_path, captures, ["securecrt"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["measured_contract_evidence_required_preset_ids"] == ["securecrt"]
    assert manifest["measured_contract_evidence_complete"] is True
    assert manifest["missing_contract_evidence_preset_ids"] == []
    assert manifest["incomplete_contract_evidence_preset_ids"] == []
    assert manifest["failed_contract_evidence_preset_ids"] == []


def test_real_gui_render_manifest_audits_failed_measured_contract_evidence(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    evidence = _complete_contract_evidence(checker, "securecrt")
    evidence["topology_measurements"][0]["passed"] = False
    captures = [
        checker.CaptureResult(
            "securecrt",
            "SecureCRT-style",
            metrics,
            path="securecrt-live.png",
            contract_evidence=evidence,
        ),
    ]

    checker.write_manifest(tmp_path, captures, ["securecrt"])
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    assert manifest["measured_contract_evidence_complete"] is False
    assert manifest["failed_contract_evidence_preset_ids"] == ["securecrt"]


def test_real_gui_render_measured_contract_evidence_errors_are_actionable() -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    missing = checker.CaptureResult("securecrt", "SecureCRT-style", metrics, path="securecrt-live.png")
    incomplete = checker.CaptureResult(
        "termius",
        "Termius-style",
        metrics,
        path="termius-live.png",
        contract_evidence={"layout_measurements": [], "topology_measurements": []},
    )
    failed_evidence = _complete_contract_evidence(checker, "remmina")
    failed_evidence["layout_measurements"][0]["passed"] = False
    failed = checker.CaptureResult(
        "remmina",
        "Remmina-style",
        metrics,
        path="remmina-live.png",
        contract_evidence=failed_evidence,
    )

    errors = checker.measured_contract_evidence_errors([missing, incomplete, failed])

    assert "missing for presets: securecrt" in errors[0]
    assert "incomplete for presets: termius" in errors[1]
    assert "failed for presets: remmina" in errors[2]


def test_real_gui_render_capture_fails_when_measured_contract_evidence_is_missing(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)

    def fake_capture_live_gui(preset_ids, *, out_dir):
        return [
            checker.CaptureResult("securecrt", "SecureCRT-style", metrics, path="securecrt-live.png"),
        ], [], ["securecrt captured 1420x820, 42 sampled colors"]

    monkeypatch.setattr(checker, "_capture_live_gui", fake_capture_live_gui)

    errors, messages = checker.capture_live_gui(["securecrt"], out_dir=tmp_path)

    assert errors == ["live GUI measured contract evidence missing for presets: securecrt"]
    assert any("securecrt captured" in message for message in messages)
    assert not (tmp_path / checker.MANIFEST_NAME).exists()


def test_real_gui_render_capture_passes_with_complete_measured_contract_evidence(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)

    def fake_capture_live_gui(preset_ids, *, out_dir):
        return [
            checker.CaptureResult(
                "securecrt",
                "SecureCRT-style",
                metrics,
                path="securecrt-live.png",
                contract_evidence=_complete_contract_evidence(checker, "securecrt"),
            ),
        ], [], ["securecrt captured 1420x820, 42 sampled colors"]

    monkeypatch.setattr(checker, "_capture_live_gui", fake_capture_live_gui)

    errors, messages = checker.capture_live_gui(["securecrt"], out_dir=tmp_path)

    assert errors == []
    assert any("wrote live screenshot manifest" in message for message in messages)
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["measured_contract_evidence_complete"] is True


def test_real_gui_render_manifest_records_live_contract_summaries(tmp_path: Path) -> None:
    checker = _load_checker()
    metrics = checker.RenderMetrics(1420, 820, 128, 42, 80, 0.25)
    captures = [
        checker.CaptureResult("native", "Native", metrics, path="native-live.png"),
        checker.CaptureResult("mobaxterm", "MobaXterm-style", metrics, path="mobaxterm-live.png"),
        checker.CaptureResult("securecrt", "SecureCRT-style", metrics, path="securecrt-live.png"),
        checker.CaptureResult("remmina", "Remmina-style", metrics, path="remmina-live.png"),
        checker.CaptureResult("termius", "Termius-style", metrics, path="termius-live.png"),
        checker.CaptureResult("mremoteng", "mRemoteNG-style", metrics, path="mremoteng-live.png"),
    ]

    checker.write_manifest(
        tmp_path,
        captures,
        ["native", "mobaxterm", "securecrt", "remmina", "termius", "mremoteng"],
    )
    manifest = checker.json.loads((tmp_path / checker.MANIFEST_NAME).read_text(encoding="utf-8"))

    summaries = manifest["preset_live_contracts"]
    assert set(summaries) == {"native", "mobaxterm", "securecrt", "remmina", "termius", "mremoteng"}
    for preset_id, summary in summaries.items():
        catalog_route = summary["expected_preset_catalog_route"]
        isolation_route = summary["expected_preset_isolation_route"]
        keyboard_shortcut_route = summary["expected_preset_keyboard_shortcut_route"]
        command_surface_route = summary["expected_preset_command_surface_route"]
        focus_interaction_route = summary["expected_preset_focus_interaction_route"]
        home_search_route = summary["expected_preset_home_search_route"]
        moba_connected_session_action_route = summary["expected_moba_connected_session_action_route"]
        moba_remote_monitoring_control_route = summary["expected_moba_remote_monitoring_control_route"]
        moba_follow_terminal_folder_control_route = summary[
            "expected_moba_follow_terminal_folder_control_route"
        ]
        reference_control_route = summary["expected_preset_reference_control_route"]
        reference_input_route = summary["expected_preset_reference_input_route"]
        reference_session_action_route = summary["expected_preset_reference_session_action_route"]
        reference_status_bar_route = summary["expected_preset_reference_status_bar_route"]
        reference_surface_route = summary["expected_preset_reference_surface_route"]
        reference_tab_route = summary["expected_preset_reference_tab_route"]
        reference_tab_chrome_route = summary["expected_preset_reference_tab_chrome_route"]
        reference_transcript_route = summary["expected_preset_reference_transcript_route"]
        selection_route = summary["expected_preset_selection_route"]
        transition_route = summary["expected_preset_transition_route"]
        visual_signature = summary["expected_preset_visual_signature"]
        assert "preset-catalog-route" in summary["contract_checks"]
        assert "preset-isolation-route" in summary["contract_checks"]
        assert "preset-selection-route" in summary["contract_checks"]
        assert "preset-transition-route" in summary["contract_checks"]
        assert "preset-visual-signature" in summary["contract_checks"]
        assert catalog_route["key"] == "gui-preset-selector-catalog-route"
        assert catalog_route["selector_object"] == "designSelect"
        assert catalog_route["default_preset_id"] == "native"
        assert catalog_route["option_ids"] == ["native", "mobaxterm", "securecrt", "termius", "remmina", "mremoteng"]
        assert catalog_route["option_count"] == 6
        assert catalog_route["product_preset_ids"] == ["mobaxterm", "securecrt", "termius", "remmina", "mremoteng"]
        assert catalog_route["product_option_count"] == 5
        assert catalog_route["render_source"] == "gui-design-preset-catalog"
        assert isolation_route["key"] == f"{preset_id}-preset-isolation-route"
        assert isolation_route["route_role"] == "active-preset-visible-hidden-widget-isolation"
        assert isolation_route["preset_id"] == preset_id
        assert isolation_route["visible_objects"]
        assert "mainToolbar" in isolation_route["visible_objects"]
        assert "sessionTabs" in isolation_route["visible_objects"]
        assert not (set(isolation_route["visible_objects"]) & set(isolation_route["hidden_objects"]))
        assert isolation_route["visible_property"] == "presetIsolationVisibleObjects"
        assert isolation_route["hidden_property"] == "presetIsolationHiddenObjects"
        assert isolation_route["render_source"] == "gui-design-preset-visibility"
        if preset_id == "mobaxterm":
            assert "mobaSshBanner" not in isolation_route["visible_objects"]
            assert "mobaRightUtilityRail" not in isolation_route["visible_objects"]
        assert selection_route["key"] == f"{preset_id}-preset-selection-route"
        assert selection_route["preset_id"] == preset_id
        assert selection_route["selector_object"] == "designSelect"
        assert selection_route["main_toolbar_object"] == "mainToolbar"
        assert selection_route["layout_toolbar_object"] == "layoutToolbar"
        assert selection_route["left_panel_header_object"] == "leftPanelHeader"
        assert selection_route["profile_tree_object"] == "profileTree"
        assert selection_route["tabs_object"] == "sessionTabs"
        assert selection_route["status_bar_object"] == "statusBar"
        assert selection_route["status_segment_object"] == "productStatusSegment"
        assert selection_route["workspace_surface_object"] == "productWorkspaceSurface"
        assert selection_route["reference_state_object"] == "productReferenceState"
        assert selection_route["status_segments"]
        assert selection_route["render_source"] == "gui-design-preset-metadata"
        assert transition_route["key"] == f"{preset_id}-preset-transition-route"
        assert transition_route["route_role"] == "selector-style-switch-resets-inactive-product-chrome"
        assert transition_route["to_preset_id"] == preset_id
        assert transition_route["selector_object"] == "designSelect"
        assert preset_id not in transition_route["from_preset_ids"]
        assert transition_route["from_preset_ids"]
        assert set(transition_route["reset_objects"]) == set(isolation_route["hidden_objects"])
        assert transition_route["route_property"] == "presetTransitionRouteKey"
        assert transition_route["from_property"] == "presetTransitionFromPresetIds"
        assert transition_route["to_property"] == "presetTransitionToPresetId"
        assert transition_route["reset_property"] == "presetTransitionResetObjects"
        assert transition_route["render_source"] == "gui-design-preset-transition"
        if preset_id in checker.EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES:
            assert "preset-keyboard-shortcut-route" in summary["contract_checks"]
            assert keyboard_shortcut_route["key"] == f"{preset_id}-keyboard-shortcut-route"
            if preset_id == "mobaxterm":
                assert keyboard_shortcut_route["key"] == "mobaxterm-keyboard-shortcut-route"
            assert keyboard_shortcut_route["route_role"] == "product-preset-keyboard-shortcuts"
            assert keyboard_shortcut_route["preset_id"] == preset_id
            assert keyboard_shortcut_route["shortcut_object"] == "presetKeyboardShortcut"
            assert keyboard_shortcut_route["expected_shortcut_keys"] == [
                "refresh-profiles",
                "new-profile",
                "edit-profile",
                "connect-selected",
                "new-local-terminal",
                "close-current-tab",
                "recover-previous-sessions",
                "split-horizontal",
                "split-vertical",
                "open-selected-layout",
                "find-log-text",
            ]
            assert keyboard_shortcut_route["expected_sequences"] == [
                "Ctrl+R",
                "Ctrl+N",
                "Ctrl+E",
                "Ctrl+Return",
                "Ctrl+T",
                "Ctrl+W",
                "Ctrl+Shift+T",
                "Ctrl+Shift+H",
                "Ctrl+Shift+V",
                "Ctrl+L",
                "Ctrl+F",
            ]
            assert keyboard_shortcut_route["expected_action_labels"] == [
                "Refresh profiles",
                "New profile",
                "Edit selected profile",
                "Connect selected profile",
                "New local terminal",
                "Close current tab",
                "Recover previous sessions",
                "Split horizontal",
                "Split vertical",
                "Open selected layout",
                "Find log text",
            ]
            assert keyboard_shortcut_route["expected_shortcut_count"] == 11
            assert keyboard_shortcut_route["shortcut_key_property"] == "presetKeyboardShortcutKey"
            assert keyboard_shortcut_route["captured_sequences_property"] == "presetKeyboardShortcutCapturedSequences"
            assert keyboard_shortcut_route["render_source"] == "gui-design-keyboard-shortcuts"
        else:
            assert "preset-keyboard-shortcut-route" not in summary["contract_checks"]
            assert keyboard_shortcut_route == {}
        if preset_id in checker.EXPECTED_PRESET_COMMAND_SURFACE_ROUTES:
            assert "preset-command-surface-route" in summary["contract_checks"]
            assert command_surface_route["key"] == f"{preset_id}-command-surface-route"
            assert command_surface_route["route_role"] == "product-preset-command-surface-route"
            assert command_surface_route["preset_id"] == preset_id
            assert command_surface_route["toolbar_object"] == "mainToolbar"
            assert command_surface_route["command_object"] in {"mobaRibbonButton", "productToolbarButton"}
            assert command_surface_route["expected_action_count"] == len(
                command_surface_route["expected_action_keys"]
            )
            assert command_surface_route["expected_action_count"] == len(
                command_surface_route["expected_action_labels"]
            )
            assert command_surface_route["expected_action_count"] == len(
                command_surface_route["expected_action_tooltips"]
            )
            assert command_surface_route["expected_action_states"]
            assert command_surface_route["key_property"] == "presetCommandSurfaceActionKey"
            assert command_surface_route["label_property"] == "presetCommandSurfaceActionLabel"
            assert command_surface_route["tooltip_property"] == "presetCommandSurfaceActionTooltip"
            assert command_surface_route["state_property"] == "interactionState"
            assert command_surface_route["captured_keys_property"] == "presetCommandSurfaceCapturedKeys"
            assert command_surface_route["captured_states_property"] == "presetCommandSurfaceCapturedStates"
            assert command_surface_route["render_source"] == "gui-design-command-surface-route"
        else:
            assert "preset-command-surface-route" not in summary["contract_checks"]
            assert command_surface_route == {}
        if preset_id in checker.EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES:
            assert "preset-focus-interaction-route" in summary["contract_checks"]
            assert focus_interaction_route["key"] == f"{preset_id}-focus-interaction-route"
            assert focus_interaction_route["route_role"] == "product-preset-focus-interaction-route"
            assert focus_interaction_route["preset_id"] == preset_id
            assert focus_interaction_route["focus_object"] in {
                "quickConnect",
                "secureCrtSessionFilter",
                "termiusHostSearch",
                "remminaProfileFilter",
                "mRemoteNgDocumentFilter",
            }
            assert focus_interaction_route["focused_control"]
            assert focus_interaction_route["active_toolbar_key"]
            assert focus_interaction_route["checked_toolbar_key"]
            assert focus_interaction_route["disabled_toolbar_key"] == ""
            assert focus_interaction_route["selected_tree_label"]
            assert focus_interaction_route["active_tab_status"]
            assert focus_interaction_route["status_note"]
            assert focus_interaction_route["status_bar_object"] == "statusBar"
            assert focus_interaction_route["profile_tree_object"] == "profileTree"
            assert focus_interaction_route["focused_state_property"] == "interactionState"
            assert focus_interaction_route["captured_focus_property"] == "presetFocusInteractionCapturedFocus"
            assert (
                focus_interaction_route["captured_selected_tree_property"]
                == "presetFocusInteractionCapturedSelectedTreeLabel"
            )
            assert focus_interaction_route["captured_toolbar_states_property"] == "presetFocusInteractionToolbarStates"
            assert focus_interaction_route["render_source"] == "gui-design-focus-interaction-route"
        else:
            assert "preset-focus-interaction-route" not in summary["contract_checks"]
            assert focus_interaction_route == {}
        if preset_id in checker.EXPECTED_PRESET_HOME_SEARCH_ROUTES:
            assert "preset-home-search-route" in summary["contract_checks"]
            assert home_search_route["key"] == f"{preset_id}-home-search-route"
            assert home_search_route["route_role"] == "product-preset-home-search-entry-route"
            assert home_search_route["preset_id"] == preset_id
            assert home_search_route["home_search_object"] == "homeSearch"
            assert home_search_route["entry_search_object"] in {
                "quickConnect",
                "secureCrtSessionFilter",
                "termiusHostSearch",
                "remminaProfileFilter",
                "mRemoteNgDocumentFilter",
            }
            assert home_search_route["container_object"] in {"mobaHomeWelcomeSurface", "welcomePanel"}
            assert home_search_route["placeholder_text"]
            assert home_search_route["entry_placeholder_text"]
            assert home_search_route["expected_home_actions"]
            assert home_search_route["expected_recent_count"] == len(home_search_route["expected_recent_labels"])
            assert home_search_route["captured_placeholder_property"] == "presetHomeSearchCapturedPlaceholder"
            assert home_search_route["captured_entry_placeholder_property"] == "presetHomeSearchCapturedEntryPlaceholder"
            assert home_search_route["captured_recent_labels_property"] == "presetHomeSearchCapturedRecentLabels"
            assert home_search_route["render_source"] == "gui-design-home-search-route"
        else:
            assert "preset-home-search-route" not in summary["contract_checks"]
            assert home_search_route == {}
        if preset_id == "mobaxterm":
            assert "connected-session-actions-route" in summary["contract_checks"]
            assert "remote-monitoring-control-route" in summary["contract_checks"]
            assert "follow-terminal-folder-control-route" in summary["contract_checks"]
            assert moba_connected_session_action_route["key"] == "moba-connected-session-actions-route"
            assert (
                moba_connected_session_action_route["route_role"]
                == "active-connected-tab-context-session-actions"
            )
            assert moba_connected_session_action_route["profile_name"] == "edge-prod"
            assert moba_connected_session_action_route["active_tab_key"] == "active-session"
            assert moba_connected_session_action_route["tabs_object"] == "sessionTabs"
            assert moba_connected_session_action_route["tab_bar_object"] == "sessionTabBar"
            assert moba_connected_session_action_route["menu_object"] == "mobaConnectedSessionTabContextMenu"
            assert moba_connected_session_action_route["expected_action_count"] == 8
            assert moba_connected_session_action_route["conditional_enabled_action_keys"] == ["close-other-tabs"]
            assert (
                moba_connected_session_action_route["captured_enabled_keys_property"]
                == "mobaConnectedSessionActionEnabledKeys"
            )
            assert moba_connected_session_action_route["render_source"] == "connected-session-state"
            assert moba_remote_monitoring_control_route["key"] == "moba-remote-monitoring-control-route"
            assert (
                moba_remote_monitoring_control_route["route_role"]
                == "remote-monitoring-control-to-telemetry-refresh"
            )
            assert moba_remote_monitoring_control_route["source_control_key"] == "remote-monitoring"
            assert moba_remote_monitoring_control_route["expected_checked"] is True
            assert moba_remote_monitoring_control_route["telemetry_route_key"] == "remote-monitoring-to-bottom-telemetry"
            assert moba_remote_monitoring_control_route["captured_command_property"] == (
                "mobaRemoteMonitoringControlCapturedCommand"
            )
            assert moba_remote_monitoring_control_route["signal"] == "toggled"
            assert moba_remote_monitoring_control_route["handler"] == "handle_moba_remote_monitoring_toggled"
            assert (
                moba_remote_monitoring_control_route["live_checked_property"]
                == "mobaRemoteMonitoringControlLiveChecked"
            )
            assert (
                moba_follow_terminal_folder_control_route["key"]
                == "moba-follow-terminal-folder-control-route"
            )
            assert (
                moba_follow_terminal_folder_control_route["route_role"]
                == "follow-terminal-folder-control-to-sftp-browser-sync"
            )
            assert moba_follow_terminal_folder_control_route["source_control_key"] == "follow-terminal-folder"
            assert moba_follow_terminal_folder_control_route["source_control_object"] == "mobaFollowTerminalFolder"
            assert moba_follow_terminal_folder_control_route["source_control_label"] == "Follow terminal folder"
            assert moba_follow_terminal_folder_control_route["expected_checked"] is True
            assert moba_follow_terminal_folder_control_route["target_path_object"] == "mobaSftpPath"
            assert moba_follow_terminal_folder_control_route["target_table_object"] == "mobaSftpFileTable"
            assert moba_follow_terminal_folder_control_route["captured_plan_property"] == (
                "mobaFollowTerminalFolderControlCapturedPlan"
            )
            assert moba_follow_terminal_folder_control_route["signal"] == "toggled"
            assert moba_follow_terminal_folder_control_route["handler"] == (
                "handle_moba_follow_terminal_folder_toggled"
            )
            assert (
                moba_follow_terminal_folder_control_route["live_checked_property"]
                == "mobaFollowTerminalFolderControlLiveChecked"
            )
        else:
            assert "connected-session-actions-route" not in summary["contract_checks"]
            assert "remote-monitoring-control-route" not in summary["contract_checks"]
            assert "follow-terminal-folder-control-route" not in summary["contract_checks"]
            assert moba_connected_session_action_route == {}
            assert moba_remote_monitoring_control_route == {}
            assert moba_follow_terminal_folder_control_route == {}
        if preset_id in checker.EXPECTED_PRESET_REFERENCE_TAB_ROUTES:
            identity_route = summary["expected_product_identity_route"]
            assert "reference-tab-activation-route" in summary["contract_checks"]
            assert "reference-tab-chrome-evidence-route" in summary["contract_checks"]
            assert "reference-status-bar-evidence-route" in summary["contract_checks"]
            assert "reference-session-actions-route" in summary["contract_checks"]
            assert "reference-surface-evidence-route" in summary["contract_checks"]
            assert "reference-control-evidence-route" in summary["contract_checks"]
            assert "reference-input-evidence-route" in summary["contract_checks"]
            assert "reference-transcript-evidence-route" in summary["contract_checks"]
            assert reference_tab_route["key"] == f"{preset_id}-reference-tab-activation-route"
            assert reference_tab_route["route_role"] == "reference-profile-tab-can-be-active-surface"
            assert reference_tab_route["preset_id"] == preset_id
            assert reference_tab_route["reference_profile"] == identity_route["selected_profile_name"]
            assert reference_tab_route["active_tab_label"] == identity_route["active_tab_label"]
            assert reference_tab_route["home_tab_label"] == selection_route["home_tab_label"]
            assert reference_tab_route["tabs_object"] == "sessionTabs"
            assert reference_tab_route["home_tab_role"] == "home"
            assert reference_tab_route["reference_tab_role"] == "terminal"
            assert reference_tab_route["activated_label_property"] == "presetReferenceTabActivatedLabel"
            assert reference_tab_route["returned_home_label_property"] == "presetReferenceTabReturnedHomeLabel"
            assert reference_tab_route["render_source"] == "gui-design-reference-tab-route"
            assert reference_tab_chrome_route["key"] == f"{preset_id}-reference-tab-chrome-evidence-route"
            assert reference_tab_chrome_route["route_role"] == "active-reference-tab-chrome-evidence"
            assert reference_tab_chrome_route["reference_profile"] == reference_tab_route["reference_profile"]
            assert reference_tab_chrome_route["active_tab_label"] == reference_tab_route["active_tab_label"]
            assert reference_tab_chrome_route["tabs_object"] == "sessionTabs"
            assert reference_tab_chrome_route["tab_bar_object"] == "sessionTabBar"
            assert reference_tab_chrome_route["reference_tab_role"] == "terminal"
            assert reference_tab_chrome_route["new_session_tab_role"] == "new-session"
            assert reference_tab_chrome_route["expected_tab_position"] == visual_signature["tab_position"]
            assert reference_tab_chrome_route["expected_tooltip"].startswith(reference_tab_route["active_tab_label"])
            assert reference_tab_chrome_route["expected_closeable"] is True
            assert reference_tab_chrome_route["expected_selected_during_capture"] is True
            assert reference_tab_chrome_route["captured_tooltip_property"] == "presetReferenceTabChromeTooltip"
            assert reference_tab_chrome_route["captured_position_property"] == "presetReferenceTabChromePosition"
            assert reference_tab_chrome_route["captured_closeable_property"] == "presetReferenceTabChromeCloseable"
            assert reference_tab_chrome_route["render_source"] == "gui-design-reference-tab-chrome"
            assert reference_status_bar_route["key"] == f"{preset_id}-reference-status-bar-evidence-route"
            assert reference_status_bar_route["route_role"] == "active-reference-status-bar-evidence"
            assert reference_status_bar_route["reference_profile"] == reference_tab_route["reference_profile"]
            assert reference_status_bar_route["active_tab_label"] == reference_tab_route["active_tab_label"]
            assert reference_status_bar_route["status_bar_object"] == "statusBar"
            assert reference_status_bar_route["status_notice_object"] == "productStatusNotice"
            assert reference_status_bar_route["status_segment_object"] == "productStatusSegment"
            expected_status_message = (
                "Running process panes: 2" if preset_id == "remmina" else "Running process panes: 1"
            )
            assert reference_status_bar_route["expected_status_message"] == expected_status_message
            assert reference_status_bar_route["expected_status_segments"] == identity_route["status_segments"]
            assert reference_status_bar_route["expected_segment_count"] == len(identity_route["status_segments"])
            assert reference_status_bar_route["captured_message_property"] == "presetReferenceStatusMessage"
            assert reference_status_bar_route["captured_segments_property"] == "presetReferenceStatusSegments"
            assert reference_status_bar_route["captured_notice_property"] == "presetReferenceStatusNotice"
            assert reference_status_bar_route["render_source"] == "gui-design-reference-status-bar"
            assert reference_session_action_route["key"] == f"{preset_id}-reference-session-actions-route"
            assert reference_session_action_route["route_role"] == "active-reference-session-actions"
            assert reference_session_action_route["reference_profile"] == reference_tab_route["reference_profile"]
            assert reference_session_action_route["active_tab_label"] == reference_tab_route["active_tab_label"]
            assert reference_session_action_route["tabs_object"] == "sessionTabs"
            assert reference_session_action_route["tab_bar_object"] == "sessionTabBar"
            assert reference_session_action_route["reference_tab_role"] == "terminal"
            assert reference_session_action_route["action_object"] == "sessionTabContextAction"
            assert reference_session_action_route["expected_action_keys"] == [
                "new-local-terminal",
                "split-horizontal",
                "split-vertical",
                "duplicate-tab",
                "close-tab",
                "close-other-tabs",
                "recover-previous-sessions",
            ]
            assert reference_session_action_route["expected_action_labels"] == [
                "New local terminal",
                "Split horizontal",
                "Split vertical",
                "Duplicate tab",
                "Close tab",
                "Close other tabs",
                "Recover previous sessions",
            ]
            assert reference_session_action_route["expected_action_count"] == 7
            assert reference_session_action_route["always_enabled_action_keys"] == [
                "new-local-terminal",
                "split-horizontal",
                "split-vertical",
                "duplicate-tab",
                "close-tab",
                "recover-previous-sessions",
            ]
            assert reference_session_action_route["conditional_enabled_action_keys"] == ["close-other-tabs"]
            assert reference_session_action_route["action_key_property"] == "sessionTabContextActionKey"
            assert reference_session_action_route["captured_action_keys_property"] == "presetReferenceSessionActionKeys"
            assert (
                reference_session_action_route["captured_enabled_keys_property"]
                == "presetReferenceSessionActionEnabledKeys"
            )
            assert reference_session_action_route["render_source"] == "gui-design-reference-session-actions"
            assert reference_surface_route["key"] == f"{preset_id}-reference-surface-evidence-route"
            assert reference_surface_route["route_role"] == "active-reference-tab-surface-evidence"
            assert reference_surface_route["preset_id"] == preset_id
            assert reference_surface_route["reference_profile"] == reference_tab_route["reference_profile"]
            assert reference_surface_route["active_tab_label"] == reference_tab_route["active_tab_label"]
            assert reference_surface_route["expected_title"] == reference_tab_route["reference_profile"]
            assert reference_surface_route["expected_source"] == f"profile:{reference_tab_route['reference_profile']}"
            assert reference_surface_route["command_target_fragment"] in identity_route["target_label"]
            assert reference_surface_route["terminal_pane_object"] == "terminalPane"
            assert reference_surface_route["terminal_command_object"] == "terminalCommand"
            assert reference_surface_route["terminal_output_object"] == "terminalOutput"
            assert reference_surface_route["captured_property"] == "presetReferenceSurfaceCaptured"
            assert reference_surface_route["actual_command_property"] == "presetReferenceSurfaceActualCommand"
            assert reference_surface_route["render_source"] == "gui-design-reference-surface"
            assert reference_control_route["key"] == f"{preset_id}-reference-control-evidence-route"
            assert reference_control_route["route_role"] == "active-reference-tab-terminal-controls"
            assert reference_control_route["reference_profile"] == reference_surface_route["reference_profile"]
            assert reference_control_route["active_tab_label"] == reference_surface_route["active_tab_label"]
            assert reference_control_route["terminal_pane_object"] == "terminalPane"
            assert reference_control_route["terminal_status_object"] == "paneStatus"
            assert reference_control_route["terminal_action_object"] == "terminalAction"
            assert reference_control_route["action_keys"] == [
                "start",
                "restart",
                "stop",
                "copy",
                "clear",
                "macro-rec",
                "macro-stop",
                "macro-cancel",
                "macro-replay",
            ]
            assert reference_control_route["action_labels"] == [
                "Start",
                "Restart",
                "Stop",
                "Copy",
                "Clear",
                "Macro Rec",
                "Macro Stop",
                "Macro Cancel",
                "Macro Replay",
            ]
            assert reference_control_route["captured_actions_property"] == "presetReferenceControlCapturedActionKeys"
            assert reference_control_route["captured_status_property"] == "presetReferenceControlStatusState"
            assert reference_control_route["render_source"] == "gui-design-reference-controls"
            assert reference_input_route["key"] == f"{preset_id}-reference-input-evidence-route"
            assert reference_input_route["route_role"] == "active-reference-tab-terminal-input"
            assert reference_input_route["reference_profile"] == reference_surface_route["reference_profile"]
            assert reference_input_route["active_tab_label"] == reference_surface_route["active_tab_label"]
            assert reference_input_route["terminal_input_object"] == "terminalInput"
            assert reference_input_route["placeholder_text"] == "stdin, shell command or interactive input"
            assert reference_input_route["expected_initial_text"] == ""
            assert reference_input_route["allowed_enabled_states"] == [True, False]
            assert reference_input_route["captured_placeholder_property"] == "presetReferenceInputPlaceholder"
            assert reference_input_route["captured_enabled_property"] == "presetReferenceInputEnabled"
            assert reference_input_route["render_source"] == "gui-design-reference-input"
            assert reference_transcript_route["key"] == f"{preset_id}-reference-transcript-evidence-route"
            assert reference_transcript_route["route_role"] == "active-reference-tab-terminal-transcript"
            assert reference_transcript_route["reference_profile"] == reference_surface_route["reference_profile"]
            assert reference_transcript_route["active_tab_label"] == reference_surface_route["active_tab_label"]
            assert reference_transcript_route["terminal_output_object"] == "terminalOutput"
            assert reference_transcript_route["command_echo_prefix"] == "$ "
            assert reference_surface_route["command_target_fragment"] in reference_transcript_route["required_fragments"]
            assert reference_transcript_route["minimum_line_count"] == 1
            assert reference_transcript_route["captured_text_property"] == "presetReferenceTranscriptText"
            assert reference_transcript_route["captured_line_count_property"] == "presetReferenceTranscriptLineCount"
            assert reference_transcript_route["captured_command_echo_property"] == "presetReferenceTranscriptCommandEcho"
            assert reference_transcript_route["render_source"] == "gui-design-reference-transcript"
        else:
            assert "reference-tab-activation-route" not in summary["contract_checks"]
            assert "reference-tab-chrome-evidence-route" not in summary["contract_checks"]
            assert "reference-status-bar-evidence-route" not in summary["contract_checks"]
            assert "reference-session-actions-route" not in summary["contract_checks"]
            assert "reference-surface-evidence-route" not in summary["contract_checks"]
            assert "reference-control-evidence-route" not in summary["contract_checks"]
            assert "reference-input-evidence-route" not in summary["contract_checks"]
            assert "reference-transcript-evidence-route" not in summary["contract_checks"]
            assert reference_tab_route == {}
            assert reference_tab_chrome_route == {}
            assert reference_status_bar_route == {}
            assert reference_session_action_route == {}
            assert reference_surface_route == {}
            assert reference_control_route == {}
            assert reference_input_route == {}
            assert reference_transcript_route == {}
        assert visual_signature["key"] == f"{preset_id}-visual-signature"
        assert visual_signature["preset_id"] == preset_id
        assert visual_signature["palette"]["window"].startswith("#")
        assert visual_signature["palette"]["terminal"].startswith("#")
        assert visual_signature["palette"]["terminal_accent"].startswith("#")
        assert visual_signature["window_object"] == "remoteOpsMain"
        assert visual_signature["main_toolbar_object"] == "mainToolbar"
        assert visual_signature["profile_tree_object"] == "profileTree"
        assert visual_signature["tabs_object"] == "sessionTabs"
        assert visual_signature["activity_log_object"] == "activityLog"
        assert visual_signature["status_bar_object"] == "statusBar"
        assert visual_signature["density_property"] == "presetVisualSignatureDensity"
        assert visual_signature["palette_property"] == "presetVisualSignaturePalette"
        assert visual_signature["render_source"] == "gui-design-preset-style"

    moba = summaries["mobaxterm"]
    assert "mobaQuickConnectChrome" in moba["required_widgets"]
    assert "mobaConnectedLeftDock" in moba["required_widgets"]
    assert "mobaSftpBrowser" in moba["required_widgets"]
    assert "mobaSftpFileTable" in moba["required_widgets"]
    assert "mobaSessionEdgeControls" not in moba["required_widgets"]
    assert "terminalPane" in moba["required_widgets"]
    assert "terminalOutput" in moba["required_widgets"]
    assert "mobaRightUtilityRail" not in moba["required_widgets"]
    assert "mobaBottomEdgeControls" in moba["required_widgets"]
    assert moba["present_widgets"] == {}
    assert moba["reference_profile"] == "edge-prod"
    assert moba["expected_reference_tab_label"] == "edge-prod.example.invalid (operator)"
    assert {
        "connected-left-dock",
        "sftp-file-table",
        "native-terminal-workspace",
        "bottom-edge-controls",
    } <= set(moba["layout_contract_ids"])
    assert "session-edge-controls" not in moba["layout_contract_ids"]
    assert {"dock-left-of-native-terminal", "sftp-table-inside-dock"} <= set(
        moba["topology_contract_ids"]
    )
    assert "moba-rail-roles" in moba["contract_checks"]
    assert "moba-rail-labels" in moba["contract_checks"]
    assert "moba-rail-geometry" in moba["contract_checks"]
    assert "moba-home-welcome" in moba["contract_checks"]
    assert "moba-home-welcome-geometry" in moba["contract_checks"]
    assert "titlebar-chrome" in moba["contract_checks"]
    assert "top-stack-geometry" in moba["contract_checks"]
    assert "top-menu-chrome" in moba["contract_checks"]
    assert "top-menu-geometry" in moba["contract_checks"]
    assert "ribbon-geometry" in moba["contract_checks"]
    assert "ribbon-edge-action-route" in moba["contract_checks"]
    assert "quick-connect-chrome" in moba["contract_checks"]
    assert "quick-connect-suggestions" in moba["contract_checks"]
    assert "connected-quick-connect-idle" in moba["contract_checks"]
    assert "moba-session-tree-icons" in moba["contract_checks"]
    assert "moba-session-tree-geometry" in moba["contract_checks"]
    assert "connected-tab-chrome" in moba["contract_checks"]
    assert "connected-tab-geometry" in moba["contract_checks"]
    assert "connected-dock-frame" in moba["contract_checks"]
    assert "connected-session-route" in moba["contract_checks"]
    assert "connected-session-identity-route" in moba["contract_checks"]
    assert "session-edge-controls" in moba["contract_checks"]
    assert "session-edge-geometry" in moba["contract_checks"]
    assert "session-edge-action-route" in moba["contract_checks"]
    assert "right-utility-rail" not in moba["contract_checks"]
    assert "ssh-banner-chrome" not in moba["contract_checks"]
    assert "terminal-transcript" not in moba["contract_checks"]
    assert "terminal-transcript-geometry" not in moba["contract_checks"]
    assert "terminal-runtime-output" in moba["contract_checks"]
    assert "truthful-terminal-preamble" in moba["contract_checks"]
    assert "native-pty-input-visibility" in moba["contract_checks"]
    assert "terminal-context-menu" in moba["contract_checks"]
    assert "telemetry-context-menu" in moba["contract_checks"]
    assert "sftp-toolbar-groups" in moba["contract_checks"]
    assert "sftp-toolbar-geometry" in moba["contract_checks"]
    assert "sftp-toolbar-action-route" in moba["contract_checks"]
    assert "sftp-dock-chrome" in moba["contract_checks"]
    assert "sftp-dock-density" in moba["contract_checks"]
    assert "sftp-browser-chrome" in moba["contract_checks"]
    assert "sftp-browser-geometry" in moba["contract_checks"]
    assert "sftp-follow-folder-route" in moba["contract_checks"]
    assert "sftp-routed-file-rows" in moba["contract_checks"]
    assert "bottom-status-chrome" in moba["contract_checks"]
    assert "bottom-status-geometry" in moba["contract_checks"]
    assert "bottom-telemetry-geometry" in moba["contract_checks"]
    assert "bottom-edge-controls" in moba["contract_checks"]
    assert "live-topology" in moba["contract_checks"]
    assert "remote-monitoring-dock" in moba["contract_checks"]
    assert "remote-monitoring-compact" in moba["contract_checks"]
    assert "monitoring-telemetry-route" in moba["contract_checks"]
    assert "remote-monitoring-control-route" in moba["contract_checks"]
    assert "follow-terminal-folder-control-route" in moba["contract_checks"]
    assert "moba-monitoring-controls" in moba["contract_checks"]
    assert moba["expected_product_tree_icons"][:4] == [
        {"label": "User sessions", "icon_key": "folder", "row_kind": "root", "static_size": 16},
        {"label": "default", "icon_key": "folder", "row_kind": "group", "static_size": 15},
        {"label": "example.jump-ssh", "icon_key": "pin", "row_kind": "profile", "static_size": 14},
        {"label": "example.rdp", "icon_key": "rdp", "row_kind": "profile", "static_size": 14},
    ]
    assert moba["expected_moba_session_tree_chrome"] == {
        "header_height": 28,
        "header_icon_x": 9,
        "header_text_x": 31,
        "row_start_y": 38,
        "indentation": 16,
        "root_row_height": 28,
        "group_row_height": 24,
        "profile_row_height": 34,
        "group_icon_x": 29,
        "group_label_x": 51,
        "profile_icon_x": 39,
        "profile_label_x": 61,
        "profile_target_x": 61,
        "selected_left": 28,
        "selected_height": 34,
        "render_source": "generated-pixmap",
    }
    assert "terminal" in moba["expected_moba_sftp_action_keys"]
    assert moba["expected_moba_rail_chrome"] == {
        "rail_width": 28,
        "icon_x": 6,
        "static_icon_size": 16,
        "live_icon_size": 20,
        "generated_icon_size": 22,
        "button_width": 28,
        "button_height": 26,
        "active_x": 2,
        "active_y_offset": -3,
        "active_width": 24,
        "active_height": 30,
        "label_width": 28,
        "label_height": 54,
        "label_step": 58,
        "unlabeled_gap_after": 8,
        "label_font_size": 12,
        "render_source": "generated-pixmap",
    }
    assert moba["expected_moba_rail_items"] == [
        {
            "role": "collapse",
            "label": "",
            "icon_key": "session",
            "rail_icon_key": "collapse",
            "object_name": "mobaRailButton",
        },
        {
            "role": "sessions",
            "label": "Sessions",
            "icon_key": "session",
            "rail_icon_key": "session",
            "object_name": "mobaRailButton",
        },
        {
            "role": "favorites",
            "label": "",
            "icon_key": "sessions",
            "rail_icon_key": "star",
            "object_name": "mobaRailAccent",
        },
        {
            "role": "tools",
            "label": "Tools",
            "icon_key": "tools",
            "rail_icon_key": "tools",
            "object_name": "mobaRailButton",
        },
        {
            "role": "macros",
            "label": "Macros",
            "icon_key": "multiexec",
            "rail_icon_key": "macros",
            "object_name": "mobaRailButton",
        },
        {
            "role": "sftp",
            "label": "SFTP",
            "icon_key": "packages",
            "rail_icon_key": "sftp",
            "object_name": "mobaRailButton",
        },
    ]
    assert moba["expected_moba_rail_item_geometry"] == [
        {"role": "collapse", "static_icon_y": 8, "static_label_y": 0},
        {"role": "sessions", "static_icon_y": 42, "static_label_y": 68},
        {"role": "favorites", "static_icon_y": 126, "static_label_y": 0},
        {"role": "tools", "static_icon_y": 160, "static_label_y": 186},
        {"role": "macros", "static_icon_y": 244, "static_label_y": 270},
        {"role": "sftp", "static_icon_y": 328, "static_label_y": 354},
    ]
    assert [item["key"] for item in moba["expected_moba_sftp_toolbar_groups"]] == [
        "parent-folder",
        "download",
        "upload",
        "connect",
        "new-folder",
        "new-file",
        "delete",
        "ascii-mode",
        "split-view",
        "tools",
        "terminal",
    ]
    assert moba["expected_moba_sftp_separator_after_keys"] == [
        "parent-folder",
        "upload",
        "delete",
        "tools",
    ]
    assert moba["expected_moba_sftp_toolbar_action_route"] == {
        "key": "moba-sftp-toolbar-action-route",
        "route_role": "sftp-toolbar-actions-to-file-transfer-workflows",
        "toolbar_object": "mobaSftpToolbar",
        "action_object": "mobaSftpAction",
        "target_browser_object": "mobaSftpBrowser",
        "target_path_object": "mobaSftpPath",
        "target_table_object": "mobaSftpFileTable",
        "queue_object": "mobaSftpTransferQueue",
        "action_keys": [
            "parent-folder",
            "download",
            "upload",
            "connect",
            "new-folder",
            "new-file",
            "delete",
            "ascii-mode",
            "split-view",
            "tools",
            "terminal",
        ],
        "action_labels": [
            "Parent folder",
            "Download",
            "Upload",
            "Reconnect",
            "New folder",
            "New file",
            "Delete",
            "ASCII",
            "Split",
            "Tools",
            "Terminal",
        ],
        "action_icon_keys": [
            "parent-folder",
            "download",
            "upload",
            "connect",
            "new-folder",
            "new-file",
            "delete",
            "ascii-mode",
            "split-view",
            "tools",
            "terminal",
        ],
        "action_group_keys": [
            "navigation",
            "transfer",
            "transfer",
            "manage",
            "manage",
            "manage",
            "manage",
            "mode",
            "mode",
            "mode",
            "terminal",
        ],
        "action_tooltips": [
            "Go to parent directory",
            "Download selected remote item",
            "Upload local item",
            "Reconnect SFTP browser",
            "Create remote folder",
            "Create remote file",
            "Delete selected remote item",
            "Toggle text transfer mode",
            "Toggle split file view",
            "Show SFTP tools",
            "Open terminal at remote folder",
        ],
        "action_handlers": ["show_moba_sftp_toolbar_action"] * 11,
        "action_statuses": [
            "navigated",
            "queued",
            "queued",
            "reconnected",
            "prepared",
            "prepared",
            "prepared",
            "toggled",
            "toggled",
            "opened",
            "opened",
        ],
        "signal": "clicked",
        "route_key_property": "mobaSftpToolbarRouteKey",
        "action_key_property": "mobaSftpToolbarRouteActionKey",
        "action_label_property": "mobaSftpToolbarRouteActionLabel",
        "action_object_property": "mobaSftpToolbarRouteActionObject",
        "icon_key_property": "mobaSftpToolbarRouteIconKey",
        "group_key_property": "mobaSftpToolbarRouteGroupKey",
        "tooltip_property": "mobaSftpToolbarRouteTooltip",
        "signal_property": "mobaSftpToolbarRouteSignal",
        "handler_property": "mobaSftpToolbarRouteHandler",
        "action_keys_property": "mobaSftpToolbarRouteActionKeys",
        "action_groups_property": "mobaSftpToolbarRouteActionGroups",
        "captured_property": "mobaSftpToolbarRouteCaptured",
        "captured_action_property": "mobaSftpToolbarRouteCapturedAction",
        "captured_status_property": "mobaSftpToolbarRouteCapturedStatus",
        "live_triggered_property": "mobaSftpToolbarRouteLiveTriggered",
        "live_action_property": "mobaSftpToolbarRouteLiveAction",
        "live_status_property": "mobaSftpToolbarRouteLiveStatus",
        "render_source": "gui-design-moba-sftp-toolbar-route",
    }
    assert moba["expected_moba_sftp_toolbar_action_geometry"] == [
            {
                "key": "parent-folder",
                "button_x": 3,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 7,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": True,
            "separator_x": 34,
        },
            {
                "key": "download",
                "button_x": 34,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 38,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "upload",
                "button_x": 58,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 62,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": True,
            "separator_x": 89,
        },
            {
                "key": "connect",
                "button_x": 89,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 93,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "new-folder",
                "button_x": 113,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 117,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "new-file",
                "button_x": 137,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 141,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "delete",
                "button_x": 161,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 165,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": True,
            "separator_x": 192,
        },
            {
                "key": "ascii-mode",
                "button_x": 192,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 196,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "split-view",
                "button_x": 216,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 220,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
            {
                "key": "tools",
                "button_x": 240,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 244,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": True,
            "separator_x": 271,
        },
            {
                "key": "terminal",
                "button_x": 271,
                "button_y": 3,
                "button_size": 24,
                "icon_x": 275,
                "icon_y": 7,
            "icon_size": 16,
            "separator_after": False,
            "separator_x": 0,
        },
    ]
    assert "sftp-file-row-icons" in moba["contract_checks"]
    assert moba["expected_moba_sftp_file_row_icons"] == [
        {
            "kind": "parent-dir",
            "icon_key": "folder-up",
            "row_kind": "parent-dir",
            "static_size": 14,
            "render_source": "generated-pixmap",
        },
        {
            "kind": "dir",
            "icon_key": "folder",
            "row_kind": "dir",
            "static_size": 14,
            "render_source": "generated-pixmap",
        },
        {
            "kind": "file",
            "icon_key": "file",
            "row_kind": "file",
            "static_size": 14,
            "render_source": "generated-pixmap",
        },
    ]
    assert moba["expected_moba_sftp_routed_file_rows"] == {
        "key": "sftp-follow-folder-file-rows",
        "route_role": "follow-folder-visible-file-list",
        "follow_route_key": "sftp-follow-terminal-folder-route",
        "target_table_object": "mobaSftpFileTable",
        "row_contract_property": "mobaSftpRowContractKey",
        "row_route_property": "mobaSftpRowFollowRouteKey",
        "row_path_property": "mobaSftpRowSourcePath",
        "row_index_property": "mobaSftpRowIndex",
        "row_selected_property": "mobaSftpRowSelectedByRoute",
        "parent_row_name": "..",
        "selected_row_kind": "parent-dir",
        "render_source": "state-file-entries",
    }
    assert "network" in moba["expected_moba_monitoring_metric_keys"]
    assert moba["expected_moba_remote_monitoring_dock_chrome"] == {
        "title_control_key": "remote-monitoring",
        "follow_control_key": "follow-terminal-folder",
        "telemetry_surface": "bottom-telemetry-bar",
        "visible_metric_keys": [],
        "refresh_seconds": 5,
        "compact": True,
        "static_height": 78,
        "divider_offset": 10,
        "divider_left_inset": 18,
        "divider_right_inset": 194,
        "content_left": 42,
        "icon_center_x": 104,
        "metric_row_gap": 21,
        "live_controls_width": 260,
    }
    assert moba["expected_moba_monitoring_telemetry_route"] == {
        "key": "remote-monitoring-to-bottom-telemetry",
        "route_role": "compact-dock-bottom-telemetry",
        "source_panel_object": "mobaRemoteMonitoring",
        "source_control_key": "remote-monitoring",
        "source_metric_keys": ["cpu", "memory", "disk", "network", "load", "processes"],
        "visible_dock_metric_keys": [],
        "telemetry_surface": "bottom-telemetry-bar",
        "target_bar_object": "mobaTelemetryBar",
        "target_cell_object": "mobaTelemetryCell",
        "target_identity_cell_key": "target",
        "target_metric_cell_keys": [
            "cpu",
            "memory",
            "disk",
            "net-up",
            "net-down",
            "connections",
            "processes",
        ],
        "render_source": "generated-pixmap",
    }
    assert moba["expected_moba_remote_monitoring_control_route"] == {
        "key": "moba-remote-monitoring-control-route",
        "route_role": "remote-monitoring-control-to-telemetry-refresh",
        "source_panel_object": "mobaRemoteMonitoring",
        "source_control_object": "mobaMonitoringControl",
        "source_control_key": "remote-monitoring",
        "source_control_label": "Remote monitoring",
        "source_control_type": "toggle",
        "expected_checked": True,
        "command_property": "mobaMonitoringCommand",
        "refresh_seconds_property": "mobaMonitoringRefreshSeconds",
        "checked_property": "mobaMonitoringControlChecked",
        "telemetry_route_key": "remote-monitoring-to-bottom-telemetry",
        "telemetry_surface": "bottom-telemetry-bar",
        "target_bar_object": "mobaTelemetryBar",
        "target_metric_cell_keys": [
            "cpu",
            "memory",
            "disk",
            "net-up",
            "net-down",
            "connections",
            "processes",
        ],
        "captured_property": "mobaRemoteMonitoringControlCaptured",
        "captured_checked_property": "mobaRemoteMonitoringControlCapturedChecked",
        "captured_command_property": "mobaRemoteMonitoringControlCapturedCommand",
        "captured_refresh_seconds_property": "mobaRemoteMonitoringControlCapturedRefreshSeconds",
        "signal": "toggled",
        "handler": "handle_moba_remote_monitoring_toggled",
        "signal_property": "mobaRemoteMonitoringControlSignal",
        "handler_property": "mobaRemoteMonitoringControlHandler",
        "live_checked_property": "mobaRemoteMonitoringControlLiveChecked",
        "render_source": "state-model",
    }
    assert moba["expected_moba_follow_terminal_folder_control_route"] == {
        "key": "moba-follow-terminal-folder-control-route",
        "route_role": "follow-terminal-folder-control-to-sftp-browser-sync",
        "source_panel_object": "mobaRemoteMonitoring",
        "source_control_object": "mobaFollowTerminalFolder",
        "source_control_key": "follow-terminal-folder",
        "source_control_label": "Follow terminal folder",
        "source_control_type": "checkbox",
        "expected_checked": True,
        "source_path_property": "mobaMonitoringFollowPath",
        "source_plan_property": "mobaMonitoringFollowPlan",
        "source_enabled_property": "mobaMonitoringFollowEnabled",
        "target_browser_object": "mobaSftpBrowser",
        "target_path_object": "mobaSftpPath",
        "target_table_object": "mobaSftpFileTable",
        "target_path_property": "mobaSftpFollowRoutePath",
        "target_plan_property": "mobaSftpFollowRoutePlan",
        "target_enabled_property": "mobaSftpFollowRouteEnabled",
        "captured_property": "mobaFollowTerminalFolderControlCaptured",
        "captured_checked_property": "mobaFollowTerminalFolderControlCapturedChecked",
        "captured_path_property": "mobaFollowTerminalFolderControlCapturedPath",
        "captured_plan_property": "mobaFollowTerminalFolderControlCapturedPlan",
        "signal": "toggled",
        "handler": "handle_moba_follow_terminal_folder_toggled",
        "signal_property": "mobaFollowTerminalFolderControlSignal",
        "handler_property": "mobaFollowTerminalFolderControlHandler",
        "live_checked_property": "mobaFollowTerminalFolderControlLiveChecked",
        "live_path_property": "mobaFollowTerminalFolderControlLivePath",
        "live_plan_property": "mobaFollowTerminalFolderControlLivePlan",
        "render_source": "state-model",
    }
    assert moba["expected_moba_sftp_follow_folder_route"] == {
        "key": "sftp-follow-terminal-folder-route",
        "route_role": "terminal-cwd-to-sftp-browser",
        "source_control_key": "follow-terminal-folder",
        "source_control_object": "mobaFollowTerminalFolder",
        "source_path_property": "mobaMonitoringFollowPath",
        "source_plan_property": "mobaMonitoringFollowPlan",
        "source_enabled_property": "mobaMonitoringFollowEnabled",
        "target_browser_object": "mobaSftpBrowser",
        "target_path_object": "mobaSftpPath",
        "target_table_object": "mobaSftpFileTable",
        "target_path_property": "mobaSftpFollowRoutePath",
        "target_plan_property": "mobaSftpFollowRoutePlan",
        "target_enabled_property": "mobaSftpFollowRouteEnabled",
        "render_source": "state-model",
    }
    assert "sftp-terminal-folder-route" in moba["contract_checks"]
    assert moba["expected_moba_sftp_terminal_folder_route"] == {
        "key": "moba-sftp-terminal-folder-route",
        "route_role": "terminal-cwd-follow-checkbox-to-sftp-path-and-rows",
        "terminal_area_object": "mobaTerminalArea",
        "terminal_output_object": "terminalOutput",
        "source_control_object": "mobaFollowTerminalFolder",
        "target_browser_object": "mobaSftpBrowser",
        "target_path_object": "mobaSftpPath",
        "target_table_object": "mobaSftpFileTable",
        "parent_row_label": "..",
        "selected_row_kind": "parent-dir",
        "remote_path": "/var/log",
        "list_command": "ls -la /var/log",
        "follow_enabled": True,
        "path_property": "mobaSftpTerminalFolderRoutePath",
        "plan_property": "mobaSftpTerminalFolderRoutePlan",
        "enabled_property": "mobaSftpTerminalFolderRouteEnabled",
        "row_route_property": "mobaSftpTerminalFolderRouteKey",
        "render_source": "connected-session-state",
    }
    assert moba["expected_moba_monitoring_controls"] == [
        {
            "key": "remote-monitoring",
            "icon_key": "monitor",
            "label": "Remote monitoring",
            "control_type": "toggle",
            "checked": True,
        },
        {
            "key": "follow-terminal-folder",
            "icon_key": "follow-folder",
            "label": "Follow terminal folder",
            "control_type": "checkbox",
            "checked": True,
        },
    ]
    assert moba["expected_moba_monitoring_control_geometry"] == [
        {
            "key": "remote-monitoring",
            "anchor_x": 104,
            "static_y": 1,
            "icon_x": 104,
            "icon_size": 20,
            "label_x": 132,
            "label_y_offset": 2,
            "label_font_size": 12,
            "label_bold": True,
            "check_size": 0,
            "check_y_offset": 0,
            "checkmark_points": [],
            "row_height": 22,
            "live_width": 146,
        },
            {
                "key": "follow-terminal-folder",
                "anchor_x": 42,
                "static_y": 50,
            "icon_x": 60,
            "icon_size": 16,
            "label_x": 80,
            "label_y_offset": 3,
            "label_font_size": 11,
            "label_bold": False,
            "check_size": 10,
            "check_y_offset": 3,
            "checkmark_points": [[2, 5], [5, 9], [10, 1]],
            "row_height": 19,
            "live_width": 208,
        },
    ]
    assert "sftp-ready" in moba["expected_moba_status_keys"]
    assert moba["expected_moba_status_chrome"] == {
        "notice": "REMOTE OPS WORKSPACE",
        "product_note": "open-protocol operator shell",
        "right_marker": "[]",
        "static_height": 18,
        "notice_x": 6,
        "notice_y": 4,
        "product_note_x": 142,
        "product_note_y": 4,
        "text_font_size": 10,
        "segment_start_right_offset": 480,
        "marker_right_inset": 4,
        "marker_y": 4,
        "marker_width": 9,
        "marker_height": 10,
    }
    assert moba["expected_moba_bottom_edge_controls"] == [
        {"key": "tab-left", "icon_key": "arrow-left", "label": "Previous tab", "static_x": 1204},
        {"key": "tab-right", "icon_key": "arrow-right", "label": "Next tab", "static_x": 1224},
        {"key": "close-active", "icon_key": "close", "label": "Close active tab", "static_x": 1244},
    ]
    assert moba["expected_moba_rail_labels"] == {
        "sessions": "Sessions",
        "tools": "Tools",
        "macros": "Macros",
        "sftp": "SFTP",
    }
    assert [item["key"] for item in moba["expected_moba_top_menu"]] == checker.EXPECTED_MOBA_TOP_MENU_KEYS
    assert [item["label"] for item in moba["expected_moba_top_menu"]] == checker.EXPECTED_MOBA_TOP_MENU_LABELS
    assert moba["expected_moba_top_menu_geometry"] == [
        geometry.to_dict() for geometry in checker.EXPECTED_MOBA_TOP_MENU_GEOMETRY
    ]
    assert moba["expected_moba_ribbon_action_geometry"] == [
        geometry.to_dict() for geometry in checker.EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY
    ]
    assert moba["expected_moba_ribbon_edge_action_route"] == {
        "key": "moba-ribbon-edge-action-route",
        "route_role": "far-right-ribbon-edge-actions-to-workflow-controls",
        "toolbar_object": "mainToolbar",
        "spacer_object": "mobaToolbarSpacer",
        "xserver_action_key": "xserver",
        "xserver_action_label": "X server",
        "xserver_action_object": "mobaXServerAction",
        "xserver_icon_key": "xserver",
        "xserver_handler": "show_moba_x_server_status",
        "xserver_dialog_title": "X server",
        "xserver_dialog_detail": "X server workflow",
        "exit_action_key": "exit",
        "exit_action_label": "Exit",
        "exit_action_object": "mobaExitAction",
        "exit_icon_key": "exit",
        "exit_handler": "close",
        "route_key_property": "mobaRibbonEdgeRouteKey",
        "action_key_property": "mobaRibbonEdgeRouteActionKey",
        "action_label_property": "mobaRibbonEdgeRouteActionLabel",
        "action_object_property": "mobaRibbonEdgeRouteActionObject",
        "icon_key_property": "mobaRibbonEdgeRouteIconKey",
        "handler_property": "mobaRibbonEdgeRouteHandler",
        "action_keys_property": "mobaRibbonEdgeRouteActionKeys",
        "render_source": "gui-design-moba-ribbon-edge-route",
    }
    assert moba["expected_moba_titlebar_chrome"] == {
        "icon_key": "moba-window",
        "static_height": 22,
        "icon_left": 5,
        "icon_size": 12,
        "title_left": 24,
        "control_keys": ["minimize", "maximize", "close"],
        "control_width": 24,
    }
    assert moba["expected_moba_top_stack_geometry"] == {
        "titlebar_height": 22,
        "menu_y": 22,
        "menu_height": 22,
        "ribbon_y": 44,
        "ribbon_height": 54,
        "quick_connect_y": 98,
        "quick_connect_height": 24,
        "left_dock_y": 122,
        "tab_y": 98,
        "tab_height": 24,
        "terminal_content_y": 122,
        "status_height": 18,
        "side_width": 394,
        "rail_width": 28,
    }
    assert moba["expected_moba_connected_dock_frame"] == {
        "side_width": 394,
        "rail_width": 28,
        "dock_x": 28,
        "dock_y": 122,
        "dock_width": 366,
        "dock_height": 620,
        "workspace_x": 394,
        "quick_connect_y": 98,
        "quick_connect_height": 24,
        "status_y": 742,
    }
    assert moba["expected_moba_connected_session_route"] == {
        "key": "moba-active-connected-session-route",
        "route_role": "active-tab-to-connected-workspace",
        "active_tab_key": "active-session",
        "active_tab_label": "edge-prod.example.invalid (operator)",
        "reference_tab_label": "7. edge-prod.example.invalid (operator)",
        "active_tab_object": "sessionTabs",
        "connected_panel_object": "mobaConnectedSession",
        "left_dock_object": "mobaConnectedLeftDock",
        "sftp_browser_object": "mobaSftpBrowser",
        "sftp_path_object": "mobaSftpPath",
        "sftp_table_object": "mobaSftpFileTable",
        "ssh_banner_object": "mobaSshBanner",
        "terminal_area_object": "mobaTerminalArea",
        "terminal_output_object": "terminalOutput",
        "telemetry_bar_object": "mobaTelemetryBar",
        "telemetry_identity_cell_key": "target",
        "target": "edge-prod.example.invalid:22",
        "remote_path": "/var/log",
        "tab_label_property": "mobaConnectedRouteActiveTabLabel",
        "target_property": "mobaConnectedRouteTarget",
        "remote_path_property": "mobaConnectedRouteRemotePath",
        "render_source": "connected-session-state",
    }
    assert moba["expected_moba_connected_session_action_route"] == {
        "key": "moba-connected-session-actions-route",
        "route_role": "active-connected-tab-context-session-actions",
        "profile_name": "edge-prod",
        "target": "edge-prod.example.invalid:22",
        "active_tab_key": "active-session",
        "active_tab_label": "edge-prod.example.invalid (operator)",
        "reference_tab_label": "7. edge-prod.example.invalid (operator)",
        "tabs_object": "sessionTabs",
        "tab_bar_object": "sessionTabBar",
        "reference_tab_role": "terminal",
        "menu_object": "mobaConnectedSessionTabContextMenu",
        "action_object": "mobaConnectedSessionTabContextAction",
        "expected_action_keys": [
            "new-local-terminal",
            "split-horizontal",
            "split-vertical",
            "duplicate-tab",
            "open-sftp-same-parameters",
            "close-tab",
            "close-other-tabs",
            "recover-previous-sessions",
        ],
        "expected_action_labels": [
            "New local terminal",
            "Split horizontal",
            "Split vertical",
            "Duplicate tab",
            "Open SFTP with same parameters",
            "Close tab",
            "Close other tabs",
            "Recover previous sessions",
        ],
        "expected_action_count": 8,
        "always_enabled_action_keys": [
            "new-local-terminal",
            "split-horizontal",
            "split-vertical",
            "duplicate-tab",
            "open-sftp-same-parameters",
            "close-tab",
            "recover-previous-sessions",
        ],
        "conditional_enabled_action_keys": ["close-other-tabs"],
        "action_key_property": "sessionTabContextActionKey",
        "action_label_property": "sessionTabContextActionLabel",
        "action_enabled_property": "sessionTabContextActionEnabled",
        "captured_property": "mobaConnectedSessionActionCaptured",
        "captured_tab_property": "mobaConnectedSessionActionCapturedTab",
        "captured_action_keys_property": "mobaConnectedSessionActionKeys",
        "captured_action_labels_property": "mobaConnectedSessionActionLabels",
        "captured_action_count_property": "mobaConnectedSessionActionCount",
        "captured_enabled_keys_property": "mobaConnectedSessionActionEnabledKeys",
        "captured_disabled_keys_property": "mobaConnectedSessionActionDisabledKeys",
        "render_source": "connected-session-state",
    }
    assert moba["expected_moba_connected_session_identity_route"] == {
        "key": "moba-connected-session-identity-route",
        "route_role": "title-tab-banner-terminal-telemetry-identity",
        "window_title": "edge-prod.example.invalid (operator)",
        "active_tab_label": "edge-prod.example.invalid (operator)",
        "reference_tab_label": "7. edge-prod.example.invalid (operator)",
        "banner_target": "edge-prod.example.invalid",
        "web_console_line": "",
        "terminal_prompt": "",
        "telemetry_target": "edge-prod.example.invalid:22",
        "target_endpoint": "edge-prod.example.invalid:22",
        "remote_path": "/var/log",
        "window_title_property": "mobaConnectedIdentityWindowTitle",
        "banner_target_property": "mobaConnectedIdentityBannerTarget",
        "terminal_prompt_property": "mobaConnectedIdentityTerminalPrompt",
        "telemetry_target_property": "mobaConnectedIdentityTelemetryTarget",
        "render_source": "connected-session-state",
    }
    assert moba["expected_moba_quick_connect_chrome"] == {
        "placeholder": "Quick connect...",
        "dropdown_marker": "v",
        "static_height": 24,
        "marker_width": 24,
        "input_left": 0,
        "connected_idle_query": "",
        "connected_suggestions_visible": False,
    }
    assert moba["expected_moba_connected_quick_connect_idle"] == {
        "query": "",
        "suggestions_visible": False,
    }
    assert moba["expected_moba_quick_connect_suggestion_chrome"] == {
        "preview_query": "edge-prod.example.invalid",
        "expected_kinds": ["profile", "direct"],
        "max_visible_rows": 4,
        "row_height": 22,
        "static_width": 394,
        "detail_separator": "    ",
    }
    assert moba["expected_moba_home_welcome_chrome"] == {
        "title": "Remote Ops Workspace",
        "subtitle": "Moba-style SSH client, SFTP browser and monitoring tools",
        "icon_key": "session",
        "primary_action_icon_key": "session",
        "secondary_action_icon_key": "tunneling",
        "search_width": 405,
        "action_spacing": 62,
        "recent_title": "Recent sessions",
        "surface_width": 640,
    }
    assert moba["expected_moba_home_welcome_geometry"] == {
        "center_side_margin": 80,
        "hero_min_y": 115,
        "hero_height": 330,
        "logo_size": 46,
        "logo_inner_padding": 7,
        "logo_icon_size": 32,
        "logo_cluster_width": 360,
        "title_gap": 28,
        "title_y_offset": 9,
        "title_font_size": 28,
        "subtitle_y_offset": 57,
        "subtitle_font_size": 12,
        "button_y_offset": 94,
        "primary_width": 206,
        "secondary_width": 220,
        "action_gap": 62,
        "button_height": 28,
        "button_icon_x": 13,
        "button_icon_y": 6,
        "button_icon_size": 16,
        "button_label_x": 40,
        "button_label_y": 8,
        "button_font_size": 11,
        "search_y_gap": 45,
        "search_height": 25,
        "search_text_x": 10,
        "search_text_y": 6,
        "search_font_size": 12,
        "recent_y_gap": 52,
        "recent_title_font_size": 12,
        "recent_item_y_offset": 28,
        "recent_item_step": 22,
        "recent_column_padding": 12,
        "footer_y_offset": 120,
        "footer_font_size": 10,
        "live_max_extra_width": 120,
        "live_layout_spacing": 13,
        "live_title_row_spacing": 18,
        "live_title_column_spacing": 3,
        "live_logo_box_width": 64,
        "live_logo_box_height": 56,
        "live_logo_pixmap_size": 56,
        "live_recent_title_top_margin": 9,
        "live_recent_column_spacing": 44,
        "live_recent_row_spacing": 5,
        "live_footer_top_margin": 12,
        "render_source": "generated-pixmap",
    }
    assert moba["expected_workflow_card_titles"] == []
    assert moba["expected_moba_sftp_browser_chrome"] == {
        "path_placeholder": "/",
        "dropdown_marker": "v",
        "parent_row_label": "..",
        "parent_row_kind": "parent-dir",
        "selected_row_kind": "parent-dir",
        "columns": [
            {"key": "name", "label": "Name", "static_x": 38, "static_width": 182},
            {"key": "size", "label": "Size (KB)", "static_x": 188, "static_width": 78},
            {"key": "modified", "label": "Last modified", "static_x": 266, "static_width": 94},
        ],
    }
    assert moba["expected_moba_sftp_browser_geometry"] == {
        "path_text_x": 14,
        "path_text_y": 6,
        "path_font_size": 11,
        "dropdown_right_offset": 18,
        "dropdown_y": 6,
        "dropdown_font_size": 10,
        "header_label_y": 7,
        "header_font_size": 10,
        "row_top_offset": 0,
        "row_icon_x": 14,
        "row_icon_y_offset": -1,
        "row_name_x": 38,
        "row_size_x": 202,
        "row_modified_x": 278,
        "row_text_y_offset": 0,
        "row_text_font_size": 10,
        "row_modified_font_size": 9,
    }
    assert moba["expected_moba_sftp_dock_layout"] == {
        "inner_margin": 0,
        "toolbar_height": 30,
        "toolbar_icon_size": 16,
        "toolbar_icon_step": 24,
        "toolbar_separator_width": 7,
        "path_height": 22,
        "table_header_height": 24,
        "file_row_height": 21,
        "static_max_rows": 9,
        "monitoring_height": 78,
        "monitoring_divider_offset": 10,
    }
    assert [line["key"] for line in moba["expected_moba_terminal_transcript"]] == (
        checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS
    )
    assert moba["expected_moba_terminal_transcript"] == []
    assert moba["expected_moba_terminal_transcript_row_geometry"] == []
    assert [cell["key"] for cell in moba["expected_moba_telemetry_cells"]] == (
        checker.EXPECTED_MOBA_TELEMETRY_CELL_KEYS
    )
    assert [cell["width"] for cell in moba["expected_moba_telemetry_cells"]] == (
        checker.EXPECTED_MOBA_TELEMETRY_CELL_WIDTHS
    )
    assert [cell["icon_size"] for cell in moba["expected_moba_telemetry_cells"]] == [12] * 8
    assert moba["expected_moba_telemetry_cells"][1]["icon_accent"] == "#f4c430"
    assert moba["expected_moba_telemetry_cells"][1]["display_text"] == "Unavailable"
    assert moba["expected_moba_telemetry_cells"][6]["display_text"] == "Connections: unavailable"
    assert moba["expected_moba_telemetry_cell_geometry"] == [
        {
            "key": "target",
            "static_x": 10,
            "static_y": 1,
            "width": 165,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "cpu",
            "static_x": 175,
            "static_y": 1,
            "width": 60,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "memory",
            "static_x": 235,
            "static_y": 1,
            "width": 125,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "disk",
            "static_x": 360,
            "static_y": 1,
            "width": 124,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "net-up",
            "static_x": 484,
            "static_y": 1,
            "width": 88,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "net-down",
            "static_x": 572,
            "static_y": 1,
            "width": 88,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "connections",
            "static_x": 660,
            "static_y": 1,
            "width": 145,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
        {
            "key": "processes",
            "static_x": 805,
            "static_y": 1,
            "width": 77,
            "height": 22,
            "icon_x": 5,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 22,
            "label_y": 6,
            "label_font_size": 9,
            "separator_top": 2,
            "separator_bottom": 22,
        },
    ]
    assert moba["expected_moba_tab_chrome_keys"] == ["active-session", "home", "new-session"]
    assert moba["expected_moba_static_tab_chrome_keys"] == [
        "active-session",
        "home",
        "inactive-session",
        "new-session",
    ]
    assert moba["expected_moba_tab_chrome_geometry"] == [
        {
            "key": "home",
            "width": 42,
            "height": 22,
            "corner_radius": 2,
            "icon_x": 8,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 26,
            "label_y": 7,
            "close_right_offset": 16,
            "close_y": 6,
            "plus_x": 11,
            "plus_y": 3,
            "gap_after": 4,
        },
        {
            "key": "inactive-session",
            "width": 226,
            "height": 22,
            "corner_radius": 2,
            "icon_x": 8,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 26,
            "label_y": 7,
            "close_right_offset": 16,
            "close_y": 6,
            "plus_x": 11,
            "plus_y": 3,
            "gap_after": 4,
        },
        {
            "key": "active-session",
            "width": 258,
            "height": 22,
            "corner_radius": 2,
            "icon_x": 8,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 26,
            "label_y": 7,
            "close_right_offset": 16,
            "close_y": 6,
            "plus_x": 11,
            "plus_y": 3,
            "gap_after": 4,
        },
        {
            "key": "new-session",
            "width": 32,
            "height": 22,
            "corner_radius": 2,
            "icon_x": 8,
            "icon_y": 5,
            "icon_size": 12,
            "label_x": 26,
            "label_y": 7,
            "close_right_offset": 16,
            "close_y": 6,
            "plus_x": 11,
            "plus_y": 3,
            "gap_after": 4,
        },
    ]
    assert moba["expected_moba_right_utility_keys"] == []
    assert "right-utility-rail-chrome" not in moba["contract_checks"]
    assert "right-utility-rail-geometry" not in moba["contract_checks"]
    assert "right-utility-action-route" not in moba["contract_checks"]
    assert moba["expected_moba_right_utility_rail_chrome"] == {}
    assert moba["expected_moba_right_utility_actions"] == []
    assert moba["expected_moba_right_utility_action_route"] == {}
    assert moba["expected_moba_session_edge_actions"] == [
        {
            "key": "attachment",
            "icon_key": "clip",
            "label": "Session attachment",
            "static_y": 112,
            "relative_y": 4,
            "static_size": 16,
            "live_icon_size": 16,
            "button_size": 22,
            "render_source": "generated-pixmap",
        },
        {
            "key": "settings",
            "icon_key": "gear",
            "label": "Session settings",
            "static_y": 130,
            "relative_y": 22,
            "static_size": 16,
            "live_icon_size": 16,
            "button_size": 22,
            "render_source": "generated-pixmap",
        },
    ]
    assert moba["expected_moba_session_edge_action_route"] == {
        "key": "moba-session-edge-action-route",
        "route_role": "session-edge-shortcuts-to-active-tab-workflows",
        "controls_object": "mobaSessionEdgeControls",
        "action_object": "mobaSessionEdgeAction",
        "placement": "tab-strip-overlay",
        "action_keys": ["attachment", "settings"],
        "action_labels": ["Session attachment", "Session settings"],
        "action_icon_keys": ["clip", "gear"],
        "action_handlers": [
            "show_moba_session_attachment",
            "show_moba_session_settings",
        ],
        "route_key_property": "mobaSessionEdgeRouteKey",
        "action_key_property": "mobaSessionEdgeRouteActionKey",
        "action_label_property": "mobaSessionEdgeRouteActionLabel",
        "action_object_property": "mobaSessionEdgeRouteActionObject",
        "icon_key_property": "mobaSessionEdgeRouteIconKey",
        "handler_property": "mobaSessionEdgeRouteHandler",
        "action_keys_property": "mobaSessionEdgeRouteActionKeys",
        "render_source": "gui-design-moba-session-edge-route",
    }
    assert moba["expected_moba_ssh_banner_chrome"] == {}
    assert moba["expected_moba_ssh_banner_row_geometry"] == []
    assert moba["expected_moba_ssh_banner_capability_card"] == {}
    assert "ssh-banner-capability-card" not in moba["contract_checks"]
    assert "ssh-banner-row-geometry" not in moba["contract_checks"]
    assert "workspace-surface" not in moba["contract_checks"]

    securecrt = summaries["securecrt"]
    assert "productWorkspaceSurface" in securecrt["required_widgets"]
    assert securecrt["required_widgets"]["secureCrtSessionStatusStrip"] == "SecureCRT session status strip"
    assert (
        securecrt["required_widgets"]["secureCrtSessionManagerChrome"]
        == "SecureCRT Session Manager filter/action chrome"
    )
    assert "designSelect" in securecrt["present_widgets"]
    assert securecrt["reference_profile"] == "edge-prod"
    assert securecrt["expected_reference_tab_label"] == "edge-prod (SSH2)"
    assert "edge-prod (SSH2)" in securecrt["expected_tree_labels"]
    assert "workspace-surface" in securecrt["contract_checks"]
    assert "reference-state" in securecrt["contract_checks"]
    assert "securecrt-top-chrome" in securecrt["contract_checks"]
    assert "securecrt-session-manager-chrome" in securecrt["contract_checks"]
    assert "securecrt-session-manager-geometry" in securecrt["contract_checks"]
    assert "securecrt-session-manager-route" in securecrt["contract_checks"]
    assert "securecrt-session-manager-filter-route" in securecrt["contract_checks"]
    assert "securecrt-sftp-tab-route" in securecrt["contract_checks"]
    assert "securecrt-sftp-browser-route" in securecrt["contract_checks"]
    assert "securecrt-sftp-browser-live-action-route" in securecrt["contract_checks"]
    assert "securecrt-tree-icons" in securecrt["contract_checks"]
    assert "securecrt-session-status-strip" in securecrt["contract_checks"]
    assert "securecrt-session-status-geometry" in securecrt["contract_checks"]
    assert "securecrt-command-window" in securecrt["contract_checks"]
    assert "securecrt-command-window-geometry" in securecrt["contract_checks"]
    assert "securecrt-command-window-send-route" in securecrt["contract_checks"]
    assert "securecrt-command-window-live-send-route" in securecrt["contract_checks"]
    assert "product-identity-route" in securecrt["contract_checks"]
    assert "live-topology" in securecrt["contract_checks"]
    assert "active-tab: edge-prod (SSH2)" in securecrt["expected_reference_state_texts"]
    assert securecrt["expected_reference_status_segments"] == ["SSH2", "Session Manager", "2 active tabs"]
    assert securecrt["expected_product_identity_route"]["key"] == "securecrt-product-identity-route"
    assert securecrt["expected_product_identity_route"]["active_tab_label"] == "edge-prod (SSH2)"
    assert securecrt["expected_product_identity_route"]["selected_tree_label"] == "edge-prod (SSH2)"
    assert securecrt["expected_product_identity_route"]["status_segments"] == [
        "SSH2",
        "Session Manager",
        "2 active tabs",
    ]
    assert [item["label"] for item in securecrt["expected_securecrt_top_chrome"]["menu_items"]] == [
        "File",
        "Edit",
        "View",
        "Options",
        "Transfer",
        "Script",
        "Tools",
        "Window",
        "Help",
    ]
    assert securecrt["expected_securecrt_top_chrome"]["toolbar_height"] == 54
    assert securecrt["expected_securecrt_top_chrome"]["toolbar_actions"][6] == {
        "key": "files",
        "icon_key": "sftp",
        "label": "SFTP",
        "static_x": 502,
        "static_width": 54,
    }
    assert securecrt["expected_securecrt_command_window"] == {
        "key": "send-to-all-sessions",
        "title": "Command Window",
        "target_scope": "All Sessions",
        "command": "$ row doctor --json",
        "send_label": "Send",
        "status": "ready",
        "static_header_height": 25,
        "static_control_y": 31,
        "static_target_width": 112,
        "static_input_x": 132,
        "static_input_text_x": 10,
        "static_input_text_y": 7,
        "static_send_width": 58,
        "static_send_right_margin": 10,
        "live_target_min_width": 112,
        "live_send_min_width": 48,
    }
    assert securecrt["expected_securecrt_command_window_send_route"] == {
        "key": "securecrt-command-window-send-route",
        "route_role": "command-input-to-active-sessions",
        "source_window_object": "secureCrtCommandWindow",
        "target_scope_object": "secureCrtCommandTarget",
        "command_input_object": "secureCrtCommandInput",
        "send_control_object": "secureCrtCommandSend",
        "status_object": "secureCrtCommandStatus",
        "command_property": "secureCrtCommandRouteCommand",
        "target_scope_property": "secureCrtCommandRouteTargetScope",
        "send_label_property": "secureCrtCommandRouteSendLabel",
        "status_property": "secureCrtCommandRouteStatus",
        "captured_property": "secureCrtCommandRouteCaptured",
        "captured_command_property": "secureCrtCommandRouteCapturedCommand",
        "captured_target_scope_property": "secureCrtCommandRouteCapturedTargetScope",
        "captured_status_property": "secureCrtCommandRouteCapturedStatus",
        "signal": "clicked",
        "secondary_signal": "returnPressed",
        "handler": "handle_securecrt_command_window_send",
        "signal_property": "secureCrtCommandRouteSignal",
        "secondary_signal_property": "secureCrtCommandRouteSecondarySignal",
        "handler_property": "secureCrtCommandRouteHandler",
        "live_submitted_property": "secureCrtCommandRouteLiveSubmitted",
        "live_command_property": "secureCrtCommandRouteLiveCommand",
        "live_target_scope_property": "secureCrtCommandRouteLiveTargetScope",
        "live_status_property": "secureCrtCommandRouteLiveStatus",
        "render_source": "state-model",
    }
    assert securecrt["expected_securecrt_session_manager_chrome"] == {
        "title": "Session Manager",
        "filter_placeholder": "Filter sessions",
        "static_title_x": 8,
        "static_title_y": 8,
        "static_filter_y": 35,
        "static_filter_x_margin": 8,
        "static_filter_height": 24,
        "static_filter_placeholder_x": 17,
        "static_filter_placeholder_y": 7,
        "live_max_height": 94,
        "live_spacing": 5,
        "live_title_spacing": 5,
        "live_filter_height": 24,
        "actions": [
            {
                "key": "connect",
                "icon_key": "connect",
                "label": "Connect",
                "static_x": 34,
                "static_y": 5,
                "static_button_size": 20,
                "static_icon_x": 7,
                "static_icon_y": 3,
                "static_icon_size": 10,
                "live_icon_size": 14,
                "live_button_size": 24,
                "render_source": "generated-pixmap",
            },
            {
                "key": "new-folder",
                "icon_key": "folder",
                "label": "New Folder",
                "static_x": 60,
                "static_y": 5,
                "static_button_size": 20,
                "static_icon_x": 5,
                "static_icon_y": 5,
                "static_icon_size": 10,
                "live_icon_size": 14,
                "live_button_size": 24,
                "render_source": "generated-pixmap",
            },
            {
                "key": "properties",
                "icon_key": "properties",
                "label": "Properties",
                "static_x": 86,
                "static_y": 5,
                "static_button_size": 20,
                "static_icon_x": 6,
                "static_icon_y": 4,
                "static_icon_size": 9,
                "live_icon_size": 14,
                "live_button_size": 24,
                "render_source": "generated-pixmap",
            },
        ],
    }
    assert securecrt["expected_securecrt_session_manager_route"] == {
        "key": "securecrt-session-manager-route",
        "route_role": "session-manager-selection-to-active-tab",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod (SSH2)",
        "selected_tree_object": "profileTree",
        "session_manager_object": "secureCrtSessionManagerChrome",
        "session_manager_action_key": "connect",
        "session_manager_action_object": "secureCrtSessionManagerAction",
        "status_strip_object": "secureCrtSessionStatusStrip",
        "status_field_key": "target",
        "status_field_object": "secureCrtSessionStatusCell",
        "active_tab_label": "edge-prod (SSH2)",
        "target_value": "edge-prod.example.invalid:22",
        "protocol_value": "SSH2",
        "session_value": "edge-prod",
        "selected_tree_property": "secureCrtSessionRouteSelected",
        "action_active_property": "secureCrtSessionRouteActive",
        "tab_label_property": "secureCrtSessionRouteActiveTab",
        "status_value_property": "secureCrtSessionRouteStatusValue",
        "render_source": "session-manager-state",
    }
    assert securecrt["expected_securecrt_session_manager_filter_route"] == {
        "key": "securecrt-session-manager-filter-route",
        "route_role": "session-manager-filter-to-visible-session-row",
        "session_manager_object": "secureCrtSessionManagerChrome",
        "filter_object": "secureCrtSessionFilter",
        "selected_tree_object": "profileTree",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod (SSH2)",
        "expected_query": "edge",
        "expected_placeholder": "Filter sessions",
        "matched_result_label": "edge-prod (SSH2)",
        "filter_route_property": "secureCrtSessionFilterRouteKey",
        "filter_query_property": "secureCrtSessionFilterRouteQuery",
        "filter_placeholder_property": "secureCrtSessionFilterRoutePlaceholder",
        "matched_result_property": "secureCrtSessionFilterRouteMatchedLabel",
        "change_signal": "textChanged",
        "handler_name": "filter_profile_tree",
        "render_source": "session-manager-filter-state",
    }
    assert securecrt["expected_securecrt_sftp_tab_route"] == {
        "key": "securecrt-sftp-tab-route",
        "route_role": "workflow-card-to-sftp-tab-status",
        "workflow_card_key": "sftp-tab",
        "workflow_card_object": "productWorkflowCard",
        "workflow_title_object": "productWorkflowTitle",
        "workflow_primary_object": "productWorkflowPrimary",
        "workflow_secondary_object": "productWorkflowSecondary",
        "session_manager_object": "secureCrtSessionManagerChrome",
        "selected_tree_object": "profileTree",
        "selected_profile_name": "files-prod",
        "selected_tree_label": "files-prod (SFTP)",
        "active_tab_label": "edge-prod (SSH2)",
        "sftp_tab_label": "files-prod",
        "status_strip_object": "secureCrtSessionStatusStrip",
        "status_field_key": "sftp",
        "status_field_object": "secureCrtSessionStatusCell",
        "status_value": "files-prod tab",
        "transfer_state": "files-prod attached",
        "workflow_title": "SFTP tab",
        "workflow_primary": "files-prod attached",
        "workflow_secondary": "terminal plus transfer workflow",
        "workflow_key_property": "secureCrtSftpTabRouteWorkflowKey",
        "tab_label_property": "secureCrtSftpTabRouteTabLabel",
        "status_property": "secureCrtSftpTabRouteStatus",
        "transfer_state_property": "secureCrtSftpTabRouteTransferState",
        "render_source": "sftp-tab-status-state",
    }
    assert securecrt["expected_securecrt_sftp_browser_route"] == {
        "key": "securecrt-sftp-browser-route",
        "route_role": "sftp-tab-to-transfer-browser",
        "sftp_tab_route_key": "securecrt-sftp-tab-route",
        "browser_object": "secureCrtSftpBrowser",
        "toolbar_object": "secureCrtSftpToolbar",
        "path_object": "secureCrtSftpPath",
        "table_object": "secureCrtSftpTable",
        "row_object": "secureCrtSftpRow",
        "queue_object": "secureCrtSftpQueue",
        "selected_profile_name": "files-prod",
        "selected_tree_label": "files-prod (SFTP)",
        "sftp_tab_label": "files-prod",
        "remote_path": "/srv/files",
        "toolbar_actions": ["upload", "download", "refresh"],
        "file_rows": [
            {"key": "parent", "kind": "folder", "name": "..", "size": "", "modified": "parent", "selected": False},
            {
                "key": "releases",
                "kind": "folder",
                "name": "releases",
                "size": "-",
                "modified": "2026-06-06",
                "selected": False,
            },
            {
                "key": "deploy-log",
                "kind": "file",
                "name": "deploy.log",
                "size": "14 KB",
                "modified": "2026-06-06",
                "selected": True,
            },
        ],
        "active_row_name": "deploy.log",
        "transfer_queue_label": "1 queued",
        "transfer_status": "ready",
        "path_property": "secureCrtSftpBrowserPath",
        "toolbar_actions_property": "secureCrtSftpBrowserToolbarActions",
        "row_name_property": "secureCrtSftpBrowserRowName",
        "row_kind_property": "secureCrtSftpBrowserRowKind",
        "row_selected_property": "secureCrtSftpBrowserRowSelected",
        "queue_state_property": "secureCrtSftpBrowserQueueState",
        "action_object": "secureCrtSftpAction",
        "action_key": "refresh",
        "action_label": "Refresh",
        "action_status": "refreshed",
        "signal": "clicked",
        "handler": "handle_securecrt_sftp_browser_action",
        "signal_property": "secureCrtSftpBrowserRouteSignal",
        "handler_property": "secureCrtSftpBrowserRouteHandler",
        "captured_property": "secureCrtSftpBrowserRouteCaptured",
        "captured_action_property": "secureCrtSftpBrowserRouteCapturedAction",
        "captured_status_property": "secureCrtSftpBrowserRouteCapturedStatus",
        "live_triggered_property": "secureCrtSftpBrowserRouteLiveTriggered",
        "live_action_property": "secureCrtSftpBrowserRouteLiveAction",
        "live_status_property": "secureCrtSftpBrowserRouteLiveStatus",
        "render_source": "sftp-browser-state",
    }
    assert securecrt["expected_securecrt_tree_icons"][:3] == [
        {"label": "Session Database", "icon_key": "database", "row_kind": "root", "static_size": 16},
        {"label": "Folder: Sessions", "icon_key": "folder", "row_kind": "group", "static_size": 14},
        {"label": "edge-prod (SSH2)", "icon_key": "ssh2", "row_kind": "profile", "static_size": 14},
    ]
    assert [field["key"] for field in securecrt["expected_securecrt_session_status_strip"]["fields"]] == [
        "session",
        "target",
        "protocol",
        "cipher",
        "sftp",
        "log",
        "state",
    ]
    assert securecrt["expected_securecrt_session_status_strip"]["title_width"] == 86
    assert securecrt["expected_securecrt_session_status_strip"]["static_cell_start_x"] == 96
    assert securecrt["expected_securecrt_session_status_strip"]["static_cell_gap"] == 6
    assert securecrt["expected_securecrt_session_status_strip"]["fields"][1] == {
        "key": "target",
        "label": "Target",
        "value": "edge-prod.example.invalid:22",
        "static_width": 174,
        "role": "normal",
        "static_y": 5,
        "static_height": 20,
        "static_label_x": 6,
        "static_label_y": 9,
        "static_value_x": 48,
        "static_value_y": 9,
        "live_min_width": 170,
        "live_cell_height": 22,
    }
    assert "session-manager-chrome" in securecrt["layout_contract_ids"]
    assert "session-status-strip" in securecrt["layout_contract_ids"]
    assert securecrt["layout_contract_count"] == len(checker.live_layout_contracts_for_preset("securecrt"))
    assert securecrt["topology_contract_count"] == len(checker.live_topology_contracts_for_preset("securecrt"))
    assert ["leftPanel", "sessionTabs"] in securecrt["topology_contract_widgets"]

    remmina = summaries["remmina"]
    assert "remmina-tree-icons" in remmina["contract_checks"]
    assert "remmina-profile-list-chrome" in remmina["contract_checks"]
    assert "remmina-viewer-controls" in remmina["contract_checks"]
    assert "remmina-profile-viewer-route" in remmina["contract_checks"]
    assert "remmina-profile-filter-route" in remmina["contract_checks"]
    assert "remmina-clipboard-route" in remmina["contract_checks"]
    assert "remmina-screenshot-route" in remmina["contract_checks"]
    assert "remmina-screenshot-live-capture-route" in remmina["contract_checks"]
    assert "remmina-sftp-transfer-route" in remmina["contract_checks"]
    assert "remmina-sftp-transfer-live-queue-route" in remmina["contract_checks"]
    assert "product-identity-route" in remmina["contract_checks"]
    assert remmina["expected_product_tree_icons"][:3] == [
        {"label": "Profile Groups", "icon_key": "folder", "row_kind": "root", "static_size": 16},
        {"label": "Group: RDP", "icon_key": "folder", "row_kind": "group", "static_size": 14},
        {"label": "RDP - win-admin", "icon_key": "rdp", "row_kind": "profile", "static_size": 14},
    ]
    assert remmina["required_widgets"]["remminaProfileListChrome"] == "Remmina profile list chrome"
    assert remmina["required_widgets"]["remminaSftpTransferPanel"] == "Remmina SFTP transfer panel"
    assert "profile-list-chrome" in remmina["layout_contract_ids"]
    assert remmina["expected_reference_tab_label"] == "RDP - win-admin"
    assert remmina["expected_product_identity_route"]["key"] == "remmina-product-identity-route"
    assert remmina["expected_product_identity_route"]["active_tab_label"] == "RDP - win-admin"
    assert remmina["expected_product_identity_route"]["selected_tree_label"] == "RDP - win-admin"
    assert remmina["expected_product_identity_route"]["status_segments"] == [
        "RDP/VNC ready",
        "Scale 100%",
        "Clipboard on",
    ]
    assert remmina["expected_remmina_profile_list_chrome"]["title"] == "Connection list"
    assert remmina["expected_remmina_profile_list_chrome"]["static_filter_x"] == 110
    assert remmina["expected_remmina_profile_list_chrome"]["static_row_height"] == 22
    assert remmina["expected_remmina_profile_list_chrome"]["static_row_step"] == 24
    assert remmina["expected_remmina_profile_list_chrome"]["live_filter_width"] == 142
    assert remmina["expected_remmina_profile_list_chrome"]["live_row_min_height"] == 24
    assert remmina["expected_remmina_profile_list_chrome"]["columns"] == [
        {"key": "name", "label": "Name", "static_width": 98, "live_min_width": 98},
        {"key": "protocol", "label": "Protocol", "static_width": 58, "live_min_width": 58},
        {"key": "server", "label": "Server", "static_width": 104, "live_min_width": 104},
    ]
    assert remmina["expected_remmina_profile_list_chrome"]["rows"][0] == {
        "key": "win-admin",
        "name": "win-admin",
        "protocol": "RDP",
        "server": "admin-win.example.invalid",
        "status": "scale 100%",
        "selected": True,
    }
    assert "remmina-viewer-control-geometry" in remmina["contract_checks"]
    assert "remmina-profile-list-geometry" in remmina["contract_checks"]
    assert remmina["expected_remmina_profile_viewer_route"] == {
        "key": "remmina-selected-profile-viewer-route",
        "route_role": "selected-profile-to-viewer-tab",
        "selected_profile_key": "win-admin",
        "selected_profile_object": "remminaProfileListRow",
        "viewer_controls_object": "remminaViewerControls",
        "viewer_control_key": "scale-100",
        "viewer_control_object": "remminaViewerControl",
        "active_tab_label": "RDP - win-admin",
        "protocol": "RDP",
        "profile_status": "scale 100%",
        "selected_row_property": "selectedRow",
        "control_active_property": "remminaProfileViewerRouteActive",
        "tab_label_property": "remminaProfileViewerRouteActiveTab",
        "render_source": "profile-list-state",
    }
    assert remmina["expected_remmina_profile_filter_route"] == {
        "key": "remmina-profile-filter-route",
        "route_role": "profile-filter-to-visible-viewer-row",
        "profile_list_object": "remminaProfileListChrome",
        "filter_object": "remminaProfileFilter",
        "selected_profile_key": "win-admin",
        "selected_profile_object": "remminaProfileListRow",
        "matched_profile_name": "win-admin",
        "matched_protocol": "RDP",
        "matched_status": "scale 100%",
        "expected_query": "rdp",
        "expected_placeholder": "Filter by name or protocol",
        "active_tab_label": "RDP - win-admin",
        "filter_route_property": "remminaProfileFilterRouteKey",
        "filter_query_property": "remminaProfileFilterRouteQuery",
        "filter_placeholder_property": "remminaProfileFilterRoutePlaceholder",
        "matched_profile_property": "remminaProfileFilterRouteMatchedProfile",
        "matched_protocol_property": "remminaProfileFilterRouteMatchedProtocol",
        "active_tab_property": "remminaProfileFilterRouteActiveTab",
        "change_signal": "textChanged",
        "handler_name": "filter_remmina_profile_rows",
        "render_source": "profile-filter-state",
    }
    assert remmina["expected_remmina_clipboard_route"] == {
        "key": "remmina-clipboard-sync-route",
        "route_role": "viewer-control-to-clipboard-state",
        "viewer_controls_object": "remminaViewerControls",
        "viewer_control_key": "clipboard",
        "viewer_control_object": "remminaViewerControl",
        "active_tab_label": "RDP - win-admin",
        "protocol": "RDP",
        "clipboard_state": "clipboard on",
        "status_segment": "Clipboard on",
        "detail_line": "Clipboard: enabled",
        "activity_line": "Clipboard: on",
        "control_active_property": "remminaClipboardRouteActive",
        "tab_label_property": "remminaClipboardRouteActiveTab",
        "clipboard_state_property": "remminaClipboardRouteState",
        "render_source": "viewer-control-state",
    }
    assert remmina["expected_remmina_screenshot_route"] == {
        "key": "remmina-screenshot-capture-route",
        "route_role": "viewer-control-to-screenshot-capture",
        "viewer_controls_object": "remminaViewerControls",
        "viewer_control_key": "screenshot",
        "viewer_control_object": "remminaViewerControl",
        "active_tab_label": "RDP - win-admin",
        "protocol": "RDP",
        "capture_state": "screenshot ready",
        "capture_artifact": "win-admin-rdp-screenshot.png",
        "status_segment": "RDP/VNC ready",
        "detail_line": "Screenshot: win-admin-rdp-screenshot.png",
        "activity_line": "Screenshot: capture ready",
        "control_active_property": "remminaScreenshotRouteActive",
        "tab_label_property": "remminaScreenshotRouteActiveTab",
        "capture_state_property": "remminaScreenshotRouteState",
        "capture_artifact_property": "remminaScreenshotRouteArtifact",
        "signal": "clicked",
        "handler": "handle_remmina_screenshot_capture",
        "signal_property": "remminaScreenshotRouteSignal",
        "handler_property": "remminaScreenshotRouteHandler",
        "captured_property": "remminaScreenshotRouteCaptured",
        "captured_state_property": "remminaScreenshotRouteCapturedState",
        "captured_artifact_property": "remminaScreenshotRouteCapturedArtifact",
        "live_triggered_property": "remminaScreenshotRouteLiveTriggered",
        "live_capture_state_property": "remminaScreenshotRouteLiveState",
        "live_capture_artifact_property": "remminaScreenshotRouteLiveArtifact",
        "render_source": "viewer-control-state",
    }
    assert remmina["expected_remmina_sftp_transfer_route"] == {
        "key": "remmina-sftp-transfer-route",
        "route_role": "transfer-toolbar-to-sftp-profile-browser",
        "profile_list_object": "remminaProfileListChrome",
        "selected_profile_key": "sftp-ops",
        "selected_profile_name": "sftp-ops",
        "selected_profile_protocol": "SFTP",
        "selected_profile_status": "file sharing",
        "selected_profile_object": "remminaProfileListRow",
        "selected_tree_label": "sftp-ops",
        "toolbar_action_key": "queue",
        "toolbar_action_label": "Transfer",
        "toolbar_action_object": "productToolbarButton",
        "active_tab_label": "sftp-ops",
        "transfer_panel_object": "remminaSftpTransferPanel",
        "toolbar_object": "remminaSftpTransferToolbar",
        "path_object": "remminaSftpTransferPath",
        "table_object": "remminaSftpTransferTable",
        "row_object": "remminaSftpTransferRow",
        "queue_object": "remminaSftpTransferQueue",
        "remote_path": "/var/log",
        "toolbar_actions": ["upload", "download", "queue"],
        "file_rows": [
            {
                "key": "parent",
                "kind": "folder",
                "name": "..",
                "size": "",
                "modified": "parent",
                "selected": False,
            },
            {
                "key": "logs",
                "kind": "folder",
                "name": "logs",
                "size": "-",
                "modified": "2026-06-06",
                "selected": False,
            },
            {
                "key": "app-log",
                "kind": "file",
                "name": "app.log",
                "size": "12 KB",
                "modified": "2026-06-06",
                "selected": True,
            },
        ],
        "active_row_name": "app.log",
        "transfer_queue_label": "1 queued",
        "transfer_status": "ready",
        "detail_line": "Shared   : file workflow ready",
        "activity_line": "SFTP transfer: queue ready",
        "selected_profile_property": "remminaSftpTransferRouteSelectedProfile",
        "toolbar_active_property": "remminaSftpTransferRouteActive",
        "tab_label_property": "remminaSftpTransferRouteActiveTab",
        "path_property": "remminaSftpTransferRoutePath",
        "toolbar_actions_property": "remminaSftpTransferRouteToolbarActions",
        "row_name_property": "remminaSftpTransferRouteRowName",
        "row_kind_property": "remminaSftpTransferRouteRowKind",
        "row_selected_property": "remminaSftpTransferRouteRowSelected",
        "queue_state_property": "remminaSftpTransferRouteQueueState",
        "action_object": "remminaSftpTransferAction",
        "action_key": "queue",
        "action_label": "Queue",
        "action_status": "queued",
        "signal": "clicked",
        "handler": "handle_remmina_sftp_transfer_action",
        "signal_property": "remminaSftpTransferRouteSignal",
        "handler_property": "remminaSftpTransferRouteHandler",
        "captured_property": "remminaSftpTransferRouteCaptured",
        "captured_action_property": "remminaSftpTransferRouteCapturedAction",
        "captured_status_property": "remminaSftpTransferRouteCapturedStatus",
        "live_triggered_property": "remminaSftpTransferRouteLiveTriggered",
        "live_action_property": "remminaSftpTransferRouteLiveAction",
        "live_status_property": "remminaSftpTransferRouteLiveStatus",
        "render_source": "sftp-transfer-state",
    }
    assert remmina["expected_remmina_viewer_controls"] == [
        {
            "key": "fit",
            "icon_key": "fit",
            "label": "Fit",
            "static_width": 74,
            "static_step": 78,
            "static_y": 7,
            "static_height": 20,
            "static_icon_x": 6,
            "static_icon_size": 12,
            "static_label_x": 22,
            "live_icon_size": 14,
            "live_min_width": 74,
            "live_button_height": 26,
            "render_source": "generated-pixmap",
        },
        {
            "key": "scale-100",
            "icon_key": "scale",
            "label": "Scale 100%",
            "static_width": 74,
            "static_step": 78,
            "static_y": 7,
            "static_height": 20,
            "static_icon_x": 6,
            "static_icon_size": 12,
            "static_label_x": 22,
            "live_icon_size": 14,
            "live_min_width": 74,
            "live_button_height": 26,
            "render_source": "generated-pixmap",
        },
        {
            "key": "clipboard",
            "icon_key": "clipboard",
            "label": "Clipboard",
            "static_width": 74,
            "static_step": 78,
            "static_y": 7,
            "static_height": 20,
            "static_icon_x": 6,
            "static_icon_size": 12,
            "static_label_x": 22,
            "live_icon_size": 14,
            "live_min_width": 74,
            "live_button_height": 26,
            "render_source": "generated-pixmap",
        },
        {
            "key": "fullscreen",
            "icon_key": "fullscreen",
            "label": "Fullscreen",
            "static_width": 74,
            "static_step": 78,
            "static_y": 7,
            "static_height": 20,
            "static_icon_x": 6,
            "static_icon_size": 12,
            "static_label_x": 22,
            "live_icon_size": 14,
            "live_min_width": 74,
            "live_button_height": 26,
            "render_source": "generated-pixmap",
        },
        {
            "key": "screenshot",
            "icon_key": "screenshot",
            "label": "Screenshot",
            "static_width": 74,
            "static_step": 78,
            "static_y": 7,
            "static_height": 20,
            "static_icon_x": 6,
            "static_icon_size": 12,
            "static_label_x": 22,
            "live_icon_size": 14,
            "live_min_width": 74,
            "live_button_height": 26,
            "render_source": "generated-pixmap",
        },
    ]

    termius = summaries["termius"]
    assert "termius-tree-icons" in termius["contract_checks"]
    assert "termius-hosts-chrome" in termius["contract_checks"]
    assert "termius-header-chips" in termius["contract_checks"]
    assert "termius-host-identity-strip" in termius["contract_checks"]
    assert "termius-host-identity-geometry" in termius["contract_checks"]
    assert "termius-host-selection-route" in termius["contract_checks"]
    assert "termius-sync-route" in termius["contract_checks"]
    assert "termius-port-forward-route" in termius["contract_checks"]
    assert "termius-snippet-route" in termius["contract_checks"]
    assert "termius-snippet-live-run-route" in termius["contract_checks"]
    assert "termius-files-browser-route" in termius["contract_checks"]
    assert "termius-files-browser-live-sync-route" in termius["contract_checks"]
    assert "product-identity-route" in termius["contract_checks"]
    assert termius["expected_product_tree_icons"][:3] == [
        {"label": "Personal Vault", "icon_key": "database", "row_kind": "root", "static_size": 16},
        {"label": "Vault / Personal", "icon_key": "folder", "row_kind": "group", "static_size": 14},
        {"label": "edge-prod  ssh host", "icon_key": "host", "row_kind": "profile", "static_size": 14},
    ]
    assert termius["required_widgets"]["termiusHostsChrome"] == "Termius Hosts search/action chrome"
    assert termius["required_widgets"]["termiusHostIdentityStrip"] == "Termius host identity strip"
    assert "hosts-sidebar-chrome" in termius["layout_contract_ids"]
    assert "host-identity-strip" in termius["layout_contract_ids"]
    assert termius["expected_reference_tab_label"] == "edge-prod"
    assert termius["expected_product_identity_route"]["key"] == "termius-product-identity-route"
    assert termius["expected_product_identity_route"]["active_tab_label"] == "edge-prod"
    assert termius["expected_product_identity_route"]["selected_tree_label"] == "edge-prod  ssh host"
    assert termius["expected_product_identity_route"]["status_segments"] == [
        "Vault unlocked",
        "Port fwd ready",
        "Sync current",
    ]
    assert termius["expected_termius_header_chips"] == [
        {"key": "vault-unlocked", "label": "Vault unlocked"},
        {"key": "sync-current", "label": "Sync current"},
        {"key": "port-forward-ready", "label": "Port fwd ready"},
    ]
    assert termius["expected_termius_hosts_chrome"] == {
        "title": "Hosts",
        "filter_placeholder": "Search hosts",
        "actions": [
            {"key": "new-host", "icon_key": "plus", "label": "Add Host", "static_x": 34},
            {"key": "keychain", "icon_key": "key", "label": "Keychain", "static_x": 60},
            {"key": "sync-hosts", "icon_key": "sync", "label": "Sync", "static_x": 86},
        ],
    }
    assert termius["expected_termius_host_identity_strip"]["title"] == "Host identity"
    assert termius["expected_termius_host_identity_strip"]["title_width"] == 88
    assert termius["expected_termius_host_identity_strip"]["static_cell_start_x"] == 80
    assert termius["expected_termius_host_identity_strip"]["static_cell_gap"] == 6
    assert termius["expected_termius_host_identity_strip"]["fields"][1] == {
        "key": "identity",
        "label": "Identity",
        "value": "prod-ed25519",
        "static_width": 112,
        "role": "normal",
        "static_y": 5,
        "static_height": 20,
        "static_label_x": 6,
        "static_label_y": 9,
        "static_value_x": 42,
        "static_value_y": 9,
        "live_min_width": 112,
        "live_cell_height": 22,
    }
    assert termius["expected_termius_host_identity_strip"]["fields"][4] == {
        "key": "forward",
        "label": "Forward",
        "value": "8080 -> localhost:80",
        "static_width": 132,
        "role": "normal",
        "static_y": 5,
        "static_height": 20,
        "static_label_x": 6,
        "static_label_y": 9,
        "static_value_x": 42,
        "static_value_y": 9,
        "live_min_width": 132,
        "live_cell_height": 22,
    }
    assert termius["expected_termius_sync_route"] == {
        "key": "termius-host-sync-route",
        "route_role": "hosts-sync-to-identity-status",
        "hosts_action_key": "sync-hosts",
        "hosts_action_object": "termiusHostsAction",
        "header_chip_key": "sync-current",
        "header_chip_object": "termiusHeaderChip",
        "identity_field_key": "sync",
        "identity_cell_object": "termiusHostIdentityCell",
        "sync_state": "current",
        "action_label_property": "termiusSyncRouteActionLabel",
        "chip_label_property": "termiusSyncRouteChipLabel",
        "identity_value_property": "termiusSyncRouteIdentityValue",
        "status_property": "termiusSyncRouteState",
        "render_source": "state-model",
    }
    assert termius["expected_termius_host_selection_route"] == {
        "key": "termius-host-selection-route",
        "route_role": "host-list-selection-to-active-tab",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod  ssh host",
        "selected_tree_object": "profileTree",
        "hosts_panel_object": "termiusHostsChrome",
        "host_identity_object": "termiusHostIdentityStrip",
        "identity_field_key": "host",
        "identity_cell_object": "termiusHostIdentityCell",
        "active_tab_label": "edge-prod",
        "target_value": "edge-prod.example.invalid:22",
        "protocol_value": "SSH + Vault",
        "host_value": "edge-prod",
        "selected_tree_property": "termiusHostRouteSelected",
        "tab_label_property": "termiusHostRouteActiveTab",
        "identity_value_property": "termiusHostRouteIdentityValue",
        "render_source": "host-list-state",
    }
    assert termius["expected_termius_port_forward_route"] == {
        "key": "termius-port-forward-route",
        "route_role": "port-forward-chip-to-host-identity-forward",
        "header_chip_key": "port-forward-ready",
        "header_chip_object": "termiusHeaderChip",
        "host_identity_object": "termiusHostIdentityStrip",
        "identity_field_key": "forward",
        "identity_cell_object": "termiusHostIdentityCell",
        "active_tab_label": "edge-prod",
        "selected_profile_name": "edge-prod",
        "forward_value": "8080 -> localhost:80",
        "forward_state": "ready",
        "local_port": 8080,
        "remote_host": "localhost",
        "remote_port": 80,
        "status_segment": "Port fwd ready",
        "chip_label_property": "termiusPortForwardRouteChipLabel",
        "identity_value_property": "termiusPortForwardRouteIdentityValue",
        "active_tab_property": "termiusPortForwardRouteActiveTab",
        "status_property": "termiusPortForwardRouteState",
        "render_source": "state-model",
    }
    assert termius["expected_termius_snippet_route"] == {
        "key": "termius-snippet-route",
        "route_role": "workflow-card-to-host-identity-snippet",
        "workflow_card_key": "snippet",
        "workflow_card_object": "productWorkflowCard",
        "workflow_title_object": "productWorkflowTitle",
        "workflow_primary_object": "productWorkflowPrimary",
        "workflow_secondary_object": "productWorkflowSecondary",
        "action_object": "termiusSnippetRunAction",
        "shortcut_object": "termiusSnippetRunShortcut",
        "host_identity_object": "termiusHostIdentityStrip",
        "identity_field_key": "snippet",
        "identity_cell_object": "termiusHostIdentityCell",
        "active_tab_label": "edge-prod",
        "selected_profile_name": "edge-prod",
        "workflow_title": "Snippet",
        "snippet_command": "row vault status",
        "snippet_state": "one-click command",
        "detail_line": "Snippet  : row vault status",
        "action_label": "Run",
        "shortcut_sequence": "Return",
        "workflow_key_property": "termiusSnippetRouteWorkflowKey",
        "command_property": "termiusSnippetRouteCommand",
        "identity_value_property": "termiusSnippetRouteIdentityValue",
        "active_tab_property": "termiusSnippetRouteActiveTab",
        "status_property": "termiusSnippetRouteState",
        "captured_property": "termiusSnippetRouteCaptured",
        "captured_command_property": "termiusSnippetRouteCapturedCommand",
        "captured_target_profile_property": "termiusSnippetRouteCapturedTargetProfile",
        "captured_status_property": "termiusSnippetRouteCapturedStatus",
        "signal": "clicked",
        "secondary_signal": "activated",
        "handler": "handle_termius_snippet_run",
        "signal_property": "termiusSnippetRouteSignal",
        "secondary_signal_property": "termiusSnippetRouteSecondarySignal",
        "handler_property": "termiusSnippetRouteHandler",
        "live_triggered_property": "termiusSnippetRouteLiveTriggered",
        "live_command_property": "termiusSnippetRouteLiveCommand",
        "live_target_profile_property": "termiusSnippetRouteLiveTargetProfile",
        "live_status_property": "termiusSnippetRouteLiveStatus",
        "render_source": "state-model",
    }
    assert termius["expected_termius_files_browser_route"] == {
        "key": "termius-files-browser-route",
        "route_role": "host-files-tab-to-sftp-browser",
        "host_selection_route_key": "termius-host-selection-route",
        "host_identity_object": "termiusHostIdentityStrip",
        "identity_field_key": "files",
        "identity_cell_object": "termiusHostIdentityCell",
        "files_browser_object": "termiusFilesBrowser",
        "toolbar_object": "termiusFilesToolbar",
        "path_object": "termiusFilesPath",
        "table_object": "termiusFilesTable",
        "row_object": "termiusFilesRow",
        "queue_object": "termiusFilesQueue",
        "active_tab_label": "edge-prod",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod  ssh host",
        "files_state": "SFTP ready",
        "remote_path": "/workspace",
        "toolbar_actions": ["upload", "download", "sync"],
        "file_rows": [
            {
                "key": "parent",
                "kind": "folder",
                "name": "..",
                "size": "",
                "modified": "parent",
                "selected": False,
            },
            {
                "key": "src",
                "kind": "folder",
                "name": "src",
                "size": "-",
                "modified": "2026-06-06",
                "selected": False,
            },
            {
                "key": "deploy-yml",
                "kind": "file",
                "name": "deploy.yml",
                "size": "3 KB",
                "modified": "2026-06-06",
                "selected": True,
            },
        ],
        "active_row_name": "deploy.yml",
        "transfer_queue_label": "sync idle",
        "transfer_status": "ready",
        "identity_value_property": "termiusFilesRouteIdentityValue",
        "active_tab_property": "termiusFilesRouteActiveTab",
        "path_property": "termiusFilesRoutePath",
        "toolbar_actions_property": "termiusFilesRouteToolbarActions",
        "row_name_property": "termiusFilesRouteRowName",
        "row_kind_property": "termiusFilesRouteRowKind",
        "row_selected_property": "termiusFilesRouteRowSelected",
        "queue_state_property": "termiusFilesRouteQueueState",
        "action_object": "termiusFilesAction",
        "action_key": "sync",
        "action_label": "Sync",
        "action_status": "synced",
        "signal": "clicked",
        "handler": "handle_termius_files_sync",
        "signal_property": "termiusFilesRouteSignal",
        "handler_property": "termiusFilesRouteHandler",
        "captured_property": "termiusFilesRouteCaptured",
        "captured_action_property": "termiusFilesRouteCapturedAction",
        "captured_status_property": "termiusFilesRouteCapturedStatus",
        "live_triggered_property": "termiusFilesRouteLiveTriggered",
        "live_action_property": "termiusFilesRouteLiveAction",
        "live_status_property": "termiusFilesRouteLiveStatus",
        "render_source": "files-browser-state",
    }

    mremoteng = summaries["mremoteng"]
    assert "mremoteng-tree-icons" in mremoteng["contract_checks"]
    assert "mremoteng-top-chrome" in mremoteng["contract_checks"]
    assert "mremoteng-document-controls" in mremoteng["contract_checks"]
    assert "mremoteng-document-control-geometry" in mremoteng["contract_checks"]
    assert "mremoteng-property-grid" in mremoteng["contract_checks"]
    assert "mremoteng-connection-document-route" in mremoteng["contract_checks"]
    assert "mremoteng-connection-reconnect-live-route" in mremoteng["contract_checks"]
    assert "mremoteng-document-filter-route" in mremoteng["contract_checks"]
    assert "mremoteng-inheritance-route" in mremoteng["contract_checks"]
    assert "product-identity-route" in mremoteng["contract_checks"]
    assert mremoteng["expected_product_tree_icons"][:3] == [
        {"label": "Connections", "icon_key": "database", "row_kind": "root", "static_size": 16},
        {"label": "Container: prod", "icon_key": "folder", "row_kind": "group", "static_size": 14},
        {"label": "edge-prod [SSH]", "icon_key": "ssh", "row_kind": "profile", "static_size": 14},
    ]
    assert mremoteng["required_widgets"]["mRemoteNgMenuBar"] == "mRemoteNG top menu bar"
    assert mremoteng["required_widgets"]["mRemoteNgPropertyGrid"] == "mRemoteNG property inheritance grid"
    assert "property-grid" in mremoteng["layout_contract_ids"]
    assert "document-tree-filter" in mremoteng["layout_contract_ids"]
    assert mremoteng["expected_reference_tab_label"] == "edge-prod [SSH]"
    assert mremoteng["expected_product_identity_route"]["key"] == "mremoteng-product-identity-route"
    assert mremoteng["expected_product_identity_route"]["active_tab_label"] == "edge-prod [SSH]"
    assert mremoteng["expected_product_identity_route"]["selected_tree_label"] == "edge-prod [SSH]"
    assert mremoteng["expected_product_identity_route"]["status_segments"] == [
        "Connections.xml",
        "Inheritance on",
        "2 open panes",
    ]
    assert [item["label"] for item in mremoteng["expected_mremoteng_top_chrome"]["menu_items"]] == [
        "File",
        "View",
        "Connections",
        "Tools",
        "Window",
        "Help",
    ]
    assert mremoteng["expected_mremoteng_top_chrome"]["toolbar_height"] == 50
    assert mremoteng["expected_mremoteng_top_chrome"]["toolbar_actions"][6] == {
        "key": "files",
        "icon_key": "external-tool",
        "label": "External",
        "static_x": 440,
        "static_width": 74,
    }
    assert mremoteng["expected_mremoteng_document_controls"] == {
        "title": "Connections.xml",
        "filter_placeholder": "Filter connection tree",
        "title_width": 112,
        "static_height": 28,
        "static_button_start_x": 128,
        "static_button_gap": 8,
        "static_filter_width": 178,
        "static_filter_y": 5,
        "static_filter_height": 18,
        "live_filter_width": 178,
        "live_filter_height": 24,
        "controls": [
            {
                "key": "save",
                "icon_key": "database",
                "label": "Save",
                "static_width": 56,
                "static_y": 4,
                "static_height": 20,
                "static_icon_x": 8,
                "static_icon_y": 7,
                "static_icon_size": 13,
                "static_label_x": 27,
                "static_label_y": 8,
                "live_icon_size": 14,
                "live_min_width": 56,
                "live_button_height": 26,
                "render_source": "generated-pixmap",
            },
            {
                "key": "reconnect",
                "icon_key": "ssh",
                "label": "Reconnect",
                "static_width": 88,
                "static_y": 4,
                "static_height": 20,
                "static_icon_x": 8,
                "static_icon_y": 7,
                "static_icon_size": 13,
                "static_label_x": 27,
                "static_label_y": 8,
                "live_icon_size": 14,
                "live_min_width": 88,
                "live_button_height": 26,
                "render_source": "generated-pixmap",
            },
            {
                "key": "external-tool",
                "icon_key": "external",
                "label": "External tool",
                "static_width": 104,
                "static_y": 4,
                "static_height": 20,
                "static_icon_x": 8,
                "static_icon_y": 7,
                "static_icon_size": 13,
                "static_label_x": 27,
                "static_label_y": 8,
                "live_icon_size": 14,
                "live_min_width": 104,
                "live_button_height": 26,
                "render_source": "generated-pixmap",
            },
            {
                "key": "dock-view",
                "icon_key": "rdp",
                "label": "Dock view",
                "static_width": 84,
                "static_y": 4,
                "static_height": 20,
                "static_icon_x": 8,
                "static_icon_y": 7,
                "static_icon_size": 13,
                "static_label_x": 27,
                "static_label_y": 8,
                "live_icon_size": 14,
                "live_min_width": 84,
                "live_button_height": 26,
                "render_source": "generated-pixmap",
            },
        ],
    }
    assert mremoteng["expected_mremoteng_property_grid"]["columns"] == [
        {"key": "property", "label": "Property", "static_width": 155},
        {"key": "inherited", "label": "Inherited", "static_width": 150},
        {"key": "effective", "label": "Effective value", "static_width": 270},
        {"key": "source", "label": "Source", "static_width": 245},
    ]
    assert mremoteng["expected_mremoteng_property_grid"]["rows"][1] == {
        "key": "hostname",
        "property_label": "Hostname",
        "inherited_from": "connection node",
        "effective_value": "edge-prod.example.invalid",
        "source": "Connections.xml/prod/edge-prod",
        "inherited": False,
    }
    assert mremoteng["expected_mremoteng_connection_document_route"] == {
        "key": "mremoteng-selected-connection-document-route",
        "route_role": "connection-tree-to-document-workspace",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod [SSH]",
        "selected_tree_object": "profileTree",
        "document_controls_object": "mRemoteNgDocumentControls",
        "document_control_key": "reconnect",
        "document_control_object": "mRemoteNgDocumentControl",
        "property_grid_object": "mRemoteNgPropertyGrid",
        "property_row_key": "protocol",
        "property_cell_object": "mRemoteNgPropertyGridCell",
        "active_tab_label": "edge-prod [SSH]",
        "protocol": "SSH",
        "workspace_state": "document open",
        "property_value": "SSH",
        "selected_tree_property": "mRemoteNgConnectionRouteSelected",
        "control_active_property": "mRemoteNgConnectionRouteActive",
        "tab_label_property": "mRemoteNgConnectionRouteActiveTab",
        "property_value_property": "mRemoteNgConnectionRoutePropertyValue",
        "signal": "clicked",
        "handler": "handle_mremoteng_document_reconnect",
        "reconnect_state": "reconnected",
        "signal_property": "mRemoteNgConnectionRouteSignal",
        "handler_property": "mRemoteNgConnectionRouteHandler",
        "captured_property": "mRemoteNgConnectionRouteCaptured",
        "captured_state_property": "mRemoteNgConnectionRouteCapturedState",
        "captured_profile_property": "mRemoteNgConnectionRouteCapturedProfile",
        "live_triggered_property": "mRemoteNgConnectionRouteLiveTriggered",
        "live_state_property": "mRemoteNgConnectionRouteLiveState",
        "live_profile_property": "mRemoteNgConnectionRouteLiveProfile",
        "render_source": "connection-tree-state",
    }
    assert mremoteng["expected_mremoteng_document_filter_route"] == {
        "key": "mremoteng-document-filter-route",
        "route_role": "document-filter-to-selected-connection-row",
        "document_controls_object": "mRemoteNgDocumentControls",
        "filter_object": "mRemoteNgDocumentFilter",
        "selected_tree_object": "profileTree",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod [SSH]",
        "matched_protocol": "SSH",
        "matched_state": "document open",
        "expected_query": "edge",
        "expected_placeholder": "Filter connection tree",
        "active_tab_label": "edge-prod [SSH]",
        "filter_route_property": "mRemoteNgDocumentFilterRouteKey",
        "filter_query_property": "mRemoteNgDocumentFilterRouteQuery",
        "filter_placeholder_property": "mRemoteNgDocumentFilterRoutePlaceholder",
        "matched_tree_property": "mRemoteNgDocumentFilterRouteMatchedTreeLabel",
        "matched_protocol_property": "mRemoteNgDocumentFilterRouteMatchedProtocol",
        "active_tab_property": "mRemoteNgDocumentFilterRouteActiveTab",
        "change_signal": "textChanged",
        "handler_name": "filter_profile_tree",
        "render_source": "connection-tree-filter-state",
    }
    assert mremoteng["expected_mremoteng_inheritance_route"] == {
        "key": "mremoteng-inheritance-route",
        "route_role": "workflow-card-to-property-grid-inheritance",
        "workflow_card_key": "inheritance-grid",
        "workflow_card_object": "productWorkflowCard",
        "workflow_title_object": "productWorkflowTitle",
        "workflow_primary_object": "productWorkflowPrimary",
        "workflow_secondary_object": "productWorkflowSecondary",
        "property_grid_object": "mRemoteNgPropertyGrid",
        "property_row_key": "credential",
        "property_cell_object": "mRemoteNgPropertyGridCell",
        "active_tab_label": "edge-prod [SSH]",
        "selected_profile_name": "edge-prod",
        "selected_tree_label": "edge-prod [SSH]",
        "workflow_title": "Config inheritance",
        "inherited_property_label": "Credential",
        "inherited_value": "operator key reference",
        "inherited_source": "Connections.xml/prod",
        "inheritance_state": "credentials inherited",
        "workflow_key_property": "mRemoteNgInheritanceRouteWorkflowKey",
        "inherited_value_property": "mRemoteNgInheritanceRouteInheritedValue",
        "active_tab_property": "mRemoteNgInheritanceRouteActiveTab",
        "status_property": "mRemoteNgInheritanceRouteState",
        "render_source": "property-grid-state",
    }

    native = summaries["native"]
    assert native["reference_profile"] is None
    assert native["layout_contract_count"] == 0
    assert native["topology_contract_count"] == 0
    assert "workspace-surface" in native["contract_checks"]


def test_real_gui_render_tracks_live_layout_contracts_for_product_presets() -> None:
    checker = _load_checker()

    assert set(checker.LIVE_LAYOUT_CONTRACTS) == checker.PRODUCT_STYLE_PRESETS
    for preset_id in checker.PRODUCT_STYLE_PRESETS:
        contracts = checker.live_layout_contracts_for_preset(preset_id)
        assert len(contracts) >= 5
        assert all("object_name" in contract for contract in contracts)
    moba_objects = {str(contract["object_name"]) for contract in checker.live_layout_contracts_for_preset("mobaxterm")}
    assert {
        "mobaQuickConnectChrome",
        "mobaConnectedLeftDock",
        "mobaBottomEdgeControls",
        "mobaSftpFileTable",
        "terminalOutput",
        "mobaTelemetryBar",
    } <= moba_objects
    assert "mobaSessionEdgeControls" not in moba_objects
    assert "mobaRightUtilityRail" not in moba_objects
    assert "mobaSshBanner" not in moba_objects
    mremoteng_objects = {str(contract["object_name"]) for contract in checker.live_layout_contracts_for_preset("mremoteng")}
    assert "mRemoteNgPropertyGrid" in mremoteng_objects
    assert "mRemoteNgDocumentFilter" in mremoteng_objects


def test_real_gui_render_rejects_overlapping_or_out_of_bounds_live_cells() -> None:
    checker = _load_checker()
    container = {"x": 0, "y": 0, "width": 100, "height": 20}
    valid = [
        {"id": "first", "x": 0, "y": 0, "width": 40, "height": 20},
        {"id": "second", "x": 40, "y": 0, "width": 60, "height": 20},
    ]
    invalid = [
        {"id": "first", "x": 0, "y": 0, "width": 60, "height": 20},
        {"id": "second", "x": 50, "y": 0, "width": 60, "height": 20},
    ]

    assert checker.validate_non_overlapping_bounds("proof", valid, container) == []
    errors = checker.validate_non_overlapping_bounds("proof", invalid, container)

    assert any("overlaps" in error for error in errors)
    assert any("outside its parent" in error for error in errors)


def test_real_gui_render_tracks_live_topology_contracts_for_product_presets() -> None:
    checker = _load_checker()

    assert set(checker.LIVE_TOPOLOGY_CONTRACTS) == checker.PRODUCT_STYLE_PRESETS
    for preset_id in checker.PRODUCT_STYLE_PRESETS:
        contracts = checker.live_topology_contracts_for_preset(preset_id)
        expected_count = 6 if preset_id == "mremoteng" else 5
        assert len(contracts) == expected_count
        assert all({"id", "from", "relation", "to"} <= set(contract) for contract in contracts)
    moba_ids = {str(contract["id"]) for contract in checker.live_topology_contracts_for_preset("mobaxterm")}
    assert {
        "rail-left-of-dock",
        "dock-left-of-native-terminal",
        "native-terminal-above-telemetry",
        "sftp-table-inside-dock",
    } <= moba_ids
    mremoteng_ids = {str(contract["id"]) for contract in checker.live_topology_contracts_for_preset("mremoteng")}
    assert "document-controls-above-property-grid" in mremoteng_ids


def test_real_gui_render_live_layout_contract_validation_rejects_geometry_drift() -> None:
    checker = _load_checker()
    contract = {
        "id": "sidebar-width",
        "object_name": "leftPanel",
        "label": "sidebar",
        "min_width": 220,
        "max_width": 360,
        "max_x": 90,
    }

    assert checker.validate_live_layout_contract(
        "securecrt",
        contract,
        {"x": 18, "y": 100, "width": 270, "height": 600},
    ) == []
    assert checker.validate_live_layout_contract(
        "securecrt",
        contract,
        {"x": 120, "y": 100, "width": 180, "height": 600},
    )


def test_real_gui_render_layout_contract_measurement_records_bounds_and_errors() -> None:
    checker = _load_checker()
    contract = {
        "id": "sidebar-width",
        "object_name": "leftPanel",
        "label": "sidebar",
        "min_width": 220,
        "max_width": 360,
    }

    passing = checker.layout_contract_measurement(
        "securecrt",
        contract,
        {"x": 18, "y": 100, "width": 270, "height": 600},
    )
    assert passing["passed"] is True
    assert passing["bounds"]["width"] == 270

    failing = checker.layout_contract_measurement(
        "securecrt",
        contract,
        {"x": 18, "y": 100, "width": 180, "height": 600},
    )
    assert failing["passed"] is False
    assert failing["errors"]


def test_real_gui_render_live_topology_contract_validation_rejects_drift() -> None:
    checker = _load_checker()
    contract = {
        "id": "sidebar-left-of-tabs",
        "from": "leftPanel",
        "relation": "left_of",
        "to": "sessionTabs",
        "min_gap": 0,
        "max_gap": 40,
    }

    assert (
        checker.validate_live_topology_contract(
            "securecrt",
            contract,
            {"x": 20, "y": 100, "width": 280, "height": 600},
            {"x": 320, "y": 100, "width": 820, "height": 500},
        )
        == []
    )
    assert checker.validate_live_topology_contract(
        "securecrt",
        contract,
        {"x": 20, "y": 100, "width": 280, "height": 600},
        {"x": 380, "y": 100, "width": 820, "height": 500},
    )


def test_real_gui_render_topology_contract_measurement_records_gap_and_containment() -> None:
    checker = _load_checker()
    left_contract = {
        "id": "sidebar-left-of-tabs",
        "from": "leftPanel",
        "relation": "left_of",
        "to": "sessionTabs",
        "min_gap": 0,
        "max_gap": 40,
    }

    left_measurement = checker.topology_contract_measurement(
        "securecrt",
        left_contract,
        {"x": 20, "y": 100, "width": 280, "height": 600},
        {"x": 320, "y": 100, "width": 820, "height": 500},
    )
    assert left_measurement["passed"] is True
    assert left_measurement["gap"] == 20

    inside_contract = {
        "id": "sftp-table-inside-dock",
        "from": "mobaSftpFileTable",
        "relation": "inside",
        "to": "mobaConnectedLeftDock",
    }
    inside_measurement = checker.topology_contract_measurement(
        "mobaxterm",
        inside_contract,
        {"x": 40, "y": 180, "width": 300, "height": 180},
        {"x": 24, "y": 130, "width": 360, "height": 600},
    )
    assert inside_measurement["passed"] is True
    assert inside_measurement["contained"] is True


def test_real_gui_render_live_topology_contract_validation_checks_inside() -> None:
    checker = _load_checker()
    contract = {
        "id": "sftp-table-inside-dock",
        "from": "mobaSftpFileTable",
        "relation": "inside",
        "to": "mobaConnectedLeftDock",
    }

    assert (
        checker.validate_live_topology_contract(
            "mobaxterm",
            contract,
            {"x": 40, "y": 180, "width": 300, "height": 180},
            {"x": 24, "y": 130, "width": 360, "height": 600},
        )
        == []
    )
    assert checker.validate_live_topology_contract(
        "mobaxterm",
        contract,
        {"x": 10, "y": 180, "width": 420, "height": 180},
        {"x": 24, "y": 130, "width": 360, "height": 600},
    )


def test_real_gui_render_prepares_mobaxterm_connected_reference() -> None:
    source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "prepare_moba_connected_reference" in source
    assert "edge-prod" in source
    assert "mobaConnectedLeftDock" in source


def test_gui_profile_tab_label_helper_is_product_specific() -> None:
    source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")

    assert "def profile_tab_label" in source
    assert '"SSH2" if protocol == "SSH" else protocol' in source
    assert 'return f"{protocol} - {profile.name}"' in source
    assert 'return f"{profile.name} [{protocol}]"' in source
    assert "moba_connected_tab_chrome_items" in source
    assert "mobaTabChromeKey" in source
    assert "mobaRightUtilityKey" in source
    assert "mobaSessionEdgeKey" in source
    assert "mobaBottomEdgeKey" in source
    assert "activate_adjacent_tab" in source
    assert "mobaSshBannerTitle" in source
    assert "mobaSshBannerTargetLine" in source
    assert "mobaSshBannerCapabilityKey" in source
    assert "mobaSshBannerFooter" in source
    assert "mobaBannerWidth" in source
    assert "def profile_tab_status" in source
    assert "build_product_workspace_surface_evidence" in source
    assert "mobaRailRole" in source
    assert "MobaRailLabel" in source
    assert "show_moba_sftp_rail" in source


def _complete_contract_evidence(checker, preset_id: str) -> dict[str, list[dict[str, object]]]:
    return {
        "layout_measurements": [
            {
                "id": str(contract["id"]),
                "widget": str(contract["object_name"]),
                "bounds": {"x": 10, "y": 10, "width": 200, "height": 100},
                "passed": True,
            }
            for contract in checker.live_layout_contracts_for_preset(preset_id)
        ],
        "topology_measurements": [
            {
                "id": str(contract["id"]),
                "from": str(contract["from"]),
                "to": str(contract["to"]),
                "relation": str(contract["relation"]),
                "gap": 10,
                "passed": True,
            }
            for contract in checker.live_topology_contracts_for_preset(preset_id)
        ],
    }


def _load_checker():
    path = Path("scripts/check_real_gui_render.py")
    spec = importlib.util.spec_from_file_location("check_real_gui_render_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeTabs:
    def __init__(self, labels: list[str]) -> None:
        self.labels = labels

    def count(self) -> int:
        return len(self.labels)

    def tabText(self, index: int) -> str:
        return self.labels[index]


class _FakeTree:
    def __init__(self, items: list[_FakeTreeItem]) -> None:
        self.items = items

    def topLevelItemCount(self) -> int:
        return len(self.items)

    def topLevelItem(self, index: int) -> _FakeTreeItem:
        return self.items[index]


class _FakeTreeItem:
    def __init__(self, label: str, children: list[_FakeTreeItem] | None = None) -> None:
        self.label = label
        self.children = children or []

    def text(self, _column: int) -> str:
        return self.label

    def childCount(self) -> int:
        return len(self.children)

    def child(self, index: int) -> _FakeTreeItem:
        return self.children[index]
