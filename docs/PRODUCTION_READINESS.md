# Production-readiness gate

The numeric assessment of current readiness and the itemized work to close each
gap are maintained in
[`docs/PRODUCTION_READINESS_SCORECARD.md`](PRODUCTION_READINESS_SCORECARD.md) and
[`docs/PRODUCTION_READINESS_BACKLOG.md`](PRODUCTION_READINESS_BACKLOG.md). This
file remains the authoritative pass/fail certification gate.

The 100/100 target is an evidence gate, not a feature-manifest percentage. A
green source build, a candidate installer, or a generated GUI parity score does
not close a native-host or release-trust requirement by itself.

## Required gates

| Gate | Required proof | Authoritative check |
| --- | --- | --- |
| Production maturity | Project metadata declares only `Development Status :: 5 - Production/Stable`, and the release tag exactly matches `project.version`; Alpha/Beta metadata cannot receive a production score | `python scripts/check_release_maturity.py --release-tag <tag>` |
| Quality and product workflows | Full local pytest, Ruff, non-GUI mypy, CLI smoke, and real PyQt6 rendering pass. The exact release SHA's GitHub `ci` push attempt reports successful aggregate jobs and required runtime, packaging, native Windows, and 100% aggregate and branch coverage steps on their expected hosts | `python scripts/verify.py --production-quality` plus `python scripts/check_python315_ci_evidence.py --repository <owner/repo> --branch main --sha <release-sha>` |
| Default release artifacts | The exact tag builds the matrix, native smoke passes, checksums/manifests exist, and the published release assets are non-empty | `check_release_publish_assets.py` with the downloaded assets, signed evidence registry, `--require-platform-goal-targets`, and `--native-release-channel production-signed`, plus the remote release audit |
| Published certified-inventory provenance | Every downloaded file has the same name, positive size, and SHA-256 digest as the live immutable GitHub Release; every asset in the complete release inventory has a witnessed SLSA provenance signature from `.github/workflows/release-promotion.yml` at the exact release SHA and exact `refs/tags/<tag>` source ref; all assets share one production-promotion run attempt and that exact attempt completed successfully | `check_release_provenance.py` through the aggregate published compliance audit, which also verifies the attested approval and governance proof from that same attempt |
| Third-party redistribution and realized runtime | An independently signed approval binds the exact native manifest and artifact hashes, the complete `pip inspect` environment, component classifications, packaged license-file extraction scans, and a per-platform fully hashed lock actually consumed by the mandatory tagged build workflow. GUI bundles additionally identify the PyQt/Qt channel and bind either both commercial licenses or the open-source application-license review, corresponding source, and relink mechanism | `check_release_license_compliance.py --verify-published-release` with the signed approval and bundle, sealed candidate inventory, signed platform registry, original Actions ZIPs, and publication governance proof supplied to the aggregate |
| Production signing | Windows Authenticode and macOS Developer ID/notarization proofs are present | Native build signing and smoke jobs, and `check_release_publish_assets.py` in `production-signed` mode |
| Protected platform parity | Finalized, release-bound accepted records for Linux i386, Linux armhf, Windows XP x86 and Windows XP x64, including real host smoke and release-byte provenance | `python scripts/check_platform_verified_evidence.py --registry <signed-registry.json> --require-goal-targets --require-review-bundles --release-tag <tag>` and the asset-backed protected-goal gate |
| Strict MobaXterm depth | Eight accepted records from a pinned registry commit on protected `main`, bound to exact release artifacts and reviewed workflow attempts, with live Professional update delivery verification | `python scripts/check_release_mobaxterm_parity.py --repository <owner/repo> --tag <tag> --sha <release-sha> --registry-commit <commit> --assets-dir <release-assets> --evidence-root <reviewed-evidence> --professional-update-origin <approved-https-origin>` |
| Repository governance | Required checks (including the stable `Python 3.15 readiness` and `Native Windows readiness` aggregates), conversation resolution, linear history, and no force-push/deletion are enabled on `main`; every required check is bound in branch protection to the configured GitHub App and resolves through that app's exact check suite to a successful `push` run of `.github/workflows/ci.yml` or `.github/workflows/codeql.yml` at the release SHA; an active, applicable tag ruleset prevents update and deletion of the exact release tag without bypass actors; pull-request approvals and signed commits remain optional controls | `python scripts/check_repository_governance.py --repository <owner/repo> --branch main --sha <release-sha> --release-tag <tag>` (live GitHub branch-protection, check-run, check-suite, Actions-run, and inherited tag-ruleset APIs, not a local manifest). Add `--require-review --require-signed-commits` for the stricter policy. |

