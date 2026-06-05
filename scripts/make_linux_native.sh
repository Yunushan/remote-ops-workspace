#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DIST="${DIST:-native-dist/linux}"
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

HOST_ARCH="$(uname -m)"
UNAME_ARCH="${TARGET_ARCH:-$HOST_ARCH}"
case "$UNAME_ARCH" in
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
    DEB_ARCH="$UNAME_ARCH"
    RPM_ARCH="$UNAME_ARCH"
    APPIMAGE_ARCH="$UNAME_ARCH"
    ;;
esac

OUT_DIR="$ROOT/$DIST"
BUILD_DIR="$ROOT/build/native/linux"
PY_DIST="$BUILD_DIR/pyinstaller-dist"
PY_WORK="$BUILD_DIR/pyinstaller-work"
LAUNCHER="$BUILD_DIR/row_launcher.py"

rm -rf "$BUILD_DIR"
mkdir -p "$OUT_DIR" "$PY_DIST" "$PY_WORK"

cat > "$LAUNCHER" <<'PY'
from remote_ops_workspace.cli import main

raise SystemExit(main())
PY

"$PYTHON_BIN" -m PyInstaller \
  --clean \
  --noconfirm \
  --onefile \
  --name row \
  --console \
  --distpath "$PY_DIST" \
  --workpath "$PY_WORK" \
  --specpath "$BUILD_DIR" \
  --collect-submodules remote_ops_workspace \
  --copy-metadata remote-ops-workspace \
  "$LAUNCHER"

ROW_BIN="$PY_DIST/row"
if [[ ! -x "$ROW_BIN" ]]; then
  echo "PyInstaller did not create $ROW_BIN" >&2
  exit 1
fi

PKGROOT="$BUILD_DIR/pkgroot"
install -Dm755 "$ROW_BIN" "$PKGROOT/usr/bin/row"
install -Dm644 "$ROOT/LICENSE" "$PKGROOT/usr/share/doc/remote-ops-workspace/LICENSE"
install -Dm644 "$ROOT/NOTICE" "$PKGROOT/usr/share/doc/remote-ops-workspace/NOTICE"
install -Dm644 "$ROOT/README.md" "$PKGROOT/usr/share/doc/remote-ops-workspace/README.md"
cat > "$PKGROOT/usr/share/doc/remote-ops-workspace/RELEASE_TARGET.md" <<EOF
# Linux native release

Package: remote-ops-workspace
Version: v$VERSION
Target: Linux $UNAME_ARCH
Build host architecture: $HOST_ARCH

This native package installs the standalone `row` command built with
PyInstaller. Protocol sessions still depend on Linux system tools such as
OpenSSH, FreeRDP, TigerVNC, virt-viewer, x2goclient, mosh, and Xorg/Wayland
display tooling.

TARGET_ARCH may be used to select the artifact naming/mapping for a matching
builder, but this script does not cross-compile PyInstaller binaries. Run it on
the requested architecture or in an equivalent container/runner.
EOF

DEB_ROOT="$BUILD_DIR/debroot"
mkdir -p "$DEB_ROOT"
cp -a "$PKGROOT/." "$DEB_ROOT/"
mkdir -p "$DEB_ROOT/DEBIAN"
INSTALLED_SIZE="$(du -ks "$DEB_ROOT/usr" | awk '{print $1}')"
cat > "$DEB_ROOT/DEBIAN/control" <<EOF
Package: remote-ops-workspace
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Installed-Size: $INSTALLED_SIZE
Maintainer: Remote Ops Workspace Contributors <maintainers@example.invalid>
Description: Operator-first remote terminal and connection workspace
 Remote Ops Workspace provides a CLI and adapter-first workflows for SSH, RDP,
 VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, serial consoles,
 raw sockets, layouts, vaults, snippets, sync, GUI, and Web/PWA workflows.
EOF

DEB="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${DEB_ARCH}.deb"
dpkg-deb --root-owner-group --build "$DEB_ROOT" "$DEB"

