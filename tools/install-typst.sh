#!/usr/bin/env sh
# Install the Typst version pinned in `.typst-version` into `.tools/typst/`.
#
# The same script runs locally and in CI, so both build with the exact same
# compiler: Typst's HTML export is still experimental, and an unpinned upgrade
# would change the site's markup underneath the pipeline.
#
#   tools/install-typst.sh            # install the pinned version
#   TYPST_VERSION=0.14.1 tools/install-typst.sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=${TYPST_VERSION:-$(tr -d ' \n' < "$root/.typst-version")}
destination="$root/.tools/typst"
binary="$destination/typst"

if [ -x "$binary" ] && "$binary" --version 2>/dev/null | grep -q "typst $version"; then
  echo "typst $version already installed at .tools/typst/typst"
  exit 0
fi

case "$(uname -s)" in
  Linux) os=unknown-linux-musl ;;
  Darwin) os=apple-darwin ;;
  *) echo "unsupported OS: $(uname -s). Install typst $version manually and set TYPST." >&2; exit 1 ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) arch=x86_64 ;;
  arm64 | aarch64) arch=aarch64 ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

target="$arch-$os"
archive="typst-$target.tar.xz"
url="https://github.com/typst/typst/releases/download/v$version/$archive"

echo "downloading typst $version for $target"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if ! curl --fail --location --silent --show-error --output "$work/$archive" "$url"; then
  echo "could not download $url" >&2
  echo "check that .typst-version names a released version." >&2
  exit 1
fi

tar -xJf "$work/$archive" -C "$work"
mkdir -p "$destination"
cp "$work/typst-$target/typst" "$binary"
chmod +x "$binary"

installed=$("$binary" --version)
echo "installed $installed -> .tools/typst/typst"
case "$installed" in
  "typst $version"*) ;;
  *) echo "warning: expected typst $version but got '$installed'" >&2 ;;
esac
