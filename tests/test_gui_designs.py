from remote_ops_workspace.gui_designs import (
    DEFAULT_GUI_DESIGN_ID,
    GUI_DESIGN_PRESETS,
    get_gui_design_preset,
    gui_design_preset_ids,
    gui_design_preset_labels,
)


def test_gui_design_presets_include_requested_product_styles() -> None:
    ids = set(gui_design_preset_ids())
    assert {
        DEFAULT_GUI_DESIGN_ID,
        "mobaxterm",
        "securecrt",
        "termius",
        "remmina",
        "mremoteng",
    }.issubset(ids)


def test_gui_design_presets_have_valid_layout_metadata() -> None:
    labels = gui_design_preset_labels()
    assert len(labels) == len(set(labels))
    for preset in GUI_DESIGN_PRESETS:
        assert preset.id
        assert preset.label
        assert preset.description
        assert preset.profile_width >= 240
        assert preset.log_height >= 100
        assert preset.tab_position in {"north", "south", "east", "west"}
        assert preset.density
        assert 12 <= preset.toolbar_icon_size <= 24
        assert preset.list_spacing >= 0
        assert preset.colors.primary.startswith("#")
        assert "QMainWindow#remoteOpsMain" in preset.stylesheet
        assert "QToolBar#mainToolbar" in preset.stylesheet
        assert "QToolBar#layoutToolbar" in preset.stylesheet
        assert "QTabWidget#sessionTabs" in preset.stylesheet
        assert "QListWidget#profileTree" in preset.stylesheet
        assert "QPushButton#primaryAction" in preset.stylesheet
        assert "QTextEdit#activityLog" in preset.stylesheet
        assert "QWidget#terminalPane" in preset.stylesheet
        assert "QSplitter::handle" in preset.stylesheet


def test_gui_design_presets_are_not_only_recolored_clones() -> None:
    signatures = {
        (
            preset.profile_width,
            preset.log_height,
            preset.tab_position,
            preset.density,
            preset.toolbar_icon_size,
            preset.colors.window,
            preset.colors.primary,
            preset.colors.terminal,
        )
        for preset in GUI_DESIGN_PRESETS
    }
    assert len(signatures) == len(GUI_DESIGN_PRESETS)


def test_gui_design_styles_avoid_fragile_decoration_patterns() -> None:
    for preset in GUI_DESIGN_PRESETS:
        stylesheet = preset.stylesheet.lower()
        assert "gradient" not in stylesheet
        assert "letter-spacing" not in stylesheet
        assert "border-radius: 9" not in stylesheet
        assert "border-radius: 10" not in stylesheet


def test_get_gui_design_preset_rejects_unknown_id() -> None:
    assert get_gui_design_preset("termius").label == "Termius-style"
    try:
        get_gui_design_preset("unknown")
    except ValueError as exc:
        assert "unknown GUI design preset" in str(exc)
    else:
        raise AssertionError("unknown GUI design preset should be rejected")
