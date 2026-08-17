# Plan: APKeep on wl_tum and wl_up (stateful firewalls + IPv6)

**Goal.** Bring the two remaining FaVe benchmarks — `wl_tum` (TUM-i8, a large
stateful IPv4 firewall) and `wl_up` (University-Potsdam, an IPv6 campus network) —
onto the APKeep backend, faithful to NetPlumber, extending the head-to-head
comparison beyond the already-done `wl_ifi` / `wl_i2` / `wl_stanford`.

**Status:** wl_tum DONE; wl_up correctness DONE (exact NP-parity on a slice,
2026-08-14). Performance is the only open item (Phase 7). **Phase 0+A DONE
2026-08-14 and they overturned the diagnosis: the wall is BUILD / AP-construction
(superlinear; full model >25 min), NOT per-query traversal (flat ~1 ms). The
lead fix pivoted from B2 to build-cost reduction, now planned as Phase C
(profile-first C0 → model/predicate/core levers; core surgery approved).**
Owner: Claas Lorenz. Driver:
PhD-thesis future work. Companion to [`APKEEP_BACKEND.md`](APKEEP_BACKEND.md)
(roadmap P8/P9) and [`APKEEP_FAITHFUL_PLAN.md`](APKEEP_FAITHFUL_PLAN.md) (the
guardrail discipline this plan reuses).

**Scope decisions (2026-08-13, with user):**
1. **wl_tum first**, wl_up second — wl_tum isolates the stateful-firewall path
   (IPv4, single device, no topology/IPv6 confounder); wl_up then stacks IPv6 on a
   proven state path.
2. **The stateful reverse-flow track is IN scope** — reproduce wl_ifi's currently
   *skipped* `related:` cchecks (the true state-*rewrite*), not only forward
   reachability.

---

## What the two benchmarks actually require (audited)

| | **wl_tum** | **wl_up** |
|---|---|---|
| IP version | **IPv4** (default; `-6` optional) | **IPv6-only** (`ip6tables`) |
| Topology | 1 `packet_filter` (`fw.tum`), no links | 1 border FW + 135 host-FWs + 23 switches |
| Rules | **3,794** (one big stateful ruleset) | ~3,254 static + a generated 1,028-rule border FW |
| State | heavy: 3,190 `--state NEW` + `ESTABLISHED` | `ESTABLISHED` only |
| Rewrite | port-metadata (`in/out_port`) + VLAN **match** (`svlan`/`dvlan`, 21 sub-ifaces) | port-metadata only; **no NAT/VLAN** |
| Oracle | **empty `{}`** → pure build/scale benchmark | populated `reachable.json`, but **stateless** (`# TODO: allow stateful`) |

**Key reframing.** The roadmap filed both under "P8 — state-shell *rewrites*",
which risked re-triggering the wl_stanford AP-explosion. The profiles show the
explosion risk is **absent**: FaVe's Python interweaving compiles conntrack state
into a **`related` *match* field** (a match does not fragment APs — wl_i2 holds 77k
match rules at ~216 APs; the wl_stanford blow-up was specific to *per-route
rewrites*, which neither benchmark has). The genuine state-**rewrite** (a `NEW`
forward spawning an `ESTABLISHED` return) is needed only for the **reverse-flow
`related:` checks** — the skipped wl_ifi cchecks — which neither shipped oracle
exercises, and which we opted into as a separate track (Phase 5).

**The remaining core lift for wl_up is IPv6.** APKeep's `BDDACLWrapper` already
declares a 128-bit **`dstIP6`** but **no source-IPv6 field** — the ACL/forwarding
paths use 32-bit `srcIP`/`dstIP` (`apkeep/src/main/java/common/BDDACLWrapper.java`
`ipBits=32` `srcIP`/`dstIP`; `ip6Bits=128` `dstIP6` only). So IPv6 is *scaffolded
but incomplete*: adding a 128-bit `srcIP6` (+ the IPv6 ACL/forwarding path) is the
bounded P9b work, mirroring the proven P9a VLAN-field addition (declare vars last +
layout-lock + wire into `ConvertACLRule`).

---

