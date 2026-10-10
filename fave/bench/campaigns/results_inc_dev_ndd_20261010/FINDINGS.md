# Findings -- indicative calibration of NDD-APKeep (dev), 2026-10-10

PROTOCOL.txt was committed (e3e9010e) before any cell ran. Indicative only:
limit_class dev, one repetition, this machine; nothing here is reportable.
Raw records: `cells/`, `oracle/`, the P4 check in `verify_port_order/`, and the re-check rule check in `verify_recheck_rule/`; tables generated from them: `table.md`,
`summary.json` (`bench/incremental_table.py`). All 33 timed cells and 3 oracle
runs completed (`run.log`, every rc=0).

## Predictions

| | prediction | outcome |
|---|---|---|
| P1 | every stream agrees across engines, up to the first refusal | **held** -- 11 of 12 streams agree outright; on `wl_example` S1 the three-way comparison stops at batch 0 (APKeep refuses, NetPlumber does not), and BDD- vs NDD-APKeep agree on all 44 batches, refusals included |
| P2 | every NDD-APKeep oracle run passes | **held** -- `wl_ifi`, `wl_airtel1`, `wl_cloud` S2: no sample mismatch, selective == full and full == from-zero at every checkpoint |
| P3 | NDD-APKeep refuses exactly what BDD-APKeep refuses | **held** -- 6 on `wl_example` S1 on both, none elsewhere; `wl_cloud` (no BDD run): 0 |
| P4 | re-checked counts EQUAL BDD-APKeep's on `wl_example` and `wl_airtel1` | **falsified** (cause verified: port iteration order, see below) -- `wl_airtel1` 3,698 vs 3,306 (S1), 4,300 vs 4,166 (S2), 10,086 vs 10,124 (S3); `wl_example` 54 vs 53 (S2), 116 vs 112 (S3), equal on S1 |
| P5 | NDD-APKeep median t_update < 10 ms on `wl_ifi`, `wl_airtel1` S1/S2 | **held** -- 0.66, 1.31, 1.32, 1.64 ms |
| P6 | NDD-APKeep median t_recheck <= BDD-APKeep's on `wl_airtel1` S1, S2 | **falsified on S1** (1.32 vs 1.18 ms), held on S2 (1.77 vs 1.87) |
| P7 | NDD-APKeep completes every `wl_cloud` cell, no error | **held** |

## P4: why the counts differ (verified 2026-10-10 on `wl_example` and `wl_airtel1`)

The prediction stays **falsified**: it assumed the two engines walk the network
in the same order, and they do not. The cause is now verified on the two
workloads P4 named.

