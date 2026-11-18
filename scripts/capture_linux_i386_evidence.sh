#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "$#" != 5 ]]; then
  printf 'Usage: bash scripts/capture_linux_i386_evidence.sh TAG ASSET_BASE_URL WORKFLOW_RUN_URL SOURCE_SHA RUN_ATTEMPT\n' >&2
  exit 2
fi

readonly RELEASE_TAG="$1" RELEASE_ASSET_BASE_URL="$2" WORKFLOW_RUN_URL="$3"
readonly SOURCE_HEAD_SHA="$4" SOURCE_RUN_ATTEMPT="$5"
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
python3 scripts/check_extended_platform_dispatch_inputs.py --target linux-i386 \
  --release-tag "$RELEASE_TAG" --release-asset-base-url "$RELEASE_ASSET_BASE_URL" \
  --workflow-run-url "$WORKFLOW_RUN_URL" --workflow-ref-name "$RELEASE_TAG" \
  --source-head-sha "$SOURCE_HEAD_SHA" --source-run-attempt "$SOURCE_RUN_ATTEMPT"
if [[ "$(git rev-parse HEAD)" != "$SOURCE_HEAD_SHA" ||
      "$(git rev-parse --verify "refs/tags/${RELEASE_TAG}^{commit}")" != "$SOURCE_HEAD_SHA" ]]; then
  echo 'Native checkout and release tag must resolve to the collector run source SHA' >&2
  exit 1
fi

readonly EVIDENCE_DIR="platform-evidence-staging/linux-i386/$RELEASE_TAG"
if [[ -e "$EVIDENCE_DIR" || -L "$EVIDENCE_DIR" || -e .venv-native || -L .venv-native ]]; then
  echo 'Use a fresh native checkout for this evidence capture' >&2
  exit 1
fi

repository_path="${WORKFLOW_RUN_URL#https://github.com/}"
export GITHUB_WORKFLOW_REF="${repository_path%/actions/runs/*}/.github/workflows/extended-platform-evidence.yml@refs/tags/$RELEASE_TAG"
export GITHUB_WORKFLOW_SHA="$SOURCE_HEAD_SHA"
python3 scripts/check_extended_platform_builder.py --target linux-i386 \
  --release-tag "$RELEASE_TAG" --workflow-run-url "$WORKFLOW_RUN_URL" \
  --workflow-run-attempt "$SOURCE_RUN_ATTEMPT" --source-head-sha "$SOURCE_HEAD_SHA" \
  --out "$EVIDENCE_DIR/builder-identity-linux-i386.json"

export RELEASE_TAG SOURCE_DATE_EPOCH=1704067200 PYTHONHASHSEED=0
export PIP_CONFIG_FILE=/dev/null PIP_REQUIRE_VIRTUALENV=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export CARGO_NET_OFFLINE=true MATURIN_NO_INSTALL_RUST=true MATURIN_PEP517_ARGS="--locked --offline"
python3 scripts/check_protected_linux_build_inputs.py --target linux-i386
CARGO_HOME="$(mktemp -d "${TMPDIR:-/tmp}/row-protected-linux-cargo.XXXXXXXX")"
export CARGO_HOME
trap 'rm -rf -- "$CARGO_HOME"' EXIT
python3 scripts/prepare_protected_linux_cargo.py
install -m 0700 scripts/protected_linux_cargo.sh "$CARGO_HOME/locked-cargo"
export CARGO="$CARGO_HOME/locked-cargo"
python3 -m venv .venv-native
# shellcheck disable=SC1091
. .venv-native/bin/activate
python -m pip install --require-hashes --force-reinstall --only-binary=:all: --requirement requirements-locks/protected-linux/linux-i386-bootstrap.txt
python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=cffi --requirement requirements-locks/protected-linux/linux-32bit-cffi.txt
python -m pip install --require-hashes --no-cache-dir --no-build-isolation --only-binary=:all: --no-binary=bcrypt,cffi,cryptography,pyftpdlib --requirement requirements-locks/protected-linux/linux-i386.txt
python -m pip install --no-deps --no-build-isolation ".[security,package,servers]"
python -m pip check
python -X utf8 -m pip inspect --local > "$EVIDENCE_DIR/candidate-pip-inspect.json"
python scripts/check_release_dependency_locks.py --runtime-report "$EVIDENCE_DIR/candidate-pip-inspect.json" \
  --lock requirements-locks/protected-linux/linux-i386.txt
TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh

bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386 \
  --workflow-run-url "$WORKFLOW_RUN_URL" --workflow-run-attempt "$SOURCE_RUN_ATTEMPT" \
  --source-head-sha "$SOURCE_HEAD_SHA" --builder-evidence "$EVIDENCE_DIR/builder-identity-linux-i386.json" \
  2>&1 | tee "$EVIDENCE_DIR/native-smoke-linux-i386.log"

mkdir -- "$EVIDENCE_DIR/artifacts"
cp -- "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i386.deb" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i686.rpm" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i686.AppImage" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i686-native.tar.gz" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i686-native-manifest.json" \
  "native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-i686-native-SHA256SUMS.txt" \
  "$EVIDENCE_DIR/artifacts/"
python scripts/check_platform_promotion_artifacts.py --target linux-i386 \
  --assets-dir "$EVIDENCE_DIR/artifacts" --tag "$RELEASE_TAG" --strict
printf 'Transfer the completed directory %s to the running collector.\n' "$EVIDENCE_DIR"