## Phase 0 — diagnostic probe (DONE 2026-08-13, no core change)

Drove the real wl_tum model through **both** backends in-process (the
`InProcessFaVe` path used by `test_apkeep_stanford`; APKeep and NP in **separate
processes** — the resident JVM cross-contaminates NP):

| backend | build | `source.tum → probe.tum` |
|---|---|---|
| **APKeep** (current adapter) | **1.77 s** | **unreachable** ✗ |
| **NetPlumber** (reference) | 6.58 s | reachable ✓ |

**Findings.**
1. **No hard capability wall.** The current `APKeepAdapter` ingests all 3,794
   stateful rules with no crash, and builds ~3.7× faster than NetPlumber — the
   wl_i2-style "APKeep wins at scale" story is plausible **once correct**.
2. **It under-approximates** (the unsound direction — drops a path NP delivers).
   Root cause localized: the adapter is entirely **stanford/VLAN-shaped**
   (`apkeep/adapter.py`: `_VLAN='packet.ether.vlan'`, `_mid_rw`, `faithful_vlan`,
   …) and has **no model for** the conntrack **`related` state field** (the
   interwoven accept path matches it → the adapter drops it → the flow dies), the
   packet-filter **`svlan`/`dvlan`** match fields, or its **`in_port`/`out_port`
   rewrite**.

This confirms the reframing: the gap is **P8 state-shell + packet-filter
modeling**, not AP-explosion.

### Phase 2 pre-surgery finding (2026-08-13) — the root cause is packet-filter forwarding, not the state field

Instrumenting `APKeepAdapter.add_rules` on the wl_tum run (ground truth) shows the
adapter receives, for `fw.tum`:

| table | rules | adapter action |
|---|---|---|
| `fw.tum.pre_routing` | 4 | captured (VLAN) |
| `fw.tum.forward_filter` | **5108** | **IGNORED** |
| `fw.tum.post_routing` | 4 | ignored |
| `fw.tum.routing` | **0** | (the only fwd table it reads — empty) |
| input_filter/output_filter/internals | 0 | — |

`add_rules` only acts on `<node>.routing`/`.1` (FIB), `.acl_in`/`.acl_out`, and
`.pre_routing` — the **router/switch** table shapes. A **`packet_filter`**'s
filtering lives in `forward_filter` (accept→`out_port` / drop), which matches none
of those, so all 5108 rules are dropped and no forwarding path forms →
under-approx. The match fields inside those ignored rules (counts): `out_port`
4510, `packet.ether.dvlan` 4506, `related` 4504, `ipv4.destination` 4405,
`ipv6.proto` 4002, `ipv4.source` 3830, `upper.dport` 3076, `in_port` 608,
`ether.svlan` 606, `upper.sport` 9.

**So the real Phase 2 is "model the `packet_filter` device"** (the multi-field,
first-match `forward_filter` that forwards accepted packets to `out_port` and drops
the rest), using the 5-tuple APKeep already supports; the `related` state field and
`svlan`/`dvlan` are fidelity refinements layered on top (Phase 3), not the primary
gap. This re-scopes tasks #3/#4 (recorded there).

---

## Phased plan (tracked as tasks #1–#7)

- **Phase 0 — diagnostic probe. DONE** (above). Task #1.
- **Phase 1 — wl_tum APKeep-vs-NP differential + gated test. DONE (2026-08-13).**
  wl_tum ships an empty oracle, so NP is the reference.
  - `fave/bench/apkeep_tum_diff.py` — the differential harness (sibling of
    `apkeep_convergence.py`; subprocess-per-backend). Compares by **full node
    name** with no same-base self-reach exclusion — wl_tum's only pair
    `source.tum → probe.tum` shares the base `tum`, which the stanford harness's
    base-keyed exclusion would wrongly drop. Current metric: `over_approx=0
    under_approx=1 UNSOUND` (exit 1) — the honest starting point.
  - `fave/test/test_apkeep_tum.py` — gated integration test (`require_or_skip` +
    `FAVE_REQUIRE_BACKENDS`). A **characterize→fix→flip** ratchet: it pins the
    single known under-approximation (`source.tum → probe.tum`) so the gap is
    green/gated/visible, and it auto-trips the instant Phases 2-3 change the
    behaviour — the cue to FLIP it to `assertEqual(apkeep, netplumber)` and gate
    convergence (Phase 4). Added to `FAVE_INTEGRATION_TESTS`.
  - `fave/test/gen_wl_tum_inputs.sh` — regenerates the gitignored wl_tum model
    JSON (`bench/wl_tum/*.json`) from tracked sources (routegen/policygen/topogen,
    IPv4 + tum-ruleset), no live backend; reproduces the committed files
    byte-for-byte. Wired into `run_integration` before the pytest step (mirrors
    the wl_stanford gen). This closes the "required test hard-fails on a clean
    checkout because inputs are gitignored" hole.
