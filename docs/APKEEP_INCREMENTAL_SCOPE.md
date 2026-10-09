# APKeep-BDD and APKeep-NDD, incremental — a scoping pass

**Status: SCOPING, no code (2026-10-09).** Answers `INCREMENTAL_PLAN.md` §9 O2
after the owner's decision of 2026-10-09: *APKeep-NDD is the NSDI'25 NDD paper's
system — APKeep's own core with its atom layer replaced by NDD — and APKeep-BDD
and APKeep-NDD work alike, including incremental re-verification.* FaVe's
`NddReachabilityEngine` is not that system (no atoms, no `updateRule`); it stays
as a differential oracle under an honest name ("NDD-flood").
**Owner:** Claas Lorenz. **Branch:** `updates`. Every claim below carries a
file:line; estimates are estimates, not measurements.

---

## 1. What the paper says, and what the reference code does

**Paper** (Li et al., NSDI'25). App. A.1: APKeep's source, with "its previous
implementation of incremental update of atomic predicates" removed and
re-implemented with NDD's `update` API; Table 2: APKeep +66/−311 LOC. App. F.2,
per update: (1) APKeep's change tuples `(from, to, δ)`, unchanged; (2)
`update(δ, a)`, `a` the atomized predicate of `from`; (3) atomize δ and move it
from `from` to `to` with `diff`/`or` on atomized NDDs. App. F.3 and Fig. 11:
transformers (NAT) by `exist` per field, measured up to 2000 NAT rules.

**Reference code**, in-tree at `ndd/src/main/java/application/wan/ndd/verifier/`
(excluded from the build, `ndd/pom.xml`): `NetworkNDDAP` (atomized) is the
paper's APKeep(NDD); its base `NetworkNDDPred` is the atom-free variant. The F.2
algorithm is there and short (`FieldNodeAP.update_ACL`, :488–564;
`NetworkNDDAP.split_ap_multi_field`, :352–396; `SplitMap`). It is **narrower
than the paper**:

| | reference APKeep(NDD) |
|---|---|
| ACL insert | yes |
| ACL delete | **no** — prints "Remove not implement !" (`NetworkNDDAP.java:178`) |
| forwarding delete | change tuples computed, `remove_set` **never applied** (:202, :252–254) |
| link up/down | **no** — topology fixed (`NetworkNDDPred.java:88`) |
| atom merge | **never** — only a full re-atomization every 1500 ACL rules (:66–79); the BDD twin merges |
| NAT | **unwired** — `encodeNAT` has no caller and loops forever (`common/BDDACLWrapper.java:951`) |
| incremental re-check | **none** — the incremental driver times one ACL insert and never runs the checker (`DPVerifierNDDAPIncre.java:48–75`) |
| fields | the IPv4 5-tuple only |

Further latent defects: `update_FW*` return early on an empty change set and so
drop `copyto_set` (`FieldNodeAP.java:78`, :281); forwarding δ is assumed to be a
single dst edge (:154, :240). It does not compile against the vendored int-node
NDD core: ~400–500 mechanical edits over ~12 files, plus a missing `NDD.toArray`.

**Consequence.** Only the *insert* path of the atom layer can be ported
faithfully. Delete, merge, links and NAT on NDD are FaVe's design and must be
labelled so wherever a result is reported.

## 2. FaVe's APKeep fork (BDD) as the shared core

- **The build is already incremental:** `Network.run` applies every rule string
  through `updateRule` (`Network.java:400–402`). Insert *and* delete exist for
  Forward, ACL, Filter and NAT elements (`identifyChangesInsert/Remove`).
- **The change tuples are computed and discarded** (`Network.java:486–512`); the
  public `updateRule` returns `void` (:434). AP ids are BDD node ids and are re-id'd
  by merges, so anything kept past one update must be a BDD, not an AP id.
- **Delete was never exercised** (no `-` rule in `apkeep/src/test`) and has
  defects that only deletion reaches:
  - equal priorities: insert uses `>` (`Element.java:68`, :117), remove `>=`
    (:176, :206) — an incremental build differs from a from-zero build at every
    tie. Ties are live today: all NAT rules sit at 65535 (`NATElement.java:125`),
    multi-port FIB rules emit one string per port at the same priority
    (`fave/apkeep/adapter.py:1011`);
  - rule identity: `Rule.equals` compares only priority and port
    (`Rule.java:48–55`), so a delete can remove the wrong rule; `NATElement.rule_map`
    is keyed by port and never cleaned;
  - a suspected use-after-free of a shared prefix BDD (`ForwardElement.java:128–129`,
    not verified).
- **No link mutation** after `initializeNetwork` (`addDirectedEdge` private, init only).
- **The checker caches nothing**; `ReachabilityChecker` is built per (source,
  probe) query (`fave/apkeep/lib_apkeep.py:249`). APKeep's own loop check runs in
  `updateRule` (`Network.java:457`) and is charged to the update (D1); for NAT
  rules it is passed the device, not the NAT element (:458 vs :476).

## 3. The adapter: which workloads a per-rule translation covers

Translation is lazy (`_build`, `adapter.py:1878–2069`) and many decisions span a
whole table or model: device type (`+ fwd` vs first-match `+ filter`,
`_is_dst_lpm_table`, :267), ingress demux classes (:1411), NAT shadowing (:236),
`-o` filters resolved against the whole FIB (:535), pass-through elision
(:2598–2652), Stanford/i2 faithful out-stage and admission numbering
(:2678–2998). One rule change can rewrite *other* rules' strings or create and
delete elements.

The tractable middle path is to **freeze** those structural decisions at build
and **refuse** (and count) any update that would change one — the same
refuse-don't-approximate rule as everywhere in M1.

| tier | workloads | translation of an update |
|---|---|---|
| A | `wl_berkeley`, `wl_airtel1/2`, `wl_i2` plain, `wl_tum` (timing only, no checks) | per rule, local: dst-LPM `+ fwd`, priority = prefix length; demux frozen |
| B | `wl_cloud` (first-match + NAT shadowing), `wl_ifi` (router ACL splice) | per device: recompute that device's strings, diff, emit `-`/`+` |
| C | `wl_example`, `wl_up` (packet-filter pipeline, `-o`, elision), `wl_stanford` and `wl_i2` faithful | structural; frozen-and-refused, or a redesign (the plan's 4–6 weeks) |

Note `wl_example` is tier C, so APKeep's small development workload would be
`wl_ifi` (tier B) or a small synthetic tier-A network.

## 4. Design

One core, two atom layers:

- **Shared (our fork):** elements and their change-tuple computation; rule
  identity and reference counts; deterministic tie-breaking (O6); `updateRule`
  returning `(element, from, to, δ)` as BDD/NDD, captured before any merge;
  public `addLink`/`removeLink` (topology only); the adapter's per-rule
  translation and refusals; the affected-check computation.
- **BDD atom layer:** today's `APKeeper` (split, transfer, merge), unchanged.
- **NDD atom layer:** `AtomizedNDD` + `SplitMap` + `split_ap_*` + transfer, ported
  from the reference's insert path (§1); delete and merge (or periodic
  re-atomization preserving `SplitMap`) designed by us. δ must be a **per-field
  NDD**, so the rule encoders are needed per field — the NDD-flood engine's
  `ruleToNDD` already encodes FaVe's whole field set (IPv6, IPv4, VLAN, flags,
  `related`) and can be reused. NAT by `exist` per field (F.3); the NDD-flood
  engine's VLAN rewrite is prior art in-tree.
