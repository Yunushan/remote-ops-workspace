from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import gui_preset_properties
from .gui_designs import (
    gui_design_home_tab_label,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_home_welcome_geometry,
    gui_design_workspace_surface,
)
from .gui_dialogs import _literal_label
from .gui_values import _widget_style

if TYPE_CHECKING:
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QStyle, QTabWidget

    from .gui_designs import GuiPresetHomeSearchRoute, GuiWorkspaceSurface


class WindowHome:
    """Build and route the desktop welcome page across design presets."""

    if TYPE_CHECKING:
        tabs: QTabWidget
        quick_connect: QLineEdit

        def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int: ...
        def apply_moba_tab_chrome(
            self, index: int, *, key: str, icon_key: str, tooltip: str, closeable: bool,
        ) -> None: ...
        def build_product_workflow_evidence(self) -> QFrame: ...
        def build_product_workspace_surface_evidence(self, surface: GuiWorkspaceSurface) -> QFrame: ...
        def connect_selected(self, dry_run: bool) -> None: ...
        def create_profile(self) -> None: ...
        def current_design_id(self) -> str: ...
        def current_design_is_moba(self) -> bool: ...
        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon: ...
        def open_local_terminal_tab(self) -> None: ...
        def recover_previous_sessions(self) -> None: ...
        def run_operator_action(self, callback: Callable[[], object]) -> None: ...
        def run_quick_connect(self) -> None: ...
        def standard_icon(self, icon_name: str) -> QStyle.StandardPixmap: ...

    def configure_welcome_responsiveness(self) -> None:
        scroll = getattr(self, "welcome_scroll", None)
        panel = getattr(self, "welcome_panel", None)
        if scroll is None or panel is None or scroll.widget() is None:
            return
        content_layout = scroll.widget().layout()
        if content_layout is None:
            return
        margins = content_layout.contentsMargins()
        available = max(
            0,
            scroll.viewport().width()
            - margins.left()
            - margins.right()
            # Reserve an additional gutter for the native style frame and
            # scrollbar rounding at the 1024 px support boundary.
            - 16,
        )
        if available <= 0:
            return
        preferred = int(panel.property("welcomePreferredWidth") or 0)
        maximum = int(panel.property("welcomeMaximumWidth") or preferred)
        minimum_width = min(preferred, available)
        maximum_width = max(minimum_width, min(maximum, available))
        panel.setMinimumWidth(minimum_width)
        panel.setMaximumWidth(maximum_width)

    def home_search_route_widgets(self, route: GuiPresetHomeSearchRoute) -> list[QWidget]:
        window = cast(QWidget, self)
        container = window.findChild(QWidget, route.container_object)
        home_search = window.findChild(QLineEdit, route.home_search_object)
        entry_search = window.findChild(QLineEdit, route.entry_search_object)
        recent_labels = (
            container.findChildren(QLabel, route.recent_label_object)
            if container is not None
            else []
        )
        candidates = [window, self.tabs, container, home_search, entry_search, *recent_labels]
        route_widgets = []
        seen: set[int] = set()
        for widget in candidates:
            if widget is None:
                continue
            widget_id = id(widget)
            if widget_id in seen:
                continue
            seen.add(widget_id)
            route_widgets.append(widget)
        return route_widgets

    def apply_home_search_route_for_design(self, route: GuiPresetHomeSearchRoute | None) -> None:
        window = cast(QWidget, self)
        for widget in [
            window,
            self.tabs,
            *window.findChildren(QWidget, "welcomePanel"),
            *window.findChildren(QWidget, "mobaHomeWelcomeSurface"),
            *window.findChildren(QLineEdit, "homeSearch"),
            *window.findChildren(QLineEdit, "quickConnect"),
            *window.findChildren(QLineEdit, "secureCrtSessionFilter"),
            *window.findChildren(QLineEdit, "termiusHostSearch"),
            *window.findChildren(QLineEdit, "remminaProfileFilter"),
            *window.findChildren(QLineEdit, "mRemoteNgDocumentFilter"),
        ]:
            gui_preset_properties.clear_preset_home_search_route_properties(widget)
        if route is None:
            return
        container = window.findChild(QWidget, route.container_object)
        home_search = window.findChild(QLineEdit, route.home_search_object)
        entry_search = window.findChild(QLineEdit, route.entry_search_object)
        action_labels = (
            [
                button.text()
                for button in container.findChildren(QPushButton)
                if button.text() in route.expected_home_actions
            ]
            if container is not None
            else []
        )
        recent_labels = (
            [label.text() for label in container.findChildren(QLabel, route.recent_label_object)]
            if container is not None
            else []
        )
        captured_placeholder = home_search.placeholderText() if home_search is not None else ""
        captured_text = home_search.text() if home_search is not None else ""
        captured_entry_placeholder = entry_search.placeholderText() if entry_search is not None else ""
        captured_entry_text = entry_search.text() if entry_search is not None else ""
        if home_search is not None:
            home_search.setProperty(route.placeholder_property, route.placeholder_text)
        if entry_search is not None:
            entry_search.setProperty(route.entry_placeholder_property, route.entry_placeholder_text)
        for widget in self.home_search_route_widgets(route):
            gui_preset_properties.apply_preset_home_search_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_placeholder_property, captured_placeholder)
            widget.setProperty(route.captured_entry_placeholder_property, captured_entry_placeholder)
            widget.setProperty(route.captured_text_property, captured_text)
            widget.setProperty(route.captured_entry_text_property, captured_entry_text)
            widget.setProperty(route.captured_actions_property, action_labels)
            widget.setProperty(route.captured_recent_labels_property, recent_labels)
            widget.setProperty(route.captured_recent_count_property, len(recent_labels))

    def add_welcome_tab(self, *, select: bool | None = None) -> None:
        surface = gui_design_workspace_surface(self.current_design_id())
        self.home_action_callbacks = self.home_action_callbacks_for_design()
        box = QWidget()
        box.setObjectName("welcomeHome")
        box.setProperty("designPreset", self.current_design_id())
        root_layout = QVBoxLayout(box)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("welcomeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.welcome_scroll = scroll
        content = QWidget()
        content.setObjectName("welcomeContent")
        content.setMinimumWidth(0)
        content.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        scroll.setWidget(content)
        root_layout.addWidget(scroll)
        layout.addStretch(1)

        if self.current_design_is_moba():
            panel = self.build_moba_home_welcome(surface)
            self.welcome_panel = panel
            layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addStretch(2)
            index = self.add_workspace_tab(
                box,
                gui_design_home_tab_label(self.current_design_id()),
                select=self.tabs.count() == 0 if select is None else select,
                role="home",
            )
            self.apply_moba_tab_chrome(
                index,
                key="home",
                icon_key="home",
                tooltip="Home",
                closeable=False,
            )
            QTimer.singleShot(0, self.configure_welcome_responsiveness)
            return

        panel = QFrame()
        panel.setObjectName("welcomePanel")
        # Product presets are workspace-led in the reference applications
        # (connected document/SFTP/viewer first, inventory landing page
        # second).  Give those live surfaces the width they need instead
        # of constraining them to the old centered hero-card width.
        product_workspace_led = self.current_design_id() in {
            "securecrt",
            "termius",
            "remmina",
            "mremoteng",
        }
        panel_width = 1120 if product_workspace_led else 780
        panel.setProperty("welcomePreferredWidth", panel_width - 160)
        panel.setProperty("welcomeMaximumWidth", panel_width)
        panel.setMinimumWidth(0)
        panel.setMaximumWidth(panel_width)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.welcome_panel = panel
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(13)

        early_workspace_evidence = None
        early_workflow = None
        if product_workspace_led:
            early_workspace_evidence = self.build_product_workspace_surface_evidence(surface)
            panel_layout.addWidget(early_workspace_evidence)
            early_workflow = self.build_product_workflow_evidence()
            panel_layout.addWidget(early_workflow)

        title_row = QHBoxLayout()
        title_row.setSpacing(18)
        title_row.addStretch(1)
        logo = QLabel(">_")
        logo.setObjectName("welcomeLogo")
        logo.setFixedSize(QSize(64, 48))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_column = QVBoxLayout()
        title_column.setSpacing(3)
        title = _literal_label(surface.title)
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        subtitle = _literal_label(surface.subtitle)
        subtitle.setObjectName("workspaceSurfaceSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        title_row.addWidget(logo)
        title_row.addLayout(title_column)
        title_row.addStretch(1)
        panel_layout.addLayout(title_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(96)
        action_row.addStretch(1)
        primary_action, secondary_action = surface.home_actions[:2]
        start_button = QPushButton(primary_action)
        start_button.setObjectName("mobaHomePrimaryAction")
        start_button.setProperty("homeActionKey", "primary")
        start_button.setProperty(
            "homeActionOperation",
            self.home_action_operations["primary"],
        )
        start_button.setIcon(
            _widget_style(cast(QWidget, self)).standardIcon(
                self.standard_icon("SP_DialogApplyButton")
            )
        )
        start_button.setMinimumWidth(200)
        recover_button = QPushButton(secondary_action)
        recover_button.setObjectName("mobaHomeAction")
        recover_button.setProperty("homeActionKey", "secondary")
        recover_button.setProperty(
            "homeActionOperation",
            self.home_action_operations["secondary"],
        )
        recover_button.setIcon(
            _widget_style(cast(QWidget, self)).standardIcon(
                self.standard_icon("SP_BrowserReload")
            )
        )
        recover_button.setMinimumWidth(218)
        start_button.clicked.connect(
            lambda _checked=False: self.run_home_action("primary")
        )
        recover_button.clicked.connect(
            lambda _checked=False: self.run_home_action("secondary")
        )
        self.home_primary_action = start_button
        self.home_secondary_action = recover_button
        action_row.addWidget(start_button)
        action_row.addWidget(recover_button)
        action_row.addStretch(1)
        panel_layout.addLayout(action_row)

        search = QLineEdit()
        search.setObjectName("homeSearch")
        search.setPlaceholderText(surface.home_search_placeholder)
        search.setMinimumWidth(405)
        search.setMaximumWidth(405)
        search.returnPressed.connect(lambda: self.run_home_search(search.text()))
        panel_layout.addWidget(search, 0, Qt.AlignmentFlag.AlignCenter)

        if early_workflow is None:
            workflow = self.build_product_workflow_evidence()
            panel_layout.addWidget(workflow)

        if early_workspace_evidence is None:
            workspace_evidence = self.build_product_workspace_surface_evidence(surface)
            panel_layout.addWidget(workspace_evidence)

        recent_title = _literal_label(
            f"Recent {gui_design_home_tab_label(self.current_design_id()).lower()}"
        )
        recent_title.setObjectName("recentSessionsTitle")
        recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_title.setContentsMargins(0, 9, 0, 0)
        panel_layout.addWidget(recent_title)

        recent_grid = QHBoxLayout()
        recent_grid.setSpacing(44)
        for column in surface.recent_columns:
            column_layout = QVBoxLayout()
            column_layout.setSpacing(5)
            for item in column:
                label = _literal_label(item)
                label.setObjectName("recentSessionsLabel")
                column_layout.addWidget(label)
            recent_grid.addLayout(column_layout)
        panel_layout.addLayout(recent_grid)

        promo = _literal_label(surface.footer)
        promo.setObjectName("homePromo")
        promo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        promo.setContentsMargins(0, 12, 0, 0)
        panel_layout.addWidget(promo)

        layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(2)
        index = self.add_workspace_tab(
            box,
            gui_design_home_tab_label(self.current_design_id()),
            select=self.tabs.count() == 0 if select is None else select,
            role="home",
        )
        QTimer.singleShot(0, self.configure_welcome_responsiveness)

    def home_action_callbacks_for_design(
        self,
    ) -> dict[str, Callable[[], object]]:
        if self.current_design_id() in {"native", "mobaxterm"}:
            self.home_action_operations = {
                "primary": "open-local-terminal",
                "secondary": "recover-previous-sessions",
            }
            return {
                "primary": self.open_local_terminal_tab,
                "secondary": self.recover_previous_sessions,
            }
        self.home_action_operations = {
            "primary": "connect-selected",
            "secondary": "create-profile",
        }
        return {
            "primary": lambda: self.connect_selected(False),
            "secondary": self.create_profile,
        }

    def run_home_action(self, action_key: str) -> None:
        callback = self.home_action_callbacks.get(action_key)
        if callback is None:
            raise RuntimeError(f"missing home action callback: {action_key}")
        self.run_operator_action(callback)

    def build_moba_home_welcome(self, surface: GuiWorkspaceSurface) -> QFrame:
        chrome = gui_design_moba_home_welcome_chrome()
        geometry = gui_design_moba_home_welcome_geometry()
        panel = QFrame()
        panel.setObjectName("mobaHomeWelcomeSurface")
        panel.setProperty("designPreset", "mobaxterm")
        panel.setProperty("mobaHomeTitle", chrome.title)
        panel.setProperty("mobaHomeSubtitle", chrome.subtitle)
        panel.setProperty("mobaHomeSearchWidth", chrome.search_width)
        panel.setProperty("mobaHomeRecentTitle", chrome.recent_title)
        panel.setProperty("mobaHomeActionSpacing", chrome.action_spacing)
        panel.setProperty("mobaHomeGeometryRenderSource", geometry.render_source)
        panel.setProperty("mobaHomeCenterSideMargin", geometry.center_side_margin)
        panel.setProperty("mobaHomeHeroMinY", geometry.hero_min_y)
        panel.setProperty("mobaHomeHeroHeight", geometry.hero_height)
        panel.setProperty("mobaHomeLogoSize", geometry.logo_size)
        panel.setProperty("mobaHomeTitleGap", geometry.title_gap)
        panel.setProperty("mobaHomeTitleYOffset", geometry.title_y_offset)
        panel.setProperty("mobaHomeSubtitleYOffset", geometry.subtitle_y_offset)
        panel.setProperty("mobaHomeButtonYOffset", geometry.button_y_offset)
        panel.setProperty("mobaHomePrimaryActionWidth", geometry.primary_width)
        panel.setProperty("mobaHomeSecondaryActionWidth", geometry.secondary_width)
        panel.setProperty("mobaHomeActionGap", geometry.action_gap)
        panel.setProperty("mobaHomeButtonHeight", geometry.button_height)
        panel.setProperty("mobaHomeSearchYGap", geometry.search_y_gap)
        panel.setProperty("mobaHomeSearchHeight", geometry.search_height)
        panel.setProperty("mobaHomeRecentYGap", geometry.recent_y_gap)
        panel.setProperty("mobaHomeRecentItemStep", geometry.recent_item_step)
        panel.setProperty("mobaHomeFooterYOffset", geometry.footer_y_offset)
        panel.setProperty("welcomePreferredWidth", chrome.surface_width)
        panel.setProperty(
            "welcomeMaximumWidth",
            chrome.surface_width + geometry.live_max_extra_width,
        )
        panel.setMinimumWidth(0)
        panel.setMaximumWidth(chrome.surface_width + geometry.live_max_extra_width)
        panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(geometry.live_layout_spacing)

        title_row = QHBoxLayout()
        title_row.setSpacing(geometry.live_title_row_spacing)
        title_row.addStretch(1)
        logo = QLabel()
        logo.setObjectName("mobaHomeLogo")
        logo.setProperty("mobaHomeIconKey", chrome.icon_key)
        logo.setProperty("mobaHomeLogoSize", geometry.logo_size)
        logo.setProperty("mobaHomeLogoBoxWidth", geometry.live_logo_box_width)
        logo.setProperty("mobaHomeLogoBoxHeight", geometry.live_logo_box_height)
        logo.setProperty("mobaHomeLogoPixmapSize", geometry.live_logo_pixmap_size)
        logo.setFixedSize(QSize(geometry.live_logo_box_width, geometry.live_logo_box_height))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(
            self.moba_ribbon_icon(chrome.icon_key, "#1a1a1a", size=geometry.live_logo_pixmap_size).pixmap(
                QSize(geometry.live_logo_pixmap_size, geometry.live_logo_pixmap_size)
            )
        )
        title_column = QVBoxLayout()
        title_column.setSpacing(geometry.live_title_column_spacing)
        title = _literal_label(chrome.title)
        title.setObjectName("mobaHomeTitle")
        title.setProperty("mobaHomeTitleFontSize", geometry.title_font_size)
        title.setProperty("mobaHomeTitleYOffset", geometry.title_y_offset)
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        subtitle = _literal_label(chrome.subtitle)
        subtitle.setObjectName("mobaHomeSubtitle")
        subtitle.setProperty("mobaHomeSubtitleFontSize", geometry.subtitle_font_size)
        subtitle.setProperty("mobaHomeSubtitleYOffset", geometry.subtitle_y_offset)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        title_row.addWidget(logo)
        title_row.addLayout(title_column)
        title_row.addStretch(1)
        panel_layout.addLayout(title_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(geometry.action_gap)
        action_row.addStretch(1)
        primary_action, secondary_action = surface.home_actions[:2]
        start_button = QPushButton(primary_action)
        start_button.setObjectName("mobaHomePrimaryAction")
        start_button.setProperty("mobaHomeActionKey", "primary")
        start_button.setProperty("homeActionKey", "primary")
        start_button.setProperty(
            "homeActionOperation",
            self.home_action_operations["primary"],
        )
        start_button.setProperty("mobaHomeActionIconKey", chrome.primary_action_icon_key)
        start_button.setProperty("mobaHomeActionStaticWidth", geometry.primary_width)
        start_button.setProperty("mobaHomeActionStaticHeight", geometry.button_height)
        start_button.setProperty("mobaHomeActionIconX", geometry.button_icon_x)
        start_button.setProperty("mobaHomeActionIconY", geometry.button_icon_y)
        start_button.setProperty("mobaHomeActionIconSize", geometry.button_icon_size)
        start_button.setIcon(
            self.moba_ribbon_icon(chrome.primary_action_icon_key, "#4db7ff", size=geometry.button_icon_size)
        )
        start_button.setMinimumWidth(geometry.primary_width)
        start_button.setFixedHeight(geometry.button_height)
        recover_button = QPushButton(secondary_action)
        recover_button.setObjectName("mobaHomeAction")
        recover_button.setProperty("mobaHomeActionKey", "secondary")
        recover_button.setProperty("homeActionKey", "secondary")
        recover_button.setProperty(
            "homeActionOperation",
            self.home_action_operations["secondary"],
        )
        recover_button.setProperty("mobaHomeActionIconKey", chrome.secondary_action_icon_key)
        recover_button.setProperty("mobaHomeActionStaticWidth", geometry.secondary_width)
        recover_button.setProperty("mobaHomeActionStaticHeight", geometry.button_height)
        recover_button.setProperty("mobaHomeActionIconX", geometry.button_icon_x)
        recover_button.setProperty("mobaHomeActionIconY", geometry.button_icon_y)
        recover_button.setProperty("mobaHomeActionIconSize", geometry.button_icon_size)
        recover_button.setIcon(
            self.moba_ribbon_icon(chrome.secondary_action_icon_key, "#35d7c7", size=geometry.button_icon_size)
        )
        recover_button.setMinimumWidth(geometry.secondary_width)
        recover_button.setFixedHeight(geometry.button_height)
        start_button.clicked.connect(
            lambda _checked=False: self.run_home_action("primary")
        )
        recover_button.clicked.connect(
            lambda _checked=False: self.run_home_action("secondary")
        )
        self.home_primary_action = start_button
        self.home_secondary_action = recover_button
        action_row.addWidget(start_button)
        action_row.addWidget(recover_button)
        action_row.addStretch(1)
        panel_layout.addLayout(action_row)

        search = QLineEdit()
        search.setObjectName("homeSearch")
        search.setProperty("mobaHomeSearchPlaceholder", surface.home_search_placeholder)
        search.setProperty("mobaHomeSearchWidth", chrome.search_width)
        search.setProperty("mobaHomeSearchHeight", geometry.search_height)
        search.setProperty("mobaHomeSearchTextX", geometry.search_text_x)
        search.setProperty("mobaHomeSearchTextY", geometry.search_text_y)
        search.setProperty("mobaHomeSearchFontSize", geometry.search_font_size)
        search.setPlaceholderText(surface.home_search_placeholder)
        search.setMinimumWidth(chrome.search_width)
        search.setMaximumWidth(chrome.search_width)
        search.setFixedHeight(geometry.search_height)
        search.returnPressed.connect(lambda: self.run_home_search(search.text()))
        panel_layout.addWidget(search, 0, Qt.AlignmentFlag.AlignCenter)

        recent_title = QLabel(chrome.recent_title)
        recent_title.setObjectName("recentSessionsTitle")
        recent_title.setProperty("mobaHomeRecentTitle", chrome.recent_title)
        recent_title.setProperty("mobaHomeRecentTitleFontSize", geometry.recent_title_font_size)
        recent_title.setProperty("mobaHomeRecentTitleTopMargin", geometry.live_recent_title_top_margin)
        recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_title.setContentsMargins(0, geometry.live_recent_title_top_margin, 0, 0)
        panel_layout.addWidget(recent_title)

        recent_grid = QHBoxLayout()
        recent_grid.setSpacing(geometry.live_recent_column_spacing)
        for column_index, column in enumerate(surface.recent_columns):
            column_layout = QVBoxLayout()
            column_layout.setSpacing(geometry.live_recent_row_spacing)
            for row_index, item in enumerate(column):
                label = _literal_label(item)
                label.setObjectName("mobaRecentSession")
                label.setProperty("mobaHomeRecentColumn", column_index)
                label.setProperty("mobaHomeRecentRow", row_index)
                label.setProperty("mobaHomeRecentItemStep", geometry.recent_item_step)
                label.setProperty("mobaHomeRecentColumnPadding", geometry.recent_column_padding)
                column_layout.addWidget(label)
            recent_grid.addLayout(column_layout)
        panel_layout.addLayout(recent_grid)

        footer = _literal_label(surface.footer)
        footer.setObjectName("mobaHomeFooter")
        footer.setProperty("mobaHomeFooter", surface.footer)
        footer.setProperty("mobaHomeFooterYOffset", geometry.footer_y_offset)
        footer.setProperty("mobaHomeFooterFontSize", geometry.footer_font_size)
        footer.setProperty("mobaHomeFooterTopMargin", geometry.live_footer_top_margin)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setContentsMargins(0, geometry.live_footer_top_margin, 0, 0)
        panel_layout.addWidget(footer)
        return panel

    def run_home_search(self, text: str) -> None:
        self.quick_connect.setText(text)
        self.run_quick_connect()
