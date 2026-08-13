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

---

## Phased plan (tracked as tasks #1–#7)

- **Phase 0 — diagnostic probe. DONE** (above). Task #1.
- **Phase 1 — wl_tum APKeep-vs-NP differential + gated test.** wl_tum ships an
  empty oracle, so NP is the reference. Build the differential (extend
  `bench/apkeep_convergence.py` or a sibling), add a gated integration test
  (`require_or_skip` + `FAVE_REQUIRE_BACKENDS`, from the P5 CI-gate work) asserting
  APKeep == NP. This is the objective metric for Phases 2–4. Task #2.
- **Phase 2 — model the conntrack `related` state field** (as a match dimension
  first; leverage the P7b VLAN-rewrite core generalized off dst-IP). Test-first
  (JUnit + adapter). `getAPNum` feasibility check (expected tractable — match, few
  distinct values, not a per-route rewrite). Task #3 (blocked by #2).
- **Phase 3 — model `svlan`/`dvlan` match + `in_port`/`out_port` rewrite** in the
  adapter/core (port-metadata rewrite is bounded → coalesces → tractable).
  Test-first. Task #4 (blocked by #2).
- **Phase 4 — wl_tum convergence + scale result.** APKeep ≡ NP (differential
  green); guardrail exactness gate stays green on ifi/i2/stanford; measure &
  document from-zero build time APKeep vs NP on the 3.8k-rule firewall (the
  wl_i2-analogue headline for firewalls); promote to CI. Task #5 (blocked by #3,#4).
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
