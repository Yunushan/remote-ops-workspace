# Full Feature Coverage Manifest

Remote Ops Workspace targets **100% public feature-family mapping** for the feature families represented by MobaXterm, Remmina, mRemoteNG, Terminator and Termius. Product-ready implementation maturity is tracked as a separate evidence-weighted score.

The project publishes two generated scores from `configs/feature_manifest.json`. Feature-family mapping answers whether each public feature family is represented by built-in code, external-client adapters, optional implementations, CLI/GUI workflows, platform scripts, or plugin extension points. Product-ready coverage applies stricter evidence weights so adapter-backed, optional, shell, script and partial workflows are not overstated.

## Current coverage score

| Product target | Feature-family mapping | Product-ready coverage | Ready gap to 100% | Feature families tracked |
|---|---:|---:|---:|---:|
| MobaXterm | 100.0% | 80.0% | 20.0% | 24 |
| Remmina | 100.0% | 80.5% | 19.5% | 11 |
| mRemoteNG | 100.0% | 82.3% | 17.7% | 15 |
| Terminator | 100.0% | 87.9% | 12.1% | 7 |
| Termius | 100.0% | 82.6% | 17.4% | 21 |
| **Overall** | **100.0%** | **82.0%** | **18.0%** | **43** |

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

Product-ready coverage weights:

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

Every feature record also exposes generated evidence in `row features --coverage --json`, including feature id, status, implementation kind, product mapping and manifest extension point.

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

The current v0.1.0 repo is a production-minded foundation, not a proprietary clone. It has real profile storage, command generation, dry-run inspection, external process launch, doctor checks, optional encrypted vault, audit log, snippets/macros, saved layouts that can be launched from CLI or opened and edited in the GUI, broadcast/fanout commands with per-target results, protocol-specific launch option builders, profile importers for common external exports, SSH keygen/FIDO adapters, SFTP batch file operations, transfer queues and previews, GUI SFTP panes, network toolbox commands, mounted-directory sync, Web/PWA shell and PyQt6 GUI shell with process-backed terminal panes.

Deep embedded protocol rendering, proprietary vendor cloud services, native Android packaging and advanced PTY/terminal emulation can still evolve behind the existing adapter and plugin boundaries without rewriting the core.
