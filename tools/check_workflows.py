#!/usr/bin/env python3
"""Check the GitHub Actions definitions before they are pushed.

A broken workflow does not fail loudly -- it fails at 06:17 on a Monday, in a
run nobody is watching. Two classes of mistake are worth catching locally:

* invalid YAML (checked when PyYAML happens to be importable);
* a shell heredoc inside a `run:` block whose terminator is indented past the
  block. YAML strips a block scalar's own indentation before the shell ever
  sees it, so a terminator sitting at exactly that indentation is correct and
  arrives at column 0. One indented *further* arrives with leading spaces,
  never closes the heredoc, and bash runs a truncated script ("here-document
  delimited by end-of-file"). One at column 0 in the file is not a shell
  problem at all -- it ends the YAML block early, which the syntax check
  catches. Both are easy to write and neither is visible by eye.

Usage:
    tools/check_workflows.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEREDOC = re.compile(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?")


def heredoc_opener(line: str) -> tuple[str, bool] | None:
    """The heredoc a line opens, if it opens one: `(marker, is_tab_stripping)`.

    `<<` only starts a heredoc outside quotes. Actions' own multiline syntax
    -- `echo "name<<DELIMITER" >> "$GITHUB_OUTPUT"` -- puts the same
    characters inside a string, where they are data, and a lint that cannot
    tell the difference reports every such workflow as broken.
    """
    single = double = False
    index = 0
    while index < len(line):
        character = line[index]
        if character == "'" and not double:
            single = not single
        elif character == '"' and not single:
            double = not double
        elif character == "#" and not single and not double:
            return None  # a comment; nothing after it runs
        elif character == "<" and not single and not double and line[index + 1 : index + 2] == "<":
            if match := HEREDOC.match(line[index:]):
                return match.group(1), line[index : index + 3].startswith("<<-")
            return None
        index += 1
    return None
BLOCK_SCALAR = re.compile(r":\s*[|>][-+]?\d*\s*$")


def check_heredocs(path: Path) -> list[str]:
    problems: list[str] = []
    lines = path.read_text(encoding="utf-8").splitlines()

    index = 0
    while index < len(lines):
        if not BLOCK_SCALAR.search(lines[index]):
            index += 1
            continue

        # The block scalar's content indentation is set by its first
        # non-empty line, and every line below it that is indented at least
        # that far belongs to the block.
        opener_indent = len(lines[index]) - len(lines[index].lstrip())
        body: list[tuple[int, str]] = []
        cursor = index + 1
        base = None
        while cursor < len(lines):
            line = lines[cursor]
            if line.strip() == "":
                body.append((cursor, line))
                cursor += 1
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= opener_indent:
                break
            if base is None:
                base = indent
            body.append((cursor, line))
            cursor += 1

        if base is not None:
            open_heredocs: list[tuple[int, str]] = []
            for number, line in body:
                stripped = line.strip()
                if open_heredocs:
                    marker, _ = open_heredocs[-1][1], None
                    if stripped == marker:
                        indent = len(line) - len(line.lstrip())
                        if indent != base:
                            problems.append(
                                f"{path.relative_to(ROOT)}:{number + 1}: heredoc "
                                f"terminator `{marker}` is indented {indent - base} "
                                "space(s) past the block; the heredoc will never close"
                            )
                        open_heredocs.pop()
                        continue
                if opener := heredoc_opener(stripped):
                    marker, tab_stripping = opener
                    if not tab_stripping:
                        open_heredocs.append((number, marker))
            for number, marker in open_heredocs:
                problems.append(
                    f"{path.relative_to(ROOT)}:{number + 1}: heredoc `{marker}` "
                    "is never terminated inside its block"
                )

        index = cursor
    return problems


def check_yaml(paths: list[Path]) -> list[str]:
    try:
        import yaml  # noqa: PLC0415 - optional
    except ImportError:
        print("PyYAML not installed; skipping the syntax check (CI parses these anyway)")
        return []

    problems = []
    for path in paths:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001 - report whatever it says
            problems.append(f"{path.relative_to(ROOT)}: invalid YAML -- {error}")
    return problems


USES_RE = re.compile(r"^\s*(?:- )?uses:\s*(?P<ref>[^\s#]+)\s*(?P<comment>#.*)?$", re.M)
PINNED_RE = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def check_pins(paths: list[Path]) -> list[str]:
    """Every third-party action is a commit, with its version in a comment.

    A tag is mutable: whoever owns an action can move `v4` onto a different
    commit, and this repository runs those actions with a token that can write
    to it. `actionlint` does not check this and Dependabot is happy either way,
    so nothing else would notice a tag creeping back in -- which is exactly
    how it would happen, one convenient copy-paste at a time.

    The trailing `# v4` is required too, because a bare forty-character hash
    tells a reader nothing about what they are running.
    """
    problems = []
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES_RE.match(line)
            if not match:
                continue
            ref = match.group("ref")
            if ref.startswith("./"):
                continue
            where = f"{path.relative_to(ROOT)}:{number}"
            if not PINNED_RE.match(ref):
                problems.append(f"{where}: {ref} is not pinned to a commit")
            elif not (match.group("comment") or "").strip().startswith("# "):
                problems.append(f"{where}: {ref} has no `# version` comment")
    return problems


def check_tools() -> list[str]:
    """Every tool in `tools/` parses as Python.

    Cheap, and it closes a gap that cost a review: a program embedded in a
    workflow is not syntax-checked by anything, so the only way to know it
    runs is to run it in CI and read the failure. Keeping the programs in
    files means this catches them before they are pushed.
    """
    problems = []
    for path in sorted((ROOT / "tools").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, str(path), "exec")
        except SyntaxError as error:
            problems.append(
                f"{path.relative_to(ROOT)}:{error.lineno}: {error.msg}"
            )
    return problems


def main() -> None:
    paths = sorted((ROOT / ".github").rglob("*.yml")) + sorted((ROOT / ".github").rglob("*.yaml"))
    if not paths:
        sys.exit("no workflow files found under .github/")

    problems = check_yaml(paths) + check_tools() + check_pins(paths)

    for path in paths:
        problems += check_heredocs(path)
        if "\t" in path.read_text(encoding="utf-8"):
            problems.append(f"{path.relative_to(ROOT)}: contains a tab; YAML forbids them for indentation")

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(f"{len(problems)} problem(s) in the workflow definitions")
    tools = len(list((ROOT / "tools").glob("*.py")))
    pins = sum(1 for p in paths for line in p.read_text(encoding="utf-8").splitlines()
               if (m := USES_RE.match(line)) and not m.group("ref").startswith("./"))
    print(f"workflows: {len(paths)} files, {tools} tools, {pins} pinned actions, no problems")


if __name__ == "__main__":
    main()
