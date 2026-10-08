# FaVe modifications to APKeep

This directory is a **fork of the upstream APKeep** data-plane verifier
(Zhang et al., *"APKeep: Realtime Verification for Real Networks"*, NSDI '20),
vendored into FaVe as a git subtree:

- Upstream: <https://github.com/XJTU-NetVerify/apkeep> (MIT license, see `LICENSE`)
- Imported from upstream commit `7b71bff46f247ca623d39ccab65c03c0ec01cb6b`
  (FaVe subtree commit `50c17885`).

Per the MIT license we state our changes prominently; this file is also the
record of enhancements for any publication. Every item below is a FaVe
modification, not upstream behaviour. Each is grounded in the commit(s) that
introduced it (all reachable via `git log -- apkeep/`).

The changes fall into three kinds:

- **[NEW]** — a capability APKeep did not have (chiefly: reachability queries, and
  extra/rewritable header fields);
- **[FIX]** — a correctness bug in the upstream code;
- **[INFRA]** — build, test, and tooling that do not change verification behaviour.

---

## 1. Reachability queries over the Port Predicate Map  **[NEW]**

Upstream APKeep exposes only forwarding-**loop** detection. FaVe needs
source→probe **reachability** (that is what its compliance checks reduce to), so
we added a solver on top of the existing atomic-predicate / Port-Predicate-Map
substrate — without changing the update algorithm.

- `apkeep/checker/ReachabilityChecker.java` (**new class**): existential
  port-to-port reachability. A simple-path DFS over the topology + per-port AP
  transfer (`Element.forwardAPs`), division-aware (tracks the forwarding and ACL
  atomic-predicate sets separately, arrival iff they overlap by BDD
  intersection). Terminates on networks with forwarding loops.
  Commits `d84133df`, `46697b9f`.
- Arrival is detected both at an egress port and at a link-destination (ingress)
  port, so a probe attached to a device input is reachable. Commit `46697b9f`.
- **Source-IP seeding** — `Network.getACLSeedAPs(srcip, prefixlen)` (**new
  method**): seeds the ACL packet space with exactly the atomic predicates
  overlapping the injected source prefix, so source-matching ACLs bite (without
  it a flow counts as reachable whenever *any* source is permitted).
  Commit `9455e4f2`.
- **Target-header constraint** — `ReachabilityChecker.isReachable(src, dst, srcip,
  len, targetHeaderBDD)`: the packets that reach the target must overlap a header
  predicate (e.g. a probe that only accepts `vlan=0`). Commits `21360933`,
  `ca4ff2ad`.
- **Witness capture** — on a reachable query the checker records the concrete
  arriving path and surviving forwarding APs in public fields `witnessPath`
  (`source .. target` hop sequence) and `witnessFwd` (the atomic predicates that
  reached the target); both reset to `null` at the start of every query and stay
  `null` when the target is unreachable. This is diagnostic-only — it does not
  change any reachability verdict — and exists to walk the exact path APKeep
  admits when reconciling its over-approximation against NetPlumber
  (`APKEEP_BACKEND.md`, wl_stanford convergence work).

## 2. Extra and rewritable header fields  **[NEW]**

APKeep's header field set is fixed (IPv4 5-tuple + MPLS + inner-IP + IPv6 dst).
FaVe workloads need VLAN, both as a match field and as a value routers rewrite.
The APKeep *technique* is header-agnostic (the header is just `h` BDD variables),
so these are additive.

- **VLAN as a match field** (`common/BDDACLWrapper.java`, `common/ACLRule.java`):
  a 12-bit `vlan` field whose BDD variables are declared **last** (after the
  existing fields) so no existing field's variables shift; `ConvertVLAN` matches
  an exact tag and is AND-ed into `ConvertACLRule` only when a rule carries one.
  `ACLRule` gained an **optional trailing** VLAN token, so the historic 14-token
  ACL format is byte-for-byte unchanged. Commit `350e6f33`.
- **VLAN as a rewritable field** (`common/Fields.java`, `common/BDDACLWrapper.java`,
  `apkeep/rules/RewriteRule.java`, `apkeep/elements/NATElement.java`): `Fields.vlan`
  + `BDDACLWrapper.vlanField` + `get_field_bdd(vlan)`; a field-selecting
  `RewriteRule` so the matched field (e.g. the dst-IP route) can differ from the
  rewritten field (VLAN); a VLAN-rewrite `NATElement.encodeOneRule` form
  (`+ nat <dev> <port> vlan <dstIP> <dstlen> <vlanN>`). Commit `15d0d119`.

## 3. NAT / rewrite plumbing for reachability  **[NEW]**

- **Inline NAT insertion** — `Network.addNATs` now inserts a `NATElement`
  *inline* on a device port: it redirects that port's existing downstream through
  `nat.inport -> nat.outport` (previously the NAT was only reachable via an added
  inport edge). Commit `f38a8bc2`.
- **Rewrites in reachability** — `ReachabilityChecker` applies a `NATElement`'s
  rewrite to the AP sets it carries and continues out the NAT's inline output, so
  a header rewrite (e.g. a VLAN reassignment) propagates through a reachability
  query. Commit `f38a8bc2`.
- **Single-universe mode** — `Parameters.USE_DIVISION` (+ `Network.isDivisionActivated`):
  when false, `ACLElement`s are kept in the *forwarding* atomic-predicate universe
  instead of a separate ACL universe ("division"). This lets a VLAN **rewrite**
  (a NAT, forwarding universe) compose with a VLAN **admission** (an ACL) in one
  universe; under division the two universes disagree on the rewritten field.
  `ReachabilityChecker` filters the forwarding AP set at ACLs in this mode. Default
  (true) preserves the upstream src-IP-ACL division path. Commit `0f834f77`.

## 4. Bug fix: multi-rule NAT + AP merging  **[FIX]**

Upstream `NATElement` coalesces ("merges") atomic predicates **eagerly, mid-update**
at several sites (`tryMergeIfNATElement`, and the output-side loop in
`transferOneAP`). With **more than one rewrite rule on a single NAT** this removes
atomic predicates that the in-progress split loop and the end-of-update batch merge
still reference, cascading into `APNotFoundException` / `APSetNotFoundException`
and a JDD `quant_rec` use-after-free (an invalid BDD node). AP merging is only a
size optimisation, so it is *supposed* to be behaviour-neutral; upstream simply
never exercised a NAT with multiple rewrite rules.

Fix — consolidate **all** merging into the single end-of-update batch merge
(`Network.softMergeAPBatch`), matching how every non-NAT element already works:

- `apkeep/core/APKeeper.java`: `tryMergeAP` no-ops on an already-merged AP; the
  `MergeAP` flag is read dynamically (was a load-time-cached `final`) so callers
  can toggle it.
- `apkeep/elements/Element.java`: the split loop skips snapshot APs no longer
  present.
- `apkeep/elements/NATElement.java`: `tryMergeIfNATElement` is a no-op (defer to
  the batch) and the `transferOneAP` output-side eager merge is removed; a new
  `updateAPSetMergeBatch` maintains the NAT rewrite table across a batch merge
  (the set analogue of the existing pairwise `updateAPSetMerge`).

Commits `3378087a`, `809c1ae0`, `954e2521`. Pinned by
`apkeep/checker/NATReachabilityTest.multipleVlanRewritesOnOneNat` (multiple
rewrites on one NAT, AP merging on).

## 5. Build reproducibility  **[INFRA]**

`pom.xml` (commit `b89b2701`):

- Pin `maven.compiler.release=11` + `maven-compiler-plugin` 3.11.0. Upstream set
  no Java version, so Maven's super-POM defaulted the compiler to Java 1.5, which
  JDK 11 (APKeep's documented target) rejects.
- Vendor a **JDD** jar (built from the author's source) in an in-tree file
  repository `local-maven-repo/` (see its `README` for provenance; zlib/public
  domain). Upstream pinned JDD `108` via JitPack, which serves only JDD's `.pom`
  (never a resolvable `.jar`), so `mvn package` could not resolve JDD at all. We
  use the nearest published tag, `111` (same author; the BDD API used here is
  long-stable across it).

## 6. Test harness  **[INFRA]**

Upstream ships **no tests** (no `src/test`, build ran `-DskipTests`). We added a
JUnit 5 + `maven-surefire` + JaCoCo harness (`pom.xml`) and a suite over the
reachability-critical classes — `BDDACLWrapper` (encoders + a variable-layout
lock), `ForwardElement` (LPM / higher-priority-wins), `ACLElement` (5-tuple + VLAN),
`APKeeper` (minimum-EC split/merge), `Network` (in-memory wiring + `getACLSeedAPs`),
and our `ReachabilityChecker` / `NATElement` additions. A JaCoCo ratchet floor
(BUNDLE instruction coverage) guards against regressions. Tests run in the `test`
phase of `mvn package`, so the FaVe integration tier gates on them.
Commits `f50f6ab8`, `5ee99fba` (+ test additions alongside each change above).

## 7. Multi-field packet-filter forwarding (`FilterElement`)  **[NEW]**

`apkeep/elements/FilterElement.java` (+ `APKeeper`/`Network` wiring). A new
`Element` subclass for a packet filter's `forward_filter` table — the FaVe
`packet_filter` device (wl_tum, wl_up). No stock element fit: `ForwardElement`
matches only a dst-IP prefix, `ACLElement` matches the full 5-tuple (+VLAN) but
only gates into permit/deny. `FilterElement` combines the two — `ACLElement`'s
first-match match encoding (`BDDACLWrapper.ConvertACLRule`) with
`ForwardElement`'s placement of each rule's hit-predicate on a real named
`out_port` — so a rule forwards accepted traffic out a chosen port and unmatched
traffic falls to a `__drop__` sink (a traversal dead-end, wired to nothing). It
extends `Element` directly (not `ACLElement`) so it lives in the forwarding AP
universe. Rule string: `+ filter <device> <accessList> <accessListNumber>
<out_port> <protoLo> <protoHi> <src> <srcWild> <sportLo> <sportHi> <dst>
<dstWild> <dportLo> <dportHi> <priority> [vlan]` — an ACL rule whose permitDeny
slot is the out_port. Wiring: a 6-arg `Network.initializeNetwork(...,
device_filters)` overload + `addFilters` (registers a `FilterElement` per
packet-filter device *before* `constructTopology`, so a topology link does not
overwrite it with a `ForwardElement`); `APKeeper.initialize` seeds a filter
device's initial all-space AP on its `__drop__` port. Tests: `FilterElementTest`
(first-match forward-to-out_port vs drop; multi-out_port priority). 27 Java tests
green. FaVe-side context: `../docs/APKEEP_TUM_UP_PLAN.md` Phase 2.

## 8. Source IPv6 + IPv6 ACL/filter matching  **[NEW]** / **[FIX]**

`common/BDDACLWrapper.java`. APKeep shipped only a *destination* IPv6 field
(`dstIP6`), and it was **mis-declared** — `DeclareDstIP6()` created only `ipBits`
(32) of its 128 variables, so IPv6 beyond a /32 was silently broken (dormant; no
ACL path used it). A firewall ACL (wl_up is IPv6-only) needs **both** IPv6
addresses at full width. Added: a 128-bit **`srcIP6`** field; **[FIX]** `dstIP6`
now declares all 128 bits. Both IPv6 fields are declared **last** (after VLAN) so
no existing field's variables shift — the behavioural layout-lock
(`BDDACLWrapperTest`) still passes. New `encodeIP6Prefix(cidr, vars)` encodes an
IPv6 "addr/len" prefix over `srcIP6`/`dstIP6`, mirroring `ConvertIPAddress`'s mask
path (same LSB-first `vars[k]` convention, so IPv6 prefixes nest/disjoin like IPv4
ones); `ConvertACLRule` routes an address token containing `':'` to the IPv6 path
(no rule-format change — IPv4 and IPv6 are mutually exclusive per rule). This
feeds both `ACLElement` and `FilterElement` (both encode via `ConvertACLRule`).
Tests: `BDDACLWrapperTest` IPv6 prefix containment/disjointness + src6/dst6
independence. 29 Java tests green. FaVe-side context:
`../docs/APKEEP_TUM_UP_PLAN.md` Phase 6 (P9b).

## 9. Reachability instrumentation (scaling diagnosis)  **[INFRA]**

`checker/ReachabilityChecker.java`, `core/Network.java`. Additive measurement
hooks, no semantic change to reachability or forwarding. `ReachabilityChecker`
gains static per-query work counters — `nodesVisited` (every `traverse()`
expansion of a (path-prefix, port)) and `branchesExplored` (child descents) —
reset at each public `isReachable()` entry, so a JPype caller reads the last
query's cost. `Network` gains read-only structural accessors `numElements()`,
`numElementsOfType(simpleClassName)`, `numPorts()`. Together these quantify the
per-pair simple-path DFS cost and the single-AP-universe precondition
(`ACLElement`/`NATElement` == 0) that the Phase-7 per-source reachability
fixpoint requires. FaVe-side context: `../docs/APKEEP_TUM_UP_PLAN.md` Phase 7
(Phase 0 guard + Phase A curve).

**Phase C addition — streaming build profiler.** `utils/BuildProfiler.java` (new):
a daemon-thread sampler that snapshots build metrics on a wall-clock interval and
appends one JSONL line per sample (flushed per line, so a killed run still yields a
parseable growth curve — the full wl_up build is a single synchronous call Python
cannot poll). Opt-in: no-op unless a path is passed, so normal runs and the
exactness gate are unaffected. `Network` gains `totalPPMEntries()` and cumulative
phase timers (`BuildProfiler.encode/insert/ppm/mergeNanos`) around the four inner
build steps (`encodeOneRule`, `insert/removeOneRule`, `updatePortPredicateMap`,
`soft/hardMergeAPBatch`) plus a `rulesApplied` progress counter; `Element` gains
`numPPMEntries()`. These attribute the from-zero build cost: on wl_up it is **PPM
update (93 %)**, a quadratic AP-partition explosion detonated by the dst-LPM FIB
rules (encode/merge negligible, insert flat). FaVe-side context:
`../docs/APKEEP_TUM_UP_PLAN.md` Phase C (C0).

**Phase C1 addition — split counters + element-name accessor.** `APKeeper.
updateSplitAP` increments `BuildProfiler.splitCount` (AP-partition splits) and
`splitTouches` (Σ elements iterated per split, since the method rewrites *every*
element on *every* split). These proved the from-zero PPM cost is
`splitCount × numElements` (`splitTouches / splitCount` == `numElements` exactly),
which retired the ForwardElement-trie hypothesis (it moves neither factor) and
redirected the fix to element-count and split-count reduction. `Network` gains
`elementNames()` so the FaVe adapter can bucket elements by role and size the
reduction. All additions are inert (counter increments / a read-only accessor);
gate green. FaVe-side context: `../docs/APKEEP_TUM_UP_PLAN.md` Phase C (C1).

**Phase C1 Lever B — query-time source-IPv6 seed (retires the per-source .sf
element).** `BDDACLWrapper.encodeSrcIP6Prefix(cidr)` builds the exact src-IPv6
prefix BDD; `ReachabilityChecker.isReachable(source, target, String srcCidr)` seeds
it into `acl_aps` as a single BDD, carried unchanged through traversal (forwarding
is source-independent; no ACL/NAT to filter it) and intersected with the forwarded
space at ARRIVAL via `hasOverlap`'s real `bdd.and`. That intersection is exact
regardless of AP-partition alignment, so a source's address need NOT split the
global partition -- which is what the FaVe adapter's per-source `.sf` FilterElement
used to force. On wl_up those per-source src predicates induced ~80 % of the AP
partition (slice ap_num 1128 -> 215, ppm_ms 11.6 s -> 2.4 s), all recovered at zero
correctness cost (NP-parity 0 diffs on cs+jura). The `.sf` path remains for the
ACL-division / IPv4 case (wl_stanford). FaVe-side context:
`../docs/APKEEP_TUM_UP_PLAN.md` Phase C (C1 Lever B).

**BUGFIX -- protect `parta`/`partb` against JDD's GC in `APKeeper.addPredicate`
(FaVe TODO item 29).** Upstream computes `parta = and(pred, oldap)` and leaves it
**unreferenced** across the following `and(predneg, oldap)` and across the whole
of `updateSplitAP`. In JDD an allocation reaches `NodeTable.grow()`, which calls
`gc()`, which frees unreferenced nodes -- so a sufficiently large build collects
`parta` mid-split and the element loop then hands a dead handle to
`BDDACLWrapper.nat()`, where `getVar` returns -1 and `quant_rec` throws
`ArrayIndexOutOfBoundsException` on `varset_vec[var]`. `NATElement.
updateRewriteTableIfPresent`'s upstream `// TODO Auto-generated catch block` then
swallows it and retries, so the build continues over a **half-updated AP
partition** (`updateSplitAP` mutates the global `AP` set before iterating
elements, and is not transactional) -- a soundness hazard, not merely a crash.
`addPredicate` now takes a temporary ref on each part on computation and drops it
after `updateSplitAP` has taken its own permanent ref, so the net reference count
per AP is unchanged from upstream.

Measured on wl_cloud (the first FaVe workload whose NAT rewrites a 32-bit
*address* rather than a 12-bit VLAN, so each `nat()` allocates enough to trigger
the GC inside the split loop): unpatched, the build dies at **1 226 of 1 773
rules, `ap_num` 53 978**, reproduced twice with every structural quantity
identical. Patched, it runs past that point with **zero exceptions**, reaches
`ap_num` 66 656 at 1 244 rules, and `merge_ms` becomes non-zero (235 238 vs 631)
-- AP merging works again, which it cannot over a corrupted partition. Java core
suite green (`mvn package` runs it). FaVe-side context: `../docs/CLOUD_BENCH_PLAN.md`
§1.7.3, `../TODO.md` item 29.

**A first attempt patched the wrong frame and is recorded because it is the
useful half of the evidence:** hoisting the `ref`s that already existed at the
END of `updateSplitAP` to above its element loop changed nothing -- the handle is
already dead on entry. That is what localised the defect to the caller.

**BUGFIX -- a NAT's rewrite outputs must be re-registered after a rule applied to
ANY OTHER element (FaVe TODO item 29).** A `NATElement` stores, per input atomic
predicate, the BDD its rewrite produces (`bdd.nat(ap, field, new_value)`).
`Element.forwardAPs` carries packets onward by INTERSECTING AP-ID SETS
(`retainAll`), so a stored output only forwards if it is a **member of the
partition** -- a node id that is merely a valid BDD intersects to nothing and the
traffic disappears. `NATElement.updateRewriteTable()` is what registers them (via
`APKeeper.addPredicate`), but upstream calls it only from
`Element.updatePortPredicateMap`, i.e. only on the element that just received a
rule. That is not when the outputs go stale: they go stale when a rule inserted
into **another** element splits or merges one of this NAT's input APs, because
`updateAPSplit` / `updateAPSetMergeBatch` recompute the outputs with `bdd.nat()`
and nothing re-registers the results. Verbatim upstream (`50c17885`), and
silent -- a wrong verdict, no exception.

`Network.refreshRewriteTables()` (**new**) now drives every `NATElement` to a
global fixpoint on **both sides** of the per-rule `softMergeAPBatch()` and of the
batch `hardMergeAPBatch()`. Both sides, because the merge's mergability guard
(`NATElement.isMergable`) reads `output_aps` -- a stale entry there lets it merge
two APs the rewrite distinguishes -- and because the merge re-derives the outputs
itself (`updateAPSetMergeBatch`); the pre-merge call is also where upstream's
per-element registration sat, so that ordering is preserved rather than changed.
`Element.updateRewriteTableIfPresent()` became `public boolean` so the network
can tell when a round changed something (registering one output splits the
partition, which can invalidate another NAT's). It terminates for the same reason
APKeep's own splitting does: each round strictly refines a finite partition.

**Cost, measured -- and it is the AP merge, not the refresh.** The partition grows
21 % (67 761 -> 82 038 atomic predicates at rule 1 300 of wl_cloud) but the build
slows by a factor that GROWS with the rule count: 1.17x at rule 1 226, 2.40x at
1 250, 3.19x at 1 275, 3.67x at 1 300. At rule 1 300 the wall goes 1 920 s ->
7 050 s, of which `ppm_ms` accounts for 648 -> 807 s (1.24x, in line with the
partition) and **`merge_ms` for 1 269 -> 6 146 s (4.8x)**. The refresh itself is
1.4 % of wall.

The merge factor is the defect again. `APKeeper` consults
`NATElement.isMergable(ap1, ap2)` before merging, and that guard is written
entirely in terms of `output_aps` and the `rewrite_table` VALUES. While those hold
stale raw BDD ids, no real atomic predicate is ever found in either, so the first
line -- `!contains(ap1) && !contains(ap2)` -- returns true for every pair. **The
guard was vacuous**, and the engine merged APs its own rewrite distinguishes: a
second way the same staleness corrupts the partition, and the reason merging used
to be cheap. `NATElement.updateRewriteTable()`'s per-call copy of the whole
rewrite table, which a dirty flag would remove, is worth only that 1.4 %.

Measured on wl_cloud, where FaVe emits the 25 NAT rules **before** ~550
first-match filter rules, so every rewrite output was stale by the end of the
build: APKeep-BDD returned **53 of 64** reachable pairs where NDD and NetPlumber
both return **59**, losing exactly the six internet-sourced ones -- the DNAT
delivered nothing. Reduced to a **70-rule, 0.4 s** repro (one DC, one leaf, one
NAT rule) and then to the four-rule model in
`../fave/test/test_apkeep_nat_rewrite.py`.

Patched, a 343-rule prune of the same model -- the endpoint-bearing leaves only,
on which NDD reproduces the full 64-cell matrix exactly -- goes **53/64 ->
59/64, cell for cell identical to both NDD and NetPlumber**. The partition grows
little (`ap_num` 16 485 -> 17 925, +8.7 %) but the build slows 2.8x (150 s ->
427 s); `dc0` goes 2/4 -> 3/4 at `ap_num` 4 329 -> 5 584 and 9.6 s -> 22.6 s. FaVe-side context: `../docs/CLOUD_BENCH_PLAN.md` §1.7.3, `../TODO.md` item 29.

---

*Full FaVe-side context (why each extension, the wl_stanford modelling, the
roadmap) lives in `../docs/APKEEP_BACKEND.md`.*

## 10. A VLAN on a destination FIB outside the HSA stages  **[FIX]**

TODO item 33, 2026-09-30. `_is_dst_lpm_table` classified a forwarding table as a
destination-prefix FIB whenever its rules matched only the destination, the
ingress port and the VLAN (`_LPM_MATCH_FIELDS`), and rewrote only `out_port` or
the VLAN (`_LPM_REWRITE_FIELDS`). A FIB is translated by `_translate_fwd_rule`,
which keeps the destination alone, so for any device outside the
`in.`/`mid.`/`out.` stages the VLAN match and the VLAN rewrite were dropped
without a word. That contradicts this adapter's own `UntranslatedSemantics`
contract.

Found on a router on a stick (`fave/test/test_revisit_router_on_a_stick.py`).
Both of a switch's VLAN-qualified rules became the same default route, and APKeep
reached host B **through a genuine loop**, where VeriFlow-FR, ad6 and NetPlumber
all answer "not reached".

**Fix.** The VLAN moved to `_LPM_STAGE_FIELDS`, which is allowed only where a
mechanism carries it:
- **a VLAN match or rewrite in an HSA stage** (`_is_staged`), whose mechanisms
  carry it (`_build_stanford_faithful`, `_build_i2_faithful`, plain mode's
  `_demux_ingress`);
- **a VLAN rewrite in a router's routing table** (`_router_devices`), which
  `_capture_vlan_port` maps to the egress port wiring the acl_out groups. That
  models egress selection, not the header change: a later table matching the new
  VLAN would see the old one. Nothing in the suite does that.

Anywhere else a VLAN match or rewrite makes the table first-match, and its
`FilterElement` carries the VLAN match and refuses a VLAN rewrite.

A first cut allowed the VLAN in HSA stages only, and the integration tier refused
`wl_ifi`: its router's declared-LPM routing table rewrites the egress VLAN. The
census behind "the suite is unaffected" had counted match fields, not rewrites.
The router case was then added, test-first. Both small networks are now **refused**, each
with its reason: the VLAN rewrite, and in-port-qualified rules on a first-match
table. That is a declared capability gap in place of a false positive.
Classifier tests: `test/test_apkeep_first_match.py`, including `wl_ifi`'s router
shape. On the suite nothing changes: every VLAN match in a forwarding table sits
in an HSA stage, and every VLAN rewrite in an HSA stage or a router's routing
table. Confirmed by the integration tier's APKeep differentials.

