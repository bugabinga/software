# The fleet

A signpost, not a description. Everything here used to be prose about
mechanisms, which meant two sources of truth and one of them silently wrong. The
mechanism is the source of truth; this says where it is.

## Where each thing is decided

| Question                                  | Read                                                                         |
| ----------------------------------------- | ---------------------------------------------------------------------------- |
| Which agents exist, and what each is for  | `.claude/agents/*.md`                                                        |
| What an agent is told on a given occasion | `.claude/fleet/*.md`, routed by `tools/fleet_brief.py`                       |
| Which occasion fires when                 | the `on:` block of each `.github/workflows/*.yml`                            |
| How a label becomes a dispatch            | `fleet.yml`, the "Work out the occasion" step                                |
| Why a push does not run an agent directly | `tools/occasion.py`, `repository_dispatch` -- and `fleet.yml`'s `relay` job  |
| What happens to an issue nobody labelled  | `triage.yml`, on the event and on a daily sweep                              |
| What the `fleet:` labels mean             | `MARKS` in `tools/triage.py`; the roster is `.github/labels.toml`            |
| What merges itself, and what waits        | `agent-branches.yml`                                                         |
| What the branch rules are                 | `repo.toml`, applied by `settings.yml`, checked by `mise run check-settings` |
| Which model runs which agent              | the `model:` in each agent definition, resolved by `tools/fleet_brief.py`    |
| What the fleet cost and what is stuck     | `mise run fleet-report`                                                      |
| Procedures a worker follows               | `.claude/skills/*/SKILL.md`                                                  |

If a question here can be answered by reading a file, that file is the answer.
Do not write the answer down a second time: a paraphrase cannot be checked, so
it rots, and the rot is found one claim at a time by whoever reads it next.

## Asking the fleet for something

Open an issue and label it `fleet:task` or `fleet:material`. `fleet.yml`
dispatches on the label. `.github/ISSUE_TEMPLATE/` has the forms; blank issues
are off, because a form that names the agent and the target dispatches by itself
and free text needs somebody to interpret it.

An issue with no label, or the wrong one, is `triage.yml`'s — on the event and
again on a daily sweep, because the event alone stranded #84 for fifteen hours
and would have stranded every issue that predated the workflow.

## The pull request cycle is the fleet's

Pull requests are theirs to open, answer and get green. The author and the
operator work on the fleet by committing to `main`. A fleet pull request that
cannot get itself merged is a bug in the fleet, and the fix goes on trunk — not
a round of comments on the branch.

This is in force until the author lifts it. What it replaced: #82 ran
`Fleet review` 153 times — 95 red, 33 cancelled by the next push, 25 green —
across 18 verdicts, every one answered by hand. It converged when the operator
stopped, not when the fleet did.

## What agents are for

Judgement. Anything mechanical belongs in a program with a gate on it, not in an
agent's instructions and not in a document — an agent asked to remember a rule
is a rule that holds most of the time.

## Stopping it

```sh
gh workflow disable fleet.yml          # scheduled and label-driven agents
gh workflow disable fleet-review.yml   # the reviewer (a required check: see repo.toml)
gh workflow disable fleet-respond.yml  # the responder
gh workflow disable triage.yml         # the issue triager
gh workflow disable claude.yml         # the @claude bot
git rm -r .claude/agents .claude/fleet # or remove the briefs entirely
```

`ci.yml` and `publish.yml` are the book being checked and published, which is a
different decision from stopping the fleet.
