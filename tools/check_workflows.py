#!/usr/bin/env python3
"""Check the GitHub Actions definitions before they are pushed.

A broken workflow does not fail loudly -- it fails at 06:17 on a Monday, in a
run nobody is watching. Six classes of mistake are worth catching locally:

* invalid YAML (checked when PyYAML happens to be importable);
* a program under `tools/` that no longer parses as Python;
* a `uses:` that is not a commit SHA, or one carrying no version comment;
* a tab, which YAML forbids for indentation;
* a comment wrapped past the width the author reads at;
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

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HEREDOC = re.compile(r"<<-?\s*'?\"?([A-Za-z_][A-Za-z0-9_]*)'?\"?")

# The width the comments are wrapped to. Not a style preference: the author
# reads these on a phone, and every other language here has a formatter that
# enforces one -- 80 for Markdown and TOML, 88 for Python. Nothing reflows a
# YAML comment, and dprint's yaml plugin never will: it formats structure, not
# prose. So the wrap stays a human decision and this is the gate that stops it
# being a silent one. A round on #81 was spent on a line left at 89 columns by
# an edit that replaced half a sentence, and two more on this gate.
COMMENT_WIDTH = 80
COMMENT = re.compile(r"^\s*#")


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
        elif (
            character == "<"
            and not single
            and not double
            and line[index + 1 : index + 2] == "<"
        ):
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
        import yaml.constructor  # noqa: PLC0415
        import yaml.resolver  # noqa: PLC0415
    except ImportError:
        print(
            "PyYAML not installed; skipping the syntax check (CI parses these anyway)"
        )
        return []

    # YAML says a duplicate key is an error; every common parser instead
    # keeps the last one and says nothing. GitHub Actions does reject it, so
    # the failure is a red run for a file that parsed cleanly here.
    #
    # It is worth a loader of its own because of how it arrives: applying a
    # review suggestion whose range is a line short of the block it replaces
    # leaves the tail of the original behind. That happened three times in
    # one afternoon -- twice from the fleet's suggestions, once from a
    # hand-written one -- and produced a step with two `uses:` keys, which
    # this parser read as valid.
    class StrictLoader(yaml.SafeLoader):
        pass

    def no_duplicates(loader, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in seen:
                mark = key_node.start_mark
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", mark
                )
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    StrictLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicates
    )

    problems = []
    for path in paths:
        try:
            yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
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
            problems.append(f"{path.relative_to(ROOT)}:{error.lineno}: {error.msg}")
    return problems


def check_comment_width(path: Path) -> list[str]:
    """Comment lines wrapped past `COMMENT_WIDTH`.

    Comments only: a long `run:` line or a long expression is the YAML
    formatter's business and sometimes unavoidable, while a comment is prose
    and always wrappable. A line whose overflow is one unbroken token -- a URL,
    a SHA, a long identifier -- is left alone, because breaking it would be
    worse than the overflow and no wrap could have avoided it.

    The escape hatch asks whether the longest token could have fitted on a
    line of its own, not whether deleting it would bring this line under the
    limit. The second question is the one this first asked, and almost every
    line slightly over the limit answers it yes: an 89-column comment
    containing `concurrency` was skipped, which is the exact line the rule was
    written for.
    """
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not COMMENT.match(line) or len(line) <= COMMENT_WIDTH:
            continue
        longest = max((len(word) for word in line.split()), default=0)
        marker = line.index("#") + 2  # the indent, the "#" and the space
        if marker + longest > COMMENT_WIDTH:
            continue  # one long token; no wrapping would have helped
        problems.append(
            f"{path.relative_to(ROOT)}:{number}: comment is {len(line)} columns, "
            f"over {COMMENT_WIDTH}"
        )
    return problems


DOCSTRING_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

COMMENT_LINE = re.compile(r"^\s*#")

# jq filters that answer once for the whole input. Harmless alone; wrong under
# `--paginate`, which is the point of the check below.
AGGREGATE = re.compile(
    r"\|\s*(length|last|first|add|min|max|any|all|unique|sort|group_by)\b"
)

# The quoted arguments after `--jq`, which is where a jq filter lives. Matching
# the window instead read every pipe in it as jq's: YAML's `run: |` joins to
# the next line, so a shell variable named `last` was a finding, and `| sort -u`
# after the call was coreutils reported as jq. Both were correct code the rule
# has no suppression for, and the first was the very idiom it exists to
# require -- `fleet-respond.yml`'s fixed call escaped only because its variable
# happens to be named `state`.
QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"")

JQ_FLAG = re.compile(r"--jq[\"']?[\s,]*")

BETWEEN_PARTS = re.compile(r"[\s,\\]*")


def _call_span(window: str, near: int) -> str:
    """The part of `window` belonging to the invocation around `near`.

    Bounded by the neighbouring `gh` invocations, which is as much structure
    as a window has: a shell line and a Python call both start one.
    """
    before = window.rfind("gh", 0, near)
    after = window.find("gh", near)
    return window[max(before, 0) : after if after != -1 else len(window)]


def _jq_filter(window: str, near: int) -> str:
    """Everything quoted after the `--jq` nearest `near` in `window`, joined.

    Nearest, not first: the window reaches six lines backwards, so an ordinary
    `gh api ... --jq` above a paginated call would otherwise lend it that
    filter and the rule would pass in silence -- a false negative on exactly
    the bug it exists to find. `fleet-respond.yml`'s own `--jq '.draft'` sits
    five lines above the window today, kept outside it by the length of the
    comment above the call it guards.

    Joined rather than tested one at a time because Python splits a long
    filter across adjacent string literals, and the aggregate can land on
    either side of the seam -- `rounds_so_far` had `| length` in the second
    of two.
    """
    # Past the flag *and* its own closing quote: in Python the argument is
    # `"--jq",` and starting at the `-` leaves that quote to be read as the
    # filter's opening one, which swallows the filter and misses the bug.
    flags = list(JQ_FLAG.finditer(window))
    if not flags:
        return ""
    flag = min(flags, key=lambda found: abs(found.start() - near))
    rest = window[flag.end() :]

    # Only the first run of quoted strings, not every quote to the end of the
    # window: a second `gh api` six lines down would otherwise lend this call
    # its filter, and there is no suppression to answer that with. A run is
    # what Python's implicit concatenation produces -- strings separated by
    # nothing but whitespace, commas or a continuation -- so the first token
    # that is none of those ends the filter.
    parts: list[str] = []
    seam = 0
    for found in QUOTED.finditer(rest):
        if parts and BETWEEN_PARTS.fullmatch(rest[seam : found.start()]) is None:
            break
        parts.append(found.group(1) if found.group(1) is not None else found.group(2))
        seam = found.end()
    return " ".join(parts)


def _without_prose(where: str, lines: list[str]) -> list[str]:
    """A copy of `lines` with comments and Python docstrings blanked.

    Blanked rather than removed so an index is still a line number.

    `ast` for the docstrings rather than counting triple quotes, because a
    one-line docstring has two of them and a counter reads that as no
    docstring at all -- which is exactly the shape `post_review.py`'s prose
    would take if anyone shortened it. A parser also cannot mistake the jq
    filter itself for prose, which a quote-counter can when the filter is
    triple-quoted. A file that will not parse keeps its comments blanked and
    nothing else, which is the old behaviour rather than a new hole.
    """
    prose = {number for number, line in enumerate(lines, 1) if COMMENT_LINE.match(line)}
    if where.endswith(".py"):
        try:
            tree = ast.parse("\n".join(lines))
        except SyntaxError:
            tree = None
        for node in ast.walk(tree) if tree else ():
            if not isinstance(node, DOCSTRING_OWNERS):
                continue
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                prose.update(
                    range(first.lineno, (first.end_lineno or first.lineno) + 1)
                )
    return ["" if number in prose else line for number, line in enumerate(lines, 1)]


def paginate_findings(where: str, lines: list[str]) -> list[str]:
    """`gh api --paginate` with a jq filter that aggregates.

    `--paginate` runs the filter once per page and concatenates what each
    returns, so `| length` over 101 reviews answers "6\\n1" rather than 7.
    Three call sites had this and all three broke on #82 the day its review
    count crossed 100: one killed `fleet-respond` outright (run 34809724830,
    a multi-line value into `$GITHUB_OUTPUT`), and two failed silently --
    a `| last | .state` comparison that quietly went false, and a
    `raw.isdigit()` fallback that reset the round counter to zero, which
    mislabels a review header -- the three-round guard is a separate count in
    `fleet-respond.yml`. The shape that works was already in the same file:
    emit one line per match and count the lines in the caller.

    A window rather than a parse, because the call spans lines in YAML and in
    Python alike and both wrap it differently. Three lines is the furthest any
    of the three reached, from the `--paginate` to the aggregate; six is slack
    against a wrap nobody has written yet. It reaches both ways, because `gh`
    takes the flags in either order and a window that only looks forward holds
    only for as long as the next writer wraps the call the way the last three
    did. There is no suppression for a false positive here, so one is answered
    by rewriting the call or narrowing this rule, and this class costs a fleet
    outage.
    """
    problems: list[str] = []
    # Blanked, not dropped, so the line numbers still point at the call.
    # Reaching backwards means reaching over the prose that explains the fix,
    # and that prose quotes the aggregates: `fleet-respond.yml`'s comment
    # names `| length` and `| last`, and `post_review.py`'s docstring names
    # both `| length` and `gh api --paginate`. Docstrings are blanked for the
    # second: no file in the tree needs it today -- measured, with the ast
    # pass and without it, no findings either way -- but a docstring naming
    # the flag and an aggregate within six lines of each other would be
    # reported, and there is no suppression to answer that with.
    code = _without_prose(where, lines)
    for number, line in enumerate(code, 1):
        if "--paginate" not in line:
            continue
        start = max(0, number - 7)
        window = "\n".join(code[start : number + 6])
        # Where the `--paginate` itself sits inside the window, so
        # `_jq_filter` takes the flag belonging to *this* call rather than a
        # neighbour's. The token, not the line: measured from the line start,
        # a `--jq` late on the previous line beats this call's own, which is
        # the false negative in the shape this rule was written for.
        near = sum(len(text) + 1 for text in code[start : number - 1])
        near += line.index("--paginate")
        # Only what `--jq` was actually given, which is also what keeps this
        # file's own prose about the flag from being its first finding.
        # `--slurp` is excluded because it is gh's own answer to this bug
        # (2.55.0; `mise.toml` pins 2.63.2): it hands the filter one array
        # spanning every page, so an aggregate over it is correct and this
        # rule would otherwise forbid the fix it exists to ask for. Scoped to
        # the call and not the window, for the reason `--jq` is: a neighbour
        # six lines away would otherwise exempt this one, and the first call
        # in a block to adopt `--slurp` would silently exempt the rest.
        call = _call_span(window, near)
        if "--slurp" not in call and AGGREGATE.search(_jq_filter(window, near)):
            problems.append(
                f"{where}:{number}: `gh api --paginate` with an "
                "aggregating jq filter; it answers once per page"
            )
    return problems


def check_paginate_aggregate(path: Path) -> list[str]:
    """`paginate_findings` over a file. The split is the self-test's seam."""
    return paginate_findings(
        str(path.relative_to(ROOT)), path.read_text(encoding="utf-8").splitlines()
    )


