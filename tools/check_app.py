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
    # Read and write are not the same finding, and saying so matters: the
    # first report this produced called `secrets` at read "the credentials
    # themselves", which is not true. GitHub never returns a secret's value
    # through the API -- reading lists names and dates. It is writing that is
    # dangerous, because overwriting a credential is how an agent would hand
    # itself a different one.
    #
    # So each entry says what read exposes and what write allows. Write fails
    # the check; read is reported and does not, because a permission that
    # cannot change anything is untidy rather than unsafe, and a check that
    # cries wolf about it will be ignored when it has something to say.
    FORBIDDEN = {
        "administration": (
            "sees repository settings, including the branch rules",
            "changes those settings, and can delete the repository",
        ),
        "secrets": (
            "lists which secrets exist, not their values -- the API never "
            "returns those",
            "overwrites a credential, which is how an agent hands itself a "
            "different one",
        ),
        "actions_variables": (
            "reads the variables the workflows read",
            "changes what the workflows read",
        ),
        "environments": (
            "sees the environment rules that gate every secret",
            "edits them, which is the stop button and the branch policy",
        ),
        "organization_administration": (
            "sees the account around the repository",
            "changes the account around the repository",
        ),
        "organization_secrets": (
            "lists credentials beyond this repository",
            "overwrites credentials beyond this repository",
        ),
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
    if install.get("repository_selection") == "all":
        lines += [
            "**Installed on every repository**, not just this one. The grant "
            "above therefore applies to repositories nobody had in mind when "
            "it was chosen, and to every repository created after it. "
            "Narrow it: the app's page -> Install App -> the gear beside the "
            "account -> Only select repositories.",
            "",
        ]
        untidy.append("installed on all repositories rather than this one")

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
    elif soft:
        lines.append(
            "**Enough for the fleet as it stands.** Below the ceiling, and "
            "each of these is a change somebody will otherwise have to come "
            "back for: "
            + "; ".join(soft)
            + ". Granting them now costs nothing and saves that trip."
        )
    else:
        lines.append(
            "**At the ceiling.** Nothing the fleet grows into needs another visit here."
        )

    report = "\n".join(lines)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as handle:
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
    for item in soft:
        print(f"::notice::Below the ceiling: {item}")
    return 1 if (blocking or unsafe) else 0


if __name__ == "__main__":
    sys.exit(main())
