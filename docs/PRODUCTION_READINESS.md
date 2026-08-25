# Production-readiness gate

The 100/100 target is an evidence gate, not a feature-manifest percentage. A
green source build, a candidate installer, or a generated GUI parity score does
not close a native-host or release-trust requirement by itself.

## Required gates

| Gate | Required proof | Authoritative check |
| --- | --- | --- |
| Quality and product workflows | CI run is green, coverage floor is met, and the repository verifier passes | `python scripts/verify.py --quick --no-cli-smoke` plus the completed GitHub `ci` run |
| Default release artifacts | The exact tag builds the matrix, native smoke passes, checksums/manifests exist, and the published release assets are non-empty | `python scripts/check_release_publish_assets.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo>` plus the remote release audit |
| Production signing | Windows Authenticode and macOS Developer ID/notarization proofs are present | release environment signing readiness and native manifest signing metadata |
| Protected platform parity | Finalized, release-bound accepted records for Linux i386, Linux armhf, Windows XP x86 and Windows XP x64, including real host smoke and release-byte provenance | `python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>` and the asset-backed protected-goal gate |
| Strict MobaXterm depth | One accepted release evidence record for every tracked article | `python scripts/check_mobaxterm_parity_evidence.py --require-complete` |
| Repository governance | Required checks (including the stable `Python 3.15 readiness` and `Native Windows readiness` aggregates), conversation resolution, linear history, and no force-push/deletion are enabled on `main`; pull-request approvals and signed commits remain optional controls | `python scripts/check_repository_governance.py --repository <owner/repo>` (GitHub branch-protection API, not a local manifest). Add `--require-review --require-signed-commits` for the stricter policy. |

The protected-platform gate must report `4/4` accepted targets and the strict
MobaXterm gate must report `8/8`. Candidate workflow success is deliberately not
counted as accepted evidence.

## External prerequisites

Configure these protected `release` environment secrets without committing their
values or writing them into logs:

- Windows: `ROW_WINDOWS_CERTIFICATE_BASE64`,
  `ROW_WINDOWS_CERTIFICATE_PASSWORD`, `ROW_WINDOWS_TIMESTAMP_URL`.
- macOS: `ROW_MACOS_CERTIFICATE_BASE64`, `ROW_MACOS_CERTIFICATE_PASSWORD`,
  `ROW_MACOS_SIGN_IDENTITY`, `ROW_MACOS_INSTALLER_SIGN_IDENTITY`,
  `ROW_MACOS_NOTARY_KEY_BASE64`, `ROW_MACOS_NOTARY_KEY_ID`,
  `ROW_MACOS_NOTARY_ISSUER`.

Bring the required evidence infrastructure online before dispatching the
protected workflows:

- a real 32-bit i386/i686 Linux builder with labels `self-hosted`, `linux`,
  `i386`;
- a real 32-bit armv7l/armhf Linux builder with labels `self-hosted`, `linux`,
  `armhf`;
- a modern collector with labels `self-hosted`, `xp-evidence`, plus a real
  Windows XP SP3 x86 host and a real Windows XP Professional x64 SP2 host for
  `scripts/xp_smoke_runner.cmd`.

Check runner availability immediately before dispatch:

```bash
python scripts/check_platform_evidence_runner_readiness.py \
  --repository <owner>/<repo> --require-goal-targets --require-idle
```

The manual protected-evidence workflows also perform this inventory check on a
hosted runner. If GitHub successfully returns the inventory but no required idle
runner exists, the workflow records an explicit non-promotional skip and leaves
the native target jobs skipped. That result does not create evidence, change the
support boundary, or satisfy the `4/4` protected-platform gate. Authentication,
permission, malformed-response, and transport failures remain hard workflow
failures so an unavailable API cannot be mistaken for an unavailable runner.

The Linux and XP hosts must produce the target/release-scoped artifacts, smoke
logs, builder or host identity, security-patch provenance, checksums, manifests,
review bundle, and finalized accepted record required by
`configs/platform_parity_promotion.json`. Do not append templates, candidate
records, screenshots, or generated placeholders to the accepted registries.

## Final promotion sequence

1. Run the runner-readiness check above.
2. Dispatch `.github/workflows/extended-platform-evidence.yml` for Linux i386 and
   armhf, and `.github/workflows/xp-native-evidence.yml` for both XP targets.
3. Run the target-specific local preflight, bundle packer, finalizer, and staged
   upload commands from `docs/PLATFORM_PROMOTION_RUNBOOK.md`.
4. Append only finalized records after their review bundles and source-run
   metadata pass validation.
5. Dispatch `release.yml` with `include_protected_platform_evidence=true` for
   the exact release tag, then run the remote byte-provenance audit.
6. Publish only after the signed channel is ready and all four protected targets
   plus all eight strict MobaXterm articles are accepted.

Until every gate above is proven, the release must remain an explicitly labeled
preview or a default release with the protected targets outside its support
boundary. Modern security defaults must remain unchanged while legacy support is
isolated per profile.

Once the external prerequisites are ready, run the strict aggregate gate against
the exact downloaded release assets:

```bash
make production-readiness \
  RELEASE_TAG=v<project.version> \
  RELEASE_REPOSITORY=<owner>/<repo> \
  RELEASE_ASSETS_DIR=<release-assets-dir>
```

The target prints `production readiness: 100/100 gates passed` only after the
static verifier, all four accepted protected records, all eight strict
MobaXterm records, production signing metadata, downloaded release assets, and
the remote release byte-provenance audit all pass. It intentionally fails early
while any one of those proofs is missing.
