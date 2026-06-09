from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_real_gui_render_checker_passes_or_verifies_fail_closed_path(tmp_path: Path) -> None:
    checker = _load_checker()

    errors, messages = checker.check_real_gui_render(["native"], out_dir=tmp_path)

    assert errors == []
    assert any("captured" in message or "fail-closed" in message for message in messages)


def test_real_gui_render_main_passes_current_environment() -> None:
    checker = _load_checker()

    assert checker.main([]) == 0


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


def test_real_gui_render_manifest_contract_names_required_widgets() -> None:
    checker = _load_checker()

    assert checker.MANIFEST_NAME == "real-gui-render-manifest.json"
    assert checker.REQUIRED_WIDGETS["designSelect"] == "view preset selector"
    assert checker.REQUIRED_WIDGETS["layoutToolbar"] == "layout toolbar"
    assert checker.REQUIRED_WIDGETS["activityLog"] == "activity log"
    assert checker.COMMON_REQUIRED_WIDGETS["productWorkflowEvidence"] == "product workflow evidence strip"
    assert checker.COMMON_REQUIRED_WIDGETS["productWorkspaceSurface"] == "product workspace evidence surface"
    assert checker.MOBA_CONNECTED_REQUIRED_WIDGETS["mobaConnectedLeftDock"] == "Moba connected SFTP/monitoring dock"
    assert checker.PRODUCT_STYLE_PRESETS == {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
    assert checker.EXPECTED_MOBA_RAIL_ROLES == {"collapse", "sessions", "favorites", "tools", "macros", "sftp"}
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
    assert checker.EXPECTED_SECURECRT_TOP_TOOLBAR_KEYS[:5] == [
        "refresh",
        "new",
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
    assert checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS == [
        "web-console",
        "spacer",
        "last-login",
        "prompt-ready",
    ]
    assert checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_TONES == [
        "info",
        "spacer",
        "info",
        "command",
    ]
    assert "terminal" in checker.EXPECTED_MOBA_SFTP_ACTION_KEYS
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
    assert checker.EXPECTED_MREMOTENG_TOP_TOOLBAR_KEYS[:6] == [
        "refresh",
        "new",
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


def test_real_gui_render_defaults_to_every_preset() -> None:
    checker = _load_checker()

    assert checker.select_presets(None) == [preset.id for preset in checker.GUI_DESIGN_PRESETS]


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
    assert checker.required_widgets_for_preset("mremoteng")["mRemoteNgMenuBar"] == "mRemoteNG top menu bar"
    assert checker.required_widgets_for_preset("mremoteng")["mRemoteNgPropertyGrid"] == (
        "mRemoteNG property inheritance grid"
    )
    assert moba_present_widgets == {}
    assert moba_widgets["mobaQuickConnectChrome"] == "Moba quick connect chrome"
    assert moba_widgets["quickConnect"] == "Moba quick connect field"
    assert moba_widgets["mobaRibbonButton"] == "Moba ribbon action"
    assert moba_widgets["mobaConnectedLeftDock"] == "Moba connected SFTP/monitoring dock"
    assert moba_widgets["mobaTelemetryBar"] == "Moba bottom telemetry bar"


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
    assert "Options" in checker.required_securecrt_top_chrome_texts()
    assert "New Session" in checker.required_securecrt_top_chrome_texts()
    assert "Connections" in checker.required_mremoteng_top_chrome_texts()
    assert "New Conn" in checker.required_mremoteng_top_chrome_texts()
    assert "Forward: 8080 -> localhost:80" in checker.required_termius_host_identity_texts()
    assert "Identity: prod-ed25519" in checker.required_termius_host_identity_texts()
    assert "check_live_reference_state" in source
    assert "check_live_securecrt_session_status_strip" in source
    assert "check_live_termius_host_identity_strip" in source
    assert "check_live_securecrt_command_window" in source
    assert "check_live_securecrt_top_chrome" in source
    assert "check_live_mremoteng_top_chrome" in source
    assert "gui_design_reference_state" in source


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

    moba = summaries["mobaxterm"]
    assert "mobaQuickConnectChrome" in moba["required_widgets"]
    assert "mobaConnectedLeftDock" in moba["required_widgets"]
    assert "mobaSftpFileTable" in moba["required_widgets"]
    assert "mobaSessionEdgeControls" in moba["required_widgets"]
    assert "mobaRightUtilityRail" in moba["required_widgets"]
    assert "mobaBottomEdgeControls" in moba["required_widgets"]
    assert moba["present_widgets"] == {}
    assert moba["reference_profile"] == "edge-prod"
    assert moba["expected_reference_tab_label"] == "edge-prod.example.invalid (operator)"
    assert {
        "connected-left-dock",
        "sftp-file-table",
        "ssh-banner-workspace",
        "session-edge-controls",
        "bottom-edge-controls",
    } <= set(moba["layout_contract_ids"])
    assert {"dock-left-of-ssh-banner", "sftp-table-inside-dock"} <= set(moba["topology_contract_ids"])
    assert "moba-rail-roles" in moba["contract_checks"]
    assert "moba-rail-labels" in moba["contract_checks"]
    assert "moba-home-welcome" in moba["contract_checks"]
    assert "titlebar-chrome" in moba["contract_checks"]
    assert "top-menu-chrome" in moba["contract_checks"]
    assert "quick-connect-chrome" in moba["contract_checks"]
    assert "quick-connect-suggestions" in moba["contract_checks"]
    assert "connected-quick-connect-idle" in moba["contract_checks"]
    assert "connected-tab-chrome" in moba["contract_checks"]
    assert "session-edge-controls" in moba["contract_checks"]
    assert "right-utility-rail" in moba["contract_checks"]
    assert "ssh-banner-chrome" in moba["contract_checks"]
    assert "terminal-transcript" in moba["contract_checks"]
    assert "sftp-toolbar-groups" in moba["contract_checks"]
    assert "sftp-dock-chrome" in moba["contract_checks"]
    assert "sftp-dock-density" in moba["contract_checks"]
    assert "sftp-browser-chrome" in moba["contract_checks"]
    assert "bottom-status-chrome" in moba["contract_checks"]
    assert "bottom-edge-controls" in moba["contract_checks"]
    assert "live-topology" in moba["contract_checks"]
    assert "remote-monitoring-dock" in moba["contract_checks"]
    assert "moba-monitoring-controls" in moba["contract_checks"]
    assert "terminal" in moba["expected_moba_sftp_action_keys"]
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
    assert "network" in moba["expected_moba_monitoring_metric_keys"]
    assert moba["expected_moba_remote_monitoring_dock_chrome"] == {
        "title_control_key": "remote-monitoring",
        "follow_control_key": "follow-terminal-folder",
        "telemetry_surface": "bottom-telemetry-bar",
        "visible_metric_keys": [],
        "refresh_seconds": 5,
        "compact": True,
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
            "check_size": 0,
            "row_height": 22,
        },
        {
            "key": "follow-terminal-folder",
            "anchor_x": 42,
            "static_y": 76,
            "icon_x": 60,
            "icon_size": 16,
            "label_x": 80,
            "check_size": 10,
            "row_height": 19,
        },
    ]
    assert "sftp-ready" in moba["expected_moba_status_keys"]
    assert moba["expected_moba_status_chrome"]["notice"] == "REMOTE OPS WORKSPACE"
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
    assert moba["expected_moba_titlebar_chrome"] == {
        "icon_key": "moba-window",
        "static_height": 22,
        "icon_left": 5,
        "icon_size": 12,
        "title_left": 24,
        "control_keys": ["minimize", "maximize", "close"],
        "control_width": 24,
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
        "static_width": 390,
        "detail_separator": "    ",
    }
    assert moba["expected_moba_home_welcome_chrome"] == {
        "title": "Remote Ops Workspace",
        "subtitle": "Moba-style SSH client, SFTP browser and monitoring tools",
        "icon_key": "session",
        "primary_action_icon_key": "session",
        "secondary_action_icon_key": "tunneling",
        "search_width": 405,
        "action_spacing": 96,
        "recent_title": "Recent sessions",
        "surface_width": 640,
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
    assert moba["expected_moba_sftp_dock_layout"] == {
        "inner_margin": 6,
        "toolbar_height": 26,
        "toolbar_icon_size": 16,
        "toolbar_icon_step": 24,
        "toolbar_separator_width": 7,
        "path_height": 24,
        "table_header_height": 24,
        "file_row_height": 21,
        "static_max_rows": 9,
        "monitoring_height": 116,
        "monitoring_divider_offset": 14,
    }
    assert [line["key"] for line in moba["expected_moba_terminal_transcript"]] == (
        checker.EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS
    )
    assert moba["expected_moba_terminal_transcript"][0]["text"] == (
        "Web console: https://edge-prod.example.invalid:9090/ or https://192.0.2.10:9090/"
    )
    assert moba["expected_moba_terminal_transcript"][3]["text"] == "[operator@edge-prod ~]$ "
    assert [cell["key"] for cell in moba["expected_moba_telemetry_cells"]] == (
        checker.EXPECTED_MOBA_TELEMETRY_CELL_KEYS
    )
    assert [cell["width"] for cell in moba["expected_moba_telemetry_cells"]] == (
        checker.EXPECTED_MOBA_TELEMETRY_CELL_WIDTHS
    )
    assert [cell["icon_size"] for cell in moba["expected_moba_telemetry_cells"]] == [12] * 8
    assert moba["expected_moba_telemetry_cells"][1]["icon_accent"] == "#f4c430"
    assert moba["expected_moba_telemetry_cells"][6]["display_text"] == "Connections: 1 (port 22)"
    assert moba["expected_moba_tab_chrome_keys"] == ["active-session", "home", "new-session"]
    assert moba["expected_moba_static_tab_chrome_keys"] == [
        "active-session",
        "home",
        "inactive-session",
        "new-session",
    ]
    assert moba["expected_moba_right_utility_keys"] == ["clip", "settings", "tools"]
    assert "right-utility-rail-geometry" in moba["contract_checks"]
    assert moba["expected_moba_right_utility_actions"] == [
        {
            "key": "clip",
            "icon_key": "clip",
            "label": "Clipboard and transfer hints",
            "static_x": 7,
            "static_y": 13,
            "static_size": 16,
            "live_icon_size": 18,
            "button_size": 22,
            "render_source": "generated-pixmap",
        },
        {
            "key": "settings",
            "icon_key": "gear",
            "label": "Terminal settings",
            "static_x": 7,
            "static_y": 49,
            "static_size": 16,
            "live_icon_size": 18,
            "button_size": 22,
            "render_source": "generated-pixmap",
        },
        {
            "key": "tools",
            "icon_key": "spark",
            "label": "Terminal tools",
            "static_x": 7,
            "static_y": 85,
            "static_size": 16,
            "live_icon_size": 18,
            "button_size": 22,
            "render_source": "generated-pixmap",
        },
    ]
    assert moba["expected_moba_session_edge_actions"] == [
        {"key": "attachment", "icon_key": "clip", "label": "Session attachment", "static_y": 112},
        {"key": "settings", "icon_key": "gear", "label": "Session settings", "static_y": 130},
    ]
    assert moba["expected_moba_ssh_banner_chrome"] == {
        "title": "Remote Ops Workspace Personal Edition v1.0",
        "subtitle": "(SSH client, SFTP browser and remote tools)",
        "heading_prefix": "* ",
        "heading_suffix": " *",
        "target_intro": "SSH session to",
        "capability_label_width": 15,
        "footer_prefix": "For more info, ctrl+click on",
        "static_width": 570,
        "static_height": 166,
    }
    assert moba["expected_moba_ssh_banner_capability_card"]["target"] == "edge-prod.example.invalid"
    assert [row["key"] for row in moba["expected_moba_ssh_banner_capability_card"]["capabilities"]] == [
        "direct-ssh",
        "ssh-compression",
        "ssh-browser",
        "x11-forwarding",
    ]
    assert moba["expected_moba_ssh_banner_capability_card"]["footer_links"] == ["help", "website"]
    assert "ssh-banner-capability-card" in moba["contract_checks"]
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
    assert "securecrt-tree-icons" in securecrt["contract_checks"]
    assert "securecrt-session-status-strip" in securecrt["contract_checks"]
    assert "securecrt-session-status-geometry" in securecrt["contract_checks"]
    assert "securecrt-command-window" in securecrt["contract_checks"]
    assert "securecrt-command-window-geometry" in securecrt["contract_checks"]
    assert "live-topology" in securecrt["contract_checks"]
    assert "active-tab: edge-prod (SSH2)" in securecrt["expected_reference_state_texts"]
    assert securecrt["expected_reference_status_segments"] == ["SSH2", "Session Manager", "2 active tabs"]
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
    assert securecrt["expected_securecrt_top_chrome"]["toolbar_actions"][5] == {
        "key": "files",
        "icon_key": "sftp",
        "label": "SFTP",
        "static_x": 424,
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
    assert remmina["expected_product_tree_icons"][:3] == [
        {"label": "Profile Groups", "icon_key": "folder", "row_kind": "root", "static_size": 16},
        {"label": "Group: RDP", "icon_key": "folder", "row_kind": "group", "static_size": 14},
        {"label": "RDP - win-admin", "icon_key": "rdp", "row_kind": "profile", "static_size": 14},
    ]
    assert remmina["required_widgets"]["remminaProfileListChrome"] == "Remmina profile list chrome"
    assert "profile-list-chrome" in remmina["layout_contract_ids"]
    assert remmina["expected_reference_tab_label"] == "RDP - win-admin"
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

    mremoteng = summaries["mremoteng"]
    assert "mremoteng-tree-icons" in mremoteng["contract_checks"]
    assert "mremoteng-top-chrome" in mremoteng["contract_checks"]
    assert "mremoteng-document-controls" in mremoteng["contract_checks"]
    assert "mremoteng-document-control-geometry" in mremoteng["contract_checks"]
    assert "mremoteng-property-grid" in mremoteng["contract_checks"]
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
    assert [item["label"] for item in mremoteng["expected_mremoteng_top_chrome"]["menu_items"]] == [
        "File",
        "View",
        "Connections",
        "Tools",
        "Window",
        "Help",
    ]
    assert mremoteng["expected_mremoteng_top_chrome"]["toolbar_height"] == 50
    assert mremoteng["expected_mremoteng_top_chrome"]["toolbar_actions"][5] == {
        "key": "files",
        "icon_key": "external-tool",
        "label": "External",
        "static_x": 368,
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
        "mobaSessionEdgeControls",
        "mobaBottomEdgeControls",
        "mobaRightUtilityRail",
        "mobaSftpFileTable",
        "mobaSshBanner",
        "mobaTelemetryBar",
    } <= moba_objects
    mremoteng_objects = {str(contract["object_name"]) for contract in checker.live_layout_contracts_for_preset("mremoteng")}
    assert "mRemoteNgPropertyGrid" in mremoteng_objects
    assert "mRemoteNgDocumentFilter" in mremoteng_objects


def test_real_gui_render_tracks_live_topology_contracts_for_product_presets() -> None:
    checker = _load_checker()

    assert set(checker.LIVE_TOPOLOGY_CONTRACTS) == checker.PRODUCT_STYLE_PRESETS
    for preset_id in checker.PRODUCT_STYLE_PRESETS:
        contracts = checker.live_topology_contracts_for_preset(preset_id)
        expected_count = 6 if preset_id in {"mobaxterm", "mremoteng"} else 5
        assert len(contracts) == expected_count
        assert all({"id", "from", "relation", "to"} <= set(contract) for contract in contracts)
    moba_ids = {str(contract["id"]) for contract in checker.live_topology_contracts_for_preset("mobaxterm")}
    assert {
        "rail-left-of-dock",
        "dock-left-of-ssh-banner",
        "ssh-banner-left-of-right-utility",
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
