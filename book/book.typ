// PDF entry point. Chapter order comes from `book.toml`, so this file never
// needs editing when a chapter is added.
//
//   typst compile --root . --features html book/book.typ dist/book.pdf
//
// Pass `--input only=<substring>` to build just the matching chapters, which
// is handy while writing:
//
//   typst watch --root . --features html --input only=01- book/book.typ /tmp/ch.pdf

#import "/book/lib/styles.typ"
#import "/book/lib/prelude.typ": chapter-anchor, slug-of

#let manifest = toml("/book/book.toml")
#let only = sys.inputs.at("only", default: "")

#show: styles.paged.with(manifest)

#if only == "" {
  styles.title-page(manifest)
  // A scoped `set page` rather than a `page(..)` call: two adjacent `page`
  // elements would leave a blank leaf between them.
  {
    set page(header: none, numbering: none)
    outline(title: [Contents], depth: 2)
  }
}

#for part in manifest.part {
  let selected = part.chapters.filter(path => only == "" or path.contains(only))
  if selected.len() == 0 { continue }

  if only == "" and part.at("title", default: "") != "" {
    styles.part-page(part.title)
  }

  // Front and back matter carry no chapter numbers.
  if not part.at("numbered", default: true) {
    set heading(numbering: none)
    for path in selected {
      chapter-anchor(slug-of(path))
      include "/book/" + path
    }
  } else {
    for path in selected {
      chapter-anchor(slug-of(path))
      include "/book/" + path
    }
  }
}
