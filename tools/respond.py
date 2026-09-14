#!/usr/bin/env python3
"""Whether there is a review to answer on this pull request, and which round.

Two `run:` blocks in `fleet-respond.yml`, eighty lines, holding the brake that
stops two agents arguing forever. Both were built out of `gh --paginate` with
a jq filter that aggregates -- the exact shape that answers once per page and
concatenates. At 101 reviews on #82 the round count came back "6\\n1", the
fallback read that as zero, and the counter reset. The guard survived only
because it is a second query; the header lied for four rounds.

`decide` and `round_of` are pure. Everything that asks GitHub is in `main`.

Usage:
    tools/respond.py --about          # which pull request, and is it answerable
    tools/respond.py --rounds --pr 82 # how many, and hold at three
"""

from __future__ import annotations

import argparse
import os
import sys
import unittest
from dataclasses import dataclass

from fleetlib import api, gh, notice, output, paged

# Three rounds, then the author. Two agents that disagree three times are not
# converging, and a fourth round is the same money for the same answer.
LIMIT = 3

HELD = (
    "Three rounds and this is not settled, so the fleet has stopped and "
    "labelled it `hold`. `agent-branches.yml` merges nothing held.\n\n"
    "The open threads above are the disagreement. Remove `hold` and push to "
    "start the loop again."
)


@dataclass(frozen=True)
class About:
    pr: int | None = None
    proceed: bool = False
    why: str = ""


def decide(
    *,
    event: str,
    pr: int | None,
    draft: bool = False,
    last_verdict: str = "",
) -> About:
    """Is there a fleet verdict on this pull request waiting to be answered?"""
    if pr is None:
        return About(why="no open pull request for this event")
    if draft:
        return About(pr=pr, why=f"#{pr} is a draft")
    # A `workflow_run` wake means the reviewer finished, which is not the same
    # as it having asked for anything. A direct `pull_request_review` already
    # carries the verdict that woke it.
    if event == "workflow_run" and last_verdict != "CHANGES_REQUESTED":
        return About(
            pr=pr,
            why=f"the last fleet verdict on #{pr} is "
            f"{last_verdict or 'none'}, so there is nothing to answer",
        )
    return About(pr=pr, proceed=True, why=f"answering the review on #{pr}")


def round_of(verdicts: list[str]) -> int:
    """How many times the fleet has already asked for changes here.

    A count of ids, never `| length` inside a paginated jq. This is the
    number that came back "6\\n1".
    """
    return sum(1 for state in verdicts if state == "CHANGES_REQUESTED")


class Answerable(unittest.TestCase):
    """Is there a fleet verdict here waiting to be answered?"""

    def test_no_pull_request(self) -> None:
        self.assertFalse(decide(event="workflow_run", pr=None).proceed)

    def test_a_draft_is_a_draft_whatever_woke_this(self) -> None:
        for event in ("workflow_run", "pull_request_review"):
            with self.subTest(event=event):
                self.assertFalse(decide(event=event, pr=7, draft=True).proceed)

    def test_finishing_is_not_objecting(self) -> None:
        # A `workflow_run` wake means the reviewer finished. Only a
        # changes-requested verdict is something to answer.
        for verdict in ("APPROVED", "COMMENTED", ""):
            with self.subTest(verdict=verdict):
                self.assertFalse(
                    decide(event="workflow_run", pr=7, last_verdict=verdict).proceed
                )
        self.assertTrue(
            decide(event="workflow_run", pr=7, last_verdict="CHANGES_REQUESTED").proceed
        )

    def test_a_review_event_carries_its_own_verdict(self) -> None:
        self.assertTrue(decide(event="pull_request_review", pr=7).proceed)

    def test_the_number_survives_a_stop(self) -> None:
        # The record step needs it even when nothing is answered.
        self.assertEqual(decide(event="workflow_run", pr=7, draft=True).pr, 7)


class Rounds(unittest.TestCase):
    """The count that decides when the fleet stops and asks the author."""

    def test_counting(self) -> None:
        for verdicts, want in (
            ([], 0),
            (["CHANGES_REQUESTED"], 1),
            (["CHANGES_REQUESTED", "COMMENTED", "CHANGES_REQUESTED"], 2),
            (["COMMENTED"] * 200, 0),
        ):
            with self.subTest(n=len(verdicts)):
                self.assertEqual(round_of(verdicts), want)

    def test_it_survives_a_second_page(self) -> None:
        # 101 is where the old `--paginate` aggregate answered "6\n1".
        self.assertEqual(round_of(["CHANGES_REQUESTED"] * 101), 101)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--about", action="store_true")
    parser.add_argument("--rounds", action="store_true")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    arguments = parser.parse_args(argv)

    repo = arguments.repo
    if not repo:
        parser.error("a repository is required")

    if arguments.about:
        event = os.environ.get("EVENT", "")
        number = arguments.pr
        if number is None and os.environ.get("EVENT_PR"):
            number = int(os.environ["EVENT_PR"])
        if number is None and os.environ.get("RUN_PRS", "").split():
            number = int(os.environ["RUN_PRS"].split()[0])
        if number is None and (branch := os.environ.get("RUN_BRANCH", "")):
            owner = repo.split("/", 1)[0]
            found = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=open") or []
            number = found[0]["number"] if found else None

        pull = api(f"repos/{repo}/pulls/{number}") if number else None
        verdicts = (
            [
                str(r.get("state", ""))
                for r in paged(f"repos/{repo}/pulls/{number}/reviews")
                if "Fleet review" in str(r.get("body", ""))
            ]
            if number
            else []
        )

        about = decide(
            event=event,
            pr=number,
            draft=bool((pull or {}).get("draft")),
            last_verdict=verdicts[-1] if verdicts else "",
        )
        notice(about.why)
        output("proceed", "true" if about.proceed else "false")
        if about.pr is not None:
            output("pr", str(about.pr))
            output("branch", str((pull or {}).get("head", {}).get("ref", "")))
            output("head", str((pull or {}).get("head", {}).get("sha", "")))
        return 0

    if arguments.rounds:
        if arguments.pr is None:
            parser.error("--rounds needs --pr")
        verdicts = [
            str(r.get("state", ""))
            for r in paged(f"repos/{repo}/pulls/{arguments.pr}/reviews")
            if "Fleet review" in str(r.get("body", ""))
        ]
        rounds = round_of(verdicts)
        output("count", str(rounds))
        if rounds < LIMIT:
            output("over", "false")
            notice(f"round {rounds + 1} of at most {LIMIT}")
            return 0

        output("over", "true")
        labels = api(f"repos/{repo}/issues/{arguments.pr}/labels") or []
        if any(label.get("name") == "hold" for label in labels):
            notice(f"already held after {rounds} rounds; saying nothing further")
            return 0
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{arguments.pr}/labels",
            "-f",
            "labels[]=hold",
            check=False,
        )
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{arguments.pr}/comments",
            "-f",
            f"body={HELD}",
            check=False,
        )
        notice(f"held #{arguments.pr} after {rounds} rounds")
        return 0

    parser.error("one of --about or --rounds")
    return 2


if __name__ == "__main__":
    sys.exit(main())
