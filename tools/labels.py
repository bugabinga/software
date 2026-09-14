#!/usr/bin/env python3
"""Make the repository's labels match `.github/labels.toml`.

The workflow embedded a Python heredoc that parsed that file with four
regexes -- a hand-rolled YAML parser, for a YAML file, inside a YAML file.
Replacing it with PyYAML traded that for a worse fault: `mise.toml` says
every tool here is standard library only, and PyYAML is on the runner by
luck rather than by declaration. The roster is TOML, which `tomllib` reads.

Creates and updates. Never deletes: a label added by hand is somebody's
decision, and a sync that removes it is a sync nobody dares run.

Usage:
    tools/labels.py
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import quote

import tomllib
from fleetlib import api, gh, notice

ROSTER = Path(__file__).resolve().parent.parent / ".github" / "labels.toml"


def read(text: str) -> list[dict[str, str]]:
    """The roster, parsed by a parser rather than by four regexes."""
    rows = []
    for entry in tomllib.loads(text).get("label") or []:
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


class Roster(unittest.TestCase):
    """The roster, read by a parser rather than by four regexes."""

    FIXTURE = (
        '[[label]]\nname = "fleet:task"\ncolor = "1d76db"\n'
        'description = "Work asked of the fleet."\n'
        '[[label]]\nname = "hold"\ncolor = "b60205"\n'
        'description = """\nA description over more than one line, which the\n'
        'regexes this replaces could not read at all.\n"""\n'
    )

    def test_names_and_colours(self) -> None:
        rows = read(self.FIXTURE)
        self.assertEqual([r["name"] for r in rows], ["fleet:task", "hold"])
        self.assertEqual(rows[0]["color"], "1d76db")

    def test_a_multiline_description(self) -> None:
        self.assertIn("more than one line", read(self.FIXTURE)[1]["description"])

    def test_a_leading_hash_is_the_same_colour(self) -> None:
        rows = read('[[label]]\nname = "x"\ncolor = "#abcdef"\n')
        self.assertEqual(rows[0]["color"], "abcdef")

    def test_the_real_roster_parses(self) -> None:
        self.assertTrue(read(ROSTER.read_text(encoding="utf-8")))


class Writes(unittest.TestCase):
    """When a label is worth a PATCH, and when it is noise in a log."""

    WANT: ClassVar[dict[str, str]] = {
        "name": "fleet:task",
        "color": "1d76db",
        "description": "Work asked of the fleet.",
    }

    def test_case_is_not_a_change(self) -> None:
        self.assertFalse(
            changed(
                self.WANT, {"color": "1D76DB", "description": self.WANT["description"]}
            )
        )

    def test_a_real_difference_is(self) -> None:
        for have in (
            {"color": "1d76db", "description": "something else"},
            {"color": "000000", "description": self.WANT["description"]},
        ):
            with self.subTest(have=have):
                self.assertTrue(changed(self.WANT, have))

    def test_github_answers_null_for_no_description(self) -> None:
        self.assertFalse(
            changed(
                {"name": "x", "color": "", "description": ""},
                {"color": "", "description": None},
            )
        )

    def test_a_colon_survives_the_url(self) -> None:
        self.assertEqual(quote("fleet:task", safe=""), "fleet%3Atask")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="")
    arguments = parser.parse_args(argv)

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
