#!/usr/bin/env python3
"""Read the reviewer's verdict, and decide whether the check passes.

This is the gate: `Fleet review` is a required context, so what this returns
decides whether a pull request can merge. It was a Python heredoc inside a
`run:` block inside YAML -- three levels of quoting around the one exit code
that matters.

Three outcomes, and the middle one is the one worth having a program for:

    skipped   the pull request edits `fleet-review.yml`, so the action
              declined and there is no review. Exit 0 -- but say so, because
              a green check that reviewed nothing is the most misleading
              thing this workflow can produce, and #82 was merged under one.
    missing   no verdict file. Exit 1. Silence is not a pass.
    read      whatever the reviewer said.

Usage:
    tools/verdict.py --file /tmp/fleet-review.json
    tools/verdict.py --self-test
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

from fleetlib import fail, notice, run_tests, summary

SELF = ".github/workflows/fleet-review.yml"


def report(data: dict[str, Any]) -> tuple[bool, str]:
    """The summary a human reads, and whether the check passes."""
    verdict = str(data.get("verdict", ""))
    said = " ".join(str(data.get("summary", "")).split()) or "(no summary given)"
    findings = data.get("findings") or []

    lines = [f"### Fleet review: **{verdict or 'unreadable'}**", "", said, ""]
    if findings:
        lines += ["| Where | What | Why |", "| --- | --- | --- |"]
        for finding in findings:
            cells = [
                " ".join(str(finding.get(key, "")).split()).replace("|", r"\|")
                for key in ("where", "what", "why")
            ]
            lines.append(f"| `{cells[0]}` | {cells[1]} | {cells[2]} |")
    else:
        lines.append("_No findings._")
    return verdict == "pass", "\n".join(lines)


def edits_itself() -> bool:
    """Does this branch change the reviewer? Then the action declined."""
    subprocess.run(  # noqa: PLW1510 - a missing remote is not an error here
        ["git", "fetch", "-q", "--depth=1", "origin", "main"],
        capture_output=True,
        timeout=60,
    )
    done = subprocess.run(  # noqa: PLW1510 - exit 1 is the answer, not a failure
        ["git", "diff", "--quiet", "FETCH_HEAD", "--", SELF],
        capture_output=True,
        timeout=60,
    )
    return done.returncode != 0


class Rendering(unittest.TestCase):
    """The summary a human reads, and the shapes that shear its table."""

    def test_a_pass_reads_as_one(self) -> None:
        passed, text = report(
            {"verdict": "pass", "summary": "  every citation holds  "}
        )
        self.assertTrue(passed)
        self.assertIn("every citation holds", text)
        self.assertIn("_No findings._", text)

    def test_findings_become_rows(self) -> None:
        failed, text = report(
            {
                "verdict": "fail",
                "summary": "two claims do not survive the files they name",
                "findings": [{"where": "a.py:1", "what": "wrong", "why": "measured"}],
            }
        )
        self.assertFalse(failed)
        self.assertIn("| `a.py:1` | wrong | measured |", text)

    def test_a_cell_cannot_break_the_table(self) -> None:
        # A pipe would end the cell; a newline would end the row.
        _, piped = report({"verdict": "fail", "findings": [{"what": "a | b"}]})
        self.assertIn(r"a \| b", piped)
        _, wrapped = report({"verdict": "fail", "findings": [{"why": "one\ntwo"}]})
        self.assertIn("| one two |", wrapped)


class OnlyPassPasses(unittest.TestCase):
    """This exit code decides whether a pull request may merge."""

    def test_anything_else_fails(self) -> None:
        for data in ({}, {"verdict": ""}, {"verdict": "passed"}, {"verdict": None}):
            with self.subTest(data=data):
                self.assertFalse(report(data)[0])

    def test_the_word_itself(self) -> None:
        self.assertTrue(report({"verdict": "pass"})[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--file", default="/tmp/fleet-review.json")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return run_tests()

    if edits_itself():
        notice(
            "This pull request changes fleet-review.yml, so the action "
            "declined and there is no review. Merging it is what makes the "
            "next pull request reviewable."
        )
        summary(
            "### Fleet review: **skipped**\n\nThis pull request changes "
            "`fleet-review.yml`. Nothing was reviewed, and this check is "
            "green only because it did not run. Changes under `.github/` "
            "need a human anyway."
        )
        return 0

    path = Path(arguments.file)
    if not path.is_file():
        fail("The reviewer left no verdict. Silence is not a pass.")
        return 1

    passed, text = report(json.loads(path.read_text(encoding="utf-8")))
    summary(text)
    said = text.splitlines()[2]
    if not passed:
        fail(f"Fleet review failed: {said}")
        return 1
    notice(f"Fleet review passed: {said}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
