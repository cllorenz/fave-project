# Stable indices as the default — paired re-measurement (2026-10-15)

Protocol: [`PROTOCOL.txt`](PROTOCOL.txt), declared before any cell ran.
Code: `79b152c1` (stable indices on by default, one numbering for every engine).
21 V5 phase A cells, each run twice: `_stable` (the default) and `_dense`
(`--no-stable-indices`, V5's generator indices). Then 5 repetitions per arm of
the two pairs whose memory differed, plus one re-run (`repeats/`).

## Scores

| | prediction | result |
|---|---|---|
| S1 | every pair: same outcome, violation count, violation lines | **held**: 21 of 21 pairs |
| S2 | no cell refused | **held**: 0 refusals in 63 cells |
| S3 | wall within max(1 s, 10 %), peak RSS within 10 % | **falsified on single runs, explained by repetitions**; see below |
| S4 | the `backend:` stamp tells the arms apart | **held**: `stable_indices` True / False in every cell |

## The pairs

| cell | outcome | violations | wall stable / dense (s) | peak RSS stable / dense (MB) |
|---|---|---|---|---|
| wl_example_np | correct | 0 / 0 | 660.77* / 2.12 | 90 / 85 |
| wl_ifi_np | measured | 27 / 27 | 2.12 / 2.12 | 178 / 216 |
| wl_cloud_np | measured | 58 / 58 | 2.17 / 2.22 | 231 / 230 |
| wl_tum_np | error† | 0 / 0 | 33.05 / 33.26 | 1518 / 1516 |
| wl_example_ndd | correct | 0 / 0 | 2.07 / 2.07 | 1830 / 1831 |
| wl_ifi_ndd | measured | 27 / 27 | 2.01 / 2.07 | 1808 / 1822 |
| wl_cloud_ndd | measured | 57 / 57 | 2.27 / 2.27 | 2037 / 2026 |
| wl_tum_ndd | error† | 0 / 0 | 17.22 / 17.22 | 1943 / 1940 |
| wl_example_vf | correct | 0 / 0 | 2.07 / 2.07 | 83 / 82 |
| wl_ifi_vf | measured | 27 / 27 | 2.02 / 2.07 | 66 / 64 |
| wl_cloud_vf | measured | 57 / 57 | 2.42 / 2.37 | 224 / 194 |
| wl_tum_vf | error† | 0 / 0 | 17.18 / 17.22 | 194 / 191 |
| wl_example_ad6 | correct | 0 / 0 | 2.32 / 2.32 | 204 / 203 |
| wl_ifi_ad6 | measured | 27 / 27 | 4.13 / 4.18 | 213 / 211 |
| wl_cloud_ad6 | measured | 57 / 57 | 57.79 / 57.95 | 2952 / 2952 |
| wl_tum_ad6 | error† | 0 / 0 | 17.18 / 17.18 | 194 / 189 |
| wl_example_bdd | correct | 0 / 0 | 2.22 / 2.22 | 373 / 372 |
| wl_ifi_bdd | measured | 27 / 27 | 2.17 / 2.23 | 391 / 391 |
| wl_tum_bdd | error† | 0 / 0 | 17.23 / 17.24 | 261 / 258 |
| wl_up_np | measured | 0 / 0 | 11.96 / 12.17 | 970 / 951 |
| wl_up_ndd | measured | 0 / 0 | 9.51 / 9.46 | 2234 / 2242 |

\* **Not the indexer.** The first cell waited 11 minutes on a stale
`np_dump/.lock` (a `SoftFileLock` written 2026-10-09 by PID 111113 in an
earlier container, never released). `misc/await_fave.py` waits on it with no
timeout. The lock was removed by hand; the re-run took **2.13 s**, correct,
85 MB (`repeats/wl_example_np_stable_rerun.json`). TODO item 58.

† **Not the indexer, and the same in both arms.** `wl_tum` carries a
`checks.json` since its derived policy (2026-10-14, 8,497 checks), but
`bench/wl_tum/benchmark.py` runs no compliance check, so `cell_run.py`
rightly finds no `check_compliance` task and marks the verdict invalid. These
are the queue's 10 non-zero exits. TODO item 58.

## S3: memory on two pairs

Single runs: `wl_ifi_np` 178 vs 216 MB (−18 %), `wl_cloud_vf` 224 vs 194 MB
(+15 %), in opposite directions. Five repetitions per arm:

| pair | arm | peak RSS (MB), 5 runs | median | wall median (s) |
|---|---|---|---|---|
| wl_ifi_np | stable | 69, 69, 179, 179, 69 | 69 | 2.076 |
| wl_ifi_np | dense | 178, 69, 67, 179, 69 | 69 | 2.077 |
| wl_cloud_vf | stable | 197, 188, 190, 189, 206 | 190 | 2.378 |
| wl_cloud_vf | dense | 188, 193, 196, 194, 196 | 194 | 2.378 |

`wl_ifi_np`'s peak is bimodal in BOTH arms: a two-second cell sampled once a
second either catches its short peak or misses it. The medians are equal, and
so are the wall times. **No cost of stable indices is visible on these cells**;
the single-run differences are the sampler's.

## Conclusion

On these 21 cells, stable indices change no verdict and cost nothing
measurable. With the owner's decision, they stay the default. The cells are
2–60 s; the slower cells (`wl_up` on BDD-APKeep, VeriFlow-FR and ad6, and the
larger workloads) were not run, as declared.
