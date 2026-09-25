# Third-party notices

Remote Ops Workspace source files are licensed under 0BSD; see `LICENSE`.

The Windows x64/ARM64 and macOS GUI packages combine the application with
PyQt6 6.11.0 (GNU GPL version 3) and Qt 6.11.2 (GNU LGPL version 3). Those GUI
packages are distributed as a GPLv3 combined work. The application's source
remains available under its existing 0BSD license. Copies of both license
texts and Qt relinking instructions are included in each GUI package.

The project also uses the following optional runtime components in native
packages:

| Component | Version | License |
| --- | --- | --- |
| PyQt6 | 6.11.0 | GPL-3.0-only |
| Qt | 6.11.2 | LGPL-3.0-only for the Qt libraries used by this GUI |
| PyQt6-sip | 13.12.0 | BSD-2-Clause |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| bcrypt | 5.0.0 | Apache-2.0 |
| truststore | 0.10.4 | MIT |
| PyInstaller | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception |

Exact package versions are pinned in `requirements-release.txt`. The release
SBOM and native artifact manifests provide the build inventory. Source for the
Qt/PyQt components and its published SHA-256 digest are listed in the release
notes and in the adjacent `*-source.json` records. The Qt and PyQt packages
retain their own notices in their corresponding source distributions.

The PyInstaller bootloader is distributed under the PyInstaller bootloader
exception, available at <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt>.
The Python runtime license is available at <https://docs.python.org/3/license.html>.
