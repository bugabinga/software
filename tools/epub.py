#!/usr/bin/env python3
"""Build the book as an EPUB, from the same chapters as everything else.

Typst has no EPUB export, and the obvious answer -- run pandoc over the HTML
-- would put a package manager into a tree that has deliberately avoided one.
It is also the worse answer: EPUB 3 is a zip of XHTML with two manifests, the
chapters are already exported as clean HTML, and converting them means
guessing at what a converter would have done rather than deciding it.

So this writes the container directly. About two hundred lines, no
dependencies, and the parts that matter are ours:

- **Maths survives.** Typst exports MathML and EPUB 3 renders MathML, so
  equations arrive as equations rather than as pictures of equations. The
  manifest has to declare `properties="mathml"` per document or readers are
  entitled to ignore it, which is the detail a converter gets wrong.
- **One file per chapter**, matching the website and the PDF, so a footnote
  stays with the chapter it belongs to.
- **Cross-chapter links keep working**, rewritten from the site's `../slug/`
  shape to `ch-slug.xhtml`.

XHTML, not HTML: an EPUB reader is entitled to parse with an XML parser and
reject the file outright, so void elements are self-closed and the content is
checked with the standard library's XML parser before it is written. A book
that opens in one reader and not another is worse than one that fails here.
"""

from __future__ import annotations

import html
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

