# Full Feature Coverage Manifest

Remote Ops Workspace targets **100% public feature-family mapping** and **100% adapter-ready coverage** for the requested product feature families.

The project publishes separate generated scores from `configs/feature_manifest.json`. Feature-family mapping answers whether each public feature family is represented by built-in code, external-client adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Adapter-ready coverage counts implemented adapter, optional, CLI, GUI and combined workflows as ready when they are tied to executable evidence. Production-parity coverage is deliberately stricter: adapter-backed, optional, CLI-only, GUI-only and shell-backed rows remain partial until they become complete integrated native workflows. Platform verified readiness is separate from feature coverage so native release targets, Termux/Web bundles and legacy Windows support do not get blended into one misleading product score.

## Current coverage score

| Product target | Feature-family mapping | Adapter-ready coverage | Production-parity coverage | Parity gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|---:|
| MobaXterm | 100.0% | 100.0% | 80.8% | 19.2% | 25 |
| Remmina | 100.0% | 100.0% | 80.5% | 19.5% | 11 |
| mRemoteNG | 100.0% | 100.0% | 82.3% | 17.7% | 15 |
| Terminator | 100.0% | 100.0% | 89.4% | 10.6% | 8 |
| Termius | 100.0% | 100.0% | 82.6% | 17.4% | 21 |
| Devolutions Remote Desktop Manager | 100.0% | 100.0% | 81.5% | 18.5% | 26 |
| Royal TS / Royal TSX | 100.0% | 100.0% | 81.5% | 18.5% | 26 |
| Electerm | 100.0% | 100.0% | 85.3% | 14.7% | 19 |
| Tabby | 100.0% | 100.0% | 84.3% | 15.7% | 21 |
| SecureCRT | 100.0% | 100.0% | 82.6% | 17.4% | 19 |
| Xshell | 100.0% | 100.0% | 82.6% | 17.4% | 19 |
| Bitvise SSH Client | 100.0% | 100.0% | 82.2% | 17.8% | 9 |
| PuTTY | 100.0% | 100.0% | 79.5% | 20.5% | 11 |
| KiTTY | 100.0% | 100.0% | 80.0% | 20.0% | 12 |
| SuperPuTTY | 100.0% | 100.0% | 81.1% | 18.9% | 14 |
| Solar-PuTTY | 100.0% | 100.0% | 82.5% | 17.5% | 12 |
| MTPuTTY | 100.0% | 100.0% | 81.1% | 18.9% | 14 |
| Windows Terminal + OpenSSH | 100.0% | 100.0% | 84.4% | 15.6% | 17 |
| WinSCP | 100.0% | 100.0% | 86.5% | 13.5% | 10 |
| Apache Guacamole | 100.0% | 100.0% | 82.5% | 17.5% | 10 |
| XPipe | 100.0% | 100.0% | 83.8% | 16.2% | 16 |
| Muon SSH | 100.0% | 100.0% | 81.8% | 18.2% | 11 |
| ConEmu (with Cygwin / MSYS2 / SSH) | 100.0% | 100.0% | 90.0% | 10.0% | 12 |
| Cmder | 100.0% | 100.0% | 89.1% | 10.9% | 11 |
| Warp (macOS/Linux, Windows coming) | 100.0% | 100.0% | 85.8% | 14.2% | 12 |
| Hyper | 100.0% | 100.0% | 89.4% | 10.6% | 8 |
| X410 + any terminal (e.g., Windows Terminal, Alacritty) | 100.0% | 100.0% | 82.1% | 17.9% | 7 |
| Xming (or VcXsrv) + PuTTY / mRemoteNG | 100.0% | 100.0% | 77.5% | 22.5% | 10 |
| **Overall** | **100.0%** | **100.0%** | **82.4%** | **17.6%** | **44** |

## Platform verified readiness

| Target | Platform | Channel | Verified readiness | Gap to 100% | Status |
|---|---|---|---:|---:|---|
| windows-x86 | Windows x86 | default-native | 100.0% | 0.0% | verified-default-native |
| windows-x64 | Windows x64 | default-native | 100.0% | 0.0% | verified-default-native |
| windows-arm64 | Windows arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| linux-i386 | Linux i386 | manual-script-native | 70.0% | 30.0% | manual-script-supported |
| linux-x86_64 | Linux x86_64 | default-native | 100.0% | 0.0% | verified-default-native |
| linux-armhf | Linux armhf | manual-script-native | 70.0% | 30.0% | manual-script-supported |
| linux-arm64 | Linux arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| macos-x64 | macOS x64 | default-native | 100.0% | 0.0% | verified-default-native |
| macos-arm64 | macOS arm64 | default-native | 100.0% | 0.0% | verified-default-native |
| android-armv7 | Android/Termux armv7 | default-termux-web | 85.0% | 15.0% | termux-web-default |
| android-arm64 | Android/Termux arm64 | default-termux-web | 85.0% | 15.0% | termux-web-default |
| Windows 8.1 | Windows legacy | legacy-windows | 60.0% | 40.0% | best-effort-source-host |
| Windows 8 | Windows legacy | legacy-windows | 45.0% | 55.0% | legacy-source-only |
| Windows 7 | Windows legacy | legacy-windows | 45.0% | 55.0% | legacy-source-only |
| Windows Vista | Windows legacy | legacy-windows | 25.0% | 75.0% | remote-target-only |
| Windows XP | Windows legacy | legacy-windows | 25.0% | 75.0% | remote-target-only |
| **Overall** | **All targets** | **mixed** | **75.6%** | **24.4%** | **mixed readiness** |

Generate the same numbers locally:

