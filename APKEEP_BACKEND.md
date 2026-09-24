# APKeep as an Alternative FaVe Verification Backend — Design & Plan

**Status:** INTEGRATED, and in agreement with the other backends on every workload
run so far. `APKeepAdapter` is a selectable FaVe backend (`--backend apkeep` on the
aggregator, `FAVE_BACKEND=apkeep` on any `bench/wl_*/benchmark.py`), carries two
engines behind one adapter (BDD and NDD), is gated in the integration tier, and has
been run end to end on wl_ifi, wl_stanford, wl_i2 and wl_up through the live
aggregator. The faithful-VLAN model is the default and selectable (`--no-vlan` opts
out). Both correctness gaps this document named on 2026-09-18 are closed: the wl_i2
11-pair over-approximation (a device-keyed, ingress-only VLAN admission gate) and the
wl_up 1,651 phantom violations (compliance CONDITIONS never reached the query) — see
"Production-path parity" in §9 for both. **§10 has no open defect left**, in APKeep or
anywhere it touches. The last one was not an APKeep defect at all but an FPL translation
defect — superrole expansion granted self-reachability in `--strict` mode, the one mode
that promises not to — and it is fixed in `policy_translator/policy.py`, so it changed
what every backend is asked rather than what any of them answered. Its sibling — the
`Wifi` self-check fix asserting self-reachability for all sixteen wl_ifi roles, because
that fix is only sound for a strict-mode matrix — is fixed and recorded beside it, along
with the reason a green full-suite run hid it for one run. What remains in §10 is
one deferred feature (IPv6, an implementation lift) and one licensing question that only
the owner can settle (`JDD`, and it is larger than it was logged as). Neither is a
correctness risk.
*(This line read "PLAN (scoping complete; no integration code yet)" until 2026-09-18,
by which point it had been wrong for months — P4/P5 landed in the tree long before.)*
**Owner:** Claas Lorenz. **Driver:** PhD-thesis future work.

This document is the deep design plan for adding **APKeep** (atomic-predicate
data-plane verifier; Zhang et al., NSDI'20) as a second FaVe verification
backend alongside NetPlumber, and benchmarking the two head-to-head. The
actionable checklist lives in `TODO.md` (item 10) and points here; this file
holds the motivation, the capability analysis, the architecture decisions, and
the roadmap — the *why* behind the checkboxes.

---

## 1. Goal

FaVe currently solves every DHSA instance with one engine: **NetPlumber**
(header-space analysis over a plumbing graph). The thesis raises the question of
how DHSA performs on a structurally different engine. **APKeep** is the natural
counterpoint: it verifies the data plane using *atomic predicates* (packet
equivalence classes maintained as BDDs) rather than header-space wildcard
expressions.

Deliverable: FaVe should be able to run a compliance verification with either
backend, and we should measure the **user-perceived, from-zero response time**
(model build + compliance analysis) of `FaVe+NetPlumber` vs `FaVe+APKeep` on the
same workloads.

Non-goals (for the first milestone): incremental/live re-verification (FaVe's
live path is unstable and intentionally out of scope — we measure from zero),
IPv6 firewalls, and any workload feature the target benchmarks do not exercise
(see §5).

## 2. Background: the APKeep artifact

There **is** a public, official implementation by the original authors (Peng
Zhang's *NetVerify* group, Xi'an Jiaotong University):

- **Repo:** <https://github.com/XJTU-NetVerify/apkeep> — **MIT**, Java, Maven,
  JDK 11, ~5K LOC. Dependencies: `JDD` (BDD library), `jline` (CLI), `fastjson`.
- **Shape:** a **batch CLI** (`Main.java`): `init <snapshot>` → `update
  [<changes>]` (replay a rule-update trace) → `dump loops` / `check whatif`.
  Not a server, not a library.
- **NSDI'25 follow-up (NDD).** "NDD: A Decision Diagram for Network Verification"
  (Li Zechun et al., same group; <https://github.com/XJTU-NetVerify/NDD>,
  Apache-2.0) re-uses *this* APKeep with its BDD layer swapped for NDD (~100×
  gains). The NDD repo ships only the diagram library, not the APKeep-on-NDD
  verifier. So the APKeep everyone evaluates against is the XJTU artifact above.

**Consequence:** we do **not** reimplement APKeep. We vendor and adapt the
official artifact (see §7).

## 3. The integration seam

FaVe is **not** hardwired to NetPlumber at the wire level. The backend boundary
is a Python abstraction:

- `fave/aggregator/abstract_engine.py:5-62` — `AbstractVerificationEngine`, ~20
  methods (`*args/**kwargs` stubs; the real contract is the one concrete impl).
- `fave/netplumber/adapter.py` — `NetPlumberAdapter(AbstractVerificationEngine)`,
  the only implementation. It translates FaVe's model into NetPlumber's JSON-RPC
  (ternary bit-vector match/mask/rw, source/probe nodes, etc.).
- `fave/aggregator/aggregator_service.py:86-91` — the single instantiation site.

So a new backend is **a second subclass selected by a CLI flag**; it does *not*
have to speak NetPlumber's JSON-RPC. But the method *signatures* encode
NetPlumber's worldview (ternary vectors; source/probe nodes; `check_compliance`
keyed by node ids — `adapter.py:181,194`; `add_generator` `adapter.py:850`;
`add_probe` `adapter.py:983`). The work is therefore **semantic translation**,
not forwarding.

## 4. Capability analysis

### 4.1 Header-field coverage (APKeep ⊊ FaVe)

APKeep's field universe is **hardcoded** in `common/Fields.java` (enum) +
`common/BDDACLWrapper.java` (BDD bit allocation):

| Field | FaVe | APKeep |
|---|---|---|
| IPv4 src / dst | ✓ | ✓ (32b) |
| L4 src / dst port | ✓ | ✓ (16b) |
| protocol | ✓ | ✓ (8b) |
| MPLS label | – | ✓ (20b) |
| inner dst IP (tunnel/NAT) | – | ✓ (32b) |
| IPv6 dst | ✓ (128b) | ✓ **dst only**, fwd-by-prefix (`ForwardingRule6`) |
| IPv6 src | ✓ | ✗ |
| Ethernet src/dst, ethertype | ✓ | ✗ |
| TCP flags, ICMP/ICMPv6 | ✓ | ✗ |
| custom DHSA domain/metadata | ✓ (**runtime-extensible** `mapping.py:155`) | ✗ (fixed enum) |

The structural point: FaVe's `Mapping` is runtime-extensible (the heart of
DHSA's "domains"); APKeep's is compile-time. **IPv6 firewalls are out of scope
for APKeep as-built** (no IPv6 src, no IPv6 ACL) — so postponing IPv6 is
necessary, not just convenient. **First milestone is IPv4 5-tuple + ACL.**

### 4.2 Query model: APKeep exposes only loop detection

APKeep ships a complete **incremental forwarding+ACL model** but only **one**
query wired to it:

- **Substrate (rich):** the *Port Predicate Map* — `Element.port_aps_raw`
  (`elements/Element.java`): per-port atomic-predicate sets; `getPortAPs(port)`,
  `forwardAPs(port, aps)` (transfer), `getHoldPorts(ap)` (`core/Network.java`,
  via `APKeeper`); priority-resolved per-rule `hit_bdd` (the packets a rule
  actually serves after shadowing); topology traversal (`checker/Checker.java`
  `traversePPM`).
- **Query (poor):** `Checker` only ever fills a `loops` set. **No reachability,
  compliance, anomaly, or flow-tree API.**

Mapping the ~20 `AbstractVerificationEngine` methods onto this:

- **Tier A — direct translation:** `add_tables` (FaVe device → `ForwardElement`
  / `ACLElement`; router→ForwardElement dst-LPM, packet-filter→ACLElement
  5-tuple permit/deny — a genuine conceptual fit), `add_rules` (`encodeOneRule` +
  `insertOneRule`; **rewrite limited to NAT-style only**), `add_wiring` /
  `add_link(s)` / `remove_link` (`topology` / `addDirectedEdge`), `stop`, and the
  `delete_*` / bookkeeping methods.
- **Tier B — new solver code on the PPM:** `add_generator` (no source object;
  emulate by seeding the traversal with `getPortAPs(src) ∩ H`), `add_probe`
  (storage is bookkeeping; evaluation is the next item), `check_compliance`
  (**source→probe reachability** — must be written; existential & universal both
  computable by forward-propagating AP sets; **path/waypoint constraints are the
  hard part** since APKeep's traversal tracks history only for loops),
  `check_anomalies(shadow)` (≈ free: a rule whose post-insertion `hit_bdd ==
  BDDFalse` is fully shadowed; `reach`/`general` are harder/NetPlumber-specific).
- **Tier C — no APKeep analog:** `add_slice` / `del_slice` (no slicing concept),
  `dump_flows` / `dump_flow_trees` / `dump_pipes` / `dump_plumbing_network` (no
  flow-tree structure — but these feed reporting, not the verdict, so they are
  **stubbable** for the benchmark).

**Verdict:** the primitives are *sufficient*; "implement" means writing a
reachability solver on the PPM — APKeep's own `traversePPM` is ~80% of it (swap
"collect loops" for "did we arrive at the probe port", anchor at the source).

## 5. Benchmark scope (audited)

The two IPv4 benchmarks that overlap APKeep's field set are `wl_stanford` and
`wl_i2` (Stanford ships *in* the APKeep repo). Audit of their
`*-json/probes.json`, `sources.json`, and `checks.json`/`cchecks.json`:

- **Probes** (16 Stanford / 9 i2), **uniform**: `quantor=existential`,
  `match=null` (observe all), `test_path=null` (**no waypoints**),
  `test_fields=["vlan=0"]` → with no path, `add_probe` emits `test_expr =
  {"type":"true"}` (**probe condition is constant true** — no invariant
  resolution).
- **Sources:** full-space generators (`ipv4_dst=0.0.0.0/0`) at one port each.
- **Checks:** all-pairs `"s=source.X && EF p=probe.Y"` (240 / 72); `cchecks.json`
  conditions are `[]` (no header condition), polarity flag uniformly `true` (no
  must-not-reach / `AG`).
- **Slices:** none (the only `slice.py` is the vendored upstream Hassel library,
  not FaVe).

**The entire workload collapses to existential port-to-port reachability:**
*injecting all packets at the source port, does any packet survive forwarding +
ACLs to the probe port?* — for each (S, P) pair. Verdicts are compared against
the bundled expected `reachable.json`.

Therefore the **hard Tier-B features (paths, universal, conditions) and all of
Tier C are not exercised** by these benchmarks. The feasibility risk is retired
for this comparison; the solver is the small/cheap end of the estimate.
*(If non-reachability/`AG` invariants are wanted later: a trivial complement of
the reachability result.)*

## 6. Measurement methodology

We measure **user-perceived, from-zero time** = full model build + compliance
analysis, started fresh (not incremental update). Rationale: that is the
user-facing cost, and FaVe's live/incremental path is unstable and not the
focus.

Because integration overhead is *part of* that number, it must be **low and
symmetric** across backends, else the comparison measures packaging, not
engines. Decision: drive **both** backends in-process via Python-callable native
libraries rather than RPC/file shims:

- **`libnetplumber`** — pybind11/Cython binding over NetPlumber's C++ core
  (`Net_plumber::add_table/add_rule/add_link/add_source/add_source_probe`; the
  JSON-RPC layer is a thin shell over it). Removes the JSON-encode + per-rule
  socket round-trip overhead — and is a **standalone FaVe improvement** (kills
  the fragile two-process / `/dev/shm` / port architecture). Build this first; it
  de-risks the in-process premise and is valuable regardless of APKeep.
- **`libapkeep`** — embed the JVM in-process via **JPype** (true JNI; *not* Py4J,
  which is socket-based). Requires refactoring APKeep from a batch app to an
  **embeddable API** (accept in-memory rule additions instead of file parsing).

**JVM warm-up confound (the methodology landmine).** A `.so`-loaded NetPlumber
has ~zero startup; a JVM pays boot + class-load + JIT. A naive from-zero
comparison would penalize APKeep for being Java, not for its algorithm.
Mitigation (standard practice, easy with the resident-JVM design):
**keep the JVM resident, run N from-zero model builds, discard warm-up
iterations, report steady-state — and report the cold single-shot number
separately and labeled.** (Optional later polish: GraalVM `native-image` to
erase JVM/JIT — risky with reflection/the BDD lib, so not the baseline.)

Note the integration overheads differ in *kind*: NetPlumber's is IPC + JSON
(binding removes nearly all of it); APKeep's is JVM startup + parsing (binding's
win is "keep JVM warm + skip file I/O").

## 7. Vendoring the upstream code

APKeep will be **modified** (the embeddable API of §6, plus the reachability
solver hooks of §4.2). Decision: **fork on GitHub + bring in-tree via
git-subtree** at a top-level `apkeep/` (sibling to `net_plumber/`, `ad6/`):

- **In-tree** matches this repo's monorepo convention (everything is vendored
  in-tree; nothing is a submodule) and keeps `test.sh` / CI simple.
- The **fork** is a citable, publishable artifact of "our modified APKeep" —
  important for thesis reproducibility.
- `git subtree pull` stays available (upstream is effectively dead — 11 commits,
  no recent activity — so drift is near-zero); `git subtree split` pushes our
  changes back to the fork for publication.

