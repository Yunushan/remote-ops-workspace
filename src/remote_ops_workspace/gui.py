Warning: truncated output (original token count: 249007)
Total output lines: 18912

from __future__ import annotations

import html
import os
import posixpath
import re
import shlex
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TypeVar
from urllib.parse import urlparse

from .doctor import run_doctor
from .enterprise_policy import assert_profile_launch_allowed
from .file_safety import (
    write_bytes_atomic,
    write_json_atomic,
)
from .file_transfer import (
    SftpBatchPlan,
    build_sftp_list_plan,
    build_sftp_queue_plan,
    parse_transfer_item_spec,
    preview_local_path,
)
from .gui_designs import (
    GUI_DESIGN_PRESETS,
    PRODUCT_GUI_PRESET_IDS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    GuiDesignPreset,
    get_gui_design_preset,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame,
    gui_design_moba_follow_terminal_folder_control_route,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_home_welcome_geometry,
    gui_design_moba_monitoring_control_geometry,
    gui_design_moba_monitoring_control_geometry_for,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry_for,
    gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_control_route,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_action_geometry,
    gui_design_moba_ribbon_action_geometry_for,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_ribbon_tooltips,
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_geometry_for,
    gui_design_moba_sftp_toolbar_action_route,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_terminal_transcript_row_geometry,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_geometry,
    gui_design_moba_top_menu_geometry_for,
    gui_design_moba_top_menu_items,
    gui_design_moba_top_stack_geometry,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_catalog_route,
    gui_design_preset_command_surface_route,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_home_search_route,
    gui_design_preset_isolation_route,
    gui_design_preset_keyboard_shortcut_route,
    gui_design_preset_reference_control_route,
    gui_design_preset_reference_input_route,
    gui_design_preset_reference_session_action_route,
    gui_design_preset_reference_status_bar_route,
    gui_design_preset_reference_surface_route,
    gui_design_preset_reference_tab_chrome_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_reference_transcript_route,
    gui_design_preset_selection_route,
    gui_design_preset_transition_route,
    gui_design_preset_visual_signature,
    gui_design_product_identity_route,
    gui_design_reference_state,
    gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_filter_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route,
    gui_design_remmina_screenshot_route,
    gui_design_remmina_sftp_transfer_route,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_sftp_browser_route,
    gui_design_securecrt_sftp_tab_route,
    gui_design_securecrt_top_chrome,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_termius_files_browser_route,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_port_forward_route,
    gui_design_termius_snippet_route,
    gui_design_termius_sync_route,
    gui_design_toolbar_actions,
    gui_design_tree_root_copy,
    gui_design_tree_root_icon,
    gui_design_tree_row_icon,
    gui_design_workflow_cards,
    gui_design_workspace_surface,
)
from .gui_editors import (
    layout_from_editor_data,
    layout_to_editor_data,
    profile_editor_protocols,
    profile_from_editor_data,
    profile_to_editor_data,
    protocol_preset_editor_data,
)
from .gui_lifecycle import ProcessStopPolicy, ProcessStopResult, stop_process
from .launcher import LauncherError, build_launch_plan
from .layouts import (
    Layout,
    LayoutStore,
    build_layout_terminal_plans,
    layout_splitter_size_lengths,
    validate_layout,
)
from .moba_connected import (
    MobaConnectedSessionState,
    build_moba_connected_session_state,
    moba_connected_profile_label,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_geometry_for,
    moba_connected_tab_chrome_geometry_items,
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_text_editor_route,
    moba_connected_window_title,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
    moba_telemetry_cells,
    normalise_remote_path,
    parse_remote_monitoring_output,
    parse_sftp_ls_output,
)
from .moba_macros import (
    MOBA_MACRO_TERMINAL_CAPTURE_SCHEMA,
    MOBA_MACRO_TERMINAL_REPLAY_SCHEMA,
    MobaMacroRecording,
    MobaMacroTerminalCaptureState,
    MobaMacroTerminalReplayInjection,
    build_terminal_macro_replay_injection,
    cancel_terminal_macro_capture,
    capture_terminal_macro_input,
    finish_terminal_macro_capture,
    start_terminal_macro_capture,
)
from .moba_multiexec import DEFAULT_MOBA_MULTIEXEC_COMMAND, build_moba_multiexec_plan
from .moba_servers import build_moba_server_gui_config_surface
from .moba_smartcards import MobaSmartCardCertificate, build_smartcard_management_gui_surface
from .moba_ssh_browser import load_moba_ssh_browser_preferences
from .models import Profile
from .paths import ensure_data_dir
from .profile_importers import import_profiles
from .storage import ProfileStore
from .terminal import (
    TerminalPanePlan,
    default_shell_plan,
    openssh_command_with_overrides,
    split_shell_plans,
    terminal_plan_for_profile,
    terminal_plan_for_sftp_browser,
)
from .terminal_emulation import (
    TERMINAL_EMULATOR_BACKEND,
    AnsiTerminalTranscript,
    AnsiTextStyle,
)
from .terminal_highlighting import (
    default_terminal_syntax_rules,
    highlight_terminal_text,
    terminal_syntax_rule_keys,
)


def _safe_tooltip_html(text: str) -> str:
    """Render arbitrary launch/profile text literally inside a Qt tooltip."""

    escaped = html.escape(text).replace("\n", "<br>")
    return f"<qt>{escaped}</qt>"


class GuiDependencyError(RuntimeError):
    pass


_GuiValue = TypeVar("_GuiValue")


def _required_gui_value(value: _GuiValue | None, label: str) -> _GuiValue:
    if value is None:
        raise RuntimeError(f"required GUI value is unavailable: {label}")
    return value


QUICK_CONNECT_PROTOCOLS = {
    "ssh",
    "sftp",
    "scp",
    "rdp",
    "vnc",
    "telnet",
    "ftp",
    "http",
    "https",
    "mosh",
    "x2go",
    "spice",
    "raw",
}
QUICK_CONNECT_DEFAULT_PORTS = {
    "ssh": 22,
    "sftp": 22,
    "scp": 22,
    "rdp": 3389,
    "vnc": 5900,
    "telnet": 23,
    "ftp": 21,
    "mosh": 22,
    "raw": None,
}


@dataclass(frozen=True)
class QuickConnectCandidate:
    kind: str
    label: str
    detail: str
    profile_name: str | None = None
    profile: Profile | None = None


def quick_connect_candidates(text: str, profiles: list[Profile], *, limit: int = 6) -> list[QuickConnectCandidate]:
    query = text.strip()
    if not query:
        return []

    direct = parse_quick_connect_profile(query)
    direct_is_explicit = direct is not None and quick_connect_is_explicit(query)
    matches = profile_quick_connect_matches(query, profiles, limit=limit)
    candidates: list[QuickConnectCandidate] = []
    if direct is not None and direct_is_explicit:
        candidates.append(direct)
    candidates.extend(matches)
    if direct is not None and not direct_is_explicit:
        candidates.append(direct)

    unique: list[QuickConnectCandidate] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (candidate.kind, candidate.profile_name or candidate.label)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique


def profile_quick_connect_matches(query: str, profiles: list[Profile], *, limit: int) -> list[QuickConnectCandidate]:
    normalized = query.lower()
    scored: list[tuple[int, str, Profile]] = []
    for profile in profiles:
        fields = [profile.name, profile.group, profile.protocol, profile.display_target, *profile.tags]
        haystack = " ".join(str(field) for field in fields if field).lower()
        if normalized not in haystack:
            continue
        score = 30
        if profile.name.lower() == normalized:
            score = 0
        elif profile.name.lower().startswith(normalized):
            score = 5
        elif profile.display_target.lower().startswith(normalized):
            score = 10
        elif profile.group.lower().startswith(normalized):
            score = 20
        scored.append((score, profile.name.lower(), profile))
    return [
        QuickConnectCandidate(
            kind="profile",
            label=f"{profile.protocol.upper()}  {profile.name}",
            detail=profile.display_target,
            profile_name=profile.name,
        )
        for _score, _name, profile in sorted(scored)[:limit]
    ]


def parse_quick_connect_profile(text: str) -> QuickConnectCandidate | None:
    query = text.strip()
    if not query:
        return None
    if looks_like_url(query):
        return quick_connect_url_candidate(query)
    parsed_uri = urlparse(query)
    if parsed_uri.scheme.lower() in QUICK_CONNECT_PROTOCOLS and parsed_uri.netloc:
        if parsed_uri.scheme.lower() in {"http", "https"}:
            return quick_connect_url_candidate(query)
        try:
            parsed_port = parsed_uri.port
        except ValueError:
            return None
        return quick_connect_parsed_endpoint_candidate(
            parsed_uri.scheme.lower(),
            parsed_uri.hostname,
            parsed_port,
            parsed_uri.username,
        )

    parts = query.split(maxsplit=1)
    protocol = "ssh"
    target = query
    if len(parts) == 2 and parts[0].lower() in QUICK_CONNECT_PROTOCOLS:
        protocol = parts[0].lower()
        target = parts[1].strip()
    elif not quick_connect_is_host_like(query):
        return None

    if protocol in {"http", "https"}:
        url = target if looks_like_url(target) else f"{protocol}://{target}"
        return quick_connect_url_candidate(url)

    endpoint = parse_quick_connect_endpoint(target)
    if endpoint is None:
        return None
    host, port, username = endpoint
    return quick_connect_parsed_endpoint_candidate(protocol, host, port, username)


def quick_connect_parsed_endpoint_candidate(
    protocol: str,
    host: str | None,
    port: int | None,
    username: str | None,
) -> QuickConnectCandidate | None:
    if not host:
        return None
    profile = Profile(
        name=quick_connect_profile_name(protocol, host),
        protocol=protocol,
        host=host,
        port=port or QUICK_CONNECT_DEFAULT_PORTS.get(protocol),
        username=username,
        group="quick-connect",
        tags=["quick-connect"],
    )
    return QuickConnectCandidate(
        kind="direct",
        label=f"DIRECT {protocol.upper()}  {profile.display_target}",
        detail="temporary quick-connect target",
        profile=profile,
    )


def quick_connect_url_candidate(url: str) -> QuickConnectCandidate | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    profile = Profile(
        name=quick_connect_profile_name(parsed.scheme, parsed.netloc),
        protocol=parsed.scheme,
        url=url,
        group="quick-connect",
        tags=["quick-connect"],
    )
    return QuickConnectCandidate(
        kind="direct",
        label=f"DIRECT {parsed.scheme.upper()}  {parsed.netloc}",
        detail=url,
        profile=profile,
    )


def parse_quick_connect_endpoint(target: str) -> tuple[str, int | None, str | None] | None:
    parsed = urlparse(f"//{target.strip()}")
    host = parsed.hostname
    if not host:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    return host, port, parsed.username


def quick_connect_is_explicit(query: str) -> bool:
    first = query.split(maxsplit=1)[0].lower()
    return first in QUICK_CONNECT_PROTOCOLS or "://" in query


def quick_connect_is_host_like(query: str) -> bool:
    return bool(
        "@" in query
        or re.search(r":\d+$", query)
        or re.search(r"\d+\.\d+\.\d+\.\d+", query)
        or "." in query
    )


def looks_like_url(query: str) -> bool:
    return query.lower().startswith(("http://", "https://"))


