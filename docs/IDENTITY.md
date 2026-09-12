# Giving the fleet an identity

Two setup jobs that need a human, written out because both are ten minutes of
clicking that nothing in this repository can do for you. Everything else the
fleet needs has been engineered around; these two cannot be.

They are independent. The App is the one that matters — it unblocks work that
is stuck today. The signing key is provenance, and can wait.

---

## 1. The GitHub App — one app, and one is enough

**What it fixes, today, not hypothetically.** `agent-branches.yml` logs this
on every branch the fleet pushes:

> `agent/badges` is green but unmerged — no pull request exists, because this
> repository does not let Actions open them, and a direct merge commit is
> refused by the linear-history rule

Two settings closing on each other. Actions cannot open a pull request here,
and without a pull request the only merge available through the API is a merge
commit, which the `Main` ruleset forbids. Squash needs a pull request. So the
fleet can do work and can push it, and then it stops, forever, and files an
issue about it.

An App installation token is not `GITHUB_TOKEN`, so:

- it opens pull requests regardless of the "Allow GitHub Actions to create and
  approve pull requests" setting;
- **its pushes and pull requests trigger other workflows.** GitHub's rule is
  that "with the exception of `workflow_dispatch` and `repository_dispatch`,
  other `GITHUB_TOKEN`-triggered events do not create workflow runs at all",
  which is why an agent's branch arrives with no CI on it and why `fleet.yml`
  currently has to ask for a CI run by hand;
- everything it does is attributed to `fleet[bot]` rather than
  `github-actions[bot]`, which is the difference between an audit log that
  distinguishes the fleet from the plumbing and one that does not.

**One app is enough**, and more than one would be worse. The app is an
identity, not a capability: every workflow mints its own short-lived token
from it, scoped by that workflow's own `permissions:` block. Separate apps per
agent would mean separate private keys to rotate and separate installations to
keep in step, in exchange for a distinction that commit trailers already make
more precisely.

It costs nothing. GitHub Apps are free, on every plan.

### Doing it

1. <https://github.com/settings/apps/new>
2. **GitHub App name**: `bugabinga fleet` (it must be unique across GitHub; if
   it is taken, anything recognisable will do — the name shows up as
   `<name>[bot]` on everything it does).
3. **Homepage URL**: `https://github.com/bugabinga/software`
4. **Webhook**: untick **Active**. Nothing here listens for webhooks.
5. **Repository permissions** — set these six, leave the rest at *No access*:

   | Permission | Access | Why |
   | --- | --- | --- |
   | Contents | Read and write | Push branches, read the tree |
   | Pull requests | Read and write | Open, comment, merge |
   | Issues | Read and write | The task and tracking issues |
   | Actions | Read and write | Start CI on a pushed branch, read runs |
   | Checks | Read | Decide whether a branch is green |
   | Metadata | Read | Mandatory; GitHub ticks it for you |

6. **Where can this GitHub App be installed?** *Only on this account.*
7. **Create GitHub App.**
8. On the app's page: note the **App ID** (a number near the top).
9. Scroll to **Private keys** → **Generate a private key**. A `.pem` file
   downloads. This is the whole of the app's authority; it is shown once.
10. Left sidebar → **Install App** → install it on `bugabinga/software` only.
11. Store the two halves, and note that they go in **different places** —
    see *Where the credentials live* below for why.
    - Repository → Settings → Secrets and variables → Actions →
      **Variables** → New repository variable: `FLEET_APP_ID`, the number
      from step 8. It is a public identifier, not a secret; keeping it out of
      the secret store means it can be read in a log when something is wrong.
    - Same page → **Environments** → New environment named `Bot` →
      **Add environment secret**: `FLEET_APP_PRIVATE_KEY`, the **entire**
      contents of the `.pem`, `-----BEGIN`/`-----END` lines and newlines
      included. A multi-line secret is correct here; the earlier newline
      problem was a token that had to fit in one HTTP header, and this is not
      that.
    - On the `Bot` environment, set **Deployment branches** to
      *Selected branches* and add `main`. Nothing that needs this key runs
      from anywhere else, and the restriction is what stops a workflow
      modified on a pushed branch from reading it.

Then tell the operator session it is done. Wiring the workflows to
`actions/create-github-app-token` is a small change and not your job.

### What changes once it exists

- `agent-branches.yml` opens pull requests instead of filing issues that say
  it could not.
- Those pull requests get CI and `Fleet review` without `fleet.yml` having to
  dispatch CI by hand — that workaround can come back out.
