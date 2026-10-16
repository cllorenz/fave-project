# Why NDD-APKeep is slow on wl_tum — findings and measured remedies (2026-10-15)

Asked by the owner: NDD-APKeep took 1,839 s on wl_tum's 8,497 checks where
BDD-APKeep took 142 s (WORKLOAD.md). In-process, one engine at a time, nothing
else on the machine; JVM default heap (~15.5 GB); every run 0 of 8,497
violated. All remedies are **experiments in an out-of-tree worktree**: the
main tree, its jars and the NDD authors' code are unchanged. Patches:
[`A_D_ndd_library.diff`](A_D_ndd_library.diff) (the NDD library, authors'
code), [`B_C_ndd_ports.diff`](B_C_ndd_ports.diff) (FaVe's NDD-APKeep port).
Scripts: `tum_time.py` (build and checks timed apart), `tum_diag.py` (per
check: answer, nodes visited, branches, time), `variantjars.py` (a pytest
plugin pointing the in-process JVM at the variant jars), `variant_tests.sh`.
Raw outputs: `raw/`.

## Results

| run | build (s) | checks (s) | total (s) |
|---|---|---|---|
| BDD-APKeep (reference) | 101 | 35 | 136 |
| NDD-APKeep, stock | 1,422 | 274 | 1,696 |
| + A (visited set in `collectAtoms`) | 474 | 281 | 755 |
| + B (incremental atom bookkeeping) | 112 | 278 | 390 |
| + A + B | 110 | 281 | 391 |
| + B + C (the reference's `and` cache policy) | 112 | 280 | 392 |
| + A + B + D (cache-slot fix), C off | 110 | 301 | 411 |
| **+ A + B + C + D** | **112** | **8.0** | **120** |

Footprint tracking was off; with it on, the stock run took about as long
(1,839 s on 2026-10-14).

## The build: two causes, both in collecting atoms

Thread dumps of the stock build: every sample in rule insertion,
`Network.updateRuleNdd → NddPorts.update → setMolecule →
AtomizedNDD.changeAtoms → collectAtoms`.

- **A — the NDD authors' `collectAtoms` walks the diagram as a tree.** No
  visited set: a node reachable on k paths is visited k times, each with a
  `HashSet.addAll`. Identical upstream. A visited set cannot change the
  result (set union is idempotent). 1,422 → 474 s.
- **B — FaVe's port recomputes whole atom sets per change.** `setMolecule`
  (ours) diffs the full atom sets of a port's old and new molecule on every
  move, three times per cube (source, target, and the accumulator of what
  moved, which grows). Variant B keeps per port, incrementally, a reference
  count per diagram node and an occurrence count per (field, atom): a change
  walks only the nodes the new molecule adds and the old one drops. Exact,
  not an approximation: the reduced diagrams mean an `or` can remove atoms
  and a `diff` add them, so no rule on the moved atoms alone would be. The
  SplitMap follows from it, splits and re-atomization included.
  1,422 → 112 s, about BDD-APKeep's 101 s. With B, A adds nothing (110 s):
  `collectAtoms` is off the build path.

## The checks: same traversal, five times the work per hop — then a cache bug

`tum_diag.py`, per check, BDD against NDD:

- **Answers identical** on all 8,497.
- **Forwarding and filtering identical**: the 704 unreachable checks explore
  everything, and visit exactly the same 352,000 nodes on both engines.
- **More nodes on reachable checks** (1.97 M against 1.37 M; at worst 443
  against 6): the traversal stops at the first hit, and the engines iterate
  ports in different orders -- the cause already found for P4 (HashMap vs
  LinkedHashMap port iteration, results_inc_dev_ndd_20261010), which the
  owner decided to leave as is (2026-10-11). About 1.4× of the gap.
- **Not more atoms — far fewer**: NDD-APKeep has 658 per-field atoms
  (`[1, 1, 6, 2, 80, 2, 266, 254, 1, 1, 22, 22]`), BDD-APKeep 122,998 global
  atomic predicates.
- **Five times the work per node** (107 µs against 20 µs): BDD-APKeep
  intersects atom-id sets; NDD-APKeep computes `AtomizedNDD.and(packets,
  port molecule)` at every hop (as the authors' reference checker does),
  which copies and intersects label sets for every pair of edges. Stack
  samples: nearly all in `AtomizedNDD.andRec`'s label intersection.

The per-query path enumeration asks the same `and`s over and over, which is
what an operation cache is for, and:

- **C — FaVe's port never enabled it.** The authors' `DPVerifierNDDAP`
  switches on AtomizedNDD's `and` cache for the property check and off for
  updates; FaVe's checker left it off. Variant C does what the reference
  does: on when a query starts (kept across queries), off and cleared when
  molecules change (update, port, rewrite, re-atomization). A garbage
  collection clears it inside the library. **Alone: no effect** (280 s);
  three identical passes over the same 200 checks took the same time.
- **D — the authors' cache stores entries in the wrong slot.** In
  `AtomizedNDD.andRec`, and in the int core's `NDD.and/or/not/diff`, a miss
  leaves its slot in the cache's shared field `hashValue`; the recursion
  below overwrites it; the final `setEntry(cache.hashValue, ...)` then
  writes the entry into the slot of the last inner miss, where no lookup for
  it ever looks. Only leaf-level entries land right. Never a wrong result
  (a lookup compares the operands), only misses. Identical upstream. Variant
  D keeps the slot in a local. Alone (C off) no gain on the checks (301 s):
  the plain-NDD caches were not their cost.
- **C + D: 280 → 8.0 s**, faster than BDD-APKeep's 35 s. Per check the
  answers equal BDD-APKeep's and the uncached run's, and nodes visited and
  branches explored equal the uncached run's exactly: the cache only skips
  recomputation.

## Verification of the variants

- Java: the NDD library's tests (29, 3 skipped as in the main tree) and
  APKeep's (38, including `NddBackendDifferentialTest`'s SplitMap invariants
  after splits and re-atomization) pass on A + B + C + D.
- Python, on the variant jars (`variant_tests.sh`, `variantjars.py`; each
  module in its own process, the plugin printing which jar `NddPorts` came
  from): `test_ndd_apkeep.py` 6 passed, `test_apkeep_ndd_fwd.py` 6,
  `test_apkeep_ndd_wlup.py` 2, `test_ndd_apkeep_reference.py` 1 (our port
  against the authors' reference), `test_incremental_m2_apkeep.py` 5,
  `test_incremental_device_removal.py` 22, `test_incremental_apkeep.py` 38.
  The first run of the fwd, wlup and reference modules loaded the MAIN jar
  (`lib_ndd` keeps its own jar path, which the plugin did not set yet); they
  were re-run on the variants. The incremental modules hold every engine to
  a from-zero oracle, so the cache across queries and its clearing at updates
  are covered.
- Per check on wl_tum (`raw/diag_ndd_abcd.jsonl.gz`): answers equal to
  BDD-APKeep's and to the uncached run's on all 8,497; nodes and branches
  equal to the uncached run's.

## NDD-flood

D also fixes the plain-NDD caches NDD-flood uses. On wl_tum it is fast either
way: stock build 0.8 s, checks 2.9 s; with D 0.5 s and 2.6 s; 0 violated.

## For the owner to decide

1. **A and D change the NDD authors' code** (rule: leave upstream alone
   without good reason). D is a plain defect that disables the library's own
   memoization; A is a complexity defect. With B in place, A buys nothing on
   wl_tum; D matters only together with C.
2. **B and C change FaVe's port.** C restores what the reference does. B is
   FaVe's design (the port is FaVe's, labelled so).
3. Whether to adopt them, and in which combination, changes every NDD-APKeep
   number measured so far (V5's NDD-flood cells do not use the atomized
   layer; D would also touch NDD-flood through the plain caches -- not
   measured yet).

## Decided (owner, 2026-10-16)

**B, C and D are applied and the default; A is a selectable option, off by
default; the stock behaviour is not selectable.** D and A are documented in
`docs/ACCOMMODATIONS.md` and `ndd/FAVE_CHANGES.md` §14, §15; B and C in
`apkeep/FAVE_CHANGES.md` §15. A is `ndd_collect_visited`
(`bench/incremental_run.py --ndd-collect-visited`), stamped. Every NDD-APKeep
(and NDD-flood) time measured before 2026-10-16 is of the unfixed code.
