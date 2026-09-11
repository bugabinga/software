// Source: notes/2026-09-11-session-01-foundations-and-craft.md, lines 131-157
// ("Beauty is a property of the mental model the artifact induces"; the
// rejection of compression as the reason; "Worked example -- Unix [filed
// under mechanical sympathy]").

#import "/book/lib/prelude.typ": *

= Beauty and mechanical sympathy

Beauty is a property of the mental model an artifact induces, not of the
artifact, which is why the program matters more than the source code and why an
obsession with the medium -- text -- is a narrowing. Simplicity is beautiful not
because it compresses well but because it composes well, is easily maintained,
and delivers the promises the software set out to keep. Formatting, naming and
style guides are not dismissed; their value is collaborative, homogenising
software so that many developers, future self included, can work in it over
time. The mental model comes from running the artifact, debugging it,
interacting with it and reading its documentation as much as from reading its
source. Software is interpreted by machines too, and there it has real meaning,
so the designs worth admiring satisfy both sides at once. Unix is the worked
example: beautifully composable from the human side, while text pipes tax the
machine with constant encoding and decoding and many small programs tax it with
spawning -- a tension that structured pipes and single-binary shells resolve,
their drawbacks being about legacy compatibility rather than design.
