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
| `publish.yml` | pushes to `main` | builds, then force-pushes the site to the `gh-pages` branch as a single orphan commit |
| `release.yml` | `v*` tags | attaches the PDF and a zip of the site to a release |
| `agent-branches.yml` | pushes to `agent/**` and `maintenance/**`, and CI completing | opens a pull request for a branch the fleet pushed where the repository permits it, and then merges green chores or reports everything else |
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

### Triggers

The fleet runs in CI, through `fleet.yml`. An agent runs on the **occasion**
that calls for it, and gets a brief written for that occasion rather than one
generic instruction:

| Trigger | Fires on | Agent | What the brief adds |
| --- | --- | --- | --- |
| `notes-arrived` | a push to `main` touching `notes/**` | `notes-cartographer` | names what just landed; asks for tensions to be surfaced now, while the author is still close to the material |
| `chapters-changed` | a push to `main` touching `book/chapters/**` | `prose-editor` | scopes the review to those chapters and to the cross-references a reworded heading silently breaks |
| `weekly-garden` | Mondays 07:00 UTC | `pipeline-gardener` | the two things only it covers: the Typst pin against the latest release, and links that died this week |
| `monthly-prose` | 1st, 08:00 UTC | `prose-editor` | the whole book at once -- terminology drift, terms used before defined, chapters that have drifted together |
| `on-demand` | `workflow_dispatch`, with an agent and a target | any | the dispatch narrows the agent's brief and may not widen it |

The briefs live in `.claude/fleet/*.md`, not in the workflow, so changing what
an agent is told on a given occasion is a readable diff. `tools/fleet_brief.py`
routes the occasion to a brief and fills it in; `make check` runs its
self-test, because a broken brief is a fleet outage that would otherwise only
show itself at 07:00 on a Monday.

**Event beats cadence.** Waiting a week to notice that notes arrived is a
worse fleet than one that notices on the push. The two schedules that remain
are the ones with no event to hang on: link rot happens to the world, not to
the repository, and whole-book consistency is only checkable periodically.

**Silence is the normal outcome.** No pull request, no issue, no message. An
agent that reports every walk around the garden is worse than no agent.

`fleet.yml` needs an `ANTHROPIC_API_KEY` secret to actually run an agent.
Without it, every trigger still fires, routes, and prints the brief it would
have used into the job summary -- so the triggers can be watched working
before any money is spent on them.

#### Interim: the scheduled sessions

Until that key exists, two Routines fire fresh Claude sessions instead: a
daily sweep at 07:00 UTC and a monthly prose pass on the 1st. They do the same
work less legibly, and **they are to be deleted the moment the key lands**, or
the weekly and monthly work will run twice.

## 3. The bot inside GitHub (on request)

`claude.yml` picks up `@claude` in an issue, a pull-request comment or a
review comment, with the repository checked out and the book's gates
available. Use it for "@claude this link is dead" or "@claude why is this
build red" without leaving GitHub.

It needs an `ANTHROPIC_API_KEY` repository secret, which cannot be set from
the author's Claude sessions — the Actions secrets API is blocked to that
environment. Until the key exists, every run exits early with a notice rather
than failing. Everything in sections 1 and 2 works without it.

## Nothing here needs setting up

Everything runs on the workflow token, which every repository grants its own
Actions by default. That is a design constraint, not an accident: three
things a normal pipeline would reach for are unavailable here, and each was
routed around rather than left as a chore for the author.

| Wanted | Refused because | Done instead |
| --- | --- | --- |
| Pages built from Actions | creating the Pages site is privileged; the workflow token gets "Resource not accessible by integration", and the Pages API is unreachable from Claude sessions | `publish.yml` pushes the built site to `gh-pages`, which needs only `contents: write` and which GitHub serves without configuration |
| Workflows opening pull requests | off by default; "GitHub Actions is not permitted to create or approve pull requests" | tried anyway, in case it is on; when it is not, a green chore is merged with `POST /merges` and anything needing review becomes one issue with a compare link |
| Repository auto-merge | a repository setting, and the settings API is unreachable from Claude sessions | `agent-branches.yml` merges explicitly, after reading the checks on the exact head commit |

`tools/bootstrap-repo.sh` grants the first two properly, if you ever have a
terminal and a token to hand. It is **optional** -- it makes the presentation
nicer (real pull requests, Pages deployment history) and changes nothing
about whether the book publishes.

**Arm the GitHub bot, if you want it** (see section 3): add an
`ANTHROPIC_API_KEY` secret. Nothing else depends on it.

Dependabot's pull requests wait for a human. The actions here are pinned to
major versions, so every bump Dependabot opens is a major-version bump --
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
