#!/usr/bin/env python3
"""Every issue gets an answer: a route, or a reason it was closed.

`fleet.yml` dispatches on `issues: [labeled]`, for `fleet:material` and
`fleet:task` only. An issue opened without a label, or with the wrong one,
therefore did nothing at all -- no run, no comment, no notice. It sat there
looking filed.

Two halves, and the split is the point. `needs_triage` is mechanical: does
this issue already carry a label that routes it? `apply` is mechanical too:
label it, comment, close it, dispatch. The judgement in between -- what this
issue actually is -- is an agent's, and it arrives as a verdict file, the same
shape `tools/post_review.py` reads.

The third half is `plan`, and it exists because the first two were reachable
only from `issues: [opened]`. An issue that was open before this workflow
landed, or whose triage run died, or that was filed while the credential was
missing, was stranded: nothing would ever look at it again. #84 sat unlabelled
for fifteen hours that way. `plan` is what a schedule asks -- which open
issues nothing routes -- so the answer is a sweep rather than an edge.

Usage:
    tools/triage.py --check --issue 7            # is triage needed?
    tools/triage.py --apply --issue 7 --verdict /tmp/triage.json
    tools/triage.py --plan                       # every issue nothing routes
    tools/triage.py --plan --issue 7             # just this one, for an event
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fleetlib import api, captured, gh, notice, output, paged, warn

ROOT = Path(__file__).resolve().parent.parent

# The labels that route. `fleet.yml`'s occasion router maps exactly these two
# to a trigger; anything else it prints a notice about and exits 0.
ROUTING = {"fleet:material", "fleet:task"}

# Applied by the fleet, not by a human, and not a route on their own. They
# are a state machine with three edges and `mark` is all of them:
#
#     picked up  ->  fleet:running
#     finished   ->  (neither)
#     died       ->  fleet:blocked
#
# `fleet.yml` used to write the first edge inline and neither of the others.
# An issue the fleet picked up kept `fleet:running` for ever -- through a
# failed run, through a merge, through everything -- so the one label that
# says "something is happening here" meant nothing at all, and a run that
# died left an issue that looked in flight. `fleet:blocked` was in the
# roster and in this set and no line of the tree ever applied it.
FLEET_STATE = {"fleet:running", "fleet:blocked"}

# What each outcome leaves behind. Absent from the list means removed.
MARKS = {
    "running": {"fleet:running"},
    "done": set(),
    "blocked": {"fleet:blocked"},
}

# What a verdict may ask for. Anything else is a malformed verdict, which is
# treated as "leave it for a human" rather than guessed at.
ROUTES = {"material", "task", "close", "human"}


def needs_triage(labels: list[str]) -> bool:
    """True when nothing on this issue will route it anywhere.

    A `fleet:` state label is not a route: `fleet:running` on an issue with no
    `fleet:task` is an issue the fleet marked and then forgot.
    """
    return not (set(labels) & ROUTING)


# A matrix leg per issue, and GitHub caps a matrix at 256. A sweep that
# wanted more than this is a repository nobody is triaging by hand either;
# the cap keeps one bad morning from spending a day of runner slots, and the
# next sweep takes the rest.
SWEEP_CAP = 20


def untriaged(issues: list[dict[str, Any]]) -> list[int]:
    """The open issues nothing routes, oldest first.

    Oldest first because a stranded issue is the one this exists for, and a
    cap that took the newest would strand it a second time. Pull requests are
    issues to this endpoint and are not triaged here.
    """
    numbers = [
        int(issue["number"])
        for issue in issues
        if not issue.get("pull_request")
        and needs_triage(
            [str(label.get("name", "")) for label in issue.get("labels") or []]
        )
    ]
    return sorted(numbers)[:SWEEP_CAP]


def mark(repo: str, issue: int, state: str) -> int:
    """Move an issue to one of the three fleet states.

    Removing first, then adding, and removing everything that is not wanted:
    a run that ends blocked must not keep `fleet:running` beside it, and the
    two together are how an issue comes to say two contradictory things.

    A label that is not on the issue removes with a 404, which is the answer
    rather than a fault -- so nothing here is checked, and the notice says
    what was intended rather than what the API thought of it.
    """
    wanted = MARKS[state]
    for label in sorted(FLEET_STATE - wanted):
        gh(
            "api",
            "-X",
            "DELETE",
            f"repos/{repo}/issues/{issue}/labels/{label}",
            check=False,
        )
    for label in sorted(wanted):
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{issue}/labels",
            "-f",
            f"labels[]={label}",
            check=False,
        )
    notice(
        f"#{issue} is {state}" + (f" ({', '.join(sorted(wanted))})" if wanted else "")
    )
    return 0


def verdict_route(verdict: dict[str, Any]) -> tuple[str, str]:
    """The route and the reason, or `human` when the verdict is unusable.

    A malformed verdict must not become a silent close. The whole reason this
    program exists is that silence looked like filing.
    """
    route = str(verdict.get("route", "")).strip()
    why = " ".join(str(verdict.get("why", "")).split())
    if route not in ROUTES:
        return "human", f"the triage verdict asked for {route!r}, which is not a route"
    if not why:
        return "human", "the triage verdict gave no reason"
    return route, why


def label_for(route: str) -> str | None:
    return {"material": "fleet:material", "task": "fleet:task"}.get(route)


def apply(repo: str, issue: int, verdict: dict[str, Any], agent: str = "") -> int:
    route, why = verdict_route(verdict)
    notice(f"#{issue}: {route} -- {why}")

    if route == "human":
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{issue}/comments",
            "-f",
            f"body=Not routed automatically: {why}\n\n"
            "Label it `fleet:task` or `fleet:material` to dispatch an agent.",
            check=False,
        )
        return 0

    if route == "close":
        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{issue}/comments",
            "-f",
            f"body=Closing: {why}\n\nReopen it if that is wrong.",
            check=False,
        )
        gh(
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/issues/{issue}",
            "-f",
            "state=closed",
            "-f",
            "state_reason=not_planned",
            check=False,
        )
        return 0

    label = label_for(route)
    assert label is not None, route
    gh(
        "api",
        "-X",
        "POST",
        f"repos/{repo}/issues/{issue}/labels",
        "-f",
        f"labels[]={label}",
        check=False,
    )

    # The label alone will not dispatch anything. Events created with
    # `GITHUB_TOKEN` do not start workflow runs, so the `issues: [labeled]`
    # trigger this just satisfied never fires. `workflow_dispatch` is one of
    # the two exceptions, so the run is asked for by name.
    fields = [
        "-f",
        f"agent={agent or 'prose-editor'}",
        "-f",
        f"target=Issue #{issue}: {why}",
    ]
    if not gh("workflow", "run", "fleet.yml", "--repo", repo, *fields, check=False):
        warn(f"labelled #{issue} {label}, but could not dispatch fleet.yml")
    return 0


class NeedsTriage(unittest.TestCase):
    """Does anything on this issue route it anywhere?"""

    def test_nothing_routing_needs_triage(self) -> None:
        for labels in ([], ["bug"], ["fleet:running"], ["fleet:blocked", "hold"]):
            with self.subTest(labels=labels):
                self.assertTrue(needs_triage(labels))

    def test_a_routing_label_is_enough(self) -> None:
        for labels in (["fleet:task"], ["fleet:material"], ["bug", "fleet:task"]):
            with self.subTest(labels=labels):
                self.assertFalse(needs_triage(labels))

    def test_a_state_label_is_not_a_route(self) -> None:
        # The case that made the hole visible: the fleet marks an issue
        # running and nothing ever routes it.
        self.assertEqual(FLEET_STATE & ROUTING, set())


class Marking(unittest.TestCase):
    """The three states, and that they cannot overlap."""

    def calls(self, state: str) -> list[tuple[str, str]]:
        """`(verb, label)` for each API call `mark` would make."""
        seen = []

        def fake(*args: str, **_: object) -> str:
            verb = args[args.index("-X") + 1]
            target = args[args.index("-X") + 2]
            label = target.rsplit("/", 1)[-1] if verb == "DELETE" else args[-1]
            return seen.append((verb, label.removeprefix("labels[]="))) or ""

        with mock.patch(f"{__name__}.gh", side_effect=fake), captured():
            mark("o/r", 7, state)
        return seen

    def test_running_removes_blocked(self) -> None:
        # The pair is the fault: an issue carrying both says two
        # contradictory things and neither of them is checkable.
        self.assertEqual(
            self.calls("running"),
            [("DELETE", "fleet:blocked"), ("POST", "fleet:running")],
        )

    def test_blocked_removes_running(self) -> None:
        self.assertEqual(
            self.calls("blocked"),
            [("DELETE", "fleet:running"), ("POST", "fleet:blocked")],
        )

    def test_done_removes_both_and_adds_nothing(self) -> None:
        self.assertEqual(
            self.calls("done"),
            [("DELETE", "fleet:blocked"), ("DELETE", "fleet:running")],
        )

    def test_every_state_is_a_subset_of_the_fleet_labels(self) -> None:
        for state, labels in MARKS.items():
            with self.subTest(state=state):
                self.assertLessEqual(labels, FLEET_STATE)

    def test_every_fleet_label_is_in_the_roster(self) -> None:
        # Against `.github/labels.toml`, not a fixture: a label the fleet
        # applies and the roster does not declare is one `labels.yml` will
        # delete out from under it.
        roster = (ROOT / ".github" / "labels.toml").read_text(encoding="utf-8")
        for label in sorted(FLEET_STATE):
            self.assertIn(f'"{label}"', roster)


class Sweeping(unittest.TestCase):
    """What a scheduled sweep picks up, and what it leaves."""

    def issues(self, *rows: tuple[int, list[str]]) -> list[dict[str, Any]]:
        return [
            {"number": number, "labels": [{"name": name} for name in labels]}
            for number, labels in rows
        ]

    def test_an_unlabelled_issue_is_stranded(self) -> None:
        self.assertEqual(untriaged(self.issues((84, []))), [84])

    def test_a_routed_issue_is_left_alone(self) -> None:
        self.assertEqual(untriaged(self.issues((7, ["fleet:task"]))), [])

    def test_a_state_label_is_not_a_route(self) -> None:
        # `fleet:running` with no `fleet:task` is an issue the fleet marked
        # and then forgot -- the exact shape the sweep is for.
        self.assertEqual(untriaged(self.issues((9, ["fleet:running"]))), [9])

    def test_a_pull_request_is_not_an_issue(self) -> None:
        # This endpoint returns both, and a pull request is reviewed, not
        # triaged.
        rows = self.issues((1, []))
        rows[0]["pull_request"] = {"url": "..."}
        self.assertEqual(untriaged(rows), [])

    def test_oldest_first_and_capped(self) -> None:
        # Oldest first because the stranded issue is the one this exists for;
        # a cap that took the newest would strand it again.
        rows = self.issues(*[(number, []) for number in range(100, 60, -1)])
        picked = untriaged(rows)
        self.assertEqual(len(picked), SWEEP_CAP)
        self.assertEqual(picked[0], 61)

    def test_nothing_to_do_is_an_empty_list_not_a_guess(self) -> None:
        self.assertEqual(untriaged([]), [])


class Verdicts(unittest.TestCase):
    """A verdict is trusted only when it is well formed."""

    def test_a_good_verdict_routes(self) -> None:
        for route in ("task", "close", "material", "human"):
            with self.subTest(route=route):
                self.assertEqual(
                    verdict_route({"route": route, "why": "because"})[0], route
                )

    def test_every_failure_lands_on_human(self) -> None:
        # Never on `close`. A malformed answer shutting somebody's issue is
        # the worst outcome this program can have.
        for data in (
            {},
            {"route": "delete", "why": "x"},
            {"route": "close"},
            {"route": "task", "why": "   "},
        ):
            with self.subTest(data=data):
                self.assertEqual(verdict_route(data)[0], "human")

    def test_a_reason_is_flattened(self) -> None:
        # It goes into a comment body and a label call, and a stray newline
        # has broken both before.
        self.assertNotIn("\n", verdict_route({"route": "task", "why": "a\nb"})[1])


class Labels(unittest.TestCase):
    def test_only_routes_have_labels(self) -> None:
        self.assertEqual(label_for("material"), "fleet:material")
        self.assertEqual(label_for("task"), "fleet:task")
        self.assertIsNone(label_for("close"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument(
        "--mark",
        choices=sorted(MARKS),
        help="move an issue between the fleet's three states",
    )
    parser.add_argument("--issue", type=int)
    parser.add_argument("--agent", default="")
    parser.add_argument("--verdict")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    arguments = parser.parse_args(argv)

    if not arguments.repo:
        parser.error("a repository is required")

    if arguments.plan:
        # One issue when an event named one, every stranded issue otherwise.
        # The same program answers both so the schedule and the event cannot
        # disagree about what "needs triage" means.
        if arguments.issue:
            wanted = [arguments.issue]
        else:
            wanted = untriaged(paged(f"repos/{arguments.repo}/issues?state=open"))
        output("issues", json.dumps(wanted))
        output("any", "true" if wanted else "false")
        notice(
            f"triaging {len(wanted)} issue(s): {wanted}"
            if wanted
            else "every open issue already routes somewhere"
        )
        return 0

    if not arguments.issue:
        parser.error("--issue is required")

    if arguments.mark:
        return mark(arguments.repo, arguments.issue, arguments.mark)

    if arguments.check:
        issue = api(f"repos/{arguments.repo}/issues/{arguments.issue}") or {}
        labels = [str(label.get("name", "")) for label in issue.get("labels") or []]
        wanted = needs_triage(labels)
        output("triage", "true" if wanted else "false")
        notice(
            f"#{arguments.issue} carries {labels or ['no labels']}; "
            f"{'triaging' if wanted else 'already routed'}"
        )
        return 0

    if arguments.apply:
        if not arguments.verdict or not Path(arguments.verdict).exists():
            # Silence is not a pass, and it is not a close either.
            return apply(
                arguments.repo,
                arguments.issue,
                {"route": "human", "why": "the triage agent left no verdict"},
            )
        with Path(arguments.verdict).open(encoding="utf-8") as handle:
            return apply(
                arguments.repo, arguments.issue, json.load(handle), arguments.agent
            )

    parser.error("one of --check, --apply, --plan or --mark")
    return 2


if __name__ == "__main__":
    sys.exit(main())