Discipline: keep our modifications as **clearly-separable commits** so the
stock-vs-ours diff stays auditable; record provenance + license in the top-level
`README.md` alongside the existing NetPlumber/PolicyTranslator credits (APKeep is
MIT — compatible; verify the `JDD` dependency's license once).

## 8. Testing strategy

**APKeep ships zero automated tests** — no `src/test/`, no JUnit/surefire in
`pom.xml`, no CI. Its only harness is `ExampleExp` + `Evaluator` (a benchmark
driver: runs the bundled Stanford set, prints timing + detected loops; no
assertions, no golden outputs). So there is **nothing upstream to integrate** —
we build the correctness gate ourselves, leveraging the dual-backend setup
(this is `TODO.md` item 8's oracle idea applied between the two backends):

1. **Characterization / golden pin (before we modify APKeep).** Run stock APKeep
   on the bundled Stanford dataset, capture its loop output, pin it — so our
   later modifications can't silently change its core behavior.
2. **Differential reachability gate (primary).** On `wl_stanford`/`wl_i2`,
   NetPlumber and APKeep must produce **identical (S,P) reachability verdicts**,
   and both must match the expected `reachable.json`.
3. **Fast-tier, JVM-free unit tests for the translator.** The FaVe-model →
   APKeep-input encoding is pure Python; test it in the `fast` tier with no JVM
   (consistent with the existing backend-free seam tests).

**Tier placement in `test.sh`:** `mvn package` build + a bundled-Stanford smoke
→ **`integration`** (heavy/native, like NetPlumber's `make test`); the
differential NetPlumber-vs-APKeep run → **`e2e`/`bench`** (needs both backends
live).

**Hardening the APKeep core itself (before extending it).** The above is the
*integration* gate. Extending the APKeep engine (P6–P9, §9) requires unit-level
coverage of its Java core, which currently has none — that strategy (harness,
coverage map by what we use, prioritized Phase-0 test roadmap, ratchet) lives in
[`TESTING_STRATEGY_JAVA.md`](TESTING_STRATEGY_JAVA.md).

## 9. Roadmap (mirrors `TODO.md` item 10)

- **P0 — Vendoring & build.** Fork + subtree APKeep into `apkeep/`; `mvn package`
  builds in the dev/CI stack; bundled-Stanford smoke + golden loop pin; provenance
  in README; integration-tier wiring.
- **P1 — `libnetplumber`.** Map NetPlumber's C++ core API to the
  `AbstractVerificationEngine` methods; pybind11 binding; a `NetPlumberLibAdapter`
  selectable by flag; equivalence-tested against the JSON-RPC adapter.
- **P2 — `libapkeep`.** Refactor APKeep to an embeddable API (in-memory rule
  add/query, no file parsing); JPype binding with a resident JVM.
- **P3 — reachability solver.** Existential port-to-port reachability over the
  PPM (adapt `traversePPM`); shadow detection via `hit_bdd` (optional).
- **P4 — `APKeepAdapter` + model translator. DONE.** Forwarding + ACL
  translation; FaVe+APKeep matches the policy oracle `reachable.json` exactly on
  wl_ifi (`test_apkeep_wl_ifi`). ACLs wired as per-port ACLElements (VLAN made
  structural) with source-IP-seeded reachability.
- **P5 — Differential gate + benchmark. DONE.** `test_backend_differential`
  (integration): APKeep and NetPlumber compute identical wl_ifi reachability and
  both match `reachable.json`. `bench/apkeep_vs_netplumber.py`: from-zero
  comparison (in-process, §6 warm-up handling).
  - **wl_ifi (18 devices):** steady-state ~49 ms (NetPlumber) vs ~140 ms
    (APKeep) -- at small scale NetPlumber's low constant overhead wins.
  - **wl_i2 (Internet2, 77k dst-IP routes): NetPlumber 341 s vs APKeep 14 s,
    ~24x faster** -- APKeep reproduced `reachable.json` exactly. **That match is
    NOT a correctness result** (added 2026-09-18): `reachable.json` is an
    all-reachable 72/72 policy mesh, so any relaxed encoding scores 100% on it by
    construction. Measured against NetPlumber instead, APKeep was 11 pairs
    OVER-approximate -- root-caused and fixed later the same day (the faithful
    VLAN admission gate; see "Production-path parity" below). The timing result
    always stood; the exactness claim did not, and this measurement was of the
    PLAIN model, which over-approximates by construction.
    The crossover is decisive at scale: header-space flow propagation is the
    bottleneck (NetPlumber's 341 s is almost entirely model build), atomic
    predicates are not. This is the result the comparison was built to show.
  - **wl_stanford:** the *forwarding* is now modelled (P7a: the `in_port` out-stage
    collapse), and it matches the bundled `reachable.json`. But `reachable.json` is
    the **artificial all-to-all policy** (from the HSA/NetPlumber papers), not the
    data plane -- so that match only proves forwarding *completeness*. The faithful
    data plane needs the VLAN-coupled ACLs, which require a VLAN **rewrite** (P7b =
    P8); see the P7 subsection for the NetPlumber cross-check that quantifies this.

### Production-path parity: four benchmarks through the live aggregator (2026-09-18)

`AD6_PLAN.md` §9.27/§9.28 built the production route to a non-NetPlumber engine
(`build_engine()` + `--backend {netplumber,apkeep,ad6}`, and `FAVE_BACKEND` /
`FAVE_ENGINE_OPTIONS` on `GenericBenchmark`, because all six `wl_*/benchmark.py`
drivers hardcode their constructor arguments). APKeep was wired into that route at
the same time but **never exercised through it**; every APKeep result up to here was
produced through `InProcessFaVe` or the adapter directly. This is that exercise: the
same `bench/<wl>/benchmark.py`, backend the only variable, verdict read from the
generated `report.md`.

**Method and its limits.** Verdicts only — the runs are not a timing comparison: this
box is a 4-core yolobox and the NetPlumber run needed its log files redirected off a
63 MB `/dev/shm` (below), so wall-clock is not like-for-like. Agreement is checked as
**set equality of the violation/reachability sets**, never as equal counts; a matching
count can hide two compensating errors.

| workload | checks | NetPlumber | APKeep | agree? |
|---|---:|---|---|---|
| wl_stanford | 240 | 75 viol → **165** reachable | 75 viol → **165** | **yes, set-equal** |
| wl_ifi | 299 | 27 viol | 27 viol | **yes, set-equal** (but see below) |
| wl_i2 | 72 | 11 viol → **61** | 0 viol → **72** | no — 11 pairs (**since fixed**, §9) |
| wl_up | 11,902 | **0** viol (ad6: 0) | **1,651** viol → **0** | no — 1,651 phantom (**since fixed**, §9) |

Both NetPlumber runs were made for this comparison on the same day and the same box,
not taken from the record.

> **DENOMINATOR CHANGED 2026-09-21 — wl_up is now 18,811 checks, not 11,911.**
> `bench/reach_csv_to_checks.py`'s denied-cell branch asserted only ONE endpoint
> of a multi-device role (it used the loop-leaked `target` instead of iterating
> `targets`), and wl_up has 40 roles mapping to two or three devices. Fixing it
> for wl_cloud's service roles added **6,900 must-not-reach checks, all of which
> PASS** — so no verdict in this document changes, but every count below is the
> pre-fix denominator and must not be compared against a post-fix one
> (TODO item 0a, CLOUD_BENCH_PLAN.md §1.9.6).

*(wl_up's check count moved twice. It is **11,902** throughout this section, **11,903**
where §10 restores the `Wifi <--> Wifi` self-check, and **11,911** today, after §10's
superrole-self-expansion fix emptied eight spurious `DMZ*` diagonals and so gave each of
them a negative self-check. Every measurement in this section was made against the
11,902-check set and none of it moves: both later additions pass, and the positive check
count — the one every reachability verdict is read from — is unchanged at 3,371.)*

#### wl_stanford — exact, and on a better oracle than the one P5 claims
`FAVE_BACKEND=apkeep bench/wl_stanford/benchmark.py` → 75 violations of 240 → 165
reachable. Set-compared against NetPlumber's own matrix from
`bench/apkeep_convergence.py --emit netplumber`: **0 NetPlumber-only, 0 APKeep-only**
(after discounting the 16 self-pairs the 240-check set excludes from its 256). This is
the same 165 `AD6_PLAN.md` §9.28/§9.31 reports for ad6 and for the post-§9.29
NetPlumber benchmark, so all three families now agree pair-for-pair on wl_stanford.

Worth stating plainly because P5 above undersells it: that bullet records wl_stanford
as "matches the bundled `reachable.json`", and `reachable.json` is the artificial
all-to-all policy mesh — matching it proves forwarding completeness and nothing about
over-approximation. Matching **NetPlumber's 165** is the stronger claim. Note this is
the plain P7a model (`faithful_vlan=False`, the only thing the production path can
build — see the gap below), not the faithful VLAN one.

#### wl_i2 — APKeep over-approximated by exactly 11 pairs (root-caused and fixed)
`FAVE_BACKEND=apkeep` → **0 violations of 72** (everything reachable).
`FAVE_BACKEND=netplumber`, same driver → **11 violations of 72** → 61 reachable:

    chic  -> hous, kans, losa, salt, seat
    atla  -> kans, seat
    newy32aoa -> kans, seat
    wash  -> kans, seat

Those 11 are **set-identical** to ad6's archived faithful result under both solvers
(`bench/wl_i2/eval/ad6_i2_flowpath_faithful_{cadical195,minisat22}_72pairs_sandbox.json`),
and to `bench/i2_structural_oracle.py`. So the 61 has four independent witnesses
(NetPlumber, ad6, the structural oracle, and now a second NetPlumber run through the
benchmark driver) and APKeep is alone at 72.

**Why the gated tests could not see this (all three now repointed).**
`test_apkeep_i2.py:98`, `test_apkeep_ndd_fwd.py:100` and `:166` all asserted equality
with `bench/wl_i2/reachable.json`, which is an **all-reachable 72/72 policy mesh**
emitted by the same generator as `checks.json`. It scores any relaxed encoding at 100%
by construction — the exact defect `TODO.md` item 1s names and `AD6_PLAN.md` §5.5 "C3
REOPENED" re-derived for ad6. `APKEEP_NDD_EVAL.md` §2.6's "faithful reachability ==
72 = NP" is contradicted by NetPlumber itself; it predates the §9.29 `length`/`mapping`
fix and was never re-run.

All three now assert against `bench/wl_i2/eval/i2_structural_oracle_atoms.json`
instead, each stating what its own model is actually entitled to claim:

| gate | model | asserts |
|---|---|---|
| `test_apkeep_ndd_fwd.py:test_i2_faithful_vlan_matches_the_structural_oracle` | faithful | **equality** — the 11 pairs exactly, over and under |
| `test_apkeep_i2.py` (BDD) | plain | reaches all 72; drops nothing the data plane delivers; surplus is exactly those 11 |
| `test_apkeep_ndd_fwd.py:test_i2_plain_is_sound_and_over_approximates_by_the_known_11` | plain | the same three |

Equality with the oracle is the right bar only for the faithful model, and there it is a
real, falsifiable assertion. The plain model relaxes the VLAN dimension by construction,
so demanding 61 of it would be demanding a model it is not.

**Be precise about what the plain gates gained: attribution, not detection power.**
While the plain model reaches all 72, its soundness and surplus assertions follow
algebraically from "reaches all 72", so they detect exactly what the old
`reachable.json` comparison detected. That is measured, not assumed — dropping a pair
from the oracle leaves them passing, which is how the first version of this change was
caught claiming more than it delivered. What changes is that each assertion names the
property it stands for and is checked against the real data plane rather than against
policy intent: a plain model that loses a DELIVERABLE pair reports unsoundness, while
one that correctly sheds one of the 11 reports only drift. `reachable.json` reported
those two identically, and read as a claim that the model is exact.

Both gates judge through one shared `test/i2_oracle.py`, so the BDD and NDD runs of the
same model cannot drift apart in what they demand of it, and the attribution property
itself is pinned by `test/test_i2_oracle_classification.py` (fast tier, synthetic sets,
no engine) — including the vacuity case above, frozen so a future rewrite cannot
re-make the claim without confronting it. No test asserts `wl_i2/reachable.json` any
more.

**The faithful model does not fix it — measured, not inferred (2026-09-18).** When
this section was first written the production path could build only
`faithful_vlan=False`, where over-approximation is expected by construction (plain mode
relaxes the VLAN constraint, and relaxing can only add reachability), so the 11 pairs
were not yet evidence of a defect. With the faithful model now the default and
selectable, `FAVE_BACKEND=apkeep bench/wl_i2/benchmark.py` builds the full dst × VLAN
model on the NDD engine (41.9 s of `check_compliance`) and **still reports 0 violations
of 72**. The over-approximation therefore survives the faithful model and the
VLAN-blind alibi is gone: both APKeep models, on both engines, say 72 where NetPlumber,
ad6 and `bench/i2_structural_oracle.py` say 61.

##### ROOT CAUSE (2026-09-18): the VLAN admission gate was keyed by device, and never applied to transit

Two independent defects in `_build_i2_faithful`, **either one sufficient** to turn the
true 61 into 72:

1. **Admission was keyed by DEVICE, not by (ingress port, VLAN).** `_capture_in_admission`
   recorded `self._in_vlans[in.X] |= {vlan}`, discarding `rule.in_ports` — the union over
   every port of the router. wl_i2's in-stage is emphatically not port-uniform: `in.kans`
   admits `{11,20,21,30,31,32,40,60,70}` on port `400029` and `{10,20,30}` on ports
   `400019/400022/400025/400026`. The union therefore admits VLAN 10 at Kansas, and VLAN 10
   is exactly what `out.chic` writes onto the link `220045 → 400029`. The union is larger
   than any single port's set at **all nine routers** (kans 40 vs max-per-port 11; chic 94
   vs 26).
2. **The gate was spliced only onto `source.* → in.X` edges.** The splice condition was
   `s_dev in self._generators`, so a transit hop `out.Y:p → in.X:q` passed **ungated** —
   no admission check at all. The docstring's own stated intent ("a VLAN an upstream mid
   assigned propagates only if the next router's ingress admits it") was never realised
   for wl_i2. Since sources inject VLAN-unconstrained, the source-edge gate is close to a
   no-op anyway, so in practice **no** admission was enforced on any packet that mattered.

`_build_stanford_faithful` did not have defect 2: wl_stanford funnels all ingress through
the single `in.X → mid.X` internal edge and gated there, which catches transit traffic.
That is why only wl_i2 was affected. It did share defect 1, and that is now fixed too —
see "wl_stanford shared defect 1" below.

**How this was established.** `bench/i2_structural_oracle.py` re-run with one property
relaxed at a time (the model semantics substituted, everything else identical):

| oracle variant | reachable pairs |
|---|---:|
| per-port admission, checked every hop (the truth) | **61** — the same 11 pairs |
| port-blind union, checked every hop (defect 1 alone) | **72** |
| per-port admission, checked at ingress only (defect 2 alone) | **72** |

Both counterfactuals reproduce APKeep's answer exactly. The oracle's `--explain atla seat`
names the mechanism directly: all 5 IPv4 atoms that reach `probe.seat` from anywhere die
at `BLOCKED@in.kans.400029(vlan=10;admits=[11,20,21,30,31,32,40,60,70])`.

**Fix and verification.** Admission is now captured per `(in.X, ingress port)`
(`_in_port_vlans`, with an in-port-agnostic rule folded into every port of its device), and
an admission element is spliced onto **every** edge delivering to an in-stage — transit and
source alike — each permitting that arrival port's own VLAN set. On wl_i2 that is 63
elements (one per reached `(device, port)`) instead of 9, one permit rule each, so the
atomic-predicate cost is unchanged in kind. Measured on the production path, faithful +
NDD: replay 6.4 s, `check_compliance` 38.2 s, **61 of 72 reachable, the 11 unreachable
pairs set-identical to NetPlumber, ad6 and the structural oracle** (missing 0, extra 0).

Corroboration that this is the intended semantics and not a tuning choice: ad6's archived
faithful run records `in_admission_port_scoped: true`, `in_admission_ports: 223`,
`in_admission_pairs: 596` — it models admission per port, and it is one of the engines
that gets 61.

Pinned by `test/test_apkeep_i2_admission.py` (integration tier), which reproduces the
defect on a two-router model: `out.b` writes VLAN 10 onto a link landing on `in.a:5`, which
admits 99 on port 5 and 10 on port 6. Either the union or an ungated transit hop makes the
probe reachable; both engines must call it unreachable.

##### wl_stanford shared defect 1 — fixed, with no verdict change (2026-09-18)

The port-blind keying was not wl_i2's alone. `_build_stanford_faithful` spliced one
ACLElement per ROUTER onto that router's `in.X → mid.X` edge, permitting
`self._in_vlans[in.X]` — the union over its ingress ports. Measured on the real model,
that union **strictly exceeds every single port's set at all 16 routers**:

| router | union | widest single port | ports |
|---|---:|---:|---:|
| `in.goza_rtr` | 151 | 128 | 23 |
| `in.gozb_rtr` | 152 | 128 | 23 |
| `in.boza_rtr` | 114 | 98 | 14 |
| `in.bbra_rtr` | 47 | 23 | 34 |
| `in.bbrb_rtr` | 17 | 9 | 20 |

So the gate admitted tags the arrival port does not — the same over-approximation that
cost wl_i2 its 11 pairs. Fixed the same way: one element per `(in.X, ingress port)`,
spliced onto every edge delivering there, permitting that port's own set. Note this
**moves** the gate rather than tightening it. A per-port gate could not have been
expressed where the old one stood: the `in.X → mid.X` funnel is downstream of the merge,
so by the time traffic reaches it the arrival port is already lost. Cost: 60 elements
instead of 16, and *fewer* VLAN tags overall (939 against 1,340), because the per-port
sets are smaller than the union.

**No verdict changed** — faithful wl_stanford on NDD is still pair-for-pair identical to
NetPlumber. That is the expected outcome, and it is why the defect survived here while
wl_i2 lost 11 pairs to it: the surplus tags happen to be ones nothing upstream assigns
towards those ports, so the relaxation admits traffic that never arrives.

**Which is exactly why the new gate is STRUCTURAL.** The reachability gate
(`test_apkeep_ndd_fwd.py`'s faithful wl_stanford test) cannot see this defect — it passed
before the fix and after it. `test/test_apkeep_stanford_admission.py` asserts the shape
instead: one element per reached ingress port, each permitting exactly that port's set
and never the device union, and every live ingress edge passing a gate (the only ungated
ones deliver to dead ports `_gate_dead_ingress` removes outright). It first asserts the
model really is port-non-uniform, so it cannot pass vacuously on a model where the two
keyings coincide. Against the pre-fix builder it produces 103 failures. This is the
distinction between a right answer and a right answer for the right reason, and it is
the general lesson of both defects: a workload where the over-approximation is
unobservable gates nothing.

#### wl_up — the conditions never reach the query (and wl_ifi cannot show it) — FIXED
`apkeep/adapter.py:1451` unpacked `(source, negated, cond)` and used `negated`; `cond`
was carried into `self._results` for reporting and **never applied to the query**. The
`related` bit *is* parsed into the rule encoding (`adapter.py:518`), so the rules carry
state — only the queries do not. NetPlumber, for contrast, builds a header-space vector
from the condition and ships it to the engine
(`netplumber/adapter.py:194`, `self._build_vector(cond).vector if cond else None`).

**wl_up is the decisive case, and APKeep fails it.** 1,651 violations of 11,902, and
the violation set is **exactly** the 1,651 `related:0` checks (verified pair-for-pair
against `cchecks.json`; note wl_up stores the backward `(X)` checks with source and
probe swapped, §9.23.1, so the comparison must normalise by name prefix, not by
position). **Zero** of the 8,600 unconditioned checks fail — which corroborates
APKeep's plain wl_up reachability and is consistent with the committed
`bench/wl_up/eval/mat_apk.json` == `mat_np.json`. FaVe+NetPlumber, run through the
same driver on the same day, reports **0 violations of 11,902**, as does ad6
(`AD6_PLAN.md` §9.34). So all 1,651 are phantom, and they are phantom for one reason:
the condition was dropped. wl_up earns this status — 136 of its 139 rulesets match on
`ctstate`/`ESTABLISHED`.

**wl_ifi looks like agreement and is not evidence.** APKeep reports 27 violations of
299; NetPlumber reports 27; the two sets are **identical** (0 either way), and both are
exactly the 27 `related:0` checks. But `related` occurs in wl_ifi *only* in
`checks.json`/`cchecks.json` — the queries — and **zero** times in `policies.json`,
`routes.json` or `topology.json`: the model has no state field at all, its Cisco ACLs
being state-blind. Conditioning on `related` therefore cannot change reachability, and
an engine that drops the condition gets the right answer for the wrong reason. The
agreement is accidental, and wl_ifi must not be quoted as evidence that APKeep handles
conditions.

Two things follow that are worth keeping. First, this is the **live-NetPlumber
confirmation** `AD6_PLAN.md` §4.2 wanted and never had: it traced wl_ifi's 27
`related:0` failures to a state-blind ACL rule and recorded the conclusion as "NOT yet
confirmed against a live NetPlumber oracle". Confirmed — the policy is aspirational
there, and the 27 are genuine violations of it. Second, it is a clean illustration of
why a differential needs a workload that can discriminate: three engines agreeing on
wl_ifi says nothing about the capability wl_up exposes.

##### RESOLVED (2026-09-18): honour `related`, refuse everything else

Both options this section originally weighed — (1) refuse, matching ad6's
`_validated_conditions`; (2) honour, as NetPlumber does — are implemented, because they
are not alternatives: honouring is the capability, and refusing is what must happen to
the conditions honouring does not cover. `_cond_related` is the single gate. A
`related:N` condition is forced onto the query; a condition naming any other field, a
malformed one, a negated one, or a contradictory pair **raises**. Nothing is skipped,
for the reason `AD6_PLAN.md` §9.23 is a post-mortem of: a dropped condition does not
fail, it answers the unconditioned question and returns a confident number.

**Where the bit is forced: at ARRIVAL, not at the source seed.** Nothing in FaVe's
models ever *rewrites* `related` — `iptables/generator.py`'s state shell emits it as a
match, never as an action — so traffic arrives carrying exactly the state bit it was
injected with. "Does the header set arriving at the probe contain a `related=N` packet"
is therefore the same question as "does an injected `related=N` packet survive", and the
arrival form is strictly cheaper: the per-source traversal stays state-independent, so
the `related:0` and `related:1` variants of a pair share one cached flood instead of
forcing two. This is the same argument ad6's `_state_field_literals` makes for forcing
the bits at one node ("nothing rewrites `related` … so pinning one node on the path pins
the whole path"), applied at the other end of the path.

Both engines already carried the field, so only the query side changed:

| layer | change |
|---|---|
| `apkeep/adapter.py` | `_cond_related` validates/extracts; `check_compliance` threads it into every query |
| `apkeep/lib_ndd.py`, `NddReachabilityEngine.java` | `isReachable(..., related)`; arrival intersected with `exact(REL, N, 1)` (field index 5, already declared) |
| `apkeep/lib_apkeep.py`, `ReachabilityChecker.java` | `setRelatedHeader(bdd)`; arrival intersected in `arrives()`, kept separate from the vlan `targetHeader` so the two compose |
| `common/BDDACLWrapper.java` | `ConvertRelated(int)` — the same `relatedVar` the rule encoder constrains |

**Measured on the production path** (`InProcessFaVe`, the real `bench/wl_up` models, the
real `checks.json` posted the way `bench/compliance_checker.py` posts it — 11,902 checks,
3,302 of them conditioned): **0 violations**, matching FaVe+NetPlumber and FaVe+ad6.
Replay 1.7 s, `check_compliance` 1.0 s — unchanged from the unconditioned run, which is
the flood cache staying shared. That is the NDD engine, wl_up's production default.

**Confirmed on the BDD engine too, at full wl_up scale.** The two engines force the bit
through different machinery — `ReachabilityChecker`'s arrival test against a
`BDDACLWrapper` predicate, versus an NDD `and` on field REL — so neither covers the other,
and the committed gate exercises the BDD path only on a two-rule model. Same models, same
11,902 checks, `engine='bdd'`: **0 violations**, set-identical to the NDD result. Total
9 m 56 s: replay 1.7 s, build 469.6 s, queries 124.2 s (95.8 checks/s, 3.99 M DFS nodes,
no single check above 0.1 s).

The build reproduces the frozen baseline's structural fingerprint **exactly** —
`APKEEP_BDD_BASELINE.md` §4.2 records `ap_num` 14 561 and 543 elements across two
environments, and this run gives 14 561 and 543 again, PPM-dominated at 95 % (`ppm_ms`
444.3 s of 469.6 s; insert 16.8 s, merge 4.3 s, encode 0.3 s) against that table's 96 %.
So honouring the condition changed the query and left the model untouched, which is what
it should do. The build wall itself is faster than §4.2's 680–748 s; that table already
flags ~10 % run-to-run variance plus env sensitivity on a BDD-heavy workload, and this
run had `FAVE_JVM_XMX=12g` and an idle box, so it is not evidence of a speedup.

**The gate asserts both halves, because either alone passes for the wrong reason.**
`test/test_apkeep_compliance_cond.py` (NDD tier) runs the same policy twice: with the
conditions it must report **zero**, and with the very same checks stripped of their
conditions it must report **exactly 1,651** — every one of them a check that carried a
condition. A condition that bound to nothing would satisfy the first assertion and fail
the second, which is precisely the failure mode wl_ifi cannot detect. The gate runs wl_up
on NDD and both engines on a two-rule stateful firewall; the BDD wl_up run above is a
manual confirmation, not part of the tier, because 8 of its 10 minutes are build.

#### The wl_ifi stateless variant — giving the benchmark a zero-violation oracle
Owner proposal, 2026-09-18, and implemented the same day. wl_ifi pairs a policy that
asks for stateful reachability with a model that faithfully reproduces Cisco ACLs'
inability to express it; the 27 violations are the honest consequence, and both
engines report them. But a nonzero expected set is a poor gate (it has to be spelled
out and maintained) and a poor discriminator (a tool that DROPS the condition scores
exactly like one that honours it).

Replacing `<->>` with `<-->` — "statefully" with "bidirectionally", both already in
the FPL grammar (`policy_translator/fpl_grammar.py:133`) — makes the policy ask only
what the model can express, and a correct tool must then report **zero**. Running both
configurations exercises a tool on each kind of policy, and separates one that
**refuses** a condition it cannot honour (ad6) from one that answers anyway.

| wl_ifi configuration | checks | conditioned | NetPlumber | APKeep |
|---|---:|---:|---:|---:|
| stateful (`<->>`) | 299 | 54 | 27 | 27 (set-identical) |
| stateless (`<-->`) | 272 | 0 | **0** | **0** |

The 27 stateful *pairs* (`related:1` must-reach + `related:0` must-not-reach) collapse
to 27 plain must-reach checks: 299 − 54 + 27 = 272. The reachability oracle
(`reachable.json`) is byte-identical between the two, so the variant changes only what
is asked, never what the network is expected to do — which is what keeps the two
configurations comparable. The NetPlumber figures come from the same InProcessFaVe path
with the stateful set as a control (27, as expected) so the 0 is a measured zero rather
than an adapter that populates no results.

**A trap found while building it, worth the next person's time.** `reach.txt` is *not*
the source of wl_ifi's policy matrix. `roles_and_services.txt` carries its own copy of
the same four rules (lines 172-181), the translator CONCATENATES its positional files
before parsing, and so editing `reach.txt` alone changes nothing — deleting a whole rule
from it leaves the generated matrix byte-identical. Both files have to change, and a
fast-tier test now pins that the two copies agree, since if they ever diverge the
concatenation order decides silently.

Artifacts: `reach_stateless.txt`, `roles_and_services_stateless.txt` and
`reachability_stateless.csv` are tracked inputs; `gen_wl_ifi_inputs.sh` derives
`checks_stateless.json` / `cchecks_stateless.json` / `reachable_stateless.json`
alongside the originals. Gates: `test_wl_ifi_stateless_policy.py` (fast — policy,
matrix and both derived check sets) and `test_wl_ifi_stateless_gate.py` (integration —
zero violations end to end).

#### wl_cloud — a forwarding table is not always a FIB (2026-09-21)

Full account in `CLOUD_BENCH_PLAN.md` §1.7.3; what belongs here is what it
changed about this backend.

**The translation's shape, not its wiring.** `_translate_fwd_rule` turned every
forwarding table into a `ForwardElement` — a destination-prefix trie — keeping
the destination and dropping any other match field, any header rewrite, and the
rule ORDER, which it replaced with the prefix length. That is exactly right for
a FIB, and wl_i2, wl_stanford, wl_up, wl_ifi and wl_example have only FIBs.
wl_cloud is the first workload whose *forwarding tables* carry ACLs, and there
the loss is not a subtlety: a permit and a deny on the same prefix arrive at the
same priority, and **the two engines resolved that tie oppositely** (BDD kept the
deny, NDD kept the permit), which is the cleanest possible evidence that the
answer had stopped depending on the model.

A table now chooses its element from its RULES — `_is_dst_lpm_table`, which reads
no device name:

| the table | the element |
|---|---|
| matches only dst (+ `vlan`/`in_port`), rewrites only `out_port` | `ForwardElement` (unchanged) |
| anything else | `FilterElement`, first-match, priority = rule index |
| … and rewrites an address | + a `NATElement` inline on the egress port |

One exemption stays and is deliberate: the HSA `in.`/`mid.`/`out.` stages, which
`_build_stanford_faithful` / `_build_i2_faithful` / `_collapse_out_stage` already
rewrite, and whose VLAN matches a `FilterElement` cannot carry anyway. It is the
last device-name test in that decision, and lifting it means giving the
`FilterElement` a VLAN field.

**Three capabilities added, all in the engines:**

| layer | change |
|---|---|
| `NATElement.java` | `+ nat <dev> <port> match <src\|dst> <ip> <len> <ACLRule body>` — an address rewrite that NAMES the field it writes and is keyed on the whole 5-tuple. The old form wrote the destination only and keyed on a destination prefix, which cannot distinguish two source rewrites that share a port and a source /24 and differ only in `tcp_src`. |
| `common/BDDACLWrapper.java` | `srcIPField`, so `get_field_bdd(Fields.src_ip)` stops returning `BDDFalse`; `negate(int)` for a negated check condition |
| `NddReachabilityEngine.java` | the same NAT form; `applyNat` generalised from VLAN to any field; `isReachable(..., List<String> conds)` |
| `ReachabilityChecker.java` | `andArrivalHeader(int)` — the check conditions beyond `related`, composing with it |
| `apkeep/adapter.py` | `_query_conditions` (protocol/port/address, positive and negated), refusing any condition on a field THIS model rewrites — the arrival form equals a source seed only while nothing rewrites the field |

**A rewrite onto a prefix frees the bits it does not fix.** Both engines
quantify the field away and then constrain it to the new predicate. This is the
semantics `AD6_PLAN.md` §9.36 had to correct on the other backend, where framing
those bits collapsed a /22 DNAT to a single host.

**And one more, found by fixing those.** `add_generator` read the injected source
ADDRESS and ignored every other field a generator states. Harmless while every
workload injected only an address (wl_stanford's `ipv4_dst=0.0.0.0/0` is the full
space; wl_up and wl_example inject `ipv6_src` alone); wl_cloud's matrix phase
injects `tcp_src` per service endpoint and its leaf ACLs match on it, so the
query asked about traffic from every source port and **293 denied pairs came back
reachable**. `_source_src_filters` is now `_source_seed_filters` and carries the
whole injected header, and an injected field it cannot express raises.

**Result: APKeep agrees with NetPlumber on every check this workload asks** —
all-pairs 64/64 (was 54/64), and through PolicyTranslator the oracle phase (6/6
third-party verdicts, 57 violated of 71), the matrix phase (1,315 of 4,224) and
the public phase (3 of 4,199), with the violated SETS equal and not merely the
totals.

**Open, and a cost result rather than a correctness one:** APKeep's own BDD
engine does not finish the corrected model's build within 40 minutes, where it
took seconds on the lossy one. 46 `FilterElement`s carrying a few hundred 5-tuple
rules each split the AP partition, and `APKeeper.updateSplitAP` touches every
element per split — the wall "Performance analysis: BDDs vs APs" below describes
and P7b hit on wl_stanford. No verdict was produced, so none is reported. The
default engine is NDD and every number above is its.

#### Three defects found in passing

1. **`faithful_vlan` had no CLI flag — FIXED 2026-09-18, and the default inverted.**
   `build_engine()` accepted it and argparse never wired it, so `FAVE_BACKEND=apkeep`
   could only ever build the plain, VLAN-blind model, and the faithful model the whole
   NDD headline rests on could not be selected in production at all. Faithful VLAN
   handling is now the **default** — ad6 and NetPlumber both model it, so an APKeep run
   that drops it is not a like-for-like comparand — and `--no-vlan` turns it off. The
   engine default moved with it of necessity: the faithful model is precisely where
   BDD's atomic-predicate cross-product explodes (it finishes neither wl_stanford nor
   wl_i2), so the default engine is now **NDD**, which builds both in seconds. `bdd`
   stays reachable by name, and all 13 existing call sites are pinned explicitly to the
   configuration they measured. Verified end to end: wl_stanford on the new defaults is
   75 violations → 165 reachable in 1.05 s, the violation set identical to the
   plain-BDD run and to NetPlumber's own matrix.
2. **The report renders APKeep's conditions as object reprs. FIXED (2026-09-18).**
   `aggregator_service.py:290` hands the engine `RuleField` *objects*
   (`RuleField.from_json`); `Ad6Adapter` converts them back to dicts, `APKeepAdapter`
   stores them as-is, and `reporting/reporter.py:70`'s `_render_cond` — whose docstring
   assumed dicts — fell through to `str(field)`. Every conditioned violation in an
   APKeep report read `<rule.rule_model.RuleField object at 0x...>`. Lenient by design
   so it could not abort a run, but unreadable at exactly the line that states the
   verdict. `_render_cond` now also accepts objects carrying `.name`/`.value`; pinned in
   `test_reporter_engine_results.py`.
3. **wl_up's headline number was under-reported by one. RESOLVED — the headline is
   3,661 everywhere, and the missing pair is now checked (2026-09-18).** `mat_np.json`
   and `mat_apk.json` (`bench/wl_up/eval/`) hold **3,661 = 3,661, 0 diffs either
   direction** over 137 probes, matching ad6's §9.22 figure. The old 3,660 excluded the
   single same-base pair `source.clients.wifi -> probe.clients.wifi`.

   *(This entry went through a wrong intermediate state earlier the same day: it was
   marked WITHDRAWN on the grounds that 3,660 was a deliberate self-excluded convention
   — `apkeep_up_diff.py` implements it, `APKEEP_BDD_BASELINE.md` froze it — and that
   both numbers were therefore right. That reading did not survive looking at the
   POLICY, which is what settled it.)*

   `Wifi` is not a host. `bench/wl_up/roles_and_services.txt:1586` defines it as an IPv6
   **/64 with no `hosts` list**, i.e. a subnet role whose one model node stands for every
   client device in it, and `bench/wl_up/reach.txt:17` says `Wifi <--> Wifi` — a
   deliberate, fine-grained, unconditional rule, and the only self-rule in that file that
   is not superrole expansion (`DMZ <--> DMZ` on line 6 yields the other eight diagonals,
   all unreachable). It states that wifi clients may reach each other: on a wifi network
   layer 2 is generally unrestricted, so this is a very common fact rather than an
   oversight. The exclusion's stated reason — "a host reaching itself is not a compliance
   question" — simply does not apply to it.

   The decisive evidence that self-exclusion was never a considered convention:
   `reach_csv_to_checks.py` has always emitted self-checks for wl_up -- **61** at the
   time, 69 today -- one per role whose policy diagonal is *empty* (`! s=source.X && EF p=probe.X`). Self-reachability
   was always a compliance question there; the `s != target` filter suppressed it only in
   the branches where the policy GRANTED it. That asymmetry, not a convention, is what
   dropped the pair.

   Fixed at the source: `--roles` carries each role's FPL attributes into the check
   generator, and a role whose single node denotes a proper subnet (not a bare address,
   not a `/0` placeholder — wl_i2 and wl_stanford give every router `ipv4 = 0.0.0.0/0`)
   keeps its self-check. wl_up: **11,903 checks, `reachable.json` 3,371 pairs, still 0
   violations**. Every other workload is byte-identical, verified by regeneration.
   `Internet` stays excluded, for the reason it always was: it is external, outside the
   administrative reach of whoever writes the policy, so its self-reachability is not
   answerable.

   *(The check count is **11,911** today. The eight `DMZ*` diagonals this paragraph
   classifies as single hosts turned out not to belong in the matrix at all — see §10,
   "superrole self-expansion". The attribute test above survives that fix and still
   decides `Wifi`; 3,371 pairs and the 3,661 headline are unaffected.)*

#### Coverage of these runs
All four benchmarks were run on both backends except wl_i2/APKeep-faithful (no
production route, see below) and the anomaly step, which APKeep does not implement and
which the harness now skips-and-says-so rather than reporting "none found"
(`AD6_PLAN.md` §9.28). wl_tum was not run: it is a single-device stateful firewall
already covered by the gated `test_apkeep_tum` differential against NetPlumber, and it
adds no case the four above do not.

#### Environment notes for the next person
* **`benchmark.py` bypasses `test.sh`'s `resolve_net_plumber`.** Run directly, the
  NetPlumber backend dies with `net_plumber: command not found` inside
  `scripts/start_np.sh`, which surfaces two layers up as "could not connect to fave" —
  the binary is present in `net_plumber/build/` and unreachable at the same time. Put
  it on `PATH` (or `make -C net_plumber/build install`).
* **63 MB `/dev/shm` cannot hold a wl_i2 NetPlumber run.** It produced **169 MB** of
  logs. Filling it does not fail the run cleanly: net_plumber becomes a zombie and the
  benchmark hangs indefinitely (observed, ~1 h wasted) — the capacity failure §9.29
  records for wl_stanford, on a second workload. `np.conf`'s three
  `RollingFileAppender` paths are redirectable, but `stdout.log` is *not*: log4j
  additivity mirrors every probe event to the console appender, and
  `aggregator_service.py:193` hardcodes `/dev/shm/np/stdout.log` as the reporter's
  verdict source. Both were redirected to disk for these runs via temporary edits to
  `bench/wl_i2/np.conf` and `scripts/start_np.sh` (log destinations only, no
  verification setting touched), **reverted afterwards**. A permanent fix would make
  the log directory configurable end to end rather than hardcoded in three places.

### Capability reassessment (APKeep paper, NSDI '20) — what is *conceptually* in scope

Reading the paper (Zhang et al., NSDI '20; copy in repo root) overturns the
earlier "out of scope" framing for state and extra header fields. The APKeep
*technique* is far more general than our as-shipped usage:

- **Arbitrary header is `h` bits of BDD variables** (§3.2): the model is
  header-agnostic. §4 states explicitly that one can *"encode these match
  conditions by adding more fields … the fields to add do not have to be packet
  headers"* — i.e. a **virtual, propagatable field is sanctioned**, which is
  exactly what FaVe's **state-shell interweaving** needs. So statelessness is not
  a blocker: interweaving compiles state into stateless rules over an extra
  field, the same way NetPlumber (also stateless) consumes it.
- **Packet rewrites are first-class** (§3.4, Alg. 3): rewriting elements encode
  header modification via existential quantification; NAT updates measured < 1 ms
  (§5.5). The state-shell's field transitions are therefore expressible.
- **Multi-field / policy-based-routing forwarding is element composition** (§4):
  in-port- or VLAN-conditioned forwarding is modelled by cascading match
  elements, not by a new primitive.
- **The one real cost is empirical, and the authors flag it** (§7): "a tradeoff
  between model granularity and the number of ECs." APKeep maintains the
  *minimum* EC set (Thm 1; Stanford 15M→515 ECs), so a richer/propagated header
  grows ECs only by the intrinsic number of distinct state×behaviour classes —
  the same lower bound any verifier faces. Whether APKeep keeps its scale edge
  under FaVe's full interwoven header is the measurable open question.

So the remaining workloads are **bounded engineering on an extensible model**,
not conceptual walls. Each extension is gated test-first by the APKeep core
hardening pass — see [`TESTING_STRATEGY_JAVA.md`](TESTING_STRATEGY_JAVA.md).

- **P6 — APKeep core test hardening. DONE (2026-06-30).** JUnit5 + jacoco harness
  (`mvn test` runs in `apkeep_smoke.sh`'s `mvn package`) + 16 unit tests on the
  reachability-critical path (`BDDACLWrapper` incl. a **variable-layout lock**,
  `ForwardElement` LPM/priority, `ACLElement` 5-tuple, `APKeeper` min-EC,
  `Network` wiring, `ReachabilityChecker` 0→94%); ratchet floor (BUNDLE
  instruction ≥ 30%). See `TESTING_STRATEGY_JAVA.md`. Gates P7–P9.

### wl_stanford modeling — decided via investigation (2026-06-30)

stanford is FaVe's HSA **3-stage pipeline** (`in`/`mid`/`out` switches per router)
of the same network APKeep models natively at router level. Investigation
(original configs + the hassel parser + APKeep's own snapshot) settled the
approach and retired two feared "wrinkles":

- **The "multicast" is L2 spanning-tree flooding**, original to the benchmark: a
  route's egress interface is a VLAN SVI (`172.20.4.0/23 → …, Vlan2`) and the
  hassel parser fans it out to the VLAN's spanning-tree ports. APKeep models the
  *same* flooding **compactly** — `ForwardElement` forwards to a single `vlanN`
  port and `vlan_ports`/`getVlanPorts` floods it at traversal (our
  `ReachabilityChecker` already does this). So it is a representation difference,
  not a limitation: reconstruct the factored form from FaVe's expanded multi-fd
  (`+ fwd dev <prefix> <len> vlanN <prio>` + a `vlan_ports` map).
- **VLAN has two roles** — a *flood* construct (above; APKeep already has it) and
  an ACL *match* field (the ingress/egress ACLs are keyed by VLAN). Adding the
  latter is the clean fix for per-interface ACL scoping (avoids splitting into
  ~46 ACLElements per edge router) **and** the minimal multi-field rehearsal for
  wl_up — so we add it (P9a).

- **P9a — VLAN as a header *match* field in APKeep core. DONE (2026-07-01,
  commit `350e6f33`).** Added a 12-bit `vlan` field to `BDDACLWrapper` whose BDD
  variables are declared *last* (after `DstIP6`), so no existing field shifts —
  the P6 layout-lock proves it; `ConvertVLAN` (exact value via `ConvertRange`) is
  AND-ed into `ConvertACLRule` only when a rule carries a tag. `ACLRule` gained an
  *optional trailing* VLAN token, so the historic 14-token format is unchanged
  (existing wl_ifi ACLs + the Python integration are unaffected); the
  `ForwardElement` FIB is untouched. Test-first: `BDDACLWrapperTest` (VLAN
  independent/distinct + the layout-lock still passing), `ACLElementTest`
  (VLAN-scoped deny/permit), and a new `VlanFloodTest` pinning the previously
  untested `getVlanPorts` flood branch P7 needs. 19 tests green; jacoco ratchet
  raised 30% → 33% (now 36.6%).
- **P7a — wl_stanford forwarding (out-stage collapse). DONE (2026-07-01).** The
  `out.X` stage is an `in_port→out_port` permutation a dst-IP `ForwardElement`
  cannot express; the generic path collapsed it to one /0 default and forwarding
  broke (baseline: missing=204/240). `APKeepAdapter._collapse_out_stage` resolves
  the `mid.X.<110n> → out.X.<130n> → [perm] → out.X.<120m> → in.Y/probe` chain
  statically and wires the `mid.` egress interface straight to the external
  neighbour, dropping `out.` (48 switches → 32 `ForwardElement`s). `in.` is a
  pass-through, `mid.` the dst-IP FIB. Gate: `test_apkeep_stanford.py` +
  `gen_wl_stanford_inputs.sh`; from-zero wired into `apkeep_vs_netplumber.py`
  (steady ~1.3 s, comparable to NetPlumber ~1.4 s).
  - **But the "exact match vs `reachable.json`" is policy-only, NOT a data-plane
    correctness check.** `reachable.json` is the artificial *all-to-all* policy;
    forwarding-only APKeep trivially satisfies it.
- **P7b — wl_stanford faithful VLAN+ACL (= P8 rewrite). PARTIAL: 240 → 77 (sound),
  VLAN admission blocked on an APKeep-core limitation.** The NetPlumber
  cross-check (the reference oracle) quantifies the gap the policy oracle hid:

  | backend | reachable pairs |
  |---|---|
  | APKeep (forwarding-only) | **240 / 240** |
  | NetPlumber (faithful HSA) | **10 / 240** (all edge→core) |

  APKeep over-approximates on **230/240** pairs; the whole gap is the VLAN.
  Rule-structure evidence (feasibility spike, 2026-07-01):
  - `in.` **matches** `(in_port, vlan, 5-tuple)`, never rewrites (511 distinct
    VLANs matched); `mid.` **rewrites** `vlan→N` keyed by dst-route (3372 rules,
    **190 distinct N**, up to 17 VLANs per egress port — so VLAN is *not*
    port-determined); `out.` mostly **passes N through** (only 45 rules reset →0),
    so VLAN **propagates across router boundaries**; probes require `vlan=0`
    (only the 45 resets produce it — hence 10/240).
  - **All 190 mid-assigned VLANs are consumed by a downstream `in.` stage** — the
    rewrite couples routers along the whole path. This resolves the old open design
    point: **static per-port composition (route i) is infeasible** (the arriving
    VLAN is set by the *previous* router's route-dependent rewrite, which only
    resolves at flow-propagation time); **the VLAN rewrite (route ii = P8) is
    required.**
  - **DONE (2026-07-01):** (1) Java VLAN-rewrite core — `Fields.vlan`,
    `get_field_bdd(vlan)`, field-selecting `RewriteRule` (commit on subtree).
    (2) NAT-in-reachability — `NATElement.encodeOneRule` VLAN form, inline NAT
    insertion in `Network.addNATs`, `ReachabilityChecker` rewrites through NATs;
    the AP-merge crash on multi-rule NATs fixed (disable-able `MergeAP`).
    (3) LibAPKeep `device_nats` + `target_vlan`. (4) Adapter faithful path
    (`faithful_vlan`): mid VLAN-rewrite NATs (folding the out-stage reset into the
    effective egress VLAN) + probe `vlan=0` target-header filter.
  - **Result: 240 → 77, a SOUND superset of NetPlumber's 10** (verified in
    separate processes: NP-only/under-approx = 0). The probe filter is correct.
  - **VLAN admission (77 → 10): correct, but blocked on PERFORMANCE, not
    modelling.** *(Superseded — see "Deferred merge, split/merge cost model, and
    the two-gap finding (2026-07-07 … 07-10)" below: a bounded-subset cross-check
    shows `77 → 10` is NOT only VLAN admission and NOT only performance; there is a
    second, orthogonal transfer-function-fidelity gap, so even a tractable faithful
    model stays a sound superset of NP.)* VLAN admission is a *drop-by-field*
    filter, and the only element
    that drops is `ACLElement`, which by default activates **AP division** (a
    separate ACL AP universe that disagrees with the forwarding-universe VLAN
    rewrite → `fwd ∩ acl ∩ vlan=0` empty; measured: in-admission alone 217, probe
    alone 77, **both 0**). Fix: a **single-universe** mode
    (`Parameters.USE_DIVISION=false`) keeps ACLElements in the forwarding APKeeper
    so admission and rewrite compose in one universe; `ReachabilityChecker` then
    filters the forwarding AP set at ACLs. **Confirmed correct** by
    `NATReachabilityTest.ingressAdmissionComposesWithRewriteInOneUniverse` (ingress
    ACL upstream of the rewrite, egress ACL downstream). The adapter splices a
    per-router ingress ACL (`iacl_<idx>`, admitting the in-stage's VLANs) onto the
    `in.X → mid.X` edge.
  - **NAT+merge AP-maintenance: FIXED (2026-07-01).** Merging with multi-rule NATs
    used to crash because `NATElement` merged atomic predicates **eagerly
    mid-update** (both `tryMergeIfNATElement` and `transferOneAP`), removing APs the
    split loop / batch merge still referenced → cascading stale-AP crashes
    (`APNotFound`/`APSetNotFound`) + a JDD `quant_rec` use-after-free. Consolidated
    ALL merging into the single end-of-update batch merge (guards + no-op eager
    sites + `updateAPSetMergeBatch` rewrite-table maintenance). 24 unit tests green
    with merge ON; the full wl_stanford faithful build no longer crashes or OOMs.
  - **NOW BLOCKED on build PERFORMANCE (2026-07-01).** The faithful build does not
    finish in 25 min. **Tried and ruled out** as the primary cause: (a) the per-rule
    batch merge (merge on vs off — both >400 s); (b) the ~1800 per-VLAN admission
    ACL rules — a **compact encoding** (one ACL rule per router over the admitted
    VLAN *set*, ~1800→16 rules; `ConvertACLRule` now ORs a comma-separated set) did
    NOT make it tractable either. The mid-NATs *alone* build in ~50 s (the sound-77
    model), so the dominant cost is the **interaction of the ~3372 per-route VLAN
    rewrites (NATs) with the VLAN-set ACLs in one AP universe** — the rewrites over
    the ACL-split predicates blow up BDD/AP work. This is impractical for the
    from-zero benchmark (NetPlumber builds wl_stanford in ~1.4 s), and it is a
    *modelling*-efficiency wall, not a bug: **APKeep's own stanford snapshot builds
    in <1 s (515 APs)** because it does NOT model the VLAN reassignment as
    thousands of per-route NAT rewrites. Reaching a tractable exact 10/240 needs a
    fundamentally more efficient stanford encoding (closer to APKeep's native form)
    — a separate, larger effort. The VLAN model itself is correct and composes
    throughout (unit-tested); every blocker has been an APKeep-core scale/perf
    issue. **Recommendation: ship the sound over-approximation (77 ⊇ NP's 10) for
    the benchmark**; the faithful path stays gated, correct-but-intractable.
  - Note: NetPlumber's `.so` diff is reproducible locally (needs `liblog4cxx`);
    APKeep vs NP must be run in SEPARATE processes (the resident JVM + NP in one
    process cross-contaminates -- NP wrongly reports 240).
- **P8 — state-shell rewrites (subsumes the P7b VLAN rewrite).** The VLAN rewrite
  above *is* the general runtime-rewrite mechanism: `NATElement`/`RewriteRule`
  generalized off dst-IP to any declared field. Test-first. Once it exists, wire
  the state field's rewrites through the adapter + `ReachabilityChecker` and
  reproduce wl_ifi's `related:` cchecks (currently skipped). Enables the stateful
  part of wl_tum.
- **P9b — general header extension / IPv6.** Generalize P9a to arbitrary fields +
  implement the scaffolded `ForwardingRule6` + an IPv6 ACL path. Enables wl_up
  (IPv6 + state-shell).
- **Per-workload:** wl_stanford = P6 + P9a + P7a (forwarding) + **P7b/P8 (faithful,
  VLAN rewrite required)**; wl_tum = + P8 (1 device, low scale value); wl_up = + P8
  + P9b (highest effort). The stanford cross-check retired the "stanford is
  rewrite-free" assumption: its faithful model needs the same P8 rewrite mechanism
  as wl_tum/wl_up, so P8 is now on the critical path, not optional. i2 already
  carries the scale result independently.
  - **wl_tum/wl_up now have a dedicated plan + Phase-0 evidence:
    [`APKEEP_TUM_UP_PLAN.md`](APKEEP_TUM_UP_PLAN.md)** — the audited profiles, the
    "state is a *match*, not a per-route rewrite" reframing (so no AP-explosion),
    the diagnostic probe (APKeep builds wl_tum's 3.8k stateful rules in 1.77 s but
    under-approximates: no `related`/`svlan`/`dvlan`/port-rewrite model), and the
    phased plan (wl_tum first; reverse-flow `related:` rewrites in scope).

### Performance analysis: BDDs vs APs, and the VLAN AP-count impact (2026-07-01)

Why is the faithful wl_stanford build intractable while APKeep's own stanford runs
in <1 s? The answer is architectural, and it corrects a tempting misconception
("adding a 12-bit field must add many APs").

**How APKeep uses BDDs vs. APs (from the code).** An atomic predicate is a
`Set<Integer>` whose ids *are* BDD-node ids used as **labels**; `ap_ports` /
`ports_aps` are integer-keyed maps. BDD operations occur only at **boundaries**:

| Path | Operation | Cost |
|---|---|---|
| reachability transfer | `Element.forwardAPs` = `retainAll` | **AP-set (fast)** |
| reachability arrival | `Element.hasOverlap` = `bdd.and` per AP-pair | BDD — *only under ACL "division"* (two AP universes) |
| source seeding | `APKeeper.getAPExp(pred)` = `bdd.and` over all APs | BDD, O(\|AP\|) |
| rule insert | per-rule `hit_bdd` via `bdd.and`/`diff` | BDD, per rule × affected rules |
| AP maintenance | `updateSplitAP` = `bdd.and`/`diff` **per AP a delta cuts** | BDD, per rule × APs |
| rewrite / merge | `nat` (exists+and), `OrInBatch` | BDD |

The **analysis/query** path is already essentially BDD-free (`retainAll`); the
only avoidable BDD there is `hasOverlap`, which needs `bdd.and` *only because
division* splits forwarding and ACL predicates into two AP universes — a
**single-universe** mode (`Parameters.USE_DIVISION=false`, added in P7b) makes it a
plain set intersection. The **build/insert** path is inherently BDD-based: splitting
the AP partition when a rule cuts existing predicates *requires* BDD `and`/`diff`.

**Measured AP counts (`getAPNum`):**

| model | VLAN usage | APs | build |
|---|---|---|---|
| wl_stanford forwarding-only | 12-bit field declared, **unused** | **133** | 1 s |
| wl_i2 (77k routes) | none | 216 | 11 s |
| APKeep's own stanford (upstream) | no VLAN field | 515 | <1 s |
| wl_stanford + mid VLAN **rewrites**, merge OFF | rewritten per route | **7916** | 57 s |
| wl_stanford + mid VLAN rewrites, merge ON | rewritten per route | (coalesces) | >400 s (times out) |

**Conclusions.**
1. **Header *width* costs nothing.** With the 12-bit VLAN field declared but not
   matched, wl_stanford stays at **133 APs** — APs count *distinct behaviours*, not
   header bits; unused variables leave the AP predicates unconstrained. So "extend
   by 12 bits → more APs" is false for VLAN as a *match* field.
2. **VLAN as a *rewritten* field explodes APs ~60× (133 → 7916)** — each mid-stage
   rewrites VLAN per dst-route, fragmenting every forwarding class into
   (dst, egress-VLAN) sub-classes. This is a property of the *per-route-NAT
   modelling*, not of VLAN: APKeep's native stanford holds the same network at 515
   APs by not encoding VLAN reassignment as thousands of per-route rewrites.
3. **The AP increase does not slow the AP-set (query) path** — `retainAll` over a
   few thousand ids is microseconds. It blows up the **build**: AP splitting is a
   BDD op *per AP*, so insertion is ~O(rules × APs × BDD); at 7916 APs the admission
   ACLs fragment further → OOM (merge off), or, with merge on to coalesce back
   toward ~515, the per-rule batch merge over ~3372 rewrites is itself too slow.

**So the bottleneck is BDD work at build time + AP fragmentation from the modelling,
not the 12-bit width and not the AP-set analysis path.** The tractable levers are a
**compact rewrite encoding** (coarser VLAN reassignment → far fewer APs, approaching
the native 515) and/or a faster batch merge — not reducing header width. The
avoidable query-side BDD (division) is already removed via single-universe.

### Deferred merge, split/merge cost model, and the two-gap finding (2026-07-07 … 07-10)

This extends the analysis above and **corrects** the earlier P7b claim that the
`77 → 10` gap is *only* VLAN admission blocked on *performance* (see the P7b bullet
"VLAN admission (77 → 10): correct, but blocked on PERFORMANCE, not modelling"). A
bounded-subset cross-check against NetPlumber shows there are in fact **two
orthogonal gaps**, and closing the performance one alone does **not** reach 10.

**(a) Deferred per-table merge — tried, ruled out.** The from-zero build does a
merge pass per rule; a batch-style variant defers the per-rule merge and merges
once per FaVe "table" (`Parameters.DEFER_MERGE` + `Network.mergeAPs()`;
adapter groups rules by device and calls `run()`+`merge()` per group). Still
> 400 s. Per-group logging pinned the cost exactly:

| rule class | count | header shape | cost |
|---|---|---|---|
| admission ACL (`iacl_*`) | **16** | **all 16 whole-space-except-VLAN** (any src/dst/proto/ports) | **~25 s each** (`iacl_0` measured 25.3 s) |
| `fwd`/`nat` specific | ~6790 | dst prefix, mode /24 | cheap (dst-local) |
| `fwd`/`nat` default `/0` | 48 | whole dst-space | broad but partition-local |

Each admission ACL is wildcard on every field but VLAN, so its `ChangeItem` delta
lands on the port holding **every** AP → `Element.updatePortPredicateMap` scans the
whole ~8000-AP partition (`bdd.and` per AP) and *splits* ~1141 APs, **growing** the
partition for the next ACL. ~16 × ~25 s ≈ the whole timeout.

**(b) Insertion order — tried, ruled out.** Inserting the 16 ACLs *first* (trivial
partition) drops them to **0.0 s each**, but then every one of the 3372 dst-wildcard-
on-VLAN FIB rules sweeps the VLAN-split partition: `mid.bbra` alone went 2.7 s / 1963
APs → **157 s / 5932 APs**. The final partition is the **VLAN×dst cross-product**
(order-independent); *some* rule class must sweep it, and there are ~200× more FIB
rules than ACLs, so moving the cost onto them is strictly worse. **No free lunch in
merge timing or insertion order.**

**(c) Split/merge cost model (from the code).** A single `updateSplitAP`/
`updateMergeAP` is **cheap and AP-count-independent**: a handful of header-bounded
BDD `ref`/`deref`/`or` ops + `O(#elements)` integer bookkeeping (clone the
ports-vector, update each element's `port_aps_raw`). AP count enters runtime **only**
through what *drives* splits — `updatePortPredicateMap` does one `bdd.and(delta, ap)`
per AP at the affected port, so a whole-space rule is `O(|AP|)` and a full build is
`≈ Σ_rules O(|AP| at that point) ≈ O(rules × |AP|)`. The **query** path is
`retainAll` (integer sets, microseconds) + `O(|AP|)` seed. So: **a large AP count is
fine for analysis and a long one-time build would be acceptable *if* |AP| were
bounded** — the wall is the `O(rules × |AP|)` build term, binding here because |AP|
is both large *and* un-mergeable (the per-route NAT rewrite outputs share no
ports-vector, so `NATElement.isMergable` refuses to coalesce them). The earlier OOM
was transient allocation churn during that sweep, not live state (~10⁶ live
nodes/entries, well under the 16 M table).

**(d) Structural VLAN (option 1) — tractable, but a sound *over-approximation*.**
Folding each mid route's effective egress VLAN into the *identity* of its egress port
(`<port>v<vlan>`) and encoding admission structurally (a qualified edge exists only
where the downstream admits that VLAN) sidesteps the NAT cross-product entirely — the
partition stays dst-based and coalesces. Measured (throwaway, env-gated
`STRUCTURAL_VLAN=1`, not committed): **337 APs, ~2 s build, ~3 s for all 240 queries,
reachable = 77** — again a **sound superset** of NP's 10 (all 10 present, 0 missing).
Adding faithful in-stage source/dst uRPF ACLs (per-`(router, arriving-VLAN)`
`ACLElement`s, first-match, default-deny, single-universe) left it at **77** — so the
in-stage 5-tuple ACLs are **not** the `77 → 10` mechanism.

**(e) Bounded-subset faithful cross-check (2026-07-09) — the decisive experiment.**
`subset_check.py` restricts wl_stanford to a router subset (induced sub-topology:
keep a link only if both endpoints are in-subset), writes an identical subset
snapshot, and runs **either** backend (separate processes — the resident JVM + NP
cross-contaminate). This makes the **faithful header-field NAT model tractable** so it
can be compared to NP directly. On the 2-router subset `{bbra_rtr, rozb_rtr}`:

| backend | reachable | pairs | size / time |
|---|---|---|---|
| **faithful APKeep** (`faithful_vlan`, VLAN = header field) | **2** | `bbra→rozb`, `rozb→bbra` | **2552 APs**, 6 s |
| **NetPlumber** (reference) | **1** | `rozb→bbra` only | 0.2 s |

(The 2552 APs for *two* routers is exactly the per-router NAT cross-product that
makes the full 16-router build ~8000 and intractable.) **The faithful VLAN model
over-approximates NetPlumber even when tractable, and is again a sound superset.**
This corrects the earlier assumption that a tractable faithful model would reproduce
NP's 10 — it would not.

**(f) Root cause: a second, orthogonal fidelity gap.** Tracing the false pair
`bbra→rozb` hop by hop on the subset ruled out every ACL/admission cause — on this
subset `in.rozb` has 76 permit-all VLANs and **0** refined rules, `out.rozb` has **0**
source matches, `in.rozb` **does** admit the transit VLAN (2) on the bbra link, and
all ingress funnels to `mid.rozb.1220000`, exactly the in-port the probe-delivery rule
requires. Every hop is individually *permissive in the model*. The over-approximation
is **cumulative**: **all 6109 mid+in transfer-function rules are in-port-qualified**,
but the adapter models them with **decoupled per-field elements** — `ForwardElement`
routes by **dst only** (in-port dropped), VLAN admission is per-VLAN (not
per-`(in_port, VLAN, dst)`), and the out-stage collapse **drops out-stage VLAN
matches** — whereas NetPlumber propagates `(in_port, vlan, src, dst, proto, dport)` as
one **jointly-correlated** packet set and finds no *single coherent header* traverses
`bbra→rozb`. It is not one rule; it is the decoupling.

**Conclusion — two independent gaps between FaVe+APKeep and NetPlumber:**

1. **VLAN tractability** — the un-mergeable NAT cross-product (2552 APs / 2 routers).
   Fix = make rewrite outputs coalesce (**`NATElement.isMergable` generalization**,
   "option 2"), which would also serve wl_up's stateful rewrites.
2. **Transfer-function fidelity** — the adapter approximates the in-port-qualified,
   jointly-correlated Stanford TF with decoupled per-field elements. Fix = faithful
   in-port-qualified forwarding + out-stage VLAN in the **adapter** (independent of
   option 2).

Closing **only** gap 1 yields a model that *scales* but still reports a **sound
superset** of NP, not equivalence. **Reproducing NP's exact 10/240 requires both.**

### Full per-(port,VLAN) admission tractability — dedicated investigation (2026-08-12)

Context reset by the LPM + in-port fixes: NP and APKeep now **agree exactly at 165**
on wl_stanford *without* any VLAN modelling (the source spans all VLANs, so admission
is non-binding for the all-pairs query, and the in-port dead-port gate
`_gate_dead_ingress` captured the only binding ingress effect). This investigation
asks whether full per-`(port, VLAN)` admission — needed for VLAN-specific / deny
queries and other workloads — is tractable *and* exact. Measurements (`getAPNum` +
build timing, `faithful_vlan=True`, full 16 routers unless noted):

| regime | APs | build | reachable | note |
|---|---|---|---|---|
| forwarding-only (+ in-port gate) | 177 | 0.6 s | 165 | matches NP; VLAN unused |
| **admission-only** (VLAN ACLs, **no rewrite**) | 249 | **0.8 s** | **56** | tractable but **UNDER-approximates** |
| full faithful (admission **+** rewrite) | ~8000 | **>480 s (no completion)** | — | intractable |

1. **Admission itself is cheap; the coupled *rewrite* is the wall.** Admission-only
   builds in 0.8 s — but drops to **56** reachable, a severe *under*-approximation:
   without the per-hop VLAN rewrite the source VLAN stays frozen, so a packet must be
   admitted at *every* hop (an intersection), whereas real routers rewrite VLAN per
   hop, so the arriving VLAN at hop N is the previous hop's rewrite output. **Faithful
   admission therefore *requires* the rewrite, and the rewrite is the intractable
   part** — admission and rewrite cannot be decoupled.
2. **The rewrite is genuinely per-destination, not per-port** — so it cannot be
   compacted to a cheap per-egress-port NAT. Egress VLAN = f(dst subnet): **79 egress
   ports carry >1 VLAN** (trunks; e.g. mid.bbra port 110012 → {2,22,42,564,566}).
   Coalescing NATs by `(port, vlan)` cuts only 3372 → 1561 (~2×); there are **190
   distinct egress VLANs** genuinely fragmenting the space.
3. **Super-linear build growth**, even on the *small*-FIB edge routers (faithful,
   edge-only subsets): n=2/3/4 → 752/2477/2625 APs at **4.5 / 28.3 / 63.5 s**; n=6
   >120 s; full 16 (incl. the big backbone FIBs) >480 s. Consistent with the
   `O(rules × |AP|)` build term and the un-mergeable per-route-NAT cross-product.
4. **Exact quotient lever (novel, but only ~3×).** Reachability only cares whether an
   arriving VLAN *passes the next admission*, not its exact value, so VLANs with the
   same admission signature (which routers admit them) are interchangeable. The 190
   egress VLANs collapse to **64 admission-equivalence classes** — an *exactness-
   preserving* reduction (unlike structural VLAN). But the class-size distribution is
   long-tailed (26,18,17,17,16, then many singletons), so it buys only ~3× (~190→64 in
   the VLAN dimension ⇒ est. ~2700 APs / ~160 s) — still impractical vs NetPlumber's
   ~1.4 s, and nowhere near the ~15× needed to approach APKeep's native 515-AP regime.
5. **The only *tractable* encodings sacrifice exactness or faithfulness:** structural
   VLAN (finding d) — 337 APs / 2 s but a sound *over*-approximation that folds VLAN
   into port identity (no header-based admission); admission-only (above) —
   *under*-approximation.

**Verdict.** Full per-`(port, VLAN)` admission, done faithfully (with the per-hop
rewrite it inescapably requires), is **intractable at 16-router scale in APKeep's
per-route-rewrite AP model** — a fundamental property of the dst×VLAN cross-product,
not a merge-timing or insertion-order artifact (both ruled out, findings a/b). The
exactness-preserving admission-equivalence quotient is the right lever if one must push
on it, but expect ~3×, not orders of magnitude; genuine scale needs a fundamentally
different (non-per-route-rewrite) VLAN encoding akin to APKeep's native snapshot.
**Practically, it is not required for wl_stanford** (both backends already exact at
165); it is a prerequisite only for VLAN-discriminating queries / other workloads.
The subset `{bbra_rtr, rozb_rtr}`, with its single known discrepancy (`bbra→rozb`),
is a fast minimal regression oracle (both backends in seconds) for developing gap 2.

### Baseline validation: NetPlumber vs config-derived ground truth (2026-07-10)

Before trusting NetPlumber as *the* oracle, we validated it against an **independent
ground truth** — the original Stanford Cisco data (`bench/wl_stanford/stanford-hassel/
*_config.txt` + `*_route.txt`), **not** against itself and **not** against
`reachable.json` (which is the artificial *all-to-all* policy — checking NP against it
would "confirm" NP by comparing to a known-bad answer). Deriving truth from the
original config validates the **whole FaVe→NetPlumber pipeline** (config → Hassel TF →
FaVe JSON *translation* **and** the NP *engine*), not just self-consistency. We
hand-derived reachability for the `{bbra_rtr, rozb_rtr}` subset from the route tables:

**Verdict (SOLID, confirmed at NP flow level):** `bbra→rozb` is genuinely UNREACHABLE
and `rozb→bbra` genuinely REACHABLE in the subset. NetPlumber is **sound AND complete**
on this pair (forwards the right flow, drops the wrong ones, drops nothing legitimate,
forwards nothing spurious); APKeep over-approximates with the `bbra→rozb` false positive.
The independent-oracle framing above means this validates the FaVe translation + NP
engine end-to-end, not just self-consistency.

> **Correction (2026-07-10, flow-level).** An earlier draft of this section attributed
> `bbra→rozb`'s unreachability to a *routing* mechanism — bbra's routes to rozb-local
> subnets take L3 next-hops (`172.20.4.65`=roza, `172.20.5.33`, `172.20.4.2`) owned by
> *third* routers absent in the subset — and framed APKeep's error as "dst-only
> forwarding ignoring the L3 next-hop on the shared `/23` segment." **That mechanism was
> wrong** (NP excludes `bbra→rozb` in the *full* topology too, where those routers are
> present; and instrumenting APKeep's checker + walking NP's own flow trees told a
> different story). The routing facts are still true, but they are **not** the operative
> reason. The corrected, flow-grounded mechanism follows.

**What NP actually does (from `dump_flow_trees`, the authoritative per-hop record):**

- `source.bbra` **does inject and reach `mid.bbra`** (869 flow branches) — so an earlier
  "bbra can't source (its ingress port has no rule)" idea is **also retracted**; bbra
  sources fine. But its flow **crosses to no neighbor**: 868 branches die at the
  `mid.bbra → out.bbra` transition, 1 reaches `probe.bbra` (self). It never touches any
  rozb table.
- `source.rozb` **does cross**: `in.rozb → mid.rozb → out.rozb → in.bbra → mid.bbra →
  out.bbra → probe.bbra` (the real `rozb→bbra` pair).

So the divergence is the **out-stage crossing**, not the in-stage and not a routing
next-hop. Both cross-links exist in NP's plumbing (`out.bbra→in.rozb` **and**
`out.rozb→in.bbra`), so it is **not a missing edge**. At a dying `mid.bbra` branch the
downstream `out.bbra` in-port **has a rule**, yet **no pipe forms** — i.e. a
**header-overlap failure at the out-stage** (NP builds a pipe only where the upstream
output header-space intersects the downstream rule's match). APKeep, by contrast,
**collapses the out-stage** (`_collapse_out_stage` / `_out_perm` wire each `mid` egress
straight to the neighbour), bypassing whatever header condition the out-stage enforces —
so it forwards `bbra`'s transit across to rozb and reports the false positive. **This is
P7c gap 2 (out-stage / transfer-function fidelity), now localized to the out-stage
crossing by NP's flows.**

**UPDATE 2026-09-24 — the localised symptom is GONE, the structural gap is not.**
Both APKeep modes are now **pair-identical to NetPlumber** on wl_stanford:
165/165, EXTRA=0, MISSING=0, faithful *and* plain. So the `bbra -> rozb` false
positive described above no longer reproduces, and the field below no longer has
a live symptom to be isolated from.

What remains is structural and measured: the collapse still discards **1,986
out-stage forwarding rules' match conditions** and **16 explicit denies**
(fields: vlan 1986, ip_proto 1624, ipv4_dst 1592, tcp_dst 1453, ipv4_src 460,
tcp_flags 24), and in the production faithful configuration the out stage
contributes **zero rules** to the engine. It costs nothing observable on this
240-pair check set -- which is precisely the hazard, since a reachability matrix
can be blind to a dropped constraint. **Reopened as TODO item 24**, with the
observation that `_demux_ingress` now expresses the in-port qualification whose
absence forced the collapse in the first place.

**PLAN 2026-09-24: [`OUT_STAGE_PLAN.md`](OUT_STAGE_PLAN.md).** Sizing it changed
the shape of the problem. Only **68 of the 681** out-stage arrival ports carry a
condition at all -- the other 613 are unconditional permutations the collapse
models *exactly*, not approximately -- and all **45 VLAN resets** sit on those
same 68 ports, so the `_out_reset` fold and the discarded conditions cover
identical ground and can be unfolded together. The plan therefore keeps the
collapse for 613 ports and gives the 68 a dedicated `FilterElement` builder.

Two findings from that sizing bear on the note below. First, on **all 68**
conditional ports the unioned permutation reaches **no more egress ports** than
the port's own catch-all, and every catch-all forwards -- so the collapse is
over-permissive purely in the HEADER dimension and **reachability cannot move**
when it is fixed. That is a stronger statement than "costs nothing observable
today": no pair-set oracle can ever evaluate this work, which is why the plan's
step 0 is a conditioned differential with the acceptance criterion that it must
FAIL on the current tree. Second, the `tcp_flags` rules are all **permits** in
front of the `ip_proto=6 + vlan=78` deny (an established-only egress filter), so
dropping that conjunct does not merely widen one rule -- it makes 2 of the 16
denies inert. The `vlan=68` denies and the 12 `ipv4_src` anti-spoofing denies are
expressible today.

**Still open — the exact out-stage field.** The condition is confirmed to be an
out-stage *header-overlap* failure, but the precise discriminating field/value is **not
yet isolated**: decoding NP's packed 48-bit header vectors was unreliable, and the
plain rule-text reading is self-contradictory (by the rule text — `mid` rewrites vlan→2,
`out.bbra.130001` matches any-vlan → `120001` → `in.rozb` which admits vlan 2 — the flow
*should* cross, yet NP builds no pipe). That contradiction means the discriminator lives
in NP's header-vector/pipe computation and needs proper vector decoding (or making
APKeep honour the out-stage and checking convergence against the NP flow oracle). **Do
not assert a specific VLAN value until this is decoded.**

**GRE is a red herring for this pair** (the operator flagged that GRE/tunnels are not
natively supported and its handling was uncertain): the witness dst `192.168.209.204/30`
is rozb's Tunnel10 subnet, but NP's flow dies at `mid.bbra` long *before* any tunnel
delivery — so tunnel handling is irrelevant to `bbra→rozb`. (It may still matter for
other pairs; not chased here.)

**Method note / how the picture was obtained.** The `ReachabilityChecker` was
instrumented with a `witnessPath`/`witnessFwd` capture (public fields set on first
arrival) to dump APKeep's exact 18-hop path; NP's side used the libnetplumber binding's
`dump_flow_trees` / `dump_plumbing_network`. NP's flow dump is now the reliable per-hop
oracle for developing the gap-2 fix — replacing static rule inspection, which produced
five successively-disproven mechanisms here.

**Caveats:** existential reachability (a *path*, not the exact header *set*); one
router-pair. A 3-router aggregation subset (`{bbra, roza, rozb}`, where `bbra→rozb`
should flip to reachable) and a header-set comparison remain the next confidence steps.

### Known limitation: APKeep does not model discard / `Null0` drop rules (2026-07-10)

The adapter's `_translate_fwd_rule` **used to** skip any rule with no forward action
(`if not out_ports: return`) — including Cisco **`Null0` / discard** routes (e.g.
`192.168.0.0/16 → Null0`, a standard aggregate/anti-bogon discard). NetPlumber (and the
real routers) honour these, so APKeep would **over-approximate for destination ranges
that reality genuinely discards** — reporting packets to those ranges as forwardable
when they would be dropped. Direction of unsoundness: *safe* for isolation /
"must-not-reach" policies (a false *alarm* — private space stays private) but *unsound*
for reachability / "must-reach" guarantees (false assurance of connectivity that can
mask an outage); operationally the false alarms are costly and erode trust.

**FIXED for dst-only discards (2026-07-10, commit `886a2082`).** `_translate_fwd_rule`
now models a *dst-only* discard as a blackhole forward to a dead `__drop__` port (no
topology link ⇒ a sink) at LPM priority — it shadows shorter-prefix forwards while a
longer-prefix forward still wins by LPM, matching NetPlumber (uses APKeep's existing
`ForwardElement`; no core change). Default-on. **Soundness guard:** discards that
constrain non-dst fields (source/proto/dport) are still skipped (a dst-LPM
`ForwardElement` can't express them; a dst-only approximation would over-drop →
false negatives); those need `ACLElement`s (out of scope). **Validated — no
regressions:** wl_ifi 3/3, wl_i2 2/2 (77k-route build + exact oracle match), wl_stanford
P7a 2/2, adapter/acl/lib 9/9, backend-differential 3/3 (APKeep ≡ NetPlumber on wl_ifi).
wl_ifi and wl_i2 have **zero** dst-only discards, so the change is a no-op there; it
exercises on stanford, which still matches its oracle. **Residual:** the
source/proto/dport discards above remain unmodelled.

**Scope — this is NOT the cause of the `bbra→rozb` false positive above.** Three pieces
of evidence rule that out: (1) NP does *not* drop `.204` — injecting it from bbra, the
flow reaches `probe.bbra`, so it is forwarded, not discarded; (2) NP applies LPM
correctly and the `192.168.208.0/20` **forward** (more specific) beats the `/16`
discard, so `.204` matches the forward; (3) the `DROP_RULES=1` prototype left
`bbra→rozb` reachable (unchanged), because under correct LPM the `/16` cannot shadow the
`/20`. Moreover `.204` lies inside the *forwarded* `/20` (internally-routed private
space), **not** the bogon remainder the `Null0` swallows — a real packet to `.204` is
forwarded at bbra (toward `172.20.5.33`), not dropped. So the discard-skip is a **real,
independent** modelling gap; the `bbra→rozb` pair is caused by the separate,
still-unpinned out-stage/segment-crossing gap.

### NetPlumber `Node::propagate` read — split-horizon exists but is dormant (2026-08-11)

Read NP's flow propagation to explain the `bbra→rozb` out-stage crossing:
`RuleNode::process_src_flow` (`rule_node.cc`), `Node::propagate_src_flow_on_pipes`
(`node.cc:395`), and `should_block_flow` (`node.cc:385`).

**Finding 1 — NP *does* have split-horizon (the operator's original hypothesis was
right; an earlier dismissal here was wrong).** At the output-layer emission,
`node.cc:406`: `if (is_output_layer && should_block_flow(*s_flow, next->local_port))
continue;`. `should_block_flow` recurses up the flow's provenance chain (`p_flow`) to
the **input-layer** node and returns `f->in_port == out_port` — *don't emit a flow out
the interface it entered on*. The ingress port is carried as **flow metadata**, not a
header field — which is why the earlier "the header has no port field ⇒ no
split-horizon" reasoning missed it. **Retract that dismissal.**

**Finding 2 — but split-horizon is DORMANT in the FaVe 3-stage Stanford model
(verified).** Port structure (subset `{bbra, rozb}`): `source.bbra` **and** the
`out.rozb → in.bbra` link both land on `in.bbra.100001`; `source.rozb` **and** the
`out.bbra → in.rozb` link both land on `in.rozb.1200001` — i.e. each source sits on its
*peer-facing* interface. If split-horizon fired it would block **both** directions
symmetrically; but `rozb→bbra` **is** reachable, so `should_block_flow` is **not
firing**. Reason: the 3-stage model numbers an interface's input vs output ports
differently (`100001` in vs `120001` out — offset by the port-type multiplier), so
`in_port == out_port` is never true. So the feature is present but inactive here —
**neither the cause of `bbra→rozb` nor an active APKeep gap on Stanford.** (It is still
worth an adapter equivalent for *general* correctness / other topologies.)

**Finding 3 — the two *active* propagation mechanisms**, and the honest limit. A flow
propagates only where (a) its rewritten space intersects the next **pipe** filter
(`propagate_src_flow_on_pipes`: `has_isect` gate, `node.cc:437`) and (b) it survives
**higher-priority subtraction** (`process_src_flow`: for each `influenced_by` rule whose
ports include `f->in_port`, `hs_diff` it out — `rule_node.cc:350`). NP's `bbra` flow
dies at the **mid** stage. After tracing this pair through the model, the adapter, NP's
flow dumps, and NP's C++, every mechanism is named (split-horizon [dormant],
pipe-intersection, priority-subtraction, shared-`/23`-segment forwarding, the adapter's
out-stage collapse) but **it could not be reduced to a single clean root cause** — it is
a genuine tangle of the shared L2 segment × 3-stage HSA × subset-removal.

**Decision — pursue soundness by *convergence*, not proof.** Root-causing this one pair
has hit hard diminishing returns. The path to eliminating the over-approximation is to
make APKeep's forwarding **faithful to NP's** and iterate against NP as the oracle:
**(1)** a faithful out-stage (respect the L3 next-hop; stop the collapse fabricating
direct segment-neighbour edges), and **(2)** an adapter split-horizon for general
correctness. Work on (1) starts next.

## 10. Open questions / decisions log

- **RESOLVED (2026-09-18) — compliance conditions are dropped.** `check_compliance`
  received `RuleField` conditions and ignored them, so every state-conditioned check was
  answered by the unconditioned query: **1,651 phantom violations of 11,902** on wl_up
  (the check count at the time; 11,903 since the `Wifi` self-rule was restored, and
  11,911 since superrole self-expansion was fixed, both below)
  — exactly the `related:0` set, where FaVe+NetPlumber and ad6 both report 0. The two
  candidate fixes turned out not to be alternatives — `related` is HONOURED (forced onto
  the query at arrival, on both engines) and everything else is REFUSED (`_cond_related`,
  the same discipline as ad6's `_validated_conditions`). wl_up now reports 0 on the NDD
  engine and, confirmed separately at full scale, on the BDD engine — which matters
  because the two force the bit through different machinery. Full derivation in §9;
  pinned by `test/test_apkeep_compliance_cond.py`, which also asserts that dropping the
  conditions would still produce the 1,651 — otherwise a condition that bound to nothing
  would pass. FaVe+APKeep is usable on a stateful workload.
- **RESOLVED (2026-09-18) — `faithful_vlan` now has a production route, and is the
  DEFAULT.** `--no-vlan` turns it off; the APKeep engine default moved to NDD with it,
  because faithful-on-BDD completes on neither wl_stanford nor wl_i2.
- **RESOLVED (2026-09-18) — the wl_i2 11-pair over-approximation.** Root cause: the
  faithful VLAN admission gate was keyed by DEVICE (the union over its ingress ports)
  and spliced only onto source edges, so transit VLANs were never checked. Either
  defect alone accounts for the full 72-vs-61 gap; both are fixed and faithful APKeep
  now returns the 11 pairs set-identical to NetPlumber, ad6 and the structural oracle.
  Full derivation in §9. wl_stanford's faithful builder shared the port-blind keying
  (it gated the right edge, so nothing was observed there) and is now fixed the same
  way, with no verdict change and a structural gate — the reachability gate cannot see
  that defect, which is the whole point.
- **RESOLVED (2026-09-18) — the wl_i2 gates asserted the wrong oracle.** All three now
  assert against `bench/wl_i2/eval/i2_structural_oracle_atoms.json` (exhaustive over
  IPv4, agreed by NetPlumber and ad6) instead of `reachable.json`, the all-to-all policy
  mesh that scores any over-approximation at 100%. The faithful gate asserts equality
  (the 11 pairs, over and under) — a real assertion. The two PLAIN gates assert that the
  model reaches all 72, drops nothing the data plane delivers, and over-approximates by
  exactly those 11. Those are equivalent while it reaches everything, so this buys
  attribution rather than detection power, and both the test docstrings and §9 say so.
  Table in §9.
- **RESOLVED (2026-09-18) — the report rendered APKeep's conditions as object reprs.**
  `_render_cond` assumed the dict shape ad6 normalises to; `APKeepAdapter` echoes back
  the `RuleField` objects the aggregator built, so every conditioned violation printed
  `<rule.rule_model.RuleField object at 0x...>` on the line that states the verdict. It
  now accepts both shapes (§9, finding 2).
- **RESOLVED (2026-09-18) — wl_up's headline was under-reported by one, because a
  subnet role's self-rule was being dropped.** The frozen 3660 excluded
  `source.clients.wifi -> probe.clients.wifi`, on the grounds that a host reaching
  itself is not a compliance question. `Wifi` is not a host: `roles_and_services.txt`
  defines it as an IPv6 /64 with **no `hosts` list**, so its one model node stands for
  every client device in the subnet, and `reach.txt:17`'s `Wifi <--> Wifi` says those
  devices may reach each other — how wifi networks generally work, layer 2 being
  unrestricted. `reach_csv_to_checks.py`'s `[s for s in sources if s != target]` filter
  discarded it. That filter was never a considered convention: the generator has always
  emitted self-checks for wl_up -- **61** then, 69 now -- one per role whose diagonal is EMPTY
  (`! s=source.X && EF p=probe.X`), suppressing them only where the policy GRANTED
  self-reachability. The filter now keeps the self-pair where the role's single node
  denotes a proper subnet (not a bare address, not a `/0` placeholder), via each role's
  FPL attributes carried through `--roles`. wl_up: **11,903 checks, `reachable.json`
  3,371 pairs, headline 3,661, still 0 violations**; every other workload byte-identical.
  (11,911 checks today, after the superrole fix below; 3,371 pairs and 3,661 unchanged.)
  `Internet` stays excluded — it is external, outside the administrative reach of
  whoever writes the policy, so its self-reachability is not answerable.
  *(This entry had a wrong intermediate state the same day: the discrepancy was marked
  WITHDRAWN on the grounds that 3660 was a deliberate self-excluded convention and both
  numbers were right. Reading the tooling supported that; reading the POLICY refuted
  it.)*
- **RESOLVED (2026-09-18) — wl_i2's and wl_stanford's self-rules are correctly
  suppressed, but not for the reason the code tests for.** Both workloads set
  `All <--> All`, so every role carries a diagonal, and both give every role
  `ipv4 = '0.0.0.0/0'` — so `_abstracts_a_subnet` finds no cardinality and emits no
  self-check. The open question was whether that was right, or the same silent
  suppression wl_up had. It is right, and measurably so.

  **Measured:** every one of wl_i2's nine routers reaches its own probe **at hop 0** —
  tapped on the first FIB lookup, before traversing a single link — on a /24 or /23
  behind its own access port:

      atla  hop 0  (atla, port 120019, vlan 0, /24)
      chic  hop 0  (chic, port 220025, vlan 0, /24)
      ...   all nine identical in shape

  So `source.X -> probe.X` is one local LPM inside one router. It never exercises
  forwarding *between* devices, which is the entire subject of these benchmarks, and its
  destination lies in an adjacent network — a Stanford department or the Internet, a
  metropolitan network at I2 — that is attached but **not modelled**, so nothing about it
  could be decided anyway. The check would be **vacuous**: 9 of 9, uniform, unable to
  fail for any data plane that routes at all. (Owner's framing, 2026-09-18: these roles
  and policies are synthetic, following the NetPlumber paper's pairwise-reachability
  experiment, which did not include self-pairs. The paper is not re-checked here; every
  artifact in this tree is consistent with it.)

  **The contrast with wl_up is the discriminator**, and it is what makes restoring
  `Wifi <--> Wifi` and suppressing these two consistent rather than contradictory:

  | workload | roles reaching themselves | reading |
  |---|---|---|
  | wl_i2 | **9 of 9** | hop-0 local tap — structural, so vacuous |
  | wl_stanford | self-excluded by construction (240 = 16×15) | same |
  | wl_up | **1 of 137** | not structural; if it were, all 137 would |

  Uniform ⇒ structural ⇒ vacuous. Singular ⇒ carries information.

  Three artifacts written at different times already encoded this: `reachable.json` is
  72 = 9×8 and 240 = 16×15 with no self-pair in either, and `bench/i2_structural_oracle.py`
  — written independently to reproduce the paper's experiment — computes
  `len(sources) × (len(sources) - 1)` and labels its delivery sets "from some **other**
  source".

  **Recorded because the code gets the right answer for a weaker reason.** The `/0` test
  means "there is no addressing to reason about", not "this pair is vacuous". The real
  justification is hop-0 delivery against an absent adjacent network. Detecting *that* in
  the check generator would cost far more than it is worth, so the heuristic stays — but
  it is a heuristic, and the next person should not mistake it for the argument. Note
  also that hop-0 vacuity is a property of THIS modelling (probes tapped on every egress
  of the device the source attaches to), not of backbone benchmarks in general: attach
  probes differently and self-reachability could become informative again.
- **RESOLVED (2026-09-18) — superrole self-expansion asserted reachability nobody wrote,
  in strict mode.** `DMZ <--> DMZ` expanded onto each *member's own* diagonal, so wl_up's
  policy asserted `DMZFileServer` reaching itself, eight times over. Nothing named a
  member reaching itself.

  The item was first logged as provenance loss — a role×role CSV cannot say whether a
  diagonal was written or expanded, which is why the `Wifi` discriminator above had to
  work from role cardinality. **That was the symptom.** The defect is one stage earlier:
  FPL's `--strict` mode exists precisely to require an explicit rule for
  self-reachability, and superrole expansion walked straight through it. Minimal case,
  atomic `A`/`B` inside superrole `Grp`, one rule `Grp <--> Grp`:

  | mode | diagonals produced |
  |---|---|
  | `--strict` | `A→A`, `B→B` |
  | loose (default) | `A→A`, `B→B`, `Internet→Internet` |

  Strict granted `A` self-reachability from a rule that never names `A`, and the two
  modes differed on nothing but `Internet`. The mechanism also explains why it stayed
  invisible: loose mode's injector at `policy_builder.py` is guarded by
  `if not policy.policy_exists(role, role)`, so expansion having already filled the
  diagonal makes the injector skip exactly the roles it would otherwise be blamed for.
  The suite stated the contract (`test_policy_builder.py`: *"Uses strict mode so the
  implicit self-reachability policies are suppressed"*) but only ever exercised atomic
  roles, so the superrole path was untested in both directions.

  **Fixed where the distinction still exists.** `add_reachability_policy` has the
  *written* role names in scope while it expands, so an explicit diagonal and an expanded
  one are told apart locally — no provenance plumbing, no CSV format change:

  ```python
  literal_diagonal = (role_from == role_to
                      and self.roles[role_from].get_roles() == [role_from])
  ...
  if self.strict and role_from_ == role_to_ and not literal_diagonal:
      continue
  ```

  `Wifi <--> Wifi` survives (both endpoints name the same atomic role). `DMZ <--> DMZ`,
  `DMZAdminConsole <->> DMZ` and `All <->> DMZDNSServer` stop producing diagonals. Loose
  mode is untouched by construction, and `wl_ifi`/`wl_example` — the only other workloads
  with superroles — are byte-identical, verified by regeneration; `wl_i2`/`wl_stanford`
  have no superroles at all.

  **wl_up, measured:** non-empty diagonals 9 → **1** (`Wifi`), no off-diagonal cell
  touched, `roles.json` byte-identical, checks **11,903 → 11,911**, negative self-checks
  **61 → 69**, positive checks **3,371 unchanged**, `reachable.json` **3,371 pairs**,
  headline **3,661**, still **0 violations** — on NDD in the gated test, and confirmed
  at full scale on BDD (8 m 59 s, all 11,911 checks answered, `ap_num` 14 561 reproducing
  `APKEEP_BDD_BASELINE.md` §4.2 exactly). The eight diagonals do not vanish from
  compliance — emptied, they take the ordinary empty-diagonal branch and each yields a
  must-not-reach check, which is what strict mode plus default-deny implies and matches
  the 61 the generator already emitted.

  **What this changes about the `Wifi` discriminator.** It stays, but it is now a second
  line of defence rather than the thing standing between the check set and eight
  fabricated assertions: the hazard the item was logged for — a superrole member that is
  itself a subnet role, whose expanded diagonal would have become a *positive* check
  nobody wrote — is removed at the source rather than filtered downstream.

  *(This paragraph first claimed the discriminator "still does the work" for loose-mode
  callers, "where every diagonal is injected regardless". That was exactly backwards, and
  the next entry is the regression it caused: where every diagonal is injected, a
  discriminator reading the diagonal has nothing to read. Loose mode now emits no
  positive self-check at all.)*

  *(Found by the owner, who pointed out that `--strict` exists and turns implicit
  self-reachability off. The entry above it had reasoned about the pipeline from
  `reach_csv_to_checks.py` backwards and mis-scoped the fix as expensive on that basis.
  Checking what strict mode actually promises made it six lines.)*
- **RESOLVED (2026-09-18) — the `Wifi` self-check fix broke wl_ifi, and a green
  full-suite run hid it.** Restoring wl_up's `Wifi <--> Wifi` self-check taught
  `reach_csv_to_checks.py` to keep the self-check on a diagonal whose role abstracts a
  subnet. That rule is only sound for a matrix built in **strict** mode. In the
  translator's DEFAULT loose mode, `policy_builder.build_policies` injects an implicit
  self-reachability policy for *every* atomic role, so every diagonal is filled whether
  or not the policy asked for one — and a discriminator that reads the diagonal has
  nothing left to read.

  wl_ifi runs loose, and all sixteen of its roles are subnets. Regenerating it produced
  **16 positive self-checks asserting reachability nobody wrote**: 299 → 315 checks, 16
  self-pairs in `reachable.json`, and four red ad6 gates
  (`test_ad6_grounding`, `test_ad6_wl_ifi`, `test_ad6_wl_ifi_stateful`). Same shape as
  the superrole item above, reached through loose-mode injection instead of expansion.

  **Fixed the same way, one layer out.** The generator cannot tell an asserted diagonal
  from an injected one — that is the same provenance loss — so the caller states it:
  `--strict`, threaded from `generic_benchmark`'s own `self.strict` and from
  `gen_wl_up_inputs.sh`. Without it no positive self-check is emitted, which is what
  every loose workload had before. wl_up unchanged (11,911 checks, one self-pair);
  wl_ifi back to 299 and zero through both its generation paths.
  `test_reach_csv_self_checks.py` pins both directions on a synthetic matrix, so the
  rule is tested where it is decided rather than through a workload.

  **Why it took a second run to see.** `test.sh all` regenerates the gitignored
  benchmark artifacts in the integration and smoke tiers, *after* the fast tier that
  asserts on them has run. The `all` reported green here had therefore validated the
  previous run's artifacts; the very next `./test.sh fast` went red on the ones smoke had
  just written. `all` now ends with a second fast pass against what the earlier tiers
  actually produced — verified to catch this exact breakage (4 failed, exit 1, against
  reproduced 315/16 artifacts) rather than assumed to.

  **The general lesson, which the two entries above share.** Every rule in this pipeline
  that reads meaning out of a policy matrix is reading an artifact whose provenance was
  discarded upstream. A filled cell means "someone or something asserted this", and the
  "something" differs per translator mode. Neither `_abstracts_a_subnet` nor any
  successor can recover that; the mode has to be carried alongside the matrix. Both fixes
  do that — one inside the translator, one across its boundary.

- **DECIDED — doc name / framing.** `APKEEP_BACKEND.md`. Generalize to "pluggable
  backends" only if a third backend appears; two do not justify the rename.
- **CLOSED (2026-09-18) — non-reachability (`AG`) invariants are already the majority
  of the work.** The entry above this one used to read *"not in the target benchmarks;
  trivial complement if needed later"*. That was wrong, and had been for as long as the
  benchmarks have had compliance artifacts:

  | workload | checks | negated (`! s=source.X && EF p=probe.X`) |
  |---|---|---|
  | wl_up | 11,911 | **8,540 (72%)** |
  | wl_ifi | 315 | **245 (78%)** |
  | wl_i2 | 72 | 0 |
  | wl_stanford | 240 | 0 |

  A negated `EF` check *is* `AG ¬p`, and it is evaluated rather than skipped:
  `adapter.py` sets `must_reach = not negated` and records a violation when
  `reachable != must_reach`. Today's full BDD run answered all 11,911 wl_up checks —
  8,540 of them non-reachability — with 0 violations, so the negative half is exercised
  at scale on both engines. The stale claim is explicable: wl_i2 and wl_stanford, the
  two workloads §5 was written around, genuinely have none. Nothing to build.
- **NOT PURSUED (2026-09-18) — GraalVM native-image for APKeep.** It targets JVM startup
  and JIT warmup. Measured here: startup is **29–31 ms** over three launches, against a
  **539 s** wl_up run — 0.006%. The cost that matters is the AP partition: **94% of the
  build is PPM** (402.3 s of 425.9 s, `APKEEP_BDD_BASELINE.md` §4.2), an algorithmic BDD
  cost AOT compilation does not reduce — and native-image also gives up the JIT, which on
  a seven-minute pointer-chasing workload usually costs more than it saves. Reopen only
  if a short-lived-process use case appears; the benchmarks are the opposite of that.
- **DEFERRED — IPv6.** Unchanged and still the one piece of genuinely deferred work in
  this section. **Not a conceptual limitation** — the paper's header is `h` BDD bits and
  explicitly extensible (§9 reassessment) — but an implementation lift (P9): add the
  IPv6 fields and wire the scaffolded `ForwardingRule6` / IPv6 ACL path. Out of scope
  *as currently coded*, not as a technique. Note that wl_up's policy is IPv6-heavy at the
  FPL level (`Wifi` is a /64), which the model handles structurally; this item is about
  the BDD header, not about the benchmarks being IPv4-only.
- **OPEN — the `JDD` licence, and it is a larger question than this item used to say.**
  Logged as "verify once before publishing the fork" (§7). Verifying it turned up three
  findings, none of which resolves it:
  - neither `apkeep/local-maven-repo/.../JDD-111.jar` nor `ndd/lib/jdd-111.jar` contains
    a `LICENSE`, `COPYING` or `NOTICE` entry;
  - the vendored POM is an `install:install-file` stub — no `<licenses>` element, no
    upstream metadata;
  - `ndd/src/main/java/jdd/` is **decompiled bytecode** (`Decompiled with CFR 0.152` in
    every header), not upstream source. Redistributing a decompiled reconstruction is a
    different and larger question than redistributing the jar, and the item as written
    did not contemplate it.

  This is not closable by reading the tree: it needs upstream's actual terms
  (bitbucket.org/vahidi/JDD) and the owner's decision. Recorded rather than guessed —
  asserting a licence here on recollection is precisely the failure mode to avoid before
  publishing.

## 11. Build & toolchain notes (P0 — done)

APKeep needs **JDK 11 + Maven** (its documented toolchain). Build with
`cd apkeep && mvn package` → `target/apkeep-1.0.0.jar` (fat jar). The
`fave/test/apkeep_smoke.sh` harness (integration tier) builds it, runs the
bundled Stanford snapshot through the CLI, and pins the forwarding-loop set.

Upstream's build was **not reproducible** and required fork-local fixes (all in
`apkeep/`, kept as one subtree-isolated commit):

- **JDD could not be resolved at all.** `org.bitbucket.vahidi:JDD:108` is a tag
  that was never published (JDD's tags start at 109), JDD is not on Maven
  Central, and JitPack serves only JDD's `.pom`, never a `.jar` (JDD is a
  Gradle/Ant project producing no JitPack-resolvable artifact). Fix: vendor a
  JDD jar built from the author's Bitbucket source at tag **111** (zlib/
  public-domain) into an in-tree file repository, `apkeep/local-maven-repo/`,
  referenced from `pom.xml`. The build is now hermetic (no network/JitPack).
- **Java version.** Maven's super-POM binds `maven-compiler-plugin` 3.1, which
  predates the `release` option and defaults to Java 1.5 (rejected by JDK 11).
  Fix: pin `maven-compiler-plugin` 3.11.0 with `release=11`.

JDK 11 + Maven are added to the CI composite action and the `Dockerfile`.

**The jars are build products, and a stale one fails LATE (2026-09-21).** Both
`apkeep/target/apkeep-1.0.0.jar` and `ndd/target/ndd-1.0.1-jar-with-dependencies.jar`
are gitignored, so an environment with a JRE but no JDK keeps whatever was built
last and cannot rebuild it. That is not a quiet degradation: a Python caller
whose Java counterpart has moved on gets `TypeError: No matching overloads
found`, which surfaces mid-run inside a compliance check rather than at import.
Encountered exactly that on wl_cloud — the NDD jar predated `isReachable(...,
related)`, so the DEFAULT engine could not answer a conditioned check at all.
`bash fave/test/apkeep_smoke.sh` and `bash fave/test/ndd_build.sh` rebuild them
and guard the toolchain up front; run both after any change under `apkeep/src`
or `ndd/src`, and treat an overload error from either engine as a stale jar
until proven otherwise.

### libnetplumber build integration (P1)

The binding (`net_plumber/python/libnetplumber.cpp`) needs `pybind11` + Python
headers (`pybind11-dev`, plus `python3-dev` for the system interpreter); these
are added to the CI composite, the `Dockerfile`, and `net_plumber/setup-ubuntu.sh`.

Because the binding links NetPlumber's core objects into a shared module, those
objects must be **position-independent**. NetPlumber is therefore built with
`make DEBUG_FLAGS=-fPIC all` (the same `DEBUG_FLAGS` hook the sanitizer build
uses; PIC executables behave identically, so the C++ tests are unaffected), and
`net_plumber/python/build_libnetplumber.sh` is then run with
`LIBNP_ASSUME_PIC=1` to link against those objects without a second rebuild.
The CI composite (`setup-fave-native`) and the `Dockerfile` do both steps, so
every integration/e2e/bench job and the image have the `.so`.

The built module is imported off `sys.path` — `netplumber/lib_adapter.py` adds
`net_plumber/python/` to `sys.path` and `import`s `libnetplumber`, failing only
when a `NetPlumberLibAdapter` is actually constructed (so importing the module,
e.g. during test collection, is safe when the `.so` is absent). The equivalence
test (`fave/test/test_lib_equivalence.py`, e2e tier) `skipIf`s when it is unbuilt.

## 12. References

1. P. Zhang et al., "APKeep: Realtime Verification for Real Networks," NSDI 2020.
   <https://www.usenix.org/system/files/nsdi20-paper-zhang-peng.pdf>
2. Z. Li et al., "NDD: A Decision Diagram for Network Verification," NSDI 2025.
   <https://www.usenix.org/system/files/nsdi25-li-zechun.pdf>
3. APKeep artifact: <https://github.com/XJTU-NetVerify/apkeep>
4. NDD library: <https://github.com/XJTU-NetVerify/NDD>
