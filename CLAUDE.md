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
  New Computer Modern Math, DejaVu Sans Mono.
- A heading with `numbering: none` does not advance the chapter counter, which
  is what makes `numbered = false` parts work as front matter.
- Regex strings use Typst string escapes: write `"^[0-9]+"`, not `"^\d+"`.
- Do not set `display` on a `<math>` element in CSS. Its intrinsic
  `display: math` is what lays the expression out; overriding it stacks every
  atom vertically. Wide equations scroll via the wrapper `tools/build.py` adds.

## CI

Three workflows share one build definition in
`.github/actions/build-book/action.yml`:

- `ci.yml` -- build (strict), internal links, example code, spelling,
  outbound links; uploads the site as an artifact and comments a preview link
  on pull requests. The comment step is `continue-on-error` because pull
  requests from forks get a read-only token.
- `publish.yml` -- deploys `dist/` to GitHub Pages on pushes to `main`.
- `release.yml` -- on a `v*` tag, attaches the PDF and a zip of the site.

Pinned tool versions: Typst in `.typst-version`, typos in `ci.yml`'s
`TYPOS_VERSION`. Actions are pinned to major versions and updated by
Dependabot.

## Content

`book/chapters/` currently holds placeholder chapters that exercise every
feature of the pipeline (callouts, math, snippets from `code/`, figures,
tables, footnotes, cross-references). They are meant to be replaced by the
real book; keep `99-prelude-reference.typ` as living documentation of the
prelude, or fold it into `docs/AUTHORING.md` if you drop it.
