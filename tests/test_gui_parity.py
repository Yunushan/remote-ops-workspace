from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_gui_parity_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_gui_parity_checker_json_mode_outputs_report(capsys) -> None:
    checker = _load_checker()

    assert checker.main(["--json"]) == 0
    output = capsys.readouterr().out
    report = checker.json.loads(output)

    assert report["schema_version"] == 1
    assert report["overall"]["current_percent"] == 100.0
    assert report["overall"]["gap_percent"] == 0.0
    assert report["overall"]["dimension_percent"] == 100.0
    assert report["overall"]["dimension_gap_percent"] == 0.0


def test_gui_parity_tracks_all_product_style_presets() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    assert set(criteria["presets"]) == checker.PRODUCT_STYLE_PRESETS
    assert criteria["target_percent"] == 100
    assert checker.count_requirements(criteria) >= 78


def test_gui_parity_requires_multi_file_requirement_evidence() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    assert checker.MIN_EVIDENCE_FILES_PER_REQUIREMENT == 2
    for preset_data in criteria["presets"].values():
        for requirement in preset_data["requirements"]:
            assert len(requirement["source_tokens"]) >= checker.MIN_EVIDENCE_FILES_PER_REQUIREMENT


def test_gui_parity_requires_non_package_requirement_evidence() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    assert checker.PACKAGE_SOURCE_PREFIX == "src/remote_ops_workspace/"
    for preset_data in criteria["presets"].values():
        for requirement in preset_data["requirements"]:
            assert checker.has_non_package_evidence_source(requirement["source_tokens"])


def test_gui_parity_scans_gui_evidence_files_for_user_specific_samples() -> None:
    checker = _load_checker()

    scanned = set(checker.GUI_PRIVACY_EVIDENCE_PATHS)
    assert "configs/gui_visual_metrics.json" in scanned
    assert "docs/GUI_DESIGN.md" in scanned
    assert "scripts/render_gui_design_previews.py" in scanned
    assert "scripts/check_real_gui_render.py" in scanned
    assert "scripts/check_gui_visual_metrics.py" in scanned


