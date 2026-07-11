# Platform Promotion Runbook

This runbook is the operator path for truthful 100% readiness promotion of
Linux i386, Linux armhf and Windows XP native-host targets. It does not promote
any target by itself. Promotion happens only when accepted evidence records are
added to `configs/platform_verified_evidence.json` and all verification gates
pass.
The default-versus-script-supported release boundary comes from
`configs/release_matrix.json` and is checked by
`python scripts/check_release_matrix.py`; this runbook carries the protected
script-supported artifact names that must stay aligned with that matrix.

Start with the shared gates:

```bash
python scripts/check_platform_parity_promotion.py
python scripts/check_platform_verified_evidence.py
python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-records-complete
python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag v<project.version>
python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets
python scripts/check_platform_evidence_runner_readiness.py --repository <owner>/<repo> --require-goal-targets --require-idle
python scripts/check_release_publish_assets.py
python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete --assets-dir <release-assets-dir> --repository <owner>/<repo>
python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> --tag v<project.version> --repository <owner>/<repo> --require-platform-goal-targets
python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> --release-assets-dir <release-assets-dir> --release-repository <owner>/<repo>
python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head
```

Run the source-ref gate before either evidence workflow dispatch. It resolves
the release tag to its commit, verifies the tagged `pyproject.toml` version and
requires both protected-platform workflow files plus all four target dispatch
options to exist at that exact tag. A release created before either evidence
workflow was added cannot be promoted retroactively under the same-tag and
same-source-SHA policy; create a new release tag from a commit containing the
workflows instead of dispatching from `main` or weakening source provenance.

Run the runner-readiness gate immediately before dispatch as well. It reads the
repository self-hosted runner inventory and requires an idle matching runner for
Linux i386, Linux armhf, and the modern `xp-evidence` collector. It intentionally
reports only sanitized counts, not runner names. This command needs `GH_TOKEN`
or `GITHUB_TOKEN` with repository administration read access; it is an operator
preflight rather than a release-workflow step because normal release tokens do
not need runner-inventory access.

