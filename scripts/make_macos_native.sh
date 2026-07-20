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

EXPECTED_TAG="v${VERSION}"
if [[ -n "${RELEASE_TAG:-}" && "${RELEASE_TAG}" != "${EXPECTED_TAG}" ]]; then
  echo "RELEASE_TAG='${RELEASE_TAG}' does not match project version ${EXPECTED_TAG}" >&2
  exit 1
fi
if [[ "${GITHUB_REF_TYPE:-}" == "tag" && "${GITHUB_REF_NAME:-}" != "${EXPECTED_TAG}" ]]; then
  echo "GITHUB_REF_NAME='${GITHUB_REF_NAME:-}' does not match project version ${EXPECTED_TAG}" >&2
  exit 1
fi
if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* && "${GITHUB_REF_NAME}" != "${EXPECTED_TAG}" ]]; then
  echo "GITHUB_REF_NAME='${GITHUB_REF_NAME}' does not match project version ${EXPECTED_TAG}" >&2
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

sign_macos_artifact() {
  if [[ "${ROW_REQUIRE_RELEASE_SIGNING:-0}" != "1" ]]; then
    codesign --force --deep --sign - "$1"
    return
  fi
  : "${ROW_MACOS_SIGN_IDENTITY:?Production signing requires ROW_MACOS_SIGN_IDENTITY}"
  codesign --force --deep --options runtime --timestamp --sign "$ROW_MACOS_SIGN_IDENTITY" "$1"
  codesign --verify --deep --strict --verbose=2 "$1"
}

create_macos_dmg() {
  local dmg_stage="$1"
  local dmg="$2"
  local dmg_tmp="$BUILD_DIR/$(basename "${dmg%.dmg}").tmp.dmg"
  local attempt
  local status=1

  rm -f "$dmg" "$dmg_tmp"
  hdiutil detach "/Volumes/$APP_NAME" -force >/dev/null 2>&1 || true
  for attempt in 1 2 3; do
    if hdiutil create -volname "$APP_NAME" -srcfolder "$dmg_stage" -format UDZO "$dmg_tmp"; then
      mv "$dmg_tmp" "$dmg"
      return 0
    fi
    status=$?
    rm -f "$dmg_tmp"
    hdiutil detach "/Volumes/$APP_NAME" -force >/dev/null 2>&1 || true
    sleep "$((attempt * 3))"
  done
  return "$status"
}

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

sign_macos_artifact "$APP_PATH"

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

Production releases require Developer ID signing, notarization and stapling.
EOF

DMG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARTIFACT_ARCH}.dmg"
create_macos_dmg "$DMG_STAGE" "$DMG"

PKG_ROOT="$BUILD_DIR/pkgroot"
mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP_PATH" "$PKG_ROOT/Applications/"
COMPONENT_PLIST="$BUILD_DIR/components.plist"
pkgbuild --analyze --root "$PKG_ROOT" "$COMPONENT_PLIST"
/usr/libexec/PlistBuddy -c "Set :0:BundleIsRelocatable false" "$COMPONENT_PLIST"
PKG="$OUT_DIR/remote-ops-workspace-v${VERSION}-macos-${ARTIFACT_ARCH}.pkg"
pkgbuild \
  --root "$PKG_ROOT" \
  --component-plist "$COMPONENT_PLIST" \
  --identifier "io.github.remoteopsworkspace.app" \
  --version "$VERSION" \
  --install-location "/" \
  "$PKG"

if [[ "${ROW_REQUIRE_RELEASE_SIGNING:-0}" == "1" ]]; then
  : "${ROW_MACOS_INSTALLER_SIGN_IDENTITY:?Production signing requires ROW_MACOS_INSTALLER_SIGN_IDENTITY}"
  : "${ROW_MACOS_NOTARY_PROFILE:?Production signing requires ROW_MACOS_NOTARY_PROFILE}"
  SIGNED_PKG="$BUILD_DIR/$(basename "$PKG").signed"
  productsign --sign "$ROW_MACOS_INSTALLER_SIGN_IDENTITY" "$PKG" "$SIGNED_PKG"
  mv "$SIGNED_PKG" "$PKG"
  xcrun notarytool submit "$PKG" --keychain-profile "$ROW_MACOS_NOTARY_PROFILE" --wait
  xcrun stapler staple "$PKG"
  xcrun notarytool submit "$DMG" --keychain-profile "$ROW_MACOS_NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
fi

"$PYTHON_BIN" - "$ROOT" "$VERSION" "$DMG" "$PKG" "$ARTIFACT_ARCH" "$OUT_DIR" "${ROW_REQUIRE_RELEASE_SIGNING:-0}" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]
dmg = Path(sys.argv[3])
pkg = Path(sys.argv[4])
arch = sys.argv[5]
out_dir = Path(sys.argv[6])
production_signing = sys.argv[7] == "1"
signing = {
    "release_channel": "production-signed" if production_signing else "unsigned-preview",
    "production_trusted": production_signing,
    "developer_id_verified": production_signing,
    "notarized": production_signing,
    "stapled": production_signing,
}

def repo_path(path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def add_integrity(item: dict[str, object]) -> dict[str, object]:
    path = root / str(item["file"])
    item["size_bytes"] = path.stat().st_size
    item["sha256"] = sha256_file(path)
    return item

def write_checksums(paths: list[Path], checksum_path: Path) -> None:
    lines = [f"{sha256_file(path)}  {path.name}" for path in paths]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="ascii")

manifest = [
    {
        "phase": "phase-3-macos-native",
        "target": f"macos-{arch}-dmg",
        "label": f"macOS {arch} DMG",
        "file": repo_path(dmg),
        "format": "dmg",
        "install_command": "Open the DMG and drag the app to Applications.",
        "signing": signing,
        "notes": (
            ["Developer ID signed, notarized, and stapled PyInstaller app bundle."]
            if production_signing
            else ["Ad-hoc signed PyInstaller app bundle; not trusted for production distribution."]
        ),
    },
    {
        "phase": "phase-3-macos-native",
        "target": f"macos-{arch}-pkg",
        "label": f"macOS {arch} PKG",
        "file": repo_path(pkg),
        "format": "pkg",
        "install_command": f"sudo installer -pkg {pkg.name} -target /",
        "signing": signing,
        "notes": (
            ["Developer ID signed, notarized, and stapled installer for managed deployment."]
            if production_signing
            else ["Unsigned preview installer; not trusted for production distribution."]
        ),
    },
]

manifest = [add_integrity(item) for item in manifest]

manifest_path = out_dir / f"remote-ops-workspace-v{version}-macos-{arch}-native-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
checksums = out_dir / f"remote-ops-workspace-v{version}-macos-{arch}-native-SHA256SUMS.txt"
write_checksums([dmg, pkg, manifest_path], checksums)
print(f"created {repo_path(dmg)}")
print(f"created {repo_path(pkg)}")
print(f"created {repo_path(manifest_path)}")
print(f"created {repo_path(checksums)}")
PY
