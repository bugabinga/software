#!/usr/bin/env python3
"""Hold the repository's settings to what `repo.toml` says they are.

Five sources of truth were being reconciled by hand: this conversation, the
Markdown, the workflow files, the runtime, and the settings -- and the
settings are the ones that live in no file, cannot be diffed, and cannot be
reviewed. `docs/FLEET.md` asserted a ruleset that had changed under it for
months, and the drift was found one claim at a time by a reviewer rather than
by a gate.

So the settings become a file, and this reads them back.

**Three outcomes per claim, not two.** Matches, differs, or could not be read.
The third is not a detail: this runs both in CI, where the token sees
everything, and in a session behind a proxy that refuses whole API paths. A
checker that called an unreadable section a difference would fail every local
run and teach everyone to ignore it; one that called it agreement would lie.
So unread is reported, loudly, and does not fail.

`--check` fails on a difference. Applying the difference is a separate verb
and a separate credential, deliberately: reading needs nothing, and writing
needs an App that may change the rules that govern the fleet.

Usage:
    tools/repo_state.py --check [--repo owner/name]
    tools/repo_state.py --self-test
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import tomllib

ROOT = Path(__file__).resolve().parent.parent
DECLARED = ROOT / "repo.toml"
DEFAULT_REPO = "bugabinga/software"

# What a section's fetch produced. `UNREAD` is a first-class answer rather
# than an error: see the docstring.
MATCH, DIFFER, UNREAD = "match", "differ", "unread"


def gh(*args: str) -> str | None:
    """Run `gh` and return stdout, or `None` when the call failed.

    `None` and `""` are different answers -- an empty body is a fetch that
    worked -- so this returns the discriminated version rather than the
    falsy-either-way one `tools/fleet_report.py` uses, which only ever reads
    the text.
    """
    binary = shutil.which("gh") or str(ROOT / ".tools" / "gh" / "gh")
    try:
        done = subprocess.run(  # noqa: PLW1510 - the caller reads returncode
            [binary, *args], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return done.stdout


def fetch(path: str) -> Any | None:
    """One API document, or `None` if it could not be read."""
    body = gh("api", path)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def compare(declared: dict[str, Any], actual: dict[str, Any], where: str) -> list[str]:
    """Every declared key that the API answers differently.

    Only declared keys are looked at. `repo.toml` is a set of assertions, not
    a mirror of the API, so a key GitHub adds next year is not this file's
    business until somebody decides it is.
    """
    findings = []
    for key, want in sorted(declared.items()):
        if isinstance(want, dict):
            continue  # a nested table; its own section handles it
        have = actual.get(key)
        # Lists are compared as sets where order is GitHub's to choose.
        same = (
            sorted(want) == sorted(have)
            if isinstance(want, list) and isinstance(have, list)
            else want == have
        )
        if not same:
            findings.append(f"{where}.{key}: declared {want!r}, found {have!r}")
    return findings


def check_repository(declared: dict[str, Any], repo: str) -> tuple[str, list[str]]:
    actual = fetch(f"repos/{repo}")
    if actual is None:
        return UNREAD, ["repository: could not be read"]
    fields = {k: v for k, v in declared.items() if k != "topics"}
    findings = compare(fields, actual, "repository")

    if "topics" in declared:
        topics = fetch(f"repos/{repo}/topics")
        if topics is None:
            findings.append("repository.topics: could not be read")
        else:
            findings += compare(
                {"topics": declared["topics"]},
                {"topics": topics.get("names")},
                "repository",
            )
    return (DIFFER if findings else MATCH), findings


def check_actions(declared: dict[str, Any], repo: str) -> tuple[str, list[str]]:
    """The Actions permissions, which a session behind the proxy cannot read.

    This is the section that most needs the three-outcome design: the field
    that decides whether the fleet may open its own pull requests lives here,
    and no local run will ever see it.
    """
    actual = fetch(f"repos/{repo}/actions/permissions/workflow")
    if actual is None:
        return UNREAD, [
            "actions: could not be read (the token or the proxy refuses this path)"
        ]
    return _verdict(compare(declared, actual, "actions"))


def check_rulesets(declared: dict[str, Any], repo: str) -> tuple[str, list[str]]:
    listing = fetch(f"repos/{repo}/rulesets")
    if listing is None:
        return UNREAD, ["rulesets: could not be read"]

    by_name = {entry.get("name"): entry.get("id") for entry in listing}
    findings: list[str] = []
    for name, want in declared.items():
        if name not in by_name:
            findings.append(
                f"ruleset.{name}: declared, and no ruleset of that name exists"
            )
            continue
        actual = fetch(f"repos/{repo}/rulesets/{by_name[name]}")
        if actual is None:
            findings.append(f"ruleset.{name}: could not be read")
            continue
        findings += _compare_ruleset(name, want, actual)
    return _verdict(findings)


def _compare_ruleset(
    name: str, want: dict[str, Any], actual: dict[str, Any]
) -> list[str]:
    where = f"ruleset.{name}"
    findings: list[str] = []

    if "enforcement" in want and want["enforcement"] != actual.get("enforcement"):
        findings.append(
            f"{where}.enforcement: declared {want['enforcement']!r}, "
            f"found {actual.get('enforcement')!r}"
        )

    if "bypass_actors" in want:
        have = actual.get("bypass_actors") or []
        if len(have) != len(want["bypass_actors"]):
            findings.append(
                f"{where}.bypass_actors: declared "
                f"{len(want['bypass_actors'])}, found {len(have)}"
            )

    if "include" in want:
        have = ((actual.get("conditions") or {}).get("ref_name") or {}).get("include")
        if sorted(want["include"]) != sorted(have or []):
            findings.append(
                f"{where}.include: declared {want['include']!r}, found {have!r}"
            )

    rules = {
        rule.get("type"): (rule.get("parameters") or {})
        for rule in actual.get("rules") or []
    }

    for rule in want.get("rules", []):
        if rule not in rules:
            findings.append(f"{where}: rule {rule!r} is declared and not present")

    for section, key in (
        ("pull_request", "pull_request"),
        ("required_status_checks", "required_status_checks"),
    ):
        if section not in want:
            continue
        if key not in rules:
            findings.append(f"{where}: rule {key!r} is declared and not present")
            continue
        findings += _compare_rule_parameters(
            f"{where}.{section}", want[section], rules[key]
        )
    return findings


def _compare_rule_parameters(
    where: str, want: dict[str, Any], have: dict[str, Any]
) -> list[str]:
    """The two rules whose parameters this repository actually decided.

    `required_status_checks` is reshaped first: the API returns a list of
    `{context, integration_id}` objects and `repo.toml` declares the names,
    because the integration id is GitHub's to choose and nobody decided it.
    """
    if "contexts" in want:
        contexts = [
            entry.get("context") for entry in have.get("required_status_checks") or []
        ]
        have = {
            **have,
            "contexts": contexts,
            "strict": have.get("strict_required_status_checks_policy"),
        }
    return compare(want, have, where)


def _verdict(findings: list[str]) -> tuple[str, list[str]]:
    return (DIFFER if findings else MATCH), findings


def check(repo: str, declared_path: Path = DECLARED) -> int:
    declared = tomllib.loads(declared_path.read_text(encoding="utf-8"))

    sections = [
        ("repository", check_repository, declared.get("repository", {})),
        ("actions", check_actions, declared.get("actions", {})),
        ("rulesets", check_rulesets, declared.get("ruleset", {})),
    ]

    differed, unread, lines = 0, 0, []
    for name, checker, want in sections:
        if not want:
            continue
        state, findings = checker(want, repo)
        if state == MATCH:
            lines.append(f"  ok      {name}")
        elif state == UNREAD:
            unread += 1
            lines.append(f"  unread  {name}")
        else:
            differed += 1
            lines.append(f"  DIFFERS {name}")
        lines += [f"            {finding}" for finding in findings]

    print(f"repo state: {repo}, against {declared_path.name}")
    print("\n".join(lines))

    if unread:
        print(
            f"\n{unread} section(s) could not be read. That is not agreement: "
            "run this where the token can see them before believing it."
        )
    if differed:
        print(
            f"\n{differed} section(s) differ from what {declared_path.name} declares."
        )
        return 1
    return 0


def self_test() -> int:
    """The comparison rules, without a network.

    What is worth pinning is the shape of the answers rather than any live
    value: a declared key that GitHub answers differently is a finding, an
    undeclared key is not, and an unreadable section is neither.
    """
    assert compare({"a": 1}, {"a": 1}, "x") == []
    assert compare({"a": 1}, {"a": 2}, "x") == ["x.a: declared 1, found 2"]
    # Undeclared keys are not this file's business.
    assert compare({"a": 1}, {"a": 1, "b": 9}, "x") == []
    # A key the API does not return at all reads as a difference, not a crash.
    assert compare({"a": 1}, {}, "x") == ["x.a: declared 1, found None"]
    # Order is GitHub's to choose for lists.
    assert compare({"t": ["b", "a"]}, {"t": ["a", "b"]}, "x") == []
    assert compare({"t": ["a"]}, {"t": ["a", "b"]}, "x") != []
    # Nested tables belong to their own section.
    assert compare({"n": {"deep": 1}}, {}, "x") == []

    checks = {
        "required_status_checks": [{"context": "CI", "integration_id": 15368}],
        "strict_required_status_checks_policy": True,
    }
    assert (
        _compare_rule_parameters("r", {"contexts": ["CI"], "strict": True}, checks)
        == []
    )
    assert (
        _compare_rule_parameters("r", {"contexts": ["CI", "Fleet review"]}, checks)
        != []
    )

    actual = {
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"]}},
        "rules": [
            {"type": "deletion"},
            {
                "type": "pull_request",
                "parameters": {"required_approving_review_count": 0},
            },
        ],
    }
    assert (
        _compare_ruleset(
            "Main",
            {
                "enforcement": "active",
                "include": ["~DEFAULT_BRANCH"],
                "rules": ["deletion"],
            },
            actual,
        )
        == []
    )
    assert _compare_ruleset("Main", {"rules": ["required_signatures"]}, actual) != []
    assert (
        _compare_ruleset(
            "Main", {"pull_request": {"required_approving_review_count": 1}}, actual
        )
        != []
    )

    # The declared file must parse and must not be empty, or the gate is a
    # gate over nothing.
    declared = tomllib.loads(DECLARED.read_text(encoding="utf-8"))
    assert declared["repository"]["default_branch"] == "main"
    assert declared["ruleset"]["Main"]["enforcement"] == "active"

    print(
        "repo_state: declared keys compared, undeclared keys ignored, unread is neither"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="compare the repository against repo.toml"
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.check:
        return check(args.repo)
    parser.error("--check or --self-test")
    return 2


if __name__ == "__main__":
    sys.exit(main())