Accepted records must start as candidates generated with
`python scripts/make_platform_verified_evidence_record.py`, then the review
bundle must be packaged and bound back into the record with
`python scripts/finalize_platform_verified_evidence_record.py`. Append only the
finalized record with `--append-registry` when the referenced run, review
bundle and release assets are the real promotion evidence.
Candidate generation must bind the exact release upload staging root with
`--staged-upload-out-dir platform-evidence-upload/<target>/v<project.version>`; XP candidate generation
must also bind `--xp-evidence-output-dir <xp-evidence-output-dir>` so the staged
upload command in the record matches the target/release-scoped XP review-bundle
output root.
`python scripts/check_platform_verified_evidence.py` validates
`configs/platform_verified_evidence.json` in finalized-only mode and rejects
candidate-only CLI validation. Candidate checks run through the
candidate-generation, bundle and finalization workflow before registry append.
Finalization reruns strict accepted-evidence validation on the unfinalized
candidate before attaching review-bundle fields, so a hand-edited candidate
cannot rely on finalization to hide missing command, evidence, source-run or
local-preflight bindings.
The strict `--require-records-complete`, `--require-goal-targets` and
`--require-platform-goal-targets`
commands must fail until linux-i386, linux-armhf, windows-xp-native-x86 and
windows-xp-native-x64 all have finalized accepted evidence records.
The protected-goal report exposes this as `record_complete`; that is only an
accepted-record/source-run state. `release_backed_complete` remains false until
the asset-backed `--assets-dir` gate below validates the actual final records,
review bundles and native release files.
When a release tag is supplied, all four accepted records must match that exact
tag, one GitHub release repository, the target-specific release source workflow
file and one release source head SHA, and each record must bind a positive
release source run attempt; stale evidence from a
previous release, different repository, different source commit or stale run
attempt cannot promote a newer release.
The strict `python scripts/verify.py --require-platform-goal-targets` command
also runs
`python scripts/import_platform_evidence_artifacts.py --release-tag v<project.version> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>`
against the supplied release tag and release asset directory, proving the
accepted records are release-importable, bound to the current checkout head and
backed by exact completed successful dispatch runs at the accepted run id,
attempt, workflow path and source SHA with a complete artifact inventory
containing exactly one non-expired, non-empty expected source artifact before
downloaded bundle and publish-asset validation can pass. It then runs
`python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete --assets-dir <release-assets-dir> --repository <owner>/<repo>`
so the protected parity gate fails if the accepted final records, review
bundles or native artifacts are missing from the actual publish-ready release
asset directory. The static readiness report still keeps
`release_asset_provenance_complete=false`; only this asset-backed protected goal
gate can flip the proof state after finalized records, review bundles and
native release bytes match. When `--release-repository <owner>/<repo>` is
supplied, the same strict verifier also runs
`python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag v<project.version> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head`
against the actual GitHub release, published native/review-bundle asset bytes,
published final accepted-record JSON bytes, exact accepted source workflow run
attempts and the published tag's source head. The remote auditor's
`--require-goal-targets` mode refuses weaker published-release audits unless
all four strict proof flags are present.
Every accepted release asset URL must use the same `/releases/download/<tag>/`
segment as the record's `release_tag`.
All release asset URLs in one accepted record must come from the same GitHub
repository; Linux i386/armhf records must also use a `workflow_run_url` from
that same repository.
Release-imported evidence artifacts are downloaded only from the accepted
record's `release_asset_source.workflow_run_url` after the release importer
confirms the GitHub Actions run is `completed`, concluded `success`, and came
from a `workflow_dispatch` event. The exact run attempt's workflow file path
must match `release_asset_source.workflow`. The run's `headSha` must match both
`release_asset_source.head_sha` in the accepted record and the release
checkout commit, the run's attempt number must match
`release_asset_source.run_attempt`, and both `repository.full_name` and
`head_repository.full_name` in the exact run metadata must match the repository
in `release_asset_source.workflow_run_url`. The run artifact inventory must be complete:
its `total_count` must match the fetched artifact list length, it must contain
exactly one `release_asset_source.artifact_name` entry, and that artifact must
not be expired or empty. The matched artifact metadata must also bind
`workflow_run.id` and `workflow_run.head_sha` to the accepted source run and
commit, and when exact run metadata exposes repository IDs the artifact
`workflow_run.repository_id` and `workflow_run.head_repository_id` must match
that same exact source run. When GitHub exposes timestamps, the artifact
`created_at` must stay inside the exact source run creation/start/update window. Failed,
still-running, unrelated, wrong-attempt, wrong-commit,
wrong-artifact-run, missing-artifact, expired-artifact or empty-artifact source
runs are not valid release artifact provenance even when an artifact name
matches.
The same release source workflow run URL cannot carry conflicting accepted run
attempts across protected-platform records for one release; that ambiguity is
aggregate evidence only and cannot complete the parity block.
The release workflow's `accepted-platform-evidence-assets` job must keep only
read permissions for repository content and Actions artifacts; no write-scoped
GitHub permission is acceptable for importing protected-platform evidence.
The downloaded source artifact must contain exactly the expected release and
review-bundle files at artifact root; extra files, private raw logs and nested
builder output directories are rejected before anything is copied into the
release asset directory.
The release importer also checks downloaded source artifact native artifact
SHA-256 values, review-bundle file sizes and review-bundle SHA-256 values
against the finalized accepted record before copying into `release-assets`.
The recorded artifact validation command must use the same target id and
`--tag` value as the accepted evidence record.
Its `--assets-dir` value must be a staged workspace-relative non-hidden path,
not an absolute path, including Windows drive paths written with forward
slashes, wildcard, workspace-root path, reserved repository/control directory or
`..` traversal. Linux and XP accepted evidence command paths must include both
the target id and release tag as path segments.
Before generating any accepted-evidence candidate, run
`python scripts/check_platform_goal_local_evidence.py` against the staged target
evidence. This local preflight reruns artifact validation plus Linux
builder/smoke or XP native evidence checks so unaccepted local proof cannot move
to candidate generation. Explicit artifact, builder, smoke and XP evidence
paths must resolve inside the declared `--root` and include the target/release
path segment under that root; proof outside that staging root must be restaged
before it can satisfy the preflight. Pass `--repository <owner>/<repo>` when the
staged proof is meant for a release in this repository; generated accepted-record
commands must carry that repository binding. Add `--json` when checking all four targets
to get a target-by-target local parity report, for example `0/4`, `2/4` or
`4/4`, before any candidate record is generated or appended. The all-target
local preflight also requires one release source head SHA and one GitHub
repository across the staged proof, and the same workflow run URL cannot carry conflicting local run attempts across protected targets.
`python scripts/make_platform_verified_evidence_record.py` reruns the same
local preflight with the recorded paths and release-source binding before it
emits a candidate record.
Package validated Linux i386/armhf evidence for review with
`python scripts/make_extended_linux_evidence_bundle.py` after the builder
identity, native artifact smoke, artifact validation and candidate accepted
record generation steps pass. Linux evidence bundle output directory must include the target id and release tag as path segments. The bundle output directory must include the
target id and release tag as path segments, must be plain non-symlink without
symlinked parent directories, and generated
manifest/archive/SHA-256 sidecar must be plain non-symlink paths. The builder
identity `--out` file must also be a plain non-symlink file without symlinked
parent directories. Candidate
generation rejects artifact, builder evidence and native smoke paths that
traverse symlinked directories. The builder evidence, native smoke log and
candidate evidence record must use target-scoped filenames: `builder-identity-<target>.json`, `native-smoke-<target>.log`, `platform-verified-evidence-<target>.json`.
Release-importable Linux i386/armhf evidence must come from
`.github/workflows/extended-platform-evidence.yml`, which validates native
artifacts on the matching self-hosted builder, generates the candidate and
review bundle, finalizes the candidate, and uploads the
`extended-linux-evidence-<target>-v<project.version>` source artifact consumed by the tagged
release importer. Before upload it runs
`python scripts/stage_extended_linux_evidence_upload.py` and stages the exact
upload set in `platform-evidence-upload/<target>/<release_tag>`, so only expected native artifacts, the
finalized evidence record and review-bundle files are uploaded; raw Linux builder output directories are not uploaded by wildcard. The Linux source artifact and upload directories must include the target id and release tag as path segments, and they must be separate roots. For Linux and XP staging, staged native artifacts and review-bundle files must match the finalized accepted record hashes, staged source and upload paths must not traverse symlinked parent directories, staged upload roots/children/destinations must be plain non-symlink paths, and the staged review bundle must re-finalize to the accepted record before upload.
After copy, the staged upload output must re-check the exact root file set and
pre-copy SHA-256 for every staged file before the GitHub Actions artifact is
uploaded. The workflow artifact upload must set `if-no-files-found: error`,
`include-hidden-files: false` and `retention-days: 90` so missing source files
fail, hidden scratch/private files stay excluded and source evidence remains
available for release import.
Strict promotion also requires each accepted record to include the review bundle
manifest, review bundle archive and review bundle SHA-256 sidecar digests
created by `python scripts/finalize_platform_verified_evidence_record.py`.
The review bundle manifest must bind the same `release_asset_urls` as the
candidate record, and the review bundle archive must contain the manifest,
candidate evidence record, target smoke evidence, and every native artifact
listed in the bundle manifest; missing, extra or hash-mismatched archive entries
do not count as reviewable promotion evidence. Archive entries must also be
safe relative paths and must not use symlink ZIP metadata.
Finalization records release asset URLs for the review bundle manifest, archive
and SHA-256 sidecar, and those URLs must use the same GitHub repository and
release tag as the native release artifacts. Native, review-bundle and finalized
record release URLs must end in exact safe file names without query strings,
fragments or path-qualified names.
It also binds `finalized_record_release_asset_url` to the exact
`platform-verified-evidence-<target>-final.json` release asset in that same
repository and tag. Candidate/finalized-record `--out` paths and
`--append-registry` registry paths must be plain non-symlink files without
symlinked parent directories.
The release importer rejects symlinked downloaded artifact and output
directories, symlinked parent directories, symlinked destination files,
non-file destinations and expected file names that are not exact safe file
names before copying accepted evidence artifacts into `release-assets`.
It also rejects downloaded source artifact native artifact SHA-256 mismatches
and review-bundle size or SHA-256 mismatches before staging those files for
release upload.
The publish-time release asset checker repeats the boundary by rejecting a
symlinked `release-assets` directory, symlinked parent directories and
symlinked release asset files before upload.
For Linux i386/armhf, the captured native smoke log must also contain the
canonical smoke command, target id, workflow run URL, release tag, target
architecture, every DEB/RPM/AppImage install/verify/upgrade/uninstall step and
the final pass line. When the smoke runs inside GitHub Actions, the script must
also reject any mismatch between the provided workflow run URL, run attempt or
source SHA and the `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_SHA` and
`GITHUB_REPOSITORY` environment values. A hash-bound log that only says the
smoke passed is not accepted evidence. Forbidden Linux weak-security proof
lines are rejected case-insensitively.
After downloading review-bundle artifacts, run
`python scripts/check_platform_review_bundle_artifacts.py --bundle-dir <bundle-dir> --require-goal-targets --release-tag v<project.version> --require-final-record-assets`
to extract each bundled candidate record, rerun finalization and prove the
accepted registry entry still matches the actual bundle files for the release
being promoted.
Finalization inputs for the candidate record, review-bundle manifest, archive
and SHA-256 sidecar must be plain non-symlink files whose parent directories do
not traverse symlinks.
The review-bundle directory itself must not be a symlink or traverse symlinked
parent directories, and the downloaded bundle records and manifest
`candidate_record.file` must use exact safe file names rather than
path-qualified names.
The publish asset checker also treats each finalized accepted-record JSON and
each finalized review bundle manifest, archive and SHA-256 sidecar as release
assets for the accepted target, so a promoted release must upload those evidence
files. The final accepted-record JSON must exactly match the accepted registry
entry, use canonical LF-terminated sorted JSON bytes, and bind its
`finalized_record_release_asset_url`; review bundle files must match the exact
size and SHA-256 recorded in `configs/platform_verified_evidence.json`, and
checksum sidecars must collectively cover every expected non-sidecar release
file except the final accepted-record JSON, which is verified by content. The
post-upload remote release audit also checks each published asset's positive
GitHub release asset ID and API URL, checks the published final-record asset
size and SHA-256 digest against that canonical public record, hashes the
downloaded published native and review-bundle asset bytes against accepted
evidence, and rejects stale protected-platform native/evidence assets that
remain outside the audited accepted-evidence scope. When those same-tag accepted
records are present, the
publish asset checker also re-reads the uploaded review bundle ZIPs and reruns
finalization to prove the release asset contents still match the accepted
registry entries.
Each accepted record must include the SHA-256 of the current
`configs/platform_parity_promotion.json` contract, so stale records cannot
promote readiness after required artifacts or evidence fields change.
Accepted registry targets are unique. Windows XP native-host promotion requires
the `windows-xp-native-x86` and `windows-xp-native-x64` records to use the same
`release_tag`, GitHub release repository, target-specific release source
workflow file and release source head SHA, and each XP record must bind a
positive release source run attempt; mismatched XP release
evidence remains partial and cannot promote the row.
Artifact validation checks names, non-empty payloads, exact SHA-256 sidecars,
exact safe checksum/native-manifest file references, exact native manifest
payload records, target architecture/format manifest binding and
package/container file signatures. ZIP and tar.gz artifacts must also be
readable archives with non-empty file entries, safe relative member names and
no symlink, hardlink or device entries. Duplicate or unexpected checksum/manifest
entries do not count as clean release evidence. Placeholder text files with
matching checksums do not count as release evidence. Promotion
artifact directories must be plain non-symlink paths without symlinked parent
directories, and contained files must be plain non-symlink paths.
Windows XP native-host accepted records must also include the SHA-256 of the
validated XP evidence JSON, the SHA-256 of the sanitized XP host identity, and
tracked `scripts/xp_smoke_runner.cmd` per-smoke command provenance that binds
the target, release tag, smoke id, evidence file, canonical
`--proof-file xp-smoke-proof/<smoke_id>.txt` path, sanitized `--host-label`
and concrete `--evidence-run-id`, `--observed-at-utc`, `--os-name`,
`--os-architecture`, `--os-service-pack` and x64-only `--os-edition` for every
smoke result.
The accepted XP summary must carry `xp_evidence_summary.smoke_evidence_files`
and each `xp_evidence_summary.smoke_commands` entry must bind `--evidence-file`
to the matching summary file path and `--proof-file` to the canonical proof
file path, with `--host-label`, `--evidence-run-id` and `--observed-at-utc`
matching `xp_evidence_summary.host_identity`, and `--os-name`,
`--os-architecture`, `--os-service-pack` plus required `--os-edition` matching
`xp_evidence_summary.os`.
Each smoke evidence file must also include `xp smoke target`, `xp smoke
release`, `xp smoke id`, `xp smoke os name`, `xp smoke os architecture`,
`xp smoke os service pack`, x64-only `xp smoke os edition`,
`xp smoke host probe command`, `xp smoke host probe output`,
`xp smoke processor architecture env`, `xp smoke processor architecture w6432
env`, `xp smoke wmic os caption`, `xp smoke wmic os csdversion`,
`xp smoke host label`, `xp smoke evidence run id` and `xp smoke observed at
utc` proof lines.
They must be plain non-symlink files under `xp-smoke-evidence/` and include the
SHA-256 values for each required smoke evidence file, so the registry stays
tied to the reviewed XP VM/toolchain bundle without exposing real usernames,
hostnames, credentials or tokens.
The XP review bundle manifest must repeat the candidate
`xp_evidence_summary.host_identity`, `xp_evidence_summary.toolchain` and
`xp_evidence_summary.security` values exactly, so reviewers and release gates see
the same legacy-toolchain and hardening proof that was accepted into the
registry.
Package validated XP evidence for review with
`python scripts/make_xp_native_evidence_bundle.py` after
`python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`
and the matching platform artifact validation pass. The XP evidence JSON path
must stay inside a plain non-symlink evidence directory without symlinked parent
directories or symlinked path components. XP evidence bundle output directory must include the target id and release tag as path segments. The bundle output directory must
include the target id and release tag as path segments, must be plain
non-symlink without symlinked parent
directories, and generated manifest/archive/SHA-256 sidecar must be plain
non-symlink paths.
Candidate generation rejects artifact, XP evidence JSON and XP evidence
directory paths that traverse symlinked directories.
The non-promoting XP evidence template output directory must also be plain
non-symlink without symlinked parent directories. Its `xp-evidence.json`,
`xp-smoke-evidence/` and generated smoke files must be plain non-symlink paths.
Release-importable XP evidence must come from
`.github/workflows/xp-native-evidence.yml`, which prints the current source run
metadata, waits for a non-empty and stable staged XP artifact/evidence file set
on a self-hosted `xp-evidence` runner, generates the candidate and review
bundle, finalizes the candidate, and uploads
`xp-native-evidence-<target>-<release_tag>` as the source artifact consumed by
the tagged release importer. Before upload it runs
`python scripts/stage_xp_native_evidence_upload.py` and stages the exact upload
set in `platform-evidence-upload/<target>/<release_tag>`, so only the expected native artifacts, finalized
evidence record and review-bundle files are uploaded; raw operator-supplied XP artifact or evidence directories are not uploaded by wildcard. The workflow-generated XP candidate record, final record and review bundle must be written under `xp-evidence-output/<target>/<release_tag>`, not a shared output root. The staged XP review bundle must re-finalize to the accepted record before upload, and staged source and upload paths must not traverse symlinked parent directories while staged upload roots/children/destinations must be plain non-symlink paths. The XP native artifact, XP evidence output and upload directories must include the target id and release tag as path segments, and must be separate roots.
After copy, the staged XP upload output must re-check the exact root file set
and pre-copy SHA-256 for every staged file before the GitHub Actions artifact is
uploaded. The workflow artifact upload must set `if-no-files-found: error`,
`include-hidden-files: false` and `retention-days: 90` so missing source files
fail, hidden scratch/private files stay excluded and source evidence remains
available for release import. Its assets_dir, evidence_file and evidence_dir dispatch inputs must be workspace-relative staged paths that include the target id and release tag as path segments, not
absolute paths, including Windows drive paths written with forward slashes,
wildcards, placeholders, workspace-root paths, reserved repository/control
directories or `..` traversal.
Accepted XP records must keep the same staged-path safety in
`native_evidence_validation_command`; its `--evidence`, `--assets-dir` and
required `--evidence-dir` values must include the target id and release tag as
path segments and must not use absolute paths, including Windows drive paths
written with forward slashes, wildcards, workspace-root paths, hidden path
segments, reserved repository/control directories or `..` traversal.

