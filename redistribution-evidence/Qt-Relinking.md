# Rebuilding the GUI with a modified Qt library

The GUI packages use PyQt6 6.11.0 with Qt 6.11.2. The exact PyQt6 and Qt source
archives, download URLs, and upstream SHA-256 digests are in
`PyQt6-6.11.0-source.json` and `qt-everywhere-src-6.11.2-source.json`.

Remote Ops Workspace's source bundle contains the native build scripts and
release pins. To recombine the application with a modified, interface-compatible
Qt library, build with Python 3.14, install the pinned build dependencies, and
install a compatible PyQt6 build using that Qt library before running the
platform script:

```powershell
python -m pip install --constraint requirements-release.txt ".[desktop,security,package]"
$env:ROW_REQUIRE_RELEASE_SIGNING = "0"
pwsh -File scripts/make_windows_native.ps1 -Arch x64
```

```sh
python -m pip install --constraint requirements-release.txt ".[desktop,security,package]"
ROW_REQUIRE_RELEASE_SIGNING=0 PYTHON_BIN=python3 scripts/make_macos_native.sh
```

The Windows GUI is rebuilt from the PyInstaller application source and the
modified Qt libraries. The macOS app is a replaceable `.app` bundle. Use a Qt
version compatible with PyQt6 6.11.0 and the application source. These preview
packages have no production code-signing or notarization protection that would
prevent a rebuilt application from running.

Qt's LGPLv3 terms permit a recipient to replace or relink the Qt library when
the terms are followed. This document describes the build path; it is not a
legal certification.