def test_gui_parity_rejects_user_specific_tokens_in_gui_evidence_files(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    bad_file = tmp_path / "bad-gui-evidence.txt"
    bad_file.write_text(f"sample host: {'yu' + 'nus'}\n", encoding="utf-8")
    monkeypatch.setattr(checker, "GUI_PRIVACY_EVIDENCE_PATHS", (bad_file,))

    errors = checker.check_no_user_specific_samples(criteria)

    assert errors == [f"{bad_file.as_posix()} must not include user-specific sample token: yunus"]


def test_gui_parity_rejects_single_file_requirement_evidence() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    broken = checker.json.loads(checker.json.dumps(criteria))
    broken["presets"]["securecrt"]["requirements"][0]["source_tokens"] = {
        "src/remote_ops_workspace/gui_designs.py": ["id=\"securecrt\""],
    }

    assert checker.check_criteria_shape(broken)
    assert not checker.requirement_satisfied(broken["presets"]["securecrt"]["requirements"][0])


def test_gui_parity_rejects_package_only_requirement_evidence() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    broken = checker.json.loads(checker.json.dumps(criteria))
    broken["presets"]["securecrt"]["requirements"][0]["source_tokens"] = {
        "src/remote_ops_workspace/gui_designs.py": ["id=\"securecrt\""],
        "src/remote_ops_workspace/gui.py": ["productWorkspaceSurface"],
    }

    assert checker.check_criteria_shape(broken)
    assert not checker.requirement_satisfied(broken["presets"]["securecrt"]["requirements"][0])


def test_gui_parity_tracks_required_objective_dimensions() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    report = checker.gui_parity_report(criteria)
    required_dimensions = [
        "layout",
        "navigation",
        "panes",
        "tabs",
        "sidebars",
        "toolbars",
        "session_trees",
        "connected_session_behavior",
        "file_monitoring_panels",
        "status_bars",
        "density",
        "spacing",
        "interaction_states",
    ]

    assert criteria["required_dimensions"] == required_dimensions
    assert report["required_dimensions"] == required_dimensions
    assert report["overall"]["dimensions_met"] == report["overall"]["dimension_count"]
    assert report["overall"]["dimension_count"] == len(required_dimensions) * len(checker.PRODUCT_STYLE_PRESETS)
    for preset_data in criteria["presets"].values():
        assert set(preset_data["dimension_coverage"]) == set(required_dimensions)
    for row in report["presets"]:
        assert row["dimension_percent"] == row["target_percent"]
        assert row["dimension_gap_percent"] == 0.0
        assert row["dimensions_met"] == row["dimension_count"] == len(required_dimensions)


def test_gui_parity_report_scores_each_product_style_preset() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    report = checker.gui_parity_report(criteria)

    assert report["target_percent"] == 100.0
    assert report["overall"]["current_percent"] == 100.0
    assert report["overall"]["gap_percent"] == 0.0
    assert report["overall"]["dimension_percent"] == 100.0
    assert report["overall"]["dimension_gap_percent"] == 0.0
    assert {row["preset_id"] for row in report["presets"]} == checker.PRODUCT_STYLE_PRESETS
    for row in report["presets"]:
        assert row["current_percent"] == row["target_percent"]
        assert row["gap_percent"] == 0.0
        assert row["requirements_met"] == row["requirement_count"]
        assert row["dimension_percent"] == row["target_percent"]
        assert row["dimension_gap_percent"] == 0.0
        assert row["dimensions_met"] == row["dimension_count"]


def test_gui_parity_report_fails_when_requirement_evidence_is_missing() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    broken = checker.json.loads(checker.json.dumps(criteria))
    broken["presets"]["securecrt"]["requirements"][0]["source_tokens"] = {
        "missing.py": ["missing-token"],
    }

    report = checker.gui_parity_report(broken)
    securecrt = next(row for row in report["presets"] if row["preset_id"] == "securecrt")

    assert securecrt["current_percent"] < 100.0
    assert securecrt["dimension_percent"] < 100.0
    assert checker.check_parity_target(broken)


def test_gui_parity_mobaxterm_connected_reference_is_explicit() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement_ids = {item["id"] for item in moba["requirements"]}

    assert "connected-session MobaXterm-style reference screenshot" in moba["reference_basis"][0]
    assert "moba.titlebar-chrome" in requirement_ids
    assert "moba.quick-connect-chrome" in requirement_ids
    assert "moba.quick-connect-suggestions" in requirement_ids
    assert "moba.connected-quick-connect-idle" in requirement_ids
    assert "moba.home-welcome-surface" in requirement_ids
    assert "moba.connected-left-dock" in requirement_ids
    assert "moba.live-dock-switch" in requirement_ids
    assert "moba.top-menu-chrome" in requirement_ids
    assert "moba.ribbon-pictograms" in requirement_ids
    assert "moba.sftp-glyphs" in requirement_ids
    assert "moba.sftp-dock-chrome" in requirement_ids
    assert "moba.sftp-toolbar-groups" in requirement_ids
    assert "moba.sftp-dock-density" in requirement_ids
    assert "moba.sftp-browser-chrome" in requirement_ids
    assert "moba.remote-monitoring" in requirement_ids
    assert "moba.remote-monitoring-compact-dock" in requirement_ids
    assert "moba.monitoring-controls" in requirement_ids
    assert "moba.bottom-telemetry" in requirement_ids
    assert "moba.bottom-status-chrome" in requirement_ids
    assert "moba.bottom-edge-controls" in requirement_ids
    assert "moba.connected-session-chrome" in requirement_ids
    assert "moba.connected-tab-chrome" in requirement_ids
    assert "moba.session-edge-controls" in requirement_ids
    assert "moba.right-utility-rail" in requirement_ids
    assert "moba.ssh-banner-chrome" in requirement_ids
    assert "moba.terminal-transcript" in requirement_ids
    assert "moba.rail-section-labels" in requirement_ids
    assert "moba.reference-line-anchors" in requirement_ids
    assert "moba.reference-topology" in requirement_ids
    assert "moba.connected-tab-chrome" in moba["dimension_coverage"]["tabs"]
    assert "moba.titlebar-chrome" in moba["dimension_coverage"]["layout"]
    assert "moba.titlebar-chrome" in moba["dimension_coverage"]["navigation"]
    assert "moba.titlebar-chrome" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["layout"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["navigation"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["sidebars"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["density"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["spacing"]
    assert "moba.quick-connect-chrome" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["layout"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["navigation"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["sidebars"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["density"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["spacing"]
    assert "moba.quick-connect-suggestions" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["layout"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["navigation"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["sidebars"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["density"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["spacing"]
    assert "moba.connected-quick-connect-idle" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["layout"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["navigation"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["tabs"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["density"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["spacing"]
    assert "moba.home-welcome-surface" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.top-menu-chrome" in moba["dimension_coverage"]["toolbars"]
    assert "moba.top-menu-chrome" in moba["dimension_coverage"]["navigation"]
    assert "moba.right-utility-rail" in moba["dimension_coverage"]["layout"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["layout"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["navigation"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["navigation"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["tabs"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["tabs"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["density"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["density"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["spacing"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["spacing"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.ssh-banner-chrome" in moba["dimension_coverage"]["panes"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["panes"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["density"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["spacing"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.terminal-transcript" in moba["dimension_coverage"]["panes"]
    assert "moba.terminal-transcript" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.sftp-dock-chrome" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["toolbars"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["density"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["spacing"]
    assert "moba.sftp-browser-chrome" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-browser-chrome" in moba["dimension_coverage"]["panes"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["layout"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["status_bars"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["density"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["spacing"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.bottom-status-chrome" in moba["dimension_coverage"]["status_bars"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["status_bars"]
    assert "moba.rail-section-labels" in moba["dimension_coverage"]["sidebars"]


def test_gui_parity_tracks_reference_line_anchors_for_product_presets() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "securecrt": "securecrt.reference-line-anchors",
        "termius": "termius.reference-line-anchors",
        "remmina": "remmina.reference-line-anchors",
        "mremoteng": "mremoteng.reference-line-anchors",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_gui_parity_tracks_reference_topology_for_product_presets() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "mobaxterm": "moba.reference-topology",
        "securecrt": "securecrt.reference-topology",
        "termius": "termius.reference-topology",
        "remmina": "remmina.reference-topology",
        "mremoteng": "mremoteng.reference-topology",
    }
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        assert requirement_id in preset["dimension_coverage"]["layout"]


def test_mobaxterm_static_renderer_uses_drawn_ribbon_pictograms() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "def draw_moba_ribbon_icon" in renderer_source
    assert "gui_design_moba_ribbon_actions" in renderer_source
    assert "GuiMobaTopMenuItem" in design_source
    assert "GUI_DESIGN_MOBA_TOP_MENU_ITEMS" in design_source
    assert "gui_design_moba_top_menu_items" in renderer_source
    for token in ['"servers"', '"tunneling"', '"xserver"', '"exit"']:
        assert token in renderer_source


def test_mobaxterm_titlebar_chrome_uses_shared_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaTitlebarChrome" in design_source
    assert "GUI_DESIGN_MOBA_TITLEBAR_CHROME" in design_source
    assert "gui_design_moba_titlebar_chrome" in renderer_source
    assert "draw_moba_titlebar_icon" in renderer_source
    assert "draw_moba_titlebar_control" in renderer_source
    assert "apply_moba_titlebar_chrome" in gui_source
    assert "mobaTitlebarTitle" in gui_source
    assert "mobaTitlebarControlKeys" in gui_source
    assert "EXPECTED_MOBA_TITLEBAR_CHROME" in checker_source
    assert "expected_moba_titlebar_chrome" in checker_source


def test_mobaxterm_quick_connect_chrome_uses_shared_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaQuickConnectChrome" in design_source
    assert "GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME" in design_source
    assert "connected_idle_query" in design_source
    assert "connected_suggestions_visible" in design_source
    assert "gui_design_moba_quick_connect_chrome" in renderer_source
    assert "draw_moba_quick_connect_chrome" in renderer_source
    assert "connected_idle_query" in renderer_source
    assert "mobaQuickConnectChrome" in gui_source
    assert "mobaQuickConnectDropdown" in gui_source
    assert "mobaQuickConnectHeight" in gui_source
    assert "set_moba_quick_connect_connected_idle" in gui_source
    assert "mobaQuickConnectConnectedMode" in gui_source
    assert "EXPECTED_MOBA_QUICK_CONNECT_CHROME" in checker_source
    assert "expected_moba_quick_connect_chrome" in checker_source
    assert "expected_moba_connected_quick_connect_idle" in checker_source
    assert "Quick Connect top strip" in docs_source
    assert "connected Quick Connect idle state" in docs_source


def test_mobaxterm_quick_connect_suggestions_use_shared_metadata() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.quick-connect-suggestions"
    )
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaQuickConnectSuggestionChrome" in design_source
    assert "GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME" in design_source
    assert "gui_design_moba_quick_connect_suggestion_chrome" in design_source
    assert "draw_moba_quick_connect_suggestions" in renderer_source
    assert "quick_connect_candidates" in renderer_source
    assert "quick_connect_suggestions" in gui_source
    assert "mobaQuickConnectSuggestionKinds" in gui_source
    assert "mobaQuickConnectSuggestionDetails" in gui_source
    assert "EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME" in checker_source
    assert "quick-connect-suggestions" in checker_source
    assert "expected_moba_quick_connect_suggestion_chrome" in checker_source
    assert "MobaXterm-style Quick Connect suggestion dropdown" in docs_source
    assert "mobaQuickConnectSuggestionKinds" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]


def test_mobaxterm_connected_quick_connect_idle_is_tracked() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.connected-quick-connect-idle"
    )
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "connected_idle_query" in requirement["source_tokens"]["src/remote_ops_workspace/gui_designs.py"]
    assert "connected_suggestions_visible" in requirement["source_tokens"]["src/remote_ops_workspace/gui_designs.py"]
    assert "connected_idle_query" in design_source
    assert "connected_suggestions_visible" in design_source
    assert "connected_idle_query" in renderer_source
    assert "connected_suggestions_visible" in renderer_source
    assert "set_moba_quick_connect_connected_idle" in gui_source
    assert "mobaQuickConnectConnectedSuggestionVisible" in gui_source
    assert "connected-quick-connect-idle" in checker_source
    assert "expected_moba_connected_quick_connect_idle" in checker_source
    assert "connected Quick Connect idle state" in docs_source


def test_mobaxterm_home_welcome_uses_shared_metadata() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    preview_checker_source = Path("scripts/check_gui_design_previews.py").read_text(encoding="utf-8")
    visual_checker_source = Path("scripts/check_gui_visual_metrics.py").read_text(encoding="utf-8")
    visual_metrics_source = Path("configs/gui_visual_metrics.json").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaHomeWelcomeChrome" in design_source
    assert "GUI_DESIGN_MOBA_HOME_WELCOME_CHROME" in design_source
    assert "gui_design_moba_home_welcome_chrome" in design_source
    assert "render_mobaxterm_home_preset" in renderer_source
    assert "mobaxterm-home.png" in renderer_source
    assert "state_previews" in renderer_source
    assert "mobaxterm-home" in preview_checker_source
    assert "check_state_preview_images" in preview_checker_source
    assert "preview_images_by_state_preview" in visual_checker_source
    assert "state_previews" in visual_checker_source
    assert "count_metric_items" in visual_checker_source
    assert "mobaxterm-home" in visual_metrics_source
    assert "home-welcome-surface" in visual_metrics_source
    assert "recent-sessions" in visual_metrics_source
    assert "build_moba_home_welcome" in gui_source
    assert "mobaHomeWelcomeSurface" in gui_source
    assert "mobaRecentSession" in gui_source
    assert "EXPECTED_MOBA_HOME_WELCOME_CHROME" in checker_source
    assert "check_live_moba_home_welcome" in checker_source
    assert "expected_moba_home_welcome_chrome" in checker_source
    assert "MobaXterm-style home welcome surface" in docs_source


def test_mobaxterm_live_gui_uses_generated_ribbon_icons() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "def moba_ribbon_icon" in gui_source
    assert "def draw_moba_ribbon_icon" in gui_source
    assert "gui_design_moba_ribbon_actions" in gui_source
    assert "gui_design_moba_top_menu_items" in gui_source
    assert "mobaTopMenuKey" in gui_source
    assert "EXPECTED_MOBA_TOP_MENU_KEYS" in live_checker_source
    assert "mobaIconKey" in gui_source
    assert "must use a generated ribbon icon" in live_checker_source


def test_mobaxterm_rail_uses_role_based_generated_icons() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "mobaRailRole" in gui_source
    assert "show_moba_sftp_rail" in gui_source
    assert '"S\\ne\\ns\\ns\\ni\\no\\nn\\ns"' not in gui_source
    assert "draw_moba_rail_icon" in renderer_source
    assert "EXPECTED_MOBA_RAIL_ROLES" in live_checker_source
    assert "must not use stacked text" in live_checker_source


def test_mobaxterm_static_sftp_dock_uses_drawn_glyphs() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaSftpFileRowIcon" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS" in design_source
    assert "draw_moba_sftp_toolbar_icon" in renderer_source
    assert "draw_moba_sftp_file_icon" in renderer_source
    assert "gui_design_moba_sftp_file_row_icon" in renderer_source
    assert "draw_moba_monitor_icon" in renderer_source
    assert "apply_sftp_file_row_icon" in gui_source
    assert "SFTP_ROW_ICON_RENDER_ROLE" in gui_source
    assert "generated-pixmap" in gui_source
    assert "EXPECTED_MOBA_SFTP_FILE_ROW_ICONS" in live_checker_source
    assert "expected_moba_sftp_file_row_icons" in live_checker_source
    assert "sftp-file-row-icons" in live_checker_source
    assert "moba_preview_reference_state" in renderer_source
    assert "moba_connected_tab_chrome_items" in renderer_source
    assert "draw_moba_telemetry_icon" in renderer_source
    assert '"[dir]"' not in renderer_source
    assert '"[file]"' not in renderer_source


def test_mobaxterm_sftp_dock_uses_shared_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaSftpDockAction" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS" in design_source
    assert "GuiMobaSftpBrowserChrome" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME" in design_source
    assert "GuiMobaSftpFileRowIcon" in design_source
    assert "GuiMobaSftpDockLayout" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT" in design_source
    assert "group_key" in design_source
    assert "separator_after" in design_source
    assert "GuiMobaMonitoringControl" in design_source
    assert "GUI_DESIGN_MOBA_MONITORING_CONTROLS" in design_source
    assert "gui_design_moba_sftp_dock_actions" in renderer_source
    assert "gui_design_moba_sftp_browser_chrome" in renderer_source
    assert "gui_design_moba_sftp_dock_layout" in renderer_source
    assert "density.file_row_height" in renderer_source
    assert "action.separator_after" in renderer_source
    assert "column.static_x" in renderer_source
    assert "gui_design_moba_monitoring_controls" in renderer_source
    assert "draw_moba_monitoring_control" in renderer_source
    assert "moba_monitoring_metric_text" in renderer_source
    assert "mobaSftpActionKey" in gui_source
    assert "mobaSftpIconKey" in gui_source
    assert "mobaSftpActionGroupKey" in gui_source
    assert "mobaSftpToolbarSeparator" in gui_source
    assert "mobaSftpPathDropdownMarker" in gui_source
    assert "mobaSftpColumnKeys" in gui_source
    assert "mobaSftpRowHeight" in gui_source
    assert "mobaSftpMonitoringHeight" in gui_source
    assert "mobaMonitoringMetricKey" in gui_source
    assert "mobaMonitoringControlKey" in gui_source
    assert "mobaMonitoringControlIconKey" in gui_source
    assert "mobaMonitoringControlStaticX" in gui_source
    assert "mobaMonitoringControlIconSize" in gui_source
    assert "mobaRemoteMonitoringCompact" in gui_source
    assert "EXPECTED_MOBA_SFTP_ACTION_KEYS" in checker_source
    assert "EXPECTED_MOBA_SFTP_BROWSER_CHROME" in checker_source
    assert "EXPECTED_MOBA_SFTP_DOCK_LAYOUT" in checker_source
    assert "EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS" in checker_source
    assert "expected_moba_sftp_toolbar_groups" in checker_source
    assert "expected_moba_sftp_dock_layout" in checker_source
    assert "EXPECTED_MOBA_MONITORING_METRIC_KEYS" in checker_source
    assert "EXPECTED_MOBA_MONITORING_CONTROL_KEYS" in checker_source
    assert "EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY" in checker_source


def test_mobaxterm_compact_monitoring_dock_uses_shared_metadata() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.remote-monitoring-compact-dock"
    )
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "compact" in requirement["description"]
    assert "GuiMobaRemoteMonitoringDockChrome" in design_source
    assert "GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME" in design_source
    assert "GuiMobaMonitoringControlGeometry" in design_source
    assert "GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY" in design_source
    assert "gui_design_moba_remote_monitoring_dock_chrome" in renderer_source
    assert "gui_design_moba_monitoring_control_geometry_for" in renderer_source
    assert "visible_metric_keys" in renderer_source
    assert "mobaRemoteMonitoringTelemetrySurface" in gui_source
    assert "mobaRemoteMonitoringCommand" in gui_source
    assert "mobaRemoteMonitoringFollowPlan" in gui_source
    assert "mobaMonitoringControlGeometryKeys" in gui_source
    assert "EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME" in checker_source
    assert "expected_moba_remote_monitoring_dock_chrome" in checker_source
    assert "expected_moba_monitoring_control_geometry" in checker_source
    assert "mobaRemoteMonitoringCompact" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "mobaMonitoringControlStaticX" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]


def test_mobaxterm_static_renderer_uses_connected_tab_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")

    assert "moba_connected_tab_chrome_items" in renderer_source
    assert "draw_moba_connected_tab" in renderer_source
    assert "draw_moba_tab_icon" in renderer_source
    assert "MobaConnectedTabChromeItem" in state_source
    assert "inactive-session" in state_source
    assert "terminal-key" in state_source


def test_mobaxterm_static_renderer_uses_right_utility_icons_not_text_placeholders() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "draw_moba_right_utility_rail" in renderer_source
    assert "draw_moba_right_utility_icon" in renderer_source
    assert "gui_design_moba_right_utility_actions" in renderer_source
    assert "action.static_y" in renderer_source
    assert '"gear"' in renderer_source
    assert 'draw_text(draw, "clip"' not in renderer_source
    assert "mobaRightUtilityRail" in gui_source
    assert "mobaRightUtilityKey" in gui_source
    assert "mobaRightUtilityIconKey" in gui_source
    assert "mobaRightUtilityStaticY" in gui_source
    assert "mobaRightUtilityButtonSize" in gui_source
    assert "mobaRightUtilityRenderSource" in gui_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_KEYS" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_BY_KEY" in checker_source
    assert "right-utility-rail-geometry" in checker_source


def test_mobaxterm_static_renderer_uses_session_edge_shortcut_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaSessionEdgeAction" in design_source
    assert "GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS" in design_source
    assert "gui_design_moba_session_edge_actions" in renderer_source
    assert "draw_moba_session_edge_controls" in renderer_source
    assert "action.static_y" in renderer_source
    assert "mobaSessionEdgeControls" in gui_source
    assert "mobaSessionEdgeAction" in gui_source
    assert "mobaSessionEdgeIconKey" in gui_source
    assert "EXPECTED_MOBA_SESSION_EDGE_KEYS" in checker_source
    assert "expected_moba_session_edge_actions" in checker_source
    assert "session edge shortcut" in docs_source


def test_mobaxterm_ssh_banner_uses_shared_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaSshBannerChrome" in design_source
    assert "gui_design_moba_ssh_banner_chrome" in renderer_source
    assert "draw_centered_text" in renderer_source
    assert "mobaSshBannerTitle" in gui_source
    assert "mobaSshBannerSubtitle" in gui_source
    assert "EXPECTED_MOBA_SSH_BANNER_CHROME" in checker_source


def test_mobaxterm_ssh_banner_capability_card_is_tracked() -> None:
    criteria = json.loads(Path("configs/gui_parity_criteria.json").read_text(encoding="utf-8"))
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    requirement_ids = {item["id"] for item in criteria["presets"]["mobaxterm"]["requirements"]}

    assert "moba.ssh-banner-capability-card" in requirement_ids
    assert "SshConnectionCapability" in state_source
    assert "capability_rows" in state_source
    assert "footer_links" in state_source
    assert "target_intro" in design_source
    assert "capability_label_width" in design_source
    assert "draw_moba_ssh_banner_card" in renderer_source
    assert "state.banner.capability_rows()" in renderer_source
    assert "state.banner.footer_links()" in renderer_source
    assert "mobaSshBannerTargetLine" in gui_source
    assert "mobaSshBannerCapabilityKey" in gui_source
    assert "mobaSshBannerFooter" in gui_source
    assert "EXPECTED_MOBA_SSH_BANNER_CAPABILITY_KEYS" in checker_source
    assert "expected_moba_ssh_banner_capability_card" in checker_source
    assert "MobaXterm-style SSH banner capability card" in docs_source


def test_mobaxterm_terminal_transcript_uses_shared_connected_state() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "MobaTerminalTranscriptLine" in state_source
    assert "build_moba_terminal_transcript" in state_source
    assert "terminal_transcript" in state_source
    assert "state.terminal_transcript" in renderer_source
    assert "line.tone" in renderer_source
    assert "apply_terminal_transcript_evidence" in gui_source
    assert "mobaTerminalTranscriptKeys" in gui_source
    assert "mobaTerminalTranscriptTones" in gui_source
    assert "EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS" in checker_source
    assert "expected_moba_terminal_transcript" in checker_source


def test_mobaxterm_bottom_status_uses_shared_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaStatusBarChrome" in design_source
    assert "GUI_DESIGN_MOBA_STATUS_SEGMENTS" in design_source
    assert "gui_design_moba_status_bar_chrome" in renderer_source
    assert "gui_design_moba_status_segments" in renderer_source
    assert "productStatusNotice" in gui_source
    assert "productStatusMarker" in gui_source
    assert "productStatusKey" in gui_source
    assert "EXPECTED_MOBA_STATUS_KEYS" in checker_source
    assert "EXPECTED_MOBA_STATUS_CHROME" in checker_source


def test_mobaxterm_bottom_edge_controls_use_shared_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaBottomEdgeControl" in design_source
    assert "GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS" in design_source
    assert "gui_design_moba_bottom_edge_controls" in renderer_source
    assert "draw_moba_bottom_edge_controls" in renderer_source
    assert "draw_moba_bottom_edge_icon" in renderer_source
    assert "mobaBottomEdgeControls" in gui_source
    assert "mobaBottomEdgeControl" in gui_source
    assert "activate_adjacent_tab" in gui_source
    assert "EXPECTED_MOBA_BOTTOM_EDGE_KEYS" in checker_source
    assert "expected_moba_bottom_edge_controls" in checker_source
    assert "bottom-edge navigation controls" in docs_source


def test_mobaxterm_connected_chrome_uses_shared_target_and_telemetry_state() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "MobaTelemetrySegment" in state_source
    assert "moba_connected_profile_label" in state_source
    assert "moba_connected_window_title" in gui_source
    assert "moba_connected_tab_label" in gui_source
    assert "moba_telemetry_cells" in gui_source
    assert "telemetry_icon_pixmap" in gui_source
    assert "mobaTelemetryIconRender" in gui_source
    assert "mobaTelemetryCellWidth" in gui_source
    assert "mobaTelemetryKey" in gui_source
    assert "EXPECTED_MOBA_TELEMETRY_CELL_KEYS" in live_checker_source
    assert "expected_moba_telemetry_cells" in live_checker_source
    assert "must not be a text placeholder" in live_checker_source
    assert "window title must be connected target label" in live_checker_source


def test_mobaxterm_live_connected_session_uses_left_dock_switch() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    connected_panel_init = gui_source.split("class MobaConnectedSessionPanel", 1)[1].split(
        "def build_terminal_area", 1
    )[0]

    assert "QSplitter" not in connected_panel_init
    assert "build_sftp" not in connected_panel_init
    assert "moba_left_stack" in gui_source
    assert "show_moba_connected_dock" in gui_source
    assert "refresh_moba_left_dock_for_current_tab" in gui_source
    assert 'set_moba_rail_active("sftp")' in gui_source


def test_gui_parity_tracks_product_specific_sidebar_identity() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "securecrt": "securecrt.session-manager-sidebar",
        "termius": "termius.hosts-sidebar",
        "remmina": "remmina.connection-profile-sidebar",
        "mremoteng": "mremoteng.connections-sidebar",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_gui_parity_tracks_product_specific_toolbar_identity() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "securecrt": "securecrt.session-toolbar",
        "termius": "termius.host-toolbar",
        "remmina": "remmina.viewer-toolbar",
        "mremoteng": "mremoteng.connection-toolbar",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_live_and_static_renderers_share_toolbar_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "GUI_DESIGN_TOOLBAR_COPY" in design_source
    assert "configure_toolbar_copy_for_design" in gui_source
    assert "gui_design_toolbar_actions" in renderer_source


def test_gui_parity_tracks_product_specific_status_bars() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "mobaxterm": "moba.status-segments",
        "securecrt": "securecrt.status-bar",
        "termius": "termius.status-bar",
        "remmina": "remmina.status-bar",
        "mremoteng": "mremoteng.status-bar",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_gui_parity_tracks_product_specific_session_trees() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "mobaxterm": "moba.session-tree",
        "securecrt": "securecrt.session-tree",
        "termius": "termius.host-tree",
        "remmina": "remmina.protocol-tree",
        "mremoteng": "mremoteng.nested-connection-tree",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_live_and_static_renderers_share_session_tree_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "GUI_DESIGN_TREE_ROOT_COPY" in design_source
    assert "GUI_DESIGN_TREE_ROWS" in design_source
    assert "GUI_DESIGN_TREE_ROOT_ICONS" in design_source
    assert "GUI_DESIGN_TREE_ROW_ICONS" in design_source
    assert "profile_group_label" in gui_source
    assert "profile_tree_tooltip" in gui_source
    assert "apply_profile_tree_icon" in gui_source
    assert "gui_design_tree_rows" in renderer_source
    assert "gui_design_tree_row_icon_key" in renderer_source


def test_static_renderer_tracks_product_specific_sidebar_glyphs() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.session-glyphs",
        "termius": "termius.host-glyphs",
        "remmina": "remmina.protocol-glyphs",
        "mremoteng": "mremoteng.connection-glyphs",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids
    assert "sidebar_row_icon_key" in renderer_source
    assert "draw_sidebar_row_icon" in renderer_source
    assert "gui_design_tree_row_icon_key" in renderer_source
    assert "ssh2" in renderer_source
    assert "command" in renderer_source
    assert "GENERATED_PROFILE_TREE_ICON_PRESETS" in gui_source
    assert "profile_tree_generated_icon" in gui_source
    assert "EXPECTED_PRODUCT_TREE_ICON_ROWS" in live_checker_source
    assert "check_product_tree_icon_metadata" in live_checker_source
    assert "termius-tree-icons" in live_checker_source
    assert "remmina-tree-icons" in live_checker_source
    assert "mremoteng-tree-icons" in live_checker_source


def test_gui_parity_tracks_product_specific_tab_models() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "securecrt": "securecrt.tab-model",
        "termius": "termius.tab-model",
        "remmina": "remmina.viewer-tabs",
        "mremoteng": "mremoteng.tab-model",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_live_and_static_renderers_share_tab_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "GUI_DESIGN_TAB_COPY" in design_source
    assert "GUI_DESIGN_HOME_TAB_COPY" in design_source
    assert "gui_design_home_tab_label" in gui_source
    assert "gui_design_tab_items" in renderer_source


def test_gui_parity_tracks_product_specific_workspace_surfaces() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "securecrt": "securecrt.workspace-surface",
        "termius": "termius.workspace-surface",
        "remmina": "remmina.viewer-surface",
        "mremoteng": "mremoteng.workspace-surface",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids


def test_live_and_static_renderers_share_workspace_surface_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "GUI_DESIGN_WORKSPACE_SURFACES" in design_source
    assert "gui_design_workspace_surface" in gui_source
    assert "productWorkspaceSurface" in gui_source
    assert "build_product_workspace_surface_evidence" in gui_source
    assert "draw_securecrt_workspace" in renderer_source
    assert "draw_termius_workspace" in renderer_source
    assert "draw_remmina_workspace" in renderer_source
    assert "draw_mremoteng_workspace" in renderer_source


def test_static_renderer_tracks_remmina_and_mremoteng_control_surfaces() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    visual_metrics_source = Path("configs/gui_visual_metrics.json").read_text(encoding="utf-8")

    remmina_requirements = {item["id"] for item in criteria["presets"]["remmina"]["requirements"]}
    assert "remmina.viewer-controls" in remmina_requirements
    assert "remmina.viewer-control-chrome" in remmina_requirements
    mremoteng_requirements = {item["id"] for item in criteria["presets"]["mremoteng"]["requirements"]}
    assert "mremoteng.top-chrome" in mremoteng_requirements
    assert "mremoteng.document-controls" in mremoteng_requirements
    assert "mremoteng.document-control-chrome" in mremoteng_requirements
    assert "mremoteng.property-grid-chrome" in mremoteng_requirements
    assert "mremoteng.top-chrome" in criteria["presets"]["mremoteng"]["dimension_coverage"]["toolbars"]
    assert "GuiMRemoteNgTopChrome" in design_source
    assert "gui_design_mremoteng_top_chrome" in design_source
    assert "GuiMRemoteNgDocumentControl" in design_source
    assert "gui_design_mremoteng_document_controls" in design_source
    assert "GuiMRemoteNgPropertyGridChrome" in design_source
    assert "gui_design_mremoteng_property_grid_chrome" in design_source
    assert "mRemoteNgTopToolbarIconKey" in gui_source
    assert "build_mremoteng_document_controls_evidence" in gui_source
    assert "mRemoteNgDocumentControlKey" in gui_source
    assert "mRemoteNgDocumentRenderSource" in gui_source
    assert "mremoteng_document_control_icon" in gui_source
    assert "build_mremoteng_property_grid_evidence" in gui_source
    assert "mRemoteNgPropertyRowKey" in gui_source
    assert "GuiRemminaViewerControl" in design_source
    assert "static_width" in design_source
    assert "live_button_height" in design_source
    assert "gui_design_remmina_viewer_controls" in design_source
    assert "build_remmina_viewer_controls_evidence" in gui_source
    assert "remmina_profile_filter" in gui_source
    assert "remminaViewerControlKey" in gui_source
    assert "remminaViewerControlStaticWidth" in gui_source
    assert "remminaViewerControlRenderSource" in gui_source
    assert "remminaProfileFilter" in live_checker_source
    assert "draw_remmina_viewer_control_icon" in renderer_source
    assert "gui_design_remmina_viewer_controls" in renderer_source
    assert "control.static_width" in renderer_source
    assert "control.static_icon_size" in renderer_source
    assert "profile-filter-focus" in visual_metrics_source
    assert "active-viewer-tab" in visual_metrics_source
    assert "transfer-toolbar-checked" in visual_metrics_source
    assert "viewer-control-glyph-cluster" in visual_metrics_source
    assert "check_live_remmina_viewer_controls" in live_checker_source
    assert "remmina-viewer-control-geometry" in live_checker_source
    assert "draw_mremoteng_title_bar" in renderer_source
    assert "draw_mremoteng_toolbar" in renderer_source
    assert "gui_design_mremoteng_top_chrome" in renderer_source
    assert "draw_mremoteng_document_toolbar" in renderer_source
    assert "gui_design_mremoteng_document_controls" in renderer_source
    assert "draw_mremoteng_document_control_icon" in renderer_source
    assert "draw_mremoteng_property_grid" in renderer_source
    assert "gui_design_mremoteng_property_grid_chrome" in renderer_source
    assert "check_live_mremoteng_top_chrome" in live_checker_source
    assert "mremoteng-top-chrome" in live_checker_source
    assert "check_live_mremoteng_document_controls" in live_checker_source
    assert "mremoteng-document-control-geometry" in live_checker_source
    assert "mRemoteNgDocumentRenderSource" in live_checker_source
    assert "check_live_mremoteng_property_grid" in live_checker_source
    assert "draw_mremoteng_config_grid" in renderer_source
    assert "mRemoteNgDocumentFilter" in gui_source
    assert "mRemoteNgDocumentFilter" in live_checker_source
    assert "document-filter-focus" in visual_metrics_source
    assert "document-external-tool-checked" in visual_metrics_source
    assert "rdp-control-glyph-cluster" in visual_metrics_source
    assert "property-grid-inherited-rows" in visual_metrics_source


def test_static_renderer_tracks_securecrt_and_termius_workflow_surfaces() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    visual_metrics_source = Path("configs/gui_visual_metrics.json").read_text(encoding="utf-8")

    securecrt_requirements = {item["id"] for item in criteria["presets"]["securecrt"]["requirements"]}
    assert "securecrt.command-window" in securecrt_requirements
    assert "securecrt.command-window-chrome" in securecrt_requirements
    assert "securecrt.session-manager-chrome" in securecrt_requirements
    assert "securecrt.top-chrome" in securecrt_requirements
    assert "securecrt.top-chrome" in criteria["presets"]["securecrt"]["dimension_coverage"]["toolbars"]
    termius_requirements = {item["id"] for item in criteria["presets"]["termius"]["requirements"]}
    assert "termius.workflow-cards" in termius_requirements
    assert "termius.hosts-sidebar-chrome" in termius_requirements
    assert "termius.header-chip-chrome" in termius_requirements
    assert "GuiSecureCrtCommandWindowChrome" in design_source
    assert "gui_design_securecrt_command_window_chrome" in design_source
    assert "GuiSecureCrtSessionManagerChrome" in design_source
    assert "gui_design_securecrt_session_manager_chrome" in design_source
    assert "GuiSecureCrtTopChrome" in design_source
    assert "gui_design_securecrt_top_chrome" in design_source
    assert "GuiTermiusHeaderChip" in design_source
    assert "GuiTermiusHostsChrome" in design_source
    assert "gui_design_termius_hosts_chrome" in design_source
    assert "gui_design_termius_header_chips" in design_source
    assert "build_securecrt_command_window_evidence" in gui_source
    assert "build_securecrt_session_manager_chrome" in gui_source
    assert "configure_menu_bar_for_design" in gui_source
    assert "secureCrtTopToolbarIconKey" in gui_source
    assert "build_termius_hosts_chrome" in gui_source
    assert "termiusHostSearch" in gui_source
    assert "build_termius_header_chips_evidence" in gui_source
    assert "termiusHeaderChipKey" in gui_source
    assert "secureCrtCommandWindowKey" in gui_source
    assert "secureCrtSessionManagerActionKey" in gui_source
    assert "draw_securecrt_command_window" in renderer_source
    assert "draw_securecrt_session_manager_chrome" in renderer_source
    assert "draw_securecrt_session_tree" in renderer_source
    assert "gui_design_tree_root_copy" in renderer_source
    assert "gui_design_securecrt_command_window_chrome" in renderer_source
    assert "gui_design_securecrt_session_manager_chrome" in renderer_source
    assert "session-manager-filter-focus" in visual_metrics_source
    assert "session-manager-tree-root" in visual_metrics_source
    assert "session-manager-tree-selected-row" in visual_metrics_source
    assert "session-tree-connectors-inside-session-manager" in visual_metrics_source
    assert "securecrt-active-tab" in visual_metrics_source
    assert "command-window-input-focus" in visual_metrics_source
    assert "command-window-send-control" in visual_metrics_source
    assert "hosts-search-focus" in visual_metrics_source
    assert "active-west-tab" in visual_metrics_source
    assert "host-identity-sync-control" in visual_metrics_source
    assert "workflow-card-action-row" in visual_metrics_source
    assert "draw_securecrt_title_bar" in renderer_source
    assert "draw_securecrt_toolbar" in renderer_source
    assert "gui_design_securecrt_top_chrome" in renderer_source
    assert "draw_termius_hosts_chrome" in renderer_source
    assert "gui_design_termius_hosts_chrome" in renderer_source
    assert "gui_design_termius_header_chips" in renderer_source
    assert "check_live_securecrt_command_window" in live_checker_source
    assert "check_live_securecrt_session_manager_chrome" in live_checker_source
    assert "check_live_securecrt_top_chrome" in live_checker_source
    assert "check_securecrt_tree_icon_metadata" in live_checker_source
    assert "EXPECTED_SECURECRT_TREE_ICON_KEYS" in live_checker_source
    assert "securecrt-top-chrome" in live_checker_source
    assert "securecrt-tree-icons" in live_checker_source
    assert "check_live_termius_hosts_chrome" in live_checker_source
    assert "termius-hosts-chrome" in live_checker_source
    assert "check_live_termius_header_chips" in live_checker_source
    assert "draw_termius_session_workflow" in renderer_source


def test_gui_parity_tracks_live_product_workflow_cards() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.live-workflow-cards",
        "termius": "termius.live-workflow-cards",
        "remmina": "remmina.live-workflow-cards",
        "mremoteng": "mremoteng.live-workflow-cards",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids
    assert "GUI_DESIGN_WORKFLOW_CARDS" in design_source
    assert "gui_design_workflow_cards" in design_source
    assert "build_product_workflow_evidence" in gui_source
    assert "productWorkflowEvidence" in gui_source
    assert "check_live_workflow_cards" in live_checker_source


def test_gui_parity_tracks_non_moba_reference_state_contracts() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-state",
        "termius": "termius.reference-state",
        "remmina": "remmina.reference-state",
        "mremoteng": "mremoteng.reference-state",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["connected_session_behavior"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["status_bars"]

    assert "GUI_DESIGN_REFERENCE_STATES" in design_source
    assert "GuiProductReferenceState" in design_source
    assert "build_product_reference_state_evidence" in gui_source
    assert "productReferenceStateItem" in gui_source
    assert "draw_product_reference_state" in renderer_source
    assert "check_live_reference_state" in live_checker_source


def test_gui_parity_tracks_product_specific_interaction_states() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)

    expected = {
        "mobaxterm": "moba.interaction-states",
        "securecrt": "securecrt.interaction-states",
        "termius": "termius.interaction-states",
        "remmina": "remmina.interaction-states",
        "mremoteng": "mremoteng.interaction-states",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids
    securecrt_interaction = next(
        item for item in criteria["presets"]["securecrt"]["requirements"] if item["id"] == "securecrt.interaction-states"
    )
    termius_interaction = next(
        item for item in criteria["presets"]["termius"]["requirements"] if item["id"] == "termius.interaction-states"
    )
    remmina_interaction = next(
        item for item in criteria["presets"]["remmina"]["requirements"] if item["id"] == "remmina.interaction-states"
    )
    mremoteng_interaction = next(
        item for item in criteria["presets"]["mremoteng"]["requirements"] if item["id"] == "mremoteng.interaction-states"
    )
    assert "configs/gui_visual_metrics.json" in securecrt_interaction["source_tokens"]
    assert "scripts/check_gui_visual_metrics.py" in securecrt_interaction["source_tokens"]
    assert "command-window-send-control" in securecrt_interaction["source_tokens"]["configs/gui_visual_metrics.json"]
    assert "configs/gui_visual_metrics.json" in termius_interaction["source_tokens"]
    assert "scripts/check_gui_visual_metrics.py" in termius_interaction["source_tokens"]
    assert "host-identity-sync-control" in termius_interaction["source_tokens"]["configs/gui_visual_metrics.json"]
    assert "configs/gui_visual_metrics.json" in remmina_interaction["source_tokens"]
    assert "scripts/check_gui_visual_metrics.py" in remmina_interaction["source_tokens"]
    assert "transfer-toolbar-checked" in remmina_interaction["source_tokens"]["configs/gui_visual_metrics.json"]
    assert "configs/gui_visual_metrics.json" in mremoteng_interaction["source_tokens"]
    assert "scripts/check_gui_visual_metrics.py" in mremoteng_interaction["source_tokens"]
    assert "document-filter-focus" in mremoteng_interaction["source_tokens"]["configs/gui_visual_metrics.json"]


def test_live_and_static_renderers_share_interaction_state_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    visual_checker_source = Path("scripts/check_gui_visual_metrics.py").read_text(encoding="utf-8")
    visual_metrics_source = Path("configs/gui_visual_metrics.json").read_text(encoding="utf-8")

    assert "GUI_DESIGN_INTERACTION_STATES" in design_source
    assert "gui_design_interaction_state" in gui_source
    assert "configure_interaction_states_for_design" in gui_source
    assert "interaction_button_colors" in renderer_source
    assert "selected_tree_label" in renderer_source
    assert "check_color_anchor" in visual_checker_source
    assert "check_line_anchor" in visual_checker_source
    assert "check_topology_contract" in visual_checker_source
    assert "session-filter-focus-outline" in visual_metrics_source
    assert "active-tab-focus-outline" in visual_metrics_source
    assert "command-window-input-focus-outline" in visual_metrics_source
    assert "host-search-focus-outline" in visual_metrics_source
    assert "active-west-tab-focus-outline" in visual_metrics_source
    assert "vault-toolbar-checked-border" in visual_metrics_source
    assert "identity-sync-control-fill" in visual_metrics_source
    assert "profile-filter-focus-outline" in visual_metrics_source
    assert "active-viewer-tab-focus-top" in visual_metrics_source
    assert "transfer-toolbar-checked-outline" in visual_metrics_source
    assert "viewer-fit-control-glyph" in visual_metrics_source
    assert "document-filter-focus-outline" in visual_metrics_source
    assert "document-external-tool-checked-outline" in visual_metrics_source
    assert "active-document-tab-focus-top" in visual_metrics_source
    assert "rdp-fit-glyph" in visual_metrics_source


def test_live_and_static_renderers_share_status_bar_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    assert "GUI_DESIGN_STATUS_COPY" in design_source
    assert "configure_status_bar_for_design" in gui_source
    assert "gui_design_status_segments" in renderer_source


def test_termius_preview_renderer_uses_vertical_tabs() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")

    assert "preset.tab_position == \"west\"" in renderer_source
    assert "draw_vertical_tabs" in renderer_source


def _load_checker():
    path = Path("scripts/check_gui_parity.py")
    spec = importlib.util.spec_from_file_location("check_gui_parity_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
