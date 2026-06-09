from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from .doctor import run_doctor
from .file_transfer import build_sftp_queue_plan, parse_transfer_item_spec, preview_local_path
from .gui_designs import (
    GUI_DESIGN_PRESETS,
    GuiDesignPreset,
    get_gui_design_preset,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_monitoring_control_geometry,
    gui_design_moba_monitoring_control_geometry_for,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_actions,
    gui_design_moba_right_utility_actions,
    gui_design_moba_session_edge_actions,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_items,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_reference_state,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_top_chrome,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_hosts_chrome,
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
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_window_title,
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
    SFTP_ROW_ICON_KEY_ROLE = int(Qt.ItemDataRole.UserRole) + 41
    SFTP_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 42
    SFTP_ROW_ICON_SIZE_ROLE = int(Qt.ItemDataRole.UserRole) + 43
    SFTP_ROW_ICON_RENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 44
    GENERATED_PROFILE_TREE_ICON_PRESETS = {"securecrt", "termius", "remmina", "mremoteng"}

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

            header = QFrame()
            header.setObjectName("terminalHeader")
            header_layout = QHBoxLayout(header)
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

            command_row = QFrame()
            command_row.setObjectName("terminalCommandRow")
            command_layout = QHBoxLayout(command_row)
            command_layout.setContentsMargins(8, 3, 8, 5)
            command_layout.addWidget(self.command_preview, 1)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(header)
            layout.addWidget(command_row)
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
        def __init__(self, state: MobaConnectedSessionState) -> None:
            super().__init__()
            self.setObjectName("mobaSftpBrowser")
            self.state = state
            density = gui_design_moba_sftp_dock_layout()
            self.setProperty("mobaSftpDockInnerMargin", density.inner_margin)
            self.setProperty("mobaSftpToolbarHeight", density.toolbar_height)
            self.setProperty("mobaSftpPathHeight", density.path_height)
            self.setProperty("mobaSftpHeaderHeight", density.table_header_height)
            self.setProperty("mobaSftpRowHeight", density.file_row_height)
            self.setProperty("mobaSftpMonitoringHeight", density.monitoring_height)
            self.setProperty("mobaSftpStaticMaxRows", density.static_max_rows)
            self.setProperty("mobaSftpToolbarSeparatorWidth", density.toolbar_separator_width)

            layout = QVBoxLayout(self)
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
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
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
            self.file_table.setProperty("mobaSftpRowHeight", density.file_row_height)
            self.file_table.setProperty(
                "mobaSftpFileRowIconKinds",
                [row_icon.kind for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
            self.file_table.setProperty(
                "mobaSftpFileRowIconKeys",
                [row_icon.icon_key for row_icon in gui_design_moba_sftp_file_row_icons()],
            )
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
            parent_item.setSizeHint(0, QSize(0, density.file_row_height))
            parent_item.setToolTip(0, "parent directory")
            self.file_table.addTopLevelItem(parent_item)
            for entry in self.state.file_entries:
                item = QTreeWidgetItem([entry.name, str(entry.size_kb), entry.modified])
                self.apply_sftp_file_row_icon(item, entry.kind)
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
            panel.setProperty("mobaRemoteMonitoringRefreshSeconds", chrome.refresh_seconds)
            panel.setProperty("mobaRemoteMonitoringCommand", self.state.monitoring_plan.printable())
            panel.setProperty("mobaRemoteMonitoringFollowPlan", self.state.follow_folder_plan.printable_batch())
            panel.setProperty(
                "mobaMonitoringControlGeometryKeys",
                [geometry.key for geometry in gui_design_moba_monitoring_control_geometry()],
            )
            panel.setFixedHeight(density.monitoring_height)
            controls = QFrame(panel)
            controls.setObjectName("mobaMonitoringControls")
            controls.setGeometry(0, 0, 260, density.monitoring_height)
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
                    250 - geometry.anchor_x,
                    max(geometry.row_height + 4, geometry.icon_size + 4),
                )
            for metric in gui_design_moba_monitoring_metrics():
                label = QLabel(self.monitoring_metric_text(metric), panel)
                label.setObjectName("mobaMonitoringMetric")
                label.setProperty("mobaMonitoringMetricKey", metric.key)
                label.setProperty("mobaMonitoringMetricVisibleInDock", metric.key in chrome.visible_metric_keys)
                label.setProperty("mobaMonitoringMetricTelemetrySurface", chrome.telemetry_surface)
                label.setVisible(False)
            return panel

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
            widget.setProperty("mobaMonitoringTelemetrySurface", gui_design_moba_remote_monitoring_dock_chrome().telemetry_surface)
            geometry = gui_design_moba_monitoring_control_geometry_for(control.key)
            widget.setProperty("mobaMonitoringControlStaticX", geometry.anchor_x)
            widget.setProperty("mobaMonitoringControlStaticY", geometry.static_y)
            widget.setProperty("mobaMonitoringControlIconX", geometry.icon_x)
            widget.setProperty("mobaMonitoringControlIconSize", geometry.icon_size)
            widget.setProperty("mobaMonitoringControlLabelX", geometry.label_x)
            widget.setProperty("mobaMonitoringControlCheckSize", geometry.check_size)
            widget.setProperty("mobaMonitoringControlRowHeight", geometry.row_height)
            widget.setCheckable(True)
            widget.setChecked(self.monitoring_control_checked(control))
            widget.setToolTip(self.monitoring_control_tooltip(control))
            widget.setIcon(self.monitoring_control_icon(control.icon_key))
            widget.setIconSize(QSize(geometry.icon_size, geometry.icon_size))
            widget.setMinimumHeight(geometry.row_height)
            if control.key == "remote-monitoring":
                widget.setProperty("mobaMonitoringCommand", self.state.monitoring_plan.printable())
                widget.setProperty(
                    "mobaMonitoringRefreshSeconds",
                    gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds,
                )
            if control.key == "follow-terminal-folder":
                widget.setProperty("mobaMonitoringFollowPlan", self.state.follow_folder_plan.printable_batch())
                widget.setProperty("mobaMonitoringFollowPath", self.state.remote_path)
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
            button = QToolButton()
            button.setObjectName("mobaSftpAction")
            button.setProperty("mobaSftpActionKey", action.key)
            button.setProperty("mobaSftpIconKey", action.icon_key)
            button.setProperty("mobaSftpActionGroupKey", action.group_key)
            button.setProperty("mobaSftpActionSeparatorAfter", action.separator_after)
            button.setProperty("mobaSftpActionButtonSize", density.toolbar_icon_step)
            button.setProperty("mobaSftpActionIconSize", density.toolbar_icon_size)
            button.setText(action.label)
            button.setToolTip(action.tooltip)
            button.setIcon(self.sftp_action_icon(action.icon_key, action.color))
            button.setIconSize(QSize(density.toolbar_icon_size, density.toolbar_icon_size))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(density.toolbar_icon_step, density.toolbar_icon_step))
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

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)
            root.addWidget(self.build_terminal_area(), 1)
            root.addWidget(self.build_telemetry_bar())

        def build_terminal_area(self) -> QWidget:
            area = QWidget()
            area.setObjectName("mobaTerminalArea")
            layout = QHBoxLayout(area)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            terminal_stack = QWidget()
            terminal_stack.setObjectName("mobaTerminalStack")
            stack_layout = QVBoxLayout(terminal_stack)
            stack_layout.setContentsMargins(0, 0, 0, 0)
            stack_layout.setSpacing(0)
            stack_layout.addWidget(self.build_ssh_banner())
            self.apply_terminal_transcript_evidence()
            stack_layout.addWidget(self.terminal_pane, 1)
            layout.addWidget(terminal_stack, 1)
            layout.addWidget(self.build_right_utility_rail())
            return area

        def apply_terminal_transcript_evidence(self) -> None:
            lines = self.state.terminal_transcript
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptKeys", [line.key for line in lines])
            self.terminal_pane.output.setProperty("mobaTerminalTranscriptTones", [line.tone for line in lines])
            self.terminal_pane.output.setPlainText("\n".join(line.text for line in lines))
            self.terminal_pane.output.moveCursor(QTextCursor.MoveOperation.End)

        def build_right_utility_rail(self) -> QFrame:
            rail = QFrame()
            rail.setObjectName("mobaRightUtilityRail")
            rail.setFixedWidth(28)
            layout = QVBoxLayout(rail)
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(8)
            layout.addWidget(self.build_session_edge_controls())
            for action in gui_design_moba_right_utility_actions():
                button = QToolButton()
                button.setObjectName("mobaRightUtilityAction")
                button.setProperty("mobaRightUtilityKey", action.key)
                button.setProperty("mobaRightUtilityIconKey", action.icon_key)
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
                layout.addWidget(button)
            layout.addStretch(1)
            return rail

        def build_session_edge_controls(self) -> QFrame:
            controls = QFrame()
            controls.setObjectName("mobaSessionEdgeControls")
            actions = gui_design_moba_session_edge_actions()
            controls.setProperty("mobaSessionEdgeActionKeys", [action.key for action in actions])
            controls.setFixedHeight(50)
            layout = QVBoxLayout(controls)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            for action in actions:
                button = QToolButton()
                button.setObjectName("mobaSessionEdgeAction")
                button.setProperty("mobaSessionEdgeKey", action.key)
                button.setProperty("mobaSessionEdgeIconKey", action.icon_key)
                button.setProperty("mobaSessionEdgeStaticY", action.static_y)
                button.setToolTip(action.tooltip)
                button.setIcon(self.moba_utility_icon(action.icon_key, action.color))
                button.setIconSize(QSize(17, 17))
                button.setFixedSize(QSize(22, 22))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                layout.addWidget(button)
            layout.addStretch(1)
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

        def build_ssh_banner(self) -> QFrame:
            chrome = gui_design_moba_ssh_banner_chrome()
            banner = QFrame()
            banner.setObjectName("mobaSshBanner")
            banner.setProperty("mobaBannerTitle", chrome.title)
            banner.setProperty("mobaBannerSubtitle", chrome.subtitle)
            banner.setProperty("mobaBannerTargetIntro", chrome.target_intro)
            banner.setProperty("mobaBannerCapabilityLabelWidth", chrome.capability_label_width)
            banner.setProperty("mobaBannerFooterPrefix", chrome.footer_prefix)
            banner.setProperty("mobaBannerCapabilityKeys", [row.key for row in self.state.banner.capability_rows()])
            banner.setProperty("mobaBannerFooterLinks", list(self.state.banner.footer_links()))
            banner.setProperty("mobaBannerWidth", chrome.static_width)
            banner.setProperty("mobaBannerHeight", chrome.static_height)
            banner.setMinimumWidth(chrome.static_width)
            banner.setMaximumWidth(chrome.static_width + 120)
            banner.setFixedHeight(chrome.static_height)
            layout = QVBoxLayout(banner)
            layout.setContentsMargins(14, 9, 14, 9)
            layout.setSpacing(2)
            title = QLabel(f"{chrome.heading_prefix}{chrome.title}{chrome.heading_suffix}")
            title.setObjectName("mobaSshBannerTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)
            subtitle = QLabel(chrome.subtitle)
            subtitle.setObjectName("mobaSshBannerSubtitle")
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(subtitle)
            layout.addSpacing(8)
            target = QLabel(f"> {chrome.target_intro} {self.state.banner.title}")
            target.setObjectName("mobaSshBannerTargetLine")
            target.setProperty("mobaSshBannerTarget", self.state.banner.title)
            target.setProperty("mobaSshBannerTargetIntro", chrome.target_intro)
            target.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(target)
            for row in self.state.banner.capability_rows():
                label = QLabel(f"  * {row.line(label_width=chrome.capability_label_width)}")
                label.setObjectName("mobaSshBannerCapability")
                label.setProperty("mobaSshBannerCapabilityKey", row.key)
                label.setProperty("mobaSshBannerCapabilityLabel", row.label)
                label.setProperty("mobaSshBannerCapabilityValue", row.value)
                label.setProperty("mobaSshBannerCapabilityStatus", row.status)
                label.setProperty("capabilityStatus", row.status)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(label)
            help_link, website_link = self.state.banner.footer_links()
            footer = QLabel(f"> {chrome.footer_prefix} {help_link} or visit our {website_link}.")
            footer.setObjectName("mobaSshBannerFooter")
            footer.setProperty("mobaSshBannerFooterLinks", [help_link, website_link])
            footer.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(footer)
            return banner

        def build_telemetry_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("mobaTelemetryBar")
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(7, 2, 7, 2)
            layout.setSpacing(0)
            for cell in moba_telemetry_cells(self.state):
                cell_frame = QFrame()
                cell_frame.setObjectName("mobaTelemetryCell")
                cell_frame.setProperty("mobaTelemetryKey", cell.key)
                cell_frame.setProperty("mobaTelemetryIconKey", cell.icon_key)
                cell_frame.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                cell_frame.setProperty("mobaTelemetryIconSize", cell.icon_size)
                cell_frame.setProperty("mobaTelemetryDisplayText", cell.display_text)
                cell_frame.setProperty("mobaTelemetryCellWidth", cell.width)
                cell_frame.setToolTip(cell.label)
                cell_frame.setFixedWidth(cell.width)
                cell_layout = QHBoxLayout(cell_frame)
                cell_layout.setContentsMargins(4, 1, 5, 1)
                cell_layout.setSpacing(4)
                icon = QLabel()
                icon.setObjectName("mobaTelemetryIcon")
                icon.setProperty("mobaTelemetryKey", cell.key)
                icon.setProperty("mobaTelemetryIconKey", cell.icon_key)
                icon.setProperty("mobaTelemetryIconAccent", cell.icon_accent)
                icon.setProperty("mobaTelemetryIconSize", cell.icon_size)
                icon.setProperty("mobaTelemetryIconRender", "generated-pixmap")
                icon.setPixmap(self.telemetry_icon_pixmap(cell))
                icon.setFixedSize(QSize(cell.icon_size, cell.icon_size))
                icon.setToolTip(cell.label)
                cell_layout.addWidget(icon)
                label = QLabel(cell.display_text)
                label.setObjectName("mobaTelemetryItem")
                label.setProperty("mobaTelemetryKey", cell.key)
                label.setProperty("mobaTelemetryDisplayText", cell.display_text)
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
            self.setObjectName("mobaRailLabel")
            self.setProperty("mobaRailRole", role)
            self.setProperty("mobaRailLabel", label)
            self.setToolTip(label)
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setFixedSize(28, 58)

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
            self.moba_x_server_button = self.toolbar_button(
                "X server",
                "SP_ComputerIcon",
                "Show X server workflow status",
            )
            self.moba_x_server_button.setObjectName("mobaXServerAction")
            self.moba_x_server_button.setProperty("mobaIconKey", "xserver")
            self.moba_x_server_button.setIcon(self.moba_ribbon_icon("xserver", "#1a1a1a"))
            self.moba_exit_button = self.toolbar_button("Exit", "SP_DialogCloseButton", "Close Remote Ops Workspace")
            self.moba_exit_button.setObjectName("mobaExitAction")
            self.moba_exit_button.setProperty("mobaIconKey", "exit")
            self.moba_exit_button.setIcon(self.moba_ribbon_icon("exit", "#e2473f"))
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
            QShortcut(QKeySequence("Ctrl+R"), self, activated=self.refresh_profiles)
            QShortcut(QKeySequence("Ctrl+N"), self, activated=self.create_profile)
            QShortcut(QKeySequence("Ctrl+E"), self, activated=self.edit_selected_profile)
            QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self.connect_selected(False))
            QShortcut(QKeySequence("Ctrl+T"), self, activated=self.open_local_terminal_tab)
            QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close_current_tab)
            QShortcut(QKeySequence("Ctrl+Shift+T"), self, activated=self.recover_previous_sessions)
            QShortcut(QKeySequence("Ctrl+Shift+H"), self, activated=lambda: self.add_split("horizontal"))
            QShortcut(QKeySequence("Ctrl+Shift+V"), self, activated=lambda: self.add_split("vertical"))
            QShortcut(QKeySequence("Ctrl+L"), self, activated=self.open_selected_layout)
            QShortcut(QKeySequence("Ctrl+F"), self, activated=self.search_input.setFocus)
            self.refresh_profiles()
            self.refresh_layouts()
            self.populate_view_design_menu()
            self.add_welcome_tab()
            self.apply_selected_design()

        def build_menu_bar(self) -> None:
            self.menuBar().setObjectName("mobaTopMenuBar")
            self.moba_top_menus: list[QMenu] = []
            self.moba_top_menu_actions = []
            for item in gui_design_moba_top_menu_items():
                menu = self.menuBar().addMenu(item.label)
                menu.setObjectName("mobaTopMenu")
                menu.setProperty("mobaTopMenuKey", item.key)
                menu.setProperty("mobaTopMenuLabel", item.label)
                menu.setToolTip(item.tooltip)
                menu.menuAction().setProperty("mobaTopMenuKey", item.key)
                menu.menuAction().setProperty("mobaTopMenuLabel", item.label)
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
            tooltips = {
                "session": "Create a new saved session",
                "servers": "Refresh saved sessions",
                "tools": "Edit selected profile",
                "games": "Show optional tool status",
                "sessions": "Connect selected profile",
                "view": "Cycle to the next visual preset",
                "split": "Open a horizontal split",
                "multiexec": "Show selected launch command",
                "tunneling": "Show tunneling workflow status",
                "packages": "Show package and file-transfer workflows",
                "settings": "Edit selected profile",
                "help": "Show help and diagnostics workflows",
            }
            buttons: list[QToolButton] = []
            for action in gui_design_moba_ribbon_actions():
                button = self.toolbar_button(action.label, "SP_FileIcon", tooltips[action.icon_key])
                button.setObjectName("mobaRibbonButton")
                button.setProperty("mobaIconKey", action.icon_key)
                button.setIcon(self.moba_ribbon_icon(action.icon_key, action.color))
                button.clicked.connect(slots[action.icon_key])
                buttons.append(button)
            return buttons

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

        def create_moba_rail(self) -> QWidget:
            rail = QWidget()
            rail.setObjectName("mobaRail")
            rail.setFixedWidth(28)
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
                button = QToolButton()
                button.setObjectName(item.object_name)
                button.setProperty("mobaRailRole", item.role)
                button.setIcon(self.moba_ribbon_icon(item.icon_key, item.color, size=22))
                button.setIconSize(QSize(20, 20))
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
            panel = QWidget()
            panel.setObjectName("leftPanel")
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
            for button, (key, label, tooltip) in zip(self.product_toolbar_buttons, actions, strict=False):
                button.setText(label)
                button.setToolTip(tooltip)
                button.setProperty("productToolbarKey", key)
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
            if preset.id == "mobaxterm":
                chrome = gui_design_moba_status_bar_chrome()
                self.status_notice_label.setText(f"{chrome.notice} - {chrome.product_note}")
                self.status_notice_label.setToolTip(f"{preset.label}: {chrome.product_note}")
                self.status_notice_label.setProperty("productStatusKey", "notice")
                self.status_marker_label.setText(chrome.right_marker)
                self.status_marker_label.setToolTip(chrome.right_marker_tooltip)
                self.status_marker_label.setProperty("productStatusKey", "right-marker")
                self.moba_bottom_edge_controls.setVisible(True)
                for label, segment in zip(self.status_segment_labels, gui_design_moba_status_segments(), strict=False):
                    label.setText(segment.text)
                    label.setToolTip(segment.tooltip)
                    label.setProperty("productStatusKey", segment.key)
                return
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

        def show_moba_connected_dock(self, state: MobaConnectedSessionState) -> None:
            if not hasattr(self, "moba_left_stack"):
                return
            if self.moba_connected_dock is not None:
                self.moba_left_stack.removeWidget(self.moba_connected_dock)
                self.moba_connected_dock.deleteLater()
            self.moba_connected_dock = MobaSftpDock(state)
            self.moba_connected_dock.setObjectName("mobaConnectedLeftDock")
            self.moba_left_stack.addWidget(self.moba_connected_dock)
            self.moba_left_stack.setCurrentWidget(self.moba_connected_dock)
            self.set_moba_quick_connect_connected_idle()
            self.set_moba_rail_active("sftp")
            title = moba_connected_window_title(state)
            self.setWindowTitle(title)
            self.apply_moba_titlebar_chrome(title)

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
            root_label, root_tooltip = gui_design_tree_root_copy(self.current_design_id())
            root = QTreeWidgetItem([root_label])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            self.apply_profile_tree_icon(root, gui_design_tree_root_icon(self.current_design_id()))
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
                item.setToolTip(0, self.profile_tree_tooltip(profile))
                parent.addChild(item)
            self.profile_list.expandAll()
            if hasattr(self, "securecrt_session_filter"):
                self.filter_profile_tree(self.securecrt_session_filter.text())
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
            is_moba = preset.id == "mobaxterm"
            self.setStyleSheet(preset.stylesheet)
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
            self.configure_toolbar_for_design(preset, is_moba, preset.toolbar_icon_size)
            self.configure_interaction_states_for_design(preset)
            self.left_panel.setMinimumWidth(min(preset.profile_width, 430))
            self.configure_profile_tree_for_design(is_moba, preset.list_spacing)
            self.root_splitter.setSizes([preset.profile_width, max(620, self.width() - preset.profile_width)])
            if is_moba:
                self.workspace.setSizes([max(620, self.height()), 0])
            else:
                self.workspace.setSizes([max(420, self.height() - preset.log_height), preset.log_height])
            self.tabs.setTabPosition(self.tab_position_for_design(preset.tab_position))
            self.tabs.setDocumentMode(preset.document_mode)
            self.configure_workspace_tabs_for_design(is_moba)
            self.refresh_moba_left_dock_for_current_tab()
            self.log.setPlaceholderText(
                f"{preset.description}\n\nLaunch output, dry-run commands and doctor reports appear here."
            )
            self.statusBar().showMessage(f"View: {preset.label}")

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
                self.main_toolbar.setMinimumHeight(64)
                self.main_toolbar.setMaximumHeight(64)
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
            self.profile_list.setIndentation(16 if is_moba else 18)
            self.profile_list.setRootIsDecorated(True)
            self.profile_list.setAnimated(is_moba)
            self.profile_list.setAllColumnsShowFocus(True)
            self.profile_list.setItemsExpandable(True)
            self.profile_list.setExpandsOnDoubleClick(True)
            self.profile_list.setProperty("listSpacing", list_spacing)

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
            if widget is not None:
                widget.setProperty("mobaTabChromeKey", key)
                widget.setProperty("mobaTabIconKey", icon_key)
                widget.setProperty("mobaTabCloseable", closeable)
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

        def show_tab_context_menu(self, position) -> None:
            index = self.tabs.tabBar().tabAt(position)
            if index < 0:
                return
            if self.tab_role(index) != "new-session":
                self.tabs.setCurrentIndex(index)
            menu = QMenu(self)
            menu.addAction("New local terminal", self.open_local_terminal_tab)
            menu.addAction("Split horizontal", lambda: self.add_split("horizontal"))
            menu.addAction("Split vertical", lambda: self.add_split("vertical"))
            menu.addSeparator()
            duplicate_action = menu.addAction("Duplicate tab", self.duplicate_current_tab)
            close_action = menu.addAction("Close tab", self.close_current_tab)
            close_others_action = menu.addAction("Close other tabs", lambda: self.close_other_tabs(index))
            role = self.tab_role(index)
            duplicate_action.setEnabled(role not in {"home", "new-session"})
            close_action.setEnabled(role not in {"home", "new-session"})
            close_others_action.setEnabled(self.count_closeable_tabs(except_index=index) > 0)
            menu.addSeparator()
            menu.addAction("Recover previous sessions", self.recover_previous_sessions)
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
            panel = QFrame()
            panel.setObjectName("mobaHomeWelcomeSurface")
            panel.setProperty("designPreset", "mobaxterm")
            panel.setProperty("mobaHomeTitle", chrome.title)
            panel.setProperty("mobaHomeSubtitle", chrome.subtitle)
            panel.setProperty("mobaHomeSearchWidth", chrome.search_width)
            panel.setProperty("mobaHomeRecentTitle", chrome.recent_title)
            panel.setProperty("mobaHomeActionSpacing", chrome.action_spacing)
            panel.setMinimumWidth(chrome.surface_width)
            panel.setMaximumWidth(chrome.surface_width + 120)

            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(13)

            title_row = QHBoxLayout()
            title_row.setSpacing(18)
            title_row.addStretch(1)
            logo = QLabel()
            logo.setObjectName("mobaHomeLogo")
            logo.setProperty("mobaHomeIconKey", chrome.icon_key)
            logo.setFixedSize(QSize(64, 56))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setPixmap(self.moba_ribbon_icon(chrome.icon_key, "#1a1a1a", size=56).pixmap(QSize(56, 56)))
            title_column = QVBoxLayout()
            title_column.setSpacing(3)
            title = QLabel(chrome.title)
            title.setObjectName("mobaHomeTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            subtitle = QLabel(chrome.subtitle)
            subtitle.setObjectName("mobaHomeSubtitle")
            subtitle.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            title_column.addWidget(title)
            title_column.addWidget(subtitle)
            title_row.addWidget(logo)
            title_row.addLayout(title_column)
            title_row.addStretch(1)
            panel_layout.addLayout(title_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(chrome.action_spacing)
            action_row.addStretch(1)
            primary_action, secondary_action = surface.home_actions[:2]
            start_button = QPushButton(primary_action)
            start_button.setObjectName("mobaHomePrimaryAction")
            start_button.setProperty("mobaHomeActionKey", "primary")
            start_button.setProperty("mobaHomeActionIconKey", chrome.primary_action_icon_key)
            start_button.setIcon(self.moba_ribbon_icon(chrome.primary_action_icon_key, "#4db7ff", size=18))
            start_button.setMinimumWidth(200)
            recover_button = QPushButton(secondary_action)
            recover_button.setObjectName("mobaHomeAction")
            recover_button.setProperty("mobaHomeActionKey", "secondary")
            recover_button.setProperty("mobaHomeActionIconKey", chrome.secondary_action_icon_key)
            recover_button.setIcon(self.moba_ribbon_icon(chrome.secondary_action_icon_key, "#35d7c7", size=18))
            recover_button.setMinimumWidth(218)
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
            search.setPlaceholderText(surface.home_search_placeholder)
            search.setMinimumWidth(chrome.search_width)
            search.setMaximumWidth(chrome.search_width)
            search.returnPressed.connect(lambda: self.run_home_search(search.text()))
            panel_layout.addWidget(search, 0, Qt.AlignmentFlag.AlignCenter)

            recent_title = QLabel(chrome.recent_title)
            recent_title.setObjectName("recentSessionsTitle")
            recent_title.setProperty("mobaHomeRecentTitle", chrome.recent_title)
            recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            recent_title.setContentsMargins(0, 9, 0, 0)
            panel_layout.addWidget(recent_title)

            recent_grid = QHBoxLayout()
            recent_grid.setSpacing(44)
            for column_index, column in enumerate(surface.recent_columns):
                column_layout = QVBoxLayout()
                column_layout.setSpacing(5)
                for row_index, item in enumerate(column):
                    label = QLabel(item)
                    label.setObjectName("mobaRecentSession")
                    label.setProperty("mobaHomeRecentColumn", column_index)
                    label.setProperty("mobaHomeRecentRow", row_index)
                    column_layout.addWidget(label)
                recent_grid.addLayout(column_layout)
            panel_layout.addLayout(recent_grid)

            footer = QLabel(surface.footer)
            footer.setObjectName("mobaHomeFooter")
            footer.setProperty("mobaHomeFooter", surface.footer)
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setContentsMargins(0, 12, 0, 0)
            panel_layout.addWidget(footer)
            return panel

        def build_product_workflow_evidence(self) -> QFrame:
            cards = gui_design_workflow_cards(self.current_design_id())
            panel = QFrame()
            panel.setObjectName("productWorkflowEvidence")
            panel.setProperty("designPreset", self.current_design_id())
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)
            for card in cards[:3]:
                card_frame = QFrame()
                card_frame.setObjectName("productWorkflowCard")
                card_frame.setProperty("workflowKey", card.key)
                card_frame.setMinimumWidth(190)
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
                card_layout.addWidget(title)
                card_layout.addWidget(primary)
                card_layout.addWidget(secondary)
                layout.addWidget(card_frame)
            return panel

        def build_product_workspace_surface_evidence(self, surface) -> QFrame:
            panel = QFrame()
            panel.setObjectName("productWorkspaceSurface")
            panel.setProperty("designPreset", self.current_design_id())
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
            if self.current_design_id() == "remmina":
                layout.addWidget(self.build_remmina_viewer_controls_evidence())
            if self.current_design_id() == "mremoteng":
                layout.addWidget(self.build_mremoteng_document_controls_evidence())
                layout.addWidget(self.build_mremoteng_property_grid_evidence())
            if self.current_design_id() == "securecrt":
                layout.addWidget(self.build_securecrt_session_status_strip_evidence())

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
            state = gui_design_interaction_state("mremoteng")
            panel = QFrame()
            panel.setObjectName("mRemoteNgDocumentControls")
            panel.setProperty("designPreset", "mremoteng")
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
            filter_input.setMinimumWidth(chrome.live_filter_width)
            filter_input.setMaximumWidth(chrome.live_filter_width)
            filter_input.setMinimumHeight(chrome.live_filter_height)
            self.mremoteng_document_filter = filter_input
            self.set_interaction_state(
                filter_input,
                "focused" if state.focused_control == "tree-filter" else "normal",
            )
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
            panel = QFrame()
            panel.setObjectName("mRemoteNgPropertyGrid")
            panel.setProperty("designPreset", "mremoteng")
            panel.setProperty("mRemoteNgPropertyColumnKeys", [column.key for column in chrome.columns])
            panel.setProperty("mRemoteNgPropertyRowKeys", [row.key for row in chrome.rows])
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
                    cell.setMinimumWidth(max(72, min(column.static_width, 190)))
                    cell.setToolTip(f"{row.property_label}: {values[column.key]}")
                    row_layout.addWidget(cell)
                layout.addWidget(row_frame)
            return panel

        def build_termius_header_chips_evidence(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("termiusHeaderChips")
            panel.setProperty("designPreset", "termius")
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
                layout.addWidget(label)
            return panel

        def build_termius_host_identity_strip_evidence(self) -> QFrame:
            strip = gui_design_termius_host_identity_strip()
            panel = QFrame()
            panel.setObjectName("termiusHostIdentityStrip")
            panel.setProperty("designPreset", "termius")
            panel.setProperty("termiusHostIdentityFieldKeys", [field.key for field in strip.fields])
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(6)

            title = QLabel(strip.title)
            title.setObjectName("termiusHostIdentityTitle")
            title.setMinimumWidth(88)
            layout.addWidget(title)
            for field in strip.fields:
                cell = QLabel(f"{field.label}: {field.value}")
                cell.setObjectName("termiusHostIdentityCell")
                cell.setProperty("termiusHostIdentityKey", field.key)
                cell.setProperty("termiusHostIdentityLabel", field.label)
                cell.setProperty("termiusHostIdentityValue", field.value)
                cell.setProperty("termiusHostIdentityWidth", field.static_width)
                cell.setToolTip(field.tooltip)
                cell.setMinimumWidth(max(78, min(field.static_width, 150)))
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(cell)
            layout.addStretch(1)
            return panel

        def build_remmina_viewer_controls_evidence(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("remminaViewerControls")
            panel.setProperty("designPreset", "remmina")
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
            panel = QFrame()
            panel.setObjectName("secureCrtSessionManagerChrome")
            panel.setProperty("designPreset", "securecrt")
            panel.setProperty("secureCrtSessionManagerActionKeys", [action.key for action in chrome.actions])
            panel.setProperty("secureCrtSessionFilterPlaceholder", chrome.filter_placeholder)
            panel.setMaximumHeight(94)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(7, 6, 7, 6)
            layout.setSpacing(5)

            title_row = QHBoxLayout()
            title_row.setSpacing(5)
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
                button.setToolTip(action.tooltip)
                button.setIcon(self.style().standardIcon(self.standard_icon(self.securecrt_session_manager_icon_name(action.icon_key))))
                button.setIconSize(QSize(14, 14))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setFixedSize(QSize(24, 24))
                button.clicked.connect(
                    lambda _checked=False, key=action.key: self.run_securecrt_session_manager_action(key)
                )
                title_row.addWidget(button)
            layout.addLayout(title_row)

            self.securecrt_session_filter = QLineEdit()
            self.securecrt_session_filter.setObjectName("secureCrtSessionFilter")
            self.securecrt_session_filter.setPlaceholderText(chrome.filter_placeholder)
            self.securecrt_session_filter.setMinimumHeight(24)
            self.securecrt_session_filter.textChanged.connect(self.filter_profile_tree)
            layout.addWidget(self.securecrt_session_filter)
            panel.setVisible(False)
            return panel

        def securecrt_session_manager_icon_name(self, icon_key: str) -> str:
            icon_map = {
                "connect": "SP_MediaPlay",
                "folder": "SP_DirIcon",
                "properties": "SP_FileDialogDetailedView",
            }
            return icon_map.get(icon_key, "SP_FileIcon")

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
            panel = QFrame()
            panel.setObjectName("termiusHostsChrome")
            panel.setProperty("designPreset", "termius")
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
            panel = QFrame()
            panel.setObjectName("remminaProfileListChrome")
            panel.setProperty("designPreset", "remmina")
            panel.setProperty("remminaProfileColumnKeys", [column.key for column in chrome.columns])
            panel.setProperty("remminaProfileRowKeys", [row.key for row in chrome.rows])
            panel.setMaximumHeight(166)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(7, 6, 7, 6)
            layout.setSpacing(5)

            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            title = QLabel(chrome.title)
            title.setObjectName("remminaProfileListTitle")
            title_row.addWidget(title)
            filter_input = QLineEdit()
            filter_input.setObjectName("remminaProfileFilter")
            filter_input.setPlaceholderText(chrome.filter_placeholder)
            filter_input.setReadOnly(True)
            filter_input.setMinimumWidth(142)
            self.remmina_profile_filter = filter_input
            title_row.addWidget(filter_input, 1)
            layout.addLayout(title_row)

            header = QHBoxLayout()
            header.setSpacing(4)
            for column in chrome.columns:
                label = QLabel(column.label)
                label.setObjectName("remminaProfileListColumn")
                label.setProperty("remminaProfileColumnKey", column.key)
                label.setProperty("remminaProfileColumnWidth", column.static_width)
                label.setMinimumWidth(max(48, min(column.static_width, 112)))
                header.addWidget(label)
            layout.addLayout(header)

            for row in chrome.rows:
                row_frame = QFrame()
                row_frame.setObjectName("remminaProfileListRow")
                row_frame.setProperty("remminaProfileRowKey", row.key)
                row_frame.setProperty("remminaProfileProtocol", row.protocol)
                row_frame.setProperty("selectedRow", "true" if row.selected else "false")
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(5, 3, 5, 3)
                row_layout.setSpacing(4)
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
                    cell.setMinimumWidth(max(48, min(column.static_width, 112)))
                    cell.setToolTip(f"{row.name}: {row.status}")
                    row_layout.addWidget(cell)
                status = QLabel(row.status)
                status.setObjectName("remminaProfileListCell")
                status.setProperty("remminaProfileRowKey", row.key)
                status.setProperty("remminaProfileColumnKey", "status")
                status.setProperty("remminaProfileCellValue", row.status)
                status.setToolTip(f"{row.name}: {row.status}")
                row_layout.addWidget(status, 1)
                layout.addWidget(row_frame)
            return panel

        def build_securecrt_session_status_strip_evidence(self) -> QFrame:
            chrome = gui_design_securecrt_session_status_strip()
            panel = QFrame()
            panel.setObjectName("secureCrtSessionStatusStrip")
            panel.setProperty("designPreset", "securecrt")
            panel.setProperty("secureCrtSessionStatusFieldKeys", [field.key for field in chrome.fields])
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(6)

            title = QLabel(chrome.title)
            title.setObjectName("secureCrtSessionStatusTitle")
            title.setMinimumWidth(86)
            layout.addWidget(title)
            for field in chrome.fields:
                cell = QLabel(f"{field.label}: {field.value}")
                cell.setObjectName("secureCrtSessionStatusCell")
                cell.setProperty("secureCrtSessionStatusKey", field.key)
                cell.setProperty("secureCrtSessionStatusLabel", field.label)
                cell.setProperty("secureCrtSessionStatusValue", field.value)
                cell.setProperty("secureCrtSessionStatusWidth", field.static_width)
                cell.setToolTip(field.tooltip)
                cell.setMinimumWidth(max(84, min(field.static_width, 170)))
                cell.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(cell)
            layout.addStretch(1)
            return panel

        def build_securecrt_command_window_evidence(self) -> QFrame:
            chrome = gui_design_securecrt_command_window_chrome()
            panel = QFrame()
            panel.setObjectName("secureCrtCommandWindow")
            panel.setProperty("secureCrtCommandWindowKey", chrome.key)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 7, 8, 7)
            layout.setSpacing(5)

            header = QHBoxLayout()
            header.setSpacing(8)
            title = QLabel(chrome.title)
            title.setObjectName("secureCrtCommandTitle")
            helper = QLabel(chrome.helper)
            helper.setObjectName("secureCrtCommandHelper")
            header.addWidget(title)
            header.addWidget(helper)
            header.addStretch(1)
            layout.addLayout(header)

            command_row = QHBoxLayout()
            command_row.setSpacing(8)
            target = QLabel(chrome.target_scope)
            target.setObjectName("secureCrtCommandTarget")
            target.setProperty("secureCrtCommandWindowKey", chrome.key)
            target.setMinimumWidth(112)
            command_input = QLabel(chrome.command)
            command_input.setObjectName("secureCrtCommandInput")
            command_input.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            send = QLabel(chrome.send_label)
            send.setObjectName("secureCrtCommandSend")
            send.setProperty("secureCrtCommandWindowKey", chrome.key)
            send.setMinimumWidth(48)
            status = QLabel(chrome.status)
            status.setObjectName("secureCrtCommandStatus")
            status.setProperty("secureCrtCommandWindowKey", chrome.key)
            command_row.addWidget(target)
            command_row.addWidget(command_input, 1)
            command_row.addWidget(send)
            command_row.addWidget(status)
            layout.addLayout(command_row)
            return panel

        def build_product_reference_state_evidence(self) -> QFrame:
            reference = gui_design_reference_state(self.current_design_id())
            panel = QFrame()
            panel.setObjectName("productReferenceState")
            panel.setProperty("designPreset", self.current_design_id())
            layout = QHBoxLayout(panel)
            layout.setContentsMargins(7, 5, 7, 5)
            layout.setSpacing(8)
            for key, value in reference.items():
                label = QLabel(f"{key}: {value}")
                label.setObjectName("productReferenceStateItem")
                label.setProperty("referenceKey", key)
                label.setToolTip(f"{reference.active_tab_label} {key}")
                layout.addWidget(label)
            layout.addStretch(1)
            return panel

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
            if tab_status:
                self.tabs.setTabToolTip(index, f"{tab_title or plan.title}: {tab_status}")
            self.update_session_status()

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
            self.apply_moba_tab_chrome(
                index,
                key=active_tab.key,
                icon_key=active_tab.icon_key,
                tooltip=active_tab.tooltip,
                closeable=active_tab.closeable,
            )
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
