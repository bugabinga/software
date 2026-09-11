# Testing — Session Notes

Working notes. Terse. Raw material, not writing.

---

## Why test — three reasons

- Fewer bugs shipped to production.
- Confidence in the implementation → broad and bold changes to the codebase become feasible without introducing regressions.
- Testing puts you in another mind space. Writing an API from the consumer's side improves its design.
  - Most prominent test-first, but holds always — just later and weaker.
  - Later sometimes means too late to change, but at least you're aware of the problem.

## On TDD

- TDD is a design and implementation tool. Works nicely in limited cases. Not generally applicable.
- Main reason: lack of knowledge or lack of vision. Goal often unclear in detail.
- Programming is frequently exploratory — manual testing, experimentation, trying random things.
- Also: limited understanding of system, context, APIs, language. The programmer is getting his bearings on the map of knowledge, not marching towards a vision.
- In those cases tests are too cumbersome and too slow, and have no value — thrown out when the experiment changes.
- In practice: some experiments get thrown away, some get shipped.
- **Key point:** programmers and stakeholders alike are often not aware they're in an exploratory phase. They perceive it as normal programming — which is why testing feels hard for them.
- Recognising it comes with experience. *Open: whether it can be taught.*

## Generalisation

- Goes back to the original challenge of programming: encoding intent and knowledge into a machine so it executes as designed.
- A test is a second, lossy encoding of the same intent.
- Only the artifact under test behaves as the artifact under test → almost no way to truly validate anything 100%.

## How much testing is enough — context and tooling

**Context = cost of mistakes.**
- Mistake not allowed or very costly → tests exponentially valuable.
- Errors cheap → testing becomes the cost.

**Tooling drives cost down** — money, time, mental power, adoption, learnability.
- Something easily available is far more often used than something that has to be fetched, configured, or installed.
- Go, Rust, Zig: testing in the toolchain. Fast, good UX, one obvious path good enough for almost everybody.
- Java: hunt for build system, test library, language server. Maven / Gradle / Mill / Bazel. Taxing and unnerving.
- Directly correlates with test quality. Go tests faster to write, faster to execute, easier to maintain. Java has good frameworks but takes real discipline to reach the same quality.
- Exotic needs — property, snapshot, mutation — reasonably stay external.

## Personal practice

- Hobby projects: invest heavily, because it's fun.
- Professional: adapt to context — customer, what's shipping, language ecosystem, runtime.

**Java desktop GUI:**
- UI components and integrations not trivially testable. Tests almost always nonexistent or very weak. Mostly accept the risk.
- Worse because UIs change a lot compared to other parts of the program.
- Pushing logic out doesn't fully solve it — UI logic deals with human interaction, and there's no cheap declarative way to mimic human interaction in a test run.
- Not permanent. LLM agents could partly replace human testing. Not fast, not cheap, but possible.
- Agents must never decide automatically. They report potential problems, screenshots, videos, source-code smells → escalated to other agents or human review. **Detector, not judge.**
- Triage cost is real. Comes down to good engineering and cost-to-benefit judgement.

## Test effectiveness

- Real problem: knowing when tests are useless, too costly, or not good enough. Easy to cargo-cult and follow a document.
- Measuring effectiveness is not a solved problem.
- Coverage is a good start but not very useful alone. Counter-example: 100% covered suite that asserts true everywhere.
- **Mutation testing** is in principle the perfect answer — tells you if unit test coverage is meaningful.
  - In practice hard to adopt: inherently slow, reruns the suite many times.
  - Works well incrementally: rely on the cache, mutate only what changed, run frequently, right after authoring or changing a test.
  - Context still in your head → results meaningful, decisions intelligent.
  - PIT (Java), Stryker (JavaScript) both support this well.

---

## Techniques

Two angles to "how": technique, and measuring effectiveness. **Measurement branch still open.**

In scope: example / Oracle unit testing, snapshot testing, property testing, fuzzing, mutation testing.
Niche, noted not explored: metamorphic, model-based, contract testing.

### Example tests

