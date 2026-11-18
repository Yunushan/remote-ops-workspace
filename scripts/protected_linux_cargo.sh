#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  build|metadata|rustc)
    command_name="$1"
    shift
    locked=false
    offline=false
    for arg in "$@"; do
      case "$arg" in
        --locked) locked=true ;;
        --offline) offline=true ;;
        --frozen) locked=true; offline=true ;;
        --) break ;;
      esac
    done
    flags=()
    if [[ "$locked" == false ]]; then
      flags+=(--locked)
    fi
    if [[ "$offline" == false ]]; then
      flags+=(--offline)
    fi
    exec cargo "$command_name" "${flags[@]}" "$@"
    ;;
  *)
    exec cargo "$@"
    ;;
esac
