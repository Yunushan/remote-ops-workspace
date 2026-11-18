from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QMessageBox, QSplitter, QWidget

from .enterprise_policy import assert_profile_launch_allowed
from .launcher import LauncherError
from .layouts import Layout, build_layout_terminal_sessions
from .models import Profile
from .terminal import TerminalPanePlan

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox, QStatusBar, QTabWidget, QTextEdit

    from .gui_dialogs import LayoutDialog
    from .gui_terminal import TerminalPane
    from .layouts import LayoutStore
    from .storage import ProfileStore


class SavedLayoutActions:
    """Saved-layout workflows for the Qt main window."""

    if TYPE_CHECKING:
        layout_store: LayoutStore
        store: ProfileStore
        layout_select: QComboBox
        log: QTextEdit
        tabs: QTabWidget

        def create_layout_dialog(self, layout: Layout | None = None) -> LayoutDialog: ...
        def refresh_layouts(self) -> None: ...
        def show_message(self, icon: QMessageBox.Icon, title: object, message: object) -> QMessageBox.StandardButton: ...
        def confirm_action(self, title: str, message: str) -> bool: ...
        def literal_tab_tooltip(self, index: int) -> str: ...
        def base_tab_tooltip(self, index: int) -> str: ...
        def set_literal_tab_tooltip(self, index: int, text: object, *, update_base: bool = True) -> None: ...
        def new_terminal_pane(
            self, plan: TerminalPanePlan, *, profile: Profile | None = None, autostart: bool = True,
        ) -> TerminalPane: ...
        def remember_terminal_plan(self, plan: TerminalPanePlan, *, profile: Profile | None = None) -> None: ...
        def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int: ...
        def update_session_status(self) -> None: ...
        def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]: ...
        def start_terminal_pane_when_active(self, pane: TerminalPane, index: int) -> None: ...
        def statusBar(self) -> QStatusBar: ...

    def create_layout(self) -> None:
        dialog = self.create_layout_dialog()
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                layout = dialog.workspace_layout()
                self.layout_store.add(layout)
            except (OSError, ValueError) as exc:
                dialog.show_validation_error(str(exc))
                continue
            self.refresh_layouts()
            self.layout_select.setCurrentText(layout.name)
            self.log.append(f"LAYOUT SAVED: {layout.name}")
            return

    def edit_selected_layout(self) -> None:
        name = self.layout_select.currentText()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "No saved layout selected.",
            )
            return
        try:
            current = self.layout_store.get(name)
        except (KeyError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Layout failed",
                str(exc),
            )
            return
        dialog = self.create_layout_dialog(current)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                layout = dialog.workspace_layout()
                self.save_layout(layout, original_name=name)
            except (KeyError, OSError, ValueError) as exc:
                dialog.show_validation_error(str(exc))
                continue
            self.refresh_layouts()
            self.layout_select.setCurrentText(layout.name)
            self.log.append(f"LAYOUT UPDATED: {layout.name}")
            return

    def remove_selected_layout(self) -> None:
        name = self.layout_select.currentText()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "No saved layout selected.",
            )
            return
        if not self.confirm_action("Remove layout", f"Remove layout {name}?"):
            return
        try:
            self.layout_store.remove(name)
            self.refresh_layouts()
            self.log.append(f"LAYOUT REMOVED: {name}")
        except (KeyError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Layout failed",
                str(exc),
            )

    def save_layout(self, layout: Layout, original_name: str) -> None:
        self.layout_store.replace_named(original_name, layout)
        if layout.name != original_name:
            self.retarget_open_layout_instances(original_name, layout.name)

    def retarget_open_layout_instances(self, original_name: str, new_name: str) -> None:
        def retarget_text(value: str) -> str:
            if not value.startswith(original_name):
                return value
            suffix = value[len(original_name):]
            if not suffix or suffix.startswith((" ·", ":", " copy")):
                return f"{new_name}{suffix}"
            return value

        for index in range(self.tabs.count()):
            root = self.tabs.widget(index)
            if root is None:
                continue
            candidates = [root, *root.findChildren(QWidget)]
            matched = [
                widget
                for widget in candidates
                if widget.property("savedLayoutName") == original_name
            ]
            if not matched:
                continue
            for widget in matched:
                widget.setProperty("savedLayoutName", new_name)
            title = self.tabs.tabText(index)
            tooltip = self.literal_tab_tooltip(index)
            base_tooltip = self.base_tab_tooltip(index)
            self.tabs.setTabText(index, retarget_text(title))
            updated_base = retarget_text(base_tooltip)
            updated_tooltip = retarget_text(tooltip)
            self.set_literal_tab_tooltip(index, updated_base)
            if updated_tooltip != updated_base:
                self.set_literal_tab_tooltip(
                    index,
                    updated_tooltip,
                    update_base=False,
                )

    def open_selected_layout(self) -> None:
        name = self.layout_select.currentText()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "No saved layout selected.",
            )
            return
        try:
            layout = self.layout_store.get(name)
            sessions = self.layout_launch_sessions(layout)
            plans = [plan for plan, _profile in sessions]
            profiles = [profile for _plan, profile in sessions]
            widget = self.layout_widget(layout, plans, profiles)
            self.bind_layout_resize_persistence(layout.name, widget)
            for plan, profile in sessions:
                self.remember_terminal_plan(plan, profile=profile)
            tab_index = self.add_workspace_tab(widget, layout.name, role="layout")
            self.log.append(f"LAYOUT: {layout.name} ({len(plans)} panes)")
            self.update_session_status()
            for pane in self.terminal_panes_in(widget):
                self.start_terminal_pane_when_active(pane, tab_index)
        except (KeyError, LauncherError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Layout failed",
                str(exc),
            )

    def layout_launch_profiles(self, layout: Layout) -> list[Profile]:
        return [profile for _plan, profile in self.layout_launch_sessions(layout)]

    def layout_launch_sessions(self, layout: Layout) -> list[tuple[TerminalPanePlan, Profile]]:
        sessions = build_layout_terminal_sessions(
            layout,
            self.store,
            surface="gui",
        )
        for _plan, profile in sessions:
            assert_profile_launch_allowed(profile, surface="gui")
        return sessions

    def layout_widget(
        self,
        layout: Layout,
        plans: list[TerminalPanePlan],
        profiles: list[Profile],
    ) -> QWidget:
        if len(plans) == 1:
            return self.new_terminal_pane(
                plans[0],
                profile=profiles[0],
                autostart=False,
            )
        if layout.orientation == "vertical":
            splitter = QSplitter(Qt.Orientation.Vertical)
            for plan, profile in zip(plans, profiles, strict=True):
                splitter.addWidget(
                    self.new_terminal_pane(
                        plan,
                        profile=profile,
                        autostart=False,
                    )
                )
            self.restore_layout_splitter_sizes(splitter, layout.splitter_sizes)
            return splitter
        if layout.orientation == "horizontal":
            splitter = QSplitter(Qt.Orientation.Horizontal)
            for plan, profile in zip(plans, profiles, strict=True):
                splitter.addWidget(
                    self.new_terminal_pane(
                        plan,
                        profile=profile,
                        autostart=False,
                    )
                )
            self.restore_layout_splitter_sizes(splitter, layout.splitter_sizes)
            return splitter
        root = QSplitter(Qt.Orientation.Vertical)
        for offset in range(0, len(plans), 2):
            row = QSplitter(Qt.Orientation.Horizontal)
            for plan, profile in zip(
                plans[offset : offset + 2],
                profiles[offset : offset + 2],
                strict=True,
            ):
                row.addWidget(
                    self.new_terminal_pane(
                        plan,
                        profile=profile,
                        autostart=False,
                    )
                )
            root.addWidget(row)
        self.restore_layout_splitter_sizes(root, layout.splitter_sizes)
        return root

    def layout_splitters(self, widget: QWidget | None) -> list[QSplitter]:
        if not isinstance(widget, QSplitter):
            return []
        splitters = [widget]
        for index in range(widget.count()):
            splitters.extend(self.layout_splitters(widget.widget(index)))
        return splitters

    def restore_layout_splitter_sizes(self, widget: QWidget, saved_sizes: list[list[int]]) -> None:
        splitters = self.layout_splitters(widget)
        for splitter in splitters:
            splitter.setChildrenCollapsible(False)
            for index in range(splitter.count()):
                splitter.setCollapsible(index, False)
                splitter.setStretchFactor(index, 1)
        if len(splitters) != len(saved_sizes):
            return
        for splitter, sizes in zip(splitters, saved_sizes, strict=True):
            if len(sizes) == splitter.count() and all(size > 0 for size in sizes):
                splitter.setSizes(sizes)

    def bind_layout_resize_persistence(self, name: str, widget: QWidget) -> None:
        widget.setProperty("savedLayoutName", name)
        for splitter in self.layout_splitters(widget):
            splitter.splitterMoved.connect(
                lambda _position, _index, layout_widget=widget: self.persist_layout_resize_state(
                    str(layout_widget.property("savedLayoutName") or ""),
                    layout_widget,
                )
            )

    def persist_layout_resize_state(self, name: str, widget: QWidget) -> None:
        sizes = [
            [max(1, int(size)) for size in splitter.sizes()]
            for splitter in self.layout_splitters(widget)
        ]
        if not sizes:
            return
        try:
            saved = self.layout_store.update_splitter_sizes(name, sizes)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Layout resize could not be saved: {exc}")
            return
        if saved:
            self.log.append(f"LAYOUT RESIZE SAVED: {name}")

    def bind_cloned_layout_persistence(self, root: QWidget) -> None:
        for widget in [root, *root.findChildren(QWidget)]:
            saved_layout_name = widget.property("savedLayoutName")
            if isinstance(saved_layout_name, str) and saved_layout_name:
                self.bind_layout_resize_persistence(saved_layout_name, widget)
