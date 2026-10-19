# The cost of APKeep's update-ready structure — findings

PROTOCOL.txt (declared 2026-10-18, `6f16073f`). 12 BDD-/NDD-APKeep pairs × 3
variants, one process each, serial, through FaVe; 2026-10-18 19:16 → 21:52
UTC. One repetition (plus the addendum below): indicative. Raw:
`results.jsonl`, `addendum_airtel2.jsonl`, `run.log`, `stderr.log`.

Build + first check (s; build = APKeep's lazy build forced before the check),
elements of the translation, and the tracked check (the footprint pass):

| workload | engine | elements plain → updatable | plain | updatable | ratio | check untracked → tracked |
|---|---|---|---|---|---|---|
| wl_airtel1 | BDD | 56 → 68 | 1.24 | 1.37 | 1.10 | 0.010 → 0.038 |
| wl_airtel2 | BDD | 53 → 68 | 1.25 | 1.38 | 1.10 | 0.010 → 0.032 |
| wl_cloud | BDD | 103 → 103 | 1,345.8 | 1,336.4 | 0.99 | 1.3 → 6.4 |
| wl_up | BDD | 271 → 443 | 378.2 | 597.1 | **1.58** | 126.3 → 341.6 |
| wl_tum | BDD | 249 → 249 | 136.1 | 135.8 | 1.00 | 34.2 → 42.2 |
| wl_airtel1 | NDD | 56 → 68 | 37.7 | 38.9 | 1.03 | 0.010 → 0.028 |
| wl_airtel2 | NDD | 53 → 68 | 29.2 | 39.2 | **1.34** | 0.012 → 0.031 |
| wl_cloud | NDD | 103 → 103 | 14.4 | 14.4 | 1.00 | 0.06 → 0.12 |
| wl_up | NDD | 271 → 443 | 10.1 | 10.1 | 1.00 | 4.0 → 32.3 |
| wl_stanford | NDD | 348 → 999 | 12.9 | 12.2 | 0.94 | 0.13 → 0.50 |
| wl_i2 | NDD | 242 → 291 | 778.6 | 763.2 | 0.98 | 0.04 → 0.16 |
| wl_tum | NDD | 249 → 249 | 116.2 | 120.7 | 1.04 | 8.1 → 9.9 |

Verdicts equal in all three variants of every pair. Peak RSS within the
JVM's lazy-heap noise (0.6-12.6 GB, no variant systematically higher).

**Addendum** (not in the protocol; the one ratio that contradicted its twin
workload, NDD on `wl_airtel2` against `wl_airtel1`, repeated twice per
variant): plain 28.8 and 30.9 s, updatable 40.7 and 42.9 s. The +34 % is
reproducible, not noise; why `wl_airtel1` (56 → 68 elements as well) shows
+3 % is not known.

## Scores

| | prediction | result |
|---|---|---|
| S1 | same violated count within each pair | **held** |
| S2 | updatable ≥ plain elements everywhere, more on wl_up and wl_tum | **failed**: equal on wl_tum (249 both) — none of the three optimisations applies there |
| S3 | switch workloads within 25 % | **failed**: NDD wl_airtel2 +34 % (reproduced); the other 8 within −6 to +10 % |
| S4 | wl_up and wl_tum > +25 % on both engines | **failed**: only BDD wl_up (+58 %); NDD wl_up and both wl_tum within 4 % |
| S5 | tracked check ≥ updatable check | **held** (1.2-8×) |

## What it says

- The update-ready structure costs build + first check noticeably on **two
  of twelve pairs**: BDD-APKeep on `wl_up` (+219 s, +58 %: 172 more elements,
  APKeep's per-split cost grows with the element count) and NDD-APKeep on
  `wl_airtel2` (+10 s, +34 %). Elsewhere it is within −6 to +10 %.
- `wl_cloud` and `wl_tum` translate to the same elements either way.
- The tracked first check (footprints) costs most on `wl_up`: +215 s on BDD,
  +28 s on NDD; at most +8 s elsewhere.

## Attribution on BDD-APKeep `wl_up` (ATTRIBUTION_PROTOCOL.txt, `64590fe9`)

2026-10-19 05:10 → 05:42 UTC, one process per variant, serial
(`attribution.jsonl`). Build + first check, over the from-zero structure:

| variant | elements | edges | build + first check s | increment |
|---|---|---|---|---|
| plain (from zero) | 271 | 602 | 373.8 | — |
| split: per-ingress-port split only | 278 | 672 | 408.9 | +35.1 s (+9 %) |
| noelide: no pass-through elision only | 436 | 767 | 567.3 | +193.5 s (+52 %) |
| updatable (both; frozen IPv6 a no-op at build) | 443 | 837 | 587.8 | +214.0 s (+57 %) |

| | prediction | result |
|---|---|---|
| A1 | verdicts equal in all four | **held** (0 violated) |
| A2 | split adds more elements than noelide | **failed**: +7 against +165 |
| A3 | split costs more than noelide | **failed**: +35 s against +194 s |
| A4 | the increments add up within 20 % | **held**: 228.6 against 214.0 s (+7 %) |

**The elision is the cost**: keeping `wl_up`'s 165 pass-through filters
costs 194 s of the 214; the per-port split adds 7 elements and 35 s.
