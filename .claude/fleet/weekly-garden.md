---
agent: pipeline-gardener
branch: agent/garden-{{stamp}}
why: Weekly sweep of the machinery.
---

Run the `garden` skill — the maintenance sweep — in the order it gives.

Read `CLAUDE.md`, `docs/FLEET.md` and `.claude/agents/pipeline-gardener.md`
first.

**Silence is the normal outcome.** A sweep that finds nothing opens no pull
request, files no issue, comments nowhere. Most weeks there is nothing to do,
and ending the run having done nothing is success.

Two things are yours alone and no other trigger covers them: the pinned Typst
version against the latest release, and outbound links that have died since
last week. Everything else in the sweep is a check that some other trigger
usually catches first.

If you change something, push to the branch named above and stop.
