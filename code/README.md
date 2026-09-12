Example code the book quotes.

Listings live here rather than inside the prose so a compiler can read them:
`mise run check-code` type-checks every file in this directory, and CI fails if a
listing stops compiling.

A chapter quotes a region of a file rather than the whole thing:

    #snippet("/code/examples/types.rs", tag: "newtype")

which prints the lines between the `[newtype]` and `[/newtype]` markers,
dedented, with the marker lines removed. Markers go inside comments, so the
file still compiles:

    // [newtype]
    pub struct Columns(pub u16);
    // [/newtype]

Quoting a tag that does not exist fails the build.

To add a language, add a branch to `tools/check_code.sh`. Rust files are
checked with `rustc --emit=metadata`, which needs no Cargo project.
