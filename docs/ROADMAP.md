# Roadmap

This roadmap is checked by `scripts/check_roadmap_truth.py` so shipped work
does not remain listed as planned work.

## Completed in v0.1.x

- Hardened CLI profile workflows.
- Shipped Phase 1 release artifacts: Python wheel/sdist plus zip/tar.gz target bundles.
- Shipped Phase 2 Windows native installers (`.exe`, `.msi`) from CI.
- Shipped Phase 3 macOS native packages (`.dmg`, `.pkg`) from CI.
- Shipped Phase 4 Linux native packages (`.deb`, `.rpm`, AppImage) from CI.
- Added group-level profile defaults with inheritance into stored profiles.
- Added snippets command group.
- Added profile importers for Remmina, mRemoteNG, Termius-style JSON and MobaXterm session exports.
- Added SSH key helper and local key generation workflow.
- Added sync provider interface.
- Added install, verify, upgrade and uninstall smoke-test contract for native packages.

## v0.1.x Remaining

- Continue enriching GUI profile and layout editors with protocol presets and import previews.

## v0.2.x

- Deeper terminal widget plugin using qtermwidget or PTY/web terminal emulation.
- Continue enriching embedded file transfer UI with live transfer progress after queue/preview support.
- Richer layout save/restore with resize persistence.
- Add release signing support for Windows Authenticode and macOS Developer ID.

## v0.3.x

- Team sync backend proof-of-concept.
- Browser API backend.
- Add Apple notarization for macOS distribution.
- Add hosted or self-hosted 32-bit Linux and ARMv7 release runners for already declared native package mappings.
- Android PWA packaging; keep APK publishing gated on a real native Android wrapper.
- More protocol plugins.
