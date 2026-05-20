# Architecture

## Layers

1. **Core model**: `Profile`, `Tunnel`, feature manifest and storage primitives.
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
  "host": "192.0.2.10",
  "port": 22,
  "username": "admin",
  "group": "lab",
  "tags": ["ssh"],
  "options": {"x11": "false"}
}
```

## Plugin model

Third-party packages can register entry points under:

```toml
[project.entry-points."remote_ops_workspace.plugins"]
my_protocol = "my_package.plugin:Plugin"
```

A plugin can provide a protocol engine, a sync backend, a terminal widget, a vault backend, or network tools.
