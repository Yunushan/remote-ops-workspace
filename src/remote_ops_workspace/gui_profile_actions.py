from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFileDialog, QMenu, QMessageBox

from .enterprise_policy import assert_profile_launch_allowed
from .gui_designs import gui_design_interaction_state
from .gui_values import _required_gui_value
from .launcher import LauncherError, build_launch_plan
from .profile_importers import import_profiles
from .terminal import terminal_plan_for_profile, terminal_plan_for_sftp_browser

if TYPE_CHECKING:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QTextEdit, QToolButton, QTreeWidget, QTreeWidgetItem, QWidget

    from .gui_connected import ConnectedSessionPanel
    from .gui_designs import GuiInteractionState
    from .gui_dialogs import ProfileDialog, ProfileImportPreviewDialog, TransferQueueDialog
    from .models import Profile
    from .profile_importers import ProfileImportResult
    from .storage import ProfileStore
    from .terminal import TerminalPanePlan


class ProfileActions:
    """Manage the selected profile and dispatch profile workflows from the desktop."""

    if TYPE_CHECKING:
        profile_list: QTreeWidget
        product_toolbar_button_by_key: dict[str, QToolButton]
        store: ProfileStore
        log: QTextEdit

        def show_message(self, icon: QMessageBox.Icon, title: object, message: object) -> QMessageBox.StandardButton: ...
        def confirm_action(self, title: str, message: str) -> bool: ...
        def selected_profile_name(self) -> str | None: ...
        def select_profile(self, name: str) -> None: ...
        def refresh_profiles(self) -> None: ...
        def current_design_id(self) -> str: ...
        def set_toolbar_widget_enabled(self, widget: QWidget, enabled: bool) -> None: ...
        def set_interaction_state(self, widget: QToolButton, state: str) -> None: ...
        def toolbar_interaction_state(self, key: str, state: GuiInteractionState) -> str: ...
        def create_profile_dialog(self, profile: Profile | None = None) -> ProfileDialog: ...
        def create_profile_import_preview_dialog(
            self, source: str, result: ProfileImportResult,
        ) -> ProfileImportPreviewDialog: ...
        def create_transfer_queue_dialog(self, profile: Profile) -> TransferQueueDialog: ...
        def profile_tab_label(self, profile: Profile) -> str: ...
        def profile_tab_status(self) -> str: ...
        def moba_connected_profile_supported(self, profile: Profile) -> bool: ...
        def moba_connected_remote_path_for_profile(self, profile: Profile) -> str: ...
        def open_moba_connected_session_tab(
            self, profile: Profile, plan: TerminalPanePlan, *, remote_path: str = "/",
            tab_title: str | None = None, tab_status: str | None = None,
        ) -> ConnectedSessionPanel: ...
        def open_terminal_tab(
            self, plan: TerminalPanePlan, *, profile: Profile | None = None,
            tab_title: str | None = None, tab_status: str | None = None,
        ) -> None: ...

    def build_profile_context_menu(
        self,
        item: QTreeWidgetItem | None = None,
    ) -> QMenu:
        if item is not None:
            self.profile_list.setCurrentItem(item)
        selected = item or self.profile_list.currentItem()
        profile_name = (
            selected.data(0, Qt.ItemDataRole.UserRole)
            if selected is not None
            else None
        )
        has_profile = isinstance(profile_name, str) and bool(profile_name)
        menu = QMenu(self.profile_list)
        menu.setObjectName("profileTreeContextMenu")
        connect_action = _required_gui_value(
            menu.addAction(
                "Connect",
                lambda: self.connect_selected(False),
            ),
            "profile context connect action",
        )
        dry_run_action = _required_gui_value(
            menu.addAction(
                "Preview command",
                lambda: self.connect_selected(True),
            ),
            "profile context preview action",
        )
        files_action = _required_gui_value(
            menu.addAction(
                "Open files / SFTP",
                self.open_files_selected,
            ),
            "profile context files action",
        )
        for action in (connect_action, dry_run_action, files_action):
            action.setEnabled(has_profile)
        menu.addSeparator()
        edit_action = _required_gui_value(
            menu.addAction("Edit profile", self.edit_selected_profile),
            "profile context edit action",
        )
        remove_action = _required_gui_value(
            menu.addAction("Remove profile", self.remove_selected_profile),
            "profile context remove action",
        )
        edit_action.setEnabled(has_profile)
        remove_action.setEnabled(has_profile)
        menu.addSeparator()
        menu.addAction("New profile", self.create_profile)
        menu.addAction("Refresh profiles", self.refresh_profiles)
        return menu

    def show_profile_context_menu(self, position: QPoint) -> None:
        item = self.profile_list.itemAt(position)
        if item is not None:
            self.profile_list.setCurrentItem(item)
        menu = self.build_profile_context_menu(item)
        viewport = _required_gui_value(
            self.profile_list.viewport(),
            "profile list viewport",
        )
        menu.exec(viewport.mapToGlobal(position))
        menu.deleteLater()

    def activate_profile_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        profile_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not profile_name:
            return
        self.profile_list.setCurrentItem(item)
        self.connect_selected(False)

    def update_profile_action_states(self) -> None:
        has_profile = bool(self.selected_profile_name())
        for key in ("edit", "remove", "connect", "files", "queue", "dry-run"):
            button = self.product_toolbar_button_by_key[key]
            self.set_toolbar_widget_enabled(button, has_profile)
            current_state = str(button.property("interactionState") or "normal")
            if not has_profile:
                self.set_interaction_state(button, "disabled")
            elif current_state == "disabled":
                design_state = gui_design_interaction_state(self.current_design_id())
                self.set_interaction_state(
                    button,
                    self.toolbar_interaction_state(key, design_state),
                )

    def create_profile(self) -> None:
        dialog = self.create_profile_dialog()
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                profile = dialog.profile()
                self.store.add(profile, surface="profile-editor")
            except (OSError, ValueError) as exc:
                dialog.show_validation_error(str(exc))
                continue
            self.refresh_profiles()
            self.select_profile(profile.name)
            self.log.append(f"PROFILE SAVED: {profile.name}")
            return

    def import_profiles_with_preview(self) -> None:
        source, _selected_filter = QFileDialog.getOpenFileName(
            cast("QWidget", self),
            "Preview profile import",
            "",
            "Profile exports (*.json *.xml *.ini *.conf *.mxtsessions);;All files (*)",
        )
        if not source:
            return
        try:
            result = import_profiles(Path(source), source_format="auto")
        except (OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Profile import failed",
                str(exc),
            )
            return
        if not result.profiles:
            self.show_message(
                QMessageBox.Icon.Information,
                "Profile import",
                "The import contains no supported profiles.",
            )
            return
        dialog = self.create_profile_import_preview_dialog(source, result)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                imported = self.store.add_many(
                    result.profiles,
                    skip_existing=True,
                    surface="profile-editor",
                )
            except (OSError, ValueError) as exc:
                self.show_message(QMessageBox.Icon.Warning, "Profile import failed", str(exc))
                continue
            imported_names = {profile.name for profile in imported}
            skipped = [
                f"{profile.name}: profile already exists"
                for profile in result.profiles if profile.name not in imported_names
            ]
            self.refresh_profiles()
            self.log.append(f"PROFILE IMPORTED: {len(imported)} from {result.source_format}")
            if skipped:
                self.show_message(
                    QMessageBox.Icon.Warning,
                    "Profile import",
                    "Some profiles were skipped:\n" + "\n".join(skipped),
                )
            return

    def edit_selected_profile(self) -> None:
        name = self.selected_profile_name()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "Select a profile first.",
            )
            return
        try:
            current = self.store.get(name, resolve=False)
        except (KeyError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Profile failed",
                str(exc),
            )
            return
        dialog = self.create_profile_dialog(current)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                profile = dialog.profile()
                self.save_profile(profile, original_name=name)
            except (KeyError, OSError, ValueError) as exc:
                dialog.show_validation_error(str(exc))
                continue
            self.refresh_profiles()
            self.select_profile(profile.name)
            self.log.append(f"PROFILE UPDATED: {profile.name}")
            return

    def remove_selected_profile(self) -> None:
        name = self.selected_profile_name()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "Select a profile first.",
            )
            return
        if not self.confirm_action("Remove profile", f"Remove profile {name}?"):
            return
        try:
            self.store.remove(name, surface="profile-editor")
            self.refresh_profiles()
            self.log.append(f"PROFILE REMOVED: {name}")
        except (KeyError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Profile failed",
                str(exc),
            )

    def save_profile(self, profile, original_name: str) -> None:
        replace_named = getattr(self.store, "replace_named", None)
        if callable(replace_named):
            replace_named(
                original_name,
                profile,
                surface="profile-editor",
            )
            return
        # Keep compatibility with lightweight editor stores used by
        # integrations while preserving the same duplicate/name checks as
        # ProfileStore.replace_named.
        profiles = list(self.store.load(resolve=False))
        if not any(item.name == original_name for item in profiles):
            raise KeyError(original_name)
        if profile.name != original_name and any(
            item.name == profile.name for item in profiles
        ):
            raise ValueError(f"profile already exists: {profile.name}")
        profiles = [item for item in profiles if item.name != original_name]
        profiles.append(profile)
        self.store.save(
            sorted(profiles, key=lambda item: (item.group, item.name)),
            surface="profile-editor",
        )

    def connect_selected(self, dry_run: bool) -> None:
        name = self.selected_profile_name()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "Select a profile first.",
            )
            return
        try:
            profile = self.store.get(name)
            self.launch_profile(profile, dry_run=dry_run, prefix="DRY RUN" if dry_run else "LAUNCHED")
        except (KeyError, LauncherError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Launch failed",
                str(exc),
            )

    def launch_profile(self, profile: Profile, *, dry_run: bool, prefix: str) -> None:
        assert_profile_launch_allowed(
            profile,
            surface="quick-connect" if profile.group == "quick-connect" else "launcher",
        )
        plan = build_launch_plan(profile)
        if dry_run:
            self.log.append(f"{prefix}: {plan.printable()}")
            for note in plan.notes:
                self.log.append(f"  note: {note}")
            return
        pane_plan = terminal_plan_for_profile(profile)
        tab_title = self.profile_tab_label(profile)
        tab_status = self.profile_tab_status()
        if self.moba_connected_profile_supported(profile):
            self.open_moba_connected_session_tab(
                profile,
                pane_plan,
                remote_path=self.moba_connected_remote_path_for_profile(profile),
                tab_title=tab_title,
                tab_status=tab_status,
            )
        else:
            self.open_terminal_tab(
                pane_plan,
                profile=profile,
                tab_title=tab_title,
                tab_status=tab_status,
            )
        self.log.append(f"{prefix}: {pane_plan.printable()}")

    def open_files_selected(self) -> None:
        name = self.selected_profile_name()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "Select a profile first.",
            )
            return
        try:
            profile = self.store.get(name)
            assert_profile_launch_allowed(profile, surface="gui")
            if self.moba_connected_profile_supported(profile):
                pane_plan = terminal_plan_for_profile(profile)
                self.open_moba_connected_session_tab(
                    profile,
                    pane_plan,
                    remote_path=self.moba_connected_remote_path_for_profile(profile),
                    tab_title=self.profile_tab_label(profile),
                    tab_status=self.profile_tab_status(),
                )
            else:
                pane_plan = terminal_plan_for_sftp_browser(profile)
                self.open_terminal_tab(pane_plan, profile=profile)
            self.log.append(f"FILES: {pane_plan.printable()}")
        except (KeyError, LauncherError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "SFTP failed",
                str(exc),
            )

    def open_transfer_queue_selected(self) -> None:
        name = self.selected_profile_name()
        if not name:
            self.show_message(
                QMessageBox.Icon.Information,
                "Remote Ops Workspace",
                "Select a profile first.",
            )
            return
        try:
            profile = self.store.get(name)
            assert_profile_launch_allowed(profile, surface="gui")
            dialog = self.create_transfer_queue_dialog(profile)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            plan = dialog.queue_plan()
            self.log.append(f"QUEUE: {plan.printable()}")
            for command in plan.batch_commands:
                self.log.append(f"  {command}")
            for note in plan.notes:
                self.log.append(f"  note: {note}")
        except (KeyError, LauncherError, OSError, ValueError) as exc:
            self.show_message(
                QMessageBox.Icon.Warning,
                "Transfer queue failed",
                str(exc),
            )
