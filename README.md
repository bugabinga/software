# A Book Written in Types

The source of a book written in [Typst](https://typst.app), published twice
from one tree: as a website and as a PDF.

- **Website** — GitHub Pages, rebuilt on every push to `main`.
- **PDF** — built alongside the site, linked from every page, and attached to
  every release.

The content is placeholder text for now; the pipeline around it is finished
and runs on every commit.

## Quick start

```sh
make setup    # install the pinned Typst into .tools/ (one-off)
make serve    # build, serve on http://127.0.0.1:8000, reload on save
```

Then edit anything under `book/` and the browser refreshes itself.

```sh
make          # list every target
make build    # website + PDF into dist/
make check    # everything CI checks: build, links, spelling, example code
```

The only tools required are Python 3.11+ and the Typst binary `make setup`
installs. There is no package manager, lockfile or `node_modules`.

## Writing

New chapter, in three steps:

1. Create `book/chapters/07-my-chapter.typ`, starting with

   ```typst
   #import "/book/lib/prelude.typ": *

   = My chapter
   ```

2. Add `"chapters/07-my-chapter.typ"` to a part in `book/book.toml`.
3. `make serve`.

The numeric prefix orders the file on disk; it is stripped from the URL, so
the chapter above is published at `/my-chapter/`. Reordering chapters does not
change their links.

[docs/AUTHORING.md](docs/AUTHORING.md) is the full guide: the helpers a
chapter can use, how cross-references work, and what the pipeline rejects.

## Layout

```
book/
  book.toml       metadata and chapter order -- the single source of truth
  book.typ        PDF entry point; needs no editing when chapters change
  chapters/       the book itself, one Typst file per chapter
  lib/            prelude (callouts, snippets, cross-references) and styling
  assets/         images
code/             example code the book quotes, type-checked by CI
site/
  templates/      the page shell for the website
  assets/         stylesheet, JavaScript, favicon
tools/
  build.py        the pipeline: Typst -> website, plus search index and PDF
  check_links.py  every internal link and anchor must resolve
  check_code.sh   type-checks code/
  install-typst.sh
  summary.py      the Markdown summary CI posts
.github/
  actions/build-book/   one build definition, shared by all three workflows
  workflows/            ci.yml, publish.yml, release.yml
```

## How the build works

1. Each chapter is compiled on its own to semantic HTML by Typst — real
   `<h2>`, `<figure>`, `<pre>`, and MathML for equations, so the site needs no
   JavaScript to render mathematics and no webfonts.
2. `tools/build.py` wraps each chapter in the page shell: navigation from
   `book.toml`, an outline of the chapter, previous/next links, an edit link,
   and a client-side search index.
3. `book/book.typ` compiles all chapters as one document for the PDF, which is
   where page numbers and full cross-referencing come from.
4. The gates: unexpected Typst warnings, broken internal links or anchors,
   misspellings, and example code that no longer compiles all fail the build.

## Publishing

Pushes to `main` publish the site to
<https://bugabinga.github.io/software/>. There is nothing to set up:
`publish.yml` builds the book and force-pushes it to the `gh-pages` branch as
a single commit, which needs no permission beyond the workflow token's own
and no Pages configuration. The deployment URL is passed into the build, so
canonical links, Open Graph tags and `sitemap.xml` are absolute.

Every pull request gets a full build with the site attached to the run as an
artifact, and a comment linking to it.

Tagging a release (`git tag v1.0 && git push --tags`) attaches the PDF and a
zip of the website to a GitHub release.

## Licence

The code in `tools/`, `site/` and `book/lib/` is under the terms in
[LICENSE](LICENSE). The book's text and figures are the author's; pick a
licence for the content before publishing and state it here.