- **Phase 2 — model the packet_filter forward_filter forwarding via `FilterElement`.
  DONE (2026-08-13).** Java core `FilterElement` (commit `9e6f3ae8`, 27 Java tests)
  + adapter/lib wiring: `add_rules` translates each `forward_filter` rule to a
  `+ filter` string (ACCEPT → the `forward_filter_accept` out_port, DROP → the
  `__drop__` sink), `_build` registers `fw.tum` as a `device_filters` FilterElement
  (not a dst-FIB ForwardElement). **Distinct-value measurement decided the field
  set:** `out_port`/`in_port`/`sport` are *constant* (1 value → non-discriminating,
  safely ignored); the discriminating fields are the 5-tuple (proto/src/dst/dport)
  plus `related`(2) and `svlan`/`dvlan`(21 each). The **5-tuple-only** translation
  already **converges** the wl_tum pair (`related`/VLAN drops are not load-bearing
  for this existential query), so they move to the wl_up/reverse-flow track.
- **Phase 3 — packet_filter field fidelity (deferred to the wl_up track):** the
  `related` state field (new BDD var, P9a-style), `svlan`/`dvlan` (adapter knows
  only `packet.ether.vlan`). NOT needed for wl_tum (converged without them);
  required for wl_up's richer/stateless-oracle queries and Phase 5. Task #4.

  **Phase 2 design (core map complete 2026-08-13).** No existing APKeep element
  both matches a multi-field header AND forwards to a chosen port: `ForwardElement`
  = dst-LPM→port; `ACLElement` = 5-tuple+vlan→permit/deny (gate only, `deny` is a
  traversal dead-end); `NATElement` = rewrite on a fixed inport→outport wire. So
  general packet-filter forwarding is a **new `Element` subclass `FilterElement`**
  composing ACLElement's first-match multi-field match (reuse
  `BDDACLWrapper.ConvertACLRule` — proto/src/dst/sport/dport/vlan already
  supported) with ForwardElement's placement of each rule's disjoint hit-predicate
  on a real named `out_port` (`port_aps_raw` + `forwardAPs`); the action is a
  concrete out_port (ACCEPT) or a drop sink (DROP, like ACL `deny`). Contract:
  `initialize`/`encodeOneRule`/`insertOneRule`/`removeOneRule`/
  `tryMergeIfNATElement` (delta unchanged); reuse base `identifyChangesInsert`
  (LinkedList first-match overload) + `updatePortPredicateMap`. Register a `filter`
  type in `Network.updateRule` dispatch + `elements`/`setAPC`. Field gaps
  (`related` BDD var, `in_port` positional) → Phase 3. Separate apkeep-subtree
  commit + FAVE_CHANGES.md (MIT vendoring).
- **Phase 4 — wl_tum convergence + scale result. DONE (2026-08-13).** The
  differential converges: **APKeep == NP, `over_approx=0 under_approx=0 SOUND`**.
  The Phase-1 characterization test tripped as designed and was flipped to the
  convergence gate `test_apkeep_tum::test_reachability_matches_netplumber`
  (`assertEqual(apkeep, netplumber)`); added to the exactness gate. The exactness
  gate stays green on wl_ifi/i2/stanford (10 passed) — no regression. **Scale
  result:** from-zero build **APKeep 2.2 s vs NetPlumber 6.5 s (~3× faster)** on
  the 3.8k-rule stateful firewall — the wl_i2 headline repeated for a firewall.
  Task #5.
