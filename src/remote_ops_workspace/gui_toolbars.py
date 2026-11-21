from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from . import gui_preset_properties
from .gui_designs import (
    GUI_DESIGN_PRESETS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    GuiDesignPreset,
    gui_design_moba_ribbon_action_geometry,
    gui_design_moba_ribbon_action_geometry_for,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_ribbon_tooltips,
    gui_design_moba_top_stack_geometry,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_catalog_route,
    gui_design_remmina_sftp_transfer_route,
    gui_design_securecrt_top_chrome,
    gui_design_toolbar_actions,
)
from .gui_values import _required_gui_value, _widget_style

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon, QShortcut
    from PyQt6.QtWidgets import QStyle


class WindowToolbars:
    """Build the desktop action and layout toolbars and apply preset geometry."""

    if TYPE_CHECKING:
        securecrt_host_shortcut: QShortcut
        securecrt_keyword_shortcut: QShortcut

        def add_split(self, direction: str) -> None: ...
        @staticmethod
        def apply_remmina_sftp_transfer_action_route_properties(
            widget: QWidget, route, *, triggered: bool = False, action_key: str | None = None,
            status: str | None = None,
        ) -> None: ...
        def connect_selected(self, dry_run: bool) -> None: ...
        def create_layout(self) -> None: ...
        def create_profile(self) -> None: ...
        def current_design_id(self) -> str: ...
        def current_design_is_moba(self) -> bool: ...
        def cycle_design_preset(self, *_args) -> None: ...
        def edit_selected_layout(self) -> None: ...
        def edit_selected_profile(self) -> None: ...
        def import_profiles_with_preview(self) -> None: ...
        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon: ...
        def open_files_selected(self) -> None: ...
        def open_selected_layout(self) -> None: ...
        def open_transfer_queue_selected(self) -> None: ...
        def product_toolbar_icon(self, preset_id: str, icon_key: str, *, size: int = 16) -> QIcon: ...
        def refresh_profiles(self) -> None: ...
        def remove_selected_layout(self) -> None: ...
        def remove_selected_profile(self) -> None: ...
        def run_operator_action(self, callback: Callable[[], object]) -> None: ...
        def show_doctor(self) -> None: ...
        def show_moba_games_status(self, *_args) -> None: ...
        def show_moba_help_dialog(self, *_args) -> None: ...
        def show_moba_multiexec_status(self, *_args) -> None: ...
        def show_moba_packages_dialog(self, *_args) -> None: ...
        def show_moba_servers_status(self, *_args) -> None: ...
        def show_moba_settings_status(self, *_args) -> None: ...
        def show_moba_tools_status(self, *_args) -> None: ...
        def show_moba_tunneling_status(self, *_args) -> None: ...
        def show_moba_x_server_status(self, *_args) -> None: ...
        def standard_icon(self, icon_name: str) -> QStyle.StandardPixmap: ...

    def build_toolbars(self) -> None:
        window = cast(QMainWindow, self)
        self.main_toolbar = QToolBar("Main")
        self.main_toolbar.setObjectName("mainToolbar")
        self.main_toolbar.setMovable(False)
        window.addToolBar(self.main_toolbar)
        self.layout_toolbar = QToolBar("Layouts")
        self.layout_toolbar.setObjectName("layoutToolbar")
        self.layout_toolbar.setMovable(False)
        window.addToolBarBreak()
        window.addToolBar(self.layout_toolbar)
        self.toolbar_widget_actions: dict[int, QAction] = {}
        self.refresh_button = self.toolbar_button(
            "Refresh", "SP_BrowserReload", "Reload profiles"
        )
        self.new_profile_button = self.toolbar_button("New", "SP_FileIcon", "Create profile")
        self.import_profile_button = self.toolbar_button(
            "Import", "SP_DialogOpenButton", "Preview and import profiles"
        )
        self.edit_profile_button = self.toolbar_button(
            "Edit", "SP_FileDialogDetailedView", "Edit selected profile"
        )
        self.remove_profile_button = self.toolbar_button(
            "Remove", "SP_TrashIcon", "Remove selected profile"
        )
        self.remove_profile_button.setObjectName("dangerAction")
        self.connect_button = self.toolbar_button(
            "Connect", "SP_MediaPlay", "Open selected profile"
        )
        self.connect_button.setObjectName("primaryAction")
        self.files_button = self.toolbar_button("Files", "SP_DirIcon", "Open SFTP browser")
        self.queue_button = self.toolbar_button(
            "Queue", "SP_FileDialogListView", "Preview transfer queue"
        )
        self.dry_run_button = self.toolbar_button(
            "Dry Run", "SP_CommandLink", "Show launch command"
        )
        self.doctor_button = self.toolbar_button(
            "Doctor", "SP_MessageBoxInformation", "Run doctor checks"
        )
        self.split_h_button = self.toolbar_button(
            "Split H", "SP_TitleBarShadeButton", "Open horizontal split"
        )
        self.split_v_button = self.toolbar_button(
            "Split V", "SP_TitleBarUnshadeButton", "Open vertical split"
        )
        self.layout_select = QComboBox()
        self.layout_select.setObjectName("layoutSelect")
        self.layout_select.setMinimumWidth(150)
        self.layout_select.setMaximumWidth(190)
        self.design_select = QComboBox()
        self.design_select.setObjectName("designSelect")
        self.design_select.setMinimumWidth(150)
        self.design_select.setMaximumWidth(180)
        for persistent_widget in (self.layout_toolbar, self.design_select):
            persistent_widget.setProperty("styleSelectorPersistent", True)
            persistent_widget.setProperty("styleSelectorLocation", "layout-toolbar")
        for preset in GUI_DESIGN_PRESETS:
            self.design_select.addItem(preset.label, preset.id)
        gui_preset_properties.apply_preset_catalog_route_properties(
            self.design_select, gui_design_preset_catalog_route()
        )
        self.new_layout_button = self.toolbar_button("New", "SP_FileIcon", "Create layout")
        self.edit_layout_button = self.toolbar_button(
            "Edit", "SP_FileDialogDetailedView", "Edit selected layout"
        )
        self.remove_layout_button = self.toolbar_button(
            "Delete", "SP_TrashIcon", "Remove selected layout"
        )
        self.remove_layout_button.setObjectName("dangerAction")
        self.open_layout_button = self.toolbar_button(
            "Open", "SP_DialogOpenButton", "Open selected layout"
        )
        self.search_input = QLineEdit()
        self.search_input.setObjectName("toolbarSearch")
        self.search_input.setMinimumWidth(120)
        self.search_input.setMaximumWidth(180)
        self.search_input.setPlaceholderText("Search active terminal or log")
        self.find_button = self.toolbar_button(
            "Find",
            "SP_FileDialogContentsView",
            "Find in the active terminal, then the activity log",
        )
        self.moba_ribbon_buttons = self.build_moba_ribbon_buttons()
        for button in self.moba_ribbon_buttons:
            self.add_toolbar_widget(self.main_toolbar, button)
        self.moba_toolbar_spacer = QWidget()
        self.moba_toolbar_spacer.setObjectName("mobaToolbarSpacer")
        self.moba_toolbar_spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self.add_toolbar_widget(self.main_toolbar, self.moba_toolbar_spacer)
        moba_edge_route = gui_design_moba_ribbon_edge_action_route()
        edge_action_keys = [moba_edge_route.xserver_action_key, moba_edge_route.exit_action_key]
        for edge_widget in (self.main_toolbar, self.moba_toolbar_spacer):
            edge_widget.setProperty("mobaRibbonEdgeRouteKey", moba_edge_route.key)
            edge_widget.setProperty("mobaRibbonEdgeRouteRole", moba_edge_route.route_role)
            edge_widget.setProperty(
                "mobaRibbonEdgeRouteToolbarObject", moba_edge_route.toolbar_object
            )
            edge_widget.setProperty("mobaRibbonEdgeRouteSpacerObject", moba_edge_route.spacer_object)
            edge_widget.setProperty(moba_edge_route.action_keys_property, edge_action_keys)
            edge_widget.setProperty("mobaRibbonEdgeRouteRenderSource", moba_edge_route.render_source)
        moba_edge_actions = {
            action.key: action for action in gui_design_moba_ribbon_edge_actions()
        }
        x_server_action = moba_edge_actions["xserver"]
        self.moba_x_server_button = self.toolbar_button(
            x_server_action.label,
            "SP_ComputerIcon",
            x_server_action.tooltip,
        )
        self.moba_x_server_button.setObjectName("mobaXServerAction")
        self.moba_x_server_button.setProperty("mobaIconKey", x_server_action.icon_key)
        self.moba_x_server_button.setIcon(self.moba_ribbon_icon(x_server_action.icon_key, x_server_action.color))
        self.apply_moba_ribbon_action_geometry(self.moba_x_server_button, x_server_action.key)
        self.apply_moba_ribbon_edge_action_route(
            self.moba_x_server_button,
            moba_edge_route.xserver_action_key,
            moba_edge_route.xserver_action_label,
            moba_edge_route.xserver_action_object,
            moba_edge_route.xserver_icon_key,
            moba_edge_route.xserver_handler,
        )
        exit_action = moba_edge_actions["exit"]
        self.moba_exit_button = self.toolbar_button(exit_action.label, "SP_DialogCloseButton", exit_action.tooltip)
        self.moba_exit_button.setObjectName("mobaExitAction")
        self.moba_exit_button.setProperty("mobaIconKey", exit_action.icon_key)
        self.moba_exit_button.setIcon(self.moba_ribbon_icon(exit_action.icon_key, exit_action.color))
        self.apply_moba_ribbon_action_geometry(self.moba_exit_button, exit_action.key)
        self.apply_moba_ribbon_edge_action_route(
            self.moba_exit_button,
            moba_edge_route.exit_action_key,
            moba_edge_route.exit_action_label,
            moba_edge_route.exit_action_object,
            moba_edge_route.exit_icon_key,
            moba_edge_route.exit_handler,
        )
        self.add_toolbar_widget(self.main_toolbar, self.moba_x_server_button)
        self.add_toolbar_widget(self.main_toolbar, self.moba_exit_button)
        self.main_toolbar_buttons = [
            self.refresh_button,
            self.new_profile_button,
            self.import_profile_button,
            self.edit_profile_button,
            self.remove_profile_button,
            self.connect_button,
            self.files_button,
            self.queue_button,
            self.dry_run_button,
            self.doctor_button,
            self.split_h_button,
            self.split_v_button,
        ]
        self.product_toolbar_buttons = self.main_toolbar_buttons
        product_toolbar_keys = (
            "refresh",
            "new",
            "import",
            "edit",
            "remove",
            "connect",
            "files",
            "queue",
            "dry-run",
            "doctor",
            "split-h",
            "split-v",
        )
        self.product_toolbar_button_by_key = dict(
            zip(product_toolbar_keys, self.product_toolbar_buttons, strict=True)
        )
        for key, button in self.product_toolbar_button_by_key.items():
            button.setObjectName("productToolbarButton")
            button.setProperty("productToolbarKey", key)
            self.add_toolbar_widget(self.main_toolbar, button)
        # SecureCRT and mRemoteNG put a compact connection field directly
        # in the native toolbar.  Keep these widgets registered even when
        # another preset is active so switching designs does not rebuild
        # the toolbar or lose keyboard focus routes.
        self.securecrt_host_input = QLineEdit()
        self.securecrt_host_input.setObjectName("secureCrtHostInput")
        self.securecrt_host_input.setPlaceholderText("Enter host <Alt+P>")
        self.securecrt_host_input.setToolTip("SecureCRT host field; press Enter to connect")
        self.securecrt_keyword_input = QLineEdit()
        self.securecrt_keyword_input.setObjectName("secureCrtKeywordInput")
        self.securecrt_keyword_input.setPlaceholderText("Keyword <Alt+/>")
        self.securecrt_keyword_input.setToolTip("SecureCRT keyword filter")
        self.mremoteng_connect_input = QLineEdit()
        self.mremoteng_connect_input.setObjectName("mRemoteNgConnectInput")
        self.mremoteng_connect_input.setPlaceholderText("Connect:")
        self.mremoteng_connect_input.setToolTip("mRemoteNG connect field; press Enter to open")
        self.mremoteng_protocol_label = QLabel("RDP")
        self.mremoteng_protocol_label.setObjectName("mRemoteNgProtocolLabel")
        self.mremoteng_protocol_label.setToolTip("mRemoteNG active protocol")
        for connection_widget in (
            self.securecrt_host_input,
            self.securecrt_keyword_input,
            self.mremoteng_connect_input,
            self.mremoteng_protocol_label,
        ):
            self.add_toolbar_widget(self.main_toolbar, connection_widget)
        self.view_label = QLabel("View")
        self.view_label.setObjectName("toolbarLabel")
        self.layout_label = QLabel("Layout")
        self.layout_label.setObjectName("toolbarLabel")
        self.add_toolbar_widget(self.layout_toolbar, self.layout_label)
        self.add_toolbar_widget(self.layout_toolbar, self.layout_select)
        self.layout_toolbar_buttons = [
            self.new_layout_button,
            self.edit_layout_button,
            self.remove_layout_button,
        ]
        for button in self.layout_toolbar_buttons:
            self.add_toolbar_widget(self.layout_toolbar, button)
        self.add_toolbar_widget(self.layout_toolbar, self.open_layout_button)
        self.layout_toolbar_buttons.append(self.open_layout_button)
        self.layout_toolbar.addSeparator()
        self.add_toolbar_widget(self.layout_toolbar, self.view_label)
        self.add_toolbar_widget(self.layout_toolbar, self.design_select)
        self.layout_toolbar.addSeparator()
        self.add_toolbar_widget(self.layout_toolbar, self.search_input)
        self.add_toolbar_widget(self.layout_toolbar, self.find_button)

    def bind_toolbar_actions(self) -> None:
        self.product_toolbar_callbacks = {
            "refresh": self.refresh_profiles,
            "new": self.create_profile,
            "import": self.import_profiles_with_preview,
            "edit": self.edit_selected_profile,
            "remove": self.remove_selected_profile,
            "connect": lambda: self.connect_selected(False),
            "files": self.open_files_selected,
            "queue": self.open_transfer_queue_selected,
            "dry-run": lambda: self.connect_selected(True),
            "doctor": self.show_doctor,
            "split-h": lambda: self.add_split("horizontal"),
            "split-v": lambda: self.add_split("vertical"),
        }
        for key, button in self.product_toolbar_button_by_key.items():
            button.setProperty("productToolbarHandlerKey", key)
            button.clicked.connect(
                lambda _checked=False, action_key=key: self.run_product_toolbar_action(
                    action_key
                )
            )
        self.layout_toolbar_callbacks = {
            "new-layout": self.create_layout,
            "edit-layout": self.edit_selected_layout,
            "remove-layout": self.remove_selected_layout,
            "open-layout": self.open_selected_layout,
        }
        for key, button in zip(
            self.layout_toolbar_callbacks,
            self.layout_toolbar_buttons,
            strict=True,
        ):
            button.setProperty("layoutToolbarHandlerKey", key)
            button.clicked.connect(
                lambda _checked=False, action_key=key: self.run_layout_toolbar_action(
                    action_key
                )
            )
        self.moba_x_server_button.clicked.connect(self.show_moba_x_server_status)
        self.moba_exit_button.clicked.connect(cast(QWidget, self).close)

    def toolbar_button(self, label: str, icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setText(label)
        button.setToolTip(tooltip)
        button.setProperty("standardIconName", icon_name)
        button.setIcon(
            _widget_style(cast(QWidget, self)).standardIcon(self.standard_icon(icon_name))
        )
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setAutoRaise(False)
        return button

    def add_toolbar_widget(self, toolbar: QToolBar, widget: QWidget) -> QAction:
        action = _required_gui_value(
            toolbar.addWidget(widget),
            f"toolbar action for {widget.objectName() or type(widget).__name__}",
        )
        self.toolbar_widget_actions[id(widget)] = action
        return action

    def set_toolbar_widget_visible(self, widget: QWidget, visible: bool) -> None:
        action = self.toolbar_widget_actions.get(id(widget))
        if action is None:
            raise RuntimeError(
                f"toolbar widget is not registered: {widget.objectName() or type(widget).__name__}"
            )
        action.setVisible(visible)
        widget.setVisible(visible)

    def toolbar_widget_action(self, widget: QWidget) -> QAction:
        action = self.toolbar_widget_actions.get(id(widget))
        if action is None:
            raise RuntimeError(
                f"toolbar widget is not registered: {widget.objectName() or type(widget).__name__}"
            )
        return action

    def set_toolbar_widget_enabled(self, widget: QWidget, enabled: bool) -> None:
        action = self.toolbar_widget_action(widget)
        action.setEnabled(enabled)
        widget.setEnabled(enabled)

    def run_product_toolbar_action(self, action_key: str) -> None:
        callback = self.product_toolbar_callbacks.get(action_key)
        if callback is None:
            raise RuntimeError(f"missing product toolbar callback: {action_key}")
        self.run_operator_action(callback)

    def run_layout_toolbar_action(self, action_key: str) -> None:
        callback = self.layout_toolbar_callbacks.get(action_key)
        if callback is None:
            raise RuntimeError(f"missing layout toolbar callback: {action_key}")
        self.run_operator_action(callback)

    def update_layout_action_states(self, *_args) -> None:
        has_layout = self.layout_select.currentIndex() >= 0
        for button in (
            self.edit_layout_button,
            self.remove_layout_button,
            self.open_layout_button,
        ):
            self.set_toolbar_widget_enabled(button, has_layout)

    def apply_moba_ribbon_action_geometry(self, button: QToolButton, key: str) -> None:
        geometry = gui_design_moba_ribbon_action_geometry_for(key)
        button.setProperty(
            "mobaRibbonActionGeometryKeys",
            [item.key for item in gui_design_moba_ribbon_action_geometry()],
        )
        button.setProperty("mobaRibbonStaticX", geometry.static_x)
        button.setProperty("mobaRibbonStaticWidth", geometry.width)
        button.setProperty("mobaRibbonIconX", geometry.icon_x)
        button.setProperty("mobaRibbonIconY", geometry.icon_y)
        button.setProperty("mobaRibbonIconSize", geometry.icon_size)
        button.setProperty("mobaRibbonLabelX", geometry.label_x)
        button.setProperty("mobaRibbonLabelY", geometry.label_y)
        button.setProperty("mobaRibbonLabelFontSize", geometry.label_font_size)
        button.setProperty("mobaRibbonSeparatorBefore", geometry.separator_before)
        button.setProperty("mobaRibbonSeparatorX", geometry.separator_x)
        button.setProperty("mobaRibbonSeparatorTop", geometry.separator_top)
        button.setProperty("mobaRibbonSeparatorBottom", geometry.separator_bottom)
        button.setProperty("mobaRibbonActiveOutlineX", geometry.active_outline_x)
        button.setProperty("mobaRibbonActiveOutlineY", geometry.active_outline_y)
        button.setProperty("mobaRibbonActiveOutlineWidth", geometry.active_outline_width)
        button.setProperty("mobaRibbonActiveOutlineHeight", geometry.active_outline_height)
        button.setMinimumWidth(geometry.width)
        button.setIconSize(QSize(geometry.icon_size, geometry.icon_size))

    def apply_moba_ribbon_edge_action_route(
        self,
        button: QToolButton,
        action_key: str,
        action_label: str,
        action_object: str,
        icon_key: str,
        handler: str,
    ) -> None:
        route = gui_design_moba_ribbon_edge_action_route()
        button.setProperty("mobaRibbonEdgeRouteKey", route.key)
        button.setProperty("mobaRibbonEdgeRouteRole", route.route_role)
        button.setProperty("mobaRibbonEdgeRouteToolbarObject", route.toolbar_object)
        button.setProperty("mobaRibbonEdgeRouteSpacerObject", route.spacer_object)
        button.setProperty(route.action_key_property, action_key)
        button.setProperty(route.action_label_property, action_label)
        button.setProperty(route.action_object_property, action_object)
        button.setProperty(route.icon_key_property, icon_key)
        button.setProperty("mobaRibbonEdgeRouteHandler", handler)
        button.setProperty(route.action_keys_property, [route.xserver_action_key, route.exit_action_key])
        button.setProperty("mobaRibbonEdgeRouteRenderSource", route.render_source)
        if action_key == route.xserver_action_key:
            button.setProperty("mobaRibbonEdgeRouteDialogTitle", route.xserver_dialog_title)
            button.setProperty("mobaRibbonEdgeRouteDialogDetail", route.xserver_dialog_detail)

    def build_moba_ribbon_buttons(self) -> list[QToolButton]:
        slots: dict[str, Callable[..., object]] = {
            "session": self.create_profile,
            "servers": self.show_moba_servers_status,
            "tools": self.show_moba_tools_status,
            "games": self.show_moba_games_status,
            "sessions": lambda _checked=False: self.connect_selected(False),
            "view": self.cycle_design_preset,
            "split": lambda _checked=False: self.add_split("horizontal"),
            "multiexec": self.show_moba_multiexec_status,
            "tunneling": self.show_moba_tunneling_status,
            "packages": self.show_moba_packages_dialog,
            "settings": self.show_moba_settings_status,
            "help": self.show_moba_help_dialog,
        }
        self.moba_ribbon_callbacks = slots
        tooltips = gui_design_moba_ribbon_tooltips()
        buttons: list[QToolButton] = []
        for action in gui_design_moba_ribbon_actions():
            button = self.toolbar_button(action.label, "SP_FileIcon", tooltips[action.icon_key])
            button.setObjectName("mobaRibbonButton")
            button.setProperty("mobaIconKey", action.icon_key)
            button.setProperty("mobaRibbonHandlerKey", action.icon_key)
            button.setIcon(self.moba_ribbon_icon(action.icon_key, action.color))
            self.apply_moba_ribbon_action_geometry(button, action.icon_key)
            button.clicked.connect(
                lambda _checked=False, action_key=action.icon_key: self.run_moba_ribbon_action(
                    action_key
                )
            )
            if action.icon_key == "split":
                split_menu = QMenu(button)
                split_menu.setObjectName("mobaSplitMenu")
                split_menu.addAction("Split horizontally", lambda: self.add_split("horizontal"))
                split_menu.addAction("Split vertically", lambda: self.add_split("vertical"))
                button.setMenu(split_menu)
                button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            buttons.append(button)
        return buttons

    def run_moba_ribbon_action(self, action_key: str) -> None:
        callback = self.moba_ribbon_callbacks.get(action_key)
        if callback is None:
            raise RuntimeError(f"missing Moba ribbon callback: {action_key}")
        self.run_operator_action(callback)

    def configure_toolbar_copy_for_design(self, preset: GuiDesignPreset) -> None:
        actions = gui_design_toolbar_actions(preset.id)
        action_keys = [key for key, _label, _tooltip in actions]
        expected_keys = set(self.product_toolbar_button_by_key)
        if len(action_keys) != len(set(action_keys)):
            raise RuntimeError(f"duplicate toolbar action keys for {preset.id}: {action_keys}")
        if set(action_keys) != expected_keys:
            missing = sorted(expected_keys - set(action_keys))
            extra = sorted(set(action_keys) - expected_keys)
            raise RuntimeError(
                f"toolbar action contract mismatch for {preset.id}: missing={missing}, extra={extra}"
            )
        securecrt_toolbar_actions = {
            action.key: action for action in gui_design_securecrt_top_chrome().toolbar_actions
        }
        mremoteng_toolbar_actions = {
            action.key: action for action in gui_design_mremoteng_top_chrome().toolbar_actions
        }
        remmina_transfer_route = (
            gui_design_remmina_sftp_transfer_route() if preset.id == "remmina" else None
        )
        for key, label, tooltip in actions:
            button = self.product_toolbar_button_by_key[key]
            button.setText(label)
            button.setToolTip(tooltip)
            button.setProperty("productToolbarKey", key)
            button.setProperty("productToolbarLabel", label)
            button.setProperty("productToolbarTooltip", tooltip)
            button.setProperty("productChromePreset", preset.id)
            securecrt_action = (
                securecrt_toolbar_actions.get(key) if preset.id == "securecrt" else None
            )
            mremoteng_action = (
                mremoteng_toolbar_actions.get(key) if preset.id == "mremoteng" else None
            )
            product_icon_key = (
                securecrt_action.icon_key
                if securecrt_action is not None
                else mremoteng_action.icon_key
                if mremoteng_action is not None
                else ""
            )
            if not product_icon_key:
                product_icon_key = {
                    "refresh": "refresh-tree",
                    "new": "new-session",
                    "import": "import-session",
                    "edit": "properties",
                    "remove": "delete",
                    "connect": "connect",
                    "files": "sftp",
                    "queue": "transfer",
                    "dry-run": "command",
                    "doctor": "tools",
                    "split-h": "tile-h",
                    "split-v": "tile-v",
                }.get(key, key)
            if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                self.product_toolbar_button_by_key[key].setIcon(
                    self.product_toolbar_icon(
                        preset.id,
                        product_icon_key or key,
                        size=max(14, min(18, preset.toolbar_icon_size)),
                    )
                )
            else:
                standard_icon_name = str(button.property("standardIconName") or "SP_FileIcon")
                button.setIcon(
                    _widget_style(cast(QWidget, self)).standardIcon(self.standard_icon(standard_icon_name))
                )
            button.setProperty(
                "secureCrtTopToolbarKey", securecrt_action.key if securecrt_action else ""
            )
            button.setProperty(
                "secureCrtTopToolbarLabel", securecrt_action.label if securecrt_action else ""
            )
            button.setProperty(
                "secureCrtTopToolbarIconKey",
                securecrt_action.icon_key if securecrt_action else "",
            )
            button.setProperty(
                "secureCrtTopToolbarStaticX",
                securecrt_action.static_x if securecrt_action else 0,
            )
            button.setProperty(
                "secureCrtTopToolbarStaticWidth",
                securecrt_action.static_width if securecrt_action else 0,
            )
            button.setProperty(
                "mRemoteNgTopToolbarKey", mremoteng_action.key if mremoteng_action else ""
            )
            button.setProperty(
                "mRemoteNgTopToolbarLabel", mremoteng_action.label if mremoteng_action else ""
            )
            button.setProperty(
                "mRemoteNgTopToolbarIconKey",
                mremoteng_action.icon_key if mremoteng_action else "",
            )
            button.setProperty(
                "mRemoteNgTopToolbarStaticX",
                mremoteng_action.static_x if mremoteng_action else 0,
            )
            button.setProperty(
                "mRemoteNgTopToolbarStaticWidth",
                mremoteng_action.static_width if mremoteng_action else 0,
            )
            active_remmina_route = (
                remmina_transfer_route
                if remmina_transfer_route is not None
                and key == remmina_transfer_route.toolbar_action_key
                else None
            )
            is_remmina_transfer = active_remmina_route is not None
            button.setProperty(
                "remminaSftpTransferRouteKey",
                active_remmina_route.key if active_remmina_route is not None else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteRole",
                active_remmina_route.route_role
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteToolbarActionKey",
                active_remmina_route.toolbar_action_key
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteToolbarActionLabel",
                active_remmina_route.toolbar_action_label
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteToolbarActionObject",
                active_remmina_route.toolbar_action_object
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteSelectedProfileKey",
                active_remmina_route.selected_profile_key
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteSelectedProfile",
                active_remmina_route.selected_profile_name
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteProtocol",
                active_remmina_route.selected_profile_protocol
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteStatus",
                active_remmina_route.selected_profile_status
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteActiveTab",
                active_remmina_route.active_tab_label
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRoutePath",
                active_remmina_route.remote_path
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteQueueState",
                active_remmina_route.transfer_status
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteQueueLabel",
                active_remmina_route.transfer_queue_label
                if active_remmina_route is not None
                else "",
            )
            button.setProperty(
                "remminaSftpTransferRouteRenderSource",
                active_remmina_route.render_source
                if active_remmina_route is not None
                else "",
            )
            if remmina_transfer_route is not None:
                button.setProperty(
                    remmina_transfer_route.toolbar_active_property,
                    "true" if is_remmina_transfer else "false",
                )
                if is_remmina_transfer:
                    self.apply_remmina_sftp_transfer_action_route_properties(button, remmina_transfer_route)
            if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                # The static preview geometry reserves room for labels,
                # while the live product chrome is intentionally
                # icon-only.  Do not let those preview widths recreate the
                # oversized generic ribbon in the real window.
                button.setMinimumWidth(
                    28 if preset.id in {"securecrt", "mremoteng"} else 30
                )
            else:
                button.setMinimumWidth(
                    securecrt_action.static_width
                    if securecrt_action
                    else mremoteng_action.static_width
                    if mremoteng_action
                    else 0
                )
            button.setEnabled(True)
            if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                button_style = _widget_style(button)
                button_style.unpolish(button)
                button_style.polish(button)
                button.update()

    def configure_toolbar_for_design(self, preset: GuiDesignPreset, is_moba: bool, icon_size: int) -> None:
        icon = QSize(icon_size, icon_size)
        is_securecrt = preset.id == "securecrt"
        is_mremoteng = preset.id == "mremoteng"
        is_product_reference = preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        self.main_toolbar.setProperty("productChromePreset", preset.id)
        self.layout_toolbar.setProperty("productChromePreset", preset.id)
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        for button in self.main_toolbar_buttons + self.layout_toolbar_buttons:
            button.setProperty("productChromePreset", preset.id)
            button.setIconSize(icon)
            button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if button in self.main_toolbar_buttons
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            button.setMinimumSize(QSize(0, 0))
            button.setMaximumSize(QSize(16777215, 16777215))
            self.set_toolbar_widget_visible(
                button,
                not is_moba,
            )
        for button in self.layout_toolbar_buttons:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            minimum_width = 116 if button is self.remove_layout_button else 72
            button.setMinimumSize(QSize(minimum_width, 44))
            maximum_width = 120 if button is self.remove_layout_button else 96
            button.setMaximumSize(QSize(maximum_width, 52))
        self.find_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.find_button.setMinimumSize(QSize(58, 0))
        self.find_button.setMaximumSize(QSize(78, 44))
        for view_widget in (self.view_label, self.design_select):
            self.set_toolbar_widget_visible(view_widget, True)
        for search_widget in (self.search_input, self.find_button):
            self.set_toolbar_widget_visible(search_widget, not is_moba)

        moba_widgets = [
            *self.moba_ribbon_buttons,
            self.moba_toolbar_spacer,
            self.moba_x_server_button,
            self.moba_exit_button,
        ]
        for moba_widget in moba_widgets:
            self.set_toolbar_widget_visible(moba_widget, is_moba)
        for securecrt_widget in (
            self.securecrt_host_input,
            self.securecrt_keyword_input,
        ):
            self.set_toolbar_widget_visible(securecrt_widget, preset.id == "securecrt")
        for mremoteng_widget in (
            self.mremoteng_connect_input,
            self.mremoteng_protocol_label,
        ):
            self.set_toolbar_widget_visible(mremoteng_widget, preset.id == "mremoteng")
        self.securecrt_host_shortcut.setEnabled(is_securecrt)
        self.securecrt_keyword_shortcut.setEnabled(is_securecrt)
        if is_moba:
            top_stack = gui_design_moba_top_stack_geometry()
            self.main_toolbar.setMinimumHeight(top_stack.ribbon_height)
            self.main_toolbar.setMaximumHeight(top_stack.ribbon_height)
            self.main_toolbar.setProperty("mobaTopStackRibbonY", top_stack.ribbon_y)
            self.main_toolbar.setProperty("mobaTopStackRibbonHeight", top_stack.ribbon_height)
            for button in self.moba_ribbon_buttons:
                button.setIconSize(icon)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                width = int(button.property("mobaRibbonStaticWidth") or 58)
                button.setMinimumSize(QSize(width, top_stack.ribbon_height))
                button.setMaximumSize(
                    QSize(width + 8, top_stack.ribbon_height)
                )
            for button in [self.moba_x_server_button, self.moba_exit_button]:
                button.setIconSize(icon)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                width = int(button.property("mobaRibbonStaticWidth") or 58)
                button.setMinimumSize(QSize(width, top_stack.ribbon_height))
                button.setMaximumSize(
                    QSize(width + 8, top_stack.ribbon_height)
                )
        elif is_securecrt:
            self.main_toolbar.setMinimumHeight(gui_design_securecrt_top_chrome().toolbar_height)
            self.main_toolbar.setMaximumHeight(gui_design_securecrt_top_chrome().toolbar_height)
            for button in self.main_toolbar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setMinimumSize(QSize(28, 28))
                button.setMaximumSize(QSize(34, 32))
            self.securecrt_host_input.setMinimumSize(QSize(142, 24))
            self.securecrt_host_input.setMaximumSize(QSize(166, 26))
            self.securecrt_keyword_input.setMinimumSize(QSize(130, 24))
            self.securecrt_keyword_input.setMaximumSize(QSize(154, 26))
        elif is_mremoteng:
            self.main_toolbar.setMinimumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
            self.main_toolbar.setMaximumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
            for button in self.main_toolbar_buttons:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setMinimumSize(QSize(28, 26))
                button.setMaximumSize(QSize(34, 30))
            self.mremoteng_connect_input.setMinimumSize(QSize(110, 24))
            self.mremoteng_connect_input.setMaximumSize(QSize(132, 26))
            self.mremoteng_protocol_label.setMinimumSize(QSize(28, 22))
            self.mremoteng_protocol_label.setMaximumSize(QSize(42, 24))
        else:
            self.main_toolbar.setMinimumHeight(0)
            self.main_toolbar.setMaximumHeight(16777215)
            for button in self.main_toolbar_buttons:
                # Give the native editor enough room for the label and
                # icon.  The responsive pass below may switch to
                # icon-only mode when the window genuinely cannot fit;
                # it must never leave a text-under-icon button with an
                # arbitrary 72px cap that paints ``Re...``/``Co...``.
                button.setMinimumSize(QSize(76, 46))
                button.setMaximumSize(QSize(124, 58))
        self.configure_responsive_layout_toolbar()
        if is_moba:
            # MobaXterm's large ribbon owns the product actions; retain a
            # small, stable utility row for the shared style selector.
            self.layout_toolbar.setMinimumHeight(30)
            self.layout_toolbar.setMaximumHeight(32)
            self.layout_toolbar.setIconSize(QSize(14, 14))
            for moba_layout_widget in (self.layout_label, self.layout_select):
                self.set_toolbar_widget_visible(moba_layout_widget, False)
            for button in self.layout_toolbar_buttons:
                self.set_toolbar_widget_visible(button, False)
            self.set_toolbar_widget_visible(self.view_label, True)
            self.set_toolbar_widget_visible(self.design_select, True)
            self.set_toolbar_widget_visible(self.search_input, False)
            self.set_toolbar_widget_visible(self.find_button, False)
            self.design_select.setMinimumSize(QSize(112, 24))
            self.design_select.setMaximumSize(QSize(150, 26))
        if is_product_reference:
            # SecureCRT, Termius, Remmina and mRemoteNG use a single
            # compact utility strip beneath their product toolbar.  Keep
            # the layout/search widgets registered and reachable for the
            # workspace routes, but do not expose the generic multi-row
            # layout editor chrome that none of the reference products
            # place above their connected document surface.
            self.layout_toolbar.setMinimumHeight(30)
            self.layout_toolbar.setMaximumHeight(32)
            self.layout_toolbar.setIconSize(QSize(min(icon_size, 14), min(icon_size, 14)))
            for reference_layout_widget in (self.layout_label, self.layout_select, self.view_label):
                self.set_toolbar_widget_visible(reference_layout_widget, False)
            for button in self.layout_toolbar_buttons:
                self.set_toolbar_widget_visible(button, False)
            self.set_toolbar_widget_visible(self.design_select, True)
            self.set_toolbar_widget_visible(self.search_input, True)
            self.set_toolbar_widget_visible(self.find_button, True)
            self.design_select.setMinimumSize(QSize(108, 24))
            self.design_select.setMaximumSize(QSize(132, 26))
            self.search_input.setMinimumSize(QSize(138, 24))
            self.search_input.setMaximumSize(QSize(210, 26))
            self.find_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.find_button.setMinimumSize(QSize(26, 24))
            self.find_button.setMaximumSize(QSize(30, 26))
            if preset.id in {"remmina", "termius"}:
                self.main_toolbar.setMinimumHeight(32)
                self.main_toolbar.setMaximumHeight(34)
                self.main_toolbar.setIconSize(QSize(16, 16))
            self.search_input.setPlaceholderText(
                {
                    "securecrt": "Find session",
                    "termius": "Search hosts",
                    "remmina": "Quick connect",
                    "mremoteng": "Filter connections",
                }.get(preset.id, "Search") if cast(QWidget, self).property("guiPreviewSamples")
                else "Search active terminal or log"
            )
            layout_toolbar_style = _widget_style(self.layout_toolbar)
            layout_toolbar_style.unpolish(self.layout_toolbar)
            layout_toolbar_style.polish(self.layout_toolbar)
        if preset.id == "termius":
            # Termius presents its connected navigation (hamburger,
            # Vaults and SFTP) inside the document surface rather than a
            # second desktop-style action ribbon.  Keep the registered
            # product actions visible as a compact icon-only strip so
            # keyboard/mouse routes and the 1024px interaction contract
            # remain reachable, while the native SFTP header owns the
            # dominant connected chrome.
            for button in self.main_toolbar_buttons:
                self.set_toolbar_widget_visible(button, True)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setMinimumSize(QSize(26, 24))
                button.setMaximumSize(QSize(30, 26))
            self.main_toolbar.setMinimumHeight(30)
            self.main_toolbar.setMaximumHeight(32)
            self.main_toolbar.setIconSize(QSize(14, 14))
            main_toolbar_style = _widget_style(self.main_toolbar)
            main_toolbar_style.unpolish(self.main_toolbar)
            main_toolbar_style.polish(self.main_toolbar)

    def configure_responsive_layout_toolbar(self) -> None:
        """Keep every layout/search control directly reachable at the 1024px boundary."""

        window = cast(QWidget, self)
        compact = window.width() <= 1100
        is_moba = self.current_design_is_moba()
        is_product_reference = self.current_design_id() in PRODUCT_REFERENCE_TAB_PRESET_IDS

        if is_product_reference:
            # The reference products use a compact, icon-led toolbar.  Do
            # not switch back to Qt's text-under-icon mode merely because
            # the window is wide enough: that produces a generic ribbon
            # instead of SecureCRT/mRemoteNG/Remmina chrome.  Text remains
            # available through the tooltip and accessibility name.
            product_id = self.current_design_id()
            button_width = 28 if product_id in {"securecrt", "mremoteng"} else 30
            button_height = 28 if product_id == "securecrt" else 26
            self.main_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            for button in self.main_toolbar_buttons:
                button.setAccessibleName(button.text())
                button.setAccessibleDescription(button.toolTip())
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setMinimumSize(QSize(button_width, button_height))
                button.setMaximumSize(QSize(button_width + 6, button_height + 4))
            if product_id == "securecrt":
                self.main_toolbar.setMinimumHeight(gui_design_securecrt_top_chrome().toolbar_height)
                self.main_toolbar.setMaximumHeight(gui_design_securecrt_top_chrome().toolbar_height)
            elif product_id == "mremoteng":
                self.main_toolbar.setMinimumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
                self.main_toolbar.setMaximumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
            else:
                self.main_toolbar.setMinimumHeight(32)
                self.main_toolbar.setMaximumHeight(34)
            self.layout_select.setMinimumWidth(112 if compact else 150)
            self.layout_select.setMaximumWidth(132 if compact else 190)
            self.design_select.setMinimumWidth(108 if compact else 118)
            self.design_select.setMaximumWidth(132 if compact else 150)
            self.search_input.setMinimumWidth(138 if compact else 164)
            self.search_input.setMaximumWidth(210 if compact else 250)
            self.search_input.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.find_button.setAccessibleName(self.find_button.text())
            self.find_button.setAccessibleDescription(self.find_button.toolTip())
            self.find_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.find_button.setMinimumSize(QSize(30, 24))
            self.find_button.setMaximumSize(QSize(34, 30))
            # Reapply the compact product utility strip on every resize.
            # Qt can otherwise restore the generic layout controls after
            # a preset transition and squeeze the product search surface.
            for widget in (self.layout_label, self.layout_select, self.view_label):
                self.set_toolbar_widget_visible(widget, False)
            for button in self.layout_toolbar_buttons:
                self.set_toolbar_widget_visible(button, False)
            self.set_toolbar_widget_visible(self.design_select, True)
            self.set_toolbar_widget_visible(self.search_input, True)
            self.set_toolbar_widget_visible(self.find_button, True)
            self.layout_toolbar.setMinimumHeight(30)
            self.layout_toolbar.setMaximumHeight(32)
            self.layout_toolbar.setIconSize(QSize(14, 14))
            self.design_select.setMinimumSize(QSize(108, 24))
            self.design_select.setMaximumSize(QSize(132, 26))
            self.search_input.setMinimumSize(QSize(138, 24))
            self.search_input.setMaximumSize(QSize(210, 26))
            return

        # A text-under-icon QToolButton needs substantially more width than
        # its icon.  Keeping that paint mode while squeezing twelve product
        # actions into a 1024px toolbar made the rectangles fit while the
        # actual labels were clipped.  Measure the real preferred widths and
        # only paint labels when all of them fit; compact mode retains the
        # full text as the accessible name and tooltip.
        if not is_moba:
            preferred_widths: list[int] = []
            for button in self.main_toolbar_buttons:
                button.setAccessibleName(button.text())
                button.setAccessibleDescription(button.toolTip())
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                )
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
                text_width = button.fontMetrics().horizontalAdvance(button.text())
                icon_width = button.iconSize().width()
                preferred_widths.append(
                    max(
                        button.sizeHint().width(),
                        text_width + 18,
                        icon_width + 22,
                        76,
                    )
                )
            toolbar_layout = _required_gui_value(
                self.main_toolbar.layout(),
                "main toolbar layout",
            )
            margins = toolbar_layout.contentsMargins()
            toolbar_margins = (margins.left(), margins.right())
            toolbar_spacing = max(0, toolbar_layout.spacing())
            toolbar_width = max(0, self.main_toolbar.width())
            available_toolbar_width = max(
                0,
                toolbar_width - toolbar_margins[0] - toolbar_margins[1],
            )
            preferred_toolbar_width = (
                sum(preferred_widths)
                + toolbar_spacing * max(0, len(preferred_widths) - 1)
                + 24
            )
            labels_fit = available_toolbar_width >= preferred_toolbar_width
            self.main_toolbar.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if labels_fit
                else Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            for button, preferred_width in zip(
                self.main_toolbar_buttons,
                preferred_widths,
                strict=True,
            ):
                minimum_height = max(40, button.minimumHeight())
                maximum_height = max(minimum_height, button.maximumHeight())
                if labels_fit:
                    button.setToolButtonStyle(
                        Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                    )
                    button.setMinimumSize(
                        QSize(preferred_width, minimum_height)
                    )
                    button.setMaximumSize(
                        QSize(preferred_width, maximum_height)
                    )
                    button.setProperty("productToolbarLabelsVisible", True)
                else:
                    button.setToolButtonStyle(
                        Qt.ToolButtonStyle.ToolButtonIconOnly
                    )
                    button.setMinimumSize(QSize(44, minimum_height))
                    button.setMaximumSize(QSize(72, maximum_height))
                    button.setProperty("productToolbarLabelsVisible", False)
                button.setToolTip(button.toolTip() or button.text())

        self.layout_select.setMinimumWidth(112 if compact else 150)
        self.layout_select.setMaximumWidth(132 if compact else 190)
        self.design_select.setMinimumWidth(112 if compact else 150)
        self.design_select.setMaximumWidth(132 if compact else 180)
        self.search_input.setMinimumWidth(132 if compact else 160)
        self.search_input.setMaximumWidth(220 if compact else 280)
        self.search_input.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        compact_auxiliary_labels = window.width() < 1280
        for button in self.layout_toolbar_buttons:
            button.setAccessibleName(button.text())
            button.setAccessibleDescription(button.toolTip())
            if compact_auxiliary_labels:
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonIconOnly
                )
                minimum_width = 44
                maximum_width = 52
            else:
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                )
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
                minimum_width = button.sizeHint().width()
                maximum_width = minimum_width
            button.setMinimumSize(QSize(minimum_width, 44))
            button.setMaximumSize(QSize(maximum_width, 52))
        self.find_button.setAccessibleName(self.find_button.text())
        self.find_button.setAccessibleDescription(self.find_button.toolTip())
        if compact_auxiliary_labels:
            self.find_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonIconOnly
            )
            self.find_button.setMinimumSize(QSize(44, 0))
            self.find_button.setMaximumSize(QSize(52, 44))
        else:
            self.find_button.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            self.find_button.setMinimumWidth(0)
            self.find_button.setMaximumWidth(16777215)
            preferred_find_width = self.find_button.sizeHint().width()
            self.find_button.setMinimumSize(QSize(preferred_find_width, 0))
            self.find_button.setMaximumSize(QSize(preferred_find_width, 44))
