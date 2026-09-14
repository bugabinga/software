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

`--check` fails on a difference and needs no credential. `--apply` makes the
repository match and needs an App that may change the rules governing the
fleet, which is why it is a separate verb, a separate workflow and a separate
environment.

Usage:
    tools/repo_state.py --check [--repo owner/name]
    tools/repo_state.py --apply [--repo owner/name]
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


def write(method: str, path: str, body: dict[str, Any]) -> str | None:
    """One API write. Returns `None` on success, or the failure to report.

    `--input -` rather than a string of `-f key=value` pairs: the fields here
    are booleans and lists, and `gh`'s field syntax turns every one of them
    into a string, so `has_wiki=false` would arrive as the truthy `"false"`.
    """
    binary = shutil.which("gh") or str(ROOT / ".tools" / "gh" / "gh")
    try:
        done = subprocess.run(  # noqa: PLW1510 - the caller reads returncode
            [binary, "api", "-X", method, path, "--input", "-"],
            input=json.dumps(body),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"{method} {path}: {error}"
    if done.returncode != 0:
        detail = done.stderr.strip().splitlines()
        return f"{method} {path}: {detail[-1] if detail else 'failed'}"
    return None


def fetch(path: str) -> Any | None:
    """One API document, or `None` if it could not be read."""
    body = gh("api", path)
    if body is None:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


# The eight fields GitHub removes from the repository object it hands a
# `contents: read` workflow token, rather than reporting them. Measured, on
# run 103821744889: arming this check in CI turned these eight from matching
# into disagreeing, because an absent key and a null one look identical
# through `.get()`.
#
# Named rather than inferred from absence, and that is the point. "Any key
# the document does not carry is unread" would also swallow `has_wikis` for
# `has_wiki` -- a hand-written file's most likely fault, silently unchecked
# under every credential. A key missing from this list is a difference, so a
# typo fails and a trim GitHub adds later fails too, which is the direction
# to fail in.
TRIMMED_BY_PERMISSION = frozenset(
    {
        "allow_auto_merge",
        "allow_merge_commit",
        "allow_rebase_merge",
        "allow_squash_merge",
        "allow_update_branch",
        "delete_branch_on_merge",
        "squash_merge_commit_message",
        "squash_merge_commit_title",
    }
)


def compare(
    declared: dict[str, Any],
    actual: dict[str, Any],
    where: str,
    may_be_hidden: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
    """Declared keys the API answers differently, and ones it does not answer.

    Only declared keys are looked at. `repo.toml` is a set of assertions, not
    a mirror of the API, so a key GitHub adds next year is not this file's
    business until somebody decides it is.

    A key absent from the document is unread *if the caller says that key can
    be hidden by permission* -- see `TRIMMED_BY_PERMISSION`. Otherwise absence
    is a difference, because the likeliest reason a hand-written file names a
    field the API does not carry is that the field is misspelled.
    """
    findings: list[str] = []
    unread: list[str] = []
    for key, want in sorted(declared.items()):
        if isinstance(want, dict):
            continue  # a nested table; its own section handles it
        if key not in actual:
            if key in may_be_hidden:
                unread.append(f"{where}.{key}: the token cannot see this field")
            else:
                findings.append(f"{where}.{key}: declared {want!r}, found nothing")
            continue
        have = actual[key]
        # Lists are compared as sets where order is GitHub's to choose.
        same = (
            sorted(want) == sorted(have)
            if isinstance(want, list) and isinstance(have, list)
            else want == have
        )
        if not same:
            findings.append(f"{where}.{key}: declared {want!r}, found {have!r}")
    return findings, unread


def check_repository(declared: dict[str, Any], repo: str) -> tuple[str, list[str]]:
    actual = fetch(f"repos/{repo}")
    if actual is None:
        return UNREAD, ["repository: could not be read"]
    fields = {k: v for k, v in declared.items() if k != "topics"}
    findings, unread = compare(fields, actual, "repository", TRIMMED_BY_PERMISSION)

    if "topics" in declared:
        topics = fetch(f"repos/{repo}/topics")
        if topics is None:
            # `repos/{repo}/topics` can be refused the way
            # `actions/permissions/workflow` already is, and an endpoint
            # nobody could read is not a setting that disagrees.
            unread.append("repository.topics: could not be read")
        else:
            more, more_unread = compare(
                {"topics": declared["topics"]},
                {"topics": topics.get("names")},
                "repository",
            )
            findings += more
            unread += more_unread
    return _verdict(findings, unread)


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
    return _verdict(*compare(declared, actual, "actions"))


def check_rulesets(declared: dict[str, Any], repo: str) -> tuple[str, list[str]]:
    listing = fetch(f"repos/{repo}/rulesets")
    if listing is None:
        return UNREAD, ["rulesets: could not be read"]

    by_name = {entry.get("name"): entry.get("id") for entry in listing}
    findings: list[str] = []
    unread: list[str] = []

    # A whole ruleset nobody declared, for the reason `_compare_ruleset` gives
    # about a rule nobody declared, one level up: `Fleet log` existed for weeks
    # against a file that named only `Main`, and this read `ok rulesets`. So
    # the declaration is every ruleset, not every rule of some of them.
    #
    # The finding names both ways out, because `--apply` cannot take either:
    # it writes the declared rulesets and never deletes one. That is
    # deliberate -- deleting a ruleset is irreversible and a program with no
    # judgement in it should not do it from a file somebody edited -- but it
    # means this difference stays red until a person acts, which is what the
    # text has to say.
    for name in sorted(set(by_name) - set(declared)):
        findings.append(
            f"ruleset.{name}: exists and is not declared. --apply will not "
            "remove it: declare it here, or delete it in the web UI"
        )

    for name, want in declared.items():
        if name not in by_name:
            findings.append(
                f"ruleset.{name}: declared, and no ruleset of that name exists"
            )
            continue
        actual = fetch(f"repos/{repo}/rulesets/{by_name[name]}")
        if actual is None:
            unread.append(f"ruleset.{name}: could not be read")
            continue
        findings += _compare_ruleset(name, want, actual)
    return _verdict(findings, unread)


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
        # Compared by content, not by count: an actor swapped for another is
        # the whole of the change worth catching, and it keeps the length the
        # same. Sorted on the printed form because the API chooses the order
        # and the entries are small dictionaries.
        have = _actors(actual.get("bypass_actors") or [])
        declared_actors = _actors(want["bypass_actors"])
        if have != declared_actors:
            findings.append(
                f"{where}.bypass_actors: declared {declared_actors}, found {have}"
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

    # The other direction, which is the one that matters: `repo.toml` declares
    # the ruleset complete, so a rule added in the web UI -- a
    # `commit_message_pattern`, a `required_deployments` -- is drift even
    # though nothing declared is missing. `--apply` would remove it on the
    # next write, and the gap between the two writes is what this closes.
    declared_rules = set(want.get("rules", [])) | {
        section
        for section in ("pull_request", "required_status_checks")
        if section in want
    }
    for rule in sorted(set(rules) - declared_rules):
        findings.append(f"{where}: rule {rule!r} is present and not declared")

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
    # No `may_be_hidden`: a ruleset's own document is not trimmed by
    # permission the way the repository object is, so a parameter missing
    # here is real drift and reads as one -- "declared X, found nothing"
    # rather than a message about a token, which would send whoever is
    # holding the red run to the App's grant instead of to the ruleset.
    findings, unread = compare(want, have, where)
    return findings + unread


def _actors(actors: list[Any]) -> list[str]:
    return sorted(json.dumps(actor, sort_keys=True) for actor in actors)


def _verdict(
    findings: list[str], unread: list[str] | None = None
) -> tuple[str, list[str]]:
    """A difference outranks an unreadable endpoint; both outrank agreement.

    The order matters because only `DIFFER` fails the run: a section that
    disagreed about one field and could not read another has disagreed.
    """
    lines = [*findings, *(unread or [])]
    if findings:
        return DIFFER, lines
    if unread:
        return UNREAD, lines
    return MATCH, lines


def apply_state(repo: str, declared_path: Path = DECLARED) -> int:
    """Make the repository match the file, for the parts it is safe to write.

    Idempotent by construction: every section is compared before it is
    written, so a run that changes nothing found nothing to change. There is
    no state file, because GitHub is the state.
    """
    declared = tomllib.loads(declared_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    changed: list[str] = []

    fields = {k: v for k, v in declared.get("repository", {}).items() if k != "topics"}
    if fields:
        actual = fetch(f"repos/{repo}")
        if actual is None:
            failures.append("repository: could not be read, so nothing was written")
        else:
            drift = {k: v for k, v in fields.items() if actual.get(k) != v}
            if drift:
                error = write("PATCH", f"repos/{repo}", drift)
                (failures if error else changed).append(
                    error or f"repository: {', '.join(sorted(drift))}"
                )

    topics = declared.get("repository", {}).get("topics")
    if topics is not None:
        actual = fetch(f"repos/{repo}/topics")
        if actual is None:
            failures.append("topics: could not be read, so nothing was written")
        elif sorted(actual.get("names") or []) != sorted(topics):
            error = write("PUT", f"repos/{repo}/topics", {"names": topics})
            (failures if error else changed).append(error or "repository: topics")

    actions = declared.get("actions", {})
    if actions:
        actual = fetch(f"repos/{repo}/actions/permissions/workflow")
        if actual is None:
            failures.append("actions: could not be read, so nothing was written")
        elif any(actual.get(k) != v for k, v in actions.items()):
            # The whole document rather than the drift: this endpoint replaces
            # rather than merges, so sending one field resets the other.
            error = write("PUT", f"repos/{repo}/actions/permissions/workflow", actions)
            (failures if error else changed).append(
                error or f"actions: {', '.join(sorted(actions))}"
            )

    rulesets = declared.get("ruleset", {})
    if rulesets:
        listing = fetch(f"repos/{repo}/rulesets")
        if listing is None:
            failures.append("rulesets: could not be read, so nothing was written")
        else:
            by_name = {entry.get("name"): entry.get("id") for entry in listing}
            for name, want in rulesets.items():
                unknown = sorted(
                    rule for rule in want.get("rules", []) if rule not in PLAIN_RULES
                )
                if unknown:
                    # Silently dropping it would write a ruleset without the
                    # rule while `--check` reported it missing forever: the
                    # gate would be permanently red and the apply would never
                    # fix it. A typo in `repo.toml` has to fail here.
                    failures.append(
                        f"ruleset {name}: {unknown} is declared and this program "
                        "does not know how to write it -- add it to PLAIN_RULES "
                        "or give it a parameters section"
                    )
                    continue
                payload = ruleset_payload(name, want)
                if name in by_name:
                    # Compared first, like the two sections above: a PUT that
                    # sends what is already there is not a change, and a log
                    # that says it changed the ruleset on every run is a log
                    # nobody can read a real change out of. And a read that
                    # failed is not a comparison, so it does not write -- the
                    # rule the other two sections already follow, and this is
                    # the write that governs merging.
                    actual = fetch(f"repos/{repo}/rulesets/{by_name[name]}")
                    if actual is None:
                        failures.append(
                            f"ruleset {name}: could not be read, so nothing was written"
                        )
                        continue
                    if not _compare_ruleset(name, want, actual):
                        continue
                    error = write(
                        "PUT", f"repos/{repo}/rulesets/{by_name[name]}", payload
                    )
                else:
                    error = write("POST", f"repos/{repo}/rulesets", payload)
                (failures if error else changed).append(error or f"ruleset: {name}")

    print(f"repo state: applying {declared_path.name} to {repo}")
    for line in changed:
        print(f"  changed {line}")
    for line in failures:
        print(f"  FAILED  {line}")
    if not changed and not failures:
        print("  nothing to change")
    return 1 if failures else 0


# Rules carrying no parameters of their own. A ruleset write replaces every
# rule at once, which is why `repo.toml` declares the whole ruleset rather
# than a subset: what is not declared is what should not exist.
PLAIN_RULES = frozenset(
    {
        "creation",
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
        "update",
    }
)


def ruleset_payload(name: str, want: dict[str, Any]) -> dict[str, Any]:
    """The complete ruleset GitHub expects, built from the declaration."""
    rules: list[dict[str, Any]] = [
        {"type": rule} for rule in sorted(want.get("rules", [])) if rule in PLAIN_RULES
    ]
    if "pull_request" in want:
        rules.append({"type": "pull_request", "parameters": dict(want["pull_request"])})
    if "required_status_checks" in want:
        checks = want["required_status_checks"]
        rules.append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "required_status_checks": [
                        {"context": context} for context in checks.get("contexts", [])
                    ],
                    "strict_required_status_checks_policy": checks.get("strict", False),
                    # Declared in `repo.toml` and compared on the way back, so
                    # it has to be written on the way out: a parameter this
                    # payload omits is one `--check` can go red on and
                    # `--apply` can never set.
                    "do_not_enforce_on_create": checks.get(
                        "do_not_enforce_on_create", False
                    ),
                },
            }
        )
    return {
        "name": name,
        "target": "branch",
        "enforcement": want.get("enforcement", "active"),
        "bypass_actors": want.get("bypass_actors", []),
        "conditions": {"ref_name": {"include": want.get("include", []), "exclude": []}},
        "rules": rules,
    }


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
    assert compare({"a": 1}, {"a": 1}, "x") == ([], [])
    assert compare({"a": 1}, {"a": 2}, "x") == (["x.a: declared 1, found 2"], [])
    # Undeclared keys are not this file's business.
    assert compare({"a": 1}, {"a": 1, "b": 9}, "x") == ([], [])
    # A key the caller says can be hidden by permission is unread when it is
    # absent. This is what arming the check in CI needed: the repository
    # object a `contents: read` token receives has no merge settings in it,
    # and calling that eight disagreements turned the gate red on a
    # repository that matched.
    findings, unread = compare({"a": 1}, {}, "x", frozenset({"a"}))
    assert findings == []
    assert unread == ["x.a: the token cannot see this field"]
    # A key that is absent and *not* on that list is a difference, because
    # the likeliest cause is a misspelling in a hand-written file. Without
    # this, `has_wikis` for `has_wiki` would pass under every credential.
    assert compare({"has_wikis": True}, {"has_wiki": True}, "repository") == (
        ["repository.has_wikis: declared True, found nothing"],
        [],
    )
    # And every trimmed field is one this file actually declares, so the list
    # cannot rot into permission for a key nobody asserts.
    declared_repo = tomllib.loads(DECLARED.read_text(encoding="utf-8"))["repository"]
    assert set(declared_repo) >= TRIMMED_BY_PERMISSION
    # A key present and null is an answer, and answers are compared.
    assert compare({"a": 1}, {"a": None}, "x") == (
        ["x.a: declared 1, found None"],
        [],
    )
    # Order is GitHub's to choose for lists.
    assert compare({"t": ["b", "a"]}, {"t": ["a", "b"]}, "x") == ([], [])
    assert compare({"t": ["a"]}, {"t": ["a", "b"]}, "x")[0] != []
    # Nested tables belong to their own section.
    assert compare({"n": {"deep": 1}}, {}, "x") == ([], [])

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
                "pull_request": {"required_approving_review_count": 0},
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
    # A rule nobody declared is drift too, because the declaration is the
    # whole ruleset. Without `pull_request` declared, `actual` has one.
    assert "not declared" in " ".join(
        _compare_ruleset("Main", {"rules": ["deletion"]}, actual)
    )
    # An actor swapped for another keeps the count and changes the ruleset.
    swapped = {**actual, "bypass_actors": [{"actor_id": 2, "actor_type": "Team"}]}
    assert (
        _compare_ruleset(
            "Main", {"bypass_actors": [{"actor_id": 1, "actor_type": "Team"}]}, swapped
        )
        != []
    )

    # Unread is neither agreement nor a difference, and a difference wins.
    assert _verdict([], []) == (MATCH, [])
    assert _verdict([], ["x: could not be read"])[0] == UNREAD
    assert _verdict(["x.a: declared 1, found 2"], ["y: could not be read"])[0] == DIFFER

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
    parser.add_argument(
        "--apply",
        action="store_true",
        help="make the repository match repo.toml (needs a writing credential)",
    )
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.apply:
        return apply_state(args.repo)
    if args.check:
        return check(args.repo)
    parser.error("--check, --apply or --self-test")
    return 2


if __name__ == "__main__":
    sys.exit(main())
