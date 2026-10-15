from __future__ import annotations

import codecs
import re
import time
from collections.abc import Callable
from dataclasses import replace

from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QProcess, QProcessEnvironment, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QClipboard,
    QColor,
    QContextMenuEvent,
    QDesktopServices,
    QFont,
    QKeySequence,
    QPainter,
    QPalette,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .enterprise_policy import assert_profile_launch_allowed
from .gui_lifecycle import ProcessStopPolicy, ProcessStopResult, stop_process
from .gui_processes import _terminal_process_backend
from .gui_values import _required_gui_value, _safe_tooltip_html
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
from .models import Profile
from .terminal import (
    TerminalPanePlan,
    harden_terminal_pane_plan_for_native_windows,
    normalise_local_shell_input,
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    ssh_command_with_control_path,
    ssh_control_path_for_profile,
)
from .terminal_emulation import TERMINAL_EMULATOR_BACKEND, AnsiTerminalTranscript, AnsiTextStyle
from .terminal_highlighting import (
    default_terminal_syntax_rules,
    highlight_terminal_text,
    terminal_syntax_rule_keys,
)
from .terminal_output import _ByteChunkQueue


def _application_clipboard() -> QClipboard:
    return _required_gui_value(QApplication.clipboard(), "application clipboard")


def _application_instance() -> QApplication:
    instance = QApplication.instance()
    if not isinstance(instance, QApplication):
        raise RuntimeError("required GUI value is unavailable: Qt application")
    return instance


def _widget_style(widget: QWidget) -> QStyle:
    return _required_gui_value(widget.style(), f"style for {type(widget).__name__}")


