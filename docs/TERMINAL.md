# Embedded Terminal

The desktop terminal pane has a bounded ANSI transcript emulator
(`ansi-transcript-v1`) in front of its process-backed stream. It handles normal
printable output, line feeds, carriage-return progress redraws, backspaces,
tabs, common SGR styling sequences, and CSI clear/erase controls. Scrollback is
bounded to 10,000 completed lines.

SGR rendering retains the normal and bright 16-color palette, xterm 256-color
indexes, 24-bit RGB foreground/background colors, bold, underlining, inverse
video, and foreground/background resets. Inverse video uses the active preset's
terminal palette rather than assuming a single dark theme. Escape sequences
stay outside the plain-text document, so copying, searching, and mouse or
keyboard selection—including selection across multiple lines—operate on the
visible text. Explicit SGR
colors take precedence over the product's semantic error/warning/prompt
highlight rules. This remains transcript styling, not complete VT screen
emulation.

Visible `http://` and `https://` text is rendered as a cyan underlined link.
Links never open from output alone: the user must Ctrl+click one, and the
terminal validates the scheme and host before handing it to the system browser.
Other schemes remain inert text so a remote process cannot activate local-file
or script URLs.

On Windows 10 version 1809/build 17763 or newer, direct embedded OpenSSH SSH and
SFTP launches use the native Windows ConPTY API. That gives `ssh.exe` and
`sftp.exe` a real local terminal for host-key, password and key-passphrase
prompts, forwards direct keystrokes and line input, and resizes the
pseudo-console with the pane. The child is launched with
`STARTF_USESHOWWINDOW`/`SW_HIDE` and null standard handles under
`STARTF_USESTDHANDLES`, so it cannot bypass the pseudoconsole during a tab
transition. SSH started inside the pipe-backed local shell is outside this
direct-launch path. Other commands and platforms keep the ordinary pipe-backed
process transport.

The bounded transcript emulator itself is not a PTY, and ConPTY does not turn it
into a complete VT implementation. It does retain a fixed-size alternate
screen, common Vim/ncurses erase and scroll-region operations, DECOM origin
addressing, insert/autowrap modes, DA/DSR replies, bracketed paste, DECCKM
application cursor keys, and remote cursor position plus `DECTCEM` visibility.
The Qt insertion caret remains hidden; a separate painted
cursor follows the remote grid cell without disturbing transcript selection or
flashing at the document end during tab changes. These contracts cover common
interactive shell, Vim and `htop` redraw/input paths, but not every terminfo
capability, terminal mouse-reporting protocol, or tmux feature. Workloads that
depend on unsupported VT behavior should still use a full external terminal.
If ConPTY is unavailable, the GUI shows an explicit pipe-fallback warning;
interactive OpenSSH authentication is not claimed there, so use key/agent
authentication or an external terminal.

Process output is initially coalesced for 16 ms, then an adaptive drain renders
at most 256 KiB per event-loop turn and yields between turns. Transport reads
are bounded to 64 KiB; reaching the 4 MiB GUI high-water mark pauses the native
reader, and draining below 1 MiB resumes it without dropping bytes. Error and
exit handlers may synchronously consume at most 64 KiB in 16 KiB decode batches,
then retain the rest for ordered asynchronous delivery. End-of-stream finalizes
split UTF-8 and resets partial child ANSI state before app-owned error/exit
trailers are rendered literally. This keeps output-heavy Vim/htop sessions and
large process tails responsive while preserving every queued byte and trailer.
Non-interactive monitoring and SFTP helper processes are created on a worker
thread and adopted by the Qt event loop after startup. Input submitted while a
helper is starting is bounded and queued, and tab teardown cancels stale starts
without waiting on process creation or console cleanup. On native Windows the
explicit **Authenticate background tools** action can unlock a profile's local
encrypted-vault `credential_ref`, or accept a direct SSH password for a profile
without one, for the current dock session. The helpers then use a hidden ConPTY
to answer one OpenSSH password prompt without creating a console window. The
password is never placed in argv, the transcript, logs or profile data, and is
wiped when the dock shuts down. Key/agent authentication continues to work
without prompting.
The terminal backends also publish `terminalConsoleSuppressed` and
`terminalChildWindowPolicy` (`conpty-hidden` or `create-no-window` on native
Windows), so tab-switch smoke tests can fail closed if a visible helper process
is introduced.

