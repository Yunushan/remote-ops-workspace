from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from urllib.parse import urlparse

from .doctor import run_doctor
from .file_transfer import build_sftp_queue_plan, parse_transfer_item_spec, preview_local_path
from .gui_designs import GUI_DESIGN_PRESETS, get_gui_design_preset
from .gui_editors import (
    layout_from_editor_data,
    layout_to_editor_data,
    profile_from_editor_data,
    profile_to_editor_data,
)
from .gui_lifecycle import ProcessStopPolicy, ProcessStopResult, stop_process
from .launcher import LauncherError, build_launch_plan
from .layouts import Layout, LayoutStore, build_layout_terminal_plans
from .moba_connected import MobaConnectedSessionState, build_moba_connected_session_state
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
        from PyQt6.QtCore import QProcess, QSize, Qt
        from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QFrame,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMenu,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QSizePolicy,
            QSplitter,
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

    class MobaConnectedSessionPanel(QWidget):
        def __init__(self, state: MobaConnectedSessionState, terminal_pane: TerminalPane) -> None:
            super().__init__()
            self.setObjectName("mobaConnectedSession")
            self.state = state
            self.terminal_pane = terminal_pane

            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            body = QSplitter(Qt.Orientation.Horizontal)
            body.setObjectName("mobaConnectedBody")
            body.addWidget(self.build_sftp_browser())
            body.addWidget(self.build_terminal_area())
            body.setStretchFactor(1, 1)
            body.setSizes([388, 792])
            root.addWidget(body, 1)
            root.addWidget(self.build_telemetry_bar())

        def build_sftp_browser(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("mobaSftpBrowser")
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(5, 5, 5, 5)
            layout.setSpacing(4)

            toolbar = QFrame()
            toolbar.setObjectName("mobaSftpToolbar")
            toolbar_layout = QHBoxLayout(toolbar)
            toolbar_layout.setContentsMargins(0, 0, 0, 0)
            toolbar_layout.setSpacing(4)
            for label, icon_name, tooltip in [
                ("Refresh", "SP_BrowserReload", "Refresh remote directory"),
                ("Up", "SP_ArrowUp", "Go to parent directory"),
                ("Download", "SP_ArrowDown", "Download selected remote item"),
                ("Upload", "SP_ArrowUp", "Upload local item"),
                ("New", "SP_DirIcon", "Create remote folder"),
                ("Delete", "SP_TrashIcon", "Delete selected remote item"),
            ]:
                toolbar_layout.addWidget(self.tool_button(label, icon_name, tooltip))
            toolbar_layout.addStretch(1)
            layout.addWidget(toolbar)

            path = QLineEdit()
            path.setObjectName("mobaSftpPath")
            path.setText(self.state.remote_path)
            path.setToolTip(self.state.follow_folder_plan.printable_batch())
            layout.addWidget(path)

            self.file_table = QTreeWidget()
            self.file_table.setObjectName("mobaSftpFileTable")
            self.file_table.setColumnCount(3)
            self.file_table.setHeaderLabels(["Name", "Size (KB)", "Last modified"])
            self.file_table.setRootIsDecorated(False)
            self.file_table.setUniformRowHeights(True)
            self.file_table.setSortingEnabled(False)
            for entry in self.state.file_entries:
                item = QTreeWidgetItem([entry.name, str(entry.size_kb), entry.modified])
                icon_name = "SP_DirIcon" if entry.kind == "dir" else "SP_FileIcon"
                item.setIcon(0, self.style().standardIcon(self.standard_icon(icon_name)))
                item.setToolTip(0, f"{entry.kind}: {entry.name}")
                self.file_table.addTopLevelItem(item)
            self.file_table.resizeColumnToContents(0)
            layout.addWidget(self.file_table, 1)

            layout.addWidget(self.build_remote_monitoring())
            return panel

        def build_terminal_area(self) -> QWidget:
            area = QWidget()
            area.setObjectName("mobaTerminalArea")
            layout = QVBoxLayout(area)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.build_ssh_banner())
            layout.addWidget(self.terminal_pane, 1)
            return area

        def build_ssh_banner(self) -> QFrame:
            banner = QFrame()
            banner.setObjectName("mobaSshBanner")
            layout = QVBoxLayout(banner)
            layout.setContentsMargins(14, 10, 14, 10)
            layout.setSpacing(2)
            for line in self.state.banner.lines():
                label = QLabel(line)
                label.setObjectName("mobaSshBannerLine")
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                layout.addWidget(label)
            return banner

        def build_remote_monitoring(self) -> QFrame:
            panel = QFrame()
            panel.setObjectName("mobaRemoteMonitoring")
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(5)
            title = QLabel("Remote monitoring")
            title.setObjectName("mobaRemoteMonitoringTitle")
            layout.addWidget(title)
            metrics = [
                f"CPU {self.state.monitoring.cpu_percent}%",
                f"RAM {self.state.monitoring.memory_label}",
                f"Disk {self.state.monitoring.disk_label}",
                f"Load {self.state.monitoring.load_average}",
                f"Processes {self.state.monitoring.process_count}",
            ]
            for metric in metrics:
                label = QLabel(metric)
                label.setObjectName("mobaMonitoringMetric")
                layout.addWidget(label)
            follow = QCheckBox("Follow terminal folder")
            follow.setObjectName("mobaFollowTerminalFolder")
            follow.setChecked(self.state.follow_terminal_folder)
            follow.setToolTip(self.state.follow_folder_plan.printable_batch())
            layout.addWidget(follow)
            return panel

        def build_telemetry_bar(self) -> QFrame:
            bar = QFrame()
            bar.setObjectName("mobaTelemetryBar")
            layout = QHBoxLayout(bar)
            layout.setContentsMargins(8, 3, 8, 3)
            layout.setSpacing(16)
            telemetry = [
                self.state.target,
                f"{self.state.monitoring.cpu_percent}% CPU",
                f"RAM {self.state.monitoring.memory_label}",
                f"Disk {self.state.monitoring.disk_label}",
                f"Net {self.state.monitoring.network_label}",
                f"Connections: {self.state.monitoring.connection_count}",
                f"Processes: {self.state.monitoring.process_count}",
            ]
            for text in telemetry:
                label = QLabel(text)
                label.setObjectName("mobaTelemetryItem")
                layout.addWidget(label)
            layout.addStretch(1)
            return bar

        def tool_button(self, label: str, icon_name: str, tooltip: str) -> QToolButton:
            button = QToolButton()
            button.setObjectName("mobaSftpAction")
            button.setText(label)
            button.setToolTip(tooltip)
            button.setIcon(self.style().standardIcon(self.standard_icon(icon_name)))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFixedSize(QSize(24, 24))
            return button

        def standard_icon(self, icon_name: str):
            return getattr(QStyle.StandardPixmap, icon_name, QStyle.StandardPixmap.SP_FileIcon)

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

    class MainWindow(QMainWindow):
        CLOSE_STOP_POLICY = ProcessStopPolicy(terminate_timeout_ms=2000, kill_timeout_ms=500)

        def __init__(self) -> None:
            super().__init__()
            self.setObjectName("remoteOpsMain")
            self.setWindowTitle("Remote Ops Workspace")
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
            self.moba_exit_button = self.toolbar_button("Exit", "SP_DialogCloseButton", "Close Remote Ops Workspace")
            self.moba_exit_button.setObjectName("mobaExitAction")
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
            self.quick_connect = QLineEdit()
            self.quick_connect.setObjectName("quickConnect")
            self.quick_connect.setPlaceholderText("Quick connect...")
            self.quick_connect_suggestions = QTreeWidget()
            self.quick_connect_suggestions.setObjectName("quickConnectSuggestions")
            self.quick_connect_suggestions.setHeaderHidden(True)
            self.quick_connect_suggestions.setColumnCount(1)
            self.quick_connect_suggestions.setRootIsDecorated(False)
            self.quick_connect_suggestions.setUniformRowHeights(True)
            self.quick_connect_suggestions.setMaximumHeight(126)
            self.quick_connect_suggestions.setVisible(False)
            self.moba_rail = self.create_moba_rail()
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
            for title in ["Terminal", "Sessions", "View", "X server", "Tools", "Games", "Settings", "Macros", "Help"]:
                menu = self.menuBar().addMenu(title)
                if title == "Terminal":
                    menu.addAction("Start local terminal", lambda _checked=False: self.add_split("horizontal"))
                elif title == "Sessions":
                    menu.addAction("New session", self.create_profile)
                    menu.addAction("Connect selected", lambda _checked=False: self.connect_selected(False))
                elif title == "View":
                    self.view_menu = menu
                    menu.addAction("Refresh sessions", self.refresh_profiles)
                elif title == "Help":
                    menu.addAction("Run doctor", self.show_doctor)
                else:
                    menu.addAction(title)

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

        def build_moba_ribbon_buttons(self) -> list[QToolButton]:
            items = [
                ("Session", "SP_FileIcon", "Create a new saved session", self.create_profile),
                ("Servers", "SP_BrowserReload", "Refresh saved sessions", self.refresh_profiles),
                ("Tools", "SP_FileDialogDetailedView", "Edit selected profile", self.edit_selected_profile),
                ("Games", "SP_DialogHelpButton", "Show optional tool status", self.show_moba_tools_status),
                ("Sessions", "SP_MediaPlay", "Connect selected profile", lambda _checked=False: self.connect_selected(False)),
                ("View", "SP_DesktopIcon", "Cycle to the next visual preset", self.cycle_design_preset),
                ("Split", "SP_TitleBarShadeButton", "Open a horizontal split", lambda _checked=False: self.add_split("horizontal")),
                ("MultiExec", "SP_CommandLink", "Show selected launch command", lambda _checked=False: self.connect_selected(True)),
                ("Tunneling", "SP_DirLinkIcon", "Show tunneling workflow status", self.show_moba_tunneling_status),
                ("Packages", "SP_DirIcon", "Show package and file-transfer workflows", self.show_moba_packages_dialog),
                ("Settings", "SP_FileDialogInfoView", "Edit selected profile", self.edit_selected_profile),
                ("Help", "SP_MessageBoxInformation", "Show help and diagnostics workflows", self.show_moba_help_dialog),
            ]
            buttons: list[QToolButton] = []
            for label, icon_name, tooltip, slot in items:
                button = self.toolbar_button(label, icon_name, tooltip)
                button.setObjectName("mobaRibbonButton")
                button.clicked.connect(slot)
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
            for text, object_name, tooltip, slot in [
                ("<<", "mobaRailButton", "Collapse or restore the sessions panel", self.toggle_moba_session_panel),
                ("S\ne\ns\ns\ni\no\nn\ns", "mobaRailButton", "Show saved sessions", self.show_moba_sessions_rail),
                ("*", "mobaRailAccent", "Show favorite sessions status", self.show_moba_favorites_rail),
                ("T\no\no\nl\ns", "mobaRailButton", "Show tools status", self.show_moba_tools_status),
                ("M\na\nc\nr\no\ns", "mobaRailButton", "Show macros status", self.show_moba_macros_status),
            ]:
                button = QToolButton()
                button.setObjectName(object_name)
                button.setText(text)
                button.setToolTip(tooltip)
                button.setCheckable(text != "<<")
                button.setAutoRaise(False)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.clicked.connect(slot)
                layout.addWidget(button)
                self.moba_rail_buttons.append(button)
            self.set_moba_rail_active("sessions")
            layout.addStretch(1)
            return rail

        def create_left_panel(self) -> QWidget:
            panel = QWidget()
            panel.setObjectName("leftPanel")
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.quick_connect)
            layout.addWidget(self.quick_connect_suggestions)
            body = QWidget()
            body_layout = QHBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(0)
            body_layout.addWidget(self.moba_rail)
            body_layout.addWidget(self.profile_list, 1)
            layout.addWidget(body, 1)
            return panel

        def refresh_profiles(self) -> None:
            selected_name = self.selected_profile_name()
            self.profile_list.clear()
            profiles = sorted(self.store.load(), key=lambda item: (item.group, item.name))
            root = QTreeWidgetItem(["User sessions"])
            root.setData(0, Qt.ItemDataRole.UserRole, None)
            root.setIcon(0, self.style().standardIcon(self.standard_icon("SP_DirHomeIcon")))
            root.setToolTip(0, "Saved Remote Ops Workspace sessions")
            self.profile_list.addTopLevelItem(root)
            group_nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}
            for profile in profiles:
                parent = root
                path: list[str] = []
                for part in self.profile_group_parts(profile.group):
                    path.append(part)
                    key = tuple(path)
                    if key not in group_nodes:
                        group_item = QTreeWidgetItem([part])
                        group_item.setData(0, Qt.ItemDataRole.UserRole, None)
                        group_item.setIcon(0, self.style().standardIcon(self.standard_icon("SP_DirIcon")))
                        group_item.setToolTip(0, f"Session folder: {'/'.join(path)}")
                        parent.addChild(group_item)
                        group_nodes[key] = group_item
                    parent = group_nodes[key]
                item = QTreeWidgetItem([self.profile_tree_label(profile)])
                item.setData(0, Qt.ItemDataRole.UserRole, profile.name)
                item.setIcon(0, self.profile_icon_for_protocol(profile.protocol))
                item.setToolTip(0, f"{profile.protocol.upper()}  {profile.display_target}\nProfile: {profile.name}")
                parent.addChild(item)
            self.profile_list.expandAll()
            if selected_name:
                self.select_profile(selected_name)
            self.refresh_layouts()

        def profile_group_parts(self, group: str) -> list[str]:
            parts = [part.strip() for part in group.replace("\\", "/").split("/") if part.strip()]
            return parts or ["default"]

        def profile_tree_label(self, profile) -> str:
            if self.current_design_is_moba():
                return profile.name
            protocol = profile.protocol.upper()
            target = profile.display_target
            return f"[{protocol}] {profile.name}  {target}" if target else f"[{protocol}] {profile.name}"

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
            self.menuBar().setVisible(is_moba)
            self.quick_connect.setVisible(is_moba)
            self.moba_rail.setVisible(is_moba)
            self.update_quick_connect_suggestions()
            self.layout_toolbar.setVisible(not is_moba)
            self.log.setVisible(not is_moba)
            self.refresh_profiles()
            self.main_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
            self.layout_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
            self.configure_toolbar_for_design(is_moba, preset.toolbar_icon_size)
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
            self.log.setPlaceholderText(
                f"{preset.description}\n\nLaunch output, dry-run commands and doctor reports appear here."
            )
            self.statusBar().showMessage(f"View: {preset.label}")

        def configure_toolbar_for_design(self, is_moba: bool, icon_size: int) -> None:
            icon = QSize(icon_size, icon_size)
            self.main_toolbar.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                if is_moba
                else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            )
            for button in self.main_toolbar_buttons + self.layout_toolbar_buttons:
                button.setIconSize(icon)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
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
            if not self.current_design_is_moba():
                self.quick_connect_suggestions.setVisible(False)
                return
            candidates = quick_connect_candidates(self.quick_connect.text(), self.store.load(), limit=6)
            for candidate in candidates:
                item = QTreeWidgetItem([f"{candidate.label}    {candidate.detail}"])
                item.setData(0, Qt.ItemDataRole.UserRole, candidate)
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
            self.quick_connect_suggestions.setVisible(self.quick_connect_suggestions.topLevelItemCount() > 0)

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
            active_text = {
                "sessions": "S\n",
                "favorites": "*",
                "tools": "T\n",
                "macros": "M\n",
            }.get(active, "")
            for button in getattr(self, "moba_rail_buttons", []):
                button.setChecked(bool(active_text and button.text().startswith(active_text)))

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
            self.set_moba_rail_active("sessions")
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
            if home_index >= 0:
                self.tabs.setTabText(home_index, "Home" if is_moba else "Welcome")
                self.tabs.setTabToolTip(home_index, "Remote Ops Workspace home")
            if is_moba:
                if home_index < 0:
                    self.add_welcome_tab()
                    home_index = self.find_tab_by_role("home")
                    if home_index >= 0:
                        self.tabs.setTabText(home_index, "Home")
                self.ensure_new_session_tab()
            else:
                self.remove_new_session_tab()
            self.refresh_special_tab_buttons()

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
            self.add_workspace_tab(new_tab, "+", select=False, role="new-session")
            self.tabs.setTabToolTip(self.find_tab_by_role("new-session"), "Open a new local terminal")

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
                for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                    tab_bar.setTabButton(new_index, position, None)

        def handle_tab_changed(self, index: int) -> None:
            if self.moba_tab_guard or index < 0:
                return
            if self.tab_role(index) != "new-session":
                return
            self.moba_tab_guard = True
            try:
                self.open_local_terminal_tab()
            finally:
                self.moba_tab_guard = False

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

        def iter_profile_tree_items(self):
            def walk(item):
                yield item
                for child_index in range(item.childCount()):
                    yield from walk(item.child(child_index))

            for index in range(self.profile_list.topLevelItemCount()):
                yield from walk(self.profile_list.topLevelItem(index))

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
            if self.moba_connected_profile_supported(profile):
                self.open_moba_connected_session_tab(profile, pane_plan)
            else:
                self.open_terminal_tab(pane_plan)
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
                    self.open_moba_connected_session_tab(profile, pane_plan, remote_path=profile.path or "/")
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

        def add_welcome_tab(self) -> None:
            box = QWidget()
            box.setObjectName("welcomeHome")
            layout = QVBoxLayout(box)
            layout.setContentsMargins(48, 48, 48, 48)
            layout.addStretch(1)

            panel = QFrame()
            panel.setObjectName("welcomePanel")
            panel.setMinimumWidth(520)
            panel.setMaximumWidth(610)
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
            title = QLabel("Remote Ops Workspace")
            title.setObjectName("welcomeTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            title_row.addWidget(logo)
            title_row.addWidget(title)
            title_row.addStretch(1)
            panel_layout.addLayout(title_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(96)
            action_row.addStretch(1)
            start_button = QPushButton("Start local terminal")
            start_button.setObjectName("mobaHomePrimaryAction")
            start_button.setIcon(self.style().standardIcon(self.standard_icon("SP_DialogApplyButton")))
            start_button.setMinimumWidth(200)
            recover_button = QPushButton("Recover previous sessions")
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
            search.setPlaceholderText("Find existing session or server name...")
            search.setMinimumWidth(405)
            search.setMaximumWidth(405)
            search.returnPressed.connect(lambda: self.run_home_search(search.text()))
            panel_layout.addWidget(search, 0, Qt.AlignmentFlag.AlignCenter)

            recent_title = QLabel("Recent sessions")
            recent_title.setObjectName("recentSessionsTitle")
            recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            recent_title.setContentsMargins(0, 9, 0, 0)
            panel_layout.addWidget(recent_title)

            recent_grid = QHBoxLayout()
            recent_grid.setSpacing(44)
            for column in [
                ["[ssh] edge-linux-02", "[ssh] lab-sftp-01", "..."],
                ["[rdp] lab-admin", "[vnc] lab-view", "..."],
                ["[ssh] example-ssh", "[https] example-web", "..."],
            ]:
                column_layout = QVBoxLayout()
                column_layout.setSpacing(5)
                for item in column:
                    label = QLabel(item)
                    label.setObjectName("recentSessionsLabel")
                    column_layout.addWidget(label)
                recent_grid.addLayout(column_layout)
            panel_layout.addLayout(recent_grid)

            promo = QLabel("Use open protocols and local profiles with Remote Ops Workspace.")
            promo.setObjectName("homePromo")
            promo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            promo.setContentsMargins(0, 12, 0, 0)
            panel_layout.addWidget(promo)

            layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignCenter)
            layout.addStretch(2)
            self.add_workspace_tab(
                box,
                "Home" if self.current_design_is_moba() else "Welcome",
                select=self.tabs.count() == 0,
                role="home",
            )

        def run_home_search(self, text: str) -> None:
            self.quick_connect.setText(text)
            self.run_quick_connect()

        def open_local_terminal_tab(self) -> None:
            self.open_terminal_tab(default_shell_plan(self.next_shell_index()))

        def next_shell_index(self) -> int:
            count = sum(1 for pane in self.all_terminal_panes() if pane.plan.source == "shell")
            return count + 1

        def open_terminal_tab(self, plan: TerminalPanePlan) -> None:
            pane = self.new_terminal_pane(plan)
            self.remember_terminal_plan(plan)
            self.add_workspace_tab(pane, plan.title, role="terminal")
            self.update_session_status()

        def moba_connected_profile_supported(self, profile: Profile) -> bool:
            return self.current_design_is_moba() and profile.protocol.lower() in {"ssh", "sftp"}

        def open_moba_connected_session_tab(
            self,
            profile: Profile,
            plan: TerminalPanePlan,
            *,
            remote_path: str = "/",
        ) -> None:
            state = build_moba_connected_session_state(profile, remote_path=remote_path)
            panel = MobaConnectedSessionPanel(state, self.new_terminal_pane(plan))
            self.remember_terminal_plan(plan)
            self.add_workspace_tab(panel, plan.title, role="terminal")
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