**Mechanism.** Both footprints are sound (P2, and the tests' oracle), so a
difference is a difference in precision, not a defect. The reachability walk is
a depth-first search that returns at the first witness, and a footprint records
only what the walk explored, so for a check that holds, the order of the walk
decides the footprint. (For a check that fails the walk is exhaustive and the
footprint is order-independent.) Both checkers loop over `e.getPorts()`, the
only place where they iterate different collections
(`apkeep/.../elements/Element.java`, `getPorts`). BDD-APKeep's is
`port_aps_raw`, a `HashMap`, iterated in hash order of the port names.
NDD-APKeep's is the per-element map in `NddPorts`, a `LinkedHashMap`, iterated
in the order ports were added. Both orders are reproducible from run to run
(Java fixes `String.hashCode`), so the choice between them is between
BDD-APKeep's arbitrary but shared order and the model's order. It is not a
choice between deterministic and non-deterministic.

**Check.** We rebuilt NDD-APKeep outside the tree with one line changed: the
per-element port map in `NddPorts.initPort` is a `HashMap`
(`verify_port_order/variant.diff`). The repo and its jars were not touched. The
adapter was pointed at the rebuilt jar in memory (`verify_port_order/sitecustomize.py`,
which only reassigns `lib_apkeep._APKEEP_JAR`), and we confirmed that the JVM
loaded `NddPorts` from it. NDD-APKeep was then rerun with this calibration's
settings (`--fraction 0.2 --seed 1 --limit-updates 200`;
`verify_port_order/run.sh`, `run.log`, cells under `verify_port_order/cells/`).
Per update, we compared the SET of re-checked checks with BDD-APKeep's cells
from this calibration (`compare.py`, output `compare.txt`). `wl_ifi` was added
as an extra and was not part of P4.

| workload | stream | BDD-APKeep | NDD-APKeep (calibration) | NDD-APKeep, hash order | updates whose re-check set differs from BDD-APKeep's: calibration -> hash order |
|---|---|---|---|---|---|
| `wl_example` | S1 | 166 | 166 | 166 | 0 -> 0 |
| | S2 | 53 | 54 | 53 | 1 -> **0** |
| | S3 | 112 | 116 | 112 | 10 -> **0** |
| `wl_airtel1` | S1 | 3,306 | 3,698 | 3,306 | 36 -> **0** |
| | S2 | 4,166 | 4,300 | 4,166 | 36 -> **0** |
| | S3 | 10,124 | 10,086 | 10,124 | 108 -> **0** |
| `wl_ifi` | S1 | 1,864 | 2,254 | 2,254 | 7 -> 7 |
| | S2 | 2,662 | 1,648 | 1,648 | 18 -> 18 |
| | S3 | 5,636 | 5,772 | 5,636 | 18 -> **0** |

(The columns are re-checks summed over the stream.) In the same port order,
NDD-APKeep re-checks exactly BDD-APKeep's set on every update of `wl_example`
and `wl_airtel1`, and on `wl_ifi` S3. Its verdict changes equal BDD-APKeep's on
all nine streams. On `wl_example` and `wl_airtel1`, port order is the whole
cause. The other candidate noted before the check, BDD-APKeep's
over-approximated IPv4 source seed, leaves no trace there.

**Residual on `wl_ifi` S1/S2: not port order (likely cause, not verified).**
The 25 differing updates do not move when the order changes, and each one
differs in a single direction (`compare_ifi.txt`):
- On S1, NDD-APKeep's set strictly contains BDD-APKeep's on all 7 (e.g. 64 vs 16).
- On S2, BDD-APKeep's set strictly contains NDD-APKeep's on all 18 (e.g. 112 vs 16).

`wl_ifi` is the only workload of the three with ACLs, and the two engines carry
an ACL's effect in different halves of the footprint. BDD-APKeep, under ACL
division, narrows the source seed at an ACL and leaves the forwarded space
alone. NDD-APKeep has one universe: it narrows the forwarded space at an ACL
and leaves the seed as the whole source space. `takeAffected` counts a change
when it meets either half. A seed that ACLs never narrow is met by more
changes, which is consistent with S1. A forwarded space that ACLs do narrow is
met by fewer, which is consistent with S2. This is the same seed-side coarseness
as the `wl_cloud` observation below. Untested: confirming it would need a
footprint that records the narrowed seed on NDD-APKeep.

**Owner decision, open:** whether to equalise the order permanently. Two ways:
- **A `HashMap` in `NddPorts`, the change tested here.** BDD-APKeep and its
  recorded numbers stay as they are.
- **Sorting the ports in both checkers.** FaVe owns the checkers. This changes
  BDD-APKeep's recorded re-check counts.

Either way, a remaining cross-engine difference in selectivity is then a
difference between the backends rather than between walk orders.

## Observations not predicted

- **`wl_cloud` re-checks a third of all checks per update on NDD-APKeep**
  (selectivity 0.32-0.38; NetPlumber 0.001-0.026), and the re-check dominates
  t_total (median 60-64 ms of 78-83 ms). The APKeep footprint design (§4,
  shared with BDD-APKeep) counts a change as affecting a check when it meets
  either the forwarded space or the source seed that arrived at the element.
  The seed constrains only the source address, so it meets every change that
  does not constrain the source -- whether the seed is a prefix or
  unconstrained (corrected 2026-10-10; this said "with an unconstrained seed").
  Coarse, sound, and the same rule BDD-APKeep uses; wl_cloud is the first
  workload where it costs this much, because BDD-APKeep never ran it. Tested
  below ("The re-check rule"): dropping the seed side is sound but does not
  narrow `wl_cloud` much; the footprint itself is the bottleneck.
- **`wl_airtel1` S3 (link updates) costs ~0.55 s per update on both APKeep
  engines** -- the adapter's shadow re-translation of the whole model, not the
  engine (t_recheck ~2.4 ms).
- NDD-APKeep's per-update costs are within a factor of ~1.5 of BDD-APKeep's on
  every stream both ran.

## The re-check rule: forwarded side only (checked 2026-10-10)

**Question.** `Network.takeAffected` re-checks a check when a change `δ` at
element `e` meets either side of the check's footprint at `e`: the forwarded
set that arrived there, or the source seed that arrived there. On NDD-APKeep
no update can change the seed. It is fixed by the query and only intersected
on arrival at the target, and ACLs, forwarding and NAT rules all act on the
forwarded set. So the seed test should be redundant, and testing the forwarded
side alone should stay sound. Two questions: is that so in practice, and what
does it buy?

**Variants**, each a one-line change in `takeAffected`, built outside the tree
(the repo and its jars untouched), and loaded through the in-memory jar
redirect (`verify_recheck_rule/sitecustomize.py`, as for P4). The redirect log
confirms each run used its variant. BDD-APKeep keeps the current rule in all
three.
- **F** (`F.diff`): NDD-APKeep tests the forwarded side only.
- **N** (`N.diff`, negative control): NDD-APKeep ignores rule changes entirely.
  Only link changes still trigger a re-check.
- **V** (`V.diff`, reference point): NDD-APKeep re-checks every check whose
  footprint contains `e`, with no packet-set test at all.

**Soundness.** The NDD-APKeep oracle tests
(`test_incremental_apkeep.py::TestIncrementalNddAPKeep` and
`::TestNddAgreesWithNetPlumber`; `oracle.sh`) give:
- **F:** all 7 pass (`oracle_F.log`), including the `wl_cloud` S2+S3 stream
  with NATs under updates (504 updates, 618 verdict changes, 10,402 re-checks
  against 11,412 under the current rule).
- **N:** 6 of 7 fail (`oracle_N.log`), so the oracle catches a rule that misses
  changes. The one N passes, `test_wl_airtel1_fib_path`, carries no verdict
  change (as `wl_airtel1` S2 in this calibration), so no rule can fail it.

F's three oracle cells (`oracle/`, settings as this calibration's
`oracle/`; checked by `oracle_check.py`, output `oracle_check.txt`) report no
sample mismatch on any update, and selective == full == from-zero at every
checkpoint, on `wl_ifi`, `wl_airtel1` and `wl_cloud` S2. In every timed cell,
F's verdict changes equal the current rule's on every update, and F's
re-check set lies inside the current rule's on every update.

