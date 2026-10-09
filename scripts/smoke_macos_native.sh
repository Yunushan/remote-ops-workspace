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
APP_EXECUTABLE_NAME="${APP_NAME%.app}"
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

BINDING_TARGET="macos-${ARCH}"
BINDING_REPORT="$SMOKE_ROOT/candidate-runtime-byte-binding.json"
python3 scripts/candidate_posix_byte_binding.py init --target "$BINDING_TARGET" --report "$BINDING_REPORT" --root "$ROOT"

candidate_check_app() {
  local executable="$1" public_path="$2" phase="$3" probe="$4"
  python3 scripts/candidate_posix_byte_binding.py check --target "$BINDING_TARGET" --report "$BINDING_REPORT" \
    --path "$executable" --public-path "$public_path" --stage "$phase" --probe "$probe"
}

cleanup() {
  hdiutil detach "$MOUNT_DIR" -quiet >/dev/null 2>&1 || true
}
trap cleanup EXIT

verify_app_runtime_resources() {
  local app_path="$1"
  local label="$2"
  local public_path="$3" phase="$4"
  local executable="$app_path/Contents/MacOS/$APP_EXECUTABLE_NAME"
  local probe_name
  local probe_file
  probe_name="$(printf '%s' "$label" | tr -c '[:alnum:]' '-')"
  probe_file="$SMOKE_ROOT/runtime-resources-${probe_name}.json"
  if [[ ! -x "$executable" ]]; then
    echo "$label installed app executable missing: $executable" >&2
    exit 1
  fi
  candidate_check_app "$executable" "$public_path" "$phase" platforms || return $?
  if ! "$executable" platforms --json >"$probe_file"; then
    echo "$label platforms --json failed for $executable" >&2
    exit 1
  fi
  python3 - "$probe_file" "$label" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
label = sys.argv[2]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"{label} platforms --json did not return valid JSON: {exc}")
for key in ("release_architectures", "windows_legacy_targets"):
    if not isinstance(payload.get(key), list) or not payload[key]:
        raise SystemExit(f"{label} packaged platform catalog has no {key}")
PY
  rm -f "$probe_file"
  echo "native installer smoke runtime resources: $label platforms --json"
}

verify_app_gui() {
  local app_path="$1"
  local label="$2"
  local public_path="$3" phase="$4"
  candidate_check_app "$app_path/Contents/MacOS/$APP_EXECUTABLE_NAME" "$public_path" "$phase" gui || return $?
  python3 - "$app_path/Contents/MacOS/$APP_EXECUTABLE_NAME" "$SMOKE_ROOT" "$VERSION" "$label" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

executable, smoke_root, version, label = sys.argv[1:]
home = Path(smoke_root) / f"gui-{uuid.uuid4().hex}"
report = home / "result.json"
environment = {**os.environ, "ROW_HOME": str(home), "QT_QPA_PLATFORM": "cocoa"}
subprocess.run([executable, "gui", "--smoke-json", str(report)], env=environment, timeout=25, check=True)
payload = json.loads(report.read_text(encoding="utf-8"))
if payload.get("success") is not True or payload.get("frozen") is not True or payload.get("qt_platform") != "cocoa" or payload.get("version") != version:
    raise SystemExit(f"{label} GUI report did not prove the frozen native macOS release")
if any(payload.get(key) is not True for key in ("profile_persisted", "profile_selected", "window_visible")) or payload.get("paint_colour_count", 0) < 3:
    raise SystemExit(f"{label} GUI profile workflow or paint evidence failed")
image = report.with_suffix(".png")
if hashlib.sha256(image.read_bytes()).hexdigest() != payload.get("screenshot_sha256"):
    raise SystemExit(f"{label} GUI screenshot digest did not match the startup report")
print(f"native installer smoke packaged GUI: {label} startup, profile selection and paint passed")
PY
}

echo "native installer smoke: DMG install"
hdiutil attach "$DMG" -mountpoint "$MOUNT_DIR" -nobrowse -readonly -quiet
if [[ ! -d "$MOUNT_DIR/$APP_NAME" ]]; then
  echo "DMG does not contain $APP_NAME" >&2
  exit 1
fi
ditto "$MOUNT_DIR/$APP_NAME" "$DMG_APP"

echo "native installer smoke: DMG verify"
codesign --verify --deep --strict "$DMG_APP"
verify_app_runtime_resources "$DMG_APP" "DMG verify" "dmg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" install
verify_app_gui "$DMG_APP" "DMG verify" "dmg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" install

echo "native installer smoke: DMG upgrade"
rm -rf "$DMG_APP"
ditto "$MOUNT_DIR/$APP_NAME" "$DMG_APP"
codesign --verify --deep --strict "$DMG_APP"
verify_app_runtime_resources "$DMG_APP" "DMG upgrade" "dmg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" reinstall

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
verify_app_runtime_resources "$PKG_APP" "PKG verify" "pkg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" install
verify_app_gui "$PKG_APP" "PKG verify" "pkg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" install

echo "native installer smoke: PKG upgrade"
sudo installer -pkg "$PKG" -target /
if [[ ! -d "$PKG_APP" ]]; then
  echo "PKG upgrade removed $PKG_APP" >&2
  exit 1
fi
codesign --verify --deep --strict "$PKG_APP"
verify_app_runtime_resources "$PKG_APP" "PKG upgrade" "pkg/$APP_NAME/Contents/MacOS/$APP_EXECUTABLE_NAME" reinstall

echo "native installer smoke: PKG uninstall"
sudo rm -rf "$PKG_APP"
sudo pkgutil --forget "$APP_ID" >/dev/null 2>&1 || true
if [[ -e "$PKG_APP" ]]; then
  echo "PKG uninstall cleanup left app bundle behind" >&2
  exit 1
fi

python3 scripts/candidate_posix_byte_binding.py complete --target "$BINDING_TARGET" --report "$BINDING_REPORT"
echo "native installer smoke passed for macOS $ARCH"
