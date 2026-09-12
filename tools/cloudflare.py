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
    curl ... | tools/cloudflare.py --subdomain --status 200
    tools/cloudflare.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subdomain", action="store_true")
    parser.add_argument("--status", default="200", help="the HTTP status curl saw")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()
    if not arguments.subdomain:
        parser.print_help()
        return 1

    name, why = read(sys.stdin.read(), arguments.status)
    if name:
        print(name)
        return 0
    print(why, file=sys.stderr)
    return 1


def self_test() -> int:
    """Each of the three situations is told apart from the other two."""
    problems = []

    cases = [
        # payload, status, expected subdomain, a word the sentence must carry
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
        (
            '{"errors": [{"code": 9109, "message": "Unauthorized"}]}',
            "401",
            None,
            "token's scope",
        ),
        ("", "000", None, "Could not reach"),
        ("<html>502</html>", "502", None, "Could not reach"),
    ]
    for payload, status, want_name, want_word in cases:
        name, why = read(payload, status)
        if name != want_name:
            problems.append(
                f"{status} {payload[:34]!r} -> {name!r}, wanted {want_name!r}"
            )
        elif want_word and want_word not in why:
            problems.append(f"{status} {payload[:34]!r} -> {why[:60]!r}")

    # A refusal must never be read as "no subdomain": that sends the reader to
    # the dashboard to create a thing that is already there.
    _, denied = read('{"errors": [{"code": 10000, "message": "x"}]}', "403")
    if "no workers.dev subdomain" in denied:
        problems.append("a refused read was reported as a missing subdomain")

    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in cloudflare", file=sys.stderr)
        return 1
    print("cloudflare: a missing subdomain, a refused read and an outage read apart")
    return 0


if __name__ == "__main__":
    sys.exit(main())
