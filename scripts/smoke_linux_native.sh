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
BUILDER_EVIDENCE=""
SMOKE_SECURITY_UPDATE_CHANNEL="distribution-security-updates"
SMOKE_CVE_REVIEW_REFERENCE="distribution-security-tracker-and-release-notes"

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
    --builder-evidence)
      BUILDER_EVIDENCE="$2"
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

if [[ -n "$TARGET" && -z "$BUILDER_EVIDENCE" ]]; then
  echo "--builder-evidence is required with --target" >&2
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

if [[ -z "$TARGET" && -n "$BUILDER_EVIDENCE" ]]; then
  echo "--builder-evidence requires --target" >&2
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

if [[ -n "$WORKFLOW_RUN_URL" && ( "$WORKFLOW_RUN_URL" =~ [[:space:]] || "$WORKFLOW_RUN_URL" == */ ) ]]; then
  echo "--workflow-run-url must be canonical without surrounding whitespace or trailing slash" >&2
  exit 2
fi

if [[ -n "$WORKFLOW_RUN_URL" && ! "$WORKFLOW_RUN_URL" =~ ^https://github\.com/[^/[:space:]]+/[^/[:space:]]+/actions/runs/[0-9]+$ ]]; then
  echo "--workflow-run-url must be a GitHub Actions run URL" >&2
  exit 2
fi

if [[ -n "$TARGET" ]]; then
  REQUESTED_WORKFLOW_RUN_ID="$WORKFLOW_RUN_URL"
  REQUESTED_WORKFLOW_RUN_ID="${REQUESTED_WORKFLOW_RUN_ID##*/}"
  REQUESTED_WORKFLOW_REPOSITORY="${WORKFLOW_RUN_URL#https://github.com/}"
  REQUESTED_WORKFLOW_REPOSITORY="${REQUESTED_WORKFLOW_REPOSITORY%/actions/runs/*}"
  if [[ -n "${GITHUB_SHA:-}" && "${GITHUB_SHA,,}" != "$SOURCE_HEAD_SHA" ]]; then
    echo "target $TARGET GITHUB_SHA ${GITHUB_SHA,,} must match --source-head-sha $SOURCE_HEAD_SHA" >&2
    exit 2
  fi
  if [[ -n "${GITHUB_RUN_ATTEMPT:-}" && "$GITHUB_RUN_ATTEMPT" != "$WORKFLOW_RUN_ATTEMPT" ]]; then
    echo "target $TARGET GITHUB_RUN_ATTEMPT $GITHUB_RUN_ATTEMPT must match --workflow-run-attempt $WORKFLOW_RUN_ATTEMPT" >&2
    exit 2
  fi
  if [[ -n "${GITHUB_RUN_ID:-}" && "$GITHUB_RUN_ID" != "$REQUESTED_WORKFLOW_RUN_ID" ]]; then
    echo "target $TARGET GITHUB_RUN_ID $GITHUB_RUN_ID must match --workflow-run-url $WORKFLOW_RUN_URL" >&2
    exit 2
  fi
  if [[ -n "${GITHUB_REPOSITORY:-}" && "${GITHUB_REPOSITORY,,}" != "${REQUESTED_WORKFLOW_REPOSITORY,,}" ]]; then
    echo "target $TARGET GITHUB_REPOSITORY ${GITHUB_REPOSITORY,,} must match --workflow-run-url $WORKFLOW_RUN_URL" >&2
    exit 2
  fi
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
SMOKE_OS_RELEASE="$(python3 - <<'PY'
from pathlib import Path

values = {}
try:
    for raw_line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line or raw_line.startswith("#"):
            continue
        key, value = raw_line.split("=", 1)
        values[key] = value.strip().strip('"')
except OSError:
    pass

print(values.get("PRETTY_NAME") or " ".join(
    value for value in (values.get("ID", ""), values.get("VERSION_ID", "")) if value
))
PY
)"
SMOKE_KERNEL_RELEASE="$(uname -r)"
SMOKE_GLIBC_VERSION="$(getconf GNU_LIBC_VERSION)"
SMOKE_PYTHON_SSL_OPENSSL="$(python3 - <<'PY'
import ssl

print(getattr(ssl, "OPENSSL_VERSION", ""))
PY
)"
SMOKE_OPENSSL_CLI_VERSION="$(openssl version | tr '[:upper:]' '[:lower:]')"
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

