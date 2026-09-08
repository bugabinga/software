---
name: garden
description: Run the book's maintenance sweep - CI health, Typst upgrades, link rot, open pull requests, and whether notes/ has material the book does not account for yet. Use for a scheduled or on-demand pass over the repository, or when asked to "garden", "do the maintenance sweep", or "check on the book".
---

# The maintenance sweep

A pass over `bugabinga/software` that leaves the repository in a better state
or, far more often, confirms it needs nothing and says nothing.

**Silence is the normal outcome.** A sweep that finds nothing does not open a
pull request, does not comment, and does not message the author. Noise from a
gardener is worse than a weed.

## Order of work

Do these in order and stop early if the repository is mid-flight (an open pull
request with red CI is more urgent than anything below it).

1. **Sync.** `git fetch origin main`, work from a branch off `origin/main`.
   Never commit to `main` directly.

2. **Open pull requests.** For each one: is CI green? Is it mergeable? Red or
   conflicted is work now -- fix it. Green chore pull requests (see *Merge
   policy*) get merged. Anything touching `book/chapters/` or `book/book.toml`
   waits for the author, however green.

3. **The gates, locally.** `make check`. If it fails on a clean checkout of
   `main`, that is the most important thing in the repository and everything
   else waits.

4. **Typst.** Compare `.typst-version` against the latest release
   (`gh api repos/typst/typst/releases/latest --jq .tag_name`). If it is
   behind, hand it to the `pipeline-gardener` agent: bump, `make setup`,
   `make check`, and read a built chapter before believing it. The HTML export
   is experimental, so an upgrade that builds is not automatically an upgrade
   that renders.

5. **Link rot.** Outbound links only; internal ones are checked on every
   build. If `lychee` is unavailable locally, read the most recent CI run for
   the `Outbound links` job instead of guessing.

6. **Notes.** Is there anything in `notes/` first seen since the last sweep
   that the book does not account for? If so, hand it to the
   `notes-cartographer` agent. Structure proposals only.

7. **Nothing else.** Do not reformat, reorganise, "improve" the stylesheet, or
   refactor `tools/` because you would have written it differently. The fleet
   earns its autonomy by being boring.

## Merge policy

The author's standing decision: everything arrives as a pull request; green
*chores* may merge themselves.

A chore is a change that touches none of `book/chapters/`, `book/book.toml`,
`book/lib/`, `site/` -- so: dependency and Typst bumps, workflow repairs,
tooling fixes, dead-link repairs outside prose, and `notes/` ingestion.

Merge a chore only when every check on the head commit has concluded
successfully. Squash, keep the pull request title as the commit subject, and
delete the branch afterwards. Repository-level auto-merge is off, so merging
is an explicit step, which means checking the status first rather than
trusting a queue.

Everything else -- prose, structure, styling, anything with a judgement in it
-- stays open for the author, with a body that can be read in two minutes.

## Reporting

Write the sweep's outcome as the pull request body, or as a comment on the
pull request you acted on. Do not open an issue to announce that you looked.
If a sweep finds a problem it cannot fix, open **one** issue naming the
problem, what you tried, and what you would need -- and check for an existing
open issue about it first.
