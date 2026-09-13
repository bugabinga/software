# Working in this repository

A book written in Typst, published as a website (GitHub Pages) and a PDF from
one source tree. `README.md` is the human entry point; `docs/AUTHORING.md` is
the guide for writing chapters. This file records what is not obvious from
reading the tree.

## Commands

```sh
mise install       # the pinned toolchain, once per machine
mise run build     # website + PDF into dist/
mise run serve     # build, serve on :8000, rebuild and live-reload on save
mise run check     # every gate CI runs; run before pushing
mise tasks         # everything there is
```

There is one way to run each of those, deliberately. The tasks live in
`mise.toml` and CI calls the same ones -- a green `mise run check` locally is
a green pull request, because it is not a second definition that agrees by
habit.

`mise install` needs network access to the tools' release pages. The
`.claude/settings.json` SessionStart hook runs `tools/bootstrap-mise.sh`,
which installs mise first if the machine has none, so a fresh session already
has the toolchain.

**Zero warnings.** Every gate runs at full severity and a warning fails the
build like an error does. Suppress only where the tool is wrong about this
repository, only at the line or the file it is wrong about, and always with
the reason written next to it -- `# noqa: RUF001 - an en dash is the right
character in a range`, `# shellcheck disable=SC2016  # backticks are markdown
here`, an `overrides` entry in `biome.jsonc`. A blanket severity filter or a
project-wide `off` hides the next finding too, which is the failure this rule
exists to prevent. `ruff.toml` states how many findings its one remaining
exception covers; recount before adding to it.

**The Python is linted and type-checked, strictly.** `ruff check` with a wide
selection (`ruff.toml` records why each switched-off rule is off) and `ty`
(`ty.toml`). Both are gates. Do not silence a finding with a bare `noqa`: give
it a code and a reason on the same line, the way the existing ones do, so the
next reader can tell a deliberate exception from a shrug.

**Formatting is mandatory, and it is never yours to decide.** `mise run
format` before you push; `mise run check` fails if you did not. One formatter
per language and no language without one -- typstyle for `.typ`, ruff for
`.py`, biome for `.js`/`.json`/`.css`, dprint for `.md`/`.toml`/`.yml`, shfmt
for `.sh`. All on their defaults. The reason is the reader: a diff that mixes
a change with a reflow costs them the ability to see the change, and the
author reads these on a phone. Do not argue with a formatter's output and do
not configure around it; where its shape and the file's fight, change the file
-- `ruff.toml`'s rule list is one code per line because that is what the TOML
formatter wanted, and it reads no worse.

`notes/` is excluded, like everywhere else. `book/` is typstyle's.

## Architecture, and what must stay true

- `book/book.toml` is the single source of truth for metadata and chapter
  order. It is read by both `book/book.typ` (via Typst's `toml()`) and
  `tools/build.py`, which is what keeps the PDF and the website in agreement.
  Do not add a second list of chapters anywhere.
- A chapter's URL is its filename with the numeric prefix stripped. The rule
  is implemented twice -- `slug-of` in `book/lib/prelude.typ` and `slug_of` in
  `tools/build.py` -- and the two must match.
- `book/lib/styles.typ` exports `web` and `paged`. Each is applied **exactly
  once** by an entry point: `paged` by `book/book.typ`, `web` by the
  per-chapter entry files `tools/build.py` generates into `build/entry/`. Do
  not apply a template from inside a chapter: Typst would then apply the show
  rules twice (once from the chapter's scope, once from the entry's) and
  transformations such as numbering prefixes would double.
- Chapters are compiled **separately** for the web, deliberately: Typst
  collects footnotes at the end of a document, so one document per chapter is
  what puts each chapter's footnotes on its own page. The cost is that Typst
  `@label` references cannot cross chapters, which is what `#xref` in the
  prelude is for.
- `tools/build.py` owns everything web-shaped: the page shell, navigation,
  heading ids, the search index, the sitemap. Typst owns the content. Resist
  moving web concerns into the Typst templates -- `html.elem` in a chapter
  helper is fine, generating the page shell from Typst is not.
- The pipeline asserts the shape of Typst's HTML export (`<head>`/`<body>`,
  headings shifted down one level, `<math display="block">`). Typst's HTML
  export is experimental, so the Typst version is pinned in `mise.toml`;
  after upgrading it,
  build and look at a chapter before trusting the output.

