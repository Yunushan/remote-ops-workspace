# Release Strategy

Remote Ops Workspace publishes release assets in phases. Each phase should ship
only when the artifact is real, reproducible, and documented.

## Phase 1: Python package artifacts

Status: active.

Release assets:

- `remote_ops_workspace-0.1.0-py3-none-any.whl`
- `remote_ops_workspace-0.1.0.tar.gz`
- target source/install bundles for Windows, Linux, macOS, BSD, Solaris,
  Android/Termux, and Web/PWA

Purpose:

- Support Python users and package indexes.
- Give downstream packagers a standard wheel and source distribution.
- Keep the target bundles available for operators who want docs, installers,
  examples, and the Web/PWA shell in one archive.

## Phase 2: Windows native installers

Status: active.

Release assets:

- `remote-ops-workspace-v0.1.0-windows-x64-setup.exe`
- `remote-ops-workspace-v0.1.0-windows-x64.msi`
- `remote-ops-workspace-v0.1.0-windows-x64-native.zip`
- `remote-ops-workspace-v0.1.0-windows-native-manifest.json`

Implementation:

- Builds a standalone `row.exe` with PyInstaller.
- Builds an interactive installer with Inno Setup.
- Builds an MSI installer with WiX.
- Publishes unsigned CI artifacts. Authenticode signing can be layered in when
  release signing credentials are available.

## Phase 3: macOS native distribution

Status: active.

Release assets:

- `remote-ops-workspace-v0.1.0-macos-<arch>.dmg`
- `remote-ops-workspace-v0.1.0-macos-<arch>.pkg`
- `remote-ops-workspace-v0.1.0-macos-<arch>-native-manifest.json`

Implementation:

- Builds a PyInstaller `.app` bundle for the PyQt6 GUI entry point.
- Builds a DMG for drag-and-drop installs.
- Builds a PKG for managed installs.
- Uses ad-hoc signing in CI. Developer ID signing and Apple notarization should
  be added before broad public macOS distribution.

## Phase 4: Linux native packages

Status: active.

Release assets:

- `remote-ops-workspace-v0.1.0-linux-amd64.deb`
- `remote-ops-workspace-v0.1.0-linux-x86_64.rpm`
- `remote-ops-workspace-v0.1.0-linux-x86_64.AppImage`
- `remote-ops-workspace-v0.1.0-linux-x86_64-native.tar.gz`
- `remote-ops-workspace-v0.1.0-linux-x86_64-native-manifest.json`

Implementation:

- Builds a standalone `row` command with PyInstaller.
- Builds a DEB with `dpkg-deb`.
- Builds an RPM with `rpmbuild`.
- Builds an AppImage with `appimagetool`.
- Keeps `.tar.gz` source/install bundles for non-deb/rpm systems.

## Android and Web

Android remains Termux plus Web/PWA until there is a real native Android wrapper.
Do not publish an APK just to wrap the current Python project unless the Android
app has its own tested install and update path.

The Web/PWA release remains a static `.zip` bundle because that is the right
artifact for static hosts, internal portals, and mobile browsers.
