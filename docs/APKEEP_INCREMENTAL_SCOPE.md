# BDD-APKeep and NDD-APKeep, incremental — a scoping pass

**Status: steps 1–3 (BDD) BUILT, 2026-10-10 — see §7; steps 4–5 (NDD) open.**
Answers `INCREMENTAL_PLAN.md` §9 O2
after the owner's decision of 2026-10-09: *NDD-APKeep is the NSDI'25 NDD paper's
system — APKeep's own core with its atom layer replaced by NDD — and BDD-APKeep
and NDD-APKeep work alike, including incremental re-verification.* FaVe's
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
  NDD-APKeep's from-zero verdicts must also equal NDD-flood's and BDD-APKeep's on
  all six benchmarks before any update is trusted.

## 5. Estimate (not measured; a range, not a promise)

| step | content | estimate |
|---|---|---|
| 1 | Core hardening on BDD: rule identity, reference counts, ties (O6), change list returned, Evaluator per batch, delete tests against from-zero per-port predicates | 1–1.5 weeks |
| 2 | BDD-APKeep incremental, tier A: adapter per-rule translation + `-` emission + refusals, links, footprint and affected checks, oracle tests | 1–1.5 weeks |
| 3 | Tier B on BDD: per-device recompute-and-diff (`wl_ifi`, `wl_cloud`); NAT under delete | 1.5–2.5 weeks |
| 4 | NDD-APKeep from zero: atom-layer interface in the fork, port of the reference insert path to the int core, per-field encoders, NAT by `exist`, parity on all six benchmarks | 2.5–4 weeks |
| 5 | NDD-APKeep incremental: delete, merge/re-atomization, the shared footprint, oracle tests, tiers A and B | 1.5–2.5 weeks |
| — | Tier C (structural updates) | deferred; refused and counted |

**Total for tiers A+B on both engines: about 7.5–12 weeks.** The largest
uncertainties: the restored `AtomizedNDD` split path is untested
(`ndd/FAVE_CHANGES.md` §2), int-core reference counting makes leaks silent, and
scale — the NDD-flood engine needed `AtomForwarding` for `wl_i2`'s 77k routes,
and whether incrementally maintained NDD atoms stay small there is exactly what
the paper claims and nobody here has measured.

## 6. Owner decisions and open questions

1. **Order — DECIDED 2026-10-09:** BDD first (steps 1–3; the core and the shared
   machinery are proven on the engine that already runs), then NDD (4–5).
2. **Scope — DECIDED 2026-10-09:** tiers A and B, structural updates frozen and
   refused (counted), tier C deferred.
