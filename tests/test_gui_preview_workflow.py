from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from remote_ops_workspace.gui_designs import GUI_DESIGN_PRESETS


def test_gui_preview_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_preview_manifest_tracks_every_gui_design_preset() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))

    assert [item["id"] for item in manifest["presets"]] == [preset.id for preset in GUI_DESIGN_PRESETS]
    assert manifest["preview_size"] == {"width": 1280, "height": 760}
    assert [item["id"] for item in manifest["state_previews"]] == ["mobaxterm-home"]
    assert manifest["state_previews"][0]["preset_id"] == "mobaxterm"
    assert manifest["state_previews"][0]["image"]["path"] == "mobaxterm-home.png"
    mobaxterm = next(item for item in manifest["presets"] if item["id"] == "mobaxterm")
    follow_route = mobaxterm["moba_follow_terminal_folder_control_route"]
    assert follow_route["key"] == "moba-follow-terminal-folder-control-route"
    assert follow_route["source_control_object"] == "mobaFollowTerminalFolder"
    assert follow_route["target_path_object"] == "mobaSftpPath"
    edge_route = mobaxterm["moba_ribbon_edge_action_route"]
    assert edge_route["key"] == "moba-ribbon-edge-action-route"
    assert edge_route["xserver_action_object"] == "mobaXServerAction"
    assert edge_route["xserver_handler"] == "show_moba_x_server_status"
    assert edge_route["exit_action_object"] == "mobaExitAction"
    assert edge_route["exit_handler"] == "close"
    utility_route = mobaxterm["moba_right_utility_action_route"]
    assert utility_route["key"] == "moba-right-utility-action-route"
    assert utility_route["rail_object"] == "mobaRightUtilityRail"
    assert utility_route["action_object"] == "mobaRightUtilityAction"
    assert utility_route["action_keys"] == ["clip", "settings", "tools"]
    assert utility_route["action_handlers"] == [
        "show_moba_clipboard_hints",
        "show_moba_terminal_settings",
        "show_moba_tools_status",
    ]
    securecrt = next(item for item in manifest["presets"] if item["id"] == "securecrt")
    securecrt_sftp_route = securecrt["securecrt_sftp_tab_route"]
    assert securecrt_sftp_route["key"] == "securecrt-sftp-tab-route"
    assert securecrt_sftp_route["workflow_card_key"] == "sftp-tab"
    assert securecrt_sftp_route["status_value"] == "files-prod tab"
    securecrt_browser_route = securecrt["securecrt_sftp_browser_route"]
    assert securecrt_browser_route["key"] == "securecrt-sftp-browser-route"
    assert securecrt_browser_route["sftp_tab_route_key"] == securecrt_sftp_route["key"]
    assert securecrt_browser_route["remote_path"] == "/srv/files"
    assert securecrt_browser_route["toolbar_actions"] == ["upload", "download", "refresh"]
    assert securecrt_browser_route["active_row_name"] == "deploy.log"
    remmina = next(item for item in manifest["presets"] if item["id"] == "remmina")
    screenshot_route = remmina["remmina_screenshot_route"]
    assert screenshot_route["key"] == "remmina-screenshot-capture-route"
    assert screenshot_route["viewer_control_key"] == "screenshot"
    assert screenshot_route["capture_artifact"] == "win-admin-rdp-screenshot.png"
    sftp_route = remmina["remmina_sftp_transfer_route"]
    assert sftp_route["key"] == "remmina-sftp-transfer-route"
    assert sftp_route["selected_profile_key"] == "sftp-ops"
    assert sftp_route["remote_path"] == "/var/log"
    assert sftp_route["toolbar_actions"] == ["upload", "download", "queue"]
    assert sftp_route["active_row_name"] == "app.log"
    termius = next(item for item in manifest["presets"] if item["id"] == "termius")
    port_forward_route = termius["termius_port_forward_route"]
    assert port_forward_route["key"] == "termius-port-forward-route"
    assert port_forward_route["header_chip_key"] == "port-forward-ready"
    assert port_forward_route["identity_field_key"] == "forward"
    assert port_forward_route["forward_value"] == "8080 -> localhost:80"
    snippet_route = termius["termius_snippet_route"]
    assert snippet_route["key"] == "termius-snippet-route"
    assert snippet_route["workflow_card_key"] == "snippet"
    assert snippet_route["identity_field_key"] == "snippet"
    assert snippet_route["snippet_command"] == "row vault status"
    files_route = termius["termius_files_browser_route"]
    assert files_route["key"] == "termius-files-browser-route"
    assert files_route["remote_path"] == "/workspace"
    assert files_route["toolbar_actions"] == ["upload", "download", "sync"]
    assert files_route["active_row_name"] == "deploy.yml"
    mremoteng = next(item for item in manifest["presets"] if item["id"] == "mremoteng")
    inheritance_route = mremoteng["mremoteng_inheritance_route"]
    assert inheritance_route["key"] == "mremoteng-inheritance-route"
    assert inheritance_route["workflow_card_key"] == "inheritance-grid"
    assert inheritance_route["property_row_key"] == "credential"
    assert inheritance_route["inherited_value"] == "operator key reference"


