---
agent: notes-cartographer
branch: agent/notes-issue-{{issue}}
why: Material arrived as an issue. Save it verbatim, then work out what it means for the book.
---

New material for the book arrived as issue #{{issue}}.

Read `.claude/agents/notes-cartographer.md` — your brief — then `CLAUDE.md`
and `docs/FLEET.md`.

**First, save it, exactly as written.** Fetch the issue body and put it into
`notes/` through the tool, which keeps a verbatim copy and records where it
came from:

```sh
gh api repos/${GITHUB_REPOSITORY}/issues/{{issue}} --jq .body > /tmp/material.md
tools/ingest_notes.py --from-file /tmp/material.md \
  --title "<a short name for this material>" \
  --source "github issue #{{issue}}"
```

Do not correct, tidy, reorder or summarise it on the way in. It is a
braindump and its value is that it is the record of a thought, not a cleaned
version of one. The issue form says as much to the person writing it.

**Then do your own job**: read it critically against the notes already there
and against the chapters as they stand, and change the book's shape if it
needs changing. It may need nothing — say so and stop.

Put `Closes #{{issue}}` in your commit message, so the issue closes when this
merges.

Push to the branch named above and stop.
