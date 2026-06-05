# Release Strategy

Remote Ops Workspace publishes release assets in phases. Each phase should ship
only when the artifact is real, reproducible, and documented.

Release integrity rules:

- Release tags must match `pyproject.toml` exactly, for example `v1.0.0`.
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
  manifest and `remote-ops-workspace-v1.0.0-SHA256SUMS.txt`;
- Windows native `x86`, `x64` and `arm64` artifacts;
- macOS native `x64` and `arm64` artifacts;
- Linux native `x86_64`/`amd64` and `aarch64`/`arm64` artifacts.

Linux `i386`/`i686` and `armv7l`/`armhf` native outputs are
script-supported by `scripts/make_linux_native.sh`, but they are not uploaded by
the default GitHub release workflow. A maintainer can promote them only after
running and verifying a matching builder. BSD, Solaris/illumos, Android
Termux/Web/PWA and legacy Windows endpoints remain source/Web/remote-target
entries unless a real native packaging path is added.

## Native installer smoke tests

Every default native installer format has an install, verify, upgrade and
uninstall smoke path before upload:

- Windows `.exe`: silent Inno Setup install into a smoke directory, `row.exe
  --version`, silent reinstall, generated uninstaller cleanup.
- Windows `.msi`: quiet `msiexec` install, Program Files `row.exe --version`,
  quiet reinstall, quiet uninstall.
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

- `remote_ops_workspace-1.0.0-py3-none-any.whl`
- `remote_ops_workspace-1.0.0.tar.gz`
- target source/install bundles for Windows, Linux, macOS, BSD, Solaris,
  Android/Termux, and Web/PWA
- `remote-ops-workspace-v1.0.0-release-manifest.json`
- `remote-ops-workspace-v1.0.0-SHA256SUMS.txt`

Purpose:

- Support Python users and package indexes.
- Give downstream packagers a standard wheel and source distribution.
- Keep the target bundles available for operators who want docs, installers,
  examples, and the Web/PWA shell in one archive.

## Phase 2: Windows native installers

Status: active.

Release assets:

- `remote-ops-workspace-v1.0.0-windows-<x86|x64|arm64>-setup.exe`
- `remote-ops-workspace-v1.0.0-windows-<x86|x64|arm64>.msi`
- `remote-ops-workspace-v1.0.0-windows-<x86|x64|arm64>-native.zip`
- `remote-ops-workspace-v1.0.0-windows-<x86|x64|arm64>-native-manifest.json`
- `remote-ops-workspace-v1.0.0-windows-<x86|x64|arm64>-native-SHA256SUMS.txt`

Implementation:

- Builds a standalone `row.exe` with PyInstaller for x86, x64 and ARM64 builders.
- Builds an interactive installer with Inno Setup.
- Builds an MSI installer with WiX.
- Runs `scripts/smoke_windows_native.ps1` to smoke install, verify, upgrade and
  uninstall the `.exe` and `.msi` artifacts before upload.
- Pins the Windows installer toolchain in CI: Inno Setup `6.3.3` and WiX
  `5.0.2`.
- Publishes unsigned CI artifacts. Authenticode signing can be layered in when
  release signing credentials are available.
- Treats Windows XP, Vista, Windows 7 and Windows 8.0 as legacy remote targets,
  not as first-class modern native runtime targets.

## Phase 3: macOS native distribution

Status: active.

Release assets:

- `remote-ops-workspace-v1.0.0-macos-<x64|arm64>.dmg`
- `remote-ops-workspace-v1.0.0-macos-<x64|arm64>.pkg`
- `remote-ops-workspace-v1.0.0-macos-<x64|arm64>-native-manifest.json`
- `remote-ops-workspace-v1.0.0-macos-<x64|arm64>-native-SHA256SUMS.txt`

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

- `remote-ops-workspace-v1.0.0-linux-<amd64|arm64>.deb`
- `remote-ops-workspace-v1.0.0-linux-<x86_64|aarch64>.rpm`
- `remote-ops-workspace-v1.0.0-linux-<x86_64|aarch64>.AppImage`
- `remote-ops-workspace-v1.0.0-linux-<x86_64|aarch64>-native.tar.gz`
- `remote-ops-workspace-v1.0.0-linux-<x86_64|aarch64>-native-manifest.json`
- `remote-ops-workspace-v1.0.0-linux-<x86_64|aarch64>-native-SHA256SUMS.txt`

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

The Web/PWA release remains a static `.zip` bundle because that is the right
artifact for static hosts, internal portals, and mobile browsers.
