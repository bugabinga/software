---
agent: pr-reviewer
branch: none
why: A pull request is open. The fleet reviews its own work before it merges.
---

Review pull request #{{pr}} in this repository.

Read `.claude/agents/pr-reviewer.md` — your brief, and it binds you — then
`CLAUDE.md` and `docs/FLEET.md`.

Start with the diff, not the description:

```sh
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}} --jq '.title, .body'
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}}/files --jq '.[].filename'
gh pr diff {{pr}} 2>/dev/null || gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}} -H "Accept: application/vnd.github.v3.diff"
```

Then work out which agent produced it — the branch name and the commit
message say — and hold it to that agent's definition.

The automated gates have already passed on this head. Do not re-run them and
do not report what they cover. You are the check on judgement: brief
adherence, citation accuracy, invention, contradiction, and proportion.

Finish by writing `/tmp/fleet-review.json` and posting your review as a
comment on the pull request. The workflow reads that file and turns it into
the check that gates the merge, so if you do not write it, the review fails.
