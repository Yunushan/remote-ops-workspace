# Release Strategy

Remote Ops Workspace publishes release assets in phases. Each phase should ship
only when the artifact is real, reproducible, and documented.

Release integrity rules:

- Release tags must match `pyproject.toml` exactly, for example `v1.0.2`.
- Pushing a `vX.Y.Z` tag automatically builds, smoke-tests and publishes the
  standard source, Windows, macOS and Linux native assets. The tag must resolve
  to a commit reachable from the trusted default branch. The default core-release
  lane does not claim Linux i386/armhf or Windows XP native-host support. To
  attach those protected assets later, manually dispatch `release.yml` with
  `release_tag=vX.Y.Z` and `include_protected_platform_evidence=true`; that
  opt-in lane requires the four evidence workflows, finalized accepted records
  and exact evidence assets before it can attach anything to the existing release.
- Source/install bundles are built with deterministic archive metadata using
  `SOURCE_DATE_EPOCH` or a fixed default.
- Python release build dependencies are constrained by `requirements-release.txt`
  and mirrored in `configs/release_toolchain.json`.
- The GitHub release workflow avoids unbounded `pip install --upgrade` commands.
- Every artifact entry in release manifests includes `size_bytes` and `sha256`.
- Release manifests record the release toolchain contract used for the build.
- The source/Python release job also emits
  `remote-ops-workspace-v<version>-SHA256SUMS.txt` covering every generated
  artifact plus the release manifest.
- Each native platform script emits a per-platform
  `remote-ops-workspace-v<version>-<platform>-<arch>-native-SHA256SUMS.txt`
  sidecar covering its native artifacts and native manifest.
- Native installer smoke coverage is declared in
  `configs/native_installer_smoke.json` and checked by
  `python scripts/check_native_installer_smoke.py`. The release workflow runs
  `scripts/smoke_windows_native.ps1`, `scripts/smoke_macos_native.sh` and
  `scripts/smoke_linux_native.sh` after native builds and before artifact
  upload.
- The core `release-preflight` workflow job runs
  `python scripts/verify.py --quick --no-cli-smoke --release-tag <tag>`, reports
  protected-platform readiness and then runs
  `python scripts/check_repository_cleanup.py --require-clean` before standard
  assets build. It does not block normal Windows, macOS or default Linux
  releases on unavailable i386, armhf or XP hosts. The opt-in protected
  promotion lane performs the stricter source-reference, accepted-record and
  review-bundle checks before it imports or attaches protected assets.
- Immediately before dispatching protected-platform evidence, an authorized
  operator must run `python scripts/check_platform_evidence_runner_readiness.py
  --repository <owner>/<repo> --require-goal-targets --require-idle`. It confirms
  the required self-hosted evidence labels are online and idle without granting
  runner-inventory access to normal release jobs.
- Before tagging or rerunning a protected-platform promotion, run the
  pre-release protected-platform import dry-run
  `python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>`.
  It proves the accepted records for Linux i386, Linux armhf and Windows XP
  native-host targets are importable from exact successful same-source
  workflow runs at the accepted run id, attempt, workflow path and source SHA,
  with a complete artifact inventory containing exactly one non-expired,
  non-empty expected source artifact whose `workflow_run.id` and
  `workflow_run.head_sha` bind it to the accepted source run, plus
  `workflow_run.repository_id` and `workflow_run.head_repository_id` binding
  from exact source-run metadata, artifact created_at
  inside the exact source run creation/start/update window from exact source-run timestamps,
  and artifact `expires_at` present and later than the artifact create/update timestamps,
  without copying files
  into the publish directory, and it does not stage files for upload.
- The opt-in `accepted-platform-evidence-assets` job keeps read-only repository
  and Actions artifact permissions; it must not request any write-scoped GitHub
  permission while importing protected-platform evidence. It runs only when
  `include_protected_platform_evidence=true`. That lane first runs
  `python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets`,
  which refuses release tags that do not contain the tagged project version and
  all four protected workflow dispatch options.
