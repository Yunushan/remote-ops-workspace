# Platform Promotion Runbook

This runbook is the operator path for truthful 100% readiness promotion of
Linux i386, Linux armhf and Windows XP native-host targets. It does not promote
any target by itself. Promotion happens only when accepted evidence records are
added to `configs/platform_verified_evidence.json` and all verification gates
pass.

Start with the shared gates:

```bash
python scripts/check_platform_parity_promotion.py
python scripts/check_platform_verified_evidence.py
python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete
python scripts/check_platform_verified_evidence.py --require-goal-targets --release-tag v<project.version>
python scripts/check_release_publish_assets.py
python scripts/check_release_publish_assets.py --require-platform-goal-targets --tag v<project.version>
python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets --release-tag v<project.version> --platform-review-bundle-dir <bundle-dir>
```

Accepted records must start as candidates generated with
`python scripts/make_platform_verified_evidence_record.py`, then the review
bundle must be packaged and bound back into the record with
`python scripts/finalize_platform_verified_evidence_record.py`. Append only the
finalized record with `--append-registry` when the referenced run, review
bundle and release assets are the real promotion evidence.
`python scripts/check_platform_verified_evidence.py` validates
`configs/platform_verified_evidence.json` in finalized-only mode by default;
`--allow-unfinalized-candidates` is only for local candidate checks before
registry append.
The strict `--require-goal-targets` and `--require-platform-goal-targets`
commands must fail until linux-i386, linux-armhf, windows-xp-native-x86 and
windows-xp-native-x64 all have finalized accepted evidence records.
When a release tag is supplied, all four accepted records must match that exact
tag; stale evidence from a previous release cannot promote a newer release.
Every accepted release asset URL must use the same `/releases/download/<tag>/`
segment as the record's `release_tag`.
All release asset URLs in one accepted record must come from the same GitHub
repository; Linux i386/armhf records must also use a `workflow_run_url` from
that same repository.
Release-imported evidence artifacts are downloaded only from the accepted
record's `release_asset_source.workflow_run_url` after the release importer
confirms the GitHub Actions run is `completed`, concluded `success`, and came
from a `workflow_dispatch` event. The run's `headSha` must match both
`release_asset_source.head_sha` in the accepted record and the release
checkout commit. Failed, still-running, unrelated, or wrong-commit source runs
are not valid release artifact provenance even when an artifact name matches.
The downloaded source artifact must contain exactly the expected release and
review-bundle files at artifact root; extra files, private raw logs and nested
builder output directories are rejected before anything is copied into the
release asset directory.
The recorded artifact validation command must use the same target id and
`--tag` value as the accepted evidence record.
Its `--assets-dir` value must be a staged workspace-relative non-hidden path,
not an absolute path, wildcard, workspace-root path, reserved
repository/control directory or `..` traversal.
Package validated Linux i386/armhf evidence for review with
`python scripts/make_extended_linux_evidence_bundle.py` after the builder
identity, native artifact smoke, artifact validation and candidate accepted
record generation steps pass. The builder evidence, native smoke log and
candidate evidence record must use target-scoped filenames: `builder-identity-<target>.json`, `native-smoke-<target>.log`, `platform-verified-evidence-<target>.json`.
Release-importable Linux i386/armhf evidence must come from
`.github/workflows/extended-platform-evidence.yml`, which validates native
artifacts on the matching self-hosted builder, generates the candidate and
review bundle, finalizes the candidate, and uploads the
`extended-linux-evidence-<target>-v<project.version>` source artifact consumed by the tagged
release importer. Before upload it runs
`python scripts/stage_extended_linux_evidence_upload.py` and stages the exact
upload set in `linux-evidence-upload`, so only expected native artifacts, the
finalized evidence record and review-bundle files are uploaded; raw Linux builder output directories are not uploaded by wildcard. The Linux source artifact directory and `linux-evidence-upload` staging directory must be separate roots. For Linux and XP staging, staged native artifacts and review-bundle files must match the finalized accepted record hashes before upload.
Strict promotion also requires each accepted record to include the review bundle
manifest, review bundle archive and review bundle SHA-256 sidecar digests
created by `python scripts/finalize_platform_verified_evidence_record.py`.
The review bundle manifest must bind the same `release_asset_urls` as the
candidate record, and the review bundle archive must contain the manifest,
candidate evidence record, target smoke evidence, and every native artifact
listed in the bundle manifest; missing, extra or hash-mismatched archive entries
do not count as reviewable promotion evidence.
Finalization records release asset URLs for the review bundle manifest, archive
and SHA-256 sidecar, and those URLs must use the same GitHub repository and
release tag as the native release artifacts.
For Linux i386/armhf, the captured native smoke log must also contain the
canonical smoke command, target id, workflow run URL, release tag, target
architecture, every DEB/RPM/AppImage install/verify/upgrade/uninstall step and
the final pass line. A hash-bound log that only says the smoke passed is not
accepted evidence.
After downloading review-bundle artifacts, run
`python scripts/check_platform_review_bundle_artifacts.py --bundle-dir <bundle-dir> --require-goal-targets --release-tag v<project.version>`
to extract each bundled candidate record, rerun finalization and prove the
accepted registry entry still matches the actual bundle files for the release
being promoted.
The publish asset checker also treats each finalized review bundle manifest,
archive and SHA-256 sidecar as release assets for the accepted target, so a
promoted release must upload those evidence files with the exact size and
SHA-256 recorded in `configs/platform_verified_evidence.json`, and checksum
sidecars must collectively cover every expected non-sidecar release file. When
those same-tag accepted records are present, the publish asset checker also
re-reads the uploaded review bundle ZIPs and reruns finalization to prove the
release asset contents still match the accepted registry entries.
Each accepted record must include the SHA-256 of the current
`configs/platform_parity_promotion.json` contract, so stale records cannot
promote readiness after required artifacts or evidence fields change.
Accepted registry targets are unique. Windows XP native-host promotion requires
the `windows-xp-native-x86` and `windows-xp-native-x64` records to use the same
`release_tag`; mismatched XP release evidence remains partial and cannot promote
the row.
Artifact validation checks names, non-empty payloads, exact SHA-256 sidecars,
exact native manifest payload records and package/container file signatures.
ZIP and tar.gz artifacts must also be readable archives with non-empty file
entries. Duplicate or unexpected checksum/manifest entries do not count as clean
release evidence. Placeholder text files with matching checksums do not count as
release evidence.
Windows XP native-host accepted records must also include the SHA-256 of the
validated XP evidence JSON, the SHA-256 of the sanitized XP host identity, and
tracked `scripts/xp_smoke_runner.cmd` per-smoke command provenance that binds
the target, release tag, smoke id, evidence file and canonical
`--proof-file xp-smoke-proof/<smoke_id>.txt` path for every smoke result.
The accepted XP summary must carry `xp_evidence_summary.smoke_evidence_files`
and each `xp_evidence_summary.smoke_commands` entry must bind `--evidence-file`
to the matching summary file path and `--proof-file` to the canonical proof
file path.
Each smoke evidence file must also include `xp smoke target`, `xp smoke
release` and `xp smoke id` proof lines.
They must also include the SHA-256 values for each required smoke evidence file,
so the registry stays
tied to the reviewed XP VM/toolchain bundle without exposing real usernames,
hostnames, credentials or tokens.
Package validated XP evidence for review with
`python scripts/make_xp_native_evidence_bundle.py` after
`python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`
and the matching platform artifact validation pass.
Release-importable XP evidence must come from
`.github/workflows/xp-native-evidence.yml`, which validates staged XP artifacts
and sanitized evidence on a self-hosted `xp-evidence` runner, generates the
candidate and review bundle, finalizes the candidate, and uploads
`xp-native-evidence-<target>-<release_tag>` as the source artifact consumed by
the tagged release importer. Before upload it runs
`python scripts/stage_xp_native_evidence_upload.py` and stages the exact upload
set in `xp-evidence-upload`, so only the expected native artifacts, finalized
evidence record and review-bundle files are uploaded; raw operator-supplied XP artifact or evidence directories are not uploaded by wildcard. The XP native artifact, XP evidence output and `xp-evidence-upload` staging directories must be separate roots. Its assets_dir, evidence_file and evidence_dir dispatch inputs must be workspace-relative staged paths that include the target id and release tag as path segments, not
absolute paths, wildcards, placeholders, workspace-root paths, reserved
repository/control directories or `..` traversal.
Accepted XP records must keep the same staged-path safety in
`native_evidence_validation_command`; its `--evidence`, `--assets-dir` and
required `--evidence-dir` values must include the target id and release tag as
path segments and must not use absolute paths, wildcards, workspace-root paths,
hidden path segments, reserved repository/control directories or `..` traversal.

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
- Provide `release_tag` and `release_asset_base_url` ending in `/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted i386/i686 Linux runner or equivalent real i386 builder.
- Use a matching `[self-hosted, linux, i386]` runner or equivalent real i386/i686 builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-i386 --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --source-head-sha <github-actions-head-sha> --out native-dist/linux/builder-identity-linux-i386.json`.
- Builder identity must prove matching `platform.machine()` and `uname -m`, `dpkg --print-architecture=i386`, `getconf LONG_BIT=32`, concrete `rpm` and `rpmbuild` tool paths, and `sudo -n true` non-interactive sudo.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON, and the JSON must bind the same `release_tag`, `workflow_run_url` and `source_head_sha` as the accepted record's release source head SHA, include a sanitized target-scoped `host_identity` block with `operator_private_data_redacted=true`, and include security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility and CVE patch review.
- Accepted evidence must include `workflow_inputs` matching `target=linux-i386`, the record `release_tag` and the release asset base URL used by the workflow dispatch, and `release_asset_source.workflow=.github/workflows/extended-platform-evidence.yml`.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url>`.
- Accepted evidence must include `native_build_command=TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh`.
- Accepted evidence must include `native_smoke_command=bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url>`.
- Capture the smoke output as `native-dist/linux/native-smoke-linux-i386.log` and bind it into the accepted record as `linux_smoke_evidence_sha256.native_smoke`.
- The captured smoke log must include `native installer smoke command: bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 --workflow-run-url <github-actions-run-url>`, `native installer smoke release: v<project.version>`, `native installer smoke target arch: i386`, `native installer smoke target: linux-i386`, `native installer smoke workflow run: <github-actions-run-url>`, every DEB/RPM/AppImage install/verify/upgrade/uninstall line and `native installer smoke passed for Linux i386`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <artifact-dir> --tag v<project.version>`.
- Review uploaded `platform-verified-evidence-linux-i386.json`.
- Package the review bundle with `python scripts/make_extended_linux_evidence_bundle.py --target linux-i386 --release-tag v<project.version> --assets-dir <artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-i386.json> --out-dir <bundle-dir>`.
- Confirm the review bundle manifest `release_asset_urls` exactly match the candidate record before finalization.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-i386.json> --bundle-manifest <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.json --bundle-archive <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.zip --bundle-sha256s <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>-SHA256SUMS.txt --out <final-record.json>`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-i386.deb`
- `remote-ops-workspace-v<project.version>-linux-i686.rpm`
- `remote-ops-workspace-v<project.version>-linux-i686.AppImage`
- `remote-ops-workspace-v<project.version>-linux-i686-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-i686-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-i686-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target linux-i386 --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --release-source-artifact-name extended-linux-evidence-linux-i386-v<project.version> --release-source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --runner-label self-hosted --runner-label linux --runner-label i386 --out <platform-verified-evidence-linux-i386.json>
python scripts/make_extended_linux_evidence_bundle.py --target linux-i386 --release-tag v<project.version> --assets-dir <artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-i386.json> --out-dir <bundle-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-i386.json> --bundle-manifest <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.json --bundle-archive <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>.zip --bundle-sha256s <bundle-dir>/extended-linux-evidence-bundle-linux-i386-v<project.version>-SHA256SUMS.txt --out <final-record.json> --append-registry
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
- Provide `release_tag` and `release_asset_base_url` ending in `/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted armv7l/armhf Linux runner or equivalent real armhf builder.
- Use a matching `[self-hosted, linux, armhf]` runner or equivalent real armv7l/armhf builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-armhf --release-tag v<project.version> --workflow-run-url <github-actions-run-url> --source-head-sha <github-actions-head-sha> --out native-dist/linux/builder-identity-linux-armhf.json`.
- Builder identity must prove matching `platform.machine()` and `uname -m`, `dpkg --print-architecture=armhf`, `getconf LONG_BIT=32`, concrete `rpm` and `rpmbuild` tool paths, and `sudo -n true` non-interactive sudo.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON, and the JSON must bind the same `release_tag`, `workflow_run_url` and `source_head_sha` as the accepted record's release source head SHA, include a sanitized target-scoped `host_identity` block with `operator_private_data_redacted=true`, and include security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility and CVE patch review.
- Accepted evidence must include `workflow_inputs` matching `target=linux-armhf`, the record `release_tag` and the release asset base URL used by the workflow dispatch, and `release_asset_source.workflow=.github/workflows/extended-platform-evidence.yml`.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url>`.
- Accepted evidence must include `native_build_command=TARGET_ARCH=armhf PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh`.
- Accepted evidence must include `native_smoke_command=bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url>`.
- Capture the smoke output as `native-dist/linux/native-smoke-linux-armhf.log` and bind it into the accepted record as `linux_smoke_evidence_sha256.native_smoke`.
- The captured smoke log must include `native installer smoke command: bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf --workflow-run-url <github-actions-run-url>`, `native installer smoke release: v<project.version>`, `native installer smoke target arch: armhf`, `native installer smoke target: linux-armhf`, `native installer smoke workflow run: <github-actions-run-url>`, every DEB/RPM/AppImage install/verify/upgrade/uninstall line and `native installer smoke passed for Linux armhf`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <artifact-dir> --tag v<project.version>`.
- Review uploaded `platform-verified-evidence-linux-armhf.json`.
- Package the review bundle with `python scripts/make_extended_linux_evidence_bundle.py --target linux-armhf --release-tag v<project.version> --assets-dir <artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-armhf.json> --out-dir <bundle-dir>`.
- Confirm the review bundle manifest `release_asset_urls` exactly match the candidate record before finalization.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-armhf.json> --bundle-manifest <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.json --bundle-archive <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.zip --bundle-sha256s <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>-SHA256SUMS.txt --out <final-record.json>`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-armhf.deb`
- `remote-ops-workspace-v<project.version>-linux-armv7hl.rpm`
- `remote-ops-workspace-v<project.version>-linux-armhf.AppImage`
- `remote-ops-workspace-v<project.version>-linux-armhf-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target linux-armhf --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --release-source-artifact-name extended-linux-evidence-linux-armhf-v<project.version> --release-source-head-sha <github-actions-head-sha> --builder-evidence <builder-identity.json> --linux-smoke-evidence <native-smoke-log> --runner-label self-hosted --runner-label linux --runner-label armhf --out <platform-verified-evidence-linux-armhf.json>
python scripts/make_extended_linux_evidence_bundle.py --target linux-armhf --release-tag v<project.version> --assets-dir <artifact-dir> --builder-evidence <builder-identity.json> --smoke-evidence <native-smoke-log> --candidate-record <platform-verified-evidence-linux-armhf.json> --out-dir <bundle-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-linux-armhf.json> --bundle-manifest <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.json --bundle-archive <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>.zip --bundle-sha256s <bundle-dir>/extended-linux-evidence-bundle-linux-armhf-v<project.version>-SHA256SUMS.txt --out <final-record.json> --append-registry
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
- No Windows XP SP3 x86 builder or VM smoke job exists in the release workflow.
- No XP x86 native artifact is declared in the default release matrix.

