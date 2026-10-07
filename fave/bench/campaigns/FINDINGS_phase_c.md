# Phase C — the long BDD cells

Protocol: `PROTOCOL_phase_c.txt`, declared 2026-10-02, unedited.
**P8 is scored below. P7 is pending** — `bdd × wl_cloud` started
2026-10-07T09:13:08Z under its 24 h limit and is still running.

## P8 — both faithful probes, scored: **HELD**

> *"Both faithful probes land within 1.5× of their 2026-09-26 counterparts, so
> neither faithful cell is re-run. Falsified by: either probe outside 1.5×,
> which triggers its 24 h run."*

Compared at matched rule count, both at `-Xmx8g`, both 120 samples, both ending
`status: deadline` at 3,600 s as designed.

| | baseline | 2026-10-07 | ratio |
|---|---:|---:|---:|
| **stanford** rules | 4,245 / 9,491 | 4,202 / 9,491 | **0.990** |
| **stanford** `ap_num` | 13,759 | 13,498 | **0.981** |
| **i2** rules | 86,709 / 154,974 | 88,058 / 154,974 | **1.016** |
| **i2** `ap_num` | 13,564 | 15,612 | **1.151** |

All four inside 1.5×, the largest being i2's `ap_num` at 1.151×. **The recorded
results stand, cited with their date, their jar and the 1.28× caveat. Neither
faithful cell earns a 24 h run**, which is the decision the probes existed to
make.

`elements` (375 / 260) and `total_rules` are identical across both pairs, so the
models are the same models; `bdd_mem_mib` is 375.7 in all four, which is 4.6% of
an 8 GB heap and is the evidence these cells are not heap-bound.

### What moved, and it is not what the probes were watching

The cost PROFILE shifted sharply even though the progress did not:

| | stanford | i2 |
|---|---|---|
| `ppm_ms` | 653,805 → 380,948 (**0.58×**) | 535,570 → **63,335 (0.118×)** |
| `merge_ms` | 2,909,067 → 2,377,039 (0.82×) | 3,030,484 → 3,115,067 (1.03×) |
| merge/ppm | 4.4× → **6.2×** | 5.7× → **49.2×** |

Per-packet-match work got much cheaper — **8.5× cheaper on i2** — while merge
work did not move at all (1.03×). So §5.3's reasoning is not merely intact, it
is stronger than when it was written: the build is merge-dominated, the merge
cost that keeps the partition small is the dominant cost, and the part that got
faster is the part that was never the bottleneck. A probe that improved the
*other* term by 8.5× and still reached the same 56% of the model is a sharper
argument against the 24 h re-run than §5.3 had available.

**One figure I cannot reconcile, stated rather than smoothed over.** §5.3 quotes
merge/ppm as "7.3× on stanford, 31.4× on i2". Computed from the baselines'
cumulative `merge_ms`/`ppm_ms` above, those come to 4.4× and 5.7×. The `windows`
in the trend carry only rule and AP deltas, not the two timers, so §5.3's
figures must come from a different run or a differently-defined ratio, and I
have not established which. **It does not affect P8**, which is scored on rules
and `ap_num` alone, and it does not affect the direction of the observation
above, which is computed consistently within one pair.

### The first probe pair was void

Recorded in `PROTOCOL_phase_c.txt`: the 2026-10-06 pair ran its full declared
hour and recorded `trend: {"samples": 0}`, because §5.3's command line does not
set `APKEEP_BUILD_PROFILE` and only the sibling driver defaulted it. Not
falsified probes — **unmeasured** ones. Fixed at the driver, re-run here, and
those two result files are deleted and cited nowhere.

## P7 — pending

> *"`bdd × wl_cloud` completes within 24 h, between 15 and 22 h."*

Running since 2026-10-07T09:13:08Z, `-Xmx8g`, 86,400 s / 32,768 MB declared.
At 8.5 minutes: 1,240 of 1,773 rules (69.9%), `ap_num` 80,278, own tail-rate
bound ≥2.35 h, 2.85 GB RSS. Scored when it lands.