def test_preview_png_dimensions_match_manifest() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))

    for item in [*manifest["presets"], *manifest["state_previews"]]:
        image = item["image"]
        path = checker.PREVIEW_DIR / image["path"]
        assert checker.png_dimensions(path) == (image["width"], image["height"])


def test_preview_gallery_links_all_preset_images() -> None:
    checker = _load_checker()
    manifest = checker.json.loads((checker.PREVIEW_DIR / "preview-manifest.json").read_text(encoding="utf-8"))
    gallery = (checker.PREVIEW_DIR / "index.html").read_text(encoding="utf-8")

    assert "all-gui-designs-contact-sheet.png" in gallery
    for item in [*manifest["presets"], *manifest["state_previews"]]:
        assert item["label"] in gallery
        assert item["image"]["path"] in gallery


def test_renderer_list_mode_does_not_require_pillow() -> None:
    renderer = _load_renderer()

    assert renderer.main(["--list"]) == 0


def test_gui_visual_metrics_checker_passes_current_tree() -> None:
    checker = _load_visual_metrics_checker()

    assert checker.main() == 0


def test_gui_visual_metrics_cover_every_preview_preset() -> None:
    checker = _load_visual_metrics_checker()
    metrics = checker.load_json(checker.METRICS_PATH)
    manifest = checker.load_json(checker.PREVIEW_MANIFEST_PATH)

    assert set(metrics["presets"]) == {item["id"] for item in manifest["presets"]}
    assert set(metrics["state_previews"]) == {item["id"] for item in manifest["state_previews"]}
    assert metrics["preview_size"] == [1280, 760]
    assert checker.count_regions(metrics) == 118
    assert checker.count_color_anchors(metrics) == 96
    assert checker.count_line_anchors(metrics) == 72
    assert checker.count_topology_contracts(metrics) == 83
    assert len(metrics["presets"]["mobaxterm"]["regions"]) == 33
    assert len(metrics["presets"]["mobaxterm"]["line_anchors"]) == 16
    assert len(metrics["state_previews"]["mobaxterm-home"]["regions"]) == 13
    assert len(metrics["state_previews"]["mobaxterm-home"]["color_anchors"]) == 9
    assert len(metrics["state_previews"]["mobaxterm-home"]["line_anchors"]) == 8
    assert len(metrics["state_previews"]["mobaxterm-home"]["topology"]) == 6
    assert len(metrics["presets"]["securecrt"]["regions"]) == 18
    assert len(metrics["presets"]["securecrt"]["line_anchors"]) == 13
    assert len(metrics["presets"]["securecrt"]["topology"]) == 17
    assert len(metrics["presets"]["termius"]["regions"]) == 16
    assert len(metrics["presets"]["termius"]["line_anchors"]) == 11
    assert len(metrics["presets"]["termius"]["topology"]) == 13
    assert len(metrics["presets"]["remmina"]["regions"]) == 17
    assert len(metrics["presets"]["remmina"]["line_anchors"]) == 11
    assert len(metrics["presets"]["remmina"]["topology"]) == 14
    assert len(metrics["presets"]["mremoteng"]["regions"]) == 17
    assert len(metrics["presets"]["mremoteng"]["line_anchors"]) == 13
    assert len(metrics["presets"]["mremoteng"]["topology"]) == 14
    assert len(metrics["presets"]["mobaxterm"]["topology"]) == 19
    assert len(metrics["presets"]["mobaxterm"]["color_anchors"]) == 23
    assert len(metrics["presets"]["securecrt"]["color_anchors"]) == 19
    assert len(metrics["presets"]["termius"]["color_anchors"]) == 14
    assert len(metrics["presets"]["remmina"]["color_anchors"]) == 13
    assert len(metrics["presets"]["mremoteng"]["color_anchors"]) == 18
    mobaxterm_region_ids = {item["id"] for item in metrics["presets"]["mobaxterm"]["regions"]}
    assert {
        "titlebar-window-controls",
        "ribbon-right-actions",
        "session-edge-controls",
        "sftp-toolbar-action-strip",
        "sftp-file-row-density",
        "sftp-selected-parent-row",
        "monitoring-control-row",
        "follow-folder-control-row",
        "right-utility-action-stack",
        "telemetry-cpu-cell",
        "bottom-edge-controls",
    } <= mobaxterm_region_ids
    mobaxterm_anchor_ids = {item["id"] for item in metrics["presets"]["mobaxterm"]["color_anchors"]}
    assert {
        "titlebar-close-control",
        "ribbon-xserver-action",
        "ribbon-exit-action",
        "session-edge-settings-control",
        "sftp-toolbar-ascii-action",
        "sftp-parent-row-icon",
        "sftp-parent-row-fill",
        "sftp-parent-row-outline",
        "monitoring-control-icon",
        "follow-folder-checkmark",
        "telemetry-cpu-icon",
        "bottom-edge-next-control",
    } <= mobaxterm_anchor_ids
    mobaxterm_topology_ids = {item["id"] for item in metrics["presets"]["mobaxterm"]["topology"]}
    assert {
        "titlebar-controls-inside-titlebar",
        "ribbon-right-actions-inside-ribbon",
        "session-edge-controls-above-right-utility-rail",
        "right-utility-stack-inside-right-utility-rail",
        "sftp-toolbar-actions-inside-connected-dock",
        "sftp-file-row-inside-connected-dock",
        "sftp-selected-parent-row-inside-connected-dock",
        "monitoring-control-row-inside-monitoring-dock",
        "follow-folder-control-row-inside-monitoring-dock",
        "telemetry-cpu-cell-inside-bottom-telemetry",
        "bottom-edge-controls-below-telemetry",
    } <= mobaxterm_topology_ids
    securecrt_region_ids = {item["id"] for item in metrics["presets"]["securecrt"]["regions"]}
    assert {
        "session-manager-filter-focus",
        "session-manager-tree-root",
        "session-manager-folder-stack",
        "session-manager-tree-selected-row",
        "session-manager-tree-connectors",
        "securecrt-active-tab",
        "command-window-input-focus",
        "command-window-send-control",
    } <= securecrt_region_ids
    securecrt_anchor_ids = {item["id"] for item in metrics["presets"]["securecrt"]["color_anchors"]}
    assert {
        "session-filter-focus-outline",
        "active-tab-focus-outline",
        "session-database-folder",
        "session-tree-local-folder",
        "session-tree-selected-fill",
        "session-tree-selected-accent",
        "session-tree-connector",
        "command-window-input-focus-outline",
        "command-window-send-fill",
    } <= securecrt_anchor_ids
    securecrt_line_ids = {item["id"] for item in metrics["presets"]["securecrt"]["line_anchors"]}
    assert {
        "session-filter-focus-outline-top",
        "active-tab-focus-outline-top",
        "command-input-focus-top-rule",
        "command-send-fill-rule",
    } <= securecrt_line_ids
    securecrt_topology_ids = {item["id"] for item in metrics["presets"]["securecrt"]["topology"]}
    assert {
        "session-filter-focus-inside-session-manager",
        "session-tree-root-inside-session-manager",
        "session-folder-stack-inside-session-manager",
        "selected-session-row-inside-session-manager",
        "session-tree-connectors-inside-session-manager",
        "selected-session-row-below-tree-root",
        "active-tab-inside-terminal-surface",
        "command-input-focus-inside-command-window",
        "send-control-right-of-command-input",
    } <= securecrt_topology_ids
    termius_region_ids = {item["id"] for item in metrics["presets"]["termius"]["regions"]}
    assert {
        "hosts-search-focus",
        "selected-host-row",
        "active-west-tab",
        "host-identity-sync-control",
        "workflow-card-action-row",
    } <= termius_region_ids
    termius_anchor_ids = {item["id"] for item in metrics["presets"]["termius"]["color_anchors"]}
    assert {
        "host-search-focus-outline",
        "selected-host-row-fill",
        "vault-toolbar-checked-border",
        "identity-sync-control-fill",
        "workflow-vault-card-icon",
    } <= termius_anchor_ids
    termius_line_ids = {item["id"] for item in metrics["presets"]["termius"]["line_anchors"]}
    assert {
        "host-search-focus-outline-top",
        "active-west-tab-focus-outline-top",
        "vault-toolbar-checked-outline-top",
        "identity-sync-control-fill-top",
    } <= termius_line_ids
    termius_topology_ids = {item["id"] for item in metrics["presets"]["termius"]["topology"]}
    assert {
        "host-search-focus-inside-hosts-sidebar",
        "selected-host-row-inside-hosts-sidebar",
        "active-west-tab-inside-west-tab-rail",
        "identity-sync-control-inside-host-identity-strip",
        "workflow-action-row-inside-host-workspace",
    } <= termius_topology_ids
    remmina_region_ids = {item["id"] for item in metrics["presets"]["remmina"]["regions"]}
    assert {
        "profile-filter-focus",
        "connection-list-selected-row",
        "protocol-tree-selected-row",
        "active-viewer-tab",
        "transfer-toolbar-checked",
        "viewer-control-glyph-cluster",
    } <= remmina_region_ids
    remmina_anchor_ids = {item["id"] for item in metrics["presets"]["remmina"]["color_anchors"]}
    assert {
        "profile-filter-focus-outline",
        "connection-list-selected-fill",
        "protocol-tree-selected-fill",
        "transfer-toolbar-checked-outline",
        "viewer-fit-control-glyph",
        "viewer-fullscreen-control-glyph",
    } <= remmina_anchor_ids
    remmina_line_ids = {item["id"] for item in metrics["presets"]["remmina"]["line_anchors"]}
    assert {
        "profile-filter-focus-left-rule",
        "active-viewer-tab-focus-top",
        "transfer-toolbar-checked-top",
        "viewer-fit-glyph-top",
    } <= remmina_line_ids
    remmina_topology_ids = {item["id"] for item in metrics["presets"]["remmina"]["topology"]}
    assert {
        "transfer-toolbar-checked-inside-toolbar",
        "profile-filter-focus-inside-profile-list",
        "connection-list-selected-inside-profile-list",
        "protocol-tree-selected-inside-profiles",
        "active-viewer-tab-above-remote-viewer",
        "viewer-control-glyphs-inside-strip",
    } <= remmina_topology_ids
    mremoteng_region_ids = {item["id"] for item in metrics["presets"]["mremoteng"]["regions"]}
    assert {
        "selected-connection-tree-row",
        "top-toolbar-active-open",
        "top-toolbar-disabled-delete",
        "top-toolbar-checked-external",
        "active-document-tab",
        "document-external-tool-checked",
        "document-filter-focus",
        "rdp-control-glyph-cluster",
        "property-grid-inherited-rows",
    } <= mremoteng_region_ids
    mremoteng_anchor_ids = {item["id"] for item in metrics["presets"]["mremoteng"]["color_anchors"]}
    assert {
        "top-open-active-outline",
        "top-external-checked-outline",
        "top-delete-disabled-fill",
        "active-document-tab-focus-outline",
        "selected-tree-row-fill",
        "document-external-tool-checked-outline",
        "document-filter-focus-outline",
        "rdp-fit-glyph",
        "rdp-fullscreen-glyph",
        "property-grid-inherited-fill",
    } <= mremoteng_anchor_ids
    mremoteng_line_ids = {item["id"] for item in metrics["presets"]["mremoteng"]["line_anchors"]}
    assert {
        "top-open-active-top",
        "top-external-checked-top",
        "active-document-tab-focus-top",
        "document-external-tool-checked-top",
        "document-filter-focus-top",
        "rdp-fit-glyph-top",
    } <= mremoteng_line_ids
    mremoteng_topology_ids = {item["id"] for item in metrics["presets"]["mremoteng"]["topology"]}
    assert {
        "top-open-active-inside-toolbar",
        "top-delete-disabled-inside-toolbar",
        "top-external-checked-inside-toolbar",
        "selected-tree-row-inside-connections-tree",
        "active-document-tab-inside-document-workspace",
        "document-external-tool-checked-inside-controls",
        "document-filter-focus-inside-controls",
        "rdp-glyphs-inside-document-workspace",
        "inherited-rows-inside-config-inheritance",
    } <= mremoteng_topology_ids


