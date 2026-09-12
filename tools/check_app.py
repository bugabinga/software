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
it is syntax-checked by `make check` and can be run against a fixture.

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

    # Three lists, and the middle one is the point.
    #
    # ESSENTIAL is what the fleet cannot run without: a gap here is a failure.
    # CEILING is everything a book pipeline could ever want, granted once so
    # that improving the fleet never means another trip to a settings page --
    # a gap here is a note, naming what it would cost, not a failure.
    # FORBIDDEN is the guardrails: repository settings, the credentials
    # themselves, the environment rules that gate them. An agent holding any
    # of these could widen its own authority, and no review after the fact
    # would catch it. A grant here fails, loudly.
    ESSENTIAL = {
        "contents": ("write", "push branches, read the tree"),
        "pull_requests": ("write", "open, comment on and merge pull requests"),
        "issues": ("write", "the task and tracking issues"),
        "metadata": ("read", "mandatory for everything else"),
    }
    CEILING = {
        "actions": ("write", "start CI on a pushed branch; read runs for the report"),
        "checks": ("write", "decide whether a branch is green; post verdicts"),
        "statuses": ("write", "report a verdict as a commit status"),
        "deployments": ("write", "record what went live and when"),
        "workflows": ("write", "push or merge a change under .github/workflows/"),
    }
    FORBIDDEN = {
        "administration": "repository settings, and deleting the repository",
        "secrets": "the credentials themselves",
        "actions_variables": "the variables the workflows read",
        "environments": "the environment rules that gate every secret",
        "organization_administration": "the account around the repository",
        "organization_secrets": "credentials beyond this repository",
    }
    RANK = {"read": 1, "write": 2, "admin": 3}

    def verdict(name, wanted):
        have = granted.get(name)
        if not have:
            return "missing", have
        if RANK.get(have, 0) < RANK.get(wanted, 0):
            return "too low", have
        return "ok", have

    rows, blocking, soft = [], [], []
    for name, (level, why) in {**ESSENTIAL, **CEILING}.items():
        state, have = verdict(name, level)
        mark = {"ok": "yes", "too low": "TOO LOW", "missing": "MISSING"}[state]
        rows.append(f"| `{name}` | {level} | {have or '—'} | {mark} | {why} |")
        if state != "ok":
            (blocking if name in ESSENTIAL else soft).append(
                f"{name} ({have or 'not granted'}, needs {level})"
            )

    # A permission that should never have been granted is a finding whichever
    # way the rest of the report goes.
    overreach = [
        f"`{name}` ({granted[name]}) -- {why}"
        for name, why in FORBIDDEN.items()
        if granted.get(name)
    ]

    extra = sorted(set(granted) - set(ESSENTIAL) - set(CEILING) - set(FORBIDDEN))

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
            "Also granted, and not needed by anything here: "
            + ", ".join(f"`{name}` ({granted[name]})" for name in extra)
            + ". Harmless, but narrower is better.",
            "",
        ]
    if overreach:
        lines += [
            "**Granted more than it should ever have.** These let the fleet "
            "change the rules that govern the fleet, which is the one thing "
            "the app must not be able to do:",
            "",
            *(f"- {item}" for item in overreach),
            "",
            "Remove them on the app's settings page. Nothing here needs them, "
            "and no review after the fact would catch their use.",
            "",
        ]

    if blocking:
        lines.append("**Not enough.** Missing: " + "; ".join(blocking) + ".")
    elif soft:
        lines.append(
            "**Enough for the fleet as it stands.** Below the ceiling, and "
            "each of these is a change somebody will otherwise have to come "
            "back for: "
            + "; ".join(soft)
            + ". Granting them now costs nothing and saves that trip."
        )
    else:
        lines.append("**At the ceiling.** Nothing the fleet grows into needs another visit here.")

    report = "\n".join(lines)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(report)

    for item in overreach:
        print(f"::error::Granted and should not be: {item}")
    if blocking:
        print(
            "::error::The app is missing a permission the fleet cannot work "
            "without: " + "; ".join(blocking)
        )
    for item in soft:
        print(f"::notice::Below the ceiling: {item}")
    return 1 if (blocking or overreach) else 0


if __name__ == "__main__":
    sys.exit(main())