- **Phase 5 — stateful reverse-flow `related:` rewrites.** The one piece needing
  the true state-*rewrite*: wire the state field's rewrites through the adapter +
  `ReachabilityChecker` and reproduce wl_ifi's skipped `related:` cchecks.
  Independent of the tum/up forward-reachability oracles. Task #6.
- **Phase 6 — wl_up IPv6 (P9b). IN PROGRESS (2026-08-14).** Task #7.
  - **Core DONE (commit `c53deab7`, apkeep subtree).** Added a 128-bit `srcIP6`
    field + **fixed** `dstIP6` (it was mis-declared with only 32 of 128 vars);
    both declared last (layout-lock behaviourally preserved). `encodeIP6Prefix`
    encodes an IPv6 `addr/len` prefix over `srcIP6`/`dstIP6` (mirrors
    `ConvertIPAddress`'s mask path); `ConvertACLRule` routes a `':'`-bearing
    address token to the IPv6 path — feeds both `ACLElement` and `FilterElement`.
    JUnit: IPv6 prefix containment/disjointness + src6/dst6 independence. 27→29
    Java tests green, no regression.
  - **Adapter IPv6 emit DONE (validated).** `_addr_tokens` emits IPv6 as
    `addr/len` (wildcard `null`); `_translate_filter_rule` reads
    `packet.ipv6.source`/`destination`. Re-probe confirms filter rules now carry
    the real IPv6 prefixes (`2001:db8:abc::/48`) instead of all-wildcard. wl_up
    builds through APKeep in ~2.2 s.
  - **Build-bug FIX DONE (commit `6141e6f8`).** wl_up's build threw
    `ArrayIndexOutOfBounds` in `ACLRule.<init>`: all 136 filter devices' internal
    routing tables emit a default `+ fwd <dev> 0 0 routing_out 0`, and a `+ fwd`
    rule dispatches by device name → it landed on that device's FilterElement and
    failed to parse as an ACL rule. (This is why the compliance jobs *hung* — the
    build threw in the handler thread and the main thread blocked on
    `queue.join()`; it was NOT slow computation.) Fix: `_build` drops dst-FIB rules
    for filter devices (their forwarding IS the FilterElement). wl_up now builds in
    **~0.4 s**; per-query reachability ~82 ms. Exactness gate green (11 passed).
  - **OPEN — wl_up still UNDER-approximates its oracle.** On a sampled probe,
    APKeep drops `clients.api → adm` that `reachable.json` reaches (the
    not-reachable cases are correct). So a gap remains *beyond* IPv6 matching. Ruled
    out: switch/router forwarding is default-flood (`0 0 → port`, not IPv6-dst), so
    not the 32-bit-ForwardElement issue. Candidates to trace: the FilterElement
    accept path (the ignored `related`/`out_port`/`dvlan` fields shifting first-match;
    or IPv6 src-seeding — `_gen_src` captures only IPv4 `packet.ipv4.source`, not
    `packet.ipv6.source`), or the switch-flood model. **Needs per-hop path tracing
    (next step).**
  - **Scale note:** full all-pairs is 137×137 = 18,769 queries (~82 ms each ⇒
    ~25 min) because `check_compliance` does per-pair `is_reachable`. Tractable but
    slow at this scale; a per-source batched reachability (137 floods, not 18,769
    pair-queries) would fix it — a separate perf item, not a correctness blocker.

### wl_up Phase-0 diagnostic (2026-08-14) — the gap is IPv6; the FilterElement foundation holds

Ran the real wl_up model through the current adapter (+ FilterElement) and NP.

- **FilterElement generalises.** APKeep builds the whole IPv6 campus model —
  **136 packet-filter/host devices** (border FW + 135 host firewalls) + 23
  switches, 137 sources/137 probes — in **2.4 s**, no crash. The packet-filter
  machinery from wl_tum works structurally for wl_up.
- **Blocker = IPv6 addressing.** forward_filter rules match on
  `packet.ipv6.source`/`packet.ipv6.destination` (128-bit, 1646 each), but the
  adapter's filter translation reads only `packet.ipv4.*` → finds nothing →
  **emits every rule all-wildcard on IP** (`... 0.0.0.0 255.255.255.255 ...` for
  both src and dst). The address constraints are dropped, so the model is
  currently meaningless for wl_up.
- **Core root cause (as predicted P9b).** `BDDACLWrapper.ConvertACLRule` ANDs only
  `{proto, srcPort, dstPort, srcIP(32), dstIP(32), vlan}` — **no `srcIP6`, and the
  existing 128-bit `dstIP6` is not wired into this ACL/filter path.**
- Minor extras surfaced: `related` (state, 1021) and a few IPv6 extension-header
  matches (`module.ipv6header.rt.type`/`segsleft`, ~10 rules).
- Reachability divergence vs NP: *(quantifying; the IPv6-blind model is expected
  to be badly wrong until srcIP6/dstIP6 are wired in).*

**P9b work items:** (1) APKeep core — declare a 128-bit `srcIP6` last (layout-lock,
P9a-style) + AND `srcIP6`/`dstIP6` into `ConvertACLRule` + IPv6 tokenization in
`ACLRule`; (2) adapter — extract `packet.ipv6.source`/`destination` and emit an
IPv6-aware filter/ACL rule form; (3) decide `related`/IPv6-ext-header handling.
Separate apkeep-subtree commit + FAVE_CHANGES.md (MIT vendoring).

---

## wl_up correctness: DONE — exact NP-parity on a slice (2026-08-14)

The IPv6/forwarding/state fidelity work is complete and validated. APKeep ==
NetPlumber on **all 112 reachable pairs, 0 differing**, on **two independent
slices** (cs and jura departments — not overfit). Commits `8e73a06d` (full
packet_filter pipeline + IPv6 router FIBs), `2a15a07a` (`related` state field),
`11db2f9e` (in/out_port anti-spoof via per-port pre/post filters), `241381af`
(residual diffs: Forward-action-gated FIB, per-source src-constraint, in/out_port
generalised to all chains). The `related`-state hypothesis was falsified along the
way — the real fidelity gaps were structural (routing/FIB, source-seeding, port
qualification), not state. Exactness gate green throughout.

**The one thing left is performance — a separable, algorithmic problem.**

## Phase 7 — wl_up performance: per-source reachability fixpoint (PLAN, 2026-08-14)

**Symptom.** The full 136-device wl_up model is correct but intractable at scale:
~40 s/query, full 137×137 never finishes. Build is fast (~2.4 s); the cost is
entirely per-query.

**Diagnosis (from tracing the query path, not speculation).** Three compounding
facts:
1. `check_compliance` (`adapter.py:1187`) issues **one independent reachability
   query per `(source, probe)` pair** — ~137×137 ≈ 18.8k queries.
2. Each query builds a **fresh** `ReachabilityChecker` (`lib_apkeep.py:200`) and
   runs a **depth-first search over simple paths** (`ReachabilityChecker.java:131`).
   It early-exits on the *one* target, but an **unreachable** pair must exhaust the
   entire reachable sub-graph — and wl_up's policy oracle is sparse, so most of the
   18.8k queries hit that worst case.
3. The DFS re-walks per pair with per-path allocation (`new ArrayList<>(history)`
   at every branch, linear `history.contains`, AP sets recomputed each hop) and
   **memoizes nothing** across the 137 targets that share a source.

So the wall is **O(pairs × simple-paths-per-source)** path enumeration over a graph
the faithful model *inflated* (each packet_filter → many FilterElements: in/fwd/out
chains + routing FIB + per-port pre/post filters + per-source src-filters). Global
atomic-predicate count is a *second-order* multiplier, **not** the primary wall as
the earlier note assumed.

**Load-bearing correctness fact (verified read-only).** wl_up runs in a **single AP
universe**: `_acl_device` is set only for router devices with `acl_in`/`acl_out`
(wl_ifi/i2/stanford); wl_up's packet_filters are **all `FilterElement`/
`ForwardElement` — zero `ACLElement`, zero `NATElement`**. In the DFS, `acl_aps`
stays `{BDDTrue}` at every hop and ACL "division" never fires (despite
`USE_DIVISION=true`). Therefore the reachable-packet set at a port is a **single**
AP-index set and the join at path merges is **exact union** — no cross-universe
over-approximation. This makes the fixpoint below *provably identical* to the DFS's
existential answer for wl_up, not merely an approximation.

**Chosen approach: B2 — per-source forward-propagation fixpoint** (user decision
2026-08-14; B1 "batch the DFS" and "A-only-then-decide" considered and rejected in
favour of the principled fix).

Phases:

- **Phase 0 — guard the precondition.** Assert at build that the wl_up model emits
  no `ACLElement`/`NATElement` (single universe). Encode as a runtime guard, not an
  assumption — it is what makes the fixpoint exact.
- **Phase A — instrument, get the curve.** Counters on the tractable slice + one
  medium slice (subnets 1→4): per-query traverse node-visits & paths, global AP
  count (`getAPNum`), built element/port count. Confirms the dominant term and sets
  a baseline to beat. No behaviour change.
- **Phase B — the fix.** New Java `ReachabilitySet`:
  - *State:* `reach(port)` = AP-index set of packets that can arrive at that port
    from the source seed.
  - *Seed:* `reach(source_egress) = seed` (full space for wl_up — the src-filter
    FilterElement already narrows source).
  - *Transfer:* worklist over ports; for element `e`, input `i`, output `o`:
    `reach(o) ∪= forwardAPs(o, reach(i))`; across an L1 link
    `reach(dst_ingress) ∪= reach(src_egress)`. Monotone over the finite AP lattice
    → **terminates even with forwarding loops** (strictly better than simple-path
    pruning).
  - *Answer:* probe `p` reachable iff `reach(p_port)` non-empty (∩ target-header
    when set). Every probe for a source is read off the same converged map — **one
    propagation per source, not per pair.**
  - *Rollout guard:* fixpoint only when division is inactive (single universe) —
    covers wl_up now, and (since rewrite distributes over union) extends cleanly to
    NAT-only cases like stanford later. **Division-active workloads (wl_ifi/i2) stay
    on the proven DFS** — no gated result changes.
  - *Adapter:* `check_compliance` inverts the rule map to group probes by source,
    issues one `reachable_set(source, seed)` per source, answers all its probes from
    the returned map.
  - *Complexity:* 137² path-exponential DFS runs → **137 monotone propagations**,
    each polynomial in (ports × AP-set size). Collapses both multipliers.
- **Phase C — graph-size reduction (only if Phase A shows node count is a real
  multiplier).** IPv4 FIB via `ForwardElement` trie instead of per-device
  `FilterElement`; merge per-port pre/post-filters; dedup identical FilterElements.
  Secondary to B.
- **Phase D — validate + gate.** (1) **Differential oracle:** on both slices,
  assert the fixpoint's answer equals the DFS's for *every* pair (tests the
  single-universe exactness claim). (2) Full 136-device wl_up: confirm APKeep == NP
  parity and measure from-zero time. (3) Wire into the exactness gate; re-run
  wl_ifi/i2/stanford/tum to prove no regression (they stay on the DFS path anyway).

**Open risk (fails safe).** The exactness proof rests on single-universe. If Phase 0
ever finds an `ACLElement` in wl_up (it should not, per the code), componentwise
union across two universes over-approximates and B2 would need division-aware
handling before being trusted — but the guard routes such cases to the DFS, so it
fails safe.

### Phase 0 + A RESULTS — the diagnosis was WRONG; the wall is BUILD, not per-query (2026-08-14)

Instrumented the DFS (`ReachabilityChecker.nodesVisited`/`branchesExplored`, reset
per query) and the built graph (`Network.numElements/numPorts/numElementsOfType`),
then swept slice sizes in fresh processes. **Phase 0 confirmed:** every config
reports **0 ACLElement / 0 NATElement** (`single_universe=True`) — the fixpoint's
exactness precondition holds. **Phase A refuted the performance hypothesis:**

| cfg | src×prb | elements | ports | ap_num | actual build¹ | per-query | nodes/query |
|-----|---------|----------|-------|--------|---------------|-----------|-------------|
| 1x1 | 13×13 | 80 | 148 | 967 | ~0 s | ~1 ms | 35–69 |
| 1x2 | 14×14 | 86 | 159 | 1112 | ~12 s | ~1 ms | 35–72 |
| 2x2 | 17×17 | 105 | 195 | 1660 | ~23 s | ~1 ms | 35–84 |
| 4x3 | 27×27 | 167 | 311 | 4258 | ~124 s | ~1 ms | 75–120 |
| full | 137×137 | ~800+ | — | — | **>25 min, capped²** | (unmeasured) | — |

¹ build wall minus the ~28 s cold-JVM floor each process pays.
² AP construction had not finished after 25 min; killed. Never reached a query.

**What the numbers say:**
- **Per-query DFS is NOT the wall.** Time is flat ~1 ms (reachable *and*
  unreachable), and `nodesVisited` grows only **linearly** (~0.7 × elements). No
  simple-path explosion — packet_filter pipelines are short chains and the filters
  *drop* most traffic, so each source's reachable set stays small and the DFS
  exhausts it cheaply. The earlier "~40 s/query" was a mis-attribution of build cost.
- **BUILD / AP-construction is the wall — and it is superlinear.** actual build
  0 → 12 → 23 → **124 s** as elements go 80 → 167; `ap_num` climbs 967 → 4258; and
  the full model (~136 devices, ~800+ elements, plus the pgf border firewall's
  ~2000 rules) did **not** finish AP construction in **>25 min**.

**Consequence for the plan (course-correction):** the chosen fix **B2 (per-source
reachability fixpoint) targets the wrong bottleneck** — it optimises per-query
cost, which is already ~1 ms. **It is deprioritised.** The real lever is
**reducing build / AP-construction cost**, i.e. what was Phase C plus APKeep-core
AP-merge/build efficiency:
- **Model-size reduction (was Phase C, now primary):** collapse the per-device
  FilterElement inflation (in/fwd/out chains + routing FIB + per-port pre/post
  filters + per-source src-filters → ~6 elements/device). Use the `ForwardElement`
  trie for IPv4/IPv6 dst-LPM FIBs instead of a FilterElement FIB per device; merge
  per-port pre/post filters; dedup structurally-identical FilterElements. Fewer
  multi-field predicates ⇒ smaller AP partition ⇒ cheaper build.
- **AP-construction efficiency (APKeep core):** profile where the >25 min goes
  (per-rule `ConvertACLRule` BDD ops vs `hardMergeAPBatch` AP merging vs
  `updatePortPredicateMap`); the superlinearity likely lives in AP merging over a
  large multi-field partition.
- **Re-scope Phase A tail:** get one *completed* full build time (run to
  completion once, unattended) to anchor the target, and profile it.

**B2 is not discarded** — it remains a correct, exactness-preserving improvement
and the natural home for all-destinations-per-source batching *if* build is ever
made tractable and per-query then dominates the 137² pair loop. But it is no longer
the lead fix; the build-cost attack below (Phase C) replaces it as the lead.

### Phase C — reduce build / AP-construction cost (PLAN, 2026-08-17)

The lead fix now that Phase A proved build/AP-construction (not per-query) is the
wall. The from-zero build time *is* the benchmark metric (user-perceived), so this
is the axis that counts.

**Model shape being optimised.** Each packet_filter → ~6 elements (input/forward/
output chains + dst-LPM FIB + per-port pre/post filters) + 137 per-source
src-filters ⇒ full ≈ 850 elements. The 135 host firewalls are **6 role-templates
(clients/file/mail/print/voip/web) × 21 subnets, structurally identical modulo the
subnet's IPv6 prefix** (verified: cs-web vs jura-web diff to zero after
address-normalisation, 20 lines each). But the *predicates* still differ by subnet
prefix — which is exactly the ambiguity the profile must resolve.

