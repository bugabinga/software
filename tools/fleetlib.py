#!/usr/bin/env python3
"""The mechanics every workflow script repeats, in one typed place.

A `run:` block can only be tested by pushing, so the tree's rule is that
anything with a branch in it lives in a program. That produced a second
problem: each program grew its own `gh` wrapper, its own way of writing a step
output, its own idea of what an annotation looks like. This is the floor they
share.

Nothing here is speculative. Every function replaces shell that existed in at
least two workflows.

Usage:
    tools/fleetlib.py --self-test
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


class GhError(RuntimeError):
    """`gh` exited non-zero and the caller asked to be told rather than die."""


def gh(*args: str, check: bool = True) -> str:
    """Run `gh`, from the PATH or the pinned copy `mise install` leaves.

    `check=False` returns "" instead of exiting, for the many callers whose
    question is "is there one?" rather than "give me it".
    """
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
    """`gh api`, decoded. `None` when the call failed or answered nothing.

    Never `--paginate` with an aggregating `--jq`: the filter runs once per
    page and the results are concatenated, so `| length` over 101 items
    answers "6\\n1". `tools/check_workflows.py` gates that; this returns whole
    objects so the counting happens in Python.
    """
    out = gh("api", path, *args, check=check).strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def paged(path: str, *args: str, pages: int = 10, per_page: int = 100) -> list[Any]:
    """Every page of a list endpoint, as one list.

    Explicit paging rather than `--paginate`, because the proxy in front of
    some sessions refuses the numeric-id Link headers `gh` follows.
    """
    joiner = "&" if "?" in path else "?"
    items: list[Any] = []
    for page in range(1, pages + 1):
        got = api(f"{path}{joiner}per_page={per_page}&page={page}", *args, check=False)
        if not isinstance(got, list) or not got:
            break
        items += got
        if len(got) < per_page:
            break
    return items


def _append(variable: str, text: str) -> bool:
    """Append to one of the runner's files. False when not on a runner."""
    where = os.environ.get(variable)
    if not where:
        return False
    with Path(where).open("a", encoding="utf-8") as handle:
        handle.write(text if text.endswith("\n") else text + "\n")
    return True


def output(name: str, value: str) -> bool:
    """A step output. Multi-line values use the heredoc form, which is the
    one that a value containing a newline does not corrupt -- the fault that
    killed `fleet-respond` when a `| length` over two pages answered "6\\n1".
    """
    if "\n" in value:
        marker = f"{name.upper()}_EOF"
        return _append("GITHUB_OUTPUT", f"{name}<<{marker}\n{value}\n{marker}")
    return _append("GITHUB_OUTPUT", f"{name}={value}")


def summary(text: str) -> bool:
    """The job summary: the readable account of a decision.

    A file, so it survives `mise run check` prefixing every line a task
    prints -- which is why `::warning::` from inside a task never reaches the
    runner and this does.
    """
    return _append("GITHUB_STEP_SUMMARY", text)


def notice(text: str) -> None:
    print(f"::notice::{text}")


def warn(text: str) -> None:
    print(f"::warning::{text}")


def fail(text: str) -> None:
    print(f"::error::{text}")


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        os.environ["GITHUB_OUTPUT"] = str(out)

        assert output("simple", "yes")
        assert out.read_text(encoding="utf-8") == "simple=yes\n"

        # The shape that matters: a value with a newline in it must not be
        # read back as a second key. `key=6\n1` makes `1` a line the runner
        # rejects, which is exactly how run 34809724830 died.
        out.write_text("", encoding="utf-8")
        assert output("count", "6\n1")
        text = out.read_text(encoding="utf-8")
        assert text == "count<<COUNT_EOF\n6\n1\nCOUNT_EOF\n", repr(text)

        del os.environ["GITHUB_OUTPUT"]
        assert output("nowhere", "x") is False, "no runner, no write, no crash"

    print("fleetlib: outputs, multi-line outputs, and no-runner all check out")
    return 0


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv[1:] else 0)
