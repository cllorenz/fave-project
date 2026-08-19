# APKeep → NDD: preservation + integration plan

**Status:** PLANNING (2026-08-17). Prerequisite context: Phase C is DONE — the FaVe/
APKeep(BDD) backend builds the full 136-device wl_up model from zero in ~11.5 min and
matches NetPlumber **exactly** (0 diffs, 3660/3660 pairs). The residual build cost is a
per-field **cross-product** in APKeep's single global atomic-predicate partition; the
sizing measurement shows building the dst vs proto/port dimensions *separately* costs
**~29× less PPM** at 8 subnets (ratio growing). The **NDD** paper (Li, Zhang, Zhang,
Yang, *"NDD: A Decision Diagram for Network Verification"*, NSDI '25) generalises exactly
that decomposition to **all fields** and provides it as a reusable library — so NDD is
the principled successor to the hand-rolled two-universe split (Phase E, Lever C), which
is retained only as a fallback. This doc plans (1) preserving/publishing the current
BDD state and (2) integrating NDD.
Owner: Claas Lorenz. Companion to [`APKEEP_TUM_UP_PLAN.md`](APKEEP_TUM_UP_PLAN.md),
[`APKEEP_BACKEND.md`](APKEEP_BACKEND.md), and `apkeep/FAVE_CHANGES.md`.

**Artifacts referenced.** Paper: `nsdi25-li-zechun.pdf` (in repo root). NDD library:
`github.com/XJTU-NetVerify/NDD` (~2K LOC Java, built on JDD — the same BDD lib our fork
uses). Reference NDD-integrated verifier: `github.com/XJTU-NetVerify/apkeep` (vanilla
APKeep on NDD; the integration was **+66 / −311 JDD LOC**, the −311 being APKeep's own
atom-maintenance that NDD replaces natively).

---

## 0. Why NDD, and its honest limits for *our* workload

- **NDD hits our dominant term at the root.** An atomized NDD computes atoms **per
  field**, so the total atom count is `Σ_f(atoms in field f)` instead of the `Π_f`
  cross-product — precisely our `D×F → D+F` collapse, but general and library-provided.
  Their atoms then grow ~linearly with network size.
- **NDD is a good structural fit for us specifically (IPv6).** The paper's cited BDD pain
  — deep bit-recursion to align 104-bit 5-tuples — is *worse* for us (256 bits: 128-bit
  IPv6 src + dst). NDD collapses each 128-bit field to a single NDD variable, removing the
  tax we pay hardest. Same JDD base, so no engine-family mismatch.
- **Critical magnitude caveat.** The 100× is *multi-layer* datacenter nets. On
  *single-layer* nets (our analog): Stanford/Internet2 ≈ **1×** (match mostly dstIP),
  Purdue **3×** (more multi-field ACLs). wl_up is more field-diverse than those, and our
  own ~29× sizing is the best predictor — but this is **not** a 100× situation, and the
  paper's §6.6 shows NDD **degrades** when rules match many fields. wl_up's anti-spoof
  rules match src+dst+in/out-port. ⇒ **field locality must be measured, not assumed
  (§2 GO/NO-GO below).**

---

## Part 1 — Preserve & publish the current BDD state

Goal: (a) reproducible numbers for a possible publication, (b) ability to restore this
exact state, (c) a home for future backported bugfixes. **Git alone does NOT achieve
this** — the 2026-08-17 container reset wiped Java, `bison/flex/m4`, `python3-dev`, and
the scratchpad while git was untouched, destroying our result artifacts. "Restore" has
three independent legs:

### 1.1 Code — a tag *and* a maintenance branch
- Cut an annotated tag (proposed: `fave-apkeep-bdd-v1`) at the exact publication commit.
  Immutable, precise; the frozen baseline the paper cites.
- Keep a maintenance branch (the current `apkeep` branch) as the *living* BDD version for
  backported bugfixes. Tag = frozen; branch = maintained. Both, not either.

### 1.2 Environment — pin it (it is load-bearing and currently only "documented" by
having been reinstalled)
- Audit/refresh `Dockerfile` to capture **exactly** the runtime deps the reset removed:
  Java 11 (openjdk-11-jre or -jdk), `bison`, `flex`, `m4`, `python3-dev` (`Python.h`),
  JDD jar, pybison + the full `.venv` stack. Pin versions.
