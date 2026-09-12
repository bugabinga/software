Fonts bundled with the book.

`--ignore-system-fonts` is passed to every Typst invocation so the PDF renders
identically on every machine, which means anything not embedded in Typst has
to live here. Typst embeds Libertinus Serif, New Computer Modern (and its
math companion) and DejaVu Sans Mono; this directory adds what it does not.

**Noto-COLRv1.ttf** — colour emoji, as `Noto Color Emoji`. Typst's embedded
fonts have no emoji glyphs, and a missing glyph is not a warning: emoji simply
came out as empty boxes in the PDF while rendering correctly on the website,
where the reader's own system supplies the font. Since the notes this book is
written from are full of emoji, that was a hole nothing would have caught.

The COLRv1 build is used rather than `NotoColorEmoji.ttf`: half the size
(5 MB against 10.7 MB) and vector rather than bitmap, so it stays sharp at
any size and in print.

Licensed under the SIL Open Font License 1.1, in `LICENSE.txt`.

To add a font: drop the file here, check what Typst calls it with

    .tools/typst/typst fonts --ignore-system-fonts --font-path book/fonts

and name that family in `book/lib/theme.typ`. Only name families that
resolve -- Typst warns about every one that does not, and `make check` treats
an unexpected warning as a failure.
