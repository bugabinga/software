---
name: workflows
description: GitHub Actions and CI. Use when writing or reviewing a workflow, pinning an action, caching, spending runner minutes, or when a run is red, slow, or never started.
---

# Building a CI workflow that is worth having

A workflow is a program that runs with your secrets, on a machine you do not
own, triggered by things other people can cause. Most advice about Actions is
about YAML. Almost none of what goes wrong is YAML.

Every number lives in GitHub's reference pages, linked below and not copied
here: limits, prices and plan allowances all change, and a skill that asserts
one is a skill that will be wrong without anybody noticing. What is here is the
judgement, which does not.

## Before the first line

1. **What occasion is this?** A trigger is an event with a payload and a trust
   level, not a schedule. A fork's `pull_request` has a read-only token and no
   secrets; [`workflow_run` and `pull_request_target`][events] have both, for
   any head. If you cannot say in one sentence who can cause this to run, stop.
2. **What may it do?** Start at `permissions: contents: read` and raise per job.
   The default is what an attacker inherits.
3. **What is its output?** A check name, an artifact, a comment, a branch. Name
   it now: a required check's _name_ is the contract with the ruleset, so
   renaming a job wedges every merge until the rule is renamed with it.
4. **What does it cost?** See _Minutes_.

## Pin every action to a full commit SHA

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
```

A SHA is [the only immutable way to name an action][secure]; a tag is a pointer
a compromised account can move. The trailing comment is what makes the pin
readable -- keep it true when you bump. Dependabot maintains these and rewrites
the comment, but it has no ecosystem for pinned _tool_ versions, so those need
their own sweep.

## Keep the logic out of the YAML

**YAML decides when and with what. A program decides what.** A `run:` block is
code that can only be tested by pushing.

- One task runner defines the work and CI calls the same entry points a
  contributor calls, so a green local run means something.
- Anything with a branch in it belongs in a program with a self-test.
  `tools/preview.py` and `tools/cloudflare.py` are the shape here.
- `set -euo pipefail`, `shellcheck`, and never interpolate `${{ }}` into a shell
  body -- pass it through `env:`, so a branch named `"; rm -rf /` is a string
  and not a statement.
- `actionlint` catches the YAML-shaped mistakes. Gate on it, and on whatever
  catches the ones it does not: here `tools/check_workflows.py` finds a heredoc
  terminator indented past its `run:` block, which never closes, so bash runs a
  truncated script and says nothing.

## Caching

Caching is not free and not always a win. The rules that outlive the numbers:

- Entries are evicted by **last access**, so a key that changes every run never
  hits and evicts everything that would have.
- **Scope runs downhill.** A branch reads its own caches, its base's and the
  default branch's; the default branch cannot read a feature branch's. Warm the
  cache on `main` if pull requests are to hit it.
- A pull request's cache is scoped to its merge ref, so every later run of that
  pull request restores it and nothing outside the pull request can.
- The key is exact; `restore-keys` is the prefix ladder below it.

Do not cache what is cheap to fetch. A toolchain cache saving forty seconds is a
bad trade the moment it evicts a build cache saving four minutes.

[Cache limits, eviction and scope][cache].

## Minutes, and where they actually go

Billing is per job and rounded up -- GitHub "rounds the minutes and partial
minutes each job uses up to the nearest whole minute" ([rates][rates]) -- so
many short jobs cost more than the same work in one, and a matrix of trivial
jobs is the usual way a bill triples without anything getting faster. Runner
cost varies by platform by roughly an order of magnitude;
[check before defaulting to macOS][billing].

A public repository is charged nothing for standard runners, which is not the
same as free. Concurrent jobs are limited **per account**, not per repository,
so every job takes one of a ceiling your other repositories share. Whether
anything ever waits behind it is a measurement, not an assumption; stay clear of
the ceiling and optimise as though the minutes were billed, because the
discipline is identical and only the unit changes.

What saves minutes, in order of effect:

1. **Do not start the run.** Path filters, and a `concurrency` group that
   cancels superseded runs. The commonest waste is five runs of one branch while
   somebody pushes fixes.
2. **Key that group on the event as well as the ref.** On the ref alone a `push`
   run and a `pull_request` run cancel each other, and a required check reading
   _Canceled_ is not a check that passed.
3. **Fewer, longer jobs.** Every job pays its own allocation, checkout and
   toolchain install.
4. **Split only for parallelism you will wait on**, or for a check name a rule
   needs. Not for tidiness.
5. **`timeout-minutes` on every job.** The default ceiling is hours; a hung job
   bills all of it.
6. **Order cheap before expensive.** The twenty-second linter first.

## Third-party actions

An action runs with your secrets and may write to the repository with the
`GITHUB_TOKEN`, so [one compromised action compromises the workflow][secure].
Decide per action, and write the decision down:

- **Could four lines of shell do it?** Most `uses:` for "set an output" or
  "comment on a PR" are `gh api` with a supply chain attached.
- **Does it need the secret?** Split the job so the step touching the credential
  is yours.
- **Did you read the code at that SHA?** A pin to code nobody read is a pin to a
  stranger's future self.
- **Can the repository restrict it centrally?** An allowlist beats a convention.

Most dangerous: anything on `pull_request_target` or `workflow_run`, which are
privileged for forks too; anything wanting `id-token: write`; anything that
curls a script at runtime, which makes the pin decorative.

## The rule that costs everyone a day

[**Events created with `GITHUB_TOKEN` do not start workflow runs.**][token] A
review posted by the workflow token raises an event nothing is subscribed to, so
a two-workflow loop silently does not exist. `workflow_dispatch` and
`repository_dispatch` are exceptions. So is a pull request the token opens or
updates -- including by pushing to the branch of one already open: that run is
created but held in an approval-required state, which is a different symptom and
a different fix.

Ways out, in order:

1. **`workflow_run`** -- it fires because a workflow finished, not because an
   actor acted. It runs the _default branch's_ copy of the file with the default
   branch's secrets for any head, so guard on
   `github.event.workflow_run.head_repository.full_name == github.repository`,
   and accept that the change cannot be tested before it merges.
2. **Dispatch it yourself** with `gh workflow run`. A dispatch carries no pull
   request, so pass what you need as an input.
3. **A GitHub App token** is not `GITHUB_TOKEN` and does start runs -- but it is
   a credential to hold, and an action that hands one back may hand back one
   that does not work here. Probe it before depending on it, and fall back.

## Auditability

A run that fails and says nothing costs more than a run that never happened.

- `::notice::` / `::warning::` / `::error::` become annotations. One line naming
  the cause beats a wall of stderr.
- `$GITHUB_STEP_SUMMARY` is the readable account of a decision; it dies with the
  logs, so anything durable goes in an artifact with a deliberate
  `retention-days`.
- Artifacts are downloadable by anyone who can see the run. On a public
  repository that is everyone: **never put a credential in one.**
- Check **names** are the integration surface -- rulesets and merge queues match
  on the job's name. A required check that never reports blocks every merge, so
  never require a name that only exists on some events, and never require a
  step's name, which is not a check.
- `always()` on the step that records, or you lose exactly the runs worth
  keeping.

## Plans

Do not design a gate before reading [what the plan includes][billing]. The two
facts that decide the shape: **a public repository runs standard runners for
free**, which is the largest lever on cost and is a repository setting; and
branch protection on a **private** repository is the thing most likely to be
absent on a free plan, so check before building a merge rule around it.

## Before you open the pull request

- [ ] Every `uses:` is a full SHA with an accurate version comment.
- [ ] `permissions:` declared, least-privilege, raised per job.
- [ ] No `${{ }}` interpolated into a shell body.
- [ ] `timeout-minutes` on every job; `concurrency` declared -- keyed on event
      and ref for per-branch runs, one global group where only one run may
      proceed at a time.
- [ ] Logic worth being wrong about lives in a program with a self-test.
- [ ] `actionlint` passes -- and `mise run check-workflows` with it, which adds
      the rules in `tools/check_workflows.py`'s docstring rather than a list
      here that goes stale: the pin rule above, a heredoc terminator indented
      past its `run:` block, and `gh api --paginate` with a jq filter that
      aggregates, which answers once per page and killed this workflow on #82.
- [ ] The check name matches what the ruleset requires, exactly.
- [ ] You can name who can trigger this and what they reach.
- [ ] If two workflows talk to each other, you have checked the `GITHUB_TOKEN`
      rule.

Three items are standing debt here rather than rules this repository keeps.
`settings.yml` is the only job in the tree that sets **`timeout-minutes`**.
Seven `run:` bodies interpolate `${{ }}`: `release.yml:43` builds a shell string
out of a tag name, `maintenance.yml:120` out of a step output,
`maintenance.yml:227` an issue body, and `fleet.yml:313`, `fleet-review.yml:216`
and `fleet-respond.yml:439` pass `runner.temp` while `fleet-review.yml:293`
passes a pull request number or a dispatch input. And three workflows declare no
`concurrency` at all: `agent-branches.yml`, `labels.yml` and `release.yml`. All
three stay on the list because they are right, and they are named because a
checklist every existing file fails is one the next worker learns to skip. Fix
the workflow you are touching; each sweep is its own pull request.

[billing]: https://docs.github.com/en/billing/concepts/product-billing/github-actions
[rates]: https://docs.github.com/en/billing/reference/actions-runner-pricing
[cache]: https://docs.github.com/en/actions/reference/dependency-caching-reference
[events]: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
[secure]: https://docs.github.com/en/actions/reference/secure-use-reference
[token]: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
