---
agent: review-responder
branch: none
why: Review comments arrived on an open pull request. They are answered while the change is still open, not left to rot.
---

Review feedback has arrived on pull request #{{pr}}.

Read `.claude/agents/review-responder.md` — your brief, and it binds you —
then `CLAUDE.md` and `docs/FLEET.md`.

Fetch the **unresolved threads**, which is the list that matters. Whether a
thread is resolved is not in the REST API, so this is the one place the fleet
uses GraphQL:

```sh
gh api graphql -f query='
  query($owner:String!, $repo:String!, $pr:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$pr) {
        reviewThreads(first:100) {
          nodes {
            id isResolved isOutdated path line
            comments(first:20) { nodes { databaseId author { login } body } }
          }
        }
      }
    }
  }' -F owner="${GITHUB_REPOSITORY%%/*}" -F repo="${GITHUB_REPOSITORY##*/}" \
     -F pr={{pr}} --jq '.data.repository.pullRequest.reviewThreads.nodes[]
                        | select(.isResolved | not)'
```

And the diff they are about:

```sh
gh api repos/${GITHUB_REPOSITORY}/pulls/{{pr}} -H "Accept: application/vnd.github.v3.diff"
```

Take every unresolved thread to a conclusion. There are exactly two:

1. **Fix it.** Change the code on this pull request's own branch. If the
   thread carries a `suggestion` block and you agree with it, apply it — that
   is what it is for.
2. **Answer it.** Reply saying what the finding missed, with the evidence.
   A reviewer that cannot see why the code is the way it is is wrong, and
   saying so is a conclusion.

Then **resolve the thread**, either way. An answered thread that stays open is
indistinguishable from an ignored one, and the repository's rules treat an
unresolved thread as a reason not to merge:

```sh
# Reply on the thread (REST; needs the comment's databaseId, not the thread id)
gh api -X POST "repos/${GITHUB_REPOSITORY}/pulls/{{pr}}/comments/<databaseId>/replies" \
  -f body="what you did, or why you did not"

# Then resolve it (GraphQL; needs the thread id from the query above)
gh api graphql -f query='
  mutation($id:ID!) { resolveReviewThread(input:{threadId:$id}) {
    thread { isResolved } } }' -F id='<thread id>'
```

Resolve only what you actually took to a conclusion. Resolving a thread you
did not address hides a finding, which is worse than leaving it open.

Verify before you act. A review comment is a claim about the code, and most
of the ones you will see here are made by a reader that cannot see why the
code is the way it is. Being wrong in the direction of "the reviewer must be
right" produces changes nobody wanted and a diff the author now has to argue
with.

`mise run check` before pushing. Push to the pull request's existing branch; do
not open another.

Your push runs the reviewer again, which is the loop working rather than a
problem. It stops after three rounds: if the reviewer has already requested
changes three times, this run does not happen at all and the pull request is
labelled `hold` for the author. So the third round is your last chance to
settle it — if a thread is a genuine disagreement rather than a fix you have
not made yet, say so plainly on the thread now rather than pushing again.
