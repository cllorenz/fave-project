# Findings: VeriFlow-FR's footprints (dev), 2026-10-11

`PROTOCOL.txt` was committed (`d2c0844a`) before any cell ran. The code it
measures is `647a97f3` (engine, adapter, tests) and `6bd65a0c` (harness flag).

This run is indicative only: limit_class dev, one repetition, this machine, so nothing
here is reportable. All 48 timed cells and 3 oracle runs completed (`run.log`, every
rc=0).

**One deviation:** during the run I developed M2 in a separate git worktree. That
work used a single core at a time, at most, alongside the cells, and none of it
touched the tree the cells imported. The timings are indicative regardless, and
the counts and verdicts are unaffected.

Raw records: `cells_<mode>/` (modes coarse, witness, dead-ends,
witness+dead-ends) and `oracle/`. Generated: `compare.md` (`python3 compare.py >
compare.md`), which holds the table and the scored predictions below.

**What the modes are** (`docs/VERIFLOW_FOOTPRINT_SCOPE.md` §4):
- **witness:** a (source, probe) pair the walk delivered to watches one path,
  with one concrete packet per hop, carried back through the rewrites.
- **dead-ends:** an undelivered pair ignores changes that send packets nowhere,
  and links going down.

Either mode reports pairs instead of whole sources. Coarse is VeriFlow-FR's
default, until the owner decides.

## Predictions

| | prediction | outcome |
|---|---|---|
| P1 | every mode changes the same verdicts as coarse on every update | **held**: all 36 mode cells |
| P2 | the three oracle runs pass | **held**: wl_ifi (56 updates, 2 full checkpoints), wl_airtel1 and wl_cloud (200, 4 each) |
| P3 | both modes re-check no more than coarse on every stream | **held**: all 12 |
| P4 | wl_airtel1 S1/S2, both: re-checks ≤ 1%, median t_recheck ≤ 10% of coarse | **held**: 0 and 4 of 51,200 re-checks; t_recheck 606 → 0.01 ms |
| P5 | wl_ifi S1/S2, both: re-checks ≤ 40% of coarse | **half**: S1 31%; **S2 48%, falsified** |
| P6 | wl_airtel1 S3, witness alone: ≥ 30% fewer re-checks | **held**: 77% fewer |
| P7 | both: median t_update ≤ 3× coarse on every stream | **falsified** on wl_ifi S2 (3.67×) and S3 (3.02×); in absolute terms 0.06 → 0.23 ms and 0.03 → 0.10 ms |
| P8 | wl_airtel1 S1/S2, both: median t_total below coarse | **held**: 607 → 0.92 ms, 601 → 0.96 ms |
| P9 | wl_ifi S1, dead-ends alone: ≤ 70% of coarse | **held**: 45% |

## Re-checks per stream (summed check lines; change against coarse)

| workload | stream | coarse | witness | dead-ends | both | t_total median, coarse → both |
|---|---|---:|---:|---:|---:|---|
| `wl_example` | S1 | 292 | 258 (−12%) | 126 (−57%) | 112 (−62%) | 2.22 → 0.19 ms |
| | S2 | 41 | 20 (−51%) | 30 (−27%) | 14 (−66%) | 2.14 → 1.02 ms |
| | S3 | 100 | 76 (−24%) | 92 (−8%) | 72 (−28%) | 1.89 → 1.79 ms |
| `wl_ifi` | S1 | 2,670 | 2,275 (−15%) | 1,213 (−55%) | 818 (−69%) | 0.07 → 0.10 ms |
| | S2 | 2,981 | 2,234 (−25%) | 2,187 (−27%) | 1,440 (−52%) | 2.21 → 2.46 ms |
| | S3 | 5,624 | 3,856 (−31%) | 4,217 (−25%) | 2,449 (−56%) | 1.88 → 1.81 ms |
| `wl_airtel1` | S1 | 51,200 | 9,200 (−82%) | 42,000 (−18%) | **0** | **607 → 0.92 ms** |
| | S2 | 51,200 | 9,204 (−82%) | 42,000 (−18%) | **4** | **601 → 0.96 ms** |
| | S3 | 34,272 | 7,962 (−77%) | 31,239 (−9%) | 4,929 (−86%) | 600 → 561 ms |
| `wl_cloud` | S1 | 13,210 | 1,860 (−86%) | 11,360 (−14%) | **10** | **223 → 0.12 ms** |
| | S2 | 7,083 | 1,653 (−77%) | 5,639 (−20%) | **136** | **130 → 0.15 ms** |
| | S3 | 7,712 | 1,662 (−78%) | 7,315 (−5%) | 1,016 (−87%) | 141 → 4.3 ms |

For scale, the same streams elsewhere:
- **APKeep with both modes** (`../results_inc_dev_footprints_20261010/`): `wl_cloud` 10 / 466 / 1,866, `wl_airtel1` 0 / 4 / 4,564.
- **NetPlumber:** `wl_cloud` 10 / 45 / 370.

**Reading it:**
- **The scope's two layers show plainly** (§2 there):
  - Fewer re-checked pairs saves time only when whole SOURCES drop out, because a
    re-check walks a source in full.
  - Witness alone cuts `wl_airtel1` S1's re-checks by 82%, yet t_recheck
    stays at 604 ms: the pairs left still cover all 16 sources.
  - Only with both modes does no source stay marked, and then the walk
    disappears: 607 → 0.92 ms per update.
  - The same holds on `wl_cloud` S1/S2.
- **Both modes are needed together**, as on APKeep. Witness narrows the
  delivered pairs and dead ends the undelivered ones, and a source drops out only
  when both halves are quiet.
- **Link updates (S3) keep most of the time.** On `wl_airtel1` S3, 4,929 pairs
  across most sources remain: a link going down on a path is a real hit.
  S3 is where the per-target re-walk that the scope left out (§4.4) would help.
- **The small workloads cost a little more per update.** The per-pair test runs
  in Python, so `wl_ifi`'s median t_update rises 0.06 → 0.23 ms (P7). On these
  workloads that is the same order as the re-check itself, so t_total barely
  moves. On the workloads where re-checks dominate, it is noise.
- **wl_ifi S2 (P5):** 48%, not ≤ 40%. A random 20% of `wl_ifi`'s ACL rules
  deleted and re-added touches many delivered paths, because an ACL rule usually
  meets a witness packet's source range. My prediction assumed the dead-end
  effect seen on S1 (deletes only, of mostly permits) would carry over.

## For the owner

- **VeriFlow-FR's default footprint is your decision** (scope §4.5). On this
  evidence both modes behave as on APKeep: verdicts unchanged everywhere, the
  oracle holding, and re-checks down by two orders of magnitude where updates
  rarely change verdicts. My recommendation is to make both modes the default, as
  on APKeep, and to keep coarse as the ablation row. Until you decide, coarse
  stays the default, so the D11 run would run VeriFlow-FR at coarse, with the
  modes as ablation rows.
