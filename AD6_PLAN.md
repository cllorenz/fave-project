# ad6 → FaVe backend: a generic SAT/QBF model checker for comparison

**Status:** PLANNING (2026-08-20). Owner: Claas Lorenz. Companions:
[`APKEEP_NDD_PLAN.md`](APKEEP_NDD_PLAN.md), [`APKEEP_NDD_EVAL.md`](APKEEP_NDD_EVAL.md),
[`APKEEP_BACKEND.md`](APKEEP_BACKEND.md); tracked as item 11 in [`TODO.md`](TODO.md).
This plans integrating **ad6** — the author's
SAT/QBF model checker for IPv6 firewalls/networks (`ad6/`, SECRYPT'15) — as a **fourth
verification family** alongside NetPlumber (HSA), APKeep(BDD), and APKeep(NDD), for a
*controlled* cross-family comparison.

---

## 0. Thesis — why a generic model checker is worth the effort

The point is **not** to show a generic solver is slower than a specialised one (a foregone
conclusion), but to characterise **why**, **by how much**, and **where the trade-off
inverts** — and to place BDD-APKeep as the analytical bridge between the two worlds.

- **The solution space is 2-D, not a line.** Two orthogonal axes:
  - *Representation of packet sets:* explicit/ternary (HSA/NetPlumber) → symbolic-BDD
    (APKeep) → symbolic per-field (NDD) → clausal SAT/QBF (ad6).
  - *Algorithm:* topology graph-traversal over precomputed equivalence classes
    (HSA/AP/NDD — the domain-specific reachability algorithm) vs generic fixpoint /
    constraint solving (ad6: Kripke + SAT/QBF).
  In this space ad6 is generic on **both** axes; **BDD-APKeep is a deliberate hybrid** —
  a *symbolic set representation borrowed from model checking* (BDD) driving a
  *domain-specific* AP-graph algorithm. (Precise: APKeep's BDDs represent packet-header
  *sets*, not a transition relation; there is no symbolic fixpoint over a state space.
  Say "symbolic set representation," never "symbolic model checking.")

- **Two-factor cost model for "why slower" (theory + measurement).**
  - **Factor A — query amortisation.** NP/APKeep/NDD exploit topology structure so one
    source-flood answers all destinations: all-pairs ≈ **O(n) floods** (n = endpoints/
    roles). ad6 issues independent solves; the FPL `<->>` operator needs **3 checks per
    ordered pair**, so worst case **O(3·n²) solves**. Even at equal per-unit cost, the
    generic path does ~n× more work units because it cannot reuse a source across
    destinations. (Note: ad6's raw `_run_reach` is already **O(n)** per direction — one
    SAT instance per Kripke node — so the n² is a property of the *policy-compliance*
    semantics, not of reachability per se. Pin this down in §1.)
  - **Factor B — per-unit cost.** A SAT/QBF solve over the whole encoded model vs a graph
    flood over precomputed equivalence classes. **Factor B grows with model size (rules).**

- **The headline hypothesis (large network, small n).** Stanford/Internet2 are large in
  *rules* but small in *roles* (n). Since build ∝ rules and query-count ∝ n², the generic
  approach may be **uncompetitive on wl_up (large n) yet competitive on Stanford/i2 (small
  n)** despite those being "bigger" — an intuition-flipping result. The offset is that
  Factor B *grows* on the bigger models, so which wins is genuinely unknown → **worth
  measuring; the two benchmark classes cleanly separate the axes.**

- **Expressiveness × performance is the real trade-off.** ad6 can check properties the DS
  tools *structurally cannot express* (temporal / QBF-quantified properties, firewall
  anomaly classes). The genericity you pay for buys expressiveness — the write-up must show
  **both** sides, not just a speed race.

- **BDD-APKeep as the instrumented bridge.** The BDD-APKeep build profiler already splits
  time into `encode_ms`+`insert_ms`+`ppm_ms`+`merge_ms`+`split_count` (BDD/AP
  *representation-maintenance* — the "MC-flavoured" part) vs the graph flood (the
  *domain-specific* part). §2.6b showed representation-maintenance is what explodes on the
  faithful models and traversal stays cheap. So we can quantify, with existing traces, how
  much of the specialisation payoff lives in shrinking the representation layer.

---

## 1. Theory first (cheap, de-risks the engineering) — DO THIS FIRST

Rationale: the theory tells us which measurements are decisive and whether the
incremental-SAT lever (§6) is worth building *before* any code revival.

- **1.1** Write down the two-factor cost model (Factor A / Factor B) and the per-solve cost
  as a function of model size, for ad6 vs {NP, APKeep, NDD}.
- **1.2** Characterise ad6's decision problems precisely from the code
  (`src/core/instantiator.py`: `InstantiateReach` / `InstantiateCross` /
  `InstantiateCycle`) and the FPL `<->>` semantics: confirm the O(n) reach vs O(3·n²)
  policy-compliance counts, and whether a single instance can answer one-source→all-dests.
- **1.3** Predict the per-benchmark regime table (wl_up large-n; wl_tum; Stanford/i2
  small-n): expected build cost, query count, and which factor dominates.
- **1.4 GO/NO-GO gate:** with 1.1–1.3 in hand, decide (a) which benchmarks are worth the
  integration effort, (b) whether to build the incremental-SAT lever up front, (c) whether
  Stanford/i2 modelling in ad6 is feasible or out of scope (see §5 risk). **Do not start
  code revival until this is decided.**

---

## 2. Metric & methodology alignment (shared with the controlled-environment effort)

- **2.1** Unify every tool on **build cost + per-query cost × query count** (ad6's "base
  model once, reused across runs" fits this exactly). ad6 already emits instantiation-time
  vs solve-time separately and computes median/stdev (+ `yappi`) — reuse that.
- **2.2** Define the **query unit** explicitly: per ordered pair, with the `<->>` 3×
  constant stated; document whether one-source→all-dests is achievable (feeds §6).
- **2.3** Cross-family fairness: NP is C++, APKeep is JVM, ad6 is Python+native SAT
  binaries (minisat/clasp) or `pycosat`. Report total wall **and** a warmed/steady
  component; separate the language-runtime tax from the algorithm.
- **2.4** SAT-solver variance: clasp/minisat use restarts/heuristics → high variance. Fix
  seeds where possible, run N repeats, report median + spread. Prefer one primary solver;
  keep the others as a sensitivity check.
- **2.5** Peak RSS per tool (not just internal table bytes), matching §2.6b's lesson.

---

## 3. Revive & harden ad6

- **3.1** Code-quality pass: `ad6/` is 2014 proof-of-concept. Inventory deps (`lxml`,
  `yappi`, `pycosat`, external `minisat`/`clasp` binaries), get `make test` green, modernise
  where needed **without changing semantics** (vendoring hygiene: separate commits +
  a `FAVE_CHANGES`-style changelog, mirroring the APKeep/NDD discipline).
- **3.2** Reproduce the **known baseline**: the prior one-off end-to-end reachability run on
  a wl_up variant (~36 min). This is the correctness/perf anchor. Identify *exactly which*
  wl_up variant it used — if it differs from today's wl_up, that reintroduces the
  "explain-the-difference" problem we hit with Stanford; resolve it now, not later.
- **3.3** Pin the ad6 env (Python deps + SAT-solver binaries + versions) in the shared
  `Dockerfile` alongside NP/APKeep/NDD.

---

## 4. Integrate with FaVe

- **4.1 Integration level — DECIDE (assess, don't assume).** Two paths:
  - **(A) `AbstractVerificationEngine` backend** — an ad6 adapter implementing the same
    seam APKeep uses (`add_generator/add_link/add_probe/add_rules/.../check_*`), building
    ad6's Kripke model from FaVe's `add_*` calls.
  - **(B) Model translation** — emit ad6's native inputs (ip6tables rulesets + network/
    Kripke config) from the FaVe model and drive `main.py`. ad6 is natively
    ip6tables-driven (`src/parser/iptables.py: IP6TablesParser`), and it ships
    `bench/up` + `bench/tum` rulesets that already share the UP/TUM lineage, so (B) may be
    the lower-friction path. First read: (B) for reach, (A) only if we want live/incremental.
- **4.2** Wire the reachability query so ad6 answers the **same source→probe matrix** as
  NP/APKeep/NDD.
- **4.3 Differential correctness gate:** ad6 vs NetPlumber (the oracle) on wl_ifi + wl_up;
  **soundness is the hard gate** (ad6 must never drop an NP-reachable pair). Same discipline
  as the APKeep/NDD differentials.

---

## 5. Extend to all benchmarks

- **5.1** wl_up, wl_tum — ad6's home turf (IPv6 firewalls; rulesets already in
  `ad6/bench/{up,tum}`). Lowest risk; gets the large-n end of the curve.
- **5.2 Stanford, Internet2 — the small-n hypothesis test (§0). REAL FEASIBILITY RISK.**
  ad6 is IPv6-firewall/anomaly-oriented (its parser is `IP6TablesParser`; Stanford/i2 are
  **IPv4 forwarding** networks with **VLANs**). Encoding pure IPv4 LPM forwarding (+ VLAN
  match/rewrite) as an ad6 Kripke/SAT model is **substantial modelling work, not a config
  toggle** — it is the crux effort, and it must clear the §1.4 gate. Owner's position:
  "matter of effort, not principle" — accepted, but the plan treats it as a scoped task
  with its own feasibility check, not a freebie.
- **5.3** Faithful-VLAN Stanford/i2 variants: likely **out of scope** for ad6 (it is not a
  forwarding/VLAN data-plane tool); revisit only if 5.2 succeeds and there is appetite.

---

## 6. Algorithmic lever — amortise the O(n²) toward O(n) (optional, high value)

Directly attacks Factor A: for a fixed source, solve the n destination queries under solver
**assumptions**, reusing learned clauses across them — a warm single solver session
approximating a flood — collapsing O(n²) toward ~O(n). More aggressive: a **QBF encoding
quantifying over destinations**. Measures "how close a generic solver gets to a
domain-specific flood by amortising." If it works, the comparison tightens dramatically; if
not, *why not* is itself a finding. Decide up-front vs post-baseline at the §1.4 gate.

---

## 7. Measurement & write-up

- **7.1** "Price of genericity" section: the two-factor decomposition, **scaling curves**
  (gap vs network size and vs n), and the crossover analysis (wl_up vs Stanford/i2).
- **7.2** Expressiveness × performance table: properties each family can/can't express.
- **7.3** The BDD-APKeep phase-split bridge figure (representation-maintenance vs traversal).
- **7.4** Keep this **separate** from the clean 3-engine reachability comparison and the NDD
  faithful-VLAN result — ad6 is its own contribution/section, not a fourth column bolted
  onto the reachability matrix.

---

## Cross-cutting guardrails (reused from the APKeep/NDD work)
- **Soundness gate:** ad6 must never drop an NP-reachable pair (differential vs NP oracle).
- **Env pinned** in the shared `Dockerfile`; measurements only trusted on the controlled
  (bare-metal) environment.
- **Vendoring hygiene:** ad6 edits as separate commits with a changelog.
- **Metric stated explicitly** (build + query×count), reported both cold and warm.

## Open decisions (resolve at the §1.4 gate)
- Integration level: (A) `AbstractVerificationEngine` backend vs (B) model translation.
- Stanford/i2 feasibility in ad6's encoding (IPv4 forwarding + VLAN) — go/no-go.
- Incremental-SAT lever (§6): build before or after the baseline measurement.
- Primary SAT solver (clasp vs minisat vs pycosat) for the headline numbers.
- Whether faithful-VLAN variants are in scope for ad6 at all.

---

## TODO checklist
- [ ] **§1.1** Write the two-factor (A/B) + per-solve cost model vs {NP, APKeep, NDD}.
- [ ] **§1.2** Confirm ad6's reach vs `<->>` policy-compliance query counts from the code
      (`Instantiator`, FPL semantics); check one-source→all-dests feasibility.
- [ ] **§1.3** Predict the per-benchmark regime table (build/query-count/dominant factor).
- [ ] **§1.4** GO/NO-GO gate: benchmark scope, Stanford/i2 feasibility, lever timing.
- [ ] **§2** Fix the shared metric (build + query×count), fairness protocol, solver-variance
      protocol; confirm reuse of ad6's built-in instantiate/solve timing split.
- [ ] **§3.1** Get `ad6` `make test` green; inventory + modernise deps (changelog).
- [ ] **§3.2** Reproduce the ~36 min wl_up reachability baseline; identify the exact variant.
- [ ] **§3.3** Pin ad6 env (Python deps + SAT binaries) in the Dockerfile.
- [ ] **§4.1** Decide integration level (A vs B) from a scoping pass.
- [ ] **§4.2** Wire ad6 to answer the source→probe matrix.
- [ ] **§4.3** Differential vs NetPlumber on wl_ifi + wl_up (soundness gate).
- [ ] **§5.1** Enable wl_up + wl_tum end-to-end through the integrated path.
- [ ] **§5.2** Feasibility spike: IPv4 forwarding (+VLAN) encoding for Stanford/i2.
- [ ] **§6** (optional) Prototype incremental-SAT source-amortisation; measure O(n²)→O(n).
- [ ] **§7** Write the "price of genericity" section + expressiveness table + bridge figure.
