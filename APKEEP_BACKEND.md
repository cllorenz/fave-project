# APKeep as an Alternative FaVe Verification Backend — Design & Plan

**Status:** PLAN (scoping complete; no integration code yet).
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
    ~24x faster** -- APKeep verified exactly (reachability == reachable.json).
    The crossover is decisive at scale: header-space flow propagation is the
    bottleneck (NetPlumber's 341 s is almost entirely model build), atomic
    predicates are not. This is the result the comparison was built to show.
  - **wl_stanford:** the *forwarding* is now modelled (P7a: the `in_port` out-stage
    collapse), and it matches the bundled `reachable.json`. But `reachable.json` is
    the **artificial all-to-all policy** (from the HSA/NetPlumber papers), not the
    data plane -- so that match only proves forwarding *completeness*. The faithful
    data plane needs the VLAN-coupled ACLs, which require a VLAN **rewrite** (P7b =
    P8); see the P7 subsection for the NetPlumber cross-check that quantifies this.

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

- **Doc name / framing:** `APKEEP_BACKEND.md` (chosen). Could later generalize to
  "pluggable backends" if a third backend appears.
- **IPv6:** postponed, but **not a conceptual limitation** — the paper's header is
  `h` BDD bits and explicitly extensible (§9 reassessment). It's an
  implementation lift (P9): add the IPv6 fields + wire the scaffolded
  `ForwardingRule6` / IPv6 ACL path. Out of scope *as currently coded*, not as a
  technique.
- **Non-reachability (`AG`) invariants:** not in the target benchmarks; trivial
  complement if needed later (§5).
- **GraalVM native-image for APKeep:** optional future polish, not the baseline
  (§6).
- **`JDD` license:** verify once before publishing the fork (§7).

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
