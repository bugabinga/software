---
agent: {{agent}}
branch: agent/{{agent}}-{{stamp}}
why: Dispatched by hand, with a target.
---

Dispatched deliberately, against this target:

{{target}}

Read your brief in `.claude/agents/{{agent}}.md` first, then `CLAUDE.md` and
`docs/FLEET.md`. The brief binds you; this dispatch narrows it, and cannot
widen it.

If the target is unclear, or achieving it would take you outside your brief,
do not improvise a nearby task. Say what you would need and stop — a dispatch
that comes back with a question costs less than one that comes back with the
wrong work.

`make check` before pushing. Push to the branch named above and stop.
