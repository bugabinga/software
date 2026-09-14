#!/usr/bin/env python3
"""Turn the reviewer's verdict into an actual GitHub review.

The fleet's review used to be a comment and a status check. Both are read-only
artefacts: a reader sees an opinion, and has to find the line themselves and
make the change themselves. GitHub's review machinery does better -- an inline
comment sits on the line it is about, a `suggestion` block is applied with one
click, and each thread stays open until somebody resolves it, which is what
turns a review into a loop that finishes rather than a note that decays.

The reviewer still only writes JSON. Asking a model to compose the reviews API
call correctly -- valid line numbers, the right side of the diff, the event
name, the fallbacks -- is asking it to be right about something a program can
be right about every time. So: the agent judges, this posts.

## What it does about lines

An inline comment is only accepted on a line that appears in the diff. A
finding about a line the diff never touched is still a real finding, so those
are not dropped: they move into the review body, named by file and line, where
they read as prose instead of vanishing.

Usage:
    tools/post_review.py --pr 42 --verdict /tmp/fleet-review.json
    tools/post_review.py --pr 42 --verdict f.json --dry-run   # print, post nothing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar

from fleetlib import run_tests

ROOT = Path(__file__).resolve().parent.parent
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def gh(*args: str, check: bool = True) -> str:
    binary = shutil.which("gh") or str(ROOT / ".tools" / "gh" / "gh")
    done = subprocess.run(  # noqa: PLW1510 - returncode is read below
        [binary, *args], capture_output=True, text=True, timeout=120
    )
    if done.returncode != 0:
        if check:
            sys.exit(f"gh {' '.join(args)}: {done.stderr.strip()}")
        return ""
    return done.stdout


def commentable_lines(diff: str) -> dict[str, set[int]]:
    """Which (file, line) pairs GitHub will accept an inline comment on.

    Every line the diff adds or leaves as context on the right-hand side. A
    deleted line has no right-hand number and cannot carry a comment on the
    side this reviewer talks about.
    """
    lines: dict[str, set[int]] = {}
    path = None
    number = 0
    for row in diff.splitlines():
        if row.startswith("+++ b/"):
            path = row[6:]
            lines.setdefault(path, set())
            continue
        if row.startswith("+++ ") or row.startswith("--- "):
            continue
        match = HUNK.match(row)
        if match:
            number = int(match.group(1))
            continue
        if path is None:
            continue
        if row.startswith("+"):
            lines[path].add(number)
            number += 1
        elif row.startswith("-") or row.startswith("\\"):
            continue
        elif row.startswith(" "):
            lines[path].add(number)
            number += 1
    return lines


def finding_body(finding: dict) -> str:
    what = str(finding.get("what", "")).strip()
    why = str(finding.get("why", "")).strip()
    body = what if not why else f"{what}\n\n{why}"
    suggestion = finding.get("suggestion")
    if isinstance(suggestion, str) and suggestion.strip():
        # The one thing a reader can act on without leaving the page. GitHub
        # renders it as an Apply button; the block must be the replacement
        # for exactly the commented lines, so a range finding needs a range
        # suggestion and a single-line one a single line.
        body += "\n\n```suggestion\n" + suggestion.rstrip("\n") + "\n```"
    return body or "(no detail given)"


def build(verdict: dict, allowed: dict[str, set[int]]) -> tuple[list[dict], list[str]]:
    inline: list[dict] = []
    orphaned: list[str] = []

    for finding in verdict.get("findings") or []:
        path = finding.get("path")
        line = finding.get("line")
        start = finding.get("start_line")
        placeable = (
            isinstance(path, str)
            and isinstance(line, int)
            and line in allowed.get(path, set())
            and (
                start is None
                or (isinstance(start, int) and start in allowed.get(path, set()))
            )
        )
        if placeable:
            comment = {
                "path": path,
                "line": line,
                "side": "RIGHT",
                "body": finding_body(finding),
            }
            if isinstance(start, int) and start < line:
                comment["start_line"] = start
                comment["start_side"] = "RIGHT"
            inline.append(comment)
        else:
            where = finding.get("where") or (f"{path}:{line}" if path else "—")
            # A row, not a bullet with a sentence of preamble. Newlines would
            # break the cell, so the finding is flattened; a finding that needs
            # paragraphs needs a line to sit on instead.
            body = " ".join(finding_body(finding).split())
            orphaned.append(f"| `{where}` | {body} |")

    return inline, orphaned


def review_body(verdict: dict, orphaned: list[str], round_number: int) -> str:
    summary = str(verdict.get("summary", "")).strip() or "(no summary given)"
    passed = verdict.get("verdict") == "pass"
    lines = [
        f"### Fleet review — {'pass' if passed else 'changes requested'}"
        + (f" (round {round_number})" if round_number > 1 else ""),
        "",
        summary,
    ]
    # No process narration. "Each thread stays open until it is answered" and
    # "these could not be attached to a line" were on every review this
    # workflow has ever posted, and the reader of a review already knows how
    # reviews work. The table header carries what the old sentence explained.
    if orphaned:
        lines += ["", "| Not on a changed line | |", "| --- | --- |", *orphaned]
    lines += ["", "---", "_Generated by [Claude Code](https://claude.ai/code)_"]
    return "\n".join(lines)


def dismiss_earlier(repo: str, pr: int) -> list[int]:
    """Withdraw the fleet's own outstanding requests for changes.

    A `CHANGES_REQUESTED` review stays in force until it is dismissed or the
    same reviewer submits a new one that supersedes it -- and this reviewer
    never approves, deliberately: whether a bot's approval satisfies a
    required-reviews rule is a question about GitHub's internals, and a check
    does not depend on the answer. Without this the loop could never finish:
    the responder fixes everything, the reviewer passes, and the pull request
    still carries a standing objection from three commits ago.

    Dismissing says, in the pull request's own record, that the objection was
    answered. That is the honest artefact, and it is more useful than an
    approval nobody can interpret.
    """
    listing = gh(
        "api",
        f"repos/{repo}/pulls/{pr}/reviews",
        "--paginate",
        "--jq",
        '.[] | select(.state == "CHANGES_REQUESTED") '
        '| select(.body | contains("Fleet review")) | .id',
        check=False,
    )
    dismissed = []
    for identifier in listing.split():
        result = gh(
            "api",
            "-X",
            "PUT",
            f"repos/{repo}/pulls/{pr}/reviews/{identifier}/dismissals",
            "-f",
            "message=Answered: the review that replaced this one passes.",
            "-f",
            "event=DISMISS",
            check=False,
        )
        if result:
            dismissed.append(int(identifier))
    return dismissed


def rounds_so_far(repo: str, pr: int) -> int:
    """How many times the fleet has already asked for changes here.

    One id per line, counted here, rather than `| length` in the filter.
    `gh api --paginate` runs the jq once per page and concatenates the
    results, so an aggregate answers per page: at 101 reviews this returned
    "6\\n1", which is not a digit string, so the fallback turned the round
    counter to zero -- which only mislabels this review's header, since the
    three-round guard is `fleet-respond.yml`'s own count, not this one. The
    dismissal query above always had the right shape; this one copied its
    endpoint and not its aggregation.
    """
    raw = gh(
        "api",
        f"repos/{repo}/pulls/{pr}/reviews",
        "--paginate",
        "--jq",
        '.[] | select(.state == "CHANGES_REQUESTED") '
        '| select(.body | contains("Fleet review")) | .id',
        check=False,
    )
    return len(raw.split())


SELF_TEST_DIFF = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -10,5 +10,7 @@ header
 keep_ten
-gone_eleven
+add_eleven
+add_twelve
 keep_thirteen
diff --git a/b.md b/b.md
--- a/b.md
+++ b/b.md
@@ -1,2 +1,3 @@
 one
+two
 three
"""


