#!/usr/bin/env python3
"""Judge the fleet: what it ran, what it cost, and what came of it.

The fleet works unattended. Between one look and the next, the only evidence
that it did anything sensible is scattered across workflow runs, branches,
pull requests and issues -- each of which is pruned, closed or force-pushed
on its own schedule. This gathers that into one page while the evidence still
exists, so the question "is the fleet any good" has an answer that is not
somebody's impression.

Three sources, in order of durability:

  1. `history.jsonl`, one line per agent run, carried on the `fleet-log`
     branch. Written by this tool, so it outlives everything below.
  2. The GitHub API: runs, conclusions, timings, branches, pull requests,
     issues. Authoritative, and pruned after 90 days.
  3. Each run's execution record, uploaded as an artifact by the fleet
     workflows. Where the turns, tokens and dollars come from.

A run with no usage record is reported as such rather than dropped: "we do
not know what this cost" is a finding about the pipeline, not a gap to paper
over.

Usage:
    tools/fleet_report.py                     # last 7 days, to stdout
    tools/fleet_report.py --days 30
    tools/fleet_report.py --html build/fleet.html
    tools/fleet_report.py --history fleet-log/history.jsonl --append
    tools/fleet_report.py --json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import statistics
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
BRIEFS = ROOT / ".claude" / "fleet"

# The workflows that are the fleet, as opposed to the ones that build the
# book. `Agent branches` is included because it is where an agent's branch
# either becomes a merge or becomes an issue, which is the outcome worth
# knowing.
AGENT_WORKFLOWS = {"Fleet", "Fleet review", "Fleet respond"}
PLUMBING_WORKFLOWS = {"Agent branches", "Maintenance"}

# Tracking issues that `agent-branches.yml` opens for branches it will not
# merge by itself. They are noise once the branch is gone, and counting them
# is how that shows up.
TRACKING_PREFIXES = ("Ready to review: ", "Green and unmerged: ")


def gh(*args: str) -> str:
    """Run `gh` and return stdout, or "" when the call fails.

    Failure is normal here: this runs both in CI, where the token can read
    everything, and in a session behind a proxy that refuses whole API paths.
    A report missing one section is worth more than a traceback.
    """
    binary = shutil.which("gh") or str(ROOT / ".tools" / "gh" / "gh")
    try:
        done = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"warning: gh {' '.join(args)}: {error}", file=sys.stderr)
        return ""
    if done.returncode != 0:
        message = done.stderr.strip().splitlines()[-1:] or [""]
        print(f"warning: gh {' '.join(args)}: {message[0]}", file=sys.stderr)
        return ""
    return done.stdout


def api(path: str, *jq: str) -> object:
    args = ["api", path]
    for expression in jq:
        args += ["--jq", expression]
    out = gh(*args).strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return [json.loads(line) for line in out.splitlines() if line.strip()]


def repository() -> str:
    if slug := os.environ.get("GITHUB_REPOSITORY"):
        return slug
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout.strip()
    return remote.removesuffix(".git").split("github.com")[-1].lstrip(":/")


# --------------------------------------------------------------------------- #
# Gathering
# --------------------------------------------------------------------------- #


def since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect_runs(repo: str, days: int) -> list[dict]:
    """Every workflow run in the window, flattened to what the report needs."""
    cutoff = since(days)
    stamp = cutoff.strftime("%Y-%m-%d")
    raw = api(f"repos/{repo}/actions/runs?per_page=100&created=%3E%3D{stamp}") or {}
    runs = []
    for run in (raw or {}).get("workflow_runs", []):
        started = parse_time(run.get("run_started_at") or run.get("created_at"))
        if not started or started < cutoff:
            continue
        finished = parse_time(run.get("updated_at"))
        runs.append(
            {
                "id": run["id"],
                "workflow": run.get("name", "?"),
                "event": run.get("event", "?"),
                "branch": run.get("head_branch") or "",
                "actor": (run.get("triggering_actor") or {}).get("login", "?"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "started": started.isoformat(),
                "seconds": (
                    round((finished - started).total_seconds())
                    if finished and started
                    else None
                ),
                "url": run.get("html_url", ""),
            }
        )
    return runs


def usage_for(repo: str, run_id: int, cache: Path | None) -> dict | None:
    """The turns, tokens and cost of one agent run.

    The fleet workflows upload the CLI's execution record as an artifact named
    `fleet-run-<id>`. Returns None when there is none, which is the answer for
    every run made before that step existed.
    """
    listing = api(
        f"repos/{repo}/actions/runs/{run_id}/artifacts",
        '[.artifacts[] | select(.name | startswith("fleet-run")) | '
        "{id, expired}] | first",
    )
    if not listing or listing.get("expired"):
        return None

    target = (cache or Path("/tmp")) / f"fleet-run-{run_id}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    blob = gh(
        "api",
        f"repos/{repo}/actions/artifacts/{listing['id']}/zip",
        "--method",
        "GET",
    )
    if not blob:
        return None
    target.write_bytes(blob.encode("latin-1", errors="ignore"))
    try:
        with zipfile.ZipFile(target) as bundle:
            name = next(
                (n for n in bundle.namelist() if n.endswith(".json")), None
            )
            if not name:
                return None
            payload = json.loads(bundle.read(name))
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
        return None
    finally:
        target.unlink(missing_ok=True)

    return summarise_execution(payload)


def summarise_execution(payload: object) -> dict | None:
    """Pull the result record out of the CLI's execution output.

    The file is a list of streamed messages; the last one of type `result`
    carries the totals. Written defensively: this is somebody else's output
    format and it is not promised to stay put.
    """
    messages = payload if isinstance(payload, list) else [payload]
    result = None
    for message in messages:
        if isinstance(message, dict) and message.get("type") == "result":
            result = message
    if not result:
        return None
    usage = result.get("usage") or {}
    return {
        "turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
        "seconds": (
            round(result["duration_ms"] / 1000)
            if isinstance(result.get("duration_ms"), (int, float))
            else None
        ),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read": usage.get("cache_read_input_tokens"),
        "cache_write": usage.get("cache_creation_input_tokens"),
        "error": bool(result.get("is_error")),
        "subtype": result.get("subtype"),
    }


def collect_branches(repo: str) -> list[dict]:
    """Every `agent/**` branch and what became of it."""
    names = api(f"repos/{repo}/branches?per_page=100", "[.[].name]") or []
    out = []
    for name in names:
        if not name.startswith("agent/"):
            continue
        pulls = (
            api(
                f"repos/{repo}/pulls?head={repo.split('/')[0]}:{name}&state=all",
                "[.[] | {number, state, merged_at}]",
            )
            or []
        )
        merged = [p for p in pulls if p.get("merged_at")]
        openish = [p for p in pulls if p.get("state") == "open"]
        out.append(
            {
                "branch": name,
                "pull": (openish or merged or [{}])[0].get("number"),
                "fate": (
                    "merged" if merged else "open" if openish else "stranded"
                ),
            }
        )
    return out


def collect_issues(repo: str) -> dict:
    issues = (
        api(
            f"repos/{repo}/issues?state=open&per_page=100",
            "[.[] | select(.pull_request == null) | "
            "{number, title, labels: [.labels[].name], created_at}]",
        )
        or []
    )
    tracking = [
        issue
        for issue in issues
        if issue["title"].startswith(TRACKING_PREFIXES)
    ]
    return {
        "open": len(issues),
        "tracking": tracking,
        "work": [issue for issue in issues if issue not in tracking],
    }


def fleet_context() -> dict:
    """What the fleet currently is, as opposed to what it did."""

    def described(directory: Path) -> list[dict]:
        entries = []
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            description = ""
            for line in text.splitlines():
                if line.startswith("description:"):
                    description = line.split(":", 1)[1].strip().strip("\"'")
                    break
            entries.append(
                {
                    "name": path.stem,
                    "description": description,
                    "lines": len(text.splitlines()),
                }
            )
        return entries

    return {
        "agents": described(AGENTS) if AGENTS.is_dir() else [],
        "briefs": described(BRIEFS) if BRIEFS.is_dir() else [],
    }


# --------------------------------------------------------------------------- #
# Judging
# --------------------------------------------------------------------------- #


def agent_of(run: dict) -> str:
    """Which agent a run stands for, from the workflow that ran it."""
    return {
        "Fleet review": "pr-reviewer",
        "Fleet respond": "review-responder",
    }.get(run["workflow"], "dispatched")


def judge(runs: list[dict], usage: dict[int, dict]) -> dict:
    agent_runs = [r for r in runs if r["workflow"] in AGENT_WORKFLOWS]
    plumbing = [r for r in runs if r["workflow"] in PLUMBING_WORKFLOWS]

    by_agent: dict[str, list[dict]] = defaultdict(list)
    for run in agent_runs:
        by_agent[agent_of(run)].append(run)

    def tally(group: list[dict]) -> dict:
        done = [r for r in group if r["conclusion"]]
        good = [r for r in done if r["conclusion"] == "success"]
        seconds = [r["seconds"] for r in done if r["seconds"] is not None]
        costs = [
            usage[r["id"]]["cost_usd"]
            for r in group
            if r["id"] in usage and usage[r["id"]].get("cost_usd") is not None
        ]
        turns = [
            usage[r["id"]]["turns"]
            for r in group
            if r["id"] in usage and usage[r["id"]].get("turns") is not None
        ]
        tokens = sum(
            (usage[r["id"]].get("input_tokens") or 0)
            + (usage[r["id"]].get("output_tokens") or 0)
            for r in group
            if r["id"] in usage
        )
        return {
            "runs": len(group),
            "finished": len(done),
            "succeeded": len(good),
            "failed": len(done) - len(good),
            "median_seconds": round(statistics.median(seconds)) if seconds else None,
            "cost_usd": round(sum(costs), 4) if costs else None,
            "median_turns": round(statistics.median(turns)) if turns else None,
            "tokens": tokens or None,
            "measured": sum(1 for r in group if r["id"] in usage),
        }

    return {
        "overall": tally(agent_runs),
        "by_agent": {name: tally(group) for name, group in sorted(by_agent.items())},
        "plumbing": tally(plumbing),
        "failures": [
            r
            for r in agent_runs + plumbing
            if r["conclusion"] not in (None, "success", "skipped")
        ],
    }


def findings(report: dict) -> list[str]:
    """The sentences worth reading if nothing else is.

    Deliberately few and deliberately blunt. A weekly report nobody reads is
    the same as no report, and the way to be read is to be short and to say
    something.
    """
    out = []
    overall = report["judgement"]["overall"]
    branches = report["branches"]
    issues = report["issues"]

    if overall["runs"] == 0:
        out.append("The fleet did not run at all this week.")
    elif overall["failed"]:
        out.append(
            f"{overall['failed']} of {overall['finished']} agent runs failed."
        )

    if overall["runs"] and not overall["measured"]:
        out.append(
            "No run recorded its usage, so nothing here says what the fleet "
            "cost. The workflows upload that record; if this persists, the "
            "step is broken."
        )

    stranded = [b for b in branches if b["fate"] == "stranded"]
    if stranded:
        out.append(
            f"{len(stranded)} agent branch(es) have no pull request and are "
            f"not merged: {', '.join(b['branch'] for b in stranded[:5])}"
            + (" …" if len(stranded) > 5 else "")
            + ". Work the fleet did that nothing will ever land."
        )

    if len(issues["tracking"]) >= 5:
        out.append(
            f"{len(issues['tracking'])} tracking issues are open. They are "
            "opened by the branch workflow and closed by nothing, so the "
            "issue list stops being readable."
        )

    if not out:
        out.append("Nothing to report: the fleet ran, and nothing is stuck.")
    return out


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def number(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


def seconds(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value}s" if value < 90 else f"{value // 60}m {value % 60}s"


def as_text(report: dict) -> str:
    lines = [
        f"Fleet report — {report['window_days']} days to "
        f"{report['generated'][:10]}",
        "",
    ]
    for finding in report["findings"]:
        lines.append(f"  * {finding}")
    lines.append("")

    overall = report["judgement"]["overall"]
    lines.append(
        f"  agent runs {overall['runs']}"
        f"  ok {overall['succeeded']}"
        f"  failed {overall['failed']}"
        f"  median {seconds(overall['median_seconds'])}"
        f"  cost {money(overall['cost_usd'])}"
    )
    for name, tally in report["judgement"]["by_agent"].items():
        lines.append(
            f"    {name:<18} {tally['runs']:>3} runs"
            f"  {tally['failed']:>2} failed"
            f"  {seconds(tally['median_seconds']):>8}"
            f"  {money(tally['cost_usd']):>9}"
        )
    lines.append("")
    fates = defaultdict(int)
    for branch in report["branches"]:
        fates[branch["fate"]] += 1
    lines.append(
        "  branches  "
        + "  ".join(f"{fate} {count}" for fate, count in sorted(fates.items()))
    )
    lines.append(
        f"  issues    {report['issues']['open']} open"
        f"  ({len(report['issues']['tracking'])} tracking)"
    )
    return "\n".join(lines) + "\n"


def as_html(report: dict) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    rows = []
    for name, tally in report["judgement"]["by_agent"].items():
        rows.append(
            "<tr>"
            f"<td>{esc(name)}</td>"
            f"<td class=n>{tally['runs']}</td>"
            f"<td class=n>{tally['failed']}</td>"
            f"<td class=n>{esc(seconds(tally['median_seconds']))}</td>"
            f"<td class=n>{esc(tally['median_turns'] or '—')}</td>"
            f"<td class=n>{esc(number(tally['tokens']))}</td>"
            f"<td class=n>{esc(money(tally['cost_usd']))}</td>"
            "</tr>"
        )

    branch_rows = "".join(
        f"<tr><td><code>{esc(b['branch'])}</code></td>"
        f"<td>{esc(b['fate'])}</td>"
        f"<td class=n>{esc(b['pull'] and '#' + str(b['pull']) or '—')}</td></tr>"
        for b in report["branches"]
    )

    failure_rows = "".join(
        f"<tr><td><a href=\"{esc(f['url'])}\">{esc(f['workflow'])}</a></td>"
        f"<td>{esc(f['branch'] or '—')}</td>"
        f"<td>{esc(f['conclusion'])}</td>"
        f"<td class=n>{esc(f['started'][:16].replace('T', ' '))}</td></tr>"
        for f in report["judgement"]["failures"][:20]
    ) or "<tr><td colspan=4>None.</td></tr>"

    context = report["context"]
    fleet_rows = "".join(
        f"<tr><td><code>{esc(a['name'])}</code></td>"
        f"<td>{esc(a['description'])}</td></tr>"
        for a in context["agents"]
    )

    findings_html = "".join(f"<li>{esc(f)}</li>" for f in report["findings"])

    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Fleet report — {esc(report['generated'][:10])}</title>
<style>
  :root {{ color-scheme: light dark; --line: color-mix(in srgb, currentColor 18%, transparent); }}
  body {{ font: 15px/1.55 ui-monospace, "DejaVu Sans Mono", monospace;
         max-width: 62rem; margin: 0 auto; padding: 2rem 1rem 6rem; }}
  h1 {{ font-size: 1.3rem; margin: 0 0 .2rem; }}
  h2 {{ font-size: 1rem; margin: 2.4rem 0 .6rem; text-transform: uppercase;
        letter-spacing: .08em; opacity: .65; }}
  p.sub {{ margin: 0 0 2rem; opacity: .6; }}
  ul.findings {{ padding-left: 1.1rem; margin: 0 0 1rem; }}
  ul.findings li {{ margin: .35rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0 0 1rem; }}
  th, td {{ text-align: left; padding: .3rem .6rem .3rem 0;
            border-bottom: 1px solid var(--line); vertical-align: top; }}
  th {{ font-weight: 600; opacity: .6; font-size: .82rem; }}
  td.n, th.n {{ text-align: right; font-variant-numeric: tabular-nums;
                padding-right: 0; }}
  code {{ font-size: .92em; }}
  a {{ color: inherit; }}
  .wrap {{ overflow-x: auto; }}
</style>

<h1>Fleet report</h1>
<p class="sub">{esc(report['window_days'])} days to {esc(report['generated'][:16].replace('T', ' '))} UTC ·
  <a href="../">the book</a></p>

<ul class="findings">{findings_html}</ul>

<h2>Agents</h2>
<div class="wrap"><table>
  <tr><th>agent</th><th class=n>runs</th><th class=n>failed</th>
      <th class=n>median</th><th class=n>turns</th><th class=n>tokens</th>
      <th class=n>cost</th></tr>
  {''.join(rows) or '<tr><td colspan=7>No agent runs in this window.</td></tr>'}
</table></div>

<h2>Failures</h2>
<div class="wrap"><table>
  <tr><th>workflow</th><th>branch</th><th>conclusion</th><th class=n>when</th></tr>
  {failure_rows}
</table></div>

<h2>Branches</h2>
<div class="wrap"><table>
  <tr><th>branch</th><th>fate</th><th class=n>pr</th></tr>
  {branch_rows or '<tr><td colspan=3>None.</td></tr>'}
</table></div>

<h2>Roster</h2>
<div class="wrap"><table>
  <tr><th>agent</th><th>brief</th></tr>
  {fleet_rows}
</table></div>
<p class="sub">{esc(len(context['briefs']))} occasions routed by
  <code>tools/fleet_brief.py</code>.
  Generated by <code>tools/fleet_report.py</code>; not part of the book.</p>
</html>
"""


