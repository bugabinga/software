// Sources:
//   notes/2026-09-11-session-01-foundations-and-craft.md, lines 194-209
//     ("Admission criterion: generality"; the list; "Cut: formatting ...")
//   notes/2026-09-11-testing-session-notes.md, all of it -- the first entry
//     in the list, and by far the deepest material the notes hold.

#import "/book/lib/prelude.typ": *

= The practices

A practice earns its place in this chapter by being general, which is what
admits testing and verification, quality assurance, version control, code
review, static analysis and typing, code conventions, dependency management,
observability, incident response and hotfixing, and automation -- and what cuts
formatting into code conventions, infrastructure as code into automation, and
feature flags out as a tactic rather than a phase of the pipeline. Each is
weighed by the exchange rate of the previous chapter. Testing and verification
comes first and carries the most: why to test at all, why test-driven
development works in limited cases because exploratory programming has no
vision to march towards, why a test is a second and lossy encoding of the same
intent, how much testing is enough given the cost of mistakes and the tooling
at hand, and how little we can say about whether a test suite is any good.