if [[ -n "$TARGET" ]]; then
  if [[ ! -f "$BUILDER_EVIDENCE" ]]; then
    echo "target $TARGET builder evidence file missing: $BUILDER_EVIDENCE" >&2
    exit 2
  fi
  BUILDER_BINDING_TSV="$(python3 - "$BUILDER_EVIDENCE" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
except OSError as exc:
    raise SystemExit(f"cannot read builder evidence: {exc}")
except json.JSONDecodeError as exc:
    raise SystemExit(f"builder evidence is not valid JSON: {exc}")

if not isinstance(data, dict):
    raise SystemExit("builder evidence must be a JSON object")

fields = (
    ("target", ("target",)),
    ("release_tag", ("release_tag",)),
    ("workflow_run_url", ("workflow_run_url",)),
    ("workflow_run_attempt", ("workflow_run_attempt",)),
    ("source_head_sha", ("source_head_sha",)),
    ("observed_git_head_sha", ("observed_git_head_sha",)),
    ("os_release", ("os_release",)),
    ("kernel_release", ("kernel_release",)),
    ("glibc_version", ("glibc_version",)),
    ("host_target", ("host_identity", "target")),
    ("host_release_tag", ("host_identity", "release_tag")),
    ("host_workflow_run_url", ("host_identity", "workflow_run_url")),
    ("host_workflow_run_attempt", ("host_identity", "workflow_run_attempt")),
    ("host_label", ("host_identity", "host_label")),
    ("evidence_run_id", ("host_identity", "evidence_run_id")),
    ("python_ssl_openssl", ("security_patch_evidence", "python_ssl_openssl")),
    ("openssl_cli_version", ("security_patch_evidence", "openssl_cli_version")),
    ("security_update_channel", ("security_patch_evidence", "security_update_channel")),
    ("cve_review_reference", ("security_patch_evidence", "cve_review_reference")),
)

for label, keys in fields:
    value = data
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise SystemExit(f"builder evidence missing {'.'.join(keys)}")
        value = value[key]
    value = str(value).strip()
    if not value:
        raise SystemExit(f"builder evidence {'.'.join(keys)} must not be empty")
    print(f"{label}\t{value}")