3. **Naming — DECIDED 2026-10-09:** the faithful port is **NDD-APKeep** (as
   BDD-APKeep is the authors' BDD artifact); FaVe's existing engine is
   **NDD-flood**, in every document that called it NDD-APKeep. *Still open:* the
   NDD-APKeep parts the reference lacks (delete, merge, links, NAT) are FaVe's
   design, and a result should say so — e.g. in its accommodations column.
4. **Provenance stamp — settled 2026-10-09 (owner): unchanged.** NDD-flood cells
   are stamped `impl: authors+fave` with the NDD library as upstream
   (`fave/apkeep/adapter.py:681`), and that is accurate: the authors' code is the
   NDD library (with FaVe's changes, `ndd/FAVE_CHANGES.md`), FaVe's part is the
   verifier on it. That the verifier is not the authors' APKeep is what the name
   NDD-flood says; the stamp need not say it again.
5. **Footprints — DECIDED 2026-10-11 (owner), §9:**
   - **Default:** witness + dead ends, set in the adapter. The coarse footprint
     stays selectable. The modes must be explainable in a paper:
     `APKEEP_FOOTPRINTS.md`.
   - **Campaign:** reports APKeep at the default, plus one ablation table
     (coarse / witness / dead ends / both), `INCREMENTAL_PLAN.md`.
   - **Port order:** left as is. The authors' code is not changed without good
     reason; the finding and its remedies are recorded (§9, "Known
     properties").
   - **Testing the forwarded side only (F):** not adopted, kept documented (§9).

## 7. What was built (2026-10-10): BDD-APKeep takes updates

Steps 1–3 for BDD, by a different route than §3–§4 planned. **The adapter does
not translate an update per rule.** It records every model-construction call
(the batches as snapshots — the aggregator keeps adding to a model object it
already handed over), and an update replays them on a *shadow* adapter with the
one rule or link changed, translates the whole model with the build's own code
(`_translate`, split out of `_build`), and applies the difference to the
engine: `-`/`+` rule strings through APKeep's `updateRule`, edges through
`setLink`. So an update can never be translated differently from a build of the
same model, whatever whole-table decision the translation makes. The tiers of
§3 collapse into one test: **does the update leave the element structure
alone?** If it would need a new element or change an element's type, it is
refused before anything changes and counted by reason (`refused_updates`); the
harness records the refusal and goes on with the model unchanged.

**Structure fixed at build when updates are expected** (`track_affected` before
the build, `_for_updates`): an ingress-qualified device is split into one
element **per ingress port**, not per class of ports with the same rules
(which one update can merge or split), and that split is reused by every later
translation; an IPv6 router stays one; pass-through filters are not elided.
Same answers, more elements. The from-zero oracle is built the same way, from
the live engine's choices (`prepare_twin`) — they derive from the initial model,
not from the update path, and they can represent a model the default
translation refuses (`wl_example`'s `office` with only its in-port-qualified
rule left).

**Two paths.** A plain declared-LPM FIB device — not staged, not a packet filter
or an IPv6 router, one `ForwardElement` or a frozen per-port split of it — is
updated per rule (`_fib_update`): the rule's own `+ fwd` strings, counted per
string over the device's rules. Everything else re-translates the whole model.
Tests check every FIB-path update against the full translation
(`verify_fib_path`).

| piece | where |
|---|---|
| change tuples kept, as BDDs, before PPM update and merge | `Network.updateRule` (fork) |
| ties: removal as if never inserted; identity incl. match; NAT priorities | `Element`, `Rule`, `FilterRule`, `NATElement` (fork) |
| the shared prefix BDD freed while in use | `APKeeper.encodePrefixBDD` (fork) |
| updates without the experiment harness (no file, no hard merge, no forced GC) | `Network.applyUpdates`, `Evaluator.quiet` (fork) |
| links | `Network.setLink` (fork) |
| footprints and affected checks (§4) | `ReachabilityChecker` + `Network.takeAffected` (fork) |
| several networks in one JVM (the from-zero oracle) | `Network.activate` (fork) |
| record, shadow-translate, diff, tie emulation, refusals, FIB path | `APKeepAdapter` |

All fork changes: `apkeep/FAVE_CHANGES.md` §11. **Ties across FaVe rules**
(O6) are handled in the diff: an added string that ties with a live one placed
after it in the new list makes that one be removed and re-added after it, so
the engine ends where a build of the new list would.

**Held to the oracle** (`test/test_incremental_apkeep.py`): selective == full
after every update, full == from-zero at checkpoints, on `wl_example` (S1,
S2+S3) and `wl_ifi` (S1, S2+S3); `wl_airtel1` S2 (0.1%, FIB path, each update
checked against the full translation, oracle at the end). On `wl_ifi` S2+S3
every update changes the **same verdicts as NetPlumber** (188 updates). Fork
fixes against from-zero builds on small networks:
`test/test_apkeep_incremental_core.py`.

**Refusals measured:** none on `wl_ifi`, `wl_airtel1` (sample) and `wl_example`
S2+S3; on `wl_example` S1, 2 of 50 — the deletion of `pgf`'s last route (a
transit packet filter turning terminal: its pipeline's elements depend on its
rules and links, tier C) and its re-insertion. Before the per-port split,
`wl_example` S2+S3 refused 10 of 30 and `wl_airtel1` about 5%.

**Found on the way, fixed in the translation** (no build affected, the full
APKeep suite unchanged):
- a router port whose VLAN no `acl_in`/`acl_out` rule names got **no** ACL
  element and let everything through; FaVe's table drops a miss. Found because
  deleting `wl_ifi`'s only rule for VLAN 464 made NetPlumber and APKeep
  disagree. Every port with a known VLAN now gets its element (deny-all when
  empty);
- an emptied forwarding table turned its device from a first-match
  `FilterElement` into a `ForwardElement` — the old shape inference again. An
  undeclared table is first-match with or without rows.

**Not covered.** `wl_cloud`: BDD-APKeep takes 3.24 h to *build* it (V5), so no
stream runs there; NAT under updates is tested on small networks instead.
Packet-filter pipelines (tier C) refuse what changes their structure. NDD
(steps 4–5): §8 — NDD-APKeep takes the same updates; NDD-flood still refuses
them.

**Costs to state with every number:** per update on the full path, one
whole-model translation, charged to `t_update` — 1–5 ms on `wl_example`/
`wl_ifi`, 0.18 s on `wl_up`, 0.5–0.65 s on `wl_airtel1` (39,600 strings); on the
FIB path a median of 6 ms on `wl_airtel1` (158 updates, engine included). The
update-mode build has more elements than the default one.

## 8. What was built (2026-10-10): NDD-APKeep

Steps 4–5, **owner decision B** (2026-10-10): one core, two atom layers, as §4
proposed — but with the seam where the reference code shows it to be. The
reference (`ndd/.../application/wan/ndd/verifier/`) is not an atom layer under
APKeep's elements: its `FieldNode` merges APKeep's forwarding and ACL elements
and carries each method twice, once on NDDs and once on BDDs (`updateFWRuleBatch`
/ `updateFWRuleBatchBDD`, `InsertACLRule` / `InsertACLRuleBDD`), identical but
for the packet-set type. So the element logic is representation-free, and the
fork's own elements now run on either: their change computation goes through a
small `PredicateOps` interface, their rule encodings through `RuleEncoder`, and
an NDD network keeps its port predicates in `apkeep.ndd.NddPorts` instead of
APKeep's `APKeeper`. Details and file list: `apkeep/FAVE_CHANGES.md` §12.

**Provenance, to be stated wherever NDD-APKeep is reported:**

| part | whose |
|---|---|
| network, topology, elements, change tuples, rule identity, ties, loop check | APKeep (the fork; §2, §7) |
| atom layer on insert: per-field atoms, molecules, splitting, the atom-to-port map, re-atomization as the merge | the NDD authors' reference, ported (`FieldNodeAP.update_ACL`/`update_FW`, `NetworkNDDAP.split_ap_multi_field`, `SplitMap`, `UpdateFieldAP`) |
| removal, links, NAT rewrites (atomized new value, `exist` — the paper's App. F.3, which the reference does not wire), footprints and the selective re-check, several networks per JVM, collecting dead molecules, the re-atomization schedule during updates | FaVe |

**One packet universe.** No ACL division: it exists to stop BDD atomic
predicates multiplying across fields, which per-field atoms avoid, and the
reference has none. A source seed is the source's exact space, intersected at
arrival — what BDD-APKeep does for an IPv6 source (Lever B), here for IPv4 too.

**From zero, check by check** (`fave/test/test_ndd_apkeep.py`; indicative
dev runs, one repetition, this machine):

| workload | checks | violations | NDD-APKeep | NDD-flood | BDD-APKeep |
|---|---:|---:|---|---|---|
| `wl_example` | 10 | 0 | = | = | = |
| `wl_ifi` | 299 | 27 | = | = | = |
| `wl_airtel1` / `wl_airtel2` | 256 each | 0 | = (17 s / 15 s) | = | = |
| `wl_cloud` | 71 | 57 | = (9 s) | = | 3.24 h build (V5), not run |
| `wl_stanford` (faithful) | 240 | 75 | = (7 s) | = | did not finish in 24 h (V5) |
| `wl_i2` (faithful) | 72 | 11 | = (312 s) | = | did not finish in 24 h (V5) |
| `wl_up` | 18,811 | 0 | = (46 s) | = | = |

**Against the reference** (`fave/test/test_ndd_apkeep_reference.py`): the
authors' `NetworkNDDAP`, through its own entry point, and NDD-APKeep build
`wl_airtel1`'s 39,600 routes (as the adapter translates them) in two JVMs. All
261 element ports carry the same destination set — 451,974 maximal prefixes,
compared canonically — every molecule equals its predicate on both sides, and
both end with 16 destination atoms. Build: 17.9 s reference (one batch), 17.1 s
NDD-APKeep (rule by rule). Insertions and destination FIBs only: all the
reference implements (§1). To run it at all, its field set-up was adapted to
the int-node core (`ndd/FAVE_CHANGES.md` §9).

**Updates** (`fave/test/test_incremental_apkeep.py`, every BDD-APKeep stream on
NDD-APKeep too): selective == full after every update, full == from-zero at
checkpoints, on `wl_example` S1 (the same 6 adapter refusals as BDD) and
S2+S3, `wl_ifi` S1 and S2+S3, `wl_airtel1` S2 on the FIB path; `wl_ifi` S2+S3
changes the same verdicts as NetPlumber update by update; and a **`wl_cloud`**
S2+S3 stream (5%: 504 updates, 618 verdict changes, none refused), NATs under
updates on the workload BDD-APKeep cannot build in a test. The Java side (`NddBackendDifferentialTest`) checks the molecule
invariants after every insertion and deletion on random networks, against
from-zero NDD and BDD builds.

**Defects found on the way:**
- **NDD's atomization mixed up fields** (a library bug, also in the reference's
  path): equal-width fields share label variables, so one prefix is one label
  id as a source and as a destination, and the label-to-atoms map was not keyed
  by field. A molecule could then hold another field's atoms — or collapse to
  "everything". On `wl_cloud` (SNAT source prefixes that are also destinations)
  this broke 43,636 molecule invariants at the 1,500th rule, while the verdicts
  still agreed with NDD-flood; a second network in the JVM then answered
  `wl_ifi` with 39 violations instead of 27. Fixed in the library
  (`ndd/FAVE_CHANGES.md` §12); the parity test now asserts the invariants.
- **Dead molecules filled the heap**: NDD collects its atomized node table only
  when full (8M nodes), and each node holds atom-id sets. NDD-APKeep collects
  between updates and between queries (`ndd/FAVE_CHANGES.md` §11).

**Open:** BDD-APKeep's and NDD-APKeep's source seeds both pass a NAT
unchanged (exact only while nothing rewrites the source — the adapter seeds no
such source); with an oracle twin in the JVM, its build's re-atomization also
re-atomizes the network under test (same predicates, new atom ids — no effect
on answers, and timed runs carry no oracle, O3). `wl_berkeley` not run.

## 9. Selectable footprints: witness and dead ends (2026-10-10)

**Why.** The calibration of NDD-APKeep found the selective re-check coarse:
on `wl_cloud` a third of all checks per update, against under 3% for
NetPlumber. Testing only the forwarded side of the §4 footprint was sound but
cut little. A variant that re-checks every check whose walk visited the changed
element matched the current rule exactly on `wl_cloud`: the footprint itself
was too wide, not the test applied to it
(`fave/bench/campaigns/results_inc_dev_ndd_20261010/FINDINGS.md`, "The re-check
rule"). The owner asked for the two redesigns below as selectable variants; since
2026-10-11 both are the default (§6.5). The account written for a paper --
setting, assumptions, definitions, soundness sketches, caveats -- is
`APKEEP_FOOTPRINTS.md`.

**The idea.** "Reachable" is existential, so the two verdicts depend on
different things. A reachable check depends only on its witness; changes
elsewhere, including on the dead ends the walk tried first, can only add paths.
An unreachable check depends on any change that could open a path.

**witness** (for reachable checks). The footprint is the witness: the hops of
the path the walk found, the logical port it left each element by, and the
links it used. After the path's last rewrite, one concrete packet of what
arrived at the target (within the seed and the check's conditions) stands for
each hop; at the rewrite and before it, a hop keeps the sets that arrived
there, because the packet's earlier header would need the rewrite inverted. A
change at a hop counts only if it moves those packets OUT of the port the path
uses; at a rewrite, any change meeting them counts. A link change on the path
counts.
*Sound because* an intact witness still delivers its packet and the walk is
complete, so it would answer "reachable" again. Moving packets into the port,
or anything off the path, cannot remove the witness.

**dead ends** (for unreachable checks). A change that moves packets only into
a dead end -- "deny", the packet filter's drop sink, or ports with no link that
are not the check's target -- is ignored. The port is added to the check's
watched ports, so a link brought up there later still counts.
*Sound because*, with the forwarding monotone (no negation; a rewrite's image
grows with its input), removing packets from a port cannot open a path, and any
new path has to leave the changed element by the port the packets moved into;
from a dead end there is none. A rewrite and an ACL element's permit ports are
never treated as dead ends (their positions in the topology are not named after
the element). A reachable check's explored footprint is kept apart, so the rule
never applies to it.

| part | where |
|---|---|
| one concrete packet of a set, both backends | `PredicateOps.onePacket` (`BddOps`: JDD `oneSat`, free variables 0; `NddOps`: one NDD path, each label's `oneSat`) |
| the witness, built on arrival when asked for | `checker/Witness.java`; the hop and egress stacks in both reachability checkers |
| footprint parts, change ports, the per-mode test, dead ends | `Network` (`Footprint.reached`/`hops`/`targets`, `changed_from`/`changed_to`, `takeAffected`, `deadEnd`) |
| selection | `Network.setFootprintModes`; `LibAPKeep(footprint=...)`; `APKeepAdapter(footprint=...)` (in the configuration stamp); `incremental_run.py`/`incremental_cell.py --footprint witness,dead-ends` (in `head.json`) |

The Java `Network` keeps both modes off. The default, both modes, is set in
the adapter layer (`lib_apkeep.DEFAULT_FOOTPRINT`, on the APKeep engines),
since 2026-10-11 (a53efbe5); `footprint=()` / `--footprint coarse` selects the
coarse footprint of §4. `head.json` and the configuration stamp record the
modes in effect, `[]` meaning coarse, as in every record before.
The coarse footprint is unchanged: the Java suite and the Stanford loop golden
are unchanged, and the coarse re-run matches the calibration. The modes act
only while updates are tracked, so builds and the static campaign are
unaffected. A switch check (`default_switch_check/` in the findings
directory) confirms the new default gives both modes' counts and
`--footprint coarse` the old ones, on `wl_cloud` S1. `apkeep/FAVE_CHANGES.md`
§13.

**Tests.** `OnePacketTest` (both backends: non-empty, inside the set, every
variable decided, deterministic); `test_apkeep_incremental_core.py`
(`Test[Ndd]WitnessFootprints`, `Test[Ndd]DeadEndFootprints`: only the half of
a split path holding the witness packet is reported; moves into the path are
not; before a rewrite the arriving set counts; a dead end is watched for a
link; a port that is the target is no dead end; reachable checks still see
their packets dropped). In `test_incremental_apkeep.py`, every oracle stream
runs at the default (witness+dead-ends) and with the coarse footprint on both
engines, and with dead-ends alone on NDD-APKeep. Two negative controls built outside the tree each fail the unit
tests and 4 or 5 of the 6 oracle tests: a witness test on the to-port instead
of the from-port, and every port a dead end.

**Measured** (indicative, dev, one repetition;
`fave/bench/campaigns/results_inc_dev_footprints_20261010/FINDINGS.md`,
predictions committed before the run). All four modes change the same verdicts
as the default on every update of 84 cells; the three oracle runs pass.
Re-checks with both modes, against the default:

| workload | S1 | S2 | S3 |
|---|---|---|---|
| `wl_cloud` (NDD-APKeep) | 5,330 -> 10 | 5,181 -> 466 | 4,540 -> 1,866 |
| `wl_airtel1` (either engine) | ~3,500 -> 0 | ~4,200 -> 4 | ~10,100 -> 4,564 |
| `wl_ifi` | -50% / -59% | -40% / -32% | -17% / -19% |
| `wl_example` | -39% | -51% | -7% / -10% |

(`wl_ifi` and `wl_example`: BDD-APKeep / NDD-APKeep where they differ.)
NetPlumber on `wl_cloud`: 10 / 45 / 370. On `wl_cloud` the median per-update
re-check falls from 57-76 ms to 0.04 ms (S1, S2) and 26 ms (S3); what remains
is the update itself (~17 ms). witness covers the link stream (S3) alone;
dead-ends contributes most on `wl_ifi` S1. One prediction missed: witness alone
doubles the median re-check time on `wl_example` S1 (~0.5 -> ~1.1 ms), likely
the cost of building witnesses on a network where a walk is as cheap.

**Decided (owner, 2026-10-11, §6.5):** both modes are the default; the
campaign reports the default plus an ablation. Not built: inverting a rewrite
to carry the witness packet before it, and per-probe backward sets for
unreachable checks (B2), which the measurements now give less reason for.

**Known properties, recorded rather than changed (owner, 2026-10-11).**
- **Port order.** The walk returns at its first witness, so a reachable
  check's footprint -- coarse explored part or witness -- depends on the order
  in which an element's ports are tried. BDD-APKeep iterates `port_aps_raw`, a
  `HashMap`, in hash order. NDD-APKeep iterates the per-element map in
  `NddPorts`, a `LinkedHashMap`, in insertion order. Both are reproducible run
  to run. This verifiably explains the engines' different coarse re-check
  counts on `wl_example` and `wl_airtel1`
  (`results_inc_dev_ndd_20261010/FINDINGS.md`, P4). It never affects an
  answer. Under witness the totals happened to agree on those workloads
  (`APKEEP_FOOTPRINTS.md` §5). The authors' code stays as it is; two remedies
  are ready if equal counts are ever needed:
  - a `HashMap` in `NddPorts.initPort`: tested, the patch is
    `verify_port_order/variant.diff`; BDD-APKeep's numbers stay;
  - sorting the ports in both checkers: changes both engines' counts.
- **Testing the forwarded side only (F).** Sound and small: 7/7 NDD-APKeep
  oracle tests and three oracle cells pass, while its negative control fails
  6 of 7. Measured against the coarse footprint, `wl_cloud` S2 drops 5,181 →
  4,218 and other streams by 0–19% (`results_inc_dev_ndd_20261010/FINDINGS.md`,
  "The re-check rule"; patch `verify_recheck_rule/F.diff`). It is not
  measured on the default, where it could touch only the unreachable checks'
  explored footprints. Not adopted: little to gain, one more rule to explain.
