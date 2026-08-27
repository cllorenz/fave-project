# ad6 encoding & solver architecture — a parallel investigation track

**Status:** Core H1/H2 investigation DONE (§§1-3). The concurrent wl_stanford session has
since ended (results committed/pushed); its own B1 cycle-soundness fix independently found
and cross-scoped against this track's §2.4 (see `AD6_PLAN.md`'s B1 write-up). §6's "if it
works" question is answered and integrated into `AD6_PLAN.md` §6 (2026-08-25); §2.5's
still-open bug relayed there too. **2026-08-27: the incremental lever is fully closed
out.** The Stanford prototype (§3.10) rescued B1's wall-clock NO-GO (full real 256-pair
all-pairs matrix, ~16-23 min vs. B1's own 6-hour/28.9%-complete result); its answers were
then run through the SAME live-NetPlumber oracle-comparison `test_ad6_wl_stanford.py`
itself uses — **EXACT MATCH, 0 diffs across all 16 roles**. The C-stack-overflow
robustness bug found along the way is FIXED (`ad6/src/bigstack.py`). The incremental
architecture is now **applied to production** (`ad6/src/solver/incremental.py`, wired
into `ad6/fave_bridge.py` — the only call site changed), verified via `ad6 make test` +
36 real fave-side ad6 tests through the actual subprocess bridge. Remaining open item:
the DIMACS-base-caching fix (§3.9's separable, smaller finding) — superseded in practice
by the full incremental architecture now being in production, so likely moot; not
pursued further. Owner: Claas Lorenz. Kept as its own file (not merged into
`AD6_PLAN.md`) — this is the detailed methodology/findings record; `AD6_PLAN.md` §6
carries the integrated summary. Started
2026-08-24.

## 0. Scope and relationship to `AD6_PLAN.md`

Two complementary investigations are running in parallel on ad6:

- **The parallel/concurrent session** drills into the existing codebase to find solutions
  within its current constraints and surface practical problems as they occur (e.g. the
  wl_stanford B1 scale-up work: the generator dead-port bug, the cycle-soundness
  CEGAR/rank-constraint fix for `InstantiateEndToEnd`). That work lives in `AD6_PLAN.md`.
- **This track** investigates ad6's architecture more broadly and with more outside
  context: specifically, whether ad6's own hand-rolled CNF/KNF conversion (vs. a more
  expressive solver — SMT/QBF) is sound architecture, and how algorithmically mature that
  conversion is. This is a Claude-session-driven research thread, not code changes to
  ad6 itself (no ad6 source files have been modified as part of this track).

## 1. The two hypotheses under test (Claas, 2026-08-24)

> 1) My naive SAT approach with custom CNF conversion states a premature optimization,
> i.e., some straightforward encoding — e.g., as QBF/SMT — would be both more readable
> and more performant due to better solvers.
> 2) If straight SAT remains reasonable, what are the measurable bottlenecks and how can
> they be addressed properly, i.e., conceptually and implementation-wise?

### Critical assessment (2026-08-24)

**H1 bundles three separable variables that need to be measured independently, or any
result is uninterpretable:**
- *Readability* — plausibly true, but almost entirely an SMT claim, not a QBF one. None
  of ad6's actual query primitives (`_run_reach`, `_measure_end_to_end`, `_run_cross`,
  `_run_cycle`, `_run_shadow`) need quantifier alternation (confirmed §2.1 below).
- *"Premature optimization"* may be the wrong diagnosis — the custom converter isn't
  optimized, it's naive (no Tseitin, §2.2). A better frame: a 2014, self-contained,
  portable prototype now stale relative to a decade of solver engineering, which is a
  different failure mode with different expected remedies.
- *"Better solvers" performance* needs splitting: (a) modern CDCL engine vs.
  minisat/clasp/pycosat — likely a large, independent win, testable with **zero encoding
  change** (same DIMACS, swap the binary); (b) SMT "theory reasoning" beating SAT — for
  quantifier-free bitvector theory, most SMT solvers (incl. Z3) bit-blast `QF_BV` to CNF
  and call a SAT solver underneath, so this is mostly "mature translator + mature solver,"
  not evidence theory-level reasoning is intrinsically faster; (c) array/UF-theory FIB
  modeling (avoiding one explicit disjunct per route) — the one place a *structural*,
  not just tooling-maturity, win seems plausible; (d) QBF performance specifically —
  QBF solvers (DepQBF/CAQE/RAReQS) lag CDCL SAT engines substantially, and folding O(n²)
  pairwise queries into one PSPACE-complete QBF instance is not free amortization.

**H2 is not an alternative to H1 — it's H1's control group.** Without isolating solver
engine, CNF-conversion quality, and modeling layer as independent axes, a future "SMT is
faster" (or "isn't faster") result can't be attributed to the right cause.

**Important correction from Claas (2026-08-24) on the thesis's "SAT too slow" verdict**
(`claas_lorenz_phd_thesis.pdf` §1.4, pp.9-10): that verdict was **comparative against
domain-specific tools**, motivating the pivot to NetPlumber/FaVe — **not** a claim that
the SAT/generic approach had been engineering-matured first. Whether Tseitin conversion
or an SMT backend would narrow or close the gap is genuinely untested — that path was
deliberately not pursued at the time in favor of the domain-specific pivot. This reframes
the current effort: it isn't only re-measuring an already-settled result with better
instrumentation, it's the first real opportunity to test a question the original work
left open by design. See memory `ad6-sat-too-slow-verdict-was-comparative-not-definitive`.

## 2. Findings so far

### 2.1 QBF vs. SAT — resolved, not an open question

`ad6/src/sat/qbfutils.py` implements real QBF machinery (prenex conversion,
Skolemization) with its own isolated test suite, but has **zero call sites** anywhere
else in the tree, and no solver adapter runs in QDIMACS/QBF mode (only
`MiniSATAdapter`/`ClaspAdapter`/`PycoSATAdapter`, all plain DIMACS CNF).

**Resolved via the SECRYPT'15 paper (`secrypt15.pdf`) and Claas's confirmation
(2026-08-24):** §3.3's `trans(C)` formula is `∀(t,c,u)∈δ. y(t,c,u) → (...∃(s,b,t)∈δ...)`.
The `∀`/`∃` range over **δ, the concrete, already-built, finite transition relation of one
specific Kripke graph** — a meta-level "for every/there exists a real edge in this
graph," not an object-level quantifier over an open Boolean domain. Because δ is
statically enumerable once built, these compile away by direct enumeration (the
`IterFTransitions`/`IterBTransitions` loops in `_ConvertNodesToImplications`/
`InstantiateReach`/`InstantiateEndToEnd`) rather than needing genuine QBF quantifier
elimination. `qbfutils.py` is the superseded, more-generic exploratory path that predates
this realization — a correctly-abandoned direction, not unfinished/aspirational code
needing a decision. **No action needed here** beyond, eventually, deciding whether to
delete the dead module or leave it as a documented historical artifact (low priority,
owner call).

### 2.2 Naive (non-Tseitin) CNF conversion — already flagged, cross-referenced

`ad6/src/sat/satutils.py::ConvertToCNF` does textbook De Morgan + AND/OR distribution,
no Tseitin auxiliary variables — exponential in formula *alternation depth*, not rule
count. Already self-flagged in `AD6_PLAN.md` §5.4/§8.5 as safe today only because every
existing frontend emits shallow, flat conditions (a convention, not a structural
guarantee) — and already a live correctness trap independent of performance: nesting a
non-flat formula (e.g. one `EQUALITY`/`CONJUNCTION` inside another) can silently produce
invalid CNF rather than erroring. This track treats §5.4/§8.5's existing writeup as
authoritative; not re-litigated here.

### 2.3 Hand-rolled bit-vector field encoding vs. SMT — bug evidence

