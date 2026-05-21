# Profile Importers

`row import` can read the native Remote Ops Workspace bundle plus practical
session exports from common remote-ops tools.

```bash
row import --in remote-ops-export.json
row import --in ~/.local/share/remmina --format remmina
row import --in confCons.xml --format mremoteng
row import --in termius-hosts.json --format termius
row import --in sessions.mxtsessions --format mobaxterm
row import --in ./exported-sessions --format auto
```

Supported formats:

| Format | Input shape | Imported fields |
|---|---|---|
| `row` | Remote Ops Workspace JSON bundle | Full local profile model |
| `remmina` | `.remmina` file or directory of `.remmina` files | Name, protocol, host/server, port, user, group, RDP/VNC/SSH options |
| `mremoteng` | `confCons.xml` style XML | Nested groups, name, protocol, host, port, user, RDP domain |
| `termius` | Termius-style JSON host list | Name/label, address, protocol, port, user, group, tags, identity file, Mosh port |
| `mobaxterm` | `.mxtsessions` or `MobaXterm.ini` bookmarks | Session name, group, protocol heuristic, host, port, user |

Use `--replace` when imported profile names should overwrite existing local
profiles. Without `--replace`, duplicate names are rejected by the profile store.
Duplicate names inside one import are made unique with numeric suffixes.

Secrets are not imported. Password, passphrase and secret-like fields are skipped
and reported as warnings, because storing or printing vendor-exported secrets
would weaken the local vault boundary. Recreate credentials with:

```bash
row vault set prod/router-password
row profile defaults prod --credential-ref prod/router-password
```

Always inspect imported launch commands before use:

```bash
row profile list
row connect PROFILE --dry-run
```
