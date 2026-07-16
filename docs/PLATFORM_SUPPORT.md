# Platform Support

## Release assets

Tagged releases publish one source bundle plus one install-oriented bundle for
each public target badge:

| Target | Asset |
|---|---|
| Python wheel | `remote_ops_workspace-1.0.5-py3-none-any.whl` |
| Python sdist | `remote_ops_workspace-1.0.5.tar.gz` |
| Source | `remote-ops-workspace-v1.0.5-source.zip` |
| Windows | `remote-ops-workspace-v1.0.5-windows.zip` |
| Linux | `remote-ops-workspace-v1.0.5-linux.tar.gz` |
| macOS | `remote-ops-workspace-v1.0.5-macos.tar.gz` |
| BSD | `remote-ops-workspace-v1.0.5-bsd.tar.gz` |
| Solaris/illumos | `remote-ops-workspace-v1.0.5-solaris.tar.gz` |
| Android/Termux | `remote-ops-workspace-v1.0.5-android-termux.tar.gz` |
| iOS/iPadOS Web/PWA | `remote-ops-workspace-v1.0.5-web-pwa.zip` |
| Web/PWA | `remote-ops-workspace-v1.0.5-web-pwa.zip` |
| Windows native | `remote-ops-workspace-v1.0.5-windows-<x86\|x64\|arm64>-setup.exe` |
| Windows native | `remote-ops-workspace-v1.0.5-windows-<x86\|x64\|arm64>.msi` |
| Windows native | `remote-ops-workspace-v1.0.5-windows-<x86\|x64\|arm64>-native.zip` |
| macOS native | `remote-ops-workspace-v1.0.5-macos-<x64\|arm64>.dmg` |
| macOS native | `remote-ops-workspace-v1.0.5-macos-<x64\|arm64>.pkg` |
| macOS native | `remote-ops-workspace-v1.0.5-macos-<x64\|arm64>-native-manifest.json` |
| Linux native | `remote-ops-workspace-v1.0.5-linux-<amd64\|arm64>.deb` |
| Linux native | `remote-ops-workspace-v1.0.5-linux-<x86_64\|aarch64>.rpm` |
| Linux native | `remote-ops-workspace-v1.0.5-linux-<x86_64\|aarch64>.AppImage` |
| Linux native | `remote-ops-workspace-v1.0.5-linux-<x86_64\|aarch64>-native.tar.gz` |
| Linux native | `remote-ops-workspace-v1.0.5-linux-<x86_64\|aarch64>-native-manifest.json` |
| Manifests | `remote-ops-workspace-v1.0.5-*-manifest.json` |

The platform bundles include source, docs, examples, relevant installer entry
points, and per-target release notes. They are not native protocol-client
bundles; SSH/RDP/VNC/X11/SPICE/X2Go/ICA rendering still depends on the external
clients available on the target system.

Native `.exe`, `.msi`, `.dmg`, `.pkg`, `.deb`, `.rpm`, and AppImage artifacts
are built by OS-specific release jobs or matching self-hosted builders. Windows
and macOS artifacts are unsigned CI builds until release signing credentials are
configured. APK-style artifacts remain out of scope until there is a real native
Android wrapper. iOS/iPadOS support is Web/PWA only; no native `.ipa` artifact
is published.

Native installer smoke coverage is declared in
`configs/native_installer_smoke.json` and checked by
`python scripts/check_native_installer_smoke.py`. The default release workflow
runs `scripts/smoke_windows_native.ps1`, `scripts/smoke_macos_native.sh` and
`scripts/smoke_linux_native.sh` after native builds and before upload. Those
smokes cover install, verify, upgrade and uninstall paths for Windows `.exe`
and `.msi`, macOS `.dmg` and `.pkg`, and Linux `.deb`, `.rpm` and AppImage
artifacts.

## Release matrix decision

The publishing contract is declared in `configs/release_matrix.json` and checked
by `python scripts/check_release_matrix.py`. It separates the broad platform
catalog from the smaller set of files uploaded by the default GitHub release:

