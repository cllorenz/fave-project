# Plan: Faithful HSA Modelling in APKeep (soundness track)

**Goal.** Eliminate APKeep's reachability **over-approximation** on the HSA-style
`wl_stanford` workload by making APKeep's forwarding *faithful* to NetPlumber (the
reference), rather than accepting a sound superset. This is "option (2)" from the
2026-08 discussion — a deep, core-touching change, chosen over accepting the
over-approximation (option 1/3) because a verification backend that silently reports a
path the real network drops is not fit for purpose.

**Context / what we already know** (detail in [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md)):
- APKeep is **provably exact** where its model matches: `wl_ifi` and `wl_i2`
  (`missing=0, extra=0`). The over-approximation is specific to Stanford's 3-stage HSA
  representation (in-port permutation at the out-stage, shared L2 `/23` segments,
  priority-subtraction pipe algebra).
- The residual false positive (`bbra→rozb`) resisted an entire session of
  root-causing across the model, the adapter, NP flow-dumps, NP's C++
  (`Node::propagate`), and NP TRACE (which segfaults in a trace-only path at the
  decisive step). NetPlumber's split-horizon (`should_block_flow`) is real but
  **dormant** in this model; the exact mid-stage mechanism remains **unpinned**.
- The discard/`Null0` gap is a *separate*, already-fixed issue (commit `886a2082`).

**Guiding principle.** The failure mode this session was **committing to a fix before
understanding the target**. So: every step produces a *checkable artifact*, every step
is gated on the already-exact workloads staying exact, and **no core change happens
until we have an evidence-backed spec of what "faithful" means** (Phase 0c gate).

---

## Phase 0 — Foundations & guardrails (no core changes)

### 0a. Freeze a regression safety net — DONE (2026-08-12)
Pin the proven-exact behaviour as the tripwire for every later step: `wl_ifi`
(`missing=0/extra=0`), `wl_i2` (77k build, exact oracle), `wl_stanford` P7a, the 25
Java unit tests, the backend-differential test.
- **Quality gate:** one command runs all green; becomes the mandatory pre-commit check.
- **Retires:** silent regression of the workloads APKeep already gets exactly right.
- **Artifact:** `fave/test/exactness_gate.sh` — composes (does not redefine) the
  exactness-critical subset into one green/red command that prints
  `EXACTNESS GATE: PASS/FAIL`: (1) APKeep Java core unit tests (`mvn test`, 25
  green), (2) bundled-Stanford loop golden pin, (3) regenerate wl_ifi/wl_i2/
  wl_stanford inputs from tracked sources, (4) the four exactness pytests
  (`test_apkeep_wl_ifi`, `test_apkeep_i2`, `test_apkeep_stanford`,
  `test_backend_differential`). Run as
  `PYTHON=/path/to/venv/python bash fave/test/exactness_gate.sh` (~40 s). Confirmed
  PASS at this commit. This is the mandatory pre-commit tripwire for every later step.

### 0b. Build the convergence harness (the objective metric) — DONE (2026-08-12)
Differential harness: APKeep vs NP over a *family* of induced subsets (2-, 3-, k-router)
reporting the over-approximation as a tracked number (`bbra→rozb` present; full-stanford
77 vs 10), plus a per-flipped-pair check against **config-derived ground truth**.
- **Quality gate:** reproduces the known divergences; prints one "over-approx count" we
  watch shrink; committed and runnable.
- **Retires:** "did my change help / break soundness?" being opinion. Every later step
  is judged by this number.
- **Artifact:** `fave/bench/apkeep_convergence.py`. Drives wl_stanford through BOTH
  backends (each in its own subprocess — the JVM/NP cross-contamination and APKeep's
  one-network-per-process limit forbid sharing) and prints the tracked
  `CONVERGENCE: over_approx=N under_approx=M SOUND/UNSOUND` line. Reference oracle = NP
  (reachable.json is the artificial all-to-all policy, not the data plane).
  **Confirmed at this commit:** full 16-router model APKeep=240 vs NP=10 →
  `over_approx=230 under_approx=0 SOUND`. Soundness is a HARD gate: `under_approx` (a
  real NP path APKeep drops) must stay 0; the harness exits non-zero otherwise — that is
  the "never introduce a false negative" tripwire, so NP itself serves as the
  config-derived ground truth for every flipped pair (NP is the reference, cross-
  validated against APKeep on wl_ifi where they agree exactly).
  `--routers a,b,...` induces a subnetwork. **Reproducer for 0c:** `--routers
  bbra_rtr,rozb_rtr` isolates the over-approximation to the single pair `bbra→rozb`
  (NP reaches rozb→bbra but not bbra→rozb; APKeep reaches both). CAVEAT: a naive subset
  poses a new self-contained forwarding problem, not a slice preserving the full-model
  verdict — it is a minimizer of the divergence, not a reproducer of a specific pair's
  full-model answer.

