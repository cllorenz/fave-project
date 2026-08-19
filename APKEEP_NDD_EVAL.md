# NDD integration — evaluation log

Running results for the NDD integration of `APKEEP_NDD_PLAN.md` Part 2. Companion to
the frozen BDD baseline (`APKEEP_BDD_BASELINE.md`), which is the differential oracle.

**NDD upstream:** `github.com/XJTU-NetVerify/NDD` @ `c8414b43` (2026-08-05, "Update
per-field mixed label backends"). Java 8 source; builds under our JDK 11; deps
(JavaFX 15, guava, hppc, log4j, junit5) resolve from Maven Central.

---

## §2.0 field-locality GO/NO-GO — MIXED (owner: GO, 2026-08-18)

See `APKEEP_BDD_BASELINE.md` §4.3. wl_up is a stateful multi-field firewall (modal
rule = 3 BDD fields; 39.2% ≤2, 29.4% ≥4) — nearer the paper's §6.6 degradation
regime than orthogonal Stanford/I2, but the two heaviest fields are the 128-bit IPv6
src/dst NDD collapses. Owner decision: **GO**, proceed to §2.1.

## §2.1 — trust the library (differential vs BDD, our profile)

### §2.1a — buildability + upstream suite: PASS
NDD builds in our env (JDK 11 compiling source 8; JavaFX only a single
`javafx.util.Pair` import in the core `AtomizedNDD`, plus the demo/visualization
apps). **Upstream test suite: 17/17 green** (`ComplementedBDDTest`,
`NDDManipulationApiTest` (10), `NDDMixedBackendTest` (4),
`LabelDecisionDiagramBackendFactoryTest`). Buildability risk retired.

Structure note: the repo is ~45 K LOC but the NDD **core** is `org.ants.jndd`
(~19 K), the rest is a vendored JDD copy + `application/`/`experiment/` demos. It
also ships a full **reference APKeep-on-NDD verifier** at
`application/wan/ndd/verifier/apkeep/` (and a BDD twin under `application/wan/bdd/…`)
— the concrete +66/−311 integration the plan's §2.2 wants to study.

### §2.1b — API surface (learned)
`NDD` statics: `initNDD`, `declareField(bits)`/`generateFields`,
`getVar/getNotVar(field,bit)`, `and/or/not/diff/imp/apply/simplify`,
`exist(a,field…)`, `restrict`, `substitute`, `satCount/anySat/allSat`, `ref/deref`,
`toBDD`/`toNDD`, `encodePrefix(field)`, `getBDDEngine()`, `LabelMode {BDD,ZDD,…}`.
Key layout fact: fields **share** a BDD variable template (`sharedVars`, sized to the
widest field); `toBDD`/`toNDD` remap fields by variable *range* (`maxVariablePerField`).
So `getBDDVars(field)` are per-field *label* variables, **not** monolithic-`toBDD`
variables — a differential must respect this (see below).

### §2.1c — 128-bit IPv6 differential-vs-BDD: PASS (7/7)
`ndd/src/test/java/org/ants/jndd/diagram/NDDIPv6DifferentialTest.java` (vendored
subtree; §2.4 done). Profile: IPv6 src(128) + dst(128) +
proto(8) + dport(16). Oracle: NDD ops commute with the `toBDD` homomorphism, compared
by JDD **canonical node-id** equality (exact; robust where `satCount` doubles lose
precision over 2^280).

| test | iters | what it proves |
|---|---|---|
| `declaresTwo128BitFields…` | — | 128-bit fields expose every bit; full-width literal exact ("createVar@128" risk retired) |
| `ipv6PrefixContainmentAndDisjointness` | — | /48 ⊇ /64; sibling /64s disjoint; union ⊂ /48 |
| `booleanOpsCommuteWithToBDD` | 400 | AND/OR/NOT/DIFF/XOR match BDD exactly on random multi-field predicates |
| `existentialQuantificationHasProjectionSemantics` | 200 | exist weakening + idempotence; quantify-all ⇒ TRUE |
| `existOnAnUnmentionedFieldIsIdentity` | 100 | exist of an unconstrained field is a no-op |
| `nddIsCanonicalAcrossConstructionOrder` | 200 | AND-order independence **and** distributivity yield the *same node id* (RONDD canonicity) |
| `deMorganAndAbsorptionHoldOnTheProfile` | 200 | de Morgan, absorption, complement laws |

**Verdict:** the NDD core is trustworthy on our IPv6 profile for the boolean/exist/
canonicity/prefix surface — the operations our adapter emits. No defects found; two
initial failures were test-harness bugs (BDD-cube variable-space mismatch; a missing
`ref` across allocating calls), both fixed.

Two observations worth carrying forward (not defects):
- `NDD.toNDD(int)` NPEs on some inputs (missing 0/FALSE base case and/or a decompose
  precondition) — a robustness gap to pin if we rely on BDD→NDD conversion.
- `AtomizedNDD.or/diff` embed their own BDD self-checks (print "wrong answer") — a
  reassuring built-in differential.

### §2.1 — atomize / update: UNBLOCKED by §2.2, differential pending
The plan's other §2.1 must-have (`atomize`/`update`, the atom-maintenance our fork's
`updateSplitAP`/`ChangeItem` maps onto). §2.2 recovered the real protocol — `AtomizedNDD.atomization(preds, ndd_aps)` takes a
`HashSet<NDD>` of **object**-form port predicates and returns per-field atom pools +
each predicate's per-field atom-id sets (`NetworkNDDAP.UpdateFieldAP`, `:260`); the
incremental path is `getAtomsToSplit*`/`changeAtoms`/`split_ap_*`. Caveat found while
scoping: `atomization` consumes **object** `NDD`/`AtomizedNDD` (not the static int-node
API our §2.1c suite uses), so the port predicates must be built via the verifier's
object-NDD pipeline (`ConvertACLRuleNDD` → `encodeACL`). That construction machinery is
precisely what a **(B) engine prototype builds**, so the atomize/update differential is
best written *with* that prototype (assert: per-field atoms partition each field's
space; each input predicate = `atomizedToNDD` of its assigned atoms == the original),
not reconstructed in isolation.

