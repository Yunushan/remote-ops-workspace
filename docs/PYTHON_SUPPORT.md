# Python runtime support

Remote Ops Workspace project metadata accepts source-host installation on
standard, GIL-enabled CPython 3.10 through 3.15. The authoritative 3.15 runtime
claim currently covers the hosted Linux, Windows and macOS CI families described
below; target-specific support rows may be narrower. Project metadata uses
`requires-python = ">=3.10,<3.16"`: versions below 3.10 are missing required
language and standard-library behavior, while Python 3.16 has not been tested
and must not be accepted implicitly.

## Python 3.15 evidence boundary

As of 2026-08-23, upstream Python 3.15 is at `3.15.0rc1`; its final release is
scheduled for 2026-10-01. The repository therefore distinguishes two claims:

- **3.15 release-candidate compatibility:** the normal release-blocking matrix
  resolves the latest available 3.15 prerelease and runs the full test suite on
  Linux, Windows and macOS. A second blocking job deliberately repeats the full
  suite with the desktop, security, package and development extras installed so
  PyQt-backed tests cannot silently skip. It runs `pip check`, imports and smokes
  every declared extra, starts PyInstaller, builds and launches a package-aware
  one-file CLI executable, renders and exercises every GUI preset, builds both
  distribution formats, and installs the wheel and sdist in clean virtual environments.
  The frozen smoke runs both `--version` and `platforms --json`
  and retains the executable SHA-256 plus command evidence; importing
  PyInstaller or printing its version alone is not accepted as packaged-runtime
  compatibility. The package extra requires PyInstaller 6.21 or newer because
  6.21 is the first upstream release with Python 3.15 support; older PyInstaller
  releases cannot satisfy this runtime contract. The desktop extra requires
  PyQt6 6.11.0 or newer and stays below PyQt6 7.0.0, matching the GUI stack
  used by the release toolchain; older PyQt6 releases are not part of the
  Python 3.15 support claim.
  Both native Windows rows additionally install the
  pinned loopback SSH server dependency and rerun the real OpenSSH/ConPTY,
  ProxyJump, terminal-input and GUI terminal-pane proofs with skip-to-pass
  disabled.
- **3.15 final-GA certification:** this requires the same blocking jobs to
  complete with a `3.15.0` final interpreter after that interpreter exists. The
  runtime evidence validator must report `releaselevel=final`; a release
  candidate cannot satisfy that final-GA condition merely because all tests pass.
  Until then, the project does not describe the upstream preview runtime as a
  production-safe Python release.

The dedicated evidence matrix covers Linux x64 and ARM64, Windows x64 and ARM64, and macOS Intel and Apple Silicon. The normal compatibility matrix also runs
3.15 on every tracked hosted macOS row and explicit Linux/Windows ARM64 rows.
These jobs are not advisory and may not use `continue-on-error`.

The stable aggregate check context is `Python 3.15 readiness`. It evaluates with
`always()` and succeeds only when both the normal compatibility matrix and the
six-host optional-dependency/evidence matrix succeed. Repository governance
requires that exact context. Merge blocking becomes effective only after the
live `main` branch rule includes it and the separate `Native Windows readiness`
context, and after
`python scripts/check_repository_governance.py --repository <owner/repo>`
passes; tracked workflow files cannot apply remote branch protection by
themselves. The native aggregate succeeds only after the native Windows
ConPTY/OpenSSH, GUI render, interaction and tab-paint evidence job succeeds.
The Python 3.15 aggregate independently fails when either its x64 or ARM64
Windows row cannot complete the same real SSH/ConPTY loopback contract.

The `python-version: "3.15"` request uses `allow-prereleases: true`. Before GA it
resolves the current release candidate; after GA the same request resolves the
stable 3.15 line, so the contract does not remain pinned to a preview build.

Each dedicated host writes `runtime.json` with the exact interpreter version,
`version_info` including `releaselevel`, implementation/cache tag, GIL state,
machine and pointer width, installed distribution versions, and GitHub run
provenance. A second JSON record contains the wheel/sdist filenames, sizes,
SHA-256 hashes, isolated-install probes and packaged runtime-resource checks.
The GUI captures, interaction evidence, distributions and runtime records are
uploaded as four fail-closed artifact groups with 90-day retention on every
host. Each Windows row uploads a fifth group containing the native SSH/ConPTY
JSON and JUnit evidence. An absent required artifact, an SSH proof that skips,
or an ambiguous distribution set fails the job.

## PyQt6 6.12 forward compatibility

