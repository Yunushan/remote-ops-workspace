# Runbook: Release promotion and artifact verification

Authoritative promotion mechanics live in
[`../PLATFORM_PROMOTION_RUNBOOK.md`](../PLATFORM_PROMOTION_RUNBOOK.md) and the
gate definition in [`../PRODUCTION_READINESS.md`](../PRODUCTION_READINESS.md).
This runbook is the operator summary; it does not replace those documents.

## States

- `release.yml` builds and seals a **release candidate**. It never publishes.
- `release-promotion.yml` performs the independent, tag-and-SHA-bound audit and
  is the only path that creates a GitHub Release.

An unsigned preview build is explicitly labeled and is not a production
promotion target.

## Promotion checks

1. Confirm the exact source digest, not just the tag:

   ```bash
   git rev-parse HEAD
   python scripts/check_python315_ci_evidence.py --repository <owner/repo> --branch main --sha <release-sha>
   ```

2. Confirm maturity, provenance and repository governance:

   ```bash
   python scripts/check_release_maturity.py --release-tag <tag>
   python scripts/check_repository_governance.py --repository <owner/repo> --branch main --sha <release-sha> --release-tag <tag>
   ```

3. Confirm protected-platform and MobaXterm depth evidence:

   ```bash
   python scripts/check_platform_verified_evidence.py --registry configs/platform_verified_evidence.json --require-goal-targets --require-review-bundles --release-tag <tag>
   python scripts/check_mobaxterm_parity_evidence.py --require-complete
   ```

4. Run the strict aggregate gate and require
   `production readiness: 100/100 gates passed`:

   ```bash
   make production-readiness
   ```

## Verify a published artifact

Every download carries a release manifest and a `SHA256SUMS.txt` checksum
sidecar (per release, plus per-platform `native-SHA256SUMS.txt`). Verify both the
checksum and the build provenance before installing:

```bash
sha256sum -c remote-ops-workspace-v<version>-SHA256SUMS.txt
gh attestation verify ./remote-ops-workspace-v<version>-linux-x86_64.AppImage \
  --repo Yunushan/remote-ops-workspace
```

The same pattern applies to Windows and macOS native artifacts and their
per-platform sidecars. See [`../PRODUCTION_DEPLOYMENT.md`](../PRODUCTION_DEPLOYMENT.md).

## Installer trust boundary (O3)

`installers/install.sh`, `installers/install.bat`, `installers/install.ps1` and
`installers/install-termux.sh` are **source installers**: they install from a
checked-out source tree and perform no artifact integrity check. They must not be
used to fetch an opaque binary over the network.

For a released binary, always download through the verified path above
(`SHA256SUMS.txt` plus `gh attestation verify`) rather than piping an unchecked
URL into a shell. Automating checksum and attestation verification inside the
installers is tracked as a follow-up; until then, verification is an operator
step documented here.

## Rollback

If a promoted release is withdrawn after publication, follow
[`UPGRADE_AND_ROLLBACK.md`](UPGRADE_AND_ROLLBACK.md) on the receiving hosts and
record the incident per
[`SECRET_ROTATION_AND_INCIDENT.md`](SECRET_ROTATION_AND_INCIDENT.md).
