#!/usr/bin/env bash
set -Eeuo pipefail

workdir="${1:?fixture work directory required}"
image="${2:?fixture image tag required}"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
image_context="$workdir/image"
mkdir -p "$image_context/wheelhouse"
cp "$root"/requirements-locks/source-linux-x86_64{,-bootstrap}.txt "$image_context/"
python -m venv "$workdir/download"
downloader="$workdir/download/bin/python"
"$downloader" -m pip install --require-hashes --only-binary=:all: \
  -r "$image_context/source-linux-x86_64-bootstrap.txt"
"$downloader" -m pip download --require-hashes --no-deps --no-build-isolation \
  --only-binary=:all: --no-binary=pyftpdlib --dest "$image_context/wheelhouse" \
  -r "$image_context/source-linux-x86_64.txt"
docker build --platform linux/amd64 --tag "$image" \
  -f "$root/docker/Dockerfile.editor-release-evidence" "$image_context"
