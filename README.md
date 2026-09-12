# A Book Written in Types

[![CI](https://github.com/bugabinga/software/actions/workflows/ci.yml/badge.svg)](https://github.com/bugabinga/software/actions/workflows/ci.yml)
[![Book](https://img.shields.io/endpoint?url=https%3A%2F%2Fbugabinga.github.io%2Fsoftware%2Fbadges%2Fprogress.json)](https://bugabinga.github.io/software/)
[![Typst](https://img.shields.io/endpoint?url=https%3A%2F%2Fbugabinga.github.io%2Fsoftware%2Fbadges%2Ftypst.json)](https://typst.app)
[![PDF](https://img.shields.io/badge/PDF-read-blue)](https://bugabinga.github.io/software/book.pdf)
[![License](https://img.shields.io/github/license/bugabinga/software)](LICENSE)

[![The book's cover card](https://bugabinga.github.io/software/social-card.png)](https://bugabinga.github.io/software/)

> **The title is a placeholder.** `A Book Written in Types` was invented by
> the build so that something could be rendered. It has not been chosen.

One programmer's thoughts about software. There is no overarching thesis, and
[the preface](book/chapters/00-preface.typ) says that is a decision rather
than an omission: what holds the chapters together is a shared vocabulary and
a foundation meant to be revised when later material strains it.

**Part I — Foundations.** Machine and program · Information and entropy ·
Knowledge · Software and its forms · Operating systems

**Part II — Craft.** Learning the craft · Beauty and mechanical sympathy ·
The cycle and its costs · The practices · Intent and product engineering

Then four appendices — the questions still open, agents, citations, a
glossary — and a fifth that is not part of the book: a live reference for the
Typst prelude, which stays until the same material lands in
[docs/AUTHORING.md](docs/AUTHORING.md).

### Read it

|          |                                                  |
| -------- | ------------------------------------------------ |
| Web      | <https://bugabinga.github.io/software/>          |
| PDF      | <https://bugabinga.github.io/software/book.pdf>  |
| EPUB     | <https://bugabinga.github.io/software/book.epub> |
| One page | <https://bugabinga.github.io/software/book.html> |

Two pages on the site are not the book, and are listed at the foot of its
front page: the [skill generator](https://bugabinga.github.io/software/skill/)
and the [fleet report](https://bugabinga.github.io/software/fleet/).

**Every chapter is a stub.** Each carries its title, one paragraph of what it
will argue, and a comment naming the lines of the author's notes it came from.
The word count in the badge is those paragraphs; none of the book is written
yet.

---

The rest of this file is about building it.

## Quick start

```sh
curl -fsSL https://mise.run | sh   # mise itself, if you do not have it
mise install       # the pinned toolchain, once per machine
mise run serve     # build, serve on http://127.0.0.1:8000, reload on save
```

Then edit anything under `book/` and the browser refreshes itself.

```sh
mise tasks         # list everything
mise run build     # website + PDF into dist/
mise run check     # everything CI checks
```

The only tools required are Python 3.11+ and [mise], which installs the
pinned Typst binary and everything else from `mise.toml`. There is no package
manager, lockfile or `node_modules`.

[mise]: https://mise.jdx.dev

## Writing

New chapter, in three steps:

1. Create `book/chapters/07-my-chapter.typ`, starting with

   ```typst
   #import "/book/lib/prelude.typ": *

   = My chapter
   ```

2. Add `"chapters/07-my-chapter.typ"` to a part in `book/book.toml`.
3. `mise run serve`.

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
  bootstrap-mise.sh  installs mise and the pinned toolchain
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
