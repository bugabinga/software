#!/usr/bin/env python3
"""Which Claude credential this run has, tidied, masked and reported.

The same thirty-five lines of shell stood at the top of `fleet.yml`,
`fleet-review.yml` and `fleet-respond.yml`. Three copies of one decision is
three places for it to drift, and this one had already cost a day: four
dispatches died in 38ms having called no model, because the secret had been
pasted with a line break in it. The tidying is now a function with that case
in its self-test.

Writes `CLAUDE_OAUTH` and `CLAUDE_API_KEY` to `$GITHUB_ENV` and `present` to
`$GITHUB_OUTPUT`.

Usage:
    tools/credential.py    # reads CLAUDE_CODE_OAUTH_TOKEN, then ANTHROPIC_API_KEY
    tools/credential.py --self-test
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from fleetlib import notice, output, warn


def tidy(raw: str | None) -> str:
    """A secret as it can actually be used.

    Every whitespace character, not just the ends: a token pasted from a
    wrapped terminal carries an interior newline, and the action fails in
    38ms with no model call and nothing in the log that names the cause.
    """
    return "".join((raw or "").split())


def mask(value: str) -> None:
    """Keep a tidied secret out of the log.

    The raw secret is masked by the runner already; the tidied one is a
    different string, so it is not -- which is the whole reason this line
    exists.
    """
    if value:
        print(f"::add-mask::{value}")


def report(oauth_raw: str | None, api_raw: str | None) -> tuple[str, str, bool]:
    """The pair to export, and whether the fleet can run at all."""
    oauth, api_key = tidy(oauth_raw), tidy(api_raw)
    mask(oauth)
    mask(api_key)

    if oauth:
        notice("running with CLAUDE_CODE_OAUTH_TOKEN")
        if oauth != (oauth_raw or ""):
            warn(
                "CLAUDE_CODE_OAUTH_TOKEN contained whitespace, which was "
                "stripped before use. Re-add it as one line to be rid of this."
            )
        return oauth, api_key, True
    if api_key:
        notice("running with ANTHROPIC_API_KEY")
        if api_key != (api_raw or ""):
            warn(
                "ANTHROPIC_API_KEY contained whitespace, which was stripped "
                "before use. Re-add it as one line to be rid of this."
            )
        return oauth, api_key, True

    notice(
        "No credential, so no agent ran. The check passes so that requiring "
        "it before the fleet is armed cannot lock the repository -- but "
        "nothing was reviewed and nothing was answered."
    )
    return "", "", False


def export(oauth: str, api_key: str, present: bool) -> None:
    where = os.environ.get("GITHUB_ENV")
    if where:
        with Path(where).open("a", encoding="utf-8") as handle:
            handle.write(f"CLAUDE_OAUTH={oauth}\nCLAUDE_API_KEY={api_key}\n")
    output("present", "true" if present else "false")


def self_test() -> int:
    assert tidy(None) == ""
    assert tidy("") == ""
    assert tidy("  ") == ""
    assert tidy("sk-abc") == "sk-abc"
    # The fault this exists for: a line break inside the pasted value.
    assert tidy("sk-abc\ndef") == "sk-abcdef"
    assert tidy("\nsk-abc\n") == "sk-abc"
    assert tidy("sk abc\tdef\r\n") == "skabcdef"

    # OAuth wins when both are set, and absence is reported, not guessed.
    assert report("oauth", "key")[0] == "oauth"
    assert report("oauth", "key")[2] is True
    assert report(None, "key")[1] == "key"
    assert report(None, "key")[2] is True
    assert report(None, None)[2] is False
    assert report("  ", "")[2] is False, "whitespace is not a credential"

    print("credential: tidying, precedence, and absence all check out")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    if parser.parse_args(argv).self_test:
        return self_test()

    oauth, api_key, present = report(
        os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"),
        os.environ.get("ANTHROPIC_API_KEY"),
    )
    export(oauth, api_key, present)
    return 0


if __name__ == "__main__":
    sys.exit(main())