def self_test() -> int:
    """`paginate_findings`, against every shape it has been wrong about.

    Each case is a correction this rule needed after it landed -- b08980d,
    c3803ef, 82e566f, f96a563, 52efb4a -- and a reader found all five, because
    a scanner that has stopped firing reads exactly like a scanner with
    nothing to report. Half of these assert *caught* for that reason: two of
    the five were false negatives introduced while fixing a false positive,
    and the fixtures were the only thing that noticed.
    """
    # `<P>` rather than the flag itself: these cases are source in a file
    # `main()` scans, so spelling it out would make the rule report its own
    # fixtures -- and there is no suppression to answer that with.
    caught, clean = True, False
    cases: list[tuple[str, bool, str]] = [
        # The bug itself: an aggregate over a paginated call answers per page.
        ("first", caught, 'gh("api", "x", "<P>", "--jq", "[.[]] | length")'),
        # gh takes the flags in either order.
        ("reversed", caught, "gh api --jq '[.[]] | length' repos/x <P>"),
        # Prose above a call must not shield it.
        (
            "under prose",
            caught,
            'def f():\n    """Mentions `| length` and `gh api <P>`."""\n'
            '    gh("api", "<P>", "--jq", "[.[]] | length")',
        ),
        # A neighbour's filter must not be read as this call's.
        (
            "after a neighbour",
            caught,
            "b=$(gh api repos/x --jq '.head.ref')\n"
            "s=$(gh api repos/x/reviews <P> \\\n"
            "  --jq '[.[]] | last | .state')",
        ),
        # Nor a neighbour's `--slurp` exempt it.
        (
            "neighbour slurped",
            caught,
            "a=$(gh api repos/x <P> --slurp --jq '[.[][]] | length')\n"
            "b=$(gh api repos/y <P> --jq '[.[]] | length')",
        ),
        # `--slurp` is gh's own answer to this bug: one array over every page,
        # so an aggregate is correct and forbidding it forbids the fix.
        (
            "slurped",
            clean,
            'gh("api", "<P>", "--slurp", "--jq", "[.[][]] | length")',
        ),
        # An aggregate quoted in the comment that explains the fix.
        (
            "comment quotes it",
            clean,
            "# `wc -l`, not `| length`, and not `| last` either.\n"
            "n=$(gh api repos/x <P> --jq '.[] | .id' | wc -l)",
        ),
        # YAML's `run: |` joins to the next line, so matching any pipe read
        # the block indicator as jq's and a variable named `last` was a find.
        (
            "shell variable",
            clean,
            "run: |\n  last=$(gh api x <P> --jq '.[] | .state')",
        ),
        # `| sort` after the call is coreutils.
        ("shell pipe", clean, "gh api x <P> --jq '.[] | .user.login' | sort -u"),
        # A second call's aggregate must not attach to the paginated one.
        (
            "unrelated neighbour",
            clean,
            "a=$(gh api x <P> --jq '.[] | .id')\n"
            "b=$(gh api y --jq '[.labels[]] | length')",
        ),
    ]

    for name, expected, source in cases:
        suffix = ".py" if source.startswith(("gh(", "def ")) else ".yml"
        spelled = source.replace("<P>", "--" + "paginate")
        found = bool(paginate_findings(name + suffix, spelled.splitlines()))
        assert found == expected, (
            f"{name}: expected {'a finding' if expected else 'none'}, got the other"
        )

    print("check_workflows: the paginate rule catches five shapes and ignores five")
    return 0


