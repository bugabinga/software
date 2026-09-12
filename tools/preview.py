"""Name and reap the per-pull-request preview Workers.

Two jobs that have to agree with each other, which is why they are one file.
`preview.yml` deploys a Worker named for a pull request and, on the next
deploy, deletes the ones whose pull requests have closed. If the naming and
the matching ever disagree, the reaper either deletes a live preview or
accumulates dead ones until the account's Worker limit stops the next deploy
-- and both failures are quiet.

Usage:
    tools/preview.py --name 70            # book-pr-70
    ... | tools/preview.py --repo o/r --reap   # which of these have closed
    tools/preview.py --self-test
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The whole contract between deploying and reaping. Anchored at both ends so
# `book-pr-70-old` is not read as pull request 70.
PREFIX = "book-pr-"
NAME_RE = re.compile(rf"^{re.escape(PREFIX)}(?P<number>[1-9][0-9]*)$")


def worker_name(pr: int | str) -> str:
    number = int(pr)
    if number < 1:
        sys.exit(f"not a pull request number: {pr!r}")
    return f"{PREFIX}{number}"


def pr_of(name: str) -> int | None:
    """The pull request a Worker name stands for, or None if it is not ours."""
    match = NAME_RE.match(name.strip())
    return int(match.group("number")) if match else None


def gh(*args: str) -> str:
    binary = shutil.which("gh") or str(ROOT / ".tools" / "gh" / "gh")
    done = subprocess.run(  # noqa: PLW1510 - returncode is read below
        [binary, *args], capture_output=True, text=True, timeout=60
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def is_open(repo: str, number: int) -> bool:
    """Open, as far as we can tell.

    A failed lookup answers "open". Deleting a live preview because the API
    was briefly unreachable is the worse of the two mistakes: the dead one
    costs a slot, the live one costs the reviewer the thing they were sent.
    """
    state = gh("api", f"repos/{repo}/pulls/{number}", "--jq", ".state")
    return state != "closed"


def reap(repo: str, names: list[str]) -> list[str]:
    """Which of these Worker names belong to closed pull requests."""
    doomed = []
    for name in names:
        number = pr_of(name)
        if number is None:
            continue
        if not is_open(repo, number):
            doomed.append(worker_name(number))
    return doomed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", help="print the Worker name for a pull request")
    parser.add_argument(
        "--reap",
        nargs="*",
        help="Worker names to consider deleting; reads stdin when given none",
    )
    parser.add_argument("--repo", default="", help="owner/name, for --reap")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()
    if arguments.name:
        print(worker_name(arguments.name))
        return 0
    if arguments.reap is not None:
        if not arguments.repo:
            sys.exit("--reap needs --repo owner/name")
        names = arguments.reap or sys.stdin.read().split()
        for name in reap(arguments.repo, names):
            print(name)
        return 0
    parser.print_help()
    return 1


def self_test() -> int:
    """Naming and matching are inverses, and nothing else is touched."""
    problems = []

    for number in (1, 7, 70, 12345):
        name = worker_name(number)
        if pr_of(name) != number:
            problems.append(f"{number} -> {name} -> {pr_of(name)}")

    # Names that are not ours must be left alone. A reaper that matches
    # loosely deletes somebody else's Worker on the same account.
    for name in (
        "book-pr-",
        "book-pr-0",
        "book-pr-07",
        "book-pr-70-old",
        "book-pr-x",
        "notes-intake",
        "xbook-pr-70",
        "",
    ):
        if pr_of(name) is not None:
            problems.append(f"claimed {name!r} as pull request {pr_of(name)}")

    if pr_of("book-pr-70 ") != 70:
        problems.append("a trailing newline from the API made the name foreign")

    # A closed pull request is reaped; an open one and an unknown name are not.
    saved = globals()["is_open"]
    globals()["is_open"] = lambda _repo, number: number != 99
    try:
        got = reap("o/r", ["book-pr-99", "book-pr-70", "notes-intake", "book-pr-0"])
    finally:
        globals()["is_open"] = saved
    if got != ["book-pr-99"]:
        problems.append(f"reap chose {got!r}, wanted ['book-pr-99']")

    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in preview", file=sys.stderr)
        return 1
    print("preview: naming and reaping agree, and match nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