def quick_connect_profile_name(protocol: str, target: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", target).strip("-") or "target"
    return f"quick-{protocol}-{slug}"[:80]


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


def create_main_window(argv: list[str] | None = None, *, show: bool = False):
    try:
        from PyQt6.QtCore import (
            QBuffer,
            QByteArray,
            QEvent,
            QIODevice,
            QPoint,
            QProcess,
            QSize,
            Qt,
            QTimer,
            QUrl,
        )
        from PyQt6.QtGui import (
            QAction,
            QBrush,
            QClipboard,
            QColor,
            QDesktopServices,
            QFont,
            QGuiApplication,
            QIcon,
            QKeySequence,
            QPainter,
            QPalette,
            QPen,
            QPixmap,
            QPolygon,
            QShortcut,
            QSyntaxHighlighter,
            QTextCharFormat,
            QTextCursor,
            QTransform,
        )
        from PyQt6.QtWidgets import (
            QAbstractButton,
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QScrollArea,
            QSizePolicy,
            QSplitter,
            QStackedWidget,
            QStatusBar,
            QStyle,
            QTabBar,
            QTabWidget,
            QTextEdit,
            QToolBar,
            QToolButton,
            QTreeWidget,
            QTreeWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except Exception as exc:  # pragma: no cover - optional dependency
        raise GuiDependencyError("PyQt6 is not installed. Install with: pip install -e '.[desktop]'") from exc

    def _application_clipboard() -> QClipboard:
        return _required_gui_value(QApplication.clipboard(), "application clipboard")

    def _application_instance() -> QApplication:
        instance = QApplication.instance()
        if not isinstance(instance, QApplication):
            raise RuntimeError("required GUI value is unavailable: Qt application")
        return instance

    def _widget_style(widget: QWidget) -> QStyle:
        return _required_gui_value(widget.style(), f"style for {type(widget).__name__}")

    def _terminal_process_backend(
        parent,
        plan: TerminalPanePlan,
        _profile: Profile | None,
    ):
        """Select a real local pseudo-console for interactive Windows sessions."""

        program_name = Path(plan.command[0]).name.lower() if plan.command else ""
        openssh_program = program_name in {"ssh", "ssh.exe", "sftp", "sftp.exe"}
        local_shell_program = bool(
            plan.source == "shell"
            and program_name
            in {
                "cmd",
                "cmd.exe",
                "powershell",
                "powershell.exe",
                "pwsh",
                "pwsh.exe",
            }
        )
        use_windows_conpty = bool(
            sys.platform == "win32"
            and (openssh_program or local_shell_program)
        )
        if not use_windows_conpty:
            return QProcess(parent), ""
        try:
            from .qt_terminal_process import QtConPtyProcess
            from .windows_conpty import conpty_support

            support = conpty_support()
            if support.supported:
                return QtConPtyProcess(parent), ""
            reason = support.reason
        except (ImportError, OSError, RuntimeError) as exc:
            reason = str(exc)
        if openssh_program:
            return (
                _openssh_pipe_fallback_process(parent),
                (
                    "Local ConPTY is unavailable, so this SSH pane is using a pipe fallback. "
                    "Interactive prompts are unsupported; this launch is restricted to "
                    f"trusted-host key/agent authentication: {reason}"
                ),
            )
        process = QProcess(parent)
        process.setProperty("terminalLineInputFallback", True)
        return (
            process,
            "Local ConPTY is unavailable, so this shell is using line-oriented input: "
            f"{reason}",
        )

    def _openssh_pipe_fallback_process(parent):
        process = QProcess(parent)
        process.setProperty("terminalOpenSshPipeFallback", True)
        return process

    def _literal_label(text: object = "", parent=None) -> QLabel:
        """Create a QLabel that never interprets profile or route text as rich text."""

        label = QLabel(str(text), parent)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def _literal_message_box(
        parent,
        icon,
        title: object,
        message: object,
        *,
        buttons=QMessageBox.StandardButton.Ok,
        default_button=None,
    ):
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

    class _ScreenBoundedDialog(QDialog):
        def showEvent(self, event) -> None:
            super().showEvent(event)
            QTimer.singleShot(0, lambda: _clamp_dialog_frame_to_parent_screen(self))

    class LiteralTextEdit(QTextEdit):
        """QTextEdit whose append API never interprets terminal or profile text as HTML."""

        def append(self, text: object) -> None:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            if cursor.position() > 0:
                cursor.insertBlock()
            cursor.insertText(str(text), QTextCharFormat())
            self.setTextCursor(cursor)
            self.ensureCursorVisible()

    TREE_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 31
    TREE_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 32
    TREE_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 33
    TREE_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 34
    TREE_ROW_STATIC_HEIGHT_ROLE = int(Qt.ItemDataRole.UserRole) + 35
    TREE_ROW_STATIC_ICON_X_ROLE = int(Qt.ItemDataRole.UserRole) + 36
    TREE_ROW_STATIC_LABEL_X_ROLE = int(Qt.ItemDataRole.UserRole) + 37
    TREE_ROW_STATIC_TARGET_X_ROLE = int(Qt.ItemDataRole.UserRole) + 38
    SFTP_ROW_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 41
    SFTP_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 42
    SFTP_ROW_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 43
    SFTP_ROW_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 44
    SFTP_ROW_CONTRACT_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 45
    SFTP_ROW_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 46
    SFTP_ROW_SOURCE_PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 47
    SFTP_ROW_INDEX_ROLE = int(Qt.ItemDataRole.UserRole) + 48
    SFTP_ROW_SELECTED_BY_ROUTE_ROLE = int(Qt.ItemDataRole.UserRole) + 49
    SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 50
    MREMOTENG_ROUTE_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 61
    MREMOTENG_ROUTE_ROLE_ROLE = int(Qt.ItemDataRole.UserRole) + 62
    MREMOTENG_ROUTE_PROFILE_ROLE = int(Qt.ItemDataRole.UserRole) + 63
    MREMOTENG_ROUTE_TAB_ROLE = int(Qt.ItemDataRole.UserRole) + 64
    MREMOTENG_ROUTE_PROTOCOL_ROLE = int(Qt.ItemDataRole.UserRole) + 65
    MREMOTENG_ROUTE_STATE_ROLE = int(Qt.ItemDataRole.UserRole) + 66
    MREMOTENG_ROUTE_SELECTED_ROLE = int(Qt.ItemDataRole.UserRole) + 67
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

    class TerminalPane(QWidget):
        STOP_POLICY = ProcessStopPolicy()

        def __init__(
            self,
            plan: TerminalPanePlan,
            *,
            profile: Profile | None = None,
            autostart: bool = True,
        ) -> None:
            super().__init__()
            self.setObjectName("terminalPane")
            self.plan = plan
            self.profile = profile
            self.process, self._terminal_backend_warning = _terminal_process_backend(
                self,
                plan,
                profile,
            )
            self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            self._restart_after_stop = False
            self._rendered_terminal_text = ""
            self._pty_initial_clear_pending = False
            self._pty_startup_probe = ""
            self._terminal_scroll_generation = 0
            self._process_output_buffer = bytearray()
            self._process_output_flush_scheduled = False
            self._process_output_flush_count = 0
            self.setProperty("terminalAutostart", bool(autostart))
            self.setProperty("terminalOutputCoalescing", "8ms-event-loop-burst")
            self.startup_preamble = ""
            self.show_launch_command = True
            self.output_context_menu_builder: Callable[[TerminalPane], QMenu] | None = None
            self._stop_timer = QTimer(self)
            self._stop_timer.setSingleShot(True)
            self._stop_timer.timeout.connect(self.kill_after_stop_timeout)
            self._process_output_timer = QTimer(self)
            self._process_output_timer.setSingleShot(True)
            self._process_output_timer.setInterval(8)
            self._process_output_timer.timeout.connect(self.flush_process_output)

            self.title = QLabel(plan.title)
            self.title.setObjectName("terminalTitle")
            self.title.setTextFormat(Qt.TextFormat.PlainText)
            self.source = QLabel(plan.source)
            self.source.setObjectName("terminalSource")
            self.source.setTextFormat(Qt.TextFormat.PlainText)
            self.source.setToolTip(_safe_tooltip_html(plan.source))
            self.source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            self.status = QLabel("ready")
            self.status.setObjectName("paneStatus")
            self.command_preview = QLabel(plan.printable())
            self.command_preview.setObjectName("terminalCommand")
            self.command_preview.setTextFormat(Qt.TextFormat.PlainText)
            self.command_preview.setToolTip(_safe_tooltip_html(plan.printable()))
            self.command_preview.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.command_preview.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            self.output = QTextEdit()
            self.output.setObjectName("terminalOutput")
            self.output.setReadOnly(True)
            self.output.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            # The QTextEdit caret is not the remote PTY cursor.  Leaving it
            # visible makes a tiny blinking mark appear at the document end
            # during tab transitions and Vim redraws, which users perceive as
            # a second miniature terminal.  Remote cursor state is retained by
            # the ANSI screen buffer instead.
            hide_qt_caret = getattr(self.output, "setCursorWidth", None)
            if callable(hide_qt_caret):
                hide_qt_caret(0)
            self.output.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.output.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            self.output.document().setUndoRedoEnabled(False)
            self.setFocusProxy(self.output)
            self.output.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.output.installEventFilter(self)
            self.output_viewport = _required_gui_value(
                self.output.viewport(),
                "terminal output viewport",
            )
            self.output_viewport.installEventFilter(self)
            self.terminal_emulator = AnsiTerminalTranscript()
            self.output.setProperty("terminalEmulatorBackend", TERMINAL_EMULATOR_BACKEND)
            self.output.setProperty(
                "terminalEmulatorPty",
                bool(getattr(self.process, "is_pty", False)),
            )
            self.output.setProperty(
                "terminalProcessBackend",
                "windows-conpty"
                if bool(getattr(self.process, "is_pty", False))
                else "qt-process-pipe",
            )
            self.output.setProperty(
                "terminalRemotePtyRequested",
                any(argument in {"-t", "-tt"} for argument in plan.command),
            )
            self.output.setProperty("terminalDirectKeyInput", True)
            self.output.setProperty("terminalQtCaretHidden", True)
            self.output.setProperty("terminalAlternateScreenActive", False)
            self.output.setProperty("terminalAlternateScreenRedraw", False)
            self.output.setProperty("terminalBracketedPasteActive", False)
            self.output.setProperty("terminalLastPasteWasBracketed", False)
            self.output.setProperty("terminalEmulatorResponseCount", 0)
            self.output.setProperty("terminalLastEmulatorResponse", b"")
            self.output.setProperty("terminalOutputBufferedBytes", 0)
            self.output.setProperty("terminalOutputFlushCount", 0)
            self.output.setProperty("terminalMouseMultilineSelection", True)
            self.output.setProperty(
                "terminalKeyboardSelectionShortcuts",
                [
                    "Shift+Left/Right",
                    "Shift+Up/Down",
                    "Shift+Home/End",
                    "Shift+PageUp/PageDown",
                ],
            )
            self.output.setProperty(
                "terminalCopyShortcuts",
                ["Ctrl+C with selection", "Ctrl+Shift+C"],
            )
            self.output.setProperty(
                "terminalTypingAfterSelection",
                "collapse-selection-and-forward-to-process",
            )
            self.output.setProperty("terminalEmulatorScrollbackLimit", self.terminal_emulator.max_scrollback_lines)
            self.output.setProperty("terminalAnsiSgrColorEnabled", True)
            self.output.setProperty(
                "terminalAnsiSgrCapabilities",
                [
                    "16-color",
                    "bright-color",
                    "256-color",
                    "rgb",
                    "foreground-reset",
                    "background-reset",
                    "bold",
                    "underline",
                    "inverse",
                ],
            )
            self.output.setProperty("terminalAnsiEscapeCodesExcludedFromPlainText", True)
            self.syntax_rules = default_terminal_syntax_rules()
            self.output.setProperty("terminalSyntaxHighlightingEnabled", True)
            self.output.setProperty("terminalSyntaxHighlightRuleKeys", list(terminal_syntax_rule_keys(self.syntax_rules)))
            self.output.setProperty("terminalLinkActivation", "ctrl-click-http-https")
            self.output.setProperty("terminalLinkAllowedSchemes", ["http", "https"])
            self.output.setProperty("terminalLinkAutoOpen", False)
            self.output.setProperty("terminalUrlHighlightColor", "#54ccef")
            self.input = QLineEdit()
            self.input.setObjectName("terminalInput")
            self.input.setPlaceholderText("stdin, shell command or interactive input")
            self._secret_prompt_active = False
            self.input.setProperty("terminalSecretInputActive", False)
            self.macro_capture_state: MobaMacroTerminalCaptureState | None = None
            self.macro_last_recording: MobaMacroRecording | None = None
            self.macro_last_injection: MobaMacroTerminalReplayInjection | None = None
            self.macro_last_event_at: float | None = None
            self.macro_replay_active = False
            self.macro_replay_cancelled = False
            self.macro_replay_sequence = 0
            self.start_button = self.terminal_button("Start", "SP_MediaPlay", "Start process")
            self.restart_button = self.terminal_button(
                "Restart", "SP_BrowserReload", "Restart process"
            )
            self.stop_button = self.terminal_button("Stop", "SP_MediaStop", "Stop process")
            self.copy_button = self.terminal_button(
                "Copy",
                "SP_DialogSaveButton",
                "Copy selected terminal output, or the launch command when nothing is selected",
            )
            self.clear_button = self.terminal_button(
                "Clear", "SP_DialogResetButton", "Clear terminal output"
            )
            self.macro_record_button = self.terminal_button(
                "Macro Rec", "SP_DialogYesButton", "Record terminal macro"
            )
            self.macro_stop_button = self.terminal_button(
                "Macro Stop", "SP_DialogApplyButton", "Stop terminal macro"
            )
            self.macro_cancel_button = self.terminal_button(
                "Macro Cancel", "SP_DialogCancelButton", "Cancel macro"
            )
            self.macro_replay_button = self.terminal_button(
                "Macro Replay", "SP_MediaSeekForward", "Replay terminal macro"
            )

            self.header = QFrame()
            self.header.setObjectName("terminalHeader")
            header_layout = QVBoxLayout(self.header)
            header_layout.setContentsMargins(8, 6, 8, 6)
            header_layout.setSpacing(5)
            identity_layout = QHBoxLayout()
            identity_layout.setContentsMargins(0, 0, 0, 0)
            identity_layout.setSpacing(8)
            identity_layout.addWidget(self.title)
            identity_layout.addWidget(self.source, 1)
            identity_layout.addWidget(self.status)
            header_layout.addLayout(identity_layout)
            self.terminal_action_buttons = [
                self.start_button,
                self.restart_button,
                self.stop_button,
                self.copy_button,
                self.clear_button,
                self.macro_record_button,
                self.macro_stop_button,
                self.macro_cancel_button,
                self.macro_replay_button,
            ]
            self.action_grid = QGridLayout()
            self.action_grid.setContentsMargins(0, 0, 0, 0)
            self.action_grid.setHorizontalSpacing(5)
            self.action_grid.setVerticalSpacing(4)
            header_layout.addLayout(self.action_grid)
            self._terminal_action_layout: tuple[int, bool] | None = None
            # Start with a compact layout.  At construction time the pane has no
            # negotiated width yet; assuming a wide pane here makes the action
            # grid's size hint widen the entire application before resizeEvent
            # gets a chance to select the compact layout.
            self.layout_terminal_actions(0)

            self.command_row = QFrame()
            self.command_row.setObjectName("terminalCommandRow")
            command_layout = QHBoxLayout(self.command_row)
            command_layout.setContentsMargins(8, 3, 8, 5)
            command_layout.addWidget(self.command_preview, 1)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.header)
            layout.addWidget(self.command_row)
            layout.addWidget(self.output, 1)
            layout.addWidget(self.input)

            self.start_button.clicked.connect(self.start)
            self.restart_button.clicked.connect(self.restart)
            self.stop_button.clicked.connect(self.request_stop)
            self.copy_button.clicked.connect(self.copy_command)
            self.clear_button.clicked.connect(self.clear_output)
            self.macro_record_button.clicked.connect(self.start_macro_capture)
            self.macro_stop_button.clicked.connect(self.stop_macro_capture)
            self.macro_cancel_button.clicked.connect(self.cancel_macro_capture)
            self.macro_replay_button.clicked.connect(self.replay_macro_capture)
            self.input.returnPressed.connect(self.send_input)
            self.output.customContextMenuRequested.connect(self.show_output_context_menu)
            self.process.readyReadStandardOutput.connect(self.read_stdout)
            self.process.readyReadStandardError.connect(self.read_stderr)
            self.process.started.connect(self.on_started)
            self.process.errorOccurred.connect(self.on_error)
            self.process.finished.connect(self.on_finished)
            self.set_status("ready", "ready")
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()
            if autostart:
                self.start()

        def terminal_button(self, label: str, icon_name: str, tooltip: str) -> QToolButton:
            button = QToolButton()
            button.setObjectName("terminalAction")
            button.setText(label)
            button.setToolTip(tooltip)
            action_key = label.lower().replace(" ", "-")
            button.setProperty("terminalActionKey", action_key)
            button.setProperty("terminalActionLabel", label)
            button.setProperty("terminalActionTooltip", tooltip)
            icon = getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)
            button.setIcon(_widget_style(self).standardIcon(icon))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # The grid owns the available width.  Ignoring the button text size
            # hint lets resizeEvent cross its breakpoints instead of trapping the
            # parent window above a stale minimum width.
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.setAccessibleName(label)
            return button

        def resizeEvent(self, event) -> None:  # noqa: N802
            super().resizeEvent(event)
            self.layout_terminal_actions(event.size().width())
            self.resize_terminal_backend()

        def resize_terminal_backend(self) -> None:
            metrics = self.output.fontMetrics()
            cell_width = max(1, metrics.horizontalAdvance("M"))
            cell_height = max(1, metrics.lineSpacing())
            viewport = self.output_viewport.size()
            columns = max(20, viewport.width() // cell_width)
            rows = max(5, viewport.height() // cell_height)
            self.terminal_emulator.set_screen_size(columns, rows)
            resize = getattr(self.process, "setTerminalSize", None)
            if resize is not None:
                resize(columns, rows)

        def layout_terminal_actions(self, width: int) -> None:
            compact = width < 620
            columns = 9 if width >= 1500 else 5 if width >= 620 else 9 if width >= 360 else 5
            layout_key = (columns, compact)
            if self._terminal_action_layout == layout_key:
                return
            self._terminal_action_layout = layout_key
            style = (
                Qt.ToolButtonStyle.ToolButtonIconOnly
                if compact
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            for index, button in enumerate(self.terminal_action_buttons):
                self.action_grid.removeWidget(button)
                button.setToolButtonStyle(style)
                self.action_grid.addWidget(button, index // columns, index % columns)
            self.action_grid.invalidate()
            header_layout = self.header.layout()
            if header_layout is not None:
                header_layout.invalidate()
            self.header.updateGeometry()
            self.updateGeometry()

        def is_running(self) -> bool:
            return self.process.state() != QProcess.ProcessState.NotRunning

        def eventFilter(self, watched, event) -> bool:  # noqa: N802
            terminal_targets = (self.output, self.output_viewport)
            if watched in terminal_targets and event.type() == QEvent.Type.MouseButtonPress:
                self.output.setFocus(Qt.FocusReason.MouseFocusReason)
                self.output.setProperty("terminalLastInputSurface", "viewport")
            if (
                watched is self.output_viewport
                and event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and not self.output.textCursor().hasSelection()
            ):
                href = self.output.anchorAt(event.position().toPoint())
                if href and self.open_terminal_link(href):
                    event.accept()
                    return True
            if watched in terminal_targets and event.type() == QEvent.Type.InputMethod:
                committed = event.commitString()
                if committed:
                    self.send_raw_input(committed.encode("utf-8"))
                    event.accept()
                    return True
            if watched in terminal_targets and event.type() == QEvent.Type.KeyPress:
                selection = self.output.textCursor().selectedText()
                if self.is_terminal_selection_navigation(event):
                    # A terminal still needs a usable local scrollback selection.
                    # Let QTextEdit extend the cursor selection instead of sending
                    # Shift+Arrow/Home/End/Page keys to the remote PTY.
                    return super().eventFilter(watched, event)
                if (
                    event.matches(QKeySequence.StandardKey.Copy)
                    and selection
                ) or self.is_terminal_copy_shortcut(event):
                    self.copy_terminal_selection()
                    return True
                if event.matches(
                    QKeySequence.StandardKey.Paste
                ) or self.is_terminal_paste_shortcut(event):
                    self.paste_to_terminal()
                    return True
                payload = self.terminal_key_payload(event)
                if payload is not None:
                    # Ordinary terminal input after a local selection must be
                    # delivered to the process, not replace the read-only
                    # transcript.  Collapse the stale selection first so the
                    # next output update starts from an unambiguous cursor.
                    self.clear_terminal_selection_for_remote_input()
                    self.send_raw_input(payload)
                    return True
            return super().eventFilter(watched, event)

        @staticmethod
        def is_terminal_selection_navigation(event) -> bool:
            """Return whether *event* extends the local scrollback selection."""

            if not (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                return False
            return event.key() in {
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
            }

        @staticmethod
        def is_terminal_copy_shortcut(event) -> bool:
            """Recognize the terminal-safe Ctrl+Shift+C copy shortcut."""

            modifiers = event.modifiers()
            return bool(
                event.key() == Qt.Key.Key_C
                and modifiers & Qt.KeyboardModifier.ControlModifier
                and modifiers & Qt.KeyboardModifier.ShiftModifier
                and not modifiers & Qt.KeyboardModifier.AltModifier
                and not modifiers & Qt.KeyboardModifier.MetaModifier
            )

        @staticmethod
        def is_terminal_paste_shortcut(event) -> bool:
            """Recognize the terminal-safe Ctrl+Shift+V paste shortcut."""

            modifiers = event.modifiers()
            return bool(
                event.key() == Qt.Key.Key_V
                and modifiers & Qt.KeyboardModifier.ControlModifier
                and modifiers & Qt.KeyboardModifier.ShiftModifier
                and not modifiers & Qt.KeyboardModifier.AltModifier
                and not modifiers & Qt.KeyboardModifier.MetaModifier
            )

        def clear_terminal_selection_for_remote_input(self) -> None:
            cursor = self.output.textCursor()
            if not cursor.hasSelection():
                return
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.output.setTextCursor(cursor)
            self.output.setProperty(
                "terminalSelectionClearedForRemoteInput",
                True,
            )

        @staticmethod
        def validated_terminal_link(href: str) -> QUrl | None:
            """Return a safe browser target for an explicit terminal link action."""

            url = QUrl(str(href).strip())
            if (
                not url.isValid()
                or url.isRelative()
                or url.scheme().lower() not in {"http", "https"}
                or not url.host()
            ):
                return None
            return url

        def open_terminal_link(self, href: str) -> bool:
            """Open an HTTP(S) terminal link only after the user's Ctrl+click."""

            url = self.validated_terminal_link(href)
            if url is None:
                self.output.setProperty("terminalLastRejectedLink", str(href))
                return False
            self.output.setProperty("terminalLastOpenedLink", url.toString())
            opened = bool(QDesktopServices.openUrl(url))
            self.output.setProperty("terminalLastLinkOpenSucceeded", opened)
            return opened

        def terminal_key_payload(self, event) -> bytes | None:
            """Translate a focused terminal key event to conventional TTY bytes."""

            key = event.key()
            modifiers = event.modifiers()
            shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
            alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
            meta = bool(modifiers & Qt.KeyboardModifier.MetaModifier)
            group_switch = bool(modifiers & Qt.KeyboardModifier.GroupSwitchModifier)
            if meta:
                return None
            text = event.text()
            if (
                text
                and (group_switch or (control and alt))
                and all(character.isprintable() for character in text)
            ):
                # Windows reports AltGr as Ctrl+Alt.  Preserve the composed
                # printable character instead of translating its physical key
                # to a terminal control byte (for example AltGr+Q -> "@").
                return text.encode("utf-8")
            if control and not alt and key == Qt.Key.Key_Space:
                return b"\x00"
            if control and int(Qt.Key.Key_A) <= int(key) <= int(Qt.Key.Key_Z):
                return bytes((int(key) - int(Qt.Key.Key_A) + 1,))
            if control and not alt:
                # Qt reports Ctrl-[ and the other control punctuation keys as
                # printable text.  They still need their conventional TTY
                # bytes (Ctrl-[ is Vim's canonical Escape sequence).
                control_punctuation = {
                    "@": b"\x00",
                    "[": b"\x1b",
                    "\\": b"\x1c",
                    "]": b"\x1d",
                    "^": b"\x1e",
                    "_": b"\x1f",
                }
                punctuation_payload = control_punctuation.get(text)
                if punctuation_payload is None:
                    control_punctuation_keys = {
                        getattr(Qt.Key, "Key_At", object()): b"\x00",
                        getattr(Qt.Key, "Key_BracketLeft", object()): b"\x1b",
                        getattr(Qt.Key, "Key_Backslash", object()): b"\x1c",
                        getattr(Qt.Key, "Key_BracketRight", object()): b"\x1d",
                        getattr(Qt.Key, "Key_AsciiCircum", object()): b"\x1e",
                        getattr(Qt.Key, "Key_Underscore", object()): b"\x1f",
                    }
                    punctuation_payload = control_punctuation_keys.get(key)
                    if punctuation_payload is None:
                        # Some Windows keyboard layouts expose punctuation as
                        # the printable ASCII key code but leave event.text()
                        # empty while Ctrl is held.  Keep Vim's Ctrl-[ and
                        # the remaining C0 punctuation controls reliable in
                        # that representation too.
                        punctuation_payload = {
                            0x40: b"\x00",
                            0x5B: b"\x1b",
                            0x5C: b"\x1c",
                            0x5D: b"\x1d",
                            0x5E: b"\x1e",
                            0x5F: b"\x1f",
                        }.get(int(key))
                if punctuation_payload is not None:
                    return punctuation_payload
            if shift and key == Qt.Key.Key_Tab:
                return b"\x1b[Z"
            function_keys = {
                Qt.Key.Key_F1: b"\x1bOP",
                Qt.Key.Key_F2: b"\x1bOQ",
                Qt.Key.Key_F3: b"\x1bOR",
                Qt.Key.Key_F4: b"\x1bOS",
                Qt.Key.Key_F5: b"\x1b[15~",
                Qt.Key.Key_F6: b"\x1b[17~",
                Qt.Key.Key_F7: b"\x1b[18~",
                Qt.Key.Key_F8: b"\x1b[19~",
                Qt.Key.Key_F9: b"\x1b[20~",
                Qt.Key.Key_F10: b"\x1b[21~",
                Qt.Key.Key_F11: b"\x1b[23~",
                Qt.Key.Key_F12: b"\x1b[24~",
            }
            function_payload = function_keys.get(key)
            if function_payload is not None and not (shift or control):
                return (
                    b"\x1b" + function_payload
                    if alt
                    else function_payload
                )
            cursor_navigation = {
                Qt.Key.Key_Up: "A",
                Qt.Key.Key_Down: "B",
                Qt.Key.Key_Right: "C",
                Qt.Key.Key_Left: "D",
                Qt.Key.Key_Home: "H",
                Qt.Key.Key_End: "F",
            }
            tilde_navigation = {
                Qt.Key.Key_Insert: 2,
                Qt.Key.Key_Delete: 3,
                Qt.Key.Key_PageUp: 5,
                Qt.Key.Key_PageDown: 6,
            }
            if key in cursor_navigation and (shift or alt or control):
                modifier = 1 + int(shift) + 2 * int(alt) + 4 * int(control)
                return f"\x1b[1;{modifier}{cursor_navigation[key]}".encode("ascii")
            if key in tilde_navigation and (shift or alt or control):
                modifier = 1 + int(shift) + 2 * int(alt) + 4 * int(control)
                return f"\x1b[{tilde_navigation[key]};{modifier}~".encode("ascii")
            special = {
                Qt.Key.Key_Return: (
                    b"\r" if bool(getattr(self.process, "is_pty", False)) else b"\n"
                ),
                Qt.Key.Key_Enter: (
                    b"\r" if bool(getattr(self.process, "is_pty", False)) else b"\n"
                ),
                Qt.Key.Key_Backspace: b"\x7f",
                Qt.Key.Key_Tab: b"\t",
                Qt.Key.Key_Escape: b"\x1b",
                Qt.Key.Key_Up: b"\x1b[A",
                Qt.Key.Key_Down: b"\x1b[B",
                Qt.Key.Key_Right: b"\x1b[C",
                Qt.Key.Key_Left: b"\x1b[D",
                Qt.Key.Key_Home: b"\x1b[H",
                Qt.Key.Key_End: b"\x1b[F",
                Qt.Key.Key_Insert: b"\x1b[2~",
                Qt.Key.Key_Delete: b"\x1b[3~",
                Qt.Key.Key_PageUp: b"\x1b[5~",
                Qt.Key.Key_PageDown: b"\x1b[6~",
            }
            payload = special.get(key)
            if payload is None:
                if not text or control:
                    return None
                payload = text.encode("utf-8")
            return b"\x1b" + payload if alt and payload != b"\x1b" else payload

        def send_raw_input(self, payload: bytes) -> None:
            if not payload:
                return
            if not self.is_running():
                self.append_text("[stdin ignored: process is not running]\n")
                return
            accepted = self.process.write(payload)
            if accepted is None:
                accepted = len(payload)
            self.output.setProperty("terminalLastInputBytesRequested", len(payload))
            self.output.setProperty("terminalLastInputBytesAccepted", int(accepted))
            # Rendering the process response decides whether the user was
            # following the live tail.  Scrolling here unconditionally makes
            # cursor-addressed programs (notably htop) jump to the bottom on
            # every keypress and steals a deliberate scrollback position.
            self.output.setProperty("terminalInputPreservedScrollPosition", True)
            if int(accepted) < len(payload):
                self.set_status("input error", "error")
                self.append_text(
                    "\n[stdin error: terminal process did not accept the complete input]\n"
                )

        def paste_to_terminal(self) -> None:
            text = _application_clipboard().text()
            if not text:
                return
            if self.is_running():
                payload = text.encode("utf-8")
                if self.terminal_emulator.bracketed_paste_active:
                    # Vim, readline, and modern shells ask for bracketed paste
                    # so pasted newlines are not mistaken for an immediate
                    # sequence of commands.  Preserve that contract instead
                    # of feeding the clipboard as an unbounded key stream.
                    payload = b"\x1b[200~" + payload + b"\x1b[201~"
                    self.output.setProperty("terminalLastPasteWasBracketed", True)
                else:
                    self.output.setProperty("terminalLastPasteWasBracketed", False)
                self.send_raw_input(payload)
                return
            self.input.insert(text)
            self.input.setFocus(Qt.FocusReason.OtherFocusReason)

        def copy_terminal_selection(self) -> None:
            selection = self.output.textCursor().selectedText().replace("\u2029", "\n")
            if selection:
                self.output.setProperty("terminalLastCopiedText", selection)
                _application_clipboard().setText(selection)

        def build_output_context_menu(self) -> QMenu:
            if callable(self.output_context_menu_builder):
                return self.output_context_menu_builder(self)
            menu = QMenu(self.output)
            selection = bool(self.output.textCursor().selectedText())
            clipboard_text = bool(_application_clipboard().text())
            copy_action = _required_gui_value(menu.addAction("Copy"), "copy action")
            copy_action.setEnabled(selection)
            copy_action.triggered.connect(self.copy_terminal_selection)
            paste_action = _required_gui_value(
                menu.addAction("Paste to terminal"),
                "paste action",
            )
            paste_action.setEnabled(clipboard_text)
            paste_action.triggered.connect(self.paste_to_terminal)
            select_action = _required_gui_value(
                menu.addAction("Select all"),
                "select-all action",
            )
            select_action.triggered.connect(self.output.selectAll)
            menu.addSeparator()
            clear_action = _required_gui_value(
                menu.addAction("Clear terminal"),
                "clear-terminal action",
            )
            clear_action.triggered.connect(self.clear_output)
            restart_action = _required_gui_value(
                menu.addAction("Restart session"),
                "restart-session action",
            )
            restart_action.setEnabled(bool(self.plan.command))
            restart_action.triggered.connect(self.restart)
            stop_action = _required_gui_value(
                menu.addAction("Stop session"),
                "stop-session action",
            )
            stop_action.setEnabled(self.is_running())
            stop_action.triggered.connect(self.request_stop)
            return menu

        def show_output_context_menu(self, position: QPoint) -> None:
            menu = self.build_output_context_menu()
            menu.exec(self.output_viewport.mapToGlobal(position))
            menu.deleteLater()

        def start(self) -> None:
            if self.is_running():
                return
            if not self.plan.command:
                self.append_text("[error] empty terminal command\n")
                return
            if self.profile is not None:
                try:
                    assert_profile_launch_allowed(self.profile, surface="gui")
                except ValueError as exc:
                    self.set_status("policy blocked", "blocked")
                    self.append_text(f"[policy blocked] {exc}\n")
                    self.update_process_actions()
                    return
            self.output.clear()
            self._rendered_terminal_text = ""
            self.terminal_emulator.reset()
            self._process_output_buffer.clear()
            self._process_output_flush_scheduled = False
            self._process_output_timer.stop()
            self.disarm_initial_pty_clear_recovery()
            self.set_status("starting", "starting")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.input.setEnabled(False)
            self.append_text(self.terminal_startup_context_text())
            self.arm_initial_pty_clear_recovery()
            runtime_command = list(self.plan.command)
            process_property = getattr(self.process, "property", lambda _name: None)
            if bool(process_property("terminalOpenSshPipeFallback")):
                runtime_command = openssh_command_with_overrides(
                    runtime_command,
                    {
                        "BatchMode": "yes",
                        "ConnectTimeout": "10",
                        "StrictHostKeyChecking": "yes",
                    },
                )
            self.process.setProgram(runtime_command[0])
            self.process.setArguments(runtime_command[1:])
            self.resize_terminal_backend()
            self.process.start()
            self.update_process_actions()

        def restart(self, *_args) -> None:
            if self.is_running():
                self.request_stop(restart=True)
                return
            self.start()

        def request_stop(
            self,
            *_args,
            policy: ProcessStopPolicy | None = None,
            restart: bool = False,
        ) -> bool:
            """Request process shutdown without blocking the GUI event loop."""

            if bool(self.property("terminalClosing")):
                self._restart_after_stop = False
            else:
                self._restart_after_stop = self._restart_after_stop or restart
            if not self.is_running():
                if self._restart_after_stop:
                    self._restart_after_stop = False
                    QTimer.singleShot(0, self.start)
                self.update_process_actions()
                return False
            active_policy = policy or self.STOP_POLICY
            self.set_status("stopping", "stopping")
            self.stop_button.setEnabled(False)
            self.append_text("\n[process stopping]\n")
            self.process.terminate()
            self._stop_timer.start(active_policy.terminate_timeout_ms)
            return True

        def kill_after_stop_timeout(self) -> None:
            if not self.is_running():
                return
            self.append_text("[process killed after graceful stop timeout]\n")
            self.process.kill()

        def prepare_for_close(self) -> None:
            """Prevent deferred restart work while a tab or window is closing."""

            self.setProperty("terminalClosing", True)
            self._stop_timer.stop()
            self._process_output_timer.stop()
            self._process_output_buffer.clear()
            self._process_output_flush_scheduled = False
            self._restart_after_stop = False

        def stop(self, policy: ProcessStopPolicy | None = None) -> ProcessStopResult:
            self._stop_timer.stop()
            self._restart_after_stop = False
            if not self.is_running():
                self.update_process_actions()
                return ProcessStopResult(
                    was_running=False,
                    terminate_requested=False,
                    kill_requested=False,
                    finished=True,
                )
            self.set_status("stopping", "stopping")
            self.stop_button.setEnabled(False)
            self.append_text("\n[process stopping]\n")
            result = stop_process(
                self.process,
                not_running_state=QProcess.ProcessState.NotRunning,
                policy=policy or self.STOP_POLICY,
            )
            if result.kill_requested:
                self.append_text("[process killed after graceful stop timeout]\n")
            if not result.finished:
                self.append_text("[warning] process did not exit after kill request]\n")
            self.update_process_actions()
            return result

        def copy_command(self) -> None:
            selection = self.output.textCursor().selectedText().replace("\u2029", "\n")
            clipboard_text = selection or self.plan.printable()
            self.append_text(
                "\n[selected output copied]\n" if selection else "\n[command copied]\n"
            )
            # Updating the transcript can invalidate delayed clipboard ownership
            # on the Windows/offscreen Qt platform.  Publish the detached string
            # after that document mutation so the copied value remains stable.
            self.output.setProperty("terminalLastCopiedText", clipboard_text)
            _application_clipboard().setText(clipboard_text)

        def clear_output(self) -> None:
            self.output.clear()
            self._rendered_terminal_text = ""
            self.terminal_emulator.reset()
            self._process_output_buffer.clear()
            self._process_output_flush_scheduled = False
            self._process_output_timer.stop()
            if self.startup_preamble:
                self.append_text(self.startup_preamble)
            if self.show_launch_command:
                self.append_text(f"$ {self.plan.printable()}\n")

        def set_launch_command_echo_visible(
            self,
            visible: bool,
            *,
            rewrite_current: bool = True,
        ) -> None:
            self.show_launch_command = bool(visible)
            self.output.setProperty(
                "terminalLaunchCommandEchoVisible",
                self.show_launch_command,
            )
            if self.show_launch_command or not rewrite_current:
                return
            command_line = f"$ {self.plan.printable()}\n"
            current = self._rendered_terminal_text
            if command_line not in current:
                return
            self.set_terminal_transcript(current.replace(command_line, "", 1))

        def set_startup_preamble(self, text: str, *, inject_current: bool = True) -> None:
            """Keep a truthful session preamble inside the scrollable transcript."""

            normalized = text.rstrip()
            self.startup_preamble = f"{normalized}\n\n" if normalized else ""
            self.output.setProperty("terminalStartupPreamble", normalized)
            self.output.setProperty(
                "terminalStartupPreambleScrollable",
                bool(self.startup_preamble),
            )
            if not inject_current or not self.startup_preamble:
                return
            current = self._rendered_terminal_text
            if current.startswith(self.startup_preamble):
                return
            self.set_terminal_transcript(f"{self.startup_preamble}{current}")

        def terminal_startup_context_text(self) -> str:
            """Return the app-owned context that precedes process output."""

            parts = [self.startup_preamble]
            if self.show_launch_command:
                parts.append(f"$ {self.plan.printable()}\n")
            parts.extend(f"[note] {note}\n" for note in self.plan.notes)
            if self._terminal_backend_warning:
                parts.append(f"[warning] {self._terminal_backend_warning}\n")
            return "".join(parts)

        def send_input(self) -> None:
            line = self.input.text()
            self.input.clear()
            if not self.is_running():
                self.append_text("[stdin ignored: process is not running]\n")
                return
            secret_input = self._secret_prompt_active
            self.input.setProperty("terminalLastSubmissionWasSecret", secret_input)
            if not secret_input:
                self.capture_macro_input(line)
            # A terminal Enter key is carriage return.  Preserve LF for the
            # ordinary pipe backend so conventional line readers still receive
            # a complete line when no local PTY is available.
            terminator = "\r" if bool(getattr(self.process, "is_pty", False)) else "\n"
            self.send_raw_input((line + terminator).encode("utf-8"))

        def macro_capture_name(self) -> str:
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", self.plan.title).strip("-").lower()
            return f"{slug or 'terminal'}-live"

        def macro_pane_id(self) -> str:
            raw = str(self.property("mobaConnectedRouteActiveTabLabel") or self.plan.title or "terminal-pane")
            slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-") or "terminal-pane"
            return f"{slug}-{id(self):x}"

        def start_macro_capture(self) -> None:
            if self._secret_prompt_active:
                self.append_text("\n[macro recording unavailable during secret input]\n")
                return
            if self.macro_capture_state is not None and self.macro_capture_state.active:
                return
            self.macro_capture_state = start_terminal_macro_capture(
                self.macro_capture_name(),
                pane_id=self.macro_pane_id(),
            )
            self.macro_last_event_at = time.monotonic()
            self.append_text("\n[macro recording started]\n")
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()

        def macro_event_delay_ms(self) -> int:
            now = time.monotonic()
            previous = self.macro_last_event_at or now
            self.macro_last_event_at = now
            return max(0, int((now - previous) * 1000))

        def capture_macro_input(self, line: str) -> None:
            state = self.macro_capture_state
            if state is None or not state.active:
                return
            capture_terminal_macro_input(state, line, delay_ms=self.macro_event_delay_ms())
            self.apply_moba_macro_runtime_properties()

        def stop_macro_capture(self) -> None:
            state = self.macro_capture_state
            if state is None or not state.active:
                return
            try:
                self.macro_last_recording = finish_terminal_macro_capture(
                    state,
                    description="Captured from the PyQt terminal pane.",
                    tags=["gui", "live"],
                )
            except ValueError as exc:
                self.append_text(f"\n[macro recording ignored: {exc}]\n")
            else:
                self.append_text(f"\n[macro recording saved: {self.macro_last_recording.name}]\n")
            self.macro_capture_state = None
            self.macro_last_event_at = None
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()

        def cancel_macro_capture(self) -> None:
            state = self.macro_capture_state
            if state is not None and state.active:
                cancel_terminal_macro_capture(state)
                self.append_text("\n[macro recording cancelled]\n")
                self.macro_capture_state = None
                self.macro_last_event_at = None
            elif self.macro_replay_active:
                self.macro_replay_cancelled = True
                self.macro_replay_sequence += 1
                self.macro_replay_active = False
                self.append_text("\n[macro replay cancelled]\n")
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()

        def replay_macro_capture(self) -> None:
            if self._secret_prompt_active:
                self.append_text("\n[macro replay unavailable during secret input]\n")
                return
            if self.macro_last_recording is None:
                self.append_text("\n[macro replay unavailable: no recorded macro]\n")
                return
            if not self.is_running():
                self.append_text("\n[macro replay unavailable: process is not running]\n")
                return
            injection = build_terminal_macro_replay_injection(self.macro_last_recording, pane_id=self.macro_pane_id())
            self.macro_last_injection = injection
            self.macro_replay_sequence += 1
            self.macro_replay_cancelled = False
            self.macro_replay_active = True
            sequence = self.macro_replay_sequence
            for step, payload in zip(injection.steps, injection.injected_payloads, strict=False):
                delay = max(0, int(step.scheduled_after_ms))
                QTimer.singleShot(delay, lambda payload=payload, sequence=sequence: self.write_macro_replay_payload(payload, sequence))
            QTimer.singleShot(
                max(0, int(injection.total_delay_ms)) + 1,
                lambda sequence=sequence: self.finish_macro_replay_queue(sequence),
            )
            self.append_text(f"\n[macro replay queued: {injection.event_count} event(s)]\n")
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()

        def write_macro_replay_payload(self, payload: str, sequence: int) -> None:
            if sequence != self.macro_replay_sequence or self.macro_replay_cancelled:
                return
            if not self.is_running():
                self.append_text("\n[macro replay stopped: process is not running]\n")
                self.finish_macro_replay_queue(sequence)
                return
            self.process.write(payload.encode("utf-8"))
            self.setProperty("mobaMacroReplayInjectedPayload", payload)
            self.input.setProperty("mobaMacroReplayInjectedPayload", payload)
            self.output.setProperty("mobaMacroReplayInjectedPayload", payload)

        def finish_macro_replay_queue(self, sequence: int) -> None:
            if sequence != self.macro_replay_sequence:
                return
            self.macro_replay_active = False
            self.apply_moba_macro_runtime_properties()
            self.update_process_actions()

        def apply_moba_macro_runtime_properties(self) -> None:
            state = self.macro_capture_state
            recording = self.macro_last_recording
            injection = self.macro_last_injection
            active = bool(state is not None and state.active)
            event_count = len(state.events) if state is not None else 0
            widgets = [
                self,
                self.input,
                self.output,
                self.macro_record_button,
                self.macro_stop_button,
                self.macro_cancel_button,
                self.macro_replay_button,
            ]
            for widget in widgets:
                widget.setProperty("mobaMacroTerminalCaptureSchema", MOBA_MACRO_TERMINAL_CAPTURE_SCHEMA)
                widget.setProperty("mobaMacroTerminalReplaySchema", MOBA_MACRO_TERMINAL_REPLAY_SCHEMA)
                widget.setProperty("mobaMacroPaneId", state.pane_id if state is not None else self.macro_pane_id())
                widget.setProperty("mobaMacroCaptureActive", active)
                widget.setProperty("mobaMacroCaptureCancelled", bool(state is not None and state.cancelled))
                widget.setProperty("mobaMacroCaptureEventCount", event_count)
                widget.setProperty("mobaMacroCaptureControls", ["record", "stop", "cancel"])
                widget.setProperty("mobaMacroCaptureSource", "pyqt-terminal-pane")
                widget.setProperty("mobaMacroLastRecordingName", recording.name if recording is not None else "")
                widget.setProperty("mobaMacroLastRecordingInputSha256", recording.to_dict()["input_sha256"] if recording is not None else "")
                widget.setProperty("mobaMacroReplayInjectionSchema", injection.schema if injection is not None else "")
                widget.setProperty("mobaMacroReplayInjectedEventCount", injection.event_count if injection is not None else 0)
                widget.setProperty("mobaMacroReplayPerKeystrokeTiming", bool(injection is not None and injection.steps))
                widget.setProperty("mobaMacroReplayCancelSupported", True)
                widget.setProperty("mobaMacroReplayActive", self.macro_replay_active)
                widget.setProperty("mobaMacroReplayCancelled", self.macro_replay_cancelled)

        def read_stdout(self) -> None:
            self.queue_process_output(bytes(self.process.readAllStandardOutput()))

        def read_stderr(self) -> None:
            self.queue_process_output(bytes(self.process.readAllStandardError()))

        def queue_process_output(self, payload: bytes) -> None:
            """Coalesce one event-loop burst before rebuilding the transcript.

            Full-screen programs redraw by emitting many small chunks. Feeding
            every chunk directly into QTextEdit can starve key events and make
            the terminal look frozen. A bounded 8 ms timer preserves ordering,
            collapses the burst into one render pass, and caps redraw frequency
            when a command floods the PTY.
            """

            if not payload:
                return
            self._process_output_buffer.extend(payload)
            self.output.setProperty(
                "terminalOutputBufferedBytes",
                len(self._process_output_buffer),
            )
            if self._process_output_flush_scheduled:
                return
            self._process_output_flush_scheduled = True
            self._process_output_timer.start()

        def flush_process_output(self) -> None:
            self._process_output_flush_scheduled = False
            if not self._process_output_buffer:
                return
            # Never let one flood of output monopolize the GUI event loop.
            # Keep the remainder queued so input, resize, and tab events can
            # run between render batches without dropping terminal bytes.
            batch_size = 64 * 1024
            payload = bytes(self._process_output_buffer[:batch_size])
            del self._process_output_buffer[:batch_size]
            self._process_output_flush_count += 1
            self.output.setProperty(
                "terminalOutputBufferedBytes",
                len(self._process_output_buffer),
            )
            self.output.setProperty(
                "terminalOutputFlushCount",
                self._process_output_flush_count,
            )
            self.append_process_text(payload.decode(errors="replace"))
            if self._process_output_buffer and not self._process_output_flush_scheduled:
                self._process_output_flush_scheduled = True
                self._process_output_timer.start()

        def flush_process_output_now(self) -> None:
            """Drain queued output synchronously at process shutdown/error."""

            self._process_output_flush_scheduled = False
            self._process_output_timer.stop()
            if not self._process_output_buffer:
                return
            payload = bytes(self._process_output_buffer)
            self._process_output_buffer.clear()
            self._process_output_flush_count += 1
            self.output.setProperty("terminalOutputBufferedBytes", 0)
            self.output.setProperty(
                "terminalOutputFlushCount",
                self._process_output_flush_count,
            )
            self.append_process_text(payload.decode(errors="replace"))

        @staticmethod
        def is_initial_conpty_screen_clear(text: str) -> bool:
            """Recognize the bounded console-initialization clear emitted by ConPTY."""

            return "\x1b[?9001h" in text and "\x1b[2J" in text

        def arm_initial_pty_clear_recovery(self) -> None:
            armed = bool(
                getattr(self.process, "is_pty", False)
                and self.terminal_startup_context_text()
            )
            self._pty_initial_clear_pending = armed
            self._pty_startup_probe = ""
            self.output.setProperty("terminalInitialPtyClearRecoveryArmed", armed)
            self.output.setProperty("terminalInitialPtyClearNormalized", False)

        def disarm_initial_pty_clear_recovery(self) -> None:
            self._pty_initial_clear_pending = False
            self._pty_startup_probe = ""
            self.output.setProperty("terminalInitialPtyClearRecoveryArmed", False)

        def append_process_text(self, text: str) -> None:
            """Render process output and normalize only ConPTY's first screen clear."""

            if not text:
                return
            transcript = self.terminal_emulator.feed(text)
            alternate_screen_active = self.terminal_emulator.alternate_screen_active
            if alternate_screen_active:
                # Keep the entire negotiated screen height in the document;
                # compacting blank rows makes Vim's status/cursor appear in
                # the middle of a giant empty pane and makes scroll state jump.
                transcript = self.terminal_emulator.screen_text()
            self.output.setProperty(
                "terminalBracketedPasteActive",
                self.terminal_emulator.bracketed_paste_active,
            )
            self.forward_terminal_emulator_responses()
            if alternate_screen_active:
                # Only the initial ConPTY shell clear may be normalized. Once
                # Vim/ncurses owns the alternate screen, rewriting the
                # transcript would reset its cursor and make it appear stuck.
                self.disarm_initial_pty_clear_recovery()
            if self._pty_initial_clear_pending and not alternate_screen_active:
                self._pty_startup_probe = (
                    self._pty_startup_probe + text
                )[-16_384:]
                if self.is_initial_conpty_screen_clear(self._pty_startup_probe):
                    body = self.normalized_initial_pty_body(transcript)
                    self.disarm_initial_pty_clear_recovery()
                    self.set_terminal_transcript(
                        f"{self.terminal_startup_context_text()}{body}"
                    )
                    self.output.setProperty(
                        "terminalInitialPtyClearNormalized",
                        True,
                    )
                    return
                startup_context = self.terminal_startup_context_text()
                visible_tail = (
                    transcript[len(startup_context) :]
                    if transcript.startswith(startup_context)
                    else transcript
                )
                if visible_tail.strip() or len(self._pty_startup_probe) >= 16_384:
                    self.disarm_initial_pty_clear_recovery()
                    normalized = self.normalized_initial_pty_transcript(transcript)
                    if normalized != transcript:
                        self.set_terminal_transcript(normalized)
                        self.output.setProperty(
                            "terminalInitialPtyClearNormalized",
                            True,
                        )
                        return
            normalized = self.normalized_initial_prompt_transcript(transcript)
            if normalized != transcript:
                self.set_terminal_transcript(normalized)
                self.output.setProperty("terminalInitialPromptPaddingNormalized", True)
                return
            self.render_terminal_transcript(transcript)

        def forward_terminal_emulator_responses(self) -> None:
            """Answer terminal capability/cursor queries without rendering them.

            Full-screen applications such as Vim issue DA/DSR requests during
            startup and redraw.  A transcript-only renderer must answer those
            requests through the same PTY, otherwise the child waits for a
            response and appears frozen or ignores the first keystrokes.
            """

            responses = self.terminal_emulator.take_pending_responses()
            if not responses:
                return
            payload = b"".join(responses)
            count = int(self.output.property("terminalEmulatorResponseCount") or 0)
            self.output.setProperty("terminalEmulatorResponseCount", count + len(responses))
            self.output.setProperty("terminalLastEmulatorResponse", payload)
            if not self.is_running():
                return
            accepted = self.process.write(payload)
            if accepted is None:
                accepted = len(payload)
            self.output.setProperty("terminalLastEmulatorResponseBytesAccepted", int(accepted))
            if int(accepted) < len(payload):
                self.set_status("input error", "error")

        def normalized_initial_pty_body(self, transcript: str) -> str:
            startup_context = self.terminal_startup_context_text()
            if transcript.startswith(startup_context):
                return transcript[len(startup_context) :].lstrip("\r\n")
            return transcript.lstrip("\r\n")

        def normalized_initial_pty_transcript(self, transcript: str) -> str:
            startup_context = self.terminal_startup_context_text()
            if transcript.startswith(startup_context):
                return f"{startup_context}{self.normalized_initial_pty_body(transcript)}"
            return transcript.lstrip("\r\n")

        def normalized_initial_prompt_transcript(self, transcript: str) -> str:
            """Remove pipe-backend screen padding immediately before auth prompts."""

            startup_context = self.terminal_startup_context_text()
            if not startup_context or not transcript.startswith(startup_context):
                return transcript
            body = transcript[len(startup_context) :]
            if not re.fullmatch(
                r"(?:[ \t]*\n)+[^\r\n]*(?:password|passphrase)[^:\r\n]*:\s*",
                body,
                flags=re.IGNORECASE,
            ):
                return transcript
            padding = re.match(r"(?:[ \t]*\n)+", body)
            if padding is None:
                return transcript
            return f"{startup_context}{body[padding.end():]}"

        def append_text(self, text: str) -> None:
            if not text:
                return
            transcript = self.terminal_emulator.feed(text)
            if self.terminal_emulator.alternate_screen_active:
                transcript = self.terminal_emulator.screen_text()
            self.render_terminal_transcript(transcript)

        def set_terminal_transcript(self, text: str) -> None:
            """Seed a rendered transcript and keep ANSI stream state in sync."""

            self.terminal_emulator.reset()
            self.output.clear()
            self._rendered_terminal_text = ""
            self.render_terminal_transcript(self.terminal_emulator.feed(text))

        def render_terminal_transcript(self, transcript: str) -> None:
            previous = self._rendered_terminal_text
            selected_cursor = self.output.textCursor()
            selection_anchor = selected_cursor.anchor()
            selection_position = selected_cursor.position()
            selection_start = selected_cursor.selectionStart()
            selection_end = selected_cursor.selectionEnd()
            selection_text_unchanged = bool(
                selected_cursor.hasSelection()
                and selection_end <= len(previous)
                and selection_end <= len(transcript)
                and previous[selection_start:selection_end]
                == transcript[selection_start:selection_end]
            )
            scroll_bar = _required_gui_value(
                self.output.verticalScrollBar(),
                "terminal vertical scroll bar",
            )
            scroll_value = scroll_bar.value()
            alternate_screen_active = self.terminal_emulator.alternate_screen_active
            was_scrolled_to_end = (
                not alternate_screen_active
                and scroll_value >= scroll_bar.maximum() - 2
            )
            self.output.setProperty(
                "terminalAlternateScreenActive",
                alternate_screen_active,
            )
            if alternate_screen_active and self.output.updatesEnabled():
                # Vim/ncurses redraw the whole screen frequently. Suppress
                # intermediate paint events so the user never sees a blank or
                # half-rendered frame while the retained transcript is rebuilt.
                self.output.setProperty("terminalAlternateScreenRedraw", True)
                self.output.setUpdatesEnabled(False)
            if previous and transcript.startswith(previous):
                replace_from = previous.rfind("\n") + 1
                cursor = self.output.textCursor()
                cursor.setPosition(replace_from)
                cursor.movePosition(
                    QTextCursor.MoveOperation.End,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
                fragment_source = transcript[replace_from:]
            else:
                self.output.clear()
                cursor = self.output.textCursor()
                fragment_source = transcript
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            ansi_fragments = self.terminal_emulator.styled_fragments(
                start=replace_from if previous and transcript.startswith(previous) else 0,
                screen=alternate_screen_active,
            )
            syntax_spans = (
                ()
                if alternate_screen_active
                else highlight_terminal_text(fragment_source, self.syntax_rules)
            )
            source_offset = replace_from if previous and transcript.startswith(previous) else 0
            boundaries = {0, len(fragment_source)}
            ansi_ranges = []
            for fragment in ansi_fragments:
                start = fragment.start - source_offset
                end = fragment.end - source_offset
                if end <= 0 or start >= len(fragment_source):
                    continue
                start = max(0, start)
                end = min(len(fragment_source), end)
                ansi_ranges.append((start, end, fragment.style))
                boundaries.update({start, end})
            for span in syntax_spans:
                boundaries.update({span.start, span.end})
            ordered_boundaries = sorted(boundaries)
            ansi_index = 0
            syntax_index = 0
            for start, end in zip(
                ordered_boundaries,
                ordered_boundaries[1:],
                strict=False,
            ):
                while ansi_index < len(ansi_ranges) and ansi_ranges[ansi_index][1] <= start:
                    ansi_index += 1
                while syntax_index < len(syntax_spans) and syntax_spans[syntax_index].end <= start:
                    syntax_index += 1
                ansi_style = (
                    ansi_ranges[ansi_index][2]
                    if ansi_index < len(ansi_ranges)
                    and ansi_ranges[ansi_index][0] <= start < ansi_ranges[ansi_index][1]
                    else AnsiTextStyle()
                )
                syntax_span = (
                    syntax_spans[syntax_index]
                    if syntax_index < len(syntax_spans)
                    and syntax_spans[syntax_index].start <= start < syntax_spans[syntax_index].end
                    else None
                )
                cursor.insertText(
                    fragment_source[start:end],
                    self.terminal_text_format(
                        ansi_style,
                        syntax_span.color if syntax_span is not None else "",
                        syntax_rule_key=(
                            syntax_span.rule_key if syntax_span is not None else ""
                        ),
                        link_target=(
                            syntax_span.text
                            if syntax_span is not None
                            and syntax_span.rule_key == "url"
                            else ""
                        ),
                    ),
                )
            self._rendered_terminal_text = transcript
            if alternate_screen_active:
                self.output.setUpdatesEnabled(True)
                self.output.viewport().update()
                self.output.setProperty("terminalAlternateScreenRedraw", False)
            if alternate_screen_active:
                # The retained screen is a viewport, not scrollback.  Always
                # anchor it at row zero even if the previous shell page had a
                # large scrollbar value.
                scroll_bar.setValue(0)
                self.output.setProperty("terminalFollowOutput", False)
            elif selection_text_unchanged:
                restored = QTextCursor(self.output.document())
                restored.setPosition(selection_anchor)
                restored.setPosition(
                    selection_position,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                self.output.setTextCursor(restored)
                scroll_bar.setValue(scroll_value)
                self.output.setProperty("terminalSelectionPreservedOnOutput", True)
            elif was_scrolled_to_end:
                self.scroll_terminal_to_end()
            else:
                scroll_bar.setValue(scroll_value)
            self.refresh_terminal_input_security(transcript)

        def scroll_terminal_to_end(self) -> None:
            """Keep live output at the true document end after layout updates."""

            if self.terminal_emulator.alternate_screen_active:
                # Alternate-screen applications own the viewport. Moving the
                # QTextEdit cursor to document end fights Vim's cursor
                # addressing and produces a visible flash on every redraw.
                self._terminal_scroll_generation += 1
                scroll_bar = _required_gui_value(
                    self.output.verticalScrollBar(),
                    "terminal vertical scroll bar",
                )
                scroll_bar.setValue(0)
                self.output.setProperty("terminalFollowOutput", False)
                return

            self._terminal_scroll_generation += 1
            generation = self._terminal_scroll_generation
            scroll_bar = _required_gui_value(
                self.output.verticalScrollBar(),
                "terminal vertical scroll bar",
            )
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.ensureCursorVisible()
            scroll_bar.setValue(scroll_bar.maximum())
            self.output.setProperty("terminalFollowOutput", True)

            def settle() -> None:
                if generation != self._terminal_scroll_generation:
                    return
                bar = _required_gui_value(
                    self.output.verticalScrollBar(),
                    "terminal vertical scroll bar",
                )
                bar.setValue(bar.maximum())
                self.output.ensureCursorVisible()
                bar.setValue(bar.maximum())

            QTimer.singleShot(0, settle)

        def terminal_text_format(
            self,
            ansi_style: AnsiTextStyle,
            syntax_color: str = "",
            *,
            syntax_rule_key: str = "",
            link_target: str = "",
        ) -> QTextCharFormat:
            """Translate retained SGR state into a Qt document character format."""

            text_format = QTextCharFormat()
            palette = self.output.palette()
            foreground, background = ansi_style.resolved_colors(
                palette.color(QPalette.ColorRole.Text).name(),
                palette.color(QPalette.ColorRole.Base).name(),
            )
            if foreground:
                text_format.setForeground(QColor(foreground))
            elif syntax_color:
                text_format.setForeground(QColor(syntax_color))
            if background:
                text_format.setBackground(QColor(background))
            if ansi_style.bold:
                text_format.setFontWeight(int(QFont.Weight.Bold))
            if ansi_style.underline:
                text_format.setFontUnderline(True)
            if (
                syntax_rule_key == "url"
                and link_target
                and self.validated_terminal_link(link_target) is not None
            ):
                text_format.setAnchor(True)
                text_format.setAnchorHref(link_target)
                text_format.setFontUnderline(True)
            return text_format

        @staticmethod
        def terminal_secret_prompt_visible(transcript: str) -> bool:
            tail = transcript[-512:]
            return bool(
                re.search(
                    r"(?i)(?:password|passphrase)[^:\r\n]{0,240}:\s*$",
                    tail,
                )
            )

        def refresh_terminal_input_security(self, transcript: str) -> None:
            active = self.terminal_secret_prompt_visible(transcript)
            if active == self._secret_prompt_active:
                return
            self._secret_prompt_active = active
            if active:
                self.input.clear()
            echo_mode = (
                QLineEdit.EchoMode.Password
                if active
                else QLineEdit.EchoMode.Normal
            )
            self.input.setEchoMode(echo_mode)
            self.input.setPlaceholderText(
                "Secret input (masked, not recorded); press Enter"
                if active
                else "stdin, shell command or interactive input"
            )
            self.input.setProperty("terminalSecretInputActive", active)
            self.output.setProperty("terminalSecretInputActive", active)
            self.update_process_actions()
            if active:
                # SSH can emit its password prompt after another control has
                # taken focus. Native PTY input is delivered through the
                # transcript widget, so restore focus before the user types.
                QTimer.singleShot(0, self.focus_terminal_input)

        def on_started(self) -> None:
            self.set_status("running", "running")
            self.update_process_actions()
            QTimer.singleShot(0, self.resize_terminal_backend)
            QTimer.singleShot(0, self.focus_terminal_input)

        def focus_terminal_input(self) -> None:
            """Focus the live terminal after its containing tab becomes visible."""

            if not self.isVisible() or not self.isEnabled() or not self.is_running():
                return
            self.output.setProperty("mobaTerminalFocusRequested", True)
            self.output.setFocus(Qt.FocusReason.OtherFocusReason)

        def on_error(self, error) -> None:
            self.flush_process_output_now()
            self.set_status("error", "error")
            detail = str(self.process.errorString()).strip()
            suffix = f": {detail}" if detail and detail != error.name else ""
            self.append_text(f"\n[error] {error.name}{suffix}\n")
            self.update_process_actions()

        def on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
            self._stop_timer.stop()
            self.flush_process_output_now()
            self.refresh_terminal_input_security("")
            state = "ready" if exit_code == 0 else "error"
            self.set_status(f"exited {exit_code}", state)
            self.append_text(f"\n[process exited: {exit_code}, {exit_status.name}]\n")
            self.update_process_actions()
            if self._restart_after_stop and not bool(self.property("terminalClosing")):
                self._restart_after_stop = False
                QTimer.singleShot(0, self.start)

        def set_status(self, text: str, state: str) -> None:
            self.status.setText(text)
            self.status.setProperty("state", state)
            status_style = _widget_style(self.status)
            status_style.unpolish(self.status)
            status_style.polish(self.status)
            self.status.update()

        def update_process_actions(self) -> None:
            running = self.is_running()
            capture_active = bool(self.macro_capture_state is not None and self.macro_capture_state.active)
            self.start_button.setEnabled(not running)
            self.restart_button.setEnabled(bool(self.plan.command))
            self.stop_button.setEnabled(running)
            self.input.setEnabled(running)
            self.macro_record_button.setEnabled(
                running
                and not capture_active
                and not self.macro_replay_active
                and not self._secret_prompt_active
            )
            self.macro_stop_button.setEnabled(capture_active)
            self.macro_cancel_button.setEnabled(capture_active or self.macro_replay_active)
            self.macro_replay_button.setEnabled(
                running
                and self.macro_last_recording is not None
                and not capture_active
                and not self._secret_prompt_active
            )
            self.apply_moba_macro_runtime_properties()

    class MobaTextEditorHighlighter(QSyntaxHighlighter):
        def __init__(self, document, syntax: str) -> None:
            super().__init__(document)
            self.syntax = syntax
            self.patterns = self.patterns_for_syntax(syntax)

        @staticmethod
        def patterns_for_syntax(syntax: str) -> list[tuple[str, str]]:
            common = [
                (r"(?m)#.*$", "#6a9955"),
                (r"(?m)//.*$", "#6a9955"),
                (r"\"(?:[^\"\\]|\\.)*\"", "#ce9178"),
                (r"\b\d+(?:\.\d+)?\b", "#b5cea8"),
            ]
            if syntax in {"json", "javascript", "typescript"}:
                return [*common, (r"\b(?:true|false|null)\b", "#569cd6")]
            if syntax in {"shell", "powershell"}:
                return [*common, (r"\b(?:if|then|else|fi|for|do|done|set|function)\b", "#569cd6")]
            if syntax in {"ssh-config", "ini", "systemd", "nginx"}:
                return [*common, (r"(?m)^[A-Za-z0-9_.-]+(?=\s|=)", "#9cdcfe")]
            if syntax == "log":
                return [*common, (r"\b(?:error|failed|denied|warning|ok|success)\b", "#dcdcaa")]
            return common

        def highlightBlock(self, text: str | None) -> None:
            source = text or ""
            for pattern, color in self.patterns:
                text_format = QTextCharFormat()
                text_format.setForeground(QColor(color))
                for match in re.finditer(pattern, source, re.IGNORECASE):
                    start, end = match.span()
                    self.setFormat(start, end - start, text_format)

    class MobaSftpDock(QFrame):
        OPERATIONAL_ACTIONS = frozenset(
            {
                "parent-folder",
                "download",
                "upload",
                "connect",
                "tools",
                "terminal",
            }
        )
        UNAVAILABLE_ACTION_DETAILS = {
            "new-folder": "Use Tools > Transfer queue to review and run mkdir safely.",
            "new-file": "Remote file creation is not available in the connected dock.",
            "delete": "Use Tools > Transfer queue for guarded rm/rmdir operations.",
            "ascii-mode": "ASCII transfer mode is not supported by the SFTP queue backend.",
            "split-view": "Split file comparison is not available in the connected dock.",
        }

        def main_window(self) -> MainWindow | None:
            window = self.window()
            return window if isinstance(window, MainWindow) else None

        @staticmethod
        def apply_connected_dock_frame_properties(widget) -> None:
            frame = gui_design_moba_connected_dock_frame()
            properties = {
                "mobaConnectedDockSideWidth": frame.side_width,
                "mobaConnectedDockRailWidth": frame.rail_width,
                "mobaConnectedDockX": frame.dock_x,
                "mobaConnectedDockY": frame.dock_y,
                "mobaConnectedDockWidth": frame.dock_width,
                "mobaConnectedDockHeight": frame.dock_height,
                "mobaConnectedDockWorkspaceX": frame.workspace_x,
                "mobaConnectedDockQuickConnectY": frame.quick_connect_y,
                "mobaConnectedDockQuickConnectHeight": frame.quick_connect_height,
                "mobaConnectedDockStatusY": frame.status_y,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_sftp_dock_density_properties(widget, density) -> None:
            widget.setProperty("mobaSftpDockInnerMargin", density.inner_margin)
            widget.setProperty("mobaSftpToolbarHeight", density.toolbar_height)
            widget.setProperty("mobaSftpPathHeight", density.path_height)
            widget.setProperty("mobaSftpHeaderHeight", density.table_header_height)
            widget.setProperty("mobaSftpRowHeight", density.file_row_height)
            widget.setProperty("mobaSftpMonitoringHeight", density.monitoring_height)
            widget.setProperty("mobaSftpStaticMaxRows", density.static_max_rows)
            widget.setProperty("mobaSftpToolbarSeparatorWidth", density.toolbar_separator_width)

        @staticmethod
        def moba_sftp_toolbar_action_index(route, action_key: str) -> int:
            try:
                return route.action_keys.index(action_key)
            except ValueError:
                return 0

        def apply_sftp_toolbar_action_route_properties(
            self,
            widget,
            route,
            *,
            triggered: bool = False,
            action_key: str | None = None,
            status: str | None = None,
        ) -> None:
            action_value = action_key or route.action_keys[1]
            action_index = self.moba_sftp_toolbar_action_index(route, action_value)
            status_value = status or route.action_statuses[action_index]
            properties = {
                "mobaSftpToolbarRouteKey": route.key,
                "mobaSftpToolbarRouteRole": route.route_role,
                "mobaSftpToolbarRouteToolbarObject": route.toolbar_object,
                "mobaSftpToolbarRouteActionObject": route.action_object,
                "mobaSftpToolbarRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpToolbarRouteTargetPathObject": route.target_path_object,
                "mobaSftpToolbarRouteTargetTableObject": route.target_table_object,
                "mobaSftpToolbarRouteQueueObject": route.queue_object,
                route.action_key_property: action_value,
                route.action_label_property: route.action_labels[action_index],
                route.action_object_property: route.action_object,
                route.icon_key_property: route.action_icon_keys[action_index],
                route.group_key_property: route.action_group_keys[action_index],
                route.tooltip_property: route.action_tooltips[action_index],
                "mobaSftpToolbarRouteSignal": route.signal,
                "mobaSftpToolbarRouteHandler": route.action_handlers[action_index],
                route.action_keys_property: list(route.action_keys),
                "mobaSftpToolbarRouteActionGroups": list(route.action_group_keys),
                route.captured_property: triggered,
                "mobaSftpToolbarRouteCapturedAction": action_value if triggered else "",
                route.captured_status_property: status_value if triggered else "",
                route.live_triggered_property: triggered,
                "mobaSftpToolbarRouteLiveAction": action_value,
                route.live_status_property: status_value,
                "mobaSftpToolbarRouteActionStatuses": list(route.action_statuses),
                "mobaSftpToolbarRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_sftp_follow_folder_route_properties(self, widget, route) -> None:
            follow_plan = self.state.follow_folder_plan.printable_batch()
            properties = {
                "mobaSftpFollowRouteKey": route.key,
                "mobaSftpFollowRouteRole": route.route_role,
                "mobaSftpFollowRouteSourceControlKey": route.source_control_key,
                "mobaSftpFollowRouteSourceControlObject": route.source_control_object,
                "mobaSftpFollowRouteSourcePathProperty": route.source_path_property,
                "mobaSftpFollowRouteSourcePlanProperty": route.source_plan_property,
                "mobaSftpFollowRouteSourceEnabledProperty": route.source_enabled_property,
                "mobaSftpFollowRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpFollowRouteTargetPathObject": route.target_path_object,
                "mobaSftpFollowRouteTargetTableObject": route.target_table_object,
                "mobaSftpFollowRouteTargetPathProperty": route.target_path_property,
                "mobaSftpFollowRouteTargetPlanProperty": route.target_plan_property,
                "mobaSftpFollowRouteTargetEnabledProperty": route.target_enabled_property,
                "mobaSftpFollowRouteRenderSource": route.render_source,
                "mobaSftpFollowRoutePath": self.state.remote_path,
                "mobaSftpFollowRoutePlan": follow_plan,
                "mobaSftpFollowRouteEnabled": self.state.follow_terminal_folder,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_sftp_terminal_folder_route_properties(self, widget) -> None:
            route = moba_sftp_terminal_folder_route(self.state)
            properties = {
                "mobaSftpTerminalFolderRouteKey": route.key,
                "mobaSftpTerminalFolderRouteRole": route.route_role,
                "mobaSftpTerminalFolderRouteTerminalAreaObject": route.terminal_area_object,
                "mobaSftpTerminalFolderRouteTerminalOutputObject": route.terminal_output_object,
                "mobaSftpTerminalFolderRouteSourceControlObject": route.source_control_object,
                "mobaSftpTerminalFolderRouteTargetBrowserObject": route.target_browser_object,
                "mobaSftpTerminalFolderRouteTargetPathObject": route.target_path_object,
                "mobaSftpTerminalFolderRouteTargetTableObject": route.target_table_object,
                "mobaSftpTerminalFolderRouteParentRowLabel": route.parent_row_label,
                "mobaSftpTerminalFolderRouteSelectedRowKind": route.selected_row_kind,
                "mobaSftpTerminalFolderRoutePath": route.remote_path,
                "mobaSftpTerminalFolderRoutePlan": route.list_command,
                "mobaSftpTerminalFolderRouteEnabled": route.follow_enabled,
                "mobaSftpTerminalFolderRouteRowRouteProperty": route.row_route_property,
                "mobaSftpTerminalFolderRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_sftp_routed_file_rows_properties(self, widget, rows, route) -> None:
            properties = {
                "mobaSftpRoutedRowsKey": rows.key,
                "mobaSftpRoutedRowsRole": rows.route_role,
                "mobaSftpRoutedRowsFollowRouteKey": rows.follow_route_key,
                "mobaSftpRoutedRowsTargetTableObject": rows.target_table_object,
                "mobaSftpRoutedRowsContractProperty": rows.row_contract_property,
                "mobaSftpRoutedRowsRouteProperty": rows.row_route_property,
                "mobaSftpRoutedRowsPathProperty": rows.row_path_property,
                "mobaSftpRoutedRowsIndexProperty": rows.row_index_property,
                "mobaSftpRoutedRowsSelectedProperty": rows.row_selected_property,
                "mobaSftpRoutedRowsParentRowName": rows.parent_row_name,
                "mobaSftpRoutedRowsSelectedRowKind": rows.selected_row_kind,
                "mobaSftpRoutedRowsRenderSource": rows.render_source,
                "mobaSftpRoutedRowsSourcePath": self.state.remote_path,
                "mobaSftpRoutedRowsEnabled": self.state.follow_terminal_folder,
                "mobaSftpRoutedRowsPlan": self.state.follow_folder_plan.printable_batch(),
                "mobaSftpRoutedRowsRoutePathProperty": route.target_path_property,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_session_route_properties(self, widget) -> None:
            route = moba_connected_session_route(self.state)
            properties = {
                "mobaConnectedRouteKey": route.key,
                "mobaConnectedRouteRole": route.route_role,
                "mobaConnectedRouteActiveTabKey": route.active_tab_key,
                "mobaConnectedRouteActiveTabLabel": route.active_tab_label,
                "mobaConnectedRouteReferenceTabLabel": route.reference_tab_label,
                "mobaConnectedRouteActiveTabObject": route.active_tab_object,
                "mobaConnectedRouteConnectedPanelObject": route.connected_panel_object,
                "mobaConnectedRouteLeftDockObject": route.left_dock_object,
                "mobaConnectedRouteSftpBrowserObject": route.sftp_browser_object,
                "mobaConnectedRouteSftpPathObject": route.sftp_path_object,
                "mobaConnectedRouteSftpTableObject": route.sftp_table_object,
                "mobaConnectedRouteSshBannerObject": route.ssh_banner_object,
                "mobaConnectedRouteTerminalAreaObject": route.terminal_area_object,
                "mobaConnectedRouteTerminalOutputObject": route.terminal_output_object,
                "mobaConnectedRouteTelemetryBarObject": route.telemetry_bar_object,
                "mobaConnectedRouteTelemetryIdentityCellKey": route.telemetry_identity_cell_key,
                route.target_property: route.target,
                route.remote_path_property: route.remote_path,
                "mobaConnectedRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_ssh_browser_state_properties(self, widget) -> None:
            browser_state = self.state.ssh_browser_state
            properties = {
                "mobaSshBrowserLocation": browser_state.location,
                "mobaSshBrowserTerminalVisible": browser_state.terminal_visible,
                "mobaSshBrowserVisible": browser_state.browser_visible,
                "mobaSshBrowserOverwriteConfirmation": browser_state.overwrite_confirmation,
                "mobaSshBrowserColumnWidthMap": dict(browser_state.column_widths),
                "mobaSshBrowserPreferenceRenderSource": browser_state.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_smartcard_selection_properties(self, widget) -> None:
            selection = self.state.smartcard_selection
            properties = {
                "mobaSmartcardSelectionEnabled": selection.enabled,
                "mobaSmartcardProvider": selection.provider_label,
                "mobaSmartcardProviderKey": selection.provider_key,
                "mobaSmartcardCertificateId": selection.certificate_id,
                "mobaSmartcardCertificateLabel": selection.certificate_label,
                "mobaSmartcardPublicKey": selection.public_key,
                "mobaSmartcardAddToMobAgent": selection.add_to_mobagent,
                "mobaSmartcardAgentSocket": selection.agent_socket,
                "mobaSmartcardPkcs11Provider": selection.pkcs11_provider,
                "mobaSmartcardProfileOptionKeys": list(selection.profile_option_keys),
                "mobaSmartcardSelectionRenderSource": selection.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def apply_connected_text_editor_route_properties(self, widget, *, triggered: bool = False, status: str = "ready") -> None:
            route = moba_connected_text_editor_route(self.state)
            properties = {
                "mobaTextEditorSchema": route.schema,
                "mobaTextEditorProfile": route.profile_name,
                "mobaTextEditorRemotePath": route.remote_path,
               …189007 tokens truncated…           self.securecrt_session_filter = QLineEdit()
            self.securecrt_session_filter.setObjectName("secureCrtSessionFilter")
            self.securecrt_session_filter.setPlaceholderText(chrome.filter_placeholder)
            self.securecrt_session_filter.setProperty("secureCrtSessionManagerLiveFilterHeight", chrome.live_filter_height)
            for property_name, property_value in filter_route_properties.items():
                self.securecrt_session_filter.setProperty(property_name, property_value)
            self.securecrt_session_filter.setFixedHeight(chrome.live_filter_height)
            self.securecrt_session_filter.textChanged.connect(self.filter_profile_tree)
            layout.addWidget(self.securecrt_session_filter)
            panel.setVisible(False)
            return panel

        def securecrt_session_manager_action_icon(self, icon_key: str, *, size: int) -> QIcon:
            return self.generated_icon(
                size,
                lambda painter, logical_size: self.draw_securecrt_session_manager_action_icon(
                    painter, icon_key, logical_size
                ),
            )

        def draw_securecrt_session_manager_action_icon(self, painter: QPainter, icon_key: str, size: int) -> None:
            primary = QColor("#d7a84a")
            dark = QColor("#201a0e")
            painter.setPen(QPen(primary, 1))
            painter.setBrush(QBrush(primary))
            if icon_key == "folder":
                painter.drawRect(1, 4, size - 2, size - 5)
                painter.drawRect(2, 2, max(4, size // 2), 3)
                return
            if icon_key == "properties":
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(2, 2, size - 4, size - 4)
                painter.setPen(QPen(dark, 1))
                painter.drawLine(4, 5, size - 4, 5)
                painter.drawLine(4, 8, size - 5, 8)
                painter.drawLine(4, 11, size - 6, 11)
                return
            painter.drawPolygon(QPoint(3, 2), QPoint(size - 3, size // 2), QPoint(3, size - 2))

        def run_securecrt_session_manager_action(self, key: str) -> None:
            actions = {
                "connect": lambda: self.connect_selected(False),
                "new-folder": self.create_profile,
                "properties": self.edit_selected_profile,
            }
            action = actions.get(key)
            if action is None:
                self.statusBar().showMessage(f"Session Manager action: {key}")
                return
            action()

        def build_termius_hosts_chrome(self) -> QFrame:
            chrome = gui_design_termius_hosts_chrome()
            sync_route = gui_design_termius_sync_route()
            host_route = gui_design_termius_host_selection_route()
            panel = QFrame()
            panel.setObjectName("termiusHostsChrome")
            panel.setProperty("designPreset", "termius")
            panel.setProperty("termiusHostRouteKey", host_route.key)
            panel.setProperty("termiusHostRouteRole", host_route.route_role)
            panel.setProperty("termiusHostRouteSelectedProfile", host_route.selected_profile_name)
            panel.setProperty("termiusHostRouteSelectedTreeLabel", host_route.selected_tree_label)
            panel.setProperty("termiusHostRouteHostsPanelObject", host_route.hosts_panel_object)
            panel.setProperty("termiusHostRouteIdentityObject", host_route.host_identity_object)
            panel.setProperty("termiusHostRouteIdentityFieldKey", host_route.identity_field_key)
            panel.setProperty("termiusHostRouteIdentityCellObject", host_route.identity_cell_object)
            panel.setProperty("termiusHostRouteActiveTab", host_route.active_tab_label)
            panel.setProperty("termiusHostRouteTarget", host_route.target_value)
            panel.setProperty("termiusHostRouteProtocol", host_route.protocol_value)
            panel.setProperty("termiusHostRouteIdentityValue", host_route.host_value)
            panel.setProperty("termiusHostRouteRenderSource", host_route.render_source)
            panel.setProperty("termiusHostsActionKeys", [action.key for action in chrome.actions])
            panel.setProperty("termiusHostSearchPlaceholder", chrome.filter_placeholder)
            panel.setMaximumHeight(94)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(7, 6, 7, 6)
            layout.setSpacing(5)

            title_row = QHBoxLayout()
            title_row.setSpacing(5)
            title = QLabel(chrome.title)
            title.setObjectName("termiusHostsTitle")
            title_row.addWidget(title, 1)
            for action in chrome.actions:
                button = QToolButton()
                button.setObjectName("termiusHostsAction")
                button.setProperty("termiusHostsActionKey", action.key)
                button.setProperty("termiusHostsIconKey", action.icon_key)
                button.setProperty("termiusHostsActionLabel", action.label)
                button.setProperty("termiusHostsStaticX", action.static_x)
                button.setToolTip(action.tooltip)
                if action.key == sync_route.hosts_action_key:
                    button.setProperty("termiusSyncRouteKey", sync_route.key)
                    button.setProperty("termiusSyncRouteRole", sync_route.route_role)
                    button.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                    button.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                    button.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                    button.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                    button.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                    button.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                    button.setProperty("termiusSyncRouteState", sync_route.sync_state)
                    button.setProperty("termiusSyncRouteActionLabel", action.label)
                    button.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
                button.setIcon(
                    _widget_style(self).standardIcon(
                        self.standard_icon(
                            self.termius_hosts_icon_name(action.icon_key)
                        )
                    )
                )
                button.setIconSize(QSize(14, 14))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(QSize(24, 24))
                button.clicked.connect(lambda _checked=False, key=action.key: self.run_termius_hosts_action(key))
                title_row.addWidget(button)
            layout.addLayout(title_row)

            self.termius_host_search = QLineEdit()
            self.termius_host_search.setObjectName("termiusHostSearch")
            self.termius_host_search.setPlaceholderText(chrome.filter_placeholder)
            self.termius_host_search.setMinimumHeight(24)
            self.termius_host_search.textChanged.connect(self.filter_profile_tree)
            layout.addWidget(self.termius_host_search)
            panel.setVisible(False)
            return panel

        def termius_hosts_icon_name(self, icon_key: str) -> str:
            icon_map = {
                "plus": "SP_FileDialogNewFolder",
                "key": "SP_FileDialogDetailedView",
                "sync": "SP_BrowserReload",
            }
            return icon_map.get(icon_key, "SP_FileIcon")

        def run_termius_hosts_action(self, key: str) -> None:
            actions = {
                "new-host": self.create_profile,
                "keychain": lambda: self.statusBar().showMessage("Termius-style keychain: vault identity list"),
                "sync-hosts": self.refresh_profiles,
            }
            action = actions.get(key)
            if action is None:
                self.statusBar().showMessage(f"Termius Hosts action: {key}")
                return
            action()

        def build_remmina_profile_list_chrome(self) -> QFrame:
            chrome = gui_design_remmina_profile_list_chrome()
            route = gui_design_remmina_profile_viewer_route()
            filter_route = gui_design_remmina_profile_filter_route()
            transfer_route = gui_design_remmina_sftp_transfer_route()
            panel = QFrame()
            panel.setObjectName("remminaProfileListChrome")
            panel.setProperty("designPreset", "remmina")
            panel.setProperty("remminaProfileColumnKeys", [column.key for column in chrome.columns])
            panel.setProperty("remminaProfileRowKeys", [row.key for row in chrome.rows])
            panel.setProperty("remminaProfileViewerRouteKey", route.key)
            panel.setProperty("remminaProfileViewerRouteRole", route.route_role)
            panel.setProperty("remminaProfileViewerSelectedProfileKey", route.selected_profile_key)
            panel.setProperty("remminaProfileViewerSelectedProfileObject", route.selected_profile_object)
            panel.setProperty("remminaProfileViewerControlsObject", route.viewer_controls_object)
            panel.setProperty("remminaProfileViewerControlKey", route.viewer_control_key)
            panel.setProperty("remminaProfileViewerControlObject", route.viewer_control_object)
            panel.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
            panel.setProperty("remminaProfileViewerProtocol", route.protocol)
            panel.setProperty("remminaProfileViewerStatus", route.profile_status)
            panel.setProperty("remminaProfileViewerRenderSource", route.render_source)
            filter_route_properties = {
                "remminaProfileFilterRouteKey": filter_route.key,
                "remminaProfileFilterRouteRole": filter_route.route_role,
                "remminaProfileFilterRouteProfileListObject": filter_route.profile_list_object,
                "remminaProfileFilterRouteFilterObject": filter_route.filter_object,
                "remminaProfileFilterRouteSelectedProfileKey": filter_route.selected_profile_key,
                "remminaProfileFilterRouteSelectedProfileObject": filter_route.selected_profile_object,
                "remminaProfileFilterRouteMatchedProfile": filter_route.matched_profile_name,
                "remminaProfileFilterRouteMatchedProtocol": filter_route.matched_protocol,
                "remminaProfileFilterRouteMatchedStatus": filter_route.matched_status,
                "remminaProfileFilterRouteQuery": filter_route.expected_query,
                "remminaProfileFilterRoutePlaceholder": filter_route.expected_placeholder,
                "remminaProfileFilterRouteActiveTab": filter_route.active_tab_label,
                "remminaProfileFilterRouteSignal": filter_route.change_signal,
                "remminaProfileFilterRouteHandler": filter_route.handler_name,
                "remminaProfileFilterRouteRenderSource": filter_route.render_source,
            }
            for property_name, property_value in filter_route_properties.items():
                panel.setProperty(property_name, property_value)
            panel.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
            panel.setProperty("remminaSftpTransferRouteRole", transfer_route.route_role)
            panel.setProperty("remminaSftpTransferRouteProfileListObject", transfer_route.profile_list_object)
            panel.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
            panel.setProperty("remminaSftpTransferRouteSelectedProfile", transfer_route.selected_profile_name)
            panel.setProperty("remminaSftpTransferRouteProtocol", transfer_route.selected_profile_protocol)
            panel.setProperty("remminaSftpTransferRouteStatus", transfer_route.selected_profile_status)
            panel.setProperty("remminaSftpTransferRouteSelectedProfileObject", transfer_route.selected_profile_object)
            panel.setProperty("remminaSftpTransferRouteSelectedTreeLabel", transfer_route.selected_tree_label)
            panel.setProperty("remminaSftpTransferRouteToolbarActionKey", transfer_route.toolbar_action_key)
            panel.setProperty("remminaSftpTransferRouteToolbarActionLabel", transfer_route.toolbar_action_label)
            panel.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
            panel.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
            panel.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
            panel.setProperty("remminaSftpTransferRouteQueueLabel", transfer_route.transfer_queue_label)
            panel.setProperty("remminaSftpTransferRouteRenderSource", transfer_route.render_source)
            self.remmina_sftp_profile_panel = panel
            self.apply_remmina_sftp_transfer_action_route_properties(panel, transfer_route)
            panel.setProperty("remminaProfileStaticFilterX", chrome.static_filter_x)
            panel.setProperty("remminaProfileStaticFilterY", chrome.static_filter_y)
            panel.setProperty("remminaProfileStaticFilterHeight", chrome.static_filter_height)
            panel.setProperty("remminaProfileStaticHeaderY", chrome.static_header_y)
            panel.setProperty("remminaProfileStaticRowStartY", chrome.static_row_start_y)
            panel.setProperty("remminaProfileStaticRowHeight", chrome.static_row_height)
            panel.setProperty("remminaProfileStaticRowStep", chrome.static_row_step)
            panel.setProperty("remminaProfileStaticCellStartX", chrome.static_cell_start_x)
            panel.setProperty("remminaProfileStaticCellY", chrome.static_cell_y)
            panel.setProperty("remminaProfileStaticStatusY", chrome.static_status_y)
            panel.setProperty("remminaProfileLiveMaxHeight", chrome.live_max_height)
            panel.setProperty("remminaProfileLiveSpacing", chrome.live_spacing)
            panel.setProperty("remminaProfileLiveRowMinHeight", chrome.live_row_min_height)
            panel.setMaximumHeight(chrome.live_max_height)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(
                chrome.live_margin_left,
                chrome.live_margin_top,
                chrome.live_margin_right,
                chrome.live_margin_bottom,
            )
            layout.setSpacing(chrome.live_spacing)

            title_row = QHBoxLayout()
            title_row.setSpacing(chrome.live_title_spacing)
            title = QLabel(chrome.title)
            title.setObjectName("remminaProfileListTitle")
            title_row.addWidget(title)
            filter_input = QLineEdit()
            filter_input.setObjectName("remminaProfileFilter")
            filter_input.setPlaceholderText(chrome.filter_placeholder)
            filter_input.setReadOnly(False)
            filter_input.setProperty("remminaProfileFilterWidth", chrome.live_filter_width)
            for property_name, property_value in filter_route_properties.items():
                filter_input.setProperty(property_name, property_value)
            filter_input.setMinimumWidth(chrome.live_filter_width)
            filter_input.textChanged.connect(self.filter_remmina_profile_rows)
            self.remmina_profile_filter = filter_input
            title_row.addWidget(filter_input, 1)
            layout.addLayout(title_row)

            header = QHBoxLayout()
            header.setSpacing(chrome.live_header_spacing)
            compact_column_widths = {
                "name": 78,
                "protocol": 45,
                "server": 78,
            }
            for column in chrome.columns:
                label = QLabel(column.label)
                label.setObjectName("remminaProfileListColumn")
                label.setProperty("remminaProfileColumnKey", column.key)
                label.setProperty("remminaProfileColumnWidth", column.static_width)
                label.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
                compact_width = compact_column_widths[column.key]
                label.setProperty("remminaProfileColumnCompactMinWidth", compact_width)
                label.setMinimumWidth(compact_width)
                label.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                header.addWidget(label, compact_width)
            layout.addLayout(header)

            for row in chrome.rows:
                row_frame = QFrame()
                row_frame.setObjectName("remminaProfileListRow")
                row_frame.setProperty("remminaProfileRowKey", row.key)
                row_frame.setProperty("remminaProfileName", row.name)
                row_frame.setProperty("remminaProfileProtocol", row.protocol)
                row_frame.setProperty("remminaProfileServer", row.server)
                row_frame.setProperty("remminaProfileStatus", row.status)
                row_frame.setProperty("selectedRow", "true" if row.selected else "false")
                row_frame.setProperty("remminaProfileFilterRouteKey", filter_route.key)
                row_frame.setProperty("remminaProfileFilterRouteRole", filter_route.route_role)
                row_frame.setProperty("remminaProfileFilterRouteQuery", filter_route.expected_query)
                row_frame.setProperty(
                    "remminaProfileFilterRouteMatched",
                    "true" if row.key == filter_route.selected_profile_key else "false",
                )
                row_frame.setProperty("remminaProfileFilterRouteRenderSource", filter_route.render_source)
                if row.key == route.selected_profile_key:
                    row_frame.setProperty("remminaProfileViewerRouteKey", route.key)
                    row_frame.setProperty("remminaProfileViewerRouteRole", route.route_role)
                    row_frame.setProperty("remminaProfileViewerControlKey", route.viewer_control_key)
                    row_frame.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                    row_frame.setProperty("remminaProfileViewerProtocol", route.protocol)
                    row_frame.setProperty("remminaProfileViewerStatus", route.profile_status)
                    row_frame.setProperty(route.selected_row_property, "true" if row.selected else "false")
                if row.key == filter_route.selected_profile_key:
                    row_frame.setProperty("remminaProfileFilterRouteSelectedProfileKey", filter_route.selected_profile_key)
                    row_frame.setProperty("remminaProfileFilterRouteMatchedProfile", filter_route.matched_profile_name)
                    row_frame.setProperty("remminaProfileFilterRouteMatchedProtocol", filter_route.matched_protocol)
                    row_frame.setProperty("remminaProfileFilterRouteMatchedStatus", filter_route.matched_status)
                    row_frame.setProperty("remminaProfileFilterRouteActiveTab", filter_route.active_tab_label)
                if row.key == transfer_route.selected_profile_key:
                    row_frame.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
                    row_frame.setProperty("remminaSftpTransferRouteRole", transfer_route.route_role)
                    row_frame.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
                    row_frame.setProperty("remminaSftpTransferRouteSelectedProfile", transfer_route.selected_profile_name)
                    row_frame.setProperty("remminaSftpTransferRouteProtocol", transfer_route.selected_profile_protocol)
                    row_frame.setProperty("remminaSftpTransferRouteStatus", transfer_route.selected_profile_status)
                    row_frame.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
                    row_frame.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
                    row_frame.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
                    row_frame.setProperty("remminaSftpTransferRouteQueueLabel", transfer_route.transfer_queue_label)
                    row_frame.setProperty("remminaSftpTransferRouteRenderSource", transfer_route.render_source)
                    self.remmina_sftp_profile_row = row_frame
                    self.apply_remmina_sftp_transfer_action_route_properties(row_frame, transfer_route)
                row_frame.setProperty("remminaProfileStaticRowHeight", chrome.static_row_height)
                row_frame.setProperty("remminaProfileStaticRowStep", chrome.static_row_step)
                row_frame.setProperty("remminaProfileLiveRowMinHeight", chrome.live_row_min_height)
                row_frame.setMinimumHeight(chrome.live_row_min_height)
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(
                    chrome.live_row_margin_left,
                    chrome.live_row_margin_top,
                    chrome.live_row_margin_right,
                    chrome.live_row_margin_bottom,
                )
                row_layout.setSpacing(chrome.live_row_spacing)
                values = {
                    "name": row.name,
                    "protocol": row.protocol,
                    "server": row.server,
                    "status": row.status,
                }
                display_values = {
                    **values,
                    "server": row.server.replace(".example.invalid", ""),
                    "status": {
                        "scale 100%": "100%",
                        "fit window": "fit",
                        "file sharing": "files",
                    }.get(row.status, row.status),
                }
                for column in chrome.columns:
                    full_text = f"{column.label}: {values[column.key]}"
                    display_text = display_values[column.key]
                    compact_width = compact_column_widths[column.key]
                    cell = _literal_label(display_text)
                    cell.setObjectName("remminaProfileListCell")
                    cell.setProperty("remminaProfileRowKey", row.key)
                    cell.setProperty("remminaProfileColumnKey", column.key)
                    cell.setProperty("remminaProfileCellValue", values[column.key])
                    cell.setProperty("remminaProfileCellFullText", full_text)
                    cell.setProperty("remminaProfileCellDisplayText", display_text)
                    cell.setProperty("remminaProfileColumnWidth", column.static_width)
                    cell.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
                    cell.setProperty("remminaProfileColumnCompactMinWidth", compact_width)
                    if row.key == route.selected_profile_key:
                        cell.setProperty("remminaProfileViewerRouteKey", route.key)
                        cell.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                        cell.setProperty("remminaProfileViewerStatus", route.profile_status)
                    if row.key == transfer_route.selected_profile_key:
                        cell.setProperty("remminaSftpTransferRouteKey", transfer_route.key)
                        cell.setProperty("remminaSftpTransferRouteSelectedProfileKey", transfer_route.selected_profile_key)
                        cell.setProperty("remminaSftpTransferRouteActiveTab", transfer_route.active_tab_label)
                        cell.setProperty("remminaSftpTransferRoutePath", transfer_route.remote_path)
                        cell.setProperty("remminaSftpTransferRouteQueueState", transfer_route.transfer_status)
                    cell.setMinimumWidth(compact_width)
                    cell.setSizePolicy(
                        QSizePolicy.Policy.Ignored,
                        QSizePolicy.Policy.Preferred,
                    )
                    cell.setAccessibleName(full_text)
                    cell.setToolTip(_safe_tooltip_html(full_text))
                    row_layout.addWidget(cell, compact_width)
                status_full_text = f"Status: {row.status}"
                status_display_text = display_values["status"]
                status_compact_width = 47
                status = _literal_label(status_display_text)
                status.setObjectName("remminaProfileListCell")
                status.setProperty("remminaProfileRowKey", row.key)
                status.setProperty("remminaProfileColumnKey", "status")
                status.setProperty("remminaProfileCellValue", row.status)
                status.setProperty("remminaProfileCellFullText", status_full_text)
                status.setProperty("remminaProfileCellDisplayText", status_display_text)
                status.setProperty(
                    "remminaProfileColumnCompactMinWidth",
                    status_compact_width,
                )
                status.setProperty("remminaProfileStaticStatusY", chrome.static_status_y)
                if row.key == route.selected_profile_key:
                    status.setProperty("remminaProfileViewerRouteKey", route.key)
                    status.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                    status.setProperty("remminaProfileViewerStatus", route.profile_status)
                status.setMinimumWidth(status_compact_width)
                status.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                status.setAccessibleName(status_full_text)
                status.setToolTip(_safe_tooltip_html(status_full_text))
                row_layout.addWidget(status, status_compact_width)
                layout.addWidget(row_frame)
            return panel

        def build_securecrt_session_status_strip_evidence(self) -> QFrame:
            chrome = gui_design_securecrt_session_status_strip()
            route = gui_design_securecrt_session_manager_route()
            sftp_route = gui_design_securecrt_sftp_tab_route()
            panel = QFrame()
            panel.setObjectName("secureCrtSessionStatusStrip")
            panel.setProperty("designPreset", "securecrt")
            panel.setProperty("secureCrtSessionRouteKey", route.key)
            panel.setProperty("secureCrtSessionRouteRole", route.route_role)
            panel.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
            panel.setProperty("secureCrtSessionRouteSelectedTreeLabel", route.selected_tree_label)
            panel.setProperty("secureCrtSessionRouteSessionManagerObject", route.session_manager_object)
            panel.setProperty("secureCrtSessionRouteActionKey", route.session_manager_action_key)
            panel.setProperty("secureCrtSessionRouteActionObject", route.session_manager_action_object)
            panel.setProperty("secureCrtSessionRouteStatusStripObject", route.status_strip_object)
            panel.setProperty("secureCrtSessionRouteStatusFieldKey", route.status_field_key)
            panel.setProperty("secureCrtSessionRouteStatusFieldObject", route.status_field_object)
            panel.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
            panel.setProperty("secureCrtSessionRouteTarget", route.target_value)
            panel.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
            panel.setProperty("secureCrtSessionRouteSession", route.session_value)
            panel.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
            panel.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
            panel.setProperty("secureCrtSftpTabRouteKey", sftp_route.key)
            panel.setProperty("secureCrtSftpTabRouteRole", sftp_route.route_role)
            panel.setProperty("secureCrtSftpTabRouteWorkflowKey", sftp_route.workflow_card_key)
            panel.setProperty("secureCrtSftpTabRouteSelectedProfile", sftp_route.selected_profile_name)
            panel.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", sftp_route.selected_tree_label)
            panel.setProperty("secureCrtSftpTabRouteActiveTab", sftp_route.active_tab_label)
            panel.setProperty("secureCrtSftpTabRouteTabLabel", sftp_route.sftp_tab_label)
            panel.setProperty("secureCrtSftpTabRouteStatusStripObject", sftp_route.status_strip_object)
            panel.setProperty("secureCrtSftpTabRouteStatusFieldKey", sftp_route.status_field_key)
            panel.setProperty("secureCrtSftpTabRouteStatusFieldObject", sftp_route.status_field_object)
            panel.setProperty("secureCrtSftpTabRouteStatus", sftp_route.status_value)
            panel.setProperty("secureCrtSftpTabRouteTransferState", sftp_route.transfer_state)
            panel.setProperty("secureCrtSftpTabRouteRenderSource", sftp_route.render_source)
            panel.setProperty("secureCrtSessionStatusFieldKeys", [field.key for field in chrome.fields])
            panel.setProperty("secureCrtSessionStatusTitleWidth", chrome.title_width)
            panel.setProperty("secureCrtSessionStatusStaticTitleX", chrome.static_title_x)
            panel.setProperty("secureCrtSessionStatusStaticTitleY", chrome.static_title_y)
            panel.setProperty("secureCrtSessionStatusStaticCellStartX", chrome.static_cell_start_x)
            panel.setProperty("secureCrtSessionStatusStaticCellGap", chrome.static_cell_gap)
            panel.setProperty("secureCrtSessionStatusLiveSpacing", chrome.live_spacing)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(
                chrome.live_margin_left,
                chrome.live_margin_top,
                chrome.live_margin_right,
                chrome.live_margin_bottom,
            )
            layout.setSpacing(chrome.live_spacing)

            title = QLabel(chrome.title)
            title.setObjectName("secureCrtSessionStatusTitle")
            title.setMinimumWidth(chrome.title_width)
            title.setMaximumWidth(chrome.title_width)
            layout.addWidget(title)
            compact_values = {
                "session": "edge-prod",
                "target": "edge-prod:22",
                "protocol": "SSH2+SFTP",
                "cipher": "chacha20",
                "sftp": "files-prod",
                "log": "session.log",
                "state": "connected",
            }
            compact_widths = {
                # The status strip can be only ~520 px wide at the accepted
                # 1024-wide window.  Keep each compact value independent and
                # let its full canonical value live in the accessible label
                # and tooltip rather than allowing sibling cells to overlap.
                "session": 44,
                "target": 62,
                "protocol": 44,
                "cipher": 48,
                "sftp": 42,
                "log": 44,
                "state": 44,
            }
            for field in chrome.fields:
                full_text = f"{field.label}: {field.value}"
                display_text = compact_values[field.key]
                compact_width = compact_widths[field.key]
                tooltip_text = f"{full_text}\n{field.tooltip}"
                cell = _literal_label(display_text)
                cell.setObjectName("secureCrtSessionStatusCell")
                cell.setProperty("secureCrtSessionStatusKey", field.key)
                cell.setProperty("secureCrtSessionStatusLabel", field.label)
                cell.setProperty("secureCrtSessionStatusValue", field.value)
                cell.setProperty("secureCrtSessionStatusWidth", field.static_width)
                cell.setProperty("secureCrtSessionStatusRole", field.role)
                cell.setProperty("secureCrtSessionStatusStaticY", field.static_y)
                cell.setProperty("secureCrtSessionStatusStaticHeight", field.static_height)
                cell.setProperty("secureCrtSessionStatusStaticLabelX", field.static_label_x)
                cell.setProperty("secureCrtSessionStatusStaticLabelY", field.static_label_y)
                cell.setProperty("secureCrtSessionStatusStaticValueX", field.static_value_x)
                cell.setProperty("secureCrtSessionStatusStaticValueY", field.static_value_y)
                cell.setProperty("secureCrtSessionStatusLiveMinWidth", field.live_min_width)
                cell.setProperty("secureCrtSessionStatusLiveCellHeight", field.live_cell_height)
                cell.setProperty("secureCrtSessionStatusFullText", full_text)
                cell.setProperty("secureCrtSessionStatusDisplayText", display_text)
                cell.setProperty("secureCrtSessionStatusTooltipText", tooltip_text)
                cell.setProperty("secureCrtSessionStatusCompactMinWidth", compact_width)
                if field.key == route.status_field_key:
                    cell.setProperty("secureCrtSessionRouteKey", route.key)
                    cell.setProperty("secureCrtSessionRouteRole", route.route_role)
                    cell.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
                    cell.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
                    cell.setProperty("secureCrtSessionRouteTarget", route.target_value)
                    cell.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
                    cell.setProperty("secureCrtSessionRouteSession", route.session_value)
                    cell.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
                    cell.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
                if field.key == sftp_route.status_field_key:
                    cell.setProperty("secureCrtSftpTabRouteKey", sftp_route.key)
                    cell.setProperty("secureCrtSftpTabRouteRole", sftp_route.route_role)
                    cell.setProperty("secureCrtSftpTabRouteWorkflowKey", sftp_route.workflow_card_key)
                    cell.setProperty("secureCrtSftpTabRouteSelectedProfile", sftp_route.selected_profile_name)
                    cell.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", sftp_route.selected_tree_label)
                    cell.setProperty("secureCrtSftpTabRouteActiveTab", sftp_route.active_tab_label)
                    cell.setProperty("secureCrtSftpTabRouteTabLabel", sftp_route.sftp_tab_label)
                    cell.setProperty("secureCrtSftpTabRouteStatusStripObject", sftp_route.status_strip_object)
                    cell.setProperty("secureCrtSftpTabRouteStatusFieldKey", sftp_route.status_field_key)
                    cell.setProperty("secureCrtSftpTabRouteStatusFieldObject", sftp_route.status_field_object)
                    cell.setProperty("secureCrtSftpTabRouteStatus", sftp_route.status_value)
                    cell.setProperty("secureCrtSftpTabRouteTransferState", sftp_route.transfer_state)
                    cell.setProperty("secureCrtSftpTabRouteRenderSource", sftp_route.render_source)
                cell.setToolTip(_safe_tooltip_html(tooltip_text))
                cell.setAccessibleName(full_text)
                cell.setMinimumWidth(compact_width)
                cell.setMinimumHeight(field.live_cell_height)
                cell.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(cell, compact_width)
            layout.addStretch(1)
            return panel

        @staticmethod
        def apply_securecrt_sftp_browser_action_route_properties(
            widget,
            route,
            *,
            triggered: bool = False,
            action_key: str | None = None,
            status: str | None = None,
        ) -> None:
            actions_value = "|".join(route.toolbar_actions)
            action_value = action_key or route.action_key
            status_value = status or route.transfer_status
            properties = {
                "secureCrtSftpBrowserRouteKey": route.key,
                "secureCrtSftpBrowserRouteRole": route.route_role,
                "secureCrtSftpBrowserTabRouteKey": route.sftp_tab_route_key,
                "secureCrtSftpBrowserObject": route.browser_object,
                "secureCrtSftpBrowserToolbarObject": route.toolbar_object,
                "secureCrtSftpBrowserPathObject": route.path_object,
                "secureCrtSftpBrowserTableObject": route.table_object,
                "secureCrtSftpBrowserRowObject": route.row_object,
                "secureCrtSftpBrowserQueueObject": route.queue_object,
                "secureCrtSftpBrowserSelectedProfile": route.selected_profile_name,
                "secureCrtSftpBrowserSelectedTreeLabel": route.selected_tree_label,
                "secureCrtSftpBrowserTabLabel": route.sftp_tab_label,
                route.path_property: route.remote_path,
                route.toolbar_actions_property: actions_value,
                "secureCrtSftpBrowserActiveRowName": route.active_row_name,
                "secureCrtSftpBrowserQueueLabel": route.transfer_queue_label,
                route.queue_state_property: route.transfer_status,
                "secureCrtSftpBrowserActionObject": route.action_object,
                "secureCrtSftpBrowserActionKey": action_value,
                "secureCrtSftpBrowserActionLabel": route.action_label,
                route.signal_property: route.signal,
                route.handler_property: route.handler,
                route.captured_property: triggered,
                route.captured_action_property: action_value if triggered else "",
                route.captured_status_property: status_value if triggered else "",
                route.live_triggered_property: triggered,
                route.live_action_property: action_value,
                route.live_status_property: status_value,
                "secureCrtSftpBrowserRenderSource": route.render_source,
            }
            for property_name, value in properties.items():
                widget.setProperty(property_name, value)

        def handle_securecrt_sftp_browser_action(self, action_key: str | None = None) -> None:
            route = gui_design_securecrt_sftp_browser_route()
            action_value = action_key or route.action_key
            status_value = (
                route.action_status
                if action_value == route.action_key
                else f"{action_value} queued"
            )
            queue = getattr(self, "securecrt_sftp_queue", None)
            if queue is not None:
                queue.setText(f"Queue: {route.transfer_queue_label} ({status_value})")
            route_widgets = (
                getattr(self, "securecrt_sftp_browser_panel", None),
                getattr(self, "securecrt_sftp_toolbar", None),
                getattr(self, "securecrt_sftp_path", None),
                getattr(self, "securecrt_sftp_table", None),
                queue,
                *getattr(self, "securecrt_sftp_action_buttons", []),
                getattr(self, "securecrt_sftp_active_row", None),
            )
            for route_widget in route_widgets:
                if route_widget is None:
                    continue
                self.apply_securecrt_sftp_browser_action_route_properties(
                    route_widget,
                    route,
                    triggered=True,
                    action_key=action_value,
                    status=status_value,
                )
            self.statusBar().showMessage(f"SecureCRT SFTP {action_value}: {status_value}")

        def build_securecrt_sftp_browser_evidence(self) -> QFrame:
            route = gui_design_securecrt_sftp_browser_route()
            actions_value = "|".join(route.toolbar_actions)
            route_props = {
                "secureCrtSftpBrowserRouteKey": route.key,
                "secureCrtSftpBrowserRouteRole": route.route_role,
                "secureCrtSftpBrowserTabRouteKey": route.sftp_tab_route_key,
                "secureCrtSftpBrowserObject": route.browser_object,
                "secureCrtSftpBrowserToolbarObject": route.toolbar_object,
                "secureCrtSftpBrowserPathObject": route.path_object,
                "secureCrtSftpBrowserTableObject": route.table_object,
                "secureCrtSftpBrowserRowObject": route.row_object,
                "secureCrtSftpBrowserQueueObject": route.queue_object,
                "secureCrtSftpBrowserSelectedProfile": route.selected_profile_name,
                "secureCrtSftpBrowserSelectedTreeLabel": route.selected_tree_label,
                "secureCrtSftpBrowserTabLabel": route.sftp_tab_label,
                route.path_property: route.remote_path,
                route.toolbar_actions_property: actions_value,
                "secureCrtSftpBrowserActiveRowName": route.active_row_name,
                "secureCrtSftpBrowserQueueLabel": route.transfer_queue_label,
                "secureCrtSftpBrowserQueueState": route.transfer_status,
                "secureCrtSftpBrowserRenderSource": route.render_source,
            }
            panel = QFrame()
            panel.setObjectName(route.browser_object)
            for property_name, value in route_props.items():
                panel.setProperty(property_name, value)
            self.securecrt_sftp_browser_panel = panel
            self.apply_securecrt_sftp_browser_action_route_properties(panel, route)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 7, 8, 7)
            layout.setSpacing(5)

            header = QHBoxLayout()
            title = _literal_label(f"SFTP - {route.sftp_tab_label}")
            title.setObjectName("secureCrtSftpTitle")
            title.setProperty("secureCrtSftpBrowserRouteKey", route.key)
            title.setProperty("secureCrtSftpBrowserTabLabel", route.sftp_tab_label)
            queue = _literal_label(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
            queue.setObjectName(route.queue_object)
            for property_name, value in route_props.items():
                queue.setProperty(property_name, value)
            self.securecrt_sftp_queue = queue
            self.apply_securecrt_sftp_browser_action_route_properties(queue, route)
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(queue)
            layout.addLayout(header)

            toolbar = QFrame()
            toolbar.setObjectName(route.toolbar_object)
            for property_name, value in route_props.items():
                toolbar.setProperty(property_name, value)
            self.securecrt_sftp_toolbar = toolbar
            self.apply_securecrt_sftp_browser_action_route_properties(toolbar, route)
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(6)
            self.securecrt_sftp_action_buttons = []
            for action_key in route.toolbar_actions:
                action = QToolButton()
                action.setObjectName(route.action_object)
                action.setProperty("secureCrtSftpBrowserRouteKey", route.key)
                action.setProperty("secureCrtSftpBrowserActionKey", action_key)
                action.setProperty(route.toolbar_actions_property, actions_value)
                self.apply_securecrt_sftp_browser_action_route_properties(
                    action,
                    route,
                    action_key=action_key,
                )
                self.securecrt_sftp_action_buttons.append(action)
                if action_key == route.action_key:
                    self.securecrt_sftp_action_button = action
                action.clicked.connect(
                    lambda _checked=False, key=action_key: self.handle_securecrt_sftp_browser_action(
                        key
                    )
                )
                action.setText(action_key.title())
                action.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                toolbar_layout.addWidget(action)
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            path = _literal_label(f"Remote path: {route.remote_path}")
            path.setObjectName(route.path_object)
            for property_name, value in route_props.items():
                path.setProperty(property_name, value)
            self.securecrt_sftp_path = path
            self.apply_securecrt_sftp_browser_action_route_properties(path, route)
            layout.addWidget(path)

            table = QFrame()
            table.setObjectName(route.table_object)
            for property_name, value in route_props.items():
                table.setProperty(property_name, value)
            self.securecrt_sftp_table = table
            self.apply_securecrt_sftp_browser_action_route_properties(table, route)
            table_layout = QVBoxLayout(table)
            table_layout.setContentsMargins(0, 0, 0, 0)
            table_layout.setSpacing(2)
            header_row = QLabel("Name        Size     Modified")
            header_row.setObjectName("secureCrtSftpHeader")
            table_layout.addWidget(header_row)
            for row in route.file_rows:
                row_frame = QFrame()
                row_frame.setObjectName(route.row_object)
                for property_name, value in route_props.items():
                    row_frame.setProperty(property_name, value)
                row_frame.setProperty(route.row_name_property, row.name)
                row_frame.setProperty(route.row_kind_property, row.kind)
                row_frame.setProperty(route.row_selected_property, row.selected)
                row_frame.setProperty("secureCrtSftpBrowserRowKey", row.key)
                row_frame.setProperty("secureCrtSftpBrowserRowSize", row.size)
                row_frame.setProperty("secureCrtSftpBrowserRowModified", row.modified)
                self.apply_securecrt_sftp_browser_action_route_properties(row_frame, route)
                if row.name == route.active_row_name:
                    self.securecrt_sftp_active_row = row_frame
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(8)
                name = _literal_label(row.name)
                name.setObjectName("secureCrtSftpRowName")
                size = _literal_label(row.size)
                size.setObjectName("secureCrtSftpRowSize")
                modified = _literal_label(row.modified)
                modified.setObjectName("secureCrtSftpRowModified")
                row_layout.addWidget(name, 2)
                row_layout.addWidget(size, 1)
                row_layout.addWidget(modified, 1)
                table_layout.addWidget(row_frame)
            layout.addWidget(table)
            return panel

        @staticmethod
        def apply_securecrt_command_window_send_route_properties(
            widget,
            route,
            chrome,
            *,
            submitted: bool = False,
            command: str | None = None,
            status: str | None = None,
        ) -> None:
            command_value = chrome.command if command is None else command
            status_value = chrome.status if status is None else status
            properties = {
                "secureCrtCommandRouteKey": route.key,
                "secureCrtCommandRouteRole": route.route_role,
                "secureCrtCommandRouteSourceWindowObject": route.source_window_object,
                "secureCrtCommandRouteTargetScopeObject": route.target_scope_object,
                "secureCrtCommandRouteCommandInputObject": route.command_input_object,
                "secureCrtCommandRouteSendControlObject": route.send_control_object,
                "secureCrtCommandRouteStatusObject": route.status_object,
                "secureCrtCommandRouteCommand": command_value,
                "secureCrtCommandRouteTargetScope": chrome.target_scope,
                "secureCrtCommandRouteSendLabel": chrome.send_label,
                "secureCrtCommandRouteStatus": status_value,
                route.captured_property: submitted,
                route.captured_command_property: command_value if submitted else "",
                route.captured_target_scope_property: chrome.target_scope if submitted else "",
                route.captured_status_property: status_value if submitted else "",
                route.signal_property: route.signal,
                route.secondary_signal_property: route.secondary_signal,
                route.handler_property: route.handler,
                "secureCrtCommandRouteLiveSubmitted": submitted,
                "secureCrtCommandRouteLiveCommand": command_value,
                "secureCrtCommandRouteLiveTargetScope": chrome.target_scope,
                "secureCrtCommandRouteLiveStatus": status_value,
                "secureCrtCommandRouteRenderSource": route.render_source,
            }
            for property_name, value in properties.items():
                widget.setProperty(property_name, value)

        def handle_securecrt_command_window_send(self, _checked: bool = False) -> None:
            chrome = gui_design_securecrt_command_window_chrome()
            route = gui_design_securecrt_command_window_send_route()
            command_input = getattr(self, "securecrt_command_input", None)
            command = command_input.text().strip() if command_input is not None else chrome.command
            if not command:
                command = chrome.command
                if command_input is not None:
                    command_input.setText(command)
            status_text = "sent"
            status = getattr(self, "securecrt_command_status", None)
            if status is not None:
                status.setText(status_text)
            route_widgets = (
                getattr(self, "securecrt_command_window", None),
                getattr(self, "securecrt_command_target", None),
                command_input,
                getattr(self, "securecrt_command_send", None),
                status,
            )
            for route_widget in route_widgets:
                if route_widget is None:
                    continue
                self.apply_securecrt_command_window_send_route_properties(
                    route_widget,
                    route,
                    chrome,
                    submitted=True,
                    command=command,
                    status=status_text,
                )
            self.statusBar().showMessage(f"SecureCRT command sent to {chrome.target_scope}: {command}")

        def build_securecrt_command_window_evidence(self) -> QFrame:
            chrome = gui_design_securecrt_command_window_chrome()
            send_route = gui_design_securecrt_command_window_send_route()
            panel = QFrame()
            panel.setObjectName("secureCrtCommandWindow")
            self.securecrt_command_window = panel
            panel.setProperty("secureCrtCommandWindowKey", chrome.key)
            panel.setProperty("secureCrtCommandStaticHeaderHeight", chrome.static_header_height)
            panel.setProperty("secureCrtCommandStaticTitleX", chrome.static_title_x)
            panel.setProperty("secureCrtCommandStaticTitleY", chrome.static_title_y)
            panel.setProperty("secureCrtCommandStaticHelperX", chrome.static_helper_x)
            panel.setProperty("secureCrtCommandStaticHelperY", chrome.static_helper_y)
            panel.setProperty("secureCrtCommandStaticControlY", chrome.static_control_y)
            panel.setProperty("secureCrtCommandStaticTargetWidth", chrome.static_target_width)
            panel.setProperty("secureCrtCommandStaticInputX", chrome.static_input_x)
            panel.setProperty("secureCrtCommandStaticSendWidth", chrome.static_send_width)
            panel.setProperty("secureCrtCommandLiveTargetMinWidth", chrome.live_target_min_width)
            panel.setProperty("secureCrtCommandLiveSendMinWidth", chrome.live_send_min_width)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(
                chrome.live_margin_left,
                chrome.live_margin_top,
                chrome.live_margin_right,
                chrome.live_margin_bottom,
            )
            layout.setSpacing(chrome.live_spacing)

            header = QHBoxLayout()
            header.setSpacing(chrome.live_header_spacing)
            title = QLabel(chrome.title)
            title.setObjectName("secureCrtCommandTitle")
            helper = QLabel(chrome.helper)
            helper.setObjectName("secureCrtCommandHelper")
            header.addWidget(title)
            header.addWidget(helper)
            header.addStretch(1)
            layout.addLayout(header)

            command_row = QHBoxLayout()
            command_row.setSpacing(chrome.live_row_spacing)
            target = _literal_label(chrome.target_scope)
            target.setObjectName("secureCrtCommandTarget")
            self.securecrt_command_target = target
            target.setProperty("secureCrtCommandWindowKey", chrome.key)
            target.setProperty("secureCrtCommandStaticTargetWidth", chrome.static_target_width)
            target.setProperty("secureCrtCommandLiveTargetMinWidth", chrome.live_target_min_width)
            target.setMinimumWidth(chrome.live_target_min_width)
            command_input = QLineEdit(chrome.command)
            command_input.setObjectName("secureCrtCommandInput")
            self.securecrt_command_input = command_input
            command_input.setProperty("secureCrtCommandWindowKey", chrome.key)
            command_input.setProperty("secureCrtCommandStaticInputX", chrome.static_input_x)
            command_input.setProperty("secureCrtCommandStaticInputTextX", chrome.static_input_text_x)
            command_input.setProperty("secureCrtCommandStaticInputTextY", chrome.static_input_text_y)
            command_input.setPlaceholderText(chrome.command)
            command_input.returnPressed.connect(self.handle_securecrt_command_window_send)
            send = QPushButton(chrome.send_label)
            send.setObjectName("secureCrtCommandSend")
            self.securecrt_command_send = send
            send.setProperty("secureCrtCommandWindowKey", chrome.key)
            send.setProperty("secureCrtCommandStaticSendWidth", chrome.static_send_width)
            send.setProperty("secureCrtCommandLiveSendMinWidth", chrome.live_send_min_width)
            send.setMinimumWidth(chrome.live_send_min_width)
            send.clicked.connect(self.handle_securecrt_command_window_send)
            status = _literal_label(chrome.status)
            status.setObjectName("secureCrtCommandStatus")
            self.securecrt_command_status = status
            status.setProperty("secureCrtCommandWindowKey", chrome.key)
            route_widgets = (panel, target, command_input, send, status)
            for route_widget in route_widgets:
                self.apply_securecrt_command_window_send_route_properties(route_widget, send_route, chrome)
            command_row.addWidget(target)
            command_row.addWidget(command_input, 1)
            command_row.addWidget(send)
            command_row.addWidget(status)
            layout.addLayout(command_row)
            return panel

        def build_product_reference_state_evidence(self) -> QFrame:
            reference = gui_design_reference_state(self.current_design_id())
            route = gui_design_product_identity_route(self.current_design_id())
            selection_route = gui_design_preset_selection_route(self.current_design_id())
            panel = QFrame()
            panel.setObjectName("productReferenceState")
            panel.setProperty("designPreset", self.current_design_id())
            self.apply_product_identity_route_properties(panel, route)
            self.apply_preset_selection_route_properties(panel, selection_route)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(8)
            for key, value in reference.items():
                label = _literal_label(f"{key}: {value}")
                label.setObjectName("productReferenceStateItem")
                label.setProperty("referenceKey", key)
                self.apply_product_identity_route_properties(label, route)
                self.apply_preset_selection_route_properties(label, selection_route)
                label.setToolTip(_safe_tooltip_html(f"{reference.active_tab_label} {key}"))
                layout.addWidget(label)
            layout.addStretch(1)
            return panel

        def apply_product_identity_route_properties(self, widget, route) -> None:
            properties = {
                "productIdentityRouteKey": route.key,
                "productIdentityRouteRole": route.route_role,
                "productIdentityPreset": route.preset_id,
                "productIdentitySelectedTreeLabel": route.selected_tree_label,
                "productIdentityReferenceStateObject": route.reference_state_object,
                "productIdentityReferenceItemObject": route.reference_item_object,
                "productIdentityTreeObject": route.tree_object,
                "productIdentityTabsObject": route.tabs_object,
                "productIdentityStatusSegmentObject": route.status_segment_object,
                "productIdentityWorkspaceSurfaceObject": route.workspace_surface_object,
                "productIdentityProfile": route.selected_profile_name,
                "productIdentityTarget": route.target_label,
                "productIdentityProtocol": route.protocol_label,
                "productIdentityActiveTab": route.active_tab_label,
                "productIdentitySidebar": route.sidebar_label,
                "productIdentityWorkspaceState": route.workspace_state,
                "productIdentityStatusSegments": list(route.status_segments),
                "productIdentityRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def build_product_workspace_pane(
            self,
            object_name: str,
            title: str,
            lead: str,
            lines: tuple[str, ...],
        ) -> QFrame:
            pane = QFrame()
            pane.setObjectName(object_name)
            pane_layout = QVBoxLayout(pane)
            pane_layout.setContentsMargins(8, 7, 8, 7)
            pane_layout.setSpacing(4)
            pane_title = _literal_label(title)
            pane_title.setObjectName("productWorkspacePaneTitle")
            pane_layout.addWidget(pane_title)
            lead_label = _literal_label(lead)
            lead_label.setObjectName("productWorkspaceLead")
            lead_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            pane_layout.addWidget(lead_label)
            for line in lines:
                line_label = _literal_label(line)
                line_label.setObjectName("productWorkspaceLine")
                line_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                pane_layout.addWidget(line_label)
            return pane

        def run_home_search(self, text: str) -> None:
            self.quick_connect.setText(text)
            self.run_quick_connect()

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

        def focus_securecrt_host(self) -> None:
            self.securecrt_host_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.securecrt_host_input.selectAll()

        def focus_securecrt_keyword(self) -> None:
            self.securecrt_keyword_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.securecrt_keyword_input.selectAll()

        def find_product_keyword(self, text: str) -> None:
            """Route SecureCRT's keyword field through the shared terminal finder."""
            query = text.strip()
            self.search_input.setText(query)
            self.find_log_text()

        def open_local_terminal_tab(self) -> None:
            self.open_terminal_tab(default_shell_plan(self.next_shell_index()))

        def next_shell_index(self) -> int:
            count = sum(1 for pane in self.all_terminal_panes() if pane.plan.source == "shell")
            return count + 1

        def profile_tab_status(self) -> str:
            return gui_design_interaction_state(self.current_design_id()).active_tab_status

        def open_terminal_tab(
            self,
            plan: TerminalPanePlan,
            *,
            profile: Profile | None = None,
            tab_title: str | None = None,
            tab_status: str | None = None,
        ) -> None:
            # Construct the pane before inserting the tab, but start the child
            # only after Qt has selected and laid out the page. This prevents a
            # transient unparented terminal surface from flashing during tab
            # changes and gives ConPTY its final viewport dimensions.
            pane = self.new_terminal_pane(plan, profile=profile, autostart=False)
            self.remember_terminal_plan(plan, profile=profile)
            tab_content: QWidget = pane
            reference_label = tab_title or plan.title
            reference_route = (
                gui_design_preset_reference_tab_route(self.current_design_id())
                if self.current_design_id() in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            if reference_route is not None and reference_label == reference_route.active_tab_label:
                tab_content = self.build_product_reference_tab_surface(pane)
            index = self.add_workspace_tab(tab_content, reference_label, role="terminal")
            if tab_content is not pane:
                # Route metadata is asserted on the tab's root widget as well
                # as on the embedded TerminalPane.  Preserve both surfaces so
                # the connected document wrapper remains fully inspectable.
                self.apply_reference_tab_route_to_terminal_tab(tab_content, reference_label)
                self.apply_reference_tab_chrome_route_to_terminal_tab(tab_content, reference_label, index)
                self.apply_reference_status_bar_route_to_terminal_tab(tab_content, reference_label)
                self.apply_reference_session_action_route_to_terminal_tab(tab_content, reference_label, index)
            self.apply_reference_tab_route_to_terminal_tab(pane, tab_title or plan.title)
            if tab_status:
                self.set_literal_tab_tooltip(
                    index,
                    f"{tab_title or plan.title}: {tab_status}",
                    update_base=False,
                )
            self.apply_reference_tab_chrome_route_to_terminal_tab(pane, tab_title or plan.title, index)
            self.update_session_status()
            self.apply_reference_status_bar_route_to_terminal_tab(pane, tab_title or plan.title)
            self.apply_reference_session_action_route_to_terminal_tab(pane, tab_title or plan.title, index)
            self.start_terminal_pane_when_active(pane, index)

        def start_terminal_pane_when_active(self, pane: TerminalPane, index: int) -> None:
            """Start a deferred pane after its tab has a stable parent/layout."""

            pane.setProperty("terminalStartDeferredUntilTabReady", True)

            def start_if_current() -> None:
                self.start_deferred_terminal_pane_if_current(pane, index)

            QTimer.singleShot(0, start_if_current)

        def build_product_reference_tab_surface(self, pane: TerminalPane) -> QWidget:
            """Compose a product-native connected document around the live pane.

            The terminal process remains a real child (so stdin, selection and
            lifecycle contracts stay intact), while the product-specific
            viewer/SFTP/document canvas is the first thing users see after
            connecting.
            """
            surface = QFrame()
            surface.setObjectName("productReferenceTabSurface")
            surface.setProperty("designPreset", self.current_design_id())
            surface.setProperty("productReferenceTabSurfaceRole", "connected-product-document")
            layout = QVBoxLayout(surface)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            preset_id = self.current_design_id()
            self.configure_product_reference_terminal_pane(pane, preset_id)
            product_surface: QWidget | None = None
            if preset_id == "termius":
                product_surface = self.build_termius_native_sftp_surface(pane)
            elif preset_id == "remmina":
                product_surface = self.build_remmina_native_viewer_surface(pane)
            elif preset_id == "mremoteng":
                product_surface = self.build_mremoteng_runtime_document_surface(pane)
            if product_surface is not None:
                layout.addWidget(product_surface, 1)
            else:
                # SecureCRT is already terminal-led, so its real pane is the
                # connected document surface rather than a nested product
                # viewer.
                layout.addWidget(pane, 1)
            return surface

        @staticmethod
        def configure_product_reference_terminal_pane(
            pane: TerminalPane,
            preset_id: str,
        ) -> None:
            """Use the reference product's document chrome around the live terminal.

            The normal workspace pane intentionally exposes process controls,
            a launch-command row and the safe line-input fallback.  Connected
            SecureCRT/mRemoteNG/Remmina/Termius documents expose those controls
            through their product toolbars instead, so the duplicate generic
            grid is hidden while the real terminal output and input remain
            live and inspectable.
            """
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                return
            pane.setProperty("productReferenceTerminalPreset", preset_id)
            pane.setProperty("productReferenceTerminalChrome", "connected-document")
            pane.command_row.setVisible(False)
            for button in pane.terminal_action_buttons:
                button.setVisible(False)
            pane_style = _widget_style(pane)
            pane_style.unpolish(pane)
            pane_style.polish(pane)

        def tab_position_name(self) -> str:
            return {
                QTabWidget.TabPosition.North: "north",
                QTabWidget.TabPosition.South: "south",
                QTabWidget.TabPosition.West: "west",
                QTabWidget.TabPosition.East: "east",
            }.get(self.tabs.tabPosition(), "north")

        def apply_reference_tab_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None:
            preset_id = self.current_design_id()
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                return
            route = gui_design_preset_reference_tab_route(preset_id)
            if tab_title != route.active_tab_label:
                return
            surface_route = gui_design_preset_reference_surface_route(preset_id)
            control_route = gui_design_preset_reference_control_route(preset_id)
            input_route = gui_design_preset_reference_input_route(preset_id)
            transcript_route = gui_design_preset_reference_transcript_route(preset_id)
            for widget in (pane, self.tabs):
                self.apply_preset_reference_tab_route_properties(widget, route)
                widget.setProperty(route.active_tab_property, route.active_tab_label)
                widget.setProperty(route.reference_profile_property, route.reference_profile)
            self.tabs.setProperty(route.activated_label_property, route.active_tab_label)
            self.apply_reference_surface_route_to_terminal_tab(pane, tab_title, surface_route)
            self.apply_reference_control_route_to_terminal_tab(pane, tab_title, control_route)
            self.apply_reference_input_route_to_terminal_tab(pane, tab_title, input_route)
            self.apply_reference_transcript_route_to_terminal_tab(pane, tab_title, transcript_route)

        def apply_reference_tab_chrome_route_to_terminal_tab(
            self,
            pane: QWidget,
            tab_title: str,
            tab_index: int,
        ) -> None:
            preset_id = self.current_design_id()
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                return
            route = gui_design_preset_reference_tab_chrome_route(preset_id)
            if tab_title != route.active_tab_label or tab_index < 0:
                return
            tab_role = self.tab_role(tab_index)
            tooltip = self.literal_tab_tooltip(tab_index)
            closeable = bool(self.tabs.tabsClosable() and tab_role == route.reference_tab_role)
            selected = self.tabs.currentIndex() == tab_index
            position = self.tab_position_name()
            for widget in (pane, self.tabs, self.moba_tab_bar):
                self.apply_preset_reference_tab_chrome_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_label_property, self.tabs.tabText(tab_index))
                widget.setProperty(route.captured_tooltip_property, tooltip)
                widget.setProperty(route.captured_index_property, tab_index)
                widget.setProperty(route.captured_role_property, tab_role)
                widget.setProperty(route.captured_position_property, position)
                widget.setProperty(route.captured_closeable_property, closeable)
                widget.setProperty(route.captured_selected_property, selected)

        def apply_reference_status_bar_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None:
            preset_id = self.current_design_id()
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                return
            route = gui_design_preset_reference_status_bar_route(preset_id)
            if tab_title != route.active_tab_label:
                return
            segment_texts = [label.text() for label in self.status_segment_labels if label.text()]
            segment_tooltips = [label.toolTip() for label in self.status_segment_labels if label.text()]
            notice_text = self.status_notice_label.text()
            message = self.statusBar().currentMessage()
            for widget in (pane, self.tabs, self.statusBar(), self.status_notice_label, *self.status_segment_labels):
                self.apply_preset_reference_status_bar_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_message_property, message)
                widget.setProperty(route.captured_segments_property, segment_texts)
                widget.setProperty(route.captured_segment_count_property, len(segment_texts))
                widget.setProperty(route.captured_segment_tooltips_property, segment_tooltips)
                widget.setProperty(route.captured_notice_property, notice_text)

        def apply_reference_session_action_route_to_terminal_tab(
            self,
            pane: QWidget,
            tab_title: str,
            tab_index: int,
        ) -> None:
            preset_id = self.current_design_id()
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
                return
            route = gui_design_preset_reference_session_action_route(preset_id)
            if tab_title != route.active_tab_label or tab_index < 0:
                return
            specs = self.tab_context_session_action_specs(tab_index)
            action_keys = [str(spec["key"]) for spec in specs]
            action_labels = [str(spec["label"]) for spec in specs]
            enabled_keys = [str(spec["key"]) for spec in specs if bool(spec["enabled"])]
            disabled_keys = [str(spec["key"]) for spec in specs if not bool(spec["enabled"])]
            for widget in (pane, self.tabs, self.moba_tab_bar):
                self.apply_preset_reference_session_action_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_action_keys_property, action_keys)
                widget.setProperty(route.captured_action_labels_property, action_labels)
                widget.setProperty(route.captured_action_count_property, len(action_keys))
                widget.setProperty(route.captured_enabled_keys_property, enabled_keys)
                widget.setProperty(route.captured_disabled_keys_property, disabled_keys)

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
                self.apply_moba_connected_session_action_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_action_keys_property, action_keys)
                widget.setProperty(route.captured_action_labels_property, action_labels)
                widget.setProperty(route.captured_action_count_property, len(action_keys))
                widget.setProperty(route.captured_enabled_keys_property, enabled_keys)
                widget.setProperty(route.captured_disabled_keys_property, disabled_keys)

        def apply_reference_surface_route_to_terminal_tab(self, pane: QWidget, tab_title: str, route) -> None:
            child_widgets = [
                getattr(pane, "title", None),
                getattr(pane, "source", None),
                getattr(pane, "command_preview", None),
                getattr(pane, "output", None),
            ]
            actual_title = getattr(getattr(pane, "title", None), "text", lambda: "")()
            actual_source = getattr(getattr(pane, "source", None), "text", lambda: "")()
            actual_command = getattr(getattr(pane, "plan", None), "printable", lambda: "")()
            output_widget = getattr(pane, "output", None)
            actual_output = getattr(output_widget, "toPlainText", lambda: "")()
            for widget in (pane, self.tabs, *[item for item in child_widgets if item is not None]):
                self.apply_preset_reference_surface_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.actual_title_property, actual_title)
                widget.setProperty(route.actual_source_property, actual_source)
                widget.setProperty(route.actual_command_property, actual_command)
                widget.setProperty(route.actual_output_property, actual_output)

        def apply_reference_control_route_to_terminal_tab(self, pane: QWidget, tab_title: str, route) -> None:
            action_button_candidates = [
                getattr(pane, "start_button", None),
                getattr(pane, "restart_button", None),
                getattr(pane, "stop_button", None),
                getattr(pane, "copy_button", None),
                getattr(pane, "clear_button", None),
            ]
            action_buttons = [
                button
                for button in action_button_candidates
                if isinstance(button, QAbstractButton)
            ]
            status_candidate = getattr(pane, "status", None)
            status_widget = (
                status_candidate if isinstance(status_candidate, QLabel) else None
            )
            action_keys = [str(button.property(route.action_key_property) or "") for button in action_buttons]
            status_state = str(status_widget.property(route.status_state_property) or "") if status_widget is not None else ""
            status_text = status_widget.text() if status_widget is not None else ""
            for widget in (pane, self.tabs, status_widget, *action_buttons):
                if widget is None:
                    continue
                self.apply_preset_reference_control_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_actions_property, action_keys)
                widget.setProperty(route.captured_status_property, status_state)
                widget.setProperty(route.captured_status_text_property, status_text)
                widget.setProperty("presetReferenceControlCapturedTab", tab_title)

        def apply_reference_input_route_to_terminal_tab(self, pane: QWidget, tab_title: str, route) -> None:
            input_widget = getattr(pane, "input", None)
            placeholder = input_widget.placeholderText() if input_widget is not None else ""
            text = input_widget.text() if input_widget is not None else ""
            enabled = input_widget.isEnabled() if input_widget is not None else False
            for widget in (pane, self.tabs, input_widget):
                if widget is None:
                    continue
                self.apply_preset_reference_input_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_placeholder_property, placeholder)
                widget.setProperty(route.captured_text_property, text)
                widget.setProperty(route.captured_enabled_property, enabled)

        def apply_reference_transcript_route_to_terminal_tab(self, pane: QWidget, tab_title: str, route) -> None:
            output_widget = getattr(pane, "output", None)
            transcript = output_widget.toPlainText() if output_widget is not None else ""
            lines = transcript.splitlines()
            command_echo = next((line for line in lines if line.startswith(route.command_echo_prefix)), "")
            for widget in (pane, self.tabs, output_widget):
                if widget is None:
                    continue
                self.apply_preset_reference_transcript_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_tab_property, tab_title)
                widget.setProperty(route.captured_text_property, transcript)
                widget.setProperty(route.captured_line_count_property, len(lines))
                widget.setProperty(route.captured_command_echo_property, command_echo)

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
        ) -> MobaConnectedSessionPanel:
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

        def add_split(self, direction: str) -> None:
            orientation = (
                Qt.Orientation.Horizontal if direction == "horizontal" else Qt.Orientation.Vertical
            )
            current = self.tabs.currentWidget()
            current_index = self.tabs.currentIndex()
            current_role = self.tab_role(current_index)
            label = "Split H" if direction == "horizontal" else "Split V"

            if isinstance(current, MobaConnectedSessionPanel) and current_role == "terminal":
                source_pane = current.terminal_pane
                plan = source_pane.plan
                profile = source_pane.profile
                pane = self.new_terminal_pane(plan, profile=profile)
                current.add_terminal_split(pane, orientation)
                self.remember_terminal_plan(plan, profile=profile)
                self.set_literal_tab_tooltip(
                    current_index,
                    f"{self.tabs.tabText(current_index)}: {label}, "
                    f"{current.terminal_splitter.count()} active panes",
                )
                self.refresh_moba_left_dock_for_current_tab()
                self.update_session_status()
                return

            if (
                isinstance(current, QSplitter)
                and current_role == "split"
                and self.terminal_panes_in(current)
            ):
                current.setOrientation(orientation)
                plan = default_shell_plan()
                current.addWidget(self.new_terminal_pane(plan))
                self.remember_terminal_plan(plan)
                self.equalize_ad_hoc_splitter(current)
                self.tabs.setTabText(current_index, f"{label} {current.count()}")
                self.set_literal_tab_tooltip(
                    current_index,
                    f"{label}: {current.count()} active panes",
                )
                self.update_session_status()
                return

            splitter = QSplitter(orientation)
            if (
                current is not None
                and current_index >= 0
                and (
                    isinstance(current, TerminalPane)
                    or current_role == "layout"
                    or (
                        current_role == "terminal"
                        and bool(self.terminal_panes_in(current))
                    )
                )
            ):
                title = self.tabs.tabText(current_index)
                tooltip = self.base_tab_tooltip(current_index) or title
                previous_guard = self.moba_tab_guard
                self.moba_tab_guard = True
                try:
                    self.tabs.removeTab(current_index)
                    splitter.addWidget(current)
                    plan = default_shell_plan()
                    splitter.addWidget(self.new_terminal_pane(plan))
                    self.remember_terminal_plan(plan)
                    splitter.setProperty("tabRole", "split")
                    new_index = self.tabs.insertTab(
                        current_index,
                        splitter,
                        f"{title} · {label}",
                    )
                    self.set_literal_tab_tooltip(new_index, f"{tooltip} · {label}")
                    self.tabs.setCurrentIndex(new_index)
                finally:
                    self.moba_tab_guard = previous_guard
                preset = get_gui_design_preset(self.current_design_id())
                self.apply_interaction_state_tab_status(
                    preset,
                    gui_design_interaction_state(preset.id),
                )
                self.equalize_ad_hoc_splitter(splitter)
                self.refresh_special_tab_buttons()
                self.refresh_moba_left_dock_for_current_tab()
                self.update_session_status()
                return

            active = self.active_terminal_pane()
            sessions = (
                [(active.plan, active.profile), (default_shell_plan(), None)]
                if active is not None
                else [(plan, None) for plan in split_shell_plans(2)]
            )
            for plan, profile in sessions:
                splitter.addWidget(self.new_terminal_pane(plan, profile=profile))
                self.remember_terminal_plan(plan, profile=profile)
            self.add_workspace_tab(
                splitter, f"{label} {self.count_closeable_tabs() + 1}", role="split"
            )
            self.equalize_ad_hoc_splitter(splitter)
            self.update_session_status()

        @staticmethod
        def equalize_ad_hoc_splitter(splitter: QSplitter) -> None:
            splitter.setChildrenCollapsible(False)
            for index in range(splitter.count()):
                child = splitter.widget(index)
                if child is not None:
                    child.show()
                splitter.setCollapsible(index, False)
                splitter.setStretchFactor(index, 1)
            splitter.setSizes([1000] * splitter.count())

        def remember_terminal_plan(
            self,
            plan: TerminalPanePlan,
            *,
            profile: Profile | None = None,
        ) -> None:
            self.recent_terminal_plans.append((plan, profile))
            self.recent_terminal_plans = self.recent_terminal_plans[-8:]

        def duplicate_current_tab(self) -> None:
            index = self.tabs.currentIndex()
            if index < 0 or self.tab_role(index) in {"home", "new-session"}:
                self.open_local_terminal_tab()
                return
            widget = self.tabs.widget(index)
            title = self.tabs.tabText(index)
            if isinstance(widget, MobaConnectedSessionPanel):
                state = self.moba_connected_state_in_widget(widget)
                source_panes = self.terminal_panes_in(widget)
                if state is not None and source_panes and source_panes[0].profile is not None:
                    duplicate = self.open_moba_connected_session_tab(
                        source_panes[0].profile,
                        source_panes[0].plan,
                        remote_path=state.remote_path,
                        tab_title=f"{title} copy",
                        tab_status="duplicated",
                    )
                    orientation = widget.terminal_splitter.orientation()
                    for source_pane in source_panes[1:]:
                        duplicate.add_terminal_split(
                            self.new_terminal_pane(
                                source_pane.plan,
                                profile=source_pane.profile,
                            ),
                            orientation,
                        )
                        self.remember_terminal_plan(
                            source_pane.plan,
                            profile=source_pane.profile,
                        )
                    source_sizes = [max(1, int(size)) for size in widget.terminal_splitter.sizes()]
                    if len(source_sizes) == duplicate.terminal_splitter.count():
                        duplicate.terminal_splitter.setSizes(source_sizes)
                    self.log.append(f"TAB DUPLICATED: {title}")
                    return
            if isinstance(widget, TerminalPane):
                self.open_terminal_tab(
                    widget.plan,
                    profile=widget.profile,
                    tab_title=f"{title} copy",
                    tab_status="duplicated",
                )
                self.log.append(f"TAB DUPLICATED: {title}")
                return
            panes = self.terminal_panes_in(widget) if widget is not None else []
            if not panes:
                self.open_local_terminal_tab()
                return
            if isinstance(widget, QSplitter) and self.terminal_splitter_clone_supported(widget):
                splitter = self.clone_terminal_splitter(widget)
            else:
                splitter = QSplitter(Qt.Orientation.Horizontal)
                for pane in panes:
                    splitter.addWidget(self.new_terminal_pane(pane.plan, profile=pane.profile))
                    self.remember_terminal_plan(pane.plan, profile=pane.profile)
                self.equalize_ad_hoc_splitter(splitter)
            source_role = self.tab_role(index)
            duplicate_role = source_role if source_role in {"layout", "split"} else "split"
            self.add_workspace_tab(splitter, f"{title} copy", role=duplicate_role)
            self.bind_cloned_layout_persistence(splitter)
            self.log.append(f"TAB DUPLICATED: {title}")
            self.update_session_status()

        def terminal_splitter_clone_supported(self, source: QSplitter) -> bool:
            for index in range(source.count()):
                child = source.widget(index)
                if isinstance(child, TerminalPane):
                    continue
                if isinstance(child, QSplitter) and self.terminal_splitter_clone_supported(
                    child
                ):
                    continue
                return False
            return True

        def clone_terminal_splitter(self, source: QSplitter) -> QSplitter:
            clone = QSplitter(source.orientation())
            clone.setChildrenCollapsible(False)
            saved_layout_name = source.property("savedLayoutName")
            if isinstance(saved_layout_name, str) and saved_layout_name:
                clone.setProperty("savedLayoutName", saved_layout_name)
            for index in range(source.count()):
                child = source.widget(index)
                duplicate: QWidget
                if isinstance(child, TerminalPane):
                    duplicate = self.new_terminal_pane(child.plan, profile=child.profile)
                    self.remember_terminal_plan(child.plan, profile=child.profile)
                elif isinstance(child, QSplitter):
                    duplicate = self.clone_terminal_splitter(child)
                else:
                    raise RuntimeError(
                        "cannot duplicate split tab with unsupported child: "
                        f"{type(child).__name__}"
                    )
                clone.addWidget(duplicate)
                clone.setCollapsible(index, False)
                clone.setStretchFactor(index, 1)
            sizes = [max(1, int(size)) for size in source.sizes()]
            if len(sizes) == clone.count():
                clone.setSizes(sizes)
            return clone

        def bind_cloned_layout_persistence(self, root: QWidget) -> None:
            for widget in [root, *root.findChildren(QWidget)]:
                saved_layout_name = widget.property("savedLayoutName")
                if isinstance(saved_layout_name, str) and saved_layout_name:
                    self.bind_layout_resize_persistence(saved_layout_name, widget)

        def close_current_tab(self) -> None:
            index = self.tabs.currentIndex()
            if index >= 0:
                self.close_tab(index)

        def activate_previous_tab(self) -> None:
            self.activate_adjacent_tab(-1)

        def activate_next_tab(self) -> None:
            self.activate_adjacent_tab(1)

        def activate_adjacent_tab(self, step: int) -> None:
            count = self.tabs.count()
            if count <= 1:
                return
            current = self.tabs.currentIndex()
            for offset in range(1, count + 1):
                index = (current + step * offset) % count
                if self.tab_role(index) != "new-session":
                    self.tabs.setCurrentIndex(index)
                    return

        def close_other_tabs(self, keep_index: int) -> None:
            for index in range(self.tabs.count() - 1, -1, -1):
                if index == keep_index or self.tab_role(index) in {"home", "new-session"}:
                    continue
                self.close_tab(index)

        def recover_previous_sessions(self) -> None:
            if not self.recent_terminal_plans:
                self.log.append("RECOVER: no saved live session state")
                self.statusBar().showMessage("No previous session state to recover")
                return
            sessions = list(self.recent_terminal_plans[-3:])
            for plan, profile in sessions:
                if (
                    self.current_design_is_moba()
                    and profile is not None
                    and self.moba_connected_profile_supported(profile)
                ):
                    self.open_moba_connected_session_tab(
                        profile,
                        plan,
                        remote_path=self.moba_connected_remote_path_for_profile(profile),
                        tab_title=self.profile_tab_label(profile),
                        tab_status="recovered",
                    )
                else:
                    is_profile_terminal = (
                        profile is not None
                        and plan.source == f"profile:{profile.name}"
                    )
                    self.open_terminal_tab(
                        plan,
                        profile=profile,
                        tab_title=(
                            self.profile_tab_label(profile)
                            if profile is not None and is_profile_terminal
                            else plan.title
                        ),
                        tab_status="recovered",
                    )
            self.log.append(f"RECOVERED: {len(sessions)} recent session pane(s)")

        def create_layout(self) -> None:
            dialog = LayoutDialog(parent=self)
            while dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    layout = dialog.workspace_layout()
                    self.layout_store.add(layout)
                except ValueError as exc:
                    dialog.show_validation_error(str(exc))
                    continue
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT SAVED: {layout.name}")
                return

        def edit_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Information,
                    "Remote Ops Workspace",
                    "No saved layout selected.",
                )
                return
            try:
                current = self.layout_store.get(name)
            except KeyError as exc:
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Layout failed",
                    str(exc),
                )
                return
            dialog = LayoutDialog(current, self)
            while dialog.exec() == QDialog.DialogCode.Accepted:
                try:
                    layout = dialog.workspace_layout()
                    self.save_layout(layout, original_name=name)
                except (KeyError, ValueError) as exc:
                    dialog.show_validation_error(str(exc))
                    continue
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT UPDATED: {layout.name}")
                return

        def remove_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Information,
                    "Remote Ops Workspace",
                    "No saved layout selected.",
                )
                return
            answer = _literal_message_box(
                self,
                QMessageBox.Icon.Question,
                "Remove layout",
                f"Remove layout {name}?",
                buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                default_button=QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.layout_store.remove(name)
                self.refresh_layouts()
                self.log.append(f"LAYOUT REMOVED: {name}")
            except KeyError as exc:
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Layout failed",
                    str(exc),
                )

        def save_layout(self, layout: Layout, original_name: str) -> None:
            validate_layout(layout)
            layouts = self.layout_store.load()
            if layout.name != original_name and any(item.name == layout.name for item in layouts):
                raise ValueError(f"layout already exists: {layout.name}")
            layouts = [item for item in layouts if item.name != original_name]
            layouts.append(layout)
            self.layout_store.save(sorted(layouts, key=lambda item: item.name))
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
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Information,
                    "Remote Ops Workspace",
                    "No saved layout selected.",
                )
                return
            try:
                layout = self.layout_store.get(name)
                profiles = self.layout_launch_profiles(layout)
                plans = build_layout_terminal_plans(layout, self.store)
                widget = self.layout_widget(layout, plans, profiles)
                self.bind_layout_resize_persistence(layout.name, widget)
                for plan, profile in zip(plans, profiles, strict=True):
                    self.remember_terminal_plan(plan, profile=profile)
                self.add_workspace_tab(widget, layout.name, role="layout")
                self.log.append(f"LAYOUT: {layout.name} ({len(plans)} panes)")
                self.update_session_status()
            except (KeyError, LauncherError, ValueError) as exc:
                _literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Layout failed",
                    str(exc),
                )

        def layout_launch_profiles(self, layout: Layout) -> list[Profile]:
            profiles: list[Profile] = []
            for index, pane in enumerate(layout.panes, start=1):
                if pane.profile:
                    profile = self.store.get(pane.profile)
                else:
                    profile = Profile(
                        name=f"layout-{layout.name}-{index}",
                        protocol="custom",
                        command=pane.command,
                        group="layout",
                    )
                assert_profile_launch_allowed(profile, surface="gui")
                profiles.append(profile)
            return profiles

        def layout_widget(
            self,
            layout: Layout,
            plans: list[TerminalPanePlan],
            profiles: list[Profile],
        ) -> QWidget:
            if len(plans) == 1:
                return self.new_terminal_pane(plans[0], profile=profiles[0])
            if layout.orientation == "vertical":
                splitter = QSplitter(Qt.Orientation.Vertical)
                for plan, profile in zip(plans, profiles, strict=True):
                    splitter.addWidget(self.new_terminal_pane(plan, profile=profile))
                self.restore_layout_splitter_sizes(splitter, layout.splitter_sizes)
                return splitter
            if layout.orientation == "horizontal":
                splitter = QSplitter(Qt.Orientation.Horizontal)
                for plan, profile in zip(plans, profiles, strict=True):
                    splitter.addWidget(self.new_terminal_pane(plan, profile=profile))
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
                    row.addWidget(self.new_terminal_pane(plan, profile=profile))
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
            layouts = self.layout_store.load()
            for layout in layouts:
                if layout.name == name:
                    if layout.splitter_sizes == sizes:
                        return
                    layout.splitter_sizes = sizes
                    self.layout_store.save(layouts)
                    self.log.append(f"LAYOUT RESIZE SAVED: {name}")
                    return

        def new_terminal_pane(
            self,
            plan: TerminalPanePlan,
            *,
            profile: Profile | None = None,
            autostart: bool = True,
        ) -> TerminalPane:
            pane = TerminalPane(plan, profile=profile, autostart=autostart)
            pane.setProperty("terminalAutoCloseOnCleanExit", plan.source == "shell")
            pane.process.started.connect(self.update_session_status)
            pane.process.finished.connect(
                lambda exit_code, _exit_status, terminal_pane=pane: self.handle_terminal_process_finished(
                    terminal_pane,
                    exit_code,
                )
            )
            return pane

        def handle_terminal_process_finished(
            self,
            pane: TerminalPane,
            exit_code: int,
        ) -> None:
            self.update_session_status()
            try:
                auto_close = bool(pane.property("terminalAutoCloseOnCleanExit"))
                closing = bool(pane.property("terminalClosing"))
            except RuntimeError:
                return
            if exit_code != 0 or not auto_close or closing:
                return
            QTimer.singleShot(
                0,
                lambda terminal_pane=pane: self.close_finished_shell_tab(
                    terminal_pane
                ),
            )

        def close_finished_shell_tab(self, pane: TerminalPane) -> None:
            """Close a standalone shell tab after its shell exits successfully."""

            try:
                if pane.is_running() or bool(pane.property("terminalClosing")):
                    return
                index = self.tabs.indexOf(pane)
            except RuntimeError:
                return
            if index >= 0 and self.tab_role(index) == "terminal":
                self.close_tab(index)

        def close_tab(self, index: int) -> None:
            widget = self.tabs.widget(index)
            if widget is None:
                return
            role = self.tab_role(index)
            if role == "home":
                self.tabs.setCurrentIndex(index)
                self.statusBar().showMessage("Home tab stays open")
                return
            if role == "new-session":
                self.open_local_terminal_tab()
                return
            running = [pane for pane in self.terminal_panes_in(widget) if pane.is_running()]
            if running and not self.confirm_stop_processes("Close tab", len(running)):
                return
            title = self.tabs.tabText(index)
            self.tabs.removeTab(index)
            if running:
                self._closing_tab_widgets.append(widget)
                for pane in running:
                    pane.prepare_for_close()
                    pane.process.finished.connect(
                        lambda *_args, closing_widget=widget: self.finish_closing_tab(
                            closing_widget
                        )
                    )
                self.stop_terminal_panes(running)
                self.finish_closing_tab(widget)
            else:
                widget.deleteLater()
            self.log.append(f"TAB CLOSED: {title}")
            if self.current_design_is_moba() and self.find_tab_by_role("home") < 0:
                self.add_welcome_tab()
            self.refresh_special_tab_buttons()
            self.refresh_moba_left_dock_for_current_tab()
            self.update_session_status()

        def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]:
            panes: list[TerminalPane] = []
            if isinstance(widget, TerminalPane):
                panes.append(widget)
            panes.extend(widget.findChildren(TerminalPane))
            return panes

        def all_terminal_panes(self) -> list[TerminalPane]:
            panes: list[TerminalPane] = []
            seen: set[int] = set()
            try:
                for index in range(self.tabs.count()):
                    widget = self.tabs.widget(index)
                    if widget is None:
                        continue
                    for pane in self.terminal_panes_in(widget):
                        key = id(pane)
                        if key in seen:
                            continue
                        seen.add(key)
                        panes.append(pane)
            except RuntimeError:
                # A QProcess may emit finished while Qt is deleting the main window's tabs.
                return []
            return panes

        def running_terminal_panes(self) -> list[TerminalPane]:
            return [pane for pane in self.all_terminal_panes() if pane.is_running()]

        def stop_terminal_panes(self, panes: list[TerminalPane]) -> None:
            requested = 0
            for pane in panes:
                if pane.request_stop(policy=self.CLOSE_STOP_POLICY):
                    requested += 1
            if requested:
                self.log.append(f"STOP REQUESTED: {requested} process pane(s)")

        def finish_closing_tab(self, widget: QWidget) -> None:
            if widget not in self._closing_tab_widgets:
                return
            if any(pane.is_running() for pane in self.terminal_panes_in(widget)):
                return
            self._closing_tab_widgets.remove(widget)
            widget.deleteLater()

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

        def update_session_status(self) -> None:
            try:
                running = len(self.running_terminal_panes())
                if running:
                    self.statusBar().showMessage(f"Running process panes: {running}")
                else:
                    self.statusBar().showMessage("No running process panes")
            except RuntimeError:
                # Ignore late process signals after Qt has disposed of the window.
                return

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
    application_font = app.font()
    application_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(application_font)
    icon = QIcon(str(application_icon_path()))
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if show:
        window.show()
    return app, window


def main() -> int:
    try:
        app, _window = create_main_window(sys.argv, show=True)
    except GuiDependencyError as exc:
        print(str(exc))
        if exc.__cause__ is not None:
            print(exc.__cause__)
        return 2
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