## §2.2 — the vanilla→NDD APKeep recipe, mapped to our fork

Source: the vendored NDD repo ships **both** an APKeep(BDD) and an APKeep(NDD)
verifier — `ndd/src/main/java/application/wan/{bdd,ndd}/verifier/apkeep/` — so the
"+66/−311" comparison is available in-tree (no separate `XJTU-NetVerify/apkeep`
clone). The change is **localized to the atom layer** (`core/` + `element/` +
`common/BDDACLWrapper`); the drivers and the rest of `common/` are near-identical.

### The seam (what NDD replaces)

| concern | BDD (**== our fork**) | NDD (reference) |
|---|---|---|
| atom pool | `APKeeper.AP : HashSet<Integer>` — one **global** pool of BDD handles, the Π cross-product | `AtomizedNDD.atomsPerField : ArrayList<HashSet<Integer>>` — one pool **per field**, count = **Σ** |
| per-port atoms | `Element.port_aps_raw : Map<String,Set<Integer>>` | `FieldNodeAP.ports_aps : Map<String,AtomizedNDD>` |
| split loop | `APKeeper.addPredicate` → `updateSplitAP` iterates **every element every split** (our 93 % PPM hotspot) | `AtomizedNDD.atomization(preds, out)` (per-field) + `NetworkNDDAP.split_ap_{single,multi}_field` + per-field `SplitMap.ap_ports` |
| rule → predicate | `BDDACLWrapper.ConvertACLRule` → **one BDD over all header bits** | `ConvertACLRuleNDD` → a list of `(field, single-field-BDD)` → `NDD.encodeACL` → a per-field DAG |
| elements | `Element{Forward,ACL,NAT,Filter}` | one type-tagged `FieldNode`/`FieldNodeAP` (**NAT dropped**; `FieldElement` is dead code) |
| checker | two universes (`fw_aps`+`acl_aps`) + `mergeSet` (OR-then-AND cross-product) | **one** `AtomizedNDD`; hop = `AtomizedNDD.and`; arrival = `or`; **no mergeSet** |

The essential swap-list: `HashSet<Integer> AP` → `atomsPerField`;
`port_aps_raw` → `ports_aps:AtomizedNDD`; `addPredicate/updateSplitAP` →
`atomization`+`split_ap_*`; two `APKeeper`s + `Checker.mergeSet` → one atom universe.
The per-field atomization (`AtomizedNDD.atomization`, `ndd`'s `AtomizedNDD.java:380`)
splits **only the atoms of the field(s) a predicate mentions**, which *is* the
D×F → D+F collapse our Phase E sizing measured (~29×), now library-provided.

### Mapping onto OUR fork (what would change, what is additive)

Our fork's atom seam is the same three files — `apkeep/core/APKeeper.java` (`AP`,
`addPredicate`, `updateSplitAP`), `apkeep/elements/Element.java` (`port_aps_raw`,
`updateAPSplit`), `common/BDDACLWrapper.java` (monolithic `ConvertACLRule`) — plus our
value-adds, which are also concentrated there:

1. **IPv6 128-bit fields** (`BDDACLWrapper.srcIP6/dstIP6`, declared last). In NDD these
   become two `declareField(128)` fields in the wrapper's field layout + per-field
   `ConvertACLRuleNDD` encoding. **Additive and a natural fit** — NDD collapses each
   128-bit field to one variable, the tax we pay hardest. §2.1c already proved
   `declareField(128)` + per-field ops are exact. The reference wrapper only has the
   IPv4 5-tuple (`SRC_IP=0…PROTOCOL=4`); we extend the field enum.
2. **`FilterElement`** (our multi-field first-match forward). Maps to a `FieldNode`
   doing forward (LPM trie) + per-rule predicate — the reference already unifies
   forward+ACL in one type-tagged node. Moderate re-expression, not new algorithm.
3. **VLAN-rewrite `NATElement`** (transformers). **The reference DROPS NAT** in the WAN
   NDD port (scaffolding + `encodeNAT` exist but are unwired; the intended mechanism is
   per-field `AtomizedNDD.exist(a,field)` to project+re-inject the rewritten field).
   ⇒ NAT-on-NDD is **unsolved upstream** and is the main risk. **But it is not needed
   for wl_up** (single-universe, 0 NATs — our §2.0/baseline data); it is needed only for
   wl_stanford *faithful-VLAN*. So it can be scoped out of the first NDD milestone.
4. **`ReachabilityChecker`** (our reachability + query-time src-IPv6 seed (Lever B) +
   witness + single-universe mode). Maps to `CheckerNDDAP`/`TranverseNodeAP`. NDD is
   **inherently single-universe**, so Lever B's "no `.sf` split, seed at query time"
   becomes seeding one `AtomizedNDD` — cleaner than today. Witness capture is our
   additive diagnostic to re-add.
5. **Multi-rule-NAT AP-merge fix** ([FIX] in `apkeep/FAVE_CHANGES.md`) is a BDD-atom
   merge bug; NDD's atom maintenance is different, so this fix is **BDD-engine-scoped**
   and does not carry over (it stays on the BDD baseline).

Our **adapter is engine-agnostic** (emits `+ fwd/filter/acl/nat` rule strings + edges)
and does **not** change — confirming the plan's "one shared adapter, two engines".

### §2.3 scoping input — leans (B) engine-swap

The plan asks to decide **(A) re-fork from the authors' NDD-APKeep** vs **(B) keep our
fork and swap the engine** from a scoping pass, not an assumption. The pass says:

- Our entanglement with the atom layer is **real but bounded and localized** to
  `APKeeper` + `Element.port_aps_raw` + `BDDACLWrapper.ConvertACLRule` + the checker —
  exactly the files the reference also rewrote. Everything else (adapter, rule strings,
  topology, drivers) is agnostic/shared.
