#!/usr/bin/env python3
"""Build the note-taker's skill zip outside the browser.

`site/skill/index.html` is the generator, and it is a page rather than an
endpoint so that the intake token never leaves the machine that types it. That
is the right design for anyone who has to set this up from a phone, and it has
one cost: the author types a token they already gave the repository, into a
form, to produce a file the deploy could have handed them.

So the deploy builds the same zip. Not a second generator -- the page's script
is pulled out and run under node, exactly as `tools/check_skill_page.py` does,
because two implementations of the skill would drift and the drift would be
invisible until a note-taking session behaved oddly.

The token is read from stdin. An argument is in the process table and in the
log of anything that traces the runner; stdin is neither.

Usage:
    tools/make_skill.py --subdomain NAME --out PATH [--book LINE] < token
    tools/make_skill.py --subdomain NAME --print-endpoint
    tools/make_skill.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from check_skill_page import extract_script

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "skill" / "index.html"
WRANGLER = ROOT / "worker" / "notes-intake" / "wrangler.jsonc"

DEFAULT_BOOK = "a book about software, written in Typst"

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


def worker_name(config: Path) -> str:
    """The deployed worker's name, from the only place that decides it.

    Read with a regex rather than a JSON parser because the file is JSONC and
    is full of comments; the field is one line and unambiguous, and a parser
    that strips comments correctly is more code than the thing it enables.
    """
    match = re.search(r'"name"\s*:\s*"([^"]+)"', config.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"{config}: no worker name in it")
    return match.group(1)


def endpoint_for(subdomain: str, config: Path = WRANGLER) -> str:
    """The inbox's address: the worker, on the account's workers.dev subdomain.

    `subdomain` is what the account is called, not a hostname -- the deploy
    reads it from Cloudflare's API, so `software-fleet` arrives rather than
    `software-fleet.workers.dev`. Tolerating the longer form costs one strip
    and saves a confusing double suffix.
    """
    name = subdomain.strip().removesuffix(".workers.dev")
    if not name or "/" in name or "." in name:
        sys.exit(f"{subdomain!r} is not a workers.dev subdomain name")
    return f"https://{worker_name(config)}.{name}.workers.dev"


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


def self_test() -> int:
    assert (
        endpoint_for("software-fleet")
        == "https://notes-intake.software-fleet.workers.dev"
    )
    # The API returns the bare name; a person pasting from a browser does not.
    assert endpoint_for("software-fleet.workers.dev") == endpoint_for("software-fleet")
    assert worker_name(WRANGLER) == "notes-intake"

    if not shutil.which("node"):
        print("make_skill: addresses agree (node absent, so the zip is unbuilt)")
        return 0

    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "skill.zip"
        build(
            "https://notes-intake.example.workers.dev",
            "a-very-long-random-intake-token",
            DEFAULT_BOOK,
            out,
        )
        with zipfile.ZipFile(out) as archive:
            assert archive.namelist() == ["file-note/SKILL.md"]
            skill = archive.read("file-note/SKILL.md").decode("utf-8")
    # The two values that make the skill work at all, rather than the prose
    # around them, which is the page's to change.
    assert "notes-intake.example.workers.dev/note" in skill
    assert "a-very-long-random-intake-token" in skill
    print("make_skill: the deploy's zip is the page's zip")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subdomain", help="the account's workers.dev subdomain name")
    parser.add_argument("--out", type=Path, help="where to write the zip")
    parser.add_argument(
        "--book", default=DEFAULT_BOOK, help="one line on what the notes are for"
    )
    parser.add_argument(
        "--print-endpoint",
        action="store_true",
        help="print the inbox's address and stop, so a caller need not build it",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.print_endpoint:
        if not args.subdomain:
            parser.error("--print-endpoint needs --subdomain")
        print(endpoint_for(args.subdomain))
        return 0
    if not args.subdomain or not args.out:
        parser.error("--subdomain and --out are both required")

    token = sys.stdin.read().strip()
    if len(token) < 16:
        sys.exit("no token on stdin, or one too short to be the real one")

    return build(endpoint_for(args.subdomain), token, args.book, args.out)


if __name__ == "__main__":
    sys.exit(main())
