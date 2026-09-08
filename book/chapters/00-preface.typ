#import "/book/lib/prelude.typ": *

= Preface

This is placeholder content. It exists so the pipeline has something real to
build, and so every feature the book relies on is exercised on every commit.
Replace it with the actual preface; delete the chapters you do not want and
drop them from `book/book.toml`.

The book is written in #term[Typst] and built twice from the same source: once
as a website, once as a PDF. Nothing about a chapter is web-specific or
print-specific unless it says so, and the pipeline refuses to publish a build
that has broken links, unresolved references or misspellings.

#note[
  Chapters are plain Typst files under `book/chapters/`. The only required
  boilerplate is the `#import` on the first line and a level-one heading for
  the chapter title.
]

#web-only[
  The PDF of this book is linked in the header of every page.
]

#print-only[
  This book is also published as a website, where the code listings are
  selectable and the cross-references are clickable.
]