def main() -> None:
    if "--self-test" in sys.argv[1:]:
        sys.exit(self_test())

    paths = sorted((ROOT / ".github").rglob("*.yml")) + sorted(
        (ROOT / ".github").rglob("*.yaml")
    )
    if not paths:
        sys.exit("no workflow files found under .github/")

    problems = check_yaml(paths) + check_tools() + check_pins(paths)

    # `tools/` too, for this one: `post_review.py` held the third instance,
    # and a rule that only reads workflows would have left it there.
    for path in [*paths, *sorted((ROOT / "tools").glob("*.py"))]:
        problems += check_paginate_aggregate(path)

    for path in paths:
        problems += check_heredocs(path)
        problems += check_comment_width(path)
        if "\t" in path.read_text(encoding="utf-8"):
            problems.append(
                f"{path.relative_to(ROOT)}: contains a tab; "
                "YAML forbids them for indentation"
            )

    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(f"{len(problems)} problem(s) in the workflow definitions")
    tools = len(list((ROOT / "tools").glob("*.py")))
    pins = sum(
        1
        for p in paths
        for line in p.read_text(encoding="utf-8").splitlines()
        if (m := USES_RE.match(line)) and not m.group("ref").startswith("./")
    )
    print(
        f"workflows: {len(paths)} files, {tools} tools, "
        f"{pins} pinned actions, no problems"
    )


if __name__ == "__main__":
    main()
