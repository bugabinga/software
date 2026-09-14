#!/usr/bin/env python3
"""Turn `trace --count --missing` output into a table worth reading.

`python3 -m trace` writes one annotated `.cover` per module and prints
nothing: the answer is in 2900 lines of prefixed source. This reads the
prefixes back. A line the tests reached carries its hit count and a colon; a
line they did not carries `>>>>>>`; everything else -- blanks, comments,
docstrings, `else:` -- is not a statement and is counted as neither.

Not a gate, deliberately. A coverage threshold buys tests written to move a
number, and the number is a question anyway: `verdict.py` sits at 65% because
its other half shells out to git, which a test should not do. Read the ranking
and ask why the bottom is at the bottom.

Usage:
    tools/coverage.py                     # after `mise run coverage`
    tools/coverage.py --coverdir build/coverage
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HIT = re.compile(r"^\s*\d+:")
MISS = ">>>>>>"


@dataclass(frozen=True)
class Module:
    """One `.cover` file, counted."""

    name: str
    hit: int
    missed: int

    @property
    def total(self) -> int:
        return self.hit + self.missed

    @property
    def share(self) -> float:
        return self.hit / self.total if self.total else 1.0


def count(text: str) -> tuple[int, int]:
    """`(reached, unreached)` statements in one annotated source."""
    hit = missed = 0
    for line in text.splitlines():
        if line.startswith(MISS):
            missed += 1
        elif HIT.match(line):
            hit += 1
    return hit, missed


def read(coverdir: Path) -> list[Module]:
    """Every module in a cover directory."""
    modules = []
    for path in sorted(coverdir.glob("*.cover")):
        hit, missed = count(path.read_text(encoding="utf-8", errors="replace"))
        if hit or missed:
            modules.append(Module(path.stem, hit, missed))
    return modules


def table(modules: list[Module]) -> str:
    """The ranking, worst first, and one total line.

    The sort lives here rather than in `read`, because the ordering is what
    the table is for: the answer being asked of it is which module is worst,
    and a caller that had to sort first could forget to. It was here in the
    first draft and the test that was meant to cover it sorted its own
    fixture instead, so it passed over a `table` that ranked nothing.
    """
    if not modules:
        return "no .cover files; run `mise run coverage` first"
    width = max(len(module.name) for module in modules)
    rows = [
        f"{module.share:5.0%}  {module.name:<{width}}  {module.hit}/{module.total}"
        for module in sorted(modules, key=lambda module: (module.share, module.name))
    ]
    hit = sum(module.hit for module in modules)
    total = sum(module.total for module in modules)
    rows.append(f"{hit / total:5.0%}  {'all':<{width}}  {hit}/{total}")
    return "\n".join(rows)


class Counting(unittest.TestCase):
    """What `trace` marks, and what it leaves unmarked."""

    def test_the_three_kinds_of_line(self) -> None:
        hit, missed = count(
            "    3: reached()\n"
            ">>>>>>     unreached()\n"
            "       # a comment is not a statement\n"
            "\n"
        )
        self.assertEqual((hit, missed), (1, 1))

    def test_nothing_in_nothing_out(self) -> None:
        self.assertEqual(count(""), (0, 0))

    def test_a_colon_in_the_source_is_not_a_hit(self) -> None:
        # The prefix is a count and a colon at the start of the line; a
        # dictionary literal further along it is not.
        self.assertEqual(count('       {"a": 1}'), (0, 0))


class Ranking(unittest.TestCase):
    """The table answers the question it is read for: what is worst."""

    def setUp(self) -> None:
        self.modules = [
            Module("good", 9, 1),
            Module("bad", 1, 9),
            Module("half", 5, 5),
        ]

    def test_worst_leads(self) -> None:
        names = [row.split()[1] for row in table(self.modules).splitlines()]
        self.assertEqual(names, ["bad", "half", "good", "all"])

    def test_the_total_is_over_statements_not_over_modules(self) -> None:
        # Three modules at 10%, 50% and 90% average 50%, and so does this --
        # but only because they are the same size. The total must follow the
        # statements, or a large untested module hides behind small tested
        # ones.
        self.assertEqual(
            table(self.modules).splitlines()[-1].split(), ["50%", "all", "15/30"]
        )

    def test_an_empty_directory_says_so(self) -> None:
        self.assertIn("run `mise run coverage`", table([]))


class TheTree(unittest.TestCase):
    """Against whatever the last coverage run left behind, if anything."""

    def test_it_reads_a_real_run(self) -> None:
        coverdir = ROOT / "build" / "coverage"
        if not coverdir.is_dir():
            self.skipTest("no coverage run in this checkout")
        modules = read(coverdir)
        self.assertTrue(all(module.total for module in modules))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverdir",
        type=Path,
        default=ROOT / "build" / "coverage",
        help="where `trace --coverdir` wrote its annotated sources",
    )
    args = parser.parse_args(argv)
    if not args.coverdir.is_dir():
        sys.exit(f"{args.coverdir} does not exist -- run `mise run coverage` first")
    print(table(read(args.coverdir)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