class LineArithmetic(unittest.TestCase):
    """The part that silently misplaces.

    A comment on the wrong line is worse than no comment: it reads as a
    finding about code that is fine, and the author has to work out that the
    reviewer meant three lines down.
    """

    def test_only_right_hand_lines_are_commentable(self) -> None:
        allowed = commentable_lines(SELF_TEST_DIFF)
        # The hunk starts at 10. `gone_eleven` is a deletion, has no
        # right-hand line, and must not appear.
        self.assertEqual(allowed["a.py"], {10, 11, 12, 13})
        self.assertEqual(allowed["b.md"], {1, 2, 3})


class Placement(unittest.TestCase):
    """Which findings become threads, and which become rows in the body."""

    FINDINGS: ClassVar[list[dict[str, object]]] = [
        {"path": "a.py", "line": 11, "what": "w", "why": "y", "suggestion": "fixed"},
        {"path": "a.py", "start_line": 10, "line": 12, "what": "range", "why": ""},
        {
            "path": "a.py",
            "line": 99,
            "where": "a.py:99",
            "what": "off the diff",
            "why": "",
        },
        {
            "path": "c.txt",
            "line": 1,
            "where": "c.txt:1",
            "what": "untouched file",
            "why": "",
        },
        {"where": "the argument", "what": "no file at all", "why": ""},
    ]

    def setUp(self) -> None:
        allowed = commentable_lines(SELF_TEST_DIFF)
        self.inline, self.orphaned = build({"findings": self.FINDINGS}, allowed)

    def test_placeable_and_not(self) -> None:
        self.assertEqual(len(self.inline), 2)
        self.assertEqual(len(self.orphaned), 3)

    def test_a_suggestion_is_fenced(self) -> None:
        self.assertIn("```suggestion\nfixed\n```", self.inline[0]["body"])

    def test_a_range_carries_its_start(self) -> None:
        self.assertEqual(self.inline[1].get("start_line"), 10)
        self.assertEqual(self.inline[1].get("start_side"), "RIGHT")

    def test_a_single_line_has_no_range(self) -> None:
        self.assertNotIn("start_line", self.inline[0])

    def test_an_off_diff_finding_still_names_its_place(self) -> None:
        self.assertTrue(any("a.py:99" in row for row in self.orphaned))


