#!/data/data/com.termux/files/usr/bin/sh
set -eu

pkg update
pkg install -y python git openssh termux-api

python -m pip install --upgrade pip
python -m pip install -e ".[security]"

row init
row doctor
