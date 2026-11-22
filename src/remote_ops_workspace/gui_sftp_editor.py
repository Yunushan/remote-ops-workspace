from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import (
    QProcess,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QColor,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QStyle,
    QToolButton,
    QTreeWidgetItem,
    QWidget,
)

from .file_transfer import (
    SftpBatchPlan,
    build_sftp_get_plan,
)
from .moba_connected import (
    MobaConnectedSessionState,
    moba_connected_text_editor_route,
)
from .moba_text import (
    MobaTextEditorTabPlan,
    build_moba_text_editor_tab_plan,
    prepare_managed_edit_cache,
    unified_text_diff,
    write_text_document,
)
from .models import Profile
from .terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    ssh_command_with_control_path,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QTreeWidget

    from .gui_connected import ConnectedGuiServices

# These roles let the editor identify the originating row in the connected dock.
SFTP_ROW_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 42
SFTP_ROW_SOURCE_PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 47
SFTP_ROW_INDEX_ROLE = int(Qt.ItemDataRole.UserRole) + 48


def _restore_document_format(baseline: str, qt_text: str) -> str:
    """Restore the original signature and paragraph endings hidden by QTextDocument."""
    signature = "\ufeff" if baseline.startswith("\ufeff") else ""
    text = baseline[len(signature):]
    parts = re.split(r"(\r\n|[\r\n\u2029])", text)
    lines, endings = parts[::2], parts[1::2]
    if qt_text == "\u2029".join(lines):
        return baseline
    first_ending = endings[0] if endings else "\n"
    if len(set(endings)) <= 1:
        return signature + qt_text.replace("\u2029", first_ending)

    # Keep matching lines' separators in mixed-format files. Replacement
    # lines inherit the replaced separators; new lines use the first style.
    edited_lines = qt_text.split("\u2029")
    edited_endings = [first_ending] * (len(edited_lines) - 1)
    matcher = difflib.SequenceMatcher(None, lines, edited_lines)
    for _tag, i, j, k, end in matcher.get_opcodes():
        for index, ending in zip(range(k, min(end, len(edited_endings))), endings[i:j], strict=False):
            edited_endings[index] = ending
    edited_endings.append("")
    return signature + "".join(line + ending for line, ending in zip(edited_lines, edited_endings, strict=True))


class MobaTextEditorHighlighter(QSyntaxHighlighter):
    def __init__(self, document, syntax: str) -> None:
        super().__init__(document)
        self.set_syntax(syntax)

    def set_syntax(self, syntax: str) -> None:
        self.syntax = syntax
        self.patterns = self.patterns_for_syntax(syntax)
        self.rehighlight()

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


