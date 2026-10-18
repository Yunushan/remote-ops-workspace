# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This changelog starts at the released 1.x line. Earlier per-release detail lives in
the versioned release notes under [`docs/`](docs) (for example
[`docs/RELEASE_NOTES_v1.0.27.md`](docs/RELEASE_NOTES_v1.0.27.md)). Release
publication status is authoritative on the
[GitHub releases page](https://github.com/Yunushan/remote-ops-workspace/releases).
For the change classes used below, see [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `docs/PRODUCTION_READINESS_SCORECARD.md` and
  `docs/PRODUCTION_READINESS_BACKLOG.md` tracking the weighted readiness score and
  the itemized backlog to close each gap.

## [1.0.27]

### Changed

- Managed process lifecycle hardened, workspace recovery improved, and release
  input handling tightened (PR #125).
- Inno Setup version detection derived from the compiler runtime; installer
  license inspection fixed for unsigned releases (PR #124, PR #123).
- Release source normalized and clean-checkout verification added; Debian, RPM,
  AppImage and Windows unsigned payload inspection added to the release audit.

### Security

- Three High CodeQL findings on `main` fixed (two polynomial regular-expression
  risks in `src/remote_ops_workspace/redaction.py` and clear-text logging of
  sensitive information in `scripts/check_security_polish.py`) (PR #114).

### Notes

- The `v1.0.27` download is an explicitly labeled **UNSIGNED PREVIEW**
  prerelease. Windows and macOS native installers are unsigned or unnotarized
  and are for testing only.
- Production promotion remains blocked by the checked-in compliance policy
  (`blocked-pending-independent-review`) and the absence of accepted
  protected-platform evidence. See
  [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md).

[Unreleased]: https://github.com/Yunushan/remote-ops-workspace/compare/v1.0.27...HEAD
[1.0.27]: https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.27
