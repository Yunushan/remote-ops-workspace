#!/data/data/com.termux/files/usr/bin/sh
set -eu

echo "Remote Ops Workspace Termux installer"

pkg update
pkg install -y python git openssh termux-api

python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10+ is required." >&2
  exit 1
}

python -m pip install --upgrade pip
python -m pip install -e ".[security]"

row init --quiet
row doctor
row welcome
