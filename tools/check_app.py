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

    # What each fleet workflow would fail without, and the one call that
    # would fail. Ranked: `need` is a hard stop, `want` costs a feature.
    NEED = {
        "contents": ("write", "push branches, read the tree"),
        "pull_requests": ("write", "open, comment on and merge pull requests"),
        "issues": ("write", "the task and tracking issues"),
        "metadata": ("read", "mandatory for everything else"),
    }
    WANT = {
        "actions": ("write", "start CI on a pushed branch; read runs for the weekly report"),
        "checks": ("read", "decide whether a branch is green"),
        "workflows": ("write", "only if an agent should ever push a change under .github/workflows/"),
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
    for name, (level, why) in {**NEED, **WANT}.items():
        state, have = verdict(name, level)
        mark = {"ok": "yes", "too low": "TOO LOW", "missing": "MISSING"}[state]
        rows.append(f"| `{name}` | {level} | {have or '—'} | {mark} | {why} |")
        if state != "ok":
            (blocking if name in NEED else soft).append(
                f"{name} ({have or 'not granted'}, needs {level})"
            )

    extra = sorted(set(granted) - set(NEED) - set(WANT))

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
    if blocking:
        lines.append("**Not enough.** Missing: " + "; ".join(blocking) + ".")
    elif soft:
        lines.append(
            "**Enough to run.** Not granted, and each costs one thing: "
            + "; ".join(soft)
            + "."
        )
    else:
        lines.append("**Enough.** Every permission the fleet needs is granted.")

    report = "\n".join(lines)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(report)

    if blocking:
        print(
            "::error::The app is missing a permission the fleet cannot work "
            "without: " + "; ".join(blocking)
        )
        return 1
    for item in soft:
        print(f"::warning::Not granted: {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
