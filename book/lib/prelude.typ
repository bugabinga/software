// The vocabulary chapters are written in.
//
// Every chapter starts with `#import "/book/lib/prelude.typ": *`; everything
// exported here is available from that one line. Helpers that need to look
// different on the web than in print branch on `target()` rather than being
// duplicated per output.
//
// See `docs/AUTHORING.md` for the rendered reference, and
// `book/chapters/99-prelude-reference.typ` for live examples of each helper.

#import "theme.typ"

/// Content that only appears on the website (e.g. an interactive link).
#let web-only(body) = context if target() == "html" { body }

/// Content that only appears in the PDF (e.g. a page cross-reference).
#let print-only(body) = context if target() == "paged" { body }

/// A defined term, at the point where the book defines it.
#let term(body) = context {
  if target() == "html" {
    html.elem("dfn", body)
  } else {
    emph(strong(body))
  }
}

/// An aside: `note`, `tip`, `warning` or `caution`.
///
/// - kind: which of `theme.callouts` to use.
/// - title: heading text, or `none` for the kind's default label. Pass `""`
///   for a callout with no heading at all.
#let callout(kind: "note", title: none, body) = {
  let style = theme.callouts.at(kind)
  let heading-text = if title == none { style.label } else { title }

  context {
    if target() == "html" {
      html.elem(
        "aside",
        attrs: (class: "callout callout-" + kind),
        {
          if heading-text != "" {
            html.elem("p", attrs: (class: "callout-title"), heading-text)
          }
          body
        },
      )
    } else {
      block(
        width: 100%,
        fill: style.bg,
        stroke: (left: 2pt + style.accent),
        inset: (x: 12pt, y: 10pt),
        radius: (right: 2pt),
        breakable: true,
        {
          if heading-text != "" {
            text(weight: "bold", fill: style.accent, heading-text)
            parbreak()
          }
          body
        },
      )
    }
  }
}

#let note(title: none, body) = callout(kind: "note", title: title, body)
#let tip(title: none, body) = callout(kind: "tip", title: title, body)
#let warning(title: none, body) = callout(kind: "warning", title: title, body)
#let caution(title: none, body) = callout(kind: "caution", title: title, body)

/// Strip the smallest common indentation from a block of lines.
#let _dedent(lines) = {
  let widths = lines
    .filter(line => line.trim() != "")
    .map(line => line.len() - line.trim(at: start).len())
  let indent = if widths.len() == 0 { 0 } else { calc.min(..widths) }
  lines.map(line => if line.len() >= indent { line.slice(indent) } else { line })
}

/// A code listing read from a real file under `code/`, so that what the book
/// shows is what the pipeline compiles.
///
/// - path: absolute-in-project path, e.g. `/code/examples/hello.rs`.
/// - lang: syntax highlighting language; inferred from the extension if `none`.
/// - tag: name of a region to extract. The file marks regions with
///   `[tag]` and `[/tag]` inside comments; the marker lines themselves are
///   dropped and the region is dedented.
#let snippet(path, lang: none, tag: none) = {
  let source = read(path)
  let language = if lang != none { lang } else { path.split(".").last() }

  if tag != none {
    let inside = false
    let kept = ()
    for line in source.split("\n") {
      if line.contains("[/" + tag + "]") {
        inside = false
      } else if line.contains("[" + tag + "]") {
        inside = true
      } else if inside {
        kept.push(line)
      }
    }
    assert(
      kept.len() > 0,
      message: "no lines found for tag `" + tag + "` in " + path,
    )
    source = _dedent(kept).join("\n")
  }

  raw(source.trim("\n"), lang: language, block: true)
}

/// The slug a chapter file is published under: its file stem without the
/// ordering prefix, so `chapters/01-the-pipeline.typ` lives at `the-pipeline/`.
///
/// `tools/build.py` derives web URLs with the same rule; keep the two in step.
#let slug-of(path) = {
  let stem = path.split("/").last().trim(".typ", at: end)
  stem.trim(regex("^[0-9]+[-_]"), at: start)
}

/// The anchor `xref` links to in print. Emitted by `book/book.typ` ahead of
/// every chapter; chapters never need to call it.
#let chapter-anchor(slug) = [#metadata(slug)#label("ch-" + slug)]

/// A reference to another chapter.
///
/// Typst's own `@label` references work inside a chapter, but each chapter is
/// its own document on the website, so references that cross a chapter
/// boundary go through this helper: a relative link on the web, a page
/// reference in the PDF.
///
/// - slug: the target chapter's slug, as `slug-of` computes it.
/// - anchor: optional heading id to jump to on the web.
#let xref(slug, anchor: none, body) = context {
  if target() == "html" {
    let fragment = if anchor == none { "" } else { "#" + anchor }
    link("../" + slug + "/" + fragment, body)
  } else {
    let anchor-label = label("ch-" + slug)
    if query(anchor-label).len() == 0 {
      // The chapter is not part of this build (a single-chapter PDF, say).
      body
    } else {
      link(anchor-label, body)
      [ (page #counter(page).at(anchor-label).first())]
    }
  }
}
