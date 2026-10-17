# BDD-APKeep's wl_cloud cells, trialled before D16 — findings

PROTOCOL.txt (declared 2026-10-17, `fd9210ee`, code `ab8d8e17`). 8 cells, the
first 50 updates each, through FaVe; 2026-10-17 18:54 → 20:54 UTC (2.0 h).
Indicative, one repetition.

| cell | build + first check s | peak RSS MB | updates | mean / median s per update |
|---|---|---|---|---|
| A S1 | 1,316 | 2,533 | 50 | 11.03 / 4.07 |
| A S3 | 1,337 | 3,076 | 50 | 0.21 / 0.19 |
| B S2 batch 10 | 1,373 | 2,945 | 5 batches | 88.5 / 82.4 per batch |
| C S4 | 1,378 | 4,186 | 50 | 89.0 / 13.4 |
| D S1 coarse | 1,378 | 2,570 | 50 | 16.3 / 12.0 |
| D S2 coarse | 1,407 | 4,395 | 50 | 13.8 / 13.8 |
| D S3 coarse | 1,359 | 2,665 | 50 | 0.37 / 0.36 |
| E S2 oracle | 1,408 | 5,498 | 50 | 8.90 / 8.34 |

The E cell: 50 sampled checks after every update, none mismatched; its full
checkpoint at update 50 (selective = full = a from-zero build, 1,108 s)
agreed.

| | prediction | result |
|---|---|---|
| T1 | no cell ends in `error` or by a limit | **held** |
| T2 | build + first check within 1,000-1,800 s | **held** (1,316-1,408 s) |
| T3 | the E cell's checkpoint agrees | **held** |
| T4 | no peak RSS above 6 GB | **held** (5,498 MB) |
| T5 | the queue ends within 3 h | **held** (2.0 h) |

**Inclusion (the protocol's rule): met.** D16 includes BDD-APKeep's
wl_cloud cells beyond A: 15 cells. Estimated from these records (calibration
`project.py`, mean rates): 3 of the pair's 18 cells reach the 12 h cap — C S4
(~25 h), E S4 (~50 h) and D S1 coarse (~16 h) — and are recorded as timeouts
(owner, 2026-10-17); A S1 ~11 h; the rest 0.4-4 h.
