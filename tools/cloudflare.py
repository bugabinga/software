"""Read the Cloudflare API's answer about an account's workers.dev subdomain.

wrangler collapses three different situations into one message -- "You need to
register a workers.dev subdomain" -- and they need three different responses:

  the subdomain exists        deploy
  the token cannot read it    fix the token's scope, not the account
  there is genuinely none     register one, once, in the dashboard

That mattered here. Every `worker-deploy.yml` run since it was armed died on
that message, and the first reading of it was "the account has no subdomain".
The account has a *domain*, which is a zone and a different thing, so the
diagnosis was neither confirmed nor obviously wrong -- and a workflow that
cannot tell the cases apart cannot say which.

Reads the API response on stdin. Prints the subdomain when there is one, and
otherwise nothing on stdout and one sentence on stderr saying which case it
is. Exit 0 when a deploy can proceed, 1 when it cannot.

Usage:
    tools/cloudflare.py --check             # ask the API and write step outputs
    curl ... | tools/cloudflare.py --subdomain --status 200
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unittest
import urllib.error
import urllib.request
from typing import ClassVar

from fleetlib import notice, output, warn

# Cloudflare answers a scope problem with an error code in the body as well
# as an HTTP status, and not always the same status, so both are consulted.
DENIED_STATUS = {"401", "403"}
DENIED_CODES = {1000, 9109, 10000}


def read(payload: str, status: str) -> tuple[str | None, str]:
    """The subdomain, or None and the sentence that explains why not."""
    try:
        answer = json.loads(payload) if payload.strip() else {}
    except json.JSONDecodeError:
        answer = {}
    if not isinstance(answer, dict):
        answer = {}

    result = answer.get("result")
    name = (result or {}).get("subdomain") if isinstance(result, dict) else None
    if isinstance(name, str) and name:
        return name, ""

    errors = answer.get("errors") or []
    codes = {e.get("code") for e in errors if isinstance(e, dict)}
    detail = "; ".join(
        f"{e.get('code')}: {e.get('message')}" for e in errors if isinstance(e, dict)
    )

    if status in DENIED_STATUS or codes & DENIED_CODES:
        return None, (
            f"The Cloudflare API refused to say whether this account has a "
            f"workers.dev subdomain (HTTP {status}"
            f"{'; ' + detail if detail else ''}). That is the token's scope "
            f"rather than a missing subdomain: CLOUDFLARE_API_TOKEN needs "
            f"Account / Workers Scripts / Edit."
        )
    if status not in {"200", "404"}:
        return None, (
            f"Could not reach the Cloudflare API to check for a workers.dev "
            f"subdomain (HTTP {status}"
            f"{'; ' + detail if detail else ''})."
        )
    return None, (
        "This Cloudflare account has no workers.dev subdomain. A domain shown "
        "in the dashboard is a zone and is not the same thing -- the subdomain "
        "is a per-account name, set once under Workers & Pages."
    )


def ask(token: str, account: str) -> tuple[str, str]:
    """The API's answer about this account's subdomain, and the HTTP status.

    `preview.yml` and `worker-deploy.yml` each held the same curl and the
    same four-line branch around this module. Identical but for one output,
    which is the state a shared step is in just before the two drift.
    """
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/subdomain",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.read().decode("utf-8"), str(answer.status)
    except urllib.error.HTTPError as error:
        return error.read().decode("utf-8", "replace"), str(error.code)
    except OSError as error:
        return "", f"000 ({error})"


def check() -> int:
    """Ask, then say whether a deploy can proceed. Never fails the job."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not (token and account):
        output("present", "false")
        warn("No Cloudflare credential, so nothing was deployed.")
        return 0

    name, why = read(*ask(token, account))
    if name is None:
        output("present", "false")
        warn(f"{why} Nothing was deployed.")
        return 0
    output("present", "true")
    output("name", name)
    notice(f"deploying to {name}.workers.dev")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subdomain", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="ask the API directly and write present= / name=",
    )
    parser.add_argument("--status", default="200", help="the HTTP status curl saw")
    arguments = parser.parse_args(argv)

    if arguments.check:
        return check()

    if not arguments.subdomain:
        parser.print_help()
        return 1

    name, why = read(sys.stdin.read(), arguments.status)
    if name:
        print(name)
        return 0
    print(why, file=sys.stderr)
    return 1


class ThreeSituations(unittest.TestCase):
    """wrangler says one thing for three cases that need three answers."""

    CASES: ClassVar[list[tuple[str, str, str | None, str]]] = [
        # payload, status, the subdomain, a word the sentence must carry
        (
            '{"result": {"subdomain": "bugabinga"}, "success": true}',
            "200",
            "bugabinga",
            "",
        ),
        (
            '{"result": {"subdomain": ""}, "success": true}',
            "200",
            None,
            "no workers.dev",
        ),
        ('{"result": null, "success": true}', "200", None, "no workers.dev"),
        ("", "404", None, "no workers.dev"),
        (
            '{"errors": [{"code": 10000, "message": "Authentication error"}]}',
            "403",
            None,
            "token's scope",
        ),
        (
            '{"errors": [{"code": 10000, "message": "Authentication error"}]}',
            "200",
            None,
            "token's scope",
        ),
        ("", "000", None, "Could not reach"),
        # Unparsable at 200 reads as "no subdomain", which is the honest
        # answer: the API said yes and said nothing.
        ("not json at all", "200", None, "no workers.dev"),
    ]

    def test_each_is_told_apart(self) -> None:
        for payload, status, want_name, want_word in self.CASES:
            with self.subTest(status=status, payload=payload[:34]):
                name, why = read(payload, status)
                self.assertEqual(name, want_name)
                if want_word:
                    self.assertIn(want_word, why)

    def test_a_refusal_is_never_a_missing_subdomain(self) -> None:
        # That sends the reader to the dashboard to create a thing which is
        # already there.
        _, denied = read('{"errors": [{"code": 10000, "message": "x"}]}', "403")
        self.assertNotIn("no workers.dev subdomain", denied)


if __name__ == "__main__":
    sys.exit(main())
