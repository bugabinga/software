# The notes inbox

How material reaches the book from the author's note-taking session, without
that session holding anything it could damage the book with.

```
note-taker  ──POST /note──▶  notes-intake Worker  ──▶  GitHub: a branch
(one bearer token)            (holds the GitHub token)        │
                                                              ▼
                                    notes-reindex.yml rebuilds notes/index.md
                                                              │
                                                              ▼
                                    agent-branches.yml opens the pull request
                                                              │
                                              merge to main ──▶ fleet.yml
                                                              │
                                                              ▼
                                              notes-cartographer reads it
```

## Why a Worker

The note-taker is a separate Claude session whose only job is to hand over
text. Every route that skips the Worker gives it a GitHub credential instead:
`repository_dispatch` and the Contents API both need `contents: write`, which
is enough to rewrite the book.

A GitHub token cannot be scoped to "may only file a note". A Worker can. The
note-taker holds a bearer token that reaches one endpoint; the GitHub
credential lives in Cloudflare and never leaves it. That is the same principle
as the GitHub App in `docs/IDENTITY.md` — _able to do the job and nothing
else_ — applied to a session nobody is supervising.

Three layers of containment, none of which trusts the caller:

1. The bearer token is compared as digests, in constant time, and a wrong one
   is answered exactly like a missing one.
2. The Worker writes only under `notes/`, and builds the path itself from a
   slug of the title. A `path` field in the request is ignored; a `../` in the
   title is slugified away. Both are covered by the tests.
3. It writes only to a fresh branch. `main` is protected by a ruleset, so even
   the credential could not push there.

## Notes stay in the repository

Cloudflare is the inbox, not the archive. `notes/` is never edited — a rule
git enforces for free, with history and diffs that no object store has. Every
agent already has the notes in its checkout, with no credential and no network
call. And the book is public: the material it is built from being readable is
part of that.

The Worker's job ends the moment the note is a commit.

## Using it

```http
POST https://notes-intake.<subdomain>.workers.dev/note
Authorization: Bearer <the intake token>
Content-Type: application/json

{
  "title": "Session 02 — what a machine is",
  "body": "# Heading\n\nThe note, in Markdown, verbatim.\n",
  "source": "claude content session 02, exported 2026-09-20"
}
```

`title` and `body` are required; `source` is free text recorded in the note's
frontmatter. The body is stored exactly as sent — this is the author thinking,
and nothing rewrites it.

**Replies.** `201` with the path and branch when the note is filed. `200` with
`"created": false` when that exact note is already on a branch, so a retry
after a timeout is safe and files nothing twice. `401` for a bad token, `400`
for a malformed note, `413` over 512 KB, `502` when GitHub refused.

`GET /` answers `{"service":"notes-intake","ok":true}` and needs no token,
which is how to check the URL is right before wiring anything to it.

## Getting the skill into the note-taker

The note-taker is told all of this by a skill: `file-note`, one `SKILL.md` in
a zip. Two ways to get one, and they are the same generator --
`site/skill/index.html` builds the zip in the browser, and
`tools/make_skill.py` runs that same script under node so the deploy can build
it too. A second implementation would drift, and the drift would show up as a
note-taking session behaving oddly rather than as a failing test.

- **From the deploy.** `worker-deploy.yml` attaches `file-note-skill` to its
  run, with the address and the token already in it, retained for a day. The
  token is one you already gave the repository, so nothing is typed.
- **From the page.** `<site>/skill/`, for a rotation or a second note-taker.
  The deploy's summary links to it with `?inbox=` filled in; the token is
  typed there, because the page is a static file on Pages and anything
  prefilled into it is published.

The zip holds a live token. That is proportionate here: the notes are not
secret, and the worst a leaked intake token buys is junk notes, which arrive
as pull requests a human merges. Rotating it means changing
`NOTES_INTAKE_TOKEN` and taking the next deploy's artifact.

## The credentials

| Secret                  | Where                                              | What it is                                                                      |
| ----------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------- |
| `NOTES_INTAKE_TOKEN`    | repository secret, and a Worker secret set from it | what the note-taker sends. Any long random string.                              |
| `NOTES_GITHUB_TOKEN`    | repository secret, and a Worker secret set from it | a **fine-grained** PAT: this repository only, **Contents: write**, nothing else |
| `CLOUDFLARE_API_TOKEN`  | `Cloudflare` environment, `main` only              | deploys the Worker                                                              |
| `CLOUDFLARE_ACCOUNT_ID` | `Cloudflare` environment                           | which account                                                                   |

`worker-deploy.yml` sets the two Worker secrets from the repository secrets on
every deploy, so what is in GitHub is what is in Cloudflare rather than
something set by hand once and forgotten.

The PAT is deliberately _not_ the GitHub App. The App holds eight write
permissions; the inbox needs one. A narrower credential in a second place
beats copying the App's key into Cloudflare, where a compromise of that
account would hand over something that can merge to `main`.

## The Cloudflare account

A **separate account from the author's other projects**, because Cloudflare
API tokens have no per-Worker scoping: `Workers Scripts Write` is account-wide,
so a token that can deploy this Worker can overwrite every Worker on the same
account. Accounts are free and switch from the same login, so the fix for "I
cannot scope this token" is to give it an account where account-wide is narrow.

Token permissions, and nothing else:

- **Workers Scripts Write** — deploy, and set the Worker's secrets
- **Workers Tail Read** — read the log when a delivery fails
- **Workers AI Read**, **Vectorize Read/Write** — only when the index below is
  built; not needed for the inbox

No zone permissions: there is no domain, and `*.workers.dev` is free.

## Testing it

`node worker/notes-intake/test.mjs`, which `mise run check` and CI both run. The
Worker uses only web-standard APIs, so the whole of its behaviour is testable
with plain node — no wrangler, no Cloudflare, no credential. Twenty-two cases,
including the ones that matter: a wrong token, a traversal in the title, a
`path` field in the request, and a retry.

## Not built yet: the index

A Vectorize index over `notes/` and the chapters would let the cartographer
ask "what already covers this?" instead of grepping. It is free at this scale
— 5M stored dimensions is thousands of chunks — and it needs Workers AI for
the embeddings.

It is deliberately second. A broken inbox blocks the workflow the author
wants; a missing index blocks nothing, and with a handful of notes an agent
reading them all is still cheaper than maintaining an index. Build it when the
corpus makes grep useless, not before.