- Default GitHub release: Python wheel/sdist, source/install bundles, Windows
  `x86`/`x64`/`arm64` native artifacts, macOS `x64`/`arm64` native artifacts and
  Linux `x86_64`/`aarch64` native artifacts.
- Script-supported native: Linux `i386`/`i686` and `armhf` outputs. The build
  script maps those architectures, but they are not uploaded by the default
  GitHub release workflow unless a maintainer runs and verifies a matching
  builder.
- Source, Web/PWA or remote-target only: BSD, Solaris/illumos, Android
  Termux/Web/PWA, iOS/iPadOS Web/PWA, and legacy Windows endpoints do not
  receive default native app installers. Windows XP x86/x64 remote endpoints
  use isolated per-profile legacy opt-ins.

Architecture support is declared in `configs/platform_targets.json`, release
publishing policy is declared in `configs/release_matrix.json`, and
`python scripts/check_platform_support_truth.py` verifies that the catalog,
release matrix, generated readiness scores and platform docs keep the same
default-native, script-supported, Termux/Web, Web/PWA and legacy remote-target
meaning.
The same catalog carries a top-level `protected_readiness_goal` contract for
Linux i386, Linux armhf and Windows XP native-host readiness. That contract sets
a `static_catalog_boundary` of `not native-host/readiness proof`, keeps
`status_source` pointing at `configs/platform_verified_evidence.json`, records
the accepted-evidence and protected-goal gate commands, and names the
`release_asset_provenance_gate` that must run with `--assets-dir` before
published native bytes can count as proven.
Its JSON consumer guidance is explicit:
`row platforms --json is the static platform catalog; use row features --coverage --json`
for the evidence-backed readiness report.
The generated platform verified readiness overall is scoped to verified
default-native, Termux/Web and Web/PWA release targets. Manual Linux i386/armhf
and legacy Windows rows remain visible as extended compatibility rows outside
the verified-readiness denominator.

## Promotion to 100% for extended targets

Linux i386/armhf and Windows XP native-host promotion to 100% is gated by
`configs/platform_parity_promotion.json` and
`python scripts/check_platform_parity_promotion.py`. Real promotion artifact
sets are validated with `python scripts/check_platform_promotion_artifacts.py`.
The checked operator runbook is `docs/PLATFORM_PROMOTION_RUNBOOK.md`, and
`python scripts/check_platform_promotion_runbook.py` keeps its target ids,
blockers, artifact names and validation commands aligned with the promotion
contract.
Manual Linux i386/armhf evidence builders run through
`.github/workflows/extended-platform-evidence.yml`; XP native evidence is
staged and uploaded through `.github/workflows/xp-native-evidence.yml`, which
prints the source run metadata, waits for the collector-side staged files, and
then runs `python scripts/check_xp_native_evidence.py` against the sanitized XP
evidence JSON and smoke files. Accepted promotion records are stored in
`configs/platform_verified_evidence.json` and checked by
`python scripts/check_platform_verified_evidence.py`; until that registry has
accepted records, the generated readiness report must keep the current partial
rows. The strict promotion path is
`python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets`,
`python scripts/check_platform_evidence_runner_readiness.py --repository <owner>/<repo> --require-goal-targets --require-idle`,
`python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-records-complete`,
`python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag v<project.version>`
and `python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> --release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>`;
that strict verifier audits the intended already-published GitHub release, exact source-run
metadata, published native/review-bundle asset bytes and published final
accepted-record JSON bytes.
The source-ref gate must run before dispatch: it resolves the release tag to a
commit, checks the tagged project version, and proves both evidence workflows
and all four protected target options exist at that tag. A tag created before
those workflows existed cannot be promoted by running a newer workflow from
`main`; promotion requires a new tag whose source commit contains the evidence
workflows.

