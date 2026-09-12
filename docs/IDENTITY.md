# Giving the fleet an identity

Two setup jobs that need a human. They are the only two, and the point of
doing them the way described here is that **you never come back**.

An earlier version of this file listed the exact permissions the fleet needed
today. That was a mistake: it made the app's grant a per-feature decision, so
every improvement to the fleet would have meant another trip to a settings
page. The grant is not the policy. Get it right once, wide enough to never
block a change, bounded where it actually matters, and do the narrowing in the
repository where it can be read, reviewed and changed by a pull request.

---

## The principle

**The app may change the work. It may never change the rules that govern the
work.**

That line is the only judgement call in this document, and it is worth stating
plainly because everything else follows from it. An agent that can rewrite the
repository's settings, read its secrets, or edit the environment protections
is not supervised by anything. An agent that can push branches, open pull
requests, merge, comment and start CI is doing its job. The first set is the
ceiling; the second is everything below it.

Three layers, and only the first is on a web page:

| Layer | Where | Who changes it |
| --- | --- | --- |
| **Ceiling** — what the app *could* ever do | GitHub App settings | you, once |
| **Per workflow** — what a given workflow may do | `permissions:` in the workflow | a pull request |
| **Per token** — what one step may do | `permission-*` inputs on the token action | a pull request |

Nothing the fleet grows into needs the first layer touched again, because the
ceiling already covers everything a book pipeline can want. Tightening happens
in the two layers that live in the repository, are diffable, and are subject
to the same review as any other change.

---

## 1. The GitHub App

**What it fixes today.** `agent-branches.yml` currently logs this on every
branch the fleet pushes:

> `agent/badges` is green but unmerged — no pull request exists, because this
> repository does not let Actions open them, and a direct merge commit is
> refused by the linear-history rule

Two settings closing on each other: Actions cannot open a pull request here,
and without one the only merge the API offers is a merge commit, which the
`Main` ruleset forbids. Squash needs a pull request. So the fleet works, and
pushes, and then stops forever and files an issue about it.

An App installation token is not `GITHUB_TOKEN`, so it opens pull requests
regardless of that setting; its pushes trigger workflows (a `GITHUB_TOKEN`
push triggers nothing, which is why an agent's branch arrives with no CI on
it); and its work is attributed to the app rather than to
`github-actions[bot]`.

**One app is enough**, and more than one would be worse. The app is an
identity, not a capability: every workflow mints its own short-lived token
from it, scoped by its own `permissions:` block. Separate apps per agent would
mean separate keys to rotate for a distinction that commit trailers make
better. It costs nothing, on every plan.

### Permissions: set these once

Everything a book pipeline can want, and nothing that would let the fleet
change its own guardrails.

**Grant, all at write** — Contents, Issues, Pull requests, Actions, Checks,
Commit statuses, Deployments, Workflows. Plus **Metadata: read**, which GitHub
ticks for you.

**Never grant** — Administration, Secrets, Variables, Environments, Codespaces
secrets, Organization anything. These are the guardrails: repository settings,
the credentials themselves, the environment rules that gate them. An agent
holding these could quietly widen its own authority, and no review after the
fact would catch it.

Everything else — Pages, Packages, Projects, Discussions, Security events,
Dependabot secrets — is neither useful here nor dangerous. Leave it at *No
access* and do not think about it again.

`Workflows: write` is in the grant list and deserves a word, because it is the
one people leave out. Without it, a token cannot push or merge any change
under `.github/workflows/`, and this repository's fleet edits its workflows
constantly. Policy still says `.github/` changes need a human — that is
enforced by `agent-branches.yml`, in the repository, where it can be read.
Enforcing it a second time by withholding a permission would mean the fleet
fails confusingly instead of stopping deliberately.

### Doing it

1. <https://github.com/settings/apps/new>
2. **Name**: anything recognisable; it appears as `<name>[bot]` on everything
   it does.
3. **Homepage URL**: the repository's URL.
4. **Webhook**: untick **Active**.
5. **Repository permissions**: as above.
6. **Where can this be installed?** *Only on this account.*
7. Create it, then note the **App ID**.
8. **Private keys** → **Generate a private key**. A `.pem` downloads; it is
   shown once and is the whole of the app's authority.
