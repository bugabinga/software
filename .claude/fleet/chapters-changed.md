---
agent: prose-editor
branch: agent/prose-{{stamp}}
why: Chapters changed on main. Review them while the change is fresh, rather than waiting for the monthly pass.
---

These chapters changed on `main`:

{{changed}}

Read `.claude/agents/prose-editor.md` — your brief — then `CLAUDE.md` and
`docs/FLEET.md`.

Review **only those chapters**, plus anything elsewhere in the book they
break: a reworded heading changes its id, so cross-references into it from
other chapters go stale silently. That check is the main reason this trigger
exists.

Scope discipline matters more here than in the monthly pass. This fires on
every change, so a review that touches the whole book every time is noise the
author will learn to ignore. If the change is sound, say so and stop.

`mise run check` before pushing. Push to the branch named above and stop; the
pull request is opened for you, and because this touches `book/chapters/` it
will be left for the author.
