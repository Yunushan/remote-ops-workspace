<div align="center">

# Remote Ops Workspace

### Operator-first remote terminal and connection workspace for SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, serial consoles, raw sockets, split panes, vaults, snippets, sync, CLI, GUI and Web/PWA.

![build](https://img.shields.io/badge/build-ready-brightgreen)
![release](https://img.shields.io/badge/release-v0.1.0-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![runtime](https://img.shields.io/badge/runtime-Python%203.10--3.14-orange)
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
row profile add --name jump-ssh --protocol ssh --host 192.0.2.10 --username admin --option proxy_jump=bastion --option keepalive_interval=30
row profile add --name lab-vnc --protocol vnc --host 192.0.2.30 --option fullscreen=true --option shared=true
row profile list
row profile show core-rdp
row connect core-rdp --dry-run
row connect core-rdp
row features
row platforms
row vault init
row vault set prod/router-password
row vault list
row features --coverage
row files ls lab-ssh /var/log --dry-run
row files get lab-ssh /etc/hosts --local ./hosts.copy --dry-run
row files queue lab-ssh --op "get /etc/hosts ./hosts.copy" --op "put ./build.tar.gz /tmp/build.tar.gz" --dry-run
row files preview-local ./README.md --json
row snippet add --name uptime --command "uptime" --tag ops
row layout save triage --pane profile:lab-ssh --pane command:top --orientation horizontal
row layout run triage --dry-run
row broadcast --group prod --command "hostname" --timeout 10 --json
row keygen --out ~/.ssh/id_ed25519_row --comment row
row nettool ping example.com --dry-run
row sync push --to ~/RemoteOpsSync
row export --out backups/remote-ops-export.json
row import --in backups/remote-ops-export.json
row import --in confCons.xml --format mremoteng
row import --in ~/.local/share/remmina --format remmina
```

The launcher never concatenates shell strings. Protocol launches are built as safe argument arrays and can be inspected with `--dry-run` before execution. Per-protocol profile options cover OpenSSH keepalives/proxies/host-key policy, Mosh ports/prediction, RDP display/security/device flags, VNC/SPICE/X2Go viewer flags and serial line settings; see [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md).

Profile imports support the native ROW bundle plus Remmina `.remmina`, mRemoteNG `confCons.xml`, Termius-style JSON host lists and MobaXterm session bookmark exports. See [`docs/IMPORTERS.md`](docs/IMPORTERS.md). File transfer queues and previews are documented in [`docs/FILE_TRANSFER.md`](docs/FILE_TRANSFER.md).

---

## GUI

The PyQt6 desktop shell provides:

- session tree and quick-connect panel;
- profile create/edit/remove dialogs backed by the same profile store as the CLI;
- external protocol launch buttons;
- interactive SFTP file browser panes and transfer queue preview dialog for SSH/SFTP profiles;
- tabbed workspace for process-backed sessions;
- process-backed terminal panes with stdout/stderr capture and stdin entry;
- horizontal and vertical split-pane shells inspired by tiling terminals;
- selectable GUI view presets: Native, MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style;
- saved layout selector plus create/edit/remove dialogs that open layout panes directly in the workspace;
- doctor/status panel;
- future plugin seam for deeper PTY/qtermwidget/web terminal emulation.

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

Coverage target: **100% public feature-family mapping** for the requested tools, tracked separately from product-ready implementation maturity.

Coverage is generated from [`configs/feature_manifest.json`](configs/feature_manifest.json). Feature-family mapping answers whether each public feature family is represented by built-in code, external adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Product-ready coverage applies stricter evidence weights so adapter-backed, optional, shell, script and partial workflows are not overstated.

| Product target | Feature-family mapping | Product-ready coverage | Ready gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|
| MobaXterm | 100.0% | 100.0% | 0.0% | 25 |
| Remmina | 100.0% | 100.0% | 0.0% | 11 |
| mRemoteNG | 100.0% | 100.0% | 0.0% | 15 |
| Terminator | 100.0% | 100.0% | 0.0% | 8 |
| Termius | 100.0% | 100.0% | 0.0% | 21 |
| Devolutions Remote Desktop Manager | 100.0% | 100.0% | 0.0% | 26 |
| Royal TS / Royal TSX | 100.0% | 100.0% | 0.0% | 26 |
| Electerm | 100.0% | 100.0% | 0.0% | 19 |
| Tabby | 100.0% | 100.0% | 0.0% | 21 |
| SecureCRT | 100.0% | 100.0% | 0.0% | 19 |
| Xshell | 100.0% | 100.0% | 0.0% | 19 |
| Bitvise SSH Client | 100.0% | 100.0% | 0.0% | 9 |
| PuTTY | 100.0% | 100.0% | 0.0% | 11 |
| KiTTY | 100.0% | 100.0% | 0.0% | 12 |
| SuperPuTTY | 100.0% | 100.0% | 0.0% | 14 |
| Solar-PuTTY | 100.0% | 100.0% | 0.0% | 12 |
| MTPuTTY | 100.0% | 100.0% | 0.0% | 14 |
| Windows Terminal + OpenSSH | 100.0% | 100.0% | 0.0% | 17 |
| WinSCP | 100.0% | 100.0% | 0.0% | 10 |
| Apache Guacamole | 100.0% | 100.0% | 0.0% | 10 |
| XPipe | 100.0% | 100.0% | 0.0% | 16 |
| Muon SSH | 100.0% | 100.0% | 0.0% | 11 |
| ConEmu (with Cygwin / MSYS2 / SSH) | 100.0% | 100.0% | 0.0% | 12 |
| Cmder | 100.0% | 100.0% | 0.0% | 11 |
| Warp (macOS/Linux, Windows coming) | 100.0% | 100.0% | 0.0% | 12 |
| Hyper | 100.0% | 100.0% | 0.0% | 8 |
| X410 + any terminal (e.g., Windows Terminal, Alacritty) | 100.0% | 100.0% | 0.0% | 7 |
| Xming (or VcXsrv) + PuTTY / mRemoteNG | 100.0% | 100.0% | 0.0% | 10 |
| **Overall** | **100.0%** | **82.4%** | **17.6%** | **44** |

Each product target uses declared product-ready evidence overrides for tested, release-supported adapter/CLI/GUI workflows. The overall row keeps the default unique-feature maturity score across the repository.

Run:

```bash
row features --coverage
row features --coverage --json
```

| Feature family | MobaXterm | Remmina | mRemoteNG | Terminator | Termius | Project coverage |
|---|---:|---:|---:|---:|---:|---|
| SSH terminal sessions | ✅ | ✅ | ✅ | local shell | ✅ | Built-in OpenSSH adapter + profile store |
| RDP | ✅ | ✅ | ✅ | — | — | MSTSC/FreeRDP adapter |
| VNC | ✅ | ✅ | ✅ | — | — | TigerVNC/RealVNC adapter |
| SFTP/SCP/FTP file transfer | ✅ | profile/file features | — | — | ✅ | OpenSSH SFTP/SCP adapter + `row files` batch operations, transfer queues, previews, GUI SFTP pane |
| Telnet/rlogin/rsh/raw sockets | ✅ | limited/plugins | ✅ | — | Telnet | External command adapters |
| Mosh | ✅ | plugins | — | — | ✅ | Mosh adapter |
| X11 forwarding / X server workflow | ✅ | X/SSH workflows | — | — | SSH forwarding | SSH `-X/-Y` + VcXsrv/XQuartz/Xorg helper notes |
| SPICE/X2Go/XDMCP | XDMCP | ✅ | — | — | — | virt-viewer/x2goclient/XDMCP adapters |
| ICA/Citrix | — | plugins | ✅ | — | — | `wfica` adapter |
| Session manager / groups / tags | ✅ | ✅ | ✅ | profiles | ✅ | JSON profile store, groups, tags, GUI profile editor |
| Tabs and split panes | ✅ | ✅ | ✅ | ✅ | multi-session | GUI shell + executable saved layouts and editor |
| Broadcast input / command fanout | macros/tools | — | — | ✅ | snippets | Broadcast/fanout CLI with per-target result reporting |
| Macros / snippets | ✅ | — | — | shortcuts | ✅ | Snippet model and manifest entries |
| Encrypted vault | passwords | password store | credential store | — | ✅ | Optional cryptography-based local vault |
| Cloud/team sync | shared sessions | — | shared config options | — | ✅ | Export/import + mounted/shared-directory provider |
| Keygen / SSH keys / agent | SSH keys | SSH keys | PuTTY keys | — | ✅ | OpenSSH keygen CLI |
| Hardware/FIDO keys | SSH support | SSH support | depends | — | ✅ | OpenSSH security-key keygen adapter |
| Portable mode | ✅ | packages | config portability | — | mobile/desktop | `ROW_HOME` portable data directory |
| Web/mobile access | — | Kasm/container options | — | — | ✅ | Static Web/PWA shell + Android/PWA docs |
| Plugin architecture | plugins | plugins | extensions | plugins | integrations | Python entry-point plugin loader |

See [`docs/FULL_FEATURE_COVERAGE.md`](docs/FULL_FEATURE_COVERAGE.md) and [`configs/feature_manifest.json`](configs/feature_manifest.json) for the full coverage manifest.

---

## Platform Support

| Platform | Target mode | Notes |
|---|---|---|
| Windows 10/11 | CLI, GUI, Web/PWA | Native x86, x64 and ARM64 release targets; OpenSSH, MSTSC, PuTTY, VcXsrv, TigerVNC adapters |
| Windows 8.1 | CLI/Web best effort, remote target | Source install depends on a compatible Python stack; remote management through RDP/VNC/SSH/Telnet/serial/raw sockets |
| Windows 8/7 | Legacy source-only, remote target | Keep as managed endpoints; modern native runtime support requires a separate legacy dependency stack |
| Windows Vista/XP | Remote target only | Connect through external clients when protocols can still be negotiated; no modern native Python/PyQt installer |
| Windows Server 2012–2025 | CLI, GUI optional, Web/PWA | Works well as an operator jump host; x86/x64/ARM64 depends on runner and Python availability |
| Linux | CLI, GUI, Web/PWA | Native i386, x86_64, armhf and arm64 package mappings; OpenSSH, FreeRDP, TigerVNC, Remmina-compatible clients, Xorg |
| Unix | CLI, Web/PWA, GUI where Qt is available | POSIX shell and OpenSSH first |
| FreeBSD/OpenBSD/NetBSD/DragonFlyBSD | CLI, Web/PWA, GUI where PyQt6 is packaged | External protocol tools vary by ports/pkg availability |
| Solaris/illumos | CLI, Web/PWA, GUI if Python/Qt stack exists | Focus on OpenSSH, browser, serial/raw sockets |
| macOS Intel/Apple Silicon | CLI, GUI, Web/PWA | OpenSSH, XQuartz, Microsoft Remote Desktop/FreeRDP, VNC viewers |
| Android | Web/PWA, Termux CLI | ARMv7 and ARM64 through Termux/Web; APK remains future work |
| Web | PWA shell | Static PWA shell; API/backend can be layered on |

---

## Architecture

```text
remote-ops-workspace/
├── src/remote_ops_workspace/     # Python core, CLI, GUI shell, vault, launchers
├── apps/web/                     # Static Web/PWA workspace
├── configs/                      # Example profiles, settings, feature and platform target manifests
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
- `row vault get` requires explicit `--show` or `--out`; secrets are not printed by default.
- `row keygen --passphrase-env` keeps software-key passphrases out of `ssh-keygen` argv by generating encrypted keys in-process.
- Launchers validate hosts, ports, URLs, snippets, broadcast payloads and X11 display names before starting external tools.
- Prefer SSH `proxy_jump`; `proxy_command` requires explicit `allow_unsafe_proxy_command=true`.
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

Create local release bundles for the advertised targets:

```bash
python scripts/make_release.py
```

The GitHub release workflow runs on tags like `v0.1.0` and uploads these assets:

| Target | Asset |
|---|---|
| Python wheel | `remote_ops_workspace-0.1.0-py3-none-any.whl` |
| Python sdist | `remote_ops_workspace-0.1.0.tar.gz` |
| Source | `remote-ops-workspace-v0.1.0-source.zip` |
| Windows | `remote-ops-workspace-v0.1.0-windows.zip` |
| Linux | `remote-ops-workspace-v0.1.0-linux.tar.gz` |
| macOS | `remote-ops-workspace-v0.1.0-macos.tar.gz` |
| BSD | `remote-ops-workspace-v0.1.0-bsd.tar.gz` |
| Solaris/illumos | `remote-ops-workspace-v0.1.0-solaris.tar.gz` |
| Android/Termux | `remote-ops-workspace-v0.1.0-android-termux.tar.gz` |
| Web/PWA | `remote-ops-workspace-v0.1.0-web-pwa.zip` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>-setup.exe` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>.msi` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>-native.zip` |
| macOS native | `remote-ops-workspace-v0.1.0-macos-<arch>.dmg` |
| macOS native | `remote-ops-workspace-v0.1.0-macos-<arch>.pkg` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<i386\|amd64\|armhf\|arm64>.deb` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<i686\|x86_64\|armv7hl\|aarch64>.rpm` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<i686\|x86_64\|armhf\|aarch64>.AppImage` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<i686\|x86_64\|armhf\|aarch64>-native.tar.gz` |
| Manifests | `remote-ops-workspace-v0.1.0-*-manifest.json` |

Native protocol rendering still depends on the external clients installed on the target system.
Windows XP/Vista/7/8 are supported as legacy remote targets, not as first-class
modern native operator hosts. The native build scripts add x86, x64, ARM64,
i386/i686, armhf and arm64 artifact mappings where a matching builder exists.

Release phases:

| Phase | Release assets | Status |
|---|---|---|
| 1 | Python wheel/sdist plus zip/tar.gz target bundles | Active |
| 2 | Windows `.exe`, `.msi`, and portable `.zip` | Active |
| 3 | macOS `.dmg` and `.pkg` | Active |
| 4 | Linux `.deb`, `.rpm`, AppImage, and native tarball | Active |

See [`docs/RELEASE_STRATEGY.md`](docs/RELEASE_STRATEGY.md).

---

## License

MIT. See [`LICENSE`](LICENSE).
