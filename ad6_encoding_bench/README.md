# ad6 encoding microbenchmark harness

Supports `../AD6_ENCODING_PLAN.md` §3 (Claas's H1/H2 hypotheses about ad6's own CNF
conversion vs. a more expressive solver). Entirely outside `ad6/` — never touches or
imports anything from the concurrent wl_stanford session's working files, only ad6's
stable core modules (`GenUtils`, `IP6TablesParser`, `Instantiator`, `SATUtils`, solver
adapters).

## What's here

- `gen_topology.py` — synthetic N-router LPM-forwarding-chain generator, built through
  ad6's real, unmodified production pipeline. `cyclic=True` currently triggers a real bug
  (see `bug_init_node_incoming_edge.py` / AD6_ENCODING_PLAN.md §2.5) — **use `cyclic=False`
  for anything you actually want an answer from** until that's resolved.
- `bug_init_node_incoming_edge.py` — minimal isolated repro of that bug. Run directly.
- `tseitin.py` — standalone Tseitin CNF converter for ad6's XML formula representation,
  the Axis 1 comparison baseline.
- `axis0_solver_swap.py` — same DIMACS ad6 produces, timed through minisat/clasp (ad6's
  own) vs. cadical/cryptominisat5 (modern CDCL). `python3 axis0_solver_swap.py [max_n]`.
- `axis1_tseitin.py` — monkeypatches `SATUtils.ConvertToCNF` for one process lifetime to
  capture every pre-CNF formula ad6's real pipeline builds, then compares ad6's naive
  converter against `tseitin.py` on the identical formulas (includes an equisatisfiability
  self-check via cadical). `python3 axis1_tseitin.py [n_routers] [distractors_per_router]`.
- `axis2_smt.py` — the same LPM decision problem modeled natively in Z3 (`BitVec`/
  `Extract`), compared end-to-end against ad6. `python3 axis2_smt.py [n_routers] [distractors_per_router]`.
- `axis3_array_uf.py` — a parametric family of R disjoint rules, encoded 4 ways (ad6
  real; Z3 ground; Z3 hand-collapsed range; Z3 `ForAll`-quantified) to test whether
  array/UF/quantified theory gives a genuine structural win over enumerating R ground
  terms. `python3 axis3_array_uf.py`.
- `axis3b_irregular_fib.py` — same question, but on deterministically-pseudo-random,
  irregular (address, prefix-length) rules with no algebraic relationship to their
  index — tests whether Axis 3's win survives without a contiguous range to exploit.
  `python3 axis3b_irregular_fib.py`.
