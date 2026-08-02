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
- Added loopback browser profile API backend with bearer authentication and policy enforcement.
- Added saved layout splitter-size persistence with validated restore for desktop sessions.
- Added GUI protocol presets and profile import previews before saving external profiles.
- Added versioned mounted-directory team sync proof-of-concept with conflict protection.
- Added install, verify, upgrade and uninstall smoke-test contract for native packages.
- Added real per-operation SFTP queue progress with fail-fast execution states.
- Added a bounded ANSI terminal-emulation backend to the embedded terminal widget.
- Added Kubernetes exec and hardened WinRM protocol adapters.

## v0.2.x

Release workflow support for Windows Authenticode and macOS Developer ID is
implemented in `.github/workflows/release.yml`, but this item is not marked
production-complete until the protected `release` environment contains the
required certificate, identity and notarization secrets and a signed release
has passed the remote asset audit.

## v0.3.x

- Apple notarization support is implemented in the macOS native workflow; the
  production prerequisite remains protected Developer ID/notary material.
- Extended Linux evidence workflows and native package mappings are present for
  32-bit Linux and ARMv7, but production readiness still requires matching
  online self-hosted builders and accepted release-bound evidence.
- The Web/PWA mobile contract is shipped and tested. APK publishing remains
  intentionally gated on a real native Android wrapper and is not claimed by
  the Web/PWA release channel.

## Current status

The repository-side implementation and verification gates for these roadmap
items pass. External release prerequisites are tracked separately in
[`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md); they must be satisfied
before a roadmap item is promoted to a 100% production claim.