**The one question C0 must answer** — the superlinear cost is one of three things,
and the fix differs completely for each, so profile before cutting:

| case | where the time goes | fixable by | difficulty |
|------|---------------------|------------|------------|
| (a) | global **AP partition** — distinct multi-field IPv6 predicates merged pairwise per subnet added | narrow/aggregate predicates, or core merge algorithm | hardest (may be architectural: APKeep is built for *incremental*, not from-zero) |
| (b) | redundant **element / PPM bookkeeping** — 850 elements each keeping a port-predicate map | model-size reduction (adapter-only) | cheapest, biggest structural win |
| (c) | per-rule **BDD encoding** — 128-bit src6+dst6 ANDed per rule in `ConvertACLRule` | field projection (skip unconstrained dims) | medium |

Template-repetition cuts toward (b) *if* the per-subnet cost is element/PPM
overhead — but if it is the distinct address predicates, it is (a) and dedup will
not help. Only the profile decides.

**Phases:**
- **C0 — profile one completed full build (measure before surgery; gates C1).**
  Additive Java timers around the three suspects — `BDDACLWrapper.ConvertACLRule`
  (encode), `APKeeper.hardMergeAPBatch`/`tryMergeAP` (merge),
  `Element.updatePortPredicateMap` (PPM) — plus an `ap_num`-vs-rules-applied
  trajectory. Run the full model to completion **once, unattended**. Deliverable:
  attribution table + `ap_num(full)` + which term is superlinear.