The desktop dependency contract is `PyQt6>=6.11.0,<7.0.0`. This accepts the
PyQt6 6.12 line without permitting an untested PyQt6 7.x API break. The
release toolchain keeps exact 6.11.x pins so native bundles remain reproducible
until a published 6.12 wheel has been exercised on every supported host.

The Python 3.15 optional-dependency matrix runs
`python scripts/check_pyqt6_compatibility.py --require-pyqt6
--target-version 6.12.0`. The probe imports the binding and bundled Qt runtime,
checks their distribution/runtime major and minor versions, rejects mixed binding
and Qt target generations, starts a real `QApplication` and paints a widget. With
the current published packages it reports that 6.12 validation is deferred; once
the upstream 6.12 wheel is available, the same blocking job automatically
exercises that exact 6.12 line. It also refuses to treat a newer 6.13 line as
evidence for 6.12. A strict local certification run is:

```bash
python scripts/check_pyqt6_compatibility.py \
  --require-pyqt6 --target-version 6.12.0 --require-target
```

The repository also has a scheduled and manually dispatchable cross-platform
workflow for Linux, Windows, and macOS that installs Riverbank's prerelease
channel. It first checks whether a 6.12 version is available; when it is, each
runner upgrades within `6.12.x` and enables strict target validation. Before
publication it runs the latest available prerelease in deferred mode. In both
cases it renders every GUI preset and exercises the GUI controls. It remains
separate from the normal pull-request gate because upstream prerelease
availability changes over time, while still producing retained evidence when
the probe runs.

For Riverbank pre-release validation before a public 6.12 wheel exists, use its
official package index in an isolated environment, then run the same compatibility,
render and interaction gates:

```bash
python -m pip install --index-url https://pypi.org/simple \
  --extra-index-url https://www.riverbankcomputing.com/pypi/simple/ \
  --pre PyQt6
python scripts/check_pyqt6_compatibility.py --require-pyqt6 --target-version 6.12.0
python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 300
python scripts/check_gui_interactions.py --require-pyqt6
```

As of 2026-08-29, [PyQt6 on PyPI](https://pypi.org/project/PyQt6/) publishes
6.11.0 as its latest binding release and [PyQt6-Qt6 on PyPI](https://pypi.org/project/PyQt6-Qt6/)
publishes the 6.11.x Qt runtime line. [Qt 6.12 final is scheduled for
2026-09-22](https://wiki.qt.io/Qt_6.12_Release), so a 6.12 certification claim
cannot honestly be made from the currently published wheels.

## Explicit exclusions

- Free-threaded `3.15t` is not claimed. PyQt6 and other extension dependencies
  need their own free-threading evidence before that separate runtime can be
  supported.
- Native release bundles continue to use the pinned Python 3.12 release
  toolchain for reproducible packaging. They are standalone artifacts and do
  not claim to embed Python 3.15.
- Linux i386/armhf and legacy Windows promotion still require their independent
  native-host evidence. Python 3.15 is not part of either protected 32-bit Linux
  target claim until target-native interpreter, dependency and package evidence
  is accepted. Adding a Python classifier or hosted 64-bit CI row does not
  satisfy those platform gates.
- BSD, Solaris/illumos and other source-only host rows do not gain a Python 3.15
  production claim from OS-independent metadata. They remain on Python 3.10
  through 3.14 until native dependency and smoke evidence is recorded.

Run the local static contract with:

```bash
python scripts/check_python_support.py
python scripts/check_ci_workflow.py
```

On native Windows, the Python 3.15 SSH proof can be reproduced after installing
`paramiko==5.0.0`:

```powershell
$env:QT_QPA_PLATFORM = "windows"
$env:ROW_REQUIRE_WINDOWS_SSH_LOOPBACK = "1"
$env:ROW_WINDOWS_SSH_EVIDENCE_DIR = "artifacts/python315-windows-ssh"
python -m pytest -q tests/test_windows_ssh_loopback.py
```

The configured release-blocking contracts are the `Python 3.15 readiness` and
`Native Windows readiness` contexts from the GitHub `ci` workflow. Release
preflight independently queries GitHub Actions and requires a completed
successful `ci` push run containing exactly one successful instance of both
aggregate jobs for the exact tagged source SHA on the default branch. It does
not accept a pull-request run, a different commit, a skipped aggregate, a job
from another attempt, or an older failed rerun. To avoid racing a tag pushed
alongside its source commit, release preflight waits for up to 90 minutes with a
bounded 15-second poll interval. It paginates the attempt-specific job list and
rejects truncated or
inconsistent API responses. Only that completed run and its retained per-host
artifacts are authoritative runtime proof. A local compile pass on one operating
system is useful diagnostic evidence,
but it is not a substitute for that six-host result.
