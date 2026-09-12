#!/usr/bin/env sh
# One-time repository setup that no workflow and no agent can do for itself.
#
# Three things need a token with administration rights on the repository. The
# workflow token does not have them, and the GitHub API paths involved are not
# reachable from the author's Claude sessions, so this is the one command that
# has to be run by a human -- once, from anywhere holding such a token.
#
#   tools/bootstrap-repo.sh
#   GH_TOKEN=<a token with repo admin> tools/bootstrap-repo.sh
#
# It is idempotent: run it again any time to confirm the settings are right.
set -eu

repo=${REPO:-bugabinga/software}
gh=${GH:-gh}

if ! command -v "$gh" >/dev/null 2>&1; then
  echo "gh is not installed. tools/bootstrap-mise.sh installs the pinned" >&2
  echo "toolchain, or set GH=/path/to/gh." >&2
  exit 1
fi

echo "Setting up $repo"
echo

# --- 1. Pages ------------------------------------------------------------- #
# Publishing needs a Pages site that builds from Actions. Creating it is
# privileged; deploying to it afterwards is not, which is why every push to
# main can publish unattended once this exists.
printf '1. GitHub Pages, building from Actions ... '
if "$gh" api "repos/$repo/pages" >/dev/null 2>&1; then
  echo "already enabled"
else
  if "$gh" api -X POST "repos/$repo/pages" -f build_type=workflow >/dev/null 2>&1; then
    echo "enabled"
  else
    echo "FAILED"
    echo "   The token needs administration rights on the repository." >&2
    echo "   Equivalent in the UI: Settings, Pages, Source: GitHub Actions." >&2
  fi
fi

# --- 2. Let workflows open pull requests ---------------------------------- #
# The fleet pushes branches and lets agent-branches.yml open the pull request,
# because an unattended session cannot reliably call the pull-request API.
# That workflow needs this permission, which is off by default.
printf '2. Allow Actions to open pull requests ... '
current=$("$gh" api "repos/$repo/actions/permissions/workflow" \
  --jq '.default_workflow_permissions' 2>/dev/null || echo "")
if [ -z "$current" ]; then
  echo "could not read the current setting"
else
  # The existing default is passed back deliberately: every workflow here
  # declares the permissions it needs, so widening the default is not wanted.
  if "$gh" api -X PUT "repos/$repo/actions/permissions/workflow" \
    -f "default_workflow_permissions=$current" \
    -F can_approve_pull_requests=true >/dev/null 2>&1; then
    echo "done (default permissions left at '$current')"
  else
    echo "FAILED"
    echo "   Equivalent in the UI: Settings, Actions, General, Workflow" >&2
    echo "   permissions, tick 'Allow GitHub Actions to create and approve" >&2
    echo "   pull requests'." >&2
  fi
fi

# --- 3. Merge hygiene ------------------------------------------------------ #
# Not required by anything, but it keeps the branch list and the history of a
# repository full of small automated pull requests readable.
printf '3. Merge hygiene (squash titles, delete merged branches) ... '
if "$gh" api -X PATCH "repos/$repo" \
  -F delete_branch_on_merge=true \
  -F allow_update_branch=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=PR_BODY >/dev/null 2>&1; then
  echo "done"
else
  echo "FAILED (harmless; everything works without it)"
fi

echo
echo "Done. Push to main and the book publishes at"
echo "  https://bugabinga.github.io/software/"
