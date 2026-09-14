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

Usage:
    tools/triage.py --check --issue 7            # is triage needed?
    tools/triage.py --apply --issue 7 --verdict /tmp/triage.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unittest
from pathlib import Path
from typing import Any

from fleetlib import api, gh, notice, output, warn

# The labels that route. `fleet.yml`'s occasion router maps exactly these two
# to a trigger; anything else it prints a notice about and exits 0.
ROUTING = {"fleet:material", "fleet:task"}

# Applied by the fleet, not by a human, and not a route on their own.
FLEET_STATE = {"fleet:running", "fleet:blocked"}

# What a verdict may ask for. Anything else is a malformed verdict, which is
# treated as "leave it for a human" rather than guessed at.
ROUTES = {"material", "task", "close", "human"}


def needs_triage(labels: list[str]) -> bool:
    """True when nothing on this issue will route it anywhere.

    A `fleet:` state label is not a route: `fleet:running` on an issue with no
    `fleet:task` is an issue the fleet marked and then forgot.
    """
    return not (set(labels) & ROUTING)


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
    parser.add_argument("--issue", type=int)
    parser.add_argument("--agent", default="")
    parser.add_argument("--verdict")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    arguments = parser.parse_args(argv)

    if not (arguments.issue and arguments.repo):
        parser.error("--issue and a repository are required")

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

    parser.error("one of --check or --apply")
    return 2


if __name__ == "__main__":
    sys.exit(main())
