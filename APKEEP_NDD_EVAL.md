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
`ndd_eval/NDDIPv6DifferentialTest.java`. Profile: IPv6 src(128) + dst(128) +
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

### §2.1 — NOT yet covered: atomize / update
The plan's other §2.1 must-have (`atomize`/`update`, the atom-maintenance our fork's
`updateSplitAP`/`ChangeItem` maps onto) is **deferred and coupled to §2.2**: the only
`AtomizedNDD` construction path is `mkAtomized(field, edges)` over pre-computed atom
ids (there is no NDD→AtomizedNDD converter), and real usage lives in the reference
`application/wan/ndd/verifier/apkeep/{FieldNodeAP,CheckerNDDAP}`. A faithful
atomize/update differential therefore needs the atomization protocol extracted from
that reference (which §2.2 does anyway) — writing it blind risks testing it wrong.

## Next steps (proposed)
1. §2.4 vendor `XJTU-NetVerify/NDD` (subtree + `FAVE_CHANGES`-style changelog); move
   `ndd_eval/NDDIPv6DifferentialTest.java` into its `src/test`.
2. §2.2 extract the vanilla→NDD APKeep recipe from `application/wan/{bdd,ndd}/…`;
   with it in hand, add the **atomize/update** differential (completing §2.1).
3. §2.3 decide (A) re-fork vs (B) engine-swap from the fork-entanglement scoping pass.
