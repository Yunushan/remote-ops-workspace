#!/usr/bin/env bash
set -euo pipefail
bash scripts/install_ci_ubuntu_packages.sh p7zip-full squashfs-tools rpm2cpio cpio msitools \
  build-essential cmake libboost-iostreams-dev libboost-filesystem-dev \
  libboost-date-time-dev libboost-system-dev libboost-program-options-dev liblzma-dev
# Upstream PR 210 adds the loader and payload formats used by Inno Setup 6.7.
# Pin its reviewed source bytes for compatible format inspection.
inspector_source="$RUNNER_TEMP/innoextract-source"
inspector_archive="$RUNNER_TEMP/innoextract-source.tar.gz"
curl --fail --location --retry 3 \
  https://codeload.github.com/dscho/innoextract/legacy.tar.gz/376a13e7c41cc5528b6088d0dd16ec1b323a8d37 \
  --output "$inspector_archive"
echo "16d7dd7bb68d6e4f8e3574d76ebdd9d153b83aa7941b4887615007349c8d0ede  $inspector_archive" | sha256sum --check --strict
mkdir "$inspector_source"
tar --extract --gzip --file "$inspector_archive" --directory "$inspector_source" --strip-components=1
cmake -S "$inspector_source" -B "$inspector_source/build" -DCMAKE_BUILD_TYPE=Release -DUSE_LTO=OFF
cmake --build "$inspector_source/build" --parallel 2
sudo install -m 755 "$inspector_source/build/innoextract" /usr/local/bin/innoextract
innoextract --version
