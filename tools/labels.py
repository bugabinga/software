#!/usr/bin/env python3
"""Make the repository's labels match `.github/labels.yml`.

The workflow embedded a Python heredoc that parsed that file with four
regexes -- a hand-rolled YAML parser, for a YAML file, inside a YAML file.
It could not read a folded description, a single-quoted name or a list
written inline, and would have misread any of them in silence.

Creates and updates. Never deletes: a label added by hand is somebody's
decision, and a sync that removes it is a sync nobody dares run.

Usage:
    tools/labels.py
    tools/labels.py --self-test
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fleetlib import api, gh, notice

ROSTER = Path(__file__).resolve().parent.parent / ".github" / "labels.yml"


def read(text: str) -> list[dict[str, str]]:
    """The roster, parsed by a parser rather than by four regexes."""
    import yaml  # noqa: PLC0415 - optional, and the caller reports its absence

    loaded = yaml.safe_load(text) or []
    rows = []
    for entry in loaded:
        if not isinstance(entry, dict) or "name" not in entry:
            continue
        rows.append(
            {
                "name": str(entry["name"]),
                "color": str(entry.get("color", "")).lstrip("#"),
                "description": str(entry.get("description", "")).strip(),
            }
        )
    return rows


def changed(want: dict[str, str], have: dict[str, Any]) -> bool:
    """Is a write needed? A no-op PATCH is a line in a log nobody can read."""
    return (
        want["color"].lower() != str(have.get("color", "")).lower()
        or want["description"] != str(have.get("description") or "").strip()
    )


def self_test() -> int:
    rows = read(
        '- name: "fleet:task"\n'
        '  color: "1d76db"\n'
        "  description: Work asked of the fleet.\n"
        "- name: hold\n"
        "  color: b60205\n"
        "  description: >-\n"
        "    A folded description, which the regexes\n"
        "    this replaces could not read at all.\n"
    )
    assert [r["name"] for r in rows] == ["fleet:task", "hold"]
    assert rows[0]["color"] == "1d76db"
    # The shape the hand-rolled parser dropped on the floor.
    assert "folded description" in rows[1]["description"]
    assert rows[1]["color"] == "b60205"

    # A colour written with a leading hash is the same colour.
    assert read('- name: x\n  color: "#abcdef"\n')[0]["color"] == "abcdef"

    have = {"color": "1D76DB", "description": "Work asked of the fleet."}
    assert not changed(rows[0], have), "case is not a change"
    assert changed(rows[0], {**have, "description": "something else"})
    assert changed(rows[0], {**have, "color": "000000"})
    # GitHub answers a description-less label with null, not "".
    assert not changed(
        {"name": "x", "color": "", "description": ""},
        {"color": "", "description": None},
    )

    # A name with a colon in it has to survive the URL.
    assert quote("fleet:task", safe="") == "fleet%3Atask"

    every = read(ROSTER.read_text(encoding="utf-8"))
    assert every, "the roster is not empty"
    print(f"labels: {len(every)} in the roster, folded and hashed forms read")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--repo", default="")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()

    import os  # noqa: PLC0415 - only main needs the environment

    repo = arguments.repo or os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        parser.error("a repository is required")

    made = updated = same = 0
    for want in read(ROSTER.read_text(encoding="utf-8")):
        where = f"repos/{repo}/labels/{quote(want['name'], safe='')}"
        have = api(where, check=False)
        fields = [
            "-f",
            f"color={want['color']}",
            "-f",
            f"description={want['description']}",
        ]
        if isinstance(have, dict) and have.get("name"):
            if not changed(want, have):
                same += 1
                continue
            gh("api", "-X", "PATCH", where, *fields, check=False)
            updated += 1
        else:
            gh(
                "api",
                "-X",
                "POST",
                f"repos/{repo}/labels",
                "-f",
                f"name={want['name']}",
                *fields,
                check=False,
            )
            made += 1
    notice(f"labels: {made} created, {updated} updated, {same} already correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
