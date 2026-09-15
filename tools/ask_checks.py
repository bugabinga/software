#!/usr/bin/env python3
"""Start the checks a `GITHUB_TOKEN` push will not start.

"When you use the repository's GITHUB_TOKEN to perform tasks, events
triggered by the GITHUB_TOKEN ... will not create a new workflow run. ...
with the exception of workflow_dispatch and repository_dispatch". So a
branch pushed by a workflow arrives with no CI on it, and
`agent-branches.yml` -- which waits for CI to complete before deciding
anything -- never wakes for it. The fleet's first real delivery sat
unchecked and unmergeable for exactly this reason.

`workflow_dispatch` is the exception the token may still raise, so asking
explicitly is the way through.

A program on the third copy. `fleet.yml` and `fleet-respond.yml` each had
this as shell, and `notes-reindex.yml` did not have it at all -- it commits
a rebuilt `notes/index.md` onto the branch the Cloudflare inbox pushed, with
the workflow token, and then stops. Every note filed through the inbox would
have landed on a head no CI ever looked at, with the merge decision waiting
on a check that could not arrive. That path had never run, so nothing said
so.

Never fails. A branch that is pushed but unchecked is worth a warning and a
sentence saying what to do; it is not worth failing the run that pushed it,
which would leave the same branch in the same state with a red run on top.

Usage:
    tools/ask_checks.py --ref agent/note-2026-09-15-a ci.yml
    tools/ask_checks.py --ref "$BRANCH" ci.yml fleet-review.yml=pr:42
"""

from __future__ import annotations

import argparse
import sys
import unittest
from dataclasses import dataclass

from fleetlib import gh, notice, warn


@dataclass(frozen=True)
class Ask:
    """One workflow to start, and the inputs it needs."""

    workflow: str
    inputs: tuple[tuple[str, str], ...] = ()

    def args(self, ref: str) -> list[str]:
        flags: list[str] = []
        for name, value in self.inputs:
            flags += ["-f", f"{name}={value}"]
        return ["workflow", "run", self.workflow, "--ref", ref, *flags]


def parse(spec: str) -> Ask:
    """`ci.yml`, or `fleet-review.yml=pr:42` for one that takes inputs.

    `ci.yml` takes no inputs and needs none: it checks a branch.
    `fleet-review.yml` reviews a pull request, which a dispatch has to name,
    because `workflow_dispatch` carries no pull request.
    """
    workflow, _, rest = spec.partition("=")
    if not workflow.endswith((".yml", ".yaml")):
        sys.exit(f"{spec!r}: a workflow file name, not {workflow!r}")
    inputs = []
    for pair in filter(None, rest.split(",")):
        name, sep, value = pair.partition(":")
        if not sep or not name:
            sys.exit(f"{spec!r}: an input is `name:value`, not {pair!r}")
        inputs.append((name, value))
    return Ask(workflow, tuple(inputs))


def ask(ref: str, wanted: list[Ask]) -> int:
    """Dispatch each. Always 0; see the module docstring."""
    for one in wanted:
        if gh(*one.args(ref), check=False) is None:
            warn(
                f"{ref} is pushed but {one.workflow} could not be started on "
                "it, so nothing downstream will pick it up. Start it by hand "
                "from the Actions tab, or re-run this step."
            )
        else:
            notice(f"dispatched {one.workflow} on {ref}")
    return 0


class Parsing(unittest.TestCase):
    """The spec a workflow writes in one `run:` line."""

    def test_a_bare_workflow(self) -> None:
        self.assertEqual(parse("ci.yml"), Ask("ci.yml"))

    def test_one_input(self) -> None:
        self.assertEqual(
            parse("fleet-review.yml=pr:42"), Ask("fleet-review.yml", (("pr", "42"),))
        )

    def test_two_inputs(self) -> None:
        self.assertEqual(parse("w.yml=a:1,b:2").inputs, (("a", "1"), ("b", "2")))

    def test_a_value_may_contain_a_colon(self) -> None:
        # A branch name or a URL as an input value. `partition` splits once.
        self.assertEqual(
            parse("w.yml=url:https://x/y").inputs, (("url", "https://x/y"),)
        )


class Arguments(unittest.TestCase):
    """What reaches `gh`. Never a shell string."""

    def test_no_inputs(self) -> None:
        self.assertEqual(
            parse("ci.yml").args("agent/x"),
            ["workflow", "run", "ci.yml", "--ref", "agent/x"],
        )

    def test_inputs_become_flags(self) -> None:
        self.assertEqual(
            parse("fleet-review.yml=pr:42").args("b")[-2:], ["-f", "pr=42"]
        )

    def test_a_ref_is_an_argument_not_a_word(self) -> None:
        # The reason this is a program. A branch named `; rm -rf /` is one
        # argument here and was a statement in the shell this replaced.
        args = parse("ci.yml").args("; rm -rf /")
        self.assertIn("; rm -rf /", args)
        self.assertEqual(len(args), 5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", required=True, help="the branch to dispatch on")
    parser.add_argument(
        "workflows", nargs="+", help="ci.yml, or fleet-review.yml=pr:42"
    )
    arguments = parser.parse_args(argv)
    return ask(arguments.ref, [parse(spec) for spec in arguments.workflows])


if __name__ == "__main__":
    sys.exit(main())
