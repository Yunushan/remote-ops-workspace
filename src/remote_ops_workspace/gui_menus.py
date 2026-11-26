from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, cast

from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow, QMenu, QMenuBar, QWidget

from .gui_designs import (
    GUI_DESIGN_PRESETS,
    GuiDesignPreset,
    GuiMobaTopMenuGeometry,
    GuiMobaTopMenuItem,
    GuiMRemoteNgTopMenuItem,
    GuiSecureCrtTopMenuItem,
    gui_design_moba_top_menu_geometry,
    gui_design_moba_top_menu_geometry_for,
    gui_design_moba_top_menu_items,
    gui_design_mremoteng_top_chrome,
    gui_design_securecrt_top_chrome,
)
from .gui_values import _required_gui_value

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox, QLineEdit

_REFERENCE_MENU_PROPERTIES = {
    "secureCrtTopMenu": (
        "secureCrtTopMenuKey",
        "secureCrtTopMenuLabel",
        "secureCrtTopMenuPrimaryAction",
    ),
    "mRemoteNgTopMenu": (
        "mRemoteNgTopMenuKey",
        "mRemoteNgTopMenuLabel",
        "mRemoteNgTopMenuPrimaryAction",
    ),
}


def _add_top_menu(
    menu_bar: QMenuBar,
    item: GuiMobaTopMenuItem | GuiSecureCrtTopMenuItem | GuiMRemoteNgTopMenuItem,
    *,
    display_name: str,
    object_name: str,
    properties: Mapping[str, object],
) -> tuple[QMenu, QAction]:
    menu = _required_gui_value(
        menu_bar.addMenu(item.label),
        f"{display_name} top menu for {item.key}",
    )
    menu.setObjectName(object_name)
    menu_action = _required_gui_value(
        menu.menuAction(),
        f"{display_name} menu action for {item.key}",
    )
    for target in (menu, menu_action):
        for name, value in properties.items():
            target.setProperty(name, value)
        target.setToolTip(item.tooltip)
    return menu, menu_action


def add_moba_top_menu(
    menu_bar: QMenuBar,
    item: GuiMobaTopMenuItem,
    geometry: GuiMobaTopMenuGeometry,
    geometry_keys: Sequence[str],
) -> tuple[QMenu, QAction]:
    return _add_top_menu(
        menu_bar,
        item,
        display_name="Moba",
        object_name="mobaTopMenu",
        properties={
            "mobaTopMenuKey": item.key,
            "mobaTopMenuLabel": item.label,
            "mobaTopMenuGeometryKeys": list(geometry_keys),
            "mobaTopMenuStaticX": geometry.static_x,
            "mobaTopMenuWidth": geometry.width,
            "mobaTopMenuLabelY": geometry.label_y,
            "mobaTopMenuLabelFontSize": geometry.label_font_size,
            "mobaTopMenuGapAfter": geometry.gap_after,
        },
    )


def add_reference_top_menu(
    menu_bar: QMenuBar,
    item: GuiSecureCrtTopMenuItem | GuiMRemoteNgTopMenuItem,
    *,
    display_name: str,
    object_name: str,
) -> tuple[QMenu, QAction]:
    key_property, label_property, action_property = _REFERENCE_MENU_PROPERTIES[object_name]
    return _add_top_menu(
        menu_bar,
        item,
        display_name=display_name,
        object_name=object_name,
        properties={
            key_property: item.key,
            label_property: item.label,
            action_property: item.primary_action,
        },
    )


def add_primary_menu_action(
    menu: QMenu,
    label: str,
    *,
    display_name: str,
    family: str,
    key: str,
    operation: str,
    invoke: Callable[[str, str], None],
) -> None:
    action = _required_gui_value(
        menu.addAction(label),
        f"{display_name} primary menu action for {key}",
    )
    action.triggered.connect(lambda _checked=False: invoke(family, key))
    action.setProperty("menuActionKey", key)
    action.setProperty("menuActionFamily", family)
    action.setProperty("menuActionOperation", operation)


