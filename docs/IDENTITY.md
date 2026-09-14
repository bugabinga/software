# Giving the fleet an identity

Two setup jobs that need a human. They are the only two, and the point of doing
them the way described here is that **you never come back**.

An earlier version of this file listed the exact permissions the fleet needed
today. That was a mistake: it made the app's grant a per-feature decision, so
every improvement to the fleet would have meant another trip to a settings page.
The grant is not the policy. Get it right once, wide enough to never block a
change, bounded where it actually matters, and do the narrowing in the
repository where it can be read, reviewed and changed by a pull request.

---

## The principle

**The app may change the rules, and only through a diff.**

An earlier version of this document said it may never change them at all. That
was the right instinct in the wrong place: an agent that can rewrite the
settings from a web page is supervised by nothing, but an agent that cannot fix
the rule blocking it stays blocked, and every week of this repository's life has
been somebody unblocking it by hand. What makes the difference is not whether
the app holds the permission but whether the change is legible: `repo.toml` is
the settings, a pull request is how they change, and `settings.yml` is the only
thing that writes them.

Four layers, and only the first is on a web page:

| Layer                                           | Where                                     | Who changes it |
| ----------------------------------------------- | ----------------------------------------- | -------------- |
| **Ceiling** — what the app _could_ ever do      | GitHub App settings                       | you, once      |
| **Repository settings** — the rules themselves  | `repo.toml`                               | a pull request |
| **Per workflow** — what a given workflow may do | `permissions:` in the workflow            | a pull request |
| **Per token** — what one step may do            | `permission-*` inputs on the token action | a pull request |

Nothing the fleet grows into needs the first layer touched again, because the
ceiling already covers everything a book pipeline can want. Everything below it
lives in the repository, is diffable, and is subject to the same review as any
other change.

---

## 1. The GitHub App

**What it fixes today.** `agent-branches.yml` currently logs this on every
branch the fleet pushes:

> `agent/badges` is green but unmerged — no pull request exists, because this
> repository does not let Actions open them, and a direct merge commit is
> refused by the linear-history rule

Two settings closing on each other: Actions cannot open a pull request here, and
without one the only merge the API offers is a merge commit, which the `Main`
ruleset forbids. Squash needs a pull request. So the fleet works, and pushes,
and then stops forever and files an issue about it.