- The default publish job runs
  `python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --repository <owner>/<repo>`
  after downloading standard workflow artifacts and before uploading the GitHub
  release. The opt-in protected promotion job runs
  `python scripts/check_protected_platform_goal.py --release-tag <tag> --require-complete --assets-dir release-assets --repository <owner>/<repo>`
  and then
  `python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --repository <owner>/<repo> --require-platform-goal-targets`
  before attaching protected evidence assets.
  The first command keeps the protected parity gate bound to the publish-ready
  release asset directory; the second verifies the full release asset contract
  and binds accepted protected-platform release URLs to the publishing
  repository.
  Static readiness JSON does not download release assets and therefore keeps
  `release_asset_provenance_complete=false`; only the asset-backed protected
  goal gate can flip that proof state after finalized records, review bundles
  and native release bytes match. It also keeps `record_complete` separate from
  `release_backed_complete` so records-only proof is not treated as published
  release-byte proof.
  The protected-platform asset job first runs
  `python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run --repository <owner>/<repo>`
  to import only same-tag, same-repository, workflow-file, source-head and
  run-attempt-bound accepted Linux i386, Linux armhf and Windows XP native-host
  artifacts from verified exact evidence workflow runs whose artifact inventory
  is complete and contains exactly one non-expired, non-empty expected source
  artifact bound by `workflow_run.id`, `workflow_run.head_sha`,
  `workflow_run.repository_id` and `workflow_run.head_repository_id` from exact
  source-run metadata, with artifact created_at inside the exact source
  run start/update window from exact source-run timestamps and artifact `expires_at`
  present and later than the artifact create/update timestamps, then runs
  `python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets`
  against the imported review bundles and finalized public record JSON files
  before uploading the platform evidence asset set. That upload must use
  `if-no-files-found: error`, `include-hidden-files: false` and
  `retention-days: 90` so missing imports fail, hidden scratch/private files
  stay excluded and the publish job can download the imported assets.
  The importer rejects symlinked downloaded-artifact/output roots, symlinked
  parent directories and symlinked destinations before copying into
  `release-assets`, and it checks downloaded source artifact native artifact
  SHA-256 values plus review-bundle size/SHA-256 values against the finalized
  accepted record before staging files for release upload.
  The publish checker then rejects a symlinked `release-assets` directory,
  symlinked parent directories and symlinked release asset files before upload.
  It verifies the expected asset set from `configs/release_matrix.json`,
  checksum sidecars, source release-manifest records, accepted platform
  evidence and the MobaXterm parity accepted-evidence registry. The protected
  platform goal flag makes release upload fail until Linux i386, Linux armhf,
  Windows XP native x86 and Windows XP native x64 all have finalized accepted
  evidence for the same release tag, GitHub release repository,
  target-specific release source workflow file, release source head SHA and a
  positive release source run attempt in each record. After upload, the remote
  evidence audit
  `python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head`
  checks the actual GitHub Release, published asset GitHub IDs/API URLs,
  digests, sizes and bytes, exact
  published final accepted-record JSON bytes, release tag Git object/source head SHA,
  source workflow run metadata,
  and source artifact `workflow_run.id`,
  `workflow_run.head_sha`, `workflow_run.repository_id` and
  `workflow_run.head_repository_id` binding from exact source-run metadata,
  plus artifact created_at inside the exact source run creation/start/update window from
  exact source-run timestamps and artifact `expires_at` present and later than
  the artifact create/update timestamps;
  it also rejects stale protected-platform native/evidence assets that remain
  on the GitHub Release outside the audited accepted-evidence scope. Use
  `--require-mobaxterm-parity-complete` only for releases that explicitly claim
  complete strict MobaXterm Home/Professional product-depth parity.
- CI build jobs run with read-only repository contents permission and checkout
  credentials are not persisted. Only the publish job receives release write
  permission.

## Release matrix policy

`configs/release_matrix.json` is the machine-readable answer to "what will a tag
release publish by default?" It is checked by
`python scripts/check_release_matrix.py` and must stay aligned with
`.github/workflows/release.yml`, `configs/platform_targets.json`, this document
and `docs/PLATFORM_SUPPORT.md`.

The default GitHub release workflow publishes:

- Python wheel, Python sdist, target source/install bundles, the release
  manifest and `remote-ops-workspace-v1.0.2-SHA256SUMS.txt`;
