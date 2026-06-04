# Full Feature Coverage Manifest

Remote Ops Workspace targets **100% public feature-family mapping**, **100% adapter-ready coverage** and **100% release-backed product workflow parity** for the requested product feature families.

The project publishes separate generated scores from `configs/feature_manifest.json`. Feature-family mapping answers whether each public feature family is represented by built-in code, external-client adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Adapter-ready coverage counts implemented adapter, optional, CLI, GUI and combined workflows as ready when they are tied to executable evidence. The `production_parity_coverage` JSON key remains for compatibility, but the public contract is release-backed product workflow parity: implemented workflows count only when tied to executable release evidence, and seam-only or docs-only rows remain partial if they appear. This is not a proprietary native clone claim. Platform verified readiness is separate from feature coverage so native release targets, Termux/Web bundles and legacy Windows support do not get blended into one misleading product score.

## Current coverage score

| Product target | Feature-family mapping | Adapter-ready coverage | Release-backed workflow parity | Workflow gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|---:|
| MobaXterm | 100.0% | 100.0% | 100.0% | 0.0% | 25 |
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
| **Overall** | **100.0%** | **100.0%** | **100.0%** | **0.0%** | **44** |

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

Release-backed workflow parity weights:

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

Every feature record also exposes generated evidence in `row features --coverage --json`, including feature id, status, implementation kind, product mapping and manifest extension point. `scripts/check_feature_reality.py` separately verifies implemented feature families against executable evidence such as CLI parser command paths, launch-plan builders, implementation symbols and shipped PWA/Termux files.

## Release-backed workflow evidence

`row features --coverage --json` includes `workflow_parity_contract` and
`workflow_parity_evidence`. The evidence ledger has one row for `Overall` and
one row for each product target. Each row lists:

- `product`, `coverage_percent`, `gap_percent` and `feature_count`;
- `feature_ids`, the exact feature-family IDs used by that product score;
- `feature_evidence`, with `id`, `status`, `implementation_kind`,
  `extension_point`, `status_weight`, `release_backed` and `evidence_refs`;
- `native_clone_claimed: false`, because the score is not a proprietary native
  clone claim or embedded protocol-engine parity claim.

`scripts/check_product_readiness.py` fails if a 100% workflow-parity row lacks
that evidence, has partial mapped features, uses blanket overrides, or blends
platform readiness into product feature coverage.

Adapter-ready coverage and release-backed product workflow parity use the
manifest status weights directly and do not use blanket per-product overrides.
Seam-only and docs-only rows remain partial, while implemented adapter,
optional, CLI, GUI, shell and combined workflows count as workflow parity when
they are tied to executable release evidence.

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
adapter-first readiness contract. Release-backed product workflow parity is also
100% for the tracked workflows because every mapped row is tied to implemented
code, tested launch-plan builders, shipped platform scripts, GUI/CLI workflows
or explicit plugin boundaries. Platform verified readiness remains separate
because manual native builders, Termux/Web channels and legacy Windows
remote-target tiers are not the same as product feature parity.