- Our value-adds (IPv6 fields, `FilterElement`, `ReachabilityChecker` with witness +
  query-seed, the exact-165/3660 modelling) are **adapter- and semantics-facing** and
  would have to be **re-implemented on the authors' structurally-different base**
  (`NetworkNDDAP`/`FieldNode`, not `Network`/`Element`) under path (A).
- The reference gives us the **exact algorithm to port** (atomization, `split_ap_*`,
  `SplitMap`, single-universe checker) — so (B) is not a research task, it is a
  transcription of a known algorithm onto our seam.

⇒ **Preliminary recommendation: (B) engine-swap**, first milestone targeting **wl_up**
(single-universe, no NAT — so the unsolved NAT-on-NDD is out of scope), gated on the
frozen BDD baseline (3660/3660). NAT-on-NDD (for wl_stanford faithful-VLAN) is a
follow-on, and is the one genuinely new piece we'd design (using `exist` per field).
This is a recommendation for owner confirmation, not a committed decision.

## §2.5 — engine prototype: BLOCKER FOUND + a way around it

Confirmed (B) engine-swap, wl_up-first. On starting the prototype, a **major obstacle**
surfaced in the vendored NDD itself:

- **The atomization layer does not compile in this NDD version.** `ndd/pom.xml`
  explicitly **excludes** `AtomizedNDD.java`, `AtomizedNodeTable.java`, and both
  `application/wan/{bdd,ndd}` reference verifiers from the build (`pom.xml:90-95`). The
  `c8414b43` "per-field mixed label backends" refactor made `org.ants.jndd.diagram.NDD`
  **int-node-id based**, which broke `AtomizedNDD` (written against an older *object*-NDD
  API). Un-excluding the two atom files and compiling yields **~100 errors**, pervasive
  `NDD↔int` conversion + missing-symbol mismatches — a substantial rewrite, not a fix.
- Consequence: the plan's premise that NDD "provides the per-field decomposition **as a
  reusable library**" (atomize/update) **does not hold for this vendored version**. The
  working, tested part is the int-based **DD core** (boolean ops, exist, canonicity,
  prefix — §2.1c, all green); the **atom computation** APKeep's fast reachability needs
  is the broken/excluded part.

**The constructive way around it (correctness-first, no atomization needed):** APKeep
uses atoms only as a *speed* optimization — precompute a disjoint atom partition once so a
hop is a bitset intersection. The *semantics* need only plain per-field NDDs: a port's
reachable header set is an NDD, hop = `NDD.and(reached, port_predicate)`, arrival =
`NDD.or`, reachable iff `!= FALSE`. All of that is the **working int-core** (validated in
§2.1c). So a wl_up reachability prototype can be built on the working core with **zero
atomization**, proving (a) the per-field NDD representation gives correct wl_up parity vs
the frozen BDD baseline, and (b) whether the per-field NDD is more compact than the BDD
global partition (`ap_num=14561`). Atomization (for performance) becomes a *later* step,
by either porting `AtomizedNDD` (~100 errors) or implementing per-field atomization
ourselves on the int-core.

This intersected with §2.0 (MIXED field-locality) as an owner decision point. **Owner
chose: invest in atomization first.**

### §2.5a — atomization RESTORED (commit f9e5b2f9): DONE
Ported `AtomizedNDD.java` + `AtomizedNodeTable.java` to the int-core (un-excluded in
`ndd/pom.xml`; `application/wan/**` stays excluded). Faithful representation port —
authors' atom-DAG algorithm unchanged; only the `field` instance member + the bridges
to plain NDD rewired to the int API (`atomizedToNDD`→int via `NDD.addAtField`;
`atomization`/`atomizeNDD`/`collectFieldPreds` read via `getField/getEdgeCount/
getEdgeTarget/getEdgeLabel`; `getTrue/getFalse`→`getAtomizedTrue/getAtomizedFalse` to
stop hiding NDD's int statics). New `NDDAtomizationTest` (the §2.1 atomize/update
differential, now enabled): per-field atoms partition each field (disjoint + cover,
BDD-checked) and each predicate **recombines exactly** (`atomizedToNDD(atomization(P))
== P`, canonical node id) on the 128-bit IPv6 profile. **25 NDD tests green** (17
upstream + 7 §2.1c + 1 atomization). Details: `ndd/FAVE_CHANGES.md` §2. `exist` (NAT,
not needed for wl_up) + incremental split compile but aren't yet directly exercised.

### §2.5b — engine sizing on real wl_up predicates: STRONG GO
`ndd/src/test/java/org/ants/jndd/diagram/NDDWlupSizingTest.java` builds the wl_up rule
hit-predicates as per-field NDDs (dumped from the adapter via
`fave/bench/wl_up/eval/wl_up_dump.py`; all 6560 rules are `+ filter`), atomizes them
with the restored `AtomizedNDD`, and reports the Σ-over-fields atom count. Result:

| | count |
|---|---|
| rules / distinct predicates | 6560 / 3161 |
| per-field atoms | src6=138, dst6=159, proto=4, sport=30, dport=31, rel=2 |
| **Σ (NDD per-field)** | **364** |
| BDD global `ap_num` (baseline) | 14 561 |
| **ratio** | **≈ 40×** |

Recombination verified on 500 predicates (`atomizedToNDD(atomization(P)) == P`).
**This resolves the §2.0 MIXED doubt in NDD's favour:** the joint BDD partition (the
src×dst×… cross-product, 14 561) collapses to a per-field sum (364). Since PPM build
cost scales with partition size, this predicts a large build-cost win, corroborating
and exceeding the plan's ~29× sizing. **Honest caveat:** 364 is over *raw* rule
predicates; the BDD 14 561 is the *post-forwarding* network partition, so the true
engine Σ will be larger (LPM/priority refinement) — but even several-fold refinement
leaves a ~10× win. This is the make-or-break perf gate, and it is GO.

