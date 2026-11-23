#!/usr/bin/env bash
set +x
set -euo pipefail

if [[ $# -ne 1 || ( "$1" != "--rehearse" && "$1" != "--build" ) ]]; then
  echo "usage: bash scripts/with_macos_release_signing.sh --rehearse|--build" >&2
  exit 2
fi
mode="$1"
for name in ROW_MACOS_CERTIFICATE_BASE64 ROW_MACOS_CERTIFICATE_PASSWORD ROW_MACOS_SIGN_IDENTITY \
  ROW_MACOS_INSTALLER_SIGN_IDENTITY ROW_MACOS_NOTARY_KEY_BASE64 ROW_MACOS_NOTARY_KEY_ID ROW_MACOS_NOTARY_ISSUER; do
  if [[ -z "${!name:-}" ]]; then
    echo "Protected release environment is missing $name" >&2
    exit 1
  fi
done

signing_dir="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/row-macos-signing.XXXXXXXX")"
keychain="$signing_dir/release.keychain-db"
certificate="$signing_dir/release.p12"
notary_key="$signing_dir/AuthKey.p8"
profile="remote-ops-notary"
cleanup_signing_material() {
  local status=$?
  trap - EXIT
  if [[ -e "$keychain" ]]; then
    security delete-keychain "$keychain" || status=1
  fi
  # This directory was made for this invocation by mktemp.
  rm -rf -- "$signing_dir" || status=1
  if [[ "$status" == 0 && "$mode" == "--rehearse" ]]; then
    echo "macOS Developer ID signing and notarization credential rehearsal passed."
  fi
  exit "$status"
}
trap cleanup_signing_material EXIT

(
  umask 077
  printf '%s' "$ROW_MACOS_CERTIFICATE_BASE64" | LC_ALL=C tr -d '[:space:]' | base64 --decode > "$certificate"
  printf '%s' "$ROW_MACOS_NOTARY_KEY_BASE64" | LC_ALL=C tr -d '[:space:]' | base64 --decode > "$notary_key"
)
unset ROW_MACOS_CERTIFICATE_BASE64 ROW_MACOS_NOTARY_KEY_BASE64
security create-keychain -p "$ROW_MACOS_CERTIFICATE_PASSWORD" "$keychain"
security set-keychain-settings -lut 21600 "$keychain"
security unlock-keychain -p "$ROW_MACOS_CERTIFICATE_PASSWORD" "$keychain"
security import "$certificate" -k "$keychain" -P "$ROW_MACOS_CERTIFICATE_PASSWORD" -T /usr/bin/codesign -T /usr/bin/productsign
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$ROW_MACOS_CERTIFICATE_PASSWORD" "$keychain"
unset ROW_MACOS_CERTIFICATE_PASSWORD
xcrun notarytool store-credentials "$profile" --keychain "$keychain" \
  --key "$notary_key" --key-id "$ROW_MACOS_NOTARY_KEY_ID" --issuer "$ROW_MACOS_NOTARY_ISSUER"
rm -f -- "$certificate" "$notary_key"
unset ROW_MACOS_NOTARY_KEY_ID ROW_MACOS_NOTARY_ISSUER

if [[ "$mode" == "--build" ]]; then
  ROW_REQUIRE_RELEASE_SIGNING=1 ROW_MACOS_SIGNING_KEYCHAIN="$keychain" ROW_MACOS_NOTARY_PROFILE="$profile" \
    bash "$(dirname "${BASH_SOURCE[0]}")/make_macos_native.sh"
  exit 0
fi

# Read the account through the exact profile that the release will use.
xcrun notarytool history --keychain "$keychain" --keychain-profile "$profile" >/dev/null
mkdir "$signing_dir/payload"
probe="$signing_dir/payload/row-signing-rehearsal"
printf 'int main(void) { return 0; }\n' | xcrun clang -x c - -o "$probe"
codesign --force --options runtime --timestamp --sign "$ROW_MACOS_SIGN_IDENTITY" --keychain "$keychain" "$probe"
codesign --verify --strict --verbose=2 "$probe"
pkgbuild --root "$signing_dir/payload" --identifier io.github.remoteopsworkspace.signing-rehearsal \
  --version 1.0 --install-location /private/tmp "$signing_dir/unsigned.pkg"
productsign --sign "$ROW_MACOS_INSTALLER_SIGN_IDENTITY" --keychain "$keychain" \
  "$signing_dir/unsigned.pkg" "$signing_dir/signed.pkg"
pkgutil --check-signature "$signing_dir/signed.pkg"
