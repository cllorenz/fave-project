# Findings -- indicative calibration of NDD-APKeep (dev), 2026-10-10

PROTOCOL.txt was committed (e3e9010e) before any cell ran. Indicative only:
limit_class dev, one repetition, this machine; nothing here is reportable.
Raw records: `cells/`, `oracle/`, and the P4 check in `verify_port_order/`; tables generated from them: `table.md`,
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
  either the forwarded space or the source seed that arrived at the element,
  and with an unconstrained seed every change at a visited element meets it.
  Coarse, sound, and the same rule BDD-APKeep uses; wl_cloud is the first
  workload where it costs this much, because BDD-APKeep never ran it.
- **`wl_airtel1` S3 (link updates) costs ~0.55 s per update on both APKeep
  engines** -- the adapter's shadow re-translation of the whole model, not the
  engine (t_recheck ~2.4 ms).
- NDD-APKeep's per-update costs are within a factor of ~1.5 of BDD-APKeep's on
  every stream both ran.
