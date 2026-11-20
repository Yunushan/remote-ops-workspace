from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
)

from .gui_designs import (
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_top_stack_geometry,
)
from .gui_values import _safe_tooltip_html
from .launcher import LauncherError
from .quick_connect import QuickConnectCandidate

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QStatusBar, QTextEdit

    from .models import Profile


class WindowQuickConnect:
    """Build Quick Connect controls and route typed queries and saved profiles."""

    if TYPE_CHECKING:
        log: QTextEdit

        def current_design_is_moba(self) -> bool: ...
        def current_moba_connected_dock_is_active(self) -> bool: ...
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def _find_quick_connect_candidates(self, text: str, *, limit: int) -> list[QuickConnectCandidate]: ...
        def profile_icon_for_protocol(self, protocol: str) -> QIcon: ...
        def profile_by_name(self, name: str | None) -> Profile | None: ...
        def select_profile(self, name: str) -> None: ...
        def connect_selected(self, dry_run: bool) -> None: ...
        def launch_profile(self, profile: Profile, *, dry_run: bool, prefix: str) -> None: ...
        def show_message(self, icon: QMessageBox.Icon, title: object, message: object) -> QMessageBox.StandardButton: ...

    def create_quick_connect_controls(self) -> None:
        self.quick_connect = QLineEdit()
        self.quick_connect.setObjectName("quickConnect")
        quick_connect_chrome = gui_design_moba_quick_connect_chrome()
        self.quick_connect.setPlaceholderText(quick_connect_chrome.placeholder)
        self.quick_connect.setProperty("mobaQuickConnectConnectedIdleQuery", quick_connect_chrome.connected_idle_query)
        self.quick_connect.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            quick_connect_chrome.connected_suggestions_visible,
        )
        self.moba_quick_connect_chrome = self.build_moba_quick_connect_chrome()
        self.quick_connect_suggestions = QTreeWidget()
        self.quick_connect_suggestions.setObjectName("quickConnectSuggestions")
        self.quick_connect_suggestions.setHeaderHidden(True)
        self.quick_connect_suggestions.setColumnCount(1)
        self.quick_connect_suggestions.setRootIsDecorated(False)
        self.quick_connect_suggestions.setUniformRowHeights(True)
        suggestion_chrome = gui_design_moba_quick_connect_suggestion_chrome()
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionMaxRows", suggestion_chrome.max_visible_rows)
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionRowHeight", suggestion_chrome.row_height)
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionStaticWidth", suggestion_chrome.static_width)
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectSuggestionExpectedKinds",
            list(suggestion_chrome.expected_kinds),
        )
        self.quick_connect_suggestions.setProperty("mobaQuickConnectConnectedMode", "")
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            quick_connect_chrome.connected_suggestions_visible,
        )
        self.quick_connect_suggestions.setMaximumHeight(
            suggestion_chrome.max_visible_rows * suggestion_chrome.row_height + 10
        )
        self.quick_connect_suggestions.setVisible(False)

    def set_moba_quick_connect_connected_idle(self) -> None:
        chrome = gui_design_moba_quick_connect_chrome()
        previous_blocked = self.quick_connect.blockSignals(True)
        try:
            self.quick_connect.setText(chrome.connected_idle_query)
        finally:
            self.quick_connect.blockSignals(previous_blocked)
        self.moba_quick_connect_chrome.setProperty("mobaQuickConnectConnectedMode", "idle")
        self.moba_quick_connect_chrome.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            chrome.connected_suggestions_visible,
        )
        self.quick_connect.setProperty("mobaQuickConnectConnectedMode", "idle")
        self.quick_connect.setProperty("mobaQuickConnectConnectedIdleQuery", chrome.connected_idle_query)
        self.quick_connect.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            chrome.connected_suggestions_visible,
        )
        self.quick_connect_suggestions.clear()
        self.quick_connect_suggestions.setProperty("mobaQuickConnectConnectedMode", "idle")
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            chrome.connected_suggestions_visible,
        )
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionQuery", chrome.connected_idle_query)
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionKinds", [])
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionLabels", [])
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionDetails", [])
        self.quick_connect_suggestions.setVisible(chrome.connected_suggestions_visible)

    def clear_moba_quick_connect_connected_idle(self) -> None:
        if not hasattr(self, "quick_connect_suggestions"):
            return
        for widget in (self.moba_quick_connect_chrome, self.quick_connect, self.quick_connect_suggestions):
            widget.setProperty("mobaQuickConnectConnectedMode", "")
            widget.setProperty("mobaQuickConnectConnectedSuggestionVisible", False)

    def update_quick_connect_suggestions(self) -> None:
        chrome = gui_design_moba_quick_connect_suggestion_chrome()
        quick_connect_chrome = gui_design_moba_quick_connect_chrome()
        self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionQuery", self.quick_connect.text().strip())
        if not self.current_design_is_moba():
            self.quick_connect_suggestions.clear()
            self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionKinds", [])
            self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionLabels", [])
            self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionDetails", [])
            self.quick_connect_suggestions.setProperty("mobaQuickConnectConnectedMode", "")
            self.quick_connect_suggestions.setProperty("mobaQuickConnectConnectedSuggestionVisible", False)
            self.quick_connect_suggestions.setVisible(False)
            return
        if (
            self.current_moba_connected_dock_is_active()
            and self.quick_connect.text().strip() == quick_connect_chrome.connected_idle_query
        ):
            self.set_moba_quick_connect_connected_idle()
            return
        connected_mode = "typed" if self.current_moba_connected_dock_is_active() else ""
        self.moba_quick_connect_chrome.setProperty("mobaQuickConnectConnectedMode", connected_mode)
        self.quick_connect.setProperty("mobaQuickConnectConnectedMode", connected_mode)
        self.quick_connect_suggestions.setProperty("mobaQuickConnectConnectedMode", connected_mode)
        try:
            candidates = self._find_quick_connect_candidates(self.quick_connect.text(), limit=6)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Quick connect unavailable: {exc}")
            return
        self.quick_connect_suggestions.clear()
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectSuggestionKinds",
            [candidate.kind for candidate in candidates],
        )
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectSuggestionLabels",
            [candidate.label for candidate in candidates],
        )
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectSuggestionDetails",
            [candidate.detail for candidate in candidates],
        )
        for candidate in candidates:
            item = QTreeWidgetItem([f"{candidate.label}{chrome.detail_separator}{candidate.detail}"])
            item.setData(0, Qt.ItemDataRole.UserRole, candidate)
            item.setData(0, int(Qt.ItemDataRole.UserRole) + 1, candidate.kind)
            item.setData(0, int(Qt.ItemDataRole.UserRole) + 2, candidate.label)
            item.setData(0, int(Qt.ItemDataRole.UserRole) + 3, candidate.detail)
            item.setSizeHint(0, QSize(0, chrome.row_height))
            item.setToolTip(0, _safe_tooltip_html(candidate.detail))
            if candidate.kind == "direct":
                item.setIcon(0, self.profile_icon_for_protocol(candidate.profile.protocol if candidate.profile else "ssh"))
            else:
                profile = self.profile_by_name(candidate.profile_name)
                if profile is not None:
                    item.setIcon(0, self.profile_icon_for_protocol(profile.protocol))
            self.quick_connect_suggestions.addTopLevelItem(item)
        if self.quick_connect_suggestions.topLevelItemCount() > 0:
            self.quick_connect_suggestions.setCurrentItem(self.quick_connect_suggestions.topLevelItem(0))
        suggestions_visible = self.quick_connect_suggestions.topLevelItemCount() > 0
        self.quick_connect_suggestions.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            suggestions_visible,
        )
        self.moba_quick_connect_chrome.setProperty(
            "mobaQuickConnectConnectedSuggestionVisible",
            suggestions_visible,
        )
        self.quick_connect.setProperty("mobaQuickConnectConnectedSuggestionVisible", suggestions_visible)
        self.quick_connect_suggestions.setVisible(suggestions_visible)

    def run_quick_connect(self) -> None:
        text = self.quick_connect.text().strip()
        if not text:
            return
        item = self.quick_connect_suggestions.currentItem()
        if item is not None:
            candidate = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(candidate, QuickConnectCandidate):
                self.run_quick_connect_candidate(item)
                return
        try:
            candidates = self._find_quick_connect_candidates(text, limit=1)
        except (OSError, ValueError) as exc:
            self.show_message(QMessageBox.Icon.Warning, "Quick connect failed", str(exc))
            return
        if candidates:
            self.run_quick_connect_candidate_value(candidates[0])
            return
        self.log.append(f"QUICK CONNECT MISS: {text}")
        self.statusBar().showMessage(f"Quick connect miss: {text}")

    def run_quick_connect_candidate(self, item: QTreeWidgetItem) -> None:
        candidate = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(candidate, QuickConnectCandidate):
            self.run_quick_connect_candidate_value(candidate)

    def run_quick_connect_candidate_value(self, candidate: QuickConnectCandidate) -> None:
        try:
            if candidate.kind == "profile" and candidate.profile_name:
                self.select_profile(candidate.profile_name)
                self.connect_selected(False)
            elif candidate.profile is not None:
                self.launch_profile(candidate.profile, dry_run=False, prefix="QUICK CONNECT")
        except (OSError, ValueError, LauncherError) as exc:
            self.show_message(QMessageBox.Icon.Warning, "Quick connect failed", str(exc))
            return
        self.quick_connect_suggestions.setVisible(False)
        self.statusBar().showMessage(f"Quick connect: {candidate.label}")

    def build_moba_quick_connect_chrome(self) -> QFrame:
        chrome = gui_design_moba_quick_connect_chrome()
        suggestions = gui_design_moba_quick_connect_suggestion_chrome()
        panel = QFrame()
        panel.setObjectName("mobaQuickConnectChrome")
        panel.setProperty("designPreset", "mobaxterm")
        panel.setProperty("mobaQuickConnectPlaceholder", chrome.placeholder)
        panel.setProperty("mobaQuickConnectDropdownMarker", chrome.dropdown_marker)
        panel.setProperty("mobaQuickConnectHeight", chrome.static_height)
        panel.setProperty("mobaQuickConnectMarkerWidth", chrome.marker_width)
        panel.setProperty("mobaQuickConnectInputLeft", chrome.input_left)
        panel.setProperty("mobaQuickConnectConnectedIdleQuery", chrome.connected_idle_query)
        panel.setProperty("mobaQuickConnectConnectedSuggestionVisible", chrome.connected_suggestions_visible)
        panel.setProperty("mobaQuickConnectConnectedMode", "")
        panel.setProperty("mobaQuickConnectSuggestionQuery", suggestions.preview_query)
        panel.setProperty("mobaQuickConnectSuggestionExpectedKinds", list(suggestions.expected_kinds))
        panel.setProperty("mobaQuickConnectSuggestionMaxRows", suggestions.max_visible_rows)
        stack = gui_design_moba_top_stack_geometry()
        panel.setProperty("mobaTopStackQuickConnectY", stack.quick_connect_y)
        panel.setProperty("mobaTopStackQuickConnectHeight", stack.quick_connect_height)
        panel.setFixedHeight(chrome.static_height)
        panel.setFocusProxy(self.quick_connect)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.quick_connect.setProperty("mobaQuickConnectPlaceholder", chrome.placeholder)
        self.quick_connect.setProperty("mobaQuickConnectInputLeft", chrome.input_left)
        self.quick_connect.setProperty("mobaQuickConnectConnectedIdleQuery", chrome.connected_idle_query)
        self.quick_connect.setProperty("mobaQuickConnectConnectedMode", "")
        layout.addWidget(self.quick_connect, 1)
        dropdown = QLabel(chrome.dropdown_marker)
        dropdown.setObjectName("mobaQuickConnectDropdown")
        dropdown.setProperty("mobaQuickConnectDropdownMarker", chrome.dropdown_marker)
        dropdown.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dropdown.setFixedWidth(chrome.marker_width)
        layout.addWidget(dropdown)
        panel.setVisible(False)
        return panel
