# Session 01 — Notes

Book on software. Foundations + craftsmanship. Raw notes, not prose.

---

## Machine and program

- Machine = abstract/theoretical sense. Input → output transformation. Not gears.
- At that level the machine/program distinction **dissolves entirely**. Universal Turing machine makes it vivid.
- Survives in practice for two reasons only:
  - **Economics** — physical machines can't be built as cheaply/easily as digital ones. Cost, energy, heat dissipation, practicality.
  - **Culture** — we doubled down on the von Neumann model, which builds the split into the architecture. Not necessary. Just adopted.
- Road not taken: lambda calculus. Equally powerful, no split. Terms reducing to terms. No stored program, no program counter.
- Von Neumann's decisive sin: made **state and location first-class**.
- Propagated into all Algol/C-descended languages. They conflate state, location, and value with fact and time. Messy because of it.
- **Not faulting the languages.** They're honest reflections of the machine and efficient because of it. The von Neumann model really has done us in.
- Time: stateful languages smuggle it in as assignment. Functional languages pretend it doesn't exist. Neither *names* it.
- No language encodes time and space first-class. Spacetime must somehow be abstracted and encoded — no idea how. **Not my job to find out, not the topic of this book.** Framing, not thesis.

### Vocabulary (side note, not its own article)

- Industry uses code / program / software / application interchangeably, meaning shifting by context.
- [DECIDED] Paragraph inside the machine-and-program article. Not standalone.
- Framed as a symptom: the craft, the industry, and humanity haven't figured out what the digital machinery / information space should look like.

---

## Information and entropy

- [DECIDED] Two terms, kept strictly apart. Do not conflate.
- **Thermodynamic entropy** — chaos. Opposite is harmony/order, which in our context is information. We recognise information because it has patterns chaos does not.
- **Shannon entropy** — surprise. Max information = max entropy. CS-curriculum meaning, different from the physicist's. Agree with Shannon; was worried I'd been using the word loosely.
- Compression and coding matter here — they connect directly to language. A word is a compressed pointer to a cluster of experience.

---

## Knowledge

- Categorically different from information. **An experience first and foremost.**
- Dead-language book test settles it:
  - **Information is intrinsic** — the pattern is there whether or not anyone can read it. A book in a language I don't know is still clearly distinguishable from chaos.
  - **Knowledge is relational** — needs a reader with the key.
- Heisenberg-ish: only by observing does it become real. Not sure.

### The regress of keys

- If knowledge needs a key, and the key is encoded, you need a key for the key. Pathological.
- Sensation as the floor: **rejected.** Sensation is a mechanism of encoding — better word, **sampling**.
- Digital machines digitize/sample. Humans sample light, temperature, physical information.
- What happens after sampling is inside consciousness. Cannot currently be defined.
- [OPEN] Filed as boundary of the framework. Not papered over.

### Non-human decoders

- Not limited to humans. Another machine could consume a running program and experience something knowledge-like.
- That's how to think about agents. **Not claiming agents are conscious at the same level as humans.** But there's something there.
- Today's agents do **not** have a separate model of the world. Classical AI tried hand-crafting exactly that and failed.
- Irony: LLMs succeeded, and their model of the world *is the language itself*. No separate model of reality.
- [DECIDED] Not adjudicating whether agents truly decode meaning. From the human perspective they appear to; however they do it doesn't really matter. Scoped as a comment on the **current state of LLMs/AI**, not a prediction.

---

## Software and its forms

- Software is **language**, in the most general sense. A language of description.
- Software is the **compressed** form of knowledge. The program is the **decompressed** form. (Claude had this backwards first.)
- At execution it becomes **information**, not knowledge — the machine transforms patterns without decoding meaning.
- Text is just the **medium**. Incidental. It didn't have to be text; text is merely convenient for us.

### The four words [DECIDED]