The runner-readiness gate must run immediately before dispatch. It checks only
sanitized counts for required self-hosted label sets and requires an idle Linux
i386 runner, an idle Linux armhf runner, and an idle modern `xp-evidence`
collector. It requires a GitHub token with repository administration read
access and does not broaden normal release-token permissions.
those commands must fail until linux-i386, linux-armhf,
windows-xp-native-x86 and windows-xp-native-x64 all have accepted records for
the same release tag, same GitHub release repository, same release source head
SHA and positive per-record release source run attempts. Mixed-tag,
mixed-repository, mixed-source-head or same-run-URL conflicting-attempt accepted records remain
aggregate evidence only and cannot complete the protected goal parity block.
The strict verifier also runs
`python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>`
then `python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete --assets-dir <release-assets-dir> --repository <owner>/<repo>`
and `python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets`,
so accepted records must be release-importable, bound to the current checkout
head, backed by completed successful dispatch runs, hash-checked as downloaded
source artifacts before being copied into the release asset directory, bound to
the publishing repository and matched by the downloaded release asset directory
before promotion is trusted.
The generated static readiness report keeps
`release_asset_provenance_complete=false`; only the asset-backed protected goal
gate can flip that proof state after finalized records, review bundles and
native release bytes match in the publish-ready asset directory.
It also exposes `record_complete` separately from `release_backed_complete`, so
accepted records and source-run provenance cannot be mistaken for published
release-byte proof.
Each protected Linux i386/armhf and Windows XP readiness row also exposes
`accepted_evidence_record_complete`, `release_asset_provenance_complete=false`,
`release_backed_readiness_complete=false` and `static_readiness_evidence_scope`
so row-level JSON cannot imply published asset-byte proof until the
asset-backed protected goal gate runs with `--assets-dir`.
Source artifact inventory checks bind `workflow_run.id`,
`workflow_run.head_sha`, `workflow_run.repository_id` and
`workflow_run.head_repository_id` from exact source-run metadata, reject
artifact `created_at` values outside the exact source run creation/start/update window
from exact source-run timestamps, require artifact `expires_at` to be present
and later than the artifact create/update timestamps, and compare the finalized public record asset to canonical
accepted-record JSON bytes before a published release can pass the live audit.
The live remote audit
(`python scripts/check_platform_release_evidence_remote.py`) also requires each
published protected-platform release asset to expose a positive GitHub release
asset ID and the matching GitHub API asset URL for the release repository.
Generate candidate accepted records with
`python scripts/make_platform_verified_evidence_record.py` after artifact and
XP evidence validators pass; package the review bundle, then use
`python scripts/finalize_platform_verified_evidence_record.py --append-registry`
only after the finalized record binds the real release/run evidence, review
bundle manifest, review bundle archive, review bundle SHA-256 sidecar and
source artifact staged upload command. Candidate generation must pass
`--staged-upload-out-dir platform-evidence-upload/<target>/v<project.version>`, and XP candidates must
also pass `--xp-evidence-output-dir <xp-evidence-output-dir>`.
Linux release-source upload staging must use
`python scripts/stage_extended_linux_evidence_upload.py`, and XP release-source
upload staging must use `python scripts/stage_xp_native_evidence_upload.py`;
both stagers re-check finalized accepted-record assets before upload and require
the public final record to use canonical LF-terminated sorted JSON bytes.
`python scripts/check_platform_verified_evidence.py` checks the persisted
registry in finalized-only mode. Candidate validation happens through the
candidate-generation, review-bundle and finalization commands before append.
Review bundle archives must include every native artifact recorded in their
bundle manifests as safe relative non-symlink ZIP entries, so reviewers can
verify the artifact bytes as well as the metadata, smoke logs and candidate
record.
Accepted records must include release asset URLs, per-artifact SHA-256 digests
for every required promotion artifact, and the promotion config SHA-256 for the
current `configs/platform_parity_promotion.json` contract. Every release asset
URL must use the same `/releases/download/<tag>/` segment as the record
`release_tag`.
The URL and hash filename sets must exactly match the target's required
artifact names; missing, duplicate or extra files keep the row partial. Staged
Linux and XP promotion artifact directories and contained files must be plain
non-symlink paths, native manifest payload records must bind the expected
target architecture and package/container format for each payload, and evidence
bundle output directories must include the target id and release tag as path
segments. Promotion uploads must also verify
native artifact and review-bundle file hashes against the finalized accepted
record before upload, and the release importer performs the same native
artifact SHA-256 plus review-bundle size/SHA-256 checks on the downloaded source
artifact before copying into `release-assets`.
The accepted record's artifact validation command must also use the same target
id, exactly one concrete `--assets-dir` value and exactly one `--tag` value
matching the record. Placeholder paths such as `<artifact-dir>` are valid in
documentation examples only, not in accepted evidence records. Linux and XP
accepted evidence command paths must include both the target id and release tag
as path segments.
All release asset URLs in one accepted record must use the same GitHub
repository, and Linux i386/armhf workflow run URLs must point to that repository
too.
Linux i386/armhf records must
also include the builder identity JSON emitted by
`python3 scripts/check_extended_platform_builder.py --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --out ...`, including
the same `release_tag`, `workflow_run_url` and `workflow_run_attempt` as the accepted record, plus `workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` matching `release_asset_source.head_sha`, `git_worktree_clean=true`, a
native smoke log with exact single-occurrence proof lines and case-insensitive
rejection of forbidden weak-security proof lines, a
sanitized target-scoped `host_identity` block with
`operator_private_data_redacted=true`, matching `platform.machine()`,
`uname -m`, `dpkg --print-architecture`
(`i386` for linux-i386 or `armhf` for linux-armhf), `getconf LONG_BIT=32`,
concrete `rpm`/`rpmbuild` tool paths and `sudo_non_interactive=true`, plus a `builder_identity_sha256` that
matches that JSON and security patch evidence proving TLS 1.3 preferred,
TLS 1.2 minimum, isolated legacy compatibility and CVE patch review while
modern Windows 10/11, Linux and macOS defaults remain hardened. The
`security_update_channel` and `cve_review_reference` values must name a
concrete update/advisory namespace such as security-updates, KB, USN, RHSA,
DSA, CVE, GHSA or an HTTPS advisory, not just a generic review label. The
accepted record must also carry a
`native_build_command` and `native_smoke_command` matching the promotion
contract, where the Linux smoke command includes the target id, workflow run
URL, workflow run attempt and source head SHA, and the captured smoke log proves
the observed Git HEAD SHA matches that source head SHA plus the sanitized host
label, deterministic evidence run ID and observed-at UTC timestamp, a `linux_smoke_evidence_sha256.native_smoke`
digest for the captured native smoke log, and a `linux_smoke_summary` that repeats the
accepted release/run/source, architecture, userland, host identity, OpenSSL and
profile-only legacy crypto scope facts in structured form. Evidence files must use target-scoped names
`builder-identity-<target>.json`, `native-smoke-<target>.log` and
`platform-verified-evidence-<target>.json`, and whose content must include the canonical smoke command, target id,
workflow run URL, release tag, target architecture, host label, evidence run ID,
observed-at timestamp, every DEB/RPM/AppImage
install/verify/upgrade/uninstall line and the final pass line, plus
`workflow_inputs` that bind the dispatch target, release tag and release asset
base URL to the record. Windows
XP records must include `xp_evidence_sha256` for the validated evidence JSON,
`workflow=.github/workflows/xp-native-evidence.yml` and `workflow_inputs`
that bind the dispatch `target`, `release_tag`, `release_asset_base_url`,
`assets_dir`, `evidence_file` and `evidence_dir` to the record and to
`native_evidence_validation_command`,
`xp_evidence_sources` that bind the evidence JSON path, file size and SHA-256
plus every required smoke evidence file path, size and SHA-256,
`xp_evidence_summary` for the XP target/release/toolchain/security/smoke
binding, `xp_evidence_summary.release_source` matching `release_asset_source`
for workflow, workflow run URL, head SHA and run attempt,
`xp_host_identity_sha256` for the sanitized XP host identity in
`xp_evidence_summary.host_identity`, required XP security patch evidence with
the same concrete update/advisory provenance rule,
security smoke proof lines for `legacy_crypto_profile_scoped` and
`modern_defaults_unchanged`,
tracked `scripts/xp_smoke_runner.cmd` per-smoke command provenance in
`xp_evidence_summary.smoke_commands`,
`xp_evidence_summary.smoke_evidence_files` bindings that match each
`--evidence-file` command argument, canonical
`--proof-file xp-smoke-proof/<smoke_id>.txt` command bindings, and
`--host-label`, `--evidence-run-id` and `--observed-at-utc` command bindings
that match `xp_evidence_summary.host_identity`, plus
`--source-workflow-run-url`, `--source-head-sha` and `--source-run-attempt`
bindings that match `xp_evidence_summary.release_source`, plus `--os-name`,
`--os-architecture`, `--os-service-pack` and required `--os-edition` command
bindings that match `xp_evidence_summary.os`,
`xp_smoke_evidence_sha256` for each required smoke evidence file, and
`xp_evidence_contract_sha256` for the
current XP evidence contract. Each smoke evidence file must include proof lines
for `xp smoke target`, `xp smoke release`, `xp smoke id`, `xp smoke os name`,
`xp smoke os architecture`, `xp smoke os service pack`, required
`xp smoke os edition`, `xp smoke host probe command`, `xp smoke host probe
output`, `xp smoke processor architecture env`, `xp smoke processor
architecture w6432 env`, `xp smoke wmic os caption`,
`xp smoke wmic os csdversion`, `xp smoke host label`, `xp smoke evidence run
id`, `xp smoke observed at utc`, `xp smoke source workflow run`,
`xp smoke source head sha` and `xp smoke source run attempt` exactly once;
duplicated source, artifact, host, OS or security proof lines are rejected.
Forbidden weak-security proof lines are rejected case-insensitively.
These exact single-occurrence bindings prevent copied evidence from another
target, smoke, release tag, lab host, evidence run, observed timestamp,
operating system, architecture, service pack, edition, Windows version probe or
processor architecture from promoting; smoke evidence paths must
also be plain non-symlink files under `xp-smoke-evidence/`. The current XP
evidence contract requires XP x86
SP3 evidence and Windows XP Professional x64 Edition SP2 evidence before either
native-host row can promote.
The accepted evidence registry also rejects duplicate target records, and
Windows XP x86/x64 native evidence must use the same `release_tag` and must
not reuse one source workflow run URL with conflicting accepted run attempts
before the Windows XP native-host row can promote.
The generated `platform_verified_readiness` rows expose
`accepted_evidence_required_targets`, `accepted_evidence_present_targets` and
`accepted_evidence_missing_targets` so partial Linux or XP promotion evidence is
visible without changing the current readiness percentage. The same JSON block
also exposes `protected_goal_parity`, which is the authoritative four-target
parity score for linux-i386, linux-armhf, windows-xp-native-x86 and
windows-xp-native-x64. The broader `overall` score only covers verified-scope
default/mobile targets and does not mean the protected goal is complete.
Protected platform goal parity is **0.0%** for the current accepted-evidence
registry (status=missing-accepted-evidence); it remains separate from the
100.0% overall verified-readiness denominator until all four protected targets
have real accepted evidence for one release source.