## Linux i386

Target id: `linux-i386`

Current state:

- `current_readiness_percent`: 70.0
- `current_status`: manual-script-supported
- `current_release_tier`: script-supported-native
- `current_github_release_channel`: manual-script-native

Current blockers:

- No default release workflow job runs on a real i386/i686 Linux builder.
- The default GitHub release matrix does not upload linux-i386 native artifacts.
- No accepted evidence record is present yet to activate publish-time requirements for linux-i386 checksum, manifest and review-bundle assets.

Required real evidence:

- Run `.github/workflows/extended-platform-evidence.yml` with `target=linux-i386`.
- Dispatch it with `gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> --ref v<project.version> -f target=linux-i386 -f release_tag=v<project.version> -f release_asset_base_url=<github-release-download-url>`.
- Provide `release_tag` and an exact `release_asset_base_url` of
  `https://github.com/<owner>/<repo>/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted i386/i686 Linux runner or equivalent real i386 builder.
- Use a matching `[self-hosted, linux, i386]` runner or equivalent real i386/i686 builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-i386 --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --out <target-release-evidence-dir>/builder-identity-linux-i386.json`.
- Builder identity must prove matching `platform.machine()` and `uname -m`, `dpkg --print-architecture=i386`, `getconf LONG_BIT=32`, concrete `rpm` and `rpmbuild` tool paths, and `sudo -n true` non-interactive sudo.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON, and the JSON must use the exact Linux builder identity schema with no scratch/private extras, including only the required tool path keys, bind the same `release_tag`, `workflow_run_url`, `workflow_run_attempt`, `workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` as the accepted record's release source, record non-empty `os_release`, `kernel_release` and `glibc_version` runtime identity values that match the smoke log, prove `git_worktree_clean=true` before native build, include a sanitized target-scoped `host_identity` block with `operator_private_data_redacted=true`, include security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility and CVE patch review with concrete security_update_channel and cve_review_reference update/advisory provenance, and prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Accepted evidence must include `workflow_inputs` matching `target=linux-i386`, the record `release_tag` and the release asset base URL used by the workflow dispatch, `release_asset_source.workflow=.github/workflows/extended-platform-evidence.yml`, and positive `release_asset_source.run_attempt`.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`.
- Accepted evidence must include `native_build_command=TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh`.
- Accepted evidence must include `native_smoke_command=bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`.
- Capture the smoke output as `<target-release-evidence-dir>/native-smoke-linux-i386.log` and bind it into the accepted record as both `linux_smoke_evidence_sha256.native_smoke` and `linux_smoke_summary`.
- The captured smoke log must include exact single-occurrence proof lines for `native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`, `native installer smoke release: v<project.version>`, `native installer smoke target arch: i386`, `native installer smoke target: linux-i386`, `native installer smoke workflow run: <github-actions-run-url>`, `native installer smoke workflow run attempt: <github-actions-run-attempt>`, `native installer smoke source head sha: <github-actions-head-sha>`, `native installer smoke git head sha: <github-actions-head-sha>`, `native installer smoke builder evidence: <builder-identity.json>`, `native installer smoke host label: linux-i386-builder`, `native installer smoke evidence run id: linux-i386-<release>-run-<github-actions-run-id>`, `native installer smoke observed at utc: <YYYY-MM-DDTHH:MM:SSZ>`, `native installer smoke uname machine: <i386-or-i686>`, `native installer smoke dpkg architecture: i386`, `native installer smoke userland bits: 32`, runtime identity proof lines `native installer smoke os release: <os-release>`, `native installer smoke kernel release: <uname-r>` and `native installer smoke glibc version: <glibc-version>` matching the builder identity JSON, Linux security proof lines including `native installer smoke security update channel: <security-update-channel>`, `native installer smoke CVE review reference: <cve-review-reference>`, `native installer smoke TLS minimum modern profiles: TLS 1.2`, `native installer smoke TLS preferred modern profiles: TLS 1.3`, `native installer smoke legacy compatibility profile: isolated-opt-in`, `native installer smoke legacy crypto scope: profile-only`, `native installer smoke weak crypto global default: false` and `native installer smoke modern defaults unchanged: true`, one `native installer smoke artifact sha256: <artifact> <sha256>` line for each expected DEB/RPM/AppImage artifact, every DEB/RPM/AppImage install/verify/upgrade/uninstall line and `native installer smoke passed for Linux i386`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
- Run the local protected-goal preflight with `python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target linux-i386 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --linux-builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --linux-workflow-run-url <github-actions-run-url> --linux-source-head-sha <github-actions-head-sha> --linux-source-run-attempt <github-actions-run-attempt>` before generating the candidate record; `<target-release-artifact-dir>` must contain only the expected release artifacts for strict promotion and must include `linux-i386` and `v<project.version>` as path segments.
- The candidate command must bind the same local evidence root as the preflight. Use `--local-evidence-root .` for the default workspace root, or replace `.` with `--local-evidence-root <staged-root>` when the preflight used a narrower staged root.
- Review uploaded `platform-verified-evidence-linux-i386.json`.
- Package the review bundle with `python scripts/make_extended_linux_evidence_bundle.py --target linux-i386 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-i386.json> --out-dir <target-release-artifact-dir>`; this reruns the candidate local protected-goal preflight root against the exact artifact, builder and smoke files being bundled.
- Confirm the review bundle manifest `validated_commands` includes the candidate `local_evidence_preflight_command`, and that `release_asset_urls` exactly match the candidate record before finalization.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-i386.json> --bundle-manifest <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.json --bundle-archive <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.zip --bundle-sha256s <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>-SHA256SUMS.txt --out <target-release-artifact-dir>/platform-verified-evidence-linux-i386-final.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-i386.deb`
- `remote-ops-workspace-v<project.version>-linux-i686.rpm`
- `remote-ops-workspace-v<project.version>-linux-i686.AppImage`
- `remote-ops-workspace-v<project.version>-linux-i686-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-i686-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-i686-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target linux-i386 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --linux-builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --linux-workflow-run-url <github-actions-run-url> --linux-source-head-sha <github-actions-head-sha> --linux-source-run-attempt <github-actions-run-attempt>
python scripts/make_platform_verified_evidence_record.py --target linux-i386 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --release-source-artifact-name extended-linux-evidence-linux-i386-v<project.version> --release-source-head-sha <github-actions-head-sha> --release-source-run-attempt <github-actions-run-attempt> --builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --local-evidence-root . --staged-upload-out-dir platform-evidence-upload/linux-i386/v<project.version> --runner-label self-hosted --runner-label linux --runner-label i386 --out <platform-verified-evidence-linux-i386.json>
python scripts/make_extended_linux_evidence_bundle.py --target linux-i386 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-i386.json> --out-dir <target-release-artifact-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-i386.json> --bundle-manifest <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.json --bundle-archive <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.zip --bundle-sha256s <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>-SHA256SUMS.txt --out <target-release-artifact-dir>/platform-verified-evidence-linux-i386-final.json --append-registry
```

## Linux armhf

Target id: `linux-armhf`

Current state:

- `current_readiness_percent`: 70.0
- `current_status`: manual-script-supported
- `current_release_tier`: script-supported-native
- `current_github_release_channel`: manual-script-native

Current blockers:

- No default release workflow job runs on a real armv7l/armhf Linux builder.
- The default GitHub release matrix does not upload linux-armhf native artifacts.
- No accepted evidence record is present yet to activate publish-time requirements for linux-armhf checksum, manifest and review-bundle assets.

Required real evidence:

- Run `.github/workflows/extended-platform-evidence.yml` with `target=linux-armhf`.
- Dispatch it with `gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> --ref v<project.version> -f target=linux-armhf -f release_tag=v<project.version> -f release_asset_base_url=<github-release-download-url>`.
- Provide `release_tag` and an exact `release_asset_base_url` of
  `https://github.com/<owner>/<repo>/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted armv7l/armhf Linux runner or equivalent real armhf builder.
