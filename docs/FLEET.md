# The fleet

Who maintains this book besides the author, what each of them may touch, and
how to stop them.

Three kinds of worker, in increasing order of how much judgement they exercise
and decreasing order of how often they run.

## 1. Workflows (no judgement, no agent)

Deterministic work that a script does better than a model.

| Workflow | When | What |
| --- | --- | --- |
| `ci.yml` | every pull request and push to `main` | build, internal links, spelling, outbound links, example code; attaches the built site to the run and comments a preview link |
| `publish.yml` | pushes to `main` | enables Pages if needed, builds with the deployment URL, deploys |
| `release.yml` | `v*` tags | attaches the PDF and a zip of the site to a release |
| `agent-branches.yml` | pushes to `agent/**` and `maintenance/**`, and CI completing | opens the pull request for a branch the fleet pushed, and merges it when it is a chore and every check on its head commit is green |
| `maintenance.yml` | Mondays 06:17 UTC | compares `.typst-version` against the latest Typst release and opens an upgrade pull request *if the book still builds and passes every gate on it*; re-runs the outbound link check and files one standing issue for dead links |

## 2. Agents (judgement, on a schedule or on demand)

Defined in `.claude/agents/`, so a scheduled session, an interactive session
and the GitHub-side bot all run the same agent rather than improvising.

| Agent | Beat | Never |
| --- | --- | --- |
| `pipeline-gardener` | Typst upgrades, CI failures, link rot, the tooling | edits prose; touches `notes/` |
| `notes-cartographer` | reads `notes/`, proposes outline changes and chapter stubs | writes chapter prose; edits `notes/` |
| `prose-editor` | copyediting, terminology drift, terms used before defined, stale cross-references | rewrites for style; changes what a paragraph claims |
| `chapter-drafter` | drafts a chapter from notes, against a named target | runs on a schedule; invents citations or uncompiled listings |

Two skills carry the procedures: `.claude/skills/garden` (the maintenance
sweep, including the merge policy) and `.claude/skills/ingest` (getting
material into `notes/`).

### Schedules

| Routine | When | What it does |
| --- | --- | --- |
| Daily sweep | 07:00 UTC | runs the `garden` skill: open pull requests first, then the gates, Typst, link rot, and whether `notes/` holds anything the book does not account for |
| Monthly prose pass | 1st, 08:00 UTC | `prose-editor` over the chapters touched in the last five weeks |

Each fires a fresh session, which reads `CLAUDE.md` and this file before doing
anything. **Silence is the normal outcome of a sweep**: no pull request, no
issue, no message. A gardener that reports every walk around the garden is
worse than no gardener.

## 3. The bot inside GitHub (on request)

`claude.yml` picks up `@claude` in an issue, a pull-request comment or a
review comment, with the repository checked out and the book's gates
available. Use it for "@claude this link is dead" or "@claude why is this
build red" without leaving GitHub.

It needs an `ANTHROPIC_API_KEY` repository secret, which cannot be set from
the author's Claude sessions — the Actions secrets API is blocked to that
environment. Until the key exists, every run exits early with a notice rather
than failing. Everything in sections 1 and 2 works without it.

## What still needs a human, and how little

Two things, both one-time or occasional, neither of them a click if you would
rather not:

**Enable Pages, once.** Creating the Pages site needs administration rights
that the workflow token does not have, and the Pages API is not reachable
from the author's Claude sessions. One command from anywhere holding a token
for this repository:

```sh
gh api -X POST repos/bugabinga/software/pages -f build_type=workflow
```

Until then `publish.yml` fails on its first step with that command in the job
summary. Afterwards every push to `main` publishes by itself.

**Arm the GitHub bot, if you want it** (see section 3): add an
`ANTHROPIC_API_KEY` secret. Nothing else depends on it.

Dependabot's pull requests also wait for a human. The actions here are pinned
to major versions, so every bump Dependabot opens is a major-version bump --
exactly the kind that changes behaviour and deserves a reading. They show up
in the daily sweep's report rather than being merged by it.

## The merge policy

The author's standing decision: **everything arrives as a pull request, and
green chores may merge themselves.**

A *chore* touches none of `book/chapters/`, `book/book.toml`, `book/lib/`,
`site/`, `.github/`, `.claude/`. So: Typst and dependency bumps, tooling
fixes, dead links outside prose, `notes/` ingestion.

`.github/` and `.claude/` are on that list on purpose. A change to the
workflows or to the fleet's own definitions is the automation deciding its
own future, and that is never merged without a human reading it — however
green it is.

Anything else — prose, structure, styling, anything with a judgement in it —
stays open for the author. Green is not permission.

### How it is actually enforced

Not by trust, and not by repository auto-merge. Agents **push a branch and
stop**; `agent-branches.yml` opens the pull request and decides about
merging, using the rules above, the files the pull request actually touches,
and the state of every check on its head commit.

That inversion exists because an unattended session may not be able to call
the pull-request API at all: GraphQL is restricted in that environment, so
`gh pr` does not work, and mutating REST calls can be refused — while
`git push` always works. It also means the merge rules live in the repository
where they can be read and changed, rather than in whatever an agent decided
at 07:00.

Label a pull request `hold` to stop it merging automatically, whatever it
touches.

## Boundaries that hold for every worker

- `main` is never committed to directly. Everything is a branch and a pull
  request.
- `notes/` is never edited. It is the record of where the material came from;
  corrections happen in the book.
- No gate is ever skipped, loosened, or excluded to turn red into green. If a
  gate is wrong, that is a deliberate change in its own commit, with the
  reasoning in the body.
- No test, check or warning is silenced to make a run pass.
- A worker that cannot finish says so — once, in one place — rather than
  half-finishing quietly.

## Stopping the fleet

```sh
# List the scheduled sessions and turn one off, or delete it
#   (from a Claude Code session: list_triggers / update_trigger / delete_trigger)

# Disable a workflow without deleting it
gh workflow disable maintenance.yml
gh workflow disable claude.yml

# Or pull the plug on the agent side entirely
git rm -r .claude/agents .claude/skills
```

Disabling `ci.yml` or `publish.yml` stops the book being checked and
published, which is a different decision from stopping the fleet.
