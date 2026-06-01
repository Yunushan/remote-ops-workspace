from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GUI_DESIGN_ID = "native"


@dataclass(frozen=True)
class GuiDesignPreset:
    id: str
    label: str
    description: str
    profile_width: int
    log_height: int
    tab_position: str
    stylesheet: str


NATIVE_STYLESHEET = ""

MOBAXTERM_STYLE_STYLESHEET = """
QMainWindow#remoteOpsMain {
  background: #111820;
}
QToolBar#mainToolbar {
  background: #17212b;
  border-bottom: 1px solid #2f4354;
  spacing: 4px;
  padding: 4px;
}
QPushButton, QComboBox, QLineEdit {
  background: #223140;
  color: #f4f7fa;
  border: 1px solid #3d5368;
  border-radius: 3px;
  padding: 4px 8px;
}
QPushButton:hover, QComboBox:hover {
  border-color: #55b7d9;
}
QListWidget#profileTree {
  background: #0f171f;
  color: #e7edf2;
  border: 0;
  font-family: Consolas, "Cascadia Mono", monospace;
}
QTabWidget#sessionTabs::pane {
  border: 1px solid #314456;
}
QTabBar::tab {
  background: #1d2b38;
  color: #f4f7fa;
  padding: 6px 12px;
  border: 1px solid #314456;
}
QTabBar::tab:selected {
  background: #247f9e;
}
QTextEdit, QPlainTextEdit {
  background: #071014;
  color: #d8f4ff;
  border: 1px solid #263946;
  font-family: Consolas, "Cascadia Mono", monospace;
}
QLabel {
  color: #e7edf2;
}
"""

SECURECRT_STYLE_STYLESHEET = """
QMainWindow#remoteOpsMain {
  background: #101010;
}
QToolBar#mainToolbar {
  background: #202020;
  border-bottom: 1px solid #383838;
  padding: 3px;
}
QPushButton, QComboBox, QLineEdit {
  background: #2a2a2a;
  color: #eeeeee;
  border: 1px solid #545454;
  border-radius: 2px;
  padding: 4px 8px;
}
QListWidget#profileTree {
  background: #171717;
  color: #eeeeee;
  border-right: 1px solid #383838;
  font-family: "Segoe UI", Arial, sans-serif;
}
QTabWidget#sessionTabs::pane {
  border: 1px solid #393939;
}
QTabBar::tab {
  background: #252525;
  color: #e6e6e6;
  padding: 5px 11px;
  border: 1px solid #393939;
}
QTabBar::tab:selected {
  background: #111111;
  border-bottom-color: #111111;
}
QTextEdit, QPlainTextEdit {
  background: #000000;
  color: #d8d8d8;
  border: 1px solid #303030;
  font-family: Consolas, "Cascadia Mono", monospace;
}
QLabel {
  color: #e6e6e6;
}
"""

TERMIUS_STYLE_STYLESHEET = """
QMainWindow#remoteOpsMain {
  background: #111418;
}
QToolBar#mainToolbar {
  background: #181d23;
  border-bottom: 1px solid #2a323c;
  padding: 5px;
}
QPushButton, QComboBox, QLineEdit {
  background: #232b34;
  color: #f3f6f9;
  border: 1px solid #35414d;
  border-radius: 6px;
  padding: 5px 9px;
}
QPushButton:hover, QComboBox:hover {
  border-color: #60d3a4;
}
QListWidget#profileTree {
  background: #151a20;
  color: #edf4f7;
  border: 0;
}
QTabWidget#sessionTabs::pane {
  border: 1px solid #2e3944;
}
QTabBar::tab {
  background: #1c2229;
  color: #dce6eb;
  padding: 7px 13px;
  border: 1px solid #2e3944;
}
QTabBar::tab:selected {
  background: #284638;
  color: #ffffff;
}
QTextEdit, QPlainTextEdit {
  background: #0b0f13;
  color: #d8f7e6;
  border: 1px solid #2b363f;
  font-family: "Cascadia Mono", Consolas, monospace;
}
QLabel {
  color: #edf4f7;
}
"""

