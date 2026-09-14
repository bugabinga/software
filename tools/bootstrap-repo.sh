#!/usr/bin/env sh
# The one repository setting no workflow and no agent can set for itself.
#
# It used to do three things. The other two -- letting Actions open pull
# requests, and the merge-hygiene fields -- are `repo.toml`'s now, applied by
# `.github/workflows/settings.yml`, and the copy here had drifted: it sent
# `can_approve_pull_requests`, which is not the API's key for that field.
# That is the argument for the file in one line.
#
# Creating a Pages site is privileged, the workflow token does not have it,
# and the Pages API is not reachable from the author's Claude sessions, so
# this remains the one command a human has to run -- once, from anywhere
# holding a token with administration rights.
#
#   tools/bootstrap-repo.sh
#   GH_TOKEN=<a token with repo admin> tools/bootstrap-repo.sh
#
# It is idempotent: run it again any time to confirm.
set -eu

repo=${REPO:-bugabinga/software}
gh=${GH:-gh}

if ! command -v "$gh" >/dev/null 2>&1; then
  echo "gh is not installed. tools/bootstrap-mise.sh installs the pinned" >&2
  echo "toolchain, or set GH=/path/to/gh." >&2
  exit 1
fi

printf 'GitHub Pages on %s, building from Actions ... ' "$repo"
if "$gh" api "repos/$repo/pages" >/dev/null 2>&1; then
  echo "already enabled"
else
  if "$gh" api -X POST "repos/$repo/pages" -f build_type=workflow >/dev/null 2>&1; then
    echo "enabled"
  else
    echo "FAILED"
    echo "   The token needs administration rights on the repository." >&2
    echo "   Equivalent in the UI: Settings, Pages, Source: GitHub Actions." >&2
    exit 1
  fi
fi

echo
echo "Everything else is repo.toml's. Push to main and the book publishes at"
echo "  https://bugabinga.github.io/software/"
