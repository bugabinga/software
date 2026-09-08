#import "/book/lib/prelude.typ": *

= The Pipeline

Placeholder content, written to exercise every part of the build. If it renders
correctly on the website and in the PDF, the pipeline is healthy.

== Prose, references and notes

A chapter is Typst markup: *bold*, _emphasis_, `inline code`, and links such as
#link("https://typst.app/docs/")[the Typst documentation]. Footnotes
work#footnote[And land at the end of the chapter on the web, at the foot of the
page in print.], as do cross-references to labelled figures like @fig-stages
and to other chapters.

#tip(title: "Writing loop")[
  `make serve` rebuilds on save and reloads the browser. `make check` runs the
  same gates that CI runs, so a green local run means a green pull request.
]

== Mathematics

Inline math like $sigma: A -> B$ sets in the middle of a sentence, and display
math gets its own block:

$ "typecheck" (Gamma, e) = tau quad <==> quad Gamma tack.r e : tau $

On the website this is MathML, rendered by the browser -- no JavaScript, no
webfont downloads. In the PDF it is set with New Computer Modern Math.

== Code

Fenced blocks are highlighted by Typst itself:

```typst
#let compose(f, g) = x => f(g(x))
```

Listings can also be quoted from real files under `code/`, by region, so the
book cannot drift out of step with code that actually compiles:

#snippet("/code/examples/types.rs", tag: "newtype")

The same file, a different region:

#snippet("/code/examples/types.rs", tag: "phantom")

#warning[
  A region that no longer exists fails the build rather than rendering empty.
]

== Figures and tables

#figure(
  caption: [The stages every build passes through.],
  table(
    columns: (auto, 1fr),
    align: (left, left),
    table.header([*Stage*], [*What it produces*]),
    [`typst`], [semantic HTML per chapter, and one PDF],
    [`build.py`], [the page shell, navigation and search index],
    [checks], [link, spelling and code-compilation failures],
    [publish], [a GitHub Pages deployment and a release asset],
  ),
) <fig-stages>

Images live in `book/assets/` and are included with `#figure(image(...))`.

== Appendix pointer

The full list of helpers available to a chapter is in
#xref("prelude-reference")[the prelude reference], which is how one chapter
points at another: `@labels` work inside a chapter, `#xref` works across
chapters, because each chapter is its own document on the website.
