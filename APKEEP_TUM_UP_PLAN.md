# Plan: APKeep on wl_tum and wl_up (stateful firewalls + IPv6)

**Goal.** Bring the two remaining FaVe benchmarks — `wl_tum` (TUM-i8, a large
stateful IPv4 firewall) and `wl_up` (University-Potsdam, an IPv6 campus network) —
onto the APKeep backend, faithful to NetPlumber, extending the head-to-head
comparison beyond the already-done `wl_ifi` / `wl_i2` / `wl_stanford`.

**Status:** PLAN + Phase 0 DONE (evidence below). Owner: Claas Lorenz. Driver:
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
- **Phase 6 — wl_up IPv6 (P9b).** Add the 128-bit `srcIP6` field (+ IPv6 ACL path +
  `ForwardingRule6`), JUnit-first with the layout-lock; then wl_up vs its
  (stateless) `reachable.json` + an NP differential; guardrail green. Highest
  effort; after the wl_tum state path is proven. Task #7 (blocked by #5).

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
