#!/usr/bin/env sh
# Install the pinned GitHub CLI into `.tools/gh/`.
#
# The fleet talks to GitHub through `gh`: scheduled sessions are fired without
# MCP tools, so `gh` is the only GitHub surface they have. It is not present
# in a fresh container, which is why this runs from the SessionStart hook
# alongside the Typst install.
#
#   tools/install-gh.sh
#   GH_VERSION=2.63.2 tools/install-gh.sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
version=${GH_VERSION:-$(tr -d ' \n' < "$root/.gh-version")}
destination="$root/.tools/gh"
binary="$destination/gh"

if [ -x "$binary" ] && "$binary" --version 2>/dev/null | grep -q "gh version $version"; then
  echo "gh $version already installed at .tools/gh/gh"
  exit 0
fi

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=macOS ;;
  *) echo "unsupported OS: $(uname -s); install gh $version manually" >&2; exit 1 ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

archive="gh_${version}_${os}_${arch}.tar.gz"
url="https://github.com/cli/cli/releases/download/v${version}/${archive}"

echo "downloading gh $version for ${os}_${arch}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if ! curl --fail --location --silent --show-error --output "$work/$archive" "$url"; then
  echo "could not download $url" >&2
  exit 1
fi

tar -xzf "$work/$archive" -C "$work"
mkdir -p "$destination"
cp "$work/gh_${version}_${os}_${arch}/bin/gh" "$binary"
chmod +x "$binary"
echo "installed $("$binary" --version | head -1) -> .tools/gh/gh"

# Put it on PATH where that is possible, so scripts and skills can say `gh`
# rather than a path. Best effort: a read-only /usr/local/bin is not an error.
if [ -w /usr/local/bin ] 2>/dev/null; then
  ln -sf "$binary" /usr/local/bin/gh 2>/dev/null && echo "linked /usr/local/bin/gh"
fi
