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
green. FaVe-side context: `../APKEEP_TUM_UP_PLAN.md` Phase 2.

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
`../APKEEP_TUM_UP_PLAN.md` Phase 6 (P9b).

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
fixpoint requires. FaVe-side context: `../APKEEP_TUM_UP_PLAN.md` Phase 7
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
`../APKEEP_TUM_UP_PLAN.md` Phase C (C0).

---

*Full FaVe-side context (why each extension, the wl_stanford modelling, the
roadmap) lives in `../APKEEP_BACKEND.md`.*
