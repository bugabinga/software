---
name: workflows
description: Write or review a GitHub Actions workflow - pinning, where the logic lives, caching, CI minutes, third-party action risk, auditability, and what each plan actually gives you. Use when adding a workflow, changing one, debugging a red or silent run, or asking why CI is slow or expensive.
---

# Building a CI workflow that is worth having

A workflow is a program that runs with your secrets, on a machine you do not
own, triggered by things other people can cause. Most advice about Actions is
about YAML. Almost none of what goes wrong here is YAML.

Numbers below are from GitHub's own reference pages and were read on
2026-09-13. They change; re-read them before relying on one.

## Before the first line

Four questions, in this order. Getting them wrong is not fixable by editing
the steps.

1. **What occasion is this?** A trigger is not a schedule, it is an event with
   a payload and a trust level. `pull_request` from a fork has a read-only
   token and no secrets; `workflow_run` and `pull_request_target` have both,
   for any head. If you cannot say in one sentence who can cause this workflow
   to run, stop.
2. **What must it be allowed to do?** Start from `permissions: contents: read`
   at the top and raise per job. The default is what an attacker inherits.
3. **What is its output?** A check name, an artifact, a comment, a pushed
   branch. Name it now: a required check's _name_ is a contract with the
   ruleset, and renaming a job silently un-gates the merge.
4. **What does it cost?** Minutes are per job. See _Minutes_ below.

## Pin every action to a full commit SHA

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
```

GitHub's own reference: "pinning to a full-length commit SHA is currently the
only way to use an action as an immutable release", and a tag "can be moved or
deleted if a bad actor gains access to the repository". The trailing comment
is what makes the pin readable; keep it accurate when you bump.

- A tag is a pointer. `@v4` is a promise by a stranger to keep meaning what it
  meant, forever, including after their account is compromised.
- Dependabot updates SHA pins and rewrites the comment. There is no mise or
  asdf ecosystem, so **only the actions are covered** -- pinned tool versions
  need their own sweep.
- The Marketplace "Verified creator" badge means GitHub verified an identity.
  It is a signal, not a guarantee.

## Keep the logic out of the YAML

An action that runs "when it runs" is untestable. The rule that pays for
itself: **YAML decides when and with what; a program decides what.**

- One task runner (`mise`, `make`, `just`, npm scripts) defines the work, and
  CI calls the same entry points a contributor calls. A green local run is
  then a green pull request because it is not a second definition that agrees
  by habit.
- Anything with a branch in it goes in a script or a program with a
  `--self-test`, not in a `run:` block. `tools/preview.py` and
  `tools/cloudflare.py` in this repository are the shape: the decision is
  testable on a laptop and the workflow only feeds it.
- Shell inside `run:` is still code. `set -euo pipefail`, `shellcheck`, and
  never interpolate `${{ }}` into a shell body -- pass it through `env:` so a
  branch named `"; rm -rf /` is a string rather than a statement.
- `actionlint` catches the YAML-shaped mistakes. Run it as a gate.

## Caching

Caching is not free and is not always a win. Measure before and after.

- **10 GB per repository** by default, shared by every cache in it.
- **Entries unused for 7 days are removed**, and when the cap is hit GitHub
  evicts "in order of last access date, from oldest to most recent". A cache
  keyed on something that changes every run is a cache that evicts everything
  else and never hits.
- **Scope runs downhill.** A branch can restore caches from itself, its base
  and the default branch; the default branch cannot restore a feature
  branch's. So warm the cache on `main` if you want pull requests to hit it.
- **A pull request's cache is scoped to its merge ref** and only re-runs of
  that pull request can restore it.

Key design: the key is exact, `restore-keys` are the prefix ladder.

```yaml
key: ${{ runner.os }}-deps-${{ hashFiles('**/lockfile') }}
restore-keys: ${{ runner.os }}-deps-
```

Do not cache what is cheap to fetch or expensive to validate. A 300 MB
toolchain cache that saves 40 seconds of download is a bad trade once it
starts evicting the build cache that saves four minutes.

## Minutes, and where they actually go

Public repositories run free on standard GitHub-hosted runners. Private ones
spend from the plan's allowance: **Free 2,000/month, Pro 3,000, Team 3,000,
Enterprise Cloud 50,000**. Self-hosted runners are free. **Larger runners are
always charged**, "even when used by public repositories".

Rates, and the reason nobody should default to macOS: Linux 2-core
**$0.006/min**, Windows **$0.010**, macOS **$0.062**. A macOS job is ten
Linux jobs.

What actually saves minutes, roughly in order of effect:

1. **Do not start the run.** Path filters (`paths`, `paths-ignore`) and a
   `concurrency` group that cancels superseded runs. The commonest waste is
   five runs of the same branch while someone pushes fixes.
2. **Be careful what the concurrency group is keyed on.** Keying on the branch
   alone makes a `push` run and a `pull_request` run cancel each other, and a
   required check that reads _Canceled_ is not a check that passed. Key on the
   event too.
3. **Fewer, longer jobs beat many short ones.** Every job pays its own setup:
   runner allocation, checkout, toolchain install. Billing is measured per
   job, so ten one-minute jobs are not the same as one ten-minute job -- and a
   matrix of trivial jobs is the usual way a bill triples without anything
   getting faster.
