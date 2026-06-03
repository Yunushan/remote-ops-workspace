from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GUI_DESIGN_ID = "native"


@dataclass(frozen=True)
class GuiDesignColors:
    window: str
    toolbar: str
    toolbar_border: str
    control: str
    control_text: str
    control_border: str
    control_hover: str
    primary: str
    primary_text: str
    danger: str
    danger_text: str
    sidebar: str
    sidebar_text: str
    sidebar_muted: str
    sidebar_selected: str
    sidebar_selected_text: str
    pane: str
    pane_border: str
    tab: str
    tab_selected: str
    tab_text: str
    tab_selected_text: str
    terminal: str
    terminal_text: str
    terminal_accent: str
    log: str
    log_text: str
    status: str


@dataclass(frozen=True)
class GuiDesignPreset:
    id: str
    label: str
    description: str
    profile_width: int
    log_height: int
    tab_position: str
    density: str
    toolbar_icon_size: int
    list_spacing: int
    document_mode: bool
    colors: GuiDesignColors
    stylesheet: str


def _stylesheet(
    colors: GuiDesignColors,
    *,
    radius: int,
    control_padding: str,
    tab_padding: str,
    tree_padding: str,
) -> str:
    return f"""
QMainWindow#remoteOpsMain {{
  background: {colors.window};
}}
QToolBar#mainToolbar {{
  background: {colors.toolbar};
  border-bottom: 1px solid {colors.toolbar_border};
  spacing: 5px;
  padding: 5px 7px;
}}
QLabel#toolbarLabel {{
  color: {colors.sidebar_muted};
  padding-left: 8px;
  padding-right: 2px;
}}
QPushButton, QComboBox, QLineEdit {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: {control_padding};
}}
QPushButton:hover, QComboBox:hover, QLineEdit:hover {{
  border-color: {colors.control_hover};
}}
QPushButton:disabled {{
  color: {colors.sidebar_muted};
  background: {colors.pane};
}}
QPushButton#primaryAction {{
  background: {colors.primary};
  color: {colors.primary_text};
  border-color: {colors.primary};
  font-weight: 600;
}}
QPushButton#primaryAction:hover {{
  border-color: {colors.control_hover};
}}
QPushButton#dangerAction {{
  color: {colors.danger_text};
  border-color: {colors.danger};
}}
QLineEdit#toolbarSearch {{
  min-width: 150px;
}}
QListWidget#profileTree {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 0;
  border-right: 1px solid {colors.pane_border};
  padding: 5px;
  outline: 0;
  font-family: "Segoe UI", Arial, sans-serif;
}}
QListWidget#profileTree::item {{
  padding: {tree_padding};
  border-radius: {radius}px;
}}
QListWidget#profileTree::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QTabWidget#sessionTabs::pane {{
  background: {colors.pane};
  border: 1px solid {colors.pane_border};
}}
QTabBar::tab {{
  background: {colors.tab};
  color: {colors.tab_text};
  padding: {tab_padding};
  border: 1px solid {colors.pane_border};
  margin-right: 2px;
}}
QTabBar::tab:selected {{
  background: {colors.tab_selected};
  color: {colors.tab_selected_text};
  border-bottom-color: {colors.tab_selected};
  font-weight: 600;
}}
QWidget#terminalPane {{
  background: {colors.pane};
}}
QLabel#paneStatus {{
  color: {colors.status};
  font-weight: 600;
}}
QTextEdit#terminalOutput, QPlainTextEdit {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border: 1px solid {colors.pane_border};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QLineEdit#terminalInput {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border-color: {colors.primary};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QTextEdit#activityLog {{
  background: {colors.log};
  color: {colors.log_text};
  border: 1px solid {colors.pane_border};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QSplitter::handle {{
  background: {colors.toolbar_border};
}}
QStatusBar {{
  background: {colors.toolbar};
  color: {colors.sidebar_muted};
  border-top: 1px solid {colors.toolbar_border};
}}
QLabel {{
  color: {colors.control_text};
}}
"""


def _preset(
    *,
    id: str,
    label: str,
    description: str,
    profile_width: int,
    log_height: int,
    tab_position: str,
    density: str,
    toolbar_icon_size: int,
    list_spacing: int,
    document_mode: bool,
    colors: GuiDesignColors,
    radius: int,
    control_padding: str,
    tab_padding: str,
    tree_padding: str,
) -> GuiDesignPreset:
    return GuiDesignPreset(
        id=id,
        label=label,
        description=description,
        profile_width=profile_width,
        log_height=log_height,
        tab_position=tab_position,
        density=density,
        toolbar_icon_size=toolbar_icon_size,
        list_spacing=list_spacing,
        document_mode=document_mode,
        colors=colors,
        stylesheet=_stylesheet(
            colors,
            radius=radius,
            control_padding=control_padding,
            tab_padding=tab_padding,
            tree_padding=tree_padding,
        ),
    )