**What it buys** (`compare.py` -> `compare.md`; F's own table, generated:
`table.md`, `summary.json`). Re-checks summed over the stream:

| workload | stream | current rule | F | V |
|---|---|---:|---:|---:|
| `wl_example` | S1 | 166 | 142 (-14%) | |
| | S2 | 54 | 48 (-11%) | |
| | S3 | 116 | 116 | |
| `wl_ifi` | S1 | 2,254 | 1,824 (-19%) | |
| | S2 | 1,648 | 1,510 (-8%) | |
| | S3 | 5,772 | 5,772 | |
| `wl_airtel1` | S1 | 3,698 | 3,698 | |
| | S2 | 4,300 | 4,090 (-5%) | |
| | S3 | 10,086 | 10,086 | |
| `wl_cloud` | S1 | 5,330 | 5,330 | 5,330 |
| | S2 | 5,181 | 4,218 (-19%) | 5,181 |
| | S3 | 4,540 | 4,540 | 4,540 |

- **S3 cannot change**: a link update re-checks by the ports a walk left by,
  not by `δ`.
- **`wl_cloud` S2**: share of checks re-checked per update 0.365 -> 0.297;
  median t_recheck 63.7 -> 46.3 ms, t_total 83.3 -> 65.3 ms. NetPlumber: 0.003.
- **Timings elsewhere**: within run-to-run noise. On `wl_cloud` S1 the median
  t_recheck went 62.7 -> 75.6 ms with the identical re-check set (V: 74.0), so
  differences of that size between single repetitions mean nothing here.

**What V shows.** On all three `wl_cloud` streams, the current rule re-checks
exactly what V does: every check whose walk visited the changed element. The
seed side, as predicted, makes the packet-set test vacuous there. F takes the
seed out, and on S1 and S3 even the forwarded side meets every change at a
visited element.

So most of the coarseness is in the footprint, not in the test applied to it.
A likely reason, not verified: the walk starts from the whole packet space and
explores every branch until it finds a witness. The forwarded set recorded at
an element is therefore everything that reached it from the source, for any
destination, not just the traffic that could reach the probe. Narrowing that
further would take a different footprint, for instance one restricted to what
can reach the probe, rather than a different test.

**Not tested:** BDD-APKeep's counterpart (test the side the changed element
acts on: the seed side for an ACL under the split, the forwarded side
otherwise, both for a NAT); and testing `δ` against the forwarded set
intersected with the seed (finer, but sound only while nothing between `e` and
the probe rewrites the source).

**Owner decision, open:** whether to adopt F for NDD-APKeep (and its BDD
counterpart). It is sound by the checker's semantics and by the oracle, and
small; but on `wl_cloud` it helps S2 only, by a fifth.

**Followed up (2026-10-10):** the footprint redesigns -- a witness footprint
for reachable checks, a dead-end rule for unreachable ones -- built as
selectable modes, off by default (`docs/APKEEP_INCREMENTAL_SCOPE.md` §9) and
measured in `../results_inc_dev_footprints_20261010/FINDINGS.md`: with both,
`wl_cloud` S1 re-checks 5,330 -> 10, verdicts unchanged.
