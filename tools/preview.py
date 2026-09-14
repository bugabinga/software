"""Name and reap the per-pull-request preview Workers.

Two jobs that have to agree with each other, which is why they are one file.
`preview.yml` deploys a Worker named for a pull request and, on the next
deploy, deletes the ones whose pull requests have closed. If the naming and
the matching ever disagree, the reaper either deletes a live preview or
accumulates dead ones until the account's Worker limit stops the next deploy
-- and both failures are quiet.

The sweep is here too, for a reason the workflow taught. It was nine lines of
`run:` -- curl the account's Workers, pipe through `--reap`, `wrangler delete`
each answer -- under `set -euo pipefail`. A token without Workers KV scope
made one delete exit non-zero, which failed the step, which turned `main` red
for a cleanup task. A preview that outlives its pull request costs a slot; a
red `main` costs the signal that tells anyone whether the tree is broken.
`sweep` reports and returns 0.

Usage:
    tools/preview.py --name 70            # book-pr-70
    ... | tools/preview.py --repo o/r --reap   # which of these have closed
    tools/preview.py --repo o/r --sweep   # list, decide and delete
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
from unittest import mock

import cloudflare
from fleetlib import captured, notice, warn

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


def workers(token: str, account: str) -> tuple[list[str], str]:
    """Every Worker on the account, and the sentence explaining an empty list.

    An empty list with no complaint means the account has no Workers. An
    empty list with one means nothing could be read, and the difference
    matters: the second must not be reported as "nothing to reap".
    """
    payload, status = cloudflare.account_get(token, account, "workers/scripts")
    try:
        answer = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError:
        answer = {}
    if not isinstance(answer, dict) or status != "200":
        detail = "; ".join(
            f"{e.get('code')}: {e.get('message')}"
            for e in (answer.get("errors") or [])
            if isinstance(e, dict)
        )
        return [], (
            f"could not list this account's Workers (HTTP {status}"
            f"{'; ' + detail if detail else ''}); nothing was reaped"
        )
    result = answer.get("result") or []
    return [str(w.get("id", "")) for w in result if isinstance(w, dict)], ""


def delete(name: str) -> str:
    """Delete one Worker. The empty string on success, the reason otherwise."""
    binary = shutil.which("mise")
    command = (
        [binary, "exec", "--", "wrangler", "delete", "--name", name, "--force"]
        if binary
        else ["wrangler", "delete", "--name", name, "--force"]
    )
    done = subprocess.run(  # noqa: PLW1510 - the reason is the return value
        command, capture_output=True, text=True, timeout=300
    )
    if done.returncode == 0:
        return ""
    tail = (done.stderr or done.stdout).strip().splitlines()
    return tail[-1] if tail else f"exit {done.returncode}"


def sweep(repo: str, token: str, account: str) -> int:
    """List, decide, delete. Always 0.

    Never non-zero, and that is the whole design. This runs on `main` after
    every pull-request build; a stale preview is worth a warning and not one
    line of red in a run list people use to tell whether the book builds.
    """
    names, complaint = workers(token, account)
    if complaint:
        warn(complaint)
        return 0
    doomed = reap(repo, names)
    if not doomed:
        notice(f"{len(names)} Worker(s) on the account, no stale previews")
        return 0
    for name in doomed:
        reason = delete(name)
        if reason:
            warn(f"could not delete {name}: {reason}")
        else:
            notice(f"deleted {name}")
    return 0


class Listing(unittest.TestCase):
    """`workers` must never report a refusal as an empty account."""

    def answer(self, payload: str, status: str) -> tuple[list[str], str]:
        with mock.patch.object(
            cloudflare, "account_get", return_value=(payload, status)
        ):
            return workers("token", "account")

    def test_two_workers(self) -> None:
        names, complaint = self.answer(
            '{"result": [{"id": "book-pr-1"}, {"id": "other"}]}', "200"
        )
        self.assertEqual(names, ["book-pr-1", "other"])
        self.assertEqual(complaint, "")

    def test_an_empty_account_is_not_a_complaint(self) -> None:
        self.assertEqual(self.answer('{"result": []}', "200"), ([], ""))

    def test_a_refusal_is_not_an_empty_account(self) -> None:
        # The fault this is for: the token lost its Workers scope, the
        # account would have read as empty, and the sweep would have said
        # "nothing to do" for as long as the token stayed broken.
        names, complaint = self.answer(
            '{"errors": [{"code": 10000, "message": "Authentication error"}]}', "403"
        )
        self.assertEqual(names, [])
        self.assertIn("10000", complaint)
        self.assertIn("nothing was reaped", complaint)

    def test_unparsable_is_a_complaint_too(self) -> None:
        self.assertNotEqual(self.answer("<html>502</html>", "502")[1], "")


class Sweeping(unittest.TestCase):
    """The sweep reports; it never fails the run."""

    def run_sweep(
        self, names: list[str], complaint: str = "", broken: str = ""
    ) -> tuple[int, str, list[str]]:
        deleted: list[str] = []

        def deleting(name: str) -> str:
            deleted.append(name)
            return "boom" if name == broken else ""

        with (
            mock.patch(f"{__name__}.workers", return_value=(names, complaint)),
            mock.patch(f"{__name__}.delete", side_effect=deleting),
            mock.patch(f"{__name__}.is_open", return_value=False),
            captured() as said,
        ):
            code = sweep("o/r", "token", "account")
        return code, said.getvalue(), deleted

    def test_a_refusal_warns_and_deletes_nothing(self) -> None:
        code, said, deleted = self.run_sweep([], "could not list this account's")
        self.assertEqual(code, 0)
        self.assertIn("::warning::", said)
        self.assertEqual(deleted, [])

    def test_a_failed_delete_does_not_fail_the_run(self) -> None:
        # The fault this function exists for: one `wrangler delete` exiting
        # non-zero under `set -e` turned `main` red for a cleanup task.
        code, said, deleted = self.run_sweep(["book-pr-1"], broken="book-pr-1")
        self.assertEqual(code, 0)
        self.assertEqual(deleted, ["book-pr-1"])
        self.assertIn("could not delete book-pr-1", said)

    def test_a_foreign_worker_is_never_touched(self) -> None:
        code, said, deleted = self.run_sweep(["somebody-elses-worker"])
        self.assertEqual(code, 0)
        self.assertEqual(deleted, [])
        self.assertIn("no stale previews", said)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", help="print the Worker name for a pull request")
    parser.add_argument(
        "--reap",
        nargs="*",
        help="Worker names to consider deleting; reads stdin when given none",
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="list the account's Workers, delete the closed ones, never fail",
    )
    parser.add_argument("--repo", default="", help="owner/name, for --reap")
    arguments = parser.parse_args(argv)

    if arguments.sweep:
        if not arguments.repo:
            sys.exit("--sweep needs --repo owner/name")
        return sweep(
            arguments.repo,
            os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        )

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


class Naming(unittest.TestCase):
    """Naming and matching are inverses, and match nothing else."""

    def test_round_trip(self) -> None:
        for number in (1, 7, 70, 12345):
            with self.subTest(number=number):
                self.assertEqual(pr_of(worker_name(number)), number)

    def test_a_foreign_name_is_left_alone(self) -> None:
        # A reaper that matches loosely deletes somebody else's Worker on
        # the same account.
        for name in (
            "book-pr-",
            "book-pr-0",
            "book-pr-07",
            "book-pr-70-old",
            "book-pr-x",
            "notes-intake",
            "",
            "xbook-pr-70",
        ):
            with self.subTest(name=name):
                self.assertIsNone(pr_of(name))

    def test_trailing_whitespace_is_still_ours(self) -> None:
        # The API returns names with a newline on them, and a name that
        # is ours does not stop being ours for it.
        self.assertEqual(pr_of("book-pr-70 "), 70)


class Reaping(unittest.TestCase):
    def test_only_closed_pull_requests(self) -> None:
        saved = globals()["is_open"]
        globals()["is_open"] = lambda _repo, number: number != 99
        self.addCleanup(globals().__setitem__, "is_open", saved)
        got = reap("o/r", ["book-pr-99", "book-pr-70", "notes-intake", "book-pr-0"])
        self.assertEqual(got, ["book-pr-99"])


if __name__ == "__main__":
    sys.exit(main())
