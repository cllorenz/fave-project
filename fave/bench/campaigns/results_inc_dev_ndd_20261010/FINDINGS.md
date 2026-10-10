# Findings -- indicative calibration of NDD-APKeep (dev), 2026-10-10

PROTOCOL.txt was committed (e3e9010e) before any cell ran. Indicative only:
limit_class dev, one repetition, this machine; nothing here is reportable.
Raw records: `cells/`, `oracle/`; tables generated from them: `table.md`,
`summary.json` (`bench/incremental_table.py`). All 33 timed cells and 3 oracle
runs completed (`run.log`, every rc=0).

## Predictions

| | prediction | outcome |
|---|---|---|
| P1 | every stream agrees across engines, up to the first refusal | **held** -- 11 of 12 streams agree outright; on `wl_example` S1 the three-way comparison stops at batch 0 (APKeep refuses, NetPlumber does not), and BDD- vs NDD-APKeep agree on all 44 batches, refusals included |
| P2 | every NDD-APKeep oracle run passes | **held** -- `wl_ifi`, `wl_airtel1`, `wl_cloud` S2: no sample mismatch, selective == full and full == from-zero at every checkpoint |
| P3 | NDD-APKeep refuses exactly what BDD-APKeep refuses | **held** -- 6 on `wl_example` S1 on both, none elsewhere; `wl_cloud` (no BDD run): 0 |
| P4 | re-checked counts EQUAL BDD-APKeep's on `wl_example` and `wl_airtel1` | **falsified** -- `wl_airtel1` 3,698 vs 3,306 (S1), 4,300 vs 4,166 (S2), 10,086 vs 10,124 (S3); `wl_example` 54 vs 53 (S2), 116 vs 112 (S3), equal on S1 |
| P5 | NDD-APKeep median t_update < 10 ms on `wl_ifi`, `wl_airtel1` S1/S2 | **held** -- 0.66, 1.31, 1.32, 1.64 ms |
| P6 | NDD-APKeep median t_recheck <= BDD-APKeep's on `wl_airtel1` S1, S2 | **falsified on S1** (1.32 vs 1.18 ms), held on S2 (1.77 vs 1.87) |
| P7 | NDD-APKeep completes every `wl_cloud` cell, no error | **held** |

## P4: why the counts differ (likely cause, not verified)

Both footprints are sound (P2, and the tests' oracle), so a difference is a
difference in precision, not a defect. The reachability walk stops at the first
witness and records only what it explored. It iterates an element's ports in
the order its port map yields them: a `HashMap`'s hash order on BDD-APKeep
(`Element.port_aps_raw`), insertion order on NDD-APKeep (`NddPorts`, a
`LinkedHashMap`). Different orders explore different parts before the witness,
hence different footprints and re-check sets. Not verified by equalising the
orders; doing so (a `HashMap` in `NddPorts`) would make the two engines' footprints
comparable and is a one-line change, left for the owner to weigh against
keeping NDD-APKeep's order deterministic. The prediction assumed the walk
order was shared; it is not.

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
