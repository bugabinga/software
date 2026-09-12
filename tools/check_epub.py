#!/usr/bin/env python3
"""Check that an EPUB is one, before anybody downloads it.

Not a full EPUBCheck -- that is a Java program and this tree has no runtime
but Python. It checks the things that decide whether a reader opens the file
at all, which is most of what goes wrong when a container is generated rather
than exported:

- `mimetype` first in the archive and stored uncompressed, which is how a
  reader identifies the file without unzipping it;
- `META-INF/container.xml` pointing at a package document that exists;
- every XML document well-formed, because a reading system may parse with an
  XML parser and reject the book outright rather than recovering;
- every manifest item present in the archive, and every spine reference
  resolving to a manifest item -- a dangling one is a chapter that silently
  does not appear;
- a navigation document, a title, a language and an identifier, without which
  the file is not EPUB 3.

Exits non-zero on the first file that fails, naming what and where.

Usage:
    tools/check_epub.py dist/book.epub [more.epub ...]
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"

XML_SUFFIXES = (".xhtml", ".opf", ".xml", ".ncx")


def check(path: Path) -> list[str]:
    problems: list[str] = []
    if not path.is_file():
        return [f"{path}: no such file"]

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        return [f"{path}: not a zip archive ({error})"]

    with archive:
        names = archive.namelist()
        entries = archive.infolist()

        if not entries or entries[0].filename != "mimetype":
            first = entries[0].filename if entries else "(empty archive)"
            problems.append(f"{path}: first entry is {first!r}, must be 'mimetype'")
        elif entries[0].compress_type != zipfile.ZIP_STORED:
            problems.append(f"{path}: mimetype is compressed, must be stored")
        elif archive.read("mimetype") != b"application/epub+zip":
            problems.append(f"{path}: mimetype does not read application/epub+zip")

        for name in names:
            if name.endswith(XML_SUFFIXES):
                try:
                    ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError as error:
                    problems.append(f"{path}: {name} is not well-formed XML: {error}")

        if "META-INF/container.xml" not in names:
            return problems + [f"{path}: no META-INF/container.xml"]

        try:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        except ElementTree.ParseError as error:
            return problems + [f"{path}: container.xml is malformed: {error}"]

        rootfile = container.find(f".//{{{CONTAINER}}}rootfile")
        opf_path = rootfile.get("full-path") if rootfile is not None else None
        if not opf_path:
            return problems + [f"{path}: container.xml names no package document"]
        if opf_path not in names:
            return problems + [
                f"{path}: package document {opf_path} is not in the archive"
            ]

        try:
            package = ElementTree.fromstring(archive.read(opf_path))
        except ElementTree.ParseError as error:
            return problems + [f"{path}: {opf_path} is malformed: {error}"]

        base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
        manifest = {
            item.get("id"): item
            for item in package.findall(f".//{{{OPF}}}manifest/{{{OPF}}}item")
        }
        if not manifest:
            problems.append(f"{path}: the manifest is empty")

        for item in manifest.values():
            href = item.get("href") or ""
            # Remote resources are legal; anything local must be present.
            if "://" in href:
                continue
            if f"{base}{href}" not in names:
                problems.append(
                    f"{path}: manifest lists {href}, which is not in the archive"
                )

        spine = package.findall(f".//{{{OPF}}}spine/{{{OPF}}}itemref")
        if not spine:
            problems.append(
                f"{path}: the spine is empty, so the book has no reading order"
            )
        for ref in spine:
            if ref.get("idref") not in manifest:
                problems.append(
                    f"{path}: spine references {ref.get('idref')!r}, "
                    "which is not in the manifest"
                )

        if not any(
            "nav" in (i.get("properties") or "").split() for i in manifest.values()
        ):
            problems.append(
                f'{path}: no navigation document (an item with properties="nav")'
            )

        for tag, what in (
            ("title", "a title"),
            ("language", "a language"),
            ("identifier", "an identifier"),
        ):
            if package.find(f".//{{{DC}}}{tag}") is None:
                problems.append(f"{path}: the package declares no {what}")

        if package.find(f'.//{{{OPF}}}meta[@property="dcterms:modified"]') is None:
            problems.append(f"{path}: no dcterms:modified, which EPUB 3 requires")

    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    failed = 0
    for name in argv:
        path = Path(name)
        problems = check(path)
        for problem in problems:
            print(
                f"::error::{problem}"
                if "GITHUB_ACTIONS" in __import__("os").environ
                else problem,
                file=sys.stderr,
            )
        if problems:
            failed += 1
        else:
            size = path.stat().st_size / 1024
            print(f"{path}: valid EPUB 3 ({size:.0f} KB)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
