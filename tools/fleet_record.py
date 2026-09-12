#!/usr/bin/env python3
"""Write down what a fleet run was, so the report can say more than what it cost.

The execution output Claude Code leaves behind says how many turns a run took,
what it cost and which model served it. It does not say what the run was *for*:
which trigger fired, which agent was dispatched, what it was asked to do, or
what came out the other end. Without that, `fleet_report.py` has to guess the
agent from the workflow name -- which works for the two single-agent workflows
and calls everything `fleet.yml` dispatches "dispatched", lumping the drafter,
the cartographer and the gardener into one row.

So each dispatching workflow writes this next to the execution output and
uploads both. The join key is the run id.

The brief is recorded as a hash and a length rather than its text. It is
generated from a template and the occasion, it can be long, and the useful
question is "was this the same instruction as last time" -- which a digest
answers and a copy of the prose does not.

Usage:
    tools/fleet_record.py --out DIR --trigger weekly-garden --agent pipeline-gardener
    tools/fleet_record.py --self-test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def env(name: str) -> str | None:
    value = os.environ.get(name)
    return value or None


def git(*args: str) -> str | None:
    """A git fact, or None. Never raises: a record is better than a failure."""
    try:
        done = subprocess.run(  # noqa: PLW1510 - returncode is read below
            ["git", *args], capture_output=True, text=True, cwd=ROOT, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() or None if done.returncode == 0 else None


def digest_of(path: Path | None) -> tuple[str | None, int | None]:
    if path is None or not path.is_file():
        return None, None
    raw = path.read_bytes()
    return hashlib.sha256(raw).hexdigest()[:16], len(raw)


def record(
    trigger: str | None,
    agent: str | None,
    model: str | None,
    brief: Path | None,
) -> dict:
    brief_sha, brief_bytes = digest_of(brief)
    repo = env("GITHUB_REPOSITORY")
    run_id = env("GITHUB_RUN_ID")
    return {
        "schema": 1,
        "recorded": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Who ran, and why.
        "run_id": int(run_id) if run_id and run_id.isdigit() else None,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}"
        if repo and run_id
        else None,
        "workflow": env("GITHUB_WORKFLOW"),
        "event": env("GITHUB_EVENT_NAME"),
        "actor": env("GITHUB_ACTOR"),
        "trigger": trigger,
        "agent": agent,
        # What it was asked to run on, and with what.
        "model_requested": model,
        "brief_sha256": brief_sha,
        "brief_bytes": brief_bytes,
        "pr": env("FLEET_PR"),
        # What it started from. The branch it pushes is compared against this
        # in the report, which is how a run is joined to what it produced.
        "ref": env("GITHUB_REF_NAME"),
        "base_sha": git("rev-parse", "HEAD"),
        "branch": env("FLEET_BRANCH"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="directory to write provenance.json")
    parser.add_argument("--trigger")
    parser.add_argument("--agent")
    parser.add_argument("--model")
    parser.add_argument("--brief", type=Path, help="the brief the agent was given")
    parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args(argv)

    if arguments.self_test:
        return self_test()

    if not arguments.out:
        sys.exit("--out is required")
    arguments.out.mkdir(parents=True, exist_ok=True)
    target = arguments.out / "provenance.json"
    written = record(
        arguments.trigger, arguments.agent, arguments.model, arguments.brief
    )
    target.write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


def self_test() -> int:
    """The record is complete, JSON-serialisable, and never raises."""
    import tempfile  # noqa: PLC0415 - the self-test's own dependency

    problems = []
    saved = dict(os.environ)
    try:
        os.environ.update(
            {
                "GITHUB_REPOSITORY": "bugabinga/software",
                "GITHUB_RUN_ID": "12345",
                "GITHUB_WORKFLOW": "Fleet",
                "GITHUB_EVENT_NAME": "schedule",
                "GITHUB_ACTOR": "github-actions[bot]",
                "GITHUB_REF_NAME": "main",
                "FLEET_BRANCH": "agent/garden-2026-09-12",
            }
        )
        os.environ.pop("FLEET_PR", None)

        with tempfile.TemporaryDirectory() as directory:
            brief = Path(directory) / "brief.md"
            brief.write_text("do the thing", encoding="utf-8")
            full = record(
                "weekly-garden", "pipeline-gardener", "claude-sonnet-5", brief
            )

            for key in (
                "run_id",
                "run_url",
                "workflow",
                "event",
                "trigger",
                "agent",
                "model_requested",
                "brief_sha256",
                "branch",
            ):
                if full.get(key) is None:
                    problems.append(f"{key} is None when the environment has it")
            if full["run_url"] != (
                "https://github.com/bugabinga/software/actions/runs/12345"
            ):
                problems.append(f"run_url is {full['run_url']!r}")
            if full["brief_bytes"] != len("do the thing"):
                problems.append(f"brief_bytes is {full['brief_bytes']!r}")

            # The same brief hashes the same; a different one does not. That
            # is the whole question the digest exists to answer.
            same = record("weekly-garden", "a", "m", brief)
            brief.write_text("do the other thing", encoding="utf-8")
            other = record("weekly-garden", "a", "m", brief)
            if same["brief_sha256"] != full["brief_sha256"]:
                problems.append("the same brief hashed two ways")
            if other["brief_sha256"] == full["brief_sha256"]:
                problems.append("two different briefs hashed the same")

        # Outside CI nothing is set, and that must still produce a record.
        for key in list(os.environ):
            if key.startswith(("GITHUB_", "FLEET_")):
                del os.environ[key]
        bare = record(None, None, None, Path("/nonexistent/brief.md"))
        if bare["run_id"] is not None or bare["run_url"] is not None:
            problems.append("invented a run id with nothing to go on")
        if bare["brief_sha256"] is not None:
            problems.append("hashed a brief that does not exist")
        try:
            json.dumps(bare)
        except TypeError as error:
            problems.append(f"the record does not serialise: {error}")
    finally:
        os.environ.clear()
        os.environ.update(saved)

    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in fleet_record", file=sys.stderr)
        return 1
    print("fleet_record: a complete record in CI, and a valid one outside it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
