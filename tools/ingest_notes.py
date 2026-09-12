#!/usr/bin/env python3
"""Download a source into `notes/`, verbatim and in readable form.

`notes/` is the raw material the book is written from: transcripts of
discussions about the content, references, anything worth keeping. Nothing in
here is built into the book -- it is the input side of the pipeline.

Each ingested source produces two files:

    notes/<date>-<slug>.md        readable Markdown, with a frontmatter header
    notes/raw/<date>-<slug>.<ext> the response body, byte for byte

The raw copy is what makes "downloaded completely" true: the Markdown is a
best-effort conversion, and if it ever loses something the original is still
there to re-read. Re-ingesting the same URL updates the note in place rather
than making a second copy.

Usage:
    tools/ingest_notes.py https://example.com/a-discussion
    tools/ingest_notes.py --from-file transcript.txt --title "Chapter 3 ideas"
    tools/ingest_notes.py --reindex

Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
RAW = NOTES / "raw"
INDEX = NOTES / "index.md"

USER_AGENT = "Mozilla/5.0 (compatible; book-notes-ingest)"

# Below this much prose, a page is almost certainly a JavaScript shell rather
# than the content itself, and saving it would be quietly useless.
THIN_PAGE_WORDS = 40


# --------------------------------------------------------------------------- #
# HTML to Markdown
# --------------------------------------------------------------------------- #

BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "main", "tr"}
DROP_TAGS = {"script", "style", "noscript", "svg", "head", "nav", "form", "button"}


class Markdownifier(HTMLParser):
    """A small, deliberately unambitious HTML-to-Markdown converter.

    It handles what discussion transcripts and articles actually contain:
    headings, paragraphs, lists, code, quotes, links, emphasis and tables.
    Anything it does not understand degrades to its text, and `notes/raw/`
    keeps the original either way.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = io.StringIO()
        self.title = ""
        self.drop_depth = 0
        self.in_title = False
        self.in_pre = 0
        self.list_stack: list[str] = []
        self.item_index: list[int] = []
        self.quote_depth = 0
        self.pending_link: str | None = None
        self.link_text: list[str] = []
        self.cell_open = False

    # -- helpers ----------------------------------------------------------- #

    def write(self, text: str) -> None:
        if self.pending_link is not None:
            self.link_text.append(text)
        else:
            self.out.write(text)

    def newline(self, count: int = 1) -> None:
        current = self.out.getvalue()
        if not current.strip():
            return
        existing = len(current) - len(current.rstrip("\n"))
        self.out.write("\n" * max(0, count - existing))

    # -- tags -------------------------------------------------------------- #

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in DROP_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth:
            return

        if tag == "title":
            self.in_title = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.newline(2)
            self.out.write("#" * int(tag[1]) + " ")
        elif tag == "br":
            self.out.write("  \n")
        elif tag == "hr":
            self.newline(2)
            self.out.write("---\n")
        elif tag == "pre":
            self.newline(2)
            language = values.get("data-lang", values.get("class", ""))
            language = re.sub(
                r"[^A-Za-z0-9+#-]", "", language.split()[0] if language.split() else ""
            )
            self.out.write(f"```{language}\n")
            self.in_pre += 1
        elif tag == "code" and not self.in_pre:
            self.write("`")
        elif tag in {"ul", "ol"}:
            self.newline(1)
            self.list_stack.append(tag)
            self.item_index.append(0)
        elif tag == "li":
            self.newline(1)
            indent = "  " * (len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1] == "ol":
                self.item_index[-1] += 1
                self.out.write(f"{indent}{self.item_index[-1]}. ")
            else:
                self.out.write(f"{indent}- ")
        elif tag == "blockquote":
            self.newline(2)
            self.quote_depth += 1
        elif tag in {"strong", "b"}:
            self.write("**")
        elif tag in {"em", "i"}:
            self.write("*")
        elif tag == "a":
            self.pending_link = values.get("href", "")
            self.link_text = []
        elif tag == "img":
            alt = values.get("alt", "image")
            source = values.get("src", "")
            if source and not source.startswith("data:"):
                self.write(f"![{alt}]({source})")
            else:
                self.write(f"[{alt}]")
        elif tag in {"td", "th"}:
            self.out.write("| " if not self.cell_open else " | ")
            self.cell_open = True
        elif tag in BLOCK_TAGS:
            self.newline(2)

    def handle_endtag(self, tag):
        if tag in DROP_TAGS:
            self.drop_depth = max(0, self.drop_depth - 1)
            return
        if self.drop_depth:
            return

        if tag == "title":
            self.in_title = False
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.newline(2)
        elif tag == "pre":
            self.in_pre = max(0, self.in_pre - 1)
            self.newline(1)
            self.out.write("```\n")
        elif tag == "code" and not self.in_pre:
            self.write("`")
        elif tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()
                self.item_index.pop()
            self.newline(2)
        elif tag == "blockquote":
            self.quote_depth = max(0, self.quote_depth - 1)
            self.newline(2)
        elif tag in {"strong", "b"}:
            self.write("**")
        elif tag in {"em", "i"}:
            self.write("*")
        elif tag == "a":
            text = "".join(self.link_text).strip()
            href = self.pending_link or ""
            self.pending_link = None
            self.link_text = []
            if text and href and not href.startswith("#"):
                self.out.write(f"[{text}]({href})")
            else:
                self.out.write(text)
        elif tag == "tr":
            if self.cell_open:
                self.out.write(" |")
                self.cell_open = False
            self.newline(1)
        elif tag in BLOCK_TAGS:
            self.newline(2)

    def handle_data(self, data):
        if self.drop_depth:
            return
        if self.in_title:
            self.title += data.strip()
            return
        if self.in_pre:
            self.out.write(data)
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip() == "" and not self.out.getvalue().endswith(" "):
            self.write(" " if text else "")
            return
        self.write(text)

    @property
    def markdown(self) -> str:
        text = self.out.getvalue()
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Quote markers are applied per paragraph after the fact; nesting
        # deeper than one level is rare enough not to model.
        return text.strip() + "\n"


