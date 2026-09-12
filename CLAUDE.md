# Working in this repository

A book written in Typst, published as a website (GitHub Pages) and a PDF from
one source tree. `README.md` is the human entry point; `docs/AUTHORING.md` is
the guide for writing chapters. This file records what is not obvious from
reading the tree.

## Commands

```sh
make setup    # install the pinned Typst into .tools/ (needed once per machine)
make build    # website + PDF into dist/
make serve    # build, serve on :8000, rebuild and live-reload on save
make check    # every gate CI runs; run before pushing
```

`make setup` needs network access to `github.com/typst/typst/releases`. The
`.claude/settings.json` SessionStart hook runs it, so a fresh session should
already have a working `.tools/typst/typst`.

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
  export is experimental, so `.typst-version` is pinned; after upgrading it,
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
  in a list, and `make check` treats unexpected warnings as failures. Name
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

The workflows share one build definition in
`.github/actions/build-book/action.yml`:

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

Pinned tool versions: Typst in `.typst-version`, typos in `ci.yml`'s
`TYPOS_VERSION`. Actions are pinned to major versions and updated by
Dependabot.

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
It lives in `book/book.toml` and, as a heading, in `README.md` -- nothing else
hardcodes it. Propose a title when the notes support one; do not treat the
current string as a decision anybody made.

`99-prelude-reference.typ` is not a stub and not part of that outline: it is
living documentation of the prelude, and it stays until the same material
lands in `docs/AUTHORING.md`.

The book's shape is the fleet's to change. Notes arrive one at a time and any
of them can invalidate the current outline, so treat the chapter list as the
latest answer rather than a settled one.
