// Source: notes/2026-09-11-session-01-foundations-and-craft.md, lines 91-101
// (marked "[own article]" in the note; library OS; path dependence; "the
// yearning for simplicity might just be a romantic feeling").

#import "/book/lib/prelude.typ": *

= Operating systems

An operating system is a fiction machine: processes, files and virtual memory
are inventions that programmers accept as bedrock, and the everyday concept of
"a program" is one of its inventions. The chapter argues that much of the
machinery layered on top -- hypervisors, virtual machines, containers -- is
heavy-handed work undoing what the operating system imposed, and that a simpler
alternative already exists rather than being hypothetical: the operating system
as a library, where you import only the stack you need and your artifact
becomes the sole program on the machine. Why that lost is trajectory and
historical path dependence, not stupidity. Large systems accrete layers and
redundancies instead of reinventing themselves into cleaner forms, as biology
does, and there is probably wisdom in that; the yearning for simplicity may
just be a romantic feeling. The value of the argument is as a thought
experiment: the world does not have to be as it is.