4. **Split only for parallelism you will actually wait on**, or for a check
   name a rule needs. Not for tidiness.
5. **`timeout-minutes` on every job.** The default ceiling is **6 hours** on a
   GitHub-hosted runner; a hung job bills all of it.
6. **`fail-fast` and ordering.** Put the 20-second linter before the
   four-minute build.

Ceilings worth knowing: 35 days per workflow run, 256 jobs per matrix,
concurrent jobs 20 (Free) / 40 (Pro) / 60 (Team) / 500 (Enterprise), and
`GITHUB_TOKEN` is limited to 1,000 API requests per hour per repository.

## Third-party actions

"A compromise of a single action within a workflow can be very significant":
an action runs with "all secrets configured on your repository, and may be
able to use the `GITHUB_TOKEN` to write to the repository".

Decide per action, and write the decision down:

- **Is it doing something you could do in four lines of shell?** Then do that.
  Most `uses:` for "set an output" or "comment on a PR" are `gh api` with
  extra supply chain.
- **Does it need the secret at all?** Split the job so the step that touches
  the credential is yours and the third-party step runs before it.
- **Is it pinned, and did you read the diff at that SHA?** A pin to code you
  have not looked at is a pin to a stranger's future self.
- **Can the repository restrict it centrally?** Settings → Actions → General
  → allowed actions (`actions: write` at the org level for a policy). An
  allowlist beats a convention.

The asymmetric ones to be most careful with: anything that runs on
`pull_request_target` or `workflow_run`, because those are privileged for
forks too; anything that wants `id-token: write`; anything that curls a script
at runtime, which makes the SHA pin decorative.

## The rule that costs everyone a day

**Events created with `GITHUB_TOKEN` do not start workflow runs.** A review
posted, a branch pushed, a pull request opened by the workflow token raises an
event that nothing is subscribed to. The exceptions are `workflow_dispatch`
and `repository_dispatch`.

So a two-workflow loop -- one posts, one reacts -- silently does not exist.
The ways out, in order of preference:

1. **`workflow_run`.** It fires because a workflow finished, not because an
   actor did something, so the rule does not apply. Remember it runs the
   _default branch's_ copy of the file with the default branch's secrets, for
   any head -- guard on
   `github.event.workflow_run.head_repository.full_name == github.repository`,
   and accept that the change cannot be tested before it merges.
2. **`gh workflow run` a `workflow_dispatch`.** Explicit, and a dispatch
   carries no pull request, so pass what you need as an input.
3. **A GitHub App installation token.** Not `GITHUB_TOKEN`, so it does start
   runs -- but it is a credential to hold, and an action that hands one back
   is not guaranteed to hand back one that works. Probe it before depending
   on it, and fall back.

## Auditability

A run that fails and says nothing costs more than a run that does not exist.

- **`::notice::`, `::warning::`, `::error::`** become annotations on the run
  and on the pull request. One line naming the cause beats a wall of stderr.
- **`$GITHUB_STEP_SUMMARY`** is the readable account of a run: what was
  decided and why. It dies with the run's logs, so anything durable goes in an
  artifact.
- **Artifacts** are the durable half. Keep the evidence a later question will
  need -- a provenance record of what ran, with what brief, at what cost --
  and set `retention-days` deliberately. Remember artifacts are downloadable
  by anyone who can see the run: on a public repository, **that is everyone**.
  Never put a credential in one.
- **Check names are the integration surface.** Rulesets, merge queues and
  status APIs match on the _job's_ name. A required check that never reports
  blocks every merge, so never require a name that only exists on some events
  -- and never require a step's name, which is not a check at all.
- **`always()`** on the step that records or reports, or you will lose exactly
  the runs worth keeping.

## What your plan actually gives you

|                         | Free   | Pro   | Team  | Enterprise Cloud |
| ----------------------- | ------ | ----- | ----- | ---------------- |
| Minutes/month (private) | 2,000  | 3,000 | 3,000 | 50,000           |
| Artifact storage        | 500 MB | 1 GB  | 2 GB  | 50 GB            |
| Cache                   | 10 GB  | 10 GB | 10 GB | 10 GB            |
| Concurrent jobs         | 20     | 40    | 60    | 500              |

- **Public repositories**: standard runners are free, on every plan. This is
  the single biggest lever on cost and it is a repository setting.
- **Larger runners** are billed always, public or not.
- **Rulesets** are documented as a Team and Enterprise feature, with
  organization-level rulesets Enterprise-only. Branch protection on a private
  repository is the thing most likely to be missing on a Free plan -- check
  before designing a gate around it.
- **Without a payment method, usage is blocked once the quota is spent.** On a
  private repository that means CI stops mid-month.

## Before you open the pull request

- [ ] Every `uses:` is a full SHA with an accurate version comment.
- [ ] `permissions:` is least-privilege, declared, and raised per job.
- [ ] No `${{ }}` interpolated into a shell body.
- [ ] `timeout-minutes` on every job; `concurrency` keyed on event and ref.
- [ ] Any logic worth being wrong about lives in a script with a self-test.
- [ ] `actionlint` passes.
- [ ] The check name matches what any ruleset requires, exactly.
- [ ] You can name who can trigger this and what they get access to.
- [ ] If two workflows talk to each other, you have checked the
      `GITHUB_TOKEN` rule above.