NATIVE_COLORS = GuiDesignColors(
    window="#f4f6f9",
    toolbar="#ffffff",
    toolbar_border="#d8dee8",
    control="#ffffff",
    control_text="#1f2937",
    control_border="#c4ccd8",
    control_hover="#2563eb",
    primary="#2563eb",
    primary_text="#ffffff",
    danger="#c2410c",
    danger_text="#7c2d12",
    sidebar="#f8fafc",
    sidebar_text="#1f2937",
    sidebar_muted="#64748b",
    sidebar_selected="#dbeafe",
    sidebar_selected_text="#0f172a",
    pane="#ffffff",
    pane_border="#d8dee8",
    tab="#eef2f7",
    tab_selected="#ffffff",
    tab_text="#334155",
    tab_selected_text="#0f172a",
    terminal="#111827",
    terminal_text="#e5edf6",
    terminal_accent="#38bdf8",
    log="#fbfdff",
    log_text="#243244",
    status="#2563eb",
)

MOBAXTERM_COLORS = GuiDesignColors(
    window="#0e1518",
    toolbar="#162327",
    toolbar_border="#29454b",
    control="#1d3036",
    control_text="#eef7f4",
    control_border="#35565d",
    control_hover="#f59e0b",
    primary="#13a68f",
    primary_text="#06100f",
    danger="#ef8354",
    danger_text="#ffd5c5",
    sidebar="#101b1f",
    sidebar_text="#d9ece9",
    sidebar_muted="#87aaa6",
    sidebar_selected="#263f45",
    sidebar_selected_text="#ffffff",
    pane="#111d21",
    pane_border="#2b474f",
    tab="#183037",
    tab_selected="#0f7f74",
    tab_text="#cce5e1",
    tab_selected_text="#ffffff",
    terminal="#071113",
    terminal_text="#c9fff0",
    terminal_accent="#5eead4",
    log="#0c1619",
    log_text="#c6dad8",
    status="#f59e0b",
)

SECURECRT_COLORS = GuiDesignColors(
    window="#151515",
    toolbar="#242424",
    toolbar_border="#3a3a3a",
    control="#303030",
    control_text="#eeeeee",
    control_border="#575757",
    control_hover="#d7a84a",
    primary="#d7a84a",
    primary_text="#17130b",
    danger="#b85c5c",
    danger_text="#f4caca",
    sidebar="#1b1b1b",
    sidebar_text="#e8e8e8",
    sidebar_muted="#9a9a9a",
    sidebar_selected="#3a3325",
    sidebar_selected_text="#fff4d6",
    pane="#090909",
    pane_border="#383838",
    tab="#2a2a2a",
    tab_selected="#101010",
    tab_text="#d8d8d8",
    tab_selected_text="#ffffff",
    terminal="#000000",
    terminal_text="#dcdcdc",
    terminal_accent="#72d572",
    log="#101010",
    log_text="#d0d0d0",
    status="#d7a84a",
)

TERMIUS_COLORS = GuiDesignColors(
    window="#111315",
    toolbar="#191d20",
    toolbar_border="#30363a",
    control="#22282c",
    control_text="#edf3f0",
    control_border="#3a4449",
    control_hover="#61d394",
    primary="#61d394",
    primary_text="#06120c",
    danger="#d46a6a",
    danger_text="#ffd2d2",
    sidebar="#15191c",
    sidebar_text="#e7eeeb",
    sidebar_muted="#9aa8a4",
    sidebar_selected="#23342c",
    sidebar_selected_text="#ffffff",
    pane="#121719",
    pane_border="#2d383d",
    tab="#1d2326",
    tab_selected="#25392f",
    tab_text="#d8e2df",
    tab_selected_text="#ffffff",
    terminal="#0a0e10",
    terminal_text="#d9f7e3",
    terminal_accent="#61d394",
    log="#101416",
    log_text="#d1ddd8",
    status="#61d394",
)

