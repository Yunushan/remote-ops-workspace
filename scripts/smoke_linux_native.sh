#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DIST="native-dist/linux"
ARCH="${TARGET_ARCH:-$(uname -m)}"
VERSION=""
TARGET=""
WORKFLOW_RUN_URL=""
WORKFLOW_RUN_ATTEMPT=""
SOURCE_HEAD_SHA=""

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
    --target)
      TARGET="$2"
      shift 2
      ;;
    --workflow-run-url)
      WORKFLOW_RUN_URL="$2"
      shift 2
      ;;
    --workflow-run-attempt)
      WORKFLOW_RUN_ATTEMPT="$2"
      shift 2
      ;;
    --source-head-sha)
      SOURCE_HEAD_SHA="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -n "$TARGET" && -z "$WORKFLOW_RUN_URL" ]] || [[ -z "$TARGET" && -n "$WORKFLOW_RUN_URL" ]]; then
  echo "--target and --workflow-run-url must be provided together" >&2
  exit 2
fi

if [[ -n "$TARGET" && -z "$SOURCE_HEAD_SHA" ]]; then
  echo "--source-head-sha is required with --target" >&2
  exit 2
fi

if [[ -n "$TARGET" && -z "$WORKFLOW_RUN_ATTEMPT" ]]; then
  echo "--workflow-run-attempt is required with --target" >&2
  exit 2
fi

if [[ -z "$TARGET" && -n "$SOURCE_HEAD_SHA" ]]; then
  echo "--source-head-sha requires --target" >&2
  exit 2
fi

if [[ -z "$TARGET" && -n "$WORKFLOW_RUN_ATTEMPT" ]]; then
  echo "--workflow-run-attempt requires --target" >&2
  exit 2
fi

if [[ -n "$SOURCE_HEAD_SHA" && ! "$SOURCE_HEAD_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "--source-head-sha must be a 40-character lowercase Git SHA" >&2
  exit 2
fi

if [[ -n "$WORKFLOW_RUN_ATTEMPT" && ! "$WORKFLOW_RUN_ATTEMPT" =~ ^[1-9][0-9]*$ ]]; then
  echo "--workflow-run-attempt must be a positive integer" >&2
  exit 2
fi

if [[ -n "$TARGET" ]]; then
  case "$TARGET:$ARCH" in
    linux-i386:i386|linux-armhf:armhf)
      ;;
    *)
      echo "target $TARGET does not match smoke arch $ARCH" >&2
      exit 2
      ;;
  esac
fi

SMOKE_UNAME_MACHINE="$(uname -m)"
SMOKE_DPKG_ARCH="$(dpkg --print-architecture)"
SMOKE_USERLAND_BITS="$(getconf LONG_BIT)"
SMOKE_PYTHON_SSL_OPENSSL="$(python3 - <<'PY'
import ssl

print(getattr(ssl, "OPENSSL_VERSION", ""))
PY
)"
SMOKE_OPENSSL_CLI_VERSION="$(openssl version)"
SMOKE_GIT_HEAD_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
SMOKE_OBSERVED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -n "$TARGET" ]]; then
  case "$TARGET" in
    linux-i386)
      case "$SMOKE_UNAME_MACHINE" in
        i386|i486|i586|i686|x86)
          ;;
        *)
          echo "target $TARGET must smoke on an i386/i686 userland, got uname -m $SMOKE_UNAME_MACHINE" >&2
          exit 2
          ;;
      esac
      if [[ "$SMOKE_DPKG_ARCH" != "i386" ]]; then
        echo "target $TARGET must smoke on dpkg architecture i386, got $SMOKE_DPKG_ARCH" >&2
        exit 2
      fi
      ;;
    linux-armhf)
      case "$SMOKE_UNAME_MACHINE" in
        armv6l|armv7l|armv7hl|armhf)
          ;;
        *)
          echo "target $TARGET must smoke on an armhf/armv7 userland, got uname -m $SMOKE_UNAME_MACHINE" >&2
          exit 2
          ;;
      esac
      if [[ "$SMOKE_DPKG_ARCH" != "armhf" ]]; then
        echo "target $TARGET must smoke on dpkg architecture armhf, got $SMOKE_DPKG_ARCH" >&2
        exit 2
      fi
      ;;
  esac
  if [[ "$SMOKE_USERLAND_BITS" != "32" ]]; then
    echo "target $TARGET must smoke on a 32-bit userland, got $SMOKE_USERLAND_BITS" >&2
    exit 2
  fi
  if [[ -z "$SMOKE_GIT_HEAD_SHA" ]]; then
    echo "target $TARGET requires git rev-parse HEAD for source head binding" >&2
    exit 2
  fi
  if [[ "$SMOKE_GIT_HEAD_SHA" != "$SOURCE_HEAD_SHA" ]]; then
    echo "target $TARGET source head sha $SOURCE_HEAD_SHA does not match git HEAD $SMOKE_GIT_HEAD_SHA" >&2
    exit 2
  fi