Current readiness:

- Linux i386: 70.0%, script-supported native. Promotion requires a real
  i386/i686 release builder, default `linux-native` release matrix membership,
  upload/publish asset coverage, `scripts/make_linux_native.sh` output,
  `scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`, native
  manifest evidence, checksum sidecars and
  `python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
  The dispatch-only evidence workflow uses a `[self-hosted, linux, i386]`
  runner and uploads `extended-linux-evidence-linux-i386-v<project.version>`, including
  `builder-identity-linux-i386.json` and
  `native-smoke-linux-i386.log` inside the review bundle, plus
  `platform-verified-evidence-linux-i386.json` as the reviewed registry-record
  candidate. The accepted record's `release_asset_source.workflow` must be `.github/workflows/extended-platform-evidence.yml`,
  and `release_asset_source.run_attempt` must be a positive GitHub Actions run attempt.
  That builder identity must prove `workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` matching the release source head SHA, `git_worktree_clean=true`, `workflow_run_attempt` matching the release source run attempt, `dpkg --print-architecture=i386`,
  `getconf LONG_BIT=32`, concrete `rpm`/`rpmbuild` tool paths and `sudo_non_interactive=true`, plus a target/release-scoped review bundle from
  `python scripts/make_extended_linux_evidence_bundle.py --target linux-i386 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-i386.json> --out-dir <target-release-artifact-dir>`.
- Linux armhf: 70.0%, script-supported native. Promotion requires a real
  armv7l/armhf release builder, default `linux-native` release matrix
  membership, upload/publish asset coverage, `scripts/make_linux_native.sh`
  output, `scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`,
  native manifest evidence, checksum sidecars and
  `python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
  The dispatch-only evidence workflow uses a `[self-hosted, linux, armhf]`
  runner and uploads `extended-linux-evidence-linux-armhf-v<project.version>`, including
  `builder-identity-linux-armhf.json` and
  `native-smoke-linux-armhf.log` inside the review bundle, plus
  `platform-verified-evidence-linux-armhf.json` as the reviewed registry-record
  candidate. The accepted record's `release_asset_source.workflow` must be `.github/workflows/extended-platform-evidence.yml`,
  and `release_asset_source.run_attempt` must be a positive GitHub Actions run attempt.
  That builder identity must prove `workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` matching the release source head SHA, `git_worktree_clean=true`, `workflow_run_attempt` matching the release source run attempt, `dpkg --print-architecture=armhf`,
  `getconf LONG_BIT=32`, concrete `rpm`/`rpmbuild` tool paths and `sudo_non_interactive=true`, plus a target/release-scoped review bundle from
  `python scripts/make_extended_linux_evidence_bundle.py --target linux-armhf --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-armhf.json> --out-dir <target-release-artifact-dir>`.
