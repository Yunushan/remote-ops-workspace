# v1.0.27 release candidate

**Status:** Prepared in the repository. No v1.0.27 tag or GitHub release has been published.

The planned downloadable release follows the v1.0.23/v1.0.24 model: an exact
`v1.0.27` tag with a GitHub prerelease titled **v1.0.27 (UNSIGNED PREVIEW)**.
Its standard source/Python and native download families must pass their build,
smoke, manifest, checksum, and asset checks before publication. Windows and
macOS native installers will remain unsigned or unnotarized and are for testing
only. The release notes must report protected-platform and MobaXterm evidence
counts without implying those goals are complete.

The native GUI bundles also require PyQt6/Qt redistribution materials and
artifact-level verification. Those materials are not yet present in the
candidate packages, so the full native preview must not be published until
this requirement is met.

This candidate targets three High CodeQL findings reported on `main`: two polynomial regular-expression risks in `src/remote_ops_workspace/redaction.py` and clear-text logging of sensitive information in `scripts/check_security_polish.py`. A fresh CodeQL run on the final release commit is needed to confirm their closure.

Production promotion remains blocked by the checked-in compliance policy (`blocked-pending-independent-review`, with no trusted independent approval key, approved closed-world inventory, or fully hashed platform locks) and by the absence of accepted protected-platform evidence. Candidate builds and local checks do not establish a published production release. See [the production-readiness gate](PRODUCTION_READINESS.md) for the required evidence and signing steps.
