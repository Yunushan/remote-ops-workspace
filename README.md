<div align="center">

# Remote Ops Workspace

### Operator-first remote terminal and connection workspace for SSH, RDP, VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, serial consoles, raw sockets, split panes, vaults, snippets, sync, CLI, GUI and Web/PWA.

![build](https://img.shields.io/badge/build-source--available-brightgreen)
![release](https://img.shields.io/badge/release-v1.0.2-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![runtime](https://img.shields.io/badge/runtime-Python%203.10--3.14-orange)
![interfaces](https://img.shields.io/badge/interfaces-CLI%20%7C%20GUI%20%7C%20Web-purple)
![targets](https://img.shields.io/badge/targets-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20BSD%20%7C%20Solaris%20%7C%20Android%20%7C%20Web-green)
![protocols](https://img.shields.io/badge/protocols-SSH%20%7C%20RDP%20%7C%20VNC%20%7C%20SFTP%20%7C%20Mosh%20%7C%20Telnet%20%7C%20SPICE%20%7C%20X2Go-yellow)

[Visual Overview](#visual-overview) • [Quick Start](#quick-start) • [CLI](#cli) • [GUI](#gui) • [Web/PWA](#webpwa) • [Feature Coverage](#feature-coverage) • [Platforms](#platform-support) • [Architecture](#architecture) • [Security](#security) • [License](#license)

English • [Türkçe](README.tr.md)

<br>

<img src="artifacts/readme/remote-ops-hero.png" alt="Remote Ops Workspace enterprise GUI overview showing protocol chips, feature counts and a dense operator console preview" width="100%">

</div>

---

## What this project is

**Remote Ops Workspace** is a MIT-licensed, cross-platform remote access workspace designed as an open foundation for the feature families people expect from MobaXterm, Remmina, mRemoteNG, Terminator and Termius.

It is intentionally built as an **adapter-first foundation**: the repo includes a working CLI, profile store, launcher command builders, optional encrypted vault support, GUI shell, Web/PWA shell, feature coverage manifest, tests, installers, CI and release scaffolding. Deep protocol rendering is delegated to native system tools such as OpenSSH, FreeRDP, TigerVNC, x2goclient, virt-viewer, PuTTY, Windows MSTSC, XQuartz/VcXsrv/Xorg, or future embedded protocol plugins.

> Not affiliated with Mobatek/MobaXterm, Remmina, mRemoteNG, GNOME Terminator, or Termius. Product names are used only to describe compatibility goals and feature coverage targets.

---

## Visual Overview

Generated README media lives in [`artifacts/readme`](artifacts/readme) and is built from the same tracked static GUI preview assets used by [`docs/GUI_DESIGN.md`](docs/GUI_DESIGN.md). They show the shipped workspace surfaces and feature flows in a deterministic gallery, while `python scripts/check_real_gui_render.py --out-dir artifacts/gui-real` captures the real PyQt6 window when the desktop extra is installed.

<p align="center">
  <img src="artifacts/readme/gui-preset-tour.gif" alt="Animated tour of Remote Ops Workspace GUI presets including Native, MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style" width="100%">
</p>

<p align="center">
  <img src="artifacts/readme/feature-workflow-tour.gif" alt="Animated feature workflow tour showing quick connect, split terminal panes, SFTP queue previews, vault audit safety and coverage metrics" width="100%">
</p>

<p align="center">
  <img src="artifacts/gui-design-previews/all-gui-designs-contact-sheet.png" alt="All GUI design presets contact sheet" width="100%">
</p>

Regenerate the README media and GUI previews with:

```bash
python scripts/render_gui_design_previews.py
python scripts/render_readme_media.py
python scripts/check_readme_media.py
python scripts/check_real_gui_render.py
```

---

## Quick Start

```bash
git clone https://github.com/Yunushan/remote-ops-workspace.git
cd remote-ops-workspace

python -m venv .venv
# Linux/macOS/BSD/Solaris
. .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install -e ".[desktop,security]"
row init
row welcome
row profile add --name lab-ssh --protocol ssh --host ssh.example.invalid --username admin
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
row welcome
row profile add --name core-rdp --protocol rdp --host rdp.example.invalid --username administrator
row profile add --name switch-console --protocol serial --path /dev/ttyUSB0 --option baud=115200
row profile add --name jump-ssh --protocol ssh --host ssh.example.invalid --username admin --option proxy_jump=bastion --option keepalive_interval=30
row profile add --name lab-vnc --protocol vnc --host vnc.example.invalid --option fullscreen=true --option shared=true
row profile list
row profile show core-rdp
row connect core-rdp --dry-run
row connect core-rdp
row features
row platforms
row vault init
row vault status
row vault set prod/router-password --secret-env ROW_ROUTER_PASSWORD
row vault list
row vault delete old/router-password --force
row plugins list
row plugins validate
row plugins scaffold --out ./row-demo-plugin --name row-demo-plugin --module row_demo_plugin --protocol demo --client demo-client
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

Profiles are normalized and validated before storage, import results, GUI edits and launch planning. The launcher never concatenates shell strings. Protocol launches are built as safe argument arrays and can be inspected with `--dry-run` before execution. Per-protocol profile options cover OpenSSH keepalives/proxies/host-key policy, Mosh ports/prediction, RDP display/security/device flags, VNC/SPICE/X2Go viewer flags and serial line settings; see [`docs/PROTOCOLS.md`](docs/PROTOCOLS.md).

Profile imports support the native ROW bundle plus Remmina `.remmina`, mRemoteNG `confCons.xml`, Termius-style JSON host lists and MobaXterm session bookmark exports. See [`docs/IMPORTERS.md`](docs/IMPORTERS.md). File transfer queues, previews and `--force` requirements for destructive SFTP actions are documented in [`docs/FILE_TRANSFER.md`](docs/FILE_TRANSFER.md). Protocol plugin scaffolding and validation are documented in [`docs/PLUGIN_DEVELOPMENT.md`](docs/PLUGIN_DEVELOPMENT.md).

---

## GUI

The PyQt6 desktop shell provides:

- session tree and quick-connect panel;
- profile create/edit/remove dialogs backed by the same profile store as the CLI;
- external protocol launch buttons;
- interactive SFTP file browser panes and transfer queue preview dialog for SSH/SFTP profiles;
- tabbed workspace for process-backed sessions with close confirmation and cleanup;
- process-backed terminal panes with stdout/stderr capture, stdin entry and managed start/stop state;
- horizontal and vertical split-pane shells inspired by tiling terminals;
- selectable GUI view presets: Native, MobaXterm-style, SecureCRT-style, Termius-style, Remmina-style and mRemoteNG-style, with reproducible static previews and live PyQt6 render smoke checks documented in [`docs/GUI_DESIGN.md`](docs/GUI_DESIGN.md);
- saved layout selector plus create/edit/remove dialogs that open layout panes directly in the workspace;
- doctor/status panel;
- protocol launch plugin discovery through Python entry points plus `row plugins list` and `row plugins validate`;
- future extension seams for deeper PTY/qtermwidget/web terminal emulation.

Install optional GUI extras:

```bash
pip install -e ".[desktop,security]"
row gui
```

Windows native portable packages for x64 and ARM64 include a double-clickable
GUI launcher:

```text
Remote Ops Workspace GUI.exe
```

The same portable zips also keep `bin\row-gui.exe` and `bin\row.exe` for
scripted workflows. The 32-bit Windows x86 native package is CLI-first because
PyQt6 does not publish 32-bit Windows wheels.

---

## Web/PWA

`apps/web` contains a static browser workspace that can run as a PWA. It is useful for Android/browser workflows, documentation demos and future API integration.

```bash
row serve-web --host 127.0.0.1 --port 8765
```

Then open the displayed URL from a browser or install it as a PWA. Binding to
`0.0.0.0`, `::` or another non-loopback interface requires
`--allow-public-bind`; use it only on trusted networks or inside the hardened
Docker entrypoint. The compose file publishes the container on
`127.0.0.1:8765` by default.

---

## Feature Coverage

Coverage target: **100% public feature-family mapping**, **100% adapter-ready coverage** and **100% release-backed product workflow parity** for the requested tools. Per-platform release readiness is tracked separately so manual architecture builds and legacy Windows remote-target tiers remain visible.

Coverage is generated from [`configs/feature_manifest.json`](configs/feature_manifest.json). Feature-family mapping answers whether each public feature family is represented by built-in code, external adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Adapter-ready coverage counts implemented adapter, optional, CLI, GUI and combined workflows as ready when they are tied to executable evidence. The `production_parity_coverage` JSON key is kept for compatibility, but the public contract is release-backed product workflow parity: implemented workflows count only when tied to executable release evidence, and seam-only or docs-only rows remain partial if they appear. This is not a proprietary native clone claim. The verifier runs both `scripts/check_feature_reality.py` and `scripts/check_product_readiness.py` so coverage claims stay tied to real CLI command paths, launch-plan builders, implementation symbols, shipped files and visible platform gaps.

| Product target | Feature-family mapping | Adapter-ready coverage | Release-backed workflow parity | Workflow gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|---:|
| MobaXterm | 100.0% | 100.0% | 100.0% | 0.0% | 30 |
| Remmina | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| mRemoteNG | 100.0% | 100.0% | 100.0% | 0.0% | 15 |
| Terminator | 100.0% | 100.0% | 100.0% | 0.0% | 8 |
| Termius | 100.0% | 100.0% | 100.0% | 0.0% | 21 |
| Devolutions Remote Desktop Manager | 100.0% | 100.0% | 100.0% | 0.0% | 26 |
| Royal TS / Royal TSX | 100.0% | 100.0% | 100.0% | 0.0% | 26 |
| Electerm | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Tabby | 100.0% | 100.0% | 100.0% | 0.0% | 21 |
| SecureCRT | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Xshell | 100.0% | 100.0% | 100.0% | 0.0% | 19 |
| Bitvise SSH Client | 100.0% | 100.0% | 100.0% | 0.0% | 9 |
| PuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| KiTTY | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| SuperPuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 14 |
| Solar-PuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| MTPuTTY | 100.0% | 100.0% | 100.0% | 0.0% | 14 |
| Windows Terminal + OpenSSH | 100.0% | 100.0% | 100.0% | 0.0% | 17 |
| WinSCP | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| Apache Guacamole | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| XPipe | 100.0% | 100.0% | 100.0% | 0.0% | 16 |
| Muon SSH | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| ConEmu (with Cygwin / MSYS2 / SSH) | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| Cmder | 100.0% | 100.0% | 100.0% | 0.0% | 11 |
| Warp (macOS/Linux, Windows coming) | 100.0% | 100.0% | 100.0% | 0.0% | 12 |
| Hyper | 100.0% | 100.0% | 100.0% | 0.0% | 8 |
| X410 + any terminal (e.g., Windows Terminal, Alacritty) | 100.0% | 100.0% | 100.0% | 0.0% | 7 |
| Xming (or VcXsrv) + PuTTY / mRemoteNG | 100.0% | 100.0% | 100.0% | 0.0% | 10 |
| **Overall** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **49** |

Adapter-ready coverage and release-backed product workflow parity use the manifest status weights directly and do not use blanket per-product overrides. Platform verified readiness is still separate and currently reports **75.6% overall** across default native, manual native, Termux/Web and legacy Windows targets.

Run:

```bash
row features --coverage
row features --coverage --json
```

The JSON report includes `workflow_parity_contract` and `workflow_parity_evidence`. Each evidence row lists the product row, mapped feature IDs, implementation status, implementation kind, manifest extension point and evidence refs used to justify the percentage. That is the source of truth for every 100% workflow-parity row.

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
| Plugin architecture | plugins | plugins | extensions | plugins | integrations | Python entry-point protocol launch plugins + `row plugins list`, `row plugins validate` and `row plugins scaffold` |

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
| Linux | CLI, GUI, Web/PWA | Default GitHub release builds x86_64/amd64 and aarch64/arm64 native packages; i386/i686 and armhf mappings are script-supported on matching builders |
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
5. **Plugin honesty**: protocol launch plugins are wired through entry points and can be validated with `row plugins validate`; broader backend seams stay documented as future work until they have a caller path.

---

## Security

- Do not commit real profiles, passwords, private keys, vault files, or customer hostnames.
- Use `ROW_HOME` for portable/private operator workspaces.
- Store examples only under `configs/*.example.*`.
- Use `row connect NAME --dry-run` before launching newly imported profiles.
- Vault encryption requires the optional `security` extra: `pip install -e ".[security]"`.
- Use `row vault set NAME --secret-env ENV` or `row vault set NAME --stdin` for automation so secret values are not placed in argv or shell history.
- `row vault get` requires explicit `--show` or `--out`; secrets are not printed by default.
- `row keygen --passphrase-env` keeps software-key passphrases out of `ssh-keygen` argv by generating encrypted keys in-process.
- Shared profile validation checks protocol names, required targets, hosts, ports and URLs; command builders also validate snippets, broadcast payloads and X11 display names before starting external tools.
- Destructive SFTP actions, remote-overwrite-prone uploads and local-overwrite downloads are blocked before execution unless an operator passes `--force`; broad delete targets and remote globs are rejected for deletes/renames.
- `row serve-web` binds to loopback by default, adds static-app security headers, disables directory listing and requires `--allow-public-bind` for non-loopback interfaces. The web Docker image runs as a non-root user and compose binds to localhost with dropped Linux capabilities.
- Prefer SSH `proxy_jump`; `proxy_command` requires explicit `allow_unsafe_proxy_command=true`.
- SSHv1 legacy profiles require both `--protocol ssh1`/`sshv1` and `--option allow_insecure_sshv1=true`; protocol v1 remains insecure and should only be used for isolated legacy systems.
- Treat protocol plugins as trusted local Python code; use `row plugins validate` to catch load failures and invalid sample launch plans before using plugin-backed profiles.
- See [`SECURITY.md`](SECURITY.md) and [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md).

---

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[desktop,security,dev]"
python scripts/verify.py
```

Pull-request and push CI runs `python scripts/verify.py --lint` across the
Python/OS matrix, and a dedicated Linux job installs the desktop extra and runs
`python scripts/check_real_gui_render.py --require-pyqt6` against a live
offscreen PyQt6 window. `python scripts/check_ci_workflow.py` keeps those gates
from drifting.

Use `python scripts/verify.py --quick` only for dependency-constrained review
environments where `pytest` is unavailable. See
[`docs/VERIFYING.md`](docs/VERIFYING.md).

Repository cleanup before tagging:

```bash
python scripts/check_repository_cleanup.py
python scripts/check_repository_cleanup.py --require-clean
```

Create local release bundles for the advertised targets:

```bash
python scripts/make_release.py
```

The GitHub release workflow runs on tags like `v1.0.2` and uploads these assets:

| Target | Asset |
|---|---|
| Python wheel | `remote_ops_workspace-1.0.2-py3-none-any.whl` |
| Python sdist | `remote_ops_workspace-1.0.2.tar.gz` |
| Source | `remote-ops-workspace-v1.0.2-source.zip` |
| Windows | `remote-ops-workspace-v1.0.2-windows.zip` |
| Linux | `remote-ops-workspace-v1.0.2-linux.tar.gz` |
| macOS | `remote-ops-workspace-v1.0.2-macos.tar.gz` |
| BSD | `remote-ops-workspace-v1.0.2-bsd.tar.gz` |
| Solaris/illumos | `remote-ops-workspace-v1.0.2-solaris.tar.gz` |
| Android/Termux | `remote-ops-workspace-v1.0.2-android-termux.tar.gz` |
| Web/PWA | `remote-ops-workspace-v1.0.2-web-pwa.zip` |
| Windows native | `remote-ops-workspace-v1.0.2-windows-<x86\|x64\|arm64>-setup.exe` |
| Windows native | `remote-ops-workspace-v1.0.2-windows-<x86\|x64\|arm64>.msi` |
| Windows native | `remote-ops-workspace-v1.0.2-windows-<x86\|x64\|arm64>-native.zip` |
| macOS native | `remote-ops-workspace-v1.0.2-macos-<x64\|arm64>.dmg` |
| macOS native | `remote-ops-workspace-v1.0.2-macos-<x64\|arm64>.pkg` |
| macOS native | `remote-ops-workspace-v1.0.2-macos-<x64\|arm64>-native-manifest.json` |
| Linux native | `remote-ops-workspace-v1.0.2-linux-<amd64\|arm64>.deb` |
| Linux native | `remote-ops-workspace-v1.0.2-linux-<x86_64\|aarch64>.rpm` |
| Linux native | `remote-ops-workspace-v1.0.2-linux-<x86_64\|aarch64>.AppImage` |
| Linux native | `remote-ops-workspace-v1.0.2-linux-<x86_64\|aarch64>-native.tar.gz` |
| Linux native | `remote-ops-workspace-v1.0.2-linux-<x86_64\|aarch64>-native-manifest.json` |
| Manifests | `remote-ops-workspace-v1.0.2-*-manifest.json` |
| Checksums | `remote-ops-workspace-v1.0.2-SHA256SUMS.txt` |

Native protocol rendering still depends on the external clients installed on the target system.
Windows x64 and ARM64 native portable zips include a top-level
`Remote Ops Workspace GUI.exe` double-click launcher, plus `bin\row-gui.exe`;
`bin\row.exe` remains the CLI entry point.
In those frozen Windows packages, `row gui` delegates to the sibling
`bin\row-gui.exe` launcher.
Windows XP/Vista/7/8 are supported as legacy remote targets, not as first-class
modern native operator hosts. The default GitHub workflow builds Windows
`x86`/`x64`/`arm64`, macOS `x64`/`arm64`, and Linux `x86_64`/`aarch64`
native jobs. The native build scripts also map Linux `i386`/`i686` and
`armhf` outputs for matching builders, but those are not uploaded by the
default GitHub release workflow.
The machine-readable release decision lives in
[`configs/release_matrix.json`](configs/release_matrix.json), while
[`configs/platform_targets.json`](configs/platform_targets.json) remains the
broader platform support catalog exposed by `row platforms --json`.
Release manifests include `size_bytes` and `sha256` for each artifact, and CI
build jobs run with read-only checkout credentials until the final publish step.
The release workflow also starts with a `release-preflight` job that runs
`python scripts/verify.py --quick --no-cli-smoke` and
`python scripts/check_repository_cleanup.py --require-clean`; source, native and
publish jobs all depend on that gate.
Before upload, the publish job runs
`python scripts/check_release_publish_assets.py --assets-dir release-assets --tag`
to verify the downloaded asset set, checksum sidecars and release manifest
against `configs/release_matrix.json`.
Python release tooling is constrained by `requirements-release.txt` and recorded
in each release manifest through `configs/release_toolchain.json`. Native
Windows, macOS and Linux jobs also emit per-platform `native-SHA256SUMS.txt`
sidecars for their native artifacts and manifests.
Native installer smoke coverage is declared in
[`configs/native_installer_smoke.json`](configs/native_installer_smoke.json)
and checked by `python scripts/check_native_installer_smoke.py`. The release
workflow runs `scripts/smoke_windows_native.ps1`,
`scripts/smoke_macos_native.sh` and `scripts/smoke_linux_native.sh` after native
builds and before upload, covering install, verify, upgrade and uninstall paths
for `.exe`, `.msi`, `.dmg`, `.pkg`, `.deb`, `.rpm` and AppImage artifacts.

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
