#!/usr/bin/env python3
"""Where the notes inbox answers, from the one file that decides it.

`worker/notes-intake/wrangler.jsonc` holds the Worker's name and, in `vars`,
the account's workers.dev subdomain. The address is those two and nothing
else, and three things need it: the skill generator builds it into the page
it ships, `tools/build.py` substitutes it into that page, and
`worker-deploy.yml` compares it against the account it just deployed to.

Its own module so the build does not have to import the skill generator to
learn one URL, and so the drift check has somewhere to live that is neither.

Read with a regex rather than a JSON parser because the file is JSONC and is
full of comments; the fields are one line each and unambiguous, and a parser
that strips comments correctly is more code than the thing it enables.

Usage:
    tools/inbox.py                # https://notes-intake.<sub>.workers.dev
    tools/inbox.py --check-live software-fleet
"""

from __future__ import annotations

import argparse
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRANGLER = ROOT / "worker" / "notes-intake" / "wrangler.jsonc"


def field(config: Path, name: str) -> str:
    """One `"name": "value"` from the config, or exit saying which is missing."""
    found = re.search(
        rf'"{re.escape(name)}"\s*:\s*"([^"]+)"', config.read_text(encoding="utf-8")
    )
    if not found:
        sys.exit(f"{config}: no {name} in it")
    return found.group(1)


def worker_name(config: Path = WRANGLER) -> str:
    return field(config, "name")


def compose(name: str, subdomain: str) -> str:
    """The URL, from a Worker name and a subdomain.

    `subdomain` is what the account is called, not a hostname -- Cloudflare's
    API answers `software-fleet` rather than `software-fleet.workers.dev`.
    Tolerating the longer form costs one strip and saves a double suffix.
    """
    short = subdomain.strip().removesuffix(".workers.dev")
    if not short or "/" in short or "." in short:
        sys.exit(f"{subdomain!r} is not a workers.dev subdomain name")
    return f"https://{name}.{short}.workers.dev"


def url(config: Path = WRANGLER) -> str:
    """The declared address."""
    return compose(worker_name(config), field(config, "WORKERS_SUBDOMAIN"))


def drift(live: str, config: Path = WRANGLER) -> str:
    """What is wrong when the account and the config disagree, or "".

    This is what makes writing the subdomain down safe. The objection to a
    checked-in copy was that it keeps looking right after the account moves;
    the deploy knows which account it just reached, so it can say so.
    """
    declared = url(config)
    reached = compose(worker_name(config), live)
    if declared == reached:
        return ""
    return (
        f"{config.name} says the inbox is at {declared}, but this deploy "
        f"reached {reached}. The skill page is built from the first, so it is "
        f"now pointing at nothing. Update WORKERS_SUBDOMAIN in {config.name}."
    )


class Composing(unittest.TestCase):
    """A subdomain name, a hostname, and the shapes that are neither."""

    def test_a_bare_name(self) -> None:
        self.assertEqual(
            compose("notes-intake", "software-fleet"),
            "https://notes-intake.software-fleet.workers.dev",
        )

    def test_the_long_form_is_tolerated(self) -> None:
        # Cloudflare answers with the short form; a human writing it down
        # reaches for the hostname. Both mean the same account.
        self.assertEqual(compose("w", "acct.workers.dev"), compose("w", "  acct  "))


class TheConfig(unittest.TestCase):
    """Against the file in this checkout, not a fixture."""

    def test_the_worker_names_itself(self) -> None:
        self.assertEqual(worker_name(), "notes-intake")

    def test_the_url_is_composed_not_stored(self) -> None:
        # No `"https://..."` anywhere in the config: if the whole URL were
        # written down, this module would be decoration.
        self.assertNotIn('workers.dev"', WRANGLER.read_text(encoding="utf-8"))
        self.assertTrue(url().endswith(".workers.dev"))

    def test_the_page_carries_the_marker_the_build_fills(self) -> None:
        # The other half of the contract, asserted from this side too: a page
        # that lost `{{inbox}}` would build clean and prefill nothing.
        page = ROOT / "site" / "skill" / "index.html"
        self.assertIn("{{inbox}}", page.read_text(encoding="utf-8"))


class Drift(unittest.TestCase):
    """The check that makes the checked-in copy safe."""

    def test_agreement_is_silence(self) -> None:
        self.assertEqual(drift(field(WRANGLER, "WORKERS_SUBDOMAIN")), "")

    def test_the_long_form_still_agrees(self) -> None:
        live = field(WRANGLER, "WORKERS_SUBDOMAIN")
        self.assertEqual(drift(f"{live}.workers.dev"), "")

    def test_a_moved_account_says_both_addresses(self) -> None:
        complaint = drift("somebody-else")
        self.assertIn("somebody-else", complaint)
        self.assertIn(url(), complaint)
        self.assertIn("WORKERS_SUBDOMAIN", complaint)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-live",
        metavar="SUBDOMAIN",
        help="the account this deploy reached; fail if the config disagrees",
    )
    arguments = parser.parse_args(argv)
    if arguments.check_live:
        complaint = drift(arguments.check_live)
        if complaint:
            sys.exit(f"::error::{complaint}")
        print(url())
        return 0
    print(url())
    return 0


if __name__ == "__main__":
    sys.exit(main())