## Typst notes worth not rediscovering

- `target()` returns `"html"` or `"paged"`. `--features html` is passed for
  both outputs so `html.elem` resolves in helpers that branch on it.
- `set` rules cannot go inside a `context` block, which is why per-output
  styling is two functions rather than one function with a branch.
- Method chains must not be broken across lines outside parentheses; Typst
  ends the statement at the newline and reports a confusing parse error.
- Two adjacent `page(..)` calls leave a blank leaf between them. Use a scoped
  `set page(..)` in a block instead (see `book/book.typ`).
- Typst warns about every font family it cannot resolve, including fallbacks
  in a list, and `mise run check` treats unexpected warnings as failures. Name
  only families that exist. Embedded: Libertinus Serif, New Computer Modern,
  New Computer Modern Math, DejaVu Sans Mono. Bundled in `book/fonts/` and
  reached via `--font-path book/fonts`, which every invocation passes: Noto
  Color Emoji.
- A **missing glyph is not a warning**. Emoji rendered as empty boxes in the
  PDF for as long as no emoji font was bundled, while looking correct on the
  website, where the reader's own system supplies one. Nothing in the gates
  catches that class of fault; the only defence is that a named fallback
  family which stops resolving does warn, and so fails the build.
- A heading with `numbering: none` does not advance the chapter counter, which
  is what makes `numbered = false` parts work as front matter.
- Regex strings use Typst string escapes: write `"^[0-9]+"`, not `"^\d+"`.
- Do not set `display` on a `<math>` element in CSS. Its intrinsic
  `display: math` is what lays the expression out; overriding it stacks every
  atom vertically. Wide equations scroll via the wrapper `tools/build.py` adds.

## CI

Fifteen workflows; `docs/FLEET.md` is the roster. The four that need a built
book -- `ci.yml`, `maintenance.yml`, `publish.yml`, `release.yml` -- share one
definition in `.github/actions/build-book/action.yml` rather than four copies
of the same install-and-compile. The four worth knowing from here are not the
same four:

- `ci.yml` -- build (strict), internal links, example code, spelling,
  outbound links; uploads the site as an artifact and comments a preview link
  on pull requests. The comment step is `continue-on-error` because pull
  requests from forks get a read-only token.
- `publish.yml` -- publishes on pushes to `main` by force-pushing `dist/` to
  the `gh-pages` branch. Not via `actions/deploy-pages`: creating a Pages
  site is privileged and the workflow token cannot do it, while pushing a
  branch needs only `contents: write`. `gh-pages` is generated output -- one
  orphan commit per deployment, never edited by hand.
- `agent-branches.yml` -- the fleet pushes branches and nothing else. This
  opens their pull requests where the repository allows Actions to, merges
  green chores either way, and turns anything needing review into one issue
  with a compare link. Everything it does uses the workflow token only.
- `release.yml` -- on a `v*` tag, attaches the PDF and a zip of the site.

Every pinned tool version lives in `mise.toml` -- Typst, typos, gh,
typstyle, wrangler -- read by `tools/pinned.py`, so the install scripts, the
build's version badge and the maintenance sweep all agree. `mise install`
works from it; nothing requires mise, because the scripts parse the file
themselves.

Dependabot has no mise ecosystem, so it covers only the Actions, which are
pinned to commits. `maintenance.yml` reads every pin in `mise.toml` on
Mondays and reports what is behind -- adding a tool to the manifest is
enough to get it watched.

## Who you are

Two kinds of session work in this repository, and they have different jobs.

- **A fleet agent or a scheduled fleet run.** Your brief is your definition in
  `.claude/agents/`, plus this file and `docs/FLEET.md`. That is the whole of
  it. `docs/OPERATOR.md` is not addressed to you: do not read it as your
  instructions, and do not take on the work it describes.
