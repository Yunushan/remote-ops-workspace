#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DIST="native-dist/macos"
ARCH=""
VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dist)
      DIST="$2"
      shift 2
      ;;
    --arch)
      ARCH="$2"
      shift 2
      ;;
    --version)
      VERSION="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  VERSION="$(python3 - <<'PY'
from pathlib import Path
import re

text = Path("pyproject.toml").read_text(encoding="utf-8")
match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
if not match:
    raise SystemExit("pyproject.toml does not define project.version")
print(match.group(1))
PY
)"
fi

if [[ -z "$ARCH" ]]; then
  case "$(uname -m)" in
    x86_64) ARCH="x64" ;;
    arm64|aarch64) ARCH="arm64" ;;
    *) ARCH="$(uname -m)" ;;
  esac
fi

OUT_DIR="$ROOT/$DIST"
DMG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARCH}.dmg"
PKG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARCH}.pkg"
APP_NAME="Remote Ops Workspace.app"
APP_ID="io.github.remoteopsworkspace.app"
SMOKE_ROOT="$ROOT/build/native-smoke/macos-${ARCH}"
MOUNT_DIR="$SMOKE_ROOT/dmg-mount"
DMG_APP_DIR="$SMOKE_ROOT/dmg-app"
DMG_APP="$DMG_APP_DIR/$APP_NAME"
PKG_APP="/Applications/$APP_NAME"

for artifact in "$DMG" "$PKG"; do
  if [[ ! -f "$artifact" ]]; then
    echo "native installer smoke artifact missing: $artifact" >&2
    exit 1
  fi
done

rm -rf "$SMOKE_ROOT"
mkdir -p "$MOUNT_DIR" "$DMG_APP_DIR"

cleanup() {
  hdiutil detach "$MOUNT_DIR" -quiet >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "native installer smoke: DMG install"
hdiutil attach "$DMG" -mountpoint "$MOUNT_DIR" -nobrowse -readonly -quiet
if [[ ! -d "$MOUNT_DIR/$APP_NAME" ]]; then
  echo "DMG does not contain $APP_NAME" >&2
  exit 1
fi
ditto "$MOUNT_DIR/$APP_NAME" "$DMG_APP"

echo "native installer smoke: DMG verify"
codesign --verify --deep --strict "$DMG_APP"

echo "native installer smoke: DMG upgrade"
rm -rf "$DMG_APP"
ditto "$MOUNT_DIR/$APP_NAME" "$DMG_APP"
codesign --verify --deep --strict "$DMG_APP"

echo "native installer smoke: DMG uninstall"
rm -rf "$DMG_APP"
if [[ -e "$DMG_APP" ]]; then
  echo "DMG uninstall cleanup left app bundle behind" >&2
  exit 1
fi
cleanup
trap - EXIT

echo "native installer smoke: PKG install"
sudo installer -pkg "$PKG" -target /
if [[ ! -d "$PKG_APP" ]]; then
  echo "PKG install did not create $PKG_APP" >&2
  exit 1
fi

echo "native installer smoke: PKG verify"
codesign --verify --deep --strict "$PKG_APP"

echo "native installer smoke: PKG upgrade"
sudo installer -pkg "$PKG" -target /
if [[ ! -d "$PKG_APP" ]]; then
  echo "PKG upgrade removed $PKG_APP" >&2
  exit 1
fi
codesign --verify --deep --strict "$PKG_APP"

echo "native installer smoke: PKG uninstall"
sudo rm -rf "$PKG_APP"
sudo pkgutil --forget "$APP_ID" >/dev/null 2>&1 || true
if [[ -e "$PKG_APP" ]]; then
  echo "PKG uninstall cleanup left app bundle behind" >&2
  exit 1
fi

echo "native installer smoke passed for macOS $ARCH"
