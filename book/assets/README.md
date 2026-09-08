Images and other files a chapter includes.

    #figure(
      image("/book/assets/diagram.svg", width: 80%),
      caption: [What the pipeline does.],
    ) <fig-pipeline>

Paths starting with `/` are resolved from the repository root, so they read
the same from any chapter.

Typst embeds images into the exported HTML as data URIs, so nothing here is
copied to the site separately -- but a large image is inlined into every page
that shows it. Keep raster images down to the size they are displayed at, and
prefer SVG for diagrams.
