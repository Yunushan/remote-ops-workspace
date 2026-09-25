# Production-readiness gate

The 100/100 target is an evidence gate, not a feature-manifest percentage. A
green source build, a candidate installer, or a generated GUI parity score does
not close a native-host or release-trust requirement by itself.

## Required gates

| Gate | Required proof | Authoritative check |
| --- | --- | --- |
| Production maturity | Project metadata declares only `Development Status :: 5 - Production/Stable`, and the release tag exactly matches `project.version`; Alpha/Beta metadata cannot receive a production score | `python scripts/check_release_maturity.py --release-tag <tag>` |
| Quality and product workflows | Full local pytest, Ruff, non-GUI mypy, CLI smoke, and real PyQt6 rendering pass; the exact release SHA's GitHub `ci` push run is successful | `python scripts/verify.py --production-quality` plus `python scripts/check_python315_ci_evidence.py --repository <owner/repo> --branch main --sha <release-sha>` |
| Default release artifacts | The exact tag builds the matrix, native smoke passes, checksums/manifests exist, and the published release assets are non-empty | `python scripts/check_release_publish_assets.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo>` plus the remote release audit |
| Published certified-inventory provenance | Every downloaded file has the same name, positive size, and SHA-256 digest as the live immutable GitHub Release; every asset in the complete release inventory has a witnessed SLSA provenance signature from `.github/workflows/release.yml` at the exact release SHA and exact `refs/tags/<tag>` source ref; all assets share one tag-push run attempt and that exact attempt completed successfully | `python scripts/check_release_provenance.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo> --sha <release-sha>` |
| Third-party redistribution and realized runtime | An independently signed approval binds the exact native manifest and artifact hashes, the complete `pip inspect` environment, component classifications, packaged license-file extraction scans, and a per-platform fully hashed lock actually consumed by the mandatory tagged build workflow. GUI bundles additionally identify the PyQt/Qt channel and bind either both commercial licenses or the open-source application-license review, corresponding source, and relink mechanism | `python scripts/check_release_license_compliance.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo> --sha <release-sha> --evidence <approval.json> --signature <approval.sig.json> --evidence-root <evidence-bundle>` |
| Production signing | Windows Authenticode and macOS Developer ID/notarization proofs are present | release environment signing readiness and native manifest signing metadata |
| Protected platform parity | Finalized, release-bound accepted records for Linux i386, Linux armhf, Windows XP x86 and Windows XP x64, including real host smoke and release-byte provenance | `python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>` and the asset-backed protected-goal gate |
| Strict MobaXterm depth | One accepted release evidence record for every tracked article | `python scripts/check_mobaxterm_parity_evidence.py --require-complete` |
| Repository governance | Required checks (including the stable `Python 3.15 readiness` and `Native Windows readiness` aggregates), conversation resolution, linear history, and no force-push/deletion are enabled on `main`; every required check is bound in branch protection to the configured GitHub App and resolves through that app's exact check suite to a successful `push` run of `.github/workflows/ci.yml` or `.github/workflows/codeql.yml` at the release SHA; an active, applicable tag ruleset prevents update and deletion of the exact release tag without bypass actors; pull-request approvals and signed commits remain optional controls | `python scripts/check_repository_governance.py --repository <owner/repo> --branch main --sha <release-sha> --release-tag <tag>` (live GitHub branch-protection, check-run, check-suite, Actions-run, and inherited tag-ruleset APIs, not a local manifest). Add `--require-review --require-signed-commits` for the stricter policy. |

The protected-platform gate must report `4/4` accepted targets and the strict
MobaXterm gate must report `8/8`. Candidate workflow success is deliberately not
counted as accepted evidence.

The v1.0.27 package metadata declares `Development Status :: 5 -
Production/Stable`. The repository remains intentionally fail-closed for
publication while `configs/release_compliance_policy.json` is
`blocked-pending-independent-review`, has no trusted approver key, no approved
closed-world inventory, and no per-platform fully hashed locks. The normal
resolver installs can therefore select unpinned transitive packages. Native
PyInstaller bundles redistribute CPython and may include PyInstaller bootloader
code, PyQt6, Qt, PyQt6-sip, cryptography/OpenSSL, bcrypt, cffi, pycparser,
truststore, and other resolved/native components; the root 0BSD `LICENSE` and
`NOTICE` do not prove those obligations are met. These are release blockers,
not evidence that may be inferred from a green build.

## External prerequisites

Configure these protected `release` environment secrets without committing their
values or writing them into logs:

- Windows: `ROW_WINDOWS_CERTIFICATE_BASE64`,
  `ROW_WINDOWS_CERTIFICATE_PASSWORD`, `ROW_WINDOWS_TIMESTAMP_URL`.
- macOS: `ROW_MACOS_CERTIFICATE_BASE64`, `ROW_MACOS_CERTIFICATE_PASSWORD`,
  `ROW_MACOS_SIGN_IDENTITY`, `ROW_MACOS_INSTALLER_SIGN_IDENTITY`,
  `ROW_MACOS_NOTARY_KEY_BASE64`, `ROW_MACOS_NOTARY_KEY_ID`,
  `ROW_MACOS_NOTARY_ISSUER`.