- Use a matching `[self-hosted, linux, armhf]` runner or equivalent real armv7l/armhf builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-armhf --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --out <target-release-evidence-dir>/builder-identity-linux-armhf.json`.
- Builder identity must prove matching `platform.machine()` and `uname -m`, `dpkg --print-architecture=armhf`, `getconf LONG_BIT=32`, concrete `rpm` and `rpmbuild` tool paths, and `sudo -n true` non-interactive sudo.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON, and the JSON must use the exact Linux builder identity schema with no scratch/private extras, including only the required tool path keys, bind the same `release_tag`, `workflow_run_url`, `workflow_run_attempt`, `workflow_ref` pointing at `.github/workflows/extended-platform-evidence.yml`, `workflow_sha`, `source_head_sha` and `observed_git_head_sha` as the accepted record's release source, record non-empty `os_release`, `kernel_release` and `glibc_version` runtime identity values that match the smoke log, prove `git_worktree_clean=true` before native build, include a sanitized target-scoped `host_identity` block with `operator_private_data_redacted=true`, include security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility and CVE patch review with concrete security_update_channel and cve_review_reference update/advisory provenance, and prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Accepted evidence must include `workflow_inputs` matching `target=linux-armhf`, the record `release_tag` and the release asset base URL used by the workflow dispatch, `release_asset_source.workflow=.github/workflows/extended-platform-evidence.yml`, and positive `release_asset_source.run_attempt`.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`.
- Accepted evidence must include `native_build_command=TARGET_ARCH=armhf PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh`.
- Accepted evidence must include `native_smoke_command=bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`.
- Capture the smoke output as `<target-release-evidence-dir>/native-smoke-linux-armhf.log` and bind it into the accepted record as both `linux_smoke_evidence_sha256.native_smoke` and `linux_smoke_summary`.
- The captured smoke log must include exact single-occurrence proof lines for `native installer smoke command: bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url> --workflow-run-attempt <github-actions-run-attempt> --source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json>`, `native installer smoke release: v<project.version>`, `native installer smoke target arch: armhf`, `native installer smoke target: linux-armhf`, `native installer smoke workflow run: <github-actions-run-url>`, `native installer smoke workflow run attempt: <github-actions-run-attempt>`, `native installer smoke source head sha: <github-actions-head-sha>`, `native installer smoke git head sha: <github-actions-head-sha>`, `native installer smoke builder evidence: <builder-identity.json>`, `native installer smoke host label: linux-armhf-builder`, `native installer smoke evidence run id: linux-armhf-<release>-run-<github-actions-run-id>`, `native installer smoke observed at utc: <YYYY-MM-DDTHH:MM:SSZ>`, `native installer smoke uname machine: <armv7l-or-compatible>`, `native installer smoke dpkg architecture: armhf`, `native installer smoke userland bits: 32`, runtime identity proof lines `native installer smoke os release: <os-release>`, `native installer smoke kernel release: <uname-r>` and `native installer smoke glibc version: <glibc-version>` matching the builder identity JSON, Linux security proof lines including `native installer smoke security update channel: <security-update-channel>`, `native installer smoke CVE review reference: <cve-review-reference>`, `native installer smoke TLS minimum modern profiles: TLS 1.2`, `native installer smoke TLS preferred modern profiles: TLS 1.3`, `native installer smoke legacy compatibility profile: isolated-opt-in`, `native installer smoke legacy crypto scope: profile-only`, `native installer smoke weak crypto global default: false` and `native installer smoke modern defaults unchanged: true`, one `native installer smoke artifact sha256: <artifact> <sha256>` line for each expected DEB/RPM/AppImage artifact, every DEB/RPM/AppImage install/verify/upgrade/uninstall line and `native installer smoke passed for Linux armhf`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
- Run the local protected-goal preflight with `python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target linux-armhf --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --linux-builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --linux-workflow-run-url <github-actions-run-url> --linux-source-head-sha <github-actions-head-sha> --linux-source-run-attempt <github-actions-run-attempt>` before generating the candidate record; `<target-release-artifact-dir>` must contain only the expected release artifacts for strict promotion and must include `linux-armhf` and `v<project.version>` as path segments.
- The candidate command must bind the same local evidence root as the preflight. Use `--local-evidence-root .` for the default workspace root, or replace `.` with `--local-evidence-root <staged-root>` when the preflight used a narrower staged root.
- Review uploaded `platform-verified-evidence-linux-armhf.json`.
- Package the review bundle with `python scripts/make_extended_linux_evidence_bundle.py --target linux-armhf --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-armhf.json> --out-dir <target-release-artifact-dir>`; this reruns the candidate local protected-goal preflight root against the exact artifact, builder and smoke files being bundled.
- Confirm the review bundle manifest `validated_commands` includes the candidate `local_evidence_preflight_command`, and that `release_asset_urls` exactly match the candidate record before finalization.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-armhf.json> --bundle-manifest <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.json --bundle-archive <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.zip --bundle-sha256s <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>-SHA256SUMS.txt --out <target-release-artifact-dir>/platform-verified-evidence-linux-armhf-final.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-armhf.deb`
- `remote-ops-workspace-v<project.version>-linux-armv7hl.rpm`
- `remote-ops-workspace-v<project.version>-linux-armhf.AppImage`
- `remote-ops-workspace-v<project.version>-linux-armhf-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target linux-armhf --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --linux-builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --linux-workflow-run-url <github-actions-run-url> --linux-source-head-sha <github-actions-head-sha> --linux-source-run-attempt <github-actions-run-attempt>
python scripts/make_platform_verified_evidence_record.py --target linux-armhf --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --release-source-artifact-name extended-linux-evidence-linux-armhf-v<project.version> --release-source-head-sha <github-actions-head-sha> --release-source-run-attempt <github-actions-run-attempt> --builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --local-evidence-root . --staged-upload-out-dir platform-evidence-upload/linux-armhf/v<project.version> --runner-label self-hosted --runner-label linux --runner-label armhf --out <platform-verified-evidence-linux-armhf.json>
python scripts/make_extended_linux_evidence_bundle.py --target linux-armhf --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-armhf.json> --out-dir <target-release-artifact-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-armhf.json> --bundle-manifest <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.json --bundle-archive <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.zip --bundle-sha256s <target-release-artifact-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>-SHA256SUMS.txt --out <target-release-artifact-dir>/platform-verified-evidence-linux-armhf-final.json --append-registry
```

## Windows XP native x86

Target id: `windows-xp-native-x86`

Current state:

- `current_readiness_percent`: 25.0
- `current_status`: remote-target-only
- `current_host_tier`: remote-target-only
- `remote_target_coverage_percent`: 100.0
- `current_stack_supported`: false
- `requires_separate_legacy_toolchain`: true

Current blockers:

- The current native stack is Python 3.10+ and PyQt6, which is not treated as an XP native host stack in this project.
- No accepted XP x86 evidence bundle from a real Windows XP SP3 host and modern xp-evidence collector exists yet.
- No XP x86 native artifact is declared in the default release matrix.

Required real evidence:

- Use a separate XP-capable legacy toolchain.
- XP host requirement: Windows XP SP3 32-bit VM or physical host running scripts/xp_smoke_runner.cmd and artifact validation.
- Dispatch `.github/workflows/xp-native-evidence.yml` with `target=windows-xp-native-x86` so the self-hosted `xp-evidence` collector prints the source workflow run URL, head SHA and run attempt, then waits for a non-empty and stable staged XP x86 native artifact/evidence file set including `xp-evidence.json` and smoke evidence files.
- Dispatch it with `gh workflow run xp-native-evidence.yml --repo <owner>/<repo> --ref v<project.version> -f target=windows-xp-native-x86 -f release_tag=v<project.version> -f release_asset_base_url=<github-release-download-url> -f assets_dir=<target-release-artifact-dir> -f evidence_file=<target-release-evidence.json> -f evidence_dir=<target-release-evidence-dir>`.
- Run `scripts/xp_smoke_runner.cmd` and artifact validation on that Windows XP host using the printed source workflow run URL, head SHA and run attempt, then stage the proof onto the modern self-hosted `xp-evidence` collector with Python 3.12 and GitHub Actions support before the bounded wait expires.
- The accepted evidence record must include `workflow=.github/workflows/xp-native-evidence.yml`, `release_asset_source.workflow=.github/workflows/xp-native-evidence.yml`, positive `release_asset_source.run_attempt` and `workflow_inputs` matching the dispatch `target`, `release_tag`, `release_asset_base_url`, `assets_dir`, `evidence_file` and `evidence_dir`; the three path inputs must match `native_evidence_validation_command`.
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x86 --release-tag v<project.version> --out-dir <evidence-dir>`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- Each `scripts/xp_smoke_runner.cmd` command must include `--source-workflow-run-url <github-actions-run-url>`, `--source-head-sha <github-actions-head-sha>` and `--source-run-attempt <github-actions-run-attempt>`; the workflow URL must end with a numeric GitHub Actions run id, the source head SHA must be lowercase 40-character Git SHA, the run attempt must be a positive integer, `--observed-at-utc` must use `YYYY-MM-DDTHH:MM:SSZ`, and `--host-label`/`--evidence-run-id` must use the `xp-x86-` target prefix. XP smoke proof lines are exact single-occurrence bindings; duplicate source, artifact, host, OS or security proof lines are rejected. The `legacy_crypto_profile_scoped` and `modern_defaults_unchanged` commands must also include `--security-update-channel <security-update-channel>` and `--cve-review-reference <cve-review-reference>` matching the smoke proof lines.
- When `GITHUB_SHA`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` or `GITHUB_REPOSITORY` are present on the XP evidence host, `scripts/xp_smoke_runner.cmd` must reject mismatches with `--source-head-sha`, `--source-workflow-run-url` and `--source-run-attempt`.
- Every smoke evidence file must include `xp smoke target: windows-xp-native-x86`, `xp smoke release: v<project.version>`, `xp smoke id: <smoke_id>`, `xp smoke os name: Windows XP`, `xp smoke os architecture: x86`, `xp smoke os service pack: SP3`, `xp smoke host probe command: ver`, `xp smoke host probe output: Microsoft Windows XP [Version 5.1.2600]`, `xp smoke processor architecture env: x86`, `xp smoke processor architecture w6432 env: <empty>`, `xp smoke wmic os caption: Microsoft Windows XP <edition>`, `xp smoke wmic os csdversion: Service Pack 3`, `xp smoke host label: <host_label>`, `xp smoke evidence run id: <evidence_run_id>`, `xp smoke observed at utc: <observed_at_utc>`, `xp smoke source workflow run: <github-actions-run-url>`, `xp smoke source head sha: <github-actions-head-sha>` and `xp smoke source run attempt: <github-actions-run-attempt>`.
- The `artifact_manifest_validation` smoke file must also include one `xp smoke artifact file: <artifact-name>` line for each required XP x86 release artifact plus `xp smoke artifact manifest validated: true` and `xp smoke artifact sha256s validated: true`.
- Forbidden weak-security smoke proof lines are rejected case-insensitively, so case variants of global legacy crypto or weakened modern-default claims cannot pass.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- XP security patch evidence must include concrete security_update_channel and cve_review_reference update/advisory provenance.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
- Run the local protected-goal preflight with `python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target windows-xp-native-x86 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --xp-source-workflow-run-url <github-actions-run-url> --xp-source-head-sha <github-actions-head-sha> --xp-source-run-attempt <github-actions-run-attempt>` before generating the candidate record. The XP evidence JSON `artifact_validation.command --assets-dir` must match `<target-release-artifact-dir>`.
- The candidate command must bind the same local evidence root as the preflight. Use `--local-evidence-root .` for the default workspace root, or replace `.` with `--local-evidence-root <staged-root>` when the preflight used a narrower staged root.
- The XP evidence JSON `artifacts` list must exactly match the required XP x86 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag` and exactly one `--strict`.
- The XP evidence JSON `release_source` block must bind `.github/workflows/xp-native-evidence.yml`, `<github-actions-run-url>`, `<github-actions-head-sha>` and `<github-actions-run-attempt>`.
- The XP evidence JSON `host_identity` block must use a sanitized lab
  `host_label`, concrete `evidence_run_id`, UTC `observed_at_utc`, matching
  OS/toolchain identity and `operator_private_data_redacted=true`.
