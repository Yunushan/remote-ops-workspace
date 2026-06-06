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
QToolBar#mainToolbar, QToolBar#layoutToolbar {{
  background: {colors.toolbar};
  border-bottom: 1px solid {colors.toolbar_border};
  spacing: 5px;
  padding: 5px 7px;
}}
QMenuBar {{
  background: {colors.toolbar};
  color: {colors.control_text};
  border-bottom: 1px solid {colors.toolbar_border};
  padding: 2px 6px;
}}
QMenuBar::item {{
  padding: 3px 8px;
  background: transparent;
}}
QMenuBar::item:selected {{
  background: {colors.control};
}}
QLabel#toolbarLabel {{
  color: {colors.sidebar_muted};
  padding-left: 8px;
  padding-right: 2px;
}}
QPushButton, QToolButton, QComboBox, QLineEdit {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: {control_padding};
}}
QPushButton:hover, QToolButton:hover, QComboBox:hover, QLineEdit:hover {{
  border-color: {colors.control_hover};
}}
QPushButton:disabled, QToolButton:disabled {{
  color: {colors.sidebar_muted};
  background: {colors.pane};
}}
QPushButton#primaryAction, QToolButton#primaryAction {{
  background: {colors.primary};
  color: {colors.primary_text};
  border-color: {colors.primary};
  font-weight: 600;
}}
QPushButton#primaryAction:hover, QToolButton#primaryAction:hover {{
  border-color: {colors.control_hover};
}}
QPushButton#dangerAction, QToolButton#dangerAction {{
  color: {colors.danger_text};
  border-color: {colors.danger};
}}
QToolButton#mobaRibbonButton {{
  background: transparent;
  color: {colors.control_text};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 500;
}}
QToolButton#mobaRibbonButton:hover {{
  background: {colors.control};
  border-color: {colors.control_border};
}}
QToolButton#mobaXServerAction {{
  background: transparent;
  color: {colors.primary};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 600;
}}
QToolButton#mobaXServerAction:hover {{
  background: {colors.control};
  border-color: {colors.control_border};
}}
QToolButton#mobaExitAction {{
  background: transparent;
  color: {colors.danger_text};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 600;
}}
QToolButton#mobaExitAction:hover {{
  background: {colors.control};
  border-color: {colors.danger};
}}
QLineEdit#toolbarSearch {{
  min-width: 150px;
}}
QLineEdit#quickConnect {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.toolbar_border};
  border-radius: 0;
  padding: 4px 8px;
}}
QTreeWidget#quickConnectSuggestions {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 1px solid {colors.toolbar_border};
  border-top: 0;
  padding: 3px;
  outline: 0;
  font-family: "Segoe UI", Arial, sans-serif;
}}
QTreeWidget#quickConnectSuggestions::item {{
  padding: 3px 5px;
  border-radius: {radius}px;
}}
QTreeWidget#quickConnectSuggestions::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QWidget#mobaRail {{
  background: {colors.window};
  border-right: 1px solid {colors.toolbar_border};
}}
QLabel#mobaRailButton, QToolButton#mobaRailButton {{
  color: {colors.sidebar_text};
  padding: 7px 3px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid {colors.toolbar_border};
  font-weight: 600;
}}
QLabel#mobaRailButton:hover, QToolButton#mobaRailButton:hover {{
  background: {colors.control};
  border-color: {colors.toolbar_border};
}}
QLabel#mobaRailButton:checked, QToolButton#mobaRailButton:checked {{
  color: {colors.primary};
  background: {colors.sidebar};
}}
QLabel#mobaRailAccent, QToolButton#mobaRailAccent {{
  color: {colors.status};
  padding: 7px 3px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid {colors.toolbar_border};
  font-weight: 700;
}}
QLabel#mobaRailAccent:hover, QToolButton#mobaRailAccent:hover {{
  background: {colors.control};
}}
QLabel#mobaRailAccent:checked, QToolButton#mobaRailAccent:checked {{
  background: {colors.sidebar};
}}
QTreeWidget#profileTree {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 0;
  border-right: 1px solid {colors.pane_border};
  padding: 5px;
  outline: 0;
  font-family: "Segoe UI", Arial, sans-serif;
}}
QTreeWidget#profileTree::item {{
  padding: {tree_padding};
  border-radius: {radius}px;
}}
QTreeWidget#profileTree::item:hover {{
  background: {colors.control};
}}
QTreeWidget#profileTree::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QTreeWidget#profileTree::branch {{
  background: transparent;
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
QTabBar::tab:hover {{
  background: {colors.control};
  color: {colors.control_text};
}}
QWidget#terminalPane {{
  background: {colors.pane};
}}
QFrame#terminalHeader {{
  background: {colors.toolbar};
  border: 1px solid {colors.pane_border};
  border-bottom: 0;
}}
QFrame#terminalCommandRow {{
  background: {colors.control};
  border-left: 1px solid {colors.pane_border};
  border-right: 1px solid {colors.pane_border};
  border-bottom: 1px solid {colors.pane_border};
}}
QLabel#terminalTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#terminalSource {{
  color: {colors.sidebar_muted};
}}
QLabel#terminalCommand {{
  color: {colors.terminal_accent};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QToolButton#terminalAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 3px 6px;
}}
QToolButton#terminalAction:hover {{
  border-color: {colors.control_hover};
}}
QToolButton#terminalAction:disabled {{
  color: {colors.sidebar_muted};
  background: {colors.pane};
}}
QDialog#workflowDialog {{
  background: {colors.pane};
  color: {colors.control_text};
}}
QDialog#workflowDialog QLabel#workflowTitle {{
  color: {colors.control_text};
  font-size: 18px;
  font-weight: 700;
}}
QDialog#workflowDialog QLabel#workflowSubtitle {{
  color: {colors.sidebar_muted};
}}
QDialog#workflowDialog QLineEdit,
QDialog#workflowDialog QComboBox,
QDialog#workflowDialog QPlainTextEdit {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: {control_padding};
}}
QDialog#workflowDialog QTreeWidget#workflowRows {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 1px solid {colors.pane_border};
  outline: 0;
}}
QDialog#workflowDialog QTreeWidget#workflowRows::item {{
  padding: 5px;
}}
QDialog#workflowDialog QTreeWidget#workflowRows::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QDialog#workflowDialog QTextEdit#workflowPreview {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border: 1px solid {colors.pane_border};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QDialog#workflowDialog QToolButton#workflowAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 4px 9px;
  font-weight: 600;
}}
QDialog#workflowDialog QToolButton#workflowAction:hover {{
  border-color: {colors.control_hover};
}}
QWidget#newSessionTab {{
  background: {colors.pane};
}}
QWidget#welcomeHome {{
  background: {colors.pane};
}}
QFrame#welcomePanel {{
  background: {colors.pane};
  border: 0;
}}
QLabel#welcomeTitle {{
  color: {colors.control_text};
  font-size: 26px;
  font-weight: 600;
}}
QLabel#welcomeSubtitle, QLabel#recentSessionsLabel {{
  color: {colors.sidebar_muted};
}}
QLabel#recentSessionsTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#paneStatus {{
  color: {colors.status};
  font-weight: 600;
  padding: 2px 7px;
  border: 1px solid {colors.status};
  border-radius: {radius}px;
}}
QLabel#paneStatus[state="running"] {{
  color: {colors.primary_text};
  background: {colors.primary};
  border-color: {colors.primary};
}}
QLabel#paneStatus[state="starting"], QLabel#paneStatus[state="stopping"] {{
  color: {colors.terminal_accent};
  border-color: {colors.terminal_accent};
}}
QLabel#paneStatus[state="error"] {{
  color: {colors.danger_text};
  border-color: {colors.danger};
}}
QTextEdit#terminalOutput, QPlainTextEdit {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border: 1px solid {colors.pane_border};
  border-top: 0;
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
    window="#101010",
    toolbar="#171717",
    toolbar_border="#454545",
    control="#222222",
    control_text="#f0f0f0",
    control_border="#5a5a5a",
    control_hover="#2f84d8",
    primary="#2d6ebd",
    primary_text="#ffffff",
    danger="#d73737",
    danger_text="#ffd0d0",
    sidebar="#151515",
    sidebar_text="#e8e8e8",
    sidebar_muted="#a6a6a6",
    sidebar_selected="#2b2b2b",
    sidebar_selected_text="#ffffff",
    pane="#202020",
    pane_border="#545454",
    tab="#1a1a1a",
    tab_selected="#242424",
    tab_text="#cfcfcf",
    tab_selected_text="#ffffff",
    terminal="#1f1f1f",
    terminal_text="#e9e9e9",
    terminal_accent="#f2cc00",
    log="#151515",
    log_text="#d9d9d9",
    status="#f2cc00",
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
        description="MobaXterm-like dark shell with quick connect, session tree, home tab and large ribbon actions.",
        profile_width=395,
        log_height=120,
        tab_position="north",
        density="moba-shell",
        toolbar_icon_size=24,
        list_spacing=1,
        document_mode=True,
        colors=MOBAXTERM_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="4px 13px",
        tree_padding="3px 5px",
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
