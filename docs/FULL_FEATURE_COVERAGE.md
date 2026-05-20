# Full Feature Coverage Manifest

Remote Ops Workspace targets 100% coverage of the public feature **families** represented by MobaXterm, Remmina, mRemoteNG, Terminator and Termius. Coverage can be one of:

- **implemented**: working code exists in this repo;
- **implemented-adapter**: working command builder exists and delegates to an external client;
- **implemented-optional**: working code exists when an optional dependency is installed;
- **gui-shell / implemented-shell**: UI shell exists and is ready for deeper embedded engines;
- **plugin-seam / adapter-seam / docs-adapter**: feature is mapped to an extension point and documented integration path.

## Product feature family mapping

### MobaXterm-style families

- Tabbed SSH terminal workflow.
- SFTP/SCP/FTP file transfer profiles.
- RDP, VNC, Telnet, rlogin, rsh, Mosh, XDMCP and raw network tool launchers.
- X11 forwarding workflow through OpenSSH `-X`/`-Y`.
- External X server helper path for VcXsrv, XQuartz and Xorg.
- Macros/snippets seam.
- Portable mode through `ROW_HOME`.
- Network toolbox seam through scripts and plugins.

### Remmina-style families

- RDP, VNC, SSH, SPICE and X2Go launchers.
- Profile grouping and tags.
- SSH tunneling model.
- Plugin architecture for protocols and features.
- Cross-distro Linux/Unix packaging scripts.

### mRemoteNG-style families

- Connection tree via groups and tags.
- RDP, VNC, ICA, SSH, Telnet, HTTP/HTTPS, rlogin and raw socket launchers.
- Quick connect through CLI/GUI.
- Import/export profile bundles.
- Group inheritance seam for future policy defaults.
- Credential store seam through the local vault.

### Terminator-style families

- Tabs.
- Horizontal and vertical split-pane UI shell.
- Layout/profile manifest seam.
- Keyboard shortcut seam.
- Broadcast input seam.
- Plugin architecture.

### Termius-style families

- SSH, Mosh, Telnet, SFTP and port-forwarding models.
- Hosts, groups and tags.
- Local encrypted vault.
- Snippets/macros seam.
- SSH keygen and FIDO/security-key seam through OpenSSH and future plugins.
- Local export/import and cloud/team sync provider seam.
- Desktop, Web/PWA and Android/Termux workflows.

## Current implementation status

The current v0.1.0 repo is a production-minded foundation, not a proprietary clone. It has real profile storage, command generation, dry-run inspection, external process launch, doctor checks, optional encrypted vault, audit log, Web/PWA shell and PyQt6 GUI shell.

Deep embedded protocol rendering, proprietary cloud sync, native Android packaging and advanced terminal emulation are represented as documented plugin seams so the project can evolve without rewriting the core.