Required real evidence:

- Use a separate XP-capable legacy toolchain.
- Run on a Windows XP SP3 32-bit VM or physical/self-hosted runner.
- Run `.github/workflows/xp-native-evidence.yml` with `target=windows-xp-native-x86` after staging the XP x86 native artifacts, `xp-evidence.json` and smoke evidence files on the self-hosted `xp-evidence` runner.
- The accepted evidence record must include `workflow=.github/workflows/xp-native-evidence.yml`, `release_asset_source.workflow=.github/workflows/xp-native-evidence.yml` and `workflow_inputs` matching the dispatch `target`, `release_tag`, `release_asset_base_url`, `assets_dir`, `evidence_file` and `evidence_dir`; the three path inputs must match `native_evidence_validation_command`.
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x86 --release-tag v<project.version> --out-dir <evidence-dir>`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- Every smoke evidence file must include `xp smoke target: windows-xp-native-x86`, `xp smoke release: v<project.version>` and `xp smoke id: <smoke_id>`.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <target-release-artifact-dir> --tag v<project.version>`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
- The XP evidence JSON `artifacts` list must exactly match the required XP x86 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag`.
- The XP evidence JSON `host_identity` block must use a sanitized lab
  `host_label`, concrete `evidence_run_id`, UTC `observed_at_utc`, matching
  OS/toolchain identity and `operator_private_data_redacted=true`.
- The `legacy_crypto_profile_scoped` smoke file must include `legacy compatibility profile: isolated-opt-in`, `legacy crypto scope: profile-only` and `weak crypto global default: false`.
- The `modern_defaults_unchanged` smoke file must include `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`, `modern defaults unchanged: true` and `weak crypto global default: false`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_host_identity_sha256`, `xp_evidence_summary`, XP security patch evidence and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.
- Confirm `xp_evidence_sources` binds the candidate `xp-evidence.json` path, size and SHA-256 plus every required XP smoke evidence file path, size and SHA-256.
- Package the XP review bundle with `python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x86 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <bundle-dir>`.
- Confirm the XP bundle manifest `validated_commands[0]`, `workflow`, `workflow_inputs`, `release_asset_source` and `release_asset_urls` exactly match the candidate record.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --bundle-manifest <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.json --bundle-archive <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.zip --bundle-sha256s <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>-SHA256SUMS.txt --out <final-record.json>`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x86-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x86 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --release-source-workflow-run-url <github-actions-run-url> --release-source-artifact-name xp-native-evidence-windows-xp-native-x86-v<project.version> --release-source-head-sha <github-actions-head-sha> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --out <platform-verified-evidence-windows-xp-native-x86.json>
python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x86 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <bundle-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x86.json> --bundle-manifest <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.json --bundle-archive <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>.zip --bundle-sha256s <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x86-v<project.version>-SHA256SUMS.txt --out <final-record.json> --append-registry
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
- No Windows XP Professional x64 Edition SP2 builder or VM smoke job exists in the release workflow.
- No XP x64 native artifact is declared in the default release matrix.

Required real evidence:

- Use a separate XP-capable legacy toolchain.
- Run on a Windows XP Professional x64 Edition SP2 VM or physical/self-hosted runner.
- Run `.github/workflows/xp-native-evidence.yml` with `target=windows-xp-native-x64` after staging the XP x64 native artifacts, `xp-evidence.json` and smoke evidence files on the self-hosted `xp-evidence` runner.
- The accepted evidence record must include `workflow=.github/workflows/xp-native-evidence.yml`, `release_asset_source.workflow=.github/workflows/xp-native-evidence.yml` and `workflow_inputs` matching the dispatch `target`, `release_tag`, `release_asset_base_url`, `assets_dir`, `evidence_file` and `evidence_dir`; the three path inputs must match `native_evidence_validation_command`.
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x64 --release-tag v<project.version> --out-dir <evidence-dir>`.
- The XP evidence JSON `os.service_pack` must include `SP2` and `os.edition`
  must be `Professional x64 Edition`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- Every smoke evidence file must include `xp smoke target: windows-xp-native-x64`, `xp smoke release: v<project.version>` and `xp smoke id: <smoke_id>`.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <target-release-artifact-dir> --tag v<project.version>`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <target-release-evidence.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir>`.
