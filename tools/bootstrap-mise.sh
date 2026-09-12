#!/usr/bin/env sh
set -eu

# Put the pinned toolchain on this machine, for the one kind of machine that
# cannot use an action to do it.
#
# CI does not call this. Every workflow sets mise up with `jdx/mise-action`,
# which caches and is the right tool on a runner. This exists for a Claude
# Code session, which has no Actions runner, so `uses:` is not available to
# it at all. `.claude/settings.json` calls this at SessionStart.
#
# The `command -v mise` guard is load-bearing, not defensive tidiness.
# `claude.yml`, `fleet.yml`, `fleet-review.yml` and `fleet-respond.yml` each
# run `claude-code-action` on a runner that `mise-action` has already
# provisioned, and the Claude Code session inside that action fires this same
# SessionStart hook. Without the guard those four jobs would install mise a
# second time, over the one CI just set up. Do not remove it.
#
# Why the vendor's script rather than a release download: from inside a
# session's proxy `github.com/jdx/mise/releases` answers 403 and
# `https://mise.run` answers 200, so this is the route that exists. Why the
# version is here and not in `mise.toml`'s `[tools]`, which is where every
# other pin lives: mise can manage itself from that table, and it would then
# install a second mise under the first on every CI run -- the duplicate this
# script is written to avoid. Bump it with the others; `maintenance.yml` does
# not watch it.
MISE_VERSION="${MISE_VERSION:-v2026.9.5}"

if command -v mise > /dev/null 2>&1; then
  mise install
  exit 0
fi

curl -fsSL https://mise.run | MISE_VERSION="$MISE_VERSION" sh

# The installer writes to ~/.local/bin, which is not necessarily on the PATH
# of whatever invoked this -- a hook's shell is not a login shell.
for candidate in mise "$HOME/.local/bin/mise" "$HOME/.mise/bin/mise"; do
  if command -v "$candidate" > /dev/null 2>&1; then
    "$candidate" install
    exit 0
  fi
done

echo "mise installed but is not on PATH; add \$HOME/.local/bin to it" >&2
exit 1
