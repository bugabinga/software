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
under `--self-test`.

Usage:
    tools/agent_branch.py --branch agent/x --sha abc123
    tools/agent_branch.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# The one thing the fleet does not merge for itself. A change under these
# prefixes is the automation deciding its own future, and an agent that can
# rewrite its own brief or its own merge rule is supervised by nothing. The
# book is deliberately absent: the author delegated it to the fleet.
PROTECTED = re.compile(r"^(\.github/|\.claude/)")

# A check that has concluded acceptably. `neutral` and `skipped` are green:
# a job that correctly decided it had nothing to do has not failed.
SETTLED = {"success", "neutral", "skipped"}

# This workflow's own checks, which cannot be waited on from inside itself.
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
    return Decision("merge", f"#{branch.pull} is green and touches nothing protected")


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


def api(path: str, *args: str, check: bool = True) -> Any:
    out = gh("api", path, *args, check=check).strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


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
    print(f"::notice::{branch.name}: {decision.action} -- {decision.why}")
    if decision.action in {"leave", "wait"}:
        return 0

    if decision.action == "raise":
        title = f"Ready to review: {branch.name}"
        body = issue_body(repo, branch.name, server, branch.subject, branch.files)
        open_issues = api(f"repos/{repo}/issues?state=open&per_page=100") or []
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
            print(f"::notice::updated issue #{existing}")
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
            print(f"::notice::opened issue #{made.get('number')}")
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
        print(f"::notice::#{branch.pull} could not be merged; leaving it")
        return 0
    print(f"::notice::merged #{branch.pull}")
    gh("api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch.name}", check=False)
    return 0


def self_test() -> int:
    """`decide`, against every shape it has been wrong about."""
    green = (("CI", "completed", "success"),)
    base = Branch(
        name="agent/x", ahead_by=1, files=("book/a.typ",), checks=green, pull=7
    )

    cases: list[tuple[str, str, dict[str, Any]]] = [
        # The happy path, and the two the shell version got wrong.
        ("green book change merges", "merge", {}),
        # A branch created before main moved on is diverged, which is normal.
        # Only "not ahead" means there is nothing left to give.
        ("not ahead", "leave", {"ahead_by": 0}),
        # Squash merging leaves the branch holding its own commits, so it
        # stays ahead forever. `agent-branches.yml` once raised review issues
        # for branches whose work was already in main.
        ("already merged", "leave", {"merged_before": True}),
        # Zero checks is not green. A GITHUB_TOKEN push starts no runs at all.
        ("no checks at all", "wait", {"checks": ()}),
        # CI by name, not "some check passed".
        (
            "only an unrelated check",
            "wait",
            {"checks": (("prose-scan", "completed", "success"),)},
        ),
        ("CI still running", "wait", {"checks": (("CI", "in_progress", "pending"),)}),
        ("CI failed", "leave", {"checks": (("CI", "completed", "failure"),)}),
        (
            "CI green, another red",
            "leave",
            {"checks": (*green, ("prose-scan", "completed", "failure"))},
        ),
        # neutral and skipped are settled, not pending.
        (
            "skipped checks are green",
            "merge",
            {"checks": (*green, ("Fleet respond", "completed", "skipped"))},
        ),
        # The automation supervising itself.
        (
            "workflow change with a pull request",
            "leave",
            {"files": (".github/workflows/ci.yml",)},
        ),
        (
            "workflow change with no pull request",
            "raise",
            {"files": (".github/workflows/ci.yml",), "pull": None},
        ),
        (
            "brief change is protected too",
            "raise",
            {"files": (".claude/agents/prose-editor.md",), "pull": None},
        ),
        (
            "one protected file among many is enough",
            "leave",
            {"files": ("book/a.typ", ".claude/x.md")},
        ),
        # The brakes.
        ("hold label", "leave", {"held": True}),
        ("[hold] in the subject", "leave", {"subject": "wip [hold] not yet"}),
        ("conflicts with main", "leave", {"mergeable_state": "dirty"}),
        ("green but nothing to merge into", "leave", {"pull": None}),
        ("no files", "leave", {"files": ()}),
    ]

    for name, want, override in cases:
        got = decide(replace(base, **override))
        assert got.action == want, (
            f"{name}: wanted {want}, got {got.action} ({got.why})"
        )

    actions = sorted({want for _, want, _ in cases})
    print(f"agent_branch: {len(cases)} cases over {', '.join(actions)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--branch")
    parser.add_argument("--sha")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument(
        "--server", default=os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the decision and change nothing."
    )
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()
    if not (arguments.branch and arguments.sha and arguments.repo):
        parser.error("--branch, --sha and a repository are required")

    branch = observe(arguments.repo, arguments.branch, arguments.sha)
    decision = decide(branch)
    if arguments.dry_run:
        print(f"{decision.action}: {decision.why}")
        return 0
    return act(arguments.repo, branch, decision, arguments.sha, arguments.server)


if __name__ == "__main__":
    sys.exit(main())
