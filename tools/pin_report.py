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
    tools/pin_report.py --self-test
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass

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


def self_test() -> int:
    rows = [
        Pin("typst", "0.15.0", "0.15.1"),
        Pin("gh", "2.63.2", "2.63.2"),
        Pin("typos", "1.28.1", UNRESOLVED),
        Pin("shfmt", "3.10.0", ""),
    ]
    assert [r.behind for r in rows] == [True, False, False, False]
    # Unresolved is not behind. Reporting a tool as behind because mise could
    # not reach its release page is how a report trains its reader to skim.
    assert rows[2].state == "mise could not resolve it"
    assert rows[3].state == "mise could not resolve it"

    rendered = table(rows)
    assert "1 behind." in rendered
    assert "| `typst` | 0.15.0 | 0.15.1 | **behind** |" in rendered
    # Every pin in the manifest reaches the table -- the row that was silently
    # missing before is the whole reason this is a program.
    assert len(rendered.splitlines()) == len(rows) + 6

    every = pins()
    assert "typst" in every, "the manifest is the roster"
    print(f"pin_report: {len(every)} pins in the manifest, four states covered")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    if parser.parse_args(argv).self_test:
        return self_test()

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
