from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from .doctor import run_doctor
from .file_transfer import build_sftp_queue_plan, parse_transfer_item_spec, preview_local_path
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
    profile_from_editor_data,
    profile_to_editor_data,
)
from .gui_lifecycle import ProcessStopPolicy, ProcessStopResult, stop_process
from .launcher import LauncherError, build_launch_plan
from .layouts import Layout, LayoutStore, build_layout_terminal_plans
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
    moba_connected_window_title,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
    moba_telemetry_cells,
)
from .models import Profile
from .storage import ProfileStore
from .terminal import (
    TerminalPanePlan,
    default_shell_plan,
    split_shell_plans,
    terminal_plan_for_profile,
    terminal_plan_for_sftp_browser,
)


class GuiDependencyError(RuntimeError):
    pass


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


def create_main_window(argv: list[str] | None = None, *, show: bool = False):
    try:
        from PyQt6.QtCore import QPoint, QProcess, QSize, Qt
        from PyQt6.QtGui import (
            QBrush,
            QColor,
            QFont,
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
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSizePolicy,
            QSplitter,
            QStackedWidget,
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

        def __init__(self, plan: TerminalPanePlan) -> None:
            super().__init__()
            self.setObjectName("terminalPane")
            self.plan = plan
            self.process = QProcess(self)
            self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

            self.title = QLabel(plan.title)
            self.title.setObjectName("terminalTitle")
            self.source = QLabel(plan.source)
            self.source.setObjectName("terminalSource")
            self.status = QLabel("ready")
            self.status.setObjectName("paneStatus")
            self.command_preview = QLabel(plan.printable())
            self.command_preview.setObjectName("terminalCommand")
            self.command_preview.setToolTip(plan.printable())
            self.command_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.output = QTextEdit()
            self.output.setObjectName("terminalOutput")
            self.output.setReadOnly(True)
            self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.input = QLineEdit()
            self.input.setObjectName("terminalInput")
            self.input.setPlaceholderText("stdin, shell command or interactive input")
            self.start_button = self.terminal_button("Start", "SP_MediaPlay", "Start process")
            self.restart_button = self.terminal_button("Restart", "SP_BrowserReload", "Restart process")
            self.stop_button = self.terminal_button("Stop", "SP_MediaStop", "Stop process")
            self.copy_button = self.terminal_button("Copy", "SP_DialogSaveButton", "Copy launch command")
            self.clear_button = self.terminal_button("Clear", "SP_DialogResetButton", "Clear terminal output")

            self.header = QFrame()
            self.header.setObjectName("terminalHeader")
            header_layout = QHBoxLayout(self.header)
            header_layout.setContentsMargins(8, 6, 8, 6)
            header_layout.setSpacing(8)
            header_layout.addWidget(self.title)
            header_layout.addWidget(self.source)
            header_layout.addWidget(self.status)
            header_layout.addStretch(1)
            for button in [
                self.start_button,
                self.restart_button,
                self.stop_button,
                self.copy_button,
                self.clear_button,
            ]:
                header_layout.addWidget(button)

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
            self.stop_button.clicked.connect(self.stop)
            self.copy_button.clicked.connect(self.copy_command)
            self.clear_button.clicked.connect(self.clear_output)
            self.input.returnPressed.connect(self.send_input)
            self.process.readyReadStandardOutput.connect(self.read_stdout)
            self.process.readyReadStandardError.connect(self.read_stderr)
            self.process.started.connect(self.on_started)
            self.process.errorOccurred.connect(self.on_error)
            self.process.finished.connect(self.on_finished)
            self.set_status("ready", "ready")
            self.update_process_actions()
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
            button.setIcon(self.style().standardIcon(icon))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            return button

        def is_running(self) -> bool:
            return self.process.state() != QProcess.ProcessState.NotRunning

        def start(self) -> None:
            if self.is_running():
                return
            if not self.plan.command:
                self.append_text("[error] empty terminal command\n")
                return
            self.output.clear()
            self.set_status("starting", "starting")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.input.setEnabled(False)
            self.append_text(f"$ {self.plan.printable()}\n")
            for note in self.plan.notes:
                self.append_text(f"[note] {note}\n")
            self.process.setProgram(self.plan.command[0])
            self.process.setArguments(self.plan.command[1:])
            self.process.start()
            self.update_process_actions()

        def restart(self) -> None:
            if self.is_running():
                self.stop()
            self.start()

        def stop(self, policy: ProcessStopPolicy | None = None) -> ProcessStopResult:
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
            QApplication.clipboard().setText(self.plan.printable())
            self.append_text("\n[command copied]\n")

        def clear_output(self) -> None:
            self.output.clear()
            self.append_text(f"$ {self.plan.printable()}\n")

        def send_input(self) -> None:
            line = self.input.text()
            self.input.clear()
            if not self.is_running():
                self.append_text("[stdin ignored: process is not running]\n")
                return
            self.process.write((line + "\n").encode("utf-8"))

        def read_stdout(self) -> None:
            self.append_text(bytes(self.process.readAllStandardOutput()).decode(errors="replace"))

        def read_stderr(self) -> None:
            self.append_text(bytes(self.process.readAllStandardError()).decode(errors="replace"))

        def append_text(self, text: str) -> None:
            if not text:
                return
            self.output.moveCursor(QTextCursor.MoveOperation.End)
            self.output.insertPlainText(text)
            self.output.moveCursor(QTextCursor.MoveOperation.End)

        def on_started(self) -> None:
            self.set_status("running", "running")
            self.update_process_actions()

        def on_error(self, error) -> None:
            self.set_status("error", "error")
            self.append_text(f"\n[error] {error.name}\n")
            self.update_process_actions()

        def on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
            state = "ready" if exit_code == 0 else "error"
            self.set_status(f"exited {exit_code}", state)
            self.append_text(f"\n[process exited: {exit_code}, {exit_status.name}]\n")
            self.update_process_actions()

        def set_status(self, text: str, state: str) -> None:
            self.status.setText(text)
            self.status.setProperty("state", state)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
            self.status.update()

        def update_process_actions(self) -> None:
            running = self.is_running()
            self.start_button.setEnabled(not running)
            self.restart_button.setEnabled(bool(self.plan.command))
            self.stop_button.setEnabled(running)
            self.input.setEnabled(running)

    class MobaSftpDock(QFrame):
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

        def __init__(self, state: MobaConnectedSessionState) -> None:
            super().__init__()
            self.setObjectName("mobaConnectedLeftDock")
            self.state = state
            frame = gui_design_moba_connected_dock_frame()
            density = gui_design_moba_sftp_dock_layout()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            routed_rows = gui_design_moba_sftp_routed_file_rows()
            self.apply_connected_dock_frame_properties(self)
            self.apply_connected_session_route_properties(self)
            self.setMinimumWidth(frame.dock_width)
            self.setMinimumHeight(frame.dock_height)

            outer_layout = QVBoxLayout(self)
            outer_layout.setContentsMargins(0, 0, 0, 0)
            outer_layout.setSpacing(0)
            browser = QFrame()
            browser.setObjectName("mobaSftpBrowser")
            browser.setMinimumWidth(frame.dock_width)
            browser.setMinimumHeight(frame.dock_height)
            self.browser = browser
            self.apply_connected_dock_frame_properties(browser)
            self.apply_connected_session_route_properties(browser)
            self.apply_sftp_dock_density_properties(browser, density)
            self.apply_sftp_follow_folder_route_properties(browser, follow_route)
            self.apply_sftp_terminal_folder_route_properties(browser)
            outer_layout.addWidget(browser)

            layout = QVBoxLayout(browser)
            layout.setContentsMargins(
                density.inner_margin,
                density.inner_margin,
                density.inner_margin,
                density.inner_margin,
            )
            layout.setSpacing(0)

            toolbar = QFrame()
            toolbar.setObjectName("mobaSftpToolbar")
            toolbar.setProperty("mobaSftpToolbarHeight", density.toolbar_height)
            toolbar.setFixedHeight(density.toolbar_height)
            toolbar_geometry = gui_design_moba_sftp_toolbar_action_geometry()
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(
                toolbar_geometry[0].button_x,
                toolbar_geometry[0].button_y,
                0,
                toolbar_geometry[0].button_y,
            )
            toolbar_layout.setSpacing(0)
            for action in gui_design_moba_sftp_dock_actions():
                toolbar_layout.addWidget(self.tool_button(action, density))
                if action.separator_after:
                    toolbar_layout.addWidget(self.toolbar_separator(action, density))
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            chrome = gui_design_moba_sftp_browser_chrome()
            path = QLineEdit()
            path.setObjectName("mobaSftpPath")
            path.setText(self.state.remote_path)
            path.setPlaceholderText(chrome.path_placeholder)
            path.setProperty("mobaSftpPathDropdownMarker", chrome.dropdown_marker)
            path.setProperty("mobaSftpPathHeight", density.path_height)
            path.setProperty("mobaSftpPathTextX", chrome.path_text_x)
            path.setProperty("mobaSftpPathTextY", chrome.path_text_y)
            path.setProperty("mobaSftpPathFontSize", chrome.path_font_size)
            path.setProperty("mobaSftpDropdownRightOffset", chrome.dropdown_right_offset)
            path.setProperty("mobaSftpDropdownY", chrome.dropdown_y)
            path.setProperty("mobaSftpDropdownFontSize", chrome.dropdown_font_size)
            self.apply_sftp_follow_folder_route_properties(path, follow_route)
            self.apply_sftp_terminal_folder_route_properties(path)
            self.apply_connected_session_route_properties(path)
            path.setFixedHeight(density.path_height)
            path.setToolTip(self.state.follow_folder_plan.printable_batch())
            layout.addSpacing(density.path_gap)
            layout.addWidget(path)

            self.file_table = QTreeWidget()
            self.file_table.setObjectName("mobaSftpFileTable")
            self.file_table.setColumnCount(len(chrome.columns))
            self.file_table.setHeaderLabels([column.label for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnKeys", [column.key for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnLabels", [column.label for column in chrome.columns])
            self.file_table.setProperty("mobaSftpColumnWidths", [column.static_width for column in chrome.columns])
            self.file_table.setProperty("mobaSftpParentRowLabel", chrome.parent_row_label)
            self.file_table.setProperty("mobaSftpParentRowKind", chrome.parent_row_kind)
            self.file_table.setProperty("mobaSftpSelectedRowKind", chrome.selected_row_kind)
            self.file_table.setProperty("mobaSftpHeaderHeight", density.table_header_height)
            self.file_table.setProperty("mobaSftpHeaderLabelY", chrome.header_label_y)
            self.file_table.setProperty("mobaSftpHeaderFontSize", chrome.header_font_size)
            self.file_table.setProperty("mobaSftpRowHeight", density.file_row_height)
            self.file_table.setProperty("mobaSftpRowTopOffset", chrome.row_top_offset)
            self.file_table.setProperty("mobaSftpRowIconX", chrome.row_icon_x)
            self.file_table.setProperty("mobaSftpRowIconYOffset", chrome.row_icon_y_offset)
            self.file_table.setProperty("mobaSftpRowNameX", chrome.row_name_x)
            self.file_table.setProperty("mobaSftpRowSizeX", chrome.row_size_x)
            self.file_table.setProperty("mobaSftpRowModifiedX", chrome.row_modified_x)
            self.file_table.setProperty("mobaSftpRowTextYOffset", chrome.row_text_y_offset)
            self.file_table.setProperty("mobaSftpRowTextFontSize", chrome.row_text_font_size)
            self.file_table.setProperty("mobaSftpRowModifiedFontSize", chrome.row_modified_font_size)
            self.file_table.setProperty(
                "mobaSftpFileRowIconKinds",
                [row_icon.kind for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
            self.file_table.setProperty(
                "mobaSftpFileRowIconKeys",
                [row_icon.icon_key for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
            self.apply_sftp_follow_folder_route_properties(self.file_table, follow_route)
            self.apply_sftp_routed_file_rows_properties(self.file_table, routed_rows, follow_route)
            self.apply_sftp_terminal_folder_route_properties(self.file_table)
            self.apply_connected_session_route_properties(self.file_table)
            self.file_table.setIconSize(QSize(density.toolbar_icon_size, density.toolbar_icon_size))
            self.file_table.setRootIsDecorated(False)
            self.file_table.setUniformRowHeights(True)
            self.file_table.setSortingEnabled(False)
            self.file_table.header().setFixedHeight(density.table_header_height)
            self.file_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.file_table.header().setStretchLastSection(False)
            for column_index, column in enumerate(chrome.columns):
                self.file_table.setColumnWidth(column_index, column.static_width)
            parent_item = QTreeWidgetItem([chrome.parent_row_label, "", ""])
            self.apply_sftp_file_row_icon(parent_item, chrome.parent_row_kind)
            self.apply_sftp_routed_file_row_metadata(
                parent_item,
                routed_rows,
                row_index=0,
                name=chrome.parent_row_label,
                selected=True,
            )
            parent_item.setSizeHint(0, QSize(0, density.file_row_height))
            parent_item.setToolTip(0, "parent directory")
            self.file_table.addTopLevelItem(parent_item)
            for row_index, entry in enumerate(self.state.file_entries, start=1):
                item = QTreeWidgetItem([entry.name, str(entry.size_kb), entry.modified])
                self.apply_sftp_file_row_icon(item, entry.kind)
                self.apply_sftp_routed_file_row_metadata(
                    item,
                    routed_rows,
                    row_index=row_index,
                    name=entry.name,
                    selected=False,
                )
                item.setSizeHint(0, QSize(0, density.file_row_height))
                item.setToolTip(0, f"{entry.kind}: {entry.name}")
                self.file_table.addTopLevelItem(item)
            parent_item.setSelected(True)
            self.file_table.setCurrentItem(parent_item)
            layout.addSpacing(density.table_header_gap)
            layout.addWidget(self.file_table, 1)

            layout.addWidget(self.build_remote_monitoring(density))

        def apply_sftp_file_row_icon(self, item: QTreeWidgetItem, kind: str) -> None:
            row_icon = gui_design_moba_sftp_file_row_icon(kind)
            item.setData(0, Qt.ItemDataRole.UserRole, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_KEY_ROLE, row_icon.icon_key)
            item.setData(0, SFTP_ROW_KIND_ROLE, row_icon.row_kind)
            item.setData(0, SFTP_ROW_ICON_SIZE_ROLE, row_icon.static_size)
            item.setData(0, SFTP_ROW_ICON_RENDER_ROLE, row_icon.render_source)
            item.setIcon(0, self.sftp_file_row_icon(row_icon.icon_key, size=row_icon.static_size))

        def apply_sftp_routed_file_row_metadata(self, item: QTreeWidgetItem, rows, *, row_index: int, name: str, selected: bool) -> None:
            item.setData(0, SFTP_ROW_CONTRACT_KEY_ROLE, rows.key)
            item.setData(0, SFTP_ROW_ROUTE_KEY_ROLE, rows.follow_route_key)
            item.setData(0, SFTP_ROW_SOURCE_PATH_ROLE, self.state.remote_path)
            item.setData(0, SFTP_ROW_INDEX_ROLE, row_index)
            item.setData(0, SFTP_ROW_SELECTED_BY_ROUTE_ROLE, selected)
            item.setData(0, SFTP_ROW_TERMINAL_FOLDER_ROUTE_KEY_ROLE, moba_sftp_terminal_folder_route(self.state).key)
            item.setToolTip(1, f"{rows.row_path_property}: {self.state.remote_path}")
            item.setToolTip(2, f"{rows.row_route_property}: {rows.follow_route_key}")
            if item.text(0) != name:
                item.setText(0, name)

        def sftp_file_row_icon(self, icon_key: str, *, size: int) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_sftp_file_row_icon(painter, icon_key, size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_sftp_file_row_icon(self, painter: QPainter, icon_key: str, size: int) -> None:
            outline = QColor("#343a40")
            folder = QColor("#f2c744")
            parent_folder = QColor("#f5d96a")
            file_fill = QColor("#d7dde5")
            folded = QColor("#eef2f7")
            muted = QColor("#6b7280")
            if icon_key in {"folder", "folder-up"}:
                painter.setPen(QPen(outline, 1))
                painter.setBrush(QBrush(parent_folder if icon_key == "folder-up" else folder))
                painter.drawRect(0, 4, size - 1, size - 5)
                painter.setBrush(QBrush(QColor("#ffe58a")))
                painter.drawRect(2, 2, max(6, size // 2), 3)
                if icon_key == "folder-up":
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(QColor("#2f6fb1")))
                    mid = size // 2
                    painter.drawPolygon(QPoint(mid, 4), QPoint(mid - 3, 8), QPoint(mid + 3, 8))
                return
            painter.setPen(QPen(outline, 1))
            painter.setBrush(QBrush(file_fill))
            painter.drawRect(2, 1, size - 3, size - 2)
            painter.setBrush(QBrush(folded))
            painter.drawPolygon(QPoint(size - 5, 1), QPoint(size - 1, 5), QPoint(size - 5, 5))
            painter.setPen(QPen(muted, 1))
            painter.drawLine(4, 7, size - 4, 7)
            painter.drawLine(4, 10, size - 5, 10)

        def build_remote_monitoring(self, density) -> QFrame:
            chrome = gui_design_moba_remote_monitoring_dock_chrome()
            route = gui_design_moba_monitoring_telemetry_route()
            control_route = gui_design_moba_remote_monitoring_control_route()
            follow_control_route = gui_design_moba_follow_terminal_folder_control_route()
            follow_route = gui_design_moba_sftp_follow_folder_route()
            metric_keys = [metric.key for metric in gui_design_moba_monitoring_metrics()]
            panel = QFrame()
            panel.setObjectName("mobaRemoteMonitoring")
            panel.setProperty("mobaSftpMonitoringHeight", density.monitoring_height)
            panel.setProperty("mobaSftpMonitoringDividerOffset", density.monitoring_divider_offset)
            panel.setProperty("mobaSftpMonitoringMetricRowGap", density.monitoring_metric_row_gap)
            panel.setProperty("mobaRemoteMonitoringCompact", chrome.compact)
            panel.setProperty("mobaRemoteMonitoringTelemetrySurface", chrome.telemetry_surface)
            panel.setProperty("mobaRemoteMonitoringMetricKeys", metric_keys)
            panel.setProperty("mobaRemoteMonitoringVisibleMetricKeys", list(chrome.visible_metric_keys))
            panel.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            panel.setProperty("mobaMonitoringTelemetryRouteRole", route.route_role)
            panel.setProperty("mobaMonitoringTelemetryTargetBarObject", route.target_bar_object)
            panel.setProperty("mobaMonitoringTelemetryTargetCellObject", route.target_cell_object)
            panel.setProperty("mobaMonitoringTelemetryMetricCellKeys", list(route.target_metric_cell_keys))
            panel.setProperty("mobaMonitoringTelemetryIdentityCellKey", route.target_identity_cell_key)
            panel.setProperty("mobaRemoteMonitoringRefreshSeconds", chrome.refresh_seconds)
            panel.setProperty("mobaRemoteMonitoringStaticHeight", chrome.static_height)
            panel.setProperty("mobaRemoteMonitoringDividerOffset", chrome.divider_offset)
            panel.setProperty("mobaRemoteMonitoringDividerLeftInset", chrome.divider_left_inset)
            panel.setProperty("mobaRemoteMonitoringDividerRightInset", chrome.divider_right_inset)
            panel.setProperty("mobaRemoteMonitoringContentLeft", chrome.content_left)
            panel.setProperty("mobaRemoteMonitoringIconCenterX", chrome.icon_center_x)
            panel.setProperty("mobaRemoteMonitoringMetricRowGap", chrome.metric_row_gap)
            panel.setProperty("mobaRemoteMonitoringLiveControlsWidth", chrome.live_controls_width)
            panel.setProperty("mobaRemoteMonitoringCommand", self.state.monitoring_plan.printable())
            panel.setProperty("mobaRemoteMonitoringFollowPlan", self.state.follow_folder_plan.printable_batch())
            self.apply_remote_monitoring_control_route_properties(panel, control_route)
            panel.setProperty(control_route.captured_property, True)
            panel.setProperty(control_route.captured_checked_property, control_route.expected_checked)
            panel.setProperty(control_route.captured_command_property, self.state.monitoring_plan.printable())
            panel.setProperty(control_route.captured_refresh_seconds_property, chrome.refresh_seconds)
            follow_plan = self.state.follow_folder_plan.printable_batch()
            self.apply_follow_terminal_folder_control_route_properties(panel, follow_control_route)
            panel.setProperty(follow_control_route.captured_property, True)
            panel.setProperty(follow_control_route.captured_checked_property, self.state.follow_terminal_folder)
            panel.setProperty(follow_control_route.captured_path_property, self.state.remote_path)
            panel.setProperty(follow_control_route.captured_plan_property, follow_plan)
            self.apply_sftp_follow_folder_route_properties(panel, follow_route)
            self.apply_sftp_terminal_folder_route_properties(panel)
            panel.setProperty(
                "mobaMonitoringControlGeometryKeys",
                [geometry.key for geometry in gui_design_moba_monitoring_control_geometry()],
            )
            panel.setFixedHeight(chrome.static_height)
            controls = QFrame(panel)
            controls.setObjectName("mobaMonitoringControls")
            controls.setGeometry(0, 0, chrome.live_controls_width, chrome.static_height)
            controls.setProperty("mobaRemoteMonitoringLiveControlsWidth", chrome.live_controls_width)
            controls.setProperty("mobaRemoteMonitoringStaticHeight", chrome.static_height)
            controls.setProperty(
                "mobaMonitoringControlGeometryKeys",
                [geometry.key for geometry in gui_design_moba_monitoring_control_geometry()],
            )
            for control in gui_design_moba_monitoring_controls():
                widget = self.monitoring_control_widget(control)
                geometry = gui_design_moba_monitoring_control_geometry_for(control.key)
                widget.setParent(controls)
                widget.setGeometry(
                    geometry.anchor_x,
                    geometry.static_y,
                    geometry.live_width,
                    max(geometry.row_height + 4, geometry.icon_size + 4),
                )
            for metric in gui_design_moba_monitoring_metrics():
                label = QLabel(self.monitoring_metric_text(metric), panel)
                label.setObjectName("mobaMonitoringMetric")
                label.setProperty("mobaMonitoringMetricKey", metric.key)
                label.setProperty("mobaMonitoringMetricVisibleInDock", metric.key in chrome.visible_metric_keys)
                label.setProperty("mobaMonitoringMetricTelemetrySurface", chrome.telemetry_surface)
                label.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
                label.setVisible(False)
            return panel

        @staticmethod
        def apply_remote_monitoring_control_route_properties(widget, route) -> None:
            properties = {
                "mobaRemoteMonitoringControlRouteKey": route.key,
                "mobaRemoteMonitoringControlRouteRole": route.route_role,
                "mobaRemoteMonitoringControlSourcePanelObject": route.source_panel_object,
                "mobaRemoteMonitoringControlSourceObject": route.source_control_object,
                "mobaRemoteMonitoringControlSourceKey": route.source_control_key,
                "mobaRemoteMonitoringControlSourceLabel": route.source_control_label,
                "mobaRemoteMonitoringControlSourceType": route.source_control_type,
                "mobaRemoteMonitoringControlExpectedChecked": route.expected_checked,
                "mobaRemoteMonitoringControlCommandProperty": route.command_property,
                "mobaRemoteMonitoringControlRefreshProperty": route.refresh_seconds_property,
                "mobaRemoteMonitoringControlCheckedProperty": route.checked_property,
                "mobaRemoteMonitoringControlTelemetryRouteKey": route.telemetry_route_key,
                "mobaRemoteMonitoringControlTelemetrySurface": route.telemetry_surface,
                "mobaRemoteMonitoringControlTargetBarObject": route.target_bar_object,
                "mobaRemoteMonitoringControlTargetMetricCellKeys": list(route.target_metric_cell_keys),
                "mobaRemoteMonitoringControlCapturedProperty": route.captured_property,
                "mobaRemoteMonitoringControlCapturedCheckedProperty": route.captured_checked_property,
                "mobaRemoteMonitoringControlCapturedCommandProperty": route.captured_command_property,
                "mobaRemoteMonitoringControlCapturedRefreshProperty": route.captured_refresh_seconds_property,
                "mobaRemoteMonitoringControlRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_follow_terminal_folder_control_route_properties(widget, route) -> None:
            properties = {
                "mobaFollowTerminalFolderControlRouteKey": route.key,
                "mobaFollowTerminalFolderControlRouteRole": route.route_role,
                "mobaFollowTerminalFolderControlSourcePanelObject": route.source_panel_object,
                "mobaFollowTerminalFolderControlSourceObject": route.source_control_object,
                "mobaFollowTerminalFolderControlSourceKey": route.source_control_key,
                "mobaFollowTerminalFolderControlSourceLabel": route.source_control_label,
                "mobaFollowTerminalFolderControlSourceType": route.source_control_type,
                "mobaFollowTerminalFolderControlExpectedChecked": route.expected_checked,
                "mobaFollowTerminalFolderControlSourcePathProperty": route.source_path_property,
                "mobaFollowTerminalFolderControlSourcePlanProperty": route.source_plan_property,
                "mobaFollowTerminalFolderControlSourceEnabledProperty": route.source_enabled_property,
                "mobaFollowTerminalFolderControlTargetBrowserObject": route.target_browser_object,
                "mobaFollowTerminalFolderControlTargetPathObject": route.target_path_object,
                "mobaFollowTerminalFolderControlTargetTableObject": route.target_table_object,
                "mobaFollowTerminalFolderControlTargetPathProperty": route.target_path_property,
                "mobaFollowTerminalFolderControlTargetPlanProperty": route.target_plan_property,
                "mobaFollowTerminalFolderControlTargetEnabledProperty": route.target_enabled_property,
                "mobaFollowTerminalFolderControlCapturedProperty": route.captured_property,
                "mobaFollowTerminalFolderControlCapturedCheckedProperty": route.captured_checked_property,
                "mobaFollowTerminalFolderControlCapturedPathProperty": route.captured_path_property,
                "mobaFollowTerminalFolderControlCapturedPlanProperty": route.captured_plan_property,
                "mobaFollowTerminalFolderControlRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def monitoring_control_widget(self, control):
            if control.control_type == "checkbox":
                widget = QCheckBox(control.label)
                widget.setObjectName("mobaFollowTerminalFolder")
            else:
                widget = QToolButton()
                widget.setObjectName("mobaMonitoringControl")
                widget.setText(control.label)
                widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                widget.setAutoRaise(True)
            widget.setProperty("mobaMonitoringControlKey", control.key)
            widget.setProperty("mobaMonitoringControlIconKey", control.icon_key)
            widget.setProperty("mobaMonitoringControlType", control.control_type)
            widget.setProperty("mobaMonitoringControlDefaultChecked", control.checked)
            route = gui_design_moba_monitoring_telemetry_route()
            widget.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            widget.setProperty("mobaMonitoringTelemetrySurface", route.telemetry_surface)
            geometry = gui_design_moba_monitoring_control_geometry_for(control.key)
            widget.setProperty("mobaMonitoringControlStaticX", geometry.anchor_x)
            widget.setProperty("mobaMonitoringControlStaticY", geometry.static_y)
            widget.setProperty("mobaMonitoringControlIconX", geometry.icon_x)
            widget.setProperty("mobaMonitoringControlIconSize", geometry.icon_size)
            widget.setProperty("mobaMonitoringControlLabelX", geometry.label_x)
            widget.setProperty("mobaMonitoringControlLabelYOffset", geometry.label_y_offset)
            widget.setProperty("mobaMonitoringControlLabelFontSize", geometry.label_font_size)
            widget.setProperty("mobaMonitoringControlLabelBold", geometry.label_bold)
            widget.setProperty("mobaMonitoringControlCheckSize", geometry.check_size)
            widget.setProperty("mobaMonitoringControlCheckYOffset", geometry.check_y_offset)
            widget.setProperty("mobaMonitoringControlCheckmarkPoints", [list(point) for point in geometry.checkmark_points])
            widget.setProperty("mobaMonitoringControlRowHeight", geometry.row_height)
            widget.setProperty("mobaMonitoringControlLiveWidth", geometry.live_width)
            control_font = QFont()
            control_font.setPointSize(geometry.label_font_size)
            control_font.setBold(geometry.label_bold)
            widget.setFont(control_font)
            widget.setCheckable(True)
            widget.setChecked(self.monitoring_control_checked(control))
            widget.setToolTip(self.monitoring_control_tooltip(control))
            widget.setIcon(self.monitoring_control_icon(control.icon_key))
            widget.setIconSize(QSize(geometry.icon_size, geometry.icon_size))
            widget.setMinimumHeight(geometry.row_height)
            if control.key == "remote-monitoring":
                control_route = gui_design_moba_remote_monitoring_control_route()
                self.apply_remote_monitoring_control_route_properties(widget, control_route)
                widget.setProperty(control_route.checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_property, True)
                widget.setProperty(control_route.captured_checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_command_property, self.state.monitoring_plan.printable())
                widget.setProperty(
                    control_route.captured_refresh_seconds_property,
                    gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds,
                )
                widget.setProperty("mobaMonitoringCommand", self.state.monitoring_plan.printable())
                widget.setProperty(
                    "mobaMonitoringRefreshSeconds",
                    gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds,
                )
            if control.key == "follow-terminal-folder":
                control_route = gui_design_moba_follow_terminal_folder_control_route()
                follow_route = gui_design_moba_sftp_follow_folder_route()
                follow_plan = self.state.follow_folder_plan.printable_batch()
                self.apply_follow_terminal_folder_control_route_properties(widget, control_route)
                widget.setProperty("mobaMonitoringFollowPlan", follow_plan)
                widget.setProperty("mobaMonitoringFollowPath", self.state.remote_path)
                widget.setProperty("mobaMonitoringFollowEnabled", self.state.follow_terminal_folder)
                widget.setProperty(control_route.captured_property, True)
                widget.setProperty(control_route.captured_checked_property, widget.isChecked())
                widget.setProperty(control_route.captured_path_property, self.state.remote_path)
                widget.setProperty(control_route.captured_plan_property, follow_plan)
                self.apply_sftp_follow_folder_route_properties(widget, follow_route)
                self.apply_sftp_terminal_folder_route_properties(widget)
            return widget

        def monitoring_control_checked(self, control) -> bool:
            if control.key == "follow-terminal-folder":
                return self.state.follow_terminal_folder
            return bool(control.checked)

        def monitoring_control_tooltip(self, control) -> str:
            if control.key == "follow-terminal-folder":
                return f"{control.tooltip}\n{self.state.follow_folder_plan.printable_batch()}"
            if control.key == "remote-monitoring":
                return f"{control.tooltip}\n{self.state.monitoring_plan.printable()}"
            return control.tooltip

        def monitoring_metric_text(self, metric) -> str:
            monitoring = self.state.monitoring
            if metric.source == "cpu_percent":
                value = f"{monitoring.cpu_percent}%"
            elif metric.source == "memory_label":
                value = monitoring.memory_label
            elif metric.source == "disk_label":
                value = monitoring.disk_label
            elif metric.source == "network_pair":
                value = f"{monitoring.net_up_mbps:.2f}/{monitoring.net_down_mbps:.2f} Mb/s"
            elif metric.source == "load_average":
                value = monitoring.load_average
            elif metric.source == "process_count":
                value = str(monitoring.process_count)
            else:
                value = ""
            return f"{metric.label} {value}".strip()

        def tool_button(self, action, density) -> QToolButton:
            geometry = gui_design_moba_sftp_toolbar_action_geometry_for(action.key)
            button = QToolButton()
            button.setObjectName("mobaSftpAction")
            button.setProperty("mobaSftpActionKey", action.key)
            button.setProperty("mobaSftpIconKey", action.icon_key)
            button.setProperty("mobaSftpActionGroupKey", action.group_key)
            button.setProperty("mobaSftpActionSeparatorAfter", action.separator_after)
            button.setProperty("mobaSftpActionStaticX", geometry.button_x)
            button.setProperty("mobaSftpActionStaticY", geometry.button_y)
            button.setProperty("mobaSftpActionButtonSize", geometry.button_size)
            button.setProperty("mobaSftpActionIconX", geometry.icon_x)
            button.setProperty("mobaSftpActionIconY", geometry.icon_y)
            button.setProperty("mobaSftpActionIconSize", geometry.icon_size)
            button.setProperty("mobaSftpActionSeparatorX", geometry.separator_x)
            button.setText(action.label)
            button.setToolTip(action.tooltip)
            button.setIcon(self.sftp_action_icon(action.icon_key, action.color, size=geometry.icon_size))
            button.setIconSize(QSize(geometry.icon_size, geometry.icon_size))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(geometry.button_size, geometry.button_size))
            return button

        def toolbar_separator(self, action, density) -> QFrame:
            separator = QFrame()
            separator.setObjectName("mobaSftpToolbarSeparator")
            separator.setProperty("mobaSftpSeparatorAfterActionKey", action.key)
            separator.setProperty("mobaSftpSeparatorGroupKey", action.group_key)
            separator.setProperty("mobaSftpSeparatorWidth", density.toolbar_separator_width)
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            separator.setFixedWidth(density.toolbar_separator_width)
            return separator

        def sftp_action_icon(self, icon_key: str, fill: str, *, size: int = 20) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_sftp_action_icon(painter, icon_key, QColor(fill), size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_sftp_action_icon(self, painter: QPainter, icon_key: str, fill: QColor, size: int) -> None:
            white = QColor("#ffffff")
            dark = QColor("#101010")
            yellow = QColor("#ffd866")
            blue = QColor("#2f6fb1")
            mid = size // 2

            def pen(color: QColor, width: int = 1) -> None:
                painter.setPen(QPen(color, width))

            def brush(color: QColor) -> None:
                painter.setBrush(QBrush(color))

            brush(fill)
            pen(QColor("#303030"))
            painter.drawRect(1, 1, size - 2, size - 2)

            if icon_key in {"parent-folder", "new-folder"}:
                brush(yellow)
                pen(dark)
                painter.drawRect(4, 8, size - 7, size - 7)
                painter.drawRect(5, 6, 7, 4)
                if icon_key == "parent-folder":
                    brush(blue)
                    pen(blue)
                    painter.drawPolygon(
                        [
                            QPoint(mid, 5),
                            QPoint(mid - 4, 10),
                            QPoint(mid + 4, 10),
                        ]
                    )
                    painter.drawRect(mid - 1, 9, 2, 6)
                else:
                    pen(QColor("#1c7a38"), 2)
                    painter.drawLine(mid, 8, mid, size - 5)
                    painter.drawLine(mid - 4, 12, mid + 4, 12)
            elif icon_key in {"download", "upload"}:
                direction = 1 if icon_key == "download" else -1
                pen(white, 2)
                painter.drawLine(mid, 5 if direction == 1 else 10, mid, 13 if direction == 1 else 16)
                if direction == 1:
                    painter.drawPolygon([QPoint(mid - 4, 12), QPoint(mid + 4, 12), QPoint(mid, 17)])
                else:
                    painter.drawPolygon([QPoint(mid - 4, 9), QPoint(mid + 4, 9), QPoint(mid, 4)])
                painter.drawRect(5, 15, size - 10, 2)
            elif icon_key == "connect":
                brush(QColor("#55cc7a"))
                pen(white, 2)
                painter.drawEllipse(4, 4, size - 8, size - 8)
                painter.drawLine(mid, 5, mid, mid)
            elif icon_key == "new-file":
                brush(QColor("#d7dde5"))
                pen(dark)
                painter.drawRect(5, 4, size - 8, size - 6)
                pen(QColor("#1c7a38"), 2)
                painter.drawLine(mid, 8, mid, size - 6)
                painter.drawLine(mid - 4, 12, mid + 4, 12)
            elif icon_key == "delete":
                pen(white, 2)
                painter.drawLine(5, 5, size - 5, size - 5)
                painter.drawLine(size - 5, 5, 5, size - 5)
            elif icon_key == "ascii-mode":
                pen(white, 1)
                painter.drawText(5, 15, "A")
            elif icon_key == "split-view":
                pen(white, 2)
                painter.drawRect(5, 5, size - 10, size - 10)
                painter.drawLine(mid, 5, mid, size - 5)
            elif icon_key == "tools":
                pen(white, 2)
                painter.drawLine(5, 5, size - 6, size - 6)
                painter.drawLine(size - 6, 5, 6, size - 5)
            elif icon_key == "terminal":
                brush(QColor("#111111"))
                pen(QColor("#d7d7d7"))
                painter.drawRect(4, 5, size - 8, size - 9)
                pen(QColor("#35d7c7"), 2)
                painter.drawLine(7, 9, 11, 12)
                painter.drawLine(11, 12, 7, 15)

        def monitoring_control_icon(self, icon_key: str, *, size: int = 20) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                cyan = QColor("#35d7c7")
                dark = QColor("#101010")
                painter.setPen(QPen(cyan, 1))
                painter.setBrush(QBrush(dark))
                if icon_key == "monitor":
                    painter.drawRect(3, 4, size - 6, size - 8)
                    painter.setPen(QPen(cyan, 2))
                    painter.drawLine(6, 12, 9, 8)
                    painter.drawLine(9, 8, 12, 14)
                    painter.drawLine(12, 14, 15, 7)
                    painter.drawLine(size // 2, size - 4, size // 2, size - 2)
                    painter.drawLine(6, size - 2, size - 6, size - 2)
                elif icon_key == "follow-folder":
                    painter.setBrush(QBrush(QColor("#ffd866")))
                    painter.setPen(QPen(QColor("#303030"), 1))
                    painter.drawRect(3, 8, size - 6, size - 7)
                    painter.drawRect(4, 6, 7, 4)
                    painter.setPen(QPen(QColor("#1c7a38"), 2))
                    painter.drawLine(size - 8, size - 7, size - 5, size - 4)
                    painter.drawLine(size - 5, size - 4, size - 2, size - 10)
                else:
                    painter.drawEllipse(4, 4, size - 8, size - 8)
            finally:
                painter.end()
            return QIcon(pixmap)

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

    class MobaConnectedSessionPanel(QWidget):
        def __init__(self, state: MobaConnectedSessionState, terminal_pane: TerminalPane) -> None:
            super().__init__()
            self.setObjectName("mobaConnectedSession")
            self.state = state
            self.terminal_pane = terminal_pane
            self.apply_connected_session_route_properties(self)
            self.apply_connected_identity_route_properties(self)

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            root.addWidget(self.build_terminal_area(), 1)
            root.addWidget(self.build_telemetry_bar())

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

        def apply_connected_identity_route_properties(self, widget) -> None:
            route = moba_connected_session_identity_route(self.state)
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

        def build_terminal_area(self) -> QWidget:
            area = QWidget()
            area.setObjectName("mobaTerminalArea")
            self.apply_connected_session_route_properties(area)
            self.apply_sftp_terminal_folder_route_properties(area)
            layout = QHBoxLayout(area)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            terminal_stack = QWidget()
            terminal_stack.setObjectName("mobaTerminalStack")
            stack_layout = QVBoxLayout(terminal_stack)
            stack_layout.setContentsMargins(0, 0, 0, 0)
            stack_layout.setSpacing(0)
            stack_layout.addWidget(self.build_ssh_banner_slot())
            self.apply_terminal_transcript_evidence()
            self.apply_moba_plain_terminal_mode()
            stack_layout.addWidget(self.terminal_pane, 1)
            layout.addWidget(terminal_stack, 1)
            layout.addWidget(self.build_right_utility_rail())
            return area

        def apply_terminal_transcript_evidence(self) -> None:
            lines = self.state.terminal_transcript
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptKeys", [line.key for line in lines])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptTones", [line.tone for line in lines])
            self.apply_connected_session_route_properties(self.terminal_pane.output)
            self.apply_connected_identity_route_properties(self.terminal_pane.output)
            self.apply_sftp_terminal_folder_route_properties(self.terminal_pane.output)
            self.terminal_pane.output.setPlainText("\n".join(line.text for line in lines))
            self.terminal_pane.output.moveCursor(QTextCursor.MoveOperation.End)

        def apply_moba_plain_terminal_mode(self) -> None:
            geometry = gui_design_moba_terminal_transcript_row_geometry()
            self.apply_connected_session_route_properties(self.terminal_pane)
            self.terminal_pane.setProperty("mobaPlainTerminalMode", True)
            self.terminal_pane.setProperty("mobaTerminalHeaderVisible", False)
            self.terminal_pane.setProperty("mobaTerminalCommandRowVisible", False)
            self.terminal_pane.setProperty("mobaTerminalInputVisible", False)
            self.terminal_pane.header.setVisible(False)
            self.terminal_pane.command_row.setVisible(False)
            self.terminal_pane.input.setVisible(False)
            self.terminal_pane.output.setProperty("mobaPlainTerminalMode", True)
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptGeometryKeys", [row.key for row in geometry])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptX", [row.static_x for row in geometry])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptY", [row.static_y for row in geometry])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptRowHeight", [row.row_height for row in geometry])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptFontSize", [row.font_size for row in geometry])

        def build_right_utility_rail(self) -> QFrame:
            chrome = gui_design_moba_right_utility_rail_chrome()
            route = gui_design_moba_right_utility_action_route()
            rail = QFrame()
            rail.setObjectName("mobaRightUtilityRail")
            rail.setProperty("mobaRightUtilityRouteKey", route.key)
            rail.setProperty("mobaRightUtilityRouteRole", route.route_role)
            rail.setProperty("mobaRightUtilityRouteRailObject", route.rail_object)
            rail.setProperty("mobaRightUtilityRouteActionObject", route.action_object)
            rail.setProperty(route.action_keys_property, list(route.action_keys))
            rail.setProperty("mobaRightUtilityRouteRenderSource", route.render_source)
            rail.setProperty("mobaRightUtilityRailStaticWidth", chrome.static_width)
            rail.setProperty("mobaRightUtilityRailLiveWidth", chrome.live_width)
            rail.setProperty("mobaRightUtilityRailMargins", [chrome.margin_left, chrome.margin_top, chrome.margin_right, chrome.margin_bottom])
            rail.setProperty("mobaRightUtilityRailActionSpacing", chrome.action_spacing)
            rail.setProperty("mobaRightUtilityRailSessionEdgeTopY", chrome.session_edge_top_y)
            rail.setProperty("mobaRightUtilityRailSessionEdgeHeight", chrome.session_edge_height)
            rail.setProperty("mobaRightUtilityRailSessionEdgeIconX", chrome.session_edge_icon_x)
            rail.setProperty("mobaRightUtilityRailSessionEdgeIconSize", chrome.session_edge_icon_size)
            rail.setFixedWidth(chrome.live_width)
            layout = QVBoxLayout(rail)
            layout.setContentsMargins(chrome.margin_left, chrome.margin_top, chrome.margin_right, chrome.margin_bottom)
            layout.setSpacing(chrome.action_spacing)
            layout.addWidget(self.build_session_edge_controls())
            route_handlers = dict(zip(route.action_keys, route.action_handlers, strict=True))
            for action in gui_design_moba_right_utility_actions():
                button = QToolButton()
                button.setObjectName("mobaRightUtilityAction")
                button.setProperty("mobaRightUtilityKey", action.key)
                button.setProperty("mobaRightUtilityIconKey", action.icon_key)
                button.setProperty("mobaRightUtilityRouteKey", route.key)
                button.setProperty("mobaRightUtilityRouteRole", route.route_role)
                button.setProperty(route.action_key_property, action.key)
                button.setProperty(route.action_label_property, action.label)
                button.setProperty(route.action_object_property, route.action_object)
                button.setProperty(route.icon_key_property, action.icon_key)
                button.setProperty("mobaRightUtilityRouteHandler", route_handlers[action.key])
                button.setProperty(route.action_keys_property, list(route.action_keys))
                button.setProperty("mobaRightUtilityRouteRenderSource", route.render_source)
                button.setProperty("mobaRightUtilityStaticX", action.static_x)
                button.setProperty("mobaRightUtilityStaticY", action.static_y)
                button.setProperty("mobaRightUtilityStaticSize", action.static_size)
                button.setProperty("mobaRightUtilityLiveIconSize", action.live_icon_size)
                button.setProperty("mobaRightUtilityButtonSize", action.button_size)
                button.setProperty("mobaRightUtilityRenderSource", action.render_source)
                button.setToolTip(action.tooltip)
                button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
                button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
                button.setFixedSize(QSize(action.button_size, action.button_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.clicked.connect(getattr(self, route_handlers[action.key]))
                layout.addWidget(button)
            layout.addStretch(1)
            return rail

        def build_session_edge_controls(self) -> QFrame:
            chrome = gui_design_moba_right_utility_rail_chrome()
            controls = QFrame()
            controls.setObjectName("mobaSessionEdgeControls")
            actions = gui_design_moba_session_edge_actions()
            controls.setProperty("mobaSessionEdgeActionKeys", [action.key for action in actions])
            controls.setProperty("mobaSessionEdgePlacement", "tab-strip-overlay")
            controls.setProperty("mobaSessionEdgeTopY", chrome.session_edge_top_y)
            controls.setProperty("mobaSessionEdgeStaticHeight", chrome.session_edge_height)
            controls.setProperty("mobaSessionEdgeIconX", chrome.session_edge_icon_x)
            controls.setProperty("mobaSessionEdgeIconSize", chrome.session_edge_icon_size)
            controls.setProperty(
                "mobaSessionEdgeRelativeY",
                [action.relative_y(chrome.session_edge_top_y) for action in actions],
            )
            controls.setFixedWidth(chrome.live_width)
            controls.setFixedHeight(chrome.session_edge_height)
            for action in actions:
                relative_y = action.relative_y(chrome.session_edge_top_y)
                button = QToolButton(controls)
                button.setObjectName("mobaSessionEdgeAction")
                button.setProperty("mobaSessionEdgeKey", action.key)
                button.setProperty("mobaSessionEdgeIconKey", action.icon_key)
                button.setProperty("mobaSessionEdgeStaticY", action.static_y)
                button.setProperty("mobaSessionEdgeRelativeY", relative_y)
                button.setProperty("mobaSessionEdgeIconX", chrome.session_edge_icon_x)
                button.setProperty("mobaSessionEdgeIconSize", chrome.session_edge_icon_size)
                button.setProperty("mobaSessionEdgeStaticSize", action.static_size)
                button.setProperty("mobaSessionEdgeLiveIconSize", action.live_icon_size)
                button.setProperty("mobaSessionEdgeButtonSize", action.button_size)
                button.setProperty("mobaSessionEdgeRenderSource", action.render_source)
                button.setToolTip(action.tooltip)
                button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
                button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
                button.setFixedSize(QSize(action.button_size, action.button_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setGeometry(
                    chrome.session_edge_icon_x,
                    relative_y,
                    action.button_size,
                    action.button_size,
                )
            return controls

        def moba_utility_icon(self, icon_key: str, fill: str) -> QIcon:
            pixmap = QPixmap(20, 20)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            color = QColor(fill)
            try:
                painter.setPen(QPen(color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if icon_key == "clip":
                    painter.drawArc(5, 3, 10, 13, 35 * 16, 280 * 16)
                    painter.drawArc(8, 5, 6, 10, 35 * 16, 280 * 16)
                    painter.drawLine(9, 14, 6, 11)
                elif icon_key == "spark":
                    painter.drawLine(10, 3, 10, 17)
                    painter.drawLine(3, 10, 17, 10)
                    painter.drawLine(5, 5, 15, 15)
                    painter.drawLine(15, 5, 5, 15)
                elif icon_key == "gear":
                    painter.drawEllipse(6, 6, 8, 8)
                    painter.drawEllipse(8, 8, 4, 4)
                    for start, end in (
                        ((10, 2), (10, 6)),
                        ((10, 14), (10, 18)),
                        ((2, 10), (6, 10)),
                        ((14, 10), (18, 10)),
                        ((4, 4), (7, 7)),
                        ((16, 4), (13, 7)),
                        ((4, 16), (7, 13)),
                        ((16, 16), (13, 13)),
                    ):
                        painter.drawLine(*start, *end)
                elif icon_key == "arrow-left":
                    painter.drawLine(14, 5, 7, 10)
                    painter.drawLine(7, 10, 14, 15)
                    painter.drawLine(7, 10, 17, 10)
                elif icon_key == "arrow-right":
                    painter.drawLine(6, 5, 13, 10)
                    painter.drawLine(13, 10, 6, 15)
                    painter.drawLine(3, 10, 13, 10)
                elif icon_key == "close":
                    painter.drawLine(6, 6, 14, 14)
                    painter.drawLine(14, 6, 6, 14)
                else:
                    painter.drawRect(4, 4, 12, 12)
            finally:
                painter.end()
            return QIcon(pixmap)

        def build_ssh_banner_slot(self) -> QFrame:
            chrome = gui_design_moba_ssh_banner_chrome()
            slot = QFrame()
            slot.setObjectName("mobaSshBannerSlot")
            self.apply_connected_session_route_properties(slot)
            slot.setProperty("mobaBannerLeftOffset", chrome.static_left_offset)
            slot.setProperty("mobaBannerTopOffset", chrome.static_top_offset)
            slot.setProperty("mobaBannerTerminalGap", chrome.terminal_gap)
            slot.setFixedHeight(chrome.static_top_offset + chrome.static_height + chrome.terminal_gap)
            banner = self.build_ssh_banner()
            banner.setParent(slot)
            banner.setGeometry(
                chrome.static_left_offset,
                chrome.static_top_offset,
                chrome.static_width,
                chrome.static_height,
            )
            return slot

        def apply_ssh_banner_row_geometry(self, label: QLabel, key: str) -> None:
            geometry = gui_design_moba_ssh_banner_row_geometry_for(key)
            label.setProperty("mobaSshBannerRowKey", geometry.key)
            label.setProperty("mobaSshBannerRowX", geometry.static_x)
            label.setProperty("mobaSshBannerRowY", geometry.static_y)
            label.setProperty("mobaSshBannerRowWidth", geometry.static_width)
            label.setProperty("mobaSshBannerRowHeight", geometry.static_height)
            label.setProperty("mobaSshBannerRowCentered", geometry.centered)
            label.setGeometry(
                geometry.static_x,
                geometry.static_y,
                geometry.static_width,
                geometry.static_height,
            )
            if geometry.centered:
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        def build_ssh_banner(self) -> QFrame:
            chrome = gui_design_moba_ssh_banner_chrome()
            banner = QFrame()
            banner.setObjectName("mobaSshBanner")
            self.apply_connected_session_route_properties(banner)
            self.apply_connected_identity_route_properties(banner)
            banner.setProperty("mobaBannerTitle", chrome.title)
            banner.setProperty("mobaBannerSubtitle", chrome.subtitle)
            banner.setProperty("mobaBannerTargetIntro", chrome.target_intro)
            banner.setProperty("mobaBannerCapabilityLabelWidth", chrome.capability_label_width)
            banner.setProperty("mobaBannerFooterPrefix", chrome.footer_prefix)
            banner.setProperty("mobaBannerCapabilityKeys", [row.key for row in self.state.banner.capability_rows()])
            banner.setProperty("mobaBannerFooterLinks", list(self.state.banner.footer_links()))
            banner.setProperty("mobaBannerWidth", chrome.static_width)
            banner.setProperty("mobaBannerHeight", chrome.static_height)
            banner.setProperty("mobaBannerLeftOffset", chrome.static_left_offset)
            banner.setProperty("mobaBannerTopOffset", chrome.static_top_offset)
            banner.setProperty("mobaBannerTerminalGap", chrome.terminal_gap)
            banner.setProperty(
                "mobaSshBannerRowGeometryKeys",
                [geometry.key for geometry in gui_design_moba_ssh_banner_row_geometry()],
            )
            banner.setFixedSize(QSize(chrome.static_width, chrome.static_height))
            title = QLabel(f"{chrome.heading_prefix}{chrome.title}{chrome.heading_suffix}")
            title.setParent(banner)
            title.setObjectName("mobaSshBannerTitle")
            self.apply_ssh_banner_row_geometry(title, "title")
            subtitle = QLabel(chrome.subtitle)
            subtitle.setParent(banner)
            subtitle.setObjectName("mobaSshBannerSubtitle")
            self.apply_ssh_banner_row_geometry(subtitle, "subtitle")
            target = QLabel(f"> {chrome.target_intro} {self.state.banner.title}")
            target.setParent(banner)
            target.setObjectName("mobaSshBannerTargetLine")
            self.apply_connected_identity_route_properties(target)
            target.setProperty("mobaSshBannerTarget", self.state.banner.title)
            target.setProperty("mobaSshBannerTargetIntro", chrome.target_intro)
            self.apply_ssh_banner_row_geometry(target, "target")
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            for row in self.state.banner.capability_rows():
                label = QLabel(f"  * {row.line(label_width=chrome.capability_label_width)}")
                label.setParent(banner)
                label.setObjectName("mobaSshBannerCapability")
                label.setProperty("mobaSshBannerCapabilityKey", row.key)
                label.setProperty("mobaSshBannerCapabilityLabel", row.label)
                label.setProperty("mobaSshBannerCapabilityValue", row.value)
                label.setProperty("mobaSshBannerCapabilityStatus", row.status)
                label.setProperty("capabilityStatus", row.status)
                self.apply_ssh_banner_row_geometry(label, row.key)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            help_link, website_link = self.state.banner.footer_links()
            footer = QLabel(f"> {chrome.footer_prefix} {help_link} or visit our {website_link}.")
            footer.setParent(banner)
            footer.setObjectName("mobaSshBannerFooter")
            footer.setProperty("mobaSshBannerFooterLinks", [help_link, website_link])
            self.apply_ssh_banner_row_geometry(footer, "footer")
            footer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return banner

        def build_telemetry_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("mobaTelemetryBar")
            self.apply_connected_session_route_properties(bar)
            self.apply_connected_identity_route_properties(bar)
            route = gui_design_moba_monitoring_telemetry_route()
            geometry_items = moba_telemetry_cell_geometry()
            bar.setProperty("mobaTelemetryGeometryKeys", [geometry.key for geometry in geometry_items])
            bar.setProperty("mobaTelemetryStartX", geometry_items[0].static_x)
            bar.setProperty("mobaTelemetryBarHeight", 24)
            bar.setProperty("mobaMonitoringTelemetryRouteKey", route.key)
            bar.setProperty("mobaMonitoringTelemetryRouteRole", route.route_role)
            bar.setProperty("mobaMonitoringTelemetrySourcePanelObject", route.source_panel_object)
            bar.setProperty("mobaMonitoringTelemetrySourceControl", route.source_control_key)
            bar.setProperty("mobaMonitoringTelemetrySurface", route.telemetry_surface)
            bar.setProperty("mobaMonitoringTelemetryMetricCellKeys", list(route.target_metric_cell_keys))
            bar.setProperty("mobaMonitoringTelemetryIdentityCellKey", route.target_identity_cell_key)
            bar.setFixedHeight(24)
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(geometry_items[0].static_x, 0, 7, 0)
            layout.setSpacing(0)
            for cell in moba_telemetry_cells(self.state):
                geometry = moba_telemetry_cell_geometry_for(cell.key)
                cell_frame = QFrame()
                cell_frame.setObjectName("mobaTelemetryCell")
                cell_frame.setProperty("mobaTelemetryKey", cell.key)
                cell_frame.setProperty("mobaTelemetryIconKey", cell.icon_key)
                cell_frame.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                cell_frame.setProperty("mobaTelemetryIconSize", cell.icon_size)
                cell_frame.setProperty("mobaTelemetryDisplayText", cell.display_text)
                if cell.key == "target":
                    self.apply_connected_identity_route_properties(cell_frame)
                cell_frame.setProperty("mobaTelemetryCellStaticX", geometry.static_x)
                cell_frame.setProperty("mobaTelemetryCellStaticY", geometry.static_y)
                cell_frame.setProperty("mobaTelemetryCellWidth", geometry.width)
                cell_frame.setProperty("mobaTelemetryCellHeight", geometry.height)
                cell_frame.setProperty("mobaTelemetrySeparatorTop", geometry.separator_top)
                cell_frame.setProperty("mobaTelemetrySeparatorBottom", geometry.separator_bottom)
                cell_frame.setProperty("mobaMonitoringTelemetryRouted", cell.key in route.target_metric_cell_keys)
                cell_frame.setToolTip(cell.label)
                cell_frame.setFixedWidth(geometry.width)
                cell_frame.setFixedHeight(geometry.height)
                cell_layout = QHBoxLayout(cell_frame)
                cell_layout.setContentsMargins(geometry.icon_x, 0, 5, 0)
                cell_layout.setSpacing(geometry.label_x - geometry.icon_x - geometry.icon_size)
                icon = QLabel()
                icon.setObjectName("mobaTelemetryIcon")
                icon.setProperty("mobaTelemetryKey", cell.key)
                icon.setProperty("mobaTelemetryIconKey", cell.icon_key)
                icon.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                icon.setProperty("mobaTelemetryIconX", geometry.icon_x)
                icon.setProperty("mobaTelemetryIconY", geometry.icon_y)
                icon.setProperty("mobaTelemetryIconSize", geometry.icon_size)
                icon.setProperty("mobaTelemetryIconRender", "generated-pixmap")
                icon.setPixmap(self.telemetry_icon_pixmap(cell))
                icon.setFixedSize(QSize(geometry.icon_size, geometry.icon_size))
                icon.setToolTip(cell.label)
                cell_layout.addWidget(icon)
                label = QLabel(cell.display_text)
                label.setObjectName("mobaTelemetryItem")
                label.setProperty("mobaTelemetryKey", cell.key)
                label.setProperty("mobaTelemetryDisplayText", cell.display_text)
                if cell.key == "target":
                    self.apply_connected_identity_route_properties(label)
                label.setProperty("mobaTelemetryLabelX", geometry.label_x)
                label.setProperty("mobaTelemetryLabelY", geometry.label_y)
                label.setProperty("mobaTelemetryLabelFontSize", geometry.label_font_size)
                label.setToolTip(cell.label)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                cell_layout.addWidget(label, 1)
                layout.addWidget(cell_frame)
            layout.addStretch(1)
            return bar

        def telemetry_icon_pixmap(self, cell) -> QPixmap:
            size = cell.icon_size
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            try:
                accent = QColor(cell.icon_accent)
                dark = QColor("#101010")

                def pen(color: QColor, width: int = 1) -> None:
                    painter.setPen(QPen(color, width))

                def brush(color: QColor) -> None:
                    painter.setBrush(QBrush(color))

                pen(accent)
                brush(dark)
                painter.drawRect(0, 0, size - 1, size - 1)
                mid = size // 2
                icon_key = cell.icon_key
                if icon_key == "host":
                    painter.drawRect(3, 3, size - 6, size - 8)
                    painter.drawLine(4, size - 3, size - 4, size - 3)
                elif icon_key == "cpu":
                    painter.drawRect(3, 3, size - 6, size - 6)
                    painter.drawPoint(mid, 4)
                    painter.drawPoint(mid, size - 4)
                    painter.drawPoint(4, mid)
                    painter.drawPoint(size - 4, mid)
                elif icon_key in {"memory", "disk"}:
                    painter.drawRect(3, 4, size - 6, size - 8)
                    painter.drawLine(4, size - 5, size - 4, size - 5)
                elif icon_key == "upload":
                    pen(accent, 2)
                    painter.drawLine(mid, size - 3, mid, 3)
                    painter.drawLine(mid, 3, mid - 3, 6)
                    painter.drawLine(mid, 3, mid + 3, 6)
                elif icon_key == "download":
                    pen(accent, 2)
                    painter.drawLine(mid, 3, mid, size - 3)
                    painter.drawLine(mid, size - 3, mid - 3, size - 6)
                    painter.drawLine(mid, size - 3, mid + 3, size - 6)
                elif icon_key == "connection":
                    pen(accent, 2)
                    painter.drawArc(2, 3, size - 4, size, 200 * 16, 140 * 16)
                elif icon_key == "process":
                    painter.drawLine(3, 4, size - 3, 4)
                    painter.drawLine(3, 7, size - 5, 7)
                    painter.drawLine(3, 10, size - 6, 10)
            finally:
                painter.end()
            return pixmap

    class ProfileDialog(QDialog):
        def __init__(self, profile=None, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("workflowDialog")
            self.setWindowTitle("Profile")
            self.resize(520, 660)
            data = profile_to_editor_data(profile)
            self.fields: dict[str, object] = {}
            form = QFormLayout(self)
            title = QLabel("Session profile")
            title.setObjectName("workflowTitle")
            subtitle = QLabel("Create or edit a connection profile, including tunnels and protocol options.")
            subtitle.setObjectName("workflowSubtitle")
            form.addRow(title)
            form.addRow(subtitle)

            for key, label in [
                ("name", "Name"),
                ("protocol", "Protocol"),
                ("host", "Host"),
                ("port", "Port"),
                ("username", "Username"),
                ("group", "Group"),
                ("tags", "Tags"),
                ("path", "Path"),
                ("url", "URL"),
                ("command", "Command"),
                ("identity_file", "Identity file"),
                ("credential_ref", "Credential ref"),
            ]:
                widget = QLineEdit(data[key])
                self.fields[key] = widget
                form.addRow(label, widget)

            description = QPlainTextEdit()
            description.setPlainText(data["description"])
            description.setMaximumBlockCount(200)
            self.fields["description"] = description
            form.addRow("Description", description)

            options = QPlainTextEdit()
            options.setPlainText(data["options"])
            options.setPlaceholderText("key=value")
            self.fields["options"] = options
            form.addRow("Options", options)

            tunnels = QPlainTextEdit()
            tunnels.setPlainText(data["tunnels"])
            tunnels.setPlaceholderText("dynamic:1080\nlocal:15432:127.0.0.1:5432")
            self.fields["tunnels"] = tunnels
            form.addRow("Tunnels", tunnels)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            form.addRow(buttons)

        def editor_data(self) -> dict[str, str]:
            data: dict[str, str] = {}
            for key, widget in self.fields.items():
                if isinstance(widget, QPlainTextEdit):
                    data[key] = widget.toPlainText()
                else:
                    data[key] = widget.text()
            return data

        def profile(self):
            return profile_from_editor_data(self.editor_data())

    class LayoutDialog(QDialog):
        def __init__(self, layout=None, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("workflowDialog")
            self.setWindowTitle("Layout")
            self.resize(520, 520)
            data = layout_to_editor_data(layout)
            form = QFormLayout(self)
            title = QLabel("Workspace layout")
            title.setObjectName("workflowTitle")
            subtitle = QLabel("Arrange multiple terminal panes from profiles and commands.")
            subtitle.setObjectName("workflowSubtitle")
            form.addRow(title)
            form.addRow(subtitle)
            self.name = QLineEdit(data["name"])
            self.orientation = QComboBox()
            self.orientation.addItems(["grid", "horizontal", "vertical"])
            self.orientation.setCurrentText(data["orientation"])
            self.description = QPlainTextEdit()
            self.description.setPlainText(data["description"])
            self.panes = QPlainTextEdit()
            self.panes.setPlainText(data["panes"])
            self.panes.setPlaceholderText("profile:edge | Edge\ncommand:python -V | Version")
            form.addRow("Name", self.name)
            form.addRow("Orientation", self.orientation)
            form.addRow("Description", self.description)
            form.addRow("Panes", self.panes)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            form.addRow(buttons)

        def editor_data(self) -> dict[str, str]:
            return {
                "name": self.name.text(),
                "orientation": self.orientation.currentText(),
                "description": self.description.toPlainText(),
                "panes": self.panes.toPlainText(),
            }

        def layout(self) -> Layout:
            return layout_from_editor_data(self.editor_data())

    class TransferQueueDialog(QDialog):
        def __init__(self, profile, parent=None) -> None:
            super().__init__(parent)
            self.setObjectName("workflowDialog")
            self.profile = profile
            self.setWindowTitle(f"Transfer Queue: {profile.name}")
            self.resize(640, 620)

            root = QVBoxLayout(self)
            title = QLabel("Transfer queue")
            title.setObjectName("workflowTitle")
            subtitle = QLabel(f"Build and preview SFTP operations for {profile.name}.")
            subtitle.setObjectName("workflowSubtitle")
            root.addWidget(title)
            root.addWidget(subtitle)
            form = QFormLayout()
            self.operations = QPlainTextEdit()
            self.operations.setPlaceholderText(
                "get /etc/hosts ./hosts.copy\nput ./build.tar.gz /tmp/build.tar.gz\nmkdir /tmp/releases"
            )
            self.local_preview_path = QLineEdit()
            self.local_preview_path.setPlaceholderText("Local file or directory")
            self.force_destructive = QCheckBox("Force destructive actions")
            form.addRow("Operations", self.operations)
            form.addRow("Local preview", self.local_preview_path)
            form.addRow("", self.force_destructive)
            root.addLayout(form)

            controls = QHBoxLayout()
            self.preview_button = QPushButton("Preview Queue")
            self.local_preview_button = QPushButton("Preview Local")
            controls.addWidget(self.preview_button)
            controls.addWidget(self.local_preview_button)
            controls.addStretch(1)
            root.addLayout(controls)

            self.preview = QTextEdit()
            self.preview.setReadOnly(True)
            self.preview.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            root.addWidget(self.preview, 1)

            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            root.addWidget(buttons)

            self.preview_button.clicked.connect(self.refresh_queue_preview)
            self.local_preview_button.clicked.connect(self.refresh_local_preview)

        def queue_plan(self):
            items = []
            for line in self.operations.toPlainText().splitlines():
                raw = line.strip()
                if raw and not raw.startswith("#"):
                    items.append(parse_transfer_item_spec(raw))
            return build_sftp_queue_plan(self.profile, items, force=self.force_destructive.isChecked())

        def refresh_queue_preview(self) -> None:
            try:
                plan = self.queue_plan()
            except ValueError as exc:
                self.preview.setPlainText(f"error: {exc}")
                return
            lines = [plan.printable(), "", "queue:"]
            for index, command in enumerate(plan.batch_commands, start=1):
                lines.append(f"{index}. {command}")
            for note in plan.notes:
                lines.append(f"note: {note}")
            self.preview.setPlainText("\n".join(lines))

        def refresh_local_preview(self) -> None:
            try:
                preview = preview_local_path(self.local_preview_path.text())
            except ValueError as exc:
                self.preview.setPlainText(f"error: {exc}")
                return
            data = preview.to_dict()
            lines = [f"{data['path']}: {data['kind']}"]
            if data.get("size") is not None:
                lines.append(f"size: {data['size']}")
            for child in data.get("children", []):
                lines.append(f"  {child}")
            if data.get("binary"):
                lines.append("binary: true")
            if data.get("truncated"):
                lines.append("truncated: true")
            if data.get("text"):
                lines.append("")
                lines.append(str(data["text"]))
            if data.get("error"):
                lines.append(f"error: {data['error']}")
            self.preview.setPlainText("\n".join(lines))

    class WorkflowDialog(QDialog):
        def __init__(
            self,
            title: str,
            subtitle: str,
            rows: list[tuple[str, str, str]],
            detail: str,
            actions: list[tuple[str, object]] | None = None,
            parent=None,
        ) -> None:
            super().__init__(parent)
            self.setObjectName("workflowDialog")
            self.setWindowTitle(title)
            self.resize(660, 520)

            root = QVBoxLayout(self)
            root.setSpacing(10)
            title_label = QLabel(title)
            title_label.setObjectName("workflowTitle")
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("workflowSubtitle")
            subtitle_label.setWordWrap(True)
            root.addWidget(title_label)
            root.addWidget(subtitle_label)

            self.rows = QTreeWidget()
            self.rows.setObjectName("workflowRows")
            self.rows.setColumnCount(3)
            self.rows.setHeaderLabels(["Workflow", "State", "Detail"])
            self.rows.setRootIsDecorated(False)
            for workflow, state, row_detail in rows:
                item = QTreeWidgetItem([workflow, state, row_detail])
                self.rows.addTopLevelItem(item)
            self.rows.resizeColumnToContents(0)
            self.rows.resizeColumnToContents(1)
            root.addWidget(self.rows, 1)

            self.detail = QTextEdit()
            self.detail.setObjectName("workflowPreview")
            self.detail.setReadOnly(True)
            self.detail.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.detail.setPlainText(detail)
            root.addWidget(self.detail, 1)

            action_row = QHBoxLayout()
            for label, callback in actions or []:
                button = QToolButton()
                button.setObjectName("workflowAction")
                button.setText(label)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.clicked.connect(self.workflow_action(callback))
                action_row.addWidget(button)
            action_row.addStretch(1)
            close_button = QToolButton()
            close_button.setObjectName("workflowAction")
            close_button.setText("Close")
            close_button.clicked.connect(self.accept)
            action_row.addWidget(close_button)
            root.addLayout(action_row)

        def workflow_action(self, callback):
            def run(*_args) -> None:
                self.accept()
                callback()

            return run

    class MobaRailLabel(QLabel):
        def __init__(self, label: str, role: str) -> None:
            super().__init__(label)
            chrome = gui_design_moba_rail_chrome()
            geometry = gui_design_moba_rail_item_geometry_for(role)
            self.setObjectName("mobaRailLabel")
            self.setProperty("mobaRailRole", role)
            self.setProperty("mobaRailLabel", label)
            self.setProperty("mobaRailStaticLabelY", geometry.static_label_y)
            self.setProperty("mobaRailLabelWidth", chrome.label_width)
            self.setProperty("mobaRailLabelHeight", chrome.label_height)
            self.setProperty("mobaRailLabelFontSize", chrome.label_font_size)
            self.setToolTip(label)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setFixedSize(chrome.label_width, chrome.label_height)

        def paintEvent(self, event) -> None:  # noqa: N802
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.translate(self.width() / 2, self.height() / 2)
            painter.rotate(-90)
            painter.drawText(
                -self.height() // 2,
                -self.width() // 2,
                self.height(),
                self.width(),
                Qt.AlignmentFlag.AlignCenter,
                self.text(),
            )
            painter.end()

    class MainWindow(QMainWindow):
        CLOSE_STOP_POLICY = ProcessStopPolicy(terminate_timeout_ms=2000, kill_timeout_ms=500)

        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("remoteOpsMain")
            self.setWindowTitle("Remote Ops Workspace")
            self.apply_moba_titlebar_chrome("Remote Ops Workspace")
            self.resize(1180, 720)
            self.store = ProfileStore()
            self.store.init(with_examples=True)
            self.layout_store = LayoutStore()

            self.build_menu_bar()
            self.main_toolbar = QToolBar("Main")
            self.main_toolbar.setObjectName("mainToolbar")
            self.main_toolbar.setMovable(False)
            self.addToolBar(self.main_toolbar)
            self.layout_toolbar = QToolBar("Layouts")
            self.layout_toolbar.setObjectName("layoutToolbar")
            self.layout_toolbar.setMovable(False)
            self.addToolBarBreak()
            self.addToolBar(self.layout_toolbar)
            self.refresh_button = self.toolbar_button("Refresh", "SP_BrowserReload", "Reload profiles")
            self.new_profile_button = self.toolbar_button("New", "SP_FileIcon", "Create profile")
            self.edit_profile_button = self.toolbar_button("Edit", "SP_FileDialogDetailedView", "Edit selected profile")
            self.remove_profile_button = self.toolbar_button("Remove", "SP_TrashIcon", "Remove selected profile")
            self.remove_profile_button.setObjectName("dangerAction")
            self.connect_button = self.toolbar_button("Connect", "SP_MediaPlay", "Open selected profile")
            self.connect_button.setObjectName("primaryAction")
            self.files_button = self.toolbar_button("Files", "SP_DirIcon", "Open SFTP browser")
            self.queue_button = self.toolbar_button("Queue", "SP_FileDialogListView", "Preview transfer queue")
            self.dry_run_button = self.toolbar_button("Dry Run", "SP_CommandLink", "Show launch command")
            self.doctor_button = self.toolbar_button("Doctor", "SP_MessageBoxInformation", "Run doctor checks")
            self.split_h_button = self.toolbar_button("Split H", "SP_TitleBarShadeButton", "Open horizontal split")
            self.split_v_button = self.toolbar_button("Split V", "SP_TitleBarUnshadeButton", "Open vertical split")
            self.layout_select = QComboBox()
            self.layout_select.setObjectName("layoutSelect")
            self.layout_select.setMinimumWidth(180)
            self.design_select = QComboBox()
            self.design_select.setObjectName("designSelect")
            self.design_select.setMinimumWidth(170)
            for preset in GUI_DESIGN_PRESETS:
                self.design_select.addItem(preset.label, preset.id)
            self.apply_preset_catalog_route_properties(self.design_select, gui_design_preset_catalog_route())
            self.new_layout_button = self.toolbar_button("New Layout", "SP_FileIcon", "Create layout")
            self.edit_layout_button = self.toolbar_button("Edit Layout", "SP_FileDialogDetailedView", "Edit selected layout")
            self.remove_layout_button = self.toolbar_button("Remove Layout", "SP_TrashIcon", "Remove selected layout")
            self.remove_layout_button.setObjectName("dangerAction")
            self.open_layout_button = self.toolbar_button("Open Layout", "SP_DialogOpenButton", "Open selected layout")
            self.search_input = QLineEdit()
            self.search_input.setObjectName("toolbarSearch")
            self.search_input.setPlaceholderText("Search log")
            self.find_button = self.toolbar_button("Find", "SP_FileDialogContentsView", "Find in log")
            self.moba_ribbon_buttons = self.build_moba_ribbon_buttons()
            for button in self.moba_ribbon_buttons:
                self.main_toolbar.addWidget(button)
            self.moba_toolbar_spacer = QWidget()
            self.moba_toolbar_spacer.setObjectName("mobaToolbarSpacer")
            self.moba_toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.main_toolbar.addWidget(self.moba_toolbar_spacer)
            moba_edge_route = gui_design_moba_ribbon_edge_action_route()
            edge_action_keys = [moba_edge_route.xserver_action_key, moba_edge_route.exit_action_key]
            for widget in (self.main_toolbar, self.moba_toolbar_spacer):
                widget.setProperty("mobaRibbonEdgeRouteKey", moba_edge_route.key)
                widget.setProperty("mobaRibbonEdgeRouteRole", moba_edge_route.route_role)
                widget.setProperty("mobaRibbonEdgeRouteToolbarObject", moba_edge_route.toolbar_object)
                widget.setProperty("mobaRibbonEdgeRouteSpacerObject", moba_edge_route.spacer_object)
                widget.setProperty(moba_edge_route.action_keys_property, edge_action_keys)
                widget.setProperty("mobaRibbonEdgeRouteRenderSource", moba_edge_route.render_source)
            moba_edge_actions = {action.key: action for action in gui_design_moba_ribbon_edge_actions()}
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
            self.main_toolbar.addWidget(self.moba_x_server_button)
            self.main_toolbar.addWidget(self.moba_exit_button)
            self.main_toolbar_buttons = [
                self.refresh_button,
                self.new_profile_button,
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
            for button in self.main_toolbar_buttons:
                self.main_toolbar.addWidget(button)
            self.main_toolbar.addSeparator()
            self.view_label = QLabel("View")
            self.view_label.setObjectName("toolbarLabel")
            self.main_toolbar.addWidget(self.view_label)
            self.main_toolbar.addWidget(self.design_select)
            self.main_toolbar.addSeparator()
            self.main_toolbar.addWidget(self.search_input)
            self.main_toolbar.addWidget(self.find_button)
            self.layout_label = QLabel("Layout")
            self.layout_label.setObjectName("toolbarLabel")
            self.layout_toolbar.addWidget(self.layout_label)
            self.layout_toolbar.addWidget(self.layout_select)
            self.layout_toolbar_buttons = [self.new_layout_button, self.edit_layout_button, self.remove_layout_button]
            for button in self.layout_toolbar_buttons:
                self.layout_toolbar.addWidget(button)
            self.layout_toolbar.addWidget(self.open_layout_button)
            self.layout_toolbar_buttons.append(self.open_layout_button)

            self.profile_list = QTreeWidget()
            self.profile_list.setObjectName("profileTree")
            self.profile_list.setMinimumWidth(300)
            self.profile_list.setHeaderHidden(True)
            self.profile_list.setColumnCount(1)
            self.profile_list.setRootIsDecorated(True)
            self.profile_list.setAnimated(True)
            self.profile_list.setUniformRowHeights(True)
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
            self.moba_connected_dock: MobaSftpDock | None = None
            self.left_panel = self.create_left_panel()
            self.tabs = QTabWidget()
            self.tabs.setObjectName("sessionTabs")
            self.tabs.tabBar().setObjectName("sessionTabBar")
            self.tabs.setTabsClosable(True)
            self.tabs.setMovable(True)
            self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
            self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.moba_tab_guard = False
            self.recent_terminal_plans: list[TerminalPanePlan] = []
            self.log = QTextEdit()
            self.log.setObjectName("activityLog")
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Launch output, dry-run commands and doctor reports appear here.")

            self.workspace = QSplitter(Qt.Orientation.Vertical)
            self.workspace.setObjectName("workspace")
            self.workspace.addWidget(self.tabs)
            self.workspace.addWidget(self.log)
            self.workspace.setStretchFactor(0, 3)
            self.workspace.setStretchFactor(1, 1)

            self.root_splitter = QSplitter(Qt.Orientation.Horizontal)
            self.root_splitter.setObjectName("rootWorkspace")
            self.root_splitter.addWidget(self.left_panel)
            self.root_splitter.addWidget(self.workspace)
            self.root_splitter.setStretchFactor(1, 1)
            self.setCentralWidget(self.root_splitter)
            self.status_segment_labels = self.create_status_segments()

            self.refresh_button.clicked.connect(self.refresh_profiles)
            self.new_profile_button.clicked.connect(self.create_profile)
            self.edit_profile_button.clicked.connect(self.edit_selected_profile)
            self.remove_profile_button.clicked.connect(self.remove_selected_profile)
            self.connect_button.clicked.connect(lambda: self.connect_selected(False))
            self.files_button.clicked.connect(self.open_files_selected)
            self.queue_button.clicked.connect(self.open_transfer_queue_selected)
            self.dry_run_button.clicked.connect(lambda: self.connect_selected(True))
            self.doctor_button.clicked.connect(self.show_doctor)
            self.split_h_button.clicked.connect(lambda: self.add_split("horizontal"))
            self.split_v_button.clicked.connect(lambda: self.add_split("vertical"))
            self.new_layout_button.clicked.connect(self.create_layout)
            self.edit_layout_button.clicked.connect(self.edit_selected_layout)
            self.remove_layout_button.clicked.connect(self.remove_selected_layout)
            self.open_layout_button.clicked.connect(self.open_selected_layout)
            self.moba_x_server_button.clicked.connect(self.show_moba_x_server_status)
            self.moba_exit_button.clicked.connect(self.close)
            self.tabs.tabCloseRequested.connect(self.close_tab)
            self.tabs.currentChanged.connect(self.handle_tab_changed)
            self.tabs.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)
            self.design_select.currentIndexChanged.connect(self.apply_selected_design)
            self.find_button.clicked.connect(self.find_log_text)
            self.quick_connect.textChanged.connect(self.update_quick_connect_suggestions)
            self.quick_connect.returnPressed.connect(self.run_quick_connect)
            self.quick_connect_suggestions.itemActivated.connect(lambda item, _column: self.run_quick_connect_candidate(item))
            self.quick_connect_suggestions.itemDoubleClicked.connect(lambda item, _column: self.run_quick_connect_candidate(item))
            self.keyboard_shortcuts = self.create_keyboard_shortcuts()
            self.refresh_profiles()
            self.refresh_layouts()
            self.populate_view_design_menu()
            self.add_welcome_tab()
            self.apply_selected_design()

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

        def create_keyboard_shortcuts(self) -> list:
            shortcuts = []
            for spec in self.keyboard_shortcut_specs():
                shortcut = QShortcut(QKeySequence(str(spec["sequence"])), self)
                shortcut.setObjectName("presetKeyboardShortcut")
                shortcut.setProperty("presetKeyboardShortcutKey", str(spec["key"]))
                shortcut.setProperty("presetKeyboardShortcutSequence", str(spec["sequence"]))
                shortcut.setProperty("presetKeyboardShortcutActionLabel", str(spec["action_label"]))
                shortcut.activated.connect(spec["callback"])
                shortcuts.append(shortcut)
            return shortcuts

        def build_menu_bar(self) -> None:
            self.menuBar().setObjectName("mobaTopMenuBar")
            self.moba_top_menus: list[QMenu] = []
            self.moba_top_menu_actions = []
            for item in gui_design_moba_top_menu_items():
                geometry = gui_design_moba_top_menu_geometry_for(item.key)
                menu = self.menuBar().addMenu(item.label)
                menu.setObjectName("mobaTopMenu")
                menu.setProperty("mobaTopMenuKey", item.key)
                menu.setProperty("mobaTopMenuLabel", item.label)
                menu.setProperty("mobaTopMenuGeometryKeys", [item.key for item in gui_design_moba_top_menu_geometry()])
                menu.setProperty("mobaTopMenuStaticX", geometry.static_x)
                menu.setProperty("mobaTopMenuWidth", geometry.width)
                menu.setProperty("mobaTopMenuLabelY", geometry.label_y)
                menu.setProperty("mobaTopMenuLabelFontSize", geometry.label_font_size)
                menu.setProperty("mobaTopMenuGapAfter", geometry.gap_after)
                menu.setToolTip(item.tooltip)
                menu.menuAction().setProperty("mobaTopMenuKey", item.key)
                menu.menuAction().setProperty("mobaTopMenuLabel", item.label)
                menu.menuAction().setProperty(
                    "mobaTopMenuGeometryKeys",
                    [item.key for item in gui_design_moba_top_menu_geometry()],
                )
                menu.menuAction().setProperty("mobaTopMenuStaticX", geometry.static_x)
                menu.menuAction().setProperty("mobaTopMenuWidth", geometry.width)
                menu.menuAction().setProperty("mobaTopMenuLabelY", geometry.label_y)
                menu.menuAction().setProperty("mobaTopMenuLabelFontSize", geometry.label_font_size)
                menu.menuAction().setProperty("mobaTopMenuGapAfter", geometry.gap_after)
                menu.menuAction().setToolTip(item.tooltip)
                self.moba_top_menus.append(menu)
                self.moba_top_menu_actions.append(menu.menuAction())
                if item.key == "terminal":
                    menu.addAction(item.primary_action, lambda _checked=False: self.add_split("horizontal"))
                elif item.key == "sessions":
                    menu.addAction("New session", self.create_profile)
                    menu.addAction(item.primary_action, lambda _checked=False: self.connect_selected(False))
                elif item.key == "view":
                    self.view_menu = menu
                    menu.addAction(item.primary_action, self.refresh_profiles)
                elif item.key == "help":
                    menu.addAction(item.primary_action, self.show_doctor)
                else:
                    menu.addAction(item.primary_action)

            securecrt_chrome = gui_design_securecrt_top_chrome()
            self.securecrt_top_menus: list[QMenu] = []
            self.securecrt_top_menu_actions = []
            for item in securecrt_chrome.menu_items:
                menu = self.menuBar().addMenu(item.label)
                menu.setObjectName("secureCrtTopMenu")
                menu.setProperty("secureCrtTopMenuKey", item.key)
                menu.setProperty("secureCrtTopMenuLabel", item.label)
                menu.setProperty("secureCrtTopMenuPrimaryAction", item.primary_action)
                menu.setToolTip(item.tooltip)
                menu.menuAction().setProperty("secureCrtTopMenuKey", item.key)
                menu.menuAction().setProperty("secureCrtTopMenuLabel", item.label)
                menu.menuAction().setProperty("secureCrtTopMenuPrimaryAction", item.primary_action)
                menu.menuAction().setToolTip(item.tooltip)
                self.securecrt_top_menus.append(menu)
                self.securecrt_top_menu_actions.append(menu.menuAction())
                if item.key == "file":
                    menu.addAction(item.primary_action, lambda _checked=False: self.connect_selected(False))
                elif item.key == "edit":
                    menu.addAction(item.primary_action, self.find_log_text)
                elif item.key == "view":
                    menu.addAction(item.primary_action, self.refresh_profiles)
                elif item.key == "transfer":
                    menu.addAction(item.primary_action, self.open_files_selected)
                elif item.key == "tools":
                    menu.addAction(item.primary_action, self.show_doctor)
                elif item.key == "window":
                    menu.addAction(item.primary_action, lambda _checked=False: self.add_split("horizontal"))
                elif item.key == "help":
                    menu.addAction(item.primary_action, self.show_doctor)
                else:
                    menu.addAction(item.primary_action)

            mremoteng_chrome = gui_design_mremoteng_top_chrome()
            self.mremoteng_top_menus: list[QMenu] = []
            self.mremoteng_top_menu_actions = []
            for item in mremoteng_chrome.menu_items:
                menu = self.menuBar().addMenu(item.label)
                menu.setObjectName("mRemoteNgTopMenu")
                menu.setProperty("mRemoteNgTopMenuKey", item.key)
                menu.setProperty("mRemoteNgTopMenuLabel", item.label)
                menu.setProperty("mRemoteNgTopMenuPrimaryAction", item.primary_action)
                menu.setToolTip(item.tooltip)
                menu.menuAction().setProperty("mRemoteNgTopMenuKey", item.key)
                menu.menuAction().setProperty("mRemoteNgTopMenuLabel", item.label)
                menu.menuAction().setProperty("mRemoteNgTopMenuPrimaryAction", item.primary_action)
                menu.menuAction().setToolTip(item.tooltip)
                self.mremoteng_top_menus.append(menu)
                self.mremoteng_top_menu_actions.append(menu.menuAction())
                if item.key in {"file", "connections"}:
                    menu.addAction(item.primary_action, lambda _checked=False: self.connect_selected(False))
                elif item.key == "view":
                    menu.addAction(item.primary_action, self.refresh_profiles)
                elif item.key == "tools":
                    menu.addAction(item.primary_action, self.show_doctor)
                elif item.key == "window":
                    menu.addAction(item.primary_action, lambda _checked=False: self.add_split("horizontal"))
                elif item.key == "help":
                    menu.addAction(item.primary_action, self.show_doctor)
                else:
                    menu.addAction(item.primary_action)

        def populate_view_design_menu(self) -> None:
            design_menu = self.view_menu.addMenu("Design preset")
            for preset in GUI_DESIGN_PRESETS:
                design_menu.addAction(
                    preset.label,
                    lambda _checked=False, preset_id=preset.id: self.set_design_preset(preset_id),
                )

        def set_design_preset(self, preset_id: str) -> None:
            index = self.design_select.findData(preset_id)
            if index >= 0:
                self.design_select.setCurrentIndex(index)

        def toolbar_button(self, label: str, icon_name: str, tooltip: str) -> QToolButton:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tooltip)
            button.setIcon(self.style().standardIcon(self.standard_icon(icon_name)))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setAutoRaise(False)
            return button

        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_moba_ribbon_icon(painter, icon_key, QColor(fill), size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_moba_ribbon_icon(self, painter: QPainter, icon_key: str, fill: QColor, size: int) -> None:
            white = QColor("#ffffff")
            dark = QColor("#101010")
            green = QColor("#42d66b")
            blue = QColor("#4da3ff")
            cyan = QColor("#26d0d4")
            red = QColor("#ff614f")
            yellow = QColor("#f7d63f")
            mid = size // 2

            def pen(color: QColor, width: int = 1) -> None:
                painter.setPen(QPen(color, width))

            def brush(color: QColor) -> None:
                painter.setBrush(QBrush(color))

            brush(fill)
            pen(fill)
            painter.drawRoundedRect(2, 2, size - 4, size - 4, 4, 4)

            if icon_key == "session":
                brush(dark)
                pen(white, 2)
                painter.drawRect(8, 7, size - 16, size - 13)
                brush(green)
                pen(green)
                painter.drawRect(11, 11, 6, 4)
                brush(white)
                painter.drawRect(11, size - 6, size - 22, 2)
            elif icon_key == "servers":
                pen(white, 2)
                painter.drawLine(mid, 7, 8, size - 8)
                painter.drawLine(mid, 7, size - 8, size - 8)
                painter.drawLine(8, size - 8, size - 8, size - 8)
                brush(cyan)
                for x, y in [(mid, 7), (8, size - 8), (size - 8, size - 8)]:
                    painter.drawEllipse(x - 4, y - 4, 8, 8)
            elif icon_key == "tools":
                pen(white, 4)
                painter.drawLine(10, 8, size - 8, size - 10)
                brush(red)
                pen(red)
                painter.drawRect(size - 12, 5, 6, 8)
                brush(yellow)
                painter.drawRect(6, size - 12, 9, 5)
            elif icon_key == "games":
                brush(white)
                pen(dark)
                painter.drawRoundedRect(5, 13, size - 10, 13, 6, 6)
                pen(dark, 2)
                painter.drawLine(10, 19, 17, 19)
                painter.drawLine(13, 16, 13, 22)
                brush(red)
                painter.drawEllipse(size - 14, 16, 5, 5)
                brush(blue)
                painter.drawEllipse(size - 9, 20, 5, 5)
            elif icon_key == "sessions":
                brush(yellow)
                pen(dark)
                painter.drawLine(mid, 4, mid + 4, 12)
                painter.drawLine(mid + 4, 12, size - 5, 12)
                painter.drawLine(size - 5, 12, mid + 6, 18)
                painter.drawLine(mid + 6, 18, mid + 9, size - 5)
                painter.drawLine(mid + 9, size - 5, mid, 21)
                painter.drawLine(mid, 21, 7, size - 5)
                painter.drawLine(7, size - 5, mid - 6, 18)
                painter.drawLine(mid - 6, 18, 5, 12)
                painter.drawLine(5, 12, mid - 4, 12)
                painter.drawLine(mid - 4, 12, mid, 4)
            elif icon_key in {"view", "split"}:
                brush(blue if icon_key == "view" else cyan)
                pen(white, 2)
                painter.drawRect(7, 7, size - 14, size - 14)
                painter.drawLine(7, mid, size - 7, mid)
                painter.drawLine(mid, 7, mid, size - 7)
            elif icon_key == "multiexec":
                pen(white, 3)
                painter.drawLine(mid, 6, mid, size - 8)
                pen(white, 2)
                painter.drawLine(mid, 13, 8, size - 8)
                painter.drawLine(mid, 13, size - 8, size - 8)
                brush(blue)
                pen(blue)
                for x, y in [(mid, 6), (8, size - 8), (size - 8, size - 8)]:
                    painter.drawEllipse(x - 3, y - 3, 6, 6)
            elif icon_key == "tunneling":
                pen(white, 4)
                painter.drawLine(7, 13, size - 7, 13)
                painter.drawLine(10, 21, size - 10, 21)
                brush(green)
                pen(green)
                painter.drawRect(6, 10, 6, 6)
                painter.drawRect(size - 12, 10, 6, 6)
            elif icon_key == "packages":
                brush(white)
                pen(dark)
                painter.drawRect(8, 8, size - 16, size - 16)
                pen(blue, 2)
                painter.drawLine(8, 14, mid, 8)
                painter.drawLine(mid, 8, size - 8, 14)
                painter.drawLine(mid, 8, mid, size - 8)
            elif icon_key == "settings":
                brush(fill)
                pen(white, 3)
                painter.drawEllipse(8, 8, size - 16, size - 16)
                for dx, dy in [(0, -9), (0, 9), (-9, 0), (9, 0)]:
                    painter.drawLine(mid, mid, mid + dx, mid + dy)
                brush(yellow)
                pen(yellow)
                painter.drawEllipse(mid - 3, mid - 3, 6, 6)
            elif icon_key == "help":
                brush(blue)
                pen(white, 2)
                painter.drawEllipse(6, 5, size - 12, size - 10)
                pen(white, 2)
                painter.drawText(12, 23, "?")
            elif icon_key == "xserver":
                pen(green, 4)
                painter.drawLine(7, 7, size - 7, size - 7)
                pen(blue, 4)
                painter.drawLine(size - 7, 7, 7, size - 7)
                pen(red, 2)
                painter.drawLine(mid, 6, mid, size - 6)
            elif icon_key == "exit":
                brush(QColor("#e2473f"))
                pen(QColor("#e2473f"))
                painter.drawEllipse(3, 3, size - 6, size - 6)
                pen(white, 3)
                painter.drawLine(mid, 8, mid, mid + 2)
                painter.drawArc(8, 8, size - 16, size - 16, 35 * 16, 290 * 16)
            elif icon_key == "home":
                brush(QColor("#f5f5f5"))
                pen(QColor("#d7d7d7"))
                painter.drawLine(mid, 5, size - 6, 13)
                painter.drawLine(mid, 5, 6, 13)
                painter.drawRect(9, 13, size - 18, size - 20)
                brush(red)
                pen(red)
                painter.drawRect(mid - 2, size - 14, 5, 7)
            elif icon_key == "terminal-key":
                brush(QColor("#2b2b2b"))
                pen(QColor("#d6a72d"), 2)
                painter.drawRect(5, 5, size - 10, size - 10)
                pen(yellow, 2)
                painter.drawLine(9, 12, mid, 12)
                painter.drawLine(mid, 12, size - 10, size - 8)
                brush(yellow)
                painter.drawRect(8, size - 12, 6, 4)
            elif icon_key == "plus":
                brush(QColor("#303030"))
                pen(QColor("#9ca3af"), 2)
                painter.drawRoundedRect(4, 4, size - 8, size - 8, 3, 3)
                painter.drawLine(mid, 8, mid, size - 8)
                painter.drawLine(8, mid, size - 8, mid)

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
            slots = {
                "session": self.create_profile,
                "servers": self.refresh_profiles,
                "tools": self.edit_selected_profile,
                "games": self.show_moba_tools_status,
                "sessions": lambda _checked=False: self.connect_selected(False),
                "view": self.cycle_design_preset,
                "split": lambda _checked=False: self.add_split("horizontal"),
                "multiexec": lambda _checked=False: self.connect_selected(True),
                "tunneling": self.show_moba_tunneling_status,
                "packages": self.show_moba_packages_dialog,
                "settings": self.edit_selected_profile,
                "help": self.show_moba_help_dialog,
            }
            tooltips = gui_design_moba_ribbon_tooltips()
            buttons: list[QToolButton] = []
            for action in gui_design_moba_ribbon_actions():
                button = self.toolbar_button(action.label, "SP_FileIcon", tooltips[action.icon_key])
                button.setObjectName("mobaRibbonButton")
                button.setProperty("mobaIconKey", action.icon_key)
                button.setIcon(self.moba_ribbon_icon(action.icon_key, action.color))
                self.apply_moba_ribbon_action_geometry(button, action.icon_key)
                button.clicked.connect(slots[action.icon_key])
                buttons.append(button)
            return buttons

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
                layout.addWidget(button)
                self.moba_rail_buttons.append(button)
                if item.label:
                    layout.addWidget(MobaRailLabel(item.label, item.role))
            self.set_moba_rail_active("sessions")
            layout.addStretch(1)
            return rail

        def create_left_panel(self) -> QWidget:
            frame = gui_design_moba_connected_dock_frame()
            panel = QWidget()
            panel.setObjectName("leftPanel")
            panel.setProperty("mobaConnectedDockSideWidth", frame.side_width)
            panel.setProperty("mobaConnectedDockRailWidth", frame.rail_width)
            panel.setProperty("mobaConnectedDockWidth", frame.dock_width)
            panel.setMinimumWidth(frame.side_width)
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
            return panel

        def show_moba_profile_tree(self) -> None:
            if not hasattr(self, "moba_left_stack"):
                return
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

        def configure_toolbar_copy_for_design(self, preset: GuiDesignPreset) -> None:
            actions = gui_design_toolbar_actions(preset.id)
            securecrt_toolbar_actions = {
                action.key: action for action in gui_design_securecrt_top_chrome().toolbar_actions
            }
            mremoteng_toolbar_actions = {
                action.key: action for action in gui_design_mremoteng_top_chrome().toolbar_actions
            }
            remmina_transfer_route = (
                gui_design_remmina_sftp_transfer_route() if preset.id == "remmina" else None
            )
            for button, (key, label, tooltip) in zip(self.product_toolbar_buttons, actions, strict=False):
                button.setObjectName("productToolbarButton")
                button.setText(label)
                button.setToolTip(tooltip)
                button.setProperty("productToolbarKey", key)
                button.setProperty("productToolbarLabel", label)
                button.setProperty("productToolbarTooltip", tooltip)
                securecrt_action = securecrt_toolbar_actions.get(key) if preset.id == "securecrt" else None
                mremoteng_action = mremoteng_toolbar_actions.get(key) if preset.id == "mremoteng" else None
                button.setProperty("secureCrtTopToolbarKey", securecrt_action.key if securecrt_action else "")
                button.setProperty("secureCrtTopToolbarLabel", securecrt_action.label if securecrt_action else "")
                button.setProperty("secureCrtTopToolbarIconKey", securecrt_action.icon_key if securecrt_action else "")
                button.setProperty("secureCrtTopToolbarStaticX", securecrt_action.static_x if securecrt_action else 0)
                button.setProperty("secureCrtTopToolbarStaticWidth", securecrt_action.static_width if securecrt_action else 0)
                button.setProperty("mRemoteNgTopToolbarKey", mremoteng_action.key if mremoteng_action else "")
                button.setProperty("mRemoteNgTopToolbarLabel", mremoteng_action.label if mremoteng_action else "")
                button.setProperty("mRemoteNgTopToolbarIconKey", mremoteng_action.icon_key if mremoteng_action else "")
                button.setProperty("mRemoteNgTopToolbarStaticX", mremoteng_action.static_x if mremoteng_action else 0)
                button.setProperty("mRemoteNgTopToolbarStaticWidth", mremoteng_action.static_width if mremoteng_action else 0)
                is_remmina_transfer = (
                    remmina_transfer_route is not None and key == remmina_transfer_route.toolbar_action_key
                )
                button.setProperty(
                    "remminaSftpTransferRouteKey",
                    remmina_transfer_route.key if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteRole",
                    remmina_transfer_route.route_role if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteToolbarActionKey",
                    remmina_transfer_route.toolbar_action_key if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteToolbarActionLabel",
                    remmina_transfer_route.toolbar_action_label if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteToolbarActionObject",
                    remmina_transfer_route.toolbar_action_object if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteSelectedProfileKey",
                    remmina_transfer_route.selected_profile_key if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteSelectedProfile",
                    remmina_transfer_route.selected_profile_name if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteProtocol",
                    remmina_transfer_route.selected_profile_protocol if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteStatus",
                    remmina_transfer_route.selected_profile_status if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteActiveTab",
                    remmina_transfer_route.active_tab_label if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRoutePath",
                    remmina_transfer_route.remote_path if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteQueueState",
                    remmina_transfer_route.transfer_status if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteQueueLabel",
                    remmina_transfer_route.transfer_queue_label if is_remmina_transfer else "",
                )
                button.setProperty(
                    "remminaSftpTransferRouteRenderSource",
                    remmina_transfer_route.render_source if is_remmina_transfer else "",
                )
                if remmina_transfer_route is not None:
                    button.setProperty(
                        remmina_transfer_route.toolbar_active_property,
                        "true" if is_remmina_transfer else "false",
                    )
                button.setMinimumWidth(
                    securecrt_action.static_width
                    if securecrt_action
                    else mremoteng_action.static_width
                    if mremoteng_action
                    else 0
                )
                button.setEnabled(True)

        def configure_menu_bar_for_design(self, preset: GuiDesignPreset) -> None:
            is_moba = preset.id == "mobaxterm"
            is_securecrt = preset.id == "securecrt"
            is_mremoteng = preset.id == "mremoteng"
            securecrt_chrome = gui_design_securecrt_top_chrome()
            mremoteng_chrome = gui_design_mremoteng_top_chrome()
            menu_bar = self.menuBar()
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

        def configure_interaction_states_for_design(self, preset: GuiDesignPreset) -> None:
            state = gui_design_interaction_state(preset.id)
            actions = gui_design_toolbar_actions(preset.id)
            for button, (key, _label, _tooltip) in zip(self.product_toolbar_buttons, actions, strict=False):
                self.set_interaction_state(button, self.toolbar_interaction_state(key, state))

            for button in getattr(self, "moba_ribbon_buttons", []):
                key = button.text().strip().lower().replace(" ", "-")
                self.set_interaction_state(button, self.toolbar_interaction_state(key, state))
            for button in [self.moba_x_server_button, self.moba_exit_button]:
                self.set_interaction_state(button, "normal")

            focus_widgets = {
                "quick-connect": self.quick_connect,
                "search-log": self.search_input,
                "session-filter": self.securecrt_session_filter,
                "host-search": self.termius_host_search,
                "profile-filter": self.remmina_profile_filter,
                "tree-filter": getattr(self, "mremoteng_document_filter", self.search_input),
            }
            for key, widget in focus_widgets.items():
                self.set_interaction_state(widget, "focused" if key == state.focused_control else "normal")
                if key == state.focused_control:
                    widget.setToolTip(f"{preset.label}: {state.status_note}")
            self.set_interaction_state(
                self.moba_quick_connect_chrome,
                "focused" if preset.id == "mobaxterm" and state.focused_control == "quick-connect" else "normal",
            )
            self.select_profile_tree_label(state.selected_tree_label)
            self.statusBar().showMessage(f"{preset.label}: {state.status_note}")
            focus_interaction_route = (
                gui_design_preset_focus_interaction_route(preset.id)
                if preset.id in PRODUCT_GUI_PRESET_IDS
                else None
            )
            self.apply_focus_interaction_route_for_design(focus_interaction_route, preset.id)

        def focus_interaction_widgets(self) -> dict[str, object]:
            return {
                "quick-connect": self.quick_connect,
                "search-log": self.search_input,
                "session-filter": self.securecrt_session_filter,
                "host-search": self.termius_host_search,
                "profile-filter": self.remmina_profile_filter,
                "tree-filter": getattr(self, "mremoteng_document_filter", self.search_input),
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
            widget.style().unpolish(widget)
            widget.style().polish(widget)
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
                    self.apply_preset_selection_route_properties(label, selection_route)
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
                self.apply_preset_selection_route_properties(label, selection_route)

        def show_moba_connected_dock(self, state: MobaConnectedSessionState) -> None:
            if not hasattr(self, "moba_left_stack"):
                return
            if self.moba_connected_dock is not None:
                self.moba_left_stack.removeWidget(self.moba_connected_dock)
                self.moba_connected_dock.deleteLater()
            self.moba_connected_dock = MobaSftpDock(state)
            self.moba_left_stack.addWidget(self.moba_connected_dock)
            self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
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
            self.menuBar().setProperty("mobaTopStackMenuY", stack.menu_y)
            self.menuBar().setProperty("mobaTopStackMenuHeight", stack.menu_height)
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
            state = getattr(widget, "moba_connected_state", None)
            if isinstance(state, MobaConnectedSessionState):
                self.show_moba_connected_dock(state)
            else:
                self.show_moba_profile_tree()

        def refresh_profiles(self) -> None:
            selected_name = self.selected_profile_name()
            self.profile_list.clear()
            profiles = sorted(self.store.load(), key=lambda item: (item.group, item.name))
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
            root_label, root_tooltip = gui_design_tree_root_copy(self.current_design_id())
            root = QTreeWidgetItem([root_label])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            self.apply_profile_tree_icon(root, gui_design_tree_root_icon(self.current_design_id()))
            self.apply_moba_profile_tree_geometry(root, "root")
            root.setToolTip(0, root_tooltip)
            self.profile_list.addTopLevelItem(root)
            group_nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
            for profile in profiles:
                parent = root
                path: list[str] = []
                for part in self.profile_group_parts(profile):
                    path.append(part)
                    key = tuple(path)
                    if key not in group_nodes:
                        group_item = QTreeWidgetItem([self.profile_group_label(part)])
                        group_item.setData(0, Qt.ItemDataRole.UserRole, None)
                        group_icon = gui_design_tree_row_icon(self.current_design_id(), part, "", True)
                        self.apply_profile_tree_icon(group_item, group_icon)
                        self.apply_moba_profile_tree_geometry(group_item, "group")
                        group_item.setToolTip(0, self.profile_group_tooltip(path))
                        parent.addChild(group_item)
                        group_nodes[key] = group_item
                    parent = group_nodes[key]
                item = QTreeWidgetItem([self.profile_tree_label(profile)])
                item.setData(0, Qt.ItemDataRole.UserRole, profile.name)
                profile_icon = gui_design_tree_row_icon(
                    self.current_design_id(),
                    self.profile_tree_label(profile),
                    self.profile_tree_tooltip(profile),
                    False,
                )
                self.apply_profile_tree_icon(item, profile_icon, protocol=profile.protocol)
                self.apply_moba_profile_tree_geometry(item, "profile")
                tooltip = self.profile_tree_tooltip(profile)
                if mremoteng_route is not None:
                    routed = profile.name == mremoteng_route.selected_profile_name
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
                    filter_routed = profile.name == mremoteng_filter_route.selected_profile_name
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
                    routed = profile.name == securecrt_route.selected_profile_name
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
                    filter_routed = profile.name == securecrt_filter_route.selected_profile_name
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
                    sftp_routed = profile.name == securecrt_sftp_route.selected_profile_name
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
                    routed = profile.name == termius_host_route.selected_profile_name
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
                item.setToolTip(0, tooltip)
                parent.addChild(item)
            self.profile_list.expandAll()
            if hasattr(self, "securecrt_session_filter"):
                self.filter_profile_tree(self.securecrt_session_filter.text())
            if self.current_design_id() == "mremoteng" and hasattr(self, "mremoteng_document_filter"):
                self.filter_profile_tree(self.mremoteng_document_filter.text())
            if selected_name:
                self.select_profile(selected_name)
            self.refresh_layouts()

        def profile_group_parts(self, profile_or_group) -> list[str]:
            if isinstance(profile_or_group, Profile):
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
                group = profile_or_group.group
            else:
                group = str(profile_or_group)
            parts = [part.strip() for part in group.replace("\\", "/").split("/") if part.strip()]
            return parts or ["default"]

        def current_design_id(self) -> str:
            return str(self.design_select.currentData() or "native")

        def profile_group_label(self, part: str) -> str:
            design_id = self.current_design_id()
            if design_id == "securecrt":
                return f"Folder: {part}"
            if design_id == "termius":
                return f"Vault / {part}"
            if design_id == "remmina":
                return f"Group: {part}"
            if design_id == "mremoteng":
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

        def profile_tree_label(self, profile) -> str:
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
                return f"{protocol} - {profile.name}"
            if design_id == "mremoteng":
                return f"{profile.name} [{protocol}]"
            return f"[{protocol}] {profile.name}  {target}" if target else f"[{protocol}] {profile.name}"

        def profile_tab_label(self, profile: Profile) -> str:
            design_id = self.current_design_id()
            protocol = profile.protocol.upper()
            if design_id == "securecrt":
                protocol = "SSH2" if protocol == "SSH" else protocol
                return f"{profile.name} ({protocol})"
            if design_id == "remmina":
                return f"{protocol} - {profile.name}"
            if design_id == "mremoteng":
                return f"{profile.name} [{protocol}]"
            if design_id == "mobaxterm" and profile.protocol.lower() in {"ssh", "sftp"}:
                return moba_connected_profile_label(profile)
            return profile.name

        def profile_tree_tooltip(self, profile) -> str:
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

        def apply_profile_tree_icon(self, item: QTreeWidgetItem, row_icon, *, protocol: str = "") -> None:
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
            if row_icon.row_kind in {"root", "group"}:
                icon_name = "SP_DirHomeIcon" if row_icon.row_kind == "root" else "SP_DirIcon"
                item.setIcon(0, self.style().standardIcon(self.standard_icon(icon_name)))
                return
            item.setIcon(0, self.profile_icon_for_protocol(protocol))

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
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_profile_tree_generated_icon(painter, icon_key, group=group, size=size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_profile_tree_generated_icon(self, painter: QPainter, icon_key: str, *, group: bool, size: int) -> None:
            fill = QColor("#f4c430" if group else "#35d7c7")
            outline = QColor("#d7dde5")
            dark = QColor("#151515")
            muted = QColor("#7d8792")
            painter.setPen(QPen(outline, 1))
            painter.setBrush(QBrush(fill if group else Qt.BrushStyle.NoBrush))
            if icon_key == "folder":
                painter.drawRect(1, 5, size - 2, size - 6)
                painter.drawRect(3, 3, max(5, size // 2), 4)
                return
            if icon_key == "database":
                painter.setBrush(QBrush(fill))
                painter.drawEllipse(1, 1, size - 2, max(5, size // 3))
                painter.drawRect(1, size // 4, size - 2, max(5, size - 7))
                painter.drawEllipse(1, size - 7, size - 2, 5)
                return
            if icon_key == "sftp":
                painter.setBrush(QBrush(fill))
                painter.drawRect(2, 5, size - 4, size - 6)
                painter.drawRect(3, 3, max(5, size // 2), 4)
                painter.setPen(QPen(dark, 1))
                painter.drawLine(4, size - 5, size - 4, size - 5)
                painter.drawLine(size - 6, size - 7, size - 3, size - 5)
                painter.drawLine(size - 6, size - 3, size - 3, size - 5)
                return
            if icon_key == "pin":
                painter.setPen(QPen(fill, 1))
                painter.setBrush(QBrush(fill))
                painter.drawPolygon(
                    [
                        QPoint(size // 2, 1),
                        QPoint(size - 2, size // 2),
                        QPoint(size // 2 + 2, size // 2 + 2),
                        QPoint(size // 2, size - 1),
                        QPoint(size // 2 - 2, size // 2 + 2),
                        QPoint(2, size // 2),
                    ]
                )
                return
            if icon_key in {"shell", "command", "ssh", "ssh2", "host"}:
                painter.setPen(QPen(fill, 1))
                painter.setBrush(QBrush(dark))
                painter.drawRect(1, 2, size - 2, size - 3)
                painter.drawLine(4, 6, 7, size // 2)
                painter.drawLine(7, size // 2, 4, size - 5)
                painter.drawLine(9, size - 5, size - 3, size - 5)
                if icon_key == "ssh2":
                    painter.setPen(QPen(outline, 1))
                    painter.drawText(size - 6, 8, "2")
                elif icon_key == "command":
                    painter.setPen(QPen(muted, 1))
                    painter.drawRect(size - 6, 4, 3, 3)
                return
            if icon_key in {"rdp", "vnc"}:
                painter.setPen(QPen(fill, 1))
                painter.setBrush(QBrush(dark if icon_key == "vnc" else QColor("#d8e6f3")))
                painter.drawRect(1, 2, size - 2, size - 5)
                painter.drawRect(4, size - 3, size - 8, 2)
                if icon_key == "vnc":
                    painter.drawLine(4, 5, size - 4, size - 5)
                    painter.drawLine(size - 4, 5, 4, size - 5)
                return
            if icon_key == "snippet":
                painter.setPen(QPen(fill, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(3, 1, size - 6, size - 2)
                painter.drawLine(5, 5, size - 5, 5)
                painter.drawLine(5, 8, size - 5, 8)
                painter.drawLine(5, 11, size - 7, 11)
                return
            painter.setPen(QPen(fill, 1))
            painter.drawRect(2, 2, size - 4, size - 4)

        def profile_icon_for_protocol(self, protocol: str):
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
            return self.style().standardIcon(self.standard_icon(icon_name))

        def refresh_layouts(self) -> None:
            self.layout_select.clear()
            for layout in self.layout_store.load():
                self.layout_select.addItem(layout.name)

        def apply_selected_design(self, *_args) -> None:
            preset_id = self.design_select.currentData() or "native"
            try:
                preset = get_gui_design_preset(str(preset_id))
            except ValueError:
                preset = get_gui_design_preset("native")
            catalog_route = gui_design_preset_catalog_route()
            isolation_route = gui_design_preset_isolation_route(preset.id)
            selection_route = gui_design_preset_selection_route(preset.id)
            transition_route = gui_design_preset_transition_route(preset.id)
            visual_signature = gui_design_preset_visual_signature(preset.id)
            keyboard_shortcut_route = (
                gui_design_preset_keyboard_shortcut_route(preset.id)
                if preset.id in PRODUCT_GUI_PRESET_IDS
                else None
            )
            command_surface_route = (
                gui_design_preset_command_surface_route(preset.id)
                if preset.id in PRODUCT_GUI_PRESET_IDS
                else None
            )
            home_search_route = (
                gui_design_preset_home_search_route(preset.id)
                if preset.id in PRODUCT_GUI_PRESET_IDS
                else None
            )
            reference_tab_route = (
                gui_design_preset_reference_tab_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_tab_chrome_route = (
                gui_design_preset_reference_tab_chrome_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_status_route = (
                gui_design_preset_reference_status_bar_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_session_action_route = (
                gui_design_preset_reference_session_action_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_surface_route = (
                gui_design_preset_reference_surface_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_control_route = (
                gui_design_preset_reference_control_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_input_route = (
                gui_design_preset_reference_input_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            reference_transcript_route = (
                gui_design_preset_reference_transcript_route(preset.id)
                if preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
                else None
            )
            is_moba = preset.id == "mobaxterm"
            self.setStyleSheet(preset.stylesheet)
            for widget in (self, self.design_select, self.main_toolbar):
                self.apply_preset_catalog_route_properties(widget, catalog_route)
                self.apply_preset_isolation_route_properties(widget, isolation_route)
                self.apply_preset_transition_route_properties(widget, transition_route)
            self.apply_keyboard_shortcut_route_for_design(keyboard_shortcut_route)
            for widget in (self, self.tabs):
                if reference_tab_route is None:
                    self.clear_preset_reference_tab_route_properties(widget)
                    self.clear_preset_reference_tab_chrome_route_properties(widget)
                    self.clear_preset_reference_status_bar_route_properties(widget)
                    self.clear_preset_reference_session_action_route_properties(widget)
                    self.clear_preset_reference_surface_route_properties(widget)
                    self.clear_preset_reference_control_route_properties(widget)
                    self.clear_preset_reference_input_route_properties(widget)
                    self.clear_preset_reference_transcript_route_properties(widget)
                else:
                    self.apply_preset_reference_tab_route_properties(widget, reference_tab_route)
                    self.apply_preset_reference_tab_chrome_route_properties(widget, reference_tab_chrome_route)
                    self.apply_preset_reference_status_bar_route_properties(widget, reference_status_route)
                    self.apply_preset_reference_session_action_route_properties(widget, reference_session_action_route)
                    self.apply_preset_reference_surface_route_properties(widget, reference_surface_route)
                    self.apply_preset_reference_control_route_properties(widget, reference_control_route)
                    self.apply_preset_reference_input_route_properties(widget, reference_input_route)
                    self.apply_preset_reference_transcript_route_properties(widget, reference_transcript_route)
            for widget in (
                self,
                self.main_toolbar,
                self.layout_toolbar,
                self.left_panel,
                self.profile_list,
                self.tabs,
                self.log,
                self.statusBar(),
            ):
                self.apply_preset_visual_signature_properties(widget, visual_signature)
            self.apply_preset_selection_route_properties(self, selection_route)
            for widget in (
                self.design_select,
                self.main_toolbar,
                self.layout_toolbar,
                self.left_panel_header,
                self.profile_list,
                self.tabs,
                self.statusBar(),
            ):
                self.apply_preset_selection_route_properties(widget, selection_route)
            self.configure_menu_bar_for_design(preset)
            self.moba_quick_connect_chrome.setVisible(is_moba)
            self.quick_connect.setVisible(is_moba)
            self.configure_left_panel_header_for_design(preset, is_moba)
            self.remmina_profile_list_chrome.setVisible(preset.id == "remmina")
            self.moba_rail.setVisible(is_moba)
            self.update_quick_connect_suggestions()
            self.layout_toolbar.setVisible(not is_moba)
            self.log.setVisible(not is_moba)
            self.refresh_profiles()
            self.main_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
            self.layout_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
            self.configure_toolbar_copy_for_design(preset)
            self.configure_status_bar_for_design(preset)
            for widget in (self.statusBar(), self.status_notice_label, *self.status_segment_labels):
                if reference_status_route is None:
                    self.clear_preset_reference_status_bar_route_properties(widget)
                else:
                    self.apply_preset_reference_status_bar_route_properties(widget, reference_status_route)
            if reference_session_action_route is None:
                self.clear_preset_reference_session_action_route_properties(self.tabs.tabBar())
            else:
                self.apply_preset_reference_session_action_route_properties(
                    self.tabs.tabBar(),
                    reference_session_action_route,
                )
            self.configure_toolbar_for_design(preset, is_moba, preset.toolbar_icon_size)
            if is_moba:
                self.apply_moba_top_stack_geometry()
            self.configure_interaction_states_for_design(preset)
            self.apply_command_surface_route_for_design(command_surface_route)
            moba_frame = gui_design_moba_connected_dock_frame()
            profile_width = moba_frame.side_width if is_moba else preset.profile_width
            self.left_panel.setMinimumWidth(min(profile_width, 430))
            self.configure_profile_tree_for_design(is_moba, preset.list_spacing)
            self.root_splitter.setSizes([profile_width, max(620, self.width() - profile_width)])
            if is_moba:
                self.workspace.setSizes([max(620, self.height()), 0])
            else:
                self.workspace.setSizes([max(420, self.height() - preset.log_height), preset.log_height])
            self.tabs.setTabPosition(self.tab_position_for_design(preset.tab_position))
            self.tabs.setDocumentMode(preset.document_mode)
            self.configure_workspace_tabs_for_design(is_moba)
            self.apply_home_search_route_for_design(home_search_route)
            self.refresh_moba_left_dock_for_current_tab()
            self.log.setPlaceholderText(
                f"{preset.description}\n\nLaunch output, dry-run commands and doctor reports appear here."
            )
            self.statusBar().showMessage(f"View: {preset.label}")

        @staticmethod
        def apply_preset_selection_route_properties(widget, route) -> None:
            properties = {
                "presetSelectionRouteKey": route.key,
                "presetSelectionRouteRole": route.route_role,
                "presetSelectionRoutePresetId": route.preset_id,
                "presetSelectionRoutePresetLabel": route.preset_label,
                "presetSelectionRoutePresetIndex": route.preset_index,
                "presetSelectionRouteSelectorObject": route.selector_object,
                "presetSelectionRouteMainToolbarObject": route.main_toolbar_object,
                "presetSelectionRouteLayoutToolbarObject": route.layout_toolbar_object,
                "presetSelectionRouteLeftPanelHeaderObject": route.left_panel_header_object,
                "presetSelectionRouteProfileTreeObject": route.profile_tree_object,
                "presetSelectionRouteTabsObject": route.tabs_object,
                "presetSelectionRouteStatusBarObject": route.status_bar_object,
                "presetSelectionRouteStatusSegmentObject": route.status_segment_object,
                "presetSelectionRouteWorkspaceSurfaceObject": route.workspace_surface_object,
                "presetSelectionRouteReferenceStateObject": route.reference_state_object,
                "presetSelectionRouteHomeTabLabel": route.home_tab_label,
                "presetSelectionRouteSidebarTitle": route.sidebar_title,
                "presetSelectionRouteSidebarSubtitle": route.sidebar_subtitle,
                "presetSelectionRouteStatusSegments": list(route.status_segments),
                "presetSelectionRouteTabPosition": route.tab_position,
                "presetSelectionRouteDocumentMode": route.document_mode,
                "presetSelectionRouteProfileWidth": route.profile_width,
                "presetSelectionRouteLogHeight": route.log_height,
                "presetSelectionRouteToolbarIconSize": route.toolbar_icon_size,
                "presetSelectionRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_preset_catalog_route_properties(widget, route) -> None:
            properties = {
                "presetCatalogRouteKey": route.key,
                "presetCatalogRouteRole": route.route_role,
                "presetCatalogRouteSelectorObject": route.selector_object,
                "presetCatalogRouteOptionIds": list(route.option_ids),
                "presetCatalogRouteOptionLabels": list(route.option_labels),
                "presetCatalogRouteProductPresetIds": list(route.product_preset_ids),
                "presetCatalogRouteProductPresetLabels": list(route.product_preset_labels),
                "presetCatalogRouteDefaultPresetId": route.default_preset_id,
                "presetCatalogRouteDefaultPresetLabel": route.default_preset_label,
                "presetCatalogRouteOptionCount": route.option_count,
                "presetCatalogRouteProductOptionCount": route.product_option_count,
                "presetCatalogRouteSelectorProperty": route.selector_property,
                "presetCatalogRouteOptionLabelsProperty": route.option_labels_property,
                "presetCatalogRouteProductIdsProperty": route.product_ids_property,
                "presetCatalogRouteDefaultProperty": route.default_property,
                "presetCatalogRouteRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_preset_isolation_route_properties(widget, route) -> None:
            properties = {
                "presetIsolationRouteKey": route.key,
                "presetIsolationRouteRole": route.route_role,
                "presetIsolationRoutePresetId": route.preset_id,
                "presetIsolationVisibleObjects": list(route.visible_objects),
                "presetIsolationHiddenObjects": list(route.hidden_objects),
                "presetIsolationVisibleProperty": route.visible_property,
                "presetIsolationHiddenProperty": route.hidden_property,
                "presetIsolationRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_preset_transition_route_properties(widget, route) -> None:
            properties = {
                "presetTransitionRouteKey": route.key,
                "presetTransitionRouteRole": route.route_role,
                "presetTransitionFromPresetIds": list(route.from_preset_ids),
                "presetTransitionToPresetId": route.to_preset_id,
                "presetTransitionToPresetIndex": route.to_preset_index,
                "presetTransitionSelectorObject": route.selector_object,
                "presetTransitionResetObjects": list(route.reset_objects),
                "presetTransitionRouteProperty": route.route_property,
                "presetTransitionFromProperty": route.from_property,
                "presetTransitionToProperty": route.to_property,
                "presetTransitionResetProperty": route.reset_property,
                "presetTransitionRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_preset_keyboard_shortcut_route_properties(widget, route) -> None:
            properties = {
                "presetKeyboardShortcutRouteKey": route.key,
                "presetKeyboardShortcutRouteRole": route.route_role,
                "presetKeyboardShortcutPresetId": route.preset_id,
                "presetKeyboardShortcutObject": route.shortcut_object,
                "presetKeyboardShortcutExpectedKeys": list(route.expected_shortcut_keys),
                "presetKeyboardShortcutExpectedSequences": list(route.expected_sequences),
                "presetKeyboardShortcutExpectedActionLabels": list(route.expected_action_labels),
                "presetKeyboardShortcutExpectedCount": route.expected_shortcut_count,
                "presetKeyboardShortcutKeyProperty": route.shortcut_key_property,
                "presetKeyboardShortcutSequenceProperty": route.shortcut_sequence_property,
                "presetKeyboardShortcutActionProperty": route.shortcut_action_property,
                "presetKeyboardShortcutCapturedProperty": route.captured_property,
                "presetKeyboardShortcutCapturedKeysProperty": route.captured_keys_property,
                "presetKeyboardShortcutCapturedSequencesProperty": route.captured_sequences_property,
                "presetKeyboardShortcutCapturedActionLabelsProperty": route.captured_action_labels_property,
                "presetKeyboardShortcutCapturedCountProperty": route.captured_count_property,
                "presetKeyboardShortcutRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_keyboard_shortcut_route_properties(widget) -> None:
            for key in (
                "presetKeyboardShortcutRouteKey",
                "presetKeyboardShortcutRouteRole",
                "presetKeyboardShortcutPresetId",
                "presetKeyboardShortcutObject",
                "presetKeyboardShortcutExpectedKeys",
                "presetKeyboardShortcutExpectedSequences",
                "presetKeyboardShortcutExpectedActionLabels",
                "presetKeyboardShortcutExpectedCount",
                "presetKeyboardShortcutKeyProperty",
                "presetKeyboardShortcutSequenceProperty",
                "presetKeyboardShortcutActionProperty",
                "presetKeyboardShortcutCapturedProperty",
                "presetKeyboardShortcutCapturedKeysProperty",
                "presetKeyboardShortcutCapturedSequencesProperty",
                "presetKeyboardShortcutCapturedActionLabelsProperty",
                "presetKeyboardShortcutCapturedCountProperty",
                "presetKeyboardShortcutsCaptured",
                "presetKeyboardShortcutCapturedKeys",
                "presetKeyboardShortcutCapturedSequences",
                "presetKeyboardShortcutCapturedActionLabels",
                "presetKeyboardShortcutCapturedCount",
                "presetKeyboardShortcutRenderSource",
            ):
                widget.setProperty(key, None)

        def apply_keyboard_shortcut_route_for_design(self, route) -> None:
            shortcuts = getattr(self, "keyboard_shortcuts", [])
            route_widgets = [self, *shortcuts]
            if route is None:
                for widget in route_widgets:
                    self.clear_preset_keyboard_shortcut_route_properties(widget)
                return
            keys = [str(shortcut.property(route.shortcut_key_property) or "") for shortcut in shortcuts]
            sequences = [str(shortcut.property(route.shortcut_sequence_property) or "") for shortcut in shortcuts]
            action_labels = [str(shortcut.property(route.shortcut_action_property) or "") for shortcut in shortcuts]
            for widget in route_widgets:
                self.apply_preset_keyboard_shortcut_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_keys_property, keys)
                widget.setProperty(route.captured_sequences_property, sequences)
                widget.setProperty(route.captured_action_labels_property, action_labels)
                widget.setProperty(route.captured_count_property, len(keys))

        @staticmethod
        def apply_preset_command_surface_route_properties(widget, route) -> None:
            properties = {
                "presetCommandSurfaceRouteKey": route.key,
                "presetCommandSurfaceRouteRole": route.route_role,
                "presetCommandSurfacePresetId": route.preset_id,
                "presetCommandSurfaceToolbarObject": route.toolbar_object,
                "presetCommandSurfaceCommandObject": route.command_object,
                "presetCommandSurfaceExpectedKeys": list(route.expected_action_keys),
                "presetCommandSurfaceExpectedLabels": list(route.expected_action_labels),
                "presetCommandSurfaceExpectedTooltips": list(route.expected_action_tooltips),
                "presetCommandSurfaceExpectedStates": dict(route.expected_action_states),
                "presetCommandSurfaceExpectedCount": route.expected_action_count,
                "presetCommandSurfaceKeyProperty": route.key_property,
                "presetCommandSurfaceLabelProperty": route.label_property,
                "presetCommandSurfaceTooltipProperty": route.tooltip_property,
                "presetCommandSurfaceStateProperty": route.state_property,
                "presetCommandSurfaceCapturedProperty": route.captured_property,
                "presetCommandSurfaceCapturedKeysProperty": route.captured_keys_property,
                "presetCommandSurfaceCapturedLabelsProperty": route.captured_labels_property,
                "presetCommandSurfaceCapturedTooltipsProperty": route.captured_tooltips_property,
                "presetCommandSurfaceCapturedStatesProperty": route.captured_states_property,
                "presetCommandSurfaceCapturedCountProperty": route.captured_count_property,
                "presetCommandSurfaceRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_command_surface_route_properties(widget) -> None:
            for key in (
                "presetCommandSurfaceRouteKey",
                "presetCommandSurfaceRouteRole",
                "presetCommandSurfacePresetId",
                "presetCommandSurfaceToolbarObject",
                "presetCommandSurfaceCommandObject",
                "presetCommandSurfaceExpectedKeys",
                "presetCommandSurfaceExpectedLabels",
                "presetCommandSurfaceExpectedTooltips",
                "presetCommandSurfaceExpectedStates",
                "presetCommandSurfaceExpectedCount",
                "presetCommandSurfaceKeyProperty",
                "presetCommandSurfaceLabelProperty",
                "presetCommandSurfaceTooltipProperty",
                "presetCommandSurfaceStateProperty",
                "presetCommandSurfaceCapturedProperty",
                "presetCommandSurfaceCapturedKeysProperty",
                "presetCommandSurfaceCapturedLabelsProperty",
                "presetCommandSurfaceCapturedTooltipsProperty",
                "presetCommandSurfaceCapturedStatesProperty",
                "presetCommandSurfaceCapturedCountProperty",
                "presetCommandSurfaceCaptured",
                "presetCommandSurfaceCapturedKeys",
                "presetCommandSurfaceCapturedLabels",
                "presetCommandSurfaceCapturedTooltips",
                "presetCommandSurfaceCapturedStates",
                "presetCommandSurfaceCapturedCount",
                "presetCommandSurfaceActionKey",
                "presetCommandSurfaceActionLabel",
                "presetCommandSurfaceActionTooltip",
                "presetCommandSurfaceRenderSource",
            ):
                widget.setProperty(key, None)

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
                self.clear_preset_command_surface_route_properties(widget)
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
                self.apply_preset_command_surface_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_keys_property, captured_keys)
                widget.setProperty(route.captured_labels_property, captured_labels)
                widget.setProperty(route.captured_tooltips_property, captured_tooltips)
                widget.setProperty(route.captured_states_property, captured_states)
                widget.setProperty(route.captured_count_property, len(captured_keys))

        @staticmethod
        def apply_preset_focus_interaction_route_properties(widget, route) -> None:
            properties = {
                "presetFocusInteractionRouteKey": route.key,
                "presetFocusInteractionRouteRole": route.route_role,
                "presetFocusInteractionPresetId": route.preset_id,
                "presetFocusInteractionFocusedControl": route.focused_control,
                "presetFocusInteractionFocusObject": route.focus_object,
                "presetFocusInteractionActiveToolbarKey": route.active_toolbar_key,
                "presetFocusInteractionCheckedToolbarKey": route.checked_toolbar_key,
                "presetFocusInteractionDisabledToolbarKey": route.disabled_toolbar_key,
                "presetFocusInteractionSelectedTreeLabel": route.selected_tree_label,
                "presetFocusInteractionActiveTabStatus": route.active_tab_status,
                "presetFocusInteractionStatusNote": route.status_note,
                "presetFocusInteractionStatusBarObject": route.status_bar_object,
                "presetFocusInteractionProfileTreeObject": route.profile_tree_object,
                "presetFocusInteractionFocusedStateProperty": route.focused_state_property,
                "presetFocusInteractionCapturedProperty": route.captured_property,
                "presetFocusInteractionCapturedFocusProperty": route.captured_focus_property,
                "presetFocusInteractionCapturedStateProperty": route.captured_focus_state_property,
                "presetFocusInteractionCapturedStatusMessageProperty": route.captured_status_message_property,
                "presetFocusInteractionCapturedSelectedTreeProperty": route.captured_selected_tree_property,
                "presetFocusInteractionCapturedToolbarStatesProperty": route.captured_toolbar_states_property,
                "presetFocusInteractionRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_focus_interaction_route_properties(widget) -> None:
            for key in (
                "presetFocusInteractionRouteKey",
                "presetFocusInteractionRouteRole",
                "presetFocusInteractionPresetId",
                "presetFocusInteractionFocusedControl",
                "presetFocusInteractionFocusObject",
                "presetFocusInteractionActiveToolbarKey",
                "presetFocusInteractionCheckedToolbarKey",
                "presetFocusInteractionDisabledToolbarKey",
                "presetFocusInteractionSelectedTreeLabel",
                "presetFocusInteractionActiveTabStatus",
                "presetFocusInteractionStatusNote",
                "presetFocusInteractionStatusBarObject",
                "presetFocusInteractionProfileTreeObject",
                "presetFocusInteractionFocusedStateProperty",
                "presetFocusInteractionCapturedProperty",
                "presetFocusInteractionCapturedFocusProperty",
                "presetFocusInteractionCapturedStateProperty",
                "presetFocusInteractionCapturedStatusMessageProperty",
                "presetFocusInteractionCapturedSelectedTreeProperty",
                "presetFocusInteractionCapturedToolbarStatesProperty",
                "presetFocusInteractionCaptured",
                "presetFocusInteractionCapturedFocus",
                "presetFocusInteractionCapturedState",
                "presetFocusInteractionStatusMessage",
                "presetFocusInteractionCapturedSelectedTreeLabel",
                "presetFocusInteractionToolbarStates",
                "presetFocusInteractionRenderSource",
            ):
                widget.setProperty(key, None)

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
                self.clear_preset_focus_interaction_route_properties(widget)
            if route is None:
                return
            focused_widget = focus_widgets.get(route.focused_control)
            if focused_widget is not None and focused_widget not in route_widgets:
                route_widgets.append(focused_widget)
            toolbar_states = self.captured_toolbar_interaction_states(preset_id)
            captured_focus_state = (
                str(focused_widget.property(route.focused_state_property) or "")
                if focused_widget is not None
                else ""
            )
            captured_status_message = self.statusBar().currentMessage()
            captured_selected_tree_label = self.selected_profile_tree_label()
            for widget in route_widgets:
                self.apply_preset_focus_interaction_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_focus_property, route.focus_object)
                widget.setProperty(route.captured_focus_state_property, captured_focus_state)
                widget.setProperty(route.captured_status_message_property, captured_status_message)
                widget.setProperty(route.captured_selected_tree_property, captured_selected_tree_label)
                widget.setProperty(route.captured_toolbar_states_property, toolbar_states)

        @staticmethod
        def apply_preset_home_search_route_properties(widget, route) -> None:
            properties = {
                "presetHomeSearchRouteKey": route.key,
                "presetHomeSearchRouteRole": route.route_role,
                "presetHomeSearchPresetId": route.preset_id,
                "presetHomeSearchHomeTabLabel": route.home_tab_label,
                "presetHomeSearchObject": route.home_search_object,
                "presetHomeSearchEntryControl": route.entry_search_control,
                "presetHomeSearchEntryObject": route.entry_search_object,
                "presetHomeSearchContainerObject": route.container_object,
                "presetHomeSearchRecentLabelObject": route.recent_label_object,
                "presetHomeSearchExpectedPlaceholder": route.placeholder_text,
                "presetHomeSearchExpectedEntryPlaceholder": route.entry_placeholder_text,
                "presetHomeSearchExpectedActions": list(route.expected_home_actions),
                "presetHomeSearchExpectedRecentLabels": list(route.expected_recent_labels),
                "presetHomeSearchExpectedRecentCount": route.expected_recent_count,
                "presetHomeSearchPlaceholderProperty": route.placeholder_property,
                "presetHomeSearchEntryPlaceholderProperty": route.entry_placeholder_property,
                "presetHomeSearchCapturedProperty": route.captured_property,
                "presetHomeSearchCapturedPlaceholderProperty": route.captured_placeholder_property,
                "presetHomeSearchCapturedEntryPlaceholderProperty": route.captured_entry_placeholder_property,
                "presetHomeSearchCapturedTextProperty": route.captured_text_property,
                "presetHomeSearchCapturedEntryTextProperty": route.captured_entry_text_property,
                "presetHomeSearchCapturedActionsProperty": route.captured_actions_property,
                "presetHomeSearchCapturedRecentLabelsProperty": route.captured_recent_labels_property,
                "presetHomeSearchCapturedRecentCountProperty": route.captured_recent_count_property,
                "presetHomeSearchRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_home_search_route_properties(widget) -> None:
            for key in (
                "presetHomeSearchRouteKey",
                "presetHomeSearchRouteRole",
                "presetHomeSearchPresetId",
                "presetHomeSearchHomeTabLabel",
                "presetHomeSearchObject",
                "presetHomeSearchEntryControl",
                "presetHomeSearchEntryObject",
                "presetHomeSearchContainerObject",
                "presetHomeSearchRecentLabelObject",
                "presetHomeSearchExpectedPlaceholder",
                "presetHomeSearchExpectedEntryPlaceholder",
                "presetHomeSearchExpectedActions",
                "presetHomeSearchExpectedRecentLabels",
                "presetHomeSearchExpectedRecentCount",
                "presetHomeSearchPlaceholderProperty",
                "presetHomeSearchEntryPlaceholderProperty",
                "presetHomeSearchCapturedProperty",
                "presetHomeSearchCapturedPlaceholderProperty",
                "presetHomeSearchCapturedEntryPlaceholderProperty",
                "presetHomeSearchCapturedTextProperty",
                "presetHomeSearchCapturedEntryTextProperty",
                "presetHomeSearchCapturedActionsProperty",
                "presetHomeSearchCapturedRecentLabelsProperty",
                "presetHomeSearchCapturedRecentCountProperty",
                "presetHomeSearchCaptured",
                "presetHomeSearchCapturedPlaceholder",
                "presetHomeSearchCapturedEntryPlaceholder",
                "presetHomeSearchCapturedText",
                "presetHomeSearchCapturedEntryText",
                "presetHomeSearchCapturedActions",
                "presetHomeSearchCapturedRecentLabels",
                "presetHomeSearchCapturedRecentCount",
                "presetHomeSearchRenderSource",
            ):
                widget.setProperty(key, None)

        def home_search_route_widgets(self, route) -> list:
            container = self.findChild(QWidget, route.container_object)
            home_search = self.findChild(QLineEdit, route.home_search_object)
            entry_search = self.findChild(QLineEdit, route.entry_search_object)
            recent_labels = (
                container.findChildren(QLabel, route.recent_label_object)
                if container is not None
                else []
            )
            candidates = [self, self.tabs, container, home_search, entry_search, *recent_labels]
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

        def apply_home_search_route_for_design(self, route) -> None:
            for widget in [
                self,
                self.tabs,
                *self.findChildren(QWidget, "welcomePanel"),
                *self.findChildren(QWidget, "mobaHomeWelcomeSurface"),
                *self.findChildren(QLineEdit, "homeSearch"),
                *self.findChildren(QLineEdit, "quickConnect"),
                *self.findChildren(QLineEdit, "secureCrtSessionFilter"),
                *self.findChildren(QLineEdit, "termiusHostSearch"),
                *self.findChildren(QLineEdit, "remminaProfileFilter"),
                *self.findChildren(QLineEdit, "mRemoteNgDocumentFilter"),
            ]:
                self.clear_preset_home_search_route_properties(widget)
            if route is None:
                return
            container = self.findChild(QWidget, route.container_object)
            home_search = self.findChild(QLineEdit, route.home_search_object)
            entry_search = self.findChild(QLineEdit, route.entry_search_object)
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
                self.apply_preset_home_search_route_properties(widget, route)
                widget.setProperty(route.captured_property, True)
                widget.setProperty(route.captured_placeholder_property, captured_placeholder)
                widget.setProperty(route.captured_entry_placeholder_property, captured_entry_placeholder)
                widget.setProperty(route.captured_text_property, captured_text)
                widget.setProperty(route.captured_entry_text_property, captured_entry_text)
                widget.setProperty(route.captured_actions_property, action_labels)
                widget.setProperty(route.captured_recent_labels_property, recent_labels)
                widget.setProperty(route.captured_recent_count_property, len(recent_labels))

        @staticmethod
        def apply_preset_reference_tab_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceTabRouteKey": route.key,
                "presetReferenceTabRouteRole": route.route_role,
                "presetReferenceTabPresetId": route.preset_id,
                "presetReferenceTabProfile": route.reference_profile,
                "presetReferenceTabActiveLabel": route.active_tab_label,
                "presetReferenceTabHomeLabel": route.home_tab_label,
                "presetReferenceTabTabsObject": route.tabs_object,
                "presetReferenceTabHomeRole": route.home_tab_role,
                "presetReferenceTabReferenceRole": route.reference_tab_role,
                "presetReferenceTabActivatedLabelProperty": route.activated_label_property,
                "presetReferenceTabReturnedHomeLabelProperty": route.returned_home_label_property,
                "presetReferenceTabActiveProperty": route.active_tab_property,
                "presetReferenceTabHomeProperty": route.home_tab_property,
                "presetReferenceTabProfileProperty": route.reference_profile_property,
                "presetReferenceTabRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_tab_route_properties(widget) -> None:
            for key in (
                "presetReferenceTabRouteKey",
                "presetReferenceTabRouteRole",
                "presetReferenceTabPresetId",
                "presetReferenceTabProfile",
                "presetReferenceTabActiveLabel",
                "presetReferenceTabHomeLabel",
                "presetReferenceTabTabsObject",
                "presetReferenceTabHomeRole",
                "presetReferenceTabReferenceRole",
                "presetReferenceTabActivatedLabelProperty",
                "presetReferenceTabReturnedHomeLabelProperty",
                "presetReferenceTabActiveProperty",
                "presetReferenceTabHomeProperty",
                "presetReferenceTabProfileProperty",
                "presetReferenceTabActivatedLabel",
                "presetReferenceTabReturnedHomeLabel",
                "presetReferenceTabRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_tab_chrome_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceTabChromeRouteKey": route.key,
                "presetReferenceTabChromeRouteRole": route.route_role,
                "presetReferenceTabChromePresetId": route.preset_id,
                "presetReferenceTabChromeProfile": route.reference_profile,
                "presetReferenceTabChromeActiveLabel": route.active_tab_label,
                "presetReferenceTabChromeHomeLabel": route.home_tab_label,
                "presetReferenceTabChromeTabsObject": route.tabs_object,
                "presetReferenceTabChromeTabBarObject": route.tab_bar_object,
                "presetReferenceTabChromeReferenceRole": route.reference_tab_role,
                "presetReferenceTabChromeNewSessionRole": route.new_session_tab_role,
                "presetReferenceTabChromeExpectedPosition": route.expected_tab_position,
                "presetReferenceTabChromeExpectedTooltip": route.expected_tooltip,
                "presetReferenceTabChromeExpectedCloseable": route.expected_closeable,
                "presetReferenceTabChromeExpectedSelectedDuringCapture": route.expected_selected_during_capture,
                "presetReferenceTabChromeCapturedProperty": route.captured_property,
                "presetReferenceTabChromeCapturedLabelProperty": route.captured_label_property,
                "presetReferenceTabChromeCapturedTooltipProperty": route.captured_tooltip_property,
                "presetReferenceTabChromeCapturedIndexProperty": route.captured_index_property,
                "presetReferenceTabChromeCapturedRoleProperty": route.captured_role_property,
                "presetReferenceTabChromeCapturedPositionProperty": route.captured_position_property,
                "presetReferenceTabChromeCapturedCloseableProperty": route.captured_closeable_property,
                "presetReferenceTabChromeCapturedSelectedProperty": route.captured_selected_property,
                "presetReferenceTabChromeRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_tab_chrome_route_properties(widget) -> None:
            for key in (
                "presetReferenceTabChromeRouteKey",
                "presetReferenceTabChromeRouteRole",
                "presetReferenceTabChromePresetId",
                "presetReferenceTabChromeProfile",
                "presetReferenceTabChromeActiveLabel",
                "presetReferenceTabChromeHomeLabel",
                "presetReferenceTabChromeTabsObject",
                "presetReferenceTabChromeTabBarObject",
                "presetReferenceTabChromeReferenceRole",
                "presetReferenceTabChromeNewSessionRole",
                "presetReferenceTabChromeExpectedPosition",
                "presetReferenceTabChromeExpectedTooltip",
                "presetReferenceTabChromeExpectedCloseable",
                "presetReferenceTabChromeExpectedSelectedDuringCapture",
                "presetReferenceTabChromeCapturedProperty",
                "presetReferenceTabChromeCapturedLabelProperty",
                "presetReferenceTabChromeCapturedTooltipProperty",
                "presetReferenceTabChromeCapturedIndexProperty",
                "presetReferenceTabChromeCapturedRoleProperty",
                "presetReferenceTabChromeCapturedPositionProperty",
                "presetReferenceTabChromeCapturedCloseableProperty",
                "presetReferenceTabChromeCapturedSelectedProperty",
                "presetReferenceTabChromeCaptured",
                "presetReferenceTabChromeLabel",
                "presetReferenceTabChromeTooltip",
                "presetReferenceTabChromeIndex",
                "presetReferenceTabChromeRole",
                "presetReferenceTabChromePosition",
                "presetReferenceTabChromeCloseable",
                "presetReferenceTabChromeSelected",
                "presetReferenceTabChromeRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_status_bar_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceStatusRouteKey": route.key,
                "presetReferenceStatusRouteRole": route.route_role,
                "presetReferenceStatusPresetId": route.preset_id,
                "presetReferenceStatusProfile": route.reference_profile,
                "presetReferenceStatusActiveTab": route.active_tab_label,
                "presetReferenceStatusBarObject": route.status_bar_object,
                "presetReferenceStatusNoticeObject": route.status_notice_object,
                "presetReferenceStatusSegmentObject": route.status_segment_object,
                "presetReferenceStatusExpectedMessage": route.expected_status_message,
                "presetReferenceStatusExpectedSegments": list(route.expected_status_segments),
                "presetReferenceStatusExpectedSegmentCount": route.expected_segment_count,
                "presetReferenceStatusCapturedProperty": route.captured_property,
                "presetReferenceStatusCapturedTabProperty": route.captured_tab_property,
                "presetReferenceStatusCapturedMessageProperty": route.captured_message_property,
                "presetReferenceStatusCapturedSegmentsProperty": route.captured_segments_property,
                "presetReferenceStatusCapturedSegmentCountProperty": route.captured_segment_count_property,
                "presetReferenceStatusCapturedSegmentTooltipsProperty": route.captured_segment_tooltips_property,
                "presetReferenceStatusCapturedNoticeProperty": route.captured_notice_property,
                "presetReferenceStatusRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_status_bar_route_properties(widget) -> None:
            for key in (
                "presetReferenceStatusRouteKey",
                "presetReferenceStatusRouteRole",
                "presetReferenceStatusPresetId",
                "presetReferenceStatusProfile",
                "presetReferenceStatusActiveTab",
                "presetReferenceStatusBarObject",
                "presetReferenceStatusNoticeObject",
                "presetReferenceStatusSegmentObject",
                "presetReferenceStatusExpectedMessage",
                "presetReferenceStatusExpectedSegments",
                "presetReferenceStatusExpectedSegmentCount",
                "presetReferenceStatusCapturedProperty",
                "presetReferenceStatusCapturedTabProperty",
                "presetReferenceStatusCapturedMessageProperty",
                "presetReferenceStatusCapturedSegmentsProperty",
                "presetReferenceStatusCapturedSegmentCountProperty",
                "presetReferenceStatusCapturedSegmentTooltipsProperty",
                "presetReferenceStatusCapturedNoticeProperty",
                "presetReferenceStatusCaptured",
                "presetReferenceStatusCapturedTab",
                "presetReferenceStatusMessage",
                "presetReferenceStatusSegments",
                "presetReferenceStatusSegmentCount",
                "presetReferenceStatusSegmentTooltips",
                "presetReferenceStatusNotice",
                "presetReferenceStatusRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_session_action_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceSessionActionRouteKey": route.key,
                "presetReferenceSessionActionRouteRole": route.route_role,
                "presetReferenceSessionActionPresetId": route.preset_id,
                "presetReferenceSessionActionProfile": route.reference_profile,
                "presetReferenceSessionActionActiveTab": route.active_tab_label,
                "presetReferenceSessionActionTabsObject": route.tabs_object,
                "presetReferenceSessionActionTabBarObject": route.tab_bar_object,
                "presetReferenceSessionActionReferenceRole": route.reference_tab_role,
                "presetReferenceSessionActionObject": route.action_object,
                "presetReferenceSessionActionExpectedKeys": list(route.expected_action_keys),
                "presetReferenceSessionActionExpectedLabels": list(route.expected_action_labels),
                "presetReferenceSessionActionExpectedCount": route.expected_action_count,
                "presetReferenceSessionActionAlwaysEnabledKeys": list(route.always_enabled_action_keys),
                "presetReferenceSessionActionConditionalEnabledKeys": list(route.conditional_enabled_action_keys),
                "presetReferenceSessionActionActionKeyProperty": route.action_key_property,
                "presetReferenceSessionActionActionLabelProperty": route.action_label_property,
                "presetReferenceSessionActionActionEnabledProperty": route.action_enabled_property,
                "presetReferenceSessionActionCapturedProperty": route.captured_property,
                "presetReferenceSessionActionCapturedTabProperty": route.captured_tab_property,
                "presetReferenceSessionActionCapturedKeysProperty": route.captured_action_keys_property,
                "presetReferenceSessionActionCapturedLabelsProperty": route.captured_action_labels_property,
                "presetReferenceSessionActionCapturedCountProperty": route.captured_action_count_property,
                "presetReferenceSessionActionCapturedEnabledKeysProperty": route.captured_enabled_keys_property,
                "presetReferenceSessionActionCapturedDisabledKeysProperty": route.captured_disabled_keys_property,
                "presetReferenceSessionActionRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_session_action_route_properties(widget) -> None:
            for key in (
                "presetReferenceSessionActionRouteKey",
                "presetReferenceSessionActionRouteRole",
                "presetReferenceSessionActionPresetId",
                "presetReferenceSessionActionProfile",
                "presetReferenceSessionActionActiveTab",
                "presetReferenceSessionActionTabsObject",
                "presetReferenceSessionActionTabBarObject",
                "presetReferenceSessionActionReferenceRole",
                "presetReferenceSessionActionObject",
                "presetReferenceSessionActionExpectedKeys",
                "presetReferenceSessionActionExpectedLabels",
                "presetReferenceSessionActionExpectedCount",
                "presetReferenceSessionActionAlwaysEnabledKeys",
                "presetReferenceSessionActionConditionalEnabledKeys",
                "presetReferenceSessionActionActionKeyProperty",
                "presetReferenceSessionActionActionLabelProperty",
                "presetReferenceSessionActionActionEnabledProperty",
                "presetReferenceSessionActionCapturedProperty",
                "presetReferenceSessionActionCapturedTabProperty",
                "presetReferenceSessionActionCapturedKeysProperty",
                "presetReferenceSessionActionCapturedLabelsProperty",
                "presetReferenceSessionActionCapturedCountProperty",
                "presetReferenceSessionActionCapturedEnabledKeysProperty",
                "presetReferenceSessionActionCapturedDisabledKeysProperty",
                "presetReferenceSessionActionsCaptured",
                "presetReferenceSessionActionsCapturedTab",
                "presetReferenceSessionActionKeys",
                "presetReferenceSessionActionLabels",
                "presetReferenceSessionActionCount",
                "presetReferenceSessionActionEnabledKeys",
                "presetReferenceSessionActionDisabledKeys",
                "presetReferenceSessionActionRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_moba_connected_session_action_route_properties(widget, route) -> None:
            properties = {
                "mobaConnectedSessionActionRouteKey": route.key,
                "mobaConnectedSessionActionRouteRole": route.route_role,
                "mobaConnectedSessionActionProfile": route.profile_name,
                "mobaConnectedSessionActionTarget": route.target,
                "mobaConnectedSessionActionActiveTabKey": route.active_tab_key,
                "mobaConnectedSessionActionActiveTab": route.active_tab_label,
                "mobaConnectedSessionActionReferenceTab": route.reference_tab_label,
                "mobaConnectedSessionActionTabsObject": route.tabs_object,
                "mobaConnectedSessionActionTabBarObject": route.tab_bar_object,
                "mobaConnectedSessionActionReferenceRole": route.reference_tab_role,
                "mobaConnectedSessionActionMenuObject": route.menu_object,
                "mobaConnectedSessionActionObject": route.action_object,
                "mobaConnectedSessionActionExpectedKeys": list(route.expected_action_keys),
                "mobaConnectedSessionActionExpectedLabels": list(route.expected_action_labels),
                "mobaConnectedSessionActionExpectedCount": route.expected_action_count,
                "mobaConnectedSessionActionAlwaysEnabledKeys": list(route.always_enabled_action_keys),
                "mobaConnectedSessionActionConditionalEnabledKeys": list(route.conditional_enabled_action_keys),
                "mobaConnectedSessionActionActionKeyProperty": route.action_key_property,
                "mobaConnectedSessionActionActionLabelProperty": route.action_label_property,
                "mobaConnectedSessionActionActionEnabledProperty": route.action_enabled_property,
                "mobaConnectedSessionActionCapturedProperty": route.captured_property,
                "mobaConnectedSessionActionCapturedTabProperty": route.captured_tab_property,
                "mobaConnectedSessionActionCapturedKeysProperty": route.captured_action_keys_property,
                "mobaConnectedSessionActionCapturedLabelsProperty": route.captured_action_labels_property,
                "mobaConnectedSessionActionCapturedCountProperty": route.captured_action_count_property,
                "mobaConnectedSessionActionCapturedEnabledKeysProperty": route.captured_enabled_keys_property,
                "mobaConnectedSessionActionCapturedDisabledKeysProperty": route.captured_disabled_keys_property,
                "mobaConnectedSessionActionRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def apply_preset_reference_surface_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceSurfaceRouteKey": route.key,
                "presetReferenceSurfaceRouteRole": route.route_role,
                "presetReferenceSurfacePresetId": route.preset_id,
                "presetReferenceSurfaceProfile": route.reference_profile,
                "presetReferenceSurfaceActiveTab": route.active_tab_label,
                "presetReferenceSurfaceExpectedTitle": route.expected_title,
                "presetReferenceSurfaceExpectedSource": route.expected_source,
                "presetReferenceSurfaceCommandExecutables": list(route.command_executables),
                "presetReferenceSurfaceCommandExecutableChoices": "|".join(route.command_executables),
                "presetReferenceSurfaceCommandTargetFragment": route.command_target_fragment,
                "presetReferenceSurfaceTerminalPaneObject": route.terminal_pane_object,
                "presetReferenceSurfaceTitleObject": route.terminal_title_object,
                "presetReferenceSurfaceSourceObject": route.terminal_source_object,
                "presetReferenceSurfaceCommandObject": route.terminal_command_object,
                "presetReferenceSurfaceOutputObject": route.terminal_output_object,
                "presetReferenceSurfaceCapturedProperty": route.captured_property,
                "presetReferenceSurfaceCapturedTabProperty": route.captured_tab_property,
                "presetReferenceSurfaceActualTitleProperty": route.actual_title_property,
                "presetReferenceSurfaceActualSourceProperty": route.actual_source_property,
                "presetReferenceSurfaceActualCommandProperty": route.actual_command_property,
                "presetReferenceSurfaceActualOutputProperty": route.actual_output_property,
                "presetReferenceSurfaceRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_surface_route_properties(widget) -> None:
            for key in (
                "presetReferenceSurfaceRouteKey",
                "presetReferenceSurfaceRouteRole",
                "presetReferenceSurfacePresetId",
                "presetReferenceSurfaceProfile",
                "presetReferenceSurfaceActiveTab",
                "presetReferenceSurfaceExpectedTitle",
                "presetReferenceSurfaceExpectedSource",
                "presetReferenceSurfaceCommandExecutables",
                "presetReferenceSurfaceCommandExecutableChoices",
                "presetReferenceSurfaceCommandTargetFragment",
                "presetReferenceSurfaceTerminalPaneObject",
                "presetReferenceSurfaceTitleObject",
                "presetReferenceSurfaceSourceObject",
                "presetReferenceSurfaceCommandObject",
                "presetReferenceSurfaceOutputObject",
                "presetReferenceSurfaceCapturedProperty",
                "presetReferenceSurfaceCapturedTabProperty",
                "presetReferenceSurfaceActualTitleProperty",
                "presetReferenceSurfaceActualSourceProperty",
                "presetReferenceSurfaceActualCommandProperty",
                "presetReferenceSurfaceActualOutputProperty",
                "presetReferenceSurfaceCaptured",
                "presetReferenceSurfaceCapturedTab",
                "presetReferenceSurfaceActualTitle",
                "presetReferenceSurfaceActualSource",
                "presetReferenceSurfaceActualCommand",
                "presetReferenceSurfaceActualOutput",
                "presetReferenceSurfaceRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_control_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceControlRouteKey": route.key,
                "presetReferenceControlRouteRole": route.route_role,
                "presetReferenceControlPresetId": route.preset_id,
                "presetReferenceControlProfile": route.reference_profile,
                "presetReferenceControlActiveTab": route.active_tab_label,
                "presetReferenceControlTerminalPaneObject": route.terminal_pane_object,
                "presetReferenceControlStatusObject": route.terminal_status_object,
                "presetReferenceControlActionObject": route.terminal_action_object,
                "presetReferenceControlActionKeys": list(route.action_keys),
                "presetReferenceControlActionLabels": list(route.action_labels),
                "presetReferenceControlActionTooltips": list(route.action_tooltips),
                "presetReferenceControlAllowedStatusStates": list(route.allowed_status_states),
                "presetReferenceControlActionKeyProperty": route.action_key_property,
                "presetReferenceControlActionLabelProperty": route.action_label_property,
                "presetReferenceControlActionTooltipProperty": route.action_tooltip_property,
                "presetReferenceControlStatusStateProperty": route.status_state_property,
                "presetReferenceControlCapturedProperty": route.captured_property,
                "presetReferenceControlCapturedActionsProperty": route.captured_actions_property,
                "presetReferenceControlCapturedStatusProperty": route.captured_status_property,
                "presetReferenceControlCapturedStatusTextProperty": route.captured_status_text_property,
                "presetReferenceControlRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_control_route_properties(widget) -> None:
            for key in (
                "presetReferenceControlRouteKey",
                "presetReferenceControlRouteRole",
                "presetReferenceControlPresetId",
                "presetReferenceControlProfile",
                "presetReferenceControlActiveTab",
                "presetReferenceControlTerminalPaneObject",
                "presetReferenceControlStatusObject",
                "presetReferenceControlActionObject",
                "presetReferenceControlActionKeys",
                "presetReferenceControlActionLabels",
                "presetReferenceControlActionTooltips",
                "presetReferenceControlAllowedStatusStates",
                "presetReferenceControlActionKeyProperty",
                "presetReferenceControlActionLabelProperty",
                "presetReferenceControlActionTooltipProperty",
                "presetReferenceControlStatusStateProperty",
                "presetReferenceControlCapturedProperty",
                "presetReferenceControlCapturedActionsProperty",
                "presetReferenceControlCapturedStatusProperty",
                "presetReferenceControlCapturedStatusTextProperty",
                "presetReferenceControlsCaptured",
                "presetReferenceControlCapturedActionKeys",
                "presetReferenceControlStatusState",
                "presetReferenceControlStatusText",
                "presetReferenceControlRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_input_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceInputRouteKey": route.key,
                "presetReferenceInputRouteRole": route.route_role,
                "presetReferenceInputPresetId": route.preset_id,
                "presetReferenceInputProfile": route.reference_profile,
                "presetReferenceInputActiveTab": route.active_tab_label,
                "presetReferenceInputTerminalPaneObject": route.terminal_pane_object,
                "presetReferenceInputObject": route.terminal_input_object,
                "presetReferenceInputExpectedPlaceholder": route.placeholder_text,
                "presetReferenceInputExpectedInitialText": route.expected_initial_text,
                "presetReferenceInputAllowedEnabledStates": list(route.allowed_enabled_states),
                "presetReferenceInputCapturedProperty": route.captured_property,
                "presetReferenceInputCapturedTabProperty": route.captured_tab_property,
                "presetReferenceInputCapturedPlaceholderProperty": route.captured_placeholder_property,
                "presetReferenceInputCapturedTextProperty": route.captured_text_property,
                "presetReferenceInputCapturedEnabledProperty": route.captured_enabled_property,
                "presetReferenceInputRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_input_route_properties(widget) -> None:
            for key in (
                "presetReferenceInputRouteKey",
                "presetReferenceInputRouteRole",
                "presetReferenceInputPresetId",
                "presetReferenceInputProfile",
                "presetReferenceInputActiveTab",
                "presetReferenceInputTerminalPaneObject",
                "presetReferenceInputObject",
                "presetReferenceInputExpectedPlaceholder",
                "presetReferenceInputExpectedInitialText",
                "presetReferenceInputAllowedEnabledStates",
                "presetReferenceInputCapturedProperty",
                "presetReferenceInputCapturedTabProperty",
                "presetReferenceInputCapturedPlaceholderProperty",
                "presetReferenceInputCapturedTextProperty",
                "presetReferenceInputCapturedEnabledProperty",
                "presetReferenceInputCaptured",
                "presetReferenceInputCapturedTab",
                "presetReferenceInputPlaceholder",
                "presetReferenceInputText",
                "presetReferenceInputEnabled",
                "presetReferenceInputRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_reference_transcript_route_properties(widget, route) -> None:
            properties = {
                "presetReferenceTranscriptRouteKey": route.key,
                "presetReferenceTranscriptRouteRole": route.route_role,
                "presetReferenceTranscriptPresetId": route.preset_id,
                "presetReferenceTranscriptProfile": route.reference_profile,
                "presetReferenceTranscriptActiveTab": route.active_tab_label,
                "presetReferenceTranscriptTerminalPaneObject": route.terminal_pane_object,
                "presetReferenceTranscriptOutputObject": route.terminal_output_object,
                "presetReferenceTranscriptCommandEchoPrefix": route.command_echo_prefix,
                "presetReferenceTranscriptRequiredFragments": list(route.required_fragments),
                "presetReferenceTranscriptMinimumLineCount": route.minimum_line_count,
                "presetReferenceTranscriptCapturedProperty": route.captured_property,
                "presetReferenceTranscriptCapturedTabProperty": route.captured_tab_property,
                "presetReferenceTranscriptCapturedTextProperty": route.captured_text_property,
                "presetReferenceTranscriptCapturedLineCountProperty": route.captured_line_count_property,
                "presetReferenceTranscriptCapturedCommandEchoProperty": route.captured_command_echo_property,
                "presetReferenceTranscriptRenderSource": route.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        @staticmethod
        def clear_preset_reference_transcript_route_properties(widget) -> None:
            for key in (
                "presetReferenceTranscriptRouteKey",
                "presetReferenceTranscriptRouteRole",
                "presetReferenceTranscriptPresetId",
                "presetReferenceTranscriptProfile",
                "presetReferenceTranscriptActiveTab",
                "presetReferenceTranscriptTerminalPaneObject",
                "presetReferenceTranscriptOutputObject",
                "presetReferenceTranscriptCommandEchoPrefix",
                "presetReferenceTranscriptRequiredFragments",
                "presetReferenceTranscriptMinimumLineCount",
                "presetReferenceTranscriptCapturedProperty",
                "presetReferenceTranscriptCapturedTabProperty",
                "presetReferenceTranscriptCapturedTextProperty",
                "presetReferenceTranscriptCapturedLineCountProperty",
                "presetReferenceTranscriptCapturedCommandEchoProperty",
                "presetReferenceTranscriptCaptured",
                "presetReferenceTranscriptCapturedTab",
                "presetReferenceTranscriptText",
                "presetReferenceTranscriptLineCount",
                "presetReferenceTranscriptCommandEcho",
                "presetReferenceTranscriptRenderSource",
            ):
                widget.setProperty(key, None)

        @staticmethod
        def apply_preset_visual_signature_properties(widget, signature) -> None:
            properties = {
                "presetVisualSignatureKey": signature.key,
                "presetVisualSignatureRole": signature.route_role,
                "presetVisualSignaturePresetId": signature.preset_id,
                "presetVisualSignaturePresetLabel": signature.preset_label,
                "presetVisualSignatureDensity": signature.density,
                "presetVisualSignatureTabPosition": signature.tab_position,
                "presetVisualSignatureDocumentMode": signature.document_mode,
                "presetVisualSignatureProfileWidth": signature.profile_width,
                "presetVisualSignatureLogHeight": signature.log_height,
                "presetVisualSignatureToolbarIconSize": signature.toolbar_icon_size,
                "presetVisualSignatureListSpacing": signature.list_spacing,
                "presetVisualSignaturePalette": dict(signature.palette_items()),
                "presetVisualSignatureWindowObject": signature.window_object,
                "presetVisualSignatureMainToolbarObject": signature.main_toolbar_object,
                "presetVisualSignatureLayoutToolbarObject": signature.layout_toolbar_object,
                "presetVisualSignatureLeftPanelObject": signature.left_panel_object,
                "presetVisualSignatureProfileTreeObject": signature.profile_tree_object,
                "presetVisualSignatureTabsObject": signature.tabs_object,
                "presetVisualSignatureActivityLogObject": signature.activity_log_object,
                "presetVisualSignatureStatusBarObject": signature.status_bar_object,
                "presetVisualSignatureDensityProperty": signature.density_property,
                "presetVisualSignaturePaletteProperty": signature.palette_property,
                "presetVisualSignatureRenderSource": signature.render_source,
            }
            for key, value in properties.items():
                widget.setProperty(key, value)

        def configure_toolbar_for_design(self, preset: GuiDesignPreset, is_moba: bool, icon_size: int) -> None:
            icon = QSize(icon_size, icon_size)
            is_securecrt = preset.id == "securecrt"
            is_mremoteng = preset.id == "mremoteng"
            self.main_toolbar.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if is_moba or is_securecrt or is_mremoteng
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            for button in self.main_toolbar_buttons + self.layout_toolbar_buttons:
                button.setIconSize(icon)
                button.setToolButtonStyle(
                    Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                    if button in self.main_toolbar_buttons and (is_securecrt or is_mremoteng)
                    else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
                )
                button.setMinimumSize(QSize(0, 0))
                button.setMaximumSize(QSize(16777215, 16777215))
                button.setVisible(not is_moba or button in self.layout_toolbar_buttons)
            for widget in [self.view_label, self.design_select, self.search_input, self.find_button]:
                widget.setVisible(not is_moba)

            moba_widgets = [*self.moba_ribbon_buttons, self.moba_toolbar_spacer, self.moba_x_server_button, self.moba_exit_button]
            for widget in moba_widgets:
                widget.setVisible(is_moba)
            if is_moba:
                top_stack = gui_design_moba_top_stack_geometry()
                self.main_toolbar.setMinimumHeight(top_stack.ribbon_height)
                self.main_toolbar.setMaximumHeight(top_stack.ribbon_height)
                self.main_toolbar.setProperty("mobaTopStackRibbonY", top_stack.ribbon_y)
                self.main_toolbar.setProperty("mobaTopStackRibbonHeight", top_stack.ribbon_height)
                for button in self.moba_ribbon_buttons:
                    button.setIconSize(icon)
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    button.setMinimumSize(QSize(68, 56))
                    button.setMaximumSize(QSize(82, 56))
                for button in [self.moba_x_server_button, self.moba_exit_button]:
                    button.setIconSize(icon)
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                    button.setMinimumSize(QSize(70, 56))
                    button.setMaximumSize(QSize(78, 56))
            elif is_securecrt:
                self.main_toolbar.setMinimumHeight(gui_design_securecrt_top_chrome().toolbar_height)
                self.main_toolbar.setMaximumHeight(gui_design_securecrt_top_chrome().toolbar_height)
                for button in self.main_toolbar_buttons:
                    width = int(button.property("secureCrtTopToolbarStaticWidth") or 58)
                    button.setMinimumSize(QSize(width, 44))
                    button.setMaximumSize(QSize(max(width + 12, 70), 48))
            elif is_mremoteng:
                self.main_toolbar.setMinimumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
                self.main_toolbar.setMaximumHeight(gui_design_mremoteng_top_chrome().toolbar_height)
                for button in self.main_toolbar_buttons:
                    width = int(button.property("mRemoteNgTopToolbarStaticWidth") or 56)
                    button.setMinimumSize(QSize(width, 40))
                    button.setMaximumSize(QSize(max(width + 12, 70), 44))
            else:
                self.main_toolbar.setMinimumHeight(0)
                self.main_toolbar.setMaximumHeight(16777215)

        def configure_profile_tree_for_design(self, is_moba: bool, list_spacing: int) -> None:
            moba_chrome = gui_design_moba_session_tree_chrome()
            self.profile_list.setIndentation(moba_chrome.indentation if is_moba else 18)
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

        def update_quick_connect_suggestions(self) -> None:
            self.quick_connect_suggestions.clear()
            chrome = gui_design_moba_quick_connect_suggestion_chrome()
            quick_connect_chrome = gui_design_moba_quick_connect_chrome()
            self.quick_connect_suggestions.setProperty("mobaQuickConnectSuggestionQuery", self.quick_connect.text().strip())
            if not self.current_design_is_moba():
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
            candidates = quick_connect_candidates(self.quick_connect.text(), self.store.load(), limit=6)
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
                item.setToolTip(0, candidate.detail)
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
            candidates = quick_connect_candidates(text, self.store.load(), limit=1)
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
            if candidate.kind == "profile" and candidate.profile_name:
                self.select_profile(candidate.profile_name)
                self.connect_selected(False)
            elif candidate.profile is not None:
                self.launch_profile(candidate.profile, dry_run=False, prefix="QUICK CONNECT")
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

        def show_moba_clipboard_hints(self, *_args) -> None:
            self.show_workflow_dialog(
                "Clipboard and transfer hints",
                "Clipboard, paste and transfer helper routes for the active terminal.",
                [
                    ("Clipboard", "available", "Copy selected terminal text or paste into the active session."),
                    ("SFTP browser", "attached", "Use the left file browser for transfer previews."),
                    ("Follow folder", "checked", "Keep the file browser aligned with the terminal working directory."),
                ],
                "\n".join(
                    [
                        "Right utility rail clipboard workflow",
                        "Use project-owned controls for copy/paste hints and transfer routing.",
                        "No captured clipboard content or user-specific data is stored in previews.",
                    ]
                ),
            )

        def show_moba_terminal_settings(self, *_args) -> None:
            self.show_workflow_dialog(
                "Terminal settings",
                "Terminal appearance, interaction and session-edge settings for the active tab.",
                [
                    ("Font", "monospace", "Reference terminal rows use fixed-width text geometry."),
                    ("Session edge", "enabled", "Attachment and settings controls remain on the right edge."),
                    ("Telemetry", "bottom strip", "Remote monitoring metrics stay routed to bottom status cells."),
                ],
                "\n".join(
                    [
                        "Right utility rail settings workflow",
                        "Adjust terminal-facing view options without changing the active connection identity.",
                        "The route is measured separately from generic toolbar settings.",
                    ]
                ),
            )

        def show_moba_tools_status(self, *_args) -> None:
            self.set_moba_rail_active("tools")
            profiles = self.store.load()
            self.show_workflow_dialog(
                "Tools",
                "Operational tools for profiles, transfers, diagnostics and saved layouts.",
                [
                    ("Profile editor", f"{len(profiles)} saved", "Create, edit or remove connection profiles."),
                    ("Transfer queue", "available", "Preview SFTP get, put, mkdir and delete operations."),
                    ("Layouts", f"{len(self.layout_store.load())} saved", "Open grid, horizontal or vertical multi-pane layouts."),
                    ("Doctor", "available", "Inspect local protocol clients and launch readiness."),
                ],
                "\n".join(
                    [
                        "Tools workflow",
                        f"Profiles: {len(profiles)}",
                        f"Layouts: {len(self.layout_store.load())}",
                        "Use the action buttons below to open the most common tools.",
                    ]
                ),
                actions=[
                    ("New profile", self.create_profile),
                    ("New layout", self.create_layout),
                    ("Run doctor", self.show_doctor),
                ],
            )

        def show_moba_tunneling_status(self, *_args) -> None:
            profile = self.selected_profile_for_workflow()
            rows: list[tuple[str, str, str]]
            detail: str
            if profile is None:
                rows = [("SSH tunnels", "select profile", "Select an SSH/SFTP/SCP profile to inspect tunnel options.")]
                detail = "No profile selected.\nSelect a session from the left tree, then open Tunneling again."
                actions = [("New profile", self.create_profile)]
            else:
                tunnel_count = len(profile.tunnels)
                x11 = profile.options.get("x11", "off")
                agent = profile.options.get("agent_forward") or profile.options.get("forward_agent") or "off"
                rows = [
                    ("Profile", profile.protocol.upper(), profile.name),
                    ("Port forwards", str(tunnel_count), "local, remote or dynamic tunnel definitions"),
                    ("X11 forwarding", str(x11), "x11=true/trusted maps to -X/-Y in SSH launch plans"),
                    ("Agent forwarding", str(agent), "agent_forward=true maps to -A"),
                ]
                detail = "\n".join(
                    [
                        f"Profile: {profile.name}",
                        f"Target : {profile.display_target}",
                        f"Tunnels: {tunnel_count}",
                        "Dry-run the profile to inspect the exact argv that will launch.",
                    ]
                )
                actions = [("Edit profile", self.edit_selected_profile), ("Dry run", lambda: self.connect_selected(True))]
            self.show_workflow_dialog("Tunneling", "SSH forwarding and tunnel launch-plan inspection.", rows, detail, actions=actions)

        def show_moba_x_server_status(self, *_args) -> None:
            profile = self.selected_profile_for_workflow()
            x11_profiles = [item for item in self.store.load() if item.options.get("x11")]
            selected_x11 = profile.options.get("x11", "off") if profile is not None else "select profile"
            self.show_workflow_dialog(
                "X server",
                "X11-forwarded SSH sessions need a local X server such as VcXsrv, XQuartz or Xorg.",
                [
                    ("Selected profile", selected_x11, profile.name if profile is not None else "No profile selected"),
                    ("Profiles with X11", str(len(x11_profiles)), "Profiles where options.x11 is set"),
                    ("Doctor check", "available", "Doctor reports local X server client availability."),
                    ("Launch behavior", "SSH -X/-Y", "Remote Ops adds forwarding flags for opted-in profiles."),
                ],
                "\n".join(
                    [
                        "X server workflow",
                        "Set profile option x11=true for -X or x11=trusted for -Y.",
                        "Start your local X server before launching the remote SSH profile.",
                    ]
                ),
                actions=[("Run doctor", self.show_doctor), ("Edit profile", self.edit_selected_profile)],
            )

        def show_moba_packages_dialog(self, *_args) -> None:
            profile = self.selected_profile_for_workflow()
            if profile is None:
                rows = [("SFTP browser", "select profile", "Select an SSH/SFTP profile first.")]
                detail = "No profile selected.\nSelect a session from the tree to open files or transfer queues."
                actions = [("New profile", self.create_profile)]
            else:
                rows = [
                    ("SFTP browser", profile.protocol.upper(), f"Open interactive file pane for {profile.name}."),
                    ("Transfer queue", "available", "Preview batch get/put/mkdir operations before running."),
                    ("Local preview", "available", "Inspect local files and directories before queueing transfers."),
                ]
                detail = "\n".join(
                    [
                        f"Profile: {profile.name}",
                        f"Target : {profile.display_target}",
                        "Packages workflow maps to files, queues and local preview tools.",
                    ]
                )
                actions = [("Open files", self.open_files_selected), ("Transfer queue", self.open_transfer_queue_selected)]
            self.show_workflow_dialog("Packages", "File, SFTP and transfer queue workflows.", rows, detail, actions=actions)

        def show_moba_help_dialog(self, *_args) -> None:
            self.show_workflow_dialog(
                "Help",
                "Shortcuts, diagnostics and workflow entry points.",
                [
                    ("New terminal", "Ctrl+T", "Open a local shell tab."),
                    ("Close tab", "Ctrl+W", "Close the current session tab."),
                    ("Recover sessions", "Ctrl+Shift+T", "Reopen recent terminal plans."),
                    ("Find log text", "Ctrl+F", "Focus the log search field in non-Moba layouts."),
                    ("Doctor", "available", "Report protocol client availability."),
                ],
                "\n".join(
                    [
                        "Help workflow",
                        "The Moba-style UI keeps common workflows in the ribbon and context menus.",
                        "Run doctor for local client availability and protocol readiness.",
                    ]
                ),
                actions=[("Run doctor", self.show_doctor)],
            )

        def set_moba_rail_active(self, active: str) -> None:
            for button in getattr(self, "moba_rail_buttons", []):
                button.setChecked(button.property("mobaRailRole") == active)

        def toggle_moba_session_panel(self, *_args) -> None:
            sizes = self.root_splitter.sizes()
            total = sum(sizes) or max(900, self.width())
            if sizes and sizes[0] > 80:
                self.root_splitter.setSizes([34, max(620, total - 34)])
                self.statusBar().showMessage("Sessions panel collapsed")
                return
            preset_id = self.design_select.currentData() or "native"
            try:
                preset = get_gui_design_preset(str(preset_id))
                width = preset.profile_width
            except ValueError:
                width = 395
            self.root_splitter.setSizes([width, max(620, total - width)])
            self.statusBar().showMessage("Sessions panel restored")

        def show_moba_sessions_rail(self, *_args) -> None:
            self.show_moba_profile_tree()
            self.profile_list.expandAll()
            self.profile_list.setFocus()
            self.statusBar().showMessage("Sessions tree ready")

        def show_moba_favorites_rail(self, *_args) -> None:
            self.set_moba_rail_active("favorites")
            favorites = [
                profile.name
                for profile in self.store.load()
                if any(tag.lower() in {"favorite", "favorites", "starred"} for tag in profile.tags)
            ]
            if favorites:
                self.select_profile(favorites[0])
                message = f"Favorites: {len(favorites)} tagged session(s)"
            else:
                message = "Favorites: add a favorite/starred tag to a profile to surface it here."
            self.statusBar().showMessage(message)
            self.log.append(message)

        def show_moba_sftp_rail(self, *_args) -> None:
            self.set_moba_rail_active("sftp")
            if getattr(self, "moba_connected_dock", None) is not None:
                self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
                self.statusBar().showMessage("Connected SFTP browser dock ready")
                return
            self.statusBar().showMessage("SFTP rail: open an SSH session to attach the browser dock")
            self.show_moba_packages_dialog()

        def show_moba_macros_status(self, *_args) -> None:
            self.set_moba_rail_active("macros")
            self.show_workflow_dialog(
                "Macros",
                "Reusable snippets and scripted workflows for repeated operator actions.",
                [
                    ("Snippets", "CLI-backed", "Store and run reusable command snippets."),
                    ("MultiExec", "ribbon", "Preview launch commands and broadcast workflows."),
                    ("Recover", "Ctrl+Shift+T", "Restore recent terminal plans."),
                    ("Future dialogs", "tracked", "GUI macro editor can build on snippet storage."),
                ],
                "Macros are represented by reusable snippets and terminal plans today.\nThe rail keeps this workflow visible in the Moba-style shell.",
                actions=[("New terminal", self.open_local_terminal_tab), ("Run doctor", self.show_doctor)],
            )

        def show_workflow_dialog(
            self,
            title: str,
            subtitle: str,
            rows: list[tuple[str, str, str]],
            detail: str,
            *,
            actions: list[tuple[str, object]] | None = None,
        ) -> None:
            dialog = WorkflowDialog(title, subtitle, rows, detail, actions=actions, parent=self)
            dialog.exec()
            self.statusBar().showMessage(f"Workflow: {title}")

        def selected_profile_for_workflow(self) -> Profile | None:
            return self.profile_by_name(self.selected_profile_name())

        def tab_position_for_design(self, value: str):
            if value == "west":
                return QTabWidget.TabPosition.West
            if value == "south":
                return QTabWidget.TabPosition.South
            if value == "east":
                return QTabWidget.TabPosition.East
            return QTabWidget.TabPosition.North

        def configure_workspace_tabs_for_design(self, is_moba: bool) -> None:
            home_index = self.find_tab_by_role("home")
            home_label = gui_design_home_tab_label(self.current_design_id())
            if home_index >= 0:
                was_current = self.tabs.currentIndex() == home_index
                self.rebuild_welcome_tab(select=was_current)
            elif is_moba or self.tabs.count() == 0:
                self.add_welcome_tab(select=self.tabs.count() == 0)
            home_index = self.find_tab_by_role("home")
            if home_index >= 0:
                self.tabs.setTabText(home_index, home_label)
                self.tabs.setTabToolTip(home_index, f"{home_label}: {self.current_design_id()} preset home tab")
                if is_moba:
                    self.apply_moba_tab_chrome(
                        home_index,
                        key="home",
                        icon_key="home",
                        tooltip="Home",
                        closeable=False,
                    )
            if is_moba:
                self.ensure_new_session_tab()
            else:
                self.remove_new_session_tab()
            self.refresh_special_tab_buttons()

        def rebuild_welcome_tab(self, *, select: bool) -> None:
            home_index = self.find_tab_by_role("home")
            if home_index < 0:
                self.add_welcome_tab(select=select)
                return
            widget = self.tabs.widget(home_index)
            self.tabs.removeTab(home_index)
            if widget is not None:
                widget.deleteLater()
            self.add_welcome_tab(select=select)

        def current_design_is_moba(self) -> bool:
            return (self.design_select.currentData() or "native") == "mobaxterm"

        def tab_role(self, index: int) -> str:
            widget = self.tabs.widget(index)
            if widget is None:
                return ""
            return str(widget.property("tabRole") or "session")

        def find_tab_by_role(self, role: str) -> int:
            for index in range(self.tabs.count()):
                if self.tab_role(index) == role:
                    return index
            return -1

        def find_tab_by_label(self, label: str) -> int:
            for index in range(self.tabs.count()):
                if self.tabs.tabText(index) == label:
                    return index
            return -1

        def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int:
            widget.setProperty("tabRole", role)
            new_index = self.find_tab_by_role("new-session")
            if new_index >= 0:
                index = self.tabs.insertTab(new_index, widget, title)
            else:
                index = self.tabs.addTab(widget, title)
            self.tabs.setTabToolTip(index, title)
            if select:
                self.tabs.setCurrentIndex(index)
            self.refresh_special_tab_buttons()
            return index

        def ensure_new_session_tab(self) -> None:
            if self.find_tab_by_role("new-session") >= 0:
                self.refresh_special_tab_buttons()
                return
            new_tab = QWidget()
            new_tab.setObjectName("newSessionTab")
            index = self.add_workspace_tab(new_tab, "+", select=False, role="new-session")
            self.apply_moba_tab_chrome(
                index,
                key="new-session",
                icon_key="plus",
                tooltip="Open a new local terminal",
                closeable=False,
            )

        def remove_new_session_tab(self) -> None:
            index = self.find_tab_by_role("new-session")
            if index < 0:
                return
            widget = self.tabs.widget(index)
            self.tabs.removeTab(index)
            if widget is not None:
                widget.deleteLater()

        def refresh_special_tab_buttons(self) -> None:
            tab_bar = self.tabs.tabBar()
            for role in ["home", "new-session"]:
                index = self.find_tab_by_role(role)
                if index < 0:
                    continue
                self.tabs.setTabText(index, "+" if role == "new-session" else self.tabs.tabText(index))
                for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                    tab_bar.setTabButton(index, position, None)
            new_index = self.find_tab_by_role("new-session")
            if new_index >= 0 and new_index != self.tabs.count() - 1:
                widget = self.tabs.widget(new_index)
                if widget is not None:
                    self.tabs.removeTab(new_index)
                    self.tabs.addTab(widget, "+")
                    self.tabs.setTabToolTip(self.tabs.count() - 1, "Open a new local terminal")
            new_index = self.find_tab_by_role("new-session")
            if new_index >= 0:
                self.apply_moba_tab_chrome(
                    new_index,
                    key="new-session",
                    icon_key="plus",
                    tooltip="Open a new local terminal",
                    closeable=False,
                )
                for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                    tab_bar.setTabButton(new_index, position, None)

        def apply_moba_tab_chrome(
            self,
            index: int,
            *,
            key: str,
            icon_key: str,
            tooltip: str,
            closeable: bool,
        ) -> None:
            if index < 0:
                return
            widget = self.tabs.widget(index)
            geometry = moba_connected_tab_chrome_geometry_for(key)
            self.tabs.setProperty(
                "mobaTabChromeGeometryKeys",
                [item.key for item in moba_connected_tab_chrome_geometry_items()],
            )
            if widget is not None:
                widget.setProperty("mobaTabChromeKey", key)
                widget.setProperty("mobaTabIconKey", icon_key)
                widget.setProperty("mobaTabCloseable", closeable)
                widget.setProperty("mobaTabStaticWidth", geometry.width)
                widget.setProperty("mobaTabStaticHeight", geometry.height)
                widget.setProperty("mobaTabCornerRadius", geometry.corner_radius)
                widget.setProperty("mobaTabIconX", geometry.icon_x)
                widget.setProperty("mobaTabIconY", geometry.icon_y)
                widget.setProperty("mobaTabIconSize", geometry.icon_size)
                widget.setProperty("mobaTabLabelX", geometry.label_x)
                widget.setProperty("mobaTabLabelY", geometry.label_y)
                widget.setProperty("mobaTabCloseRightOffset", geometry.close_right_offset)
                widget.setProperty("mobaTabCloseY", geometry.close_y)
                widget.setProperty("mobaTabPlusX", geometry.plus_x)
                widget.setProperty("mobaTabPlusY", geometry.plus_y)
                widget.setProperty("mobaTabGapAfter", geometry.gap_after)
            self.tabs.setIconSize(QSize(16, 16))
            self.tabs.setTabIcon(index, self.moba_ribbon_icon(icon_key, "#d6a72d", size=18))
            self.tabs.setTabToolTip(index, tooltip)
            if not closeable:
                tab_bar = self.tabs.tabBar()
                for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                    tab_bar.setTabButton(index, position, None)

        def handle_tab_changed(self, index: int) -> None:
            if self.moba_tab_guard or index < 0:
                self.refresh_moba_left_dock_for_current_tab()
                return
            if self.tab_role(index) != "new-session":
                self.refresh_moba_left_dock_for_current_tab()
                return
            self.moba_tab_guard = True
            try:
                self.open_local_terminal_tab()
            finally:
                self.moba_tab_guard = False
            self.refresh_moba_left_dock_for_current_tab()

        def tab_context_session_action_specs(self, index: int) -> list[dict[str, object]]:
            role = self.tab_role(index)
            is_closeable_session = role not in {"home", "new-session"}
            return [
                {"key": "new-local-terminal", "label": "New local terminal", "enabled": True},
                {"key": "split-horizontal", "label": "Split horizontal", "enabled": True},
                {"key": "split-vertical", "label": "Split vertical", "enabled": True},
                {"key": "duplicate-tab", "label": "Duplicate tab", "enabled": is_closeable_session},
                {"key": "close-tab", "label": "Close tab", "enabled": is_closeable_session},
                {
                    "key": "close-other-tabs",
                    "label": "Close other tabs",
                    "enabled": self.count_closeable_tabs(except_index=index) > 0,
                },
                {"key": "recover-previous-sessions", "label": "Recover previous sessions", "enabled": True},
            ]

        def reference_session_action_route_for_tab(self, index: int):
            preset_id = self.current_design_id()
            if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS or index < 0:
                return None
            route = gui_design_preset_reference_session_action_route(preset_id)
            if self.tabs.tabText(index) != route.active_tab_label:
                return None
            if self.tab_role(index) != route.reference_tab_role:
                return None
            return route

        def moba_connected_session_action_route_for_tab(self, index: int):
            if not self.current_design_is_moba() or index < 0:
                return None
            widget = self.tabs.widget(index)
            state = getattr(widget, "moba_connected_state", None)
            if state is None:
                return None
            route = moba_connected_session_action_route(state)
            if self.tab_role(index) != route.reference_tab_role:
                return None
            if self.tabs.tabText(index) not in {route.active_tab_label, route.reference_tab_label}:
                return None
            return route

        def session_action_route_for_tab(self, index: int):
            return self.moba_connected_session_action_route_for_tab(index) or self.reference_session_action_route_for_tab(
                index
            )

        @staticmethod
        def session_action_capture_from_specs(
            specs: list[dict[str, object]],
        ) -> tuple[list[str], list[str], list[str], list[str]]:
            action_keys = [str(spec["key"]) for spec in specs]
            action_labels = [str(spec["label"]) for spec in specs]
            enabled_keys = [str(spec["key"]) for spec in specs if bool(spec["enabled"])]
            disabled_keys = [str(spec["key"]) for spec in specs if not bool(spec["enabled"])]
            return action_keys, action_labels, enabled_keys, disabled_keys

        def apply_session_action_spec_properties(self, action, spec: dict[str, object], route) -> None:
            action.setObjectName(route.action_object if route is not None else "sessionTabContextAction")
            action.setProperty("sessionTabContextActionKey", str(spec["key"]))
            action.setProperty("sessionTabContextActionLabel", str(spec["label"]))
            action.setProperty("sessionTabContextActionEnabled", bool(spec["enabled"]))
            if route is not None:
                if hasattr(route, "profile_name"):
                    self.apply_moba_connected_session_action_route_properties(action, route)
                else:
                    self.apply_preset_reference_session_action_route_properties(action, route)

        @staticmethod
        def session_action_menu_object_name(route) -> str:
            if route is None:
                return "sessionTabContextMenu"
            return str(getattr(route, "menu_object", "presetReferenceSessionTabContextMenu"))

        def apply_session_action_menu_capture(self, menu, route, tab_title: str, actions: list[object]) -> None:
            if route is None:
                return
            if hasattr(route, "profile_name"):
                self.apply_moba_connected_session_action_route_properties(menu, route)
            else:
                self.apply_preset_reference_session_action_route_properties(menu, route)
            action_keys = [str(action.property(route.action_key_property) or "") for action in actions]
            action_labels = [str(action.property(route.action_label_property) or "") for action in actions]
            enabled_keys = [
                str(action.property(route.action_key_property) or "")
                for action in actions
                if bool(action.property(route.action_enabled_property))
            ]
            disabled_keys = [
                str(action.property(route.action_key_property) or "")
                for action in actions
                if not bool(action.property(route.action_enabled_property))
            ]
            menu.setProperty(route.captured_property, True)
            menu.setProperty(route.captured_tab_property, tab_title)
            menu.setProperty(route.captured_action_keys_property, action_keys)
            menu.setProperty(route.captured_action_labels_property, action_labels)
            menu.setProperty(route.captured_action_count_property, len(action_keys))
            menu.setProperty(route.captured_enabled_keys_property, enabled_keys)
            menu.setProperty(route.captured_disabled_keys_property, disabled_keys)

        def build_tab_context_menu(self, index: int):
            if index < 0:
                return None
            route = self.session_action_route_for_tab(index)
            specs = {str(spec["key"]): spec for spec in self.tab_context_session_action_specs(index)}
            menu = QMenu(self)
            menu.setObjectName(self.session_action_menu_object_name(route))
            context_actions = []

            def add_context_action(key: str, callback) -> None:
                spec = specs[key]
                action = menu.addAction(str(spec["label"]), callback)
                action.setEnabled(bool(spec["enabled"]))
                self.apply_session_action_spec_properties(action, spec, route)
                context_actions.append(action)

            add_context_action("new-local-terminal", self.open_local_terminal_tab)
            add_context_action("split-horizontal", lambda: self.add_split("horizontal"))
            add_context_action("split-vertical", lambda: self.add_split("vertical"))
            menu.addSeparator()
            add_context_action("duplicate-tab", self.duplicate_current_tab)
            add_context_action("close-tab", self.close_current_tab)
            add_context_action("close-other-tabs", lambda: self.close_other_tabs(index))
            menu.addSeparator()
            add_context_action("recover-previous-sessions", self.recover_previous_sessions)
            self.apply_session_action_menu_capture(menu, route, self.tabs.tabText(index), context_actions)
            return menu

        def show_tab_context_menu(self, position) -> None:
            index = self.tabs.tabBar().tabAt(position)
            if index < 0:
                return
            if self.tab_role(index) != "new-session":
                self.tabs.setCurrentIndex(index)
            menu = self.build_tab_context_menu(index)
            if menu is not None:
                menu.exec(self.tabs.tabBar().mapToGlobal(position))

        def count_closeable_tabs(self, *, except_index: int | None = None) -> int:
            count = 0
            for index in range(self.tabs.count()):
                if index == except_index:
                    continue
                if self.tab_role(index) not in {"home", "new-session"}:
                    count += 1
            return count

        def selected_profile_name(self) -> str | None:
            item = self.profile_list.currentItem()
            if not item:
                return None
            return item.data(0, Qt.ItemDataRole.UserRole)

        def create_profile(self) -> None:
            dialog = ProfileDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                profile = dialog.profile()
                self.store.add(profile)
                self.refresh_profiles()
                self.select_profile(profile.name)
                self.log.append(f"PROFILE SAVED: {profile.name}")
            except ValueError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def edit_selected_profile(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                current = self.store.get(name)
            except KeyError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))
                return
            dialog = ProfileDialog(current, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                profile = dialog.profile()
                self.save_profile(profile, original_name=name)
                self.refresh_profiles()
                self.select_profile(profile.name)
                self.log.append(f"PROFILE UPDATED: {profile.name}")
            except (KeyError, ValueError) as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def remove_selected_profile(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            answer = QMessageBox.question(self, "Remove profile", f"Remove profile {name}?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.store.remove(name)
                self.refresh_profiles()
                self.log.append(f"PROFILE REMOVED: {name}")
            except KeyError as exc:
                QMessageBox.warning(self, "Profile failed", str(exc))

        def save_profile(self, profile, original_name: str) -> None:
            profiles = self.store.load(resolve=False)
            if profile.name != original_name and any(item.name == profile.name for item in profiles):
                raise ValueError(f"profile already exists: {profile.name}")
            profiles = [item for item in profiles if item.name != original_name]
            profiles.append(profile)
            self.store.save(sorted(profiles, key=lambda item: (item.group, item.name)))

        def select_profile(self, name: str) -> None:
            for item in self.iter_profile_tree_items():
                if item.data(0, Qt.ItemDataRole.UserRole) == name:
                    self.profile_list.setCurrentItem(item)
                    parent = item.parent()
                    while parent is not None:
                        parent.setExpanded(True)
                        parent = parent.parent()
                    return

        def select_profile_tree_label(self, label: str) -> bool:
            for item in self.iter_profile_tree_items():
                if label in item.text(0):
                    self.profile_list.setCurrentItem(item)
                    parent = item.parent()
                    while parent is not None:
                        parent.setExpanded(True)
                        parent = parent.parent()
                    return True
            return False

        def iter_profile_tree_items(self):
            def walk(item):
                yield item
                for child_index in range(item.childCount()):
                    yield from walk(item.child(child_index))

            for index in range(self.profile_list.topLevelItemCount()):
                yield from walk(self.profile_list.topLevelItem(index))

        def filter_profile_tree(self, text: str) -> None:
            needle = text.strip().lower()

            def apply_filter(item) -> bool:
                own_text = item.text(0).lower()
                own_tooltip = item.toolTip(0).lower()
                child_match = False
                for child_index in range(item.childCount()):
                    child_match = apply_filter(item.child(child_index)) or child_match
                item_match = not needle or needle in own_text or needle in own_tooltip or child_match
                item.setHidden(not item_match)
                if item_match and child_match:
                    item.setExpanded(True)
                return item_match

            for index in range(self.profile_list.topLevelItemCount()):
                apply_filter(self.profile_list.topLevelItem(index))

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

        def connect_selected(self, dry_run: bool) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                self.launch_profile(profile, dry_run=dry_run, prefix="DRY RUN" if dry_run else "LAUNCHED")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Launch failed", str(exc))

        def launch_profile(self, profile: Profile, *, dry_run: bool, prefix: str) -> None:
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
                self.open_moba_connected_session_tab(profile, pane_plan, tab_title=tab_title, tab_status=tab_status)
            else:
                self.open_terminal_tab(pane_plan, tab_title=tab_title, tab_status=tab_status)
            self.log.append(f"{prefix}: {pane_plan.printable()}")

        def open_files_selected(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                if self.moba_connected_profile_supported(profile):
                    pane_plan = terminal_plan_for_profile(profile)
                    self.open_moba_connected_session_tab(
                        profile,
                        pane_plan,
                        remote_path=profile.path or "/",
                        tab_title=self.profile_tab_label(profile),
                        tab_status=self.profile_tab_status(),
                    )
                else:
                    pane_plan = terminal_plan_for_sftp_browser(profile)
                    self.open_terminal_tab(pane_plan)
                self.log.append(f"FILES: {pane_plan.printable()}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "SFTP failed", str(exc))

        def open_transfer_queue_selected(self) -> None:
            name = self.selected_profile_name()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "Select a profile first.")
                return
            try:
                profile = self.store.get(name)
                dialog = TransferQueueDialog(profile, self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                plan = dialog.queue_plan()
                self.log.append(f"QUEUE: {plan.printable()}")
                for command in plan.batch_commands:
                    self.log.append(f"  {command}")
                for note in plan.notes:
                    self.log.append(f"  note: {note}")
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Transfer queue failed", str(exc))

        def show_doctor(self) -> None:
            self.log.append(run_doctor().to_json())

        def find_log_text(self) -> None:
            needle = self.search_input.text()
            if not needle:
                return
            if not self.log.find(needle):
                cursor = self.log.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                self.log.setTextCursor(cursor)
                self.log.find(needle)

        def add_welcome_tab(self, *, select: bool | None = None) -> None:
            surface = gui_design_workspace_surface(self.current_design_id())
            box = QWidget()
            box.setObjectName("welcomeHome")
            layout = QVBoxLayout(box)
            layout.setContentsMargins(48, 48, 48, 48)
            layout.addStretch(1)

            if self.current_design_is_moba():
                panel = self.build_moba_home_welcome(surface)
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
                return

            panel = QFrame()
            panel.setObjectName("welcomePanel")
            panel.setMinimumWidth(620)
            panel.setMaximumWidth(780)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(13)

            title_row = QHBoxLayout()
            title_row.setSpacing(18)
            title_row.addStretch(1)
            logo = QLabel(">_")
            logo.setObjectName("welcomeLogo")
            logo.setFixedSize(QSize(64, 48))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_column = QVBoxLayout()
            title_column.setSpacing(3)
            title = QLabel(surface.title)
            title.setObjectName("welcomeTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            subtitle = QLabel(surface.subtitle)
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
            start_button.setIcon(self.style().standardIcon(self.standard_icon("SP_DialogApplyButton")))
            start_button.setMinimumWidth(200)
            recover_button = QPushButton(secondary_action)
            recover_button.setObjectName("mobaHomeAction")
            recover_button.setIcon(self.style().standardIcon(self.standard_icon("SP_BrowserReload")))
            recover_button.setMinimumWidth(218)
            start_button.clicked.connect(self.open_local_terminal_tab)
            recover_button.clicked.connect(self.recover_previous_sessions)
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

            workflow = self.build_product_workflow_evidence()
            panel_layout.addWidget(workflow)

            workspace_evidence = self.build_product_workspace_surface_evidence(surface)
            panel_layout.addWidget(workspace_evidence)

            recent_title = QLabel(f"Recent {gui_design_home_tab_label(self.current_design_id()).lower()}")
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
                    label = QLabel(item)
                    label.setObjectName("recentSessionsLabel")
                    column_layout.addWidget(label)
                recent_grid.addLayout(column_layout)
            panel_layout.addLayout(recent_grid)

            promo = QLabel(surface.footer)
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
            if self.current_design_is_moba():
                self.apply_moba_tab_chrome(
                    index,
                    key="home",
                    icon_key="home",
                    tooltip="Home",
                    closeable=False,
                )

        def build_moba_home_welcome(self, surface) -> QFrame:
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
            panel.setMinimumWidth(chrome.surface_width)
            panel.setMaximumWidth(chrome.surface_width + geometry.live_max_extra_width)

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
            title = QLabel(chrome.title)
            title.setObjectName("mobaHomeTitle")
            title.setProperty("mobaHomeTitleFontSize", geometry.title_font_size)
            title.setProperty("mobaHomeTitleYOffset", geometry.title_y_offset)
            title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            subtitle = QLabel(chrome.subtitle)
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
            start_button.clicked.connect(self.open_local_terminal_tab)
            recover_button.clicked.connect(self.recover_previous_sessions)
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
                    label = QLabel(item)
                    label.setObjectName("mobaRecentSession")
                    label.setProperty("mobaHomeRecentColumn", column_index)
                    label.setProperty("mobaHomeRecentRow", row_index)
                    label.setProperty("mobaHomeRecentItemStep", geometry.recent_item_step)
                    label.setProperty("mobaHomeRecentColumnPadding", geometry.recent_column_padding)
                    column_layout.addWidget(label)
                recent_grid.addLayout(column_layout)
            panel_layout.addLayout(recent_grid)

            footer = QLabel(surface.footer)
            footer.setObjectName("mobaHomeFooter")
            footer.setProperty("mobaHomeFooter", surface.footer)
            footer.setProperty("mobaHomeFooterYOffset", geometry.footer_y_offset)
            footer.setProperty("mobaHomeFooterFontSize", geometry.footer_font_size)
            footer.setProperty("mobaHomeFooterTopMargin", geometry.live_footer_top_margin)
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setContentsMargins(0, geometry.live_footer_top_margin, 0, 0)
            panel_layout.addWidget(footer)
            return panel

        def build_product_workflow_evidence(self) -> QFrame:
            design_id = self.current_design_id()
            cards = gui_design_workflow_cards(design_id)
            snippet_route = gui_design_termius_snippet_route() if design_id == "termius" else None
            inheritance_route = gui_design_mremoteng_inheritance_route() if design_id == "mremoteng" else None
            securecrt_sftp_route = gui_design_securecrt_sftp_tab_route() if design_id == "securecrt" else None
            panel = QFrame()
            panel.setObjectName("productWorkflowEvidence")
            panel.setProperty("designPreset", design_id)
            if snippet_route is not None:
                panel.setProperty("termiusSnippetRouteKey", snippet_route.key)
                panel.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
                panel.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
                panel.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
                panel.setProperty("termiusSnippetRouteTitleObject", snippet_route.workflow_title_object)
                panel.setProperty("termiusSnippetRoutePrimaryObject", snippet_route.workflow_primary_object)
                panel.setProperty("termiusSnippetRouteSecondaryObject", snippet_route.workflow_secondary_object)
                panel.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
                panel.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
                panel.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
                panel.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
                panel.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
                panel.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
                panel.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
                panel.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
                panel.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
                panel.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
            if inheritance_route is not None:
                panel.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                panel.setProperty("mRemoteNgInheritanceRouteRole", inheritance_route.route_role)
                panel.setProperty("mRemoteNgInheritanceRouteWorkflowKey", inheritance_route.workflow_card_key)
                panel.setProperty(
                    "mRemoteNgInheritanceRouteWorkflowCardObject",
                    inheritance_route.workflow_card_object,
                )
                panel.setProperty("mRemoteNgInheritanceRouteTitleObject", inheritance_route.workflow_title_object)
                panel.setProperty("mRemoteNgInheritanceRoutePrimaryObject", inheritance_route.workflow_primary_object)
                panel.setProperty(
                    "mRemoteNgInheritanceRouteSecondaryObject",
                    inheritance_route.workflow_secondary_object,
                )
                panel.setProperty("mRemoteNgInheritanceRoutePropertyGridObject", inheritance_route.property_grid_object)
                panel.setProperty("mRemoteNgInheritanceRoutePropertyRowKey", inheritance_route.property_row_key)
                panel.setProperty("mRemoteNgInheritanceRoutePropertyCellObject", inheritance_route.property_cell_object)
                panel.setProperty("mRemoteNgInheritanceRouteActiveTab", inheritance_route.active_tab_label)
                panel.setProperty("mRemoteNgInheritanceRouteSelectedProfile", inheritance_route.selected_profile_name)
                panel.setProperty("mRemoteNgInheritanceRouteSelectedTreeLabel", inheritance_route.selected_tree_label)
                panel.setProperty("mRemoteNgInheritanceRouteTitle", inheritance_route.workflow_title)
                panel.setProperty("mRemoteNgInheritanceRouteInheritedValue", inheritance_route.inherited_value)
                panel.setProperty("mRemoteNgInheritanceRouteInheritedSource", inheritance_route.inherited_source)
                panel.setProperty("mRemoteNgInheritanceRouteState", inheritance_route.inheritance_state)
                panel.setProperty("mRemoteNgInheritanceRouteRenderSource", inheritance_route.render_source)
            if securecrt_sftp_route is not None:
                panel.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                panel.setProperty("secureCrtSftpTabRouteRole", securecrt_sftp_route.route_role)
                panel.setProperty("secureCrtSftpTabRouteWorkflowKey", securecrt_sftp_route.workflow_card_key)
                panel.setProperty(
                    "secureCrtSftpTabRouteWorkflowCardObject",
                    securecrt_sftp_route.workflow_card_object,
                )
                panel.setProperty("secureCrtSftpTabRouteTitleObject", securecrt_sftp_route.workflow_title_object)
                panel.setProperty("secureCrtSftpTabRoutePrimaryObject", securecrt_sftp_route.workflow_primary_object)
                panel.setProperty(
                    "secureCrtSftpTabRouteSecondaryObject",
                    securecrt_sftp_route.workflow_secondary_object,
                )
                panel.setProperty(
                    "secureCrtSftpTabRouteSessionManagerObject",
                    securecrt_sftp_route.session_manager_object,
                )
                panel.setProperty("secureCrtSftpTabRouteSelectedTreeObject", securecrt_sftp_route.selected_tree_object)
                panel.setProperty("secureCrtSftpTabRouteSelectedProfile", securecrt_sftp_route.selected_profile_name)
                panel.setProperty("secureCrtSftpTabRouteSelectedTreeLabel", securecrt_sftp_route.selected_tree_label)
                panel.setProperty("secureCrtSftpTabRouteActiveTab", securecrt_sftp_route.active_tab_label)
                panel.setProperty("secureCrtSftpTabRouteTabLabel", securecrt_sftp_route.sftp_tab_label)
                panel.setProperty("secureCrtSftpTabRouteStatusStripObject", securecrt_sftp_route.status_strip_object)
                panel.setProperty("secureCrtSftpTabRouteStatusFieldKey", securecrt_sftp_route.status_field_key)
                panel.setProperty("secureCrtSftpTabRouteStatusFieldObject", securecrt_sftp_route.status_field_object)
                panel.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
                panel.setProperty("secureCrtSftpTabRouteTransferState", securecrt_sftp_route.transfer_state)
                panel.setProperty("secureCrtSftpTabRouteRenderSource", securecrt_sftp_route.render_source)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)
            for card in cards[:3]:
                card_frame = QFrame()
                card_frame.setObjectName("productWorkflowCard")
                card_frame.setProperty("workflowKey", card.key)
                card_frame.setMinimumWidth(190)
                if snippet_route is not None and card.key == snippet_route.workflow_card_key:
                    card_frame.setProperty("termiusSnippetRouteKey", snippet_route.key)
                    card_frame.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
                    card_frame.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
                    card_frame.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
                    card_frame.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
                    card_frame.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
                    card_frame.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
                    card_frame.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
                    card_frame.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
                    card_frame.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
                    card_frame.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
                    card_frame.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
                    card_frame.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
                    card_frame.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
                if inheritance_route is not None and card.key == inheritance_route.workflow_card_key:
                    card_frame.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                    card_frame.setProperty("mRemoteNgInheritanceRouteRole", inheritance_route.route_role)
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteWorkflowKey",
                        inheritance_route.workflow_card_key,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteWorkflowCardObject",
                        inheritance_route.workflow_card_object,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteTitleObject",
                        inheritance_route.workflow_title_object,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRoutePrimaryObject",
                        inheritance_route.workflow_primary_object,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteSecondaryObject",
                        inheritance_route.workflow_secondary_object,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRoutePropertyGridObject",
                        inheritance_route.property_grid_object,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRoutePropertyRowKey",
                        inheritance_route.property_row_key,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRoutePropertyCellObject",
                        inheritance_route.property_cell_object,
                    )
                    card_frame.setProperty("mRemoteNgInheritanceRouteActiveTab", inheritance_route.active_tab_label)
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteSelectedProfile",
                        inheritance_route.selected_profile_name,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteSelectedTreeLabel",
                        inheritance_route.selected_tree_label,
                    )
                    card_frame.setProperty("mRemoteNgInheritanceRouteTitle", inheritance_route.workflow_title)
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteInheritedPropertyLabel",
                        inheritance_route.inherited_property_label,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteInheritedValue",
                        inheritance_route.inherited_value,
                    )
                    card_frame.setProperty(
                        "mRemoteNgInheritanceRouteInheritedSource",
                        inheritance_route.inherited_source,
                    )
                    card_frame.setProperty("mRemoteNgInheritanceRouteState", inheritance_route.inheritance_state)
                    card_frame.setProperty("mRemoteNgInheritanceRouteRenderSource", inheritance_route.render_source)
                if securecrt_sftp_route is not None and card.key == securecrt_sftp_route.workflow_card_key:
                    card_frame.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                    card_frame.setProperty("secureCrtSftpTabRouteRole", securecrt_sftp_route.route_role)
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteWorkflowKey",
                        securecrt_sftp_route.workflow_card_key,
                    )
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteWorkflowCardObject",
                        securecrt_sftp_route.workflow_card_object,
                    )
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteStatusStripObject",
                        securecrt_sftp_route.status_strip_object,
                    )
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteStatusFieldKey",
                        securecrt_sftp_route.status_field_key,
                    )
                    card_frame.setProperty("secureCrtSftpTabRouteActiveTab", securecrt_sftp_route.active_tab_label)
                    card_frame.setProperty("secureCrtSftpTabRouteTabLabel", securecrt_sftp_route.sftp_tab_label)
                    card_frame.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteTransferState",
                        securecrt_sftp_route.transfer_state,
                    )
                    card_frame.setProperty(
                        "secureCrtSftpTabRouteRenderSource",
                        securecrt_sftp_route.render_source,
                    )
                card_layout = QVBoxLayout(card_frame)
                card_layout.setContentsMargins(8, 7, 8, 7)
                card_layout.setSpacing(3)
                title = QLabel(card.title)
                title.setObjectName("productWorkflowTitle")
                primary = QLabel(card.primary)
                primary.setObjectName("productWorkflowPrimary")
                secondary = QLabel(card.secondary)
                secondary.setObjectName("productWorkflowSecondary")
                secondary.setWordWrap(True)
                if snippet_route is not None and card.key == snippet_route.workflow_card_key:
                    title.setProperty("termiusSnippetRouteKey", snippet_route.key)
                    title.setProperty("termiusSnippetRouteTitle", card.title)
                    primary.setProperty("termiusSnippetRouteKey", snippet_route.key)
                    primary.setProperty("termiusSnippetRouteCommand", card.primary)
                    secondary.setProperty("termiusSnippetRouteKey", snippet_route.key)
                    secondary.setProperty("termiusSnippetRouteState", card.secondary)
                if inheritance_route is not None and card.key == inheritance_route.workflow_card_key:
                    title.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                    title.setProperty("mRemoteNgInheritanceRouteTitle", card.title)
                    primary.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                    primary.setProperty("mRemoteNgInheritanceRouteState", card.primary)
                    secondary.setProperty("mRemoteNgInheritanceRouteKey", inheritance_route.key)
                    secondary.setProperty("mRemoteNgInheritanceRoutePropertyGridObject", inheritance_route.property_grid_object)
                if securecrt_sftp_route is not None and card.key == securecrt_sftp_route.workflow_card_key:
                    title.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                    title.setProperty("secureCrtSftpTabRouteTitle", card.title)
                    primary.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                    primary.setProperty("secureCrtSftpTabRouteTransferState", card.primary)
                    secondary.setProperty("secureCrtSftpTabRouteKey", securecrt_sftp_route.key)
                    secondary.setProperty("secureCrtSftpTabRouteStatus", securecrt_sftp_route.status_value)
                card_layout.addWidget(title)
                card_layout.addWidget(primary)
                card_layout.addWidget(secondary)
                layout.addWidget(card_frame)
            return panel

        def build_product_workspace_surface_evidence(self, surface) -> QFrame:
            selection_route = gui_design_preset_selection_route(self.current_design_id())
            panel = QFrame()
            panel.setObjectName("productWorkspaceSurface")
            panel.setProperty("designPreset", self.current_design_id())
            self.apply_preset_selection_route_properties(panel, selection_route)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(10, 9, 10, 9)
            layout.setSpacing(8)

            header = QHBoxLayout()
            header.setSpacing(8)
            title = QLabel(surface.title)
            title.setObjectName("productWorkspaceTitle")
            state = QLabel(surface.primary_state)
            state.setObjectName("productWorkspaceState")
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(state)
            layout.addLayout(header)

            layout.addWidget(self.build_product_reference_state_evidence())
            if self.current_design_id() == "termius":
                layout.addWidget(self.build_termius_header_chips_evidence())
                layout.addWidget(self.build_termius_host_identity_strip_evidence())
                layout.addWidget(self.build_termius_files_browser_evidence())
            if self.current_design_id() == "remmina":
                layout.addWidget(self.build_remmina_viewer_controls_evidence())
                layout.addWidget(self.build_remmina_sftp_transfer_evidence())
            if self.current_design_id() == "mremoteng":
                layout.addWidget(self.build_mremoteng_document_controls_evidence())
                layout.addWidget(self.build_mremoteng_property_grid_evidence())
            if self.current_design_id() == "securecrt":
                layout.addWidget(self.build_securecrt_session_status_strip_evidence())
                layout.addWidget(self.build_securecrt_sftp_browser_evidence())

            panes = QHBoxLayout()
            panes.setSpacing(8)
            primary = self.build_product_workspace_pane(
                "productWorkspacePrimaryPane",
                surface.primary_title,
                surface.command_line,
                surface.detail_lines,
            )
            secondary = self.build_product_workspace_pane(
                "productWorkspaceSecondaryPane",
                surface.secondary_title,
                surface.secondary_state,
                surface.activity_lines,
            )
            panes.addWidget(primary, 3)
            panes.addWidget(secondary, 2)
            layout.addLayout(panes)
            if self.current_design_id() == "securecrt":
                layout.addWidget(self.build_securecrt_command_window_evidence())
            return panel

        def build_mremoteng_document_controls_evidence(self) -> QFrame:
            chrome = gui_design_mremoteng_document_toolbar_chrome()
            route = gui_design_mremoteng_connection_document_route()
            filter_route = gui_design_mremoteng_document_filter_route()
            state = gui_design_interaction_state("mremoteng")
            panel = QFrame()
            panel.setObjectName("mRemoteNgDocumentControls")
            panel.setProperty("designPreset", "mremoteng")
            panel.setProperty("mRemoteNgConnectionRouteKey", route.key)
            panel.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
            panel.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
            panel.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
            panel.setProperty("mRemoteNgConnectionRoutePropertyGridObject", route.property_grid_object)
            panel.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
            panel.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
            panel.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
            panel.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
            panel.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
            panel.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
            panel.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
            filter_route_properties = {
                "mRemoteNgDocumentFilterRouteKey": filter_route.key,
                "mRemoteNgDocumentFilterRouteRole": filter_route.route_role,
                "mRemoteNgDocumentFilterRouteDocumentControlsObject": filter_route.document_controls_object,
                "mRemoteNgDocumentFilterRouteFilterObject": filter_route.filter_object,
                "mRemoteNgDocumentFilterRouteSelectedTreeObject": filter_route.selected_tree_object,
                "mRemoteNgDocumentFilterRouteSelectedProfile": filter_route.selected_profile_name,
                "mRemoteNgDocumentFilterRouteMatchedTreeLabel": filter_route.selected_tree_label,
                "mRemoteNgDocumentFilterRouteMatchedProtocol": filter_route.matched_protocol,
                "mRemoteNgDocumentFilterRouteMatchedState": filter_route.matched_state,
                "mRemoteNgDocumentFilterRouteQuery": filter_route.expected_query,
                "mRemoteNgDocumentFilterRoutePlaceholder": filter_route.expected_placeholder,
                "mRemoteNgDocumentFilterRouteActiveTab": filter_route.active_tab_label,
                "mRemoteNgDocumentFilterRouteSignal": filter_route.change_signal,
                "mRemoteNgDocumentFilterRouteHandler": filter_route.handler_name,
                "mRemoteNgDocumentFilterRouteRenderSource": filter_route.render_source,
            }
            for property_name, property_value in filter_route_properties.items():
                panel.setProperty(property_name, property_value)
            panel.setProperty("mRemoteNgDocumentTitleWidth", chrome.title_width)
            panel.setProperty("mRemoteNgDocumentStaticHeight", chrome.static_height)
            panel.setProperty("mRemoteNgDocumentStaticButtonStartX", chrome.static_button_start_x)
            panel.setProperty("mRemoteNgDocumentStaticButtonGap", chrome.static_button_gap)
            panel.setProperty("mRemoteNgDocumentStaticFilterWidth", chrome.static_filter_width)
            panel.setProperty("mRemoteNgDocumentStaticFilterY", chrome.static_filter_y)
            panel.setProperty("mRemoteNgDocumentStaticFilterHeight", chrome.static_filter_height)
            panel.setProperty("mRemoteNgDocumentLiveSpacing", chrome.live_spacing)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(
                chrome.live_margin_left,
                chrome.live_margin_top,
                chrome.live_margin_right,
                chrome.live_margin_bottom,
            )
            layout.setSpacing(chrome.live_spacing)

            title = QLabel(chrome.title)
            title.setObjectName("mRemoteNgDocumentTitle")
            title.setMinimumWidth(chrome.title_width)
            title.setMaximumWidth(chrome.title_width)
            layout.addWidget(title)
            for control in gui_design_mremoteng_document_controls():
                button = QToolButton()
                button.setObjectName("mRemoteNgDocumentControl")
                button.setProperty("mRemoteNgDocumentControlKey", control.key)
                button.setProperty("mRemoteNgDocumentIconKey", control.icon_key)
                button.setProperty("mRemoteNgDocumentStaticWidth", control.static_width)
                button.setProperty("mRemoteNgDocumentStaticY", control.static_y)
                button.setProperty("mRemoteNgDocumentStaticHeight", control.static_height)
                button.setProperty("mRemoteNgDocumentStaticIconX", control.static_icon_x)
                button.setProperty("mRemoteNgDocumentStaticIconY", control.static_icon_y)
                button.setProperty("mRemoteNgDocumentStaticIconSize", control.static_icon_size)
                button.setProperty("mRemoteNgDocumentStaticLabelX", control.static_label_x)
                button.setProperty("mRemoteNgDocumentStaticLabelY", control.static_label_y)
                button.setProperty("mRemoteNgDocumentLiveIconSize", control.live_icon_size)
                button.setProperty("mRemoteNgDocumentLiveMinWidth", control.live_min_width)
                button.setProperty("mRemoteNgDocumentLiveButtonHeight", control.live_button_height)
                button.setProperty("mRemoteNgDocumentRenderSource", control.render_source)
                if control.key == route.document_control_key:
                    button.setProperty("mRemoteNgConnectionRouteKey", route.key)
                    button.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
                    button.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
                    button.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
                    button.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
                    button.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
                    button.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
                    button.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                    button.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
                    button.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
                    button.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                    button.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                    button.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
                    button.setProperty(route.control_active_property, "true")
                else:
                    button.setProperty(route.control_active_property, "false")
                button.setText(control.label)
                button.setToolTip(control.tooltip)
                control_state = "checked" if control.key == "external-tool" and state.checked_toolbar_key == "files" else "normal"
                button.setCheckable(control_state == "checked")
                button.setChecked(control_state == "checked")
                self.set_interaction_state(button, control_state)
                button.setIcon(self.mremoteng_document_control_icon(control.icon_key, size=control.live_icon_size))
                button.setIconSize(QSize(control.live_icon_size, control.live_icon_size))
                button.setMinimumWidth(control.live_min_width)
                button.setMinimumHeight(control.live_button_height)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.clicked.connect(
                    lambda _checked=False, label=control.label: self.statusBar().showMessage(
                        f"mRemoteNG document control: {label}"
                    )
                )
                layout.addWidget(button)
            layout.addStretch(1)

            filter_input = QLineEdit()
            filter_input.setObjectName("mRemoteNgDocumentFilter")
            filter_input.setPlaceholderText(chrome.filter_placeholder)
            filter_input.setProperty("mRemoteNgDocumentFilterWidth", chrome.live_filter_width)
            filter_input.setProperty("mRemoteNgDocumentFilterHeight", chrome.live_filter_height)
            for property_name, property_value in filter_route_properties.items():
                filter_input.setProperty(property_name, property_value)
            filter_input.setMinimumWidth(chrome.live_filter_width)
            filter_input.setMaximumWidth(chrome.live_filter_width)
            filter_input.setMinimumHeight(chrome.live_filter_height)
            self.mremoteng_document_filter = filter_input
            self.set_interaction_state(
                filter_input,
                "focused" if state.focused_control == "tree-filter" else "normal",
            )
            filter_input.textChanged.connect(self.filter_profile_tree)
            layout.addWidget(filter_input)
            return panel

        def mremoteng_document_control_icon(self, icon_key: str, *, size: int) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_mremoteng_document_control_icon(painter, icon_key, size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_mremoteng_document_control_icon(self, painter: QPainter, icon_key: str, size: int) -> None:
            primary = QColor("#2f6fb1")
            dark = QColor("#35516a")
            fill = QColor("#e8edf3")
            painter.setPen(QPen(primary, 1))
            painter.setBrush(QBrush(fill))
            if icon_key == "database":
                painter.drawEllipse(2, 2, size - 4, 4)
                painter.drawRect(2, 4, size - 4, size - 7)
                painter.drawArc(2, size - 6, size - 4, 4, 0, -180 * 16)
                painter.drawLine(2, 7, size - 2, 7)
                return
            if icon_key == "ssh":
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(1, 4, 5, 5)
                painter.drawLine(6, 6, size - 2, 6)
                painter.drawLine(size - 5, 6, size - 5, 10)
                painter.drawLine(size - 2, 6, size - 2, 9)
                return
            if icon_key == "external":
                painter.drawRect(1, 4, size - 6, size - 6)
                painter.setPen(QPen(dark, 1))
                painter.drawLine(size - 7, 2, size - 2, 2)
                painter.drawLine(size - 2, 2, size - 2, 7)
                painter.drawLine(size - 8, 8, size - 2, 2)
                return
            if icon_key == "rdp":
                painter.drawRect(1, 3, size - 2, size - 6)
                painter.drawLine(size // 2, size - 3, size // 2, size - 1)
                painter.drawLine(4, size - 1, size - 4, size - 1)
                painter.setPen(QPen(dark, 1))
                painter.drawLine(3, 6, size - 4, 6)
                return
            painter.setPen(QPen(dark, 1))
            painter.drawText(2, size - 3, icon_key[:1].upper())

        def build_mremoteng_property_grid_evidence(self) -> QFrame:
            chrome = gui_design_mremoteng_property_grid_chrome()
            route = gui_design_mremoteng_connection_document_route()
            inheritance_route = gui_design_mremoteng_inheritance_route()
            inheritance_route_properties = {
                "mRemoteNgInheritanceRouteKey": inheritance_route.key,
                "mRemoteNgInheritanceRouteRole": inheritance_route.route_role,
                "mRemoteNgInheritanceRouteWorkflowKey": inheritance_route.workflow_card_key,
                "mRemoteNgInheritanceRouteWorkflowCardObject": inheritance_route.workflow_card_object,
                "mRemoteNgInheritanceRouteTitleObject": inheritance_route.workflow_title_object,
                "mRemoteNgInheritanceRoutePrimaryObject": inheritance_route.workflow_primary_object,
                "mRemoteNgInheritanceRouteSecondaryObject": inheritance_route.workflow_secondary_object,
                "mRemoteNgInheritanceRoutePropertyGridObject": inheritance_route.property_grid_object,
                "mRemoteNgInheritanceRoutePropertyRowKey": inheritance_route.property_row_key,
                "mRemoteNgInheritanceRoutePropertyCellObject": inheritance_route.property_cell_object,
                "mRemoteNgInheritanceRouteActiveTab": inheritance_route.active_tab_label,
                "mRemoteNgInheritanceRouteSelectedProfile": inheritance_route.selected_profile_name,
                "mRemoteNgInheritanceRouteSelectedTreeLabel": inheritance_route.selected_tree_label,
                "mRemoteNgInheritanceRouteTitle": inheritance_route.workflow_title,
                "mRemoteNgInheritanceRouteInheritedPropertyLabel": inheritance_route.inherited_property_label,
                "mRemoteNgInheritanceRouteInheritedValue": inheritance_route.inherited_value,
                "mRemoteNgInheritanceRouteInheritedSource": inheritance_route.inherited_source,
                "mRemoteNgInheritanceRouteState": inheritance_route.inheritance_state,
                "mRemoteNgInheritanceRouteRenderSource": inheritance_route.render_source,
            }
            panel = QFrame()
            panel.setObjectName("mRemoteNgPropertyGrid")
            panel.setProperty("designPreset", "mremoteng")
            panel.setProperty("mRemoteNgPropertyColumnKeys", [column.key for column in chrome.columns])
            panel.setProperty("mRemoteNgPropertyRowKeys", [row.key for row in chrome.rows])
            panel.setProperty("mRemoteNgConnectionRouteKey", route.key)
            panel.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
            panel.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
            panel.setProperty("mRemoteNgConnectionRouteSelectedTreeLabel", route.selected_tree_label)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlsObject", route.document_controls_object)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlKey", route.document_control_key)
            panel.setProperty("mRemoteNgConnectionRouteDocumentControlObject", route.document_control_object)
            panel.setProperty("mRemoteNgConnectionRoutePropertyGridObject", route.property_grid_object)
            panel.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
            panel.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
            panel.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
            panel.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
            panel.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
            panel.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
            panel.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
            for property_name, property_value in inheritance_route_properties.items():
                panel.setProperty(property_name, property_value)
            panel.setMaximumHeight(176)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(7, 6, 7, 6)
            layout.setSpacing(4)

            title_row = QHBoxLayout()
            title = QLabel(chrome.title)
            title.setObjectName("mRemoteNgPropertyGridTitle")
            scope = QLabel(chrome.scope_label)
            scope.setObjectName("mRemoteNgPropertyGridScope")
            scope.setProperty("mRemoteNgPropertyScope", chrome.scope_label)
            state = QLabel(chrome.inheritance_label)
            state.setObjectName("mRemoteNgPropertyGridScope")
            state.setProperty("mRemoteNgPropertyInheritanceLabel", chrome.inheritance_label)
            title_row.addWidget(title)
            title_row.addWidget(scope)
            title_row.addStretch(1)
            title_row.addWidget(state)
            layout.addLayout(title_row)

            header = QHBoxLayout()
            header.setSpacing(3)
            for column in chrome.columns:
                label = QLabel(column.label)
                label.setObjectName("mRemoteNgPropertyGridColumn")
                label.setProperty("mRemoteNgPropertyColumnKey", column.key)
                label.setProperty("mRemoteNgPropertyColumnWidth", column.static_width)
                label.setMinimumWidth(max(72, min(column.static_width, 190)))
                header.addWidget(label)
            layout.addLayout(header)

            for row in chrome.rows:
                row_frame = QFrame()
                row_frame.setObjectName("mRemoteNgPropertyGridRow")
                row_frame.setProperty("mRemoteNgPropertyRowKey", row.key)
                row_frame.setProperty("mRemoteNgPropertyInherited", "true" if row.inherited else "false")
                row_frame.setProperty("inherited", "true" if row.inherited else "false")
                if row.key == route.property_row_key:
                    row_frame.setProperty("mRemoteNgConnectionRouteKey", route.key)
                    row_frame.setProperty("mRemoteNgConnectionRouteRole", route.route_role)
                    row_frame.setProperty("mRemoteNgConnectionRouteSelectedProfile", route.selected_profile_name)
                    row_frame.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                    row_frame.setProperty("mRemoteNgConnectionRouteProtocol", route.protocol)
                    row_frame.setProperty("mRemoteNgConnectionRouteState", route.workspace_state)
                    row_frame.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                    row_frame.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
                    row_frame.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                    row_frame.setProperty("mRemoteNgConnectionRouteRenderSource", route.render_source)
                if row.key == inheritance_route.property_row_key:
                    for property_name, property_value in inheritance_route_properties.items():
                        row_frame.setProperty(property_name, property_value)
                    row_frame.setProperty(inheritance_route.workflow_key_property, inheritance_route.workflow_card_key)
                    row_frame.setProperty(inheritance_route.active_tab_property, inheritance_route.active_tab_label)
                    row_frame.setProperty(inheritance_route.status_property, inheritance_route.inheritance_state)
                    row_frame.setProperty(
                        inheritance_route.inherited_value_property,
                        inheritance_route.inherited_value,
                    )
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(3)
                values = {
                    "property": row.property_label,
                    "inherited": row.inherited_from,
                    "effective": row.effective_value,
                    "source": row.source,
                }
                for column in chrome.columns:
                    cell = QLabel(values[column.key])
                    cell.setObjectName("mRemoteNgPropertyGridCell")
                    cell.setProperty("mRemoteNgPropertyRowKey", row.key)
                    cell.setProperty("mRemoteNgPropertyColumnKey", column.key)
                    cell.setProperty("mRemoteNgPropertyCellValue", values[column.key])
                    if row.key == route.property_row_key:
                        cell.setProperty("mRemoteNgConnectionRouteKey", route.key)
                        cell.setProperty("mRemoteNgConnectionRouteActiveTab", route.active_tab_label)
                        cell.setProperty("mRemoteNgConnectionRoutePropertyRowKey", route.property_row_key)
                        cell.setProperty("mRemoteNgConnectionRoutePropertyCellObject", route.property_cell_object)
                        cell.setProperty("mRemoteNgConnectionRoutePropertyValue", route.property_value)
                    if row.key == inheritance_route.property_row_key:
                        for property_name, property_value in inheritance_route_properties.items():
                            cell.setProperty(property_name, property_value)
                        cell.setProperty(inheritance_route.workflow_key_property, inheritance_route.workflow_card_key)
                        cell.setProperty(inheritance_route.active_tab_property, inheritance_route.active_tab_label)
                        cell.setProperty(inheritance_route.status_property, inheritance_route.inheritance_state)
                        cell.setProperty(
                            inheritance_route.inherited_value_property,
                            inheritance_route.inherited_value,
                        )
                    cell.setMinimumWidth(max(72, min(column.static_width, 190)))
                    cell.setToolTip(f"{row.property_label}: {values[column.key]}")
                    row_layout.addWidget(cell)
                layout.addWidget(row_frame)
            return panel

        def build_termius_header_chips_evidence(self) -> QFrame:
            sync_route = gui_design_termius_sync_route()
            port_forward_route = gui_design_termius_port_forward_route()
            panel = QFrame()
            panel.setObjectName("termiusHeaderChips")
            panel.setProperty("designPreset", "termius")
            panel.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
            panel.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
            panel.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
            panel.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
            panel.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
            panel.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
            panel.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
            panel.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
            panel.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
            panel.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
            panel.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
            panel.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
            panel.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
            panel.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
            panel.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
            panel.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(8)
            layout.addStretch(1)
            for chip in gui_design_termius_header_chips():
                label = QLabel(chip.label)
                label.setObjectName("termiusHeaderChip")
                label.setProperty("termiusHeaderChipKey", chip.key)
                label.setToolTip(chip.tooltip)
                label.setMinimumWidth(104)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if chip.key == sync_route.header_chip_key:
                    label.setProperty("termiusSyncRouteKey", sync_route.key)
                    label.setProperty("termiusSyncRouteRole", sync_route.route_role)
                    label.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                    label.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                    label.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                    label.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                    label.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                    label.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                    label.setProperty("termiusSyncRouteState", sync_route.sync_state)
                    label.setProperty("termiusSyncRouteChipLabel", chip.label)
                    label.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
                if chip.key == port_forward_route.header_chip_key:
                    label.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
                    label.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
                    label.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
                    label.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
                    label.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
                    label.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
                    label.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
                    label.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
                    label.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
                    label.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
                    label.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
                    label.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
                    label.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
                    label.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
                    label.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
                    label.setProperty(port_forward_route.chip_label_property, chip.label)
                    label.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
                layout.addWidget(label)
            return panel

        def build_termius_host_identity_strip_evidence(self) -> QFrame:
            strip = gui_design_termius_host_identity_strip()
            sync_route = gui_design_termius_sync_route()
            host_route = gui_design_termius_host_selection_route()
            port_forward_route = gui_design_termius_port_forward_route()
            snippet_route = gui_design_termius_snippet_route()
            files_route = gui_design_termius_files_browser_route()
            panel = QFrame()
            panel.setObjectName("termiusHostIdentityStrip")
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
            panel.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
            panel.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
            panel.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
            panel.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
            panel.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
            panel.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
            panel.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
            panel.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
            panel.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
            panel.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
            panel.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
            panel.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
            panel.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
            panel.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
            panel.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
            panel.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
            panel.setProperty("termiusSnippetRouteKey", snippet_route.key)
            panel.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
            panel.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
            panel.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
            panel.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
            panel.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
            panel.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
            panel.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
            panel.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
            panel.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
            panel.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
            panel.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
            panel.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
            panel.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
            panel.setProperty("termiusFilesRouteKey", files_route.key)
            panel.setProperty("termiusFilesRouteRole", files_route.route_role)
            panel.setProperty("termiusFilesRouteHostSelectionKey", files_route.host_selection_route_key)
            panel.setProperty("termiusFilesRouteIdentityObject", files_route.host_identity_object)
            panel.setProperty("termiusFilesRouteIdentityFieldKey", files_route.identity_field_key)
            panel.setProperty("termiusFilesRouteIdentityCellObject", files_route.identity_cell_object)
            panel.setProperty("termiusFilesRouteBrowserObject", files_route.files_browser_object)
            panel.setProperty("termiusFilesRouteActiveTab", files_route.active_tab_label)
            panel.setProperty("termiusFilesRouteSelectedProfile", files_route.selected_profile_name)
            panel.setProperty("termiusFilesRouteSelectedTreeLabel", files_route.selected_tree_label)
            panel.setProperty("termiusFilesRouteState", files_route.files_state)
            panel.setProperty("termiusFilesRoutePath", files_route.remote_path)
            panel.setProperty("termiusFilesRouteQueueState", files_route.transfer_status)
            panel.setProperty("termiusFilesRouteRenderSource", files_route.render_source)
            panel.setProperty("termiusHostIdentityFieldKeys", [field.key for field in strip.fields])
            panel.setProperty("termiusHostIdentityTitleWidth", strip.title_width)
            panel.setProperty("termiusHostIdentityStaticTitleX", strip.static_title_x)
            panel.setProperty("termiusHostIdentityStaticTitleY", strip.static_title_y)
            panel.setProperty("termiusHostIdentityStaticCellStartX", strip.static_cell_start_x)
            panel.setProperty("termiusHostIdentityStaticCellGap", strip.static_cell_gap)
            panel.setProperty("termiusHostIdentityLiveSpacing", strip.live_spacing)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(
                strip.live_margin_left,
                strip.live_margin_top,
                strip.live_margin_right,
                strip.live_margin_bottom,
            )
            layout.setSpacing(strip.live_spacing)

            title = QLabel(strip.title)
            title.setObjectName("termiusHostIdentityTitle")
            title.setMinimumWidth(strip.title_width)
            title.setMaximumWidth(strip.title_width)
            layout.addWidget(title)
            for field in strip.fields:
                cell = QLabel(f"{field.label}: {field.value}")
                cell.setObjectName("termiusHostIdentityCell")
                cell.setProperty("termiusHostIdentityKey", field.key)
                cell.setProperty("termiusHostIdentityLabel", field.label)
                cell.setProperty("termiusHostIdentityValue", field.value)
                cell.setProperty("termiusHostIdentityWidth", field.static_width)
                cell.setProperty("termiusHostIdentityRole", field.role)
                cell.setProperty("termiusHostIdentityStaticY", field.static_y)
                cell.setProperty("termiusHostIdentityStaticHeight", field.static_height)
                cell.setProperty("termiusHostIdentityStaticLabelX", field.static_label_x)
                cell.setProperty("termiusHostIdentityStaticLabelY", field.static_label_y)
                cell.setProperty("termiusHostIdentityStaticValueX", field.static_value_x)
                cell.setProperty("termiusHostIdentityStaticValueY", field.static_value_y)
                cell.setProperty("termiusHostIdentityLiveMinWidth", field.live_min_width)
                cell.setProperty("termiusHostIdentityLiveCellHeight", field.live_cell_height)
                cell.setToolTip(field.tooltip)
                cell.setMinimumWidth(field.live_min_width)
                cell.setMinimumHeight(field.live_cell_height)
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                if field.key == sync_route.identity_field_key:
                    cell.setProperty("termiusSyncRouteKey", sync_route.key)
                    cell.setProperty("termiusSyncRouteRole", sync_route.route_role)
                    cell.setProperty("termiusSyncRouteHostsActionKey", sync_route.hosts_action_key)
                    cell.setProperty("termiusSyncRouteHostsActionObject", sync_route.hosts_action_object)
                    cell.setProperty("termiusSyncRouteHeaderChipKey", sync_route.header_chip_key)
                    cell.setProperty("termiusSyncRouteHeaderChipObject", sync_route.header_chip_object)
                    cell.setProperty("termiusSyncRouteIdentityFieldKey", sync_route.identity_field_key)
                    cell.setProperty("termiusSyncRouteIdentityCellObject", sync_route.identity_cell_object)
                    cell.setProperty("termiusSyncRouteState", sync_route.sync_state)
                    cell.setProperty("termiusSyncRouteIdentityValue", field.value)
                    cell.setProperty("termiusSyncRouteRenderSource", sync_route.render_source)
                if field.key == host_route.identity_field_key:
                    cell.setProperty("termiusHostRouteKey", host_route.key)
                    cell.setProperty("termiusHostRouteRole", host_route.route_role)
                    cell.setProperty("termiusHostRouteSelectedProfile", host_route.selected_profile_name)
                    cell.setProperty("termiusHostRouteSelectedTreeLabel", host_route.selected_tree_label)
                    cell.setProperty("termiusHostRouteActiveTab", host_route.active_tab_label)
                    cell.setProperty("termiusHostRouteTarget", host_route.target_value)
                    cell.setProperty("termiusHostRouteProtocol", host_route.protocol_value)
                    cell.setProperty("termiusHostRouteIdentityValue", host_route.host_value)
                    cell.setProperty("termiusHostRouteRenderSource", host_route.render_source)
                if field.key == port_forward_route.identity_field_key:
                    cell.setProperty("termiusPortForwardRouteKey", port_forward_route.key)
                    cell.setProperty("termiusPortForwardRouteRole", port_forward_route.route_role)
                    cell.setProperty("termiusPortForwardRouteHeaderChipKey", port_forward_route.header_chip_key)
                    cell.setProperty("termiusPortForwardRouteHeaderChipObject", port_forward_route.header_chip_object)
                    cell.setProperty("termiusPortForwardRouteIdentityObject", port_forward_route.host_identity_object)
                    cell.setProperty("termiusPortForwardRouteIdentityFieldKey", port_forward_route.identity_field_key)
                    cell.setProperty("termiusPortForwardRouteIdentityCellObject", port_forward_route.identity_cell_object)
                    cell.setProperty("termiusPortForwardRouteActiveTab", port_forward_route.active_tab_label)
                    cell.setProperty("termiusPortForwardRouteSelectedProfile", port_forward_route.selected_profile_name)
                    cell.setProperty("termiusPortForwardRouteForwardValue", port_forward_route.forward_value)
                    cell.setProperty("termiusPortForwardRouteState", port_forward_route.forward_state)
                    cell.setProperty("termiusPortForwardRouteLocalPort", port_forward_route.local_port)
                    cell.setProperty("termiusPortForwardRouteRemoteHost", port_forward_route.remote_host)
                    cell.setProperty("termiusPortForwardRouteRemotePort", port_forward_route.remote_port)
                    cell.setProperty("termiusPortForwardRouteStatusSegment", port_forward_route.status_segment)
                    cell.setProperty("termiusPortForwardRouteIdentityValue", field.value)
                    cell.setProperty("termiusPortForwardRouteRenderSource", port_forward_route.render_source)
                if field.key == snippet_route.identity_field_key:
                    cell.setProperty("termiusSnippetRouteKey", snippet_route.key)
                    cell.setProperty("termiusSnippetRouteRole", snippet_route.route_role)
                    cell.setProperty("termiusSnippetRouteWorkflowKey", snippet_route.workflow_card_key)
                    cell.setProperty("termiusSnippetRouteWorkflowCardObject", snippet_route.workflow_card_object)
                    cell.setProperty("termiusSnippetRouteIdentityObject", snippet_route.host_identity_object)
                    cell.setProperty("termiusSnippetRouteIdentityFieldKey", snippet_route.identity_field_key)
                    cell.setProperty("termiusSnippetRouteIdentityCellObject", snippet_route.identity_cell_object)
                    cell.setProperty("termiusSnippetRouteActiveTab", snippet_route.active_tab_label)
                    cell.setProperty("termiusSnippetRouteSelectedProfile", snippet_route.selected_profile_name)
                    cell.setProperty("termiusSnippetRouteTitle", snippet_route.workflow_title)
                    cell.setProperty("termiusSnippetRouteCommand", snippet_route.snippet_command)
                    cell.setProperty("termiusSnippetRouteState", snippet_route.snippet_state)
                    cell.setProperty("termiusSnippetRouteDetailLine", snippet_route.detail_line)
                    cell.setProperty("termiusSnippetRouteIdentityValue", field.value)
                    cell.setProperty("termiusSnippetRouteRenderSource", snippet_route.render_source)
                if field.key == files_route.identity_field_key:
                    cell.setProperty("termiusFilesRouteKey", files_route.key)
                    cell.setProperty("termiusFilesRouteRole", files_route.route_role)
                    cell.setProperty("termiusFilesRouteHostSelectionKey", files_route.host_selection_route_key)
                    cell.setProperty("termiusFilesRouteIdentityObject", files_route.host_identity_object)
                    cell.setProperty("termiusFilesRouteIdentityFieldKey", files_route.identity_field_key)
                    cell.setProperty("termiusFilesRouteIdentityCellObject", files_route.identity_cell_object)
                    cell.setProperty("termiusFilesRouteBrowserObject", files_route.files_browser_object)
                    cell.setProperty("termiusFilesRouteActiveTab", files_route.active_tab_label)
                    cell.setProperty("termiusFilesRouteSelectedProfile", files_route.selected_profile_name)
                    cell.setProperty("termiusFilesRouteSelectedTreeLabel", files_route.selected_tree_label)
                    cell.setProperty("termiusFilesRouteIdentityValue", field.value)
                    cell.setProperty("termiusFilesRouteState", files_route.files_state)
                    cell.setProperty("termiusFilesRoutePath", files_route.remote_path)
                    cell.setProperty("termiusFilesRouteQueueState", files_route.transfer_status)
                    cell.setProperty("termiusFilesRouteRenderSource", files_route.render_source)
                layout.addWidget(cell)
            layout.addStretch(1)
            return panel

        def build_termius_files_browser_evidence(self) -> QFrame:
            route = gui_design_termius_files_browser_route()
            actions_value = "|".join(route.toolbar_actions)
            route_props = {
                "termiusFilesRouteKey": route.key,
                "termiusFilesRouteRole": route.route_role,
                "termiusFilesRouteHostSelectionKey": route.host_selection_route_key,
                "termiusFilesRouteIdentityObject": route.host_identity_object,
                "termiusFilesRouteIdentityFieldKey": route.identity_field_key,
                "termiusFilesRouteIdentityCellObject": route.identity_cell_object,
                "termiusFilesRouteBrowserObject": route.files_browser_object,
                "termiusFilesRouteToolbarObject": route.toolbar_object,
                "termiusFilesRoutePathObject": route.path_object,
                "termiusFilesRouteTableObject": route.table_object,
                "termiusFilesRouteRowObject": route.row_object,
                "termiusFilesRouteQueueObject": route.queue_object,
                route.active_tab_property: route.active_tab_label,
                "termiusFilesRouteSelectedProfile": route.selected_profile_name,
                "termiusFilesRouteSelectedTreeLabel": route.selected_tree_label,
                route.identity_value_property: route.files_state,
                "termiusFilesRouteState": route.files_state,
                route.path_property: route.remote_path,
                route.toolbar_actions_property: actions_value,
                "termiusFilesRouteActiveRowName": route.active_row_name,
                "termiusFilesRouteQueueLabel": route.transfer_queue_label,
                "termiusFilesRouteQueueState": route.transfer_status,
                "termiusFilesRouteRenderSource": route.render_source,
            }
            panel = QFrame()
            panel.setObjectName(route.files_browser_object)
            for property_name, value in route_props.items():
                panel.setProperty(property_name, value)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 7, 8, 7)
            layout.setSpacing(5)

            header = QHBoxLayout()
            title = QLabel(f"Files - {route.selected_profile_name}")
            title.setObjectName("termiusFilesTitle")
            title.setProperty("termiusFilesRouteKey", route.key)
            title.setProperty("termiusFilesRouteState", route.files_state)
            queue = QLabel(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
            queue.setObjectName(route.queue_object)
            for property_name, value in route_props.items():
                queue.setProperty(property_name, value)
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(queue)
            layout.addLayout(header)

            toolbar = QFrame()
            toolbar.setObjectName(route.toolbar_object)
            for property_name, value in route_props.items():
                toolbar.setProperty(property_name, value)
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(6)
            for action_key in route.toolbar_actions:
                action = QLabel(action_key.title())
                action.setObjectName("termiusFilesAction")
                action.setProperty("termiusFilesRouteKey", route.key)
                action.setProperty("termiusFilesRouteActionKey", action_key)
                action.setProperty(route.toolbar_actions_property, actions_value)
                toolbar_layout.addWidget(action)
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            path = QLabel(f"Remote path: {route.remote_path}")
            path.setObjectName(route.path_object)
            for property_name, value in route_props.items():
                path.setProperty(property_name, value)
            layout.addWidget(path)

            table = QFrame()
            table.setObjectName(route.table_object)
            for property_name, value in route_props.items():
                table.setProperty(property_name, value)
            table_layout = QVBoxLayout(table)
            table_layout.setContentsMargins(0, 0, 0, 0)
            table_layout.setSpacing(2)
            header_row = QLabel("Name        Size     Modified")
            header_row.setObjectName("termiusFilesHeader")
            table_layout.addWidget(header_row)
            for row in route.file_rows:
                row_frame = QFrame()
                row_frame.setObjectName(route.row_object)
                for property_name, value in route_props.items():
                    row_frame.setProperty(property_name, value)
                row_frame.setProperty(route.row_name_property, row.name)
                row_frame.setProperty(route.row_kind_property, row.kind)
                row_frame.setProperty(route.row_selected_property, row.selected)
                row_frame.setProperty("termiusFilesRouteRowKey", row.key)
                row_frame.setProperty("termiusFilesRouteRowSize", row.size)
                row_frame.setProperty("termiusFilesRouteRowModified", row.modified)
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(8)
                name = QLabel(row.name)
                name.setObjectName("termiusFilesRowName")
                size = QLabel(row.size)
                size.setObjectName("termiusFilesRowSize")
                modified = QLabel(row.modified)
                modified.setObjectName("termiusFilesRowModified")
                row_layout.addWidget(name, 2)
                row_layout.addWidget(size, 1)
                row_layout.addWidget(modified, 1)
                table_layout.addWidget(row_frame)
            layout.addWidget(table)
            return panel

        def build_remmina_viewer_controls_evidence(self) -> QFrame:
            route = gui_design_remmina_profile_viewer_route()
            clipboard_route = gui_design_remmina_clipboard_route()
            screenshot_route = gui_design_remmina_screenshot_route()
            panel = QFrame()
            panel.setObjectName("remminaViewerControls")
            panel.setProperty("designPreset", "remmina")
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
            panel.setProperty("remminaClipboardRouteKey", clipboard_route.key)
            panel.setProperty("remminaClipboardRouteRole", clipboard_route.route_role)
            panel.setProperty("remminaClipboardViewerControlsObject", clipboard_route.viewer_controls_object)
            panel.setProperty("remminaClipboardViewerControlKey", clipboard_route.viewer_control_key)
            panel.setProperty("remminaClipboardViewerControlObject", clipboard_route.viewer_control_object)
            panel.setProperty("remminaClipboardRouteActiveTab", clipboard_route.active_tab_label)
            panel.setProperty("remminaClipboardRouteProtocol", clipboard_route.protocol)
            panel.setProperty("remminaClipboardRouteState", clipboard_route.clipboard_state)
            panel.setProperty("remminaClipboardRouteStatusSegment", clipboard_route.status_segment)
            panel.setProperty("remminaClipboardRouteDetailLine", clipboard_route.detail_line)
            panel.setProperty("remminaClipboardRouteActivityLine", clipboard_route.activity_line)
            panel.setProperty("remminaClipboardRouteRenderSource", clipboard_route.render_source)
            panel.setProperty("remminaScreenshotRouteKey", screenshot_route.key)
            panel.setProperty("remminaScreenshotRouteRole", screenshot_route.route_role)
            panel.setProperty("remminaScreenshotViewerControlsObject", screenshot_route.viewer_controls_object)
            panel.setProperty("remminaScreenshotViewerControlKey", screenshot_route.viewer_control_key)
            panel.setProperty("remminaScreenshotViewerControlObject", screenshot_route.viewer_control_object)
            panel.setProperty("remminaScreenshotRouteActiveTab", screenshot_route.active_tab_label)
            panel.setProperty("remminaScreenshotRouteProtocol", screenshot_route.protocol)
            panel.setProperty("remminaScreenshotRouteState", screenshot_route.capture_state)
            panel.setProperty("remminaScreenshotRouteArtifact", screenshot_route.capture_artifact)
            panel.setProperty("remminaScreenshotRouteStatusSegment", screenshot_route.status_segment)
            panel.setProperty("remminaScreenshotRouteDetailLine", screenshot_route.detail_line)
            panel.setProperty("remminaScreenshotRouteActivityLine", screenshot_route.activity_line)
            panel.setProperty("remminaScreenshotRouteRenderSource", screenshot_route.render_source)
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(6)
            layout.addStretch(1)
            for control in gui_design_remmina_viewer_controls():
                button = QToolButton()
                button.setObjectName("remminaViewerControl")
                button.setProperty("remminaViewerControlKey", control.key)
                button.setProperty("remminaViewerIconKey", control.icon_key)
                button.setProperty("remminaViewerControlStaticWidth", control.static_width)
                button.setProperty("remminaViewerControlStaticStep", control.static_step)
                button.setProperty("remminaViewerControlStaticY", control.static_y)
                button.setProperty("remminaViewerControlStaticHeight", control.static_height)
                button.setProperty("remminaViewerControlStaticIconX", control.static_icon_x)
                button.setProperty("remminaViewerControlStaticIconSize", control.static_icon_size)
                button.setProperty("remminaViewerControlStaticLabelX", control.static_label_x)
                button.setProperty("remminaViewerControlLiveIconSize", control.live_icon_size)
                button.setProperty("remminaViewerControlLiveMinWidth", control.live_min_width)
                button.setProperty("remminaViewerControlLiveButtonHeight", control.live_button_height)
                button.setProperty("remminaViewerControlRenderSource", control.render_source)
                if control.key == route.viewer_control_key:
                    button.setProperty("remminaProfileViewerRouteKey", route.key)
                    button.setProperty("remminaProfileViewerRouteRole", route.route_role)
                    button.setProperty("remminaProfileViewerSelectedProfileKey", route.selected_profile_key)
                    button.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                    button.setProperty("remminaProfileViewerStatus", route.profile_status)
                    button.setProperty(route.control_active_property, "true")
                else:
                    button.setProperty(route.control_active_property, "false")
                if control.key == clipboard_route.viewer_control_key:
                    button.setProperty("remminaClipboardRouteKey", clipboard_route.key)
                    button.setProperty("remminaClipboardRouteRole", clipboard_route.route_role)
                    button.setProperty(clipboard_route.tab_label_property, clipboard_route.active_tab_label)
                    button.setProperty("remminaClipboardRouteProtocol", clipboard_route.protocol)
                    button.setProperty(clipboard_route.clipboard_state_property, clipboard_route.clipboard_state)
                    button.setProperty("remminaClipboardRouteStatusSegment", clipboard_route.status_segment)
                    button.setProperty("remminaClipboardRouteDetailLine", clipboard_route.detail_line)
                    button.setProperty("remminaClipboardRouteActivityLine", clipboard_route.activity_line)
                    button.setProperty("remminaClipboardRouteRenderSource", clipboard_route.render_source)
                    button.setProperty(clipboard_route.control_active_property, "true")
                else:
                    button.setProperty(clipboard_route.control_active_property, "false")
                if control.key == screenshot_route.viewer_control_key:
                    button.setProperty("remminaScreenshotRouteKey", screenshot_route.key)
                    button.setProperty("remminaScreenshotRouteRole", screenshot_route.route_role)
                    button.setProperty(screenshot_route.tab_label_property, screenshot_route.active_tab_label)
                    button.setProperty("remminaScreenshotRouteProtocol", screenshot_route.protocol)
                    button.setProperty(screenshot_route.capture_state_property, screenshot_route.capture_state)
                    button.setProperty(screenshot_route.capture_artifact_property, screenshot_route.capture_artifact)
                    button.setProperty("remminaScreenshotRouteStatusSegment", screenshot_route.status_segment)
                    button.setProperty("remminaScreenshotRouteDetailLine", screenshot_route.detail_line)
                    button.setProperty("remminaScreenshotRouteActivityLine", screenshot_route.activity_line)
                    button.setProperty("remminaScreenshotRouteRenderSource", screenshot_route.render_source)
                    button.setProperty(screenshot_route.control_active_property, "true")
                else:
                    button.setProperty(screenshot_route.control_active_property, "false")
                button.setText(control.label)
                button.setToolTip(control.tooltip)
                button.setIcon(self.remmina_viewer_control_icon(control.icon_key, size=control.live_icon_size))
                button.setIconSize(QSize(control.live_icon_size, control.live_icon_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                button.setMinimumWidth(control.live_min_width)
                button.setMinimumHeight(control.live_button_height)
                button.clicked.connect(
                    lambda _checked=False, label=control.label: self.statusBar().showMessage(
                        f"Remmina viewer control: {label}"
                    )
                )
                layout.addWidget(button)
            return panel

        def build_remmina_sftp_transfer_evidence(self) -> QFrame:
            route = gui_design_remmina_sftp_transfer_route()
            actions_value = "|".join(route.toolbar_actions)
            route_props = {
                "remminaSftpTransferRouteKey": route.key,
                "remminaSftpTransferRouteRole": route.route_role,
                "remminaSftpTransferRouteProfileListObject": route.profile_list_object,
                "remminaSftpTransferRouteSelectedProfileKey": route.selected_profile_key,
                route.selected_profile_property: route.selected_profile_name,
                "remminaSftpTransferRouteProtocol": route.selected_profile_protocol,
                "remminaSftpTransferRouteStatus": route.selected_profile_status,
                "remminaSftpTransferRouteSelectedProfileObject": route.selected_profile_object,
                "remminaSftpTransferRouteSelectedTreeLabel": route.selected_tree_label,
                "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
                "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
                "remminaSftpTransferRouteToolbarActionObject": route.toolbar_action_object,
                route.tab_label_property: route.active_tab_label,
                "remminaSftpTransferRoutePanelObject": route.transfer_panel_object,
                "remminaSftpTransferRouteToolbarObject": route.toolbar_object,
                "remminaSftpTransferRoutePathObject": route.path_object,
                "remminaSftpTransferRouteTableObject": route.table_object,
                "remminaSftpTransferRouteRowObject": route.row_object,
                "remminaSftpTransferRouteQueueObject": route.queue_object,
                route.path_property: route.remote_path,
                route.toolbar_actions_property: actions_value,
                "remminaSftpTransferRouteActiveRowName": route.active_row_name,
                "remminaSftpTransferRouteQueueLabel": route.transfer_queue_label,
                route.queue_state_property: route.transfer_status,
                "remminaSftpTransferRouteDetailLine": route.detail_line,
                "remminaSftpTransferRouteActivityLine": route.activity_line,
                "remminaSftpTransferRouteRenderSource": route.render_source,
            }
            panel = QFrame()
            panel.setObjectName(route.transfer_panel_object)
            for property_name, value in route_props.items():
                panel.setProperty(property_name, value)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 7, 8, 7)
            layout.setSpacing(5)

            header = QHBoxLayout()
            title = QLabel(f"SFTP transfer - {route.selected_profile_name}")
            title.setObjectName("remminaSftpTransferTitle")
            title.setProperty("remminaSftpTransferRouteKey", route.key)
            queue = QLabel(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
            queue.setObjectName(route.queue_object)
            for property_name, value in route_props.items():
                queue.setProperty(property_name, value)
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(queue)
            layout.addLayout(header)

            toolbar = QFrame()
            toolbar.setObjectName(route.toolbar_object)
            for property_name, value in route_props.items():
                toolbar.setProperty(property_name, value)
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(6)
            for action_key in route.toolbar_actions:
                action = QLabel(action_key.title())
                action.setObjectName("remminaSftpTransferAction")
                action.setProperty("remminaSftpTransferRouteKey", route.key)
                action.setProperty("remminaSftpTransferRouteActionKey", action_key)
                action.setProperty(route.toolbar_actions_property, actions_value)
                toolbar_layout.addWidget(action)
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            path = QLabel(f"Remote path: {route.remote_path}")
            path.setObjectName(route.path_object)
            for property_name, value in route_props.items():
                path.setProperty(property_name, value)
            layout.addWidget(path)

            table = QFrame()
            table.setObjectName(route.table_object)
            for property_name, value in route_props.items():
                table.setProperty(property_name, value)
            table_layout = QVBoxLayout(table)
            table_layout.setContentsMargins(0, 0, 0, 0)
            table_layout.setSpacing(2)
            header_row = QLabel("Name        Size     Modified")
            header_row.setObjectName("remminaSftpTransferHeader")
            table_layout.addWidget(header_row)
            for row in route.file_rows:
                row_frame = QFrame()
                row_frame.setObjectName(route.row_object)
                for property_name, value in route_props.items():
                    row_frame.setProperty(property_name, value)
                row_frame.setProperty(route.row_name_property, row.name)
                row_frame.setProperty(route.row_kind_property, row.kind)
                row_frame.setProperty(route.row_selected_property, row.selected)
                row_frame.setProperty("remminaSftpTransferRouteRowKey", row.key)
                row_frame.setProperty("remminaSftpTransferRouteRowSize", row.size)
                row_frame.setProperty("remminaSftpTransferRouteRowModified", row.modified)
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(8)
                name = QLabel(row.name)
                name.setObjectName("remminaSftpTransferRowName")
                size = QLabel(row.size)
                size.setObjectName("remminaSftpTransferRowSize")
                modified = QLabel(row.modified)
                modified.setObjectName("remminaSftpTransferRowModified")
                row_layout.addWidget(name, 2)
                row_layout.addWidget(size, 1)
                row_layout.addWidget(modified, 1)
                table_layout.addWidget(row_frame)
            layout.addWidget(table)
            return panel

        def remmina_viewer_control_icon(self, icon_key: str, *, size: int) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_remmina_viewer_control_icon(painter, icon_key, size)
            finally:
                painter.end()
            return QIcon(pixmap)

        def draw_remmina_viewer_control_icon(self, painter: QPainter, icon_key: str, size: int) -> None:
            primary = QColor("#2f6fb1")
            dark = QColor("#35516a")
            fill = QColor("#e8edf3")
            painter.setPen(QPen(primary, 1))
            painter.setBrush(QBrush(fill))
            if icon_key == "fit":
                painter.drawRect(2, 2, size - 4, size - 4)
                painter.drawLine(4, 4, 7, 4)
                painter.drawLine(4, 4, 4, 7)
                painter.drawLine(size - 5, size - 5, size - 8, size - 5)
                painter.drawLine(size - 5, size - 5, size - 5, size - 8)
                return
            if icon_key == "scale":
                painter.drawRect(2, 4, size - 4, size - 6)
                painter.setPen(QPen(dark, 1))
                painter.drawText(4, size - 3, "1")
                return
            if icon_key == "clipboard":
                painter.drawRect(4, 3, size - 7, size - 5)
                painter.drawRect(6, 1, size - 11, 4)
                painter.setPen(QPen(dark, 1))
                painter.drawLine(6, 7, size - 5, 7)
                painter.drawLine(6, 10, size - 6, 10)
                return
            if icon_key == "fullscreen":
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(2, 2, size - 4, size - 4)
                painter.drawLine(4, 6, 4, 4)
                painter.drawLine(4, 4, 6, 4)
                painter.drawLine(size - 5, size - 7, size - 5, size - 5)
                painter.drawLine(size - 7, size - 5, size - 5, size - 5)
                return
            if icon_key == "screenshot":
                painter.drawRect(2, 5, size - 4, size - 7)
                painter.drawRect(5, 3, 5, 3)
                painter.setBrush(QBrush(primary))
                painter.drawEllipse(size // 2 - 2, size // 2 - 1, 4, 4)
                return
            painter.drawEllipse(3, 3, size - 6, size - 6)

        def build_securecrt_session_manager_chrome(self) -> QFrame:
            chrome = gui_design_securecrt_session_manager_chrome()
            route = gui_design_securecrt_session_manager_route()
            filter_route = gui_design_securecrt_session_manager_filter_route()
            sftp_route = gui_design_securecrt_sftp_tab_route()
            panel = QFrame()
            panel.setObjectName("secureCrtSessionManagerChrome")
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
            filter_route_properties = {
                "secureCrtSessionFilterRouteKey": filter_route.key,
                "secureCrtSessionFilterRouteRole": filter_route.route_role,
                "secureCrtSessionFilterRouteSessionManagerObject": filter_route.session_manager_object,
                "secureCrtSessionFilterRouteFilterObject": filter_route.filter_object,
                "secureCrtSessionFilterRouteSelectedTreeObject": filter_route.selected_tree_object,
                "secureCrtSessionFilterRouteSelectedProfile": filter_route.selected_profile_name,
                "secureCrtSessionFilterRouteSelectedTreeLabel": filter_route.selected_tree_label,
                "secureCrtSessionFilterRouteQuery": filter_route.expected_query,
                "secureCrtSessionFilterRoutePlaceholder": filter_route.expected_placeholder,
                "secureCrtSessionFilterRouteMatchedLabel": filter_route.matched_result_label,
                "secureCrtSessionFilterRouteSignal": filter_route.change_signal,
                "secureCrtSessionFilterRouteHandler": filter_route.handler_name,
                "secureCrtSessionFilterRouteRenderSource": filter_route.render_source,
            }
            for property_name, property_value in filter_route_properties.items():
                panel.setProperty(property_name, property_value)
            panel.setProperty("secureCrtSessionManagerActionKeys", [action.key for action in chrome.actions])
            panel.setProperty("secureCrtSessionFilterPlaceholder", chrome.filter_placeholder)
            panel.setProperty("secureCrtSessionManagerStaticTitleX", chrome.static_title_x)
            panel.setProperty("secureCrtSessionManagerStaticTitleY", chrome.static_title_y)
            panel.setProperty("secureCrtSessionManagerStaticFilterY", chrome.static_filter_y)
            panel.setProperty("secureCrtSessionManagerStaticFilterXMargin", chrome.static_filter_x_margin)
            panel.setProperty("secureCrtSessionManagerStaticFilterHeight", chrome.static_filter_height)
            panel.setProperty("secureCrtSessionManagerStaticFilterPlaceholderX", chrome.static_filter_placeholder_x)
            panel.setProperty("secureCrtSessionManagerStaticFilterPlaceholderY", chrome.static_filter_placeholder_y)
            panel.setProperty("secureCrtSessionManagerLiveMaxHeight", chrome.live_max_height)
            panel.setProperty("secureCrtSessionManagerLiveSpacing", chrome.live_spacing)
            panel.setProperty("secureCrtSessionManagerLiveTitleSpacing", chrome.live_title_spacing)
            panel.setProperty("secureCrtSessionManagerLiveFilterHeight", chrome.live_filter_height)
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
            title.setObjectName("secureCrtSessionManagerTitle")
            title_row.addWidget(title, 1)
            for action in chrome.actions:
                button = QToolButton()
                button.setObjectName("secureCrtSessionManagerAction")
                button.setProperty("secureCrtSessionManagerActionKey", action.key)
                button.setProperty("secureCrtSessionManagerIconKey", action.icon_key)
                button.setProperty("secureCrtSessionManagerActionLabel", action.label)
                button.setProperty("secureCrtSessionManagerStaticX", action.static_x)
                button.setProperty("secureCrtSessionManagerStaticY", action.static_y)
                button.setProperty("secureCrtSessionManagerStaticButtonSize", action.static_button_size)
                button.setProperty("secureCrtSessionManagerStaticIconX", action.static_icon_x)
                button.setProperty("secureCrtSessionManagerStaticIconY", action.static_icon_y)
                button.setProperty("secureCrtSessionManagerStaticIconSize", action.static_icon_size)
                button.setProperty("secureCrtSessionManagerLiveIconSize", action.live_icon_size)
                button.setProperty("secureCrtSessionManagerLiveButtonSize", action.live_button_size)
                button.setProperty("secureCrtSessionManagerRenderSource", action.render_source)
                button.setProperty("secureCrtSessionRouteKey", route.key)
                button.setProperty("secureCrtSessionRouteRole", route.route_role)
                button.setProperty("secureCrtSessionRouteSelectedProfile", route.selected_profile_name)
                button.setProperty("secureCrtSessionRouteSelectedTreeLabel", route.selected_tree_label)
                button.setProperty("secureCrtSessionRouteActiveTab", route.active_tab_label)
                button.setProperty("secureCrtSessionRouteTarget", route.target_value)
                button.setProperty("secureCrtSessionRouteProtocol", route.protocol_value)
                button.setProperty("secureCrtSessionRouteSession", route.session_value)
                button.setProperty("secureCrtSessionRouteStatusValue", route.target_value)
                button.setProperty("secureCrtSessionRouteRenderSource", route.render_source)
                button.setProperty(
                    "secureCrtSessionRouteActive",
                    "true" if action.key == route.session_manager_action_key else "false",
                )
                button.setToolTip(action.tooltip)
                button.setIcon(self.securecrt_session_manager_action_icon(action.icon_key, size=action.live_icon_size))
                button.setIconSize(QSize(action.live_icon_size, action.live_icon_size))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(QSize(action.live_button_size, action.live_button_size))
                button.clicked.connect(
                    lambda _checked=False, key=action.key: self.run_securecrt_session_manager_action(key)
                )
                title_row.addWidget(button)
            layout.addLayout(title_row)

            self.securecrt_session_filter = QLineEdit()
            self.securecrt_session_filter.setObjectName("secureCrtSessionFilter")
            self.securecrt_session_filter.setPlaceholderText(chrome.filter_placeholder)
            self.securecrt_session_filter.setProperty("secureCrtSessionManagerLiveFilterHeight", chrome.live_filter_height)
            for property_name, property_value in filter_route_properties.items():
                self.securecrt_session_filter.setProperty(property_name, property_value)
            self.securecrt_session_filter.setMinimumHeight(chrome.live_filter_height)
            self.securecrt_session_filter.textChanged.connect(self.filter_profile_tree)
            layout.addWidget(self.securecrt_session_filter)
            panel.setVisible(False)
            return panel

        def securecrt_session_manager_action_icon(self, icon_key: str, *, size: int) -> QIcon:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                self.draw_securecrt_session_manager_action_icon(painter, icon_key, size)
            finally:
                painter.end()
            return QIcon(pixmap)

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
                button.setIcon(self.style().standardIcon(self.standard_icon(self.termius_hosts_icon_name(action.icon_key))))
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
            for column in chrome.columns:
                label = QLabel(column.label)
                label.setObjectName("remminaProfileListColumn")
                label.setProperty("remminaProfileColumnKey", column.key)
                label.setProperty("remminaProfileColumnWidth", column.static_width)
                label.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
                label.setMinimumWidth(column.live_min_width)
                header.addWidget(label)
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
                for column in chrome.columns:
                    cell = QLabel(values[column.key])
                    cell.setObjectName("remminaProfileListCell")
                    cell.setProperty("remminaProfileRowKey", row.key)
                    cell.setProperty("remminaProfileColumnKey", column.key)
                    cell.setProperty("remminaProfileCellValue", values[column.key])
                    cell.setProperty("remminaProfileColumnWidth", column.static_width)
                    cell.setProperty("remminaProfileColumnLiveMinWidth", column.live_min_width)
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
                    cell.setMinimumWidth(column.live_min_width)
                    cell.setToolTip(f"{row.name}: {row.status}")
                    row_layout.addWidget(cell)
                status = QLabel(row.status)
                status.setObjectName("remminaProfileListCell")
                status.setProperty("remminaProfileRowKey", row.key)
                status.setProperty("remminaProfileColumnKey", "status")
                status.setProperty("remminaProfileCellValue", row.status)
                status.setProperty("remminaProfileStaticStatusY", chrome.static_status_y)
                if row.key == route.selected_profile_key:
                    status.setProperty("remminaProfileViewerRouteKey", route.key)
                    status.setProperty("remminaProfileViewerRouteActiveTab", route.active_tab_label)
                    status.setProperty("remminaProfileViewerStatus", route.profile_status)
                status.setToolTip(f"{row.name}: {row.status}")
                row_layout.addWidget(status, 1)
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
            for field in chrome.fields:
                cell = QLabel(f"{field.label}: {field.value}")
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
                cell.setToolTip(field.tooltip)
                cell.setMinimumWidth(field.live_min_width)
                cell.setMinimumHeight(field.live_cell_height)
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(cell)
            layout.addStretch(1)
            return panel

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
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 7, 8, 7)
            layout.setSpacing(5)

            header = QHBoxLayout()
            title = QLabel(f"SFTP - {route.sftp_tab_label}")
            title.setObjectName("secureCrtSftpTitle")
            title.setProperty("secureCrtSftpBrowserRouteKey", route.key)
            title.setProperty("secureCrtSftpBrowserTabLabel", route.sftp_tab_label)
            queue = QLabel(f"Queue: {route.transfer_queue_label} ({route.transfer_status})")
            queue.setObjectName(route.queue_object)
            for property_name, value in route_props.items():
                queue.setProperty(property_name, value)
            header.addWidget(title)
            header.addStretch(1)
            header.addWidget(queue)
            layout.addLayout(header)

            toolbar = QFrame()
            toolbar.setObjectName(route.toolbar_object)
            for property_name, value in route_props.items():
                toolbar.setProperty(property_name, value)
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(6)
            for action_key in route.toolbar_actions:
                action = QLabel(action_key.title())
                action.setObjectName("secureCrtSftpAction")
                action.setProperty("secureCrtSftpBrowserRouteKey", route.key)
                action.setProperty("secureCrtSftpBrowserActionKey", action_key)
                action.setProperty(route.toolbar_actions_property, actions_value)
                toolbar_layout.addWidget(action)
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            path = QLabel(f"Remote path: {route.remote_path}")
            path.setObjectName(route.path_object)
            for property_name, value in route_props.items():
                path.setProperty(property_name, value)
            layout.addWidget(path)

            table = QFrame()
            table.setObjectName(route.table_object)
            for property_name, value in route_props.items():
                table.setProperty(property_name, value)
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
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(4, 1, 4, 1)
                row_layout.setSpacing(8)
                name = QLabel(row.name)
                name.setObjectName("secureCrtSftpRowName")
                size = QLabel(row.size)
                size.setObjectName("secureCrtSftpRowSize")
                modified = QLabel(row.modified)
                modified.setObjectName("secureCrtSftpRowModified")
                row_layout.addWidget(name, 2)
                row_layout.addWidget(size, 1)
                row_layout.addWidget(modified, 1)
                table_layout.addWidget(row_frame)
            layout.addWidget(table)
            return panel

        def build_securecrt_command_window_evidence(self) -> QFrame:
            chrome = gui_design_securecrt_command_window_chrome()
            send_route = gui_design_securecrt_command_window_send_route()
            panel = QFrame()
            panel.setObjectName("secureCrtCommandWindow")
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
            target = QLabel(chrome.target_scope)
            target.setObjectName("secureCrtCommandTarget")
            target.setProperty("secureCrtCommandWindowKey", chrome.key)
            target.setProperty("secureCrtCommandStaticTargetWidth", chrome.static_target_width)
            target.setProperty("secureCrtCommandLiveTargetMinWidth", chrome.live_target_min_width)
            target.setMinimumWidth(chrome.live_target_min_width)
            command_input = QLabel(chrome.command)
            command_input.setObjectName("secureCrtCommandInput")
            command_input.setProperty("secureCrtCommandStaticInputX", chrome.static_input_x)
            command_input.setProperty("secureCrtCommandStaticInputTextX", chrome.static_input_text_x)
            command_input.setProperty("secureCrtCommandStaticInputTextY", chrome.static_input_text_y)
            command_input.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            send = QLabel(chrome.send_label)
            send.setObjectName("secureCrtCommandSend")
            send.setProperty("secureCrtCommandWindowKey", chrome.key)
            send.setProperty("secureCrtCommandStaticSendWidth", chrome.static_send_width)
            send.setProperty("secureCrtCommandLiveSendMinWidth", chrome.live_send_min_width)
            send.setMinimumWidth(chrome.live_send_min_width)
            status = QLabel(chrome.status)
            status.setObjectName("secureCrtCommandStatus")
            status.setProperty("secureCrtCommandWindowKey", chrome.key)
            route_widgets = (panel, target, command_input, send, status)
            route_value_properties = {
                "secureCrtCommandRouteCommand": chrome.command,
                "secureCrtCommandRouteTargetScope": chrome.target_scope,
                "secureCrtCommandRouteSendLabel": chrome.send_label,
                "secureCrtCommandRouteStatus": chrome.status,
            }
            for route_widget in route_widgets:
                route_widget.setProperty("secureCrtCommandRouteKey", send_route.key)
                route_widget.setProperty("secureCrtCommandRouteRole", send_route.route_role)
                route_widget.setProperty("secureCrtCommandRouteSourceWindowObject", send_route.source_window_object)
                route_widget.setProperty("secureCrtCommandRouteTargetScopeObject", send_route.target_scope_object)
                route_widget.setProperty("secureCrtCommandRouteCommandInputObject", send_route.command_input_object)
                route_widget.setProperty("secureCrtCommandRouteSendControlObject", send_route.send_control_object)
                route_widget.setProperty("secureCrtCommandRouteStatusObject", send_route.status_object)
                route_widget.setProperty("secureCrtCommandRouteRenderSource", send_route.render_source)
                for route_property, route_value in route_value_properties.items():
                    route_widget.setProperty(route_property, route_value)
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
                label = QLabel(f"{key}: {value}")
                label.setObjectName("productReferenceStateItem")
                label.setProperty("referenceKey", key)
                self.apply_product_identity_route_properties(label, route)
                self.apply_preset_selection_route_properties(label, selection_route)
                label.setToolTip(f"{reference.active_tab_label} {key}")
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
            pane_title = QLabel(title)
            pane_title.setObjectName("productWorkspacePaneTitle")
            pane_layout.addWidget(pane_title)
            lead_label = QLabel(lead)
            lead_label.setObjectName("productWorkspaceLead")
            lead_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            pane_layout.addWidget(lead_label)
            for line in lines[:4]:
                line_label = QLabel(line)
                line_label.setObjectName("productWorkspaceLine")
                line_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                pane_layout.addWidget(line_label)
            return pane

        def run_home_search(self, text: str) -> None:
            self.quick_connect.setText(text)
            self.run_quick_connect()

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
            tab_title: str | None = None,
            tab_status: str | None = None,
        ) -> None:
            pane = self.new_terminal_pane(plan)
            self.remember_terminal_plan(plan)
            index = self.add_workspace_tab(pane, tab_title or plan.title, role="terminal")
            self.apply_reference_tab_route_to_terminal_tab(pane, tab_title or plan.title)
            if tab_status:
                self.tabs.setTabToolTip(index, f"{tab_title or plan.title}: {tab_status}")
            self.apply_reference_tab_chrome_route_to_terminal_tab(pane, tab_title or plan.title, index)
            self.update_session_status()
            self.apply_reference_status_bar_route_to_terminal_tab(pane, tab_title or plan.title)
            self.apply_reference_session_action_route_to_terminal_tab(pane, tab_title or plan.title, index)

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
            tooltip = self.tabs.tabToolTip(tab_index)
            closeable = bool(self.tabs.tabsClosable() and tab_role == route.reference_tab_role)
            selected = self.tabs.currentIndex() == tab_index
            position = self.tab_position_name()
            for widget in (pane, self.tabs, self.tabs.tabBar()):
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
            for widget in (pane, self.tabs, self.tabs.tabBar()):
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
            for widget in (panel, self.tabs, self.tabs.tabBar()):
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
            action_buttons = [
                getattr(pane, "start_button", None),
                getattr(pane, "restart_button", None),
                getattr(pane, "stop_button", None),
                getattr(pane, "copy_button", None),
                getattr(pane, "clear_button", None),
            ]
            action_buttons = [button for button in action_buttons if button is not None]
            status_widget = getattr(pane, "status", None)
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

        def open_moba_connected_session_tab(
            self,
            profile: Profile,
            plan: TerminalPanePlan,
            *,
            remote_path: str = "/",
            tab_title: str | None = None,
            tab_status: str | None = None,
        ) -> None:
            state = build_moba_connected_session_state(profile, remote_path=remote_path)
            panel = MobaConnectedSessionPanel(state, self.new_terminal_pane(plan))
            panel.moba_connected_state = state
            self.remember_terminal_plan(plan)
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
                self.tabs.setTabToolTip(index, f"{title}: {tab_status}")
            self.show_moba_connected_dock(state)
            self.update_session_status()

        def add_split(self, direction: str) -> None:
            orientation = Qt.Orientation.Horizontal if direction == "horizontal" else Qt.Orientation.Vertical
            splitter = QSplitter(orientation)
            plans = split_shell_plans(2)
            for plan in plans:
                splitter.addWidget(self.new_terminal_pane(plan))
                self.remember_terminal_plan(plan)
            label = "Split H" if direction == "horizontal" else "Split V"
            self.add_workspace_tab(splitter, f"{label} {self.count_closeable_tabs() + 1}", role="split")
            self.update_session_status()

        def remember_terminal_plan(self, plan: TerminalPanePlan) -> None:
            self.recent_terminal_plans.append(plan)
            self.recent_terminal_plans = self.recent_terminal_plans[-8:]

        def duplicate_current_tab(self) -> None:
            index = self.tabs.currentIndex()
            if index < 0 or self.tab_role(index) in {"home", "new-session"}:
                self.open_local_terminal_tab()
                return
            widget = self.tabs.widget(index)
            title = self.tabs.tabText(index)
            if isinstance(widget, TerminalPane):
                self.open_terminal_tab(widget.plan)
                return
            panes = self.terminal_panes_in(widget) if widget is not None else []
            if not panes:
                self.open_local_terminal_tab()
                return
            orientation = widget.orientation() if isinstance(widget, QSplitter) else Qt.Orientation.Horizontal
            splitter = QSplitter(orientation)
            for pane in panes[:4]:
                splitter.addWidget(self.new_terminal_pane(pane.plan))
                self.remember_terminal_plan(pane.plan)
            self.add_workspace_tab(splitter, f"{title} copy", role="split")
            self.log.append(f"TAB DUPLICATED: {title}")
            self.update_session_status()

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
            plans = list(self.recent_terminal_plans[-3:])
            for plan in plans:
                self.open_terminal_tab(plan)
            self.log.append(f"RECOVERED: {len(plans)} recent session pane(s)")

        def create_layout(self) -> None:
            dialog = LayoutDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                layout = dialog.layout()
                self.layout_store.add(layout)
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT SAVED: {layout.name}")
            except ValueError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def edit_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            try:
                current = self.layout_store.get(name)
            except KeyError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))
                return
            dialog = LayoutDialog(current, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            try:
                layout = dialog.layout()
                self.save_layout(layout, original_name=name)
                self.refresh_layouts()
                self.layout_select.setCurrentText(layout.name)
                self.log.append(f"LAYOUT UPDATED: {layout.name}")
            except (KeyError, ValueError) as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def remove_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            answer = QMessageBox.question(self, "Remove layout", f"Remove layout {name}?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            try:
                self.layout_store.remove(name)
                self.refresh_layouts()
                self.log.append(f"LAYOUT REMOVED: {name}")
            except KeyError as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def save_layout(self, layout: Layout, original_name: str) -> None:
            layouts = self.layout_store.load()
            if layout.name != original_name and any(item.name == layout.name for item in layouts):
                raise ValueError(f"layout already exists: {layout.name}")
            layouts = [item for item in layouts if item.name != original_name]
            layouts.append(layout)
            self.layout_store.save(sorted(layouts, key=lambda item: item.name))

        def open_selected_layout(self) -> None:
            name = self.layout_select.currentText()
            if not name:
                QMessageBox.information(self, "Remote Ops Workspace", "No saved layout selected.")
                return
            try:
                layout = self.layout_store.get(name)
                plans = build_layout_terminal_plans(layout, self.store)
                widget = self.layout_widget(layout, plans)
                for plan in plans:
                    self.remember_terminal_plan(plan)
                self.add_workspace_tab(widget, layout.name, role="layout")
                self.log.append(f"LAYOUT: {layout.name} ({len(plans)} panes)")
                self.update_session_status()
            except (KeyError, LauncherError, ValueError) as exc:
                QMessageBox.warning(self, "Layout failed", str(exc))

        def layout_widget(self, layout: Layout, plans: list[TerminalPanePlan]) -> QWidget:
            if len(plans) == 1:
                return self.new_terminal_pane(plans[0])
            if layout.orientation == "vertical":
                splitter = QSplitter(Qt.Orientation.Vertical)
                for plan in plans:
                    splitter.addWidget(self.new_terminal_pane(plan))
                return splitter
            if layout.orientation == "horizontal":
                splitter = QSplitter(Qt.Orientation.Horizontal)
                for plan in plans:
                    splitter.addWidget(self.new_terminal_pane(plan))
                return splitter
            root = QSplitter(Qt.Orientation.Vertical)
            for offset in range(0, len(plans), 2):
                row = QSplitter(Qt.Orientation.Horizontal)
                for plan in plans[offset : offset + 2]:
                    row.addWidget(self.new_terminal_pane(plan))
                root.addWidget(row)
            return root

        def new_terminal_pane(self, plan: TerminalPanePlan) -> TerminalPane:
            pane = TerminalPane(plan)
            pane.process.started.connect(self.update_session_status)
            pane.process.finished.connect(lambda *_args: self.update_session_status())
            return pane

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
            self.stop_terminal_panes(running)
            title = self.tabs.tabText(index)
            self.tabs.removeTab(index)
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
            return panes

        def running_terminal_panes(self) -> list[TerminalPane]:
            return [pane for pane in self.all_terminal_panes() if pane.is_running()]

        def stop_terminal_panes(self, panes: list[TerminalPane]) -> None:
            stopped = 0
            killed = 0
            unfinished = 0
            for pane in panes:
                result = pane.stop(self.CLOSE_STOP_POLICY)
                if result.was_running:
                    stopped += 1
                if result.kill_requested:
                    killed += 1
                if not result.finished:
                    unfinished += 1
            if stopped:
                detail = f"STOPPED: {stopped} process pane(s)"
                if killed:
                    detail += f", {killed} killed after timeout"
                if unfinished:
                    detail += f", {unfinished} still exiting"
                self.log.append(detail)

        def confirm_stop_processes(self, title: str, count: int) -> bool:
            answer = QMessageBox.question(
                self,
                title,
                f"Stop {count} running process pane(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return answer == QMessageBox.StandardButton.Yes

        def update_session_status(self) -> None:
            running = len(self.running_terminal_panes())
            if running:
                self.statusBar().showMessage(f"Running process panes: {running}")
            else:
                self.statusBar().showMessage("No running process panes")

        def closeEvent(self, event) -> None:
            running = self.running_terminal_panes()
            if running and not self.confirm_stop_processes("Quit Remote Ops Workspace", len(running)):
                event.ignore()
                return
            self.stop_terminal_panes(running)
            event.accept()

    app = QApplication.instance()
    if app is None:
        app = QApplication(argv or sys.argv)
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