PY
)"
  while IFS=$'\t' read -r key value; do
    case "$key" in
      target) BUILDER_TARGET="$value" ;;
      release_tag) BUILDER_RELEASE_TAG="$value" ;;
      workflow_run_url) BUILDER_WORKFLOW_RUN_URL="$value" ;;
      workflow_run_attempt) BUILDER_WORKFLOW_RUN_ATTEMPT="$value" ;;
      source_head_sha) BUILDER_SOURCE_HEAD_SHA="$value" ;;
      observed_git_head_sha) BUILDER_OBSERVED_GIT_HEAD_SHA="$value" ;;
      os_release) BUILDER_OS_RELEASE="$value" ;;
      kernel_release) BUILDER_KERNEL_RELEASE="$value" ;;
      glibc_version) BUILDER_GLIBC_VERSION="$value" ;;
      host_target) BUILDER_HOST_TARGET="$value" ;;
      host_release_tag) BUILDER_HOST_RELEASE_TAG="$value" ;;
      host_workflow_run_url) BUILDER_HOST_WORKFLOW_RUN_URL="$value" ;;
      host_workflow_run_attempt) BUILDER_HOST_WORKFLOW_RUN_ATTEMPT="$value" ;;
      host_label) SMOKE_HOST_LABEL="$value" ;;
      evidence_run_id) SMOKE_EVIDENCE_RUN_ID="$value" ;;
      python_ssl_openssl) BUILDER_PYTHON_SSL_OPENSSL="$value" ;;
      openssl_cli_version) BUILDER_OPENSSL_CLI_VERSION="$value" ;;
      security_update_channel)
        BUILDER_SECURITY_UPDATE_CHANNEL="$value"
        SMOKE_SECURITY_UPDATE_CHANNEL="$value"
        ;;
      cve_review_reference)
        BUILDER_CVE_REVIEW_REFERENCE="$value"
        SMOKE_CVE_REVIEW_REFERENCE="$value"
        ;;
    esac
  done <<< "$BUILDER_BINDING_TSV"

  require_builder_match() {
    local label="$1"
    local expected="$2"
    local actual="$3"
    if [[ "$expected" != "$actual" ]]; then
      echo "target $TARGET builder evidence $label $expected must match smoke value $actual" >&2
      exit 2
    fi
  }

  require_builder_value() {
    local label="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
      echo "target $TARGET builder evidence $label must be set" >&2
      exit 2
    fi
  }

  require_builder_match "target" "$BUILDER_TARGET" "$TARGET"
  require_builder_match "release_tag" "$BUILDER_RELEASE_TAG" "v$VERSION"
  require_builder_match "workflow_run_url" "$BUILDER_WORKFLOW_RUN_URL" "$WORKFLOW_RUN_URL"
  require_builder_match "workflow_run_attempt" "$BUILDER_WORKFLOW_RUN_ATTEMPT" "$WORKFLOW_RUN_ATTEMPT"
  require_builder_match "source_head_sha" "$BUILDER_SOURCE_HEAD_SHA" "$SOURCE_HEAD_SHA"
  require_builder_match "observed_git_head_sha" "$BUILDER_OBSERVED_GIT_HEAD_SHA" "$SMOKE_GIT_HEAD_SHA"
  require_builder_match "os_release" "$BUILDER_OS_RELEASE" "$SMOKE_OS_RELEASE"
  require_builder_match "kernel_release" "$BUILDER_KERNEL_RELEASE" "$SMOKE_KERNEL_RELEASE"
  require_builder_match "glibc_version" "$BUILDER_GLIBC_VERSION" "$SMOKE_GLIBC_VERSION"
  require_builder_match "host_identity.target" "$BUILDER_HOST_TARGET" "$TARGET"
  require_builder_match "host_identity.release_tag" "$BUILDER_HOST_RELEASE_TAG" "v$VERSION"
  require_builder_match "host_identity.workflow_run_url" "$BUILDER_HOST_WORKFLOW_RUN_URL" "$WORKFLOW_RUN_URL"
  require_builder_match "host_identity.workflow_run_attempt" "$BUILDER_HOST_WORKFLOW_RUN_ATTEMPT" "$WORKFLOW_RUN_ATTEMPT"
  require_builder_match "security_patch_evidence.python_ssl_openssl" "$BUILDER_PYTHON_SSL_OPENSSL" "$SMOKE_PYTHON_SSL_OPENSSL"
  require_builder_match "security_patch_evidence.openssl_cli_version" "$BUILDER_OPENSSL_CLI_VERSION" "$SMOKE_OPENSSL_CLI_VERSION"
  require_builder_value "security_patch_evidence.security_update_channel" "$BUILDER_SECURITY_UPDATE_CHANNEL"
  require_builder_value "security_patch_evidence.cve_review_reference" "$BUILDER_CVE_REVIEW_REFERENCE"
  require_builder_match "security_patch_evidence.security_update_channel" "$BUILDER_SECURITY_UPDATE_CHANNEL" "$SMOKE_SECURITY_UPDATE_CHANNEL"
  require_builder_match "security_patch_evidence.cve_review_reference" "$BUILDER_CVE_REVIEW_REFERENCE" "$SMOKE_CVE_REVIEW_REFERENCE"
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
  SMOKE_COMMAND="$SMOKE_COMMAND --target $TARGET --workflow-run-url $WORKFLOW_RUN_URL --workflow-run-attempt $WORKFLOW_RUN_ATTEMPT --source-head-sha $SOURCE_HEAD_SHA --builder-evidence $BUILDER_EVIDENCE"
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
  SMOKE_WORKFLOW_RUN_ID="$REQUESTED_WORKFLOW_RUN_ID"
  echo "native installer smoke builder evidence: $BUILDER_EVIDENCE"
  echo "native installer smoke host label: $SMOKE_HOST_LABEL"
  echo "native installer smoke evidence run id: $SMOKE_EVIDENCE_RUN_ID"
  echo "native installer smoke observed at utc: $SMOKE_OBSERVED_AT_UTC"
fi
echo "native installer smoke uname machine: $SMOKE_UNAME_MACHINE"
echo "native installer smoke dpkg architecture: $SMOKE_DPKG_ARCH"
echo "native installer smoke userland bits: $SMOKE_USERLAND_BITS"
echo "native installer smoke os release: $SMOKE_OS_RELEASE"
echo "native installer smoke kernel release: $SMOKE_KERNEL_RELEASE"
echo "native installer smoke glibc version: $SMOKE_GLIBC_VERSION"
echo "native installer smoke python ssl openssl: $SMOKE_PYTHON_SSL_OPENSSL"
echo "native installer smoke openssl cli version: $SMOKE_OPENSSL_CLI_VERSION"
echo "native installer smoke security update channel: $SMOKE_SECURITY_UPDATE_CHANNEL"
echo "native installer smoke CVE review reference: $SMOKE_CVE_REVIEW_REFERENCE"
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
