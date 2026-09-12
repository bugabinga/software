# The fleet

Who maintains this book besides the author, what each of them may touch, and
how to stop them.

Three kinds of worker, in increasing order of how much judgement they exercise
and decreasing order of how often they run.

## 1. Workflows (no judgement, no agent)

Deterministic work that a script does better than a model.

| Workflow             | When                                                         | What                                                                                                                                                                                                                                                       |
| -------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ci.yml`             | every pull request and push to `main`                        | build, internal links, spelling, outbound links, example code; attaches the built site to the run and comments a preview link                                                                                                                              |
| `publish.yml`        | pushes to `main`                                             | builds, then force-pushes the site to the `gh-pages` branch as a single orphan commit                                                                                                                                                                      |
| `release.yml`        | `v*` tags                                                    | attaches the PDF and a zip of the site to a release                                                                                                                                                                                                        |
| `agent-branches.yml` | pushes to `agent/**` and `maintenance/**`, and CI completing | opens a pull request for a branch the fleet pushed where the repository permits it, and then merges green chores or reports everything else                                                                                                                |
| `fleet-report.yml`   | Mondays 09:00 UTC                                            | judges the fleet -- runs, failures, cost, turns, tokens, what each branch became, what is stuck -- and publishes one page to `<site>/fleet/`, appending a line to `history.jsonl` on the `fleet-log` branch so the record outlives the API's 90-day window |
| `notes-reindex.yml`  | pushes to `agent/note-**`                                    | rebuilds `notes/index.md` after the Cloudflare inbox files a note, since the Worker writes one file and stops                                                                                                                                              |
| `worker-deploy.yml`  | pushes to `main` touching `worker/**`                        | tests the notes inbox with plain node, then deploys it to Cloudflare and sets its secrets from the repository's                                                                                                                                            |
| `preview.yml`        | CI finishing on a pull request                               | deploys the site CI just built as an assets-only Cloudflare Worker, comments its URL, and deletes the previews whose pull requests have closed                                                                                                             |
| `maintenance.yml`    | Mondays 06:17 UTC                                            | compares every pin in `mise.toml` against its upstream, bumps Typst and opens an upgrade pull request _if the book still builds and passes every gate on it_; re-runs the outbound link check and files one standing issue for dead links                  |

### What a push costs

Measured, not guessed: one push to a branch with an open pull request used to
run **nine jobs, 131 seconds of work, nine billed minutes**. GitHub rounds
every job up to the whole minute, so parallelism across short jobs is bought
with money and repaid in seconds.

`ci.yml` is one job now instead of three, and `agent-branches.yml` one instead
of three, each thing gated by the event that wants it. Same work, four billed
minutes instead of nine.

Two jobs stay alone, and each is a deliberate purchase. `Fleet review` is a
model call, which is the only place the minutes are actually being spent on
thinking. `Preview` is a fifth minute per push, bought for a URL a reviewer
can open on a phone instead of a zip they cannot.

## 2. Agents (judgement, on a schedule or on demand)

Each definition in `.claude/agents/` opens with **who that agent is** — its
voice, the one thing it protects, what it refuses, and its characteristic
failure. They are deliberately unalike, and some of them disagree: the
cartographer keeps moving the book, the prose editor needs it to stand still;
the reviewer's job is _no_, the responder's is to end the exchange. Those
tensions are load-bearing. Do not smooth them out.

House style for every worker is in `CLAUDE.md` — terse, link rather than
restate, long code comments and short reports.

Defined in `.claude/agents/`, so a scheduled session, an interactive session
and the GitHub-side bot all run the same agent rather than improvising.

| Agent                | Beat                                                                              | Never                                                        |
| -------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `pipeline-gardener`  | Typst upgrades, CI failures, link rot, the tooling                                | edits prose; touches `notes/`                                |
| `notes-cartographer` | reads `notes/`, proposes outline changes and chapter stubs                        | writes chapter prose; edits `notes/`                         |
| `prose-editor`       | copyediting, terminology drift, terms used before defined, stale cross-references | rewrites for style; changes what a paragraph claims          |
| `chapter-drafter`    | drafts a chapter from notes, against a named target                               | runs on a schedule; invents citations or uncompiled listings |

Two skills carry the procedures: `.claude/skills/garden` (the maintenance
sweep, including the merge policy) and `.claude/skills/ingest` (getting
material into `notes/`).

### Triggers

The fleet runs in CI, through `fleet.yml`. An agent runs on the **occasion**
that calls for it, and gets a brief written for that occasion rather than one
generic instruction:

| Trigger            | Fires on                                        | Agent                | What the brief adds                                                                                           |
| ------------------ | ----------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------- |
| `notes-arrived`    | a push to `main` touching `notes/**`            | `notes-cartographer` | names what just landed; asks for tensions to be surfaced now, while the author is still close to the material |
| `chapters-changed` | a push to `main` touching `book/chapters/**`    | `prose-editor`       | scopes the review to those chapters and to the cross-references a reworded heading silently breaks            |
| `weekly-garden`    | Mondays 07:00 UTC                               | `pipeline-gardener`  | the two things only it covers: the Typst pin against the latest release, and links that died this week        |
| `monthly-prose`    | 1st, 08:00 UTC                                  | `prose-editor`       | the whole book at once -- terminology drift, terms used before defined, chapters that have drifted together   |
| `on-demand`        | `workflow_dispatch`, with an agent and a target | any                  | the dispatch narrows the agent's brief and may not widen it                                                   |

The briefs live in `.claude/fleet/*.md`, not in the workflow, so changing what
an agent is told on a given occasion is a readable diff. `tools/fleet_brief.py`
routes the occasion to a brief and fills it in; `mise run check` runs its
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

- It reports what it does _not_ know. A run whose usage was never recorded is
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

## How notes arrive

`docs/NOTES-INBOX.md` is the whole of it. In short: the author's note-taking
session POSTs to a Cloudflare Worker, which writes the note to an
`agent/note-**` branch and stops. Everything after that is the machinery
already described here.

The Worker exists for one reason, and it is not hosting: a GitHub token cannot
be scoped to "may only file a note", so without it that session would hold
`contents: write` on the book. Notes still live in `notes/`, in the
repository, verbatim and never edited. Cloudflare is the inbox, not the
archive.

## Previews

Every pull request from this repository gets a URL once CI is green, posted
as a comment and replaced on each push. `preview.yml` deploys the site CI
already built as an assets-only Cloudflare Worker named `book-pr-<number>`.
A fork's gets none: `workflow_run` would hand it the credential, so the head
repository is checked rather than assumed.

**The account needs a workers.dev subdomain**, once, at
<https://dash.cloudflare.com/?to=/:account/workers/subdomain>. Without it
wrangler refuses to publish anything that has no route, which is every Worker
here -- and that is why `worker-deploy.yml` failed on every run from the day
it was armed, so the notes inbox has never actually deployed. Both workflows
now ask before deploying and say that sentence instead of failing red.

It runs on `workflow_run` rather than as a step in `ci.yml`, and that is the
whole design. The Cloudflare credential is an environment secret and the
`Cloudflare` environment is restricted to `main` on purpose -- a deploy from a
branch would be a stranger's Worker on the author's account. A `workflow_run`
job executes in `main`'s context, so it satisfies that restriction instead of
loosening it, and needs no second token. The cost is one extra job per push,
which is one billed minute.

Previews delete themselves, but not when the pull request closes: the reaper
runs inside the next `Preview` job, and that job needs an open pull request
of its own to have pushed and passed CI. Close the last one and its Worker
survives until another is built. It rides along there because that run is
already awake and already holding the credential; a schedule or a
`pull_request: closed` trigger would each be another run, and `pull_request`
cannot reach the `Cloudflare` environment anyway. The naming and the matching
live together in `tools/preview.py` and are tested against each other: a
reaper that matches loosely deletes somebody else's Worker on the same
account, and one that matches too tightly leaks previews until the account's
limit stops the next deploy. Both fail quietly.

## Standalone pages

Reachable on the site, and deliberately not part of the book: no navigation,
no sitemap entry, no search index, `noindex` in their own head. A reader who
wandered into one from a chapter would be right to be confused.

| Page            | What it is                                                                                                                                                                                                                                                     |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `<site>/skill/` | Builds the note-taker's skill. Two fields in, a zip out. The zip is assembled in the browser, so the intake token never leaves the page -- there is no server behind a static file on Pages, which is the whole reason this is a page rather than an endpoint. |
| `<site>/fleet/` | The weekly fleet report, folded in by `publish.yml` from the `fleet-log` branch.                                                                                                                                                                               |

Anything under `site/` that is not `assets` or `templates` is copied to the
site root by `tools/build.py`, so a new standalone page is a directory and
nothing else.

`tools/check_skill_page.py` runs the generator's own script under node and
opens the zip it produces with Python's `zipfile`. Two runtimes have to agree
it is a zip before it is published, because the failure mode is the author
discovering a corrupt download at the moment they are setting up their
note-taker.

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

| Wanted                          | Refused because                                                                                                                                                | Done instead                                                                                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pages built from Actions        | creating the Pages site is privileged; the workflow token gets "Resource not accessible by integration", and the Pages API is unreachable from Claude sessions | `publish.yml` pushes the built site to `gh-pages`, which needs only `contents: write` and which GitHub serves without configuration                           |
| Workflows opening pull requests | off by default; "GitHub Actions is not permitted to create or approve pull requests"                                                                           | tried anyway, in case it is on; when it is not, a green chore is merged with `POST /merges` and anything needing review becomes one issue with a compare link |
| Repository auto-merge           | a repository setting, and the settings API is unreachable from Claude sessions                                                                                 | `agent-branches.yml` merges explicitly, after reading the checks on the exact head commit                                                                     |

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

| Form                        | Label it applies | What happens                                                                                                              |
| --------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Material for the book       | `fleet:material` | `notes-cartographer` saves the body to `notes/` verbatim, then reads it against the book and changes the shape if it must |
| Ask the fleet for something | `fleet:task`     | the agent named in the form's dropdown runs, with the form's fields as its target                                         |
| Something is wrong          | `bug`            | nothing automatic; it is a message to a person                                                                            |

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

## Two channels for two kinds of finding

A fault in a chapter is either decidable or it is judgement, and they should
not share an artefact.

**Decidable** — a cross-reference to no chapter, a note cited at a line it does
not have, a marker left in the prose. `tools/prose_scan.py` finds these and
emits SARIF, which GitHub takes from any tool: the finding lands as an
annotation on the line, with a rule id, a severity, a dismissal flow and
history in the Security tab. `mise run check` runs it too. The test for a rule
belonging here is whether two people would agree on every result without
discussing it.

**Judgement** — invention, a citation that does not support its claim, an
agent outside its brief. That is `pr-reviewer`'s, delivered as review threads.

Until this split, the reviewer wrote prose about faults a program could have
pinned to a line, which wastes a model and produces the worse artefact.

`book/terms.toml` exists and is deliberately empty: the `term-drift` rule
is inactive until somebody writes down what this book's vocabulary is. A
rule that invented its own terminology would be enforcing a program's
opinion.

## Reviews: how the loop runs

`pr-reviewer` posts a **real GitHub review**, not a comment: findings become
inline threads on the lines they are about, and where the reviewer knows the
fix it comes as a `suggestion` block applied with one click. A `fail` is
submitted as _changes requested_.

`review-responder` then answers every unresolved thread -- a fix pushed to the
same branch, or a reply saying what the finding missed -- and **resolves it**.
Its push runs the reviewer again on the new head. That is the loop, and it is
the point: a review that nothing has to answer decays into a note.

Three things keep it from running forever:

- **Three rounds.** `fleet-respond.yml` counts the fleet's own
  changes-requested reviews. On the fourth it does not run the agent at all:
  it labels the pull request `hold`, says once why, and leaves it. Two agents
  disagreeing is the author's to settle.
- **The responder does not answer itself.** It wakes on a
  `pull_request_review` that requests changes, never on a
  `pull_request_review_comment`, which is what its own replies are.
- **A pass dismisses the objection.** The reviewer never approves -- whether a
  bot's approval satisfies a rule is a question about GitHub's internals, and
  the merge is gated by the `Fleet review` check instead. So when a later
  round passes, `tools/post_review.py` dismisses the earlier changes-requested
  reviews. Without that a fixed pull request would carry a standing objection
  from three commits ago and never become mergeable.

The reviewer writes only JSON; `tools/post_review.py` turns it into the
review. Line numbers, diff sides, the range syntax and the fallback when
GitHub refuses a request for changes on its own pull request are things a
program is right about every time. Its `--self-test` checks the line
arithmetic, which is the part that silently misplaces a comment.

## Who reviews, and who answers

Two reviewers, and neither of them is Copilot.

`pr-reviewer` judges every pull request and gates the merge. The author
reviews what they choose to. `fleet-respond.yml` wakes `review-responder` on
either, and every comment ends in a fix or in a reply saying what the finding
missed -- because `required_review_thread_resolution` means an unanswered
thread blocks the merge outright.

**Copilot's automated review is off.** It needs a paid Copilot plan, and since
1 June 2026 each review also bills Actions minutes, which is the budget this
fleet is built around. The `copilot_code_review` rule was removed from the
`Main` ruleset on 2026-09-12 rather than paid for; `pr-reviewer` already
covers the same ground and costs a model call the fleet is paying for anyway.
Nothing here should assume a third reviewer exists.

Three workflows, three verbs, so it is clear which to look at:

| Workflow            | Verb            | Writes                        |
| ------------------- | --------------- | ----------------------------- |
| `fleet.yml`         | do the work     | a new branch                  |
| `fleet-review.yml`  | judge it        | a check, and a comment        |
| `fleet-respond.yml` | answer feedback | the pull request's own branch |

## Which model runs which agent

Three tiers, and the words are the author's.

| Tier      | Model              | For                                      |
| --------- | ------------------ | ---------------------------------------- |
| workhorse | `claude-sonnet-5`  | often, and mechanical                    |
| smart     | `claude-opus-5`    | everything else, which is most judgement |
| genius    | `claude-fable-5-1` | important and rare                       |

| Agent                | Tier      | Why                                               |
| -------------------- | --------- | ------------------------------------------------- |
| `chapter-drafter`    | genius    | writes the book itself, and only on request       |
| `notes-cartographer` | genius    | decides the book's shape, once a note arrives     |
| `pr-reviewer`        | smart     | the gate; a careless pass is worse than no review |
| `review-responder`   | smart     | must resist deference, which is judgement         |
| `prose-editor`       | smart     | what is left after the scanner is judgement       |
| `pipeline-gardener`  | workhorse | weekly and on every CI failure; mechanical        |

The tier lives in the agent's own `model:` frontmatter and the mapping lives
in `tools/fleet_brief.py`, which resolves one to the other and writes `model=`
for the workflow to pass as `--model`. It was decorative before that: these
definitions are briefs an agent is told to read, not Claude Code subagents, so
nothing read their frontmatter and every agent ran on the action's default --
which is how `pr-reviewer` gated eight merges on Haiku without anyone
noticing.

What the tier asks for and what actually served are different facts. The
weekly report records the second, per agent, because a fallback under load
changes it and nothing else in the repository would say so.

## What is written down, and where

Three records, and each exists because the one above it expires.

| Record                         | Granularity | Lives   | Written by                   |
| ------------------------------ | ----------- | ------- | ---------------------------- |
| `fleet-run-<id>` artifact      | one run     | 90 days | each dispatching workflow    |
| `runs.jsonl` on `fleet-log`    | one run     | forever | `fleet_report.py --runs-log` |
| `history.jsonl` on `fleet-log` | one week    | forever | `fleet_report.py --history`  |

The artifact holds two files. Claude Code's execution output says how many
turns a run took, what it cost and which model served it. `provenance.json`,
written by `tools/fleet_record.py`, says what the run was _for_: the trigger,
the agent, the model its definition asked for, a digest of the brief it was
given, the branch it was pointed at and the commit it started from.

Both are needed and neither is enough. Without provenance the report has to
guess the agent from the workflow name, which works for `fleet-review.yml` and
`fleet-respond.yml` and collapses everything `fleet.yml` dispatches into one
row called "dispatched". Without the execution output there is no cost.

The brief is recorded as a digest rather than its text. It is generated from a
template and the occasion, it can be long, and the question worth answering is
"was this the same instruction as last time", which a hash answers and a copy
does not.

`runs.jsonl` is the durable half, appended weekly and deduplicated by run id.
Both the artifact and the API's own run listing stop at 90 days, so a question
asked in the spring about a run in the winter has nothing else to read. One
line per agent run: trigger, agent, model asked for, model served, turns,
seconds, cost, branch, pull request, and the commit it started from.

A run that died before calling the model still gets a line. `always()` on the
recording step is deliberate: the runs worth tracing are disproportionately
the ones that failed.

`fleet-log` is append-only in the git sense as well as the file sense: the
report commits on top of what is there and pushes a fast-forward. It used to
rebuild the history each week and force-push over it, which kept the branch
to one commit and meant the JSONL files were the only copy of a record whose
whole purpose is to outlive the API's 90-day window. Fast-forward is also
what lets a ruleset guard the branch with nothing on its bypass list.

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

| The fleet tries                  | Result                                                                        |
| -------------------------------- | ----------------------------------------------------------------------------- |
| `POST /merges` (no pull request) | rejected — `required_linear_history` forbids a merge commit                   |
| opening a pull request           | refused — Actions is not permitted to create pull requests                    |
| `PUT /pulls/N/merge`             | would be blocked — one approving review is required and Actions has no bypass |

The owner can still merge, so nothing is stuck permanently; it just all
routes through a human, which is the opposite of the delegation above.

#### Review by the fleet, which is what the protection was for

The intention behind the ruleset was not "a human must approve" but "this must
be reviewed" -- and the reviewer is the fleet. `fleet-review.yml` does that,
and it is built as a **status check** rather than as an approving review on
purpose. A check from Actions gates a merge in a way nothing argues with;
whether a bot's _approval_ satisfies a required-reviews rule is a question
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

## Who has to approve what

`.github/CODEOWNERS` names the author as the owner of `.github/` and
`.claude/`, and the `Main` ruleset requires an owner's approval. Everything
else in the tree has no owner, which is the point: the author controls the
book by controlling the fleet, not by reviewing what it writes.

This duplicates a rule `agent-branches.yml` already applies -- it refuses to
auto-merge anything under those paths -- and the duplication is deliberate.
That rule is the automation policing itself, in a file the automation can
write to. It holds only because editing that file is itself a `.github/`
change, which is an argument rather than a mechanism. CODEOWNERS is the
mechanism, and the fleet cannot reach the setting that enforces it.

**The one way it bites:** a pull request the author opens themselves touching
those paths cannot be approved by them, and there is no second owner. The
fleet's own pull requests are authored by `claude[bot]`, so those are fine.
For the rare hand-written one, the bypass toggle is what it is for.

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
