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

You need the line numbers, so read the diff with them:

```sh
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}} -H "Accept: application/vnd.github.v3.diff" \
  > /tmp/pr.diff
```

Finish by writing `/tmp/fleet-review.json`. Do not post anything yourself:
the workflow turns that file into a real GitHub review, with your findings as
inline threads on the lines they are about, and into the check that gates the
merge. If you do not write it, the review fails.

Put every finding on a line where you can. A finding with `path` and `line`
becomes a thread the responder has to answer and resolve; one without becomes
a paragraph in the review body that nothing tracks. The line must be one the
diff touches -- added or context, never deleted -- and `tools/post_review.py`
moves anything else into the body rather than misplacing it.

Where you know the fix, write it as `suggestion`: the exact replacement for
the lines you commented on, which the author or the responder applies with one
click. A suggestion you are not sure about is worse than none, because the
click is easier than the thought.