An App installation token is not `GITHUB_TOKEN`, so it opens pull requests
regardless of that setting; its pushes trigger workflows (a `GITHUB_TOKEN` push
triggers nothing, which is why an agent's branch arrives with no CI on it); and
its work is attributed to the app rather than to `github-actions[bot]`.

**One app is enough**, and more than one would be worse. The app is an identity,
not a capability: every workflow mints its own short-lived token from it, scoped
by its own `permissions:` block. Separate apps per agent would mean separate
keys to rotate for a distinction that commit trailers make better. It costs
nothing, on every plan.

### Permissions

**Every repository permission, and no organization permission.** That is the
whole of it, and it is deliberate: the app manages the author's repositories and
nobody can predict what the fleet will need next, so a per-feature grant means
another trip to a settings page for every improvement.

One of them has to be **Read and write**, not Read: **Administration**. It is
what `repo_state.py` writes the repository object, the topics, the Actions
permission and the ruleset with, and `settings.yml` asks for it by name, so at
Read the token request is refused with a 422 before anything is applied. Run
34695708756 (2026-09-12) read it at Read; run 34791533048 minted the token and
applied all five settings, so it is Read and write now. If a `Settings` run ever
dies at the token step, that is the first thing to look at -- the annotation
prints what it asked for against what the installation holds.

An earlier version of this file listed each permission and forbade
Administration, Secrets, Variables and Environments, on the argument that an
agent holding them could widen its own authority. The argument was right and the
remedy was in the wrong place. What replaced it is `repo.toml`: the rules the
app may change are declared in a file, changed by a pull request, applied by
`settings.yml`, and read back by `mise run check-settings`, which
`mise run
check` runs. The ceiling moved from a settings page with no history to
a diff with one.

So the app can change the rules `repo.toml` declares, through a diff and nothing
else. That is the principle above, and it is the point.

**Three grants sit outside that file's reach**, and they are the three the
earlier version of this document forbade by name: Secrets, Variables and
Environments. `repo_state.py` reads the repository object, the Actions
permissions and the rulesets, and nothing else -- so an App holding Environments
at write could change the `Fleet` and `Bot` protection rules, which is the
second place the fleet can be paused (`docs/FLEET.md`), and no diff and no check
would say so. Nothing in the fleet uses those three today. What bounds them is
that every workflow mints its own token by name, and `settings.yml`'s asks for
administration and metadata: a step that wanted a secret would have to say so in
a diff. That is weaker than the ruleset's bound, and it is the honest
description of it.

### Doing it

1. <https://github.com/settings/apps/new>
2. **Name**: anything recognisable; it appears as `<name>[bot]` on everything it
   does.
3. **Homepage URL**: the repository's URL.
4. **Webhook**: untick **Active**.
5. **Repository permissions**: as above.
6. **Where can this be installed?** _Only on this account._
7. Create it, then note the **App ID**.
8. **Private keys** → **Generate a private key**. A `.pem` downloads; it is
   shown once and is the whole of the app's authority.
9. **Install App** → this repository only.
10. Store the two halves — they go in different places, see below:
    - Settings → Secrets and variables → Actions → **Variables** →
      `FLEET_APP_ID`, the number. Not a secret: it is a public identifier, and
      hiding it only means it is masked out of the log at the moment somebody is
      reading one.
    - Settings → **Environments** → new environment `Bot` → **Add environment
      secret** → `FLEET_APP_PRIVATE_KEY`, the **entire** `.pem` including the
      `-----BEGIN`/`-----END` lines. Multi-line is correct here; the earlier
      newline problem was a token that had to fit in one HTTP header.
    - On `Bot`, set **Deployment branches** to _Selected branches_ → `main`.

Then say so. Wiring the workflows is a pull request, not your job.

### Checking it

`repo.toml` and `tools/repo_state.py`. The file says what the repository is
configured to be; `mise run check-settings` reads it back, wherever a credential
is held, and `mise run check` runs it. `actions/permissions/workflow` needs
administration, so that section reads unread everywhere but the apply. There is
no separate check of the grant, because `repo.toml` is the boundary now -- with
the one exception above, which the `Settings` run reports for itself.

---

## 2. Commit signing

Optional, not urgent, and worth being honest about: it makes the fleet's commits
read **Verified** instead of **Unverified**. That matters if the fleet's
branches ever merge without a human reading them, and very little while they do
not. It is a prerequisite for one day requiring signed commits on `main`.

Skip `use_commit_signing`, which is the obvious input and the wrong one: it
commits through GitHub's API instead of the git CLI, and the action's own
security document says that route "cannot perform complex git operations". Every
agent here works by making a branch with git and pushing it. `ssh_signing_key`
signs and leaves git alone.

1. `ssh-keygen -t ed25519 -f ~/.ssh/fleet_signing -N "" -C "fleet signing"`
2. <https://github.com/settings/ssh/new> — paste `fleet_signing.pub`, and set
   **Key type** to **Signing Key**. Not _Authentication Key_: that one signs
   nothing and fails silently.
3. Settings → Environments → `Fleet` → **Add environment secret** →
   `FLEET_SSH_SIGNING_KEY`, the contents of the **private** file
   `~/.ssh/fleet_signing`. The private half; the public half went to GitHub in
   step 2.

---

## Where the credentials live

| Credential                | Where                          | Why there                                                |
| ------------------------- | ------------------------------ | -------------------------------------------------------- |
| `CLAUDE_CODE_OAUTH_TOKEN` | `Fleet` environment            | Buys model time. Only the three agent workflows need it. |
| `FLEET_SSH_SIGNING_KEY`   | `Fleet` environment            | Same consumers, and it grants nothing.                   |
| `FLEET_APP_ID`            | repository variable            | Not a secret.                                            |
| `FLEET_APP_PRIVATE_KEY`   | `Bot` environment, `main` only | Write access to the repository.                          |

**Why the App key is not in `Fleet`.** The workflow that needs it,
`agent-branches.yml`, is plumbing: no model, no judgement, it opens pull
requests and merges green chores. Sharing `Fleet` would force it to declare that
environment, and then anything protecting `Fleet` protects it too — including
the required-reviewers rule that is the real stop button for a misbehaving
agent. Pressing that button would also stop pull requests being opened, which is
the opposite of what you want while deciding whether an agent has gone wrong.

**Why `Fleet` cannot be locked to `main`.** It looks like obvious hardening and
it does not work: `Fleet review` runs on `pull_request`, and its deployment
records carry the pull request's head branch as the ref — `agent/badges`,
`dependabot/github_actions/…`. A _Selected branches: main_ rule would block
every review. `Bot` has no such consumer, so it has the rule.

**The exposure that leaves.** `Fleet` is reachable from any branch here, so a
workflow altered on a branch and opened as a pull request would run with
`Fleet`'s secrets in scope. That is why `.github/` needs a human, and the second
reason the App key lives elsewhere: the credential that can merge should not sit
behind the same door as the one that can only spend money.

---

## What none of this is

Neither of these gives the fleet more say over the book. What agents may change
is decided by `docs/FLEET.md` and the rules in `agent-branches.yml` — the
protected set, the merge policy, `hold`. An identity changes who the work is
attributed to and which of GitHub's own doors are open. It does not change what
the fleet is allowed to decide.
