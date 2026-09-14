#!/usr/bin/env python3
"""Print a Markdown summary of a build.

Used for the GitHub Actions job summary and for the pull-request preview
comment, so both say the same thing.

Usage:
    tools/summary.py [dist]
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


def render(out: Path) -> str:
    """The table itself, so it can be built without a shell and a file."""
    info = json.loads((out / "build-info.json").read_text(encoding="utf-8"))

    lines = [f"### {info['title']}", ""]
    edition = info.get("edition")
    if edition:
        lines.append(f"Edition `{edition}` · built {info['built']}")
        lines.append("")

    lines.append("| # | Chapter | Words |")
    lines.append("| --: | --- | --: |")
    for chapter in info["chapters"]:
        number = chapter["number"] or ""
        lines.append(f"| {number} | {chapter['title']} | {chapter['words']:,} |")
    lines.append(f"| | **{len(info['chapters'])} chapters** | **{info['words']:,}** |")
    lines.append("")

    pdf = out / "book.pdf"
    if pdf.is_file():
        size = pdf.stat().st_size / 1024
        lines.append(f"PDF: {size:,.0f} KB")
    return "\n".join(lines)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    if not (out / "build-info.json").is_file():
        sys.exit(f"no build to summarise at {out / 'build-info.json'}")
    print(render(out))


class Rendering(unittest.TestCase):
    """The same table reaches the job summary and the preview comment, so a
    change here shows up in two places at once."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dist = Path(tmp.name)
        (self.dist / "build-info.json").write_text(
            json.dumps(
                {
                    "title": "A Book",
                    "edition": "draft",
                    "built": "2026-09-15T00:00:00Z",
                    "chapters": [
                        {"slug": "one", "title": "One", "number": 1, "words": 100},
                        {
                            "slug": "pre",
                            "title": "Preface",
                            "number": None,
                            "words": 50,
                        },
                    ],
                    "words": 150,
                }
            ),
            encoding="utf-8",
        )

    def test_it_names_the_book_and_counts_it(self) -> None:
        text = render(self.dist)
        self.assertIn("A Book", text)
        self.assertIn("150", text)
        self.assertIn("One", text)

    def test_an_unnumbered_chapter_still_appears(self) -> None:
        # Front matter has no number, and dropping it would silently shorten
        # the table.
        self.assertIn("Preface", render(self.dist))


if __name__ == "__main__":
    main()