class SftpTextEditor(QFrame):
    """Own the remote editor widgets and their nonblocking SFTP operation."""

    if TYPE_CHECKING:
        _connected_services: ConnectedGuiServices
        _background_auth_prompt_buffers: dict[str, bytearray]
        _background_auth_prompt_complete: dict[str, bool]
        _background_password: bytearray | None
        active_remote_path: str
        file_table: QTreeWidget
        runtime_shutting_down: bool
        state: MobaConnectedSessionState
        text_editor: QPlainTextEdit
        text_editor_toolbar: QFrame

        def _submit_background_password_if_prompt(self, process_kind: str, payload: bytes) -> None: ...
        def _write_connected_sftp_batch(self, process: QProcess, plan: SftpBatchPlan, process_kind: str) -> int: ...
        def background_ssh_overrides(self) -> dict[str, str]: ...
        def ensure_background_authentication_for_request(self, *, allow_prompt: bool = False) -> bool: ...
        def profile_for_sftp_action(self) -> Profile | None: ...
        def schedule_background_auth_retry(self, *, waiting_for_smartcard: bool = False) -> None: ...
        def shared_ssh_control_path(self) -> str: ...
        def show_sftp_status(self, message: str) -> None: ...
        def standard_icon(self, icon_name: str) -> QStyle.StandardPixmap: ...

    def initialize_text_editor_runtime(self, process_factory: Callable[..., Any]) -> None:
        self.text_editor_output_buffer = bytearray()
        self.text_editor_process = process_factory(self, interactive_auth=True)
        self.text_editor_process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )
        self.text_editor_process.started.connect(
            self.write_text_editor_sftp_batch
        )
        self.text_editor_process.readyReadStandardOutput.connect(
            self.read_text_editor_sftp_output
        )
        self.text_editor_process.finished.connect(
            self.handle_text_editor_sftp_finished
        )
        self.text_editor_process.errorOccurred.connect(
            self.handle_text_editor_sftp_error
        )
        self.text_editor_timeout = QTimer(self)
        self.text_editor_timeout.setSingleShot(True)
        self.text_editor_timeout.timeout.connect(
            self.cancel_text_editor_sftp_timeout
        )
        self.text_editor_auth_probe_timer = QTimer(self)
        self.text_editor_auth_probe_timer.setSingleShot(True)
        self.text_editor_auth_probe_timer.setInterval(1200)
        self.text_editor_auth_probe_timer.timeout.connect(
            lambda: self.write_text_editor_sftp_batch(force=True)
        )
        self.text_editor_generation = 0
        self.text_editor_active_generation = 0
        self.text_editor_operation = ""
        self.text_editor_tab_plan: MobaTextEditorTabPlan | None = None
        self.text_editor_sftp_plan: SftpBatchPlan | None = None
        self.text_editor_pending_sftp: tuple[str, SftpBatchPlan, str, str] | None = None
        self.text_editor_remote_path = ""
        self.text_editor_local_path = ""
        self.text_editor_probe_path = ""
        self.text_editor_baseline_text = ""
        self.text_editor_original_remote_sha256 = ""
        self.text_editor_cache_sha256 = ""
        self.text_editor_approved_remote_sha256 = ""
        self.text_editor_review_in_progress = False

    def apply_connected_text_editor_route_properties(self, widget, *, triggered: bool = False, status: str = "ready") -> None:
        route = moba_connected_text_editor_route(self.state)
        properties = {
            "mobaTextEditorSchema": route.schema,
            "mobaTextEditorProfile": route.profile_name,
            "mobaTextEditorRemotePath": route.remote_path,
            "mobaTextEditorLocalPath": route.local_path,
            "mobaTextEditorSyntax": route.syntax,
            "mobaTextEditorEncoding": route.encoding,
            "mobaTextEditorRemoteSha256": route.remote_sha256,
            "mobaTextEditorOpenedFromSftpBrowser": route.opened_from_sftp_browser,
            "mobaTextEditorSourceBrowserObject": route.source_browser_object,
            "mobaTextEditorSourceTableObject": route.source_table_object,
            "mobaTextEditorSourceRowName": route.source_row_name,
            "mobaTextEditorSourceRowIndex": route.source_row_index,
            "mobaTextEditorTabObject": route.editor_tab_object,
            "mobaTextEditorObject": route.editor_object,
            "mobaTextEditorSaveActionObject": route.save_action_object,
            "mobaTextEditorDiffActionObject": route.diff_action_object,
            "mobaTextEditorOpenSignal": route.open_signal,
            "mobaTextEditorSaveSignal": route.save_signal,
            "mobaTextEditorDiffSignal": route.diff_signal,
            "mobaTextEditorOpenCommand": list(route.open_command),
            "mobaTextEditorOpenBatchCommands": list(route.open_batch_commands),
            "mobaTextEditorSaveCommand": list(route.save_command),
            "mobaTextEditorSaveBatchCommands": list(route.save_batch_commands),
            "mobaTextEditorConflictPolicy": route.conflict_policy,
            "mobaTextEditorCapturedOpen": triggered,
            "mobaTextEditorStatus": status,
            "mobaTextEditorDirty": False,
            "mobaTextEditorRenderSource": route.render_source,
        }
        for key, value in properties.items():
            widget.setProperty(key, value)

    def build_text_editor_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setObjectName("mobaTextEditorToolbar")
        self.apply_connected_text_editor_route_properties(toolbar)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 4, 0, 2)
        layout.setSpacing(4)
        self.text_editor_save_button = self.text_editor_action_button(
            "save",
            "SP_DialogSaveButton",
            "mobaTextEditorSaveAction",
            self.handle_moba_text_editor_save,
        )
        self.text_editor_diff_button = self.text_editor_action_button(
            "diff",
            "SP_FileDialogDetailedView",
            "mobaTextEditorDiffAction",
            self.handle_moba_text_editor_diff,
        )
        layout.addWidget(self.text_editor_save_button)
        layout.addWidget(self.text_editor_diff_button)
        layout.addStretch(1)
        close_button = self.text_editor_action_button(
            "close",
            "SP_DialogCancelButton",
            "mobaTextEditorCloseAction",
            self.hide_moba_text_editor,
        )
        close_button.setToolTip("Close the inline editor")
        self.text_editor_close_button = close_button
        layout.addWidget(close_button)
        return toolbar

    def build_text_editor(self) -> QPlainTextEdit:
        route = moba_connected_text_editor_route(self.state)
        editor = QPlainTextEdit()
        editor.setObjectName(route.editor_object)
        self.apply_connected_text_editor_route_properties(editor)
        editor.setPlainText("")
        editor.setPlaceholderText(
            "Remote content is not loaded. Use Download to retrieve the file first."
        )
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        editor.setFixedHeight(116)
        editor.setReadOnly(True)
        editor.setProperty("mobaTextEditorContentLoaded", False)
        editor.setProperty("mobaTextEditorSyntheticPreviewSuppressed", True)
        editor.textChanged.connect(self.handle_moba_text_editor_changed)
        self.text_editor_highlighter = MobaTextEditorHighlighter(editor.document(), route.syntax)
        self.text_editor_save_button.setEnabled(False)
        self.text_editor_diff_button.setEnabled(False)
        return editor

    def text_editor_action_button(self, action_key: str, icon_name: str, object_name: str, handler) -> QToolButton:
        route = moba_connected_text_editor_route(self.state)
        button = QToolButton()
        button.setObjectName(object_name)
        button.setProperty("mobaTextEditorActionKey", action_key)
        button.setProperty("mobaTextEditorActionObject", object_name)
        button.setProperty("mobaTextEditorRemotePath", route.remote_path)
        button.setProperty("mobaTextEditorRenderSource", route.render_source)
        button.setIcon(self._connected_services.widget_style(self).standardIcon(self.standard_icon(icon_name)))
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(QSize(24, 22))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.clicked.connect(handler)
        return button

    def text_editor_route_widgets(self) -> tuple[QWidget, ...]:
        return tuple(
            widget
            for widget in (
                self,
                getattr(self, "browser", None),
                getattr(self, "file_table", None),
                getattr(self, "text_editor_toolbar", None),
                getattr(self, "text_editor", None),
                getattr(self, "text_editor_save_button", None),
                getattr(self, "text_editor_diff_button", None),
            )
            if widget is not None
        )

    def update_text_editor_state_from_plan(
        self,
        plan: MobaTextEditorTabPlan,
        *,
        source_row_name: str,
        source_row_index: int,
        remote_sha256: str = "",
    ) -> None:
        current = self.state.text_editor
        self.state = replace(
            self.state,
            text_editor=replace(
                current,
                schema=plan.schema,
                profile_name=plan.profile_name,
                remote_path=plan.remote_path,
                local_path=plan.local_path,
                syntax=plan.syntax,
                encoding=plan.encoding,
                remote_sha256=remote_sha256,
                opened_from_sftp_browser=plan.opened_from_sftp_browser,
                source_row_name=source_row_name,
                source_row_index=source_row_index,
                open_command=tuple(plan.download_plan.command),
                open_batch_commands=tuple(plan.download_plan.batch_commands),
                save_command=tuple(plan.save_plan.command),
                save_batch_commands=tuple(plan.save_plan.batch_commands),
                conflict_policy=plan.conflict_policy,
                preview_text="",
                render_source="connected-sftp-browser-text-editor",
            ),
        )
        self.text_editor_highlighter.set_syntax(plan.syntax)

    def set_text_editor_runtime_state(
        self,
        *,
        status: str,
        dirty: bool | None = None,
        content_loaded: bool | None = None,
        remote_sha256: str | None = None,
        operation: str | None = None,
    ) -> None:
        editor = getattr(self, "text_editor", None)
        if editor is None:
            return
        effective_dirty = (
            bool(editor.property("mobaTextEditorDirty"))
            if dirty is None
            else bool(dirty)
        )
        effective_loaded = (
            bool(editor.property("mobaTextEditorContentLoaded"))
            if content_loaded is None
            else bool(content_loaded)
        )
        for widget in self.text_editor_route_widgets():
            widget.setProperty("mobaTextEditorStatus", status)
            widget.setProperty("mobaTextEditorDirty", effective_dirty)
            widget.setProperty("mobaTextEditorContentLoaded", effective_loaded)
            if remote_sha256 is not None:
                widget.setProperty("mobaTextEditorRemoteSha256", remote_sha256)
            if operation is not None:
                widget.setProperty("mobaTextEditorOperation", operation)
        operation_is_locked = operation == "upload"
        editor.setReadOnly(not effective_loaded or operation_is_locked)
        save_button = getattr(self, "text_editor_save_button", None)
        if save_button is not None:
            save_button.setEnabled(effective_loaded and effective_dirty)
            save_button.setProperty("mobaTextEditorDirty", effective_dirty)
        diff_button = getattr(self, "text_editor_diff_button", None)
        if diff_button is not None:
            diff_button.setEnabled(effective_loaded)
            diff_button.setProperty("mobaTextEditorDirty", effective_dirty)

    def handle_moba_text_editor_open_from_item(self, item: QTreeWidgetItem, _column: int) -> None:
        remote_path = self.text_editor_remote_path_for_item(item)
        if not remote_path:
            return
        editor = getattr(self, "text_editor", None)
        if editor is None:
            return
        if (
            bool(editor.property("mobaTextEditorContentLoaded"))
            and bool(editor.property("mobaTextEditorDirty"))
        ):
            current_path = self.text_editor_remote_path or "the current document"
            generation = self.text_editor_generation
            choice = self._connected_services.literal_message_box(
                self,
                QMessageBox.Icon.Warning,
                "Unsaved editor changes",
                (
                    f"Discard unsaved changes to {current_path} and open "
                    f"{remote_path}?"
                ),
                buttons=(
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ),
                default_button=QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                self.show_sftp_status("Opening the file was cancelled; unsaved changes were kept")
                return
            if self.runtime_shutting_down or self.text_editor_generation != generation:
                return
        profile = self.profile_for_sftp_action()
        if profile is None:
            self.show_sftp_status(
                "Text editor unavailable: connected profile was not found"
            )
            return
        try:
            plan = build_moba_text_editor_tab_plan(profile, remote_path)
            prepare_managed_edit_cache(plan.local_path)
        except (OSError, ValueError) as exc:
            self.show_sftp_status(f"Text editor unavailable: {exc}")
            return
        self.cancel_text_editor_sftp_operation()
        self.text_editor_tab_plan = plan
        self.text_editor_remote_path = plan.remote_path
        self.text_editor_local_path = plan.local_path
        self.text_editor_probe_path = ""
        self.text_editor_baseline_text = ""
        self.text_editor_original_remote_sha256 = ""
        self.text_editor_cache_sha256 = ""
        self.text_editor_approved_remote_sha256 = ""
        self.update_text_editor_state_from_plan(
            plan,
            source_row_name=item.text(0),
            source_row_index=int(item.data(0, SFTP_ROW_INDEX_ROLE) or -1),
        )
        previous = editor.blockSignals(True)
        try:
            editor.clear()
        finally:
            editor.blockSignals(previous)
        save_button = getattr(self, "text_editor_save_button", None)
        diff_button = getattr(self, "text_editor_diff_button", None)
        toolbar = getattr(self, "text_editor_toolbar", None)
        widgets = [
            self,
            getattr(self, "browser", None),
            getattr(self, "file_table", None),
            editor,
            save_button,
            diff_button,
            toolbar,
        ]
        for widget in widgets:
            if widget is None:
                continue
            self.apply_connected_text_editor_route_properties(widget, triggered=True, status="opened")
            widget.setProperty("mobaTextEditorRemotePath", plan.remote_path)
            widget.setProperty("mobaTextEditorLocalPath", plan.local_path)
            widget.setProperty("mobaTextEditorCapturedRowName", item.text(0))
            widget.setProperty("mobaTextEditorCapturedOpenSignal", "itemDoubleClicked")
            widget.setProperty("mobaTextEditorDirty", False)
            widget.setProperty("mobaTextEditorContentLoaded", False)
            widget.setProperty("mobaTextEditorOnDemand", True)
        editor.setPlaceholderText(
            f"Downloading {plan.remote_path}..."
        )
        editor.setReadOnly(True)
        if toolbar is not None:
            toolbar.setVisible(True)
        editor.setVisible(True)
        self.setProperty("mobaTextEditorOnDemandVisible", True)
        self.set_text_editor_runtime_state(
            status="downloading",
            dirty=False,
            content_loaded=False,
            operation="open",
        )
        if not self.ensure_background_authentication_for_request():
            self.set_text_editor_runtime_state(
                status="auth-required",
                dirty=False,
                content_loaded=False,
                operation="open",
            )
            editor.setPlaceholderText(
                f"Authentication required to download {plan.remote_path}."
            )
            return
        self.show_sftp_status(f"Downloading {plan.remote_path} for editing")
        self.start_text_editor_sftp_operation("open", plan.download_plan)

    def hide_moba_text_editor(self, *_args) -> None:
        self.cancel_text_editor_sftp_operation()
        toolbar = getattr(self, "text_editor_toolbar", None)
        editor = getattr(self, "text_editor", None)
        if toolbar is not None:
            toolbar.setVisible(False)
        if editor is not None:
            editor.setVisible(False)
        self.setProperty("mobaTextEditorOnDemandVisible", False)

    def handle_moba_text_editor_changed(self) -> None:
        editor = getattr(self, "text_editor", None)
        if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
            return
        self.set_text_editor_runtime_state(
            status="modified",
            dirty=True,
            content_loaded=True,
            operation="idle",
        )

    def handle_moba_text_editor_save(self) -> None:
        editor = getattr(self, "text_editor", None)
        if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
            self.show_sftp_status("Text editor save unavailable: remote content is not loaded")
            return
        if not bool(editor.property("mobaTextEditorDirty")):
            self.show_sftp_status("Text editor has no unsaved changes")
            return
        if self.text_editor_active_generation or self.text_editor_review_in_progress:
            self.show_sftp_status("Text editor is still transferring")
            return
        profile = self.profile_for_sftp_action()
        if profile is None:
            self.show_sftp_status("Text editor save unavailable: connected profile was not found")
            return
        if not self.ensure_background_authentication_for_request():
            return
        self.text_editor_approved_remote_sha256 = ""
        self.request_text_editor_remote_check(profile)

    def request_text_editor_remote_check(self, profile: Profile) -> None:
        local_path = Path(self.text_editor_local_path)
        probe_path = local_path.with_name(f"{local_path.name}.remote-check")
        try:
            probe_plan = build_sftp_get_plan(
                profile,
                self.text_editor_remote_path,
                local_path=probe_path,
                allow_overwrite=True,
            )
        except ValueError as exc:
            self.show_sftp_status(f"Text editor save unavailable: {exc}")
            return
        self.text_editor_probe_path = str(probe_path)
        self.set_text_editor_runtime_state(
            status="checking-remote",
            dirty=True,
            content_loaded=True,
            operation="save-check",
        )
        self.show_sftp_status(
            f"Checking {self.text_editor_remote_path} for remote changes"
        )
        self.start_text_editor_sftp_operation("save-check", probe_plan)

    def current_text_editor_text(self) -> str:
        document = self.text_editor.document()
        assert document is not None  # QPlainTextEdit always owns a document.
        return _restore_document_format(self.text_editor_baseline_text, document.toRawText())

    def handle_moba_text_editor_diff(self) -> None:
        editor = getattr(self, "text_editor", None)
        if editor is None or not bool(editor.property("mobaTextEditorContentLoaded")):
            self.show_sftp_status("Text editor diff unavailable: remote content is not loaded")
            return
        diff_lines = unified_text_diff(
            self.text_editor_baseline_text, self.current_text_editor_text(),
            self.text_editor_remote_path, f"{self.text_editor_remote_path} (editor)",
        )
        diff_text = "".join(diff_lines)
        self.capture_moba_text_editor_action("diff", status="diff-ready")
        for widget in self.text_editor_route_widgets():
            widget.setProperty("mobaTextEditorDiffText", diff_text)
            widget.setProperty("mobaTextEditorDiffEqual", not bool(diff_text))
            widget.setProperty(
                "mobaTextEditorDiffHunkCount",
                sum(1 for line in diff_lines if line.startswith("@@")),
            )
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Remote text diff")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(
            "No changes from the downloaded remote baseline."
            if not diff_text
            else "Local editor changes compared with the downloaded remote baseline:"
        )
        box.setDetailedText(diff_text or "No changes")
        box.exec()

    def capture_moba_text_editor_action(self, action: str, *, status: str) -> None:
        editor = getattr(self, "text_editor", None)
        route = moba_connected_text_editor_route(self.state)
        line_count = len(editor.toPlainText().splitlines()) if editor is not None else 0
        dirty = bool(editor is not None and editor.property("mobaTextEditorDirty"))
        content_loaded = bool(
            editor is not None
            and editor.property("mobaTextEditorContentLoaded")
        )
        for widget in self.text_editor_route_widgets():
            self.apply_connected_text_editor_route_properties(widget, triggered=True, status=status)
            widget.setProperty("mobaTextEditorCapturedAction", action)
            widget.setProperty("mobaTextEditorCapturedLineCount", line_count)
            widget.setProperty("mobaTextEditorCapturedSaveBatchCommands", list(route.save_batch_commands))
            widget.setProperty("mobaTextEditorCapturedConflictPolicy", route.conflict_policy)
            widget.setProperty("mobaTextEditorDirty", dirty)
            widget.setProperty("mobaTextEditorContentLoaded", content_loaded)
            if action == "save":
                widget.setProperty("mobaTextEditorCapturedSave", True)
                widget.setProperty("mobaTextEditorDirty", False)
            elif action == "diff":
                widget.setProperty("mobaTextEditorCapturedDiff", True)

    def text_editor_remote_path_for_item(self, item: QTreeWidgetItem) -> str:
        kind = str(item.data(0, SFTP_ROW_KIND_ROLE) or "")
        name = item.text(0).strip()
        if kind != "file" or not name:
            return ""
        base = str(
            item.data(0, SFTP_ROW_SOURCE_PATH_ROLE)
            or self.active_remote_path
        ).rstrip("/")
        if not base:
            base = "/"
        return f"/{name}" if base == "/" else f"{base}/{name}"

    def text_editor_preview_for_remote_path(self, remote_path: str) -> str:
        del remote_path
        return ""

    def start_text_editor_sftp_operation(
        self,
        operation: str,
        plan: SftpBatchPlan,
    ) -> bool:
        """Run one editor transfer without blocking the Qt event loop."""

        if self.runtime_shutting_down:
            return False
        process = self.text_editor_process
        if process.state() != QProcess.ProcessState.NotRunning:
            self.text_editor_generation += 1
            self.text_editor_active_generation = 0
            self.text_editor_pending_sftp = (
                operation,
                plan,
                self.text_editor_remote_path,
                self.text_editor_local_path,
            )
            process.kill()
            self.show_sftp_status("Text editor transfer queued")
            return True
        self.text_editor_generation += 1
        request_generation = self.text_editor_generation
        self.text_editor_active_generation = request_generation
        self.text_editor_operation = operation
        self.text_editor_sftp_plan = plan
        self.text_editor_output_buffer.clear()
        self._background_auth_prompt_buffers["text-editor"].clear()
        self._background_auth_prompt_complete["text-editor"] = False
        runtime_command = openssh_command_with_overrides(
            list(plan.command),
            self.background_ssh_overrides(),
        )
        runtime_command = openssh_command_without_windows_connection_sharing(
            runtime_command
        )
        control_path = self.shared_ssh_control_path()
        if control_path:
            runtime_command = ssh_command_with_control_path(
                runtime_command,
                control_path,
                master=False,
            )
        try:
            process.setProgram(runtime_command[0])
            process.setArguments(runtime_command[1:])
            process.start()
        except (OSError, RuntimeError) as exc:
            self.text_editor_active_generation = 0
            self.set_text_editor_runtime_state(
                status="error",
                operation="idle",
            )
            self.show_sftp_status(f"Text editor transfer could not start: {exc}")
            if operation == "save-check":
                self.clear_text_editor_probe_file()
            self.schedule_pending_text_editor_sftp()
            return False
        self.text_editor_timeout.start(30_000)
        return True

    def clear_text_editor_probe_file(self) -> None:
        probe_path = self.text_editor_probe_path
        self.text_editor_probe_path = ""
        if not probe_path:
            return
        try:
            Path(probe_path).unlink(missing_ok=True)
        except OSError:
            pass

    def cancel_text_editor_sftp_operation(self) -> None:
        self.text_editor_generation += 1
        self.text_editor_active_generation = 0
        self.text_editor_pending_sftp = None
        self.text_editor_approved_remote_sha256 = ""
        self.text_editor_timeout.stop()
        self.text_editor_auth_probe_timer.stop()
        self.clear_text_editor_probe_file()
        if self.text_editor_process.state() != QProcess.ProcessState.NotRunning:
            self.text_editor_process.kill()

    def text_editor_sftp_request_is_current(self) -> bool:
        return bool(
            not self.runtime_shutting_down
            and self.text_editor_active_generation != 0
            and self.text_editor_active_generation == self.text_editor_generation
        )

    def write_text_editor_sftp_batch(self, *, force: bool = False) -> None:
        if not self.text_editor_sftp_request_is_current():
            return
        if self._background_password and not force:
            if not self.text_editor_auth_probe_timer.isActive():
                self.text_editor_auth_probe_timer.start()
            return
        self.text_editor_auth_probe_timer.stop()
        plan = self.text_editor_sftp_plan
        if plan is None:
            return
        accepted = self._write_connected_sftp_batch(self.text_editor_process, plan, "text-editor")
        if accepted < 0:
            self.show_sftp_status(
                "Text editor transfer failed: batch input was not accepted"
            )

    def read_text_editor_sftp_output(self) -> None:
        payload = bytes(self.text_editor_process.readAllStandardOutput())
        self._submit_background_password_if_prompt("text-editor", payload)
        self.text_editor_output_buffer.extend(payload)

    def handle_text_editor_sftp_error(self, error) -> None:
        self.text_editor_timeout.stop()
        self.text_editor_auth_probe_timer.stop()
        operation = self.text_editor_operation
        request_is_current = self.text_editor_sftp_request_is_current()
        self.text_editor_active_generation = 0
        if operation == "save-check":
            self.clear_text_editor_probe_file()
        if request_is_current:
            detail = getattr(error, "name", str(error))
            self.set_text_editor_runtime_state(
                status="error",
                operation="idle",
            )
            self.show_sftp_status(f"Text editor transfer error: {detail}")
        self.schedule_pending_text_editor_sftp()

    def cancel_text_editor_sftp_timeout(self) -> None:
        if self.text_editor_process.state() == QProcess.ProcessState.NotRunning:
            return
        request_is_current = self.text_editor_sftp_request_is_current()
        operation = self.text_editor_operation
        self.text_editor_active_generation = 0
        self.text_editor_auth_probe_timer.stop()
        if operation == "save-check":
            self.clear_text_editor_probe_file()
        self.text_editor_process.kill()
        if request_is_current:
            self.set_text_editor_runtime_state(
                status="error",
                operation="idle",
            )
            self.show_sftp_status("Text editor transfer timed out after 30 seconds")

    def handle_text_editor_sftp_finished(
        self,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        self.text_editor_timeout.stop()
        self.text_editor_auth_probe_timer.stop()
        request_is_current = self.text_editor_sftp_request_is_current()
        self.read_text_editor_sftp_output()
        output = self.text_editor_output_buffer.decode(errors="replace")
        operation = self.text_editor_operation
        self.text_editor_active_generation = 0
        if not request_is_current:
            self.schedule_pending_text_editor_sftp()
            return
        if exit_code != 0:
            if operation == "save-check":
                self.clear_text_editor_probe_file()
            detail = next(
                (line.strip() for line in reversed(output.splitlines()) if line.strip()),
                f"exit {exit_code}",
            )
            self.set_text_editor_runtime_state(
                status="error",
                operation="idle",
            )
            self.show_sftp_status(
                f"Text editor {operation} failed: {detail[:160]}"
            )
            self.schedule_background_auth_retry()
            self.schedule_pending_text_editor_sftp()
            return
        try:
            if operation == "open":
                self.finish_text_editor_open()
            elif operation == "save-check":
                self.finish_text_editor_save_check()
            elif operation == "upload":
                self.finish_text_editor_upload()
            else:
                self.show_sftp_status(f"Text editor completed unknown operation: {operation}")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            self.set_text_editor_runtime_state(
                status="error",
                operation="idle",
            )
            self.show_sftp_status(f"Text editor transfer result was invalid: {exc}")
        self.schedule_pending_text_editor_sftp()

    def schedule_pending_text_editor_sftp(self) -> None:
        pending = self.text_editor_pending_sftp
        self.text_editor_pending_sftp = None
        if pending is None or self.runtime_shutting_down:
            return
        operation, plan, remote_path, local_path = pending

        def start_pending() -> None:
            if self.runtime_shutting_down:
                return
            self.text_editor_remote_path = remote_path
            self.text_editor_local_path = local_path
            self.start_text_editor_sftp_operation(operation, plan)

        QTimer.singleShot(0, start_pending)

    @staticmethod
    def text_editor_file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def finish_text_editor_open(self) -> None:
        path = Path(self.text_editor_local_path)
        encoding = self.state.text_editor.encoding or "utf-8"
        payload = path.read_bytes()
        if b"\x00" in payload:
            raise ValueError("remote file appears to be binary; text editing was refused")
        text = payload.decode(encoding)
        digest = self.text_editor_file_sha256(path)
        editor = self.text_editor
        previous = editor.blockSignals(True)
        try:
            editor.setPlainText(text)
        finally:
            editor.blockSignals(previous)
        editor.setPlaceholderText("")
        self.text_editor_baseline_text = text
        self.text_editor_original_remote_sha256 = digest
        self.text_editor_cache_sha256 = digest
        route = self.state.text_editor
        self.state = replace(
            self.state,
            text_editor=replace(route, remote_sha256=digest),
        )
        for widget in self.text_editor_route_widgets():
            self.apply_connected_text_editor_route_properties(
                widget,
                triggered=True,
                status="loaded",
            )
            widget.setProperty("mobaTextEditorCapturedOpenSignal", "itemDoubleClicked")
        self.set_text_editor_runtime_state(
            status="loaded",
            dirty=False,
            content_loaded=True,
            remote_sha256=digest,
            operation="idle",
        )
        if self.file_table.hasFocus():
            editor.setFocus(Qt.FocusReason.OtherFocusReason)
        self.show_sftp_status(
            f"Loaded {self.text_editor_remote_path} for editing"
        )

    def finish_text_editor_save_check(self) -> None:
        probe = Path(self.text_editor_probe_path)
        try:
            current_digest = self.text_editor_file_sha256(probe)
        finally:
            self.clear_text_editor_probe_file()
        if current_digest not in (self.text_editor_original_remote_sha256, self.text_editor_approved_remote_sha256):
            generation = self.text_editor_generation
            self.text_editor_review_in_progress = True
            try:
                choice = self._connected_services.literal_message_box(
                    self,
                    QMessageBox.Icon.Warning,
                    "Remote file changed",
                    (
                        f"{self.text_editor_remote_path} changed after it was opened. "
                        "Overwrite the reviewed remote version?"
                    ),
                    buttons=(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No),
                    default_button=QMessageBox.StandardButton.No,
                )
            finally:
                self.text_editor_review_in_progress = False
            if self.runtime_shutting_down or generation != self.text_editor_generation:
                return
            if choice != QMessageBox.StandardButton.Yes:
                self.set_text_editor_runtime_state(
                    status="conflict",
                    dirty=True,
                    content_loaded=True,
                    operation="idle",
                )
                self.show_sftp_status("Text editor save cancelled after remote conflict")
                return
            profile = self.profile_for_sftp_action()
            if profile is None:
                self.set_text_editor_runtime_state(status="conflict", operation="idle")
                self.show_sftp_status("Text editor save unavailable: connected profile changed during review")
                return
            self.text_editor_approved_remote_sha256 = current_digest
            self.request_text_editor_remote_check(profile)
            return
        try:
            result = write_text_document(
                self.text_editor_local_path,
                self.current_text_editor_text(),
                expected_sha256=self.text_editor_cache_sha256,
                backup=True,
                encoding=self.state.text_editor.encoding or "utf-8",
            )
        except (OSError, ValueError) as exc:
            self.set_text_editor_runtime_state(
                status="error",
                dirty=True,
                content_loaded=True,
                operation="idle",
            )
            self.show_sftp_status(f"Text editor cache save failed: {exc}")
            return
        self.text_editor_cache_sha256 = result.new_sha256
        tab_plan = self.text_editor_tab_plan
        if tab_plan is None:
            self.show_sftp_status("Text editor upload unavailable: editor plan is missing")
            return
        self.set_text_editor_runtime_state(
            status="uploading",
            dirty=True,
            content_loaded=True,
            operation="upload",
        )
        self.show_sftp_status(
            f"Uploading edited {self.text_editor_remote_path}"
        )
        self.start_text_editor_sftp_operation("upload", tab_plan.save_plan)

    def finish_text_editor_upload(self) -> None:
        digest = self.text_editor_file_sha256(Path(self.text_editor_local_path))
        self.text_editor_baseline_text = self.current_text_editor_text()
        self.text_editor_original_remote_sha256 = digest
        self.text_editor_cache_sha256 = digest
        route = self.state.text_editor
        self.state = replace(
            self.state,
            text_editor=replace(route, remote_sha256=digest),
        )
        self.capture_moba_text_editor_action("save", status="saved")
        self.set_text_editor_runtime_state(
            status="saved",
            dirty=False,
            content_loaded=True,
            remote_sha256=digest,
            operation="idle",
        )
        self.show_sftp_status(
            f"Saved {self.text_editor_remote_path} to the remote host"
        )
