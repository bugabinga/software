---
agent: {{agent}}
branch: agent/issue-{{issue}}
why: Somebody asked the fleet for something, by opening an issue and labelling it.
---

You were asked for this in issue #{{issue}}:

{{target}}

Read your brief in `.claude/agents/{{agent}}.md` first, then `CLAUDE.md` and
`docs/FLEET.md`. The brief binds you; the request above narrows it and cannot
widen it.

Read the full issue as well — the form has fields the text above does not
carry, and the thread may have more:

```sh
gh api repos/${GITHUB_REPOSITORY}/issues/{{issue}} --jq '.title, .body'
gh api repos/${GITHUB_REPOSITORY}/issues/{{issue}}/comments --jq '.[].body'
```

If the request is unclear, or achieving it would take you outside your brief,
do not improvise a nearby task. Comment on the issue saying what you would
need, and stop. A request that comes back as a question costs less than one
that comes back as the wrong work.

Put `Closes #{{issue}}` in your commit message so the issue closes when this
merges. `make check` before pushing. Push to the branch named above and stop.