- The `legacy_crypto_profile_scoped` smoke file must include `legacy compatibility profile: isolated-opt-in`, `legacy crypto scope: profile-only`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`.
- The `modern_defaults_unchanged` smoke file must include `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`, `modern defaults unchanged: true`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_host_identity_sha256`, `xp_evidence_summary`, `xp_evidence_summary.release_source`, XP security patch evidence and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.
- Confirm `xp_evidence_sources` binds the candidate `xp-evidence.json` path, size and SHA-256 plus every required XP smoke evidence file path, size and SHA-256.
- Package the XP review bundle with `python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x86 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>`; this reruns the candidate local protected-goal preflight root against the exact XP artifacts, evidence JSON and smoke evidence directory being bundled.
- Confirm the XP bundle manifest `validated_commands` includes the candidate `local_evidence_preflight_command`, that `workflow`, `workflow_inputs`, `release_asset_source` and `release_asset_urls` exactly match the candidate record, and that `release_source`, `host_identity`, `toolchain` and `security` exactly match the candidate `xp_evidence_summary`.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --bundle-manifest <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.json --bundle-archive <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.zip --bundle-sha256s <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>-SHA256SUMS.txt --out <xp-evidence-output-dir>/platform-verified-evidence-windows-xp-native-x86-final.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x86-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target windows-xp-native-x86 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --xp-source-workflow-run-url <github-actions-run-url> --xp-source-head-sha <github-actions-head-sha> --xp-source-run-attempt <github-actions-run-attempt>
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x86 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --release-source-workflow-run-url <github-actions-run-url> --release-source-artifact-name xp-native-evidence-windows-xp-native-x86-v<project.version> --release-source-head-sha <github-actions-head-sha> --release-source-run-attempt <github-actions-run-attempt> --local-evidence-root . --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --staged-upload-out-dir platform-evidence-upload/windows-xp-native-x86/v<project.version> --xp-evidence-output-dir <xp-evidence-output-dir> --out <platform-verified-evidence-windows-xp-native-x86.json>
python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x86 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --bundle-manifest <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.json --bundle-archive <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.zip --bundle-sha256s <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>-SHA256SUMS.txt --out <xp-evidence-output-dir>/platform-verified-evidence-windows-xp-native-x86-final.json --append-registry
```

## Windows XP native x64

Target id: `windows-xp-native-x64`

Current state:

- `current_readiness_percent`: 25.0
- `current_status`: remote-target-only
- `current_host_tier`: remote-target-only
- `remote_target_coverage_percent`: 100.0
- `current_stack_supported`: false
- `requires_separate_legacy_toolchain`: true

Current blockers:

- The current native stack is Python 3.10+ and PyQt6, which is not treated as an XP native host stack in this project.
- No accepted XP x64 evidence bundle from a real Windows XP Professional x64 Edition SP2 host and modern xp-evidence collector exists yet.
- No XP x64 native artifact is declared in the default release matrix.

Required real evidence:

- Use a separate XP-capable legacy toolchain.
- XP host requirement: Windows XP Professional x64 Edition SP2 VM or physical host running scripts/xp_smoke_runner.cmd and artifact validation.
- Dispatch `.github/workflows/xp-native-evidence.yml` with `target=windows-xp-native-x64` so the self-hosted `xp-evidence` collector prints the source workflow run URL, head SHA and run attempt, then waits for a non-empty and stable staged XP x64 native artifact/evidence file set including `xp-evidence.json` and smoke evidence files.
- Dispatch it with `gh workflow run xp-native-evidence.yml --repo <owner>/<repo> --ref v<project.version> -f target=windows-xp-native-x64 -f release_tag=v<project.version> -f release_asset_base_url=<github-release-download-url> -f assets_dir=<target-release-artifact-dir> -f evidence_file=<target-release-evidence.json> -f evidence_dir=<target-release-evidence-dir>`.
- Run `scripts/xp_smoke_runner.cmd` and artifact validation on that Windows XP host using the printed source workflow run URL, head SHA and run attempt, then stage the proof onto the modern self-hosted `xp-evidence` collector with Python 3.12 and GitHub Actions support before the bounded wait expires.
- The accepted evidence record must include `workflow=.github/workflows/xp-native-evidence.yml`, `release_asset_source.workflow=.github/workflows/xp-native-evidence.yml`, positive `release_asset_source.run_attempt` and `workflow_inputs` matching the dispatch `target`, `release_tag`, `release_asset_base_url`, `assets_dir`, `evidence_file` and `evidence_dir`; the three path inputs must match `native_evidence_validation_command`.
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x64 --release-tag v<project.version> --out-dir <evidence-dir>`.
- The XP evidence JSON `os.service_pack` must include `SP2` and `os.edition`
  must be `Professional x64 Edition`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- Each `scripts/xp_smoke_runner.cmd` command must include `--source-workflow-run-url <github-actions-run-url>`, `--source-head-sha <github-actions-head-sha>` and `--source-run-attempt <github-actions-run-attempt>`; the workflow URL must end with a numeric GitHub Actions run id, the source head SHA must be lowercase 40-character Git SHA, the run attempt must be a positive integer, `--observed-at-utc` must use `YYYY-MM-DDTHH:MM:SSZ`, and `--host-label`/`--evidence-run-id` must use the `xp-x64-` target prefix. XP smoke proof lines are exact single-occurrence bindings; duplicate source, artifact, host, OS or security proof lines are rejected. The `legacy_crypto_profile_scoped` and `modern_defaults_unchanged` commands must also include `--security-update-channel <security-update-channel>` and `--cve-review-reference <cve-review-reference>` matching the smoke proof lines.