class Rounds(unittest.TestCase):
    def test_later_rounds_are_numbered(self) -> None:
        self.assertIn(
            "(round 3)", review_body({"verdict": "fail", "summary": "s"}, [], 3)
        )

    def test_the_first_is_not(self) -> None:
        self.assertNotIn("(round 1)", review_body({"verdict": "fail"}, [], 1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--verdict", type=Path)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument(
        "--diff", type=Path, help="a diff to use instead of fetching one"
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    if arguments.self_test:
        return run_tests()
    if arguments.pr is None or arguments.verdict is None:
        parser.error("--pr and --verdict are required unless --self-test")

    if not arguments.verdict.is_file():
        sys.exit(f"{arguments.verdict}: the reviewer left no verdict")
    verdict = json.loads(arguments.verdict.read_text(encoding="utf-8"))

    if arguments.diff:
        diff = arguments.diff.read_text(encoding="utf-8")
    else:
        diff = gh(
            "api",
            f"repos/{arguments.repo}/pulls/{arguments.pr}",
            "-H",
            "Accept: application/vnd.github.v3.diff",
        )

    allowed = commentable_lines(diff)
    inline, orphaned = build(verdict, allowed)
    round_number = (
        1 if arguments.dry_run else rounds_so_far(arguments.repo, arguments.pr) + 1
    )

    payload = {
        "body": review_body(verdict, orphaned, round_number),
        # A pass is a comment, not an approval: whether a bot's approval
        # satisfies a required-reviews rule is a question about GitHub's
        # internals, and a check does not depend on the answer. What stops a
        # merge is the check, not this payload: `fleet-review.yml` exits
        # non-zero on a non-pass verdict and `Fleet review` is required on
        # `Main`. The `REQUEST_CHANGES` event is where the findings land.
        "event": "COMMENT" if verdict.get("verdict") == "pass" else "REQUEST_CHANGES",
        "comments": inline,
    }

    if arguments.dry_run:
        print(json.dumps(payload, indent=2))
        print(
            f"\n{len(inline)} inline comment(s), {len(orphaned)} in the body, "
            f"event {payload['event']}",
            file=sys.stderr,
        )
        return 0

    body_file = Path("/tmp/fleet-review-payload.json")
    body_file.write_text(json.dumps(payload), encoding="utf-8")
    result = gh(
        "api",
        "-X",
        "POST",
        f"repos/{arguments.repo}/pulls/{arguments.pr}/reviews",
        "--input",
        str(body_file),
        check=False,
    )

    if not result:
        # The one refusal worth handling rather than failing on: GitHub will
        # not let an author request changes on their own pull request, and
        # once the app opens the fleet's pull requests the reviewer is the
        # author. A comment review says the same thing and is always allowed.
        payload["event"] = "COMMENT"
        payload["body"] = payload["body"].replace(
            "changes requested", "changes requested (posted as a comment)"
        )
        body_file.write_text(json.dumps(payload), encoding="utf-8")
        result = gh(
            "api",
            "-X",
            "POST",
            f"repos/{arguments.repo}/pulls/{arguments.pr}/reviews",
            "--input",
            str(body_file),
        )

    posted = json.loads(result)
    print(
        f"::notice::posted review {posted.get('id')} as {payload['event']} "
        f"with {len(inline)} inline comment(s), round {round_number}"
    )

    if verdict.get("verdict") == "pass":
        dismissed = dismiss_earlier(arguments.repo, arguments.pr)
        if dismissed:
            print(
                "::notice::dismissed "
                + ", ".join(str(i) for i in dismissed)
                + " -- the objections they raised have been answered"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
