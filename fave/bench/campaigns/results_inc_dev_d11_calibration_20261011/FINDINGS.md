# Findings: the D11 sizing calibration (dev), 2026-10-11/12

`PROTOCOL.txt` was committed (`c32b9ce9`) before any cell ran. It declares the code
as `updates` at `e96f6b89` + `a8e3c2b3`. Its purpose is to project full-stream
wall times for the D11 run, and nothing else. The run is indicative only:
limit_class dev, one repetition, the first 50 updates of each stream.

The raw records live in four directories:
- `cells/`: `run.sh`, as declared.
- `cells_jar_rerun/`: 12 of its cells re-run on the declared jar (deviation 3).
- `cells_fixed/` and `cells_fixed2/`: `wl_up` × BDD-APKeep on the M2 code
  (deviation 2).

`run.log` carries every deviation as a dated DECLARED line, written when it
happened.

## Deviations

1. **The integration tier ran alongside**, as the protocol says, and so did M2
   development in a worktree, including about 30 short diagnostic runs on
   12 October. The timings carry that interference.
2. **`wl_up` × BDD-APKeep.**
   - On the declared code, S1 finished **no update** in 7,200 s. Its build plus
     first check never ended. The first attempt was killed by the session tool's
     time limit at 5,951 s (`interrupted/`), and the runner was restarted
     detached.
   - S2 and S3 were therefore skipped on the old code (`SKIPPED.txt`), and all
     three were run on M2 instead.
   - The first M2 version (`d8318633`, `cells_fixed/`) crashed in S2 and S3.
     That was a reference-counting defect in its own `Network.unionOf`
     (`apkeep/FAVE_CHANGES.md` §14, fixed in `a850ad11`).
   - The fixed code (`cells_fixed2/`) completes all three. The three cells ran
     in parallel with each other and with `run.sh`.
3. **The APKeep jar was not always the declared code: my mistake.**
   - **What happened:** the worktree linked `apkeep/target` to this tree's.
     From 2026-10-11T15:44Z, every M2 build there replaced the jar this run
     loads. Those were work-in-progress builds, `d8318633`, diagnostic builds
     that are inert without `FAVE_APKEEP_DEBUG=1`, and finally `a850ad11`.
   - **Affected:** 12 BDD-/NDD-APKeep cells started on such a jar.
   - **One crash:** `wl_airtel2` × NDD-APKeep S3 ended in `error`
     (`NoClassDefFoundError: apkeep/checker/Witness$Hop`, 0 updates). A build
     had replaced the jar under its running JVM, so this is a session artefact,
     not an engine finding.
   - **Remedy:** the link was removed, and this tree's jar was rebuilt from its
     own source (`87b18e82`; sha256 prefix `3645a5154f8e754a`). The 12 cells
     were re-run on it, sequentially and alone (`run_jar_rerun.sh`,
     `cells_jar_rerun/`). The records in `cells/` stay.
   - **Unaffected:** the NDD jar and both C++ modules, which were last built
     before the run, and the two clean BDD-APKeep cells, whose JVMs started
     before 15:44Z.
   - **The reruns agree with the originals:** median per update within 0–7%,
     build + first check within 14% (`wl_airtel2` × NDD-APKeep S2: 18.2 s
     against 15.7 s). The 11 that completed both times differ in nothing that
     matters for sizing. The crashed cell now measures 50 of 50.

## Predictions

| | prediction | outcome |
|---|---|---|
| C1 | every cell completes its 50 updates or is stopped by its wall limit; none crashes | **falsified as recorded:** one `error` (`wl_airtel2` × NDD-APKeep S3), and it was a session artefact (deviation 3). On the declared code after the rerun, **held**: 37 cells measured, three stopped by the wall limit (`wl_stanford` × VeriFlow-FR S1 at 34 updates and S3 at 38; `wl_up` × BDD-APKeep S1 at 0), and two skipped by declaration |
| C2 | VeriFlow-FR (coarse) is the slowest engine per update on all four workloads, ≥ 10× NetPlumber on S1 | **falsified on one stream:** on `wl_airtel2` S3, VeriFlow-FR's median `t_total` is 41 ms against BDD-APKeep's 549 ms and NDD-APKeep's 527 ms. It **held** on S1 and S2 of all four workloads, and on S3 of the other three. On `wl_up`, BDD-APKeep on the declared code has no per-update number (its first check never ended); on M2, VeriFlow-FR is still the slowest there. Against NetPlumber on S1: 1,500× (`wl_airtel2`), 240× (`wl_up`), 2.0 M× (`wl_stanford`), 1,800× (`wl_i2`) |
| C3 | no cell's build + first check exceeds its V5 from-zero cost (RESULTS.md §2) by more than 2× | **falsified** on `wl_up` × BDD-APKeep: more than 7,200 s on the declared code against V5's 380 s, and 805 s on M2 (2.1×). Held on every NetPlumber and VeriFlow-FR cell, where the largest ratio is 1.25× (VeriFlow-FR on `wl_stanford`), and on BDD-APKeep elsewhere. **Not scorable for NDD-APKeep:** V5 has no NDD-APKeep cell. Its NDD-flood column is a different engine; for scale, NDD-APKeep's build + first check is 2–8× that |

## What it says for D11

Projections take the build + first check plus a full stream at the measured
mean per update (`project.py`, in the D11 run's directory):

| full stream, projected | S1 | S2 | S3 |
|---|---:|---:|---:|
| `wl_up` × VeriFlow-FR | 84 h | 22 h | 43 h |
| `wl_up` × BDD-APKeep (M2) | 43 h | 37 h | 35 h |
| `wl_up` × NDD-APKeep | 0.8 h | 6.2 h | 13.8 h |
| `wl_stanford` × VeriFlow-FR | 985 h | 96 h | — |
| `wl_i2` × VeriFlow-FR | 5,428 h | 1,022 h | — |
| `wl_i2` × NDD-APKeep | 74 h | 15 h | — |

NetPlumber needs at most 3 h for any of them.

**Reading it:**
- **A full grid cannot run once here.** VeriFlow-FR's re-walk of every
  affected source costs 120–200 s per update on `wl_stanford` and `wl_i2`. The
  D11 run therefore caps each cell at 7,200 s, the same cap as here. A capped
  cell's partial stream is its indicative number.
- **Link updates are the expensive stream for every engine but NetPlumber.**
  `wl_up` S3 medians: VeriFlow-FR 168 s, BDD-APKeep 124 s, NDD-APKeep 50 s,
  NetPlumber 6 ms.
- **NDD-APKeep builds `wl_up` 12× faster than BDD-APKeep** (68 s against
  805 s), and on S1 its per-update median is the same (141 ms against 144 ms).
