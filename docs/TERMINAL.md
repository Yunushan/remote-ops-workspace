# Embedded Terminal

The desktop terminal pane has a bounded ANSI transcript emulator
(`ansi-transcript-v1`) in front of its process-backed stream. It handles normal
printable output, line feeds, carriage-return progress redraws, backspaces,
tabs, common SGR styling sequences, and CSI clear/erase controls. Scrollback is
bounded to 10,000 completed lines.

This is not a PTY and does not claim to run full-screen terminal applications.
Programs that require terminal-size negotiation, alternate screens, mouse
reporting, or complete cursor-addressing support (for example `vim`, `top`, or
`tmux`) must be launched in a real external terminal. The embedded pane keeps
the existing safe argv process launch, input, lifecycle, and macro controls.