- Windows XP native host: 25.0%, remote-target-only as a local operator host
  row. Promotion requires a separate XP-capable legacy toolchain, XP x86 SP3
  and Windows XP Professional x64 Edition SP2 VM or physical-host smoke
  evidence captured with `scripts/xp_smoke_runner.cmd`, native artifact evidence, and
  security proof that weak TLS/SSH/RDP compatibility remains profile-scoped and
  never lowers modern OS defaults. Validate XP artifact sets with
  `scripts/make_windows_xp_legacy.ps1 -Arch x86` and
  `scripts/make_windows_xp_legacy.ps1 -Arch x64` to create separate .NET Framework
  v4 WinForms candidate archives. These local candidate builds do not count as XP
  host proof and do not alter modern Python/PyQt6 defaults. Then validate with
  `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <artifact-dir> --tag v<project.version> --strict`
  and
  `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <artifact-dir> --tag v<project.version> --strict`.
  Start collection with
  `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x86 --release-tag v<project.version> --out-dir <evidence-dir>`
  or
  `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x64 --release-tag v<project.version> --out-dir <evidence-dir>`;
  the generated template is intentionally incomplete and must fail validation
  until real XP evidence replaces the placeholders. The XP evidence validator
  rejects leftover `TODO`, `placeholder`, `replace with real` and
  `template evidence` markers in both the JSON file and referenced smoke
  evidence files, and requires a sanitized `host_identity` block instead of
  real usernames, personal hostnames, credentials or tokens.
  Package release-importable XP evidence with
  `.github/workflows/xp-native-evidence.yml` on a modern self-hosted
  `xp-evidence` collector with Python 3.12 and GitHub Actions support. Dispatch
  the workflow first, use its printed workflow run URL, source head SHA and run
  attempt when running `scripts/xp_smoke_runner.cmd` on the real XP host, then
  stage the native artifacts, evidence JSON and smoke files onto the collector
  while the workflow waits; the collector workflow validates staged proof and uploads
  `xp-native-evidence-<target>-<release_tag>` for the release importer. Its
  generated candidate record, final record and review bundle must
  stay under `xp-evidence-output/<target>/<release_tag>`. Its assets_dir,
  evidence_file and evidence_dir dispatch paths must be workspace-relative and
  include the XP target id plus release tag as path segments, for example
  `staged/windows-xp-native-x86/v<project.version>/...`.
  The `legacy_crypto_profile_scoped` smoke file must include
  `legacy compatibility profile: isolated-opt-in`,
  `legacy crypto scope: profile-only` and `weak crypto global default: false`.
  The `modern_defaults_unchanged` smoke file must include
  `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`,
  `modern defaults unchanged: true` and `weak crypto global default: false`.
  Import the VM/toolchain smoke bundle with
  `python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
  Package validated XP evidence for review with
  `python scripts/make_xp_native_evidence_bundle.py --target <windows-xp-native-target> --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-target.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>`.
  The accepted record must carry the evidence JSON SHA-256, the sanitized XP
  host identity SHA-256 and all required smoke evidence SHA-256 values from
  that validated bundle, plus `xp_evidence_summary.release_source` matching
  `release_asset_source`.
  Each required XP smoke result must reference a bundled evidence file, resolved
  relative to the evidence JSON directory unless `--evidence-dir` is supplied,
  must record the concrete command/action that produced that evidence, must bind
  the sanitized host label, evidence run ID, release source workflow run URL,
  release source head SHA and release source run attempt in both the command and
  smoke file, and the recorded SHA-256 must match that file.

The broad support catalog is exposed with:

```bash
row platforms
row platforms --json
```

The human `row platforms` output includes an `Evidence-backed protected
readiness` section. That section prints the protected platform goal percentage,
the `Release asset provenance` state, missing accepted evidence targets and the
explicit warning that the static platform catalog is not native-host/readiness
proof for Linux i386/armhf or Windows XP. The `row platforms --json` output
stays the static catalog from `configs/platform_targets.json`; its
`protected_readiness_goal` metadata repeats the protected target list, accepted
evidence source, security boundary and asset-provenance gate, but the
evidence-backed score still comes from `row features --coverage --json`.
The human `row features --coverage` platform rows add a protected-row note such
as `accepted records/release assets pending` until the accepted records and
asset-backed release byte checks both exist.

## Windows and Windows Server

Target support:

- Windows 10/11 on x86, x64 and ARM64 where a matching Python/PyInstaller build exists.
- Windows Server 2012, 2012 R2, 2016, 2019, 2022 and 2025.
- Windows 8.1 as a best-effort source install and remote target.
- Windows 8 and Windows 7 as legacy source-only or remote-target systems.
- Windows Vista and Windows XP as remote targets only.

Legacy Windows support means this project can store profiles, generate adapter
commands, and connect to those systems through RDP, VNC, SSH, Telnet, serial
consoles or raw sockets when the chosen external client can still negotiate the
old protocol. The modern Python 3.10+/PyQt6 native release stack does not make
XP, Vista, Windows 7 or Windows 8.0 first-class local operator hosts.
Windows XP remote-target coverage is 100.0% for x86 and x64 endpoints in the
legacy remote-target contract. Weak SSH algorithms, SSHv1 and FreeRDP
`security=rdp` remain disabled unless the profile declares
`legacy_target=windows-xp-32` or `windows-xp-64` and sets the matching
`allow_legacy_crypto=true` or `allow_legacy_rdp_security=true` opt-in.
Generic XP labels such as `xp`, `winxp` and `windows-xp`, and the
`legacy_platform` alias key, do not unlock those legacy exceptions.

Architecture targets:

- x86: 32-bit Windows native artifacts from a 32-bit Python/PyInstaller build;
  CLI-first because PyQt6 does not publish 32-bit Windows wheels.
- x64: default 64-bit Windows native artifacts with `bin\row.exe` and
  double-clickable `Remote Ops Workspace GUI.exe` in portable zips.
- ARM64: native Windows ARM64 artifacts from an ARM64 Windows builder with
  `bin\row.exe` and double-clickable `Remote Ops Workspace GUI.exe` in portable zips.

For the Windows x64 or ARM64 portable zip, extract the archive and double-click
`Remote Ops Workspace GUI.exe` to start the desktop UI. The same zip also keeps
`bin\row-gui.exe` and `bin\row.exe` for scripted workflows and automation. In
frozen Windows native packages, `row gui` delegates to the sibling
`bin\row-gui.exe` launcher.

Recommended external clients:

- OpenSSH Client for SSH/SFTP/SCP.
- MSTSC for RDP.
- PuTTY for serial, SSH fallback and Telnet fallback.
- VcXsrv for X11 display workflows.
- TigerVNC/RealVNC for VNC.

Install:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\installers\install.ps1
row doctor
```