### §2.5c — NDD reachability engine + parity gate: EXACT PARITY ✅
`ndd/src/test/java/org/ants/jndd/diagram/NDDWlupReachabilityTest.java` — an NDD
reachability engine for the full wl_up model, run against the frozen BDD golden
(`fave/bench/wl_up/eval/mat_apk.json`, via line files from `wl_up_dump2.py`):

    NDD pairs=3661  golden=3661  OVER(ndd\bdd)=0  UNDER(bdd\ndd)=0
    EXACT PARITY: 3661 pairs   (= 3660 meaningful, self-pair excluded)

**The (B) engine-swap is correctness-proven on wl_up: the NDD engine reproduces the
BDD baseline pair-for-pair (0 over, 0 under).** Engine design: 269 filter devices
(first-match residual per out_port via `NDD.diff`, priority-sorted ⇒ LPM), 137 sources
emitting their src-IPv6 space (Lever B seed), 137 probe sinks; per-source fixpoint
flood keyed by (device, arrival-port) with **no-hairpin** (a header does not leave via
the port it arrived on) — which reproduces the BDD checker's simple-path semantics.
An initial cut without no-hairpin over-approximated by exactly 29 host-to-self pairs
(the router hairpinning `dst=self` back down the arrival link); UNDER was 0 throughout
(never dropped a real path). Reachability runs on **plain per-field NDDs** (hop =
`NDD.and`, arrival iff `!= FALSE`); the §2.5b atomization is the orthogonal speed layer.

### §2.5d — from-zero build+query time: the win, MEASURED ✅
Both engine variants (same `NDDWlupReachabilityTest`), full wl_up, cold JVM, **each
EXACT PARITY 3661/3661**:

| engine | build | query | build+query |
|---|---|---|---|
| **NDD (plain per-field, hop = `NDD.and`)** | 210 ms | 235 ms | **445 ms** |
| **NDD (atom-based, hop = `AtomizedNDD.and`, 341 atoms)** | 202 ms | 398 ms | **601 ms** |
| BDD baseline (APKeep, `ap_num` 14 561) | ~692 s | — | **~1079 s** |
| NetPlumber (HSA reference) | — | — | ~49 s |

**The NDD engine does the full from-zero build+query in ~0.5 s vs BDD-APKeep's ~1079 s
(~1700–2400×), and ~80× faster than NetPlumber — at exact parity.** The atom-based
path (the §2.5b `AtomizedNDD`) validates the ported atomization end-to-end in
reachability (341 atoms, matching the §2.5b sizing); at wl_up's small scale it is not
faster than plain `NDD.and` (atomization's advantage is asymptotic / for incremental
updates), but it holds parity.

**Honest framing.** The comparison is fair in that both compute the identical full
137×137 matrix from zero with exact parity, but the architectures differ: the BDD 692 s
is APKeep's build of its global atomic-predicate partition (the src×dst×… cross-product
blowup, 93 % PPM), whereas the NDD engine is a direct per-source fixpoint flood that
never materialises that partition. The result *is* the thesis: the per-field
representation removes the blowup, which is why NDD lands with NetPlumber-class (indeed
sub-second) from-zero cost while BDD-APKeep pays ~692 s. Timings are cold single-runs;
the gap dwarfs any warm-up effect.

### §2.5 — status: DONE (prototype). Productionization: §2.5e DONE (wl_up)
The (B) engine-swap is proven on wl_up: **correct** (§2.5c, 3660/3660) and **fast**
(§2.5d, ~0.5 s vs ~1079 s). Remaining to make it a real second backend:
1. ✅ **§2.5e (DONE):** productionized into the adapter as a selectable second engine
   ("one shared adapter, two engines"); wl_up NDD wired into the exactness gate.
2. Extend beyond wl_up: NAT-on-NDD (per-field `exist`) for wl_stanford faithful-VLAN;
   the ACL-division / IPv4 workloads.
3. Incremental updates (the `getAtomsToSplit*`/`changeAtoms` path) if update-time
   (not just from-zero) becomes a target.

### §2.5e — productionize the NDD engine (wl_up): DONE
The §2.5c/d prototype lived in a JUnit test driven by line-file dumps. Productionized
it into the real FaVe path with **no new correctness risk** (the residual/flood/encoders
are the proven code, ported verbatim):

- **Promoted** the engine to a main-source class
  `ndd/src/main/java/org/ants/jndd/fave/NddReachabilityEngine.java`:
  `build(rules, edges)` + `isReachable(srcDev,srcPort,cidr,dstDev,dstPort)` with
  per-source flood caching (plain `NDD.and` hop). In the NDD fat jar (`mvn -f ndd`).
- **Bound** it via JPype in `fave/apkeep/lib_ndd.py` (`LibNDD`), a resident-JVM handle
  parallel to `LibAPKeep`. Both `_ensure_jvm` now use a **union classpath** (apkeep +
  ndd jars) so either engine can boot the process-global JVM and both stay reachable.
- **Selector** in `APKeepAdapter(engine='bdd'|'ndd')`. The model construction is
  engine-agnostic (it already emits the neutral `+ filter` / `dev port dev port` IR —
  the exact strings `wl_up_dump2.py` captured); `_build()` branches at the dispatch:
  BDD → `LibAPKeep.init_in_memory/run`; NDD → `LibNDD.build(all_rules, edges)`. NDD is
  guarded **single-universe** (no ACL/NAT rules) and raises otherwise. `check_compliance`
  dispatches `is_reachable` to the active engine (NDD takes the src CIDR as the query
  seed — Lever B for every source). BDD path byte-unchanged (`run(all_rules)` where
  `all_rules == _dedup(fwd)+acl+nat+filter`, the former inline expression).
- **Gate:** new `fave/test/test_apkeep_ndd_wlup.py` drives the REAL wl_up model through
  the REAL aggregator into `APKeepAdapter(engine='ndd')` and asserts the full
  source→probe matrix equals the frozen BDD baseline `bench/wl_up/eval/mat_apk.json`
  **exactly: 3661 pairs, 0 over, 0 under** (2 passed, ~3.2 s incl. JVM boot + replay).
  Added to `exactness_gate.sh` (which now also builds the ndd jar + regenerates wl_up
  inputs via the new `gen_wl_up_inputs.sh`, byte-identical to the tracked model).
  Standalone JPype smoke (dump → LibNDD → golden): build 389 ms + query 176 ms, parity.