- **The operator** -- the interactive session the author talks to. Your full
  brief is `docs/OPERATOR.md`, printed into your context at session start by
  `tools/operator-brief.sh`. Read it if you have not seen it.

  The core of it is repeated here because this file is re-injected after
  compaction and that one is not, so this is what survives a long session:

  1. **You run the fleet. You do not write the book.** Chapters, prose,
     stubs, structure: dispatch the agent whose beat it is. Offering to write
     it yourself is this role's characteristic failure.
  2. **The fleet decides about the book**; you decide about the fleet. The
     author controls the book by controlling the fleet, so a question about
     the book's content or shape is answered by improving an agent's brief,
     not by asking the author to adjudicate.
  3. **Review before relaying.** An agent's account of its own work is not
     evidence. Read the diff, re-run the gates, check its citations.
  4. **The fleet runs in CI.** Dispatching from a session is for emergencies
     and for what the author asks for in the moment.
  5. **The author is often on a phone.** A shell script is not a deliverable.
     Engineer around what the environment denies; where something genuinely
     cannot be, reduce it to one paste.
  6. **A fleet rule is not shipped until it has been checked against the
     situations that actually exist in the repository.**

## How the fleet writes

Every worker here, the operator included. This is a house style, not a
preference, because the author reads all of it on a phone.

**Terse.** The diff is the record. A commit body that narrates the diff makes
the reader read the change twice. Say what the diff cannot: why, what you
verified, what you left alone. Three lines is usually enough and five is
usually too many.

**Link, do not restate.** `docs/FLEET.md`, `notes/2026-09-11-session-01.md:140`,
a run URL, a pull request number. A pointer to the source of truth outlives a
paraphrase of it and cannot drift from it. If you find yourself explaining
what a file says, link the file.

**The exception is code comments.** A comment explaining why something is the
way it is earns its length, because the next reader has no other way to
recover the reasoning and the alternative is rediscovering it. That is the
opposite case from a report, which the reader is holding the artefact for
already. Long comments, short reports.

**A report is three things**: what changed, what you checked, what you
deliberately did not do. Nothing else. No preamble, no restatement of the
task, no summary of your summary, no "I have now".

**One claim per sentence, and no adjectives you cannot defend.** "Comprehensive"
and "robust" are how a report sounds when it has nothing to say.

### Three registers, because there are three readers

A commit message, a pull request and a comment are not one text at three
lengths. Different readers, at different moments, holding different things.
Writing one and pasting it into the others is the characteristic failure, and
it happens because it feels efficient.

**Commit — what and why, technical.** The reader is in `git log` or `git
blame`, months from now, with the diff already in front of them, asking why
this line is like this. Never narrate the diff. Say what it cannot: the
constraint you hit, the alternative you rejected and why, the fact that will
have been forgotten. Unsentimental, no audience. One commit, one concern.

**Pull request — the story, high level.** The reader is deciding whether to
accept this, now, with no context. What hurt, what you did about it, what is
different afterwards. Written for someone who has not read the commits and may
not. **Never a copy of the commit body** — if the two are the same text, one
of them is wrong. Link the commits; that is what they are for.

**Comment — terse, context-aware.** The reader is in a conversation already in
progress and has the thread. No preamble, no restating what is above, no
summarising the exchange. Contribute the next thing and stop. This is the only
one of the three _addressed to someone_, so it may be short in a way the
others may not: a sentence is often the whole comment.

## The fleet

`docs/FLEET.md` is the roster: which workflows run when, which agents exist
(`.claude/agents/`), which procedures they follow (`.claude/skills/`), the
merge policy, and how to stop any of it. Read it before doing maintenance
work, and keep it accurate when the fleet changes -- a scheduled session that
fires next week has nothing else to go on.

Two rules that no worker overrides: `main` is never committed to directly,
and `notes/` is never edited.

## Content

`book/chapters/` holds the outline the author's notes fixed: a preface, five
Foundations chapters, five Craft chapters, and four appendices. Each is a stub
-- a source comment naming the note lines it came from, the title, and one
paragraph of what the chapter will argue. None of them is written yet.

The **title is a placeholder**. `A Book Written in Types` was invented by the
pipeline so that something could be rendered; the author has not chosen one.
It is written out in three places and nowhere else: `book/book.toml`, the
heading of `README.md`, and this paragraph. Propose a title when the notes support one; do not treat the
current string as a decision anybody made.

`99-prelude-reference.typ` is not a stub and not part of that outline: it is
living documentation of the prelude, and it stays until the same material
lands in `docs/AUTHORING.md`.

The book's shape is the fleet's to change. Notes arrive one at a time and any
of them can invalidate the current outline, so treat the chapter list as the
latest answer rather than a settled one.
