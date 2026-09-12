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
| `fleet-report.yml` | Mondays 09:00 UTC | judges the fleet -- runs, failures, cost, turns, tokens, what each branch became, what is stuck -- and publishes one page to `<site>/fleet/`, appending a line to `history.jsonl` on the `fleet-log` branch so the record outlives the API's 90-day window |
| `maintenance.yml` | Mondays 06:17 UTC | compares every pin in `mise.toml` against its upstream, bumps Typst and opens an upgrade pull request *if the book still builds and passes every gate on it*; re-runs the outbound link check and files one standing issue for dead links |

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

#### The credential

The three fleet workflows read `CLAUDE_CODE_OAUTH_TOKEN` from the **`Fleet`
environment**, falling back to `ANTHROPIC_API_KEY` if that is what is set.
An environment secret is invisible to a job that does not name the
environment, which is why every fleet job carries `environment: Fleet`; get
that name wrong and the secret is simply absent, and the run says so rather
than failing obscurely.

Without either credential every trigger still fires, routes, and prints the
brief it would have used into the job summary. That is deliberate: it makes
`Fleet review` safe to require before the fleet is armed, and it makes the
routing watchable for nothing.

Note that a GitHub environment can carry protection rules of its own --
required reviewers, wait timers. Any set on `Fleet` apply to every fleet run,
which is a second place, besides the branch ruleset, where the fleet can be
paused or gated.

## 3. The bot inside GitHub (on request)

`claude.yml` picks up `@claude` in an issue, a pull-request comment or a
review comment, with the repository checked out and the book's gates
available. Use it for "@claude this link is dead" or "@claude why is this
build red" without leaving GitHub.

It needs an `ANTHROPIC_API_KEY` repository secret, which cannot be set from
the author's Claude sessions — the Actions secrets API is blocked to that
environment. Until the key exists, every run exits early with a notice rather
than failing. Everything in sections 1 and 2 works without it.

## Judging the fleet

`tools/fleet_report.py` is the operator's instrument, run weekly by
`fleet-report.yml` and by hand with `make fleet-report` (`DAYS=30` for a
longer window). It gathers what exists while it still exists -- workflow runs
and their conclusions, each agent run's execution record uploaded as an
artifact, every `agent/**` branch and whether it merged, and the open issues
-- and says a few blunt sentences about it before any table.

Three things make it worth reading rather than a dashboard nobody opens:

- It reports what it does *not* know. A run whose usage was never recorded is
  counted as unmeasured, because "we cannot say what the fleet cost" is a
  finding about the pipeline.
- It names work that will never land: a branch with no pull request and no
  merge is effort spent for nothing, and that is a fleet fault, not a backlog.
- Its history is a file, not a query. `history.jsonl` on `fleet-log` keeps one
  line per report forever, so a bad month is still visible after GitHub has
  pruned the runs it was derived from.

The page is at `<site>/fleet/`. It is reachable and `noindex`, and it is not
part of the book: not in the navigation, the sitemap or the search index.
`publish.yml` folds it in from the `fleet-log` branch, so it survives the
force-push that replaces the site.

## Identities the fleet does not have yet

Two things need a human and are written out in `docs/IDENTITY.md`: a GitHub
App, which is what would let the fleet open its own pull requests and get its
branches checked without a workaround, and an SSH signing key, which is what
would make its commits read Verified. Until the App exists, a branch the fleet
pushes cannot reach `main` without somebody opening a pull request for it.

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

## Issues: how the fleet is asked for things

Issues are the control surface. They are how work is requested from a phone,
and they are where the fleet reports what it could not do.

**Asking.** `.github/ISSUE_TEMPLATE/` has three forms, and blank issues are
off, because a form that names the agent and the target dispatches by itself
while free text needs somebody to interpret it.

| Form | Label it applies | What happens |
| --- | --- | --- |
| Material for the book | `fleet:material` | `notes-cartographer` saves the body to `notes/` verbatim, then reads it against the book and changes the shape if it must |
| Ask the fleet for something | `fleet:task` | the agent named in the form's dropdown runs, with the form's fields as its target |
| Something is wrong | `bug` | nothing automatic; it is a message to a person |

The **label is the trigger**, not the form: `fleet.yml` fires on
`issues: [labeled]`. So a label added later to an old issue dispatches it too,
which is the re-run mechanism, and a label removed and re-added is a retry.

Every dispatched agent puts `Closes #N` in its commit message, so the issue
closes when the work merges. The fleet adds `fleet:running` when it starts
and comments a link to the run.