class TerminalTextEdit(QTextEdit):
    """Read-only transcript view with a stable remote-terminal cursor overlay."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._remote_cursor_position: int | None = None
        self._remote_cursor_trailing_cells = 0
        self._remote_cursor_visible = False

    def set_remote_cursor_state(
        self,
        position: int,
        *,
        trailing_cells: int = 0,
        visible: bool,
    ) -> None:
        document = _required_gui_value(
            self.document(),
            "terminal text document",
        )
        maximum = max(0, document.characterCount() - 1)
        self._remote_cursor_position = max(0, min(maximum, int(position)))
        self._remote_cursor_trailing_cells = max(0, int(trailing_cells))
        self._remote_cursor_visible = bool(visible)
        self.setProperty("terminalRemoteCursorVisible", self._remote_cursor_visible)
        self.setProperty(
            "terminalRemoteCursorDocumentPosition",
            self._remote_cursor_position,
        )
        self.setProperty(
            "terminalRemoteCursorTrailingCells",
            self._remote_cursor_trailing_cells,
        )
        _required_gui_value(
            self.viewport(),
            "terminal text viewport",
        ).update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if bool(self.property("terminalTabPaintFrozen")):
            return
        super().paintEvent(event)
        if not self._remote_cursor_visible or self._remote_cursor_position is None:
            return
        viewport = _required_gui_value(
            self.viewport(),
            "terminal paint viewport",
        )
        document = _required_gui_value(
            self.document(),
            "terminal paint document",
        )
        cursor = QTextCursor(document)
        cursor.setPosition(
            max(
                0,
                min(document.characterCount() - 1, self._remote_cursor_position),
            )
        )
        rectangle = self.cursorRect(cursor)
        if self._remote_cursor_trailing_cells:
            cell_width = max(1, self.fontMetrics().horizontalAdvance("M"))
            rectangle.translate(
                self._remote_cursor_trailing_cells * cell_width,
                0,
            )
        if not rectangle.intersects(viewport.rect()):
            return
        color = self.palette().color(QPalette.ColorRole.Text)
        color.setAlpha(230)
        painter = QPainter(viewport)
        try:
            cursor_width = max(2, round(self.devicePixelRatioF()))
            painter.fillRect(
                rectangle.x(),
                rectangle.y() + 1,
                cursor_width,
                max(1, rectangle.height() - 2),
                color,
            )
        finally:
            painter.end()


class TerminalPane(QWidget):
    STOP_POLICY = ProcessStopPolicy()
    OUTPUT_RENDER_BATCH_BYTES = 16 * 1024
    OUTPUT_RENDER_TURN_BUDGET_BYTES = 256 * 1024
    OUTPUT_SYNC_DRAIN_BUDGET_BYTES = 64 * 1024
    OUTPUT_READ_CHUNK_BYTES = 64 * 1024
    OUTPUT_BUFFER_HIGH_WATER_BYTES = 4 * 1024 * 1024
    OUTPUT_BUFFER_LOW_WATER_BYTES = 1 * 1024 * 1024

    def __init__(
        self,
        plan: TerminalPanePlan,
        *,
        profile: Profile | None = None,
        autostart: bool = True,
        authentication_change_handler: Callable[[TerminalPane, bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("terminalPane")
        # A terminal page is a fill surface, never a size-hint-driven
        # floating child.  Explicitly keeping a zero minimum and an
        # expanding policy prevents QStackedWidget/QSplitter from
        # exposing a transient miniature page while another tab is being
        # activated or its ConPTY is negotiating a resize.
        self.setMinimumSize(0, 0)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        # Saved layouts and restored tabs can carry plans created before
        # the native-Windows OpenSSH socket guard existed. Apply the same
        # normalization at the live terminal boundary as at plan build.
        plan = harden_terminal_pane_plan_for_native_windows(plan)
        self.profile = profile
        self.ssh_control_path = ""
        if profile is not None:
            control_path = ssh_control_path_for_profile(profile)
            shared_command = ssh_command_with_control_path(
                plan.command,
                control_path,
                master=True,
            )
            if shared_command != plan.command:
                plan = replace(plan, command=shared_command)
                self.ssh_control_path = control_path
        self.plan = plan
        self.setProperty("sshControlPath", self.ssh_control_path)
        self.process, self._terminal_backend_warning = _terminal_process_backend(
            self,
            plan,
            profile,
        )
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._restart_after_stop = False
        self._rendered_terminal_text = ""
        self._rendered_terminal_revision = -1
        self._pending_terminal_transcript: str | None = None
        self._pty_initial_clear_pending = False
        self._pty_startup_probe = ""
        self._terminal_scroll_generation = 0
        self._terminal_scroll_settle_generation = 0
        self._terminal_scroll_closed = False
        self._terminal_follow_output = True
        self._terminal_scroll_programmatic = 0
        self._terminal_force_follow_output = False
        self._process_output_buffer = _ByteChunkQueue()
        self._process_output_flush_scheduled = False
        self._process_output_flush_count = 0
        self._process_output_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._process_output_decode_final_pending = False
        self._process_output_end_pending = False
        self._process_output_source_end_pending = False
        self._process_output_source_drained = True
        self._process_output_trailers: list[str] = []
        self._process_output_read_paused = False
        self._restart_when_output_drained = False
        self._pending_terminal_size: tuple[int, int] | None = None
        self.setProperty("terminalAutostart", bool(autostart))
        self.setProperty(
            "terminalOutputCoalescing",
            "normal-next-turn-alt-16ms-coalesce-256KiB-adaptive-turn-4MiB-backpressure",
        )
        self.startup_preamble = ""
        self.show_launch_command = True
        self.output_context_menu_builder: Callable[[TerminalPane], QMenu] | None = None
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self.kill_after_stop_timeout)
        self._process_output_timer = QTimer(self)
        self._process_output_timer.setSingleShot(True)
        self._process_output_timer.setInterval(16)
        self._process_output_timer.timeout.connect(self.flush_process_output)
        self._terminal_resize_timer = QTimer(self)
        self._terminal_resize_timer.setSingleShot(True)
        self._terminal_resize_timer.setInterval(40)
        self._terminal_resize_timer.timeout.connect(self.flush_terminal_resize)
        self._terminal_scroll_timer = QTimer(self)
        self._terminal_scroll_timer.setSingleShot(True)
        self._terminal_scroll_timer.timeout.connect(self.settle_terminal_scroll)

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
        self.command_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.command_preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.output = TerminalTextEdit()
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
        self.output.setCursorWidth(0)
        self.output.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.output.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        document = _required_gui_value(
            self.output.document(),
            "terminal output document",
        )
        document.setUndoRedoEnabled(False)
        # Keep a runaway command or redraw-heavy session from making
        # QTextEdit's document grow without bound.  The ANSI model
        # remains authoritative for the terminal screen and scrollback.
        document.setMaximumBlockCount(10_256)
        self.setFocusProxy(self.output)
        self.output.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.output.installEventFilter(self)
        self.output_viewport = _required_gui_value(
            self.output.viewport(),
            "terminal output viewport",
        )
        self.output_viewport.installEventFilter(self)
        terminal_scroll_bar = _required_gui_value(
            self.output.verticalScrollBar(),
            "terminal vertical scroll bar",
        )
        terminal_scroll_bar.valueChanged.connect(self._on_terminal_scroll_value_changed)
        self.terminal_emulator = AnsiTerminalTranscript()
        self.output.setProperty("terminalEmulatorBackend", TERMINAL_EMULATOR_BACKEND)
        self.output.setProperty(
            "terminalEmulatorPty",
            bool(getattr(self.process, "is_pty", False)),
        )
        self.output.setProperty(
            "terminalProcessBackend",
            "windows-conpty" if bool(getattr(self.process, "is_pty", False)) else "qt-process-pipe",
        )
        process_property = getattr(self.process, "property", lambda _name: None)
        self.output.setProperty(
            "terminalConsoleSuppressed",
            bool(process_property("terminalConsoleSuppressed")),
        )
        self.output.setProperty(
            "terminalChildWindowPolicy",
            str(process_property("terminalChildWindowPolicy") or "unspecified"),
        )
        self.output.setProperty(
            "terminalRemotePtyRequested",
            any(argument in {"-t", "-tt"} for argument in plan.command),
        )
        self.output.setProperty("terminalDirectKeyInput", True)
        self.output.setProperty("terminalQtCaretHidden", True)
        self.output.setProperty("terminalTabPaintFrozen", False)
        self.output.setProperty("terminalFollowOutput", True)
        self.output.setProperty("terminalAlternateScreenActive", False)
        self.output.setProperty("terminalAlternateScreenRedraw", False)
        self.output.setProperty("terminalBracketedPasteActive", False)
        self.output.setProperty("terminalOriginModeActive", False)
        self.output.setProperty("terminalInsertModeActive", False)
        self.output.setProperty("terminalAutoWrapActive", True)
        self.output.setProperty("terminalLastPasteWasBracketed", False)
        # Automatic mouse paste is a MobaXterm convention, not a safe
        # cross-preset terminal default. MainWindow enables both gestures
        # only while the MobaXterm preset is active.
        self._terminal_right_click_paste_enabled = False
        self._terminal_middle_click_paste_enabled = False
        # Some Windows Qt styles deliver a context-menu event after the
        # right-button press; others deliver only the press to an embedded
        # terminal viewport.  Paste on the press for the Moba fast path
        # and remember the dispatch briefly so a later context event does
        # not paste the same clipboard text twice.
        self._terminal_right_click_paste_pending = False
        self._terminal_right_click_paste_generation = 0
        # Keep the production OS clipboard while allowing native/headless
        # GUI gates to inject a deterministic clipboard provider. Windows
        # service sessions can expose QClipboard without owning a desktop
        # clipboard, which must not make terminal input tests flaky.
        self._terminal_clipboard_provider = _application_clipboard
        self.output.setProperty("terminalRightClickPasteEnabled", False)
        self.output.setProperty("terminalMiddleClickPasteEnabled", False)
        self.output.setProperty(
            "terminalContextMenuGesture",
            "Right-click",
        )
        self.output.setProperty("terminalLastPasteGesture", "")
        self.output.setProperty("terminalEmulatorResponseCount", 0)
        self.output.setProperty("terminalLastEmulatorResponse", b"")
        self.output.setProperty("terminalOutputBufferedBytes", 0)
        self.output.setProperty("terminalOutputFlushCount", 0)
        self.output.setProperty(
            "terminalOutputRenderBatchBytes",
            self.OUTPUT_RENDER_BATCH_BYTES,
        )
        self.output.setProperty(
            "terminalOutputRenderTurnBudgetBytes",
            self.OUTPUT_RENDER_TURN_BUDGET_BYTES,
        )
        self.output.setProperty(
            "terminalOutputSyncDrainBudgetBytes",
            self.OUTPUT_SYNC_DRAIN_BUDGET_BYTES,
        )
        self.output.setProperty(
            "terminalOutputBufferHighWaterBytes",
            self.OUTPUT_BUFFER_HIGH_WATER_BYTES,
        )
        self.output.setProperty(
            "terminalOutputBufferLowWaterBytes",
            self.OUTPUT_BUFFER_LOW_WATER_BYTES,
        )
        self.output.setProperty("terminalOutputReadPaused", False)
        self.output.setProperty("terminalOutputDeferredTrailerCount", 0)
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
        self.output.setProperty(
            "terminalEmulatorScrollbackLimit", self.terminal_emulator.max_scrollback_lines
        )
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
        self.output.setProperty(
            "terminalSyntaxHighlightRuleKeys", list(terminal_syntax_rule_keys(self.syntax_rules))
        )
        self.output.setProperty("terminalLinkActivation", "ctrl-click-http-https")
        self.output.setProperty("terminalLinkAllowedSchemes", ["http", "https"])
        self.output.setProperty("terminalLinkAutoOpen", False)
        self.output.setProperty("terminalUrlHighlightColor", "#54ccef")
        self.input = QLineEdit()
        self.input.setObjectName("terminalInput")
        self.input.setPlaceholderText("stdin, shell command or interactive input")
        self._secret_prompt_active = False
        self._authentication_change_handler = authentication_change_handler
        self.input.setProperty("terminalSecretInputActive", False)
        self.macro_capture_state: MobaMacroTerminalCaptureState | None = None
        self.macro_last_recording: MobaMacroRecording | None = None
        self.macro_last_injection: MobaMacroTerminalReplayInjection | None = None
        self.macro_last_event_at: float | None = None
        self.macro_replay_active = False
        self.macro_replay_cancelled = False
        self.macro_replay_sequence = 0
        self.start_button = self.terminal_button("Start", "SP_MediaPlay", "Start process")
        self.restart_button = self.terminal_button("Restart", "SP_BrowserReload", "Restart process")
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

    def set_terminal_paint_frozen(self, frozen: bool) -> None:
        """Hold the terminal viewport steady while its workspace tab settles."""

        frozen = bool(frozen)
        self.setProperty("terminalTabPaintFrozen", frozen)
        self.output.setProperty("terminalTabPaintFrozen", frozen)
        # Frame rendering owns its own short-lived repaint guard. Do not
        # let a stale alternate-screen diagnostic flag keep the terminal
        # permanently invisible after a tab switch or failed redraw.
        self.output.setUpdatesEnabled(not frozen)
        if not frozen:
            pending_transcript = self._pending_terminal_transcript
            self._pending_terminal_transcript = None
            if pending_transcript is not None:
                self.render_terminal_transcript(pending_transcript)
            # Output may have arrived while painting was suppressed. One
            # queued repaint exposes the already-rendered transcript after
            # the final tab geometry is in place without blocking the UI.
            self.output_viewport.update()
            self.output.update()

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

    def set_terminal_authentication_change_handler(
        self,
        handler: Callable[[TerminalPane, bool], None] | None,
    ) -> None:
        """Attach a host callback for interactive auth-prompt transitions."""

        self._authentication_change_handler = handler

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
        self._pending_terminal_size = (columns, rows)
        if not self._terminal_resize_timer.isActive():
            self._terminal_resize_timer.start()

    def flush_terminal_resize(self) -> None:
        pending = self._pending_terminal_size
        self._pending_terminal_size = None
        if pending is None:
            return
        resize = getattr(self.process, "setTerminalSize", None)
        if resize is not None:
            resize(*pending)

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
        header_layout = _required_gui_value(
            self.header.layout(),
            "terminal header layout",
        )
        header_layout.invalidate()
        self.header.updateGeometry()
        self.updateGeometry()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def _on_terminal_scroll_value_changed(self, value: int) -> None:
        """Remember whether the user has intentionally left the live tail."""

        if self._terminal_scroll_programmatic or bool(
            self.output.property("terminalAlternateScreenRedraw")
        ):
            return
        scroll_bar = _required_gui_value(
            self.output.verticalScrollBar(),
            "terminal vertical scroll bar",
        )
        following = int(value) >= max(0, scroll_bar.maximum() - 2)
        self._terminal_follow_output = following
        if not following:
            self._terminal_force_follow_output = False
        self.output.setProperty("terminalFollowOutput", following)

    def _set_terminal_scroll_value(self, value: int) -> None:
        """Move the scroll bar without treating the move as user input."""

        scroll_bar = _required_gui_value(
            self.output.verticalScrollBar(),
            "terminal vertical scroll bar",
        )
        self._terminal_scroll_programmatic += 1
        try:
            scroll_bar.setValue(int(value))
        finally:
            self._terminal_scroll_programmatic = max(
                0,
                self._terminal_scroll_programmatic - 1,
            )

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        terminal_targets = (self.output, self.output_viewport)
        if watched in terminal_targets and event.type() == QEvent.Type.FocusIn:
            # QApplication.focusChanged can lag behind native focus
            # delivery. Track the terminal surface at the source so a
            # subsequent workspace search always uses the pane that just
            # received focus.
            workspace = self.window()
            remember = getattr(workspace, "remember_terminal_focus", None)
            if callable(remember):
                remember(None, watched)
        if watched in terminal_targets and event.type() == QEvent.Type.MouseButtonPress:
            self.output.setFocus(Qt.FocusReason.MouseFocusReason)
            self.output.setProperty("terminalLastInputSurface", "viewport")
            if (
                event.button() == Qt.MouseButton.MiddleButton
                and self._terminal_middle_click_paste_enabled
            ):
                self.paste_middle_click_selection()
                event.accept()
                return True
            if (
                event.button() == Qt.MouseButton.RightButton
                and self._terminal_right_click_paste_enabled
                and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                # A second genuine click must never be swallowed just
                # because the first click is waiting for Qt's synthetic
                # context-menu event.
                self._cancel_right_click_paste_suppression()
                self._arm_right_click_paste_suppression()
                self.paste_to_terminal(gesture="right-click")
                event.accept()
                return True
        if watched in terminal_targets and event.type() == QEvent.Type.ContextMenu:
            # MobaXterm's fast path pastes on a plain right-click.  Keep
            # the complete context menu available through Shift+Right-click
            # (and let users switch the fast path off from that menu).
            modifiers = event.modifiers()
            if (
                self._terminal_right_click_paste_enabled
                and event.reason() == QContextMenuEvent.Reason.Mouse
                and not modifiers & Qt.KeyboardModifier.ShiftModifier
            ):
                if self._terminal_right_click_paste_pending:
                    self._cancel_right_click_paste_suppression()
                    event.accept()
                    return True
                self.paste_to_terminal(gesture="right-click")
                event.accept()
                return True
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
            # The terminal event filter normally owns key delivery so
            # that readline, Vim, and ncurses receive exact TTY bytes.
            # Ctrl+Tab is the workspace traversal gesture, however; if
            # it reaches terminal_key_payload it becomes a remote Tab
            # byte before the window-level QShortcut can activate.
            if (
                event.key() == Qt.Key.Key_Tab
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and not event.modifiers()
                & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
            ):
                workspace = self.window()
                activate = getattr(
                    workspace,
                    "activate_previous_tab"
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    else "activate_next_tab",
                    None,
                )
                if callable(activate):
                    activate()
                    event.accept()
                    return True
            selection = self.output.textCursor().selectedText()
            if self.is_terminal_selection_navigation(event):
                # A terminal still needs a usable local scrollback selection.
                # Let QTextEdit extend the cursor selection instead of sending
                # Shift+Arrow/Home/End/Page keys to the remote PTY.
                return super().eventFilter(watched, event)
            if (
                event.matches(QKeySequence.StandardKey.Copy) and selection
            ) or self.is_terminal_copy_shortcut(event):
                self.copy_terminal_selection()
                return True
            if event.matches(QKeySequence.StandardKey.Paste) or self.is_terminal_paste_shortcut(
                event
            ):
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

    def _arm_right_click_paste_suppression(self) -> None:
        """Avoid duplicate Moba paste when Qt also emits a context event."""

        self._terminal_right_click_paste_generation += 1
        generation = self._terminal_right_click_paste_generation
        self._terminal_right_click_paste_pending = True
        QTimer.singleShot(
            500,
            lambda generation=generation: self._clear_right_click_paste_suppression(generation),
        )

    def _cancel_right_click_paste_suppression(self) -> None:
        self._terminal_right_click_paste_generation += 1
        self._terminal_right_click_paste_pending = False

    def _clear_right_click_paste_suppression(self, generation: int) -> None:
        if generation == self._terminal_right_click_paste_generation:
            self._terminal_right_click_paste_pending = False

    @staticmethod
    def is_terminal_selection_navigation(event) -> bool:
        """Return whether *event* extends the local scrollback selection."""

        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
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
            return b"\x1b" + function_payload if alt else function_payload
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
        application_cursor = self.terminal_emulator.application_cursor_keys_active
        cursor_prefix = b"\x1bO" if application_cursor else b"\x1b["
        special = {
            Qt.Key.Key_Return: (b"\r" if bool(getattr(self.process, "is_pty", False)) else b"\n"),
            Qt.Key.Key_Enter: (b"\r" if bool(getattr(self.process, "is_pty", False)) else b"\n"),
            Qt.Key.Key_Backspace: b"\x7f",
            Qt.Key.Key_Tab: b"\t",
            Qt.Key.Key_Escape: b"\x1b",
            Qt.Key.Key_Up: cursor_prefix + b"A",
            Qt.Key.Key_Down: cursor_prefix + b"B",
            Qt.Key.Key_Right: cursor_prefix + b"C",
            Qt.Key.Key_Left: cursor_prefix + b"D",
            Qt.Key.Key_Home: cursor_prefix + b"H",
            Qt.Key.Key_End: cursor_prefix + b"F",
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
        submitted_line = b"\r" in payload or b"\n" in payload
        follow_live_tail = (
            submitted_line
            and not self.terminal_emulator.alternate_screen_active
            and int(accepted) > 0
        )
        if follow_live_tail:
            # A submitted shell line starts a new prompt/output cycle.
            # Mark this before the asynchronous response arrives so a
            # delayed document/layout event cannot restore old scrollback.
            self._terminal_follow_output = True
            self._terminal_force_follow_output = True
            self.output.setProperty("terminalFollowOutput", True)
            self.output.setProperty("terminalInputRequestedLiveTail", True)
            self.scroll_terminal_to_end()
        else:
            self.output.setProperty("terminalInputRequestedLiveTail", False)
        if int(accepted) < len(payload):
            self.set_status("input error", "error")
            self.append_text(
                "\n[stdin error: terminal process did not accept the complete input]\n"
            )

    def paste_to_terminal(self, *, gesture: str = "action") -> None:
        self.paste_text_to_terminal(
            self._terminal_clipboard_provider().text(),
            gesture=gesture,
        )

    def paste_middle_click_selection(self) -> None:
        """Paste the X11 selection when available, otherwise the clipboard."""

        clipboard = self._terminal_clipboard_provider()
        text = ""
        if clipboard.supportsSelection():
            text = clipboard.text(QClipboard.Mode.Selection)
        if not text:
            text = clipboard.text()
        self.paste_text_to_terminal(text, gesture="middle-click")

    def paste_text_to_terminal(self, text: str, *, gesture: str) -> None:
        if not text:
            return
        self.output.setProperty("terminalLastPasteGesture", gesture)
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

    def set_terminal_right_click_paste_enabled(self, enabled: bool) -> None:
        self._cancel_right_click_paste_suppression()
        self._terminal_right_click_paste_enabled = bool(enabled)
        self.output.setProperty(
            "terminalRightClickPasteEnabled",
            self._terminal_right_click_paste_enabled,
        )
        self.output.setProperty(
            "terminalContextMenuGesture",
            "Shift+Right-click" if self._terminal_right_click_paste_enabled else "Right-click",
        )

    def set_terminal_middle_click_paste_enabled(self, enabled: bool) -> None:
        self._terminal_middle_click_paste_enabled = bool(enabled)
        self.output.setProperty(
            "terminalMiddleClickPasteEnabled",
            self._terminal_middle_click_paste_enabled,
        )

    def copy_terminal_selection(self) -> None:
        selection = self.output.textCursor().selectedText().replace("\u2029", "\n")
        if selection:
            self.output.setProperty("terminalLastCopiedText", selection)
            clipboard = self._terminal_clipboard_provider()
            clipboard.setText(selection)
            # Another Windows process can briefly hold the native
            # clipboard. Qt retries reads in that case, but a failed first
            # OleSetClipboard call otherwise drops this copy operation.
            # Use the readback as one bounded retry point without sleeping
            # or blocking the GUI event loop.
            retried = clipboard.text() != selection
            if retried:
                clipboard.setText(selection)
            self.output.setProperty("terminalClipboardWriteRetried", retried)

    def build_output_context_menu(self) -> QMenu:
        if callable(self.output_context_menu_builder):
            menu = self.output_context_menu_builder(self)
            self.add_terminal_mouse_paste_menu(menu)
            return menu
        menu = QMenu(self.output)
        selection = bool(self.output.textCursor().selectedText())
        clipboard_text = bool(self._terminal_clipboard_provider().text())
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
        self.add_terminal_mouse_paste_menu(menu)
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

    def add_terminal_mouse_paste_menu(self, menu: QMenu) -> None:
        if bool(menu.property("terminalMousePasteMenuAdded")):
            return
        menu.setProperty("terminalMousePasteMenuAdded", True)
        mouse_menu = _required_gui_value(
            menu.addMenu("Mouse paste behavior (this terminal)"),
            "terminal mouse paste menu",
        )
        mouse_menu.setObjectName("terminalMousePasteMenu")
        right_click_action = _required_gui_value(
            mouse_menu.addAction("Right-click pastes automatically"),
            "terminal right-click paste action",
        )
        right_click_action.setCheckable(True)
        right_click_action.setChecked(self._terminal_right_click_paste_enabled)
        right_click_action.toggled.connect(self.set_terminal_right_click_paste_enabled)
        middle_click_action = _required_gui_value(
            mouse_menu.addAction("Middle-click pastes"),
            "terminal middle-click paste action",
        )
        middle_click_action.setCheckable(True)
        middle_click_action.setChecked(self._terminal_middle_click_paste_enabled)
        middle_click_action.toggled.connect(self.set_terminal_middle_click_paste_enabled)
        mouse_menu.addSeparator()
        context_hint = _required_gui_value(
            mouse_menu.addAction(
                "Shift+Right-click opens this menu"
                if self._terminal_right_click_paste_enabled
                else "Right-click opens this menu"
            ),
            "terminal context-menu gesture hint",
        )
        context_hint.setEnabled(False)
        right_click_action.toggled.connect(
            lambda enabled, hint=context_hint: hint.setText(
                "Shift+Right-click opens this menu" if enabled else "Right-click opens this menu"
            )
        )

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
        if self.process_output_pending():
            # A finished process can still have a bounded output tail.  Do
            # not let a manual Start/Restart clear bytes that have not yet
            # reached the transcript.
            self._restart_when_output_drained = True
            self.set_status("draining output", "stopping")
            self.schedule_process_output_flush(backlog=True)
            self.update_process_actions()
            return
        if self.profile is not None:
            try:
                assert_profile_launch_allowed(self.profile, surface="gui")
            except (OSError, ValueError) as exc:
                self.set_status("policy blocked", "blocked")
                self.append_text(f"[policy blocked] {exc}\n")
                self.update_process_actions()
                return
        self.output.clear()
        self._rendered_terminal_text = ""
        self.terminal_emulator.reset()
        self._terminal_follow_output = True
        self._terminal_force_follow_output = False
        self.output.setProperty("terminalFollowOutput", True)
        self.reset_process_output_pipeline()
        self._restart_when_output_drained = False
        self.disarm_initial_pty_clear_recovery()
        self.set_status("starting", "starting")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.input.setEnabled(False)
        self.append_text(self.terminal_startup_context_text())
        self.arm_initial_pty_clear_recovery()
        runtime_override = self.property("terminalRuntimeCommand")
        if isinstance(runtime_override, (list, tuple)) and runtime_override:
            runtime_command = [str(argument) for argument in runtime_override]
        else:
            runtime_command = list(self.plan.command)
        runtime_command = openssh_command_without_windows_connection_sharing(runtime_command)
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
        if self.plan.environment:
            environment = QProcessEnvironment.systemEnvironment()
            for key, value in self.plan.environment.items():
                environment.insert(key, value)
            self.process.setProcessEnvironment(environment)
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

        self._terminal_scroll_closed = True
        self._terminal_scroll_generation += 1
        self._terminal_scroll_timer.stop()
        self.setProperty("terminalClosing", True)
        self._stop_timer.stop()
        self.reset_process_output_pipeline()
        self._restart_when_output_drained = False
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
        self.append_text("\n[selected output copied]\n" if selection else "\n[command copied]\n")
        # Updating the transcript can invalidate delayed clipboard ownership
        # on the Windows Qt platform.  Flush the resulting posted selection
        # update without accepting new user input, then publish the detached
        # string so the stale selection event cannot clear the fresh copy.
        self.output.setProperty("terminalLastCopiedText", clipboard_text)
        _application_instance().processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        clipboard = self._terminal_clipboard_provider()
        clipboard.setText(clipboard_text)
        _application_instance().processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        # A different Windows process can hold the native clipboard for a
        # short interval.  Keep this path consistent with the interactive
        # terminal copy action: verify the write and make one bounded retry
        # without sleeping or blocking the GUI event loop.
        retried = clipboard.text() != clipboard_text
        if retried:
            clipboard.setText(clipboard_text)
            _application_instance().processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )
        self.output.setProperty("terminalClipboardWriteRetried", retried)

    def clear_output(self) -> None:
        self._terminal_follow_output = True
        self._terminal_force_follow_output = False
        self.output.setProperty("terminalFollowOutput", True)
        self.output.clear()
        self._rendered_terminal_text = ""
        self.terminal_emulator.reset()
        self.reset_process_output_pipeline()
        self._restart_when_output_drained = False
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
        raw_line = self.input.text()
        self.input.clear()
        if not self.is_running():
            self.append_text("[stdin ignored: process is not running]\n")
            return
        secret_input = self._secret_prompt_active
        self.input.setProperty("terminalLastSubmissionWasSecret", secret_input)
        line = raw_line
        if not secret_input:
            self.capture_macro_input(raw_line)
            line = normalise_local_shell_input(raw_line, self.plan)
        self.input.setProperty("terminalLastSubmittedText", raw_line)
        self.input.setProperty("terminalLastCommandSent", line)
        self.input.setProperty("terminalLastCommandTranslated", line != raw_line)
        # A terminal Enter key is carriage return.  Preserve LF for the
        # ordinary pipe backend so conventional line readers still receive
        # a complete line when no local PTY is available.
        terminator = "\r" if bool(getattr(self.process, "is_pty", False)) else "\n"
        self.send_raw_input((line + terminator).encode("utf-8"))

    def macro_capture_name(self) -> str:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", self.plan.title).strip("-").lower()
        return f"{slug or 'terminal'}-live"

    def macro_pane_id(self) -> str:
        raw = str(
            self.property("mobaConnectedRouteActiveTabLabel") or self.plan.title or "terminal-pane"
        )
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
        injection = build_terminal_macro_replay_injection(
            self.macro_last_recording, pane_id=self.macro_pane_id()
        )
        self.macro_last_injection = injection
        self.macro_replay_sequence += 1
        self.macro_replay_cancelled = False
        self.macro_replay_active = True
        sequence = self.macro_replay_sequence
        for step, payload in zip(injection.steps, injection.injected_payloads, strict=False):
            delay = max(0, int(step.scheduled_after_ms))
            QTimer.singleShot(
                delay,
                lambda payload=payload, sequence=sequence: self.write_macro_replay_payload(
                    payload, sequence
                ),
            )
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
            widget.setProperty(
                "mobaMacroPaneId", state.pane_id if state is not None else self.macro_pane_id()
            )
            widget.setProperty("mobaMacroCaptureActive", active)
            widget.setProperty(
                "mobaMacroCaptureCancelled", bool(state is not None and state.cancelled)
            )
            widget.setProperty("mobaMacroCaptureEventCount", event_count)
            widget.setProperty("mobaMacroCaptureControls", ["record", "stop", "cancel"])
            widget.setProperty("mobaMacroCaptureSource", "pyqt-terminal-pane")
            widget.setProperty(
                "mobaMacroLastRecordingName", recording.name if recording is not None else ""
            )
            widget.setProperty(
                "mobaMacroLastRecordingInputSha256",
                recording.to_dict()["input_sha256"] if recording is not None else "",
            )
            widget.setProperty(
                "mobaMacroReplayInjectionSchema", injection.schema if injection is not None else ""
            )
            widget.setProperty(
                "mobaMacroReplayInjectedEventCount",
                injection.event_count if injection is not None else 0,
            )
            widget.setProperty(
                "mobaMacroReplayPerKeystrokeTiming", bool(injection is not None and injection.steps)
            )
            widget.setProperty("mobaMacroReplayCancelSupported", True)
            widget.setProperty("mobaMacroReplayActive", self.macro_replay_active)
            widget.setProperty("mobaMacroReplayCancelled", self.macro_replay_cancelled)

    def read_stdout(self) -> None:
        self.pull_process_output_channel("stdout")

    def read_stderr(self) -> None:
        self.pull_process_output_channel("stderr")

    def process_output_pending(self) -> bool:
        return bool(
            self._process_output_buffer
            or self._process_output_flush_scheduled
            or self._process_output_trailers
            or self._process_output_decode_final_pending
            or self._process_output_end_pending
            or (self._process_output_source_end_pending and not self._process_output_source_drained)
        )

    def reset_process_output_pipeline(self) -> None:
        """Reset one completed stream without leaving transport readers paused."""

        self._process_output_timer.stop()
        self._process_output_flush_scheduled = False
        self._process_output_buffer.clear()
        self._process_output_decoder.reset()
        self._process_output_decode_final_pending = False
        self._process_output_end_pending = False
        self._process_output_source_end_pending = False
        self._process_output_source_drained = True
        self._process_output_trailers.clear()
        self._process_output_flush_count = 0
        self.output.setProperty("terminalOutputBufferedBytes", 0)
        self.output.setProperty("terminalOutputFlushCount", 0)
        self.output.setProperty("terminalOutputDeferredTrailerCount", 0)
        # Resume last: native transports may synchronously emit retained
        # output from their pause setter. The clean decoder/queue must be
        # ready before that byte-preserving callback can run.
        self.set_process_output_read_paused(False)

    def set_process_output_read_paused(self, paused: bool) -> None:
        """Apply byte-preserving transport backpressure when supported."""

        enabled = bool(paused)
        if enabled == self._process_output_read_paused:
            return
        self._process_output_read_paused = enabled
        self.output.setProperty("terminalOutputReadPaused", enabled)
        setter = getattr(self.process, "setOutputPaused", None)
        self.output.setProperty(
            "terminalOutputBackpressureAvailable",
            callable(setter),
        )
        if callable(setter):
            setter(enabled)

    def read_process_output_chunk(self, channel: str, max_bytes: int) -> bytes:
        """Read a bounded transport prefix without discarding the remainder."""

        method_name = "readStandardError" if channel == "stderr" else "readStandardOutput"
        bounded_reader = getattr(self.process, method_name, None)
        if callable(bounded_reader):
            return bytes(bounded_reader(max_bytes))
        read = getattr(self.process, "read", None)
        set_channel = getattr(self.process, "setReadChannel", None)
        if callable(read) and callable(set_channel):
            process_channel = (
                QProcess.ProcessChannel.StandardError
                if channel == "stderr"
                else QProcess.ProcessChannel.StandardOutput
            )
            set_channel(process_channel)
            payload = read(max_bytes)
            return bytes(payload) if payload is not None else b""
        # Every production terminal backend supports a bounded reader.  The
        # fallback keeps compatibility with small test doubles only.
        fallback = getattr(
            self.process,
            "readAllStandardError" if channel == "stderr" else "readAllStandardOutput",
        )
        return bytes(fallback())

    def pull_process_output_channel(self, channel: str) -> tuple[int, bool]:
        """Fill the GUI queue up to its high-water mark.

        The boolean result records that an empty read was observed.  Once
        the process has ended, observing both channels empty is the safe
        boundary for final UTF-8 decoding and lifecycle trailers.
        """

        total = 0
        observed_empty = False
        while len(self._process_output_buffer) < self.OUTPUT_BUFFER_HIGH_WATER_BYTES:
            allowance = self.OUTPUT_BUFFER_HIGH_WATER_BYTES - len(self._process_output_buffer)
            payload = self.read_process_output_chunk(
                channel,
                min(self.OUTPUT_READ_CHUNK_BYTES, allowance),
            )
            if not payload:
                observed_empty = True
                break
            total += len(payload)
            self.queue_process_output(payload)
        if len(self._process_output_buffer) >= self.OUTPUT_BUFFER_HIGH_WATER_BYTES:
            self.set_process_output_read_paused(True)
        return total, observed_empty

    def pull_ended_process_output(self) -> None:
        """Incrementally consume bytes retained by an ended transport."""

        if not self._process_output_source_end_pending:
            return
        if len(self._process_output_buffer) > self.OUTPUT_BUFFER_LOW_WATER_BYTES:
            return
        self.set_process_output_read_paused(False)
        _stdout_bytes, stdout_empty = self.pull_process_output_channel("stdout")
        if len(self._process_output_buffer) >= self.OUTPUT_BUFFER_HIGH_WATER_BYTES:
            return
        _stderr_bytes, stderr_empty = self.pull_process_output_channel("stderr")
        if stdout_empty and stderr_empty:
            self._process_output_source_drained = True

    def refill_process_output(self) -> None:
        """Pull retained transport bytes whenever the GUI queue has capacity."""

        if len(self._process_output_buffer) > self.OUTPUT_BUFFER_LOW_WATER_BYTES:
            return
        self.set_process_output_read_paused(False)
        if self._process_output_source_end_pending:
            self.pull_ended_process_output()
            return
        self.pull_process_output_channel("stdout")
        if len(self._process_output_buffer) < self.OUTPUT_BUFFER_HIGH_WATER_BYTES:
            self.pull_process_output_channel("stderr")

    def schedule_process_output_flush(self, *, backlog: bool = False) -> None:
        # A normal shell command should be visible as soon as Qt returns
        # to its event loop. Full-screen apps still get one short frame
        # window to coalesce redraw fragments without delaying input.
        alternate_screen_active = bool(self.terminal_emulator.alternate_screen_active)
        delay_ms = 16 if alternate_screen_active and not backlog else 0
        self.output.setProperty("terminalOutputFlushDelayMs", delay_ms)
        self.output.setProperty(
            "terminalOutputFlushMode",
            "alternate-screen-coalesced"
            if alternate_screen_active and not backlog
            else "next-event-turn",
        )
        if self._process_output_flush_scheduled:
            if delay_ms == 0 and self._process_output_timer.remainingTime() > 0:
                self._process_output_timer.start(0)
            return
        self._process_output_flush_scheduled = True
        self._process_output_timer.start(delay_ms)

    def queue_process_output(self, payload: bytes) -> None:
        """Coalesce one event-loop burst before rebuilding the transcript.

        Full-screen programs redraw by emitting many small chunks. Feeding
        every chunk directly into QTextEdit can starve key events and make
        the terminal look frozen. A frame-bounded 16 ms timer preserves
        ordering, collapses the burst into one render pass, and leaves time
        for keyboard, resize and tab events when a command floods the PTY.
        """

        if not payload:
            return
        if bool(self.property("terminalClosing")):
            return
        self._process_output_buffer.append(payload)
        self.output.setProperty(
            "terminalOutputBufferedBytes",
            len(self._process_output_buffer),
        )
        if len(self._process_output_buffer) >= self.OUTPUT_BUFFER_HIGH_WATER_BYTES:
            self.set_process_output_read_paused(True)
        self.schedule_process_output_flush()

    def flush_process_output(self) -> None:
        self._process_output_flush_scheduled = False
        if not self._process_output_buffer:
            self.refill_process_output()
        if not self._process_output_buffer:
            self.finish_deferred_process_output()
            return
        # One bounded render per event turn is substantially faster than a
        # fixed 16 KiB/16 ms rate, while the zero-delay continuation still
        # yields to input, resize and tab events between transcript builds.
        payload = self._process_output_buffer.take(self.OUTPUT_RENDER_TURN_BUDGET_BYTES)
        self._process_output_flush_count += 1
        self.output.setProperty(
            "terminalOutputBufferedBytes",
            len(self._process_output_buffer),
        )
        self.output.setProperty(
            "terminalOutputFlushCount",
            self._process_output_flush_count,
        )
        self.append_decoded_process_output(payload)
        if len(self._process_output_buffer) <= self.OUTPUT_BUFFER_LOW_WATER_BYTES:
            self.refill_process_output()
        if self._process_output_buffer:
            self.schedule_process_output_flush(backlog=True)
        else:
            self.finish_deferred_process_output()

    def flush_process_output_now(self) -> None:
        """Drain a bounded prefix at shutdown and defer the remainder.

        A process can exit immediately after emitting megabytes of output.
        Rendering that entire tail inside ``finished`` or ``errorOccurred``
        blocks the Qt event loop and makes the window appear hung. Preserve
        byte ordering while limiting the synchronous work to four normal
        render batches; the 16 ms timer drains the remainder.
        """

        self._process_output_flush_scheduled = False
        self._process_output_timer.stop()
        remaining_budget = self.OUTPUT_SYNC_DRAIN_BUDGET_BYTES
        while self._process_output_buffer and remaining_budget > 0:
            payload = self._process_output_buffer.take(
                min(self.OUTPUT_RENDER_BATCH_BYTES, remaining_budget)
            )
            remaining_budget -= len(payload)
            self._process_output_flush_count += 1
            self.output.setProperty(
                "terminalOutputBufferedBytes",
                len(self._process_output_buffer),
            )
            self.output.setProperty(
                "terminalOutputFlushCount",
                self._process_output_flush_count,
            )
            self.append_decoded_process_output(payload)
        if len(self._process_output_buffer) <= self.OUTPUT_BUFFER_LOW_WATER_BYTES:
            self.refill_process_output()
        if self._process_output_buffer:
            self.schedule_process_output_flush(backlog=True)
        else:
            self.finish_deferred_process_output()

    def append_decoded_process_output(self, payload: bytes) -> None:
        """Decode one byte batch without corrupting split UTF-8 sequences."""

        text = self._process_output_decoder.decode(payload, final=False)
        if not text:
            return
        self.append_process_text(text)

    def queue_process_output_trailer(self, text: str) -> None:
        """Render app-owned exit/error text after every queued process byte."""

        if not text:
            return
        if (
            self._process_output_buffer
            or self._process_output_flush_scheduled
            or (self._process_output_source_end_pending and not self._process_output_source_drained)
            or self._process_output_decode_final_pending
            or self._process_output_end_pending
        ):
            self._process_output_trailers.append(text)
            self.output.setProperty(
                "terminalOutputDeferredTrailerCount",
                len(self._process_output_trailers),
            )
            self.schedule_process_output_flush(backlog=True)
            return
        self.append_terminal_notice(text)

    def mark_process_output_end(self) -> None:
        """Record that no new process bytes may follow the retained tail."""

        self._process_output_source_end_pending = True
        self._process_output_source_drained = False
        self._process_output_decode_final_pending = True
        self._process_output_end_pending = True
        self.pull_ended_process_output()

    def finish_deferred_process_output(self) -> None:
        """Publish ordered trailers and a requested restart after tail drain."""

        if self._process_output_buffer:
            return
        if self._process_output_source_end_pending and not self._process_output_source_drained:
            self.pull_ended_process_output()
            if self._process_output_buffer:
                self.schedule_process_output_flush(backlog=True)
            elif not self._process_output_source_drained:
                self.schedule_process_output_flush(backlog=True)
            return
        if self._process_output_decode_final_pending:
            final_text = self._process_output_decoder.decode(b"", final=True)
            self._process_output_decoder.reset()
            self._process_output_decode_final_pending = False
            if final_text:
                self.append_process_text(final_text)
        if self._process_output_end_pending:
            transcript = self.terminal_emulator.end_of_stream()
            self._process_output_end_pending = False
            self._process_output_source_end_pending = False
            self._process_output_source_drained = True
            self.sync_terminal_emulator_mode_properties()
            self.render_terminal_transcript(transcript)
        trailers = self._process_output_trailers
        self._process_output_trailers = []
        self.output.setProperty("terminalOutputDeferredTrailerCount", 0)
        for trailer in trailers:
            self.append_terminal_notice(trailer)
        if self._restart_when_output_drained and not bool(self.property("terminalClosing")):
            self._restart_when_output_drained = False
            QTimer.singleShot(0, self.start)

    @staticmethod
    def is_initial_conpty_screen_clear(text: str) -> bool:
        """Recognize the bounded console-initialization clear emitted by ConPTY."""

        return "\x1b[?9001h" in text and "\x1b[2J" in text

    def arm_initial_pty_clear_recovery(self) -> None:
        armed = bool(
            getattr(self.process, "is_pty", False) and self.terminal_startup_context_text()
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
        self.sync_terminal_emulator_mode_properties()
        self.forward_terminal_emulator_responses()
        if alternate_screen_active:
            # Only the initial ConPTY shell clear may be normalized. Once
            # Vim/ncurses owns the alternate screen, rewriting the
            # transcript would reset its cursor and make it appear stuck.
            self.disarm_initial_pty_clear_recovery()
        if self._pty_initial_clear_pending and not alternate_screen_active:
            self._pty_startup_probe = (self._pty_startup_probe + text)[-16_384:]
            if self.is_initial_conpty_screen_clear(self._pty_startup_probe):
                body = self.normalized_initial_pty_body(transcript)
                self.disarm_initial_pty_clear_recovery()
                self.set_terminal_transcript(f"{self.terminal_startup_context_text()}{body}")
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

    def sync_terminal_emulator_mode_properties(self) -> None:
        """Expose negotiated VT modes for diagnostics and interaction evidence."""

        self.output.setProperty(
            "terminalBracketedPasteActive",
            self.terminal_emulator.bracketed_paste_active,
        )
        self.output.setProperty(
            "terminalOriginModeActive",
            self.terminal_emulator.origin_mode_active,
        )
        self.output.setProperty(
            "terminalInsertModeActive",
            self.terminal_emulator.insert_mode_active,
        )
        self.output.setProperty(
            "terminalAutoWrapActive",
            self.terminal_emulator.auto_wrap_active,
        )

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
        normalized_body = re.sub(
            r"\A(?:[ \t]*\n)+",
            "",
            body,
            count=1,
        )
        return f"{startup_context}{normalized_body}"

    def append_text(self, text: str) -> None:
        if not text:
            return
        transcript = self.terminal_emulator.feed(text)
        if self.terminal_emulator.alternate_screen_active:
            transcript = self.terminal_emulator.screen_text()
        self.sync_terminal_emulator_mode_properties()
        self.render_terminal_transcript(transcript)

    def append_terminal_notice(self, text: str) -> None:
        """Render app-owned text without trusting child ANSI parser state."""

        if not text:
            return
        transcript = self.terminal_emulator.feed_literal(text)
        if self.terminal_emulator.alternate_screen_active:
            transcript = self.terminal_emulator.screen_text()
        self.render_terminal_transcript(transcript)

    def set_terminal_transcript(self, text: str) -> None:
        """Seed a rendered transcript and keep ANSI stream state in sync."""

        self._terminal_follow_output = True
        self._terminal_force_follow_output = False
        self.output.setProperty("terminalFollowOutput", True)
        self.terminal_emulator.reset()
        self.output.clear()
        self._rendered_terminal_text = ""
        self.render_terminal_transcript(self.terminal_emulator.feed(text))

    def render_terminal_transcript(self, transcript: str) -> None:
        if bool(self.output.property("terminalTabPaintFrozen")):
            # A live SSH session may deliver a burst while Qt is settling
            # a tab close/switch. Keep emulator state current but avoid
            # rebuilding the QTextDocument on every chunk; the latest
            # transcript is rendered once the viewport is unfrozen.
            self._pending_terminal_transcript = transcript
            return
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
            and previous[selection_start:selection_end] == transcript[selection_start:selection_end]
        )
        scroll_bar = _required_gui_value(
            self.output.verticalScrollBar(),
            "terminal vertical scroll bar",
        )
        scroll_value = scroll_bar.value()
        alternate_screen_active = self.terminal_emulator.alternate_screen_active
        full_redraw_hint = self.terminal_emulator.consume_full_redraw_hint()
        # An alternate-screen application owns a fixed terminal grid, not
        # the transcript's scrollback.  Keeping QTextEdit's scrollbar
        # visible while replacing that grid lets Qt change the viewport
        # width and vertical offset between redraws, which produces the
        # one-frame gaps seen during tab switches and Vim repaints.
        alternate_scrollbars_hidden = bool(
            self.output.property("terminalAlternateScreenScrollbarsHidden")
        )
        if alternate_screen_active != alternate_scrollbars_hidden:
            scrollbar_policy = (
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                if alternate_screen_active
                else Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self.output.setVerticalScrollBarPolicy(scrollbar_policy)
            self.output.setHorizontalScrollBarPolicy(scrollbar_policy)
            self.output.setProperty(
                "terminalAlternateScreenScrollbarsHidden",
                alternate_screen_active,
            )
        was_scrolled_to_end = (
            not alternate_screen_active and scroll_value >= scroll_bar.maximum() - 2
        )
        follow_output = self._terminal_follow_output or was_scrolled_to_end
        self.output.setProperty(
            "terminalAlternateScreenActive",
            alternate_screen_active,
        )
        terminal_revision = int(getattr(self.terminal_emulator, "_render_revision", 0))
        if transcript == previous and terminal_revision == self._rendered_terminal_revision:
            # Cursor/selection state can change without changing a frame's
            # text. Avoid rebuilding the document in that case; this is a
            # common path for htop's cursor and status queries.
            self.update_remote_cursor_overlay(transcript)
            self.refresh_terminal_input_security(transcript)
            return
        updates_were_enabled = self.output.updatesEnabled()
        # QTextEdit paints synchronously while its document is edited. A
        # single guard for every frame prevents blank intermediate pages,
        # including normal shell output arriving beside an alternate screen.
        self.output.setProperty("terminalAlternateScreenRedraw", True)
        self.output.setUpdatesEnabled(False)
        append_only = bool(
            previous
            and transcript.startswith(previous)
            and not full_redraw_hint
            and not alternate_screen_active
        )
        replace_from = 0
        if append_only:
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
            start=replace_from if append_only else 0,
            screen=alternate_screen_active,
        )
        syntax_spans = (
            ()
            if alternate_screen_active
            else highlight_terminal_text(fragment_source, self.syntax_rules)
        )
        source_offset = replace_from if append_only else 0
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
                    syntax_rule_key=(syntax_span.rule_key if syntax_span is not None else ""),
                    link_target=(
                        syntax_span.text
                        if syntax_span is not None and syntax_span.rule_key == "url"
                        else ""
                    ),
                ),
            )
        self._rendered_terminal_text = transcript
        self._rendered_terminal_revision = terminal_revision
        if alternate_screen_active:
            # The retained screen is a viewport, not scrollback.  Always
            # anchor it at row zero even if the previous shell page had a
            # large scrollbar value.
            self._set_terminal_scroll_value(0)
            self._terminal_follow_output = False
            self._terminal_force_follow_output = False
            self.output.setProperty("terminalFollowOutput", False)
        elif self._terminal_force_follow_output:
            self._terminal_force_follow_output = False
            self.scroll_terminal_to_end()
        elif selection_text_unchanged:
            restored = QTextCursor(self.output.document())
            restored.setPosition(selection_anchor)
            restored.setPosition(
                selection_position,
                QTextCursor.MoveMode.KeepAnchor,
            )
            self.output.setTextCursor(restored)
            self._set_terminal_scroll_value(scroll_value)
            self._terminal_follow_output = follow_output
            self.output.setProperty("terminalFollowOutput", follow_output)
            self.output.setProperty("terminalSelectionPreservedOnOutput", True)
        elif follow_output:
            self.scroll_terminal_to_end()
        else:
            self._set_terminal_scroll_value(scroll_value)
            self._terminal_follow_output = False
            self.output.setProperty("terminalFollowOutput", False)
        if not alternate_screen_active:
            self.output.setProperty(
                "terminalAlternateScreenScrollbarsHidden",
                False,
            )
        self.output.setProperty("terminalAlternateScreenRedraw", False)
        self.output.setUpdatesEnabled(updates_were_enabled)
        self.output_viewport.update()
        self.output.update()
        self.update_remote_cursor_overlay(transcript)
        self.refresh_terminal_input_security(transcript)

    def update_remote_cursor_overlay(self, transcript: str) -> None:
        """Place the painted cursor at the emulator's active grid cell."""

        lines = transcript.split("\n")
        row = max(0, min(len(lines) - 1, self.terminal_emulator.cursor_row))
        column = max(0, self.terminal_emulator.cursor_column)
        line = lines[row]
        document_position = sum(len(value) + 1 for value in lines[:row])
        document_position += min(column, len(line))
        trailing_cells = max(0, column - len(line))
        self.output.setProperty("terminalRemoteCursorRow", row)
        self.output.setProperty("terminalRemoteCursorColumn", column)
        self.output.setProperty(
            "terminalApplicationCursorKeysActive",
            self.terminal_emulator.application_cursor_keys_active,
        )
        self.output.set_remote_cursor_state(
            document_position,
            trailing_cells=trailing_cells,
            visible=self.terminal_emulator.cursor_visible and self.is_running(),
        )

    def scroll_terminal_to_end(self) -> None:
        """Keep live output at the true document end after layout updates."""

        if self._terminal_scroll_closed:
            return
        if self.terminal_emulator.alternate_screen_active:
            # Alternate-screen applications own the viewport. Moving the
            # QTextEdit cursor to document end fights Vim's cursor
            # addressing and produces a visible flash on every redraw.
            self._terminal_scroll_generation += 1
            scroll_bar = _required_gui_value(
                self.output.verticalScrollBar(),
                "terminal vertical scroll bar",
            )
            self._set_terminal_scroll_value(0)
            self._terminal_follow_output = False
            self._terminal_force_follow_output = False
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
        self._set_terminal_scroll_value(scroll_bar.maximum())
        self._terminal_follow_output = True
        self.output.setProperty("terminalFollowOutput", True)

        self._terminal_scroll_settle_generation = generation
        self._terminal_scroll_timer.start(0)

    def settle_terminal_scroll(self) -> None:
        """Settle live output only while this pane owns the scheduled timer."""

        if self._terminal_scroll_closed:
            return
        if self._terminal_scroll_settle_generation != self._terminal_scroll_generation:
            return
        if self.terminal_emulator.alternate_screen_active:
            return
        if not self._terminal_follow_output:
            return
        bar = _required_gui_value(
            self.output.verticalScrollBar(),
            "terminal vertical scroll bar",
        )
        self._set_terminal_scroll_value(bar.maximum())
        self._terminal_scroll_programmatic += 1
        try:
            self.output.ensureCursorVisible()
        finally:
            self._terminal_scroll_programmatic = max(
                0,
                self._terminal_scroll_programmatic - 1,
            )
        self._set_terminal_scroll_value(bar.maximum())

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
        echo_mode = QLineEdit.EchoMode.Password if active else QLineEdit.EchoMode.Normal
        self.input.setEchoMode(echo_mode)
        self.input.setPlaceholderText(
            "Secret input (masked, not recorded); press Enter"
            if active
            else "stdin, shell command or interactive input"
        )
        self.input.setProperty("terminalSecretInputActive", active)
        self.output.setProperty("terminalSecretInputActive", active)
        self.update_process_actions()
        handler = self._authentication_change_handler
        if callable(handler):
            try:
                handler(self, active)
            except RuntimeError:
                # A tab can be replaced while a deferred output frame is
                # notifying the owning window about authentication.
                pass
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
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.mark_process_output_end()
        self.set_status("error", "error")
        detail = str(self.process.errorString()).strip()
        suffix = f": {detail}" if detail and detail != error.name else ""
        self.queue_process_output_trailer(f"\n[error] {error.name}{suffix}\n")
        self.flush_process_output_now()
        self.update_process_actions()

    def on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._stop_timer.stop()
        self.mark_process_output_end()
        self.refresh_terminal_input_security("")
        state = "ready" if exit_code == 0 else "error"
        self.set_status(f"exited {exit_code}", state)
        self.queue_process_output_trailer(f"\n[process exited: {exit_code}, {exit_status.name}]\n")
        self.flush_process_output_now()
        self.update_process_actions()
        if self._restart_after_stop and not bool(self.property("terminalClosing")):
            self._restart_after_stop = False
            if self._process_output_buffer or self._process_output_flush_scheduled:
                self._restart_when_output_drained = True
            else:
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
        output_pending = self.process_output_pending()
        capture_active = bool(
            self.macro_capture_state is not None and self.macro_capture_state.active
        )
        self.start_button.setEnabled(not running and not output_pending)
        self.restart_button.setEnabled(bool(self.plan.command) and (running or not output_pending))
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
