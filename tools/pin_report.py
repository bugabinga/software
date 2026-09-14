#!/usr/bin/env python3
"""Which pinned tools are behind upstream, and is Typst one of them.

Seventy lines of shell in `maintenance.yml`, and one of them never worked:

    for tool in gh typos; do
      eval "pinned=\\$${tool}_pinned latest=\\$${tool}_latest"

`gh_pinned` and `typos_latest` were never assigned -- only `typst_*` were --
so the loop compared empty to empty every Monday and reported nothing. It
looked like two extra tools were being watched. `mise.toml` is the roster
(`tools/pinned.py`), so the report is over all of it and the arithmetic is
here, where a test can reach it.

Usage:
    tools/pin_report.py            # writes the summary and Typst's outputs
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from dataclasses import dataclass
from typing import ClassVar

from fleetlib import notice, output, summary
from pinned import pins

UNRESOLVED = "?"


@dataclass(frozen=True)
class Pin:
    tool: str
    pinned: str
    latest: str

    @property
    def state(self) -> str:
        if self.latest in {"", UNRESOLVED}:
            return "mise could not resolve it"
        return "current" if self.pinned == self.latest else "**behind**"

    @property
    def behind(self) -> bool:
        return self.state == "**behind**"


def table(rows: list[Pin]) -> str:
    """The report a human reads, and the count they act on."""
    behind = [row for row in rows if row.behind]
    lines = [
        "### Pinned tools",
        "",
        "| Tool | Pinned | Latest | |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| `{r.tool}` | {r.pinned} | {r.latest or UNRESOLVED} | {r.state} |"
        for r in rows
    ]
    lines += [
        "",
        f"{len(behind)} behind. Only Typst is bumped automatically, and "
        "only when the book still builds on it; the rest are reported.",
    ]
    return "\n".join(lines)


def latest(tool: str) -> str:
    """What mise says the newest version is, or `?` when it cannot say."""
    if not shutil.which("mise"):
        return UNRESOLVED
    done = subprocess.run(  # noqa: PLW1510 - a tool mise cannot resolve is not an error
        ["mise", "latest", tool], capture_output=True, text=True, timeout=60
    )
    return done.stdout.strip() or UNRESOLVED


class States(unittest.TestCase):
    """Behind, current, and the one the shell version conflated with behind."""

    ROWS: ClassVar[list[Pin]] = [
        Pin("typst", "0.15.0", "0.15.1"),
        Pin("gh", "2.63.2", "2.63.2"),
        Pin("typos", "1.28.1", UNRESOLVED),
        Pin("shfmt", "3.10.0", ""),
    ]

    def test_only_a_known_newer_version_is_behind(self) -> None:
        self.assertEqual([r.behind for r in self.ROWS], [True, False, False, False])

    def test_unresolved_is_not_behind(self) -> None:
        # Reporting a tool as behind because a release page was unreachable
        # is how a weekly report teaches its reader to skim it.
        for row in self.ROWS[2:]:
            with self.subTest(latest=row.latest):
                self.assertEqual(row.state, "mise could not resolve it")


class Table(unittest.TestCase):
    def test_every_pin_reaches_it(self) -> None:
        rendered = table(States.ROWS)
        self.assertIn("1 behind.", rendered)
        self.assertIn("| `typst` | 0.15.0 | 0.15.1 | **behind** |", rendered)
        # The row silently missing before is the whole reason this is a program.
        self.assertEqual(len(rendered.splitlines()), len(States.ROWS) + 6)

    def test_the_manifest_is_the_roster(self) -> None:
        self.assertIn("typst", pins())


def main() -> int:
    rows = [Pin(tool, pinned, latest(tool)) for tool, pinned in sorted(pins().items())]
    summary(table(rows))
    behind = [row for row in rows if row.behind]
    notice(f"{len(behind)} pinned tool(s) behind upstream")
    for row in behind:
        notice(f"{row.tool} {row.pinned} is behind {row.latest}")

    typst = next((row for row in rows if row.tool == "typst"), None)
    if typst is None:
        print("::error::no typst pin in mise.toml")
        return 1
    output("pinned", typst.pinned)
    output("latest", typst.latest)
    output("behind", "true" if typst.behind else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
