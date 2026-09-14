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
    tools/occasion.py --self-test
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from fleetlib import notice, output

# Label -> trigger. `tools/triage.py` routes unlabelled issues to one of
# these, so the two must agree; `--self-test` checks that they do.
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
) -> Occasion:
    if event == "workflow_dispatch":
        return Occasion(trigger="on-demand", why="dispatched by hand")

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


def self_test() -> int:
    assert decide("workflow_dispatch").trigger == "on-demand"

    assert decide("issues", label="fleet:task", issue="7").trigger == "issue-task"
    assert decide("issues", label="fleet:task", issue="7").issue == "7"
    assert decide("issues", label="fleet:material").trigger == "issue-material"
    # A label the fleet does not act on is quiet, not red: `hold`, `chore` and
    # `fleet:running` all reach this workflow.
    for label in ("hold", "chore", "fleet:running", ""):
        got = decide("issues", label=label)
        assert got.trigger == "" and got.problem == "", label

    assert decide("schedule", cron="0 7 * * 1").trigger == "weekly-garden"
    assert decide("schedule", cron="0 8 1 * *").trigger == "monthly-prose"
    # An unmapped cron is a schedule added without a brief. Loud.
    assert decide("schedule", cron="0 0 * * *").problem

    # Notes beat chapters when a push carries both.
    both = ("notes/2026-01-01.md", "book/chapters/01-x.typ")
    assert decide("push", changed=both).trigger == "notes-arrived"
    assert decide("push", changed=both).changed == "notes/2026-01-01.md"
    # The generated index is not new material, and neither is a raw capture.
    assert decide("push", changed=("notes/index.md",)).trigger == ""
    assert decide("push", changed=("notes/raw/x.html",)).trigger == ""
    assert (
        decide("push", changed=("notes/index.md", "book/chapters/a.typ")).trigger
        == "chapters-changed"
    )
    assert decide("push", changed=("README.md",)).trigger == ""

    assert decide("deployment_status").problem

    # Every trigger this can produce must have a brief, and every label
    # `triage.py` applies must route here. Two files, one agreement.
    import triage  # noqa: PLC0415 - the check is the point

    assert set(triage.ROUTING) == set(BY_LABEL), (triage.ROUTING, BY_LABEL)

    fleet_dir = Path(__file__).resolve().parent.parent / ".claude" / "fleet"
    briefs = {brief.stem for brief in fleet_dir.glob("*.md")}
    produced = {
        "on-demand",
        *BY_LABEL.values(),
        *BY_CRON.values(),
        "notes-arrived",
        "chapters-changed",
    }
    missing = produced - briefs
    assert not missing, f"triggers with no brief: {missing}"

    print(
        f"occasion: {len(produced)} triggers, all with briefs, labels agree with triage"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--event", default="")
    parser.add_argument("--label", default="")
    parser.add_argument("--cron", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--changed", default="", help="newline separated paths")
    parser.add_argument("--before", default="", help="a push's previous sha")
    parser.add_argument("--sha", default="", help="a push's new sha")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()

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
    )
    if got.problem:
        print(f"::error::{got.problem}")
        return 1
    output("trigger", got.trigger)
    output("changed", got.changed)
    output("issue", got.issue)
    notice(f"occasion: {got.trigger or 'none'} -- {got.why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
