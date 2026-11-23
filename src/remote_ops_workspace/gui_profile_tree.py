from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSignalBlocker, QSize, Qt
from PyQt6.QtWidgets import QFrame, QLineEdit, QMessageBox, QTreeWidgetItem

from .gui_designs import (
    gui_design_moba_session_tree_chrome,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_filter_route,
    gui_design_saved_tree_row_icon,
    gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_sftp_tab_route,
    gui_design_termius_host_selection_route,
    gui_design_tree_root_copy,
    gui_design_tree_root_icon,
    gui_design_tree_row_icon,
)
from .gui_icons import draw_profile_tree_generated_icon
from .gui_values import _safe_tooltip_html, _widget_style
from .models import Profile

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from PyQt6.QtGui import QIcon, QPainter
    from PyQt6.QtWidgets import QMainWindow, QSplitter, QStyle, QTabWidget, QTreeWidget, QWidget

    from .gui_designs import (
        GuiDesignTreeRowIcon,
        GuiMRemoteNgConnectionDocumentRoute,
        GuiMRemoteNgDocumentFilterRoute,
        GuiSecureCrtSessionManagerFilterRoute,
        GuiSecureCrtSessionManagerRoute,
        GuiSecureCrtSftpTabRoute,
        GuiTermiusHostSelectionRoute,
    )
    from .storage import ProfileStore


TREE_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 31
TREE_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 32
TREE_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 33
TREE_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 34
TREE_ROW_STATIC_HEIGHT_ROLE = int(Qt.ItemDataRole.UserRole) + 35
TREE_ROW_STATIC_ICON_X_ROLE = int(Qt.ItemDataRole.UserRole) + 36
TREE_ROW_STATIC_LABEL_X_ROLE = int(Qt.ItemDataRole.UserRole) + 37
TREE_ROW_STATIC_TARGET_X_ROLE = int(Qt.ItemDataRole.UserRole) + 38
TREE_SEARCH_TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 39
TREE_CONNECT_ENDPOINT_ROLE = int(Qt.ItemDataRole.UserRole) + 40
MREMOTENG_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 61
MREMOTENG_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 62
MREMOTENG_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 63
MREMOTENG_ROUTE_TAB_ROLE = int(Qt.ItemDataRole.UserRole) + 64
MREMOTENG_ROUTE_PROTOCOL_ROLE = int(Qt.ItemDataRole.UserRole) + 65
MREMOTENG_ROUTE_STATE_ROLE = int(Qt.ItemDataRole.UserRole) + 66
MREMOTENG_ROUTE_SELECTED_ROLE = int(Qt.ItemDataRole.UserRole) + 67
MREMOTENG_CONFIG_ROLE = int(Qt.ItemDataRole.UserRole) + 68
MREMOTENG_FILTER_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 91
MREMOTENG_FILTER_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 92
MREMOTENG_FILTER_ROUTE_QUERY_ROLE = int(Qt.ItemDataRole.UserRole) + 93
MREMOTENG_FILTER_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 94
MREMOTENG_FILTER_ROUTE_LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 95
MREMOTENG_FILTER_ROUTE_MATCHED_ROLE = int(Qt.ItemDataRole.UserRole) + 96
MREMOTENG_FILTER_ROUTE_RENDER_SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 97
SECURECRT_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 71
SECURECRT_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 72
SECURECRT_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 73
SECURECRT_ROUTE_TAB_ROLE = int(Qt.ItemDataRole.UserRole) + 74
SECURECRT_ROUTE_TARGET_ROLE = int(Qt.ItemDataRole.UserRole) + 75
SECURECRT_ROUTE_PROTOCOL_ROLE = int(Qt.ItemDataRole.UserRole) + 76
SECURECRT_ROUTE_SELECTED_ROLE = int(Qt.ItemDataRole.UserRole) + 77
SECURECRT_FILTER_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 81
SECURECRT_FILTER_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 82
SECURECRT_FILTER_ROUTE_QUERY_ROLE = int(Qt.ItemDataRole.UserRole) + 83
SECURECRT_FILTER_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 84
SECURECRT_FILTER_ROUTE_LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 85
SECURECRT_FILTER_ROUTE_MATCHED_ROLE = int(Qt.ItemDataRole.UserRole) + 86
SECURECRT_FILTER_ROUTE_RENDER_SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 87
SECURECRT_SFTP_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 101
SECURECRT_SFTP_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 102
SECURECRT_SFTP_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 103
SECURECRT_SFTP_ROUTE_TREE_LABEL_ROLE = int(Qt.ItemDataRole.UserRole) + 104
SECURECRT_SFTP_ROUTE_TAB_ROLE = int(Qt.ItemDataRole.UserRole) + 105
SECURECRT_SFTP_ROUTE_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 106
SECURECRT_SFTP_ROUTE_TRANSFER_ROLE = int(Qt.ItemDataRole.UserRole) + 107
TERMIUS_HOST_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 81
TERMIUS_HOST_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 82
TERMIUS_HOST_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 83
TERMIUS_HOST_ROUTE_TAB_ROLE = int(Qt.ItemDataRole.UserRole) + 84
TERMIUS_HOST_ROUTE_TARGET_ROLE = int(Qt.ItemDataRole.UserRole) + 85
TERMIUS_HOST_ROUTE_PROTOCOL_ROLE = int(Qt.ItemDataRole.UserRole) + 86
TERMIUS_HOST_ROUTE_SELECTED_ROLE = int(Qt.ItemDataRole.UserRole) + 87
GENERATED_PROFILE_TREE_ICON_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}


@dataclass
class _RemminaSearchTree:
    groups: list[tuple[QTreeWidgetItem, bool]]
    rows: list[tuple[QTreeWidgetItem, QTreeWidgetItem, int]]
    selection: QTreeWidgetItem | None

    @staticmethod
    def selection_key(item: QTreeWidgetItem) -> tuple[bool, str]:
        name = item.data(0, Qt.ItemDataRole.UserRole)
        return (True, name) if name is not None else (False, item.toolTip(0))


