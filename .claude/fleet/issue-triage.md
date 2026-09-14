---
agent: notes-cartographer
branch: ""
why: An issue arrived carrying nothing that routes it. Decide what it is.
---

Issue #{{issue}} was opened with no label that routes it. Nothing will happen to
it until one is applied, which is why you are here.

{{target}}

Read it and decide **one** of:

| Route      | When                                                                   |
| ---------- | ---------------------------------------------------------------------- |
| `material` | Source material for the book -- a link, a transcript, a braindump.     |
| `task`     | Work asked of the fleet, on the book or the machinery.                 |
| `close`    | Spam, a duplicate, or a question already answered. Say which.          |
| `human`    | A real request you cannot route without the author deciding something. |

Write `/tmp/triage.json` and nothing else. Do not label, comment or close --
`tools/triage.py` does that, so that a malformed answer becomes `human` rather
than somebody's issue being shut:

```json
{ "route": "task", "why": "asks for the glossary appendix to be drafted" }
```

`why` is one sentence and it is quoted back to the author, so write it for them.
When the route is `task`, add `"agent"` naming which of `.claude/agents/` should
get it.

You are not doing the work. You are deciding where it goes.
