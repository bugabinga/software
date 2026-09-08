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
from pathlib import Path


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    info_file = out / "build-info.json"
    if not info_file.is_file():
        sys.exit(f"no build to summarise at {info_file}")
    info = json.loads(info_file.read_text(encoding="utf-8"))

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
    print("\n".join(lines))


if __name__ == "__main__":
    main()