- **Software** — all the informationy, squishy, moving parts that get compiled into an artifact. Used interchangeably with source code.
- **Source code** — all authored input. Config, shaders, MP3s, 3D models, asset pipelines. Not just text.
- **Program** — the compiled artifact that runs on a physical machine.
- **Process** — the running program. The moment it becomes physical. Word has OS baggage, but it's the one.
- The source-code/asset distinction is **technical, not philosophical**. No meaningful difference between source code, a config file, a shader, an MP3.
- Rejected: "the work" (Claude's suggestion).

---

## Operating systems [own article]

- OS is a fiction machine. Processes, files, virtual memory — inventions treated as bedrock.
- Programmers mostly don't distinguish or understand the abstractions the OS draws for them. They accept them as reality, as if there were no other choice.
- The everyday concept of "a program" is an **OS invention**.
- The weirdness: hypervisors, virtualization, VMs, containers as heavy-handed abstractions to split up the same machine. Much of it undoing what the OS imposed.
- Simpler alternative already exists and is real, not hypothetical: OS **as a library** — import only the stack you need, your artifact becomes the sole program on the machine. (Called them monokernels in session; check the term — unikernels / library OS, MirageOS.)
- Why they lost: **trajectory and historical path dependence.** Not stupidity.
- Big complicated systems don't reinvent themselves into cleaner forms. They accrete redundancies and layers. Biology does the same. **There is probably wisdom in that.**
- The yearning for simplicity **might just be a romantic feeling.**
- Not condemning current architecture. Value is as a thought experiment: the world does not have to be as it is.

---

## Learning the craft

- Claude's opening question (gap between taught and practiced) was **ill-posed**. The craft is essentially not taught.
- CS degrees are woefully out of touch with reality. Any programmer knows uni was a fraction of the day-to-day, if relevant at all.
- **Not a total failure.** Theory and research degrees are valuable and shouldn't be dismissed. The failure is universities *pretending* to teach craft.
- Craft transmits by mentorship, guidance, osmosis, and heavily **self-teaching**.

### My path (self-taught)

- Started as an **artist drawing comics**. Intended to go into art. Trained on paper and pencil.
- Photoshop, digital art, graphics tablets, as that scene matured. Looking for my style and workflow in the digital space.
- **Flash** — animations, frames, transitions, small scripts in the authoring tool.
- Got hooked. Wanted particle emitters, effects, visual websites, rich applications.
- Ended up in **Eclipse writing ActionScript**, not Flash anymore.
- Transition from artist to programmer: too gradual to pinpoint.

### Drawing / programming parallel

- People think drawing is intuition and feeling. Far from reality. It has almost **algorithmic concepts**, trained by studying anatomy, ranges of movement, perspective, light.
- A physical connection to experienced reality, then a satisfying process putting it down on paper.
- Programming is the same shape. Clear rules, thought processes, and **thought castles** — *Gedankenschlösser*. Doesn't work in English, works in German.
- Elaborate abstract constructs built in thought, then put into the machine as code. Previously as drawings.
- Intoxicating and beautiful. Still what draws me to programming.

---

## Beauty and mechanical sympathy

- Less bothered by syntax and textual construct than programmers who only ever programmed. Those are obsessed with the medium — text.
- Attention goes to architecture, modules, beauty and simplicity of the artifact. **The program matters more than the source code.**
- Formatting / naming / style guides: **not dismissed.** Valuable *collaboratively* — homogenizing software so many developers can work in it over time. Includes solo devs: future me is reading my code right now. Practical, not inherently beautiful.
- Beauty is a property of the **mental model the artifact induces**, not of the artifact.
- Simplicity is beautiful **not** because it compresses well (Claude's suggestion — rejected). Because it **composes** well, is easily maintained, and delivers the promises the software set out to keep.

### Where the mental model comes from

- Not only from reading source. Running the artifact, running it in a debugger, interacting with it, reading docs, reading source — all contribute.
- **I am not a machine. I do not run the artifact.**
- I can only build a model of *how* and *when* it will run — and more importantly, of how the running artifact affects interactions with the world, other machines, and humans.

### The duality

- Software is also interpreted by machines, and there it has real meaning.
- Sometimes tension between human beauty and machine execution. Sometimes it aligns nicely.
- With experience I find beauty in designs achieving **both**: understandable, composed, modular thought castles that also map efficiently, performantly, optimally onto the substrate.

### Worked example — Unix [filed under mechanical sympathy]

- Bash, grep, ls. Beautifully composable **from the human side only**.
- Machine side: text pipes force constant encode/decode of arbitrary data; splitting execution across many programs is inefficient.
- Nonetheless hugely successful over time.
- **PowerShell and Nushell** resolve it: structured pipes (PowerShell = objects, Nushell = tables) kill the serialization tax. Bundling commands into **one binary** instead of many small executables kills the spawn tax.
- Their drawbacks are about **legacy compatibility, not design**.

---

## The cycle and its costs

- Domains differ vastly day-to-day. Game dev and web dev might as well be different universes.
- [DECIDED] Those were **illustrative examples only.** Not interested in splitting by domain. Differences may be noted in passing. **Never a topic of the book.**
- Invariants: **author → build → ship**.
- **Consumers**, deliberately, not people. May be machines.
- Not a straight line — a **cycle**. Problems only become apparent over repeated iterations. Every practice exists as a response to those problems.

### Costs

- Other constraints — space, manpower, time, expertise — roughly group under cost. Money solves most. Time is a partial exception.
- Distribution is domain-specific. Amazon: huge shipping/delivery cost. Games: front-loaded authoring, one ship event. Small programs: negligible delivery.
- Roughly: **authoring > shipping > building.**
- Authoring dominates because **human attention, paid in yearly salaries, is the scarce input.**
- **Authoring ≠ typing code.** Authoring encompasses all the product, design, and intent-capture phases. Typing code was never the real cost. Agents cheapening the typing only exposes how much cost was always upstream.

### Exchange rates

- Practices move cost between phases. Not zero-sum — **leverage**.
- Testing: ~1% extra in build, ~15% saved in authoring. Arbitrary numbers, right shape.
- Budget is not fixed. The point is achieving more with the same budget by shuffling where energy is spent.
- [DECIDED] General test for adopting any practice: **what's the exchange rate?**
- In an ideal world with perfect information this would be the sole motivation. In reality: ideology, cargo culting, imperfect knowledge. People follow trends and "best practices" without deep thought.

### Measurability

- This is exactly what **observability** (tracing, tracking) attacks — increase the information we have about our own pipeline.
- Perfect knowledge is philosophically impossible. Also unnecessary.
- Enough to be **better than the rest**. With a monopoly on a niche, enough to deliver anything at all.
- Only when competing for optimality does deeper instrumentation become genuinely valuable.

---

## The practices

Admission criterion: **generality**.

- Testing and verification
- **Quality assurance** — distinct from automated testing. **A phase, not a headcount.** Nothing inherently human about it; defined by when it triggers. Matters as agents do exploratory testing.
- Version control
- Code review
- Static analysis and typing
- **Code conventions** — the umbrella. Formatting alone is just a technique. Point is to homogenize the software so many developers are comfortable working in it over time.
- Dependency management
- Observability
- **Incident response and hotfixing** — reactive counterpart to observability. "Incident response" alone is a cloud/web term that doesn't generalize; games have crash reporting, telemetry, hotfix patches, less formally. Combined name settled.
- **Automation** — the umbrella, and arguably the overarching drive. Absorbs CI/CD and infrastructure as code.

**Cut:** formatting (→ code conventions), infrastructure as code (→ automation, too cloud-heavy as a standalone term), feature flags (a tactic, not a pipeline practice).

---

## Intent / product engineering

- [DECIDED] One article: product engineering, requirements engineering, UX, design, requirements gathering, user interviews. All belong together.
- Tickets and user stories are its artifacts. Jira/PR workflow specifics **out of scope** — way too specific.
- In general: some system where developers interact with domain experts about **what and why** to build. Not yet how to achieve it in code.
- Shape determined by **distance between engineer and consumer**:
  - **Zero** — building for myself. Collapses into me just thinking about it.
  - **Short** — building for developers. I can imagine their needs and problems easily.
  - **Large** — engineer and consumer in different groups. Fundamental shift. Requires direct contact, or **middlemen**: product managers, support, others closer to the target group.
- Every middleman is another encode-decode hop, with loss.
- **Cost caveat:** huge cost driver and time sink in most orgs, even though it should *reduce* authoring cost. That is **accidental, not essential.** Remedy is fewer hops, not more ceremony.
- [OPEN] Dislike the term "product engineering." It names a **role** when the point is that **all engineers should engage with it.** Org-dependent and muddy. Find a better name.

---

## Agents [PARKED — fits in the book, write up later]

- LLMs are not AI in the **classical** sense. Classical = digital system with a model of the world, adjusting and using the model, learning.
- LLMs do learn, but not dynamically. **Pretrained.**
- Recent innovation is the **agent**: an LLM given **sensors and actuators**. That's what the **harness** does — tools to observe and act in digital environments. Possibly only ever digital.
- The harness is a **sampling apparatus**. Connects straight back to the sampling argument in the knowledge article.
- **Core claim: the intelligence is the fine-tuned agent, not the base model.** Common misconception that the LLM is the intelligence.
- Base models were only somewhat intelligent — they encoded lots of knowledge. Intelligence emerged from fine-tuning for harnesses/tool calls *and* reasoning, by exposing models to environments and having them adapt.
- Base models regurgitate knowledge. Intelligence emerges when the agent learns to **sample and act within its environment**.
- Corollary worth stating: many people think "thinking models" merely *think more*. In reality they learned **how to act in their environment**.

---

## Citations — consciousness

- **Annaka Harris** — *Conscious: A Brief Guide to the Fundamental Mystery of the Mind*; audio series *LIGHTS ON*. Treats consciousness as possibly **fundamental** rather than emergent. Strongest fit.
- **David Chalmers** — the hard problem.
- **Anil Seth.**
- **Giulio Tononi** — IIT.
- **Thomas Metzinger.**
- Also mentioned in session, not yet filed: Sam Harris, Chomsky.

---

## Open questions

1. Floor of knowledge — what's below sampling. Consciousness undefined.
2. What is the key? Regress unresolved.
3. A language encoding time and space first-class. Deliberately not pursued.
4. Do agents decode meaning? Declined to adjudicate.
5. Better name than "product engineering."
6. Does authoring stay dominant? Provisionally yes, because authoring = intent capture. Open part is empirical: how much of intent capture is irreducibly human attention, and is that fraction stable.
7. Is the yearning for simplicity romantic?

---

## Book decisions

- **No overarching thesis.** For now this book is just a collection of my thoughts. Organized, sharing a vocabulary. Claude proposed a spine (encoded knowledge / loss at every hop) — **declined.**
- Foundation is **living, not finished.** Revise Part I when later material strains it.
- Structure: Part I Foundations (machine and program, information and entropy, knowledge, software and its forms, operating systems). Part II Craft (learning the craft, beauty and mechanical sympathy, the cycle and its costs, the practices, intent and product engineering). Appendix (open questions, deferred agents, citations, glossary).
- Format: MkDocs Material, markdown per article, GitHub Actions → Pages.

---

## Workflow

- Interviews stay here, on the phone. Text interface for artifacts.
- Repo work belongs to a separate Claude Code instance. Two halves don't share context — **annoying, that's the product's gap, not mine to solve.**
- Bridge: export conversation → `transcripts/` in the repo → Claude Code compiles from the raw transcript, not from a summary. Lossless-ish.
- Repo is the single source of truth. Chat is disposable.
- Something must trigger Claude Code. It doesn't run on its own. Unavoidable.
- [TODO] git init, commit, push, enable Pages.