- The XP evidence JSON `artifacts` list must exactly match the required XP x64 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag`.
- The XP evidence JSON `host_identity` block must use a sanitized lab
  `host_label`, concrete `evidence_run_id`, UTC `observed_at_utc`, matching
  OS/toolchain identity and `operator_private_data_redacted=true`.
- The `legacy_crypto_profile_scoped` smoke file must include `legacy compatibility profile: isolated-opt-in`, `legacy crypto scope: profile-only` and `weak crypto global default: false`.
- The `modern_defaults_unchanged` smoke file must include `modern TLS minimum: TLS 1.2`, `modern TLS preferred: TLS 1.3`, `modern defaults unchanged: true` and `weak crypto global default: false`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_host_identity_sha256`, `xp_evidence_summary`, XP security patch evidence and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.
- Confirm `xp_evidence_sources` binds the candidate `xp-evidence.json` path, size and SHA-256 plus every required XP smoke evidence file path, size and SHA-256.
- Package the XP review bundle with `python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x64 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <bundle-dir>`.
- Confirm the XP bundle manifest `validated_commands[0]`, `workflow`, `workflow_inputs`, `release_asset_source` and `release_asset_urls` exactly match the candidate record.
- Finalize the accepted-evidence record with `python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --bundle-manifest <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.json --bundle-archive <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.zip --bundle-sha256s <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>-SHA256SUMS.txt --out <final-record.json>`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x64-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-SHA256SUMS.txt`

Generate, finalize and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x64 --release-tag v<project.version> --assets-dir <target-release-artifact-dir> --release-asset-base-url <github-release-download-url> --release-source-workflow-run-url <github-actions-run-url> --release-source-artifact-name xp-native-evidence-windows-xp-native-x64-v<project.version> --release-source-head-sha <github-actions-head-sha> --xp-evidence <target-release-evidence.json> --xp-evidence-dir <target-release-evidence-dir> --out <platform-verified-evidence-windows-xp-native-x64.json>
python scripts/make_xp_native_evidence_bundle.py --target windows-xp-native-x64 --evidence <target-release-evidence.json> --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --assets-dir <target-release-artifact-dir> --evidence-dir <target-release-evidence-dir> --out-dir <bundle-dir>
python scripts/finalize_platform_verified_evidence_record.py --candidate-record <platform-verified-evidence-windows-xp-native-x64.json> --bundle-manifest <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.json --bundle-archive <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>.zip --bundle-sha256s <bundle-dir>/xp-native-evidence-bundle-windows-xp-native-x64-v<project.version>-SHA256SUMS.txt --out <final-record.json> --append-registry
```

Windows XP native-host readiness reaches 100% only when both
`windows-xp-native-x86` and `windows-xp-native-x64` accepted evidence records
are present for the same `release_tag`.
