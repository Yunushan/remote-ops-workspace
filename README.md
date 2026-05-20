<div align="center">

# Remote Ops Workspace

### Operator-first remote terminal and connection workspace for SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, serial consoles, raw sockets, split panes, vaults, snippets, sync, CLI, GUI and Web/PWA.

![build](https://img.shields.io/badge/build-ready-brightgreen)
![release](https://img.shields.io/badge/release-v0.1.0-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![runtime](https://img.shields.io/badge/runtime-Python%203.10--3.13-orange)
![interfaces](https://img.shields.io/badge/interfaces-CLI%20%7C%20GUI%20%7C%20Web-purple)
![targets](https://img.shields.io/badge/targets-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD%20%7C%20Solaris%20%7C%20Android%20%7C%20Web-green)
![protocols](https://img.shields.io/badge/protocols-SSH%20%7C%20RDP%20%7C%20VNC%20%7C%20SFTP%20%7C%20Mosh%20%7C%20Telnet%20%7C%20SPICE%20%7C%20X2Go-yellow)

[Quick Start](#quick-start) • [CLI](#cli) • [GUI](#gui) • [Web/PWA](#webpwa) • [Feature Coverage](#feature-coverage) • [Platforms](#platform-support) • [Architecture](#architecture) • [Security](#security) • [License](#license)

English • [Türkçe](README.tr.md)

</div>

---

## What this project is

**Remote Ops Workspace** is a GitHub-ready, MIT-licensed, cross-platform remote access workspace designed as an open foundation for the feature families people expect from MobaXterm, Remmina, mRemoteNG, Terminator and Termius.

It is intentionally built as an **adapter-first product**: the repo includes a real CLI, profile store, launcher command builders, encrypted vault support, GUI shell, Web/PWA shell, feature coverage manifest, tests, installers, CI and release scaffolding. Deep protocol rendering can be provided by native system tools such as OpenSSH, FreeRDP, TigerVNC, x2goclient, virt-viewer, PuTTY, Windows MSTSC, XQuartz/VcXsrv/Xorg, or by future embedded protocol plugins.

> Not affiliated with Mobatek/MobaXterm, Remmina, mRemoteNG, GNOME Terminator, or Termius. Product names are used only to describe compatibility goals and feature coverage targets.

---

## Quick Start

```bash
git clone https://github.com/YOUR-ORG/remote-ops-workspace.git
cd remote-ops-workspace

python -m venv .venv
# Linux/macOS/BSD/Solaris
. .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[desktop,security]"
row init
row profile add --name lab-ssh --protocol ssh --host 192.0.2.10 --username admin
row connect lab-ssh --dry-run
row doctor
```

Start the desktop UI:

```bash
row gui
```

Start the browser/PWA UI:

```bash
row serve-web --host 127.0.0.1 --port 8765
```

---

## CLI

```bash
row init
row profile add --name core-rdp --protocol rdp --host 192.0.2.20 --username administrator
row profile add --name switch-console --protocol serial --path /dev/ttyUSB0 --option baud=115200
row profile list
row profile show core-rdp
row connect core-rdp --dry-run
row connect core-rdp
row features
row vault init
row vault set prod/router-password
row vault list
row export --out backups/remote-ops-export.json
row import --in backups/remote-ops-export.json
```

The launcher never concatenates shell strings. Protocol launches are built as safe argument arrays and can be inspected with `--dry-run` before execution.

---

## GUI

The PyQt6 desktop shell provides:

- session tree and quick-connect panel;
- external protocol launch buttons;
- tabbed workspace placeholder;
- split-pane layout controls inspired by tiling terminals;
- doctor/status panel;
- plugin-ready terminal embedding seam for `qtermwidget`, PTY-backed terminals, web terminals, or native terminal widgets.

Install optional GUI extras:

```bash
pip install -e ".[desktop,security]"
row gui
```

---

## Web/PWA

`apps/web` contains a static browser workspace that can run as a PWA. It is useful for Android/browser workflows, documentation demos and future API integration.

```bash
row serve-web --host 0.0.0.0 --port 8765
```

Then open the displayed URL from a browser or install it as a PWA.

---

## Feature Coverage

Coverage target: **100% of the public feature families** represented by the requested tools, mapped to either built-in code, external-client adapters, or documented plugin seams.

| Feature family | MobaXterm | Remmina | mRemoteNG | Terminator | Termius | Project coverage |
|---|---:|---:|---:|---:|---:|---|
| SSH terminal sessions | ✅ | ✅ | ✅ | local shell | ✅ | Built-in OpenSSH adapter + profile store |
| RDP | ✅ | ✅ | ✅ | — | — | MSTSC/FreeRDP adapter |
| VNC | ✅ | ✅ | ✅ | — | — | TigerVNC/RealVNC adapter |
| SFTP/SCP/FTP file transfer | ✅ | profile/file features | — | — | ✅ | OpenSSH SFTP/SCP adapter + file-transfer profile type |
| Telnet/rlogin/rsh/raw sockets | ✅ | limited/plugins | ✅ | — | Telnet | External command adapters |
| Mosh | ✅ | plugins | — | — | ✅ | Mosh adapter |
| X11 forwarding / X server workflow | ✅ | X/SSH workflows | — | — | SSH forwarding | SSH `-X/-Y` + VcXsrv/XQuartz/Xorg helper notes |
| SPICE/X2Go/XDMCP | XDMCP | ✅ | — | — | — | virt-viewer/x2goclient/XDMCP plugin seams |
| ICA/Citrix | — | plugins | ✅ | — | — | `wfica` adapter seam |
| Session manager / groups / tags | ✅ | ✅ | ✅ | profiles | ✅ | JSON profile store, groups, tags |
| Tabs and split panes | ✅ | ✅ | ✅ | ✅ | multi-session | GUI shell + layout manifest |
| Broadcast input / command fanout | macros/tools | — | — | ✅ | snippets | Command group and snippets seam |
| Macros / snippets | ✅ | — | — | shortcuts | ✅ | Snippet model and manifest entries |
| Encrypted vault | passwords | password store | credential store | — | ✅ | Optional cryptography-based local vault |
| Cloud/team sync | shared sessions | — | shared config options | — | ✅ | Export/import now; sync provider seam |
| Keygen / SSH keys / agent | SSH keys | SSH keys | PuTTY keys | — | ✅ | OpenSSH key helper seam |
| Hardware/FIDO keys | SSH support | SSH support | depends | — | ✅ | OpenSSH/FIDO agent seam |
| Portable mode | ✅ | packages | config portability | — | mobile/desktop | `ROW_HOME` portable data directory |
| Web/mobile access | — | Kasm/container options | — | — | ✅ | Static Web/PWA shell + Android/PWA docs |
| Plugin architecture | plugins | plugins | extensions | plugins | integrations | Python entry-point plugin loader |

See [`docs/FULL_FEATURE_COVERAGE.md`](docs/FULL_FEATURE_COVERAGE.md) and [`configs/feature_manifest.json`](configs/feature_manifest.json) for the full coverage manifest.

---

## Platform Support

| Platform | Target mode | Notes |
|---|---|---|
| Windows 10/11 | CLI, GUI, Web/PWA | OpenSSH, MSTSC, PuTTY, VcXsrv, TigerVNC adapters |
| Windows Server 2012–2025 | CLI, GUI optional, Web/PWA | Works well as an operator jump host; use PowerShell installer |
| Linux | CLI, GUI, Web/PWA | OpenSSH, FreeRDP, TigerVNC, Remmina-compatible clients, Xorg |
| Unix | CLI, Web/PWA, GUI where Qt is available | POSIX shell and OpenSSH first |
| FreeBSD/OpenBSD/NetBSD/DragonFlyBSD | CLI, Web/PWA, GUI where PyQt6 is packaged | External protocol tools vary by ports/pkg availability |
| Solaris/illumos | CLI, Web/PWA, GUI if Python/Qt stack exists | Focus on OpenSSH, browser, serial/raw sockets |
| macOS Intel/Apple Silicon | CLI, GUI, Web/PWA | OpenSSH, XQuartz, Microsoft Remote Desktop/FreeRDP, VNC viewers |
| Android | Web/PWA, Termux CLI | Browser/PWA first; Termux can run the Python CLI and OpenSSH adapters |
| Web | PWA shell | Static UI today; API/backend seam included |

---

## Architecture

```text
remote-ops-workspace/
├── src/remote_ops_workspace/     # Python core, CLI, GUI shell, vault, launchers
├── apps/web/                     # Static Web/PWA workspace
├── configs/                      # Example profiles, settings, feature manifest
├── docs/                         # Feature coverage, platform, security, runbooks
├── installers/                   # install.sh, install.ps1, install.bat
├── scripts/                      # platform doctor, release helper, support bundle
├── tests/                        # Unit tests for core behavior
└── .github/workflows/            # CI and release automation
```

Core design principles:

1. **No proprietary client code**: launch and integrate open/system protocol tools unless a future plugin adds an embedded engine.
2. **Safe-by-default launching**: command arrays instead of shell strings.
3. **Portable profiles**: JSON profile store, environment-driven data path, backup/export/import.
4. **Security boundary clarity**: local encrypted vault support, no secrets committed, redaction utilities.
5. **Plugin-ready parity**: every requested feature family has a registry entry and extension point.

---

## Security

- Do not commit real profiles, passwords, private keys, vault files, or customer hostnames.
- Use `ROW_HOME` for portable/private operator workspaces.
- Store examples only under `configs/*.example.*`.
- Use `row connect NAME --dry-run` before launching newly imported profiles.
- Vault encryption requires the optional `security` extra: `pip install -e ".[security]"`.
- See [`SECURITY.md`](SECURITY.md) and [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

---

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security,dev]"
python -m compileall src
pytest -q
```

Create a local release bundle:

```bash
python scripts/make_release.py
```

---

## License

MIT. See [`LICENSE`](LICENSE).
