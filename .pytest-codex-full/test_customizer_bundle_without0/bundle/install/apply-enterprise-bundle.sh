#!/usr/bin/env sh
set -eu
bundle_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
target="${ROW_HOME:-${HOME}/.config/remote-ops-workspace}"
mkdir -p "$target"
cp "$bundle_root/config/settings.json" "$target/settings.json"
cp "$bundle_root/config/profiles.json" "$target/profiles.json"
cp "$bundle_root/config/policy.json" "$target/policy.json"
cp "$bundle_root/welcome.txt" "$target/welcome.txt"
printf 'Applied Remote Ops Workspace enterprise bundle to %s
' "$target"