def test_gui_visual_metrics_reject_visual_anchor_drift() -> None:
    checker = _load_visual_metrics_checker()
    image = checker.read_png_rgb(checker.PREVIEW_DIR / "mobaxterm.png")
    anchor = {
        "id": "broken-anchor",
        "point": [10, 110],
        "rgb_min": [250, 250, 250],
        "rgb_max": [255, 255, 255],
    }

    assert checker.check_color_anchor("mobaxterm", image, anchor)


def test_gui_visual_metrics_reject_line_anchor_drift() -> None:
    checker = _load_visual_metrics_checker()
    image = checker.read_png_rgb(checker.PREVIEW_DIR / "mobaxterm.png")
    anchor = {
        "id": "broken-line",
        "from": [4, 110],
        "to": [386, 110],
        "rgb_min": [250, 250, 250],
        "rgb_max": [255, 255, 255],
        "min_match_ratio": 0.95,
    }

    assert checker.check_line_anchor("mobaxterm", image, anchor)


def test_gui_visual_metrics_reject_topology_drift() -> None:
    checker = _load_visual_metrics_checker()
    metrics = checker.load_json(checker.METRICS_PATH)
    contract = {
        "id": "broken-topology",
        "from": "connected-left-dock",
        "relation": "left_of",
        "to": "connected-terminal",
        "min_gap": 40,
    }

    assert checker.check_topology_contract("mobaxterm", metrics["presets"]["mobaxterm"], contract)


def _load_checker():
    path = Path("scripts/check_gui_design_previews.py")
    spec = importlib.util.spec_from_file_location("check_gui_design_previews_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_visual_metrics_checker():
    path = Path("scripts/check_gui_visual_metrics.py")
    spec = importlib.util.spec_from_file_location("check_gui_visual_metrics_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_renderer():
    path = Path("scripts/render_gui_design_previews.py")
    spec = importlib.util.spec_from_file_location("render_gui_design_previews_script_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
