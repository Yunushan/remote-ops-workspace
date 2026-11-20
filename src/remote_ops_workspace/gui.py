from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import quick_connect as _quick_connect
from .doctor import run_doctor
from .file_transfer import SftpQueueItem
from .gui_designs import (
    PRODUCT_GUI_PRESET_IDS,
    GuiDesignPreset,
    get_gui_design_preset,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry_for,
    gui_design_moba_rail_items,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_stack_geometry,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_selection_route,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_toolbar_actions,
)
from .gui_lifecycle import ProcessStopPolicy
from .gui_values import _required_gui_value, _safe_tooltip_html, _widget_style
from .launcher import LauncherError, ssh_identity_agent
from .layouts import Layout, LayoutStore
from .moba_connected import (
    MobaConnectedSessionState,
    build_moba_connected_session_state,
    moba_connected_profile_label,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_window_title,
)
from .moba_smartcards import (
    update_smartcard_profile_key,
)
from .moba_ssh_browser import load_moba_ssh_browser_preferences
from .models import Profile
from .process_status import ProcessStatusError
from .smartcard_keys import PINNED_SMARTCARD_KEY
from .storage import ProfileStore
from .terminal import TerminalPanePlan, openssh_command_without_windows_connection_sharing
from .terminal import terminal_plan_for_profile as terminal_plan_for_profile
from .terminal_output import _ByteChunkQueue  # noqa: F401 - existing queue seam

# Qt requires QApplication to outlive every widget. Keep a process-wide Python
# reference so short-lived windows and test fixtures cannot collect its wrapper.
_QT_APPLICATION_REF: object | None = None






class GuiDependencyError(RuntimeError):
    pass


# Keep the Quick Connect names available to existing GUI callers.
QUICK_CONNECT_PROTOCOLS = _quick_connect.QUICK_CONNECT_PROTOCOLS
QUICK_CONNECT_DEFAULT_PORTS = _quick_connect.QUICK_CONNECT_DEFAULT_PORTS
QuickConnectCandidate = _quick_connect.QuickConnectCandidate
quick_connect_candidates = _quick_connect.quick_connect_candidates
profile_quick_connect_matches = _quick_connect.profile_quick_connect_matches
parse_quick_connect_profile = _quick_connect.parse_quick_connect_profile
quick_connect_parsed_endpoint_candidate = _quick_connect.quick_connect_parsed_endpoint_candidate
quick_connect_url_candidate = _quick_connect.quick_connect_url_candidate
parse_quick_connect_endpoint = _quick_connect.parse_quick_connect_endpoint
quick_connect_is_explicit = _quick_connect.quick_connect_is_explicit
quick_connect_is_host_like = _quick_connect.quick_connect_is_host_like
looks_like_url = _quick_connect.looks_like_url
quick_connect_profile_name = _quick_connect.quick_connect_profile_name


def application_icon_path() -> Path:
    """Return the packaged vector icon used by the desktop window and taskbar."""

    return Path(__file__).resolve().parent / "assets" / "remote_ops_workspace.svg"


def set_windows_taskbar_app_id() -> None:
    """Keep the Windows taskbar grouped under the product icon rather than Python's default."""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Yunushan.RemoteOpsWorkspace.Desktop"
        )
    except (AttributeError, OSError):
        # The Qt window icon still works when a restricted Windows shell denies this hint.
        return


