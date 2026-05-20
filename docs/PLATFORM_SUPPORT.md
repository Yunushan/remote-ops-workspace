# Platform Support

## Windows and Windows Server

Target support:

- Windows 10/11.
- Windows Server 2012, 2012 R2, 2016, 2019, 2022 and 2025.

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
- CLI through Termux with Python and OpenSSH.

Termux example:

```bash
pkg update
pkg install python git openssh
python -m venv .venv
. .venv/bin/activate
pip install -e .
row init
row doctor
```

## Web

`apps/web` is static and can be served by the included Python HTTP server, Nginx, Apache, Caddy, a static host, or an internal portal.