- When `GITHUB_SHA`, `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` or `GITHUB_REPOSITORY` are present on the XP evidence host, `scripts/xp_smoke_runner.cmd` must reject mismatches with `--source-head-sha`, `--source-workflow-run-url` and `--source-run-attempt`.
- Every smoke evidence file must include `xp smoke target: windows-xp-native-x64`, `xp smoke release: v<project.version>`, `xp smoke id: <smoke_id>`, `xp smoke os name: Windows XP`, `xp smoke os architecture: x64`, `xp smoke os service pack: SP2`, `xp smoke os edition: Professional x64 Edition`, `xp smoke host probe command: ver`, `xp smoke host probe output: Microsoft Windows [Version 5.2.3790]`, `xp smoke processor architecture env: AMD64`, `xp smoke processor architecture w6432 env: <empty-or-AMD64>`, `xp smoke wmic os caption: Microsoft Windows XP Professional x64 Edition`, `xp smoke wmic os csdversion: Service Pack 2`, `xp smoke host label: <host_label>`, `xp smoke evidence run id: <evidence_run_id>`, `xp smoke observed at utc: <observed_at_utc>`, `xp smoke source workflow run: <github-actions-run-url>`, `xp smoke source head sha: <github-actions-head-sha>` and `xp smoke source run attempt: <github-actions-run-attempt>`.
- The `artifact_manifest_validation` smoke file must also include one `xp smoke artifact file: <artifact-name>` line for each required XP x64 release artifact plus `xp smoke artifact manifest validated: true` and `xp smoke artifact sha256s validated: true`.
- Forbidden weak-security smoke proof lines are rejected case-insensitively, so case variants of global legacy crypto or weakened modern-default claims cannot pass.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- XP security patch evidence must include concrete security_update_channel and cve_review_reference update/advisory provenance.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <target-release-artifact-dir> --tag v<project.version> --strict`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
- Run the local protected-goal preflight with `python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target windows-xp-native-x64 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --xp-source-workflow-run-url <github-actions-run-url> --xp-source-head-sha <github-actions-head-sha> --xp-source-run-attempt <github-actions-run-attempt>` before generating the candidate record. The XP evidence JSON `artifact_validation.command --assets-dir` must match `<target-release-artifact-dir>`.
- The candidate command must bind the same local evidence root as the preflight. Use `--local-evidence-root .` for the default workspace root, or replace `.` with `--local-evidence-root <staged-root>` when the preflight used a narrower staged root.
- The XP evidence JSON `artifacts` list must exactly match the required XP x64 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag` and exactly one `--strict`.
- The XP evidence JSON `release_source` block must bind `.github/workflows/xp-native-evidence.yml`, `<github-actions-run-url>`, `<github-actions-head-sha>` and `<github-actions-run-attempt>`.
- The XP evidence JSON `host_identity` block must use a sanitized lab
  `host_label`, concrete `evidence_run_id`, UTC `observed_at_utc`, matching
  OS/toolchain identity and `operator_private_data_redacted=true`.
