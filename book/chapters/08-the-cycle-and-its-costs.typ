// Source: notes/2026-09-11-session-01-foundations-and-craft.md, lines 161-190
// (author/build/ship, "Consumers, deliberately, not people"; "authoring >
// shipping > building"; [DECIDED] exchange rate at line 182; observability
// and measurability).

#import "/book/lib/prelude.typ": *

= The cycle and its costs

Under the vast day-to-day differences between domains lie three invariants:
author, build, ship -- to consumers, deliberately, who may be machines. It is
not a straight line but a cycle, and problems only become apparent over
repeated iterations, which is why every practice in the next chapter exists as
a response to a problem the cycle produced. Costs group roughly as authoring
over shipping over building, with authoring dominant because human attention,
paid in yearly salaries, is the scarce input -- and authoring is not typing
code but everything that captures product, design and intent, which is why
agents cheapening the typing mostly expose how much of the cost was always
upstream. Practices move cost between phases, and because the budget is not
fixed this is leverage rather than a zero-sum trade; the general test for
adopting any practice is to ask what its exchange rate is. Knowing the rate is
what observability attacks, and perfect knowledge is both impossible and
unnecessary: it is enough to be better than the rest.