- Rationale: pybison compiles its parser at runtime and segfaults without `bison` +
  `Python.h`; the JVM+pybison combo is what crashed post-reset. Without a pinned env the
  performance numbers are not reproducible — the whole point of the exercise.

### 1.3 Eval artifacts — commit them, out of scratchpad
- The reset already destroyed `mat_apk.json`, `full_AB.jsonl`, and the harness scripts.
  Move the harness (`up_diff.py`, the streaming profiler driver, `c1c_xprod` prober) and
  the golden result matrices into the repo (proposed: `fave/bench/wl_up/eval/`) and
  commit. Scratchpad is never again a preservation location.

### 1.4 Two reframings that raise the bar
- **The BDD version is the published *baseline*, not an archive.** The paper mirrors the
  NDD paper's APKeep(BDD) vs APKeep(NDD) structure, so the BDD numbers are a *comparison
  point* and must reproduce on the pinned env.
- **Re-measure the *timing* headlines on the pinned env before freezing.** Correctness
  numbers (3660/3660, exactness gate) are deterministic and safe as-is. But the build-time
  headlines (692 s, the Lever A/B deltas, ~29×) were produced on the pre-reset environment
  that no longer exists; a different Java build can shift timings. Re-run on the documented
  env so the frozen numbers actually reproduce.

### 1.5 Maintenance model — shared adapter, two engines
- Our Python adapter is essentially **backend-agnostic** (emits rule strings + edges); the
  Java engine is what diverges for NDD. Structure: **one shared adapter, two engines
  (BDD, NDD)**. Modeling bugfixes land in the adapter and benefit both; engine fixes are
  branch-scoped. Document this so "backport" has a defined meaning.

### Part 1 deliverables
Tag; refreshed pinned `Dockerfile`; committed `eval/` harness + golden matrices;
re-measured timing table with provenance (commit + env + command); a short RESULTS doc
freezing the headline numbers; documented maintenance/backport policy.

---

## Part 2 — NDD integration

Methodology spine (endorsed): **test the library → study the authors' vanilla-APKeep
integration → abstract it → apply to our fork**, gated throughout by differential
correctness. Refinements below; the frozen BDD baseline (Part 1) is the **test oracle**,
so Part 1 precedes Part 2.

### 2.0 GO/NO-GO gate — measure wl_up field locality (do FIRST, cheap)
- Measure the rule → #fields-matched distribution across the wl_up model (FIB dst rules;
  service filters proto/port; anti-spoof src/dst/in-out-port; related/ipv6header).
- Decision rule: mostly 1–2 fields (orthogonal) ⇒ strong NDD case, proceed. Many rules
  spanning 4–5 fields ⇒ we are in the paper's §6.6 degradation regime ⇒ reconsider before
  investing. **Do not start integration until this number is in hand.** Predicts whether
  we're near Purdue's 3× or well above (our ~29× sizing suggests above).

### 2.1 Trust the library — differential vs BDD, on OUR profile
- NDD wraps JDD, so the oracle is **differential against BDD**: build random multi-field
  predicates as BDD and NDD, apply the same `and/or/not/exist/atomize/update`, assert
  semantic equivalence (extract the represented packet set and compare).
- Must-haves specific to us: test on the **128-bit IPv6 src+dst** profile (not the paper's
  IPv4 — `createVar(len)` at 128 bits is exactly where research code breaks); test the
  **`atomize`/`update`** APIs (what our atom-maintenance depends on), plus RONDD canonicity.
- Scope to the API subset we will actually use; do not gold-plate the 2K-LOC library.

### 2.2 Extract the integration recipe
- Diff vanilla APKeep vs the authors' NDD-APKeep (`XJTU-NetVerify/apkeep`) to get the
  concrete +66/−311 change; **abstract it to "what it does to the atom API"** (replace BDD
  predicate representation; replace APKeep's atom computation/incremental update with NDD
  `atomize`/`update`; handle packet transformers via per-field atoms).

