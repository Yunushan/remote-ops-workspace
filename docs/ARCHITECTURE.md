# Architecture

## Layers

1. **Core model**: `Profile`, `Tunnel`, shared profile validation, feature manifest and storage primitives.
2. **Adapters**: protocol command builders in `launcher.py`.
3. **Operator interfaces**: CLI, PyQt6 GUI shell and Web/PWA shell.
4. **Security**: encrypted local vault, redacted audit log and safe command-array launching.
5. **Extensibility**: entry-point plugin loader and manifest-driven feature coverage.

## Why adapter-first?

The requested products cover many protocols and platforms. Re-implementing every protocol engine from scratch would create unnecessary licensing, security and maintenance risk. Adapter-first design lets the workspace support real workflows immediately by using battle-tested native clients, while keeping a clean plugin seam for embedded engines.

## Data model

Profiles are stored as JSON under the platform-specific config directory or under `ROW_HOME` for portable mode.

```json
{
  "name": "lab-ssh",
  "protocol": "ssh",
  "host": "ssh.example.invalid",
  "port": 22,
  "username": "admin",
  "group": "lab",
  "tags": ["ssh"],
  "options": {"x11": "false"}
}
```

The import path keeps the native JSON bundle as the canonical format, then converts
common external exports into the same `Profile` model. Current importers cover
Remmina `.remmina` files, mRemoteNG `confCons.xml`, Termius-style JSON host lists
and MobaXterm bookmark/session exports. Secret-like fields are skipped so imported
credentials stay behind the local vault boundary.

`profile_validation.py` owns shared profile invariants: supported protocol names,
clean profile/group/tag/option text, valid tunnel shape, safe host/port/url fields
and minimum launch target requirements such as host-backed SSH/RDP/VNC profiles,
explicit raw-socket ports, serial device paths and custom commands. Storage,
importers, GUI editor parsing and launch planning all pass through this layer
before protocol-specific command builders add adapter options.

GUI profile and layout editors use a pure conversion layer before touching PyQt
widgets. That keeps validation shared between tests and the desktop dialogs:
profile edits become `Profile` objects, layout pane text becomes `LayoutPane`
objects, and the same storage classes persist the results.

GUI terminal panes own a `QProcess` for each process-backed session, while the
main window owns tab and shutdown lifecycle. `gui_lifecycle.py` centralizes the
stop contract: idle processes are ignored, running processes receive a graceful
terminate request first, and stubborn processes are killed after a bounded
timeout. Closing a tab or quitting the app enumerates child terminal panes,
confirms live sessions with the operator, and applies the same cleanup path to
single tabs, split panes and saved-layout tabs.

File transfer operations are represented as SFTP batch plans. One-shot commands,
queued transfers and preview commands all flow through `file_transfer.py`, which
keeps remote paths, local paths and generated batch text validated before any
external `sftp` process is launched. Plans carry destructive-action metadata so
uploads, deletes, renames and known local-overwrite downloads can be previewed
with `--dry-run` but cannot execute through the project runner without `--force`.

## Plugin model

Third-party packages can register entry points under:

```toml
[project.entry-points."remote_ops_workspace.plugins"]
my_protocol = "my_package.plugin:Plugin"
```

Today this entry point is wired for protocol launch plugins. A plugin declares
`name`, `protocols` and optional `executables`, then implements
`build(profile) -> LaunchPlan`. Installed plugin protocols are accepted by
profile validation, can be listed with `row plugins list`, validated with
`row plugins validate`, appear in `row doctor`, and are dispatched by
`row connect`. `row plugins scaffold` creates a minimal third-party package
with the expected entry point, plugin class and launch-plan test. See
[`PLUGIN_DEVELOPMENT.md`](PLUGIN_DEVELOPMENT.md) for the exact contract.

Sync backends, terminal widgets, vault backends and network-tool plugins remain
future extension points. They should not be represented as active integrations
until they have a caller path equivalent to the protocol-launch path above.