9. **Install App** → this repository only.
10. Store the two halves — they go in different places, see below:
    - Settings → Secrets and variables → Actions → **Variables** →
      `FLEET_APP_ID`, the number. Not a secret: it is a public identifier, and
      hiding it only means it is masked out of the log at the moment somebody
      is reading one.
    - Settings → **Environments** → new environment `Bot` → **Add environment
      secret** → `FLEET_APP_PRIVATE_KEY`, the **entire** `.pem` including the
      `-----BEGIN`/`-----END` lines. Multi-line is correct here; the earlier
      newline problem was a token that had to fit in one HTTP header.
    - On `Bot`, set **Deployment branches** to *Selected branches* → `main`.

Then say so. Wiring the workflows is a pull request, not your job.

### Checking it

`bot-check.yml` asks GitHub what the app was actually granted and reports it
against the list above — on demand, when the check itself changes, and on the
first of each month. An app can declare a permission and be installed without
it, and permissions are edited on a web page months apart, so the failure mode
is silence until the one call that needed the thing that went away.

It fails on a missing essential, notes anything below the ceiling with what it
would cost, and fails on anything in the *never grant* list. That last one is
the check worth having: it is the only thing standing between a mis-click and
a fleet that can rewrite its own rules.

---

## 2. Commit signing

Optional, not urgent, and worth being honest about: it makes the fleet's
commits read **Verified** instead of **Unverified**. That matters if the
fleet's branches ever merge without a human reading them, and very little
while they do not. It is a prerequisite for one day requiring signed commits
on `main`.

Skip `use_commit_signing`, which is the obvious input and the wrong one: it
commits through GitHub's API instead of the git CLI, and the action's own
security document says that route "cannot perform complex git operations".
Every agent here works by making a branch with git and pushing it.
`ssh_signing_key` signs and leaves git alone.

1. `ssh-keygen -t ed25519 -f ~/.ssh/fleet_signing -N "" -C "fleet signing"`
2. <https://github.com/settings/ssh/new> — paste `fleet_signing.pub`, and set
   **Key type** to **Signing Key**. Not *Authentication Key*: that one signs
   nothing and fails silently.
3. Settings → Environments → `Fleet` → **Add environment secret** →
   `FLEET_SSH_SIGNING_KEY`, the contents of the **private** file
   `~/.ssh/fleet_signing`. The private half; the public half went to GitHub in
   step 2.

---

## Where the credentials live

| Credential | Where | Why there |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | `Fleet` environment | Buys model time. Only the three agent workflows need it. |
| `FLEET_SSH_SIGNING_KEY` | `Fleet` environment | Same consumers, and it grants nothing. |
| `FLEET_APP_ID` | repository variable | Not a secret. |
| `FLEET_APP_PRIVATE_KEY` | `Bot` environment, `main` only | Write access to the repository. |

**Why the App key is not in `Fleet`.** The workflow that needs it,
`agent-branches.yml`, is plumbing: no model, no judgement, it opens pull
requests and merges green chores. Sharing `Fleet` would force it to declare
that environment, and then anything protecting `Fleet` protects it too —
including the required-reviewers rule that is the real stop button for a
misbehaving agent. Pressing that button would also stop pull requests being
opened, which is the opposite of what you want while deciding whether an agent
has gone wrong.

**Why `Fleet` cannot be locked to `main`.** It looks like obvious hardening and
it does not work: `Fleet review` runs on `pull_request`, and its deployment
records carry the pull request's head branch as the ref — `agent/badges`,
`dependabot/github_actions/…`. A *Selected branches: main* rule would block
every review. `Bot` has no such consumer, so it has the rule.

**The exposure that leaves.** `Fleet` is reachable from any branch here, so a
workflow altered on a branch and opened as a pull request would run with
`Fleet`'s secrets in scope. That is why `.github/` needs a human, and the
second reason the App key lives elsewhere: the credential that can merge
should not sit behind the same door as the one that can only spend money.

---

## What none of this is

Neither of these gives the fleet more say over the book. What agents may change
is decided by `docs/FLEET.md` and the rules in `agent-branches.yml` — the
protected set, the merge policy, `hold`. An identity changes who the work is
attributed to and which of GitHub's own doors are open. It does not change what
the fleet is allowed to decide.
