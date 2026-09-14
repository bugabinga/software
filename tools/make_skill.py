#!/usr/bin/env python3
"""Build the note-taker's skill zip outside the browser.

`site/skill/index.html` is the generator, and it is a page rather than an
endpoint so that the intake token never leaves the machine that types it. That
is the right design for anyone setting this up from a phone, and it is the
wrong shape for anyone who already has a checkout and a shell.

Not a second generator: the page's script is pulled out and run under node,
exactly as `tools/check_skill_page.py` does. Two implementations of the skill
would drift, and the drift would surface as a note-taking session behaving
oddly rather than as a failing test.

The deploy does not call this to build a zip, and deliberately: the repository
is public, so a workflow artifact holding the token would publish it. What the
deploy does use is `--print-endpoint`, so the worker's name stays in
`wrangler.jsonc` and the job summary cannot point somewhere that never existed.

The token is read from stdin. An argument is in the process table and in the
log of anything that traces the runner; stdin is neither.

Usage:
    tools/make_skill.py --subdomain NAME --out PATH [--book LINE] < token
    tools/make_skill.py --subdomain NAME --print-endpoint
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from check_skill_page import extract_script
from fleetlib import captured
from inbox import compose, worker_name

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "skill" / "index.html"

# The zip is assembled by the page's own `zip()`; this only feeds it and
# writes the bytes out. `arrayBuffer()` because the page produces a Blob,
# which is what a browser download wants and node has to unwrap.
DRIVER = """
const api = require("./page.cjs");
const input = JSON.parse(require("node:fs").readFileSync("input.json", "utf8"));

api.zip({ "file-note/SKILL.md": api.skillMarkdown(input) })
  .arrayBuffer()
  .then((buffer) => {
    require("node:fs").writeFileSync("out.zip", Buffer.from(buffer));
  });
"""


def default_book(page: Path = PAGE) -> str:
    """What the page prefills its `about` field with.

    Read out of the page rather than restated here, for the reason in this
    module's docstring. A constant holding the same sentence is a second
    generator in miniature, and it drifted on its first opportunity: the page
    was reworded and the constant kept the old string, which is what anyone
    with a checkout got from `--book`. Nothing caught it, and nothing was
    going to -- the cases below assert the endpoint and the token and
    deliberately not the prose around them.

    A regex rather than an HTML parser, for the same reason `worker_name`
    uses one: the attribute is on one line and unambiguous. A page that moves
    it exits here with the file named, which is the direction to fail in.
    """
    text = page.read_text(encoding="utf-8")
    match = re.search(r'id="book"[^>]*\svalue="([^"]*)"', text)
    if not match:
        sys.exit(f"{page}: the `about` field has no value to default to")
    return html.unescape(match.group(1))


def build(endpoint: str, token: str, book: str, out: Path, page: Path = PAGE) -> int:
    node = shutil.which("node")
    if not node:
        sys.exit("node is not installed, and the page's script is what builds the zip")

    script = extract_script(page)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # `.cjs` so node reads it as CommonJS whatever the page contains --
        # the page's export guard writes to `module.exports`.
        (work / "page.cjs").write_text(script, encoding="utf-8")
        (work / "driver.cjs").write_text(DRIVER, encoding="utf-8")
        # Through a file rather than argv, for the same reason as stdin.
        (work / "input.json").write_text(
            json.dumps({"endpoint": endpoint, "token": token, "book": book}),
            encoding="utf-8",
        )

        done = subprocess.run(  # noqa: PLW1510 - the caller reads returncode
            [node, "driver.cjs"], cwd=work, capture_output=True, text=True, timeout=60
        )
        if done.returncode != 0:
            print(done.stderr, file=sys.stderr)
            sys.exit(f"{page}: the script failed under node")

        produced = work / "out.zip"
        if not produced.is_file():
            sys.exit(f"{page}: the script ran but wrote no zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(produced.read_bytes())

    print(f"{out}: the skill for {endpoint}")
    return 0


@unittest.skipUnless(shutil.which("node"), "node is absent, so the zip is unbuilt")
class TheZip(unittest.TestCase):
    """This tool's zip is the page's zip, built by the page's own code."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        out = Path(tmp.name) / "skill.zip"
        self.enterContext(captured())
        build(
            "https://notes-intake.example.workers.dev",
            "a-very-long-random-intake-token",
            default_book(),
            out,
        )
        with zipfile.ZipFile(out) as archive:
            self.names = archive.namelist()
            self.skill = archive.read("file-note/SKILL.md").decode("utf-8")

    def test_one_file(self) -> None:
        self.assertEqual(self.names, ["file-note/SKILL.md"])

    def test_the_two_values_that_make_it_work(self) -> None:
        # Rather than the prose around them, which is the page's to change.
        self.assertIn("notes-intake.example.workers.dev/note", self.skill)
        self.assertIn("a-very-long-random-intake-token", self.skill)

    def test_the_default_travels_from_the_field(self) -> None:
        # Not prose-pinning: both sides are the page's, and what this asserts
        # is that the default reaches the file rather than being copied out
        # on the way.
        self.assertIn(default_book(), self.skill)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subdomain", help="the account's workers.dev subdomain name")
    parser.add_argument("--out", type=Path, help="where to write the zip")
    parser.add_argument(
        # Not `default=default_book()`: that reads the page when the parser
        # is built, so `--print-endpoint` -- which `worker-deploy.yml` calls,
        # and which has nothing to do with the page's prose -- would die on a
        # page edit that moved the `value=` attribute. Resolved at use.
        "--book",
        help="one line on what the notes are for (default: the page's)",
    )
    parser.add_argument(
        "--print-endpoint",
        action="store_true",
        help="print the inbox's address and stop, so a caller need not build it",
    )
    args = parser.parse_args(argv)

    if args.print_endpoint:
        if not args.subdomain:
            parser.error("--print-endpoint needs --subdomain")
        print(compose(worker_name(), args.subdomain))
        return 0
    if not args.subdomain or not args.out:
        parser.error("--subdomain and --out are both required")

    token = sys.stdin.read().strip()
    if len(token) < 16:
        sys.exit("no token on stdin, or one too short to be the real one")

    return build(
        compose(worker_name(), args.subdomain),
        token,
        args.book or default_book(),
        args.out,
    )


if __name__ == "__main__":
    sys.exit(main())