class ProfileTree:
    """Project saved profiles into the Qt tree and maintain its selection."""

    _remmina_search: _RemminaSearchTree | None = None

    if TYPE_CHECKING:
        _profile_icons: dict[tuple[str, bool, int, float], QIcon]
        _saved_profile_names: set[str]
        profile_list: QTreeWidget
        remmina_profile_list_chrome: QFrame
        remmina_profile_filter: QLineEdit
        root_splitter: QSplitter
        store: ProfileStore
        tabs: QTabWidget

        def current_design_id(self) -> str: ...
        def current_design_is_moba(self) -> bool: ...
        def generated_icon(
            self, size: int, draw: Callable[[QPainter, int], None], *, antialias: bool = True,
        ) -> QIcon: ...
        def standard_icon(self, icon_name: str) -> QStyle.StandardPixmap: ...
        def refresh_layouts(self) -> None: ...
        def refresh_recent_session_buttons(self) -> None: ...
        def refresh_live_status_segments(self) -> bool: ...
        def show_message(self, icon: QMessageBox.Icon, title: object, message: object) -> QMessageBox.StandardButton: ...
        def update_layout_action_states(self, *_args) -> None: ...
        def update_profile_action_states(self) -> None: ...
        @staticmethod
        def apply_mremoteng_reconnect_route_properties(
            widget: QWidget, route: GuiMRemoteNgConnectionDocumentRoute, *,
            triggered: bool = False, reconnect_state: str | None = None,
            profile_name: str | None = None,
        ) -> None: ...

    def refresh_profiles(self) -> None:
        selected_name = self.selected_profile_name()
        try:
            profiles = sorted(self.store.load(), key=lambda item: (item.group, item.name))
        except (OSError, ValueError) as exc:
            self.show_message(QMessageBox.Icon.Warning, "Profile refresh failed", str(exc))
            return
        previous_search = self._remmina_search
        collapsed = (
            {group.toolTip(0) for group, expanded in previous_search.groups if not expanded}
            if previous_search else set()
        )
        selection_key = (
            previous_search.selection_key(previous_search.selection)
            if previous_search and previous_search.selection is not None else None
        )
        self._remmina_search = None
        self.profile_list.clear()
        preview = bool(cast("QWidget", self).property("guiPreviewSamples"))
        self._saved_profile_names = {profile.name for profile in profiles}
        self.refresh_recent_session_buttons()
        self.refresh_live_status_segments()
        mremoteng_route = (
            gui_design_mremoteng_connection_document_route()
            if self.current_design_id() == "mremoteng"
            else None
        )
        mremoteng_filter_route = (
            gui_design_mremoteng_document_filter_route()
            if self.current_design_id() == "mremoteng"
            else None
        )
        securecrt_route = (
            gui_design_securecrt_session_manager_route()
            if self.current_design_id() == "securecrt"
            else None
        )
        securecrt_filter_route = (
            gui_design_securecrt_session_manager_filter_route()
            if self.current_design_id() == "securecrt"
            else None
        )
        securecrt_sftp_route = (
            gui_design_securecrt_sftp_tab_route()
            if self.current_design_id() == "securecrt"
            else None
        )
        termius_host_route = (
            gui_design_termius_host_selection_route()
            if self.current_design_id() == "termius"
            else None
        )
        self._apply_mremoteng_tree_routes(mremoteng_route, mremoteng_filter_route)
        self._apply_securecrt_tree_routes(securecrt_route, securecrt_filter_route, securecrt_sftp_route)
        self._apply_termius_tree_route(termius_host_route)
        platform_icons: dict[tuple[str, str], QIcon] = {}
        root = cast(QTreeWidgetItem, self.profile_list.invisibleRootItem())
        if self.current_design_id() != "remmina" or preview:
            root_label, root_tooltip = gui_design_tree_root_copy(self.current_design_id())
            root = QTreeWidgetItem([root_label])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            self.apply_profile_tree_icon(root, gui_design_tree_root_icon(self.current_design_id()), platform_icons)
            self.apply_moba_profile_tree_geometry(root, "root")
            root.setToolTip(0, _safe_tooltip_html(root_tooltip))
            self.profile_list.addTopLevelItem(root)
        group_nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
        for profile in profiles:
            parent = root
            path: list[str] = []
            group_parts = self.profile_group_parts(profile, preview=preview)
            for part in group_parts:
                path.append(part)
                key = tuple(path)
                if key not in group_nodes:
                    group_item = QTreeWidgetItem([self.profile_group_label(part, preview=preview)])
                    group_item.setData(0, Qt.ItemDataRole.UserRole, None)
                    group_icon = (
                        gui_design_tree_row_icon(self.current_design_id(), part, "", True)
                        if preview else gui_design_saved_tree_row_icon(self.current_design_id(), part)
                    )
                    self.apply_profile_tree_icon(group_item, group_icon, platform_icons)
                    self.apply_moba_profile_tree_geometry(group_item, "group")
                    group_item.setToolTip(0, _safe_tooltip_html(self.profile_group_tooltip(path)))
                    parent.addChild(group_item)
                    group_nodes[key] = group_item
                parent = group_nodes[key]
            label = self.profile_tree_label(profile, preview=preview)
            tooltip = self.profile_tree_tooltip(profile)
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, profile.name)
            item.setData(0, TREE_CONNECT_ENDPOINT_ROLE, (profile.protocol, profile.host or "", profile.display_target))
            search_text = " ".join((
                label, profile.protocol, profile.display_target, profile.group, "/".join(group_parts),
                profile.description, *profile.tags,
            ))
            item.setData(0, TREE_SEARCH_TEXT_ROLE, search_text.casefold())
            profile_icon = (
                gui_design_tree_row_icon(self.current_design_id(), label, tooltip, False)
                if preview else gui_design_saved_tree_row_icon(self.current_design_id(), label, profile.protocol)
            )
            self.apply_profile_tree_icon(item, profile_icon, platform_icons, protocol=profile.protocol)
            self.apply_moba_profile_tree_geometry(item, "profile")
            if mremoteng_route is not None:
                item.setData(0, MREMOTENG_CONFIG_ROLE, [
                    profile.name, profile.protocol.upper(), profile.host or "", str(profile.port or ""),
                    profile.username or "", profile.group,
                ])
                routed = preview and profile.name == mremoteng_route.selected_profile_name
                item.setData(0, MREMOTENG_ROUTE_KEY_ROLE, mremoteng_route.key)
                item.setData(0, MREMOTENG_ROUTE_ROLE_ROLE, mremoteng_route.route_role)
                item.setData(0, MREMOTENG_ROUTE_PROFILE_ROLE, mremoteng_route.selected_profile_name)
                item.setData(0, MREMOTENG_ROUTE_TAB_ROLE, mremoteng_route.active_tab_label)
                item.setData(0, MREMOTENG_ROUTE_PROTOCOL_ROLE, mremoteng_route.protocol)
                item.setData(0, MREMOTENG_ROUTE_STATE_ROLE, mremoteng_route.workspace_state)
                item.setData(0, MREMOTENG_ROUTE_SELECTED_ROLE, routed)
                if routed:
                    tooltip = f"{tooltip}\n{mremoteng_route.key}: {mremoteng_route.active_tab_label}"
                    item.setSelected(True)
                    self.profile_list.setCurrentItem(item)
            if mremoteng_filter_route is not None:
                filter_routed = preview and profile.name == mremoteng_filter_route.selected_profile_name
                item.setData(0, MREMOTENG_FILTER_ROUTE_KEY_ROLE, mremoteng_filter_route.key)
                item.setData(0, MREMOTENG_FILTER_ROUTE_ROLE_ROLE, mremoteng_filter_route.route_role)
                item.setData(0, MREMOTENG_FILTER_ROUTE_QUERY_ROLE, mremoteng_filter_route.expected_query)
                item.setData(0, MREMOTENG_FILTER_ROUTE_PROFILE_ROLE, mremoteng_filter_route.selected_profile_name)
                item.setData(0, MREMOTENG_FILTER_ROUTE_LABEL_ROLE, mremoteng_filter_route.selected_tree_label)
                item.setData(0, MREMOTENG_FILTER_ROUTE_MATCHED_ROLE, filter_routed)
                item.setData(0, MREMOTENG_FILTER_ROUTE_RENDER_SOURCE_ROLE, mremoteng_filter_route.render_source)
                if filter_routed:
                    tooltip = (
                        f"{tooltip}\n{mremoteng_filter_route.key}: "
                        f"{mremoteng_filter_route.expected_query} -> "
                        f"{mremoteng_filter_route.selected_tree_label}"
                    )
            if securecrt_route is not None:
                routed = preview and profile.name == securecrt_route.selected_profile_name
                item.setData(0, SECURECRT_ROUTE_KEY_ROLE, securecrt_route.key)
                item.setData(0, SECURECRT_ROUTE_ROLE_ROLE, securecrt_route.route_role)
                item.setData(0, SECURECRT_ROUTE_PROFILE_ROLE, securecrt_route.selected_profile_name)
                item.setData(0, SECURECRT_ROUTE_TAB_ROLE, securecrt_route.active_tab_label)
                item.setData(0, SECURECRT_ROUTE_TARGET_ROLE, securecrt_route.target_value)
                item.setData(0, SECURECRT_ROUTE_PROTOCOL_ROLE, securecrt_route.protocol_value)
                item.setData(0, SECURECRT_ROUTE_SELECTED_ROLE, routed)
                if routed:
                    tooltip = f"{tooltip}\n{securecrt_route.key}: {securecrt_route.active_tab_label}"
                    item.setSelected(True)
                    self.profile_list.setCurrentItem(item)
            if securecrt_filter_route is not None:
                filter_routed = preview and profile.name == securecrt_filter_route.selected_profile_name
                item.setData(0, SECURECRT_FILTER_ROUTE_KEY_ROLE, securecrt_filter_route.key)
                item.setData(0, SECURECRT_FILTER_ROUTE_ROLE_ROLE, securecrt_filter_route.route_role)
                item.setData(0, SECURECRT_FILTER_ROUTE_QUERY_ROLE, securecrt_filter_route.expected_query)
                item.setData(0, SECURECRT_FILTER_ROUTE_PROFILE_ROLE, securecrt_filter_route.selected_profile_name)
                item.setData(0, SECURECRT_FILTER_ROUTE_LABEL_ROLE, securecrt_filter_route.matched_result_label)
                item.setData(0, SECURECRT_FILTER_ROUTE_MATCHED_ROLE, filter_routed)
                item.setData(0, SECURECRT_FILTER_ROUTE_RENDER_SOURCE_ROLE, securecrt_filter_route.render_source)
                if filter_routed:
                    tooltip = (
                        f"{tooltip}\n{securecrt_filter_route.key}: "
                        f"{securecrt_filter_route.expected_query} -> {securecrt_filter_route.matched_result_label}"
                    )
            if securecrt_sftp_route is not None:
                sftp_routed = preview and profile.name == securecrt_sftp_route.selected_profile_name
                item.setData(0, SECURECRT_SFTP_ROUTE_KEY_ROLE, securecrt_sftp_route.key)
                item.setData(0, SECURECRT_SFTP_ROUTE_ROLE_ROLE, securecrt_sftp_route.route_role)
                item.setData(0, SECURECRT_SFTP_ROUTE_PROFILE_ROLE, securecrt_sftp_route.selected_profile_name)
                item.setData(0, SECURECRT_SFTP_ROUTE_TREE_LABEL_ROLE, securecrt_sftp_route.selected_tree_label)
                item.setData(0, SECURECRT_SFTP_ROUTE_TAB_ROLE, securecrt_sftp_route.sftp_tab_label)
                item.setData(0, SECURECRT_SFTP_ROUTE_STATUS_ROLE, securecrt_sftp_route.status_value)
                item.setData(0, SECURECRT_SFTP_ROUTE_TRANSFER_ROLE, securecrt_sftp_route.transfer_state)
                if sftp_routed:
                    tooltip = (
                        f"{tooltip}\n{securecrt_sftp_route.key}: "
                        f"{securecrt_sftp_route.sftp_tab_label} -> {securecrt_sftp_route.status_value}"
                    )
            if termius_host_route is not None:
                routed = preview and profile.name == termius_host_route.selected_profile_name
                item.setData(0, TERMIUS_HOST_ROUTE_KEY_ROLE, termius_host_route.key)
                item.setData(0, TERMIUS_HOST_ROUTE_ROLE_ROLE, termius_host_route.route_role)
                item.setData(0, TERMIUS_HOST_ROUTE_PROFILE_ROLE, termius_host_route.selected_profile_name)
                item.setData(0, TERMIUS_HOST_ROUTE_TAB_ROLE, termius_host_route.active_tab_label)
                item.setData(0, TERMIUS_HOST_ROUTE_TARGET_ROLE, termius_host_route.target_value)
                item.setData(0, TERMIUS_HOST_ROUTE_PROTOCOL_ROLE, termius_host_route.protocol_value)
                item.setData(0, TERMIUS_HOST_ROUTE_SELECTED_ROLE, routed)
                if routed:
                    tooltip = f"{tooltip}\n{termius_host_route.key}: {termius_host_route.active_tab_label}"
                    item.setSelected(True)
                    self.profile_list.setCurrentItem(item)
            item.setToolTip(0, _safe_tooltip_html(tooltip))
            parent.addChild(item)
        self.profile_list.expandAll()
        if collapsed:
            for folder in group_nodes.values():
                if folder.toolTip(0) in collapsed:
                    folder.setExpanded(False)
        if selected_name:
            self.select_profile(selected_name)
        design_id = self.current_design_id()
        window = cast("QMainWindow", self)
        if design_id == "native" and self.profile_list.property("nativeHomeFilterText"):
            self.filter_profile_tree(str(self.profile_list.property("nativeHomeFilterText")))
        if design_id == "remmina" and not window.property("guiPreviewSamples"):
            self.filter_profile_tree(self.remmina_profile_filter.text())
            if self._remmina_search and selection_key is not None:
                search = self._remmina_search
                search.selection = next(
                    (item for item in self.iter_profile_tree_items() if search.selection_key(item) == selection_key), None,
                )
        if design_id == "securecrt":
            session_filter = window.findChild(QLineEdit, "secureCrtSessionFilter")
            if session_filter is not None:
                self.filter_profile_tree(session_filter.text())
        if design_id == "mremoteng":
            document_filter = window.findChild(QLineEdit, "mRemoteNgDocumentFilter")
            if document_filter is not None:
                self.filter_profile_tree(document_filter.text())
        if design_id == "termius":
            host_search = window.findChild(QLineEdit, "termiusHostSearch")
            if host_search is not None:
                self.filter_profile_tree(host_search.text())
        self.refresh_layouts()
        self.update_profile_action_states()
        self.update_layout_action_states()

    def _apply_mremoteng_tree_routes(
        self,
        mremoteng_route: GuiMRemoteNgConnectionDocumentRoute | None,
        mremoteng_filter_route: GuiMRemoteNgDocumentFilterRoute | None,
    ) -> None:
        self.profile_list.setProperty("mRemoteNgConnectionRouteKey", mremoteng_route.key if mremoteng_route else "")
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteRole",
            mremoteng_route.route_role if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteSelectedProfile",
            mremoteng_route.selected_profile_name if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteSelectedTreeLabel",
            mremoteng_route.selected_tree_label if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteDocumentControlsObject",
            mremoteng_route.document_controls_object if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteDocumentControlKey",
            mremoteng_route.document_control_key if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteDocumentControlObject",
            mremoteng_route.document_control_object if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRoutePropertyGridObject",
            mremoteng_route.property_grid_object if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRoutePropertyRowKey",
            mremoteng_route.property_row_key if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRoutePropertyCellObject",
            mremoteng_route.property_cell_object if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteActiveTab",
            mremoteng_route.active_tab_label if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteProtocol",
            mremoteng_route.protocol if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteState",
            mremoteng_route.workspace_state if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRoutePropertyValue",
            mremoteng_route.property_value if mremoteng_route else "",
        )
        self.profile_list.setProperty(
            "mRemoteNgConnectionRouteRenderSource",
            mremoteng_route.render_source if mremoteng_route else "",
        )
        if mremoteng_route is not None:
            self.apply_mremoteng_reconnect_route_properties(self.profile_list, mremoteng_route)
        mremoteng_filter_props = {
            "mRemoteNgDocumentFilterRouteKey": mremoteng_filter_route.key if mremoteng_filter_route else "",
            "mRemoteNgDocumentFilterRouteRole": (
                mremoteng_filter_route.route_role if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteDocumentControlsObject": (
                mremoteng_filter_route.document_controls_object if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteFilterObject": (
                mremoteng_filter_route.filter_object if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteSelectedTreeObject": (
                mremoteng_filter_route.selected_tree_object if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteSelectedProfile": (
                mremoteng_filter_route.selected_profile_name if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteMatchedTreeLabel": (
                mremoteng_filter_route.selected_tree_label if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteMatchedProtocol": (
                mremoteng_filter_route.matched_protocol if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteMatchedState": (
                mremoteng_filter_route.matched_state if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteQuery": (
                mremoteng_filter_route.expected_query if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRoutePlaceholder": (
                mremoteng_filter_route.expected_placeholder if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteActiveTab": (
                mremoteng_filter_route.active_tab_label if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteSignal": (
                mremoteng_filter_route.change_signal if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteHandler": (
                mremoteng_filter_route.handler_name if mremoteng_filter_route else ""
            ),
            "mRemoteNgDocumentFilterRouteRenderSource": (
                mremoteng_filter_route.render_source if mremoteng_filter_route else ""
            ),
        }
        for property_name, property_value in mremoteng_filter_props.items():
            self.profile_list.setProperty(property_name, property_value)

    def _apply_securecrt_tree_routes(
        self,
        securecrt_route: GuiSecureCrtSessionManagerRoute | None,
        securecrt_filter_route: GuiSecureCrtSessionManagerFilterRoute | None,
        securecrt_sftp_route: GuiSecureCrtSftpTabRoute | None,
    ) -> None:
        self.profile_list.setProperty(
            "secureCrtSessionRouteKey",
            securecrt_route.key if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteRole",
            securecrt_route.route_role if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteSelectedProfile",
            securecrt_route.selected_profile_name if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteSelectedTreeLabel",
            securecrt_route.selected_tree_label if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteSessionManagerObject",
            securecrt_route.session_manager_object if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteActionKey",
            securecrt_route.session_manager_action_key if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteActionObject",
            securecrt_route.session_manager_action_object if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteStatusStripObject",
            securecrt_route.status_strip_object if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteStatusFieldKey",
            securecrt_route.status_field_key if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteStatusFieldObject",
            securecrt_route.status_field_object if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteActiveTab",
            securecrt_route.active_tab_label if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteTarget",
            securecrt_route.target_value if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteProtocol",
            securecrt_route.protocol_value if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteSession",
            securecrt_route.session_value if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteStatusValue",
            securecrt_route.target_value if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionRouteRenderSource",
            securecrt_route.render_source if securecrt_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteKey",
            securecrt_filter_route.key if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteRole",
            securecrt_filter_route.route_role if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteSessionManagerObject",
            securecrt_filter_route.session_manager_object if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteFilterObject",
            securecrt_filter_route.filter_object if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteSelectedTreeObject",
            securecrt_filter_route.selected_tree_object if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteSelectedProfile",
            securecrt_filter_route.selected_profile_name if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteSelectedTreeLabel",
            securecrt_filter_route.selected_tree_label if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteQuery",
            securecrt_filter_route.expected_query if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRoutePlaceholder",
            securecrt_filter_route.expected_placeholder if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteMatchedLabel",
            securecrt_filter_route.matched_result_label if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteSignal",
            securecrt_filter_route.change_signal if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteHandler",
            securecrt_filter_route.handler_name if securecrt_filter_route else "",
        )
        self.profile_list.setProperty(
            "secureCrtSessionFilterRouteRenderSource",
            securecrt_filter_route.render_source if securecrt_filter_route else "",
        )
        securecrt_sftp_route_props = {
            "secureCrtSftpTabRouteKey": securecrt_sftp_route.key if securecrt_sftp_route else "",
            "secureCrtSftpTabRouteRole": securecrt_sftp_route.route_role if securecrt_sftp_route else "",
            "secureCrtSftpTabRouteWorkflowKey": (
                securecrt_sftp_route.workflow_card_key if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteWorkflowCardObject": (
                securecrt_sftp_route.workflow_card_object if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteSessionManagerObject": (
                securecrt_sftp_route.session_manager_object if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteSelectedTreeObject": (
                securecrt_sftp_route.selected_tree_object if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteSelectedProfile": (
                securecrt_sftp_route.selected_profile_name if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteSelectedTreeLabel": (
                securecrt_sftp_route.selected_tree_label if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteActiveTab": (
                securecrt_sftp_route.active_tab_label if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteTabLabel": (
                securecrt_sftp_route.sftp_tab_label if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteStatusStripObject": (
                securecrt_sftp_route.status_strip_object if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteStatusFieldKey": (
                securecrt_sftp_route.status_field_key if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteStatusFieldObject": (
                securecrt_sftp_route.status_field_object if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteStatus": (
                securecrt_sftp_route.status_value if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteTransferState": (
                securecrt_sftp_route.transfer_state if securecrt_sftp_route else ""
            ),
            "secureCrtSftpTabRouteRenderSource": (
                securecrt_sftp_route.render_source if securecrt_sftp_route else ""
            ),
        }
        for property_name, property_value in securecrt_sftp_route_props.items():
            self.profile_list.setProperty(property_name, property_value)
        if securecrt_route is not None:
            self.tabs.setProperty("secureCrtSessionRouteKey", securecrt_route.key)
            self.tabs.setProperty("secureCrtSessionRouteRole", securecrt_route.route_role)
            self.tabs.setProperty("secureCrtSessionRouteSelectedProfile", securecrt_route.selected_profile_name)
            self.tabs.setProperty("secureCrtSessionRouteSelectedTreeLabel", securecrt_route.selected_tree_label)
            self.tabs.setProperty("secureCrtSessionRouteActiveTab", securecrt_route.active_tab_label)
            self.tabs.setProperty("secureCrtSessionRouteTarget", securecrt_route.target_value)
            self.tabs.setProperty("secureCrtSessionRouteProtocol", securecrt_route.protocol_value)
            self.tabs.setProperty("secureCrtSessionRouteSession", securecrt_route.session_value)
            self.tabs.setProperty("secureCrtSessionRouteRenderSource", securecrt_route.render_source)
        if securecrt_sftp_route is not None:
            for property_name, property_value in securecrt_sftp_route_props.items():
                self.tabs.setProperty(property_name, property_value)

    def _apply_termius_tree_route(self, termius_host_route: GuiTermiusHostSelectionRoute | None) -> None:
        self.profile_list.setProperty(
            "termiusHostRouteKey",
            termius_host_route.key if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteRole",
            termius_host_route.route_role if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteSelectedProfile",
            termius_host_route.selected_profile_name if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteSelectedTreeLabel",
            termius_host_route.selected_tree_label if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteHostsPanelObject",
            termius_host_route.hosts_panel_object if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteIdentityObject",
            termius_host_route.host_identity_object if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteIdentityFieldKey",
            termius_host_route.identity_field_key if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteIdentityCellObject",
            termius_host_route.identity_cell_object if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteActiveTab",
            termius_host_route.active_tab_label if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteTarget",
            termius_host_route.target_value if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteProtocol",
            termius_host_route.protocol_value if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteIdentityValue",
            termius_host_route.host_value if termius_host_route else "",
        )
        self.profile_list.setProperty(
            "termiusHostRouteRenderSource",
            termius_host_route.render_source if termius_host_route else "",
        )
        if termius_host_route is not None:
            self.tabs.setProperty("termiusHostRouteKey", termius_host_route.key)
            self.tabs.setProperty("termiusHostRouteRole", termius_host_route.route_role)
            self.tabs.setProperty("termiusHostRouteSelectedProfile", termius_host_route.selected_profile_name)
            self.tabs.setProperty("termiusHostRouteSelectedTreeLabel", termius_host_route.selected_tree_label)
            self.tabs.setProperty("termiusHostRouteActiveTab", termius_host_route.active_tab_label)
            self.tabs.setProperty("termiusHostRouteTarget", termius_host_route.target_value)
            self.tabs.setProperty("termiusHostRouteProtocol", termius_host_route.protocol_value)
            self.tabs.setProperty("termiusHostRouteIdentityValue", termius_host_route.host_value)
            self.tabs.setProperty("termiusHostRouteRenderSource", termius_host_route.render_source)

    def update_profile_tree_indentation(self, sidebar_width: int) -> None:
        if self.current_design_is_moba():
            indentation = gui_design_moba_session_tree_chrome().indentation
        elif sidebar_width <= 300:
            indentation = 11
        elif sidebar_width <= 380:
            indentation = 13
        else:
            indentation = 15
        self.profile_list.setIndentation(indentation)
        self.profile_list.setProperty("responsiveTreeIndentation", indentation)

    def profile_group_parts(self, profile_or_group: Profile | str, *, preview: bool = False) -> list[str]:
        if preview and isinstance(profile_or_group, Profile):
            design_id = self.current_design_id()
            protocol = profile_or_group.protocol.lower()
            if design_id == "securecrt":
                if profile_or_group.name == "jump-host":
                    return ["Pinned"]
                return ["Sessions"]
            if design_id == "termius":
                if profile_or_group.name == "prod-cluster" or profile_or_group.group.lower() == "teams":
                    return ["Teams"]
                return ["Personal"]
            if design_id == "remmina":
                if protocol == "rdp":
                    return ["RDP"]
                if protocol == "vnc":
                    return ["VNC"]
                if protocol in {"ssh", "sftp", "scp"}:
                    return ["SSH/SFTP"]
        group = profile_or_group.group if isinstance(profile_or_group, Profile) else profile_or_group
        parts = [part.strip() for part in group.replace("\\", "/").split("/") if part.strip()]
        return parts or ["default"]

    def profile_group_label(self, part: str, *, preview: bool) -> str:
        design_id = self.current_design_id()
        if design_id == "securecrt":
            return f"Folder: {part}"
        if design_id == "termius":
            return f"Vault / {part}"
        if design_id == "remmina" and preview:
            return f"Group: {part}"
        if design_id == "mremoteng" and preview:
            return f"Container: {part}"
        return part

    def profile_group_tooltip(self, path: list[str]) -> str:
        joined = "/".join(path)
        design_id = self.current_design_id()
        if design_id == "securecrt":
            return f"SecureCRT-style session folder: {joined}"
        if design_id == "termius":
            return f"Termius-style vault group: {joined}"
        if design_id == "remmina":
            return f"Remmina-style connection profile group: {joined}"
        if design_id == "mremoteng":
            return f"mRemoteNG-style nested container: {joined}"
        return f"Session folder: {joined}"

    def profile_tree_label(self, profile: Profile, *, preview: bool) -> str:
        design_id = self.current_design_id()
        if design_id == "mobaxterm":
            return profile.name
        protocol = profile.protocol.upper()
        target = profile.display_target
        if design_id == "securecrt":
            display_protocol = "SSH2" if protocol == "SSH" else protocol
            return f"{profile.name} ({display_protocol})"
        if design_id == "termius":
            return f"{profile.name}  {protocol.lower()} host"
        if design_id == "remmina":
            return f"{protocol} - {profile.name}" if preview else profile.name
        if design_id == "mremoteng":
            return f"{profile.name} [{protocol}]" if preview else profile.name
        return f"[{protocol}] {profile.name}  {target}" if target else f"[{protocol}] {profile.name}"

    def profile_tree_tooltip(self, profile: Profile) -> str:
        protocol = profile.protocol.upper()
        target = profile.display_target
        design_id = self.current_design_id()
        if design_id == "securecrt":
            return f"Session Manager entry\nProtocol: {protocol}\nTarget: {target}"
        if design_id == "termius":
            return f"Vault host\nProtocol: {protocol}\nTarget: {target}"
        if design_id == "remmina":
            return f"Connection profile\nProtocol: {protocol}\nTarget: {target}"
        if design_id == "mremoteng":
            return f"Connection tree node\nProtocol: {protocol}\nTarget: {target}"
        return f"{protocol}  {target}\nProfile: {profile.name}"

    def apply_profile_tree_icon(
        self, item: QTreeWidgetItem, row_icon: GuiDesignTreeRowIcon,
        platform_icons: dict[tuple[str, str], QIcon], *, protocol: str = "",
    ) -> None:
        item.setData(0, TREE_ICON_KEY_ROLE, row_icon.icon_key)
        item.setData(0, TREE_ROW_KIND_ROLE, row_icon.row_kind)
        item.setData(0, TREE_ICON_SIZE_ROLE, row_icon.static_size)
        if self.current_design_id() in GENERATED_PROFILE_TREE_ICON_PRESETS:
            item.setData(0, TREE_ICON_RENDER_ROLE, "generated-pixmap")
            item.setIcon(
                0,
                self.profile_tree_generated_icon(
                    row_icon.icon_key,
                    group=row_icon.row_kind in {"root", "group"},
                    size=row_icon.static_size,
                ),
            )
            return
        item.setData(0, TREE_ICON_RENDER_ROLE, "platform")
        key = (row_icon.row_kind, protocol)
        if key not in platform_icons:
            if row_icon.row_kind in {"root", "group"}:
                icon_name = "SP_DirHomeIcon" if row_icon.row_kind == "root" else "SP_DirIcon"
                icon = _widget_style(cast("QMainWindow", self)).standardIcon(self.standard_icon(icon_name))
            else:
                icon = self.profile_icon_for_protocol(protocol)
            platform_icons[key] = icon
        item.setIcon(0, platform_icons[key])

    def apply_moba_profile_tree_geometry(self, item: QTreeWidgetItem, row_kind: str) -> None:
        if self.current_design_id() != "mobaxterm":
            return
        chrome = gui_design_moba_session_tree_chrome()
        if row_kind == "root":
            row_height = chrome.root_row_height
            icon_x = chrome.header_icon_x
            label_x = chrome.header_text_x
            target_x = 0
        elif row_kind == "group":
            row_height = chrome.group_row_height
            icon_x = chrome.group_icon_x
            label_x = chrome.group_label_x
            target_x = 0
        else:
            row_height = chrome.profile_row_height
            icon_x = chrome.profile_icon_x
            label_x = chrome.profile_label_x
            target_x = chrome.profile_target_x
        item.setSizeHint(0, QSize(0, row_height))
        item.setData(0, TREE_ROW_STATIC_HEIGHT_ROLE, row_height)
        item.setData(0, TREE_ROW_STATIC_ICON_X_ROLE, icon_x)
        item.setData(0, TREE_ROW_STATIC_LABEL_X_ROLE, label_x)
        item.setData(0, TREE_ROW_STATIC_TARGET_X_ROLE, target_x)

    def profile_tree_generated_icon(self, icon_key: str, *, group: bool, size: int = 16) -> QIcon:
        key = (icon_key, group, size, cast("QWidget", self).devicePixelRatioF())
        if key not in self._profile_icons:
            self._profile_icons[key] = self.generated_icon(
                size,
                lambda painter, logical_size: draw_profile_tree_generated_icon(
                    painter, icon_key, group=group, size=logical_size
                ),
            )
        return self._profile_icons[key]

    def profile_icon_for_protocol(self, protocol: str) -> QIcon:
        normalized = protocol.lower()
        icon_name = "SP_FileDialogContentsView"
        if normalized in {"rdp", "vnc", "spice", "x2go", "ica"}:
            icon_name = "SP_ComputerIcon"
        elif normalized in {"sftp", "scp", "ftp"}:
            icon_name = "SP_DirIcon"
        elif normalized in {"http", "https"}:
            icon_name = "SP_DriveNetIcon"
        elif normalized in {"serial", "raw", "telnet", "rlogin", "rsh"}:
            icon_name = "SP_CommandLink"
        return _widget_style(cast("QMainWindow", self)).standardIcon(self.standard_icon(icon_name))

    def configure_profile_tree_for_design(self, is_moba: bool, list_spacing: int) -> None:
        moba_chrome = gui_design_moba_session_tree_chrome()
        sidebar_sizes = self.root_splitter.sizes()
        sidebar_width = sidebar_sizes[0] if sidebar_sizes else self.profile_list.width()
        self.update_profile_tree_indentation(sidebar_width)
        self.profile_list.setRootIsDecorated(moba_chrome.root_is_decorated if is_moba else True)
        self.profile_list.setAnimated(moba_chrome.animated if is_moba else False)
        self.profile_list.setAllColumnsShowFocus(True)
        self.profile_list.setItemsExpandable(True)
        self.profile_list.setExpandsOnDoubleClick(True)
        self.profile_list.setUniformRowHeights(moba_chrome.uniform_row_heights if is_moba else True)
        self.profile_list.setProperty("listSpacing", list_spacing)
        if is_moba:
            self.profile_list.setProperty("mobaSessionTreeHeaderHeight", moba_chrome.header_height)
            self.profile_list.setProperty("mobaSessionTreeHeaderIconX", moba_chrome.header_icon_x)
            self.profile_list.setProperty("mobaSessionTreeHeaderTextX", moba_chrome.header_text_x)
            self.profile_list.setProperty("mobaSessionTreeRowStartY", moba_chrome.row_start_y)
            self.profile_list.setProperty("mobaSessionTreeIndentation", moba_chrome.indentation)
            self.profile_list.setProperty("mobaSessionTreeRootRowHeight", moba_chrome.root_row_height)
            self.profile_list.setProperty("mobaSessionTreeGroupRowHeight", moba_chrome.group_row_height)
            self.profile_list.setProperty("mobaSessionTreeProfileRowHeight", moba_chrome.profile_row_height)
            self.profile_list.setProperty("mobaSessionTreeGroupIconX", moba_chrome.group_icon_x)
            self.profile_list.setProperty("mobaSessionTreeGroupLabelX", moba_chrome.group_label_x)
            self.profile_list.setProperty("mobaSessionTreeProfileIconX", moba_chrome.profile_icon_x)
            self.profile_list.setProperty("mobaSessionTreeProfileLabelX", moba_chrome.profile_label_x)
            self.profile_list.setProperty("mobaSessionTreeProfileTargetX", moba_chrome.profile_target_x)
            self.profile_list.setProperty("mobaSessionTreeSelectedLeft", moba_chrome.selected_left)
            self.profile_list.setProperty("mobaSessionTreeSelectedHeight", moba_chrome.selected_height)
            self.profile_list.setProperty("mobaSessionTreeRenderSource", moba_chrome.render_source)
        else:
            for property_name in (
                "mobaSessionTreeHeaderHeight",
                "mobaSessionTreeHeaderIconX",
                "mobaSessionTreeHeaderTextX",
                "mobaSessionTreeRowStartY",
                "mobaSessionTreeIndentation",
                "mobaSessionTreeRootRowHeight",
                "mobaSessionTreeGroupRowHeight",
                "mobaSessionTreeProfileRowHeight",
                "mobaSessionTreeGroupIconX",
                "mobaSessionTreeGroupLabelX",
                "mobaSessionTreeProfileIconX",
                "mobaSessionTreeProfileLabelX",
                "mobaSessionTreeProfileTargetX",
                "mobaSessionTreeSelectedLeft",
                "mobaSessionTreeSelectedHeight",
                "mobaSessionTreeRenderSource",
            ):
                self.profile_list.setProperty(property_name, None)

    def filter_profile_tree(self, text: str) -> None:
        needle = text.strip().casefold()
        if self.current_design_id() == "remmina" and not cast("QWidget", self).property("guiPreviewSamples"):
            self._filter_remmina_saved_profiles(needle)
            self.update_profile_action_states()
            return

        def apply_filter(item) -> bool:
            own_text = item.data(0, TREE_SEARCH_TEXT_ROLE) or item.text(0).casefold()
            child_match = False
            for child_index in range(item.childCount()):
                child_match = apply_filter(item.child(child_index)) or child_match
            item_match = not needle or needle in own_text or child_match
            item.setHidden(not item_match)
            if item_match and child_match:
                item.setExpanded(True)
            return item_match

        for index in range(self.profile_list.topLevelItemCount()):
            apply_filter(self.profile_list.topLevelItem(index))
        current = self.profile_list.currentItem()
        if current is not None and not self.profile_tree_item_is_visible(current):
            self.profile_list.setCurrentItem(None)
            self.profile_list.clearSelection()
        self.update_profile_action_states()

    def _filter_remmina_saved_profiles(self, needle: str) -> None:
        tree = self.profile_list
        state = self._remmina_search
        if not needle and state is None:
            return
        current = tree.currentItem()
        with QSignalBlocker(tree):
            if state is None:
                groups = []
                rows = []
                for item in self.iter_profile_tree_items():
                    if item.data(0, Qt.ItemDataRole.UserRole):
                        parent = cast(QTreeWidgetItem, item.parent())  # Every saved profile has a folder.
                        rows.append((item, parent, parent.indexOfChild(item)))
                    else:
                        groups.append((item, item.isExpanded()))
                self._remmina_search = state = _RemminaSearchTree(groups, rows, current)
                for group, _ in groups:
                    group.setHidden(True)
                for item, parent, _ in rows:
                    parent.removeChild(item)
                tree.addTopLevelItems(sorted((item for item, _, _ in rows), key=lambda item: item.text(0).casefold()))
                tree.setRootIsDecorated(False)
            if needle:
                for item, _, _ in state.rows:
                    item.setHidden(needle not in item.data(0, TREE_SEARCH_TEXT_ROLE))
                if current is not None and current.isHidden():
                    current = None
            else:
                # The flat rows follow the hidden top-level groups. Move the same items back in order.
                for _ in state.rows:
                    tree.takeTopLevelItem(tree.topLevelItemCount() - 1)
                for item, parent, index in state.rows:
                    parent.insertChild(index, item)
                    item.setHidden(False)
                for group, expanded in state.groups:
                    group.setHidden(False)
                    group.setExpanded(expanded)
                tree.setRootIsDecorated(True)
                current = current or state.selection
                self._remmina_search = None
            tree.setCurrentItem(current)

    def filter_profile_tree_names(self, allowed_names: set[str] | None) -> None:
        """Show all profile rows, or only an explicit Moba rail name set."""

        def apply_filter(item) -> bool:
            child_match = False
            for child_index in range(item.childCount()):
                child_match = apply_filter(item.child(child_index)) or child_match
            profile_name = item.data(0, Qt.ItemDataRole.UserRole)
            own_match = (
                allowed_names is None
                or (isinstance(profile_name, str) and profile_name in allowed_names)
            )
            item_match = own_match if isinstance(profile_name, str) else child_match
            item.setHidden(not item_match)
            if item_match and child_match:
                item.setExpanded(True)
            return item_match

        for index in range(self.profile_list.topLevelItemCount()):
            apply_filter(self.profile_list.topLevelItem(index))
        self.profile_list.setProperty(
            "mobaProfileTreeFilterMode",
            "all" if allowed_names is None else "favorites",
        )
        self.profile_list.setProperty(
            "mobaProfileTreeFilterNames",
            [] if allowed_names is None else sorted(allowed_names),
        )
        current = self.profile_list.currentItem()
        if current is not None and not self.profile_tree_item_is_visible(current):
            self.profile_list.setCurrentItem(None)
            self.profile_list.clearSelection()
        self.update_profile_action_states()

    def filter_remmina_profile_rows(self, text: str) -> None:
        if not hasattr(self, "remmina_profile_list_chrome"):
            return
        needle = text.strip().lower()
        rows = self.remmina_profile_list_chrome.findChildren(QFrame, "remminaProfileListRow")
        for row in rows:
            values = [
                str(row.property("remminaProfileRowKey") or ""),
                str(row.property("remminaProfileName") or ""),
                str(row.property("remminaProfileProtocol") or ""),
                str(row.property("remminaProfileServer") or ""),
                str(row.property("remminaProfileStatus") or ""),
            ]
            row.setVisible(not needle or any(needle in value.lower() for value in values))

    def selected_profile_name(self) -> str | None:
        item = self.profile_list.currentItem()
        if not item or not self.profile_tree_item_is_visible(item):
            return None
        return item.data(0, Qt.ItemDataRole.UserRole)

    @staticmethod
    def profile_tree_item_is_visible(item: QTreeWidgetItem) -> bool:
        current: QTreeWidgetItem | None = item
        while current is not None:
            if current.isHidden():
                return False
            current = current.parent()
        return True

    def select_profile(self, name: str) -> None:
        for item in self.iter_profile_tree_items():
            if (
                item.data(0, Qt.ItemDataRole.UserRole) == name
                and self.profile_tree_item_is_visible(item)
            ):
                self.profile_list.setCurrentItem(item)
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                return

    def select_profile_tree_label(self, label: str) -> bool:
        for item in self.iter_profile_tree_items():
            if label in item.text(0) and self.profile_tree_item_is_visible(item):
                self.profile_list.setCurrentItem(item)
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                return True
        return False

    def iter_profile_tree_items(self) -> Iterator[QTreeWidgetItem]:
        def walk(item):
            yield item
            for child_index in range(item.childCount()):
                yield from walk(item.child(child_index))

        for index in range(self.profile_list.topLevelItemCount()):
            yield from walk(self.profile_list.topLevelItem(index))
