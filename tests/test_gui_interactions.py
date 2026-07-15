from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_checker():
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_gui_interactions.py"
    spec = importlib.util.spec_from_file_location("check_gui_interactions", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gui_interaction_gate_inventories_every_visible_toolbar_command() -> None:
    checker = _load_checker()

    assert checker.PRODUCT_KEYS == (
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
    assert checker.LAYOUT_KEYS == ("new-layout", "edit-layout", "remove-layout", "open-layout")
    assert len(checker.MOBA_KEYS) == 12
    assert len(checker.MENU_OPERATIONS) == 24
    assert tuple(checker.PRODUCT_CALLBACK_CONTRACTS) == checker.PRODUCT_KEYS
    assert tuple(checker.LAYOUT_CALLBACK_CONTRACTS) == checker.LAYOUT_KEYS
    assert tuple(checker.MOBA_CALLBACK_CONTRACTS) == checker.MOBA_KEYS
    assert tuple(checker.MENU_CALLBACK_CONTRACTS) == tuple(
        (family, key) for family, key, _operation in checker.MENU_OPERATIONS
    )
    assert ("securecrt", "script", "script-status") in checker.MENU_OPERATIONS
    assert ("mremoteng", "tools", "external-tools-status") in checker.MENU_OPERATIONS
    assert len(checker.SUPPORTED_WINDOW_SIZES) == 5
    assert checker.SUPPORTED_WINDOW_SIZES[0] == (1024, 768)
    assert (1180, 720) in checker.SUPPORTED_WINDOW_SIZES


def test_gui_interaction_gate_runs_on_linux_and_native_windows_ci() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("scripts/check_gui_interactions.py --require-pyqt6") == 2
    assert "gui-interactions-windows:" in workflow
    assert "runs-on: windows-2025-vs2026" in workflow
    assert 'QT_QPA_PLATFORM: "windows"' in workflow
    assert 'QT_QPA_PLATFORM: "offscreen"' in workflow


def test_gui_interaction_gate_defaults_to_host_native_qt_platform() -> None:
    checker = _load_checker()

    assert checker.configure_qt_platform_environment({}, system_platform="win32") == "windows"
    assert checker.configure_qt_platform_environment({}, system_platform="darwin") == "cocoa"
    assert checker.configure_qt_platform_environment({}, system_platform="linux") == "offscreen"
    explicit = {"QT_QPA_PLATFORM": "minimal"}
    assert (
        checker.configure_qt_platform_environment(explicit, system_platform="win32")
        == "minimal"
    )


def test_gui_interaction_manifest_records_fail_closed_font_render_evidence() -> None:
    checker = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_gui_interactions.py"
    ).read_text(encoding="utf-8")

    assert '"font-render-preflight"' in checker
    assert '"capture_mode": capture_mode' in checker
    assert '"font_render_evidence": font_render_payload' in checker
    assert "validate_qt_font_render_evidence(font_render_evidence)" in checker
    assert "if font_render_errors:" in checker


def test_gui_interaction_evidence_snapshots_mutable_dispatch_details() -> None:
    checker = (
        Path(__file__).resolve().parents[1] / "scripts" / "check_gui_interactions.py"
    ).read_text(encoding="utf-8")

    assert 'record("product-click-dispatch", tuple(dispatched) == PRODUCT_KEYS, list(dispatched))' in checker
    assert 'record("layout-click-dispatch", tuple(dispatched) == LAYOUT_KEYS, list(dispatched))' in checker
    assert "detail_snapshot = copy.deepcopy(detail)" in checker
    assert '"qt_platform_plugin": QApplication.platformName()' in checker
    assert "interaction evidence was not produced" in checker
    assert "gui interaction debug" not in checker
    assert "TEMP_PROGRESS" not in checker
    assert 'window.set_design_preset("mobaxterm")' in checker
    assert "quick-connect-double-click-dispatches-once" in checker
    assert "find-control-preserves-second-split-pane-target" in checker
    assert "termius-search-return-does-not-trigger-snippet" in checker
    assert "wrapped-open-layout-rename-retargets-resize-persistence" in checker
    assert "moba-recovery-preserves-identity-path-and-dock" in checker
    assert "preset-cycle-replaces-tab-status-without-accumulation" in checker
    assert "moba-to-native-restores-quick-connect-base-tooltip" in checker
    assert "termius-filter-remains-applied-after-preset-round-trip" in checker
    assert "remmina-filter-remains-applied-after-preset-round-trip" in checker
    assert "nested-five-pane-duplicate-preserves-recursive-topology" in checker
    assert "tab-switch-refreshes-current-preset-runtime-status" in checker
    assert "split-preset-cycle-uses-stable-base-tooltip" in checker
    assert "securecrt-no-match-filter-clears-stale-selection" in checker
    assert "termius-no-match-filter-clears-stale-selection" in checker
    assert "mremoteng-no-match-filter-clears-stale-selection" in checker
    assert "moba-native-duplicate-preserves-identity-path-sftp-and-splits" in checker
    assert "duplicated-open-layout-rename-retargets-title-tooltip-and-binding" in checker
    for preset_id in ("securecrt", "termius", "remmina", "mremoteng"):
        assert f"recovery-{preset_id}-preserves-profile-and-sftp-tab-identity" in checker


def test_gui_policy_guards_every_profile_backed_execution_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "remote_ops_workspace"
        / "gui.py"
    ).read_text(encoding="utf-8")

    assert 'assert_profile_launch_allowed(self.profile, surface="gui")' in source
    assert 'assert_profile_launch_allowed(profile, surface="gui")' in source
    assert "profiles = self.layout_launch_profiles(layout)" in source
    assert "self.open_terminal_tab(pane_plan, profile=profile)" in source
    assert "pane = TerminalPane(plan, profile=profile)" in source
    assert "widget.plan,\n                    profile=widget.profile," in source
    assert "self.open_terminal_tab(\n                        plan,\n                        profile=profile," in source
    for required in (
        "allow_insecure_sshv1=true",
        "legacy_target=windows-xp-32",
        "windows-xp-64",
        "allow_legacy_crypto=true",
        "isolated legacy systems",
    ):
        assert required in source


def test_gui_state_transitions_preserve_stable_identity_contracts() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "remote_ops_workspace"
        / "gui.py"
    ).read_text(encoding="utf-8")

    assert "tooltip = self.base_tab_tooltip(current_index) or title" in source
    assert "if isinstance(widget, MobaConnectedSessionPanel):" in source
    assert (
        "self.current_design_is_moba() and isinstance(widget, MobaConnectedSessionPanel)"
        not in source
    )
    assert "if current is not None and not self.profile_tree_item_is_visible(current):" in source
    assert "self.profile_list.setCurrentItem(None)" in source
    assert "and plan.source == f\"profile:{profile.name}\"" in source
    assert "and self.moba_connected_profile_supported(profile)" in source
    assert "suffix.startswith((\" ·\", \":\", \" copy\"))" in source