- The `legacy_crypto_profile_scoped` smoke file must include `legacy compatibility profile: isolated-opt-in`, `legacy crypto scope: profile-only`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`.
- The `modern_defaults_unchanged` smoke file must include `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`, `modern defaults unchanged: true`, `weak crypto global default: false`, `security update channel: <security-update-channel>` and `CVE review reference: <cve-review-reference>`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_host_identity_sha256`, `xp_evidence_summary`, `xp_evidence_summary.release_source`, XP security patch evidence and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.
- Confirm `xp_evidence_sources` binds the candidate `xp-evidence.json` path, size and SHA-256 plus every required XP smoke evidence file path, size and SHA-256.
- Package the XP review bundle with `python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x64 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>`; this reruns the candidate local protected-goal preflight root against the exact XP artifacts, evidence JSON and smoke evidence directory being bundled.
- Confirm the XP bundle manifest `validated_commands` includes the candidate `local_evidence_preflight_command`, that `workflow`, `workflow_inputs`, `release_asset_source` and `release_asset_urls` exactly match the candidate record, and that `release_source`, `host_identity`, `toolchain` and `security` exactly match the candidate `xp_evidence_summary`.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --bundle-manifest <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.json --bundle-archive <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.zip --bundle-sha256s <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>-SHA256SUMS.txt --out <xp-evidence-output-dir>/platform-verified-evidence-windows-xp-native-x64-final.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x64-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/check_platform_goal_local_evidence.py --root . --release-tag v<project.version> --target windows-xp-native-x64 --assets-dir <target-release-artifact-dir> --repository <owner>/<repo> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --xp-source-workflow-run-url <github-actions-run-url> --xp-source-head-sha <github-actions-head-sha> --xp-source-run-attempt <github-actions-run-attempt>
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x64 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --release-source-workflow-run-url <github-actions-run-url> --release-source-artifact-name xp-native-evidence-windows-xp-native-x64-v<project.version> --release-source-head-sha <github-actions-head-sha> --release-source-run-attempt <github-actions-run-attempt> --local-evidence-root . --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --staged-upload-out-dir platform-evidence-upload/windows-xp-native-x64/v<project.version> --xp-evidence-output-dir <xp-evidence-output-dir> --out <platform-verified-evidence-windows-xp-native-x64.json>
python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x64 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <xp-evidence-output-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --bundle-manifest <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.json --bundle-archive <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.zip --bundle-sha256s <xp-evidence-output-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>-SHA256SUMS.txt --out <xp-evidence-output-dir>/platform-verified-evidence-windows-xp-native-x64-final.json --append-registry
```

Windows XP native-host readiness reaches 100% only when both
`windows-xp-native-x86` and `windows-xp-native-x64` accepted evidence records
are present for the same `release_tag`.
