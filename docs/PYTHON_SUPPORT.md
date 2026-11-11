# Python runtime support

Remote Ops Workspace project metadata accepts source-host installation on
standard, GIL-enabled CPython 3.10 through 3.15. The authoritative 3.15 runtime
claim currently covers the hosted Linux, Windows and macOS CI families described
below; target-specific support rows may be narrower. Project metadata uses
`requires-python = ">=3.10,<3.16"`: versions below 3.10 are missing required
language and standard-library behavior, while Python 3.16 has not been tested
and must not be accepted implicitly.

## Python 3.15 evidence boundary

Python 3.15.0 reached general availability on October 9, 2026.
See the [Python 3.15 release schedule](https://peps.python.org/pep-0790/).

- **Stable CPython 3.15.** The blocking compatibility matrix runs the full
  test suite on Linux, Windows and macOS. The optional-dependency matrix repeats
  the suite with the desktop, security, package and development extras installed.
  It runs `pip check`, exercises the extras, renders and exercises every GUI
  preset, and installs the wheel and sdist in clean virtual environments. It
  also uses PyInstaller 6.21 or newer to build and launch a one-file CLI
  executable. The smoke runs `--version` and `platforms --json` and retains the
  executable SHA-256 and command evidence. Both Windows architectures run real
  OpenSSH/ConPTY, ProxyJump, terminal-input and GUI terminal-pane tests.
- **3.15 final-GA certification.** Each optional-dependency host must record
  `releaselevel=final` on a standard GIL-enabled 3.15 interpreter. Release
  evidence binds those results to the exact tagged source SHA.

The dedicated evidence matrix covers Linux x64 and ARM64, Windows x64 and ARM64, and macOS Intel and Apple Silicon. The normal compatibility matrix also runs
3.15 on every tracked hosted macOS row and explicit Linux/Windows ARM64 rows.
These jobs are not advisory and may not use `continue-on-error`.

The stable aggregate check context is `Python 3.15 readiness`. It evaluates with
`always()` and requires the normal compatibility matrix, the six-host
optional-dependency matrix, Apple 27 readiness and the PyQt6 minimum-runtime
matrix. Repository governance requires that exact context. Merge blocking
becomes effective only after the
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

## PyQt6 compatibility

The desktop extra supports PyQt6 6.11.0 up to, but excluding, PyQt6 7.0.
Release builds pin PyQt6 and its Qt runtime to 6.12.0. CI also tests the
hash-pinned PyQt6 6.11.0 and Qt 6.11.2 minimum across Linux, Windows and
macOS on x64 and ARM64. The minimum job starts Qt and renders the GUI presets.

The Python 3.15 optional-dependency matrix imports the binding and Qt, checks
their distribution and runtime versions, and renders a real Qt widget. To
require the 6.12 runtime when running the probe locally:

```bash
python scripts/check_pyqt6_compatibility.py \
  --require-pyqt6 --target-version 6.12.0 --require-target
```

The scheduled and manually dispatchable workflow installs the latest available
6.12 wheels from PyPI and Riverbank's prerelease index. Its strict probe also
requires an installed PyQt6 binding newer than the release pin. It renders
every GUI preset and exercises the GUI controls on Linux, Windows and macOS.
Upstream wheel availability can change between runs. The workflow records
its evidence separately from the blocking pull-request checks.

## Explicit exclusions

- Free-threaded `3.15t` is not claimed. PyQt6 and other extension dependencies
  need their own free-threading evidence before that separate runtime can be
  supported.
- Native release bundles use the exact Python 3.14.7 release
  toolchain recorded in `configs/release_toolchain.json`. They are standalone
  artifacts and do not claim to embed Python 3.15.
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
