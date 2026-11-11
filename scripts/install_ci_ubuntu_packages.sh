#!/usr/bin/env bash
set -euo pipefail

install_options=()
if [[ "${1:-}" == --no-install-recommends ]]; then
  install_options+=(--no-install-recommends)
  shift
fi
missing_packages=()
for package in "$@"; do
  if [[ "$(dpkg-query -W -f='${db:Status-Status}' -- "$package" 2>/dev/null)" != installed ]]; then
    missing_packages+=("$package")
  fi
done
if (( ${#missing_packages[@]} == 0 )); then
  echo "All required Ubuntu CI packages are already installed."
  exit 0
fi

source /etc/os-release
architecture="$(dpkg --print-architecture)"
if [[ "${ID:-}" != ubuntu || ! "${VERSION_CODENAME:-}" =~ ^[a-z]+$ ]]; then
  echo "Ubuntu CI package setup requires an Ubuntu runner with a release codename." >&2
  exit 1
fi

case "$VERSION_CODENAME:$architecture" in
  *:amd64|resolute:arm64)
    archive=https://archive.ubuntu.com/ubuntu
    security=https://security.ubuntu.com/ubuntu
    fallback=https://mirrors.mit.edu/ubuntu
    ;;
  noble:arm64)
    archive=https://ftp.ports.ubuntu.com/ubuntu-ports
    security="$archive"
    fallback=https://mirrors.mit.edu/ubuntu-ports
    ;;
  *)
    echo "Unsupported Ubuntu CI package archive for $VERSION_CODENAME/$architecture." >&2
    exit 1
    ;;
esac

probe_options=(--head --fail --silent --show-error --connect-timeout 5 --max-time 8)
if ! curl "${probe_options[@]}" "$archive/dists/$VERSION_CODENAME/InRelease" >/dev/null ||
   ! curl "${probe_options[@]}" "$security/dists/$VERSION_CODENAME-security/InRelease" >/dev/null; then
  echo "Canonical archive unavailable. Using the Ubuntu archive mirror at $fallback."
  archive="$fallback"
  security="$fallback"
fi

# Use fresh indexes and verify the archive with the runner's Ubuntu signing key.
apt_dir="$(mktemp -d /tmp/row-ci-apt.XXXXXXXX)"
trap 'sudo -n rm -rf -- "$apt_dir"' EXIT
chmod 755 "$apt_dir"
cat > "$apt_dir/ubuntu.sources" <<EOF
Types: deb
URIs: $archive
Suites: $VERSION_CODENAME $VERSION_CODENAME-updates
Components: main restricted universe multiverse
Architectures: $architecture
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: $security
Suites: $VERSION_CODENAME-security
Components: main restricted universe multiverse
Architectures: $architecture
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

mkdir "$apt_dir/lists"
apt_options=(
  -o "Dir::Etc::sourcelist=$apt_dir/ubuntu.sources"
  -o Dir::Etc::sourceparts=-
  -o "Dir::State::lists=$apt_dir/lists"
  -o Acquire::Retries=2
  -o Acquire::https::Timeout=15
)
sudo -n apt-get "${apt_options[@]}" update --error-on=any
sudo -n apt-get "${apt_options[@]}" install -y "${install_options[@]}" "${missing_packages[@]}"