RPMBUILD="$BUILD_DIR/rpmbuild"
mkdir -p "$RPMBUILD/BUILD" "$RPMBUILD/BUILDROOT" "$RPMBUILD/RPMS" "$RPMBUILD/SOURCES" "$RPMBUILD/SPECS" "$RPMBUILD/SRPMS"
SPEC="$RPMBUILD/SPECS/remote-ops-workspace.spec"
cat > "$SPEC" <<EOF
Name: remote-ops-workspace
Version: $VERSION
Release: 1%{?dist}
Summary: Operator-first remote terminal and connection workspace
License: MIT
BuildArch: $RPM_ARCH

%description
Remote Ops Workspace provides a CLI and adapter-first workflows for SSH, RDP,
VNC, SFTP, Mosh, Telnet, X11, SPICE, X2Go, ICA, HTTP/HTTPS, serial consoles,
raw sockets, layouts, vaults, snippets, sync, GUI, and Web/PWA workflows.

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/doc/remote-ops-workspace
cp "$PKGROOT/usr/bin/row" %{buildroot}/usr/bin/row
cp "$PKGROOT/usr/share/doc/remote-ops-workspace/LICENSE" %{buildroot}/usr/share/doc/remote-ops-workspace/LICENSE
cp "$PKGROOT/usr/share/doc/remote-ops-workspace/NOTICE" %{buildroot}/usr/share/doc/remote-ops-workspace/NOTICE
cp "$PKGROOT/usr/share/doc/remote-ops-workspace/README.md" %{buildroot}/usr/share/doc/remote-ops-workspace/README.md
cp "$PKGROOT/usr/share/doc/remote-ops-workspace/RELEASE_TARGET.md" %{buildroot}/usr/share/doc/remote-ops-workspace/RELEASE_TARGET.md

%files
/usr/bin/row
/usr/share/doc/remote-ops-workspace/LICENSE
/usr/share/doc/remote-ops-workspace/NOTICE
/usr/share/doc/remote-ops-workspace/README.md
/usr/share/doc/remote-ops-workspace/RELEASE_TARGET.md
EOF

rpmbuild --define "_topdir $RPMBUILD" --define "_build_id_links none" -bb "$SPEC"
RPM_SOURCE="$(find "$RPMBUILD/RPMS" -name '*.rpm' -type f | head -n 1)"
RPM="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${RPM_ARCH}.rpm"
cp "$RPM_SOURCE" "$RPM"

APPDIR="$BUILD_DIR/Remote_Ops_Workspace.AppDir"
install -Dm755 "$ROW_BIN" "$APPDIR/usr/bin/row"
install -Dm644 "$ROOT/LICENSE" "$APPDIR/usr/share/doc/remote-ops-workspace/LICENSE"
install -Dm644 "$ROOT/NOTICE" "$APPDIR/usr/share/doc/remote-ops-workspace/NOTICE"
cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/row" "$@"
EOF
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/remote-ops-workspace.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Remote Ops Workspace
Exec=row
Icon=remote-ops-workspace
Categories=Network;Utility;
Terminal=true
EOF
cat > "$APPDIR/remote-ops-workspace.svg" <<'EOF'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="18" fill="#12343b"/>
  <path d="M26 38h76v52H26z" fill="#ffffff"/>
  <path d="M35 49l16 15-16 15" fill="none" stroke="#12343b" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M59 78h31" fill="none" stroke="#12343b" stroke-width="8" stroke-linecap="round"/>
</svg>
EOF
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"
cp "$APPDIR/remote-ops-workspace.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/remote-ops-workspace.svg"

APPIMAGE="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${APPIMAGE_ARCH}.AppImage"
APPIMAGETOOL="${APPIMAGETOOL:-$BUILD_DIR/appimagetool-${APPIMAGE_ARCH}.AppImage}"
APPIMAGETOOL_URL="${APPIMAGETOOL_URL:-https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage}"
if ! command -v appimagetool >/dev/null 2>&1 && [[ ! -x "$APPIMAGETOOL" ]]; then
  curl -fsSL -o "$APPIMAGETOOL" "$APPIMAGETOOL_URL"
  if [[ -n "${APPIMAGETOOL_SHA256:-}" ]]; then
    echo "${APPIMAGETOOL_SHA256}  ${APPIMAGETOOL}" | sha256sum -c -
  else
    echo "warning: APPIMAGETOOL_SHA256 is not set; downloaded appimagetool was not checksum-verified" >&2
  fi
  chmod +x "$APPIMAGETOOL"
