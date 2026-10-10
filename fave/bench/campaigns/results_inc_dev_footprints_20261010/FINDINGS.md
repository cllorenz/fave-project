# Findings -- the selectable footprints (dev), 2026-10-10

PROTOCOL.txt was committed (1ec1e26b) before any cell ran; the code it measures
is 3209124f (fork) and 55ba3c09 (adapter, bench). Indicative only: limit_class
dev, one repetition, this machine; nothing here is reportable. All 84 timed
cells and 3 oracle runs completed (`run.log`, every rc=0).

Raw records: `cells_<mode>/` (modes: default, witness, dead-ends,
witness+dead-ends), `oracle/`, `controls/` (the negative controls).
Generated: `table_<mode>.md`, `summary_<mode>.json`
(`bench/incremental_table.py`, which also compares the two engines per stream);
`compare.md` (`compare.py`: every mode against the default, per cell, and the
predictions scored); `oracle_check.txt` (`oracle_check.py`).

**What the modes are** (`docs/APKEEP_INCREMENTAL_SCOPE.md` §9): **witness** --
a reachable check's footprint is its witness path, with one concrete packet per
hop after the path's last rewrite, and a change counts only if it moves those
packets out of the port the path uses. **dead-ends** -- an unreachable check
ignores a change that only moves packets into a dead end (deny, the drop sink,
an unlinked port that is not its target), and watches that port for a link.
Both off by default.

## Predictions

| | prediction | outcome |
|---|---|---|
| P1 | every mode changes the same verdicts as the default on every update | **held** -- all 63 mode cells, every update; and per mode the two engines agree on all 9 streams they share |
| P2 | the three oracle runs pass | **held** -- `wl_ifi`, `wl_airtel1`, `wl_cloud` S2, NDD-APKeep, witness+dead-ends: no sample mismatch, selective == full and full == from-zero at every checkpoint |
| P3 | witness+dead-ends re-checks no more than the default everywhere | **held** -- on all 21 streams |
| P4 | witness cuts `wl_cloud` S1 and S2 by >= 25% | **held** -- 42%, 47% |
| P5 | witness cuts `wl_airtel1` S3 by >= 30%, both engines | **held** -- 55% on both |
| P6 | dead-ends cuts `wl_ifi` S2 by >= 20%, both engines | **held on BDD-APKeep (22%), falsified on NDD-APKeep (16%)** |
| P7 | no mode raises a median t_recheck by more than 1.5x | **falsified** -- witness on `wl_example` S1: 0.56 -> 1.07 ms (BDD-APKeep), 0.49 -> 1.06 ms (NDD-APKeep); every other cell within 1.5x, most lower |

## Re-checks per stream (summed check lines; change against the default)

| workload | engine | stream | default | witness | dead-ends | both |
|---|---|---|---:|---:|---:|---:|
| `wl_example` | BDD | S1 | 166 | 154 (-7%) | 114 (-31%) | 102 (-39%) |
| | | S2 | 53 | 34 (-36%) | 47 (-11%) | 26 (-51%) |
| | | S3 | 112 | 104 (-7%) | 112 | 104 (-7%) |
| | NDD | S1 | 166 | 154 (-7%) | 114 (-31%) | 102 (-39%) |
| | | S2 | 54 | 34 (-37%) | 48 (-11%) | 26 (-52%) |
| | | S3 | 116 | 104 (-10%) | 116 | 104 (-10%) |
| `wl_ifi` | BDD | S1 | 1,864 | 1,745 (-6%) | 1,054 (-43%) | 935 (-50%) |
| | | S2 | 2,662 | 2,181 (-18%) | 2,070 (-22%) | 1,589 (-40%) |
| | | S3 | 5,636 | 4,700 (-17%) | 5,636 | 4,700 (-17%) |
| | NDD | S1 | 2,254 | 2,042 (-9%) | 1,147 (-49%) | 935 (-59%) |
| | | S2 | 1,648 | 1,377 (-16%) | 1,392 (-16%) | 1,121 (-32%) |
| | | S3 | 5,772 | 4,700 (-19%) | 5,772 | 4,700 (-19%) |
| `wl_airtel1` | BDD | S1 | 3,306 | 641 (-81%) | 2,665 (-19%) | **0** |
| | | S2 | 4,166 | 911 (-78%) | 3,259 (-22%) | **4** |
| | | S3 | 10,124 | 4,564 (-55%) | 10,124 | 4,564 (-55%) |
| | NDD | S1 | 3,698 | 641 (-83%) | 3,057 (-17%) | **0** |
| | | S2 | 4,300 | 911 (-79%) | 3,393 (-21%) | **4** |
| | | S3 | 10,086 | 4,564 (-55%) | 10,086 | 4,564 (-55%) |
| `wl_cloud` | NDD | S1 | 5,330 | 3,081 (-42%) | 2,280 (-57%) | **10** |
| | | S2 | 5,181 | 2,748 (-47%) | 3,160 (-39%) | **466** |
| | | S3 | 4,540 | 1,866 (-59%) | 4,540 | 1,866 (-59%) |