IP/CIDR, port, proto, state, VLAN are all exploded into one-hot/per-bit propositional
literals by hand (`xmlutils.py`'s `Convert*ToVariables` family) — up to ~128 vars for one
IPv6 prefix on one rule side, no bitvector *theory* anywhere. Three concrete bugs already
found and fixed trace to this layer specifically (not the translator/adapter layer):
`CanonizeIP`'s `"::"` boundary-expansion bug, the hardcoded-IPv4-`version` bug that
silently corrupted IPv6 conditions, and the `packet.ipv4.*` field-name mismatch on a
pure-IPv6 benchmark. All three are exactly the class of bug hand-encoding typed data
(address family, prefix width) as untyped bit strings produces, and exactly what an SMT
bitvector theory (`bvult`, prefix extraction) would prevent by construction. §5.2
(Stanford/i2 LPM-at-scale) is SMT's home turf for this reason.

### 2.4 NEW (2026-08-24): the cyclic-topology soundness gap is a theory-level gap, not an
implementation drift bug — and it isn't confined to `InstantiateEndToEnd`

Working through §3.3's `trans(C)` formula in detail: its recursive grounding clause
(`trans(t,init) ∨ ∃ predecessor fired`) is plain material implication, which enforces
local consistency, not well-founded derivation. A purely self-referential cycle of
mutually-supporting transitions (A→B→C→A, none marked init) satisfies it forever without
ever bottoming out at a real init flag — the exact mechanism the wl_stanford B1
CEGAR/rank-constraint fix addresses for `InstantiateEndToEnd`
(`AD6_PLAN.md` §5.4 Stage B).

**This gap predates the FaVe integration — it's latent in the 2015 formalization itself**
(inherited via Jeffrey & Samak's model per `secrypt15.pdf` §2.2/§3). Checked which of
ad6's four native anomaly primitives share it, by reading the code
(`ad6/src/core/instantiator.py`) and empirically probing the vulnerable one (isolated
script in scratch space, no tracked files touched, no interference with the concurrent
session):

| primitive | grounding direction | status |
|---|---|---|
| `InstantiateReach` (→ `_run_reach`, and via composition `InstantiateShadow`/`_run_shadow`) | backward, ungrounded (`∃ incoming transition true`, no forced connection to real init) | **CONFIRMED vulnerable** — a disconnected orphan 3-cycle with zero edges to the model's only real init reports SAT ("reachable") for every node in the cycle; a genuinely dead acyclic control node correctly reports UNSAT, isolating the cause to the cycle specifically. |
| `InstantiateCross` (`_run_cross`) | backward, ungrounded — identical code shape to `InstantiateReach` (two independent "∃ incoming transition into Accept/Drop is true" checks, no init-grounding at all) | **Structurally identical to the confirmed-vulnerable case; not empirically cross-checked** — deferred at Claas's request (2026-08-24) as "rather exotic." Flagged here for whoever revisits this, not asserted as proven. |
| `InstantiateCycle` (`_run_cycle`) | **forward**, anchored at real `Kripke.IterInits` edges | **Safe.** The forced forward chase (`_CreateCycle`'s "every fired transition needs a fired successor") can only ever enter a cycle reachable via genuine edges from a real init, because the anchor disjunct is built directly from `IterFTransitions(Init)` for actual init nodes — a structurally different (and sound) construction from the other three. |
| `InstantiateEndToEnd` (FaVe-integration primitive, not in the 2015 paper at all) | two fully **independent** existential disjuncts (source's outgoing edge; destination's incoming edge), no shared connecting witness required | **Confirmed vulnerable** (this is the primitive the concurrent session's CEGAR fix targets) — and structurally *weaker* than even the paper's own flawed `reach_constraint`: it doesn't need one floating cycle to satisfy both disjuncts, two entirely unrelated ones could each satisfy one. |

**Practical implication:** patching only `InstantiateEndToEnd` (the concurrent session's
current scope) leaves `_run_reach`/`_run_shadow` — ad6's own native, paper-faithful
anomaly detectors — exposed to the same false-positive class on any real topology with a
cycle disconnected from init (a realistic pattern: an orphan jump-target chain never
wired into INPUT/OUTPUT/FORWARD, or a genuinely isolated network segment). Whether this
bites on Stanford/wl_up's actual graphs, as opposed to being a real-but-unexercised
latent risk, is an open empirical question — **deliberately not investigated further
here** to avoid duplicating/interfering with the concurrent session's own scope on those
benchmarks. This is a candidate for its own writeup (a previously-unpublished correction
to a decade-old published formalization), independent of the SAT-vs-SMT/QBF question:
**fixing it is a modeling-semantics fix (a rank/distance variable enforcing well-founded
grounding) — moving to SMT or a mature Tseitin conversion would carry the identical
unsoundness into a nicer syntax, not remove it.**

### 2.5 NEW (2026-08-24): a second, DISTINCT correctness bug — spurious UNSAT for an
init node that also receives a real incoming edge (implementation bug, not a theory gap)

Found while smoke-testing the H1/H2 harness's cyclic topology generator (§3) against
ad6's real pipeline — not a re-derivation of §2.4, a different mechanism entirely, and
the opposite failure direction (false negative, not false positive).

**Root cause:** `Instantiator._ConvertNodesToImplications` (`ad6/src/core/instantiator.py`)
is supposed to encode `trans(C)`'s `(trans(t,init) ∨ ∃ incoming transition fired)`
motivating disjunct (secrypt15.pdf §3.3) for the source of every outgoing edge. The code:

```python
if len(Transitions) > 1:
    Disjunction = XMLUtils.disjunction(); Disjunction.extend(Transitions)
elif len(Transitions) == 1:
    Disjunction = Transitions[0]
else:
    if XMLUtils.INIT in Node.Props:
        Disjunction = XMLUtils.constant()      # "OR init" -- only reachable here
    else:
        Disjunction = XMLUtils.constant(False)
```

The `XMLUtils.INIT in Node.Props` check — the "OR init" half of the paper's disjunction —
is only ever consulted when the node has **zero** incoming edges. The moment a node has
**any** real incoming edge in δ, the `if`/`elif` branch fires instead and the code
requires **one of those incoming edges to fire**, dropping "OR init" entirely — even when
the node genuinely is an init node. This is a mistranslation of the paper's formula, not a
gap in the formula itself (the paper's `trans(t,init) ∨ ∃...` is a plain, unconditional
disjunction, regardless of how many incoming edges exist).

**Effect:** an init node that also happens to receive a real incoming edge — an entirely
ordinary topology (e.g. a gateway/entry router that is also on a real forwarding loop) —
loses its "trivially motivated, no predecessor needed" property. A query that is
genuinely, structurally reachable from that init node can come back **spurious UNSAT**,
because the encoding wrongly demands an unrelated predecessor edge also fire, and that
edge's own guard can conflict with the query's real answer.

**Confirmed with a minimal, isolated repro**
(`ad6_encoding_bench/bug_init_node_incoming_edge.py`, no `ad6/` files touched): Router1
(init) forwards `db8::/32` traffic to Router2; Router2 accepts the specific destination
`beef::/64` (a subset of `db8::/32`) and otherwise loops back to Router1. `beef::/64`
traffic plainly flows Router1→Router2→ACCEPT without ever touching the loop-back edge —
yet `InstantiateReach`/`_run_reach` reports **UNSAT** (not reachable). Traced to exactly
this mechanism: forcing Router1's real outgoing edge additionally, wrongly, forces the
loop-back edge (Router2's fallthrough) to also fire, and that edge's own guard requires
the destination to *not* match `beef::/64` — a direct contradiction with the query's real
(and otherwise satisfiable) answer.

**Relationship to §2.4 and to the concurrent session's B1 work:** opposite failure
direction from §2.4 (spurious UNSAT here vs. spurious SAT there), different mechanism
(an implementation bug in the code's translation of `trans(C)`, not a gap in `trans(C)`
itself), found independently via this harness's own construction. **This is likely
relevant to the concurrent session's wl_stanford differential work** — any real topology
where a query's init/entry node also sits on a genuine incoming path (plausible for a
real backbone network) could hit this and report false UNSAT, independent of and in
addition to the floating-cycle CEGAR fix already built for `InstantiateEndToEnd`. Not
reported to or coordinated with that session — Claas's call whether/how to relay it.
**Not fixed here**, per the same reasoning as §2.4: this file tracks findings, it doesn't
patch `ad6/` core.

**Practical consequence for this harness:** the cyclic topology variant (§3) is affected;
all H1/H2 axis measurements below use the acyclic variant only, to avoid confounding
solver-engine/CNF-quality/encoding-technology comparisons with this bug's effect on
satisfiability itself.

## 3. Empirical probe plan for H1/H2 (design done, not yet executed)

To keep H1 and H2 from contaminating each other, treat solver engine, CNF-conversion
quality, and modeling layer as independent axes, measured on a small synthetic/reduced
benchmark (clean scaling curves, not one noisy real-benchmark data point):

- **Axis 0 (cheapest, do first):** swap the solver binary only — same DIMACS ad6 already
  produces, run through `cadical` or `cryptominisat` instead of
  minisat/clasp/pycosat. If this alone recovers a large chunk of the "too slow" gap,
  that's a cheap, striking result that reframes everything downstream.
- **Axis 1:** naive distribution vs. Tseitin CNF conversion, same propositional model,
  same solver — isolates the CNF-conversion-quality question (§2.2/`AD6_PLAN.md`
  §5.4/§8.5).
- **Axis 2:** hand-rolled bit-vector encoding vs. Z3/pysmt `QF_BV`, same solver
  underneath where possible — isolates "mature translator" from "solver engine" (per the
  bit-blasting point in the H1 assessment above).
- **Axis 3 (only if 1–2 don't explain the gap):** array/UF-theory FIB modeling — the one
  place a structural, not just engineering-maturity, win seems plausible.
- **Orthogonal to all of the above:** incremental/assumption-based solving for the O(n²)
  query architecture (`AD6_PLAN.md` §6's lever) — a query-architecture question, not an
  encoding question; measure separately.

**Environment (2026-08-24, this sandbox): installed and used.** `z3-solver` (pip, 5.1.0),
`cadical` (apt, 1.7.4), `cryptominisat` (apt, 5.11.15). Harness lives at
`ad6_encoding_bench/` (project root, sibling to `ad6/`) — outside `ad6/`, so it can't
collide with the concurrent session's files. See `ad6_encoding_bench/README.md` for how
to run it.

### 3.1 Results so far (2026-08-24, first pass — small synthetic microbenchmark)

Topology: a chain of N routers, each doing sequential (first-match) LPM-style
destination-CIDR forwarding, with R deliberately-disjoint distractor prefixes per hop
(stresses rule/bit-vector count — Factor B — without ever making satisfiability itself
combinatorially hard; that's intentional, to isolate build-side encoding cost from
solver-search difficulty). Built via ad6's real, unmodified, production pipeline
(`IP6TablesParser` → `GenUtils` → `Instantiator`) — the same path wl_ifi/wl_up/wl_stanford
go through. Caveat: this is a small microbenchmark, not Stanford/i2 scale, and it isolates
Factor B/build cost specifically — it says nothing yet about Factor A (query
amortization) or about genuinely hard (not just large) instances.

**Axis 0 (solver swap, zero encoding change) — modest, real signal.** Same DIMACS ad6
produces, run through 4 solver binaries. At n_routers=30, R=200/hop (~24k vars, 63k
clauses): `cadical`/`cryptominisat5` ≈0.066s vs `minisat`/`clasp` ≈0.115s — a consistent
~1.7× win for the modern engines, but all four stay sub-second. This problem class (LPM
chains) stays *easy* for every solver generation — no combinatorial struggle anywhere —
so the modern-solver edge here is a real but modest constant-factor effect (better
preprocessing/inprocessing), not a search-algorithm rescue. The genuinely hard case is
probably elsewhere (wl_up's stateful/VLAN cross-product, per §1.3's own table), not plain
LPM depth.

**Axis 1 (naive CNF vs. Tseitin, same formulas, verified equisatisfiable) — sharp, decisive
signal.** Monkeypatched `SATUtils.ConvertToCNF` to capture every pre-CNF formula ad6's own
pipeline builds (one per Kripke edge, `_ConvertNodesToImplications`), and ran both ad6's
own naive converter and a standard Tseitin converter (`ad6_encoding_bench/tseitin.py`) on
the identical formulas. Confirmed equisatisfiable on the largest captured formula (via
`cadical`). At n_routers=5:

| R/hop | naive time | naive clauses | Tseitin time | Tseitin clauses |
|---|---|---|---|---|
| 10 | 0.050s | 1,158 | 0.004s | 3,987 |
| 100 | 0.498s | 8,458 | 0.058s | 31,987 |
| 400 | 2.807s | 33,178 | 0.177s | 125,707 |

Tseitin produces **~3.8× more clauses** (expected — auxiliary variables per gate) but
converts **~16× faster at R=400**, and the gap widens with R (naive scales worse than
linear even on these shallow, per-edge formulas that never trigger the
alternation-depth blowup §5.4/§8.5 warn about — the cost here is ordinary superlinear
data-structure/recursion overhead in `_ConvertBinaryForm`/`_ConvertDNCToCNFRecurse`,
confirmed the dominant cost via `cProfile`: ~56% of total build time in this benchmark).
**This is the most actionable, least ambiguous finding of this pass**: Tseitin isn't only
the "safe against pathological blowup" fix §5.4/§8.5 already flagged — it's a strict,
substantial, unconditional build-time win even in the shallow-formula regime ad6 already
handles safely today.

**Axis 2 (own hand-rolled bit-vector encoding vs. native Z3 QF_BV) — sharp, decisive
signal, and it widens.** Same logical question (does some destination exist admitted
hop-by-hop to ACCEPT, same R disjoint distractor exclusions per hop reasoned about on both
sides), modeled two ways. ad6 end-to-end (parse+build+solve) vs. Z3 end-to-end
(build+`check()`), n_routers=5:

| R/hop | ad6 total | Z3 total | ad6/Z3 ratio |
|---|---|---|---|
| 10 | 0.153s | 0.021s | 7.4× |
| 100 | 1.061s | 0.070s | 15.1× |
| 400 | 5.399s | 0.269s | 20.1× |

The ratio **widens** with R (7×→20×), consistent with Z3's native bitvector handling
(prefix `Extract`, not per-bit boolean explosion) plus a mature Tseitin-quality frontend
staying closer to linear while ad6's own pipeline compounds the naive-CNF cost (Axis 1)
on top of the per-bit encoding cost.

**Reading these together:** at this (small, deliberately-easy, build-cost-isolating)
scale, most of the gap traces to **build-side encoding quality** (Axis 1's naive CNF
conversion, compounded by per-bit field encoding), not to solver-search difficulty (Axis
0 stays modest) or to any inherent SAT-vs-SMT solving disadvantage. This directly informs
Claas's H1: the naive CNF conversion specifically looks like the highest-leverage,
least-ambiguous target — not "SAT is inherently slower than SMT," but "this particular,
avoidable, already-self-flagged (§5.4/§8.5) implementation choice costs a lot, even in the
regime it was assumed to be safe in." Whether this generalizes to real benchmark scale
(Stanford/i2, wl_up) — where formulas are less uniform and Factor A (query count) may
dominate over Factor B (per-query build cost) — is not yet tested; that's the natural next
step once this preliminary read is reviewed.

### 3.2 Axis 3 (2026-08-25): array/UF/quantified FIB modeling — CONFIRMED, a genuine
structural win, not just mature tooling — with an important scope caveat

**Design note, worth recording because it reframes what "array/UF" should even mean
here:** a genuine LPM tie-break (narrower overrides wider) does *not* actually stress an
*existential* reachability query — a solver free to pick any satisfying witness address
just picks one matching the simplest/widest relevant rule, sidestepping the tie-break
entirely. Nesting only bites a query that fixes the address externally or asks "for all
addresses" — neither of which is ad6/FaVe's actual query shape (point existential
reachability, §1.2's own primitive table). So the honest structural-win candidate isn't
overlapping/nested prefixes — it's whether a *parametric family* of R otherwise-
independent (Axis-2-style, mutually disjoint) rules can be represented as **one
constraint over an index variable** instead of R ground instances, the way a real
contiguous routing range naturally could be, and the way a domain-specific tool's
"one flood answers all" (§1's Factor A) already exploits structure ad6 can't.

**Four encodings of the identical R rules** (a router with R "block this specific /64
sub-range" distractors, indexed 0..R-1 by a contiguous hextet value, plus the real
destination → ACCEPT), `ad6_encoding_bench/axis3_array_uf.py`: (1) ad6's real pipeline —
R separate ip6tables rules, the only way a real ruleset can literally be written; (2) Z3
QF_BV **ground** — R separate ground exclusions, mirroring Axis 2's style exactly, no
algebraic insight used; (3) Z3 QF_BV **collapsed** — hand-derived: since the R
distractors are a contiguous index range by construction, "excluded by some distractor"
collapses algebraically to one inequality (`hextet < R`); (4) Z3 **quantified** — an
actual `z3.ForAll` over the index variable, asking Z3's *own* quantifier instantiation to
find this automatically, rather than hand-deriving it — the fair test of "would
array/UF/quantified theory let the *solver* avoid enumerating R terms," not just "can a
human avoid it." All four agree (SAT) at every tested size.

| R | ad6 total | Z3 ground | Z3 collapsed | Z3 quantified |
|---|---|---|---|---|
| 10 | 0.059s | 0.0037s | 0.0016s | 0.0034s |
| 100 | 0.620s | 0.0255s | 0.0017s | 0.0018s |
| 1,000 | 7.71s | 0.173s | 0.0057s | 0.0029s |
| 5,000 | 58.5s | 0.771s | 0.0065s | 0.0023s |
| 20,000 | *(skipped — projected minutes)* | 3.26s | 0.028s | 0.0020s |

**ad6: severely superlinear (confirms §3.1's pattern at more extreme scale). Z3 ground:
roughly linear, ~150–200× faster than ad6 at R=1,000–5,000 but still O(R). Z3 collapsed
and Z3 quantified: both stay near-flat all the way to R=20,000** — Z3's own quantifier
instantiation (`ForAll`) finds essentially the same near-constant-time behavior as the
hand-derived algebraic collapse, **without being told the shortcut**. This is the
"structural, not just engineering-maturity" win the plan predicted, empirically
confirmed: ad6's architecture has no notion of a symbolic index variable at all — every
rule is grounded from the moment it's parsed — so this class of win is categorically
unavailable to it, not merely unoptimized.

**Important scope caveat, not yet tested — this is a best case, not a general result.**
This benchmark's R rules form a clean contiguous index range, a best-case structure for
bitvector quantifier reasoning (a tractable, Presburger-like fragment). §5.2's real
open question (Stanford/i2 LPM-at-scale, VLAN-admission cross-product) involves
semi-structured but *not* perfectly regular rule sets — arbitrary CIDR blocks, not a
clean `0..R-1` index. Whether Z3's quantifier instantiation still finds a comparable
shortcut on real FIB-shaped irregularity is genuinely unknown and is the natural next
step — this result is a validated proof-of-concept for the *mechanism*, not yet evidence
it closes §5.2's actual question.

### 3.3 Axis 3 follow-up (2026-08-25): tested against irregular FIB structure — the
structural win does NOT generalize, and fails cleanly rather than just degrading

Directly tests §3.2's caveat. `ad6_encoding_bench/axis3b_irregular_fib.py`: same logical
shape (R independent "block this prefix" distractors + real destination → ACCEPT), but
each distractor now has an independent, deterministically-pseudo-random (seeded) address
and prefix length (16–56 bits) — no arithmetic relationship to its index, i.e. no
contiguous range for a quantifier's decision procedure to collapse algebraically, unlike
§3.2's `hextet == i` structure. Three encodings: ad6's real pipeline; Z3 ground (R
separate ground exclusions, same style as §3.1/§3.2's "ground" baseline); Z3
**quantified-via-array-table** — the honest generalization of §3.2's `ForAll` idea to
irregular data: two Z3 `Array`s (`addr_table`, `len_table`, populated via R `Store`
operations — building the table is still O(R), there's no way around specifying R
independent rules) plus **one** `z3.ForAll` over the index variable referencing the
arrays, with a *symbolic* (data-dependent, not syntactic) mask width — the genuinely
"irregular" bit, since §3.2's fixed hextet slice no longer applies.

| R | ad6 total | Z3 ground | Z3 quantified-array |
|---|---|---|---|
| 10 | 0.057s | 0.0063s | 0.0226s |
| 100 | 0.386s | 0.0113s | 0.164s |
| 500 | 2.15s | 0.0372s | 20.08s (**timeout, `unknown`**) |
| 1,000 | *(skipped)* | 0.067s | 20.17s (**timeout, `unknown`**) |
| 5,000 | *(skipped)* | 0.443s | 20.91s (**timeout, `unknown`**) |

**The quantified-array approach isn't just slower on irregular data — it fails outright**
(hits a 20s timeout and returns Z3's honest "`unknown`", not a wrong answer) starting at
R=500, while it's already *slower than ground* even at R=10 (0.023s vs 0.006s). Z3
ground stays comfortably fast and roughly linear throughout, confirming it — not the
quantified/array approach — is the reliable, scalable encoding once there's no algebraic
regularity to exploit. `unknown` (not a false SAT/UNSAT) is the correct, safe behavior
for an undecidable-in-practice quantifier instance — a good sign for soundness, but it
means the technique provides no answer at all here, gracefully or not.

**Conclusion, closing §3.2's open caveat:** the array/UF/quantified structural win
confirmed in §3.2 is real but **narrow** — it depends on exploitable algebraic
regularity in the rule set (a contiguous index range, in that test). §5.2's actual open
question (Stanford/i2's real, irregular FIB/VLAN structure) does **not** have that
regularity, and on data shaped like it, the technique doesn't just fail to help — it
actively fails (times out) while adding overhead even at small scale. **This closes the
question for THIS mechanism**: quantified/array theory is not, by itself, the lever that
makes §5.2's LPM-at-scale tractable. Plain QF_BV with ground exclusions (Axis 2's
approach) remains the scalable fallback for irregular rule sets, at the ordinary
(non-structural) ~1–2 orders of magnitude speedup over ad6's own naive pipeline already
established in §3.1/§3.2 — not the further, near-flat win §3.2's best case showed.

**Honest gaps closed by §3.4 below:** the incremental/assumption-based-solving lever (§6,
Factor A) was untouched by Axes 0–3 (all Factor-B/build-cost questions) — see §3.4.
Remaining gaps: none of this has been run at real benchmark scale (Stanford/i2/wl_up);
whether some intermediate regularity (e.g. VLAN admission's own structure, distinct from
plain LPM) might be exploitable by a different quantifier formulation is unexplored —
§3.3's result rules out the naive "just add a ForAll" approach, not every conceivable
structured encoding.

### 3.4 Axis 4 (2026-08-25): the incremental/assumption-based-solving lever (§6, Factor A)
— CONFIRMED, and this is the most decisive result of the whole investigation

Orthogonal to Axes 0–3 (all Factor B / per-query build-cost, holding query count fixed).
This tests §6's actual proposal: does incremental/assumption-based solving amortize the
*query-count* problem — ad6 issuing one independent solve per query with zero state
carried between them, vs. a domain-specific "one flood answers all destinations"
traversal (§1's Factor A: "one graph flood yields n answers, one SAT solve yields 1") —
the single most damaging architectural gap in the whole cost model, more fundamental
than any encoding-quality question Axes 0–3 addressed.

`ad6_encoding_bench/axis4_incremental.py` + `xml_to_z3.py` (a direct ad6-XML-to-Z3-term
converter, no CNF involved — Z3 takes arbitrary Boolean structure natively). Three
encodings of "N independent reachability queries against one shared base," captured via
the same pre-CNF-capture monkeypatch as Axis 1: (1) **ad6 real** — `fave_bridge.py`'s
actual pattern, one fresh `PycoSATAdapter().Solve()` per query; (2) **Z3 fresh** — the
*same already-converted* Z3 term, but a brand-new `Solver()` + `add()` per query, no
state reuse — isolates "no incremental reuse" from "Z3 is a different engine" (Axis
0/2's question) by holding formula-construction cost fixed and identical to (3); (3)
**Z3 incremental** — one persistent `Solver()`, the base added once, N
`solver.check(assumption)` calls reusing internal propagation/learned-clause state.
**Correctness verified**: on a topology with a genuinely mixed reachable/unreachable set
(including a deliberately dead, unreferenced chain), (1) and (3) agree exactly, node by
node — the speed isn't coming from a wrong-but-fast shortcut.

**Isolated Factor-A test** — base topology **fixed** at 200 rules/nodes (holding Factor B
constant), only the number of queries against it varies:

| queries | ad6 fresh | Z3 fresh | Z3 incremental |
|---|---|---|---|
| 10 | 1.82s | 0.39s | 0.054s |
| 25 | 4.36s | 0.53s | 0.041s |
| 50 | 8.60s | 1.10s | 0.055s |
| 100 | 16.76s | 2.23s | 0.095s |
| 200 | 33.53s | 4.71s | 0.186s |

**ad6 fresh and Z3 fresh both scale linearly in query count** (as expected — each query
pays its own independent solve, ~0.17s/query for ad6, ~0.024s/query for Z3-fresh, the
latter gap being Axis 1/2's already-established build-cost story showing up per-query).
**Z3 incremental does not scale linearly — going from 10 to 200 queries (20×) only costs
~3.4× more time (0.054s→0.186s).** After the first query primes the shared base's
propagated units and learned clauses, each additional query against the *same* base
becomes progressively cheaper — a real, measured approximation of the "one flood
answers many" property domain-specific tools get architecturally and ad6 currently
doesn't.

**Why this result is more significant than Axes 0–3's:** it requires no special
algebraic regularity in the rules (unlike §3.2/§3.3's contiguous-range dependency) — it's
a general property of incremental solving over a shared base, so it isn't defeated by
irregular, realistic rule sets the way Axis 3's quantifier win was. It also targets
Factor A specifically, which the plan's own cost model (§1) identifies as ad6's most
fundamental architectural disadvantage — more so than any single encoding-quality choice
Axes 0–3 examined.

**Honest gaps closed by §3.5 below:** cross-source reuse (only destination varied here)
— see §3.5. Remaining gaps: still a small microbenchmark; not tested against FaVe's
actual stateful `<->>` 3-check queries; measures Z3's own incremental engine only, not
whether ad6's shipped solvers (`minisat`/`clasp`) could be driven incrementally via their
own APIs (both support this in principle — untested here).

### 3.5 Axis 5 (2026-08-25): cross-source incremental reuse — CONFIRMED, generalizes, and
query order barely matters

Closes §3.4's open gap: does the amortization survive when the *source*, not just the
destination, varies every query — the genuine n-by-n all-pairs shape FaVe's real
cross-family comparisons actually use? Uses ad6's real
`Instantiator.InstantiateEndToEnd(Source, Destination)` — the actual FaVe-integration
primitive (not §3.4's `InstantiateReach`, which only ever varies the destination against
the model's fixed init set) — so both of its two disjuncts (source's own outgoing edge;
destination's own incoming edge) vary independently per query.
`ad6_encoding_bench/axis5_cross_source.py`. Base fixed at 150 rules; K=15 candidate
nodes used as both sources and destinations, giving 210 genuinely distinct (source≠dest)
pairs.

**Correctness**: ad6 real vs. Z3 incremental match exactly across all 210 pairs.

**Scaling (fully-rotated order — the worst case for locality: zero consecutive queries
share either source or destination)**:

| pairs | ad6 fresh | Z3 fresh | Z3 incremental |
|---|---|---|---|
| 20 | 2.84s | 0.34s | 0.023s |
| 56 | 6.68s | 1.13s | 0.043s |
| 110 | 13.35s | 1.76s | 0.072s |
| 210 | 26.31s | 5.31s | 0.162s |

Incremental reuse **still works with both dimensions varying** — ~160–280× faster than
ad6 real, ~30× faster than Z3-fresh (so incrementality itself, not just engine choice,
is still doing most of the work) — though the amortization is somewhat less extreme than
§3.4's destination-only case (10.5× more pairs costs ~7× more time here, vs. ~3.4× for
20× more queries in §3.4) — consistent with less state staying "warm" when every query
touches a different source too, but still solidly sub-linear and still dominant.

**Bonus finding — query order barely matters.** Same 210-pair set, two visitation
orders: grouped-by-source (all of source A's queries, then all of source B's, …) vs.
fully-rotated (a stride permutation — zero consecutive queries share either source or
destination). Incremental time: **0.114s (grouped) vs. 0.130s (rotated) — only ~14%
difference.** This is good practical news: adopting incremental solving would not
require careful query scheduling by shared source to get most of the benefit; the
robustness comes from the shared base's own propagated units/learned clauses, not from
consecutive-query locality.

**Honest gaps closed by §3.6/§3.7 below:** wl_up-scale (n≈137) all-pairs testing (§3.6);
real wl_up rules + real stateful `<->>` queries (§3.7). Remaining gap: still only Z3's
incremental engine, not `minisat`/`clasp`'s own incremental APIs.

### 3.6 Axis 5 at wl_up scale (2026-08-25): n≈137, full n×(n−1) all-pairs matrix —
CONFIRMED at the project's own real benchmark scale, and the headline number is stark

Closes §3.5's remaining scale gap directly: n=137 is wl_up's *actual* role count
(`AD6_PLAN.md` §1.3's own table), and a full all-pairs matrix (source≠dest) at that n is
137×136 = **18,632 pairs** — close to §1.3's own "naive n²≈18.8k" estimate.
`ad6_encoding_bench/axis5b_wlup_scale.py`. Same mechanism as §3.5 (real
`InstantiateEndToEnd`, both source and destination varying, fully-rotated/scrambled
visitation order — the locality worst case), but at true scale, with one optimization
needed to make it tractable at all: per-node outgoing/incoming disjunctions are built
**once** (2×137 conversions, 0.019s) and combined per-pair via cheap `z3.And()`
composition, rather than reconverting from the XML tree per pair (§3.5's simpler
approach doesn't scale to 18.6k pairs).

**Practical necessity, stated plainly:** `AD6_PLAN.md` §5.1 documents ad6's real,
measured rate on the *actual* wl_up model at ~0.5s/query; a full 18,632-pair sweep at
that rate is hours, not something to literally run mid-session. So ad6-real and Z3-fresh
are measured on a real, timed 300-pair sample (well within this synthetic topology, at
this same n=137 base) and **extrapolated** linearly to the full matrix — justified
because every prior axis in this investigation (0, 1, 4, 5) already independently
confirmed ad6's own architecture scales linearly in query count, so this isn't a novel
assumption. **Z3 incremental was not extrapolated — it was actually run, in full, at all
18,632 pairs.**

| | 300-pair sample (measured) | full 18,632-pair matrix |
|---|---|---|
| ad6-real | 28.52s (0.095s/pair) | **~29.5 min (extrapolated)** |
| Z3-fresh | 3.79s (0.0126s/pair) | **~3.9 min (extrapolated)** |
| Z3-incremental | — | **8.04s (MEASURED, 0.00043s/pair)** |

**Correctness**: Z3-incremental's answers on the first 300 (of the full matrix's) pairs
match ad6-real's sampled answers exactly.

**The headline number**: at the project's own real benchmark's actual role count, this
mechanism turns an estimated ~30-minute all-pairs sweep into a *measured* 8-second run —
over **200× faster than ad6's real architecture, ~29× faster than a fresh-Z3-per-query
control** (so, consistent with every prior axis, incrementality itself — not just
engine choice — is carrying most of that). This is the most concrete data point in the
whole investigation because it's calibrated to a real number the project already cites,
not an arbitrary synthetic size.

**Important caveat, stated precisely so this isn't over-claimed:** this uses the same
simplified synthetic rule-chain topology as every other axis — matching wl_up's real
*role count* (n=137), not its real *rule content* (ACL/state/VLAN/routing complexity).
Tellingly, this synthetic topology's ad6-real rate (0.095s/pair) is already *faster*
than `AD6_PLAN.md` §5.1's documented real-wl_up rate (~0.5s/pair) — real wl_up's rules
are more complex per query, so both the ad6-real baseline *and* the Z3-incremental time
would likely be higher against the actual ruleset. **What's confirmed here is the
mechanism at true wl_up scale (n and query count), not yet the exact magnitude of the
win against wl_up's real rule complexity or its stateful `<->>` semantics** — that's the
natural remaining step if this direction is pursued further.

### 3.7 Axis 6 (2026-08-25): tested against wl_up's REAL rules and REAL stateful `<->>`
queries — CONFIRMED, no extrapolation needed this time

Closes §3.6's remaining gap directly, against the real thing rather than a proxy.
`ad6_encoding_bench/axis6_wlup_real.py` builds the actual FaVe+ad6 model via the real,
unmodified integration path — `fave/ad6/adapter.py`'s `Ad6Adapter` +
`util/in_process_driver.py`'s `InProcessFaVe`, exactly as `fave/test/test_ad6_wl_up.py`
does — calling `favemodel.build_config`/`instantiate_base` **in-process** (not through
`ad6/fave_bridge.py`'s subprocess boundary) so the real Kripke/CNF model is directly
available, the way every other axis in this harness works. Model: 137 generators, 137
probes, 159 devices, 5,977 Kripke nodes, ~10–15s build time — all matching
`AD6_PLAN.md`'s own documented counts exactly. Queries: real entries from
`bench/wl_up/cchecks.json` (11,902 total, 3,302 stateful) — 50 plain + 50 stateful
(mixing `related:0`/`related:1` `<->>` forcing), not synthesized. Each query answered
via `Instantiator.SolveAcyclicEndToEnd` — ad6's actual current production path,
including real src-CIDR seeding and state forcing (`fave_bridge.py`'s own
`_seed_literals`/`_state_literals`, called unmodified) — vs. Z3 fresh vs. Z3
incremental, same methodology as every prior axis. **Zero queries escalated to the
CEGAR/rank-constraint path** — confirms wl_up's real topology doesn't trigger the
floating-cycle gap (§2.4's Stanford-specific finding), so a plain-semantics Z3 model is
a fair, representative comparison here.

| | time | rate |
|---|---|---|
| ad6 real | 136.3s | 1.363s/query |
| Z3 fresh | 43.3s | 0.433s/query |
| Z3 incremental | **1.78s** | **0.018s/query** |

**~77× faster than ad6's real architecture, ~24× faster than a fresh-Z3-per-query
control — on the real model, real rules, real stateful queries, no extrapolation.**
Correctness: **exact match** with ad6 real across all 100 queries, plain and stateful
alike. This is the least hedged, most directly load-bearing result in the whole
investigation — no synthetic proxy, no scaling-law extrapolation, the actual production
path against the actual benchmark's actual compliance checks.

**One honest observation, not fully explained:** this sample's ad6-real rate
(1.36s/query) runs higher than `AD6_PLAN.md` §5.1's own documented ~0.5s/query. That
figure was measured for a fixed-destination, varying-source batch (closer to this
investigation's own §3.4 shape); this sample draws real, diverse (source, probe) pairs
from `cchecks.json` directly, which may simply hit costlier code paths more often, or
reflect ordinary environment/hardware variance — not chased down further here, since it
doesn't change the comparison's conclusion (Z3 incremental's own measured time is what
it is, independent of how the ad6-real baseline's rate is explained).

**A genuinely nice, if minor, side-confirmation:** `favemodel.gen_entry_key`'s own
docstring (`ad6/src/parser/favemodel.py`) independently describes the exact mechanism
behind §2.4's finding — "`KripkeUtils._ConvertNodesToImplications`'s INIT exemption...
only fires for a node with ZERO backward transitions... every device entry point... DOES
have a real predecessor once wire_edges connects the topology... marking it INIT anyway
does not exempt it" — and explains that real queries are deliberately routed through a
**dedicated injection node with guaranteed zero backward transitions** specifically to
route around this. So §2.4's finding wasn't novel to the codebase — it was already
understood well enough to be engineered around at the integration-design level, just not
fixed at the root (`_ConvertNodesToImplications` itself) or written up in `AD6_PLAN.md`.

**Honest gaps closed by §3.8/§3.9 below:** sample size and rate discrepancy (§3.8);
whether the lever is Z3/SMT-specific or general (§3.9, ad6's own solver family, tested).

### 3.8 Axis 6, scaled (2026-08-25): a larger sample, and Z3 incremental actually run on
ALL 11,902 real queries — twice, independently

`ad6_encoding_bench/axis6b_wlup_full_scale.py`. Same real model/queries/methodology as
§3.7, scaled two ways: (a) the ad6-real/Z3-fresh measurement sample grew from 100 to 300
(150 stateful, interleaved with plain rather than front-loaded, so the sample is
representative of the real mix); (b) **Z3 incremental was run for real on the entire
real query set — all 11,902 cchecks.json entries (3,302 stateful, 8,600 plain), not a
sample** — since §3.7's own rate implied well under 5 minutes for the full set, making it
worth actually measuring rather than extrapolating, unlike the other two.

| | 300-sample (measured) | full 11,902-query set |
|---|---|---|
| ad6 real | 180.7s (0.602s/query) | ~7,168s / **~2.0 hr** (extrapolated) |
| Z3 fresh | 63.2s (0.211s/query) | ~2,506s / **~41.8 min** (extrapolated) |
| Z3 incremental | — | **71.1s / ~1.2 min (MEASURED, full run)** |

**Correctness, doubly checked**: ad6-real matches Z3-fresh exactly on the 300-query
sample; ad6-real's sample also matches Z3-incremental's answers at the corresponding
positions in the full 11,902-query run. Both checks pass.

**This resolves §3.7's own open rate discrepancy.** §3.7's smaller (n=100) sample gave
an ad6-real rate of 1.36s/query, running notably higher than `AD6_PLAN.md`'s documented
~0.5s/query and left unexplained there. This larger, better-interleaved 300-sample gives
**0.602s/query — much closer to the documented figure** — consistent with §3.7's higher
number simply being sample-composition noise from a smaller draw, not a systematic issue
worth chasing further.

**A second, independent full-scale Z3-incremental run was also captured** (from the
validation pass before this section's own 300-sample run, same model, same full query
set): **101.6s**, vs. this section's **71.1s** — two independent measurements of the
identical 11,902-query workload, differing by ~30s. This is ordinary run-to-run
variance (system/cache/scheduling noise), not a methodological problem — both numbers
are almost two orders of magnitude below either extrapolated baseline, and neither
changes the conclusion.

**The headline, now on the most solid footing in the whole investigation:** processing
FaVe's entire real wl_up compliance-check suite — all 11,902 checks, including every one
of the 3,302 real stateful `<->>` checks — takes **~71–102 seconds** measured, against
an extrapolated **~2 hours** for ad6's real, currently-shipped architecture. Roughly
**100–140× faster**, correctness-verified twice, on the actual benchmark FaVe/ad6 are
compared against, not a proxy.

**Honest gaps closed by §3.9 below:** whether this is Z3/SMT-specific or a general SAT
property, testable via ad6's own solver family. Remaining: ad6-real/Z3-fresh stay
extrapolations for the full set (ad6-real alone would cost ~2 hours to literally run).

### 3.9 Axis 7 (2026-08-25): ad6's OWN solver family (Minisat), via its real native
incremental API — CONFIRMED, and even stronger than the Z3 result, plus a separable
bonus finding

Closes the last open item on this lever: is the incremental-solving win specific to
Z3/SMT technology, or would ad6's own already-shipped solver family (`minisat`) show the
same thing via *its* real incremental interface? `ad6_encoding_bench/
axis7_native_incremental.py` uses **PySAT** (`pysat.solvers.Minisat22`), which wraps the
MiniSat engine as a genuine incremental library call (`add_clause` any time,
`solve(assumptions=[...])` reusing internal state).

**Correction (2026-08-25, caught while scoping the integration into `AD6_PLAN.md`):**
the "ad6 real" baseline row below is `Instantiator.SolveAcyclicEndToEnd` running through
`PycoSATAdapter` (`src.solver.pycosat`) — the actual `fave_bridge.py` production path,
confirmed by reading `ad6/fave_bridge.py` directly. `PycoSATAdapter` wraps `pycosat`, a
native library, **not** a CLI subprocess (`axis7_native_incremental.py` line 141;
`MiniSATAdapter`, imported at line 47, is used only to borrow
`AbstractSolver._ConvertToDIMACS`'s numbering scheme for building the DIMACS bridge, not
run as the baseline). The original framing below — "ad6 real (CLI subprocess)" and the
~24× bonus as a CLI→library swap — was wrong: production already uses a native library.
Traced further (`AD6_PLAN.md` §6, `ad6/src/core/instantiator.py:180-215`,
`ad6/src/solver/solver.py:27-90`): every query pays for a `deepcopy()` of the entire base
CNF tree plus a full from-scratch Python-level DIMACS renumbering, regardless of solver
backend — *that's* what PySAT-fresh (below) avoids by reusing a precomputed base, not a
CLI-vs-library difference. The **timing numbers themselves are unaffected** — same
harness, same runs — only their causal explanation changes. Left uncorrected below (with
this note) rather than rewritten in place, so the actual runs stay traceable to what was
literally measured; read "CLI subprocess" in the rest of §3.9 as "ad6's current
per-query-fresh-rebuild architecture" instead.

**Methodology note — this is arguably a *more* faithful test than the Z3 version.**
PySAT's assumptions must be single literals (unlike Z3's arbitrary-formula assumptions),
so each query's disjunction (source's own outgoing edges; destination's own incoming
edges) needed a manual Tseitin OR-gate auxiliary variable, built directly against **ad6's
own DIMACS variable numbering** — reusing `AbstractSolver._ConvertToDIMACS`, the exact
method `MiniSATAdapter`/`ClaspAdapter` already call before shelling out. So this tests
"ad6's own encoding, solved incrementally via its own solver family's native interface,"
not a different formula representation the way Z3's arbitrary-Boolean-term model was.

Same real wl_up model and real `cchecks.json` queries as §3.7/§3.8. n=300 (150
stateful):

| | time | rate |
|---|---|---|
| ad6 real (CLI subprocess) | 204.3s | 0.681s/query |
| PySAT/Minisat22 fresh (native lib, no reuse) | 8.67s | 0.029s/query |
| PySAT/Minisat22 incremental (native, reused) | **0.176s** | **0.00059s/query** |

**Correctness**: both PySAT fresh and PySAT incremental match ad6-real exactly across
all 300 queries.

**PySAT incremental was also run on the entire real 11,902-query set — for real, not
extrapolated: 16.6s.** Faster than either of §3.8's two independent Z3 full-scale runs
(71.1s, 101.6s). (Not read as "Minisat beats Z3" — the two use different auxiliary-
variable strategies and problem representations, not a controlled head-to-head; both
independently confirm the same qualitative phenomenon, which is the point.) Against the
extrapolated ad6-real full-set time (~8,105s / ~2.25 hr, consistent with §3.8's own
extrapolation), that's **roughly 490× faster** — the largest ratio in the whole
investigation.

**This confirms the lever is not an SMT/Z3-specific artifact.** ad6's own native solver
family gets the same — here, even larger — amortization via its real incremental API.
The current CLI-subprocess architecture, not the choice of solver engine, is what's
actually costing the O(n) per-query overhead.

**A separable bonus finding, worth calling out on its own:** PySAT-fresh (**no**
incrementality — a brand-new solver per query, just using the native library instead of
a CLI subprocess) is *already* ~24× faster than ad6-real by itself. That's a real,
distinct, lower-effort win available independent of adopting full incremental solving —
simply switching `MiniSATAdapter` from CLI-subprocess-per-query to a native library
binding (PySAT or direct linking) would already recover a substantial fraction of the
overall gap, before any incremental-state-reuse work at all. Worth flagging as a
separate, smaller, easier first step, distinct from the incremental-architecture change
this whole lever (§3.4–3.9) has been about.

**Honest gaps:** `clasp` (ASP-oriented, no simple pip-installable incremental Python
binding found within reasonable effort) not tested — only `minisat`, via PySAT, was;
PySAT-vs-Z3 full-run timing difference (16.6s vs 71–102s) isn't a controlled comparison
and shouldn't be read as one.

### 3.10 Axis 8 (2026-08-25/27): the incremental lever against the REAL Stanford
differential — RESCUES the B1 wall-clock NO-GO for the tested primitive

Direct follow-up from the integration discussion: wl_up (§3.7-3.9) never exercises
`SolveAcyclicEndToEnd`'s escalation path at all (zero of its queries are on a cycle), so
those results say nothing about whether the lever survives Stanford's real
cyclic-topology rank-constraint cost — the actual thing that made the B1 differential a
NO-GO (`AD6_PLAN.md`'s B1 write-up: 6h budget, 74/256 (28.9%) complete, 40/74 escalated at
7.7s-2923s each, ~20-21h extrapolated for a full run). Three attempts, in
`ad6_encoding_bench/`:

**Attempt 1 (`axis8_stanford_incremental.py`) — died silently, no traceback.** Root cause,
confirmed by fix: `sys.setrecursionlimit(10**6)` (set at import, matching `ad6/main.py`'s
own convention) combined with the shell's default 8MB `ulimit -s` lets a deep recursive
operation blow the real C stack and segfault with zero Python-catchable output — the
process just vanishes. Cgroup `memory.events` showed `oom_kill 0`, ruling out an OOM
kill. **This is a previously-unknown, still-live robustness bug in ad6's own core**,
independent of anything else in this investigation: `fave_bridge.py` runs as a subprocess
inheriting its parent's ulimits, so any real Stanford (or other cyclic-topology) run is at
risk of this exact silent crash if the parent process's stack limit is at the OS default —
worth its own fix/flag regardless of the lever question. Not yet relayed into
`AD6_PLAN.md`'s core-bugs tracking as of this writing — should be.

**Fix confirmed**: re-running with `ulimit -s unlimited` let the ad6-real sample (via
`Instantiator.SolveAcyclicEndToEnd`/`PycoSATAdapter`, the actual production path) complete
cleanly: 5 queries, 2 escalated at **2164.64s and 2259.70s each** (~36-38 min, consistent
with — near the upper end of — B1's original 7.7s-2923s range), 3 fast-path in <1s. This
is real, fresh ground truth on the exact real 16-router topology, not an extrapolation.

**Attempt 2 (`axis8b_stanford_incremental_only.py`) — Z3, INCONCLUSIVE, not a negative
result on the lever itself.** Building the entire rank-constrained base as a Z3 term
(443,963 extra clauses, from the PRE-CNF nested formula, matching axis6's own Z3-capture
convention) was itself cheap (~84s total: rank-constraint build 19.8s + base XML→Z3 4.2s +
rank clauses→Z3 52.4s + persistent-solver load 0.3s) — but `solver.check()`, the actual
per-query solve, never returned even ONCE in 90 minutes, fresh or incremental. Read
carefully: this implicates Z3's *term-based* construction of a huge nested
implication/equality tree specifically (Z3 has to internally Tseitin-transform + reason
over it from scratch), not the incremental-solving *principle* — ad6's own solver
(`pycosat`) already solved the identical logical content (slowly, via CEGAR's repeated
full reconversion, see above), so the underlying problem is not inherently intractable for
a DIMACS/CDCL engine.

**Attempt 3 (`axis8c_stanford_pysat.py`) — PySAT/Minisat22 on ad6's OWN already-CNF'd
representation — SUCCEEDED, cleanly.** Stayed entirely within the flat, already-Tseitin'd
DIMACS form `favemodel.instantiate_base` already produces (exactly what `fave_bridge.py`
uses in production) plus `_CreateAcyclicConstraints`'s own already-CNF'd output — converted
to DIMACS **once** (213,125 vars, 504,346 clauses, 1.81s) and loaded into a **persistent**
`Minisat22` instance (0.17s) — no CEGAR needed (the rank encoding is sound by construction
via a plain solve, per its own docstring). Result:

| | |
|---|---|
| DIMACS base+rank one-time build | 0.17s (+ 15.95s rank-constraint build + 1.81s DIMACS conversion) |
| **PySAT incremental, ALL 256 real Stanford pairs** | **971.09s (~16.2 min), 3.79s/query average** |
| Correctness vs. known ad6-real (5 pairs) | **0 mismatches** |
| ad6-real (production architecture), for comparison | 2 of 5 sampled queries alone took >73 min combined; B1's own extrapolation for a full 256-query run: ~20-21 hours |

**A concrete illustration of the mechanism, not just the aggregate**: query 2
(`bbrb_rtr`→`bbra_rtr`) is the SAME pair that took **2164.64s** under ad6-real's
CEGAR/fresh-reconversion architecture — here it took **~102.7s** (elapsed jumped from
0.170s to 102.847s). Query 3 (`boza_rtr`→`bbra_rtr`), the pair that took **2259.70s** under
ad6-real, took **~0.15s** here (elapsed 102.847s→103.001s) — the learned clauses from
query 2's solve carried over almost entirely. This is the lever's whole thesis, observed
directly on the two specific pairs already known to be the expensive ones, not inferred
from an aggregate.

**This rescues the B1 NO-GO for the primitive tested** (`SolveAcyclicEndToEnd`'s pure
reachability question) — the full real 256-pair all-pairs matrix, previously unable to
finish in 6 hours, completes in ~16-23 minutes with this architecture, correctness-verified
against ad6's own current answers on the overlapping sample. **Follow-up, DONE
2026-08-27**: fed all 256 answers through B1's own differential-against-NetPlumber
oracle-comparison logic (`ad6_encoding_bench/axis8d_stanford_netplumber_diff.py`, mirrors
`test_ad6_wl_stanford.py`'s own `test_reachability_matches_netplumber` exactly — a live
NetPlumber worker, not `reachable.json`, not a recorded snapshot) — **EXACT MATCH, 0
diffs across all 16 roles**. This closes the loop: not just "matches ad6's own prior
answers" but "matches the independent oracle." **Since applied to production**
(`ad6/src/solver/incremental.py`, wired into `ad6/fave_bridge.py` — see
`AD6_PLAN.md` §6).
- The escalated-query pattern in this run (query 2 alone: ~102.7s, the single largest
  jump, then rapidly amortizing to ~3.8s/query average by the end) suggests the FIRST
  hard query pays most of the real solving cost and later queries reuse learned clauses
  heavily — consistent with the lever's whole thesis, not a coincidence.
- Per-query progress was only logged at fixed checkpoints (1-10, then every 20th) — the
  exact per-query cost curve past query 10 isn't fully visible, only the running average.
- This is still the harness's in-process reconstruction of the real model
  (`Ad6Adapter`+`InProcessFaVe`+`favemodel`, same as every other Axis 6+ script) — not yet
  a `fave_bridge.py`/`Instantiator` production change.

## 4. Open questions / next steps

- [x] Install z3/cadical/cryptominisat and build the isolated microbenchmark harness —
  done, `ad6_encoding_bench/`. See §3.1 for first-pass results.
- [x] Axis 0 (solver swap) — done, modest (~1.7×) real signal, see §3.1.
- [x] Axis 1 (naive vs Tseitin) — done, sharp/decisive (~16× at R=400, widening), see §3.1.
- [x] Axis 2 (own encoding vs Z3 QF_BV) — done, sharp/decisive (7×→20×, widening), see §3.1.
- [x] Axis 3 (array/UF/quantified FIB modeling) — done, CONFIRMED as a genuine
  structural win (near-flat scaling to R=20,000 vs. ad6's severe superlinear growth),
  with an important caveat: tested only on a clean contiguous-range best case, not on
  real (irregular) FIB structure. See §3.2.
- [x] Test Axis 3's structural win against irregular FIB structure — done, CLOSED: the
  win is narrow (depends on exploitable algebraic regularity), fails outright (Z3
  `unknown`, not just slower) on irregular data starting at R=500. See §3.3. Plain QF_BV
  ground exclusions remains the scalable approach for real (irregular) rule sets.
- [x] Axis 4 — incremental/assumption-based solving (§6, Factor A) — done, CONFIRMED,
  the strongest positive result of the investigation: near-flat scaling in query count
  vs. ad6's/Z3-fresh's linear growth, verified correct on a mixed reachable/unreachable
  case. See §3.4.
- [x] Cross-source incremental reuse — done, CONFIRMED: still ~160–280× faster than ad6
  real with both source and destination varying every query; query visitation order
  (grouped-by-source vs. fully-rotated) barely matters (~14% difference). See §3.5.
- [x] wl_up-scale (n≈137) full all-pairs matrix (18,632 pairs) — done, CONFIRMED: Z3
  incremental actually run at full scale (8.04s measured); ad6-real/Z3-fresh
  extrapolated from a measured sample (~29.5 min / ~3.9 min). See §3.6. Caveat: synthetic
  topology matches wl_up's role count, not its real rule complexity or stateful `<->>`
  semantics.
- [x] Test against wl_up's real rules and real stateful `<->>` queries (not the
  synthetic proxy) — done, CONFIRMED with no extrapolation needed: ~77× faster than ad6
  real, ~24× faster than fresh-Z3, exact-match correctness across 100 real (plain +
  stateful) `cchecks.json` queries. See §3.7.
- [x] Scale to a larger sample and the full 11,902-query set — done, CONFIRMED: Z3
  incremental actually run on ALL 11,902 real queries, twice independently (71.1s and
  101.6s), vs. an extrapolated ~2 hours for ad6-real (~100–140× faster); the earlier
  rate discrepancy resolved (larger sample's rate closely matches `AD6_PLAN.md`'s
  documented figure). See §3.8 — the most solidly-grounded result in the investigation.
- [x] Whether ad6's own shipped solvers support the same incremental/assumption pattern
  via their native APIs, not just Z3's — done, CONFIRMED for `minisat` (via PySAT):
  ~490× faster than ad6-real extrapolated, full 11,902-query set actually run in 16.6s
  (faster than either Z3 full run). Bonus: native-library-vs-CLI-subprocess alone (no
  incrementality) is already ~24× faster — a separate, smaller, easier win. `clasp` not
  tested (no simple incremental Python binding found). See §3.9.
- [ ] Scale this harness up toward real benchmark territory (more routers, genuinely
  harder — not just larger — instances) to test whether the build-cost-dominated picture
  from §3.1 holds, or whether a genuinely hard SAT instance changes the picture.
- [x] Decide whether §2.4's theory-level soundness gap (`InstantiateReach`/`_run_shadow`,
  and likely `InstantiateCross`) gets its own fix/writeup, and how/when it feeds back into
  `AD6_PLAN.md`/the concurrent session's scope — **done independently by the concurrent
  session itself**, which found the identical gap from the paper's own formalization and
  scoped its own B1 fix's claims against it (`AD6_PLAN.md`, the B1 write-up under §5.4,
  commit `e712ec25`). No action needed here.
- [x] §2.5's implementation bug (spurious UNSAT, distinct from §2.4) — **relayed into
  `AD6_PLAN.md` 2026-08-25** (the B1 write-up's new "second scope caveat"), now that the
  concurrent session has ended; confirmed still present, unfixed, in current
  `ad6/src/core/instantiator.py:556-608`.
- [ ] `InstantiateCross` empirical cross-check — deferred per Claas (2026-08-24), "exotic."
  Revisit only if it becomes relevant to a real benchmark's cross-path checks.
- [x] Reconcile this file with `AD6_PLAN.md` — done 2026-08-25, the concurrent session's
  wl_stanford work ended and its results are committed/pushed. `AD6_PLAN.md` §6 now carries
  the lever's confirmed status and cross-links back here; kept as two separate files (this
  one as the detailed methodology/findings record, `AD6_PLAN.md` §6 as the integrated
  summary), not merged, since this file is significantly more granular than a single
  section warrants.
- [ ] **New, from the integration discussion (2026-08-25):** implement the DIMACS-base-
  caching fix (§3.9's correction) in `ad6/src/core/instantiator.py`/`ad6/fave_bridge.py` —
  test-first, no architecture change, keeps `pycosat`.
- [x] **New, from the integration discussion (2026-08-25):** prototype the incremental
  lever against the real Stanford/i2 differential specifically (not wl_up) — done
  2026-08-27, CONFIRMED: the lever survives real cyclic-topology rank-constraint escalation
  cost and rescues B1's wall-clock NO-GO for `SolveAcyclicEndToEnd`'s own reachability
  question — full real 256-pair Stanford all-pairs matrix in ~16.2 min vs. B1's own
  6-hour/28.9%-complete measurement, 0 mismatches. Took 3 attempts (Z3's term-based
  construction never completed even one solve; flat-DIMACS/PySAT-Minisat22 succeeded
  cleanly) and surfaced a new, still-open C-stack-overflow robustness bug along the way.
  See §3.10.
- [x] **New, from §3.10 (2026-08-27):** decide on the C-stack-overflow robustness bug — **FIXED
  2026-08-27**: `ad6/src/bigstack.py` (`run_with_big_stack`) runs `fave_bridge.py`'s
  `main()` in a thread with an explicit 256MB stack, portable and independent of the
  launching shell's ulimit. Wired into `fave_bridge.py` only (the real production entry
  point); `main.py`'s demo CLI left unchanged (bigger refactor, lower value, not
  attempted). Test-first (`testRunWithBigStackIsATransparentWrapper`, confirmed failing
  pre-fix); the crash itself wasn't reproduced as a fast synthetic unit test (calibration
  attempts didn't finish in reasonable time — CEGAR cost dominates first at any small
  enough scale) — justified by the real Stanford A/B run instead. No regression: `ad6 make
  test` (10 suites) + a real `fave_bridge.py` smoke test via `Ad6Adapter`/`InProcessFaVe`.
- [x] **New, from §3.10 (2026-08-27):** feed Axis 8's 256 real answers through the same
  NetPlumber oracle-comparison logic `test_ad6_wl_stanford.py` uses — **DONE, EXACT
  MATCH**: `ad6_encoding_bench/axis8d_stanford_netplumber_diff.py`, 0 diffs across all 16
  roles, comparing the full real wl_stanford data plane against a live NetPlumber worker
  (not `reachable.json`, not a recorded snapshot). Solve took 1361.07s this run (heavier
  concurrent load than the standalone 971.09s measurement); NetPlumber worker itself only
  9.74s. This is the strongest possible correctness confirmation available for this work
  — not just "matches ad6's own prior answers" but "matches the independent oracle."
  Along the way, fixed a pre-existing environment gap blocking this entirely:
  `liblog4cxx.so.15` wasn't installed in this sandbox, so `NetPlumberLibAdapter`
  (`fave/netplumber/lib_adapter.py`) silently couldn't import `libnetplumber` and every
  test depending on it (including `test_ad6_wl_stanford_plain.py`'s own N=2 live
  differential) errored — `apt-get install liblog4cxx15 liblog4cxx-dev
  libcppunit-1.15-0` fixed it, confirmed via that test going from 2 errors to 11/11
  passing.
- [x] **New, from §3.10 (2026-08-27):** build the incremental architecture into
  `ad6/fave_bridge.py` for production use — **DONE**. `ad6/src/solver/incremental.py`
  (`IncrementalSession`); only `fave_bridge.py`'s call site changed, `Instantiator`'s own
  methods untouched. New dependency `python-sat` (Dockerfile). Verified via `ad6 make
  test` + 36 real fave-side ad6 tests through the actual subprocess bridge, all green;
  wl_ifi's full 219-pair compliance run now 0.81s. See `AD6_PLAN.md` §6 for the full
  writeup.
