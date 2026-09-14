#!/usr/bin/env python3
"""Name the release's files after the book and the tag, and check them.

A Python heredoc nested inside a shell heredoc inside YAML, to slugify one
string. The slug decides what a reader downloads, and it is the one part of a
release that cannot be corrected afterwards: assets are named once.

Usage:
    tools/release_assets.py --tag v0.2.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import unittest
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


class Slugs(unittest.TestCase):
    """A title as a filename. Release assets are named once."""

    def test_shapes(self) -> None:
        for title, want in (
            ("A Book Written in Types", "a-book-written-in-types"),
            ("Software: A Memoir", "software-a-memoir"),
            ("  Leading and trailing  ", "leading-and-trailing"),
            ("Types & Values", "types-values"),
            ("C++", "c"),
            ("\u00dcber Software", "ber-software"),
        ):
            with self.subTest(title=title):
                self.assertEqual(slug(title), want)

    def test_it_is_always_a_usable_filename(self) -> None:
        # Never doubled, never leading or trailing -- each of those makes a
        # name somebody has to quote.
        for title in ("A Book", "!!!", "a---b", "-x-"):
            with self.subTest(title=title):
                made = slug(title)
                self.assertNotIn("--", made)
                self.assertFalse(made.startswith("-"))
                self.assertFalse(made.endswith("-"))


class Sizes(unittest.TestCase):
    def test_units(self) -> None:
        for size, want in (
            (0, "0 B"),
            (999, "999 B"),
            (1536, "1.5 KB"),
            (5 * 1024 * 1024, "5.0 MB"),
        ):
            with self.subTest(size=size):
                self.assertEqual(human(size), want)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    arguments = parser.parse_args(argv)

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
