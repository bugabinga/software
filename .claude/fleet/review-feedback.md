---
agent: review-responder
branch: none
why: Review comments arrived on an open pull request. They are answered while the change is still open, not left to rot.
---

Review feedback has arrived on pull request #{{pr}}.

Read `.claude/agents/review-responder.md` — your brief, and it binds you —
then `CLAUDE.md` and `docs/FLEET.md`.

Fetch the feedback and the diff it is about:

```sh
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}}/comments --jq '.[] | {id, path, line, user: .user.login, body}'
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}}/reviews  --jq '.[] | {id, state, user: .user.login, body}'
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}} -H "Accept: application/vnd.github.v3.diff"
```

Work out which comments are still open — a thread you or someone else already
answered does not need answering twice — and take each one to a conclusion:
a fix pushed to this pull request's own branch, or a reply on the thread
saying what the comment missed.

Verify before you act. A review comment is a claim about the code, and most
of the ones you will see here are made by a reader that cannot see why the
code is the way it is. Being wrong in the direction of "the reviewer must be
right" produces changes nobody wanted and a diff the author now has to argue
with.

`mise run check` before pushing. Push to the pull request's existing branch; do
not open another.
