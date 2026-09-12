#!/usr/bin/env python3
"""Build the book.

Two outputs from one source tree:

  * the website -- each chapter compiled to semantic HTML by Typst, then
    wrapped in the page shell from `site/templates/`, with navigation, an
    in-page table of contents and a search index generated here;
  * the PDF -- `book/book.typ` compiled as a single document, so that
    cross-references and page numbers work.

Chapter order and metadata come from `book/book.toml`, which is also read by
`book/book.typ`, so the two outputs cannot disagree about what the book is.

Usage:
    tools/build.py                     # build ./dist
    tools/build.py --strict            # also fail on unexpected Typst warnings
    tools/build.py --serve             # build, then serve and rebuild on change
    tools/build.py --no-pdf            # skip the PDF (faster while writing)

Standard library only, so CI needs nothing but Python and the Typst binary.
"""

from __future__ import annotations

import argparse
import html as html_escape
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

if sys.version_info < (3, 11):
    sys.exit("tools/build.py requires Python 3.11 or newer (for tomllib)")

import tomllib

# A sibling module, so the directory this file lives in has to be importable
# when the script is run by path from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from epub import build_epub
from pinned import pins as _pins


def pinned(tool: str) -> str:
    return _pins()[tool]


ROOT = Path(__file__).resolve().parent.parent
BOOK_DIR = ROOT / "book"
SITE_DIR = ROOT / "site"
MANIFEST = BOOK_DIR / "book.toml"
TEMPLATES = SITE_DIR / "templates"

# Typst warnings that are expected and must not fail even a strict build.
# Anything not matched here is treated as a defect in the book's source.
ALLOWED_WARNINGS = ("html export is under active development and incomplete",)


# --------------------------------------------------------------------------- #
# Typst
# --------------------------------------------------------------------------- #


def typst_pin() -> str:
    """The Typst version this tree is pinned to, per `mise.toml`."""
    return pinned("typst")


def typst_binary() -> str:
    """The Typst to build with: $TYPST, then a local install, then $PATH."""
    if env := os.environ.get("TYPST"):
        return env
    local = ROOT / ".tools" / "typst" / "typst"
    if local.is_file():
        return str(local)
    found = shutil.which("typst")
    if not found:
        sys.exit(
            "no typst binary found.\n"
            "  run `mise install` to install the pinned version into .tools/,\n"
            "  or set TYPST=/path/to/typst"
        )
    return found


class TypstError(RuntimeError):
    pass


