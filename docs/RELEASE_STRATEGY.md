# Release Strategy

Remote Ops Workspace publishes release assets in phases. Each phase should ship
only when the artifact is real, reproducible, and documented.

Release integrity rules:

- Release tags must match `pyproject.toml` exactly, for example `v1.0.2`.
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
- The `release-preflight` workflow job runs
  `python scripts/verify.py --quick --no-cli-smoke` and
  `python scripts/check_repository_cleanup.py --require-clean` before any
  source, Python or native artifact build job can start.
- The publish job runs
  `python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag>`
  after downloading workflow artifacts and before uploading the GitHub release.
  It verifies the expected asset set from `configs/release_matrix.json`,
  checksum sidecars and source release-manifest records.
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
running and verifying a matching builder. BSD, Solaris/illumos, Android
Termux/Web/PWA, iOS/iPadOS Web/PWA and legacy Windows endpoints remain
source/Web/remote-target entries unless a real native packaging path is added.
Windows XP x86/x64 remote endpoints use isolated per-profile legacy opt-ins
instead of lowering modern TLS, SSH or RDP defaults globally.

`configs/platform_parity_promotion.json` and
`python scripts/check_platform_parity_promotion.py` define the required evidence
before extended targets can be promoted. Linux i386 and Linux armhf can move
from script-supported to default-native only when the release matrix, release
workflow, publish asset contract, native build outputs, smoke tests, checksum
sidecars and native manifests all include those architectures. The produced
artifact directory must pass
`python scripts/check_platform_promotion_artifacts.py --target linux-i386 --assets-dir <artifact-dir> --tag v<project.version>`
or
`python scripts/check_platform_promotion_artifacts.py --target linux-armhf --assets-dir <artifact-dir> --tag v<project.version>`.
`.github/workflows/extended-platform-evidence.yml` is the dispatch-only
self-hosted collection path for that evidence; it uses `[self-hosted, linux,
i386]` and `[self-hosted, linux, armhf]` runners and uploads evidence artifacts
without publishing a GitHub release. Each run also writes
`platform-verified-evidence-linux-i386.json` or
`platform-verified-evidence-linux-armhf.json` into the uploaded evidence
artifact. Accepted release evidence records must be added to
`configs/platform_verified_evidence.json` and pass
`python scripts/check_platform_verified_evidence.py` before generated readiness
can promote either Linux extended architecture. Generate those records with
`python scripts/make_platform_verified_evidence_record.py` so artifact URLs,
per-artifact SHA-256 digests, the Linux builder identity SHA-256 and the
workflow dispatch inputs, and the promotion config SHA-256 are derived from the same promotion contract.
Linux records must also include the builder identity JSON emitted by
`python3 scripts/check_extended_platform_builder.py --out ...`; its
`builder_identity_sha256` must match that JSON. The recorded
`workflow_inputs.release_asset_base_url` must prefix every release asset URL in
the accepted record. Use
`--append-registry` only when the referenced run and release assets are the real
promotion evidence. The publish-time asset checker revalidates the full
accepted-evidence registry before trusting it, then rejects Linux i386/armhf
native assets in the default release asset set unless the matching accepted
evidence target is present.
Windows XP native-host readiness can move from remote-target-only only through a
separate XP-capable legacy toolchain with x86/x64 XP VM or self-hosted runner
evidence and proof that legacy crypto compatibility stays isolated from modern
defaults. XP artifact directories must pass
`python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --assets-dir <artifact-dir> --tag v<project.version>`
or
`python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 --assets-dir <artifact-dir> --tag v<project.version>`.
The XP VM/toolchain evidence JSON must also pass
`python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>`.
The XP evidence JSON must be bundled with per-smoke evidence files for
`cli_launch`, `gui_or_legacy_host_ui_launch`, `loopback_profile_dry_run`,
`artifact_manifest_validation`, `legacy_crypto_profile_scoped` and
`modern_defaults_unchanged`; the validator resolves each relative
`evidence_file` path and checks the recorded SHA-256.
Accepted XP records generated from that bundle must include `xp_evidence_sha256`
for the evidence JSON, `xp_evidence_summary` for the XP target/release/toolchain/security/smoke
binding and `xp_smoke_evidence_sha256` for every required smoke evidence file,
plus `xp_evidence_contract_sha256` for the current
`configs/xp_native_evidence_contract.json`.
Both XP x86 and XP x64 accepted records must be present in
`configs/platform_verified_evidence.json` before the Windows XP native-host row
can promote to 100%. Generate each accepted-record candidate with
`python scripts/make_platform_verified_evidence_record.py` after
`python scripts/check_xp_native_evidence.py` passes, then append it with
`--append-registry` only after reviewing the XP VM/toolchain evidence bundle and
the per-artifact SHA-256 digests recorded for the XP native artifacts.
The same publish-time guard rejects Windows XP native assets unless the registry
passes full accepted-evidence validation and both XP x86 and XP x64 accepted
evidence records are present, because one architecture alone does not prove the
Windows XP native-host row.

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
- Linux `.deb`: `sudo dpkg -i`, `/usr/bin/row --version`, reinstall, `dpkg -r`.
- Linux `.rpm`: `sudo rpm -Uvh --replacepkgs`, `/usr/bin/row --version`,
  reinstall, `rpm -e`.
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

The tag workflow repeats this protection automatically. The `release-preflight`
job is a dependency of `source-and-python`, `windows-native`, `macos-native`,
`linux-native` and `publish`, so a stale manifest, broken verifier check or
dirty checkout stops the release before artifacts are built or uploaded.

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
