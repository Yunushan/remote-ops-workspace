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
pseudo-console with the pane. SSH started inside the pipe-backed local shell is
outside this direct-launch path. Other commands and platforms keep the ordinary
pipe-backed process transport.

The bounded transcript emulator itself is not a PTY, and ConPTY does not turn it
into a complete terminal emulator. Programs that require alternate screens,
mouse reporting, or complete cursor-addressing support (for example `vim`,
`top`, or `tmux`) should still be launched in a full external terminal. If
ConPTY is unavailable, the GUI shows an explicit pipe-fallback warning;
interactive OpenSSH authentication is not claimed there, so use key/agent
authentication or an external terminal.

For an SSH profile that does not choose explicit values, the embedded launch
uses a 10-second connection timeout and retains OpenSSH's interactive host-key
confirmation. The optional SSH/SFTP editor preset records
`StrictHostKeyChecking=ask`; a first-seen key therefore requires operator
confirmation and a changed key is rejected. Existing profiles keep their
explicit policy or OpenSSH's hardened default; the code never silently selects
`accept-new` or `no`. Background monitoring remains non-interactive, uses
`StrictHostKeyChecking=yes`, and requires a previously trusted host plus
key/agent authentication.

When the transcript ends in a password or passphrase prompt, the line-input
field switches to masked mode and macro capture/replay is disabled for that
submission. Typing directly on the terminal surface also goes only to ConPTY.
Credentials stay behind the local vault and OpenSSH prompt boundaries and are
not added to argv, transcript text, macro recordings, logs, or profile options.