def create_main_window(
    argv: list[str] | None = None,
    *,
    show: bool = False,
    preview_samples: bool = False,
):
    global _QT_APPLICATION_REF

    try:
        from PyQt6.QtCore import (
            QPoint,
            QSize,
            Qt,
            QTimer,
        )
        from PyQt6.QtGui import (
            QClipboard,
            QColor,
            QFont,
            QGuiApplication,
            QIcon,
            QKeySequence,
            QPainter,
            QPen,
            QPixmap,
            QShortcut,
            QTextCursor,
        )
        from PyQt6.QtWidgets import (
            QApplication,
            QDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMenu,
            QMessageBox,
            QSplitter,
            QStackedWidget,
            QStatusBar,
            QStyle,
            QTextEdit,
            QToolButton,
            QTreeWidget,
            QTreeWidgetItem,
            QVBoxLayout,
            QWidget,
        )

        from .gui_terminal import TerminalPane, TerminalTextEdit
    except Exception as exc:  # pragma: no cover - optional dependency
        raise GuiDependencyError("PyQt6 is not installed. Install with: pip install -e '.[desktop]'") from exc

    # Imported only after Qt is available so CLI commands keep working without it.
    from . import gui_preset_properties
    from .gui_connected import (
        ConnectedGuiServices,
        ConnectedMainWindow,
        ConnectedSessionPanel,
        ConnectedSftpDock,
        create_moba_connected_classes,
    )
    from .gui_design_activation import WindowDesign
    from .gui_dialogs import (
        DialogServices,
        LayoutDialog,
        LiteralTextEdit,
        ProfileDialog,
        ProfileImportPreviewDialog,
        TransferQueueDialog,
        WorkflowDialog,
        _literal_label,
    )
    from .gui_home import WindowHome
    from .gui_icons import (
        draw_moba_ribbon_icon,
        draw_mremoteng_toolbar_icon,
        draw_securecrt_toolbar_icon,
    )
    from .gui_layouts import SavedLayoutActions
    from .gui_menus import WindowMenus
    from .gui_mremoteng import MRemoteNgWorkspace
    from .gui_operator_workflows import OperatorWorkflows
    from .gui_product_workspace import ProductWorkspaceContent
    from .gui_profile_actions import ProfileActions
    from .gui_profile_tree import ProfileTree
    from .gui_reference_tabs import ReferenceTabs
    from .gui_remmina import RemminaWorkspace
    from .gui_securecrt import SecureCrtWorkspace
    from .gui_session_tabs import SessionTabActions
    from .gui_smartcards import SmartCardDialog
    from .gui_terminal_lifecycle import TerminalLifecycle
    from .gui_termius import TermiusWorkspace
    from .gui_toolbars import WindowToolbars
    from .gui_workspace import MobaRailLabel, MobaWorkspaceTabBar, ResponsiveWorkspaceTabs
    from .gui_workspace_tabs import WorkspaceTabs

    def _application_clipboard() -> QClipboard:
        return _required_gui_value(QApplication.clipboard(), "application clipboard")

    def _application_instance() -> QApplication:
        instance = QApplication.instance()
        if not isinstance(instance, QApplication):
            raise RuntimeError("required GUI value is unavailable: Qt application")
        return instance


    def _literal_message_box(
        parent: QWidget | None,
        icon: QMessageBox.Icon,
        title: object,
        message: object,
        *,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox.StandardButton:
        """Show untrusted names, paths and errors without Qt AutoText interpretation."""

        box = QMessageBox(parent)
        box.setIcon(icon)
        box.setWindowTitle(str(title))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(str(message))
        box.setStandardButtons(buttons)
        if default_button is not None:
            box.setDefaultButton(default_button)
        return QMessageBox.StandardButton(box.exec())

    def _dialog_screen(parent):
        if parent is not None:
            screen = parent.screen()
            if screen is not None:
                return screen
        return QApplication.primaryScreen()

    def _size_dialog_for_parent_screen(
        dialog: QDialog,
        parent,
        *,
        maximum_width: int,
        maximum_height: int,
        minimum_width: int = 320,
        minimum_height: int = 320,
    ) -> None:
        """Keep a dialog's initial and minimum size inside its parent's screen."""

        screen = _dialog_screen(parent)
        available = screen.availableGeometry() if screen is not None else None
        target_width = (
            min(maximum_width, max(1, available.width() - 48))
            if available is not None
            else maximum_width
        )
        target_height = (
            min(maximum_height, max(1, available.height() - 80))
            if available is not None
            else maximum_height
        )
        dialog.setMinimumSize(
            min(minimum_width, target_width),
            min(minimum_height, target_height),
        )
        dialog.resize(target_width, target_height)

    def _clamp_dialog_frame_to_parent_screen(dialog: QDialog) -> None:
        screen = _dialog_screen(dialog.parentWidget())
        if screen is None:
            return
        available = screen.availableGeometry()
        frame = dialog.frameGeometry()
        client = dialog.geometry()
        frame_width = max(0, frame.width() - client.width())
        frame_height = max(0, frame.height() - client.height())
        maximum_client_width = max(1, available.width() - frame_width)
        maximum_client_height = max(1, available.height() - frame_height)
        if dialog.width() > maximum_client_width or dialog.height() > maximum_client_height:
            dialog.resize(
                min(dialog.width(), maximum_client_width),
                min(dialog.height(), maximum_client_height),
            )
        frame = dialog.frameGeometry()
        left = min(
            max(frame.left(), available.left()),
            available.right() - frame.width() + 1,
        )
        top = min(
            max(frame.top(), available.top()),
            available.bottom() - frame.height() + 1,
        )
        dialog.move(dialog.pos() + QPoint(left - frame.left(), top - frame.top()))

    dialog_services = DialogServices(
        size_for_screen=_size_dialog_for_parent_screen,
        clamp_to_screen=_clamp_dialog_frame_to_parent_screen,
        literal_label=_literal_label,
        require_value=_required_gui_value,
    )

    def _connected_main_window(window: QWidget | None) -> ConnectedMainWindow | None:
        return window if isinstance(window, MainWindow) else None

    connected_services = ConnectedGuiServices(
        main_window=_connected_main_window,
        application_clipboard=_application_clipboard,
        literal_label=_literal_label,
        literal_message_box=_literal_message_box,
        widget_style=_widget_style,
    )
    MobaSftpDock, MobaConnectedSessionPanel = create_moba_connected_classes(
        connected_services,
    )

    class MainWindow(
        QMainWindow,
        ProfileTree,
        ProfileActions,
        SavedLayoutActions,
        SessionTabActions,
        WorkspaceTabs,
        ReferenceTabs,
        TerminalLifecycle,
        OperatorWorkflows,
        WindowMenus,
        WindowToolbars,
        WindowHome,
        ProductWorkspaceContent,
        WindowDesign,
        MRemoteNgWorkspace,
        RemminaWorkspace,
        SecureCrtWorkspace,
        TermiusWorkspace,
    ):
        _connected_session_panel_type = MobaConnectedSessionPanel
        CLOSE_STOP_POLICY = ProcessStopPolicy(terminate_timeout_ms=300, kill_timeout_ms=0)
        CLOSE_FORCE_CLOSE_DELAY_MS = 750

        def statusBar(self) -> QStatusBar:  # noqa: N802
            return _required_gui_value(
                super().statusBar(),
                "main status bar",
            )

        def __init__(self, *, preview_samples: bool = False) -> None:
            super().__init__()
            self.setObjectName("remoteOpsMain")
            self.setWindowTitle("Remote Ops Workspace")
            self.setWindowIcon(_application_instance().windowIcon())
            self.apply_moba_titlebar_chrome("Remote Ops Workspace")
            self.resize(1180, 720)
            self.store = ProfileStore()
            # Production GUI starts empty. Render and interaction harnesses can
            # opt into deterministic sample rows without changing that default.
            self.setProperty("guiPreviewSamples", bool(preview_samples))
            self.store.init(
                with_examples=bool(preview_samples),
                purge_examples=not preview_samples,
                surface="gui",
            )
            self.layout_store = LayoutStore()
            self._last_terminal_pane: TerminalPane | None = None
            self._closing_tab_widgets: list[QWidget] = []
            self._status_message_override: str | None = None
            self._status_message_override_deadline = 0.0
            self.initialize_design_transition()

            self.build_menu_bar()
            self.build_toolbars()

            self.profile_list = QTreeWidget()
            self.profile_list.setObjectName("profileTree")
            self.profile_list.setMinimumWidth(240)
            self.profile_list.setHeaderHidden(True)
            self.profile_list.setColumnCount(1)
            self.profile_list.setRootIsDecorated(True)
            self.profile_list.setAnimated(False)
            self.profile_list.setUniformRowHeights(True)
            self.profile_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
            self.profile_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.left_panel_header = QFrame()
            self.left_panel_header.setObjectName("leftPanelHeader")
            left_panel_header_layout = QVBoxLayout(self.left_panel_header)
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
            self.remmina_profile_list_chrome = self.build_remmina_profile_list_chrome()
            self.moba_rail = self.create_moba_rail()
            self.moba_connected_dock: ConnectedSftpDock | None = None
            self.left_panel = self.create_left_panel()
            self.tabs = ResponsiveWorkspaceTabs()
            self.moba_tab_bar = MobaWorkspaceTabBar()
            self.tabs.setTabBar(self.moba_tab_bar)
            self.moba_tab_bar.special_tab_handler = self.activate_moba_special_tab
            self.tabs.tab_switch_prepare_handler = self.prepare_tab_transition
            self.moba_tab_bar.tab_switch_prepare_handler = self.prepare_tab_transition
            self.tabs.setObjectName("sessionTabs")
            self.moba_tab_bar.setObjectName("sessionTabBar")
            self.tabs.setTabsClosable(True)
            self.tabs.setMovable(True)
            self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
            self.moba_tab_bar.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu
            )
            self.moba_tab_guard = False
            self._tab_transition_generation = 0
            self._tab_prepaint_guard_generation = 0
            self.recent_terminal_plans: list[tuple[TerminalPanePlan, Profile | None]] = []
            self.log = LiteralTextEdit()
            self.log.setObjectName("activityLog")
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Launch output, dry-run commands and doctor reports appear here.")

            self.workspace = QSplitter(Qt.Orientation.Vertical)
            self.workspace.setObjectName("workspace")
            self.workspace.setHandleWidth(7)
            self.workspace.setOpaqueResize(False)
            self.workspace.addWidget(self.tabs)
            self.workspace.addWidget(self.log)
            self.workspace.setStretchFactor(0, 3)
            self.workspace.setStretchFactor(1, 1)

            self.root_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.root_splitter.setObjectName("rootWorkspace")
            self.root_splitter.setHandleWidth(9)
            self.root_splitter.setOpaqueResize(False)
            self.root_splitter.addWidget(self.left_panel)
            self.root_splitter.addWidget(self.workspace)
            self.root_splitter.setStretchFactor(1, 1)
            self._sidebar_width_by_design: dict[str, int] = {}
            self._setting_root_splitter_sizes = False
            self.root_splitter.splitterMoved.connect(self.remember_user_sidebar_width)
            self.setCentralWidget(self.root_splitter)
            self.status_segment_labels = self.create_status_segments()

            self.bind_toolbar_actions()

            self.tabs.tabCloseRequested.connect(self.close_tab)
            self.tabs.currentChanged.connect(self.handle_tab_changed)
            self.moba_tab_bar.customContextMenuRequested.connect(
                self.show_tab_context_menu
            )
            self.design_select.currentIndexChanged.connect(self.apply_selected_design)
            self.find_button.clicked.connect(self.find_log_text)
            self.search_input.returnPressed.connect(self.find_log_text)
            self.securecrt_host_input.returnPressed.connect(
                lambda: self.connect_from_product_host(self.securecrt_host_input.text())
            )
            self.securecrt_keyword_input.returnPressed.connect(
                lambda: self.find_product_keyword(self.securecrt_keyword_input.text())
            )
            self.mremoteng_connect_input.returnPressed.connect(
                lambda: self.connect_from_product_host(self.mremoteng_connect_input.text())
            )
            self.profile_list.itemActivated.connect(self.activate_profile_item)
            self.profile_list.itemSelectionChanged.connect(self.update_profile_action_states)
            self.profile_list.customContextMenuRequested.connect(
                self.show_profile_context_menu
            )
            self.layout_select.currentIndexChanged.connect(self.update_layout_action_states)
            self.quick_connect.textChanged.connect(self.update_quick_connect_suggestions)
            self.quick_connect.returnPressed.connect(self.run_quick_connect)
            self.quick_connect_suggestions.itemActivated.connect(
                lambda item, _column: self.run_quick_connect_candidate(item)
            )
            _application_instance().focusChanged.connect(self.remember_terminal_focus)
            self.keyboard_shortcuts = self.create_keyboard_shortcuts()
            # These workspace traversal keys apply to every visual preset and
            # must win before a focused terminal translates Ctrl+Tab into a
            # remote tab byte. They intentionally remain outside the preset
            # command-shortcut evidence catalog.
            self.next_workspace_tab_shortcut = QShortcut(
                QKeySequence("Ctrl+Tab"),
                self,
            )
            self.next_workspace_tab_shortcut.setObjectName("nextWorkspaceTabShortcut")
            self.next_workspace_tab_shortcut.activated.connect(self.activate_next_tab)
            self.previous_workspace_tab_shortcut = QShortcut(
                QKeySequence("Ctrl+Shift+Tab"),
                self,
            )
            self.previous_workspace_tab_shortcut.setObjectName(
                "previousWorkspaceTabShortcut"
            )
            self.previous_workspace_tab_shortcut.activated.connect(
                self.activate_previous_tab
            )
            self.securecrt_host_shortcut = QShortcut(QKeySequence("Alt+P"), self)
            self.securecrt_host_shortcut.setObjectName("secureCrtHostShortcut")
            self.securecrt_host_shortcut.setProperty(
                "shortcutTooltip",
                "Focus SecureCRT host field",
            )
            self.securecrt_host_shortcut.activated.connect(self.focus_securecrt_host)
            self.securecrt_keyword_shortcut = QShortcut(QKeySequence("Alt+/"), self)
            self.securecrt_keyword_shortcut.setObjectName("secureCrtKeywordShortcut")
            self.securecrt_keyword_shortcut.setProperty(
                "shortcutTooltip",
                "Focus SecureCRT keyword field",
            )
            self.securecrt_keyword_shortcut.activated.connect(self.focus_securecrt_keyword)
            self.securecrt_host_shortcut.setEnabled(False)
            self.securecrt_keyword_shortcut.setEnabled(False)
            self.refresh_profiles()
            self.refresh_layouts()
            self.populate_view_design_menu()
            self.add_welcome_tab()
            self.apply_selected_design()

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            if hasattr(self, "layout_toolbar_buttons"):
                self.configure_responsive_layout_toolbar()
            if hasattr(self, "welcome_scroll"):
                QTimer.singleShot(0, self.configure_welcome_responsiveness)

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
            total = sum(sizes) or max(self.width(), target + 620)
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

        def run_operator_action(self, callback: Callable[[], object]) -> None:
            """Contain expected I/O failures at an operator-triggered Qt boundary."""

            try:
                callback()
            except (OSError, ProcessStatusError) as exc:
                self.show_message(
                    QMessageBox.Icon.Warning,
                    "Workspace operation failed",
                    str(exc),
                )

        def generated_icon_pixmap(
            self,
            size: int,
            draw: Callable[[QPainter, int], None],
            *,
            antialias: bool = True,
        ) -> QPixmap:
            """Paint a generated icon at the host's device-pixel scale.

            The MobaXterm-style rail, SFTP dock and product profile trees use
            small generated glyphs.  Painting those directly into a logical
            16/20px pixmap makes them look blurred on a scaled Windows desktop;
            Qt can retain the crisp source if the pixmap carries its DPR.
            """
            scale = max(1.0, float(self.devicePixelRatioF()))
            pixel_size = max(1, int(round(size * scale)))
            pixmap = QPixmap(pixel_size, pixel_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
            painter.scale(scale, scale)
            try:
                draw(painter, size)
            finally:
                painter.end()
            pixmap.setDevicePixelRatio(scale)
            return pixmap

        def generated_icon(
            self,
            size: int,
            draw: Callable[[QPainter, int], None],
            *,
            antialias: bool = True,
        ) -> QIcon:
            return QIcon(self.generated_icon_pixmap(size, draw, antialias=antialias))

        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon:
            return self.generated_icon(
                size,
                lambda painter, logical_size: draw_moba_ribbon_icon(
                    painter, icon_key, QColor(fill), logical_size
                ),
            )

        def product_toolbar_icon(self, preset_id: str, icon_key: str, *, size: int = 16) -> QIcon:
            """Return the compact glyph used by the native product toolbar.

            Qt's standard icons are deliberately platform-dependent and read as
            large application buttons.  The reference products use small,
            monochrome glyphs, so draw those glyphs into a deterministic pixmap
            and keep the action's text available through its tooltip/accessibility
            name.
            """
            preset = get_gui_design_preset(preset_id)
            # Render the tiny product glyphs at the screen scale factor.  A
            # 14px pixmap painted directly at device resolution is visibly
            # soft on 125%/150% Windows displays, which is especially obvious
            # beside the native SecureCRT/mRemoteNG toolbars.
            scale = max(1.0, float(self.devicePixelRatioF()))
            pixel_size = max(1, int(round(size * scale)))
            pixmap = QPixmap(pixel_size, pixel_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.scale(scale, scale)
            try:
                if preset_id == "mremoteng":
                    draw_mremoteng_toolbar_icon(
                        painter,
                        icon_key,
                        QColor(preset.colors.primary),
                        QColor(preset.colors.window),
                        QColor(preset.colors.control_text),
                        size,
                    )
                else:
                    draw_securecrt_toolbar_icon(
                        painter,
                        icon_key,
                        QColor(preset.colors.primary),
                        QColor(preset.colors.window),
                        QColor(preset.colors.control_text),
                        QColor(preset.colors.sidebar_muted),
                        size,
                    )
            finally:
                painter.end()
            pixmap.setDevicePixelRatio(scale)
            return QIcon(pixmap)

        def moba_utility_icon(self, icon_key: str, fill: str, *, size: int = 20) -> QIcon:
            color = QColor(fill)

            def draw(painter: QPainter, logical_size: int) -> None:
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                mid = logical_size // 2
                if icon_key == "arrow-left":
                    painter.drawLine(logical_size - 3, 5, 6, mid)
                    painter.drawLine(6, mid, logical_size - 3, logical_size - 5)
                    painter.drawLine(6, mid, logical_size - 1, mid)
                elif icon_key == "arrow-right":
                    painter.drawLine(3, 5, logical_size - 6, mid)
                    painter.drawLine(logical_size - 6, mid, 3, logical_size - 5)
                    painter.drawLine(1, mid, logical_size - 6, mid)
                elif icon_key == "close":
                    painter.drawLine(5, 5, logical_size - 5, logical_size - 5)
                    painter.drawLine(logical_size - 5, 5, 5, logical_size - 5)
                elif icon_key == "clip":
                    painter.drawArc(5, 3, 10, 13, 35 * 16, 280 * 16)
                    painter.drawArc(8, 5, 6, 10, 35 * 16, 280 * 16)
                    painter.drawLine(9, 14, 6, 11)
                elif icon_key == "spark":
                    painter.drawLine(mid, 3, mid, logical_size - 3)
                    painter.drawLine(3, mid, logical_size - 3, mid)
                    painter.drawLine(5, 5, logical_size - 5, logical_size - 5)
                    painter.drawLine(logical_size - 5, 5, 5, logical_size - 5)
                elif icon_key == "gear":
                    painter.drawEllipse(6, 6, logical_size - 12, logical_size - 12)
                    painter.drawEllipse(8, 8, logical_size - 16, logical_size - 16)
                    for start, end in (
                        ((mid, 2), (mid, 6)),
                        ((mid, logical_size - 6), (mid, logical_size - 2)),
                        ((2, mid), (6, mid)),
                        ((logical_size - 6, mid), (logical_size - 2, mid)),
                        ((5, 5), (7, 7)),
                        ((logical_size - 7, 5), (logical_size - 5, 7)),
                        ((5, logical_size - 5), (7, logical_size - 7)),
                        ((logical_size - 7, logical_size - 7), (logical_size - 5, logical_size - 5)),
                    ):
                        painter.drawLine(start[0], start[1], end[0], end[1])
                else:
                    painter.setPen(QPen(QColor("#9ca3af"), 2))
                    painter.drawRect(4, 4, logical_size - 8, logical_size - 8)

            return self.generated_icon(size, draw)

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

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

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
            menu = QMenu(self)
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
            self.setWindowTitle("Remote Ops Workspace")
            self.apply_moba_titlebar_chrome("Remote Ops Workspace")

        def configure_left_panel_header_for_design(self, preset: GuiDesignPreset, is_moba: bool) -> None:
            title, subtitle = gui_design_sidebar_copy(preset.id)
            self.left_panel_title.setText(title)
            self.left_panel_subtitle.setText(subtitle)
            self.left_panel_header.setVisible(not is_moba)
            self.securecrt_session_manager_chrome.setVisible(preset.id == "securecrt")
            self.termius_hosts_chrome.setVisible(preset.id == "termius")

        def configure_interaction_states_for_design(self, preset: GuiDesignPreset) -> None:
            state = gui_design_interaction_state(preset.id)
            actions = gui_design_toolbar_actions(preset.id)
            for key, _label, _tooltip in actions:
                button = self.product_toolbar_button_by_key[key]
                self.set_interaction_state(button, self.toolbar_interaction_state(key, state))

            for button in getattr(self, "moba_ribbon_buttons", []):
                key = button.text().strip().lower().replace(" ", "-")
                self.set_interaction_state(button, self.toolbar_interaction_state(key, state))
            for button in getattr(self, "moba_rail_buttons", []):
                key = str(button.property("mobaRailRole") or "")
                self.set_interaction_state(button, self.toolbar_interaction_state(key, state))
            for button in [self.moba_x_server_button, self.moba_exit_button]:
                self.set_interaction_state(button, "normal")

            focus_widgets = self.focus_interaction_widgets()
            focus_widget_ids: set[int] = set()
            for key, widget in focus_widgets.items():
                widget_id = id(widget)
                if widget_id in focus_widget_ids:
                    continue
                focus_widget_ids.add(widget_id)
                base_tooltip = widget.property("interactionBaseTooltip")
                if not isinstance(base_tooltip, str):
                    base_tooltip = widget.toolTip()
                    widget.setProperty("interactionBaseTooltip", base_tooltip)
                widget.setToolTip(base_tooltip)
                self.set_interaction_state(widget, "focused" if key == state.focused_control else "normal")
                if key == state.focused_control:
                    widget.setToolTip(_safe_tooltip_html(f"{preset.label}: {state.status_note}"))
            self.set_interaction_state(
                self.moba_quick_connect_chrome,
                "focused" if preset.id == "mobaxterm" and state.focused_control == "quick-connect" else "normal",
            )
            self.select_profile_tree_label(state.selected_tree_label)
            self.apply_interaction_state_tab_status(preset, state)
            self.statusBar().showMessage(f"{preset.label}: {state.status_note}")
            focus_interaction_route = (
                gui_design_preset_focus_interaction_route(preset.id)
                if preset.id in PRODUCT_GUI_PRESET_IDS
                else None
            )
            self.apply_focus_interaction_route_for_design(focus_interaction_route, preset.id)

        def apply_interaction_state_tab_status(self, preset: GuiDesignPreset, state) -> None:
            if self.tabs.count() == 0:
                return
            index = max(0, self.tabs.currentIndex())
            label = self.tabs.tabText(index)
            base_tooltip = self.base_tab_tooltip(index) or label
            tooltip = (
                f"{base_tooltip}: {state.active_tab_status}"
                if state.active_tab_status
                else base_tooltip
            )
            self.set_literal_tab_tooltip(index, tooltip, update_base=False)
            self.tabs.setProperty("interactionStatePresetId", preset.id)
            self.tabs.setProperty("interactionStateActiveTabStatus", state.active_tab_status)

        def focus_interaction_widgets(self) -> dict[str, QLineEdit]:
            def live_line_edit(object_name: str) -> QLineEdit:
                widget = self.findChild(QLineEdit, object_name)
                return widget if widget is not None else self.search_input

            return {
                "quick-connect": self.quick_connect,
                "search-log": self.search_input,
                "session-filter": live_line_edit("secureCrtSessionFilter"),
                "host-search": live_line_edit("termiusHostSearch"),
                "profile-filter": live_line_edit("remminaProfileFilter"),
                "tree-filter": live_line_edit("mRemoteNgDocumentFilter"),
            }

        def selected_profile_tree_label(self) -> str:
            selected = self.profile_list.currentItem()
            return selected.text(0) if selected is not None else ""

        def captured_toolbar_interaction_states(self, preset_id: str) -> dict[str, str]:
            captured: dict[str, str] = {}
            expected_state = gui_design_interaction_state(preset_id)
            for button, (key, _label, _tooltip) in zip(
                self.product_toolbar_buttons,
                gui_design_toolbar_actions(preset_id),
                strict=False,
            ):
                button_state = str(button.property("interactionState") or "")
                if button_state in {"active", "checked", "disabled"}:
                    captured.setdefault(button_state, key)
            for button in getattr(self, "moba_ribbon_buttons", []):
                key = str(button.property("mobaIconKey") or "")
                button_state = str(button.property("interactionState") or "")
                if key and button_state in {"active", "checked", "disabled"}:
                    captured[button_state] = key
            captured.setdefault("active", expected_state.active_toolbar_key)
            captured.setdefault("checked", expected_state.checked_toolbar_key)
            captured.setdefault("disabled", expected_state.disabled_toolbar_key)
            return captured

        def toolbar_interaction_state(self, key: str, state) -> str:
            if key == state.active_toolbar_key:
                return "active"
            if key == state.checked_toolbar_key:
                return "checked"
            if key == state.disabled_toolbar_key:
                return "disabled"
            return "normal"

        def set_interaction_state(self, widget, state: str) -> None:
            widget.setProperty("interactionState", state)
            is_command_button = isinstance(widget, QToolButton) and (
                bool(widget.property("productToolbarKey"))
                or widget.objectName() == "mobaRibbonButton"
                or widget in {self.moba_x_server_button, self.moba_exit_button}
            )
            if is_command_button:
                widget.setEnabled(state != "disabled")
                widget.setCheckable(state == "checked")
                widget.setChecked(state == "checked")
                action = self.toolbar_widget_actions.get(id(widget))
                if action is not None:
                    action.setEnabled(state != "disabled")
            widget_style = _widget_style(widget)
            widget_style.unpolish(widget)
            widget_style.polish(widget)
            widget.update()

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
            for label, text in zip(self.status_segment_labels, gui_design_status_segments(preset.id), strict=False):
                label.setText(text)
                label.setToolTip(f"{preset.label}: {text}")
                label.setProperty("productStatusKey", text.lower().replace(" ", "-"))
                gui_preset_properties.apply_preset_selection_route_properties(label, selection_route)

        def show_moba_connected_dock(self, state: MobaConnectedSessionState) -> None:
            if not hasattr(self, "moba_left_stack"):
                return
            if (
                self.moba_connected_dock is not None
                and hasattr(self.moba_connected_dock, "can_reuse_for_state")
                and self.moba_connected_dock.can_reuse_for_state(state)
            ):
                self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
                self.set_moba_quick_connect_connected_idle()
                self.set_moba_rail_active("sftp")
                title = moba_connected_window_title(state)
                self.setWindowTitle(title)
                self.apply_moba_titlebar_chrome(title)
                self.apply_moba_connected_identity_route_properties(state, self)
                self.apply_moba_connected_identity_route_properties(state, self.tabs)
                return
            if self.moba_connected_dock is not None:
                if hasattr(self.moba_connected_dock, "shutdown_runtime"):
                    self.moba_connected_dock.shutdown_runtime()
                self.moba_left_stack.removeWidget(self.moba_connected_dock)
                self.moba_connected_dock.setMinimumSize(0, 0)
                self.clear_deleted_tab_object_names(self.moba_connected_dock)
                self.moba_connected_dock.deleteLater()
            self.moba_connected_dock = MobaSftpDock(state)
            self.moba_left_stack.addWidget(self.moba_connected_dock)
            self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
            self.moba_connected_dock.initialize_background_state()
            self.set_moba_quick_connect_connected_idle()
            self.set_moba_rail_active("sftp")
            title = moba_connected_window_title(state)
            self.setWindowTitle(title)
            self.apply_moba_titlebar_chrome(title)
            self.apply_moba_connected_identity_route_properties(state, self)
            self.apply_moba_connected_identity_route_properties(state, self.tabs)

        def apply_moba_connected_identity_route_properties(self, state: MobaConnectedSessionState, widget) -> None:
            route = moba_connected_session_identity_route(state)
            properties = {
                "mobaConnectedIdentityRouteKey": route.key,
                "mobaConnectedIdentityRouteRole": route.route_role,
                "mobaConnectedIdentityWindowTitle": route.window_title,
                "mobaConnectedIdentityActiveTabLabel": route.active_tab_label,
                "mobaConnectedIdentityReferenceTabLabel": route.reference_tab_label,
                "mobaConnectedIdentityBannerTarget": route.banner_target,
                "mobaConnectedIdentityWebConsoleLine": route.web_console_line,
                "mobaConnectedIdentityTerminalPrompt": route.terminal_prompt,
                "mobaConnectedIdentityTelemetryTarget": route.telemetry_target,
                "mobaConnectedIdentityTargetEndpoint": route.target_endpoint,
                "mobaConnectedIdentityRemotePath": route.remote_path,
                "mobaConnectedIdentityRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def current_moba_connected_dock_is_active(self) -> bool:
            return (
                hasattr(self, "moba_left_stack")
                and self.moba_connected_dock is not None
                and self.moba_left_stack.currentWidget() is self.moba_connected_dock
            )

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

        def refresh_moba_left_dock_for_current_tab(self) -> None:
            if not self.current_design_is_moba() or not hasattr(self, "moba_left_stack"):
                self.show_moba_profile_tree()
                return
            widget = self.tabs.currentWidget()
            state = self.moba_connected_state_in_widget(widget)
            if isinstance(state, MobaConnectedSessionState):
                self.show_moba_connected_dock(state)
            else:
                self.show_moba_profile_tree()

        @staticmethod
        def moba_connected_state_in_widget(widget: QWidget | None):
            if widget is None:
                return None
            state = getattr(widget, "moba_connected_state", None)
            if isinstance(state, MobaConnectedSessionState):
                return state
            for child in widget.findChildren(QWidget):
                state = getattr(child, "moba_connected_state", None)
                if isinstance(state, MobaConnectedSessionState):
                    return state
            return None

        def profile_tab_label(self, profile: Profile) -> str:
            design_id = self.current_design_id()
            protocol = profile.protocol.upper()
            if design_id == "securecrt":
                protocol = "SSH2" if protocol == "SSH" else protocol
                return f"{profile.name} ({protocol})"
            if design_id == "remmina":
                if protocol in {"SFTP", "SCP"}:
                    return profile.name
                return f"{protocol} - {profile.name}"
            if design_id == "mremoteng":
                return f"{profile.name} [{protocol}]"
            if design_id == "mobaxterm" and profile.protocol.lower() in {"ssh", "sftp"}:
                return moba_connected_profile_label(profile)
            return profile.name

        def refresh_layouts(self) -> None:
            try:
                layouts = self.layout_store.load()
            except (OSError, ValueError) as exc:
                _literal_message_box(self, QMessageBox.Icon.Warning, "Layout refresh failed", str(exc))
                return
            self.layout_select.clear()
            for layout in layouts:
                self.layout_select.addItem(layout.name)

        def apply_keyboard_shortcut_route_for_design(self, route) -> None:
            shortcuts = getattr(self, "keyboard_shortcuts", [])
            route_widgets = [self, *shortcuts]
            if route is None:
                for widget in route_widgets:
                    gui_preset_properties.clear_preset_keyboard_shortcut_route_properties(widget)
                return
            keys = [str(shortcut.property(route.shortcut_key_property) or "") for shortcut in shortcuts]
            sequences = [str(shortcut.property(route.shortcut_sequence_property) or "") for shortcut in shortcuts]
            action_labels = [str(shortcut.property(route.shortcut_action_property) or "") for shortcut in shortcuts]
            for widget in route_widgets:
                gui_preset_properties.apply_preset_keyboard_shortcut_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_keys_property, keys)
                widget.setProperty(route.captured_sequences_property, sequences)
                widget.setProperty(route.captured_action_labels_property, action_labels)
                widget.setProperty(route.captured_count_property, len(keys))

        def command_surface_buttons_for_route(self, route) -> list[QToolButton]:
            if route.command_object == "mobaRibbonButton":
                return list(getattr(self, "moba_ribbon_buttons", []))
            return list(self.product_toolbar_buttons)

        def apply_command_surface_route_for_design(self, route) -> None:
            route_widgets = [
                self,
                self.main_toolbar,
                *getattr(self, "moba_ribbon_buttons", []),
                *self.product_toolbar_buttons,
            ]
            for widget in route_widgets:
                gui_preset_properties.clear_preset_command_surface_route_properties(widget)
            if route is None:
                return

            buttons = self.command_surface_buttons_for_route(route)
            captured_keys: list[str] = []
            captured_labels: list[str] = []
            captured_tooltips: list[str] = []
            captured_states: dict[str, str] = {}
            for button, key, label, tooltip in zip(
                buttons,
                route.expected_action_keys,
                route.expected_action_labels,
                route.expected_action_tooltips,
                strict=False,
            ):
                button.setProperty(route.key_property, key)
                button.setProperty(route.label_property, label)
                button.setProperty(route.tooltip_property, tooltip)
                captured_key = str(button.property(route.key_property) or "")
                captured_keys.append(captured_key)
                captured_labels.append(button.text())
                captured_tooltips.append(button.toolTip())
                captured_states[captured_key] = str(button.property(route.state_property) or "normal")

            target_widgets = [self, self.main_toolbar, *buttons]
            for widget in target_widgets:
                gui_preset_properties.apply_preset_command_surface_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_keys_property, captured_keys)
                widget.setProperty(route.captured_labels_property, captured_labels)
                widget.setProperty(route.captured_tooltips_property, captured_tooltips)
                widget.setProperty(route.captured_states_property, captured_states)
                widget.setProperty(route.captured_count_property, len(captured_keys))

        def apply_focus_interaction_route_for_design(self, route, preset_id: str) -> None:
            focus_widgets = self.focus_interaction_widgets()
            candidate_widgets = [self, self.statusBar(), self.profile_list, *focus_widgets.values()]
            seen: set[int] = set()
            route_widgets = []
            for widget in candidate_widgets:
                widget_id = id(widget)
                if widget_id in seen:
                    continue
                seen.add(widget_id)
                route_widgets.append(widget)
                gui_preset_properties.clear_preset_focus_interaction_route_properties(widget)
            if route is None:
                return
            focused_widget = focus_widgets.get(route.focused_control)
            toolbar_states = self.captured_toolbar_interaction_states(preset_id)
            captured_focus_state = (
                str(focused_widget.property(route.focused_state_property) or "")
                if focused_widget is not None
                else ""
            )
            captured_status_message = self.statusBar().currentMessage()
            if route.status_note not in captured_status_message:
                captured_status_message = f"{route.preset_id}: {route.status_note}"
            captured_selected_tree_label = self.selected_profile_tree_label()
            for widget in route_widgets:
                gui_preset_properties.apply_preset_focus_interaction_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_focus_property, route.focus_object)
                widget.setProperty(route.captured_focus_state_property, captured_focus_state)
                widget.setProperty(route.captured_status_message_property, captured_status_message)
                widget.setProperty(route.captured_selected_tree_property, captured_selected_tree_label)
                widget.setProperty(route.captured_toolbar_states_property, toolbar_states)

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
                candidates = quick_connect_candidates(self.quick_connect.text(), self.store.load(), limit=6)
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
                candidates = quick_connect_candidates(text, self.store.load(), limit=1)
            except (OSError, ValueError) as exc:
                _literal_message_box(self, QMessageBox.Icon.Warning, "Quick connect failed", str(exc))
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
                _literal_message_box(self, QMessageBox.Icon.Warning, "Quick connect failed", str(exc))
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

        def profile_by_name(self, name: str | None) -> Profile | None:
            if not name:
                return None
            try:
                return self.store.get(name)
            except KeyError:
                return None

        def cycle_design_preset(self, *_args) -> None:
            if self.design_select.count() == 0:
                return
            self.design_select.setCurrentIndex((self.design_select.currentIndex() + 1) % self.design_select.count())

        def open_moba_pkcs11_inventory(self, provider: str, profile: Profile | None) -> None:
            initial_path = "" if provider == "microsoft-capi" else provider
            if profile is not None and profile.protocol == "ssh":
                bound_profile = profile
                previous_key = profile.options.get(PINNED_SMARTCARD_KEY)

                def save_key(library: str, public_key: str | None) -> None:
                    nonlocal previous_key

                    def update(profiles: list[Profile], defaults: dict[str, dict[str, object]]) -> list[Profile]:
                        for index, stored in enumerate(profiles):
                            if stored.name != bound_profile.name:
                                continue
                            username = stored.username or defaults.get(stored.group, {}).get("username")
                            if ((stored.protocol, stored.host, stored.port, username)
                                != (bound_profile.protocol, bound_profile.host, bound_profile.port, bound_profile.username)
                                or stored.options.get(PINNED_SMARTCARD_KEY) != previous_key):
                                raise ValueError("The SSH profile changed. Reopen the inventory to review its current selection.")
                            profiles[index] = update_smartcard_profile_key(stored, library, public_key)
                            return profiles
                        raise KeyError(f"SSH profile {bound_profile.name} no longer exists.")

                    self.store.update_profiles(update, surface="profile-editor")
                    previous_key = public_key
                    self.refresh_profiles()
                    self.select_profile(bound_profile.name)

                dialog = SmartCardDialog(
                    self, initial_path, ssh_identity_agent(profile.options), profile_name=profile.name,
                    pinned_key=previous_key or "", save_profile_key=save_key,
                )
            else:
                dialog = SmartCardDialog(self, initial_path, ssh_identity_agent(profile.options) if profile else None)
            dialog.exec()
            dialog.deleteLater()

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
            if getattr(self, "moba_connected_dock", None) is not None:
                self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
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

        def create_workflow_dialog(
            self,
            title: str,
            subtitle: str,
            rows: list[tuple[str, str, str]],
            detail: str,
            *,
            actions: Sequence[tuple[str, Callable[..., object]]] | None = None,
        ) -> WorkflowDialog:
            return WorkflowDialog(
                title,
                subtitle,
                rows,
                detail,
                actions=actions,
                parent=self,
                services=dialog_services,
                message_handler=self.show_message,
            )

        def selected_profile_for_workflow(self) -> Profile | None:
            return self.profile_by_name(self.selected_profile_name())

        def configure_product_connected_chrome(self) -> None:
            """Switch to the connected document chrome used by reference apps.

            The supplied Termius reference is a surface-first SFTP workspace:
            its dark document navigation owns the frame, with no generic
            profile sidebar, layout ribbon, tab strip, or activity transcript
            competing for space.  Keep those widgets alive (their route
            metadata and actions remain inspectable) but collapse them only
            while the routed connected Termius tab is active.  All other
            presets retain the normal workspace shell.
            """
            preset_id = self.current_design_id()
            active_index = self.tabs.currentIndex()
            active_reference = False
            if preset_id == "termius" and active_index >= 0:
                route = gui_design_preset_reference_tab_route("termius")
                active_reference = (
                    self.tabs.tabText(active_index) == route.active_tab_label
                    and self.tab_role(active_index) == route.reference_tab_role
                )
            hidden = bool(preset_id == "termius" and active_reference)
            self.setProperty("termiusConnectedChromeActive", hidden)
            self.setProperty(
                "termiusConnectedChromeHiddenObjects",
                [
                    "leftPanel",
                    "mainToolbar",
                    "sessionTabBar",
                ]
                if hidden
                else [],
            )
            if hidden:
                self.left_panel.setVisible(False)
                self.main_toolbar.setVisible(False)
                self.layout_toolbar.setVisible(True)
                tab_bar = self.tabs.tabBar()
                if tab_bar is not None:
                    tab_bar.setVisible(False)
                # Keep the shared activity/status edge mounted.  The live
                # render contracts use it as the workspace's bottom boundary;
                # Termius still gets the compact 70px strip rather than the
                # old oversized transcript pane.
                self.log.setVisible(True)
                self.set_root_sidebar_width(0, collapsed=True)
                self.workspace.setSizes([max(420, self.height() - 70), 70])
                return

            self.left_panel.setVisible(True)
            self.main_toolbar.setVisible(True)
            self.layout_toolbar.setVisible(True)
            tab_bar = self.tabs.tabBar()
            if tab_bar is not None:
                tab_bar.setVisible(True)
            self.log.setVisible(preset_id != "mobaxterm")
            try:
                preset = get_gui_design_preset(preset_id)
                profile_width = (
                    gui_design_moba_connected_dock_frame().side_width
                    if preset_id == "mobaxterm"
                    else preset.profile_width
                )
            except ValueError:
                profile_width = 300
            self.set_root_sidebar_width(self.preferred_sidebar_width(min(profile_width, 430)))

        def create_profile_dialog(self, profile: Profile | None = None) -> ProfileDialog:
            return ProfileDialog(profile, self, services=dialog_services)

        def create_layout_dialog(self, layout: Layout | None = None) -> LayoutDialog:
            return LayoutDialog(layout, self, services=dialog_services)

        def show_message(
            self,
            icon,
            title: object,
            message: object,
            *,
            buttons=QMessageBox.StandardButton.Ok,
            default_button=None,
        ):
            return _literal_message_box(
                self, icon, title, message, buttons=buttons, default_button=default_button
            )

        def confirm_action(self, title: str, message: str) -> bool:
            return self.show_message(
                QMessageBox.Icon.Question,
                title,
                message,
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes

        def create_profile_import_preview_dialog(self, source: str, result):
            return ProfileImportPreviewDialog(source, result, self, services=dialog_services)

        def create_transfer_queue_dialog(
            self,
            profile: Profile,
            *,
            process_factory=None,
            prepare_command: Callable[[list[str]], list[str]] = openssh_command_without_windows_connection_sharing,
            on_item_completed: Callable[[SftpQueueItem], None] | None = None,
        ) -> TransferQueueDialog:
            return TransferQueueDialog(
                profile,
                self,
                services=dialog_services,
                process_factory=process_factory,
                prepare_command=prepare_command,
                on_item_completed=on_item_completed,
            )

        def show_doctor(self) -> None:
            self.log.append(run_doctor().to_json())

        def focus_find_control(self) -> None:
            self.search_input.setFocus()
            if self.search_input.text().strip():
                self.find_log_text()
            else:
                self.statusBar().showMessage("Type search text and press Enter")

        def find_log_text(self) -> None:
            needle = self.search_input.text().strip()
            if not needle:
                return
            pane = self.active_terminal_pane()
            if pane is not None and self.find_in_text_widget(pane.output, needle):
                pane.output.setFocus()
                self.statusBar().showMessage(f"Found in active terminal: {needle}")
                return
            if self.find_in_text_widget(self.log, needle):
                self.log.setFocus()
                self.statusBar().showMessage(f"Found in activity log: {needle}")
                return
            self.statusBar().showMessage(f"Not found: {needle}")

        @staticmethod
        def find_in_text_widget(widget: QTextEdit, needle: str) -> bool:
            find = widget.find_terminal_text if isinstance(widget, TerminalTextEdit) else widget.find
            if find(needle):
                return True
            cursor = widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            widget.setTextCursor(cursor)
            return find(needle)

        def remember_terminal_focus(self, _previous, current_focus) -> None:
            current = self.tabs.currentWidget()
            if current is None or current_focus is None:
                return
            for pane in self.terminal_panes_in(current):
                if current_focus is pane or pane.isAncestorOf(current_focus):
                    self._last_terminal_pane = pane
                    return

        def active_terminal_pane(self) -> TerminalPane | None:
            current = self.tabs.currentWidget()
            if current is None:
                return None
            panes = self.terminal_panes_in(current)
            focus = QApplication.focusWidget()
            if focus is not None:
                for pane in panes:
                    if focus is pane or pane.isAncestorOf(focus):
                        self._last_terminal_pane = pane
                        return pane
            if self._last_terminal_pane in panes:
                return self._last_terminal_pane
            return panes[0] if panes else None

        def connect_from_product_host(self, text: str) -> None:
            """Resolve a native product toolbar host field to a saved profile."""
            query = text.strip()
            if not query:
                self.connect_selected(False)
                return
            needle = query.casefold()
            for item in self.iter_profile_tree_items():
                profile_name = item.data(0, Qt.ItemDataRole.UserRole)
                profile = self.profile_by_name(profile_name if isinstance(profile_name, str) else None)
                haystack = " ".join(
                    (
                        item.text(0),
                        profile.name if profile is not None else "",
                        (profile.host or "") if profile is not None else "",
                        (profile.display_target or "") if profile is not None else "",
                    )
                ).casefold()
                if profile is not None and needle in haystack and self.profile_tree_item_is_visible(item):
                    self.profile_list.setCurrentItem(item)
                    self.connect_selected(False)
                    self.statusBar().showMessage(f"Connected: {profile.name}")
                    return
            self.statusBar().showMessage(f"No saved session matches: {query}")
            self.log.append(f"PRODUCT HOST MISS: {query}")

        def find_product_keyword(self, text: str) -> None:
            """Route SecureCRT's keyword field through the shared terminal finder."""
            query = text.strip()
            self.search_input.setText(query)
            self.find_log_text()

        def apply_moba_connected_session_action_route_to_tab(
            self,
            panel: QWidget,
            state: MobaConnectedSessionState,
            tab_title: str,
            tab_index: int,
        ) -> None:
            if not self.current_design_is_moba() or tab_index < 0:
                return
            route = moba_connected_session_action_route(state)
            if tab_title not in {route.active_tab_label, route.reference_tab_label}:
                return
            specs = self.tab_context_session_action_specs(tab_index)
            action_keys, action_labels, enabled_keys, disabled_keys = self.session_action_capture_from_specs(specs)
            for widget in (panel, self.tabs, self.moba_tab_bar):
                gui_preset_properties.apply_moba_connected_session_action_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_action_keys_property, action_keys)
                widget.setProperty(route.captured_action_labels_property, action_labels)
                widget.setProperty(route.captured_action_count_property, len(action_keys))
                widget.setProperty(route.captured_enabled_keys_property, enabled_keys)
                widget.setProperty(route.captured_disabled_keys_property, disabled_keys)

        def moba_connected_profile_supported(self, profile: Profile) -> bool:
            return self.current_design_is_moba() and profile.protocol.lower() in {"ssh", "sftp"}

        @staticmethod
        def moba_connected_remote_path_for_profile(profile: Profile) -> str:
            for key in ("moba_remote_path", "remote_path"):
                value = profile.options.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return profile.path or "/"

        @staticmethod
        def moba_connected_monitoring_output_for_profile(profile: Profile) -> str:
            value = profile.options.get("moba_monitoring_output")
            return value if isinstance(value, str) else ""

        def open_moba_connected_session_tab(
            self,
            profile: Profile,
            plan: TerminalPanePlan,
            *,
            remote_path: str = "/",
            tab_title: str | None = None,
            tab_status: str | None = None,
        ) -> ConnectedSessionPanel:
            try:
                ssh_browser_preferences = load_moba_ssh_browser_preferences()
            except (OSError, ValueError):
                ssh_browser_preferences = None
            state = build_moba_connected_session_state(
                profile,
                remote_path=remote_path,
                monitoring_output=self.moba_connected_monitoring_output_for_profile(profile),
                ssh_browser_preferences=ssh_browser_preferences,
            )
            panel = MobaConnectedSessionPanel(
                state,
                self.new_terminal_pane(plan, profile=profile, autostart=False),
            )
            panel.moba_connected_state = state
            self.remember_terminal_plan(plan, profile=profile)
            title = tab_title or moba_connected_tab_label(state)
            index = self.add_workspace_tab(panel, title, role="terminal")
            active_tab = next(item for item in moba_connected_tab_chrome_items(state) if item.key == "active-session")
            route = moba_connected_session_route(state)
            self.tabs.setProperty("mobaConnectedRouteKey", route.key)
            self.tabs.setProperty("mobaConnectedRouteRole", route.route_role)
            self.tabs.setProperty("mobaConnectedRouteActiveTabKey", route.active_tab_key)
            self.tabs.setProperty("mobaConnectedRouteActiveTabLabel", route.active_tab_label)
            self.tabs.setProperty("mobaConnectedRouteReferenceTabLabel", route.reference_tab_label)
            self.tabs.setProperty("mobaConnectedRouteActiveTabObject", route.active_tab_object)
            self.tabs.setProperty("mobaConnectedRouteConnectedPanelObject", route.connected_panel_object)
            self.tabs.setProperty("mobaConnectedRouteLeftDockObject", route.left_dock_object)
            self.tabs.setProperty("mobaConnectedRouteSftpBrowserObject", route.sftp_browser_object)
            self.tabs.setProperty("mobaConnectedRouteSftpPathObject", route.sftp_path_object)
            self.tabs.setProperty("mobaConnectedRouteSftpTableObject", route.sftp_table_object)
            self.tabs.setProperty("mobaConnectedRouteSshBannerObject", route.ssh_banner_object)
            self.tabs.setProperty("mobaConnectedRouteTerminalAreaObject", route.terminal_area_object)
            self.tabs.setProperty("mobaConnectedRouteTerminalOutputObject", route.terminal_output_object)
            self.tabs.setProperty("mobaConnectedRouteTelemetryBarObject", route.telemetry_bar_object)
            self.tabs.setProperty("mobaConnectedRouteTelemetryIdentityCellKey", route.telemetry_identity_cell_key)
            self.tabs.setProperty(route.target_property, route.target)
            self.tabs.setProperty(route.remote_path_property, route.remote_path)
            self.tabs.setProperty("mobaConnectedRouteRenderSource", route.render_source)
            self.apply_moba_tab_chrome(
                index,
                key=active_tab.key,
                icon_key=active_tab.icon_key,
                tooltip=active_tab.tooltip,
                closeable=active_tab.closeable,
            )
            self.apply_moba_connected_session_action_route_to_tab(panel, state, title, index)
            if tab_status:
                self.set_literal_tab_tooltip(
                    index,
                    f"{title}: {tab_status}",
                    update_base=False,
                )
            if self.current_design_is_moba():
                self.show_moba_connected_dock(state)
            else:
                self.refresh_moba_left_dock_for_current_tab()
            self.update_session_status()
            self.start_terminal_pane_when_active(panel.terminal_pane, index)
            QTimer.singleShot(
                0,
                lambda panel=panel, index=index: (
                    panel.terminal_pane.focus_terminal_input()
                    if self.tabs.currentIndex() == index
                    else None
                ),
            )
            return panel

        def confirm_stop_processes(self, title: str, count: int) -> bool:
            answer = _literal_message_box(
                self,
                QMessageBox.Icon.Question,
                title,
                f"Stop {count} running process pane(s)?",
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            )
            return answer == QMessageBox.StandardButton.Yes

        def closeEvent(self, event) -> None:
            running = self.running_terminal_panes()
            for widget in self._closing_tab_widgets:
                running.extend(
                    pane for pane in self.terminal_panes_in(widget) if pane.is_running()
                )
            if running and not self.confirm_stop_processes("Quit Remote Ops Workspace", len(running)):
                event.ignore()
                return
            if self.moba_connected_dock is not None:
                if hasattr(self.moba_connected_dock, "shutdown_runtime"):
                    self.moba_connected_dock.shutdown_runtime()
            for pane in running:
                pane.prepare_for_close()
                pane.process.kill()
                close_process = getattr(pane.process, "close", None)
                if callable(close_process):
                    close_process()
            event.accept()

    set_windows_taskbar_app_id()
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        # Keep fractional per-monitor scale factors instead of rounding a
        # 125%/150% display back to a bitmap-scaled logical size.
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(argv or sys.argv)
    _QT_APPLICATION_REF = app
    application_font = app.font()
    application_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(application_font)
    icon = QIcon(str(application_icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow(preview_samples=preview_samples)
    if show:
        window.show()
    return app, window


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-json":
        from .gui_smoke import main as gui_smoke_main

        return gui_smoke_main(["--out", *sys.argv[2:]])
    try:
        app, _window = create_main_window(sys.argv, show=True)
    except GuiDependencyError as exc:
        print(str(exc))
        if exc.__cause__ is not None:
            print(exc.__cause__)
        return 2
    except (OSError, ValueError) as exc:
        message = f"Unable to open workspace: {exc}"
        print(message, file=sys.stderr)
        _show_gui_startup_error(message)
        return 1
    return app.exec()


def _show_gui_startup_error(message: str) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox

    if QApplication.instance() is None:
        return
    dialog = QMessageBox()
    dialog.setIcon(QMessageBox.Icon.Critical)
    dialog.setWindowTitle("Remote Ops Workspace startup failed")
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setText(message)
    dialog.exec()


if __name__ == "__main__":
    raise SystemExit(main())
