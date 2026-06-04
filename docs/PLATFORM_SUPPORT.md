# Platform Support

## Release assets

Tagged releases publish one source bundle plus one install-oriented bundle for
each public target badge:

| Target | Asset |
|---|---|
| Python wheel | `remote_ops_workspace-0.1.0-py3-none-any.whl` |
| Python sdist | `remote_ops_workspace-0.1.0.tar.gz` |
| Source | `remote-ops-workspace-v0.1.0-source.zip` |
| Windows | `remote-ops-workspace-v0.1.0-windows.zip` |
| Linux | `remote-ops-workspace-v0.1.0-linux.tar.gz` |
| macOS | `remote-ops-workspace-v0.1.0-macos.tar.gz` |
| BSD | `remote-ops-workspace-v0.1.0-bsd.tar.gz` |
| Solaris/illumos | `remote-ops-workspace-v0.1.0-solaris.tar.gz` |
| Android/Termux | `remote-ops-workspace-v0.1.0-android-termux.tar.gz` |
| Web/PWA | `remote-ops-workspace-v0.1.0-web-pwa.zip` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>-setup.exe` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>.msi` |
| Windows native | `remote-ops-workspace-v0.1.0-windows-<x86\|x64\|arm64>-native.zip` |
| macOS native | `remote-ops-workspace-v0.1.0-macos-<x64\|arm64>.dmg` |
| macOS native | `remote-ops-workspace-v0.1.0-macos-<x64\|arm64>.pkg` |
| macOS native | `remote-ops-workspace-v0.1.0-macos-<x64\|arm64>-native-manifest.json` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<amd64\|arm64>.deb` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<x86_64\|aarch64>.rpm` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<x86_64\|aarch64>.AppImage` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<x86_64\|aarch64>-native.tar.gz` |
| Linux native | `remote-ops-workspace-v0.1.0-linux-<x86_64\|aarch64>-native-manifest.json` |
| Manifests | `remote-ops-workspace-v0.1.0-*-manifest.json` |

The platform bundles include source, docs, examples, relevant installer entry
points, and per-target release notes. They are not native protocol-client
bundles; SSH/RDP/VNC/X11/SPICE/X2Go/ICA rendering still depends on the external
clients available on the target system.

Native `.exe`, `.msi`, `.dmg`, `.pkg`, `.deb`, `.rpm`, and AppImage artifacts
are built by OS-specific release jobs or matching self-hosted builders. Windows
and macOS artifacts are unsigned CI builds until release signing credentials are
configured. APK-style artifacts remain out of scope until there is a real native
Android wrapper.

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
  Termux/Web/PWA, and legacy Windows endpoints do not receive default native app
  installers.

Architecture support is declared in `configs/platform_targets.json`, release
publishing policy is declared in `configs/release_matrix.json`, and
`python scripts/check_platform_support_truth.py` verifies that the catalog,
release matrix, generated readiness scores and platform docs keep the same
default-native, script-supported, Termux/Web and legacy remote-target meaning.
The broad support catalog is exposed with:

```bash
row platforms
row platforms --json
```

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

Architecture targets:

- x86: 32-bit Windows native artifacts from a 32-bit Python/PyInstaller build.
- x64: default 64-bit Windows native artifacts.
- ARM64: native Windows ARM64 artifacts from an ARM64 Windows builder.

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

## Web

`apps/web` is static and can be served by the included Python HTTP server, Nginx, Apache, Caddy, a static host, or an internal portal. The included server binds to loopback by default and requires `--allow-public-bind` for non-loopback interfaces. The web Docker compose file publishes `127.0.0.1:8765` by default.
