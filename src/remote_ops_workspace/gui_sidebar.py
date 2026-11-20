from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QPoint, QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .gui_designs import (
    get_gui_design_preset,
    gui_design_moba_connected_dock_frame,
    gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry_for,
    gui_design_moba_rail_items,
    gui_design_sidebar_copy,
)
from .gui_values import _required_gui_value
from .gui_workspace import MobaRailLabel

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QComboBox, QSplitter, QStatusBar, QTabWidget, QTextEdit, QTreeWidget

    from .gui_connected import ConnectedSftpDock
    from .gui_designs import GuiDesignPreset
    from .moba_connected import MobaConnectedSessionState
    from .models import Profile
    from .storage import ProfileStore


class WindowSidebar:
    """Build the desktop sidebar and route its navigation and resize actions."""

    if TYPE_CHECKING:
        design_select: QComboBox
        left_panel: QWidget
        left_panel_header: QFrame
        log: QTextEdit
        moba_connected_dock: ConnectedSftpDock | None
        moba_quick_connect_chrome: QFrame
        moba_rail: QWidget
        profile_list: QTreeWidget
        quick_connect_suggestions: QTreeWidget
        remmina_profile_list_chrome: QFrame
        root_splitter: QSplitter
        securecrt_session_manager_chrome: QWidget
        store: ProfileStore
        tabs: QTabWidget
        termius_hosts_chrome: QWidget
        _setting_root_splitter_sizes: bool
        _sidebar_width_by_design: dict[str, int]

        def apply_moba_titlebar_chrome(self, title: str) -> None: ...
        def build_mremoteng_property_grid_evidence(self) -> QFrame: ...
        def build_securecrt_session_manager_chrome(self) -> QFrame: ...
        def build_termius_hosts_chrome(self) -> QFrame: ...
        def clear_moba_quick_connect_connected_idle(self) -> None: ...
        @staticmethod
        def clear_deleted_tab_object_names(widget: QWidget) -> None: ...
        def create_profile(self) -> None: ...
        def current_design_id(self) -> str: ...
        def filter_profile_tree_names(self, allowed_names: set[str] | None) -> None: ...
        @staticmethod
        def moba_connected_state_in_widget(widget: QWidget | None) -> MobaConnectedSessionState | None: ...
        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon: ...
        def open_files_selected(self) -> None: ...
        def select_profile(self, name: str) -> None: ...
        def selected_profile_for_workflow(self) -> Profile | None: ...
        def show_moba_connected_dock(self, state: MobaConnectedSessionState) -> None: ...
        def show_moba_macros_status(self, *_args) -> None: ...
        def show_moba_tools_status(self, *_args) -> None: ...
        def show_transient_status_message(self, message: str, timeout_ms: int = 1800) -> None: ...
        def show_workflow_dialog(
            self,
            title: str,
            subtitle: str,
            rows: list[tuple[str, str, str]],
            detail: str,
            *,
            actions: Sequence[tuple[str, Callable[..., object]]] | None = None,
        ) -> None: ...
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def update_profile_tree_indentation(self, sidebar_width: int) -> None: ...

    @staticmethod
    def sidebar_minimum_width_for_design(preset_id: str) -> int:
        return 280 if preset_id == "mobaxterm" else 240

    def preferred_sidebar_width(self, default_width: int) -> int:
        preset_id = self.current_design_id()
        minimum = self.sidebar_minimum_width_for_design(preset_id)
        remembered = self._sidebar_width_by_design.get(preset_id)
        return max(minimum, int(remembered or default_width))

    def set_root_sidebar_width(
        self,
        width: int,
        *,
        collapsed: bool = False,
    ) -> None:
        """Resize the main dock without mistaking programmatic moves for drags."""

        preset_id = self.current_design_id()
        minimum = self.sidebar_minimum_width_for_design(preset_id)
        target = 0 if collapsed else max(minimum, int(width))
        self.left_panel.setMinimumWidth(0 if collapsed else minimum)
        sizes = self.root_splitter.sizes()
        total = sum(sizes) or max(cast(QWidget, self).width(), target + 620)
        self._setting_root_splitter_sizes = True
        try:
            self.root_splitter.setSizes([target, max(1, total - target)])
        finally:
            self._setting_root_splitter_sizes = False
        self.root_splitter.setProperty("userResizableSidebar", True)
        self.root_splitter.setProperty("sidebarHandleWidth", self.root_splitter.handleWidth())
        self.update_profile_tree_indentation(target)

    def remember_user_sidebar_width(self, _position: int, handle_index: int) -> None:
        if self._setting_root_splitter_sizes or handle_index != 1:
            return
        sizes = self.root_splitter.sizes()
        if not sizes or not self.left_panel.isVisible():
            return
        preset_id = self.current_design_id()
        minimum = self.sidebar_minimum_width_for_design(preset_id)
        width = int(sizes[0])
        if width < minimum:
            return
        self._sidebar_width_by_design[preset_id] = width
        self.root_splitter.setProperty("rememberedSidebarWidth", width)
        self.update_profile_tree_indentation(width)

    def create_moba_rail(self) -> QWidget:
        frame = gui_design_moba_connected_dock_frame()
        rail_chrome = gui_design_moba_rail_chrome()
        rail = QWidget()
        rail.setObjectName("mobaRail")
        rail.setProperty("mobaConnectedDockRailWidth", frame.rail_width)
        rail.setProperty("mobaRailStaticWidth", rail_chrome.rail_width)
        rail.setProperty("mobaRailIconX", rail_chrome.icon_x)
        rail.setProperty("mobaRailStaticIconSize", rail_chrome.static_icon_size)
        rail.setProperty("mobaRailLiveIconSize", rail_chrome.live_icon_size)
        rail.setProperty("mobaRailButtonHeight", rail_chrome.button_height)
        rail.setProperty("mobaRailLabelHeight", rail_chrome.label_height)
        rail.setProperty("mobaRailRenderSource", rail_chrome.render_source)
        rail.setFixedWidth(rail_chrome.rail_width)
        rail.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        rail.customContextMenuRequested.connect(
            lambda position, source=rail: self.show_moba_rail_context_menu(
                source,
                position,
            )
        )
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.moba_rail_buttons: list[QToolButton] = []
        slots = {
            "collapse": self.toggle_moba_session_panel,
            "sessions": self.show_moba_sessions_rail,
            "favorites": self.show_moba_favorites_rail,
            "tools": self.show_moba_tools_status,
            "macros": self.show_moba_macros_status,
            "sftp": self.show_moba_sftp_rail,
        }
        for item in gui_design_moba_rail_items():
            geometry = gui_design_moba_rail_item_geometry_for(item.role)
            button = QToolButton()
            button.setObjectName(item.object_name)
            button.setProperty("mobaRailRole", item.role)
            button.setProperty("mobaRailIconKey", item.icon_key)
            button.setProperty("mobaRailStaticIconKey", item.rail_icon_key)
            button.setProperty("mobaRailStaticIconX", rail_chrome.icon_x)
            button.setProperty("mobaRailStaticIconY", geometry.static_icon_y)
            button.setProperty("mobaRailStaticIconSize", rail_chrome.static_icon_size)
            button.setProperty("mobaRailLiveIconSize", rail_chrome.live_icon_size)
            button.setProperty("mobaRailButtonWidth", rail_chrome.button_width)
            button.setProperty("mobaRailButtonHeight", rail_chrome.button_height)
            button.setProperty("mobaRailActiveX", rail_chrome.active_x)
            button.setProperty("mobaRailActiveYOffset", rail_chrome.active_y_offset)
            button.setProperty("mobaRailActiveWidth", rail_chrome.active_width)
            button.setProperty("mobaRailActiveHeight", rail_chrome.active_height)
            button.setProperty("mobaRailRenderSource", rail_chrome.render_source)
            button.setIcon(self.moba_ribbon_icon(item.icon_key, item.color, size=rail_chrome.generated_icon_size))
            button.setIconSize(QSize(rail_chrome.live_icon_size, rail_chrome.live_icon_size))
            button.setFixedSize(rail_chrome.button_width, rail_chrome.button_height)
            button.setToolTip(item.tooltip)
            button.setCheckable(item.role != "collapse")
            button.setAutoRaise(False)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.clicked.connect(slots[item.role])
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda position, source=button: self.show_moba_rail_context_menu(
                    source,
                    position,
                )
            )
            layout.addWidget(button)
            self.moba_rail_buttons.append(button)
            if item.label:
                label = MobaRailLabel(item.label, item.role, button)
                label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                label.customContextMenuRequested.connect(
                    lambda position, source=label: self.show_moba_rail_context_menu(
                        source,
                        position,
                    )
                )
                layout.addWidget(label)
        self.set_moba_rail_active("sessions")
        layout.addStretch(1)
        return rail

    def build_moba_rail_context_menu(self) -> QMenu:
        menu = QMenu(cast(QWidget, self))
        menu.setObjectName("mobaRailContextMenu")
        menu.addAction("Sessions", self.show_moba_sessions_rail)
        menu.addAction("Favorites", self.show_moba_favorites_rail)
        menu.addSeparator()
        menu.addAction("Tools", self.show_moba_tools_status)
        menu.addAction("Macros", self.show_moba_macros_status)
        sftp_action = _required_gui_value(
            menu.addAction("SFTP browser", self.show_moba_sftp_rail),
            "Moba rail SFTP action",
        )
        sftp_action.setEnabled(self.moba_connected_dock is not None)
        menu.addSeparator()
        menu.addAction("Collapse or expand sessions", self.toggle_moba_session_panel)
        return menu

    def show_moba_rail_context_menu(self, source: QWidget, position: QPoint) -> None:
        menu = self.build_moba_rail_context_menu()
        menu.exec(source.mapToGlobal(position))
        menu.deleteLater()

    def create_left_panel_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("leftPanelHeader")
        left_panel_header_layout = QVBoxLayout(header)
        left_panel_header_layout.setContentsMargins(10, 8, 10, 8)
        left_panel_header_layout.setSpacing(3)
        self.left_panel_title = QLabel("Profiles")
        self.left_panel_title.setObjectName("leftPanelTitle")
        self.left_panel_subtitle = QLabel("Saved sessions and local layouts")
        self.left_panel_subtitle.setObjectName("leftPanelSubtitle")
        self.left_panel_subtitle.setWordWrap(True)
        left_panel_header_layout.addWidget(self.left_panel_title)
        left_panel_header_layout.addWidget(self.left_panel_subtitle)
        self.securecrt_session_manager_chrome = self.build_securecrt_session_manager_chrome()
        left_panel_header_layout.addWidget(self.securecrt_session_manager_chrome)
        self.termius_hosts_chrome = self.build_termius_hosts_chrome()
        left_panel_header_layout.addWidget(self.termius_hosts_chrome)
        return header

    def create_left_panel(self) -> QWidget:
        frame = gui_design_moba_connected_dock_frame()
        panel = QWidget()
        panel.setObjectName("leftPanel")
        panel.setProperty("mobaConnectedDockSideWidth", frame.side_width)
        panel.setProperty("mobaConnectedDockRailWidth", frame.rail_width)
        panel.setProperty("mobaConnectedDockWidth", frame.dock_width)
        panel.setMinimumWidth(240)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.moba_quick_connect_chrome)
        layout.addWidget(self.quick_connect_suggestions)
        layout.addWidget(self.left_panel_header)
        layout.addWidget(self.remmina_profile_list_chrome)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self.moba_rail)
        self.moba_left_stack = QStackedWidget()
        self.moba_left_stack.setObjectName("mobaLeftStack")
        self.moba_left_stack.setProperty("mobaConnectedDockX", frame.dock_x)
        self.moba_left_stack.setProperty("mobaConnectedDockWidth", frame.dock_width)
        self.moba_left_stack.addWidget(self.profile_list)
        body_layout.addWidget(self.moba_left_stack, 1)
        layout.addWidget(body, 1)
        # mRemoteNG keeps a compact Config/property inspector docked
        # beneath the Connections tree while a document is active.  Keep
        # the real routed grid in the left chrome (rather than rendering
        # it only on the welcome surface) so the connected layout follows
        # the product's actual split-pane workflow.  It is hidden for
        # other presets by ``apply_selected_design``.
        self.mremoteng_left_property_grid_panel = (
            self.build_mremoteng_property_grid_evidence()
        )
        self.mremoteng_left_property_grid_panel.setProperty(
            "mRemoteNgLeftDockView",
            True,
        )
        self.mremoteng_left_property_grid_panel.setMaximumHeight(176)
        self.mremoteng_left_property_grid_panel.setVisible(False)
        layout.addWidget(self.mremoteng_left_property_grid_panel, 0)
        return panel

    def show_moba_profile_tree(self, *, preserve_connected_dock: bool = False) -> None:
        if not hasattr(self, "moba_left_stack"):
            return
        if self.moba_connected_dock is not None and not preserve_connected_dock:
            dock = self.moba_connected_dock
            self.moba_connected_dock = None
            if hasattr(dock, "shutdown_runtime"):
                dock.shutdown_runtime()
            self.moba_left_stack.removeWidget(dock)
            dock.setMinimumSize(0, 0)
            self.clear_deleted_tab_object_names(dock)
            dock.deleteLater()
        self.moba_left_stack.setCurrentWidget(self.profile_list)
        self.clear_moba_quick_connect_connected_idle()
        self.set_moba_rail_active("sessions")
        cast(QWidget, self).setWindowTitle("Remote Ops Workspace")
        self.apply_moba_titlebar_chrome("Remote Ops Workspace")

    def configure_left_panel_header_for_design(self, preset: GuiDesignPreset, is_moba: bool) -> None:
        title, subtitle = gui_design_sidebar_copy(preset.id)
        self.left_panel_title.setText(title)
        self.left_panel_subtitle.setText(subtitle)
        self.left_panel_header.setVisible(not is_moba)
        self.securecrt_session_manager_chrome.setVisible(preset.id == "securecrt")
        self.termius_hosts_chrome.setVisible(preset.id == "termius")

    def set_moba_rail_active(self, active: str) -> None:
        for button in getattr(self, "moba_rail_buttons", []):
            button.setChecked(button.property("mobaRailRole") == active)

    def toggle_moba_session_panel(self, *_args) -> None:
        sizes = self.root_splitter.sizes()
        if sizes and sizes[0] > 80:
            self.set_root_sidebar_width(0, collapsed=True)
            self.statusBar().showMessage("Sessions panel collapsed")
            return
        preset_id = self.design_select.currentData() or "native"
        try:
            preset = get_gui_design_preset(str(preset_id))
            width = preset.profile_width
        except ValueError:
            width = 395
        self.set_root_sidebar_width(self.preferred_sidebar_width(width))
        self.statusBar().showMessage("Sessions panel restored")

    def show_moba_sessions_rail(self, *_args) -> None:
        self.show_moba_profile_tree(preserve_connected_dock=True)
        self.filter_profile_tree_names(None)
        self.profile_list.expandAll()
        self.profile_list.setFocus()
        self.statusBar().showMessage("Sessions tree ready")

    def show_moba_favorites_rail(self, *_args) -> None:
        self.show_moba_profile_tree(preserve_connected_dock=True)
        self.set_moba_rail_active("favorites")
        favorites = [
            profile.name
            for profile in self.store.load()
            if any(tag.lower() in {"favorite", "favorites", "starred"} for tag in profile.tags)
        ]
        self.filter_profile_tree_names(set(favorites))
        if favorites:
            self.select_profile(favorites[0])
            message = f"Favorites: {len(favorites)} tagged session(s)"
        else:
            message = "Favorites: add a favorite/starred tag to a profile to surface it here."
        self.statusBar().showMessage(message)
        self.log.append(message)

    def show_moba_sftp_rail(self, *_args) -> None:
        self.set_moba_rail_active("sftp")
        if getattr(self, "moba_connected_dock", None) is None:
            state = self.moba_connected_state_in_widget(self.tabs.currentWidget())
            if state is not None:
                self.show_moba_connected_dock(state)
        dock = getattr(self, "moba_connected_dock", None)
        if dock is not None:
            self.moba_left_stack.setCurrentWidget(dock)
            self.statusBar().showMessage("Connected SFTP browser dock ready")
            return
        profile = self.selected_profile_for_workflow()
        if profile is not None and profile.protocol.lower() in {"ssh", "sftp"}:
            self.open_files_selected()
            return
        self.statusBar().showMessage("SFTP rail: select or open an SSH/SFTP profile")
        self.show_workflow_dialog(
            "SFTP browser",
            "Browse files through a selected SSH or SFTP profile.",
            [
                (
                    "Connected session",
                    "not selected",
                    "Open an SSH session to attach its synchronized browser dock.",
                ),
                (
                    "Saved profile",
                    profile.name if profile is not None else "none selected",
                    "Select an SSH/SFTP profile in Sessions, then choose SFTP.",
                ),
            ],
            "The SFTP rail no longer routes to unrelated package controls.",
            actions=[
                ("Sessions", self.show_moba_sessions_rail),
                ("New profile", self.create_profile),
            ],
        )

    def open_moba_sftp_same_parameters(self, index: int | None = None) -> None:
        tab_index = self.tabs.currentIndex() if index is None else index
        widget = self.tabs.widget(tab_index) if tab_index >= 0 else None
        state = self.moba_connected_state_in_widget(widget)
        if state is None:
            self.show_moba_sftp_rail()
            return
        self.show_moba_connected_dock(state)
        self.show_moba_sftp_rail()
        self.show_transient_status_message(
            f"SFTP attached to {state.target} at {state.remote_path}"
        )
