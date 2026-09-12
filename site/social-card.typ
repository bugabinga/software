// The repository's social preview card: what GitHub, Slack, Mastodon and the
// rest show when someone links the repository.
//
//   typst compile --root . --features html --ignore-system-fonts \
//     --font-path book/fonts site/social-card.typ dist/social-card.png --ppi 72
//
// 1280 x 640 is GitHub's recommended size, and at 72 PPI one Typst point is
// one pixel, so the page below is literally the output in pixels.
//
// **Deliberately says nothing about the book.** An earlier version set the
// title and description from `book.toml`, which meant the card advertised a
// working title and a description of the build pipeline, and would have had
// to be looked at again every time either changed. This one carries no words,
// so it stays correct through any amount of rewriting.
//
// What it draws instead is the idea the book opens with: information is what
// we recognise because it has a pattern that chaos does not. The field runs
// from a lattice on the left to scatter on the right -- order dissolving into
// noise, in the direction you read.
//
// Generated, but not random: the jitter is a hash of each cell's coordinates,
// so every build produces an identical file and the published image does not
// churn.

#set document(title: "Social preview")

#set page(width: 1280pt, height: 640pt, margin: 0pt, fill: rgb("#12141a"))

// --- the field ------------------------------------------------------------

#let columns = 40
#let rows = 13
#let cell = 34pt

// A stable pseudo-random number in [0, 1) for a cell, per salt. Three odd
// multipliers and a modulus: enough decorrelation to read as noise, and
// completely determined by its inputs, so the image is the same on every
// machine and every build.
#let noise(i, j, salt) = {
  let h = calc.rem(i * 73856093 + j * 19349663 + salt * 83492791, 65521)
  h / 65521
}

#let ordered = rgb("#5b8dff")
#let dissolved = rgb("#8b93a7")

// The field is a band across the middle rather than a full-bleed texture.
// Filling the canvas left nowhere for the eye to rest and read as wallpaper;
// a band has a top and a bottom, so it reads as a figure.
#let band-height = rows * cell
#let band-top = (640pt - band-height) / 2

#for j in range(rows) {
  for i in range(columns) {
    // 0 at the left edge, 1 at the right: how far this cell has dissolved.
    let t = i / (columns - 1)
    // Eased, so the lattice holds for a while before it gives way rather than
    // degrading from the very first column.
    let d = calc.pow(t, 2.1)

    // Fade towards the band's own top and bottom, so it has no cut edge.
    let v = calc.abs(j / (rows - 1) - 0.5) * 2
    let vertical = calc.max(0.0, 1.0 - calc.pow(v, 3.4))

    let jitter = d * cell * 1.5
    let x = i * cell + (noise(i, j, 1) - 0.5) * jitter
    let y = band-top + j * cell + (noise(i, j, 2) - 0.5) * jitter

    // Marks thin out as they scatter, but a few survive at full strength,
    // which keeps the right-hand side from reading as a flat wash.
    if noise(i, j, 3) > d * 0.72 {
      let size = cell * (0.30 - 0.09 * d + 0.10 * noise(i, j, 4))
      let alpha = (1.0 - d * 0.6) * vertical
      place(
        left + top,
        dx: x - cell / 2,
        dy: y - cell / 2,
        square(
          size: size,
          radius: 1pt,
          fill: ordered
            .mix((dissolved, d * 100%))
            .transparentize(100% - alpha * 100%),
        ),
      )
    }
  }
}

// --- the one fixed mark ---------------------------------------------------

// The website's favicon, so the card, the browser tab and the site agree. Its
// tile is within a shade of this background, so what shows is the glyph, on
// the clear space the band leaves. It is the only thing here that identifies
// the repository and the only thing not generated -- and being a mark rather
// than words, it cannot go out of date.
#place(
  left + bottom,
  dx: 96pt,
  dy: -84pt,
  image("/site/assets/favicon.svg", width: 58pt),
)
