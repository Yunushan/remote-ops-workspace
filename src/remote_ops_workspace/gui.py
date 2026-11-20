from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import quick_connect as _quick_connect
from .doctor import run_doctor
from .file_transfer import SftpQueueItem
from .gui_designs import (
    get_gui_design_preset,
    gui_design_moba_connected_dock_frame,
    gui_design_preset_reference_tab_route,
)
from .gui_lifecycle import ProcessStopPolicy
from .gui_values import _required_gui_value, _widget_style
from .gui_values import _safe_tooltip_html as _safe_tooltip_html
from .launcher import ssh_identity_agent
from .layouts import Layout, LayoutStore
from .moba_connected import moba_connected_profile_label
from .moba_smartcards import (
    update_smartcard_profile_key,
)
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
            QMainWindow,
            QMessageBox,
            QSplitter,
            QStatusBar,
            QStyle,
            QTextEdit,
            QToolButton,
            QTreeWidget,
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
    from .gui_interaction_states import WindowInteractionStates
    from .gui_layouts import SavedLayoutActions
    from .gui_menus import WindowMenus
    from .gui_moba_sessions import MobaConnectedSessions
    from .gui_mremoteng import MRemoteNgWorkspace
    from .gui_operator_workflows import OperatorWorkflows
    from .gui_product_workspace import ProductWorkspaceContent
    from .gui_profile_actions import ProfileActions
    from .gui_profile_tree import ProfileTree
    from .gui_quick_connect import WindowQuickConnect
    from .gui_reference_tabs import ReferenceTabs
    from .gui_remmina import RemminaWorkspace
    from .gui_securecrt import SecureCrtWorkspace
    from .gui_session_tabs import SessionTabActions
    from .gui_sidebar import WindowSidebar
    from .gui_smartcards import SmartCardDialog
    from .gui_terminal_lifecycle import TerminalLifecycle
    from .gui_termius import TermiusWorkspace
    from .gui_toolbars import WindowToolbars
    from .gui_window_chrome import WindowChrome
    from .gui_workspace import MobaWorkspaceTabBar, ResponsiveWorkspaceTabs
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
        WindowInteractionStates,
        WindowQuickConnect,
        ProfileTree,
        ProfileActions,
        SavedLayoutActions,
        SessionTabActions,
        MobaConnectedSessions,
        WorkspaceTabs,
        ReferenceTabs,
        TerminalLifecycle,
        OperatorWorkflows,
        WindowMenus,
        WindowToolbars,
        WindowHome,
        WindowSidebar,
        ProductWorkspaceContent,
        WindowDesign,
        WindowChrome,
        MRemoteNgWorkspace,
        RemminaWorkspace,
        SecureCrtWorkspace,
        TermiusWorkspace,
    ):
        _connected_session_panel_type = MobaConnectedSessionPanel
        _connected_sftp_dock_type = MobaSftpDock
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
            self.left_panel_header = self.create_left_panel_header()
            self.create_quick_connect_controls()
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

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

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

        def _find_quick_connect_candidates(self, text: str, *, limit: int) -> list[QuickConnectCandidate]:
            return quick_connect_candidates(text, self.store.load(), limit=limit)

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
