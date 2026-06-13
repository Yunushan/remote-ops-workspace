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
    assert "moba.home-welcome-geometry" in requirement_ids
    assert "moba.connected-left-dock" in requirement_ids
    assert "moba.connected-dock-frame" in requirement_ids
    assert "moba.live-dock-switch" in requirement_ids
    assert "moba.top-menu-chrome" in requirement_ids
    assert "moba.top-menu-geometry" in requirement_ids
    assert "moba.ribbon-pictograms" in requirement_ids
    assert "moba.ribbon-geometry" in requirement_ids
    assert "moba.sftp-glyphs" in requirement_ids
    assert "moba.sftp-dock-chrome" in requirement_ids
    assert "moba.sftp-toolbar-groups" in requirement_ids
    assert "moba.sftp-toolbar-geometry" in requirement_ids
    assert "moba.sftp-dock-density" in requirement_ids
    assert "moba.sftp-browser-chrome" in requirement_ids
    assert "moba.sftp-browser-geometry" in requirement_ids
    assert "moba.sftp-follow-folder-route" in requirement_ids
    assert "moba.sftp-routed-file-rows" in requirement_ids
    assert "moba.remote-monitoring" in requirement_ids
    assert "moba.remote-monitoring-compact-dock" in requirement_ids
    assert "moba.monitoring-telemetry-route" in requirement_ids
    assert "moba.monitoring-controls" in requirement_ids
    assert "moba.monitoring-control-geometry" in requirement_ids
    assert "moba.remote-monitoring-control-route" in requirement_ids
    assert "moba.follow-terminal-folder-control-route" in requirement_ids
    assert "moba.bottom-telemetry" in requirement_ids
    assert "moba.bottom-telemetry-geometry" in requirement_ids
    assert "moba.bottom-status-chrome" in requirement_ids
    assert "moba.bottom-status-geometry" in requirement_ids
    assert "moba.bottom-edge-controls" in requirement_ids
    assert "moba.connected-session-chrome" in requirement_ids
    assert "moba.connected-session-route" in requirement_ids
    assert "moba.connected-session-actions-route" in requirement_ids
    assert "moba.connected-session-action-menu-route" in requirement_ids
    assert "moba.connected-session-identity-route" in requirement_ids
    assert "moba.connected-tab-chrome" in requirement_ids
    assert "moba.session-edge-controls" in requirement_ids
    assert "moba.session-edge-geometry" in requirement_ids
    assert "moba.right-utility-rail" in requirement_ids
    assert "moba.right-utility-rail-chrome" in requirement_ids
    assert "moba.ssh-banner-chrome" in requirement_ids
    assert "moba.ssh-banner-row-geometry" in requirement_ids
    assert "moba.terminal-transcript" in requirement_ids
    assert "moba.terminal-transcript-geometry" in requirement_ids
    assert "moba.rail-section-labels" in requirement_ids
    assert "moba.rail-geometry" in requirement_ids
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
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["navigation"]
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["tabs"]
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.home-welcome-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.top-menu-chrome" in moba["dimension_coverage"]["toolbars"]
    assert "moba.top-menu-chrome" in moba["dimension_coverage"]["navigation"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["navigation"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["toolbars"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.top-menu-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.ribbon-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.ribbon-geometry" in moba["dimension_coverage"]["toolbars"]
    assert "moba.ribbon-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.ribbon-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.ribbon-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.right-utility-rail" in moba["dimension_coverage"]["layout"]
    assert "moba.right-utility-rail-chrome" in moba["dimension_coverage"]["layout"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["layout"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["navigation"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["navigation"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["navigation"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["tabs"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["tabs"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["tabs"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.right-utility-rail-chrome" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["density"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.right-utility-rail-chrome" in moba["dimension_coverage"]["density"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["density"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["spacing"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.right-utility-rail-chrome" in moba["dimension_coverage"]["spacing"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["spacing"]
    assert "moba.session-edge-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.session-edge-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.right-utility-rail-chrome" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.ssh-banner-chrome" in moba["dimension_coverage"]["panes"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["panes"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["density"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["spacing"]
    assert "moba.ssh-banner-capability-card" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["panes"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.ssh-banner-row-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.terminal-transcript" in moba["dimension_coverage"]["panes"]
    assert "moba.terminal-transcript" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["panes"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.terminal-transcript-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.sftp-dock-chrome" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["toolbars"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-toolbar-groups" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["toolbars"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.sftp-toolbar-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["density"]
    assert "moba.sftp-dock-density" in moba["dimension_coverage"]["spacing"]
    assert "moba.connected-dock-frame" in moba["dimension_coverage"]["layout"]
    assert "moba.connected-dock-frame" in moba["dimension_coverage"]["panes"]
    assert "moba.connected-dock-frame" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.connected-dock-frame" in moba["dimension_coverage"]["density"]
    assert "moba.connected-dock-frame" in moba["dimension_coverage"]["spacing"]
    assert "moba.sftp-browser-chrome" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-browser-chrome" in moba["dimension_coverage"]["panes"]
    assert "moba.sftp-browser-geometry" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-browser-geometry" in moba["dimension_coverage"]["panes"]
    assert "moba.sftp-browser-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.sftp-browser-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.sftp-follow-folder-route" in moba["dimension_coverage"]["panes"]
    assert "moba.sftp-follow-folder-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.sftp-follow-folder-route" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-follow-folder-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.sftp-follow-folder-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["layout"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["panes"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["density"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["spacing"]
    assert "moba.sftp-routed-file-rows" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.monitoring-controls" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.monitoring-control-geometry" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["layout"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["status_bars"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["density"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["spacing"]
    assert "moba.remote-monitoring-compact-dock" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.monitoring-telemetry-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.monitoring-telemetry-route" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.monitoring-telemetry-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.monitoring-telemetry-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.remote-monitoring-control-route" in moba["dimension_coverage"]["layout"]
    assert "moba.remote-monitoring-control-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.remote-monitoring-control-route" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.remote-monitoring-control-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.remote-monitoring-control-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.follow-terminal-folder-control-route" in moba["dimension_coverage"]["layout"]
    assert "moba.follow-terminal-folder-control-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.follow-terminal-folder-control-route" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.follow-terminal-folder-control-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.follow-terminal-folder-control-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.bottom-telemetry-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.bottom-telemetry-geometry" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.bottom-telemetry-geometry" in moba["dimension_coverage"]["status_bars"]
    assert "moba.bottom-telemetry-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.bottom-telemetry-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.bottom-status-chrome" in moba["dimension_coverage"]["status_bars"]
    assert "moba.bottom-status-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.bottom-status-geometry" in moba["dimension_coverage"]["status_bars"]
    assert "moba.bottom-status-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.bottom-status-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.bottom-edge-controls" in moba["dimension_coverage"]["status_bars"]
    assert "moba.rail-section-labels" in moba["dimension_coverage"]["sidebars"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["layout"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["navigation"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["sidebars"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["spacing"]
    assert "moba.rail-geometry" in moba["dimension_coverage"]["interaction_states"]


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
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement_ids = {item["id"] for item in moba["requirements"]}
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "moba.ribbon-edge-action-route" in requirement_ids
    for dimension_key in [
        "layout",
        "navigation",
        "toolbars",
        "connected_session_behavior",
        "density",
        "spacing",
        "interaction_states",
    ]:
        assert "moba.ribbon-edge-action-route" in moba["dimension_coverage"][dimension_key]
    assert "def draw_moba_ribbon_icon" in renderer_source
    assert "gui_design_moba_ribbon_actions" in renderer_source
    assert "gui_design_moba_ribbon_edge_actions" in renderer_source
    assert "gui_design_moba_ribbon_edge_action_route" in renderer_source
    assert "moba_ribbon_edge_action_route" in renderer_source
    assert "xserver_dialog_detail" in renderer_source
    assert "gui_design_moba_ribbon_action_geometry_for" in renderer_source
    assert "geometry.separator_x" in renderer_source
    assert "geometry.active_outline_x" in renderer_source
    assert "GuiMobaRibbonEdgeActionRoute" in design_source
    assert "GUI_DESIGN_MOBA_RIBBON_EDGE_ACTION_ROUTE" in design_source
    assert "gui_design_moba_ribbon_edge_action_route" in design_source
    assert "GuiMobaRibbonActionGeometry" in design_source
    assert "GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY" in design_source
    assert "apply_moba_ribbon_edge_action_route" in gui_source
    assert "mobaRibbonEdgeRouteKey" in gui_source
    assert "mobaRibbonEdgeRouteHandler" in gui_source
    assert "EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE" in checker_source
    assert "ribbon-edge-action-route" in checker_source
    assert "expected_moba_ribbon_edge_action_route" in checker_source
    assert "EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY" in checker_source
    assert "ribbon-geometry" in checker_source
    assert "expected_moba_ribbon_action_geometry" in checker_source
    assert "MobaXterm-style ribbon geometry" in docs_source
    assert "MobaXterm-style ribbon edge action route" in docs_source
    assert "GuiMobaTopMenuItem" in design_source
    assert "GUI_DESIGN_MOBA_TOP_MENU_ITEMS" in design_source
    assert "gui_design_moba_top_menu_items" in renderer_source
    for token in ['"servers"', '"tunneling"', '"xserver"', '"exit"']:
        assert token in renderer_source


def test_mobaxterm_titlebar_chrome_uses_shared_metadata() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    requirement_ids = {item["id"] for item in criteria["presets"]["mobaxterm"]["requirements"]}
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "moba.top-stack-geometry" in requirement_ids
    assert "moba.top-menu-geometry" in requirement_ids
    assert "GuiMobaTitlebarChrome" in design_source
    assert "GuiMobaTopStackGeometry" in design_source
    assert "GuiMobaTopMenuGeometry" in design_source
    assert "GUI_DESIGN_MOBA_TITLEBAR_CHROME" in design_source
    assert "GUI_DESIGN_MOBA_TOP_STACK_GEOMETRY" in design_source
    assert "GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY" in design_source
    assert "gui_design_moba_titlebar_chrome" in renderer_source
    assert "gui_design_moba_top_stack_geometry" in renderer_source
    assert "gui_design_moba_top_menu_geometry_for" in renderer_source
    assert "geometry.static_x" in renderer_source
    assert "geometry.label_font_size" in renderer_source
    assert "top_stack.ribbon_y" in renderer_source
    assert "top_stack.left_dock_y" in renderer_source
    assert "draw_moba_titlebar_icon" in renderer_source
    assert "draw_moba_titlebar_control" in renderer_source
    assert "apply_moba_titlebar_chrome" in gui_source
    assert "apply_moba_top_stack_geometry" in gui_source
    assert "mobaTitlebarTitle" in gui_source
    assert "mobaTitlebarControlKeys" in gui_source
    assert "mobaTopStackRibbonHeight" in gui_source
    assert "mobaTopStackQuickConnectY" in gui_source
    assert "mobaTopMenuStaticX" in gui_source
    assert "mobaTopMenuLabelFontSize" in gui_source
    assert "EXPECTED_MOBA_TITLEBAR_CHROME" in checker_source
    assert "EXPECTED_MOBA_TOP_STACK_GEOMETRY" in checker_source
    assert "EXPECTED_MOBA_TOP_MENU_GEOMETRY" in checker_source
    assert "expected_moba_titlebar_chrome" in checker_source
    assert "expected_moba_top_stack_geometry" in checker_source
    assert "expected_moba_top_menu_geometry" in checker_source
    assert "top-stack-geometry" in checker_source
    assert "top-menu-geometry" in checker_source


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
    assert "GuiMobaHomeWelcomeGeometry" in design_source
    assert "GUI_DESIGN_MOBA_HOME_WELCOME_GEOMETRY" in design_source
    assert "gui_design_moba_home_welcome_geometry" in design_source
    assert "render_mobaxterm_home_preset" in renderer_source
    assert "mobaxterm-home.png" in renderer_source
    assert "state_previews" in renderer_source
    assert "gui_design_moba_home_welcome_geometry" in renderer_source
    assert "geometry.button_y_offset" in renderer_source
    assert "geometry.recent_item_step" in renderer_source
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
    assert "mobaHomeActionStaticWidth" in gui_source
    assert "mobaHomeSearchHeight" in gui_source
    assert "mobaHomeFooterYOffset" in gui_source
    assert "EXPECTED_MOBA_HOME_WELCOME_CHROME" in checker_source
    assert "EXPECTED_MOBA_HOME_WELCOME_GEOMETRY" in checker_source
    assert "check_live_moba_home_welcome" in checker_source
    assert "expected_moba_home_welcome_chrome" in checker_source
    assert "moba-home-welcome-geometry" in checker_source
    assert "expected_moba_home_welcome_geometry" in checker_source
    assert "MobaXterm-style home welcome surface" in docs_source
    assert "MobaXterm-style home welcome geometry" in docs_source


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
    assert "mobaRibbonStaticX" in gui_source
    assert "mobaRibbonIconX" in gui_source
    assert "mobaRibbonActiveOutlineWidth" in gui_source
    assert "mobaRibbonSeparatorBottom" in live_checker_source
    assert "must use a generated ribbon icon" in live_checker_source


def test_mobaxterm_rail_uses_role_based_generated_icons() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement = next(item for item in moba["requirements"] if item["id"] == "moba.rail-geometry")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "mobaRailRole" in gui_source
    assert "mobaRailStaticIconY" in gui_source
    assert "mobaRailStaticIconKey" in gui_source
    assert "mobaRailButtonHeight" in gui_source
    assert "show_moba_sftp_rail" in gui_source
    assert '"S\\ne\\ns\\ns\\ni\\no\\nn\\ns"' not in gui_source
    assert "GuiMobaRailChrome" in design_source
    assert "GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY" in design_source
    assert "rail_icon_key" in design_source
    assert "draw_moba_rail_icon" in renderer_source
    assert "gui_design_moba_rail_item_geometry_for" in renderer_source
    assert "rail_chrome.static_icon_size" in renderer_source
    assert "EXPECTED_MOBA_RAIL_ROLES" in live_checker_source
    assert "EXPECTED_MOBA_RAIL_CHROME" in live_checker_source
    assert "moba-rail-geometry" in live_checker_source
    assert "expected_moba_rail_item_geometry" in live_checker_source
    assert "must not use stacked text" in live_checker_source
    assert "MobaXterm-style left rail geometry" in docs_source
    assert "mobaRailStaticIconY" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]


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
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    connected_frame_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.connected-dock-frame"
    )
    toolbar_geometry_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.sftp-toolbar-geometry"
    )
    browser_geometry_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.sftp-browser-geometry"
    )
    follow_route_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.sftp-follow-folder-route"
    )
    terminal_folder_route_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.sftp-terminal-folder-route"
    )
    routed_rows_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.sftp-routed-file-rows"
    )
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")

    assert "GuiMobaSftpDockAction" in design_source
    assert "GuiMobaSftpToolbarActionGeometry" in design_source
    assert "GuiMobaConnectedDockFrame" in design_source
    assert "GUI_DESIGN_MOBA_CONNECTED_DOCK_FRAME" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY" in design_source
    assert "GuiMobaSftpBrowserChrome" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME" in design_source
    assert "path_text_x" in design_source
    assert "dropdown_right_offset" in design_source
    assert "row_modified_x" in design_source
    assert "geometry_dict" in design_source
    assert "GuiMobaSftpFileRowIcon" in design_source
    assert "GuiMobaSftpDockLayout" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT" in design_source
    assert "group_key" in design_source
    assert "separator_after" in design_source
    assert "GuiMobaMonitoringControl" in design_source
    assert "GUI_DESIGN_MOBA_MONITORING_CONTROLS" in design_source
    assert "GuiMobaSftpFollowFolderRoute" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_FOLLOW_FOLDER_ROUTE" in design_source
    assert "gui_design_moba_sftp_follow_folder_route" in design_source
    assert "GuiMobaSftpRoutedFileRows" in design_source
    assert "GUI_DESIGN_MOBA_SFTP_ROUTED_FILE_ROWS" in design_source
    assert "gui_design_moba_sftp_routed_file_rows" in design_source
    assert "MobaSftpTerminalFolderRoute" in state_source
    assert "moba_sftp_terminal_folder_route" in state_source
    assert "terminal-cwd-follow-checkbox-to-sftp-path-and-rows" in state_source
    assert "gui_design_moba_sftp_dock_actions" in renderer_source
    assert "gui_design_moba_connected_dock_frame" in renderer_source
    assert "frame.dock_x" in renderer_source
    assert "frame.dock_width" in renderer_source
    assert "gui_design_moba_sftp_browser_chrome" in renderer_source
    assert "gui_design_moba_sftp_dock_layout" in renderer_source
    assert "density.file_row_height" in renderer_source
    assert "gui_design_moba_sftp_toolbar_action_geometry" in renderer_source
    assert "geometry.icon_x" in renderer_source
    assert "geometry.separator_x" in renderer_source
    assert "column.static_x" in renderer_source
    assert "chrome.path_text_x" in renderer_source
    assert "chrome.dropdown_right_offset" in renderer_source
    assert "chrome.row_icon_x" in renderer_source
    assert "chrome.row_modified_font_size" in renderer_source
    assert "gui_design_moba_sftp_follow_folder_route" in renderer_source
    assert "moba_sftp_terminal_folder_route" in renderer_source
    assert "folder_route.list_command" in renderer_source
    assert "folder_route.target_path_object" in renderer_source
    assert "gui_design_moba_sftp_routed_file_rows" in renderer_source
    assert "routed_rows.follow_route_key" in renderer_source
    assert "routed_rows.selected_row_kind" in renderer_source
    assert "follow_route.source_control_key" in renderer_source
    assert "follow_route.target_path_object" in renderer_source
    assert "gui_design_moba_monitoring_controls" in renderer_source
    assert "draw_moba_monitoring_control" in renderer_source
    assert "moba_monitoring_metric_text" in renderer_source
    assert "mobaSftpActionKey" in gui_source
    assert "mobaSftpIconKey" in gui_source
    assert "mobaConnectedDockSideWidth" in gui_source
    assert "mobaConnectedDockRailWidth" in gui_source
    assert "mobaConnectedDockWidth" in gui_source
    assert "mobaSftpActionGroupKey" in gui_source
    assert "mobaSftpActionStaticX" in gui_source
    assert "mobaSftpActionIconX" in gui_source
    assert "mobaSftpActionSeparatorX" in gui_source
    assert "mobaSftpToolbarSeparator" in gui_source
    assert "mobaSftpPathDropdownMarker" in gui_source
    assert "mobaSftpPathTextX" in gui_source
    assert "mobaSftpDropdownRightOffset" in gui_source
    assert "mobaSftpColumnKeys" in gui_source
    assert "mobaSftpRowHeight" in gui_source
    assert "mobaSftpRowModifiedX" in gui_source
    assert "mobaSftpRowModifiedFontSize" in gui_source
    assert "mobaSftpFollowRouteKey" in gui_source
    assert "mobaSftpFollowRoutePath" in gui_source
    assert "mobaSftpFollowRoutePlan" in gui_source
    assert "mobaSftpTerminalFolderRouteKey" in gui_source
    assert "mobaSftpTerminalFolderRoutePlan" in gui_source
    assert "SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE" in gui_source
    assert "mobaSftpRoutedRowsKey" in gui_source
    assert "SFTP_ROW_ROUTE_KEY_ROLE" in gui_source
    assert "SFTP_ROW_SELECTED_BY_ROUTE_ROLE" in gui_source
    assert "mobaMonitoringFollowEnabled" in gui_source
    assert "mobaSftpMonitoringHeight" in gui_source
    assert "mobaMonitoringMetricKey" in gui_source
    assert "mobaMonitoringControlKey" in gui_source
    assert "mobaMonitoringControlIconKey" in gui_source
    assert "mobaMonitoringControlStaticX" in gui_source
    assert "mobaMonitoringControlIconSize" in gui_source
    assert "mobaMonitoringControlLabelYOffset" in gui_source
    assert "mobaMonitoringControlCheckmarkPoints" in gui_source
    assert "mobaMonitoringControlLiveWidth" in gui_source
    assert "mobaRemoteMonitoringCompact" in gui_source
    assert "EXPECTED_MOBA_SFTP_ACTION_KEYS" in checker_source
    assert "EXPECTED_MOBA_CONNECTED_DOCK_FRAME" in checker_source
    assert "connected-dock-frame" in checker_source
    assert "expected_moba_connected_dock_frame" in checker_source
    assert "EXPECTED_MOBA_SFTP_BROWSER_CHROME" in checker_source
    assert "sftp-browser-geometry" in checker_source
    assert "expected_moba_sftp_browser_geometry" in checker_source
    assert "mobaSftpRowIconYOffset" in checker_source
    assert "EXPECTED_MOBA_SFTP_DOCK_LAYOUT" in checker_source
    assert "EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS" in checker_source
    assert "EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY" in checker_source
    assert "expected_moba_sftp_toolbar_groups" in checker_source
    assert "expected_moba_sftp_toolbar_action_geometry" in checker_source
    assert "expected_moba_sftp_dock_layout" in checker_source
    assert "EXPECTED_MOBA_MONITORING_METRIC_KEYS" in checker_source
    assert "EXPECTED_MOBA_MONITORING_CONTROL_KEYS" in checker_source
    assert "EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY" in checker_source
    assert "EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE" in checker_source
    assert "sftp-follow-folder-route" in checker_source
    assert "expected_moba_sftp_follow_folder_route" in checker_source
    assert "EXPECTED_MOBA_SFTP_TERMINAL_FOLDER_ROUTE" in checker_source
    assert "sftp-terminal-folder-route" in checker_source
    assert "expected_moba_sftp_terminal_folder_route" in checker_source
    assert "EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS" in checker_source
    assert "sftp-routed-file-rows" in checker_source
    assert "expected_moba_sftp_routed_file_rows" in checker_source
    assert "MobaXterm-style connected dock frame" in docs_source
    assert "MobaXterm-style SFTP toolbar geometry" in docs_source
    assert "MobaXterm-style SFTP browser geometry" in docs_source
    assert "MobaXterm-style SFTP follow-folder route" in docs_source
    assert "MobaXterm-style SFTP terminal-folder route" in docs_source
    assert "MobaXterm-style SFTP routed file rows" in docs_source
    assert (
        "mobaConnectedDockSideWidth"
        in connected_frame_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "mobaSftpActionStaticX"
        in toolbar_geometry_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "mobaSftpPathTextX"
        in browser_geometry_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "mobaSftpFollowRouteKey"
        in follow_route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "mobaSftpTerminalFolderRouteKey"
        in terminal_folder_route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "MobaSftpTerminalFolderRoute"
        in terminal_folder_route_requirement["source_tokens"]["src/remote_ops_workspace/moba_connected.py"]
    )
    assert (
        "mobaSftpRoutedRowsKey"
        in routed_rows_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )


def test_mobaxterm_compact_monitoring_dock_uses_shared_metadata() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.remote-monitoring-compact-dock"
    )
    geometry_requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.remote-monitoring-footer-geometry"
    )
    control_geometry_requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.monitoring-control-geometry"
    )
    telemetry_route_requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.monitoring-telemetry-route"
    )
    remote_control_route_requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.remote-monitoring-control-route"
    )
    follow_control_route_requirement = next(
        item
        for item in criteria["presets"]["mobaxterm"]["requirements"]
        if item["id"] == "moba.follow-terminal-folder-control-route"
    )
    assert "moba.follow-terminal-folder-control-route" in criteria["presets"]["mobaxterm"]["dimension_coverage"][
        "layout"
    ]
    assert "moba.follow-terminal-folder-control-route" in criteria["presets"]["mobaxterm"]["dimension_coverage"][
        "connected_session_behavior"
    ]
    assert "moba.follow-terminal-folder-control-route" in criteria["presets"]["mobaxterm"]["dimension_coverage"][
        "file_monitoring_panels"
    ]
    assert "moba.follow-terminal-folder-control-route" in criteria["presets"]["mobaxterm"]["dimension_coverage"][
        "interaction_states"
    ]
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "compact" in requirement["description"]
    assert "GuiMobaRemoteMonitoringDockChrome" in design_source
    assert "GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME" in design_source
    assert "GuiMobaMonitoringTelemetryRoute" in design_source
    assert "GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE" in design_source
    assert "gui_design_moba_monitoring_telemetry_route" in design_source
    assert "GuiMobaRemoteMonitoringControlRoute" in design_source
    assert "GUI_DESIGN_MOBA_REMOTE_MONITORING_CONTROL_ROUTE" in design_source
    assert "gui_design_moba_remote_monitoring_control_route" in design_source
    assert "GuiMobaFollowTerminalFolderControlRoute" in design_source
    assert "GUI_DESIGN_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE" in design_source
    assert "gui_design_moba_follow_terminal_folder_control_route" in design_source
    assert "GuiMobaMonitoringControlGeometry" in design_source
    assert "GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY" in design_source
    assert "divider_left_inset" in design_source
    assert "live_controls_width" in design_source
    assert "label_y_offset" in design_source
    assert "checkmark_points" in design_source
    assert "live_width" in design_source
    assert "gui_design_moba_remote_monitoring_dock_chrome" in renderer_source
    assert "gui_design_moba_monitoring_telemetry_route" in renderer_source
    assert "moba_remote_monitoring_control_route" in renderer_source
    assert "remote_monitoring_control_route.telemetry_route_key" in renderer_source
    assert "moba_follow_terminal_folder_control_route" in renderer_source
    assert "follow_terminal_folder_control_route.expected_checked" in renderer_source
    assert "gui_design_moba_monitoring_control_geometry_for" in renderer_source
    assert "telemetry_route.visible_dock_metric_keys" in renderer_source
    assert "telemetry_route.telemetry_surface" in renderer_source
    assert "geometry.label_y_offset" in renderer_source
    assert "geometry.checkmark_points" in renderer_source
    assert "visible_metric_keys" in renderer_source
    assert "chrome.static_height" in renderer_source
    assert "chrome.divider_left_inset" in renderer_source
    assert "mobaRemoteMonitoringTelemetrySurface" in gui_source
    assert "mobaRemoteMonitoringCommand" in gui_source
    assert "mobaRemoteMonitoringFollowPlan" in gui_source
    assert "mobaMonitoringControlGeometryKeys" in gui_source
    assert "mobaRemoteMonitoringStaticHeight" in gui_source
    assert "mobaRemoteMonitoringLiveControlsWidth" in gui_source
    assert "apply_remote_monitoring_control_route_properties" in gui_source
    assert "mobaRemoteMonitoringControlRouteKey" in gui_source
    assert "mobaRemoteMonitoringControlCapturedCommand" in gui_source
    assert "apply_follow_terminal_folder_control_route_properties" in gui_source
    assert "mobaFollowTerminalFolderControlRouteKey" in gui_source
    assert "mobaFollowTerminalFolderControlCapturedPlan" in gui_source
    assert "mobaMonitoringTelemetryRouteKey" in gui_source
    assert "mobaMonitoringTelemetryMetricCellKeys" in gui_source
    assert "mobaMonitoringTelemetryRouted" in gui_source
    assert "mobaMonitoringControlLabelFontSize" in gui_source
    assert "mobaMonitoringControlCheckYOffset" in gui_source
    assert "EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME" in checker_source
    assert "EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE" in checker_source
    assert "EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE" in checker_source
    assert "EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE" in checker_source
    assert "expected_moba_remote_monitoring_dock_chrome" in checker_source
    assert "expected_moba_monitoring_telemetry_route" in checker_source
    assert "expected_moba_remote_monitoring_control_route" in checker_source
    assert "expected_moba_follow_terminal_folder_control_route" in checker_source
    assert "expected_moba_monitoring_control_geometry" in checker_source
    assert "monitoring-telemetry-route" in checker_source
    assert "remote-monitoring-control-route" in checker_source
    assert "follow-terminal-folder-control-route" in checker_source
    assert "remote-monitoring-footer-geometry" in checker_source
    assert "moba-monitoring-control-geometry" in checker_source
    assert "mobaMonitoringControlCheckmarkPoints" in checker_source
    assert "mobaRemoteMonitoringStaticHeight" in checker_source
    assert "mobaRemoteMonitoringCompact" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "mobaMonitoringControlStaticX" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "mobaRemoteMonitoringStaticHeight" in geometry_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "chrome.divider_left_inset" in geometry_requirement["source_tokens"]["scripts/render_gui_design_previews.py"]
    assert "mobaMonitoringControlLiveWidth" in control_geometry_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "geometry.checkmark_points" in control_geometry_requirement["source_tokens"]["scripts/render_gui_design_previews.py"]
    assert "mobaMonitoringTelemetryRouteKey" in telemetry_route_requirement["source_tokens"][
        "src/remote_ops_workspace/gui.py"
    ]
    assert "expected_moba_monitoring_telemetry_route" in telemetry_route_requirement["source_tokens"][
        "scripts/check_real_gui_render.py"
    ]
    assert "mobaRemoteMonitoringControlRouteKey" in remote_control_route_requirement["source_tokens"][
        "src/remote_ops_workspace/gui.py"
    ]
    assert "expected_moba_remote_monitoring_control_route" in remote_control_route_requirement["source_tokens"][
        "scripts/check_real_gui_render.py"
    ]
    assert "mobaFollowTerminalFolderControlRouteKey" in follow_control_route_requirement["source_tokens"][
        "src/remote_ops_workspace/gui.py"
    ]
    assert "expected_moba_follow_terminal_folder_control_route" in follow_control_route_requirement["source_tokens"][
        "scripts/check_real_gui_render.py"
    ]
    assert "MobaXterm-style monitoring telemetry route" in docs_source
    assert "MobaXterm-style remote monitoring control route" in docs_source
    assert "MobaXterm-style follow terminal folder control route" in docs_source


def test_mobaxterm_static_renderer_uses_connected_tab_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement_ids = {item["id"] for item in moba["requirements"]}
    geometry_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.connected-tab-geometry"
    )
    action_route_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.connected-session-actions-route"
    )
    action_menu_route_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.connected-session-action-menu-route"
    )

    assert "moba_connected_tab_chrome_items" in renderer_source
    assert "draw_moba_connected_tab" in renderer_source
    assert "draw_moba_tab_icon" in renderer_source
    assert "MobaConnectedTabChromeItem" in state_source
    assert "MobaConnectedSessionActionRoute" in state_source
    assert "moba_connected_session_action_route" in state_source
    assert "mobaConnectedSessionTabContextMenu" in state_source
    assert "inactive-session" in state_source
    assert "terminal-key" in state_source
    assert "moba.connected-tab-geometry" in requirement_ids
    assert "moba.connected-session-actions-route" in requirement_ids
    assert "moba.connected-session-action-menu-route" in requirement_ids
    assert "moba.connected-tab-geometry" in moba["dimension_coverage"]["tabs"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["tabs"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["panes"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["file_monitoring_panels"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.connected-session-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.connected-session-actions-route" in moba["dimension_coverage"]["navigation"]
    assert "moba.connected-session-actions-route" in moba["dimension_coverage"]["panes"]
    assert "moba.connected-session-actions-route" in moba["dimension_coverage"]["tabs"]
    assert "moba.connected-session-actions-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.connected-session-actions-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.connected-session-action-menu-route" in moba["dimension_coverage"]["navigation"]
    assert "moba.connected-session-action-menu-route" in moba["dimension_coverage"]["panes"]
    assert "moba.connected-session-action-menu-route" in moba["dimension_coverage"]["tabs"]
    assert "moba.connected-session-action-menu-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.connected-session-action-menu-route" in moba["dimension_coverage"]["interaction_states"]
    assert "moba.connected-session-identity-route" in moba["dimension_coverage"]["layout"]
    assert "moba.connected-session-identity-route" in moba["dimension_coverage"]["tabs"]
    assert "moba.connected-session-identity-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.connected-session-identity-route" in moba["dimension_coverage"]["status_bars"]
    assert "moba.connected-session-identity-route" in moba["dimension_coverage"]["interaction_states"]
    assert "MobaConnectedTabChromeGeometry" in state_source
    assert "moba_connected_tab_chrome_geometry_for" in renderer_source
    assert "geometry.close_right_offset" in renderer_source
    assert "geometry.gap_after" in renderer_source
    assert "mobaTabStaticWidth" in gui_source
    assert "mobaTabCloseRightOffset" in gui_source
    assert "mobaTabChromeGeometryKeys" in gui_source
    assert "mobaConnectedSessionActionRouteKey" in gui_source
    assert "apply_moba_connected_session_action_route_to_tab" in gui_source
    assert "build_tab_context_menu" in gui_source
    assert "apply_session_action_menu_capture" in gui_source
    assert "session_action_menu_object_name" in gui_source
    assert "EXPECTED_MOBA_TAB_CHROME_GEOMETRY" in checker_source
    assert "EXPECTED_MOBA_CONNECTED_SESSION_ACTION_ROUTE" in checker_source
    assert "check_live_moba_connected_session_action_route" in checker_source
    assert "connected session action menu" in checker_source
    assert "route.menu_object" in checker_source
    assert "expected_moba_connected_session_action_route" in checker_source
    assert "expected_moba_tab_chrome_geometry" in checker_source
    assert "MobaXterm-style connected tab geometry" in docs_source
    assert "MobaXterm-style connected session action route" in docs_source
    assert "MobaXterm-style connected session action menu route" in docs_source
    assert (
        "mobaTabStaticWidth"
        in geometry_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "route.captured_enabled_keys_property"
        in action_route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "apply_session_action_menu_capture"
        in action_menu_route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )
    assert (
        "session_action_menu_object_name"
        in action_menu_route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    )


def test_mobaxterm_static_renderer_uses_right_utility_icons_not_text_placeholders() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement = next(item for item in moba["requirements"] if item["id"] == "moba.right-utility-rail-chrome")
    route_requirement = next(
        item for item in moba["requirements"] if item["id"] == "moba.right-utility-action-route"
    )
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "draw_moba_right_utility_rail" in renderer_source
    assert "draw_moba_right_utility_icon" in renderer_source
    assert "gui_design_moba_right_utility_actions" in renderer_source
    assert "gui_design_moba_right_utility_action_route" in renderer_source
    assert "moba_right_utility_action_route" in renderer_source
    assert "show_moba_clipboard_hints" in renderer_source
    assert "gui_design_moba_right_utility_rail_chrome" in renderer_source
    assert "right_rail.static_width" in renderer_source
    assert "rail.session_edge_icon_x" in renderer_source
    assert "rail.session_edge_top_y" in renderer_source
    assert "action.static_y" in renderer_source
    assert '"gear"' in renderer_source
    assert 'draw_text(draw, "clip"' not in renderer_source
    assert "GuiMobaRightUtilityRailChrome" in design_source
    assert "GUI_DESIGN_MOBA_RIGHT_UTILITY_RAIL_CHROME" in design_source
    assert "GuiMobaRightUtilityActionRoute" in design_source
    assert "GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTION_ROUTE" in design_source
    assert "gui_design_moba_right_utility_action_route" in design_source
    assert "mobaRightUtilityRail" in gui_source
    assert "mobaRightUtilityRailStaticWidth" in gui_source
    assert "mobaRightUtilityRailMargins" in gui_source
    assert "mobaRightUtilityRailSessionEdgeIconSize" in gui_source
    assert "mobaRightUtilityKey" in gui_source
    assert "mobaRightUtilityIconKey" in gui_source
    assert "mobaRightUtilityStaticY" in gui_source
    assert "mobaRightUtilityButtonSize" in gui_source
    assert "mobaRightUtilityRenderSource" in gui_source
    assert "mobaRightUtilityRouteKey" in gui_source
    assert "mobaRightUtilityRouteHandler" in gui_source
    assert "show_moba_clipboard_hints" in gui_source
    assert "show_moba_terminal_settings" in gui_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_KEYS" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_BY_KEY" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME" in checker_source
    assert "EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE" in checker_source
    assert "expected_moba_right_utility_rail_chrome" in checker_source
    assert "expected_moba_right_utility_action_route" in checker_source
    assert "right-utility-rail-chrome" in checker_source
    assert "right-utility-rail-geometry" in checker_source
    assert "right-utility-action-route" in checker_source
    assert "MobaXterm-style right utility rail chrome" in docs_source
    assert "MobaXterm-style right utility action route" in docs_source
    assert "mobaRightUtilityRailStaticWidth" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["layout"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["navigation"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["toolbars"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["connected_session_behavior"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["density"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["spacing"]
    assert "moba.right-utility-action-route" in moba["dimension_coverage"]["interaction_states"]
    assert (
        "GuiMobaRightUtilityActionRoute"
        in route_requirement["source_tokens"]["src/remote_ops_workspace/gui_designs.py"]
    )
    assert "show_moba_clipboard_hints" in route_requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]


def test_mobaxterm_static_renderer_uses_session_edge_shortcut_metadata() -> None:
    criteria = _load_checker().load_json(_load_checker().CRITERIA_PATH)
    moba = criteria["presets"]["mobaxterm"]
    requirement = next(item for item in moba["requirements"] if item["id"] == "moba.session-edge-geometry")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaSessionEdgeAction" in design_source
    assert "GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS" in design_source
    assert "gui_design_moba_session_edge_actions" in renderer_source
    assert "draw_moba_session_edge_controls" in renderer_source
    assert "action.relative_y" in renderer_source
    assert "action.static_size" in renderer_source
    assert "mobaSessionEdgeControls" in gui_source
    assert "mobaSessionEdgeAction" in gui_source
    assert "mobaSessionEdgeIconKey" in gui_source
    assert "mobaSessionEdgeRelativeY" in gui_source
    assert "mobaSessionEdgeButtonSize" in gui_source
    assert "mobaSessionEdgeRenderSource" in gui_source
    assert "EXPECTED_MOBA_SESSION_EDGE_KEYS" in checker_source
    assert "EXPECTED_MOBA_SESSION_EDGE_BY_KEY" in checker_source
    assert "session-edge-geometry" in checker_source
    assert "mobaSessionEdgeButtonSize" in checker_source
    assert "expected_moba_session_edge_actions" in checker_source
    assert "MobaXterm-style session-edge shortcut geometry" in docs_source
    assert "mobaSessionEdgeRelativeY" in requirement["source_tokens"]["src/remote_ops_workspace/gui.py"]


def test_mobaxterm_ssh_banner_uses_shared_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    assert "GuiMobaSshBannerChrome" in design_source
    assert "GuiMobaSshBannerRowGeometry" in design_source
    assert "gui_design_moba_ssh_banner_chrome" in renderer_source
    assert "gui_design_moba_ssh_banner_row_geometry_for" in renderer_source
    assert "draw_centered_text" in renderer_source
    assert "mobaSshBannerTitle" in gui_source
    assert "mobaSshBannerSubtitle" in gui_source
    assert "mobaSshBannerSlot" in gui_source
    assert "mobaSshBannerRowY" in gui_source
    assert "EXPECTED_MOBA_SSH_BANNER_CHROME" in checker_source
    assert "EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY" in checker_source
    assert "expected_moba_ssh_banner_row_geometry" in checker_source


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
    assert "moba.ssh-banner-row-geometry" in requirement_ids
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
    assert "MobaXterm-style SSH banner row geometry" in docs_source


def test_mobaxterm_terminal_transcript_uses_shared_connected_state() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "MobaTerminalTranscriptLine" in state_source
    assert "build_moba_terminal_transcript" in state_source
    assert "terminal_transcript" in state_source
    assert "GuiMobaTerminalTranscriptRowGeometry" in design_source
    assert "state.terminal_transcript" in renderer_source
    assert "line.tone" in renderer_source
    assert "gui_design_moba_terminal_transcript_row_geometry_for" in renderer_source
    assert "geometry.font_size" in renderer_source
    assert "apply_terminal_transcript_evidence" in gui_source
    assert "mobaTerminalTranscriptKeys" in gui_source
    assert "mobaTerminalTranscriptTones" in gui_source
    assert "mobaPlainTerminalMode" in gui_source
    assert "mobaTerminalTranscriptGeometryKeys" in gui_source
    assert "EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS" in checker_source
    assert "expected_moba_terminal_transcript" in checker_source
    assert "EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY" in checker_source
    assert "expected_moba_terminal_transcript_row_geometry" in checker_source
    assert "terminal-transcript-geometry" in checker_source
    assert "MobaXterm-style terminal transcript geometry" in docs_source


def test_mobaxterm_bottom_status_uses_shared_chrome_metadata() -> None:
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GuiMobaStatusBarChrome" in design_source
    assert "GUI_DESIGN_MOBA_STATUS_SEGMENTS" in design_source
    assert "segment_start_right_offset" in design_source
    assert "marker_right_inset" in design_source
    assert "gui_design_moba_status_bar_chrome" in renderer_source
    assert "gui_design_moba_status_segments" in renderer_source
    assert "chrome.notice_x" in renderer_source
    assert "chrome.segment_start_right_offset" in renderer_source
    assert "productStatusNotice" in gui_source
    assert "productStatusMarker" in gui_source
    assert "productStatusKey" in gui_source
    assert "mobaStatusNoticeX" in gui_source
    assert "mobaStatusMarkerRightInset" in gui_source
    assert "EXPECTED_MOBA_STATUS_KEYS" in checker_source
    assert "EXPECTED_MOBA_STATUS_CHROME" in checker_source
    assert "mobaStatusSegmentStartRightOffset" in checker_source
    assert "expected_moba_status_chrome" in checker_source
    assert "MobaXterm-style bottom status geometry" in docs_source


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
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    state_source = Path("src/remote_ops_workspace/moba_connected.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "MobaTelemetrySegment" in state_source
    assert "MobaConnectedSessionRoute" in state_source
    assert "moba_connected_session_route" in state_source
    assert "active-tab-to-connected-workspace" in state_source
    assert "MobaConnectedSessionIdentityRoute" in state_source
    assert "moba_connected_session_identity_route" in state_source
    assert "title-tab-banner-terminal-telemetry-identity" in state_source
    assert "MobaTelemetryCellGeometry" in state_source
    assert "moba_connected_profile_label" in state_source
    assert "moba_telemetry_cell_geometry" in state_source
    assert "moba_telemetry_cell_geometry_for" in renderer_source
    assert "moba_connected_session_route" in renderer_source
    assert "connected_route.reference_tab_label" in renderer_source
    assert "connected_route.telemetry_identity_cell_key" in renderer_source
    assert "moba_connected_session_identity_route" in renderer_source
    assert "identity_route.terminal_prompt" in renderer_source
    assert "identity_route.telemetry_target" in renderer_source
    assert "geometry.label_x" in renderer_source
    assert "moba_connected_window_title" in gui_source
    assert "moba_connected_tab_label" in gui_source
    assert "mobaConnectedRouteKey" in gui_source
    assert "mobaConnectedRouteActiveTabLabel" in gui_source
    assert "mobaConnectedRouteTelemetryBarObject" in gui_source
    assert "mobaConnectedIdentityRouteKey" in gui_source
    assert "mobaConnectedIdentityWindowTitle" in gui_source
    assert "mobaConnectedIdentityTelemetryTarget" in gui_source
    assert "moba_telemetry_cells" in gui_source
    assert "mobaTelemetryGeometryKeys" in gui_source
    assert "mobaTelemetryCellStaticX" in gui_source
    assert "mobaTelemetryLabelX" in gui_source
    assert "telemetry_icon_pixmap" in gui_source
    assert "mobaTelemetryIconRender" in gui_source
    assert "mobaTelemetryCellWidth" in gui_source
    assert "mobaTelemetryKey" in gui_source
    assert "EXPECTED_MOBA_TELEMETRY_CELL_KEYS" in live_checker_source
    assert "EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY" in live_checker_source
    assert "expected_moba_telemetry_cells" in live_checker_source
    assert "expected_moba_telemetry_cell_geometry" in live_checker_source
    assert "EXPECTED_MOBA_CONNECTED_SESSION_ROUTE" in live_checker_source
    assert "connected-session-route" in live_checker_source
    assert "expected_moba_connected_session_route" in live_checker_source
    assert "EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE" in live_checker_source
    assert "connected-session-identity-route" in live_checker_source
    assert "expected_moba_connected_session_identity_route" in live_checker_source
    assert "bottom-telemetry-geometry" in live_checker_source
    assert "must not be a text placeholder" in live_checker_source
    assert "window title must be connected target label" in live_checker_source
    assert "MobaXterm-style bottom telemetry geometry" in docs_source
    assert "MobaXterm-style connected-session route" in docs_source
    assert "MobaXterm-style connected-session identity route" in docs_source


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
    moba = criteria["presets"]["mobaxterm"]
    assert "moba.session-tree-geometry" in {item["id"] for item in moba["requirements"]}
    assert "moba.session-tree-geometry" in moba["dimension_coverage"]["session_trees"]
    assert "moba.session-tree-geometry" in moba["dimension_coverage"]["sidebars"]
    assert "moba.session-tree-geometry" in moba["dimension_coverage"]["density"]
    assert "moba.session-tree-geometry" in moba["dimension_coverage"]["spacing"]


def test_live_and_static_renderers_share_session_tree_copy() -> None:
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    assert "GUI_DESIGN_TREE_ROOT_COPY" in design_source
    assert "GUI_DESIGN_TREE_ROWS" in design_source
    assert "GUI_DESIGN_TREE_ROOT_ICONS" in design_source
    assert "GUI_DESIGN_TREE_ROW_ICONS" in design_source
    assert "GuiMobaSessionTreeChrome" in design_source
    assert "GUI_DESIGN_MOBA_SESSION_TREE_CHROME" in design_source
    assert "profile_group_label" in gui_source
    assert "profile_tree_tooltip" in gui_source
    assert "apply_profile_tree_icon" in gui_source
    assert "GENERATED_PROFILE_TREE_ICON_PRESETS = {\"mobaxterm\"" in gui_source
    assert "mobaSessionTreeProfileRowHeight" in gui_source
    assert "TREE_ROW_STATIC_HEIGHT_ROLE" in gui_source
    assert "gui_design_tree_rows" in renderer_source
    assert "gui_design_tree_row_icon_key" in renderer_source
    assert "gui_design_moba_session_tree_chrome" in renderer_source
    assert "chrome.profile_target_x" in renderer_source
    assert "EXPECTED_MOBA_SESSION_TREE_CHROME" in live_checker_source
    assert "moba-session-tree-geometry" in live_checker_source
    assert "expected_moba_session_tree_chrome" in live_checker_source
    assert "MobaXterm-style saved-session tree geometry" in docs_source


def test_static_renderer_tracks_product_specific_sidebar_glyphs() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.session-tree-geometry",
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
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    remmina_requirements = {item["id"] for item in criteria["presets"]["remmina"]["requirements"]}
    assert "remmina.viewer-controls" in remmina_requirements
    assert "remmina.viewer-control-chrome" in remmina_requirements
    assert "remmina.profile-list-geometry" in remmina_requirements
    assert "remmina.profile-viewer-route" in remmina_requirements
    assert "remmina.profile-filter-route" in remmina_requirements
    assert "remmina.clipboard-route" in remmina_requirements
    assert "remmina.screenshot-route" in remmina_requirements
    assert "remmina.sftp-transfer-route" in remmina_requirements
    assert "remmina.profile-viewer-route" in criteria["presets"]["remmina"]["dimension_coverage"]["tabs"]
    assert "remmina.profile-viewer-route" in criteria["presets"]["remmina"]["dimension_coverage"]["connected_session_behavior"]
    assert "remmina.profile-viewer-route" in criteria["presets"]["remmina"]["dimension_coverage"]["interaction_states"]
    assert "remmina.profile-filter-route" in criteria["presets"]["remmina"]["dimension_coverage"]["tabs"]
    assert "remmina.profile-filter-route" in criteria["presets"]["remmina"]["dimension_coverage"]["session_trees"]
    assert (
        "remmina.profile-filter-route"
        in criteria["presets"]["remmina"]["dimension_coverage"]["connected_session_behavior"]
    )
    assert "remmina.profile-filter-route" in criteria["presets"]["remmina"]["dimension_coverage"]["interaction_states"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["tabs"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["toolbars"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["connected_session_behavior"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["file_monitoring_panels"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["status_bars"]
    assert "remmina.clipboard-route" in criteria["presets"]["remmina"]["dimension_coverage"]["interaction_states"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["tabs"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["toolbars"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["connected_session_behavior"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["file_monitoring_panels"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["status_bars"]
    assert "remmina.screenshot-route" in criteria["presets"]["remmina"]["dimension_coverage"]["interaction_states"]
    for dimension_key in [
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
    ]:
        assert "remmina.sftp-transfer-route" in criteria["presets"]["remmina"]["dimension_coverage"][dimension_key]
    mremoteng_requirements = {item["id"] for item in criteria["presets"]["mremoteng"]["requirements"]}
    assert "mremoteng.top-chrome" in mremoteng_requirements
    assert "mremoteng.document-controls" in mremoteng_requirements
    assert "mremoteng.document-control-chrome" in mremoteng_requirements
    assert "mremoteng.property-grid-chrome" in mremoteng_requirements
    assert "mremoteng.connection-document-route" in mremoteng_requirements
    assert "mremoteng.document-filter-route" in mremoteng_requirements
    assert "mremoteng.inheritance-route" in mremoteng_requirements
    assert "mremoteng.top-chrome" in criteria["presets"]["mremoteng"]["dimension_coverage"]["toolbars"]
    assert "mremoteng.connection-document-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["tabs"]
    assert "mremoteng.connection-document-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["session_trees"]
    assert "mremoteng.connection-document-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["connected_session_behavior"]
    assert "mremoteng.connection-document-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["interaction_states"]
    assert "mremoteng.document-filter-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["tabs"]
    assert "mremoteng.document-filter-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["session_trees"]
    assert (
        "mremoteng.document-filter-route"
        in criteria["presets"]["mremoteng"]["dimension_coverage"]["connected_session_behavior"]
    )
    assert "mremoteng.document-filter-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["interaction_states"]
    assert "mremoteng.inheritance-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["layout"]
    assert "mremoteng.inheritance-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["tabs"]
    assert "mremoteng.inheritance-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["session_trees"]
    assert (
        "mremoteng.inheritance-route"
        in criteria["presets"]["mremoteng"]["dimension_coverage"]["connected_session_behavior"]
    )
    assert "mremoteng.inheritance-route" in criteria["presets"]["mremoteng"]["dimension_coverage"]["interaction_states"]
    assert "GuiMRemoteNgTopChrome" in design_source
    assert "gui_design_mremoteng_top_chrome" in design_source
    assert "GuiMRemoteNgDocumentControl" in design_source
    assert "gui_design_mremoteng_document_controls" in design_source
    assert "GuiMRemoteNgPropertyGridChrome" in design_source
    assert "gui_design_mremoteng_property_grid_chrome" in design_source
    assert "GuiMRemoteNgConnectionDocumentRoute" in design_source
    assert "GuiMRemoteNgDocumentFilterRoute" in design_source
    assert "GUI_DESIGN_MREMOTENG_DOCUMENT_FILTER_ROUTE" in design_source
    assert "GuiMRemoteNgInheritanceRoute" in design_source
    assert "GUI_DESIGN_MREMOTENG_INHERITANCE_ROUTE" in design_source
    assert "gui_design_mremoteng_connection_document_route" in design_source
    assert "gui_design_mremoteng_document_filter_route" in design_source
    assert "gui_design_mremoteng_inheritance_route" in design_source
    assert "mRemoteNgTopToolbarIconKey" in gui_source
    assert "build_mremoteng_document_controls_evidence" in gui_source
    assert "mRemoteNgDocumentControlKey" in gui_source
    assert "mRemoteNgDocumentRenderSource" in gui_source
    assert "mRemoteNgConnectionRouteKey" in gui_source
    assert "mRemoteNgConnectionRouteActive" in gui_source
    assert "mRemoteNgDocumentFilterRouteKey" in gui_source
    assert "mRemoteNgInheritanceRouteKey" in gui_source
    assert "mRemoteNgInheritanceRouteInheritedValue" in gui_source
    assert "MREMOTENG_FILTER_ROUTE_KEY_ROLE" in gui_source
    assert "mremoteng_document_control_icon" in gui_source
    assert "build_mremoteng_property_grid_evidence" in gui_source
    assert "mRemoteNgPropertyRowKey" in gui_source
    assert "GuiRemminaViewerControl" in design_source
    assert "GuiRemminaProfileListChrome" in design_source
    assert "GuiRemminaProfileViewerRoute" in design_source
    assert "GuiRemminaProfileFilterRoute" in design_source
    assert "GUI_DESIGN_REMMINA_PROFILE_FILTER_ROUTE" in design_source
    assert "GuiRemminaClipboardRoute" in design_source
    assert "GUI_DESIGN_REMMINA_CLIPBOARD_ROUTE" in design_source
    assert "GuiRemminaScreenshotRoute" in design_source
    assert "GUI_DESIGN_REMMINA_SCREENSHOT_ROUTE" in design_source
    assert "GuiRemminaSftpTransferRoute" in design_source
    assert "GUI_DESIGN_REMMINA_SFTP_TRANSFER_ROUTE" in design_source
    assert "gui_design_remmina_profile_filter_route" in design_source
    assert "gui_design_remmina_clipboard_route" in design_source
    assert "gui_design_remmina_screenshot_route" in design_source
    assert "gui_design_remmina_sftp_transfer_route" in design_source
    assert "gui_design_remmina_profile_viewer_route" in design_source
    assert "static_width" in design_source
    assert "live_button_height" in design_source
    assert "static_row_start_y" in design_source
    assert "gui_design_remmina_viewer_controls" in design_source
    assert "build_remmina_viewer_controls_evidence" in gui_source
    assert "remmina_profile_filter" in gui_source
    assert "remminaViewerControlKey" in gui_source
    assert "remminaViewerControlStaticWidth" in gui_source
    assert "remminaViewerControlRenderSource" in gui_source
    assert "remminaProfileViewerRouteKey" in gui_source
    assert "remminaProfileViewerRouteActive" in gui_source
    assert "remminaProfileFilterRouteKey" in gui_source
    assert "filter_remmina_profile_rows" in gui_source
    assert "filter_input.textChanged.connect" in gui_source
    assert "remminaClipboardRouteKey" in gui_source
    assert "remminaClipboardRouteActive" in gui_source
    assert "remminaClipboardRouteState" in gui_source
    assert "remminaScreenshotRouteKey" in gui_source
    assert "remminaScreenshotRouteActive" in gui_source
    assert "remminaScreenshotRouteArtifact" in gui_source
    assert "remminaSftpTransferRouteKey" in gui_source
    assert "remminaSftpTransferRoutePath" in gui_source
    assert "remminaSftpTransferRouteQueueState" in gui_source
    assert "remminaProfileStaticRowStartY" in gui_source
    assert "remminaProfileLiveRowMinHeight" in gui_source
    assert "remminaProfileFilter" in live_checker_source
    assert "draw_remmina_viewer_control_icon" in renderer_source
    assert "gui_design_remmina_viewer_controls" in renderer_source
    assert "route.viewer_control_key" in renderer_source
    assert "route.active_tab_label" in renderer_source
    assert "gui_design_remmina_profile_filter_route" in renderer_source
    assert "remmina_profile_filter_route.expected_query" in renderer_source
    assert "gui_design_remmina_clipboard_route" in renderer_source
    assert "clipboard_route.viewer_control_key" in renderer_source
    assert "clipboard_route.status_segment" in renderer_source
    assert "gui_design_remmina_screenshot_route" in renderer_source
    assert "screenshot_route.viewer_control_key" in renderer_source
    assert "screenshot_route.capture_artifact" in renderer_source
    assert "gui_design_remmina_sftp_transfer_route" in renderer_source
    assert "draw_remmina_sftp_transfer_panel" in renderer_source
    assert "sftp_transfer_route.active_row_name" in renderer_source
    assert "control.static_width" in renderer_source
    assert "control.static_icon_size" in renderer_source
    assert "chrome.static_row_step" in renderer_source
    assert "profile-filter-focus" in visual_metrics_source
    assert "active-viewer-tab" in visual_metrics_source
    assert "transfer-toolbar-checked" in visual_metrics_source
    assert "viewer-control-glyph-cluster" in visual_metrics_source
    assert "check_live_remmina_viewer_controls" in live_checker_source
    assert "remmina-viewer-control-geometry" in live_checker_source
    assert "remmina-profile-list-geometry" in live_checker_source
    assert "EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE" in live_checker_source
    assert "remmina-profile-viewer-route" in live_checker_source
    assert "expected_remmina_profile_viewer_route" in live_checker_source
    assert "EXPECTED_REMMINA_PROFILE_FILTER_ROUTE" in live_checker_source
    assert "check_live_remmina_profile_filter_route" in live_checker_source
    assert "remmina-profile-filter-route" in live_checker_source
    assert "expected_remmina_profile_filter_route" in live_checker_source
    assert "EXPECTED_REMMINA_CLIPBOARD_ROUTE" in live_checker_source
    assert "check_live_remmina_clipboard_route" in live_checker_source
    assert "remmina-clipboard-route" in live_checker_source
    assert "expected_remmina_clipboard_route" in live_checker_source
    assert "EXPECTED_REMMINA_SCREENSHOT_ROUTE" in live_checker_source
    assert "check_live_remmina_screenshot_route" in live_checker_source
    assert "remmina-screenshot-route" in live_checker_source
    assert "expected_remmina_screenshot_route" in live_checker_source
    assert "EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE" in live_checker_source
    assert "check_live_remmina_sftp_transfer_route" in live_checker_source
    assert "remmina-sftp-transfer-route" in live_checker_source
    assert "expected_remmina_sftp_transfer_route" in live_checker_source
    assert "Remmina-style profile-viewer route" in docs_source
    assert "Remmina-style profile filter route" in docs_source
    assert "Remmina-style clipboard route" in docs_source
    assert "Remmina-style screenshot route" in docs_source
    assert "Remmina-style SFTP transfer route" in docs_source
    assert "remminaProfileLiveRowMinHeight" in live_checker_source
    assert "draw_mremoteng_title_bar" in renderer_source
    assert "draw_mremoteng_toolbar" in renderer_source
    assert "gui_design_mremoteng_top_chrome" in renderer_source
    assert "draw_mremoteng_document_toolbar" in renderer_source
    assert "gui_design_mremoteng_document_controls" in renderer_source
    assert "draw_mremoteng_document_control_icon" in renderer_source
    assert "draw_mremoteng_property_grid" in renderer_source
    assert "gui_design_mremoteng_property_grid_chrome" in renderer_source
    assert "route.document_control_key" in renderer_source
    assert "route.active_tab_label" in renderer_source
    assert "gui_design_mremoteng_document_filter_route" in renderer_source
    assert "mremoteng_document_filter_route.expected_query" in renderer_source
    assert "gui_design_mremoteng_inheritance_route" in renderer_source
    assert "inheritance_route.property_row_key" in renderer_source
    assert "inheritance_route.inherited_value" in renderer_source
    assert "check_live_mremoteng_top_chrome" in live_checker_source
    assert "mremoteng-top-chrome" in live_checker_source
    assert "check_live_mremoteng_document_controls" in live_checker_source
    assert "mremoteng-document-control-geometry" in live_checker_source
    assert "mRemoteNgDocumentRenderSource" in live_checker_source
    assert "check_live_mremoteng_property_grid" in live_checker_source
    assert "EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE" in live_checker_source
    assert "mremoteng-connection-document-route" in live_checker_source
    assert "expected_mremoteng_connection_document_route" in live_checker_source
    assert "EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE" in live_checker_source
    assert "check_live_mremoteng_document_filter_route" in live_checker_source
    assert "mremoteng-document-filter-route" in live_checker_source
    assert "expected_mremoteng_document_filter_route" in live_checker_source
    assert "EXPECTED_MREMOTENG_INHERITANCE_ROUTE" in live_checker_source
    assert "check_live_mremoteng_inheritance_route" in live_checker_source
    assert "mremoteng-inheritance-route" in live_checker_source
    assert "expected_mremoteng_inheritance_route" in live_checker_source
    assert "mRemoteNG-style connection-document route" in docs_source
    assert "mRemoteNG-style document filter route" in docs_source
    assert "mRemoteNG-style inheritance route" in docs_source
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
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")

    securecrt_requirements = {item["id"] for item in criteria["presets"]["securecrt"]["requirements"]}
    assert "securecrt.command-window" in securecrt_requirements
    assert "securecrt.command-window-chrome" in securecrt_requirements
    assert "securecrt.command-window-send-route" in securecrt_requirements
    assert "securecrt.session-manager-chrome" in securecrt_requirements
    assert "securecrt.session-manager-route" in securecrt_requirements
    assert "securecrt.session-manager-filter-route" in securecrt_requirements
    assert "securecrt.sftp-tab-route" in securecrt_requirements
    assert "securecrt.sftp-browser-route" in securecrt_requirements
    assert "securecrt.top-chrome" in securecrt_requirements
    assert "securecrt.session-status-geometry" in securecrt_requirements
    assert "securecrt.command-window-geometry" in securecrt_requirements
    assert "securecrt.command-window-send-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["layout"]
    assert "securecrt.command-window-send-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["connected_session_behavior"]
    assert "securecrt.command-window-send-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["interaction_states"]
    assert "securecrt.session-manager-geometry" in securecrt_requirements
    assert "securecrt.session-manager-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["tabs"]
    assert "securecrt.session-manager-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["session_trees"]
    assert "securecrt.session-manager-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["connected_session_behavior"]
    assert "securecrt.session-manager-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["interaction_states"]
    assert "securecrt.session-manager-filter-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["navigation"]
    assert "securecrt.session-manager-filter-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["session_trees"]
    assert "securecrt.session-manager-filter-route" in criteria["presets"]["securecrt"]["dimension_coverage"]["interaction_states"]
    for dimension_key in [
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
    ]:
        assert "securecrt.sftp-tab-route" in criteria["presets"]["securecrt"]["dimension_coverage"][
            dimension_key
        ]
        assert "securecrt.sftp-browser-route" in criteria["presets"]["securecrt"]["dimension_coverage"][
            dimension_key
        ]
    assert "securecrt.top-chrome" in criteria["presets"]["securecrt"]["dimension_coverage"]["toolbars"]
    termius_requirements = {item["id"] for item in criteria["presets"]["termius"]["requirements"]}
    assert "termius.workflow-cards" in termius_requirements
    assert "termius.hosts-sidebar-chrome" in termius_requirements
    assert "termius.header-chip-chrome" in termius_requirements
    assert "termius.host-identity-geometry" in termius_requirements
    assert "termius.sync-route" in termius_requirements
    assert "termius.host-selection-route" in termius_requirements
    assert "termius.port-forward-route" in termius_requirements
    assert "termius.snippet-route" in termius_requirements
    assert "termius.files-browser-route" in termius_requirements
    assert "termius.host-selection-route" in criteria["presets"]["termius"]["dimension_coverage"]["tabs"]
    assert "termius.host-selection-route" in criteria["presets"]["termius"]["dimension_coverage"]["session_trees"]
    assert "termius.host-selection-route" in criteria["presets"]["termius"]["dimension_coverage"]["connected_session_behavior"]
    assert "termius.sync-route" in criteria["presets"]["termius"]["dimension_coverage"]["connected_session_behavior"]
    assert "termius.sync-route" in criteria["presets"]["termius"]["dimension_coverage"]["interaction_states"]
    assert "termius.port-forward-route" in criteria["presets"]["termius"]["dimension_coverage"]["tabs"]
    assert "termius.port-forward-route" in criteria["presets"]["termius"]["dimension_coverage"]["toolbars"]
    assert "termius.port-forward-route" in criteria["presets"]["termius"]["dimension_coverage"]["status_bars"]
    assert "termius.port-forward-route" in criteria["presets"]["termius"]["dimension_coverage"]["connected_session_behavior"]
    assert "termius.snippet-route" in criteria["presets"]["termius"]["dimension_coverage"]["tabs"]
    assert "termius.snippet-route" in criteria["presets"]["termius"]["dimension_coverage"]["panes"]
    assert "termius.snippet-route" in criteria["presets"]["termius"]["dimension_coverage"]["connected_session_behavior"]
    for dimension_key in [
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
    ]:
        assert "termius.files-browser-route" in criteria["presets"]["termius"]["dimension_coverage"][
            dimension_key
        ]
    assert "GuiSecureCrtCommandWindowChrome" in design_source
    assert "GuiSecureCrtCommandWindowSendRoute" in design_source
    assert "GUI_DESIGN_SECURECRT_COMMAND_WINDOW_SEND_ROUTE" in design_source
    assert "static_control_y" in design_source
    assert "gui_design_securecrt_command_window_chrome" in design_source
    assert "gui_design_securecrt_command_window_send_route" in design_source
    assert "GuiSecureCrtSessionManagerChrome" in design_source
    assert "GuiSecureCrtSessionManagerRoute" in design_source
    assert "GuiSecureCrtSessionManagerFilterRoute" in design_source
    assert "GuiSecureCrtSftpTabRoute" in design_source
    assert "GuiSecureCrtSftpBrowserRoute" in design_source
    assert "GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE" in design_source
    assert "GUI_DESIGN_SECURECRT_SESSION_MANAGER_FILTER_ROUTE" in design_source
    assert "GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE" in design_source
    assert "GUI_DESIGN_SECURECRT_SFTP_BROWSER_ROUTE" in design_source
    assert "static_button_size" in design_source
    assert "live_button_size" in design_source
    assert "render_source" in design_source
    assert "GuiSecureCrtSessionStatusStrip" in design_source
    assert "static_cell_start_x" in design_source
    assert "gui_design_securecrt_session_manager_chrome" in design_source
    assert "gui_design_securecrt_session_manager_route" in design_source
    assert "gui_design_securecrt_session_manager_filter_route" in design_source
    assert "gui_design_securecrt_sftp_tab_route" in design_source
    assert "gui_design_securecrt_sftp_browser_route" in design_source
    assert "GuiSecureCrtTopChrome" in design_source
    assert "gui_design_securecrt_top_chrome" in design_source
    assert "GuiTermiusHeaderChip" in design_source
    assert "GuiTermiusHostsChrome" in design_source
    assert "GuiTermiusHostIdentityStrip" in design_source
    assert "GuiTermiusSyncRoute" in design_source
    assert "GUI_DESIGN_TERMIUS_SYNC_ROUTE" in design_source
    assert "GuiTermiusHostSelectionRoute" in design_source
    assert "GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE" in design_source
    assert "GuiTermiusPortForwardRoute" in design_source
    assert "GUI_DESIGN_TERMIUS_PORT_FORWARD_ROUTE" in design_source
    assert "GuiTermiusSnippetRoute" in design_source
    assert "GUI_DESIGN_TERMIUS_SNIPPET_ROUTE" in design_source
    assert "GuiTermiusFilesBrowserRoute" in design_source
    assert "GUI_DESIGN_TERMIUS_FILES_BROWSER_ROUTE" in design_source
    assert "static_cell_start_x" in design_source
    assert "gui_design_termius_hosts_chrome" in design_source
    assert "gui_design_termius_header_chips" in design_source
    assert "gui_design_termius_sync_route" in design_source
    assert "gui_design_termius_host_selection_route" in design_source
    assert "gui_design_termius_port_forward_route" in design_source
    assert "gui_design_termius_snippet_route" in design_source
    assert "gui_design_termius_files_browser_route" in design_source
    assert "build_securecrt_command_window_evidence" in gui_source
    assert "secureCrtCommandStaticControlY" in gui_source
    assert "secureCrtCommandLiveSendMinWidth" in gui_source
    assert "secureCrtCommandRouteKey" in gui_source
    assert "secureCrtCommandRouteCommand" in gui_source
    assert "secureCrtCommandRouteSendLabel" in gui_source
    assert "build_securecrt_session_manager_chrome" in gui_source
    assert "secureCrtSessionManagerLiveButtonSize" in gui_source
    assert "secureCrtSessionManagerRenderSource" in gui_source
    assert "secureCrtSessionRouteKey" in gui_source
    assert "secureCrtSessionRouteActive" in gui_source
    assert "secureCrtSessionRouteActiveTab" in gui_source
    assert "secureCrtSessionFilterRouteKey" in gui_source
    assert "SECURECRT_FILTER_ROUTE_MATCHED_ROLE" in gui_source
    assert "secureCrtSftpTabRouteKey" in gui_source
    assert "SECURECRT_SFTP_ROUTE_TAB_ROLE" in gui_source
    assert "secureCrtSftpTabRouteTransferState" in gui_source
    assert "secureCrtSftpBrowserRouteKey" in gui_source
    assert "secureCrtSftpBrowserPath" in gui_source
    assert "secureCrtSftpBrowserQueueState" in gui_source
    assert "securecrt_session_manager_action_icon" in gui_source
    assert "secureCrtSessionStatusStaticCellStartX" in gui_source
    assert "secureCrtSessionStatusLiveCellHeight" in gui_source
    assert "configure_menu_bar_for_design" in gui_source
    assert "secureCrtTopToolbarIconKey" in gui_source
    assert "build_termius_hosts_chrome" in gui_source
    assert "termiusHostSearch" in gui_source
    assert "build_termius_header_chips_evidence" in gui_source
    assert "termiusHeaderChipKey" in gui_source
    assert "termiusHostIdentityStaticCellStartX" in gui_source
    assert "termiusHostIdentityLiveCellHeight" in gui_source
    assert "termiusSyncRouteKey" in gui_source
    assert "termiusSyncRouteState" in gui_source
    assert "termiusSyncRouteHeaderChipKey" in gui_source
    assert "termiusHostRouteKey" in gui_source
    assert "termiusHostRouteActiveTab" in gui_source
    assert "termiusPortForwardRouteKey" in gui_source
    assert "termiusPortForwardRouteIdentityValue" in gui_source
    assert "termiusPortForwardRouteState" in gui_source
    assert "termiusSnippetRouteKey" in gui_source
    assert "termiusSnippetRouteCommand" in gui_source
    assert "termiusSnippetRouteIdentityValue" in gui_source
    assert "termiusFilesRouteKey" in gui_source
    assert "termiusFilesRoutePath" in gui_source
    assert "termiusFilesRouteQueueState" in gui_source
    assert "TERMIUS_HOST_ROUTE_SELECTED_ROLE" in gui_source
    assert "secureCrtCommandWindowKey" in gui_source
    assert "secureCrtSessionManagerActionKey" in gui_source
    assert "draw_securecrt_command_window" in renderer_source
    assert "chrome.static_send_width" in renderer_source
    assert "draw_securecrt_session_manager_chrome" in renderer_source
    assert "draw_securecrt_session_manager_action_icon" in renderer_source
    assert "action.static_button_size" in renderer_source
    assert "draw_securecrt_session_tree" in renderer_source
    assert "draw_securecrt_session_status_strip" in renderer_source
    assert "chrome.static_cell_gap" in renderer_source
    assert "gui_design_tree_root_copy" in renderer_source
    assert "gui_design_securecrt_command_window_chrome" in renderer_source
    assert "gui_design_securecrt_command_window_send_route" in renderer_source
    assert "send_route.command_input_object" in renderer_source
    assert "send_route.send_control_object" in renderer_source
    assert "gui_design_securecrt_session_manager_chrome" in renderer_source
    assert "gui_design_securecrt_session_manager_route" in renderer_source
    assert "gui_design_securecrt_session_manager_filter_route" in renderer_source
    assert "gui_design_securecrt_sftp_tab_route" in renderer_source
    assert "gui_design_securecrt_sftp_browser_route" in renderer_source
    assert "draw_securecrt_sftp_browser" in renderer_source
    assert "route.session_manager_action_key" in renderer_source
    assert "route.active_tab_label" in renderer_source
    assert "filter_route.expected_query" in renderer_source
    assert "securecrt_sftp_tab_route.status_field_key" in renderer_source
    assert "securecrt_sftp_tab_route.transfer_state" in renderer_source
    assert "securecrt_sftp_browser_route.active_row_name" in renderer_source
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
    assert "draw_termius_host_identity_strip" in renderer_source
    assert "strip.static_cell_gap" in renderer_source
    assert "gui_design_termius_hosts_chrome" in renderer_source
    assert "gui_design_termius_sync_route" in renderer_source
    assert "gui_design_termius_host_selection_route" in renderer_source
    assert "gui_design_termius_port_forward_route" in renderer_source
    assert "gui_design_termius_snippet_route" in renderer_source
    assert "gui_design_termius_files_browser_route" in renderer_source
    assert "sync_route.hosts_action_key" in renderer_source
    assert "sync_route.identity_field_key" in renderer_source
    assert "host_route.active_tab_label" in renderer_source
    assert "host_route.identity_field_key" in renderer_source
    assert "port_forward_route.identity_field_key" in renderer_source
    assert "port_forward_route.forward_value" in renderer_source
    assert "snippet_route.identity_field_key" in renderer_source
    assert "snippet_route.snippet_command" in renderer_source
    assert "draw_termius_files_browser" in renderer_source
    assert "termius_files_browser_route.active_row_name" in renderer_source
    assert "gui_design_termius_header_chips" in renderer_source
    assert "check_live_securecrt_command_window" in live_checker_source
    assert "check_live_securecrt_session_manager_chrome" in live_checker_source
    assert "check_live_securecrt_top_chrome" in live_checker_source
    assert "check_securecrt_tree_icon_metadata" in live_checker_source
    assert "EXPECTED_SECURECRT_TREE_ICON_KEYS" in live_checker_source
    assert "securecrt-top-chrome" in live_checker_source
    assert "securecrt-tree-icons" in live_checker_source
    assert "securecrt-session-status-geometry" in live_checker_source
    assert "securecrt-session-manager-geometry" in live_checker_source
    assert "securecrt-session-manager-route" in live_checker_source
    assert "securecrt-session-manager-filter-route" in live_checker_source
    assert "check_live_securecrt_sftp_tab_route" in live_checker_source
    assert "EXPECTED_SECURECRT_SFTP_TAB_ROUTE" in live_checker_source
    assert "securecrt-sftp-tab-route" in live_checker_source
    assert "expected_securecrt_sftp_tab_route" in live_checker_source
    assert "check_live_securecrt_sftp_browser_route" in live_checker_source
    assert "EXPECTED_SECURECRT_SFTP_BROWSER_ROUTE" in live_checker_source
    assert "securecrt-sftp-browser-route" in live_checker_source
    assert "expected_securecrt_sftp_browser_route" in live_checker_source
    assert "secureCrtSessionManagerRenderSource" in live_checker_source
    assert "secureCrtSessionStatusLiveCellHeight" in live_checker_source
    assert "securecrt-command-window-geometry" in live_checker_source
    assert "securecrt-command-window-send-route" in live_checker_source
    assert "EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE" in live_checker_source
    assert "EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE" in live_checker_source
    assert "EXPECTED_SECURECRT_SESSION_MANAGER_FILTER_ROUTE" in live_checker_source
    assert "expected_securecrt_session_manager_route" in live_checker_source
    assert "expected_securecrt_session_manager_filter_route" in live_checker_source
    assert "check_live_securecrt_session_manager_route" in live_checker_source
    assert "check_live_securecrt_session_manager_filter_route" in live_checker_source
    assert "expected_securecrt_command_window_send_route" in live_checker_source
    assert "secureCrtCommandLiveSendMinWidth" in live_checker_source
    assert "check_live_termius_hosts_chrome" in live_checker_source
    assert "termius-hosts-chrome" in live_checker_source
    assert "check_live_termius_header_chips" in live_checker_source
    assert "termius-host-identity-geometry" in live_checker_source
    assert "termiusHostIdentityLiveCellHeight" in live_checker_source
    assert "check_live_termius_sync_route" in live_checker_source
    assert "EXPECTED_TERMIUS_SYNC_ROUTE" in live_checker_source
    assert "expected_termius_sync_route" in live_checker_source
    assert "check_live_termius_host_selection_route" in live_checker_source
    assert "EXPECTED_TERMIUS_HOST_SELECTION_ROUTE" in live_checker_source
    assert "expected_termius_host_selection_route" in live_checker_source
    assert "check_live_termius_port_forward_route" in live_checker_source
    assert "EXPECTED_TERMIUS_PORT_FORWARD_ROUTE" in live_checker_source
    assert "termius-port-forward-route" in live_checker_source
    assert "expected_termius_port_forward_route" in live_checker_source
    assert "check_live_termius_snippet_route" in live_checker_source
    assert "EXPECTED_TERMIUS_SNIPPET_ROUTE" in live_checker_source
    assert "termius-snippet-route" in live_checker_source
    assert "expected_termius_snippet_route" in live_checker_source
    assert "check_live_termius_files_browser_route" in live_checker_source
    assert "EXPECTED_TERMIUS_FILES_BROWSER_ROUTE" in live_checker_source
    assert "termius-files-browser-route" in live_checker_source
    assert "expected_termius_files_browser_route" in live_checker_source
    assert "draw_termius_session_workflow" in renderer_source
    assert "SecureCRT-style Session Manager route" in docs_source
    assert "SecureCRT-style Session Manager filter route" in docs_source
    assert "SecureCRT-style SFTP tab route" in docs_source
    assert "SecureCRT-style SFTP browser route" in docs_source
    assert "Termius-style port-forward route" in docs_source
    assert "Termius-style snippet route" in docs_source
    assert "Termius-style files browser route" in docs_source
    assert "Termius-style host-selection route" in docs_source


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


def test_gui_parity_tracks_non_moba_product_identity_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.product-identity-route",
        "termius": "termius.product-identity-route",
        "remmina": "remmina.product-identity-route",
        "mremoteng": "mremoteng.product-identity-route",
    }
    for preset_id, requirement_id in expected.items():
        requirement_ids = {item["id"] for item in criteria["presets"][preset_id]["requirements"]}
        assert requirement_id in requirement_ids
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["navigation"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["tabs"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["session_trees"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["connected_session_behavior"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["status_bars"]
        assert requirement_id in criteria["presets"][preset_id]["dimension_coverage"]["interaction_states"]

    assert "GuiProductIdentityRoute" in design_source
    assert "gui_design_product_identity_route" in design_source
    assert "tree-tab-reference-status-workspace-identity" in design_source
    assert "productIdentityRouteKey" in gui_source
    assert "productIdentityActiveTab" in gui_source
    assert "productIdentityStatusSegments" in gui_source
    assert "gui_design_product_identity_route" in renderer_source
    assert "product_identity_route.active_tab_label" in renderer_source
    assert "product_identity_route.status_segments" in renderer_source
    assert "EXPECTED_PRODUCT_IDENTITY_ROUTES" in live_checker_source
    assert "product-identity-route" in live_checker_source
    assert "expected_product_identity_route" in live_checker_source
    assert "product identity route" in docs_source


def test_gui_parity_tracks_reference_tab_activation_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-tab-activation-route",
        "termius": "termius.reference-tab-activation-route",
        "remmina": "remmina.reference-tab-activation-route",
        "mremoteng": "mremoteng.reference-tab-activation-route",
    }
    dimension_keys = ["layout", "navigation", "tabs", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceTabRoute" in design_source
    assert "PRODUCT_REFERENCE_TAB_PRESET_IDS" in design_source
    assert "gui_design_preset_reference_tab_route" in design_source
    assert "reference-profile-tab-can-be-active-surface" in design_source
    assert "presetReferenceTabActivatedLabel" in gui_source
    assert "presetReferenceTabReturnedHomeLabel" in gui_source
    assert "find_tab_by_label" in gui_source
    assert "preset_reference_tab_route" in renderer_source
    assert "reference_tab_route.active_tab_label" in renderer_source
    assert "reference_tab_route.home_tab_label" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_TAB_ROUTES" in live_checker_source
    assert "check_live_preset_reference_tab_route" in live_checker_source
    assert "expected_preset_reference_tab_route" in live_checker_source
    assert "reference tab activation route" in docs_source


def test_gui_parity_tracks_reference_tab_chrome_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-tab-chrome-evidence-route",
        "termius": "termius.reference-tab-chrome-evidence-route",
        "remmina": "remmina.reference-tab-chrome-evidence-route",
        "mremoteng": "mremoteng.reference-tab-chrome-evidence-route",
    }
    dimension_keys = ["layout", "navigation", "tabs", "connected_session_behavior", "spacing", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceTabChromeRoute" in design_source
    assert "gui_design_preset_reference_tab_chrome_route" in design_source
    assert "active-reference-tab-chrome-evidence" in design_source
    assert "presetReferenceTabChromeTooltip" in gui_source
    assert "apply_reference_tab_chrome_route_to_terminal_tab" in gui_source
    assert "preset_reference_tab_chrome_route" in renderer_source
    assert "reference_tab_chrome_route.expected_tooltip" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES" in live_checker_source
    assert "check_live_preset_reference_tab_chrome_route" in live_checker_source
    assert "reference-tab-chrome-evidence-route" in live_checker_source
    assert "expected_preset_reference_tab_chrome_route" in live_checker_source
    assert "reference tab chrome evidence route" in docs_source


def test_gui_parity_tracks_reference_status_bar_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-status-bar-evidence-route",
        "termius": "termius.reference-status-bar-evidence-route",
        "remmina": "remmina.reference-status-bar-evidence-route",
        "mremoteng": "mremoteng.reference-status-bar-evidence-route",
    }
    dimension_keys = ["tabs", "connected_session_behavior", "status_bars", "spacing", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceStatusBarRoute" in design_source
    assert "gui_design_preset_reference_status_bar_route" in design_source
    assert "active-reference-status-bar-evidence" in design_source
    assert "presetReferenceStatusSegments" in gui_source
    assert "apply_reference_status_bar_route_to_terminal_tab" in gui_source
    assert "preset_reference_status_bar_route" in renderer_source
    assert "reference_status_route.expected_status_segments" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES" in live_checker_source
    assert "check_live_preset_reference_status_bar_route" in live_checker_source
    assert "reference-status-bar-evidence-route" in live_checker_source
    assert "expected_preset_reference_status_bar_route" in live_checker_source
    assert "reference status-bar evidence route" in docs_source


def test_gui_parity_tracks_product_keyboard_shortcut_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.keyboard-shortcut-route",
        "securecrt": "securecrt.keyboard-shortcut-route",
        "termius": "termius.keyboard-shortcut-route",
        "remmina": "remmina.keyboard-shortcut-route",
        "mremoteng": "mremoteng.keyboard-shortcut-route",
    }
    dimension_keys = ["navigation", "tabs", "toolbars", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetKeyboardShortcutRoute" in design_source
    assert "gui_design_preset_keyboard_shortcut_route" in design_source
    assert "product-preset-keyboard-shortcuts" in design_source
    assert "presetKeyboardShortcutCapturedSequences" in gui_source
    assert "create_keyboard_shortcuts" in gui_source
    assert "preset_keyboard_shortcut_route" in renderer_source
    assert "keyboard_shortcut_route.expected_sequences" in renderer_source
    assert "EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES" in live_checker_source
    assert "check_live_preset_keyboard_shortcut_route" in live_checker_source
    assert "preset-keyboard-shortcut-route" in live_checker_source
    assert "expected_preset_keyboard_shortcut_route" in live_checker_source
    assert "preset keyboard shortcut route" in docs_source


def test_gui_parity_tracks_product_command_surface_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.command-surface-route",
        "securecrt": "securecrt.command-surface-route",
        "termius": "termius.command-surface-route",
        "remmina": "remmina.command-surface-route",
        "mremoteng": "mremoteng.command-surface-route",
    }
    dimension_keys = ["navigation", "tabs", "toolbars", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetCommandSurfaceRoute" in design_source
    assert "gui_design_preset_command_surface_route" in design_source
    assert "product-preset-command-surface-route" in design_source
    assert "presetCommandSurfaceCapturedKeys" in gui_source
    assert "apply_command_surface_route_for_design" in gui_source
    assert "presetCommandSurfaceCapturedStates" in gui_source
    assert "preset_command_surface_route" in renderer_source
    assert "command_surface_route.expected_action_keys" in renderer_source
    assert "EXPECTED_PRESET_COMMAND_SURFACE_ROUTES" in live_checker_source
    assert "check_live_preset_command_surface_route" in live_checker_source
    assert "preset-command-surface-route" in live_checker_source
    assert "expected_preset_command_surface_route" in live_checker_source
    assert "preset command surface route" in docs_source


def test_gui_parity_tracks_product_command_surface_visual_metrics() -> None:
    metrics = json.loads(Path("configs/gui_visual_metrics.json").read_text(encoding="utf-8"))
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    visual_checker_source = Path("scripts/check_gui_visual_metrics.py").read_text(encoding="utf-8")

    expected_regions = {
        "mobaxterm": {
            "command-surface-active-sessions",
            "command-surface-disabled-games",
            "command-surface-checked-sftp-rail",
        },
        "securecrt": {
            "command-surface-active-connect",
            "command-surface-checked-sftp",
            "command-surface-disabled-delete",
        },
        "termius": {
            "command-surface-active-connect",
            "command-surface-checked-vault",
            "command-surface-disabled-remove",
        },
        "remmina": {
            "command-surface-active-connect",
            "command-surface-checked-transfer",
            "command-surface-disabled-delete",
        },
        "mremoteng": {
            "top-toolbar-active-open",
            "top-toolbar-checked-external",
            "top-toolbar-disabled-delete",
        },
    }
    expected_topology = {
        "mobaxterm": {
            "command-surface-active-sessions-inside-ribbon",
            "command-surface-disabled-games-inside-ribbon",
            "command-surface-checked-sftp-rail-inside-moba-rail",
        },
        "securecrt": {
            "command-surface-active-connect-inside-toolbar",
            "command-surface-checked-sftp-inside-toolbar",
            "command-surface-disabled-delete-inside-toolbar",
        },
        "termius": {
            "command-surface-active-connect-inside-toolbar",
            "command-surface-checked-vault-inside-toolbar",
            "command-surface-disabled-remove-inside-toolbar",
        },
        "remmina": {
            "command-surface-active-connect-inside-toolbar",
            "command-surface-checked-transfer-inside-toolbar",
            "command-surface-disabled-delete-inside-toolbar",
        },
        "mremoteng": {
            "top-open-active-inside-toolbar",
            "top-external-checked-inside-toolbar",
            "top-delete-disabled-inside-toolbar",
        },
    }

    for preset_id, region_ids in expected_regions.items():
        preset_metrics = metrics["presets"][preset_id]
        measured_region_ids = {region["id"] for region in preset_metrics["regions"]}
        measured_topology_ids = {contract["id"] for contract in preset_metrics.get("topology", [])}

        assert region_ids <= measured_region_ids
        assert expected_topology[preset_id] <= measured_topology_ids

    assert "check_region" in visual_checker_source
    assert "check_topology_contract" in visual_checker_source
    assert "command-surface state visual metrics" in docs_source


def test_gui_parity_tracks_product_focus_interaction_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.focus-interaction-route",
        "securecrt": "securecrt.focus-interaction-route",
        "termius": "termius.focus-interaction-route",
        "remmina": "remmina.focus-interaction-route",
        "mremoteng": "mremoteng.focus-interaction-route",
    }
    dimension_keys = ["navigation", "tabs", "sidebars", "toolbars", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetFocusInteractionRoute" in design_source
    assert "gui_design_preset_focus_interaction_route" in design_source
    assert "product-preset-focus-interaction-route" in design_source
    assert "presetFocusInteractionCapturedFocus" in gui_source
    assert "apply_focus_interaction_route_for_design" in gui_source
    assert "preset_focus_interaction_route" in renderer_source
    assert "focus_interaction_route.focused_control" in renderer_source
    assert "EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES" in live_checker_source
    assert "check_live_preset_focus_interaction_route" in live_checker_source
    assert "preset-focus-interaction-route" in live_checker_source
    assert "expected_preset_focus_interaction_route" in live_checker_source
    assert "preset focus interaction route" in docs_source


def test_gui_parity_tracks_product_home_search_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.home-search-route",
        "securecrt": "securecrt.home-search-route",
        "termius": "termius.home-search-route",
        "remmina": "remmina.home-search-route",
        "mremoteng": "mremoteng.home-search-route",
    }
    dimension_keys = ["navigation", "tabs", "sidebars", "toolbars", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetHomeSearchRoute" in design_source
    assert "gui_design_preset_home_search_route" in design_source
    assert "product-preset-home-search-entry-route" in design_source
    assert "presetHomeSearchCapturedPlaceholder" in gui_source
    assert "apply_home_search_route_for_design" in gui_source
    assert "preset_home_search_route" in renderer_source
    assert "home_search_route.placeholder_text" in renderer_source
    assert "EXPECTED_PRESET_HOME_SEARCH_ROUTES" in live_checker_source
    assert "check_live_preset_home_search_route" in live_checker_source
    assert "preset-home-search-route" in live_checker_source
    assert "expected_preset_home_search_route" in live_checker_source
    assert "preset home search route" in docs_source


def test_gui_parity_tracks_reference_session_action_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-session-actions-route",
        "termius": "termius.reference-session-actions-route",
        "remmina": "remmina.reference-session-actions-route",
        "mremoteng": "mremoteng.reference-session-actions-route",
    }
    dimension_keys = ["navigation", "tabs", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceSessionActionRoute" in design_source
    assert "gui_design_preset_reference_session_action_route" in design_source
    assert "active-reference-session-actions" in design_source
    assert "sessionTabContextActionKey" in gui_source
    assert "apply_reference_session_action_route_to_terminal_tab" in gui_source
    assert "preset_reference_session_action_route" in renderer_source
    assert "reference_session_action_route.expected_action_keys" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES" in live_checker_source
    assert "check_live_preset_reference_session_action_route" in live_checker_source
    assert "reference-session-actions-route" in live_checker_source
    assert "expected_preset_reference_session_action_route" in live_checker_source
    assert "reference session action route" in docs_source


def test_gui_parity_tracks_reference_surface_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-surface-evidence-route",
        "termius": "termius.reference-surface-evidence-route",
        "remmina": "remmina.reference-surface-evidence-route",
        "mremoteng": "mremoteng.reference-surface-evidence-route",
    }
    dimension_keys = ["layout", "panes", "tabs", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceSurfaceRoute" in design_source
    assert "gui_design_preset_reference_surface_route" in design_source
    assert "active-reference-tab-surface-evidence" in design_source
    assert "presetReferenceSurfaceActualCommand" in gui_source
    assert "presetReferenceSurfaceActualOutput" in gui_source
    assert "apply_reference_surface_route_to_terminal_tab" in gui_source
    assert "preset_reference_surface_route" in renderer_source
    assert "reference_surface_route.command_target_fragment" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES" in live_checker_source
    assert "check_live_preset_reference_surface_route" in live_checker_source
    assert "reference-surface-evidence-route" in live_checker_source
    assert "expected_preset_reference_surface_route" in live_checker_source
    assert "reference surface evidence route" in docs_source


def test_gui_parity_tracks_reference_control_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-control-evidence-route",
        "termius": "termius.reference-control-evidence-route",
        "remmina": "remmina.reference-control-evidence-route",
        "mremoteng": "mremoteng.reference-control-evidence-route",
    }
    dimension_keys = ["layout", "panes", "toolbars", "connected_session_behavior", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceControlRoute" in design_source
    assert "gui_design_preset_reference_control_route" in design_source
    assert "active-reference-tab-terminal-controls" in design_source
    assert "terminalActionKey" in gui_source
    assert "presetReferenceControlCapturedActionKeys" in gui_source
    assert "apply_reference_control_route_to_terminal_tab" in gui_source
    assert "preset_reference_control_route" in renderer_source
    assert "reference_control_route.action_keys" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES" in live_checker_source
    assert "check_live_preset_reference_control_route" in live_checker_source
    assert "reference-control-evidence-route" in live_checker_source
    assert "expected_preset_reference_control_route" in live_checker_source
    assert "reference control evidence route" in docs_source


def test_gui_parity_tracks_reference_input_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-input-evidence-route",
        "termius": "termius.reference-input-evidence-route",
        "remmina": "remmina.reference-input-evidence-route",
        "mremoteng": "mremoteng.reference-input-evidence-route",
    }
    dimension_keys = ["layout", "panes", "connected_session_behavior", "spacing", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceInputRoute" in design_source
    assert "gui_design_preset_reference_input_route" in design_source
    assert "active-reference-tab-terminal-input" in design_source
    assert "presetReferenceInputEnabled" in gui_source
    assert "apply_reference_input_route_to_terminal_tab" in gui_source
    assert "preset_reference_input_route" in renderer_source
    assert "reference_input_route.placeholder_text" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_INPUT_ROUTES" in live_checker_source
    assert "check_live_preset_reference_input_route" in live_checker_source
    assert "reference-input-evidence-route" in live_checker_source
    assert "expected_preset_reference_input_route" in live_checker_source
    assert "reference input evidence route" in docs_source


def test_gui_parity_tracks_reference_transcript_evidence_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "securecrt": "securecrt.reference-transcript-evidence-route",
        "termius": "termius.reference-transcript-evidence-route",
        "remmina": "remmina.reference-transcript-evidence-route",
        "mremoteng": "mremoteng.reference-transcript-evidence-route",
    }
    dimension_keys = ["layout", "panes", "connected_session_behavior", "density", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetReferenceTranscriptRoute" in design_source
    assert "gui_design_preset_reference_transcript_route" in design_source
    assert "active-reference-tab-terminal-transcript" in design_source
    assert "presetReferenceTranscriptCommandEcho" in gui_source
    assert "apply_reference_transcript_route_to_terminal_tab" in gui_source
    assert "preset_reference_transcript_route" in renderer_source
    assert "reference_transcript_route.required_fragments" in renderer_source
    assert "EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES" in live_checker_source
    assert "check_live_preset_reference_transcript_route" in live_checker_source
    assert "reference-transcript-evidence-route" in live_checker_source
    assert "expected_preset_reference_transcript_route" in live_checker_source
    assert "reference transcript evidence route" in docs_source


def test_gui_parity_tracks_preset_selection_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.preset-selection-route",
        "securecrt": "securecrt.preset-selection-route",
        "termius": "termius.preset-selection-route",
        "remmina": "remmina.preset-selection-route",
        "mremoteng": "mremoteng.preset-selection-route",
    }
    dimension_keys = [
        "layout",
        "navigation",
        "tabs",
        "sidebars",
        "toolbars",
        "connected_session_behavior",
        "status_bars",
        "interaction_states",
    ]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetSelectionRoute" in design_source
    assert "gui_design_preset_selection_route" in design_source
    assert "selector-to-toolbar-sidebar-tabs-status-workspace" in design_source
    assert "presetSelectionRouteKey" in gui_source
    assert "presetSelectionRouteHomeTabLabel" in gui_source
    assert "presetSelectionRouteStatusSegments" in gui_source
    assert "gui_design_preset_selection_route" in renderer_source
    assert "preset_selection_route" in renderer_source
    assert "selection_route.home_tab_label" in renderer_source
    assert "selection_route.status_segments" in renderer_source
    assert "EXPECTED_PRESET_SELECTION_ROUTES" in live_checker_source
    assert "preset-selection-route" in live_checker_source
    assert "expected_preset_selection_route" in live_checker_source
    assert "preset-selection route" in docs_source


def test_gui_parity_tracks_preset_catalog_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.preset-catalog-route",
        "securecrt": "securecrt.preset-catalog-route",
        "termius": "termius.preset-catalog-route",
        "remmina": "remmina.preset-catalog-route",
        "mremoteng": "mremoteng.preset-catalog-route",
    }
    dimension_keys = ["layout", "navigation", "toolbars", "interaction_states"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetCatalogRoute" in design_source
    assert "gui_design_preset_catalog_route" in design_source
    assert "preset-catalog-to-design-selector-options" in design_source
    assert "presetCatalogRouteOptionIds" in gui_source
    assert "presetCatalogRouteProductPresetIds" in gui_source
    assert "presetCatalogRouteDefaultPresetId" in gui_source
    assert "gui_design_preset_catalog_route" in renderer_source
    assert "preset_catalog_route" in renderer_source
    assert "catalog_route.option_ids" in renderer_source
    assert "catalog_route.option_labels" in renderer_source
    assert "EXPECTED_PRESET_CATALOG_ROUTE" in live_checker_source
    assert "preset-catalog-route" in live_checker_source
    assert "expected_preset_catalog_route" in live_checker_source
    assert "design selector catalog" in docs_source


def test_gui_parity_tracks_preset_visual_signatures() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.visual-signature",
        "securecrt": "securecrt.visual-signature",
        "termius": "termius.visual-signature",
        "remmina": "remmina.visual-signature",
        "mremoteng": "mremoteng.visual-signature",
    }
    dimension_keys = ["layout", "tabs", "sidebars", "toolbars", "status_bars", "density", "spacing"]
    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirement_ids = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirement_ids
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetVisualSignature" in design_source
    assert "gui_design_preset_visual_signature" in design_source
    assert "preset-palette-density-to-live-static-style" in design_source
    assert "presetVisualSignatureDensity" in gui_source
    assert "presetVisualSignaturePalette" in gui_source
    assert "presetVisualSignatureRenderSource" in gui_source
    assert "gui_design_preset_visual_signature" in renderer_source
    assert "preset_visual_signature" in renderer_source
    assert "visual_signature.palette_items" in renderer_source
    assert "visual_signature.terminal_accent_color" in renderer_source
    assert "EXPECTED_PRESET_VISUAL_SIGNATURES" in live_checker_source
    assert "preset-visual-signature" in live_checker_source
    assert "expected_preset_visual_signature" in live_checker_source
    assert "visual signature contract" in docs_source


def test_gui_parity_tracks_preset_isolation_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.preset-isolation-route",
        "securecrt": "securecrt.preset-isolation-route",
        "termius": "termius.preset-isolation-route",
        "remmina": "remmina.preset-isolation-route",
        "mremoteng": "mremoteng.preset-isolation-route",
    }
    dimension_keys = [
        "layout",
        "navigation",
        "tabs",
        "sidebars",
        "toolbars",
        "connected_session_behavior",
        "interaction_states",
    ]

    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirements = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirements
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetIsolationRoute" in design_source
    assert "gui_design_preset_isolation_route" in design_source
    assert "active-preset-visible-hidden-widget-isolation" in design_source
    assert "presetIsolationVisibleObjects" in gui_source
    assert "presetIsolationHiddenObjects" in gui_source
    assert "presetIsolationRenderSource" in gui_source
    assert "preset_isolation_route" in renderer_source
    assert "isolation_route.visible_objects" in renderer_source
    assert "isolation_route.hidden_objects" in renderer_source
    assert "EXPECTED_PRESET_ISOLATION_ROUTES" in live_checker_source
    assert "preset-isolation-route" in live_checker_source
    assert "expected_preset_isolation_route" in live_checker_source
    assert "preset isolation route" in docs_source


def test_gui_parity_tracks_preset_transition_routes() -> None:
    checker = _load_checker()
    criteria = checker.load_json(checker.CRITERIA_PATH)
    docs_source = Path("docs/GUI_DESIGN.md").read_text(encoding="utf-8")
    gui_source = Path("src/remote_ops_workspace/gui.py").read_text(encoding="utf-8")
    renderer_source = Path("scripts/render_gui_design_previews.py").read_text(encoding="utf-8")
    live_checker_source = Path("scripts/check_real_gui_render.py").read_text(encoding="utf-8")
    design_source = Path("src/remote_ops_workspace/gui_designs.py").read_text(encoding="utf-8")

    expected = {
        "mobaxterm": "moba.preset-transition-route",
        "securecrt": "securecrt.preset-transition-route",
        "termius": "termius.preset-transition-route",
        "remmina": "remmina.preset-transition-route",
        "mremoteng": "mremoteng.preset-transition-route",
    }
    dimension_keys = [
        "layout",
        "navigation",
        "tabs",
        "sidebars",
        "toolbars",
        "connected_session_behavior",
        "interaction_states",
    ]

    for preset_id, requirement_id in expected.items():
        preset = criteria["presets"][preset_id]
        requirements = {item["id"] for item in preset["requirements"]}
        assert requirement_id in requirements
        for dimension_key in dimension_keys:
            assert requirement_id in preset["dimension_coverage"][dimension_key]

    assert "GuiPresetTransitionRoute" in design_source
    assert "gui_design_preset_transition_route" in design_source
    assert "selector-style-switch-resets-inactive-product-chrome" in design_source
    assert "presetTransitionFromPresetIds" in gui_source
    assert "presetTransitionResetObjects" in gui_source
    assert "presetTransitionRenderSource" in gui_source
    assert "preset_transition_route" in renderer_source
    assert "transition_route.from_preset_ids" in renderer_source
    assert "transition_route.reset_objects" in renderer_source
    assert "EXPECTED_PRESET_TRANSITION_ROUTES" in live_checker_source
    assert "preset-transition-route" in live_checker_source
    assert "expected_preset_transition_route" in live_checker_source
    assert "preset transition route" in docs_source


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