## Linux

Target distributions include Ubuntu, Debian, Linux Mint, Kali, Fedora, RHEL, Rocky Linux, AlmaLinux, Oracle Linux, CentOS Stream, openSUSE, Arch, Manjaro, Gentoo and Alpine.

Native package architecture mappings:

- i386/i686: 32-bit x86 Linux packages, script-supported only.
- x86_64/amd64: default 64-bit x86 Linux packages.
- armv7l/armhf: 32-bit ARM Linux packages, script-supported only.
- aarch64/arm64: default 64-bit ARM Linux packages.

The Linux native script maps these architectures, but it does not cross-compile
PyInstaller binaries. Run `scripts/make_linux_native.sh` on the requested
architecture, in a matching container, or on a matching self-hosted runner.

Recommended external clients:

- OpenSSH.
- FreeRDP.
- TigerVNC.
- virt-viewer.
- x2goclient.
- mosh.
- Xorg/Wayland display tooling.

## Unix/BSD

Target systems include FreeBSD, OpenBSD, NetBSD, DragonFlyBSD and other POSIX-like operator hosts with Python 3.10+.

Use the CLI and Web/PWA first. GUI support depends on local PyQt6 availability.

## Solaris/illumos

Use the CLI and Web/PWA first. GUI support depends on local Python/Qt packages. OpenSSH, serial tools, browser launching and raw sockets are the safest initial workflows.

