# Rebuild the GUI with a modified Qt library

The Windows x64/ARM64 and macOS GUI packages use PyQt6 6.12.1 with Qt 6.12.0.
The files `PyQt6-6.12.1-source.json` and `qt-everywhere-src-6.12.0-source.json`
next to this guide give the source archive URLs and SHA-256 digests.

## Prepare the replacement

Start with the Remote Ops Workspace source for the release and Python 3.14
for the target architecture. Windows packaging also uses WiX and Inno Setup.
On macOS, use the native Apple build and packaging tools.

Prepare a local `PyQt6-Qt6` runtime wheel for the same platform and architecture
with your modified, binary-compatible Qt 6.12.0 libraries and plugins. One way
to make it is to unpack the matching upstream runtime wheel with `wheel unpack`,
replace the libraries you built under `PyQt6/Qt6`, and run `wheel pack` on the
unpacked directory to regenerate the wheel and its file hashes. Preserve the
runtime layout and the Qt framework structure on macOS. Keep the repacked wheel
in a separate directory and set `ROW_QT_WHEEL` to its absolute filename.
[Wheel unpack](https://wheel.readthedocs.io/en/stable/reference/wheel_unpack.html) ·
[Wheel pack](https://wheel.readthedocs.io/en/stable/reference/wheel_pack.html)

## Build with the replacement

Run the commands for your platform from the checkout root. They install the
release dependencies first, then replace the Qt runtime from your local file
in the same environment that PyInstaller will use.

**Windows PowerShell 7.4 or later** (use `-Arch arm64` with ARM64 Python)

```powershell
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$wheel = (Get-Item -LiteralPath $env:ROW_QT_WHEEL).FullName
py -3.14 -m venv .qt-relink
$py = (Resolve-Path .qt-relink/Scripts/python.exe).Path
& $py -m pip install --constraint requirements-release.txt ".[desktop,security,package,servers]"
& $py -m pip install --no-index --no-deps --force-reinstall $wheel
& $py -m pip check
& $py -c "from PyQt6.QtCore import QLibraryInfo as Q; print(Q.path(Q.LibraryPath.BinariesPath))"
$env:ROW_REQUIRE_RELEASE_SIGNING = "0"
pwsh -File scripts/make_windows_native.ps1 -Python $py -Arch x64
```

**macOS**

```sh
set -e
python3.14 -m venv .qt-relink
py="$PWD/.qt-relink/bin/python"
"$py" -m pip install --constraint requirements-release.txt ".[desktop,security,package,servers]"
"$py" -m pip install --no-index --no-deps --force-reinstall "${ROW_QT_WHEEL:?set the absolute path to your modified wheel}"
"$py" -m pip check
"$py" -c "from PyQt6.QtCore import QLibraryInfo as Q; print(Q.path(Q.LibraryPath.LibrariesPath))"
ROW_REQUIRE_RELEASE_SIGNING=0 PYTHON_BIN="$py" bash scripts/make_macos_native.sh
```

Check the Qt library in the printed directory against your modified build.
The installers are written to `native-dist/windows` or `native-dist/macos`.

## Check the installed library

Install or extract your rebuilt package. For a modified QtCore, inspect these
files using a distinctive byte string from your build that the upstream binary
does not contain. For a change to a different library or plugin, inspect that
member instead.

- **Windows.** Open the installed `bin/row-gui.exe` with
  `& $py -m PyInstaller.utils.cliutils.archive_viewer "PATH_TO_ROW_GUI_EXE"`.
  Enter `X` followed by the exact
  displayed member name ending in `Qt6Core.dll`, then give the extracted DLL
  a new output filename. [PyInstaller archive viewer](https://pyinstaller.org/en/stable/advanced-topics.html#using-pyi-archive-viewer)
- **macOS.** In the installed `Remote Ops Workspace.app`, find the framework
  binary with `find "/Applications/Remote Ops Workspace.app/Contents/Frameworks" -type f -name QtCore`.
  PyInstaller can rewrite Mach-O load paths and the build ad-hoc signs the app,
  so the whole-file hash can change during packaging.

For example, pass the extracted DLL or installed framework binary and your
actual ASCII build marker to Python. The check exits successfully only when the
specified file contains that marker. Launch the rebuilt GUI and exercise the
behavior you changed.

```sh
python -c "import pathlib, sys; sys.exit(sys.argv[2].encode('ascii') not in pathlib.Path(sys.argv[1]).read_bytes())" "PATH_TO_LIBRARY" "YOUR_BUILD_MARKER"
```