The machine running the aggregate gate must have GitHub CLI installed and
authenticated, with `GH_TOKEN` or `GITHUB_TOKEN` providing read access to
Actions, artifact attestations, commit check runs, releases, and `main` branch
protection. The installed CLI must support `gh attestation verify` with
`--signer-workflow`, `--source-digest`, and `--deny-self-hosted-runners`.
The governance audit must be authenticated with enough ruleset access for
GitHub to return `bypass_actors`; GitHub hides that field from callers without
ruleset write visibility, and the audit fails closed when it cannot prove that
the release-tag update/deletion rules have no bypass actors.
The release tag and its full 40-character commit SHA must both resolve in the
local checkout. The checkout's `HEAD` must equal that SHA, and the working tree
must be clean before the local quality run and again immediately before the
success message. The gate rejects a SHA that does not match the tag, a different
checkout, or tracked/non-ignored untracked bytes that are not part of the tag.

An independent compliance authority must enroll a real Ed25519 public key in
the tracked policy and sign the exact approval JSON bytes. The evidence bundle
must retain the hashed resolver locks, raw `pip inspect` captures, extracted
license/notice files from every native artifact, and referenced legal/source or
commercial-license review records. The checker reads and hashes those files; a
path/digest claim without the referenced bytes fails. For each production
target, the tagged `release.yml` job must consume the tracked lock with
`pip --require-hashes`, and its `publish` job must run the full exact-artifact
compliance checker before `softprops/action-gh-release`. A reviewer signature
over an unused lock is insufficient.

The policy-only preflight therefore withholds the production-signed publication
lane today. Once the tracked policy and locks are independently approved, the
tag run builds and retains the exact signed/notarized candidate artifacts, then
the `release-compliance-review` environment holds its publish job. A reviewer
downloads those exact run artifacts, signs their complete evidence inventory,
and places the evidence, detached signature, and hash-bound bundle under
`releases/<tag>/<sha>/` on the data-only `release-compliance-evidence` branch.
Only after that external step is complete may the reviewer approve the held job.
The tag run checks out the untrusted transport branch as data and authenticates
all of it through the tag-pinned Ed25519 policy. It then performs the full audit,
attests the complete inventory, creates a draft,
verifies every draft byte and attestation against its own tag-bound invocation,
rechecks the tag, and promotes the draft once. Manual `release.yml` runs never
publish. The separate `unsigned-preview.yml` workflow is the only preview lane;
its unique non-`v*` tag and `UNSIGNED PREVIEW` prerelease cannot satisfy 100/100.

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
5. Let the exact-tag workflow produce and retain the signed/notarized candidate
   bytes, then leave its `release-compliance-review` publish job awaiting review.
6. Review those exact Actions artifacts, capture each platform's tracked fully
   hashed resolver input, raw realized environment, artifact extraction/license
   inventory, and build provenance, sign the exact manifest/artifact hashes, and
   place the authenticated bundle on `release-compliance-evidence`. Approve the
   held job only after the files are visible at `releases/<tag>/<sha>/`; do not
   rebuild after approval.
7. Push the immutable production tag only after that two-stage path exists, then
   download the complete release asset inventory.
8. Run the certified-inventory provenance check and the protected-platform remote
   byte-provenance audit. The provenance check requires one common, successful,
   certificate-bound `release.yml` tag run attempt at the exact release SHA; a
   main-branch dispatch, green run for another commit, and unattested or locally
   substituted bytes do not count.
9. Certify only after the signed channel is ready and all four protected targets
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
  RELEASE_SHA=<40-character-tag-commit-sha> \
  RELEASE_REPOSITORY=<owner>/<repo> \
  RELEASE_ASSETS_DIR=<release-assets-dir> \
  RELEASE_LICENSE_EVIDENCE=<approval.json> \
  RELEASE_LICENSE_SIGNATURE=<approval.sig.json> \
  RELEASE_LICENSE_EVIDENCE_ROOT=<evidence-bundle-dir>
```

The target prints `production readiness: 100/100 gates passed` only after the
production metadata, tag/SHA/checkout equality, and clean-tree checks; the full local pytest, Ruff, mypy, CLI, and real-GUI
quality profile; the exact-SHA successful `ci` push run; app-, suite-, and
workflow-bound exact-SHA required check runs; non-bypassable update/deletion
rules for the exact release tag; all four accepted protected records; all eight strict MobaXterm
records; production signing metadata; downloaded bytes matching the complete
published release inventory; independently signed closed-world runtime/license
   evidence and enforced hashed locks; a common witnessed complete-inventory
attestation from one successful exact-tag/exact-SHA `release.yml` run attempt; and the protected remote
release byte-provenance audit all pass. It intentionally fails early while any
one of those proofs is missing, pending, skipped, mismatched, or unsuccessful.
