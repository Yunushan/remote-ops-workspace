from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMenuBar

from .gui_designs import (
    GuiMobaTopMenuGeometry,
    GuiMobaTopMenuItem,
    GuiMRemoteNgTopMenuItem,
    GuiSecureCrtTopMenuItem,
)
from .gui_values import _required_gui_value

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
