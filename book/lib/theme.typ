// Visual constants for the PDF build.
//
// The website has its own tokens in `site/assets/book.css`; keep the two
// roughly in sync by hand. Nothing here is read by the web build, so a change
// only affects the PDF.

// Only families that actually resolve belong here: Typst warns about every
// unknown family in the list, and `make check` treats warnings as failures.
// Typst embeds Libertinus Serif, New Computer Modern (+ Math) and DejaVu Sans
// Mono; drop extra `.ttf`/`.otf` files in `book/fonts/` to use anything else.
#let serif = "Libertinus Serif"
#let mono = "DejaVu Sans Mono"
#let math-font = "New Computer Modern Math"

#let ink = rgb("#16181d")
#let muted = rgb("#5b6270")
#let rule = rgb("#d7dae0")
#let accent = rgb("#24479c")
#let code-bg = rgb("#f5f6f8")

// Callout colours, keyed by the `kind` passed to `callout`.
#let callouts = (
  note: (accent: rgb("#24479c"), bg: rgb("#eef2fb"), label: "Note"),
  tip: (accent: rgb("#1c7a45"), bg: rgb("#ecf6f0"), label: "Tip"),
  warning: (accent: rgb("#8a6100"), bg: rgb("#fbf3e3"), label: "Warning"),
  caution: (accent: rgb("#a02b2b"), bg: rgb("#fbeeee"), label: "Caution"),
)

#let body-size = 11pt
#let page-margin = (inside: 2.6cm, outside: 2.2cm, y: 2.4cm)
