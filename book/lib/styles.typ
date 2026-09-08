// Output-specific styling, applied exactly once by an entry point:
// `paged` by `book/book.typ` (the PDF), `web` by the per-chapter entries
// `tools/build.py` generates (the website).
//
// Splitting them this way means no show rule is ever applied twice, and the
// web build stays deliberately thin: layout for the site lives in
// `site/assets/book.css`, not here.

#import "theme.typ"

/// Styling shared by both outputs. Semantic only -- anything visual belongs in
/// `paged` or in the stylesheet.
#let common(manifest, body) = {
  set text(lang: manifest.book.at("language", default: "en"))
  set par(justify: false)
  show link: it => it
  body
}

/// The website. Typst emits semantic HTML (`<h2>`, `<figure>`, `<pre>`,
/// MathML), `tools/build.py` wraps it in the page shell, and the stylesheet
/// does the rest.
#let web(manifest, body) = {
  show: common.with(manifest)
  set heading(numbering: none)
  body
}

/// The PDF: page geometry, running heads, and print typography.
#let paged(manifest, body) = {
  let meta = manifest.book

  set document(
    title: meta.title,
    author: meta.at("authors", default: ()),
    description: meta.at("description", default: ""),
  )

  set page(
    width: 16cm,
    height: 24cm,
    margin: theme.page-margin,
    numbering: "1",
    header: context {
      // Running head: the current chapter, suppressed on chapter openings.
      let here-page = here().page()
      let starts = query(heading.where(level: 1))
      let opening = starts.any(h => h.location().page() == here-page)
      if opening { return }

      let earlier = starts.filter(h => h.location().page() <= here-page)
      let current = earlier.at(-1, default: none)
      if current == none { return }

      set text(size: 8.5pt, fill: theme.muted)
      grid(
        columns: (1fr, auto),
        align: (left, right),
        emph(current.body),
        meta.title,
      )
      v(-6pt)
      line(length: 100%, stroke: 0.4pt + theme.rule)
    },
  )

  set text(font: theme.serif, size: theme.body-size)
  set par(justify: true, leading: 0.68em, spacing: 0.9em)
  show: common.with(manifest)

  set heading(numbering: "1.1")
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    block(above: 1.4cm, below: 0.9cm, {
      set text(size: 20pt, weight: "bold")
      if it.numbering != none {
        block(
          below: 6pt,
          text(size: 11pt, weight: "regular", fill: theme.muted, [Chapter #counter(heading).display("1")]),
        )
      }
      it.body
    })
  }
  show heading.where(level: 2): set text(size: 14pt)
  show heading.where(level: 3): set text(size: 12pt)

  show link: it => text(fill: theme.accent, it)
  show math.equation: set text(font: theme.math-font)

  set raw(tab-size: 2)
  show raw.where(block: true): it => block(
    width: 100%,
    fill: theme.code-bg,
    inset: (x: 9pt, y: 8pt),
    radius: 2pt,
    breakable: true,
    text(size: 8.8pt, it),
  )
  show raw.where(block: false): it => box(
    fill: theme.code-bg,
    inset: (x: 2pt),
    outset: (y: 3pt),
    radius: 1pt,
    text(size: 9.4pt, it),
  )

  set figure(gap: 10pt)
  show figure.caption: it => text(size: 9pt, fill: theme.muted, it)
  set table(stroke: 0.4pt + theme.rule)

  body
}

/// The PDF title page.
#let title-page(manifest) = {
  let meta = manifest.book
  page(numbering: none, header: none, {
    v(3.5cm)
    text(size: 30pt, weight: "bold", meta.title)
    if meta.at("subtitle", default: "") != "" {
      v(4pt)
      text(size: 14pt, fill: theme.muted, meta.subtitle)
    }
    v(1cm)
    line(length: 40%, stroke: 0.6pt + theme.rule)
    v(1cm)
    text(size: 12pt, meta.at("authors", default: ()).join(", "))
    place(bottom + left, text(
      size: 9pt,
      fill: theme.muted,
      [#meta.at("edition", default: "") #h(1fr)],
    ))
  })
}

/// A part opener in the PDF.
#let part-page(title) = page(numbering: none, header: none, {
  v(6cm)
  align(center, text(size: 22pt, weight: "bold", title))
})
