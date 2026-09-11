---
agent: prose-editor
branch: agent/prose-monthly-{{stamp}}
why: Monthly consistency pass over the whole book.
---

Read `.claude/agents/prose-editor.md` — your brief — then `CLAUDE.md` and
`docs/FLEET.md`.

This is the pass the per-change trigger cannot do: it sees the **whole book at
once**, so it is where cross-chapter consistency is actually checkable.
Concentrate on what only a whole-book reading reveals:

- the same concept named two ways in different chapters, or one name used for
  two concepts;
- a term used in an early chapter and defined with `#term` in a later one;
- chapters that have drifted into covering the same ground;
- cross-references that resolve but no longer point at what they claim to.

Ordinary line-level mechanics are secondary here — the per-change trigger
sees those sooner and in smaller pieces.

If the book has fewer than three chapters with real prose in them, there is
nothing a consistency pass can find. Say so and stop.

`make check`, then push to the branch named above and stop.