fi

if command -v appimagetool >/dev/null 2>&1; then
  ARCH="$APPIMAGE_ARCH" appimagetool "$APPDIR" "$APPIMAGE"
else
  ARCH="$APPIMAGE_ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$APPIMAGE"
fi

TARBALL="$OUT_DIR/remote-ops-workspace-v${VERSION}-linux-${APPIMAGE_ARCH}-native.tar.gz"
tar -C "$PKGROOT" -czf "$TARBALL" .

"$PYTHON_BIN" - "$ROOT" "$VERSION" "$OUT_DIR" "$DEB" "$RPM" "$APPIMAGE" "$TARBALL" "$DEB_ARCH" "$RPM_ARCH" "$APPIMAGE_ARCH" "$UNAME_ARCH" "$HOST_ARCH" <<'PY'
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2]
out_dir = Path(sys.argv[3])
deb = Path(sys.argv[4])
rpm = Path(sys.argv[5])
appimage = Path(sys.argv[6])
tarball = Path(sys.argv[7])
deb_arch = sys.argv[8]
rpm_arch = sys.argv[9]
appimage_arch = sys.argv[10]
requested_arch = sys.argv[11]
host_arch = sys.argv[12]

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
        "phase": "phase-4-linux-native",
        "target": f"linux-{deb_arch}-deb",
        "label": f"Linux {deb_arch} DEB",
        "architecture": deb_arch,
        "file": repo_path(deb),
        "format": "deb",
        "install_command": f"sudo apt install ./{deb.name}",
        "notes": [
            "Debian/Ubuntu package containing the standalone row CLI.",
            f"Requested architecture: {requested_arch}; build host architecture: {host_arch}.",
        ],
    },
    {
        "phase": "phase-4-linux-native",
        "target": f"linux-{rpm_arch}-rpm",
        "label": f"Linux {rpm_arch} RPM",
        "architecture": rpm_arch,
        "file": repo_path(rpm),
        "format": "rpm",
        "install_command": f"sudo rpm -Uvh {rpm.name}",
        "notes": [
            "Fedora/RHEL/openSUSE-style package containing the standalone row CLI.",
            f"Requested architecture: {requested_arch}; build host architecture: {host_arch}.",
        ],
    },
    {
        "phase": "phase-4-linux-native",
        "target": f"linux-{appimage_arch}-appimage",
        "label": f"Linux {appimage_arch} AppImage",
        "architecture": appimage_arch,
        "file": repo_path(appimage),
        "format": "AppImage",
        "install_command": f"chmod +x {appimage.name} && ./{appimage.name} --version",
        "notes": [
            "Portable AppImage containing the standalone row CLI.",
            f"Requested architecture: {requested_arch}; build host architecture: {host_arch}.",
        ],
    },
    {
        "phase": "phase-4-linux-native",
        "target": f"linux-{appimage_arch}-native-tarball",
        "label": f"Linux {appimage_arch} native tarball",
        "architecture": appimage_arch,
        "file": repo_path(tarball),
        "format": "tar.gz",
        "install_command": "Extract into a staging root or copy usr/bin/row into PATH.",
        "notes": [
            "Native Linux filesystem payload used by the package builders.",
            f"Requested architecture: {requested_arch}; build host architecture: {host_arch}.",
        ],
    },
]

manifest = [add_integrity(item) for item in manifest]

manifest_path = out_dir / f"remote-ops-workspace-v{version}-linux-{appimage_arch}-native-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
checksums = out_dir / f"remote-ops-workspace-v{version}-linux-{appimage_arch}-native-SHA256SUMS.txt"
write_checksums([deb, rpm, appimage, tarball, manifest_path], checksums)
for path in (deb, rpm, appimage, tarball, manifest_path, checksums):
    print(f"created {repo_path(path)}")
PY
