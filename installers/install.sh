#!/usr/bin/env sh
set -eu

PYTHON_BIN="${PYTHON_BIN:-python3}"
EXTRAS="${ROW_EXTRAS:-desktop,security}"

echo "Remote Ops Workspace installer"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ first." >&2
  exit 1
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10+ is required." >&2
  exit 1
}

"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[${EXTRAS}]"
row init --quiet
row doctor
row welcome

echo
echo "Activate this environment later with: . .venv/bin/activate"