- **Affected checks, both engines:** each (source, probe) check records a
  footprint while it is answered — the (element, arrival port, arriving set) it
  visited, the set as a BDD/NDD, not atom ids. A change `(e, from, to, δ)` affects
  a check iff some footprint state at `e` meets δ; a link change affects a check
  iff its footprint left by that link's source port. This is VeriFlow-FR's
  footprint idea. Sound with the checker's early exit: a reachable verdict can
  only be lost through a change on its explored part, which includes its witness.
- **Oracle:** as in M1 — selective == full after every update; full == from-zero
  at checkpoints; plus per-port predicates of the incremental build == from-zero
  (compared as BDD/NDD unions, since merges make the partition history-dependent).
  APKeep-NDD's from-zero verdicts must also equal NDD-flood's and APKeep-BDD's on
  all six benchmarks before any update is trusted.

## 5. Estimate (not measured; a range, not a promise)

| step | content | estimate |
|---|---|---|
| 1 | Core hardening on BDD: rule identity, reference counts, ties (O6), change list returned, Evaluator per batch, delete tests against from-zero per-port predicates | 1–1.5 weeks |
| 2 | APKeep-BDD incremental, tier A: adapter per-rule translation + `-` emission + refusals, links, footprint and affected checks, oracle tests | 1–1.5 weeks |
| 3 | Tier B on BDD: per-device recompute-and-diff (`wl_ifi`, `wl_cloud`); NAT under delete | 1.5–2.5 weeks |
| 4 | APKeep-NDD from zero: atom-layer interface in the fork, port of the reference insert path to the int core, per-field encoders, NAT by `exist`, parity on all six benchmarks | 2.5–4 weeks |
| 5 | APKeep-NDD incremental: delete, merge/re-atomization, the shared footprint, oracle tests, tiers A and B | 1.5–2.5 weeks |
| — | Tier C (structural updates) | deferred; refused and counted |

**Total for tiers A+B on both engines: about 7.5–12 weeks.** The largest
uncertainties: the restored `AtomizedNDD` split path is untested
(`ndd/FAVE_CHANGES.md` §2), int-core reference counting makes leaks silent, and
scale — the NDD-flood engine needed `AtomForwarding` for `wl_i2`'s 77k routes,
and whether incrementally maintained NDD atoms stay small there is exactly what
the paper claims and nobody here has measured.

## 6. Questions for the owner

1. **Order:** BDD first (steps 1–3; the core and every piece of shared machinery
   gets proven on the engine that already runs), then NDD (4–5). *Recommended.*
2. **Scope:** tiers A and B, structural updates frozen and refused (counted),
   tier C deferred. *Recommended.*
3. **Labelling:** the NDD insert path is the paper's; delete, merge, links and NAT
   on NDD are FaVe's. Reported as "APKeep-NDD (FaVe: delete/merge/links/NAT)"?
4. **V5:** footnote the `RESULTS.md` "NDD-APKeep" columns now as NDD-flood, or
   when the port can be measured beside it? (Asked 2026-10-09, open.)