The protected-platform gate must report `4/4` accepted targets and the strict
MobaXterm gate must report `8/8`. Candidate workflow success is deliberately not
counted as accepted evidence.

The v1.0.28 candidate metadata declares `Development Status :: 5 -
Production/Stable`. The repository remains intentionally fail-closed for
publication while `configs/release_compliance_policy.json` is
`blocked-pending-independent-review`, has no trusted approver key, no approved
closed-world inventory, and incomplete protected-platform lock evidence. Modern
source, Windows, macOS and Linux builders now consume complete target-specific
hash locks from `requirements-locks/`; source-build backends are installed from
hashed subset locks before isolated resolution is disabled. The resolver receipt
binds every input and lock digest, and `scripts/check_release_dependency_locks.py`
checks workflow consumption. These build inputs still require native-run and
exact-artifact approval evidence. Native
PyInstaller bundles redistribute CPython and may include PyInstaller bootloader
code, PyQt6, Qt, PyQt6-sip, cryptography/OpenSSL, bcrypt, cffi, pycparser,
truststore, and other resolved/native components; the root 0BSD `LICENSE` and
`NOTICE` do not prove those obligations are met. These are release blockers,
not evidence that may be inferred from a green build.

## External prerequisites

Use custom deployment rules to allow `v*` tags in the `release`,
`release-compliance-review`, and `platform-evidence` GitHub environments.
Keep the signing, promotion, and runner-inventory credentials scoped to
their respective environments. See
[GitHub environment configuration](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

Configure the signing inputs in the protected `release` environment without
committing their values or writing them into logs:

- Windows: `ROW_WINDOWS_CERTIFICATE_BASE64`,
  `ROW_WINDOWS_CERTIFICATE_PASSWORD`, `ROW_WINDOWS_TIMESTAMP_URL`.
- macOS: `ROW_MACOS_CERTIFICATE_BASE64`, `ROW_MACOS_CERTIFICATE_PASSWORD`,
  `ROW_MACOS_SIGN_IDENTITY`, `ROW_MACOS_INSTALLER_SIGN_IDENTITY`,
  `ROW_MACOS_NOTARY_KEY_BASE64`, `ROW_MACOS_NOTARY_KEY_ID`,
  `ROW_MACOS_NOTARY_ISSUER`.

The current hosted Windows jobs use a PFX on the GitHub runner. On a Windows
signing host provisioned by a certificate provider, the native and XP builders
can use a certificate from the `My` store by setting
`ROW_WINDOWS_CERTIFICATE_THUMBPRINT` to its 40-digit hexadecimal thumbprint.
Set `ROW_WINDOWS_CERTIFICATE_STORE_LOCATION=LocalMachine` for a machine-store
certificate. The default is `CurrentUser`. Set `ROW_WINDOWS_TIMESTAMP_URL` to
the provider's RFC 3161 endpoint and clear the PFX settings before selecting the
store certificate. Use `ROW_REQUIRE_RELEASE_SIGNING=1` for the modern builder
or `ROW_XP_REQUIRE_SIGNING=1` for the XP builder.

For a newly issued publicly trusted Windows code-signing certificate, connect
the signing provider on the protected runner so the key stays inside compliant
hardware or a signing service. The thumbprint selects the certificate and the
file and timestamp digests use SHA-256.
Qualify that integration against the staged application executables, the EXE
and MSI installers for each modern Windows architecture, and the two XP
executables. The EXE build calls the signer during Inno Setup compilation
to sign the installer, its temporary executables and the uninstaller.
Verify Authenticode and the RFC 3161 timestamp on the final bytes before
creating manifests. Native smoke verifies the installed uninstaller before
running it.
For the XP targets, record the signing profile and verify that the signed
executables still run on the two required hosts.
[CA/Browser Forum code-signing requirements](https://cabforum.org/working-groups/code-signing/requirements/#6274-subscriber-private-key-protection-and-verification) ·
[Microsoft SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool).

The Windows builder requires successful Authenticode verification with a
timestamp for each signed executable and MSI. The macOS builder signs the DMG
with Developer ID Application and the PKG with Developer ID Installer. It
validates both stapled notarization tickets and checks both final packages
against Gatekeeper policy before generating their signed-build manifests.

Enable [GitHub immutable releases](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
before production promotion. Give the `release-compliance-review` environment a
`ROW_RELEASE_IMMUTABILITY_TOKEN` scoped to this repository with Administration,
Actions, and Checks read access. Before creating a draft and again before
publishing it, promotion verifies the immutable-release setting, branch
protection, and the trusted workflow identity and success of each required check
at the release SHA. The independent signed tag-governance proof is verified at
each mutation boundary.

The machine running the aggregate gate must have GitHub CLI installed and
authenticated, with `GH_TOKEN` or `GITHUB_TOKEN` providing read access to
Actions, artifact attestations, commit check runs, releases, and `main` branch
protection. The installed CLI must support `gh attestation verify` with
`--signer-workflow`, `--source-digest`, and `--deny-self-hosted-runners`.
The governance audit must be authenticated with enough ruleset access for
GitHub to return `bypass_actors`; GitHub hides that field from callers without
ruleset write visibility, and the audit fails closed when it cannot prove that
the release-tag update/deletion rules have no bypass actors.
The local `refs/tags/<tag>` must resolve to the full 40-character
`RELEASE_SHA`. The checkout's `HEAD` must equal that SHA, and the working tree
must be clean before the local quality run and again immediately before the
success message. The gate checks both refs at those boundaries and verifies
that the tag matches the project and package version declarations.

An independent compliance authority must enroll a real Ed25519 public key in
the tracked policy and sign the exact approval JSON bytes. Follow the
[redistribution approval and local audit procedure](runbooks/RELEASE_PROMOTION.md#prepare-the-signed-redistribution-approval).
The evidence bundle
must retain the hashed resolver locks, raw `pip inspect` captures, extracted
license/notice files from every native artifact, and referenced legal/source or
commercial-license review records. The checker reads and hashes those files; a
path/digest claim without the referenced bytes fails. For each production
Python target, its tagged build job must consume the tracked lock with
`pip --require-hashes`. The separate `release-promotion.yml` promotion job must
run the full exact-artifact compliance checker before creating or uploading a
GitHub Release. A reviewer signature
over an unused lock is insufficient.

After the four protected host runs succeed, put their original
`platform-verified-evidence-<target>-final.json` files in one directory.
Prepare the release registry and source capture while the original Actions
archives are still available.

```bash
python scripts/prepare_protected_platform_review.py \
  --repository "$release_repository" --release-tag "$release_tag" --release-sha "$release_sha" \
  --records-dir "$protected_finalized_records" --out "$protected_review_dir"
```

Use the tagged checkout and GitHub credentials with Actions and contents read
access. The command checks the live tag, verifies the original Actions ZIPs,
and re-finalizes the review bundles. Copy the generated
`platform_verified_evidence.json` and `protected-platform-sources/` directory
into the evidence bundle for independent review. Include the
`protected_platform_sources` field from `protected-platform-sources.json` in
the exact approval JSON before signing. Keep the generated `archives/`
directory in release evidence storage with the approved bundle. Promotion
compares the signed source metadata with live GitHub records and verifies
each original ZIP against GitHub's digest and the finalized record. The
completed-release audit verifies the retained ZIPs against the same signed
digests and checks the immutable release and its published files live.

The XP candidate workflow builds the WinForms companion against the tracked
.NET Framework 4 reference package. It keeps an attempt-scoped build receipt
with the compiler version and digest, reference digests, and hashes of the
source, executable, archive, and native manifest. The builder runs
`scripts/check_xp_candidate_build_inputs.py` before uploading the candidate
and receipt. The checker compares the tagged source and reference lock to the
receipt and inspects the ZIP for the expected executable architecture and
packaged license files. For signed builds, it also extracts the executable to
a temporary directory and verifies its Authenticode signature and timestamp
with Windows SDK SignTool. With the exact tagged commit checked out, run
`scripts/check_xp_candidate_run.py` for each architecture. It checks the
live tag and successful candidate attempt, compares the downloaded candidate
and receipt ZIPs to their GitHub artifact IDs and digests, and verifies that
the candidate files match the files staged for release. The command requires
the two original Actions ZIPs and an Actions read token. Independent review
of the exact package and its runtime prerequisites is still required. For
each XP manifest, the signed inventory uses profile `xp-dotnet-framework-v4`.
It supplies `run_id` and `run_attempt`, plus hash-bound
`candidate_artifact`, `receipt_artifact` and `redistribution_review` records.
Both artifact records include their numeric GitHub `artifact_id`. The review
record binds the independent decision, the `.NET Framework 4` prerequisite
and `runtime_redistributed: false`. Promotion repeats the live candidate check
for both XP architectures using the signed records.
Branch builds, release-tag pushes and default manual runs create unsigned
XP candidates. To request signed candidates, dispatch the workflow against
the release tag with `sign` enabled. That job uses the protected `release`
environment, the Windows certificate and the RFC 3161 timestamp settings
above. Tag builds and explicit signing runs verify the live release tag
and its ancestry on the default branch before building. The signed run
verifies the executable both before archiving and inside the resulting ZIP.
The receipt checker receives `--require-signing` for that explicit choice,
and production evidence verification requires the signed candidate job.
The XP build receipt and native manifest bind signature metadata to the
candidate bytes. The XP host tests still have to demonstrate the behavior
of those exact files on each target OS.

With signing configured and the tagged source qualified, the tag run builds
and retains the signed and notarized candidate artifacts. It seals their
numeric artifact identities and archive digests. Publication requires the
tracked policy and locks to be independently approved. The inventory
also records the SHA-256 and size of each standard native target's
`candidate-pip-inspect.json`, captured with the Python interpreter used for
packaging. A reviewer downloads those exact run artifacts, uses the sealed
report bytes in the signed evidence, signs their complete evidence inventory,
and places the evidence, detached signature, and hash-bound bundle under
`releases/<tag>/<sha>/` on the data-only `release-compliance-evidence` branch.
Only after that external step is complete may the operator dispatch
`release-promotion.yml` from the same tag, supplying the exact candidate run,
inventory artifact ID/digest, and immutable evidence commit SHA. Its protected
`release-compliance-review` job checks that the tagged commit is on the
default branch and that the exact commit has successful required CI.
It checks out the untrusted transport branch as data, authenticates the
evidence through the tag-pinned Ed25519 policy and performs the full
redistribution audit. It also opens each exact standard and protected Linux
package with format-specific archive readers to verify the tagged third-party
notices and required PyQt/Qt materials. It then attests the complete
inventory, obtains a fresh signed governance proof
for draft creation, creates a draft,
verifies every draft byte and attestation against its own tag-bound invocation,
obtains a fresh publication proof for the numeric draft, and promotes that draft once.
The workflow rechecks each proof immediately before its mutation. The auditor follows
the [tag ruleset capture procedure](runbooks/RELEASE_PROMOTION.md#capture-the-signed-tag-ruleset-proof).
`release.yml` builds candidates
and never publishes. The `unsigned-preview.yml` branch lane publishes source/Python assets
under a unique non-`v*` tag. The separate `versioned-unsigned-release.yml` lane
may publish the standard downloads under an exact `vX.Y.Z` tag as an explicitly
labeled `UNSIGNED PREVIEW` prerelease. Neither preview is production
certification or satisfies the 100/100 gate.

Bring the required evidence infrastructure online before dispatching the
protected workflows:

- a real 32-bit i386/i686 Linux builder with labels `self-hosted`, `linux`,
  `i386`;
- a real 32-bit armv7l/armhf Linux builder with labels `self-hosted`, `linux`,
  `armhf`;
- a modern Windows collector with PowerShell 7 and labels
  `self-hosted`, `windows`, `xp-evidence`, plus a real
  Windows XP SP3 x86 host and a real Windows XP Professional x64 SP2 host for
  `scripts/xp_smoke_runner.cmd`.

Check runner availability immediately before dispatch:

```bash
python scripts/check_platform_evidence_runner_readiness.py \
  --repository <owner>/<repo> --require-goal-targets --require-idle
```

The manual protected-evidence workflows use a GitHub-hosted runner to confirm
that the tagged commit is on the default branch before checking the inventory.
Configure the tag-restricted `platform-evidence` environment
and its read-only inventory token as described in the
[platform promotion runbook](PLATFORM_PROMOTION_RUNBOOK.md).
If GitHub successfully returns the inventory but no required idle
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

The v1.0.28 candidate uses a fresh release namespace. The protected `v1.0.27`
tag belongs to the published unsigned preview. Verify the production version
is still unused before creating the tag on the qualified source commit.

1. Run the runner-readiness check above.
2. Prepare the signing credentials and the independently approved release
   policy on protected main. Run the
   [pre-tag check](runbooks/RELEASE_PROMOTION.md#prepare-the-policy-before-tagging)
   against the exact qualified source commit. Push the immutable
   production source tag. The tag push starts `release.yml`,
   which builds and seals the signed and notarized candidate bytes.
   If the build fails before sealing, dispatch a fresh run with
   `gh workflow run release.yml --repo <owner>/<repo> --ref <tag>`.
   Use the same immutable tag and submit the new sealed inventory for review.
3. Dispatch `.github/workflows/extended-platform-evidence.yml` for Linux i386
   and armhf and `.github/workflows/xp-native-evidence.yml` for both XP targets.
   Select the production tag as the workflow ref and as the `release_tag` input
   so the evidence runs bind to the tagged commit. The Linux builders run
   `pip check` and retain the raw `pip inspect --local` report inside their
   version 2 review ZIP. Use that report verbatim as the signed Linux
   `realized_environment` evidence. The report records installed dependencies.
   The builders use the target-specific candidate locks in
   `requirements-locks/protected-linux/`. Production requires the independent
   reviewer to approve the exact lock bytes and the native build outputs.
4. Run the target-specific local preflight, bundle packer, finalizer, and staged
   upload commands from `docs/PLATFORM_PROMOTION_RUNBOOK.md`.
5. Put the finalized records in the protected-platform registry for the signed
   compliance bundle after their review bundles and source-run metadata pass
   validation.
6. [Stage the exact Actions artifacts for review](runbooks/RELEASE_PROMOTION.md#stage-the-candidate-for-review).
   Capture each platform's tracked fully hashed resolver input, raw realized
   environment, artifact extraction/license inventory, and build provenance.
   Sign the exact manifest and artifact hashes and place the authenticated
   bundle on `release-compliance-evidence`. Record its
   immutable commit SHA and retain the exact sealed candidate inventory; do not
   rebuild after approval.
7. Follow the [production promotion dispatch](runbooks/RELEASE_PROMOTION.md#dispatch-production-promotion)
   using the same tag and the sealed inventory from a successful candidate run
   on attempt 1. Once promotion completes, [download the complete release inventory
   and the exact publication evidence](runbooks/RELEASE_PROMOTION.md#download-the-publication-evidence)
   from that promotion attempt.
8. Check the `release-certification.yml` run triggered by that promotion for a successful audit of
   the immutable inventory and the two attested proofs. The final aggregate
   also runs the published compliance audit with the complete signed bundle
   and original protected-platform source archives.
9. [Finalize the eight MobaXterm evidence records](MOBAXTERM_PARITY.md#finalize-the-registry-after-immutable-publication)
   against the complete immutable release. Merge the reviewed registry into
   protected `main` and retain the full SHA of that registry commit.
10. Run the aggregate certification gate from the tagged checkout with the
    downloaded release assets and the pinned evidence inputs. The final
    audit rechecks the live release notes because GitHub allows edits to
    release notes after immutable publication.
    [GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)

Until every gate above is proven, the release must remain an explicitly labeled
preview or a default release with the protected targets outside its support
boundary. Modern security defaults must remain unchanged while legacy support is
isolated per profile.

Once the external prerequisites are ready, run the strict aggregate gate against
the exact downloaded release assets:

```bash
make production-readiness \
  RELEASE_TAG="<version-tag>" \
  RELEASE_SHA="<40-character-tag-commit-sha>" \
  RELEASE_REPOSITORY="<owner>/<repo>" \
  RELEASE_ASSETS_DIR="<downloaded-release-assets-dir>" \
  RELEASE_LICENSE_EVIDENCE="<approval.json>" \
  RELEASE_LICENSE_SIGNATURE="<approval.sig.json>" \
  RELEASE_LICENSE_EVIDENCE_ROOT="<evidence-bundle-dir>" \
  RELEASE_CANDIDATE_INVENTORY="<sealed-candidate-inventory.json>" \
  RELEASE_PLATFORM_EVIDENCE_REGISTRY="<signed-bundle-platform_verified_evidence.json>" \
  RELEASE_PLATFORM_SOURCE_ARCHIVES="<capture-directory>/archives" \
  RELEASE_MOBAXTERM_REGISTRY_COMMIT="<merged-parity-registry-commit-sha>" \
  RELEASE_MOBAXTERM_EVIDENCE_ROOT="<reviewed-parity-evidence-directory>" \
  RELEASE_PROFESSIONAL_UPDATE_ORIGINS="<approved-HTTPS-origin-list>" \
  RELEASE_TAG_GOVERNANCE_ATTESTATION="<tag-governance-attestation.json>" \
  RELEASE_TAG_GOVERNANCE_SIGNATURE="<tag-governance-attestation.sig.json>"
```

Set the same `RELEASE_*` names as environment variables to run the audit
directly with `python scripts/check_production_readiness.py` from the tagged
checkout. In PowerShell, assign each value with `$env:RELEASE_TAG = 'vX.Y.Z'`
and the corresponding variable name for the other inputs. The Make target
calls the same Python audit.

The audit checks all required inputs before running the gate. Evidence
directories must exist, and evidence files must be nonempty. Keep the inputs
outside the tagged checkout so its clean-tree check can pass. The default `release-assets/`
download directory is ignored by Git.
Use the protected-platform registry from the signed compliance bundle for
`RELEASE_PLATFORM_EVIDENCE_REGISTRY`. The local checks and live GitHub audit
both use that same file. The MobaXterm audit reads the registry from
`RELEASE_MOBAXTERM_REGISTRY_COMMIT` on GitHub. That commit must descend from
the release source and be reachable from protected `main`. The audit compares
the accepted records with the release identity, live GitHub reviews and run
attempts, and SHA-256 hashes of the same downloaded assets checked by the
release provenance gate.

Supply `RELEASE_PROFESSIONAL_UPDATE_ORIGINS` as a space-separated list of
independently approved HTTPS origins for the organization's update channel,
including any origins reached by its approved redirects. Each item is an
origin such as `https://updates.example.org`. After evidence and provenance
checks pass, the release audit downloads the signed manifest and both branded
Windows installers. Their sizes and SHA-256 digests must match the reviewed
bytes before certification can succeed.

Use the exact publication proof and detached signature retained by the promotion
for the aggregate. It verifies their signatures and attested
digests alongside the redistribution approval, sealed candidate inventory,
protected-platform registry, and published files. All must share a completed,
successful promotion attempt. The aggregate compares the standard published
files with the approved candidate inventory and verifies the published protected
files against the signed registry. The live immutable release's publication
time must fall within that attempt and the independently signed governance
window. The operator audit can run after the governance window has expired.

Retain the exact reviewed article files in a separate directory under
`<reviewed-parity-evidence-directory>/<article-id>/`, with the article document
named `evidence.json`. Generate the candidate using that file and its article
directory as `--assets-dir`. The strict gate checks the directory's exact file
inventory and hashes, runs the article validator again, and compares its
results with the reviewed summary.

The audit verifies the original GitHub Actions ZIP from the successful
qualification job for MobApt, X11 forwarding, the Debian embedded server suite,
the connected editor, macro replay, Professional deployment, the physical
smart-card file browser and the native terminal grid. It
checks the archive's size and SHA-256 against GitHub and compares its
candidate record and every evidence file with the reviewed record. While the
artifact is available, the audit downloads it if needed. Retain the original
ZIP as `workflow-artifacts/<artifact-name>.zip` under the reviewed parity
evidence directory so the audit can use it after downloads expire. GitHub
must still report the artifact's metadata for the exact run attempt.

The target prints `production readiness: 100/100 gates passed` only after the
production metadata, tag/SHA/checkout equality, and clean-tree checks; the full local pytest, Ruff, mypy, CLI, and real-GUI
quality profile; the exact-SHA successful `ci` push run and its successful
100% coverage and branch-threshold validation steps; app-, suite-, and
workflow-bound exact-SHA required check runs; non-bypassable update/deletion
rules for the exact release tag; all four accepted protected records; all eight strict MobaXterm
records; production signing metadata; downloaded bytes matching the complete
published release inventory; independently signed closed-world runtime/license
   evidence and enforced hashed locks; a common witnessed complete-inventory
attestation from one successful exact-tag/exact-SHA `release-promotion.yml` run attempt; and the protected remote
release byte-provenance audit all pass. It intentionally fails early while any
one of those proofs is missing, pending, skipped, mismatched, or unsuccessful.