REMMINA_STYLE_STYLESHEET = """
QMainWindow#remoteOpsMain {
  background: #f2f3f5;
}
QToolBar#mainToolbar {
  background: #ffffff;
  border-bottom: 1px solid #c9cdd3;
  padding: 4px;
}
QPushButton, QComboBox, QLineEdit {
  background: #ffffff;
  color: #20242a;
  border: 1px solid #b8bec7;
  border-radius: 3px;
  padding: 4px 8px;
}
QPushButton:hover, QComboBox:hover {
  border-color: #547aa5;
}
QListWidget#profileTree {
  background: #ffffff;
  color: #1e2329;
  border-right: 1px solid #c9cdd3;
}
QTabWidget#sessionTabs::pane {
  border: 1px solid #c9cdd3;
}
QTabBar::tab {
  background: #e7eaee;
  color: #1e2329;
  padding: 6px 12px;
  border: 1px solid #c9cdd3;
}
QTabBar::tab:selected {
  background: #ffffff;
}
QTextEdit, QPlainTextEdit {
  background: #ffffff;
  color: #171b20;
  border: 1px solid #c9cdd3;
  font-family: Consolas, "Cascadia Mono", monospace;
}
QLabel {
  color: #1e2329;
}
"""

MREMOTENG_STYLE_STYLESHEET = """
QMainWindow#remoteOpsMain {
  background: #dfe4ea;
}
QToolBar#mainToolbar {
  background: #f7f8fa;
  border-bottom: 1px solid #aeb7c2;
  padding: 3px;
}
QPushButton, QComboBox, QLineEdit {
  background: #ffffff;
  color: #1b242d;
  border: 1px solid #9ea9b5;
  border-radius: 2px;
  padding: 4px 7px;
}
QListWidget#profileTree {
  background: #f7f8fa;
  color: #1b242d;
  border-right: 1px solid #aeb7c2;
  font-family: "Segoe UI", Arial, sans-serif;
}
QTabWidget#sessionTabs::pane {
  border: 1px solid #aeb7c2;
}
QTabBar::tab {
  background: #eef1f4;
  color: #1b242d;
  padding: 5px 10px;
  border: 1px solid #aeb7c2;
}
QTabBar::tab:selected {
  background: #ffffff;
}
QTextEdit, QPlainTextEdit {
  background: #ffffff;
  color: #101820;
  border: 1px solid #aeb7c2;
  font-family: Consolas, "Cascadia Mono", monospace;
}
QLabel {
  color: #1b242d;
}
"""


GUI_DESIGN_PRESETS: tuple[GuiDesignPreset, ...] = (
    GuiDesignPreset(
        id=DEFAULT_GUI_DESIGN_ID,
        label="Native",
        description="Default Qt desktop layout.",
        profile_width=300,
        log_height=170,
        tab_position="north",
        stylesheet=NATIVE_STYLESHEET,
    ),
    GuiDesignPreset(
        id="mobaxterm",
        label="MobaXterm-style",
        description="Dense operator workspace with connection tree, toolbar actions, tabs and split panes.",
        profile_width=330,
        log_height=150,
        tab_position="north",
        stylesheet=MOBAXTERM_STYLE_STYLESHEET,
    ),
    GuiDesignPreset(
        id="securecrt",
        label="SecureCRT-style",
        description="Terminal-first workspace with restrained dark chrome and wide session tabs.",
        profile_width=260,
        log_height=115,
        tab_position="north",
        stylesheet=SECURECRT_STYLE_STYLESHEET,
    ),
    GuiDesignPreset(
        id="termius",
        label="Termius-style",
        description="Dark SSH-focused workspace with compact host list and vault-oriented visual treatment.",
        profile_width=285,
        log_height=135,
        tab_position="west",
        stylesheet=TERMIUS_STYLE_STYLESHEET,
    ),
    GuiDesignPreset(
        id="remmina",
        label="Remmina-style",
        description="Light remote-desktop oriented workspace for protocol profiles and viewer tabs.",
        profile_width=320,
        log_height=160,
        tab_position="north",
        stylesheet=REMMINA_STYLE_STYLESHEET,
    ),
    GuiDesignPreset(
        id="mremoteng",
        label="mRemoteNG-style",
        description="Classic connection-manager workspace with a persistent left tree and document tabs.",
        profile_width=360,
        log_height=145,
        tab_position="north",
        stylesheet=MREMOTENG_STYLE_STYLESHEET,
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
