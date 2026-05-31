# Roadmap

## v0.1.x

- Harden CLI profile workflows.
- Ship Phase 1 release artifacts: Python wheel/sdist plus zip/tar.gz target bundles.
- Ship Phase 2 Windows native installers (`.exe`, `.msi`) from CI.
- Ship Phase 3 macOS native packages (`.dmg`, `.pkg`) from CI.
- Ship Phase 4 Linux native packages (`.deb`, `.rpm`, AppImage) from CI.
- Add group inheritance defaults.
- Add snippets command group.
- Add profile importers for Remmina, mRemoteNG, Termius-style JSON and MobaXterm session exports.
- Continue enriching GUI profile and layout editors with protocol presets and import previews.

## v0.2.x

- Deeper terminal widget plugin using qtermwidget or PTY/web terminal emulation.
- Continue enriching embedded file transfer UI with live transfer progress after queue/preview support.
- Richer layout save/restore with resize persistence.
- SSH key helper and local key generation workflow.
- Sync provider interface.
- Add install, upgrade and uninstall smoke tests for native packages.
- Add release signing support for Windows Authenticode and macOS Developer ID.

## v0.3.x

- Team sync backend proof-of-concept.
- Browser API backend.
- Add Apple notarization for macOS distribution.
- Add hosted or self-hosted 32-bit Linux and ARMv7 release runners for already declared native package mappings.
- Android PWA packaging; keep APK publishing gated on a real native Android wrapper.
- More protocol plugins.
