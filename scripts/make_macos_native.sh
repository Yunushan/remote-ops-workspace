#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DIST="${DIST:-native-dist/macos}"
VERSION="$("$PYTHON_BIN" - <<'PY'
from pathlib import Path
import re

text = Path("pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
if not match:
    raise SystemExit("pyproject.toml does not define project.version")
print(match.group(1))
PY
)"

if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" != "v${VERSION}" ]]; then
  echo "GITHUB_REF_NAME='${GITHUB_REF_NAME}' does not match project version v${VERSION}" >&2
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARTIFACT_ARCH="x64" ;;
  arm64|aarch64) ARTIFACT_ARCH="arm64" ;;
  *) ARTIFACT_ARCH="$ARCH" ;;
esac
if [[ -n "${EXPECTED_ARTIFACT_ARCH:-}" && "$ARTIFACT_ARCH" != "$EXPECTED_ARTIFACT_ARCH" ]]; then
  echo "EXPECTED_ARTIFACT_ARCH='${EXPECTED_ARTIFACT_ARCH}' does not match detected artifact architecture '${ARTIFACT_ARCH}'" >&2
  exit 1
fi

OUT_DIR="$ROOT/$DIST"
BUILD_DIR="$ROOT/build/native/macos"
PY_DIST="$BUILD_DIR/pyinstaller-dist"
PY_WORK="$BUILD_DIR/pyinstaller-work"
LAUNCHER="$BUILD_DIR/remote_ops_workspace_gui_launcher.py"
APP_NAME="Remote Ops Workspace"
APP_PATH="$PY_DIST/$APP_NAME.app"

rm -rf "$BUILD_DIR"
mkdir -p "$OUT_DIR" "$PY_DIST" "$PY_WORK"

cat > "$LAUNCHER" <<'PY'
from remote_ops_workspace.cli import main

raise SystemExit(main(["gui"]))
PY

"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --noconfirm \
  --windowed \
  --name "$APP_NAME" \
  --distpath "$PY_DIST" \
  --workpath "$PY_WORK" \
  --specpath "$BUILD_DIR" \
  --collect-submodules remote_ops_workspace \
  --copy-metadata remote-ops-workspace \
  "$LAUNCHER"

if [[ ! -d "$APP_PATH" ]]; then
  echo "PyInstaller did not create $APP_PATH" >&2
  exit 1
fi

codesign --force --deep --sign - "$APP_PATH"

DMG_STAGE="$BUILD_DIR/dmg-stage"
mkdir -p "$DMG_STAGE"
cp -R "$APP_PATH" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
cp "$ROOT/LICENSE" "$DMG_STAGE/LICENSE"
cp "$ROOT/NOTICE" "$DMG_STAGE/NOTICE"
cat > "$DMG_STAGE/RELEASE_TARGET.md" <<EOF
# macOS native release

Package: remote-ops-workspace
Version: v$VERSION
Target: macOS $ARTIFACT_ARCH

This native package installs a PyInstaller app bundle for the PyQt6 desktop UI.
Protocol sessions still depend on macOS system tools such as OpenSSH, XQuartz,
Microsoft Remote Desktop/FreeRDP, and VNC clients.

This CI-built artifact is ad-hoc signed. Production distribution should add
Developer ID signing and Apple notarization.
EOF

DMG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARTIFACT_ARCH}.dmg"
hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG"

PKG_ROOT="$BUILD_DIR/pkgroot"
mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP_PATH" "$PKG_ROOT/Applications/"
PKG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARTIFACT_ARCH}.pkg"
pkgbuild \
  --root "$PKG_ROOT" \
  --identifier "io.github.remoteopsworkspace.app" \
  --version "$VERSION" \
  --install-location "/" \
  "$PKG"

"$PYTHON_BIN" - "$ROOT" "$VERSION" "$DMG" "$PKG" "$ARTIFACT_ARCH" "$OUT_DIR" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]
dmg = Path(sys.argv[3])
pkg = Path(sys.argv[4])
arch = sys.argv[5]
out_dir = Path(sys.argv[6])

def repo_path(path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()

manifest = [
    {
        "phase": "phase-3-macos-native",
        "target": f"macos-{arch}-dmg",
        "label": f"macOS {arch} DMG",
        "file": repo_path(dmg),
        "format": "dmg",
        "install_command": "Open the DMG and drag the app to Applications.",
        "notes": [
            "Ad-hoc signed PyInstaller app bundle for the PyQt6 desktop UI.",
            "Developer ID signing and notarization should be added for production distribution.",
        ],
    },
    {
        "phase": "phase-3-macos-native",
        "target": f"macos-{arch}-pkg",
        "label": f"macOS {arch} PKG",
        "file": repo_path(pkg),
        "format": "pkg",
        "install_command": f"sudo installer -pkg {pkg.name} -target /",
        "notes": [
            "Installer package for managed macOS deployment.",
            "Unsigned CI artifact; production distribution should add signing and notarization.",
        ],
    },
]

manifest_path = out_dir / f"remote-ops-workspace-v{version}-macos-{arch}-native-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"created {repo_path(dmg)}")
print(f"created {repo_path(pkg)}")
print(f"created {repo_path(manifest_path)}")
PY
