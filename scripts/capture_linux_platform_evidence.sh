#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" != 6 ]]; then
  printf 'Usage: bash scripts/capture_linux_platform_evidence.sh TARGET TAG ASSET_BASE_URL WORKFLOW_RUN_URL SOURCE_SHA RUN_ATTEMPT\n' >&2
  exit 2
fi

readonly TARGET="$1" RELEASE_TAG="$2" RELEASE_ASSET_BASE_URL="$3" WORKFLOW_RUN_URL="$4"
readonly SOURCE_HEAD_SHA="$5" SOURCE_RUN_ATTEMPT="$6"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 scripts/check_extended_platform_dispatch_inputs.py --target "$TARGET" \
  --release-tag "$RELEASE_TAG" --release-asset-base-url "$RELEASE_ASSET_BASE_URL" \
  --workflow-run-url "$WORKFLOW_RUN_URL" --workflow-ref-name "$RELEASE_TAG" \
  --source-head-sha "$SOURCE_HEAD_SHA" --source-run-attempt "$SOURCE_RUN_ATTEMPT"
if [[ "$(git rev-parse HEAD)" != "$SOURCE_HEAD_SHA" ||
      "$(git rev-parse --verify "refs/tags/${RELEASE_TAG}^{commit}")" != "$SOURCE_HEAD_SHA" ]]; then
  echo 'Native checkout and release tag must resolve to the collector run source SHA' >&2
  exit 1
fi

readonly EVIDENCE_DIR="platform-evidence-staging/$TARGET/$RELEASE_TAG"
if [[ -e "$EVIDENCE_DIR" || -L "$EVIDENCE_DIR" || -e .venv-native || -L .venv-native ]]; then
  echo 'Use a fresh native checkout for this evidence capture' >&2
  exit 1
fi

python3 scripts/check_protected_linux_build_inputs.py --target "$TARGET"
repository_path="${WORKFLOW_RUN_URL#https://github.com/}"
export GITHUB_WORKFLOW_REF="${repository_path%/actions/runs/*}/.github/workflows/extended-platform-evidence.yml@refs/tags/$RELEASE_TAG"
export GITHUB_WORKFLOW_SHA="$SOURCE_HEAD_SHA"
python3 scripts/check_extended_platform_builder.py --target "$TARGET" \
  --release-tag "$RELEASE_TAG" --workflow-run-url "$WORKFLOW_RUN_URL" \
  --workflow-run-attempt "$SOURCE_RUN_ATTEMPT" --source-head-sha "$SOURCE_HEAD_SHA" \
  --out "$EVIDENCE_DIR/builder-identity-$TARGET.json"

export RELEASE_TAG SOURCE_DATE_EPOCH=1704067200 PYTHONHASHSEED=0
export PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_VIRTUALENV=1 PIP_DISABLE_PIP_VERSION_CHECK=1
python3 -m venv .venv-native
# shellcheck disable=SC1091
. .venv-native/bin/activate
case "$TARGET" in
  linux-i386)
    readonly ARCH=i386 RPM_ARCH=i686 APPIMAGE_ARCH=i686
    export CARGO_NET_OFFLINE=true MATURIN_NO_INSTALL_RUST=true MATURIN_PEP517_ARGS="--locked --offline"
    CARGO_HOME="$(mktemp -d "${TMPDIR:-/tmp}/row-protected-linux-cargo.XXXXXXXX")"
    export CARGO_HOME
    trap 'rm -rf -- "$CARGO_HOME"' EXIT
    python3 scripts/prepare_protected_linux_cargo.py
    install -m 0700 scripts/protected_linux_cargo.sh "$CARGO_HOME/locked-cargo"
    export CARGO="$CARGO_HOME/locked-cargo"
    python -m pip install --require-hashes --force-reinstall --only-binary=:all: --requirement requirements-locks/protected-linux/linux-i386-bootstrap.txt
    python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=cffi --requirement requirements-locks/protected-linux/linux-32bit-cffi.txt
    python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=bcrypt,cffi,cryptography,pyftpdlib --requirement requirements-locks/protected-linux/linux-i386.txt
    ;;
  linux-armhf)
    readonly ARCH=armhf RPM_ARCH=armv7hl APPIMAGE_ARCH=armhf
    python -m pip install --require-hashes --force-reinstall --only-binary=:all: --requirement requirements-locks/protected-linux/linux-armhf-bootstrap.txt
    python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=cffi --requirement requirements-locks/protected-linux/linux-32bit-cffi.txt
    python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=cffi,pyftpdlib,pyinstaller --requirement requirements-locks/protected-linux/linux-armhf.txt
    ;;
  *)
    exit 2
    ;;
esac
python -m pip install --no-deps --no-build-isolation ".[security,package,servers]"
python -m pip check
python -X utf8 -m pip inspect --local > "$EVIDENCE_DIR/candidate-pip-inspect.json"
python scripts/check_release_dependency_locks.py --runtime-report "$EVIDENCE_DIR/candidate-pip-inspect.json" \
  --lock "requirements-locks/protected-linux/$TARGET.txt"
TARGET_ARCH="$ARCH" PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh

bash scripts/smoke_linux_native.sh --arch "$ARCH" --dist native-dist/linux --target "$TARGET" \
  --workflow-run-url "$WORKFLOW_RUN_URL" --workflow-run-attempt "$SOURCE_RUN_ATTEMPT" \
  --source-head-sha "$SOURCE_HEAD_SHA" --builder-evidence "$EVIDENCE_DIR/builder-identity-$TARGET.json" \
  2>&1 | tee "$EVIDENCE_DIR/native-smoke-$TARGET.log"

mkdir -- "$EVIDENCE_DIR/artifacts"
cp -- "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$ARCH.deb" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$RPM_ARCH.rpm" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$APPIMAGE_ARCH.AppImage" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$APPIMAGE_ARCH-native.tar.gz" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$APPIMAGE_ARCH-native-manifest.json" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-$APPIMAGE_ARCH-native-SHA256SUMS.txt" \
  "$EVIDENCE_DIR/artifacts/"
python scripts/check_platform_promotion_artifacts.py --target "$TARGET" \
  --assets-dir "$EVIDENCE_DIR/artifacts" --tag "$RELEASE_TAG" --strict
printf 'Transfer the completed directory %s to the running collector.\n' "$EVIDENCE_DIR"