class WindowMenus:
    """Desktop menu configuration, action dispatch, and keyboard shortcuts."""

    if TYPE_CHECKING:
        design_select: QComboBox
        search_input: QLineEdit

        def add_split(self, direction: str) -> None: ...
        def add_mremoteng_tab_options(self, tools: QMenu) -> None: ...
        def close_current_tab(self) -> None: ...
        def connect_selected(self, dry_run: bool) -> None: ...
        def create_profile(self) -> None: ...
        def edit_selected_profile(self) -> None: ...
        def focus_find_control(self) -> None: ...
        def open_files_selected(self) -> None: ...
        def open_local_terminal_tab(self) -> None: ...
        def open_selected_layout(self) -> None: ...
        def populate_moba_macro_menu(self, menu: QMenu) -> None: ...
        def recover_previous_sessions(self) -> None: ...
        def refresh_profiles(self) -> None: ...
        def run_operator_action(self, callback: Callable[[], object]) -> None: ...
        def show_doctor(self) -> None: ...
        def show_external_tools_status(self, *_args) -> None: ...
        def show_key_manager_status(self, *_args) -> None: ...
        def show_moba_games_status(self, *_args) -> None: ...
        def show_moba_help_dialog(self, *_args) -> None: ...
        def show_moba_macros_status(self, *_args) -> None: ...
        def show_moba_settings_status(self, *_args) -> None: ...
        def show_moba_tools_status(self, *_args) -> None: ...
        def show_moba_x_server_status(self, *_args) -> None: ...
        def show_securecrt_script_status(self, *_args) -> None: ...

    def keyboard_shortcut_specs(self) -> list[dict[str, object]]:
        return [
            {
                "key": "refresh-profiles",
                "sequence": "Ctrl+R",
                "action_label": "Refresh profiles",
                "callback": self.refresh_profiles,
            },
            {
                "key": "new-profile",
                "sequence": "Ctrl+N",
                "action_label": "New profile",
                "callback": self.create_profile,
            },
            {
                "key": "edit-profile",
                "sequence": "Ctrl+E",
                "action_label": "Edit selected profile",
                "callback": self.edit_selected_profile,
            },
            {
                "key": "connect-selected",
                "sequence": "Ctrl+Return",
                "action_label": "Connect selected profile",
                "callback": lambda: self.connect_selected(False),
            },
            {
                "key": "new-local-terminal",
                "sequence": "Ctrl+T",
                "action_label": "New local terminal",
                "callback": self.open_local_terminal_tab,
            },
            {
                "key": "close-current-tab",
                "sequence": "Ctrl+W",
                "action_label": "Close current tab",
                "callback": self.close_current_tab,
            },
            {
                "key": "recover-previous-sessions",
                "sequence": "Ctrl+Shift+T",
                "action_label": "Recover previous sessions",
                "callback": self.recover_previous_sessions,
            },
            {
                "key": "split-horizontal",
                "sequence": "Ctrl+Shift+H",
                "action_label": "Split horizontal",
                "callback": lambda: self.add_split("horizontal"),
            },
            {
                "key": "split-vertical",
                "sequence": "Ctrl+Shift+V",
                "action_label": "Split vertical",
                "callback": lambda: self.add_split("vertical"),
            },
            {
                "key": "open-selected-layout",
                "sequence": "Ctrl+L",
                "action_label": "Open selected layout",
                "callback": self.open_selected_layout,
            },
            {
                "key": "find-log-text",
                "sequence": "Ctrl+F",
                "action_label": "Find log text",
                "callback": self.search_input.setFocus,
            },
        ]

    def create_keyboard_shortcuts(self) -> list[QShortcut]:
        shortcuts = []
        for spec in self.keyboard_shortcut_specs():
            shortcut = QShortcut(QKeySequence(str(spec["sequence"])), cast(QWidget, self))
            shortcut.setObjectName("presetKeyboardShortcut")
            shortcut.setProperty("presetKeyboardShortcutKey", str(spec["key"]))
            shortcut.setProperty("presetKeyboardShortcutSequence", str(spec["sequence"]))
            shortcut.setProperty("presetKeyboardShortcutActionLabel", str(spec["action_label"]))
            callback = spec["callback"]
            if not callable(callback):
                raise RuntimeError(
                    f"keyboard shortcut callback is unavailable: {spec['key']}"
                )
            shortcut.activated.connect(callback)
            shortcuts.append(shortcut)
        return shortcuts

    def build_menu_bar(self) -> None:
        self.main_menu_bar = _required_gui_value(
            cast(QMainWindow, self).menuBar(),
            "main menu bar",
        )
        self.main_menu_bar.setObjectName("mobaTopMenuBar")
        self.moba_top_menus: list[QMenu] = []
        self.moba_top_menu_actions: list[QAction] = []
        self.product_menu_callbacks = {
            "mobaxterm": {
                "terminal": self.open_local_terminal_tab,
                "sessions": lambda: self.connect_selected(False),
                "view": self.refresh_profiles,
                "x-server": self.show_moba_x_server_status,
                "tools": self.show_moba_tools_status,
                "games": self.show_moba_games_status,
                "settings": self.show_moba_settings_status,
                "macros": self.show_moba_macros_status,
                "help": self.show_doctor,
            },
            "securecrt": {
                "file": lambda: self.connect_selected(False),
                "edit": self.focus_find_control,
                "view": self.refresh_profiles,
                "options": self.edit_selected_profile,
                "transfer": self.open_files_selected,
                "script": self.show_securecrt_script_status,
                "tools": self.show_key_manager_status,
                "window": lambda: self.add_split("horizontal"),
                "help": self.show_moba_help_dialog,
            },
            "mremoteng": {
                "file": self.create_profile,
                "view": self.refresh_profiles,
                "connections": lambda: self.connect_selected(False),
                "tools": self.show_external_tools_status,
                "window": lambda: self.add_split("horizontal"),
                "help": self.show_moba_help_dialog,
            },
        }
        self.product_menu_operations = {
            "mobaxterm": {
                "terminal": "new-local-terminal",
                "sessions": "connect-selected",
                "view": "refresh-profiles",
                "x-server": "x-server-status",
                "tools": "tools-status",
                "games": "games-status",
                "settings": "settings-status",
                "macros": "manage-macros",
                "help": "run-doctor",
            },
            "securecrt": {
                "file": "connect-selected",
                "edit": "focus-find",
                "view": "refresh-profiles",
                "options": "edit-selected-profile",
                "transfer": "open-sftp",
                "script": "script-status",
                "tools": "key-manager-status",
                "window": "split-horizontal",
                "help": "help-topics",
            },
            "mremoteng": {
                "file": "create-profile",
                "view": "refresh-profiles",
                "connections": "connect-selected",
                "tools": "external-tools-status",
                "window": "split-horizontal",
                "help": "help-topics",
            },
        }

        def invoke_menu_action(family: str, key: str) -> None:
            self.run_product_menu_action(family, key)

        for moba_item in gui_design_moba_top_menu_items():
            menu, menu_action = add_moba_top_menu(
                self.main_menu_bar,
                moba_item,
                gui_design_moba_top_menu_geometry_for(moba_item.key),
                [entry.key for entry in gui_design_moba_top_menu_geometry()],
            )
            self.moba_top_menus.append(menu)
            self.moba_top_menu_actions.append(menu_action)
            if moba_item.key == "sessions":
                menu.addAction("New session", self.create_profile)
            if moba_item.key == "view":
                self.view_menu = menu
            if moba_item.key not in self.product_menu_callbacks["mobaxterm"]:
                raise RuntimeError(
                    f"missing Moba top-menu handler: {moba_item.key}"
                )
            add_primary_menu_action(
                menu,
                moba_item.primary_action,
                display_name="Moba",
                family="mobaxterm",
                key=moba_item.key,
                operation=self.product_menu_operations["mobaxterm"][moba_item.key],
                invoke=invoke_menu_action,
            )
            if moba_item.key == "macros":
                menu.aboutToShow.connect(lambda menu=menu: self.populate_moba_macro_menu(menu))

        self.securecrt_top_menus: list[QMenu] = []
        self.securecrt_top_menu_actions: list[QAction] = []
        self.mremoteng_top_menus: list[QMenu] = []
        self.mremoteng_top_menu_actions: list[QAction] = []
        reference_menus = (
            (
                "securecrt",
                "SecureCRT",
                "secureCrtTopMenu",
                gui_design_securecrt_top_chrome,
                self.securecrt_top_menus,
                self.securecrt_top_menu_actions,
            ),
            (
                "mremoteng",
                "mRemoteNG",
                "mRemoteNgTopMenu",
                gui_design_mremoteng_top_chrome,
                self.mremoteng_top_menus,
                self.mremoteng_top_menu_actions,
            ),
        )
        for family, display_name, object_name, top_chrome, menus, menu_actions in reference_menus:
            for item in top_chrome().menu_items:
                menu, menu_action = add_reference_top_menu(
                    self.main_menu_bar, item, display_name=display_name, object_name=object_name,
                )
                menus.append(menu)
                menu_actions.append(menu_action)
                if item.key not in self.product_menu_callbacks[family]:
                    raise RuntimeError(f"missing {display_name} top-menu handler: {item.key}")
                add_primary_menu_action(
                    menu,
                    item.primary_action,
                    display_name=display_name,
                    family=family,
                    key=item.key,
                    operation=self.product_menu_operations[family][item.key],
                    invoke=invoke_menu_action,
                )
                if family == "mremoteng" and item.key == "tools":
                    self.add_mremoteng_tab_options(menu)

    def run_product_menu_action(self, family: str, action_key: str) -> None:
        callbacks = self.product_menu_callbacks.get(family)
        callback = callbacks.get(action_key) if callbacks is not None else None
        if callback is None:
            raise RuntimeError(f"missing {family} menu callback: {action_key}")
        self.run_operator_action(callback)

    def populate_view_design_menu(self) -> None:
        design_menu = QMenu("Design preset", self.view_menu)
        self.view_menu.addMenu(design_menu)
        for preset in GUI_DESIGN_PRESETS:
            design_menu.addAction(
                preset.label,
                lambda _checked=False, preset_id=preset.id: self.set_design_preset(preset_id),
            )

    def set_design_preset(self, preset_id: str) -> None:
        index = self.design_select.findData(preset_id)
        if index >= 0:
            self.design_select.setCurrentIndex(index)

    def configure_menu_bar_for_design(self, preset: GuiDesignPreset) -> None:
        is_moba = preset.id == "mobaxterm"
        is_securecrt = preset.id == "securecrt"
        is_mremoteng = preset.id == "mremoteng"
        securecrt_chrome = gui_design_securecrt_top_chrome()
        mremoteng_chrome = gui_design_mremoteng_top_chrome()
        menu_bar = self.main_menu_bar
        menu_bar.setVisible(is_moba or is_securecrt or is_mremoteng)
        menu_bar.setObjectName(
            "mobaTopMenuBar"
            if is_moba
            else "secureCrtMenuBar"
            if is_securecrt
            else "mRemoteNgMenuBar"
            if is_mremoteng
            else "productMenuBar"
        )
        menu_bar.setProperty("designPreset", preset.id)
        menu_bar.setProperty(
            "secureCrtTopMenuKeys",
            [item.key for item in securecrt_chrome.menu_items] if is_securecrt else [],
        )
        menu_bar.setProperty(
            "secureCrtTopMenuLabels",
            [item.label for item in securecrt_chrome.menu_items] if is_securecrt else [],
        )
        menu_bar.setProperty(
            "secureCrtTopToolbarKeys",
            [action.key for action in securecrt_chrome.toolbar_actions] if is_securecrt else [],
        )
        menu_bar.setProperty("secureCrtWindowTitle", securecrt_chrome.window_title if is_securecrt else "")
        menu_bar.setProperty(
            "mRemoteNgTopMenuKeys",
            [item.key for item in mremoteng_chrome.menu_items] if is_mremoteng else [],
        )
        menu_bar.setProperty(
            "mRemoteNgTopMenuLabels",
            [item.label for item in mremoteng_chrome.menu_items] if is_mremoteng else [],
        )
        menu_bar.setProperty(
            "mRemoteNgTopToolbarKeys",
            [action.key for action in mremoteng_chrome.toolbar_actions] if is_mremoteng else [],
        )
        menu_bar.setProperty("mRemoteNgWindowTitle", mremoteng_chrome.window_title if is_mremoteng else "")
        for action in self.moba_top_menu_actions:
            action.setVisible(is_moba)
        for action in self.securecrt_top_menu_actions:
            action.setVisible(is_securecrt)
        for action in self.mremoteng_top_menu_actions:
            action.setVisible(is_mremoteng)
