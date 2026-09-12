# Writing the book

Everything you need to know to add to the book, and the few places where the
pipeline has opinions.

## The loop

```sh
mise run serve
```

Builds the site, serves it on <http://127.0.0.1:8000>, and rebuilds on every
save; the page you are looking at reloads itself. Typst compiles a chapter in
under a tenth of a second, so the loop feels immediate.

For the printed shape of a single chapter, watch the PDF instead:

```sh
.tools/typst/typst watch --root . --features html --input only=03- \
  book/book.typ /tmp/chapter.pdf
```

`--input only=<substring>` builds only the chapters whose path contains the
substring, which is why chapter files carry a numeric prefix.

Before opening a pull request:

```sh
mise run check
```

which is exactly what CI runs.

## Adding a chapter

1. `book/chapters/07-my-chapter.typ`:

   ```typst
   #import "/book/lib/prelude.typ": *

   = My chapter

   The first paragraph is used as the page description in search results and
   link previews, so make it a sentence about the chapter.
   ```

2. Add the path to the right part in `book/book.toml`:

   ```toml
   [[part]]
   title = "Part II: Practice"
   numbered = true
   chapters = [
     "chapters/06-something.typ",
     "chapters/07-my-chapter.typ",
   ]
   ```

The level-one heading is the chapter title everywhere: the sidebar, the
contents page, the PDF outline, the `<title>` tag. There must be exactly one
per chapter, and it must come first.

`numbered = false` marks a part as front or back matter: its chapters get no
chapter number and do not advance the numbering of the rest.

## What a chapter can use

Plain Typst, plus the prelude. `book/chapters/99-prelude-reference.typ` is a
live example of every helper -- read it rendered, and copy from its source.

| Helper | What it does |
| --- | --- |
| `#note[..]` `#tip[..]` `#warning[..]` `#caution[..]` | Callouts. Optional `title:`; `title: ""` for no heading. |
| `#term[..]` | Marks where the book defines a word (`<dfn>` on the web). |
| `#snippet(path, tag: .., lang: ..)` | Quotes a region of a real file under `code/`. |
| `#xref("slug", anchor: ..)[..]` | Links to another chapter. |
| `#web-only[..]` `#print-only[..]` | Content for one output only. |
| `#slug-of(path)` | The URL a chapter file is published under. |

Anything else is ordinary Typst: `#figure`, `#table`, `#image`, `#footnote`,
lists, math, `@labels`. The
[Typst reference](https://typst.app/docs/reference/) applies unchanged.

### Mathematics

Write it as normal Typst. On the website it becomes MathML, which every
current browser renders natively; in the PDF it is set in New Computer Modern
Math. Nothing to configure, and no JavaScript in the page.

### Code

Short listings can be fenced inline:

````typst
```rust
fn main() {}
```
````

Anything you want a compiler to keep honest goes in `code/` and is quoted with
`#snippet` -- see [code/README.md](../code/README.md). `mise run check-code`
type-checks those files, so a listing cannot rot silently.

### Tables

Mark header rows with `table.header`, not by styling the first row:

```typst
#figure(
  caption: [What each stage produces.],
  table(
    columns: 2,
    table.header([Stage], [Output]),
    [`typst`], [HTML and a PDF],
  ),
) <fig-stages>
```

That is what makes the website emit a real `<thead>`, which is both how the
header gets styled and how a screen reader announces the table.

### Cross-references

Inside a chapter, use Typst's own references: label a figure or heading and
point at it.

```typst
#figure(..., caption: [..]) <fig-stages>
As @fig-stages shows, ...
```

Across chapters, use `#xref`, because each chapter is a separate document on
the website:

```typst
See #xref("knowledge")[the chapter on knowledge].
See #xref("prelude-reference", anchor: "callouts")[the callouts].
```

On the web that is a relative link; in the PDF it becomes a link plus the page
number. A Typst `@label` that points into another chapter fails the web build
with "label does not exist" -- that is the reminder to use `#xref`.

Heading ids are generated from heading text (`## Figures and tables` becomes
`#figures-and-tables`), so `anchor:` values are predictable. Rewording a
heading changes its id and breaks links to it; the link checker catches that
on the next build.

## What the pipeline rejects

`mise run check` (and CI) fails on:

- a Typst error, and on any Typst warning that is not the known
  "html export is under active development" notice;
- a broken internal link or a `#fragment` that does not exist in the page it
  points at;
- a misspelling, per `.typos.toml`;
- an outbound link that does not resolve (CI only, with retries, per
  `lychee.toml`);
- example code under `code/` that no longer compiles;
- a chapter listed in `book.toml` that does not exist, two chapters that would
  publish at the same URL, or a chapter without a level-one heading.

To let a word past the spell check, add it to `.typos.toml` rather than
switching the check off. To let a URL past the link check, add it to
`lychee.toml`.

## Styling

Two places, deliberately separate:

- `site/assets/book.css` -- the website. Design tokens are CSS custom
  properties at the top, with a dark palette below them.
- `book/lib/theme.typ` and `book/lib/styles.typ` -- the PDF: page size,
  margins, running heads, fonts.

`styles.typ` exports one function per output (`web` and `paged`), each applied
exactly once by an entry point, so no show rule is ever applied twice. Helpers
that must differ per output branch on `target()` inside `book/lib/prelude.typ`.

The page shell is `site/templates/page.html`; `{{placeholders}}` are filled by
`tools/build.py`, which fails loudly on an unknown one.

## Fonts

The PDF uses only fonts Typst embeds (Libertinus Serif, New Computer Modern
Math, DejaVu Sans Mono) and builds with `--ignore-system-fonts`, so it renders
identically on every machine. To use another font, put the file in
`book/fonts/`, add `--font-path book/fonts` to the Typst calls in
`tools/build.py`, and name it in `book/lib/theme.typ`. List only families that
actually resolve: Typst warns about unknown families, and `mise run check` treats
warnings as failures.

The website uses system font stacks, so it loads no webfonts at all.

## Known trade-offs

- **Typst's HTML export is experimental.** That is why the Typst pin in `mise.toml` is
  pinned and the pipeline asserts the shape of the exported document: if a
  Typst upgrade changes the markup, the build says so instead of publishing
  something broken. Upgrade deliberately, then read a chapter.
- **Syntax colours come from Typst** and are chosen for paper. In dark mode
  the stylesheet lifts them with a CSS filter rather than shipping a second
  highlighting theme. For exact control, set a `.tmTheme` via
  `#set raw(theme: ..)` in `book/lib/styles.typ`.
- **Images are inlined** into the HTML as data URIs by Typst's export. Keep
  them small; prefer SVG.
- **Footnotes are per chapter**, collected at the end of each web page, which
  is why chapters are compiled separately rather than as one long document.