- **C1 — attack the dominant term** (branch on C0), each correctness-neutral:
  - **L1 model-size reduction (adapter, case (b)):** fold per-port pre/post filters
    into their chain; fold each per-source src-filter into that source's input
    filter; use the `ForwardElement` trie for dst-LPM FIBs instead of a per-device
    FilterElement FIB. Target ~850 → ~2–3 elements/device.
  - **L2 predicate reduction (adapter+core, case (c)):** project away unconstrained
    header dimensions per rule (a ports-only rule shouldn't drag 256 bits of IPv6
    through the partition); exploit the `uni::/48` structure so per-subnet prefixes
    nest rather than cross-partition.
  - **L3 APKeep-core AP-merge efficiency (subtree, case (a)):** batch/reorder the
    merge, or a from-scratch bulk-partition path distinct from the incremental one.
- **C2 — correctness preserved (hard gate after every lever):** differential vs NP
  on both slices stays **exact (0 diffs)**; exactness gate green; soundness
  (APKeep never drops an NP-reachable pair) is the tripwire. A speed win that moves
  a single pair is rejected.
- **C3 — measure at full scale:** re-run the Phase A curve + a completed full
  build; report the improvement vs the C0 baseline (and measure NP's wl_up build
  for context).

**Decisions (with user, 2026-08-17):**
- **Depth: go as deep as needed, including L3 core surgery.** If C0 points at the
  AP-merge algorithm (case (a)), invest in APKeep-core work to make from-zero
  tractable — do not stop at the architectural finding.