def run_typst(binary: str, args: list[str]) -> list[str]:
    """Run Typst, returning the warnings it emitted. Raises on failure."""
    result = subprocess.run(  # noqa: PLW1510 - the warnings are the return value
        [binary, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TypstError(result.stderr.strip() or "typst failed with no output")
    return collect_warnings(result.stderr)


def collect_warnings(stderr: str) -> list[str]:
    """Pull the `warning:` headlines out of Typst's diagnostics."""
    warnings = []
    for line in stderr.splitlines():
        if line.startswith("warning:"):
            warnings.append(line[len("warning:") :].strip())
    return warnings


def unexpected(warnings: list[str]) -> list[str]:
    return [w for w in warnings if not any(a in w for a in ALLOWED_WARNINGS)]


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


@dataclass
class Chapter:
    source: Path  # e.g. book/chapters/01-the-pipeline.typ
    relative: str  # e.g. chapters/01-the-pipeline.typ, as written in book.toml
    slug: str  # e.g. the-pipeline
    part: str  # part title, or "" when ungrouped
    numbered: bool
    number: int | None = None

    title_html: str = ""
    title_text: str = ""
    content: str = ""
    typst_head: str = ""
    sections: list[tuple[int, str, str]] = field(default_factory=list)
    text: str = ""
    summary: str = ""
    words: int = 0

    @property
    def url(self) -> str:
        return f"{self.slug}/"

    @property
    def label(self) -> str:
        """How the chapter is named in navigation."""
        if self.number is None:
            return self.title_html
        return f'<span class="num">{self.number}</span> {self.title_html}'


@dataclass
class Book:
    meta: dict
    chapters: list[Chapter]

    @property
    def title(self) -> str:
        return self.meta.get("title", "Untitled")

    @property
    def language(self) -> str:
        return self.meta.get("language", "en")

    @property
    def base_url(self) -> str:
        base = self.meta.get("base-url", "").strip()
        return base.rstrip("/") + "/" if base else ""

    @property
    def base_path(self) -> str:
        """The path the site is served under, e.g. `/software/` on Pages.

        The 404 page needs it: GitHub Pages serves that page for any missing
        path under the project, at any depth, so its one link home has to be
        absolute -- and absolute means including this prefix, not `/`.
        """
        if not self.base_url:
            return "/"
        path = urlsplit(self.base_url).path or "/"
        return path if path.endswith("/") else path + "/"


def slug_of(relative: str) -> str:
    """Publishing slug for a chapter path.

    Mirrors `slug-of` in `book/lib/prelude.typ`: the file stem without its
    ordering prefix, so `chapters/01-the-pipeline.typ` is served at
    `the-pipeline/` and can be reordered without breaking its URL.
    """
    stem = Path(relative).stem
    return re.sub(r"^[0-9]+[-_]", "", stem)


def load_book() -> Book:
    if not MANIFEST.is_file():
        sys.exit(f"missing manifest: {MANIFEST.relative_to(ROOT)}")
    with MANIFEST.open("rb") as handle:
        manifest = tomllib.load(handle)

    meta = manifest.get("book", {})
    chapters: list[Chapter] = []
    seen: dict[str, str] = {}
    number = 0

    for part in manifest.get("part", []):
        part_title = part.get("title", "")
        numbered = part.get("numbered", True)
        for relative in part.get("chapters", []):
            source = BOOK_DIR / relative
            if not source.is_file():
                sys.exit(
                    f"book.toml lists {relative}, which does not exist "
                    f"(looked in {source.parent.relative_to(ROOT)})"
                )
            slug = slug_of(relative)
            if slug in seen:
                sys.exit(
                    f"{relative} and {seen[slug]} both publish as '{slug}/'; "
                    "rename one of them"
                )
            seen[slug] = relative
            if numbered:
                number += 1
            chapters.append(
                Chapter(
                    source=source,
                    relative=relative,
                    slug=slug,
                    part=part_title,
                    numbered=numbered,
                    number=number if numbered else None,
                )
            )

    if not chapters:
        sys.exit("book.toml lists no chapters")
    return Book(meta=meta, chapters=chapters)


# --------------------------------------------------------------------------- #
# HTML post-processing
# --------------------------------------------------------------------------- #

HEAD_RE = re.compile(r"<head>(.*?)</head>", re.S)
BODY_RE = re.compile(r"<body[^>]*>(.*?)</body>", re.S)
HEADING_RE = re.compile(r"<h([1-5])([^>]*)>(.*?)</h\1>", re.S)
ID_RE = re.compile(r'id="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")


class TextExtractor(HTMLParser):
    """Visible text, for the search index and word counts."""

    SKIPPED: ClassVar[set[str]] = {"math", "script", "style", "figcaption"}
    SKIPPED_CLASSES: ClassVar[set[str]] = {"permalink", "copy-button"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        classes = set(dict(attrs).get("class", "").split())
        if tag in self.SKIPPED or classes & self.SKIPPED_CLASSES:
            self.depth += 1

    def handle_endtag(self, tag):
        # Closing tags carry no attributes, so an anchor closing inside a
        # skipped anchor simply ends the skip -- nesting of skipped elements
        # does not occur in the markup Typst emits.
        if (tag in self.SKIPPED or tag == "a") and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


def first_paragraph(body: str) -> str:
    """The chapter's opening paragraph, for meta descriptions."""
    match = re.search(r"<p>(.*?)</p>", body, re.S)
    return visible_text(match.group(1)) if match else ""


def visible_text(fragment: str) -> str:
    extractor = TextExtractor()
    extractor.feed(fragment)
    return extractor.text


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "\u2026"


def slugify(text: str) -> str:
    text = re.sub(r"\s+", "-", text.strip().lower())
    text = re.sub(r"[^a-z0-9\-_]", "", text)
    return re.sub(r"-{2,}", "-", text).strip("-") or "section"


def promote_headings(body: str) -> str:
    """Undo Typst's one-level shift.

    Typst's HTML export reserves `<h1>` for the document title and starts
    document headings at `<h2>`. The page shell supplies no competing `<h1>`,
    so shifting everything back up restores a natural outline: the chapter
    title is the page's `<h1>`, its sections are `<h2>`.
    """
    return re.sub(
        r"<(/?)h([2-6])\b",
        lambda m: f"<{m.group(1)}h{int(m.group(2)) - 1}",
        body,
    )


def index_headings(body: str) -> tuple[str, str, list[tuple[int, str, str]]]:
    """Give every heading a stable id and a permalink; collect the outline.

    Returns the rewritten body, the chapter title (the first `<h1>`), and the
    list of `(level, id, text)` for the in-page table of contents.
    """
    title = ""
    outline: list[tuple[int, str, str]] = []
    used: set[str] = set()

    def rewrite(match: re.Match[str]) -> str:
        nonlocal title
        level, attrs, inner = int(match.group(1)), match.group(2), match.group(3)
        text = visible_text(inner)

        existing = ID_RE.search(attrs)
        if existing:
            anchor = existing.group(1)
        else:
            anchor = slugify(text)
            candidate, suffix = anchor, 2
            while candidate in used:
                candidate, suffix = f"{anchor}-{suffix}", suffix + 1
            anchor = candidate
            attrs = f'{attrs} id="{anchor}"'
        used.add(anchor)

        if level == 1 and not title:
            # The chapter title is rendered by the shell, not by the article.
            title = inner.strip()
            return ""

        if 2 <= level <= 3:
            outline.append((level, anchor, text))

        permalink = (
            f'<a class="permalink" href="#{anchor}" '
            f'aria-label="Permalink to this section">#</a>'
        )
        return f"<h{level}{attrs}>{inner}{permalink}</h{level}>"

    body = HEADING_RE.sub(rewrite, body)
    return body, title, outline


def wrap_balanced(body: str, opening: str, tag: str, css_class: str) -> str:
    """Wrap every `opening` element in a `<div class=...>`.

    Wide content -- big equations, wide tables -- must scroll inside its own
    container rather than stretching the page, and neither `<math>` nor
    `<table>` can carry `overflow-x` reliably itself. The close tag is found by
    counting nested `<tag>`s, so a nested element cannot end the wrap early.
    """
    open_tag, close_tag = f"<{tag}", f"</{tag}>"
    out: list[str] = []
    position = 0
    while True:
        start = body.find(opening, position)
        if start == -1:
            out.append(body[position:])
            return "".join(out)

        depth, cursor = 0, start
        while cursor < len(body):
            next_open = body.find(open_tag, cursor + 1)
            next_close = body.find(close_tag, cursor + 1)
            if next_close == -1:
                # Malformed; leave the rest of the document untouched.
                out.append(body[position:])
                return "".join(out)
            if next_open != -1 and next_open < next_close:
                depth += 1
                cursor = next_open
                continue
            if depth == 0:
                end = next_close + len(close_tag)
                break
            depth -= 1
            cursor = next_close
        else:
            out.append(body[position:])
            return "".join(out)

        out.append(body[position:start])
        out.append(f'<div class="{css_class}">')
        out.append(body[start:end])
        out.append("</div>")
        position = end


def split_document(document: str, source: str) -> tuple[str, str]:
    """Separate Typst's `<head>` extras from the body content."""
    head = HEAD_RE.search(document)
    body = BODY_RE.search(document)
    if not head or not body:
        raise TypstError(
            f"unexpected HTML from typst for {source}: no <head>/<body> found. "
            "The HTML export format may have changed; tools/build.py needs updating."
        )
    # Keep whatever Typst puts in <head> (currently the MathML stylesheet) but
    # drop the parts the shell owns.
    extras = re.sub(r"<title>.*?</title>", "", head.group(1), flags=re.S)
    extras = re.sub(r"<meta[^>]*>", "", extras)
    return extras.strip(), body.group(1).strip()


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def render(template: str, values: dict[str, str]) -> str:
    """Fill `{{name}}` placeholders, failing loudly on an unknown one."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"template uses unknown placeholder {{{{{key}}}}}")
        return values[key]

    return re.sub(r"\{\{(\w+)\}\}", replace, template)


def esc(text: str) -> str:
    return html_escape.escape(text, quote=True)


def nav_html(book: Book, current: Chapter | None, prefix: str) -> str:
    """The sidebar: every chapter, grouped by part, with the current chapter's
    sections expanded underneath it."""
    out: list[str] = ['<nav class="toc" aria-label="Contents">']
    out.append(f'<a class="toc-home" href="{prefix}">{esc(book.title)}</a>')

    part = None
    open_list = False
    for chapter in book.chapters:
        if chapter.part != part:
            if open_list:
                out.append("</ul>")
            part = chapter.part
            if part:
                out.append(f'<p class="toc-part">{esc(part)}</p>')
            out.append("<ul>")
            open_list = True

        is_current = current is not None and chapter.slug == current.slug
        attrs = ' aria-current="page"' if is_current else ""
        out.append(
            f'<li class="{"current" if is_current else ""}">'
            f'<a href="{prefix}{chapter.url}"{attrs}>{chapter.label}</a>'
        )
        if is_current and chapter.sections:
            out.append('<ul class="toc-sections">')
            for level, anchor, text in chapter.sections:
                out.append(
                    f'<li class="level-{level}">'
                    f'<a href="#{anchor}">{esc(text)}</a></li>'
                )
            out.append("</ul>")
        out.append("</li>")

    if open_list:
        out.append("</ul>")
    out.append("</nav>")
    return "\n".join(out)


def page_toc_html(chapter: Chapter) -> str:
    if len(chapter.sections) < 2:
        return ""
    items = "\n".join(
        f'<li class="level-{level}"><a href="#{anchor}">{esc(text)}</a></li>'
        for level, anchor, text in chapter.sections
    )
    return (
        '<aside class="page-toc" aria-label="On this page">'
        "<p>On this page</p>"
        f"<ul>{items}</ul>"
        "</aside>"
    )


def prev_next_html(book: Book, chapter: Chapter) -> str:
    order = book.chapters
    position = order.index(chapter)
    previous = order[position - 1] if position > 0 else None
    following = order[position + 1] if position + 1 < len(order) else None

    links = []
    if previous:
        links.append(
            f'<a class="prev" href="../{previous.url}" rel="prev">'
            f"<span>Previous</span>{previous.title_html}</a>"
        )
    if following:
        links.append(
            f'<a class="next" href="../{following.url}" rel="next">'
            f"<span>Next</span>{following.title_html}</a>"
        )
    if not links:
        return ""
    return f'<nav class="pager" aria-label="Chapter navigation">{"".join(links)}</nav>'


def edit_link_html(book: Book, chapter: Chapter) -> str:
    repository = book.meta.get("repository", "").strip().rstrip("/")
    if not repository:
        return ""
    branch = book.meta.get("edit-branch", "main")
    url = f"{repository}/edit/{branch}/book/{chapter.relative}"
    return f'<a class="edit" href="{esc(url)}">Edit this page</a>'


def head_meta_html(book: Book, title: str, description: str, path: str) -> str:
    parts = [f'<meta name="description" content="{esc(description)}">']
    if book.base_url:
        canonical = book.base_url + path
        parts.append(f'<link rel="canonical" href="{esc(canonical)}">')
        parts.append(f'<meta property="og:url" content="{esc(canonical)}">')
    parts.append(f'<meta property="og:title" content="{esc(title)}">')
    parts.append(f'<meta property="og:site_name" content="{esc(book.title)}">')
    parts.append(f'<meta property="og:description" content="{esc(description)}">')
    parts.append('<meta property="og:type" content="article">')
    return "\n".join(parts)


# Reachable on the site and deliberately not part of the book: no navigation,
# no search index, no place in the contents. They were also, until this, not
# linked from anywhere at all -- `dist/skill/` had been serving for a day and
# the only way to find it was to know the URL, which is not "reachable".
#
# `when` is what a reader sees if they follow the link before the thing
# exists. The fleet report is written by Monday's run and pulled onto the site
# by the next publish, so it 404s until then and saying so is kinder than a
# dead link with no explanation.
STANDALONE = [
    {
        "url": "skill/",
        "name": "Skill generator",
        "blurb": "Builds the note-taker's Claude skill as a zip, in the browser.",
        "when": "",
    },
    {
        "url": "fleet/",
        "name": "Fleet report",
        "blurb": "What the agents did last week: runs, failures, cost, what merged.",
        "when": "published by Monday's run",
    },
]


def standalone_html() -> str:
    """The not-the-book pages, for the landing page's footer."""
    items = []
    for page in STANDALONE:
        when = (
            f' <span class="aside-when">{esc(page["when"])}</span>'
            if page["when"]
            else ""
        )
        items.append(
            f'<li><a href="{esc(page["url"])}">{esc(page["name"])}</a>{when}'
            f'<span class="aside-blurb">{esc(page["blurb"])}</span></li>'
        )
    return (
        '<nav class="aside-pages" aria-label="Not part of the book">'
        "<h2>Also here</h2><ul>" + "".join(items) + "</ul></nav>"
    )


def contents_html(book: Book) -> str:
    """The landing page's table of contents: chapters, with their sections."""
    out: list[str] = []
    part = None
    open_list = False
    for chapter in book.chapters:
        if chapter.part != part:
            if open_list:
                out.append("</ol>")
            part = chapter.part
            if part:
                out.append(f'<h2 class="contents-part">{esc(part)}</h2>')
            out.append('<ol class="contents">')
            open_list = True
        sections = "".join(
            f'<li><a href="{chapter.url}#{anchor}">{esc(text)}</a></li>'
            for level, anchor, text in chapter.sections
            if level == 2
        )
        out.append(
            f'<li><a class="contents-chapter" href="{chapter.url}">{chapter.label}</a>'
            + (f'<ul class="contents-sections">{sections}</ul>' if sections else "")
            + "</li>"
        )
    if open_list:
        out.append("</ol>")
    return "\n".join(out)


DEV_SCRIPT = """<script>
// Development only: reload when the build counter changes.
(function () {
  let seen = null;
  setInterval(async function () {
    try {
      const response = await fetch("/__build", { cache: "no-store" });
      const value = await response.text();
      if (seen === null) seen = value;
      else if (value !== seen) location.reload();
    } catch (error) {
      /* server restarting */
    }
  }, 600);
})();
</script>"""


# --------------------------------------------------------------------------- #
# The build
# --------------------------------------------------------------------------- #


def compile_chapters(
    book: Book,
    binary: str,
    build_dir: Path,
    only: list[Chapter] | None = None,
) -> list[str]:
    """Compile chapters to HTML and fill in their parsed content."""
    entries = build_dir / "entry"
    raw = build_dir / "html"
    entries.mkdir(parents=True, exist_ok=True)
    raw.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    for chapter in only if only is not None else book.chapters:
        entry = entries / f"{chapter.slug}.typ"
        entry.write_text(
            "// Generated by tools/build.py -- edit the chapter, not this file.\n"
            '#import "/book/lib/styles.typ"\n'
            '#show: styles.web.with(toml("/book/book.toml"))\n'
            f'#include "/book/{chapter.relative}"\n',
            encoding="utf-8",
        )
        output = raw / f"{chapter.slug}.html"
        warnings += run_typst(
            binary,
            [
                "compile",
                "--root",
                ".",
                "--features",
                "html",
                "--format",
                "html",
                "--pretty",
                "--ignore-system-fonts",
                "--font-path",
                "book/fonts",
                str(entry.relative_to(ROOT)),
                str(output.relative_to(ROOT)),
            ],
        )

        head, body = split_document(
            output.read_text(encoding="utf-8"), chapter.relative
        )
        body = promote_headings(body)
        body = wrap_balanced(body, '<math display="block">', "math", "math-scroll")
        body = wrap_balanced(body, "<table", "table", "table-scroll")
        body, title, sections = index_headings(body)
        if not title:
            sys.exit(
                f"{chapter.relative} has no level-one heading; "
                "every chapter needs `= Chapter title` as its first heading"
            )
        chapter.typst_head = head
        chapter.content = body.strip()
        chapter.title_html = title
        chapter.title_text = visible_text(title)
        chapter.sections = sections
        chapter.text = visible_text(body)
        chapter.summary = truncate(first_paragraph(body), 170)
        chapter.words = len(chapter.text.split())
    return warnings


ID_ATTR_RE = re.compile(r'\bid="([^"]+)"')
FRAGMENT_RE = re.compile(r'href="#([^"]+)"')


def namespace_ids(body: str, prefix: str) -> str:
    """Make one chapter's ids unique so several can share a page.

    Typst numbers footnote anchors per document -- every chapter has its own
    `loc-1` -- so concatenating chapters without this makes every footnote in
    the single-file build point at the first chapter's notes.
    """
    body = ID_ATTR_RE.sub(lambda m: f'id="{prefix}--{m.group(1)}"', body)
    return FRAGMENT_RE.sub(lambda m: f'href="#{prefix}--{m.group(1)}"', body)


def localise_xrefs(body: str, slugs: set[str]) -> str:
    """Turn cross-chapter links into in-page ones."""
    for slug in slugs:
        body = body.replace(f'href="../{slug}/#', f'href="#{slug}--')
        body = body.replace(f'href="../{slug}/"', f'href="#{slug}"')
    return body


def build_single_page(book: Book, out_dir: Path) -> Path:
    """The whole book as one self-contained HTML file.

    No external stylesheet, no script, no separate assets: images are already
    data URIs in Typst's export, so the result is a single file that reads
    offline, prints, and can be handed to anything that renders HTML. It is
    also what makes the book readable somewhere other than a Pages site.
    """
    template = (TEMPLATES / "single.html").read_text(encoding="utf-8")
    stylesheet = (SITE_DIR / "assets" / "book.css").read_text(encoding="utf-8")
    slugs = {chapter.slug for chapter in book.chapters}

    sections: list[str] = []
    contents: list[str] = []
    part = None
    for chapter in book.chapters:
        body = localise_xrefs(namespace_ids(chapter.content, chapter.slug), slugs)
        eyebrow = (
            f"Chapter {chapter.number}" if chapter.number is not None else chapter.part
        )
        sections.append(
            f'<section class="chapter" id="{chapter.slug}">'
            + (f'<p class="eyebrow">{esc(eyebrow)}</p>' if eyebrow else "")
            + f"<h1>{chapter.title_html}</h1>{body}</section>"
        )
        if chapter.part != part:
            part = chapter.part
            if part:
                contents.append(f'<li class="part">{esc(part)}</li>')
        contents.append(f'<li><a href="#{chapter.slug}">{chapter.label}</a></li>')

    # Typst's <head> additions (the MathML stylesheet) are identical for every
    # chapter, so one copy suffices.
    typst_head = book.chapters[0].typst_head if book.chapters else ""

    page = render(
        template,
        {
            "lang": book.language,
            "title": esc(book.title),
            "book_title": esc(book.title),
            "subtitle": esc(book.meta.get("subtitle", "")),
            "authors": esc(", ".join(book.meta.get("authors", []))),
            "description": esc(book.meta.get("description", "")),
            "edition": esc(book.meta.get("edition", "")),
            "style": stylesheet,
            "typst_head": typst_head,
            "contents": "\n".join(contents),
            "content": "\n".join(sections),
        },
    )
    destination = out_dir / "book.html"
    destination.write_text(page, encoding="utf-8")
    return destination


def write_pages(book: Book, out_dir: Path, dev: bool) -> None:
    page_template = (TEMPLATES / "page.html").read_text(encoding="utf-8")
    index_template = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    not_found_template = (TEMPLATES / "404.html").read_text(encoding="utf-8")
    edition = book.meta.get("edition", "")
    dev_script = DEV_SCRIPT if dev else ""

    for chapter in book.chapters:
        eyebrow = ""
        if chapter.number is not None:
            eyebrow = f"Chapter {chapter.number}"
        elif chapter.part:
            eyebrow = chapter.part

        summary = chapter.summary or book.meta.get("description", "")

        page = render(
            page_template,
            {
                "lang": book.language,
                "title": esc(f"{chapter.title_text} — {book.title}"),
                "meta_head": head_meta_html(
                    book, chapter.title_text, summary, chapter.url
                ),
                "typst_head": chapter.typst_head,
                "prefix": "../",
                "book_title": esc(book.title),
                "nav": nav_html(book, chapter, "../"),
                "eyebrow": esc(eyebrow),
                "chapter_title": chapter.title_html,
                "page_toc": page_toc_html(chapter),
                "content": chapter.content,
                "pager": prev_next_html(book, chapter),
                "edit_link": edit_link_html(book, chapter),
                "edition": esc(edition),
                "dev_script": dev_script,
            },
        )
        destination = out_dir / chapter.slug / "index.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(page, encoding="utf-8")

    authors = ", ".join(book.meta.get("authors", []))
    index = render(
        index_template,
        {
            "lang": book.language,
            "title": esc(book.title),
            "meta_head": head_meta_html(
                book, book.title, book.meta.get("description", ""), ""
            ),
            "prefix": "",
            "book_title": esc(book.title),
            "subtitle": esc(book.meta.get("subtitle", "")),
            "description": esc(book.meta.get("description", "")),
            "authors": esc(authors),
            "nav": nav_html(book, None, ""),
            "contents": contents_html(book),
            "standalone": standalone_html(),
            "start_url": book.chapters[0].url,
            "edition": esc(edition),
            "dev_script": dev_script,
        },
    )
    (out_dir / "index.html").write_text(index, encoding="utf-8")

    (out_dir / "404.html").write_text(
        render(
            not_found_template,
            {
                "lang": book.language,
                "title": esc(f"Not found — {book.title}"),
                "heading": "That page is not part of this book",
                "message": esc(book.title),
                "home": esc(book.base_path),
            },
        ),
        encoding="utf-8",
    )


def write_search_index(book: Book, out_dir: Path) -> None:
    documents = [
        {
            "slug": chapter.slug,
            "url": f"{chapter.slug}/",
            "number": chapter.number,
            "title": chapter.title_text,
            "part": chapter.part,
            "sections": [
                {"id": anchor, "title": text} for _, anchor, text in chapter.sections
            ],
            # Enough text to search without shipping the whole book twice.
            "text": chapter.text[:20000],
        }
        for chapter in book.chapters
    ]
    (out_dir / "search-index.json").write_text(
        json.dumps({"book": book.title, "documents": documents}, ensure_ascii=False),
        encoding="utf-8",
    )


def write_site_files(book: Book, out_dir: Path, pdf: bool) -> None:
    # Pages would otherwise run the output through Jekyll.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    if book.base_url:
        urls = [""] + [chapter.url for chapter in book.chapters]
        entries = "\n".join(
            f"  <url><loc>{book.base_url}{url}</loc></url>" for url in urls
        )
        (out_dir / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{entries}\n</urlset>\n",
            encoding="utf-8",
        )
        (out_dir / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nSitemap: {book.base_url}sitemap.xml\n",
            encoding="utf-8",
        )

    info = {
        "title": book.title,
        "edition": book.meta.get("edition", ""),
        "base_path": book.base_path,
        "base_url": book.base_url,
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "typst": typst_pin(),
        "chapters": [
            {
                "slug": chapter.slug,
                "title": chapter.title_text,
                "number": chapter.number,
                "words": chapter.words,
            }
            for chapter in book.chapters
        ],
        "words": sum(chapter.words for chapter in book.chapters),
        "pdf": pdf,
    }
    (out_dir / "build-info.json").write_text(
        json.dumps(info, indent=2), encoding="utf-8"
    )


def write_fleet_placeholder(book: Book, out_dir: Path) -> None:
    """A page at `fleet/` before there is a report to put there.

    `publish.yml` writes the real one over this, from `report.html` on the
    `fleet-log` branch. Until Monday's first run there is nothing to write,
    and the landing page links here regardless -- so without this the link
    check fails the build, and removing the link instead would hide the page
    from the only place it is advertised.
    """
    target = out_dir / "fleet" / "index.html"
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render(
            (TEMPLATES / "404.html").read_text(encoding="utf-8"),
            {
                "lang": book.language,
                "title": esc(f"Fleet report — {book.title}"),
                "heading": "No report yet",
                "message": (
                    "The fleet report is written on Mondays and reaches the "
                    "site on the next publish."
                ),
                "home": esc(book.base_path),
            },
        ),
        encoding="utf-8",
    )


def prune_stale_pages(book: Book, out_dir: Path) -> list[str]:
    """Delete chapter directories for chapters that no longer exist.

    Nothing removed a page when its chapter was renamed or dropped, so a local
    `dist/` accumulated them -- `the-pipeline/` outlived the scaffolding it
    came from by every chapter the book has had since. CI never noticed,
    because it builds into an empty checkout, and that is exactly the shape of
    fault worth removing: a gate that passes locally and means something
    different there.

    Conservative on purpose. A directory goes only if it holds nothing but an
    `index.html`, sits directly under the output, and is neither a current
    chapter nor somewhere another part of the pipeline writes.
    """
    # Derived, not listed. A hardcoded set drifts the moment somebody adds a
    # standalone page: `dist/skill/` holds one index.html and is not a
    # chapter, which is exactly the shape this deletes.
    standalone = {
        entry.name
        for entry in SITE_DIR.iterdir()
        if entry.is_dir() and entry.name not in {"assets", "templates"}
    }
    keep = (
        {chapter.slug for chapter in book.chapters}
        | {"assets", "badges", "fleet"}
        | standalone
    )
    removed = []
    for entry in sorted(out_dir.iterdir()):
        if not entry.is_dir() or entry.name in keep:
            continue
        if {child.name for child in entry.iterdir()} != {"index.html"}:
            continue
        (entry / "index.html").unlink()
        entry.rmdir()
        removed.append(entry.name)
    return removed


def write_badges(book: Book, out_dir: Path) -> None:
    """Shields endpoints for the README, generated rather than typed.

    A badge whose text is written into the README is wrong the first time
    anyone changes the thing it describes, and nobody notices, because a
    badge is the part of a README that is looked at and not read. These are
    JSON documents on the published site, read by shields.io's endpoint
    badge, so what the README claims is whatever the last deployment
    measured.

    <https://shields.io/badges/endpoint-badge> defines the schema. The
    `cacheSeconds` floor is shields' own; asking for less does not get less.
    """
    badges_dir = out_dir / "badges"
    badges_dir.mkdir(parents=True, exist_ok=True)

    words = sum(chapter.words for chapter in book.chapters)
    endpoints = {
        "progress.json": {
            "label": "book",
            "message": f"{len(book.chapters)} chapters · {words:,} words",
            "color": "blue",
        },
        "typst.json": {
            "label": "typst",
            "message": typst_pin(),
            "color": "239dad",  # Typst's own.
        },
    }
    for name, badge in endpoints.items():
        (badges_dir / name).write_text(
            json.dumps({"schemaVersion": 1, "cacheSeconds": 3600, **badge}, indent=2)
            + "\n",
            encoding="utf-8",
        )


def copy_assets(out_dir: Path) -> None:
    assets = out_dir / "assets"
    if assets.exists():
        shutil.rmtree(assets)
    shutil.copytree(SITE_DIR / "assets", assets)

    # Standalone pages: reachable on the site, and deliberately not part of
    # the book. No navigation, no sitemap entry, no search index, `noindex` in
    # their own head. `site/skill/` is the generator that builds the
    # note-taker's skill; `/fleet/` arrives by another route because it is
    # generated weekly rather than checked in.
    for page in sorted((SITE_DIR).iterdir()):
        if not page.is_dir() or page.name in {"assets", "templates"}:
            continue
        destination = out_dir / page.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(page, destination)


def build_social_card(binary: str, out_dir: Path) -> list[str]:
    """The repository's social preview image.

    1280x640 is what GitHub asks for, and at 72 PPI one Typst point is one
    pixel, so `site/social-card.typ`'s page size is literally the output. It
    is built here rather than drawn by hand so that it cannot go stale: the
    words on it come from `book.toml`, so a title the fleet changes changes
    the card too.
    """
    return run_typst(
        binary,
        [
            "compile",
            "--root",
            ".",
            "--features",
            "html",
            "--ignore-system-fonts",
            "--font-path",
            "book/fonts",
            "--ppi",
            "72",
            "site/social-card.typ",
            str((out_dir / "social-card.png").relative_to(ROOT)),
        ],
    )


def build_pdf(binary: str, out_dir: Path) -> list[str]:
    return run_typst(
        binary,
        [
            "compile",
            "--root",
            ".",
            "--features",
            "html",
            "--ignore-system-fonts",
            "--font-path",
            "book/fonts",
            "book/book.typ",
            str((out_dir / "book.pdf").relative_to(ROOT)),
        ],
    )


def build(args: argparse.Namespace, binary: str) -> Book:
    out_dir = (ROOT / args.out).resolve()
    build_dir = ROOT / "build"
    out_dir.mkdir(parents=True, exist_ok=True)

    book = load_book()
    if args.base_url is not None:
        book.meta["base-url"] = args.base_url

    started = time.perf_counter()
    if args.pdf_only:
        warnings = build_pdf(binary, out_dir)
        for warning in sorted(set(unexpected(warnings))):
            print(f"typst warning: {warning}", file=sys.stderr)
        print(
            f"built {out_dir.relative_to(ROOT)}/book.pdf "
            f"in {time.perf_counter() - started:.1f}s"
        )
        if unexpected(warnings) and args.strict:
            sys.exit("strict mode: unexpected typst warning(s)")
        return book

    warnings = compile_chapters(book, binary, build_dir)
    warnings += build_social_card(binary, out_dir)
    if not args.no_pdf:
        warnings += build_pdf(binary, out_dir)

    write_pages(book, out_dir, dev=args.dev)
    single = build_single_page(book, out_dir)
    write_search_index(book, out_dir)
    copy_assets(out_dir)
    write_fleet_placeholder(book, out_dir)

    for stale in prune_stale_pages(book, out_dir):
        print(f"  removed stale page: {stale}/")
    epub = build_epub(book, out_dir, cover=out_dir / "social-card.png")
    write_badges(book, out_dir)
    write_site_files(book, out_dir, pdf=not args.no_pdf)
    elapsed = time.perf_counter() - started

    surprises = unexpected(warnings)
    for warning in sorted(set(surprises)):
        print(f"typst warning: {warning}", file=sys.stderr)

    words = sum(chapter.words for chapter in book.chapters)
    print(
        f"  single file: {single.relative_to(ROOT)} "
        f"({single.stat().st_size / 1024:.0f} KB)"
    )
    print(
        f"  epub:        {epub.relative_to(ROOT)} ({epub.stat().st_size / 1024:.0f} KB)"
    )
    print(
        f"built {len(book.chapters)} chapters, {words:,} words "
        f"-> {out_dir.relative_to(ROOT)} in {elapsed:.1f}s"
        + ("" if args.no_pdf else " (with PDF)")
    )
    if surprises and args.strict:
        sys.exit(f"strict mode: {len(surprises)} unexpected typst warning(s)")
    return book


# --------------------------------------------------------------------------- #
# Watch and serve
# --------------------------------------------------------------------------- #

WATCHED = ("book", "site", "code")


def snapshot() -> dict[Path, float]:
    seen: dict[Path, float] = {}
    for directory in WATCHED:
        for path in (ROOT / directory).rglob("*"):
            if path.is_file():
                seen[path] = path.stat().st_mtime
    return seen


def serve_forever(out_dir: Path, port: int, counter: list[int]) -> None:
    # Only `--serve` needs an HTTP server; every other run would pay for
    # the import.
    from http.server import (  # noqa: PLC0415
        SimpleHTTPRequestHandler,
        ThreadingHTTPServer,
    )

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(out_dir), **kwargs)

        def do_GET(self):
            if self.path.startswith("/__build"):
                body = str(counter[0]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def watch(args: argparse.Namespace, binary: str) -> None:
    import threading  # noqa: PLC0415 - only `--watch` needs it

    out_dir = (ROOT / args.out).resolve()
    counter = [0]

    if args.serve:
        threading.Thread(
            target=serve_forever, args=(out_dir, args.port, counter), daemon=True
        ).start()
        print(f"serving http://127.0.0.1:{args.port} -- ctrl-c to stop")

    known = snapshot()
    while True:
        time.sleep(0.4)
        current = snapshot()
        if current == known:
            continue
        known = current
        try:
            build(args, binary)
            counter[0] += 1
        except (TypstError, SystemExit) as error:
            print(f"build failed: {error}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", default="dist", help="output directory (default: dist)"
    )
    parser.add_argument("--no-pdf", action="store_true", help="skip the PDF build")
    parser.add_argument(
        "--pdf-only", action="store_true", help="build only the PDF, not the site"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on any Typst warning that is not known-benign",
    )
    parser.add_argument(
        "--base-url", help="override book.toml's base-url (for staged deployments)"
    )
    parser.add_argument(
        "--watch", action="store_true", help="rebuild when files change"
    )
    parser.add_argument(
        "--serve", action="store_true", help="serve the output and rebuild on change"
    )
    parser.add_argument("--port", type=int, default=8000, help="port for --serve")
    parser.add_argument(
        "--dev",
        action="store_true",
        help="inject the live-reload script (implied by --serve)",
    )
    args = parser.parse_args()

    if args.serve:
        args.watch = True
        args.dev = True
    if args.pdf_only and args.no_pdf:
        sys.exit("--pdf-only and --no-pdf contradict each other")

    binary = typst_binary()
    try:
        build(args, binary)
    except TypstError as error:
        sys.exit(f"typst: {error}")

    if args.watch:
        try:
            watch(args, binary)
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