- Windows native `x86`, `x64` and `arm64` artifacts;
- macOS native `x64` and `arm64` artifacts;
- Linux native `x86_64`/`amd64` and `aarch64`/`arm64` artifacts.

Linux `i386`/`i686` and `armv7l`/`armhf` native outputs are
script-supported by `scripts/make_linux_native.sh`, but they are not uploaded by
the default GitHub release workflow. A maintainer can promote them only after
running and verifying a matching 32-bit builder whose identity evidence records
`dpkg --print-architecture` as `i386` or `armhf`, `getconf LONG_BIT` as
`32`, a concrete `rpm` tool path and `sudo -n true` passing. BSD, Solaris/illumos, Android
Termux/Web/PWA, iOS/iPadOS Web/PWA and legacy Windows endpoints remain
source/Web/remote-target entries unless a real native packaging path is added.
Windows XP x86/x64 remote endpoints use isolated per-profile legacy opt-ins
instead of lowering modern TLS, SSH or RDP defaults globally.
If those endpoints are promoted to native-host evidence, the release-importable
source artifact must come from `.github/workflows/xp-native-evidence.yml`,
which prints the current source workflow run metadata, waits for staged XP
artifacts and sanitized smoke evidence on a self-hosted `xp-evidence` runner,
stages only the expected release/evidence files into a plain non-symlink
`platform-evidence-upload/<target>/<release_tag>` tree, re-checks the staged
output exact root file set and pre-copy SHA-256 values, and uploads
`xp-native-evidence-<target>-<release_tag>` with `if-no-files-found: error`,
`include-hidden-files: false` and `retention-days: 90`; workflow-generated candidate
records, final records and review bundles must stay under
`xp-evidence-output/<target>/<release_tag>`, the staged XP artifact and
evidence-output directories must include the target id and release tag as path
segments, and staged source and upload paths must not traverse symlinked parent
directories.

