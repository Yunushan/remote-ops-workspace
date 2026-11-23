# Third-party notices

Remote Ops Workspace source files are licensed under 0BSD; see `LICENSE`.

The Windows x64/ARM64 and macOS GUI packages combine the application with
PyQt6 6.12.1 (GNU GPL version 3) and Qt 6.12.0 (GNU LGPL version 3). Those GUI
packages are distributed as a GPLv3 combined work. The application's source
remains available under its existing 0BSD license. Each GUI package includes
both license texts, `Qt-Relinking.md`, and the source archive records
`PyQt6-6.12.1-source.json` and `qt-everywhere-src-6.12.0-source.json`. Find them
under `docs/licenses/` on Windows or `Contents/Resources/licenses/` inside the
macOS app. Each source record gives the upstream archive URL and SHA-256 digest.

The native packages use different subsets of these runtime components.

| Component | Version | License |
| --- | --- | --- |
| PyQt6 | 6.12.1 | GPL-3.0-only |
| Qt | 6.12.0 | LGPL-3.0-only for the Qt libraries used by this GUI |
| PyQt6-sip | 13.13.1 | BSD-2-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| bcrypt | 5.0.0 | Apache-2.0 |
| truststore | 0.10.5 | MIT |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception |

Exact package versions are pinned in `requirements-release.txt`. The release
SBOM and native artifact manifests provide the build inventory. The release
notes link to the Qt and PyQt source archives. Their corresponding source
distributions retain their own notices.

The PyInstaller bootloader is distributed under the PyInstaller bootloader
exception, available at <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>.
The Python runtime license is available at <https://docs.python.org/3/license.html>.
