from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from . import gui_preset_properties
from .gui_designs import (
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_stack_geometry,
    gui_design_preset_selection_route,
    gui_design_status_segments,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QMenuBar, QStatusBar, QTabWidget, QToolBar

    from .gui_designs import GuiDesignPreset


class WindowChrome:
    """Build and update the main window's status bar and top chrome."""

    if TYPE_CHECKING:
        _saved_profile_names: set[str]
        main_menu_bar: QMenuBar
        main_toolbar: QToolBar
        moba_quick_connect_chrome: QFrame
        status_segment_labels: list[QLabel]
        tabs: QTabWidget

        def activate_next_tab(self) -> None: ...
        def activate_previous_tab(self) -> None: ...
        def close_current_tab(self) -> None: ...
        def moba_utility_icon(self, icon_key: str, fill: str, *, size: int = 20) -> QIcon: ...
        def setProperty(self, name: str, value: object) -> bool: ...  # noqa: N802
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def tab_role(self, index: int) -> str: ...

    def refresh_live_status_segments(self) -> bool:
        if cast(QWidget, self).property("guiPreviewSamples"):
            return False
        count = sum(self.tab_role(index) not in {"home", "new-session"} for index in range(self.tabs.count()))
        values = (("profiles", f"Saved profiles: {len(self._saved_profile_names)}"),
                  ("sessions", f"Open workspace tabs: {count}"), ("", ""))
        for label, (key, text) in zip(self.status_segment_labels, values, strict=True):
            label.setText(text)
            label.setToolTip(text)
            label.setProperty("productStatusKey", key)
        return True

    def create_status_segments(self) -> list[QLabel]:
        self.statusBar().setObjectName("statusBar")
        self.status_notice_label = QLabel()
        self.status_notice_label.setObjectName("productStatusNotice")
        self.statusBar().addWidget(self.status_notice_label, 1)
        labels: list[QLabel] = []
        for _index in range(3):
            label = QLabel()
            label.setObjectName("productStatusSegment")
            label.setMinimumWidth(92)
            self.statusBar().addPermanentWidget(label)
            labels.append(label)
        self.moba_bottom_edge_controls = self.create_moba_bottom_edge_controls()
        self.statusBar().addPermanentWidget(self.moba_bottom_edge_controls)
        self.status_marker_label = QLabel()
        self.status_marker_label.setObjectName("productStatusMarker")
        self.status_marker_label.setMinimumWidth(18)
        self.statusBar().addPermanentWidget(self.status_marker_label)
        return labels

    def create_moba_bottom_edge_controls(self) -> QFrame:
        controls = QFrame()
        controls.setObjectName("mobaBottomEdgeControls")
        actions = gui_design_moba_bottom_edge_controls()
        controls.setProperty("mobaBottomEdgeControlKeys", [action.key for action in actions])
        layout = QHBoxLayout(controls)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        slots = {
            "tab-left": self.activate_previous_tab,
            "tab-right": self.activate_next_tab,
            "close-active": self.close_current_tab,
        }
        for action in actions:
            button = QToolButton()
            button.setObjectName("mobaBottomEdgeControl")
            button.setProperty("mobaBottomEdgeKey", action.key)
            button.setProperty("mobaBottomEdgeIconKey", action.icon_key)
            button.setProperty("mobaBottomEdgeStaticX", action.static_x)
            button.setToolTip(action.tooltip)
            button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
            button.setIconSize(QSize(14, 14))
            button.setFixedSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.clicked.connect(slots[action.key])
            layout.addWidget(button)
        controls.setVisible(False)
        return controls

    def configure_status_bar_for_design(self, preset: GuiDesignPreset) -> None:
        selection_route = gui_design_preset_selection_route(preset.id)
        if preset.id == "mobaxterm":
            chrome = gui_design_moba_status_bar_chrome()
            status_bar = self.statusBar()
            status_bar.setFixedHeight(chrome.static_height)
            status_bar.setProperty("mobaStatusStaticHeight", chrome.static_height)
            status_bar.setProperty("mobaStatusSegmentStartRightOffset", chrome.segment_start_right_offset)
            self.status_notice_label.setText(f"{chrome.notice} - {chrome.product_note}")
            self.status_notice_label.setToolTip(f"{preset.label}: {chrome.product_note}")
            self.status_notice_label.setProperty("productStatusKey", "notice")
            self.status_notice_label.setProperty("mobaStatusNoticeX", chrome.notice_x)
            self.status_notice_label.setProperty("mobaStatusNoticeY", chrome.notice_y)
            self.status_notice_label.setProperty("mobaStatusProductNoteX", chrome.product_note_x)
            self.status_notice_label.setProperty("mobaStatusProductNoteY", chrome.product_note_y)
            self.status_notice_label.setProperty("mobaStatusTextFontSize", chrome.text_font_size)
            self.status_marker_label.setText(chrome.right_marker)
            self.status_marker_label.setToolTip(chrome.right_marker_tooltip)
            self.status_marker_label.setProperty("productStatusKey", "right-marker")
            self.status_marker_label.setProperty("mobaStatusMarkerRightInset", chrome.marker_right_inset)
            self.status_marker_label.setProperty("mobaStatusMarkerY", chrome.marker_y)
            self.status_marker_label.setProperty("mobaStatusMarkerWidth", chrome.marker_width)
            self.status_marker_label.setProperty("mobaStatusMarkerHeight", chrome.marker_height)
            self.moba_bottom_edge_controls.setVisible(True)
            if self.refresh_live_status_segments():
                return
            for label, segment in zip(self.status_segment_labels, gui_design_moba_status_segments(), strict=False):
                label.setText(segment.text)
                label.setToolTip(segment.tooltip)
                label.setProperty("productStatusKey", segment.key)
                gui_preset_properties.apply_preset_selection_route_properties(label, selection_route)
            return
        self.statusBar().setFixedHeight(22)
        self.status_notice_label.setText("Remote Ops Workspace")
        self.status_notice_label.setToolTip(preset.description)
        self.status_notice_label.setProperty("productStatusKey", "notice")
        self.status_marker_label.setText("")
        self.status_marker_label.setToolTip("")
        self.status_marker_label.setProperty("productStatusKey", "right-marker")
        self.moba_bottom_edge_controls.setVisible(False)
        if self.refresh_live_status_segments():
            return
        for label, text in zip(self.status_segment_labels, gui_design_status_segments(preset.id), strict=False):
            label.setText(text)
            label.setToolTip(f"{preset.label}: {text}")
            label.setProperty("productStatusKey", text.lower().replace(" ", "-"))
            gui_preset_properties.apply_preset_selection_route_properties(label, selection_route)

    def apply_moba_top_stack_geometry(self) -> None:
        stack = gui_design_moba_top_stack_geometry()
        properties = {
            "mobaTopStackTitlebarHeight": stack.titlebar_height,
            "mobaTopStackMenuY": stack.menu_y,
            "mobaTopStackMenuHeight": stack.menu_height,
            "mobaTopStackRibbonY": stack.ribbon_y,
            "mobaTopStackRibbonHeight": stack.ribbon_height,
            "mobaTopStackQuickConnectY": stack.quick_connect_y,
            "mobaTopStackQuickConnectHeight": stack.quick_connect_height,
            "mobaTopStackLeftDockY": stack.left_dock_y,
            "mobaTopStackTabY": stack.tab_y,
            "mobaTopStackTabHeight": stack.tab_height,
            "mobaTopStackTerminalContentY": stack.terminal_content_y,
            "mobaTopStackStatusHeight": stack.status_height,
            "mobaTopStackSideWidth": stack.side_width,
            "mobaTopStackRailWidth": stack.rail_width,
        }
        for key, value in properties.items():
            self.setProperty(key, value)
        self.main_menu_bar.setProperty("mobaTopStackMenuY", stack.menu_y)
        self.main_menu_bar.setProperty(
            "mobaTopStackMenuHeight",
            stack.menu_height,
        )
        self.main_toolbar.setProperty("mobaTopStackRibbonY", stack.ribbon_y)
        self.main_toolbar.setProperty("mobaTopStackRibbonHeight", stack.ribbon_height)
        self.moba_quick_connect_chrome.setProperty("mobaTopStackQuickConnectY", stack.quick_connect_y)
        self.moba_quick_connect_chrome.setProperty("mobaTopStackQuickConnectHeight", stack.quick_connect_height)
        self.tabs.setProperty("mobaTopStackTabY", stack.tab_y)
        self.tabs.setProperty("mobaTopStackTabHeight", stack.tab_height)

    def apply_moba_titlebar_chrome(self, title: str) -> None:
        chrome = gui_design_moba_titlebar_chrome()
        self.setProperty("mobaTitlebarTitle", title)
        self.setProperty("mobaTitlebarIconKey", chrome.icon_key)
        self.setProperty("mobaTitlebarHeight", chrome.static_height)
        self.setProperty("mobaTitlebarIconLeft", chrome.icon_left)
        self.setProperty("mobaTitlebarIconSize", chrome.icon_size)
        self.setProperty("mobaTitlebarTitleLeft", chrome.title_left)
        self.setProperty("mobaTitlebarControlKeys", list(chrome.control_keys))
        self.setProperty("mobaTitlebarControlWidth", chrome.control_width)