**Reporting.** The fleet opens an issue in exactly two situations, and updates
one rather than filing duplicates:

- a branch it was entitled to merge that it could not (`Green and unmerged`);
- outbound links that have died, once a week, as a standing issue.

It does not open an issue to say it looked and found nothing.

## Reviews: Copilot, and answering it

The ruleset turns on Copilot's automated review. A review nobody answers is
worse than no review — the comments pile up, stop being read, and
`required_review_thread_resolution` means an unanswered thread blocks the
merge outright.

`fleet-respond.yml` wakes `review-responder` on any review or review comment
that is not the fleet's own. Its brief is explicit about what Copilot is good
and bad at here: reliable on shell quoting, unhandled errors, off-by-ones;
unreliable on prose, on Typst, and on anything whose correctness depends on
why the code exists. So it verifies before acting, fixes what is right, and
replies on the thread naming what a wrong comment missed. Every comment ends
in a fix or an answer.

Three workflows, three verbs, so it is clear which to look at:

| Workflow | Verb | Writes |
| --- | --- | --- |
| `fleet.yml` | do the work | a new branch |
| `fleet-review.yml` | judge it | a check, and a comment |
| `fleet-respond.yml` | answer feedback | the pull request's own branch |

## The merge policy

The author's standing decision: **everything arrives as a pull request, and
anything green merges itself except the automation.**

**The fleet decides about the book.** Structure, splits, rewrites, prose: the
author controls those by writing the agent definitions in `.claude/agents/`,
not by approving pull requests one at a time. Notes arrive one at a time over
weeks and any of them can invalidate the shape the book has; a fleet that had
to queue for approval on each would simply stop keeping up. So a green change
to `book/` merges, and the pull request is written for someone reading a
decision already taken.

The one thing that still waits for a human is `.github/` and `.claude/`: the
workflows and the fleet's own definitions. An agent that can rewrite its own
brief, or its own merge rule, is supervised by nothing. That is the whole of
the protected set, and it is what makes the delegation above safe to give.

To take a decision back, do not review harder: change the agent's brief, or
label a pull request `hold`.

### What branch protection did to this

`main` carries an active ruleset. Measured against it, the fleet currently
**cannot land anything**:

| The fleet tries | Result |
| --- | --- |
| `POST /merges` (no pull request) | rejected — `required_linear_history` forbids a merge commit |
| opening a pull request | refused — Actions is not permitted to create pull requests |
| `PUT /pulls/N/merge` | would be blocked — one approving review is required and Actions has no bypass |

The owner can still merge, so nothing is stuck permanently; it just all
routes through a human, which is the opposite of the delegation above.

#### Review by the fleet, which is what the protection was for

The intention behind the ruleset was not "a human must approve" but "this must
be reviewed" -- and the reviewer is the fleet. `fleet-review.yml` does that,
and it is built as a **status check** rather than as an approving review on
purpose. A check from Actions gates a merge in a way nothing argues with;
whether a bot's *approval* satisfies a required-reviews rule is a question
about GitHub's internals that would have to keep being true.

`pr-reviewer` reads the diff and checks what the automated gates cannot:
whether the agent stayed inside its brief, whether cited notes actually say
what the change claims, whether anything was invented, whether it contradicts
the book, and whether it is the smallest change that does the job. It writes a
verdict file; the workflow turns that into the check. No file means failure,
because silence must never read as approval.

So the settings that fit the intention are:

1. **Settings → Actions → General → Workflow permissions →** allow GitHub
   Actions to create and approve pull requests. Without this the fleet cannot
   open a pull request at all, and there is nothing to review.
2. **The `Main` ruleset → required status checks →** `Build`, `Spelling`,
   `Outbound links`, and — once the fleet is armed — `Fleet review`. Only
   `Spelling` is required today, so the gate that matters least is the only
   one enforced.
3. **The `Main` ruleset → require approvals: 0.** The review requirement moves
   into the checks, where the fleet can satisfy it. Leave it at 1 and only a
   second human can ever merge, since GitHub does not let an author approve
   their own pull request.

With those, no bypass actor is needed: the fleet opens a pull request, the
gates and the fleet review run, and a green one squash-merges. Linear history
intact, every rule still enforced.

**Order matters.** Do not make `Fleet review` a required check before an
`ANTHROPIC_API_KEY` exists and a few real pull requests have been through it.
A required check that can never pass would brick the repository, which is why
the workflow passes with a notice when there is no key.

Until then, a green branch the fleet may not merge becomes one issue saying
so, rather than a red run every time.

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