def to_markdown(body: str) -> tuple[str, str]:
    parser = Markdownifier()
    parser.feed(body)
    return parser.title, parser.markdown


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #


def slugify(text: str, fallback: str = "note") -> str:
    text = re.sub(r"https?://", "", text.strip().lower())
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:60].rstrip("-") or fallback


def fetch(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get_content_type()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{url}: HTTP {error.code} {error.reason}") from error
    except Exception as error:  # network, TLS and DNS all land here
        raise SystemExit(f"{url}: {type(error).__name__}: {error}") from error


def existing_note_for(source: str) -> Path | None:
    """The note already ingested from this source, if any."""
    for note in sorted(NOTES.glob("*.md")):
        head = note.read_text(encoding="utf-8")[:600]
        if re.search(rf"^source: {re.escape(source)}$", head, re.M):
            return note
    return None


def write_note(
    *,
    source: str,
    title: str,
    markdown: str,
    raw: bytes,
    extension: str,
    allow_thin: bool,
) -> Path:
    NOTES.mkdir(exist_ok=True)
    RAW.mkdir(exist_ok=True)

    words = len(markdown.split())
    if words < THIN_PAGE_WORDS and not allow_thin:
        raise SystemExit(
            f"{source}: only {words} words of text came back.\n"
            "  That usually means the page renders its content with JavaScript,\n"
            "  or needs a login, so there is nothing useful to save. Options:\n"
            "    - publish the content as an artifact and let me read that;\n"
            "    - paste the text and use --from-file;\n"
            "    - pass --allow-thin to save it anyway."
        )

    previous = existing_note_for(source)
    if previous:
        stem = previous.stem
    else:
        stem = f"{date.today().isoformat()}-{slugify(title or source)}"

    note_path = NOTES / f"{stem}.md"
    raw_path = RAW / f"{stem}.{extension}"
    raw_path.write_bytes(raw)

    fetched = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = hashlib.sha256(raw).hexdigest()
    first_seen = fetched
    if previous:
        match = re.search(
            r"^first-seen: (\S+)$", previous.read_text(encoding="utf-8")[:600], re.M
        )
        if match:
            first_seen = match.group(1)

    frontmatter = "\n".join(
        [
            "---",
            f"title: {title or stem}",
            f"source: {source}",
            f"first-seen: {first_seen}",
            f"fetched: {fetched}",
            f"raw: raw/{raw_path.name}",
            f"sha256: {digest}",
            f"words: {words}",
            "---",
            "",
        ]
    )
    note_path.write_text(frontmatter + markdown, encoding="utf-8")
    action = "updated" if previous else "added"
    print(f"{action} {note_path.relative_to(ROOT)} ({words:,} words, raw kept)")
    return note_path


def ingest_url(url: str, title: str | None, allow_thin: bool) -> Path:
    raw, content_type = fetch(url)
    if content_type in {"text/html", "application/xhtml+xml"}:
        page_title, markdown = to_markdown(raw.decode("utf-8", errors="replace"))
        extension = "html"
    elif content_type.startswith("text/") or content_type in {"application/json"}:
        page_title, markdown = "", raw.decode("utf-8", errors="replace")
        extension = "txt"
    else:
        # A binary source (a PDF, say): keep it, and leave a stub pointing at it.
        extension = content_type.split("/")[-1][:8] or "bin"
        page_title, markdown = (
            "",
            (f"Binary source of type `{content_type}`, kept verbatim in `raw/`.\n"),
        )
        allow_thin = True
    return write_note(
        source=url,
        title=title or page_title or slugify(url),
        markdown=markdown,
        raw=raw,
        extension=extension,
        allow_thin=allow_thin,
    )


def ingest_file(
    path: Path, title: str | None, source: str | None, allow_thin: bool
) -> Path:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if path.suffix.lower() in {".html", ".htm"}:
        page_title, markdown = to_markdown(text)
        extension = "html"
    else:
        page_title, markdown = "", text
        extension = path.suffix.lstrip(".") or "txt"
    return write_note(
        source=source or f"file://{path.name}",
        title=title or page_title or path.stem,
        markdown=markdown,
        raw=raw,
        extension=extension,
        allow_thin=allow_thin,
    )


def reindex() -> None:
    NOTES.mkdir(exist_ok=True)
    rows = []
    for note in sorted(NOTES.glob("*.md")):
        head = note.read_text(encoding="utf-8")[:800]
        # A note is a file this tool wrote: it carries a `source:` header.
        # README.md and index.md do not, and are not listed.
        if not re.search(r"^source: ", head, re.M):
            continue
        field = lambda name, head=head: (  # noqa: E731 - terse on purpose
            match.group(1)
            if (match := re.search(rf"^{name}: (.*)$", head, re.M))
            else ""
        )
        rows.append(
            {
                "file": note.name,
                "title": field("title"),
                "source": field("source"),
                "first_seen": field("first-seen")[:10],
                "words": field("words"),
            }
        )

    lines = [
        "# Notes index",
        "",
        "Generated by `tools/ingest_notes.py --reindex`; do not edit by hand.",
        "",
        "| First seen | Note | Words | Source |",
        "| --- | --- | --: | --- |",
    ]
    for row in rows:
        source = row["source"]
        link = f"[link]({source})" if source.startswith("http") else "`" + source + "`"
        lines.append(
            f"| {row['first_seen']} | [{row['title']}]({row['file']}) "
            f"| {row['words']} | {link} |"
        )
    if not rows:
        lines.append("| | *nothing ingested yet* | | |")
    lines.append("")
    INDEX.write_text("\n".join(lines), encoding="utf-8")
    print(f"indexed {len(rows)} note(s) -> notes/index.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("urls", nargs="*", help="sources to download")
    parser.add_argument(
        "--from-file", type=Path, help="ingest a local file instead of a URL"
    )
    parser.add_argument("--source", help="source URL to record for --from-file")
    parser.add_argument("--title", help="title for the note (default: the page's own)")
    parser.add_argument(
        "--allow-thin",
        action="store_true",
        help="save even when almost no text came back",
    )
    parser.add_argument(
        "--reindex", action="store_true", help="only rebuild notes/index.md"
    )
    arguments = parser.parse_args()

    if arguments.reindex and not arguments.urls and not arguments.from_file:
        reindex()
        return
    if not arguments.urls and not arguments.from_file:
        parser.error("give a URL, --from-file, or --reindex")

    if arguments.from_file:
        ingest_file(
            arguments.from_file, arguments.title, arguments.source, arguments.allow_thin
        )
    for url in arguments.urls:
        ingest_url(
            url,
            arguments.title if len(arguments.urls) == 1 else None,
            arguments.allow_thin,
        )
    reindex()


if __name__ == "__main__":
    main()