Properties of a good one:
- Speed and reliability. A flaky test has **negative value** — decreases confidence in the system rather than increasing it.
- Proper scope. As few assertions as possible, so a failure points straight at the problem without debugging the test first.
- Structure: setup → mutate state → assertions last.
- Naming: verbose mixed camel and snake case, when-given-then. Clauses separated by underscores, words inside clauses in camel case. Drop a clause when there's nothing to say.
- Long names are fine. Test method names are not API, they're description. They replace the comment.

Flaky tests:
- Fix if obvious and easy. Delete if repeat offenders.
- Deleting doesn't lose real bugs — an intermittent bug will show up again.
- Flakiness usually comes from complexity and bugs in the test environment, not the system.

Downside:
- Burden is on the programmer to choose good examples. Sometimes a lot of work and non-obvious.
- Mitigation: discipline on sentinel and edge-case values, plus coverage and mutation testing as safety net.

### Snapshot testing

- Elegant. An example-generation technique using real patterns from application output.
- Immediate value. Doesn't go as deep as integration tests but has similar properties — covers a lot.
- Limitation: not applicable to systems without clear textual or easily comparable output.
- Re-bless-without-reading failure mode is not a real concern. Good frameworks output a diff that makes the judgement cheap. No system prevents stupid behaviour.
- Snapshots live in version control.

### Property testing

- An extension of example tests. Programmer still has to think of what to assert, but a huge range of values is tested at once.
- Not easier than choosing examples — pitched one level up. Must be intimately familiar with the system's behaviour to write good properties.
- Shrinking can cause performance issues. Ecosystem mature enough that it rarely shows up now.
- Reach for it on: pure functions, functional cores, input-output transformations.
- Stateful code fine too, as long as state is internal or externally controllable.

### Fuzzing

- The big cousin of property testing. Property tests operate at function and method level; fuzzing is the integration-test variation.
- Not universally applicable.
- Shines in compiler and parser-like applications with a clear input-output transformation chain.

---

## Web UI testing

- Tooling arrived here because web apps ship semantic, structural, declarative HTML.
- Technically far easier than desktop GUI — but technically easier does not mean semantically or logically valuable tests.
- The human component is still unsimulatable in a declarative, reproducible way. Real UI tests never test human UI interaction; they test the technical layer.
- That layer still has real value: existence of elements and structures, navigational testing, automatically walking the whole application, catching common bugs like 404s. Plumbing, not usability.

### BDD, revisited

- Behaviour-driven testing is underexplored. Fell out of favour because it didn't deliver on its promises.
- Potential remains, especially coupled with agents — agents sit between business people and the coding harness, absorbing the glue work and grudge, leaving only hard cases for programmers.
- Doesn't fix spec rot. General problem with documentation and source of truth: **the artifact is the source of truth**; comments, docs, manuals, test descriptions are caches or alternative views. Caches rot. Agents can alleviate, not solve. Inherent.

## Tests as query engine — the inversion

- Earlier claim: in exploratory phases, testing is cumbersome and low-value.
- Opposite holds for mature and legacy systems with big mature test setups. There the testing layer becomes valuable ground for experimentation and learning — almost a **query engine for the system under test**.
- Especially valuable for agents: validate and double-check assumptions about the code they're writing and the system they're mutating.
- Doesn't change testing strategy beyond what you'd want anyway: tests must be fast, easy to call, easy to scope, well structured.

## Simulation-based testing

- From the systems programming side.
- Example: TigerBeetle, a financial transaction database. Tests with a simulation-based state machine environment rather than relying only on classic techniques. Simulate the whole environment around the application → inject failures and failure modes outside the application's control.
- **The meta-observation is what matters:** programmers forget the application is not the whole program. What the user experiences is the sum of all the layers underneath. Simulation testing is the only technique that admits the environment is part of the program.
- Not practised personally. Admiration from a distance. No system yet that would genuinely benefit.
- When does a system cross the line into needing it? Easy in hindsight — the company failed from expensive mistakes, but then it's game over and the learning helped nobody. Takes foresight: predicting the future from experience and knowledge of history. Judgement, not a rule.

---

## Open questions

- Whether exploratory-phase awareness can be taught, or only comes with experience.
- How to actually measure test effectiveness.
- The measurement-and-tracking branch of "how" — not yet covered.
- Whether agent-mediated BDD survives contact with reality.
