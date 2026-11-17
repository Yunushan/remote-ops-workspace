#!/usr/bin/env bash
set -euo pipefail

case "${1:-}" in
  build|metadata|rustc)
    command_name="$1"
    shift
    exec cargo "$command_name" --locked --offline "$@"
    ;;
  *)
    exec cargo "$@"
    ;;
esac
