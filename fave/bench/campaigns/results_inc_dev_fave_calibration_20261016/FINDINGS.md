# Calibration through FaVe before the D16 run — findings

PROTOCOL.txt (declared 2026-10-16, `408ada25`, code `1b9f092b`). 135 cells,
the first 50 updates of each cell kind of the D16 grid, driven through FaVe
(`driven: fave`), 4 jobs, 12 h cap. Run 2026-10-16 16:15 → 2026-10-17 10:24
UTC, **18.15 h**. Indicative: one repetition, `limit_class` dev, this machine.
Sizing for D16, not a result.

Files: `cells.tsv` (one row per cell, from `analyze.py`), `scores.json`,
`summary/` (from `summarize.py`, D11's), `project.py` → `projections.json`
(the D16 sizing). The raw records are archived (`summary/ARCHIVE.txt`).

## Outcomes

127 cells measured their 50 updates; **8 stopped by a limit, none crashed**:

- **6 memory stops on `wl_tum`**: VeriFlow-FR's single cell, and five of the
  seven BDD-APKeep cells (four in their build, `D_wl_tum_apkeep_s2_coarse`
  after 18 updates). Two different causes, below.
- **2 wall stops**: VeriFlow-FR coarse on `wl_stanford`, S1 and S3 (32 and 33
  of 50 updates). Coarse re-checks all 240 checks after every update, at
  ~1,280 s each; the S2 cell finished in 43,109 s, just under the cap.

Every engine's initial verdicts agree on every workload (6 distinct sets for
7 workloads; `wl_airtel1` and `wl_airtel2` share one).

## Scores

| | prediction | result |
|---|---|---|
| C1 | no cell ends in `error` | **held** (127 measured, 8 by a limit) |
| C2 | no cell stopped by its memory limit | **failed**: 6, all on `wl_tum` |
| C3 | NetPlumber's A medians through FaVe ≤ max(10×, +5 ms) of D11's (its first 50 records) on the 5 switch workloads | **held**, 15 of 15 |
| C4 | NDD-APKeep's build + first check below D11's where D11 had one | **failed**: below on `wl_up` only (39 vs 70 s); 1.6–2.8× above on 5 workloads; `wl_tum` not comparable (D11 had no checks there) |
| C5 | on `wl_up` S2, NetPlumber's median `t_model + t_diff` of re-sends > median `t_update` | **held**: 5.82 vs 1.97 ms (45 re-sends) |
| C6 | APKeep refuses ≤ 3 % of each `wl_up` cell's updates | **held**: 0 refusals in all 14 cells |
| C7 | the queue ends within 24 h | **held**: 18.15 h |

C3 in detail (median ms per update, FaVe vs D11 adapter): `wl_airtel1`
1.08/0.35, 1.91/0.70, 3.12/4.15; `wl_airtel2` 1.08/0.45, 1.75/0.57,
2.89/4.18; `wl_cloud` 0.61/0.01, 0.65/0.04, 0.77/0.30; `wl_stanford`
0.66/0.08, 6.85/4.62, 36.6/101.5; `wl_i2` 76.5/94.8, 23.5/16.4, 2.31/38.1.
FaVe adds well under a millisecond per route command; the S3 cells are
faster through FaVe (link commands), so the two paths do not do the same
work there.

## Finding 1 — the re-send leak (TODO item 60, fixed after the run)

VeriFlow-FR on `wl_tum` built and checked in 14,727 s at 2,964 MB, as item 59
measured, then grew **~90 MB per configuration re-send** and stopped at its
4,096 MB limit after 12 updates. Every engine grew on re-sends (`wl_up` S2:
NetPlumber +4.0, VeriFlow-FR +4.5, BDD-APKeep +10.7 MB per update; NetPlumber
on `wl_tum` S2 reached 5,972 MB against 1,486 MB on S1), while route and link
streams stayed flat. Cause: pybison 0.6.4 leaks every parse tree in the
process that parses, and the in-process harness parsed re-sent configurations
in the measured process. Fixed in `37e59925` (a first fix, `e10c0700`,
forked the client and deadlocked in processes holding a JVM): the client side
of a re-send runs in a worker process, as in real FaVe a client runs as a
process of its own. **This run's re-send memory and times include the leak**:
in the dev probes re-sends through the worker were faster than in-process
(`wl_up` 0.054 against 0.176 s, `wl_tum` 2.17 against 5.76 s, median, with an
engine that keeps nothing).