REMMINA_COLORS = GuiDesignColors(
    window="#eef2f5",
    toolbar="#ffffff",
    toolbar_border="#c8d0d8",
    control="#ffffff",
    control_text="#20262d",
    control_border="#b6c0ca",
    control_hover="#2c7be5",
    primary="#2c7be5",
    primary_text="#ffffff",
    danger="#ba4a31",
    danger_text="#8a2f1e",
    sidebar="#f7f9fb",
    sidebar_text="#1d252d",
    sidebar_muted="#687682",
    sidebar_selected="#d6e9ff",
    sidebar_selected_text="#0f253f",
    pane="#ffffff",
    pane_border="#c8d0d8",
    tab="#e6ebf0",
    tab_selected="#ffffff",
    tab_text="#26323d",
    tab_selected_text="#111820",
    terminal="#fbfcfd",
    terminal_text="#17212b",
    terminal_accent="#1a7f64",
    log="#ffffff",
    log_text="#1f2b36",
    status="#2c7be5",
)

MREMOTENG_COLORS = GuiDesignColors(
    window="#dfe5eb",
    toolbar="#f4f7fa",
    toolbar_border="#aab6c2",
    control="#ffffff",
    control_text="#1b2733",
    control_border="#99a8b6",
    control_hover="#3b6ea8",
    primary="#3b6ea8",
    primary_text="#ffffff",
    danger="#9f3d35",
    danger_text="#7a2c26",
    sidebar="#edf2f6",
    sidebar_text="#1b2733",
    sidebar_muted="#687887",
    sidebar_selected="#c9d8e8",
    sidebar_selected_text="#0f1b26",
    pane="#f8fafc",
    pane_border="#aab6c2",
    tab="#e8edf2",
    tab_selected="#ffffff",
    tab_text="#263442",
    tab_selected_text="#111820",
    terminal="#ffffff",
    terminal_text="#102030",
    terminal_accent="#315f8f",
    log="#ffffff",
    log_text="#1d2a36",
    status="#315f8f",
)


GUI_DESIGN_PRESETS: tuple[GuiDesignPreset, ...] = (
    _preset(
        id=DEFAULT_GUI_DESIGN_ID,
        label="Native",
        description="System-friendly Windows layout with quiet chrome and readable terminal panes.",
        profile_width=305,
        log_height=165,
        tab_position="north",
        density="comfortable",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=NATIVE_COLORS,
        radius=4,
        control_padding="5px 9px",
        tab_padding="7px 13px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="mobaxterm",
        label="MobaXterm-style",
        description="Dense operator console with a connection tree, action strip, tabs and split panes.",
        profile_width=335,
        log_height=148,
        tab_position="north",
        density="dense",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=True,
        colors=MOBAXTERM_COLORS,
        radius=3,
        control_padding="4px 8px",
        tab_padding="6px 12px",
        tree_padding="5px 6px",
    ),
    _preset(
        id="securecrt",
        label="SecureCRT-style",
        description="Terminal-first workspace with restrained dark chrome and wide session tabs.",
        profile_width=270,
        log_height=118,
        tab_position="north",
        density="terminal",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=False,
        colors=SECURECRT_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="6px 14px",
        tree_padding="5px 6px",
    ),
    _preset(
        id="termius",
        label="Termius-style",
        description="Dark SSH-focused workspace with compact hosts, vault cues and vertical session tabs.",
        profile_width=292,
        log_height=136,
        tab_position="west",
        density="focused",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=TERMIUS_COLORS,
        radius=5,
        control_padding="5px 9px",
        tab_padding="8px 12px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="remmina",
        label="Remmina-style",
        description="Light remote-desktop workspace with clear protocol profiles and viewer tabs.",
        profile_width=320,
        log_height=158,
        tab_position="north",
        density="comfortable",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=REMMINA_COLORS,
        radius=4,
        control_padding="5px 9px",
        tab_padding="7px 13px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="mremoteng",
        label="mRemoteNG-style",
        description="Classic connection-manager workspace with a persistent tree and document tabs.",
        profile_width=355,
        log_height=145,
        tab_position="north",
        density="classic",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=True,
        colors=MREMOTENG_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="6px 11px",
        tree_padding="5px 6px",
    ),
)


def gui_design_preset_ids() -> list[str]:
    return [preset.id for preset in GUI_DESIGN_PRESETS]


def gui_design_preset_labels() -> list[str]:
    return [preset.label for preset in GUI_DESIGN_PRESETS]


def get_gui_design_preset(preset_id: str) -> GuiDesignPreset:
    for preset in GUI_DESIGN_PRESETS:
        if preset.id == preset_id:
            return preset
    raise ValueError(f"unknown GUI design preset: {preset_id}")
