#!/usr/bin/env sh
# Print the operator's brief into a session's context at startup.
#
# `docs/OPERATOR.md` is an ordinary file: nothing loads it on its own, and an
# operator that has to remember to read it will eventually not. This runs from
# the SessionStart hook so it arrives without anyone deciding to fetch it.
#
# It stays quiet inside GitHub Actions, where the session is a fleet run and
# the operator's responsibilities are not its business.
set -eu

if [ -n "${GITHUB_ACTIONS:-}" ] || [ -n "${FLEET_RUN:-}" ]; then
  exit 0
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
brief="$root/docs/OPERATOR.md"

[ -f "$brief" ] || exit 0

echo "The operator's brief follows, from docs/OPERATOR.md. It is addressed to"
echo "the interactive session that runs the fleet. If you are a fleet agent or"
echo "a scheduled fleet run, ignore it: your brief is your agent definition."
echo
cat "$brief"