## Finding 2 — BDD-APKeep's `wl_tum` cells stop on a lazy heap, not on need

The cells run the JVM with its default heap cap (a quarter of RAM, ~15.5 GB).
BDD-APKeep's `wl_tum` build reached 11,811 MB in the one A cell that finished
and 12,292–12,655 MB in the four that stopped at 12,288 MB: the same build,
stopped or not by when the JVM chose to collect. A limit below the heap cap
measures the collector. D16 sizes JVM cells as heap cap + 2.5 GB.

## Finding 3 — two engines' first checks got slower since D11

Build + first check per workload × engine, median over the cells, D11 →
now: NetPlumber, BDD-APKeep and VeriFlow-FR within −9 to +14 % everywhere
except below.

- **NDD-APKeep:** `wl_airtel1` 16.7 → 42.8 s, `wl_airtel2` 17.3 → 39.0,
  `wl_cloud` 8.8 → 14.1, `wl_stanford` 7.2 → 13.5, `wl_i2` 287.6 → 808.0;
  `wl_up` 69.8 → 39.4 (faster). Dev probes through FaVe (worktrees with their
  own jars, 2026-10-17; `wl_airtel1` / `wl_stanford`): `4f2366fe^` (before
  the svlan/dvlan fields) 16.5 / 7.5 s; `63728ebd^` (with them) 16.3 / 7.4 s;
  `63728ebd` (B+C+D) 46.4 / 14.7 s; HEAD 39.2 / 12.1 s. Within `63728ebd`:
  C off (the query cache) 42.2 s; D reverted (NDD's cache-slot fix) 40.5 s.
  So it is **B, FaVe's incremental atom bookkeeping in the NDD-APKeep port**
  (apkeep/FAVE_CHANGES.md §15): it took `wl_tum` from 1,422 to 112 s and
  costs the route-heavy workloads 2–3×. Answers equal in every probe.
- **VeriFlow-FR on `wl_stanford`:** 193 → 1,283 s. Dev probe with tracking on
  (as the cells): the state rule's 1 M-state bound (`9f0a2709`, item 59 option
  c) 1,270 s at 554 MB peak; 4 M states 269 s at 923 MB; unbounded 268 s at
  923 MB; verdicts equal (75 of 240 violated). Without tracking the first
  check takes 0.3 s. On `wl_tum` the bound holds the worst walk at 1.3 GB
  (4.4 GB at 4 M, 55.7 GB unbounded; `9f0a2709`).

## Other numbers D16 needs

- BDD-APKeep's `wl_cloud` build + first check: **1,352 s** (D11: 1,390 s), not
  the 3.24 h from zero of V5 that D11 excluded its other cells for.
- `wl_tum` through FaVe: NetPlumber 22 s, NDD-APKeep 122 s, BDD-APKeep 140–181
  s, VeriFlow-FR 14,727 s (its checks with tracking on).
- Re-sends on `wl_tum` are slow for every engine (NetPlumber S2 median 12.8 s
  per update): the parse and generation of a large configuration, FaVe's cost.
- Stream lengths through FaVe (rule units, links): `wl_airtel1`/`2` 39,500 /
  84; `wl_cloud` 1,741 / 165; `wl_up` 3,570 (3,252 lines, 318 routes) / 590;
  `wl_stanford` 8,792 / 1,468; `wl_i2` 77,841 / 297; `wl_tum` 4,043 (3,794
  lines, 249 routes) / 495.
