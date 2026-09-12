// Not from notes: living documentation of the prelude, not part of the
// outline the author's notes fixed. It stays until the same material
// lands in docs/AUTHORING.md. See CLAUDE.md.

#import "/book/lib/prelude.typ": *

= Prelude reference

Everything a chapter can use after `#import "/book/lib/prelude.typ": *`, with
its output shown inline. The source of this chapter is the copy-paste source
for each helper.

== Callouts

`#note[...]`, `#tip[...]`, `#warning[...]` and `#caution[...]` take an optional
`title:`; pass `title: ""` to drop the heading entirely.

#note[The default heading is the callout's name.]

#tip(title: "Custom heading")[Any string works as a title.]

#warning(title: "")[A callout with no heading.]

#caution[For anything that loses data or money.]

== Defined terms

`#term[...]` marks the place where the book defines a word: a #term[functor]
becomes a `<dfn>` on the web and bold italic in print, so a glossary can be
generated from the same markup later.

== Output-specific content

`#web-only[...]` and `#print-only[...]` include content in one output only.

#web-only[This sentence only exists on the website.]

#print-only[This sentence only exists in the PDF.]

== Code from real files

`#snippet(path, tag: none, lang: none)` reads a file under `code/` and quotes
one marked region of it. Regions are delimited by `[name]` and `[/name]`
inside comments, are dedented, and must exist:

```typst
#snippet("/code/examples/types.rs", tag: "newtype")
```

== Everything else

The rest is plain Typst: headings, lists, `#figure`, `#table`, `#image`,
`#link`, `@labels`, `#footnote`, and math. The
#link("https://typst.app/docs/reference/")[Typst reference] applies unchanged.