### 2.3 Decide integration strategy (A) vs (B) — AFTER scoping, not assumed
The authors' −311 LOC **deletes the atom-maintenance layer our fork *extended***
(`FilterElement` multi-field, our 128-bit IPv6 encoding in `BDDACLWrapper`,
`updateSplitAP`/`ChangeItem`, Lever B's query seed). Their diff therefore *collides* with
our additions and cannot be replayed verbatim. Two viable paths:
- **(A) Re-fork from the authors' NDD-APKeep** and replay our FaVe changes onto it.
  Inherits their clean NDD integration; costs re-doing our multi-phase fork on a new base.
- **(B) Keep our fork and swap the engine** (JDD→NDD, rewire atom maintenance). Preserves
  our structure; we own the NDD integration.
- **Deciding input:** how entangled is our Java work with the atom layer NDD replaces?
  First read: bounded — the adapter is agnostic; entanglement is `FilterElement` + IPv6
  fields + the reachability seed — which leans (B). But **make the call from a scoping
  pass, not an assumption.**

### 2.4 Vendor the NDD library
- Bring `XJTU-NetVerify/NDD` in with the same hygiene as APKeep (subtree + a
  `FAVE_CHANGES`-style changelog for any local edits), and fold it into the pinned env.

### 2.5 Integrate on a slice, gated on differential-vs-baseline
- Build the NDD backend on a wl_up slice; gate on **exact parity with our frozen BDD
  baseline** (pair-for-pair) + the exactness gate. This differential-against-our-own-golden
  is our strongest correctness lever (why Part 1 must come first).

### 2.6 Full-scale correctness + performance (exit criteria) — ✅ COMPLETE
Original exit criteria, both met (see `APKEEP_NDD_EVAL.md` §2.5/§2.6 for the record):
- Full-model differential vs BDD baseline: **0 diffs** (correctness necessary but not the
  goal).
- **Performance is the goal:** NDD-APKeep must *beat* BDD-APKeep on the full model.

**Outcome — met and exceeded.** NDD is a selectable second FaVe backend
(`APKeepAdapter(engine='ndd')`), exact on **all six benchmarks** and in the exactness
gate (19 passed, 0 skipped):

| benchmark | correctness | NDD vs BDD |
|---|---|---|
| wl_up (IPv6 5-tuple) | exact 3660/3660 vs frozen BDD golden | **~0.5 s vs BDD ~1079 s** (~2000×) |
| wl_tum (IPv4 5-tuple) | exact == BDD | on par / faster |
| wl_stanford-P7a (IPv4 fwd) | exact == BDD | on par (single-field) |
| wl_i2 (77k IPv4 dst) | exact == reachable.json | 0.7 s (216-atom AP engine) vs BDD s-scale |
| **wl_stanford faithful (dst×VLAN)** | exact == NetPlumber (165) | **NDD 3 s vs BDD intractable** (ap_num≈21.6k, 28 min+ unfinished) |
| **wl_i2 faithful (dst×VLAN)** | exact == reachable.json (72) | **NDD ~15 s vs BDD intractable** (ap_num≥19k, 28 min+ unfinished) |

**When NDD wins: field INDEPENDENCE.** The per-field Σ representation beats BDD's single
joint partition (Π) exactly when the model has multiple *independent* fields — dramatic on
wl_up and on the two faithful-VLAN models (where BDD-APKeep cannot even finish). Where a
field is functionally slaved (i2's `rw=vlan` alone) or absent (single-field FIBs), NDD ≈
BDD. Scaling wl_i2's 77k-route FIB required a dedicated atomic-predicate forwarding engine
(`AtomForwarding` / `buildFwdPortPred`: interval-LPM → minimal atom partition), since the
naive per-port residual OOMs there while BDD-APKeep's incremental APs handle it — i.e. the
single-field FIB is the one place NDD needed extra engineering to reach parity.

### Refined sequence — ✅ ALL COMPLETE
1. ✅ Part 1 preservation (tag `fave-apkeep-bdd-v1`, pinned env, committed eval artifacts,
   re-measured timings, shared-adapter/two-engine model). ← safety net **and** test oracle.
2. ✅ §2.0 field-locality GO/NO-GO (MIXED → owner GO).
3. ✅ §2.1 library trust (differential vs BDD on our IPv6 profile; atomization restored +
   ported to the int-core; canonicity).
4. ✅ §2.2 extract + abstract the vanilla→NDD APKeep recipe.
5. ✅ §2.3 → **(B) engine-swap** (from the fork-entanglement scoping pass).
6. ✅ §2.5 slice integration (wl_up), gated on differential-vs-baseline + exactness gate.
7. ✅ §2.6 full-scale correctness + performance — all six benchmarks exact + gated; NDD
   beats BDD on every multi-independent-field model (two of them BDD cannot finish).

---

## Cross-cutting guardrails (reused throughout)
- **Exactness gate** (`fave/test/exactness_gate.sh`) stays green on every commit.
- **Differential vs the frozen BDD baseline** is the primary correctness oracle for the
  NDD work; soundness (never drop an NP/BDD-reachable pair) is the hard gate.
- **Measure before core surgery** — field locality (2.0) gates the whole effort; library
  trust (2.1) gates building on NDD.
- All vendored-library (`apkeep/`, `NDD/`) edits are separate subtree commits with a
  changelog entry (vendoring hygiene).

## Open decisions — resolved
- **(A) re-fork vs (B) engine-swap** → **(B) engine-swap**: our fork kept, engine
  swapped (BDD→NDD) behind one shared adapter. NDD vendored as a git subtree at `ndd/`
  (from a FaVe-owned fork), int-node-id core; atomization layer + `AtomForwarding`
  restored/added; `FAVE_CHANGES.md` documents all edits. **Owner handles pushing the
  subtree — DO NOT PUSH.**
- Tag / branch policy → frozen BDD baseline tagged `fave-apkeep-bdd-v1`; NDD work on
  branch `ndd`.
- Shared eval harness → `fave/bench/wl_up/eval/` (+ `fave/bench/wl_i2/eval/`).

## Status: DONE
Part 1 (preservation) and Part 2 (NDD integration, §2.0–§2.6) are complete. NDD is a
selectable second backend, exact on all six FaVe benchmarks and decisively faster wherever
multiple independent header fields make BDD-APKeep pay a cross-product (two faithful-VLAN
models are outright intractable for BDD-APKeep). Full record: `APKEEP_NDD_EVAL.md`.

## Planned: uncapped BDD-APKeep faithful measurements (future)
**Why.** The BDD-APKeep numbers for the two faithful (dst×VLAN) models are currently
*capped* — each was stopped by a 1700 s (~28 min) wall-clock `timeout` I imposed, **not**
by an OutOfMemoryError, and the profiler shows the atomic-predicate count still growing
~linearly (≈2.7 APs per `+nat` rule, no plateau) with only ~52 % of rules applied while
the per-rule PPM cost grows superlinearly (see `APKEEP_NDD_EVAL.md` §2.6a and the
committed traces `bench/wl_{i2,stanford}/eval/faithful_bdd_capped_profile.jsonl`). For a
paper-grade claim we want the *definitive* BDD-APKeep outcome, not a capped snapshot.

**Goal.** For faithful-stanford and faithful-i2 (`engine='bdd', faithful_vlan=True`),
record either (a) eventual completion — final `ap_num`, build+query wall time, peak heap —
or (b) a genuine heap ceiling — the `ap_num`/heap at which it OOMs.

**Method.**
- No `timeout`; the largest heap the machine allows (`FAVE_JVM_XMX`; the capped run used
  11 GB on a 15 GB box — use a bigger-RAM host, e.g. ≥ 64 GB).
- `APKEEP_BUILD_PROFILE=<path> APKEEP_BUILD_PROFILE_MS=30000` to log the `ap_num`/PPM
  trajectory (coarser interval to cut overhead); run detached.
- Reproduce via the adapter: replay `bench/wl_i2/i2-json` (files `device_topology.json`,
  `probes.json`) or `bench/wl_stanford/stanford-json`, `faithful_vlan=True`, `engine='bdd'`,
  then read `ap_num()` + `element_metrics()` + wall time (same driver used for the capped
  run; just drop the `timeout` and raise the heap).
- **Hedge against non-termination:** also run a *reduced* slice (e.g. 3–4 PoPs, via
  `apkeep_convergence`-style router subsetting) so at least one BDD-APKeep faithful build
  *completes*, giving a real final `ap_num`/time to anchor an extrapolation.
- Compare against the NDD side (already measured): faithful-stanford ≈ 3 s; faithful-i2
  ≈ 15 s build + ≈ 35 s query; per-field Σ (216 dst + 37 VLAN classes) — for a clean
  Σ-vs-Π table.

**Also worth doing** (not required by this plan): productionize incremental *updates* (not
just from-zero); speed up the faithful-i2 NDD query path (~35 s today — the per-hop NAT
`exist`+rewrite over 2-field NDDs dominates); a paper-ready benchmark table drawing on the
above.