# Void elements, which XHTML requires be self-closed. Typst's own export is
# already close to XHTML; these come from helpers that emit raw HTML.
VOID = (
    "area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr"
)
VOID_RE = re.compile(rf"<({VOID})\b([^>]*?)\s*/?>", re.I)
# An ampersand that is not already a character reference.
BARE_AMP_RE = re.compile(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#[xX][0-9a-fA-F]+);)")

STYLESHEET = """\
/* Deliberately small. A reading system's own typography is usually better
   than a book's, and the settings a reader has chosen are certainly better
   than ours, so this styles what would otherwise be unreadable and stops. */
body { line-height: 1.6; margin: 0 5%; }
h1, h2, h3 { line-height: 1.25; }
h1 { margin: 2em 0 1em; }
p { margin: 0 0 1em; text-align: justify; }
a { color: inherit; }
code, pre, kbd { font-family: monospace; }
pre { padding: .8em; overflow-x: auto; background: rgba(127,127,127,.12);
      border-radius: .25em; white-space: pre-wrap; word-wrap: break-word; }
code { font-size: .92em; }
blockquote { margin: 1em 0 1em 1em; padding-left: 1em;
             border-left: 3px solid rgba(127,127,127,.4); }
figure { margin: 1.5em 0; text-align: center; }
figcaption { font-size: .9em; opacity: .8; }
img { max-width: 100%; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { text-align: left; padding: .3em .7em .3em 0;
         border-bottom: 1px solid rgba(127,127,127,.3); }
dfn { font-style: italic; font-weight: bold; }
.callout { margin: 1.4em 0; padding: .8em 1em; border-radius: .25em;
           border-left: 4px solid rgba(127,127,127,.5);
           background: rgba(127,127,127,.08); }
.callout-title { font-weight: bold; display: block; margin-bottom: .3em; }
.callout-warning, .callout-caution { border-left-color: #b3541e; }
.callout-tip { border-left-color: #2c7a4b; }
.eyebrow { font-size: .85em; letter-spacing: .08em; text-transform: uppercase;
           opacity: .65; margin-bottom: .2em; }
.title-page { text-align: center; margin-top: 25%; }
.title-page h1 { font-size: 2em; margin: 0 0 .3em; }
.title-page .subtitle { font-style: italic; opacity: .8; }
.title-page .authors { margin-top: 2em; }
"""


def xhtmlify(fragment: str) -> str:
    """Make an HTML fragment parse as XML without changing what it says."""
    fragment = BARE_AMP_RE.sub("&amp;", fragment)
    return VOID_RE.sub(lambda m: f"<{m.group(1)}{m.group(2)}/>", fragment)


def relink(fragment: str, slugs: set[str]) -> str:
    """Point the site's cross-chapter links at this container's files."""
    for slug in slugs:
        fragment = fragment.replace(f'href="../{slug}/#', f'href="ch-{slug}.xhtml#')
        fragment = fragment.replace(f'href="../{slug}/"', f'href="ch-{slug}.xhtml"')
    return fragment


def document(title: str, body: str, language: str, extra_head: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        f'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{language}" '
        f'lang="{language}">\n'
        f"<head><title>{html.escape(title)}</title>"
        '<meta charset="utf-8"/>'
        '<link rel="stylesheet" type="text/css" href="style.css"/>'
        f"{extra_head}</head>\n"
        f"<body>{body}</body>\n</html>\n"
    )


def stable_identifier(book) -> str:
    """The same book at the same edition gets the same id every build.

    A reading system uses this to decide whether a file is a new book or a new
    copy of one it already has, so it must not be a fresh uuid4 per build.
    """
    seed = f"{book.base_url or 'urn:book:'}|{book.meta.get('edition', '')}"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"


def build_epub(book, out_dir: Path, cover: Path | None = None) -> Path:
    language = book.language
    slugs = {chapter.slug for chapter in book.chapters}
    authors = book.meta.get("authors", []) or ["Unknown"]

    documents: list[tuple[str, str, bool]] = []  # (filename, xhtml, has_mathml)

    subtitle = book.meta.get("subtitle", "")
    edition = book.meta.get("edition", "")
    title_body = (
        '<section class="title-page" epub:type="titlepage">'
        f"<h1>{html.escape(book.title)}</h1>"
        + (f'<p class="subtitle">{html.escape(subtitle)}</p>' if subtitle else "")
        + f'<p class="authors">{html.escape(", ".join(authors))}</p>'
        + (f'<p class="edition">{html.escape(edition)}</p>' if edition else "")
        + "</section>"
    )
    documents.append(("title.xhtml", document(book.title, title_body, language), False))

    for chapter in book.chapters:
        body = xhtmlify(relink(chapter.content, slugs))
        eyebrow = (
            f"Chapter {chapter.number}" if chapter.number is not None else chapter.part
        )
        section = (
            f'<section class="chapter" id="{chapter.slug}" epub:type="chapter">'
            + (f'<p class="eyebrow">{html.escape(eyebrow)}</p>' if eyebrow else "")
            + f"<h1>{xhtmlify(chapter.title_html)}</h1>{body}</section>"
        )
        documents.append(
            (
                f"ch-{chapter.slug}.xhtml",
                document(chapter.title_text, section, language),
                "<math" in body,
            )
        )

    # The navigation document is both the machine-readable spine order and the
    # table of contents a reader shows, so it is not optional and not a
    # courtesy copy of the one in the text.
    items = []
    part = None
    for chapter in book.chapters:
        if chapter.part != part:
            part = chapter.part
        items.append(
            f'<li><a href="ch-{chapter.slug}.xhtml">'
            f"{html.escape(chapter.title_text)}</a></li>"
        )
    nav_body = (
        '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>'
        + "".join(items)
        + "</ol></nav>"
        '<nav epub:type="landmarks" hidden="hidden"><ol>'
        '<li><a epub:type="titlepage" href="title.xhtml">Title page</a></li>'
        + (
            f'<li><a epub:type="bodymatter" href="ch-{book.chapters[0].slug}.xhtml">'
            "Start of content</a></li>"
            if book.chapters
            else ""
        )
        + "</ol></nav>"
    )
    documents.append(("nav.xhtml", document("Contents", nav_body, language), False))

    for name, text, _ in documents:
        try:
            ElementTree.fromstring(text)
        except ElementTree.ParseError as error:
            raise SystemExit(f"epub: {name} is not well-formed XML: {error}")

    identifier = stable_identifier(book)
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cover_item = cover_meta = cover_spine = ""
    if cover and cover.is_file():
        cover_item = (
            '<item id="cover-image" href="cover.png" media-type="image/png" '
            'properties="cover-image"/>\n    '
            '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>'
        )
        cover_meta = '<meta name="cover" content="cover-image"/>'
        cover_spine = '<itemref idref="cover"/>'

    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>',
        '<item id="style" href="style.css" media-type="text/css"/>',
        '<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>',
    ]
    spine = ['<itemref idref="title"/>']
    for index, chapter in enumerate(book.chapters):
        has_math = documents[index + 1][2]
        properties = ' properties="mathml"' if has_math else ""
        manifest.append(
            f'<item id="ch{index}" href="ch-{chapter.slug}.xhtml" '
            f'media-type="application/xhtml+xml"{properties}/>'
        )
        spine.append(f'<itemref idref="ch{index}"/>')

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="book-id" xml:lang="{language}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">{identifier}</dc:identifier>
    <dc:title>{html.escape(book.title)}</dc:title>
    <dc:language>{language}</dc:language>
    {"".join(f"<dc:creator>{html.escape(name)}</dc:creator>" for name in authors)}
    <dc:description>{html.escape(book.meta.get("description", ""))}</dc:description>
    <meta property="dcterms:modified">{modified}</meta>
    {cover_meta}
  </metadata>
  <manifest>
    {chr(10).join("    " + line for line in manifest).strip()}
    {cover_item}
  </manifest>
  <spine>
    {cover_spine}
    {chr(10).join("    " + line for line in spine).strip()}
  </spine>
</package>
"""
    try:
        ElementTree.fromstring(opf)
    except ElementTree.ParseError as error:
        raise SystemExit(f"epub: content.opf is not well-formed XML: {error}")

    destination = out_dir / "book.epub"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        # The mimetype must be the first entry and must be stored uncompressed:
        # it is how a reader identifies the file without unzipping it.
        archive.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
            '  <rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles>\n'
            "</container>\n",
        )
        archive.writestr("OEBPS/content.opf", opf)
        archive.writestr("OEBPS/style.css", STYLESHEET)
        for name, text, _ in documents:
            archive.writestr(f"OEBPS/{name}", text)
        if cover and cover.is_file():
            archive.writestr("OEBPS/cover.png", cover.read_bytes())
            archive.writestr(
                "OEBPS/cover.xhtml",
                document(
                    "Cover",
                    '<section epub:type="cover"><img src="cover.png" '
                    f'alt="{html.escape(book.title)}"/></section>',
                    language,
                ),
            )

    return destination