- Green chores merge themselves again, by squash, satisfying linear history.
- The fleet appears in the audit log under its own name.

---

## 2. Commit signing, so the fleet's commits say **Verified**

Skip `use_commit_signing`. It is the obvious input and it is the wrong one
here: it commits through GitHub's API instead of the git CLI, and the action's
own security document says that route "cannot perform complex git operations".
Every agent in this fleet works by making a branch with git and pushing it, so
turning it on would take the CLI out from under the design in exchange for a
badge.

`ssh_signing_key` signs and leaves git alone. It needs a key that only you can
install, because the public half goes on your GitHub account.

### Doing it

1. Generate a keypair used for nothing else:

   ```sh
   ssh-keygen -t ed25519 -f ~/.ssh/fleet_signing -N "" -C "fleet commit signing"
   ```

2. <https://github.com/settings/ssh/new> — paste `~/.ssh/fleet_signing.pub`,
   and set **Key type** to **Signing Key**. Not *Authentication Key*; this is
   the step everyone gets wrong, and an authentication key silently fails to
   verify anything.
3. Repository → Settings → Environments → `Fleet` → **Add environment
   secret**: `FLEET_SSH_SIGNING_KEY`, the contents of the **private** file
   `~/.ssh/fleet_signing` — all of it, `-----BEGIN`/`-----END` lines included.
   `Fleet` and not `Bot`: only the two workflows that make commits need it,
   both already run there, and a signing key is authority over nothing.
4. Delete the private file from your machine afterwards if you like; it exists
   only to be pasted, and a new pair can be made in ten seconds.

Then the operator adds `ssh_signing_key` to the three fleet workflows.

### What it buys, honestly

Not much on its own, and it is worth being clear about that. Commits will read
**Verified** instead of **Unverified**. That proves a commit came from a run
holding the key rather than from anyone else with push access — which matters
if the fleet's branches ever start merging without a human reading them, and
matters very little while they do not. It is cheap, it is not urgent, and it
is a prerequisite for one day requiring signed commits on `main`.

---

## Where the credentials live, and why not all in one place

Three credentials, three different blast radii, and the deciding question is
what happens when you want to stop something.

| Credential | Where | Why there |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | `Fleet` environment | Buys model time. Only the three agent workflows need it, and they all name `Fleet`. |
| `FLEET_SSH_SIGNING_KEY` | `Fleet` environment | Same two consumers, and it grants nothing: it makes a commit say Verified. |
| `FLEET_APP_ID` | repository **variable** | Not a secret. A number on a public page. |
| `FLEET_APP_PRIVATE_KEY` | `Bot` environment, `main` only | Write access to the repository, in the identity that opens and merges pull requests. The highest authority here, and the one with a consumer that must not be gated. |

**Why the App key does not go in `Fleet`.** `agent-branches.yml` is the
workflow that needs it, and that workflow is plumbing: no model, no judgement,
it opens pull requests and merges green chores. Putting the key in `Fleet`
would force it to declare `environment: Fleet`, and from then on anything
protecting `Fleet` protects it too. The protection worth having on `Fleet` is
**required reviewers** — the real stop button, far better than deleting a
secret, because it pauses an agent run until you approve it. If the plumbing
shares that environment, pressing the stop button also stops pull requests
being opened and chores being merged, which is the opposite of what you want
while you are deciding whether an agent has gone wrong.

**Why `Fleet` cannot be locked to `main`.** It would be the obvious hardening,
and it does not work here. `Fleet review` runs on `pull_request`, and the
deployment records show those runs carrying the pull request's *head* branch
as their ref -- `agent/badges`, `agent/typst-0.15.1`,
`dependabot/github_actions/...`. A *Selected branches: main* rule on `Fleet`
would block every review. `Bot` has no such consumer, so it can have the rule,
and should.

**The exposure that leaves.** `Fleet` is reachable from any branch in this
repository, so a workflow altered on a branch and opened as a pull request
would run with `Fleet`'s secrets in scope. That is the reason `.github/` is in
the protected set and needs a human, and it is the second reason the App key
lives somewhere else: the credential that can merge should not sit behind the
same door as the credential that can only spend money.

## What neither of these is

Neither gives the fleet more power over the book. What the agents may change
is decided by `docs/FLEET.md` and the rules in `agent-branches.yml` — the
protected set, the merge policy, `hold`. An identity changes who the work is
attributed to and which of GitHub's own doors are open to it. It does not
change what the fleet is allowed to decide.
