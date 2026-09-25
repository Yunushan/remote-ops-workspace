# v1.0.27 release candidate

**Status:** Prepared in the repository. No v1.0.27 tag or GitHub release has been published.

This candidate targets three High CodeQL findings reported on `main`: two polynomial regular-expression risks in `src/remote_ops_workspace/redaction.py` and clear-text logging of sensitive information in `scripts/check_security_polish.py`. A fresh CodeQL run on the final release commit is needed to confirm their closure.

Production promotion remains blocked by the checked-in compliance policy (`blocked-pending-independent-review`, with no trusted independent approval key, approved closed-world inventory, or fully hashed platform locks) and by the absence of accepted protected-platform evidence. Candidate builds and local checks do not establish a published production release. See [the production-readiness gate](PRODUCTION_READINESS.md) for the required evidence and signing steps.
