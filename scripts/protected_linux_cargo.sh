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
    if [[ "$offline" == false ]]; then
      set -- --offline "$@"
    fi
    if [[ "$locked" == false ]]; then
      set -- --locked "$@"
    fi
    exec cargo "$command_name" "$@"
    ;;
  *)
    exec cargo "$@"
    ;;
esac
