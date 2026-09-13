#!/usr/bin/env python3
"""Say whether the GitHub App may do what the fleet needs.

Reads two documents the caller has already fetched -- `GET /app` and
`GET /repos/{owner}/{repo}/installation` -- and reports each permission the
fleet depends on against what was actually granted. An app can declare a
permission and be installed without it, so the installation is the one that
decides.

Exits non-zero when something the fleet cannot work without is missing. A
permission that costs one capability warns instead: the fleet still runs, one
thing it does stops working, and that is worth saying rather than failing.

Lives here rather than inside the composite action that calls it because a
Python program indented inside a YAML block scalar inside a shell heredoc is
three layers of quoting deep, and the fleet's own reviewer read it as broken.
It was not, but being unreadable enough to look broken is its own defect: here
it is syntax-checked by `mise run check` and can be run against a fixture.

Usage:
    tools/check_app.py --app app.json --installation installation.json \
        --where "the Bot environment" --repository owner/name
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

# One boundary, and everything else is a statement rather than a grade.
#
# The app is the author's own, installed on their own repositories, granted
# every **repository** permission on purpose: they cannot predict what the
# fleet will need, and an earlier version of this file made the grant a
# per-feature decision, so every improvement meant another trip to a settings
# page. What replaced the old ceiling is `repo.toml`: the rules the app may
# change are declared in a file, changed by a pull request, and checked by
# `tools/repo_state.py`. The gate moved from the grant to the diff.
#
# So ESSENTIAL still fails when missing -- the fleet cannot work without it.
# FORBIDDEN is now only what reaches **beyond this repository**, because that
# is the line the author drew and the one `repo.toml` cannot police. Anything
# repository-scoped and not essential is neither: it is reported, ungraded,
# because a warning that fires forever on a deliberate decision is how a
# checker teaches people to ignore it.
ESSENTIAL = {
    "contents": ("write", "push branches, read the tree"),
    "pull_requests": ("write", "open, comment on and merge pull requests"),
    "issues": ("write", "the task and tracking issues"),
    "metadata": ("read", "mandatory for everything else"),
}
# Beyond the repository. Each entry says what read exposes and what write
# allows, because they are not the same finding -- GitHub never returns a
# secret's value, so reading lists names and writing hands the fleet a
# different credential.
FORBIDDEN = {
    "organization_administration": (
        "sees the account around the repository",
        "changes the account around the repository",
    ),
    "organization_secrets": (
        "lists credentials beyond this repository",
        "overwrites credentials beyond this repository",
    ),
    "organization_self_hosted_runners": (
        "sees runners other repositories share",
        "changes runners other repositories share",
    ),
}
RANK = {"read": 1, "write": 2, "admin": 3}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=pathlib.Path, required=True)
    parser.add_argument("--installation", type=pathlib.Path, required=True)
    parser.add_argument("--where", required=True)
    parser.add_argument("--repository", required=True)
    arguments = parser.parse_args()

    app = json.loads(arguments.app.read_text())
    install = json.loads(arguments.installation.read_text())

    granted = install.get("permissions") or {}

    def verdict(name, wanted):
        have = granted.get(name)
        if not have:
            return "missing", have
        if RANK.get(have, 0) < RANK.get(wanted, 0):
            return "too low", have
        return "ok", have

    rows, blocking = [], []
    for name, (level, why) in ESSENTIAL.items():
        state, have = verdict(name, level)
        mark = {"ok": "yes", "too low": "TOO LOW", "missing": "MISSING"}[state]
        rows.append(f"| `{name}` | {level} | {have or '—'} | {mark} | {why} |")
        if state != "ok":
            blocking.append(f"{name} ({have or 'not granted'}, needs {level})")

    # A permission that should never have been granted is a finding whichever
    # way the rest of the report goes -- but only write can actually do the
    # damage, so only write fails.
    unsafe, untidy = [], []
    for name, (reading, writing) in FORBIDDEN.items():
        level = granted.get(name)
        if not level:
            continue
        if RANK.get(level, 0) >= RANK["write"]:
            unsafe.append(f"`{name}` ({level}) -- {writing}")
        else:
            untidy.append(f"`{name}` ({level}) -- {reading}")

    extra = sorted(set(granted) - set(ESSENTIAL) - set(FORBIDDEN))

    lines = [
        f"### App check — key found in {arguments.where}",
        "",
        f"**{app.get('name')}** (`{app.get('slug')}`), owned by "
        f"`{(app.get('owner') or {}).get('login')}`, installed on "
        f"`{arguments.repository}` "
        f"({install.get('repository_selection')} repositories).",
        "",
        "| permission | needed | granted | | for |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
    ]
    if extra:
        lines += [
            "**Also granted, within the repository**, and this is a statement "
            "rather than a finding: the app is granted every repository "
            "permission on purpose, so that improving the fleet never means "
            "another trip to a settings page. What bounds it is `repo.toml` "
            "and the pull request that changes it, not this list: "
            + ", ".join(f"`{name}` ({granted[name]})" for name in extra)
            + ".",
            "",
        ]
    if unsafe:
        lines += [
            "**Granted what it must never have.** These let the fleet change "
            "the rules that govern the fleet, and no review after the fact "
            "would catch their use:",
            "",
            *(f"- {item}" for item in unsafe),
            "",
            "Remove them on the app's settings page.",
            "",
        ]
    # Scope is a permission too, and the coarsest one. An app installed on
    # every repository carries its whole grant into repositories nobody
    # thought about when the grant was chosen -- including ones created later.
    # Scope is a permission too, and the coarsest one -- so it is written
    # down rather than graded. The author installed this app across their own
    # repositories deliberately, to manage them the same way. A warning here
    # would fire forever on a decision somebody made on purpose, and the next
    # reader needs the blast radius stated, not scored.
    if install.get("repository_selection") == "all":
        lines += [
            "**Installed on every repository of this account**, deliberately: "
            "the app exists to manage them the same way. Read with the grant "
            "above, that is the blast radius -- every repository permission, "
            "on every repository, including ones created later. It is bounded "
            "by what `repo.toml` declares and by the pull request that changes "
            "it, so that is where to look before widening anything.",
            "",
        ]

    if untidy:
        lines += [
            "**Granted more than it needs, at read.** Nothing here can change "
            "anything, so this is untidy rather than unsafe -- worth removing "
            "next time that page is open, not worth a special trip:",
            "",
            *(f"- {item}" for item in untidy),
            "",
        ]

    if blocking:
        lines.append("**Not enough.** Missing: " + "; ".join(blocking) + ".")
    else:
        lines.append(
            "**Enough, and inside the line.** The fleet has what it needs and "
            "nothing that reaches past this repository."
        )

    report = "\n".join(lines)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with pathlib.Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(report)

    for item in unsafe:
        print(f"::error::Granted and must not be: {item}")
    for item in untidy:
        print(f"::warning::Granted and not needed: {item}")
    if blocking:
        print(
            "::error::The app is missing a permission the fleet cannot work "
            "without: " + "; ".join(blocking)
        )
    return 1 if (blocking or unsafe) else 0


if __name__ == "__main__":
    sys.exit(main())
