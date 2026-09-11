// Sources:
//   notes/2026-09-11-session-01-foundations-and-craft.md, lines 228-237
//     -- the section is marked "[PARKED -- fits in the book, write up
//     later]", which is why this is an appendix and not a chapter.
//   notes/2026-09-11-testing-session-notes.md, lines 64, 139, 146
//     (agents as "Detector, not judge"; agent-mediated BDD; the test suite
//     as a query engine an agent can use).

#import "/book/lib/prelude.typ": *

= Agents

Large language models are not artificial intelligence in the classical sense of
a system that holds a model of the world and adjusts it; they learn, but not
dynamically, being pretrained. The recent innovation is the agent: a model
given sensors and actuators by a harness, which is a sampling apparatus in
exactly the sense the chapter on knowledge gives the word. The claim worth
making is that the intelligence is the fine-tuned agent rather than the base
model -- base models encode knowledge and regurgitate it, and intelligence
emerges when a model is fine-tuned to act within an environment, which is also
why "thinking models" are better described as having learned how to act than as
merely thinking more. The note this is drawn from is parked for later writing.
