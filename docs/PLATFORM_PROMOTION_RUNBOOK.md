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
python scripts/check_release_publish_assets.py
```

Accepted records must be generated with
`python scripts/make_platform_verified_evidence_record.py`, reviewed, and then
added with `--append-registry` only when the referenced run and release assets
are the real promotion evidence.
Every accepted release asset URL must use the same `/releases/download/<tag>/`
segment as the record's `release_tag`.
All release asset URLs in one accepted record must come from the same GitHub
repository; Linux i386/armhf records must also use a `workflow_run_url` from
that same repository.
The recorded artifact validation command must use the same target id and
`--tag` value as the accepted evidence record.
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
validated XP evidence JSON and the SHA-256 values for each required smoke
evidence file, so the registry stays tied to the reviewed XP VM/toolchain
bundle.

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
- No release publish contract currently requires linux-i386 checksum and manifest assets.

Required real evidence:

- Run `.github/workflows/extended-platform-evidence.yml` with `target=linux-i386`.
- Provide `release_tag` and `release_asset_base_url` ending in `/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted i386/i686 Linux runner or equivalent real i386 builder.
- Use a matching `[self-hosted, linux, i386]` runner or equivalent real i386/i686 builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-i386 --out native-dist/linux/builder-identity-linux-i386.json`.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON.
- Accepted evidence must include `workflow_inputs` matching `target=linux-i386`, the record `release_tag` and the release asset base URL used by the workflow dispatch.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <artifact-dir> --tag v<project.version>`.
- Review uploaded `platform-verified-evidence-linux-i386.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-i386.deb`
- `remote-ops-workspace-v<project.version>-linux-i686.rpm`
- `remote-ops-workspace-v<project.version>-linux-i686.AppImage`
- `remote-ops-workspace-v<project.version>-linux-i686-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-i686-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-i686-native-SHA256SUMS.txt`

Generate and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target linux-i386 --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --builder-evidence <builder-identity.json> --runner-label self-hosted --runner-label linux --runner-label i386 --append-registry
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
- No release publish contract currently requires linux-armhf checksum and manifest assets.

Required real evidence:

- Run `.github/workflows/extended-platform-evidence.yml` with `target=linux-armhf`.
- Provide `release_tag` and `release_asset_base_url` ending in `/releases/download/vX.Y.Z`.
- Required runner evidence: matching self-hosted armv7l/armhf Linux runner or equivalent real armhf builder.
- Use a matching `[self-hosted, linux, armhf]` runner or equivalent real armv7l/armhf builder.
- Capture builder identity evidence with `python3 scripts/check_extended_platform_builder.py --target linux-armhf --out native-dist/linux/builder-identity-linux-armhf.json`.
- Accepted evidence must include `builder_identity_sha256` matching that builder identity JSON.
- Accepted evidence must include `workflow_inputs` matching `target=linux-armhf`, the record `release_tag` and the release asset base URL used by the workflow dispatch.
- Build with `scripts/make_linux_native.sh`.
- Smoke with `scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux`.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <artifact-dir> --tag v<project.version>`.
- Review uploaded `platform-verified-evidence-linux-armhf.json`.

Required artifacts:

- `remote-ops-workspace-v<project.version>-linux-armhf.deb`
- `remote-ops-workspace-v<project.version>-linux-armv7hl.rpm`
- `remote-ops-workspace-v<project.version>-linux-armhf.AppImage`
- `remote-ops-workspace-v<project.version>-linux-armhf-native.tar.gz`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-manifest.json`
- `remote-ops-workspace-v<project.version>-linux-armhf-native-SHA256SUMS.txt`

Generate and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target linux-armhf --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --workflow-run-url <github-actions-run-url> --builder-evidence <builder-identity.json> --runner-label self-hosted --runner-label linux --runner-label armhf --append-registry
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
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x86 --release-tag v<project.version> --out-dir <evidence-dir>`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <artifact-dir> --tag v<project.version>`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>`.
- The XP evidence JSON `artifacts` list must exactly match the required XP x86 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_evidence_summary` and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x86-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x86-native-SHA256SUMS.txt`

Generate and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x86 --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --xp-evidence <evidence.json> --xp-evidence-dir <evidence-dir> --append-registry
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
- No Windows XP x64 builder or VM smoke job exists in the release workflow.
- No XP x64 native artifact is declared in the default release matrix.

Required real evidence:

- Use a separate XP-capable legacy toolchain.
- Run on a Windows XP Professional x64 VM or physical/self-hosted runner.
- Start a non-promoting evidence skeleton with `python scripts/make_xp_native_evidence_template.py --target windows-xp-native-x64 --release-tag v<project.version> --out-dir <evidence-dir>`.
- Produce smoke evidence files for `cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`, `artifact_manifest_validation`, `legacy_crypto_profile_scoped` and `modern_defaults_unchanged`.
- legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in.
- Keep legacy TLS, SSH and RDP compatibility profile-scoped and opt-in.
- modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto.
- Prove modern Windows 10/11, Linux and macOS defaults remain hardened.
- Validate artifacts with `python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <artifact-dir> --tag v<project.version>`.
- Validate XP evidence with `python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>`.
- The XP evidence JSON `artifacts` list must exactly match the required XP x64 artifact names, and its `artifact_validation.command` must use exactly one `--tag` matching the evidence `release_tag`.
- Use `--xp-evidence-dir` when smoke evidence files live outside the evidence JSON directory.
- Review the generated record's `xp_evidence_sha256`, `xp_evidence_contract_sha256`, `xp_evidence_summary` and `xp_smoke_evidence_sha256` values against the validated XP evidence bundle before appending.

Required artifacts:

- `remote-ops-workspace-v<project.version>-windows-xp-x64-native.zip`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-manifest.json`
- `remote-ops-workspace-v<project.version>-windows-xp-x64-native-SHA256SUMS.txt`

Generate and append only after review:

```bash
python scripts/make_platform_verified_evidence_record.py --target windows-xp-native-x64 --release-tag v<project.version> --assets-dir <artifact-dir> --release-asset-base-url <github-release-download-url> --xp-evidence <evidence.json> --xp-evidence-dir <evidence-dir> --append-registry
```

Windows XP native-host readiness reaches 100% only when both
`windows-xp-native-x86` and `windows-xp-native-x64` accepted evidence records
are present for the same `release_tag`.