`configs/platform_parity_promotion.json` and
`python scripts/check_platform_parity_promotion.py` define the required evidence
before extended targets can be promoted. Linux i386 and Linux armhf can move
from script-supported to default-native only when the release matrix, release
workflow, publish asset contract, native build outputs, smoke tests, checksum
sidecars and native manifests all include those architectures. Linux smoke
proof lines must be exact single-occurrence bindings, and forbidden
weak-security proof lines are rejected case-insensitively. The produced artifact
directory must pass
`python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`
or
`python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
That strict artifact check rejects symlinked artifact paths, artifact
directories that traverse symlinked parent directories, unsafe ZIP/tar
member names, link/device entries inside native archives and path-qualified
checksum/native-manifest references. Accepted Linux evidence command paths must
include the Linux target id and release tag as path segments.
`.github/workflows/extended-platform-evidence.yml` is the dispatch-only
self-hosted collection path for that evidence; it uses `[self-hosted, linux,
i386]` and `[self-hosted, linux, armhf]` runners and uploads evidence artifacts
without publishing a GitHub release. Before artifact upload it runs
`python scripts/stage_extended_linux_evidence_upload.py`, stages the exact
release-importable file set in a plain non-symlink
`platform-evidence-upload/<target>/<release_tag>` tree,
requires the staged source directory to include the target id and release tag as
path segments, rejects staged source or upload paths that traverse symlinked
parent directories, re-checks the staged output exact root file set and pre-copy
SHA-256 values, requires `if-no-files-found: error`,
`include-hidden-files: false` and `retention-days: 90` on the source artifact
upload, and avoids uploading raw Linux builder output directories by wildcard. Each run also writes
`platform-verified-evidence-linux-i386.json` or
`platform-verified-evidence-linux-armhf.json` into the uploaded evidence
artifact and packages the review bundle with
`python scripts/make_extended_linux_evidence_bundle.py`, whose output directory
must include the target id and release tag as path segments, must be plain
non-symlink without symlinked parent directories, and whose generated bundle
files must be plain non-symlink paths. Accepted release
evidence records must be added to
`configs/platform_verified_evidence.json` and pass
`python scripts/check_platform_verified_evidence.py` before generated readiness
can promote either Linux extended architecture. Generate those records with
`python scripts/make_platform_verified_evidence_record.py` so artifact URLs,
per-artifact SHA-256 digests, the Linux builder identity SHA-256 and the
workflow dispatch inputs, `release_asset_source.workflow=.github/workflows/extended-platform-evidence.yml`,
the source artifact staged upload command and the promotion config SHA-256 are
derived from the same promotion contract. Linux candidate generation must pass
`--staged-upload-out-dir platform-evidence-upload/<target>/v<project.version>` so the accepted record
binds the exact release upload staging root.
Linux records must also include the builder identity JSON emitted by
`python3 scripts/check_extended_platform_builder.py --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --out ...`; its
`--out` path must be a plain non-symlink file without symlinked parent
directories, `builder_identity_sha256` must
match that JSON, generator input paths for the artifact directory, builder
evidence and native smoke log must not traverse symlinked directories, and the JSON must bind the
same `release_tag`, `workflow_run_url` and `workflow_run_attempt` as the accepted record while `source_head_sha` and `observed_git_head_sha` match `release_asset_source.head_sha`, prove `git_worktree_clean=true` before native build, and also
including a sanitized target-scoped `host_identity` block with
`operator_private_data_redacted=true`, matching `platform.machine()` and
`uname -m`, `dpkg --print-architecture`
(`i386` for linux-i386 or `armhf` for linux-armhf), `getconf LONG_BIT` as
`32`, concrete `rpm` and `rpmbuild` tool paths, `sudo_non_interactive=true`,
and security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum,
isolated legacy compatibility and CVE patch review while modern Windows 10/11,
Linux and macOS defaults remain hardened. Linux records must also
include `native_build_command` and `native_smoke_command` matching the promotion
contract, where the smoke command binds the target id, workflow run URL, workflow
run attempt and source head SHA, plus `linux_smoke_evidence_sha256.native_smoke`, which is the SHA-256 of the captured
`scripts/smoke_linux_native.sh` output from the same builder, and `linux_smoke_summary`,
which exposes the accepted release/run/source, architecture, userland, host identity,
OpenSSL, TLS floor/preference, profile-only legacy crypto scope, weak crypto disabled by
default and modern defaults unchanged values without rereading the raw log. That smoke log
must contain the canonical command, target id, workflow run URL, release tag,
target architecture, sanitized host label, deterministic evidence run ID,
observed-at UTC timestamp, the observed Git HEAD SHA matching the release source head
SHA, all DEB/RPM/AppImage install/verify/upgrade/uninstall lines and the final
pass line for the target architecture. The recorded
`workflow_inputs.release_asset_base_url` must be the exact GitHub release base
URL `https://github.com/<owner>/<repo>/releases/download/vX.Y.Z` and must prefix
every release asset URL in the accepted record. Finalize the candidate with
`python scripts/finalize_platform_verified_evidence_record.py` and append only
that finalized record when the referenced run, release assets, review-bundle
manifest release asset URL binding, review-bundle release asset URLs and
review-bundle hashes are the real promotion evidence. Finalized-record output
and registry append paths must be plain non-symlink files without symlinked
parent directories, and finalization input files must not be symlinks or
traverse symlinked directories. Accepted release
URLs must end in exact safe file names without query strings, fragments or
path-qualified names. The default
`python scripts/check_platform_verified_evidence.py` registry check is
finalized-only, and candidate validation stays inside the generator, bundle
and finalization commands before append. The publish-time asset checker
revalidates finalized accepted evidence before trusting it, compares downloaded
release file SHA-256 values against the accepted `artifact_sha256` map, requires
the finalized review-bundle manifest/archive/SHA-256 sidecar files to be present
with the recorded size, SHA-256 and same-repository release URLs, requires
checksum sidecars to collectively cover every expected non-sidecar file, re-reads
the same-tag review-bundle ZIP contents from a plain non-symlink directory
without symlinked parent directories,
rejects unsafe or symlink-mode archive entries, and reruns finalization against
the accepted registry entries, then rejects Linux
i386/armhf native assets in the default release asset set unless the matching
finalized accepted evidence target is present.
Windows XP native-host readiness can move from remote-target-only only through a
separate XP-capable legacy toolchain with XP x86 SP3 and Windows XP
Professional x64 Edition SP2 VM or physical-host evidence captured with
`scripts/xp_smoke_runner.cmd` using the source metadata printed by the running
`.github/workflows/xp-native-evidence.yml` job, then staged onto a modern
self-hosted `xp-evidence` collector with Python 3.12 and GitHub Actions support
before the bounded wait expires, plus proof that
legacy crypto compatibility stays isolated from modern defaults. XP artifact
directories must pass
`python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <artifact-dir> --tag v<project.version> --strict`
or
`python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <artifact-dir> --tag v<project.version> --strict`.
That strict artifact check rejects symlinked artifact paths, artifact
directories that traverse symlinked parent directories, unsafe ZIP/tar
member names, link/device entries inside native archives and path-qualified
checksum/native-manifest references.
The XP VM/toolchain evidence JSON must also pass
`python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
The evidence JSON path must stay inside a plain non-symlink evidence directory
without symlinked parent directories and must not traverse symlinked path
components. Candidate generation also rejects artifact, XP evidence JSON and XP
evidence directory paths that traverse symlinked directories.
That validator requires the x86 evidence service-pack field to include `SP3`
and the x64 evidence to include `os.service_pack=SP2` plus
`os.edition=Professional x64 Edition`. It also requires a sanitized
`host_identity` block with a lab `host_label`, concrete `evidence_run_id`, UTC
`observed_at_utc`, matching OS/toolchain identity and
`operator_private_data_redacted=true`; do not record real usernames, personal
hostnames, credentials or tokens in XP evidence.
Package the validated XP evidence review artifact with
`python scripts/make_xp_native_evidence_bundle.py --target <windows-xp-native-target> --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-target.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>`; the packer validates the full candidate record and requires the candidate XP validation command to match the bundled evidence inputs. XP accepted records must bind `release_asset_source.workflow=.github/workflows/xp-native-evidence.yml`.
The XP bundle output directory must include the target id and release tag as
path segments, must be plain non-symlink without symlinked parent directories,
and generated bundle files must be plain non-symlink paths.
Before XP evidence upload, `python scripts/stage_xp_native_evidence_upload.py`
stages only the exact native artifact, finalized accepted-record and review
bundle files, then re-checks finalized accepted-record assets before upload and
requires the public final record to use canonical LF-terminated sorted JSON
bytes.
Evidence generated by `python scripts/make_xp_native_evidence_template.py` is
scaffolding only; any remaining `TODO`, `placeholder`, `replace with real` or
`template evidence` marker in the JSON or referenced smoke files fails XP
evidence validation. Its output directory must be plain non-symlink without
symlinked parent directories; `xp-evidence.json`, `xp-smoke-evidence/` and
generated smoke files must be plain non-symlink paths.
The XP evidence JSON must be bundled with per-smoke evidence files for
`cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`,
`artifact_manifest_validation`, `legacy_crypto_profile_scoped` and
`modern_defaults_unchanged`; the validator resolves each relative
`evidence_file` path, requires a concrete `scripts/xp_smoke_runner.cmd`
command on each smoke result that binds the target, release tag, smoke id,
evidence file, canonical `--proof-file xp-smoke-proof/<smoke_id>.txt`,
sanitized `--host-label`, concrete `--evidence-run-id` and
`--observed-at-utc`, `--source-workflow-run-url`, `--source-head-sha` and
`--source-run-attempt` matching the XP evidence JSON `release_source`, plus `--os-name`, `--os-architecture`,
`--os-service-pack` and x64-only `--os-edition`,
requires each smoke evidence file to include `xp smoke target`,
`xp smoke release`, `xp smoke id`, `xp smoke os name`,
`xp smoke os architecture`, `xp smoke os service pack`, x64-only
`xp smoke os edition`, `xp smoke host probe command`, `xp smoke host probe
output`, `xp smoke processor architecture env`, `xp smoke processor
architecture w6432 env`, `xp smoke wmic os caption`,
`xp smoke wmic os csdversion`, `xp smoke host label`, `xp smoke evidence run
id`, `xp smoke observed at utc`, `xp smoke source workflow run`,
`xp smoke source head sha` and `xp smoke source run attempt` proof lines, and
checks the recorded SHA-256. XP smoke proof lines must be exact
single-occurrence bindings; duplicate source, artifact, host, OS or security
proof lines are rejected, and forbidden weak-security proof lines are rejected
case-insensitively.
Accepted XP records generated from that bundle must include `xp_evidence_sha256`
for the evidence JSON, `xp_evidence_summary` for the XP target/release/toolchain/security/smoke
binding, `xp_evidence_summary.release_source` matching `release_asset_source`
for workflow, workflow run URL, head SHA and run attempt,
`workflow=.github/workflows/xp-native-evidence.yml` and
`workflow_inputs` for `target`, `release_tag`, `release_asset_base_url`,
`assets_dir`, `evidence_file` and `evidence_dir`, where the path inputs match
the same `native_evidence_validation_command` reviewed in the XP evidence bundle,
`xp_evidence_sources` binding the evidence JSON and every required XP smoke
evidence file by path, size and SHA-256,
XP security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum,
isolated legacy compatibility and CVE patch review, security smoke proof lines
for `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`, tracked
`scripts/xp_smoke_runner.cmd` per-smoke command provenance in
`xp_evidence_summary.smoke_commands`, `xp_evidence_summary.smoke_evidence_files`
bindings that match each `--evidence-file` command argument, and
canonical `--proof-file xp-smoke-proof/<smoke_id>.txt` command bindings,
`xp_host_identity_sha256` for the sanitized host identity in
`xp_evidence_summary.host_identity`, `--host-label`, `--evidence-run-id` and
`--observed-at-utc` smoke command bindings that match that identity, and
`--os-name`, `--os-architecture`, `--os-service-pack` plus required
`--os-edition` smoke command bindings that match `xp_evidence_summary.os`,
with smoke evidence proof lines from `ver`, `%PROCESSOR_ARCHITECTURE%`,
`%PROCESSOR_ARCHITEW6432%` and `wmic os get Caption,CSDVersion /value`,
`xp_smoke_evidence_sha256` for every
required smoke evidence file, plus `xp_evidence_contract_sha256` for the current
`configs/xp_native_evidence_contract.json`.
Both XP x86 and XP x64 accepted records must be present in
`configs/platform_verified_evidence.json` before the Windows XP native-host row
can promote to 100%. Generate each accepted-record candidate with
`python scripts/make_platform_verified_evidence_record.py` after
`python scripts/check_xp_native_evidence.py` passes, then finalize and append it
with `python scripts/finalize_platform_verified_evidence_record.py` only after
reviewing the XP VM/toolchain evidence bundle and the per-artifact SHA-256
digests recorded for the XP native artifacts. XP candidate generation must pass
`--staged-upload-out-dir platform-evidence-upload/<target>/v<project.version>` and
`--xp-evidence-output-dir <xp-evidence-output-dir>` so the accepted record binds
the staged upload command and the target/release-scoped XP evidence output root.
The same publish-time guard rejects Windows XP native assets unless the registry
passes full finalized accepted-evidence validation, downloaded source artifact
SHA-256 values match the accepted records before staging, post-copy staged
output exact root file sets and pre-copy SHA-256 values match, each artifact
validation command carries one
concrete `--assets-dir`, finalized XP review-bundle files are present in the
release with matching hashes, same-repository release URLs and bundle contents
that re-finalize to the accepted registry entries, and both XP x86 and XP x64
accepted evidence records are present, because one architecture alone does not
prove the Windows XP native-host row.

## MobaXterm parity evidence

The generated feature table is not the gate for true MobaXterm 26.4
Home/Professional product-depth parity. The strict article evidence lives in
`configs/mobaxterm_parity_evidence.json` and is checked by
`python scripts/check_mobaxterm_parity_evidence.py`. The default publish-time
asset checker validates that registry so malformed accepted records cannot ship
quietly. A maintainer can add `--require-mobaxterm-parity-complete` to
`python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag>`
when a release intends to claim complete strict MobaXterm parity; that mode
fails until all seven article IDs have accepted, SHA-bound release evidence
records generated from real passing article verifiers.

## Native installer smoke tests

Every default native installer format has an install, verify, upgrade and
uninstall smoke path before upload:

- Windows `.exe`: silent Inno Setup install into a smoke directory, `row.exe
  --version`, `row-gui.exe` presence on x64/ARM64, silent reinstall, generated
  uninstaller cleanup.
- Windows `.msi`: quiet `msiexec` install, Program Files `row.exe --version`,
  `row-gui.exe` presence on x64/ARM64, quiet reinstall, quiet uninstall.
- macOS `.dmg`: read-only mount, app bundle copy, `codesign --verify`, bundle
  replacement, bundle cleanup and detach.
- macOS `.pkg`: `sudo installer`, `/Applications` app verification, reinstall,
  app removal and receipt cleanup.
- Linux `.deb`: `sudo -n dpkg -i`, `/usr/bin/row --version`, reinstall, `sudo -n dpkg -r`.
- Linux `.rpm`: `sudo -n rpm -Uvh --replacepkgs`, `/usr/bin/row --version`,
  reinstall, `sudo -n rpm -e`.
- Linux AppImage: stage executable copy, `APPIMAGE_EXTRACT_AND_RUN=1
  --version`, overwrite staged copy, remove staged copy.

## Repository cleanup before tagging

Run the normal verifier first, then run the cleanup preflight:

```bash
python scripts/check_repository_cleanup.py
python scripts/check_repository_cleanup.py --require-clean
```

The default cleanup check verifies `.gitignore` coverage for Python caches,
release outputs, native build outputs, workflow download folders, local
`ROW_HOME` data, support bundles and private key/profile/vault file patterns. It
also scans tracked and non-ignored untracked text files for merge-conflict
markers and rejects private/support artifacts that would otherwise be committed.

Use `--require-clean` only immediately before creating the tag. It adds a
`git status --porcelain` requirement so the tag is cut from a fully committed
tree. During ordinary development, the default cleanup check can run while local
work is still in progress.

The tag-triggered core release repeats this protection through actual GitHub
Actions `needs` entries. The `release-preflight` job is a dependency of
`source-and-python`, `windows-native`, `macos-native`, `linux-native`,
`accepted-platform-evidence-assets` and `publish`. The protected evidence jobs
run only on explicit manual opt-in and wait for the completed core release. A
stale manifest, broken verifier check or dirty checkout stops standard assets;
unimportable protected-platform evidence stops only the protected attachment
lane before it can upload anything.

## Phase 1: Python package artifacts

Status: active.

Release assets:

- `remote_ops_workspace-1.0.2-py3-none-any.whl`
- `remote_ops_workspace-1.0.2.tar.gz`
- target source/install bundles for Windows, Linux, macOS, BSD, Solaris,
  Android/Termux, and Web/PWA
- `remote-ops-workspace-v1.0.2-release-manifest.json`
- `remote-ops-workspace-v1.0.2-SHA256SUMS.txt`

Purpose:

- Support Python users and package indexes.
- Give downstream packagers a standard wheel and source distribution.
- Keep the target bundles available for operators who want docs, installers,
  examples, and the Web/PWA shell in one archive.

## Phase 2: Windows native installers

Status: active.

Release assets:

- `remote-ops-workspace-v1.0.2-windows-<x86|x64|arm64>-setup.exe`
- `remote-ops-workspace-v1.0.2-windows-<x86|x64|arm64>.msi`
- `remote-ops-workspace-v1.0.2-windows-<x86|x64|arm64>-native.zip`
- `remote-ops-workspace-v1.0.2-windows-<x86|x64|arm64>-native-manifest.json`
- `remote-ops-workspace-v1.0.2-windows-<x86|x64|arm64>-native-SHA256SUMS.txt`

Implementation:

- Builds a standalone `row.exe` with PyInstaller for x86, x64 and ARM64 builders.
- Builds a no-console `row-gui.exe` PyInstaller launcher for Windows x64 and
  ARM64 portable/installable GUI use. Windows x86 remains CLI-first because
  PyQt6 does not publish 32-bit Windows wheels.
- Adds `Remote Ops Workspace GUI.exe` at the root of GUI-capable native zips so
  portable users can start the desktop UI without opening a terminal.
- Builds an interactive installer with Inno Setup.
- Builds an MSI installer with WiX.
- Runs `scripts/smoke_windows_native.ps1` to smoke install, verify, upgrade and
  uninstall the native portable `.zip`, `.exe` and `.msi` artifacts before
  upload, including `Remote Ops Workspace GUI.exe` in portable zips and
  `row-gui.exe` presence on GUI-capable Windows architectures.
- Pins the Windows installer toolchain in CI: Inno Setup `6.3.3` and WiX
  `5.0.2`.
- Publishes unsigned CI artifacts. Authenticode signing can be layered in when
  release signing credentials are available.
- Treats Windows XP, Vista, Windows 7 and Windows 8.0 as legacy remote targets,
  not as first-class modern native runtime targets. Windows XP x86/x64 remote
  endpoints use isolated per-profile legacy opt-ins.

## Phase 3: macOS native distribution

Status: active.

Release assets:

- `remote-ops-workspace-v1.0.2-macos-<x64|arm64>.dmg`
- `remote-ops-workspace-v1.0.2-macos-<x64|arm64>.pkg`
- `remote-ops-workspace-v1.0.2-macos-<x64|arm64>-native-manifest.json`
- `remote-ops-workspace-v1.0.2-macos-<x64|arm64>-native-SHA256SUMS.txt`

Implementation:

- Builds a PyInstaller `.app` bundle for the PyQt6 GUI entry point.
- Builds a DMG for drag-and-drop installs.
- Builds a PKG for managed installs.
- Runs `scripts/smoke_macos_native.sh` to smoke install, verify, upgrade and
  uninstall the `.dmg` and `.pkg` artifacts before upload.
- Uses ad-hoc signing in CI. Developer ID signing and Apple notarization should
  be added before broad public macOS distribution.

## Phase 4: Linux native packages

Status: active.

Release assets:

- `remote-ops-workspace-v1.0.2-linux-<amd64|arm64>.deb`
- `remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.rpm`
- `remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.AppImage`
- `remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>-native.tar.gz`
- `remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>-native-manifest.json`
- `remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>-native-SHA256SUMS.txt`

Implementation:

- Builds a standalone `row` command with PyInstaller.
- Builds a DEB with `dpkg-deb`.
- Builds an RPM with `rpmbuild`.
- Builds an AppImage with `appimagetool`.
- Runs `scripts/smoke_linux_native.sh` to smoke install, verify, upgrade and
  uninstall the `.deb`, `.rpm` and AppImage artifacts before upload.
- Downloads appimagetool from the maintained `AppImage/appimagetool` upstream
  when a local `APPIMAGETOOL` is not supplied, and supports
  `APPIMAGETOOL_SHA256` verification for pinned binary inputs.
- Keeps `.tar.gz` source/install bundles for non-deb/rpm systems.
- The default GitHub release workflow builds `x86_64` and `aarch64` jobs only.
- The script also maps i386/i686 and armv7l/armhf names for matching builders,
  but those extra outputs are not uploaded by the default GitHub workflow.
- PyInstaller is not cross-compiled by this script; use a matching builder for
  each native CPU.

## Android and Web

Android remains Termux plus Web/PWA until there is a real native Android wrapper.
Do not publish an APK just to wrap the current Python project unless the Android
app has its own tested install and update path.

The CI contract for Android Web/PWA runs `android-emulator-web` across Android
12 through Android 16 (API 31-36), opens the Web/PWA in each emulator, and
uploads screenshot artifacts. Termux ARMv7/ARM64 coverage remains a package and
metadata contract, not a native APK claim.

iOS/iPadOS remains Web/PWA-only until there is a real native iOS wrapper. Do not
publish an `.ipa` or App Store package unless the iOS app has its own tested
install, update and signing path.

The CI contract for iOS/iPadOS Web/PWA runs `ios-simulator-web` on the current
GitHub macOS/Xcode runner. The supported compatibility contract is iOS/iPadOS 15
through 26.x; the live simulator smoke uses the available current iOS runtime.

The Web/PWA release remains a static `.zip` bundle because that is the right
artifact for static hosts, internal portals, and mobile browsers.
