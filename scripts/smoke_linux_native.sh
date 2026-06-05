#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DIST="native-dist/linux"
ARCH="${TARGET_ARCH:-$(uname -m)}"
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

case "$ARCH" in
  x86_64)
    DEB_ARCH="amd64"
    RPM_ARCH="x86_64"
    APPIMAGE_ARCH="x86_64"
    ;;
  i386|i486|i586|i686|x86)
    DEB_ARCH="i386"
    RPM_ARCH="i686"
    APPIMAGE_ARCH="i686"
    ;;
  armv6l)
    DEB_ARCH="armhf"
    RPM_ARCH="armv6hl"
    APPIMAGE_ARCH="armhf"
    ;;
  armv7l|armv7hl|armhf)
    DEB_ARCH="armhf"
    RPM_ARCH="armv7hl"
    APPIMAGE_ARCH="armhf"
    ;;
  aarch64|arm64)
    DEB_ARCH="arm64"
    RPM_ARCH="aarch64"
    APPIMAGE_ARCH="aarch64"
    ;;
  *)
    DEB_ARCH="$ARCH"
    RPM_ARCH="$ARCH"
    APPIMAGE_ARCH="$ARCH"
    ;;
esac

OUT_DIR="$ROOT/$DIST"
DEB="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${DEB_ARCH}.deb"
RPM="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${RPM_ARCH}.rpm"
APPIMAGE="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${APPIMAGE_ARCH}.AppImage"
SMOKE_ROOT="$ROOT/build/native-smoke/linux-${ARCH}"
STAGED_APPIMAGE="$SMOKE_ROOT/appimage/row.AppImage"

for artifact in "$DEB" "$RPM" "$APPIMAGE"; do
  if [[ ! -f "$artifact" ]]; then
    echo "native installer smoke artifact missing: $artifact" >&2
    exit 1
  fi
done

verify_row() {
  local row_bin="$1"
  if [[ ! -x "$row_bin" ]]; then
    echo "expected executable missing: $row_bin" >&2
    exit 1
  fi
  "$row_bin" --version | grep -F "$VERSION" >/dev/null
}

rm -rf "$SMOKE_ROOT"
mkdir -p "$SMOKE_ROOT/appimage"

echo "native installer smoke: DEB install"
sudo dpkg -i "$DEB"
echo "native installer smoke: DEB verify"
verify_row /usr/bin/row
echo "native installer smoke: DEB upgrade"
sudo dpkg -i "$DEB"
verify_row /usr/bin/row
echo "native installer smoke: DEB uninstall"
sudo dpkg -r remote-ops-workspace
if [[ -e /usr/bin/row ]]; then
  echo "DEB uninstall left /usr/bin/row behind" >&2
  exit 1
fi

echo "native installer smoke: RPM install"
sudo rpm -Uvh --nodeps --replacepkgs "$RPM"
echo "native installer smoke: RPM verify"
verify_row /usr/bin/row
echo "native installer smoke: RPM upgrade"
sudo rpm -Uvh --nodeps --replacepkgs "$RPM"
verify_row /usr/bin/row
echo "native installer smoke: RPM uninstall"
sudo rpm -e --nodeps remote-ops-workspace
if [[ -e /usr/bin/row ]]; then
  echo "RPM uninstall left /usr/bin/row behind" >&2
  exit 1
fi

echo "native installer smoke: AppImage install"
install -m 755 "$APPIMAGE" "$STAGED_APPIMAGE"
echo "native installer smoke: AppImage verify"
APPIMAGE_EXTRACT_AND_RUN=1 "$STAGED_APPIMAGE" --version | grep -F "$VERSION" >/dev/null
echo "native installer smoke: AppImage upgrade"
install -m 755 "$APPIMAGE" "$STAGED_APPIMAGE"
APPIMAGE_EXTRACT_AND_RUN=1 "$STAGED_APPIMAGE" --version | grep -F "$VERSION" >/dev/null
echo "native installer smoke: AppImage uninstall"
rm -f "$STAGED_APPIMAGE"
if [[ -e "$STAGED_APPIMAGE" ]]; then
  echo "AppImage uninstall cleanup left staged artifact behind" >&2
  exit 1
fi

echo "native installer smoke passed for Linux $ARCH"