- `xml_to_z3.py` — direct ad6-XML-formula-to-Z3-term converter (no CNF involved).
- `axis4_incremental.py` — orthogonal to Axes 0–3: does incremental/assumption-based
  solving over one shared base amortize query count (§6's Factor-A lever)? Compares
  ad6's real per-query-fresh-solve pattern against a fresh-Z3-per-query control and a
  genuinely incremental one-persistent-solver-many-assumptions version, with a
  base-size-fixed isolation of query-count scaling specifically. `python3
  axis4_incremental.py`.
- `axis5_cross_source.py` — Axis 4 follow-up: does the amortization survive when the
  *source*, not just the destination, varies every query (ad6's real
  `InstantiateEndToEnd`, the genuine n×n all-pairs shape)? Also tests whether query
  visitation order (grouped-by-source vs. fully-rotated) changes the benefit. `python3
  axis5_cross_source.py`.
- `axis5b_wlup_scale.py` — same question at n≈137 (wl_up's real role count), full
  n×(n−1)=18,632-pair all-pairs matrix. Z3 incremental is actually run in full; ad6-real/
  Z3-fresh are measured on a sample and extrapolated (a full run would take ~30 min).
  `python3 axis5b_wlup_scale.py`.
- `axis6_wlup_real.py` — the real thing: builds the actual FaVe+ad6 wl_up model
  in-process (`Ad6Adapter`+`InProcessFaVe`+`favemodel`, read-only use of `ad6/`/`fave/`'s
  existing modules) and answers real `bench/wl_up/cchecks.json` queries (plain and
  stateful `<->>`, via ad6's real `SolveAcyclicEndToEnd` production path) three ways.
  Run from `ad6_encoding_bench/`: `python3 axis6_wlup_real.py [n_plain] [n_stateful]`.
- `axis6b_wlup_full_scale.py` — scales Axis 6 up: a larger ad6-real/Z3-fresh sample, and
  Z3 incremental run for real on **all 11,902** real `cchecks.json` queries (not a
  sample). `python3 axis6b_wlup_full_scale.py [sample_size]`.
- `axis7_native_incremental.py` — is the incremental win Z3/SMT-specific, or does ad6's
  own solver family (Minisat) show it too via its real native incremental API (PySAT's
  `Minisat22`, not the CLI subprocess `MiniSATAdapter` uses)? Same real wl_up
  model/queries. `python3 axis7_native_incremental.py [sample_size]`.

## Running

```
cd ad6_encoding_bench
PYTHONPATH=../ad6 python3 axis0_solver_swap.py
PYTHONPATH=../ad6 python3 axis1_tseitin.py
PYTHONPATH=../ad6 python3 axis2_smt.py
```

Requires (installed 2026-08-24 in this sandbox): `minisat`, `clasp` (ad6's own, apt),
`cadical`, `cryptominisat` (apt), `z3-solver` (pip, in the project `.venv`).

## Results

See `AD6_ENCODING_PLAN.md` §3.1/§3.2 for the numbers and their reading. Headline: at
this (small, deliberately build-cost-isolating) scale, most of the ad6-vs-modern gap
traces to the naive CNF conversion (Axis 1, ~16× at R=400/hop) and the hand-rolled bit-vector
field encoding (Axis 2, 7×→20× vs. Z3, widening with rule count) — not to solver-search
difficulty (Axis 0, a modest ~1.7×). **Axis 3 confirmed a genuine structural (not just
tooling-maturity) win on a clean contiguous-range best case**: representing R disjoint
rules as one quantified constraint instead of R ground terms stays near-flat to
R=20,000 in Z3 (both hand-collapsed and via Z3's own `ForAll`). **But Axis 3b shows this
does NOT generalize to irregular (realistic) FIB structure** — on rules with no
algebraic relationship to their index, the same quantified-array approach is already
slower than plain ground exclusions at R=10, and times out (Z3 `unknown`) entirely by
R=500. Plain QF_BV with ground exclusions remains the scalable, reliable approach for
real (irregular) rule sets — the near-flat quantifier win is real but narrow, not a
general answer to §5.2's LPM-at-scale question.

**Axis 4 is the strongest result of the whole investigation**: incremental/assumption-
based solving over a shared base (§6's Factor-A lever) — a *general* property, not
dependent on any algebraic regularity in the rules — gives near-flat scaling in query
count (20× more queries costs only ~3.4× more time) where both ad6's real architecture
and a fresh-Z3-per-query control scale linearly, verified correct on a mixed reachable/
unreachable case. This targets ad6's most fundamental architectural gap (Factor A, per
§1's cost model), not an encoding-quality question like Axes 0–3.

**Axis 5 confirms this survives genuine cross-source variation** (ad6's real
`InstantiateEndToEnd`, both source and destination varying every query, 210 pairs):
still ~160–280× faster than ad6 real, ~30× faster than a fresh-Z3 control, verified
correct against ad6's own answers. Query visitation order (grouped-by-source vs.
fully-rotated) barely matters (~14% difference) — no careful scheduling needed to get
most of the benefit.

**Axis 5b confirms this at wl_up's actual scale** (n=137, full 18,632-pair all-pairs
matrix): Z3 incremental actually run in full — **8.04s measured** — against an
extrapolated ~29.5 min for ad6-real and ~3.9 min for Z3-fresh (both extrapolations from
a real, timed 300-pair sample; every prior axis already confirmed ad6's linear
query-count scaling, so this isn't a novel assumption). Over 200× faster than ad6's real
architecture, at the project's own real benchmark's real role count. Caveat: synthetic
topology matches wl_up's role count, not its real rule complexity or stateful `<->>`
semantics — the mechanism is confirmed at true scale, not yet the exact magnitude against
wl_up's real rules.

**Axis 6 closes that gap for real, no extrapolation**: the actual FaVe+ad6 wl_up model
(137 generators, 137 probes, 5,977 Kripke nodes), 100 real `cchecks.json` queries (50
plain + 50 stateful `<->>`, real `related:0`/`related:1` forcing) — **1.78s measured for
Z3 incremental vs. 136.3s for ad6 real (~77×) and 43.3s for Z3 fresh (~24×)**, exact-match
correctness across all 100. Zero queries needed the CEGAR/rank-constraint escalation
path, confirming wl_up's real topology doesn't hit the floating-cycle gap (§2.4), so this
comparison is representative, not a lucky easy case.

**Axis 6b scales this to the entire real benchmark**: Z3 incremental was actually run —
twice, independently — on **all 11,902** real `cchecks.json` queries (3,302 stateful,
8,600 plain): **71.1s and 101.6s**, vs. an extrapolated **~2 hours** for ad6's real
architecture and **~42 minutes** for a fresh-Z3 control. Roughly **100–140× faster**,
correctness-verified against ad6-real at every step. This is the most solidly-grounded
result in the whole investigation — the actual benchmark, not a sample, not a proxy.

**Axis 7 confirms the lever isn't Z3/SMT-specific**: ad6's own solver family
(`minisat`), driven via its real native incremental library API (PySAT's `Minisat22`,
not ad6's own CLI-subprocess `MiniSATAdapter`) — **~490× faster than ad6-real
extrapolated**, full 11,902-query set actually run in **16.6s** (faster than either of
Axis 6b's two Z3 full runs, though not a controlled engine-vs-engine comparison).
**Bonus, separable finding**: switching from CLI-subprocess to a native library call
*alone* (no incrementality at all) is already ~24× faster than ad6-real by itself — a
smaller, easier win available independent of adopting full incremental solving.