```bash
row features --coverage
row features --coverage --json
```

## Scoring method

Coverage can be one of:

- **implemented**: working code exists in this repo;
- **implemented-adapter**: working command builder exists and delegates to an external client;
- **implemented-optional**: working code exists when an optional dependency is installed;
- **implemented-cli / implemented-gui / implemented-cli-gui**: working user-facing CLI, GUI, or combined workflow exists;
- **implemented-shell**: working shell exists for the named interface;
- **plugin-seam / adapter-seam / docs-adapter**: feature is mapped to an extension point and documented integration path.

Feature-family mapping weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 1.00 |
| implemented-cli | 1.00 |
| implemented-gui | 1.00 |
| implemented-adapter | 1.00 |
| implemented-optional | 1.00 |
| implemented-shell | 1.00 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Adapter-ready coverage weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 1.00 |
| implemented-cli | 1.00 |
| implemented-gui | 1.00 |
| implemented-adapter | 1.00 |
| implemented-optional | 1.00 |
| implemented-shell | 1.00 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Production-parity coverage weights:

| Status | Weight |
|---|---:|
| implemented | 1.00 |
| implemented-cli-gui | 0.90 |
| implemented-cli | 0.85 |
| implemented-gui | 0.85 |
| implemented-adapter | 0.75 |
| implemented-optional | 0.75 |
| implemented-shell | 0.45 |
| gui-shell | 0.40 |
| adapter-seam | 0.25 |
| docs-adapter | 0.20 |
| plugin-seam | 0.20 |
| manifest-seam | 0.15 |
| script-seam | 0.15 |

Every feature record also exposes generated evidence in `row features --coverage --json`, including feature id, status, implementation kind, product mapping and manifest extension point. `scripts/check_feature_reality.py` separately verifies implemented feature families against executable evidence such as CLI parser command paths, launch-plan builders, implementation symbols and shipped PWA/Termux files.

Adapter-ready coverage uses the manifest status weights directly and does not
use blanket per-product overrides. Production-parity coverage deliberately
uses stricter weights so adapter-backed, optional, CLI-only and GUI-only rows
do not imply full native commercial-product equivalence before that work is
implemented.

## Product feature family mapping

### MobaXterm-style families

- Tabbed SSH terminal workflow.
- SFTP/SCP/FTP file transfer profiles, `row files` SFTP browser actions, transfer queues and local/remote previews.
- RDP, VNC, Telnet, rlogin, rsh, Mosh, XDMCP and raw network tool launchers.
- Per-protocol launch options for OpenSSH, Mosh, RDP, VNC and serial console adapters.
- X11 forwarding workflow through OpenSSH `-X`/`-Y`.
- External X server helper path for VcXsrv, XQuartz and Xorg.
- Macros/snippets CLI.
- Portable mode through `ROW_HOME`.
- Network toolbox CLI.

### Remmina-style families

- RDP, VNC, SSH, SPICE and X2Go launchers.
- RDP, VNC, SPICE and X2Go viewer option mapping through native client argv.
- Profile grouping and tags.
- GUI profile editor backed by the shared profile store.
- Remmina profile import from `.remmina` files and directories.
- SSH tunneling model.
- Plugin architecture for protocols and features.
- Cross-distro Linux/Unix packaging scripts.

### mRemoteNG-style families

- Connection tree via groups and tags.
- GUI profile editing for quick connection updates.
- RDP, VNC, ICA, SSH, Telnet, HTTP/HTTPS, rlogin and raw socket launchers.
- Per-connection RDP display/security/device options and SSH adapter options.
- Quick connect through CLI/GUI.
- Import/export profile bundles.
- mRemoteNG `confCons.xml` import for nested connection trees.
- Group inheritance through group-level profile defaults.
- Credential store through the local vault.

### Terminator-style families

- Tabs.
- Horizontal and vertical process-backed split-pane UI shell.
- Saved layout/profile CLI and GUI opener.
- GUI layout editor for profile and command panes.
- Keyboard shortcuts.
- Broadcast/fanout command CLI with per-target result reporting.
- Plugin architecture.

### Termius-style families

- SSH, Mosh, Telnet, SFTP browser and port-forwarding models.
- SSH keepalive/proxy/host-key options and Mosh port/prediction options.
- Hosts, groups and tags.
- Local encrypted vault.
- Snippets/macros CLI.
- SSH keygen and FIDO/security-key adapters through OpenSSH.
- Local export/import and mounted/shared-directory sync provider.
- Termius-style JSON host import for local migration.
- SFTP queued transfer and preview workflow for SSH hosts.
- Desktop, Web/PWA and Android/Termux workflows.

## Current implementation status

The current v0.1.0 repo is an adapter-first foundation, not a proprietary clone. It has working profile storage, command generation, dry-run inspection, external process launch, doctor checks, optional encrypted vault, audit log, snippets/macros, saved layouts that can be launched from CLI or opened and edited in the GUI, broadcast/fanout commands with per-target results, protocol-specific launch option builders, profile importers for common external exports, SSH keygen/FIDO adapters, SFTP batch file operations, transfer queues and previews, GUI SFTP panes, network toolbox commands, mounted-directory sync, Web/PWA shell and PyQt6 GUI shell with process-backed terminal panes.

For each requested product target, the repository maps every tracked public
feature family and the implemented rows now score as adapter-ready under the
adapter-first readiness contract. Full production parity is lower by design:
deep embedded protocol rendering, proprietary vendor cloud services, native
Android packaging and advanced PTY/terminal emulation still need to evolve
behind the existing adapter and plugin boundaries before they can honestly be
called complete product-level parity.
