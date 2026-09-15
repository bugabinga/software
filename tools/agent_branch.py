#!/usr/bin/env python3
"""What a green agent branch has earned: merge it, raise it, or leave it.

This was 185 lines of shell inside `agent-branches.yml`, which is the one
workflow that decides what reaches `main` without a human. A `run:` block can
only be tested by pushing, and this one had already been wrong twice in ways
nothing caught: it grepped for a check named `Build` after the job was renamed
`CI`, so it merged nothing at all for weeks; and it tested for `diverged`,
which is the normal state of any branch created before `main` moved on, so it
skipped the fleet's first real delivery.

`decide` is a pure function of what the API answered. Everything that talks to
GitHub is in `main`, and everything worth being wrong about is in `decide`,
in this file's tests.

Usage:
    tools/agent_branch.py --branch agent/x --sha abc123
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unittest
from dataclasses import dataclass, field, replace
from typing import Any

import ask_checks
from fleetlib import api, gh, notice, paged, warn

# The one thing the fleet does not merge for itself. A change under these
# prefixes is the automation deciding its own future, and an agent that can
# rewrite its own brief or its own merge rule is supervised by nothing. The
# book is deliberately absent: the author delegated it to the fleet.
PROTECTED = re.compile(r"^(\.github/|\.claude/)")

# A check that has concluded acceptably. `neutral` and `skipped` are green:
# a job that correctly decided it had nothing to do has not failed.
SETTLED = {"success", "neutral", "skipped"}

# This workflow's own checks, which cannot be waited on from inside itself.
GREEN_CI = (("CI", "completed", "success"),)

OWN_CHECKS = {"Merge green chores", "Open the pull request", "Agent branches"}


@dataclass(frozen=True)
class Branch:
    """Everything the decision reads, and nothing else."""

    name: str
    ahead_by: int
    files: tuple[str, ...] = ()
    subject: str = ""
    checks: tuple[tuple[str, str, str], ...] = ()  # (name, status, conclusion)
    pull: int | None = None
    held: bool = False
    merged_before: bool = False
    mergeable_state: str = ""


@dataclass(frozen=True)
class Decision:
    action: str  # leave | wait | raise | merge
    why: str
    fields: dict[str, Any] = field(default_factory=dict)


def decide(branch: Branch) -> Decision:
    """Merge it, raise it for the author, wait for CI, or leave it alone."""
    if branch.held:
        return Decision("leave", f"#{branch.pull} is labelled hold")
    if branch.ahead_by == 0:
        return Decision("leave", f"{branch.name} is not ahead of main")
    if branch.merged_before:
        return Decision(
            "leave", f"{branch.name} was already merged through a pull request"
        )
    if "[hold]" in branch.subject:
        return Decision("leave", f"{branch.name} is marked [hold]")
    if not branch.files:
        return Decision("leave", f"{branch.name} does not differ from main")

    # Every check on this exact commit concluded well -- and "every" has to
    # mean at least one. Asking whether any check is *not* green answers yes
    # for a commit with no checks at all, and a branch pushed with the
    # workflow token gets no runs whatsoever, because `GITHUB_TOKEN` pushes
    # do not trigger workflows. `agent/typst-0.15.1` had exactly zero check
    # runs; nothing merged it only because it fell foul of a later rule,
    # which is luck rather than a safeguard. So `CI` must be present and
    # successful by name.
    others = [c for c in branch.checks if c[0] not in OWN_CHECKS]
    ci = [c for c in others if c[0] == "CI"]
    if not any(status == "completed" for _, status, _ in ci):
        return Decision("wait", f"CI has not reported on {branch.name} yet")
    if not any(conclusion == "success" for _, _, conclusion in ci):
        return Decision("leave", f"{branch.name} has no successful CI check")
    ungreen = [
        name
        for name, status, con in others
        if status != "completed" or con not in SETTLED
    ]
    if ungreen:
        return Decision(
            "leave", f"{branch.name} has checks that are not green", {"checks": ungreen}
        )

    protected = [f for f in branch.files if PROTECTED.match(f)]
    if protected:
        if branch.pull is not None:
            return Decision(
                "leave",
                f"#{branch.pull} changes the automation itself; "
                "the pull request is where the author reads it",
            )
        return Decision(
            "raise",
            f"{branch.name} changes the automation itself",
            {"protected": protected},
        )

    if branch.pull is None:
        return Decision(
            "leave", f"{branch.name} is green but has no pull request to merge"
        )
    if branch.mergeable_state == "dirty":
        return Decision("leave", f"#{branch.pull} conflicts with main")
    if branch.mergeable_state == "behind":
        # `strict = true` on the Main ruleset: a branch behind `main` cannot
        # land until it is updated. `repo.toml` turns on `allow_update_branch`
        # and calls it "the button that does it" -- and nothing pressed it.
        # `main` moves several times an hour while the fleet is being built,
        # so every branch the fleet pushes is behind within minutes, and the
        # merge was refused by the ruleset with `act` reporting only "could
        # not be merged; leaving it". Every delivery would have stalled there.
        return Decision("update", f"#{branch.pull} is behind main")
    return Decision("merge", f"#{branch.pull} is green and touches nothing protected")


def observe(repo: str, branch: str, sha: str, attempts: int = 12) -> Branch:
    """Ask GitHub the questions `decide` answers from.

    The check runs are polled: this job starts the instant CI reports
    completion and they are not always visible by then. A minute of asking,
    then `decide` gets what there is and says `wait`.
    """
    owner = repo.split("/", 1)[0]
    pulls = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=all") or []
    open_pulls = [p for p in pulls if p.get("state") == "open"]
    number = open_pulls[0]["number"] if open_pulls else None

    held = False
    mergeable = ""
    if number is not None:
        labels = api(f"repos/{repo}/issues/{number}/labels") or []
        held = any(label.get("name") == "hold" for label in labels)
        mergeable = (api(f"repos/{repo}/pulls/{number}") or {}).get(
            "mergeable_state", ""
        )

    comparison = api(f"repos/{repo}/compare/main...{branch}") or {}
    commits = comparison.get("commits") or []
    subject = (
        (commits[-1]["commit"]["message"].splitlines() or [""])[0] if commits else ""
    )

    checks: tuple[tuple[str, str, str], ...] = ()
    for attempt in range(1, attempts + 1):
        runs = (api(f"repos/{repo}/commits/{sha}/check-runs") or {}).get(
            "check_runs"
        ) or []
        checks = tuple(
            (r.get("name", ""), r.get("status", ""), r.get("conclusion") or "pending")
            for r in runs
        )
        if any(n == "CI" and s == "completed" for n, s, _ in checks):
            break
        print(f"waiting for checks on {sha} (attempt {attempt})", file=sys.stderr)
        time.sleep(5)

    return Branch(
        name=branch,
        ahead_by=int(comparison.get("ahead_by") or 0),
        files=tuple(f["filename"] for f in comparison.get("files") or []),
        subject=subject,
        checks=checks,
        pull=number,
        held=held,
        merged_before=any(p.get("merged_at") for p in pulls),
        mergeable_state=mergeable,
    )


def issue_body(
    repo: str, branch: str, server: str, subject: str, files: tuple[str, ...]
) -> str:
    compare = f"{server}/{repo}/compare/main...{branch}"
    rows = "\n".join(f"| `{name}` |" for name in files)
    return (
        f"`{branch}` is green. It changes the automation itself, which is the "
        "one thing that is not merged automatically.\n\n"
        f"**[Diff]({compare})** · **[Open a pull request]({compare}?expand=1)**\n\n"
        f"> {subject}\n\n"
        "| Files |\n| --- |\n"
        f"{rows}\n"
    )


def act(repo: str, branch: Branch, decision: Decision, sha: str, server: str) -> int:
    notice(f"{branch.name}: {decision.action} -- {decision.why}")
    if decision.action in {"leave", "wait"}:
        return 0

    if decision.action == "raise":
        title = f"Ready to review: {branch.name}"
        body = issue_body(repo, branch.name, server, branch.subject, branch.files)
        open_issues = paged(f"repos/{repo}/issues?state=open")
        existing = next(
            (i["number"] for i in open_issues if i.get("title") == title), None
        )
        if existing is not None:
            gh(
                "api",
                "-X",
                "POST",
                f"repos/{repo}/issues/{existing}/comments",
                "-f",
                f"body={body}",
                check=False,
            )
            notice(f"updated issue #{existing}")
        else:
            made = (
                api(
                    f"repos/{repo}/issues",
                    "-X",
                    "POST",
                    "-f",
                    f"title={title}",
                    "-f",
                    f"body={body}",
                )
                or {}
            )
            notice(f"opened issue #{made.get('number')}")
        return 0

    if decision.action == "update":
        if (
            gh(
                "api",
                "-X",
                "PUT",
                f"repos/{repo}/pulls/{branch.pull}/update-branch",
                check=False,
            )
            is None
        ):
            notice(f"#{branch.pull} could not be updated; leaving it")
            return 0
        # The update is a push by the workflow token, so it starts nothing.
        # Without this the branch is up to date and stuck: the new head has
        # no CI, and `decide` waits for a check that cannot arrive.
        ask_checks.ask(branch.name, [ask_checks.Ask("ci.yml")])
        notice(f"updated #{branch.pull} from main; CI asked for on the new head")
        return 0

    merged = gh(
        "api",
        "-X",
        "PUT",
        f"repos/{repo}/pulls/{branch.pull}/merge",
        "-f",
        "merge_method=squash",
        "-f",
        f"sha={sha}",
        check=False,
    )
    if not merged:
        notice(f"#{branch.pull} could not be merged; leaving it")
        return 0
    notice(f"merged #{branch.pull}")
    gh("api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch.name}", check=False)
    return 0


def pr_body(branch: str, commits: tuple[str, ...], files: tuple[str, ...]) -> str:
    """The body for a pull request the fleet could not open for itself."""
    rows = "\n".join(f"| `{name}` |" for name in files)
    log = "\n".join(f"- {subject}" for subject in commits)
    return (
        f"Opened for `{branch}`, which the fleet pushed and cannot open a pull "
        "request for itself. The commit messages carry the reasoning; nobody "
        "wrote the story of this change, because no human opened it.\n\n"
        f"**Commits**\n\n{log}\n\n"
        f"| Files |\n| --- |\n{rows}\n"
    )


def open_pull(repo: str, branch: str) -> int:
    """Open one for a branch the fleet pushed, if this repository allows it."""
    owner = repo.split("/", 1)[0]
    existing = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=open") or []
    if existing:
        notice(f"#{existing[0]['number']} already tracks {branch}")
        return 0

    comparison = api(f"repos/{repo}/compare/main...{branch}") or {}
    commits = tuple(
        c["commit"]["message"].splitlines()[0] for c in comparison.get("commits") or []
    )
    files = tuple(f["filename"] for f in comparison.get("files") or [])
    subject = commits[-1] if commits else branch

    made = api(
        f"repos/{repo}/pulls",
        "-X",
        "POST",
        "-f",
        f"title={subject}",
        "-f",
        f"head={branch}",
        "-f",
        "base=main",
        "-f",
        f"body={pr_body(branch, commits, files)}",
        check=False,
    )
    if not isinstance(made, dict) or "number" not in made:
        # Not a failure. `decide` handles a branch with no pull request; one
        # is the nicer presentation, not the mechanism. A repository with
        # Actions barred from opening them answers exactly here.
        notice(
            f"no pull request was opened for {branch}; it will be handled without one"
        )
        return 0

    number = made["number"]
    notice(f"opened #{number} for {branch}")
    # `Fleet review` is required, and a pull request opened with the workflow
    # token starts no runs, so the verdict would never report and the branch
    # could never merge. Asked for by name.
    if not gh(
        "workflow",
        "run",
        "fleet-review.yml",
        "--repo",
        repo,
        "--ref",
        branch,
        "-f",
        f"pr={number}",
        check=False,
    ):
        warn(
            f"#{number} is open but Fleet review could not be started on it. "
            f"Run that workflow from the Actions tab with pr={number}."
        )
    return 0


# Branches this may delete. Nothing else, ever: a prefix is the whole of the
# safety argument, and `main`, `gh-pages` and `fleet-log` are all one typo
# away from a rule that matched on "has a merged pull request" alone.
DISPOSABLE = re.compile(r"^(agent|maintenance)/")


def prunable(branch: str, pulls: list[dict[str, Any]]) -> str:
    """Why this branch can be deleted, or "" for leave it.

    `delete_branch_on_merge` covers a branch merged through the web UI, and
    `act` deletes the ones it merges itself. Neither covered the ten that were
    merged before that setting was applied, and neither covers a branch merged
    by any route nobody has thought of yet. This is the sweep that does.

    An open pull request is the veto even when a merged one also exists: a
    branch reopened for a follow-up is live work, and the merged ancestor says
    nothing about it.
    """
    if not DISPOSABLE.match(branch):
        return ""
    if any(pull.get("state") == "open" for pull in pulls):
        return ""
    merged = next((p for p in pulls if p.get("merged_at")), None)
    return f"merged in #{merged['number']}" if merged else ""


def prune(repo: str) -> int:
    """Delete every disposable branch whose work is already on `main`."""
    owner = repo.split("/", 1)[0]
    gone = 0
    for ref in paged(f"repos/{repo}/branches"):
        branch = str(ref.get("name", ""))
        if not DISPOSABLE.match(branch):
            continue
        pulls = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=all") or []
        why = prunable(branch, pulls)
        if not why:
            continue
        gh(
            "api",
            "-X",
            "DELETE",
            f"repos/{repo}/git/refs/heads/{branch}",
            check=False,
        )
        notice(f"deleted {branch}: {why}")
        gone += 1
    if not gone:
        notice("no merged agent branches left behind")
    return 0


def close_finished(repo: str) -> int:
    """Close the notices that stood in for a pull request, once one exists."""
    owner = repo.split("/", 1)[0]
    tracked = re.compile(r"^(Ready to review|Green and unmerged): (?P<branch>.+)$")
    closed = 0
    for issue in paged(f"repos/{repo}/issues?state=open"):
        if issue.get("pull_request"):
            continue
        found = tracked.match(str(issue.get("title", "")))
        if not found:
            continue
        branch = found["branch"]

        if api(f"repos/{repo}/git/ref/heads/{branch}", check=False) is None:
            why = f"`{branch}` no longer exists."
        else:
            pulls = api(f"repos/{repo}/pulls?head={owner}:{branch}&state=all") or []
            merged = next((p for p in pulls if p.get("merged_at")), None)
            open_one = next((p for p in pulls if p.get("state") == "open"), None)
            if merged:
                why = f"`{branch}` was merged in #{merged['number']}."
            elif open_one:
                why = f"#{open_one['number']} now tracks `{branch}`."
            else:
                continue

        gh(
            "api",
            "-X",
            "POST",
            f"repos/{repo}/issues/{issue['number']}/comments",
            "-f",
            f"body={why} Closing: it tracked one branch and that branch is done.",
            check=False,
        )
        gh(
            "api",
            "-X",
            "PATCH",
            f"repos/{repo}/issues/{issue['number']}",
            "-f",
            "state=closed",
            "-f",
            "state_reason=completed",
            check=False,
        )
        closed += 1
    notice(f"closed {closed} finished tracking issue(s)")
    return 0


class Behind(unittest.TestCase):
    """A branch behind `main` is updated, not abandoned."""

    def branch(self, state: str) -> Branch:
        return Branch(
            name="agent/x",
            ahead_by=1,
            files=("book/chapters/01-x.typ",),
            subject="a change",
            checks=GREEN_CI,
            pull=7,
            mergeable_state=state,
        )

    def test_behind_asks_for_an_update(self) -> None:
        # The Main ruleset is `strict = true`, so this merge is refused by
        # GitHub. `repo.toml` turns on `allow_update_branch` for exactly this
        # and nothing pressed it: every fleet delivery would have stalled
        # with "could not be merged; leaving it".
        self.assertEqual(decide(self.branch("behind")).action, "update")

    def test_clean_still_merges(self) -> None:
        self.assertEqual(decide(self.branch("clean")).action, "merge")

    def test_a_conflict_is_still_left_alone(self) -> None:
        # Updating a branch that conflicts would leave conflict markers in
        # the tree. That one is the author's.
        self.assertEqual(decide(self.branch("dirty")).action, "leave")

    def test_ungreen_wins_over_behind(self) -> None:
        # Order matters: updating a red branch spends a CI run to rediscover
        # that it is red.
        behind = Branch(
            name="agent/x",
            ahead_by=1,
            files=("book/chapters/01-x.typ",),
            checks=(*GREEN_CI, ("Lint", "completed", "failure")),
            pull=7,
            mergeable_state="behind",
        )
        self.assertEqual(decide(behind).action, "leave")


class Pruning(unittest.TestCase):
    """Which branches the sweep may delete. The prefix is the safety."""

    def pulls(self, *rows: tuple[int, str, bool]) -> list[dict[str, Any]]:
        return [
            {"number": n, "state": state, "merged_at": "2026-01-01" if merged else None}
            for n, state, merged in rows
        ]

    def test_a_merged_agent_branch_goes(self) -> None:
        why = prunable("agent/pages-bootstrap", self.pulls((7, "closed", True)))
        self.assertIn("#7", why)

    def test_maintenance_too(self) -> None:
        self.assertTrue(
            prunable("maintenance/typst-0.15.1", self.pulls((9, "closed", True)))
        )

    def test_main_is_never_disposable(self) -> None:
        # Not a hypothetical: "has a merged pull request" is true of `main`
        # and of `fleet-log`, and a rule written on that alone deletes them.
        for branch in ("main", "gh-pages", "fleet-log", "claude/something"):
            with self.subTest(branch=branch):
                self.assertEqual(prunable(branch, self.pulls((7, "closed", True))), "")

    def test_an_open_pull_request_vetoes_a_merged_one(self) -> None:
        # A branch reopened for a follow-up is live work; the merged ancestor
        # says nothing about it.
        self.assertEqual(
            prunable("agent/x", self.pulls((7, "closed", True), (9, "open", False))), ""
        )

    def test_an_unmerged_branch_stays(self) -> None:
        self.assertEqual(prunable("agent/x", self.pulls((7, "closed", False))), "")

    def test_a_branch_with_no_pull_request_stays(self) -> None:
        # The fleet pushes a branch before anything opens a pull request for
        # it. Deleting that is deleting the delivery.
        self.assertEqual(prunable("agent/x", []), "")


class Earned(unittest.TestCase):
    """What a green agent branch has earned. Both old faults are cases."""

    GREEN = (("CI", "completed", "success"),)
    BASE = Branch(
        name="agent/x",
        ahead_by=1,
        files=("book/a.typ",),
        checks=(("CI", "completed", "success"),),
        pull=7,
    )

    def outcome(self, **over: object) -> str:
        return decide(replace(self.BASE, **over)).action

    def test_a_green_book_change_merges(self) -> None:
        self.assertEqual(self.outcome(), "merge")

    def test_diverged_is_normal_only_not_ahead_is_done(self) -> None:
        # Testing for `diverged` is what skipped the fleet's first delivery:
        # it is the state of any branch created before main moved on.
        self.assertEqual(self.outcome(ahead_by=0), "leave")

    def test_a_squash_merged_branch_stays_ahead_forever(self) -> None:
        self.assertEqual(self.outcome(merged_before=True), "leave")

    def test_green_means_ci_by_name(self) -> None:
        # Zero checks is not green: a GITHUB_TOKEN push starts no runs at
        # all, and `agent/typst-0.15.1` had exactly none.
        for checks, want in (
            ((), "wait"),
            ((("prose-scan", "completed", "success"),), "wait"),
            ((("CI", "in_progress", "pending"),), "wait"),
            ((("CI", "completed", "failure"),), "leave"),
            ((*GREEN_CI, ("prose-scan", "completed", "failure")), "leave"),
            ((*GREEN_CI, ("Fleet respond", "completed", "skipped")), "merge"),
        ):
            with self.subTest(checks=checks):
                self.assertEqual(self.outcome(checks=checks), want)

    def test_the_automation_supervises_itself(self) -> None:
        for files, pull, want in (
            ((".github/workflows/ci.yml",), 7, "leave"),
            ((".github/workflows/ci.yml",), None, "raise"),
            ((".claude/agents/prose-editor.md",), None, "raise"),
            (("book/a.typ", ".claude/x.md"), 7, "leave"),
        ):
            with self.subTest(files=files, pull=pull):
                self.assertEqual(self.outcome(files=files, pull=pull), want)

    def test_the_brakes(self) -> None:
        for over in (
            {"held": True},
            {"subject": "wip [hold] not yet"},
            {"mergeable_state": "dirty"},
            {"pull": None},
            {"files": ()},
        ):
            with self.subTest(over=over):
                self.assertEqual(self.outcome(**over), "leave")


class PullRequestBody(unittest.TestCase):
    """The only pure part of the two subcommands, and what a human reads."""

    def test_it_carries_the_log_and_the_files(self) -> None:
        body = pr_body("agent/x", ("first", "second"), ("book/a.typ",))
        self.assertIn("- first", body)
        self.assertIn("- second", body)
        self.assertIn("| `book/a.typ` |", body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--branch")
    parser.add_argument("--sha")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument(
        "--server", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the decision and change nothing."
    )
    parser.add_argument(
        "--open-pull",
        action="store_true",
        help="Open a pull request for a branch the fleet pushed.",
    )
    parser.add_argument(
        "--close-finished",
        action="store_true",
        help="Close the notices whose branch is done.",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete agent branches whose work is already merged.",
    )
    arguments = parser.parse_args(argv)

    if not arguments.repo:
        parser.error("a repository is required")
    if arguments.prune:
        return prune(arguments.repo)
    if arguments.close_finished:
        return close_finished(arguments.repo)
    if arguments.open_pull:
        if not arguments.branch:
            parser.error("--open-pull needs --branch")
        return open_pull(arguments.repo, arguments.branch)
    if not (arguments.branch and arguments.sha):
        parser.error("--branch and --sha are required")

    branch = observe(arguments.repo, arguments.branch, arguments.sha)
    decision = decide(branch)
    if arguments.dry_run:
        print(f"{decision.action}: {decision.why}")
        return 0
    return act(arguments.repo, branch, decision, arguments.sha, arguments.server)


if __name__ == "__main__":
    sys.exit(main())
