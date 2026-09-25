# v1.0.27 release preparation

This file records the v1.0.27 release plan. Check the [GitHub release page](https://github.com/Yunushan/remote-ops-workspace/releases/tag/v1.0.27) for publication status.

The planned downloadable release follows the v1.0.23/v1.0.24 model: an exact
`v1.0.27` tag with a GitHub prerelease titled **v1.0.27 (UNSIGNED PREVIEW)**.
Its standard source/Python and native download families must pass their build,
smoke, manifest, checksum, and asset checks before publication. Windows and
macOS native installers will remain unsigned or unnotarized and are for testing
only. The release notes must report protected-platform and MobaXterm evidence
counts without implying those goals are complete.

The native GUI bundles include PyQt6/Qt redistribution materials and relinking
instructions. The manual exact-tag workflow verifies those materials against
the built Windows and macOS packages before publishing; this artifact check is
not a legal certification.

PR #114 fixed the three High CodeQL findings reported on `main`: two polynomial regular-expression risks in `src/remote_ops_workspace/redaction.py` and clear-text logging of sensitive information in `scripts/check_security_polish.py`. The release source must continue to pass exact-SHA CI and CodeQL checks.

The project source remains under 0BSD. The Windows x64/ARM64 and macOS GUI bundles combine it with PyQt6 under GPLv3 and Qt under LGPLv3. Each GUI package contains both license texts and relinking instructions; the release notes link to the exact corresponding upstream source archives and hashes.

Production promotion remains blocked by the checked-in compliance policy (`blocked-pending-independent-review`, with no trusted independent approval key, approved closed-world inventory, or fully hashed platform locks) and by the absence of accepted protected-platform evidence. Candidate builds and local checks do not establish a published production release. See [the production-readiness gate](PRODUCTION_READINESS.md) for the required evidence and signing steps.
