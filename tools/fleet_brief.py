#!/usr/bin/env python3
"""Work out which fleet agent to run, and hand it its brief.

The briefs live in `.claude/fleet/*.md` rather than inside the workflow, so
that changing what an agent is told on a given occasion is a readable diff
and not a YAML edit. Each brief carries a small frontmatter header naming the
agent to run, the branch it should push to, and why the trigger exists.

Routing is deliberately a separate, testable thing from running the agent:
CI needs an API key to run one, but nothing needs a key to check that the
right brief is chosen and filled in.

Usage:
    tools/fleet_brief.py --trigger notes-arrived --changed notes/a.md,notes/b.md
    tools/fleet_brief.py --trigger on-demand --agent prose-editor --target "chapter 3"
    tools/fleet_brief.py --list
    tools/fleet_brief.py --self-test

Prints the filled-in brief on stdout, and `agent=` / `branch=` lines to the
path in $GITHUB_OUTPUT when that is set.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / ".claude" / "fleet"
AGENTS = ROOT / ".claude" / "agents"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


class BriefError(RuntimeError):
    pass


def issue_section(body: str, heading: str) -> str:
    """The text under one heading of a GitHub issue form.

    A form renders as `### Field label` followed by the answer, so a field is
    addressable by its label. Returns "" when the field is absent or was left
    empty, which for an optional field is the normal case.
    """
    lines = body.replace("\r\n", "\n").splitlines()
    wanted = heading.strip().lower()
    collected: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("### "):
            if inside:
                break
            inside = line[4:].strip().lower() == wanted
            continue
        if inside:
            collected.append(line)
    text = "\n".join(collected).strip()
    # GitHub writes this into a field the author left blank.
    return "" if text == "_No response_" else text


def agent_from_issue(body: str, known: set[str]) -> str | None:
    """Which agent the issue form's dropdown named.

    The option text is `name — what it does`, so the first token is the agent.
    Checked against the definitions that exist rather than trusted, because a
    dropdown edited in the form but not in `.claude/agents/` would otherwise
    dispatch a name nothing implements.
    """
    chosen = issue_section(body, "Which agent")
    if not chosen:
        return None
    candidate = chosen.split()[0].strip("`*_")
    return candidate if candidate in known else None


def load(trigger: str) -> tuple[dict[str, str], str]:
    path = BRIEFS / f"{trigger}.md"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in BRIEFS.glob("*.md")))
        raise BriefError(f"no brief for trigger {trigger!r}; have: {available}")

    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise BriefError(f"{path.relative_to(ROOT)} has no frontmatter header")

    header: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            header[key.strip()] = value.strip()
    for required in ("agent", "branch", "why"):
        if required not in header:
            raise BriefError(f"{path.relative_to(ROOT)} is missing `{required}:`")
    return header, match.group(2)


def fill(text: str, values: dict[str, str]) -> str:
    """Substitute `{{name}}`, refusing to leave one unfilled.

    An unfilled placeholder would reach the agent as literal braces and be
    read as part of the instruction, which is worse than failing here.
    """
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values or not values[key]:
            missing.append(key)
            return match.group(0)
        return values[key]

    filled = PLACEHOLDER.sub(replace, text)
    if missing:
        raise BriefError(
            f"this trigger needs {', '.join(sorted(set(missing)))}; "
            "pass --changed, --agent or --target"
        )
    return filled


def build(
    trigger: str,
    changed: list[str],
    agent: str | None,
    target: str | None,
    pr: str | None = None,
    issue: str | None = None,
) -> tuple[str, str, str]:
    header, body = load(trigger)

    values = {
        "stamp": date.today().isoformat(),
        "changed": "\n".join(f"- `{path}`" for path in changed),
        "target": target or "",
        "agent": agent or "",
        "pr": pr or "",
        "issue": issue or "",
    }
    # The header may itself name the agent, in which case it wins over the
    # command line -- a trigger's brief decides whose beat it is.
    resolved_agent = fill(header["agent"], values)
    values["agent"] = resolved_agent

    if not (AGENTS / f"{resolved_agent}.md").is_file():
        raise BriefError(
            f"brief {trigger!r} names agent {resolved_agent!r}, "
            f"which has no definition in {AGENTS.relative_to(ROOT)}"
        )

    return resolved_agent, fill(header["branch"], values), fill(body, values).strip()


def self_test() -> None:
    """Check every brief routes, fills and names a real agent."""
    failures = []
    samples = {
        "changed": ["notes/x.md"],
        "agent": "prose-editor",
        "target": "chapter 3",
        "pr": "42",
        "issue": "7",
    }
    for path in sorted(BRIEFS.glob("*.md")):
        trigger = path.stem
        try:
            agent, branch, body = build(
                trigger,
                samples["changed"],
                samples["agent"],
                samples["target"],
                samples["pr"],
                samples["issue"],
            )
            if PLACEHOLDER.search(body) or PLACEHOLDER.search(branch):
                failures.append(f"{trigger}: placeholder survived filling")
            elif len(body) < 200:
                failures.append(f"{trigger}: brief is suspiciously short")
            else:
                print(f"{trigger:20} -> {agent:20} {branch}")
        except BriefError as error:
            failures.append(f"{trigger}: {error}")

    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        sys.exit(f"{len(failures)} brief(s) broken")
    print(f"\n{len(list(BRIEFS.glob('*.md')))} briefs, all route to a defined agent")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trigger", help="which brief to use")
    parser.add_argument(
        "--changed", default="", help="comma or newline separated paths"
    )
    parser.add_argument(
        "--agent", help="agent to run, for triggers that do not fix one"
    )
    parser.add_argument("--target", help="what to work on, for on-demand dispatch")
    parser.add_argument("--pr", help="pull request number, for the review trigger")
    parser.add_argument("--issue", help="issue number, for the issue triggers")
    parser.add_argument(
        "--issue-body-file",
        type=Path,
        help="file holding an issue body; the agent and target are read "
        "from its form fields",
    )
    parser.add_argument("--list", action="store_true", help="list the triggers")
    parser.add_argument("--self-test", action="store_true", help="check every brief")
    arguments = parser.parse_args()

    if arguments.self_test:
        self_test()
        return
    if arguments.list:
        for path in sorted(BRIEFS.glob("*.md")):
            header, _ = load(path.stem)
            print(f"{path.stem:20} {header['agent']:20} {header['why']}")
        return
    if not arguments.trigger:
        parser.error("--trigger is required")

    changed = [p.strip() for p in re.split(r"[,\n]", arguments.changed) if p.strip()]

    if arguments.issue_body_file:
        body = arguments.issue_body_file.read_text(encoding="utf-8")
        known = {path.stem for path in AGENTS.glob("*.md")}
        if not arguments.agent:
            arguments.agent = agent_from_issue(body, known)
        if not arguments.target:
            arguments.target = (
                issue_section(body, "What exactly")
                or issue_section(body, "What happened")
                or body.strip()
            )
            extra = issue_section(body, "Anything it must or must not do")
            if extra:
                arguments.target += "\n\nConstraints given:\n" + extra
    try:
        agent, branch, body = build(
            arguments.trigger,
            changed,
            arguments.agent,
            arguments.target,
            arguments.pr,
            arguments.issue,
        )
    except BriefError as error:
        sys.exit(str(error))

    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"agent={agent}\nbranch={branch}\n")
    print(body)


if __name__ == "__main__":
    main()
