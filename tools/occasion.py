#!/usr/bin/env python3
"""Which occasion woke `fleet.yml`, and what to tell the brief builder.

Sixty lines of nested `case` in a `run:` block, deciding which of six agents
runs. Two of its arms had already been wrong in ways only a live run showed:
a label it did not recognise exited 0 with a notice nobody reads, and a push
touching both `notes/` and `book/chapters/` had to pick one.

The mapping is data. `decide` is a pure function over it, and the pairs below
are the whole of the routing table -- adding an occasion is a row and a brief,
not another arm.

Usage:
    tools/occasion.py --event issues --label fleet:task --issue 7
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

from fleetlib import gh, notice, output

ROOT = Path(__file__).resolve().parent.parent

# Label -> trigger. `tools/triage.py` routes unlabelled issues to one of
# these, so the two must agree; `AgreesWithTheTree` checks that.
BY_LABEL = {
    "fleet:material": "issue-material",
    "fleet:task": "issue-task",
}

# Cron -> trigger, exactly as written in the workflow's `schedule:`. A cron
# that reaches here unmapped is a schedule somebody added without a brief,
# which is a failure and not a shrug.
BY_CRON = {
    "0 7 * * 1": "weekly-garden",
    "0 8 1 * *": "monthly-prose",
}


@dataclass(frozen=True)
class Occasion:
    trigger: str = ""
    changed: str = ""
    issue: str = ""
    problem: str = ""  # non-empty means exit non-zero
    why: str = ""


def decide(
    event: str,
    *,
    label: str = "",
    cron: str = "",
    issue: str = "",
    changed: tuple[str, ...] = (),
    relayed: str = "",
    relayed_changed: str = "",
) -> Occasion:
    if event == "workflow_dispatch":
        return Occasion(trigger="on-demand", why="dispatched by hand")

    if event == "repository_dispatch":
        # A push relayed. `claude-code-action` refuses to run on `push` --
        # `src/github/context.ts` throws "Unsupported event type" for
        # anything outside issues, pull requests, the two dispatches,
        # `schedule` and `workflow_run` -- so every push that touched
        # `notes/` or `book/chapters/` fired this workflow and died after
        # resolving its credential. The whole "a note arrives, the fleet
        # reacts" path had never worked. `repository_dispatch` is the
        # carrier because the action accepts it, because `GITHUB_TOKEN` can
        # raise it (it is one of the two documented exceptions to the rule
        # that a token's events start no runs), and because its
        # `client_payload` carries the occasion the push already decided.
        if not relayed:
            return Occasion(problem="a relayed push carried no trigger")
        return Occasion(trigger=relayed, changed=relayed_changed, why="a push, relayed")

    if event == "issues":
        trigger = BY_LABEL.get(label)
        if trigger is None:
            # Not a failure: every label on the repository reaches here, and
            # `hold` or `chore` arriving is normal. `triage.yml` is what
            # answers an issue nothing routes.
            return Occasion(why=f"label {label!r} is not one the fleet acts on")
        return Occasion(trigger=trigger, issue=issue, why=f"label {label}")

    if event == "schedule":
        trigger = BY_CRON.get(cron)
        if trigger is None:
            return Occasion(problem=f"no trigger mapped to cron {cron!r}")
        return Occasion(trigger=trigger, why=f"cron {cron}")

    if event == "push":
        # Notes win when a push touches both. New material can change what
        # the chapters should say in the first place, so reconciling the
        # outline comes before copyediting it.
        notes = [
            p
            for p in changed
            if p.startswith("notes/") and p != "notes/index.md" and "/raw/" not in p
        ]
        if notes:
            return Occasion(
                trigger="notes-arrived", changed="\n".join(notes), why="notes arrived"
            )
        chapters = [p for p in changed if p.startswith("book/chapters/")]
        if chapters:
            return Occasion(
                trigger="chapters-changed",
                changed="\n".join(chapters),
                why="chapters changed",
            )
        return Occasion(why="nothing the fleet cares about changed")

    return Occasion(problem=f"no routing for event {event!r}")


class Routing(unittest.TestCase):
    """Which occasion woke the workflow, from the event it carries."""

    def test_a_dispatch_is_on_demand(self) -> None:
        self.assertEqual(decide("workflow_dispatch").trigger, "on-demand")

    def test_a_routing_label_routes(self) -> None:
        for label, want in BY_LABEL.items():
            with self.subTest(label=label):
                self.assertEqual(decide("issues", label=label, issue="7").trigger, want)
        self.assertEqual(decide("issues", label="fleet:task", issue="7").issue, "7")

    def test_any_other_label_is_quiet_not_red(self) -> None:
        # `hold`, `chore` and `fleet:running` all reach this workflow, and
        # `triage.yml` is what answers an issue nothing routes.
        for label in ("hold", "chore", "fleet:running", ""):
            with self.subTest(label=label):
                got = decide("issues", label=label)
                self.assertEqual(got.trigger, "")
                self.assertEqual(got.problem, "")

    def test_a_mapped_cron_routes(self) -> None:
        for cron, want in BY_CRON.items():
            with self.subTest(cron=cron):
                self.assertEqual(decide("schedule", cron=cron).trigger, want)

    def test_an_unmapped_cron_is_loud(self) -> None:
        # A schedule somebody added without a brief is a failure, not a shrug.
        self.assertTrue(decide("schedule", cron="0 0 * * *").problem)
        self.assertTrue(decide("deployment_status").problem)


class Pushes(unittest.TestCase):
    """What a push changed, and which beat wins when it changed both."""

    def test_notes_beat_chapters(self) -> None:
        both = ("notes/2026-01-01.md", "book/chapters/01-x.typ")
        self.assertEqual(decide("push", changed=both).trigger, "notes-arrived")
        self.assertEqual(decide("push", changed=both).changed, "notes/2026-01-01.md")

    def test_generated_and_raw_are_not_material(self) -> None:
        for path in ("notes/index.md", "notes/raw/x.html"):
            with self.subTest(path=path):
                self.assertEqual(decide("push", changed=(path,)).trigger, "")

    def test_chapters_alone(self) -> None:
        self.assertEqual(
            decide("push", changed=("notes/index.md", "book/chapters/a.typ")).trigger,
            "chapters-changed",
        )

    def test_anything_else_is_nothing(self) -> None:
        self.assertEqual(decide("push", changed=("README.md",)).trigger, "")


class AgreesWithTheTree(unittest.TestCase):
    """Two agreements no single file can hold on its own."""

    def test_every_trigger_has_a_brief(self) -> None:
        fleet_dir = Path(__file__).resolve().parent.parent / ".claude" / "fleet"
        briefs = {brief.stem for brief in fleet_dir.glob("*.md")}
        produced = {
            "on-demand",
            *BY_LABEL.values(),
            *BY_CRON.values(),
            "notes-arrived",
            "chapters-changed",
        }
        self.assertEqual(produced - briefs, set())

    def test_labels_match_triage(self) -> None:
        # Drift here is an issue that triage labels and no brief answers.
        import triage  # noqa: PLC0415 - the cross-check is the point

        self.assertEqual(set(triage.ROUTING), set(BY_LABEL))


# `client_payload` is capped at 64KB and this is the only field that can grow.
# A push that rewrote three hundred notes is a push whose brief should say
# "a lot of notes" rather than list them; the cap is where that becomes true
# rather than where the API starts refusing.
RELAY_PATHS = 50


def relay(repo: str, occasion: Occasion) -> int:
    """Raise the `repository_dispatch` that carries this push's occasion.

    The dispatch runs the default branch's copy of the workflow, which is
    where this push just landed, so there is no version skew to reason about.
    """
    if not occasion.trigger:
        notice(f"nothing to relay: {occasion.why}")
        return 0
    paths = occasion.changed.splitlines()
    kept = paths[:RELAY_PATHS]
    payload = {
        "trigger": occasion.trigger,
        "changed": "\n".join(kept),
        "truncated": len(paths) - len(kept),
    }
    gh(
        "api",
        "-X",
        "POST",
        f"repos/{repo}/dispatches",
        "-f",
        "event_type=fleet",
        "--raw-field",
        f"client_payload={json.dumps(payload)}",
        check=False,
    )
    notice(f"relayed {occasion.trigger} with {len(kept)} path(s)")
    return 0


class Relayed(unittest.TestCase):
    """A push, carried on the one event the action will run on."""

    def test_the_trigger_survives_the_trip(self) -> None:
        got = decide(
            "repository_dispatch",
            relayed="notes-arrived",
            relayed_changed="notes/a.md\nnotes/b.md",
        )
        self.assertEqual(got.trigger, "notes-arrived")
        self.assertEqual(got.changed, "notes/a.md\nnotes/b.md")

    def test_an_empty_payload_is_an_error_not_a_silent_pass(self) -> None:
        # A relay that lost its payload must be a red run. Returning "no
        # occasion" would look exactly like a push that touched nothing, and
        # this workflow's whole failure mode was looking like something else.
        self.assertTrue(decide("repository_dispatch").problem)

    def test_a_push_still_decides_the_occasion(self) -> None:
        # The relay does not move the decision; it only carries it. A push
        # event reaching `decide` answers the same as it always did.
        self.assertEqual(
            decide("push", changed=("notes/a.md",)).trigger, "notes-arrived"
        )

    def test_a_push_decides_and_the_relay_carries_the_same_answer(self) -> None:
        # The relay must not become a second router. What `push` decides is
        # what `repository_dispatch` reports; `AgreesWithTheTree` is what
        # checks that each of those has a brief.
        for paths in (("notes/a.md",), ("book/chapters/01-x.typ",)):
            with self.subTest(paths=paths):
                pushed = decide("push", changed=paths)
                carried = decide(
                    "repository_dispatch",
                    relayed=pushed.trigger,
                    relayed_changed=pushed.changed,
                )
                self.assertEqual(carried.trigger, pushed.trigger)
                self.assertEqual(carried.changed, pushed.changed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default="")
    parser.add_argument("--label", default="")
    parser.add_argument("--cron", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--changed", default="", help="newline separated paths")
    parser.add_argument("--before", default="", help="a push's previous sha")
    parser.add_argument("--sha", default="", help="a push's new sha")
    parser.add_argument(
        "--trigger", default="", help="a relayed push's trigger, from client_payload"
    )
    parser.add_argument(
        "--relay",
        action="store_true",
        help="decide, then raise a repository_dispatch carrying the answer",
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    arguments = parser.parse_args(argv)

    changed = tuple(p for p in arguments.changed.splitlines() if p.strip())
    if not changed and arguments.before and arguments.sha:
        # The workflow used to run this `git diff` itself and hand over the
        # result. Asking here keeps the whole decision in one testable place,
        # and the paths never pass through a shell.
        done = subprocess.run(  # noqa: PLW1510 - an empty diff is not an error
            ["git", "diff", "--name-only", arguments.before, arguments.sha],
            capture_output=True,
            text=True,
            timeout=60,
        )
        changed = tuple(p for p in done.stdout.splitlines() if p.strip())

    got = decide(
        arguments.event,
        label=arguments.label,
        cron=arguments.cron,
        issue=arguments.issue,
        changed=changed,
        relayed=arguments.trigger,
        relayed_changed=arguments.changed,
    )
    if got.problem:
        print(f"::error::{got.problem}")
        return 1

    if arguments.relay:
        return relay(arguments.repo, got)

    output("trigger", got.trigger)
    output("changed", got.changed)
    output("issue", got.issue)
    notice(f"occasion: {got.trigger or 'none'} -- {got.why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
