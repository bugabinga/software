#!/usr/bin/env python3
"""Check every internal link in the built site.

A broken cross-reference is the most common way a book rots, and the most
annoying for a reader to hit, so this runs on every build rather than only in
CI: every `href` and `src` that stays inside the site must resolve to a file
that exists, and every `#fragment` must resolve to an id that exists in the
page it points at.

External links are not checked here -- CI does that with lychee, which can
retry and cache. Standard library only.

Usage:
    tools/check_links.py [dist]
"""

from __future__ import annotations

import posixpath
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

LINK_ATTRIBUTES = {
    "a": "href",
    "area": "href",
    "img": "src",
    "link": "href",
    "script": "src",
    "source": "src",
    "iframe": "src",
}

EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel", "data", "javascript"}


@dataclass
class Page:
    path: Path
    ids: set[str] = field(default_factory=set)
    links: list[tuple[str, str]] = field(default_factory=list)  # (attr value, tag)


class PageParser(HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__(convert_charrefs=True)
        self.page = page

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if identifier := values.get("id"):
            self.page.ids.add(identifier)
        # `name` still anchors in HTML5 for <a>.
        if tag == "a" and (name := values.get("name")):
            self.page.ids.add(name)
        attribute = LINK_ATTRIBUTES.get(tag)
        if attribute and (target := values.get(attribute)):
            self.page.links.append((target, tag))


def read_pages(root: Path) -> dict[Path, Page]:
    pages: dict[Path, Page] = {}
    for path in sorted(root.rglob("*.html")):
        page = Page(path=path)
        PageParser(page).feed(path.read_text(encoding="utf-8", errors="replace"))
        pages[path] = page
    return pages


def resolve(root: Path, page: Path, target: str) -> Path:
    """The file a link points at, as an absolute path inside the site."""
    if target.startswith("/"):
        base = root
        relative = target.lstrip("/")
    else:
        base = page.parent
        relative = target
    resolved = Path(posixpath.normpath(str(base / unquote(relative))))
    if str(resolved).endswith("/") or resolved.is_dir():
        resolved = resolved / "index.html"
    return resolved


def check(root: Path) -> list[str]:
    pages = read_pages(root)
    if not pages:
        return [f"{root}: no HTML files to check -- did the build run?"]

    problems: list[str] = []
    for path, page in pages.items():
        where = path.relative_to(root)
        for target, tag in page.links:
            split = urlsplit(target)
            if split.scheme in EXTERNAL_SCHEMES or split.netloc:
                continue
            if not split.path and not split.fragment:
                continue  # an empty href, harmless

            if split.path:
                destination = resolve(root, path, split.path)
                if not destination.exists():
                    problems.append(
                        f"{where}: <{tag}> points at {target!r}, which does not exist"
                    )
                    continue
            else:
                destination = path  # same-page fragment

            if split.fragment:
                if destination.suffix != ".html":
                    continue
                target_page = pages.get(destination)
                if target_page is None:
                    target_page = Page(path=destination)
                    PageParser(target_page).feed(
                        destination.read_text(encoding="utf-8", errors="replace")
                    )
                    pages[destination] = target_page
                if unquote(split.fragment) not in target_page.ids:
                    problems.append(
                        f"{where}: <{tag}> points at {target!r}, "
                        "but that page has no such id"
                    )
    return problems


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    if not root.is_dir():
        sys.exit(f"{root} does not exist -- run `make build` first")

    problems = check(root)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(f"{len(problems)} broken internal link(s)")

    pages = len(list(root.rglob("*.html")))
    print(f"internal links: {pages} pages, no broken links")


if __name__ == "__main__":
    main()
