#!/usr/bin/env python3
"""Check that the skill generator produces a real zip.

The page at `site/skill/index.html` writes a zip container by hand, in the
browser, so that the intake token never leaves it. That is the right design
and it has an obvious failure mode: a zip that no unzip will open, discovered
by the author at the moment they are trying to set up their note-taker.

So the script is pulled out of the page, run under node exactly as shipped,
and the bytes it produces are opened with Python's `zipfile`. Two runtimes
have to agree that it is a zip before it is published.

Testing a copy of the zip writer would test the wrong thing, which is why the
page's DOM wiring is guarded rather than the logic being duplicated into a
test file.

Usage:
    tools/check_skill_page.py [site/skill/index.html]
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "site" / "skill" / "index.html"

DRIVER = """
const api = require("./page.cjs");

const md = api.skillMarkdown({
  endpoint: "https://notes-intake.example.workers.dev",
  token: "a-very-long-random-intake-token",
  book: "a book about software, written in Typst",
});

api.zip({ "file-note/SKILL.md": md }).arrayBuffer().then((buffer) => {
  require("node:fs").writeFileSync("out.zip", Buffer.from(buffer));
  console.log(JSON.stringify({ markdownBytes: Buffer.byteLength(md) }));
});
"""


def extract_script(page: Path) -> str:
    html = page.read_text(encoding="utf-8")
    match = re.search(r"<script>\n(.*?)\n</script>", html, re.S)
    if not match:
        sys.exit(f"{page}: no <script> block to test")
    return match.group(1)


def main(argv: list[str]) -> int:
    page = Path(argv[0]) if argv else PAGE
    if not page.is_file():
        sys.exit(f"{page}: no such file")

    node = shutil.which("node")
    if not node:
        print("node not installed; CI checks the skill page on every pull request")
        return 0

    script = extract_script(page)
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        # `.cjs` so node treats it as CommonJS whatever the page contains, and
        # `module.exports` is what the page's export guard writes to.
        (work / "page.cjs").write_text(script, encoding="utf-8")
        (work / "driver.cjs").write_text(DRIVER, encoding="utf-8")

        done = subprocess.run(
            [node, "driver.cjs"], cwd=work, capture_output=True, text=True, timeout=60
        )
        if done.returncode != 0:
            print(done.stdout, file=sys.stderr)
            print(done.stderr, file=sys.stderr)
            sys.exit(f"{page}: the script failed under node")

        produced = work / "out.zip"
        if not produced.is_file():
            sys.exit(f"{page}: the script ran but wrote no zip")

        # The real test: another implementation, in another language, opens it.
        try:
            with zipfile.ZipFile(produced) as archive:
                bad = archive.testzip()
                if bad:
                    sys.exit(f"{page}: {bad} fails its CRC")
                names = archive.namelist()
                if names != ["file-note/SKILL.md"]:
                    sys.exit(f"{page}: unexpected contents {names}")
                skill = archive.read(names[0]).decode("utf-8")
        except zipfile.BadZipFile as error:
            sys.exit(f"{page}: not a valid zip -- {error}")

        meta = json.loads(done.stdout.strip().splitlines()[-1])

    # And the skill inside it has to be a skill: Claude reads the frontmatter
    # to decide when it applies, so a missing `name` or `description` is a
    # skill that never fires.
    for required in ("---\nname: file-note", "description:"):
        if required not in skill:
            sys.exit(f"{page}: the generated SKILL.md has no {required.strip()!r}")
    if "notes-intake.example.workers.dev/note" not in skill:
        sys.exit(f"{page}: the endpoint did not reach the generated skill")
    if "a-very-long-random-intake-token" not in skill:
        sys.exit(f"{page}: the token did not reach the generated skill")

    written = len(skill.encode("utf-8"))
    if written != meta["markdownBytes"]:
        sys.exit(
            f"{page}: the zip holds {written} bytes but the script generated "
            f"{meta['markdownBytes']} -- something is being re-encoded"
        )
    print(f"skill page: valid zip, {written} bytes of SKILL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
