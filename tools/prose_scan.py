#!/usr/bin/env python3
"""Find the faults in the book that a program can find, and say where.

There are two kinds of thing wrong with a chapter. One is judgement — a
citation that does not support its claim, an agent outside its brief,
invention — and that is `pr-reviewer`'s, delivered as review threads on the
lines it is about. The other is mechanical: a cross-reference to a chapter
that no longer exists, a note cited at a line the note does not have. Those
need no judgement at all, and until now they were also delivered as an agent's
prose, which is a waste of a model and a worse artefact.

This is the mechanical half. It emits SARIF, which is not a security format:
it is findings with a file, a line, a rule and a severity, and GitHub accepts
it from any tool. What that buys is inline annotations on the diff, a rule id,
a dismissal flow with a reason, history in the Security tab, and a merge gate
that can be set to block on `error` alone.

**Every rule here must be decidable.** If a rule needs to know what a sentence
means, it belongs to the reviewer instead. The test for a rule is whether two
people would agree on every result without discussing it.

Usage:
    tools/prose_scan.py                     # human-readable, exits 1 on error
    tools/prose_scan.py --sarif out.sarif   # for github/codeql-action
    tools/prose_scan.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "book" / "chapters"
MANIFEST = ROOT / "book" / "book.toml"
TERMS = ROOT / "book" / "terms.toml"

# `Source:` or `Sources:`, and the paths may follow on later comment lines --
# `90-open-questions.typ` does exactly that, and requiring them on the same
# line made this rule fire on four chapters that cite their notes perfectly
# well. The paths themselves are checked wherever they appear.
SOURCE_RE = re.compile(r"//\s*Sources?:")
# A chapter may declare that it is not derived from notes, with a reason.
# `99-prelude-reference.typ` is living documentation of the prelude, not part
# of the outline the notes fixed. The exemption sits next to the thing it
# exempts and shows up in the diff, which a list inside this program would
# not.
EXEMPT_RE = re.compile(r"//\s*Not from notes:\s*(?P<reason>\S.*)$")
NOTE_RE = re.compile(r"(?P<path>notes/[^\s,]+\.md)")
LINES_RE = re.compile(r"lines?\s+(?P<start>\d+)(?:\s*[-–]\s*(?P<end>\d+))?")
XREF_RE = re.compile(r'#xref\(\s*"(?P<slug>[^"]+)"')
SNIPPET_RE = re.compile(r'#snippet\(\s*"(?P<path>[^"]+)"')
TODO_RE = re.compile(r"\b(TODO|FIXME|XXX)\b")

# Every rule, with the severity it reports at and what it is for. `error`
# blocks a merge where the ruleset is set to; `warning` and `note` annotate.
RULES = {
    "dead-note": (
        "error",
        "A cited note does not exist",
        "The chapter cites a file under `notes/` that is not in the tree. "
        "Either the note was renamed, or the citation was written from memory.",
    ),
    "note-line-out-of-range": (
        "error",
        "A cited note line does not exist",
        "The chapter cites a line range the note is not long enough to have. "
        "The most likely cause is a citation carried over after the note grew "
        "or shrank.",
    ),
    "dead-xref": (
        "error",
        "A cross-reference points at no chapter",
        "`#xref` names a slug that `book/book.toml` does not list. Chapters "
        "are compiled separately, so nothing else catches this until the link "
        "check runs over a built site.",
    ),
    "dead-snippet": (
        "error",
        "An included snippet does not exist",
        "`#snippet` reads a file at build time; a missing one fails the build "
        "with a Typst error that does not say which chapter asked for it.",
    ),
    "uncited-chapter": (
        "warning",
        "A chapter cites no note",
        "Every chapter in this book is derived from the author's notes and "
        "says so in a `// Source:` comment. A chapter without one cannot be "
        "traced, which is the first thing the reviewer checks.",
    ),
    "todo-left": (
        "warning",
        "A marker was left in the prose",
        "TODO, FIXME or XXX in a chapter. Fine while drafting, not fine in "
        "something being merged.",
    ),
    "term-drift": (
        "warning",
        "Two names for one thing",
        "`book/terms.toml` names a preferred term and the spellings to avoid. "
        "A reader holding two names for one referent is spending attention "
        "the argument needed.",
    ),
}


@dataclass
class Finding:
    rule: str
    path: str
    line: int
    message: str
    column: int = 1
    end_column: int | None = None

    @property
    def level(self) -> str:
        return RULES[self.rule][0]


@dataclass
class Book:
    slugs: set[str] = field(default_factory=set)
    chapters: list[Path] = field(default_factory=list)


# One implementation, not a third. `CLAUDE.md` records that the slug rule
# lives in exactly two places -- `slug-of` in the prelude and `slug_of` in
# `tools/build.py` -- and that the two must match.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import slug_of  # noqa: E402 - after the path is set up


def load_book() -> Book:
    if not MANIFEST.is_file():
        sys.exit(f"missing manifest: {MANIFEST}")
    with MANIFEST.open("rb") as handle:
        manifest = tomllib.load(handle)
    book = Book()
    for part in manifest.get("part", []):
        for relative in part.get("chapters", []):
            book.slugs.add(slug_of(relative))
            book.chapters.append(ROOT / "book" / relative)
    return book


def load_terms() -> list[tuple[str, list[str]]]:
    """The preferred spellings, if anyone has written any down.

    Absent by design until the book has vocabulary worth policing. A rule that
    invents its own terminology would be enforcing this program's opinion, and
    the terms belong to the author.
    """
    if not TERMS.is_file():
        return []
    with TERMS.open("rb") as handle:
        data = tomllib.load(handle)
    return [
        (entry["name"], list(entry.get("avoid", [])))
        for entry in data.get("term", [])
        if entry.get("name")
    ]


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def scan_chapter(path: Path, book: Book, terms, root: Path) -> list[Finding]:
    relative = str(path.relative_to(root))
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    findings: list[Finding] = []
    cited = False

    for number, line in enumerate(lines, start=1):
        if SOURCE_RE.search(line) or EXEMPT_RE.search(line):
            cited = True

        # Notes are cited in a `// Source:` header and in follow-on comments,
        # so every mention of a notes path is checked wherever it appears.
        notes_here = list(NOTE_RE.finditer(line))
        for index, match in enumerate(notes_here):
            note = root / match.group("path")
            column = match.start() + 1
            if not note.is_file():
                findings.append(
                    Finding(
                        "dead-note",
                        relative,
                        number,
                        f"`{match.group('path')}` is cited here "
                        "and is not in the tree.",
                        column,
                        match.end() + 1,
                    )
                )
                continue
            total = line_count(note)
            # A range belongs to the path it follows. Searching the whole
            # line makes `notes/a.md lines 1-3, notes/b.md lines 900-950`
            # report `a.md` as too short for a range never about it.
            stop = (
                notes_here[index + 1].start()
                if index + 1 < len(notes_here)
                else len(line)
            )
            for span in LINES_RE.finditer(line, match.end(), stop):
                start = int(span.group("start"))
                end = int(span.group("end") or start)
                if max(start, end) > total:
                    findings.append(
                        Finding(
                            "note-line-out-of-range",
                            relative,
                            number,
                            f"`{match.group('path')}` has {total} lines; this cites "
                            f"{start}–{end}.",
                            span.start() + 1,
                            span.end() + 1,
                        )
                    )

        for match in XREF_RE.finditer(line):
            slug = match.group("slug")
            if slug not in book.slugs:
                findings.append(
                    Finding(
                        "dead-xref",
                        relative,
                        number,
                        f"`{slug}` is not a chapter in book.toml.",
                        match.start() + 1,
                        match.end() + 1,
                    )
                )

        for match in SNIPPET_RE.finditer(line):
            target = match.group("path")
            resolved = root / target.lstrip("/")
            if not resolved.is_file():
                findings.append(
                    Finding(
                        "dead-snippet",
                        relative,
                        number,
                        f"`{target}` does not exist.",
                        match.start() + 1,
                        match.end() + 1,
                    )
                )

        if not line.lstrip().startswith("//"):
            for match in TODO_RE.finditer(line):
                findings.append(
                    Finding(
                        "todo-left",
                        relative,
                        number,
                        f"`{match.group(1)}` left in the prose.",
                        match.start() + 1,
                        match.end() + 1,
                    )
                )

        if line.lstrip().startswith("//"):
            continue

        for preferred, avoid in terms:
            for spelling in avoid:
                for match in re.finditer(rf"\b{re.escape(spelling)}\b", line, re.I):
                    findings.append(
                        Finding(
                            "term-drift",
                            relative,
                            number,
                            f"`{match.group(0)}` — this book says `{preferred}`.",
                            match.start() + 1,
                            match.end() + 1,
                        )
                    )

    if not cited:
        findings.append(
            Finding(
                "uncited-chapter",
                relative,
                1,
                "No `// Source:` comment naming the notes this chapter came from, "
                "and no `// Not from notes: <reason>` saying why there is none.",
            )
        )

    return findings


def scan(root: Path = ROOT) -> list[Finding]:
    book = load_book()
    terms = load_terms()
    findings: list[Finding] = []
    for path in book.chapters:
        if path.is_file():
            findings.extend(scan_chapter(path, book, terms, root))
    return sorted(findings, key=lambda f: (f.path, f.line, f.rule))


# --------------------------------------------------------------------------- #


def sarif(findings: list[Finding]) -> dict:
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "prose-scan",
                        "informationUri": "https://github.com/bugabinga/software",
                        "rules": [
                            {
                                "id": rule,
                                "name": rule.replace("-", " ").title().replace(" ", ""),
                                "shortDescription": {"text": short},
                                "fullDescription": {"text": full},
                                "defaultConfiguration": {"level": level},
                                "help": {"text": full},
                            }
                            for rule, (level, short, full) in RULES.items()
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": f.rule,
                        "level": f.level,
                        "message": {"text": f.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": f.path},
                                    "region": {
                                        "startLine": f.line,
                                        "startColumn": f.column,
                                        **(
                                            {"endColumn": f.end_column}
                                            if f.end_column
                                            else {}
                                        ),
                                    },
                                }
                            }
                        ],
                    }
                    for f in findings
                ],
            }
        ],
    }


def as_text(findings: list[Finding]) -> str:
    if not findings:
        return "prose: no mechanical faults\n"
    rows = [
        f"{f.level:>7}  {f.path}:{f.line}  [{f.rule}] {f.message}" for f in findings
    ]
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.level] = counts.get(f.level, 0) + 1
    tally = ", ".join(f"{n} {level}" for level, n in sorted(counts.items()))
    return "\n".join(rows) + f"\n\nprose: {tally}\n"


# --------------------------------------------------------------------------- #


def self_test() -> int:
    """Every rule fires on a tree built to trip it, and on nothing else."""
    import shutil  # noqa: PLC0415 - the self-test's own dependencies
    import tempfile  # noqa: PLC0415

    problems = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "book" / "chapters").mkdir(parents=True)
        (root / "notes").mkdir()
        (root / "notes" / "n.md").write_text("one\ntwo\nthree\n", encoding="utf-8")
        (root / "notes" / "m.md").write_text(
            "\n".join(str(n) for n in range(50)), encoding="utf-8"
        )
        (root / "book" / "book.toml").write_text(
            '[book]\ntitle = "T"\n'
            '[[part]]\ntitle = "P"\nchapters = ["chapters/01-good.typ", '
            '"chapters/02-bad.typ", "chapters/03-bare.typ", '
            '"chapters/04-plural.typ", "chapters/05-exempt.typ", '
            '"chapters/06-two-notes.typ"]\n',
            encoding="utf-8",
        )
        (root / "book" / "terms.toml").write_text(
            '[[term]]\nname = "substrate"\navoid = ["medium"]\n', encoding="utf-8"
        )

        (root / "book" / "chapters" / "01-good.typ").write_text(
            "// Source: notes/n.md, lines 1-3\n= Good\n\nThe substrate holds.\n"
            '#xref("bad", "see")\n',
            encoding="utf-8",
        )
        (root / "book" / "chapters" / "02-bad.typ").write_text(
            "// Source: notes/gone.md, lines 1-2\n"
            "// Source: notes/n.md, lines 40-44\n"
            "= Bad\n\nThe medium holds. TODO tighten.\n"
            '#xref("nowhere", "see")\n'
            '#snippet("code/missing.rs")\n',
            encoding="utf-8",
        )
        (root / "book" / "chapters" / "03-bare.typ").write_text(
            "= Bare\n\nNothing cited.\n", encoding="utf-8"
        )
        (root / "book" / "chapters" / "04-plural.typ").write_text(
            "// Sources:\n//   notes/n.md, lines 1-2\n= Plural\n", encoding="utf-8"
        )
        (root / "book" / "chapters" / "05-exempt.typ").write_text(
            "// Not from notes: living documentation of the prelude.\n= Exempt\n",
            encoding="utf-8",
        )
        # Two notes on one line, both cited correctly. Every range on the line
        # used to be checked against every note on it, so the short one was
        # reported as too short for the long one's range -- an `error`, which
        # is the level that blocks a merge, on prose that is right.
        (root / "book" / "chapters" / "06-two-notes.typ").write_text(
            "// Sources: notes/n.md, lines 1-2, notes/m.md, lines 40-50\n= Two\n",
            encoding="utf-8",
        )

        global ROOT, MANIFEST, TERMS
        saved = (ROOT, MANIFEST, TERMS)
        ROOT, MANIFEST, TERMS = (
            root,
            root / "book" / "book.toml",
            root / "book" / "terms.toml",
        )
        try:
            findings = scan(root)
        finally:
            ROOT, MANIFEST, TERMS = saved

        got = sorted({(f.rule, f.path) for f in findings})
        want = sorted(
            [
                ("dead-note", "book/chapters/02-bad.typ"),
                ("note-line-out-of-range", "book/chapters/02-bad.typ"),
                ("dead-xref", "book/chapters/02-bad.typ"),
                ("dead-snippet", "book/chapters/02-bad.typ"),
                ("todo-left", "book/chapters/02-bad.typ"),
                ("term-drift", "book/chapters/02-bad.typ"),
                ("uncited-chapter", "book/chapters/03-bare.typ"),
            ]
        )
        if got != want:
            problems.append(f"rules fired: {got}\n            wanted: {want}")

        clean = [
            f
            for f in findings
            if f.path.endswith(
                ("01-good.typ", "04-plural.typ", "05-exempt.typ", "06-two-notes.typ")
            )
        ]
        if clean:
            problems.append(f"the clean chapter produced {clean}")

        # `#xref("bad")` in the good chapter must resolve: `02-bad.typ` is a
        # chapter, so its slug is `bad`. That is the prefix-stripping rule.
        if any(f.rule == "dead-xref" and "01-good" in f.path for f in findings):
            problems.append("slug_of does not strip the numeric prefix")

        document = sarif(findings)
        if document["runs"][0]["results"][0]["level"] not in {
            "error",
            "warning",
            "note",
        }:
            problems.append("a result has a level SARIF does not define")
        rule_ids = {r["id"] for r in document["runs"][0]["tool"]["driver"]["rules"]}
        unknown = {r["ruleId"] for r in document["runs"][0]["results"]} - rule_ids
        if unknown:
            problems.append(f"results reference undeclared rules: {unknown}")
        json.dumps(document)  # must serialise

        shutil.rmtree(root, ignore_errors=True)

    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in prose_scan", file=sys.stderr)
        return 1
    print(f"prose_scan: {len(RULES)} rules, each fires exactly where it should")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif", type=Path, help="write SARIF here")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--fail-on",
        default="error",
        choices=["error", "warning", "note", "never"],
        help="lowest level that exits non-zero (default: error)",
    )
    arguments = parser.parse_args()

    if arguments.self_test:
        return self_test()

    findings = scan()
    print(as_text(findings), end="")

    if arguments.sarif:
        arguments.sarif.parent.mkdir(parents=True, exist_ok=True)
        arguments.sarif.write_text(
            json.dumps(sarif(findings), indent=2), encoding="utf-8"
        )
        print(f"wrote {arguments.sarif}", file=sys.stderr)

    if arguments.fail_on == "never":
        return 0
    order = {"error": 3, "warning": 2, "note": 1}
    threshold = order[arguments.fail_on]
    return 1 if any(order[f.level] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
