#!/usr/bin/env python3
"""A count in prose, checked against the thing it counts.

Issue #84's roster: prose that states a count, a list or a coverage claim
which a program in the tree already owns, true when written and false after
the next change to the owner, with nothing reading it. The general rule -- a
numeral near a symbol another file exports -- is unwriteable without noise;
every one of the six instances on #82 was found by a reader who happened to
count. One narrower shape earns a gate here: a number word immediately before
a colon that heads a list, compared against the list's length. It caught the
`check_workflows.py` instance exactly ("Six classes of mistake" over seven
bullets), and it reads on any file format because it never has to know what a
comment marker looks like -- see `bullet_count`.

The other shape the issue named -- a number word in the sentence naming
`TRIMMED_BY_PERMISSION`, compared against its length -- was tried and is not
here. Scanning raw text for it needs the same prose/code split
`check_workflows.py`'s `_without_prose` already does, since a bare mention in
a `compare(...)` call otherwise absorbs the rest of the function into one
"sentence" for want of a period. Fixing that is not what sank it: with the
split in place, `tools/repo_state.py:409` still reads "the same distinction,
and the same reason, as `TRIMMED_BY_PERMISSION` one section up" -- correct
prose, on the file the gate exists to protect, that a naive reading marks
wrong because "one" there names a section, not a count. Bullet counts do not
have this problem: the number word is never doing double duty, since it
either counts the list under it or it is not before a colon that heads one.
A word as common as "one" naming a length is not decidable the same way, and
telling the two readings apart is judgement, not a gate. "not six and four"
call sites (`site/skill/index.html`, owned by CSS) and "in CI, where the
token sees everything" (`tools/repo_state.py`, a stale claim rather than a
numeral) are outside both shapes and stay a reader's job too.

Usage:
    tools/check_counts.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
NUMBER_ALTERNATION = "|".join(NUMBER_WORDS)

EXTENSIONS = {
    ".typ",
    ".py",
    ".js",
    ".json",
    ".css",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".sh",
}


def tracked_files() -> list[Path]:
    """Every hand-written file git tracks, minus `notes/`.

    By what a file is, not by where somebody remembered to look -- the same
    reason `check-format` reads `git ls-files` rather than a directory list.
    `notes/` is excluded because it is source material kept verbatim: a stale
    count there is not this repository's to fix.
    """
    output = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout
    return [
        ROOT / name
        for name in output.split("\0")
        if name and Path(name).suffix in EXTENSIONS and not name.startswith("notes/")
    ]


# A number word as the last word before a trailing colon. Deliberately not
# anchored to a comment marker or a language: `find` the colon, and the
# marker under it decides whether it heads a list at all.
NUMBER_COLON = re.compile(rf"\b(?P<word>{NUMBER_ALTERNATION})\b\s*:\s*$", re.IGNORECASE)

BULLET = re.compile(r"^(?:[*-]|\d+\.)\s+\S")

# A leading comment marker, if the line has one -- `#` (Python, TOML, YAML)
# or `//` (Typst). Stripped only to find where the content starts; a plain
# Markdown or prose line has none and is used as-is.
LEADER = re.compile(r"^(?P<indent>[ \t]*)(?:#+|//+)?[ \t]?")


def _content(line: str) -> tuple[str, int]:
    """A line's text past any comment marker, and the column it starts at.

    The column is what tells a continuation line (indented past it) from a
    new list item (flush with it) -- see `_list_length`.
    """
    rest = LEADER.sub("", line, count=1)
    stripped = rest.lstrip()
    return stripped, len(line) - len(stripped)


def _blank(line: str) -> bool:
    """Whether a line carries no content once a comment marker is stripped.

    `"#"` on its own is a blank line inside a wrapped comment, the same as an
    empty one -- `_content` would otherwise read it as a zero-column, empty
    "item" and stop the list one line early.
    """
    content, _ = _content(line)
    return content == ""


def _list_length(lines: list[str], colon_index: int) -> int | None:
    """Items in the list right after `lines[colon_index]`, or `None`.

    `None` when the next non-blank line is not a list item at all -- the
    colon heads prose, not a list, and this rule has nothing to say about it.
    A blank line inside the list is tolerated by peeking past it for another
    item at the same column; anything else, including a line indented less
    than the first item, ends it.
    """
    index = colon_index + 1
    while index < len(lines) and _blank(lines[index]):
        index += 1
    if index >= len(lines):
        return None
    content, column = _content(lines[index])
    if not BULLET.match(content):
        return None

    count = 0
    while index < len(lines):
        line = lines[index]
        if _blank(line):
            lookahead = index + 1
            while lookahead < len(lines) and _blank(lines[lookahead]):
                lookahead += 1
            if lookahead < len(lines):
                peek_content, peek_column = _content(lines[lookahead])
                if peek_column == column and BULLET.match(peek_content):
                    index = lookahead
                    continue
            break
        content, this_column = _content(line)
        if this_column == column and BULLET.match(content):
            count += 1
            index += 1
            continue
        if this_column > column:
            index += 1  # a continuation of the item above
            continue
        break
    return count


def bullet_count(text: str) -> list[tuple[int, str, int]]:
    """`(line, word, actual)` for every number word that misnames the list under it.

    Only where the two disagree -- a number word before a colon that heads a
    list of exactly that length is the common case and not a finding.
    """
    lines = text.splitlines()
    findings = []
    for index, line in enumerate(lines):
        match = NUMBER_COLON.search(line)
        if not match:
            continue
        length = _list_length(lines, index)
        if length is None:
            continue
        word = match.group("word").lower()
        if NUMBER_WORDS[word] != length:
            findings.append((index + 1, word, length))
    return findings


def check_bullet_counts(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line, word, actual in bullet_count(text):
            problems.append(
                f"{path.relative_to(ROOT)}:{line}: says {word!r} but the list "
                f"below has {actual} item(s)"
            )
    return problems


def main() -> None:
    paths = tracked_files()
    problems = check_bullet_counts(paths)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(f"{len(problems)} count(s) in prose disagree with what they count")
    print(f"counts: {len(paths)} files, no problems")


class BulletCounts(unittest.TestCase):
    """`bullet_count`, against the shapes it has to tell apart."""

    def test_a_matching_count_is_not_a_finding(self) -> None:
        text = "There are exactly two:\n\n1. Fix it.\n2. Answer it.\n"
        self.assertEqual(bullet_count(text), [])

    def test_a_wrong_count_is_a_finding(self) -> None:
        text = "There are exactly two:\n\n1. Fix it.\n2. Answer it.\n3. Or a third.\n"
        self.assertEqual(bullet_count(text), [(1, "two", 3)])

    def test_a_number_before_prose_is_not_a_list(self) -> None:
        # `chapter-drafter.md`'s shape: the colon introduces an explanation,
        # not a list, and this rule has nothing to say about it.
        text = "You should not develop one:\nthe prose is the author's.\n"
        self.assertEqual(bullet_count(text), [])

    def test_a_wrapped_comment_list(self) -> None:
        # `check_workflows.py`'s own shape: no comment marker to strip, a
        # continuation line indented past the marker, blank line tolerated.
        text = (
            "worth catching locally, six:\n"
            "\n"
            "* one\n"
            "* two, which wraps onto\n"
            "  a second line\n"
            "\n"
            "* three\n"
        )
        self.assertEqual(bullet_count(text), [(1, "six", 3)])

    def test_a_commented_list(self) -> None:
        text = "# three:\n#\n# * a\n# * b\n"
        self.assertEqual(bullet_count(text), [(1, "three", 2)])

    def test_indented_less_ends_the_list(self) -> None:
        text = "four:\n\n- a\n- b\nback to margin\n- c\n- d\n"
        self.assertEqual(bullet_count(text), [(1, "four", 2)])

    def test_the_tree_passes_its_own_gate(self) -> None:
        self.assertEqual(check_bullet_counts(tracked_files()), [])


if __name__ == "__main__":
    main()
