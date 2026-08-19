# FaVe modifications to NDD

This directory is a **fork of the upstream NDD** decision-diagram library (Li,
Zhang, Zhang, Yang, *"NDD: A Decision Diagram for Network Verification"*, NSDI
'25), vendored into FaVe as a git subtree:

- Upstream: <https://github.com/XJTU-NetVerify/NDD> (see `LICENSE`)
- Imported from upstream commit `c8414b433fe8d1d8b289be7fdee740a293371571`
  (2026-08-05, "Update per-field mixed label backends"), via a FaVe-owned fork.

NDD is planned as the second **engine** behind FaVe's backend-agnostic APKeep
adapter (BDD today, NDD next); see `../APKEEP_NDD_PLAN.md` and `../APKEEP_NDD_EVAL.md`.
As with `apkeep/FAVE_CHANGES.md`, we state our changes prominently here. Kinds:

- **[NEW]** — a capability NDD did not have;
- **[FIX]** — a correctness bug in the upstream code;
- **[INFRA]** — build, test, and tooling that do not change library behaviour.

All items below are reachable via `git log -- ndd/`.

---

## 1. Differential-vs-BDD trust suite on FaVe's IPv6 profile  **[INFRA]**

`src/test/java/org/ants/jndd/diagram/NDDIPv6DifferentialTest.java` (**new test**).
The upstream suite exercises the paper's IPv4-style profile; FaVe's workloads are
IPv6, so this adds a trust suite on **two 128-bit IPv6 address fields** (src, dst)
plus small transport fields — the case the plan flags as highest-risk
(`createVar`/`declareField` at 128 bits). It is a *differential against BDD*: every
NDD boolean op is checked to commute with the `toBDD` homomorphism
(`toBDD(op_NDD(P,Q)) == op_BDD(toBDD(P), toBDD(Q))`) using the same JDD engine NDD
runs on (`NDD.getBDDEngine()`), compared by **canonical node-id equality** — an
exact set-equality oracle that (unlike `satCount` over a 2^280 space) never rounds.
`exist` is checked with layout-independent algebraic identities because NDD fields
share a BDD variable template (so a `getBDDVars`-built cube is not in the `toBDD`
variable space). 7 tests: 128-bit field addressing; IPv6 prefix containment/
disjointness; boolean-op differential (AND/OR/NOT/DIFF/XOR, 400 iters); exist
projection semantics; RONDD canonicity (AND-order + distributivity yield the same
node id); de Morgan/absorption. No upstream behaviour changed; runs in the existing
JUnit 5 + surefire harness (`mvn test`). Full context: `../APKEEP_NDD_EVAL.md` §2.1.

## 2. Restore the atomization layer on the int-node-id core  **[FIX]**

The upstream `c8414b43` refactor ("Update per-field mixed label backends") made
`org.ants.jndd.diagram.NDD` **int-node-id based** but left `AtomizedNDD.java` +
`AtomizedNodeTable.java` written against the older **object-form** NDD, so they no
longer compiled and were **excluded from the build** (`pom.xml`), together with the
`application/wan/**` reference verifiers. Atomization (the atomic-predicate
maintenance APKeep's fast reachability needs) was therefore absent from a working
build. FaVe restores it:

- **Un-excluded** `AtomizedNDD.java` + `AtomizedNodeTable.java` (`pom.xml`); the
  `application/wan/**` reference verifiers stay excluded (separately stale).
- Ported the two files to the int core, preserving the authors' algorithm (a
  representation port, not a redesign): `AtomizedNDD` carries its own instance
  `field` (the int core has no inherited instance field); the atom-DAG boolean ops
  (`and/or/not/diff/exist`) are unchanged; the **bridges** to plain NDD are rewired
  to the int API — `atomizedToNDD` returns an `int` node id built via
  `NDD.addAtField` (with explicit `ref`/`deref` for GC safety), and `atomization` /
  `atomizeNDD` / `collectFieldPreds` / `getAtomsToSplitSingleField` read predicate
  structure via `NDD.getField/getEdgeCount/getEdgeTarget/getEdgeLabel` and key on
  `int` node ids (`HashSet<Integer>`/`HashMap<Integer,…>`). `AtomizedNDD.getTrue/
  getFalse` were renamed `getAtomizedTrue/getAtomizedFalse` to stop them hiding the
  int-returning `NDD.getTrue/getFalse`.
- **New test** `src/test/java/org/ants/jndd/diagram/NDDAtomizationTest.java`: a
  differential correctness gate on FaVe's 128-bit IPv6 profile — per-field atoms are
  pairwise-disjoint and cover each field (BDD-level check), each input predicate
  **recombines exactly** (`atomizedToNDD(atomization(P)) == P`, canonical node id),
  and the atom count is the per-field sum. Green: 25 tests total (17 upstream + our
  §2.1c 7 + this). FaVe-side context: `../APKEEP_NDD_EVAL.md` §2.1/§2.5.

Not yet exercised: `exist` (transformers/NAT — not needed for wl_up) and the
incremental split path (`getAtomsToSplit*`/`changeAtoms`) are ported and compile but
are covered only indirectly; the from-zero engine uses batch `atomization`.

## 3. wl_up NDD engine tests (sizing + reachability)  **[INFRA]**

Two FaVe tests exercise the atomization/DD core on the real wl_up model (both skip
unless `-Dwlup.*` system properties point at line-file dumps produced by
`../fave/bench/wl_up/eval/wl_up_dump2.py`):

- `src/test/java/org/ants/jndd/diagram/NDDWlupSizingTest.java` — builds the 6560 wl_up
  rule hit-predicates as per-field NDDs and atomizes them; measures Σ-over-fields atoms
  (= **364**, src6 138 / dst6 159 / proto 4 / sport 30 / dport 31 / rel 2) vs the BDD
  global partition (`ap_num` 14 561) ⇒ **~40× reduction**; verifies recombination.
- `src/test/java/org/ants/jndd/diagram/NDDWlupReachabilityTest.java` — a full NDD
  reachability engine for wl_up (first-match residual per out_port ⇒ LPM; per-source
  fixpoint flood keyed by (device, arrival-port), no-hairpin; source src-IPv6 seed),
  gated on **exact parity** with the frozen BDD baseline: **3661/3661, 0 over, 0
  under**. Proves the (B) engine-swap correct on wl_up. It also carries an atom-based
  variant (hop = `AtomizedNDD.and` over the §2.5b atoms) at equal parity, and phase
  timing: full from-zero build+query is **~0.45 s** (plain) / **~0.6 s** (atom-based)
  vs the BDD-APKeep baseline's **~1079 s** and NetPlumber's ~49 s. FaVe context:
  `../APKEEP_NDD_EVAL.md` §2.5b/§2.5c/§2.5d.

## 4. Productionized NDD reachability engine (main-source, JPype-driven)  **[NEW]**

`src/main/java/org/ants/jndd/fave/NddReachabilityEngine.java` (**new main class**)
promotes the §2.5c/d prototype out of the test tree into a callable engine that
FaVe drives through JPype (`../fave/apkeep/lib_ndd.py`), so NDD is a real second
**backend engine** behind the one shared APKeep adapter (the BDD engine is
`../apkeep`). The FaVe adapter emits a backend-neutral IR — the same
`+ filter …` rule strings and `"dev port dev port"` topology edges it hands the
BDD engine — and this class consumes them directly: `build(rules, edges)`
computes the per-device first-match residual predicate per out_port (higher
priority ⇒ LPM), and `isReachable(srcDev, srcPort, cidr, dstDev, dstPort)` runs
the per-source fixpoint flood keyed by (device, arrival-port) with no-hairpin and
the source's src-IPv6 space as the query-time seed. The residual/flood/encoders
are ported **verbatim** from `NDDWlupReachabilityTest` (plain `NDD.and` hop); the
only additions are the in-memory API and per-source flood caching (so the
adapter's probe×source loop pays 137 floods, not 137²). Scope: single-universe
forwarding (no ACL/NAT) — the adapter guards it. Field layout is initialised once
per JVM (NDD's node tables are process-global statics).

Covered by the FaVe-side parity gate `../fave/test/test_apkeep_ndd_wlup.py`:
the real wl_up model, driven through the real aggregator into
`APKeepAdapter(engine='ndd')`, reproduces the frozen BDD baseline matrix
(`../fave/bench/wl_up/eval/mat_apk.json`) **exactly** (3661 pairs, 0 over, 0
under). Added to `../fave/test/exactness_gate.sh` (which now also builds this
jar). FaVe context: `../APKEEP_NDD_EVAL.md` §2.5e.

## 5. IPv4 forwarding in the reachability engine (§2.6 incr 1)  **[NEW]**

`NddReachabilityEngine` gains IPv4 so it covers FaVe's IPv4 benchmarks, not just
wl_up's IPv6. The field layout now APPENDS 32-bit `SRC4`/`DST4` and a 16-bit
`VLAN` after the six wl_up fields (indices 0–5 unchanged, so wl_up parity is
preserved by construction — one process-global field set serves every benchmark).
Added: IPv4 address encoders (a uint32 prefix, or a dotted-quad + cisco
inverse-mask wildcard built bit-by-bit so any wildcard is exact) with the src/dst
slot dispatching v4-vs-v6 by token; and parsing of `+ fwd <dev> <prefix> <plen>
<out> <prio>` (dst-LPM ForwardElement) folded into the SAME first-match residual
model as `+ filter`. wl_tum (IPv4 5-tuple) and wl_stanford P7a (IPv4 dst-LPM) now
reach exact parity with the BDD engine (`../fave/test/test_apkeep_ndd_fwd.py`),
alongside wl_up.

Not yet handled: **wl_i2 scale** (77 k dst routes). The residual materializes each
port's forwarded-set as a monolithic per-field NDD (a union of thousands of
prefixes → a large BDD; true partition is only `ap_num`=216), and one-shot
`AtomizedNDD.atomization` of the raw rules is ~O(n²) — both exhaust memory/time.
The fix is APKeep-style *incremental* atomic-predicate maintenance (atom-id sets
over the minimal partition, via the ported-but-untested `getAtomsToSplit*`/
`changeAtoms` path). Tracked in `../APKEEP_NDD_EVAL.md` §2.6.

## 6. ACLElement (permit/deny) in the reachability engine (§2.6 incr 2)  **[NEW]**

`NddReachabilityEngine` now consumes `+ acl` rules, so wl_ifi (router ACLs) runs
on NDD. An ACL rule has the SAME token layout as `+ filter` (proto/src/sport/dst/
dport at identical indices) — only `t[1]`=`acl` and `t[5]`=`permit`/`deny` differ
— so the predicate reuses the filter encoder; a permit maps to the element's
`"permit"` out_port and a deny drops, folded into the same first-match residual
(Cisco first-match ⇒ higher priority wins). The only genuinely new bit is APKeep's
ACLElement node naming: an element `E` appears in the topology graph as the node
`E_in`/`E_out`, so the flood maps an arrival node back to its element (`elementOf`,
a trailing-suffix strip that leaves dotted names like `in.bbra_rtr` untouched). The
source's src-IP is the query-time seed, so source-matching ACLs bite. Gated exact
vs the ground truth by `../fave/test/test_apkeep_ndd_fwd.py` (wl_ifi ==
reachable.json). NAT/VLAN rewrite (`+ nat`) is still future work (§2.6 incr 3).

## 7. NAT/VLAN transformer in the reachability engine (§2.6 incr 3)  **[NEW]**

`NddReachabilityEngine` gains packet transformers, so the faithful wl_stanford
VLAN model runs on NDD. Additions: a 16-bit VLAN field (already declared in the
canonical layout); VLAN-admission ACLs (a `+ acl` with a trailing comma-separated
VLAN set → constrain the VLAN field, OR over the set); and `+ nat <dev> <port>
vlan <dstIP> <plen> <vlanN>` — an inline VLAN rewrite on the egress port, applied
in the flood via `NDD.exist(part, VLAN)` (drop the old VLAN) `∧ VLAN=vlanN` on the
dst-prefix-matched part, with unmatched dst passing unchanged (the NATElement's
identity default). A probe (host on an access port) STRIPS the VLAN tag on
delivery, so a probe device's header is `exist(VLAN)`-untagged before the arrival
check — a no-op where VLAN is free (every non-faithful benchmark), and what makes
the faithful data plane match the reference. The query API grows a `targetVlan`
arg (the checker's probe-VLAN constraint) and a device→header cache.

Gated exact vs **NetPlumber** by `../fave/test/test_apkeep_ndd_fwd.py::
test_stanford_faithful_vlan_matches_netplumber` (165 pairs, 0 over/under). This is
the workload BDD-APKeep cannot finish — its VLAN×dst atomic-predicate partition
explodes (ap_num ≈ 21.6k, 28 min+ unfinished) — while NDD builds it in ~3 s. Full
context + the BDD build profile: `../APKEEP_NDD_EVAL.md` §2.6.

## 8. Atomic-predicate dst-IP forwarding for large FIBs (§2.6 incr 1b)  **[NEW]**

`src/main/java/org/ants/jndd/fave/AtomForwarding.java` (**new class**) makes
wl_i2 (77k dst routes) tractable on NDD. The general engine's monolithic per-port
residual OOMs/times out there (the true partition is only `ap_num=216`), so this
computes that minimal partition directly with **integer interval arithmetic** (no
BDDs): each `+ fwd` rule is a [lo,hi] dst range; the union of range boundaries
gives elementary intervals (16 232); a per-device binary trie gives each
interval's LPM port; intervals with the same per-device forwarding signature
merge into one atom → **216 atoms, == APKeep's ap_num**. Reachability floods
atom-sets (per (device, out_port) atom-set; per-source fixpoint, no-hairpin).
Builds in ~0.7 s, exact vs the oracle (72 pairs). The FaVe adapter routes any
pure-`+fwd` FIB (wl_i2, wl_stanford-P7a) here via `LibNDD.build_fwd_atoms`. It is
the base for a two-field faithful-i2 (dst × VLAN) engine, where the VLAN stays a
separate field (NDD's Σ) vs BDD's dst×VLAN cross-product (Π). Context:
`../APKEEP_NDD_EVAL.md` §2.6.

---

*Full FaVe-side context (why NDD, the field-locality GO/NO-GO, the integration
roadmap) lives in `../APKEEP_NDD_PLAN.md` and `../APKEEP_NDD_EVAL.md`.*