## macOS

Target support:

- macOS Intel.
- macOS Apple Silicon.

Recommended external clients:

- OpenSSH.
- XQuartz for X11.
- Microsoft Remote Desktop or FreeRDP for RDP.
- VNC viewers.

## Android

Target workflows:

- Web/PWA from a browser.
- CLI through Termux with Python and OpenSSH on ARMv7 and ARM64 devices where
  Termux packages are available.
- Android 12 through Android 16 (API 31-36) Web/PWA emulator CI through the
  `android-emulator-web` job.

Termux example:

```bash
pkg update
pkg install python git openssh
python -m venv .venv
. .venv/bin/activate
pip install -e .
row init
row welcome
row doctor
```

## iOS/iPadOS

Target workflows:

- Web/PWA from Safari or another trusted browser.
- Static Web/PWA asset from `remote-ops-workspace-v1.0.5-web-pwa.zip`.
- iOS/iPadOS 15 through 26.x Web/PWA compatibility contract.
- Live simulator smoke on the current GitHub macOS/Xcode runtime through the
  `ios-simulator-web` job.

iOS/iPadOS support is Web/PWA only; no native `.ipa` artifact is published.
The Python CLI and PyQt6 desktop GUI are not supported as local iOS apps. Use
the Web/PWA from a trusted HTTPS origin or internal portal, then add it to the
Home Screen when an installed PWA-style launch icon is needed.

## Web

`apps/web` is static and can be served by the included Python HTTP server, Nginx, Apache, Caddy, a static host, or an internal portal. The included server binds to loopback by default and requires `--allow-public-bind` for non-loopback interfaces. The web Docker compose file publishes `127.0.0.1:8765` by default.
