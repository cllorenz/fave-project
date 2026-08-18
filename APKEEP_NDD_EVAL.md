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

### §2.5c — NDD reachability engine + parity gate: NEXT
Build the atom-based NDD reachability on wl_up (single-universe traversal over the
per-field atoms; hop = `AtomizedNDD.and`; source src-IPv6 seed) and gate on exact
parity with the frozen BDD baseline (3660/3660). The sizing (§2.5b) justifies the
investment. NAT-on-NDD stays out of scope (wl_up has none).

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