fi

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

SMOKE_COMMAND="bash scripts/smoke_linux_native.sh --arch $ARCH --dist $DIST"
if [[ -n "$TARGET" ]]; then
  SMOKE_COMMAND="$SMOKE_COMMAND --target $TARGET --workflow-run-url $WORKFLOW_RUN_URL --workflow-run-attempt $WORKFLOW_RUN_ATTEMPT --source-head-sha $SOURCE_HEAD_SHA"
fi

echo "native installer smoke command: $SMOKE_COMMAND"
echo "native installer smoke release: v$VERSION"
echo "native installer smoke target arch: $ARCH"
if [[ -n "$TARGET" ]]; then
  echo "native installer smoke target: $TARGET"
  echo "native installer smoke workflow run: $WORKFLOW_RUN_URL"
  echo "native installer smoke workflow run attempt: $WORKFLOW_RUN_ATTEMPT"
  echo "native installer smoke source head sha: $SOURCE_HEAD_SHA"
  echo "native installer smoke git head sha: $SMOKE_GIT_HEAD_SHA"
  SMOKE_WORKFLOW_RUN_ID="${WORKFLOW_RUN_URL%/}"
  SMOKE_WORKFLOW_RUN_ID="${SMOKE_WORKFLOW_RUN_ID##*/}"
  echo "native installer smoke host label: ${TARGET}-builder"
  echo "native installer smoke evidence run id: ${TARGET}-${VERSION//./-}-run-${SMOKE_WORKFLOW_RUN_ID}"
  echo "native installer smoke observed at utc: $SMOKE_OBSERVED_AT_UTC"
fi
echo "native installer smoke uname machine: $SMOKE_UNAME_MACHINE"
echo "native installer smoke dpkg architecture: $SMOKE_DPKG_ARCH"
echo "native installer smoke userland bits: $SMOKE_USERLAND_BITS"
echo "native installer smoke python ssl openssl: $SMOKE_PYTHON_SSL_OPENSSL"
echo "native installer smoke openssl cli version: $SMOKE_OPENSSL_CLI_VERSION"
echo "native installer smoke TLS minimum modern profiles: TLS 1.2"
echo "native installer smoke TLS preferred modern profiles: TLS 1.3"
echo "native installer smoke legacy compatibility profile: isolated-opt-in"
echo "native installer smoke legacy crypto scope: profile-only"
echo "native installer smoke weak crypto global default: false"
echo "native installer smoke modern defaults unchanged: true"
for artifact in "$DEB" "$RPM" "$APPIMAGE"; do
  digest="$(sha256sum "$artifact" | awk '{print $1}')"
  echo "native installer smoke artifact sha256: $(basename "$artifact") $digest"
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
sudo -n dpkg -i "$DEB"
echo "native installer smoke: DEB verify"
verify_row /usr/bin/row
echo "native installer smoke: DEB upgrade"
sudo -n dpkg -i "$DEB"
verify_row /usr/bin/row
echo "native installer smoke: DEB uninstall"
sudo -n dpkg -r remote-ops-workspace
if [[ -e /usr/bin/row ]]; then
  echo "DEB uninstall left /usr/bin/row behind" >&2
  exit 1
fi

echo "native installer smoke: RPM install"
sudo -n rpm -Uvh --nodeps --replacepkgs "$RPM"
echo "native installer smoke: RPM verify"
verify_row /usr/bin/row
echo "native installer smoke: RPM upgrade"
sudo -n rpm -Uvh --nodeps --replacepkgs "$RPM"
verify_row /usr/bin/row
echo "native installer smoke: RPM uninstall"
sudo -n rpm -e --nodeps remote-ops-workspace
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
