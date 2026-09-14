#!/usr/bin/env python3
"""Name the release's files after the book and the tag, and check them.

A Python heredoc nested inside a shell heredoc inside YAML, to slugify one
string. The slug decides what a reader downloads, and it is the one part of a
release that cannot be corrected afterwards: assets are named once.

Usage:
    tools/release_assets.py --tag v0.2.0
    tools/release_assets.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

from fleetlib import notice, output, summary

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
OUT = ROOT / "release"

# Every build the release attaches, and the extension it keeps.
PARTS = ("book.pdf", "book.epub", "book.html")


def slug(title: str) -> str:
    """A title as a filename: lowercase, one hyphen between runs of other."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def human(size: int) -> str:
    scaled = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if scaled < 1024 or unit == "GB":
            return f"{scaled:.0f} {unit}" if unit == "B" else f"{scaled:.1f} {unit}"
        scaled /= 1024
    return f"{scaled:.0f} B"


def self_test() -> int:
    assert slug("A Book Written in Types") == "a-book-written-in-types"
    # The shapes a title can actually take, all of which the regex meets.
    assert slug("Software: A Memoir") == "software-a-memoir"
    assert slug("  Leading and trailing  ") == "leading-and-trailing"
    assert slug("Types & Values") == "types-values"
    assert slug("C++") == "c"
    assert slug("Über Software") == "ber-software", "non-ascii is dropped, not mangled"
    # A slug is never empty, never starts or ends with a hyphen, and never
    # doubles one -- each of those makes a filename somebody has to quote.
    for title in ("A Book", "!!!", "a---b", "-x-"):
        made = slug(title)
        assert "--" not in made and not made.startswith("-") and not made.endswith("-")

    assert human(0) == "0 B"
    assert human(999) == "999 B"
    assert human(1536) == "1.5 KB"
    assert human(5 * 1024 * 1024) == "5.0 MB"

    print("release_assets: six slug shapes, four sizes")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--tag")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()
    if not arguments.tag:
        parser.error("--tag is required")
    tag = arguments.tag

    title = json.loads((DIST / "build-info.json").read_text(encoding="utf-8"))["title"]
    stem = f"{slug(title)}-{tag}"
    OUT.mkdir(exist_ok=True)

    for part in PARTS:
        shutil.copy2(DIST / part, OUT / f"{stem}{Path(part).suffix}")

    site = OUT / f"{stem}-site.zip"
    with zipfile.ZipFile(site, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(DIST.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DIST))

    made = sorted(p for p in OUT.iterdir() if p.is_file())
    (OUT / "SHA256SUMS.txt").write_text(
        "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in made
        ),
        encoding="utf-8",
    )

    rows = "\n".join(
        f"| `{p.name}` | {human(p.stat().st_size)} |"
        for p in sorted(OUT.iterdir())
        if p.is_file()
    )
    summary(f"### {slug(title)} {tag}\n\n| file | size |\n| --- | --- |\n{rows}")
    output("tag", tag)
    notice(f"{len(made) + 1} asset(s) named {stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