Tab changes freeze the old page before Qt exposes the successor and release the
guard only after deferred layout/chrome reconciliation. Mouse selection,
Ctrl+Tab/Backtab navigation, and closing the active tab use the same prepaint
path so an intermediate minimum-size terminal cannot appear in the center of
the workspace. The native Windows paint gate launches both probe terminals as
real continuous ANSI producers through native ConPTY, the Qt `readyRead` path
and the production output batcher. It captures every mouse, Ctrl+Tab and
active-close event turn and rejects blank, miniature, wrong-tab,
non-alternate-screen, stopped-process or no-output-batch frames.

The native Windows SSH loopback gate additionally opens two strict-host-key
profiles as separate live ConPTY tabs through both the direct terminal-tab and
Moba-connected-session-tab compositions, authenticates both, switches between
them repeatedly, and records route-specific `ssh-tab-switch-evidence-*.json`
files plus the established `ssh-tab-switch-evidence.json` artifact. That
evidence requires every active SSH viewport to remain full-sized, live, and
outside the tab-transition/prepaint guards. The same gate also selects each
tab through the real MobaXterm-style tab-bar mouse press/release route for
repeated cycles; it rejects any miniature, blank, or unpainted page during
those mouse-driven changes. It also enumerates visible top-level windows for
each OpenSSH process and its descendants at every mouse press/release and
Ctrl+Tab key press/release boundary, so a spawned `conhost.exe` surface fails
the gate instead of being mistaken for a Qt paint artifact.

In the MobaXterm preset, the left and right edges of a normal session tab are
bounded mouse resize handles. Session widths stay between 140 and 640 logical
pixels, preserve the user's width when active-tab chrome is refreshed, and do
not resize the fixed Home or new-session tabs. Terminal splitters and the
sidebar remain independently mouse-resizable.

The desktop GUI starts with an empty private profile store. It never seeds
sample SSH, RDP, SFTP, or web sessions into a normal source or frozen run.
Internal screenshot and interaction checks may pass the explicit
`preview_samples=True` factory option to render deterministic sample rows;
that opt-in is test data and is not a release default.

The MobaXterm preset enables its native mouse-paste convention: a plain
right-button press pastes the clipboard (with a later Qt context event
deduplicated), middle-click pastes the platform selection
when one exists (falling back to the clipboard), and Shift+Right-click opens
the complete terminal context menu. Other presets keep ordinary right-click
menus by default. When the remote application negotiates bracketed paste, all
paste routes preserve the `ESC [ 200 ~` / `ESC [ 201 ~` envelope. The required
native Windows SSH loopback gate exercises keyboard, Qt-dispatched right-click,
middle-click, and remotely negotiated bracketed-paste bytes through the real
Qt, ConPTY and OpenSSH path.

For an SSH profile that does not choose explicit values, the embedded launch
uses a 10-second connection timeout and retains OpenSSH's interactive host-key
confirmation. The optional SSH/SFTP editor preset records
`StrictHostKeyChecking=ask`; a first-seen key therefore requires operator
confirmation and a changed key is rejected. Existing profiles keep their
explicit policy or OpenSSH's hardened default; the code never silently selects
`accept-new` or `no`. Background monitoring remains host-key strict. It
requires a previously trusted host plus key/agent authentication, or the
explicit vault-authenticated helper route described above.

When the transcript ends in a password or passphrase prompt, the line-input
field switches to masked mode and macro capture/replay is disabled for that
submission. Typing directly on the terminal surface also goes only to ConPTY.
Credentials stay behind the local vault and OpenSSH prompt boundaries and are
not added to argv, transcript text, macro recordings, logs, or profile options.