- **Success bar: best-effort, no fixed threshold.** Reduce build cost as far as the
  levers reasonably allow and report the curve; NP-parity on build time is context,
  not a gate.

**Standing risk.** Case (a) may prove genuinely architectural even after L3; if so
that is itself a thesis result (APKeep incremental-optimised, not from-zero at this
scale) — but per the depth decision we attempt the core fix before concluding it.

---

## Cross-cutting guardrails (reused from the wl_stanford effort)

- The **exactness gate** (`fave/test/exactness_gate.sh`) stays green on
  wl_ifi/wl_i2/wl_stanford on every commit — the non-negotiable tripwire.
- The **APKeep-vs-NP differential** is the objective metric; **soundness is a hard
  gate** (APKeep must never drop a pair NP reaches — `under_approx == 0`).
- All `apkeep/` (Java) changes are **separate subtree commits** with
  `FAVE_CHANGES.md` entries (MIT vendoring hygiene).
- **Measure before core surgery** (`getAPNum` / build-time feasibility) — the
  lesson from wl_stanford's intractable faithful-VLAN path.

## Environment note

Driving these firewall benchmarks needs `pybison` (the `ip6tables`/`iptables`
ruleset parser — the integration-tier dependency), unlike stanford/i2/ifi which
ship pre-generated JSON transfer functions. The project `.venv` already carries the
full stack (bison + JPype), so use `.venv/bin/python` for the probes/harness.
