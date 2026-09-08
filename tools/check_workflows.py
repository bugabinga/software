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
                if match := HEREDOC.search(stripped):
                    if "<<-" not in stripped:
                        open_heredocs.append((number, match.group(1)))
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


def main() -> None:
    paths = sorted((ROOT / ".github").rglob("*.yml")) + sorted((ROOT / ".github").rglob("*.yaml"))
    if not paths:
        sys.exit("no workflow files found under .github/")

    problems = check_yaml(paths)

    for path in paths:
        problems += check_heredocs(path)
        if "\t" in path.read_text(encoding="utf-8"):
            problems.append(f"{path.relative_to(ROOT)}: contains a tab; YAML forbids them for indentation")

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(f"{len(problems)} problem(s) in the workflow definitions")
    print(f"workflows: {len(paths)} files, no problems")


if __name__ == "__main__":
    main()