### 0c. Nail the NP semantics — HARD GO/NO-GO GATE
Produce a written, evidence-backed spec of the exact NP forwarding behaviour we must
replicate — the artifact we could **not** produce this session. Get NP to *tell* us
what it does, via one of:
- (a) fix the TRACE-mode segfault (crashes in a trace-only `hs_to_str`/`array_to_str`
  path — likely a null; small NP patch), then trace the `.204`-from-bbra case; or
- (b) a **minimal reproducer inside NP's own C++ test suite** (a 2-router hand-built
  model reproducing `bbra→rozb`) — far more controllable than the full JVM/JPype stack.
- **Quality gate:** a short spec stating precisely which mechanism blocks the flow
  (pipe-intersection? priority-subtraction? out-stage?) with trace/reproducer evidence.
- **Retires:** the exact trap that cost us this session — designing against a guessed
  mechanism.
- **NO-GO rule:** if 0c cannot produce the spec within a bounded effort, **stop and
  reassess** (fall back to option 1 or 3) rather than do core surgery blind. This gate
  is the plan's main risk control.

---

## Phase 1 — Design against the spec

### 1a. Identify the minimal missing capability
From the 0c spec, name the smallest gap (candidates: in-port-qualified out-stage
forwarding; split-horizon; shared-segment delivery). Deliberately resist "reimplement
HSA in APKeep."
- **Quality gate:** a one-page design naming the single capability + why it's minimal.

### 1b. Soundness + AP-count analysis *before* code
Write the soundness argument (the change may only remove spurious reachability, never
real reachability) and a worst-case atomic-predicate count analysis — the VLAN-rewrite
path already showed how a header-dimension addition explodes APs (~8000, intractable).
Choose the representation (structural/port dimension vs header field) on that basis.
- **Quality gate:** written soundness argument + AP-count bound; reviewed against the
  `NATElement.isMergable` / minimum-EC (Thm 1) invariants.
- **Retires:** (i) introducing unsoundness, (ii) building something correct-but-intractable.

### 1c. Prototype on a hand-built micro-network (Java)
A JUnit test with a 2–3 port network isolating *only* the new capability (e.g. a 2-way
in-port permutation + a shared segment), independent of the full Stanford model.
- **Quality gate:** the micro-test passes with the new capability, fails without it.
- **Retires:** debugging a new primitive inside the 8000-AP Stanford model.

---

## Phase 2 — Implement incrementally, behind a flag

### 2a. Core capability in vendored APKeep (test-first, gated)
Implement in the Java core so default behaviour is byte-identical; the new path is opt-in.
- **Quality gate:** new JUnit tests + all 24 existing green + jacoco coverage ratchet
  held + `apkeep/FAVE_CHANGES.md` updated (MIT state-changes); **separate
  apkeep-subtree commit** per the vendoring rule.
- **Retires:** core regression, licensing/hygiene drift.

### 2b. Wire the adapter to use it for the out-stage (behind a `faithful` flag)
Replace the over-connecting collapse (`_collapse_out_stage`/`_out_perm`) with the
faithful path.
- **Quality gate:** the 0a suite still exact; the 0b harness number drops (e.g. subset
  `2→1`); **zero new false negatives** (every reachable→unreachable flip checked against
  config ground truth).
- **Retires:** the fix "working" on one pair while breaking others or over-dropping.

---

## Phase 3 — Validate convergence, soundness, scale

- **3a. Convergence:** run the 0b harness at full scale; target `77→10` (or
  characterize + document the residual). Every flip validated vs ground truth.
- **3b. Scale/perf:** measure AP count + build time under the faithful path against the
  Phase-1b bound; must stay tractable (the whole point of APKeep) or be documented.
- **3c. Lock it in:** promote the differential result to a CI gate (APKeep ≡ NP on the
  validated set).
- **Quality gates:** harness number at target; perf within bound; new CI test committed.

---

## Phase 4 — Generalize & document

Confirm the capability also serves the deeper `isMergable` / `wl_up` state-rewrite gap
(or scope it), then update `APKEEP_BACKEND.md`, `apkeep/FAVE_CHANGES.md`, and the thesis
writeup.
- **Quality gate:** docs reviewed; an explicit statement of what soundness now holds and
  on which workloads.

---

## Cross-cutting quality measures (apply to every step)
- The **0a exactness suite** is the non-negotiable tripwire on every commit.
- The **0b harness number** is the objective progress metric throughout.
- Every **reachable→unreachable flip** is checked against config-derived ground truth
  (soundness — never introduce a false negative).
- All `apkeep/` changes are **separate subtree commits** with `FAVE_CHANGES.md` entries
  (MIT vendoring hygiene).

## Sequencing & the decision point
Start Phase 0 in order. 0a and 0b are low-risk and immediately useful. **0c is the
make-or-break gate:** if NP's exact semantics can't be extracted even from its own test
harness within a bounded effort, that is strong evidence (2) is research-scale, and we
reconsider scope *before* spending on core surgery — not after.