For scale, NetPlumber in the calibration (`../results_inc_dev_ndd_20261010/`,
same settings, another run): `wl_cloud` 10 / 45 / 370, `wl_airtel1`
243 / 295 / 1,804 (S1 / S2 / S3).

**Reading it:**
- **The two modes cover each other's half.** witness narrows the reachable
  checks; dead-ends narrows the unreachable ones; together they reach two
  orders of magnitude on `wl_cloud` S1 (5,330 -> 10, as NetPlumber; its 8
  verdict changes are all among the 10) and on `wl_airtel1` S1/S2 (-> 0 and 4).
  Likely (not verified per update): a rule update there that moves packets of
  an unreachable check moves them into a drop or an unlinked default port,
  which dead-ends ignores, and one that touches a reachable check rarely
  moves its witness packet.
- **S3 (link updates) is witness's alone**: a link change triggers by port,
  where dead-ends has nothing to say; witness cuts it by 7-59% because a
  reachable check then watches only its path's links.
- **Time follows the counts where re-checks dominated.** `wl_cloud` with both
  modes: median t_recheck 76 -> 0.04 ms (S1), 63 -> 0.04 ms (S2), 57 -> 26 ms
  (S3); median t_total 95 -> 17 ms (S1), 84 -> 18 ms (S2). What remains is the
  update itself (~17 ms on `wl_cloud`) -- now the larger part. `wl_airtel1` S3
  stays ~550 ms per update: the adapter's shadow re-translation, not the engine.
- **The cross-engine gap shrinks.** Under witness the two engines re-check
  exactly the same totals on `wl_example`, `wl_airtel1` and `wl_ifi` S3 (in
  the default they differ by port order, see the calibration's P4); with both
  modes also on `wl_ifi` S1 (935 each). `wl_ifi` S2 still differs (1,589 vs
  1,121), where the engines handle ACLs in different universes.

**P7's miss, likely cause (not verified):** on `wl_example` S1 witness re-checks
154 checks against 166, yet the median per-update re-check time doubles, by
~0.5 ms. Building a witness costs a union of the arrived sets, one packet
(a variable-by-variable cube of ~400 variables on BDD, a path walk on NDD) and
a set per hop, on every reachable re-check; on a tiny network that is the same
order as the walk. Absolute numbers are sub-millisecond, and every larger cell
got faster.

**P6's miss:** dead-ends alone cuts `wl_ifi` S2 by 22% on BDD-APKeep but 16% on
NDD-APKeep. The default re-checks fewer there on NDD-APKeep to begin with
(1,648 vs 2,662: one universe, see the calibration's `wl_ifi` residual), so
there was less for the rule to remove; both engines end near each other with
both modes (1,589 / 1,121).

## Soundness evidence

- P1 and P2 above; the per-update verdict equality with the default is the
  same check as the oracle's "selective == full" against an engine already
  verified (the default; calibration P2 and the oracle tests).
- **The oracle tests with the modes on** (`fave/test/test_incremental_apkeep.py`):
  every stream -- `wl_example` S1 (oracle at every update) and S2+S3, `wl_ifi`
  S1 and S2+S3, `wl_airtel1` on the FIB path, `wl_cloud` S2+S3 with NATs under
  updates -- passes with witness+dead-ends on both engines and with dead-ends
  alone on NDD-APKeep (17 tests). The `wl_cloud` stream there: 3,465 re-checks
  with both modes, 10,165 with dead-ends alone, 11,412 by default; 618 verdict
  changes in each.
- **Negative controls** (`controls/`): two variants with one plausible bug each,
  built outside the tree. NW (`NW.diff`): the witness test checks the port a
  change moves packets INTO instead of out of -- fails 6 unit tests and 4 of 6
  oracle tests. ND (`ND.diff`): every port is a dead end -- fails 6 unit tests
  and 5 of 6 oracle tests. Both pass `wl_airtel1` on the FIB path, which
  changes no verdict and cannot fail; NW also passes `wl_example` S2+S3.
- **Not covered by an oracle run with the modes on:** S1 and S3 timed cells
  (covered by P1 only), and BDD-APKeep's `wl_cloud` (not buildable here).

## Owner decisions, open

- Whether to make witness, dead-ends, or both the default. They are sound by
  construction and by every check above, and cut the re-checks by up to two
  orders of magnitude; the cost is a witness per reachable re-check (P7) and
  more code in the footprint path.
- Whether the measurement campaign should report the modes as separate
  configurations of APKeep (as here) or only the chosen default.