# --------------------------------------------------------------------------- #


def build_report(days: int, cache: Path | None) -> dict:
    repo = repository()
    runs = collect_runs(repo, days)
    usage = {}
    for run in runs:
        if run["workflow"] not in AGENT_WORKFLOWS or not run["conclusion"]:
            continue
        if found := usage_for(repo, run["id"], cache):
            usage[run["id"]] = found

    report = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": repo,
        "window_days": days,
        "runs": runs,
        "usage": usage,
        "branches": collect_branches(repo),
        "issues": collect_issues(repo),
        "context": fleet_context(),
    }
    report["judgement"] = judge(runs, usage)
    report["findings"] = findings(report)
    return report


def append_history(report: dict, path: Path) -> None:
    """One line per report, so trends outlive the API's 90-day window."""
    overall = report["judgement"]["overall"]
    line = {
        "generated": report["generated"],
        "window_days": report["window_days"],
        "runs": overall["runs"],
        "succeeded": overall["succeeded"],
        "failed": overall["failed"],
        "cost_usd": overall["cost_usd"],
        "tokens": overall["tokens"],
        "branches": {
            fate: sum(1 for b in report["branches"] if b["fate"] == fate)
            for fate in ("merged", "open", "stranded")
        },
        "open_issues": report["issues"]["open"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--html", type=Path, help="write the page here")
    parser.add_argument("--history", type=Path, help="JSONL to append a line to")
    parser.add_argument("--json", action="store_true", help="dump everything")
    parser.add_argument(
        "--cache", type=Path, default=ROOT / "build" / "fleet-artifacts"
    )
    arguments = parser.parse_args()

    report = build_report(arguments.days, arguments.cache)

    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(as_text(report), end="")

    if arguments.html:
        arguments.html.parent.mkdir(parents=True, exist_ok=True)
        arguments.html.write_text(as_html(report), encoding="utf-8")
        print(f"wrote {arguments.html}", file=sys.stderr)

    if arguments.history:
        append_history(report, arguments.history)

    return 0


if __name__ == "__main__":
    sys.exit(main())