This realizes "one shared adapter, two engines" for wl_up. Not yet productionized:
transformers (NAT/VLAN) and ACL division for the other workloads — future work (item 2).

### §2.6 — extend the NDD engine to all benchmarks
Goal: `engine='ndd'` available for every FaVe benchmark. A scoping pass (replay each
model, capture the adapter's neutral IR) gives the capability matrix:

| benchmark | rules | needs beyond wl_up | status |
|---|---|---|---|
| wl_up | `+filter` IPv6 | — | ✅ done (§2.5e) |
| wl_tum | `+filter` IPv4 5-tuple (5108) | IPv4 in filter encoders | ✅ EXACT (NDD==BDD) |
| wl_stanford P7a | `+fwd` IPv4 (3890) | IPv4 fields + `+fwd` parse | ✅ EXACT (NDD==BDD) |
| wl_i2 | `+fwd` IPv4 (77841) | scale | ⚠️ **obstacle (below)** |
| wl_ifi | `+fwd`+`+acl`+`+filter` IPv4 | ACLElement + src-IP seed | ✅ EXACT (== reachable.json) |
| wl_stanford faithful | + `+nat` + `+acl` (VLAN) | NAT transformer + VLAN field | ✅ EXACT (== NetPlumber; BDD can't finish) |

**Incr 1 (IPv4 forwarding) — DONE for tum + stanford-P7a.** Extended the engine
(`NddReachabilityEngine`) with a canonical field layout that APPENDS IPv4 src/dst
(32-bit) + VLAN after the wl_up fields (indices 0–5 unchanged ⇒ wl_up parity preserved
by construction), IPv4 address encoders (uint32 prefix + cisco inverse-mask wildcard,
built bit-by-bit ⇒ general), and `+ fwd` ForwardElement parsing folded into the same
first-match/LPM residual model as `+ filter`. wl_tum and wl_stanford-P7a reach **exact
parity vs the BDD engine** (differential in-process); wl_up still exact. Gate:
`fave/test/test_apkeep_ndd_fwd.py`.

**wl_i2 (77841 routes) — OBSTACLE.** The true partition is tiny (BDD `ap_num=216`),
but the NDD reachability materializes each port's forwarded-set as a *monolithic
per-field NDD* — a union of thousands of IPv4 prefixes is a large BDD — and the
residual's running `covered` union grows likewise; build did not finish in 9 min
(8 GB heap) / OOM'd at the default heap. An alternative that atomizes the raw rule
hits first also OOM'd: one-shot `AtomizedNDD.atomization` of 77 k distinct prefixes
builds an ~O(n²) *fine* partition (≈ one atom per prefix), never the coarse 216.
**Root cause:** the engine lacks APKeep's *incremental atomic-predicate maintenance*
— represent forwarded-sets as SETS of atom-ids over the minimal partition, splitting
atoms as rules arrive so equivalent ones merge (staying at 216). That is the core of
APKeep-on-NDD (the vendored `application/wan/ndd` reference verifier, excluded/stale).
Correctness is NOT in question — stanford-P7a is the identical `+fwd`/LPM code at 1/20
the scale and is exact; only scale fails. i2 test is opt-in (`FAVE_NDD_SCALE=1`),
skipped in the default gate.

**Incr 2 (ACLs) — DONE (wl_ifi).** `+ acl` has the SAME token layout as `+ filter`
(proto/src/sport/dst/dport at the same indices) — only `t[1]`=acl and `t[5]`=permit/
deny differ — so the ACL predicate reuses `ruleToNDD` verbatim; a permit forwards to
the element's `"permit"` out_port (Cisco first-match ⇒ higher priority wins), a deny
drops. The one new piece is APKeep's ACLElement node naming: an element `E` appears in
the topology as node `E_in`/`E_out`, so the flood strips that suffix (`elementOf`) to
find the residual. The adapter's NDD guard is relaxed to reject only NAT (`+ nat`), not
ACLs. The source's src-IP is the query seed, so source-matching ACLs bite. **wl_ifi NDD
== reachable.json exactly** (`test_apkeep_ndd_fwd.py::test_ifi_matches_ground_truth`).

Now on NDD: **wl_up, wl_tum, wl_stanford-P7a, wl_ifi** (4 of 6). Remaining: wl_i2 scale
(incr 1b) and wl_stanford faithful-VLAN NAT (incr 3).

*Env note:* a yolobox container reset wipes the toolchain (JDK/Maven, and the pybison
build deps m4/bison/flex/python3-dev, and the NP C++ deps). Reinstall before building/
testing; a missing pybison dep segfaults during model replay (looks like a JVM crash but
is not). See [[env-integration-tier-deps]].

**Incr 3 (NAT/VLAN transformer) — DONE (wl_stanford faithful-VLAN); the headline
result.** The faithful model adds per-router VLAN **admission** (`+ acl` with a VLAN
set → constrain the VLAN field) and per-route VLAN **rewrite** (`+ nat <dev> <port>
vlan <dstIP> <plen> <vlanN>` → an inline transformer on the egress port: `exist(VLAN)`
on the dst-prefix-matched part, then set `VLAN=vlanN`; unmatched dst passes unchanged).
The one correctness subtlety: a probe is a host on an access port that **strips the VLAN
tag** on delivery, so a probe accepts traffic regardless of the transit VLAN it carried —
modeled by `exist(VLAN)` on a probe device's header (a no-op for the VLAN-free
benchmarks). With that, **NDD faithful == NetPlumber exactly: 165 pairs, 0 over, 0
under** (`test_apkeep_ndd_fwd.py::test_stanford_faithful_vlan_matches_netplumber`; NP is
the oracle — BDD-APKeep == NP on the tractable configs).

**Why this is the headline:** the faithful VLAN model is precisely where BDD-APKeep's
atomic-predicate cross-product explodes. Profiling the BDD build (`APKEEP_BUILD_PROFILE`,
11 GB heap) shows it **does not finish in 28 min** — at that point only 4884/7278 rules
were applied, with **ap_num ≈ 21,600** (vs ~hundreds for P7a), 4.58M PPM entries, 13.5M
BDD nodes, and time dominated by AP `merge` (920 s) + PPM update (773 s), 92k splits /
19.5M split-touches. The per-field NDD engine builds the same model in **~3 s**. This is
the cross-product blow-up (VLAN × dst) that NDD is designed to eliminate, demonstrated on
the hardest FaVe workload: BDD is intractable, NDD is sub-3-s and exact.

**Incr 1b (wl_i2 scale) — DONE (dst-only) via atomic-predicate forwarding.** The
monolithic per-port residual is intractable for wl_i2 (77k routes: >9 min / OOM even
per-device), though the true partition is only `ap_num=216`. `AtomForwarding`
(`org.ants.jndd.fave`) computes that minimal partition directly with INTEGER interval
arithmetic (no BDDs): rule ranges → 16 232 elementary intervals → per-device binary-trie
LPM → merge intervals by forwarding signature → **216 atoms (== APKeep's ap_num)**.
Reachability floods atom-sets. **Builds in ~0.7 s, exact vs the oracle (72 pairs).** The
adapter routes any pure-`+fwd` FIB (wl_i2, wl_stanford-P7a) here; wl_i2 is now in the
gate (18 passed, 0 skipped).

*wl_i2 reachability is VLAN-redundant, but the PARTITION is not.* i2's source routing is
VLAN-based (`in.*` match `vlan=N`; `out.*` match dst + `rw=vlan:M`); every role has a
distinct IPv4 range, so the collapsed dst-only model reproduces the ground-truth
*reachability* exactly (72 = reachable.json = NP), and faithful-i2 yields the **same 72**.
Its value is the **Σ-vs-Π partition scaling**, and a sizing pass
(`bench/wl_i2/eval/faithful_sizing.py`) shows it IS a genuine NDD win:

- dst-atoms = 216; the 229 admitted VLANs collapse to **37 admission-classes** (VLANs
  admitted by the same `in.*` routers merge).
- **NDD Σ (per-field) = 216 + 37 = 253.** BDD **Π (joint) ≈ 216 × 37 ≈ 7 992** — the
  `in.*` VLAN admission is INDEPENDENT of dst, so it multiplies against the dst partition
  (a cross-product APKeep's single-BDD atoms must materialise). **≈ 32× for NDD.**
- Nuance (and a correction of an earlier under-estimate): the `rw=vlan` rewrite is
  *dst-slaved* (one VLAN per prefix) and does NOT blow up on its own — the *independent*
  `in.*` admission does. This delimits when NDD wins: field INDEPENDENCE, not mere
  presence of a second field.

**Measured (adapter faithful-i2 mode + BDD-APKeep).** The adapter now has a faithful-i2
mode (`_build_i2_faithful`: `out.*` dst-FIB kept as `+fwd`, `rw=vlan` → inline `+nat`,
`in.*` VLAN admission → per-router `+acl iadm_<idx>` on the source→in.X ingress; sources
inject VLAN-unconstrained). Building it in **BDD-APKeep is INTRACTABLE**, exactly like
faithful-stanford: it **did not finish in 28 min** (only 81 161 / 154 920 rules applied),
with **`ap_num` = 19 081 and still climbing** (216 dst → 1 680 @10s → 9 168 @20s →
19 081 @28min), time dominated by PPM updates (~1.2M ms) over the exploding dst×VLAN
partition (`APKEEP_BUILD_PROFILE`). NDD's per-field **Σ = 253**. So the second Σ-vs-Π
result is confirmed and even stronger than the estimate — the independent `in.*` VLAN
admission (plus the per-route `rw=vlan` NATs, which split further) blows up BDD's single
global partition, while NDD keeps dst (216) and VLAN (37) additive. NDD-side reachability
is the tractable dst-atom flood (AtomForwarding: 216 atoms, ~0.7 s, 72 pairs; VLAN is
non-restrictive, so faithful reachability == 72 = NP).

**Two-field NDD engine (completeness).** The general `NddReachabilityEngine` now builds
the FULL faithful-i2 (dst × VLAN) model: its dst-IP FIB is computed by an atom-based
per-port builder (`buildFwdPortPred`: per-device trie-LPM over elementary intervals →
each port's dst set as a bounded union of contiguous ranges, no growing residual), and
the VLAN rides the existing `+nat` rewrite / `+acl` admission / probe-untag path. It
**builds in ~15 s and its reachability is EXACT (72 = reachable.json = NP)** — where
BDD-APKeep does not finish in 28 min. So the demonstration is end-to-end: NDD builds and
solves faithful-i2 tractably; BDD cannot. Gated by
`test_apkeep_ndd_fwd.py::test_i2_faithful_vlan_matches_ground_truth`.

**Takeaway (thesis).** NDD's advantage is field INDEPENDENCE: it appears on wl_up
(IPv6 src×dst×proto×ports), faithful-stanford (ap_num≈21.6k, BDD 28min+), and faithful-i2
(ap_num≥19k, BDD 28min+) — all where BDD's flat AP partition pays a cross-product NDD
avoids. It does NOT appear where a field is functionally slaved (i2's `rw=vlan` alone) or
absent (single-field FIBs), where NDD ≈ BDD.

### §2.6a — how the BDD-APKeep faithful builds stop (profiler analysis)
Both faithful (dst×VLAN) BDD builds were stopped by a **wall-clock `timeout` I imposed
(1700 s ≈ 28 min, GNU `timeout` → rc=124), NOT by an OutOfMemoryError.** Captured
profiler traces (`APKEEP_BUILD_PROFILE`, committed):
`bench/wl_i2/eval/faithful_bdd_capped_profile.jsonl` (170 snapshots) and
`bench/wl_stanford/eval/faithful_bdd_capped_profile.jsonl` (114). Analysis of the i2 trace
(the fuller one):

- **The AP count is NOT converging — it grows ~linearly in rules applied.** Per newly
  applied `+nat` (rw=vlan) rule: a one-time initial burst (~119 APs/rule for the first
  ~63 rules, as the first VLAN rewrites split the whole partition), then a **flat ~2.7
  APs/rule for the entire remaining run** (the per-rule split rate never trends to 0).
  Extrapolating over the ~73.8k `+nat` rules still unprocessed at the cap ⇒ `ap_num`
  heading to **~200k**, no plateau.
- **The apparent time-series "slowdown" (1 680 @10s → 9 168 @20s → 19 081 @28min) is a
  wall-clock artifact, not saturation.** The rule *rate* collapsed from ~7 700 rules/s in
  the `+fwd` phase to **~2 rules/s** in the `+nat` phase, so APs accumulate slowly *in
  time* only because the build is crawling. The cause is the PPM (port-predicate-map)
  cost: `ppm_entries` 346k → 3.93M, **`ppm_ms` 5 258 → 1 198 664** (~20 min) and
  `merge_ms` 2 767 → 488 440 (~8 min) — each AP split re-touches the PPM across all
  elements, so per-rule cost is superlinear in the (growing) partition.
- At the cap: 81 161 / 154 920 rules applied (~52 %), `ap_num` = 19 081 and climbing,
  BDD heap ~0.41 GB used of the 11 GB given (nowhere near OOM).
- **Correction to the §2.6 sizing estimate.** I earlier put Π ≈ 216 dst × 37 VLAN-
  admission-classes ≈ 8k. The real build already exceeds that (19k at half the rules)
  because the per-route `rw=vlan` rewrites introduce many intermediate `(dst,
  current-VLAN)` states beyond the admission classes — so the joint partition (and the
  BDD blow-up) is *larger* than that lower bound, not smaller.

**Net:** "intractable" here means "does not finish in 28 min, with a linearly-growing
partition and superlinear per-rule PPM cost" — a wall-clock cap, not a crash. Whether
BDD-APKeep *eventually* completes (final `ap_num`/time) or hits a real heap ceiling is
left to the planned uncapped runs (APKEEP_NDD_PLAN → "Planned: uncapped BDD-APKeep
faithful measurements").

### §2.6b — uncapped BDD-APKeep faithful measurements (the definitive outcome)
Executes the plan's "Planned: uncapped BDD-APKeep faithful measurements". Ran on the
pinned env, **this box (15 GB RAM, 4 cores)**. The driver is committed —
`bench/faithful_bdd_measure.py` (builds `faithful_vlan=True, engine='bdd'`, times the
BDD/AP build via `single_universe()` separately from the query, reads `ap_num`,
`element_metrics`, peak heap, reachable pairs; profiler on via `APKEEP_BUILD_PROFILE`).

**The binding resource is wall-clock, not RAM — now proven at length.** §2.6a already
noted heap was ~0.41 GB at the cap; the uncapped runs confirm the BDD table
(`bdd_mem`) is pinned at **376–392 MB for the entire run**, at *any* length, on both
models. `bdd_used` (live+dead nodes) oscillates as JDD GCs — e.g. the i2 run reclaimed
15.7M→2.5M nodes mid-build — but never forces a table resize and never approaches the
multi-GB heap. So the honest outcome is **neither (a) completion nor (b) an OOM heap
ceiling**: it is *unbounded wall-clock growth with a flat, tiny heap*. **More RAM would
not help** (the plan's "≥64 GB host" caveat is therefore moot — a bigger box changes
nothing, since the limit is the superlinear PPM cost of an ever-growing partition, a
single-threaded cost).

**faithful-i2 (dst×VLAN) — uncapped, 10 GB heap, profiled 30 s
(`bench/wl_i2/eval/faithful_bdd_uncapped_profile.jsonl`, 109 samples).**
- Ran **53.5 min (3 210 s)** — nearly **2× the old 28-min cap** — then was stopped
  (it would not finish in any practical time; see below). It **decisively surpassed the
  capped snapshot on both axes**: `rules` 82 003 > 81 161, `ap_num` **20 930 > 19 081**,
  still only **52.9 %** of the 154 920 rules applied.
- `ap_num` grows **linearly with no plateau**: ~**2.8 AP per applied `+nat` rule**
  across the whole tail (matching §2.6a's ~2.7). Extrapolated over the ~73 k unapplied
  `+nat` rules ⇒ `ap_num` heading past **~220 k** — vs **NDD's per-field Σ = 253**.
- The `+fwd` phase (77.5 k routes) applies in seconds; the `+nat` (VLAN-rewrite) phase
  then crawls at **~2 rules/s**, PPM-dominated: at the stop, `ppm_ms` = 2 133 376
  (35.6 min) + `merge_ms` = 1 072 060 (17.9 min) — i.e. per-rule cost superlinear in the
  growing partition, exactly the cross-product blow-up NDD avoids.

**Completion frontier — the plan's reduced-slice hedge (Stanford faithful).** Induced
router subsets (`--routers`, reusing `apkeep_convergence._filter_model`), profiled;
these **do complete**, anchoring the extrapolation. `ap_num` is deterministic
(contention-independent); build times marked † ran concurrently with the i2 crawl and
are upper bounds.

| slice | routers | `ap_num` | NAT elems | reachable | peak heap | build |
|---|---|---|---|---|---|---|
| N=2 | bbra + rozb (backbone+1 edge) | 2 574 | 29 | 2 | 460 MB | 34 s (clean) / 67 s † |
| N=3 | + roza (full ro PoP) | 2 661 | 36 | 3 | 455 MB | 110 s † |
| N=5 | + soza,sozb (ro+so PoPs) | 5 697 | 49 | 7 | 634 MB | 940 s † |

`ap_num` and build time grow **superlinearly** as independent VLAN×dst PoPs are added
(N=5's build is ~14× N=2's for ~2× the `ap_num`), so the curve runs *up into* the full
16-router model's `ap_num` ≈ 21.6 k — the point at which the build no longer completes
in a bounded time. So faithful BDD-APKeep **completes at small scale and stops
completing as the independent-field partition grows** — a clean, definitive frontier.

**faithful-stanford (dst×VLAN) — full model, uncapped, 13 GB heap, profiled
(`bench/wl_stanford/eval/faithful_bdd_uncapped_profile.jsonl`, 110 samples).**
- Ran **54 min (3 240 s)** on a clean core, then stopped. **Surpassed the capped
  snapshot on both axes**: `rules` 5 092 > 4 884, `ap_num` **22 249 > 21 582**, with
  **70.0 %** of the 7 278 rules applied — and *still climbing* (no plateau).
- Same verdict as i2: **neither completion nor OOM.** The `+fwd` phase applies ~3 950
  rules in seconds (`ap_num` already 16 087); the `+nat` phase then crawls at
  **0.36 rules/s** (slope ~5.4 AP/rule) and *decays further* (last 15-min window fell to
  ~0.16 rules/s as the slope steepened to ~18) — so the remaining ~2 200 rules are
  effectively unreachable in bounded time.
- The BDD table (`bdd_mem`) is pinned at **exactly 376 MB for the whole 54 min**
  (min = max), free RAM never dropped below ~8.6 GB — **no memory pressure whatsoever**.
  Here `merge_ms` = 2 091 235 (34.8 min) dominates over `ppm_ms` = 1 147 188 (19 min)
  — AP *merge* is the Stanford hotspot vs i2's PPM-update, but both are the same
  cross-product cost.

**Both faithful models therefore give the identical, definitive answer:** run uncapped,
BDD-APKeep **does not complete and does not OOM** — it exhibits *unbounded, superlinear
wall-clock growth of a per-field cross-product partition while the heap stays flat at
~0.38 GB*. This is a stronger result than either of the plan's two anticipated outcomes
(complete / OOM): the wall is algorithmic, not resource, so no bigger box rescues it.

**Σ-vs-Π summary (BDD's joint partition Π vs NDD's per-field Σ).**

| faithful model | BDD-APKeep Π (`ap_num`) | NDD Σ | NDD build |
|---|---|---|---|
| wl_i2 (dst×VLAN) | **≥ 20 930 and climbing** (uncapped 53 min, 53 % of rules; → ~220 k projected) | **253** (216 dst + 37 VLAN) | ~15 s, exact |
| wl_stanford (dst×VLAN) | **≥ 22 249 and climbing** (uncapped 54 min, 70 % of rules; capped was 21 582) | (per-field, ~hundreds) | ~3 s, exact |

The BDD partition is **~80–800×** the NDD Σ and unbounded; NDD keeps the fields additive.
This is the Σ-vs-Π headline the plan set out to make paper-grade — measured, not assumed.

**Reproduction & committed artifacts.** Driver: `bench/faithful_bdd_measure.py` (see its
docstring for exact invocations). From `fave/`, `PYTHONPATH=.`, venv active, jar built:
```
# reduced slice (completes -> anchor):
FAVE_JVM_XMX=6g python3 bench/faithful_bdd_measure.py --bench stanford \
    --routers bbra_rtr,roza_rtr,rozb_rtr --out <slice>.json
# full uncapped (no timeout, profiled) -- stanford | i2:
FAVE_JVM_XMX=13g APKEEP_BUILD_PROFILE=<prof>.jsonl APKEEP_BUILD_PROFILE_MS=30000 \
    python3 bench/faithful_bdd_measure.py --bench stanford --out <full>.json
```
Committed traces (this run): `bench/wl_i2/eval/faithful_bdd_uncapped_profile.jsonl`
(109 samples, 53.5 min), `bench/wl_stanford/eval/faithful_bdd_uncapped_profile.jsonl`
(110 samples, 54 min), and the completing anchors
`bench/wl_stanford/eval/faithful_bdd_pop_N{2,3,5}.json` (+ their `_profile.jsonl`).
Caveat: the reduced-slice **build times** were measured under concurrent load (the i2
crawl shared CPU) and are upper bounds; `ap_num` is deterministic and load-independent.

### §2.6 status: all 6 benchmarks have NDD coverage; 6/6 exact + gated
wl_up, wl_tum, wl_stanford-P7a, wl_ifi, **wl_stanford faithful-VLAN**, **wl_i2** — all
exact and in the exactness gate (18 passed, 0 skipped). The NDD multi-field advantage is
proven on wl_up (0.5 s vs 1079 s) and faithful-stanford (BDD intractable, ap_num≈21.6k,
vs NDD 3 s). Optional follow-on: faithful-i2 (dst×VLAN) as a second Σ-vs-Π data point,
with a BDD-APKeep faithful-i2 comparison.

## §2.4 — vendor NDD: DONE
`XJTU-NetVerify/NDD` @ `c8414b43` vendored as a git subtree at **`ndd/`** (from a
FaVe-owned fork), with `ndd/FAVE_CHANGES.md` (vendoring hygiene). The IPv6
differential test now lives in `ndd/src/test/...` and runs in the subtree's own
`mvn test`: **24 tests green** (17 upstream + 7 ours).

## Next steps (proposed)
1. **atomize/update differential** (completes §2.1) — now unblocked by §2.2: exercise
   `AtomizedNDD.atomization` + `getAtomsToSplit*`/`changeAtoms` on our IPv6 profile and
   assert the per-field atoms partition the space and recombine to the input predicates
   (differential vs a BDD reference).
2. §2.3 owner decision: confirm **(B) engine-swap** (see §2.2 scoping) vs (A) re-fork.
3. Under (B): first NDD milestone = wl_up (single-universe, no NAT), gated on the frozen
   BDD baseline (3660/3660). Follow-on: NAT-on-NDD (per-field `exist`) for wl_stanford
   faithful-VLAN.
4. Pin the `NDD.toNDD(int)` NPE robustness gap (missing 0/FALSE base case).
